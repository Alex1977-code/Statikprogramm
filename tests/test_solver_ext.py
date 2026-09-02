"""
Verifikation der Erweiterungen: Gelenke, Trapezlasten, Temperatur,
Schnittgroessen an Zwischenstellen, Lastfaelle/Kombinationen (Superposition),
Kontakt (einseitiges Lager, Spaltelement, Knoten-Flaeche mit Reibung),
parallele Assemblierung.
Aufruf:  python -m tests.test_solver_ext
"""
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section, ShellProp
from statik3d import solver, mesher, parallel
from statik3d.combinations import generate_combinations

RESULTS = []


def check(name, num, ana, tol):
    err = abs(num - ana) / abs(ana) if ana else abs(num)
    ok = err <= tol
    RESULTS.append((name, num, ana, err, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:48s} num={num: .6e} ana={ana: .6e} "
          f"Abw={err*100:7.3f}%")
    return ok


def _beam_line(m, mat, sec, L, ne, z0=0.0):
    ids = [m.add_node(i * L / ne, 0, z0) for i in range(ne + 1)]
    els = [m.add_element("beam", [ids[i], ids[i + 1]], mat, sec) for i in range(ne)]
    return ids, els


# --------------------------------------------------------------------------
def test_hinge():
    """Einfeldtraeger mit Momentengelenk in Feldmitte + Einspannung links:
    linke Haelfte ist Kragarm mit Endkraft = Auflagerkraft rechts = F/2? Nein:
    System: Einspannung links, Gelenk in Mitte, gelenkiges Lager rechts,
    Einzellast F am Gelenkknoten -> rechte Haelfte kraeftefrei (Pendelstuetze
    traegt nichts, da Last im Gelenk und rechter Stab nur Normalkraft?).
    Einfacher Nachweis: Durchlauftraeger 2 Felder mit Gelenk ueber Mittelstuetze
    -> M an der Mittelstuetze = 0, Feldmomente = qL^2/8."""
    L, q = 4.0, 5000.0
    m = Model()
    m.add_material(Material("S"))
    m.add_section(Section.rectangle("R", 0.1, 0.3))
    ids, els = _beam_line(m, "S", "R", 2 * L, 8)
    # Gelenk am Ende von Element 3 (Knoten 4 = Mittelstuetze): Rotation ry frei
    m.elements[3].hinges = [10]          # ry am Elementende
    for e in els:
        m.load_beam(e, qz=-q)
    m.fix(ids[0], [0, 1, 2, 3, 5]); m.fix(ids[4], [1, 2, 3, 5]); m.fix(ids[8], [1, 2, 3, 5])
    r = solver.solve_static(m)
    st = r.stations(9)
    Mmid = st[3]["My"][-1]
    check("Gelenk: Moment am Gelenk = 0", Mmid / (q * L ** 2 / 8) + 1.0, 1.0, 1e-6)
    Mfeld = max(abs(st[1]["My"]).max(), abs(st[2]["My"]).max())
    check("Gelenk: Feldmoment qL^2/8", Mfeld, q * L ** 2 / 8, 1e-3)
    check("Gelenk: Auflagerkraft Mitte qL", r.reactions[ids[4], 2], q * L, 1e-6)


def test_trapezoid_and_stations():
    """Einfeldtraeger mit Dreieckslast q(x) = q0 x/L:
    A = q0 L/6, B = q0 L/3, Mmax = q0 L^2 /(9 sqrt3) bei x = L/sqrt3."""
    L, q0 = 6.0, 8000.0
    m = Model()
    m.add_material(Material("S"))
    m.add_section(Section.rectangle("R", 0.1, 0.3))
    ne = 12
    ids, els = _beam_line(m, "S", "R", L, ne)
    for k, e in enumerate(els):
        x1, x2 = k * L / ne, (k + 1) * L / ne
        m.load_beam(e, qz=-q0 * x1 / L, q2=[0, 0, -q0 * x2 / L])
    m.fix(ids[0], [0, 1, 2, 3, 5]); m.fix(ids[-1], [1, 2, 3, 5])
    r = solver.solve_static(m)
    check("Dreieckslast: Auflager A", r.reactions[ids[0], 2], q0 * L / 6, 1e-6)
    check("Dreieckslast: Auflager B", r.reactions[ids[-1], 2], q0 * L / 3, 1e-6)
    st = r.stations(21)
    Mmax = max(np.abs(st[k]["My"]).max() for k in els)
    check("Dreieckslast: Mmax (Zwischenstellen)", Mmax, q0 * L ** 2 / (9 * np.sqrt(3)), 2e-3)
    # Querkraft ist Ableitung des Moments: Vz an x=0 = -A? Konvention: Vz(0) = -fl[2]
    Vz0 = st[els[0]]["Vz"][0]
    check("Dreieckslast: |Vz(0)| = A", abs(Vz0), q0 * L / 6, 1e-6)
    # Gleichgewicht ueber Stab (Elementkette): Momentensumme
    mem = m.add_member("S1", els)
    mf = r.member_forces(mem, 5)
    check("Stab-Schnittgroessen: Laenge", mf["L"], L, 1e-12)
    check("Stab-Schnittgroessen: M(0)=0", abs(mf["My"][0]) / (q0 * L ** 2) + 1, 1.0, 1e-9)


