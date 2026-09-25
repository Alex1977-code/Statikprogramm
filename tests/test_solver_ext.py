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
    # 1e-9 statt 1e-12: die parallelen Elementschleifen summieren in anderer
    # Reihenfolge, das letzte Bit kann sich unterscheiden. Die Spannung erbt
    # das aus den Verschiebungen - 1e-9 von 60 N/mm² sind 6e-8 N/mm², weit
    # unter jeder Ablesegenauigkeit.
    check("Parallel: Verschiebung identisch", r2.umag.max(), r1.umag.max(), 1e-9)
    check("Parallel: Spannung identisch", np.nanmax(r2.node_vm), np.nanmax(r1.node_vm), 1e-9)


def test_stehender_pool():
    """Ein Prozesspool je Rechnung: das Modell einmal je Arbeiter aus der
    Datei, verschachtelte Bloecke teilen ihn, danach ist er zu. Gemessen am
    Drehlager: 244 s Nachlauf je Lastfall, weil jeder Aufruf einen neuen Pool
    startete und das 275-MB-Modell je Arbeiter pickelte."""
    from statik3d.examples_lib import plate_example

    def check_bool(name, ok):
        check(name, 1.0 if ok else 0.0, 1.0, 0.0)

    m = plate_example()
    old = parallel.settings().min_elements
    parallel.configure(min_elements=1)
    try:
        r1 = solver.solve_static(m, workers=1)
        with parallel.arbeiter(m, workers=3) as a:
            check_bool("Pool steht und ist der aktive Block", a.pool is not None and parallel._AKTIV is a
                       and a.pfad is not None and os.path.exists(a.pfad))
            with parallel.arbeiter(m, workers=3) as b:
                check_bool("verschachtelt: derselbe Pool, Tiefe 2", b is a and a.tiefe == 2)
            check_bool("nach dem inneren Block steht er noch", parallel._AKTIV is a and a.tiefe == 1)
            r2 = solver.solve_static(m, workers=3)
            n1 = a.aufrufe
            r3 = solver.solve_static(m, workers=3)
            check_bool("zwei Rechnungen ueber denselben Pool (Aufrufe zaehlen hoch, kein Neustart)",
                       n1 > 0 and a.aufrufe > n1 and parallel._AKTIV is a and a.pool is not None)
            pfad = a.pfad
        check_bool("danach ist der Pool zu, die Modelldatei weg, kein aktiver Block",
                   parallel._AKTIV is None and a.pool is None and not os.path.exists(pfad))
        check("stehender Pool: Verschiebung identisch", r2.umag.max(), r1.umag.max(), 1e-9)
        check("stehender Pool: Spannung identisch", np.nanmax(r3.node_vm), np.nanmax(r1.node_vm), 1e-9)
        keine = [f for f in os.listdir(__import__("tempfile").gettempdir())
                 if f.startswith("statik3d_pool_") or f.startswith("statik3d_extra_")]
        check_bool("keine Pool-Dateien bleiben liegen", not any(pfad.endswith(f) for f in keine))
    finally:
        parallel.configure(min_elements=old)


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


def pruefe(name, ok, detail=""):
    """Ja/Nein-Pruefung mit der Zahlenhilfe dieser Datei (check erwartet
    Messwert und Sollwert) - dieselbe Ausgabe, damit main() weiterzaehlt."""
    check(f"{name}" + (f"  [{detail}]" if detail else ""), 1.0 if ok else 0.0, 1.0, 0.0)
    return bool(ok)


def test_ketten_rechnen_dasselbe():
    """Rechenketten: mehrere Lastfälle gleichzeitig, jede Kette in einem
    eigenen Prozess und in sich warm gestartet.

    Der Warmstart ist der größte Einzelgewinn je Lastfall (Drehlager
    20.09.2026: kalt 112 Kontaktrunden, warm 41 bis 48). Wer alle Lastfälle
    als einzelne Aufträge verteilt, macht jeden kalt und verliert mehr, als
    die Parallelität bringt - darum kommt eine ganze Folge in einen Auftrag.
    Geprüft wird, dass dabei dasselbe herauskommt."""
    from statik3d import parallel
    from statik3d.examples_lib import hall_frame_example
    m = hall_frame_example()
    namen = list(m.load_cases)
    pruefe(f"Probe mit {len(namen)} Lastfällen", len(namen) >= 4, str(namen))
    alt_k = parallel.settings().ketten
    try:
        parallel.configure(ketten=1)
        a = solver.solve_cases(m, cases=namen)
        parallel.configure(ketten=3)
        b = solver.solve_cases(m, cases=namen)
    finally:
        parallel.configure(ketten=alt_k)
    pruefe("die Ketten liefern dieselben Lastfälle in derselben Reihenfolge",
          list(a) == list(b) == namen, str(list(b)))
    d = max(float(np.abs(a[n].u - b[n].u).max()) for n in namen)
    bez = max(max(float(np.abs(a[n].u).max()) for n in namen), 1e-30)
    pruefe("und dieselben Verschiebungen", d <= 1e-12 * bez, f"{d / bez:.2e} relativ")
    dr = max(float(np.abs(a[n].reactions - b[n].reactions).max()) for n in namen)
    pruefe("und dieselben Auflagerkräfte", dr <= 1e-9 * max(
        max(float(np.abs(a[n].reactions).max()) for n in namen), 1e-30), f"{dr:.2e} N")
    pruefe("das Modell hängt wieder an jedem Ergebnis (es wird nicht zurückgesendet)",
          all(b[n].model is m for n in namen))


