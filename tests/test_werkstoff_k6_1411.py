"""
Behebungen vom 14.11.2026, zweite Runde (BEFUNDE-2026-11-14-RUNDE2.md, Agent
„werkstoff“): Werte ueber 80 mm Erzeugnisdicke ohne Dickentabelle.

A'3   Kopfplatte ueber 80 mm ohne Dickentabelle: die Drehfeder S_j des
      Anschlusses haengt nicht an f_y und sitzt wieder in der Rechnung;
      ein uebersprungener Anschluss steht im Protokoll und in an.info.
A'6   Sortenwechsel in der Werkstofftabelle und in der Werkstoffmaske leert
      die Stufe ueber 80 mm (Erzeugnisnorm) wie der Werkstoffdialog.
A'11  Kreisring ueber 80 mm: Meldung statt still ohne Beurteilung;
      Joint.ort() zaehlt Elemente ab 0; Bericht zeigt beim kurzen Zylinder
      C_θ,s (Tab. D.4); Th-II-Vorkruemmungskriterium ohne f_y: Meldung.

Zwei Wege je Zahl: Kragarm mit Drehfeder als Programm gegen starr gerechneten
Kragarm plus P L²/S_j (geschlossen), S_j ohne f_y gegen S_j mit eingetragenem
f_y; C_θ,s gegen Tab. D.4 von Hand; Vorkruemmungskriterium gegen
N_Ed ≷ N_cr/4 von Hand und gegen den Wert mit eingetragenem f_y.

Aufruf:  python -m tests.test_werkstoff_k6_1411
"""
import contextlib
import io
import math
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:96s} {str(detail)[:220]}")
    return ok


# --------------------------------------------------------------------------
# A'3: Anschluss mit Kopfplatte ueber 80 mm
# --------------------------------------------------------------------------
P_, L_ = 20e3, 4.0


def _kragarm(tp, eingabe=None, modellierung="automatisch"):
    from statik3d.model import Model, Material, Section
    from statik3d import mesher
    from statik3d.joints import templates, anschluss
    m = Model("A")
    mt = Material.steel("S355")
    if eingabe:
        mt.erzeugnisnorm_setzen(*eingabe)
    m.add_material(mt)
    m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
    ids = mesher.line_of_beams(m, "S355", "IPE300", (0, 0, 0), (L_, 0, 0), n=4)
    m.fix(ids[0], "all")
    m.load_node(ids[-1], Fz=-P_)
    t = templates.propose("kopfplatte", m, 0, end=0, N=0.0, Vz=20000.0, My=80000.0)
    t.tp = tp
    j = anschluss.als_joint(t, name="KP")
    j.modellierung = modellierung
    m.joints[j.name] = j
    return m, ids


def _rechnen(m, ids, progress=None):
    from statik3d import solver
    with contextlib.redirect_stdout(io.StringIO()):
        an = solver.solve_all(m, workers=1, combinations=False, progress=progress)
    res = an.cases[list(an.cases)[0]]
    return an, -float(res.u[ids[-1]][2])