def test_temperature():
    """Beidseitig gehaltener Stab: N = -E A alpha dT (Druck)."""
    L, dT = 3.0, 40.0
    m = Model()
    m.add_material(Material("S", alpha=1.2e-5))
    sec = m.add_section(Section.rectangle("R", 0.1, 0.1))
    ids, els = _beam_line(m, "S", "R", L, 3)
    m.fix(ids[0], "all"); m.fix(ids[-1], "all")
    for e in els:
        m.load_temp(e, dT)
    r = solver.solve_static(m)
    N = r.beam_forces[0]["N"][0]
    check("Temperatur: gehaltener Stab N", N, -210e9 * sec.A * 1.2e-5 * dT, 1e-9)
    # freier Stab: spannungsfrei, Verlaengerung alpha dT L
    m2 = Model()
    m2.add_material(Material("S", alpha=1.2e-5))
    m2.add_section(Section.rectangle("R", 0.1, 0.1))
    ids, els = _beam_line(m2, "S", "R", L, 3)
    m2.fix(ids[0], "all")
    for e in els:
        m2.load_temp(e, dT)
    r2 = solver.solve_static(m2)
    check("Temperatur: freier Stab Dehnung", r2.u[ids[-1], 0], 1.2e-5 * dT * L, 1e-9)
    check("Temperatur: freier Stab N = 0", abs(r2.beam_forces[0]["N"][0]) / 1e3 + 1, 1.0, 1e-9)


def test_superposition():
    """Kombination per Superposition == direkte Loesung mit Faktoren."""
    L = 5.0
    m = Model()
    m.add_material(Material("S"))
    m.add_section(Section.i_profile("IPE 200", 0.2, 0.1, 0.0056, 0.0085, 0.012))
    ids, els = _beam_line(m, "S", "IPE 200", L, 5)
    m.fix(ids[0], "all")
    m.set_gravity(-9.81)                       # LF1 (G)
    m.add_load_case("Q", "Q_B")
    m.load_node(ids[-1], Fz=-10000.0)
    m.add_load_case("W", "W")
    for e in els:
        m.load_beam(e, qy=2000.0)
    m.add_combination("K1", {"LF1": 1.35, "Q": 1.5, "W": 0.9}, "ULS")
    an = solver.solve_all(m)
    r_sup = an.combinations["K1"]
    sysm = solver.StaticSystem(m)
    r_dir = solver._solve_loads(m, sysm, {"LF1": 1.35, "Q": 1.5, "W": 0.9}, "K1", "combination")
    check("Superposition: Verschiebung", r_sup.u[ids[-1], 2], r_dir.u[ids[-1], 2], 1e-10)
    check("Superposition: Einspannmoment My", r_sup.beam_forces[0]["My"][0],
          r_dir.beam_forces[0]["My"][0], 1e-10)
    check("Superposition: Mz", r_sup.beam_forces[0]["Mz"][0], r_dir.beam_forces[0]["Mz"][0], 1e-10)
    st1, st2 = r_sup.stations(5)[2], r_dir.stations(5)[2]
    check("Superposition: Zwischenstellen", st1["Mz"][2], st2["Mz"][2], 1e-10)
    # Umhuellende
    env = an.envelopes["ULS"]
    check("Umhuellende: max |u|", env.umag_max.max(), r_dir.umag.max(), 1e-10)
    # Automatische Kombinationen
    n = len(generate_combinations(m))
    check("Kombinationsgenerator: Anzahl > 0", float(n > 0), 1.0, 0)


