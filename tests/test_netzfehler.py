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
    # Der Fehlerschaetzer liest Tetraeder (netzfehler.ORDNUNG); die Platte ist
    # sweepbar und bekaeme sonst Hexaeder und Keile (statik3d.sweep, 20.09.2026)
    m.netz.sweep = False
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


def test_hexaeder_und_keile_im_schaetzer():
    """Der Schaetzer liest seit 21.09.2026 auch hex8, pent6 und pyr5: an einer
    gesweepten Platte ist der Fehler bei gleichfoermiger Spannung null, die
    Energienorm stimmt, und unter Zug sammelt sich der Fehler an der Bohrung.
    Dann eine adaptive Runde auf dem gesweepten Netz: die Schleife verfeinert
    auch Hexaeder-Koerper, und der Fehler faellt."""
    m, k = platte_mit_bohrungen(0.4, 0.24, 0.08, bohrungen=((0.2, 0.12, 0.04),))
    # Die Vorgabe `netz.sweep` ist seit dem 21.09.2026 aus (992 entartete
    # Keile am Drehlager); dieser Fall hat das gesweepte Netz zum Gegenstand.
    m.netz.sweep = True
    zug_und_lager(m)
    m.netz.ziellaenge = 0.03
    m.netz.dichte = "eigene"
    m.netz.max_elemente = 1_000_000
    mesher.modell_vernetzen(m, [], workers=1)
    typen = {e.typ for e in m.elements}
    check("die Platte ist gesweept (hex8 und pent6)", typen <= {"hex8", "pent6"} and "hex8" in typen, str(typen))
    res = Results(name="Probe", model=m)
    s_ = np.array([100e6, 20e6, -5e6, 3e6, 0.0, 1e6])
    for i, e in enumerate(m.elements):
        res.solid_res[i] = s_.copy()
    ind = netzfehler.indikator(m, res)
    check("alle Elemente bewertet, Hexaeder wie Keile", ind["N"] == len(m.elements), f"{ind['N']} von {len(m.elements)}")
    check("gleichfoermige Spannung: Fehler je Element null", float(np.abs(ind["eta"]).max()) < 1e-9 * ind["U"],
          f"max eta {np.abs(ind['eta']).max():.3e}, U {ind['U']:.3e}")
    from statik3d.elements.solid import D_matrix, solid_volume
    C = np.linalg.inv(D_matrix(210e9, 0.3))
    V = float(ind["V"].sum())
    V_el = sum(solid_volume(e.typ, m.nodes[e.nodes]) for e in m.elements)
    check("die Volumen der Quadratur sind die der Elemente", abs(V - V_el) < 1e-9 * V_el, f"{V:.6e} gegen {V_el:.6e}")
    check("U^2 = V * s^T D^-1 s", abs(ind["U"] ** 2 - V * (s_ @ C @ s_)) < 1e-6 * ind["U"] ** 2)
    # Mit Rechnung: der Fehler sammelt sich an der Bohrung
    res = solver.solve_static(m, case="LF1", workers=1)
    ind = netzfehler.indikator(m, res)
    check("bezogener Fehler zwischen 0 und 1", 0.0 < ind["eta_rel"] < 1.0, f"{ind['eta_rel'] * 100:.1f} %")
    d = np.linalg.norm(ind["zentren"] - [0.2, 0.12, 0.04], axis=1)
    nah, fern = ind["eta"][d < 0.07], ind["eta"][d > 0.12]
    check("Fehler je Element an der Bohrung groesser als im Feld", nah.mean() > 1.5 * fern.mean(),
          f"{nah.mean():.3e} an der Bohrung, {fern.mean():.3e} im Feld")
    # Zwei adaptive Runden auf dem gesweepten Netz: die Lagen folgen dem Feld
    # (sweep._lagen_aus_weg), die Kalibrierung dem Elementgemisch
    log = []
    erg = adaptiv.adaptiv_vernetzen(m, ["LF1"], runden=2, log=log, workers=1, grob_beginnen=False)
    v = erg["verlauf"]
    check("drei Durchgaenge auf Hexaedern und Keilen", len(v) == 3 and {e.typ for e in m.elements} <= {"hex8", "pent6"},
          f"{len(v)} Durchgaenge, {sorted({e.typ for e in m.elements})}")
    if len(v) == 3:
        check("der geschaetzte Fehler faellt ueber die Runden (gemessen 13,7 -> 9,2 %)",
              v[2]["eta_rel"] < v[0]["eta_rel"],
              " -> ".join(f"{x['eta_rel'] * 100:.1f} %" for x in v))
        check("die Elementzahl waechst je Runde, im Budget (das Dreifache plus 15 %)",
              all(v[i]["elemente"] < v[i + 1]["elemente"] <= 1.15 * netzfehler.WACHSTUM_MAX * v[i]["elemente"]
                  for i in range(2)), " -> ".join(str(x["elemente"]) for x in v))
        lagen = [z.split(", ")[1] for z in log if "gesweept - Grundfläche" in z]
        check("die Lagen werden mit dem Feld feiner (3 Lagen zu Beginn)", lagen and lagen[0].startswith("3 Lagen")
              and int(lagen[-1].split(" ")[0]) > 3, str(lagen))
    check("die Kalibrierung folgt dem Gemisch: Hexaedernetz 1,5, Tetraedernetz 5",
          abs(netzfehler.kalibrierung_fuer(m, erg["indikator"]) - netzfehler.KALIBRIERUNG_HEX) < 1e-12)
    check("die Netzeinstellungen tragen die Koerperkantenlaenge", "V1" in m.netz.koerper_h, str(m.netz.koerper_h))
    bef = diagnose.abnahme(m)
    check("das adaptive Hexaedernetz geht durch die Abnahme", not bef, str([b.pruefung for b in bef])[:120])


