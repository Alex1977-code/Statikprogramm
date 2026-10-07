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

Nachtrag zur Fehlerliste (07.10.2026, N25 bis N30) - der Rundlauf Export ->
Import gibt seitdem dasselbe Modell zurueck (tests.test_nachtrag_q8):

* **Knotenlasten** (N25): je Knotenlast und Komponente eine Zeile, Kraefte im
  Blatt StructuralPointAction (Direction X/Y/Z, Value [kN]), Momente im Blatt
  StructuralPointMoment (Direction Mx/My/Mz, Value [kNm]), beide mit Force
  action "In node" und Reference node. Bis zum 07.10.2026 standen Fx ... Mz als
  Spalten ohne Direction und Value da; der Import las keine Zeile davon.
* **Einheiten** (N26) nach der Einheitentabelle der SAF-Beschreibung
  (gitbook.saf.guide, gelesen 07.10.2026), in der Kopfzeile genannt: E und G in
  MPa, Dichte kg/m3, A m2, I m4, Iw m6, Wpl m3, Parameter und Dicken mm; f_y und
  f_u als "Design properties" (1|f_y; 2|f_u in MPa). Ein Querschnitt geht als
  Profil der Datenbank (Manufactured), als Form mit Abmessungen (Parametric)
  oder mit seinen Kennwerten (General) hinaus. Bis zum 07.10.2026 standen E und
  die Kennwerte in SI ohne Einheit da; der Import las E als MPa (2,1e17 Pa), A
  als mm² und die Dicke als mm.
* **Rollung** (N27): die Datei fuehrt einen Stab vom kleineren zum groesseren
  Endknoten (_common.chain_ends). Ist das erste Element andersherum gezeichnet,
  wird die Rollung so umgerechnet, dass die lokale z-Achse bleibt. Bis zum
  07.10.2026 ging die Rollung des Elements unveraendert hinaus, der Stab kam um
  2θ verdreht zurueck.
* **Eigengewicht, Temperatur, Flaechenlasten** (N28): Eigengewicht als Lastfall
  mit Load type "Self weight", Temperatur im Blatt StructuralCurveActionThermal
  (Staebe) und StructuralSurfaceActionThermal (Schalen), Flaechenlasten im Blatt
  StructuralSurfaceAction. Was SAF nicht kennt (Situation, Theorie,
  Leiteinwirkung, Zwangsverformung, Vorspannung, Uebermass, Lasten auf
  Volumenelementen), nennt das Protokoll als WARNUNG.
* **Staebe aus mehreren Elementen** (N30): die Spalte Nodes nennt alle Knoten
  der Elementkette (Segments Line); bis zum 07.10.2026 standen nur Anfangs- und
  Endknoten da, und der Stab kam als ein Element zurueck.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

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

#: Erdbeschleunigung, die der Import fuer "Self weight" ansetzt (importers/saf.py)
G_SAF = 9.81


def _namen(liste, n: int = 8) -> str:
    """Die ersten n Eintraege, dazu "und k weitere"."""
    liste = list(liste)
    text = ", ".join(liste[:n])
    return text + (f" und {len(liste) - n} weitere" if len(liste) > n else "")


# --------------------------------------------------------------------------
# Staebe: Elementkette, Rollung, Achsen (N27, N30)
# --------------------------------------------------------------------------
def _kette(model: Model, elems: list, na: int):
    """Die Elemente eines Stabes als Kette vom SAF-Anfangsknoten ``na`` aus:
    ``(folge, punkte)`` mit ``folge`` = [(Element, vorwaerts)] und ``punkte`` =
    die Knoten der Kette in dieser Reihenfolge. None, wenn sie sich nicht als
    Kette ordnen lassen (Luecke, Verzweigung)."""
    knoten, rest, folge, punkte = int(na), [int(e) for e in elems], [], [int(na)]
    while rest:
        for e in rest:
            n0, n1 = (int(x) for x in model.elements[e].nodes[:2])
            if knoten in (n0, n1):
                break
        else:
            return None
        vor = n0 == knoten
        knoten = n1 if vor else n0
        folge.append((e, vor))
        punkte.append(knoten)
        rest.remove(e)
    return folge, punkte


