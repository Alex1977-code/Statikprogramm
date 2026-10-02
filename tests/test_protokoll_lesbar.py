"""
Protokoll lesbar (Plan-Schritt 9a, 02.10.2026): FEHLER rot, WARNUNG orange,
Abschnitte fett, eine echte Festbreitenschrift.

* Die Zeilen werden ueber einen Syntaxfaerber am Dokument gefaerbt - der Text
  des Protokolls (toPlainText) bleibt Zeichen fuer Zeichen derselbe, denn sehr
  viele Pruefungen lesen ihn so.
* FEHLER-Zeile: ganze Zeile in der Fehlerfarbe der Oberflaeche
  (design.FARBEN["schlecht"]); WARNUNG-Zeile in der Warnfarbe
  (FARBEN["warn"]); Abschnittskopf („--- Titel ---“): fett.
* Schrift: unter Windows ist „monospace“ kein Schriftname - die Vorgabe wurde
  zu Tahoma, einer Proportionalschrift (gemessen 02.10.2026). Jetzt waehlt
  design.festschrift_familie die erste wirklich festbreite Schrift.

Aufruf:  python -m tests.test_protokoll_lesbar
         python -m tests.test_protokoll_lesbar --nur-schrift   (ohne Hauptfenster,
         zum Lauf auf dem Desktop mit QT_QPA_PLATFORM=windows: dann gibt es
         Schriften, offscreen gibt es keine)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_protokoll_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    """Die Anwendung - Qt verlangt sie, bevor man nach Schriften fragt."""
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
    _FENSTER.update(w=w, app=app)
    return w, app


def _zeilen(w):
    """Die Zeilen des Protokolls als (Text, [(von, laenge, Farbe, fett), ...])
    - so, wie der Faerber sie dem Layout des Blocks mitgegeben hat."""
    from PySide6 import QtGui
    aus = []
    b = w.log.document().begin()
    while b.isValid():
        fm = []
        lay = b.layout()
        for r in (lay.formats() if lay is not None else []):
            f = r.format
            farbe = f.foreground().color().name() if f.hasProperty(
                QtGui.QTextFormat.ForegroundBrush) else None
            fett = f.hasProperty(QtGui.QTextFormat.FontWeight) and f.fontWeight() >= 700
            fm.append((r.start, r.length, farbe, fett))
        aus.append((b.text(), fm))
        b = b.next()
    return aus


def _letzte(w, n=1):
    z = _zeilen(w)
    return z[-n:] if n > 1 else z[-1]


def _farben():
    from PySide6 import QtGui
    from statik3d.gui.design import FARBEN
    return (QtGui.QColor(FARBEN["schlecht"]).name(), QtGui.QColor(FARBEN["warn"]).name())


def test_zeilenarten_im_fenster():
    """Fehler rot, Warnung in der Warnfarbe, Abschnitt fett, Rest ohne Format."""
    w, app = _fenster()
    rot, warn = _farben()
    w.log.clear()

    def schreibe(text):
        w.log.appendPlainText(text)
        return _letzte(w)

    t, fm = schreibe("FEHLER: Probe ohne Lager")
    check("FEHLER-Zeile: ganze Zeile rot", fm == [(0, len(t), rot, False)], str(fm))
    t, fm = schreibe("WARNUNG: Probe mit Hinweis")
    check("WARNUNG-Zeile: ganze Zeile in der Warnfarbe", fm == [(0, len(t), warn, False)], str(fm))
    t, fm = schreibe("--- Modellprüfung ---")
    check("Abschnittskopf: ganze Zeile fett, Farbe unberührt",
          fm == [(0, len(t), None, True)], str(fm))
    t, fm = schreibe("max. Verschiebung       : 16.894 mm (Knoten 13)")
    check("normale Zeile: ohne jedes Format", fm == [], str(fm))

    # Einrueckung und Schreibweisen aus echten Protokollen (Importhinweise
    # „  WARNUNG:   ...“, Eingabefehler „FEHLER Versatz ...: ...“)
    t, fm = schreibe("  WARNUNG:   Stabtyp Zugstab: faellt in RFEM bei Druck aus")
    check("eingerückte WARNUNG (Importhinweis) in der Warnfarbe",
          fm == [(0, len(t), warn, False)], str(fm))
    t, fm = schreibe("FEHLER Versatz Anfang y, z [mm]: „1.5“ ist mehrdeutig")
    check("FEHLER ohne Doppelpunkt (Eingabefehler) rot", fm == [(0, len(t), rot, False)], str(fm))
    t, fm = schreibe("WARNUNG: FEHLER: 2 Teiltragwerke ohne Lager")
    check("WARNUNG vor FEHLER: gilt das erste Wort (Warnfarbe)",
          fm == [(0, len(t), warn, False)], str(fm))

    # was nur so aussieht, bleibt unberuehrt
    for text in ("Abnahme: FEHLER mitten im Satz",
                 "FEHLERFREI: nichts zu melden",
                 "WARNUNGEN: 3",
                 "Fehler: klein geschrieben",
                 "warnung: klein geschrieben",
                 "-- zwei Striche",
                 "---ohne Leerzeichen",
                 "    --- eingerückt ---",
                 "Netz --- Mitte"):
        t, fm = schreibe(text)
        check(f"ohne Format: „{text}“", fm == [], str(fm))

    # eine Folgezeile einer Meldung ist eine eigene Zeile: nichts blutet nach
    w.log.appendPlainText("FEHLER: erste Zeile\nzweite Zeile der Meldung")
    z = _zeilen(w)
    check("mehrzeilige Meldung: nur die Zeile mit FEHLER ist rot",
          z[-2][1] == [(0, len(z[-2][0]), rot, False)] and z[-1][0] == "zweite Zeile der Meldung"
          and z[-1][1] == [], str(z[-2:]))
    w.log.appendPlainText("danach eine ganz normale Zeile")
    check("die Zeile nach einer FEHLER-Zeile bleibt ohne Format", _letzte(w)[1] == [], str(_letzte(w)))


def test_aufrufe_des_programms():
    """Die Stellen, die wirklich ins Protokoll schreiben: error, warnung,
    Abschnittskopf des Modellwechsels und der Modellpruefung, rote Sammelzeile."""
    w, app = _fenster()
    rot, warn = _farben()
    w.log.clear()
    # waehrend einer Rechnung geht error/warnung ohne Fenster ins Protokoll
    w._rechnet_gerade = True
    try:
        w.error("Probefehler")
        z = _letzte(w)
        check("error(): „FEHLER: Probefehler“ steht rot im Protokoll",
              z[0] == "FEHLER: Probefehler" and z[1] == [(0, len(z[0]), rot, False)], str(z))
        w.warnung("Probewarnung")
        z = _letzte(w)
        check("warnung(): „WARNUNG: Probewarnung“ steht in der Warnfarbe",
              z[0] == "WARNUNG: Probewarnung" and z[1] == [(0, len(z[0]), warn, False)], str(z))
    finally:
        w._rechnet_gerade = False
    w._protokoll_neu("Probe-Modell")
    z = _letzte(w)
    check("Modellwechsel: „--- Probe-Modell  (Datum) ---“ fett",
          z[0].startswith("--- Probe-Modell") and z[1] == [(0, len(z[0]), None, True)], str(z))
    w.do_check()
    kopf = [x for x in _zeilen(w) if x[0] == "--- Modellprüfung ---"]
    check("Modellprüfung: der Kopf ist fett", len(kopf) == 1 and kopf[0][1] == [(0, len(kopf[0][0]), None, True)],
          str(kopf))
    # die rote Sammelzeile (Nachweise) behaelt ihr eigenes Zeichenformat: rot und
    # fett; der Faerber legt nichts darueber, was ihr widerspraeche
    w._protokoll_rot("Nachweise: 1 NICHT erfüllt (Probe)")
    b = w.log.document().lastBlock()
    f = b.begin().fragment().charFormat()
    check("rote Sammelzeile: eigenes Format rot und fett bleibt",
          f.foreground().color().name() == rot and f.fontWeight() >= 700
          and _letzte(w)[1] == [], str(_letzte(w)))
    w._protokoll_rot("FEHLER: auch rot gesetzt")
    b = w.log.document().lastBlock()
    f = b.begin().fragment().charFormat()
    check("rote Sammelzeile mit FEHLER: bleibt rot und fett",
          f.foreground().color().name() == rot and f.fontWeight() >= 700
          and _letzte(w)[1] == [(0, len("FEHLER: auch rot gesetzt"), rot, False)], str(_letzte(w)))


def test_text_bleibt_wie_geschrieben():
    """Der Faerber aendert keinen Buchstaben: toPlainText ist genau das
    Geschriebene (sehr viele Pruefungen lesen das Protokoll so)."""
    w, app = _fenster()
    w.log.clear()
    zeilen = ["--- Beispiel 'hall'  (02.10.2026 08:39) ---",
              "FEHLER: Etwas ist schiefgegangen",
              "WARNUNG: 2 von 6 freien Bewegungen tragen Last",
              "  WARNUNG:   Stabtyp Zugstab: faellt in RFEM bei Druck aus",
              "Lastfaelle: 5   Kombinationen: 72   Rechenzeit: 0.51 s",
              "",
              "    eingerückt mit Umlauten äöüß und „Anführungen“",
              "--- Abnahme des Netzes: bestanden --- (3 Warnungen)"]
    for z in zeilen:
        w.log.appendPlainText(z)
    check("toPlainText ist genau das Geschriebene", w.log.toPlainText() == "\n".join(zeilen),
          repr(w.log.toPlainText()[:80]))
    # leere Zeile: kein Format, kein Absturz
    leer = [x for x in _zeilen(w) if x[0] == ""]
    check("leere Zeile ohne Format", len(leer) == 1 and leer[0][1] == [], str(leer))


def test_leistung_je_zeile():
    """Der Faerber arbeitet je Block: zwanzigtausend Zeilen anhaengen kostet
    nicht spuerbar mehr als ohne Faerber (Grenze grosszuegig, nur gegen eine
    Schleife ueber das ganze Dokument je Zeile)."""
    import time
    from statik3d.gui import main as M
    w, app = _fenster()
    n = 3000

    def lauf(mit):
        f = M.Protokollfeld()
        f.setReadOnly(True)
        f.setMaximumBlockCount(20000)
        if not mit:
            f.faerber.setDocument(None)
        t0 = time.perf_counter()
        for i in range(n):
            f.appendPlainText(f"FEHLER: Zeile {i}" if i % 7 == 0 else f"Zeile {i} ohne Besonderheit")
        return time.perf_counter() - t0
    mit, ohne = lauf(True), lauf(False)
    print(f"      {n} Zeilen anhängen: mit Färber {mit:.3f} s, ohne {ohne:.3f} s")
    check(f"{n} Zeilen anhängen: mit Färber höchstens 3-fache Zeit plus 0,5 s",
          mit <= 3 * ohne + 0.5, f"mit {mit:.3f} s, ohne {ohne:.3f} s")


def test_waehle_festschrift():
    """Die Wahl der Schrift als reine Logik - ohne Schriftdatenbank pruefbar."""
    from statik3d.gui import design as dsg
    _app()
    fest = {"Consolas", "Cascadia Mono", "Courier New", "DejaVu Sans Mono"}

    def ist_fest(n):
        return n in fest
    w = dsg.waehle_festschrift
    check("Consolas vorhanden: Consolas",
          w(["Segoe UI", "Consolas", "Courier New", "Tahoma"], ist_fest) == "Consolas")
    check("ohne Consolas: Cascadia Mono",
          w(["Segoe UI", "Courier New", "Cascadia Mono"], ist_fest) == "Cascadia Mono")
    check("nur Courier New: Courier New", w(["Segoe UI", "Courier New"], ist_fest) == "Courier New")
    check("Linux: DejaVu Sans Mono", w(["Noto Sans", "DejaVu Sans Mono"], ist_fest) == "DejaVu Sans Mono")
    check("keine der Schriften da: None", w(["Segoe UI", "Tahoma"], ist_fest) is None)
    check("leere Liste (offscreen ohne Schriften): None", w([], ist_fest) is None)
    check("gleich benannt, aber nicht fest: übersprungen",
          w(["Consolas", "Courier New"], lambda n: n == "Courier New") == "Courier New")
    check("Schreibweise der Liste egal (consolas)", w(["consolas"], lambda n: True) == "consolas")
    s = dsg.festschrift_stil(11)
    check("Stilzeile: Familie in Anführungszeichen und Größe",
          s.startswith('font-family: "') and s.rstrip().endswith("font-size: 11px;"), s)
    check("„monospace“ steht nicht fest im Stil, solange es eine echte Schrift gibt",
          "monospace" not in s or not dsg._schriften_vorhanden(), s)


def _echte_schrift(w_log=None):
    """Mit Schriftdatenbank (Desktop): die Schrift im Widget ist wirklich fest.
    Offscreen gibt es gar keine Schriften - dann wird nur gesagt, dass nichts
    zu pruefen war."""
    from PySide6 import QtGui, QtWidgets
    from statik3d.gui import design as dsg
    _app()
    if not dsg._schriften_vorhanden():
        print("      (keine Schriftdatenbank - offscreen -, echte Schrift nicht pruefbar;"
              " Lauf mit QT_QPA_PLATFORM=windows --nur-schrift)")
        return
    eltern = QtWidgets.QMainWindow()
    eltern.setStyleSheet(dsg.stil())       # wie das Hauptfenster: Segoe UI fuer alles
    if w_log is None:
        w_log = QtWidgets.QPlainTextEdit(eltern)
        w_log.setStyleSheet(dsg.festschrift_stil())
    w_log.ensurePolished()
    i = QtGui.QFontInfo(w_log.font())
    check("Windows: die Schrift des Protokolls ist wirklich festbreit",
          i.fixedPitch(), f"{i.family()}, fest={i.fixedPitch()}, {i.pixelSize()} px")
    check("… und es ist nicht die Proportionalschrift der Oberfläche",
          i.family() not in ("Segoe UI", "Tahoma", "MS Shell Dlg 2"), i.family())
    check("… in der gewählten Familie", i.family().lower() == dsg.festschrift_familie().lower(),
          f"{i.family()} gegen {dsg.festschrift_familie()}")


def test_schrift_im_fenster():
    """Protokoll und die drei Textfelder rechts benutzen dieselbe Stilzeile."""
    from statik3d.gui import design as dsg
    w, app = _fenster()
    soll = dsg.festschrift_stil(11)
    for name in ("log", "txt_regelwerk", "txt_summary", "txt_res"):
        feld = getattr(w, name)
        ist = feld.styleSheet().strip()
        check(f"{name}: Stilzeile aus dem gemeinsamen Helfer", ist == soll.strip(), ist)
        check(f"{name}: nicht mehr „monospace“, solange es eine echte Festbreitenschrift gibt",
              "monospace" not in ist or not dsg._schriften_vorhanden(), ist)
    w.log.ensurePolished()
    _echte_schrift(w.log)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    nur_schrift = "--nur-schrift" in sys.argv
    tests = ((test_waehle_festschrift, _echte_schrift) if nur_schrift else
             (test_zeilenarten_im_fenster, test_aufrufe_des_programms,
              test_text_bleibt_wie_geschrieben, test_leistung_je_zeile,
              test_waehle_festschrift, test_schrift_im_fenster))
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
