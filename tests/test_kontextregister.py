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
    # ein Lager, dessen Knoten nicht unter den zwei gewaehlten sind (die Knoten eines
    # gewaehlten Lagers zaehlen nicht als Knoten)
    lager = next(i for i, x in enumerate(w.model.supports) if int(x.node) >= 2)
    _waehlen(w, knoten=2, linien=["L1"], staebe=["S1"], flaechen=["F1", "F2"], koerper=["V1"],
             elemente=[1, 2, 3], lager=[("lager", lager)], lasten=[("G", "knoten", 0)])
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


def _platte_modell(w, vernetzen=True):
    """Neues Modell: Rechteck aus vier Linien, Fläche F1 (d12, S235), zwei Werkstoffe,
    zwei Dicken - wie tests/test_geometrie_kette.py."""
    from statik3d.model import Material, ShellProp
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S235"))
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("d12", 0.012))
    m.add_shell_prop(ShellProp("d20", 0.02))
    m.add_nodes(np.array([[0, 0, 0], [4, 0, 0], [4, 2, 0], [0, 2, 0.]]))
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="d12", material="S235", teilung=[4, 2])
    w.refresh_all()
    if vernetzen:
        w.geometrie_vernetzen()
        _ruhe()
    return w.model


def _quader_modell(w):
    """Neues Modell: Quader aus sechs Flächen (ohne Dicke) und der Körper Q, vernetzt."""
    from statik3d.model import Material, ShellProp
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S235"))
    m.add_material(Material.steel("S355"))
    m.add_shell_prop(ShellProp("d20", 0.02))
    lx, ly, lz = 2.0, 1.0, 1.0
    m.add_nodes(np.array([[0, 0, 0], [lx, 0, 0], [lx, ly, 0], [0, ly, 0],
                          [0, 0, lz], [lx, 0, lz], [lx, ly, lz], [0, ly, lz]], float))
    kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)]
    for i, (a, b) in enumerate(kanten):
        m.add_line(f"K{i + 1}", [a, b])
    seiten = {"Boden": ["K1", "K2", "K3", "K4"], "Deckel": ["K5", "K6", "K7", "K8"],
              "S1": ["K1", "K10", "K5", "K9"], "S2": ["K2", "K11", "K6", "K10"],
              "S3": ["K3", "K12", "K7", "K11"], "S4": ["K4", "K9", "K8", "K12"]}
    for n, ls in seiten.items():
        m.add_flaeche(n, ls, material="S355")
    m.add_koerper("Q", list(seiten), material="S355")
    w.refresh_all()
    w.geometrie_vernetzen()
    _ruhe()
    return w.model


