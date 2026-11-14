"""
Befundliste vom 14.11.2026, zweite Runde (BEFUNDE-2026-11-14-RUNDE2.md), vom
Anwender am 14.11.2026 zur Behebung freigegeben:

B'3  Verformungsnachweis der Art „Stab“ mit ux nahm die Durchbiegung w_z
     (Kragarm: 5,30 mm statt der Laengsverschiebung 0,18 mm). Jetzt wie φ:
     fuer „Stab“ abgewiesen, aeltere Dateien melden, Nachweis „nicht geführt“.
B'4  Punktpaar mit einer Verdrehung und Grenze L/x verglich Radiant mit einer
     Laenge (10,32 mrad gegen L/300 = 13,3 mm „erfüllt“). Verdrehungen nur
     noch mit absolutem Grenzwert.
B'5  Browser „Stellung ändern“ loeschte das Antriebsmoment; Knotennummer
     „-1“ wurde Knoten 1, die Zahl 0 (JSON) „kein Antrieb“.
A'11 Protokoll „an Knoten {knoten + 1}“, Stellungsmaske des Arbeitsplatzes ab 1,
     Tabelle „Umhüllende“ mit fest zwei Nachkommastellen (MN: 0,00), Wert unter
     der Farbskala auf 0 gerundet (-0,0004 -> „0“).
B'9  Bericht: α_T, Lastspielzahlen, N_R, Konvergenz und Woehler-Beschriftung
     in wissenschaftlicher Schreibweise („1.20e-05“, „5e+05“).

Keine Hauptfenster: reine Funktionen, einzelne Widgets (offscreen), der Server
ueber seine Operationen.

Aufruf:  python -m tests.test_anzeige_runde2
"""
import math
import os
import re
import sys
import tempfile
import types
from decimal import Decimal

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


#: Zahl in wissenschaftlicher Schreibweise (ohne Hex-Kennungen wie „798818e44“:
#: davor darf keine Ziffer/kein Buchstabe ohne Punkt stehen, wie im Belegskript p2)
WISS = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:[.,]\d+)?[eE][+-]?\d+")


def _kragarm(Fx=0.0, Fy=0.0, Fz=-10e3):
    """Kragarm HEA 200, L = 4 m, 8 Elemente, Knoten 0 eingespannt, Last am Knoten 8."""
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
    m.load_node(8, Fx=Fx, Fy=Fy, Fz=Fz, case="LF1")
    m.add_combination("LK1", {"LF1": 1.0}, typ="SLS_CH")
    return m, sec


def _speichern_laden(m):
    from statik3d.model import Model
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "alt.s3d")
        m.save(p)
        return Model.load(p)