def test_a3_feder():
    from statik3d.joints import anschluss
    # S_j zweimal: ohne f_y (90 mm, nur Sorte) und mit eingetragenem f_y 300
    m0, ids0 = _kragarm(0.090)
    m1, ids1 = _kragarm(0.090, (300e6, 450e6))
    log0 = []
    f0 = anschluss.federn_setzen(m0, log0)
    f1 = anschluss.federn_setzen(m1, [])
    S0 = (f0.get("KP") or (None, 0.0))[1]
    S1 = (f1.get("KP") or (None, 0.0))[1]
    check("A'3 Kopfplatte 90 mm ohne Dickentabelle: Drehfeder gesetzt (vorher übersprungen)",
          (f0.get("KP") or ("",))[0] == "feder", f"{f0.get('KP')} | {log0}")
    check("A'3 S_j ohne f_y = S_j mit eingetragenem f_y 300 N/mm² (S_j hängt nicht an f_y)",
          S0 > 0 and abs(S0 - S1) <= 1e-9 * S1, f"{S0 / 1e6:.4f} / {S1 / 1e6:.4f} MNm/rad")
    check("A'3 S_j = 22,716 MNm/rad (Stand c766722 mit f_y 335 gemessen, s4_anschluss.py)",
          abs(S0 / 1e6 - 22.716486) < 1e-5, f"{S0 / 1e6:.6f}")
    # Gelenkkennwerte: S_j da, M_j,Rd und Rotationsvermoegen nicht bestimmt, mit Meldung
    t = anschluss.vorlage(m0, m0.joints["KP"])
    g = t.momenten_rotation(stuetze={}, rahmen="ausgesteift")
    hw = " ".join(g.hinweise)
    check("A'3 ohne f_y: M_j,Rd nicht bestimmt (0), Hinweis nennt f_y nach Erzeugnisnorm",
          g.M_j_Rd == 0.0 and "Erzeugnisnorm" in hw and "M_j,Rd" in hw, hw[:200])
    check("A'3 ohne f_y: Rotationsvermögen nicht nachgewiesen, Grund nennt f_y",
          not g.rotation_ok and "f_y" in g.rotation_grund, g.rotation_grund[:160])
    # Kragarm: Programm gegen geschlossene Loesung
    an0, u0 = _rechnen(m0, ids0)
    # Nachweis mit den Ergebnissen: weiterhin keiner (C4), mit der Meldung
    c = anschluss.check_joint(m0, m0.joints["KP"], dict(an0.cases), an0)
    check("A'3 Anschlussnachweis bleibt ohne f_y ungeführt (C4-Meldung)",
          "Erzeugnisnorm" in (c.fehler or "") and c.status() == "nicht geführt", (c.fehler or "")[:120])
    ms, idss = _kragarm(0.090, modellierung="starr")
    _a, us = _rechnen(ms, idss)
    zus = P_ * L_ * L_ / S0
    check("A'3 Kragarm u_z = u_z starr + P L²/S_j (Programm gegen geschlossene Lösung)",
          abs((u0 - us) - zus) <= 1e-3 * zus, f"{u0 * 1e3:.3f} − {us * 1e3:.3f} = {(u0 - us) * 1e3:.3f} mm, "
                                               f"P L²/S_j {zus * 1e3:.3f} mm")
    check("A'3 Kragarm u_z = 39,97 mm (vorher 25,88 mm, starr)", abs(u0 * 1e3 - 39.969) < 0.01,
          f"{u0 * 1e3:.3f} mm")
    check("A'3 an.info: kein übersprungener Anschluss", not an0.info.get("anschluesse_uebersprungen"),
          str(an0.info.get("anschluesse_uebersprungen")))


def test_a3_protokoll():
    """Ein Anschluss, dessen Steifigkeit sich nicht bestimmen laesst (Werkstoff
    ohne f_y und Sorte), steht im Protokoll der Rechnung und in an.info."""
    m, ids = _kragarm(0.050)
    mt = m.materials["S355"]
    mt.fy, mt.grade = None, ""
    zeilen = []
    an, u = _rechnen(m, ids, progress=lambda t, *a: zeilen.append(str(t)))
    ueb = an.info.get("anschluesse_uebersprungen") or {}
    check("A'3 übersprungener Anschluss in an.info[„anschluesse_uebersprungen“]", "KP" in ueb, str(ueb)[:160])
    z = [x for x in zeilen if "Anschluss KP" in x]
    check("A'3 Protokoll der Rechnung: WARNUNG mit Grund und „starr“",
          any(x.startswith("WARNUNG") and "starr" in x and "f_y" in x for x in z), " | ".join(z)[:220])
    check("A'3 Zusammenfassung der Rechnung nennt den Anschluss",
          "Anschluss KP" in an.summary(), "")


def test_a3_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("anschluss_feder_ueber_80")
    ja, _ = _kragarm(0.090)
    nein1, _ = _kragarm(0.050)
    nein2, _ = _kragarm(0.090, (300e6, 450e6))
    check("A'3 Merkmal Stand 53, Fehlerkorrektur",
          mk is not None and mk.wechsel[-1].stand == 53 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.VERFAHRENSSTAND >= 53, str(mk and mk.wechsel))
    check("A'3 Merkmal: betrifft Kopfplatte 90 mm ohne Tabelle, nicht 50 mm, nicht mit Eintrag",
          mk is not None and mk.betrifft(ja) and not mk.betrifft(nein1) and not mk.betrifft(nein2))


# --------------------------------------------------------------------------
# A'6: Sortenwechsel leert die Stufe ueber 80 mm
# --------------------------------------------------------------------------
def _mt_eingetragen():
    from statik3d.model import Material
    mt = Material.steel("S355")
    mt.erzeugnisnorm_setzen(285e6, 470e6)
    return mt


