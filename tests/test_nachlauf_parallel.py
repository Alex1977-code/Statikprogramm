"""
Nachlauf seriell gegen parallel (24.09.2026): die geglaettete Knotenspannung
(res.solid_knoten) muss bei jedem Arbeiterzahl bitgleich sein - auch mit
Tetraedern mit Ordnung p, auch wenn dasselbe Modell vorher schon einmal
gerechnet wurde.

Befund aus Fables Messung V5 (tests/messung_adaptiv_v5.py): die parallele
Rechnung brach bei tetp mit "max() iterable argument is empty" bzw. "tetp:
Element gehoert nicht zum Modell" ab. Ursache: tetp.index_von fand das
Element ueber id(Objekt) in einer Zuordnung, die mit dem Modell in den
Arbeitsprozess gepickelt wurde - dort sind es andere Objekte. Dazu: fehlt
einem Element im Nachlauf jeder Auswertepunkt, meldet der Nachlauf das mit
Elementnummer statt mit Pythons leerem max().

Aufruf:  python -m tests.test_nachlauf_parallel
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import parallel, solver                              # noqa: E402
from statik3d.elements import solid as sl, tetp                    # noqa: E402
from statik3d.model import FaceLoad                                # noqa: E402
from tests import pruefkoerper as pk                               # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")


def kugel_tetp(nt=4, nr=4):
    """Hohlkugel-Achtel aus tet10, Innendruck als Seitenlast, dann tetp:
    tetp4 an der Innenflaeche, sonst tetp2 (wie Fables 'tetp4innen')."""
    hk = pk.Hohlkugel()
    m = hk.modell("tet10", nt, nr)
    m.case().nodal_loads = []
    X = np.asarray(m.nodes)
    r = np.linalg.norm(X, axis=1)
    for i, e in enumerate(m.elements):
        for f, seite in enumerate(sl.FLAECHEN["tet10"]):
            if np.all(np.abs(r[[e.nodes[a] for a in seite]] - hk.a) < 1e-9):
                m.case().face_loads.append(FaceLoad(elem=i, p=hk.p, face=f))
    tetp.aus_tet10(m, ordnung=2)
    X = np.asarray(m.nodes)
    r = np.linalg.norm(X, axis=1)
    for e in m.elements:
        if np.any(np.abs(r[list(e.nodes[:4])] - hk.a) < 1e-9):
            e.typ = "tetp4"
    m._tetp_version = getattr(m, "_tetp_version", 0) + 1
    return m


def test_tetp_seriell_dann_parallel():
    alt = parallel.settings()
    alt_min, alt_chunk = alt.min_elements, alt.chunk_elements
    parallel.configure(min_elements=1, chunk_elements=7)
    try:
        m = kugel_tetp()
        r1 = next(iter(solver.solve_all(m, workers=1).cases.values()))
        try:
            r2 = next(iter(solver.solve_all(m, workers=2).cases.values()))
            a, b = r1.solid_knoten, r2.solid_knoten
            gleich = (np.array_equal(a["knoten"], b["knoten"])
                      and np.array_equal(np.asarray(a["spannung"]), np.asarray(b["spannung"])))
            text = f"{len(b['knoten'])} Knoten, {len(m.elements)} Elemente"
        except Exception as ex:                  # noqa: BLE001
            gleich, text = False, f"{type(ex).__name__}: {str(ex)[:70]}"
        check("tetp2/tetp4 (Hohlkugel): erst seriell, dann mit 2 Arbeitern - solid_knoten bitgleich",
              gleich, text)
    finally:
        parallel.configure(min_elements=alt_min, chunk_elements=alt_chunk)


def test_leerer_nachlauf_ist_laut():
    """Liefert ein Element keine Auswertepunkte, nennt der Nachlauf es."""
    m, _ids = pk.Kragarm().modell("hex8", 4, 1, 2)
    vorher = sl.spannungen_stapel

    def leer(model, typ, idx, E, nu, U, punkte=None):
        S, M = vorher(model, typ, idx, E, nu, U, punkte)
        return S[:, :0, :], M
    sl.spannungen_stapel = leer
    try:
        try:
            next(iter(solver.solve_all(m, workers=1).cases.values()))
            text = "lief durch"
            ok = False
        except Exception as ex:                  # noqa: BLE001
            text = str(ex)[:90]
            ok = "Element 1 (hex8)" in text and "max()" not in text
    finally:
        sl.spannungen_stapel = vorher
    check("keine Auswertepunkte: Meldung mit Elementnummer statt „max() iterable argument is empty“",
          ok, text)


def main():
    print("=" * 100)
    print("STATIK3D - Nachlauf seriell gegen parallel")
    print("=" * 100)
    for t in (test_tetp_seriell_dann_parallel, test_leerer_nachlauf_ist_laut):
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    ok = sum(1 for _n, o in RESULTS if o)
    print(f"\nErgebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