def test_unveraendert_in_allen_feldern():
    """Punkt 1 der Gegenpruefung: wer nur die Dicke aendert, laesst Werkstoff und
    Querschnitt stehen - und umgekehrt."""
    from statik3d.model import Material, ShellProp
    w, app = _fenster()
    w.load_example("plate")
    _ruhe()
    m = w.model
    m.add_material(Material.steel("S355"))      # das Beispiel kennt nur S235: S355 ist der zweite Werkstoff
    m.add_shell_prop(ShellProp("t = 20 mm", 0.02))
    for i in (0, 1, 2):
        m.elements[i].mat = "S355"
    vorher = [(e.sec, e.mat) for e in m.elements]
    w.refresh_all()
    _waehlen(w, elemente=[0, 1, 2])
    felder = (("Querschnitt", w.cb_assign_sec), ("Werkstoff", w.cb_assign_mat), ("Dicke", w.cb_assign_shell))
    check("alle drei Felder beginnen mit „unverändert“ und stehen darauf",
          all(cb.itemText(0) == "unverändert" and cb.currentIndex() == 0 for _n, cb in felder),
          str([(n, cb.itemText(0), cb.currentIndex()) for n, cb in felder]))
    w.refresh_all()
    _ruhe()
    check("… auch nach refresh_all",
          all(cb.itemText(0) == "unverändert" and cb.currentIndex() == 0 for _n, cb in felder),
          str([(n, cb.currentText()) for n, cb in felder]))
    n_undo = len(w._undo)
    w.fehler_liste.clear()
    w.assign_props()
    check("alle drei „unverändert“: ein Hinweis, kein Rückgängig-Schritt",
          len(w.fehler_liste) == 1 and "Nichts zu ändern" in w.fehler_liste[0] and len(w._undo) == n_undo,
          str((w.fehler_liste, len(w._undo) - n_undo)))
    w.cb_assign_shell.setCurrentText("t = 20 mm")
    w.assign_props()
    _ruhe()
    m = w.model
    check("nur die Dicke geändert: der Werkstoff S355 bleibt (bis 03.10.2026: erster Werkstoff der Liste)",
          {m.elements[i].sec for i in (0, 1, 2)} == {"t = 20 mm"} and {m.elements[i].mat for i in (0, 1, 2)} == {"S355"},
          str([(m.elements[i].sec, m.elements[i].mat) for i in (0, 1, 2)]))
    check("… die übrigen Elemente bleiben unberührt",
          [(e.sec, e.mat) for e in m.elements[3:]] == vorher[3:])
    # Staebe: nur der Werkstoff - der Querschnitt bleibt
    w.load_example("hall")
    _ruhe()
    m = w.model
    m.add_material(Material.steel("S235"))
    w.refresh_all()
    riegel = [int(e) for e in m.members["Riegel"].elements]
    _waehlen(w, staebe=["Riegel"])
    w.cb_assign_mat.setCurrentText("S235")
    w.assign_props()
    _ruhe()
    m = w.model
    check("nur der Werkstoff geändert: der Querschnitt IPE 500 bleibt (bis 03.10.2026: erster Querschnitt)",
          {m.elements[i].mat for i in riegel} == {"S235"} and {m.elements[i].sec for i in riegel} == {"IPE 500"},
          str({(m.elements[i].sec, m.elements[i].mat) for i in riegel}))
    w.cb_assign_mat.setCurrentIndex(0)
    w.cb_assign_sec.setCurrentText("HEB 300")
    w.assign_props()
    _ruhe()
    m = w.model
    check("nur der Querschnitt geändert: der Werkstoff S235 bleibt",
          {m.elements[i].sec for i in riegel} == {"HEB 300"} and {m.elements[i].mat for i in riegel} == {"S235"},
          str({(m.elements[i].sec, m.elements[i].mat) for i in riegel}))
    _leeren(w)


def test_zuweisen_aendert_flaeche_und_volumen():
    """Punkt 2: das Netz entsteht aus Flaeche.dicke/material und Volumenkoerper.material."""
    w, app = _fenster()
    m = _platte_modell(w)
    f = m.flaechen["F1"]
    check("Vorbereitung: Fläche F1 vernetzt, d12 und S235",
          len(f.elemente) > 0 and {m.elements[i].sec for i in f.elemente} == {"d12"}
          and {m.elements[i].mat for i in f.elemente} == {"S235"})
    _waehlen(w, flaechen=["F1"])
    w.cb_assign_shell.setCurrentText("d20")
    w.cb_assign_mat.setCurrentText("S355")
    w.assign_props()
    _ruhe()
    m = w.model
    f = m.flaechen["F1"]
    check("Zuweisen an eine Fläche: das Objekt trägt Dicke d20 und Werkstoff S355, auch ihre Elemente",
          f.dicke == "d20" and f.material == "S355"
          and {m.elements[i].sec for i in f.elemente} == {"d20"} and {m.elements[i].mat for i in f.elemente} == {"S355"},
          f"{f.dicke} {f.material}")
    w.sel_flaechen[:] = ["F1"]
    w.geometrie_vernetzen()
    _ruhe()
    m = w.model
    f = m.flaechen["F1"]
    check("… „Neu vernetzen“ setzt die Zuweisung nicht zurück",
          len(f.elemente) > 0 and {m.elements[i].sec for i in f.elemente} == {"d20"}
          and {m.elements[i].mat for i in f.elemente} == {"S355"},
          str(({m.elements[i].sec for i in f.elemente}, {m.elements[i].mat for i in f.elemente})))
    # Volumen: der Koerper traegt den Werkstoff; eine Randflaeche ohne Dicke traegt nicht
    m = _quader_modell(w)
    check("Vorbereitung: Quader vernetzt, Randfläche „Boden“ ohne Dicke und ohne eigenes Netz",
          len(m.koerper["Q"].elemente) > 0 and m.flaechen["Boden"].dicke == ""
          and not m.flaeche_traegt("Boden") and not m.flaechen["Boden"].elemente)
    _waehlen(w, koerper=["Q"], flaechen=["Boden"])
    w.cb_assign_mat.setCurrentText("S235")
    w.cb_assign_shell.setCurrentText("d20")
    w.fehler_liste.clear()
    w.assign_props()
    _ruhe()
    m = w.model
    k = m.koerper["Q"]
    check("Zuweisen an Volumen: der Körper trägt S235, auch seine Elemente",
          k.material == "S235" and {m.elements[i].mat for i in k.elemente} == {"S235"},
          f"{k.material} {({m.elements[i].mat for i in k.elemente})}")
    check("… eine Randfläche ohne eigene Steifigkeit bekommt keine Dicke (sonst entstünde ein Schalennetz)",
          m.flaechen["Boden"].dicke == "" and not m.flaeche_traegt("Boden") and m.flaechen["Boden"].material == "S355",
          f"{m.flaechen['Boden'].dicke!r} {m.flaechen['Boden'].material}")
    w.sel_koerper[:] = ["Q"]
    w.sel_flaechen[:] = []
    w.geometrie_vernetzen()
    _ruhe()
    m = w.model
    check("… „Neu vernetzen“ des Körpers behält S235",
          {m.elements[i].mat for i in m.koerper["Q"].elemente} == {"S235"},
          str({m.elements[i].mat for i in m.koerper["Q"].elemente}))
    _leeren(w)