def test_a6_material():
    mt = _mt_eingetragen()
    zeilen = mt.sorte_wechseln("S235") if hasattr(mt, "sorte_wechseln") else []
    check("A'6 Material.sorte_wechseln S355 → S235: über 80 mm kein f_y, kein f_u (Meldung C4)",
          mt.grade == "S235" and not mt.yield_strength(0.1) and not mt.zugfestigkeit_angegeben(0.1)
          and bool(mt.dicke_ohne_wert(0.1)) and bool(mt.dicke_ohne_wert(0.1, "fu")),
          f"{mt.grade} f_y {mt.yield_strength(0.1)}")
    check("A'6 … bis 80 mm die Werte der neuen Sorte (Tab. 3.1: 60 mm f_y 215)",
          abs(mt.yield_strength(0.06) - 215e6) < 1 and abs(mt.zugfestigkeit_angegeben(0.06) - 360e6) < 1,
          f"{mt.yield_strength(0.06)}")
    check("A'6 … eine Protokollzeile nennt den Wechsel und „über 80 mm“",
          len(zeilen) == 1 and "S355" in zeilen[0] and "S235" in zeilen[0] and "über 80 mm" in zeilen[0],
          " | ".join(zeilen))
    mt2 = _mt_eingetragen()
    z2 = mt2.sorte_wechseln("s 355") if hasattr(mt2, "sorte_wechseln") else ["-"]
    check("A'6 gleiche Sorte anders geschrieben: Stufe bleibt, keine Zeile",
          not z2 and abs(mt2.yield_strength(0.1) - 285e6) < 1, f"{z2} {mt2.yield_strength(0.1)}")


def _zelle(sorte):
    from statik3d.gui import main as gm
    from statik3d.model import Model
    mod = Model("Z")
    mod.add_material(_mt_eingetragen())
    s = mock.MagicMock()
    s.model = mod
    s.tbl_mat.modell.zeilen = [["S355"]]
    gm.MainWindow._mat_aendern(s, 0, 5, sorte)
    return mod.materials["S355"], s


def _texte(s):
    aus = []
    for f in (s.info, s._zelle_uebernommen, s.hinweis):
        aus += [str(c.args[0]) for c in f.call_args_list if c.args]
    return aus


def test_a6_tabelle():
    v, s = _zelle("S235")
    t = _texte(s)
    check("A'6 Werkstofftabelle Sorte S355 → S235: f_y 100 mm leer (vorher 285)",
          v.grade == "S235" and not v.yield_strength(0.1) and bool(v.dicke_ohne_wert(0.1)),
          f"{v.yield_strength(0.1)}")
    check("A'6 … Protokollzeile über 80 mm", any("über 80 mm" in x for x in t), " | ".join(t)[:200])
    v2, _s2 = _zelle("S355")
    check("A'6 Werkstofftabelle gleiche Sorte: Stufe bleibt (285)", abs(v2.yield_strength(0.1) - 285e6) < 1,
          f"{v2.yield_strength(0.1)}")


def test_a6_maske():
    from statik3d.gui.main import MainWindow
    from statik3d.model import Model
    m = Model("t")
    m.add_material(_mt_eingetragen())
    s = mock.MagicMock()
    s.model = m
    w = {"name": "S355", "E": "210", "nu": "0.3", "rho": "7850", "alpha": "12",
         "fy": "355", "fu": "510", "grade": "S235"}
    MainWindow._eigenschaften_uebernehmen(s, "werkstoff", "S355", w, False, {"grade"})
    v = m.materials["S355"]
    t = _texte(s)
    check("A'6 Werkstoffmaske Sorte S355 → S235: f_y 100 mm leer (vorher 285)",
          v.grade == "S235" and not v.yield_strength(0.1) and bool(v.dicke_ohne_wert(0.1)),
          f"{v.grade} {v.yield_strength(0.1)}")
    check("A'6 … Protokollzeile über 80 mm", any("über 80 mm" in x for x in t), " | ".join(t)[:200])


def test_a6_merkmal():
    from statik3d import rechenverfahren as rv
    from statik3d.model import Model, Section
    from statik3d import mesher
    mk = rv.merkmal("werkstoff_sorte_ueber_80")

    def modell(mt):
        m = Model("W")
        m.add_material(mt)
        m.add_section(Section.i_profile("IPE300", 0.300, 0.150, 0.0071, 0.0107))
        mesher.line_of_beams(m, mt.name, "IPE300", (0, 0, 0), (1, 0, 0), n=1)
        return m
    alt = _mt_eingetragen()
    alt.grade = "S235"                    # so liess die Zelle sie bis zum 14.11.2026
    neu = _mt_eingetragen()
    check("A'6 Merkmal Stand 53, Fehlerkorrektur",
          mk is not None and mk.wechsel[-1].stand == 53 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR)
    check("A'6 Merkmal: Sorte ≠ Sorte der Stufe über 80 mm betroffen, gleiche Sorte nicht",
          mk is not None and mk.betrifft(modell(alt)) and not mk.betrifft(modell(neu)))
    check("A'6 Merkmal: Text am Modell nennt den Werkstoff",
          mk is not None and mk.im_modell is not None and "S355" in mk.im_modell(modell(alt))
          and mk.im_modell(modell(neu)) == "")


