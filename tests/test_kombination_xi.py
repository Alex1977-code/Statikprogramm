"""
Regel 6.10a/b nach DIN EN 1990: der Abminderungsbeiwert ξ gilt nur fuer die
unguenstigen staendigen Einwirkungen (ξ γ_G,sup G_k,sup), nicht fuer die
Vorspannung (γ_P P) und nicht fuer guenstiges G (γ_G,inf G_k,inf).
Bis zum 09.11.2026 nahm der Generator ξ auf jeden staendigen Faktor
(Befund A6 der Pruefagenten): P mit 0,85 statt 1,0, guenstiges G mit 0,85
statt 1,0 - beides auf der unsicheren Seite.

Erwartung mit den Vorgaben γ_G,sup = 1,35, γ_G,inf = 1,0, γ_P = 1,0,
γ_Q = 1,5, ξ = 0,85, Lastfaelle LF1 G, LF2 P, LF3 Q_B:
  * 6.10b, G unguenstig: LF1 1,1475, LF2 1,0, LF3 1,5
  * 6.10b, G guenstig:   LF1 1,0,    LF2 1,0, LF3 1,5
  * 6.10a, G unguenstig: LF1 1,35,   LF2 1,0, LF3 1,5 · 0,7 = 1,05
  * Regel 6.10 bleibt unberuehrt: LF1 1,35, LF2 1,0, LF3 1,5

Aufruf:  python -m tests.test_kombination_xi
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _modell(regel):
    from statik3d.model import Model
    m = Model("xi")
    m.case().category = "G"
    m.add_load_case("LF2", "P", nummer=2)
    m.add_load_case("LF3", "Q_B", nummer=3)
    m.design.combination_rule = regel
    return m


def _uls(m):
    from statik3d.combinations import generate_combinations
    generate_combinations(m)
    return [c for c in m.combinations.values() if c.typ == "ULS"]


def _finde(kombis, text, **faktoren):
    for c in kombis:
        if text in (c.description or "") and all(
                abs(c.factors.get(k, 0.0) - v) < 1e-9 for k, v in faktoren.items()):
            return c
    return None


def _zeige(kombis, text):
    return "; ".join(f"{c.description}: {dict(sorted(c.factors.items()))}" for c in kombis
                     if text in (c.description or ""))


def test_610ab():
    m = _modell("6.10ab")
    k = _uls(m)
    lf1 = m.case().name
    check("6.10b, G ungünstig: LF1 ξ·γ_G,sup = 1,1475, P 1,0, Q 1,5",
          _finde(k, "6.10b", **{lf1: 1.1475, "LF2": 1.0, "LF3": 1.5}) is not None
          and _finde(k, "6.10b", **{"LF2": 0.85}) is None, _zeige(k, "6.10b"))
    check("6.10b, G günstig: LF1 γ_G,inf = 1,0 ohne ξ, P 1,0, Q 1,5",
          _finde(k, "6.10b Leit LF3, G guenstig", **{lf1: 1.0, "LF2": 1.0, "LF3": 1.5}) is not None,
          _zeige(k, "G guenstig"))
    check("6.10a, G ungünstig: LF1 1,35, P 1,0, Q 1,5 · ψ0 0,7 = 1,05",
          _finde(k, "6.10a, G unguenstig", **{lf1: 1.35, "LF2": 1.0, "LF3": 1.05}) is not None,
          _zeige(k, "6.10a"))


def test_610_unberuehrt():
    m = _modell("6.10")
    k = _uls(m)
    lf1 = m.case().name
    check("Regel 6.10: LF1 1,35, P 1,0, Q 1,5 (unverändert)",
          _finde(k, "6.10 Leit LF3, G unguenstig", **{lf1: 1.35, "LF2": 1.0, "LF3": 1.5}) is not None,
          _zeige(k, "6.10 Leit"))


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("kombination_xi")
    ja = _modell("6.10ab")
    _uls(ja)
    nein = _modell("6.10")
    _uls(nein)
    check("Verfahrenstabelle: „kombination_xi“ Fehlerkorrektur Stand 11, nur mit Kombinationen nach 6.10b",
          mk is not None and mk.wechsel[-1].art == rv.FEHLERKORREKTUR and mk.wechsel[-1].stand == 11
          and rv.VERFAHRENSSTAND >= 11 and mk.betrifft(ja) and not mk.betrifft(nein))


def main():
    for t in (test_610ab, test_610_unberuehrt, test_verfahrenstabelle):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
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
