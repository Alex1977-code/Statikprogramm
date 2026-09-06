"""
Netzqualität: Formgüte, Seitenverhältnis, Kantenlänge.

Geprüft wird gegen die Formen, deren Güte man kennt: der regelmäßige
Tetraeder, der Würfel, das Quadrat und das gleichseitige Dreieck bekommen
genau 1; entartete Formen 0; umgestülpte Elemente einen negativen Wert.

Aufruf:  python -m tests.test_netzguete
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import netzguete as ng                       # noqa: E402
from statik3d.model import Model, Material, ShellProp       # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:60s} {detail}")
    return bool(ok)


def close(name, num, ana, tol, einheit=""):
    num, ana = float(num), float(ana)
    abw = abs(num - ana)
    return check(name, abw <= tol, f"{num:.6g}{einheit} / {ana:.6g}{einheit}")


def leer() -> Model:
    m = Model("G")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    m.add_shell(ShellProp("d10", t=0.010)) if hasattr(m, "add_shell") else None
    return m


def knoten(m, punkte) -> list:
    i0 = m.nn
    for p in punkte:
        m.add_node(*p)
    return list(range(i0, i0 + len(punkte)))


# ==========================================================================
# 1  Die idealen Formen bekommen genau 1
# ==========================================================================
def test_ideale_formen():
    m = leer()
    a = 1.0
    reg = knoten(m, [(0, 0, 0), (a, 0, 0), (a / 2, a * np.sqrt(3) / 2, 0),
                     (a / 2, a * np.sqrt(3) / 6, a * np.sqrt(2 / 3))])
    i_tet = m.add_element("tet4", reg, "S355")
    wuerfel = knoten(m, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                         (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)])
    i_hex = m.add_element("hex8", wuerfel, "S355")
    quad = knoten(m, [(0, 0, 5), (1, 0, 5), (1, 1, 5), (0, 1, 5)])
    i_quad = m.add_element("shell4", quad, "S355", sec="d10")
    i_tri = m.add_element("shell3", reg[:3], "S355", sec="d10")
    keil = knoten(m, [(0, 0, 0), (1, 0, 0), (0.5, np.sqrt(3) / 2, 0),
                      (0, 0, 1), (1, 0, 1), (0.5, np.sqrt(3) / 2, 1)])
    i_keil = m.add_element("pent6", keil, "S355")

    pyr = knoten(m, [(0, 0, 20), (1, 0, 20), (1, 1, 20), (0, 1, 20),
                     (0.5, 0.5, 20 + 1 / np.sqrt(2))])
    i_pyr = m.add_element("pyr5", pyr, "S355")

    q = ng.guete(m)
    close("regelmäßiger Tetraeder q = 1", q[i_tet], 1.0, 1e-9)
    close("Pyramide mit gleich langen Kanten q = 1", q[i_pyr], 1.0, 1e-12)
    close("Einheitswürfel q = 1", q[i_hex], 1.0, 1e-12)
    close("Quadrat q = 1", q[i_quad], 1.0, 1e-12)
    close("gleichseitiges Dreieck q = 1", q[i_tri], 1.0, 1e-9)
    close("gerader Keil q = 1", q[i_keil], 1.0, 1e-12)
    check("alle Werte liegen in −1 … 1",
          bool(np.all(np.isfinite(q)) and q.min() >= -1.0 and q.max() <= 1.0),
          f"{q.min():.3f} … {q.max():.3f}")


def test_entartete_formen():
    m = leer()
    eben = knoten(m, [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)])
    i_eben = m.add_element("tet4", eben, "S355")
    flach = knoten(m, [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0.3, 0.3, 1e-4)])
    i_flach = m.add_element("tet4", flach, "S355")
    lang = knoten(m, [(0, 0, 0), (10, 0, 0), (5, 0.2, 0), (5, 0.1, 0.2)])
    i_lang = m.add_element("tet4", lang, "S355")

    q = ng.guete(m)
    close("ebener Tetraeder q = 0", q[i_eben], 0.0, 1e-12)
    check("fast ebener Tetraeder ist unbrauchbar", q[i_flach] < 0.01, f"{q[i_flach]:.5f}")
    check("lang gezogener Tetraeder ist ein Splitter", q[i_lang] < ng.SPLITTER,
          f"{q[i_lang]:.5f}")
    check("die Bewertung nennt die Stufe", ng.bewertung(q[i_eben]) == "unbrauchbar"
          and ng.bewertung(1.0) == "sehr gut" and ng.bewertung(0.5) == "gut",
          f"{ng.bewertung(q[i_eben])}, {ng.bewertung(1.0)}, {ng.bewertung(0.5)}")


def test_umgestuelpt():
    """Ein Hexaeder mit vertauschter Deckfläche hat eine negative
    Jacobi-Determinante - so ein Element rechnet falsch."""
    m = leer()
    kn = knoten(m, [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                    (0, 0, -1), (1, 0, -1), (1, 1, -1), (0, 1, -1)])
    i = m.add_element("hex8", kn, "S355")
    q = ng.guete(m)
    check("umgestülpter Hexaeder bekommt einen negativen Wert", q[i] < 0, f"{q[i]:.3f}")
    d = ng.kennwerte(m)
    check("er wird gezählt", d["umgestuelpt"] == 1, str(d["umgestuelpt"]))
    check("der Bericht nennt ihn",
          any("umgestülpt" in z for z in ng.bericht(m)),
          "; ".join(ng.bericht(m))[:90])


# ==========================================================================
# 2  Seitenverhältnis und Kantenlänge
# ==========================================================================
def test_seitenverhaeltnis_und_laenge():
    m = leer()
    kn = knoten(m, [(0, 0, 0), (4, 0, 0), (4, 1, 0), (0, 1, 0)])
    i = m.add_element("shell4", kn, "S355", sec="d10")
    sv = ng.guete(m, "seitenverhaeltnis")
    kl = ng.guete(m, "kantenlaenge")
    close("Rechteck 4 × 1: Seitenverhältnis 1/4", sv[i], 0.25, 1e-12)
    close("längste Kante 4 m", kl[i], 4.0, 1e-12, " m")

    m2 = leer()
    kn2 = knoten(m2, [(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
    j = m2.add_element("shell4", kn2, "S355", sec="d10")
    close("Quadrat: Seitenverhältnis 1", ng.guete(m2, "seitenverhaeltnis")[j], 1.0, 1e-12)

    try:
        ng.guete(m, "unsinn")
        check("unbekanntes Maß wird abgewiesen", False, "kein Fehler")
    except ValueError as ex:
        check("unbekanntes Maß wird abgewiesen", "unsinn" in str(ex), str(ex)[:60])


def test_ohne_form():
    """Stäbe, Federn und Grenzschichten haben keine Form in diesem Sinn."""
    from statik3d.model import Section
    m = leer()
    m.add_section(Section("Q", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5))
    kn = knoten(m, [(0, 0, 0), (1, 0, 0)])
    i_beam = m.add_element("beam", kn, "S355", "Q")
    m.add_feder_prop("F1", k=[1e8] * 6)
    i_feder = m.add_element("feder", kn, "S355", sec="F1")
    q = ng.guete(m)
    check("Stab bekommt keinen Wert", not np.isfinite(q[i_beam]), str(q[i_beam]))
    check("Feder bekommt keinen Wert", not np.isfinite(q[i_feder]), str(q[i_feder]))
    d = ng.kennwerte(m)
    check("sie zählen als „ohne Form“", d["ohne_form"] == 2 and d["bewertet"] == 0,
          f"{d['ohne_form']} ohne Form, {d['bewertet']} bewertet")
    check("der Bericht sagt es statt zu rechnen",
          "kein Element mit auswertbarer Form" in ng.bericht(m)[0], ng.bericht(m)[0][:70])


# ==========================================================================
# 3  Kennwerte und Bericht
# ==========================================================================
def test_kennwerte_und_bericht():
    m = leer()
    a = 1.0
    for k in range(3):                      # drei regelmäßige Tetraeder
        kn = knoten(m, [(k * 3, 0, 0), (k * 3 + a, 0, 0),
                        (k * 3 + a / 2, a * np.sqrt(3) / 2, 0),
                        (k * 3 + a / 2, a * np.sqrt(3) / 6, a * np.sqrt(2 / 3))])
        m.add_element("tet4", kn, "S355")
    schlecht = knoten(m, [(0, 0, 9), (1, 0, 9), (0, 1, 9), (0.3, 0.3, 9 + 1e-4)])
    i_schlecht = m.add_element("tet4", schlecht, "S355")

    d = ng.kennwerte(m)
    check("alle Elemente bewertet", d["bewertet"] == 4 and d["ohne_form"] == 0)
    close("max = 1 (der regelmäßige Tetraeder)", d["max"], 1.0, 1e-9)
    check("min ist der schlechte", abs(d["min"] - ng.guete(m)[i_schlecht]) < 1e-12)
    check("die Stufen zählen jedes Element genau einmal",
          sum(k for _n, k, _g in d["stufen"]) == d["bewertet"],
          str([(n, k) for n, k, _g in d["stufen"]]))
    check("ein Splitter gezählt", d["splitter"] == 1, str(d["splitter"]))
    check("die schlechtesten stehen zuerst",
          d["schlechteste"][0][0] == i_schlecht, str(d["schlechteste"][:2]))
    check("aufsteigend sortiert",
          all(b >= a_ for (_i, a_), (_j, b) in zip(d["schlechteste"], d["schlechteste"][1:])),
          str([round(v, 3) for _i, v in d["schlechteste"]]))

    z = ng.bericht(m)
    check("der Bericht nennt Anzahl, min, Mittel, max",
          "4 Elemente bewertet" in z[0] and "min" in z[0] and "Mittel" in z[0], z[0][:90])
    check("und die Verteilung", any("sehr gut" in x for x in z), "; ".join(z)[:90])
    check("und die Splitter mit Rat", any("Splitter" in x and "feiner" in x for x in z))
    check("und die schlechtesten mit Nummer und Art",
          any("schlechteste" in x and "tet4" in x for x in z), z[-1][:90])


def test_leeres_modell():
    m = leer()
    check("leeres Modell: keine Werte", len(ng.guete(m)) == 0)
    d = ng.kennwerte(m)
    check("leeres Modell: Kennwerte ohne Absturz",
          d["bewertet"] == 0 and d["schlechteste"] == [], str(d)[:70])
    check("leeres Modell: Bericht sagt es",
          len(ng.bericht(m)) == 1 and "kein Element" in ng.bericht(m)[0],
          ng.bericht(m)[0][:70])


def test_quadratische_elemente():
    """Bei tet10, hex20, shell6 und shell8 zählen die Ecken; die
    Seitenmittenknoten ändern die Form nicht."""
    m = leer()
    a = 1.0
    P = [(0, 0, 0), (a, 0, 0), (a / 2, a * np.sqrt(3) / 2, 0),
         (a / 2, a * np.sqrt(3) / 6, a * np.sqrt(2 / 3))]
    ecken = knoten(m, P)
    mitten = knoten(m, [tuple((np.array(P[i]) + np.array(P[j])) / 2)
                        for i, j in [(0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)]])
    i10 = m.add_element("tet10", ecken + mitten, "S355")
    i4 = m.add_element("tet4", ecken, "S355")
    q = ng.guete(m)
    close("tet10 wird wie tet4 bewertet", q[i10], q[i4], 1e-12)
    close("und trifft die 1", q[i10], 1.0, 1e-9)


def test_schnell_genug():
    """Die Prüfung läuft vor jeder Anzeige; bei einem Volumennetz mit einer
    halben Million Elementen darf das keine Minute dauern."""
    import time
    rng = np.random.default_rng(0)
    m = leer()
    for p in rng.random((2000, 3)):
        m.add_node(*p)
    n = 60000
    for _ in range(n):
        a = int(rng.integers(0, 1996))
        m.add_element("tet4", [a, a + 1, a + 2, a + 3], "S355")
    t0 = time.time()
    q = ng.guete(m)
    dt = time.time() - t0
    check(f"{n} Tetraeder in unter 2 s", dt < 2.0, f"{dt:.2f} s")
    check("jeder bekommt einen Wert", int(np.isfinite(q).sum()) == n, str(int(np.isfinite(q).sum())))


def main():
    print("=" * 92)
    print("STATIK3D - Netzqualität")
    print("=" * 92)
    for t in (test_ideale_formen, test_entartete_formen, test_umgestuelpt,
              test_seitenverhaeltnis_und_laenge, test_ohne_form,
              test_kennwerte_und_bericht, test_leeres_modell,
              test_quadratische_elemente, test_schnell_genug):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(t.__name__, False, str(ex)[:80])
    print("\n" + "=" * 92)
    nok = sum(1 for _n, ok in RESULTS if ok)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN: " + "; ".join(schlecht))
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