# ---------------------------------------------------------------------------
# B'3  Stab mit ux
# ---------------------------------------------------------------------------
def test_b3_stab_ohne_ux():
    from statik3d import solver, gzg
    from statik3d.model import Verformungsgrenze, verformungsgroessen
    m, sec = _kragarm(Fx=50e3, Fz=-10e3)
    stab = list(m.members)[0]
    g_stab = list(verformungsgroessen("stab"))
    check("B'3 verformungsgroessen(„stab“): nur uy, uz und u", g_stab == ["uy", "uz", "u"], str(g_stab))
    try:
        m.add_verformungsgrenze("S_ux", "stab", stab=stab, groesse="ux", grenzart="absolut", wert=0.05,
                                situation="SLS_CH")
        ok, text = False, "angenommen"
    except ValueError as ex:
        ok, text = "ux" in str(ex) and "Knoten" in str(ex), str(ex)
    check("B'3 add_verformungsgrenze: Art „Stab“ mit ux wird mit Klartext abgewiesen", ok, text[:160])
    for g in ("uy", "uz", "u"):
        m.add_verformungsgrenze(f"S_{g}", "stab", stab=stab, groesse=g, grenzart="absolut", wert=0.05,
                                situation="SLS_CH")
    m.add_verformungsgrenze("K_ux", "knoten", knoten=[8], groesse="ux", grenzart="absolut", wert=0.05,
                            situation="SLS_CH")
    # aeltere Datei mit Stab/ux (am add_verformungsgrenze vorbei)
    m.verformungsgrenzen["S_alt_ux"] = Verformungsgrenze("S_alt_ux", "stab", stab=stab, groesse="ux",
                                                         grenzart="absolut", wert=0.05, situation="SLS_CH")
    m2 = _speichern_laden(m)
    hinw = [h for h in getattr(m2, "_ladehinweise", []) if "S_alt_ux" in h]
    check("B'3 Öffnen einer älteren Datei: ein Hinweis zu „S_alt_ux“, Knoten- oder Punktpaarnachweis",
          len(hinw) == 1 and "Knoten" in hinw[0] and "nicht geführt" in hinw[0], str(hinw)[:220])
    check("B'3 … der Eintrag bleibt in der Datei stehen", "S_alt_ux" in m2.verformungsgrenzen)

    an = solver.solve_all(m2, progress=lambda *a: None, design=False)
    res = gzg.check_verformung(m2, an)
    alt = res.checks["S_alt_ux"]
    check("B'3 Nachweis „Stab“ mit ux: „nicht geführt“ statt 5,30 mm „erfüllt“",
          alt.status() == "nicht geführt" and "ux" in alt.fehler, f"{alt.status()}: {alt.fehler} "
          f"(Wert {alt.wert * 1e3:.3f} mm)")
    # zwei Wege fuer die Laengsverschiebung: Knotennachweis und Hand N L/(EA)
    hand = 50e3 * 4.0 / (210e9 * sec.A)
    kn = res.checks["K_ux"]
    check("B'3 … als Knotennachweis: ux = 0,177 mm (Hand N L/(EA) = 0,1769 mm)",
          abs(kn.wert - hand) < 1e-3 * hand, f"Programm {kn.wert * 1e3:.4f} mm, Hand {hand * 1e3:.4f} mm")
    # uz am Stab bleibt die Durchbiegung gegen die Sehne: Hand w(x) = F/(6EI)(3Lx²-x³) - x/L·w(L)
    EI = 210e9 * sec.Iy
    x = np.linspace(0.0, 4.0, 4001)
    w = 10e3 / (6 * EI) * (3 * 4.0 * x ** 2 - x ** 3)
    hand_uz = float(np.max(np.abs(w - x / 4.0 * w[-1])))
    suz = res.checks["S_uz"]
    check("B'3 … Stab mit uz unverändert die Durchbiegung gegen die Sehne (Hand 5,295 mm)",
          abs(suz.wert - hand_uz) < 2e-3 * hand_uz and suz.status() == "erfüllt",
          f"Programm {suz.wert * 1e3:.4f} mm, Hand {hand_uz * 1e3:.4f} mm")
    # _wert hat fuer „Stab“ keinen Rueckfall auf w_z mehr
    g = Verformungsgrenze("X", "stab", stab=stab, groesse="ux", grenzart="absolut", wert=0.05)
    try:
        v = gzg._wert(m2, g, an.combinations["LK1"], gzg.GrenzeCheck("X"))
        ok, text = False, f"Wert {v}"
    except (ValueError, KeyError) as ex:
        ok, text = True, str(ex)
    check("B'3 gzg._wert: „Stab“ mit ux liefert keine Durchbiegung mehr", ok, text[:120])


