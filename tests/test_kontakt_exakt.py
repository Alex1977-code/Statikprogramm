"""Exakte Normalbedingung mit Multiplikator (contact.EXAKTE_NORMALBEDINGUNG,
26.09.2026): der primal-duale semiglatte Newton fuer den Normalkontakt.

Was hier belegt wird - jede Behauptung mit einer Zahl:

1. Geschlossene Bedingungen haben den Spalt **null** (nicht 1e-4 der
   Verschiebung wie die Feder), ihre Kraft ist der Multiplikator lambda >= 0,
   und die Summe der Multiplikatoren ist die Auflast (Gleichgewicht).
2. Ein kippender Block, dessen Fuge zur Haelfte aufgeht: die Aktivmenge
   konvergiert ohne eine festgehaltene Bedingung; keine geschlossene traegt
   Zug, keine offene durchdringt. Ruecknahmeprobe: mit der Feder liegen die
   geschlossenen Knoten in der Unterlage (Durchdringung Fn/k_n).
3. Presspassung (Pruefmatrix K3): das Uebermass wird exakt geschlossen,
   sigma = delta E / (2 L) in jedem Element auf 1e-6 N/mm2.
4. Eine Fuge mit Feder des Anwenders (stiffness > 0) bleibt eine Feder:
   Durchdringung = Fn / k.
5. Einseitige Lager und Spaltelemente laufen ebenfalls exakt.

Aufruf:  python -m tests.test_kontakt_exakt
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import contact, mesher, solver                  # noqa: E402
from statik3d.examples_lib import block_friction_example      # noqa: E402
from statik3d.model import Material, Model, ShellProp         # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:74s} {detail}")
    return ok


def _block_auf_platte(kipp: float = 0.0, mu: float = 0.3, stiffness: float = 0.0) -> Model:
    """Stahlblock 0,4 m auf starrer Platte (wie examples_lib.block_friction_example),
    Auflast 90 kN; ``kipp`` legt die Auflast linear ueber x schief (1,5: die
    Fuge oeffnet auf der Seite x < 0), ohne Horizontalkraft."""
    m = Model("Block auf Platte")
    m.add_material(Material.steel("S235"))
    m.add_material(Material("Starr", E=210e12))
    m.add_shell_prop(ShellProp("t = 50 mm", 0.05))
    pl = mesher.grid_plate(m, "Starr", "t = 50 mm", 1.0, 1.0, 2, 2, origin=(-0.5, -0.5, 0))
    for n in pl.ravel():
        m.fix(int(n), "all")
    plate = list(range(len(m.elements)))
    box = mesher.grid_box(m, "S235", 0.4, 0.4, 0.4, 4, 4, 4, origin=(-0.2, -0.2, 0.0))
    bottom = [int(n) for n in box[:, :, 0].ravel()]
    top = [int(n) for n in box[:, :, -1].ravel()]
    m.add_contact_pair("Block/Platte", bottom, plate, mu=mu, stiffness=stiffness)
    X = np.asarray(m.nodes, float)
    for n in top:
        m.load_node(n, Fz=-90000.0 / len(top) * (1.0 + kipp * X[n, 0] / 0.2))
    return m


def _fuge(res, name="Block/Platte"):
    return [c for c in (res.contact or []) if str(c.get("label", "")).startswith(name)]


def test_spalt_null_und_gleichgewicht():
    print("\n--- Geschlossene Bedingung: Spalt null, Kraft = Multiplikator, Summe = Last ---")
    m = block_friction_example()
    res = solver.solve_static(m)
    zu = [c for c in _fuge(res) if c["status"] != "offen"]
    offen = [c for c in _fuge(res) if c["status"] == "offen"]
    # 20 zu, 5 offen: die Horizontalkraft am Deckel kippt den Block, die
    # hintere Reihe hebt ab - dieselbe Aktivmenge wie mit der Feder (gemessen
    # 26.09.2026: beide 20/5, 21 Schritte, 7 Faktorisierungen)
    check("konvergiert, 20 Bedingungen geschlossen, 5 offen (Block kippt unter der Horizontalkraft)",
          res.info.get("contact_converged") and len(zu) == 20 and len(offen) == 5,
          f"{len(zu)} zu, {len(offen)} offen, {res.info.get('contact_iterations')} Schritte")
    g_max = max(abs(float(c["gap"])) for c in zu)
    check("Spalt geschlossener Bedingungen ist null (|g| < 1e-15 m)", g_max < 1e-15, f"max |g| = {g_max:.1e} m")
    fn_min = min(float(c["Fn"]) for c in zu)
    check("jeder Multiplikator ist Druck (Fn >= 0)", fn_min >= 0.0, f"min Fn = {fn_min:.3f} N")
    summe = sum(float(c["Fn"]) for c in zu)
    check("Summe der Multiplikatoren = Auflast 90 kN (1e-9)", abs(summe - 90000.0) < 1e-9 * 90000.0, f"{summe:.6f} N")
    R = float(res.reactions[:, 2].sum())
    check("Auflagerkraft der Platte = 90 kN (Reaktionen kennen die Kontaktkraft)", abs(R - 90000.0) < 1e-6 * 90000.0,
          f"{R:.6f} N")
    check("keine festgehaltene Bedingung, keine Zeile 'oszilliert'",
          not any(c.get("frozen") for c in _fuge(res)) and not any("oszilliert" in z for z in res.info.get("contact_log", [])))


def test_kippender_block():
    print("\n--- Kippender Block: die Fuge oeffnet, die Aktivmenge konvergiert ohne Festhalten ---")
    m = _block_auf_platte(kipp=1.5)
    res = solver.solve_static(m)
    zu = [c for c in _fuge(res) if c["status"] != "offen"]
    offen = [c for c in _fuge(res) if c["status"] == "offen"]
    check("konvergiert, Fuge teils offen", res.info.get("contact_converged") and 3 <= len(offen) <= 20 and len(zu) >= 5,
          f"{len(zu)} zu, {len(offen)} offen, {res.info.get('contact_iterations')} Schritte")
    g_zu = max((abs(float(c["gap"])) for c in zu), default=0.0)
    g_offen = min((float(c["gap"]) for c in offen), default=0.0)
    check("geschlossene: Spalt null (|g| < 1e-15 m); offene: kein Durchdringen (g >= 0)",
          g_zu < 1e-15 and g_offen >= -1e-15, f"zu max |g| {g_zu:.1e}, offen min g {g_offen:.2e} m")
    fn_min = min(float(c["Fn"]) for c in zu)
    check("keine geschlossene Bedingung unter Zug (min Fn >= 0)", fn_min >= 0.0, f"min Fn = {fn_min:.3f} N")
    check("nichts festgehalten", not any(c.get("frozen") for c in _fuge(res))
          and not any("oszilliert" in z for z in res.info.get("contact_log", [])))
    X = np.asarray(m.nodes, float)
    x_offen = [X[int(c["node"]), 0] for c in offen]
    x_zu = [X[int(c["node"]), 0] for c in zu]
    check("die Fuge oeffnet auf der entlasteten Seite (x < 0), die belastete bleibt zu",
          max(x_offen) < min(x_zu) + 1e-9, f"offen bis x = {max(x_offen):.2f}, zu ab x = {min(x_zu):.2f}")
    summe = sum(float(c["Fn"]) for c in zu)
    check("Summe der Multiplikatoren = Auflast 90 kN", abs(summe - 90000.0) < 1e-9 * 90000.0, f"{summe:.6f} N")
    # Ruecknahmeprobe: die Feder
    alt = contact.EXAKTE_NORMALBEDINGUNG
    contact.EXAKTE_NORMALBEDINGUNG = False
    try:
        res_f = solver.solve_static(_block_auf_platte(kipp=1.5))
    finally:
        contact.EXAKTE_NORMALBEDINGUNG = alt
    zu_f = [c for c in _fuge(res_f) if c["status"] != "offen"]
    g_f = max(-float(c["gap"]) for c in zu_f)
    check("Ruecknahme (Feder): geschlossene Knoten durchdringen die Platte (max -g > 1e-13 m)",
          res_f.info.get("contact_converged") and g_f > 1e-13, f"max Durchdringung {g_f:.2e} m")
    # Seit der Reibung primal-dual (28.09.2026) rechnet der exakte Weg auch
    # die Reibung anders als der Feder-Weg (Haftzeilen, Richtung aus der
    # Versuchskraft): fuer den Vergleich der **Normalbedingung** laeuft der
    # exakte Weg hier noch einmal mit der Reibung der Feder (gemessen: mit
    # beiden Neuerungen 9,2e-3 auseinander, davon 9,1e-3 die Reibung)
    alt_pd = contact.REIBUNG_PRIMAL_DUAL
    contact.REIBUNG_PRIMAL_DUAL = False
    try:
        res_e = solver.solve_static(_block_auf_platte(kipp=1.5))
    finally:
        contact.REIBUNG_PRIMAL_DUAL = alt_pd
    du = float(np.abs(res_e.u[:, :3] - res_f.u[:, :3]).max()) / float(np.abs(res_e.u[:, :3]).max())
    check("beide Wege liefern dieselbe Verformung bis auf die Federdurchdringung (< 1e-3)", du < 1e-3, f"{du:.1e}")


def test_presspassung_exakt():
    print("\n--- Presspassung K3: Uebermass exakt geschlossen ---")
    from tests import pruefmatrix as pm
    fall = pm.UebermassFuge()
    for typ in ("hex8", "tet4"):
        m, meta = fall.modell(typ, 0.5)
        res = solver.solve_static(m)
        s = fall.sigma_soll() / 1e6
        fehler = pm.elementfehler(res, fall.sigma_soll())
        check(f"{typ}: sigma_v = {s:.0f} N/mm2 in jedem Element (1e-6 N/mm2)", res.info.get("contact_converged")
              and abs(fehler) < 1e-6, f"groesster Fehler {fehler:.2e} N/mm2")
        zu = [c for c in (res.contact or []) if c["status"] != "offen"]
        g = max(abs(float(c["gap"])) for c in zu)
        check(f"{typ}: Spalt nach dem Schliessen des Uebermasses null (|g| < 1e-15 m)", g < 1e-15, f"{g:.1e} m")
        R = float(res.reactions[meta["unten"], 2].sum())
        check(f"{typ}: Auflagerkraft = sigma A (1e-9)", abs(R / fall.sigma_soll() - 1.0) < 1e-9, f"{R / fall.sigma_soll():.12f}")


def test_feder_bleibt_feder():
    print("\n--- Feder des Anwenders (stiffness > 0) bleibt Penalty ---")
    k = 1.0e9
    m = _block_auf_platte(kipp=0.0, stiffness=k)
    res = solver.solve_static(m)
    zu = [c for c in _fuge(res) if c["status"] != "offen"]
    abw = max(abs(-float(c["gap"]) * k - float(c["Fn"])) / max(float(c["Fn"]), 1.0) for c in zu)
    check("Durchdringung = Fn / k an jeder geschlossenen Bedingung (1e-9)", res.info.get("contact_converged") and abw < 1e-9,
          f"groesste Abweichung {abw:.1e}, k = {k:.0e} N/m")
    g = max(-float(c["gap"]) for c in zu)
    check("und sie ist messbar (max -g > 1e-6 m bei 90 kN auf 25 Federn)", g > 1e-6, f"{g:.2e} m")


def test_lager_und_spaltelement():
    print("\n--- Einseitiges Lager und Spaltelement exakt ---")
    from statik3d.model import Section
    m = Model("Balken auf einseitigem Lager")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 200"))
    n = [m.add_node(x, 0.0, 0.0) for x in (0.0, 1.0, 2.0)]
    for i in range(2):
        m.add_element("beam", [n[i], n[i + 1]], "S235", sec="IPE 200")
    m.fix(n[0], "all")
    m.add_contact_support(n[2], direction=[0, 0, 1])          # nur Druck
    m.load_node(n[1], Fz=-10000.0)
    res = solver.solve_static(m)
    c = res.contact[0]
    check("Kragarm auf einseitigem Lager: Lager traegt, Spalt null, Kraft = Multiplikator",
          res.info.get("contact_converged") and c["status"] != "offen" and abs(float(c["gap"])) < 1e-15 and float(c["Fn"]) > 0,
          f"g {float(c['gap']):.1e} m, Fn {float(c['Fn']):.3f} N")
    # Zug: das Lager oeffnet - kein Restzug
    m2 = Model("Balken, Lager unter Zug")
    m2.add_material(Material.steel("S235"))
    m2.add_section(Section.from_profile("IPE 200"))
    n2 = [m2.add_node(x, 0.0, 0.0) for x in (0.0, 1.0, 2.0)]
    for i in range(2):
        m2.add_element("beam", [n2[i], n2[i + 1]], "S235", sec="IPE 200")
    m2.fix(n2[0], "all")
    m2.add_contact_support(n2[2], direction=[0, 0, 1])
    m2.load_node(n2[2], Fz=+10000.0)
    res2 = solver.solve_static(m2)
    c2 = res2.contact[0]
    check("unter Zug oeffnet das Lager (Status offen, Fn 0, Spalt > 0)",
          res2.info.get("contact_converged") and c2["status"] == "offen" and float(c2["Fn"]) == 0.0 and float(c2["gap"]) > 0,
          f"{c2['status']}, g {float(c2['gap']):.3e} m")


def test_haftfuge_bindung_bleibt():
    """Haftfuge (in der Ebene starr, normal Ausfall bei Zug): die Schubbindung
    steht auch dort, wo die Normalbedingung offen ist (Constraint.bindung,
    26.09.2026). Am Drehlager pendelte die Aktivmenge sonst: an den
    pendelnden Knoten trug die Bindung das 19-Fache der Normalkraft, und ihr
    Schalten mit dem Normalzustand warf den Knoten in die Fuge zurueck."""
    print("\n--- Haftfuge: die Schubbindung bleibt bei offener Normalbedingung ---")
    # H = 5 kN am Deckel (z = 0,4 m): Moment 2 kNm, die Resultierende der 90 kN
    # wandert von x = 0,15 auf 0,172 m - noch innerhalb der Fuge (0,2 m).
    # Mit 20 kN laege sie bei 0,239 m: der Block kippt wirklich, "hebt ab"
    # ist dann die richtige Antwort (so gemessen am 26.09.2026)
    H = 5000.0
    m = _block_auf_platte(kipp=1.5, mu=0.0)
    cp = m.contact_pairs[0]
    cp.haften = True
    top = [int(l.node) for l in m.case().nodal_loads]
    for n in top:
        m.case().nodal_loads[[int(l.node) for l in m.case().nodal_loads].index(n)].F[0] += H / len(top)
    res = solver.solve_static(m)
    fuge = _fuge(res)
    zu = [c for c in fuge if c["status"] != "offen"]
    offen = [c for c in fuge if c["status"] == "offen"]
    check("konvergiert, Fuge teils offen, nichts festgehalten",
          res.info.get("contact_converged") and 3 <= len(offen) <= 20 and not any(c.get("frozen") for c in fuge),
          f"{len(zu)} zu, {len(offen)} offen, {res.info.get('contact_iterations')} Schritte")
    geb = [c for c in offen if c.get("gebunden")]
    check("jede offene Bedingung ist gebunden und traegt Schub (Ft > 0)",
          len(geb) == len(offen) and all(float(c["Ft"]) > 0.0 for c in geb),
          f"{len(geb)} gebunden, Ft {min((float(c['Ft']) for c in geb), default=0):.1f}..{max((float(c['Ft']) for c in geb), default=0):.1f} N")
    fn_min = min(float(c["Fn"]) for c in zu)
    check("geschlossene: Fn >= 0 und Spalt null", fn_min >= 0.0 and max(abs(float(c["gap"])) for c in zu) < 1e-15,
          f"min Fn {fn_min:.3f} N")
    Fx = sum(float(c["F_vek"][0]) for c in fuge)
    Fz = sum(float(c["F_vek"][2]) for c in fuge)
    check("Gleichgewicht: Summe der Kontaktkraefte x = -H, z = +90 kN (1e-9)",
          abs(Fx + H) < 1e-9 * H and abs(Fz - 90000.0) < 1e-9 * 90000.0, f"Fx {Fx:.6f} N, Fz {Fz:.6f} N")
    Fx_offen = sum(float(c["F_vek"][0]) for c in geb)
    check("davon tragen die offenen, gebundenen Knoten einen Teil des Schubs (|Fx| > 0)",
          abs(Fx_offen) > 0.0, f"{Fx_offen:.3f} N von {-H:.0f} N")
    R = res.reactions[:, :3].sum(axis=0)
    check("Auflagerreaktionen der Platte: Rx = -H, Rz = +90 kN", abs(R[0] + H) < 1e-6 * H and abs(R[2] - 90000.0) < 1e-6 * 90000.0,
          f"{R}")
    # Ruecknahmeprobe: ohne Bindung traegt ein offener Knoten keinen Schub
    m2 = _block_auf_platte(kipp=1.5, mu=0.0)
    cp2 = m2.contact_pairs[0]
    cp2.haften = True
    for l in m2.case().nodal_loads:
        l.F[0] += H / len(top)
    alt = contact.ContactSystem._bedingung

    def ohne_bindung(self, *a, **kw):
        alt(self, *a, **kw)
        self.cons[-1].bindung = False
    contact.ContactSystem._bedingung = ohne_bindung
    try:
        res2 = solver.solve_static(m2)
    finally:
        contact.ContactSystem._bedingung = alt
    offen2 = [c for c in _fuge(res2) if c["status"] == "offen"]
    check("Ruecknahme: ohne Bindung traegt ein offener Knoten keinen Schub (Ft = 0, nicht gebunden)",
          offen2 and all(float(c["Ft"]) == 0.0 and not c.get("gebunden") for c in offen2),
          f"{len(offen2)} offen, {res2.info.get('contact_iterations')} Schritte, konvergiert {res2.info.get('contact_converged')}")


def _coulomb(m):
    """Rechnen und am Endzustand das Reibgesetz pruefen: je gleitendem Knoten
    der Winkel zwischen Reibkraft (Ft-Konvention, parallel zum Weg) und
    Tangentialweg d_t = C_t u, je haftendem |Ft| / (mu Fn)."""
    import math
    letzte = {}
    alt = contact.ContactSystem.results

    def gemerkt(self):
        letzte["cs"] = self
        return alt(self)
    contact.ContactSystem.results = gemerkt
    try:
        res = solver.solve_static(m)
    finally:
        contact.ContactSystem.results = alt
    u = np.asarray(res.u, float).ravel()
    winkel, kegel = [], []
    for c in letzte["cs"].cons:
        if not (c.active and c.ct is not None and c.mu > 0 and not c.haften):
            continue
        dt = np.array([c.ct[0] @ u[c.dofs], c.ct[1] @ u[c.dofs]])
        if c.slip and np.linalg.norm(dt) > 0 and np.linalg.norm(c.Ft) > 0:
            cw = float(dt @ c.Ft) / (np.linalg.norm(dt) * np.linalg.norm(c.Ft))
            winkel.append(math.degrees(math.acos(max(-1.0, min(1.0, cw)))))
        elif not c.slip:
            kegel.append(float(np.linalg.norm(c.Ft)) / max(c.mu * max(c.Fn, 0.0), 1e-300))
    return res, (max(winkel) if winkel else 0.0), (max(kegel) if kegel else 0.0), len(winkel)


def test_reibung_primal_dual():
    """Reibung primal-dual (contact.REIBUNG_PRIMAL_DUAL, 28.09.2026): am
    Endzustand liegt die Reibkraft jedes gleitenden Knotens parallel zu seinem
    Weg, und kein haftender liegt ausserhalb des Kegels. Mit festgehaltenen
    Gleitrichtungen (bis dahin) stand sie am Stempel auf gewoelbter Unterseite
    bis 180 Grad gegen den Weg (Median 47), am Block mit Reibung bis 52 Grad."""
    print("\n--- Reibung primal-dual: Coulomb am Endzustand ---")
    from statik3d.examples_lib import block_friction_example
    from tests.test_plastizitaet import _drehlagerartiges_modell

    def stempel():
        m = _drehlagerartiges_modell()
        m.plastizitaet.an = False
        return m
    for name, bau in (("Stempel auf Sockel", stempel), ("Block mit Reibung", block_friction_example)):
        res, w, k, n = _coulomb(bau())
        check(f"{name}: Reibkraft parallel zum Gleitweg (max Winkel < 1 Grad), Haften im Kegel",
              res.info.get("contact_converged") and n > 0 and w < 1.0 and k <= 1.0 + 1e-6,
              f"{n} gleitend, max {w:.2f} Grad, haftend |Ft|/muFn max {k:.4f}")
    alt = contact.REIBUNG_PRIMAL_DUAL
    contact.REIBUNG_PRIMAL_DUAL = False
    try:
        _res, w, _k, n = _coulomb(stempel())
    finally:
        contact.REIBUNG_PRIMAL_DUAL = alt
    check("Ruecknahme (festgehaltene Richtungen): am Stempel Reibkraft bis weit gegen den Weg (> 10 Grad)",
          w > 10.0, f"{n} gleitend, max {w:.1f} Grad")


def test_reibung_mit_symmetrischem_loeser():
    """Die Kopplungsspalte der Reibung (contact._gekoppelt) macht das System
    unsymmetrisch; mit dem Gleichungsloeser ama (LDL^T, nur symmetrisch)
    rechnet der Kontakt ohne sie - Ergebnis wie mit PARDISO (gemessen
    28.09.2026: 8,3e-6 relativ, 30 statt 29 Runden)."""
    print("\n--- Reibung mit ama: ohne Kopplungsspalte, dasselbe Ergebnis ---")
    from statik3d import parallel
    from statik3d.examples_lib import block_friction_example
    try:
        import ama  # noqa: F401
    except ImportError:
        print("     uebersprungen (ama nicht installiert)")
        return
    ref = solver.solve_static(block_friction_example())
    st = parallel.settings()
    alt = st.solver_backend
    st.solver_backend = "ama"
    gesehen = {}
    alt_sm = contact.ContactSystem.system_matrizen

    def sm(self, ndof):
        erg = alt_sm(self, ndof)
        gesehen["nur_sym"] = bool(getattr(self, "nur_symmetrisch", False))
        gesehen["D"] = gesehen.get("D", False) or getattr(self, "D_kopplung", None) is not None
        return erg
    contact.ContactSystem.system_matrizen = sm
    try:
        res = solver.solve_static(block_friction_example())
    finally:
        st.solver_backend = alt
        contact.ContactSystem.system_matrizen = alt_sm
    du = float(np.abs(np.asarray(res.u) - np.asarray(ref.u)).max()) / float(np.abs(np.asarray(ref.u)).max())
    check("ama: nur_symmetrisch gesetzt, keine Kopplungsspalte, konvergiert, u wie PARDISO auf 1e-4",
          gesehen.get("nur_sym") and not gesehen.get("D") and res.info.get("contact_converged") and du < 1e-4,
          f"nur_symmetrisch {gesehen.get('nur_sym')}, Spalte {gesehen.get('D')}, du {du:.1e}")


def test_mortar_ungleiche_netze():
    """Mortar-Gewichte (contact.MORTAR, statik3d/mortar.py, 28.09.2026): bei
    deckungsgleichen Netzen Knoten auf Knoten (Gewicht 1), bei ungleichen
    kommt ein gleichmaessiger Druck gleichmaessig an. Pruefmatrix K6 (oben
    3 x 3, unten 2 x 2, p = 100 N/mm2): vorher sigma_v +74,16 N/mm2 mit hex8,
    -13,56 mit tet4, an den unteren Knoten 846 / 661 statt 625 cm2."""
    print("\n--- Mortar: ungleiche Netze geben den Druck weiter ---")
    from statik3d import mortar as mo
    from tests import pruefmatrix as pm

    def gitter(n, z, versatz=0):
        xs = np.linspace(0, 1, n + 1)
        K = [[xs[i], xs[j], z] for j in range(n + 1) for i in range(n + 1)]
        F = [(versatz + j * (n + 1) + i, versatz + j * (n + 1) + i + 1,
              versatz + (j + 1) * (n + 1) + i + 1, versatz + (j + 1) * (n + 1) + i)
             for j in range(n) for i in range(n)]
        return np.array(K, float), F
    Ks, Fs = gitter(3, 1.0)
    Km, Fm = gitter(3, 1.0, versatz=len(Ks))
    w = mo.gewichte(np.vstack([Ks, Km]), Fs, Fm, 0.1)
    fehl = max(abs(v - (D if i == j + len(Ks) else 0.0)) / D for j, (D, Mj) in w.items() for i, v in Mj.items())
    check("deckungsgleiche Netze: Gewicht 1 auf dem gegenueberliegenden Knoten (auf 1e-12)",
          fehl < 1e-12, f"{fehl:.1e}")
    Km, Fm = gitter(2, 1.0, versatz=len(Ks))
    w = mo.gewichte(np.vstack([Ks, Km]), Fs, Fm, 0.1)
    last = {}
    for j, (D, Mj) in w.items():
        for i, v in Mj.items():
            last[i] = last.get(i, 0.0) + v
    soll = {0: 0.0625, 1: 0.125, 2: 0.0625, 3: 0.125, 4: 0.25, 5: 0.125, 6: 0.0625, 7: 0.125, 8: 0.0625}
    abw = max(abs(last[i + len(Ks)] - a) for i, a in soll.items())
    check("3 x 3 gegen 2 x 2: an den Master-Knoten genau ihre Einflussflaechen (625 / 1250 / 2500 cm2)",
          abw < 1e-12, f"max Abweichung {abw:.1e} m2")
    fall = pm.UngleicheNetze()
    for typ in ("hex8", "tet4"):
        m, meta = fall.bauen("hex" if typ == "hex8" else "tet", typ, 1, 0.5, [])
        res = solver.solve_static(m, workers=1)
        met = fall.auswerten(m, res, meta)[0]
        sv = max(abs(float(x["wert"])) for x in met if "σ_v" in x["name"])
        check(f"K6 {typ}: sigma_v auf 1 N/mm2 homogen (vorher +74,16 hex8 / -13,56 tet4)",
              res.info.get("contact_converged") and sv < 1.0, f"max |d sigma_v| {sv:.4f} N/mm2")
    alt = contact.MORTAR
    contact.MORTAR = False
    try:
        m, meta = fall.bauen("hex", "hex8", 1, 0.5, [])
        res = solver.solve_static(m, workers=1)
        met = fall.auswerten(m, res, meta)[0]
        sv = max(abs(float(x["wert"])) for x in met if "σ_v" in x["name"])
    finally:
        contact.MORTAR = alt
    check("Ruecknahme (Knoten gegen Flaeche): K6 hex8 wieder weit daneben (> 10 N/mm2)", sv > 10.0,
          f"{sv:.2f} N/mm2")


def main() -> int:
    for t in (test_spalt_null_und_gleichgewicht, test_kippender_block, test_presspassung_exakt,
              test_feder_bleibt_feder, test_lager_und_spaltelement, test_haftfuge_bindung_bleibt,
              test_reibung_primal_dual, test_reibung_mit_symmetrischem_loeser,
              test_mortar_ungleiche_netze):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
