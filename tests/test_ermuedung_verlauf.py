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


def test_lastfall_umbenennen_zieht_ermuedungslasten_nach():
    """Nebenbefund NB3 (22./23.09.2026): ein umbenannter Lastfall hiess in
    den Ermuedungslasten weiter wie vorher.

    Die Oberflaeche (Register Lastfaelle, Tabelle „Lastfaelle“ unten, Maske
    rechts) benannte ihn nur in den Kombinationen um, nicht in case_max,
    case_min und den Gliedern eines Verlaufs; der Webserver (Operation
    edit_case) zog case_max/case_min nach, den Verlauf nicht. Danach meldete die
    Modellpruefung den alten Namen als „unbekannt“, und dem Nachweis fehlte
    die Last: gemessen am Stand ec6448c D = 0,018426 (Oberflaeche) bzw.
    1,236980 (Web) statt 2,437110, beide als unvollstaendig markiert.
    Geprueft werden alle vier Wege, die Oberflaeche mit ihren echten
    Methoden (self und Lastfallmaske als Attrappe). Richtig ist: dieselbe
    Schaedigung wie vor dem Umbenennen.
    """
    import importlib
    from unittest import mock
    # statik3d.gui.main als Modul - der Paketname "main" ist die Startfunktion
    G = importlib.import_module("statik3d.gui.main")
    from statik3d.web import OPS

    def bau():
        m = _kragarm()
        m.add_fatigue_load("Paar", "LF2", "LF3", cycles=1e5)
        m.fatigue_loads["Verlauf"] = FatigueLoad("Verlauf", folge=["LF1", "LF2", "LF3"],
                                                 wiederholungen=1e5)
        return m

    def schaedigung(m):
        an = solver.solve_all(m, design=False, fatigue=True)
        fm = an.fatigue.members["Kragarm"]
        return fm.util, list(getattr(fm, "fehlende_lasten", None) or [])

    D0, fehlt0 = schaedigung(bau())
    check("vor dem Umbenennen: Nachweis vollständig", D0 > 0 and not fehlt0,
          f"D = {D0:.6f}, fehlend {fehlt0}")

    class Lastfallmaske:
        """Attrappe der Maske Lastfall: LF2 heisst jetzt 'Nutzlast'."""
        def __init__(self, _fenster, lc, *_a, **_k):
            self.lc = lc

        def exec(self):
            return True

        def values(self):
            return ("Nutzlast", self.lc.category, self.lc.description,
                    self.lc.exclusive_group)

        def situation_name(self):
            return self.lc.situation

        def theorie_name(self):
            return self.lc.theorie

    def pruefen(weg, m):
        fl, vl = m.fatigue_loads["Paar"], m.fatigue_loads["Verlauf"]
        check(f"{weg}: der Lastfall heißt jetzt 'Nutzlast'",
              list(m.load_cases) == ["LF1", "Nutzlast", "LF3"], str(list(m.load_cases)))
        check(f"{weg}: oberer Zustand der Ermüdungslast umbenannt",
              fl.case_max == "Nutzlast" and fl.case_min == "LF3",
              f"{fl.case_max} gegen {fl.case_min}")
        check(f"{weg}: der Verlauf nennt den neuen Namen",
              vl.folge == ["LF1", "Nutzlast", "LF3"], str(vl.folge))
        unbekannt = [x for x in m.check() if "unbekannt" in x]
        check(f"{weg}: Modellprüfung meldet nichts „unbekannt“", not unbekannt,
              "; ".join(unbekannt)[:90])
        D, fehlt = schaedigung(m)
        check(f"{weg}: dieselbe Schädigung wie vor dem Umbenennen",
              not fehlt and abs(D - D0) <= 1e-12 * D0,
              f"D = {D:.6f} gegen {D0:.6f}, fehlend {fehlt}")

    # Drei Wege der Oberflaeche: Register Lastfaelle (edit_case), Doppelklick
    # in der Tabelle „Lastfaelle“ unten (lastfall_bearbeiten, einziger
    # Aufrufer ist tbl_lastfall.view.doubleClicked in _build_modelltabellen)
    # und die Maske rechts („Übernehmen“, _eigenschaften_uebernehmen). Der
    # Doppelklick im Modellbaum ist kein eigener Weg, er oeffnet die Maske
    # rechts - geprueft nach deren Weg. Bis zum 24.09.2026 stand hier
    # „Modellbaum“ fuer lastfall_bearbeiten (Gegenpruefung zu NB3).
    m = bau()
    m.active_case = "LF2"
    fenster = mock.MagicMock()
    fenster.model = m
    with mock.patch.object(G, "LoadCaseDialog", Lastfallmaske):
        G.MainWindow.edit_case(fenster)
    pruefen("Oberfläche, Register Lastfälle", m)
    check("Oberfläche: aktiver Lastfall folgt", m.active_case == "Nutzlast", m.active_case)

    m = bau()
    fenster = mock.MagicMock()
    fenster.model = m
    with mock.patch.object(G.dg, "LoadCaseDialog", Lastfallmaske):
        G.MainWindow.lastfall_bearbeiten(fenster, "LF2")
    pruefen("Oberfläche, Tabelle Lastfälle", m)

    m = bau()
    lc = m.load_cases["LF2"]
    fenster = mock.MagicMock()
    fenster.model = m
    G.MainWindow._eigenschaften_uebernehmen(
        fenster, "lastfall", "LF2",
        {"name": "Nutzlast", "kategorie": lc.category, "beschreibung": lc.description,
         "gruppe": lc.exclusive_group, "situation": "", "theorie": "", "grundlast": False,
         "nummer": lc.nummer, "g_z": str(lc.gravity[2] if len(lc.gravity) > 2 else 0.0),
         "psi": ""}, False)
    pruefen("Oberfläche, Objektmaske", m)
    # Der Doppelklick im Modellbaum fuehrt in dieselbe Maske (_baum_bearbeiten
    # -> _objektmaske), nicht nach lastfall_bearbeiten. Nur dann ist der Weg
    # ueber den Modellbaum mit dem der Maske oben mitgeprueft.
    fenster = mock.MagicMock()
    fenster.model = bau()
    G.MainWindow._baum_bearbeiten(fenster, "lastfall", "LF2")
    check("Oberfläche: Doppelklick im Modellbaum öffnet die Maske rechts",
          fenster._objektmaske.call_args_list == [mock.call("lastfall", "LF2")]
          and not fenster.lastfall_bearbeiten.called,
          f"_objektmaske {fenster._objektmaske.call_args_list}, "
          f"lastfall_bearbeiten {fenster.lastfall_bearbeiten.call_args_list}")

    m = bau()
    OPS["edit_case"](None, m, {"name": "LF2", "fields": {"new_name": "Nutzlast"}})
    pruefen("Web", m)

    # Der untere Zustand zieht ebenso nach
    m = bau()
    OPS["edit_case"](None, m, {"name": "LF3", "fields": {"new_name": "Wind"}})
    fl = m.fatigue_loads["Paar"]
    check("Web: unterer Zustand umbenannt, Verlauf auch",
          fl.case_min == "Wind" and m.fatigue_loads["Verlauf"].folge == ["LF1", "LF2", "Wind"],
          f"{fl.case_min}, {m.fatigue_loads['Verlauf'].folge}")


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


