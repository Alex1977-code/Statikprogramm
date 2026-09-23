"""
Ermuedung aus Verlaeufen: Zaehlverfahren "spanne", Nachweis fuer Volumen.

"spanne" ist die Schwingbreite Maximum minus Minimum ueber die Zustaende
eines Verlaufs - das, was RFEM aus einer Ergebniskombination fuer die
Ermuedung bildet - mit einem Spiel je Wiederholung und Palmgren-Miner ueber
alle Lasten. Rainflow und Reservoir bleiben als Option. Volumen bekommen den
Nachweis ueber die vorzeichenbehaftete Hauptspannung mit dem groessten Betrag
je Element.

Aufruf:  python -m tests.test_ermuedung_verlauf
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, FatigueLoad  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402
from statik3d import mesher, solver  # noqa: E402
from statik3d.ec3 import fatigue as F  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def _kragarm():
    """IPE 200, 2 m, drei Lastfaelle mit Einzellast an der Spitze."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (2, 0, 0), 4)
    m.fix(ids[0], [0, 1, 2, 3, 4, 5])
    m.case().category = "G"
    m.load_node(ids[-1], Fz=-10000.0)
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fz=-25000.0)
    m.add_load_case("LF3", "Q")
    m.load_node(ids[-1], Fz=-5000.0)
    m.add_member("Kragarm", list(range(4)), detail_category=71e6)
    return m


def test_spanne():
    m = _kragarm()
    fl = FatigueLoad("Ereignis", folge=["LF1", "LF2", "LF3"], wiederholungen=1e5)
    check("Vorgabe fuer einen Verlauf ist spanne", fl.zaehlung == "spanne", fl.zaehlung)
    m.fatigue_loads[fl.name] = fl
    an = solver.solve_all(m, design=False, fatigue=True)
    fm = an.fatigue.members["Kragarm"]
    sec = m.sections["IPE 200"]
    dsig = (25000.0 - 5000.0) * 2.0 / sec.Wel_y * m.design.gamma_Ff     # M/W an der Einspannung
    check("spanne: genau eine Stufe am massgebenden Ort", len(fm.kollektiv) == 1,
          str(fm.kollektiv))
    check("mit der Schwingbreite Maximum minus Minimum (LF2 - LF3)",
          abs(fm.kollektiv[0][0] - dsig) < 1e-6 * dsig,
          f"{fm.kollektiv[0][0]/1e6:.3f} MPa, Hand {dsig/1e6:.3f} MPa")
    check("und einem Spiel je Wiederholung", abs(fm.kollektiv[0][1] - 1e5) < 1e-6)
    check("Schaedigung nach Palmgren-Miner", abs(fm.D - 1e5 / F.sn_life(dsig, 71e6, fm.gamma_Mf)) < 1e-12)
    check("die Uebersichtszeile nennt die Stufe", fm.ranges and abs(fm.ranges[0][0] - dsig) < 1e-6 * dsig
          and abs(fm.ranges[0][1] - 1e5) < 1e-6, str(fm.ranges))
    # Reihenfolge ist gleichgueltig
    fl.folge = ["LF3", "LF1", "LF2"]
    D2 = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    check("spanne haengt nicht von der Reihenfolge ab", abs(D2 - fm.D) < 1e-15)
    # Zwei Zustaende im Verlauf: spanne zaehlt ein Spiel je Wiederholung -
    # dasselbe wie die Zwei-Zustaende-Form (case_max gegen case_min mit n
    # Spielen). Rainflow zaehlt dort nur ein halbes Spiel (ASTM-Rest,
    # gemessen: D 0,609 statt 1,219) - fuer eine Ergebniskombination aus
    # zwei Zustaenden waere das die halbe Schaedigung.
    fl.folge = ["LF2", "LF3"]
    Ds = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    fl.zaehlung = "rainflow"
    Dr = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    m.fatigue_loads.clear()
    m.add_fatigue_load("Zwei", "LF2", "LF3", 1e5)
    Dz = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    check("zwei Zustaende: spanne = Zwei-Zustaende-Form (n Spiele)",
          abs(Ds - Dz) < 1e-15 and abs(Ds - fm.D) < 1e-15, f"{Ds:.4e} / {Dz:.4e}")
    check("Rainflow zaehlt bei zwei Zustaenden ein halbes Spiel", abs(Dr - 0.5 * Ds) < 1e-15,
          f"{Dr:.4e} / {Ds:.4e}")
    # Globale Lastspielzahl: ohne eigene Zahl gilt die der Nachweiseinstellungen
    m.fatigue_loads.clear()
    fg = FatigueLoad("Global", folge=["LF2", "LF3"])
    m.fatigue_loads["Global"] = fg
    check("ohne eigene Zahl: Wiederholungen None (global)", fg.wiederholungen is None and "global" in fg.bezug(),
          fg.bezug())
    m.design.ermuedung_lastspiele = 5e5
    Dg = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    check("die globale Lastspielzahl (5e5) wirkt: D = 5 x D(1e5)", abs(Dg - 5.0 * Ds) < 1e-12 * Dg,
          f"{Dg:.4e} / {Ds:.4e}")
    fg.wiederholungen = 1e5
    Dl = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    check("die eigene Zahl geht vor", abs(Dl - Ds) < 1e-15)
    m.fatigue_loads.clear()
    fz = m.add_fatigue_load("Zwei global", "LF2", "LF3", None)
    Dz2 = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    check("zwei Zustaende ohne eigene Zahl: globale Lastspielzahl", fz.cycles is None
          and abs(Dz2 - 5.0 * Ds) < 1e-12 * Dz2 and "globale" in fz.bezug(), fz.bezug())
    # Direkt am Zaehler
    check("_zaehlen spanne: eine Stufe max - min",
          F._zaehlen([1.0, 4.0, -2.0, 3.0], "spanne") == [(6.0, 1.0)])
    check("_zaehlen spanne: ein Zustand ist kein Spiel", F._zaehlen([3.0], "spanne") == [])
    check("Rainflow liefert beim Sprung 1,4,-2,3 mehr als eine Stufe",
          len(F._zaehlen([1.0, 4.0, -2.0, 3.0], "rainflow")) > 1)


