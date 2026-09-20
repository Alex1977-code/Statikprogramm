"""
Fehlerschaetzer (statik3d.netzfehler) und adaptive Vernetzung (statik3d.adaptiv).

  * Ein gleichfoermiger Spannungszustand hat den Fehler null - Knotenmittel
    und Elementspannung fallen zusammen.
  * Das geschlossene Integral ueber den Tetraeder stimmt gegen die
    Zahlenquadratur.
  * Feineres Netz, kleinerer geschaetzter Fehler (Platte mit Bohrung unter Zug).
  * Die neuen Kantenlaengen halten Schritt und Budget ein.
  * Eine adaptive Runde: der Fehler faellt, die Elementzahl bleibt im Budget,
    das Netz geht durch die Abnahme, die Netzeinstellungen tragen das Feld.

Aufruf: python -m tests.test_netzfehler
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from statik3d.model import Model, Material                      # noqa: E402
from statik3d import mesher, netzfehler, adaptiv, diagnose, solver  # noqa: E402
from statik3d.solver import Results                             # noqa: E402
from test_netzfeld import platte_mit_bohrungen, zug_und_lager   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return bool(ok)


def _kleine_platte(h):
    """Platte 0,4 x 0,24 x 0,08 m mit Bohrung r = 40 mm unter Zug - klein
    genug, dass zwei Netze und zwei Rechnungen Sekunden brauchen."""
    m, k = platte_mit_bohrungen(0.4, 0.24, 0.08, bohrungen=((0.2, 0.12, 0.04),))
    zug_und_lager(m)
    m.netz.ziellaenge = h
    m.netz.dichte = "eigene"
    m.netz.max_elemente = 1_000_000
    return m, k


def test_gleichfoermige_spannung_hat_fehler_null():
    m, k = _kleine_platte(0.04)
    mesher.modell_vernetzen(m, [], workers=1)
    res = Results(name="Probe", model=m)
    s = np.array([100e6, 20e6, -5e6, 3e6, 0.0, 1e6])
    for i, e in enumerate(m.elements):
        if e.typ == "tet4":
            res.solid_res[i] = s.copy()
    ind = netzfehler.indikator(m, res)
    check("alle Tetraeder bewertet", ind["N"] == sum(1 for e in m.elements if e.typ == "tet4"), str(ind["N"]))
    check("gleichfoermige Spannung: Fehler je Element null", float(np.abs(ind["eta"]).max()) < 1e-9 * ind["U"],
          f"max eta {np.abs(ind['eta']).max():.3e}, U {ind['U']:.3e}")
    check("bezogener Fehler null", ind["eta_rel"] < 1e-9, f"{ind['eta_rel']:.2e}")
    # Energienorm der Loesung: U^2 = V * s^T C s mit C = D^-1
    from statik3d.elements.solid import D_matrix
    C = np.linalg.inv(D_matrix(210e9, 0.3))
    V = float(ind["V"].sum())
    check("U^2 = V * s^T D^-1 s", abs(ind["U"] ** 2 - V * (s @ C @ s)) < 1e-6 * ind["U"] ** 2)
    h_neu = netzfehler.neue_kantenlaengen(ind, 0.05)
    check("ohne Fehler wird ueberall bis zum Faktor groeber",
          np.allclose(h_neu, ind["h"] * netzfehler.FAKTOR_MAX))


def test_integral_ueber_den_tetraeder():
    """eta^2 = V/20 [ (Sum e_i)^T C (Sum e_i) + Sum e_i^T C e_i ] gegen eine
    Zahlenquadratur mit vielen Punkten in einem Tetraeder."""
    rng = np.random.default_rng(5)
    X = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float) * 0.1 + rng.normal(scale=0.01, size=(4, 3))
    C = np.diag(rng.uniform(0.5, 2.0, 6))
    E4 = rng.normal(size=(4, 6))
    V = abs(np.linalg.det(np.column_stack([X[1] - X[0], X[2] - X[0], X[3] - X[0]]))) / 6.0
    summe = E4.sum(axis=0)
    geschlossen = V / 20.0 * (summe @ C @ summe + np.einsum("ki,ij,kj->", E4, C, E4))
    # Quadratur: zufaellige baryzentrische Punkte (Dirichlet), Mittelwert mal V
    lam = rng.dirichlet(np.ones(4), size=200000)
    e = lam @ E4
    quad = V * float(np.mean(np.einsum("ni,ij,nj->n", e, C, e)))
    check("das geschlossene Integral trifft die Quadratur (0,5 %)",
          abs(geschlossen - quad) < 0.005 * quad, f"{geschlossen:.6g} gegen {quad:.6g}")


def test_feiner_ist_besser():
    werte = {}
    for h in (0.03, 0.015):
        m, k = _kleine_platte(h)
        mesher.modell_vernetzen(m, [], workers=1)
        res = solver.solve_static(m, case="LF1", workers=1)
        ind = netzfehler.indikator(m, res)
        werte[h] = (ind["eta_rel"], len(m.elements), float(ind["sv"].max()))
        check(f"h = {h * 1e3:.0f} mm: der Schaetzer liefert einen Wert zwischen 0 und 1",
              0.0 < ind["eta_rel"] < 1.0, f"{ind['eta_rel'] * 100:.1f} % bei {len(m.elements)} Elementen")
    check("das feinere Netz hat den kleineren geschaetzten Fehler", werte[0.015][0] < werte[0.03][0],
          f"{werte[0.03][0] * 100:.1f} % -> {werte[0.015][0] * 100:.1f} %")
    check("und die groessere Kerbspannung (der lineare Tetraeder ist zu steif)",
          werte[0.015][2] > werte[0.03][2] * 0.95,
          f"{werte[0.03][2] / 1e6:.0f} -> {werte[0.015][2] / 1e6:.0f} N/mm²")


def test_neue_kantenlaengen_und_budget():
    N = 1000
    rng = np.random.default_rng(11)
    h = np.full(N, 0.05)
    # U = 30: zulaessig je Element bei 5 % etwa 0,05 * 30 / sqrt(1000) = 0,047.
    # 950 Elemente liegen darunter (0,005 … 0,03), fuenfzig weit darueber.
    eta = rng.uniform(0.005, 0.03, N)
    eta[:50] = rng.uniform(0.5, 1.0, 50)
    ind = {"eta": eta, "h": h, "U": 30.0, "N": N, "p": np.ones(N, int),
           "V": np.full(N, 1e-6), "zentren": rng.uniform(0, 1, (N, 3)), "ids": np.arange(N), "sv": np.ones(N)}
    hn = netzfehler.neue_kantenlaengen(ind, ziel=0.05, wachstum_max=0.0)
    check("grosser Fehler -> feiner, kleiner Fehler -> groeber",
          hn[:50].max() < 0.05 and hn[50:].min() > 0.05, f"{hn[:50].max() * 1e3:.1f} / {hn[50:].min() * 1e3:.1f} mm")
    check("der Schritt bleibt im Fenster [1/3, 2]",
          hn.min() >= 0.05 * netzfehler.FAKTOR_MIN - 1e-12 and hn.max() <= 0.05 * netzfehler.FAKTOR_MAX + 1e-12)
    hb = netzfehler.neue_kantenlaengen(ind, ziel=0.005, wachstum_max=3.0, kalibrierung=1.0)
    n_neu = float(np.sum((h / hb) ** 3))
    check("mit Budget waechst die geschaetzte Elementzahl hoechstens auf das Dreifache",
          n_neu <= 3.0 * N * 1.001, f"{n_neu:.0f} von {N}")
    ho = netzfehler.neue_kantenlaengen(ind, ziel=0.005, wachstum_max=0.0)
    check("ohne Budget waere es weit mehr", float(np.sum((h / ho) ** 3)) > 3.0 * N, f"{np.sum((h / ho) ** 3):.0f}")
    hk = netzfehler.neue_kantenlaengen(ind, ziel=0.005, wachstum_max=3.0)
    # 5 % Spiel: die Deckelung einzelner Elemente (Faktor 2, h_min/h_max)
    # verhindert, dass die Skalierung das Budget genau trifft (606 von 600)
    check("die Kalibrierung laesst die Schaetzung nur noch ein Fuenftel des Budgets fuellen",
          float(np.sum((h / hk) ** 3)) <= 3.0 * N / netzfehler.KALIBRIERUNG * 1.05,
          f"{np.sum((h / hk) ** 3):.0f} von {3.0 * N / netzfehler.KALIBRIERUNG:.0f}")
    # Spannungsschutz: hoch beanspruchte Elemente werden nicht groeber
    ind2 = dict(ind)
    ind2["sv"] = np.ones(N)
    ind2["sv"][100:120] = 10.0                 # zwanzig hoch beanspruchte mit kleinem Fehler
    hs = netzfehler.neue_kantenlaengen(ind2, ziel=0.05, wachstum_max=0.0)
    check("hoch beanspruchte Elemente werden nicht groeber, die anderen schon",
          bool(np.all(hs[100:120] <= h[100:120] + 1e-12)) and hs[120:].mean() > 0.05,
          f"{hs[100:120].max() * 1e3:.1f} mm gegen {hs[120:].mean() * 1e3:.1f} mm")
    check("die Reihenfolge bleibt: wer den groesseren Fehler hat, wird nicht groeber als der Nachbar",
          bool(np.all(hb[np.argsort(-eta)][:-1] <= hb[np.argsort(-eta)][1:] + 1e-12)))
    hm = netzfehler.neue_kantenlaengen(ind, ziel=0.05, h_min=0.03, h_max=0.06)
    check("h_min und h_max deckeln", hm.min() >= 0.03 - 1e-12 and hm.max() <= 0.06 + 1e-12)


def test_adaptive_runde():
    m, k = _kleine_platte(0.03)
    log = []
    erg = adaptiv.adaptiv_vernetzen(m, ["LF1"], runden=1, log=log, workers=1)
    v = erg["verlauf"]
    check("zwei Durchgaenge", len(v) == 2, str(len(v)))
    if len(v) == 2:
        check("der geschaetzte Fehler faellt", v[1]["eta_rel"] < v[0]["eta_rel"],
              f"{v[0]['eta_rel'] * 100:.1f} % -> {v[1]['eta_rel'] * 100:.1f} %")
        check("die Elementzahl bleibt im Budget (das Dreifache, plus 15 % Spiel der Nachmessung)",
              v[1]["elemente"] <= 1.15 * netzfehler.WACHSTUM_MAX * v[0]["elemente"],
              f"{v[0]['elemente']} -> {v[1]['elemente']}")
        check("die Elementzahl ist nicht einfach ueberall gestiegen",
              v[1]["elemente"] > v[0]["elemente"], f"{v[0]['elemente']} -> {v[1]['elemente']}")
    check("die Netzeinstellungen tragen Koerperkantenlaenge und Feldpunkte",
          "V1" in m.netz.koerper_h and len(m.netz.feldpunkte) > 0,
          f"koerper_h {m.netz.koerper_h}, {len(m.netz.feldpunkte)} Feldpunkte")
    check("nebenflaechen_grob steht danach wieder auf der Vorgabe", m.netz.nebenflaechen_grob is False)
    bef = diagnose.abnahme(m)
    check("das adaptive Netz geht durch die Abnahme", not bef, str([b.pruefung for b in bef])[:120])
    check("das Protokoll fuehrt den Verlauf", sum(1 for z in log if z.startswith("Adaptiv Durchgang")) == 2)
    ind = erg["indikator"]
    L = ind["h"]
    d = np.linalg.norm(ind["zentren"] - [0.2, 0.12, 0.04], axis=1)
    check("fein an der Bohrung, grob am Rand",
          L[(d > 0.04) & (d < 0.06)].mean() < L[d > 0.15].mean(),
          f"{L[(d > 0.04) & (d < 0.06)].mean() * 1e3:.1f} mm an der Bohrung, {L[d > 0.15].mean() * 1e3:.1f} mm am Rand")
    # Speichern und Laden: das Feld entsteht aus den Einstellungen wieder
    m2 = Model.from_dict(m.to_dict())
    from statik3d import netzfeld
    feld = netzfeld.aufbauen(m2)
    check("aus der gespeicherten Datei entsteht dasselbe Feld wieder",
          feld is not None and len(feld.X) > 0 and abs(feld(np.array([[0.2, 0.16, 0.04]]))[0]
                                                      - netzfeld.aufbauen(m)(np.array([[0.2, 0.16, 0.04]]))[0]) < 1e-12)


def main():
    for t in (test_gleichfoermige_spannung_hat_fehler_null, test_integral_ueber_den_tetraeder,
              test_feiner_ist_besser, test_neue_kantenlaengen_und_budget, test_adaptive_runde):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:100])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