# ---------------------------------------------------------------------------
# B'4  Verdrehung nur mit absolutem Grenzwert
# ---------------------------------------------------------------------------
def test_b4_verdrehung_nur_absolut():
    from statik3d import solver, gzg
    from statik3d.model import Verformungsgrenze
    from statik3d import rechenverfahren as rv
    m, sec = _kragarm()
    for art, kn in (("punktpaar", [0, 8]), ("knoten", [8])):
        try:
            m.add_verformungsgrenze(f"P_{art}", art, knoten=kn, groesse="phiy", grenzart="L/x", wert=300,
                                    situation="SLS_CH")
            ok, text = False, "angenommen"
        except ValueError as ex:
            ok, text = "absolut" in str(ex) and "phiy" in str(ex), str(ex)
        check(f"B'4 add_verformungsgrenze: „{art}“ mit phiy und L/x wird mit Klartext abgewiesen", ok,
              text[:160])
    m.add_verformungsgrenze("P_abs", "punktpaar", knoten=[0, 8], groesse="phiy", grenzart="absolut",
                            wert=0.010, situation="SLS_CH")
    check("B'4 … Punktpaar mit phiy und absolutem Grenzwert bleibt möglich", "P_abs" in m.verformungsgrenzen)
    m.verformungsgrenzen["P_alt"] = Verformungsgrenze("P_alt", "punktpaar", knoten=[0, 8], groesse="phiy",
                                                      grenzart="L/x", wert=300, situation="SLS_CH")
    m2 = _speichern_laden(m)
    hinw = [h for h in getattr(m2, "_ladehinweise", []) if "P_alt" in h]
    check("B'4 Öffnen einer älteren Datei: ein Hinweis zu „P_alt“ (absoluten Grenzwert wählen)",
          len(hinw) == 1 and "absolut" in hinw[0] and "nicht geführt" in hinw[0], str(hinw)[:220])
    an = solver.solve_all(m2, progress=lambda *a: None, design=False)
    res = gzg.check_verformung(m2, an)
    alt = res.checks["P_alt"]
    check("B'4 Punktpaar phiy mit L/x: „nicht geführt“ statt 10,32 mrad gegen 13,3 mm „erfüllt“",
          alt.status() == "nicht geführt" and "absolut" in alt.fehler, f"{alt.status()}: {alt.fehler}")
    # zwei Wege fuer den absoluten Nachweis: Programm und Hand F L²/(2EI)
    hand = 10e3 * 16.0 / (2 * 210e9 * sec.Iy)
    p = res.checks["P_abs"]
    check("B'4 … mit absolutem Grenzwert: φy(8) - φy(0) = 10,32 mrad (Hand 10,318), „NICHT erfüllt“",
          abs(p.wert - hand) < 1e-3 * hand and p.status() == "NICHT erfüllt",
          f"Programm {p.wert * 1e3:.3f} mrad, Hand {hand * 1e3:.3f} mrad, {p.status()}")

    # Verfahrenstabelle: nur Modelle mit einem solchen gespeicherten Nachweis
    from statik3d.model import Model
    mk = rv.merkmal("gzg_groesse_grenzart")
    m_uz, _s = _kragarm()
    m_uz.add_verformungsgrenze("S_uz", "stab", stab=list(m_uz.members)[0], groesse="uz")
    m_ux, _s = _kragarm()
    m_ux.verformungsgrenzen["S_ux"] = Verformungsgrenze("S_ux", "stab", stab=list(m_ux.members)[0],
                                                        groesse="ux")
    check("B'3/B'4 Verfahrenstabelle: Merkmal „gzg_groesse_grenzart“, Stand 57, Fehlerkorrektur, betrifft "
          "nur Modelle mit Stab/ux oder Verdrehung mit L/x",
          mk is not None and mk.wechsel[-1].stand == 57 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 57 and mk.betrifft(m2) and mk.betrifft(m_ux)
          and not mk.betrifft(m_uz) and not mk.betrifft(Model("leer")),
          f"{mk and mk.wechsel}, Verfahrensstand {rv.VERFAHRENSSTAND}")

    # Dialog: Verdrehung -> nur „absoluter Wert“; Stab ohne ux
    _app()
    from statik3d.gui.dialogs import VerformungsgrenzeDialog
    d = VerformungsgrenzeDialog(None, m)
    d.cb_art.setCurrentIndex(d.cb_art.findData("stab"))
    stab_g = [d.cb_groesse.itemData(i) for i in range(d.cb_groesse.count())]
    check("B'3 Dialog: bei „Stab“ nur uy, uz und u in der Auswahl", stab_g == ["uy", "uz", "u"], str(stab_g))
    d.cb_art.setCurrentIndex(d.cb_art.findData("punktpaar"))
    d.cb_grenzart.setCurrentIndex(d.cb_grenzart.findData("L/x"))
    d.cb_groesse.setCurrentIndex(d.cb_groesse.findData("phiy"))
    i_lx = d.cb_grenzart.findData("L/x")
    lx_aus = not d.cb_grenzart.model().item(i_lx).isEnabled()
    _name, kw = d.result()
    check("B'4 Dialog: Punktpaar mit phiy stellt auf „absoluter Wert“ und sperrt L/x",
          d.cb_grenzart.currentData() == "absolut" and lx_aus and kw["grenzart"] == "absolut",
          f"{d.cb_grenzart.currentData()}, L/x gesperrt {lx_aus}, Hinweis: {d.hinweis.text()[:90]}")
    d.cb_groesse.setCurrentIndex(d.cb_groesse.findData("uz"))
    lx_an = d.cb_grenzart.model().item(i_lx).isEnabled()
    check("B'4 … bei einer Verschiebung ist L/x wieder wählbar", lx_an)
    d.deleteLater()