# --------------------------------------------------------------------------
# A'11: Meldungen und Anzeige
# --------------------------------------------------------------------------
def test_a11_scheibe():
    import types
    from statik3d.model import Material
    from statik3d import scheibeneinleitung as SCH
    mod = types.SimpleNamespace(materials={"S355": Material.steel("S355")},
                                koerper={"Platte": types.SimpleNamespace(material="S355")})
    fy = SCH.fy_koerper(mod, "Platte", 0.100)
    meld = SCH.fy_meldung_koerper(mod, "Platte", 0.100) if hasattr(SCH, "fy_meldung_koerper") else ""
    z = dict(einleitung=SCH.RING, d_aussen=0.060, d_innen=0.030, F=3000e3, fy=fy, dicke=0.100,
             fy_meldung=meld)
    SCH.pressung_setzen(z)
    p = 3000e3 / (math.pi / 4 * (0.06 ** 2 - 0.03 ** 2))
    txt = SCH.pressung_text(z)
    check("A'11 Kreisring 100 mm ohne Tabelle: Pressung 1414,7 N/mm² (Hand F/A)",
          abs(z["pressung"] - p) < 1.0, f"{z['pressung'] / 1e6:.1f}")
    check("A'11 … Hinweis „nicht beurteilt“ mit C4-Meldung statt leer",
          fy is None and "Erzeugnisnorm" in z["hinweis"] and "nicht beurteilt" in z["hinweis"], z["hinweis"])
    check("A'11 … Pressungstext nennt das fehlende f_y", "f_y" in txt and "80 mm" in txt, txt)
    # 60 mm: unveraendert „Auflage prüfen“
    z2 = dict(einleitung=SCH.RING, d_aussen=0.060, d_innen=0.030, F=3000e3,
              fy=SCH.fy_koerper(mod, "Platte", 0.060), dicke=0.060,
              fy_meldung=SCH.fy_meldung_koerper(mod, "Platte", 0.060) if hasattr(SCH, "fy_meldung_koerper") else "")
    SCH.pressung_setzen(z2)
    check("A'11 … 60 mm unverändert: Auflage prüfen", z2["hinweis"] == SCH.AUFLAGE_PRUEFEN, z2["hinweis"])


def test_a11_scheibe_modell():
    """Die Zeile aus scheiben() traegt die Meldung (Koerperdicke 100 mm)."""
    from statik3d import fugen, scheibeneinleitung as SCH
    from tests.test_scheibe_kreisring import blech
    m = blech(h=0.006, ordnung=1, F=900e3)
    SCH.alle_auf_kreisring(m)
    fugen.starre_kopplungen_erneuern(m, [])
    with mock.patch.object(SCH, "dicke_koerper", lambda model, k, cache=None: 0.100):
        z = SCH.scheiben(m)[0]
    check("A'11 scheiben(): Körper 100 mm ohne Tabelle – Hinweis mit Meldung statt leer",
          z["fy"] is None and "Erzeugnisnorm" in z["hinweis"], f"{z['hinweis']!r} | {SCH.pressung_text(z)}")


def test_a11_ort():
    from statik3d.model import Joint
    check("A'11 Joint.ort(): Element ab 0 (Index 2 → „Element 2, Ende E“)",
          Joint("J", "kopfplatte", 2, 1).ort() == "Element 2, Ende E", Joint("J", "kopfplatte", 2, 1).ort())


def test_a11_c_theta_s():
    from statik3d.ec3 import schalenbeulen as S
    for rand, soll in (("BC2-BC2", lambda w: 1 + 3 / w ** 1.35),
                       ("BC1-BC1", lambda w: 1.5 + 10 / w ** 2 - 5 / w ** 3)):
        z = S.zylinder(r=1.0, t=0.010, l=0.5, fy=355e6, sigma_theta=20e6, rand=rand)
        w = z.werte
        hand = soll(w["omega"])
        zurueck = w["umfang"]["sigma_Rcr"] / (0.92 * 210e9 * 0.01 / 1.0) * w["omega"]
        check(f"A'11 {rand} kurz: werte C_theta_s = Tab. D.4 von Hand = aus σ_θ,Rcr zurück ({hand:.3f})",
              abs((w.get("C_theta_s") or 0) - hand) < 1e-9 and abs(zurueck - hand) < 1e-9,
              f"{w.get('C_theta_s')} / {zurueck:.4f}")


