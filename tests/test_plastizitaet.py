"""Plastizitaet (17.09.2026): von Mises mit linearer Verfestigung als
Anfangsdehnungs-Iteration - gegen die geschlossene Loesung des einachsigen
Zugversuchs (ein Hexaeder) und die Rueckfuehrung im Schub.

Aufruf:  python -m tests.test_plastizitaet
"""
import math
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import plastizitaet as pl, solver                  # noqa: E402
from statik3d.examples_lib import block_friction_example          # noqa: E402
from statik3d.model import Material, Model, NodalLoad             # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.6g} soll {soll:.6g} ({abw * 100:.3f} %) {einheit}")


E, NU, FY = 210e9, 0.3, 355e6


def _wuerfel_zug(p: float):
    """Ein Hexaeder 1 x 1 x 1 m, unten in z gehalten, oben mit der Spannung p
    (vier gleiche Knotenlasten = gleichfoermiger Zug)."""
    m = Model("Zug")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    n = [m.add_node(x, y, z) for z in (0.0, 1.0) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    m.add_element("hex8", n, "S355", "")
    for i in n[:4]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    for i in n[4:]:
        lc.nodal_loads.append(NodalLoad(i, [0, 0, p / 4.0, 0, 0, 0]))
    return m, n


def test_rueckfuehrung():
    G = E / (2 * (1 + NU))
    H = 0.0
    sig, d, dg = pl.rueckfuehrung([FY * 0.9, 0, 0, 0, 0, 0], FY, H, G)
    check("unter der Streckgrenze: elastisch, keine plastische Dehnung", dg == 0.0 and np.allclose(sig, [FY * 0.9, 0, 0, 0, 0, 0]))
    sig, d, dg = pl.rueckfuehrung([1.2 * FY, 0, 0, 0, 0, 0], FY, H, G)
    nahe("einachsig ueber fy, ideal-plastisch: die Spannung faellt auf fy", pl.vergleichsspannung(sig), FY, 1e-9, "Pa")
    nahe("… Δγ = (σ − fy)/(3G), plastische Dehnung xx = Δγ, quer −Δγ/2", d[0], dg, 1e-12)
    nahe("… Volumentreue: Spur der plastischen Dehnung null", d[0] + d[1] + d[2], 0.0, 1e-9)
    tau = FY / math.sqrt(3) * 1.3
    sig, d, dg = pl.rueckfuehrung([0, 0, 0, tau, 0, 0], FY, H, G)
    nahe("reiner Schub ueber fy/√3: zurueck auf fy/√3", sig[3], FY / math.sqrt(3), 1e-9, "Pa")
    nahe("… die Gleitung ist doppelt so gross wie die Tensorkomponente (Ingenieurgleitung)", d[3], 2 * dg * 1.5 * tau / (math.sqrt(3) * tau), 1e-9)
    einst = pl.Plastizitaet(verfestigung=0.01)
    nahe("Verfestigung E_t/E = 1 %: H = E r/(1 − r)", einst.H(E), E * 0.01 / 0.99, 1e-12, "Pa")


def test_zugversuch():
    einst = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2, iterationen=60, toleranz=1e-8)
    H = einst.H(E)
    for p in (0.8 * FY, 1.1 * FY):
        m, n = _wuerfel_zug(p)
        system = solver.StaticSystem(m)
        F = solver.case_loads(m, {"LF1": 1.0})[0]
        log = []
        u, zustand, F_p, info = pl.iteration(m, F, lambda Fg: system.solve(Fg), einst, log=log)
        uz = float(u.reshape(-1, 6)[n[4:], 2].mean())
        eps_p = max(0.0, (p - FY) / H)
        soll = 1.0 * (p / E + eps_p)
        art = "elastisch" if p < FY else "plastisch"
        nahe(f"Zugversuch {art} ({p / 1e6:.0f} MPa): Dehnung oben = σ/E + (σ − fy)/H", uz, soll, 1e-6, "m")
        check(f"Zugversuch {art}: {'kein' if p < FY else 'ein'} Element fließt, konvergiert",
              info["konvergiert"] and (info["fliessend"] == (0 if p < FY else 1)), str(info["fliessend"]))
        if p > FY:
            nahe("… plastische Vergleichsdehnung = (σ − fy)/H", info["eps_p_max"], eps_p, 1e-6)
            s0 = pl.sigma0_je_element(m, zustand)
            from statik3d import assemble as asm
            from statik3d.elements import solid as sl
            e = m.elements[0]
            ue = u[asm.element_dofs(e, m)]
            sig_el = np.asarray(sl.stress_points("hex8", m.nodes[e.nodes], E, NU, ue, punkte=[sl.AUSWERTEPUNKTE["hex8"][0]])[0], float)
            sig = sig_el - s0[0]
            nahe("… Spannung im Nachlauf σ = D ε − D eps_p: σ_zz = p", sig[2], p, 1e-6, "Pa")
            nahe("… und quer spannungsfrei", abs(sig[0]) + abs(sig[1]), 0.0, 1e-6 * p)
            check("… die plastischen Knotenlasten sind nicht null", float(np.abs(F_p).max()) > 0)


