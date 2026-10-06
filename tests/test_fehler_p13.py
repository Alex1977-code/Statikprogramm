"""
Fehlerliste 06.10.2026, Paket P13, Eintraege F26 und F27.

F26 - SAF-Export. Ausgangsstand d50592e: Eine Ergebniskombination (Alternativen
ohne Faktoren) fiel beim Schreiben still aus (die Schleife las nur
``c.factors``), und von jeder Stablast gingen nur ``q`` und ``system`` hinaus:
Trapez (q2) und Abschnitt a bis b wurden zur vollen Gleichlast. Beim Nachlesen
zeigte sich dahinter mehr: das Blatt trug die Spalten "q x / q y / q z" und als
Stab "E1" statt des Stabnamens, und der SAF-Import las nichts davon - jede
Stablast kam mit "Stab 'E1' unbekannt" nicht zurueck, die Faktoren einer
Kombination kamen als 1,0 zurueck (der Export schrieb "Coefficient", der Import
las "Factor").
Geprueft wird darum der Rundlauf Export -> Import an Gleich-, Trapez- und
Abschnittslasten (global und lokal, an vorwaerts und rueckwaerts gezeichneten
Staeben, an einem Stab aus zwei Elementen mit verschiedener Rollung) und an
einer Ergebniskombination; das Lastbild wird dazu **nach der Geometrie**
verglichen (an Messpunkten entlang jedes Stabes), nicht nach Elementnummern.
Was SAF nicht darstellen kann, steht im Protokoll des Exports.

F27 - ``parallel.einstellungen_speichern``. Ausgangsstand d50592e: schrieb die
Datei mit ``open(p, "w")`` (abgebrochenes Schreiben liess eine leere oder halbe
Datei zurueck) und ueberschrieb sie bei einem Lesefehler (gesperrt, kein
Zugriff) nur mit den eigenen Schluesseln - Fenstergroesse und Abschnitte
gingen verloren.

Aufruf:  python -m tests.test_fehler_p13
"""
import builtins
import json
import os
import sys
import tempfile
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import parallel  # noqa: E402
from statik3d.model import Model, Material, Section  # noqa: E402
from statik3d.exporters import export_model  # noqa: E402
from statik3d.importers import import_file  # noqa: E402
from statik3d.importers.xlsx_reader import read_table_file, write_xlsx  # noqa: E402
from statik3d.elements import beam3d as bm  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


