"""
Lage der Texte in der Ergebnisansicht und im Berichtsbild (13.10.2026).

Anwender zum Bild vom 13.10.2026: „(3) Textzeilen unten links und Fußzeile
überlagern sich. (4) Legendentitel und Magenta-Hinweis rechts abgeschnitten.“

Geprueft wird an der Platte mit Loch (Zone mit Schraffur, Hinweis,
Legendeneintrag, Werteskala Grenzwert mit „> Skalenmax“), bei
Fenstergroessen 1280 x 800, 1600 x 900, 1920 x 1080 und zwei schmalen
Fenstern, mit den Begrenzungsrechtecken der Texte in Bildpunkten der Ansicht:

* jeder Text liegt ganz in der Ansicht (nichts abgeschnitten),
* kein Text ueberdeckt einen anderen, die Farbskala, das Achsenkreuz, den
  Ansichtswuerfel oder die Glasleiste,
* das Bild fuer den Bericht (Strg+B, ansicht_in_bericht) hat die Groesse der
  Ansicht - es ist dieselbe Zeichnung.

Die Pruefung gehoert auf den Bildschirm: offscreen fehlt die Schrift, die
Breiten sind dort Kaestchenwerte. Sie laeuft dort trotzdem und sagt es.

Aufruf:  python -m tests.test_textlage
"""
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_textlage_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver, spannungen as spn  # noqa: E402

RESULTS = []
#: (Breite, Hoehe, Ueberdeckung pruefen): die drei Groessen des Anwenders und
#: zwei schmale Fenster; im schmalsten (Ansicht rund 170 px breit) passt nicht
#: alles nebeneinander - dort gilt nur: nichts abgeschnitten
GROESSEN = [(1280, 800, True), (1600, 900, True), (1920, 1080, True), (1100, 700, True), (900, 640, False)]
TEXTE = ("kopfzeile", "kennwerte", "farbskala_titel", "spitzen_schraffur_legende", "spitzen_legende")
#: Rechtecke, die als Text zaehlen, ohne ein eigener Darsteller zu sein
TEXTE_SONST = ("spitzen_schraffur_muster", "farbskala_titel_waagerecht", "skalenfeld_notiz")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


def _platte():
    from tests.test_spitzenstellen import lochplatte
    m, _ids, _mitte = lochplatte(vorspannung=1.2e6)
    an = solver.solve_all(m)
    return m, an


def _rechtecke(w) -> dict:
    """{Name: (x0, x1, y0, y1)} in Bildpunkten der Ansicht, y von unten."""
    from statik3d.gui import viewport as vp
    from PySide6 import QtCore
    ren = w.plotter.renderer
    breit, hoch = (float(v) for v in w.plotter.render_window.GetSize())
    aus = {}
    for name in TEXTE:
        akt = w.plotter.actors.get(name)
        if akt is not None and akt.GetVisibility() and (akt.GetInput() or "").strip():
            r = vp.kennwerte_rahmen(ren, akt)
            if r is not None:
                aus[name] = r
    muster = w.plotter.actors.get("spitzen_schraffur_muster")
    if muster is not None:
        b = muster.GetMapper().GetInput().GetBounds()
        aus["spitzen_schraffur_muster"] = (b[0], b[1], b[2], b[3])
    for k, sb in enumerate(w.plotter.scalar_bars.values()):
        p = sb.GetPositionCoordinate().GetComputedDisplayValue(ren)
        p2 = sb.GetPosition2Coordinate().GetComputedDisplayValue(ren)
        aus[f"farbskala{k}"] = (float(p[0]), float(p2[0]), float(p[1]), float(p2[1]))
        if sb.GetOrientation() == 0 and sb.GetTitleTextProperty().GetOpacity() > 0:
            # waagerecht (Kompaktstufe): der Titel der Skala steht mittig ueber ihr
            import vtk
            bb = [0, 0, 0, 0]
            vtk.vtkTextRenderer.GetInstance().GetBoundingBox(sb.GetTitleTextProperty(), sb.GetTitle() or " ",
                                                            bb, int(ren.GetRenderWindow().GetDPI()))
            bw, bh = float(bb[1] - bb[0] + 1), float(bb[3] - bb[2] + 1)
            mx = 0.5 * (float(p[0]) + float(p2[0]))
            aus["farbskala_titel_waagerecht"] = (mx - bw / 2, mx + bw / 2, float(p2[1]) - bh, float(p2[1]))
        if sb.GetOrientation() == 0 and sb.GetDrawAboveRangeSwatch() and sb.GetAboveRangeAnnotation():
            # VTK beschriftet das Feld ueber der Skala unter ihr, am rechten Ende
            import vtk
            bb = [0, 0, 0, 0]
            vtk.vtkTextRenderer.GetInstance().GetBoundingBox(sb.GetAnnotationTextProperty(),
                                                            sb.GetAboveRangeAnnotation(), bb,
                                                            int(ren.GetRenderWindow().GetDPI()))
            nw, nh = float(bb[1] - bb[0] + 1), float(bb[3] - bb[2] + 1)
            aus["skalenfeld_notiz"] = (float(p2[0]) - nw, float(p2[0]), float(p[1]) - nh - 2, float(p[1]))
    # Achsenkreuz unten rechts (eigener Darsteller im Ausschnitt)
    aus["achsenkreuz"] = (0.86 * breit, breit, 0.0, 0.16 * hoch)
    # Ansichtswuerfel und Glasleiste liegen als Qt-Fenster ueber der Ansicht
    s = w._pixelmass()
    ia = w.plotter.interactor
    for name, wid in (("wuerfel", getattr(w, "ansichtswuerfel", None)),
                      ("glasleiste", getattr(w, "glasleiste", None))):
        if wid is not None and wid.isVisible():
            lo = ia.mapFromGlobal(wid.mapToGlobal(QtCore.QPoint(0, 0)))
            aus[name] = (lo.x() * s, (lo.x() + wid.width()) * s,
                         hoch - (lo.y() + wid.height()) * s, hoch - lo.y() * s)
    return aus


