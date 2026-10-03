"""
Beenden ohne Absturz (Plan-Teilpaket C15, 03.10.2026).

Befund aus der Gegenpruefung von 8b: Pruefungen endeten sporadisch nach dem
Ergebnis mit einer Zugriffsverletzung beim Beenden (Exit -1073741819), oft auch
mit Exitcode 0 - zu sehen nur mit ``-X faulthandler`` als „Windows fatal
exception: access violation“. Ursache: Ein ``deleteLater``, das bei ``os._exit``
noch vorgemerkt ist, an einem Widget mit einem Lambda am Signal (PySide haengt
dafuer eine eigene Verbindung an ``destroyed``) oder an einem Fenster, das schon
zu sehen war. In einer Pruefung bleibt jedes ``deleteLater`` vorgemerkt, denn
``processEvents`` ausserhalb von ``exec`` loescht nichts. Seit C15 holt
``statik3d.gui.entsorgen`` vor ``os._exit`` alle vorgemerkten Loeschungen nach.

Die erste Fassung von C15 trennte stattdessen vor dem Loeschen alle Signale und
gab Fenster mit ``destroy()`` frei. Das liess die Rauchpruefung auf dem Desktop
beim normalen Ende (sys.exit) abstuerzen, schnitt Empfaenger ab, die nach dem
Schliessen noch an der Reihe waren, und liess Qts Stilblatt-Zwischenspeicher
wachsen. Diese Pruefung verlangt darum auch: Entsorgen trennt nichts und
zerstoert kein Fenster nativ.

Ablauf: Ein kleines Programm-Skript (``--kind``) laeuft in eigenen Prozessen,
sechsmal mit ``os._exit(0)`` am Ende (wie die anderen Pruefungen) und dreimal
mit ``w.close()`` und ``sys.exit(0)`` (wie die Rauchpruefung). Es oeffnet und
schliesst eine Stab-Maske, eine Uebersicht aus dem Baum, eine Maske mit der
Leiste „Übernehmen | Verwerfen“ (13m), das Kontextregister, die
Ergebnissteuerung nach einer Rechnung mit Masken darunter, das
Rechtsklickmenue, die Kuerzelliste, den Werkzeug-Dialog (Qt ersetzt dessen
Knoepfe), ein Beulfeld mit geloeschter Zeile (Qt loescht das Zell-Widget) und
die Maske „Darstellung“, entsorgt in einer inneren Schleife und mitten in einer
Signalausgabe. Verlangt wird in jedem Lauf Exitcode 0 und keine Zeile „Windows
fatal exception“ oder „Fatal Python error“ von faulthandler.

Aufruf:  python -m tests.test_beenden_ohne_absturz
"""
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import tokenize

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

RESULTS = []
#: so oft laeuft das Kind mit os._exit und mit sys.exit am Ende
LAEUFE_OS_EXIT = 6
LAEUFE_SYS_EXIT = 3


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


# ---------------------------------------------------------------------------
# Das Kind: ein Programmlauf, der Masken und Seiten baut und wieder schliesst
# ---------------------------------------------------------------------------
#: Objekte des Kindes, die bis zum Ende leben (nie geloescht)
_BEHALTEN = []


def _melden(name, ok, detail=""):
    print(f"SCHRITT {name} {'ja' if ok else 'nein'} {detail}", flush=True)


def _ruhe(app, n=3):
    """Wie in allen Pruefungen nur processEvents: ein deleteLater bleibt dabei
    vorgemerkt - genau der Zustand, in dem es beim Beenden abstuerzte."""
    for _ in range(n):
        app.processEvents()


def _alle(baum):
    from PySide6 import QtWidgets
    out = []
    it = QtWidgets.QTreeWidgetItemIterator(baum)
    while it.value():
        out.append(it.value())
        it += 1
    return out


def _art(it):
    from PySide6 import QtCore
    return str(it.data(0, QtCore.Qt.UserRole) or "")


def _key(it):
    from PySide6 import QtCore
    return it.data(0, QtCore.Qt.UserRole + 1)


