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

from statik3d import mesher, plastizitaet as pl, solver          # noqa: E402
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
    # Die Fliessbedingung gilt an den **Gausspunkten** (dort rechnet die
    # Plastizitaet seit dem 20.09.2026), nicht in der Elementmitte - die ist
    # ein Auswertepunkt dazwischen. Die Mitte muss darum unter der
    # verfestigten Fliessgrenze des am staerksten gedehnten Punktes bleiben;
    # vorher stand hier die Faustgrenze 1,5 fy, die nur galt, solange die
    # Plastizitaet selbst in der Mitte sass.
    ep_max = max(r.info.get("plastisch", {}).values(), default=0.0)
    grenze = fy + m.plastizitaet.H(m.materials["S235"].E) * ep_max
    check("die Vergleichsspannung bleibt unter der verfestigten Fließgrenze fy + H·ε_p",
          q1 <= grenze * 1.02,
          f"max {q1 / 1e6:.2f} MPa, Grenze {grenze / 1e6:.2f} MPa "
          f"(fy {fy / 1e6:.2f} + H·ε_p {(grenze - fy) / 1e6:.2f})")
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
        # Die Wahl "mit Kontakt" (23.09.2026) ebenso - und eine Datei von
        # vorher ohne sie laedt mit der Vorgabe
        m.plastizitaet.kontakt = "verschachtelt"
        m.save(pf)
        e4 = Model.load(pf).plastizitaet
        import json as _json
        with open(pf, encoding="utf-8") as f:
            daten = _json.load(f)
        daten["plastizitaet"].pop("kontakt", None)
        with open(pf, "w", encoding="utf-8") as f:
            _json.dump(daten, f)
        e5 = Model.load(pf).plastizitaet
        check("… auch „mit Kontakt: verschachtelt“; ältere Dateien laden mit „gemeinsam“",
              e4.kontakt == "verschachtelt" and e5.kontakt == "gemeinsam", f"{e4.kontakt} / {e5.kontakt}")


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
            # eps_p_eq steht seit dem 20.09.2026 je Gausspunkt (ein Feld),
            # nicht mehr als eine Zahl je Element.
            dq = max(float(np.max(np.abs(np.asarray(zb.eps_p_eq[i], float)
                                         - np.asarray(zs.eps_p_eq[i], float))))
                     for i in zb.eps_p_eq)
            check(f"Lauf {lauf}: eps_p und eps_p,eq stimmen bis auf Rundung",
                  dp < 1e-12 and dq < 1e-12, f"{dp:.2e} / {dq:.2e}")
        nahe(f"Lauf {lauf}: dieselbe größte Vergleichsspannung", ib["q_max"], is_["q_max"], 1e-12, "Pa")
    # Der Werkstoff ohne Streckgrenze fließt in keinem der beiden Wege
    u = rng.normal(0.0, 5e-3, m.ndof)
    _F, zb, _i = pl._schritt_block(m, u, pl.Zustand(), einst, el, "tet4", [])
    ohne = [i for i in zb.eps_p if m.elements[i].mat == "Ohne fy"
            and float(np.max(zb.eps_p_eq[i])) > 0]
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
    nie steifer - sonst könnte K + ΔK indefinit werden) und die **exakte**
    Ableitung −∂F_p/∂u - für jeden Typ, siehe
    test_tangente_exakt_fuer_jeden_typ."""
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


def test_tangente_exakt_fuer_jeden_typ():
    """A5/B3 des Auftrags vom 22.09.2026: ΔK = −∂F_p/∂u für **jeden** Typ.

    Im Quelltext stand bis dahin, ΔK weiche beim tet10 bis 53 % und beim hex8
    rund 1 % ab. Das galt, solange ε_p an der Elementmitte hing; seit dem
    Zustand je Gaußpunkt (20.09.2026) ist ΔK Punkt für Punkt die Ableitung
    der Rückführung - gemessen gegen zentrale Differenzen auf 0,8e-9 bis
    1,7e-9. Die Verschiebung ist so groß gewählt, dass mehrere Punkte
    fließen; geprüft werden nur die Spalten, in denen ΔK etwas trägt (die
    übrigen sind elastisch und ohnehin null)."""
    einst = pl.Plastizitaet(an=True, verfestigung=0.02)
    rng = np.random.default_rng(5)
    for typ in ("tet4", "hex8", "tet10", "hex20", "pent6", "pent15", "pyr5"):
        m = _stapel_modell(typ, n=2)
        el = pl._solid_elemente(m, None)
        u = rng.normal(0.0, 2.5e-3, m.ndof)
        _F, _z, info = pl._schritt_block(m, u, pl.Zustand(), einst, el, typ, [], tangente=True)
        dK = info["dK"].toarray()
        spalten = np.flatnonzero(np.abs(dK).sum(axis=0) > 0)
        num = np.zeros((m.ndof, len(spalten)))
        h = 1e-9
        for j, a in enumerate(spalten):
            up, um = u.copy(), u.copy()
            up[a] += h
            um[a] -= h
            num[:, j] = -(pl._schritt_block(m, up, pl.Zustand(), einst, el, typ, [])[0]
                          - pl._schritt_block(m, um, pl.Zustand(), einst, el, typ, [])[0]) / (2 * h)
        abw = float(np.abs(dK[:, spalten] - num).max()) / max(float(np.abs(num).max()), 1e-30)
        check(f"{typ}: ΔK = −∂F_p/∂u ({info['fliessend']} fließende Elemente)",
              info["fliessend"] > 0 and abw < 1e-6, f"{abw:.2e}")


def test_newton_konvergiert_quadratisch():
    """Mit exakter Tangente ist Newton quadratisch: e_k+1 ≲ C e_k². Kragträger
    200 x 200 mm unter 1,20 M_el (Endmoment als lineare Normalspannung),
    eine Laststufe, hex8 und tet10. Gemessen 22.09.2026: hex8 2,2e-1, 3,6e-1,
    1,8e-3, 2,5e-6, 2,3e-12; tet10 9,6e-2, 1,5e-1, 2,1e-3, 2,4e-6, 8,5e-12 -
    danach Rundung."""
    import re
    from tests import pruefkoerper as pk
    fy, b, h, L = 235e6, 0.2, 0.2, 1.0
    M = 1.2 * fy * b * h ** 2 / 6.0
    I = b * h ** 3 / 12.0
    for typ, netz in (("hex8", (5, 1, 4)), ("tet10", (5, 1, 2))):
        m, _ids = pk.quader(typ, *netz, L, b, h, fy=fy)
        for k in [n for n in range(m.nn) if abs(m.nodes[n, 0]) < 1e-9]:
            m.fix(int(k), "all")
        seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - L) < 1e-9)))
        pk.spannung_auf_seiten(m, seiten, lambda x: (M * (x[2] - h / 2) / I, 0.0, 0.0))
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=1,
                                         iterationen=12, toleranz=1e-10)
        meld = []
        r = solver.solve_static(m, progress=lambda s_, *a, **k: meld.append(str(s_)))
        e = [float(z[-1]) for s_ in meld if "Newton-Schritt" in s_
             for z in [re.findall(r"nderung ([0-9.]+e[+-][0-9]+)", s_)] if z]
        info = r.info.get("plastizitaet") or {}
        # die letzten drei Schritte oberhalb des Rundungsrauschens
        ueber = [x for x in e if x > 1e-10]
        quad = len(ueber) >= 3 and all(ueber[k + 1] <= 10.0 * ueber[k] ** 2
                                       for k in range(len(ueber) - 3, len(ueber) - 1))
        check(f"{typ}: Newton quadratisch unter 1,20 M_el", quad and info.get("konvergiert")
              and len(e) <= 6, " → ".join(f"{x:.1e}" for x in e))


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

    Nachgemessen 23.09.2026, nachdem die Anfangsdehnung nicht mehr den
    Zustand über die Schritte fortschreibt und am geschätzten Fehler abbricht
    (test_anfangsdehnung_trifft_den_newton): sie liegt bei 1,2 fy 18,3 % und
    bei 1,5 fy 0,32 % daneben (vorher 7,9 und 9,1 %) - beide Male nicht
    konvergiert, der Wert ist dann der letzte Schritt und kein Gütemaß. Geprüft wird darum nur noch, dass der Newton
    mindestens so nah liegt und der alte Weg „nicht konvergiert“ meldet.

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
        check("… mindestens so nah wie der alte Weg",
              abs(eps_t - soll) <= abs(eps_a - soll),
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


def test_rohr_ideal_plastisch_nach_hill():
    """Abnahme (Auftrag 4.3, 23.09.2026): plastische Grenzlast mit exaktem
    Sollwert. Dickwandiges Rohr a = 0,1 / b = 0,2 m, ebene Dehnung, ideal
    plastisch (fy = 355 N/mm², keine Verfestigung), nu = 0,4999 - dafür ist
    Hills Lösung exakt (tests/messung_rohr_plastisch.py). Bei c/a = 1,5
    (p = 255,88 N/mm²) ist σ_v an der Außenfläche fy c²/b² = 199,69 N/mm²,
    u_r(b) = k c²/(2G b); die Grenzlast p_L = 2 k ln(b/a) = 284,13 N/mm².

    Gemessen 23.09.2026: tet10 8 x 4 (1 377 FHG) σ_v(b) +0,56 N/mm², u_r(b)
    0,9967; hex8 32 x 16 (3 366 FHG) -0,42 / 0,9991. Die Grenzlast (mit dem
    Newton bestimmt): beide Netze tragen 0,995 p_L und 1,005 p_L nicht."""
    from tests import messung_rohr_plastisch as mr
    for typ, n_t, n_r in (("tet10", 8, 4), ("hex8", 32, 16)):
        z = mr.lauf(typ, n_t, n_r)
        check(f"Rohr nach Hill, {typ} {n_t} x {n_r}: ideal plastisch konvergiert", z["ok"].endswith(" konv."),
              z["ok"])
        check(f"… σ_v an der Außenfläche auf 1 N/mm² ({z['fhg']} FHG)", abs(z["sv_b"]) < 1.0,
              f"{z['sv_b']:+.2f} N/mm²")
        check("… u_r an der Außenfläche auf 0,5 %", abs(z["u"] - 1.0) < 5e-3, f"{z['u']:.4f}")
    for faktor, soll in ((0.995, True), (1.005, False)):
        check(f"tet10 8 x 4 {'trägt' if soll else 'trägt nicht'} {faktor:.3f} p_L "
              f"(Grenzlast nach Hill auf 0,5 %)", mr.traegt("tet10", 8, 4, faktor) == soll)


def test_anfangsdehnung_trifft_den_newton():
    """Beide Wege lösen dieselben Gleichungen und müssen auf denselben Punkt
    kommen. Bis zum 23.09.2026 schrieb die Anfangsdehnungs-Iteration den
    Zustand von Schritt zu Schritt fort; mit der Aitken-Überrelaxation sammelte
    sich plastische Dehnung entlang des Iterationswegs an, und sie meldete
    „konvergiert“ an einem anderen Punkt: am Rohr nach Hill (tet10 8 x 4,
    ideal plastisch, Toleranz 1e-6) u_r(b) 7e-4 neben dem Newton. Seitdem geht
    jede Rückführung vom Zustand am Anfang der Laststufe aus.

    Dazu der Abbruch am geschätzten Fehler statt an der Änderung (siehe
    plastizitaet.iteration) und die Zusage an die Löser-Sitzung: der Boden der
    Tangente (pl.H_TANGENTE) ändert bei üblicher Verfestigung kein Bit."""
    from tests import messung_rohr_plastisch as mr
    h = mr.Hill()
    u = {}
    for weg, ver in (("anfangsdehnung", 0.0), ("tangente", 1e-300)):
        m = mr.modell("tet10", 8, 4, h.p(0.15), verfestigung=ver)
        res = solver.solve_static(m)
        info = res.info["plastizitaet"]
        check(f"Rohr nach Hill, ideal plastisch: {weg} konvergiert", info.get("konvergiert")
              and info.get("verfahren") == weg, f"{info.get('verfahren')}, "
              f"{info.get('iterationen')} Schritte")
        u[weg] = np.asarray(res.u, float)
    abw = float(np.abs(u["anfangsdehnung"] - u["tangente"]).max() / np.abs(u["tangente"]).max())
    check("… Anfangsdehnung und Newton auf demselben Punkt (1e-5)", abw < 1e-5, f"{abw:.1e}")
    # Abbruch am geschaetzten Fehler (23.09.2026): nahe der Grenzlast zieht
    # sich die Folge mit ρ → 1 zusammen, und die Aenderung allein meldete zu
    # frueh "konvergiert" - bei der Vorgabe-Toleranz 1e-3 lag σ_v an den
    # Knoten bis 0,39 (hex8) bzw. 3,86 N/mm2 (tet10) neben dem Newton
    from statik3d.elements import solid as sl
    for typ, grenze_sv, grenze_u in (("hex8", 0.05e6, 1e-5), ("tet10", 1.0e6, None)):
        sv, uu, n = {}, {}, {}
        for weg, ver in (("anfangsdehnung", 0.0), ("tangente", 1e-300)):
            m = mr.modell(typ, 8, 4, 0.97 * h.p_grenz(), laststufen=4, verfestigung=ver,
                          iterationen=300)
            m.plastizitaet.toleranz = 1e-3
            res = solver.solve_static(m)
            sv[weg] = np.array([sl.von_mises(x) for x in np.asarray(res.solid_knoten["spannung"])])
            uu[weg] = np.asarray(res.u, float)
            n[weg] = res.info["plastizitaet"]
        d_sv = float(np.abs(sv["anfangsdehnung"] - sv["tangente"]).max())
        d_u = float(np.abs(uu["anfangsdehnung"] - uu["tangente"]).max() / np.abs(uu["tangente"]).max())
        check(f"{typ} 8 x 4 bei 0,97 p_L, Toleranz 1e-3: die Anfangsdehnung meldet „konvergiert“ "
              f"erst am Newton (σ_v auf {grenze_sv / 1e6:g} N/mm²"
              + (f", u auf {grenze_u:g})" if grenze_u else ")"),
              n["anfangsdehnung"].get("konvergiert") and d_sv < grenze_sv
              and (grenze_u is None or d_u < grenze_u),
              f"σ_v {d_sv / 1e6:.3f} N/mm², u {d_u:.1e}, "
              f"{n['anfangsdehnung'].get('iterationen')} Schritte")
    # Bitgleich bei ueblicher Verfestigung: mit und ohne Boden
    erg = []
    for boden in (pl.H_TANGENTE, 0.0):
        alt, pl.H_TANGENTE = pl.H_TANGENTE, boden
        try:
            m, _e, _L = _zugstab(1.2 * FY)
            m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=3,
                                             iterationen=25, toleranz=1e-6)
            erg.append(np.asarray(solver.solve_static(m).u, float))
        finally:
            pl.H_TANGENTE = alt
    check("Boden der Tangente bei 1 % Verfestigung: Ergebnis bitgleich",
          np.array_equal(erg[0], erg[1]))


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


def test_laufbuch_mit_fliessen():
    """Laufbuch je Lastfall (22.09.2026): mit Fließen rechnet derselbe
    Lastfall viele Kontaktläufe - am Drehlager zwölf. Die Summen in res.info
    sagen nicht, welcher Lauf gedeckelt war und ob der letzte dabei ist, aus
    dem u und σ stammen. Jetzt steht jeder Lauf einzeln da, mit seiner Art
    (Vorlauf, Laststufe, Newton, Abschluss), abgeleitet aus info['verlauf']
    der Fließ-Iteration, ohne deren Signatur zu ändern."""
    from statik3d import contact as ct
    from tests.test_kontakthalt import laufbuch_pruefen
    # Die verschachtelte Iteration mit ihrem Vorlauf; die gemeinsame (Vorgabe
    # seit dem 23.09.2026) steht unten
    m = _fliessendes_kontaktmodell()
    m.plastizitaet.kontakt = "verschachtelt"
    r = solver.solve_static(m)
    laeufe = laufbuch_pruefen(r, "Fließen", pruefe=check)
    if not laeufe:
        return
    arten = [e["art"] for e in laeufe]
    pz = r.info.get("plastizitaet") or {}
    check("erster Lauf der Vorlauf, letzter der Abschluss",
          arten[0] == "Vorlauf" and arten[-1] == "Abschluss", str(arten))
    check("je Laststufe ein Lauf 'Laststufe'", arten.count("Laststufe") == pz.get("laststufen"),
          f"{arten.count('Laststufe')} gegen {pz.get('laststufen')} Laststufen")
    check("die Newton-Läufe: je Schritt, der die Toleranz verfehlt, einer - mit Tangente",
          pz.get("konvergiert") and "Newton" in arten
          and arten.count("Newton") == int(pz["iterationen"]) - int(pz["laststufen"])
          and all(e["tangente"] for e in laeufe if e["art"] == "Newton"),
          f"{arten.count('Newton')} Newton-Läufe, {pz.get('iterationen')} Schritte")
    check("jeder spätere Lauf startet vom Zustand des Laufs davor",
          all(e["start_von_lauf"] == e["nr"] - 1 for e in laeufe[2:]),
          str([e["start_von_lauf"] for e in laeufe]))
    check("der Vorlauf gibt seinen Zustand an keinen Lauf weiter",
          laeufe[1]["start_von_lauf"] == laeufe[0]["start_von_lauf"]
          and not any(e["start_von_lauf"] == 1 for e in laeufe),
          str([e["start_von_lauf"] for e in laeufe]))

    # Gemeinsam (Vorgabe): kein Vorlauf, die Arten schreibt der Newton selbst
    # mit (plastizitaet._newton, info['aufrufe']) - auch die "Abnahme"
    mg = _fliessendes_kontaktmodell()
    rg = solver.solve_static(mg)
    lg = laufbuch_pruefen(rg, "Fließen gemeinsam", pruefe=check)
    ag = [e["art"] for e in lg]
    pzg = rg.info.get("plastizitaet") or {}
    check("gemeinsam: kein Vorlauf, erster Lauf die Laststufe, letzter der Abschluss",
          ag and "Vorlauf" not in ag and ag[0] == "Laststufe" and ag[-1] == "Abschluss"
          and ag.count("Laststufe") == pzg.get("laststufen"), str(ag))
    check("gemeinsam: jeder Lauf nach dem ersten startet vom Zustand des Laufs davor",
          all(e["start_von_lauf"] == e["nr"] - 1 for e in lg[1:]),
          str([e["start_von_lauf"] for e in lg]))
    check("gemeinsam: die Arten stehen so im Laufbuch, wie der Newton sie gerufen hat",
          [tuple(a) for a in pzg.get("aufrufe") or []]
          == [(e["art"], e.get("stufe"), e.get("schritt")) for e in lg],
          str([tuple(a) for a in pzg.get("aufrufe") or []][:4]))

    # Anfangsdehnung: je Schritt ein Aufruf, der erste einer Laststufe heisst so
    m3 = _fliessendes_kontaktmodell()
    m3.plastizitaet.verfahren = "anfangsdehnung"
    m3.plastizitaet.kontakt = "verschachtelt"
    r3 = solver.solve_static(m3)
    l3 = laufbuch_pruefen(r3, "Anfangsdehnung", pruefe=check)
    a3 = [e["art"] for e in l3]
    pz3 = r3.info.get("plastizitaet") or {}
    check("Anfangsdehnung: Vorlauf, je Schritt ein Lauf, Abschluss",
          a3 and a3[0] == "Vorlauf" and a3[-1] == "Abschluss"
          and len(a3) == int(pz3.get("iterationen", -9)) + 2
          and a3.count("Laststufe") == pz3.get("laststufen") and "Fliessschritt" in a3,
          f"{len(a3)} Läufe, {pz3.get('iterationen')} Schritte: {a3[:5]}")
    # ... und gemeinsam (Vorgabe): abgekuerzt wird dort nichts, aber der
    # Vorlauf entfaellt auch hier - bei bitgleichem Ergebnis
    m4 = _fliessendes_kontaktmodell()
    m4.plastizitaet.verfahren = "anfangsdehnung"
    r4 = solver.solve_static(m4)
    l4 = laufbuch_pruefen(r4, "Anfangsdehnung gemeinsam", pruefe=check)
    a4 = [e["art"] for e in l4]
    check("Anfangsdehnung gemeinsam: ohne Vorlauf und ohne abgekürzte Läufe, "
          "sonst dieselben Läufe und bitgleich",
          a4 == a3[1:] and not any(e.get("abgekuerzt") for e in l4)
          and np.array_equal(np.asarray(r4.u, float), np.asarray(r3.u, float)),
          f"{a4[:3]} gegen {a3[:3]}")

    # Mit Deckel 1: gedeckelte Läufe stehen einzeln da
    m2 = _fliessendes_kontaktmodell()          # vor dem Deckel bauen: es rechnet selbst
    alt_max = ct.MAX_CYCLES
    ct.MAX_CYCLES = 1
    try:
        r2 = solver.solve_static(m2)
    finally:
        ct.MAX_CYCLES = alt_max
    l2 = laufbuch_pruefen(r2, "Fließen, Deckel 1", pruefe=check)
    gedeckelt = [e["nr"] for e in l2 if e["grund"] == "deckel"]
    check("mit Deckel 1: mindestens ein Lauf gedeckelt, jeder mit Nummer und Art",
          gedeckelt and all(l2[n - 1]["art"] for n in gedeckelt),
          f"gedeckelt {gedeckelt} von {len(l2)}: " + str([l2[n - 1]["art"] for n in gedeckelt]))


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
               "gleit_anteil", "gleit_guete", "am_deckel")}
    # Zustand verbiegen, wie ihn eine Rechnung hinterlässt
    cs.phase, cs.cycles, cs.settle = 2, 7, 3
    cs.stabilising, cs.warm, cs.dF_slip = True, True, 1.5
    cs.gleit_anteil, cs.gleit_guete = 0.5, 0.02
    cs.am_deckel = True
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


def test_sechsflaechner_fliesst_unter_biegung():
    """Der hex8 muss unter reiner Biegung fliessen - und an der richtigen Stelle.

    Kragtraeger 200 x 200 mm, Endmoment als Kraeftepaar, M = 1,20 M_el. Die
    Randfaser traegt elastisch 282 N/mm2 gegen fy = 235, sie **muss** also
    fliessen; die plastische Zone reicht rechnerisch bis
    z/(h/2) = sqrt(3 - 2*1,20) = 0,775.

    Bis zum 20.09.2026 wertete die Plastizitaet in der **Elementmitte** aus.
    Dort ist die Spannung bei reiner Biegung null, und der Gradient der
    inkompatiblen Moden diag(-2r,-2s,-2t) verschwindet ebenfalls - die Mitte
    ist genau der eine Punkt, an dem der hex8 seine Biegung nicht zeigt.
    Gemessen: mit vier Lagen ueber die Hoehe meldete das Programm **0 von 20**
    fliessenden Elementen unter einem Moment, das den Querschnitt
    plastifiziert. Ohne den Umbau faellt diese Pruefung durch.
    """
    fy, E, nu = 235e6, 210e9, 0.3
    b = h = 0.2
    L = 1.0
    M_el = fy * b * h ** 2 / 6.0

    def rechnen(nz, weg, dicke=2):
        m = Model()
        m.add_material(Material("S", E=E, nu=nu, fy=fy))
        g = mesher.grid_box(m, "S", L, b, h, 5, 1, nz, typ="hex8")
        for k in g[0, :, :].ravel():
            m.fix(int(k), "all")
        ob = [int(k) for k in g[-1, :, -1].ravel()]
        un = [int(k) for k in g[-1, :, 0].ravel()]
        Pk = 1.2 * M_el / h
        for k in ob:
            m.load_node(k, Fx=+Pk / len(ob))
        for k in un:
            m.load_node(k, Fx=-Pk / len(un))
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=3,
                                         iterationen=60, toleranz=1e-6, verfahren=weg,
                                         dicke_punkte=dicke)
        return m, solver.solve_static(m)

    m4, r4 = rechnen(4, "tangente")
    fl4 = r4.info.get("plastisch", {})
    check("hex8 unter 1,20 M_el, vier Lagen: es fließt (vor dem 20.09.2026: 0 von 20)",
          len(fl4) > 0, f"{len(fl4)} von {len(m4.elements)}")
    check("… und die Newton-Iteration konvergiert",
          (r4.info.get("plastizitaet") or {}).get("konvergiert"),
          f"{(r4.info.get('plastizitaet') or {}).get('iterationen')} Schritte")
    # Nur die aeusseren Lagen duerfen fliessen: die plastische Zone reicht bis
    # 77,5 % der halben Hoehe, der aeusserste Gausspunkt der vierten Lage
    # liegt bei 89,4 %, der der dritten bei 60,6 %.
    innen = [i for i in fl4 if abs(float(m4.nodes[list(m4.elements[i].nodes)][:, 2].mean())
                                   - h / 2.0) < 0.5 * h / 2.0]
    check("… und nur außen, nicht in der Nähe der Nulllinie", not innen,
          f"{len(innen)} Elemente innerhalb der halben Höhe")
    ep4 = max(fl4.values()) if fl4 else 0.0
    # Die Randfaser waere voll plastisch bei (282-235)/H = 1,097 %; die
    # Gausspunkte liegen darunter, also muss eps_p deutlich kleiner sein.
    check("… und die plastische Dehnung bleibt in der Größenordnung des Randfaserwerts",
          0.0 < ep4 < 1.097e-2, f"ε_p,eq max {ep4 * 100:.4f} % (Randfaser 1,097 %)")

    # Zweiter Weg, dieselbe Antwort: die Anfangsdehnungs-Iteration rechnet
    # ohne Tangente. Stimmen beide ueberein, ist es keine gemeinsame
    # Verwechslung der Tangente.
    m4b, r4b = rechnen(4, "anfangsdehnung")
    fl4b = r4b.info.get("plastisch", {})
    check("beide Verfahren finden dieselben fließenden Elemente",
          set(fl4) == set(fl4b), f"{len(fl4)} gegen {len(fl4b)}")
    nahe("… und dieselbe größte plastische Dehnung",
         max(fl4b.values()) if fl4b else 0.0, ep4, 0.05)

    # Feiner: acht Lagen fassen die Zone mit zwei Lagen, es fliesst mehr
    m8, r8 = rechnen(8, "tangente")
    fl8 = r8.info.get("plastisch", {})
    check("acht Lagen fassen die plastische Zone besser als vier",
          len(fl8) / len(m8.elements) > 0.0 and max(fl8.values()) > ep4,
          f"{len(fl8)}/{len(m8.elements)}, ε_p max {max(fl8.values()) * 100:.4f} % "
          f"gegen {ep4 * 100:.4f} % bei vier Lagen")

    # Eine Lage mit 2x2x2 Gausspunkten kann es nicht sehen: der aeusserste
    # Punkt liegt bei 57,7 % der halben Hoehe und traegt 0,577 * 282 = 163
    # N/mm2, also unter fy. Darum rechnet der hex8 mit Fliessen seit dem
    # 22.09.2026 fuenf Lobatto-Punkte ueber die Dicke (Plastizitaet.
    # dicke_punkte, Auftrag A2) - dann fliesst auch eine Lage, an der Faser.
    m1, r1 = rechnen(1, "tangente", dicke=2)
    check("eine Lage mit 2x2x2 fließt nicht - der äußerste Gaußpunkt liegt bei 57,7 %",
          not r1.info.get("plastisch", {}),
          "0,577 · 282 = 163 N/mm² < fy = 235 N/mm²")
    m1, r1 = rechnen(1, "tangente", dicke=5)
    check("eine Lage mit fünf Lobatto-Punkten über die Dicke fließt",
          len(r1.info.get("plastisch", {})) > 0,
          f"{len(r1.info.get('plastisch', {}))} von {len(m1.elements)}")


def test_plastische_randfaser_mit_wenigen_lagen():
    """A2 (22.09.2026): σ_v und ε_p,eq an der Randfaser gegen die Momenten-
    Krümmungs-Beziehung des Rechteckquerschnitts - mit einer und zwei Lagen.

    Kragträger 1,0 x 0,2 x 0,2 m, Endmoment 1,20 M_el als lineare
    Normalspannung, fy = 235, E_t/E = 2 %. Die Randfaser trägt nach der
    bilinearen Momenten-Krümmungs-Beziehung 236,35 N/mm² bei ε_p = 0,0315 %.
    Gelesen wird der Integrationspunkt der obersten Lage bei x ≈ L/2 - mit
    Lobatto liegt er **auf** der Oberfläche. Gemessen 22.09.2026: eine Lage
    -0,20 N/mm² (ε_p -15 %), zwei Lagen -0,20 (-15 %)."""
    from scipy.optimize import brentq
    from statik3d.elements import solid as sl
    from tests import pruefkoerper as pk
    fy, Em, nu, r = 235e6, 210e9, 0.3, 0.02
    b = h = 0.2
    L = 1.0
    M = 1.2 * fy * b * h ** 2 / 6.0
    ey = fy / Em

    def sig(eps):
        a = abs(eps)
        return np.sign(eps) * (Em * a if a <= ey else fy + r * Em * (a - ey))
    z = np.linspace(-h / 2, h / 2, 4001)
    kappa = brentq(lambda k: b * np.trapezoid(np.array([sig(k * x) for x in z]) * z, z) - M,
                   1e-9, 1e-1)
    sf = sig(kappa * h / 2)
    epf = kappa * h / 2 - sf / Em
    for lagen in (1, 2):
        m, _ids = pk.quader("hex8", 5, 1, lagen, L, b, h, fy=fy, nu=nu)
        for k in [n for n in range(m.nn) if abs(m.nodes[n, 0]) < 1e-9]:
            m.fix(int(k), "all")
        seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - L) < 1e-9)))
        I = b * h ** 3 / 12
        pk.spannung_auf_seiten(m, seiten, lambda x: (M * (x[2] - h / 2) / I, 0.0, 0.0))
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=r, laststufen=1, iterationen=30,
                                         toleranz=1e-9)
        res = solver.solve_static(m)
        u = np.asarray(res.u, float).ravel()
        el = pl._solid_elemente(m, None)
        # Eine Laststufe, einachsig proportional: der Endzustand ist die
        # Rueckfuehrung aus dem Anfangszustand bei der Endverschiebung
        _F, zst, _i = pl.schritt(m, u, pl.Zustand(), m.plastizitaet, el)
        d = pl._stapel(m, el, "hex8")[0]
        op = d["op"]
        Ue = u[op.dofs()]
        eps_p = np.stack([np.asarray(zst.eps_p.get(int(i), np.zeros((op.P, 6)))) for i in op.idx],
                         axis=1)
        alpha = pl._eas_alpha(d["eas"], d["lam"], d["mu"], eps_p, d["lasten"], Ue)
        D = sl.D_matrix(Em, nu)
        best = None
        for a, i in enumerate(op.idx):
            X = m.nodes[m.elements[int(i)].nodes]
            for p in range(op.P):
                xp = sl.hex8_N_dN(*op.xi[p])[0] @ X
                key = (-round(xp[2], 9), abs(xp[0] - L / 2))
                if best is None or key < best[0]:
                    eps = sl.dehnung_mit_moden(op.teil([a]), p, Ue[a:a + 1], alpha[a:a + 1])[0]
                    best = (key, xp, D @ (eps - eps_p[p, a]),
                            float(np.asarray(zst.eps_p_eq[int(i)])[p]) if int(i) in zst.eps_p_eq else 0.0)
        _k, xp, s, ep = best
        sv = sl.von_mises(s)
        check(f"hex8, {lagen} Lage(n), 5 Lobatto-Punkte: σ_v an der Randfaser auf 1 N/mm²",
              abs(xp[2] - h) < 1e-12 and abs(sv - sf) < 1e6,
              f"{sv / 1e6:.3f} gegen {sf / 1e6:.3f} N/mm² (z = {xp[2]:.3f} m), "
              f"ε_p,eq {ep * 100:.4f} % gegen {epf * 100:.4f} %")
        check(f"hex8, {lagen} Lage(n): ε_p,eq an der Randfaser auf 20 % der Momenten-Krümmungs-Lösung",
              abs(ep - epf) < 0.2 * epf, f"{(ep / epf - 1) * 100:+.1f} %")


def test_tet4_wertet_in_seinem_gausspunkt_aus():
    """Beim tet4 ist der Auswertepunkt **der** Gausspunkt - der Umbau auf
    Gausspunkte darf am Tetraeder nichts aendern (das Drehlager rechnet mit
    645.934 davon)."""
    import numpy as _np
    from statik3d.elements import solid as _sl
    _fn, GP, W = _sl._ISO["tet4"]
    check("tet4 hat genau einen Gaußpunkt", len(GP) == 1, f"{len(GP)}")
    check("… und er ist der Auswertepunkt der Spannung",
          _np.allclose(_np.asarray(GP[0], float),
                       _np.asarray(_sl.AUSWERTEPUNKTE["tet4"][0], float)),
          f"{tuple(GP[0])} gegen {_sl.AUSWERTEPUNKTE['tet4'][0]}")
    check("hex8 dagegen hat acht Gaußpunkte, und keiner ist die Mitte",
          len(_sl._ISO["hex8"][1]) == 8
          and not any(_np.allclose(p, 0.0) for p in _sl._ISO["hex8"][1]),
          f"{len(_sl._ISO['hex8'][1])} Punkte, Auswertepunkt {_sl.AUSWERTEPUNKTE['hex8'][0]}")


def _drehlagerartiges_modell():
    """Zwei Koerper mit einer Reibfuge, wie am Drehlager (23.09.2026): ein
    Stempel 0,2 x 0,2 x 0,2 m aus tet4 mit gewoelbter Unterseite (Spalt bis
    0,1 mm am Rand, die Beruehrflaeche waechst mit der Last) auf einem Sockel
    0,6 x 0,6 x 0,3 m, Fuge mit mu 0,1, Sockel unten fest, Stempel oben
    seitlich gehalten. Die Auflast sitzt zu 60 % auf der Seite x > 0,3 und ist
    so gross, dass die elastische Vergleichsspannung fy/0,4 erreicht - unter
    der gedrueckten Kante fliesst der Sockel. Einstellungen wie am Drehlager:
    E_t/E 1 %, drei Laststufen, Toleranz 1e-3."""
    def aufbau(P):
        m = Model("Stempel")
        m.add_material(Material("S235", E=210e9, nu=0.3, rho=7850))
        s = mesher.grid_box(m, "S235", 0.6, 0.6, 0.3, 6, 6, 3, typ="tet4")
        n_sockel = len(m.elements)
        for n in s[:, :, 0].ravel():
            m.fix(int(n), "all")
        p = mesher.grid_box(m, "S235", 0.2, 0.2, 0.2, 4, 4, 4, origin=(0.2, 0.2, 0.3), typ="tet4")
        X = m.nodes
        for n in p.ravel():
            x, y, z = X[int(n)]
            X[int(n), 2] = z + 5e-5 * ((x - 0.3) ** 2 + (y - 0.3) ** 2) / 0.01 * (1.0 - (z - 0.3) / 0.2)
        m.add_contact_pair("Stempel/Sockel", [int(n) for n in p[:, :, 0].ravel()],
                           list(range(n_sockel)), mu=0.1)
        oben = [int(n) for n in p[:, :, -1].ravel()]
        for n in oben:
            m.fix(n, [0, 1])
        lc = m.add_load_case("LF1")
        lc.gravity = [0, 0, 0]
        xs = np.asarray(m.nodes, float)[oben, 0]
        rechts = [n for n, x in zip(oben, xs) if x > 0.3 + 1e-9]
        links = [n for n, x in zip(oben, xs) if x < 0.3 - 1e-9]
        for n in rechts:
            m.load_node(n, Fz=-P * 0.6 / len(rechts))
        for n in links:
            m.load_node(n, Fz=-P * 0.4 / len(links))
        return m

    m0 = aufbau(1.0)
    q0 = max(pl.vergleichsspannung(np.asarray(v, float))
             for v in solver.solve_static(m0).solid_res.values())
    m = aufbau(235e6 / (0.4 * q0))
    m.materials["S235"].fy = 235e6
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=3,
                                     iterationen=25, toleranz=1e-3)
    return m


def _gequetschter_block():
    """tests/test_solver_ext.test_probelauf_und_kennzahlen: Block 0,4 m auf
    starrer Platte, mu 0,3, 60 MN Auflast (weit ueber der Quetschlast von
    37,6 MN) und 9 MN quer; 2 %, zwei Laststufen, Toleranz 1e-4. Alle neun
    Kontaktbedingungen gleiten, ε_p erreicht 12 %."""
    from statik3d.model import ShellProp
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
    for n in oben:
        m.load_node(n, Fz=-60e6 / len(oben), Fx=9e6 / len(oben))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2,
                                     iterationen=40, toleranz=1e-4)
    return m


def _gezaehlt(m):
    """solve_static mit gezaehlten Zerlegungen (Aufrufe von LinearSolver)."""
    n = {"z": 0}
    alt = solver.LinearSolver.__init__

    def zaehlend(self, *a, **kw):
        n["z"] += 1
        alt(self, *a, **kw)

    solver.LinearSolver.__init__ = zaehlend
    try:
        r = solver.solve_static(m)
    finally:
        solver.LinearSolver.__init__ = alt
    return r, n["z"]


def _vergleichsspannungen(r):
    return np.array([pl.vergleichsspannung(np.asarray(r.solid_res[i], float))
                     for i in sorted(r.solid_res)])


_VERGLEICH: dict = {}


def _gemeinsam_gegen_verschachtelt():
    """Je Modell (verschachtelt, gemeinsam): (Ergebnis, Zerlegungen) - einmal
    gerechnet, von T1 bis T3 gelesen."""
    if not _VERGLEICH:
        for titel, bau in (("Block mit Reibung", _fliessendes_kontaktmodell),
                           ("zwei Körper, Fuge mit µ 0,1", _drehlagerartiges_modell)):
            m_alt = bau()
            m_alt.plastizitaet.kontakt = "verschachtelt"
            alt = _gezaehlt(m_alt)
            neu = _gezaehlt(bau())
            _VERGLEICH[titel] = (alt, neu)
    return _VERGLEICH


def test_gemeinsame_iteration_spart_zerlegungen():
    """T1 (23.09.2026): Fließen und Kontakt gemeinsam iteriert - innerhalb
    einer Laststufe rechnet jeder Newton-Schritt nur einen Kontaktschritt,
    die Stufe endet mit voll auskonvergiertem Kontakt - braucht deutlich
    weniger Zerlegungen als die verschachtelte Iteration, in der jeder
    Newton-Schritt den Kontakt auskonvergiert. Gezählt werden die Aufrufe
    von LinearSolver, nicht die Buchführung des Laufbuchs."""
    for titel, ((_r_alt, z_alt), (_r_neu, z_neu)) in _gemeinsam_gegen_verschachtelt().items():
        check(f"{titel}: gemeinsam höchstens 70 % der Zerlegungen von verschachtelt",
              z_neu <= 0.70 * z_alt, f"{z_neu} gegen {z_alt} ({z_neu / max(z_alt, 1) * 100:.0f} %)")


def test_gemeinsame_iteration_rechnet_dasselbe():
    """T2 (23.09.2026): dasselbe Ergebnis wie verschachtelt - Vergleichs-
    spannung je Element auf 1 N/mm² (und auf 1 ‰ der größten), Verschiebung
    auf 1e-4 der größten, Auflagerkräfte im Gleichgewicht mit der Last, beide
    Rechnungen „konvergiert“. Vorbedingung: die gemeinsame Rechnung ist
    wirklich eine andere - ohne Vorlauf, und am Modell mit zwei Körpern
    unterwegs abgekürzt -, sonst vergliche der Test zweimal dasselbe. Am
    Block ändert sich der Kontakt in keinem Newton-Schritt: jeder
    abgekürzte Lauf ist dort nach seinem einen Schritt auskonvergiert."""
    from statik3d.gui.rechenliste import zustand_aus_info
    for titel, ((r_alt, _z), (r_neu, _z2)) in _gemeinsam_gegen_verschachtelt().items():
        arten_alt = [e["art"] for e in (r_alt.info.get("laeufe") or [])]
        arten_neu = [e["art"] for e in (r_neu.info.get("laeufe") or [])]
        check(f"{titel}: die gemeinsame Rechnung ist eine andere - ohne Vorlauf",
              "Vorlauf" in arten_alt and "Vorlauf" not in arten_neu,
              f"verschachtelt {arten_alt[:2]}, gemeinsam {arten_neu[:2]}")
        if titel.startswith("zwei"):
            ab = [e["nr"] for e in (r_neu.info.get("laeufe") or []) if e.get("grund") == "abgekuerzt"]
            check(f"{titel}: die gemeinsame Rechnung kürzt unterwegs ab", ab,
                  f"{len(ab)} abgekürzte von {len(arten_neu)} Läufen")
        za, zn = zustand_aus_info(r_alt.info), zustand_aus_info(r_neu.info)
        check(f"{titel}: beide konvergiert", za == "konvergiert" and zn == "konvergiert",
              f"verschachtelt: {za}; gemeinsam: {zn}")
        sa, sn = _vergleichsspannungen(r_alt), _vergleichsspannungen(r_neu)
        d = float(np.abs(sa - sn).max())
        check(f"{titel}: σ_v je Element auf 1 N/mm² und 1 ‰ der größten gleich",
              d <= 1e6 and d <= 1e-3 * float(sa.max()),
              f"max |Δσ_v| {d / 1e6:.4f} N/mm² bei σ_v,max {float(sa.max()) / 1e6:.2f} N/mm²")
        ua, un = np.asarray(r_alt.u, float)[:, :3], np.asarray(r_neu.u, float)[:, :3]
        du = float(np.abs(ua - un).max()) / float(np.abs(ua).max())
        check(f"{titel}: Verschiebungen auf 1e-4 der größten gleich", du <= 1e-4, f"{du:.2e}")
        F = solver.case_loads(r_neu.model, {list(r_neu.model.load_cases)[0]: 1.0})[0]
        F3 = np.asarray(F, float)[:r_neu.model.nn * 6].reshape(-1, 6)[:, :3].sum(axis=0)
        Ra = np.asarray(r_alt.reactions, float)[:, :3].sum(axis=0)
        Rn = np.asarray(r_neu.reactions, float)[:, :3].sum(axis=0)
        bez = float(np.abs(F3).max())
        check(f"{titel}: Auflagerkräfte beider im Gleichgewicht mit der Last",
              float(np.abs(Rn + F3).max()) <= 1e-6 * bez and float(np.abs(Ra - Rn).max()) <= 1e-6 * bez,
              f"Σ R gemeinsam {Rn}, verschachtelt {Ra}, Last {F3}")


def _rest_am_ende(m):
    """Rechnen und hinterher nachprüfen: passt F_p zum End-u? Die Rückführung
    von der Basis der letzten Laststufe (das Argument des letzten
    Tangentenschritts) an der End-Verschiebung gegen das zurückgegebene F_p,
    bezogen auf |F| wie das Kriterium der Iteration. Unabhängig von dem, was
    die Iteration selbst darüber meldet."""
    spur = {}
    alt_schritt, alt_iteration = pl.schritt, pl.iteration

    def schritt(model, u, zustand, einst, elemente, log=None, tangente=False):
        if tangente:
            spur["basis"], spur["elemente"] = zustand, elemente
        return alt_schritt(model, u, zustand, einst, elemente, log, tangente)

    def iteration(model, F, *a, **kw):
        erg = alt_iteration(model, F, *a, **kw)
        spur["erg"], spur["F"] = erg, np.asarray(F, float)
        return erg

    pl.schritt, pl.iteration = schritt, iteration
    try:
        r = solver.solve_static(m)
    finally:
        pl.schritt, pl.iteration = alt_schritt, alt_iteration
    u, _z, F_p, _info = spur["erg"]
    F_p_ende, _z2, _i2 = alt_schritt(m, u, spur["basis"], m.plastizitaet, spur["elemente"])
    return r, float(np.linalg.norm(F_p_ende - F_p)) / float(np.linalg.norm(spur["F"]))


def test_gemeinsame_iteration_kein_falsches_konvergiert():
    """T3 (23.09.2026): „konvergiert“ nur, wenn der letzte Schritt mit voll
    auskonvergiertem Kontakt gerechnet ist und beide Kriterien dort gelten.

    (a) Abgekürzte Läufe stehen im Laufbuch (Grund „abgekuerzt“) und
    verderben den Lastfall nicht; jede Laststufe endet mit einem vollen Lauf,
    der letzte Lauf ist der volle Abschluss. (b) Deckel 2: der Abschluss wird
    gedeckelt - der Lastfall heißt „NICHT konvergiert“. (c) Plastizität am
    End-u: am gequetschten Block (tests/test_solver_ext) änderte der volle
    Kontaktlauf des Abschlusses den Zustand, und F_p passte am Ende nicht
    mehr zum u (gemessen 23.09.2026: Rest 2,5e-4 bei Toleranz 1e-4) - bis
    dahin trotzdem „konvergiert“, in beiden Verfahren."""
    from statik3d import contact as ct
    from statik3d.gui.rechenliste import zustand_aus_info
    from tests.test_kontakthalt import laufbuch_pruefen
    (_alt, (r, _z)) = _gemeinsam_gegen_verschachtelt()["zwei Körper, Fuge mit µ 0,1"]
    laeufe = laufbuch_pruefen(r, "gemeinsam", pruefe=check)
    ab = [e for e in laeufe if e.get("grund") == "abgekuerzt"]
    check("(a) abgekürzte Läufe stehen einzeln im Laufbuch, als nicht konvergiert mit Grund",
          ab and all(not e["konvergiert"] and e.get("abgekuerzt") for e in ab),
          f"{len(ab)} von {len(laeufe)}")
    check("(a) … und verderben den Lastfall nicht",
          r.info.get("contact_converged") is True
          and int(r.info.get("contact_laeufe_nicht_konvergiert", -1)) == 0
          and int(r.info.get("contact_laeufe_abgekuerzt", -1)) == len(ab)
          and zustand_aus_info(r.info) == "konvergiert",
          f"{zustand_aus_info(r.info)}, nicht konvergiert "
          f"{r.info.get('contact_laeufe_nicht_konvergiert')}")
    zeile = [x for x in r.summary().splitlines() if x.startswith("Kontakt-Iterationen")]
    check("(a) die Zusammenfassung nennt die abgekürzten Läufe",
          zeile and f"({len(ab)} davon abgekürzt)" in zeile[0], zeile[0] if zeile else "keine Zeile")
    stufenende =[laeufe[i - 1] for i, e in enumerate(laeufe) if i and e["art"] == "Laststufe"]
    check("(a) jede Laststufe endet mit einem vollen Lauf, der letzte ist der volle Abschluss",
          laeufe[-1]["art"] == "Abschluss" and laeufe[-1]["konvergiert"]
          and not laeufe[-1].get("abgekuerzt")
          and all(not e.get("abgekuerzt") for e in stufenende),
          str([(e["nr"], e["art"], e["grund"]) for e in stufenende + [laeufe[-1]]]))

    m2 = _drehlagerartiges_modell()          # vor dem Deckel bauen: es rechnet selbst
    alt_max = ct.MAX_CYCLES
    ct.MAX_CYCLES = 2
    try:
        r2 = solver.solve_static(m2)
    finally:
        ct.MAX_CYCLES = alt_max
    l2 = r2.info.get("laeufe") or []
    check("(b) Deckel 2: auch hier wird unterwegs abgekürzt",
          any(e.get("grund") == "abgekuerzt" for e in l2), f"{len(l2)} Läufe")
    check("(b) Deckel 2: der Abschluss ist gedeckelt - „NICHT konvergiert“",
          l2 and l2[-1]["grund"] == "deckel" and r2.info.get("contact_letzter_lauf_konvergiert") is False
          and r2.info.get("contact_converged") is False
          and zustand_aus_info(r2.info).startswith("NICHT konvergiert"),
          f"letzter Lauf {l2[-1]['art'] if l2 else '-'} / {l2[-1]['grund'] if l2 else '-'}: "
          f"{zustand_aus_info(r2.info)}")

    tol = 1e-4
    for kontakt in ("verschachtelt", "gemeinsam"):
        m3 = _gequetschter_block()
        m3.plastizitaet.kontakt = kontakt
        r3, rest = _rest_am_ende(m3)
        z3 = zustand_aus_info(r3.info)
        check(f"(c) gequetschter Block, {kontakt}: „konvergiert“ nur, wenn F_p am End-u passt",
              rest <= tol if z3 == "konvergiert" else z3.startswith("NICHT konvergiert"),
              f"{z3}; Rest am End-u {rest:.2e} (Toleranz {tol:g})")


def test_ruecknahme_der_schlussabnahme():
    """T4 (23.09.2026): Rücknahmeprobe zu T3 (c). Ohne die Schlussabnahme -
    Prüfung der Plastizität an der Lösung mit dem voll auskonvergierten
    Kontakt des Abschlusses - meldet der gequetschte Block wieder
    „konvergiert“, obwohl F_p dort nicht zum u passt. Die Prüfung ist also
    das, was die falsche Meldung verhindert, nicht ein Zufall der Rechnung."""
    from statik3d.gui.rechenliste import zustand_aus_info
    alt = pl._schlussabnahme
    pl._schlussabnahme = lambda rest, toleranz: True
    try:
        m = _gequetschter_block()
        m.plastizitaet.kontakt = "verschachtelt"
        r, rest = _rest_am_ende(m)
    finally:
        pl._schlussabnahme = alt
    check("ohne Schlussabnahme: „konvergiert“, obwohl F_p am End-u um mehr als die Toleranz abweicht",
          zustand_aus_info(r.info) == "konvergiert" and rest > 1e-4,
          f"{zustand_aus_info(r.info)}; Rest {rest:.2e} > 1e-4")


def test_gemeinsam_aendert_nichts_ohne_beides():
    """T5 (23.09.2026): die Einstellung wirkt nur, wo Fließen UND Kontakt
    zusammenkommen. Kontakt ohne Plastizität und Plastizität ohne Kontakt
    rechnen mit „gemeinsam“ und „verschachtelt“ bitgleich (Verschiebungen,
    Auflagerkräfte, Kontaktkräfte), je an zwei Modellen. Dass beide auch
    bitgleich zum Stand vor dem Umbau sind, belegt die Messung gegen 6a961e5
    (sha256), nicht dieser Test - er läuft auf einem Stand."""
    def rechne(m, kontakt):
        m.plastizitaet.kontakt = kontakt
        r = solver.solve_static(m)
        cf = getattr(r, "contact_forces", None)
        return (np.asarray(r.u, float), np.asarray(r.reactions, float),
                np.asarray(np.zeros((0, 3)) if cf is None else cf, float),
                np.array(sorted((r.info.get("plastisch") or {}).items()), float).reshape(-1, 2))

    def nur_kontakt_stempel():
        m = _drehlagerartiges_modell()
        m.plastizitaet.an = False
        return m

    def zugwuerfel():
        m, _n = _wuerfel_zug(1.1 * FY)
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2,
                                         iterationen=60, toleranz=1e-8)
        return m

    def kragtraeger_tet4():
        m = Model()
        m.add_material(Material("S", E=E, nu=NU, fy=235e6))
        g = mesher.grid_box(m, "S", 1.0, 0.2, 0.2, 6, 2, 2, typ="tet4")
        for k in g[0, :, :].ravel():
            m.fix(int(k), "all")
        # 1 MN: elastisch 1,5 fy am Einspannrand, 48 von 120 Elementen fliessen
        for k in g[-1, :, -1].ravel():
            m.load_node(int(k), Fz=-1.0e6 / len(g[-1, :, -1].ravel()))
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=3,
                                         iterationen=25, toleranz=1e-3)
        return m

    for titel, bau in (("Kontakt ohne Plastizität: Block mit Reibung", block_friction_example),
                       ("Kontakt ohne Plastizität: Stempel auf Sockel", nur_kontakt_stempel),
                       ("Plastizität ohne Kontakt: Zugwürfel hex8", zugwuerfel),
                       ("Plastizität ohne Kontakt: Kragträger tet4", kragtraeger_tet4)):
        a = rechne(bau(), "verschachtelt")
        b = rechne(bau(), "gemeinsam")
        # Ohne Kontakt sind die Kontaktkraefte NaN (nicht vorhanden) - NaN an
        # derselben Stelle gilt als gleich
        check(f"{titel}: gemeinsam und verschachtelt bitgleich "
              f"({len(a[3])} Elemente fließen)",
              all(np.array_equal(x, y, equal_nan=True) for x, y in zip(a, b)),
              str([float(np.nanmax(np.abs(x - y))) if x.shape == y.shape and x.size else x.shape
                   for x, y in zip(a, b)]))


def main():
    for t in (test_rueckfuehrung, test_tangente_ist_die_ableitung_der_rueckfuehrung,
              test_blockweise_wie_die_schleife,
              test_blockweise_fuer_jeden_elementtyp, test_zugversuch,
              test_dk_symmetrisch_weich_und_bei_tet4_exakt,
              test_tangente_exakt_fuer_jeden_typ, test_newton_konvergiert_quadratisch,
              test_newton_bei_kleiner_verfestigung, test_rohr_ideal_plastisch_nach_hill,
              test_anfangsdehnung_trifft_den_newton,
              test_zusatzsteifigkeit_gehoert_in_den_schluessel_der_faktorisierung,
              test_protokoll_sagt_was_die_runde_bewegt_und_kostet,
              test_kennzahlen_zaehlen_alle_laeufe_des_lastfalls,
              test_laufbuch_mit_fliessen,
              test_kontaktsystem_wird_wiederverwendet,
              test_initialize_setzt_den_ganzen_zustand_zurueck,
              test_sechsflaechner_fliesst_unter_biegung,
              test_plastische_randfaser_mit_wenigen_lagen,
              test_tet4_wertet_in_seinem_gausspunkt_aus,
              test_loeser, test_kombination, test_kontakt,
              test_gemeinsame_iteration_spart_zerlegungen,
              test_gemeinsame_iteration_rechnet_dasselbe,
              test_gemeinsame_iteration_kein_falsches_konvergiert,
              test_ruecknahme_der_schlussabnahme,
              test_gemeinsam_aendert_nichts_ohne_beides):
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
