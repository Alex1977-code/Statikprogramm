"""Die Fliesspruefung sieht die Anfangsspannung einer Vorspannung als Koerper.

Eine Vorspannkraft in einem Volumenkoerper (model.Vorspannung, art
"koerper") wirkt als einachsige Anfangsspannung σ₀ = −F_v/A · a⊗a; die
wahre Spannung ist σ = D(ε − ε_p) − σ₀ (assemble.solid_prestress, im
Spannungsnachlauf seit jeher so). Bis zum 10.10.2026 pruefte die
Rueckfuehrung (plastizitaet._schritt_teil, _schritt_schleife) aber
σ_trial = D(ε − ε_p) ohne σ₀. Bei einer Temperatur im Volumen schadet das
nicht - die Dehnung ist isotrop, von Mises sieht nur den Deviator -, eine
einachsige Bolzenvorspannung ist aber deviatorisch. Ein vorgespannter
Volumenbolzen wurde darum mit der falschen Vergleichsspannung auf Fliessen
geprueft: in der Pruefung unten fliesst er am alten Stand gar nicht, obwohl
die angezeigte Spannung ueber f_y liegt.

Gepruefter Bolzen: ein Hexaeder 1 x 1 x 1 m (S355, Verfestigung E_t/E = 2 %),
unten in z gehalten, als Koerper mit F_v = 0,98 f_y A vorgespannt, oben ein
Klemmpaket aus vier Fachwerkstaeben zum Boden (zusammen 19-mal so steif wie
der Bolzen) und eine aeussere Zuglast P auf den Kopf. Geschlossene Loesung
(einachsig, das Verspannungsschaubild): elastisch traegt der Bolzen
σ = (k_K F_v + k_B P) / ((k_B + k_K) A), also ohne Last 0,931 f_y; er
beginnt bei P_y = F_v + (k_B + k_K)·(L/E)·(f_y − F_v/A) = 1,38 f_y A zu
fliessen, danach bilinear.

Geprueft: bei 0,99 P_y fliesst nichts, bei 1,01 P_y und 1,3 P_y fliesst der
Bolzen; Kopfverschiebung, angezeigte Spannung σ_zz, Vergleichsspannung und
ε_p treffen die geschlossene Loesung, die Lager tragen die Last, und
Bolzenspannung plus Klemmkraft halten der Last das Gleichgewicht. Dazu die
Rueckfuehrung selbst (ohne Verschiebung fliesst ein Punkt mit
σ₀ = −1,2 f_y), Block und Schleife gleich, und ΔK bleibt die Ableitung.

Aufruf:  python -m tests.test_vorspannung_fliessen
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import plastizitaet as pl, solver                    # noqa: E402
from statik3d.model import Material, Model, NodalLoad, Section    # noqa: E402
from statik3d.model import Volumenkoerper                          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def nahe(name, ist, soll, tol, einheit=""):
    ist, soll = float(ist), float(soll)
    abw = abs(ist - soll) / (abs(soll) if abs(soll) > 1e-14 else 1.0)
    return check(name, abw <= tol, f"ist {ist:.6g} soll {soll:.6g} ({abw * 100:.3g} %) {einheit}")


E, NU, FY, ET = 210e9, 0.3, 355e6, 0.02
A, L = 1.0, 1.0             # Bolzen: Querschnitt [m2], Laenge [m]
FV = 0.98 * FY * A          # Vorspannkraft [N]
KK = 19.0                   # Klemmpaket k_K / k_B
LK = 2.0                    # Laenge der Klemmstaebe [m]
AK = KK * E * A / L * LK / (4.0 * E)     # Querschnitt je Klemmstab [m2]
H = E * ET / (1.0 - ET)     # Verfestigungsmodul zu E_t/E (Plastizitaet.H)
KB = E * A / L
P_Y = FV + (KB + KK * KB) * (FY - FV / A) * L / E   # Fliessbeginn: 1,38 f_y A


def _geschlossen(P):
    """(w Kopf nach oben [m], σ_zz Bolzen [Pa], ε_p) - einachsig, bilinear."""
    kk = KK * KB
    w = (P - FV) / (KB + kk)
    sig = E * w / L + FV / A
    if sig <= FY:
        return w, sig, 0.0
    Et = ET * E
    # σ = f_y + E_t (ε_mech − f_y/E), ε_mech = w/L + F_v/(E A); P = σ A + k_K w
    w = (P - FY * A - Et * A * (FV / (E * A) - FY / E)) / (Et * A / L + kk)
    sig = FY + Et * (w / L + FV / (E * A) - FY / E)
    return w, sig, (sig - FY) / H


def _bolzen(P, stufen=3):
    m = Model("Bolzen")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    m.add_material(Material("Klemmpaket", E=E, nu=NU, rho=7850))
    m.add_section(Section.circle("K", float(np.sqrt(4 * AK / np.pi))))
    n = [m.add_node(x, y, z) for z in (0.0, L) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    b = m.add_element("hex8", n, "S355", "")
    m.koerper["Bolzen"] = Volumenkoerper("Bolzen", flaechen=[], material="S355", elemente=[b])
    for i in n[:4]:
        m.fix(i, [2])
    m.fix(n[0], [0, 1])
    m.fix(n[1], [1])
    m.fix(n[3], [0])
    boden = [m.add_node(x, y, L - LK) for x, y in ((0, 0), (1, 0), (1, 1), (0, 1))]
    for g, t in zip(boden, n[4:]):
        m.fix(g, "all")
        m.add_element("truss", [g, t], "Klemmpaket", "K")
    m.add_load_case("LF1").gravity = [0, 0, 0]
    m.add_vorspannung("Bolzen", FV, achse=[0, 0, 1], case="LF1")
    for i in n[4:]:
        m.case("LF1").nodal_loads.append(NodalLoad(i, [0, 0, P / 4.0, 0, 0, 0]))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=ET, laststufen=stufen, iterationen=60,
                                     toleranz=1e-8)
    return m, b, n[4:], boden


def _vm(s):
    return pl.vergleichsspannung(np.asarray(s, float))


def test_bolzen_geschlossen():
    print(f"--- Bolzen: F_v = {FV / 1e6:.2f} MN, P_y = {P_Y / 1e6:.2f} MN ---")
    for anteil in (0.0, 0.99, 1.01, 1.3):
        P = anteil * P_Y
        m, b, kopf, boden = _bolzen(P)
        r = solver.solve_static(m)
        w_s, sig_s, ep_s = _geschlossen(P)
        was = f"P = {anteil:g} P_y"
        pz = r.info.get("plastizitaet") or {}
        soll_fl = 1 if anteil > 1.0 else 0
        sig_el = E * (P - FV) / (KB + KK * KB) / L + FV / A       # ohne Fliessen
        check(f"{was}: der Bolzen fließt {'' if soll_fl else 'nicht '}(elastisch σ = {sig_el / FY:.4f} f_y)",
              pz.get("konvergiert") and pz.get("fliessend") == soll_fl,
              f"fließend {pz.get('fliessend')}, konvergiert {pz.get('konvergiert')}")
        u = np.asarray(r.u, float).reshape(-1, 6)
        w = float(u[kopf, 2].mean())
        nahe(f"{was}: Kopfverschiebung = geschlossene Lösung", w, w_s, 1e-6, "m")
        s = np.asarray(r.solid_res[b], float)
        nahe(f"{was}: angezeigte σ_zz = geschlossene Lösung", s[2], sig_s, 1e-6, "Pa")
        nahe(f"{was}: angezeigte Vergleichsspannung = |σ_zz| (einachsig)", _vm(s), abs(sig_s), 1e-6, "Pa")
        ep = float(pz.get("eps_p_max", 0.0) or 0.0)
        if soll_fl:
            nahe(f"{was}: ε_p,eq = (σ − f_y)/H", ep, ep_s, 1e-6)
            check(f"{was}: die Spannung liegt auf der verfestigten Fließfläche f_y + H ε_p",
                  abs(_vm(s) - (FY + H * ep)) <= 1e-6 * FY, f"{_vm(s) / 1e6:.4f} gegen {(FY + H * ep) / 1e6:.4f} MPa")
        else:
            check(f"{was}: keine plastische Dehnung", ep == 0.0, f"{ep:.3e}")
        # Gleichgewicht: die Lager tragen die Last (die Vorspannung ist innere
        # Kraft), und am Kopf halten Bolzenspannung und Klemmkraft ihr die Waage
        Rz = float(np.asarray(r.reactions, float)[:, 2].sum())
        N_k = sum(E * AK * (u[t, 2] - u[g, 2]) / LK for g, t in zip(boden, kopf))
        check(f"{was}: Gleichgewicht ΣR_z = −P", abs(Rz + P) <= 1e-9 * FV, f"ΣR_z {Rz / 1e6:.6f} MN")
        check(f"{was}: am Kopf σ_zz A + Klemmkraft = P", abs(s[2] * A + N_k - P) <= 1e-6 * FV,
              f"{s[2] * A / 1e6:.4f} + {N_k / 1e6:.4f} = {(s[2] * A + N_k) / 1e6:.4f} MN, P {P / 1e6:.4f} MN")


def _ein_element(typ="hex8"):
    from statik3d.elements import solid as sl
    m = Model("Punkt")
    m.add_material(Material("S355", E=E, nu=NU, rho=7850, fy=FY))
    ecken = {"hex8": [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
             "tet4": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]}[typ]
    rng = np.random.default_rng(7)
    P = np.asarray(ecken, float) + 0.05 * rng.standard_normal((len(ecken), 3))
    m.add_element(typ, [m.add_node(*p) for p in P[:sl._KNOTENZAHL[typ]]], "S355", "")
    return m


def _zustand(s0):
    z = pl.Zustand()
    z.sigma0 = {0: np.asarray(s0, float)}
    return z


def test_rueckfuehrung_sieht_sigma0():
    """Ohne Verschiebung ist die wahre Spannung −σ₀: mit σ₀ = −1,2 f_y in z
    (einachsiger Zug 1,2 f_y) muss der Punkt fliessen, mit −0,9 f_y nicht."""
    einst = pl.Plastizitaet(an=True, verfestigung=ET)
    for typ in ("hex8", "tet4"):
        m = _ein_element(typ)
        el = pl._solid_elemente(m, None)
        u = np.zeros(m.ndof)
        for faktor, soll in ((1.2, True), (0.9, False)):
            s0 = np.array([0.0, 0.0, -faktor * FY, 0.0, 0.0, 0.0])
            _F, z, info = pl.schritt(m, u, _zustand(s0), einst, el, [])
            fl = info["fliessend"] > 0
            check(f"{typ}: σ₀ = −{faktor:g} f_y ohne Verschiebung: {'fließt' if soll else 'fließt nicht'}",
                  fl == soll, f"fließend {info['fliessend']}, q_max {info['q_max'] / 1e6:.2f} MPa")
            if soll:
                # einachsig: σ_v nach der Rueckfuehrung = f_y + H Δγ mit
                # Δγ = (1,2 f_y − f_y)/(3G + H)
                G = E / (2 * (1 + NU))
                dg = (faktor * FY - FY) / (3 * G + H)
                nahe(f"{typ}: σ_v nach der Rückführung = f_y + H Δγ", info["q_max"], FY + H * dg, 1e-9, "Pa")


def test_block_gleich_schleife_mit_sigma0():
    """Block (Feldoperationen) und Schleife (Element fuer Element) rechnen mit
    σ₀ dasselbe - zwei unabhaengige Wege durch dieselbe Rueckfuehrung."""
    einst = pl.Plastizitaet(an=True, verfestigung=ET)
    rng = np.random.default_rng(13)
    for typ in ("hex8", "tet4"):
        m = _ein_element(typ)
        el = pl._solid_elemente(m, None)
        u = rng.normal(0.0, 1e-5, m.ndof)
        s0 = np.array([0.0, 0.0, -1.05 * FY, 0.0, 0.0, 0.0])
        Fb, zb, ib = pl._schritt_block(m, u, _zustand(s0), einst, el, typ, [])
        Fs, zs, is_ = pl._schritt_schleife(m, u, _zustand(s0), einst, el, [])
        bez = max(float(np.abs(Fs).max()), 1e-30)
        check(f"{typ} mit σ₀: Block und Schleife gleich ({ib['fliessend']} fließend)",
              ib["fliessend"] == is_["fliessend"] == 1 and float(np.abs(Fb - Fs).max()) <= 1e-9 * bez
              and abs(ib["q_max"] - is_["q_max"]) <= 1e-9 * is_["q_max"],
              f"ΔF_p {float(np.abs(Fb - Fs).max()) / bez:.2e}, q_max {ib['q_max'] / 1e6:.4f} / "
              f"{is_['q_max'] / 1e6:.4f} MPa")


def test_tangente_mit_sigma0():
    """ΔK bleibt mit σ₀ die Ableitung −∂F_p/∂u (zentrale Differenzen)."""
    einst = pl.Plastizitaet(an=True, verfestigung=ET)
    rng = np.random.default_rng(17)
    for typ in ("hex8", "tet4"):
        m = _ein_element(typ)
        el = pl._solid_elemente(m, None)
        u = rng.normal(0.0, 1e-5, m.ndof)
        s0 = np.array([0.0, 0.0, -1.05 * FY, 0.0, 0.0, 0.0])
        _F, _z, info = pl._schritt_block(m, u, _zustand(s0), einst, el, typ, [], tangente=True)
        dK = info["dK"].toarray()
        spalten = np.flatnonzero(np.abs(dK).sum(axis=0) > 0)
        num = np.zeros((m.ndof, len(spalten)))
        h = 1e-9
        for j, a in enumerate(spalten):
            up, um = u.copy(), u.copy()
            up[a] += h
            um[a] -= h
            num[:, j] = -(pl._schritt_block(m, up, _zustand(s0), einst, el, typ, [])[0]
                          - pl._schritt_block(m, um, _zustand(s0), einst, el, typ, [])[0]) / (2 * h)
        abw = (float(np.abs(dK[:, spalten] - num).max()) / max(float(np.abs(num).max()), 1e-30)
               if len(spalten) else float("nan"))
        check(f"{typ} mit σ₀: ΔK = −∂F_p/∂u ({info['fliessend']} fließend)",
              info["fliessend"] > 0 and len(spalten) > 0 and abw < 1e-6, f"{abw:.2e}")


def main():
    for t in (test_bolzen_geschlossen, test_rueckfuehrung_sieht_sigma0, test_block_gleich_schleife_mit_sigma0,
              test_tangente_mit_sigma0):
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