def _kragarm_volumen(netz):
    """Kragarm-Pruefkoerper (tests/pruefkoerper.Kragarm, hex8): Oberkante bei
    L/2, Breitenmitte, nach Saint-Venant 355 N/mm2. Der Koerper mit Kerbfall
    sind die Elemente mit x >= L/2 - das Moment faellt von dort zur Last hin,
    seine groesste Schwingbreite liegt also am Schnitt x = L/2. Eine
    Ermuedungslast 0 -> F (kein Mindestzustand): ihre Schwingbreite ist der
    statische Wert."""
    from statik3d.model import Volumenkoerper
    from tests import pruefkoerper as pk
    kr = pk.Kragarm()
    m, ids = kr.modell("hex8", *netz)
    rechts = [i for i, e in enumerate(m.elements) if m.nodes[e.nodes, 0].min() >= kr.x_nw - 1e-9]
    m.koerper["R"] = Volumenkoerper("R", [], material="S", elemente=rechts, kerbfall=160e6)
    lf = list(m.load_cases)[0]
    m.add_fatigue_load("0-F", lf, None, 1e5)
    nx, ny, nz = netz
    return m, kr, lf, rechts, ids[(nx // 2, ny // 2, nz)]


def _balken(kr, x, z):
    """sigma_xx des Kragarms nach der Balkenloesung (Saint-Venant) bei x in
    der Hoehe z: F (L - x) (z - H/2) / I."""
    return kr.F * (kr.L - x) * (z - kr.H / 2) / kr.I


def test_volumen_randspannung_kragarm():
    """Befund der ersten Element-Sitzung (23.09.2026): die Volumen-Ermuedung
    las den Elementwert (res.solid_res), der statische Nachweis seit dem
    22./23.09.2026 die geglaettete Randspannung (res.solid_knoten, an freien
    Oberflaechen sigma n = 0). Am Kragarm (Schwingbreite 0 -> F, Koerper
    x >= L/2) lag die groesste Schwingbreite nach der Elementregel bei
    314,35 N/mm2 (hex8 8x2x4) bzw. 333,31 (16x4x8) gegen 355 - 40,65 bzw.
    21,69 N/mm2 auf der unsicheren Seite (gemessen am Stand ec6448c,
    23.09.2026). Jetzt: je Knoten die Schwingbreite aus den geglaetteten
    Tensoren, auf 1 N/mm2 wie der statische Nachweis; die alte Regel bleibt
    waehlbar (DesignSettings.ermuedung_volumen = "element") und liefert die
    alten Zahlen; der Bericht nennt die gerechnete Regel.

    Dazu (Gegenpruefung 24.09.2026, Runde 4): wo der Elementwert liegt und
    was die Balkenloesung dort gibt, und die Koerperenden x >= 3L/8 und
    x >= L/4 - die Handbuecher nennen genau diese Zahlen.
    """
    from statik3d import assemble as asm
    from statik3d.elements import solid as sl
    gemessen = {}
    for netz in ((8, 2, 4), (16, 4, 8)):
        m, kr, lf, rechts, n = _kragarm_volumen(netz)
        an = solver.solve_all(m, design=False, fatigue=True)
        res = an.cases[lf]
        fv = an.fatigue.volumen["R"]
        g = m.design.gamma_Ff
        name = "hex8 %dx%dx%d" % netz
        # statisch: die geglaettete Knotenspannung des Loesers am Nachweispunkt
        sk = res.solid_knoten
        j = np.flatnonzero(np.asarray(sk["knoten"]) == n)
        S = np.asarray(sk["spannung"])[j[:1]]
        s_stat = float(F.signalspannung(S)[0]) if len(j) == 1 else float("nan")
        check(f"{name}: statisch am Nachweispunkt auf 1 N/mm2 (Hauptspannung, von Mises)",
              abs(s_stat - kr.sigma) < 1e6 and abs(sl.von_mises(S[0]) - kr.sigma) < 1e6,
              f"{s_stat / 1e6:.2f} / {sl.von_mises(S[0]) / 1e6:.2f} gegen {kr.sigma / 1e6:.1f} N/mm2")
        # Schwingbreite 0 -> F am selben Knoten: gleich dem statischen Wert
        orte = getattr(fv, "orte", None)
        d_je = getattr(fv, "dsig_je_ort", None)
        k = np.flatnonzero(np.asarray(orte) == n) if orte is not None else []
        d_n = float(np.asarray(d_je)[k[0]]) if len(k) == 1 else float("nan")
        check(f"{name}: Schwingbreite 0 -> F am Nachweispunkt = statischer Wert, auf 1 N/mm2",
              abs(d_n - g * s_stat) < 1e-9 * kr.sigma and abs(d_n - g * kr.sigma) < 1e6,
              f"{d_n / 1e6:.2f} N/mm2")
        check(f"{name}: groesste Schwingbreite des Koerpers auf 1 N/mm2 an der Balkenloesung",
              abs(fv.dsig_max - g * kr.sigma) < 1e6,
              f"{fv.dsig_max / 1e6:.2f} gegen {g * kr.sigma / 1e6:.1f} N/mm2")
        check(f"{name}: Regel 'knoten' gerechnet, massgebender Knoten benannt, D = n / N_R",
              getattr(fv, "regel", "") == "knoten" and getattr(fv, "knoten", -1) >= 0
              and fv.element in rechts
              and abs(fv.D - 1e5 / F.sn_life(fv.dsig_max, 160e6, fv.gamma_Mf)) < 1e-12 * fv.D,
              f"{getattr(fv, 'regel', None)} Knoten {getattr(fv, 'knoten', None)} D = {fv.D:.5f}")
        # Die alte Regel bleibt waehlbar - mit den alten Zahlen (Elementwert)
        alt = max(abs(float(F.signalspannung(np.asarray(res.solid_res[i])[None])[0])) for i in rechts) * g
        m.design.ermuedung_volumen = "element"
        fa = F.check_fatigue(m, an).volumen["R"]
        check(f"{name}: Regel 'element' liefert den Elementwert wie bisher",
              getattr(fa, "regel", "") == "element" and abs(fa.dsig_max - alt) < 1e-9 * alt
              and abs(fa.D - 1e5 / F.sn_life(alt, 160e6, fa.gamma_Mf)) < 1e-12 * fa.D
              and abs(alt - kr.sigma) > 20e6,
              f"{fa.dsig_max / 1e6:.2f} N/mm2 ({(fa.dsig_max - kr.sigma) / 1e6:+.2f})")
        gemessen[netz] = {"element": fa.dsig_max / g, "knoten": fv.dsig_max / g}
        # Wo der Elementwert liegt (Gegenpruefung 24.09.2026, Runde 4): der
        # Elementwert (solid_res) ist der Tensor an einem Auswertepunkt des
        # Elements. b4b545e verglich den der Elemente zur Einspannung mit dem
        # Soll bei L/2 und schrieb "46,94 N/mm2 zu viel" - ihr Auswertepunkt
        # liegt aber bei x = 3L/8 (8x2x4) bzw. 7L/16 (16x4x8), und dort gibt
        # die Balkenloesung mehr: gemessen 401,94 gegen 443,75 bzw. 377,61
        # gegen 399,38 N/mm2. Je Element am Nachweisknoten: der Auswertepunkt,
        # dessen Tensor gleich solid_res ist, und die Balkenloesung dort.
        ecken = np.asarray(sl.ECKEN_NATUERLICH["hex8"], float)
        mat = m.materials[m.elements[0].mat]
        u = np.asarray(res.u, float).reshape(-1)
        am_knoten = []
        for i, e in enumerate(m.elements):
            if n not in e.nodes:
                continue
            X = m.nodes[e.nodes]
            S9 = sl.spannungen_hex8_stapel(X[None], mat.E, mat.nu, u[asm.element_dofs(e, m)][None])[0]
            sr = np.asarray(res.solid_res[i], float)
            punkte = [q for q in range(len(S9)) if np.allclose(S9[q], sr, rtol=1e-10, atol=1e-3)]
            if not punkte:
                am_knoten.append((i, "?", float("nan"), float("nan"), float("nan")))
                continue
            p = np.asarray(sl.AUSWERTEPUNKTE["hex8"][punkte[0]], float)
            xp = (np.prod(1 + ecken * p[None], axis=1) / 8.0) @ X
            links = m.nodes[e.nodes, 0].max() <= kr.x_nw + 1e-9
            am_knoten.append((i, "Einspannseite" if links else "Lastseite", xp[0],
                              float(F.signalspannung(sr[None])[0]), _balken(kr, xp[0], xp[2])))
        check(f"{name}: Elementwerte am Nachweisknoten liegen an ihrem Auswertepunkt unter der "
              "Balkenlösung, auf beiden Seiten des Schnitts",
              len(am_knoten) == 4 and {s for _i, s, *_r in am_knoten} == {"Einspannseite", "Lastseite"}
              and all(s_el < b for _i, _s, _x, s_el, b in am_knoten),
              "; ".join(f"{s} x {x:.4f}: {s_el / 1e6:.2f} gegen {b / 1e6:.2f}"
                        for s, (x, s_el, b) in {s: (x, s_el, b) for _i, s, x, s_el, b
                                                in am_knoten}.items()) + " N/mm2")
        gemessen[netz]["einspannseite"] = next(
            ((s_el, b) for _i, s, _x, s_el, b in am_knoten if s == "Einspannseite"), None)
        # Andere Koerperenden (x >= 3L/8, x >= L/4): die Balkenloesung am
        # Koerperende ist die groesste Schwingbreite des Koerpers
        for x0 in (3 * kr.L / 8, kr.L / 4):
            m.koerper["R"].elemente = [i for i, e in enumerate(m.elements)
                                       if m.nodes[e.nodes, 0].min() >= x0 - 1e-9]
            w = {}
            for regel in ("element", "knoten"):
                m.design.ermuedung_volumen = regel
                w[regel] = F.check_fatigue(m, an).volumen["R"].dsig_max / g
            b = _balken(kr, x0, kr.H)
            gemessen[(netz, x0)] = w
            check(f"{name}, Körper x >= {x0:.3f}: Elementregel unter der Balkenlösung am Körperende, "
                  "Knotenregel näher daran",
                  w["element"] < b and abs(w["knoten"] - b) < abs(w["element"] - b),
                  f"Balken {b / 1e6:.2f}, Element {w['element'] / 1e6:.2f}, "
                  f"Knoten {w['knoten'] / 1e6:.2f} N/mm2")
        m.koerper["R"].elemente = rechts
        if netz != (8, 2, 4):
            continue
        # Der Bericht nennt die gerechnete Regel
        from statik3d.report.html import Report
        import tempfile
        texte = {}
        for regel in ("knoten", "element"):
            m.design.ermuedung_volumen = regel
            an.fatigue = F.check_fatigue(m, an)
            pfad_ = os.path.join(tempfile.mkdtemp(), f"kragarm_{regel}.html")
            Report(m, an).to_html(pfad_)
            texte[regel] = open(pfad_, encoding="utf-8").read()
        check("Bericht nennt die Regel: geglättete Knotenspannung bzw. Elementwert",
              "geglättete Knotenspannung" in texte["knoten"] and "Regel „knoten“" in texte["knoten"]
              and "Regel „element“" in texte["element"] and "Regel „knoten“" not in texte["element"])
    # Die Handbuecher nennen genau diese Messung: Theoriehandbuch 5.5-3 die
    # Tabelle der Koerperenden und den Elementwert der Einspannseite gegen
    # die Balkenloesung an seinem Auswertepunkt; der Satz aus b4b545e ("zu
    # viel", "haengt also daran, wo der Koerper endet") ist weg.
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(wurzel, "docs", "Theoriehandbuch.md"), encoding="utf-8") as fh:
        th = fh.read()
    with open(os.path.join(wurzel, "docs", "Benutzerhandbuch.md"), encoding="utf-8") as fh:
        bh = fh.read()

    def de(x):
        return f"{x / 1e6:.2f}".replace(".", ",")

    def mit_abw(x, b):
        return f"{de(x)} ({'+' if x >= b else '−'}{de(abs(x - b))})"

    fehlt = []
    for netz in ((8, 2, 4), (16, 4, 8)):
        for x0, w in [(kr.x_nw, gemessen.get(netz))] + [(x, gemessen.get((netz, x)))
                                                          for x in (3 * kr.L / 8, kr.L / 4)]:
            b = _balken(kr, x0, kr.H)
            for regel in ("element", "knoten"):
                t = mit_abw(w[regel], b) if w else "?"
                if t not in th:
                    fehlt.append(f"{netz} x0={x0:.3f} {regel}: {t}")
        es = gemessen.get(netz, {}).get("einspannseite")
        for t in ((de(es[0]), de(es[1])) if es else ("?",)):
            if t not in th:
                fehlt.append(f"{netz} Einspannseite: {t}")
    i = bh.find("**Ermüdung für Volumen.**")
    absatz = bh[i:bh.find("**Berührungsstellen zwischen Volumen.**", i)] if i >= 0 else ""
    check("Handbücher: Elementwert gegen die Balkenlösung an seinem Auswertepunkt und am "
          "Körperende, ohne 'zu viel' und ohne 'hängt daran, wo der Körper endet'",
          not fehlt and absatz and "zu viel" not in absatz and "46,94" not in absatz
          and "wo der Körper endet" not in absatz and "wo der Körper endet" not in th,
          f"fehlt im Theoriehandbuch: {fehlt}" if fehlt else "")


def test_volumen_regel_rueckfall_und_fliessen():
    """Die Grenzen der Regel "knoten": Ergebnisse ohne Knotenwerte (aus
    Programmfassungen vor dem 23.09.2026 - main bekam res.solid_knoten mit dem
    Merge 21ce779 am 23.09.2026) rechnen nach der alten Regel **mit Hinweis**,
    und der Hinweis nennt die Ursache, die vorliegt; eine unbekannte
    Einstellung fuehrt den Nachweis nicht; fliessende Elemente bleiben wie im
    statischen Nachweis von sigma n = 0 ausgenommen, und der Nachweis sagt es
    - mit dem, was ihre Knoten tragen (Gegenpruefung 23.09.2026, Maengel 3
    und 4: der Hinweis nannte "vor dem 22.09.2026" und "Kombination
    verschiedener Situationen", die Fliessmeldung "die Spannung des naechsten
    Integrationspunkts" - der Knoten traegt aber das Mittel, am Kragarm mit
    fy = 400 N/mm2 333,99 gegen 451,62 am Integrationspunkt)."""
    m, kr, lf, rechts, n = _kragarm_volumen((8, 2, 4))
    an = solver.solve_all(m, design=False, fatigue=True)
    alt = max(abs(float(F.signalspannung(np.asarray(an.cases[lf].solid_res[i])[None])[0]))
              for i in rechts) * m.design.gamma_Ff
    sk_voll = an.cases[lf].solid_knoten
    # (1) aeltere Ergebnisdatei: kein solid_knoten
    an.cases[lf].solid_knoten = {}
    fv = F.check_fatigue(m, an).volumen["R"]
    check("ohne Knotenwerte: alte Regel (Elementwert), gerechnet, mit Hinweis",
          getattr(fv, "regel", "") == "element" and not fv.fehler and abs(fv.dsig_max - alt) < 1e-9 * alt
          and any("Knotenwerte" in w and lf in w for w in fv.warnings),
          f"{getattr(fv, 'regel', None)} {fv.warnings}")
    check("ohne Knotenwerte: der Hinweis nennt den 23.09.2026, keine Situationen",
          any("23.09.2026" in w and "22.09.2026" not in w and "Situation" not in w
              for w in fv.warnings), str(fv.warnings))
    # (2) verworfene Ueberlagerung (Results.combine: Lastfaelle mit
    # verschiedenen Knotentabellen)
    an.cases[lf].solid_knoten = {"verworfen": True}
    fv = F.check_fatigue(m, an).volumen["R"]
    check("verworfene Knotenwerte: ebenso alte Regel mit Hinweis, der das Verwerfen nennt",
          getattr(fv, "regel", "") == "element" and any("Knotenwerte" in w for w in fv.warnings)
          and any("verworfen" in w and "Situation" not in w for w in fv.warnings),
          str(fv.warnings))
    # (2b) ein Ort fehlt, an dem ein Element des Koerpers wirkt: alte Regel,
    # der Hinweis nennt den Knoten und raet nicht "neu rechnen"
    weg = np.asarray(sk_voll["knoten"]) != n
    an.cases[lf].solid_knoten = {k: (np.asarray(v)[weg] if k in ("knoten", "gruppe", "spannung", "frei")
                                     else v) for k, v in sk_voll.items()}
    fv = F.check_fatigue(m, an).volumen["R"]
    check("fehlender Ort an einem wirkenden Element: alte Regel, Hinweis nennt den Knoten",
          getattr(fv, "regel", "") == "element" and abs(fv.dsig_max - alt) < 1e-9 * alt
          and any(f"Knoten {n + 1}" in w and "eu rechnen" not in w for w in fv.warnings),
          str(fv.warnings))
    an.cases[lf].solid_knoten = sk_voll
    # (3) unbekannte Einstellung: nicht geführt, Grund nennt die erlaubten Werte
    m.design.ermuedung_volumen = "irgendwas"
    fv = F.check_fatigue(m, an).volumen.get("R")
    check("unbekannte Einstellung: nicht geführt, keine stille Ersatzregel",
          fv is not None and fv.status() == "nicht geführt" and "irgendwas" in fv.fehler
          and "knoten" in fv.fehler and "element" in fv.fehler,
          repr(getattr(fv, "fehler", None)))
    # (4) fliessende Elemente: Balken aus einer hex8-Lage, reine Biegung
    # 1,20 M_el (wie tests/test_volumen.py, test_randspannung_fliessend)
    from statik3d import plastizitaet as pl
    from statik3d.model import Volumenkoerper
    from tests import pruefkoerper as pk
    fy, b, h, L = 235e6, 0.2, 0.2, 1.0
    M = 1.2 * fy * b * h ** 2 / 6.0
    mp, _ids = pk.quader("hex8", 5, 1, 1, L, b, h, fy=fy)
    for k in [x for x in range(mp.nn) if abs(mp.nodes[x, 0]) < 1e-9]:
        mp.fix(int(k), "all")
    seiten = pk.randseiten(mp, lambda X: bool(np.all(np.abs(X[:, 0] - L) < 1e-9)))
    pk.spannung_auf_seiten(mp, seiten, lambda x: (M * (x[2] - h / 2) / (b * h ** 3 / 12), 0.0, 0.0))
    mp.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=1, iterationen=30,
                                      toleranz=1e-9)
    mp.koerper["B"] = Volumenkoerper("B", [], material="S", elemente=list(range(len(mp.elements))),
                                     kerbfall=160e6)
    lfp = list(mp.load_cases)[0]
    mp.add_fatigue_load("0-M", lfp, None, 1e5)
    anp = solver.solve_all(mp, design=False, fatigue=True)
    fliessend = len(anp.cases[lfp].info.get("plastisch") or {})
    fv = anp.fatigue.volumen["B"]
    check("fließende Elemente: Meldung nennt Zustand und Zahl, Nachweis gerechnet",
          fliessend > 0 and getattr(fv, "regel", "") == "knoten" and not fv.fehler
          and any("fließen" in w and lfp in w and f"{fliessend} " in w for w in fv.warnings),
          f"{fliessend} fließend, {fv.warnings}")
    check("fließend: die Meldung sagt, dass der Knoten das Mittel trägt (Beitrag des nächsten "
          "Integrationspunkts)",
          any("Knotenmittel" in w and "nächsten Integrationspunkts bei" in w
              and "tragen die Spannung des nächsten" not in w for w in fv.warnings),
          str(fv.warnings))
    sk = anp.cases[lfp].solid_knoten
    kn = np.asarray(sk["knoten"])
    orte = getattr(fv, "orte", None)
    d_je = getattr(fv, "dsig_je_ort", None)
    soll = np.abs(F.signalspannung(np.asarray(sk["spannung"]))) * mp.design.gamma_Ff
    gleich = (orte is not None and d_je is not None and np.array_equal(np.asarray(orte), kn)
              and np.allclose(np.asarray(d_je), soll, rtol=1e-12, atol=1e-3))
    check("fließend: die Schwingbreite ist die Knotenspannung des Lösers (dort ohne σ·n = 0)", gleich,
          f"{0 if orte is None else len(orte)} Orte / {len(kn)} Knoten")