def test_ketten_teilen_und_zaehlen():
    """Die Aufteilung hält jede Situation zusammen - sonst liefe der
    Warmstart ins Leere, denn jede Situation hat ihr eigenes System. Und die
    Zahl der Ketten folgt der Einstellung, 0 heißt automatisch."""
    from statik3d import parallel
    from statik3d.examples_lib import hall_frame_example
    m = hall_frame_example()
    namen = list(m.load_cases)
    bloecke = solver._ketten_teilen(m, namen, 3)
    pruefe("drei Ketten aus fünf Lastfällen", len(bloecke) == 3, str(bloecke))
    pruefe("jeder Lastfall genau einmal",
          sorted(x for b in bloecke for x in b) == sorted(namen),
          str(sorted(x for b in bloecke for x in b)))
    # Situationen bleiben zusammenhängend: die Folge der Blöcke ist die
    # Folge der Situationen
    folge = [n for b in bloecke for n in b]
    je_sit = m.lastfaelle_je_situation(namen)
    soll = [n for v in je_sit.values() for n in v]
    pruefe("die Reihenfolge folgt den Situationen", folge == soll, str(folge))
    pruefe("mehr Ketten als Lastfälle gibt es nicht",
          len(solver._ketten_teilen(m, namen[:2], 9)) <= 2,
          str(solver._ketten_teilen(m, namen[:2], 9)))
    alt_k = parallel.settings().ketten
    try:
        parallel.configure(ketten=1)
        pruefe("Vorgabe 1: nacheinander wie bisher", solver.ketten_zahl(50) == 1)
        parallel.configure(ketten=4)
        pruefe("vier Ketten, aber nie mehr als Lastfälle",
              solver.ketten_zahl(50) == 4 and solver.ketten_zahl(2) == 2)
        parallel.configure(ketten=0)
        n = solver.ketten_zahl(50)
        pruefe(f"0 heißt automatisch nach freiem Speicher ({n} Ketten)",
              1 <= n <= parallel.settings().workers, str(n))
    finally:
        parallel.configure(ketten=alt_k)


def test_ketten_greifen_nicht_wo_sie_nicht_duerfen():
    """Mit übergebenem System gilt dieses für alle genannten Lastfälle - dann
    wird nicht geteilt.

    Bis zum 22.09.2026 stand hier auch, eingefrorene Ermüdungszustände
    verhinderten das Teilen. Das stimmte, war aber die Sperre selbst und
    nicht ihre Begründung: sie brauchen ihren Referenzzustand aus demselben
    Lauf, und das ist eine Frage des **Schnitts**, nicht des Teilens. Seit
    `_ketten_teilen` an Gruppengrenzen schneidet, dürfen sie mit
    (test_ketten_mit_eingefrorenen_zustaenden). Die Zusicherungen dieser
    Prüfung haben den Referenzfall ohnehin nie angesehen - nur den Docstring
    hat es geglaubt.
    """
    from statik3d import parallel
    from statik3d.examples_lib import hall_frame_example
    m = hall_frame_example()
    namen = list(m.load_cases)
    gerufen = {"n": 0}
    alt_fn = solver._cases_in_ketten

    def merken(*a, **kw):
        gerufen["n"] += 1
        return alt_fn(*a, **kw)

    alt_k = parallel.settings().ketten
    solver._cases_in_ketten = merken
    try:
        parallel.configure(ketten=3)
        sys_ = solver.StaticSystem(m)
        solver.solve_cases(m, cases=namen, system=sys_)
        pruefe("mit übergebenem System wird nicht in Ketten geteilt", gerufen["n"] == 0,
              str(gerufen["n"]))
        solver.solve_cases(m, cases=namen)
        pruefe("ohne System dagegen schon", gerufen["n"] == 1, str(gerufen["n"]))
    finally:
        solver._cases_in_ketten = alt_fn
        parallel.configure(ketten=alt_k)


def _ermuedungsmodell(n_lasten=4, je=3):
    """Block mit Reibung, dazu n_lasten Ermüdungslasten mit je Zuständen.

    **Mehrere** Lasten, nicht eine: die Zustände EINER Ermüdungslast hängen
    alle an derselben Referenz und bilden eine einzige unteilbare Gruppe - da
    gibt es nichts zu teilen. Der Hebel entsteht erst zwischen den Lasten. Am
    Drehlager sind es 50 Ermüdungslasten mit 164 Zuständen.
    """
    import copy
    from statik3d.examples_lib import block_friction_example
    m = block_friction_example()
    grund = m.case()
    namen, gruppen = [], []
    for e in range(n_lasten):
        zust = []
        for i in range(je):
            name = f"E{e + 1}Z{i + 1}"
            lc = copy.deepcopy(grund)
            lc.name = name
            lc.description = f"Ermüdungslast {e + 1}, Zustand {i + 1}"
            f = 1.0 + 0.05 * (e * je + i)       # Zustände nicht identisch
            for nl in lc.nodal_loads:
                nl.F = [v * f for v in nl.F]
            m.load_cases[name] = lc
            zust.append(name)
        namen.extend(zust)
        gruppen.append(zust)
    for k in list(m.load_cases):
        if k not in namen:
            del m.load_cases[k]
    for e, zust in enumerate(gruppen):
        fl = m.add_fatigue_load(f"EL{e + 1}", zust[0], zust[-1])
        fl.folge = list(zust)
    return m, namen, gruppen


