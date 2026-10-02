# -*- coding: utf-8 -*-
"""Auswertung B (01.10.2026): das Tet10-Spannungsfeld direkt am Punkt.

Unabhaengig vom Nachlauf des Loesers: nimmt nur Knoten, Tet10-Knoten und die
Verschiebungen. Je Referenzpunkt alle Tetraeder, die den Punkt enthalten
(baryzentrisch, Toleranz 1e-9); die Mittelknoten werden geometrisch den Kanten
zugeordnet (keine Annahme ueber die Knotenreihenfolge). Verzerrung aus den
eigenen Ableitungen der quadratischen Ansatzfunktionen, Spannung nach Hooke,
Mittel ueber die enthaltenden Elemente.

Aufruf: python auswertung_b.py <ausgabeordner des Laufs>
"""
import json
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

E = 210000.0e6
NU = 0.3
LAM = E * NU / ((1 + NU) * (1 - 2 * NU))
MU = E / (2 * (1 + NU))
KANTEN = ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3))


def punkte():
    out = []
    for seite, x04, x10 in (("rechts", 140.0, 146.0), ("links", 60.0, 54.0)):
        for y in range(32, 49, 2):
            out.append((seite, "0.4t", x04, float(y)))
            out.append((seite, "1.0t", x10, float(y)))
    return out


def sigma_im_tet(X10, u10, p):
    C = X10[:4]
    J = (C[1:] - C[0]).T                      # Spalten x_i - x_0
    lam = np.linalg.solve(J, p - C[0])
    L = np.array([1.0 - lam.sum(), *lam])
    Jinv = np.linalg.inv(J)
    gL = np.vstack([-Jinv.sum(axis=0), Jinv])  # Gradienten der L_i (4, 3)
    # Mittelknoten geometrisch den Kanten zuordnen
    mitte = X10[4:]
    zuordnung, abw = [], 0.0
    for a, b in KANTEN:
        d = np.linalg.norm(mitte - 0.5 * (C[a] + C[b]), axis=1)
        j = int(np.argmin(d))
        zuordnung.append(4 + j)
        abw = max(abw, float(d[j]) / float(np.linalg.norm(C[a] - C[b])))
    assert len(set(zuordnung)) == 6
    H = np.zeros((3, 3))
    for i in range(4):
        H += np.outer(u10[i], (4 * L[i] - 1) * gL[i])
    for (a, b), k in zip(KANTEN, zuordnung):
        H += np.outer(u10[k], 4 * (L[a] * gL[b] + L[b] * gL[a]))
    eps = 0.5 * (H + H.T)
    sig = LAM * np.trace(eps) * np.eye(3) + 2 * MU * eps
    return sig, L, abw


def main():
    aus = sys.argv[1]
    X = np.load(os.path.join(aus, "knoten_m.npy"))
    T = np.load(os.path.join(aus, "tet10.npy"))
    U = np.load(os.path.join(aus, "u_m.npy"))
    ecken = X[T[:, :4]]
    schwer = ecken.mean(axis=1)
    rmax = float(np.max(np.linalg.norm(ecken - schwer[:, None, :], axis=2)))
    baum = cKDTree(schwer)
    ergebnis, max_abw = [], 0.0
    for seite, lage, x, y in punkte():
        p = np.array([x, y, 0.0]) * 1e-3
        werte = []
        for k in baum.query_ball_point(p, rmax * 1.001):
            C = ecken[k]
            lam = np.linalg.solve((C[1:] - C[0]).T, p - C[0])
            L = np.array([1.0 - lam.sum(), *lam])
            if L.min() < -1e-9:
                continue
            sig, _L, abw = sigma_im_tet(X[T[k]], U[T[k]], p)
            max_abw = max(max_abw, abw)
            werte.append(sig)
        assert werte, (x, y)
        S = np.array(werte) / 1e6
        sxx = S[:, 0, 0]
        ergebnis.append({"seite": seite, "lage": lage, "x_mm": x, "y_mm": y, "elemente": len(werte),
                         "sigma_xx": float(sxx.mean()), "spanne_xx": float(sxx.max() - sxx.min()),
                         "sigma": S.mean(axis=0).tolist()})
    hs = []
    for seite in ("rechts", "links"):
        for y in range(32, 49, 2):
            a = next(e for e in ergebnis if e["seite"] == seite and e["lage"] == "0.4t" and e["y_mm"] == y)
            b = next(e for e in ergebnis if e["seite"] == seite and e["lage"] == "1.0t" and e["y_mm"] == y)
            hs.append({"seite": seite, "y_mm": float(y),
                       "sigma_hs": 5.0 / 3.0 * a["sigma_xx"] - 2.0 / 3.0 * b["sigma_xx"]})
    out = {"verfahren": "B: Tet10-Feld am Punkt, Mittel der enthaltenden Elemente",
           "mittelknoten_max_abweichung_rel": max_abw, "punkte": ergebnis, "hot_spot": hs}
    with open(os.path.join(aus, "auswertung_b.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for h in hs:
        print(f"B {h['seite']:6s} y {h['y_mm']:4.0f}: sigma_hs {h['sigma_hs']:9.4f}")


if __name__ == "__main__":
    main()