def test_mittelfeld_wird_bevorzugt():
    """`solid_res` traegt fuer ein elastisches Element den Punkt mit der
    hoechsten Vergleichsspannung, fuer ein fliessendes die Mitte
    (Loeser-Sitzung, 21.09.2026) - der Sprung waere dann zum Teil dieser
    Regelwechsel. Fuehrt der Loeser ein einheitliches Gausspunktmittel
    (netzfehler.MITTELFELD), nimmt der Schaetzer es."""
    m, k = _kleine_platte(0.04)
    mesher.modell_vernetzen(m, [], workers=1)
    res = Results(name="Probe", model=m)
    hoch = np.array([300e6, 0.0, 0.0, 0.0, 0.0, 0.0])
    mittel = np.array([100e6, 0.0, 0.0, 0.0, 0.0, 0.0])
    for i, e in enumerate(m.elements):
        if e.typ == "tet4":
            res.solid_res[i] = hoch.copy()
    ind1 = netzfehler.indikator(m, res)
    setattr(res, netzfehler.MITTELFELD, {i: mittel.copy() for i in res.solid_res})
    ind2 = netzfehler.indikator(m, res)
    check("ohne Mittelfeld zaehlt solid_res", abs(ind1["sv"].max() - 300e6) < 1e-6 * 300e6,
          f"{ind1['sv'].max() / 1e6:.1f} N/mm^2")
    check("mit Mittelfeld zaehlt dieses", abs(ind2["sv"].max() - 100e6) < 1e-6 * 100e6,
          f"{ind2['sv'].max() / 1e6:.1f} N/mm^2")
    check("dieselben Elemente, dieselbe Zahl", ind1["N"] == ind2["N"] and ind1["N"] > 0, str(ind2["N"]))
    check("die Energienorm folgt mit (ein Drittel der Spannung, ein Drittel der Norm)",
          abs(ind2["U"] - ind1["U"] / 3.0) < 1e-6 * ind1["U"], f"{ind2['U']:.4g} gegen {ind1['U'] / 3:.4g}")