# --------------------------------------------------------------------------
# Modell und Lastbild
# --------------------------------------------------------------------------
def _modell() -> Model:
    """Zwei Staebe mit je zwei Elementen (S1 vorwaerts, S2 nach unten gezeichnet,
    also gegen die Ordnung der SAF-Datei: dort steht der untere Knoten zuerst)
    und ein Einzelelement ohne Stab (E6). Die Rollung ist je Element verschieden:
    die lokale Last des zweiten Elements von S1 liegt in anderen Achsen als das
    Stabsystem, das die Datei fuehrt (es hat die Rollung des ersten Elements)."""
    m = Model("P13")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    n = [m.add_node(*p) for p in ((0, 0, 0), (4, 0, 0), (6, 0, 0), (6, 0, -5),
                                  (6, 0, -8), (0, 5, 0), (3, 5, 0))]
    e0 = m.add_element("beam", [n[0], n[1]], "S355", "IPE 400", roll=0.0)
    e1 = m.add_element("beam", [n[1], n[2]], "S355", "IPE 400", roll=0.2)
    e2 = m.add_element("beam", [n[2], n[3]], "S355", "IPE 400", roll=0.0)
    e3 = m.add_element("beam", [n[3], n[4]], "S355", "IPE 400", roll=0.3)
    e4 = m.add_element("beam", [n[5], n[6]], "S355", "IPE 400", roll=0.0)
    m.add_member("S1", [e0, e1])
    m.add_member("S2", [e2, e3])
    m.fix(n[0], "all")
    del m.load_cases["LF1"]
    m.add_load_case("LF7", "G", "ständig")
    m.add_load_case("LF8", "Q", "Verkehr", activate=False)
    # --- LF7 ---
    m.load_beam(e0, qz=-10e3, case="LF7")                                  # Gleichlast
    m.load_beam(e1, qz=-4e3, q2=[2e3, 0.0, -12e3], case="LF7")             # Trapez, zwei Richtungen
    m.load_beam(e1, qz=-6e3, a=0.5, b=1.5, case="LF7")                     # Abschnitt, gleichmaessig
    m.load_beam(e0, qz=-3e3, q2=[0.0, 0.0, -9e3], a=1.0, b=3.5, case="LF7")  # Abschnitt + Trapez
    m.load_beam(e1, qy=1e3, system="local", case="LF7")                    # lokal, anders gerollt
    m.load_beam(e4, qx=2e3, qy=-1e3, case="LF7")                           # Stab ohne Elementkette
    # --- LF8: die rueckwaerts gezeichneten Elemente ---
    m.load_beam(e2, qx=5e3, case="LF8")
    m.load_beam(e3, qz=-2e3, q2=[0.0, 0.0, -8e3], a=0.5, b=2.5, case="LF8")  # Abschnitt+Trapez, rueckwaerts
    m.load_beam(e2, qz=-3e3, q2=[0.0, 1e3, -6e3], system="local", case="LF8")
    m.load_beam(e3, qx=1e3, q2=[3e3, 0.0, 0.0], case="LF8")                # Trapez ueber das ganze Element
    m.load_beam(e3, qy=2e3, a=1.0, system="local", case="LF8")             # Abschnitt bis zum Elementende
    m.add_combination("K1", {"LF7": 1.35, "LF8": 1.5}, typ="ULS")
    m.add_combination("EK3", {}, typ="ULS", description="Umhüllende",
                      alternativen=[{"LF7": 1.0, "LF8": 0.5}, {"LF7": 1.35}, {"LF8": 1.5, "LF7": 1.0}])
    return m


def lastbild_in(m: Model, fall: str, p) -> np.ndarray:
    """Die globale Streckenlast [N/m] im Punkt p: Summe aller Stablasten des
    Lastfalls, die dort wirken. Aus den Elementdefinitionen gelesen
    (Richtungskosinus, Abschnitt, Trapez), unabhaengig von Elementnummern."""
    p = np.asarray(p, float)
    q = np.zeros(3)
    for bl in m.load_cases[fall].beam_loads:
        e = m.elements[bl.elem]
        X = m.nodes[[int(x) for x in e.nodes[:2]]]
        T3, L = bm.local_axes(X[0], X[1], e.roll)
        d = p - X[0]
        s = float(d @ T3[0])
        if np.linalg.norm(d - s * T3[0]) > 1e-6 or not (0.0 <= s <= L):
            continue
        a = max(0.0, float(bl.a or 0.0))
        b = L if bl.b is None else min(float(bl.b), L)
        if not (a <= s <= b) or b <= a:
            continue
        q1 = np.asarray(bl.q, float)
        q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
        w = q1 + (q2 - q1) * (s - a) / (b - a)
        q += T3.T @ w if bl.system == "local" else w
    return q


def messpunkte(m: Model):
    """Messpunkte entlang jedes Stabes - zwischen den Elementgrenzen und den
    Abschnittsgrenzen (keine liegt darauf)."""
    n = m.nodes
    for a, b in (((0, 0, 0), (6, 0, 0)), ((6, 0, 0), (6, 0, -8)), ((0, 5, 0), (3, 5, 0))):
        a, b = np.array(a, float), np.array(b, float)
        for k in range(60):
            yield a + (k + 0.5) / 60.0 * (b - a)


def lastbild_abweichung(m1: Model, m2: Model):
    """(groesste Abweichung [N/m], groesste Last [N/m], Messpunkte) ueber alle Faelle."""
    worst, biggest, n = 0.0, 0.0, 0
    for fall in ("LF7", "LF8"):
        if fall not in m2.load_cases:
            return float("inf"), 1.0, 0
        for p in messpunkte(m1):
            q1, q2 = lastbild_in(m1, fall, p), lastbild_in(m2, fall, p)
            worst = max(worst, float(np.max(np.abs(q1 - q2))))
            biggest = max(biggest, float(np.max(np.abs(q1))))
            n += 1
    return worst, biggest, n


