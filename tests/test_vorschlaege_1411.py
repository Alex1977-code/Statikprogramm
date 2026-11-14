"""
Drei Vorschlaege, vom Anwender am 14.11.2026 freigegeben („ja, alle drei
vorschläge einverstanden“).

(1) Werkstoff ueber 80 mm: Seit Befund C4 hat ein Werkstoff, der nur die
    Stahlsorte kennt, ueber 80 mm Erzeugnisdicke kein f_y und kein f_u
    (Meldung „f_y nach Erzeugnisnorm eintragen“). Eintragen ging bis jetzt nur,
    indem man die Sorte loeschte - dann fehlte β_w der Naehte. Der
    Werkstoffdialog hat jetzt die Zeile „f_y/f_u über 80 mm (Erzeugnisnorm)“;
    sie legt eine Dickenstufe in fy_dicke/fu_dicke ab (wie die RFEM-Tabelle),
    die Sorte bleibt. Probe: S355, Blech 200 mm, Eingabe 285/470 -> f_y 285.
    Zweiter Weg: ein Zugstab mit 200 mm Flansch, f_y aus der Ausnutzung
    N / (A f_y / γ_M0) zurueckgerechnet.

(2) U-Profile mit I_w nach der alten Formel (volle Flanschbreite, Befund C6):
    Model.u_profile_iw_alt nennt sie, Model.u_profile_iw_berichtigen rechnet I_w
    neu - nur, wo I_w genau dem alten Formelwert entspricht. Zweiter Weg: die
    numerisch integrierte Woelbordinate (ec3.woelb.sektorwerte). Die Frage
    beim Oeffnen (MainWindow._u_profile_iw_fragen) wird an einer Attrappe
    ohne Fenster geprueft: Ja berichtigt (Rueckgaengig-Schritt vorher), Nein
    laesst alles stehen.

(3) Flaechenlager mit Elementliste aus einer Ergebnisdatei von vor Stand 37:
    beim Oeffnen ein offener Hinweis im Modell („Flächenlager nach
    Neuvernetzen prüfen“), der als Korrektur am Modell im Status steht - auch
    nach „neu rechnen“ -, bis der Anwender ihn bestaetigt
    (Model.flaechenlager_geprueft). Kein Hinweis ab Stand 37, ohne
    Elementliste und auf unvernetzten Flaechen.

Ohne Hauptfenster; der Werkstoffdialog laeuft mit QApplication offscreen.

Aufruf:  python -m tests.test_vorschlaege_1411
"""
import contextlib
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_vorschlaege_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FAIL'} {name:<96} {str(detail)[:160]}")
    return bool(ok)


def close(name, ist, soll, tol, einheit=""):
    return check(name, ist is not None and abs(ist - soll) <= tol, f"ist {ist}, soll {soll:.6g}{einheit}")


def still(f, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a, **kw)


