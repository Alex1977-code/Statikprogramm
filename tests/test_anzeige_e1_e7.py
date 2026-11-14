"""
Befundliste vom 14.11.2026, Gruppe B, E1 bis E7: Anzeige und Eingabe in der
eingestellten Einheit (vom Anwender am 14.11.2026 zur Behebung freigegeben).

E1  Browser-Oberflaeche, Antriebsmoment einer Stellung: das Formular schickte
    kNm ohne Umrechnung (40 kNm kamen als 40 Nm an), der Server zog von der
    Knotennummer 1 ab (Auswahl zaehlt ab 0: Knoten 8 wurde 7, Knoten 0 wurde -1).
E2  Verformungsnachweis Art „Stab“ mit phix/phiy/phiz verglich eine
    Durchbiegung (0,00 „mrad“ erfuellt statt 10,32 mrad nicht erfuellt).
    Anwenderentscheidung: fuer „Stab“ abweisen, aeltere Dateien melden.
E3  Register Lager: die Federsteifigkeit [Kraft/Laenge] galt auch fuer die
    Drehfreiheitsgrade (10 bei mm -> 10 000 kNm/rad). Jetzt ein eigenes Feld
    in {moment}/rad.
E4  Einheiten.zahl schnitt bei 0 Nachkommastellen Nullen ab (-100 kN als „1 kN“).
E5  Beschriftung Vorspannung: „P₀ 250, Δs 2,00 mm kN“.
E6  Tabellen „Lasten“ und „Umhüllende“ ohne Einheit und unabhaengig von der Einstellung.
E7  Wissenschaftliche Schreibweise im Bericht (Verlauf, Reynoldszahl), im
    Windprotokoll und unter der Farbskala.

Keine Hauptfenster: reine Funktionen, einzelne Widgets (offscreen) und die
Fuellfunktionen der Tabellen an einem Ersatzobjekt.

Aufruf:  python -m tests.test_anzeige_e1_e7
"""
import math
import os
import re
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

RESULTS = []
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _wiss(text) -> bool:
    """Steht eine Zahl in wissenschaftlicher Schreibweise im Text?"""
    return bool(re.search(r"\d[eE][+-]?\d", str(text)))


def _kragarm():
    """Kragarm HEA 200, L = 4 m, 8 Elemente, Knoten 0 eingespannt, Fz = -10 kN am Ende."""
    from statik3d.model import Model, Material
    from statik3d import profiles, mesher
    m = Model("Kragarm")
    m.add_material(Material.steel("S355"))
    sec = profiles.make_section("HEA 200")
    m.add_section(sec)
    mesher.line_of_beams(m, list(m.materials)[0], sec.name, (0, 0, 0), (4, 0, 0), 8)
    m.auto_members()
    m.add_load_case("LF1", "G")
    m.fix(0, "all")
    m.load_node(8, Fz=-10e3, case="LF1")
    m.add_combination("LK1", {"LF1": 1.0}, typ="SLS_CH")
    return m, sec


