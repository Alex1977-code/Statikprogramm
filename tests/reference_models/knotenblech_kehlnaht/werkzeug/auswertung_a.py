# -*- coding: utf-8 -*-
"""Auswertung A (01.10.2026): die geglaettete Eckspannung des Loesers.

Programmweg: res.solid_knoten (randspannung_knoten - Knotenmittel des
Elementfelds an den Ecken je Koerper und Werkstoff, dieselbe Spannung, die der
Volumennachweis liest). Je Referenzpunkt das Dreieck der freien Blechoberseite
z = 0 (Randseite, die nur zu einem Tetraeder gehoert, alle drei Ecken auf z = 0),
das den Punkt in der Ebene enthaelt; die Eckwerte linear interpoliert, auf einer
Kante das Mittel beider Dreiecke.

Aufruf: python auswertung_a.py <ausgabeordner des Laufs>
"""
import json
import os
import sys

import numpy as np


def punkte():
    out = []
    for seite, x04, x10 in (("rechts", 140.0, 146.0), ("links", 60.0, 54.0)):
        for y in range(32, 49, 2):
            out.append((seite, "0.4t", x04, float(y)))
            out.append((seite, "1.0t", x10, float(y)))
    return out


def main():
    aus = sys.argv[1]
    X = np.load(os.path.join(aus, "knoten_m.npy")) * 1e3        # mm
    T = np.load(os.path.join(aus, "tet10.npy"))
    kn = np.load(os.path.join(aus, "solid_knoten_knoten.npy"))
    gr = np.load(os.path.join(aus, "solid_knoten_gruppe.npy"))
    sp = np.load(os.path.join(aus, "solid_knoten_spannung.npy")) / 1e6   # N/mm2
    assert len(np.unique(gr)) == 1, "mehr als ein Koerper/Werkstoff"
    sxx = np.full(len(X), np.nan)
    sxx[kn] = sp[:, 0]
    # Randseiten (Eckdreiecke), die nur einmal vorkommen
    zahl = {}
    for t in T[:, :4]:
        for f in ((0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)):
            s = tuple(sorted(int(t[j]) for j in f))
            zahl[s] = zahl.get(s, 0) + 1
    oben = np.array([s for s, z in zahl.items() if z == 1 and np.all(np.abs(X[list(s), 2]) < 1e-9)])
    P = X[oben][:, :, :2]                                          # (nf, 3, 2)
    ergebnis = []
    for seite, lage, x, y in punkte():
        q = np.array([x, y])
        a, b, c = P[:, 0], P[:, 1], P[:, 2]
        v0, v1, v2 = b - a, c - a, q - a
        d = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
        l1 = (v2[:, 0] * v1[:, 1] - v2[:, 1] * v1[:, 0]) / d
        l2 = (v0[:, 0] * v2[:, 1] - v0[:, 1] * v2[:, 0]) / d
        l0 = 1.0 - l1 - l2
        drin = np.flatnonzero((l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9))
        assert drin.size, (x, y)
        w = [float(l0[i] * sxx[oben[i, 0]] + l1[i] * sxx[oben[i, 1]] + l2[i] * sxx[oben[i, 2]])
             for i in drin]
        ergebnis.append({"seite": seite, "lage": lage, "x_mm": x, "y_mm": y, "dreiecke": int(drin.size),
                         "sigma_xx": float(np.mean(w)), "spanne_xx": float(np.max(w) - np.min(w))})
    hs = []
    for seite in ("rechts", "links"):
        for y in range(32, 49, 2):
            a = next(e for e in ergebnis if e["seite"] == seite and e["lage"] == "0.4t" and e["y_mm"] == y)
            b = next(e for e in ergebnis if e["seite"] == seite and e["lage"] == "1.0t" and e["y_mm"] == y)
            hs.append({"seite": seite, "y_mm": float(y),
                       "sigma_hs": 5.0 / 3.0 * a["sigma_xx"] - 2.0 / 3.0 * b["sigma_xx"]})
    out = {"verfahren": "A: geglaettete Eckspannung des Loesers (res.solid_knoten), linear auf der Oberseite",
           "dreiecke_oberseite": int(len(oben)), "punkte": ergebnis, "hot_spot": hs}
    with open(os.path.join(aus, "auswertung_a.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for h in hs:
        print(f"A {h['seite']:6s} y {h['y_mm']:4.0f}: sigma_hs {h['sigma_hs']:9.4f}")


if __name__ == "__main__":
    main()