def test_unilateral_support():
    """Zweifeldtraeger, Last nur im linken Feld -> rechtes Endlager hebt ab.
    Mit einseitigem Lager rechts: System = Kragarm ueber Mittelstuetze mit
    Endlager links?  Klarer: Einfeldtraeger mit Kragarm: Lager A (links, beidseitig),
    einseitiges Lager B (Mitte), Last am Kragarmende zieht B nach oben?
    Wir nehmen: Einfeldtraeger A-B (L), Kragarm B-C (L/2), Einzellast F nach unten
    am Ende C. Lager A ist einseitig (nur Druck): A muesste Zug erhalten
    (F*L/2 / L = F/2 Zug) -> oeffnet -> System wird kinematisch? Nein: B haelt,
    A oeffnet -> Kragarm um B ohne Halt -> kinematisch. Daher Gegenlast:
    Eigengewichtsersatz G = 3F nach unten in Feldmitte -> A bleibt gedrueckt.
    Testfall 1: A einseitig, Druck erwartet -> gleiche Loesung wie beidseitig.
    Testfall 2: Last im Feld weg, zusaetzlich federndes einseitiges Lager unter C:
    C-Lager bekommt Druck, A wird zum Zuglager -> A oeffnet -> Loesung entspricht
    System mit Lagern B und C."""
    L, F = 4.0, 10000.0
    m = Model()
    m.add_material(Material("S"))
    m.add_section(Section.rectangle("R", 0.1, 0.3))
    ids, els = _beam_line(m, "S", "R", 1.5 * L, 6)   # Knoten 0..6, Lager B bei Knoten 4 (x=L)
    A, B, C = ids[0], ids[4], ids[6]
    m.fix(A, [0, 1, 3, 5])
    m.fix(B, [1, 2, 3, 5])
    m.add_contact_support(A, (0, 0, 1))                   # einseitig in z
    m.load_node(C, Fz=-F)
    m.load_node(ids[2], Fz=-3 * F)
    r = solver.solve_static(m)
    # Vergleich: beidseitiges Lager
    m2 = m.copy(); m2.contact_supports.clear(); m2.fix(A, [2])
    r2 = solver.solve_static(m2)
    check("Einseitiges Lager (Druck): wie beidseitig", r.u[C, 2], r2.u[C, 2], 1e-4)
    check("Einseitiges Lager: Reaktion A", r.reactions[A, 2], r2.reactions[A, 2], 1e-6)
    # Fall 2: Feldlast weg, Lager unter C einseitig -> A hebt ab
    m3 = m.copy()
    m3.case().nodal_loads = []
    m3.load_node(ids[5], Fz=-F)          # Last zwischen B und C
    m3.add_contact_support(C, (0, 0, 1))
    # Last im Feld B-C drueckt C ins Lager; A will nach oben -> A oeffnet, Stab liegt auf B und C
    r3 = solver.solve_static(m3)
    stat = {c["node"]: c["status"] for c in r3.contact}
    check("Einseitiges Lager: A offen", float(stat[A] == "offen"), 1.0, 0)
    check("Einseitiges Lager: C Kontakt", float(stat[C] != "offen"), 1.0, 0)
    # Vergleich: A frei, C gelagert
    m4 = m3.copy(); m4.contact_supports.clear(); m4.fix(C, [2])
    r4 = solver.solve_static(m4)
    check("Einseitiges Lager: Verschiebung A wie ohne Lager", r3.u[A, 2], r4.u[A, 2], 1e-4)
    check("Einseitiges Lager: Reaktion C = Kontaktkraft", r3.reactions[C, 2], r4.reactions[C, 2], 1e-4)


def test_gap_element():
    """Kragarm, dessen Spitze nach einem Spalt s auf einen Anschlag trifft:
    Endverschiebung = s (Anschlag starr), Kontaktkraft = F - 3EI s / L^3."""
    L, F, s = 3.0, 20000.0, 0.002
    m = Model()
    m.add_material(Material("S"))
    sec = m.add_section(Section.rectangle("R", 0.1, 0.2))
    sec.Asz = 0.0; sec.Asy = 0.0            # Bernoulli fuer Handformel
    ids, els = _beam_line(m, "S", "R", L, 6)
    m.fix(ids[0], "all")
    stop = m.add_node(L, 0, -s)               # Anschlagknoten unter der Spitze
    m.fix(stop, "all")
    m.add_gap_element(ids[-1], stop, direction=(0, 0, -1), gap=s)
    # Richtung a->b = -z: Kontakt wenn sich b (Anschlag) relativ zu a um mehr als gap auf a zubewegt,
    # d.h. a bewegt sich nach -z ueber s hinaus.
    m.load_node(ids[-1], Fz=-F)
    r = solver.solve_static(m)
    check("Spaltelement: Endverschiebung = Spalt", -r.u[ids[-1], 2], s, 1e-3)
    Fc = r.contact[0]["Fn"]
    ana = F - 3 * 210e9 * sec.Iy * s / L ** 3
    check("Spaltelement: Kontaktkraft", Fc, ana, 1e-3)
    # ohne Kontakt (Last klein): Spalt bleibt offen
    m.case().nodal_loads[0].F = [0, 0, -100.0, 0, 0, 0]
    r = solver.solve_static(m)
    check("Spaltelement: offen bei kleiner Last", float(r.contact[0]["status"] == "offen"), 1.0, 0)


