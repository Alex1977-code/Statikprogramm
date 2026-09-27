"""T5: Schnittgroessen und Kopplung.

(a) Reine Biegung: exakte 3D-Loesung (quadratisches Feld) ueber Nitsche auf beiden
    Schnittebenen -> Schnittgroessen und Feld exakt (1e-6).
(b) Vertrags-Stub (Euler-Bernoulli-Kragarm): Moment < 1 %; die Querkraft-Abweichung wird
    durch die fehlende Schubverformung der Balkentheorie erklaert (Timoshenko-Anteil im Test
    berechnet) - ebene Querschnitte ohne Schubverformung auf beiden Schnittebenen erzwingen
    eine kleinere Querkraft als die Balkentheorie meldet.

Aufruf: python -m volumen3d.tests.test_kragarm   (~1 min)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

E, NU, L, B, H, F = 210000.0, 0.3, 1000.0, 100.0, 200.0, 10000.0
I = B * H ** 3 / 12


def _segment(x0, x1, p, h, polster=0.13, projektion="schnitt"):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [x0 - 5, -B / 2, -H / 2], "max": [x1 + 5, B / 2, H / 2], "name": "balken"},
        {"typ": "halbraum", "punkt": [x0, 0, 0], "normale": [-1, 0, 0], "name": "links"},
        {"typ": "halbraum", "punkt": [x1, 0, 0], "normale": [1, 0, 0], "name": "rechts"}]}})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), polster=polster)
    pr.verschiebungsrand("links", "links", projektion=projektion)
    pr.verschiebungsrand("rechts", "rechts", projektion=projektion)
    return pr


def test_reine_biegung():
    M = 5e6

    def u(P):
        x, y, z = np.asarray(P, float).T
        return np.stack([-M * x * z / (E * I), NU * M * y * z / (E * I), M * (x ** 2 + NU * (z ** 2 - y ** 2)) / (2 * E * I)], axis=1)

    # sigma_xx = -M z / I gehoert zu M_y = -M (Stabkonvention sigma_xx = +M_y z / I):
    # rechte Ebene (+x) M_y = -M, linke Ebene (-x, Normale nach aussen) M_y = +M
    for projektion in ("schnitt", "voll"):
        t = time.perf_counter()
        pr = _segment(400.0, 600.0, 2, 50.0, projektion=projektion)
        U = pr.loesen({"links": u, "rechts": u})[:, 0]
        aus = pr.auswertung(U)
        Fr, Mr = aus.schnittgroessen(pr.raender["rechts"].quadratur, np.array([600.0, 0, 0]))
        Fl, Ml = aus.schnittgroessen(pr.raender["links"].quadratur, np.array([400.0, 0, 0]))
        check(f"reine Biegung ({projektion}), rechte Ebene (+x): Kraft 0, Moment M_y = -M exakt (1e-6)",
              np.abs(Fr).max() < 1e-6 * M / H and abs(Mr[1] / M + 1) < 1e-6 and np.abs(Mr[[0, 2]]).max() < 1e-6 * M,
              f"F {Fr}, M {Mr}, dofs {pr.protokoll['dofs']}, Zwaenge {pr.n_zwaenge}, {time.perf_counter() - t:.1f} s")
        check(f"reine Biegung ({projektion}), linke Ebene (-x): Moment +M", abs(Ml[1] / M - 1) < 1e-6, f"M {Ml}")
        if projektion == "schnitt":
            lam = pr.multiplikatoren[:, 0]
            check("Multiplikatoren der Mittelwertzwaenge (Querkraft, Torsion) bei reiner Biegung 0",
                  np.abs(lam).max() < 1e-6 * M / H, str(lam))
        P = np.array([[500, 20, 60.0], [450, -30, -80], [580, 45, 95]])
        check(f"Feld exakt reproduziert ({projektion}, 1e-6)", np.abs(aus.verschiebung(P) - u(P)).max() / np.abs(u(P)).max() < 1e-6)
        s = aus.spannung(P)
        check(f"sigma_xx = -M z / I, uebrige Komponenten 0 ({projektion}, 1e-6)",
              np.allclose(s[:, 0], -M * P[:, 2] / I, rtol=1e-6, atol=1e-6 * M * H / I) and np.abs(s[:, 1:]).max() < 1e-6 * M * H / I, str(s[0]))


def test_stub_kragarm():
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.model import ResultKey
    from statik3d_contracts.testing import StubGlobalFieldProvider
    prov = StubGlobalFieldProvider(L, B, H, E, F)
    key = ResultKey("LF1")

    def u(P):
        return prov.displacement_at(np.asarray(P, float), key)[0]

    x0, x1 = 200.0, 800.0
    soll = prov.section_forces(CutPlane(np.array([x1, 0, 0]), np.array([1.0, 0, 0])), key)
    # Messung der vollen Vorgabe (alle Komponenten punktweise): sperrt die Querkontraktion
    pr_v = _segment(x0, x1, 2, 50.0, projektion="voll")
    Fv, Mv = pr_v.auswertung(pr_v.loesen({"links": u, "rechts": u})[:, 0]).schnittgroessen(pr_v.raender["rechts"].quadratur, np.array([x1, 0, 0]))
    check("Befund: volle punktweise Vorgabe der Stabkinematik ueberhoeht das Moment (> 20 %, gemessen 45 % am 27.09.)",
          abs(Mv[1] / soll.moment[1] - 1) > 0.2, f"{(Mv[1] / soll.moment[1] - 1) * 100:+.1f} %")
    t = time.perf_counter()
    pr = _segment(x0, x1, 3, 50.0)
    U = pr.loesen({"links": u, "rechts": u})[:, 0]
    aus = pr.auswertung(U)
    Fr, Mr = aus.schnittgroessen(pr.raender["rechts"].quadratur, np.array([x1, 0, 0]))
    dM = abs(Mr[1] / soll.moment[1] - 1)
    dQ = abs(Fr[2] / soll.force[2] - 1)
    # Unabhaengige Vorhersage: schubweiches Segment (Timoshenko) mit den vorgegebenen Endwerten.
    # Kinematik u_x = -z phi, u_z = w; M_y = -EI phi', Q_z = kappa G A (w' - phi), dM_y/dx = Q_z.
    # Loesung: M_y = M0 + Q s, phi = th1 - (M0 s + Q s^2/2)/EI, w = w1 + th1 s - (M0 s^2/2 + Q s^3/6)/EI + Q s/(kGA)
    # mit s = x - x0; M0, Q aus phi(x1) = th2, w(x1) = w2. Endwerte aus dem Stub-Feld.
    G = E / (2 * (1 + NU))
    A = B * H
    l = x1 - x0
    th1, th2 = -u(np.array([[x0, 0, 1.0]]))[0, 0], -u(np.array([[x1, 0, 1.0]]))[0, 0]
    w1, w2 = u(np.array([[x0, 0, 0.0]]))[0, 2], u(np.array([[x1, 0, 0.0]]))[0, 2]

    def vorhersage(kappa):
        kGA = kappa * G * A if np.isfinite(kappa) else np.inf
        # Gleichungen: -(M0 l + Q l^2/2)/EI = th2 - th1 ;  -(M0 l^2/2 + Q l^3/6)/EI + Q l/kGA = w2 - w1 - th1 l
        M_ = np.array([[-l / (E * I), -l ** 2 / (2 * E * I)],
                       [-l ** 2 / (2 * E * I), -l ** 3 / (6 * E * I) + (l / kGA if np.isfinite(kGA) else 0.0)]])
        M0, Q = np.linalg.solve(M_, [th2 - th1, w2 - w1 - th1 * l])
        return M0 + Q * l, Q

    M_eb, Q_eb = vorhersage(np.inf)
    check("Herleitung: ohne Schub (kappa -> inf) liefert die Vorhersage genau die Stab-Schnittgroessen",
          abs(M_eb / soll.moment[1] - 1) < 1e-9 and abs(Q_eb / soll.force[2] - 1) < 1e-9, f"M {M_eb:.4e} / {soll.moment[1]:.4e}, Q {Q_eb:.1f} / {soll.force[2]:.1f}")
    M_t, Q_t = vorhersage(5.0 / 6.0)
    phi = 12 * E * I / (5 / 6 * G * A * l ** 2)
    check(f"FCM gegen Timoshenko-Vorhersage (kappa 5/6, Phi = {phi:.2f}): Moment < 3 %",
          abs(Mr[1] / M_t - 1) < 0.03,
          f"FCM {Mr[1]:.4e}, Timoshenko {M_t:.4e} ({(Mr[1] / M_t - 1) * 100:+.2f} %), Stab {soll.moment[1]:.4e} ({dM * 100:+.1f} %); dofs {pr.protokoll['dofs']}, {time.perf_counter() - t:.1f} s")
    check("FCM gegen Timoshenko-Vorhersage: Querkraft < 3 %", abs(Fr[2] / Q_t - 1) < 0.03,
          f"FCM {Fr[2]:.1f} N, Timoshenko {Q_t:.1f} N ({(Fr[2] / Q_t - 1) * 100:+.2f} %), Stab {soll.force[2]:.1f} N ({dQ * 100:+.1f} %)")
    # Multiplikator = Traktion je Flaeche (N/mm2): lambda * A ist die Zwangskraft der Mittelwertbedingung
    A_r = pr.raender["rechts"].quadratur.gewichte.sum()
    lam = pr.multiplikatoren[:, 0]
    check("Zwangskraft der Querkraft-Mittelwertbedingung (lambda * A) = uebertragene Querkraft aus den Spannungen (< 3 %)",
          abs(np.abs(lam).max() * A_r / abs(Fr[2]) - 1) < 0.03, f"lambda {np.abs(lam).max():.5f} N/mm2 * {A_r:.0f} mm2 = {np.abs(lam).max() * A_r:.0f} N gegen {abs(Fr[2]):.0f} N")
    check("Schnittgroessen endlich, Querkraft mit richtigem Vorzeichen", np.all(np.isfinite(Fr)) and np.all(np.isfinite(Mr)) and Fr[2] * soll.force[2] > 0)


if __name__ == "__main__":
    sys.exit(lauf([test_reine_biegung, test_stub_kragarm]))