def _z_achse(model: Model, e: int) -> np.ndarray:
    el = model.elements[e]
    return bm.local_axes(model.nodes[int(el.nodes[0])], model.nodes[int(el.nodes[1])], el.roll)[0][2]


def _rollung_fuer(model: Model, e: int, p_a, p_b) -> float:
    """Die Rollung [rad] eines Stabes von p_a nach p_b, mit der seine lokale
    z-Achse die des Elements e ist (N27).

    beam3d.local_axes dreht die Grundachsen (y0, z0) um x: z(θ) = -sin θ y0 +
    cos θ z0. Laeuft der Stab entgegen dem Element, kehrt sich x um und die
    Grundachsen mit ihm; dieselbe Rollung legte z woanders hin - gemessen am
    senkrechten Stab mit 0,5 rad um 57,3° (2θ) gedreht."""
    ze = _z_achse(model, e)
    T0, _ = bm.local_axes(p_a, p_b, 0.0)
    return float(np.arctan2(-float(ze @ T0[1]), float(ze @ T0[2])))


def _staebe(model: Model) -> list:
    """Je SAF-Stab (``_common.member_chains``) ein dict:

    * ``name``, ``elems``, ``na``, ``nb`` (Anfangs- und Endknoten der Datei),
      ``erstes`` (das Element am Anfangsknoten - seine Rollung, sein
      Querschnitt und Werkstoff gelten fuer den Stab);
    * ``punkte``: die Knoten der Kette von na nach nb (Spalte Nodes, N30) oder
      None, wenn die Elemente keine Kette bilden;
    * ``roll``: die Rollung [rad], die die Datei fuehrt (N27);
    * ``achsen``: Element -> Achsen (3x3) des Abschnitts, den der Import aus
      zwei aufeinanderfolgenden Knoten mit dieser Rollung baut - in ihnen stehen
      die lokalen Lasten;
    * ``lagen``: Element -> (Beginn, Laenge, vorwaerts) entlang des Stabes;
    * ``anders``: was an den Elementen nicht mit einem SAF-Stab geht
      (verschiedene Rollung, Querschnitte, Werkstoffe, Elementarten)."""
    out = []
    p = model.nodes
    for name, elems in C.member_chains(model):
        na, nb = C.chain_ends(model, elems)
        k = _kette(model, elems, na)
        st = {"name": name, "elems": elems, "na": na, "nb": nb, "punkte": None,
              "achsen": {}, "lagen": {}, "anders": []}
        if k is None:
            st["erstes"] = int(elems[0])
            st["roll"] = float(model.elements[elems[0]].roll)
        else:
            folge, punkte = k
            e0, vor0 = folge[0]
            st["erstes"] = e0
            st["punkte"] = punkte
            # vorwaerts bleibt die Rollung des Elements, wie sie ist (4,0 rad
            # ginge sonst als -2,28 rad hinaus - gleiche Achsen, fremde Zahl)
            st["roll"] = float(model.elements[e0].roll)
            if not vor0:
                try:
                    st["roll"] = _rollung_fuer(model, e0, p[punkte[0]], p[punkte[1]])
                except ValueError:           # Element der Laenge 0: keine Achsen
                    pass
            pos = 0.0
            dreh = 0.0
            for (e, vor), a, b in zip(folge, punkte[:-1], punkte[1:]):
                L = model.element_length(e)
                try:
                    T3s = bm.local_axes(p[a], p[b], st["roll"])[0]
                except ValueError:
                    T3s = None
                st["achsen"][e] = T3s
                st["lagen"][e] = (pos, L, vor)
                pos += L
                if T3s is not None and model.elements[e].typ == "beam":
                    c = float(np.clip(T3s[2] @ _z_achse(model, e), -1.0, 1.0))
                    dreh = max(dreh, float(np.degrees(np.arccos(c))))
            if dreh > 1e-6:
                st["anders"].append(f"der Rollung (lokale z-Achse bis {dreh:.3g}° gegen die des Stabes)")
        ref = model.elements[st["erstes"]]
        for feld, wort in (("sec", "den Querschnitten"), ("mat", "den Werkstoffen"),
                           ("typ", "der Elementart")):
            werte = sorted({str(getattr(model.elements[e], feld) or "") for e in elems})
            if len(werte) > 1:
                st["anders"].append(f"{wort} ({', '.join(werte)}; geschrieben {getattr(ref, feld)})")
        out.append(st)
    return out