def test_zuweisen_ueberspringt_federn():
    """Punkt 3: eine Feder traegt den Namen ihrer Federeigenschaft, nie einen Querschnitt."""
    from statik3d import solver
    from statik3d.model import Material, Section
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S235"))
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    m.add_section(Section.from_profile("IPE 500"))
    a, b, c = (m.add_node(float(x), 0.0, 0.0) for x in (0, 1, 2))
    m.add_feder_prop("F", [2e6] * 6)
    stab = m.add_element("beam", [a, b], "S235", "HEB 300")
    feder = m.add_element("feder", [b, c], "S235", "F")
    m.fix(a, "all")
    m.fix(c, "all")
    m.load_node(b, Fz=-1000.0)
    w.refresh_all()
    _waehlen(w, elemente=[stab, feder])
    w.cb_assign_sec.setCurrentText("IPE 500")
    w.cb_assign_mat.setCurrentText("S355")
    w.assign_props()
    _ruhe()
    m = w.model
    check("Querschnitt: der Stab bekommt IPE 500, die Feder behält ihre Federeigenschaft „F“",
          m.elements[stab].sec == "IPE 500" and m.elements[feder].sec == "F",
          f"{m.elements[stab].sec} / {m.elements[feder].sec}")
    check("… der Werkstoff geht an den Stab, nicht an die Feder (Verbindungen haben keinen)",
          m.elements[stab].mat == "S355" and m.elements[feder].mat == "S235",
          f"{m.elements[stab].mat} / {m.elements[feder].mat}")
    try:
        r = solver.solve_static(m)
        ok = np.isfinite(r.u).all()
        detail = ""
    except (KeyError, RuntimeError) as ex:        # assemble wirft KeyError, der Löser reicht ihn als RuntimeError weiter
        ok, detail = False, f"{type(ex).__name__} {ex} / {ex.__cause__!r}"
    check("… und die Rechnung findet die Feder (bis 03.10.2026: KeyError in assemble)", ok, detail)
    _leeren(w)


def test_zuweisen_verwirft_ergebnisse():
    """Punkt 4: nach einer echten Aenderung gehoeren die Ergebnisse zum alten Stand."""
    from statik3d import solver
    w, app = _fenster()
    w.load_example("hall")
    _ruhe()
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an)
    _ruhe()
    check("Vorbereitung: gerechnet", w.analysis is not None)
    _waehlen(w, staebe=["Riegel"])
    w.cb_assign_sec.setCurrentText("HEB 300")
    w.assign_props()
    _ruhe()
    check("Zuweisen mit echter Änderung: die Ergebnisse sind verworfen",
          w.analysis is None and w.results is None, f"{w.analysis!r}")
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an)
    _ruhe()
    n_undo = len(w._undo)
    _waehlen(w, staebe=["Riegel"])
    w.cb_assign_sec.setCurrentText("HEB 300")
    w.assign_props()
    _ruhe()
    check("… dieselben Werte noch einmal: nichts geändert, Ergebnisse und Rückgängig-Stapel bleiben",
          w.analysis is not None and len(w._undo) == n_undo, f"{w.analysis!r} {len(w._undo) - n_undo}")
    _leeren(w)


