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
        # grobe Matrizen (Teilmatrizen der feinen) gegen C_k^T (K_k + K_rand,k) C_k aus den Teilbloecken der
        # Zellmatrizen - unabhaengige Pruefung der Galerkin-Eigenschaft
        import scipy.sparse as sp
        from volumen3d.fcm.mehrgitter import _teilraum_indizes
        from volumen3d.fcm.operator import Zelldaten
        zd_f = mg.zelldaten_fein
        K_rand_f = pr.K_rand
        f_g = 0.0
        for k in range(1, len(mg.ebenen)):
            fe, eb = mg.ebenen[k - 1], mg.ebenen[k]
            sub = _teilraum_indizes(fe.p, eb.p)
            paare = np.unique(np.stack([fe.gitter.zell_moden[:, sub].ravel(), eb.gitter.zell_moden.ravel()], axis=1), axis=0)
            P3 = sp.kron(sp.csr_matrix((np.ones(len(paare)), (paare[:, 0], paare[:, 1])), shape=(fe.gitter.n_moden, eb.gitter.n_moden)),
                         sp.eye(3), format="csr")
            zd_k = Zelldaten.teilraum(zd_f, eb.gitter, sub)
            K_rand_k = (P3.T @ K_rand_f @ P3).tocsr()
            A_ind = (eb.C.T @ (zd_k.matrix() + K_rand_k) @ eb.C).tocsr()
            D = (A_ind - eb.A_matrix).tocsr()
            f_g = max(f_g, (float(np.abs(D.data).max()) if D.nnz else 0.0) / float(np.abs(A_ind.data).max()))
            zd_f, K_rand_f = zd_k, K_rand_k
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
              f"A_grob = P~^T A_fein P~ (< 1e-12), Teilmatrix = C^T K C aus Teilbloecken (< 1e-12), abgeleitete grobe Zwaenge "
              f"= unabhaengig gebaute (< 1e-10); lambda_max {mg.statistik['lambda_max']}, {t_mg:.1f} s {mg.statistik['zeiten_s']}",
              ok_inj and fehler < 1e-12 and f_g < 1e-12 and gleich_frei and f_c < 1e-10,
              f"A {fehler:.1e}, Galerkin {f_g:.1e}, C {f_c:.1e}, freie Moden gleich {gleich_frei}")


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


