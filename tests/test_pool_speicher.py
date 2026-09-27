# -*- coding: utf-8 -*-
"""Der Arbeiterpool bemisst sich nach dem freien Speicher (27.09.2026).

Am Drehlager erschoepften 31 Arbeiter (je 2,9 GB Commit) plus der
Hauptprozess (24 GB) das Commit-Limit von 166 GB: PARDISO -2, davor ein
Absturz in der Faktorisierung. Seither: hoechstens so viele Arbeiter, wie in
den halben freien Commit-Speicher passen, wenn jeder so viel braucht wie der
Hauptprozess beim Start des Pools (parallel.arbeiter_nach_speicher).
"""
import sys

from statik3d import parallel

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:70s} {detail}")


def test_bemessung():
    GB = 2 ** 30
    n = parallel.arbeiter_nach_speicher(31, frei=126 * GB, eigen=5 * GB)
    check("Drehlager: 126 GB frei, Hauptprozess 5 GB -> 12 statt 31 Arbeiter", n == 12, str(n))
    check("kleines Modell: Hauptprozess 0,3 GB -> die Vorgabe bleibt",
          parallel.arbeiter_nach_speicher(31, frei=126 * GB, eigen=int(0.3 * GB)) == 31)
    check("knapp: 4 GB frei, Hauptprozess 3 GB -> ein Arbeiter (nie null)",
          parallel.arbeiter_nach_speicher(31, frei=4 * GB, eigen=3 * GB) == 1)
    check("ohne Auskunft (0) bleibt die Vorgabe",
          parallel.arbeiter_nach_speicher(31, frei=0, eigen=5 * GB) == 31
          and parallel.arbeiter_nach_speicher(31, frei=126 * GB, eigen=0) == 31)
    check("ein Arbeiter bleibt einer", parallel.arbeiter_nach_speicher(1, frei=1, eigen=10 ** 12) == 1)


def test_auskunft():
    frei, commit = parallel.speicher_frei()
    eigen = parallel.speicher_eigen()
    check("das System gibt freien Speicher und Commit an (Byte, > 0)",
          frei > 0 and commit > 0, f"frei {frei / 2 ** 30:.1f} GB, Commit {commit / 2 ** 30:.1f} GB")
    check("der eigene Commit-Speicher ist bekannt (> 10 MB)", eigen > 10 * 2 ** 20,
          f"{eigen / 2 ** 20:.0f} MB")


def test_pool_wird_begrenzt():
    """Ein Pool mit Vorgabe 31 und (gestellt) 3 GB freiem Commit bei 2 GB
    eigenem Speicher: ein Arbeiter - und dann startet kein Prozesspool."""
    from statik3d.model import Model, Material
    from statik3d import mesher
    m = Model()
    m.add_material(Material("S"))
    mesher.grid_box(m, "S", 1.0, 1.0, 1.0, 12, 12, 12, typ="tet4")   # > min_elements
    alt_frei, alt_eigen = parallel.speicher_frei, parallel.speicher_eigen
    parallel.speicher_frei = lambda: (3 * 2 ** 30, 3 * 2 ** 30)
    parallel.speicher_eigen = lambda: 2 * 2 ** 30
    try:
        with parallel.arbeiter(m, workers=31) as a:
            check("Pool auf einen Arbeiter begrenzt, kein Prozesspool gestartet",
                  a.w == 1 and a.pool is None and a.begrenzung == (31, 1),
                  f"w {a.w}, Pool {a.pool}, {a.begrenzung}")
    finally:
        parallel.speicher_frei, parallel.speicher_eigen = alt_frei, alt_eigen


def main():
    for t in (test_bemessung, test_auskunft, test_pool_wird_begrenzt):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