def test_hauptspannungen():
    """Die geschlossene Loesung (Cardano, trigonometrisch) fuer 2000 Tensoren
    gleicht eigvalsh je Element; das Signal ist die Hauptspannung mit dem
    groessten Betrag samt Vorzeichen; die Woehlerlinie vektorisiert gleicht
    sn_life je Wert."""
    from statik3d.ec3 import volumen as V
    rng = np.random.default_rng(3)
    S = rng.normal(size=(2000, 6)) * 50e6
    S[:10, 3:] = 0.0                                   # reine Normalspannungen
    S[10] = [30e6, 30e6, 30e6, 0.0, 0.0, 0.0]          # hydrostatisch (q = 0)
    S[11] = 0.0                                        # spannungsfrei
    S[12] = [100e6, 100e6, -50e6, 0.0, 0.0, 0.0]       # zwei gleiche Eigenwerte
    H = F.hauptspannungen(S)
    ref = np.array([V.hauptspannungen(s) for s in S])
    check("hauptspannungen vektorisiert = eigvalsh je Element (2000 Tensoren)",
          np.allclose(H, ref, rtol=1e-7, atol=10.0), f"groesste Abweichung {np.abs(H - ref).max():.2e} Pa")
    check("absteigend geordnet", bool(np.all(H[:, 0] >= H[:, 1]) and np.all(H[:, 1] >= H[:, 2])))
    sig = F.signalspannung(S)
    soll = np.where(np.abs(ref[:, 0]) >= np.abs(ref[:, 2]), ref[:, 0], ref[:, 2])
    check("signalspannung = Hauptspannung mit dem groessten Betrag, mit Vorzeichen",
          np.allclose(sig, soll, rtol=1e-7, atol=10.0))
    check("reiner Zug -> +sigma, Druck mit kleinerem Querzug -> -sigma",
          abs(F.signalspannung(np.array([[100e6, 0, 0, 0, 0, 0.0]]))[0] - 100e6) < 1.0
          and abs(F.signalspannung(np.array([[-100e6, 20e6, 0, 0, 0, 0.0]]))[0] + 100e6) < 1.0)
    d = rng.uniform(1e6, 400e6, 1000)
    NR = F._n_vektor(d, 71e6, 1.15)
    ref_n = np.array([F.sn_life(x, 71e6, 1.15) for x in d])
    check("_n_vektor = sn_life je Wert (1000 Schwingbreiten, mit unendlich)",
          np.array_equal(np.isinf(NR), np.isinf(ref_n))
          and np.allclose(NR[np.isfinite(NR)], ref_n[np.isfinite(ref_n)], rtol=1e-12)
          and np.isinf(NR).sum() > 0, f"{np.isinf(NR).sum()} unendlich")
    t = time.time()
    F.signalspannung(rng.normal(size=(200000, 6)) * 50e6)
    dauer = time.time() - t
    check("200 000 Tensoren in unter 2 s (eigvalsh je Element: Minuten bei 2 Mio.)",
          dauer < 2.0, f"{dauer:.2f} s")


def _zugstab_volumen(F1: float, F2: float):
    """Quader 1 x 0,1 x 0,1 m aus 10 x 2 x 2 Hexaedern, Symmetrielagerung
    (x = 0: u_x, y = 0: u_y, z = 0: u_z), Zug an der Stirnflaeche x = 1 als
    konsistente Knotenlasten - ein gleichfoermiger Spannungszustand
    sigma_x = F / A, den jedes Element genau trifft (Patch-Test)."""
    from statik3d.model import Volumenkoerper
    m = Model()
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", 1.0, 0.1, 0.1, 10, 2, 2, typ="hex8")
    nx, ny, nz = ids.shape[0] - 1, ids.shape[1] - 1, ids.shape[2] - 1
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                dof = ([0] if i == 0 else []) + ([1] if j == 0 else []) + ([2] if k == 0 else [])
                if dof:
                    m.fix(int(ids[i, j, k]), dof)
    m.case().category = "G"
    m.add_load_case("LF2", "Q")
    for lc, Fx in (("LF1", F1), ("LF2", F2)):
        m.active_case = lc
        Fe = Fx / (ny * nz) / 4.0
        for j in range(ny):
            for k in range(nz):
                for jj, kk in ((j, k), (j + 1, k), (j, k + 1), (j + 1, k + 1)):
                    m.load_node(int(ids[nx, jj, kk]), Fx=Fe)
    m.koerper["V1"] = Volumenkoerper("V1", [], material="S235", elemente=list(range(len(m.elements))),
                                     kerbfall=71e6)
    return m