# ---------------------------------------------------------------------------
# B'5  Browser: Stellung aendern behaelt den Antrieb, Knotennummer streng
# ---------------------------------------------------------------------------
def _frame():
    from statik3d.model import Model
    m = Model("x")
    for i in range(17):
        m.add_node(0.5 * i, 0, 0)
    return m


def test_b5_web_stellung():
    from statik3d.web import server as sv
    m = _frame()
    st = types.SimpleNamespace(model=m)
    sv._op_stellung(st, m, {"name": "S1", "winkel": 0.0, "antrieb_knoten": "16", "antrieb_mz": 40e3})
    zus = sv._stellungen_summary(st)
    z = zus["liste"][0]
    check("B'5 Server: die Liste nennt Knoten (ab 0) und Momente [kNm] des Antriebs",
          z.get("antrieb_knoten") == 16 and np.allclose(z.get("antrieb_moment") or [], [0.0, 0.0, 40.0]),
          f"{z.get('antrieb_knoten')!r}, {z.get('antrieb_moment')!r}")
    sv._op_stellung(st, m, {"name": "S1", "winkel": 5.0})
    a = st.stellungen[0].antrieb
    check("B'5 „Stellung ändern“ ohne Antriebsfeld behält den Antrieb (Knoten 16, Mz 40 kNm)",
          a is not None and a[0] == 16 and np.allclose(list(a[1]), [0, 0, 40e3]), str(a))
    sv._op_stellung(st, m, {"name": "S1", "winkel": 5.0, "antrieb_knoten": "12"})
    a = st.stellungen[0].antrieb
    check("B'5 … neuer Knoten ohne Momentfelder: Momente bleiben", a is not None and a[0] == 12
          and np.allclose(list(a[1]), [0, 0, 40e3]), str(a))
    sv._op_stellung(st, m, {"name": "S1", "winkel": 5.0, "antrieb_knoten": ""})
    check("B'5 … leeres Knotenfeld: kein Antrieb", st.stellungen[0].antrieb is None,
          str(st.stellungen[0].antrieb))
    sv._op_stellung(st, m, {"name": "S0", "antrieb_knoten": 0, "antrieb_mz": 1e3})
    a = [s for s in st.stellungen if s.name == "S0"][0].antrieb
    check("B'5 JSON-Zahl 0: Antrieb an Knoten 0 (bisher kein Antrieb)", a is not None and a[0] == 0, str(a))
    for roh in ("-1", -1, "1,2", "abc", "1.5", 2.5, True, "3 4"):
        st2 = types.SimpleNamespace()
        try:
            sv._op_stellung(st2, m, {"name": "X", "antrieb_knoten": roh, "antrieb_mz": 1e3})
            ok, text = False, f"angenommen: {st2.stellungen[0].antrieb}"
        except sv.ApiError as ex:
            ok, text = True, str(ex)
        check(f"B'5 Knotennummer {roh!r} wird abgewiesen (ApiError)", ok, text[:100])
    js = open(os.path.join(WURZEL, "statik3d", "web", "static", "app.js"), encoding="utf-8").read()
    form = js[js.find("function stellungForm"):js.find("function renderBruecke")]
    tr_k = re.search(r"inp\('antrieb_knoten',[^\n]*s\.antrieb_knoten[^\n]*data-keep", form)
    tr_m = ("const am = s.antrieb_moment" in form
            and all(re.search(r"num\('antrieb_%s', '[^']*', am\[%d\], \{scale:\s*1e3\}\)" % (k, i), form)
                    for i, k in enumerate(("mx", "my", "mz"))))
    check("B'5 app.js: Formular belegt Knoten und Momente [kNm] vor, ein leeres Knotenfeld wird geschickt",
          tr_k is not None and tr_m, f"Knoten {tr_k is not None}, Momente {tr_m}")


