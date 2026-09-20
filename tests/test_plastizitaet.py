"""Plastizitaet (17.09.2026): von Mises mit linearer Verfestigung - gegen die
geschlossene Loesung des einachsigen Zugversuchs (ein Hexaeder) und die
Rueckfuehrung im Schub.

Dazu (20.09.2026) der zweite Weg: Newton mit der konsistenten
elastoplastischen Tangente. Geprueft wird, dass D_ep wirklich die Ableitung
der Rueckfuehrung ist, dass der Zugversuch bei 1 % Verfestigung damit
konvergiert (die Anfangsdehnungs-Iteration tut es nicht) und dass die
Faktorisierungen gezaehlt werden.

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


def _tet4_netz(n=6):
    """Ein Quader aus n Wuerfeln zu je sechs Tetraedern - genug Elemente,
    Knoten und Nachbarschaften, um die blockweise Rechnung zu pruefen."""
    m = Model("Tet4")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    m.add_material(Material("Ohne fy", E=E, nu=NU, rho=7850))
    knoten = {}
    for i in range(n + 1):
        for j in range(2):
            for k in range(2):
                knoten[(i, j, k)] = m.add_node(i * 0.1, j * 0.1, k * 0.1)
    # Die sechs Tetraeder eines Wuerfels (Kuhn-Zerlegung)
    muster = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]
    for i in range(n):
        ecke = [knoten[(i + (b & 1), (b >> 1) & 1, (b >> 2) & 1)] for b in range(8)]
        for t, vier in enumerate(muster):
            mat = "S355" if (i + t) % 5 else "Ohne fy"    # ein Werkstoff ohne Streckgrenze dazwischen
            m.add_element("tet4", [ecke[v] for v in vier], mat, "")
    return m


def test_blockweise_wie_die_schleife():
    """Die blockweise Rechnung muss dasselbe liefern wie die Schleife - sie
    ist nur schneller (19.09.2026: am Drehlager 51,5 s → 1,39 s je Schritt
    bei 646 706 Tetraedern, gemessen mit u = 0; die Zeit lag im Aufrufaufwand
    je Element, nicht in der Physik)."""
    m = _tet4_netz()
    el = pl._solid_elemente(m, None)
    check(f"Netz aus {len(el)} Tetraedern, zwei Werkstoffe (einer ohne fy)",
          len(el) >= 30 and len({m.elements[i].mat for i in el}) == 2, str(len(el)))
    einst = pl.Plastizitaet(an=True, verfestigung=0.02)
    rng = np.random.default_rng(5)
    for lauf, faktor in enumerate((0.0, 2e-4, 2e-3), start=1):
        u = rng.normal(0.0, faktor, m.ndof) if faktor else np.zeros(m.ndof)
        Fb, zb, ib = pl._schritt_block(m, u, pl.Zustand(), einst, el, "tet4", [])
        Fs, zs, is_ = pl._schritt_schleife(m, u, pl.Zustand(), einst, el, [])
        bez = max(float(np.abs(Fs).max()), 1e-30)
        check(f"Lauf {lauf} (u ~ {faktor:g}): gleich viele fließende Elemente "
              f"({is_['fliessend']})", ib["fliessend"] == is_["fliessend"],
              f"{ib['fliessend']} / {is_['fliessend']}")
        check(f"Lauf {lauf}: F_p stimmt bis auf Rundung",
              float(np.abs(Fb - Fs).max()) <= 1e-9 * bez,
              f"{float(np.abs(Fb - Fs).max()):.3e} N von {bez:.3e} N")
        check(f"Lauf {lauf}: dieselben Elemente mit plastischer Dehnung",
              set(zb.eps_p) == set(zs.eps_p), f"{len(zb.eps_p)} / {len(zs.eps_p)}")
        if zb.eps_p:
            dp = max(float(np.abs(np.asarray(zb.eps_p[i]) - np.asarray(zs.eps_p[i])).max())
                     for i in zb.eps_p)
            dq = max(abs(zb.eps_p_eq[i] - zs.eps_p_eq[i]) for i in zb.eps_p_eq)
            check(f"Lauf {lauf}: eps_p und eps_p,eq stimmen bis auf Rundung",
                  dp < 1e-12 and dq < 1e-12, f"{dp:.2e} / {dq:.2e}")
        nahe(f"Lauf {lauf}: dieselbe größte Vergleichsspannung", ib["q_max"], is_["q_max"], 1e-12, "Pa")
    # Der Werkstoff ohne Streckgrenze fließt in keinem der beiden Wege
    u = rng.normal(0.0, 5e-3, m.ndof)
    _F, zb, _i = pl._schritt_block(m, u, pl.Zustand(), einst, el, "tet4", [])
    ohne = [i for i in zb.eps_p if m.elements[i].mat == "Ohne fy" and zb.eps_p_eq[i] > 0]
    check("ein Werkstoff ohne Streckgrenze bleibt elastisch", not ohne, str(ohne[:4]))
    # Und der Stapel wird nur einmal gebaut
    d1 = pl._stapel(m, el, "tet4")
    d2 = pl._stapel(m, el, "tet4")
    check("die Geometriedaten des Stapels werden wiederverwendet", d1 is d2)


#: Eckpunkte je Elementtyp (Einheitsform) und die Kanten fuer die Mitten der
#: quadratischen Typen - fuer den Vergleich blockweise gegen Schleife
_ECKEN = {
    "tet4": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)],
    "hex8": [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
             (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    "pent6": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (0, 1, 1)],
    "pyr5": [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 1)],
}
_KANTEN = {
    "tet10": ("tet4", [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]),
    "hex20": ("hex8", [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                       (0, 4), (1, 5), (2, 6), (3, 7)]),
    "pent15": ("pent6", [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)]),
}


def _stapel_modell(typ, n=8):
    """n Elemente eines Typs, leicht verzerrt - eine gerade Jacobi-Matrix
    würde einen Fehler in der blockweisen Rechnung verdecken."""
    from statik3d.elements import solid as sl
    m = Model(typ)
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    m.add_material(Material("Ohne fy", E=E, nu=NU, rho=7850))
    grundtyp, kanten = _KANTEN.get(typ, (typ, []))
    basis = np.asarray(_ECKEN[grundtyp], float)
    if kanten:
        basis = np.vstack([basis] + [(basis[a] + basis[b]) / 2 for a, b in kanten])
    rng = np.random.default_rng(11)
    for e in range(n):
        P = basis + np.array([e * 1.3, 0.0, 0.0]) + rng.normal(0.0, 0.02, basis.shape)
        ids = [m.add_node(*p) for p in P[:sl._KNOTENZAHL[typ]]]
        m.add_element(typ, ids, "S355" if e % 4 else "Ohne fy", "")
    return m


def test_blockweise_fuer_jeden_elementtyp():
    """Der blockweise Weg gilt für **jeden** Volumenelementtyp: die
    Plastizität wertet je Element einen Punkt aus (die Mitte), und die
    Formfunktionsableitungen dort sind eine feste Matrix des Typs. Nur die
    plastischen Knotenlasten brauchen alle Gaußpunkte - bei hex8 acht statt
    einem (19.09.2026, „dann mach das für die anderen Elementtypen auch“)."""
    from statik3d.elements import solid as sl
    rng = np.random.default_rng(3)
    for typ in ("tet4", "hex8", "tet10", "hex20", "pent6", "pent15", "pyr5"):
        m = _stapel_modell(typ)
        el = pl._solid_elemente(m, None)
        u = rng.normal(0.0, 1.5e-3, m.ndof)
        einst = pl.Plastizitaet(an=True, verfestigung=0.02)
        Fb, zb, ib = pl._schritt_block(m, u, pl.Zustand(), einst, el, typ, [])
        Fs, zs, is_ = pl._schritt_schleife(m, u, pl.Zustand(), einst, el, [])
        bez = max(float(np.abs(Fs).max()), 1e-30)
        gleich = set(zb.eps_p) == set(zs.eps_p)
        dp = (max(float(np.abs(np.asarray(zb.eps_p[i]) - np.asarray(zs.eps_p[i])).max())
                  for i in zb.eps_p) if gleich and zb.eps_p else 0.0)
        check(f"{typ}: gleich viele fließende Elemente ({is_['fliessend']} von {len(el)})",
              ib["fliessend"] == is_["fliessend"], f"{ib['fliessend']} / {is_['fliessend']}")
        check(f"{typ}: F_p stimmt bis auf Rundung",
              float(np.abs(Fb - Fs).max()) <= 1e-9 * bez,
              f"{float(np.abs(Fb - Fs).max()) / bez:.2e} relativ")
        check(f"{typ}: dieselben Elemente mit plastischer Dehnung, gleiche Werte",
              gleich and dp < 1e-12, f"{len(zb.eps_p)} / {len(zs.eps_p)}, Δ {dp:.2e}")
        check(f"{typ}: dieselbe größte Vergleichsspannung",
              abs(ib["q_max"] - is_["q_max"]) <= 1e-9 * max(is_["q_max"], 1e-30),
              f"{ib['q_max']:.6e} / {is_['q_max']:.6e}")
    # Ein gemischtes Netz geht Typ für Typ und legt die Ergebnisse zusammen
    m = Model("gemischt")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    for typ in ("tet4", "hex8"):
        basis = np.asarray(_ECKEN[typ], float)
        for e in range(3):
            P = basis + np.array([e * 1.3 + (0 if typ == "tet4" else 10.0), 0.0, 0.0])
            m.add_element(typ, [m.add_node(*p) for p in P], "S355", "")
    el = pl._solid_elemente(m, None)
    u = rng.normal(0.0, 1.5e-3, m.ndof)
    einst = pl.Plastizitaet(an=True, verfestigung=0.02)
    Fb, zb, ib = pl.schritt(m, u, pl.Zustand(), einst, el, [])
    Fs, zs, is_ = pl._schritt_schleife(m, u, pl.Zustand(), einst, el, [])
    check("gemischtes Netz (tet4 und hex8): gleiches Ergebnis wie die Schleife",
          ib["fliessend"] == is_["fliessend"] and set(zb.eps_p) == set(zs.eps_p)
          and float(np.abs(Fb - Fs).max()) <= 1e-9 * max(float(np.abs(Fs).max()), 1e-30),
          f"{ib['fliessend']} / {is_['fliessend']} fließend")


def test_tangente_ist_die_ableitung_der_rueckfuehrung():
    """D_ep muss die Ableitung der Rueckfuehrung nach der Gesamtdehnung sein -
    sonst ist es kein Newton-Verfahren, sondern Glueckssache. Geprueft gegen
    die zentrale Differenz, ueber die Verfestigung von 0,1 % bis 50 % und ueber
    zufaellige Dehnungszustaende mit und ohne vorhandene plastische Dehnung
    (auch reiner Schub und mehrachsig, nicht nur einachsig)."""
    G = E / (2 * (1 + NU))
    lam = E * NU / ((1 + NU) * (1 - 2 * NU))
    D_el = np.zeros((6, 6))
    for a in range(6):
        e = np.zeros(6)
        e[a] = 1.0
        D_el[:, a] = pl._spannung(np.array([lam]), np.array([G]), e[None, :])[0]

    def sigma(eps, H, eps_p_alt, eps_p_eq):
        tr = pl._spannung(np.array([lam]), np.array([G]), (eps - eps_p_alt)[None, :])[0]
        return pl.rueckfuehrung(tr, FY, H, G, eps_p_eq)[0]

    rng = np.random.default_rng(7)
    schlecht, geprueft, groesste = [], 0, 0.0
    for r in (0.001, 0.01, 0.1, 0.5):
        H = E * r / (1 - r)
        for lauf in range(8):
            eps = rng.normal(0, 3e-3, 6)
            if lauf == 0:                       # reiner Schub
                eps = np.array([0.0, 0.0, 0.0, 6e-3, 0.0, 0.0])
            eps_p_alt = rng.normal(0, 5e-4, 6) if lauf % 2 else np.zeros(6)
            eps_p_alt = eps_p_alt - eps_p_alt[:3].mean() * np.array([1.0, 1.0, 1.0, 0, 0, 0])
            eps_p_eq = float(abs(rng.normal(0, 1e-3))) if lauf % 2 else 0.0
            tr = pl._spannung(np.array([lam]), np.array([G]), (eps - eps_p_alt)[None, :])[0]
            q = pl.vergleichsspannung(tr)
            if q <= FY + H * eps_p_eq:
                continue
            dev = tr - ((tr[0] + tr[1] + tr[2]) / 3.0) * pl._EINS
            dg = pl.rueckfuehrung(tr, FY, H, G, eps_p_eq)[2]
            D_ep = D_el + pl.tangenten_differenz(dev[None, :], np.array([q]), np.array([dg]),
                                                 np.array([G]), np.array([H]))[0]
            num = np.zeros((6, 6))
            h = 1e-9
            for a in range(6):
                ep, em = eps.copy(), eps.copy()
                ep[a] += h
                em[a] -= h
                num[:, a] = (sigma(ep, H, eps_p_alt, eps_p_eq)
                             - sigma(em, H, eps_p_alt, eps_p_eq)) / (2 * h)
            abw = float(np.abs(D_ep - num).max() / np.abs(num).max())
            sym = float(np.abs(D_ep - D_ep.T).max() / np.abs(D_ep).max())
            geprueft += 1
            groesste = max(groesste, abw)
            if abw > 1e-5 or sym > 1e-12:
                schlecht.append((r, lauf, abw, sym))
    check(f"D_ep ist die Ableitung der Rückführung ({geprueft} Zustände, 0,1 % bis 50 % "
          f"Verfestigung)", geprueft >= 20 and not schlecht,
          f"größte Abweichung {groesste:.1e}" + (f", schlecht: {schlecht[:2]}" if schlecht else ""))
    # Einachsig: die Tangente muss unter sigma_yy = sigma_zz = 0 genau E_t geben
    for r in (0.01, 0.1):
        H = E * r / (1 - r)
        eps = np.array([2.0 * FY / E, 0.0, 0.0, 0.0, 0.0, 0.0])
        eps[1] = eps[2] = -0.5 * eps[0]          # volumentreu: einachsig weit im Fliessen
        tr = pl._spannung(np.array([lam]), np.array([G]), eps[None, :])[0]
        q = pl.vergleichsspannung(tr)
        dg = pl.rueckfuehrung(tr, FY, H, G, 0.0)[2]
        dev = tr - ((tr[0] + tr[1] + tr[2]) / 3.0) * pl._EINS
        D_ep = D_el + pl.tangenten_differenz(dev[None, :], np.array([q]), np.array([dg]),
                                             np.array([G]), np.array([H]))[0]
        # E_t = 1 / (S_ep)_11 mit S_ep = D_ep^-1 - das ist die einachsige Tangente
        E_t = 1.0 / np.linalg.inv(D_ep)[0, 0]
        nahe(f"einachsige Tangente aus D_ep bei E_t/E = {r:.0%}", E_t, r * E, 1e-9, "Pa")


def test_dk_symmetrisch_weich_und_bei_tet4_exakt():
    """ΔK muss dreierlei sein: **symmetrisch** (CHOLMOD in der Löserkette
    verträgt nichts anderes), **negativ semidefinit** (Fließen macht weicher,
    nie steifer - sonst könnte K + ΔK indefinit werden) und bei tet4 die
    **exakte** Ableitung −∂F_p/∂u.

    Bei den quadratischen Typen ist sie es nicht: ε_p hängt an der Dehnung in
    der Elementmitte, F_p integriert aber über alle Gaußpunkte, und für
    tet10/hex20/pent15 ist das Mittel von B über das Element nicht der Wert in
    der Mitte. Gemessen an verzerrten Elementen weicht ΔK dort bis zu 53 % von
    −∂F_p/∂u ab (hex8 und pent6: rund 1 %). Es bleibt ein Quasi-Newton: die
    Richtung stimmt, die Konvergenz ist superlinear statt quadratisch."""
    einst = pl.Plastizitaet(an=True, verfestigung=0.02)
    rng = np.random.default_rng(3)
    for typ in ("tet4", "hex8", "tet10", "hex20", "pent6", "pent15", "pyr5"):
        m = _stapel_modell(typ, n=2)
        el = pl._solid_elemente(m, None)
        u = rng.normal(0.0, 1.5e-3, m.ndof)
        F_p, _z, info = pl._schritt_block(m, u, pl.Zustand(), einst, el, typ, [], tangente=True)
        dK = info["dK"].toarray()
        gr = max(float(np.abs(dK).max()), 1e-30)
        ew = np.linalg.eigvalsh(0.5 * (dK + dK.T))
        check(f"{typ}: ΔK ist symmetrisch", float(np.abs(dK - dK.T).max()) / gr < 1e-12,
              f"{float(np.abs(dK - dK.T).max()) / gr:.2e}")
        check(f"{typ}: ΔK ist negativ semidefinit (Fließen macht weicher)",
              float(ew.max()) <= 1e-9 * float(np.abs(ew).max()),
              f"größter Eigenwert {float(ew.max()) / max(float(np.abs(ew).max()), 1e-30):+.2e}")
        if typ in ("tet4", "pyr5"):
            num = np.zeros((m.ndof, m.ndof))
            h = 1e-9
            for a in range(m.ndof):
                up, um = u.copy(), u.copy()
                up[a] += h
                um[a] -= h
                num[:, a] = -(pl._schritt_block(m, up, pl.Zustand(), einst, el, typ, [])[0]
                              - pl._schritt_block(m, um, pl.Zustand(), einst, el, typ, [])[0]) / (2 * h)
            abw = float(np.abs(dK - num).max()) / max(float(np.abs(num).max()), 1e-30)
            check(f"{typ}: ΔK ist genau −∂F_p/∂u (ein Auswertepunkt = ein Gaußpunkt)",
                  abw < 1e-6, f"{abw:.2e}")


def _zugstab(sigma, n=2, L=0.3, b=0.1):
    """Quader an drei Symmetrieebenen gehalten, am anderen Ende gezogen -
    einachsig, ohne Singularität, mit tet4 vernetzt. Für den Vergleich der
    beiden Wege mit der geschlossenen Lösung σ = fy + H ε_p."""
    kuhn = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]
    m = Model("Zugstab")
    m.add_material(Material("S355", E=E, nu=NU, rho=0.0, fy=FY))
    ids = {}
    for i in range(n + 1):
        for j in range(n + 1):
            for k in range(n + 1):
                ids[(i, j, k)] = m.add_node(i * L / n, j * b / n, k * b / n)
    for i in range(n):
        for j in range(n):
            for k in range(n):
                ec = [ids[(i + (x & 1), j + ((x >> 1) & 1), k + ((x >> 2) & 1))] for x in range(8)]
                for v in kuhn:
                    m.add_element("tet4", [ec[x] for x in v], "S355", "")
    for j in range(n + 1):
        for k in range(n + 1):
            m.fix(ids[(0, j, k)], [0])
    for i in range(n + 1):
        for k in range(n + 1):
            m.fix(ids[(i, 0, k)], [1])
        for j in range(n + 1):
            m.fix(ids[(i, j, 0)], [2])
    gew = {ids[(n, j, k)]: (0.5 if j in (0, n) else 1.0) * (0.5 if k in (0, n) else 1.0)
           for j in range(n + 1) for k in range(n + 1)}
    s = sum(gew.values())
    for nd, w in gew.items():
        m.load_node(nd, Fx=sigma * b * b * w / s)
    return m, [ids[(n, j, k)] for j in range(n + 1) for k in range(n + 1)], L


def test_newton_bei_kleiner_verfestigung():
    """Der Kern der Sache (20.09.2026): bei 1 % Verfestigung zieht sich die
    Anfangsdehnungs-Iteration mit 1 − E_t/E = 0,99 je Schritt zusammen - rund
    700 Schritte für 1e-3. Sie konvergiert in 25 Schritten je Laststufe nicht,
    und bei 1,5 fy lag die Dehnung am Ende um 9 % daneben. Newton mit der
    konsistenten Tangente braucht 7 bis 12 Schritte und bleibt unter 0,5 %.

    Gemessen wird die **mittlere Dehnung am gezogenen Ende** gegen
    ε = σ/E + (σ − fy)/H; die größte Vergleichsspannung der Elementmitten
    streut auf diesem groben Netz von sich aus um rund 1 %.
    """
    r = 0.01
    H = E * r / (1 - r)
    for faktor, hoechstens in ((1.20, 0.01), (1.50, 0.01)):
        sig = faktor * FY
        soll = sig / E + (sig - FY) / H
        ergebnis = {}
        for weg in ("tangente", "anfangsdehnung"):
            m, ende, L = _zugstab(sig)
            m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=r, laststufen=3,
                                             iterationen=25, toleranz=1e-3, verfahren=weg)
            res = solver.solve_static(m)
            info = res.info.get("plastizitaet") or {}
            ergebnis[weg] = (info, float(res.u[ende, 0].mean()) / L)
        (it, eps_t), (ia, eps_a) = ergebnis["tangente"], ergebnis["anfangsdehnung"]
        check(f"Zugversuch {faktor:.2f} fy, Verfestigung 1 %: Newton konvergiert in "
              f"{it.get('iterationen')} Schritten", it.get("konvergiert"),
              f"{it.get('iterationen')} Schritte, {it.get('faktorisierungen')} Faktorisierungen")
        check("… die Anfangsdehnungs-Iteration nicht (25 Schritte je Laststufe)",
              not ia.get("konvergiert"), f"{ia.get('iterationen')} Schritte, "
              f"Dehnung {100 * abs(eps_a - soll) / soll:.2f} % daneben")
        nahe("… und die Dehnung am Ende stimmt (ε = σ/E + (σ − fy)/H)", eps_t, soll, hoechstens)
        check("… deutlich besser als der alte Weg",
              abs(eps_t - soll) < 0.25 * abs(eps_a - soll),
              f"{100 * abs(eps_t - soll) / soll:.2f} % gegen {100 * abs(eps_a - soll) / soll:.2f} %")
    # Die Zahl der Faktorisierungen ist genau die Zahl der Newton-Schritte, in
    # denen noch korrigiert wurde: je Laststufe einer weniger als Schritte.
    m, ende, L = _zugstab(1.2 * FY)
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=r, laststufen=3, iterationen=25,
                                     toleranz=1e-3, verfahren="tangente")
    info = (solver.solve_static(m).info.get("plastizitaet") or {})
    check("je Plastizitätsschritt eine Faktorisierung - bis auf den letzten je Laststufe",
          info.get("faktorisierungen") == info.get("iterationen") - info.get("laststufen")
          and info.get("verfahren") == "tangente",
          f"{info.get('faktorisierungen')} Faktorisierungen, {info.get('iterationen')} Schritte, "
          f"{info.get('laststufen')} Laststufen")
    m2, _e2, _L2 = _zugstab(1.2 * FY)
    m2.plastizitaet = pl.Plastizitaet(an=True, verfestigung=r, laststufen=3, iterationen=25,
                                      toleranz=1e-3, verfahren="anfangsdehnung")
    i2 = (solver.solve_static(m2).info.get("plastizitaet") or {})
    check("der alte Weg faktorisiert gar nicht neu", i2.get("faktorisierungen") == 0
          and i2.get("verfahren") == "anfangsdehnung", str(i2.get("faktorisierungen")))
    # Ohne Verfestigung ist D_ep in Fließrichtung singulär - dann bleibt nur
    # der alte Weg, und zwar von selbst
    m3, _e3, _L3 = _zugstab(1.05 * FY)
    m3.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.0, laststufen=2, iterationen=10,
                                      toleranz=1e-2, verfahren="tangente")
    i3 = (solver.solve_static(m3).info.get("plastizitaet") or {})
    check("ideal-plastisch (keine Verfestigung): fällt auf die Anfangsdehnungs-Iteration zurück",
          i3.get("verfahren") == "anfangsdehnung" and i3.get("faktorisierungen") == 0, str(i3)[:90])


def test_zusatzsteifigkeit_gehoert_in_den_schluessel_der_faktorisierung():
    """``StaticSystem.solve`` behält die Faktorisierung, solange die Signatur
    des Kontakts gleich bleibt. Die kennt K_zusatz nicht - und K_zusatz ändert
    sich in **jedem** Newton-Schritt (die konsistente Tangente) und in jedem
    Ausfallschritt (die abgezogene Steifigkeit). Ohne den Inhalt von K_zusatz
    im Schlüssel löste der zweite Aufruf mit der alten Matrix weiter
    (20.09.2026)."""
    from scipy import sparse
    m = block_friction_example()

    def zusatz(system, f):
        """Diagonale Zusatzsteifigkeit auf den freien FHG - groß genug, um die
        Lösung zu verschieben, klein genug, dass die Aktivmenge gleich bleibt
        (und damit die Kontaktsignatur, worauf es hier ankommt)."""
        fi = system.fi
        k = f * float(abs(system.K.diagonal()[fi]).mean())
        return sparse.coo_matrix((np.full(len(fi), k), (fi, fi)), shape=system.K.shape).tocsr()

    F = solver.case_loads(m, {list(m.load_cases)[0]: 1.0})[0]
    # Ein eingefrorener Kontaktzustand: derselbe Zustand, also **dieselbe**
    # Kontaktsignatur bei jedem Aufruf - genau die Lage, in der die Newton-
    # Schritte der Plastizität landen, sobald sich die Aktivmenge nicht mehr
    # rührt. Nur K_zusatz ist verschieden.
    s0 = solver.StaticSystem(m)
    zustand = solver.solve_with_contact(m, s0, F)[4]["contact_state"]
    check("ein Kontaktzustand zum Einfrieren liegt vor", zustand is not None)
    sa = solver.StaticSystem(m)
    ua = solver.solve_with_contact(m, sa, F, K_zusatz=zusatz(sa, 0.05), einfrieren=zustand)[0]
    sb = solver.StaticSystem(m)
    ub = solver.solve_with_contact(m, sb, F, K_zusatz=zusatz(sb, 0.20), einfrieren=zustand)[0]
    bez = max(float(np.abs(ua).max()), 1e-30)
    check("zwei verschiedene Zusatzsteifigkeiten geben zwei verschiedene Lösungen",
          float(np.abs(ua - ub).max()) / bez > 1e-3,
          f"{float(np.abs(ua - ub).max()) / bez:.3e}")
    # Und nun beide nacheinander auf **einem** System
    s = solver.StaticSystem(m)
    u1 = solver.solve_with_contact(m, s, F, K_zusatz=zusatz(s, 0.05), einfrieren=zustand)[0]
    u2 = solver.solve_with_contact(m, s, F, K_zusatz=zusatz(s, 0.20), einfrieren=zustand)[0]
    check("erst 5 %: dieselbe Lösung wie auf dem frischen System",
          float(np.abs(u1 - ua).max()) / bez < 1e-9, f"{float(np.abs(u1 - ua).max()) / bez:.3e}")
    check("dann 20 %: auch - die Faktorisierung der 5 % bleibt nicht kleben",
          float(np.abs(u2 - ub).max()) / bez < 1e-9, f"{float(np.abs(u2 - ub).max()) / bez:.3e}")


def test_protokoll_sagt_was_die_runde_bewegt_und_kostet():
    """Die Zahl „N aktiv“ beantwortet nicht, ob eine Runde noch etwas
    ausrichtet: sie zählt offen gegen geschlossen und bleibt beim Wechsel
    haften → gleiten unverändert - und genau das ist die Arbeit von Phase 2
    (19.09.2026, Anwender vor einem Drehlager-Protokoll: „ist das wirklich
    relevant obwohl sich die anzahl so gering ändert“, und „interessant ist
    dass die iterationen immer schneller werden“). Die Zeile sagt jetzt dazu,
    wie weit sich u noch bewegt und ob die Matrix neu faktorisiert wurde -
    neu wird sie nur bei geänderter Signatur, und genau daran liegt es, dass
    die späten Runden rasen."""
    zeilen = []
    m = block_friction_example()
    solver.solve_static(m, progress=lambda t, a=None: zeilen.append(str(t)))
    kz = [z for z in zeilen if z.startswith("Kontakt-Iteration ")]
    check(f"die Kontakt-Iteration meldet jede Runde ({len(kz)})", len(kz) >= 5, str(kz[:1]))
    check("jede Runde sagt, ob die Matrix neu faktorisiert wurde",
          all(("Matrix neu" in z) or ("Matrix bleibt" in z) for z in kz),
          str([z for z in kz if "Matrix" not in z][:1]))
    check("ab der zweiten Runde steht die Verschiebungsänderung dabei",
          all("Δu" in z for z in kz[1:]), str([z for z in kz[1:] if "Δu" not in z][:1]))
    teuer = [z for z in kz if "Matrix neu" in z]
    billig = [z for z in kz if "Matrix bleibt" in z]
    check(f"beide Sorten kommen vor: {len(teuer)} mit neuer Matrix, {len(billig)} ohne",
          teuer and billig, f"{len(teuer)} / {len(billig)}")
    # Der Kern der Sache: gleiche Zahl „aktiv“, trotzdem unterschiedlich teuer
    def aktiv(z):
        return z.split(": ", 1)[1].split(" aktiv", 1)[0]
    gleich = {aktiv(z) for z in teuer} & {aktiv(z) for z in billig}
    check("dieselbe Zahl „aktiv“ kommt teuer und billig vor - die Zahl allein sagt nichts",
          bool(gleich), str(sorted(gleich)[:3]))


def test_kennzahlen_zaehlen_alle_laeufe_des_lastfalls():
    """Mit Plastizität löst derselbe Lastfall viele Male. ``res.info.update``
    liess davon nur die Zahlen des letzten Laufes stehen: am Drehlager meldete
    die Zusammenfassung „Kontakt-Iterationen: 2“ für eine Rechnung von 2289 s
    (19.09.2026). Jetzt wird aufaddiert - und die Zahl der Faktorisierungen
    steht dabei, denn sie trägt die Rechenzeit, nicht die Zahl der Runden."""
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    q0 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
             if m0.elements[i].mat == "S235")
    check("ohne Plastizität ist es ein Lauf, und die Faktorisierungen stehen dabei",
          int(r0.info.get("contact_laeufe", 0)) == 1
          and 1 <= int(r0.info.get("contact_factorisations", 0)) <= int(r0.info["contact_iterations"]),
          f"{r0.info.get('contact_laeufe')} Läufe, {r0.info.get('contact_factorisations')} von "
          f"{r0.info.get('contact_iterations')} Runden")
    m = block_friction_example()
    m.materials["S235"].fy = 0.6 * q0
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2,
                                     iterationen=40, toleranz=1e-4)
    r = solver.solve_static(m)
    n_l = int(r.info.get("contact_laeufe", 0))
    n_it = int(r.info.get("contact_iterations", 0))
    n_f = int(r.info.get("contact_factorisations", 0))
    check(f"mit Plastizität sind es viele Läufe ({n_l}), nicht einer", n_l > 1, str(n_l))
    check(f"die Runden werden über alle Läufe gezählt ({n_it})", n_it >= n_l, f"{n_it} zu {n_l}")
    check(f"und die Faktorisierungen auch ({n_f}) - höchstens eine je Runde",
          1 <= n_f <= n_it, f"{n_f} von {n_it}")
    z = [x for x in r.summary().splitlines() if x.startswith("Kontakt-Iterationen")]
    check("die Zusammenfassung nennt Runden, Läufe und Faktorisierungen",
          z and f"in {n_l} Läufen" in z[0] and "mit neuer Faktorisierung" in z[0],
          z[0] if z else "keine Zeile")


def _fliessendes_kontaktmodell():
    """Block mit Reibung, Streckgrenze auf 60 % der elastischen
    Vergleichsspannung: Kontakt **und** Fließen, also viele Läufe desselben
    Lastfalls."""
    m0 = block_friction_example()
    r0 = solver.solve_static(m0)
    q0 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
             if m0.elements[i].mat == "S235")
    m = block_friction_example()
    m.materials["S235"].fy = 0.6 * q0
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2,
                                     iterationen=40, toleranz=1e-4)
    return m


def test_kontaktsystem_wird_wiederverwendet():
    """Der geometrische Teil des Kontakts - welcher Slave-Knoten auf welche
    Master-Facette fällt, Normalen, Flächenquadriken, Suchbäume - hängt weder
    an der Last noch am Verformungszustand. Gebaut wurde er trotzdem bei jedem
    Aufruf neu, mit Plastizität also einmal je Schritt: am Drehlager 276
    Aufrufe von _build_pair für 12 Fugen, 172 s von 542 s (cProfile,
    20.09.2026). Jetzt hängt er am StaticSystem.

    Geprüft wird beides: dass er wirklich seltener gebaut wird **und** dass
    dieselbe Lösung herauskommt wie beim Bauen in jedem Schritt."""
    from statik3d import contact as ct
    n = {"bau": 0}
    alt_init = ct.ContactSystem.__init__

    def zaehlend(self, *a, **kw):
        n["bau"] += 1
        alt_init(self, *a, **kw)

    ct.ContactSystem.__init__ = zaehlend
    try:
        m = _fliessendes_kontaktmodell()
        n["bau"] = 0
        r = solver.solve_static(m)
        gebaut = n["bau"]
        laeufe = int(r.info.get("contact_laeufe", 0))
        # Die Schwelle war 10 Läufe - mit der konsistenten Tangente konvergiert
        # dasselbe Modell in 9 statt 28 Läufen (20.09.2026). Geprüft wird die
        # Wiederverwendung, nicht die Zahl der Läufe.
        check(f"viele Läufe desselben Lastfalls ({laeufe}), aber nur {gebaut} Kontaktsysteme",
              laeufe >= 4 and gebaut <= 2, f"{gebaut} Aufbauten bei {laeufe} Läufen")
        # Gegenprobe: bei jedem Aufruf neu bauen - dasselbe Ergebnis
        alt_ks = solver._kontaktsystem

        def immer_neu(system, model, uebermass, log):
            cs = ct.ContactSystem(model, system.K, log, uebermass)
            return cs

        solver._kontaktsystem = immer_neu
        try:
            m2 = _fliessendes_kontaktmodell()
            n["bau"] = 0
            r2 = solver.solve_static(m2)
            gebaut2 = n["bau"]
        finally:
            solver._kontaktsystem = alt_ks
        check(f"ohne Wiederverwendung wird je Lauf gebaut ({gebaut2})",
              gebaut2 >= laeufe, f"{gebaut2} Aufbauten bei {laeufe} Läufen")
        du = float(np.abs(r.u - r2.u).max())
        bez = max(float(np.abs(r2.u).max()), 1e-30)
        check("dieselbe Verschiebung wie beim Bauen in jedem Schritt",
              du <= 1e-12 * bez, f"{du / bez:.2e} relativ")
        check("dieselbe Zahl Kontaktrunden und Faktorisierungen",
              r.info["contact_iterations"] == r2.info["contact_iterations"]
              and r.info["contact_factorisations"] == r2.info["contact_factorisations"],
              f"{r.info['contact_iterations']}/{r.info['contact_factorisations']} zu "
              f"{r2.info['contact_iterations']}/{r2.info['contact_factorisations']}")
        pz, pz2 = r.info.get("plastizitaet") or {}, r2.info.get("plastizitaet") or {}
        check("dasselbe Fließen", pz.get("fliessend") == pz2.get("fliessend")
              and abs(pz.get("eps_p_max", 0) - pz2.get("eps_p_max", 0)) <= 1e-15,
              f"{pz.get('fliessend')} zu {pz2.get('fliessend')} Elemente")
    finally:
        ct.ContactSystem.__init__ = alt_init


def test_initialize_setzt_den_ganzen_zustand_zurueck():
    """Ein wiederverwendetes Kontaktsystem muss vor jeder Rechnung so
    dastehen wie ein frisch gebautes - sonst begönne der nächste Lastfall in
    Phase 2 mit den eingefrorenen Bedingungen des vorigen."""
    from statik3d import contact as ct
    m = block_friction_example()
    sys_ = solver.StaticSystem(m)
    cs = ct.ContactSystem(m, sys_.K, [], None)
    frisch = {k: getattr(cs, k) for k in
              ("phase", "cycles", "settle", "stabilising", "warm", "dF_slip",
               "gleit_anteil", "gleit_guete")}
    # Zustand verbiegen, wie ihn eine Rechnung hinterlässt
    cs.phase, cs.cycles, cs.settle = 2, 7, 3
    cs.stabilising, cs.warm, cs.dF_slip = True, True, 1.5
    cs.gleit_anteil, cs.gleit_guete = 0.5, 0.02
    for c in cs.cons[:5]:
        c.slip, c.frozen, c.yielding, c.toggles = True, True, True, 9
        c.gehalten = c.schub_halt = True
        c.Fn, c.g_yield = 1e5, 0.3
    cs.initialize()
    anders = [k for k, v in frisch.items() if getattr(cs, k) != v]
    check("initialize() stellt Phase, Zähler und Gleitanteil wieder her", not anders, str(anders))
    schlecht = [c.label for c in cs.cons[:5]
                if c.slip or c.frozen or c.yielding or c.toggles or c.gehalten
                or c.schub_halt or c.Fn or c.g_yield]
    check("und den Zustand jeder Bedingung", not schlecht, str(schlecht[:2]))


def main():
    for t in (test_rueckfuehrung, test_tangente_ist_die_ableitung_der_rueckfuehrung,
              test_blockweise_wie_die_schleife,
              test_blockweise_fuer_jeden_elementtyp, test_zugversuch,
              test_dk_symmetrisch_weich_und_bei_tet4_exakt,
              test_newton_bei_kleiner_verfestigung,
              test_zusatzsteifigkeit_gehoert_in_den_schluessel_der_faktorisierung,
              test_protokoll_sagt_was_die_runde_bewegt_und_kostet,
              test_kennzahlen_zaehlen_alle_laeufe_des_lastfalls,
              test_kontaktsystem_wird_wiederverwendet,
              test_initialize_setzt_den_ganzen_zustand_zurueck,
              test_loeser, test_kombination, test_kontakt):
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
