"""
Messung (Abnahme tet10, Auftrag 4.1): dickwandiges Rohr unter Innendruck,
ebene Dehnung, bis nu = 0,4999 - volumetrisches Sperren gemessen und benannt.

Gemeldet je Typ und nu: u_r an der Innenflaeche gegen Lame (1,0 = exakt) und
die Abweichung von sigma_v an der Innenflaeche (geglaettete Knotenspannung,
Mittel ueber die Eckknoten der Innenflaeche) in N/mm2.

Kein Test. Aufruf:  python -m tests.messung_zylinder [typ ...]
"""
from __future__ import annotations

import sys

import numpy as np

from statik3d.elements import solid as sl
from tests import pruefkoerper as pk


def lauf(typ, nu, n_t=8, n_r=4):
    rz = pk.Hohlzylinder()
    m = rz.modell(typ, n_t, n_r, nu=nu)
    res, _t = pk.loese(m)
    u = pk.verschiebungen(res, m)
    X = np.asarray(m.nodes, float)
    r = np.hypot(X[:, 0], X[:, 1])
    ecken = {int(n) for e in m.elements for n in e.nodes[:len(sl.ECKEN_NATUERLICH[e.typ])]}
    innen = [n for n in range(m.nn) if abs(r[n] - rz.a) < 1e-9 and n in ecken]
    ur = np.mean([(u[n, 0] * X[n, 0] + u[n, 1] * X[n, 1]) / r[n] for n in innen])
    sk = res.solid_knoten
    pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
    S = np.asarray(sk["spannung"])
    sv = np.mean([sl.von_mises(S[pos[n]]) for n in innen])
    return ur / rz.u_r(rz.a, nu=nu), (sv - rz.sv_innen(nu)) / 1e6, pk.fhg(m)


def main(argv=None):
    typen = list(sys.argv[1:] if argv is None else argv) or ["hex8", "tet4", "tet10", "pent6"]
    print("Rohr a 0,1 / b 0,2 m, Innendruck 100 N/mm2, ebene Dehnung, 8 x 4 Zellen")
    for typ in typen:
        z = []
        for nu in (0.3, 0.49, 0.499, 0.4999):
            try:
                q, f, fhg = lauf(typ, nu)
                z.append(f"nu {nu}: u {q:.4f} sv {f:+.2f}")
            except Exception as ex:                    # noqa: BLE001
                z.append(f"nu {nu}: {type(ex).__name__}")
        print(f"{typ:6s} ({fhg} FHG) " + " | ".join(z), flush=True)


if __name__ == "__main__":
    main()