def test_nullkandidaten():
    """Die Nullraumerkennung haengt nicht an einer einzelnen Probe und nicht an der Groesse des Grobgitters.

    Synthetisch: A = Laplace-Kette mit freien Enden (Nullraum: Konstante), N = 20 000, verschobene Zerlegung wie
    im Mehrgitter (delta = 1e-10 max diag). Die erste Probe liegt senkrecht zur Konstanten - das Residuum dieser
    Probe ist dann Rundung, die fruehere Schwelle (> 1e-3) sah keinen Nullraum (Kirsch h 12: 9,8e-4, PCG
    divergierte). Erwartet: genau ein Kandidat, parallel zur Konstanten (|cos| > 1 - 1e-8); gelagerte Kette
    (erstes Ende fest) ohne Kandidaten, fuer zehn Zufallsstaende."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    from volumen3d.fcm.mehrgitter import grob_nullkandidaten
    N = 20_000
    haupt = np.full(N, 2.0); haupt[[0, -1]] = 1.0
    A_frei = sp.diags([-np.ones(N - 1), haupt, -np.ones(N - 1)], [-1, 0, 1], format="csc")
    A_fest = A_frei.copy().tolil(); A_fest[0, 0] = 2.0; A_fest = A_fest.tocsc()
    eins = np.ones(N) / np.sqrt(N)
    ok_frei, ok_fest, texte, fest_max = True, True, [], 0.0
    for seed in range(10):
        rng = np.random.default_rng(seed)
        for A, frei in ((A_frei, True), (A_fest, False)):
            delta = 1e-10 * float(A.diagonal().max())
            lu = spla.splu((A + delta * sp.eye(N, format="csc")).tocsc())
            X = rng.standard_normal((N, 6))
            X[:, 0] -= eins * (eins @ X[:, 0])                 # erste Probe ohne Nullanteil
            alt_probe = np.linalg.norm(X[:, 0] - lu.solve(A @ X[:, 0])) / np.linalg.norm(X[:, 0])
            K, s_w = grob_nullkandidaten(lambda R: lu.solve(A @ R), X)
            if frei:
                cos = abs(float(eins @ K[:, 0])) if K.shape[1] == 1 else 0.0
                ok_frei &= K.shape[1] == 1 and cos > 1 - 1e-8 and alt_probe < 1e-3
                texte.append(f"frei: {K.shape[1]} Kand., cos {cos:.10f}, alte Probe {alt_probe:.1e}")
            else:
                ok_fest &= K.shape[1] == 0
                fest_max = max(fest_max, float(s_w.max()))
    check("Nullraum der freien Kette erkannt, obwohl die erste Probe ihn nicht enthaelt (alte Schwelle versagt)", ok_frei, texte[0])
    check("gelagerte Kette: kein Nullraumkandidat (zehn Zufallsstaende)", ok_fest,
          f"groesster Singulaerwert {fest_max:.1e} (Schwelle 0,1)")


def test_nullkandidaten_mehrdimensional():
    """Mehrere freie Bewegungen und Mittelwertzwaenge (Gutachten 28.09.2026).

    k = 6 getrennte freie Laplace-Ketten (je 3000 Unbekannte, Nullraum: je eine Konstante) - so viele
    Nullvektoren wie ein ganz ungelagerter Koerper. Die Singulaerwerte der Nullvektoren sind die einer
    k x m-Gaussmatrix; mit den frueheren m = 6 Proben lag der kleinste fuer k = 6 mit rund 20 %
    Wahrscheinlichkeit unter der Schwelle 0,1. Erwartet mit _NULL_PROBEN: in allen zehn Zufallsstaenden
    genau sechs Kandidaten, die den Nullraum aufspannen (Hauptwinkel-Cosinus > 1 - 1e-8). Zum Vergleich wird
    gezaehlt, wie oft sechs Proben einen Nullvektor verloren haetten.
    Sattelpunkt: zwei freie Ketten, eine Mittelwertzeile sperrt die Konstante der ersten; der Loeser des
    Sattelpunkts filtert sie heraus, uebrig bleibt genau die Konstante der zweiten Kette."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    from volumen3d.fcm.mehrgitter import _NULL_PROBEN, grob_nullkandidaten

    def kette(n):
        haupt = np.full(n, 2.0); haupt[[0, -1]] = 1.0
        return sp.diags([-np.ones(n - 1), haupt, -np.ones(n - 1)], [-1, 0, 1])

    k, n = 6, 3000
    A = sp.block_diag([kette(n)] * k, format="csc")
    N = np.zeros((k * n, k))
    for i in range(k):
        N[i * n:(i + 1) * n, i] = 1.0 / np.sqrt(n)
    delta = 1e-10 * float(A.diagonal().max())
    lu = spla.splu((A + delta * sp.eye(k * n, format="csc")).tocsc())
    ok, verloren_6, cos_min = True, 0, 1.0
    for seed in range(10):
        rng = np.random.default_rng(seed)
        for m, zaehlen in ((_NULL_PROBEN, False), (6, True)):
            K, _ = grob_nullkandidaten(lambda R: lu.solve(A @ R), rng.standard_normal((k * n, m)))
            if zaehlen:
                verloren_6 += int(K.shape[1] < k)
                continue
            if K.shape[1] != k:
                ok = False
                continue
            c = float(np.linalg.svd(N.T @ K, compute_uv=False).min())
            cos_min = min(cos_min, c)
            ok &= c > 1 - 1e-8
    check(f"sechs freie Bewegungen mit {_NULL_PROBEN} Proben in allen zehn Staenden erkannt (mit 6 Proben in {verloren_6} von 10 "
          f"Staenden ein Nullvektor verloren)", ok, f"kleinster Hauptwinkel-Cosinus {cos_min:.10f}")
    # Sattelpunkt mit Mittelwertzwang auf der ersten Kette
    n2 = 2000
    A2 = sp.block_diag([kette(n2), kette(n2)], format="csr")
    B = np.zeros((1, 2 * n2)); B[0, :n2] = 1.0 / n2
    d2 = 1e-10 * float(A2.diagonal().max())
    S = sp.bmat([[A2 + d2 * sp.eye(2 * n2), sp.csr_matrix(B).T], [sp.csr_matrix(B), None]], format="csc")
    lu2 = spla.splu(S)
    K2, s2 = grob_nullkandidaten(lambda R: lu2.solve(np.concatenate([A2 @ R, B @ R], axis=0))[:2 * n2],
                                 np.random.default_rng(3).standard_normal((2 * n2, _NULL_PROBEN)))
    e2 = np.zeros(2 * n2); e2[n2:] = 1.0 / np.sqrt(n2)
    c2 = abs(float(e2 @ K2[:, 0])) if K2.shape[1] == 1 else 0.0
    check("Sattelpunkt: die von B gesperrte Bewegung faellt heraus, die freie bleibt (genau ein Kandidat)",
          K2.shape[1] == 1 and c2 > 1 - 1e-8, f"{K2.shape[1]} Kandidat(en), Cosinus {c2:.10f}, Singulaerwerte {np.round(s2[:3], 4).tolist()}")