def test_baum_ersetzt_die_auswahl_ganz():
    """Punkt 5: ein Klick im Baum ersetzt die Auswahl ganz - Elemente, Lager, Lasten
    bleiben nicht stehen."""
    w, app = _fenster()
    w.load_example("hall")
    _ruhe()
    m = w.model
    riegel = {int(e) for e in m.members["Riegel"].elements}
    fremd = [i for i in range(len(m.elements)) if i not in riegel][:3]
    _waehlen(w, elemente=fremd, lager=[("lager", 0)], lasten=[("LF1", "beam_loads", 0)])
    w._baum_geklickt("stab", "Riegel")
    _ruhe()
    check("Netzelemente gewählt, dann Stab im Baum: nur der Stab ist gewählt",
          w.sel_staebe == ["Riegel"] and not w.sel_elemente and not w.sel_lager and not w.sel_lasten
          and not len(w.selection), f"{w.sel_staebe} {w.sel_elemente} {w.sel_lager} {w.sel_lasten}")
    check("… der Reiter sagt „Auswahl: 1 Stab“", _reiter(w) == "Auswahl: 1 Stab", repr(_reiter(w)))
    vorher = {i: m.elements[i].sec for i in range(len(m.elements))}
    w.cb_assign_sec.setCurrentText("HEB 300")
    w.assign_props()
    _ruhe()
    m = w.model
    geaendert = {i for i in range(len(m.elements)) if m.elements[i].sec != vorher[i]}
    check("… Zuweisen trifft nur die Elemente des Stabs (die gewählten Netzelemente von vorher nicht)",
          geaendert == riegel and not (geaendert & set(fremd)), f"{sorted(geaendert)} / Riegel {sorted(riegel)}")
    w.undo()
    _ruhe()
    # die Mehrfachauswahl im Baum
    _waehlen(w, elemente=fremd, lager=[("lager", 0)])
    w._baum_mehrfach("stab", ["Riegel", "Stiel links"])
    _ruhe()
    check("Mehrfachauswahl im Baum: Stäbe gewählt, Elemente und Lager vergessen",
          sorted(w.sel_staebe) == ["Riegel", "Stiel links"] and not w.sel_elemente and not w.sel_lager,
          f"{w.sel_staebe} {w.sel_elemente} {w.sel_lager}")
    _waehlen(w, elemente=fremd, lager=[("lager", 0)], lasten=[("LF1", "beam_loads", 0)])
    w._baum_geklickt("knoten", "3")
    _ruhe()
    check("Knoten im Baum: nur dieser Knoten, nichts sonst", list(w.selection) == [3] and not w.sel_elemente
          and not w.sel_lager and not w.sel_lasten, f"{list(w.selection)} {w.sel_elemente} {w.sel_lager}")
    from statik3d.model import GESAMTSYSTEM
    _waehlen(w, elemente=fremd, lager=[("lager", 0)], lasten=[("LF1", "beam_loads", 0)])
    w._subsystem_zeigen(GESAMTSYSTEM)
    _ruhe()
    check("Subsystem im Baum: ersetzt die Auswahl ganz (keine Lager, keine Lasten von vorher)",
          not w.sel_lager and not w.sel_lasten and len(w.sel_elemente) == len(w.model.elements),
          f"{w.sel_lager} {w.sel_lasten} {len(w.sel_elemente)}")
    _waehlen(w, elemente=fremd, lager=[("lager", 0)], lasten=[("LF1", "beam_loads", 0)], staebe=["Riegel"])
    w._auswahl_leeren()
    check("_auswahl_leeren leert jede Art (auch Lager und Lasten)",
          not w._auswahl_arten() and w.ribbon._kontext is None, str(w._auswahl_arten()))
    _leeren(w)


