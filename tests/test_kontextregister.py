"""
Kontextregister „Auswahl“ (Teilpaket 12c des Oberflaechenplans, 03.10.2026).

Stand davor (am Quelltext und mit dem Hauptfenster offscreen gemessen):

* das Register erschien nur, wenn **Knoten** gewaehlt waren; wer Staebe,
  Linien, Flaechen, Volumen, Elemente, Lager oder Lasten waehlte, bekam keines
  - dabei verspricht der Hinweis von „Querschnitt zuweisen…“ es fuer Stab,
  Flaeche und Netz;
* die drei Auswahlfelder von „Zuweisen“ trugen nur einen Tooltip, keine
  sichtbare Beschriftung; nach jedem refresh_all verlor das Feld „Dicke“ seinen
  leeren Eintrag und stand auf der ersten Dicke - „Zuweisen“ haette sie allen
  gewaehlten Schalen gegeben;
* nach Neu, Beispiel, Oeffnen, Import, Rueckgaengig und Wiederholen blieb das
  Register mit der Zahl des vorigen Stands stehen („Auswahl: 4 Knoten“ ueber
  einem leeren Modell); lag es vorn, sprang die Ansicht auf den Nachbarn
  „Extras“; wechselte nur die Zahl, wurde das Register neu gebaut und lag danach
  nicht mehr vorn;
* die Befehle des Registers galten nur fuer Knoten.

Geprueft wird mit dem echten Hauptfenster (offscreen):

* der Reiter nennt jede Auswahlart mit Anzahl und richtiger Einzahl oder
  Mehrzahl; bei gemischter Auswahl steht die Zahl der Objekte im Reiter und die
  Aufstellung im Tooltip und in der Gruppe „Gewählt“ (die Registerzeile hat bei
  1280 px nur Platz fuer rund 21 Zeichen, gemessen: siehe unten);
* die Registerzeile bekommt bei 1280 und 1366 px auch mit den laengsten Reitern
  keine Rollpfeile;
* jedes Auswahlfeld des Registers hat eine sichtbare Beschriftung (QLabel mit
  Text, dem Feld als Buddy zugeordnet); „Dicke“ behaelt „unverändert“;
* „Zuweisen“ wirkt auch auf die Elemente gewaehlter Staebe;
* das Register zeigt nur Befehle, die zur Auswahl passen;
* nur die Zahl wechselt: dasselbe Register, bleibt vorn; wechselt die Art:
  neues Register, bleibt vorn;
* nach Neu, Beispiel, Oeffnen, Import, Rueckgaengig, Wiederholen, Loeschen und
  „Alles deselektieren“ ist das Register weg und das zuletzt benutzte Register
  liegt vorn (nicht der Nachbar).

Aufruf:  python -m tests.test_kontextregister
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Die Breitenpruefung braucht die Schrift des Desktops (siehe
# tests/test_glasleiste_ribbon.py): offscreen findet Qt unter Windows sonst keine
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                                         "Fonts"))
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_kontext_"), "einstellungen.json")
TMP = tempfile.mkdtemp(prefix="statik3d_kontext_modelle_")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}

#: wie in tests/test_glasleiste_ribbon.py: Anteil der Breite, den die Reiter
#: zusammen hoechstens brauchen duerfen (Desktop-Schrift bis 2,9 % breiter)
RESERVE = 0.97
LISTEN = ("sel_linien", "sel_staebe", "sel_flaechen", "sel_koerper", "sel_elemente",
          "sel_lager", "sel_lasten")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: (w.fehler_liste.append(str(msg)),
                                    w.log.appendPlainText("FEHLER: " + str(msg)))
    w.load_example("hall")
    app.processEvents()
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(n=4):
    from PySide6 import QtWidgets
    for _ in range(n):
        QtWidgets.QApplication.processEvents()


def _leeren(w):
    """Auswahl leer - ohne den Weg, den die Pruefung gerade misst."""
    w.selection = np.array([], dtype=int)
    for name in LISTEN:
        getattr(w, name).clear()
    w._auswahl_register()
    _ruhe()


def _waehlen(w, knoten=0, **listen):
    """Auswahl setzen und das Register nachziehen, wie es jeder Klick tut."""
    _leeren(w)
    w.selection = np.arange(knoten, dtype=int)
    for art, werte in listen.items():
        getattr(w, "sel_" + art)[:] = list(werte)
    w._auswahl_register()
    _ruhe()


def _reiter(w) -> str:
    """Text des Kontext-Reiters, leer ohne Register."""
    rb = w.ribbon
    if rb._kontext is None:
        return ""
    return rb.tabs.tabText(rb.tabs.indexOf(rb._kontext))


def _register_namen(w) -> list:
    t = w.ribbon.tabs
    return [t.tabText(i) for i in range(t.count())]


def _befehle(w) -> list:
    return [b.text for b in w.ribbon.befehle if b.register.startswith("Auswahl")]


def _vorn(w) -> str:
    t = w.ribbon.tabs
    return t.tabText(t.currentIndex())


# --------------------------------------------------------------------------
def test_reitertext_je_art():
    w, app = _fenster()
    faelle = [
        ("Knoten", 1, dict(knoten=1), "Auswahl: 1 Knoten"),
        ("Knoten", 3, dict(knoten=3), "Auswahl: 3 Knoten"),
        ("Linie", 1, dict(linien=["L1"]), "Auswahl: 1 Linie"),
        ("Linien", 2, dict(linien=["L1", "L2"]), "Auswahl: 2 Linien"),
        ("Stab", 1, dict(staebe=["S1"]), "Auswahl: 1 Stab"),
        ("Stäbe", 2, dict(staebe=["S1", "S2"]), "Auswahl: 2 Stäbe"),
        ("Fläche", 1, dict(flaechen=["F1"]), "Auswahl: 1 Fläche"),
        ("Flächen", 2, dict(flaechen=["F1", "F2"]), "Auswahl: 2 Flächen"),
        ("Volumen", 1, dict(koerper=["V1"]), "Auswahl: 1 Volumen"),
        ("Volumen", 2, dict(koerper=["V1", "V2"]), "Auswahl: 2 Volumen"),
        ("Element", 1, dict(elemente=[4]), "Auswahl: 1 Element"),
        ("Elemente", 2, dict(elemente=[4, 5]), "Auswahl: 2 Elemente"),
        ("Lager", 1, dict(lager=[("lager", 0)]), "Auswahl: 1 Lager"),
        ("Lager", 2, dict(lager=[("lager", 0), ("lager", 1)]), "Auswahl: 2 Lager"),
        ("Last", 1, dict(lasten=[("G", "knoten", 0)]), "Auswahl: 1 Last"),
        ("Lasten", 2, dict(lasten=[("G", "knoten", 0), ("G", "knoten", 1)]), "Auswahl: 2 Lasten"),
    ]
    for art, n, auswahl, erwartet in faelle:
        _waehlen(w, **auswahl)
        check(f"Reiter für {n} {art}: „{erwartet}“", _reiter(w) == erwartet,
              f"{_reiter(w)!r} {_register_namen(w)[-2:]}")
    _leeren(w)
    check("ohne Auswahl kein Register", w.ribbon._kontext is None and "Auswahl" not in " ".join(_register_namen(w)))


def test_reitertext_gemischt():
    from PySide6 import QtWidgets
    w, app = _fenster()
    _waehlen(w, knoten=1, staebe=["S1", "S2", "S3"])
    i = w.ribbon.tabs.indexOf(w.ribbon._kontext)
    tip = w.ribbon.tabs.tabToolTip(i)
    check("gemischt (1 Knoten, 3 Stäbe): der Reiter nennt die Zahl der Objekte",
          _reiter(w) == "Auswahl: 4 Objekte", repr(_reiter(w)))
    check("… der Tooltip des Reiters nennt jede Art mit Anzahl", "1 Knoten, 3 Stäbe" in tip, repr(tip))
    gew = w.ribbon._kontext.findChild(QtWidgets.QLabel, "kontextgewaehlt")
    check("… die Gruppe „Gewählt“ im Register nennt sie ebenfalls",
          gew is not None and gew.text() == "1 Knoten, 3 Stäbe", repr(gew.text() if gew else None))
    _waehlen(w, knoten=2, linien=["L1"], staebe=["S1"], flaechen=["F1", "F2"], koerper=["V1"],
             elemente=[1, 2, 3], lager=[("lager", 0)], lasten=[("G", "knoten", 0)])
    gew = w.ribbon._kontext.findChild(QtWidgets.QLabel, "kontextgewaehlt")
    erwartet = ("2 Knoten, 1 Linie, 1 Stab, 2 Flächen, 1 Volumen, 3 Elemente, 1 Lager, 1 Last")
    check("alle acht Arten zugleich: die Aufstellung nennt jede, Einzahl und Mehrzahl stimmen",
          gew.text() == erwartet, repr(gew.text()))
    check("… der Reiter bleibt kurz: „Auswahl: 12 Objekte“", _reiter(w) == "Auswahl: 12 Objekte", repr(_reiter(w)))
    # eine einzige Art, aber zu viele Ziffern fuer den Reiter: die Zahl bleibt
    _waehlen(w, elemente=list(range(1234)))
    check("1234 Elemente passen nicht mehr als Wort in den Reiter: Zahl der Objekte",
          _reiter(w) == "Auswahl: 1234 Objekte", repr(_reiter(w)))
    _leeren(w)


def test_reiter_laenge():
    from statik3d.gui.main import MainWindow
    langste = 0
    schlecht = []
    for art, ein, mehr in (("knoten", "Knoten", "Knoten"),) + MainWindow.AUSWAHL_LISTEN:
        for n in (1, 2, 9, 12, 99, 123, 999, 1234, 9999, 12345, 123456, 999999):
            reiter, _lang = MainWindow._auswahl_texte([(art, n, ein, mehr)])
            langste = max(langste, len(reiter))
            if len(reiter) > MainWindow.REITER_ZEICHEN or not reiter.startswith("Auswahl: "):
                schlecht.append(reiter)
    check(f"kein Reiter über {MainWindow.REITER_ZEICHEN} Zeichen, bei jeder Art und jeder Zahl bis 999 999",
          not schlecht, f"längster {langste} Zeichen; {schlecht[:3]}")


def _breite_messen(w, breite, hoehe):
    from PySide6 import QtWidgets
    w.resize(breite, hoehe)
    _ruhe()
    tb = w.ribbon.tabs.tabBar()
    summe = sum(tb.tabRect(i).width() for i in range(tb.count()))
    pfeile = [k for k in tb.findChildren(QtWidgets.QToolButton) if k.isVisible()]
    return summe, tb.width(), len(pfeile)


def test_registerzeile_ohne_rollpfeile():
    from PySide6 import QtGui, QtWidgets
    w, app = _fenster()
    knopf = w.ribbon.findChildren(QtWidgets.QToolButton)[0]
    if not sys.platform.startswith("win"):
        print("Registerzeile: Schriftmessung nur unter Windows (Segoe UI) - übersprungen")
        return
    if not check("Schrift wie auf dem Desktop (Segoe UI) - sonst misst die Prüfung Kästen",
                 QtGui.QFontInfo(knopf.font()).family() == "Segoe UI", "QT_QPA_FONTDIR fehlt?"):
        return
    from statik3d.gui.main import MainWindow
    # Ende-zu-Ende: echte Auswahlen, auch riesige (123 456 Knoten wie ein Select-all
    # am Drehlager) und die gemischte
    lagen = [dict(knoten=123456), dict(staebe=list(range(999))), dict(elemente=list(range(1234))),
             dict(koerper=[f"V{i}" for i in range(9999)]),
             dict(knoten=88, staebe=["S1"], flaechen=["F1"])]
    # die Regel selbst: jede Art mit jeder Zahl, die Ziffern der breitesten Zeichen
    # (gemessen sind 8 und 9 die breitesten, 1 die schmalste) - dazu gemischte Zahlen
    texte = []
    for art, ein, mehr in (("knoten", "Knoten", "Knoten"),) + MainWindow.AUSWAHL_LISTEN:
        for ziffer in "189":
            for stellen in range(1, 8):
                n = int(ziffer * stellen)
                texte.append(MainWindow._auswahl_texte([(art, n, ein, mehr)])[0])
    for n in (2, 9, 12, 99, 888, 8888, 88888, 888888):
        texte.append(MainWindow._auswahl_texte([("knoten", n, "Knoten", "Knoten"),
                                                ("staebe", 1, "Stab", "Stäbe")])[0])
    texte = sorted(set(texte), key=len)
    for breite, hoehe in ((1366, 768), (1280, 720)):
        schlecht = []
        breiteste = (0, "")
        for lage in lagen:
            _waehlen(w, **lage)
            summe, zeile, pfeile = _breite_messen(w, breite, hoehe)
            breiteste = max(breiteste, (summe, _reiter(w)))
            if summe > RESERVE * zeile or pfeile:
                schlecht.append(f"{_reiter(w)}: {summe} px von {zeile}, {pfeile} Pfeile")
        _waehlen(w, knoten=3)
        for t in texte:
            w.ribbon.kontext_benennen(t)
            summe, zeile, pfeile = _breite_messen(w, breite, hoehe)
            breiteste = max(breiteste, (summe, t))
            if summe > RESERVE * zeile or pfeile:
                schlecht.append(f"{t}: {summe} px von {zeile}, {pfeile} Pfeile")
        check(f"{breite} px: die Registerzeile passt mit jedem Reiter (keine Rollpfeile, {RESERVE:.0%})",
              not schlecht, f"{len(texte) + len(lagen)} Reiter, breitester {breiteste[1]!r} {breiteste[0]} "
                            f"von {int(RESERVE * zeile)} px; " + "; ".join(schlecht)[:200])
    w.resize(1600, 980)
    _leeren(w)


def test_felder_beschriftet():
    from PySide6 import QtWidgets
    w, app = _fenster()
    _waehlen(w, knoten=3)
    reg = w.ribbon._kontext
    felder = [("Querschnitt", w.cb_assign_sec), ("Werkstoff", w.cb_assign_mat), ("Dicke", w.cb_assign_shell)]
    labels = reg.findChildren(QtWidgets.QLabel)
    for text, cb in felder:
        passend = [lb for lb in labels if lb.buddy() is cb]
        check(f"Auswahlfeld „{text}“ hat eine sichtbare Beschriftung als Buddy",
              len(passend) == 1 and passend[0].text() == text and passend[0].isVisibleTo(reg)
              and cb.isVisibleTo(reg), str([(lb.text(), lb.buddy() is cb) for lb in labels]))
    # keine Beschriftung steht ueber dem Rand der Gruppe oder wird gekuerzt
    from PySide6 import QtGui
    gekuerzt = [lb.text() for lb in labels
                if lb.isVisibleTo(reg) and not lb.wordWrap()
                and QtGui.QFontMetrics(lb.font()).horizontalAdvance(lb.text()) > lb.width()]
    check("… keine Beschriftung ist gekürzt", not gekuerzt, str(gekuerzt))
    check("Feld „Dicke“ beginnt mit „unverändert“ (kein leeres Feld)",
          w.cb_assign_shell.itemText(0) == "unverändert" and w.cb_assign_shell.currentIndex() == 0,
          str([w.cb_assign_shell.itemText(i) for i in range(w.cb_assign_shell.count())]))
    w.refresh_all()
    _ruhe()
    check("… und behält es nach refresh_all (Befund: danach stand die erste Dicke da)",
          w.cb_assign_shell.itemText(0) == "unverändert" and w.cb_assign_shell.currentIndex() == 0,
          str([w.cb_assign_shell.itemText(i) for i in range(w.cb_assign_shell.count())]))
    _leeren(w)


def test_zuweisen_auf_staebe():
    w, app = _fenster()
    m = w.model
    riegel = [int(e) for e in m.members["Riegel"].elements]
    stiel = [int(e) for e in m.members["Stiel links"].elements]
    vorher = {i: m.elements[i].sec for i in range(len(m.elements))}
    check("Vorbereitung: Riegel IPE 500, Stiel HEB 300",
          {vorher[i] for i in riegel} == {"IPE 500"} and {vorher[i] for i in stiel} == {"HEB 300"})
    _waehlen(w, staebe=["Riegel"])
    check("ein gewählter Stab: Register „Auswahl: 1 Stab“ mit „Zuweisen“",
          _reiter(w) == "Auswahl: 1 Stab" and "Zuweisen" in _befehle(w), f"{_reiter(w)!r} {_befehle(w)}")
    w.cb_assign_sec.setCurrentText("HEB 300")
    w.fehler_liste.clear()
    w.assign_props()
    _ruhe()
    nachher = {i: m.elements[i].sec for i in range(len(m.elements))}
    check("„Zuweisen“ gibt den Elementen des Stabs den Querschnitt, die übrigen bleiben",
          {nachher[i] for i in riegel} == {"HEB 300"}
          and all(nachher[i] == vorher[i] for i in range(len(m.elements)) if i not in riegel)
          and not w.fehler_liste, f"{ {nachher[i] for i in riegel} } {w.fehler_liste}")
    w.undo()
    _ruhe()
    m = w.model                      # Rueckgaengig setzt eine Kopie des Modells ein
    check("Rückgängig nimmt die Zuweisung zurück", {m.elements[i].sec for i in riegel} == {"IPE 500"})
    # Knoten wie bisher: alle Elemente, deren Knoten gewaehlt sind
    e0 = m.elements[stiel[0]]
    _waehlen(w)
    w.selection = np.array(sorted(int(n) for n in e0.nodes), dtype=int)
    w._auswahl_register()
    w.cb_assign_sec.setCurrentText("IPE 500")
    w.assign_props()
    _ruhe()
    check("Knoten gewählt: „Zuweisen“ wirkt wie bisher auf das Element zwischen ihnen",
          m.elements[stiel[0]].sec == "IPE 500" and not w.fehler_liste, str(w.fehler_liste))
    w.undo()
    _ruhe()
    _waehlen(w, staebe=["Riegel"])
    w.fehler_liste.clear()
    w.ribbon.zeigen("Start")
    w.zuweisen_zeigen("querschnitt")
    check("„Querschnitt zuweisen…“ mit gewähltem Stab: kein Hinweis, Register vorn, Feld hat den Fokus",
          not w.fehler_liste and w.ribbon.tabs.currentWidget() is w.ribbon._kontext, str(w.fehler_liste))
    _waehlen(w, linien=["L1"])
    w.fehler_liste.clear()
    w.zuweisen_zeigen("querschnitt")
    check("… mit gewählter Linie: ein Hinweis statt stummem Befehl (das Register hat kein Feld dafür)",
          len(w.fehler_liste) == 1 and "wählen" in w.fehler_liste[0], str(w.fehler_liste))
    _leeren(w)
    w.fehler_liste.clear()
    w.zuweisen_zeigen("querschnitt")
    check("… ohne jede Auswahl: der Hinweis bleibt", len(w.fehler_liste) == 1, str(w.fehler_liste))


def test_befehle_je_auswahl():
    w, app = _fenster()
    _waehlen(w, knoten=3)
    knoten = set(_befehle(w))
    check("Knoten: alle Befehle wie bisher",
          {"Zuweisen", "Gelenke", "Elemente löschen", "Knoten löschen", "Lager", "Last",
           "Alles deselektieren", "Auswahl umkehren"} <= knoten, str(sorted(knoten)))
    _waehlen(w, staebe=["Riegel"])
    staebe = set(_befehle(w))
    check("Stäbe: Zuweisen und Gelenke, nichts, was nur Knoten meint",
          {"Zuweisen", "Gelenke", "Alles deselektieren"} <= staebe
          and not ({"Lager", "Last", "Knoten löschen", "Elemente löschen", "Auswahl umkehren"} & staebe),
          str(sorted(staebe)))
    _waehlen(w, flaechen=["F1"])
    flaechen = set(_befehle(w))
    check("Flächen: Zuweisen, kein Gelenk (Gelenke sind Stabsache)",
          "Zuweisen" in flaechen and "Gelenke" not in flaechen and "Lager" not in flaechen, str(sorted(flaechen)))
    _waehlen(w, linien=["L1"])
    linien = set(_befehle(w))
    check("Linien: nur „Alles deselektieren“ - nichts, was ins Leere liefe",
          linien == {"Alles deselektieren"}, str(sorted(linien)))
    _waehlen(w, lager=[("lager", 0)])
    check("Lager: ebenso", set(_befehle(w)) == {"Alles deselektieren"}, str(sorted(_befehle(w))))
    _leeren(w)
    check("ohne Auswahl sind die Befehle abgemeldet", not _befehle(w))


def test_register_bleibt():
    w, app = _fenster()
    w.ribbon.zeigen("Geometrie")
    _waehlen(w, knoten=3)
    reg = w.ribbon._kontext
    w.ribbon.kontext_zeigen()
    _ruhe()
    anzahl = len(_befehle(w))
    w.selection = np.arange(4)
    w._auswahl_register()
    _ruhe()
    check("nur die Zahl wechselt: dasselbe Register, neuer Reiter",
          w.ribbon._kontext is reg and _reiter(w) == "Auswahl: 4 Knoten", _reiter(w))
    check("… es liegt weiter vorn (Befund: die Ansicht sprang auf „Extras“)",
          w.ribbon.tabs.currentWidget() is reg, _vorn(w))
    check("… seine Befehle tragen den neuen Namen, keiner doppelt, keiner fehlt",
          len(_befehle(w)) == anzahl and all(b.register == "Auswahl: 4 Knoten"
                                              for b in w.ribbon.befehle if b.register.startswith("Auswahl")),
          str({b.register for b in w.ribbon.befehle if b.register.startswith("Auswahl")}))
    hits = w.ribbon.finden("Zuweisen")
    check("… die Befehlssuche nennt den Ort mit dem neuen Namen",
          any("Auswahl: 4 Knoten" in b.ort_text() for b in hits), str([b.ort_text() for b in hits]))
    w.sel_staebe[:] = ["Riegel"]
    w._auswahl_register()
    _ruhe()
    check("kommt eine Art dazu: neues Register, Reiter „Auswahl: 5 Objekte“",
          w.ribbon._kontext is not reg and _reiter(w) == "Auswahl: 5 Objekte", _reiter(w))
    check("… und es liegt vorn, wenn das alte vorn lag", w.ribbon.tabs.currentWidget() is w.ribbon._kontext,
          _vorn(w))
    # nicht vorn: bleibt hinten
    w.ribbon.zeigen("Start")
    w.selection = np.arange(6)
    w._auswahl_register()
    _ruhe()
    check("lag es nicht vorn, bleibt das vordere Register stehen", _vorn(w) == "Start", _vorn(w))
    _leeren(w)


def test_verschwindet():
    from PySide6 import QtWidgets
    from statik3d.examples_lib import build_example
    from statik3d.gui import dialogs as dg
    from statik3d.gui import main as G
    w, app = _fenster()

    def mit_register(vorn="Geometrie"):
        w.ribbon.zeigen(vorn)
        _waehlen(w, knoten=4, staebe=["Riegel"])
        w.ribbon.kontext_zeigen()
        _ruhe()
        return w.ribbon._kontext is not None and w.ribbon.tabs.currentWidget() is w.ribbon._kontext

    def weg(was):
        ok = (w.ribbon._kontext is None and not _befehle(w)
              and not any(t.startswith("Auswahl") for t in _register_namen(w)))
        ok &= _vorn(w) == "Geometrie"
        check(f"{was}: das Register ist weg, das zuletzt benutzte („Geometrie“) liegt vorn",
              ok, f"{_register_namen(w)[-2:]} vorn {_vorn(w)} Auswahl {len(w.selection)}")

    check("Vorbereitung: Register liegt vorn", mit_register())
    w.clear_selection()
    _ruhe()
    weg("Alles deselektieren")

    mit_register()
    w.new_model()
    _ruhe()
    weg("Neu")
    check("… Neu: Auswahl leer, Lagerauswahl leer", not len(w.selection) and not w.sel_lager)

    w.sel_lager[:] = [("lager", 0)]
    w._auswahl_register()
    check("Vorbereitung: ein gewähltes Lager macht ein Register", _reiter(w) == "Auswahl: 1 Lager", _reiter(w))
    w.ribbon.zeigen("Geometrie")
    w.new_model()
    _ruhe()
    check("Neu leert auch die gewählten Lager - kein Register „Auswahl: 1 Lager“ über dem leeren Modell",
          w.ribbon._kontext is None and not w.sel_lager, f"{_reiter(w)!r} {w.sel_lager}")

    w.load_example("hall")
    _ruhe()
    mit_register()
    w.load_example("truss")
    _ruhe()
    weg("Beispiel öffnen")

    pfad = os.path.join(TMP, "modell.json")
    build_example("frame").save(pfad)
    w.load_example("hall")
    mit_register()
    w.modell_laden(pfad, fragen=False)
    _ruhe()
    weg("Modell öffnen")

    class _Dlg:
        def __init__(self, *a, **k):
            self.append = type("_H", (), {"isChecked": lambda s: False})()
            self.members = type("_H", (), {"isChecked": lambda s: False})()

        def exec(self):
            return 1

        def options(self):
            return {}
    alt_open = QtWidgets.QFileDialog.getOpenFileName
    alt_dlg = G.ImportDialog
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (pfad, ""))
    G.ImportDialog = _Dlg
    try:
        w.load_example("hall")
        mit_register()
        n_vor = w.model.nn
        w.import_file()
        _ruhe()
    finally:
        QtWidgets.QFileDialog.getOpenFileName = alt_open
        G.ImportDialog = alt_dlg
    check("Vorbereitung: der Import hat das Modell ersetzt", w.model.nn != n_vor or w.model.name != "Hallenrahmen",
          f"{w.model.name} {w.model.nn} Knoten")
    weg("Import ohne Anhängen")

    # Rueckgaengig und Wiederholen leeren die Auswahl in der Ansicht - dann auch das Register
    w.load_example("hall")
    w.ribbon.zeigen("Geometrie")
    w.merken("Probe")
    w.model.add_node(1.0, 2.0, 3.0)
    mit_register()
    w.undo()
    _ruhe()
    weg("Rückgängig")
    mit_register()
    w.redo()
    _ruhe()
    weg("Wiederholen")

    # Loeschen gewaehlter Objekte (Rechtsklick „Löschen“) hebt die Auswahl auf
    w.load_example("hall")
    _waehlen(w, staebe=["Riegel"])
    w.ribbon.zeigen("Geometrie")
    w.auswahl_loeschen("stab", ["Riegel"])
    _ruhe()
    check("Löschen eines gewählten Stabs: das Register „Auswahl: 1 Stab“ bleibt nicht stehen",
          w.ribbon._kontext is None and not w.sel_staebe, f"{_reiter(w)!r} {w.sel_staebe}")
    _leeren(w)


def test_nach_neu_ohne_fehler():
    """Die Felder des Registers sind mit ihm weg: nichts greift auf gelöschte Widgets zu."""
    w, app = _fenster()
    w.fehler_liste.clear()
    _waehlen(w, knoten=2)
    w.new_model()
    _ruhe()
    w.refresh_all()
    _ruhe()
    check("nach Neu mit offenem Register: kein Fehler, die Auswahlfelder sind abgemeldet",
          not w.fehler_liste and w.cb_assign_sec is None and w.cb_assign_shell is None, str(w.fehler_liste))


def test_klick_waehlt():
    """Die Wege der Auswahl in der Ansicht (Klick, Lager, Last, Klick ins Leere)."""
    w, app = _fenster()
    w.load_example("hall")
    _ruhe()
    _leeren(w)
    w.ribbon.zeigen("Geometrie")
    w.auswahlart_setzen("Stab")
    w._objekt_umschalten(w.sel_staebe, "Riegel", "Stäbe")
    _ruhe()
    check("Klick auf einen Stab: Register „Auswahl: 1 Stab“", _reiter(w) == "Auswahl: 1 Stab", repr(_reiter(w)))
    reg = w.ribbon._kontext
    w._objekt_umschalten(w.sel_staebe, "Stiel links", "Stäbe")
    _ruhe()
    check("… zweiter Stab: dasselbe Register, „Auswahl: 2 Stäbe“",
          w.ribbon._kontext is reg and _reiter(w) == "Auswahl: 2 Stäbe", repr(_reiter(w)))
    w._objekt_umschalten(w.sel_staebe, "Riegel", "Stäbe")
    _ruhe()
    check("… einen abgewählt: „Auswahl: 1 Stab“", _reiter(w) == "Auswahl: 1 Stab", repr(_reiter(w)))
    w._objekt_umschalten(w.sel_staebe, "Stiel links", "Stäbe")
    _ruhe()
    check("… den letzten abgewählt: kein Register", w.ribbon._kontext is None and _vorn(w) == "Geometrie",
          f"{_reiter(w)!r} vorn {_vorn(w)}")
    # intelligente Auswahl: der Zug kommt mit, der Reiter zaehlt ihn
    alt = w.act_klug.isChecked()
    w.act_klug.setChecked(True)
    try:
        w._objekt_umschalten_klug(w.sel_staebe, "Riegel", "Stäbe", w._stabenden())
    finally:
        w.act_klug.setChecked(alt)
    _ruhe()
    n = len(w.sel_staebe)
    check("intelligente Auswahl: der Reiter zählt die Stäbe des Zugs",
          n >= 1 and _reiter(w) == f"Auswahl: {n} {'Stab' if n == 1 else 'Stäbe'}", f"{n}: {_reiter(w)!r}")
    _leeren(w)
    w.auswahlart_setzen("Lager")
    w._lager_umschalten(("lager", 0))
    _ruhe()
    check("Klick auf ein Lager: „Auswahl: 1 Lager“", _reiter(w) == "Auswahl: 1 Lager", repr(_reiter(w)))
    w._lager_umschalten(("lager", 0))
    _ruhe()
    check("… nochmal: abgewählt, kein Register", w.ribbon._kontext is None, repr(_reiter(w)))
    w.auswahlart_setzen("Last")
    fall = next(n for n, c in w.model.load_cases.items() if c.beam_loads)
    w._last_waehlen(fall, "beam_loads", 0)
    _ruhe()
    check("Klick auf eine Last: „Auswahl: 1 Last“", _reiter(w) == "Auswahl: 1 Last", repr(_reiter(w)))
    w._klick_ins_leere()
    _ruhe()
    check("Klick ins Leere hebt die Auswahl auf: das Register ist weg",
          w.ribbon._kontext is None and not w.sel_lasten, repr(_reiter(w)))
    w.auswahlart_setzen("Knoten")
    w.maskenrand.schliessen()
    _ruhe()


def test_handbuch():
    """Das Handbuch nennt, was das Programm tut - die Zahl der Zeichen aus der Regel selbst."""
    from statik3d.gui.main import MainWindow
    from tests.handbuch import absatz
    reiter = absatz("**Der Reiter nennt, was gewählt ist.**")
    check("Handbuch: der Reiter nennt jede Art, Beispiel „Auswahl: 2 Stäbe“, Stand vor dem 03.10.2026",
          "Auswahl: 2 Stäbe" in reiter and "Auswahl: 1 Fläche" in reiter and "Bis zum 03.10.2026" in reiter
          and "nur, wenn **Knoten** gewählt waren" in reiter, reiter[:80])
    check(f"… und die Länge des Reiters: {MainWindow.REITER_ZEICHEN} Zeichen, gemischt die Zahl der Objekte",
          f"{MainWindow.REITER_ZEICHEN} Zeichen im Reiter" in reiter and "Auswahl: 4 Objekte" in reiter, reiter[-90:])
    check("Handbuch: Befehle nach Auswahl, Beschriftung, „unverändert“",
          "unverändert" in absatz("**Die Befehle richten sich nach der Auswahl.**")
          and "sichtbarer Beschriftung" in absatz("**Die Befehle richten sich nach der Auswahl.**"))
    check("Handbuch: das Register bleibt stehen, solange nur die Zahl wechselt",
          "Extras" in absatz("**Das Register bleibt stehen, solange sich nur die Zahl ändert.**"))
    check("Handbuch: es verschwindet mit der Auswahl, auch nach Neu, Öffnen, Import, Rückgängig",
          all(t in absatz("**Es verschwindet mit der Auswahl.**")
              for t in ("*Neu*", "*Öffnen*", "*Importieren*", "*Rückgängig*", "*Wiederholen*", "zuletzt")))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_reitertext_je_art, test_reitertext_gemischt, test_reiter_laenge,
              test_registerzeile_ohne_rollpfeile, test_felder_beschriftet, test_befehle_je_auswahl,
              test_zuweisen_auf_staebe, test_register_bleibt, test_verschwindet,
              test_nach_neu_ohne_fehler, test_klick_waehlt, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