def _eintrag(w, art=None, text=None):
    """Mit ``art`` der erste Eintrag (eine Zeile mit Schluessel) dieser Art,
    mit ``text`` der Zweig dieses Namens. Seit 8b traegt auch der Zweig
    „Knoten“ die Art „knoten“, und ein Klick auf einen Zweig waehlt nichts."""
    for it in _alle(w.baum):
        if art is not None and (_art(it) != art or _key(it) is None):
            continue
        if text is not None and (it.text(0) != text or _key(it) is not None):
            continue
        return it
    return None


def _klick(w, app, item):
    """Ein echter Mausklick auf eine Zeile des Modellbaums."""
    from PySide6 import QtCore, QtTest
    b = w.baum
    p = item.parent()
    while p is not None:
        p.setExpanded(True)
        p = p.parent()
    b.scrollToItem(item)
    app.processEvents()
    QtTest.QTest.mouseClick(b.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            b.visualItemRect(item).center())
    _ruhe(app)


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _verbunden(wurzel) -> int:
    """Summe der Empfaenger an ``destroyed`` im Baum unter ``wurzel`` - daran
    haengen PySides Buchfuehrung fuer Lambdas und Qts eigenes Aufraeumen
    (Stilblatt). Entsorgen darf daran nichts aendern."""
    from PySide6 import QtCore
    sig = QtCore.SIGNAL("destroyed()")
    return sum(o.receivers(sig) for o in [wurzel] + wurzel.findChildren(QtCore.QObject))


def _kind_fenster():
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    B = QtWidgets.QMessageBox
    for name, rueck in (("critical", B.Ok), ("warning", B.Ok), ("information", B.Ok), ("question", B.No)):
        setattr(B, name, staticmethod(lambda *a, _r=rueck, **k: _r))
    QtWidgets.QDialog.exec = lambda self, *a, **k: 0
    # Kein Menue und keine Rueckfrage darf stehen bleiben: QMenu.exec laesst
    # sich in PySide6 nicht ersetzen (tests/test_rechtsklick.py), darum
    # schliesst ein Takt jedes Menue und jedes modale Fenster gleich wieder.
    # Er lebt bis zum Ende und wird nie geloescht.

    def nachsehen():
        for p in (QtWidgets.QApplication.activePopupWidget(), QtWidgets.QApplication.activeModalWidget()):
            if p is not None:
                p.close()
    takt = QtCore.QTimer()
    takt.setInterval(5)
    takt.timeout.connect(nachsehen)
    takt.start()
    _BEHALTEN.append(takt)
    from statik3d.gui.main import MainWindow
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler = []
    w.error = lambda msg, *a, **k: w.fehler.append(str(msg))
    return w, app


