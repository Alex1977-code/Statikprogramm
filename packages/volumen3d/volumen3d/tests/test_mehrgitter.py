"""W1/W2 (Teilprojekt 4): p-Ebenen (Injektion, Schachtelung der Zwaenge, Galerkin = Teilblock),
V-Zyklus als Vorkonditionierer im CG gegen den Direktloeser; Iterationszahlen gegen Jacobi.

Aufruf: python -m volumen3d.tests.test_mehrgitter   (~4 min)
"""
from __future__ import annotations

import sys
import time

import numpy as np

from volumen3d.tests._pruef import check, lauf


def _faelle():
    from volumen3d.tests.test_kragarm import _segment
    from volumen3d.tests.test_operator import _kirsch, _lame
    from volumen3d.tests.test_patch import _problem as patch_problem, u_exakt
    from volumen3d.tests.test_pcg import _lame_mit_druck

    def u_lin(P):
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([1e-3 * P[:, 0], -0.3e-3 * P[:, 1], -0.3e-3 * P[:, 2]], axis=1)

    return [("Patch h 20 p 2 (voll, Aggregation)", lambda: patch_problem(2, 1e-8), {"alles": u_exakt}),
            ("Kragarmsegment p 3 h 50 (schnitt)", lambda: _segment(400.0, 600.0, 3, 50.0), {"links": u_lin, "rechts": u_lin}),
            ("Lame h 20 p 3 (normal, Druck)", lambda: _lame_mit_druck(_lame(p=3)), {}),
            ("Kirsch h 20 p 2 verfeinert", lambda: _kirsch(verfeinert=True), {}),
            ("Kirsch h 20 p 3 verfeinert", lambda: _kirsch(p=3, verfeinert=True), {})]


def test_ebenen():
    import copy
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.fcm.zwaenge import Zwaenge
    rng = np.random.default_rng(3)
    for name, bau, _ in _faelle()[:4]:
        pr = bau()
        pr.aufbauen()
        t = time.perf_counter()
        mg = PMehrgitter(pr)
        t_mg = time.perf_counter() - t
        ok_inj = all(np.all(np.asarray(eb.P.sum(axis=0)).ravel() == 1) and np.all(eb.P.data == 1.0) for eb in mg.ebenen[1:])
        fehler = 0.0
        for k in range(len(mg.ebenen) - 1):
            fein, grob = mg.ebenen[k], mg.ebenen[k + 1]
            for _ in range(3):
                x = rng.standard_normal(grob.n_frei)
                a_g = grob.A(x)
                a_f = grob.P.T @ fein.A(grob.P @ x)
                fehler = max(fehler, float(np.abs(a_g - a_f).max() / max(np.abs(a_f).max(), 1e-300)))
        # abgeleitete grobe Zwaenge gegen unabhaengig gebaute (Spurbindung und Aggregation auf dem groben Gitter)
        f_c = 0.0
        gleich_frei = True
        for eb in mg.ebenen[1:]:
            ag_k = None
            if pr.aggregation is not None:
                ag_k = copy.copy(pr.aggregation)
                ag_k.gitter = eb.gitter
                ag_k.statistik = dict(pr.aggregation.statistik)
            zw = Zwaenge(eb.gitter, ag_k)
            gleich_frei &= bool(np.array_equal(np.sort(eb.moden_frei), zw.moden_frei))
            if gleich_frei:
                ordnung = np.argsort(eb.moden_frei)
                sp3 = (3 * ordnung[:, None] + np.arange(3)).ravel()
                D = (eb.C[:, sp3] - zw.C).tocsr()
                f_c = max(f_c, float(np.abs(D.data).max()) if D.nnz else 0.0)
        check(f"{name}: Ebenen {mg.statistik['ebenen']} mit {mg.statistik['frei_je_ebene']} freien Koordinaten; Injektion, "
              f"A_grob = P~^T A_fein P~ (< 1e-12), abgeleitete grobe Zwaenge = unabhaengig gebaute (< 1e-10); "
              f"lambda_max {mg.statistik['lambda_max']}, {t_mg:.1f} s {mg.statistik['zeiten_s']}",
              ok_inj and fehler < 1e-12 and gleich_frei and f_c < 1e-10, f"A {fehler:.1e}, C {f_c:.1e}, freie Moden gleich {gleich_frei}")


