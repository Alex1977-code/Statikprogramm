"""
Messung: Lame-Hohlkugel (tests/pruefkoerper.Hohlkugel) mit dem Tetraeder mit
Ordnung p - dasselbe Netz und dieselbe Auswertung wie tests/messung_hohlkugel.py
(geglaettete Knotenspannung res.solid_knoten an allen Eckknoten der
Innenflaeche), damit die Zahlen neben hex8, tet4 und tet10 stehen koennen.

Das Netz ist das Kuhn-Tetraedernetz des Pruefkoerpers. Die Kantenmitten auf
Kugelflaechen (beide Ecken auf demselben Radius) liegen auf der Kugel wie beim
tet10 des Pruefkoerpers (model.tetp_kantenmitten). Der Innendruck wirkt als
Seitendruck auf die tetp-Seiten (konsistent, auch auf die Zusatz-FHG).

Ordnungen: "p2", "p3", "p4" ueberall; "p4innen" = p = 4 in den Elementen mit
einer Ecke auf der Innenflaeche, sonst p = 2.

Kein Test. Aufruf:  python -m tests.messung_tetp_hohlkugel [ordnung ...] [--stufung q]
"""
from __future__ import annotations

import sys
import time

import numpy as np

from statik3d import solver
from statik3d.elements import solid as sl
from statik3d.elements import tetp as tp
from tests import pruefkoerper as pk

NETZE = ((2, 2), (4, 4), (8, 8))


def modell(hk, nt, nr, ordnung, stufung=1.0):
    m = hk.modell("tet4", nt, nr, stufung=stufung)
    # Knotenlasten des tet4-Drucks durch Seitendruck auf die p-Seiten ersetzen
    lc = m.case()
    lc.nodal_loads.clear()
    X = np.asarray(m.nodes, float)
    r = np.linalg.norm(X, axis=1)
    innen = np.abs(r - hk.a) < 1e-9 * hk.b
    for i, e in enumerate(m.elements):
        if ordnung == "p4innen":
            e.typ = "tetp4" if innen[e.nodes].any() else "tetp2"
        else:
            e.typ = "tetp" + ordnung[1:]
        for s, ecken in enumerate(tp.SEITEN):
            if innen[[e.nodes[a] for a in ecken]].all():
                m.load_face(i, hk.p, s)
    m._tetp_version = getattr(m, "_tetp_version", 0) + 1
    # Kantenmitten auf der Kugel, wo beide Ecken auf demselben Radius liegen
    km = {}
    for e in m.elements:
        for a, b in tp.TET10_KANTEN:
            p, q = int(e.nodes[a]), int(e.nodes[b])
            if abs(r[p] - r[q]) < 1e-12 * hk.b:
                M = 0.5 * (X[p] + X[q])
                km[(min(p, q), max(p, q))] = M / np.linalg.norm(M) * r[p]
    m.tetp_kantenmitten = km
    return m


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    q = 1.0
    if "--stufung" in argv:
        i = argv.index("--stufung")
        q = float(argv[i + 1])
        del argv[i:i + 2]
    ordnungen = argv or ["p2", "p3", "p4", "p4innen"]
    hk = pk.Hohlkugel()
    print(f"Hohlkugel a = {hk.a} m, b = {hk.b} m, p = {hk.p / 1e6:.2f} N/mm2, "
          f"Soll sigma_v(a) = {hk.sigma / 1e6:.0f} N/mm2, radiale Stufung {q}")
    for ordnung in ordnungen:
        for nt, nr in NETZE:
            try:
                m = modell(hk, nt, nr, ordnung, q)
                t0 = time.perf_counter()
                res = next(iter(solver.solve_all(m).cases.values()))
                dt = time.perf_counter() - t0
            except Exception as ex:                     # noqa: BLE001
                print(f"{ordnung} {nt}x{nr}: {type(ex).__name__}: {str(ex)[:100]}")
                continue
            sk = res.solid_knoten
            pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"]))}
            S = np.asarray(sk["spannung"])
            f = np.array([sl.von_mises(S[pos[n]]) for n in hk.nachweisknoten(m)]) / 1e6 - 355.0
            print(f"{ordnung:8s} {nt}x{nr}  FHG {m.ndof - 3 * m.nn:7d} (Ecken {3 * m.nn}, Zusatz "
                  f"{tp.anzahl_fhg(m)})  Abweichung min {f.min():+8.2f}  max {f.max():+8.2f}  "
                  f"Mittel {f.mean():+8.2f} N/mm2  ({dt:.1f} s)", flush=True)


if __name__ == "__main__":
    main()