def _kind(ende: str) -> None:
    import faulthandler
    faulthandler.enable()
    import shiboken6
    from PySide6 import QtCore, QtWidgets
    w, app = _kind_fenster()
    #: Name -> (Objekt, Empfaenger an destroyed, solange es offen war)
    zu = {}

    def merken(name, obj):
        if obj is not None and name not in zu:
            zu[name] = (obj, _verbunden(obj))

    try:
        from statik3d.gui import entsorgen as E
    except ImportError:
        E = None
    _melden("ende_holt_loeschungen_nach", E is not None and os._exit.__name__ == "_exit_nach_loeschen",
            getattr(os._exit, "__name__", "?"))

    w.load_example("hall")
    _ruhe(app)

    # A. Rechtsklick in der Ansicht: das Menue des vorigen geht (sein exec ist
    #    eine Ereignisschleife und loescht, was bis dahin vorgemerkt war)
    pos = QtCore.QPoint(20, 20)
    w._viewport_menu(pos)
    merken("rechtsklickmenue", getattr(w, "_kontextmenue_zuletzt", None))
    w._viewport_menu(pos)
    _ruhe(app)

    # B. Entsorgen in einer kurzen inneren Schleife: danach bleibt es bis zum
    #    Ende vorgemerkt. Danach laeuft keine Schleife mehr - alles, was ab
    #    hier geschlossen wird, wartet bis zum Ende auf sein deleteLater.
    innen = QtWidgets.QWidget(w)
    innen.show()
    knopf_innen = QtWidgets.QPushButton("x", innen)
    knopf_innen.clicked.connect(lambda *_a: None)
    merken("in_innerer_schleife", innen)
    schleife = QtCore.QEventLoop()

    def _in_der_schleife():
        if E is not None:
            E.entsorgen(innen)
        else:
            innen.deleteLater()
        schleife.quit()
    QtCore.QTimer.singleShot(0, _in_der_schleife)
    schleife.exec()

    # 1. Stab-Maske ueber den Baum, geschlossen ueber den Maskenrand
    _klick(w, app, _eintrag(w, art="stab"))
    mk = _maske(w)
    _melden("stabmaske_offen", mk is not None, getattr(mk, "titel", ""))
    merken("stabmaske", mk)
    w.maskenrand.schliessen()
    _ruhe(app)

    # 2. Uebersicht aus dem Baum, ersetzt durch die naechste
    _klick(w, app, _eintrag(w, text="Lastfälle"))
    mk = _maske(w)
    _melden("uebersicht_offen", mk is not None, getattr(mk, "titel", ""))
    merken("uebersicht_lastfaelle", mk)
    _klick(w, app, _eintrag(w, text="Knoten"))
    merken("uebersicht_knoten", _maske(w))

    # 3. Kontextregister: ein Stab gewaehlt, dann ein Knoten - das erste geht
    _klick(w, app, _eintrag(w, art="stab"))
    reg = w.ribbon._kontext
    _melden("kontextregister_offen", reg is not None, w.ribbon._kontext_name)
    merken("kontextregister", reg)
    merken("stabmaske_2", _maske(w))
    _klick(w, app, _eintrag(w, art="knoten"))
    _melden("kontextregister_ersetzt", reg is not None and w.ribbon._kontext is not reg
            and "Knoten" in w.ribbon._kontext_name, w.ribbon._kontext_name)

    # 4. Leiste „Übernehmen | Verwerfen“ (13m): Knoten aendern, im Baum
    #    weiter - die Leiste haelt an, „Verwerfen“ fuehrt den Klick aus
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    _melden("knotenmaske_offen", mk is not None, getattr(mk, "titel", ""))
    if mk is not None:
        merken("knotenmaske", mk)
        mk.setzen("x", 7.5)
        _ruhe(app)
        _klick(w, app, _eintrag(w, art="stab"))
        leiste = getattr(w, "aenderungsleiste", None)
        sichtbar = leiste is not None and leiste.isVisible()
        _melden("leiste_offen", sichtbar)
        if sichtbar:
            knopf = next((b for b in leiste.findChildren(QtWidgets.QPushButton) if b.text() == "Verwerfen"), None)
            if knopf is not None:
                knopf.click()
            _ruhe(app)
        _melden("leiste_verworfen", _maske(w) is not mk and not (leiste is not None and leiste.isVisible()),
                getattr(_maske(w), "titel", ""))
        merken("stabmaske_nach_leiste", _maske(w))
        w.maskenrand.schliessen()
        _ruhe(app)

    # 5. Rechnung: die Ergebnissteuerung steht oben, Masken darunter
    from statik3d import solver
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an)
    _ruhe(app)
    st = getattr(w, "ergebnissteuerung", None)
    _melden("ergebnissteuerung_sichtbar", st is not None and st.isVisible())
    merken("maske_nach_rechnung", _maske(w))
    for art in ("stab", "knoten"):
        _klick(w, app, _eintrag(w, art=art))
        merken(f"{art}maske_unter_ergebnissteuerung", _maske(w))
    _klick(w, app, _eintrag(w, text="Lastfälle"))
    merken("uebersicht_unter_ergebnissteuerung", _maske(w))
    _melden("ergebnissteuerung_bleibt", st is not None and st.isVisible())

    # 6. Kuerzelliste zweimal: die erste geht - ein Fenster, das zu sehen war;
    #    es darf beim Entsorgen nicht nativ zerstoert werden
    alt = w.kuerzel_zeigen()
    merken("kuerzelliste", alt)
    w.kuerzel_zeigen()
    _melden("fenster_nicht_nativ_zerstoert", shiboken6.isValid(alt) and alt.windowHandle() is not None,
            f"windowHandle {'da' if shiboken6.isValid(alt) and alt.windowHandle() is not None else 'weg'}")
    _ruhe(app)

    # 7. Werkzeug-Dialog neu gefuellt: Qt ersetzt die Knoepfe der Tabelle
    #    (setCellWidget) und loescht die alten selbst mit deleteLater
    from statik3d.gui.werkzeuge_dialog import WerkzeugeDialog
    dlg = WerkzeugeDialog(w)
    _BEHALTEN.append(dlg)
    alte = list(dlg.knoepfe.values())
    _melden("werkzeugknoepfe_da", bool(alte), str(len(alte)))
    for i, b in enumerate(alte):
        merken(f"werkzeugknopf_{i}", b)
    dlg._fuellen()
    _ruhe(app)

    # 8. Beulfeld: eine Zeile loeschen - Qt loescht das Zell-Widget mit
    #    deleteLater; daran haengt hier ein Lambda
    from statik3d.gui import dialogs as dg
    bf = dg.BeulfeldDialog(w, w.model)
    _BEHALTEN.append(bf)
    bf.show()
    _ruhe(app)
    bf._zeile("laengs")
    bf._zeile("quer")
    zelle = bf.tbl.cellWidget(0, 0)
    zelle.currentIndexChanged.connect(lambda *_a: None)
    merken("beulfeld_zelle", zelle)
    bf.tbl.setCurrentCell(0, 1)
    bf._weg()
    _melden("beulfeld_zeile_weg", bf.tbl.rowCount() == 1, f"{bf.tbl.rowCount()} Zeilen")
    bf.close()
    _ruhe(app)

    # 9. Maske „Darstellung“: ihre Schieber haengen am Schieber des Fensters
    #    und werden beim Loeschen abgehaengt (wie im Programm wirklich geloescht)
    fehler = []
    alt_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: fehler.append(f"{t.__name__}: {v}")
    sig = QtCore.SIGNAL("valueChanged(int)")
    n0 = w.sl_lager.receivers(sig)
    mk = w.maske_darstellung()
    _ruhe(app)
    n1 = w.sl_lager.receivers(sig)
    w.maskenrand.schliessen()
    app.sendPostedEvents(mk, QtCore.QEvent.DeferredDelete)
    _ruhe(app)
    geloescht = not shiboken6.isValid(mk)
    w.sl_lager.setValue(w.sl_lager.value() + 1)
    _ruhe(app)
    sys.excepthook = alt_hook
    _melden("darstellung_abgehaengt", n1 > n0 and geloescht and w.sl_lager.receivers(sig) == n0 and not fehler,
            f"Empfaenger {n0} -> {n1} -> {w.sl_lager.receivers(sig)}, geloescht {geloescht}, "
            f"Fehler {fehler[:1]}")

    # 10. Entsorgen mitten in einer Signalausgabe: wer danach an der Reihe ist,
    #     bekommt das Signal noch (die erste Fassung von C15 schnitt ihn ab)
    class _Maske(QtWidgets.QWidget):
        angewendet = QtCore.Signal(object)

    class _Fenster(QtCore.QObject):
        def __init__(self):
            super().__init__()
            self.log = []

        def erster(self, _x):
            self.log.append("erster")

        def dritter(self, _x):
            self.log.append("dritter")
    f_ = _Fenster()
    _BEHALTEN.append(f_)
    m_ = _Maske(w)
    m_.angewendet.connect(f_.erster)
    m_.angewendet.connect(lambda _x: (f_.log.append("zweiter entsorgt"), E.entsorgen(m_) if E else m_.deleteLater()))
    m_.angewendet.connect(f_.dritter)
    m_.angewendet.emit({})
    _melden("spaetere_empfaenger_bekommen_das_signal", f_.log == ["erster", "zweiter entsorgt", "dritter"],
            str(f_.log))
    merken("maske_mitten_im_signal", m_)

    # 11. Entsorgen trennt nichts: Qts eigenes Aufraeumen und PySides
    #     Buchfuehrung an destroyed bleiben, bis wirklich geloescht wird
    probe = QtWidgets.QLabel("Probe", w.centralWidget())
    probe.show()
    knopf_probe = QtWidgets.QPushButton("y", probe)
    knopf_probe.clicked.connect(lambda *_a: None)
    _ruhe(app)
    vorher = _verbunden(probe)
    if E is not None:
        E.entsorgen(probe)
    else:
        probe.deleteLater()
    nachher = _verbunden(probe) if shiboken6.isValid(probe) else -1
    _melden("entsorgen_trennt_nichts", vorher > 0 and nachher >= vorher, f"{vorher} -> {nachher}")

    # zuletzt: geschlossene Objekte trennt niemand; was noch lebt, wartet bis
    # zum Ende auf sein deleteLater (das Ende holt es nach)
    w.maskenrand.schliessen()
    _ruhe(app)
    noch_da = 0
    for name, (obj, vorher) in zu.items():
        lebt = shiboken6.isValid(obj)
        noch_da += lebt
        nachher = _verbunden(obj) if lebt else vorher
        # mehr darf es werden (etwa wenn das Stilblatt ein Feld erst spaet
        # anlegt), weniger nicht: Trennen naehme alles weg
        _melden(f"nicht_getrennt_{name}", nachher >= vorher,
                f"{vorher} -> {nachher if lebt else 'geloescht'}")
    _melden("bis_zum_ende_vorgemerkt", noch_da >= 5, f"{noch_da} von {len(zu)} Objekten")
    print(f"fertig {len(zu)} geschlossene Objekte, Meldungen {len(w.fehler)}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    if ende == "sys":
        # wie die Rauchpruefung: Fenster zu, normales Ende des Interpreters
        w.close()
        app.processEvents()
        print("normales Ende mit sys.exit", flush=True)
        sys.exit(0)
    os._exit(0)


# ---------------------------------------------------------------------------
# Die Pruefung
# ---------------------------------------------------------------------------
def _lauf(ende: str) -> tuple:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONUTF8"] = "1"
    env["STATIK3D_NO_UPDATE_CHECK"] = "1"
    env["STATIK3D_KEIN_BROWSER"] = "1"
    env["STATIK3D_UNGESPEICHERT"] = "verwerfen"
    env["STATIK3D_EINSTELLUNGEN"] = os.path.join(tempfile.mkdtemp(prefix="statik3d_beenden_"),
                                                 "einstellungen.json")
    t0 = time.time()
    r = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "tests.test_beenden_ohne_absturz",
                        "--kind", ende], cwd=HIER, env=env, capture_output=True, timeout=900)
    text = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, text, time.time() - t0