def test_p1_und_gleichgewicht():
    """p = 1 (nur eine Ebene, das Grobgitter ist der ganze Operator) und eine Last in Richtung der freien
    Bewegung (Gutachten 28.09.2026). Erwartet: bei p = 1 ist der V-Zyklus die Grobgitterloesung selbst, bis auf
    die Verschiebung delta die exakte Inverse; der PCG konvergiert in hoechstens fuenf Iterationen (gemessen 4)
    und trifft den Direktloeser auf 1e-8; eine z-Last auf die Kirsch-Scheibe (u_z frei) wird sofort als
    Last nicht im Gleichgewicht gemeldet, statt 1000 Iterationen bis 'nicht konvergiert' zu laufen."""
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.linalg.pcg import pcg
    from volumen3d.tests.test_operator import _kirsch
    from volumen3d.tests.test_kirsch import L
    pr = _kirsch(p=1)
    pr.aufbauen()
    n = pr.gitter.n_dof
    C = pr.zwaenge.C
    mg = PMehrgitter(pr)
    b = np.asarray(C.T @ pr.rechte_seite({})[:n]).ravel()
    erg = pcg(lambda x: mg.ebenen[0].A(x), b, mg.anwenden, tol=1e-12, max_iter=50)
    U = np.asarray(C @ erg.x).ravel()
    U_ref = pr.loesen({})[:, 0]
    # Spannungen statt Verschiebungen: u_z ist frei, der Direktloeser liefert dafuer einen beliebigen Anteil,
    # das Mehrgitter projiziert ihn heraus
    rng = np.random.default_rng(6)
    P = rng.uniform([0, 0, 0], [400, 200, 10], (4000, 3))
    P = P[pr.geometrie.abstand(P) < -0.5][:300]
    s_mg, s_ref = pr.auswertung(U).spannung(P), pr.auswertung(U_ref).spannung(P)
    f = np.abs(s_mg - s_ref).max() / np.abs(s_ref).max()
    check("p = 1: eine Ebene, PCG in <= 5 Iterationen, Spannungen wie direkt (< 1e-8)",
          len(mg.ebenen) == 1 and erg.konvergiert and erg.iterationen <= 5 and f < 1e-8,
          f"Ebenen {len(mg.ebenen)}, Iterationen {erg.iterationen}, Abweichung {f:.1e}, Nullraum {mg.statistik['nullraum_dim']}")
    pr2 = _kirsch(p=2, verfeinert=True)
    stirn = pr2.oberflaeche.auswahl((pr2.oberflaeche.name.astype(str) == "platte") & (np.abs(pr2.oberflaeche.punkte[:, 0] - L / 2) < 1e-6))
    pr2.traktion(None, np.array([0.0, 0.0, 1.0]), quadratur=stirn)
    pr2.loeser = "mehrgitter"
    pr2.aufbauen()
    t = time.perf_counter()
    try:
        pr2.loesen({})
        meldung = ""
    except ValueError as ex:
        meldung = str(ex)
    dt = time.perf_counter() - t
    check("z-Last bei freier z-Bewegung: sofort 'Last nicht im Gleichgewicht' statt Stagnation",
          meldung.startswith("Last nicht im Gleichgewicht") and dt < 30.0, f"{meldung!r}, {dt:.1f} s")