def test_ketten_mit_eingefrorenen_zustaenden():
    """Rechenketten trotz Ermüdungsreferenzen - aber nie durch eine Gruppe.

    Am Drehlager liefen bis zum 22.09.2026 **alle 422 Lastfälle
    hintereinander in einem Prozess**, weil `_solve_cases_innen` die Ketten
    sperrte, sobald es eingefrorene Zustände gab. `ermuedungsreferenzen`
    liefert dort 117 davon - die Sperre griff also immer. Sie war keine
    Eigenschaft der Rechnung, sondern die Folge davon, dass `_ketten_teilen`
    an festen Blöcken schnitt: liegt eine Referenz in einer anderen Kette,
    gibt `_einfrieren` still `(None, None)` zurück und der Zustand rechnet
    voll nichtlinear - **kein falsches Ergebnis, aber der Gewinn ist weg, und
    niemand sieht es.**

    Geprüft wird darum genau das, was dabei schiefgehen kann.
    """
    from statik3d import parallel, solver
    m, namen, gruppen = _ermuedungsmodell()
    ref = solver.ermuedungsreferenzen(m)
    pruefe("das Prüfmodell hat eingefrorene Zustände",
           len(ref) == len(gruppen) * 2 and len(set(ref.values())) == len(gruppen),
           f"{len(ref)} Zustände, {len(set(ref.values()))} Referenzen")

    for k in (1, 2, 3, 4, 9):
        b = solver._ketten_teilen(m, namen, k, ref)
        heil = all(any(set(g) <= set(kette) for kette in b) for g in gruppen)
        einmal = sorted(x for kette in b for x in kette) == sorted(namen)
        pruefe(f"k={k}: keine Gruppe wird zerschnitten", heil, str(b))
        pruefe(f"k={k}: jeder Lastfall genau einmal", einmal)
        pruefe(f"k={k}: nie mehr Ketten als angefordert", len(b) <= max(1, k),
               f"{len(b)} Ketten bei k={k}")

    # Ohne Referenzen muss sich nichts geändert haben
    ohne = solver._ketten_teilen(m, namen, 3)
    pruefe("ohne Referenzen bleibt die alte Aufteilung",
           len(ohne) == 3 and sorted(x for b_ in ohne for x in b_) == sorted(namen),
           str([len(b_) for b_ in ohne]))

    alt_k = parallel.settings().ketten
    gerufen = {"n": 0}
    echt = solver._cases_in_ketten

    def merken(*a, **kw):
        gerufen["n"] += 1
        return echt(*a, **kw)

    solver._cases_in_ketten = merken
    try:
        parallel.configure(ketten=2)
        erg2 = solver.solve_cases(m, cases=list(namen), referenzen=ref)
        pruefe("mit eingefrorenen Zuständen wird jetzt geteilt", gerufen["n"] == 1,
               f"{gerufen['n']}x gerufen")
        parallel.configure(ketten=1)
        erg1 = solver.solve_cases(m, cases=list(namen), referenzen=ref)
    finally:
        solver._cases_in_ketten = echt
        parallel.configure(ketten=alt_k)

    # Seit dem 22.09.2026 bleibt ein Zustand nur eingefroren, wenn sein
    # eingefrorener Kontaktzustand zur Last passt; sonst wird er nachgerechnet
    # (contact_frozen_verworfen). Die Ketten duerfen daran nichts aendern:
    # dieselben Zustaende eingefroren, dieselben verworfen, und jeder Zustand
    # mit Referenz ist eines von beiden.
    def _art(e):
        i = e.info
        return "eingefroren" if i.get("contact_frozen") else             "verworfen" if i.get("contact_frozen_verworfen") else "frei"
    arten1 = {n: _art(erg1[n]) for n in namen}
    arten2 = {n: _art(erg2[n]) for n in namen}
    mit_ref1 = sorted(n for n in namen if arten1[n] != "frei")
    pruefe("dieselben Zustände sind eingefroren bzw. verworfen wie ohne Ketten",
           arten1 == arten2 and mit_ref1 == sorted(ref),
           f"eingefroren {sum(a == 'eingefroren' for a in arten1.values())} gegen "
           f"{sum(a == 'eingefroren' for a in arten2.values())}, verworfen "
           f"{sum(a == 'verworfen' for a in arten1.values())} gegen "
           f"{sum(a == 'verworfen' for a in arten2.values())}, mit Referenz {len(mit_ref1)} von {len(ref)}")

    # Die erste Kette sieht dieselbe Folge wie der Einzellauf und muss darum
    # bitgleich sein. Die zweite beginnt mit einem **kalten** Kopf - dort
    # weicht sie ab, und das ist der Preis der Ketten, nicht ein Fehler.
    bloecke = solver._ketten_teilen(m, namen, 2, ref)
    erste = set(bloecke[0])
    d_erste = max(float(np.abs(np.asarray(erg1[n].u, float)
                               - np.asarray(erg2[n].u, float)).max()) for n in erste)
    pruefe("die erste Kette rechnet bitgleich wie der Einzellauf", d_erste == 0.0,
           f"{d_erste:.3e} m")
    rest = [n for n in namen if n not in erste]
    d_rest = max(float(np.abs(np.asarray(erg1[n].u, float)
                              - np.asarray(erg2[n].u, float)).max()) for n in rest)
    gross = max(float(np.abs(np.asarray(erg1[n].u, float)).max()) for n in rest)
    pruefe("die zweite weicht ab - ihr Kopf startet kalt", d_rest > 0.0,
           f"{d_rest:.3e} m ({d_rest / gross:.1e} relativ)")
    pruefe("aber nur in der dritten Stelle", d_rest < 1e-2 * gross,
           f"{d_rest / gross:.1e} relativ")