def _exportieren(m: Model, tmp: str, name="m.xlsx"):
    p = os.path.join(tmp, name)
    log = []
    export_model(m, p, log=log)
    return p, log


# --------------------------------------------------------------------------
# F26
# --------------------------------------------------------------------------
def test_stablasten_rundlauf():
    """Export -> Import: dasselbe Lastbild an jedem Messpunkt jedes Stabes."""
    m = _modell()
    with tempfile.TemporaryDirectory() as tmp:
        p, _log = _exportieren(m, tmp)
        lg = []
        m2 = import_file(p, log=lg)
    warn = [z for z in lg if "WARNUNG" in z]
    check("Import der Stablasten ohne Warnung", not warn, "; ".join(warn[:2])[:120])
    abw, gross, n = lastbild_abweichung(m, m2)
    check("Rundlauf: Lastbild an allen Messpunkten gleich (Gleich-, Trapez-, Abschnittslast, "
          "global und lokal)", abw <= 1e-6 * gross and n == 2 * 180,
          f"groesste Abweichung {abw:.6g} N/m bei groesster Last {gross:.6g} N/m, {n} Messpunkte")
    # Gegenpruefung der Pruefung selbst: eine geaenderte Last muss auffallen
    m3 = _modell()
    m3.load_cases["LF8"].beam_loads[1].b = 2.0
    abw3, _g, _n = lastbild_abweichung(m3, m2)
    check("Gegenprobe der Messung: ein um 0,5 m kuerzerer Abschnitt faellt auf", abw3 > 1.0, f"{abw3:.6g} N/m")


def test_blatt_nach_saf_vokabular():
    """Das Blatt StructuralCurveAction traegt die Spalten und Werte der
    SAF-Beschreibung (gitbook.saf.guide, geprueft 06.10.2026): Distribution
    Uniform/Trapez, Value 1/2 in kN/m, Member, Extent Full/Span mit Start/End
    point, Coordinate definition Absolute, Origin From start."""
    m = Model("Blatt")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    a = m.add_node(0, 0, 0)
    b = m.add_node(6, 0, 0)
    e = m.add_element("beam", [a, b], "S355", "IPE 400")
    m.add_member("S1", [e])
    del m.load_cases["LF1"]
    m.add_load_case("LF7", "G")
    m.load_beam(e, qz=-10e3, case="LF7")
    m.load_beam(e, qz=-4e3, q2=[0, 0, -12e3], case="LF7")
    m.load_beam(e, qz=-6e3, a=1.0, b=3.5, case="LF7")
    with tempfile.TemporaryDirectory() as tmp:
        p, _log = _exportieren(m, tmp)
        t = read_table_file(p)
    rows = t.get("StructuralCurveAction") or []
    kopf = [str(c) for c in rows[0]] if rows else []
    soll = ["Name", "Distribution", "Direction", "Value 1 [kN/m]", "Value 2 [kN/m]", "Member",
            "Load case", "Coordinate system", "Coordinate definition", "Origin", "Extent",
            "Start point [m]", "End point [m]"]
    check("Kopfzeile: die Spalten der SAF-Beschreibung", all(s in kopf for s in soll),
          str([s for s in soll if s not in kopf]))
    z = [defaultdict(str, zip(kopf, r)) for r in rows[1:]]   # fehlende Spalte: leer statt KeyError
    check("drei Zeilen, je Stablast und Richtung eine", len(z) == 3, str(len(z)))
    if len(z) == 3:
        gl, tr, ab = z
        check("Gleichlast: Uniform, Z, -10 kN/m beide Werte, Stab S1, ganze Laenge",
              gl["Distribution"] == "Uniform" and gl["Direction"] == "Z" and gl["Member"] == "S1"
              and abs(float(gl["Value 1 [kN/m]"]) + 10.0) < 1e-12
              and abs(float(gl["Value 2 [kN/m]"]) + 10.0) < 1e-12 and gl["Extent"] == "Full", str(gl))
        check("Trapez: Trapez, -4 kN/m bis -12 kN/m, ganze Laenge",
              tr["Distribution"] == "Trapez" and abs(float(tr["Value 1 [kN/m]"]) + 4.0) < 1e-12
              and abs(float(tr["Value 2 [kN/m]"]) + 12.0) < 1e-12 and tr["Extent"] == "Full", str(tr))
        check("Abschnitt 1,0 bis 3,5 m: Span, Absolute, From start, Start 1 / End 3,5",
              ab["Extent"] == "Span" and ab["Coordinate definition"] == "Absolute"
              and ab["Origin"] == "From start" and abs(float(ab["Start point [m]"]) - 1.0) < 1e-12
              and abs(float(ab["End point [m]"]) - 3.5) < 1e-12
              and abs(float(ab["Value 1 [kN/m]"]) + 6.0) < 1e-12, str(ab))


