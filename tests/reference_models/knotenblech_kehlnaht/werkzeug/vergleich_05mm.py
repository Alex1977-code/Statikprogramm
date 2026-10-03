# -*- coding: utf-8 -*-
"""Abnahme Knotenblech mit 0,5 mm am Uebergang pruefen (Kriterien in ABNAHME-05MM.md,
vor der Rechnung festgelegt, 02.10.2026) und die Erwartungswerte schreiben.

Abgewandelt aus werkzeug/vergleich.py (PR #13): Die Netzpruefung zaehlt die
C3D10-Zeilen der Datei statt fester Zahlen, und je Nahtpunkt steht die Aenderung
gegen die 1-mm-Referenz daneben (Netzkonvergenz belegt bei hoechstens 1 %).

Aufruf: python vergleich_05mm.py <eichung-ordner> <referenz-ordner> <ziel.json> <erwartung_tet10.json 1 mm>
"""
import json
import os
import sys

import numpy as np


def lade(o, n):
    with open(os.path.join(o, n), encoding="utf-8") as f:
        return json.load(f)


def kantenlaenge_uebergang(o):
    X = np.load(os.path.join(o, "knoten_m.npy")) * 1e3
    T = np.load(os.path.join(o, "tet10.npy"))[:, :4]
    C = X[T]
    nah = np.zeros(len(T), bool)
    for x0 in (64.0, 136.0):
        d = np.sqrt((C[:, :, 0] - x0) ** 2 + C[:, :, 2] ** 2)
        im_band = (C[:, :, 1] >= 30.0) & (C[:, :, 1] <= 50.0)
        nah |= np.any((d <= 1.5) & im_band, axis=1)
    L = []
    for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
        L.append(np.linalg.norm(C[nah, a] - C[nah, b], axis=1))
    L = np.concatenate(L)
    return {"tetraeder": int(nah.sum()), "median_mm": float(np.median(L)),
            "p90_mm": float(np.percentile(L, 90)), "max_mm": float(L.max())}


def c3d10_zeilen(pfad):
    """Elementzeilen unter *ELEMENT, TYPE=C3D10 (eine Zeile je Element bei 11 Zahlen)."""
    n, drin = 0, False
    with open(pfad, encoding="utf-8", errors="replace") as f:
        for zeile in f:
            if zeile.startswith("*"):
                kw = zeile.upper().replace(" ", "")
                drin = kw.startswith("*ELEMENT") and "TYPE=C3D10" in kw
                continue
            if drin and zeile.strip():
                n += 1
    return n