def _schwarz_probe():
    """Kuenstlicher Fall mit einem grossen Block (Zelle 0 beruehrt 2000 freie Koordinaten) und 50 kleinen
    (je 6, Einheitszeilen): C, Zellfreiheitsgrade, SPD-Matrix A und die unabhaengige Referenz
    z = sum_i R_i^T A[S_i, S_i]^-1 R_i r mit numpy."""
    import scipy.sparse as sp
    rng = np.random.default_rng(11)
    gross, n_klein, n3 = 2000, 50, 6
    n = gross + n_klein * n3
    zeilen, spalten = [], []
    for r in range(n3):
        c = np.arange(r, gross, n3)
        zeilen += [r] * len(c)
        spalten += list(c)
    zeilen += list(range(n3, n3 + n_klein * n3))
    spalten += list(range(gross, n))
    C = sp.csr_matrix((np.ones(len(zeilen)), (zeilen, spalten)), shape=(n3 + n_klein * n3, n))
    dofs = np.arange(n3 + n_klein * n3).reshape(-1, n3)
    M = rng.standard_normal((n, n)) / np.sqrt(n)
    A_dicht = M @ M.T + np.eye(n)
    A = sp.csr_matrix(A_dicht)
    r = rng.standard_normal(n)
    z_ref = np.zeros(n)
    for c in range(dofs.shape[0]):
        S = np.unique(C[dofs[c]].indices)
        z_ref[S] += np.linalg.solve(A_dicht[np.ix_(S, S)], r[S])
    return C, dofs, A, r, z_ref


def test_schwarz_grosse_bloecke():
    """Glaetterbloecke ueber _EINZELN_AB werden einzeln (LAPACK im Hauptfaden) invertiert; der Glaetter wendet
    genau die Blockinversen an (gegen numpy, < 1e-10). Anlass: Block h 14 p 3 mit einem Block der Groesse 2463,
    in der gestapelten Inversion 8,6 s (A1, Plan TP 5)."""
    from volumen3d.fcm.mehrgitter import _EINZELN_AB, ZellSchwarz
    C, dofs, A, r, z_ref = _schwarz_probe()
    t = time.perf_counter()
    sw = ZellSchwarz(C, dofs, A, geraet="cpu")
    dt = time.perf_counter() - t
    f = float(np.abs(sw.anwenden(r) - z_ref).max() / np.abs(z_ref).max())
    groessen = sorted(int(I.shape[1]) for I, _ in sw.gruppen)
    check(f"Schwarz CPU mit einem Block der Groesse 2000 (> {_EINZELN_AB}) und 50 kleinen: Blockinversen exakt (< 1e-10)",
          f < 1e-10 and groessen == [6, 2000], f"Abweichung {f:.1e}, Gruppen {groessen}, Einrichten {dt:.2f} s")