def test_volumen_abgeschaltete_elemente():
    """Gegenpruefung 23.09.2026 (Maengel 2 und 3): ein frisch gerechnetes
    Ergebnis in einer Situation mit abgeschalteten Elementen des Koerpers
    fuehrt die Knoten nicht, an denen nur abgeschaltete Elemente liegen. Die
    Regel "knoten" fiel darauf fuer den ganzen Koerper auf den Elementwert
    zurueck, mit einem Hinweis, der eine alte Ergebnisdatei oder eine
    Kombination verschiedener Situationen als Ursache nannte und "neu
    rechnen" riet - am Kragarm 8x2x4 mit abgeschaltetem Eckelement stand nach
    beiden Laeufen Regel 'element', 1141,55 N/mm2, derselbe Hinweis. Der
    statische Nachweis las am selben Ergebnis die geglaettete Spannung.

    Jetzt: ein Ort, an dem im Zustand kein Element des Koerpers wirkt, traegt
    dort die Spannung 0 - wie das abgeschaltete Element nach der Elementregel
    (solver.postprocess gibt ihm Nullen) -, jeder andere die geglaettete
    Spannung des Loesers, dieselbe wie der statische Nachweis."""
    from statik3d.model import Situation, Volumenkoerper
    from tests import pruefkoerper as pk
    kr = pk.Kragarm()
    m, ids = kr.modell("hex8", 8, 2, 4)
    ecke = ids[(0, 0, 0)]
    e0 = next(i for i, e in enumerate(m.elements) if ecke in e.nodes)
    m.situationen["S1"] = Situation("S1", "", [e0], "Ecke aus")
    lf = list(m.load_cases)[0]
    m.load_cases[lf].situation = "S1"
    m.koerper["K"] = Volumenkoerper("K", [], material="S", elemente=list(range(len(m.elements))),
                                    kerbfall=160e6)
    # ein zweiter Lastfall in der Grundstellung: die halbe Last
    m.add_load_case("LF2", "Q")
    m.active_case = "LF2"
    seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - kr.L) < 1e-9)))
    pk.schubkraft_auf_seiten(m, seiten, 0.5 * kr.F, (0.0, 0.0, -1.0))
    m.add_fatigue_load("0-F", lf, None, 1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    g = m.design.gamma_Ff

    def signal_je_ort(res, orte):
        sk = res.solid_knoten
        wo = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
        S = np.asarray(sk["spannung"])
        return np.array([float(F.signalspannung(S[wo[int(o)]][None])[0]) if int(o) in wo else 0.0
                         for o in orte])

    r1, r2 = an.cases[lf], an.cases["LF2"]
    fehlt = ecke not in set(np.asarray(r1.solid_knoten["knoten"]).tolist())
    fv = an.fatigue.volumen["K"]
    orte = getattr(fv, "orte", None)
    check("abgeschaltetes Eckelement: der Loeser fuehrt seinen Eckknoten nicht (Voraussetzung)",
          fehlt and r1.info.get("inaktiv") == [e0], f"inaktiv {r1.info.get('inaktiv')}")
    check("abgeschaltetes Element: Regel 'knoten' ohne Rueckfall-Hinweis",
          getattr(fv, "regel", "") == "knoten" and orte is not None
          and not any("Knotenwerte" in w for w in fv.warnings),
          f"{getattr(fv, 'regel', None)} {fv.warnings}")
    orte = np.asarray(orte) if orte is not None else np.zeros(0, int)
    d_je = np.asarray(fv.dsig_je_ort) if fv.dsig_je_ort is not None else np.zeros(0)
    soll = np.abs(signal_je_ort(r1, orte)) * g
    k0 = np.flatnonzero(orte == ecke)
    check("0 -> F: je Ort die Knotenspannung des Loesers, am Ort ohne wirkendes Element 0",
          len(orte) > 0 and np.allclose(d_je, soll, rtol=1e-12, atol=1e-3) and len(k0) == 1
          and d_je[k0[0]] == 0.0 and abs(fv.dsig_max - soll.max()) <= 1e-12 * soll.max(),
          f"max {fv.dsig_max / 1e6:.2f} N/mm2, am Eckknoten {d_je[k0[0]] if len(k0) else None}")
    # Schwingbreite zwischen zwei Situationen: LF1 (Eckelement aus) und LF2
    m.fatigue_loads.clear()
    m.add_fatigue_load("LF1-LF2", lf, "LF2", 1e5)
    fv = F.check_fatigue(m, an).volumen["K"]
    orte = np.asarray(fv.orte) if getattr(fv, "orte", None) is not None else np.zeros(0, int)
    soll = np.abs(signal_je_ort(r2, orte) - signal_je_ort(r1, orte)) * g
    k0 = np.flatnonzero(orte == ecke)
    s_ecke = abs(float(signal_je_ort(r2, [ecke])[0])) * g
    check("zwei Situationen: je Ort |sigma(LF2) - sigma(LF1)|, am Eckknoten |sigma(LF2) - 0|",
          getattr(fv, "regel", "") == "knoten" and len(orte) > 0
          and np.allclose(np.asarray(fv.dsig_je_ort), soll, rtol=1e-12, atol=1e-3)
          and len(k0) == 1 and abs(fv.dsig_je_ort[k0[0]] - s_ecke) <= 1e-12 * s_ecke and s_ecke > 0,
          f"{getattr(fv, 'regel', None)}, Eckknoten {s_ecke / 1e6:.2f} N/mm2, {fv.warnings}")


def test_volumen_ergebnis_aelterer_fassung():
    """Gegenpruefung 24.09.2026, Runde 4 (Mangel 1): ein Ermuedungsergebnis,
    das eine Programmfassung ohne die Einstellung ermuedung_volumen (vor
    a4ec83f) gerechnet und in die Ergebnisdatei geschrieben hat, kennt das
    Feld 'regel' nicht - Pickle stellt nur das __dict__ her, getattr liest
    die Klassenvorgabe "element". Der Bericht schrieb dann "Gerechnet mit der
    Einstellung ermuedung_volumen = „element“ oder - mit Hinweis am Koerper -
    weil dem Ergebnis die Knotenwerte fehlen"; beides stimmte nicht (gemessen
    mit einer Ergebnisdatei von ec6448c, Kragarm 8x2x4, Koerper x >= L/2:
    Einstellung des geladenen Modells 'knoten', keine Hinweise, Element 12,
    314,3 N/mm2). Nachgebildet: das Ergebnis nach der Elementregel ohne die
    vier Felder, die a4ec83f dazubrachte, durch die Ergebnisdatei geschrieben
    und gelesen - ohne Neurechnung, wie beim Oeffnen in der Oberflaeche."""
    import re
    import tempfile
    from statik3d import ergebnisse
    from statik3d.report.html import Report
    m, kr, lf, rechts, n = _kragarm_volumen((8, 2, 4))
    m.design.ermuedung_volumen = "element"
    an = solver.solve_all(m, design=False, fatigue=True)
    fv = an.fatigue.volumen["R"]
    for feld in ("regel", "knoten", "orte", "dsig_je_ort"):
        vars(fv).pop(feld, None)
    m.design.ermuedung_volumen = "knoten"
    ordner = tempfile.mkdtemp()
    pfad = os.path.join(ordner, "alt.ergebnisse")
    ergebnisse.schreiben(pfad, m, an)
    an2 = ergebnisse.lesen(pfad, m)
    fv2 = an2.fatigue.volumen["R"]
    check("ältere Fassung nachgebildet: 'regel' fehlt nach dem Lesen, keine Hinweise",
          "regel" not in vars(fv2) and fv2.regel == "element" and fv2.warnings == []
          and fv2.element in rechts, f"{sorted(vars(fv2))[:4]} … Element {fv2.element}")

    def bericht(a, name):
        p = os.path.join(ordner, name)
        Report(m, a).to_html(p)
        with open(p, encoding="utf-8") as fh:
            t = re.sub(r"<[^>]+>", " ", fh.read())
        return re.sub(r"\s+", " ", t)

    t = bericht(an2, "alt.html")
    # der Block im Text (das Inhaltsverzeichnis fuehrt die Ueberschrift ohne &nbsp;)
    i = t.find("&nbsp;Ermüdungsnachweis Volumen")
    block = t[i:t.find("&nbsp;Anschlüsse nach DIN EN 1993-1-8", i)] if i >= 0 else ""
    check("ältere Fassung: der Bericht nennt weder die Einstellung „element“ noch fehlende "
          "Knotenwerte als Grund",
          block and "Gerechnet mit der Einstellung ermuedung_volumen" not in block
          and "Knotenwerte fehlen" not in block, block[:160])
    check("ältere Fassung: der Bericht sagt, woher das Ergebnis kommt und was neu gerechnet gilt",
          "älteren Programmfassung" in block and "nicht neu gerechnet" in block
          and "ermuedung_volumen = „knoten“" in block
          and f"Element {fv2.element}" in block and "314.3" in block, block[:400])
    zus = t[t.rfind("Zusammenfassung"):]
    check("ältere Fassung: Hinweis auch in der Zusammenfassung",
          "Ermüdung Volumen R" in zus and "älteren Programmfassung" in zus, zus[:300])
    # Gegenprobe: ein neu gerechnetes Ergebnis nach der Regel "element"
    m.design.ermuedung_volumen = "element"
    an2.fatigue = F.check_fatigue(m, an2)
    t = bericht(an2, "neu.html")
    check("neu gerechnet nach „element“: der Bericht nennt die Einstellung, keine ältere Fassung",
          "Gerechnet mit der Einstellung ermuedung_volumen = „element“" in t
          and "älteren Programmfassung" not in t)
    m.design.ermuedung_volumen = "knoten"


def main():
    for t in (test_spanne, test_hauptspannungen, test_volumen, test_naht_beruehrung,
              test_kerbfall_vorschlaege,
              test_fehlender_mindestzustand_wird_gemeldet,
              test_lastfall_umbenennen_zieht_ermuedungslasten_nach,
              test_mindestzustand_volumen_und_oder_ek,
              test_volumen_ohne_beitrag_und_unvollstaendig,
              test_unvollstaendig_je_weg,
              test_volumen_randspannung_kragarm,
              test_volumen_regel_rueckfall_und_fliessen,
              test_volumen_abgeschaltete_elemente,
              test_volumen_ergebnis_aelterer_fassung):
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