def test_beenden_nach_masken_ohne_absturz():
    abstuerze = {"os": 0, "sys": 0}
    abweichend = set()
    erster = True
    for ende, laeufe in (("os", LAEUFE_OS_EXIT), ("sys", LAEUFE_SYS_EXIT)):
        for i in range(1, laeufe + 1):
            rc, text, dauer = _lauf(ende)
            absturz = ("Windows fatal exception" in text) or ("Fatal Python error" in text)
            abstuerze[ende] += bool(absturz or rc != 0)
            schritte = re.findall(r"^SCHRITT (\S+) (ja|nein)(.*)$", text, re.M)
            fertig = re.search(r"^fertig .*$", text, re.M)
            zeile = next((z.strip() for z in text.splitlines() if "fatal" in z.lower()), "")
            wie = "os._exit" if ende == "os" else "sys.exit"
            check(f"{wie}, Lauf {i}: Exitcode 0 und kein Absturz beim Beenden (faulthandler)",
                  rc == 0 and not absturz, f"Exitcode {rc}, {dauer:.0f} s {zeile}")
            check(f"{wie}, Lauf {i}: das Kind lief bis zum Ende", fertig is not None,
                  fertig.group(0) if fertig else text[-400:].replace("\n", " | "))
            if erster:
                erster = False
                check("das Kind hat alle Schritte gemeldet", len(schritte) >= 30, f"{len(schritte)} Schritte")
                for n, ok, d in schritte:
                    check(f"… {n}", ok == "ja", d.strip())
            else:
                abweichend.update(n for n, ok, _d in schritte if ok != "ja")
    check(f"{LAEUFE_OS_EXIT} Läufe mit os._exit ohne Absturz beim Beenden", abstuerze["os"] == 0,
          f"{abstuerze['os']} von {LAEUFE_OS_EXIT} mit Absturz")
    check(f"{LAEUFE_SYS_EXIT} Läufe mit sys.exit ohne Absturz beim Beenden", abstuerze["sys"] == 0,
          f"{abstuerze['sys']} von {LAEUFE_SYS_EXIT} mit Absturz")
    check("die weiteren Läufe melden dieselben Schritte als erledigt", not abweichend,
          ", ".join(sorted(abweichend))[:200])


