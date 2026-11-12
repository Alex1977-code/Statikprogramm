"""Traglast, Mechanismus und Gueltigkeitsgrenze der plastischen Rechnung (16.10.2026).

Anlass: Am Pruefblech aus tests/test_scheibe_kreisring (Blech 60 x 60 x 20 mm,
S355, Bohrung 20, Kreisring 20/37, tet10, Endvorspannung 900 kN) meldete die
plastische Rechnung „konvergiert“ mit ε_p max = 2 399 (rund 240 000 %). Der
Newton hatte im Spannschritt richtig „nicht konvergiert“ gemeldet (600 und
900 kN), aber nur ein vorlaeufiger Kontakt ging an den Lastfall weiter: der
Spannzustand wurde in der weggelaufenen Lage verriegelt (4,56 m Einsenkung,
Verriegelungskraft 1 369,6 MN), und der Lastfall begann bei diesem Zustand, der
mit der eingefrorenen plastischen Last per Konstruktion im Gleichgewicht war;
gemessen wurde dazu gegen ‖F_lock‖ = 1,94e9 N statt der Sollkraft
(scratchpad tl_werk/tet10_900.log).

Auftrag des Anwenders vom 16.10.2026 (wörtlich): „Oberhalb der Traglast gibt es
bei ideal plastischem Material kein Gleichgewicht, das Programm muss ‚Traglast
überschritten‘ mit dem letzten konvergierten Lastfaktor melden.“ Dazu
Mechanismus, Gültigkeitsgrenze ε_p,max (Vorgabe 20 % bzw. Bruchdehnung) und je
plastischem Lauf ε_p,max mit Ort sowie ΣR und ΣM.

Prüfmodelle:

* Zugstab aus Volumen, Querschnitt 50 x 50 mm, S355 mit f_u = 510 N/mm²
  (bilinear E/100 bis f_u, danach ideal plastisch): F_lim = A f_u = 1 275 kN.
  Das letzte Fünftel ist elastisch (Werkstoff ohne f_y), dort greift die Last
  an - so bestimmt die Einleitung nicht die Grenzlast.
* Kragträger aus Volumen unter reinem Moment (Kräftepaar am elastischen Kopf),
  f_u = f_y: ideal plastisch ab f_y, M_pl = f_y b h²/4 (rechteckiger
  Querschnitt, ganz durchplastiziert).
* Das Prüfblech mit 900 kN.

Aufruf:  python -m tests.test_traglast
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import elementwahl, mesher, solver                    # noqa: E402
from statik3d import gleichgewicht as gg                            # noqa: E402
from statik3d import plastizitaet as pl                             # noqa: E402
from statik3d.model import Material, Model                          # noqa: E402

RESULTS = []

E, NU, FY, FU = 210e9, 0.3, 355e6, 510e6
B_ZUG, L_ZUG = 0.05, 0.3
F_LIM = B_ZUG * B_ZUG * FU
B_BAL, H_BAL, L_BAL = 0.04, 0.08, 0.6
M_PL = FY * B_BAL * H_BAL ** 2 / 4.0


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:86s} {str(detail)[:220]}")
    return ok


def _symmetrie(m, X):
    for i in range(m.nn):
        for d in range(3):
            if abs(X[i, d]) < 1e-12:
                m.fix(i, [d])


def zugstab(faktor, typ="tet4", fu=FU):
    m = Model("Zugstab")
    m.add_material(Material("S355", E=E, nu=NU, rho=0.0, fy=FY, fu=fu))
    m.add_material(Material("Kopf", E=E, nu=NU, rho=0.0))
    mesher.grid_box(m, "S355", L_ZUG, B_ZUG, B_ZUG, 6, 2, 2, typ="tet4")
    X = np.asarray(m.nodes, float)
    for e in m.elements:
        if X[list(e.nodes)].mean(axis=0)[0] > 0.8 * L_ZUG:
            e.mat = "Kopf"
    if typ == "tet10":
        elementwahl.tet4_zu_tet10(m)
    X = np.asarray(m.nodes, float)
    _symmetrie(m, X)
    ende = [i for i in range(m.nn) if abs(X[i, 0] - L_ZUG) < 1e-12]
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for i in ende:
        m.load_node(i, Fx=faktor * F_LIM / len(ende))
    m.active_case = "LF1"
    m.plastizitaet = pl.Plastizitaet(an=True)
    return m


def balken(faktor, typ="tet10"):
    m = Model("Balken")
    m.add_material(Material("S355", E=E, nu=NU, rho=0.0, fy=FY, fu=FY))
    m.add_material(Material("Kopf", E=E, nu=NU, rho=0.0))
    nx = 12
    mesher.grid_box(m, "S355", L_BAL, B_BAL, H_BAL, nx, 2, 4, typ="tet4")
    X = np.asarray(m.nodes, float)
    for e in m.elements:
        if X[list(e.nodes)].mean(axis=0)[0] > L_BAL - 2 * L_BAL / nx:
            e.mat = "Kopf"
    if typ == "tet10":
        elementwahl.tet4_zu_tet10(m)
    X = np.asarray(m.nodes, float)
    for i in range(m.nn):
        if abs(X[i, 0]) < 1e-12:
            m.fix(i, [0, 1, 2])
    P = faktor * M_PL / H_BAL
    oben = [i for i in range(m.nn) if abs(X[i, 0] - L_BAL) < 1e-12 and abs(X[i, 2] - H_BAL) < 1e-12]
    unten = [i for i in range(m.nn) if abs(X[i, 0] - L_BAL) < 1e-12 and abs(X[i, 2]) < 1e-12]
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for i in oben:
        m.load_node(i, Fx=-P / len(oben))
    for i in unten:
        m.load_node(i, Fx=P / len(unten))
    m.active_case = "LF1"
    m.plastizitaet = pl.Plastizitaet(an=True)
    return m


def rechnen(m):
    meld = []
    r = solver.solve_static(m, progress=lambda t, *a: meld.append(str(t)), workers=1)
    return r, meld


def _pz(r):
    return (r.info.get("plastizitaet") or {}) if r is not None else {}


def _gueltig_text(r):
    return solver.gueltigkeit(r.info)


# ---------------------------------------------------------------------------
def test_zugstab():
    print("\n--- 1. Zugstab aus Volumen: F_lim = A f_u ---")
    for typ in ("tet4", "tet10"):
        r, meld = rechnen(zugstab(0.9, typ))
        pz = _pz(r)
        check(f"{typ}, 0,9 F_lim: konvergiert, gültig, keine Traglastmeldung",
              pz.get("konvergiert") is True and not _gueltig_text(r) and not pz.get("traglast"),
              f"ε_p {pz.get('eps_p_max')}, {_gueltig_text(r)!r}")
        # ε_p am Stab: (σ − f_y)/H mit H = E/99. Das Maximum sitzt am Übergang zum
        # elastischen Kopf (Querdehnung behindert): gemessen tet4 −3,8 %, tet10 +12,6 %
        soll = (0.9 * FU - FY) / (E / 99.0)
        ep = float(pz.get("eps_p_max") or 0.0)
        check(f"{typ}, 0,9 F_lim: ε_p,max ≈ (0,9 f_u − f_y)/H = {soll * 100:.3f} % (± 15 %)",
              abs(ep - soll) <= 0.15 * soll, f"{ep * 100:.3f} %")
        r, meld = rechnen(zugstab(1.2, typ))
        pz = _pz(r)
        tl = pz.get("traglast") or {}
        lam = float(tl.get("lastfaktor", -1.0))
        check(f"{typ}, 1,2 F_lim: „Traglast überschritten“, nicht konvergiert",
              tl.get("ueberschritten") is True and pz.get("konvergiert") is False,
              str(tl.get("text", ""))[:160])
        # tet4 sperrt: die konstante Dehnung je Element und das volumentreue
        # Fliessen behindern die Querkontraktion, die Spannung wird dreiachsig und
        # σ_x steigt ueber f_u - gemessen konvergiert bei 1,1 F_lim mit ε_p 92,5 %;
        # das faengt die Gueltigkeitsgrenze (unten)
        oben = 1.0 + 1e-9 if typ == "tet10" else 1.15
        check(f"{typ}, 1,2 F_lim: letzter konvergierter Faktor · 1,2 F_lim zwischen 0,95 und "
              f"{'1,0' if typ == 'tet10' else '1,15 (Sperren)'} F_lim",
              0.95 <= lam * 1.2 <= oben, f"λ {lam:.5f} → {lam * 1.2:.4f} F_lim")
        g = _gueltig_text(r)
        # Wortlaut seit 16.10.2026 nachmittags (Vorgabe des Anwenders, tests/test_traglast_meldung)
        check(f"{typ}, 1,2 F_lim: NICHT gültig mit „Kein Gleichgewicht gefunden bei Laststufe …“",
              g.startswith("NICHT gültig") and "Kein Gleichgewicht gefunden bei Laststufe" in g, g[:160])
        # Der letzte konvergierte Zustand bleibt sichtbar und gekennzeichnet
        ep = float(pz.get("eps_p_max") or 0.0)
        check(f"{typ}, 1,2 F_lim: gezeigt ist der letzte konvergierte Zustand (gekennzeichnet in "
              "Zusammenfassung)", "Letzter konvergierter Lastanteil" in r.summary(), f"ε_p {ep * 100:.3f} %")
        if typ == "tet10":
            check("tet10, 1,2 F_lim: der gezeigte Zustand bleibt in der Theorie kleiner Verzerrungen (ε_p < 20 %)",
                  ep < 0.2, f"ε_p {ep * 100:.3f} %")
        else:
            check("tet4, 1,2 F_lim: der gesperrte Zustand (ε_p über 20 %) ist zusätzlich als außerhalb der "
                  "Theorie kleiner Verzerrungen gekennzeichnet", ep < 0.2 or "kleiner Verzerrungen" in g, g[:200])
        Rx = float(r.reactions[:, 0].sum()) if r.reactions is not None else 0.0
        check(f"{typ}, 1,2 F_lim: Lagerkraft des gezeigten Zustands = λ · 1,2 F_lim",
              abs(-Rx - lam * 1.2 * F_LIM) <= 2e-3 * F_LIM, f"ΣR_x {Rx / 1e3:.2f} kN gegen "
              f"{lam * 1.2 * F_LIM / 1e3:.2f} kN")
        check(f"{typ}, 1,2 F_lim: Protokoll nennt Traglast und Faktor",
              any("Kein Gleichgewicht gefunden bei Laststufe" in z for z in meld), "")
        if typ == "tet10":
            import tempfile
            from statik3d.report import write_report
            with tempfile.TemporaryDirectory() as td:
                pfad = write_report(r.model, solver.Analysis(r.model, cases={"LF1": r}),
                                    os.path.join(td, "b.md"), fmt="md")
                text = open(pfad, encoding="utf-8").read()
            check("tet10, 1,2 F_lim: der Bericht nennt das Ergebnis NICHT GÜLTIG mit der Traglast",
                  "NICHT GÜLTIG – LF1: Kein Gleichgewicht gefunden" in text, "")


def test_balken():
    print("\n--- 2. Kragträger aus Volumen unter reinem Moment: M_pl = f_y b h²/4 ---")
    r, _m = rechnen(balken(0.9))
    pz = _pz(r)
    check("tet10, 0,9 M_pl: konvergiert, gültig", pz.get("konvergiert") is True and not _gueltig_text(r),
          f"ε_p {pz.get('eps_p_max')}")
    r, meld = rechnen(balken(1.2))
    pz = _pz(r)
    tl = pz.get("traglast") or {}
    lam = float(tl.get("lastfaktor", -1.0))
    check("tet10, 1,2 M_pl: Traglast überschritten", tl.get("ueberschritten") is True, str(tl.get("text"))[:160])
    check("tet10, 1,2 M_pl: letzter konvergierter Faktor · 1,2 M_pl zwischen 0,95 und 1,05 M_pl",
          0.95 <= lam * 1.2 <= 1.05, f"λ {lam:.5f} → {lam * 1.2:.4f} M_pl")
    mech = pz.get("mechanismus") or {}
    check("tet10, 1,2 M_pl: Mechanismus erkannt (Verschiebung wächst, Spannung bleibt)",
          bool(mech) and "Mechanismus" in str(mech.get("text", "")), str(mech.get("text", ""))[:200])
    g = _gueltig_text(r)
    check("tet10, 1,2 M_pl: NICHT gültig, Mechanismus genannt", g.startswith("NICHT gültig") and "Mechanismus" in g,
          g[:200])
    check("tet10, 1,2 M_pl: Newton bricht am Mechanismus früh ab (höchstens 120 Schritte)",
          int(pz.get("iterationen", 999)) <= 120, f"{pz.get('iterationen')} Schritte")


def test_gueltigkeitsgrenze():
    print("\n--- 3. Gültigkeitsgrenze ε_p,max ---")
    r, _m = rechnen(zugstab(0.9))
    dg = _pz(r).get("dehnungsgrenze") or {}
    check("Vorgabe 20 %: Zugstab 0,9 F_lim (ε_p 5 %) gültig, Grenze steht im Ergebnis",
          not _gueltig_text(r) and abs(float(dg.get("grenze", 0)) - 0.20) < 1e-12 and dg.get("verletzt") is False,
          str(dg))
    m = zugstab(0.9)
    m.plastizitaet.dehnungsgrenze = 0.03
    r, _m = rechnen(m)
    g = _gueltig_text(r)
    check("Grenze 3 % eingestellt: NICHT gültig – außerhalb der Theorie kleiner Verzerrungen",
          g.startswith("NICHT gültig") and "außerhalb der Theorie kleiner Verzerrungen" in g, g[:200])
    m = zugstab(0.9)
    m.materials["S355"].bruchdehnung = 0.04
    r, _m = rechnen(m)
    g = _gueltig_text(r)
    dg = _pz(r).get("dehnungsgrenze") or {}
    check("Bruchdehnung 4 % am Werkstoff: sie ist die Grenze, NICHT gültig",
          g.startswith("NICHT gültig") and "Bruchdehnung" in g and abs(float(dg.get("grenze", 0)) - 0.04) < 1e-12,
          g[:200])
    check("… die Meldung gilt für das ganze Ergebnis (Zusammenfassung)",
          "NICHT GÜLTIG" in r.summary() and "kleiner Verzerrungen" in r.summary(), "")
    # Speichern: die Einstellung mit ihrer Vorgabe steht nicht in der Datei
    d = pl.Plastizitaet(an=True).als_dict()
    check("Vorgabe 20 % nicht in der Modelldatei (alte Dateien bleiben bitgleich)", "dehnungsgrenze" not in d, str(d)[:120])
    d2 = pl.Plastizitaet(an=True, dehnungsgrenze=0.1).als_dict()
    check("… eine andere Grenze steht drin", d2.get("dehnungsgrenze") == 0.1, "")
    mat = Material("S", E=E, nu=NU, fy=FY, fu=FU, bruchdehnung=0.15)
    m2 = Model("x")
    m2.add_material(mat)
    m3 = Model.from_dict(m2.to_dict())
    check("Bruchdehnung des Werkstoffs übersteht Speichern und Laden",
          getattr(m3.materials["S"], "bruchdehnung", None) == 0.15, "")
    m4 = Model("y")
    m4.add_material(Material("S", E=E, nu=NU, fy=FY, fu=FU))
    check("ohne Bruchdehnung kein neuer Schlüssel im Werkstoff",
          "bruchdehnung" not in str(m4.to_dict().get("materials")), "")


def test_ausgabe():
    print("\n--- 4. Ausgabe: ε_p,max mit Ort, ΣR und ΣM ---")
    r, meld = rechnen(zugstab(0.9))
    pz = _pz(r)
    ort = pz.get("eps_p_ort") or {}
    check("ε_p,max mit Ort: Körper, Element, Koordinate",
          ort.get("element") is not None and ort.get("xyz") is not None and "koerper" in ort
          and abs(float(ort.get("wert", -1)) - float(pz.get("eps_p_max", -2))) < 1e-12, str(ort)[:200])
    X = np.asarray(ort.get("xyz") or [9, 9, 9], float)
    check("… der Ort liegt im fließenden Teil des Stabs (x ≤ 0,8 L)", X[0] <= 0.8 * L_ZUG + 1e-9, str(X))
    log = pz.get("log") or []
    check("Protokoll: Zeile „ε_p,max … in Element … bei (…)“",
          any(z.startswith("Plastizität: ε_p,max") and "Element" in z for z in log),
          next((z for z in log if z.startswith("Plastizität: ε_p,max")), "")[:200])
    check("Protokoll: Zeile mit ΣR und ΣM",
          any("ΣR" in z and "ΣM" in z for z in log), next((z for z in log if "ΣR" in z), "")[:200])
    s = r.summary()
    check("Zusammenfassung: ε_p,max mit Ort und ΣR/ΣM",
          "ε_p,max" in s and "Element" in s and "ΣR" in s and "ΣM" in s, "")
    z = next((z for z in log if "ΣR" in z), "")
    check("ΣR_x = −0,9 F_lim (Lager halten die Last)", f"{-0.9 * F_LIM / 1e3:.1f}".replace(".", ",") in z
          or abs(float(r.reactions[:, 0].sum()) + 0.9 * F_LIM) < 1.0, z[:200])


def test_gleichgewicht_mit_inneren_kraeften():
    print("\n--- 5. Gleichgewichtskontrolle mit inneren Kräften (Residuum) ---")
    r, _m = rechnen(zugstab(0.9))
    res = (r.info.get("gleichgewicht_global") or {}).get("residuum") or {}
    check("0,9 F_lim: Residuum an den freien FHG klein (bezogen ≤ 1e-3), nicht verletzt",
          res and float(res.get("rel", 1.0)) <= 1e-3 and not gg.verletzt_text(r.info["gleichgewicht_global"]),
          str(res)[:200])
    r, _m = rechnen(zugstab(1.2))
    g = r.info.get("gleichgewicht_global") or {}
    res = g.get("residuum") or {}
    check("1,2 F_lim: gegen die verlangte Last fehlt (1 − λ) F – Residuum verletzt",
          float(res.get("rel", 0.0)) >= gg.UNGUELTIG and "Residuum" in gg.verletzt_text(g), str(res)[:200])
    # Ruecknahmeprobe: ohne Traglasterkennung rechnet der Newton wie bis zum
    # 16.10.2026 weiter - die Kontrolle allein erkennt das Ergebnis als nicht gueltig
    alt = pl.TRAGLAST_ERKENNEN
    pl.TRAGLAST_ERKENNEN = False
    try:
        m = zugstab(1.2, "tet10")
        m.plastizitaet.dehnungsgrenze = 1e9     # nur die Gleichgewichtskontrolle soll urteilen
        r, _m = rechnen(m)
    finally:
        pl.TRAGLAST_ERKENNEN = alt
    g = r.info.get("gleichgewicht_global") or {}
    gt = _gueltig_text(r)
    check("Rücknahme (Traglasterkennung aus): die Kontrolle allein macht 1,2 F_lim NICHT gültig",
          gt.startswith("NICHT gültig") and "Residuum" in gt, gt[:200])


def test_pruefblech():
    print("\n--- 6. Prüfblech mit Kreisring, 900 kN ---")
    from tests import test_scheibe_kreisring as T
    m = T.blech(h=0.004, ordnung=2, ring=True, plast=True, F=900e3)
    r, meld = rechnen(m)
    pz = _pz(r)
    g = _gueltig_text(r)
    check("tet10, 900 kN: NICHT gültig – kein Gleichgewicht (im Spannschritt)",
          g.startswith("NICHT gültig") and "Kein Gleichgewicht gefunden im Spannschritt" in g, g[:220])
    check("tet10, 900 kN: nicht „konvergiert“", solver.konvergenz_zustand(r.info) != solver.KONVERGIERT,
          solver.konvergenz_zustand(r.info)[:160])
    # Gemessen 16.10.2026: Spannstufe 600 kN ohne Gleichgewicht, nach vier
    # Halbierungen letzter konvergierter Anteil 0,5417 (487,5 kN), bei 0,5625
    # (506,3 kN) kein Gleichgewicht; der gezeigte Zustand hat am Lochrand unter dem
    # Ring ε_p 53 % und ist darum zusaetzlich ausserhalb der Gueltigkeitsgrenze
    ep = float(pz.get("eps_p_max") or 0.0)
    check("tet10, 900 kN: gezeigt der letzte konvergierte Zustand (ε_p,max endlich, unter 100 %) – "
          "über 20 % zusätzlich als außerhalb der Theorie kleiner Verzerrungen gekennzeichnet",
          ep < 1.0 and (ep <= 0.2 or "kleiner Verzerrungen" in g), f"{ep * 100:.3f} %")
    tl = (r.info.get("vorspannung") or {}).get("traglast") or pz.get("traglast") or {}
    check("tet10, 900 kN: Faktor der Sollkraft genannt (unter 1)", 0.0 <= float(tl.get("lastfaktor", 2.0)) < 1.0,
          str(tl.get("text", ""))[:200])
    gl = r.info.get("gleichgewicht_global") or {}
    check("tet10, 900 kN: Gleichgewichtskontrolle mit inneren Kräften schlägt an (Sollkraft als Bezug)",
          bool(gg.verletzt_text(gl)), str((gl.get("residuum") or {}))[:200])
    m = T.blech(h=0.004, ordnung=1, ring=True, plast=True, F=900e3)
    r, meld = rechnen(m)
    g = _gueltig_text(r)
    check("tet4, 900 kN (konvergiert mit ε_p 20,6 %): NICHT gültig – außerhalb der Theorie kleiner Verzerrungen",
          g.startswith("NICHT gültig") and "kleiner Verzerrungen" in g, g[:220])
    # Bezug der Toleranz im Lastfall nach dem Verriegeln: die Sollkraft, nicht ‖F_lock‖
    m = T.blech(h=0.004, ordnung=1, ring=True, plast=True, F=300e3)
    r, meld = rechnen(m)
    pz = _pz(r)
    b = float(pz.get("bezug", 0.0))
    check("tet4, 300 kN: Bezug der Abbruchtoleranz = ‖Kräftepaar der Sollkraft‖ (300 kN · √2)",
          abs(b - 300e3 * math.sqrt(2.0)) <= 1e-6 * b, f"{b:.6g} N")
    check("tet4, 300 kN: weiter konvergiert und gültig", pz.get("konvergiert") is True and not _gueltig_text(r),
          _gueltig_text(r)[:160])


def test_oberflaeche():
    print("\n--- 7. Oberfläche: Gültigkeitsgrenze und Bruchdehnung einstellbar ---")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
    os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    hinweise = []
    w.hinweis = lambda t, *a, **k: hinweise.append(str(t))
    w.model = zugstab(0.9)
    w.refresh_all()
    app.processEvents()
    w._plast_anzeigen()
    check("Maske Berechnung: Feld „Gültigkeitsgrenze ε_p“ mit Vorgabe 20 %",
          hasattr(w, "sp_plast_grenze") and abs(w.sp_plast_grenze.value() - 20.0) < 1e-9, "")
    vorher = dict(vars(w.model.plastizitaet))
    w._plast_schreiben(w.model.plastizitaet)
    check("… Öffnen und Übernehmen ohne Eingabe ändert die Einstellung nicht",
          dict(vars(w.model.plastizitaet)) == vorher, "")
    w.sp_plast_grenze.setValue(15.0)
    w._plast_schreiben(w.model.plastizitaet)
    check("… 15 % übernommen: Plastizitaet.dehnungsgrenze = 0,15",
          abs(w.model.plastizitaet.dehnungsgrenze - 0.15) < 1e-12, str(w.model.plastizitaet.dehnungsgrenze))
    felder = {"name": "S355", "E": "210", "nu": "0.3", "rho": "0", "alpha": "12", "fy": "355", "fu": "510",
              "grade": ""}
    w._eigenschaften_uebernehmen("werkstoff", "S355", dict(felder, bruchdehnung="22"))
    check("Werkstoffmaske: Bruchdehnung 22 % übernommen", getattr(w.model.materials["S355"], "bruchdehnung", None)
          == 0.22, str(getattr(w.model.materials["S355"], "bruchdehnung", None)))
    w._eigenschaften_uebernehmen("werkstoff", "S355", dict(felder, bruchdehnung="0"))
    check("… 0 % abgewiesen, der Wert bleibt", getattr(w.model.materials["S355"], "bruchdehnung", None) == 0.22
          and any("Bruchdehnung" in h for h in hinweise), hinweise[-1:] if hinweise else "")
    w._eigenschaften_uebernehmen("werkstoff", "S355", dict(felder, bruchdehnung=""))
    check("… leer = Grenze der Rechnung (None)", getattr(w.model.materials["S355"], "bruchdehnung", 1) is None, "")
    w.close()


class _ZonenAttrappe:
    """Die Zonen des ingenieurmaessigen Abbruchs, nur was residuum_stufe liest."""
    ingenieur = True
    auffaellig = {1}

    def __init__(self, dofs):
        self._innen_dof = np.asarray(dofs, np.int64)

    def _masken(self):
        pass


def _stufenpruefer(r_gleich_null=True):
    """Ein _KontaktImNewton an einem kleinen Modell, dessen Lagerkraefte die Last
    genau ausgleichen - die Summenkontrolle ist erfuellt (Φᵀ(F + R) = 0)."""
    m = zugstab(0.5)
    F = solver.case_loads(m, {"LF1": 1.0})[0]
    res = solver.Results(name="LF1", kind="case", model=m)
    kn = solver._KontaktImNewton(None, res, None, None, [], False, 1e-3)
    R = np.zeros(m.ndof)
    lager = [i for i in range(m.nn) if abs(m.nodes[i][0]) < 1e-12]
    for i in lager:
        R[6 * i] = -float(np.asarray(F, float)[0::6].sum()) / len(lager)
    kn.halter["R"] = R
    kn.frei = np.ones(m.ndof, bool)
    return m, F, kn


def test_residuum_stufe_mit_kontakt():
    print("\n--- 8. Residuum am Ende einer Laststufe: inneres Gleichgewicht statt Summe ---")
    m, F, kn = _stufenpruefer()
    b = float(np.linalg.norm(F))
    # Rücknahme: ohne Residuum urteilt nur die Summe - erfüllt, gleich wie groß das
    # innere Ungleichgewicht ist (so bis zum 16.10.2026)
    z0, ok0 = kn.residuum_stufe(F, "1/1")
    check("ohne inneres Residuum (bisher): die Summe allein ist erfüllt", ok0 and "Gleichgewicht" in z0, z0[:160])
    r = np.zeros(m.ndof)
    r[6 * 10] = 0.02 * b                       # 2 % der Last als Paar, Summe null
    r[6 * 11] = -0.02 * b
    z1, ok1 = kn.residuum_stufe(F, "1/1", r=r, bezug=b)
    check("inneres Residuum 2,8 % der Lasten (Kräftepaar, Summe null): Stufe nicht konvergiert",
          not ok1 and "inneres Gleichgewicht" in z1 and "nicht konvergiert" in z1, z1[:220])
    check("… die Zeile nennt die Summe weiter mit", "Summe der Kräfte" in z1, "")
    kn.zonen = _ZonenAttrappe([6 * 10, 6 * 11])
    z2, ok2 = kn.residuum_stufe(F, "1/1", r=r, bezug=b)
    check("dasselbe Residuum nur in ausgenommenen Zonen: außerhalb erfüllt, Zonen getrennt ausgewiesen",
          ok2 and "in den ausgenommenen Zonen 0,028" in z2, z2[:220])
    kn.zonen = None
    r_klein = r * 1e-3
    z3, ok3 = kn.residuum_stufe(F, "1/1", r=r_klein, bezug=b)
    check("inneres Residuum 2,8e-5 der Lasten: erfüllt (Schranke = Toleranz 1e-3)", ok3, z3[:160])
    # am gerechneten Kontaktfall: Block mit Reibung und Fließen (tests/test_plastizitaet)
    from tests import test_plastizitaet as TP
    mk = TP._gequetschter_block()
    rk = solver.solve_static(mk, workers=1)
    zeilen = [z for z in (rk.info.get("plastizitaet") or {}).get("log") or [] if "Residuum am Ende" in z]
    werte = [float(x.replace(",", ".")) for z in zeilen for x in _re_inner(z)]
    check("Kontaktfall (gequetschter Block): jede Laststufe meldet das innere Gleichgewicht",
          zeilen and all("inneres Gleichgewicht" in z for z in zeilen), f"{len(zeilen)} Zeilen")
    check("… und es liegt unter der Toleranz 1e-3, konvergiert",
          werte and max(werte) <= 1e-3 and (rk.info.get("plastizitaet") or {}).get("konvergiert") is True,
          f"größtes {max(werte) if werte else None:.2e}" if werte else "")


def _re_inner(z):
    import re
    m = re.search(r"inneres Gleichgewicht .*? = ([0-9,]+) der Lasten", z)
    return [m.group(1)] if m else []


def test_ingenieurkriterium_inneres_residuum():
    print("\n--- 9. Ingenieurkriterium des Kontaktlaufs: inneres Residuum ---")
    from statik3d import contact
    from tests import test_ingenieur_warm as tiw
    from tests import test_kontakt_pendeln as tp
    m = tp.lager_in_flaechenachsen()
    with tiw.weite_schranken(), tp.schutz(False):
        r = solver.solve_static(m)
    ing = r.info.get("contact_ingenieur") or {}
    zeile = next((z for z in r.info.get("contact_log") or [] if "Ingenieurkriterium" in z), "")
    check("Pendelmodell: angenommen, inneres Residuum der Lösung unter 1e-4 und im Protokoll",
          r.info.get("contact_converged") and ing and float(ing.get("inneres_residuum", 1.0)) <= 1e-4
          and "inneres Residuum" in zeile, f"{ing.get('inneres_residuum')}")
    # eingespielt: das Kontaktgesetz liefert an einem Knoten 1 % der Last mehr, als die
    # Lösung trägt - nur in der Sicht des inneren Residuums; die Summe sieht es nicht
    alt = contact.ContactSystem.nodal_forces
    F = solver.case_loads(m, {list(m.load_cases)[0]: 1.0})[0]
    zusatz = 0.01 * float(np.linalg.norm(F))

    def nf(self, nn, _a=alt):
        f = _a(self, nn)
        if len(f):
            k = int(np.argmax(np.linalg.norm(f, axis=1)))
            f = f.copy()
            f[k, 0] += zusatz
        return f
    contact.ContactSystem.nodal_forces = nf
    try:
        m2 = tp.lager_in_flaechenachsen()
        with tiw.weite_schranken(), tp.schutz(False):
            r2 = solver.solve_static(m2)
    finally:
        contact.ContactSystem.nodal_forces = alt
    ing2 = r2.info.get("contact_ingenieur") or {}
    check("eingespieltes Ungleichgewicht 1 % der Last: nicht angenommen (die Kontaktbedingung bleibt streng)",
          not ing2, f"konvergiert {r2.info.get('contact_converged')}, Runden {r2.info.get('contact_iterations')}")


def main():
    test_zugstab()
    test_balken()
    test_gueltigkeitsgrenze()
    test_ausgabe()
    test_gleichgewicht_mit_inneren_kraeften()
    test_pruefblech()
    test_oberflaeche()
    test_residuum_stufe_mit_kontakt()
    test_ingenieurkriterium_inneres_residuum()
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
