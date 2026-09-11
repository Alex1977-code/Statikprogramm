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


def main():
    for t in (test_spanne, test_hauptspannungen, test_volumen, test_kerbfall_vorschlaege):
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