# ---------------------------------------------------------------------------
# (1) f_y/f_u ueber 80 mm nach Erzeugnisnorm
# ---------------------------------------------------------------------------
def test_erzeugnisnorm_werkstoff():
    from statik3d.model import Material
    from statik3d.joints.welds import beta_w
    mt = Material.steel("S355")
    check("(1) vor der Eingabe: S355, 200 mm ohne f_y, Meldung", not mt.yield_strength(0.2)
          and "Erzeugnisnorm" in mt.dicke_ohne_wert(0.2))
    zeilen = mt.erzeugnisnorm_setzen(285e6, 470e6)
    close("(1) S355, Blech 200 mm, Eingabe 285/470: f_y 285", mt.yield_strength(0.200) / 1e6, 285.0, 1e-9,
          " N/mm²")
    close("(1) … f_u 470 (zugfestigkeit_angegeben)", (mt.zugfestigkeit_angegeben(0.200) or 0) / 1e6, 470.0,
          1e-9, " N/mm²")
    close("(1) … f_u 470 (ultimate_strength)", mt.ultimate_strength(0.200) / 1e6, 470.0, 1e-9, " N/mm²")
    check("(1) … keine Meldung mehr über 80 mm", mt.dicke_ohne_wert(0.2, "fy") == ""
          and mt.dicke_ohne_wert(0.2, "fu") == "")
    close("(1) … bis 40 mm unverändert 355", mt.yield_strength(0.030) / 1e6, 355.0, 1e-9)
    close("(1) … 40–80 mm unverändert 335 (Tab. 3.1)", mt.yield_strength(0.060) / 1e6, 335.0, 1e-9)
    close("(1) … 80 mm genau: 335", mt.yield_strength(0.080) / 1e6, 335.0, 1e-9)
    close("(1) … f_u bis 40 mm 510, 40–80 mm 470", mt.zugfestigkeit_angegeben(0.03) / 1e6
          + mt.zugfestigkeit_angegeben(0.06) / 1e6, 980.0, 1e-9)
    check("(1) … Stahlsorte bleibt, β_w 0,9 bleibt", mt.grade == "S355" and abs(beta_w(mt.grade) - 0.9) < 1e-12,
          mt.grade)
    check("(1) … als Dickenstufe abgelegt und wieder erkannt", mt.erzeugnisnorm_wert("fy") == 285e6
          and mt.erzeugnisnorm_wert("fu") == 470e6 and mt.fy_dicke and mt.fu_dicke, f"{mt.fy_dicke}")
    check("(1) … Protokollzeile nennt den Wert", any("285" in z for z in zeilen), zeilen)
    # nur f_y: f_u bleibt ohne Wert
    m2 = Material.steel("S355")
    m2.erzeugnisnorm_setzen(285e6, None)
    check("(1) nur f_y eingetragen: f_y 285, f_u weiter Meldung", m2.yield_strength(0.2) == 285e6
          and "f_u nach Erzeugnisnorm" in m2.dicke_ohne_wert(0.2, "fu"))
    # leeren: wieder wie vorher
    mt.erzeugnisnorm_setzen(None, None)
    check("(1) leer eingetragen: Stufe entfernt, wieder Meldung", not mt.fy_dicke and not mt.fu_dicke
          and "Erzeugnisnorm" in mt.dicke_ohne_wert(0.2))
    # RFEM-Dickentabelle bleibt unveraendert
    r = Material.steel("S355", name="S355 RFEM")
    tab = [[0.016, 355e6], [0.040, 345e6], [0.063, 335e6], [0.080, 325e6], [0.100, 315e6],
           [0.150, 295e6], [0.200, 285e6], [0.250, 275e6], [0.400, 265e6]]
    r.fy_dicke = [list(x) for x in tab]
    z = r.erzeugnisnorm_setzen(300e6, None)
    check("(1) Werkstoff mit RFEM-Dickentabelle: unverändert, nicht als Erzeugnisnorm erkannt",
          r.fy_dicke == tab and r.erzeugnisnorm_wert("fy") is None and r.yield_strength(0.2) == 285e6, z)
    # ein eigener Wert bis 40 mm (f_y 360) bleibt die duennste Stufe
    e = Material.steel("S355")
    e.fy = 360e6
    e.erzeugnisnorm_setzen(285e6, None)
    check("(1) eigenes f_y 360 bis 40 mm bleibt, 40–80 mm 335, über 80 mm 285",
          (e.yield_strength(0.02), e.yield_strength(0.06), e.yield_strength(0.2)) == (360e6, 335e6, 285e6),
          e.fy_dicke)
    # f_y bis 40 mm danach geaendert (Werkstoffmaske): die duennste Stufe folgt, ohne Text zur Quelldatei
    vor = e.fy
    e.fy = 350e6
    zeilen = e.dickentabellen_nachfuehren(vor, e.fu)
    check("(1) f_y danach geändert: dünnste Stufe folgt, über 80 mm bleibt 285, kein Text „Quelldatei“",
          e.yield_strength(0.02) == 350e6 and e.yield_strength(0.2) == 285e6
          and not any("Quelldatei" in z for z in zeilen), zeilen)