def test_chebyshev_fenster():
    """Chebyshev-Fenster des Glaetters [lambda_max/100, lambda_max] statt [lambda_max/16, lambda_max] (Plan TP 5, A5):
    lambda_max von M^-1 A sitzt im Uebergangsguertel des Oktrees und wandert mit der Schnittlage, das schmale
    Fenster liess darunter je nach Lage Moden liegen. Kirsch h 20 p 3 verfeinert, Versatz 0,4 (zwei halb
    gefuellte Zellschichten ueber die Dicke), CPU: der Standard braucht hoechstens 85 % der Iterationen von
    alpha 16, die Spannungen stimmen ueberein (< 1e-6). Auf der GPU gemessen (h 10 und h 8, je fuenf Lagen):
    24,8 statt 33,0 und 30,6 statt 39,6 Iterationen im Mittel."""
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.fcm.mehrgitter import PMehrgitter
    from volumen3d.linalg.pcg import pcg
    from volumen3d.tests.test_kirsch import D, T, _platte
    h = 20.0
    pr = _platte(3, h, versatz=0.4, verfeinerung=Verfeinerung(bereiche=((np.array([0.0, 0.0, T / 2]), D / 2 + 10.0, h / 4),)))
    pr.loeser = "pcg"
    pr.aufbauen()
    n = pr.gitter.n_dof
    C = pr.zwaenge.C
    b = np.asarray(C.T @ pr.rechte_seite({})[:n]).ravel()
    P = np.concatenate([pr.quadratur.zelle(c)[0][pr.quadratur.zelle(c)[2]][:3] for c in range(0, len(pr.gitter.ijk), max(1, len(pr.gitter.ijk) // 100))])
    erg = {}
    for name, mg in (("alpha 16", PMehrgitter(pr, alpha=16.0)), ("Standard", PMehrgitter(pr))):
        e = pcg(pr._operator.frei_anwenden, b, mg.anwenden, tol=1e-10, max_iter=500)
        erg[name] = (e.iterationen, e.konvergiert, pr.auswertung(np.asarray(C @ e.x).ravel()).spannung(P), mg.alpha)
    (i16, k16, s16, _), (i_s, k_s, s_s, a_s) = erg["alpha 16"], erg["Standard"]
    f = float(np.abs(s_s - s16).max() / np.abs(s16).max())
    check(f"Kirsch h 20 p 3 Versatz 0,4: Standardfenster (alpha {a_s:g}) {i_s} Iterationen <= 85 % von alpha 16 ({i16}), "
          f"Spannungen gleich (< 1e-6)", k16 and k_s and a_s == 100.0 and i_s <= 0.85 * i16 and f < 1e-6, f"Spannungen {f:.1e}")


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
    a_g = mg.ebenen[1].A(x)                                   # Teilmatrix der assemblierten Matrix
    a_f = mg.ebenen[1].P.T @ mg.ebenen[0].A(mg.ebenen[1].P @ x)  # feiner Operator matrixfrei
    fehler = np.abs(a_g - a_f).max() / np.abs(a_f).max()      # relativ (Eintraege ~1e6)
    b = np.asarray(C.T @ pr.rechte_seite({})[:n]).ravel()
    erg = pcg(op.frei_anwenden, b, mg.anwenden, tol=1e-10, max_iter=500)
    U_ref = pr.loesen({})[:, 0]
    U = np.asarray(C @ erg.x).ravel()
    check(f"Kernsuite: p-Ebenen geschachtelt (< 1e-12) und PCG mit V-Zyklus in {erg.iterationen} Iterationen (< 100), Loesung wie Direktloeser",
          fehler < 1e-12 and erg.konvergiert and erg.iterationen < 100 and np.abs(U - U_ref).max() / np.abs(U_ref).max() < 1e-6,
          f"Schachtelung {fehler:.1e}, Iterationen {erg.iterationen}")


if __name__ == "__main__":
    sys.exit(lauf([test_ebenen, test_nullkandidaten, test_nullkandidaten_mehrdimensional, test_p1_und_gleichgewicht, test_nullraum, test_schwarz_grosse_bloecke, test_chebyshev_fenster, test_symmetrie, test_problem_mehrgitter, test_pcg_mehrgitter]))
