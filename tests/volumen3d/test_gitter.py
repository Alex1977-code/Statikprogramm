"""T2c: Wurzelgitter - Klassifikation gegen feine Abtastung, Modenzahl gegen die
geschlossene Formel, gemeinsame Moden von Nachbarn, Punktsuche.

Aufruf: python -m tests.volumen3d.test_gitter
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from tests.volumen3d._pruef import check, lauf  # noqa: E402


def _kugel_gitter(h=10.0):
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 43.0}})
    return g, Gitter(g, h=h, polster=0.1)


def test_klassifikation():
    from volumen3d.fcm.gitter import CUT, INSIDE, OUTSIDE
    g, G = _kugel_gitter()
    check("Wurzelgitter: 9x9x9 Zellen (86 mm + 2 mm Polster bei h = 10)", list(G.n) == [9, 9, 9], str(G.n))
    rng = np.random.default_rng(2)
    falsch = 0
    for c in range(len(G.ijk)):
        lo, hi = G.zellbox(c)
        P = rng.uniform(lo, hi, (300, 3))
        if G.klasse[c] == INSIDE and not g.innen(P).all():
            falsch += 1
    check("INSIDE-Zellen sind wirklich ganz innen (300 Stichproben je Zelle)", falsch == 0, f"{falsch} falsch")
    Pm, I = G.alle_mitten()
    aussen = G.alle_klassen == OUTSIDE
    falsch = 0
    for i in np.flatnonzero(aussen):
        lo = G.ursprung + I[i] * G.h
        if g.innen(rng.uniform(lo, lo + G.h, (300, 3))).any():
            falsch += 1
    check("OUTSIDE-Zellen enthalten keinen Werkstoff", falsch == 0, f"{falsch} falsch")
    check("Zellklassen: innen, cut und aussen kommen vor",
          (G.klasse == INSIDE).sum() > 0 and (G.klasse == CUT).sum() > 0 and aussen.sum() > 0,
          f"innen {(G.klasse == INSIDE).sum()}, cut {(G.klasse == CUT).sum()}, aussen {aussen.sum()}")
    check("aktive Zellen = gesamt - aussen", len(G.ijk) == G.gesamt_zellen - aussen.sum())


def test_moden_vollgitter():
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [40, 30, 20]}})
    G = Gitter(g, h=10.0, polster=0.0)
    check("Quader ohne Polster: 4x3x2 Zellen, alle CUT (Oberflaeche liegt auf den Zellgrenzen)",
          list(G.n) == [4, 3, 2] and len(G.ijk) == 24, f"{G.n}, {len(G.ijk)} aktiv")
    for p in (1, 2, 3, 4):
        G.moden_nummerieren(p)
        soll = (4 * p + 1) * (3 * p + 1) * (2 * p + 1)
        check(f"p={p}: Moden = (n_x p+1)(n_y p+1)(n_z p+1) = {soll}", G.n_moden == soll, str(G.n_moden))
        zm = G.zell_moden
        check(f"p={p}: jede Zelle hat (p+1)^3 verschiedene Moden",
              zm.shape == (24, (p + 1) ** 3) and all(len(set(z)) == (p + 1) ** 3 for z in zm))
        check(f"p={p}: Nummern lueckenlos 0..n-1", set(zm.ravel()) == set(range(G.n_moden)))
    G.moden_nummerieren(3)
    a = np.flatnonzero((G.ijk == [0, 0, 0]).all(axis=1))[0]
    b = np.flatnonzero((G.ijk == [1, 0, 0]).all(axis=1))[0]
    c = np.flatnonzero((G.ijk == [1, 1, 0]).all(axis=1))[0]
    check("Nachbarn ueber eine Flaeche teilen (p+1)^2 = 16 Moden", len(set(G.zell_moden[a]) & set(G.zell_moden[b])) == 16)
    check("Nachbarn ueber eine Kante teilen p+1 = 4 Moden", len(set(G.zell_moden[a]) & set(G.zell_moden[c])) == 4)
    # geteilte Moden sind dieselben Funktionen: Mode (1,b,c) von Zelle a = Mode (0,b,c) von Zelle b
    from volumen3d.fcm.basis import modenklassen
    abc = modenklassen(3)["abc"]
    ok = True
    for m in range(len(abc)):
        if abc[m, 0] == 1:                       # rechte Seite von a
            m2 = np.flatnonzero((abc[:, 0] == 0) & (abc[:, 1] == abc[m, 1]) & (abc[:, 2] == abc[m, 2]))[0]
            ok &= G.zell_moden[a, m] == G.zell_moden[b, m2]
        elif abc[m, 0] >= 2:                     # hoehere x-Moden gehoeren ins Innere / die y-z-Flaechen, nie geteilt mit b
            ok &= G.zell_moden[a, m] not in set(G.zell_moden[b])
    check("geteilte Nummern entsprechen denselben Funktionen (Index 1 links = Index 0 rechts)", bool(ok))


def test_punktsuche():
    g, G = _kugel_gitter()
    P = np.array([[0, 0, 0], [40, 0, 0], [60, 60, 60.0]])
    c = G.zelle_finden(P)
    check("Punktsuche: Mitte und Randpunkt in aktiven Zellen, ausserhalb -1", c[0] >= 0 and c[1] >= 0 and c[2] == -1, str(c))
    xi = G.lokal(P[:2], c[:2])
    check("lokale Koordinaten in [-1,1]", np.all(np.abs(xi) <= 1 + 1e-12))
    lo, hi = G.zellbox(c[:2])
    check("Rueckabbildung", np.allclose(lo + 0.5 * (xi + 1) * (hi - lo), P[:2]))
    # Punkt genau auf einer Zellgrenze zwischen einer aktiven Zelle und ihrem OUTSIDE-Nachbarn in +x:
    # floor ohne Epsilon traefe die OUTSIDE-Zelle, der Epsilon-Rueckfall muss die aktive finden
    from volumen3d.fcm.gitter import OUTSIDE
    grenze = None
    for c in range(len(G.ijk)):
        I = G.ijk[c] + [1, 0, 0]
        if I[0] < G.n[0] and G.alle_klassen[G.flach(I)] == OUTSIDE:
            grenze = G.zellbox(c)[1] * [1, 0, 0] + (G.zellbox(c)[0] + 0.5 * G.h) * [0, 1, 1]
            break
    check("Punkt auf der Grenze aktive Zelle | OUTSIDE-Nachbar (+x) wird der aktiven Zelle zugeschlagen",
          grenze is not None and G.zelle_finden(grenze[None])[0] == c, f"{grenze} -> Zelle {G.zelle_finden(grenze[None])[0] if grenze is not None else None}, erwartet {c}")
    check("zell_dofs: 3 (p+1)^3 Eintraege, Reihenfolge 3*mode + Komponente",
          (G.moden_nummerieren(2) is not None) and list(G.zell_dofs(0)[:6]) == [3 * G.zell_moden[0, 0] + k for k in range(3)] + [3 * G.zell_moden[0, 1] + k for k in range(3)])


if __name__ == "__main__":
    sys.exit(lauf([test_klassifikation, test_moden_vollgitter, test_punktsuche]))