def test_lager_zaehlt_einmal():
    """Punkt 6: ein einzelnes Lager heisst „Auswahl: 1 Lager“, nicht „2 Objekte“."""
    from PySide6 import QtWidgets
    w, app = _fenster()
    w.load_example("hall")
    _ruhe()
    w._baum_geklickt("lager_einzeln", "0")
    _ruhe()
    check("Knotenlager im Baum: „Auswahl: 1 Lager“ (die Knoten des Lagers zählen nicht mit)",
          _reiter(w) == "Auswahl: 1 Lager" and len(w.selection) >= 1, f"{_reiter(w)!r} Knoten {list(w.selection)}")
    check("… die Knoten leuchten weiter in der Ansicht (selection bleibt gesetzt)", len(w.selection) >= 1)
    lager_knoten = {int(i) for i in w.selection}
    extra = next(n for n in range(w.model.nn) if n not in lager_knoten)
    w._set_selection(sorted(lager_knoten | {extra}))
    _ruhe()
    check("… ein zusätzlich gewählter Knoten zählt: „1 Knoten, 1 Lager“",
          w.ribbon._kontext is not None and _reiter(w) == "Auswahl: 2 Objekte"
          and w.ribbon._kontext.findChild(QtWidgets.QLabel, "kontextgewaehlt").text() == "1 Knoten, 1 Lager",
          f"{_reiter(w)!r}")
    _leeren(w)
    w._tabelle_lager(0)
    _ruhe()
    check("Lagertabelle: ein Klick auf Zeile 0 wählt „Auswahl: 1 Lager“", _reiter(w) == "Auswahl: 1 Lager",
          f"{_reiter(w)!r} {w.sel_lager}")
    # Der Zweig waehlt nichts (Teilpaket 8b, 03.10.2026): bis dahin waehlte er
    # alle Knotenlager, und der Reiter hiess „Auswahl: N Lager“
    _waehlen(w, lager=[("lager", 0)])
    w._baum_geklickt("lager", "Knotenlager")
    _ruhe()
    mk = w.maskenrand.maske
    check("Zweig „Knotenlager“ (8b): die Auswahl bleibt „Auswahl: 1 Lager“, rechts die Übersicht",
          w.sel_lager == [("lager", 0)] and _reiter(w) == "Auswahl: 1 Lager"
          and mk is not None and mk.titel == "Knotenlager", f"{_reiter(w)!r} {w.sel_lager}")
    _leeren(w)