# --------------------------------------------------------------------------
# Querschnitte (N26)
# --------------------------------------------------------------------------
def _gleiche_werte(a, b) -> bool:
    """Zwei Querschnitte mit denselben Kennwerten (bis auf den Namen; Zahlen
    relativ auf 1e-9)."""
    for f in dataclasses.fields(a):
        if f.name == "name":
            continue
        x, y = getattr(a, f.name), getattr(b, f.name)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if abs(float(x) - float(y)) > 1e-9 * max(abs(float(x)), abs(float(y))):
                return False
        elif x != y:
            return False
    return True


#: Statik3D-Bauart -> SAF-Form (Parametric) und Parameter [m] in der
#: Reihenfolge der SAF-Beschreibung (Annex "Supported shapes of parametric
#: cross-section"): Rectangle H; B - Circle D - Pipe D; t - I rolled H; B; t; s; R
def _form(s) -> Optional[tuple]:
    if s.typ == "rect":
        return "Rectangle", [s.h, s.b]
    if s.typ == "circle":
        return "Circle", [s.h]
    if s.typ == "CHS":
        return "Pipe", [s.h, s.tw]
    if s.typ == "I":
        return "I rolled", [s.h, s.b, s.tf, s.tw, s.r]
    return None


def _querschnitt(name: str, s) -> tuple:
    """(Cross-section type, Shape, Parameters [mm], Profile) des Querschnitts.

    Manufactured nur, wenn das Profil der Datenbank gleichen Namens dieselben
    Kennwerte hat; Parametric nur, wenn der Import aus Form und geschriebenen
    Abmessungen denselben Querschnitt baut (beides mit den Funktionen des
    Imports geprueft). Sonst General mit den Kennwerten. Das Beispiel "frame"
    etwa traegt ein HEA 200 ohne Ausrundung: aus der Datenbank kaeme es mit
    A = 53,8 statt 51,1 cm² zurueck."""
    from ..importers import _common as IC
    from ..importers.saf import _section_from_shape
    db = IC.section_from_designation(name, name)
    if db is not None and _gleiche_werte(db, s):
        return "Manufactured", "", "", name
    form = _form(s)
    if form is not None:
        shape, werte = form
        texte = [f"{float(v) * 1e3:.12g}" for v in werte]
        nachgebaut = _section_from_shape(name, shape, [float(t) * 1e-3 for t in texte])
        if nachgebaut is not None and _gleiche_werte(nachgebaut, s):
            return "Parametric", shape, "; ".join(texte), ""
    return "General", "", "", ""