# ---------------------------------------------------------------------------
# E1
# ---------------------------------------------------------------------------
def test_e1_antrieb_browser():
    from statik3d.model import Model
    from statik3d.web import server as sv
    js = open(os.path.join(WURZEL, "statik3d", "web", "static", "app.js"), encoding="utf-8").read()
    for k in ("mx", "my", "mz"):
        tr = re.search(r"num\('antrieb_%s',[^)]*\{[^}]*scale:\s*1e3" % k, js)
        check(f"E1 app.js: Feld antrieb_{k} [kNm] rechnet mit data-scale 1e3 in Nm um", tr is not None)
    m = Model("x")
    for i in range(9):
        m.add_node(0.5 * i, 0, 0)
    # was der Browser nach data-scale schickt: 40 kNm -> 40 000 Nm, Knoten 8 aus der Auswahl
    st = types.SimpleNamespace()
    sv._op_stellung(st, m, {"name": "S1", "antrieb_knoten": "8", "antrieb_my": 40e3})
    a = st.stellungen[0].antrieb
    # zweiter Weg Knoten: die Knotenlast des Browsers mit derselben Auswahl „8“
    from statik3d.web.server import _op_nodal_load
    m.add_load_case("LF1", "G")
    _op_nodal_load(None, m, {"case": "LF1", "nodes": "8", "F": [0, 0, -1.0, 0, 0, 0]})
    kn_last = int(m.load_cases["LF1"].nodal_loads[-1].node)
    check("E1 Browser: Knoten 8 bleibt Knoten 8 (Zählung ab 0 wie Auswahl und Knotenlast)",
          a is not None and a[0] == 8 == kn_last, f"Stellung {a}, Knotenlast an {kn_last}")
    # zweiter Weg Moment: der Dialog der Arbeitsplatzoberflaeche mit 40 kNm (der zaehlt
    # seine Knoten ab 1 - Nebenbefund 14.11.2026 -, darum dort 9 fuer den Knoten 8)
    _app()
    from statik3d.gui.dialogs import StellungDialog
    dlg = StellungDialog(None, None, m)
    dlg.ed_name.setText("S1")
    dlg.ed_knoten.setzen(9)
    dlg.ed_moment[1].setzen(40.0)
    b = dlg.stellung().antrieb
    dlg.deleteLater()
    check("E1 Browser: 40 kNm kommen als 40 000 Nm an, wie im Dialog des Arbeitsplatzes",
          a is not None and b is not None and a[0] == b[0]
          and np.allclose(list(a[1]), [0.0, 40e3, 0.0]) and np.allclose(list(b[1]), list(a[1])),
          f"Browser {a}, Dialog {b}")
    st2 = types.SimpleNamespace()
    sv._op_stellung(st2, m, {"name": "S0", "antrieb_knoten": "0", "antrieb_my": 1e3})
    check("E1 Browser: Knoten 0 bleibt Knoten 0 (bisher -1)", st2.stellungen[0].antrieb[0] == 0,
          str(st2.stellungen[0].antrieb))
    st3 = types.SimpleNamespace()
    try:
        sv._op_stellung(st3, m, {"name": "S9", "antrieb_knoten": "9", "antrieb_my": 1e3})
        ok, text = False, f"angenommen: {st3.stellungen[0].antrieb}"
    except sv.ApiError as ex:
        ok, text = "existier" in str(ex), str(ex)
    check("E1 Browser: ein Knoten, den es nicht gibt, wird abgewiesen", ok, text)