class _SitModell:
    """Ein Modellstummel, der nur sagt, welche Lastfälle zu welcher Situation
    gehören - mehr braucht `_ketten_teilen` nicht."""

    def __init__(self, je_situation):
        self._je = dict(je_situation)

    def lastfaelle_je_situation(self, namen=None):
        if namen is None:
            return dict(self._je)
        drin = set(namen)
        return {k: [n for n in v if n in drin] for k, v in self._je.items()
                if any(n in drin for n in v)}


def test_ketten_zerreissen_die_situationen_nicht():
    """Die Referenzordnung gilt je Situation, nicht über alle Lastfälle.

    `_mit_referenzen_zuerst` zieht jeden Referenzzustand vor die Zustände, die
    ihn einfrieren. Über **alle** Lastfälle angewandt zieht es damit Fälle aus
    einer Situation vor und zerreißt die Ordnung, die derselbe Docstring
    zusichert. Jede Situation, die eine Kette berührt, kostet dort ein eigenes
    System und eine eigene Faktorisierung (87 s von 235 s je Lastfall am
    Drehlager), während `ketten_zahl` mit 9,5 GB je Kette für **eine** Matrix
    rechnet.

    Gefunden von drei unabhängigen Blickrichtungen einer Gegenlesung am
    22.09.2026 - und zwar an einer Fassung, die ich zwei Stunden vorher
    gebaut hatte.
    """
    m = _SitModell({"Grund": ["A1", "A2", "A3"], "Stellung2": ["B1", "B2", "B3"]})
    namen = ["A1", "A2", "A3", "B1", "B2", "B3"]
    # A3 friert A1 ein, B3 friert B1 ein - die Referenzen stehen NICHT vorn
    ref = {"A3": "A1", "B3": "B1"}
    folge = [n for kette in solver._ketten_teilen(m, namen, 1, ref) for n in kette]
    a = [i for i, n in enumerate(folge) if n.startswith("A")]
    b = [i for i, n in enumerate(folge) if n.startswith("B")]
    pruefe("jede Situation bleibt zusammenhängend",
           max(a) < min(b) or max(b) < min(a), str(folge))
    pruefe("und innerhalb der Situation steht die Referenz vor ihrem Zustand",
           folge.index("A1") < folge.index("A3")
           and folge.index("B1") < folge.index("B3"), str(folge))


def test_kettenabbruch_behaelt_die_fertigen_ketten():
    """Bricht eine Kette, bleiben die Ergebnisse der anderen erhalten.

    Der Abbruchschutz vom 19.09.2026 (`_teil_merken`) rettet jeden fertigen
    Lastfall an die Ausnahme. Der Kettenweg lag bis zum 22.09.2026 **vor**
    diesem Schutz: `_cases_in_ketten` warf beim ersten nicht-ok sofort, und
    die fertigen Ergebnisse aller übrigen Ketten waren weg. Am Drehlager
    hätte ein einziger divergierender Lastfall die Rechenzeit von Stunden
    gekostet - und das ausgerechnet auf dem Weg, der für dieses Modell
    gebaut wurde.
    """
    from statik3d import parallel
    from statik3d.examples_lib import hall_frame_example
    m = hall_frame_example()
    namen = list(m.load_cases)

    class _Erg:
        def __init__(self, ok, result=None, error=""):
            self.ok, self.result, self.error = ok, result, error

    echt = solver.run_jobs if hasattr(solver, "run_jobs") else None

    def run_jobs_stub(jobs, workers=None, progress=None):
        # Die erste Kette gelingt, die zweite faellt aus
        aus = []
        for i, j in enumerate(jobs):
            faelle = list(j.payload.get("cases") or [])
            if i == 0:
                aus.append(_Erg(True, {n: _Ergebnis_stub(n) for n in faelle}))
            else:
                aus.append(_Erg(False, None, "Arbeiter abgestürzt"))
        return aus

    class _Ergebnis_stub:
        def __init__(self, name):
            self.name = name
            self.model = None
            self.info = {}

    import statik3d.solver as _s
    alt_rj = _s.run_jobs if hasattr(_s, "run_jobs") else None
    import statik3d.parallel as _p
    alt_p = _p.run_jobs
    alt_k = parallel.settings().ketten
    _p.run_jobs = run_jobs_stub
    try:
        parallel.configure(ketten=2)
        fehler = None
        try:
            solver._cases_in_ketten(m, namen, 2, None, None)
        except RuntimeError as ex:
            fehler = ex
        pruefe("der Ausfall einer Kette wird gemeldet", fehler is not None,
               str(fehler)[:60])
        gerettet = getattr(fehler, "teil_cases", None) if fehler else None
        pruefe("die fertige Kette hängt an der Ausnahme", bool(gerettet),
               f"{len(gerettet or {})} Lastfälle gerettet")
        pruefe("und es sind genau die der gelungenen Kette",
               gerettet is not None
               and set(gerettet) <= set(namen) and len(gerettet) < len(namen),
               f"{sorted(gerettet or {})}")
    finally:
        _p.run_jobs = alt_p
        parallel.configure(ketten=alt_k)