def test_register_zieht_in_allen_wegen_nach():
    """Punkt 7: Wege, die die Auswahl aendern, ohne _auswahl_register zu rufen."""
    import types
    w, app = _fenster()
    w.load_example("hall")
    _ruhe()
    _leeren(w)
    # a) Mehrfachauswahl im Baum
    w._baum_mehrfach("stab", ["Riegel", "Stiel links"])
    _ruhe()
    check("Baum, mehrere Stäbe: „Auswahl: 2 Stäbe“", _reiter(w) == "Auswahl: 2 Stäbe", repr(_reiter(w)))
    # b) Lastart im Baum: die belasteten Objekte werden gewaehlt
    _leeren(w)
    lc = next(c for c in w.model.load_cases.values() if c.nodal_loads)     # Stablasten leuchten nur
    art = next(a for a, ls in lc.lasten_je_art().items() if ls)
    w._lastart_geklickt(f"{lc.name}|{art}")
    _ruhe()
    arten = w._auswahl_arten()
    check("Lastart im Baum: die gewählten belasteten Objekte stehen im Register",
          bool(arten) and w.ribbon._kontext is not None and _reiter(w) == w._auswahl_texte(arten)[0],
          f"{_reiter(w)!r} {[(k, n) for k, n, _e, _m in arten]}")
    # c) Verbindungszweig (Federn): kehrt im Baum vor dem Abgleich zurueck
    _leeren(w)
    w.maskenrand.schliessen()
    m = w.model
    m.add_feder_prop("F", [1e6] * 6)
    m.add_element("feder", [0, 1], "S355", "F")
    # eine zweite Feder an anderen Knoten: der Zweig waehlte bis 8b die Knoten
    # beider, der Eintrag „F“ nur die seiner Feder
    m.add_feder_prop("F2", [1e6] * 6)
    m.add_element("feder", [2, 3], "S355", "F2")
    w.refresh_all()
    _leeren(w)
    # Der Eintrag „F“ (bis zum 03.10.2026 waehlte auch der Zweig „Federn“ die
    # Knoten aller Federn; seit 8b waehlt ein Zweig nichts)
    w._baum_geklickt("feder", "F")
    _ruhe()
    check("Baum, Eintrag „F“ unter „Federn“: die Knoten der Feder sind gewählt und das Register nennt sie",
          sorted(int(i) for i in w.selection) == [0, 1] and _reiter(w) == "Auswahl: 2 Knoten",
          f"{_reiter(w)!r} {list(w.selection)}")
    vorher = (list(w.selection), _reiter(w))
    w._baum_geklickt("federn", "Federn")
    _ruhe()
    check("… der Zweig „Federn“ lässt diese Auswahl stehen (8b)",
          (list(w.selection), _reiter(w)) == vorher, f"{_reiter(w)!r} {list(w.selection)}")
    # d) Klickmodus einer Maske (Randlinien einer Flaeche)
    _leeren(w)
    w.maskenrand.schliessen()
    maske = types.SimpleNamespace(werte=lambda: {"linien": "L1, L2"})
    w.new_model()
    m = w.model
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0.]]))
    for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a, b])
    w.refresh_all()
    w._objektmaske_klick_zeigen(maske, "geoflaeche")
    _ruhe()
    check("Klickmodus der Flächenmaske: „Auswahl: 2 Linien“", _reiter(w) == "Auswahl: 2 Linien", repr(_reiter(w)))
    # d2) Klickmodus der Kontaktmaske: beide Seiten der Fuge leuchten
    _leeren(w)
    _quader_modell(w)
    maske = types.SimpleNamespace(werte=lambda: {"flaechennamen": "Boden", "gegenflaechen": "Deckel"})
    w._objektmaske_klick_zeigen(maske, "kontaktbedingung")
    _ruhe()
    check("Klickmodus der Kontaktmaske: „Auswahl: 2 Flächen“", _reiter(w) == "Auswahl: 2 Flächen", repr(_reiter(w)))
    w.new_model()
    m = w.model
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0.]]))
    for i, (a_, b_) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        m.add_line(f"L{i + 1}", [a_, b_])
    w.refresh_all()
    # e) Linientabelle -> _baum_auswaehlen
    _leeren(w)
    w._baum_auswaehlen("linie", "L1")
    _ruhe()
    check("Klick in der Linientabelle: die Knoten der Linie, „Auswahl: 2 Knoten“",
          _reiter(w) == "Auswahl: 2 Knoten" and list(w.selection) == [0, 1], f"{_reiter(w)!r} {list(w.selection)}")
    # f) Vernetzen vor dem Rechnen: die Auswahl kommt zurueck, das Register muss mit
    m = _platte_modell(w, vernetzen=False)
    w._fragen = lambda *a, **k: True
    w.sel_flaechen[:] = ["F1"]
    w._auswahl_register()
    _ruhe()
    check("Vorbereitung: Fläche F1 gewählt, noch ohne Netz", _reiter(w) == "Auswahl: 1 Fläche"
          and not w.model.flaechen["F1"].elemente, repr(_reiter(w)))
    ok = w._vor_rechnung_vernetzen()
    _ruhe()
    check("Vernetzen vor dem Rechnen: vernetzt, die Auswahl kommt zurück und das Register mit ihr",
          ok and len(w.model.flaechen["F1"].elemente) > 0 and w.sel_flaechen == ["F1"]
          and _reiter(w) == "Auswahl: 1 Fläche", f"{ok} {w.sel_flaechen} {_reiter(w)!r}")
    _leeren(w)


def test_schlechte_waehlen_waehlt_elemente():
    """Punkt 8: „Schlechte wählen“ der Netzqualität schrieb Elementnummern in die Knotenauswahl."""
    from PySide6 import QtWidgets
    from statik3d.model import Material
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=7850))
    m.add_material(Material.steel("S235"))
    for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]:
        m.add_node(*p)
    for t in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6)]:
        m.add_element("tet4", list(t), "S355")
    m.add_element("tet4", [0, 1, 2, 3], "S355")          # eben: Formgüte 0
    w.refresh_all()
    w.maske_netzguete()
    mk = w.maskenrand.maske
    knoepfe = {b.text(): b for b in mk.findChildren(QtWidgets.QPushButton)}
    mk.setzen("mass", "Formgüte (1 = beste Form)")
    knoepfe["Schlechte wählen"].click()
    _ruhe()
    check("„Schlechte wählen“: Element 5 steht in der Elementauswahl, die Knotenauswahl bleibt leer",
          w.sel_elemente == [5] and not len(w.selection) and w.auswahlart == "Netz",
          f"Elemente {w.sel_elemente} Knoten {list(w.selection)} / {w.auswahlart}")
    check("… das Register nennt es: „Auswahl: 1 Element“", _reiter(w) == "Auswahl: 1 Element", repr(_reiter(w)))
    w.cb_assign_mat.setCurrentText("S235")
    w.assign_props()
    _ruhe()
    m = w.model
    check("… Zuweisen trifft genau dieses Element",
          [e.mat for e in m.elements] == ["S355"] * 5 + ["S235"], str([e.mat for e in m.elements]))
    knoepfe["Aus"].click()
    w._auswahl_register()
    w.clear_mesh()
    _ruhe()
    check("„Modell leeren“ danach: keine Elementauswahl und kein Register über dem leeren Modell",
          not w.sel_elemente and w.ribbon._kontext is None and not len(w.model.elements),
          f"{w.sel_elemente} {_reiter(w)!r} {len(w.model.elements)} Elemente")
    w.maskenrand.schliessen()
    _leeren(w)