def test_volumen():
    m = _zugstab_volumen(1000e3, 400e3)
    m.fatigue_loads["Zug"] = FatigueLoad("Zug", folge=["LF1", "LF2"], wiederholungen=1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    fv = an.fatigue.volumen.get("V1")
    check("Ermuedungsnachweis fuer das Volumen liegt vor", fv is not None, str(list(an.fatigue.volumen)))
    if fv is None:
        return
    k1 = m.koerper["V1"]
    gMf = F.GAMMA_MF.get((k1.assessment, k1.consequence), 1.15)
    dsig = 600e3 / 0.01 * m.design.gamma_Ff
    check("Schwingbreite = Delta F / A = 60 N/mm2 (Patch-Test)",
          abs(fv.dsig_max - dsig) < 1e-6 * dsig, f"{fv.dsig_max / 1e6:.4f} MPa")
    check("Schaedigung = n / N_R(60 MPa, Kerbfall 71)",
          abs(fv.D - 1e5 / F.sn_life(dsig, 71e6, gMf)) < 1e-12 * max(fv.D, 1e-12), f"D = {fv.D:.5f}")
    check("gamma_Mf aus Schadensfolge und Konzept des Koerpers", fv.gamma_Mf == gMf, str(fv.gamma_Mf))
    check("massgebendes Element benannt", fv.element in m.koerper["V1"].elemente, str(fv.element))
    check("Kollektiv am massgebenden Element: eine Stufe, n Spiele",
          len(fv.kollektiv) == 1 and abs(fv.kollektiv[0][1] - 1e5) < 1e-6, str(fv.kollektiv))
    ube = an.fatigue.util_by_element(m)
    check("Ausnutzung je Element fuer die Faerbung - alle 40 Elemente gleich (float32)",
          len(ube) == 40 and all(abs(u - fv.util) < 1e-6 * fv.util for u in ube.values()), f"{len(ube)}")
    tab = an.fatigue.table()
    check("Tabelle Ermuedung fuehrt das Volumen", any(str(r[0]).startswith("Volumen V1") for r in tab[1:]),
          str([r[0] for r in tab[1:]]))
    check("Zusammenfassung nennt Volumen", "Volumen" in an.fatigue.summary(), an.fatigue.summary())
    # Verlauf 1 -> 2 -> 1 mit spanne: identisch; mit Rainflow: eine Stufe, ein Spiel
    m.fatigue_loads["Zug"].folge = ["LF1", "LF2", "LF1"]
    D_sp = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"].D
    m.fatigue_loads["Zug"].zaehlung = "rainflow"
    fr = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"]
    check("Verlauf 1-2-1: spanne = Rainflow (ein Spiel von 60 MPa)",
          abs(D_sp - fv.D) < 1e-15 and abs(fr.D - fv.D) < 1e-12 * fv.D
          and len(fr.kollektiv) == 1 and abs(fr.kollektiv[0][1] - 1e5) < 1e-6,
          f"{D_sp:.5f} / {fr.D:.5f} {fr.kollektiv}")
    # Zwei Zustaende ohne Verlauf
    m.fatigue_loads.clear()
    m.add_fatigue_load("Zwei", "LF1", "LF2", 1e5)
    D2 = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"].D
    check("zwei Zustaende (case_max/case_min): dieselbe Schaedigung", abs(D2 - fv.D) < 1e-15)
    # Druck statt Zug: das Signal ist negativ, die Schwingbreite dieselbe
    md = _zugstab_volumen(-1000e3, -400e3)
    md.fatigue_loads["Druck"] = FatigueLoad("Druck", folge=["LF1", "LF2"], wiederholungen=1e5)
    fd = solver.solve_all(md, design=False, fatigue=True).fatigue.volumen["V1"]
    check("Druck: Signal negativ, Schwingbreite und Schaedigung gleich",
          abs(fd.D - fv.D) < 1e-12 * fv.D and abs(fd.dsig_max - dsig) < 1e-6 * dsig, f"{fd.D:.5f}")
    # Sammlung (0 Wiederholungen) traegt nichts bei; Koerper ohne Kerbfall bleibt aussen vor
    m.fatigue_loads.clear()
    m.fatigue_loads["Sammlung"] = FatigueLoad("Sammlung", folge=["LF1", "LF2"], wiederholungen=0.0)
    an0 = solver.solve_all(m, design=False, fatigue=True)
    check("nur eine unwirksame Sammlung: kein Volumennachweis", "V1" not in an0.fatigue.volumen)
    m.fatigue_loads["Zug"] = FatigueLoad("Zug", folge=["LF1", "LF2"], wiederholungen=1e5)
    m.koerper["V1"].kerbfall = 0.0
    an1 = solver.solve_all(m, design=False, fatigue=True)
    check("Koerper ohne Kerbfall: kein Nachweis", not an1.fatigue.volumen)
    # Bericht
    m.koerper["V1"].kerbfall = 71e6
    an = solver.solve_all(m, design=False, fatigue=True)
    from statik3d.report.html import Report
    import tempfile
    pfad_ = os.path.join(tempfile.mkdtemp(), "volumen.html")
    Report(m, an).to_html(pfad_)
    html = open(pfad_, encoding="utf-8").read()
    check("Bericht: Block „Ermüdung Volumen“ mit dem Koerper und der Hauptspannung",
          "Ermüdungsnachweis Volumen" in html and "V1" in html and "Hauptspannung" in html)


def test_naht_beruehrung():
    """Zwei Volumen aus einem Netz (gemeinsame Knoten in der Ebene x = 1 m):
    die Elemente an der Beruehrungsstelle tragen den Kerbfall Naht (90), der
    Rest den des Koerpers (160). Eine Kontaktbedingung zwischen beiden macht
    die Beruehrung zur Fuge - kein Nahtkerbfall."""
    from statik3d.model import Volumenkoerper, Kontaktbedingung
    m = Model()
    m.add_material(Material.steel("S235"))
    ids = mesher.grid_box(m, "S235", 2.0, 0.1, 0.1, 20, 2, 2, typ="hex8")
    nx, ny, nz = 20, 2, 2
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                dof = ([0] if i == 0 else []) + ([1] if j == 0 else []) + ([2] if k == 0 else [])
                if dof:
                    m.fix(int(ids[i, j, k]), dof)
    m.case().category = "G"
    m.add_load_case("LF2", "Q")
    for lc, Fx in (("LF1", 1000e3), ("LF2", 400e3)):
        m.active_case = lc
        for j in range(ny):
            for k in range(nz):
                for jj, kk in ((j, k), (j + 1, k), (j, k + 1), (j + 1, k + 1)):
                    m.load_node(int(ids[nx, jj, kk]), Fx=Fx / (ny * nz) / 4.0)
    # Element i, j, k hat die Nummer i*ny*nz + j*nz + k (grid_box-Reihenfolge)
    links = [e for e in range(len(m.elements)) if e // (ny * nz) < 10]
    rechts = [e for e in range(len(m.elements)) if e // (ny * nz) >= 10]
    m.koerper["V1"] = Volumenkoerper("V1", [], material="S235", elemente=links, kerbfall=160e6,
                                     kerbfall_naht=90e6)
    m.koerper["V2"] = Volumenkoerper("V2", [], material="S235", elemente=rechts, kerbfall=160e6)
    m.fatigue_loads["Zug"] = FatigueLoad("Zug", folge=["LF1", "LF2"], wiederholungen=1e5)
    kn = F.nahtknoten(m)
    check("Nahtknoten: die 9 Knoten der Ebene x = 1 m, fuer beide Koerper",
          set(kn) == {"V1", "V2"} and len(kn["V1"]) == 9 and kn["V1"] == kn["V2"]
          and all(abs(m.nodes[nd, 0] - 1.0) < 1e-9 for nd in kn["V1"]), str({a: len(b) for a, b in kn.items()}))
    an = solver.solve_all(m, design=False, fatigue=True)
    f1, f2 = an.fatigue.volumen["V1"], an.fatigue.volumen["V2"]
    dsig = 600e3 / 0.01 * m.design.gamma_Ff
    check("V1: 4 Elemente an der Naht, massgebend eines davon mit Kerbfall 90",
          f1.n_naht == 4 and f1.naht and f1.category == 90e6 and f1.element in links
          and f1.element // (ny * nz) == 9, f"{f1.n_naht} {f1.category} Element {f1.element}")
    check("V1: D mit der Woehlerlinie 90 an der Naht",
          abs(f1.D - 1e5 / F.sn_life(dsig, 90e6, f1.gamma_Mf)) < 1e-12 * f1.D, f"{f1.D:.5f}")
    check("V2 ohne Kerbfall Naht: 4 Elemente beruehren, aber Kerbfall 160 ueberall",
          f2.n_naht == 4 and f2.category == 160e6
          and abs(f2.D - 1e5 / F.sn_life(dsig, 160e6, f2.gamma_Mf)) < 1e-12 * max(f2.D, 1e-300),
          f"{f2.n_naht} {f2.category} D {f2.D:.3e}")
    check("Tabelle nennt beide Kerbfaelle und die Naht",
          any("160 / Naht 90" in str(r[1]) and "(Naht)" in str(r[-1]) for r in an.fatigue.table()[1:]),
          str(an.fatigue.table()[1]))
    # Kontaktbedingung zwischen V1 und V2: Fuge, keine Naht
    m.kontaktbedingungen["Fuge"] = Kontaktbedingung("Fuge", koerpernamen=["V1"], gegenkoerper=["V2"])
    check("mit Kontaktbedingung: keine Nahtknoten", F.nahtknoten(m) == {} and F.kontaktpaare(m) == {frozenset(("V1", "V2"))})
    f1k = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"]
    check("und V1 rechnet ueberall mit 160", f1k.n_naht == 0 and f1k.category == 160e6 and not f1k.naht)
    # Vorschlag: Kerbfall Naht 90 kommt mit dem Volumenvorschlag
    from statik3d.ec3 import kerbfaelle as K
    m.koerper["V2"].kerbfall = 0.0
    K.anwenden(m, None)
    check("Vorschlag fuer ein Volumen: 160 und Naht 90",
          m.koerper["V2"].kerbfall == 160e6 and m.koerper["V2"].kerbfall_naht == 90e6
          and m.koerper["V2"].kerbfall_vorschlag)


def test_kerbfall_vorschlaege():
    """Zugstab mit Rundquerschnitt 50, gewalzter Querschnitt 160, Volumen 160
    (Strukturspannung); Naehte gehen vor; eingegebene Werte bleiben; eine
    Eingabe loescht die Marke."""
    from statik3d.ec3 import kerbfaelle as K
    from statik3d.model import Section, Volumenkoerper, Member
    m = _kragarm()                                   # Kragarm: IPE 200 (typ I)
    s = Section(name="Rund 20")
    s.A, s.Iy, s.Iz, s.It, s.typ = 3.14e-4, 7.85e-9, 7.85e-9, 1.57e-8, "circle"
    m.add_section(s)
    n0 = m.add_node(0.0, 1.0, 0.0)
    n1 = m.add_node(2.0, 1.0, 0.0)
    e = m.add_element("truss", [n0, n1], "S235", "Rund 20")
    m.add_member("Anker", [e])
    m.members["Kragarm"].detail_category = None
    m.koerper["V1"] = Volumenkoerper("V1", [], material="S235")
    m.members["Eigen"] = Member("Eigen", [0], detail_category=71e6)
    log = []
    n = K.anwenden(m, log)
    check("Zugstab (truss, Rund): 50 N/mm2 als Vorschlag",
          m.members["Anker"].detail_category == 50e6 and m.members["Anker"].kerbfall_vorschlag,
          str(m.members["Anker"].detail_category))
    check("gewalzter Querschnitt (IPE): 160 N/mm2 als Vorschlag",
          m.members["Kragarm"].detail_category == 160e6 and m.members["Kragarm"].kerbfall_vorschlag)
    check("Volumen: 160 N/mm2, Konzept Strukturspannung, Vorschlag",
          m.koerper["V1"].kerbfall == 160e6 and m.koerper["V1"].kerbfall_konzept == "Strukturspannung"
          and m.koerper["V1"].kerbfall_vorschlag)
    check("eingegebener Kerbfall bleibt", m.members["Eigen"].detail_category == 71e6
          and not m.members["Eigen"].kerbfall_vorschlag and n["behalten"] == 1, str(n))
    check("Protokoll nennt Zahl und Fundstelle", any("Kerbfälle vorgeschlagen" in x and "Tab. 8.1" in x for x in log),
          log[0] if log else "-")
    # ein frueherer Vorschlag wird erneuert, ein bestaetigter nicht
    m.members["Anker"].detail_category = 63e6
    m.members["Anker"].kerbfall_vorschlag = False
    m.members["Kragarm"].detail_category = 63e6            # Marke bleibt: nur ein Vorschlag
    K.anwenden(m, None)
    check("bestaetigter Wert bleibt, alter Vorschlag wird erneuert",
          m.members["Anker"].detail_category == 63e6 and m.members["Kragarm"].detail_category == 160e6)


def test_fehlender_mindestzustand_wird_gemeldet():
    """Ein angegebener, aber nicht gerechneter Mindestzustand ist nicht null.

    `_member_nachweisen` fiel bis zum 22.09.2026 für einen fehlenden
    `case_min` in denselben Zweig wie „kein Mindestzustand angegeben" und
    setzte σ_min = 0. Bei wechselnder Beanspruchung - dem Regelfall - ist das
    die **halbe Schwingbreite**: aus −80/+100 N/mm² werden 100 statt 180. Da
    die Schädigung mit der dritten bis fünften Potenz eingeht, fällt D um den
    Faktor 6 bis 25 zu klein aus, und zwar **auf der unsicheren Seite**.

    Der fehlende **Höchst**zustand wurde die ganze Zeit gemeldet - der
    Mindestzustand nicht. Genau diese Unsymmetrie ist der Fehler.

    Der Prüfkörper nennt als Mindestzustand einen Lastfall, den es nicht
    gibt - das ist derselbe Zustand wie ein nicht gerechneter und ohne
    Umweg herstellbar.
    """
    from statik3d.model import Model, Material, Section
    from statik3d import solver

    def bau(case_min):
        m = Model("ermuedung")
        m.add_material(Material.steel("S235"))
        m.add_section(Section.rectangle("R", 0.1, 0.1))
        k = [m.add_node(i * 1.0, 0.0, 0.0) for i in range(3)]
        for i in range(2):
            m.add_element("beam", [k[i], k[i + 1]], "S235", "R")
        m.fix(k[0], "all")
        m.add_member("M1", [0, 1], detail_category=71e6)
        m.add_load_case("OBEN", "Q")
        m.load_node(k[2], Fz=-1.0e4, case="OBEN")
        m.add_load_case("UNTEN", "Q")
        m.load_node(k[2], Fz=+0.8e4, case="UNTEN")
        m.add_fatigue_load("EL", "OBEN", case_min, cycles=1e6)
        return m

    # (1) Beide Zustaende da: der Nachweis laeuft und liefert eine Schaedigung
    an = solver.solve_all(bau("UNTEN"), fatigue=True)
    fm = (getattr(an.fatigue, "members", None) or {}).get("M1")
    voll = getattr(fm, "util", 0.0)
    check("mit beiden Zuständen wird der Nachweis geführt",
          fm is not None and voll > 0, f"D = {voll:.4f}")

    # (2) Der Mindestzustand ist genannt, aber nicht gerechnet
    an2 = solver.solve_all(bau("FEHLT_ABSICHTLICH"), fatigue=True)
    fm2 = (getattr(an2.fatigue, "members", None) or {}).get("M1")
    warn = list(getattr(fm2, "warnings", None) or [])
    gemeldet = any("Mindestzustand" in w for w in warn)
    check("das Fehlen des Mindestzustands wird gemeldet", gemeldet,
          "; ".join(warn)[:90] or "(keine Warnung)")
    halb = getattr(fm2, "util", 0.0)
    check("und es wird keine halbierte Schwingbreite ausgewiesen",
          halb == 0.0, f"D = {halb:.4f} gegen {voll:.4f} mit beiden Zuständen")
    # Die Gegenprobe: ohne Mindestzustand (Feld leer) ist null richtig und
    # es darf KEINE Warnung geben - sonst waere die Kur zu scharf.
    an3 = solver.solve_all(bau(None), fatigue=True)
    fm3 = (getattr(an3.fatigue, "members", None) or {}).get("M1")
    warn3 = list(getattr(fm3, "warnings", None) or [])
    check("ohne angegebenen Mindestzustand bleibt es beim Schwingen gegen null",
          getattr(fm3, "util", 0.0) > 0
          and not any("Mindestzustand" in w for w in warn3),
          f"D = {getattr(fm3, 'util', 0.0):.4f}, keine Warnung")


def _oder_ek(m, name="EK_oder"):
    """Eine oder-verknuepfte Ergebniskombination, wie sie der RFEM-Import fuer
    die FAT-Kombinationen anlegt: ``factors`` leer, je Alternative ein
    Lastfall. Der Loeser legt sie nur als Umhuellende ab (an.envelopes), nie
    in an.combinations - ein Einzelergebnis gibt es zu ihr nicht."""
    ek = m.add_combination(name, {}, "FAT")
    ek.alternativen = [{"LF1": 1.0}, {"LF2": 1.0}]
    return ek


def _stab_oben_unten():
    """Kragarm aus zwei Balken, Stab M1 mit Kerbfall 71, Lastfaelle OBEN
    (Fz -10 kN) und UNTEN (Fz +8 kN) - wie im Stabtest des Mindestzustands."""
    from statik3d.model import Section
    m = Model("ermuedung")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.1))
    k = [m.add_node(i * 1.0, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [k[i], k[i + 1]], "S235", "R")
    m.fix(k[0], "all")
    m.add_member("M1", [0, 1], detail_category=71e6)
    m.add_load_case("OBEN", "Q")
    m.load_node(k[2], Fz=-1.0e4, case="OBEN")
    m.add_load_case("UNTEN", "Q")
    m.load_node(k[2], Fz=+0.8e4, case="UNTEN")
    return m


def test_mindestzustand_volumen_und_oder_ek():
    """Befunde FE2, FE5, FE13 (22.09.2026): der Volumenzweig und der Weg ueber
    die oder-verknuepfte Ergebniskombination.

    Der Stabtest oben nimmt einen unbekannten Namen - den meldet die
    Modellpruefung ohnehin. Der Weg, auf dem der Fehler wirklich entsteht,
    ist ein anderer: die Maske bot jede Kombination als unteren Zustand an,
    auch eine oder-EK. Die steht in model.combinations (die Pruefung liess
    sie durch), liefert aber kein Einzelergebnis (nur an.envelopes). Bis
    efcf3d6 wurde daraus still sigma_min = 0.

    Hier gehalten: der Volumenzweig (fatigue.py, ``case_min`` benannt und
    nicht gerechnet), die Modellpruefung **vor** der Rechnung - bei einem
    Verlauf nur fuer dessen Glieder - und die Auswahl der Zustaende samt der
    Maske selbst.
    """
    # (1) Volumen, Mindestzustand unbekannt
    m = _zugstab_volumen(1000e3, -400e3)
    m.add_fatigue_load("Zwei", "LF1", "FEHLT", 1e5)
    fv = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen.get("V1")
    check("Volumen, Mindestzustand fehlt: V1 bleibt im Nachweis", fv is not None,
          "V1 fehlt" if fv is None else "")
    check("als nicht gefuehrt, Grund nennt den Mindestzustand",
          fv is not None and "Mindestzustand" in fv.fehler, repr(getattr(fv, "fehler", None)))
    check("und ohne Schaedigung aus |sigma_max - 0|", fv is not None and fv.D == 0.0,
          f"D = {getattr(fv, 'D', None)}")
    # Gegenprobe mit gerechnetem Mindestzustand: 100 gegen -40 N/mm2
    m.fatigue_loads.clear()
    m.add_fatigue_load("Zwei", "LF1", "LF2", 1e5)
    fr = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"]
    soll = 1400e3 / 0.01 * m.design.gamma_Ff
    check("Gegenprobe LF1 gegen LF2: Schwingbreite 140 N/mm2, kein fehler",
          not fr.fehler and abs(fr.dsig_max - soll) < 1e-6 * soll and fr.D > 0,
          f"{fr.dsig_max / 1e6:.3f} MPa, D = {fr.D:.5f}")

    # (2) Volumen, Mindestzustand ist eine oder-EK
    m = _zugstab_volumen(1000e3, -400e3)
    _oder_ek(m)
    m.add_fatigue_load("Zwei", "LF1", "EK_oder", 1e5)
    zeilen = [z for z in m.check() if "EK_oder" in z]
    check("Modellpruefung meldet die oder-EK als Zustand einer Ermuedungslast",
          any(z.startswith("FEHLER") and "Zwei" in z for z in zeilen),
          "; ".join(zeilen)[:90] or "(keine Zeile)")
    an = solver.solve_all(m, design=False, fatigue=True)
    fv = an.fatigue.volumen.get("V1")
    check("oder-EK: nur Umhuellende, kein Einzelergebnis",
          "EK_oder" in an.envelopes and "EK_oder" not in an.all_results())
    check("Volumen, oder-EK als Mindestzustand: nicht gefuehrt, D = 0",
          fv is not None and "EK_oder" in fv.fehler and fv.D == 0.0,
          repr(getattr(fv, "fehler", None)))

    # (3) Stab, Mindestzustand ist eine oder-EK
    ms = _stab_oben_unten()
    ek = ms.add_combination("EK_oder", {}, "FAT")
    ek.alternativen = [{"OBEN": 1.0}, {"UNTEN": 1.0}]
    ms.add_fatigue_load("EL", "OBEN", "EK_oder", cycles=1e6)
    zeilen = [z for z in ms.check() if "EK_oder" in z]
    check("Modellpruefung meldet die oder-EK auch am Stabmodell",
          any(z.startswith("FEHLER") and "EL" in z for z in zeilen),
          "; ".join(zeilen)[:90] or "(keine Zeile)")
    fm = solver.solve_all(ms, fatigue=True).fatigue.members.get("M1")
    check("Stab, oder-EK als Mindestzustand: Warnung, nicht gefuehrt, D = 0",
          fm is not None and any("Mindestzustand" in w for w in fm.warnings)
          and "EK_oder" in fm.fehler and fm.util == 0.0,
          repr(getattr(fm, "fehler", None)))

    # (4) Die Maske bietet nur Zustaende mit Einzelergebnis an - geprueft an
    # der Maske selbst (offscreen, ohne exec). Die erste Fassung pruefte nur
    # Model.ermuedungszustaende(); die Maske mit ihrer alten Zeile (alle
    # Lastfaelle + alle Kombinationen) blieb dabei gruen (Mangel 4 der
    # Gegenpruefung, 23.09.2026, Mutationsprobe M1).
    zust = getattr(m, "ermuedungszustaende", None)
    m.add_combination("EK_summe", {"LF1": 1.0, "LF2": 1.0}, "FAT")
    namen = list(zust()) if callable(zust) else None
    check("Auswahl der Zustaende: Lastfaelle und gewoehnliche Kombinationen, keine oder-EK",
          namen is not None and "EK_oder" not in namen
          and {"LF1", "LF2", "EK_summe"} <= set(namen), str(namen))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from statik3d.gui.dialogs import FatigueLoadDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    maske = FatigueLoadDialog(None, m)
    oben = [maske.cmax.itemText(i) for i in range(maske.cmax.count())]
    unten = [maske.cmin.itemText(i) for i in range(maske.cmin.count())]
    maske.deleteLater()
    app.processEvents()
    check("Maske: oberer Zustand ohne oder-EK, mit Lastfaellen und EK_summe",
          "EK_oder" not in oben and {"LF1", "LF2", "EK_summe"} <= set(oben), str(oben))
    check("Maske: unterer Zustand ohne oder-EK, Nullzustand zuerst",
          "EK_oder" not in unten and unten[:1] == ["(Nullzustand)"]
          and {"LF1", "LF2", "EK_summe"} <= set(unten), str(unten))

    # (5) Ein Verlauf liest nur seine Glieder (fatigue.py: "if folge: ...
    # continue"). Ein case_max, das eine Verlaufs-Last aus der alten Maske
    # mitbringt, darf die Pruefung darum nicht melden - ihr FEHLER liess die
    # CLI mit Exit 2 abbrechen und wies den Web-Rechenstart ab, obwohl die
    # Rechnung dasselbe D liefert (Mangel 2 der Gegenpruefung, 23.09.2026).
    m = _zugstab_volumen(1000e3, -400e3)
    _oder_ek(m)
    m.fatigue_loads["V"] = FatigueLoad("V", case_max="EK_oder", case_min="EK_oder",
                                       folge=["LF1", "LF2"], wiederholungen=1e5)
    zeilen = [z for z in m.check() if "EK_oder" in z]
    check("Verlauf, oder-EK nur im ungenutzten case_max/case_min: keine Zeile",
          not zeilen, "; ".join(zeilen)[:90])
    fv = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"]
    m.fatigue_loads["V"].case_max, m.fatigue_loads["V"].case_min = "", None
    fo = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"]
    check("... und die Rechnung liest es nicht: D wie ohne case_max, erfüllt",
          fv.D == fo.D and fv.D > 0 and fv.status() == "erfüllt" and not fv.warnings,
          f"D = {fv.D:.5f} / {fo.D:.5f}, {fv.status()}")
    m.fatigue_loads["V"].folge = ["LF1", "EK_oder", "LF2"]
    zeilen = [z for z in m.check() if "EK_oder" in z]
    check("oder-EK als Glied des Verlaufs: FEHLER",
          any(z.startswith("FEHLER") and "'V'" in z for z in zeilen),
          "; ".join(zeilen)[:90] or "(keine Zeile)")


def test_volumen_ohne_beitrag_und_unvollstaendig():
    """Befund SV5 (22.09.2026) und der Rest aus FE5.

    Seit efcf3d6 bleibt ein Koerper, zu dem wegen fehlender Ergebnisse keine
    Last beitraegt, als "nicht gefuehrt" im Nachweis. Hier gehalten - und
    was danach noch falsch war: der Eintrag stand in Zusammenfassung und
    Tabelle mit D = 0.000 und "Element -1", und ein Koerper, dessen einzige
    Last 0 Lastspiele hat, liess die Zusammenfassung "keine Staebe oder
    Volumen mit Kerbfall" sagen. Faellt von zwei Lasten eine aus, ist der
    Nachweis nicht vollstaendig - auch das muss am Eintrag stehen.
    """
    # (1) case_max fehlt
    m = _zugstab_volumen(1000e3, -400e3)
    m.add_fatigue_load("Oben fehlt", "FEHLT", "LF2", 1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    fv = an.fatigue.volumen.get("V1")
    check("case_max fehlt: V1 bleibt im Nachweis, fehler nennt den Fall",
          fv is not None and "FEHLT" in fv.fehler, repr(getattr(fv, "fehler", None)))
    st = fv.status() if fv is not None and hasattr(fv, "status") else None
    check("Status des Eintrags: nicht geführt", st == "nicht geführt", str(st))
    s = an.fatigue.summary()
    check("Zusammenfassung nennt den Eintrag nicht geführt, keine Schaedigung 0.000",
          "nicht geführt" in s and "D = 0.000" not in s, s)
    zeile = next((r for r in an.fatigue.table()[1:] if str(r[0]) == "Volumen V1"), None)
    check("Tabelle: 'nicht geführt' samt Grund statt 'Element -1'",
          zeile is not None and "Element -1" not in str(zeile[-1])
          and "nicht geführt" in str(zeile[-1]) and "FEHLT" in str(zeile[-1]),
          str(zeile[-1] if zeile else None))
    # (2) Folgeglied fehlt - es bleibt nur ein Zustand
    m.fatigue_loads.clear()
    m.fatigue_loads["Folge"] = FatigueLoad("Folge", folge=["LF1", "FEHLT"], wiederholungen=1e5)
    fv = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen.get("V1")
    check("Folgeglied fehlt: V1 bleibt als nicht gefuehrt",
          fv is not None and "FEHLT" in fv.fehler and fv.D == 0.0,
          repr(getattr(fv, "fehler", None)))
    # (3) einzige Last mit 0 Lastspielen: gewollt kein Eintrag ("0 heisst
    # unwirksam"), aber die Zusammenfassung darf nicht behaupten, es gebe
    # keinen Koerper mit Kerbfall
    m.fatigue_loads.clear()
    m.add_fatigue_load("Null", "LF1", "LF2", 0.0)
    an = solver.solve_all(m, design=False, fatigue=True)
    s = an.fatigue.summary()
    check("0 Lastspiele: kein Eintrag (unwirksam, wie bisher)", "V1" not in an.fatigue.volumen)
    check("Zusammenfassung nennt V1 ohne wirksame Last statt 'keine ... mit Kerbfall'",
          "keine Staebe oder Volumen mit Kerbfall" not in s
          and "keine Stäbe oder Volumen mit Kerbfall" not in s and "V1" in s, s)
    # Fehlt der einzigen, unwirksamen Last dagegen ein Ergebnis, gibt es einen
    # Eintrag "nicht geführt" mit diesem Grund (fatigue.py: "if fv.warnings:
    # fv.fehler = ..."), aber keine fehlende Last. So beschreibt es jetzt das
    # Benutzerhandbuch; dessen erste Fassung sagte "kein Eintrag" (Mangel 3
    # der Gegenpruefung, 23.09.2026).
    m.fatigue_loads.clear()
    m.fatigue_loads["S"] = FatigueLoad("S", folge=["LF1", "FEHLT", "LF2"], wiederholungen=0.0)
    an = solver.solve_all(m, design=False, fatigue=True)
    fv = an.fatigue.volumen.get("V1")
    check("einzige Last unwirksam und ihr fehlt ein Ergebnis: Eintrag nicht geführt",
          fv is not None and fv.status() == "nicht geführt" and "FEHLT" in fv.fehler
          and not fv.fehlende_lasten and not an.fatigue.ohne_wirksame_last,
          f"{fv.status() if fv else None} {getattr(fv, 'fehler', None)!r} "
          f"{an.fatigue.ohne_wirksame_last}")
    # (4) zwei Lasten, eine ohne Mindestzustand (oder-EK): gerechnet wird die
    # andere, der Eintrag ist aber unvollstaendig
    m = _zugstab_volumen(1000e3, -400e3)
    m.add_fatigue_load("Gut", "LF1", "LF2", 1e5)
    D_gut = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"].D
    _oder_ek(m)
    m.add_fatigue_load("Schlecht", "LF1", "EK_oder", 1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    fv = an.fatigue.volumen["V1"]
    check("eine von zwei Lasten faellt aus: D nur aus 'Gut', kein fehler",
          not fv.fehler and abs(fv.D - D_gut) < 1e-12 * D_gut, f"D = {fv.D:.5f} / {D_gut:.5f}")
    check("und der Eintrag nennt die nicht gerechnete Last, Status unvollständig",
          getattr(fv, "fehlende_lasten", None) == ["Schlecht"]
          and hasattr(fv, "status") and fv.status() == "unvollständig",
          f"{getattr(fv, 'fehlende_lasten', None)} / "
          f"{fv.status() if hasattr(fv, 'status') else None}")
    s = an.fatigue.summary()
    check("Zusammenfassung sagt unvollständig", "unvollständig" in s, s)
    # (5) Gegenprobe, damit die Kur nicht zu scharf ist: eine gewollt
    # unwirksame Last (Sammlung mit 0 Wiederholungen, wie aus dem
    # RFEM-Import), der ein Ergebnis fehlt, macht den Nachweis nicht
    # unvollstaendig - sie haette ohnehin nichts beigetragen.
    m = _zugstab_volumen(1000e3, -400e3)
    m.add_fatigue_load("Gut", "LF1", "LF2", 1e5)
    m.fatigue_loads["Sammlung"] = FatigueLoad("Sammlung", folge=["LF1", "FEHLT", "LF2"],
                                              wiederholungen=0.0)
    m.add_fatigue_load("Null", "FEHLT", "LF2", 0.0)
    fv = solver.solve_all(m, design=False, fatigue=True).fatigue.volumen["V1"]
    check("Volumen: unwirksame Lasten mit fehlendem Ergebnis -> weiter erfüllt",
          fv.status() == "erfüllt" and not fv.fehlende_lasten
          and abs(fv.D - D_gut) < 1e-12 * D_gut,
          f"{fv.status()} {fv.fehlende_lasten}")
    ms = _stab_oben_unten()
    ms.add_fatigue_load("EL", "OBEN", "UNTEN", cycles=5e4)     # D < 1 (1e6: 14,08)
    ms.fatigue_loads["Sammlung"] = FatigueLoad("Sammlung", folge=["OBEN", "FEHLT"],
                                               wiederholungen=0.0)
    ms.add_fatigue_load("Null", "OBEN", "FEHLT", 0.0)
    fm = solver.solve_all(ms, fatigue=True).fatigue.members["M1"]
    check("Stab: unwirksame Lasten mit fehlendem Ergebnis -> weiter erfüllt",
          fm.status() == "erfüllt" and not fm.fehlende_lasten and 0 < fm.util < 1,
          f"{fm.status()} {fm.fehlende_lasten} D = {fm.util:.4f}")


def test_unvollstaendig_je_weg():
    """Befund FE5 an jedem Weg, auf dem eine Last aus D faellt - am Stab und
    am Volumen (Mangel 1 der Gegenpruefung, 23.09.2026).

    Die ersten Pruefungen auf "unvollständig" hielten nur den Volumenzweig
    mit zwei Zustaenden und fehlendem Mindestzustand. Die urspruengliche
    Fehlerstelle des Befunds liegt aber im Stabzweig, und weder dorthin noch
    zum Verlauf mit Luecke noch zum fehlenden Hoechstzustand fuehrte eine
    Pruefung: jede dieser Stellen liess sich auf die alte blosse Warnung
    zuruecksetzen, und beide Suiten blieben bei 77/77 und 120/120
    (Mutationsproben M5, M7, M10, M12, M13). Der Stab stand dann mit
    "erfüllt" und ohne fehlende Last da - genau der Befund FE5.

    Hier traegt je eine Last "Gut" bei, und eine zweite, "Schlecht", faellt
    auf einem von vier Wegen aus. Erwartet: kein fehler, fehlende_lasten
    ["Schlecht"], Status "unvollständig", D allein aus dem Gerechneten. Ein
    Verlauf mit Luecke rechnet seine uebrigen Glieder: dort [oben, unten],
    also dieselbe Spanne wie "Gut" und D = D_gut * (1 + n_schlecht / n_gut).
    """
    def stab():
        m = _stab_oben_unten()
        m.add_fatigue_load("Gut", "OBEN", "UNTEN", cycles=5e4)        # D = 0,704 < 1
        return m

    def volumen():
        m = _zugstab_volumen(1000e3, -400e3)
        m.add_fatigue_load("Gut", "LF1", "LF2", 1e5)                  # D = 0,383 < 1
        return m

    faelle = (("Stab", stab, "OBEN", "UNTEN", 5e4, lambda an: an.fatigue.members.get("M1")),
              ("Volumen", volumen, "LF1", "LF2", 1e5, lambda an: an.fatigue.volumen.get("V1")))
    for art, bau, oben, unten, n_gut, eintrag in faelle:
        gut = eintrag(solver.solve_all(bau(), fatigue=True))
        D_gut = gut.util
        check(f"{art}: Gegenprobe, 'Gut' allein ist erfüllt",
              gut.status() == "erfüllt" and 0 < D_gut < 1 and not gut.fehlende_lasten,
              f"{gut.status()} D = {D_gut:.5f}")
        n_verlauf = 0.2 * n_gut                                     # D_teil = 1,2 D_gut < 1

        def ek(m):
            e = m.add_combination("EK_oder", {}, "FAT")
            e.alternativen = [{oben: 1.0}, {unten: 1.0}]

        wege = (
            ("Hoechstzustand fehlt", lambda m: m.add_fatigue_load("Schlecht", "FEHLT", unten, n_gut), 1.0),
            ("Mindestzustand fehlt", lambda m: m.add_fatigue_load("Schlecht", oben, "FEHLT", n_gut), 1.0),
            ("Mindestzustand oder-EK", lambda m: (ek(m), m.add_fatigue_load("Schlecht", oben, "EK_oder",
                                                                           n_gut)), 1.0),
            ("Verlauf mit Luecke", lambda m: m.fatigue_loads.__setitem__(
                "Schlecht", FatigueLoad("Schlecht", folge=[oben, "FEHLT", unten],
                                        wiederholungen=n_verlauf)), 1.0 + n_verlauf / n_gut),
        )
        for weg, dazu, faktor in wege:
            m = bau()
            dazu(m)
            x = eintrag(solver.solve_all(m, fatigue=True))
            ok = (x is not None and not x.fehler and x.fehlende_lasten == ["Schlecht"]
                  and x.status() == "unvollständig"
                  and abs(x.util - faktor * D_gut) < 1e-9 * D_gut)
            check(f"{art}, {weg}: unvollständig, fehlt 'Schlecht', D aus dem Gerechneten", ok,
                  "kein Eintrag" if x is None else
                  f"{x.status()} {x.fehlende_lasten} {x.fehler!r} D = {x.util:.5f} "
                  f"(soll {faktor * D_gut:.5f})")

        # Reihenfolge in _status: D > 1 schon aus dem Gerechneten ist "NICHT
        # erfüllt", auch wenn eine Last fehlt - ihr Summand nach Miner ist
        # >= 0, sie kann das Urteil nicht umkehren (Mangel 4, Mutation M6:
        # "unvollständig" vor "NICHT erfüllt" blieb unbemerkt).
        m = bau()
        m.fatigue_loads["Gut"].cycles = 20.0 * n_gut                  # D = 20 D_gut > 1
        m.add_fatigue_load("Schlecht", oben, "FEHLT", n_gut)
        x = eintrag(solver.solve_all(m, fatigue=True))
        check(f"{art}: D > 1 und eine Last fehlt -> NICHT erfüllt, nicht unvollständig",
              x is not None and x.util > 1 and x.fehlende_lasten == ["Schlecht"]
              and x.status() == "NICHT erfüllt",
              "kein Eintrag" if x is None else f"{x.status()} D = {x.util:.3f} {x.fehlende_lasten}")


def test_maske_verlauf_ohne_zustaende():
    """Befund B067 (Nebenbefund 22./23.09.2026, am Stand ec6448c gemessen):
    Die Maske uebergab im Modus Verlauf den ersten Eintrag der gesperrten
    Auswahl „Oberer Zustand“ (im Hallenrahmen 'Kran') als case_max. Der
    Anschlussnachweis las ihn: der Verlauf Null -> S -> Null ergab an der
    Kopfplatte K1 D = 3,04294 (Kran gegen null) statt 7,12871 (S gegen null).
    Und nach dem Loeschen von 'Kran' meldete die Modellpruefung einen FEHLER
    fuer eine Last, die 'Kran' gar nicht nennt. Geprueft ueber den echten
    MainWindow.add_fatigue_load mit der echten Maske (offscreen, exec ersetzt).
    """
    import importlib
    import types
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtWidgets
    from statik3d import examples_lib
    # das Modul, nicht die gleichnamige Startfunktion aus statik3d.gui
    G = importlib.import_module("statik3d.gui.main")
    from statik3d.gui.dialogs import FatigueLoadDialog
    from statik3d.joints import anschluss as A
    from statik3d.joints.templates import propose
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    class Maske(FatigueLoadDialog):
        """Die echte Maske im Modus Verlauf, eigene Wiederholungen 5e5."""
        text = ""

        def __init__(self, _parent, model):
            super().__init__(None, model)
            self.art.setCurrentIndex(1)
            self.folge.setText(Maske.text)
            self.global_n.setChecked(False)
            self.wdh.set(5e5)

        def exec(self):
            return True

    meldungen = []

    def neu(m, text):
        Maske.text = text
        vorher = set(m.fatigue_loads)
        s = types.SimpleNamespace(model=m, error=meldungen.append,
                                  merken=lambda _was: None, refresh_all=lambda: None)
        alt = G.FatigueLoadDialog
        G.FatigueLoadDialog = Maske
        try:
            G.MainWindow.add_fatigue_load(s)
        finally:
            G.FatigueLoadDialog = alt
        app.processEvents()
        neue = [n for n in m.fatigue_loads if n not in vorher]
        return m.fatigue_loads[neue[0]] if neue else None

    def fehler(m):
        return [z for z in m.check() if z.startswith("FEHLER")]

    def hall():
        m = examples_lib.build_example("hall")
        m.fatigue_loads.clear()
        return m

    # (1) Im Modus Verlauf stehen die Zustaende nur in der Folge
    m = hall()
    fl = neu(m, "LF1, S, LF1")
    check("Maske, Modus Verlauf: Folge übernommen, case_max leer, case_min None",
          fl is not None and fl.folge == ["LF1", "S", "LF1"] and fl.case_max == ""
          and fl.case_min is None and fl.wiederholungen == 5e5,
          "keine Last" if fl is None else f"case_max {fl.case_max!r}, case_min {fl.case_min!r}")
    m.remove_load_case("Kran")
    check("... Lastfall 'Kran' gelöscht: kein FEHLER für den Verlauf ohne 'Kran'",
          not fehler(m), "; ".join(fehler(m))[:100])

    # (2) Dateien aus der alten Maske tragen das case_max weiter: die
    # Modellpruefung liest es bei einem Verlauf nicht mehr - eine Last aus
    # zwei Zustaenden mit geloeschtem Zustand bleibt ein FEHLER
    m = hall()
    m.fatigue_loads["Alt"] = FatigueLoad("Alt", case_max="Kran", folge=["LF1", "S", "LF1"],
                                         wiederholungen=5e5)
    m.add_fatigue_load("Zwei", "Kran", None, 5e5)
    m.remove_load_case("Kran")
    zeilen = fehler(m)
    check("alter Verlauf mit case_max 'Kran': kein FEHLER, zwei Zustände: FEHLER",
          not [z for z in zeilen if "'Alt'" in z] and [z for z in zeilen if "'Zwei'" in z],
          "; ".join(zeilen)[:110])

    # (3) Modus Verlauf mit leerem Feld: frueher entstand still die Last
    # „Kran gegen Nullzustand“ aus der gesperrten Auswahl
    m = hall()
    meldungen.clear()
    fl = neu(m, "")
    check("Modus Verlauf ohne Lastfälle: Meldung, keine Last",
          fl is None and not m.fatigue_loads and meldungen,
          "angelegt: " + (fl.bezug() if fl is not None else "-") + f"; {meldungen}")

    # (4) Anschluss K1: der Verlauf Null -> S -> Null ueber die Maske wie S gegen null
    m = hall()
    lc = m.add_load_case("Null", "Q", activate=False)
    lc.gravity = [0.0, 0.0, 0.0]
    e_kopf = m.members["Riegel"].elements[0]
    m.joints["K1"] = A.als_joint(propose("kopfplatte", m, e_kopf, end=0, N=-50e3,
                                         Vz=150e3, My=300e3), "K1")
    verlauf = neu(m, "Null, S, Null")
    m.add_fatigue_load("S-Null", "S", None, 5e5)
    m.add_fatigue_load("Kran-Null", "Kran", None, 5e5)
    an = solver.solve_all(m, design=True, fatigue=False)
    D = {}
    for name in (verlauf.name if verlauf is not None else "?", "S-Null", "Kran-Null"):
        m.joints["K1"].ermuedung = [name]
        D[name] = A.check_joints(m, an).joints["K1"].D
    dv = D.get(verlauf.name if verlauf is not None else "?", 0.0)
    check("Anschluss K1: Verlauf Null-S-Null über die Maske wie S gegen null",
          D["S-Null"] > 0 and abs(dv - D["S-Null"]) <= 1e-9 * D["S-Null"]
          and D["Kran-Null"] != D["S-Null"],
          f"D = {dv:.6g}, S gegen null {D['S-Null']:.6g}, Kran gegen null {D['Kran-Null']:.6g}")


def main():
    for t in (test_spanne, test_hauptspannungen, test_volumen, test_naht_beruehrung,
              test_kerbfall_vorschlaege,
              test_fehlender_mindestzustand_wird_gemeldet,
              test_mindestzustand_volumen_und_oder_ek,
              test_volumen_ohne_beitrag_und_unvollstaendig,
              test_unvollstaendig_je_weg, test_maske_verlauf_ohne_zustaende):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
