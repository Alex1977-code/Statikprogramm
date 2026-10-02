"""
Tabelleninhalte im unteren Bereich (Teilpaket 10a der Oberflaechenplanung,
02.10.2026).

* Lastfaelle und Kombinationen stehen in der Reihenfolge des Modells, nicht
  nach Name sortiert; ein Klick auf den Spaltenkopf sortiert, der dritte Klick
  bringt die Modellreihenfolge zurueck;
* kein „-0,00“: ein auf null gerundeter Wert hat kein Vorzeichen (Zellen,
  min / max-Paare, Lasttabelle, Export);
* Zahlentexte in Tabellen mit Komma - auch die Lasttabelle (bisher Punkt);
* die Art steht im Klartext („Balken 3D“ statt „beam“), gesucht, sortiert und
  exportiert wird, was dasteht;
* der Kontakt-Hinweis erscheint nur bei Modellen mit Kontakt;
* ein Klick auf einen Lastfall stellt die Lasttabelle auf seine Lasten;
* editierbare Zellen weiss, die uebrigen grau (nur Eingabetabellen).

Aufruf:  python -m tests.test_tabelleninhalte
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_tabelleninhalte_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: (w.fehler_liste.append(str(msg)),
                                     w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell(kontakt=False):
    """Kragarm mit drei Lastfaellen und zwei Kombinationen, bewusst NICHT in der
    Reihenfolge des Alphabets angelegt (Zebra, Adler, Mitte / KB, KA). Das
    Modell bringt „LF1“ schon mit, der Lastfall steht also vorn."""
    from statik3d.model import Model, Material, Section
    m = Model("Probe")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n0 = m.add_node(0.0, 0.0, 0.0)
    n1 = m.add_node(3.0, 0.0, 0.0)
    m.add_element("beam", [n0, n1], "S355", "HEB 300")
    m.support(n0, "all", name="Einspannung")
    for name, kat in (("Zebra", "G"), ("Adler", "Q"), ("Mitte", "W")):
        m.add_load_case(name, kat, activate=False)
    # ein auf null gerundeter negativer Wert: -0,0004 kN/m und -0,4 N Querkraft
    m.load_beam(0, qz=-0.4, case="Zebra")
    m.load_node(n1, Fz=-5e3, case="Zebra")
    m.load_node(n1, Fy=1e-3, Fz=-1e-3, case="Adler")
    m.load_node(n1, Fy=2e3, case="Mitte")
    m.set_gravity(-9.81, case="Zebra")
    m.add_combination("KB", {"Zebra": 1.35, "Adler": 1.5})
    m.add_combination("KA", {"Zebra": 1.35, "Mitte": 1.5})
    if kontakt:
        m.add_contact_support(n1, (0, 0, 1), gap=0.0)
    return m


def _namen(tbl):
    return [str(z[0]) for z in tbl.modell.zeilen]


# --------------------------------------------------------------------------
def test_festkomma():
    from statik3d.gui.tabellen import festkomma
    check("festkomma: -0,0004 mit zwei Stellen ist „0,00“, ohne Vorzeichen",
          festkomma(-0.0004, 2) == "0,00", festkomma(-0.0004, 2))
    check("… -0.0 und -1e-12 ebenso", festkomma(-0.0, 3) == "0,000" and festkomma(-1e-12, 1) == "0,0",
          f"{festkomma(-0.0, 3)} {festkomma(-1e-12, 1)}")
    check("… -0,006 bleibt „-0,01“ (es ist nicht null)", festkomma(-0.006, 2) == "-0,01",
          festkomma(-0.006, 2))
    check("… 1234,5 mit Komma, ohne Tausenderzeichen", festkomma(1234.5, 2) == "1234,50")
    check("… eine Zahl ohne Nachkommastellen: -0,3 wird „0“", festkomma(-0.3, 0) == "0",
          festkomma(-0.3, 0))
    check("… was keine Zahl ist, steht als „–“ da", festkomma(float("nan"), 2) == "–"
          and festkomma(float("inf"), 2) == "–", festkomma(float("nan"), 2))


def test_tabelle_pur():
    """Datentabelle ohne Hauptfenster: Zellen, Paar, Klartext, Farben, Reihenfolge."""
    from PySide6 import QtCore, QtGui
    from statik3d.gui import tabellen as tab
    from statik3d.gui.tabellen import Datentabelle, Spalte
    _app()
    DR, BG = QtCore.Qt.DisplayRole, QtCore.Qt.BackgroundRole

    t = Datentabelle([Spalte("Nr", "", "ganz"), Spalte("N", "kN", "zahl", 2),
                      Spalte("R", "kN", "zahl", 2),
                      Spalte("Art", klartext={"beam": "Balken 3D", "shell4": "Schale, Viereck"})],
                     "Probe")
    t.setzen([[1, -0.0004, "-0.00 / 1.23", "beam"], [2, -0.006, "0.50 / -0.001", "shell4"],
              [3, 12.5, "-2.5 / 0.001", "tet99"]])
    m = t.modell
    cell = lambda r, k: m.data(m.index(r, k), DR)
    check("Zelle: -0,0004 mit zwei Stellen steht als „0,00“", cell(0, 1) == "0,00", cell(0, 1))
    check("… -0,006 als „-0,01“", cell(1, 1) == "-0,01", cell(1, 1))
    check("min / max-Paar mit Punkt im Rechenteil: Komma, kein „-0,00“",
          cell(0, 2) == "0,00 / 1,23" and cell(1, 2) == "0,50 / 0,00", f"{cell(0, 2)} | {cell(1, 2)}")
    check("… -2,5 bleibt, 0,001 wird „0,00“", cell(2, 2) == "-2,50 / 0,00", cell(2, 2))
    text = t.text()
    from statik3d.gui.tabellen import als_csv
    csv_ = als_csv(["x"], [[1e-5], [-4e-9], [2.5], [1e20]]).splitlines()[1:]
    check("CSV: nie wissenschaftlich („1e-05“ wird „0,00001“), Komma",
          csv_ == ["0,00001", "-0,000000004", "2,5", "100000000000000000000"], str(csv_))
    n = Datentabelle([Spalte("Nr", "", "ganz"), Spalte("N", "kN", "zahl", 2)], "Null")
    n.setzen([[1, -0.0], [2, -1e-12], [3, 1e-7]])
    csv_ = n.text().splitlines()[1:]
    check("Export einer negativen Null oder von Rundungsschrott: „0,0“, nie „-0,0“ oder „1e-07“",
          csv_ == ["1;0,0", "2;0,0", "3;0,0000001"], str(csv_))
    check("Export (CSV, Zwischenablage): kein „-0“ vor einer Null, keine Punktzahl",
          not re.search(r"-0[,.]0+(?!\d)", text) and "1.23" not in text and "0,00 / 1,23" in text,
          text.splitlines()[1])
    check("Art im Klartext: „Balken 3D“, unbekannte Schluessel bleiben stehen",
          cell(0, 3) == "Balken 3D" and cell(1, 3) == "Schale, Viereck" and cell(2, 3) == "tet99",
          f"{cell(0, 3)} | {cell(1, 3)} | {cell(2, 3)}")
    check("… die Zeile behaelt den Schluessel (Wahllisten lesen ihn)", m.zeilen[0][3] == "beam")
    t.filter.setze_filter(3, "balken")
    check("… der Filter sucht im Klartext", t.sichtbar() == 1, str(t.sichtbar()))
    t.filter.setze_filter(3, "beam")
    check("… und findet den Schluessel nicht mehr", t.sichtbar() == 0, str(t.sichtbar()))
    t.filter.leeren()
    check("… der Export nennt den Klartext", "Balken 3D" in text and "beam" not in text)
    t.view.sortByColumn(3, QtCore.Qt.AscendingOrder)
    folge = [t.filter.data(t.filter.index(r, 3), DR) for r in range(t.filter.rowCount())]
    check("… sortiert wird nach dem Klartext", folge == sorted(folge, key=str.lower), str(folge))

    # Farben: nur Eingabetabellen
    e = Datentabelle([Spalte("Name"), Spalte("E", "GPa", "zahl", 1, True)], "Eingabe")
    e.setzen([["S355", 210.0]])
    farbe = lambda tab_, k: tab_.modell.data(tab_.modell.index(0, k), BG)
    check("Eingabetabelle: editierbare Zelle weiss",
          isinstance(farbe(e, 1), QtGui.QBrush) and farbe(e, 1).color().name() == tab.ZELLE_EDIT == "#ffffff",
          farbe(e, 1).color().name() if farbe(e, 1) is not None else "None")
    check("… nicht editierbare Zelle grau",
          isinstance(farbe(e, 0), QtGui.QBrush) and farbe(e, 0).color().name() == tab.ZELLE_FEST
          and farbe(e, 0).color().name() != "#ffffff",
          farbe(e, 0).color().name() if farbe(e, 0) is not None else "None")
    check("… keine Zebrastreifen darunter", not e.view.alternatingRowColors())
    check("Ergebnistabelle (nichts editierbar): keine Farbe, Zebrastreifen bleiben",
          farbe(t, 1) is None and t.view.alternatingRowColors())
    check("Fusszeile (Max / Min) bleibt ohne Zellfarbe", e.fussmodell.zellfarben is False)

    # Reihenfolge
    z = [["Zebra", 1], ["Adler", 2], ["Mitte", 3]]
    r = Datentabelle([Spalte("Name"), Spalte("n", "", "ganz")], "Reihe", modellreihenfolge=True)
    r.setzen(z)
    check("Modellreihenfolge: so, wie die Zeilen gesetzt wurden",
          [x[0] for x in r.modell.zeilen] == ["Zebra", "Adler", "Mitte"], str([x[0] for x in r.modell.zeilen]))
    a = Datentabelle([Spalte("Name"), Spalte("n", "", "ganz")], "Alphabet")
    a.setzen(z)
    check("… ohne den Schalter nach der ersten Spalte (Vorgabe bleibt)",
          [x[0] for x in a.modell.zeilen] == ["Adler", "Mitte", "Zebra"], str([x[0] for x in a.modell.zeilen]))
    r.view.sortByColumn(0, QtCore.Qt.AscendingOrder)
    check("Klick auf den Kopf sortiert wie gewohnt",
          [x[0] for x in r.modell.zeilen] == ["Adler", "Mitte", "Zebra"])
    r.setzen(z)
    check("… und bleibt nach neuem Fuellen bestehen",
          [x[0] for x in r.modell.zeilen] == ["Adler", "Mitte", "Zebra"])
    r.view.sortByColumn(-1, QtCore.Qt.AscendingOrder)
    check("dritter Klick (Sortierung aufgehoben): die Modellreihenfolge kommt zurueck",
          [x[0] for x in r.modell.zeilen] == ["Zebra", "Adler", "Mitte"], str([x[0] for x in r.modell.zeilen]))
    check("… der Kopf laesst die Sortierung aufheben", r.view.horizontalHeader().isSortIndicatorClearable())
    r.setzen(z + [["Eins", 4]])
    check("Neue Zeile haengt hinten an",
          [x[0] for x in r.modell.zeilen] == ["Zebra", "Adler", "Mitte", "Eins"])
    # echte Mausklicks auf den Spaltenkopf: aufsteigend, absteigend, aufgehoben
    from PySide6 import QtTest
    app = _app()
    h = Datentabelle([Spalte("Name"), Spalte("n", "", "ganz")], "Klick", modellreihenfolge=True)
    h.resize(420, 220)
    h.show()
    app.processEvents()
    h.setzen(z)
    kopf = h.view.horizontalHeader()
    pos = QtCore.QPoint(kopf.sectionViewportPosition(0) + 12, max(2, kopf.height() // 2))
    folgen = []
    for _ in range(3):
        QtTest.QTest.mouseClick(kopf.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos)
        app.processEvents()
        folgen.append([x[0] for x in h.modell.zeilen])
    check("Drei Klicks auf den Kopf: aufsteigend, absteigend, wieder die Modellreihenfolge",
          folgen == [["Adler", "Mitte", "Zebra"], ["Zebra", "Mitte", "Adler"],
                     ["Zebra", "Adler", "Mitte"]], str(folgen))
    h.close()


def _lasttexte(w):
    return [str(x) for z in w.tbl_last.modell.zeilen for x in z]


def test_fenster_reihenfolge_und_lasten():
    from PySide6 import QtCore
    w, app = _fenster()
    w._modell_setzen(_modell()); app.processEvents()
    check("Lastfaelle: Reihenfolge des Modells (LF1, Zebra, Adler, Mitte), nicht nach Name",
          _namen(w.tbl_lastfall) == ["LF1", "Zebra", "Adler", "Mitte"] == list(w.model.load_cases),
          str(_namen(w.tbl_lastfall)))
    check("Kombinationen: Reihenfolge des Modells (KB, KA)",
          _namen(w.tbl_kombi) == ["KB", "KA"], str(_namen(w.tbl_kombi)))
    check("… bei neu angelegtem Lastfall hinten", (w.model.add_load_case("Anfang", "G", activate=False),
                                                   w.refresh_all(), app.processEvents())
          and _namen(w.tbl_lastfall) == ["LF1", "Zebra", "Adler", "Mitte", "Anfang"], str(_namen(w.tbl_lastfall)))
    del w.model.load_cases["Anfang"]
    w.refresh_all(); app.processEvents()
    # die Tabelle liefert ihren Schluessel auch, wenn sie umsortiert wurde
    w.tbl_lastfall.view.sortByColumn(0, QtCore.Qt.AscendingOrder); app.processEvents()
    check("Spaltenkopf sortiert weiter (Adler, LF1, Mitte, Zebra)",
          _namen(w.tbl_lastfall) == ["Adler", "LF1", "Mitte", "Zebra"], str(_namen(w.tbl_lastfall)))
    w.tbl_lastfall.view.sortByColumn(-1, QtCore.Qt.AscendingOrder); app.processEvents()
    check("… und hebt sich wieder auf", _namen(w.tbl_lastfall) == ["LF1", "Zebra", "Adler", "Mitte"],
          str(_namen(w.tbl_lastfall)))

    # Lasttabelle: Komma, kein -0,000
    w.cb_lastfilter.setCurrentText("(alle)"); app.processEvents()
    items = [w.cb_lastfilter.itemText(i) for i in range(w.cb_lastfilter.count())]
    check("Auswahl „Lastfall“ über der Lasttabelle: ebenfalls in der Reihenfolge des Modells",
          items == ["(alle)", "LF1", "Zebra", "Adler", "Mitte"], str(items))
    texte = _lasttexte(w)
    grosse = [z[4] for z in w.tbl_last.modell.zeilen]
    punkt = [t for t in grosse + [str(z[5]) for z in w.tbl_last.modell.zeilen]
             if re.search(r"\d\.\d", t)]
    check("Lasttabelle: Zahlentexte mit Komma, kein Dezimalpunkt",
          not punkt and any("," in t for t in grosse), str(punkt[:3]))
    check("… keine „-0,000“ / „-0.000“ (auf null gerundet, ohne Vorzeichen)",
          not any(re.search(r"-0[,.]0+(?!\d)", t) for t in texte),
          str([t for t in texte if re.search(r"-0[,.]0", t)][:3]))
    check("… die Streckenlast -0,4 N/m steht als „q = (0,000, 0,000, 0,000) kN/m“",
          any(t == "q = (0,000, 0,000, 0,000) kN/m" for t in grosse), str(grosse))
    check("… Eigengewicht mit Komma: „-9,81 m/s²“", any(t == "-9,81 m/s²" for t in grosse), str(grosse))
    check("… das Bezugssystem steht auf Deutsch: „global“",
          any(str(z[5]) == "global" for z in w.tbl_last.modell.zeilen))


def test_art_im_klartext():
    w, app = _fenster()
    w._modell_setzen(_modell()); app.processEvents()
    m = w.model
    m.add_line("L1", [0, 1])
    w.refresh_all(); app.processEvents()
    t = w.tbl_elem.modell
    check("Elemente: Art „Balken 3D“ statt „beam“", t.data(t.index(0, 1)) == "Balken 3D",
          str(t.data(t.index(0, 1))))
    check("… die Zeile haelt den Schluessel (die Wahlliste des Querschnitts liest ihn)",
          t.zeilen[0][1] == "beam"
          and set(t.spalten[4].wahlwerte(t.zeilen[0])) == set(m.sections))
    t = w.tbl_linie.modell
    check("Linien: Art „Polylinie“ statt „polyline“", t.data(t.index(0, 1)) == "Polylinie",
          str(t.data(t.index(0, 1))))
    t = w.tbl_sec.modell
    check("Querschnitte: Typ „I-Profil“ statt „I“", t.data(t.index(0, 1)) == "I-Profil",
          str(t.data(t.index(0, 1))))
    sichtbar = []
    for name in ("tbl_elem", "tbl_linie", "tbl_sec", "tbl_lastfall", "tbl_kombi", "tbl_last"):
        tb = getattr(w, name)
        for r in range(tb.modell.rowCount()):
            for k in range(tb.modell.columnCount()):
                sichtbar.append(str(tb.modell.data(tb.modell.index(r, k))))
    check("kein Schluessel („beam“, „polyline“) in den Modelltabellen sichtbar",
          not any(s in ("beam", "polyline", "I", "local") for s in sichtbar),
          str([s for s in sichtbar if s in ("beam", "polyline", "I", "local")]))
    # Farben im Fenster: die Elementtabelle hat editierbare und feste Spalten
    from PySide6 import QtCore
    tm = w.tbl_elem.modell
    wei = tm.data(tm.index(0, 2), QtCore.Qt.BackgroundRole)
    grau = tm.data(tm.index(0, 0), QtCore.Qt.BackgroundRole)
    check("Elementtabelle: „Knoten“ (editierbar) weiss, „Element“ grau",
          wei is not None and wei.color().name() == "#ffffff"
          and grau is not None and grau.color().name() != "#ffffff",
          f"{wei.color().name() if wei else None} / {grau.color().name() if grau else None}")
    check("Lasttabelle (nichts editierbar): Zebrastreifen, keine Zellfarbe",
          w.tbl_last.view.alternatingRowColors()
          and w.tbl_last.modell.data(w.tbl_last.modell.index(0, 0), QtCore.Qt.BackgroundRole) is None
          if w.tbl_last.modell.rowCount() else True)


def test_klick_auf_lastfall():
    from PySide6 import QtCore
    w, app = _fenster()
    w._modell_setzen(_modell()); app.processEvents()
    w.cb_lastfilter.setCurrentText("(alle)"); app.processEvents()
    n_alle = len(w.tbl_last.modell.zeilen)
    register = w.tab_unten.currentIndex()
    vorher = len(getattr(w, "_undo", []))
    # Klick auf die Zeile „Adler“
    w.tbl_lastfall.zeile_gewaehlt.emit("Adler"); app.processEvents()
    lastfaelle = {str(z[1]) for z in w.tbl_last.modell.zeilen}
    check("Klick auf „Adler“: die Lasttabelle zeigt nur dessen Lasten",
          lastfaelle == {"Adler"} and w.cb_lastfilter.currentText() == "Adler",
          f"{lastfaelle} / {w.cb_lastfilter.currentText()}")
    check("… ohne das Register zu wechseln (der Doppelklick auf den Lastfall bleibt moeglich)",
          w.tab_unten.currentIndex() == register)
    check("… ohne Rueckfrage und ohne Aenderung des Modells (kein Rueckgaengig-Schritt)",
          len(getattr(w, "_undo", [])) == vorher and not w.fehler_liste, str(w.fehler_liste[:1]))
    w.tbl_lastfall.zeile_gewaehlt.emit("Zebra"); app.processEvents()
    zeb = {str(z[1]) for z in w.tbl_last.modell.zeilen}
    check("Klick auf „Zebra“: dessen Lasten (Eigengewicht, Streckenlast, Knotenlast)",
          zeb == {"Zebra"} and len(w.tbl_last.modell.zeilen) == 3, f"{zeb} {len(w.tbl_last.modell.zeilen)}")
    # echter Mausklick auf die Zeile der Tabelle
    tb = w.tbl_lastfall
    tb.view.selectRow(3); app.processEvents()
    idx = tb.filter.index(3, 0)
    tb.view.clicked.emit(idx); app.processEvents()
    check("Klick in der Tabelle auf die vierte Zeile („Mitte“)",
          {str(z[1]) for z in w.tbl_last.modell.zeilen} == {"Mitte"},
          str({str(z[1]) for z in w.tbl_last.modell.zeilen}))
    # die Lasttabelle loescht/waehlt weiter die richtige Last
    lc, liste, k = w._lastzeiger(0)
    check("… die Zeilen der Lasttabelle finden ihre Last wieder (Filter beruecksichtigt)",
          lc is not None and lc.name == "Mitte" and liste == "nodal_loads",
          f"{getattr(lc, 'name', None)} {liste}")
    w.cb_lastfilter.setCurrentText("(alle)"); app.processEvents()
    check("„(alle)“ zeigt wieder alles", len(w.tbl_last.modell.zeilen) == n_alle,
          f"{len(w.tbl_last.modell.zeilen)} von {n_alle}")
    w.tbl_lastfall.zeile_gewaehlt.emit("GibtEsNicht"); app.processEvents()
    check("Unbekannter Name: nichts geschieht", w.cb_lastfilter.currentText() == "(alle)"
          and not w.fehler_liste)


def _umhuellende(w, app, kontakt):
    from statik3d import solver
    w._modell_setzen(_modell(kontakt)); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    return an


def test_kontakt_hinweis():
    w, app = _fenster()
    _umhuellende(w, app, kontakt=False)
    check("Vorbedingung: die Umhüllende steht vorn",
          w.cb_result.currentText().startswith("Umhüllende"), w.cb_result.currentText())
    z1, z2 = w.tbl_contact.lbl_zeilen.text(), w.tbl_kontaktpaare.lbl_zeilen.text()
    check("Modell ohne Kontakt: kein Kontakt-Hinweis zur Umhüllenden",
          "Kontaktkräfte" not in z1 and "Kontaktkräfte" not in z2, f"{z1!r} / {z2!r}")
    check("… die Tabellen sind leer und sagen nur die Zeilenzahl",
          z1 == "0 Zeilen" and z2 == "0 Zeilen", f"{z1!r} / {z2!r}")
    _umhuellende(w, app, kontakt=True)
    z1, z2 = w.tbl_contact.lbl_zeilen.text(), w.tbl_kontaktpaare.lbl_zeilen.text()
    check("Modell mit Kontakt: der Hinweis steht, wie bisher",
          "Kontaktkräfte gibt es zu Lastfall oder Kombination" in z1
          and "Kontaktkräfte gibt es zu Lastfall oder Kombination" in z2, f"{z1!r}")
    # auf einen Lastfall umschalten: der alte Hinweis verschwindet, es gibt Zeilen
    faelle = [i for i in range(w.cb_result.count()) if w.cb_result.itemData(i)[0] == "case"]
    w.cb_result.setCurrentIndex(faelle[0]); app.processEvents()
    z1 = w.tbl_contact.lbl_zeilen.text()
    check("… bei einem Lastfall-Ergebnis steht kein Hinweis mehr",
          "Kontaktkräfte gibt es" not in z1 and w.tbl_contact.zeilenzahl() >= 1, f"{z1!r}")
    # Kontakt-Art im Klartext
    t = w.tbl_contact.modell
    arten = {str(t.data(t.index(r, 1))) for r in range(t.rowCount())}
    check("Kontakt-Tabelle: die Art steht im Klartext („Einseitiges Lager“)",
          arten and arten <= {"Einseitiges Lager", "Spaltelement", "Kontaktfläche",
                              "Lagerbedingung (Verschiebung)", "Lagerbedingung (Drehung)"}
          and not arten & {"support", "gap", "surface", "dof"}, str(arten))
    # ohne Kontakt, Lastfall-Ergebnis nach der Umhuellenden: ein Hinweis von vorhin bleibt nicht stehen
    _umhuellende(w, app, kontakt=False)
    faelle = [i for i in range(w.cb_result.count()) if w.cb_result.itemData(i)[0] == "case"]
    w.cb_result.setCurrentIndex(faelle[0]); app.processEvents()
    check("Modell ohne Kontakt, Lastfall-Ergebnis: auch hier kein Hinweis",
          "Kontaktkräfte gibt es" not in w.tbl_contact.lbl_zeilen.text(),
          w.tbl_contact.lbl_zeilen.text())
    # Auflager der Umhuellenden: Komma, kein -0,00
    w.cb_result.setCurrentIndex(0); app.processEvents()
    t = w.tbl_react.modell
    zellen = [str(t.data(t.index(r, k))) for r in range(t.rowCount()) for k in range(1, t.columnCount())]
    check("Auflager der Umhüllenden: „min / max“ mit Komma, kein Punkt, kein „-0,00“",
          zellen and all("," in z and "." not in z for z in zellen)
          and not any(re.search(r"-0,0+(?!\d)", z) for z in zellen), str(zellen[:3]))


def main():
    print("=" * 96)
    print("STATIK3D - Tabelleninhalte (Teilpaket 10a)")
    print("=" * 96)
    for t in (test_festkomma, test_tabelle_pur, test_fenster_reihenfolge_und_lasten,
              test_art_im_klartext, test_klick_auf_lastfall, test_kontakt_hinweis):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001 - eine fehlende Funktion darf die Suite nicht abbrechen
            check(f"{t.__name__} lief bis zum Ende durch", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 96)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