def test_sammelmaske_behaelt_ihr_unveraendert():
    """Die Sammelmaske (Rechtsklick „Bearbeiten…“) nennt ihre Auswahl „(unverändert)“.

    Ursache des Rauchtest-Risses am Stand 485f9bf: 12c hatte die Konstante der
    Auswahlfelder im Register unter dem Namen ``UNVERAENDERT`` angelegt - der
    Name gehoert in MainWindow schon der Sammelmaske (Wert „(unverändert)“), und
    die spaetere Zeile gewann. Die zwei Werte sind verschieden, die Namen auch."""
    from statik3d.gui.main import MainWindow
    from statik3d.model import Member as Mb
    w, app = _fenster()
    w.new_model()
    m = w.model
    mat, sec = list(m.materials)[0], list(m.sections)[0]
    k0 = m.add_node(0, 0, 0)
    k1 = m.add_node(4, 0, 0)
    k3 = m.add_node(0, 3, 0)
    e0 = m.add_element("beam", [k0, k1], mat, sec)
    m.members["S1"] = Mb("S1", elements=[e0])
    m.fix(k0, "all")
    m.fix(k3, [0, 1, 2])
    w.refresh_all()
    _ruhe()
    check("die Sammelmaske behält ihr „(unverändert)“, das Register sein „unverändert“ (zwei Konstanten)",
          MainWindow.UNVERAENDERT == "(unverändert)" and MainWindow.ZUWEISEN_UNVERAENDERT == "unverändert",
          f"{MainWindow.UNVERAENDERT!r} / {getattr(MainWindow, 'ZUWEISEN_UNVERAENDERT', None)!r}")
    w.sammelmaske("lager", [0, 1])
    _ruhe()
    mk = w.maskenrand.maske
    werte = mk.werte()
    check("Sammelmaske Lager: u_x bei beiden gesperrt (ja), φ_x verschieden → „(unverändert)“",
          werte["d0"] == "ja" and werte["d3"] == "(unverändert)", f"d0={werte['d0']!r} d3={werte['d3']!r}")
    mk.setzen("d3", "ja")
    mk.anwenden()
    _ruhe()
    check("… und „ja“ sperrt φ_x bei beiden Lagern, „(unverändert)“ lässt es (Rückweg der Maske)",
          all(3 in s.dofs for s in w.model.supports), str([list(s.dofs) for s in w.model.supports]))
    w.maskenrand.schliessen()
    _leeren(w)