def test_der_kettenauftrag_traegt_referenzen_nur_wenn_es_welche_gibt():
    """Ohne Ermüdungsreferenzen bleibt der Auftrag, wie er war.

    Der neue Schlüssel `referenzen` bringt einen Arbeiter älteren Stands zu
    Fall (Rechnerfarm, danebenliegende `Statik3D.exe`): er kennt das Argument
    nicht und fällt mit TypeError aus, und zusammen mit dem Kettenabbruch
    stünde der Anwender ohne jedes Ergebnis da. In fast jedem Modell gibt es
    gar keine Referenzen - dann darf der Auftrag sich auch nicht ändern.
    """
    from statik3d import parallel
    from statik3d.examples_lib import hall_frame_example
    import statik3d.parallel as _p
    m = hall_frame_example()
    namen = list(m.load_cases)
    gesehen = {"jobs": None}

    class _Erg:
        ok, result, error = True, {}, ""

    def run_jobs_stub(jobs, workers=None, progress=None):
        gesehen["jobs"] = list(jobs)
        return [_Erg() for _ in jobs]

    alt_p = _p.run_jobs
    alt_k = parallel.settings().ketten
    _p.run_jobs = run_jobs_stub
    try:
        parallel.configure(ketten=2)
        solver._cases_in_ketten(m, namen, 2, None, None)
        ohne = gesehen["jobs"]
        pruefe("ohne Referenzen steht der Schlüssel nicht im Auftrag",
               all("referenzen" not in (j.payload or {}) for j in ohne),
               str([sorted(j.payload) for j in ohne])[:120])
        ref = {namen[1]: namen[0]} if len(namen) > 1 else {}
        solver._cases_in_ketten(m, namen, 2, None, ref)
        mit = gesehen["jobs"]
        pruefe("mit Referenzen steht er drin, wo beide Enden in der Kette liegen",
               any("referenzen" in (j.payload or {}) for j in mit),
               str([sorted(j.payload) for j in mit])[:120])
    finally:
        _p.run_jobs = alt_p
        parallel.configure(ketten=alt_k)


def test_ausfallstaebe_duerfen_nicht_ueberlagert_werden():
    """Ein Zugstab, der in einem Lastfall ausfällt, verbietet die Überlagerung.

    `_nichtlinear()` kannte bis zum 22.09.2026 nur Kontakt und Fließen -
    **nicht** Ausfallstäbe und Seile, obwohl das Modell sie seit jeher kennt
    (`Model.hat_ausfallstaebe`) und der Löser sie an zwei anderen Stellen
    abfragt. Jeder Lastfall wurde mit einer **anderen** Menge tragender Stäbe
    gerechnet; die Summe solcher Ergebnisse steht in keinem Gleichgewicht
    eines wirklichen Zustands.

    Der Prüfkörper ist ein Balken an zwei nur-Zug-Hängern: Lastfall A drückt
    nach unten (die Hänger ziehen), Lastfall B hebt an (sie fallen aus). Die
    Überlagerung mischt damit zwei unvereinbare Zustände.
    """
    import numpy as np
    from statik3d.model import Model, Material, Section

    m = Model("seilzug")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    m.add_section(Section.rectangle("Z", 0.02, 0.02))
    k = [m.add_node(x, 0.0, 0.0) for x in (0.0, 1.0, 2.0, 3.0, 4.0)]
    oben = [m.add_node(1.0, 0.0, 2.0), m.add_node(3.0, 0.0, 2.0)]
    for i in range(4):
        m.add_element("beam", [k[i], k[i + 1]], "S235", "R")
    for a, b in ((k[1], oben[0]), (k[3], oben[1])):
        e = m.add_element("truss", [a, b], "S235", "Z")
        m.elements[e].nur = "zug"
    m.fix(k[0], [0, 1, 2, 3, 4, 5])
    m.fix(k[4], [1, 2, 3])
    for o in oben:
        m.fix(o, "all")
    m.add_load_case("A", "Q")
    for kk in (k[1], k[2], k[3]):
        m.load_node(kk, Fz=-2.0e4, case="A")
    m.add_load_case("B", "Q")
    for kk in (k[1], k[2], k[3]):
        m.load_node(kk, Fz=+3.0e4, case="B")
    m.add_combination("K1", {"A": 1.0, "B": 1.0})

    pruefe("das Modell hat Ausfallstäbe", m.hat_ausfallstaebe())
    pruefe("und gilt darum als nichtlinear", solver._nichtlinear(m),
           "sonst würde überlagert")

    faelle = solver.solve_cases(m, cases=["A", "B"])
    aus_a = list(faelle["A"].info.get("ausfall") or [])
    aus_b = list(faelle["B"].info.get("ausfall") or [])
    pruefe("die beiden Lastfälle haben verschiedene Aktivmengen",
           aus_a != aus_b, f"A: {aus_a}, B: {aus_b}")

    direkt = solver.solve_combination(m, m.combinations["K1"], None)
    ueberlagert = solver.Results.combine(
        m, [(faelle["A"], 1.0), (faelle["B"], 1.0)], "K1")
    ud = float(np.abs(np.asarray(direkt.u, float)).max())
    uu = float(np.abs(np.asarray(ueberlagert.u, float)).max())
    pruefe("die Überlagerung liegt deutlich daneben - sie ist kein "
           "Gleichgewichtszustand", abs(uu - ud) > 0.2 * max(ud, 1e-30),
           f"direkt {ud*1e3:.4f} mm, überlagert {uu*1e3:.4f} mm "
           f"({abs(uu-ud)/max(ud,1e-30)*100:.1f} %)")

    # Und der Weg, den das Programm wirklich nimmt: solve_combinations darf
    # hier nicht überlagern.
    out = solver.solve_combinations(m, ["K1"], case_results=faelle)
    ur = float(np.abs(np.asarray(out["K1"].u, float)).max())
    pruefe("solve_combinations rechnet die Kombination direkt",
           abs(ur - ud) <= 1e-9 * max(ud, 1e-30),
           f"{ur*1e3:.4f} mm gegen {ud*1e3:.4f} mm direkt")


