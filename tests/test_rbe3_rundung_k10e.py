"""
Zusammenfuehrung k10 (16.11.2026): Strafbeiwert des frei definierten RBE3
bei Koeffizienten auf Rundungsniveau.

assemble.rbe3_zeilen_master (fix/k10-ring, Nachbesserung 2) gibt jeder
Masterbewegung j einen eigenen Strafbeiwert k_j = Faktor mal die Steifigkeit,
mit der die Slaves der Bewegung widerstehen (Zaehler Σ b_ji² d_i). Haben die
Slaves einer Zeile keine Steifigkeit, gilt die groesste Hauptdiagonale. Nach
der Umformung mit G_m^-1 bleibt aber an einem Slave, der die Bewegung gar
nicht mitbestimmt, ein Rundungsrest des Koeffizienten (um 3e-16 relativ).
Traegt dieser Slave Steifigkeit, lag der Zaehler um 1e-22 statt bei null:
k_j fiel auf rund 1e-14 N/m, die Zwangsbedingung dieser Masterbewegung
fehlte, und eine Last am Master in dieser Richtung ging still in die
automatische Fesselung.

Pruefkoerper: Kragarm a-b (L = 3 m, eingespannt in a), RBE3-Master P
(L, 1, 0) ohne Element, Slaves b und n Knoten (L, 1 + 0,1 i, 0,2 i), diese
in allen Richtungen gelagert (wie test_singulaer_meldung_k10.viele, dort
lose). Die Verschiebung x des Masters bestimmen allein die gelagerten
Slaves; b hat in dieser Zeile den Koeffizienten null (Rundungsrest). Last
Fx = 1 kN und Fz = 1 kN an P.

Sollwerte, je zwei Wege:
* Gleichgewicht (Hand): Summe Rx = -1 000 N, und zwar an den gelagerten
  Slaves; u_x(P) = 0 (die Slaves stehen).
* Gegenrechnung mit der Straffeder vor Nachbesserung 2 (k Gᵀ G,
  assemble.RBE3_ZEILEN_ALT, so rechnete Stand 65): dieselben Lagerkraefte.

Vor der Behebung: Summe Rx = 0 N, die Last steht in der automatischen
Fesselung (res.info["auto_gehalten"]).

Aufruf:  python -m tests.test_rbe3_rundung_k10e
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

E = 210e9
L = 3.0
I = 8e-5
F = 1e3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def modell(n):
    """(Modell, Master P, Kragarmende b, gelagerte Slaves)."""
    from statik3d.model import Model, Material, Section
    m = Model("k10e")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    p = m.add_node(L, 1, 0)
    slaves = [m.add_node(L, 1 + 0.1 * i, 0.2 * i) for i in range(1, n + 1)]
    for k in slaves:
        m.fix(k, "all")
    m.add_starrkoerper(p, [b] + slaves, "RBE3", name="V")
    m.load_node(p, Fx=F, Fz=-F, case="LF1")
    return m, p, b, slaves


def rechne(m, alt=False):
    from statik3d import assemble as asm
    from statik3d import solver
    vorher = asm.RBE3_ZEILEN_ALT
    asm.RBE3_ZEILEN_ALT = bool(alt)
    try:
        r = _still(solver.solve_static, m, case="LF1")
    finally:
        asm.RBE3_ZEILEN_ALT = vorher
    return (r, np.asarray(r.u, float).reshape(-1, 6), np.asarray(r.reactions, float).reshape(-1, 6))


def test_last_am_master():
    for n in (3, 10):
        m, p, b, sl = modell(n)
        try:
            r, u, R = rechne(m)
        except Exception as ex:                     # noqa: BLE001
            check(f"n = {n}: rechnet", False, f"{type(ex).__name__}: {str(ex)[:160]}")
            continue
        rx = float(R[:, 0].sum())
        rx_sl = float(R[sl, 0].sum())
        check(f"n = {n}: Summe Rx = -1 000 N (Gleichgewicht), an den gelagerten Slaves",
              abs(rx + F) <= 1e-6 * F and abs(rx_sl + F) <= 1e-6 * F, f"Summe Rx {rx:.6f} N, an den Slaves {rx_sl:.6f} N")
        check(f"n = {n}: Summe Rz = 1 000 N", abs(float(R[:, 2].sum()) - F) <= 1e-6 * F, f"{R[:, 2].sum():.6f} N")
        check(f"n = {n}: u_x(P) = 0 (die Slaves stehen; Luecke der Straffeder unter 0,000001 mm)",
              abs(u[p, 0]) <= 1e-9, f"u_x(P) {u[p, 0] * 1e3:.9f} mm")
        check(f"n = {n}: keine automatische Fesselung am Master (die Last steht nicht dort)",
              not (r.info or {}).get("auto_gehalten"), str((r.info or {}).get("auto_gehalten"))[:160])
        _r0, _u0, R0 = rechne(m, alt=True)
        dr = float(np.abs(R[:, :3] - R0[:, :3]).max())
        check(f"n = {n}: Lagerkraefte gleich der Gegenrechnung mit k Gᵀ G (Stand 65) auf 0,001 N",
              dr <= 1e-3, f"groesste Abweichung {dr:.6f} N, Gegenrechnung Summe Rx {R0[:, 0].sum():.6f} N")


def test_strafbeiwert_je_zeile():
    """Jede Zeile hat einen Strafbeiwert in der Groesse der uebrigen, keiner auf
    Rundungsniveau; die Zeile x des Masters ist die ohne Steifigkeit."""
    from statik3d import assemble as asm
    from statik3d.elements import verbindung as vb
    m, p, b, sl = modell(10)
    sk = m.starrkoerper[0]
    knoten = [b] + sl
    G = vb.starrkoerper_matrix(m.nodes[p], m.nodes[knoten], sk.art, None)
    d = np.array(list(range(6 * p, 6 * p + 6)) + [x for s in knoten for x in range(6 * s, 6 * s + 6)])
    K = asm._assemble_triplets(m, asm._matrix_chunk, 1, None)
    gross = float(np.abs(K.diagonal()).max())
    Gs = asm.rbe3_zeilen_master(G, asm.rbe3_zeilensummen(K, G, d), gross)
    k = np.array([float(Gs[j, j]) ** 2 for j in range(6)]) if Gs is not None else np.zeros(6)
    check("Strafbeiwert je Masterbewegung: keiner unter 1e10 N/m (vorher k_x um 1e-14 N/m)",
          Gs is not None and float(k.min()) >= 1e10, f"k_j {np.array2string(k, precision=3)}")


def test_bitgleich_mit_tragenden_slaves():
    """Wo die tragenden Slaves Steifigkeit haben, bleibt der Strafbeiwert
    bitgleich (Kreisring R = 0,1 und 0,02 m aus test_rbe3_ring_k10): die
    Summe wird unveraendert ueber alle Koeffizienten gebildet."""
    from statik3d import assemble as asm
    from statik3d.elements import verbindung as vb
    from tests import test_rbe3_ring_k10 as T
    for Rr in (0.1, 0.02):
        m, b, p, rk = T.modell_var(10, Rr=Rr)
        sk = m.starrkoerper[0]
        G = vb.starrkoerper_matrix(m.nodes[int(sk.master)], m.nodes[rk], sk.art, None)
        d = np.array(list(range(6 * p, 6 * p + 6)) + [x for s in rk for x in range(6 * s, 6 * s + 6)])
        K = asm._assemble_triplets(m, asm._matrix_chunk, 1, None)
        gross = float(np.abs(K.diagonal()).max())
        zs = asm.rbe3_zeilensummen(K, G, d)
        Gs = asm.rbe3_zeilen_master(G, zs, gross)
        # zweiter Weg: dieselbe Formel ohne die Behandlung der Rundungsreste
        Gn = np.linalg.solve(G[:, :6], G)
        Gn[:, :6] = np.eye(6)
        Gn[:, 6:][:, np.all(G[:, 6:] == 0.0, axis=0)] = 0.0
        S = np.empty(6)
        for j in range(6):
            b2 = Gn[j, 6:] ** 2
            nb2 = float(b2.sum())
            z = float(b2 @ np.abs(zs)[6:])
            S[j] = z / nb2 ** 2 if z > 0.0 else gross / nb2
        f = max(asm.RBE3_FAKTOR, asm.RBE3_STEIF_MIN / float(S[:3].max()))
        ref = np.sqrt(f * S)[:, None] * Gn
        check(f"Kreisring R = {Rr} m: Straffeder bitgleich zur Formel ohne Rundungsbehandlung",
              Gs is not None and np.array_equal(Gs, ref), "")


def main():
    for t in (test_last_am_master, test_strafbeiwert_je_zeile, test_bitgleich_mit_tragenden_slaves):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"{t.__name__} (Ausnahme: {ex})", False))
    ok = sum(1 for _n, o in RESULTS if o)
    print(f"\n{'=' * 60}\nErgebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    bad = [n for n, o in RESULTS if not o]
    if bad:
        print("FEHLGESCHLAGEN:", bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