def test_ergebniskombination():
    """Eine Ergebniskombination geht hinaus: je Alternative eine gewoehnliche
    Summe (SAF fuehrt Kombinationen als Summen), zusammengehalten durch die
    Spalte "Envelope"; der Import macht daraus wieder die Ergebniskombination."""
    m = _modell()
    with tempfile.TemporaryDirectory() as tmp:
        p, log = _exportieren(m, tmp)
        t = read_table_file(p)
        lg = []
        m2 = import_file(p, log=lg)
    rows = t.get("StructuralLoadCombination") or []
    namen = {str(r[0]) for r in rows[1:]}
    check("Blatt: die drei Alternativen stehen als Kombinationen da",
          {"EK3 [1]", "EK3 [2]", "EK3 [3]"} <= namen, str(sorted(namen)))
    check("Protokoll des Exports nennt die Ergebniskombinationen und was SAF nicht kennt",
          any("Ergebniskombination" in z and "Umhüllende" in z for z in log), "; ".join(log)[:200])
    k1 = m2.combinations.get("K1")
    check("Rundlauf: gewoehnliche Kombination behaelt ihre Faktoren (1,35 / 1,5, nicht 1,0)",
          k1 is not None and abs(k1.factors.get("LF7", 0) - 1.35) < 1e-12
          and abs(k1.factors.get("LF8", 0) - 1.5) < 1e-12, str(k1.factors if k1 else None))
    ek = m2.combinations.get("EK3")
    check("Rundlauf: EK3 ist wieder eine Ergebniskombination mit drei Alternativen",
          ek is not None and ek.ist_umhuellende and len(ek.alternativen) == 3 and ek.art == "EK",
          str(ek.alternativen if ek else None))
    if ek is not None:
        soll = [{"LF7": 1.0, "LF8": 0.5}, {"LF7": 1.35}, {"LF8": 1.5, "LF7": 1.0}]
        check("… mit denselben Lastfaellen und Faktoren je Alternative, in derselben Reihenfolge",
              len(ek.alternativen) == 3 and all(
                  set(a) == set(s) and all(abs(a[k] - s[k]) < 1e-12 for k in s)
                  for a, s in zip(ek.alternativen, soll)), str(ek.alternativen))
        check("… und ohne eigene Faktoren (die Summe waere sinnlos)", not ek.factors, str(ek.factors))
    check("… die Alternativen kommen nicht zusaetzlich als eigene Kombinationen herein",
          not [n for n in m2.combinations if n.startswith("EK3 [")], str(sorted(m2.combinations)))
    check("Import der Kombinationen ohne Warnung", not [z for z in lg if "WARNUNG" in z],
          "; ".join(z for z in lg if "WARNUNG" in z)[:120])