# ---------------------------------------------------------------------------
# E2
# ---------------------------------------------------------------------------
def test_e2_stab_ohne_verdrehung():
    from statik3d import solver, gzg
    from statik3d.model import Model, Verformungsgrenze
    m, sec = _kragarm()
    stab = list(m.members)[0]
    for g in ("phix", "phiy", "phiz"):
        try:
            m.add_verformungsgrenze(f"G_{g}", "stab", stab=stab, groesse=g, grenzart="absolut",
                                    wert=0.010, situation="SLS_CH")
            ok, text = False, "angenommen"
        except ValueError as ex:
            ok, text = "Knotennachweis" in str(ex) and g in str(ex), str(ex)
        check(f"E2 add_verformungsgrenze: Art „Stab“ mit {g} wird mit Klartext abgewiesen", ok, text[:150])
    m.add_verformungsgrenze("G_uz", "stab", stab=stab, groesse="uz", grenzart="L/x", wert=300,
                            situation="SLS_CH")
    m.add_verformungsgrenze("G_knoten_phiy", "knoten", knoten=[8], groesse="phiy", grenzart="absolut",
                            wert=0.010, situation="SLS_CH")
    check("E2 … „Stab“ mit uz und „Knoten“ mit phiy bleiben möglich",
          {"G_uz", "G_knoten_phiy"} <= set(m.verformungsgrenzen))

    # Dialog: fuer „Stab“ keine Verdrehungen in der Auswahl
    _app()
    from statik3d.gui.dialogs import VerformungsgrenzeDialog
    d = VerformungsgrenzeDialog(None, m)
    d.cb_art.setCurrentIndex(d.cb_art.findData("stab"))
    stab_g = [d.cb_groesse.itemData(i) for i in range(d.cb_groesse.count())]
    d.cb_art.setCurrentIndex(d.cb_art.findData("knoten"))
    knoten_g = [d.cb_groesse.itemData(i) for i in range(d.cb_groesse.count())]
    d.deleteLater()
    check("E2 Dialog: bei „Stab“ keine φ-Größe in der Auswahl, bei „Knoten“ alle drei",
          not any(str(g).startswith("phi") for g in stab_g) and "uz" in stab_g
          and {"phix", "phiy", "phiz"} <= set(knoten_g), f"Stab {stab_g}, Knoten {knoten_g}")

    # aeltere Datei mit einem solchen Eintrag (am add_verformungsgrenze vorbei)
    m.verformungsgrenzen["G_alt_phiy"] = Verformungsgrenze("G_alt_phiy", "stab", stab=stab, groesse="phiy",
                                                           grenzart="absolut", wert=0.010,
                                                           situation="SLS_CH")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "alt.s3d")
        m.save(p)
        m2 = Model.load(p)
    hinw = [h for h in getattr(m2, "_ladehinweise", []) if "G_alt_phiy" in h]
    check("E2 Öffnen einer älteren Datei: Hinweis, den Nachweis als Knotennachweis anzulegen",
          len(hinw) == 1 and "Knotennachweis" in hinw[0], str(hinw)[:200])
    check("E2 … der Eintrag bleibt in der Datei stehen (nichts still gelöscht)",
          "G_alt_phiy" in m2.verformungsgrenzen)
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("gzg_stab_verdrehung")
    ohne = Model("ohne")
    check("E2 Verfahrenstabelle: Merkmal „gzg_stab_verdrehung“, Stand 47, Fehlerkorrektur, betrifft nur "
          "Modelle mit einem solchen Nachweis",
          mk is not None and mk.wechsel[-1].stand == 47 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 47 and mk.betrifft(m2) and not mk.betrifft(ohne),
          f"{mk and mk.wechsel}, Verfahrensstand {rv.VERFAHRENSSTAND}")

    an = solver.solve_all(m2, progress=lambda *a: None, design=False)
    res = gzg.check_verformung(m2, an)
    alt = res.checks["G_alt_phiy"]
    check("E2 Nachweis „Stab“ mit phiy: „nicht geführt“ statt „erfüllt“ mit 0,00 mrad",
          alt.status() == "nicht geführt" and "Knotennachweis" in alt.fehler, f"{alt.status()}: {alt.fehler}")
    # zwei Wege: Knotennachweis im Programm und Hand F L² / (2 E I)
    EI = 210e9 * sec.Iy
    hand = 10e3 * 4.0 ** 2 / (2 * EI)
    kn = res.checks["G_knoten_phiy"]
    check("E2 … als Knotennachweis: φy = 10,32 mrad (Hand F L²/(2EI) = 10,318), „NICHT erfüllt“",
          abs(kn.wert - hand) < 1e-3 * hand and kn.status() == "NICHT erfüllt",
          f"Programm {kn.wert * 1e3:.3f} mrad, Hand {hand * 1e3:.3f} mrad, {kn.status()}")


# ---------------------------------------------------------------------------
# E3
# ---------------------------------------------------------------------------
def _lager_setzen(laenge, k_text, kr_text, **art):
    """MainWindow.set_support an einem Ersatzobjekt mit den echten Zahlenfeldern."""
    _app()
    from PySide6 import QtWidgets
    from statik3d import einheiten as eh
    from statik3d.model import Model
    from statik3d.gui import main as gm
    from statik3d.gui.dialogs import NumEdit
    E = eh.Einheiten(laenge=laenge)
    m = Model("x")
    m.add_node(0, 0, 0)
    m.einheiten = E
    k = NumEdit(0.0, 90)
    k.einheit_binden("strecke", lambda: E)
    k.setText(k_text)
    kr = NumEdit(0.0, 90)
    kr.einheit_binden("drehfeder", lambda: E)
    kr.setText(kr_text)
    haken = [QtWidgets.QCheckBox(n) for n in ("ux", "uy", "uz", "phix", "phiy", "phiz")]
    for i in art.pop("haken", []):
        haken[i].setChecked(True)
    fehler = []
    dummy = types.SimpleNamespace(model=m, selection=[0], ed_spring=k, ed_drehfeder=kr, cb_dof=haken,
                                  _zahlmeldung=lambda t: fehler.append(t), merken=lambda *a: None,
                                  refresh_all=lambda: None, error=lambda t: fehler.append(t))
    gm.MainWindow.set_support(dummy, **art)
    return m, fehler