def test_probelauf_und_kennzahlen():
    """Probelauf: ein Kontaktschritt, keine Plastizitaet - und die Kennzahlen
    der Faktorisierung in Results.info.

    Beides hat die Vernetzersitzung angefordert (20.09.2026, Abschnitt 2.1 und
    2.2 ihrer Anforderungen): die adaptive Schleife rechnet je Durchgang einen
    Lastfall, braucht davon aber nur den Spannungssprung zwischen
    Nachbarelementen als Netzmass. Ein voller Lastfall am Drehlager kostet
    235 s mit 48 Kontaktschritten; der Probelauf rechnet einen.
    """
    from statik3d import plastizitaet as pl

    def aufbau():
        m = Model()
        m.add_material(Material("S", fy=235e6))
        m.add_material(Material("Starr", E=210e12))
        m.add_shell_prop(ShellProp("t", 0.05))
        pl_ = mesher.grid_plate(m, "Starr", "t", 2.0, 2.0, 2, 2, origin=(-1, -1, 0))
        for n in pl_.ravel():
            m.fix(int(n), "all")
        platte = list(range(len(m.elements)))
        box = mesher.grid_box(m, "S", 0.4, 0.4, 0.4, 2, 2, 2, origin=(-0.2, -0.2, 0.0))
        unten = [int(n) for n in box[:, :, 0].ravel()]
        oben = [int(n) for n in box[:, :, -1].ravel()]
        m.add_contact_pair("Block/Platte", unten, platte, mu=0.3)
        # Auflast weit ueber der Streckgrenze (0,4 x 0,4 m, 235 MPa waeren
        # 37,6 MN) und eine Querkraft, damit die Aktivmenge sich bewegt
        N, H = 60e6, 9e6
        for n in oben:
            m.load_node(n, Fz=-N / len(oben), Fx=H / len(oben))
        return m

    m = aufbau()
    # Verglichen wird mit der verschachtelten Iteration, in der jeder
    # Fliessschritt den Kontakt auskonvergiert - daran misst sich "ein
    # Kontaktschritt je Fliessschritt" - seit dem 24.09.2026 wieder die
    # Vorgabe. Die gemeinsame Iteration (waehlbar) kuerzt selbst ab; dass sie
    # trotzdem mit auskonvergiertem Kontakt endet, prueft
    # tests/test_plastizitaet (T3).
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2,
                                     iterationen=40, toleranz=1e-4, kontakt="verschachtelt")
    voll = solver.solve_static(m)

    m2 = aufbau()
    m2.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2,
                                      iterationen=40, toleranz=1e-4)
    probe = solver.solve_static(m2, probelauf=True)

    pruefe("Probelauf: Results.info sagt es", probe.info.get("probelauf") is True)
    pruefe("voller Lauf sagt es nicht", "probelauf" not in voll.info)
    # Der Probelauf begrenzt den **Kontakt** auf einen Schritt, nicht die
    # Plastizitaet; contact_iterations summiert ueber alle Fliessschritte
    # (_kontakt_info_sammeln). Das Mass ist darum das Verhaeltnis.
    def je_schritt(r):
        it_p = (r.info.get("plastizitaet") or {}).get("iterationen", 0)
        return r.info["contact_iterations"] / max(1, it_p)

    pruefe("Probelauf: ein Kontaktschritt je Fließschritt",
           je_schritt(probe) <= 1.5,
           f"{probe.info['contact_iterations']} Kontakt- auf "
           f"{(probe.info.get('plastizitaet') or {}).get('iterationen')} Fließschritte "
           f"= {je_schritt(probe):.2f}")
    pruefe("voller Lauf iteriert den Kontakt aus",
           je_schritt(voll) > 2.0,
           f"{voll.info['contact_iterations']} Kontakt- auf "
           f"{(voll.info.get('plastizitaet') or {}).get('iterationen')} Fließschritte "
           f"= {je_schritt(voll):.2f}")
    # Das Fliessen gehoert dazu: die erste Fassung (357d61d) liess es aus, und
    # am Drehlager traf der Probelauf damit nur 54 von 100 Spitzenelementen
    # (Loeser-Sitzung, 21.09.2026). Er verfeinerte an den falschen Stellen.
    pruefe("Probelauf: das Fliessen wird mitgerechnet",
           bool(probe.info.get("plastisch")),
           f"{len(probe.info.get('plastisch', {}))} von {len(m2.elements)} Elementen")
    pruefe("… und der Vernetzer erkennt es an den zwei Schluesseln",
           probe.info.get("probelauf") is True and "plastizitaet" in probe.info)
    pruefe("voller Lauf: Plastizitaet gerechnet und Elemente fliessen",
           bool(voll.info.get("plastisch")),
           f"{len(voll.info.get('plastisch', {}))} von {len(m.elements)} Elementen")
    # **Keine Zeitpruefung hier.** An diesem Block ist der Probelauf nicht
    # schneller (gemessen 21.09.2026: 0,57 gegen 0,35 s) - die Plastizitaet
    # braucht ihre Schritte so oder so, und der Kontakt ist bei zwoelf
    # Elementen nicht der Brocken. Die Ersparnis entsteht erst, wo die
    # Kontaktiteration dominiert: am Drehlager 199 statt 633 s
    # (Loeser-Sitzung, 21.09.2026). Eine Zeitpruefung an diesem Modell wuerde
    # etwas festhalten, das keine Eigenschaft der Aenderung ist.
    # Der Warmstart **innerhalb** des Lastfalls muss bleiben. Der Probelauf
    # verwirft den des vorigen Lastfalls (damit jede Netzrunde dieselbe Lage
    # misst); bis zum 21.09.2026 warf dieselbe Zeile auch den Zustand weg, den
    # die Plastizitaetsschleife je Fliessschritt durchreicht - jeder Schritt
    # fing den Kontakt wieder bei der Geometrie an. Am Drehlager gemessen
    # (Loeser-Sitzung): 8,97 % andere Vergleichsspannung, 2,1 % steifer
    # (0,2657 statt 0,2715 mm). Ohne die Behebung faellt diese Pruefung durch.
    mitgegeben = []
    _echt = solver.solve_with_contact

    def _fangen(model_, system_, F_, *a_, **kw_):
        mitgegeben.append(kw_.get("start"))
        return _echt(model_, system_, F_, *a_, **kw_)

    m3 = aufbau()
    m3.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2,
                                      iterationen=40, toleranz=1e-4)
    solver.solve_with_contact = _fangen
    try:
        solver.solve_static(m3, probelauf=True)
    finally:
        solver.solve_with_contact = _echt
    pruefe("Probelauf: der erste Kontaktschritt startet bei der Geometrie",
           bool(mitgegeben) and mitgegeben[0] is None,
           f"{len(mitgegeben)} Kontaktaufrufe")
    pruefe("… die weiteren Fließschritte übernehmen den Kontaktzustand",
           sum(1 for x in mitgegeben if x is not None) > 0,
           f"{sum(1 for x in mitgegeben if x is not None)} von {len(mitgegeben)} mit Warmstart")

    pruefe("Probelauf spart Kontaktschritte",
           probe.info["contact_iterations"] < voll.info["contact_iterations"],
           f"{probe.info['contact_iterations']} statt {voll.info['contact_iterations']}")
    # Verformung: derselbe erste Schritt, also dieselbe Groessenordnung -
    # der Probelauf darf kein anderes Modell rechnen
    du_p = float(np.abs(probe.u).max())
    du_v = float(np.abs(voll.u).max())
    pruefe("Probelauf verformt in derselben Groessenordnung",
           0.0 < du_p <= du_v * 1.5, f"{du_p*1e3:.3f} mm gegen {du_v*1e3:.3f} mm")

    # ------------------------------------------------ Kennzahlen (2.2)
    for name, r in (("voller Lauf", voll), ("Probelauf", probe)):
        pruefe(f"{name}: Nichtnullen der Matrix gemeldet", r.info["nnz_matrix"] > 0,
               f"{r.info['nnz_matrix']}")
        pruefe(f"{name}: Faktorisierungszeit gemeldet, kleiner als die Gesamtzeit",
               0.0 < r.info["zeit_faktorisierung"] <= r.info["time"],
               f"{r.info['zeit_faktorisierung']:.3f} s von {r.info['time']:.3f} s")
    # Die Nichtnullen der Faktoren meldet nur PARDISO (iparm(18)); mit einem
    # anderen Loeser steht 0 da, und das ist kein Fehler.
    if voll.info.get("solver") == "pardiso":
        pruefe("PARDISO: Nichtnullen der Faktorisierung, mindestens die der Matrix",
               voll.info["nnz_faktor"] >= voll.info["nnz_matrix"],
               f"{voll.info['nnz_faktor']} gegen {voll.info['nnz_matrix']}")
    else:
        pruefe("ohne PARDISO bleiben die Nichtnullen der Faktorisierung 0",
               voll.info["nnz_faktor"] == 0, voll.info.get("solver", "?"))


