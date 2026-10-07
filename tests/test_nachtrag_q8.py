"""
Nachtrag zur Fehlerliste (06.10.2026), Paket Q8, Eintraege N25 bis N30:
der SAF-Rundlauf.

Ein Modell, das Statik3D als SAF schreibt und wieder liest, soll dasselbe
Modell sein. Verglichen wird wie in tests.test_fehler_p13 **nach der
Geometrie**, nicht nach Nummern: Knotenlasten am Ort des Knotens, Stablasten an
Messpunkten entlang der Stabelemente, Flaechen- und Temperaturlasten,
Werkstoff, Querschnitt und lokale Achsen am Mittelpunkt jedes Elements.

Ausgangsstand 3f7b670 (gemessen am 07.10.2026):

* N25 - der Export schrieb Knotenlasten als Spalten Fx ... Mz ohne Direction
  und Value; der Import uebersprang jede Zeile mit "Richtung '' unbekannt",
  der Export sagte nichts. Frame, truss, hall, contact, solid und friction
  verloren alle Knotenlasten.
* N26 - E-Modul und freie Querschnittswerte gingen in SI ohne Einheit hinaus;
  der Import las E als MPa (2,1e17 Pa) und A als mm² (6e-8 statt 0,06 m²).
* N27 - die Datei fuehrt einen Stab vom kleineren zum groesseren Endknoten
  (nach Koordinaten); die Rollung eines rueckwaerts gezeichneten Stabes ging
  unveraendert hinaus, zurueck kam er um 2θ verdreht (0,5 rad -> 57,3°).
* N28 - Eigengewicht und Temperaturlast fehlten in der Datei ohne Zeile im
  Protokoll; ebenso Flaechenlasten und die Felder Situation, Theorie und
  Leiteinwirkung (hier nachgewiesen).
* N29 - der Import in ein frisches Modell nannte "LF1" der Datei "LF1_2",
  weil der leere Vorgabelastfall LF1 noch stand; die Kombinationen zeigten
  auf LF1_2.
* N30 - ein Stab aus mehreren Elementen kam als ein Element zurueck (die
  Datei nannte nur Anfangs- und Endknoten).

Aufruf:  python -m tests.test_nachtrag_q8
"""
import os
import sys
import tempfile
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section, ShellProp  # noqa: E402
from statik3d.exporters import export_model  # noqa: E402
from statik3d.importers import import_file  # noqa: E402
from statik3d.importers.xlsx_reader import read_table_file  # noqa: E402
from statik3d.elements import beam3d as bm  # noqa: E402
from statik3d import elemente as EL  # noqa: E402
from statik3d.examples_lib import EXAMPLES, build_example  # noqa: E402
from tests.test_fehler_p13 import lastbild_in  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Rundlauf und Vergleich nach Geometrie
# --------------------------------------------------------------------------
def rundlauf(m: Model, name: str = "m.xlsx"):
    """Export -> Import in ein frisches Modell. Rueckgabe (m2, Exportprotokoll,
    Importprotokoll, Blaetter der Datei)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, name)
        elog: list = []
        export_model(m, p, log=elog)
        tab = read_table_file(p)
        ilog: list = []
        m2 = import_file(p, log=ilog)
    return m2, elog, ilog, tab


def warnungen(log) -> list:
    return [z for z in log if "WARNUNG" in z]


def _ort(x) -> tuple:
    return tuple(float(v) for v in np.round(np.asarray(x, float), 6))


def _mitte(m: Model, i: int) -> tuple:
    e = m.elements[i]
    if e.typ in EL.STAB_TYPEN:
        return _ort(m.nodes[[int(n) for n in e.nodes[:2]]].mean(axis=0))
    return _ort(m.nodes[[int(n) for n in e.nodes]].mean(axis=0))


def _nach_ort(m: Model) -> dict:
    return {_mitte(m, i): i for i in range(len(m.elements))}


def _normale(m: Model, i: int) -> np.ndarray:
    X = m.nodes[[int(n) for n in m.elements[i].nodes]]
    n = np.cross(X[1] - X[0], X[2] - X[0]) if len(X) == 3 else np.cross(X[2] - X[0], X[3] - X[1])
    return n / np.linalg.norm(n)


def _achsen(m: Model, i: int) -> np.ndarray:
    e = m.elements[i]
    X = m.nodes[[int(n) for n in e.nodes[:2]]]
    return bm.local_axes(X[0], X[1], e.roll)[0]


def _gleich(a, b, rel=1e-9) -> bool:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return bool(np.all(np.abs(a - b) <= rel * np.maximum(1.0, np.maximum(np.abs(a), np.abs(b)))))


def _knotenlasten(m: Model, fall: str) -> dict:
    out: dict = defaultdict(lambda: np.zeros(6))
    for nl in m.load_cases[fall].nodal_loads:
        out[_ort(m.nodes[int(nl.node)])] += np.asarray(nl.F, float)
    return out


def _flaechenlasten(m: Model, fall: str) -> dict:
    """Je Schalenelement (Mittelpunkt) die Flaechenlast als Vektor [N/m²]."""
    out: dict = defaultdict(lambda: np.zeros(3))
    for fl in m.load_cases[fall].face_loads:
        i = int(fl.elem)
        if not m.elements[i].typ.startswith("shell"):
            continue
        d = (_normale(m, i) if fl.direction is None
             else np.asarray(fl.direction, float) / np.linalg.norm(fl.direction))
        out[_mitte(m, i)] += float(fl.p) * d
    return out


def _temperaturen(m: Model, fall: str) -> dict:
    """Je Stab- und Schalenelement (Mittelpunkt): (dT, dT_z mal Richtung der
    lokalen z-Achse bzw. der Normale) - so ist der Vergleich unabhaengig davon,
    in welche Richtung das Element gezeichnet ist."""
    out: dict = defaultdict(lambda: np.zeros(4))
    for tl in m.load_cases[fall].temp_loads:
        i = int(tl.elem)
        e = m.elements[i]
        if e.typ in EL.STAB_TYPEN:
            z = _achsen(m, i)[2]
        elif e.typ.startswith("shell"):
            z = _normale(m, i)
        else:
            continue
        out[_mitte(m, i)] += np.concatenate([[float(tl.dT)], float(tl.dT_z) * z])
    return out


def abweichungen(m1: Model, m2: Model) -> dict:
    """Was am zurueckgelesenen Modell m2 anders ist als an m1 - je Art eine
    Liste von Klartextzeilen (leer = gleich)."""
    aus: dict = defaultdict(list)
    # --- Lastfaelle (Namen, N29) ---
    if set(m1.load_cases) != set(m2.load_cases):
        aus["Lastfälle"].append(f"{sorted(m1.load_cases)} -> {sorted(m2.load_cases)}")
    faelle = [f for f in m1.load_cases if f in m2.load_cases]
    # --- Elemente: Art, Werkstoff, Querschnitt, Achsen ---
    ort2 = _nach_ort(m2)
    n_stab1 = sum(1 for e in m1.elements if e.typ in EL.STAB_TYPEN)
    n_stab2 = sum(1 for e in m2.elements if e.typ in EL.STAB_TYPEN)
    if n_stab1 != n_stab2:
        aus["Elemente"].append(f"{n_stab1} Stabelemente -> {n_stab2}")
    n_sch1 = sum(1 for e in m1.elements if e.typ.startswith("shell"))
    n_sch2 = sum(1 for e in m2.elements if e.typ.startswith("shell"))
    if n_sch1 != n_sch2:
        aus["Elemente"].append(f"{n_sch1} Schalenelemente -> {n_sch2}")
    for i, e in enumerate(m1.elements):
        if not (e.typ in EL.STAB_TYPEN or e.typ.startswith("shell")):
            continue
        j = ort2.get(_mitte(m1, i))
        if j is None:
            aus["Elemente"].append(f"Element {i + 1} ({e.typ}) bei {_mitte(m1, i)} fehlt")
            continue
        e2 = m2.elements[j]
        w1, w2 = m1.materials[e.mat], m2.materials[e2.mat]
        for feld in ("E", "nu", "rho", "alpha"):
            if not _gleich(getattr(w1, feld), getattr(w2, feld)):
                aus["Werkstoff"].append(f"Element {i + 1}: {feld} {getattr(w1, feld):.6g} -> "
                                        f"{getattr(w2, feld):.6g}")
        if not _gleich(w1.yield_strength(0.0), w2.yield_strength(0.0)):
            aus["Werkstoff"].append(f"Element {i + 1}: f_y {w1.yield_strength(0.0):.6g} -> "
                                    f"{w2.yield_strength(0.0):.6g}")
        if e.typ in EL.STAB_TYPEN:
            s1, s2 = m1.sections[e.sec], m2.sections[e2.sec]
            for feld in ("A", "Iy", "Iz", "It", "Iw", "Asy", "Asz", "h"):
                if not _gleich(getattr(s1, feld), getattr(s2, feld)):
                    aus["Querschnitt"].append(f"Element {i + 1} ({e.sec}): {feld} "
                                              f"{getattr(s1, feld):.6g} -> {getattr(s2, feld):.6g}")
            if e.typ == "beam" and e2.typ == "beam":
                z1, z2 = _achsen(m1, i)[2], _achsen(m2, j)[2]
                if float(z1 @ z2) < 1.0 - 1e-9:
                    w = np.degrees(np.arccos(max(-1.0, min(1.0, float(z1 @ z2)))))
                    aus["Achsen"].append(f"Element {i + 1}: lokale z-Achse um {w:.3f}° gedreht")
        else:
            t1, t2 = m1.shells[e.sec].t, m2.shells[e2.sec].t
            if not _gleich(t1, t2):
                aus["Querschnitt"].append(f"Schale {i + 1}: t {t1:.6g} -> {t2:.6g}")
    # --- Lasten je Lastfall ---
    for f in faelle:
        lc1, lc2 = m1.load_cases[f], m2.load_cases[f]
        if not _gleich(np.asarray(lc1.gravity, float), np.asarray(lc2.gravity, float)):
            aus["Eigengewicht"].append(f"{f}: g {list(lc1.gravity)} -> {list(lc2.gravity)}")
        k1, k2 = _knotenlasten(m1, f), _knotenlasten(m2, f)
        for o in set(k1) | set(k2):
            if not _gleich(k1.get(o, np.zeros(6)), k2.get(o, np.zeros(6))):
                aus["Knotenlasten"].append(f"{f} bei {o}: {k1.get(o, np.zeros(6)).tolist()} -> "
                                           f"{k2.get(o, np.zeros(6)).tolist()}")
        worst = gross = 0.0
        for i, e in enumerate(m1.elements):
            if e.typ not in EL.STAB_TYPEN:
                continue
            X = m1.nodes[[int(n) for n in e.nodes[:2]]]
            for t in (0.07, 0.31, 0.5, 0.77, 0.93):
                p = X[0] + t * (X[1] - X[0])
                q1, q2 = lastbild_in(m1, f, p), lastbild_in(m2, f, p)
                worst = max(worst, float(np.max(np.abs(q1 - q2))))
                gross = max(gross, float(np.max(np.abs(q1))))
        if worst > 1e-9 * max(gross, 1.0):
            aus["Stablasten"].append(f"{f}: größte Abweichung {worst:.6g} N/m bei {gross:.6g} N/m")
        a1, a2 = _flaechenlasten(m1, f), _flaechenlasten(m2, f)
        for o in set(a1) | set(a2):
            if not _gleich(a1.get(o, np.zeros(3)), a2.get(o, np.zeros(3))):
                aus["Flächenlasten"].append(f"{f} bei {o}: {a1.get(o, np.zeros(3)).tolist()} -> "
                                            f"{a2.get(o, np.zeros(3)).tolist()}")
        t1, t2 = _temperaturen(m1, f), _temperaturen(m2, f)
        for o in set(t1) | set(t2):
            if not _gleich(t1.get(o, np.zeros(4)), t2.get(o, np.zeros(4))):
                aus["Temperatur"].append(f"{f} bei {o}: {t1.get(o, np.zeros(4)).tolist()} -> "
                                         f"{t2.get(o, np.zeros(4)).tolist()}")
    # --- Kombinationen ---
    for n, c in m1.combinations.items():
        c2 = m2.combinations.get(n)
        if c2 is None:
            aus["Kombinationen"].append(f"{n} fehlt")
            continue
        if c.factors != c2.factors or [dict(a) for a in c.alternativen] != [dict(a) for a in c2.alternativen]:
            aus["Kombinationen"].append(f"{n}: {c.factors}/{c.alternativen} -> {c2.factors}/{c2.alternativen}")
    return aus


def _kurz(aus: dict, art: str) -> str:
    z = aus.get(art) or []
    return f"{len(z)}: " + "; ".join(z[:2])[:160] if z else ""


# --------------------------------------------------------------------------
# N25 Knotenlasten
# --------------------------------------------------------------------------
def _modell_knotenlasten() -> Model:
    m = Model("N25")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 300"))
    n = [m.add_node(*p) for p in ((0, 0, 0), (5, 0, 0), (5, 3, 0), (5, 3, 4))]
    for a, b in ((0, 1), (1, 2), (2, 3)):
        m.add_element("beam", [n[a], n[b]], "S355", "IPE 300")
    m.fix(n[0], "all")
    m.case("LF1").description = "ständig"
    m.load_node(n[1], Fz=-40e3)                                       # eine Komponente
    m.load_node(n[2], Fx=12e3, Fy=-3.5e3, Fz=-7e3, Mx=1.5e3, My=-2e3, Mz=4.25e3)   # alle sechs
    m.load_node(n[2], Fz=-1e3)                                        # zweite Last am selben Knoten
    m.add_load_case("LF2", "Q", "Nutzlast", activate=False)
    m.load_node(n[3], My=8e3, case="LF2")                             # nur ein Moment
    return m


def test_n25_knotenlasten():
    m = _modell_knotenlasten()
    m2, elog, ilog, tab = rundlauf(m)
    aus = abweichungen(m, m2)
    check("N25: Knotenlasten (Kraefte und Momente, mehrere je Knoten) kommen gleich zurueck",
          not aus.get("Knotenlasten"), _kurz(aus, "Knotenlasten"))
    check("N25: Import ohne Warnung", not warnungen(ilog), "; ".join(warnungen(ilog))[:160])
    kopf = [str(c) for c in (tab.get("StructuralPointAction") or [[]])[0]]
    check("N25: Blatt StructuralPointAction nach SAF (Direction, Value [kN], Reference node)",
          all(s in kopf for s in ("Direction", "Value [kN]", "Reference node", "Force action")), str(kopf))
    kopf = [str(c) for c in (tab.get("StructuralPointMoment") or [[]])[0]]
    check("N25: Momente im Blatt StructuralPointMoment (Value [kNm])",
          all(s in kopf for s in ("Direction", "Value [kNm]", "Reference node")), str(kopf))


# --------------------------------------------------------------------------
# N26 Einheiten
# --------------------------------------------------------------------------
def _modell_einheiten() -> Model:
    m = Model("N26")
    w = Material("Stahl frei", 205e9, 0.28, 7800.0, 1.1e-5, fy=320e6, fu=470e6)
    m.add_material(w)
    m.add_section(Section.rectangle("R", 0.2, 0.3))
    m.add_section(Section("Frei", A=0.0123, Iy=3.4e-4, Iz=5.6e-5, It=7.8e-6, Iw=1.2e-7))
    m.add_section(Section.from_profile("IPE 400"))
    n = [m.add_node(*p) for p in ((0, 0, 0), (4, 0, 0), (8, 0, 0), (12, 0, 0))]
    m.add_element("beam", [n[0], n[1]], "Stahl frei", "R")
    m.add_element("beam", [n[1], n[2]], "Stahl frei", "Frei")
    m.add_element("beam", [n[2], n[3]], "Stahl frei", "IPE 400")
    m.fix(n[0], "all")
    return m


def test_n26_einheiten():
    m = _modell_einheiten()
    m2, elog, ilog, tab = rundlauf(m)
    aus = abweichungen(m, m2)
    check("N26: Werkstoff (E, nu, rho, alpha, f_y) kommt gleich zurueck", not aus.get("Werkstoff"),
          _kurz(aus, "Werkstoff"))
    check("N26: Querschnitte (Rechteck, freie Werte, Datenbankprofil) kommen gleich zurueck",
          not aus.get("Querschnitt"), _kurz(aus, "Querschnitt"))
    mk = [str(c) for c in (tab.get("StructuralMaterial") or [[]])[0]]
    qk = [str(c) for c in (tab.get("StructuralCrossSection") or [[]])[0]]
    check("N26: Kopfzeile Werkstoff mit den Einheiten der SAF-Beschreibung",
          all(s in mk for s in ("E modulus [MPa]", "G modulus [MPa]", "Unit mass [kg/m3]",
                                "Thermal expansion [1/K]")), str(mk))
    check("N26: Kopfzeile Querschnitt mit den Einheiten der SAF-Beschreibung",
          all(s in qk for s in ("A [m2]", "Iy [m4]", "Iz [m4]", "It [m4]", "Iw [m6]")), str(qk))
    w2 = next(iter(m2.materials.values()))
    check("N26: E-Modul 205 000 MPa kommt als 2,05e11 Pa zurueck (nicht 2,05e17)",
          abs(w2.E - 205e9) < 1.0, f"{w2.E:.6g}")
    check("N26: f_u 470 MPa ueber 'Design properties' zurueck", abs(w2.ultimate_strength(0.0) - 470e6) < 1.0,
          f"{w2.ultimate_strength(0.0):.6g}")


# --------------------------------------------------------------------------
# N27 Rollung rueckwaerts gefuehrter Staebe
# --------------------------------------------------------------------------
def _modell_rollung() -> Model:
    m = Model("N27")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    a, b = m.add_node(0, 0, 0), m.add_node(0, 0, -4)          # nach unten gezeichnet
    c, d = m.add_node(5, 2, 1), m.add_node(1, 1, 1)           # schraeg, gegen die Ordnung der Datei
    e, f, g = m.add_node(9, 0, 0), m.add_node(9, 0, 3), m.add_node(9, 0, 6)
    m.add_element("beam", [a, b], "S355", "IPE 400", roll=0.5)
    m.add_element("beam", [c, d], "S355", "IPE 400", roll=-1.1)
    e1 = m.add_element("beam", [g, f], "S355", "IPE 400", roll=0.7)   # Stab aus zwei Elementen,
    e2 = m.add_element("beam", [f, e], "S355", "IPE 400", roll=0.7)   # beide rueckwaerts
    m.add_member("S3", [e1, e2])
    m.fix(a, "all")
    m.load_beam(e1, qy=2e3, system="local")
    m.load_beam(e2, qz=-3e3, q2=[0.0, 1e3, -5e3], system="local")
    return m


def test_n27_rollung():
    m = _modell_rollung()
    m2, elog, ilog, tab = rundlauf(m)
    aus = abweichungen(m, m2)
    check("N27: lokale Achsen rueckwaerts gefuehrter Staebe kommen gleich zurueck (auch Stab aus zwei Elementen)",
          not aus.get("Achsen"), _kurz(aus, "Achsen"))
    check("N27: lokale Stablasten an diesen Staeben: gleiches Lastbild", not aus.get("Stablasten"),
          _kurz(aus, "Stablasten"))
    check("N27: Export ohne Warnung (gleiche Rollung je Stab ist darstellbar)", not warnungen(elog),
          "; ".join(warnungen(elog))[:160])


def test_n27_verschiedene_rollung_gemeldet():
    """Ein Stab, dessen Elemente verschieden gerollt sind: SAF fuehrt eine Rollung
    je Stab - das Protokoll nennt den Stab, statt still eine zu nehmen."""
    m = Model("N27b")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    n = [m.add_node(x, 0, 0) for x in (0, 3, 6)]
    e0 = m.add_element("beam", [n[0], n[1]], "S355", "IPE 400", roll=0.0)
    e1 = m.add_element("beam", [n[1], n[2]], "S355", "IPE 400", roll=0.3)
    m.add_member("S1", [e0, e1])
    m.fix(n[0], "all")
    _m2, elog, _ilog, _tab = rundlauf(m)
    nennt = [z for z in warnungen(elog) if "S1" in z and "Rollung" in z]
    check("N27: verschieden gerollte Elemente eines Stabes: WARNUNG nennt Stab und Rollung", bool(nennt),
          "; ".join(elog)[:200])


# --------------------------------------------------------------------------
# N28 Eigengewicht, Temperatur, Flaechenlasten, Felder ohne SAF-Gegenstueck
# --------------------------------------------------------------------------
def _modell_lasten() -> Model:
    m = Model("N28")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 300"))
    m.add_shell_prop(ShellProp("t = 10 mm", 0.010))
    n = [m.add_node(*p) for p in ((0, 0, 0), (3, 0, 0), (6, 0, 0), (0, 0, 3), (3, 0, 3), (0, 2, 3), (3, 2, 3))]
    e0 = m.add_element("beam", [n[0], n[1]], "S355", "IPE 300", roll=0.2)
    e1 = m.add_element("beam", [n[2], n[1]], "S355", "IPE 300")          # rueckwaerts
    e2 = m.add_element("truss", [n[1], n[4]], "S355", "IPE 300")
    s0 = m.add_element("shell4", [n[3], n[4], n[6], n[5]], "S355", "t = 10 mm")
    m.add_member("S1", [e0])
    m.fix(n[0], "all")
    m.fix(n[2], "all")
    lf1 = m.case("LF1")
    lf1.description = "Eigengewicht"
    m.set_gravity(-9.81, "LF1")
    m.add_load_case("LF2", "T", "Temperatur", activate=False)
    m.load_temp(e0, 25.0, 8.0, case="LF2")
    m.load_temp(e1, -10.0, 4.0, case="LF2")
    m.load_temp(e2, 15.0, case="LF2")
    m.load_temp(s0, 20.0, case="LF2")
    m.add_load_case("LF3", "Q", "Flächenlast", activate=False)
    m.load_face(s0, -2.5e3, case="LF3")                                 # normal (lokal z)
    m.load_face(s0, 1.2e3, case="LF3", direction=(0, 1, 0))             # global
    m.load_face(s0, 0.8e3, case="LF3", direction=(1.0, 0.0, -1.0))      # schraeg: in Komponenten
    m.add_combination("K1", {"LF1": 1.35, "LF3": 1.5}, typ="ULS")
    return m


def test_n28_lasten_rundlauf():
    m = _modell_lasten()
    m2, elog, ilog, tab = rundlauf(m)
    aus = abweichungen(m, m2)
    # nach der Beschreibung gesucht, nicht nach dem Namen: im Ausgangsstand hiess
    # LF1 nach dem Import LF1_2 (N29), der Vergleich nach Namen saehe ihn nicht
    eg = [lc for lc in m2.load_cases.values() if lc.description == "Eigengewicht"]
    check("N28: Eigengewicht kommt zurueck (Load type Self weight)",
          not aus.get("Eigengewicht") and len(eg) == 1 and _gleich(eg[0].gravity, [0.0, 0.0, -9.81]),
          _kurz(aus, "Eigengewicht") + (f" g = {list(eg[0].gravity)}" if eg else " kein Lastfall"))
    check("N28: Temperaturlasten (Stab gleichmaessig und mit Unterschied, Fachwerkstab, Schale) gleich",
          not aus.get("Temperatur"), _kurz(aus, "Temperatur"))
    check("N28: Flaechenlasten (normal, global, schraeg) gleich", not aus.get("Flächenlasten"),
          _kurz(aus, "Flächenlasten"))
    check("N28: Import ohne Warnung", not warnungen(ilog), "; ".join(warnungen(ilog))[:160])
    check("N28: Export ohne Warnung (alles ist darstellbar)", not warnungen(elog),
          "; ".join(warnungen(elog))[:160])


def test_n28_nicht_darstellbares_gemeldet():
    """Was SAF nicht kennt, steht als WARNUNG im Protokoll des Exports."""
    m = _modell_lasten()
    m.load_cases["LF1"].gravity = [0.0, 0.0, -9.81 * 1.1]              # nicht die Erdbeschleunigung
    m.load_cases["LF2"].situation = "Bauzustand"
    m.load_cases["LF2"].theorie = "II"
    c = m.combinations["K1"]
    c.situation, c.theorie, c.leading = "Bauzustand", "II", "LF3"
    from statik3d.model import Zwangsverformung
    m.load_cases["LF3"].zwangsverformungen.append(Zwangsverformung(0, [2], [0.0, 0.0, -0.01, 0, 0, 0]))
    _m2, elog, _ilog, _tab = rundlauf(m)
    w = warnungen(elog)
    check("N28: Eigengewicht mit g ≠ 9,81 m/s² in -Z: WARNUNG nennt Lastfall", any("LF1" in z and "Eigengewicht" in z
                                                                                 for z in w), "; ".join(w)[:200])
    check("N28: Situation und Theorie eines Lastfalls: WARNUNG", any("LF2" in z and "Situation" in z and "Theorie" in z
                                                                  for z in w), "; ".join(w)[:200])
    check("N28: Situation, Theorie und Leiteinwirkung einer Kombination: WARNUNG",
          any("K1" in z and "Situation" in z and "Theorie" in z and "Leiteinwirkung" in z for z in w),
          "; ".join(w)[:200])
    check("N28: Zwangsverformung: WARNUNG nennt Lastfall und Lastart",
          any("LF3" in z and "Zwangsverformung" in z for z in w), "; ".join(w)[:200])


def test_n28_volumen_gemeldet():
    """Temperatur- und Flaechenlasten auf Volumenelementen kennt SAF nicht."""
    m = build_example("solid")
    m.load_temp(0, 10.0)
    m.load_face(0, 1e3, face=1)
    _m2, elog, _ilog, _tab = rundlauf(m)
    w = warnungen(elog)
    check("N28: Temperatur- und Flaechenlast auf Volumenelement: WARNUNG",
          any("Temperatur" in z for z in w) and any("Flächenlast" in z for z in w), "; ".join(w)[:200])


# --------------------------------------------------------------------------
# N29 LF1 im frischen Modell
# --------------------------------------------------------------------------
def test_n29_lf1_bleibt():
    m = _modell_knotenlasten()
    m.add_combination("K1", {"LF1": 1.35, "LF2": 1.5}, typ="ULS")
    m2, _elog, ilog, _tab = rundlauf(m)
    check("N29: Import in ein frisches Modell: die Lastfaelle heissen wie in der Datei (LF1, nicht LF1_2)",
          sorted(m2.load_cases) == ["LF1", "LF2"], str(sorted(m2.load_cases)))
    k1 = m2.combinations.get("K1")
    check("N29: Kombination zeigt auf LF1 und LF2", k1 is not None and k1.factors == {"LF1": 1.35, "LF2": 1.5},
          str(k1.factors if k1 else None))
    check("N29: LF1 traegt die Beschreibung und Lasten der Datei",
          m2.load_cases["LF1"].description == "ständig" and len(m2.load_cases["LF1"].nodal_loads) >= 2
          if "LF1" in m2.load_cases else False,
          str(m2.load_cases.get("LF1")) [:120])
    # Gegenstueck: Anhaengen an ein Modell, dessen LF1 Lasten traegt - dann
    # bleibt dessen LF1, der Lastfall der Datei bekommt einen eigenen Namen
    ziel = _modell_einheiten()
    ziel.load_node(1, Fz=-5e3)
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "a.xlsx")
        export_model(m, p, log=[])
        import_file(p, model=ziel, log=[])
    check("N29: Anhaengen an ein Modell mit belegtem LF1: dessen LF1 bleibt unberuehrt",
          len(ziel.load_cases["LF1"].nodal_loads) == 1 and "LF1_2" in ziel.load_cases,
          str(sorted(ziel.load_cases)))
    # Anhaengen an ein neues, leeres Modell (Oberflaeche: Neu, dann Import mit
    # "Anhängen"): wie ein frisches - der leere LF1 weicht dem der Datei
    leer = Model("leer")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "a.xlsx")
        export_model(m, p, log=[])
        import_file(p, model=leer, log=[])
    check("N29: Anhaengen an ein leeres Modell: LF1 der Datei ersetzt den leeren Vorgabelastfall",
          sorted(leer.load_cases) == ["LF1", "LF2"] and len(leer.load_cases["LF1"].nodal_loads) >= 2,
          str(sorted(leer.load_cases)))


# --------------------------------------------------------------------------
# Dateien, die Statik3D vor dem 07.10.2026 schrieb
# --------------------------------------------------------------------------
def test_alte_datei():
    """Die Blaetter, wie sie der Export bis zum 07.10.2026 schrieb (Ausgangsstand
    3f7b670, mit dessen write_saf erzeugt und hier abgeschrieben): Werte in SI
    ohne Einheit, Knotenlasten als Spalten Fx ... Mz. Der Import erkennt die
    Datei an der Spalte "Yield strength" und liest sie in SI."""
    from statik3d.importers.xlsx_reader import write_xlsx
    blaetter = {
        "StructuralPointConnection": [["Name", "Coordinate X", "Coordinate Y", "Coordinate Z"],
                                      ["N1", 0.0, 0.0, 0.0], ["N2", 3.0, 0.0, 0.0],
                                      ["N3", 3.0, 2.0, 0.0], ["N4", 0.0, 2.0, 0.0]],
        "StructuralMaterial": [["Name", "Material type", "Quality", "Unit mass", "E modulus",
                                "Poisson coefficient", "G modulus", "Thermal expansion", "Yield strength",
                                "Ultimate strength"],
                               ["Stahl", "Steel", "Stahl", 7850.0, 205000000000.0, 0.3, 78846153846.15384,
                                1.2e-05, 320000000.0, 0.0]],
        "StructuralCrossSection": [["Name", "Material", "Form code", "A", "I y", "I z", "I t", "Height",
                                    "Width", "Web thickness", "Flange thickness"],
                                   ["R", "Stahl", "rect", 0.06, 0.00045, 0.0002, 0.0004695308641975309,
                                    0.3, 0.2, 0.0, 0.0]],
        "StructuralCurveMember": [["Name", "Cross-section", "Material", "Begin node", "End node", "Rotation",
                                   "Length", "Type"],
                                  ["E1", "R", "Stahl", "N1", "N2", 0.0, 3.0, "Beam"]],
        "StructuralSurfaceMember": [["Name", "Material", "Thickness", "Nodes", "Type"],
                                    ["S2", "Stahl", 0.012, "N1;N2;N3;N4", "Plate"]],
        "StructuralLoadCase": [["Name", "Load group", "Load type", "Action type", "Description"],
                               ["LF1", "G", "Static", "G", ""]],
        "StructuralPointAction": [["Name", "Load case", "Node", "Fx", "Fy", "Fz", "Mx", "My", "Mz"],
                                  ["F1", "LF1", "N2", 0.0, 0.0, -4000.0, 0.0, 2000.0, 0.0]],
    }
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "alt.xlsx")
        write_xlsx(p, blaetter)
        lg = []
        m = import_file(p, log=lg)
    w = m.materials.get("Stahl")
    check("alte Datei: E 2,05e11 Pa (nicht 2,05e17), f_y 320 MPa", w is not None and abs(w.E - 205e9) < 1.0
          and abs((w.fy or 0) - 320e6) < 1.0, f"{w.E if w else None:.6g}" if w else "kein Werkstoff")
    s = m.sections.get("R")
    check("alte Datei: A 0,06 m², Iy 4,5e-4 m⁴ (nicht als mm² und mm⁴)", s is not None
          and abs(s.A - 0.06) < 1e-12 and abs(s.Iy - 4.5e-4) < 1e-15, f"{s.A:.6g} / {s.Iy:.6g}" if s else "")
    t = [sp.t for sp in m.shells.values()]
    check("alte Datei: Dicke 12 mm (nicht 0,012 mm)", t and abs(t[0] - 0.012) < 1e-12, str(t))
    lasten = [l.F for lc in m.load_cases.values() for l in lc.nodal_loads]
    check("alte Datei: Knotenlast Fz -4 kN und My 2 kNm", lasten == [[0.0, 0.0, -4000.0, 0.0, 2000.0, 0.0]],
          str(lasten))
    check("alte Datei: das Protokoll sagt, wie sie gelesen wurde", any("vor dem 07.10.2026" in z for z in lg),
          "; ".join(lg)[:160])


# --------------------------------------------------------------------------
# N30 Stab aus mehreren Elementen
# --------------------------------------------------------------------------
def test_n30_mehrere_elemente():
    m = Model("N30")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    n = [m.add_node(*p) for p in ((0, 0, 0), (2, 0, 0), (3.5, 0, 0), (6, 0, 0),
                                  (6, 0, 2), (6, 1, 4))]       # gerade, dann geknickt
    el = [m.add_element("beam", [n[k], n[k + 1]], "S355", "HEB 200") for k in range(3)]
    m.add_member("Riegel", el)
    k1 = m.add_element("beam", [n[3], n[4]], "S355", "HEB 200")
    k2 = m.add_element("beam", [n[5], n[4]], "S355", "HEB 200")      # rueckwaerts im Polygonzug
    m.add_member("Knick", [k1, k2])
    m.fix(n[0], "all")
    m.load_node(n[2], Fz=-10e3)                 # Last am Zwischenknoten
    m2, elog, ilog, tab = rundlauf(m)
    aus = abweichungen(m, m2)
    check("N30: alle Zwischenknoten und Elemente kommen zurueck (gerader und geknickter Stab)",
          not aus.get("Elemente") and m2.nn == m.nn, f"{m2.nn} Knoten; " + _kurz(aus, "Elemente"))
    check("N30: Stabnamen mit derselben Zahl Elemente",
          {k: len(v.elements) for k, v in m2.members.items()} == {"Riegel": 3, "Knick": 2},
          str({k: len(v.elements) for k, v in m2.members.items()}))
    check("N30: Last am Zwischenknoten kommt an ihren Knoten zurueck", not aus.get("Knotenlasten"),
          _kurz(aus, "Knotenlasten"))
    kopf = [str(c) for c in (tab.get("StructuralCurveMember") or [[]])[0]]
    zeilen = [dict(zip(kopf, r)) for r in (tab.get("StructuralCurveMember") or [[]])[1:]]
    riegel = next((z for z in zeilen if z.get("Name") == "Riegel"), {})
    check("N30: Blatt nennt die Knoten nach SAF (Nodes 'N1; N2; N3; N4', Segments 'Line; Line; Line')",
          riegel.get("Nodes") == "N1; N2; N3; N4" and riegel.get("Segments") == "Line; Line; Line",
          str(riegel)[:200])
    check("N30: Export ohne Warnung", not warnungen(elog), "; ".join(warnungen(elog))[:160])


# --------------------------------------------------------------------------
# Alle Beispiele
# --------------------------------------------------------------------------
#: Beispiele mit Volumenelementen: SAF kennt keine Volumen; verglichen werden
#: dort nur Lastfaelle und Knotenlasten (an den Knoten der Volumen)
_VOLUMEN = {"solid", "friction"}


def test_beispiele():
    for name in EXAMPLES:
        m = build_example(name)
        m2, elog, ilog, _tab = rundlauf(m, name + ".xlsx")
        aus = abweichungen(m, m2)
        if name in _VOLUMEN:
            arten = ("Lastfälle", "Knotenlasten")
        else:
            arten = ("Lastfälle", "Elemente", "Werkstoff", "Querschnitt", "Achsen", "Eigengewicht",
                     "Knotenlasten", "Stablasten", "Flächenlasten", "Temperatur", "Kombinationen")
        rest = {a: aus[a] for a in arten if aus.get(a)}
        check(f"Beispiel {name}: Lastbild und Steifigkeitsangaben gleich zurueck",
              not rest, "; ".join(f"{a} {_kurz(rest, a)}" for a in rest)[:240])
        check(f"Beispiel {name}: Import ohne Warnung", not warnungen(ilog), "; ".join(warnungen(ilog))[:160])


# --------------------------------------------------------------------------
# Handbuch
# --------------------------------------------------------------------------
def test_handbuch():
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(wurzel, "docs", "Benutzerhandbuch.md"), encoding="utf-8") as f:
        text = " ".join(f.read().split())
    with open(os.path.join(wurzel, "docs", "Schnittstellen.md"), encoding="utf-8") as f:
        schn = " ".join(f.read().split())
    check("Handbuch: SAF-Rundlauf mit Knotenlasten, Einheiten, Rollung, Temperatur (Bis zum 07.10.2026 …)",
          "Bis zum 07.10.2026" in text and "StructuralPointAction" in schn
          and "StructuralCurveActionThermal" in schn and "Design properties" in schn)


def main():
    for t in (test_n25_knotenlasten, test_n26_einheiten, test_n27_rollung, test_n27_verschiedene_rollung_gemeldet,
              test_n28_lasten_rundlauf, test_n28_nicht_darstellbares_gemeldet, test_n28_volumen_gemeldet,
              test_n29_lf1_bleibt, test_n30_mehrere_elemente, test_alte_datei, test_beispiele,
              test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