def test_e3_drehfeder():
    from statik3d import einheiten as eh
    for laenge, soll in (("m", "kNm/rad"), ("cm", "kNcm/rad"), ("mm", "kNmm/rad")):
        E = eh.Einheiten(laenge=laenge)
        check(f"E3 Einheit der Drehfeder bei Länge {laenge}: {soll}, Faktor wie das Moment",
              E.einheit("drehfeder") == soll and E.faktor("drehfeder") == E.faktor("moment"),
              f"{E.einheit('drehfeder')} {E.faktor('drehfeder')}")
    for laenge, k_si, kr_si in (("m", 1e4, 1e4), ("mm", 1e7, 10.0)):
        m, f = _lager_setzen(laenge, "10", "10", all_dofs=True)
        s = m.supports[0].stiffness if m.supports else None
        soll = [k_si] * 3 + [kr_si] * 3
        check(f"E3 Einspannung bei Länge {laenge}: 10 kN/{laenge} und 10 kN{laenge}/rad -> "
              f"{k_si:g} N/m und {kr_si:g} Nm/rad",
              s is not None and np.allclose(s, soll), f"{s} statt {soll} {f}")
    # zweiter Weg: der Dialog „Nichtlinearitaet“ zeigt in kN/m und kNm/rad
    from statik3d.gui.dialogs import SupportNonlinearDialog
    m, _ = _lager_setzen("mm", "10", "10", all_dofs=True)
    d = SupportNonlinearDialog(None, m.supports[0])
    ux = float(d.rows[0][1].text().replace(" ", "").replace(",", "."))
    phix = float(d.rows[3][1].text().replace(" ", "").replace(",", "."))
    d.deleteLater()
    check("E3 … Dialog Nichtlinearität: ux 10 000 kN/m, φx 0,01 kNm/rad (10 kNmm = 0,01 kNm)",
          abs(ux - 1e4) < 1e-6 and abs(phix - 0.01) < 1e-9, f"ux {ux}, phix {phix}")
    m, _ = _lager_setzen("mm", "10", "10", pinned=True)
    check("E3 Gelenkig: nur die Wegfeder, die Drehfeder bleibt außen vor",
          m.supports[0].dofs == [0, 1, 2] and np.allclose(m.supports[0].stiffness, [1e7] * 3),
          str(m.supports[0].stiffness))
    m, _ = _lager_setzen("m", "0", "25", haken=[3, 4, 5])
    check("E3 nur Drehungen angehakt: 25 kNm/rad -> 25 000 Nm/rad",
          m.supports[0].dofs == [3, 4, 5] and np.allclose(m.supports[0].stiffness, [25e3] * 3),
          str(m.supports[0].stiffness))
    m, _ = _lager_setzen("m", "5", "0", all_dofs=True)
    check("E3 Wegfeder ohne Drehfeder: Drehungen starr (0 heißt starr)",
          np.allclose(m.supports[0].stiffness, [5e3] * 3 + [0.0] * 3)
          and m.supports[0].dof_behaviour(4).typ == "rigid", str(m.supports[0].stiffness))
    m, _ = _lager_setzen("m", "0", "0", all_dofs=True)
    check("E3 beides 0: starres Lager wie bisher", m.supports[0].stiffness is None, str(m.supports[0].stiffness))


# ---------------------------------------------------------------------------
# E4
# ---------------------------------------------------------------------------
class _Plotter:
    def __init__(self):
        self.zeilen = []

    def add_point_labels(self, pts, zeilen, **k):
        self.zeilen.extend(zeilen)

    def __getattr__(self, n):
        return lambda *a, **k: None


