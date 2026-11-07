"""Pendeln mit Reibungstangente (17.10.2026, kontakt/pendeln-rt).

Anlass: Drehlager-Z-Modell mit μ = 0,2 in der Fuge Ankerplatte – Unterlegblech (Lauf
GZ02, Integrationsstand 0dcf399). Jeder Kontaktlauf endete nach 40 Runden am Deckel; die
Fuge pendelte mit Periode 2: rund 54 Knoten öffneten und schlossen, 13 bis 19 wechselten
zwischen Haften und Gleiten, die Gruppe war abwechselnd „ganz rutschend“ und nicht, und
der Lauf blieb in Phase 1, wo weder das Einfrieren noch das Ingenieurkriterium wirken.
Gegenprobe auf abaf33f: dieselben 44 Runden, also nicht neu.

Ursache (belegt am Prüfkörper unten): ist die Gruppe ganz rutschend und hält sonst
nichts das Bauteil (solver._gruppen_frei), bekam jeder gleitende Knoten die grobe
Reststeifigkeit SLIP_STIFFNESS·k_t (10-fache Diagonale, ohne Ausgleich) statt der feinen
RT_REST·c_pd (1e-8 der Diagonale, mit Ausgleich) - das 10⁹-fache. Die grobe Feder trägt
Kraft und verschiebt die Platte, Knoten haften wieder, die Gruppe ist nicht mehr ganz
rutschend, die nächste Runde springt zurück. Hängt die Reststeifigkeit nicht am
Gleitstatus, konvergiert derselbe Lauf in 7 Runden.

Geprüft wird:
1. Prüfkörper Platte mit Bohrung auf einer Reibfuge (μ 0,2) unter Ankerkraft, in der
   Ebene nur über die Reibfuge gehalten: der Kontaktlauf konvergiert, ohne Deckel, mit
   kleinem inneren Residuum; keine falsche Warnung „Bauteil rutscht“ (die resultierende
   Reibkraft ist null, die Reibung hält das Gleichgewicht). Rücknahme: ohne die Regel
   (contact.RT_HALT_EINMAL = False) der Deckel wie am Drehlager.
2. Ein Bauteil, das wirklich rutscht (H = 0,4 N > μ N, tests/test_solver_ext), behält die
   grobe Feder, die Warnung und die Konvergenz.
3. Dieselbe Platte mit einer reibungsfreien Nachbarfuge: hält die Nachbarfuge die Platte,
   ändert die Regel nichts.
4. Die Pendel-Prüfmodelle mit Tangente (bisher nur ohne geprüft).
5. Ausfall-Iteration: nach einem Kontaktlauf am Deckel beginnt der nächste warm
   (solver.AUSFALL_WARM_NACH_DECKEL), das Ergebnis bleibt vorläufig.

Aufruf:  python -m tests.test_pendeln_rt
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                                  # noqa: E402

from statik3d import contact, mesher, solver                        # noqa: E402
from statik3d.model import Material, Model, ShellProp               # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:86s} {str(detail)[:200]}")
    return ok


def platte_auf_reibfuge(n=16, F=300e3, mu=0.2, a=0.12, t=0.02, loch=2, nachbar=False):
    """Platte a x a x t (tet4, n x n x 2 Zellen) mit quadratischer Bohrung auf einem
    gleich grossen Unterlegblech (unten fest), Reibfuge mu; die Ankerkraft F als Last auf
    den Knoten der Oberseite im ersten Elementring um die Bohrung (Kreisring). In der
    Ebene haelt die Platte nur die Reibfuge - wie im Spannschritt, wenn der Anker inaktiv
    ist. ``nachbar``: dazu eine reibungsfreie Nachbarfuge an der Seite x = a gegen einen
    festen Klotz, Spalt null - die Platte dehnt sich unter der Last, die Seitenknoten
    oeffnen und schliessen."""
    m = Model("Platte auf Reibfuge")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=0.0))
    s = mesher.grid_box(m, "S355", a, a, t, n, n, 2, typ="tet4")
    lo, hi = (n - loch) // 2, (n + loch) // 2
    h = a / n

    def im_loch(e):
        c = np.asarray(m.nodes, float)[list(e.nodes)].mean(axis=0)
        return lo * h < c[0] < hi * h and lo * h < c[1] < hi * h
    m.elements[:] = [e for e in m.elements if not im_loch(e)]
    n_sockel = len(m.elements)
    for k in s[:, :, 0].ravel():
        m.fix(int(k), "all")
    p = mesher.grid_box(m, "S355", a, a, t, n, n, 2, origin=(0.0, 0.0, t), typ="tet4")
    m.elements[:] = m.elements[:n_sockel] + [e for e in m.elements[n_sockel:] if not im_loch(e)]
    benutzt = {int(k) for e in m.elements for k in e.nodes}
    unten = [int(k) for k in p[:, :, 0].ravel() if int(k) in benutzt]
    m.add_contact_pair("Platte/Unterlegblech", unten, list(range(n_sockel)), mu=mu)
    X = np.asarray(m.nodes, float)
    oben = [int(k) for k in p[:, :, -1].ravel() if int(k) in benutzt]
    ring = [k for k in oben if (lo - 1) * h - 1e-9 <= X[k, 0] <= (hi + 1) * h + 1e-9
            and (lo - 1) * h - 1e-9 <= X[k, 1] <= (hi + 1) * h + 1e-9]
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    for k in ring:
        m.load_node(k, Fz=-F / len(ring))
    if nachbar:
        n_vor = len(m.elements)
        q = mesher.grid_box(m, "S355", 0.02, a, t, 1, n, 2, origin=(a, 0.0, t), typ="tet4")
        for k in q[-1, :, :].ravel():
            m.fix(int(k), "all")
        seite = [int(k) for k in p[-1, :, :].ravel() if int(k) in benutzt]
        m.add_contact_pair("Platte/Nachbar", seite, list(range(n_vor, len(m.elements))), mu=0.0)
    m.active_case = "LF1"
    m.plastizitaet.an = False
    return m


def _lauf(m):
    r = solver.solve_static(m, workers=1)
    log = [str(z) for z in r.info.get("contact_log") or []]
    lb = (r.info.get("laeufe") or [{}])[-1]
    return r, log, lb


def test_platte_reibfuge():
    print("\n--- 1. Platte mit Bohrung auf Reibfuge (μ 0,2), in der Ebene nur über die Fuge gehalten ---")
    alt = contact.RT_HALT_EINMAL
    try:
        contact.RT_HALT_EINMAL = False
        r0, log0, _lb0 = _lauf(platte_auf_reibfuge())
    finally:
        contact.RT_HALT_EINMAL = alt
    check("Rücknahme (Reststeifigkeit nach dem Gleitstatus jeder Runde): Deckel nach 40 Runden",
          not r0.info.get("contact_converged") and any("40 Runden abgebrochen" in z for z in log0),
          f"konvergiert {r0.info.get('contact_converged')}, Runden {r0.info.get('contact_iterations')}")
    r, log, lb = _lauf(platte_auf_reibfuge())
    check("mit der Regel: der Kontaktlauf konvergiert, weit unter dem Deckel (höchstens 20 Runden)",
          r.info.get("contact_converged") is True and int(r.info.get("contact_iterations", 99)) <= 20,
          f"Runden {r.info.get('contact_iterations')}")
    check("… keine Warnung „Bauteil rutscht“ (die Reibung hält das Gleichgewicht, Resultierende null)",
          not any("rutscht" in z for z in log), next((z for z in log if "rutscht" in z), "")[:160])
    Fv = np.sum([c["F_vek"] for c in r.contact], axis=0)
    Fx, Fy, Fz = (float(x) for x in Fv)
    sft = sum(c["Ft"] for c in r.contact)
    check("… Last in der Fuge (ΣFz = 300 kN), Reibkräfte da (ΣFt > 0), Resultierende in der Ebene unter 1e-3 der Last",
          abs(abs(Fz) - 300e3) <= 1e-3 * 300e3 and sft > 0.01 * 300e3 and np.hypot(Fx, Fy) <= 1e-3 * abs(Fz),
          f"ΣFx {Fx:.3g} N, ΣFy {Fy:.3g} N, ΣFz {Fz:.6g} N, Σ|Ft| {sft:.4g} N")
    gl = sum(1 for c in r.contact if c["status"] == "Gleiten")
    ha = sum(1 for c in r.contact if c["status"] == "Haften")
    print(f"     Status am Ende: {gl} gleitend, {ha} haftend")
    runden = lb.get("runden") or []
    from statik3d.contact import RUNDEN_FELDER
    i_res = RUNDEN_FELDER.index("residuum")
    res_ende = float(runden[-1][i_res]) if runden else 1.0
    check("… Kontaktresiduum am Ende unter 1e-4 der Kontaktkraft", res_ende <= 1e-4, f"{res_ende:.2e}")


def test_rutschender_block():
    print("\n--- 2. Ein Bauteil, das wirklich rutscht (H = 0,4 N > μ N): grobe Feder, Warnung ---")
    m = Model()
    m.add_material(Material("S"))
    m.add_material(Material("Starr", E=210e12))
    m.add_shell_prop(ShellProp("t", 0.05))
    pl = mesher.grid_plate(m, "Starr", "t", 2.0, 2.0, 2, 2, origin=(-1, -1, 0))
    for k in pl.ravel():
        m.fix(int(k), "all")
    platte = list(range(len(m.elements)))
    box = mesher.grid_box(m, "S", 0.4, 0.4, 0.4, 2, 2, 2, origin=(-0.2, -0.2, 0.0))
    unten = [int(k) for k in box[:, :, 0].ravel()]
    oben = [int(k) for k in box[:, :, -1].ravel()]
    mu, N = 0.3, 90000.0
    m.add_contact_pair("Block/Platte", unten, platte, mu=mu)
    for k in oben:
        m.load_node(k, Fz=-N / len(oben), Fx=0.4 * N / len(oben))
    r = solver.solve_static(m, workers=1)
    log = [str(z) for z in r.info.get("contact_log") or []]
    act = [c for c in r.contact if c["status"] != "offen"]
    check("alle aktiven gleiten, Reibkraft = μ N, konvergiert, Warnung „Bauteil rutscht“",
          act and all(c["status"] == "Gleiten" for c in act)
          and abs(sum(c["Ft"] for c in r.contact) - mu * N) <= 2e-2 * mu * N
          and r.info.get("contact_converged") is True and any("rutscht" in z for z in log),
          f"ΣFt {sum(c['Ft'] for c in r.contact):.4g} N, konvergiert {r.info.get('contact_converged')}")


def test_nachbarfuge():
    print("\n--- 3. Dieselbe Platte mit reibungsfreier Nachbarfuge (Seite x = a, Spalt null) ---")
    erg = {}
    alt = contact.RT_HALT_EINMAL
    try:
        for an in (False, True):
            contact.RT_HALT_EINMAL = an
            r, log, _lb = _lauf(platte_auf_reibfuge(nachbar=True))
            st = {}
            for c in r.contact:
                k = (c["label"].split(":")[0], c["status"])
                st[k] = st.get(k, 0) + 1
            erg[an] = (r, st)
    finally:
        contact.RT_HALT_EINMAL = alt
    (r0, st0), (r1, st1) = erg[False], erg[True]
    zu = st1.get(("Platte/Nachbar", "Kontakt"), 0)
    auf = st1.get(("Platte/Nachbar", "offen"), 0)
    check("mit und ohne Regel konvergiert, Nachbarfuge teils offen, teils geschlossen",
          r0.info.get("contact_converged") is True and r1.info.get("contact_converged") is True
          and zu > 0 and auf > 0, f"Runden {r0.info.get('contact_iterations')}/{r1.info.get('contact_iterations')}, "
                                  f"Nachbar zu {zu}, offen {auf}")
    du = float(np.abs(np.asarray(r1.u) - np.asarray(r0.u)).max()) / max(float(np.abs(np.asarray(r0.u)).max()), 1e-300)
    check("… hält die Nachbarfuge die Platte, ändert die Regel nichts (gleicher Status, u gleich bis 1e-6)",
          st0 == st1 and du <= 1e-6, f"{st1}, Δu/u {du:.1e}")


def test_pendelmodelle_mit_tangente():
    print("\n--- 4. Die Pendel-Prüfmodelle (tests/test_pendeln_periode2, _kontakt_pendeln) mit Tangente ---")
    from tests import test_kontakt_pendeln as kp
    from tests import test_pendeln_periode2 as p2
    erg = {}
    alt = contact.RT_HALT_EINMAL
    try:
        for an in (False, True):
            contact.RT_HALT_EINMAL = an
            m = p2.pendelmodell(0.5e6)
            m.plastizitaet.reibungstangente = True
            erg[an] = kp.rechnen(m)
    finally:
        contact.RT_HALT_EINMAL = alt
    (r0, _c0), (r1, cs1) = erg[False], erg[True]
    pd = r1.info.get("contact_pendeln") or {}
    check("Pendelmodell p1 0,5 N/mm²: die Gruppe gleitet ganz, die Fuge hält den Block (Ausnutzung < 1) - "
          "fein; konvergiert nach dem Pendelkriterium, nicht später als ohne Regel",
          r1.info.get("contact_converged") is True and r0.info.get("contact_converged") is True
          and pd.get("ok") is True and any("die Reibung haelt das Bauteil" in str(z)
                                            for z in r1.info.get("contact_log") or [])
          and int(r1.info.get("contact_iterations", 99)) <= int(r0.info.get("contact_iterations", 0)),
          f"Runden {r0.info.get('contact_iterations')} -> {r1.info.get('contact_iterations')}, "
          f"eingefroren {pd.get('knoten')}, Weg {pd.get('weg', 0) * 1e6:.3g} µm")
    m, _kn = kp.block_auf_reiblager(anschlag=True)
    m.plastizitaet.reibungstangente = True
    r, cs = kp.rechnen(m)
    w, k, ng, nh = kp.coulomb(r, cs)
    check("Block auf Reiblager mit Anschlag: konvergiert, Coulomb erfüllt (Winkel unter 1°, Kegel ≤ 1)",
          r.info.get("contact_converged") is True and w < 1.0 and k <= 1.0 + 1e-6,
          f"Runden {r.info.get('contact_iterations')}, Winkel {w:.2f}°, Kegel {k:.4f}, {ng} gleitend, {nh} haftend")
    # Beobachtung, nicht Gegenstand dieser Aenderung (mit und ohne Regel gleich, 17.10.2026):
    # p1 5 N/mm2 endet mit Grund "pendeln", das Richtungsmodell am Deckel
    for name, mk in (("Pendelmodell p1 5 N/mm²", lambda: p2.pendelmodell(5e6)),
                     ("Richtungsmodell", p2.richtungsmodell)):
        m = mk()
        m.plastizitaet.reibungstangente = True
        r, _cs = kp.rechnen(m)
        print(f"     Beobachtung {name}: konvergiert {r.info.get('contact_converged')}, "
              f"Gründe {kp.grund(r)}, Runden {r.info.get('contact_iterations')}")


def platte_mit_zugstab():
    """Die Platte aus 1 mit einem Stab, der nur Zug aufnimmt, von einer Ecke der
    Oberseite senkrecht nach oben zu einem festen Punkt: die Ecke hebt sich unter der
    Last, der Stab bekommt Druck und faellt aus - die Ausfall-Iteration rechnet einen
    zweiten Lauf."""
    from statik3d.model import Section
    m = platte_auf_reibfuge()
    X = np.asarray(m.nodes, float)
    oben = np.nonzero(np.isclose(X[:, 2], 0.04))[0]
    A = int(oben[np.argmin(X[oben, 0] + X[oben, 1])])
    P = m.add_node(X[A, 0], X[A, 1], 0.5)
    m.fix(P, "all")
    m.add_section(Section("Stab", 1e-4, 1e-8, 1e-8, 2e-8))
    m.add_element("truss", [A, P], "S355", "Stab", nur="zug")
    return m


def test_ausfall_warm():
    print("\n--- 5. Ausfall-Iteration nach dem Deckel warm (AUSFALL_WARM_NACH_DECKEL) ---")
    alt = (contact.MAX_CYCLES, solver.AUSFALL_WARM_NACH_DECKEL)
    erg = {}
    try:
        contact.MAX_CYCLES = 3                  # der Lauf braucht 7 Runden: Deckel
        schritte = {}
        for an in (False, True):
            solver.AUSFALL_WARM_NACH_DECKEL = an
            meld = []
            r = solver.solve_static(platte_mit_zugstab(), workers=1,
                                    progress=lambda t_, *a: meld.append(str(t_)))
            erg[an] = r
            schritte[an] = [z for z in meld if z.startswith("Ausfall-Iteration")]
    finally:
        contact.MAX_CYCLES, solver.AUSFALL_WARM_NACH_DECKEL = alt
    aus0, aus1 = erg[False].info.get("ausfall"), erg[True].info.get("ausfall")
    log1 = [str(z) for z in erg[True].info.get("contact_log") or []]
    log0 = [str(z) for z in erg[False].info.get("contact_log") or []]
    d0 = sum(1 for z in log0 if "Runden abgebrochen" in z)
    d1 = sum(1 for z in log1 if "Runden abgebrochen" in z)
    check("der Stab fällt aus, zwei Schritte der Ausfall-Iteration, beide Kontaktläufe am Deckel; "
          "die Menge bleibt, die Iteration endet",
          aus0 == aus1 and len(aus1 or []) == 1 and len(schritte[False]) == 2 and len(schritte[True]) == 2
          and d0 >= 2 and d1 >= 2,
          f"ausgefallen {aus1}, Schritte {len(schritte[False])}/{len(schritte[True])}, Deckelzeilen {d0}/{d1}")
    w1 = sum(1 for z in log1 if "Warmstart" in z)
    w0 = sum(1 for z in log0 if "Warmstart" in z)
    check("Rücknahme: der zweite Lauf beginnt kalt; mit der Regel beginnt er beim Deckel-Zustand",
          w0 == 0 and w1 >= 1, f"Warmstart-Zeilen {w0}/{w1}")
    check("… und das Ergebnis bleibt vorläufig (nicht konvergiert), solange kein Lauf konvergiert",
          erg[True].info.get("contact_converged") is False, f"contact_converged {erg[True].info.get('contact_converged')}")


def main():
    test_platte_reibfuge()
    test_rutschender_block()
    test_nachbarfuge()
    test_pendelmodelle_mit_tangente()
    test_ausfall_warm()
    n_f = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_f} von {len(RESULTS)} Prüfungen bestanden")
    return 1 if n_f else 0


if __name__ == "__main__":
    sys.exit(main())
