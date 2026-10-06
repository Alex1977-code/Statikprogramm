"""
Export nach SAF - Structural Analysis Format (Excel).

Geschrieben werden die Blaetter, die der SAF-Import wieder liest und die RFEM 6,
SCIA, Allplan und AxisVM erwarten: Knoten, Stabzuege, Staebe, Flaechen,
Querschnitte, Materialien, Lager, Lastfaelle, Lastgruppen und Lasten.

Grundsatz (Fehlerliste 06.10.2026, F26): was SAF darstellen kann, geht
vollstaendig hinaus, was nicht, wird **im Protokoll genannt** - es wird weder
still weggelassen noch verfaelscht geschrieben. Das gilt hier fuer

* **Stablasten** (Blatt StructuralCurveAction, Spalten nach der SAF-
  Beschreibung): gleichmaessig, trapezfoermig (Distribution Trapez, Value 1
  und 2) und abschnittsweise (Extent Span mit Start und End point, absolut vom
  Stabanfang); global oder im Stabsystem (Local). Bis zum 06.10.2026 gingen nur
  ``q`` und ``system`` hinaus, und der Stab hiess "E<Element>" statt wie im
  Blatt der Staebe;
* **Ergebniskombinationen**: SAF fuehrt eine Kombination als Summe
  (Lastfall und Faktor). Jede Alternative geht als gewoehnliche Kombination
  "<Name> [k]" hinaus; die Spalte "Envelope" - eine Spalte, die SAF nicht
  kennt - haelt sie fuer Statik3D zusammen. Bis zum 06.10.2026 fehlte die
  Ergebniskombination im Blatt, ohne ein Wort im Protokoll.
"""
from __future__ import annotations

import numpy as np

from ..model import Model
from ..importers.xlsx_reader import write_xlsx
from ..elements import beam3d as bm
from .. import elemente as EL
from . import _common as C

#: Lagerbedingung -> SAF-Schluesselwort (die Federsteifigkeit steht in der
#: eigenen Spalte "Stiffness ...", so wie SAF es fuehrt)
def _cond(beh) -> str:
    if beh.typ == "rigid":
        return "Rigid"
    if beh.typ == "spring":
        return "Flexible"
    return "Free"


#: Kopfzeile des Blattes StructuralCurveAction - die Spalten und Werte der
#: SAF-Beschreibung (gitbook.saf.guide, geprueft 06.10.2026); die Einheit steht
#: in der Kopfzeile, so liest sie auch der Import
STABLAST_KOPF = ["Name", "Type", "Force action", "Distribution", "Direction",
                 "Value 1 [kN/m]", "Value 2 [kN/m]", "Member", "Load case",
                 "Coordinate system", "Location", "Coordinate definition", "Origin",
                 "Extent", "Start point [m]", "End point [m]"]


def _lage_der_elemente(model: Model) -> tuple:
    """Wo jedes Stabelement im SAF-Stab liegt.

    Rueckgabe ``(lagen, staebe, ohne)``:

    * ``lagen``: Element -> (Stab, Beginn, Laenge, vorwaerts). ``Beginn`` ist der
      Abstand der dem SAF-Anfangsknoten naeheren Elementecke [m] **entlang des
      Stabes, wie ihn die Datei fuehrt** (von ``C.chain_ends``, also nicht
      unbedingt in der Richtung der Elemente); ``vorwaerts`` sagt, ob das Element
      selbst in dieser Richtung gezeichnet ist.
    * ``staebe``: Stab -> (Laenge entlang der Elemente, Achsen des SAF-Stabes
      oder None, Abstand der Endknoten). Die Achsen sind die des Stabes, den der
      Import aus Anfangs- und Endknoten und der Rotation des ersten Elements
      bildet - in ihnen stehen die lokalen Lasten.
    * ``ohne``: Element -> Stab fuer die Elemente, die sich nicht als Kette vom
      Anfangs- zum Endknoten ordnen lassen (Luecke, Verzweigung)."""
    lagen: dict = {}
    staebe: dict = {}
    ohne: dict = {}
    for name, elems in C.member_chains(model):
        na, nb = C.chain_ends(model, elems)
        e0 = model.elements[elems[0]]
        try:
            T3, _ = bm.local_axes(model.nodes[na], model.nodes[nb], e0.roll)
        except ValueError:
            T3 = None
        knoten, pos, rest, weg = int(na), 0.0, list(elems), {}
        while rest:
            for e in rest:
                n0, n1 = (int(x) for x in model.elements[e].nodes[:2])
                if knoten in (n0, n1):
                    break
            else:
                weg = None
                break
            L = model.element_length(e)
            vor = n0 == knoten
            weg[e] = (pos, L, vor)
            pos += L
            knoten = n1 if vor else n0
            rest.remove(e)
        staebe[name] = (sum(model.element_length(e) for e in elems), T3,
                        float(np.linalg.norm(model.nodes[nb] - model.nodes[na])))
        if weg is None:
            for e in elems:
                ohne.setdefault(int(e), name)
            continue
        for e, (p, L, vor) in weg.items():
            lagen.setdefault(int(e), (name, p, L, vor))
    return lagen, staebe, ohne