def test_loeser():
    """Ueber solver.solve_static: die Einstellung am Modell schaltet das
    Fliessen ein, der Spannungsnachlauf zieht D eps_p ab, die Zusammenfassung
    nennt es, das Gleichgewicht stimmt (Auflager = Last, nicht Last + F_p)."""
    einst = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2, iterationen=60, toleranz=1e-8)
    p = 1.1 * FY
    m, n = _wuerfel_zug(p)
    r0 = solver.solve_static(m)
    m.plastizitaet = einst
    r = solver.solve_static(m)
    eps_p = (p - FY) / einst.H(E)
    uz0 = float(r0.u[n[4:], 2].mean())
    uz = float(r.u[n[4:], 2].mean())
    nahe("ohne Einstellung elastisch: Dehnung σ/E", uz0, p / E, 1e-6, "m")
    nahe("mit Plastizität am Modell: Dehnung σ/E + (σ − fy)/H", uz, p / E + eps_p, 1e-6, "m")
    info = r.info.get("plastizitaet") or {}
    check("res.info['plastizitaet']: 1 Element fließt, konvergiert, 2 Laststufen",
          info.get("fliessend") == 1 and info.get("konvergiert") and info.get("laststufen") == 2, str(info)[:120])
    nahe("… ε_p,eq max = (σ − fy)/H", info.get("eps_p_max", 0.0), eps_p, 1e-6)
    check("res.info['plastisch']: Element 0 mit seiner plastischen Vergleichsdehnung",
          list(r.info.get("plastisch", {}).keys()) == [0] and abs(r.info["plastisch"][0] - eps_p) < 1e-6 * eps_p)
    sig = np.asarray(r.solid_res[0], float)
    nahe("Spannungsnachlauf: σ_zz = p (D ε − D eps_p), nicht E ε", sig[2], p, 1e-6, "Pa")
    nahe("… quer spannungsfrei", abs(sig[0]) + abs(sig[1]), 0.0, 1e-6 * p)
    nahe("Gleichgewicht: die Auflager tragen p, nicht p + F_p", float(r.reactions[n[:4], 2].sum()), -p, 1e-6, "N")
    z = r.summary()
    check("Zusammenfassung nennt die Plastizität", "Plastizität" in z and "1 Elemente fließen" in z and "2 Laststufen" in z,
          [x for x in z.splitlines() if "Plastizit" in x][:1])
    check("das Protokoll steht in res.info['plastizitaet']['log']", any("fließen" in x for x in info.get("log", [])))
    # Einstellung ohne Streckgrenze: elastisch, mit Hinweis
    m2, n2 = _wuerfel_zug(p)
    m2.materials["S355"].fy = None
    m2.plastizitaet = einst
    r2 = solver.solve_static(m2)
    nahe("Werkstoff ohne fy: bleibt elastisch", float(r2.u[n2[4:], 2].mean()), p / E, 1e-6, "m")
    check("… und das Protokoll nennt den Werkstoff", any("ohne Streckgrenze" in x and "S355" in x
                                                          for x in (r2.info.get("plastizitaet") or {}).get("log", [])))