def test_e4_zahl_ohne_nachkomma():
    from statik3d import einheiten as eh
    e = eh.Einheiten(nk_last=0, nk_verformung=0)
    for wert, art, soll in ((10e3, "kraft", "10"), (100e3, "kraft", "100"), (20e3, "strecke", "20"),
                            (5e3, "flaechenlast", "5"), (0.010, "zwang", "10"), (0.0, "kraft", "0")):
        z = e.zahl(wert, art, 0)
        # zweiter Weg: Einheiten.text ohne Einheit
        t = e.text(wert, art, 0, mit_einheit=False)
        check(f"E4 zahl({wert:g} {art}, 0 Nachkommastellen) = „{soll}“ wie text", z == soll == t, f"{z!r} / {t!r}")
    e2 = eh.Einheiten()
    for wert, soll in ((10e3, "10"), (12.5e3, "12.5"), (100e3, "100"), (0.25e3, "0.25")):
        z = e2.zahl(wert, "kraft", 2)
        check(f"E4 zahl({wert:g} N, 2 Nachkommastellen) = „{soll}“ (Nullen hinter dem Komma fallen weiter)",
              z == soll, repr(z))
    from statik3d.model import Model, Material
    from statik3d import profiles, mesher
    from statik3d.gui import viewport as vp
    m = Model("x")
    m.add_material(Material.steel("S355"))
    sec = profiles.make_section("HEA 200")
    m.add_section(sec)
    mesher.line_of_beams(m, list(m.materials)[0], sec.name, (0, 0, 0), (4, 0, 0), 2)
    m.add_load_case("LF1", "G")
    m.load_node(2, Fz=-10e3, case="LF1")
    m.load_node(1, Fz=-100e3, case="LF1")
    m.load_beam(0, qz=-20e3, case="LF1")
    m.einheiten = e
    p = _Plotter()
    vp.add_loads(p, m, m.load_cases["LF1"], 10.0, beschriften=True, einheiten=e, merker=[])
    check("E4 Ansicht bei 0 Nachkommastellen: 10 kN, 100 kN, 20 kN/m (bisher 1 kN, 1 kN, 2 kN/m)",
          sorted(p.zeilen) == sorted(["10 kN", "100 kN", "20 kN/m"]), str(p.zeilen))


# ---------------------------------------------------------------------------
# E5
# ---------------------------------------------------------------------------
def test_e5_beschriftung_vorspannung():
    from statik3d.model import Model, Material
    from statik3d import profiles, mesher, einheiten as eh
    from statik3d.gui import viewport as vp
    m = Model("V")
    m.add_material(Material.steel("S355"))
    sec = profiles.make_section("HEA 200")
    m.add_section(sec)
    m.add_load_case("LF1", "G")
    mesher.line_of_beams(m, list(m.materials)[0], sec.name, (0, 0, 0), (4, 0, 0), 2)
    m.auto_members()
    stab = list(m.members)[0]
    m.add_vorspannung(stab, 250e3, case="LF1", sollkraft=True, kraftart="presse", schlupf=0.002)
    for name, e, soll in (("Vorgabe kN, mm", eh.Einheiten(), "P₀ 250 kN, Δs 2,00 mm"),
                          ("N, mm, Verformung cm", eh.Einheiten(kraft="N", laenge="mm", verformung="cm"),
                           "P₀ 250000 N, Δs 0,20 cm")):
        m.einheiten = e
        p = _Plotter()
        vp.add_loads(p, m, m.load_cases["LF1"], 10.0, beschriften=True, einheiten=e, merker=[])
        # zweiter Weg: Einheiten.text fuer Kraft und Verformung
        weg2 = (f"P₀ {e.zahl(250e3, 'kraft', e.nk_last)} {e.einheit('kraft')}, "
                f"Δs {e.text(0.002, 'verformung')}").replace(".", ",")
        check(f"E5 Beschriftung Vorspannung [{name}]: „{soll}“",
              soll in p.zeilen and weg2 == soll, f"{p.zeilen} / {weg2}")


# ---------------------------------------------------------------------------
# E6
# ---------------------------------------------------------------------------
def _lasten(E):
    _app()
    from PySide6 import QtWidgets
    from statik3d.gui import main as gm
    from statik3d.model import Model, Material
    from statik3d import profiles, mesher
    m = Model("x")
    m.add_material(Material.steel("S355"))
    sec = profiles.make_section("HEA 200")
    m.add_section(sec)
    mesher.line_of_beams(m, list(m.materials)[0], sec.name, (0, 0, 0), (4, 0, 0), 2)
    m.auto_members()
    m.add_load_case("LF1", "G")
    m.load_node(2, Fz=-10e3, My=5e3, case="LF1")
    m.load_beam(0, qz=-20e3, case="LF1")
    m.add_vorspannung(list(m.members)[0], 250e3, case="LF1", sollkraft=True, kraftart="presse",
                      schlupf=0.002)
    m.einheiten = E
    erfasst = {}
    dummy = types.SimpleNamespace(model=m, cb_lastfilter=QtWidgets.QComboBox(),
                                  LASTRICHTUNG=gm.MainWindow.LASTRICHTUNG, tbl_last="tbl_last",
                                  _fill=lambda t, z, *a: erfasst.setdefault(t, z))
    gm.MainWindow._lasten_fuellen(dummy)
    return {z[2]: z[4] for z in erfasst["tbl_last"]}