def _stablasten(model: Model, log) -> list:
    """Das Blatt StructuralCurveAction: je Stablast und nicht verschwindender
    Richtung (X, Y, Z) eine Zeile, Werte in kN/m.

    Die Stablast des Modells liegt auf einem **Element** (q bei ``a``, q2 bei
    ``b``, global oder im Elementsystem). Hier wird sie auf den SAF-Stab gelegt:
    Positionen entlang des Stabes von seinem SAF-Anfang aus (ein Element, das
    entgegen dem Stab gezeichnet ist, tauscht Anfang und Ende und damit Value 1
    und 2), lokale Werte in die Achsen des SAF-Stabes gedreht (Element mit anderer
    Rollung oder Richtung als der Stab). Was sich nicht legen laesst, steht im
    Protokoll und nicht im Blatt."""
    lagen, staebe, ohne = _lage_der_elemente(model)
    zeilen = [list(STABLAST_KOPF)]
    nicht: dict = {}
    gekruemmt: set = set()
    n_last = n_trapez = n_abschnitt = k = 0

    def melden(stab, grund, fall):
        nicht.setdefault((stab, grund), []).append(fall)

    for fall, lc in model.load_cases.items():
        for l in lc.beam_loads:
            i = int(l.elem)
            if not 0 <= i < len(model.elements) or model.elements[i].typ not in EL.STAB_TYPEN:
                melden(f"Element {i + 1}", "kein Stabelement (die Rechnung trägt eine Stablast "
                                           "dort auch nicht ein)", fall)
                continue
            lage = lagen.get(i)
            if lage is None:
                melden(f"Stab '{ohne.get(i, f'E{i + 1}')}'", "seine Elemente liegen nicht als Kette "
                       "vom Anfangs- zum Endknoten hintereinander, die Lage entlang des Stabes ist "
                       "nicht eindeutig", fall)
                continue
            stab, pos, L, vor = lage
            gesamt, T3m, sehne = staebe[stab]
            a = max(0.0, float(l.a or 0.0))
            b = L if l.b is None else min(float(l.b), L)
            if b <= a:
                continue                     # kein belasteter Abschnitt - die Rechnung traegt nichts ein
            q1 = np.array(l.q, float)
            q2 = np.array(l.q2, float) if l.q2 is not None else q1.copy()
            lokal = l.system == "local"
            if lokal:
                if T3m is None:
                    melden(f"Stab '{stab}'", "Anfangs- und Endknoten fallen zusammen, es gibt kein "
                           "Stabsystem für eine lokale Last", fall)
                    continue
                e = model.elements[i]
                T3e, _ = bm.local_axes(model.nodes[e.nodes[0]], model.nodes[e.nodes[1]], e.roll)
                R = T3m @ T3e.T              # Elementachsen -> Achsen des SAF-Stabes
                q1, q2 = R @ q1, R @ q2
            if vor:
                x1, x2, v1, v2 = pos + a, pos + b, q1, q2
            else:
                x1, x2, v1, v2 = pos + L - b, pos + L - a, q2, q1
            skala = max(float(np.max(np.abs(v1))), float(np.max(np.abs(v2))))
            eps = 1e-9 * skala               # Rundung der Drehung ist keine Last
            ganz = abs(x1) <= 1e-9 * max(gesamt, 1.0) and abs(x2 - gesamt) <= 1e-9 * max(gesamt, 1.0)
            n_zeilen = 0
            trapez = False
            for c, achse in enumerate("XYZ"):
                w1, w2 = (float(v1[c]) if abs(v1[c]) > eps else 0.0,
                          float(v2[c]) if abs(v2[c]) > eps else 0.0)
                if w1 == 0.0 and w2 == 0.0:
                    continue
                gleich = abs(w1 - w2) <= eps
                trapez = trapez or not gleich
                k += 1
                n_zeilen += 1
                zeilen.append([f"Q{k}", "Standard", "On beam", "Uniform" if gleich else "Trapez",
                               achse, w1 / 1e3, (w1 if gleich else w2) / 1e3, stab, fall,
                               "Local" if lokal else "Global", "" if lokal else "Length",
                               "Absolute", "From start", "Full" if ganz else "Span",
                               "" if ganz else float(x1), "" if ganz else float(x2)])
            if n_zeilen:
                n_last += 1
                n_trapez += int(trapez)
                n_abschnitt += int(a > 1e-9 * L or b < L * (1 - 1e-9))    # Abschnitt im Modell, nicht Stabteil
                if abs(gesamt - sehne) > 1e-6 * max(gesamt, 1.0):
                    gekruemmt.add((stab, gesamt, sehne))
    if n_last:
        C.say(log, f"SAF: {n_last} Stablasten geschrieben ({len(zeilen) - 1} Zeilen, "
                   f"{n_trapez} trapezförmig, {n_abschnitt} abschnittsweise)")
    for stab, gesamt, sehne in sorted(gekruemmt):
        C.warn(log, f"SAF: Stab '{stab}' ist nicht gerade (Länge entlang der Elemente {gesamt:g} m, "
                    f"Abstand der Endknoten {sehne:g} m); die Datei führt ihn als gerade Verbindung "
                    "seiner Endknoten, die Lastpositionen sind Längen entlang der Elemente")
    for (stab, grund), faelle in nicht.items():
        folge = ", ".join(sorted(set(faelle)))
        C.warn(log, f"SAF: {len(faelle)} Stablast{'en' if len(faelle) != 1 else ''} auf {stab} "
                    f"(Lastfall {folge}) nicht geschrieben: {grund}")
    return zeilen


