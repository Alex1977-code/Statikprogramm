"""
Protokoll lesbar (Plan-Schritt 9a, 02.10.2026): FEHLER rot, WARNUNG orange,
Abschnitte fett, eine echte Festbreitenschrift.

* Die Zeilen werden ueber einen Syntaxfaerber am Dokument gefaerbt - der Text
  des Protokolls (toPlainText) bleibt Zeichen fuer Zeichen derselbe, denn sehr
  viele Pruefungen lesen ihn so.
* FEHLER-Zeile: ganze Zeile in der Fehlerfarbe der Oberflaeche
  (design.FARBEN["schlecht"]); WARNUNG-Zeile in der Textfarbe der Warnung
  (FARBEN["warn_text"], dunkler als FARBEN["warn"]: 11-px-Text braucht nach
  WCAG 4,5 zu 1 auf Weiss, geprueft in test_kontrast_der_protokollfarben);
  Abschnittskopf („--- Titel ---“): fett.
* Schrift: unter Windows ist „monospace“ kein Schriftname - die Vorgabe wurde
  zu Tahoma, einer Proportionalschrift (gemessen 02.10.2026). Jetzt waehlt
  design.festschrift_familie die erste wirklich festbreite Schrift. Dasselbe
  gilt fuer die Dialoge, die „Courier New“ per setFont verlangten (das Stilblatt
  des Fensters hob es auf): Anschluesse, Update-Befund, Anschlussdialog,
  Querschnittsdialog.

Aufruf:  python -m tests.test_protokoll_lesbar
         python -m tests.test_protokoll_lesbar --nur-schrift   (ohne Hauptfenster,
         mit QT_QPA_PLATFORM=windows: dann gibt es Schriften, offscreen gibt es
         keine; der normale Lauf startet das unter Windows selbst als
         Unterprozess und uebernimmt die Pruefungen)
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
    return (QtGui.QColor(FARBEN["schlecht"]).name(), QtGui.QColor(FARBEN["warn_text"]).name())


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
    t, fm = schreibe("  S1: FEHLER RuntimeError: Probe")
    check("Stichwort nach „Name:“ als erstem Wort: FEHLER rot",
          fm == [(0, len(t), rot, False)], str(fm))
    t, fm = schreibe("  S1: WARNUNG Kombination K9 ohne Ergebnis")
    check("Stichwort nach „Name:“ als erstem Wort: WARNUNG in der Warnfarbe",
          fm == [(0, len(t), warn, False)], str(fm))
    t, fm = schreibe("ABBRUCH: Berechnung abgebrochen")
    check("ABBRUCH als erstes Wort zählt wie FEHLER (rot)", fm == [(0, len(t), rot, False)], str(fm))

    # was nur so aussieht, bleibt unberuehrt
    for text in ("Die Abnahme meldet FEHLER mitten im Satz",
                 "Situation S1: Stellung S9 - WARNUNG: gibt es nicht",
                 "Klappe offen: WARNUNG Name aus zwei Wörtern (Regel: erstes Wort)",
                 "Hinweis ABBRUCH ohne Doppelpunkt davor und nicht als erstes Wort",
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


def _leuchtdichte(farbe):
    """Relative Leuchtdichte nach WCAG 2.x (sRGB) einer Farbe „#rrggbb“."""
    r, g, b = (int(farbe[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _kontrast(vorder, grund):
    """Kontrastverhaeltnis nach WCAG 2.x: (hell + 0,05) / (dunkel + 0,05)."""
    a, b = _leuchtdichte(vorder), _leuchtdichte(grund)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def test_kontrast_nur_rechnung():
    """11-px-Text braucht nach WCAG AA mindestens 4,5 zu 1 auf dem Grund des
    Protokolls (design.FARBEN["flaeche"]). Die Warnfarbe des Modellbaums
    (FARBEN["warn"], 3,6 zu 1) reicht dafuer nicht und bleibt fuer Flaechen
    und grosse Zeichen, wie sie ist."""
    from statik3d.gui import design as dsg
    F = dsg.FARBEN
    grund = F["flaeche"]
    k_fehler = _kontrast(F["schlecht"], grund)
    check("Fehlerfarbe auf dem Protokollgrund: Kontrast mindestens 4,5 zu 1",
          k_fehler >= 4.5, f"{F['schlecht']} auf {grund}: {k_fehler:.2f}")
    check("Warnfarbe für Text (warn_text) gibt es und erreicht 4,5 zu 1",
          "warn_text" in F and _kontrast(F.get("warn_text", "#ffffff"), grund) >= 4.5,
          f"{F.get('warn_text')}: {_kontrast(F.get('warn_text', '#ffffff'), grund):.2f}")
    check("Warnfarbe für Text ist ein Orange (Farbton 20 bis 40 Grad), kein Braun-Schwarz",
          "warn_text" in F and 20 <= _farbton(F["warn_text"]) <= 40,
          f"{_farbton(F.get('warn_text', '#000000')):.0f} Grad")
    check("FARBEN[\"warn\"] für Modellbaum und Filmstreifen ist unverändert (#b7791f)",
          F["warn"] == "#b7791f", F["warn"])
    check("das Protokoll nimmt warn_text, nicht warn (und unterscheidet es von Rot)",
          F.get("warn_text") not in (None, F["warn"], F["schlecht"]), str(F.get("warn_text")))
    # die Rechnung selbst an einem bekannten Wert: Schwarz auf Weiss ist 21 zu 1
    check("Kontrastrechnung: Schwarz auf Weiss ist 21 zu 1",
          abs(_kontrast("#000000", "#ffffff") - 21.0) < 1e-6, f"{_kontrast('#000000', '#ffffff'):.4f}")


def test_kontrast_der_protokollfarben():
    """Wie test_kontrast_nur_rechnung, dazu die Zeile im Fenster."""
    from statik3d.gui import design as dsg
    test_kontrast_nur_rechnung()
    w, app = _fenster()
    rot, warn = _farben()
    w.log.clear()
    w.log.appendPlainText("WARNUNG: Kontrastprobe")
    z = _letzte(w)
    check("WARNUNG-Zeile im Fenster hat die Textfarbe der Warnung mit Kontrast >= 4,5",
          z[1] and z[1][0][2] == warn and _kontrast(z[1][0][2], dsg.FARBEN["flaeche"]) >= 4.5,
          f"{z[1]}")


def _farbton(farbe):
    import colorsys
    r, g, b = (int(farbe[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360.0


def _felder_der_modalen_maske(app, aufruf, versuche=100, zaehler=None):
    """Ruft *aufruf* (enthaelt ein ``exec()``); der Zeitgeber merkt sich, sobald
    die Maske steht, Stilzeile und Schrift ihrer Textfelder und schliesst sie.
    Steht nach *versuche* Versuchen (alle 50 ms) keine Maske da, gibt er auf und
    schliesst eine sichtbare Maske, damit ``exec()`` nicht ewig haengt; kehrt
    *aufruf* ohne Maske zurueck, plant er nichts mehr ein. *zaehler* bekommt je
    leerem Versuch einen Eintrag. Zurueck: [(Titel, Stilzeile, Familie, fest?), ...]."""
    from PySide6 import QtCore, QtGui, QtWidgets
    gefunden = []
    fertig = [False]
    leer = [0]

    def zu():
        if fertig[0]:
            return
        d = QtWidgets.QApplication.activeModalWidget()
        if d is None:
            leer[0] += 1
            if zaehler is not None:
                zaehler.append(leer[0])
            if leer[0] < versuche:
                QtCore.QTimer.singleShot(50, zu)
            else:
                for x in QtWidgets.QApplication.topLevelWidgets():
                    if isinstance(x, QtWidgets.QDialog) and x.isVisible():
                        x.reject()
            return
        for t in d.findChildren(QtWidgets.QPlainTextEdit):
            t.ensurePolished()
            i = QtGui.QFontInfo(t.font())
            gefunden.append((d.windowTitle(), t.styleSheet().strip(), i.family(), i.fixedPitch()))
        d.reject()
    QtCore.QTimer.singleShot(0, zu)
    try:
        aufruf()
    finally:
        fertig[0] = True
    return gefunden


def test_zeitgeber_der_modalen_maske_gibt_auf():
    """Der Zeitgeber des Helfers plant sich nicht endlos neu ein."""
    from PySide6 import QtCore
    app = _app()

    def warten(ms):
        schleife = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, schleife.quit)
        schleife.exec()
    zaehler = []
    got = _felder_der_modalen_maske(app, lambda: warten(500), versuche=3, zaehler=zaehler)
    check("ohne Maske: der Zeitgeber gibt nach 3 Versuchen auf (0,5 s hätten 10 gegeben)",
          got == [] and len(zaehler) == 3, str(zaehler))
    z2 = []
    _felder_der_modalen_maske(app, lambda: None, versuche=3, zaehler=z2)
    warten(300)
    check("Aufruf ohne Maske kehrt zurück: der Zeitgeber plant nichts mehr ein", z2 == [], str(z2))


def test_echte_schrift_im_unterprozess():
    """Die Wirkung der Schrift zeigt nur eine Plattform mit Schriften. Unter Windows
    startet der normale Lauf darum einen Unterprozess mit QT_QPA_PLATFORM=windows
    und --nur-schrift (baut Widgets, zeigt kein Fenster) und uebernimmt dessen
    Pruefungen; sonst wird mit Hinweis uebersprungen."""
    import json
    import subprocess
    if sys.platform != "win32":
        print("      (nicht Windows: Unterprozess mit QT_QPA_PLATFORM=windows übersprungen)")
        return
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "windows"
    env["PYTHONUTF8"] = "1"
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-m", "tests.test_protokoll_lesbar", "--nur-schrift"],
                       cwd=wurzel, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    marke = "ERGEBNISSE_JSON "
    zeilen = [z for z in r.stdout.splitlines() if z.startswith(marke)]
    if not zeilen:
        check("Unterprozess (windows, --nur-schrift) liefert Ergebnisse", False,
              (r.stderr or r.stdout)[-300:].replace("\n", " | "))
        return
    erg = json.loads(zeilen[-1][len(marke):])
    check("Unterprozess (windows, --nur-schrift): mindestens 20 Prüfungen übernommen",
          len(erg) >= 20, str(len(erg)))
    for name, ok in erg:
        check(f"[windows] {name}", ok)
    check("Unterprozess (windows, --nur-schrift) endete mit 0", r.returncode == 0, str(r.returncode))


def _fest_pruefen(name, stil, familie, fest, soll):
    """Die Stilzeile ist die des Helfers; mit Schriftdatenbank (Desktop) meldet
    QFontInfo am Widget eine feste Schrift in der gewaehlten Familie."""
    from statik3d.gui import design as dsg
    check(f"{name}: Stilzeile aus dem gemeinsamen Helfer", stil == soll.strip(), stil)
    check(f"{name}: kein „monospace“, solange es eine echte Festbreitenschrift gibt",
          "monospace" not in stil or not dsg._schriften_vorhanden(), stil)
    if dsg._schriften_vorhanden():
        check(f"{name}: QFontInfo meldet eine feste Schrift", fest and familie.lower() ==
              dsg.festschrift_familie().lower(), f"{familie}, fest={fest}")


def test_weitere_stellen_mit_festschrift():
    """Die vier weiteren Stellen, die „Courier New“ per setFont oder „monospace“
    verlangten: Anschlüsse (show_joints), Update-Befund (update_report),
    Anschlussdialog (JointDialog.txt) und die Profilwerte im Querschnittsdialog
    (SectionDialog.props). Unter dem Stilblatt des Fensters hob dieses das
    gesetzte Schriftbild auf (gemessen: Segoe UI statt Courier New)."""
    from PySide6 import QtWidgets
    from statik3d.gui import design as dsg
    from statik3d.gui.dialogs import JointDialog, SectionDialog
    from statik3d.joints.templates import TYPES
    from statik3d.model import Material, Section
    w, app = _fenster()
    soll = dsg.festschrift_stil(None)
    check("festschrift_stil(None) setzt nur die Familie, keine Größe",
          soll.startswith('font-family: "') and "font-size" not in soll and soll.endswith(";"), soll)

    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    n = [m.add_node(6.0 * i, 0.0, 0.0) for i in range(2)]
    e = m.add_element("beam", [n[0], n[1]], "S355", "IPE 400")
    m.add_joint("A1", next(iter(TYPES)), e, 1)
    w.analysis = None

    # Anschluesse: die Maske zeigt den Befund im Klartext
    got = _felder_der_modalen_maske(app, w.show_joints)
    check("Anschlüsse: die Maske hat ein Textfeld", len(got) == 1, str(got))
    if got:
        _fest_pruefen("Anschlüsse (main.py show_joints)", got[0][1], got[0][2], got[0][3], soll)

    # Update-Befund: der Befund kommt aus einem Arbeiter - hier ausgeschaltet
    w._run_update_worker = lambda *a, **k: None
    got = _felder_der_modalen_maske(app, w.update_report)
    check("Update-Befund: die Maske hat ein Textfeld", len(got) == 1, str(got))
    if got:
        _fest_pruefen("Update-Befund (main.py update_report)", got[0][1], got[0][2], got[0][3], soll)

    # Anschlussdialog und Querschnittsdialog: ohne exec, nur gebaut
    d = JointDialog(w, m, e, 1, {"N": -100e3, "Vz": 90e3, "My": 180e3})
    d.txt.ensurePolished()
    from PySide6 import QtGui
    i = QtGui.QFontInfo(d.txt.font())
    _fest_pruefen("Anschlussdialog (dialogs.py JointDialog.txt)", d.txt.styleSheet().strip(),
                  i.family(), i.fixedPitch(), soll)
    d.close()
    s = SectionDialog(w)
    s.props.ensurePolished()
    i = QtGui.QFontInfo(s.props.font())
    _fest_pruefen("Querschnittsdialog (dialogs.py SectionDialog.props)", s.props.styleSheet().strip(),
                  i.family(), i.fixedPitch(), soll)
    s.close()


def _echte_schrift_dialoge():
    """Ohne Hauptfenster (Lauf mit QT_QPA_PLATFORM=windows --nur-schrift): die
    beiden Dialoge aus dialogs.py unter dem Stilblatt des Fensters; mit Schriften
    meldet QFontInfo dort die feste Schrift."""
    from PySide6 import QtGui, QtWidgets
    from statik3d.gui import design as dsg
    from statik3d.gui.dialogs import JointDialog, SectionDialog
    from statik3d.joints.templates import TYPES
    from statik3d.model import Material, Model, Section
    _app()
    if not dsg._schriften_vorhanden():
        print("      (keine Schriftdatenbank - offscreen -, Dialoge nicht pruefbar)")
        return
    eltern = QtWidgets.QMainWindow()
    eltern.setStyleSheet(dsg.stil())
    soll = dsg.festschrift_stil(None)
    m = Model("Probe")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("IPE 400"))
    n = [m.add_node(6.0 * i, 0.0, 0.0) for i in range(2)]
    e = m.add_element("beam", [n[0], n[1]], "S355", "IPE 400")
    d = JointDialog(eltern, m, e, 1, {"N": -100e3, "Vz": 90e3, "My": 180e3})
    d.txt.ensurePolished()
    i = QtGui.QFontInfo(d.txt.font())
    _fest_pruefen("Anschlussdialog ohne Hauptfenster", d.txt.styleSheet().strip(),
                  i.family(), i.fixedPitch(), soll)
    s = SectionDialog(eltern)
    s.props.ensurePolished()
    i = QtGui.QFontInfo(s.props.font())
    _fest_pruefen("Querschnittsdialog ohne Hauptfenster", s.props.styleSheet().strip(),
                  i.family(), i.fixedPitch(), soll)


def test_meldungen_der_echten_erzeuger():
    """Meldungen, die das Programm wirklich schreibt und die das Stichwort nicht
    als erstes Wort tragen: die Stellungsreihe (bridges/positions.py: „  S1:
    WARNUNG ...“, „  S1: FEHLER ...“) und der ABBRUCH (main.py, solver.py).
    Die Zeilen der Stellungsreihe baut ihr eigener Code - hier mit einer kleinen
    echten Rechnung; die Quelle der Warnung und der Fehler ist ersetzt."""
    from unittest import mock
    from statik3d.bridges import positions as P
    from statik3d.bridges.positions import Stellung, Stellungsreihe
    from statik3d.model import Material, Section
    w, app = _fenster()
    rot, warn = _farben()
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(4.0 * i, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300")
    m.support(n[0], "all", name="Einspannung")
    g = next(iter(m.load_cases))
    m.load_node(n[-1], Fz=-5e3, case=g)

    def reihe_rechnen():
        reihe = Stellungsreihe(m, "Probe")
        reihe.add(Stellung("S1", 0.0, "geschlossen", faelle=[g]))
        reihe.rechnen(kombinationen=False, nachweise=False)
        w.log.clear()
        for z in reihe.log:                  # wie MainWindow.stellungen_rechnen
            w.info(z)
        return {t: f for t, f in _zeilen(w)}

    with mock.patch.object(P.StellungsErgebnis, "warnungen",
                           property(lambda self: ["Kombination K9 ohne Ergebnis"])):
        zeilen = reihe_rechnen()
    wz = [t for t in zeilen if t.startswith("  S1: WARNUNG")]
    check("Stellungsreihe: „  S1: WARNUNG …“ steht in der Warnfarbe, ganze Zeile",
          len(wz) == 1 and zeilen[wz[0]] == [(0, len(wz[0]), warn, False)], str(zeilen))
    uz = [t for t in zeilen if t.startswith("  S1: u_max")]
    check("Stellungsreihe: „  S1: u_max = …“ bleibt ohne Format",
          len(uz) == 1 and zeilen[uz[0]] == [], str(uz))
    kz = [t for t in zeilen if t.startswith("Stellung S1")]
    check("Stellungsreihe: Kopfzeile „Stellung S1 (0°) - geschlossen“ bleibt ohne Format",
          len(kz) == 1 and zeilen[kz[0]] == [], str(kz))

    with mock.patch("statik3d.solver.solve_all",
                    side_effect=RuntimeError("Faktorisierung gescheitert")):
        zeilen = reihe_rechnen()
    fz = [t for t in zeilen if t.startswith("  S1: FEHLER")]
    check("Stellungsreihe: „  S1: FEHLER …“ steht rot, ganze Zeile",
          len(fz) == 1 and zeilen[fz[0]] == [(0, len(fz[0]), rot, False)], str(zeilen))

    # ABBRUCH: die Zeilen aus main.py (_abbruch_teil_zeigen, Kontaktabbruch) und
    # solver.py (Zusammenfassung); eine Folgezeile bleibt, wie sie ist
    w.log.clear()
    w.log.appendPlainText(
        "ABBRUCH: gezeigt wird die Verformung der letzten Kontakt-Iteration (1) als Ergebnis "
        "„LF1 - Abbruch (Iteration 1)“ - kein Gleichgewicht, keine Auflagerkräfte.")
    w.log.appendPlainText(
        "ABBRUCH: Berechnung abgebrochen (nach 7 s) - 1 Lastfall bleibt erhalten, 2 Kombinationen offen.\n"
        "    Die gerechneten Ergebnisse stehen in der Auswahl und im Modellbaum wie sonst.\n"
        "    Ein neuer Lauf rechnet alles noch einmal.")
    w.log.appendPlainText("ABBRUCH                 : Kontakt-Iteration 2: Gleichungssystem singulär")
    z = _zeilen(w)
    check("ABBRUCH (Kontaktabbruch) als erstes Wort: ganze Zeile rot",
          z[0][1] == [(0, len(z[0][0]), rot, False)], str(z[0]))
    check("ABBRUCH (Sammellauf) als erstes Wort: rot, die eingerückten Folgezeilen nicht",
          z[1][1] == [(0, len(z[1][0]), rot, False)] and z[2][1] == [] and z[3][1] == [], str(z[1:4]))
    check("ABBRUCH der Zusammenfassung („ABBRUCH      : …“): rot",
          z[4][1] == [(0, len(z[4][0]), rot, False)], str(z[4]))

    # was bewusst ungefaerbt bleibt: das Stichwort mitten im Satz (main.py, Situation)
    w.log.clear()
    w.log.appendPlainText("Situation S1: Stellung S9 + 2 Lastfälle - WARNUNG: die Stellung „S9“ gibt es nicht; "
                          "die Modellprüfung meldet es")
    w.log.appendPlainText("Abgebrochen wegen ABBRUCH mitten im Satz")
    z = _zeilen(w)
    check("Stichwort mitten im Satz („… - WARNUNG: …“): ohne Format",
          z[0][1] == [] and z[1][1] == [], str(z))


def test_zeilenende_bei_zeichen_ausserhalb_der_grundebene():
    """Qt zaehlt in UTF-16-Einheiten, Python in Codepunkten: eine Zeile mit einem
    Emoji im Pfad muss bis zum Ende gefaerbt sein."""
    w, app = _fenster()
    rot, warn = _farben()
    w.log.clear()
    smiley = "\U0001F600"
    zeilen = (f"--- Modell geöffnet: x{smiley}.s3d ---",
              f"FEHLER: Datei x{smiley}.s3d nicht lesbar",
              f"WARNUNG: {smiley}{smiley} im Namen",
              f"  S1: WARNUNG {smiley}")
    for text in zeilen:
        w.log.appendPlainText(text)
    soll = [(None, True), (rot, False), (warn, False), (warn, False)]
    for (text, fm), (farbe, fett), z in zip(_zeilen(w), soll, zeilen):
        n16 = len(z.encode("utf-16-le")) // 2
        check(f"UTF-16-Länge: „{z[:24]}…“ ganze Zeile ({n16} Einheiten, {len(z)} Zeichen)",
              n16 > len(z) and text == z and fm == [(0, n16, farbe, fett)], str(fm))


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
    tests = ((test_waehle_festschrift, _echte_schrift, _echte_schrift_dialoge,
              test_kontrast_nur_rechnung) if nur_schrift else
             (test_zeilenarten_im_fenster, test_meldungen_der_echten_erzeuger,
              test_zeilenende_bei_zeichen_ausserhalb_der_grundebene,
              test_aufrufe_des_programms,
              test_text_bleibt_wie_geschrieben, test_leistung_je_zeile,
              test_kontrast_der_protokollfarben,
              test_waehle_festschrift, test_schrift_im_fenster,
              test_zeitgeber_der_modalen_maske_gibt_auf,
              test_weitere_stellen_mit_festschrift,
              test_echte_schrift_im_unterprozess))
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    if nur_schrift:                    # fuer den Lauf als Unterprozess (test_echte_schrift_im_unterprozess)
        import json
        print("ERGEBNISSE_JSON " + json.dumps(RESULTS, ensure_ascii=True))
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
