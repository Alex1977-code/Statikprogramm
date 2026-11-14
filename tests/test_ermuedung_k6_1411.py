"""
Behebungen vom 14.11.2026, zweite Runde (BEFUNDE-2026-11-14-RUNDE2.md), Agent
„ermuedung“: Kerbfall-Vorschlag mit k_s in der Stabmaske (A'1), Doppel-U und
unbenutzte U-Profile beim I_w (A'10), Protokoll „Kerbfälle vorschlagen“ und
k_s-Texte (A'11), Wölbflächenmoment S_ω des U-Profils (B'1) und I_w der UPN
mit Flanschneigung (B'2).

Zwei Wege je Zahl: das Programm gegen eine numerische Integration auf der
Profilmittellinie (eigene Funktion hier, Trapezregel, Schubmittelpunkt aus
der Projektion auf 1, y, z) bzw. gegen die Handformel.

Aufruf:  python -m tests.test_ermuedung_k6_1411
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {detail}")
    return ok


def close(name, ist, soll, tol, einheit=""):
    return check(name, abs(ist - soll) <= tol, f"ist {ist:.6g}, soll {soll:.6g}{einheit}")


# --------------------------------------------------------------------------
# Zweiter Weg: Woelbordinate numerisch auf der Mittellinie, Flanschdicke
# t(x) = t_f + Neigung (b/2 - x), x vom Stegruecken (DIN 1026-1: t bei b/2)
# --------------------------------------------------------------------------
def _mittellinie(h, b, tw, tf, neigung=0.0, n=20001):
    bs, hs = b - tw / 2, h - tf
    yf = np.linspace(bs, 0, n)
    zw = np.linspace(hs / 2, -hs / 2, n)
    yu = np.linspace(0, bs, n)
    y = np.r_[yf, 0 * zw, yu]
    z = np.r_[hs / 2 + 0 * yf, zw, -hs / 2 + 0 * yu]
    t = np.r_[tf + neigung * (b / 2 - (yf + tw / 2)), tw + 0 * zw, tf + neigung * (b / 2 - (yu + tw / 2))]
    teil = np.r_[0 * yf, 1 + 0 * zw, 2 + 0 * yu]
    dy = np.diff(y, prepend=y[0])
    dz = np.diff(z, prepend=z[0])
    om = np.cumsum(y * dz - z * dy)
    ds = np.sqrt(dy ** 2 + dz ** 2)
    w = np.zeros_like(ds)
    w[1:] += 0.5 * ds[1:]
    w[:-1] += 0.5 * ds[1:]
    dA = t * w
    B = np.c_[np.ones_like(y), y, z]
    c = np.linalg.solve(B.T @ (B * dA[:, None]), B.T @ (dA * om))
    o = om - B @ c
    S = np.r_[0, np.cumsum(0.5 * (o[1:] * t[1:] + o[:-1] * t[:-1]) * ds[1:])]
    return {"Iw": float((dA * o * o).sum()), "S_t": float(np.max(np.abs(S) / t)),
            "teil": int(teil[int(np.argmax(np.abs(S) / t))]),
            "S_mitte": float(S[np.where(teil == 1)[0][np.argmin(np.abs(z[teil == 1]))]]),
            "omega_max": float(np.abs(o).max())}


# --------------------------------------------------------------------------
# A'1: Stabmaske mit dem Kerbfall-Vorschlag k_s
# --------------------------------------------------------------------------
def test_stabmaske():
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from types import SimpleNamespace as NS
    from statik3d.model import Member, Section
    from statik3d.gui.dialogs import MemberDialog
    from statik3d.ec3 import kerbfaelle as kf
    for d, text in ((0.040, "46,53"), (0.050, "44,01")):
        sec = Section.circle("Rd", d)
        m = NS(elements=[NS(typ="truss", sec="Rd")], sections={"Rd": sec})
        v = kf.vorschlag_stab(m, NS(elements=[0], name="Z"))
        mem = Member(name="Z", elements=[0])
        mem.detail_category = v.kerbfall
        mem.kerbfall_vorschlag = True
        dlg = MemberDialog(None, mem, 3.0)
        gezeigt = dlg.cat.currentText()
        dlg.apply(mem)
        check(f"A'1 Rund {d * 1e3:.0f}: Maske zeigt „{text} N/mm² – Vorschlag mit k_s“",
              gezeigt.startswith(f"{text} N/mm²") and "Vorschlag mit k_s" in gezeigt, repr(gezeigt))
        check(f"A'1 Rund {d * 1e3:.0f}: nach OK steht der Vorschlag unverändert ({v.kerbfall / 1e6:.4f} N/mm²)",
              mem.detail_category == v.kerbfall, f"{mem.detail_category}")
        dlg.deleteLater()
    # eigener Wert ausserhalb der Liste (47) und Listenwert (71): bleiben
    for wert, text in ((47e6, "47 N/mm² – eingegebener Wert"), (71e6, "71: ")):
        mem = Member(name="Z", elements=[0])
        mem.detail_category = wert
        dlg = MemberDialog(None, mem, 3.0)
        gezeigt = dlg.cat.currentText()
        dlg.apply(mem)
        check(f"A'1 Kerbfall {wert / 1e6:.0f}: Maske zeigt „{text}…“, OK lässt ihn stehen",
              gezeigt.startswith(text) and mem.detail_category == wert, f"{gezeigt!r} {mem.detail_category}")
        dlg.deleteLater()
    # „kein Ermüdungsnachweis“ bleibt waehlbar
    mem = Member(name="Z", elements=[0])
    mem.detail_category = 46.5302e6
    dlg = MemberDialog(None, mem, 3.0)
    dlg.cat.setCurrentIndex(0)
    dlg.apply(mem)
    check("A'1 „kein Ermüdungsnachweis“ gewählt: None", mem.detail_category is None)
    dlg.deleteLater()


def _kragarm(kerbfall):
    from statik3d import mesher
    from statik3d.model import Material, Model
    from statik3d.profiles import make_section
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (2, 0, 0), 4)
    m.fix(ids[0], [0, 1, 2, 3, 4, 5])
    m.case().category = "G"
    m.load_node(ids[-1], Fz=-10000.0)
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fz=-25000.0)
    m.add_member("Kragarm", list(range(4)), detail_category=kerbfall)
    return m


def test_bericht_und_tabelle():
    from statik3d.report.html import Report
    from statik3d.model import FatigueLoad
    from statik3d import solver
    k = 46.5302e6
    m = _kragarm(k)
    m.members["Kragarm"].kerbfall_vorschlag = True
    rep = Report(m, None)
    zelle = None
    for blk in rep.chapter_system():
        if blk[0] == "table" and blk[1] and blk[1][0][-1] == "Kerbfall [MPa]":
            zelle = blk[1][1][-1]
    check("A'1 Bericht, Stabtabelle: Kerbfall 46.53 statt 47", zelle == "46.53", repr(zelle))
    # Ermuedungskapitel (kleine Rechnung)
    m.fatigue_loads["E"] = FatigueLoad("E", folge=["LF1", "LF2"], wiederholungen=1e5)
    an = solver.solve_all(m, design=False, fatigue=True)
    rep = Report(m, an)
    bl = rep.chapter_fatigue()
    ueb = [blk[1][1][1] for blk in bl if blk[0] == "table" and blk[1]
           and blk[1][0][:2] == ["Stab", "Kerbfall Δσ_C [MPa]"]]
    kv = [dict(blk[1]).get("Kerbfall Normalspannung Δσ_C", "") for blk in bl if blk[0] == "kv"]
    check("A'1 Bericht, Ermüdung Übersicht: 46.53", ueb == ["46.53"], repr(ueb))
    check("A'1 Bericht, Ermüdung im Einzelnen: „46.53 MPa – …“, nicht 47",
          kv and kv[0].startswith("46.53 MPa") and "47" not in kv[0], repr(kv))
    # Stabtabelle der Oberflaeche (MainWindow.refresh_members an einer Attrappe)
    from statik3d.gui.main import MainWindow

    class Att:
        model = m
        zeilen = None

        def _fill(self, tbl, rows):
            Att.zeilen = rows
        tbl_mem = None
    MainWindow.refresh_members(Att())
    check("A'1 Oberfläche, Stabtabelle: „46.53 (Vorschlag)“", Att.zeilen and Att.zeilen[0][-1] == "46.53 (Vorschlag)",
          repr(Att.zeilen and Att.zeilen[0][-1]))
    m.members["Kragarm"].detail_category = 71e6
    m.members["Kragarm"].kerbfall_vorschlag = False
    MainWindow.refresh_members(Att())
    check("A'1 … ganzzahliger Kerbfall bleibt „71“", Att.zeilen[0][-1] == "71", repr(Att.zeilen[0][-1]))


# --------------------------------------------------------------------------
# A'11: Protokoll „Kerbfälle vorschlagen“ und k_s-Texte
# --------------------------------------------------------------------------
def _zugstaebe():
    from statik3d.model import Material, Model, Section
    m = Model("Z")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.circle("Rund 40", 0.040))
    m.add_section(Section.circle("Rund 20", 0.020))
    k = [m.add_node(i, 0, 0) for i in range(4)]
    m.add_element("truss", [k[0], k[1]], "S355", "Rund 40")
    m.add_element("truss", [k[1], k[2]], "S355", "Rund 40")
    m.add_element("truss", [k[2], k[3]], "S355", "Rund 20")
    m.add_member("Z1", [0])
    m.add_member("Z2", [1])
    m.add_member("Z3", [2])
    return m


def test_protokoll_und_ks():
    from statik3d.ec3 import kerbfaelle as kf
    m = _zugstaebe()
    log = []
    n = kf.anwenden(m, log)
    z = log[0] if log else ""
    check("A'11 Protokoll: Zählung unverändert (3 Zugstäbe)", n["zugstab"] == 3, str(n))
    check("A'11 Protokoll nennt 1 Zugstab mit Kerbfall 50 N/mm²", "1 Zugstab: Kerbfall 50 N/mm²" in z, z)
    check("A'11 … und 2 Zugstäbe Ø 40 mm mit 46,53 N/mm² und k_s = (30/40)^0,25 = 0,931",
          "2 Zugstäbe Ø 40 mm: Kerbfall 46,53 N/mm²" in z and "k_s = (30/40)^0,25 = 0,931" in z, z)
    check("A'11 … nicht mehr pauschal „3 Zugstäbe: Kerbfall 50“", "3 Zugstäbe" not in z, z)
    v = kf.vorschlag_stab(m, m.members["Z1"])
    check("A'11 Vorschlagsgrund mit Komma: „k_s = (30/40)^0,25 = 0,931“",
          "k_s = (30/40)^0,25 = 0,931" in v.grund and "0.931" not in v.grund, v.grund)
    from statik3d.joints import design as jd
    r = jd.fatigue_check("schraube_zug", [(100e6, 1e5)], d=0.036)
    check("A'11 Schraube M36: „k_s = (30/36)^0,25 = 0,955“ mit Komma",
          "k_s = (30/36)^0,25 = 0,955" in r["beschreibung"] and "0.955" not in r["beschreibung"],
          r["beschreibung"])


# --------------------------------------------------------------------------
# B'2: I_w der UPN mit Flanschneigung
# --------------------------------------------------------------------------
def test_iw_upn():
    from statik3d.profiles import make_section, UPN, UPE
    from statik3d.model import iw_u_profil
    from statik3d.ec3 import woelb as W
    for nm, tab, neig in (("UPN 200", UPN[200], 0.08), ("UPN 300", UPN[300], 0.08), ("UPN 100", UPN[100], 0.08),
                          ("UPE 200", UPE[200], 0.0), ("UPE 400", UPE[400], 0.0)):
        h, b, tw, tf, _r = [x * 1e-3 for x in tab]
        s = make_section(nm)
        soll = _mittellinie(h, b, tw, tf, neig)["Iw"]
        check(f"B'2 {nm}: I_w wie die numerisch integrierte Wölbordinate mit Flanschdicke t(x) (1e-5)",
              abs(s.Iw / soll - 1) < 1e-5, f"{s.Iw * 1e12:.1f} gegen {soll * 1e12:.1f} cm⁶")
        close(f"B'2 {nm}: Wölbordinaten ec3.woelb.sektorwerte treffen I_w (Probe)",
              W.sektorwerte(s).Iw_probe / s.Iw, 1.0, 1e-9)
    s = make_section("UPN 200")
    close("B'2 UPN 200: I_w 9 559,6 cm⁶ (vorher 10 499,5)", s.Iw * 1e12, 9559.6, 0.05, " cm⁶")
    u = make_section("UPE 200")
    check("B'2 UPE 200 unverändert: 11 565,1 cm⁶ wie die geschlossene Formel",
          u.Iw == iw_u_profil(u.h, u.b, u.tw, u.tf) and abs(u.Iw * 1e12 - 11565.1) < 0.05, f"{u.Iw * 1e12:.2f}")
    # M_cr mit dem neuen I_w: Programm gegen Handformel (Gabellager, C1 = 1)
    from statik3d.ec3.stability import Mcr
    E, G = 210e9, 80.769e9
    for L in (2.0, 4.0):
        ist = Mcr(s, E, G, L)
        hand = math.pi ** 2 * E * s.Iz / L ** 2 * math.sqrt(s.Iw / s.Iz + L ** 2 * G * s.It / (math.pi ** 2 * E * s.Iz))
        close(f"B'2 UPN 200 L = {L:g} m: M_cr Programm = Handformel mit I_w 9 559,6 cm⁶", ist / 1e3, hand / 1e3,
              1e-6, " kNm")


def _modell_mit(*querschnitte, benutzt=None):
    from statik3d.model import Model, Material
    m = Model("U")
    m.add_material(Material.steel("S235"))
    for s in querschnitte:
        m.add_section(s)
    n = [m.add_node(i * 3.0, 0, 0) for i in range(len(benutzt or []) + 1)]
    for i, nm in enumerate(benutzt or []):
        m.add_element("beam", [n[i], n[i + 1]], "S235", nm)
    return m


def test_iw_gespeichert():
    from statik3d.profiles import make_section
    from statik3d.model import iw_u_profil, iw_u_profil_alt
    from statik3d import rechenverfahren as rv
    alt45 = make_section("UPN 200")
    alt45.name = "UPN 200 Stand 45"
    alt45.Iw = iw_u_profil(alt45.h, alt45.b, alt45.tw, alt45.tf)        # ohne Flanschneigung
    alt41 = make_section("UPN 200")
    alt41.name = "UPN 200 alt"
    alt41.Iw = iw_u_profil_alt(alt41.h, alt41.b, alt41.tw, alt41.tf)    # volle Flanschbreite
    eig = make_section("UPN 200")
    eig.name = "UPN 200 eigen"
    eig.Iw = 9000e-12
    upe = make_section("UPE 200")
    m = _modell_mit(alt45, alt41, eig, upe, benutzt=["UPN 200 Stand 45", "UPN 200 alt", "UPN 200 eigen", "UPE 200"])
    check("B'2 gespeicherter UPN mit dem Formelwert ohne Neigung (10 499,5) wird erkannt, eigener und UPE nicht",
          m.u_profile_iw_alt() == ["UPN 200 Stand 45", "UPN 200 alt"], m.u_profile_iw_alt())
    t = rv.modell_betroffen(m)
    check("B'2 Status „Wölbwiderstand“ nennt beide", "UPN 200 Stand 45" in t and "UPN 200 alt" in t, t[:200])
    zeilen = m.u_profile_iw_berichtigen()
    close("B'2 berichtigt: 10 499,5 → 9 559,6 cm⁶", m.sections["UPN 200 Stand 45"].Iw * 1e12, 9559.6, 0.05)
    close("B'2 berichtigt: 12 277,2 → 9 559,6 cm⁶", m.sections["UPN 200 alt"].Iw * 1e12, 9559.6, 0.05)
    check("B'2 eigener Wert 9 000 cm⁶ bleibt", m.sections["UPN 200 eigen"].Iw == 9000e-12)
    check("B'2 Protokollzeile nennt 10 499,5 → 9 559,6", zeilen and "10 499,5 → 9 559,6" in zeilen[0], zeilen)
    check("B'2 danach kein Status mehr", "U-Profile" not in rv.modell_betroffen(m) and not m.u_profile_iw_alt())
    mk = rv.merkmal("u_profil_iw")
    check("B'2 Merkmal u_profil_iw: Wechsel Stand 51", mk is not None and mk.wechsel[-1].stand == 51,
          mk and [w.stand for w in mk.wechsel])


# --------------------------------------------------------------------------
# A'10: Doppel-U und unbenutzte U-Profile
# --------------------------------------------------------------------------
def test_doppel_u():
    from statik3d.sections import double_channel
    from statik3d.profiles import make_section
    from statik3d.model import iw_u_profil, iw_u_profil_alt
    from statik3d import rechenverfahren as rv
    c = make_section("UPN 200")
    neu = double_channel("2 UPN 200", "UPN 200", gap=0.01)
    close("A'10 Doppel-U 2 UPN 200 neu: I_w = 2 · 9 559,6 cm⁶", neu.Iw * 1e12, 2 * c.Iw * 1e12, 1e-6)
    for wert, was in ((iw_u_profil_alt(c.h, c.b, c.tw, c.tf), "volle Flanschbreite (24 554,3)"),
                      (iw_u_profil(c.h, c.b, c.tw, c.tf), "ohne Flanschneigung (20 999,0)")):
        s = double_channel("2 UPN 200", "UPN 200", gap=0.01)
        s.Iw = s.Iw - 2 * c.Iw + 2 * wert
        m = _modell_mit(s, benutzt=["2 UPN 200"])
        check(f"A'10 Doppel-U mit {was}: erkannt", m.u_profile_iw_alt() == ["2 UPN 200"], m.u_profile_iw_alt())
        check("A'10 … Status nennt ihn", "2 UPN 200" in rv.modell_betroffen(m), rv.modell_betroffen(m)[:160])
        m.u_profile_iw_berichtigen()
        close("A'10 … berichtigt auf 19 119,2 cm⁶", m.sections["2 UPN 200"].Iw * 1e12, neu.Iw * 1e12, 1e-6)
        check("A'10 … danach kein Status", not m.u_profile_iw_alt() and "U-Profile" not in rv.modell_betroffen(m))
    s = double_channel("2 UPN 200", "UPN 200", gap=0.01)
    s.Iw = 15000e-12
    m = _modell_mit(s, benutzt=["2 UPN 200"])
    check("A'10 Doppel-U mit eigenem I_w: nicht erkannt", m.u_profile_iw_alt() == [])


class _Attrappe:
    def __init__(self, model, antwort):
        self.model, self.antwort = model, antwort
        self.fragen, self.gemerkt, self.protokoll = [], [], []
        self.analysis, self.results = object(), None
        outer = self

        class _Log:
            def appendPlainText(_s, t):
                outer.protokoll.append(t)
        self.log = _Log()

    def _fragen(self, titel, text):
        self.fragen.append(text)
        return self.antwort

    def merken(self, was, beschriftung=False):
        self.gemerkt.append(was)

    def refresh_all(self):
        pass

    def info(self, text):
        self.protokoll.append(text)

    def _ergebnisse_verworfen_nachziehen(self):
        pass


def test_unbenutzt():
    from statik3d.profiles import make_section
    from statik3d.model import iw_u_profil_alt
    from statik3d.gui.main import MainWindow
    from statik3d import rechenverfahren as rv
    upe = make_section("UPE 200")
    upe.Iw = iw_u_profil_alt(upe.h, upe.b, upe.tw, upe.tf)
    m = _modell_mit(upe, make_section("IPE 200"), benutzt=["IPE 200"])
    a = _Attrappe(m, True)
    r = MainWindow._u_profile_iw_fragen(a)
    check("A'10 nur unbenutztes U-Profil mit altem I_w: keine Frage, nichts verworfen, kein Status",
          not r and not a.fragen and a.analysis is not None and rv.modell_betroffen(m) == "",
          f"{a.fragen} {rv.modell_betroffen(m)!r}")
    check("A'10 … Wert bleibt", m.sections["UPE 200"].Iw == upe.Iw)
    # benutztes und unbenutztes: Frage nennt das benutzte; Ja berichtigt beide
    upn = make_section("UPN 200")
    upn.Iw = iw_u_profil_alt(upn.h, upn.b, upn.tw, upn.tf)
    upe2 = make_section("UPE 200")
    upe2.Iw = iw_u_profil_alt(upe2.h, upe2.b, upe2.tw, upe2.tf)
    m = _modell_mit(upn, upe2, benutzt=["UPN 200"])
    a = _Attrappe(m, True)
    r = MainWindow._u_profile_iw_fragen(a)
    erste = a.fragen[0].split("\n")[0] if a.fragen else ""
    check("A'10 benutzt UPN 200, unbenutzt UPE 200: Frage nennt nur das benutzte als betroffen",
          r and "UPN 200" in erste and "UPE 200" not in erste
          and "I_w der U-Profile nach der berichtigten Formel neu berechnen?" in a.fragen[0], a.fragen)
    check("A'10 … Ja: beide berichtigt, Ergebnisse verworfen",
          not m.u_profile_iw_alt() and a.analysis is None)


# --------------------------------------------------------------------------
# B'1: Woelbflaechenmoment S_omega des U-Profils
# --------------------------------------------------------------------------
def test_s_omega():
    from statik3d.profiles import make_section, UPN, UPE
    from statik3d.model import Section
    from statik3d.ec3 import woelb as W
    for nm, tab, neig in (("UPE 200", UPE[200], 0.0), ("UPE 400", UPE[400], 0.0),
                          ("UPN 200", UPN[200], 0.08), ("UPN 300", UPN[300], 0.08)):
        h, b, tw, tf, r = [x * 1e-3 for x in tab]
        s = make_section(nm)
        sw = W.sektorwerte(s)
        num = _mittellinie(h, b, tw, tf, neig)
        close(f"B'1 {nm}: max S_ω/t = numerisch (0,1 %)", sw.S_max / sw.t_S * 1e6,
              num["S_t"] * 1e6, num["S_t"] * 1e3, " cm³")
        check(f"B'1 {nm}: Ort wie numerisch (Flansch oder Steg)", sw.ort_S.startswith("Flansch") == (num["teil"] != 1)
              and sw.ort_S != "Stegmitte", f"{sw.ort_S} / numerisch {'Steg' if num['teil'] == 1 else 'Flansch'}")
        close(f"B'1 {nm}: ω_max = numerisch (0,1 %)", sw.omega_max, num["omega_max"], num["omega_max"] * 1e-3)
    # UPN-Masse mit parallelen Flanschen (Rechenmodell der Pruefagenten): 91,7 cm³
    h, b, tw, tf, r = [x * 1e-3 for x in UPN[200]]
    p = Section.channel("U parallel", h, b, tw, tf, r)
    sw = W.sektorwerte(p)
    close("B'1 UPN-200-Maße, parallele Flansche: S_ω/t 91,73 cm³ (Beleg s_omega_u.py, vorher 197,16)",
          sw.S_max / sw.t_S * 1e6, 91.727, 0.01, " cm³")
    # Steg: S in Stegmitte von Hand e t_w h_m^2 / 24 (positiv)
    bs, hm = b - tw / 2, h - tf
    e = 3 * tf * bs ** 2 / (6 * tf * bs + hm * tw)
    num = _mittellinie(h, b, tw, tf, 0.0)
    close("B'1 Stegmitte: |S_ω| = e t_w h_m²/24 = numerisch (33,5 cm⁴)", e * tw * hm ** 2 / 24 * 1e8,
          abs(num["S_mitte"]) * 1e8, 0.01, " cm⁴")
    # tau_w aus spannungen
    sp = W.spannungen(p, np.array([0.0]), np.array([1000.0]), np.array([0.0]))
    close("B'1 τ_w = M_t,w S_ω/(I_w t) mit 91,73 cm³", sp["tau_w"][0], 1000.0 * 91.727e-6 / p.Iw,
          1000.0 * 91.727e-6 / p.Iw * 2e-4, " N/m²")


def test_merkmale():
    from statik3d import rechenverfahren as rv
    for nm in ("u_profil_iw", "woelb_u_schub", "kerbfall_maske_ks"):
        mk = rv.merkmal(nm)
        check(f"Merkmal {nm} mit Stand 51 (Fehlerkorrektur)", mk is not None and mk.wechsel[-1].stand == 51
              and mk.wechsel[-1].art == rv.FEHLERKORREKTUR, mk and [w.stand for w in mk.wechsel])
    check("VERFAHRENSSTAND 51", rv.VERFAHRENSSTAND == 51, str(rv.VERFAHRENSSTAND))
    # Woelbnachweis an einem U-Profil -> Merkmal betrifft das Modell
    from statik3d.profiles import make_section
    m = _modell_mit(make_section("UPE 200"), benutzt=["UPE 200"])
    m.add_member("S1", [0])
    m.members["S1"].woelb_check = False
    mk = rv.merkmal("woelb_u_schub")
    check("woelb_u_schub: ohne Wölbnachweis nicht betroffen", mk is not None and not mk.betrifft(m))
    m.members["S1"].woelb_check = True
    check("woelb_u_schub: Stab mit U-Profil und Wölbnachweis betroffen", mk is not None and mk.betrifft(m))
    # Kerbfall nach der Maske: Zugstab Rund 40 mit Ermuedungslast und ohne Kerbfall
    from statik3d.model import FatigueLoad
    z = _zugstaebe()
    mk = rv.merkmal("kerbfall_maske_ks")
    z.fatigue_loads["E"] = FatigueLoad("E", case_max="LF1", cycles=1e5)
    check("kerbfall_maske_ks: Zugstäbe ohne Kerbfall mit Ermüdungslast betroffen",
          mk is not None and mk.betrifft(z))
    wo = mk.im_ergebnis(z, None) if mk is not None and mk.im_ergebnis else ""
    check("kerbfall_maske_ks: nennt Z1, Z2 (Rund 40), nicht Z3", "Z1" in (wo or "") and "Z3" not in (wo or ""), wo)
    for nm in ("Z1", "Z2"):
        z.members[nm].detail_category = 46.5302e6
    check("kerbfall_maske_ks: mit Kerbfall nicht mehr betroffen", mk is not None and not mk.betrifft(z))


def main():
    for t in (test_stabmaske, test_bericht_und_tabelle, test_protokoll_und_ks, test_iw_upn,
              test_iw_gespeichert, test_doppel_u, test_unbenutzt, test_s_omega, test_merkmale):
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, repr(ex))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Prüfungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