def test_nullraum():
    """Freie Starrkoerperbewegung (Kirsch: nur Normalen-Nitsche auf sym_x, sym_y -> u_z frei) wird am
    Grobgitter erkannt, am feinen Operator bestaetigt und herausprojiziert; gelagerte Modelle haben keinen
    Nullraum. Ohne Projektion sprang das Residuum bei h 10 von 1e-8 zurueck auf 1e-6 (147 bis 243 Iterationen)."""
    from volumen3d.fcm.mehrgitter import PMehrgitter
    for name, bau, erwartet in ((_faelle()[3][0], _faelle()[3][1], 1), (_faelle()[0][0], _faelle()[0][1], 0), (_faelle()[1][0], _faelle()[1][1], 0)):
        pr = bau()
        pr.aufbauen()
        mg = PMehrgitter(pr)
        k = mg.statistik["nullraum_dim"]
        ok = k == erwartet
        text = f"Nullraum {k} (erwartet {erwartet}), Warnungen {mg.statistik['warnungen']}"
        if erwartet and mg.nullraum is not None:
            # der Nullvektor ist die starre z-Verschiebung: nur u_z-Anteile, alle gleich (freie Koordinaten der Ecken)
            n = pr.zwaenge.C @ mg.nullraum[:, 0]
            u = n.reshape(-1, 3)
            anteil_z = np.linalg.norm(u[:, 2]) / np.linalg.norm(u)
            ok &= anteil_z > 0.999
            text += f", z-Anteil des Nullvektors {anteil_z:.4f}"
        check(f"{name}: Nullraum erkannt und bestaetigt wie erwartet", ok, text)


def test_symmetrie():
    """Der V-Zyklus als CG-Vorkonditionierer muss symmetrisch und positiv definit sein (Gutachten 28.09.2026:
    bisher nur ueber die Iterationszahlen belegt)."""
    from volumen3d.fcm.mehrgitter import PMehrgitter
    rng = np.random.default_rng(8)
    for name, bau, _ in (_faelle()[0], _faelle()[2]):
        pr = bau()
        pr.aufbauen()
        mg = PMehrgitter(pr)
        n = mg.ebenen[0].n_frei
        asym, rq = 0.0, np.inf
        for _ in range(5):
            x, y = rng.standard_normal(n), rng.standard_normal(n)
            Mx, My = mg.anwenden(x), mg.anwenden(y)
            asym = max(asym, abs(float(y @ Mx - x @ My)) / abs(float(y @ Mx)))
            rq = min(rq, float(x @ Mx) / float(x @ x))
        # Bezug der Schranke: die Grobgitterloesung (LU mit Pivotisierung) ist nur bis auf Kondition x
        # Rundung symmetrisch; die Blockinversen werden symmetrisiert (vorher 1,2e-9 bzw. 5,1e-9)
        check(f"{name}: V-Zyklus symmetrisch (|y^T M x - x^T M y| / |y^T M x| < 1e-8) und positiv (x^T M x > 0)",
              asym < 1e-8 and rq > 0, f"Asymmetrie {asym:.1e}, kleinster Rayleigh-Quotient {rq:.2e}")


def test_problem_mehrgitter():
    """FcmProblem(loeser='mehrgitter') am Kragarmsegment: Verschiebungen und Multiplikatoren wie der
    Sattelpunkt des Direktloesers - auch fuer eine reine Verdrehung ohne Last (f = 0, nur d, Gutachten
    28.09.2026: Residuumsprobe meldete dort faelschlich einen Fehler)."""
    from volumen3d.tests.test_kragarm import _segment

    def u_lin(P):
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([1e-3 * P[:, 0], -0.3e-3 * P[:, 1], -0.3e-3 * P[:, 2]], axis=1)

    def u_dreh(P):                                           # Verdrehung um die Stabachse x um 1e-3 rad
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([np.zeros(len(P)), -1e-3 * P[:, 2], 1e-3 * P[:, 1]], axis=1)

    for name, vorg in (("Zug/Querkontraktion", {"links": u_lin, "rechts": u_lin}), ("reine Verdrehung rechts, links fest", {"links": 0.0, "rechts": u_dreh})):
        ergebnisse = {}
        for loeser in ("direkt", "pcg", "mehrgitter"):
            pr = _segment(400.0, 600.0, 3, 50.0)
            # Mehrgitter bis 1e-12 (Vorgabe 9: 1e-6 gegen die Referenz; mit 1e-10 gemessen 4,3e-6 bei Grad 5), Jacobi 1e-10
            pr.loeser, pr.toleranz = loeser, (1e-12 if loeser == "mehrgitter" else 1e-10)
            t = time.perf_counter()
            U = pr.loesen(vorg)[:, 0]
            ergebnisse[loeser] = (U, pr.multiplikatoren[:, 0].copy(), pr.protokoll.get("iterationen"), time.perf_counter() - t, pr.protokoll["residuum"])
        U_d, lam_d = ergebnisse["direkt"][:2]
        for loeser in ("pcg", "mehrgitter"):
            U, lam, it, t, res = ergebnisse[loeser]
            fu = np.abs(U - U_d).max() / np.abs(U_d).max()
            fl = np.abs(lam - lam_d).max() / max(np.abs(lam_d).max(), 1.0)
            # Jacobi-PCG: Kondition ~1e7, bei tol 1e-10 gemessen 1,5e-5 in u (28.09.2026) - Referenzloeser ohne Mehrgitter
            grenze = 1e-6 if loeser == "mehrgitter" else 1e-4
            check(f"Kragarmsegment p 3, {name}, loeser={loeser}: Verschiebungen und Multiplikatoren wie direkt (< {grenze:g}); "
                  f"{it} Iterationen, Residuumsprobe {res:.1e}, {t:.1f} s", fu < grenze and fl < grenze, f"U {fu:.1e}, lambda {fl:.1e}")