def test_probelauf_nur_mit_fliessen():
    """Der Probelauf des Loesers (357d61d) laesst das Fliessen aus; so
    verfeinerte er am Drehlager an den falschen Stellen (54 von 100
    Spitzenelementen, Loeser-Sitzung 20.09.2026). Die Schleife erkennt das am
    Ergebnis und rechnet ein fliessendes Modell voll; elastische Modelle
    behalten den Probelauf. Der Loeser ist hier ein Stellvertreter, der nur
    protokolliert, wie er gerufen wurde."""
    aufrufe = []

    class Erg:
        def __init__(self, info):
            self.info = info

    def unecht(m, case=None, workers=None, probelauf=False, **kw):
        aufrufe.append(bool(probelauf))
        if probelauf:
            return Erg({"probelauf": True, "ndof": 12, "nfree": 9, "solver": "pardiso"})
        return Erg({"plastizitaet": {"schritte": 1}, "ndof": 12, "nfree": 9, "solver": "pardiso"})

    echt = solver.solve_static
    solver.solve_static = unecht
    try:
        m = Model()
        m.plastizitaet.an = True
        log = []
        rechnen = adaptiv._rechnen_standard(1, None, log)
        r1 = rechnen(m, "LF1")
        check("fliessendes Modell, Vorgabe: Probelauf gefragt, elastisch erkannt, voller Lauf gerechnet",
              aufrufe == [True, False] and "plastizitaet" in r1.info, str(aufrufe))
        check("das Protokoll sagt es", any("lässt das Fließen aus" in z for z in log))
        rechnen(m, "LF2")
        check("danach nur noch volle Laeufe, ohne neue Anfrage", aufrufe == [True, False, False], str(aufrufe))
        zahlen = adaptiv._loeserzahlen([r1], m)
        check("die Loeserzahlen nennen die Schluessel der Element-Sitzung und das Fliessen",
              "ndof 12" in zahlen and "nfree 9" in zahlen and "solver pardiso" in zahlen
              and "Fließen mitgerechnet" in zahlen, zahlen)
        aufrufe.clear()
        log.clear()
        m.plastizitaet.an = False
        r2 = adaptiv._rechnen_standard(1, None, log)(m, "LF1")
        check("elastisches Modell: der Probelauf bleibt, keine Warnung",
              aufrufe == [True] and r2.info.get("probelauf") is True and not log, str(aufrufe))
        aufrufe.clear()
        log.clear()
        m.plastizitaet.an = True
        r3 = adaptiv._rechnen_standard(1, True, log)(m, "LF1")
        check("probelauf=True: der Probelauf trotz Fliessen, mit Warnung",
              aufrufe == [True] and r3.info.get("probelauf") is True and any("Fließen aus" in z for z in log),
              str(aufrufe))
        check("die Loeserzahlen sagen dann 'nicht gerechnet'",
              "Fließen nicht gerechnet" in adaptiv._loeserzahlen([r3], m))
        aufrufe.clear()
        log.clear()
        adaptiv._rechnen_standard(1, False, log)(m, "LF1")
        check("probelauf=False: voller Lauf ohne Anfrage", aufrufe == [False] and not log, str(aufrufe))
        check("probelauf_elastisch erkennt genau den Fall",
              adaptiv.probelauf_elastisch(m, Erg({"probelauf": True}))
              and not adaptiv.probelauf_elastisch(m, Erg({"probelauf": True, "plastizitaet": {}}))
              and not adaptiv.probelauf_elastisch(m, Erg({})))
    finally:
        solver.solve_static = echt


def main():
    for t in (test_gleichfoermige_spannung_hat_fehler_null, test_integral_ueber_den_tetraeder,
              test_feiner_ist_besser, test_neue_kantenlaengen_und_budget, test_adaptive_runde,
              test_hexaeder_und_keile_im_schaetzer, test_mittelfeld_wird_bevorzugt,
              test_probelauf_nur_mit_fliessen):
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