def test_klick_waehlt():
    """Die Wege der Auswahl in der Ansicht (Klick, Lager, Last, Klick ins Leere)."""
    w, app = _fenster()
    w.load_example("hall")
    _ruhe()
    _leeren(w)
    w.ribbon.zeigen("Geometrie")
    w.auswahlart_setzen("Stab")
    # ersetzen=True ist der Klick ohne Taste, ersetzen=False Strg+Klick: dazu oder
    # heraus (seit 03.10.2026, tests/test_klickauswahl.py)
    w._objekt_umschalten(w.sel_staebe, "Riegel", "Stäbe", ersetzen=True)
    _ruhe()
    check("Klick auf einen Stab: Register „Auswahl: 1 Stab“", _reiter(w) == "Auswahl: 1 Stab", repr(_reiter(w)))
    reg = w.ribbon._kontext
    w._objekt_umschalten(w.sel_staebe, "Stiel links", "Stäbe", ersetzen=False)
    _ruhe()
    check("… Strg+Klick auf einen zweiten Stab: dasselbe Register, „Auswahl: 2 Stäbe“",
          w.ribbon._kontext is reg and _reiter(w) == "Auswahl: 2 Stäbe", repr(_reiter(w)))
    w._objekt_umschalten(w.sel_staebe, "Riegel", "Stäbe", ersetzen=False)
    _ruhe()
    check("… Strg+Klick wählt einen ab: „Auswahl: 1 Stab“", _reiter(w) == "Auswahl: 1 Stab", repr(_reiter(w)))
    w._objekt_umschalten(w.sel_staebe, "Stiel links", "Stäbe", ersetzen=False)
    _ruhe()
    check("… Strg+Klick wählt den letzten ab: kein Register", w.ribbon._kontext is None and _vorn(w) == "Geometrie",
          f"{_reiter(w)!r} vorn {_vorn(w)}")
    # intelligente Auswahl: der Zug kommt mit, der Reiter zaehlt ihn
    alt = w.act_klug.isChecked()
    w.act_klug.setChecked(True)
    try:
        w._objekt_umschalten_klug(w.sel_staebe, "Riegel", "Stäbe", w._stabenden(), ersetzen=True)
    finally:
        w.act_klug.setChecked(alt)
    _ruhe()
    n = len(w.sel_staebe)
    check("intelligente Auswahl: der Reiter zählt die Stäbe des Zugs",
          n >= 1 and _reiter(w) == f"Auswahl: {n} {'Stab' if n == 1 else 'Stäbe'}", f"{n}: {_reiter(w)!r}")
    _leeren(w)
    w.auswahlart_setzen("Lager")
    w._lager_umschalten(("lager", 0), ersetzen=True)
    _ruhe()
    check("Klick auf ein Lager: „Auswahl: 1 Lager“", _reiter(w) == "Auswahl: 1 Lager", repr(_reiter(w)))
    w._lager_umschalten(("lager", 0), ersetzen=False)
    _ruhe()
    check("… Strg+Klick noch einmal: abgewählt, kein Register", w.ribbon._kontext is None, repr(_reiter(w)))
    w.auswahlart_setzen("Last")
    fall = next(n for n, c in w.model.load_cases.items() if c.beam_loads)
    w._last_waehlen(fall, "beam_loads", 0, ersetzen=True)
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
    befehle = absatz("**Die Befehle richten sich nach der Auswahl.**")
    check("Handbuch: Zuweisen mit sichtbarer Beschriftung, „unverändert“ in jedem Feld, nur Gesetztes wird geschrieben",
          "sichtbare Beschriftung" in befehle and "jedes beginnt mit dem Eintrag „unverändert“" in befehle
          and "Nichts zu ändern" in befehle and "Bis zum 03.10.2026" in befehle, befehle[:90])
    objekte = absatz("Die Elemente der Auswahl sind alle Elemente")
    check("Handbuch: Zuweisen an Flächen und Volumen ändert das Objekt, Feder, Randfläche, Ergebnisse verworfen",
          "auch das Objekt" in objekte and "*Neu vernetzen*" in objekte and "Feder" in objekte
          and "Randfläche" in objekte and "sind die Ergebnisse verworfen" in objekte, objekte[:90])
    check("Handbuch: ein einzelnes Lager heißt „Auswahl: 1 Lager“, vorher „2 Objekte“",
          "„Auswahl: 1 Lager“" in reiter and "„Auswahl: 2 Objekte“" in reiter, reiter[-120:])
    baum = absatz("**Ein Klick im Modellbaum ersetzt die Auswahl ganz.**")
    check("Handbuch: der Baum ersetzt die Auswahl ganz, „Schlechte wählen“ wählt Elemente",
          "Netzelemente, Lager und Lasten" in baum and "Schlechte wählen" in baum, baum[:90])
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
              test_nach_neu_ohne_fehler, test_unveraendert_in_allen_feldern,
              test_zuweisen_aendert_flaeche_und_volumen, test_zuweisen_ueberspringt_federn,
              test_zuweisen_verwirft_ergebnisse, test_baum_ersetzt_die_auswahl_ganz, test_lager_zaehlt_einmal,
              test_register_zieht_in_allen_wegen_nach, test_schlechte_waehlen_waehlt_elemente,
              test_sammelmaske_behaelt_ihr_unveraendert, test_klick_waehlt, test_handbuch):
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
