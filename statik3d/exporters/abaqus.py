"""Export als Abaqus/CalculiX-Eingabedatei (.inp).

Geschrieben werden Knoten, Elemente (Balken B31, Fachwerkstab und Seil T3D2,
Schalen, Volumen, ebene Elemente), Werkstoffe (E, nu, rho, alpha),
Querschnittswerte samt Schubflaechen (*TRANSVERSE SHEAR STIFFNESS),
Stabendgelenke um die Stabachsen (*RELEASE), starre
Knotenlager samt vorgegebener Verschiebung (*BOUNDARY) und je Lastfall ein
*STEP mit Eigengewicht, Knotenlasten, gleichmaessigen Stablasten (*DLOAD
PX/PY/PZ) und Druck auf Volumenflaechen (*DLOAD Pn).

Was die Datei nicht traegt, steht nach dem Export als Hinweis mit Anzahl im
Protokoll (:func:`_common.nicht_uebertragen`; Befund B4 der Pruefagenten,
09.11.2026: bis dahin fielen Stablasten, Flaechenlasten, Gelenke und
Lagerfedern ohne ein Wort weg, und das Eigengewicht stand auf einer
Elementmenge ALL, die es in der Datei nicht gab).
"""
from __future__ import annotations

import numpy as np

from ..model import Model
from ..elements.beam3d import local_axes
from . import _common as C

#: Statik3D-Element -> Abaqus-Elementart. Die ebenen Elemente bekommen ihren
#: Namen aus dem Zustand (Scheibe CPS, ebener Dehnungszustand CPE,
#: rotationssymmetrisch CAX), siehe :func:`abq_typ`.
ABQ = {"beam": "B31", "truss": "T3D2", "seil": "T3D2",
       "shell3": "S3", "shell4": "S4", "shell6": "STRI65", "shell8": "S8R",
       "tet4": "C3D4", "tet10": "C3D10", "hex8": "C3D8", "hex20": "C3D20",
       "pent6": "C3D6", "pent15": "C3D15", "pyr5": "C3D5"}
#: Ebene Elemente: (Zustand, Knotenzahl) -> Abaqus-Name
ABQ_EBENE = {("spannung", 3): "CPS3", ("spannung", 4): "CPS4", ("spannung", 6): "CPS6",
             ("spannung", 8): "CPS8", ("dehnung", 3): "CPE3", ("dehnung", 4): "CPE4",
             ("dehnung", 6): "CPE6", ("dehnung", 8): "CPE8", ("rotation", 3): "CAX3",
             ("rotation", 4): "CAX4", ("rotation", 6): "CAX6", ("rotation", 8): "CAX8"}
#: Geloeste Drehungen eines Stabendes (lokale FHG 3, 4, 5) -> Schluessel von
#: *RELEASE. Die 1-Achse des Querschnitts ist die Achse von I11, hier die
#: lokale y-Achse (I11 = I_y), die 2-Achse die lokale z-Achse.
RELEASE = {(3,): "T", (4,): "M1", (5,): "M2", (4, 5): "M1-M2", (3, 4): "M1-T",
           (3, 5): "M2-T", (3, 4, 5): "ALLM"}
#: Volumentypen, deren Flaechendruck als Pn hinausgeht (Seitennummern wie in
#: Abaqus; der eigene Import liest ihn bei diesen)
_DRUCK_VOLUMEN = ("tet4", "tet10", "hex8")


def abq_typ(e) -> str:
    """Abaqus-Elementart eines Elements ("" = nicht exportierbar)."""
    if e.typ.startswith("ebene"):
        return ABQ_EBENE.get((getattr(e, "zustand", "spannung"), len(e.nodes)), "")
    return ABQ.get(e.typ, "")


def _z(v) -> str:
    """Zahl mit voller Genauigkeit (bis zum 09.11.2026 acht Stellen)."""
    return repr(float(v))