def test_a11_bericht():
    from statik3d.model import Model, Material, ShellProp
    from statik3d import solver
    from statik3d.report.html import Report
    mz = Model("Rohr")
    mz.add_material(Material.steel("S355"))
    mz.add_shell_prop(ShellProp("t8", 0.008))
    nu_, nz, rr, ll = 24, 4, 0.5, 0.3
    idz = {}
    for k in range(nz + 1):
        for j in range(nu_):
            w_ = 2 * math.pi * j / nu_
            idz[(j, k)] = mz.add_node(rr * math.cos(w_), rr * math.sin(w_), ll * k / nz)
    elz = []
    for k in range(nz):
        for j in range(nu_):
            j2 = (j + 1) % nu_
            elz.append(mz.add_element("shell4", [idz[(j, k)], idz[(j2, k)], idz[(j2, k + 1)], idz[(j, k + 1)]],
                                      "S355", "t8"))
    for j in range(nu_):
        mz.fix(idz[(j, 0)], "all")
        mz.load_node(idz[(j, nz)], Fz=-1200e3 / nu_)
    mz.add_beulfeld("Mantel", elz, art="zylinder", qualitaet="B")
    with contextlib.redirect_stdout(io.StringIO()):
        anz = solver.solve_all(mz, combinations=False, envelopes=False, design=True)
    c = anz.beulen.felder["Mantel"]
    zyl = (c.werte or {}).get("zylinder") or {}
    hz = Report(mz, anz).html()
    cts = zyl.get("C_theta_s")
    from statik3d.report.html import fmt
    check("A'11 Bericht kurzer Zylinder: „C_θ,s = …“ (Tab. D.4) statt C_θ",
          zyl.get("bereich_umfang") == "kurz" and cts is not None and f"C_θ,s = {fmt(cts, 3)}" in hz,
          f"{zyl.get('bereich_umfang')} {cts}")


def test_a11_theorie2():
    from statik3d.model import Model, Material, Section
    from statik3d import mesher, theorie2
    m = Model("T")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.i_profile("I90", 0.500, 0.450, 0.050, 0.090))
    mesher.line_of_beams(m, "S355", "I90", (0, 0, 0), (0, 0, 8), n=4)
    if not m.members:
        m.add_member("S1", list(range(len(m.elements))))
    mem = next(iter(m.members.values()))
    sec = m.sections["I90"]
    Ncr = math.pi ** 2 * 210e9 * sec.Iz / 8.0 ** 2
    m2 = Model("T2")
    mt2 = Material.steel("S355")
    mt2.erzeugnisnorm_setzen(285e6, 450e6)
    m2.add_material(mt2)
    m2.add_section(Section.i_profile("I90", 0.500, 0.450, 0.050, 0.090))
    mesher.line_of_beams(m2, "S355", "I90", (0, 0, 0), (0, 0, 8), n=4)
    if not m2.members:
        m2.add_member("S1", list(range(len(m2.elements))))
    mem2 = next(iter(m2.members.values()))
    for N in (2000e3, 0.3 * Ncr):
        k = theorie2.vorkruemmung_noetig(m, mem, N)
        k2 = theorie2.vorkruemmung_noetig(m2, mem2, N)
        hand = N > Ncr / 4.0
        check(f"A'11 Th II N = {N / 1e3:.0f} kN ohne f_y: Entscheidung = N_Ed > N_cr/4 von Hand = mit f_y 285",
              k["noetig"] == hand == k2["noetig"], f"{k['noetig']} {hand} {k2['noetig']}")
        check(f"A'11 Th II N = {N / 1e3:.0f} kN ohne f_y: Meldung statt still 235 (kein λ̄ mit 235)",
              "Erzeugnisnorm" in k["grund"] and "235" not in k["grund"], k["grund"][:200])
    # die Ersatzlasten sammeln die Meldung (auch fuer angesetzte Vorkruemmungen)
    with mock.patch.object(theorie2, "_member_N", lambda model, mem_, res: -0.3 * Ncr):
        _F, info = theorie2.ersatzlasten_vorkruemmung(m, None)
    check("A'11 Th II Ersatzlasten: info[„meldungen“] nennt das fehlende f_y",
          any("Erzeugnisnorm" in x for x in info.get("meldungen") or []), str(info.get("meldungen"))[:160])


def main():
    for t in (test_a3_feder, test_a3_protokoll, test_a3_merkmal, test_a6_material, test_a6_tabelle,
              test_a6_maske, test_a6_merkmal, test_a11_scheibe, test_a11_scheibe_modell, test_a11_ort,
              test_a11_c_theta_s, test_a11_bericht, test_a11_theorie2):
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