def test_erzeugnisnorm_nachweis():
    """Zweiter Weg: Zugstab mit 200 mm dickem Flansch, f_y aus der Ausnutzung."""
    from statik3d import solver, mesher
    from statik3d.ec3.design import check_member
    from statik3d.model import Model, Material, Section
    m = Model("C4")
    mt = Material.steel("S355")
    m.add_material(mt)
    sec = Section.i_profile("I dick", 0.600, 0.400, 0.050, 0.200)
    m.add_section(sec)
    ids = mesher.line_of_beams(m, "S355", "I dick", (0, 0, 0), (2, 0, 0), n=2)
    if not m.members:
        m.add_member("S1", list(range(len(m.elements))))
    m.fix(ids[0], "all")
    N = 5000e3
    m.load_node(ids[-1], Fx=N)
    an = still(solver.solve_all, m, workers=1, combinations=False)
    mem = next(iter(m.members.values()))
    mc = still(check_member, m, mem, dict(an.cases))
    check("(1) Zugstab, Flansch 200 mm, ohne Eingabe: nicht geführt", "Erzeugnisnorm" in (mc.fehler or ""),
          mc.fehler)
    mt.erzeugnisnorm_setzen(285e6, 470e6)
    mc = still(check_member, m, mem, dict(an.cases))
    g0 = float(m.design.gamma_M0)
    fy = N * g0 / (sec.A * mc.util) if mc.util else 0.0
    check("(1) … mit 285/470: geführt", not mc.fehler, mc.fehler)
    close("(1) … f_y aus der Ausnutzung N γ_M0 / (A η) = 285 N/mm²", fy / 1e6, 285.0, 0.01, " N/mm²")


def test_erzeugnisnorm_datei():
    from statik3d.model import Material, Model
    m = Model("D")
    mt = Material.steel("S355")
    mt.erzeugnisnorm_setzen(285e6, 470e6)
    m.add_material(mt)
    p = os.path.join(tempfile.mkdtemp(prefix="statik3d_erz_"), "w.json")
    m.save(p)
    m2 = Model.load(p)
    w = m2.materials["S355"]
    check("(1) Speichern/Laden: Stufe über 80 mm bleibt (f_y 285, f_u 470, Sorte S355)",
          w.yield_strength(0.2) == 285e6 and w.zugfestigkeit_angegeben(0.2) == 470e6 and w.grade == "S355"
          and w.erzeugnisnorm_wert("fy") == 285e6, w.fy_dicke)
    m2.save(p)
    m3 = Model.load(p)
    check("(1) … zweiter Rundlauf bitgleich", m3.materials["S355"].fy_dicke == w.fy_dicke
          and m3.materials["S355"].fu_dicke == w.fu_dicke)


