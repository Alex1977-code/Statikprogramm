"""
Das Startbild: die Halle darauf muss statisch sauber sein.

Ein Statikprogramm, das sich mit einem Tragwerk vorstellt, das so nicht steht,
verspielt genau das Vertrauen, um das es geht. Darum wird die Grafik hier
nachgerechnet statt begutachtet:

* Der Querschnitt ist ein **Zweigelenkrahmen**. Das ist keine Geschmacksfrage,
  sondern nachprüfbar: an beiden Stielfüßen muss das Moment **null** sein.
  Beim ersten Anlauf war es das nicht — dort waren die Füße eingespannt
  (M = 25,6 kNm), gezeichnet aber als Gelenk. Genau dieser Widerspruch wird
  hier festgehalten.
* Die **Auflagerkräfte** müssen die Last tragen und die Horizontalschübe sich
  aufheben.
* Die **Farbe der Dachhaut** ist der Momentenverlauf dieses Rahmens, mit dem
  Löser dieses Programms gerechnet. `start.DACH_M` ist der eingebackene Wert —
  eingebacken, weil das Startbild erscheinen soll, *bevor* numpy und scipy
  geladen sind. Dieser Test rechnet ihn neu und vergleicht: driftet der Löser,
  fällt es hier auf, nicht erst dem Betrachter.
* Die Zahl der **Lager** muss zur Zahl der Rahmen passen — drei
  Zweigelenkrahmen haben sechs Gelenke, nicht vier.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform.startswith("win"):
    # Die Plattform offscreen hat auf Windows keine Schriftdatenbank; ohne
    # QT_QPA_FONTDIR faellt "eine echte Schrift ist da" - so wie der Packer
    # (packaging/make_icon.py) es setzt, findet sie Segoe UI.
    os.environ.setdefault("QT_QPA_FONTDIR",
                          os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:60s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    return check(name, abs(got - want) <= tol, f"{got:.6g} statt {want:.6g} {unit}".strip())


QZ = -5.0e3          # N/m Gleichlast auf den Riegeln
N_TEIL = 8           # Elemente je Bauteil - so viele Felder hat die Dachhaut


def _rahmen(spann, traufe, first):
    """Der Querschnitt der Halle als rechenbares Modell."""
    from statik3d.model import BeamLoad, Material, Model, Section
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(Section.from_profile("IPE 300"))
    sec = list(m.sections)[0]

    def kette(A, B, n):
        A, B = np.asarray(A, float), np.asarray(B, float)
        return [m.add_node(*(A + (B - A) * i / n)) for i in range(n + 1)]

    st_l = kette((-spann, 0, 0), (-spann, 0, traufe), N_TEIL)
    ri_l = kette((-spann, 0, traufe), (0, 0, first), N_TEIL)
    ri_r = kette((0, 0, first), (spann, 0, traufe), N_TEIL)
    st_r = kette((spann, 0, traufe), (spann, 0, 0), N_TEIL)
    ri_l[0], ri_r[0], st_r[0] = st_l[-1], ri_l[-1], ri_r[-1]

    riegel = []
    for teil in (st_l, ri_l, ri_r, st_r):
        for a, b in zip(teil, teil[1:]):
            e = m.add_element("beam", [a, b], "S235", sec)
            if teil in (ri_l, ri_r):
                riegel.append(e)
    # Gelenkiger Fuss: ry ist die Biegeachse in der Rahmenebene und bleibt frei
    for k in (st_l[0], st_r[-1]):
        m.support(k, ["ux", "uy", "uz", "rx", "rz"])
    for i in range(m.nn):                       # ebenes Problem
        m.support(i, ["uy", "rx", "rz"])
    for e in riegel:
        m.case().beam_loads.append(BeamLoad(elem=e, q=[0.0, 0.0, QZ], system="global"))
    return m, riegel, st_l[0], st_r[-1]


def test_zweigelenkrahmen():
    """M = 0 an beiden Füßen, Gleichgewicht, Symmetrie."""
    from statik3d import solver
    from statik3d.gui import start
    m, riegel, fl, fr = _rahmen(start.SPANN, start.TRAUFE, start.FIRST)
    r = solver.solve_static(m)
    R = r.reactions
    schraege = 2 * float(np.hypot(start.SPANN, start.FIRST - start.TRAUFE))
    last = -QZ * schraege
    # Das Gelenk: kein Moment am Fusspunkt
    close("Gelenk links: M = 0", float(R[fl][4]), 0.0, 1e-6 * last, "Nm")
    close("Gelenk rechts: M = 0", float(R[fr][4]), 0.0, 1e-6 * last, "Nm")
    # Gleichgewicht
    close("Summe der Auflagerkräfte trägt die Last",
          float(R[fl][2] + R[fr][2]), last, 1e-6 * last, "N")
    close("die Horizontalschübe heben sich auf",
          float(R[fl][0] + R[fr][0]), 0.0, 1e-6 * last, "N")
    check("Horizontalschub ist vorhanden (Rahmen, kein Balken)",
          abs(float(R[fl][0])) > 0.1 * last, f"H = {R[fl][0] / 1e3:.1f} kN")
    close("symmetrisches System, symmetrische Auflagerkräfte",
          float(R[fl][2]), float(R[fr][2]), 1e-6 * last, "N")


def test_dachfarbe_ist_gerechnet():
    """start.DACH_M muss der nachgerechnete Momentenverlauf sein."""
    from statik3d import solver
    from statik3d.gui import start
    m, riegel, _fl, _fr = _rahmen(start.SPANN, start.TRAUFE, start.FIRST)
    r = solver.solve_static(m)
    bf = r.beam_forces
    M = np.array([float(np.max(np.abs(bf[e]["My"]))) for e in riegel])
    norm = M / M.max()
    check("so viele Werte wie Riegelelemente",
          len(start.DACH_M) == len(norm), f"{len(start.DACH_M)} zu {len(norm)}")
    fehler = float(np.max(np.abs(np.asarray(start.DACH_M) - norm)))
    check("die eingebackenen Werte stimmen mit der Rechnung überein",
          fehler < 1e-3, f"groesste Abweichung {fehler:.2e}")
    # Der Verlauf eines Zweigelenkrahmens: groesstes Moment an der Traufe
    # Nach der Division durch den Groesstwert ist nur *ein* Endwert exakt 1,0;
    # der andere liegt um die Rechengenauigkeit daneben. Geprueft wird darum,
    # dass das Maximum an einem Ende liegt und beide Enden gleich gross sind.
    check("das grösste Moment liegt an der Traufe",
          int(np.argmax(norm)) in (0, len(norm) - 1)
          and abs(norm[0] - 1.0) < 1e-9 and abs(norm[-1] - 1.0) < 1e-9,
          f"{norm[0]:.6f} / {norm[-1]:.6f}, Maximum bei {int(np.argmax(norm))}")
    check("dazwischen ein Nulldurchgang (Vorzeichenwechsel im Riegel)",
          norm.min() < 0.35, f"kleinster Wert {norm.min():.3f}")
    check("der Verlauf ist symmetrisch",
          bool(np.allclose(norm, norm[::-1], atol=1e-9)))


def test_lager_und_geometrie():
    """Drei Zweigelenkrahmen haben sechs Gelenke - und sie liegen auf dem Boden."""
    from statik3d.gui import start
    ys = [0.0, start.FELD, 2 * start.FELD]
    fuesse = [P for y in ys for P in (start._rahmenpunkte(y)[0],
                                      start._rahmenpunkte(y)[4])]
    check("sechs Lager (drei Rahmen mal zwei Gelenke)", len(fuesse) == 6, str(len(fuesse)))
    check("alle Lager liegen auf dem Boden z = 0",
          all(abs(P[2]) < 1e-12 for P in fuesse))
    ecken = start._rahmenpunkte(0.0)
    check("der First liegt über der Traufe", ecken[2][2] > ecken[1][2],
          f"{ecken[2][2]} > {ecken[1][2]}")
    check("der Rahmen ist symmetrisch", abs(ecken[0][0] + ecken[4][0]) < 1e-12)


def test_bild_entsteht():
    """Das Startbild wird gezeichnet und hat die Größe, die die Spec erwartet."""
    from PySide6 import QtWidgets
    from statik3d.gui import start
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    check("eine echte Schrift ist da", start.schrift_vorhanden())
    pm = start.startbild("9.9.9", "abc1234")
    check("Größe wie in Statik3D.spec", pm.width() == start.BREITE and pm.height() == start.HOEHE,
          f"{pm.width()}x{pm.height()}")
    bild = pm.toImage()
    # Die Dachhaut faerbt das Bild: es darf nicht einfarbig sein
    farben = {bild.pixel(x, y) for x in range(0, start.BREITE, 7)
              for y in range(0, start.HOEHE, 7)}
    check("das Bild ist nicht einfarbig", len(farben) > 200, f"{len(farben)} Farben")
    check("die Meldungszeile bleibt frei für den Packer",
          start.MELDUNG_Y < start.HOEHE and start.MELDUNG_Y > start.HOEHE - 60,
          str(start.MELDUNG_Y))


def main():
    for f in (test_zweigelenkrahmen, test_dachfarbe_ist_gerechnet,
              test_lager_und_geometrie, test_bild_entsteht):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