def test_surface_contact_friction():
    """Block (Hex8) auf starrer Platte (Schalen-Facetten): Auflast N, Horizontalkraft H.
    H < mu N -> Haften (Block folgt nur elastisch), H > mu N -> Gleiten."""
    m = Model()
    m.add_material(Material("S"))
    m.add_material(Material("Starr", E=210e12))
    m.add_shell_prop(ShellProp("t", 0.05))
    # starre Platte z = 0 aus shell4, 2x2 m
    pl = mesher.grid_plate(m, "Starr", "t", 2.0, 2.0, 2, 2, origin=(-1, -1, 0))
    for n in pl.ravel():
        m.fix(int(n), "all")
    plate_elems = list(range(len(m.elements)))
    # Block 0.4 x 0.4 x 0.4 direkt auf der Platte (z von 0 bis 0.4), Knoten getrennt
    box = mesher.grid_box(m, "S", 0.4, 0.4, 0.4, 2, 2, 2, origin=(-0.2, -0.2, 0.0))
    bottom = [int(n) for n in box[:, :, 0].ravel()]
    top = [int(n) for n in box[:, :, -1].ravel()]
    mu = 0.3
    m.add_contact_pair("Block/Platte", bottom, plate_elems, mu=mu)
    N, H = 90000.0, 13500.0          # H = 0.5 mu N
    for n in top:
        m.load_node(n, Fz=-N / len(top), Fx=H / len(top))
    # Kippsicherung: kleines Verhaeltnis H/N -> alle Knoten gedrueckt
    r = solver.solve_static(m)
    stat = [c["status"] for c in r.contact]
    Fn = sum(c["Fn"] for c in r.contact)
    check("Flaechenkontakt: Summe Kontaktkraft = N", Fn, N, 1e-3)
    check("Flaechenkontakt: nicht alle gleiten (H < mu N)",
          float(any(s == "Haften" for s in stat) and not all(s == "Gleiten" for s in stat)), 1.0, 0)
    Rx = r.reactions[:, 0].sum()
    check("Flaechenkontakt: Gleichgewicht x", Rx, -H, 1e-6)
    Rz = r.reactions[:, 2].sum()
    check("Flaechenkontakt: Gleichgewicht z", Rz, N, 1e-6)
    check("Flaechenkontakt: Kontaktkraefte auf Knoten", r.contact_forces[bottom, 2].sum(), N, 1e-3)
    check("Flaechenkontakt: Reibkraefte im Gleichgewicht mit H", r.contact_forces[bottom, 0].sum(), -H, 1e-2)
    check("Flaechenkontakt: Coulomb an haftenden Knoten (Ft/mu Fn in 0..1)",
          max((c["Ft"] / (mu * c["Fn"]) for c in r.contact if c["status"] == "Haften" and c["Fn"] > 0), default=0.0),
          0.5, 1.0)
    # Gleiten
    for l in m.case().nodal_loads:
        l.F[0] = 0.4 * N / len(top)      # H = 0.4 N > mu N (Kippen: H*0.4 = 14.4 < N*0.2 = 18 kNm)
    r = solver.solve_static(m)
    act = [c for c in r.contact if c["status"] != "offen"]
    Ft = sum(c["Ft"] for c in r.contact)
    check("Flaechenkontakt: hintere Reihe hebt ab (Moment)",
          float(sum(1 for c in r.contact if c["status"] == "offen") == 3), 1.0, 0)
    check("Flaechenkontakt: alle aktiven gleiten (H > mu N)",
          float(bool(act) and all(c["status"] == "Gleiten" for c in act)), 1.0, 0)
    check("Flaechenkontakt: Reibkraft = mu N", Ft, mu * N, 2e-2)
    check("Flaechenkontakt: Iteration konvergiert", float(r.info["contact_converged"]), 1.0, 0)
    check("Flaechenkontakt: Warnung Rutschen", float(any("rutscht" in w for w in r.info["contact_log"])), 1.0, 0)
    # Teilweises Abheben mit hoher Reibung: H = 0.444 N -> hintere Reihe hebt ab (H > N/3),
    # kein Kippen (H*0.4 = 16 < N*0.2 = 18 kNm), kein Gleiten (mu = 1)
    m.contact_pairs[0].mu = 1.0
    for l in m.case().nodal_loads:
        l.F[0] = 0.444 * N / len(top)
    r = solver.solve_static(m)
    n_open = sum(1 for c in r.contact if c["status"] == "offen")
    check("Flaechenkontakt: Kippen -> Knoten heben ab", float(0 < n_open < 9), 1.0, 0)
    check("Flaechenkontakt: Kippen Summe Fn = N", sum(c["Fn"] for c in r.contact), N, 1e-3)
    # Vollstaendiges Abheben: kein Gleichgewicht -> verstaendliche Fehlermeldung
    for l in m.case().nodal_loads:
        l.F[0] = 0.0
        l.F[2] = +N / len(top)
    try:
        solver.solve_static(m)
        ok = 0.0
    except RuntimeError as ex:
        ok = float("hebt" in str(ex) or "Gleichgewicht" in str(ex))
    check("Flaechenkontakt: vollstaendiges Abheben -> Fehlermeldung", ok, 1.0, 0)


