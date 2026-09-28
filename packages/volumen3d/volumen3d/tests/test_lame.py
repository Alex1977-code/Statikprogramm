"""T6: Lame. Viertel eines dickwandigen Zylinders (r_i 50, r_a 100, Dicke 20) unter Innendruck
100 N/mm2, ebener Dehnungszustand ueber Normalen-Nitsche auf vier Symmetrieebenen, Druck ueber
die Flaechenquadratur der Bohrung. Referenz (Lame, unabhaengig vom Dehnungszustand):
sigma_r = k (1 - r_a^2/r^2), sigma_phi = k (1 + r_a^2/r^2), k = p r_i^2 / (r_a^2 - r_i^2).
Gegenprobe: Kesselformel int sigma_phi dr = p r_i.

Aufruf: python -m volumen3d.tests.test_lame   (~2 min)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

RI, RA, T, PI, E, NU = 50.0, 100.0, 20.0, 100.0, 210000.0, 0.3


def _lame(r):
    k = PI * RI ** 2 / (RA ** 2 - RI ** 2)
    return k * (1 - RA ** 2 / r ** 2), k * (1 + RA ** 2 / r ** 2)


def _u_r(r):
    """Radialverschiebung im ebenen Dehnungszustand."""
    k = PI * RI ** 2 / (RA ** 2 - RI ** 2)
    return (1 + NU) / E * k * ((1 - 2 * NU) * r + RA ** 2 / r)


def _geometrie():
    from volumen3d.geometry.csg import aus_params
    return aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "schnitt", "teile": [
            {"typ": "zylinder", "p0": [0, 0, -1], "p1": [0, 0, T + 1], "radius": RA, "name": "aussen"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [-1, 0, 0], "name": "sym_x"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, -1, 0], "name": "sym_y"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, 0, -1], "name": "sym_z0"},
            {"typ": "halbraum", "punkt": [0, 0, T], "normale": [0, 0, 1], "name": "sym_z1"}]},
        {"typ": "zylinder", "p0": [0, 0, -2], "p1": [0, 0, T + 2], "radius": RI, "name": "innen"}]}})


def _rechnen(p, h):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    pr = FcmProblem(_geometrie(), h=h, p=p, werkstoff=Werkstoff(E, NU))
    for s in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
        pr.verschiebungsrand(s, s, projektion="normal")
    pr.druck("innen", PI)
    U = pr.loesen({})[:, 0]
    return pr, pr.auswertung(U)


def _fehler(aus, th_grad=37.0):
    r = np.linspace(RI + 1, RA - 1, 9)
    th = np.deg2rad(th_grad)
    P = np.stack([r * np.cos(th), r * np.sin(th), np.full_like(r, T / 2)], axis=1)
    s, u = aus.spannung_und_verschiebung(P)
    c, sn = np.cos(th), np.sin(th)
    sr = s[:, 0] * c * c + s[:, 1] * sn * sn + 2 * s[:, 3] * sn * c
    sphi = s[:, 0] * sn * sn + s[:, 1] * c * c - 2 * s[:, 3] * sn * c
    sr_e, sphi_e = _lame(r)
    ur = u[:, 0] * c + u[:, 1] * sn
    return (np.abs(sr - sr_e).max() / PI, np.abs(sphi - sphi_e).max() / sphi_e.max(),
            np.abs(ur - _u_r(r)).max() / np.abs(_u_r(r)).max(), np.abs(s[:, 2] - NU * (sr_e + sphi_e)).max() / PI)


def test_referenz():
    r = np.linspace(RI, RA, 2001)
    _, sphi_e = _lame(r)
    check("Referenzformel: Kesselformel int sigma_phi dr = p_i r_i (< 1e-6)", abs(np.trapezoid(sphi_e, r) / (PI * RI) - 1) < 1e-6)
    sr_i, _ = _lame(np.array([RI]))
    sr_a, _ = _lame(np.array([RA]))
    check("Randbedingungen der Referenz: sigma_r(r_i) = -p, sigma_r(r_a) = 0", abs(sr_i[0] + PI) < 1e-12 and abs(sr_a[0]) < 1e-12)


def test_lame():
    # gemessen 27.09.2026 (h = 10): p=2 sigma_r 1,41 % / sigma_phi 0,96 %; p=3 0,31 % / 0,12 %.
    # Abnahme (Vorgabe 13: < 1 % bei moderatem Aufwand) gilt fuer p >= 3 (Standard des Vertrags p = 3).
    ergebnisse = {}
    for p, h, grenze in ((2, 10.0, 0.02), (3, 10.0, 0.01), (4, 10.0, 0.01)):
        t = time.perf_counter()
        pr, aus = _rechnen(p, h)
        er, ep, eu, ez = _fehler(aus)
        ergebnisse[p] = (er, ep)
        prot = pr.protokoll
        check(f"p={p}, h={h}: sigma_r < {grenze * 100:.0f} % von p_i, sigma_phi < {grenze * 100:.0f} %", er < grenze and ep < grenze,
              f"sigma_r {er * 100:.3f} %, sigma_phi {ep * 100:.3f} %, u_r {eu * 100:.3f} %, sigma_z (ebene Dehnung) {ez * 100:.3f} %; "
              f"dofs {prot['dofs']} ({prot['dofs_frei']} frei), cut {prot['cut']}/{prot['zellen']}, {prot['quadraturpunkte']} Punkte, "
              f"{prot['oberflaechenpunkte']} Flaechenpunkte, Aggregation {prot['aggregation']['zellen_schlecht']} Zellen, "
              f"Zeiten {prot['t_assemblierung_s']} + {prot['t_faktorisierung_s']} + {prot['t_loesen_s']} s, gesamt {time.perf_counter() - t:.1f} s")
    # p = 4 ist bei Tiefe 2 nicht besser als p = 3 (gemessen sigma_phi 3,2e-4 -> 9,5e-4): die
    # Tangentialebenen der Schnittzellen (Fehler ~ (Blattkante/R)^2 = (2,5/50)^2) begrenzen die
    # Genauigkeit unabhaengig von p; siehe Theoriehandbuch 11.7 (Messung mit Tiefe 3).
    check("p = 3 deutlich besser als p = 2 (sigma_phi, Faktor > 5)", ergebnisse[3][1] * 5 < ergebnisse[2][1],
          f"{ergebnisse[2][1]:.2e} -> {ergebnisse[3][1]:.2e} -> {ergebnisse[4][1]:.2e} (p = 4 an der Geometriegrenze der Tangentialebenen)")
    # Schnittlage: anderer Winkel und andere Hoehe muessen dasselbe liefern (Rotationssymmetrie)
    pr, aus = _rechnen(3, 10.0)
    e1 = _fehler(aus, 12.0)
    e2 = _fehler(aus, 71.0)
    check("Rotationssymmetrie: Fehler bei 12 und 71 Grad ebenfalls < 1 %", max(e1[0], e1[1], e2[0], e2[1]) < 0.01, f"{e1[:2]} {e2[:2]}")


if __name__ == "__main__":
    sys.exit(lauf([test_referenz, test_lame]))
