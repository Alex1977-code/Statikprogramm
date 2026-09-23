"""
Messung: Freiheitsgrade und Rechenzeit bis 1 N/mm2 am Kragarm.

Kragarm 1,0 x 0,1 x 0,2 m (der Statik3D-Sitzung), eingespannt, Querkraft am
Ende, Last so skaliert, dass an der Nachweisstelle (Oberkante, Mitte der
Breite, x = L/2) nach Saint-Venant 355 N/mm2 stehen. Je Elementtyp eine
Netzreihe auf demselben Knotengitter (tests/pruefkoerper.py); gemeldet
werden je Netz:

    FHG        3 x Knoten
    t [s]      solver.solve_all, ein Lastfall (Wandzeit, Maschine muss ruhig sein)
    w/w_ref    Endverschiebung gegen die des feinsten hex8-Netzes der Reihe
    s_mittel   sigma_v am Punkt, Mittel der Elementfelder (Knotenglaettung)
    Spanne     kleinster und groesster Einzelwert der Elemente am Punkt
    s_nachweis groesstes sigma_v aus res.solid_res der Elemente am Punkt
    Fehler     s_mittel - 355 N/mm2

Kein Test (steht nicht in run_all). Aufruf:

    python -m tests.messung_kragarm [typ ...] [--bis STUFE]
"""
from __future__ import annotations

import sys

import numpy as np

from tests import pruefkoerper as pk

NETZE = [(4, 1, 2), (8, 2, 4), (16, 4, 8), (32, 8, 16)]
TYPEN = ("hex8", "tet4", "tet4+dil", "tet10", "pent6")


def lauf(kr, typ, nx, ny, nz):
    kw = {}
    t = typ
    if typ == "tet4+dil":
        t, kw = "tet4", {"knotendilatation": True}
    m, _ids = kr.modell(t, nx, ny, nz, **kw)
    res, sek = pk.loese(m)
    u = pk.verschiebungen(res, m)
    X = np.asarray(m.nodes, float)
    ende = np.abs(X[:, 0] - kr.L) < 1e-9
    w = float(-u[ende, 2].mean())
    ps = pk.punktspannung(m, res, kr.punkt())
    return {"typ": typ, "netz": (nx, ny, nz), "fhg": pk.fhg(m), "ne": len(m.elements),
            "t": sek, "w": w, **ps}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    bis = len(NETZE)
    if "--bis" in argv:
        i = argv.index("--bis")
        bis = int(argv[i + 1])
        del argv[i:i + 2]
    typen = argv or list(TYPEN)
    kr = pk.Kragarm()
    print(f"Kragarm {kr.L} x {kr.B} x {kr.H} m, F = {kr.F / 1e3:.1f} kN, "
          f"Soll sigma_v(L/2, Oberkante) = {kr.sigma / 1e6:.1f} N/mm2")
    print(f"{'Typ':>9s} {'Netz':>9s} {'FHG':>7s} {'t[s]':>6s} {'w[mm]':>8s} "
          f"{'s_mittel':>9s} {'Fehler':>8s} {'Spanne':>17s} {'s_nachw':>8s}")
    zeilen = []
    for typ in typen:
        for nx, ny, nz in NETZE[:bis]:
            try:
                z = lauf(kr, typ, nx, ny, nz)
            except Exception as ex:                    # noqa: BLE001 - Messung, weiter
                print(f"{typ:>9s} {nx}x{ny}x{nz}: {type(ex).__name__}: {ex}")
                continue
            zeilen.append(z)
            f = (z["sv_mittel"] - kr.sigma) / 1e6
            print(f"{typ:>9s} {f'{nx}x{ny}x{nz}':>9s} {z['fhg']:7d} {z['t']:6.2f} "
                  f"{z['w'] * 1e3:8.4f} {z['sv_mittel'] / 1e6:9.2f} {f:+8.2f} "
                  f"{z['sv_min'] / 1e6:8.2f}-{z['sv_max'] / 1e6:8.2f} "
                  f"{z['sv_nachweis'] / 1e6:8.2f}")
            sys.stdout.flush()
    return zeilen


if __name__ == "__main__":
    main()
