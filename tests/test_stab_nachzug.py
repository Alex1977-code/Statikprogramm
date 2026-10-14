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


def main():
    for t in (test_pendel_saitenform, test_kg_saitenform_je_art, test_zugband_gegen_hand):
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
