"""Nachzug zur Stabkraft mit Anfangsdehnung (14.10.2026).

Offen geblieben nach dem Paket „Stabkraft mit Anfangsdehnung“:

1. **Geometrische Steifigkeit des Fachwerkstabs.** asm.geometric_stiffness
   setzte fuer jeden Stab die Balkenform an (6/5 N/L mit Drehanteilen), auch
   fuer Fachwerkstaebe, Zug-/Druckstaebe und Seile, die keine
   Biegesteifigkeit haben. Ihre geometrische Steifigkeit ist die der Saite,
   N/L auf den Querverschiebungen (so rechnet Theorie III. Ordnung seit jeher).
   Gemessen: ein Pendelstab mit Querfeder k hatte alpha_cr 166,67 statt
   k L/P = 200 (auf der sicheren Seite), das gezogene Zugband einer
   Kragstuetze alpha_cr 4 126 statt 2 679 (54 % auf der unsicheren Seite).

Geprueft mit geschlossenen Loesungen:

* Pendelstab (Fachwerkstab, Fuss fest, Kopf mit Querfedern), Drucklast P:
  alpha_cr = k L/P, erster Knickfaktor ebenso, Theorie II. Ordnung mit
  Querlast H: u = H/(k - P/L), gleich Theorie III. Ordnung.
* Die geometrische Steifigkeit eines Fachwerkstabs, eines Zug- und eines
  Druckstabs und eines Seils ist die Saitenform N/L, die eines Balkens die
  Balkenform (auch mit „trägt nur“: er hat Biegesteifigkeit).
* Zugband an der Kragstuetze: alpha_cr = pi^2 E I/L^2 / N_Stuetze.

2. **Streckenlast auf Seilen nach Theorie III. Ordnung.** Das Seil rechnet
   dort als Kettenlinie; seine Lasten nahm solve_theorie3 aus dem
   Lastvektor, weil das Eigengewicht in der Kettenlinie steckt - eine
   Streckenlast auf dem Seil fiel dabei still weg (10 kN quer: u = 0,
   Auflager z = 0). Seither geht eine gleichmaessige Streckenlast ueber die
   ganze Seillaenge als Kettenlinienlast ein (wie das Eigengewicht);
   trapezfoermig oder abschnittsweise kennt die Kettenlinie nicht - dann ist
   der Lastfall nach Theorie III. Ordnung gesperrt, mit Seil, Lastfall und
   Betrag in der Meldung.

* Seil (zwei Elemente, vorgespannt) mit qz = -1 kN/m global: dieselbe
  Lage, Seilkraft und Auflagerkraft wie mit Eigengewicht rho A g = 1 kN/m,
  Summe der Auflager z = 10 kN; dieselbe Last lokal ebenso.
* Trapezfoermig und abschnittsweise: Sperre mit Meldung; ueber „Alle
  Lastfälle“ steht der Fehler im Theoriekapitel, und das Ergebnis sagt
  „I. Ordnung“ statt „III. Ordnung“.

3. **RFEM-Seile** (MemberImplCable) kamen beim Import als Fachwerkstab ohne
   Ausfall an und trugen Druck. Seither legt der Import sie als Seil an
   (Elementtyp seil, „trägt nur“ Zug): nach Theorie I./II. Ordnung ein
   Zugstab, der bei Druck ausfällt, nach Theorie III. Ordnung die
   Kettenlinie. Ein früher gespeichertes Modell bekommt beim Öffnen den
   Hinweis wie für Zugstäbe; die Umstellung (rfem6_db.zugstaebe_aus_rfem)
   macht aus den Seilen wieder Seile. Seilenden auf einem Körper hängen an
   dessen Netz wie die Enden der Zugstäbe (fugen.stabenden_koppeln), und eine
   Temperatur-Vorspannung auf einem Seil zählt als Vorspannkraft.

* synthetische rf6: Seil und Balken zwischen denselben Knoten, Druck 10 kN:
  das Seil fällt aus, der Balken trägt 10 kN; Protokoll und Merkmal.
* gespeichertes Modell (Seil als Fachwerkstab, ohne Merkmal): Hinweis,
  Umstellung zum Seil, danach kein Hinweis mehr.

4. **alpha_cr in Situationen.** theorie2.alpha_cr baute K_g aus allen
   Elementen, ohne die Maske der Situation (system.aktiv): ein abgeschalteter
   Stab, dessen Enden sich mit dem System bewegen, stand mit seiner
   rechnerischen Normalkraft darin. K, solve_theorie2 und solve_buckling
   nahmen nur die wirksamen Elemente.

* Kragstuetze mit einem Fachwerkstab daneben (gedrueckt) bzw. darueber
  (gezogen), in der Situation abgeschaltet oder deaktiviert: alpha_cr wie im
  Modell ohne den Stab.

Aufruf:  python -m tests.test_stab_nachzug
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, solver, theorie2, theorie3   # noqa: E402
from statik3d.elements import beam3d as bm                         # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section     # noqa: E402

RESULTS = []
E = 210e9


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.9g} soll {soll:.9g} ({abw:.2e}) {einheit}")


# --------------------------------------------------------------------------
# 1. Geometrische Steifigkeit des Fachwerkstabs: Saitenform N/L
# --------------------------------------------------------------------------
K_FEDER = 1e5           # Querfeder am Kopf in x [N/m]; in y doppelt so steif
L_PENDEL = 2.0


def _pendel(typ="truss", nur="", P=1e3, H=0.0):
    """Pendelstab 2 m (Rundstahl 50 mm), Fuss fest, Kopf mit Querfedern
    kx = 1e5, ky = 2e5 N/m, Kopfdrehungen gehalten; Drucklast P, Querlast H
    in x. Geschlossen: alpha_cr = kx L/P, u_x = H/(kx - P/L)."""
    m = Model("Pendel")
    m.add_material(Material("S", E=E, nu=0.3, rho=0.0))
    m.add_section(Section.circle("D", 0.05))
    a = m.add_node(0, 0, 0)
    b = m.add_node(0, 0, L_PENDEL)
    m.fix(a, "all")
    m.support(b, [0], ux=dict(typ="spring", stiffness=K_FEDER))
    m.support(b, [1], uy=dict(typ="spring", stiffness=2 * K_FEDER))
    m.fix(b, [3, 4, 5])
    e = m.add_element(typ, [a, b], "S", "D")
    m.elements[e].nur = nur
    m.add_member("St", [e])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(b, [H, 0, -P, 0, 0, 0]))
    m.design.imperfektionen = False
    return m, e, b


def test_pendel_saitenform():
    print("\n--- 1: Pendelstab mit Querfeder – alpha_cr, Knicken, Theorie II/III ---")
    soll = K_FEDER * L_PENDEL / 1e3
    m, e, b = _pendel()
    system = solver.StaticSystem(m)
    u = system.solve(solver.case_loads(m, {"LF1": 1.0})[0])
    nahe("Pendelstab: alpha_cr = k L/P", theorie2.alpha_cr(m, system, u)["alpha_cr"], soll, 1e-9)
    bk = solver.solve_buckling(m, nmodes=2, case="LF1")
    nahe("Pendelstab: erster Knickfaktor = k L/P", float(bk.buckling_factors[0]), soll, 1e-7)
    H = 10.0
    mh, _e, bh = _pendel(H=H)
    r2, i2 = theorie2.solve_theorie2(mh, {"LF1": 1.0}, "LF1", imperfektionen=False)
    u2 = float(r2.u[bh, 0])
    nahe("Theorie II. Ordnung: u_x = H/(k - P/L)", u2, H / (K_FEDER - 1e3 / L_PENDEL), 1e-7, "m")
    r3, i3 = theorie3.solve_theorie3(mh, {"LF1": 1.0}, "LF1", schritte=2, imperfektionen=False)
    nahe("Theorie II. Ordnung = Theorie III. Ordnung (dort seit jeher N/L)", u2, float(r3.u[bh, 0]), 1e-6, "m")


def _block(m, e, u):
    el = m.elements[e]
    d = asm.element_dofs(el, m)[:12]
    blk = asm.geometric_stiffness(m, u)[d][:, d].toarray()
    N = asm.stab_normalkraft(m, el, u)
    kl, T3, T, Le = asm.beam_local(m, el)
    ks = np.zeros((12, 12))
    for a_, b_ in ((1, 7), (2, 8)):
        ks[a_, a_] = ks[b_, b_] = N / Le
        ks[a_, b_] = ks[b_, a_] = -N / Le
    sec = m.sections[el.sec]
    balken = T.T @ bm.kg_local_beam(N, Le, sec.A, sec.Iy + sec.Iz) @ T
    return blk, T.T @ ks @ T, balken, N


def test_kg_saitenform_je_art():
    print("\n--- 1: K_G je Stabart – Saitenform für Fachwerk, Zug-/Druckstab und Seil ---")
    for typ, nur, P, text in (("truss", "", 1e3, "Fachwerkstab (Druck)"),
                              ("truss", "zug", -1e3, "Zugstab „nur Zug“ (Zug)"),
                              ("truss", "druck", 1e3, "Druckstab „nur Druck“ (Druck)"),
                              ("seil", "", -1e3, "Seil (Zug)")):
        m, e, _b = _pendel(typ, nur, P=P)
        system = solver.StaticSystem(m)
        u = system.solve(solver.case_loads(m, {"LF1": 1.0})[0])
        blk, saite, _balken, N = _block(m, e, u)
        rest = float(np.abs(blk - saite).max()) / float(np.abs(saite).max())
        check(f"{text}: K_G = Saitenform N/L", rest <= 1e-12, f"N {N:.3f} N, Abweichung {rest:.2e}")
        dreh = [3, 4, 5, 9, 10, 11]
        el = m.elements[e]
        d = asm.element_dofs(el, m)[:12]
        kg = asm.geometric_stiffness(m, u)[d][:, d].toarray()
        check(f"{text}: K_G ohne Drehanteile", float(np.abs(kg[dreh]).max()) == 0.0,
              f"größter Drehanteil {float(np.abs(kg[dreh]).max()):.3e}")
    for nur in ("", "zug"):
        m, e, _b = _pendel("beam", nur, P=-1e3)
        system = solver.StaticSystem(m)
        u = system.solve(solver.case_loads(m, {"LF1": 1.0})[0])
        blk, _saite, balken, N = _block(m, e, u)
        rest = float(np.abs(blk - balken).max()) / float(np.abs(balken).max())
        check(f"Balken{' „nur Zug“' if nur else ''}: K_G bleibt die Balkenform", rest <= 1e-12,
              f"Abweichung {rest:.2e}")


def test_zugband_gegen_hand():
    print("\n--- 1: Zugband an der Kragstütze – alpha_cr gegen pi^2 E I/L^2/N_Stütze ---")
    import tests.test_stabkraft_anfangsdehnung as TA
    m, band, _kopf = TA._zugband()
    r = solver.solve_static(m, case="V")
    u = TA._u_voll(m, r)
    n = solver.anfangsnormalkraefte(m, {"V": 1.0})
    system = solver.StaticSystem(m)
    ac = theorie2.alpha_cr(m, system, u, n_anfang=n)["alpha_cr"]
    N = asm.stab_normalkraft(m, m.elements[band], u, n.get(band, 0.0))
    I = m.sections["Q"].Iy
    N_c = abs(N) * 3.0 / math.sqrt(13.0)
    nahe("Zugband: alpha_cr des Programms = pi^2 E I/L^2 / N_Stütze", ac,
         math.pi ** 2 * TA.E * I / 9.0 / N_c, 1e-5)


# --------------------------------------------------------------------------
# 2. Streckenlast auf Seilen nach Theorie III. Ordnung
# --------------------------------------------------------------------------
def _seil(fall):
    """Seil 10 m waagerecht zwischen zwei Festpunkten, Mittelknoten in x und
    z frei, zwei Seilelemente (Rundstahl 20 mm), Vorspannung 10 kN, ohne
    Eigengewicht. ``fall``: "global" qz = -1 kN/m auf beiden Elementen,
    "lokal" dieselbe Last lokal (die lokale z-Achse des waagerechten Seils
    ist global z), "gewicht" gleichwertig als Eigengewicht rho A g = 1 kN/m,
    "trapez" 1 -> 2 kN/m auf dem ersten Element, "abschnitt" 1 kN/m auf
    1 bis 3 m des ersten Elements."""
    m = Model("Seil")
    A = math.pi * 0.02 ** 2 / 4.0
    m.add_material(Material("S", E=E, nu=0.3, rho=1e3 / (A * 9.81) if fall == "gewicht" else 0.0))
    m.add_section(Section.circle("D", 0.02))
    a, b, c = m.add_node(0, 0, 0), m.add_node(5, 0, 0), m.add_node(10, 0, 0)
    m.fix(a, "all")
    m.fix(c, "all")
    m.fix(b, [1, 3, 4, 5])
    e1 = m.add_element("seil", [a, b], "S", "D")
    e2 = m.add_element("seil", [b, c], "S", "D")
    m.add_member("Tragseil", [e1, e2])
    m.add_load_case("LF1").gravity = [0, 0, -9.81] if fall == "gewicht" else [0, 0, 0]
    m.add_vorspannung("Tragseil", 10e3, case="LF1")
    if fall in ("global", "lokal"):
        for e in (e1, e2):
            m.load_beam(e, qz=-1e3, case="LF1", system="global" if fall == "global" else "local")
    elif fall == "trapez":
        m.load_beam(e1, qz=-1e3, case="LF1", q2=[0, 0, -2e3])
    elif fall == "abschnitt":
        m.load_beam(e1, qz=-1e3, case="LF1", a=1.0, b=3.0)
    m.design.imperfektionen = False
    return m, b


def _th3(m):
    res, info = theorie3.solve_theorie3(m, {"LF1": 1.0}, "LF1", schritte=5, imperfektionen=False)
    return res, info


def test_seil_streckenlast():
    print("\n--- 2: Streckenlast auf dem Seil nach Theorie III. Ordnung – Kettenlinienlast ---")
    werte = {}
    for fall in ("gewicht", "global", "lokal"):
        m, b = _seil(fall)
        try:
            res, info = _th3(m)
        except ValueError as ex:
            check(f"{fall}: gerechnet", False, str(ex)[:120])
            continue
        werte[fall] = (float(res.u[b, 2]), float(np.asarray(res.reactions)[:, 2].sum()),
                       float(np.asarray(res.beam_end[0])[6]), info.gerechnet)
        print(f"   {fall:8s}: u_z Mitte {werte[fall][0] * 1e3:.4f} mm, Summe Auflager z "
              f"{werte[fall][1] / 1e3:.4f} kN, Seilkraft {werte[fall][2] / 1e3:.4f} kN")
    g = werte.get("gewicht")
    for fall in ("global", "lokal"):
        w = werte.get(fall)
        if g is None or w is None:
            check(f"Streckenlast {fall}: gerechnet", False)
            continue
        check(f"Streckenlast {fall}: gerechnet", w[3])
        nahe(f"Streckenlast {fall}: Summe der Auflager z = 10 kN", w[1], 10e3, 1e-9, "N")
        nahe(f"Streckenlast {fall}: Durchhang wie mit gleichwertigem Eigengewicht", w[0], g[0], 1e-9, "m")
        nahe(f"Streckenlast {fall}: Seilkraft wie mit gleichwertigem Eigengewicht", w[2], g[2], 1e-9, "N")
    # gegen Hand (flaches Seil als Parabel): f = q L^2/(8 H), die Seillaenge
    # L (1 + 8 f^2/(3 L^2)) gedehnt aus der spannungsfreien L/(1 + N0/(E A))
    # mit H/(E A) - auf 1 % (die Parabel und das mittlere H statt T)
    w = werte.get("global")
    if w is not None:
        EA = E * math.pi * 0.02 ** 2 / 4.0
        Ls, q0, N0 = 10.0, 1e3, 10e3
        lo, hi = 1e3, 1e7
        for _k in range(200):
            H = 0.5 * (lo + hi)
            f_ = q0 * Ls ** 2 / (8.0 * H)
            rest = H / EA - (1.0 + 8.0 * f_ ** 2 / (3.0 * Ls ** 2)) * (1.0 + N0 / EA) + 1.0
            lo, hi = (H, hi) if rest < 0 else (lo, H)
        nahe("Streckenlast global: Durchhang gegen Hand (Parabel)", abs(w[0]), q0 * Ls ** 2 / (8.0 * H), 1e-2, "m")


def test_seil_streckenlast_gesperrt():
    print("\n--- 2: Trapezförmig oder abschnittsweise: gesperrt, mit Meldung ---")
    for fall, wort, betrag in (("trapez", "trapezförmig", "1 → 2 kN/m"),
                               ("abschnitt", "abschnittsweise", "1 kN/m")):
        m, _b = _seil(fall)
        try:
            _th3(m)
            check(f"{fall}: Theorie III. Ordnung gesperrt", False, "gerechnet, ohne Meldung")
            continue
        except ValueError as ex:
            text = str(ex)
        check(f"{fall}: Theorie III. Ordnung gesperrt", True, text[:150])
        check(f"{fall}: die Meldung nennt Seil, Lastfall, Art und Betrag",
              "Tragseil" in text and "LF1" in text and wort in text and betrag in text, text[:200])
    m, _b = _seil("trapez")
    m.load_cases["LF1"].theorie = "III"
    from statik3d import solver as slv
    an = slv.solve_all(m)
    info = (an.theorie3.kombinationen.get("LF1") if an.theorie3 else None)
    check("„Alle Lastfälle“: der Fehler steht im Theoriekapitel",
          info is not None and "Tragseil" in str(info.fehler), str(getattr(info, "fehler", ""))[:120])
    res = an.cases.get("LF1")
    check("… und das Ergebnis gibt sich nicht als III. Ordnung aus",
          res is not None and res.info.get("theorie") != "III. Ordnung", str(res.info.get("theorie") if res else "-"))


# --------------------------------------------------------------------------
# 3. RFEM-Seile
# --------------------------------------------------------------------------
def _rf6_seil(tmp, mit_zugstab=False):
    """Synthetische rf6: Stab 1 Seil (MemberImplCable) und Stab 2 Balken
    zwischen denselben zwei Knoten (Knoten 1 fest, Knoten 2 in x frei);
    ``mit_zugstab``: dazu Stab 3, ein Zugstab daneben."""
    import sqlite3
    import zipfile
    from tests.test_rfem6 import INF, build_db
    db = os.path.join(tmp, "model.db")
    knoten = [(0, 0, 0), (1, 0, 0)] + ([(0, 1, 0), (1, 1, 0)] if mit_zugstab else [])
    linien = [[1, 2], [1, 2]] + ([[3, 4]] if mit_zugstab else [])
    staebe = [(1, None, None, "MemberImplTension"), (2, None, None, "MemberImplBeam")]
    if mit_zugstab:
        staebe.append((3, None, None, "MemberImplTension"))
    lager = [("Fest", (INF,) * 6, (0,) * 6, None, [1] + ([3, 4] if mit_zugstab else [])),
             ("Gleit", (0.0, INF, INF, INF, INF, INF), (0,) * 6, None, [2])]
    build_db(db, nodes=knoten, lines=linien, members=staebe, supports=lager)
    con = sqlite3.connect(db)
    try:
        spalten = [r[1] for r in con.execute("PRAGMA table_info(MemberImplTension)")]
        con.execute("CREATE TABLE MemberImplCable AS SELECT * FROM MemberImplTension WHERE 0")
        con.execute(f"INSERT INTO MemberImplCable SELECT {', '.join(spalten)} FROM MemberImplTension WHERE id=1")
        con.execute("DELETE FROM MemberImplTension WHERE id=1")
        con.execute("UPDATE Member SET impl_table='MemberImplCable' WHERE id=1")
        con.commit()
    finally:
        con.close()
    rf6 = os.path.join(tmp, "seil.rf6")
    with zipfile.ZipFile(rf6, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "model.db")
        z.writestr("format.txt", "RFEM\n6.11.0004\nRFEM6\n6.12.0010\n1773229130\n")
    os.remove(db)
    return rf6


def _arten(m, stab):
    return [(m.elements[i].typ, m.elements[i].nur) for i in m.members[stab].elements]


def test_rfem_seil_import():
    print("\n--- 3: RFEM-Seil beim Import – Seil, trägt nur Zug ---")
    import shutil
    import tempfile
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        log = []
        m = R6.read_rf6(_rf6_seil(tmp), log=log)
        check("RFEM-Seil kommt als Seil mit „trägt nur Zug“ an", _arten(m, "S1") == [("seil", "zug")],
              str(_arten(m, "S1")))
        check("das Protokoll nennt das Seil", any("Seil" in z and "S1" in z and "nur Zug" in z for z in log),
              next((z.strip() for z in log if "Seil" in z), "-"))
        check("keine Warnung „Seiltheorie fehlt“ mehr", not any("Seiltheorie" in z for z in log))
        check("das Modell trägt das Merkmal der Seile", bool(m.meta.get("rfem_seile")), str(m.meta.get("rfem_seile")))
        lc = m.add_load_case("D")
        lc.gravity = [0, 0, 0]
        m.load_node(1, Fx=-10e3, case="D")
        r = solver.solve_static(m, case="D")
        z = m.members["S1"].elements[0]
        b = m.members["S2"].elements[0]
        N_s, N_b = float(r.beam_forces[z]["N"][1]), float(r.beam_forces[b]["N"][1])
        check("unter Druck fällt das Seil aus, der Balken trägt 10 kN",
              list(r.info.get("ausfall") or []) == [z] and abs(N_s) < 1e-9 and abs(N_b + 10e3) < 1e-6,
              f"ausgefallen {r.info.get('ausfall')}, N Seil {N_s:.3g} N, N Balken {N_b:.6g} N")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rfem_seil_gespeichert():
    print("\n--- 3: gespeichertes Modell von vor dem 14.10.2026 – Hinweis und Umstellung zum Seil ---")
    import shutil
    import tempfile
    from statik3d.importers import rfem6_db as R6
    tmp = tempfile.mkdtemp()
    try:
        rf6 = _rf6_seil(tmp, mit_zugstab=True)
        m = R6.read_rf6(rf6, log=[])
        for e in m.elements:              # so legte der Import es bis zum 14.10.2026 an
            if e.typ == "seil":
                e.typ = "truss"
            e.nur = ""
        m.meta.pop("rfem_zugstaebe", None)
        m.meta.pop("rfem_seile", None)
        m.meta["quelle"] = rf6
        pfad = os.path.join(tmp, "alt.json")
        m.save(pfad)
        alt = Model.load(pfad)
        h = [x for x in alt.importhinweise if x.get("art") == "zugstab" and not x.get("erledigt")]
        check("beim Öffnen: ein Hinweis, der die Seile nennt", len(h) == 1 and "Seil" in h[0].get("text", ""),
              h[0].get("text", "")[:160] if h else "kein Hinweis")
        check("von selbst wird nichts umgestellt", _arten(alt, "S1") == [("truss", "")])
        aus = R6.zugstaebe_aus_rfem(alt, log=[])
        check("Umstellung: das Seil wird Seil, der Zugstab nur Zug, der Balken bleibt",
              _arten(alt, "S1") == [("seil", "zug")] and _arten(alt, "S3") == [("truss", "zug")]
              and _arten(alt, "S2") == [("beam", "")], f"{_arten(alt, 'S1')} {_arten(alt, 'S3')} {aus}")
        check("Umstellung: sie nennt das Seil", aus.get("seil") == ["S1"] and aus.get("zug") == ["S3"], str(aus))
        alt.save(pfad)
        wieder = Model.load(pfad)
        check("nach dem Speichern: kein neuer Hinweis, das Seil bleibt Seil",
              not any(x.get("art") == "zugstab" and not x.get("erledigt") for x in wieder.importhinweise)
              and _arten(wieder, "S1") == [("seil", "zug")])
        # am 14.10.2026 mit Zugstaeben, aber noch ohne Seile uebernommen
        m2 = R6.read_rf6(rf6, log=[])
        for e in m2.elements:
            if e.typ == "seil":
                e.typ, e.nur = "truss", ""
        m2.meta.pop("rfem_seile", None)
        m2.meta["quelle"] = rf6
        m2.save(pfad)
        h2 = [x for x in Model.load(pfad).importhinweise if x.get("art") == "zugstab" and not x.get("erledigt")]
        check("Merkmal der Zugstäbe, aber nicht der Seile: auch dann der Hinweis", len(h2) == 1,
              h2[0].get("text", "")[:120] if h2 else "kein Hinweis")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_seilende_am_koerper():
    print("\n--- 3: Seilende auf einem Körper hängt an dessen Netz; Temperatur-Vorspannung als Kraft ---")
    from statik3d import fugen
    import tests.test_stabende as TS
    m, fuss, _kopf, innen, _oben2, _a3, _b3 = TS._modell()
    for i in m.members["Zug"].elements:
        m.elements[i].typ = "seil"
        m.elements[i].nur = "zug"
    b = fugen.stabenden_koppeln(m, [])
    partner = {int(k.node_a) for k in m.kopplungen}
    check("das Seilende in der Deckelfläche hängt am Netz wie ein Zugstabende",
          b["stabenden"] == 2 and fuss in partner and innen in partner, str(b["anschluesse"]))
    from statik3d.model import TempLoad
    i = m.members["Zug"].elements[0]
    mat, sec = m.materials[m.elements[i].mat], m.sections[m.elements[i].sec]
    soll = mat.E * sec.A * mat.alpha * 100.0
    nahe("Temperatur-Vorspannung auf einem Seil: die Kraft E A alpha (-dT)",
         TempLoad(i, -100.0).vorspannkraft(m), soll, 1e-12, "N")


# --------------------------------------------------------------------------
# 4. alpha_cr in Situationen
# --------------------------------------------------------------------------
def _stuetze(stab="", art="situation"):
    """Kragstuetze 3 m (16 Balkenelemente, Vollquadrat 0,1 m, schubstarr),
    Kopf mit P = 100 kN gedrueckt. ``stab``: "unten" ein Fachwerkstab
    (Rundstahl 40 mm) vom Fuss zum Kopf - wirkte er, waere er gedrueckt;
    "oben" einer vom Kopf zu einem Festpunkt 3 m darueber - gezogen. ``art``:
    "situation" in der Situation „ohne“ abgeschaltet (der Lastfall rechnet
    in ihr), "aus" der Stab deaktiviert (Member.aus, wirkt nirgends)."""
    from statik3d.model import Situation
    m = Model("Stuetze")
    m.add_material(Material("S", E=E, nu=0.3, rho=0.0))
    q = Section.rectangle("Q", 0.1, 0.1)
    q.Asy = q.Asz = 0.0
    m.add_section(q)
    m.add_section(Section.circle("D", 0.04))
    kn = [m.add_node(0.0, 0.0, 3.0 * k / 16) for k in range(17)]
    m.fix(kn[0], "all")
    for k in range(16):
        m.add_element("beam", [kn[k], kn[k + 1]], "S", "Q")
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(kn[-1], [0, 0, -100e3, 0, 0, 0]))
    if stab:
        if stab == "unten":
            t = m.add_element("truss", [kn[0], kn[-1]], "S", "D")
        else:
            fest = m.add_node(0.0, 0.0, 6.0)
            m.fix(fest, "all")
            t = m.add_element("truss", [kn[-1], fest], "S", "D")
        m.add_member("Band", [t])
        if art == "situation":
            m.situationen["ohne"] = Situation("ohne", "", [t], "Fachwerkstab aus")
            lc.situation = "ohne"
        else:
            m.members["Band"].aus = True
    m.design.imperfektionen = False
    return m


def _alpha_cr(m, sit=""):
    if sit:
        m_s, system = solver.situationssystem(m, sit)
    else:
        m_s, system = m, solver.StaticSystem(m)
    u = system.solve(solver.case_loads(m_s, {"LF1": 1.0}, system.aktiv)[0])
    a = theorie2.alpha_cr(m_s, system, u)["alpha_cr"]
    _r, info = theorie2.solve_theorie2(m_s, {"LF1": 1.0}, "LF1", system, imperfektionen=False)
    return a, info.alpha_cr


def test_alpha_cr_situation():
    print("\n--- 4: alpha_cr mit einem abgeschalteten Stab – wie ohne ihn ---")
    ref, _r2 = _alpha_cr(_stuetze())
    for stab, kraft in (("unten", "gedrückt"), ("oben", "gezogen")):
        for art, text in (("situation", "in der Situation abgeschaltet"), ("aus", "deaktiviert")):
            a, a2 = _alpha_cr(_stuetze(stab, art), "ohne" if art == "situation" else "")
            nahe(f"Fachwerkstab {kraft}, {text}: alpha_cr wie ohne den Stab", a, ref, 1e-9)
            nahe(f"… ebenso in solve_theorie2", a2, ref, 1e-9)


def main():
    for t in (test_pendel_saitenform, test_kg_saitenform_je_art, test_zugband_gegen_hand,
              test_seil_streckenlast, test_seil_streckenlast_gesperrt,
              test_rfem_seil_import, test_rfem_seil_gespeichert, test_seilende_am_koerper,
              test_alpha_cr_situation):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
