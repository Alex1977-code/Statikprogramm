"""
Rechtsklick in der Ansicht (Plan-Teilpaket 14c, 03.10.2026): auf ein Objekt
dessen Befehle, ins Leere Sicht und Zoom.

Plan, Kapitel 6, Zeile 14c: „Rechtsklick auf ein Objekt zeigt dessen Befehle,
ins Leere Sicht und Zoom (heute sind beide Menüs gleich, nur Lager werden
erkannt)“.

Stand davor (am Quelltext gelesen): ein Menue fuer jeden Rechtsklick - oben die
Befehle der Auswahl, dann ein Knoten-, Linien- oder Flaechenlager, wenn eines
unter dem Zeiger lag, sonst die Lagergroessen, darunter Darstellung, FE-Netz,
Knoten, Nummern und „Zoom alles“. Knoten, Staebe, Linien, Flaechen, Volumen,
Elemente und Lasten unter dem Zeiger erkannte es nicht, und der Rechtsklick
waehlte nichts.

Geprueft wird mit dem echten Hauptfenster (offscreen) auf dem Weg aus
``tests/test_klickauswahl.py``: Rechtsklick als Qt-Mausereignisse (Druecken und
Loslassen ohne Zug) an die Ansicht, VTK sieht den Zeiger auf dem Weltpunkt, die
Draufsicht bildet die Pruefung selbst ab (``_projizieren``, 30 Bildpunkte je
Meter), Flaechen und Volumen findet ein Ersatz des Zellenpickers nach der Lage
des Zeigers. Das Menue oeffnet sich wirklich (``QMenu.exec``); ein Takt haelt es
fest und schliesst es gleich wieder - ``QMenu.exec`` laesst sich in PySide6
nicht ersetzen (gemessen: das ersetzte blieb ungerufen, das echte stand). Seine
Eintraege werden danach ausgeloest (``trigger``).

* je Objektart (Knoten, Stab, Linie, Flaeche, Volumen, Element, Knoten-,
  Linien- und Flaechenlager, Last) Titel und Eintraege des Menues, und jeder
  Eintrag tut, was er sagt (Maske, Tabelle, Baum, Ausblenden, Nur dieses
  zeigen, Loeschen, Lagergroesse, Lagerdichte);
* ins Leere nur Sicht und Zoom, mit Auswahl dazu ihre Befehle; die Auswahl bleibt;
* Auswahl beim Rechtsklick: ausserhalb ersetzt das Objekt sie, innerhalb bleibt
  sie, und das Menue bietet dazu die Befehle der ganzen Auswahl;
* zweite Ecke des Auswahlfensters: der Rechtsklick schliesst es ab, kein Menue;
* geaenderte Maske: „Bearbeiten…“ und die Eintraege, die eine Maske oeffnen,
  halten an der Leiste, und die Auswahl wird erst danach umgestellt;
* waehrend einer Rechnung nur Sicht und Zoom.

Offscreen **ungeprueft**: ``_weltpunkt`` (der vtkPropPicker liefert offscreen
immer None - hier liefert ein Ersatz den Weltpunkt, an dem Lager und Lasten
erkannt werden), der Zellenpicker (Ersatz nach der Lage des Zeigers, fuer
Elemente ein fester Ersatz), die echte Kamera beim Treffen (das Renderfenster
hat offscreen 0 x 0 Bildpunkte) und das Menue selbst auf dem Bildschirm: Lage,
Schrift, Trennlinien, ob es sich mit Esc schliesst. Das prueft die
Oberflaechenpruefung auf dem Desktop.

Aufruf:  python -m tests.test_rechtsklick
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

import numpy as np  # noqa: E402

from tests import test_klickauswahl as ka  # noqa: E402  (Pruefmodell, Draufsicht, Klick)

os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_rechtsklick_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
#: die Menues, die sich geoeffnet haben (der Takt aus _fangen schliesst sie gleich)
MENUES = []
#: die Rueckfragen vor dem Loeschen
FRAGEN = []
#: modale Fenster, die sich oeffnen wollten: (Art, Text)
MODAL = []
#: was die ersetzte Eingabe einer Zahl (Lagergroesse, Lagerdichte) liefert
ZAHL = 2.5
#: ein Punkt, unter dem nichts liegt
LEER = np.array([14.0, 6.0, 0.0])


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _abfangen():
    """Kein modales Fenster bleibt stehen - jedes wird aufgezeichnet."""
    from PySide6 import QtWidgets
    QtWidgets.QInputDialog.getDouble = staticmethod(lambda *a, **k: (MODAL.append(("zahl", str(a[1:3]))),
                                                                     (ZAHL, True))[1])
    QtWidgets.QDialog.exec = lambda self, *a, **k: (MODAL.append(("exec", type(self).__name__)), 0)[1]
    B = QtWidgets.QMessageBox
    B.question = staticmethod(lambda *a, **k: (MODAL.append(("question", str(a[2:3]))), B.No)[1])


class _Fang:
    """Solange er laeuft: ein Takt, der jedes Menue, das sich oeffnet, festhaelt
    und gleich wieder schliesst (exec kehrt dann ohne Eintrag zurueck), und jedes
    modale Fenster aufzeichnet und schliesst - offscreen bliebe beides stehen."""

    def __enter__(self):
        from PySide6 import QtCore, QtWidgets

        def nachsehen():
            p = QtWidgets.QApplication.activePopupWidget()
            if isinstance(p, QtWidgets.QMenu) and (not MENUES or MENUES[-1] is not p):
                MENUES.append(p)
                p.close()
            d = QtWidgets.QApplication.activeModalWidget()
            if d is not None:
                MODAL.append(("modal", type(d).__name__))
                d.close()
        self.takt = QtCore.QTimer()
        self.takt.setInterval(5)
        self.takt.timeout.connect(nachsehen)
        self.takt.start()
        return self

    def __exit__(self, *_exc):
        self.takt.stop()
        return False


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _abfangen()
    w = MainWindow()
    w.show()
    app.processEvents()
    # Rueckfragen nie anzeigen (Neu mit ungespeicherten Aenderungen, Loeschen)
    w._fragen_knoepfe = lambda *a, **k: True
    w._frage_speichern_verwerfen = lambda *a, **k: "verwerfen"
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: w.fehler_liste.append(str(msg))
    _FENSTER.update(w=w, app=app)
    _antwort(w, True)
    return w, app


def _antwort(w, ja: bool):
    """Die Rueckfrage vor dem Loeschen: aufzeichnen und mit Ja oder Nein beantworten."""
    w._bestaetigen = lambda text, *a, **k: (FRAGEN.append(str(text)), ja)[1]


def _modell(w, app):
    """Das Pruefmodell aus tests/test_klickauswahl.py (Staebe S1-S4 an K0-K5,
    Flaechen F1, F2 mit Netz und je einem Volumen, Knotenlager an K0, Linienlager
    auf F1L0, Flaechenlager auf F2, Knotenlasten an K3 und K5), dazu ein freier
    Knoten K6, eine freie Linie LF, das Gelenk G1 an S1 und die
    Kontaktbedingung „Fuge“ an F1."""
    from statik3d.model import Kontaktbedingung
    m, n = ka._modell(w, app)
    n["K6"] = int(m.add_node(6.0, 3.0, 0.0))
    a, b = m.add_node(6.0, 7.0, 0.0), m.add_node(7.5, 7.0, 0.0)
    m.add_line("LF", [int(a), int(b)])
    m.add_hinge("G1", end=1, phiy="free")
    m.apply_hinge(int(m.members["S1"].elements[0]), "G1")
    m.kontaktbedingungen["Fuge"] = Kontaktbedingung("Fuge", flaechennamen=["F1"])
    w.refresh_all()
    w.auswahlart_setzen("Knoten")
    _leeren(w, app)
    MODAL.clear()
    FRAGEN.clear()
    return m, n


def _leeren(w, app):
    leiste = getattr(w, "aenderungsleiste", None)
    if leiste is not None and leiste.isVisible():
        _druecken(w, app, "Verwerfen")
    w.maskenrand.schliessen()
    w.clear_selection()
    if any(w.versteckt.values()):
        w.alles_zeigen()
    app.processEvents()


def rechtsklick(w, app, P, welt=None):
    """Rechtsklick (Druecken und Loslassen ohne Zug) auf den Weltpunkt P; das
    Menue, das sich oeffnen wollte - oder None. ``welt``: der Weltpunkt, den der
    Picker unter dem Zeiger faende (fuer Lager und Lasten; sonst None wie offscreen)."""
    from PySide6 import QtCore
    pos = ka._zeiger(w, P)
    punkt = None if welt is None else np.asarray(welt, float)
    w._weltpunkt = lambda _x, _y, _p=punkt: _p
    vorher = len(MENUES)
    try:
        with _Fang():
            ka._maus(w, app, QtCore.QEvent.MouseButtonPress, pos, QtCore.Qt.RightButton, QtCore.Qt.RightButton,
                     QtCore.Qt.NoModifier)
            ka._maus(w, app, QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.RightButton, QtCore.Qt.NoButton,
                     QtCore.Qt.NoModifier)
    finally:
        w.__dict__.pop("_weltpunkt", None)
    return MENUES[-1] if len(MENUES) > vorher else None


def _text(a) -> str:
    return a.text().split("\t")[0]


def texte(menu) -> list:
    """Die Eintraege eines Menues (Untermenues mit ihrem Titel), ohne Trennlinien."""
    return [_text(a) for a in menu.actions() if not a.isSeparator()] if menu is not None else []


def eintrag(menu, text):
    if menu is None:
        return None
    return next((a for a in menu.actions() if not a.isSeparator() and _text(a) == text), None)


def ausloesen(w, app, menu, text) -> bool:
    """Den Eintrag ``text`` ausloesen - False, wenn es ihn nicht gibt oder er gesperrt ist."""
    a = eintrag(menu, text)
    if a is None or not a.isEnabled():
        return False
    with _Fang():
        a.trigger()
        app.processEvents()
    return True


def _titel(menu) -> str:
    """Die erste Zeile des Menues, wenn sie ein gesperrter Titel ist."""
    if menu is None or not menu.actions():
        return ""
    a = menu.actions()[0]
    return _text(a) if not a.isEnabled() else ""


def _maske(w):
    mr = w.maskenrand
    return mr.maske.titel if mr.offen() and mr.maske is not None else None


def _knoten(w):
    return sorted(int(i) for i in w.selection)


def _markiert(t) -> list:
    zeilen = sorted({i.row() for i in t.view.selectionModel().selectedRows()})
    return [t.filter.index(r, 0).data() for r in zeilen]


def _baumeintrag(w):
    it = w.baum.currentItem()
    return w.baum._schluessel(it) if it is not None else None


def _vorher_woanders(w):
    """Vor „In der Tabelle zeigen“ und „Im Baum zeigen“: eine andere Tabelle vorn,
    im Baum nichts gewaehlt - sonst prueften die Eintraege nichts."""
    w.tabelle_zeigen("Werkstoffe")
    w.baum.setCurrentItem(None)


def _leiste(w):
    leiste = getattr(w, "aenderungsleiste", None)
    return leiste if leiste is not None and leiste.isVisible() else None


def _druecken(w, app, text) -> bool:
    from PySide6 import QtWidgets
    leiste = getattr(w, "aenderungsleiste", None)
    b = None if leiste is None else next(
        (x for x in leiste.findChildren(QtWidgets.QPushButton) if x.text() == text), None)
    if b is None or not b.isVisible():
        return False
    b.click()
    app.processEvents()
    return True


# ---------------------------------------------------------------------------
def test_knoten():
    w, app = _fenster()
    m, n = _modell(w, app)
    k1 = n["K1"]
    menu = rechtsklick(w, app, m.nodes[k1])
    check("Knoten: Rechtsklick auf K1 öffnet sein Menü, K1 ist danach gewählt",
          menu is not None and _knoten(w) == [k1], f"{menu is not None} {_knoten(w)}")
    erwartet = [f"Knoten K{k1}", "Bearbeiten…", "Knotenlager…", "Knotenlast…", "In der Tabelle zeigen",
                "Im Baum zeigen", "Ausblenden", "Nur dieses zeigen", "Löschen"]
    check("… Titel „Knoten K1“ und die Befehle des Knotens", texte(menu) == erwartet
          and _titel(menu) == f"Knoten K{k1}", str(texte(menu)))
    ausloesen(w, app, menu, "Bearbeiten…")
    check("… „Bearbeiten…“ öffnet rechts die Maske des Knotens", _maske(w) == f"Knoten K{k1}", repr(_maske(w)))
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k1]), "Knotenlager…")
    check("… „Knotenlager…“ öffnet die Lagermaske, gewählt ist K1", _maske(w) == "Lager" and _knoten(w) == [k1],
          f"{_maske(w)!r} {_knoten(w)}")
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k1]), "Knotenlast…")
    check("… „Knotenlast…“ öffnet die Maske der Knotenlast", _maske(w) == "Knotenlast", repr(_maske(w)))
    _vorher_woanders(w)
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k1]), "In der Tabelle zeigen")
    check("… „In der Tabelle zeigen“: die Knotentabelle vorn, K1 markiert",
          w.aktive_tabelle() is w.tbl_knoten and [int(x) for x in _markiert(w.tbl_knoten)] == [k1],
          str(_markiert(w.tbl_knoten)))
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k1]), "Im Baum zeigen")
    check("… „Im Baum zeigen“: der Eintrag K1 ist im Modellbaum gewählt",
          _baumeintrag(w) == ("knoten", str(k1)), str(_baumeintrag(w)))
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k1]), "Ausblenden")
    check("… „Ausblenden“ nimmt K1 aus dem Bild", k1 in w.versteckt["knoten"], str(sorted(w.versteckt["knoten"])))
    w.alles_zeigen()
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k1]), "Nur dieses zeigen")
    check("… „Nur dieses zeigen“: K1 bleibt, K4 geht aus dem Bild",
          k1 not in w.versteckt["knoten"] and n["K4"] in w.versteckt["knoten"], str(len(w.versteckt["knoten"])))
    w.alles_zeigen()
    # Ein Knoten mit Lager: der Eintrag bearbeitet das Lager
    menu = rechtsklick(w, app, m.nodes[n["K0"]])
    check("Knoten K0 mit Lager: „Knotenlager bearbeiten…“ statt „Knotenlager…“",
          "Knotenlager bearbeiten…" in texte(menu) and "Knotenlager…" not in texte(menu), str(texte(menu)))
    ausloesen(w, app, menu, "Knotenlager bearbeiten…")
    check("… öffnet die Maske seines Lagers", _maske(w) == "Knotenlager 1", repr(_maske(w)))
    # Ein Netzknoten steht nicht im Modellbaum (nur die Knoten der Konstruktion, 8c)
    mitte = int(np.argmin(np.linalg.norm(m.nodes - np.array([2.0, 11.0, 0.0]), axis=1)))
    menu = rechtsklick(w, app, m.nodes[mitte])
    check("Netzknoten (Mitte von F1): dasselbe Menü ohne „Im Baum zeigen“",
          _titel(menu) == f"Knoten K{mitte}" and texte(menu) == [x if x != f"Knoten K{k1}" else f"Knoten K{mitte}"
                                                                for x in erwartet if x != "Im Baum zeigen"],
          str(texte(menu)))
    # Loeschen: der freie Knoten K6, eine Rueckfrage
    nn = m.nn
    FRAGEN.clear()
    ausloesen(w, app, rechtsklick(w, app, m.nodes[n["K6"]]), "Löschen")
    check("… „Löschen“ auf dem freien Knoten K6: eine Rückfrage, der Knoten ist weg",
          len(FRAGEN) == 1 and "1 Knoten" in FRAGEN[0] and w.model.nn == nn - 1
          and not np.any(np.all(np.isclose(w.model.nodes, [6.0, 3.0, 0.0]), axis=1)), f"{FRAGEN} {nn} -> {w.model.nn}")
    _leeren(w, app)


def test_stab():
    w, app = _fenster()
    m, n = _modell(w, app)
    w.auswahlart_setzen("Stab")
    try:
        s2 = ka._mitte(m, n["K1"], n["K2"])
        menu = rechtsklick(w, app, s2)
        erwartet = ["Stab S2", "Bearbeiten…", "Gelenke…", "Stablast…", "In der Tabelle zeigen", "Im Baum zeigen",
                    "Ausblenden", "Nur dieses zeigen", "Löschen"]
        check("Stab: Rechtsklick auf S2 - Titel und Befehle, S2 gewählt",
              texte(menu) == erwartet and _titel(menu) == "Stab S2" and w.sel_staebe == ["S2"],
              f"{texte(menu)} {w.sel_staebe}")
        menu1 = rechtsklick(w, app, ka._mitte(m, n["K0"], n["K1"]))
        check("… S1 trägt das Gelenk G1: „Gelenk G1 bearbeiten…“ nach „Gelenke…“",
              texte(menu1)[2:5] == ["Gelenke…", "Gelenk G1 bearbeiten…", "Stablast…"], str(texte(menu1)))
        ausloesen(w, app, menu1, "Gelenk G1 bearbeiten…")
        check("… und öffnet die Maske des Gelenks", (_maske(w) or "").startswith("Gelenk G1"), repr(_maske(w)))
        ausloesen(w, app, rechtsklick(w, app, s2), "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Maske des Stabes", _maske(w) == "Stab S2", repr(_maske(w)))
        ausloesen(w, app, rechtsklick(w, app, s2), "Gelenke…")
        check("… „Gelenke…“ öffnet die Gelenkmaske für den gewählten Stab S2",
              (_maske(w) or "").startswith("Gelenk") and w.sel_staebe == ["S2"], f"{_maske(w)!r} {w.sel_staebe}")
        ausloesen(w, app, rechtsklick(w, app, s2), "Stablast…")
        check("… „Stablast…“ öffnet die Maske der Linienlast für S2",
              _maske(w) == "Linienlast" and w.sel_staebe == ["S2"], f"{_maske(w)!r} {w.sel_staebe}")
        _vorher_woanders(w)
        ausloesen(w, app, rechtsklick(w, app, s2), "In der Tabelle zeigen")
        els = [int(e) for e in m.members["S2"].elements]
        check("… „In der Tabelle zeigen“: die Elementtabelle vorn, die Elemente von S2 markiert",
              w.aktive_tabelle() is w.tbl_elem and sorted(int(x) for x in _markiert(w.tbl_elem)) == els,
              str(_markiert(w.tbl_elem)))
        ausloesen(w, app, rechtsklick(w, app, s2), "Im Baum zeigen")
        check("… „Im Baum zeigen“: S2 im Modellbaum gewählt", _baumeintrag(w) == ("stab", "S2"), str(_baumeintrag(w)))
        ausloesen(w, app, rechtsklick(w, app, s2), "Ausblenden")
        check("… „Ausblenden“ nimmt die Elemente von S2 aus dem Bild", set(els) <= w.versteckt["elemente"],
              str(sorted(w.versteckt["elemente"])[:8]))
        w.alles_zeigen()
        ausloesen(w, app, rechtsklick(w, app, s2), "Nur dieses zeigen")
        andere = [int(e) for e in m.members["S4"].elements]
        check("… „Nur dieses zeigen“: S2 bleibt, S4 geht aus dem Bild",
              not (set(els) & w.versteckt["elemente"]) and set(andere) <= w.versteckt["elemente"])
        w.alles_zeigen()
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, ka._mitte(m, n["K4"], n["K5"])), "Löschen")
        check("… „Löschen“ auf S4: eine Rückfrage, der Stab ist weg",
              len(FRAGEN) == 1 and "S4" not in w.model.members, f"{FRAGEN} {list(w.model.members)}")
    finally:
        w.auswahlart_setzen("Knoten")
    # Auswahlart Knoten, Rechtsklick auf die Stabachse: wie der Linksklick der Stab
    _leeren(w, app)
    menu = rechtsklick(w, app, ka._mitte(m, n["K1"], n["K2"]) + [0.6, 0.0, 0.0])
    check("Auswahlart Knoten, Rechtsklick auf die Achse von S2: das Menü des Stabes, die Art springt um",
          _titel(menu) == "Stab S2" and w.auswahlart == "Stab" and w.sel_staebe == ["S2"],
          f"{_titel(menu)!r} {w.auswahlart} {w.sel_staebe}")
    w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_linie():
    w, app = _fenster()
    m, n = _modell(w, app)
    w.auswahlart_setzen("Linie")
    P = np.array([6.75, 7.0, 0.0])
    try:
        menu = rechtsklick(w, app, P, welt=P)
        erwartet = ["Linie LF", "Bearbeiten…", "Linienlast…", "In der Tabelle zeigen", "Im Baum zeigen",
                    "Ausblenden", "Nur dieses zeigen", "Löschen"]
        check("Linie: Rechtsklick auf LF - Titel und Befehle, LF gewählt",
              texte(menu) == erwartet and w.sel_linien == ["LF"], f"{texte(menu)} {w.sel_linien}")
        ausloesen(w, app, menu, "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Maske der Linie", _maske(w) == "Linie LF", repr(_maske(w)))
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Linienlast…")
        check("… „Linienlast…“ öffnet die Maske der Linienlast für LF",
              _maske(w) == "Linienlast" and w.sel_linien == ["LF"], f"{_maske(w)!r} {w.sel_linien}")
        _vorher_woanders(w)
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "In der Tabelle zeigen")
        check("… „In der Tabelle zeigen“: die Linientabelle vorn, LF markiert",
              w.aktive_tabelle() is w.tbl_linie and _markiert(w.tbl_linie) == ["LF"], str(_markiert(w.tbl_linie)))
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Im Baum zeigen")
        check("… „Im Baum zeigen“: LF im Modellbaum gewählt", _baumeintrag(w) == ("linie", "LF"),
              str(_baumeintrag(w)))
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Ausblenden")
        check("… „Ausblenden“ nimmt LF aus dem Bild", "LF" in w.versteckt["linien"], str(w.versteckt["linien"]))
        w.alles_zeigen()
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Nur dieses zeigen")
        check("… „Nur dieses zeigen“: LF bleibt, F1L0 geht aus dem Bild",
              "LF" not in w.versteckt["linien"] and "F1L0" in w.versteckt["linien"], str(len(w.versteckt["linien"])))
        w.alles_zeigen()
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Löschen")
        check("… „Löschen“: eine Rückfrage, die Linie LF ist weg", len(FRAGEN) == 1 and "LF" not in w.model.lines,
              f"{FRAGEN}")
    finally:
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_flaeche_volumen():
    w, app = _fenster()
    m, n = _modell(w, app)
    f1, f2 = np.array([2.0, 11.0, 0.0]), np.array([10.0, 11.0, 0.0])
    w.auswahlart_setzen("Fläche")
    try:
        menu = rechtsklick(w, app, f1)
        erwartet = ["Fläche F1", "Bearbeiten…", "Flächenlast…", "Kontaktbedingung Fuge…", "In der Tabelle zeigen",
                    "Im Baum zeigen", "Ausblenden", "Nur dieses zeigen", "Löschen"]
        check("Fläche: Rechtsklick auf F1 - Titel, Befehle und ihre Kontaktbedingung, F1 gewählt",
              texte(menu) == erwartet and w.sel_flaechen == ["F1"], f"{texte(menu)} {w.sel_flaechen}")
        check("… F2 ohne Kontaktbedingung: kein solcher Eintrag",
              texte(rechtsklick(w, app, f2)) == ["Fläche F2"] + [x for x in erwartet[1:] if not x.startswith("Kontakt")],
              str(texte(MENUES[-1])))
        ausloesen(w, app, rechtsklick(w, app, f1), "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Maske der Fläche", _maske(w) == "Fläche F1", repr(_maske(w)))
        ausloesen(w, app, rechtsklick(w, app, f1), "Flächenlast…")
        check("… „Flächenlast…“ öffnet die Maske der Flächenlast für F1",
              _maske(w) == "Flächenlast" and w.sel_flaechen == ["F1"], f"{_maske(w)!r} {w.sel_flaechen}")
        ausloesen(w, app, rechtsklick(w, app, f1), "Kontaktbedingung Fuge…")
        check("… „Kontaktbedingung Fuge…“ öffnet ihre Maske", _maske(w) == "Kontaktbedingung Fuge", repr(_maske(w)))
        _vorher_woanders(w)
        ausloesen(w, app, rechtsklick(w, app, f1), "In der Tabelle zeigen")
        check("… „In der Tabelle zeigen“: die Flächentabelle vorn, F1 markiert",
              w.aktive_tabelle() is w.tbl_geoflaeche and _markiert(w.tbl_geoflaeche) == ["F1"],
              str(_markiert(w.tbl_geoflaeche)))
        ausloesen(w, app, rechtsklick(w, app, f1), "Im Baum zeigen")
        check("… „Im Baum zeigen“: F1 im Modellbaum gewählt", _baumeintrag(w) == ("geoflaeche", "F1"),
              str(_baumeintrag(w)))
        ausloesen(w, app, rechtsklick(w, app, f1), "Ausblenden")
        check("… „Ausblenden“ nimmt F1 aus dem Bild", "F1" in w.versteckt["flaechen"], str(w.versteckt["flaechen"]))
        w.alles_zeigen()
        ausloesen(w, app, rechtsklick(w, app, f1), "Nur dieses zeigen")
        check("… „Nur dieses zeigen“: F1 bleibt, F2 geht aus dem Bild",
              "F1" not in w.versteckt["flaechen"] and "F2" in w.versteckt["flaechen"], str(w.versteckt["flaechen"]))
        w.alles_zeigen()
        # Volumen
        w.auswahlart_setzen("Volumen")
        menu = rechtsklick(w, app, f1)
        erwartet_v = ["Volumen V1"] + erwartet[1:]
        check("Volumen: Rechtsklick auf V1 - Titel und Befehle (die Kontaktbedingung an seiner Fläche)",
              texte(menu) == erwartet_v and w.sel_koerper == ["V1"], f"{texte(menu)} {w.sel_koerper}")
        ausloesen(w, app, menu, "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Maske des Volumens", _maske(w) == "Volumen V1", repr(_maske(w)))
        ausloesen(w, app, rechtsklick(w, app, f1), "Flächenlast…")
        check("… „Flächenlast…“ öffnet die Maske für V1", _maske(w) == "Flächenlast" and w.sel_koerper == ["V1"],
              f"{_maske(w)!r} {w.sel_koerper}")
        _vorher_woanders(w)
        ausloesen(w, app, rechtsklick(w, app, f1), "In der Tabelle zeigen")
        check("… „In der Tabelle zeigen“: die Tabelle der Volumenkörper vorn, V1 markiert",
              w.aktive_tabelle() is w.tbl_geokoerper and _markiert(w.tbl_geokoerper) == ["V1"],
              str(_markiert(w.tbl_geokoerper)))
        ausloesen(w, app, rechtsklick(w, app, f1), "Im Baum zeigen")
        check("… „Im Baum zeigen“: V1 im Modellbaum gewählt", _baumeintrag(w) == ("geokoerper_einzeln", "V1"),
              str(_baumeintrag(w)))
        ausloesen(w, app, rechtsklick(w, app, f1), "Ausblenden")
        check("… „Ausblenden“ nimmt V1 aus dem Bild", "V1" in w.versteckt["koerper"], str(w.versteckt["koerper"]))
        w.alles_zeigen()
        ausloesen(w, app, rechtsklick(w, app, f1), "Nur dieses zeigen")
        check("… „Nur dieses zeigen“: V1 bleibt, V2 geht aus dem Bild",
              "V1" not in w.versteckt["koerper"] and "V2" in w.versteckt["koerper"], str(w.versteckt["koerper"]))
        w.alles_zeigen()
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, f2), "Löschen")
        check("… „Löschen“ auf V2: eine Rückfrage, das Volumen ist weg",
              len(FRAGEN) == 1 and "V2" not in w.model.koerper, f"{FRAGEN}")
        w.auswahlart_setzen("Fläche")
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, f2), "Löschen")
        check("Fläche: „Löschen“ auf F2 (ohne ihr Volumen): eine Rückfrage, die Fläche ist weg",
              len(FRAGEN) == 1 and "F2" not in w.model.flaechen, f"{FRAGEN}")
    finally:
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_element():
    w, app = _fenster()
    m, n = _modell(w, app)
    w.auswahlart_setzen("Netz")
    alt = w._element_am_zeiger
    P = np.array([2.0, 11.0, 0.0])
    try:
        w._element_am_zeiger = lambda: 5
        menu = rechtsklick(w, app, P)
        erwartet = ["Element E5", "Bearbeiten…", "In der Tabelle zeigen", "Ausblenden", "Nur dieses zeigen", "Löschen"]
        check("Element (Schale E5): Titel und Befehle, ohne „Im Baum zeigen“ (Schalen stehen dort nicht einzeln)",
              texte(menu) == erwartet and [int(x) for x in w.sel_elemente] == [5], f"{texte(menu)} {w.sel_elemente}")
        ausloesen(w, app, menu, "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Sammelmaske für E5", _maske(w) == "1 Elemente bearbeiten", repr(_maske(w)))
        _vorher_woanders(w)
        ausloesen(w, app, rechtsklick(w, app, P), "In der Tabelle zeigen")
        check("… „In der Tabelle zeigen“: die Elementtabelle vorn, E5 markiert",
              w.aktive_tabelle() is w.tbl_elem and [int(x) for x in _markiert(w.tbl_elem)] == [5],
              str(_markiert(w.tbl_elem)))
        ausloesen(w, app, rechtsklick(w, app, P), "Ausblenden")
        check("… „Ausblenden“ nimmt E5 aus dem Bild", w.versteckt["elemente"] == {5}, str(w.versteckt["elemente"]))
        w.alles_zeigen()
        ausloesen(w, app, rechtsklick(w, app, P), "Nur dieses zeigen")
        check("… „Nur dieses zeigen“: E5 bleibt, E6 geht aus dem Bild",
              5 not in w.versteckt["elemente"] and 6 in w.versteckt["elemente"])
        w.alles_zeigen()
        ne = len(w.model.elements)
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, P), "Löschen")
        check("… „Löschen“: eine Rückfrage, ein Element weniger", len(FRAGEN) == 1 and len(w.model.elements) == ne - 1,
              f"{FRAGEN} {ne} -> {len(w.model.elements)}")
        # ein Stabelement: Maske des Stabelements, im Baum unter FE-Netz
        e1 = int(w.model.members["S2"].elements[0])
        w._element_am_zeiger = lambda: e1
        menu = rechtsklick(w, app, P)
        check("Stabelement: mit „Im Baum zeigen“", texte(menu) == [f"Element E{e1}", "Bearbeiten…",
                                                                   "In der Tabelle zeigen", "Im Baum zeigen",
                                                                   "Ausblenden", "Nur dieses zeigen", "Löschen"],
              str(texte(menu)))
        ausloesen(w, app, menu, "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Maske des Stabelements", _maske(w) == f"Stab E{e1}", repr(_maske(w)))
        ausloesen(w, app, rechtsklick(w, app, P), "Im Baum zeigen")
        check("… „Im Baum zeigen“: das Stabelement im Modellbaum gewählt",
              _baumeintrag(w) == ("stabelement", str(e1)), str(_baumeintrag(w)))
    finally:
        w._element_am_zeiger = alt
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_lager():
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    m, n = _modell(w, app)
    size = m.characteristic_size()
    p_ll = vp.lager_punkte(m, m.line_supports[0], size, w.lagerdichte)[0][0]
    p_fl = vp.lager_punkte(m, m.surface_supports[0], size, w.lagerdichte)[0][0]
    k0 = np.asarray(m.nodes[n["K0"]], float)
    n_k, n_l = len(m.supports), len(m.line_supports)
    w.auswahlart_setzen("Lager")
    try:
        # Titel wie im Modellbaum: Name (oder Art und Nummer) und Ort; das
        # Pruefmodell nennt Linien- und Flaechenlager „LL1“ und „FL1“
        for art, P, lang, baum, zeile, mitte, titel, maske in (
                ("lager", k0, "Knotenlager", "lager_einzeln", 0, "Größe dieses Lagers…", "Knotenlager 1 (K0)",
                 "Knotenlager 1"),
                ("linienlager", p_ll, "Linienlager", "linienlager_einzeln", n_k, "Lagerdichte…",
                 f"Linienlager {w._lagername(('linienlager', 0))}", "Linienlager LL1"),
                ("flaechenlager", p_fl, "Flächenlager", "flaechenlager_einzeln", n_k + n_l, "Lagerdichte…",
                 f"Flächenlager {w._lagername(('flaechenlager', 0))}", "Flächenlager FL1")):
            menu = rechtsklick(w, app, P, welt=P)
            erwartet = [titel, "Bearbeiten…", mitte, "Größe aller Lager…", "In der Tabelle zeigen", "Im Baum zeigen",
                        "Löschen"]
            check(f"{lang}: Rechtsklick auf das Symbol - Titel „{titel}“ und Befehle, das Lager gewählt",
                  texte(menu) == erwartet and w.sel_lager == [(art, 0)], f"{texte(menu)} {w.sel_lager}")
            ausloesen(w, app, menu, "Bearbeiten…")
            check(f"… „Bearbeiten…“ öffnet die Maske „{maske}“", _maske(w) == maske, repr(_maske(w)))
            MODAL.clear()
            ausloesen(w, app, rechtsklick(w, app, P, welt=P), mitte)
            if art == "lager":
                check("… „Größe dieses Lagers…“ fragt die Zahl ab und setzt sie an diesem Lager",
                      len(MODAL) == 1 and float(m.supports[0].groesse) == ZAHL, f"{MODAL} {m.supports[0].groesse}")
            else:
                check("… „Lagerdichte…“ fragt die Zahl ab und setzt die Dichte",
                      len(MODAL) == 1 and w.lagerdichte == ZAHL, f"{MODAL} {w.lagerdichte}")
                w.lagerdichte = 1.0
                w.redraw()
            ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Größe aller Lager…")
            check("… „Größe aller Lager…“ setzt die Größe aller", w.lagergroesse == ZAHL, str(w.lagergroesse))
            w.lagergroesse = 1.0
            w.redraw()
            _vorher_woanders(w)
            ausloesen(w, app, rechtsklick(w, app, P, welt=P), "In der Tabelle zeigen")
            check("… „In der Tabelle zeigen“: die Lagertabelle vorn, seine Zeile markiert",
                  w.aktive_tabelle() is w.tbl_lager and [int(x) for x in _markiert(w.tbl_lager)] == [zeile],
                  str(_markiert(w.tbl_lager)))
            ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Im Baum zeigen")
            check("… „Im Baum zeigen“: das Lager im Modellbaum gewählt", _baumeintrag(w) == (baum, "0"),
                  str(_baumeintrag(w)))
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, p_fl, welt=p_fl), "Löschen")
        check("Flächenlager: „Löschen“ - eine Rückfrage, das Lager ist weg",
              len(FRAGEN) == 1 and not w.model.surface_supports, f"{FRAGEN}")
        # Lager trifft der Rechtsklick in jeder Auswahlart (wie vorher)
        w.auswahlart_setzen("Stab")
        menu = rechtsklick(w, app, k0 + [-1.0, -1.0, 0.0], welt=k0)
        check("Auswahlart Stab, Rechtsklick neben die Stäbe auf das Lagersymbol: das Menü des Knotenlagers",
              _titel(menu) == "Knotenlager 1 (K0)", repr(_titel(menu)))
    finally:
        w.lagergroesse = 1.0
        w.lagerdichte = 1.0
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_last():
    w, app = _fenster()
    m, n = _modell(w, app)
    fall = m.active_case
    w.auswahlart_setzen("Last")
    w.redraw()
    app.processEvents()
    try:
        punkte = [x for x in (getattr(w, "_lastpunkte", None) or []) if x[0] == "nodal_loads"]
        if not check("Last: die Knotenlasten stehen als Symbole im Bild", len(punkte) >= 2, str(len(punkte))):
            return
        _liste, k, P = punkte[0][:3]
        k = int(k)
        knoten = m.load_cases[fall].nodal_loads[k].node
        titel = f"Knotenlast K{knoten} ({fall})"
        menu = rechtsklick(w, app, P, welt=P)
        check("Last: Rechtsklick auf die Knotenlast - Titel und Befehle, die Last gewählt, ihre Maske noch zu",
              texte(menu) == [titel, "Bearbeiten…", "In der Tabelle zeigen", "Löschen"]
              and w.sel_lasten == [(fall, "nodal_loads", k)] and _maske(w) is None,
              f"{texte(menu)} {w.sel_lasten} {_maske(w)!r}")
        ausloesen(w, app, menu, "Bearbeiten…")
        check("… „Bearbeiten…“ öffnet die Maske der Last", _maske(w) == titel, repr(_maske(w)))
        _vorher_woanders(w)
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "In der Tabelle zeigen")
        zeilen = [int(x) for x in _markiert(w.tbl_last)]
        lc_, liste_, k_ = w._lastzeiger(zeilen[0]) if len(zeilen) == 1 else (None, "", -1)
        check("… „In der Tabelle zeigen“: die Lasttabelle vorn, die Zeile dieser Last markiert",
              w.aktive_tabelle() is w.tbl_last and lc_ is not None and (lc_.name, liste_, k_) == (fall, "nodal_loads", k),
              f"{zeilen} -> {(getattr(lc_, 'name', None), liste_, k_)}")
        # die Zeilennummer der Last (_lastzeile) ist die Umkehrung von _lastzeiger - fuer jede Zeile
        paare, nr = [], 0
        while True:
            lc_, liste_, k_ = w._lastzeiger(nr)
            if lc_ is None:
                break
            paare.append((nr, w._lastzeile(lc_.name, liste_, k_)))
            nr += 1
        check("… jede Zeile der Lasttabelle findet ihre Last wieder (_lastzeile kehrt _lastzeiger um)",
              len(paare) >= 2 and all(a == b for a, b in paare), str(paare))
        vorher = len(m.load_cases[fall].nodal_loads)
        FRAGEN.clear()
        ausloesen(w, app, rechtsklick(w, app, P, welt=P), "Löschen")
        check("… „Löschen“: eine Rückfrage, eine Knotenlast weniger",
              len(FRAGEN) == 1 and len(w.model.load_cases[fall].nodal_loads) == vorher - 1, f"{FRAGEN}")
    finally:
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


SICHT = ["Isometrisch", "Ansicht von +X", "Ansicht von -X", "Ansicht von +Y", "Ansicht von -Y",
         "Ansicht von +Z (Draufsicht)", "Ansicht von -Z (Untersicht)", "Rückseite (180°)", "Zoom alles",
         "Vorherige Sicht", "Alles zeigen", "Darstellung", "Nummern"]


def test_ins_leere():
    w, app = _fenster()
    m, n = _modell(w, app)
    menu = rechtsklick(w, app, LEER)
    check("ins Leere, nichts gewählt: nur Sicht und Zoom, ohne Titel", texte(menu) == SICHT and _titel(menu) == "",
          str(texte(menu)))
    check("… „Vorherige Sicht“ und „Alles zeigen“ gesperrt, solange nichts ausgeblendet ist",
          not eintrag(menu, "Vorherige Sicht").isEnabled() and not eintrag(menu, "Alles zeigen").isEnabled())
    kam = w.plotter.renderer.GetActiveCamera
    for text, r in (("Ansicht von +X", "+x"), ("Ansicht von -X", "-x"), ("Ansicht von +Y", "+y"),
                    ("Ansicht von -Y", "-y"), ("Ansicht von +Z (Draufsicht)", "+z"),
                    ("Ansicht von -Z (Untersicht)", "-z")):
        ausloesen(w, app, rechtsklick(w, app, LEER), text)
        d = np.asarray(kam().GetDirectionOfProjection(), float)
        check(f"… „{text}“ dreht die Kamera", np.allclose(d, w.BLICKRICHTUNGEN[r][0], atol=1e-6), str(np.round(d, 3)))
    ausloesen(w, app, rechtsklick(w, app, LEER), "Isometrisch")
    d = np.asarray(kam().GetDirectionOfProjection(), float)
    check("… „Isometrisch“: schräg von oben", np.allclose(np.abs(d), 1 / np.sqrt(3), atol=1e-6) and d[2] < 0,
          str(np.round(d, 3)))
    ausloesen(w, app, rechtsklick(w, app, LEER), "Rückseite (180°)")
    d2 = np.asarray(kam().GetDirectionOfProjection(), float)
    check("… „Rückseite (180°)“ kehrt die Blickrichtung um", np.allclose(d2, -d, atol=1e-6), str(np.round(d2, 3)))
    zaehler = []
    alt = w.zoom_alles
    w.zoom_alles = lambda: (zaehler.append(1), alt())
    try:
        ausloesen(w, app, rechtsklick(w, app, LEER), "Zoom alles")
    finally:
        w.zoom_alles = alt
    check("… „Zoom alles“ passt alles ein", zaehler == [1], str(zaehler))
    # Sicht: ausblenden, alles zeigen, vorherige Sicht
    w.sel_staebe[:] = ["S4"]
    w.auswahl_ausblenden()
    app.processEvents()
    menu = rechtsklick(w, app, LEER)
    check("… nach dem Ausblenden: „Vorherige Sicht“ und „Alles zeigen“ frei",
          eintrag(menu, "Vorherige Sicht").isEnabled() and eintrag(menu, "Alles zeigen").isEnabled())
    weg = {k: set(v) for k, v in w.versteckt.items()}
    ausloesen(w, app, menu, "Alles zeigen")
    check("… „Alles zeigen“ holt alles zurück", not any(w.versteckt.values()))
    ausloesen(w, app, rechtsklick(w, app, LEER), "Vorherige Sicht")
    check("… „Vorherige Sicht“ nimmt das zurück", w.versteckt == weg)
    w.alles_zeigen()
    # Darstellung und Nummern als Untermenue
    from statik3d.gui import viewport as vp
    dm = eintrag(rechtsklick(w, app, LEER), "Darstellung").menu()
    name = list(vp.DARSTELLUNGEN)[-1]
    a = next((x for x in dm.actions() if x.text().endswith(name)), None)
    if a is not None:
        a.trigger()
        app.processEvents()
    check(f"… Untermenü „Darstellung“: „{name}“ stellt die Darstellung um", w.darstellung == name, w.darstellung)
    w.darstellung_setzen("Voll")
    nm = eintrag(rechtsklick(w, app, LEER), "Nummern").menu()
    art = next(iter(w.NUMMERN))
    vorher = w.act_nummern[art].isChecked()
    next(x for x in nm.actions() if x.text() == art).trigger()
    app.processEvents()
    check(f"… Untermenü „Nummern“: „{art}“ schaltet um", w.act_nummern[art].isChecked() != vorher)
    w.nummern_aus()
    # mit Auswahl: dazu ihre Befehle, die Auswahl bleibt
    w.selection = np.array([n["K1"]], int)
    w.sel_staebe[:] = ["S4"]
    w._auswahl_nachziehen()
    menu = rechtsklick(w, app, LEER)
    t = texte(menu)
    check("ins Leere mit Auswahl: die Auswahl bleibt (der Rechtsklick hebt sie nicht auf)",
          _knoten(w) == [n["K1"]] and w.sel_staebe == ["S4"], f"{_knoten(w)} {w.sel_staebe}")
    check("… zuerst Sicht und Zoom, dann die Auswahl mit ihren Befehlen und „Auswahl löschen“, „Auswahl aufheben“",
          t[:len(SICHT)] == SICHT and t[len(SICHT)] == "Auswahl: 1 Knoten, 1 Stab"
          and t[len(SICHT) + 1:len(SICHT) + 3] == ["Selektiertes anzeigen", "Selektiertes ausblenden"]
          and t[-2:] == ["Auswahl löschen", "Auswahl aufheben"], str(t))
    ausloesen(w, app, menu, "Auswahl aufheben")
    check("… „Auswahl aufheben“ hebt sie auf", not len(w.selection) and not w.sel_staebe)
    w.selection = np.array([n["K6"]], int)
    w._auswahl_nachziehen()
    nn = m.nn
    FRAGEN.clear()
    ausloesen(w, app, rechtsklick(w, app, LEER), "Auswahl löschen")
    check("… „Auswahl löschen“ löscht sie wie Entf: eine Rückfrage, K6 ist weg",
          len(FRAGEN) == 1 and FRAGEN[0].startswith("1 Knoten wirklich löschen?") and w.model.nn == nn - 1,
          f"{FRAGEN} {nn} -> {w.model.nn}")
    _leeren(w, app)


def test_auswahl_innen_aussen():
    w, app = _fenster()
    m, n = _modell(w, app)
    k1, k2, k3 = n["K1"], n["K2"], n["K3"]
    ka.klick(w, app, m.nodes[k1])
    ka.klick(w, app, m.nodes[k2], strg=True)
    menu = rechtsklick(w, app, m.nodes[k2])
    t = texte(menu)
    check("innerhalb der Auswahl (K1, K2): Rechtsklick auf K2 lässt die Auswahl stehen",
          _knoten(w) == sorted([k1, k2]), str(_knoten(w)))
    check("… das Menü nennt K2 und bietet dazu die Befehle der ganzen Auswahl",
          _titel(menu) == f"Knoten K{k2}" and "Auswahl: 2 Knoten" in t and "Selektiertes anzeigen" in t
          and t[-2:] == ["Auswahl löschen", "Auswahl aufheben"], str(t))
    ausloesen(w, app, menu, "Bearbeiten…")
    check("… „Bearbeiten…“ öffnet die Maske von K2, die Auswahl bleibt K1, K2",
          _maske(w) == f"Knoten K{k2}" and _knoten(w) == sorted([k1, k2]), f"{_maske(w)!r} {_knoten(w)}")
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k2]), "Knotenlast…")
    check("… „Knotenlast…“ gilt dem Knoten: danach ist nur K2 gewählt, die Maske offen",
          _maske(w) == "Knotenlast" and _knoten(w) == [k2], f"{_maske(w)!r} {_knoten(w)}")
    w.maskenrand.schliessen()
    menu = rechtsklick(w, app, m.nodes[k3])
    check("außerhalb der Auswahl: Rechtsklick auf K3 ersetzt sie (nur K3), ohne die Befehle einer Auswahl",
          _knoten(w) == [k3] and "Auswahl löschen" not in texte(menu) and _titel(menu) == f"Knoten K{k3}",
          f"{_knoten(w)} {texte(menu)}")
    # gemischte Auswahl: Knoten K1 und Stab S4, Rechtsklick auf S4
    _leeren(w, app)
    w.auswahlart_setzen("Stab")
    try:
        w.selection = np.array([k1], int)
        w.sel_staebe[:] = ["S4"]
        w._auswahl_nachziehen()
        menu = rechtsklick(w, app, ka._mitte(m, n["K4"], n["K5"]))
        check("gemischte Auswahl (K1, S4), Rechtsklick auf S4: sie bleibt, das Menü nennt beides",
              _knoten(w) == [k1] and w.sel_staebe == ["S4"] and _titel(menu) == "Stab S4"
              and "Auswahl: 1 Knoten, 1 Stab" in texte(menu), f"{_knoten(w)} {w.sel_staebe} {texte(menu)}")
    finally:
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_fensterecke():
    from PySide6 import QtCore
    w, app = _fenster()
    m, n = _modell(w, app)
    T0 = QtCore.Qt.NoModifier
    w.selection = np.array([n["K4"]], int)
    p1 = ka._zeiger(w, np.asarray(m.nodes[n["K0"]], float) + [-1, -1, 0])
    p2 = ka._zeiger(w, np.asarray(m.nodes[n["K2"]], float) + [1, 1, 0])
    ka._maus(w, app, QtCore.QEvent.MouseButtonPress, p1, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, T0)
    for q in (QtCore.QPointF(0.5 * (p1.x() + p2.x()), 0.5 * (p1.y() + p2.y())), p2):
        ka._maus(w, app, QtCore.QEvent.MouseMove, q, QtCore.Qt.NoButton, QtCore.Qt.LeftButton, T0)
    ecke = w._fenster_ecke is not None
    vorher = len(MENUES)
    with _Fang():
        ka._maus(w, app, QtCore.QEvent.MouseButtonPress, p2, QtCore.Qt.RightButton,
                 QtCore.Qt.LeftButton | QtCore.Qt.RightButton, T0)
        ka._maus(w, app, QtCore.QEvent.MouseButtonRelease, p2, QtCore.Qt.RightButton, QtCore.Qt.LeftButton, T0)
        ka._maus(w, app, QtCore.QEvent.MouseButtonRelease, p2, QtCore.Qt.LeftButton, QtCore.Qt.NoButton, T0)
    erwartet = sorted([n["K0"], n["K1"], n["K2"]])
    check("zweite Fensterecke per Rechtsklick: das Fenster wählt K0, K1, K2 (ersetzt), kein Menü",
          ecke and _knoten(w) == erwartet and w._fenster_ecke is None and len(MENUES) == vorher,
          f"Ecke {ecke}, {_knoten(w)}, {len(MENUES) - vorher} Menüs")
    # dieselbe Ecke ueber den Menueweg selbst (_viewport_menu): auch dort kein Menue
    w.selection = np.array([n["K4"]], int)
    w._fenster_beginnen(QtCore.QPoint(int(p1.x()), int(p1.y())))
    vorher = len(MENUES)
    with _Fang():
        w._viewport_menu(QtCore.QPoint(int(p2.x()), int(p2.y())))
        app.processEvents()
    check("… über _viewport_menu ebenso: Fenster abgeschlossen, kein Menü",
          _knoten(w) == erwartet and w._fenster_ecke is None and len(MENUES) == vorher,
          f"{_knoten(w)} {len(MENUES) - vorher}")
    _leeren(w, app)


def test_geaenderte_maske():
    w, app = _fenster()
    m, n = _modell(w, app)
    k1, k2, k3, k4 = n["K1"], n["K2"], n["K3"], n["K4"]

    def knotenlast_geaendert(fz):
        w._set_selection([k3, k4])
        w.maske_knotenlast()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("Fz", fz)
        app.processEvents()
        return mk

    mk = knotenlast_geaendert(-12.0)
    fall = mk.werte().get("fall")
    vorher = len(m.load_cases[fall].nodal_loads)
    menu = rechtsklick(w, app, m.nodes[k1])
    check("geänderte Maske, Rechtsklick auf K1 (außerhalb): das Menü kommt, die Auswahl bleibt K3, K4, keine Leiste",
          _titel(menu) == f"Knoten K{k1}" and _knoten(w) == sorted([k3, k4]) and _leiste(w) is None,
          f"{_titel(menu)!r} {_knoten(w)}")
    ausloesen(w, app, menu, "Bearbeiten…")
    check("… „Bearbeiten…“ hält an der Leiste; Auswahl und Maske bleiben",
          _leiste(w) is not None and _knoten(w) == sorted([k3, k4]) and w.maskenrand.maske is mk,
          f"{_knoten(w)} {_maske(w)!r}")
    _druecken(w, app, "Übernehmen")
    dazu = sorted(int(x.node) for x in m.load_cases[fall].nodal_loads[vorher:])
    check("… „Übernehmen“: die Last kommt auf K3 und K4, danach ist K1 gewählt und seine Maske offen",
          dazu == sorted([k3, k4]) and _knoten(w) == [k1] and _maske(w) == f"Knoten K{k1}",
          f"{dazu} {_knoten(w)} {_maske(w)!r}")
    # Eintraege ohne Maske laufen gleich und stellen die Auswahl nicht um
    _leeren(w, app)
    mk = knotenlast_geaendert(-13.0)
    vorher = len(m.load_cases[fall].nodal_loads)
    _vorher_woanders(w)
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k2]), "In der Tabelle zeigen")
    check("… „In der Tabelle zeigen“ läuft ohne Leiste und lässt die Auswahl: K2 markiert, K3, K4 gewählt",
          _leiste(w) is None and _knoten(w) == sorted([k3, k4]) and w.aktive_tabelle() is w.tbl_knoten
          and [int(x) for x in _markiert(w.tbl_knoten)] == [k2] and w.maskenrand.maske is mk,
          f"{_knoten(w)} {_markiert(w.tbl_knoten)}")
    ausloesen(w, app, rechtsklick(w, app, m.nodes[k2]), "Knotenlast…")
    check("… „Knotenlast…“ hält an der Leiste, bevor die Auswahl umgestellt wird",
          _leiste(w) is not None and _knoten(w) == sorted([k3, k4]) and w.maskenrand.maske is mk, str(_knoten(w)))
    _druecken(w, app, "Verwerfen")
    check("… „Verwerfen“: keine Last, K2 gewählt, eine neue Maske „Knotenlast“",
          len(m.load_cases[fall].nodal_loads) == vorher and _knoten(w) == [k2] and _maske(w) == "Knotenlast"
          and w.maskenrand.maske is not mk, f"{_knoten(w)} {_maske(w)!r}")
    # innerhalb der Auswahl: auch dort haelt „Bearbeiten…“
    _leeren(w, app)
    mk = knotenlast_geaendert(-14.0)
    menu = rechtsklick(w, app, m.nodes[k3])
    check("… Rechtsklick auf K3 (in der Auswahl): Auswahl bleibt, das Menü bietet sie mit an",
          _knoten(w) == sorted([k3, k4]) and "Auswahl: 2 Knoten" in texte(menu), str(texte(menu)))
    ausloesen(w, app, menu, "Bearbeiten…")
    leiste = _leiste(w) is not None
    _druecken(w, app, "Verwerfen")
    check("… „Bearbeiten…“ hält auch hier; nach „Verwerfen“ die Maske von K3, die Auswahl bleibt K3, K4",
          leiste and _maske(w) == f"Knoten K{k3}" and _knoten(w) == sorted([k3, k4]), f"{_maske(w)!r} {_knoten(w)}")
    # Loeschen fragt selbst und nennt die Maske, ohne Leiste
    _leeren(w, app)
    mk = knotenlast_geaendert(-15.0)
    FRAGEN.clear()
    _antwort(w, False)
    try:
        ausloesen(w, app, rechtsklick(w, app, m.nodes[n["K6"]]), "Löschen")
    finally:
        _antwort(w, True)
    check("… „Löschen“ hält nicht an der Leiste, fragt selbst und nennt die Maske; „Nein“ lässt alles stehen",
          _leiste(w) is None and len(FRAGEN) == 1 and "nicht übernommene Änderungen" in FRAGEN[0]
          and w.maskenrand.maske is mk and _knoten(w) == sorted([k3, k4]), f"{FRAGEN}")
    _leeren(w, app)


def test_rechnung():
    w, app = _fenster()
    m, n = _modell(w, app)
    w._set_selection([n["K1"]])
    w._rechnet_gerade = True
    try:
        menu = rechtsklick(w, app, m.nodes[n["K2"]])
        t = texte(menu)
        check("während einer Rechnung, Rechtsklick auf K2: nur Sicht und Zoom, die Auswahl bleibt K1",
              t == ["Rechnung läuft – nur Sicht und Zoom"] + SICHT and _knoten(w) == [n["K1"]], f"{t} {_knoten(w)}")
        w.auswahlart_setzen("Lager")
        menu = rechtsklick(w, app, m.nodes[n["K0"]], welt=m.nodes[n["K0"]])
        check("… ebenso auf einem Lager, ohne die Befehle der Auswahl", texte(menu) == t and not w.sel_lager,
              str(texte(menu)))
        zaehler = []
        alt = w.zoom_alles
        w.zoom_alles = lambda: (zaehler.append(1), alt())
        try:
            ausloesen(w, app, rechtsklick(w, app, LEER), "Zoom alles")
        finally:
            w.zoom_alles = alt
        check("… „Zoom alles“ wirkt auch während der Rechnung", zaehler == [1])
    finally:
        w._rechnet_gerade = False
        w.auswahlart_setzen("Knoten")
    _leeren(w, app)


def test_handbuch():
    from tests.handbuch import absatz
    t = absatz("**Rechtsklick in der Ansicht.**")
    check("Handbuch: Rechtsklick auf ein Objekt und ins Leere, Stand bis zum 03.10.2026",
          "Bis zum 03.10.2026" in t and "Im Baum zeigen" in t and "Zoom alles" in t, t[:100])
    check("… die Auswahl beim Rechtsklick und die Leiste bei einer geänderten Maske",
          "bleibt die Auswahl" in t and "Übernehmen | Verwerfen" in t and "Rechnung" in t, t[-200:])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_knoten, test_stab, test_linie, test_flaeche_volumen, test_element, test_lager, test_last,
              test_ins_leere, test_auswahl_innen_aussen, test_fensterecke, test_geaenderte_maske, test_rechnung,
              test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    if MODAL:
        print(f"modale Fenster (abgefangen): {MODAL[:6]}")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    # os._exit: kein Schliessen des Fensters, keine Rueckfrage „Ungespeicherte Änderungen“
    rc = main()
    os._exit(rc)