# ---------------------------------------------------------------------------
# A'11  Knoten ab 0, Nachkommastellen, Wert unter der Farbskala
# ---------------------------------------------------------------------------
def test_a11_anzeige():
    import copy
    from statik3d.bridges.positions import Stellung
    m = _frame()
    m.add_load_case("LF1", "G")
    s = Stellung(name="S", faelle=["LF1"], antrieb=(16, [0.0, 0.0, 40e3]))
    mk = copy.deepcopy(m)
    log = []
    s._antrieb(mk, log, m)
    lf = [n for n, lc in mk.load_cases.items() if (lc.bezeichnung or "").startswith("Antrieb")][0]
    knoten_last = [int(l.node) for l in mk.load_cases[lf].nodal_loads]
    check("A'11 Stellungsprotokoll: „an Knoten 16“ wie die Knotenlast im Lastfall (bisher 17)",
          len(log) == 1 and log[0].endswith("an Knoten 16") and knoten_last == [16], f"{log} / {knoten_last}")

    _app()
    from statik3d.gui.dialogs import StellungDialog
    from statik3d.web import server as sv
    dlg = StellungDialog(None, s, m)
    vor = dlg.ed_knoten.wert(None)
    dlg.ed_knoten.setzen(8)
    b = dlg.stellung().antrieb
    dlg.deleteLater()
    st = types.SimpleNamespace()
    sv._op_stellung(st, m, {"name": "S", "antrieb_knoten": "8", "antrieb_mz": 40e3})
    w = st.stellungen[0].antrieb
    check("A'11 Stellungsmaske des Arbeitsplatzes zählt Knoten ab 0 (zeigt 16, „8“ wird Knoten 8 wie im Browser)",
          vor == 16 and b is not None and b[0] == 8 == w[0], f"vorbelegt {vor}, Maske {b}, Browser {w}")

    from statik3d import einheiten as eh
    from statik3d.gui import main as gm, tabellen as tab
    r = types.SimpleNamespace(extreme_table=lambda: [[0, "N", -1.5e3, "LK1", 40e3, "LK2"],
                                                       [0, "My", -40e3, "LK1", 2.5e3, "LK2"]])
    for E in (eh.Einheiten(kraft="MN", nk_kraft=4), eh.Einheiten(kraft="kN", nk_kraft=0)):
        zeilen = gm.MainWindow._huelle_zeilen(types.SimpleNamespace(_einheiten_modell=lambda E=E: E), r)
        tm = tab.TabellenModell(gm.MainWindow._huelle_spalten())
        tm.einheiten_quelle = lambda E=E: E
        tm.zeilen = [list(z) for z in zeilen]
        txt = [[tm.data(tm.index(i, j)) for j in (3, 5)] for i in range(2)]
        # zweiter Weg: Einheiten.text mit der Einstellung, Komma wie in Tabellen
        weg2 = [[E.text(-1.5e3, "kraft", mit_einheit=False), E.text(40e3, "kraft", mit_einheit=False)],
                [E.text(-40e3, "moment", mit_einheit=False), E.text(2.5e3, "moment", mit_einheit=False)]]
        weg2 = [[t.replace(".", ",") for t in z] for z in weg2]
        check(f"A'11 Umhüllende [{E.kraft}, {E.nk_kraft} Nachkommastellen]: {weg2[0][0]} statt fest 2 Stellen",
              txt == weg2, f"{txt} / {weg2}")

    from statik3d import spannungen as spn
    sk = spn.Werteskala(modus="fest", unten=0.0, oben=0.005)
    for wmin in (-0.0004, -0.00049, -0.0012):
        g = spn.grenzen(sk, np.array([wmin, 0.002, 0.004]))
        weg2 = format(Decimal(repr(wmin)).normalize(), "f")
        check(f"A'11 Farbskala: Wert unter der Skala {weg2} (bisher „0“ bzw. „-0.001“)",
              g["below_label"] == weg2, f"{g['below_label']!r} / {weg2!r}")


