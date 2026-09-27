"""T4: Patch-Test. Schraeg durch zwei Halbraeume geschnittener Quader (viele CUT-Zellen),
lineares Verschiebungsfeld ueber Nitsche auf dem ganzen Rand; die Loesung muss das Feld auf
1e-6 treffen (Vorgabe Abschnitt 13: "exakt, Fehler < 1e-6"). Dazu die Konsistenz von Nitsche
gegen beta und der Einfluss von alpha.

Aufruf: python -m tests.volumen3d.test_patch
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from tests.volumen3d._pruef import check, lauf  # noqa: E402

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


def test_ohne_aggregation():
    """Messung des alpha-Effekts ohne Zellaggregation (Begruendung der Massnahme): Fehler ~ alpha / Anteil."""
    werte = {}
    for a in (1e-8, 1e-10):
        pr = _problem(2, a, aggregation=None)
        U = pr.loesen({"alles": u_exakt})[:, 0]
        werte[a] = _fehler(pr, U)[1]
    check("ohne Aggregation: Spannungsfehler skaliert mit alpha (Faktor > 30 zwischen 1e-8 und 1e-10) und liegt ueber 1e-6",
          werte[1e-8] / werte[1e-10] > 30 and werte[1e-8] > 1e-6, f"1e-8: {werte[1e-8]:.1e}, 1e-10: {werte[1e-10]:.1e}")


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
    sys.exit(lauf([test_patch, test_ohne_aggregation, test_kleine_schnittzellen, test_alpha_und_beta, test_normalprojektion]))