def test_erzeugnisnorm_dialog():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from statik3d.gui.dialogs import MaterialDialog
    from statik3d.model import Material
    d = MaterialDialog(None, Material.steel("S355"))
    check("(1) Dialog: Zeile „f_y/f_u über 80 mm (Erzeugnisnorm)“ vorhanden, frei, leer",
          hasattr(d, "fy80") and hasattr(d, "fu80") and d.fy80.isEnabled()
          and d.fy80.text() == "" and d.fu80.text() == "")
    if not hasattr(d, "fy80"):
        return
    d.fy80.setText("285")
    d.fu80.setText("470")
    mt = d.result_material()
    close("(1) Dialog: Eingabe 285/470 -> f_y bei 200 mm 285", mt.yield_strength(0.2) / 1e6, 285.0, 1e-9)
    check("(1) … Sorte S355 bleibt, Protokollzeile", mt.grade == "S355" and d.dicken_meldungen,
          d.dicken_meldungen)
    d2 = MaterialDialog(None, mt)
    check("(1) Dialog wieder geöffnet: zeigt 285 und 470", d2.fy80.wert(None) == 285.0
          and d2.fu80.wert(None) == 470.0, f"{d2.fy80.text()} {d2.fu80.text()}")
    d2.fy80.setText("")
    d2.fu80.setText("")
    mt2 = d2.result_material()
    check("(1) … geleert: wieder ohne Wert über 80 mm", not mt2.fy_dicke and not mt2.fu_dicke
          and "Erzeugnisnorm" in mt2.dicke_ohne_wert(0.2))
    d3 = MaterialDialog(None, mt)
    d3.grade.setCurrentText("S235")
    check("(1) … Sorte gewechselt: Felder über 80 mm leer (gehörten zur alten Sorte)",
          d3.fy80.text() == "" and d3.fu80.text() == "")
    mt3 = d3.result_material()
    check("(1) … und keine Stufe der alten Sorte, kein Text „Quelldatei“", not mt3.fy_dicke
          and not any("Quelldatei" in z for z in d3.dicken_meldungen), d3.dicken_meldungen)
    r = Material.steel("S355", name="RF")
    r.fy_dicke = [[0.016, 355e6], [0.040, 345e6], [0.400, 265e6]]
    d4 = MaterialDialog(None, r)
    check("(1) Werkstoff mit RFEM-Dickentabelle: Zeile gesperrt", not d4.fy80.isEnabled())
    r4 = d4.result_material()
    check("(1) … Tabelle unverändert", r4.fy_dicke == r.fy_dicke)
    o = Material("eigen", 210e9, 0.3, 7850.0, 1.2e-5, 300e6, 450e6, "")
    d5 = MaterialDialog(None, o)
    check("(1) Werkstoff ohne Stahlsorte: Zeile gesperrt", not d5.fy80.isEnabled())
    for x in (d, d2, d3, d4, d5):
        x.deleteLater()
    app.processEvents()


# ---------------------------------------------------------------------------
# (2) I_w der U-Profile
# ---------------------------------------------------------------------------
def _u_modell():
    from statik3d.model import Model, Material, iw_u_profil_alt
    from statik3d.profiles import make_section
    m = Model("U")
    m.add_material(Material.steel("S235"))
    alt = make_section("UPN 200")
    alt.name = "UPN 200 alt"
    alt.Iw = iw_u_profil_alt(alt.h, alt.b, alt.tw, alt.tf)
    m.add_section(alt)
    eig = make_section("UPN 200")
    eig.name = "UPN 200 eigen"
    eig.Iw = 9000e-12
    m.add_section(eig)
    neu = make_section("UPE 300")
    m.add_section(neu)
    n0, n1, n2 = m.add_node(0, 0, 0), m.add_node(3, 0, 0), m.add_node(6, 0, 0)
    m.add_element("beam", [n0, n1], "S235", alt.name)
    m.add_element("beam", [n1, n2], "S235", eig.name)
    return m


