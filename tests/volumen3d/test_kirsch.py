"""T7/T8: Kirsch-Lochplatte und Schnittlagen-Robustheit.

Viertelmodell einer Platte W 400 x L 800 x t 10 mit Loch d 40 (d/W = 0,1) unter Zug
sigma_0 = 100 N/mm2 (Traktion auf der Stirnseite x = L/2), Symmetrie x = 0 und y = 0 ueber
Normalen-Nitsche. Referenz K_tg (Bruttospannung), zwei unabhaengige Formeln:
Heywood  K_tn = 2 + (1 - d/W)^3,                       K_tg = K_tn / (1 - d/W) = 3,032
Pilkey   K_tn = 3 - 3,14 d/W + 3,667 (d/W)^2 - 1,527 (d/W)^3,  K_tg = 3,023
(Howland 1930 tabelliert 3,03). 3D-Effekt bei t/d = 0,25 in Plattenmitte etwa +1 %
(Folias/Wang), im Kriterium 2 % enthalten. Auswertung sigma_xx bei (0, d/2, t/2).

Aufruf: python -m tests.volumen3d.test_kirsch   (~5 min)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from tests.volumen3d._pruef import check, lauf  # noqa: E402

W, L, T, D, S0, E, NU = 400.0, 800.0, 10.0, 40.0, 100.0, 210000.0, 0.3


def kt_referenz():
    dw = D / W
    heywood = (2 + (1 - dw) ** 3) / (1 - dw)
    pilkey = (3 - 3.14 * dw + 3.667 * dw ** 2 - 1.527 * dw ** 3) / (1 - dw)
    return heywood, pilkey


def _platte(p, h, versatz=0.0, polster=0.1):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "differenz", "teile": [
        {"typ": "schnitt", "teile": [
            {"typ": "quader", "min": [-5, -5, 0], "max": [L / 2, W / 2, T], "name": "platte"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [-1, 0, 0], "name": "sym_x"},
            {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, -1, 0], "name": "sym_y"}]},
        {"typ": "zylinder", "p0": [0, 0, -1], "p1": [0, 0, T + 1], "radius": D / 2, "name": "loch"}]})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), polster=polster + versatz, facette_mm=0.5)
    pr.verschiebungsrand("sym_x", "sym_x", projektion="normal")
    pr.verschiebungsrand("sym_y", "sym_y", projektion="normal")
    stirn = pr.oberflaeche.auswahl((pr.oberflaeche.name.astype(str) == "platte") & (np.abs(pr.oberflaeche.punkte[:, 0] - L / 2) < 1e-6))
    pr.traktion(None, np.array([S0, 0, 0]), quadratur=stirn)
    return pr


def _kt(pr):
    U = pr.loesen({})[:, 0]
    aus = pr.auswertung(U)
    # minimal in den Werkstoff geruckt, damit die Punktsuche eine aktive Zelle findet
    s = aus.spannung(np.array([[0.0, D / 2 + 1e-6, T / 2], [0.0, D / 2 + 1e-6, 1e-6]]))
    return s[0, 0] / S0, s[1, 0] / S0


def test_kirsch():
    hw, pk = kt_referenz()
    ref = 0.5 * (hw + pk)
    check("Referenz: Heywood und Pilkey stimmen auf 0,5 % ueberein", abs(hw / pk - 1) < 0.005, f"{hw:.4f} / {pk:.4f}")
    for p, h in ((4, 10.0), (4, 5.0)):
        t = time.perf_counter()
        pr = _platte(p, h)
        kt_mitte, kt_rand = _kt(pr)
        prot = pr.protokoll
        ok = abs(kt_mitte / ref - 1) < 0.02
        check(f"p={p}, h={h}: K_tg Mitte {kt_mitte:.4f} gegen {ref:.3f} (< 2 %)", ok,
              f"Abw. {(kt_mitte / ref - 1) * 100:+.2f} %, Oberflaeche {kt_rand:.4f}; dofs {prot['dofs']} ({prot['dofs_frei']} frei), "
              f"cut {prot['cut']}/{prot['zellen']}, {prot['quadraturpunkte']} Punkte, Loeser {prot['loeser']}, "
              f"Zeiten {prot['t_assemblierung_s']} + {prot['t_faktorisierung_s']} + {prot['t_loesen_s']} s, gesamt {time.perf_counter() - t:.1f} s")
        if ok:
            break


def test_schnittlage():
    """T8: Wurzelgitter um 0,2 ... 0,8 Zellen verschoben -> Streuung von K_t < 1 %."""
    werte = []
    t = time.perf_counter()
    for v in (0.0, 0.2, 0.4, 0.6, 0.8):
        werte.append(_kt(_platte(4, 10.0, versatz=v))[0])
    streuung = (max(werte) - min(werte)) / np.mean(werte)
    check("Schnittlagen-Streuung von K_t (5 Lagen) < 1 %", streuung < 0.01,
          " ".join(f"{w:.4f}" for w in werte) + f" -> {streuung * 100:.2f} %, {time.perf_counter() - t:.0f} s")


if __name__ == "__main__":
    sys.exit(lauf([test_kirsch, test_schnittlage]))
