"""
Messung A3: MacNeal/Harder (1985), gerader Kragtraeger - Verschiebungen.

Laenge 6,0, Breite 0,2, Hoehe 0,1, E = 1,0e7, nu = 0,30; 6 x 1 x 1
Elemente, regelmaessig, Trapez (Innenflaechen um +-45 Grad gekippt) und
Parallelogramm (alle um 45 Grad). Endlasten 1,0 als gleichmaessige
Schubspannung auf der Stirnseite (Streckung, Querkraft in der Ebene der
Breite und in der Ebene der Hoehe). Sollwerte nach MacNeal/Harder:
Streckung 3,0e-5, Querkraft in der Ebene 0,1081, aus der Ebene 0,4321.
Gemeldet wird w / w_soll (1,0 = exakt).

Die Verzerrung geht in der Ebene der jeweiligen Biegung: die gekippten
Innenflaechen liegen in der x-y-Ebene (Biegung in y, "in der Ebene"). Fuer
die Biegung in z (aus der Ebene) sind die Elemente dann Parallelepipede.

Kein Test. Aufruf:  python -m tests.messung_macneal [typ ...]
"""
from __future__ import annotations

import sys

import numpy as np

from tests import pruefkoerper as pk

L, B, H = 6.0, 0.2, 0.1
E, NU = 1.0e7, 0.30
SOLL = {"streckung": 3.0e-5, "ebene": 0.1081, "aus": 0.4321}


def form(art):
    def f(i, j, k, p):
        if art == "regelmaessig" or i in (0, 6):
            return p
        # x der Innenebene i je nach y verschieben: 45 Grad ueber die Breite
        d = 0.5 * B * (1 if (art == "parallelogramm" or i % 2) else -1)
        yrel = (p[1] - B / 2) / (B / 2)
        return p + np.array([d * yrel, 0.0, 0.0])
    return f


def lauf(typ, art, last):
    m, ids = pk.quader(typ, 6, 1, 1, L, B, H, E=E, nu=NU, form=form(art))
    tol = 1e-9
    pk.einspannen(m, lambda X: bool(np.all(np.abs(X[:, 0]) < tol)))
    seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - L) < tol)))
    richtung = {"streckung": (1, 0, 0), "ebene": (0, 1, 0), "aus": (0, 0, 1)}[last]
    pk.schubkraft_auf_seiten(m, seiten, 1.0, richtung)
    res, _t = pk.loese(m)
    u = pk.verschiebungen(res, m)
    X = np.asarray(m.nodes, float)
    ende = np.abs(X[:, 0] - L) < tol
    k = {"streckung": 0, "ebene": 1, "aus": 2}[last]
    return float(u[ende, k].mean()) / SOLL[last]


def main(argv=None):
    typen = list(sys.argv[1:] if argv is None else argv) or ["hex8", "tet10", "pent6"]
    print("MacNeal/Harder gerader Kragtraeger 6 x 1 x 1: w / w_soll")
    for typ in typen:
        for art in ("regelmaessig", "trapez", "parallelogramm"):
            z = []
            for last in ("streckung", "ebene", "aus"):
                try:
                    z.append(f"{last} {lauf(typ, art, last):.4f}")
                except Exception as ex:                 # noqa: BLE001
                    z.append(f"{last}: {type(ex).__name__}")
            print(f"{typ:6s} {art:14s} " + "  ".join(z), flush=True)


if __name__ == "__main__":
    main()