def _loeschstellen(pfad: str) -> list:
    """Stellen einer Datei, die an entsorgen() vorbei loeschen: ``.deleteLater``
    (gerufen oder weitergereicht, auch mit Leerzeichen), der Name als Text
    (``getattr(x, "deleteLater")``) und ``WA_DeleteOnClose``. Kommentare und
    Texte zaehlen nicht (tokenize, kein Schnitt am ersten #)."""
    with open(pfad, "rb") as f:
        toks = list(tokenize.tokenize(io.BytesIO(f.read()).readline))
    funde = []
    vorher = None
    for t in toks:
        if t.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            continue
        if t.type == tokenize.NAME and t.string == "deleteLater" and vorher is not None \
                and vorher.type == tokenize.OP and vorher.string == ".":
            funde.append(t.start[0])
        elif t.type == tokenize.STRING and t.string.strip("rbuRBU").strip("'\"") == "deleteLater":
            funde.append(t.start[0])
        elif t.type == tokenize.NAME and t.string == "WA_DeleteOnClose":
            funde.append(t.start[0])
        vorher = t
    return funde


def test_kein_deletelater_an_entsorgen_vorbei():
    """Jedes Loeschen in statik3d geht ueber entsorgen() - die eine Stelle."""
    wurzel = os.path.join(HIER, "statik3d")
    funde = []
    for ordner, _dirs, dateien in os.walk(wurzel):
        for name in sorted(dateien):
            pfad = os.path.join(ordner, name)
            if not name.endswith(".py") or os.path.normpath(pfad) == os.path.normpath(
                    os.path.join(wurzel, "gui", "entsorgen.py")):
                continue
            funde += [f"{os.path.relpath(pfad, HIER)}:{nr}" for nr in _loeschstellen(pfad)]
    check("kein deleteLater in statik3d an entsorgen() vorbei", not funde, ", ".join(funde))
    # der Waechter selbst: er findet alle Schreibweisen, und Kommentare und Texte nicht
    probe = os.path.join(tempfile.mkdtemp(prefix="statik3d_waechter_"), "probe.py")
    with open(probe, "w", encoding="utf-8") as f:
        f.write('a.deleteLater()\n'
                'b . deleteLater ()\n'
                'QtCore.QTimer.singleShot(0, c.deleteLater)\n'
                'getattr(d, "deleteLater")()\n'
                'e.setAttribute(QtCore.Qt.WA_DeleteOnClose)\n'
                'x = "# kein Kommentar"; f.deleteLater()\n'
                '# g.deleteLater() im Kommentar\n'
                's = "h.deleteLater() im Text"\n')
    gefunden = _loeschstellen(probe)
    check("… der Wächter findet jede Schreibweise, Kommentare und Texte nicht",
          gefunden == [1, 2, 3, 4, 5, 6], str(gefunden))


def main():
    if "--kind" in sys.argv:
        ende = sys.argv[sys.argv.index("--kind") + 1] if len(sys.argv) > sys.argv.index("--kind") + 1 else "os"
        _kind(ende)
        return 0
    for t in (test_beenden_nach_masken_ohne_absturz, test_kein_deletelater_an_entsorgen_vorbei):
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