def write_inp(model: Model, path: str, results=None, log: list = None, **_) -> str:
    z = [f"** Statik3D-Export: {model.name}", "** Einheiten m, N, kg", "*NODE"]
    for i, p in enumerate(model.nodes, 1):
        z.append(f"{i}, {_z(p[0])}, {_z(p[1])}, {_z(p[2])}")
    gruppen: dict[tuple, list] = {}
    geschrieben = set()
    for i, e in enumerate(model.elements, 1):
        art = abq_typ(e)
        if not art:
            continue
        gruppen.setdefault((art, e.mat, e.sec or ""), []).append((i, e))
        geschrieben.add(i - 1)
    mengen = []
    for (art, mat, sec), items in gruppen.items():
        setname = f"E_{art}_{_safe(mat)}_{_safe(sec)}"
        mengen.append(setname)
        z.append(f"*ELEMENT, TYPE={art}, ELSET={setname}")
        for i, e in items:
            z.append(f"{i}, " + ", ".join(str(int(n) + 1) for n in e.nodes))
    # die Menge aller Elemente, auf der das Eigengewicht steht
    if mengen:
        z.append("*ELSET, ELSET=ALL")
        z += mengen
    # ---- Stabendgelenke ----------------------------------------------------
    n_gelenk_weg = 0
    zeilen = []
    for i, e in enumerate(model.elements, 1):
        if e.typ != "beam" or not getattr(e, "hinges", None):
            continue
        for ende in (0, 1):
            d = sorted({int(x) % 6 for x in e.hinges if int(x) // 6 == ende})
            dreh = tuple(x for x in d if x >= 3)
            if any(x < 3 for x in d):
                n_gelenk_weg += 1
            if dreh:
                zeilen.append(f"{i}, S{ende + 1}, {RELEASE[dreh]}")
    if zeilen:
        z.append("*RELEASE")
        z += zeilen
    for name, m in model.materials.items():
        z.append(f"*MATERIAL, NAME={_safe(name)}")
        z.append("*ELASTIC")
        z.append(f"{_z(m.E)}, {_z(m.nu)}")
        z.append("*DENSITY")
        z.append(f"{_z(m.rho)}")
        z.append("*EXPANSION")
        z.append(f"{_z(m.alpha)}")
    n_ohne_qs = 0
    for (art, mat, sec), items in gruppen.items():
        setname = f"E_{art}_{_safe(mat)}_{_safe(sec)}"
        if art in ("B31", "T3D2"):
            s = model.sections.get(sec)
            n_ohne_qs += s is None
            A = s.A if s else 1e-3
            if art == "T3D2":
                z.append(f"*SOLID SECTION, ELSET={setname}, MATERIAL={_safe(mat)}")
                z.append(f"{_z(A)}")
            else:
                z.append(f"*BEAM GENERAL SECTION, ELSET={setname}, "
                         f"MATERIAL={_safe(mat)}, SECTION=GENERAL")
                z.append(f"{_z(A)}, {_z(s.Iy if s else 1e-6)}, 0.0, "
                         f"{_z(s.Iz if s else 1e-6)}, {_z(s.It if s else 1e-6)}")
                z.append("0.0, 0.0, -1.0")
                m = model.materials.get(mat)
                if s is not None and m is not None and s.Asy and s.Asz:
                    # Schubsteifigkeiten K23, K13 = G * Schubflaeche; die
                    # 1-Achse ist die Achse von I11, hier die lokale y-Achse
                    z.append("*TRANSVERSE SHEAR STIFFNESS")
                    z.append(f"{_z(m.G * s.Asz)}, {_z(m.G * s.Asy)}")
        elif art.startswith("S"):
            p = model.shells.get(sec)
            z.append(f"*SHELL SECTION, ELSET={setname}, MATERIAL={_safe(mat)}")
            z.append(f"{_z(p.t if p else 0.01)}")
        else:
            z.append(f"*SOLID SECTION, ELSET={setname}, MATERIAL={_safe(mat)}")
            if art.startswith("CP") or art.startswith("CAX"):
                p = model.shells.get(sec)
                if p is not None and art.startswith("CP"):
                    z.append(f"{_z(p.t)}")
    # ---- Lager -------------------------------------------------------------
    n_federfhg = 0
    zeilen = []
    for s in model.supports:
        for d in range(6):
            b = s.dof_behaviour(d)
            if b.typ == "rigid":
                v = 0.0
                if s.values and d in s.dofs and s.dofs.index(d) < len(s.values):
                    v = float(s.values[s.dofs.index(d)] or 0.0)
                zeilen.append(f"{s.node + 1}, {d + 1}, {d + 1}, {_z(v)}")
            elif b.typ == "spring":
                n_federfhg += 1
    if zeilen:
        z.append("*BOUNDARY")
        z += zeilen
    # ---- Lastfaelle --------------------------------------------------------
    n_stablast_rest = n_flaeche_schale = n_flaeche_rest = n_lokal = 0
    for name, lc in model.load_cases.items():
        z.append(f"*STEP, NAME={_safe(name)}")
        z.append("*STATIC")
        dload = []
        if np.any(np.asarray(lc.gravity, float)):
            g = np.asarray(lc.gravity, float)
            gn = float(np.linalg.norm(g))
            dload.append(f"ALL, GRAV, {_z(gn)}, {_z(g[0] / gn)}, {_z(g[1] / gn)}, {_z(g[2] / gn)}")
        for bl in lc.beam_loads:
            i = int(bl.elem)
            e = model.elements[i] if 0 <= i < len(model.elements) else None
            q = np.asarray(bl.q, float)
            trapez = bl.q2 is not None and not np.allclose(np.asarray(bl.q2, float), q,
                                                           rtol=1e-12, atol=0.0)
            if e is None or i not in geschrieben or e.typ not in ("beam", "truss") \
                    or bl.teilweise or trapez or getattr(bl, "bezugslaenge", ""):
                n_stablast_rest += 1
                continue
            if bl.system == "local":
                n_lokal += 1
                T3, _L = local_axes(model.nodes[int(e.nodes[0])], model.nodes[int(e.nodes[1])],
                                    float(e.roll or 0.0))
                q = T3.T @ q
                q[np.abs(q) < 1e-12 * float(np.abs(q).max() or 1.0)] = 0.0
            for achse in range(3):
                if q[achse]:
                    dload.append(f"{i + 1}, P{'XYZ'[achse]}, {_z(q[achse])}")
        for fl in lc.face_loads:
            i = int(fl.elem)
            e = model.elements[i] if 0 <= i < len(model.elements) else None
            if e is not None and e.typ.startswith("shell"):
                n_flaeche_schale += 1
            elif e is None or i not in geschrieben or e.typ not in _DRUCK_VOLUMEN \
                    or fl.direction is not None:
                n_flaeche_rest += 1
            elif float(fl.p):
                dload.append(f"{i + 1}, P{int(fl.face) + 1}, {_z(fl.p)}")
        if dload:
            z.append("*DLOAD")
            z += dload
        if lc.nodal_loads:
            z.append("*CLOAD")
            for nl in lc.nodal_loads:
                for k, v in enumerate(float(x) for x in nl.F):
                    if v:
                        z.append(f"{nl.node + 1}, {k + 1}, {_z(v)}")
        z.append("*NODE FILE")
        z.append("U, RF")
        z.append("*EL FILE")
        z.append("S, E")
        z.append("*END STEP")
    with open(path, "w", encoding="ascii", errors="replace") as f:
        f.write("\n".join(z) + "\n")
    C.say(log, f"Abaqus-Eingabedatei geschrieben: {model.nn} Knoten, "
               f"{sum(len(v) for v in gruppen.values())} Elemente, "
               f"{len(model.load_cases)} Lastfälle -> {path}")
    if n_lokal:
        C.say(log, f"Abaqus: {C.anzahl(n_lokal, 'Stablast', 'Stablasten')} im Stabsystem "
                   "in globale Komponenten umgerechnet (die Datei kennt für Stablasten nur "
                   "die globalen Richtungen PX, PY, PZ).")
    if n_ohne_qs:
        C.warn(log, f"Abaqus: {C.anzahl(n_ohne_qs, 'Stabgruppe', 'Stabgruppen')} ohne "
                    "Querschnitt im Modell (mit A = 0,001 m² und I = 0,000001 m⁴ geschrieben). "
                    "Bitte im Modell ergänzen.")
    n_roll = sum(1 for e in model.elements if e.typ == "beam" and abs(float(e.roll or 0.0)) > 1e-9)
    n_seil = sum(1 for e in model.elements if e.typ == "seil")
    n_gelenkfeder = len({(i, int(x[0]) // 6) for i, e in enumerate(model.elements)
                         for x in (getattr(e, "hinge_springs", None) or [])})
    benutzt = {k[2] for k in gruppen if k[0] in ("B31", "T3D2")}
    n_form = sum(1 for n, s in model.sections.items()
                 if n in benutzt and (s.typ != "free" or getattr(s, "parts", None)))
    n_schub = sum(1 for n, s in model.sections.items()
                  if n in benutzt and bool(s.Asy) != bool(s.Asz))
    n_fest = sum(1 for m in model.materials.values()
                 if getattr(m, "fy", None) or getattr(m, "fu", None))
    n_plast = sum(1 for m in model.materials.values()
                  if getattr(m, "verfestigung", None) is not None
                  or getattr(m, "Ep", None) is not None)
    n_lager_nl = sum(1 for s in model.supports if s.nonlinear)
    n_kat = sum(1 for k, lc in enumerate(model.load_cases.values())
                if lc.category != ("G" if k == 0 else "Q"))
    C.nicht_uebertragen(log, "Abaqus", [
        (n_seil, "Seil (geht als Fachwerkstab T3D2 hinaus)",
         "Seile (gehen als Fachwerkstäbe T3D2 hinaus)"),
        (n_roll, "Stabverdrehung um die Stabachse", "Stabverdrehungen um die Stabachse"),
        (n_gelenk_weg, "Stabende mit Verschiebungsgelenk (Normalkraft- oder Querkraftgelenk)",
         "Stabenden mit Verschiebungsgelenk (Normalkraft- oder Querkraftgelenk)"),
        (n_gelenkfeder, "Stabende mit Gelenkfeder", "Stabenden mit Gelenkfeder"),
        (n_form, "Querschnittsform mit Maßen (es stehen Fläche und Trägheitsmomente in "
                 "der Datei)",
         "Querschnittsformen mit Maßen (es stehen Fläche und Trägheitsmomente in der Datei)"),
        (n_schub, "Querschnitt mit Schubfläche in nur einer Richtung (der Stab kommt "
                  "schubstarr an)",
         "Querschnitte mit Schubfläche in nur einer Richtung (die Stäbe kommen schubstarr "
         "an)"),
        (sum(1 for n in model.sections if n not in benutzt),
         "Querschnitt, den kein Stab benutzt", "Querschnitte, die kein Stab benutzt"),
        (n_fest, "Werkstoff mit Streckgrenze oder Zugfestigkeit (es stehen E, ν, ρ und α in "
                 "der Datei)",
         "Werkstoffe mit Streckgrenze oder Zugfestigkeit (es stehen E, ν, ρ und α in der "
         "Datei)"),
        (n_plast, "Werkstoffgesetz mit Verfestigung", "Werkstoffgesetze mit Verfestigung"),
        (n_federfhg, "gefederter Freiheitsgrad eines Knotenlagers (er bleibt in der Datei "
                     "frei)",
         "gefederte Freiheitsgrade von Knotenlagern (sie bleiben in der Datei frei)"),
        (n_lager_nl, "Knotenlager mit Ausfall, Schlupf, Reibung oder Grenzkraft (es geht "
                     "als beidseitig wirkendes Lager hinaus)",
         "Knotenlager mit Ausfall, Schlupf, Reibung oder Grenzkraft (sie gehen als "
         "beidseitig wirkende Lager hinaus)"),
        (len(model.line_supports), "Linienlager", "Linienlager"),
        (len(model.surface_supports), "Flächenlager", "Flächenlager"),
        (n_stablast_rest, "Stablast (trapezförmig, auf einem Teilstück, auf die Projektion "
                          "bezogen oder auf einem Seil)",
         "Stablasten (trapezförmig, auf einem Teilstück, auf die Projektion bezogen oder "
         "auf einem Seil)"),
        (n_flaeche_schale, "Flächenlast auf einem Schalenelement",
         "Flächenlasten auf Schalenelementen"),
        (n_flaeche_rest, "Flächenlast auf einem Volumenelement (mit eigener Richtung, auf "
                         "Hexaedern mit Seitenmittenknoten, Prismen oder Pyramiden)",
         "Flächenlasten auf Volumenelementen (mit eigener Richtung, auf Hexaedern mit "
         "Seitenmittenknoten, Prismen oder Pyramiden)"),
        (C.lastzahl(model, "temp_loads"), "Temperaturlast", "Temperaturlasten"),
        (n_kat, "Lastfallkategorie (der eigene Import setzt „G“ für den ersten und „Q“ für "
                "jeden weiteren Lastfall)",
         "Lastfallkategorien (der eigene Import setzt „G“ für den ersten und „Q“ für jeden "
         "weiteren Lastfall)"),
        (len(model.combinations), "Kombination", "Kombinationen"),
    ] + C.weiteres(model))
    return path


def _safe(t: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in str(t))[:60] or "X"