# --------------------------------------------------------------------------
# Stablasten
# --------------------------------------------------------------------------
def _stablasten(model: Model, log, staebe: list) -> list:
    """Das Blatt StructuralCurveAction: je Stablast und nicht verschwindender
    Richtung (X, Y, Z) eine Zeile, Werte in kN/m.

    Die Stablast des Modells liegt auf einem **Element** (q bei ``a``, q2 bei
    ``b``, global oder im Elementsystem). Hier wird sie auf den SAF-Stab gelegt:
    Positionen entlang des Stabes von seinem SAF-Anfang aus (ein Element, das
    entgegen dem Stab gezeichnet ist, tauscht Anfang und Ende und damit Value 1
    und 2), lokale Werte in die Achsen des Abschnitts gedreht, den der Import
    baut (Element mit anderer Rollung oder Richtung als der Stab). Was sich nicht
    legen laesst, steht im Protokoll und nicht im Blatt."""
    lagen, achsen, gesamt_von, ohne = {}, {}, {}, {}
    for st in staebe:
        gesamt_von[st["name"]] = sum(model.element_length(e) for e in st["elems"])
        for e in st["elems"]:
            if e in st["lagen"]:
                lagen.setdefault(e, (st["name"],) + st["lagen"][e])
                achsen.setdefault(e, st["achsen"][e])
            else:
                ohne.setdefault(int(e), st["name"])
    zeilen = [list(STABLAST_KOPF)]
    nicht: dict = {}
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
            gesamt = gesamt_von[stab]
            a = max(0.0, float(l.a or 0.0))
            b = L if l.b is None else min(float(l.b), L)
            if b <= a:
                continue                     # kein belasteter Abschnitt - die Rechnung traegt nichts ein
            q1 = np.array(l.q, float)
            q2 = np.array(l.q2, float) if l.q2 is not None else q1.copy()
            lokal = l.system == "local"
            if lokal:
                T3s = achsen.get(i)
                if T3s is None:
                    melden(f"Stab '{stab}'", "Anfangs- und Endknoten fallen zusammen, es gibt kein "
                           "Stabsystem für eine lokale Last", fall)
                    continue
                e = model.elements[i]
                T3e, _ = bm.local_axes(model.nodes[e.nodes[0]], model.nodes[e.nodes[1]], e.roll)
                R = T3s @ T3e.T              # Elementachsen -> Achsen des SAF-Abschnitts
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
    if n_last:
        C.say(log, f"SAF: {n_last} Stablasten geschrieben ({len(zeilen) - 1} Zeilen, "
                   f"{n_trapez} trapezförmig, {n_abschnitt} abschnittsweise)")
    for (stab, grund), faelle in nicht.items():
        folge = ", ".join(sorted(set(faelle)))
        C.warn(log, f"SAF: {len(faelle)} Stablast{'en' if len(faelle) != 1 else ''} auf {stab} "
                    f"(Lastfall {folge}) nicht geschrieben: {grund}")
    return zeilen


# --------------------------------------------------------------------------
# Knotenlasten (N25)
# --------------------------------------------------------------------------
def _knotenlasten(model: Model, log) -> tuple:
    """Die Blaetter StructuralPointAction (Kraefte, kN) und
    StructuralPointMoment (Momente, kNm): je Knotenlast und nicht
    verschwindender Komponente eine Zeile, global, "In node"."""
    kraefte = [["Name", "Type", "Direction", "Force action", "Reference node", "Value [kN]",
                "Load case", "Coordinate system"]]
    momente = [["Name", "Type", "Direction", "Force action", "Reference node", "Value [kNm]",
                "Load case", "Coordinate system"]]
    n_last = 0
    for fall, lc in model.load_cases.items():
        for l in lc.nodal_loads:
            F = [float(v) for v in l.F]
            if not any(F):
                continue
            n_last += 1
            for c, v in enumerate(F):
                if v == 0.0:
                    continue
                if c < 3:
                    kraefte.append([f"F{len(kraefte)}", "Standard", "XYZ"[c], "In node",
                                    f"N{int(l.node) + 1}", v / 1e3, fall, "Global"])
                else:
                    momente.append([f"M{len(momente)}", "Standard", ("Mx", "My", "Mz")[c - 3], "In node",
                                    f"N{int(l.node) + 1}", v / 1e3, fall, "Global"])
    if n_last:
        C.say(log, f"SAF: {n_last} Knotenlasten geschrieben ({len(kraefte) - 1} Kraft-, "
                   f"{len(momente) - 1} Momentzeilen)")
    return kraefte, momente


# --------------------------------------------------------------------------
# Flaechen- und Temperaturlasten (N28)
# --------------------------------------------------------------------------
def _zaehlen(nicht: dict, fall: str, wort: str, n: int = 1) -> None:
    nicht[(fall, wort)] = nicht.get((fall, wort), 0) + n