def test_e6_tabellen():
    from statik3d import einheiten as eh
    from statik3d.gui import main as gm
    for E, kn, st, vs in (
            (eh.Einheiten(), "Fz = -10,00 kN; My = 5,00 kNm", "q = (0,00; 0,00; -20,00) kN/m",
             "P₀ = 250 kN, Δs = 2 mm"),
            (eh.Einheiten(kraft="N", laenge="mm", verformung="cm"),
             "Fz = -10000,00 N; My = 5000000,00 Nmm", "q = (0,00; 0,00; -20,00) N/mm",
             "P₀ = 250000 N, Δs = 0,2 cm")):
        z = _lasten(E)
        # zweiter Weg: Einheiten.text je Komponente
        weg2 = (f"Fz = {E.text(-10e3, 'kraft')}; My = {E.text(5e3, 'moment')}").replace(".", ",")
        check(f"E6 Lasten [{E.kraft}, {E.laenge}]: Knotenlast „{kn}“", z.get("Knotenlast") == kn == weg2,
              f"{z.get('Knotenlast')!r} / {weg2!r}")
        check(f"E6 Lasten [{E.kraft}, {E.laenge}]: Streckenlast „{st}“", z.get("Streckenlast") == st,
              repr(z.get("Streckenlast")))
        check(f"E6 Lasten [{E.kraft}, {E.laenge}]: Anfangsvorspannung „{vs}“",
              z.get("Anfangsvorspannung (P₀)") == vs, repr(z.get("Anfangsvorspannung (P₀)")))

    # Umhuellende: Einheitenspalte, Werte in der eingestellten Einheit
    spalten = gm.MainWindow._huelle_spalten()
    namen = [s.name for s in spalten]
    check("E6 Umhüllende: Spalte „Einheit“ hinter „Größe“", namen[:3] == ["Element", "Größe", "Einheit"],
          str(namen))
    r = types.SimpleNamespace(extreme_table=lambda: [[0, "My", -40e3, "LK1", 10e3, "LK2"],
                                                       [0, "N", -5e3, "LK2", 2e3, "LK1"]])
    for E, soll in ((eh.Einheiten(), [[0, "My", "kNm", -40.0, "LK1", 10.0, "LK2"],
                                      [0, "N", "kN", -5.0, "LK2", 2.0, "LK1"]]),
                    (eh.Einheiten(kraft="N", laenge="mm"), [[0, "My", "Nmm", -40e6, "LK1", 10e6, "LK2"],
                                                            [0, "N", "N", -5e3, "LK2", 2e3, "LK1"]])):
        zeilen = gm.MainWindow._huelle_zeilen(types.SimpleNamespace(_einheiten_modell=lambda E=E: E), r)
        # zweiter Weg: Einheiten.aus_si
        weg2 = [E.aus_si(-40e3, "moment"), E.aus_si(-5e3, "kraft")]
        gleich = (len(zeilen) == 2 and all(len(z) == len(spalten) for z in zeilen)
                  and all(a[:3] == b[:3] and a[4] == b[4] and a[6] == b[6]
                          and math.isclose(a[3], b[3]) and math.isclose(a[5], b[5]) for a, b in zip(zeilen, soll))
                  and math.isclose(zeilen[0][3], weg2[0]) and math.isclose(zeilen[1][3], weg2[1]))
        check(f"E6 Umhüllende [{E.kraft}, {E.laenge}]: My -40 kNm als {soll[0][3]:g} {soll[0][2]}",
              gleich, str(zeilen))