def test_nicht_darstellbares_im_protokoll():
    """Eine Stablast, die sich nicht entlang des Stabes legen laesst, wird nicht
    still verfaelscht oder weggelassen: das Protokoll nennt sie."""
    m = Model("Ketten")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    n = [m.add_node(*p) for p in ((0, 0, 0), (2, 0, 0), (5, 0, 0), (7, 0, 0))]
    e0 = m.add_element("beam", [n[0], n[1]], "S355", "IPE 400")
    e1 = m.add_element("beam", [n[2], n[3]], "S355", "IPE 400")    # liegt nicht an e0
    m.add_member("LUECKE", [e0, e1])
    del m.load_cases["LF1"]
    m.add_load_case("LF7", "G")
    m.load_beam(e0, qz=-1e3, case="LF7")
    m.load_beam(e1, qz=-2e3, case="LF7")
    with tempfile.TemporaryDirectory() as tmp:
        p, log = _exportieren(m, tmp)
        t = read_table_file(p)
    zeilen = (t.get("StructuralCurveAction") or [[]])[1:]
    nennt = [z for z in log if "LUECKE" in z and "nicht geschrieben" in z]
    check("Last auf einem Stab ohne zusammenhaengende Elementkette: Protokoll nennt Stab und Grund",
          bool(nennt) and "Stablast" in nennt[0], "; ".join(log)[:200])
    check("… und das Blatt traegt dazu keine verfaelschte Zeile", len(zeilen) == 0, str(len(zeilen)))


def test_import_abschnitt_relativ():
    """Der Import liest Span mit Start/End point - absolut und relativ - und
    meldet einen Span ohne Positionen, statt ihn still als Volllast zu nehmen."""
    kopf = ["Name", "Type", "Force action", "Distribution", "Direction", "Value 1 [kN/m]",
            "Value 2 [kN/m]", "Member", "Load case", "Coordinate system", "Location",
            "Coordinate definition", "Origin", "Extent", "Start point [m]", "End point [m]"]
    blaetter = {
        "StructuralPointConnection": [["Name", "Coordinate X", "Coordinate Y", "Coordinate Z"],
                                      ["N1", 0.0, 0.0, 0.0], ["N2", 8.0, 0.0, 0.0]],
        "StructuralCurveMember": [["Name", "Cross-section", "Material", "Begin node", "End node",
                                   "Rotation", "Length", "Type"],
                                  ["B1", "IPE 400", "S355", "N1", "N2", 0.0, 8.0, "Beam"]],
        "StructuralLoadCase": [["Name", "Load group", "Load type", "Action type", "Description"],
                               ["LF7", "G", "Static", "G", ""]],
        "StructuralCurveAction": [kopf,
            ["Q1", "Standard", "On beam", "Uniform", "Z", -5.0, -5.0, "B1", "LF7", "Global", "Length",
             "Relative", "From start", "Span", 0.25, 0.75],
            ["Q2", "Standard", "On beam", "Trapez", "Z", -1.0, -3.0, "B1", "LF7", "Global", "Length",
             "Absolute", "From end", "Span", 1.0, 3.0],
            ["Q3", "Standard", "On beam", "Uniform", "Z", -7.0, -7.0, "B1", "LF7", "Global", "Length",
             "Absolute", "From start", "Span", "", ""]],
    }
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "saf.xlsx")
        write_xlsx(p, blaetter)
        lg = []
        m = import_file(p, log=lg)
    fall = m.load_cases.get("LF7")
    q = lambda x: float(lastbild_in(m, "LF7", (x, 0.0, 0.0))[2])  # noqa: E731
    check("relativ 0,25 bis 0,75 von 8 m: -5 kN/m von 2 m bis 6 m, davor und dahinter nichts",
          fall is not None and abs(q(3.0) + 5e3) < 1e-6 and abs(q(1.0)) < 1e-6 and abs(q(7.5)) < 1e-6,
          f"{[round(q(x)) for x in (1, 3, 7.5)]}")
    # Q2 ab Stabende: Start 1 m (Wert -1) = 7 m, End 3 m (Wert -3) = 5 m - Wert 1 gehoert zum Startpunkt
    check("From end: Start- und Endpunkt vom Stabende gezaehlt, Wert 1 am Startpunkt (5,5 m: -7,5; 6,5 m: -1,5 kN/m)",
          abs(q(5.5) + 7.5e3) < 1e-6 and abs(q(6.5) + 1.5e3) < 1e-6, f"{q(5.5):.6g} / {q(6.5):.6g}")
    warn = [z for z in lg if "WARNUNG" in z]
    check("Span ohne Start/End point: Warnung (nennt Span und die Last) statt stiller Volllast",
          any("Span" in z for z in warn) and abs(q(7.5)) < 1e-6, "; ".join(warn)[:200])