def test_u_profil_modell():
    from statik3d import rechenverfahren as rv
    from statik3d.ec3 import woelb as W
    m = _u_modell()
    check("(2) vorher: Status „U-Profile … neu zuweisen“", "U-Profile" in rv.modell_betroffen(m),
          rv.modell_betroffen(m)[:100])
    if not hasattr(m, "u_profile_iw_alt"):
        check("(2) Model.u_profile_iw_alt / u_profile_iw_berichtigen vorhanden", False)
        return
    check("(2) u_profile_iw_alt nennt nur das Profil mit dem alten Formelwert",
          m.u_profile_iw_alt() == ["UPN 200 alt"], m.u_profile_iw_alt())
    zeilen = m.u_profile_iw_berichtigen()
    s = m.sections["UPN 200 alt"]
    close("(2) berichtigt: UPN 200 I_w 10 499 cm⁶ (vorher 12 277)", round(s.Iw * 1e12), 10499.0, 1.0, " cm⁶")
    from tests.test_befunde_b_1411 import _iw_sektor
    soll = _iw_sektor(s.h, s.b, s.tw, s.tf)
    close("(2) … zweiter Weg: numerisch integrierte Wölbordinate ∫ω² t ds (0,1 %)", s.Iw / soll, 1.0, 1e-3)
    close("(2) … dritter Weg: Wölbordinaten ec3.woelb.sektorwerte", W.sektorwerte(s).Iw_probe / s.Iw, 1.0, 1e-6)
    check("(2) eigener Wert 9 000 cm⁶ bleibt", abs(m.sections["UPN 200 eigen"].Iw - 9000e-12) < 1e-18)
    check("(2) Protokollzeile: Profil, alt und neu", len(zeilen) == 1 and "UPN 200 alt" in zeilen[0]
          and "12 277" in zeilen[0] and "10 499" in zeilen[0], zeilen)
    check("(2) Status verschwunden", "U-Profile" not in rv.modell_betroffen(m) and not m.u_profile_iw_alt())
    check("(2) zweiter Aufruf: nichts mehr zu tun", m.u_profile_iw_berichtigen() == [])


class _Attrappe:
    """Nur was _u_profile_iw_fragen braucht - kein Fenster."""

    def __init__(self, model, antwort):
        self.model = model
        self.antwort = antwort
        self.fragen = []
        self.gemerkt = []
        self.protokoll = []
        self.analysis = object()
        self.results = None
        self.neu = 0

        class _Log:
            def appendPlainText(_s, t):
                self.protokoll.append(t)
        self.log = _Log()

    def _fragen(self, titel, text):
        self.fragen.append((titel, text))
        return self.antwort

    def merken(self, was, beschriftung=False):
        self.gemerkt.append((was, self.model.copy()))

    def refresh_all(self):
        self.neu += 1

    def info(self, text):
        self.protokoll.append(text)

    def _ergebnisse_verworfen_nachziehen(self):
        pass


def test_u_profil_frage():
    from statik3d.gui.main import MainWindow
    from statik3d import rechenverfahren as rv
    f = getattr(MainWindow, "_u_profile_iw_fragen", None)
    check("(2) MainWindow._u_profile_iw_fragen vorhanden", f is not None)
    if f is None:
        return
    a = _Attrappe(_u_modell(), False)
    f(a)
    check("(2) Frage gestellt: „I_w der U-Profile nach der berichtigten Formel neu berechnen?“",
          a.fragen and "I_w der U-Profile nach der berichtigten Formel neu berechnen?" in a.fragen[0][1],
          a.fragen)
    check("(2) Nein: I_w bleibt, Status bleibt, kein Rückgängig-Schritt",
          a.model.u_profile_iw_alt() == ["UPN 200 alt"] and "U-Profile" in rv.modell_betroffen(a.model)
          and not a.gemerkt and a.analysis is not None)
    a = _Attrappe(_u_modell(), True)
    f(a)
    check("(2) Ja: berichtigt, Protokollzeile, Status weg", not a.model.u_profile_iw_alt()
          and any("12 277" in z for z in a.protokoll) and "U-Profile" not in rv.modell_betroffen(a.model),
          a.protokoll)
    check("(2) … Rückgängig-Schritt mit dem Stand davor (alter Wert)", len(a.gemerkt) == 1
          and a.gemerkt[0][1].u_profile_iw_alt() == ["UPN 200 alt"], [g[0] for g in a.gemerkt])
    check("(2) … geladene Ergebnisse verworfen (Modell geändert)", a.analysis is None)
    b = _Attrappe(_u_modell(), True)
    b.model.u_profile_iw_berichtigen()
    f(b)
    check("(2) ohne alte U-Profile: keine Frage", not b.fragen)


