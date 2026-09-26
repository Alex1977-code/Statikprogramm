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
    du = float(np.abs(res.u[:, :3] - res_f.u[:, :3]).max()) / float(np.abs(res.u[:, :3]).max())
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


def main() -> int:
    for t in (test_spalt_null_und_gleichgewicht, test_kippender_block, test_presspassung_exakt,
              test_feder_bleibt_feder, test_lager_und_spaltelement, test_haftfuge_bindung_bleibt):
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
