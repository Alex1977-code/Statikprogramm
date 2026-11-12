"""
Lastfaelle mit den Einwirkungen der DIN 19704 im Generator nach DIN EN 1990
(Befund A5 der Pruefagenten, Entscheidung des Anwenders vom 09.11.2026).

Bis zum 09.11.2026 kannte der Generator nur die Kategorien der DIN EN 1990:
ein Lastfall „Eigengewicht Ausruestung“ (G_A), „Wasserdruck staendig“ (W_S),
„Wasserdruck veraenderlich“ (W_V), Eis, Schwall, Wind bei Bewegung,
Antriebsmoment, Anprall, Verklemmen, Montage oder Erdbeben stand in **keiner**
erzeugten Kombination und fehlte still in der Bemessung.

Jetzt:
  * G_A und W_S sind staendige Einwirkungen (γ_G,sup 1,35 / γ_G,inf 1,0),
  * W_V, EIS, SCHWALL, WIND_B, A_M, A_MG sind veraenderlich (γ_Q 1,5, ψ aus
    der Tabelle der Einwirkungen),
  * ANPRALL und KLEMM sind aussergewoehnlich (6.11b, Faktor 1,0),
  * ERD und MONT lehnt der Generator ab und nennt den Generator „DIN 19704“.

Zweiter Weg der Zahlen: Einfeldtraeger L = 6 m, max M = q L² / 8 von Hand,
mit q aus den Beiwerten der DIN EN 1990 (Tabelle im Kopf jeder Pruefung).

Aufruf:  python -m tests.test_din19704_kategorien
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

RESULTS = []
L = 6.0          # m
G_K = 10.0       # kN/m, LF1 Eigengewicht
Q_K = 5.0        # kN/m, LF2 die gepruefte Einwirkung


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:86s} {detail}")
    return ok


def _faelle(kat, dritter=None, faktorisiert=False):
    """Nur Lastfaelle: LF1 G, LF2 mit der Kategorie *kat*, wahlweise LF3."""
    from statik3d.model import Model
    m = Model("din19704")
    m.case().category = "G"
    lc = m.add_load_case("LF2", kat, nummer=2)
    if faktorisiert:
        m.load_cases["LF2"].faktorisiert = True
    if dritter:
        m.add_load_case("LF3", dritter, nummer=3)
    return m


def _traeger(kat):
    """Einfeldtraeger 6 m, LF1 G mit 10 kN/m, LF2 *kat* mit 5 kN/m."""
    from statik3d import mesher
    from statik3d.model import Model, Material, Section
    m = Model("din19704")
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 300"))
    ids = mesher.line_of_beams(m, "S235", "IPE 300", (0, 0, 0), (L, 0, 0), 6)
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.case().category = "G"
    for e in range(6):
        m.load_beam(e, qz=-G_K * 1e3)
    m.add_load_case("LF2", kat, nummer=2)
    for e in range(6):
        m.load_beam(e, qz=-Q_K * 1e3)
    m.add_member("T", list(range(6)))
    return m


def _erzeugen(m, **kw):
    from statik3d.combinations import generate_combinations
    return generate_combinations(m, **kw)


def _finde(kombis, typ, text, **faktoren):
    for c in kombis:
        if c.typ == typ and text in (c.description or "") and all(
                abs(c.factors.get(k, 0.0) - v) < 1e-9 for k, v in faktoren.items()):
            return c
    return None


def _zeige(kombis, typ):
    return "; ".join(f"{c.description}: {dict(sorted(c.factors.items()))}" for c in kombis
                     if c.typ == typ)


def _max_my(m, typ):
    """max |My| der Umhuellenden *typ* in kNm."""
    import numpy as np
    from statik3d import solver
    an = solver.solve_all(m, workers=1)
    env = an.envelopes.get(typ)
    if env is None:
        return 0.0
    return max(max(np.abs(env.beam[e]["My"][i]).max() for i in (0, 1)) for e in env.beam) / 1e3


# --------------------------------------------------------------------------
def test_staendig():
    """G_A und W_S: γ_G,sup = 1,35 wie das Eigengewicht, günstig 1,0."""
    for kat in ("G_A", "W_S"):
        m = _faelle(kat, dritter="Q_B")
        k = _erzeugen(m)
        lf1 = m.case().name if m.case().category == "G" else "LF1"
        lf1 = next(n for n, lc in m.load_cases.items() if lc.category == "G")
        check(f"{kat}: ständig – 6.10 Leit LF3 mit {lf1} 1,35, LF2 1,35, LF3 1,5",
              _finde(k, "ULS", "6.10 Leit LF3, G unguenstig",
                     **{lf1: 1.35, "LF2": 1.35, "LF3": 1.5}) is not None, _zeige(k, "ULS")[:160])
        check(f"{kat}: G günstig – LF2 mit γ_G,inf = 1,0",
              _finde(k, "ULS", "6.10 Leit LF3, G guenstig",
                     **{lf1: 1.0, "LF2": 1.0, "LF3": 1.5}) is not None)
        check(f"{kat}: GZG quasi-ständig mit LF2 1,0 und LF3 ψ2 = 0,3",
              _finde(k, "SLS_QP", "", **{lf1: 1.0, "LF2": 1.0, "LF3": 0.3}) is not None,
              _zeige(k, "SLS_QP")[:160])


def test_veraenderlich():
    """Veränderliche Einwirkungen: Leiteinwirkung γ_Q = 1,5; als Begleiteinwirkung
    neben einer Nutzlast Kat. B γ_Q · ψ0 mit ψ0 aus der Tabelle der Einwirkungen."""
    psi0 = {"W_V": 0.8, "EIS": 0.6, "SCHWALL": 0.6, "WIND_B": 0.6, "A_M": 1.0, "A_MG": 1.0}
    from statik3d.model import ACTION_CATEGORIES
    for kat, p0 in psi0.items():
        check(f"{kat}: ψ0 der Tabelle ist {p0:.1f}".replace(".", ","),
              abs(ACTION_CATEGORIES[kat][1][0] - p0) < 1e-12)
        m = _faelle(kat, dritter="Q_B")
        k = _erzeugen(m)
        lf1 = next(n for n, lc in m.load_cases.items() if lc.category == "G")
        check(f"{kat}: veränderlich – Leit LF2 mit 1,5 und LF3 1,5 · 0,7 = 1,05",
              _finde(k, "ULS", "6.10 Leit LF2, G unguenstig",
                     **{lf1: 1.35, "LF2": 1.5, "LF3": 1.05}) is not None, _zeige(k, "ULS")[:160])
        check(f"{kat}: Begleiteinwirkung – Leit LF3 mit LF2 1,5 · ψ0 = {1.5 * p0:.2f}".replace(".", ","),
              _finde(k, "ULS", "6.10 Leit LF3, G unguenstig",
                     **{lf1: 1.35, "LF2": 1.5 * p0, "LF3": 1.5}) is not None)


def test_aussergewoehnlich():
    """ANPRALL und KLEMM: 6.11b, G 1,0 + A 1,0 + ψ1 · Q (Leit) – und in keiner
    Kombination der ständigen und vorübergehenden Bemessungssituation."""
    for kat in ("ANPRALL", "KLEMM"):
        m = _faelle(kat, dritter="Q_B")
        k = _erzeugen(m)
        lf1 = next(n for n, lc in m.load_cases.items() if lc.category == "G")
        check(f"{kat}: außergewöhnlich – 6.11b mit {lf1} 1,0, LF2 1,0, LF3 ψ1 = 0,5",
              _finde(k, "ACC", "6.11b LF2, Leit LF3",
                     **{lf1: 1.0, "LF2": 1.0, "LF3": 0.5}) is not None, _zeige(k, "ACC")[:160])
        check(f"{kat}: steht in keiner GZT- und keiner GZG-Kombination",
              not any("LF2" in c.factors for c in k if c.typ != "ACC"))


def test_bemessung():
    """Am Einfeldträger: die Umhüllende enthält die Einwirkung. Handrechnung q L² / 8."""
    soll = {
        # ständig: 1,35 · (10 + 5) · 36 / 8
        "G_A": ("ULS", 1.35 * (G_K + Q_K) * L ** 2 / 8),
        "W_S": ("ULS", 1.35 * (G_K + Q_K) * L ** 2 / 8),
        # veränderlich: (1,35 · 10 + 1,5 · 5) · 36 / 8
        "W_V": ("ULS", (1.35 * G_K + 1.5 * Q_K) * L ** 2 / 8),
        "EIS": ("ULS", (1.35 * G_K + 1.5 * Q_K) * L ** 2 / 8),
        # außergewöhnlich: (1,0 · 10 + 1,0 · 5) · 36 / 8 = 67,5 – die Kombinationen 6.11b
        # gehen in die Umhüllende GZT ein (solver.umhuellende_art); ohne den
        # Lastfall bliebe dort 1,35 · 10 · 36 / 8 = 60,75
        "ANPRALL": ("ULS", (G_K + Q_K) * L ** 2 / 8),
    }
    for kat, (typ, hand) in soll.items():
        m = _traeger(kat)
        _erzeugen(m)
        ist = _max_my(m, typ)
        check(f"{kat}: max |My| der Umhüllenden {typ} = {hand:.2f} kNm (Handrechnung q L²/8)"
              .replace(".", ","), abs(ist - hand) < 0.005 * hand, f"gerechnet {ist:.2f} kNm".replace(".", ","))


def test_abgelehnt():
    """ERD und MONT: der Generator erzeugt nichts, nennt Lastfall und den Weg
    (Generator „DIN 19704“), und lässt vorhandene Kombinationen stehen."""
    from statik3d.model import Combination, KombinationGesperrt
    for kat in ("ERD", "MONT"):
        m = _faelle(kat, dritter="Q_B")
        lf1 = next(n for n, lc in m.load_cases.items() if lc.category == "G")
        m.combinations["LK1"] = Combination("LK1", {lf1: 1.0}, "ULS")
        text, gesperrt = "", False
        try:
            _erzeugen(m)
        except KombinationGesperrt as ex:
            text, gesperrt = str(ex), list(getattr(ex, "lastfaelle", []) or []) == ["LF2"]
        check(f"{kat}: der Generator nach EN 1990 lehnt ab und nennt LF2 und „DIN 19704“",
              gesperrt and "LF2" in text and "DIN 19704" in text, text[:150].replace("\n", " "))
        check(f"{kat}: nichts erzeugt, die vorhandene Kombination steht noch",
              list(m.combinations) == ["LK1"], str(list(m.combinations)))
        # als Bemessungslastfall (bereits faktorisiert) steht er für sich mit 1,0
        m2 = _faelle(kat, dritter="Q_B", faktorisiert=True)
        k2 = _erzeugen(m2)
        check(f"{kat}: als Bemessungslastfall erlaubt – eigene Kombination mit 1,0",
              _finde(k2, "ULS", "Bemessungslastfall LF2", LF2=1.0) is not None
              and sum(1 for c in k2 if "LF2" in c.factors) == 1)


def test_unberuehrt():
    """Kategorien der DIN EN 1990 bleiben, wie sie waren; FAT steht weiter in keiner
    Kombination, „nicht zugeordnet“ bleibt gesperrt."""
    m = _faelle("W", dritter="Q_B")
    k = _erzeugen(m)
    lf1 = next(n for n, lc in m.load_cases.items() if lc.category == "G")
    check("Wind und Nutzlast Kat. B: Leit LF3 mit LF2 1,5 · 0,6 = 0,9 (unverändert)",
          _finde(k, "ULS", "6.10 Leit LF3, G unguenstig",
                 **{lf1: 1.35, "LF2": 0.9, "LF3": 1.5}) is not None)
    m = _faelle("FAT", dritter="Q_B")
    k = _erzeugen(m)
    check("Ermüdungslastfall (FAT) steht in keiner erzeugten Kombination",
          not any("LF2" in c.factors for c in k))
    from statik3d.model import LoadCase
    klassen = {kat: (LoadCase("x", kat).is_permanent, LoadCase("x", kat).is_variable,
                     LoadCase("x", kat).is_accidental)
               for kat in ("G", "P", "SET", "Q_BEW", "H", "A", "G_A", "W_S", "W_V", "EIS", "SCHWALL",
                           "WIND_B", "A_M", "A_MG", "ANPRALL", "KLEMM", "ERD", "MONT", "FAT", "NZ")}
    check("jede Kategorie in höchstens einer Klasse",
          all(sum(v) <= 1 for v in klassen.values()), str({k: v for k, v in klassen.items() if sum(v) > 1}))
    check("ohne Klasse sind genau ERD, MONT, FAT und „nicht zugeordnet“",
          sorted(k for k, v in klassen.items() if sum(v) == 0) == ["ERD", "FAT", "MONT", "NZ"],
          str(sorted(k for k, v in klassen.items() if sum(v) == 0)))


def test_verfahrenstabelle():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("kategorien_din19704")
    if not check("Verfahrenstabelle: Merkmal „kategorien_din19704“ vorhanden", mk is not None):
        return
    w = mk.wechsel[-1]
    check("Verfahrenstabelle: Fehlerkorrektur, Stand 21",
          w.art == rv.FEHLERKORREKTUR and w.stand == 21 and rv.VERFAHRENSSTAND >= 21,
          f"art {w.art}, Stand {w.stand}, Verfahrensstand {rv.VERFAHRENSSTAND}")
    # Modell wie vor der Korrektur: G_A-Lastfall, Kombinationen des Generators ohne ihn
    alt = _faelle("G", dritter="Q_B")
    _erzeugen(alt)
    alt.load_cases["LF2"].category = "G_A"
    for c in alt.combinations.values():
        c.factors.pop("LF2", None)
        c.als_erzeugt("EN 1990")
    neu = _faelle("G_A", dritter="Q_B")
    _erzeugen(neu)
    ohne = _faelle("W", dritter="Q_B")
    _erzeugen(ohne)
    hand = _faelle("G_A", dritter="Q_B")
    check("betrifft: G_A-Lastfall fehlt in den erzeugten Kombinationen – ja",
          mk.betrifft(alt))
    check("betrifft: neu erzeugte Kombinationen enthalten ihn – nein", not mk.betrifft(neu))
    check("betrifft: Modell ohne Einwirkungen der DIN 19704 – nein", not mk.betrifft(ohne))
    check("betrifft: Modell ohne erzeugte Kombinationen – nein", not mk.betrifft(hand))


def main():
    for t in (test_staendig, test_veraenderlich, test_aussergewoehnlich, test_bemessung,
              test_abgelehnt, test_unberuehrt, test_verfahrenstabelle):
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