def test_kombination():
    """Zwei Lastfaelle zu je 0,6 fy, die Kombination 1,0 + 1,0 = 1,2 fy: mit
    Fliessen wird sie direkt gerechnet (Dehnung σ/E + (σ − fy)/H), nicht aus
    den elastischen Lastfaellen ueberlagert (2 x 0,6 fy/E)."""
    einst = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2, iterationen=60, toleranz=1e-8)
    p = 0.6 * FY
    m, n = _wuerfel_zug(p)
    lc2 = m.add_load_case("LF2")
    lc2.gravity = [0, 0, 0]
    for i in n[4:]:
        lc2.nodal_loads.append(NodalLoad(i, [0, 0, p / 4.0, 0, 0, 0]))
    m.add_combination("K1", {"LF1": 1.0, "LF2": 1.0}, typ="ULS")
    out0 = solver.solve_combinations(m, ["K1"])
    nahe("ohne Fließen: die Kombination ist die Überlagerung, 1,2 fy/E", float(out0["K1"].u[n[4:], 2].mean()), 2 * p / E, 1e-6, "m")
    m.plastizitaet = einst
    out = solver.solve_combinations(m, ["K1"])
    r = out["K1"]
    nahe("mit Fließen: die Kombination wird direkt gerechnet, 1,2 fy/E + 0,2 fy/H",
         float(r.u[n[4:], 2].mean()), 2 * p / E + (2 * p - FY) / einst.H(E), 1e-6, "m")
    check("… und trägt die Plastizität in res.info", (r.info.get("plastizitaet") or {}).get("fliessend") == 1)


def test_kontakt():
    """Block auf starrer Platte mit Reibung (Kontakt-Iteration) - die
    Streckgrenze auf 60 % der elastischen Vergleichsspannung gesetzt: die
    Plastizitaet iteriert um die Kontaktrechnung, konvergiert, das
    Gleichgewicht bleibt, die Verformung waechst, die starre Platte (ohne fy)
    bleibt elastisch."""
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    q0 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
             if m0.elements[i].mat == "S235")
    F = np.array([l.F[:3] for l in m0.case().nodal_loads], float).sum(axis=0)
    m = block_friction_example()
    m.materials["S235"].fy = 0.6 * q0
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2, iterationen=40, toleranz=1e-4)
    r = solver.solve_static(m)
    info = r.info.get("plastizitaet") or {}
    check(f"Block mit fy = 60 % der elastischen Vergleichsspannung ({q0 / 1e6:.1f} MPa): Fließen, konvergiert",
          info.get("fliessend", 0) > 0 and info.get("konvergiert"), f"{info.get('fliessend')} Elemente, "
          f"{info.get('iterationen')} Schritte, ε_p max {info.get('eps_p_max', 0) * 100:.4f} %")
    check("die Kontakt-Iteration ist konvergiert", r.info.get("contact_converged"), str(r.info.get("contact_iterations")))
    check("Gleichgewicht: die Auflager tragen die Last",
          np.allclose(r.reactions[:, :3].sum(axis=0), -F, rtol=1e-6, atol=1e-6 * float(np.abs(F).max())),
          f"{r.reactions[:, :3].sum(axis=0)} zu {-F}")
    u0 = float(np.abs(r0.u[:, :3]).max())
    u1 = float(np.abs(r.u[:, :3]).max())
    check("mit Fließen ist die größte Verschiebung größer als elastisch", u1 > u0 * 1.001, f"{u1 * 1e3:.4f} mm zu {u0 * 1e3:.4f} mm")
    q1 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r.solid_res.items() if m.elements[i].mat == "S235")
    fy = m.materials["S235"].fy
    check("die Vergleichsspannung der Elementmitten bleibt nahe fy (Verfestigung 5 %)",
          q1 < fy * 1.5, f"max {q1 / 1e6:.1f} MPa, fy {fy / 1e6:.1f} MPa")
    check("die starre Platte (ohne fy) fließt nicht",
          all(m.elements[i].mat != "Starr" for i in r.info.get("plastisch", {})))
    # speichern und laden der Einstellung
    with tempfile.TemporaryDirectory() as tmp:
        pf = os.path.join(tmp, "p.json")
        m.save(pf)
        m3 = Model.load(pf)
        e3 = getattr(m3, "plastizitaet", None)
        check("die Einstellung reist mit dem Modell (an, 5 %, 2 Laststufen)",
              e3 is not None and e3.an and abs(e3.verfestigung - 0.05) < 1e-12 and e3.laststufen == 2, str(e3))


def main():
    for t in (test_rueckfuehrung, test_zugversuch, test_loeser, test_kombination, test_kontakt):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