def _flaechenlasten(model: Model, log, nicht: dict) -> list:
    """Das Blatt StructuralSurfaceAction (kN/m²) fuer Flaechenlasten auf
    Schalen: normal zur Schale als Local Z, mit Richtung als globale
    Komponenten X/Y/Z (die Rechnung nimmt die Richtung als Einheitsvektor,
    assemble.shell_face_load)."""
    zeilen = [["Name", "Direction", "Type", "Force action", "Value [kN/m2]", "2D Member",
               "Load case", "Coordinate system", "Location"]]
    n_last = 0
    for fall, lc in model.load_cases.items():
        for fl in lc.face_loads:
            i = int(fl.elem)
            if not 0 <= i < len(model.elements) or not model.elements[i].typ.startswith("shell"):
                _zaehlen(nicht, fall, "Flächenlasten auf Volumen- oder Scheibenelementen (SAF kennt "
                                      "Flächenlasten nur auf Schalen)")
                continue
            p = float(fl.p)
            if p == 0.0:
                continue
            n_last += 1
            if fl.direction is None:
                zeilen.append([f"SF{len(zeilen)}", "Z", "Standard", "On 2D member", p / 1e3,
                               f"S{i + 1}", fall, "Local", "Length"])
                continue
            d = np.asarray(fl.direction, float)
            d = d / (np.linalg.norm(d) or 1.0)
            for c, achse in enumerate("XYZ"):
                if abs(d[c]) > 1e-12:
                    zeilen.append([f"SF{len(zeilen)}", achse, "Standard", "On 2D member",
                                   p * float(d[c]) / 1e3, f"S{i + 1}", fall, "Global", "Length"])
    if n_last:
        C.say(log, f"SAF: {n_last} Flächenlasten geschrieben ({len(zeilen) - 1} Zeilen)")
    return zeilen


def _temperaturlasten(model: Model, log, staebe: list, nicht: dict) -> tuple:
    """Die Blaetter StructuralCurveActionThermal (Staebe) und
    StructuralSurfaceActionThermal (Schalen), Temperaturen in °C.

    Gleichmaessig (dT_z = 0): Variation Constant mit deltaT (Stab) bzw. TempT
    (Schale). Mit Temperaturunterschied: Variation Linear, TempT - TempB = dT_z
    (oben = lokale +z-Seite, nachgemessen: dT_z = +10 K hebt die Mitte eines
    Einfeldtraegers IPE 300, 4 m, z nach oben, um +0,8 mm), Mitte dT, beim Stab
    TempL = TempR = dT. Die Lage am Stab: das Element von Start bis End point,
    absolut vom Stabanfang."""
    lagen, achsen = {}, {}
    for st in staebe:
        for e, lage in st["lagen"].items():
            lagen.setdefault(e, (st["name"],) + lage)
            achsen.setdefault(e, st["achsen"][e])
    stab = [["Name", "Force action", "Variation", "deltaT [°C]", "TempL [°C]", "TempR [°C]",
             "TempT [°C]", "TempB [°C]", "Member", "Load case", "Coordinate definition", "Origin",
             "Start point [m]", "End point [m]"]]
    schale = [["Name", "Variation", "TempT [°C]", "TempB [°C]", "2D Member", "Load case"]]
    for fall, lc in model.load_cases.items():
        for tl in lc.temp_loads:
            i = int(tl.elem)
            dT, dTz = float(tl.dT), float(tl.dT_z)
            if dT == 0.0 and dTz == 0.0:
                continue
            typ = model.elements[i].typ if 0 <= i < len(model.elements) else ""
            if typ.startswith("shell"):
                if dTz == 0.0:
                    schale.append([f"TS{len(schale)}", "Constant", dT, "", f"S{i + 1}", fall])
                else:
                    schale.append([f"TS{len(schale)}", "Linear", dT + dTz / 2, dT - dTz / 2,
                                   f"S{i + 1}", fall])
                continue
            if typ not in EL.STAB_TYPEN:
                _zaehlen(nicht, fall, "Temperaturlasten auf Volumen- oder Scheibenelementen (SAF kennt "
                                      "Temperatur nur an Stäben und Schalen)")
                continue
            lage = lagen.get(i)
            if lage is None:
                _zaehlen(nicht, fall, "Temperaturlasten auf Stäben, deren Elemente keine Kette bilden "
                                      "(die Lage am Stab ist nicht eindeutig)")
                continue
            name, pos, L, _vor = lage
            if dTz != 0.0:
                T3s = achsen.get(i)
                c = float(T3s[2] @ _z_achse(model, i)) if T3s is not None else 0.0
                if abs(abs(c) - 1.0) > 1e-9:
                    _zaehlen(nicht, fall, "Temperaturunterschiede an Elementen, deren lokale z-Achse "
                                          "nicht die des Stabes ist (SAF führt je Stab eine Rollung)")
                    continue
                dTz *= float(np.sign(c))
                stab.append([f"TB{len(stab)}", "On beam", "Linear", "", dT, dT, dT + dTz / 2,
                             dT - dTz / 2, name, fall, "Absolute", "From start", float(pos),
                             float(pos + L)])
            else:
                stab.append([f"TB{len(stab)}", "On beam", "Constant", dT, "", "", "", "", name, fall,
                             "Absolute", "From start", float(pos), float(pos + L)])
    if len(stab) + len(schale) > 2:
        C.say(log, f"SAF: {len(stab) + len(schale) - 2} Temperaturlasten geschrieben "
                   f"({len(stab) - 1} auf Stäben, {len(schale) - 1} auf Schalen)")
    return stab, schale