# ---------------------------------------------------------------------------
# (3) Flaechenlager mit Elementliste aus einer Datei von vor Stand 37
# ---------------------------------------------------------------------------
def zwei_flaechen(h=0.5):
    from statik3d import mesher
    from statik3d.model import Material, Model, ShellProp
    m = Model("Z")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6, fu=360e6))
    m.add_shell_prop(ShellProp("t12", 0.012))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0.]]))
    m.add_line("a0", [0, 1]); m.add_line("a1", [1, 2]); m.add_line("a2", [2, 3]); m.add_line("a3", [3, 0])
    m.add_line("b0", [1, 4]); m.add_line("b1", [4, 5]); m.add_line("b2", [5, 2])
    m.add_flaeche("A", ["a0", "a1", "a2", "a3"], material="S235", dicke="t12")
    m.add_flaeche("B", ["b0", "b1", "b2", "a1"], material="S235", dicke="t12")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    still(mesher.modell_vernetzen, m, [], workers=1)
    return m


def _mit_bettung():
    from statik3d.model import DofBehaviour
    m = zwei_flaechen()
    m.add_surface_support(elements=list(m.flaechen["B"].elemente), name="Bettung",
                          uz=DofBehaviour("spring", stiffness=1e7))
    m.add_load_case("LF1", "G")
    m.case("LF1").gravity = [0, 0, -9.81]
    return m


def _datei_mit_stand(m, stand):
    """Ergebnisdatei des Modells, geschrieben wie vom Programm des Stands ``stand``."""
    from statik3d import ergebnisse as erg, rechenverfahren as rv, solver
    an = still(solver.solve_all, m, workers=1, combinations=False, design=False)
    p = os.path.join(tempfile.mkdtemp(prefix="statik3d_fl_"), "m.ergebnisse")
    alt, alt_merkmale = rv.VERFAHRENSSTAND, rv.aktuelle_merkmale
    rv.VERFAHRENSSTAND = stand
    # die Merkmale, die es beim Stand ``stand`` schon gab
    rv.aktuelle_merkmale = lambda model: {k: v for k, v in alt_merkmale(model).items()
                                          if rv.merkmal(k).wechsel[0].stand <= stand}
    an.info.pop("rechenverfahren", None)
    an.info.pop("verfahren_aus_datei", None)
    try:
        erg.schreiben(p, m, an)
    finally:
        rv.VERFAHRENSSTAND, rv.aktuelle_merkmale = alt, alt_merkmale
    return p


def _offen(m):
    return [h for h in (getattr(m, "importhinweise", None) or [])
            if h.get("art") == "flaechenlager_neuvernetzen" and not h.get("erledigt")]


