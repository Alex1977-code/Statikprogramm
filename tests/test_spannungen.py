"""
Spannungsgroessen fuer die Anzeige und die Werteskala (statik3d/spannungen.py).

Grundspannungen, Hauptspannungen, Vergleichsspannung und Kontaktdruck gegen
geschlossene Werte; Mittelung auf die Knoten; die Farbskala mit Grenzwert
(355 fuer S355): darueber eine eigene Farbe, der Groesstwert als Beschriftung,
und die Anzeige nur der Ueberschreitungen.

Aufruf:  python -m tests.test_spannungen
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d import solver, examples_lib, spannungen as sp  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")


def test_volumen():
    """Ebener Tensor sx = 100, sy = 50, txy = 30 (MPa): Hauptspannungen aus der
    Mohrschen Formel, von Mises, Tresca; hydrostatisch: s1 = s2 = s3."""
    S = np.array([[100.0, 50.0, 0.0, 30.0, 0.0, 0.0], [10.0, 10.0, 10.0, 0.0, 0.0, 0.0]])
    m, r = 75.0, np.hypot(25.0, 30.0)
    s1, s2 = m + r, m - r
    check("Komponenten unveraendert", np.allclose(sp.volumen_werte(S, "txy"), [30.0, 0.0])
          and np.allclose(sp.volumen_werte(S, "sz"), [0.0, 10.0]))
    check("Hauptspannungen sortiert (Mohr): s1, s2, s3 = 0",
          np.allclose(sp.volumen_werte(S, "s1")[0], s1) and np.allclose(sp.volumen_werte(S, "s2")[0], s2)
          and abs(sp.volumen_werte(S, "s3")[0]) < 1e-9,
          f"{sp.volumen_werte(S, 's1')[0]:.3f} / {s1:.3f}")
    sv = np.sqrt(100 ** 2 - 100 * 50 + 50 ** 2 + 3 * 30 ** 2)
    check("von Mises = sqrt(sx² - sx sy + sy² + 3 txy²)", np.allclose(sp.volumen_werte(S, "sv")[0], sv),
          f"{sp.volumen_werte(S, 'sv')[0]:.3f} / {sv:.3f}")
    check("Tresca sint = s1 - s3, tmax = sint/2", np.allclose(sp.volumen_werte(S, "sint")[0], s1)
          and np.allclose(sp.volumen_werte(S, "tmax")[0], s1 / 2))
    check("hydrostatisch: alle drei Hauptspannungen gleich, von Mises 0",
          np.allclose(sp.volumen_werte(S, "s1")[1], 10.0) and np.allclose(sp.volumen_werte(S, "s3")[1], 10.0)
          and abs(sp.volumen_werte(S, "sv")[1]) < 1e-9)


def test_flaechen_und_staebe():
    oben = np.array([[100.0, 0.0, 0.0], [-20.0, -20.0, 0.0]])
    unten = np.array([[-120.0, 0.0, 0.0], [10.0, 10.0, 0.0]])
    check("Flaeche: Seite oben/unten getrennt, max = groesserer Betrag mit Vorzeichen",
          np.allclose(sp.flaechen_werte(oben, unten, "sx", "oben"), [100.0, -20.0])
          and np.allclose(sp.flaechen_werte(oben, unten, "sx", "unten"), [-120.0, 10.0])
          and np.allclose(sp.flaechen_werte(oben, unten, "sx", "max"), [-120.0, -20.0]))
    check("Flaeche: s1/s2 ebener Spannungszustand, von Mises",
          np.allclose(sp.flaechen_werte(oben, unten, "s1", "oben"), [100.0, -20.0])
          and np.allclose(sp.flaechen_werte(oben, unten, "s2", "oben"), [0.0, -20.0])
          and np.allclose(sp.flaechen_werte(oben, unten, "sv", "oben"), [100.0, 20.0]))
    # Rahmen: Stabspannungen aus N und M, an den Enden, gemittelt am Knoten
    m = examples_lib.build_example("frame")
    lf = list(m.load_cases)[0]
    res = solver.solve_cases(m, [lf])[lf]
    ids, w = sp.stab_werte(m, res, "sx")
    i0 = int(ids[0])
    d = res.beam_forces[i0]
    sec = m.sections[m.elements[i0].sec]
    erwartet = abs(d["N"][0]) / sec.A + abs(d["My"][0]) * sec.zmax / sec.Iy + abs(d["Mz"][0]) * sec.ymax / sec.Iz
    check("Stab: sigma_x Rand am Anfang = |N|/A + |My| zmax/Iy + |Mz| ymax/Iz",
          np.isclose(w[0, 0], erwartet) and max(w.max(axis=1)) <= max(d2["sig_max"] for d2 in res.beam_forces.values()) + 1e-6,
          f"{w[0, 0] / 1e6:.2f} N/mm²")
    kn = sp.je_knoten(m, res, "staebe", "sn")
    n0 = int(m.elements[i0].nodes[0])
    beteiligt = [(i, k) for i in res.beam_forces for k in (0, -1) if int(m.elements[i].nodes[k]) == n0]
    soll = np.mean([res.beam_forces[i]["N"][0 if k == 0 else 1] / m.sections[m.elements[i].sec].A
                    for i, k in beteiligt]) * 1e-6
    check("Stab: sigma_N je Knoten = Mittel der Elementenden am Knoten (N/mm²)",
          np.isclose(kn[n0], soll) and np.isnan(kn).sum() < m.nn, f"{kn[n0]:.3f} / {soll:.3f}")
    check("Knotenmittel: zwei Beitraege am selben Knoten werden gemittelt, sonst NaN",
          np.allclose(sp.knotenmittel(3, [0, 0, 2], [1.0, 3.0, 5.0])[[0, 2]], [2.0, 5.0])
          and np.isnan(sp.knotenmittel(3, [0, 0, 2], [1.0, 3.0, 5.0])[1]))


def test_volumen_und_kontakt():
    """Block mit Reibung: Auflast 90 kN, Horizontalkraft 20 kN. Der Kontaktdruck
    aus Knotenkraft und Einflussflaeche integriert sich zur Auflast, die
    Vergleichsspannung je Knoten stimmt mit Results.node_vm ueberein."""
    m = examples_lib.build_example("friction")
    lf = list(m.load_cases)[0]
    res = solver.solve_cases(m, [lf])[lf]
    sv = sp.je_knoten(m, res, "volumen", "sv")
    ref = res.node_vm * 1e-6
    vol = [n for i, e in enumerate(m.elements) if e.typ == "hex8" for n in e.nodes]
    vol = np.unique(vol)
    nur_vol = [n for n in vol if not any(n in m.elements[i].nodes for i in res.shell_stress)]
    check("Volumen: von Mises je Knoten = Results.node_vm (Knoten ohne Schalenanteil)",
          np.allclose(sv[nur_vol], ref[nur_vol], rtol=1e-9, atol=1e-9) and len(nur_vol) > 50,
          f"{len(nur_vol)} Knoten, max {np.nanmax(sv):.3f} N/mm²")
    # Results.node_vm (vektorisiert seit 12.09.2026) = die alte Schleife je Element
    from statik3d.elements import solid as sl
    acc, cnt = np.zeros(m.nn), np.zeros(m.nn)
    for i, d in res.beam_forces.items():
        for n in m.elements[i].nodes:
            acc[n] += d["sig_max"]; cnt[n] += 1
    for i, d in res.shell_stress.items():
        for n in m.elements[i].nodes:
            acc[n] += d["vM"]; cnt[n] += 1
    for i, s in res.solid_res.items():
        for n in m.elements[i].nodes:
            acc[n] += sl.von_mises(s); cnt[n] += 1
    alt_vm = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    check("Results.node_vm vektorisiert = Schleife je Element (Staebe, Schalen, Volumen)",
          np.allclose(res.node_vm, alt_vm, equal_nan=True, rtol=1e-9, atol=1e-6)
          and np.isnan(res.node_vm).sum() == np.isnan(alt_vm).sum(),
          f"max {np.nanmax(res.node_vm) / 1e6:.3f} N/mm²")
    knoten = np.array([c["node"] for c in res.contact])
    A = sp.kontaktflaechen(m, knoten)
    P = m.nodes[knoten]
    dx = P[:, 0].max() - P[:, 0].min()
    dy = P[:, 1].max() - P[:, 1].min()
    check("Kontakt: Einflussflaechen der 25 Kontaktknoten = Grundflaeche des Blocks",
          np.isclose(A[knoten].sum(), dx * dy) and np.all(A[knoten] > 0)
          and np.isclose(A.sum(), A[knoten].sum()),
          f"{A[knoten].sum():.4f} / {dx * dy:.4f} m²")
    p = sp.kontakt_je_knoten(m, res, "p")
    Fn = sum(c["Fn"] for c in res.contact)
    check("Kontaktdruck p = Fn/A: Summe p·A = Summe Fn = Auflast, NaN ausserhalb",
          np.isclose(np.nansum(p[knoten] * 1e6 * A[knoten]), Fn) and np.isclose(Fn, 90e3)
          and np.isnan(p).sum() == m.nn - len(knoten),
          f"Σ p·A = {np.nansum(p[knoten] * 1e6 * A[knoten]) / 1e3:.2f} kN")
    tau = sp.kontakt_je_knoten(m, res, "tau")
    Ft = sum(c["Ft"] for c in res.contact)          # Summe der Betraege je Knoten
    Fx = abs(float(res.contact_forces[knoten, 0].sum()))
    check("Reibspannung τ = |Ft|/A: Summe τ·A = Summe |Ft| ≥ Horizontalkraft 20 kN (Resultierende)",
          np.isclose(np.nansum(tau[knoten] * 1e6 * A[knoten]), Ft) and Ft >= Fx - 1.0
          and np.isclose(Fx, 20e3, rtol=1e-3),
          f"Σ τ·A = {np.nansum(tau[knoten] * 1e6 * A[knoten]) / 1e3:.2f} kN, Resultierende {Fx / 1e3:.2f} kN")
    spalt = sp.kontakt_je_knoten(m, res, "spalt")
    fn = sp.kontakt_je_knoten(m, res, "fn")
    check("Spalt in mm, Kontaktkraft in kN", np.isclose(np.nansum(fn), Fn / 1e3)
          and np.nanmax(np.abs(spalt)) < 1.0)
    check("Schluessel und Beschriftung", sp.schluessel("volumen", "sv") == "spannung:volumen:sv"
          and sp.beschriftung("volumen", "sv") == "Volumen σ_v (von Mises) [N/mm²]"
          and sp.beschriftung("flaechen", "sx", "oben") == "Flächen σ_x oben [N/mm²]"
          and sp.beschriftung("kontakt", "spalt") == "Kontakt Spalt [mm]")


def test_werteskala():
    w = np.array([0.0, 100.0, 250.0, 400.0, np.nan])
    s = sp.Werteskala(modus="grenze", grenze=355.0, stufen=9)
    g = sp.grenzen(s, w)
    check("Grenze 355: Skala 0 … 355, darueber eigene Farbe, Beschriftung = Groesstwert 400",
          g["clim"] == [0.0, 355.0] and g["above_color"] == sp.FARBE_UEBER and g["above_label"] == "400"
          and g["anzahl_ueber"] == 1 and g["below_color"] is None and g["n_colors"] == 9 and g["n_labels"] == 10,
          str({k: g[k] for k in ("clim", "above_label", "anzahl_ueber")}))
    g = sp.grenzen(s, np.array([0.0, 100.0, 250.0]))
    check("nichts ueber der Grenze: keine Sonderfarbe", g["above_color"] is None and g["anzahl_ueber"] == 0)
    g = sp.grenzen(s, np.array([-400.0, -10.0, 100.0]))
    check("negative Werte: Skala −355 … 355, darunter eigene Farbe mit Kleinstwert",
          g["clim"] == [-355.0, 355.0] and g["below_color"] == sp.FARBE_UNTER and g["below_label"] == "-400"
          and g["anzahl_unter"] == 1 and g["above_color"] is None)
    s.nur_ueber = True
    g = sp.grenzen(s, w)
    check("nur Ueberschreitungen: nur |Wert| > 355 bleibt, Skala von der Grenze bis zum Groesstwert",
          np.isnan(g["werte"][:3]).all() and g["werte"][3] == 400.0 and g["clim"] == [355.0, 400.0]
          and g["anzahl_ueber"] == 1)
    g = sp.grenzen(sp.Werteskala(modus="fest", unten=10.0, oben=200.0), w)
    check("fest: unten/oben, darueber und darunter je eigene Farbe",
          g["clim"] == [10.0, 200.0] and g["above_label"] == "400" and g["below_label"] == "0"
          and g["anzahl_ueber"] == 2 and g["anzahl_unter"] == 1)
    g = sp.grenzen(sp.Werteskala(), w)
    check("auto: Grenzen aus den Werten (ohne NaN)", g["clim"] == [0.0, 400.0] and g["above_color"] is None)
    g = sp.grenzen(sp.Werteskala(), np.array([np.nan, np.nan]))
    check("ohne Werte: 0 … 1", g["clim"] == [0.0, 1.0] and g["wmax"] is None)
    d = sp.Werteskala(modus="grenze", grenze=235.0, stufen=12, nur_ueber=True).to_dict()
    s2 = sp.Werteskala.from_dict(d)
    check("Speichern und Laden der Einstellung, Unsinn wird abgefangen",
          s2 == sp.Werteskala(modus="grenze", grenze=235.0, stufen=12, nur_ueber=True)
          and sp.Werteskala.from_dict({"modus": "x", "stufen": 1}).modus == "auto"
          and sp.Werteskala.from_dict({"stufen": 1}).stufen == 2)


def main():
    for t in (test_volumen, test_flaechen_und_staebe, test_volumen_und_kontakt, test_werteskala):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(t.__name__, False, str(ex)[:120])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    fehl = [n for n, ok in RESULTS if not ok]
    if fehl:
        print("FEHLGESCHLAGEN:", fehl)
        return 1
    print("ALLE TESTS BESTANDEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
