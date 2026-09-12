"""
Ergebnisse neben der Modelldatei speichern und laden (statik3d/ergebnisse.py).

Aufruf:  python -m tests.test_ergebnisse
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d import solver, examples_lib, ergebnisse as erg  # noqa: E402
from statik3d.model import Model  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")


def _gleich(a, b) -> bool:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.array_equal(np.asarray(a), np.asarray(b), equal_nan=True)
    if isinstance(a, dict):
        return set(a) == set(b) and all(_gleich(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_gleich(x, y) for x, y in zip(a, b))
    return a == b


def test_schreiben_lesen():
    m = examples_lib.build_example("hall")
    an = solver.solve_all(m, design=True)
    ordner = tempfile.mkdtemp()
    pfad = os.path.join(ordner, "halle.json")
    m.save(pfad)
    epfad = erg.pfad_zu(pfad)
    check("Pfad: neben der Modelldatei, Endung .ergebnisse", epfad == os.path.join(ordner, "halle.ergebnisse"))
    t0 = time.time()
    n = erg.schreiben(epfad, m, an)
    t_s = time.time() - t0
    check("geschrieben (Bytes > 0)", os.path.exists(epfad) and n > 1000, f"{erg.groesse_text(n)} in {t_s:.2f} s")
    m2 = Model.load(pfad)
    t0 = time.time()
    an2 = erg.lesen(epfad, m2)
    t_l = time.time() - t0
    check("gelesen: dieselben Lastfaelle und Kombinationen",
          list(an2.cases) == list(an.cases) and list(an2.combinations) == list(an.combinations),
          f"{len(an2.cases)} / {len(an2.combinations)} in {t_l:.2f} s")
    lf = list(an.cases)[0]
    a, b = an.cases[lf], an2.cases[lf]
    check("Verschiebungen, Reaktionen und Stabendkraefte gleich",
          _gleich(a.u, b.u) and _gleich(a.reactions, b.reactions) and _gleich(a.beam_end, b.beam_end)
          and _gleich(a.info, b.info))
    check("das Modell der Ergebnisse ist das geladene Modell (nicht mitgeschrieben)",
          b.model is m2 and all(r.model is m2 for r in an2.combinations.values()))
    env = next(iter(an.envelopes)) if an.envelopes else None
    check("Umhuellende dabei, mit dem geladenen Modell", env is not None and env in an2.envelopes
          and _gleich(an.envelopes[env].u_max, an2.envelopes[env].u_max)
          and an2.envelopes[env].model is m2, str(list(an2.envelopes)))
    check("Nachweise dabei", an2.design is not None and an2.design.table() == an.design.table())
    check("abgeleitete Groessen rechnen wieder (node_vm, beam_forces)",
          np.allclose(b.node_vm, a.node_vm, equal_nan=True) and b.beam_forces.keys() == a.beam_forces.keys())
    # Volumen: solid_res als (Nummern, Matrix) gepackt
    mv = examples_lib.build_example("friction")
    lfv = list(mv.load_cases)[0]
    rv = solver.solve_cases(mv, [lfv])[lfv]
    anv = solver.Analysis(mv, cases={lfv: rv})
    pv = os.path.join(ordner, "block.ergebnisse")
    erg.schreiben(pv, mv, anv)
    anv2 = erg.lesen(pv, mv)
    check("Volumenspannungen je Element und Kontaktzeilen kommen zurueck",
          _gleich(rv.solid_res, anv2.cases[lfv].solid_res) and _gleich(rv.contact, anv2.cases[lfv].contact)
          and _gleich(rv.contact_forces, anv2.cases[lfv].contact_forces)
          and anv2.cases[lfv].kontaktzustand is not None)
    # Kennung: passt nicht mehr, wenn das Modell ein anderes ist
    m3 = Model.load(pfad)
    m3.add_load_case("Neu", "Q")
    try:
        erg.lesen(epfad, m3)
        check("anderes Modell (Lastfaelle): Fehler mit Grund", False)
    except ValueError as ex:
        check("anderes Modell (Lastfaelle): Fehler mit Grund", "Lastfaelle" in str(ex), str(ex)[:70])
    m4 = Model.load(pfad)
    m4.nodes[0, 0] += 0.5
    ok, grund = erg.passt(erg.kennung(m), m4)
    check("verschobener Knoten: Kennung passt nicht", not ok and "oordinaten" in grund, grund)
    ok, grund = erg.passt(erg.kennung(m), Model.load(pfad))
    check("unveraendertes Modell: Kennung passt", ok and grund == "")


def main():
    for t in (test_schreiben_lesen,):
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