def _ueberlappung(a, b, rand=1.0) -> bool:
    return not (a[1] <= b[0] + rand or b[1] <= a[0] + rand or a[3] <= b[2] + rand or b[3] <= a[2] + rand)


def test_lage(fall):
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    m, an = fall
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    if os.environ.get("QT_QPA_PLATFORM", "") == "offscreen" or 0 in tuple(w.plotter.render_window.GetSize()):
        # offscreen hat die Ansicht keine Groesse (0 x 0) und keine Schrift
        print("   offscreen: NICHT GEPRÜFT - die Prüfung gehört auf den Bildschirm "
              "(python -m tests.test_textlage ohne QT_QPA_PLATFORM)")
        w.close()
        return
    w._fragen = lambda *a, **k: True
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "case" and d[1] == "LF1":
            w.cb_result.setCurrentIndex(k)
    w.cb_field.setCurrentIndex(w.cb_field.findText(spn.feldname("volumen", "sv")))
    w.model.werteskala = spn.Werteskala(modus="grenze", grenze=150.0)
    app.processEvents()
    for breit, hoch, deckung in GROESSEN:
        w.showNormal()
        w.resize(breit, hoch)
        for _ in range(5):
            app.processEvents()
        w.redraw()
        app.processEvents()
        w.plotter.render()
        app.processEvents()
        W, H = (int(v) for v in w.plotter.render_window.GetSize())
        r = _rechtecke(w)
        texte = {k: v for k, v in r.items() if k in TEXTE or k in TEXTE_SONST}
        titel = "farbskala_titel" in texte
        draussen = {k: tuple(round(x) for x in v) for k, v in texte.items()
                    if v[0] < -1 or v[1] > W + 1 or v[2] < -1 or v[3] > H + 1}
        check(f"Fenster {breit}x{hoch} (Ansicht {W}x{H}): alle Texte ganz in der Ansicht",
              not draussen and titel and "spitzen_legende" in texte,
              f"außerhalb: {draussen}; Texte {sorted(texte)}")
        paare = []
        namen = list(r)
        for i, a in enumerate(namen):
            for b in namen[i + 1:]:
                if a not in texte and b not in texte:
                    continue
                if {a, b} == {"spitzen_schraffur_legende", "spitzen_schraffur_muster"}:
                    continue
                if {a, b} & {"farbskala_titel_waagerecht", "skalenfeld_notiz"} and any(
                        x.startswith("farbskala") and x != "farbskala_titel_waagerecht" for x in (a, b)):
                    continue                    # Titel und Feld gehoeren zu ihrer Skala
                if _ueberlappung(r[a], r[b]):
                    paare.append((a, b))
        if not deckung:
            print(f"   nur gemeldet (schmalstes Fenster): Überdeckungen {paare}")
            continue
        check(f"… keine Überdeckung von Texten untereinander, mit Farbskala, Achsenkreuz, Würfel, Glasleiste",
              not paare, f"{paare}; " + "; ".join(f"{k} {tuple(round(x) for x in v)}" for k, v in r.items()))
    # Berichtsbild: dieselbe Zeichnung in der Groesse der Ansicht
    n0 = len(w.model.bericht)
    W, H = (int(v) for v in w.plotter.render_window.GetSize())
    w.ansicht_in_bericht(name="Textlage")
    app.processEvents()
    bild = w.model.bericht[-1].bild if len(w.model.bericht) > n0 else ""
    from PySide6 import QtGui
    img = QtGui.QImage.fromData(base64.b64decode(bild)) if bild else QtGui.QImage()
    check("Berichtsbild (Strg+B): dieselbe Zeichnung in der Größe der Ansicht",
          not img.isNull() and (img.width(), img.height()) == (W, H), f"{img.width()}x{img.height()} / {W}x{H}")
    w.close()


def main():
    try:
        fall = _platte()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        RESULTS.append((f"Platte rechnen (Ausnahme: {ex})", False))
        fall = None
    if fall is not None:
        print("\n--- test_lage ---")
        try:
            test_lage(fall)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"test_lage (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