def write_saf(model: Model, path: str, results=None, log: list = None, **_) -> str:
    blaetter: dict[str, list[list]] = {}

    blaetter["StructuralPointConnection"] = [
        ["Name", "Coordinate X", "Coordinate Y", "Coordinate Z"]] + [
        [f"N{i + 1}", float(p[0]), float(p[1]), float(p[2])]
        for i, p in enumerate(model.nodes)]

    mats = [["Name", "Material type", "Quality", "Unit mass", "E modulus",
             "Poisson coefficient", "G modulus", "Thermal expansion",
             "Yield strength", "Ultimate strength"]]
    for name, m in model.materials.items():
        mats.append([name, "Steel", m.grade or name, float(m.rho), float(m.E),
                     float(m.nu), float(m.G), float(m.alpha),
                     float(m.fy or 0.0), float(m.fu or 0.0)])
    blaetter["StructuralMaterial"] = mats

    secs = [["Name", "Material", "Form code", "A", "I y", "I z", "I t",
             "Height", "Width", "Web thickness", "Flange thickness"]]
    for name, s in model.sections.items():
        secs.append([name, next(iter(model.materials), ""), s.typ, float(s.A),
                     float(s.Iy), float(s.Iz), float(s.It), float(s.h),
                     float(s.b), float(s.tw), float(s.tf)])
    blaetter["StructuralCrossSection"] = secs

    kurven = [["Name", "Cross-section", "Material", "Begin node", "End node",
               "Rotation", "Length", "Type"]]
    for name, elems in C.member_chains(model):
        na, nb = C.chain_ends(model, elems)
        e = model.elements[elems[0]]
        kurven.append([name, e.sec or "", e.mat, f"N{na + 1}", f"N{nb + 1}",
                       float(np.degrees(e.roll)), C.chain_length(model, elems), "Beam"])
    blaetter["StructuralCurveMember"] = kurven

    flaechen = [["Name", "Material", "Thickness", "Nodes", "Type"]]
    for i in C.shell_elements(model):
        e = model.elements[i]
        t = model.shells[e.sec].t if e.sec in model.shells else 0.010
        flaechen.append([f"S{i + 1}", e.mat, float(t),
                         ";".join(f"N{int(n) + 1}" for n in e.nodes), "Plate"])
    blaetter["StructuralSurfaceMember"] = flaechen

    # Spaltennamen nach SAF: ux uy uz fix fiy fiz, dazu die Steifigkeiten
    lager = [["Name", "Node", "ux", "uy", "uz", "fix", "fiy", "fiz",
              "Stiffness X", "Stiffness Y", "Stiffness Z",
              "Stiffness fix", "Stiffness fiy", "Stiffness fiz",
              "Coordinate system"]]
    for i, sup in enumerate(model.supports, 1):
        b = [sup.dof_behaviour(d) for d in range(6)]
        lager.append([sup.name or f"Sn{i}", f"N{sup.node + 1}"]
                     + [_cond(x) for x in b]
                     + [float(x.stiffness) if x.typ == "spring" else "" for x in b]
                     + ["Global"])
    blaetter["StructuralPointSupport"] = lager

    faelle = [["Name", "Load group", "Load type", "Action type", "Description"]]
    for name, lc in model.load_cases.items():
        faelle.append([name, lc.category, "Static", lc.category, lc.description])
    blaetter["StructuralLoadCase"] = faelle

    # Eine gewoehnliche Kombination ist eine Summe: je Lastfall eine Zeile.
    # Eine Ergebniskombination (Umhuellende ueber Alternativen, ``factors`` leer)
    # schrieb dieser Export bis zum 06.10.2026 gar nicht (F26); SAF kennt keine
    # Umhuellende, wohl aber die Summe - darum je Alternative eine Kombination
    # "<Name> [k]" (derselbe Name wie in den Ergebnissen, solver.
    # alternativen_der_kombination), und die Spalte "Envelope" nennt die
    # Ergebniskombination, zu der sie gehoert (Statik3D liest daraus wieder eine)
    from ..solver import alternativen_der_kombination
    kombis = [["Name", "Description", "Category", "Load case", "Factor", "Envelope"]]
    n_ek = n_alt = 0
    for name, c in model.combinations.items():
        if c.ist_umhuellende:
            n_ek += 1
            for alt_name, teile in alternativen_der_kombination(c):
                n_alt += 1
                for lf, f in teile.items():
                    kombis.append([alt_name, c.description, c.typ, lf, float(f), name])
        else:
            for lf, f in c.factors.items():
                kombis.append([name, c.description, c.typ, lf, float(f), ""])
    blaetter["StructuralLoadCombination"] = kombis
    if n_ek:
        C.say(log, f"SAF: {n_ek} Ergebniskombination{'en' if n_ek != 1 else ''} mit {n_alt} "
                   "Alternativen als gewöhnliche Kombinationen „<Name> [k]“ geschrieben. SAF kennt "
                   "keine Umhüllende; die Spalte „Envelope“ hält sie für Statik3D zusammen, andere "
                   "Programme lesen jede Alternative einzeln")

    lasten = [["Name", "Load case", "Node", "Fx", "Fy", "Fz", "Mx", "My", "Mz"]]
    k = 0
    for name, lc in model.load_cases.items():
        for l in lc.nodal_loads:
            k += 1
            lasten.append([f"F{k}", name, f"N{l.node + 1}"]
                          + [float(v) for v in l.F])
    blaetter["StructuralPointAction"] = lasten

    blaetter["StructuralCurveAction"] = _stablasten(model, log)

    write_xlsx(path, blaetter)
    C.say(log, f"SAF geschrieben: {len(blaetter)} Blätter, {model.nn} Knoten, "
               f"{len(kurven) - 1} Stäbe -> {path}")
    return path