def test_parallel_assembly():
    """Parallele Assemblierung/Nachlauf liefert identische Ergebnisse."""
    from statik3d.examples_lib import plate_example
    m = plate_example()
    r1 = solver.solve_static(m, workers=1)
    old = parallel.settings().min_elements
    parallel.configure(min_elements=1)
    try:
        r2 = solver.solve_static(m, workers=3)
    finally:
        parallel.configure(min_elements=old)
    check("Parallel: Verschiebung identisch", r2.umag.max(), r1.umag.max(), 1e-12)
    check("Parallel: Spannung identisch", np.nanmax(r2.node_vm), np.nanmax(r1.node_vm), 1e-12)


def test_farm():
    """Farm-Server + Worker (Threads) + Client: Auftraege verteilen."""
    from statik3d import farm
    from statik3d.parallel import Job
    from statik3d.examples_lib import frame_example
    port = 5599
    farm.start_server_thread("127.0.0.1", port, "test")
    stop, ths = farm.start_worker_threads("127.0.0.1", port, "test", n=2)
    try:
        client = farm.FarmClient("127.0.0.1", port, "test")
        m = frame_example()
        m.add_combination("K1", {"LF1": 1.35}, "ULS")
        m.add_combination("K2", {"LF1": 1.0}, "SLS_CH")
        jobs = [Job("ping", {"x": 1}),
                Job("solve_combination", {"model": m.to_dict(), "combination": "K1"}),
                Job("solve_combination", {"model": m.to_dict(), "combination": "K2"})]
        res = client.run(jobs, timeout=120)
        check("Farm: ping ok", float(res[0].ok), 1.0, 0)
        ref = solver.solve_static(m)
        check("Farm: Kombination 1.35*LF1", res[1].result.umag.max(), 1.35 * ref.umag.max(), 1e-9)
        check("Farm: Kombination 1.0*LF1", res[2].result.umag.max(), ref.umag.max(), 1e-9)
        st = client.status()
        check("Farm: 2 Worker registriert", float(len(st["workers"])), 2.0, 0)
        # ueber parallel.run_jobs mit backend farm
        parallel.configure(backend="farm", farm_host="127.0.0.1", farm_port=port, farm_key="test")
        try:
            out = solver.solve_combinations(m, use_jobs=True)
        finally:
            parallel.configure(backend="local")
        check("Farm: solve_combinations ueber run_jobs", out["K1"].umag.max(),
              1.35 * ref.umag.max(), 1e-9)
    finally:
        stop.set()


def main():
    print("=" * 96)
    print("STATIK3D - Verifikation Erweiterungen (Gelenke, Lasten, Kombinationen, Kontakt, Parallel)")
    print("=" * 96)
    test_hinge()
    test_trapezoid_and_stations()
    test_temperature()
    test_superposition()
    test_unilateral_support()
    test_gap_element()
    test_surface_contact_friction()
    test_parallel_assembly()
    test_farm()
    nok = sum(1 for r in RESULTS if r[4])
    print("=" * 96)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