def test_flaechenlager_hinweis():
    from statik3d import ergebnisse as erg, rechenverfahren as rv, solver
    from statik3d.model import Model, DofBehaviour
    mk = rv.merkmal("flaechenlager_neuvernetzen")
    check("(3) Merkmal „flaechenlager_neuvernetzen“: Korrektur am Modell mit Grund, Stand 37",
          mk is not None and mk.import_korrektur and bool(mk.modellgrund) and mk.wechsel[-1].stand == 37,
          f"{mk.import_korrektur if mk else '-'} {mk.modellgrund if mk else ''!r}")
    m = _mit_bettung()
    p = _datei_mit_stand(m, 30)
    an = erg.lesen(p, m)
    offen = _offen(m)
    check("(3) Datei Stand 30 geöffnet: offener Hinweis „Flächenlager nach Neuvernetzen prüfen“ für Bettung",
          len(offen) == 1 and offen[0].get("objekte") == ["Bettung"]
          and "Flächenlager nach Neuvernetzen prüfen" in offen[0].get("text", ""), offen)
    check("(3) … steht im Status der geladenen Ergebnisse", mk.titel in (an.info.get("verfahren_betroffen") or ""),
          (an.info.get("verfahren_betroffen") or "")[:120])
    an2 = still(solver.solve_all, m, workers=1, combinations=False, design=False)
    mm2 = rv.merkmale_der_datei({"verfahren": rv.angabe(m)}, m)
    st = rv.bewerten(m, mm2, an2)["betroffen"]
    check("(3) … neu gerechnet: Status bleibt (bis zur Bestätigung)", mk.titel in st, st[:120])
    erg.lesen(p, m)
    check("(3) … zweites Öffnen derselben Datei: kein zweiter Hinweis", len(_offen(m)) == 1)
    q = os.path.join(os.path.dirname(p), "m.json")
    m.save(q)
    m2 = Model.load(q)
    check("(3) … der Hinweis überdauert Speichern und Laden", len(_offen(m2)) == 1)
    if not hasattr(m2, "flaechenlager_geprueft"):
        check("(3) Model.flaechenlager_geprueft vorhanden", False)
        return
    namen = m2.flaechenlager_geprueft("Bettung")
    st = rv.bewerten(m2, rv.merkmale_der_datei({"verfahren": rv.angabe(m2)}, m2), an2)["betroffen"]
    check("(3) bestätigt: Hinweis erledigt, Status weg", namen == ["Bettung"] and not _offen(m2)
          and mk.titel not in st, st[:120])
    # die Oberflaeche uebergibt nur (Rechtsklick „Flächenlager geprüft“), an einer Attrappe
    from unittest import mock
    from statik3d.gui.main import MainWindow
    s = mock.MagicMock()
    s.model = m
    s.analysis = an
    idx = next(i for i, x in enumerate(m.surface_supports) if x.name == "Bettung")
    vorher = MainWindow._flaechenlager_hinweis_offen(s, idx)
    MainWindow.flaechenlager_geprueft(s, idx)
    check("(3) Oberfläche: Eintrag nur bei offenem Hinweis; „Flächenlager geprüft“ erledigt ihn, "
          "Status der geladenen Ergebnisse neu bewertet, Rückgängig-Schritt",
          vorher and not MainWindow._flaechenlager_hinweis_offen(s, idx) and not _offen(m)
          and mk.titel not in (an.info.get("verfahren_betroffen") or "")
          and s.merken.call_args is not None and s.merken.call_args.kwargs.get("beschriftung") is True,
          (an.info.get("verfahren_betroffen") or "")[:100])
    # kein Hinweis ab Stand 37
    m3 = _mit_bettung()
    erg.lesen(_datei_mit_stand(m3, 37), m3)
    check("(3) Datei Stand 37: kein Hinweis", not _offen(m3) and not mk.betrifft(m3))
    # Lager ohne Elementliste (auf der Flaeche B)
    m4 = zwei_flaechen()
    s4 = m4.add_surface_support(name="Geo", uz=DofBehaviour("spring", stiffness=1e7))
    s4.flaechen = ["B"]
    m4.add_load_case("LF1", "G")
    m4.case("LF1").gravity = [0, 0, -9.81]
    erg.lesen(_datei_mit_stand(m4, 30), m4)
    check("(3) Lager ohne Elementliste (Flächenbezug): kein Hinweis", not _offen(m4))
    # unvernetzte Flaechen: das Netz gehoert zu keiner Flaeche
    m5 = _mit_bettung()
    for f in m5.flaechen.values():
        f.elemente = []
    erg.lesen(_datei_mit_stand(m5, 30), m5)
    check("(3) Lager auf Elementen ohne vernetzte Fläche: kein Hinweis", not _offen(m5))


def main():
    for t in (test_erzeugnisnorm_werkstoff, test_erzeugnisnorm_nachweis, test_erzeugnisnorm_datei,
              test_erzeugnisnorm_dialog, test_u_profil_modell, test_u_profil_frage, test_flaechenlager_hinweis):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, repr(ex))
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
