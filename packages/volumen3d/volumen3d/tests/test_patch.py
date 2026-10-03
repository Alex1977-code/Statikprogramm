"""T4: Patch-Test. Schraeg durch zwei Halbraeume geschnittener Quader (viele CUT-Zellen),
lineares Verschiebungsfeld ueber Nitsche auf dem ganzen Rand; die Loesung muss das Feld auf
1e-6 treffen (Vorgabe Abschnitt 13: "exakt, Fehler < 1e-6"). Dazu die Konsistenz von Nitsche
gegen beta und der Einfluss von alpha.

Aufruf: python -m volumen3d.tests.test_patch
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

A = np.array([[1e-3, 2e-4, -3e-4], [4e-4, -5e-4, 6e-4], [-7e-4, 8e-4, 9e-4]])
B0 = np.array([0.1, -0.2, 0.3])
E, NU = 210000.0, 0.3


def u_exakt(P):
    return np.asarray(P, float).reshape(-1, 3) @ A.T + B0


def sigma_exakt():
    from volumen3d.fcm.elastizitaet import d_matrix
    eps = 0.5 * (A + A.T)
    return d_matrix(E, NU) @ np.array([eps[0, 0], eps[1, 1], eps[2, 2], 2 * eps[0, 1], 2 * eps[1, 2], 2 * eps[0, 2]])


def _problem(p, alpha, h=20.0, beta_faktor=10.0, aggregation=0.25, extra=()):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "quader"},
        {"typ": "halbraum", "punkt": [60, 50, 50], "normale": [1, 2, 3], "name": "s1"},
        {"typ": "halbraum", "punkt": [30, 40, 70], "normale": [-2, 1, 1.5], "name": "s2"}] + list(extra)}})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), alpha=alpha, beta_faktor=beta_faktor, aggregation=aggregation)
    pr.verschiebungsrand("alles", None, projektion="voll")
    return pr


def _fehler(pr, U):
    aus = pr.auswertung(U)
    rng = np.random.default_rng(4)
    P = rng.uniform(0, 100, (4000, 3))
    P = P[pr.geometrie.abstand(P) < -0.5][:1500]
    eu = np.abs(aus.verschiebung(P) - u_exakt(P)).max() / np.abs(u_exakt(P)).max()
    es = np.abs(aus.spannung(P) - sigma_exakt()).max() / np.abs(sigma_exakt()).max()
    # auch direkt an der Oberflaeche (Punkte der Flaechenquadratur, minimal nach innen gerueckt)
    Po = pr.oberflaeche.punkte - 1e-6 * pr.gitter.h * pr.oberflaeche.normalen
    eo = np.abs(aus.spannung(Po[::7]) - sigma_exakt()).max() / np.abs(sigma_exakt()).max()
    return eu, es, eo


def test_patch():
    for p in (1, 2, 3):
        t = time.perf_counter()
        pr = _problem(p, 1e-8)
        pr.aufbauen()
        U = pr.loesen({"alles": u_exakt})[:, 0]
        eu, es, eo = _fehler(pr, U)
        ag = pr.protokoll["aggregation"]
        info = (f"u {eu:.1e}, sigma innen {es:.1e}, sigma Rand {eo:.1e}; cut {pr.protokoll['cut']}/{pr.protokoll['zellen']} Zellen, "
                f"dofs {pr.protokoll['dofs']} ({pr.protokoll['dofs_frei']} frei), Aggregation: {ag['zellen_schlecht']} Zellen, "
                f"{ag['moden_gebunden']} Moden, kleinster Anteil {ag['anteil_min']:.1e}; {time.perf_counter() - t:.1f} s")
        check(f"p={p}: Verschiebung relativ < 1e-6", eu < 1e-6, info)
        check(f"p={p}: Spannung innen und am Rand relativ < 1e-6", es < 1e-6 and eo < 1e-6)


def _polynomfeld(k):
    """Allgemeines Polynomfeld vom Gesamtgrad k (alle Komponenten gekoppelt): lineares Feld des Patch-Tests plus quadratischer und kubischer Anteil um die
    Koerpermitte. Rueckgabe u(P), sigma(P) (Voigt xx yy zz xy yz xz), f(P) = -div sigma aus dem zentralen Differenzenquotienten der Spannung - fuer sigma bis
    zum Grad 2 exakt (bis auf Rundung)."""
    from volumen3d.fcm.elastizitaet import d_matrix
    D = d_matrix(E, NU)
    rng = np.random.default_rng(7)
    Q2 = rng.uniform(-1, 1, (3, 3, 3)) * 1e-5
    Q2 = 0.5 * (Q2 + Q2.transpose(0, 2, 1))                                    # symmetrisch in den beiden Ortsindizes
    C3 = rng.uniform(-1, 1, (3, 3, 3, 3)) * 1e-7
    C3 = (C3 + C3.transpose(0, 1, 3, 2) + C3.transpose(0, 2, 1, 3) + C3.transpose(0, 2, 3, 1) + C3.transpose(0, 3, 1, 2) + C3.transpose(0, 3, 2, 1)) / 6.0
    x0 = np.array([50.0, 50.0, 50.0])

    def u(P):
        x = np.asarray(P, float).reshape(-1, 3) - x0
        v = u_exakt(P).copy()
        if k >= 2:
            v += 0.5 * np.einsum("ijk,nj,nk->ni", Q2, x, x)
        if k >= 3:
            v += np.einsum("ijkl,nj,nk,nl->ni", C3, x, x, x) / 6.0
        return v

    def sig(P):
        x = np.asarray(P, float).reshape(-1, 3) - x0
        G = np.broadcast_to(A, (len(x), 3, 3)).copy()
        if k >= 2:
            G += np.einsum("ilk,nk->nil", Q2, x)
        if k >= 3:
            G += 0.5 * np.einsum("imkl,nk,nl->nim", C3, x, x)
        e = 0.5 * (G + G.transpose(0, 2, 1))
        return np.stack([e[:, 0, 0], e[:, 1, 1], e[:, 2, 2], 2 * e[:, 0, 1], 2 * e[:, 1, 2], 2 * e[:, 0, 2]], axis=1) @ D.T

    voigt = ((0, 3, 5), (3, 1, 4), (5, 4, 2))                                  # Voigt-Index von sigma_ij

    def f(P):
        P = np.asarray(P, float).reshape(-1, 3)
        aus = np.zeros((len(P), 3))
        for j in range(3):
            e = np.zeros(3)
            e[j] = 1.0
            d = 0.5 * (sig(P + e) - sig(P - e))                                # d sigma / d x_j
            for i in range(3):
                aus[:, i] -= d[:, voigt[i][j]]
        return aus
    return u, sig, f, Q2


def _lastvektor(pr, f):
    """Volumenlast f(P) ueber die Zellquadratur (rand.volumenlast kennt nur konstante Lasten)."""
    from volumen3d.fcm.basis import basis_3d
    g = pr.gitter
    F = np.zeros(g.n_dof)
    for c in range(len(g.ijk)):
        P, W, I = pr.quadratur.zelle(c)
        if len(P) and I.any():
            N, _ = basis_3d(g.p, g.lokal(P[I], np.full(int(I.sum()), c)))
            F[g.zell_dofs(c)] += ((N * W[I][:, None]).T @ f(P[I])).ravel()
    return F


def _polynomfehler(p, k, **kw):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "quader"},
        {"typ": "halbraum", "punkt": [60, 50, 50], "normale": [1, 2, 3], "name": "s1"},
        {"typ": "halbraum", "punkt": [30, 40, 70], "normale": [-2, 1, 1.5], "name": "s2"}]}})
    pr = FcmProblem(g, h=20.0, p=p, werkstoff=Werkstoff(E, NU), **kw)
    pr.verschiebungsrand("alles", None, projektion="voll")
    u, sig, f, _ = _polynomfeld(k)
    U = pr.loesen({"alles": u}, zusatzlasten=[_lastvektor(pr, f)])[:, 0]
    aus = pr.auswertung(U)
    rng = np.random.default_rng(4)
    P = rng.uniform(0, 100, (4000, 3))
    P = P[pr.geometrie.abstand(P) < -0.5][:1500]
    Po = (pr.oberflaeche.punkte - 1e-6 * pr.gitter.h * pr.oberflaeche.normalen)[::7]
    gross = np.abs(sig(P)).max()
    return (float(np.abs(aus.spannung(P) - sig(P)).max() / gross), float(np.abs(aus.spannung(Po) - sig(Po)).max() / gross), pr)


def test_patch_hoeherer_ordnung():
    """Patch-Test hoeherer Ordnung (Plan TP 5 O5, Theorie 11.21): ein Polynomfeld vom Gesamtgrad k <= p liegt im Ansatzraum und muss am schraeg geschnittenen
    Koerper bis auf Rundung reproduziert werden. Bis 03.10.2026 galt das nur fuer k = 1: die Tetraederregel der schraegen Stuecke war bis zum Gesamtgrad 3p - 1
    (p gerade) exakt, noetig sind 3p + k - 2; die Flaechenregel bis 3p (p ungerade), noetig sind 3p + k - 1. Gemessen vorher / jetzt (Spannung am Rand):
    p 2 k 2 2,6e-4 / 2,0e-11 bis 2,6e-11; p 3 k 2 1,9e-4 / 1,2e-9 bis 2,3e-9; p 3 k 3 2,2e-4 / 8,1e-10 bis 1,4e-9 (je sechs Laeufe am 03.10.2026: der Wert liegt auf
    Rundungsniveau und streut von Lauf zu Lauf um den Faktor 2). Schranke 1e-8 bei p 2 und 1e-7 bei p 3: bei p 3 gibt die Zwangsmatrix Polynome nur auf rund 1e-9
    wieder (11.21, H4), und 1e-8 liess dem groessten Messwert nur das Vierfache - eine Pruefung gleicher Art (test_haengende_moden, 1e-8) fiel am selben Tag in
    der CI mit 1,7e-8 durch. Der alte Weg liegt mit 1e-5 bis 1e-4 um mehr als zwei Groessenordnungen ueber beiden Schranken."""
    from volumen3d.fcm import quadratur as Q
    # Gegenprobe der Volumenlast am quadratischen Feld: f_i = -[lambda Q_mmi + mu (Q_ijj + Q_jij)], unabhaengig vom Differenzenquotienten
    u, sig, f, Q2 = _polynomfeld(2)
    lam, mu = E * NU / ((1 + NU) * (1 - 2 * NU)), E / (2 * (1 + NU))
    f_formel = -(lam * np.einsum("mmi->i", Q2) + mu * (np.einsum("ijj->i", Q2) + np.einsum("jij->i", Q2)))
    d_f = float(np.abs(f(np.array([[10.0, 20.0, 30.0], [70.0, 5.0, 90.0]])) - f_formel).max() / np.abs(f_formel).max())
    check(f"Volumenlast des quadratischen Felds: Differenzenquotient der Spannung gleich der Formel ({d_f:.1e} < 1e-12)", d_f < 1e-12)
    for p, k in ((2, 2), (3, 2), (3, 3)):
        t = time.perf_counter()
        es, eo, pr = _polynomfehler(p, k)
        st = pr.quadratur.statistik
        schranke = 1e-8 if p == 2 else 1e-7
        check(f"p {p}, Feld vom Grad {k}: Spannung innen {es:.1e} und am Rand {eo:.1e} (< {schranke:.0e})", es < schranke and eo < schranke,
              f"{st['stuecke_exakt']} schraege Stuecke mit exakten Momenten (von {st['stuecke']} Stuecken, die uebrigen achsparallele Teilboxen), "
              f"Flaechenordnung {pr.ordnung_flaeche}, "
              f"Zellen ohne Wurzel {pr.protokoll['aggregation']['zellen_ohne_wurzel'] if pr.protokoll.get('aggregation') else pr.aggregation.statistik['zellen_ohne_wurzel']}, "
              f"{time.perf_counter() - t:.1f} s")
    # ohne die beiden Aenderungen (zum Vergleich, damit die Pruefung oben nicht leer ist): Tetraederregel bei p 2, alte Flaechenordnung 5 bei p 3
    Q.STUECKE_EXAKT_STANDARD = False
    try:
        es2, eo2, _ = _polynomfehler(2, 2)
    finally:
        Q.STUECKE_EXAKT_STANDARD = True
    es3, eo3, _ = _polynomfehler(3, 2, ordnung_flaeche=5)
    check(f"zum Vergleich: p 2 k 2 mit der Tetraederregel {es2:.1e} / {eo2:.1e} (> 1e-5), p 3 k 2 mit der Flaechenordnung 5 {es3:.1e} / {eo3:.1e} (> 1e-6)",
          min(es2, eo2) > 1e-5 and max(es3, eo3) > 1e-6)


def test_ohne_aggregation():
    """Messung ohne Zellaggregation (Begruendung der Massnahme): Zellen mit Werkstoffanteil 2,8e-5 treiben den Fehler des linearen Felds auf 1e-4 bis 1e-2,
    und alpha kleiner zu waehlen hilft nicht verlaesslich. Gemessen am 03.10.2026 (exakte Stueckmomente, Plan TP 5 O5) bei alpha 1e-6 / 1e-7 / 1e-8 / 1e-9 /
    1e-10 / 1e-12: 3,2e-2 / 5,1e-2 / 7,8e-4 / 4,3e-4 / 1,8e-4 / 2,5e-5 - nicht monoton. Mit der Tetraederregel davor: 3,5e-2 / 6,0e-3 / 1,4e-2 / 4,1e-4 / 1,4e-4 /
    1,0e-5, ebenfalls nicht monoton; die fruehere Pruefung 'Faktor > 30 zwischen 1e-8 und 1e-10' traf nur das eine Wertepaar 1,4e-2 / 1,4e-4 und war kein Gesetz.
    Geprueft wird, was traegt: ohne Aggregation liegt der Fehler bei alpha 1e-8 und 1e-10 ueber 1e-5 (rund ein Achtzehntel des kleineren Messwerts), mit
    Aggregation unter 1e-6 (test_patch)."""
    werte = {}
    for a in (1e-8, 1e-10):
        pr = _problem(2, a, aggregation=None)
        U = pr.loesen({"alles": u_exakt})[:, 0]
        werte[a] = _fehler(pr, U)[1]
    check("ohne Aggregation: Spannungsfehler des linearen Felds bei alpha 1e-8 und 1e-10 ueber 1e-5 (mit Aggregation unter 1e-6)",
          min(werte.values()) > 1e-5, f"1e-8: {werte[1e-8]:.1e}, 1e-10: {werte[1e-10]:.1e}")


def test_kleine_schnittzellen():
    """Vorgabe 13: gezielt erzeugte Schnittanteile 1e-6 - Loesung bleibt exakt, keine Ausreisser."""
    # dritter Halbraum schneidet eine Zellschicht bis auf 1e-6 h ab: Zellen der Schicht x in [80, 100] behalten 2e-5 mm
    extra = ({"typ": "halbraum", "punkt": [80.0 + 2e-5, 0, 0], "normale": [1, 0, 0], "name": "s3"},)
    pr = _problem(2, 1e-8, extra=extra)
    ag = pr.protokoll if pr.K is not None else None
    U = pr.loesen({"alles": u_exakt})[:, 0]
    eu, es, eo = _fehler(pr, U)
    ag = pr.protokoll["aggregation"]
    check("Schnittanteil 1e-6: Aggregation greift (kleinster Anteil < 1e-5, Zellen gebunden)", ag["anteil_min"] < 1e-5 and ag["zellen_schlecht"] > 0, str(ag))
    check("Schnittanteil 1e-6: u und sigma weiter < 1e-6, keine Ausreisser", eu < 1e-6 and es < 1e-6 and eo < 1e-6, f"u {eu:.1e}, sigma {es:.1e}, Rand {eo:.1e}")
    check("alle Werte endlich", np.all(np.isfinite(U)))


def test_alpha_und_beta():
    pr = _problem(2, 1e-10)
    U = pr.loesen({"alles": u_exakt})[:, 0]
    eu, es, _ = _fehler(pr, U)
    check("alpha = 1e-10: weiter < 1e-6", eu < 1e-6 and es < 1e-6, f"u {eu:.1e}, sigma {es:.1e}")
    pr = _problem(2, 1e-8, beta_faktor=100.0)
    U = pr.loesen({"alles": u_exakt})[:, 0]
    eu, es, _ = _fehler(pr, U)
    check("Nitsche konsistent: beta-Faktor 100 statt 10 aendert die exakte Loesung nicht (< 1e-6)", eu < 1e-6 and es < 1e-6, f"u {eu:.1e}, sigma {es:.1e}")


def test_normalprojektion():
    """Symmetrie-Nitsche: nur die Normalkomponente wird vorgegeben. Wuerfel mit u_n = 0 auf
    x=0, y=0, z=0 und Zug sigma_xx = 100 auf x=100: Loesung eps_xx = 100/E, Querkontraktion frei."""
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [-3, -3, -3], "max": [100, 100, 100], "name": "w"},
        {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [-1, 0, 0], "name": "sx"},
        {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, -1, 0], "name": "sy"},
        {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, 0, -1], "name": "sz"}]}})
    pr = FcmProblem(g, h=25.0, p=2, werkstoff=Werkstoff(E, NU), polster=0.17)
    for s in ("sx", "sy", "sz"):
        pr.verschiebungsrand(s, s, projektion="normal")
    stirn = pr.oberflaeche.auswahl((pr.oberflaeche.name.astype(str) == "w") & (np.abs(pr.oberflaeche.punkte[:, 0] - 100.0) < 1e-9))
    pr.traktion(None, np.array([100.0, 0, 0]), quadratur=stirn)
    U = pr.loesen({})[:, 0]
    aus = pr.auswertung(U)
    P = np.array([[50, 50, 50.0], [90, 10, 30], [10, 80, 70]])
    u = aus.verschiebung(P)
    s = aus.spannung(P)
    soll = np.stack([100.0 / E * P[:, 0], -NU * 100.0 / E * P[:, 1], -NU * 100.0 / E * P[:, 2]], axis=1)
    check("einachsiger Zug mit Symmetrieebenen: u = (eps x, -nu eps y, -nu eps z) < 1e-6",
          np.abs(u - soll).max() / np.abs(soll).max() < 1e-6, f"{np.abs(u - soll).max() / np.abs(soll).max():.1e}")
    check("sigma_xx = 100, sonst 0 (< 1e-6)", abs(s[:, 0] - 100).max() < 1e-4 and np.abs(s[:, 1:]).max() < 1e-4, str(s[0]))


if __name__ == "__main__":
    sys.exit(lauf([test_patch, test_patch_hoeherer_ordnung, test_ohne_aggregation, test_kleine_schnittzellen, test_alpha_und_beta, test_normalprojektion]))