def _ist_eigengewicht(g) -> bool:
    return bool(np.all(np.abs(np.asarray(g, float) - np.array([0.0, 0.0, -G_SAF])) <= 1e-9 * G_SAF))


def _nicht_geschrieben(model: Model, log, nicht: dict) -> None:
    """Was SAF nicht kennt, steht als WARNUNG im Protokoll (N28): Lasten ohne
    SAF-Gegenstueck je Lastfall, Eigengewicht ausser g = 9,81 m/s² in -Z,
    Situation und Theorie der Lastfaelle, Situation, Theorie und
    Leiteinwirkung der Kombinationen. Objektlasten (an Flaechen, Koerpern,
    Linien) gehen als die Element- und Knotenlasten hinaus, die sie beim
    Vernetzen erzeugt haben (Kennzeichen ``_geo``)."""
    for fall, lc in model.load_cases.items():
        g = np.asarray(lc.gravity if lc.gravity is not None else [0.0, 0.0, 0.0], float)
        if np.any(g) and not _ist_eigengewicht(g):
            C.warn(log, f"SAF: Lastfall {fall}: Eigengewicht mit g = ({g[0]:g}, {g[1]:g}, {g[2]:g}) m/s² "
                        "nicht geschrieben - SAF kennt nur das Eigengewicht „Self weight“ "
                        f"(g = {G_SAF:g} m/s² nach unten)")
        for liste, wort in (("zwangsverformungen", "Zwangsverformungen (Lagerverschiebungen; SAF kennt "
                                                   "sie nicht)"),
                            ("vorspannungen", "Vorspannungen (SAF kennt sie nicht)"),
                            ("uebermasse", "Übermaße (SAF kennt sie nicht)")):
            n = len(getattr(lc, liste, None) or [])
            if n:
                _zaehlen(nicht, fall, wort, n)
        objekte = len(lc.geometrielasten or []) + len(lc.linienlasten or [])
        if objekte:
            n_geo = sum(1 for liste in (lc.nodal_loads, lc.beam_loads, lc.face_loads, lc.temp_loads)
                        for l in liste if getattr(l, "_geo", False))
            if n_geo:
                C.say(log, f"SAF: Lastfall {fall}: {objekte} Objektlasten (an Flächen, Körpern, Linien) "
                           f"gehen als die {n_geo} Element- und Knotenlasten hinaus, die sie beim "
                           "Vernetzen erzeugt haben")
            else:
                _zaehlen(nicht, fall, "Objektlasten, die noch nicht auf Elemente verteilt sind "
                                      "(erst vernetzen)", objekte)
    for (fall, wort), n in nicht.items():
        C.warn(log, f"SAF: Lastfall {fall}: {wort} nicht geschrieben, Anzahl {n}")
    felder = []
    for fall, lc in model.load_cases.items():
        teile = []
        if getattr(lc, "situation", ""):
            teile.append(f"Situation „{lc.situation}“")
        if getattr(lc, "theorie", ""):
            teile.append(f"Theorie {lc.theorie}")
        if teile:
            felder.append(f"{fall} ({', '.join(teile)})")
    if felder:
        C.warn(log, "SAF: Situation und Theorie eines Lastfalls kennt SAF nicht, sie fehlen in der Datei: "
                    + _namen(felder))
    felder = []
    for name, c in model.combinations.items():
        teile = []
        if getattr(c, "situation", ""):
            teile.append(f"Situation „{c.situation}“")
        if getattr(c, "theorie", ""):
            teile.append(f"Theorie {c.theorie}")
        if getattr(c, "leading", ""):
            teile.append(f"Leiteinwirkung {c.leading}")
        if teile:
            felder.append(f"{name} ({', '.join(teile)})")
    if felder:
        C.warn(log, "SAF: Situation, Theorie und Leiteinwirkung einer Kombination kennt SAF nicht, sie "
                    "fehlen in der Datei: " + _namen(felder))


