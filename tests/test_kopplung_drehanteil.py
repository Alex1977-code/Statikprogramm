"""Kopplungen mit Drehanteil: Momentengleichgewicht der starren Kopplungen
(Entscheidung des Anwenders vom 14.10.2026).

Befund (Rueckmeldung stab/haltung, scratchpad sht_werk/b3): Ein Stabende in
einem Volumen und die Netzknoten einer starren Scheibe hingen bis zum
14.10.2026 nur ueber ihre Verschiebungen an ihrem Masterknoten (u_s = u_m je
Knoten). Fuer versetzte Knoten ist das keine Starrkoerperbewegung: Die
Kopplungskraefte haben die Kraftsumme null, aber ein Moment. Am Wuerfel 1 m
(tet4, h 0,25) mit einer Stuetze d = 100 mm, die bei z = 0,6 im Block endet
und am Kopf (z = 3 m) 10 kN quer traegt, hielt das Fundament -5,345 statt
-30 kNm, und die Kopplung selbst trug 24,655 kNm.

Jetzt:
* starre Scheibe: RBE2 mit Drehanteil, u_s = u_m + theta_m x (x_s - x_m);
* Stabende an 1-4 Knoten: RBE3 (der Stabknoten folgt dem baryzentrischen
  Mittel der Knoten; hat er ein Biegestab-Element, auch ihrer Drehung, mit
  mindestens drei nicht kollinearen Knoten - sonst ueber die Ecken des
  Elements, in dem er liegt);
* nach jeder Rechnung die globale Gleichgewichtskontrolle (Summe der Kraefte
  und Momente der Lasten und Lagerkraefte).

Aufruf:  python -m tests.test_kopplung_drehanteil
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, fugen, solver          # noqa: E402
from statik3d.model import NDOF, Kopplung, Model, NodalLoad, Section   # noqa: E402
from tests.test_fugen import _flaechenknoten, _wuerfel, Bauer   # noqa: E402

RESULTS = []
F = 1.0e4          # N quer (x) am Kopf
ZK = 3.0           # Kopfhoehe [m]
D = 0.1            # Stuetze Rund 100
E_STAHL = 210e9


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def hand(z0: float) -> float:
    """Kopfverschiebung der bei z0 voll eingespannten Kragstuetze (Biegung)."""
    I = np.pi * D ** 4 / 64
    return F * (ZK - z0) ** 3 / (3 * E_STAHL * I)


def kopplungskraefte(m, r) -> np.ndarray:
    """Knotenkraefte (nn, 6) aller Kopplungen und Starrkoerper: (K_k + K_s) u."""
    u = np.zeros(m.ndof)
    u[:m.nn * NDOF] = np.asarray(r.u, float).reshape(-1)
    K = asm._assemble_triplets(m, asm._matrix_chunk, None)
    f = np.zeros(m.ndof)
    Kk = asm.kopplungen(m, K)
    if Kk is not None:
        f += Kk @ u
    Ks = asm.starrkoerper(m, K, K_bezug=K)
    if Ks is not None:
        f += Ks @ u
    return f[:m.nn * NDOF].reshape(-1, NDOF)


def moment_um(m, f6, p) -> np.ndarray:
    X = np.asarray(m.nodes, float)
    return (np.cross(X - np.asarray(p, float), f6[:, :3]) + f6[:, 3:]).sum(axis=0)


def stuetze(art: str, gelenk: bool = False, z0: float = 0.6):
    """Wuerfel 1 m (tet4, h 0,25), Boden fest, Stuetze Rund 100 bei
    (0,41; 0,47) bis z = 3 m. ``art``: "innen" (Stabende bei z = 0,6 im Block),
    "deckel" (in der Deckelflaeche z = 1), "durch" (Stab von z = 0,2 bis 1,0
    durch den Block, 5 Knoten darin), "fest" (neben dem Block bei ``z0`` voll
    eingespannt). Bei "innen" liegt auch der zweite Stabknoten (z = 0,84)
    im Block und haengt an ihm; eingespannt ist die Stuetze dann bei 0,84. ``gelenk``: Momentengelenk am unteren Stabende, der Kopf
    ist dann quer gehalten und die Last greift in halber Hoehe an."""
    m = _wuerfel(0.25)
    m.add_section(Section.circle("D", D))
    for i in _flaechenknoten(m, 0.0):
        m.fix(i, [0, 1, 2])
    x, y = 0.41, 0.47
    if art == "fest":
        y += 5.0
    zs = {"innen": [0.6], "fest": [z0], "deckel": [1.0], "durch": [0.2, 0.4, 0.6, 0.8, 1.0]}[art]
    if zs[-1] == 1.0:
        zs = zs + list(np.linspace(1.0, ZK, 9)[1:])
    elif art == "fest" and abs(z0 - 0.84) < 1e-9:
        zs = list(np.linspace(0.6, ZK, 11)[1:])           # dieselbe Teilung wie "innen"
    else:
        zs = zs + list(np.linspace(zs[-1], ZK, 11)[1:])
    kn = [m.add_node(x, y, z) for z in zs]
    els = []
    for i in range(len(kn) - 1):
        els.append(m.add_element("beam", [kn[i], kn[i + 1]], "S235", "D",
                                 hinges=[4, 5] if (gelenk and i == 0) else None))
    m.add_member("Stuetze", els)
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    if gelenk:
        m.fix(kn[-1], [0, 1, 5])
        mitte = kn[len(kn) // 2]
        m.load_node(mitte, Fx=F, case="LF1")
    else:
        m.load_node(kn[-1], Fx=F, case="LF1")
    if art == "fest":
        m.fix(kn[0], "all")
        b = {"stabenden": 0, "kopplungen": 0}
    else:
        b = fugen.stabenden_koppeln(m, [])
    return m, kn, b


def _auswerten(m, kn, art):
    r = solver.solve_static(m, case="LF1")
    R = np.asarray(r.reactions, float)
    unten = _flaechenknoten(m, 0.0)
    p0 = np.array([0.41, 0.47, 0.0])
    M_fund = moment_um(m, _nur(R, unten, m.nn), p0)
    fk = kopplungskraefte(m, r)
    M_k = moment_um(m, fk, p0)
    return r, M_fund, fk, M_k


def _nur(R, knoten, nn):
    aus = np.zeros((nn, NDOF))
    aus[knoten] = R[knoten]
    return aus


def test_stuetze_im_block():
    print("\n--- 1. Kragstuetze, die im Block endet (Befund b3) ---")
    M_soll = -F * ZK
    fest = {}
    for z0 in (0.84, 1.0):
        m, kn, _b = stuetze("fest", z0=z0)
        fest[z0] = float(solver.solve_static(m, case="LF1").u[kn[-1], 0])
    print(f"    eingespannt bei z0 = 0,84: Hand {hand(0.84) * 1e3:.3f} mm, gerechnet {fest[0.84] * 1e3:.3f} mm; "
          f"bei z0 = 1,0: Hand {hand(1.0) * 1e3:.3f} mm, gerechnet {fest[1.0] * 1e3:.3f} mm")
    bezug = {"innen": 0.84, "deckel": 1.0, "durch": 1.0}
    for art in ("innen", "deckel", "durch"):
        m, kn, b = stuetze(art)
        try:
            r, M_fund, fk, M_k = _auswerten(m, kn, art)
        except Exception as ex:                       # noqa: BLE001
            check(f"{art}: die Rechnung laeuft", False, f"{type(ex).__name__}: {str(ex)[:160]}")
            continue
        u_k = float(r.u[kn[-1], 0])
        partner = sorted({int(k.node_b) for k in m.kopplungen if int(k.node_a) == kn[0]})
        print(f"    {art}: {b['stabenden']} Stabknoten im Block, {b['kopplungen']} Kopplungen (unteres Ende an "
              f"{len(partner)} Knoten); Kopf {u_k * 1e3:.3f} mm; Fundament M_y {M_fund[1] / 1e3:.4f} kNm; "
              f"Moment der Kopplungskraefte {np.round(M_k / 1e3, 6)} kNm, Kraftsumme "
              f"{np.round(fk[:, :3].sum(axis=0), 6)} N")
        check(f"{art}: die Kopplung ist im Momentengleichgewicht (|M| < 1e-6 F L)",
              float(np.linalg.norm(M_k)) < 1e-6 * F * ZK, f"{np.linalg.norm(M_k):.3e} Nm")
        check(f"{art}: das Fundament haelt das Einspannmoment -30 kNm (auf 1e-6)",
              abs(M_fund[1] - M_soll) < 1e-6 * abs(M_soll), f"{M_fund[1] / 1e3:.6f} kNm")
        z0 = bezug[art]
        check(f"{art}: Kopf wie bei z = {z0:g} eingespannt, mehr nur um die Nachgiebigkeit des Blocks "
              "(0 bis +2 %)", fest[z0] * (1 - 1e-6) <= u_k <= fest[z0] * 1.02,
              f"{u_k * 1e3:.3f} gegen {fest[z0] * 1e3:.3f} mm (Hand {hand(z0) * 1e3:.3f})")


def test_gelenk_am_stabende():
    print("\n--- 2. Stab mit Momentengelenk am Ende im Block ---")
    m, kn, _b = stuetze("deckel", gelenk=True)
    r, M_fund, fk, M_k = _auswerten(m, kn, "deckel")
    mf = solver.member_forces(m, r, m.members["Stuetze"])
    M_ende = float(np.hypot(mf["My"][0], mf["Mz"][0]))           # Biegung (lokal y, z)
    p = np.asarray(m.nodes[kn[0]], float)
    M_um_ende = moment_um(m, _nur(fk, [i for i in range(m.nn) if i != kn[0]], m.nn), p)
    print(f"    Stabmoment am Gelenk {M_ende:.3e} Nm; Moment der Kopplungskraefte im Block um das Stabende "
          f"{np.round(M_um_ende, 6)} Nm; Kopplung gesamt {np.round(M_k, 6)} Nm")
    check("Gelenk bleibt Gelenk: Stabmoment am Ende 0", M_ende < 1e-6 * F * ZK, f"{M_ende:.3e} Nm")
    # Biegung um x und y; die Torsion um die Stabachse (z) haelt das Gelenk
    # nicht frei, sie ist ein Hundertstel Nm aus der unsymmetrischen Seite
    check("die Kopplung gibt kein Biegemoment in den Block (um das Stabende < 1e-6 F L)",
          float(np.linalg.norm(M_um_ende[:2])) < 1e-6 * F * ZK, f"{np.linalg.norm(M_um_ende[:2]):.3e} Nm")
    check("die Kopplung ist im Momentengleichgewicht", float(np.linalg.norm(M_k)) < 1e-6 * F * ZK,
          f"{np.linalg.norm(M_k):.3e} Nm")


def scheibe(exzentrisch: float = 0.1, P: float = 50e3, stab: str = "truss"):
    """Wuerfel 1 m (tet4, h 0,25), Boden fest; oben eine starre Scheibe
    0,2..0,8 m, in ihrer Mitte das Ende eines Stabes (Fachwerkstab nach
    oben zu einem festen Knoten oder Kragarm). Last am Stabknoten: P nach
    unten und das Moment P e um y - gleichwertig P im Abstand e auf der
    Seite +x."""
    m = _wuerfel(0.25)
    for i in _flaechenknoten(m, 0.0):
        m.fix(i, [0, 1, 2])
    b = Bauer(m)
    ecken = [m.add_node(x, y, 1.0) for x, y in ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))]
    linien = [b.linie(ecken[i], ecken[(i + 1) % 4]) for i in range(4)]
    m.add_flaeche("Scheibe", linien, material="S235")
    m.flaechen["Scheibe"].steifigkeit = "starr"
    mitte = m.add_node(0.5, 0.5, 1.0)
    oben = m.add_node(0.5, 0.5, 2.0)
    m.add_section(Section("Rund", 1e-4, 1e-9, 1e-9, 1e-9))
    e = m.add_element(stab, [mitte, oben], "S235", "Rund", group="Stab")
    m.add_member("Stab", [e])
    m.fix(oben, [0, 1] if stab == "truss" else [0, 1, 3, 4, 5])
    fugen.starre_flaechen_koppeln(m, [])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    lc.nodal_loads.append(NodalLoad(mitte, [0, 0, -P, 0, P * exzentrisch, 0]))
    return m, mitte


def test_starre_scheibe_exzentrisch():
    print("\n--- 3. Starre Scheibe mit exzentrischer Last ---")
    P, e = 50e3, 0.1
    m, mitte = scheibe(e, P)
    r = solver.solve_static(m, case="LF1")
    R = np.asarray(r.reactions, float)
    unten = _flaechenknoten(m, 0.0)
    pm = np.asarray(m.nodes[mitte], float)
    M_fund = moment_um(m, _nur(R, unten, m.nn), pm)
    fk = kopplungskraefte(m, r)
    M_k = moment_um(m, fk, pm)
    slaves = sorted({int(k.node_b) for k in m.kopplungen if str(k.gruppe).startswith(fugen.STARR_GRUPPE)})
    X = np.asarray(m.nodes, float)
    th = np.asarray(r.u[mitte, 3:], float)
    soll = r.u[mitte, :3][None, :] + np.cross(th[None, :], X[slaves] - pm)
    abw = float(np.abs(r.u[slaves, :3] - soll).max())
    uz = r.u[slaves, 2]
    print(f"    Fundament um den Scheibenmittelpunkt {np.round(M_fund, 3)} Nm (Soll M_y = -P e = {-P * e:.1f}); "
          f"Moment der Kopplungskraefte {np.round(M_k, 6)} Nm; Drehung der Scheibe {np.round(th, 9)} rad; "
          f"u_z der Scheibenknoten {uz.min() * 1e6:.4f} .. {uz.max() * 1e6:.4f} µm; Abweichung von der "
          f"Starrkoerperbewegung {abw:.2e} m")
    check("das Fundament traegt das Moment P e (auf 1e-6)", abs(M_fund[1] + P * e) < 1e-6 * P * e,
          f"{M_fund[1]:.6f} Nm")
    check("die Kopplung ist im Momentengleichgewicht (|M| < 1e-9 P e)",
          float(np.linalg.norm(M_k)) < 1e-9 * P * e, f"{np.linalg.norm(M_k):.3e} Nm")
    check("die Scheibe kippt zur Last hin (theta_y > 0), die Knoten folgen u_m + theta x r (auf 1e-3)",
          th[1] > 0 and abw < 1e-3 * float(np.abs(r.u[slaves, :3]).max()), f"theta_y {th[1]:.3e} rad")
    check("die Scheibe bleibt eben und kippt: u_z linear in x und y (Rest < 1e-4 relativ), Spanne > 10 %",
          _ebenenrest(X[slaves], uz) < 1e-4 * float(np.abs(uz).max())
          and float(uz.max() - uz.min()) > 0.1 * float(np.abs(uz).max()),
          f"Rest {_ebenenrest(X[slaves], uz):.2e} m, Spanne {float(uz.max() - uz.min()):.2e} m")
    s = r.summary()
    gg = r.info.get("gleichgewicht_global") or {}
    check("die globale Gleichgewichtskontrolle steht im Ergebnis und ist erfuellt",
          gg and gg.get("ok") and "Gleichgewicht" in s,
          next((z for z in s.splitlines() if "Gleichgewicht" in z), "")[:160])


def _ebenenrest(X, w) -> float:
    A = np.column_stack([np.ones(len(X)), X[:, 0], X[:, 1]])
    c, *_ = np.linalg.lstsq(A, w, rcond=None)
    return float(np.abs(A @ c - w).max())


def test_gleichgewichtskontrolle_warnt():
    print("\n--- 4. Globale Gleichgewichtskontrolle warnt bei einer versetzten Kopplung ohne Drehanteil ---")
    m, kn, _b = stuetze("innen")
    # eine von Hand angelegte Kopplung (nicht Stabende, nicht starre Scheibe)
    # zwischen dem Stabende und drei versetzten Netzknoten: nur Verschiebungen
    alt = [k for k in m.kopplungen if str(k.gruppe).startswith(fugen.STABENDE_GRUPPE)]
    m.kopplungen = [Kopplung(int(k.node_a), int(k.node_b), k.richtungen, k.steifigkeiten, "Hand")
                    for k in alt]
    r = solver.solve_static(m, case="LF1")
    gg = r.info.get("gleichgewicht_global") or {}
    s = r.summary()
    zeile = next((z for z in s.splitlines() if "Gleichgewicht" in z), "")
    print(f"    {zeile}")
    # seit dem 14.10.2026 ab 1e-2 des Umsatzes „nicht gültig“ (hier bezogen 0,96)
    check("die Kontrolle meldet die Abweichung im Moment: nicht gültig (bezogen über 1e-2)",
          gg and not gg.get("ok") and gg.get("dM", 0) > 1e3 and "NICHT GÜLTIG" in zeile
          and "Gleichgewicht verletzt" in solver.gueltigkeit(r.info), str(gg)[:200])


def test_ohne_versetzte_kopplung_bitgleich():
    print("\n--- 5. Ohne versetzte Kopplungen bitgleich ---")
    from tests.test_fugen import kontaktbedingung, zwei_bloecke
    m = zwei_bloecke("gemeinsam", ordnung=1)
    kb = kontaktbedingung(m, "gemeinsam", tangential="rigid")
    fugen.kontaktfuge_ausfuehren(m, kb, [])
    K = asm._assemble_triplets(m, asm._matrix_chunk, None)
    Kk = asm.kopplungen(m, K).tocsr()
    # dieselbe Matrix wie vor dem 14.10.2026: je Richtung k c c^T auf den Verschiebungen
    diag = np.abs(np.asarray(K.diagonal()).ravel())
    starr = 1e4 * float(diag[diag > 0].max())
    from scipy import sparse
    rows, cols, vals = [], [], []
    for kp in m.kopplungen:
        d = np.array(asm._trans_dofs(int(kp.node_a)) + asm._trans_dofs(int(kp.node_b)), int)
        for richtung, wert in kp.paare():
            k = starr if not np.isfinite(wert) else float(wert)
            c = np.concatenate([-richtung, richtung])
            r_, cc = np.meshgrid(d, d, indexing="ij")
            rows.append(r_.ravel()); cols.append(cc.ravel()); vals.append((k * np.outer(c, c)).ravel())
    alt = sparse.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                            shape=Kk.shape).tocsr()
    d = (Kk - alt)
    check("Fugenkopplungen (deckungsgleiche Knoten): Matrix bitgleich wie bisher",
          d.nnz == 0 or float(np.abs(d.data).max()) == 0.0, f"{len(m.kopplungen)} Kopplungen")


def test_ankerplatte():
    print("\n--- 6. Ankerplatte aus test_spitzen_abbruch (elastisch) ---")
    from tests.test_spitzen_abbruch import ankerplatte, ankerkraft
    m, ids, mitte, e = ankerplatte(F_v=0.45e6, P=0.15e6)
    m.plastizitaet.an = False
    r = solver.solve_static(m)
    fk = kopplungskraefte(m, r)
    pm = np.asarray(m.nodes[mitte], float)
    M_k = moment_um(m, fk, pm)
    N = ankerkraft(m, r, e)
    slaves = sorted({int(k.node_b) for k in m.kopplungen})
    F_ring = -fk[slaves, :3].sum(axis=0)
    print(f"    Ankerkraft {N / 1e3:.3f} kN, Kraft der Scheibe auf die Platte {np.round(F_ring / 1e3, 3)} kN, "
          f"Moment der Kopplungskraefte {np.round(M_k, 6)} Nm, Drehung der Scheibe {np.round(r.u[mitte, 3:], 12)}")
    check("Ankerplatte: die Kopplung ist im Momentengleichgewicht", float(np.linalg.norm(M_k)) < 1e-9 * N * 0.025,
          f"{np.linalg.norm(M_k):.3e} Nm")
    check("Ankerplatte: die Scheibe gibt Ankerkraft und Last in die Platte (N + P, auf 1e-6)",
          abs(abs(F_ring[2]) - (N + 0.15e6)) <= 1e-6 * (N + 0.15e6), f"{F_ring[2] / 1e3:.6f} kN")
    gg = r.info.get("gleichgewicht_global") or {}
    check("Ankerplatte: globale Gleichgewichtskontrolle erfuellt", gg.get("ok"), str(gg)[:160])


def main():
    for t in (test_stuetze_im_block, test_gelenk_am_stabende, test_starre_scheibe_exzentrisch,
              test_gleichgewichtskontrolle_warnt, test_ohne_versetzte_kopplung_bitgleich, test_ankerplatte):
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