# ---------------------------------------------------------------------------
# E7
# ---------------------------------------------------------------------------
def test_e7_keine_wissenschaftliche_schreibweise():
    from statik3d.model import Model
    from statik3d.report.html import Report
    from statik3d import zahlen as zl
    m = Model("x")
    m.add_load_case("LF1", "G")
    P = [[0.0, 0.0, 0.0, 0.0], [12.5, 0.0, -0.00002, 1234.5e3]]
    m.add_geometrielast("F1", 0.0, case="LF1", verlauf={"punkte": P})
    rep = Report(m, None)
    zeile = None
    for blk in rep._load_tables(m.load_cases["LF1"]):
        if blk[0] == "table" and blk[1] and blk[1][0][:3] == ["Ziel", "p [kN/m²]", "Verlauf"]:
            zeile = blk[1][1]
    verlauf = str(zeile[2]) if zeile else ""
    soll = zl.zahl_text(1234.5, stellen=3, punkt=True)
    check("E7 Bericht, Flächenlast mit Verlauf: ohne „e+03“/„e-05“, Wert „1 230“, z „-0.00002“",
          verlauf and not _wiss(verlauf) and verlauf.endswith("→ " + soll) and "-0.00002" in verlauf,
          repr(verlauf))

    from statik3d import spannungen as spn
    from statik3d.gui import viewport as vp
    sk = spn.Werteskala(modus="fest", unten=0.0, oben=100.0)
    for wmin, soll, soll2 in ((-0.00002, "0", "0"), (-12345.6, "-12346", "-1235"), (-1.2345, "-1.23", "-0.123")):
        g = spn.grenzen(sk, np.array([wmin, 50.0, 80.0]))
        g2 = vp.skala_umrechnen(g, 0.1)
        # zweiter Weg: spannungen.dezimal (ohne Nachkommanullen)
        weg2 = [spn.dezimal(x).rstrip("0").rstrip(".") if "." in spn.dezimal(x) else spn.dezimal(x)
                for x in (wmin, wmin * 0.1)]
        check(f"E7 Farbskala, Wert unter der Skala {wmin:g}: „{soll}“, umgerechnet „{soll2}“",
              [g["below_label"], g2["below_label"]] == [soll, soll2] == weg2,
              f"{g['below_label']!r} / {g2['below_label']!r} / {weg2}")

    # Reynoldszahl: Windprotokoll und Bericht
    from statik3d.model import Material, Section, Member
    from statik3d import wind as wm
    from statik3d.wind import Wind
    mw = Model("Mast")
    mw.add_material(Material("S"))
    mw.add_section(Section.pipe("CHS", 0.2, 0.006))
    ids = [mw.add_node(0, 0, i * 1.0) for i in range(7)]
    el = [mw.add_element("beam", [ids[i], ids[i + 1]], "S", "CHS") for i in range(6)]
    mw.members["Mast"] = Member("Mast", el)
    mw.fix(ids[0], "all")
    w = Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"])
    mw.winde["W"] = w
    kw = wm.lasten_erzeugen(mw, w)
    Re = kw["staebe"][0]["Re"]
    soll_re = zl.zahl_text(float(f"{Re:.3g}"))
    text = [t for t in wm.erlaeuterung(w, kw) if t.startswith("Stab Mast")]
    check(f"E7 Windprotokoll: Re = {soll_re} statt {Re:.2e}",
          len(text) == 1 and f"Re = {soll_re};" in text[0] and not _wiss(text[0]), str(text)[:220])
    # Die Kennwerte des Berichts (wind.kennwerte) tragen die Staebe heute nicht
    # (Nebenbefund 14.11.2026) - die Tabelle wird mit denen aus lasten_erzeugen gefuellt
    zellen = []
    alt_kw = wm.kennwerte
    wm.kennwerte = lambda w_, m_: kw
    try:
        for blk in Report(mw, None).chapter_lastgenerierer():
            if blk[0] == "table" and blk[1] and "Re" in blk[1][0]:
                k = blk[1][0].index("Re")
                zellen = [z[k] for z in blk[1][1:]]
    finally:
        wm.kennwerte = alt_kw
    check(f"E7 Bericht, Kraftbeiwerte der Stäbe: Re „{soll_re}“", zellen == [soll_re], str(zellen))


def main():
    for t in (test_e1_antrieb_browser, test_e2_stab_ohne_verdrehung, test_e3_drehfeder,
              test_e4_zahl_ohne_nachkomma, test_e5_beschriftung_vorspannung, test_e6_tabellen,
              test_e7_keine_wissenschaftliche_schreibweise):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
