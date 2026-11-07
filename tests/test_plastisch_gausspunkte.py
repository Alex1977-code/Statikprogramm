"""
Plastische Ergebnisse zeigen Integrationspunktwerte, nie Eckwerte (06.11.2026).

Festlegung des Anwenders: auch ein Element, das nicht fliesst, zeigt in einer plastischen
Rechnung seine Gausspunkte. Die Faerbung tat das seit dem 13.10.2026
(spannungen.anzeige_knotenwerte), der Elementwert ``res.solid_res`` und die Knotentabelle
``res.solid_knoten`` nicht: am Drehlager (Mittel) trugen sie an 124 tet10 mit fast entarteter
Ecke (det J das 0,006-Fache) bis 14 379 N/mm², wo die Gausspunkte desselben Elements hoechstens
344 N/mm² haben. Lineare Rechnungen bleiben, wie sie sind.

Pruefkoerper: Kragarm aus tet10, an einem inneren Element eine Seitenmitte auf das Viertel der
Kante gerueckt (dieselbe Ecke, dieselbe Spitze).

Aufruf:  python -m tests.test_plastisch_gausspunkte
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402

from statik3d import plastizitaet as pl, solver, spannungen as spn  # noqa: E402
from statik3d.elements import solid as sl  # noqa: E402
from statik3d.model import Material, Model  # noqa: E402
with contextlib.redirect_stdout(io.StringIO()):
    from tests import test_fugen as tf  # noqa: E402

RESULTS = []
GP = sl._TET_GP


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return bool(ok)


def _sv(S):
    return spn.volumen_werte(np.asarray(S, float).reshape(-1, 6), "sv") / 1e6


def _kragarm(F, plastisch):
    m = Model()
    m.add_material(Material.steel("S235"))
    m.netz.ziellaenge = 0.1
    m.netz.ordnung = 2
    tf._kasten(m, 0.0, 1.0, 0.0, 0.2, 0.0, 0.2, "K", h=0.1)
    X = np.asarray(m.nodes, float)
    # ein Element fern von Lager und Last, die Seitenmitte der Kante (0, 1) zur Ecke 0
    mitte = np.array([X[e.nodes[:4]].mean(axis=0) for e in m.elements])
    e0 = int(np.argmin(np.linalg.norm(mitte - [0.5, 0.1, 0.17], axis=1)))
    el = m.elements[e0]
    a, b, kn = int(el.nodes[0]), int(el.nodes[1]), int(el.nodes[4])
    m.nodes[kn] = X[a] + 0.2515 * (X[b] - X[a])
    fest = [k for k in range(m.nn) if abs(X[k, 0]) < 1e-9]
    last = [k for k in range(m.nn) if abs(X[k, 0] - 1.0) < 1e-9]
    for k in fest:
        m.fix(k, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for k in last:
        m.load_node(k, Fz=F / len(last), case="LF1")
    if plastisch:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=2, iterationen=40, toleranz=1e-4)
    an = solver.solve_all(m, design=False)
    return m, an.cases["LF1"], e0


def _punkte(m, r, e, punkte):
    el = m.elements[e]
    X = np.asarray(m.nodes, float)[el.nodes]
    ue = np.asarray(r.u, float)[np.asarray(el.nodes)][:, :3].ravel()
    mat = m.materials[el.mat]
    return np.array([sl.stress_tet10(X, mat.E, mat.nu, ue, *p) for p in punkte])


def _knotentabelle_max(r, m, e):
    sk = r.solid_knoten
    k = {int(x) for x in m.elements[e].nodes[:4]}
    w = [i for i, n in enumerate(np.asarray(sk["knoten"]).tolist()) if int(n) in k]
    return float(_sv(np.asarray(sk["spannung"], float)[w]).max())


def test_nicht_fliessend():
    F = 2e5
    m, r, e = _kragarm(F, True)
    ecke = _sv(_punkte(m, r, e, sl.AUSWERTEPUNKTE["tet10"])).max()
    gp = _sv(_punkte(m, r, e, GP)).max()
    check("Prüfkörper: die Ecke steht weit über den Gaußpunkten, das Element fließt nicht",
          ecke > 5 * gp and e not in (r.info.get("plastisch") or {}), f"Ecke {ecke:.0f}, Gaußpunkte {gp:.1f} N/mm²")
    sv = float(_sv(r.solid_res[e])[0])
    check("Plastisch: der Elementwert ist der größte Gaußpunkt", abs(sv - gp) < 1e-6 * gp, f"{sv:.3f} gegen {gp:.3f} N/mm²")
    k = _knotentabelle_max(r, m, e)
    check("Plastisch: die Spitze schlägt nicht auf die Knotentabelle durch", k < 2 * gp, f"{k:.1f} N/mm²")
    alle = _sv(np.array(list(r.solid_res.values()), float))
    # was die Anzeige zeigt, stimmt mit dem Elementwert zusammen: nirgends mehr als der Punkt
    kw = spn.anzeige_knotenwerte(m, r, "sv")
    check("… und die Färbung bleibt bei den Punkten", kw is not None and float(np.max(kw[1])) / 1e6 <= float(alle.max()) * (1 + 1e-9),
          f"Färbung {float(np.max(kw[1])) / 1e6:.1f}, Elementwert {alle.max():.1f} N/mm²")
    sv0 = solver.PLASTISCH_NUR_PUNKTE
    solver.PLASTISCH_NUR_PUNKTE = False
    try:
        m2, r2, e2 = _kragarm(F, True)
        d = float(_sv(r2.solid_res[e2])[0])
        k2 = _knotentabelle_max(r2, m2, e2)
    finally:
        solver.PLASTISCH_NUR_PUNKTE = sv0
    check("Rücknahme: ohne die Änderung steht die Ecke im Elementwert und in der Knotentabelle",
          d > 3 * gp and k2 > 1.5 * k, f"Elementwert {d:.0f}, Knotentabelle {k2:.0f} N/mm²")


def test_fliessend_unveraendert():
    m, r, e = _kragarm(4e6, True)
    pl_el = r.info.get("plastisch") or {}
    check("Mit Fließen: Elemente fließen", len(pl_el) > 0, f"{len(pl_el)} Elemente")
    punkte = r.info.get("ip_spannungen") or {}
    gut = True
    for (_typ, _P), (ids, S) in punkte.items():
        for a, i in enumerate(ids.tolist()):
            if abs(float(_sv(r.solid_res[i])[0]) - float(_sv(S[a]).max())) > 1e-6 * max(float(_sv(S[a]).max()), 1.0):
                gut = False
    check("… fließende Elemente: Elementwert wie bisher der größte abgelegte Punkt", gut)
    ohne = [i for i in r.solid_res if i not in pl_el]
    w = np.array([_sv(_punkte(m, r, i, GP)).max() - float(_sv(r.solid_res[i])[0]) for i in ohne])
    check("… nicht fließende daneben: der größte Gaußpunkt", np.abs(w).max() < 1e-3, f"{len(ohne)} Elemente, bis {np.abs(w).max():.1e} N/mm²")


def test_linear_unveraendert():
    m, r, e = _kragarm(2e5, False)
    w = _punkte(m, r, e, sl.AUSWERTEPUNKTE["tet10"])
    sv = float(_sv(r.solid_res[e])[0])
    check("Linear: der Elementwert bleibt der größte Auswertepunkt (Ecke)", abs(sv - _sv(w).max()) < 1e-6 * sv,
          f"{sv:.0f} N/mm²")


def main():
    for t in (test_nicht_fliessend, test_fliessend_unveraendert, test_linear_unveraendert):
        print(f"\n--- {t.__name__}")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
