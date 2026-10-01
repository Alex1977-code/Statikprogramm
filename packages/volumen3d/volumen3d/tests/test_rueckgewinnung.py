"""Spannungsrueckgewinnung durch L2-Projektion (Vorgabe 11.1, Plan TP 5 B2, Theorie 11.12).

Aufruf: python -m volumen3d.tests.test_rueckgewinnung   (~40 s)
Auswertepunkte immer auf der echten Oberflaeche: Punkte der Flaechenquadratur, 1e-7 h nach innen geruckt (so
wertet auch der Vertragsweg aus).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def _oberflaeche(pr):
    o = pr.oberflaeche
    return o.punkte - 1e-7 * pr.gitter.h * o.normalen, o.name.astype(str)


def test_patch_exakt():
    """Konstante Spannungen gehoeren zum Ansatzraum: die Projektion gibt sie exakt wieder (p 2 und p 3, schraeg
    geschnittenes Gebiet mit Aggregation) - an allen Oberflaechenpunkten gegen sigma exakt."""
    from volumen3d.tests import test_patch as T
    for p in (2, 3):
        pr = T._problem(p, 1e-8)
        U = pr.loesen({"alles": T.u_exakt})[:, 0]
        P, _ = _oberflaeche(pr)
        t = time.perf_counter()
        s = pr.auswertung(U).spannung(P, geglaettet=True)
        f = float(np.abs(s - T.sigma_exakt()).max() / np.abs(T.sigma_exakt()).max())
        check(f"Patch p {p}: geglaettete Spannung an {len(P)} Oberflaechenpunkten exakt (< 1e-6)", f < 1e-6,
              f"Abweichung {f:.1e}, {time.perf_counter() - t:.2f} s, {pr._rueckgewinnung.statistik}")


def test_haengende_moden():
    """Pruefluecke G2-5 (Gutachten C2, 02.10.2026): die L2-Projektion erbt haengende Moden und Aggregation ueber die skalare Zwangsmatrix
    C[0::3, 0::3]; geprueft waren nur Faelle ohne Verfeinerung. Patch-Gebiet (Quader mit zwei schraegen Schnitten), lokale Verfeinerung zwei
    Ebenen um einen Punkt der Schnittebene, p 2, Aggregation 0,25: das lineare Feld muss an allen Oberflaechenpunkten und in den feinen Zellen
    exakt sein (Gutachter gemessen 2,3e-10 / 2,1e-11; Schranke 1e-8 wie der Patch-Test). Dazu G2-9: Punkte ausserhalb -> ValueError."""
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    from volumen3d.postprocess.rueckgewinnung import rueckgewinnung
    from volumen3d.tests import test_patch as T
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "quader"},
        {"typ": "halbraum", "punkt": [60, 50, 50], "normale": [1, 2, 3], "name": "s1"},
        {"typ": "halbraum", "punkt": [30, 40, 70], "normale": [-2, 1, 1.5], "name": "s2"}]}})
    v = Verfeinerung(bereiche=((np.array([55.0, 45.0, 40.0]), 22.0, 5.0),))
    pr = FcmProblem(g, h=20.0, p=2, werkstoff=Werkstoff(T.E, T.NU), alpha=1e-8, beta_faktor=10.0, aggregation=0.25, verfeinerung=v)
    pr.verschiebungsrand("alles", None, projektion="voll")
    U = pr.loesen({"alles": T.u_exakt})[:, 0]
    o = pr.oberflaeche
    aus = pr.auswertung(U)
    s_ex = T.sigma_exakt()
    f_o = float(np.abs(aus.spannung(o.punkte - 1e-7 * pr.gitter.h * o.normalen, geglaettet=True) - s_ex).max() / np.abs(s_ex).max())
    rng = np.random.default_rng(1)
    Q = rng.uniform(0, 100, (20000, 3))
    Q = Q[(pr.geometrie.abstand(Q) < -0.5) & (np.linalg.norm(Q - [55, 45, 40], axis=1) < 22)][:1500]
    f_i = float(np.abs(aus.spannung(Q, geglaettet=True) - s_ex).max() / np.abs(s_ex).max())
    zs = pr.zwaenge.statistik
    try:
        r = rueckgewinnung(pr)
        r.spannung(np.array([[500.0, 500.0, 500.0]]), r.knoten(U[:, None]))
        aussen = ""
    except ValueError as ex:
        aussen = str(ex)
    check(f"haengende Moden {zs['moden_haengend']}, aggregiert {zs['moden_aggregiert']}: geglaettet an der Oberflaeche {f_o:.1e}, in den feinen Zellen "
          f"{f_i:.1e} (< 1e-8); Punkt ausserhalb -> ValueError",
          zs["moden_haengend"] > 0 and zs["moden_aggregiert"] > 0 and f_o < 1e-8 and f_i < 1e-8 and "ausserhalb" in aussen, aussen[:60])


def test_lame_besser_als_roh():
    """Lame-Zylinder h 20 p 2 (Innendruck, ebene Dehnung): sigma_r, sigma_phi, sigma_z gegen Lame an allen
    Oberflaechenpunkten; die Projektion senkt den groessten Fehler deutlich (gemessen 30.09.2026: roh 56,6 %,
    geglaettet 15,2 % von p_i; Mittel 3,7 gegen 2,9 %). Erwartungswerte im Test aus der Lame-Loesung berechnet."""
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.tests import test_lame as L
    pr = FcmProblem(L._geometrie(), h=20.0, p=2, werkstoff=Werkstoff(L.E, L.NU))
    for s_ in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
        pr.verschiebungsrand(s_, s_, projektion="normal")
    pr.druck("innen", L.PI)
    U = pr.loesen({})[:, 0]
    P, _ = _oberflaeche(pr)
    r = np.hypot(P[:, 0], P[:, 1])
    th = np.arctan2(P[:, 1], P[:, 0])
    c, sn = np.cos(th), np.sin(th)
    k = L.PI * L.RI ** 2 / (L.RA ** 2 - L.RI ** 2)                  # Lame unabhaengig von test_lame._lame nachgerechnet
    sr_e, sphi_e = k * (1 - L.RA ** 2 / r ** 2), k * (1 + L.RA ** 2 / r ** 2)
    fehler = {}
    aus = pr.auswertung(U)
    for art, gl in (("roh", False), ("geglaettet", True)):
        s = aus.spannung(P, geglaettet=gl)
        sr = s[:, 0] * c * c + s[:, 1] * sn * sn + 2 * s[:, 3] * sn * c
        sphi = s[:, 0] * sn * sn + s[:, 1] * c * c - 2 * s[:, 3] * sn * c
        f = np.max(np.abs(np.stack([sr - sr_e, sphi - sphi_e, s[:, 2] - L.NU * (sr_e + sphi_e)])), axis=0) / L.PI
        fehler[art] = (float(f.max()), float(f.mean()))
    check(f"Lame h 20 p 2 an {len(P)} Oberflaechenpunkten: groesster Fehler geglaettet < roh / 2 und < 20 % von p_i",
          fehler["geglaettet"][0] < 0.5 * fehler["roh"][0] and fehler["geglaettet"][0] < 0.20
          and fehler["geglaettet"][1] < fehler["roh"][1],
          f"roh {fehler['roh'][0] * 100:.1f} % (Mittel {fehler['roh'][1] * 100:.2f} %), geglaettet {fehler['geglaettet'][0] * 100:.1f} % "
          f"(Mittel {fehler['geglaettet'][1] * 100:.2f} %)")


def test_reine_biegung():
    """Kragarmsegment p 3, reine Biegung: sigma_xx = -M z / I bleibt auch geglaettet an der Oberflaeche exakt (< 1e-6)."""
    from volumen3d.tests import test_kragarm as KR
    M = 5e6

    def u(P):
        x, y, z = np.asarray(P, float).T
        return np.stack([-M * x * z / (KR.E * KR.I), KR.NU * M * y * z / (KR.E * KR.I),
                         M * (x ** 2 + KR.NU * (z ** 2 - y ** 2)) / (2 * KR.E * KR.I)], axis=1)
    pr = KR._segment(400.0, 600.0, 3, 50.0)
    U = pr.loesen({"links": u, "rechts": u})[:, 0]
    P, _ = _oberflaeche(pr)
    s = pr.auswertung(U).spannung(P, geglaettet=True)
    ex = np.zeros_like(s)
    ex[:, 0] = -M * P[:, 2] / KR.I
    f = float(np.abs(s - ex).max() / (M * KR.H / (2 * KR.I)))
    check(f"reine Biegung p 3: geglaettetes sigma an {len(P)} Oberflaechenpunkten exakt (< 1e-6)", f < 1e-6, f"Abweichung {f:.1e}")


def test_mehrere_lastfaelle():
    """Mehrere Lastfaelle mit einer Faktorisierung: die Projektion ist linear, knoten(U) fuer zwei Spalten gleich
    den beiden Einzelprojektionen, die Massenmatrix wird nur einmal gebaut. Schranke 1e-6: die Massenmatrix hat hier
    die Kondition 2,2e8 (Schnittzellen, hierarchische Basis), die rechten Seiten werden fuer zwei Spalten in anderer
    Reihenfolge summiert - Kondition mal Maschinengenauigkeit ~5e-8; gemessen 1,1e-9 mit PARDISO, 2,6e-8 mit
    SuperLU (30.09.2026)."""
    from volumen3d.postprocess.rueckgewinnung import rueckgewinnung
    from volumen3d.tests import test_patch as T
    pr = T._problem(2, 1e-8)
    U1 = pr.loesen({"alles": T.u_exakt})[:, 0]
    U2 = pr.loesen({"alles": lambda P: 2.0 * T.u_exakt(P) + np.array([1.0, -2.0, 0.5])})[:, 0]
    r = rueckgewinnung(pr)
    X = r.knoten(np.stack([U1, U2], axis=1))
    X1, X2 = r.knoten(U1), r.knoten(U2)
    f = max(float(np.abs(X[:, :, 0] - X1[:, :, 0]).max()), float(np.abs(X[:, :, 1] - X2[:, :, 0]).max())) / float(np.abs(X1).max())
    check("zwei Lastfaelle in einem Aufruf wie einzeln (< 1e-6), Rueckgewinnung einmal je Problem gebaut",
          f < 1e-6 and rueckgewinnung(pr) is r, f"Abweichung {f:.1e}")


if __name__ == "__main__":
    sys.exit(lauf([test_patch_exakt, test_haengende_moden, test_lame_besser_als_roh, test_reine_biegung, test_mehrere_lastfaelle]))