def test_import_alte_datei_coefficient():
    """Eine Datei, die der Export bis zum 06.10.2026 schrieb (Spalte "Coefficient"
    statt "Factor"), liest der Import weiter mit ihren Faktoren."""
    blaetter = {
        "StructuralLoadCase": [["Name", "Load group", "Load type", "Action type", "Description"],
                               ["LF7", "G", "Static", "G", ""], ["LF8", "Q", "Static", "Q", ""]],
        "StructuralLoadCombination": [["Name", "Category", "Load case", "Coefficient"],
                                      ["K1", "ULS", "LF7", 1.35], ["K1", "ULS", "LF8", 1.5]],
    }
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "alt.xlsx")
        write_xlsx(p, blaetter)
        m = import_file(p, log=[])
    k1 = m.combinations.get("K1")
    check("Datei mit Spalte „Coefficient“: Faktoren 1,35 und 1,5 bleiben",
          k1 is not None and k1.factors == {"LF7": 1.35, "LF8": 1.5}, str(k1.factors if k1 else None))


# --------------------------------------------------------------------------
# F27
# --------------------------------------------------------------------------
class _Datei:
    """Eine Einstellungsdatei in einem eigenen Ordner; STATIK3D_EINSTELLUNGEN zeigt darauf."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ordner = os.path.join(self.tmp.name, "daten")
        os.makedirs(self.ordner)
        self.pfad = os.path.join(self.ordner, "einstellungen.json")
        self.alt = os.environ.get("STATIK3D_EINSTELLUNGEN")
        os.environ["STATIK3D_EINSTELLUNGEN"] = self.pfad
        return self

    def __exit__(self, *a):
        if self.alt is None:
            os.environ.pop("STATIK3D_EINSTELLUNGEN", None)
        else:
            os.environ["STATIK3D_EINSTELLUNGEN"] = self.alt
        self.tmp.cleanup()

    def schreibe(self, d):
        with open(self.pfad, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def lies(self):
        with open(self.pfad, encoding="utf-8") as f:
            return json.load(f)

    def roh(self):
        with open(self.pfad, "rb") as f:
            return f.read()


_FREMD = {"fenster": {"fassung": 1, "geometrie": [10, 20, 1600, 900], "maximiert": False},
          "abschnitte": {"berechnung_experten": True}, "solver_threads": 7}


def test_einstellungen_fremde_schluessel():
    with _Datei() as d:
        d.schreibe(_FREMD)
        r = parallel.einstellungen_speichern()
        inhalt = d.lies()
        check("lesbare Datei: fremde Schluessel (fenster, abschnitte) bleiben stehen",
              r == d.pfad and inhalt.get("fenster") == _FREMD["fenster"]
              and inhalt.get("abschnitte") == _FREMD["abschnitte"], str(sorted(inhalt)))
        check("… und die eigenen Schluessel sind geschrieben (solver_threads aus den Einstellungen)",
              all(k in inhalt for k in parallel.GESPEICHERT)
              and inhalt["solver_threads"] == parallel.settings().solver_threads, str(inhalt.get("solver_threads")))
        check("… es bleibt keine Hilfsdatei liegen", os.listdir(d.ordner) == ["einstellungen.json"],
              str(os.listdir(d.ordner)))
    with _Datei() as d:
        r = parallel.einstellungen_speichern()
        check("fehlende Datei: wird angelegt", r == d.pfad and set(d.lies()) == set(parallel.GESPEICHERT))
    with _Datei() as d:
        with open(d.pfad, "w", encoding="utf-8") as f:
            f.write("{kein json")
        r = parallel.einstellungen_speichern()
        check("kaputtes JSON (nichts mehr zu retten): wie bei fenster.py neu geschrieben",
              r == d.pfad and set(d.lies()) == set(parallel.GESPEICHERT))


def test_einstellungen_lesefehler():
    """Laesst sich die vorhandene Datei nicht lesen (gesperrt, kein Zugriff),
    wird sie nicht ueberschrieben - sonst gingen die fremden Schluessel verloren."""
    with _Datei() as d:
        d.schreibe(_FREMD)
        vorher = d.roh()
        echt = builtins.open
        n = {"n": 0}

        def sperre(datei, mode="r", *a, **k):
            if str(datei) == d.pfad and "r" in mode and "b" not in mode:
                n["n"] += 1
                raise PermissionError(13, "Zugriff verweigert", d.pfad)
            return echt(datei, mode, *a, **k)

        builtins.open = sperre
        try:
            try:
                parallel.einstellungen_speichern()
                fehler = None
            except OSError as ex:
                fehler = ex
        finally:
            builtins.open = echt
        check("Lesefehler: einstellungen_speichern wirft OSError (die Aufrufer fangen es und protokollieren)",
              fehler is not None, repr(fehler))
        check("… die Datei bleibt byteweise gleich (fremde Schluessel nicht ueberschrieben)",
              d.roh() == vorher and n["n"] >= 1, f"{n['n']} Leseversuche")
        text = str(fehler) if fehler is not None else ""
        check("… und die Meldung sagt, dass sie sich nicht lesen laesst und nichts geschrieben wurde",
              "nicht lesen" in text and "nichts geschrieben" in text, text)
        check("… nach dem Fehler schreibt der naechste Aufruf wieder, mit allen Schluesseln",
              parallel.einstellungen_speichern() == d.pfad and d.lies().get("fenster") == _FREMD["fenster"])


def test_einstellungen_atomar():
    """Bricht das Schreiben mittendrin ab, bleibt die alte Datei ganz."""
    with _Datei() as d:
        d.schreibe(_FREMD)
        vorher = d.roh()
        echt = json.dump

        def kaputt(obj, fp, *a, **k):
            fp.write('{"abgebrochen": ')
            raise OSError(28, "Kein Speicherplatz mehr")

        json.dump = kaputt
        try:
            try:
                parallel.einstellungen_speichern()
                fehler = None
            except OSError as ex:
                fehler = ex
        finally:
            json.dump = echt
        check("Schreiben bricht ab: OSError nach oben", fehler is not None, repr(fehler))
        check("… die alte Datei ist ganz (byteweise gleich, nicht leer, nicht halb)",
              d.roh() == vorher, f"{len(d.roh())} gegen {len(vorher)} Byte")
        check("… und es bleibt keine halbe Hilfsdatei liegen", os.listdir(d.ordner) == ["einstellungen.json"],
              str(os.listdir(d.ordner)))


def test_handbuch():
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(wurzel, "docs", "Benutzerhandbuch.md"), encoding="utf-8") as f:
        text = " ".join(f.read().split())
    with open(os.path.join(wurzel, "docs", "Schnittstellen.md"), encoding="utf-8") as f:
        schn = " ".join(f.read().split())
    check("Handbuch: SAF-Export schreibt Trapez- und Abschnittslasten (Bis zum 06.10.2026 …)",
          "Bis zum 06.10.2026 schrieb der SAF-Export" in text and "Abschnitt" in text
          and "Ergebniskombination" in text and "Envelope" in text)
    check("Handbuch: Einstellungsdatei wird atomar geschrieben und bei Lesefehler nicht angefasst",
          "Bis zum 06.10.2026 schrieb Statik3D die Einstellungsdatei" in text)
    check("Schnittstellenhandbuch: Stablasten und Ergebniskombination im SAF",
          "StructuralCurveAction" in schn and "Envelope" in schn)


def main():
    for t in (test_stablasten_rundlauf, test_blatt_nach_saf_vokabular, test_ergebniskombination,
              test_nicht_darstellbares_im_protokoll, test_import_abschnitt_relativ,
              test_import_alte_datei_coefficient,
              test_einstellungen_fremde_schluessel, test_einstellungen_lesefehler,
              test_einstellungen_atomar, test_handbuch):
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