def test_reibkraft_gleitender_knoten_ohne_reststeifigkeit():
    """Zwei Kloetze (hex8) auf einer starren Platte in EINEM Kontaktpaar mit
    mu 0,3, wie K4 der Pruefmatrix: A mit H_A = 0,5 mu N haftet, B mit
    H_B = 1,5 mu N gleitet gegen Federn k auf seinem Deckel. Die Reibkraft an
    B ist dann mu N, die Federn tragen H_B - mu N (15 mm Schlupf).

    Bis zum 25.09.2026 trug die Reststeifigkeit der gleitenden Knoten (Phase
    2: 1e-8 k_t, "vernachlaessigbar") bei 14,5 mm Schlupf 693 kN = 2,3 % von
    mu N, die in keiner Kontaktkraft standen: die wahre Knotenkraft aus K u
    wich von contact_forces ab, die Federkraft lag 3,5 % (tet4: 10 %) unter
    H_B - mu N. Seither wirkt sie nur auf die Aenderung seit dem letzten
    Zustand (contact.AUSGLEICH_RESTSTEIFIGKEIT), und K u = contact_forces.

    Was bleibt, kommt von den **festgehaltenen Gleitrichtungen** (offen,
    gemessen 25.09.2026 an diesem Modell, Lasten und Federn konsistent
    verteilt, in y exakt symmetrisch): die Richtungen der Rand- und Eckknoten
    von B liegen 20 bis 40 Grad neben der Bewegung (Eckknoten (-0,762,
    +0,647)), die Querkraefte heben sich paarweise auf, aber die Reibkraft in
    x ist nur 28 004 statt 30 000 kN (-6,7 %), und die Federn tragen 17 000
    statt 15 000 kN. Darum prueft der Test die Reibkraft nur gegen die harte
    obere Schranke mu N und gegen 0,9 mu N, nicht auf 1 %."""
    from statik3d import assemble, contact as CT
    mu, N = 0.3, 1.0e8
    H_A, H_B, k = 0.5 * mu * N, 1.5 * mu * N, 1.0e9
    # konsistente Knotenanteile einer gleichmaessigen Flaechenlast auf dem
    # 2 x 2 Deckel (Ecke 1, Rand 2, Mitte 4 von 16) - so bleibt das Modell
    # in y exakt symmetrisch
    W = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], float) / 16.0

    def modell():
        m = Model()
        m.add_material(Material("S"))
        m.add_material(Material("Starr", E=210e12))
        m.add_shell_prop(ShellProp("t", 0.05))
        pl = mesher.grid_plate(m, "Starr", "t", 3.0, 2.0, 3, 2, origin=(-0.5, -0.5, 0))
        for n in pl.ravel():
            m.fix(int(n), "all")
        platte = list(range(len(m.elements)))
        bA = mesher.grid_box(m, "S", 1.0, 1.0, 0.25, 2, 2, 1, origin=(0.0, 0.0, 0.0))
        bB = mesher.grid_box(m, "S", 1.0, 1.0, 0.25, 2, 2, 1, origin=(1.0, 0.0, 0.0))
        unten_a = [int(n) for n in bA[:, :, 0].ravel()]
        unten_b = [int(n) for n in bB[:, :, 0].ravel()]
        oben_b = [int(n) for n in bB[:, :, -1].ravel()]
        m.add_contact_pair("Fuge", unten_a + unten_b, platte, mu=mu)
        for box, H in ((bA, H_A), (bB, H_B)):
            for i in range(3):
                for j in range(3):
                    n = int(box[i, j, -1])
                    m.load_node(n, Fz=-N * W[i, j], Fx=H * W[i, j])
                    if H == H_B:
                        m.fix(n, [0, 1], stiffness=[k * W[i, j]] * 2)
        return m, unten_a, unten_b, oben_b

    def messen(m, unten_b, oben_b, r):
        K = assemble.stiffness(m, workers=1)
        uf = np.asarray(r.u, float).reshape(-1)[:K.shape[0]]
        fint = np.asarray(K @ uf).ravel()
        wahr = np.array([fint[6 * n:6 * n + 3] for n in unten_b]).sum(axis=0)
        cf = np.asarray(r.contact_forces, float)[unten_b, :3].sum(axis=0)
        feder = float(np.asarray(r.reactions, float)[oben_b, 0].sum())
        return wahr, cf, feder

    m, unten_a, unten_b, oben_b = modell()
    r = solver.solve_static(m)
    wahr, cf, feder = messen(m, unten_b, oben_b, r)
    st = {int(c["node"]): c["status"] for c in r.contact}
    check("K4: B gleitet ganz, A nicht ganz (Phase 2 mit feiner Reststeifigkeit)",
          float(all(st[n] == "Gleiten" for n in unten_b) and any(st[n] == "Haften" for n in unten_a)), 1.0, 0)
    check("K4: Kontakt konvergiert", float(bool(r.info.get("contact_converged"))), 1.0, 0)
    check("K4: K u = contact_forces an den Gleitknoten (x)", float(wahr[0]), float(cf[0]), 1e-4)
    check("K4: K u = contact_forces an den Gleitknoten (y, Symmetrie: beide 0)",
          float(abs(wahr[1] - cf[1]) + abs(cf[1]) <= 1e-6 * mu * N), 1.0, 0)
    check("K4: Reibkraft an B hoechstens mu N", float(-cf[0] <= mu * N * (1 + 1e-6)), 1.0, 0)
    check("K4: Reibkraft an B mindestens 0,9 mu N (offene Richtungsabweichung, gemessen 0,933)",
          float(-cf[0] >= 0.9 * mu * N), 1.0, 0)
    # 1e-5: der Ausgleich laesst den Rest der letzten Runde, k_res mal der
    # letzten Aenderung der Tangentialverschiebung (gemessen 130 N = 3e-6 H_B)
    check("K4: Gleichgewicht von B, H_B = Reibung + Feder", -float(cf[0]) - feder, H_B, 1e-5)
    # Ruecknahmeprobe: ohne Ausgleich traegt die Reststeifigkeit Kraft, die
    # in keiner Kontaktkraft steht
    CT.AUSGLEICH_RESTSTEIFIGKEIT = False
    try:
        m0, _ua, ub0, ob0 = modell()
        r0 = solver.solve_static(m0)
        wahr0, cf0, _f0 = messen(m0, ub0, ob0, r0)
    finally:
        CT.AUSGLEICH_RESTSTEIFIGKEIT = True
    check("K4 ohne Ausgleich: K u weicht von contact_forces um mehr als 1 % von mu N ab",
          float(abs(wahr0[0] - cf0[0]) > 0.01 * mu * N), 1.0, 0)


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
    test_reibkraft_gleitender_knoten_ohne_reststeifigkeit()
    test_parallel_assembly()
    test_stehender_pool()
    test_ketten_rechnen_dasselbe()
    test_ketten_teilen_und_zaehlen()
    test_ketten_greifen_nicht_wo_sie_nicht_duerfen()
    test_ketten_mit_eingefrorenen_zustaenden()
    test_ketten_zerreissen_die_situationen_nicht()
    test_kettenabbruch_behaelt_die_fertigen_ketten()
    test_der_kettenauftrag_traegt_referenzen_nur_wenn_es_welche_gibt()
    test_ausfallstaebe_duerfen_nicht_ueberlagert_werden()
    test_probelauf_und_kennzahlen()
    test_farm()
    nok = sum(1 for r in RESULTS if r[4])
    print("=" * 96)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
