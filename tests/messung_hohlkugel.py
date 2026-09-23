"""
Messung: Lame-Hohlkugel unter Innendruck (tests/pruefkoerper.Hohlkugel).

Achtel mit Symmetrie, a = 0,1 m, b = 0,2 m; Druck so, dass sigma_v an der
Innenflaeche nach Lame 355 N/mm2 ist. Gemeldet je Netz: FHG und die
Abweichung der geglaetteten Knotenspannung (res.solid_knoten) an allen
Eckknoten der Innenflaeche (kleinste, groesste, Mittel) in N/mm2.

Kein Test. Aufruf:  python -m tests.messung_hohlkugel [typ ...] [--stufung q]
"""
from __future__ import annotations

import sys

import numpy as np

from statik3d.elements import solid as sl
from tests import pruefkoerper as pk

NETZE = {"hex8": ((2, 2), (4, 4), (8, 8)), "tet4": ((2, 2), (4, 4), (8, 8)),
         "tet10": ((2, 2), (4, 4), (8, 8))}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    q = 1.0
    if "--stufung" in argv:
        i = argv.index("--stufung")
        q = float(argv[i + 1])
        del argv[i:i + 2]
    typen = argv or list(NETZE)
    hk = pk.Hohlkugel()
    print(f"Hohlkugel a = {hk.a} m, b = {hk.b} m, p = {hk.p / 1e6:.2f} N/mm2, "
          f"Soll sigma_v(a) = {hk.sigma / 1e6:.0f} N/mm2, radiale Stufung {q}")
    for typ in typen:
        for nt, nr in NETZE[typ]:
            try:
                m = hk.modell(typ, nt, nr, stufung=q)
                res, _t = pk.loese(m)
            except Exception as ex:                     # noqa: BLE001
                print(f"{typ} {nt}x{nr}: {type(ex).__name__}: {str(ex)[:80]}")
                continue
            sk = res.solid_knoten
            pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
            S = np.asarray(sk["spannung"])
            f = np.array([sl.von_mises(S[pos[n]]) for n in hk.nachweisknoten(m)]) / 1e6 - 355.0
            print(f"{typ:6s} {nt}x{nr}  FHG {pk.fhg(m):7d}  Abweichung min {f.min():+8.2f}  "
                  f"max {f.max():+8.2f}  Mittel {f.mean():+8.2f} N/mm2", flush=True)


if __name__ == "__main__":
    main()