# --------------------------------------------------------------------------
def write_saf(model: Model, path: str, results=None, log: list = None, **_) -> str:
    blaetter: dict[str, list[list]] = {}

    blaetter["StructuralPointConnection"] = [
        ["Name", "Coordinate X [m]", "Coordinate Y [m]", "Coordinate Z [m]"]] + [
        [f"N{i + 1}", float(p[0]), float(p[1]), float(p[2])]
        for i, p in enumerate(model.nodes)]

    # Werkstoffe in den Einheiten der SAF-Beschreibung (N26); f_y und f_u als
    # "Design properties" (Index 1 und 2, MPa), nur wenn das Modell sie nennt
    mats = [["Name", "Material type", "Quality", "Unit mass [kg/m3]", "E modulus [MPa]",
             "Poisson coefficient", "G modulus [MPa]", "Thermal expansion [1/K]",
             "Design properties"]]
    for name, m in model.materials.items():
        dp = "; ".join(f"{k}|{float(v) / 1e6:.12g}" for k, v in ((1, m.fy), (2, m.fu)) if v)
        mats.append([name, "Steel", m.grade or name, float(m.rho), float(m.E) / 1e6,
                     float(m.nu), float(m.G) / 1e6, float(m.alpha), dp])
        if m.fy_dicke or m.fu_dicke:
            C.warn(log, f"SAF: Werkstoff '{name}': Streckgrenze und Zugfestigkeit nach Erzeugnisdicke "
                        "kennt SAF nicht - geschrieben "
                        + (f"f_y = {m.fy / 1e6:g} MPa" if m.fy else "nur die Sorte")
                        + (f", f_u = {m.fu / 1e6:g} MPa" if m.fu else ""))
    blaetter["StructuralMaterial"] = mats

    secs = [["Name", "Material", "Cross-section type", "Shape", "Parameters [mm]", "Profile",
             "Form code", "A [m2]", "Iy [m4]", "Iz [m4]", "It [m4]", "Iw [m6]", "Wply [m3]",
             "Wplz [m3]"]]
    frei = []
    for name, s in model.sections.items():
        art, shape, par, profil = _querschnitt(name, s)
        secs.append([name, next(iter(model.materials), ""), art, shape, par, profil, s.typ,
                     float(s.A), float(s.Iy), float(s.Iz), float(s.It), float(s.Iw),
                     float(s.Wpl_y), float(s.Wpl_z)])
        if art == "General":
            fehlt = [w for w, ja in (("Schubflächen", s.Asy or s.Asz),
                                     ("Abmessungen", s.h or s.b or s.tw or s.tf),
                                     ("elastische Widerstandsmomente und Randabstände",
                                      s.Wel_y or s.Wel_z or s.zmax or s.ymax)) if ja]
            frei.append(f"{name}" + (f" (ohne {', '.join(fehlt)})" if fehlt else ""))
    if frei:
        C.warn(log, "SAF: Querschnitte nur mit Kennwerten (A, Iy, Iz, It, Iw, Wpl) als „General“ ohne "
                    "Umriss (CompositeShapeDef) geschrieben - Statik3D liest sie zurück, andere "
                    "Programme brauchen den Umriss: " + _namen(frei))
    blaetter["StructuralCrossSection"] = secs

    staebe = _staebe(model)
    kurven = [["Name", "Type", "Cross-section", "Material", "Nodes", "Segments", "Begin node",
               "End node", "Length [m]", "LCS Rotation [deg]"]]
    for st in staebe:
        e = model.elements[st["erstes"]]
        punkte = st["punkte"] or [st["na"], st["nb"]]
        kurven.append([st["name"], "Beam", e.sec or "", e.mat,
                       "; ".join(f"N{int(n) + 1}" for n in punkte),
                       "; ".join(["Line"] * (len(punkte) - 1)),
                       f"N{st['na'] + 1}", f"N{st['nb'] + 1}",
                       C.chain_length(model, st["elems"]), float(np.degrees(st["roll"])) + 0.0])   # ohne -0.0
        if st["punkte"] is None and len(st["elems"]) > 1:
            C.warn(log, f"SAF: Stab '{st['name']}': seine {len(st['elems'])} Elemente bilden keine Kette "
                        "vom Anfangs- zum Endknoten (Lücke oder Verzweigung) - die Datei führt ihn als "
                        "ein Element zwischen seinen Endknoten")
        if st["anders"]:
            C.warn(log, f"SAF: Stab '{st['name']}': SAF führt je Stab eine Rollung, einen Querschnitt und "
                        "einen Werkstoff; seine Elemente unterscheiden sich in "
                        + "; ".join(st["anders"]) + " - alle Elemente kommen wie das erste zurück")
    blaetter["StructuralCurveMember"] = kurven

    flaechen = [["Name", "Material", "Thickness [mm]", "Nodes", "Type"]]
    for i in C.shell_elements(model):
        e = model.elements[i]
        t = model.shells[e.sec].t if e.sec in model.shells else 0.010
        flaechen.append([f"S{i + 1}", e.mat, float(t) * 1e3,
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

    # Eigengewicht (N28): ein Lastfall mit g = 9,81 m/s² nach unten fuehrt
    # Load type "Self weight" - so liest ihn der Import wieder als Eigengewicht.
    # Bis zum 07.10.2026 stand dort immer "Static", das Eigengewicht fehlte.
    faelle = [["Name", "Load group", "Load type", "Action type", "Description"]]
    n_eg = 0
    for name, lc in model.load_cases.items():
        eg = _ist_eigengewicht(lc.gravity if lc.gravity is not None else [0.0, 0.0, 0.0])
        n_eg += int(eg)
        faelle.append([name, lc.category, "Self weight" if eg else "Static", lc.category, lc.description])
    blaetter["StructuralLoadCase"] = faelle
    if n_eg:
        C.say(log, f"SAF: Eigengewicht in {n_eg} Lastfall{'' if n_eg == 1 else 'en'} als „Self weight“")

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

    nicht: dict = {}
    blaetter["StructuralPointAction"], blaetter["StructuralPointMoment"] = _knotenlasten(model, log)
    blaetter["StructuralCurveAction"] = _stablasten(model, log, staebe)
    blaetter["StructuralSurfaceAction"] = _flaechenlasten(model, log, nicht)
    (blaetter["StructuralCurveActionThermal"],
     blaetter["StructuralSurfaceActionThermal"]) = _temperaturlasten(model, log, staebe, nicht)
    _nicht_geschrieben(model, log, nicht)

    write_xlsx(path, blaetter)
    C.say(log, f"SAF geschrieben: {len(blaetter)} Blätter, {model.nn} Knoten, "
               f"{len(kurven) - 1} Stäbe -> {path}")
    return path