def test_pcg_mehrgitter():
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.linalg.pcg import jacobi_diagonale, pcg
    for name, bau, vorgaben in _faelle():
        pr = bau()
        U_ref = pr.loesen(vorgaben)[:, 0]
        n = pr.gitter.n_dof
        C = pr.zwaenge.C
        z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
        pr._zelldaten = z
        op = Operator(z, C=C, K_rand=pr.K_rand)
        F = pr.rechte_seite(vorgaben)
        b = np.asarray(C.T @ F[:n]).ravel()
        B = np.asarray(pr._B @ C) if pr.n_zwaenge else None
        d = F[n:] if pr.n_zwaenge else None
        t = time.perf_counter()
        mg = PMehrgitter(pr)
        t_auf = time.perf_counter() - t
        # ein V-Zyklus als Loeser: Residuumsfaktor
        r0 = b - op.frei_anwenden(np.zeros_like(b))
        x1 = mg.anwenden(r0)
        faktor = np.linalg.norm(b - op.frei_anwenden(x1)) / np.linalg.norm(b)
        t = time.perf_counter()
        erg = pcg(op.frei_anwenden, b, mg.anwenden, tol=1e-10, B=B, d=d, max_iter=2000)
        t_mg = time.perf_counter() - t
        diag = jacobi_diagonale(z, C, pr.K_rand)
        t = time.perf_counter()
        erg_j = pcg(op.frei_anwenden, b, 1.0 / diag, tol=1e-10, B=B, d=d, max_iter=40000)
        t_j = time.perf_counter() - t
        U = np.asarray(C @ erg.x).ravel()
        P = np.concatenate([pr.quadratur.zelle(c)[0][pr.quadratur.zelle(c)[2]][:3] for c in range(0, len(pr.gitter.ijk), max(1, len(pr.gitter.ijk) // 100))])
        s_ref = pr.auswertung(U_ref).spannung(P)
        s = pr.auswertung(U).spannung(P)
        f_s = np.abs(s - s_ref).max() / max(np.abs(s_ref).max(), 1e-300)
        check(f"{name}: PCG mit V-Zyklus {erg.iterationen} Iterationen ({t_mg:.1f} s, Einrichten {t_auf:.1f} s) gegen Jacobi "
              f"{erg_j.iterationen} ({t_j:.1f} s); ein V-Zyklus reduziert das Residuum auf {faktor:.2e}; Spannungen wie Direktloeser < 1e-6; "
              f"Ebenen {mg.statistik['ebenen']}, lambda_max {mg.statistik['lambda_max']}",
              erg.konvergiert and f_s < 1e-6 and erg.iterationen < 100 and faktor < 0.5, f"Spannungen {f_s:.1e}")


def test_kern():
    """Kurzfassung fuer die Kernsuite: Schachtelung und V-Zyklus an Lame h 25 p 2."""
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.fcm.operator import Operator, Zelldaten
    from volumen3d.linalg.pcg import pcg
    from volumen3d.tests.test_operator import _lame
    from volumen3d.tests.test_pcg import _lame_mit_druck
    pr = _lame_mit_druck(_lame(p=2, h=25.0))
    pr.aufbauen()
    n = pr.gitter.n_dof
    C = pr.zwaenge.C
    z = Zelldaten(pr.gitter, pr.quadratur, pr.werkstoff.E, pr.werkstoff.nu)
    op = Operator(z, C=C, K_rand=pr.K_rand)
    mg = PMehrgitter(pr)
    x = np.random.default_rng(1).standard_normal(mg.ebenen[1].n_frei)
    fehler = np.abs(mg.ebenen[1].A(x) - mg.ebenen[1].P.T @ mg.ebenen[0].A(mg.ebenen[1].P @ x)).max()
    b = np.asarray(C.T @ pr.rechte_seite({})[:n]).ravel()
    erg = pcg(op.frei_anwenden, b, mg.anwenden, tol=1e-10, max_iter=500)
    U_ref = pr.loesen({})[:, 0]
    U = np.asarray(C @ erg.x).ravel()
    check(f"Kernsuite: p-Ebenen geschachtelt (< 1e-12) und PCG mit V-Zyklus in {erg.iterationen} Iterationen (< 100), Loesung wie Direktloeser",
          fehler / max(np.abs(x).max(), 1) < 1e-12 and erg.konvergiert and erg.iterationen < 100 and np.abs(U - U_ref).max() / np.abs(U_ref).max() < 1e-6,
          f"Schachtelung {fehler:.1e}, Iterationen {erg.iterationen}")


if __name__ == "__main__":
    sys.exit(lauf([test_ebenen, test_nullraum, test_symmetrie, test_problem_mehrgitter, test_pcg_mehrgitter]))