# ---------------------------------------------------------------------------
# B'9  Bericht ohne wissenschaftliche Schreibweise
# ---------------------------------------------------------------------------
def _sichtbar(t):
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
    texte = []
    for s in re.findall(r"<svg.*?</svg>", t, flags=re.S | re.I):
        texte += re.findall(r"<text[^>]*>(.*?)</text>", s, flags=re.S)
    t = re.sub(r"<svg.*?</svg>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as H
    return H.unescape(t), [H.unescape(x) for x in texte]


def _tabelle(bloecke, titel_teil):
    for b in bloecke:
        if b[0] == "table" and len(b) > 2 and titel_teil in str(b[2]):
            return b[1]
    return None


def test_b9_bericht():
    from statik3d import examples_lib as ex, solver, zahlen as zl
    from statik3d.report.html import Report
    from statik3d.ec3.fatigue import sn_life
    for n in ("hall", "gate"):
        m = ex.build_example(n)
        an = solver.solve_all(m, design=True, fatigue=True, progress=lambda *a: None)
        opts = {k: True for k in Report.DEFAULTS if isinstance(Report.DEFAULTS[k], bool)}
        h = Report(m, an, options=opts).html()
        text, svg = _sichtbar(h)
        tr = sorted(set(WISS.findall(text)))
        tr_svg = sorted(set(z for s in svg for z in WISS.findall(s)))
        check(f"B'9 Bericht „{n}“: keine wissenschaftliche Schreibweise im Text und in den Bildern",
              not tr and not tr_svg, f"Text {tr[:6]}, Bilder {tr_svg[:4]}")
        a = list(m.materials.values())[0].alpha
        soll_a = zl.zahl_text(float(f"{a:.3g}"), punkt=True)
        check(f"B'9 … α_T = {soll_a} (Decimal: {format(Decimal(repr(a)).normalize(), 'f')})",
              f" {soll_a} " in text and soll_a == format(Decimal(repr(a)).normalize(), "f"), soll_a)
        if n == "hall":
            fm = next(iter(an.fatigue.members.values()))
            dsg, nz, NR, _di, _k = fm.tabelle()[0]
            NR2 = sn_life(dsg, fm.category, fm.gamma_Mf)
            # zweiter Weg: ganze Zahlen von Hand, ohne Tausendertrenner wie fmt im Bericht
            soll_n = str(int(round(nz)))
            soll_NR = str(int(float(f"{NR2:.3g}")))
            check(f"B'9 … Kollektiv: n = {soll_n}, N_R = {soll_NR} (aus sn_life nachgerechnet)",
                  f"n = {soll_n}" in " ".join(svg) and re.search(
                      rf"{re.escape(soll_n)}\s+{re.escape(soll_NR)}\s", text) is not None,
                  f"n {nz}, N_R Programm {NR}, sn_life {NR2}")

    # Konvergenz nach Theorie III. Ordnung
    from statik3d.model import Model, Material, Section
    m = Model("T3")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.1))
    k = [m.add_node(i * 1.0, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [k[i], k[i + 1]], "S235", "R")
    m.fix(k[0], "all")
    lc = m.case()
    lc.theorie = "III"
    m.load_node(k[2], Fz=-1000.0, Fx=-5000.0)
    an = solver.solve_all(m)
    rep = Report(m, an)
    rows = _tabelle(rep.chapter_theorie3(), "Theorie III. Ordnung je Lastfall")
    info = next(iter(an.theorie3.kombinationen.values())) if an.theorie3 else None
    zelle = rows[1][3] if rows and len(rows) > 1 else ""
    soll = format(Decimal(f"{info.konvergenz:.1e}").normalize(), "f") if info else "?"
    check(f"B'9 Theorie III. Ordnung: Residuum „{soll}“ statt „{info.konvergenz:.1e}“" if info else "B'9 Theorie III",
          bool(zelle) and not WISS.search(zelle) and zelle == soll
          and math.isclose(float(zelle), info.konvergenz, rel_tol=0.06), repr(zelle))

    # Schwingung: Lastspiele N und N_R
    from tests import test_schwingung as tsw
    from statik3d import schwingung as sw, wasserdruck as wdm
    from statik3d.wasserdruck import Wasserdruck
    m = tsw._haut(nz=20)
    wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0], unterstroemt=True, spalt=0.3,
                     cp_dyn=0.1)
    wdm.lasten_erzeugen(m, wd)
    m.wasserdruecke["S"] = wd
    an = solver.Analysis(m)
    an.schwingung = sw.nachweis(m, sw.Schwingungsnachweis("N1", wasserdruck="S", n_moden=2, d_kante=0.2,
                                                         betriebsstunden=100.0), an)
    rows = _tabelle(Report(m, an).chapter_schwingung(), "Antwort auf die Druckschwankung")
    zeilen = {r[0]: r[1] for r in (rows or [])[1:]}
    d = an.schwingung.dyn or {}
    nN = zeilen.get("Lastspiele N = f_s·t", "")
    nr = zeilen.get("N_R, D = N/N_R", "")
    soll_N = str(int(float(f"{d.get('N', 0):.3g}")))
    check(f"B'9 Schwingung: Lastspiele N „{soll_N}“, N_R ohne Exponent",
          "N" in d and nN == soll_N and not WISS.search(nN) and not WISS.search(nr), f"{nN!r} / {nr!r}")


def main():
    for t in (test_b3_stab_ohne_ux, test_b4_verdrehung_nur_absolut, test_b5_web_stellung, test_a11_anzeige,
              test_b9_bericht):
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