def main():
    eich, ref, ziel, alt_pfad = sys.argv[1:5]
    ok = True
    befund = []
    # --- Eichung
    ea, eb, el = lade(eich, "auswertung_a.json"), lade(eich, "auswertung_b.json"), lade(eich, "lauf.json")
    fa = max(abs(p["sigma_xx"] - 100.0) for p in ea["punkte"])
    fb = max(abs(p["sigma_xx"] - 100.0) for p in eb["punkte"])
    rest = max(abs(v) for p in eb["punkte"] for i, z in enumerate(p["sigma"]) for j, v in enumerate(z)
               if (i, j) != (0, 0))
    fr = abs(el["reaktion_x_an_x200_N"] - 80000.0)
    e_ok = fa <= 1e-6 and fb <= 1e-6 and rest <= 1e-6 and fr <= 0.01
    befund.append(f"Eichung: max|sxx-100| A {fa:.2e}, B {fb:.2e}; uebrige Komponenten B {rest:.2e}; "
                  f"Reaktion x200 {el['reaktion_x_an_x200_N']:.4f} N -> {'ERFUELLT' if e_ok else 'NICHT ERFUELLT'}")
    ok &= e_ok
    # --- Referenz
    ra, rb, rl = lade(ref, "auswertung_a.json"), lade(ref, "auswertung_b.json"), lade(ref, "lauf.json")
    n_datei = c3d10_zeilen(os.path.join(ref, "netz_c3d10.inp"))
    netz_ok = (rl["elemente"] == {"tet10": n_datei}
               and rl["stirn_x0"] == rl["nset_groessen_datei"].get("STIRN_X0")
               and rl["stirn_x200"] == rl["nset_groessen_datei"].get("STIRN_X200"))
    befund.append(f"Netz: {rl['elemente']} gegen {n_datei} C3D10-Zeilen der Datei, Knoten {rl['knoten_benutzt']}, "
                  f"Stirn {rl['stirn_x0']}/{rl['stirn_x200']} "
                  f"gegen NSET {rl['nset_groessen_datei']} -> {'ERFUELLT' if netz_ok else 'NICHT ERFUELLT'}")
    ok &= netz_ok
    R = np.load(os.path.join(ref, "reaktion_N.npy"))
    X = np.load(os.path.join(ref, "knoten_m.npy"))
    r0 = float(R[np.abs(X[:, 0]) < 1e-9, 0].sum())
    r200 = float(R[np.abs(X[:, 0] - 0.2) < 1e-9, 0].sum())
    gg = abs(r0 + r200) / abs(r200)
    befund.append(f"Gleichgewicht: Rx(x0) {r0:.3f} N, Rx(x200) {r200:.3f} N, rel {gg:.1e} -> "
                  f"{'ERFUELLT' if gg <= 1e-9 else 'NICHT ERFUELLT'}")
    ok &= gg <= 1e-9
    d_hs = max(abs(a["sigma_hs"] - b["sigma_hs"]) / abs(b["sigma_hs"]) for a, b in zip(ra["hot_spot"], rb["hot_spot"]))
    d_xx = max(abs(a["sigma_xx"] - b["sigma_xx"]) / abs(b["sigma_xx"]) for a, b in zip(ra["punkte"], rb["punkte"]))
    ab_ok = d_hs <= 0.01 and d_xx <= 0.02
    befund.append(f"A gegen B: sigma_hs max {d_hs * 100:.3f} %, sigma_xx max {d_xx * 100:.3f} % -> "
                  f"{'ERFUELLT' if ab_ok else 'NICHT ERFUELLT'}")
    ok &= ab_ok
    hs = {(h["seite"], h["y_mm"]): h["sigma_hs"] for h in rb["hot_spot"]}
    sym_rl = max(abs(hs[("rechts", y)] - hs[("links", y)]) / abs(hs[("rechts", y)]) for y in map(float, range(32, 49, 2)))
    sym_y = max(abs(hs[(s, 40.0 + d)] - hs[(s, 40.0 - d)]) / abs(hs[(s, 40.0)])
                for s in ("rechts", "links") for d in (2.0, 4.0, 6.0, 8.0))
    kl = kantenlaenge_uebergang(ref)
    befund.append(f"Symmetrie rechts/links max {sym_rl * 100:.3f} %, um y = 40 max {sym_y * 100:.3f} % (berichtet)")
    befund.append(f"Kantenlaenge am Uebergang: Median {kl['median_mm']:.3f} mm, 90 % {kl['p90_mm']:.3f} mm, "
                  f"max {kl['max_mm']:.3f} mm ({kl['tetraeder']} Tetraeder)")
    # Aenderung gegen die 1-mm-Referenz je Nahtpunkt (berichtet; Netzkonvergenz bei <= 1 %)
    with open(alt_pfad, encoding="utf-8") as f:
        alt = json.load(f)
    alt_hs = {(h["seite"], float(h["y_mm"])): h["sigma_hs"] for h in alt["hot_spot"]}
    aenderung = {f"{s} {y:g}": (hs[(s, y)] - alt_hs[(s, y)]) / alt_hs[(s, y)] for (s, y) in sorted(hs)}
    groesste = max(aenderung.values(), key=abs)
    befund.append("Aenderung sigma_hs gegen 1 mm: " + ", ".join(f"{k} {v * 100:+.2f} %" for k, v in aenderung.items()))
    befund.append(f"Netzkonvergenz: groesste Aenderung {groesste * 100:+.2f} % -> "
                  f"{'BELEGT (<= 1 %)' if abs(groesste) <= 0.01 else 'NICHT BELEGT (> 1 %)'} (berichtet)")
    for z in befund:
        print(z)
    if not ok:
        print("ABNAHME NICHT ERFUELLT - keine erwartung_tet10.json")
        return 1
    a_pkt = {(p["seite"], p["lage"], p["y_mm"]): p for p in ra["punkte"]}
    a_hs = {(h["seite"], h["y_mm"]): h["sigma_hs"] for h in ra["hot_spot"]}
    erw = {
        "modell": "knotenblech_kehlnaht",
        "beschreibung": "Tet10-Referenz des Hauptprogramms statik3d (Entscheidung E2 des Anwenders, 29.09.2026)",
        "programmstand": {"commit": rl["commit"], "zweig": "main"},
        "netz": {"quelle": rl["netz"], "sha256": rl["netz_sha256"],
                 "erzeuger": "gmsh (Session B), C3D10, 0,5 mm am Uebergang",
                 "elemente_tet10": n_datei, "knoten": rl["knoten_benutzt"],
                 "kantenlaenge_uebergang_mm": {k: round(v, 3) for k, v in kl.items() if k != "tetraeder"},
                 "hinweis": "nur die C3D10-Elemente der Datei; die CPS6-Stirnflaechen sind weggelassen"},
        "werkstoff": {"E_N_mm2": 210000.0, "nu": 0.3},
        "randbedingungen": {
            "ux_x0_mm": 0.0, "ux_x200_mm": round(100.0 / 210000.0 * 200.0, 9), "quer": "frei",
            "starrkoerper": {"uy_uz_0_bei_mm": [round(v * 1e3, 6) for v in rl["starrkoerper"]["uy_uz_0"]],
                             "uz_0_bei_mm": [round(v * 1e3, 6) for v in rl["starrkoerper"]["uz_0"]]}},
        "reaktion_x_an_x200_N": round(r200, 3),
        "auswertung": {
            "primaer": "sigma_xx = Spannungsfeld des Tet10-Elements am Punkt (interpoliert, Rohwert), "
                       "gemittelt ueber die Elemente, die den Punkt enthalten",
            "zum_vergleich": "sigma_xx_knoten = geglaettete Eckspannung des Loesers (res.solid_knoten), "
                             "linear im Oberflaechendreieck interpoliert",
            "einheit": "N/mm2"},
        "punkte": [{"seite": p["seite"], "lage": p["lage"], "x_mm": p["x_mm"], "y_mm": p["y_mm"], "z_mm": 0.0,
                    "sigma_xx": round(p["sigma_xx"], 4),
                    "sigma_xx_knoten": round(a_pkt[(p["seite"], p["lage"], p["y_mm"])]["sigma_xx"], 4)}
                   for p in rb["punkte"]],
        "hot_spot": [{"seite": h["seite"], "y_mm": h["y_mm"], "sigma_hs": round(h["sigma_hs"], 4),
                      "sigma_hs_knoten": round(a_hs[(h["seite"], h["y_mm"])], 4)} for h in rb["hot_spot"]],
        "aenderung_gegen_1mm": {k: round(v, 6) for k, v in aenderung.items()},
        "pruefung": {"eichung_max_abweichung_N_mm2": max(fa, fb),
                     "primaer_gegen_knoten_hs_max": round(d_hs, 6),
                     "symmetrie_rechts_links_max": round(sym_rl, 6), "symmetrie_y40_max": round(sym_y, 6)},
    }
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with open(ziel, "w", encoding="utf-8", newline="\n") as f:
        json.dump(erw, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("ABNAHME ERFUELLT ->", ziel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
