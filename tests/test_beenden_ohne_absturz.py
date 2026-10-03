"""
Beenden ohne Absturz (Plan-Teilpaket C15, 03.10.2026).

Befund aus der Gegenpruefung von 8b: Pruefungen endeten auf dem Desktop
sporadisch nach dem Ergebnis mit einer Zugriffsverletzung beim Beenden (Exit
-1073741819), oft auch mit Exitcode 0 - zu sehen nur mit ``-X faulthandler``
als „Windows fatal exception: access violation“. Ursache: PySide6 6.11 haengt
an jeden Sender, an dessen Signal ein Lambda, ein functools.partial oder das
emit eines anderen Signals haengt, eine eigene Verbindung an ``destroyed``
(eine gebundene Methode bekommt keine). Wartet ein solcher Sender bei
``os._exit`` noch auf sein deleteLater - und das tut jede geschlossene Maske
in einer Pruefung, denn processEvents ausserhalb einer Ereignisschleife
loescht nichts -, greift PySide beim Beenden ins Leere. Ein Fenster, das
schon zu sehen war, stuerzt so auch ohne jede Verbindung ab. Seit C15 trennt
``statik3d.gui.entsorgen`` vor dem Loeschen alle Verbindungen des Widgets und
seiner Kinder und gibt die Fensterressourcen eines Fensters frei - aber nur,
solange keine Ereignisschleife laeuft. Im laufenden Programm loescht die
Schleife gleich, und Qts eigenes Aufraeumen an ``destroyed`` (Stilblatt)
bleibt; das prueft der erste Schritt des Kindes.

Die Pruefung startet ein kleines Programm-Skript sechsmal in einem eigenen
Prozess (``--kind``). Es oeffnet und schliesst eine Stab-Maske, eine Uebersicht
aus dem Baum, eine Maske mit der Leiste „Übernehmen | Verwerfen“ (13m), das
Kontextregister, die Ergebnissteuerung nach einer Rechnung mit Masken
darunter, das Rechtsklickmenue, die Kuerzelliste, den Werkzeug-Dialog und die
Maske „Darstellung“, und endet mit ``os._exit(0)`` wie die anderen
Pruefungen. Verlangt wird in jedem Lauf Exitcode 0 und keine Zeile „Windows
fatal exception“ (oder „Fatal Python error“) in der Ausgabe von faulthandler.
Dazu meldet das Kind fuer jedes geschlossene Objekt, ob seine Verbindungen
getrennt sind.

Aufruf:  python -m tests.test_beenden_ohne_absturz
"""
import os
import re
import subprocess
import sys
import tempfile
import time

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HIER)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

RESULTS = []
#: so oft laeuft das Kind; der Absturz kam im Programm 4 von 4 und 8 von 8 Mal
LAEUFE = 6


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


def _verfolgt(wurzel) -> int:
    """Wie viele Objekte im Baum unter ``wurzel`` haben Empfaenger an
    ``destroyed`` - darunter die Buchfuehrung von PySide fuer Lambdas, die den
    Absturz beim Beenden macht. Nach dem Trennen: 0."""
    from PySide6 import QtCore
    sig = QtCore.SIGNAL("destroyed()")
    return sum(1 for o in [wurzel] + wurzel.findChildren(QtCore.QObject) if o.receivers(sig) > 0)


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
    # Er lebt bis os._exit und wird nie geloescht.

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


def _kind() -> None:
    import faulthandler
    faulthandler.enable()
    import shiboken6
    from PySide6 import QtCore, QtWidgets
    w, app = _kind_fenster()
    #: Name -> (Objekt, Zahl der verfolgten Objekte, solange es offen war)
    zu = {}

    def merken(name, obj):
        if obj is not None and name not in zu:
            zu[name] = (obj, _verfolgt(obj))

    # Zuerst die beiden Schritte mit einer Ereignisschleife: jede Schleife
    # loescht, was bis dahin vorgemerkt war - danach bleibt alles Geschlossene
    # bis zum Ende vorgemerkt, wie in jeder Pruefung.

    # A. Im laufenden Programm (Ereignisschleife) trennt entsorgen nichts:
    #    Qts eigenes Aufraeumen an destroyed bleibt (Stilblatt des Fensters)
    try:
        from statik3d.gui.entsorgen import entsorgen
    except ImportError:
        entsorgen = None
    sig_d = QtCore.SIGNAL("destroyed()")
    probe = QtWidgets.QLabel("Probe", w.centralWidget())
    probe.show()
    _ruhe(app)
    vorher = probe.receivers(sig_d)
    im_lauf = []
    schleife = QtCore.QEventLoop()

    def entsorgen_im_lauf():
        if entsorgen is not None:
            entsorgen(probe)
            im_lauf.append(probe.receivers(sig_d))
        schleife.quit()
    QtCore.QTimer.singleShot(0, entsorgen_im_lauf)
    schleife.exec()
    app.sendPostedEvents(probe, QtCore.QEvent.DeferredDelete)
    _melden("im_programm_nicht_getrennt", vorher > 0 and im_lauf == [vorher] and not shiboken6.isValid(probe),
            f"Empfaenger an destroyed {vorher} -> {im_lauf}, geloescht {not shiboken6.isValid(probe)}")

    w.load_example("hall")
    _ruhe(app)

    # B. Rechtsklick in der Ansicht: das Menue des vorigen geht (sein exec ist
    #    eine Ereignisschleife)
    pos = QtCore.QPoint(20, 20)
    w._viewport_menu(pos)
    merken("rechtsklickmenue", getattr(w, "_kontextmenue_zuletzt", None))
    w._viewport_menu(pos)
    _ruhe(app)

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

    # 6. Kuerzelliste zweimal: die erste geht
    merken("kuerzelliste", w.kuerzel_zeigen())
    w.kuerzel_zeigen()
    _ruhe(app)

    # 7. Werkzeug-Dialog neu gefuellt: Qt loescht die alten Knoepfe der Tabelle
    from statik3d.gui.werkzeuge_dialog import WerkzeugeDialog
    dlg = WerkzeugeDialog(w)
    _BEHALTEN.append(dlg)
    alte = list(dlg.knoepfe.values())
    _melden("werkzeugknoepfe_da", bool(alte), str(len(alte)))
    for i, b in enumerate(alte):
        merken(f"werkzeugknopf_{i}", b)
    dlg._fuellen()
    _ruhe(app)

    # 8. Maske „Darstellung“: ihre Schieber haengen am Schieber des Fensters
    #    und werden beim Schliessen abgehaengt. Hier wird sie wirklich
    #    geloescht wie im Programm (dort laeuft die Ereignisschleife)
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

    # zuletzt: jedes geschlossene Objekt ist getrennt (oder schon geloescht)
    w.maskenrand.schliessen()
    _ruhe(app)
    summe = 0
    for name, (obj, vorher) in zu.items():
        summe += vorher
        nachher = _verfolgt(obj) if shiboken6.isValid(obj) else 0
        _melden(f"getrennt_{name}", nachher == 0,
                f"{vorher} -> {nachher if shiboken6.isValid(obj) else 'geloescht'}")
    _melden("lambdas_im_ablauf", summe > 0, f"{summe} Objekte mit Empfaengern an destroyed, solange offen")
    print(f"fertig {len(zu)} geschlossene Objekte, Meldungen {len(w.fehler)}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


# ---------------------------------------------------------------------------
# Die Pruefung
# ---------------------------------------------------------------------------
def _lauf() -> tuple:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONUTF8"] = "1"
    env["STATIK3D_NO_UPDATE_CHECK"] = "1"
    env["STATIK3D_KEIN_BROWSER"] = "1"
    env["STATIK3D_UNGESPEICHERT"] = "verwerfen"
    env["STATIK3D_EINSTELLUNGEN"] = os.path.join(tempfile.mkdtemp(prefix="statik3d_beenden_"),
                                                 "einstellungen.json")
    t0 = time.time()
    r = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "tests.test_beenden_ohne_absturz", "--kind"],
                       cwd=HIER, env=env, capture_output=True, timeout=900)
    text = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, text, time.time() - t0


def test_beenden_nach_masken_ohne_absturz():
    abstuerze = 0
    abweichend = set()
    for i in range(1, LAEUFE + 1):
        rc, text, dauer = _lauf()
        absturz = ("Windows fatal exception" in text) or ("Fatal Python error" in text)
        abstuerze += bool(absturz or rc != 0)
        schritte = re.findall(r"^SCHRITT (\S+) (ja|nein)(.*)$", text, re.M)
        fertig = re.search(r"^fertig .*$", text, re.M)
        zeile = next((z.strip() for z in text.splitlines() if "fatal" in z.lower()), "")
        check(f"Lauf {i}: Exitcode 0 und kein Absturz beim Beenden (faulthandler)",
              rc == 0 and not absturz, f"Exitcode {rc}, {dauer:.0f} s {zeile}")
        check(f"Lauf {i}: das Kind lief bis zum Ende", fertig is not None,
              fertig.group(0) if fertig else text[-400:].replace("\n", " | "))
        if i == 1:
            check("das Kind hat alle Schritte gemeldet", len(schritte) >= 25, f"{len(schritte)} Schritte")
            for n, ok, d in schritte:
                check(f"… {n}", ok == "ja", d.strip())
        else:
            abweichend.update(n for n, ok, _d in schritte if ok != "ja")
    check(f"{LAEUFE} Läufe ohne Absturz beim Beenden", abstuerze == 0, f"{abstuerze} von {LAEUFE} mit Absturz")
    check("die weiteren Läufe melden dieselben Schritte als erledigt", not abweichend,
          ", ".join(sorted(abweichend))[:200])


def test_kein_deletelater_an_entsorgen_vorbei():
    """Jedes Loeschen in statik3d/gui geht ueber entsorgen(): ein neues
    ``x.deleteLater()`` an einem Widget mit Lambdas braechte den Absturz zurueck."""
    gui = os.path.join(HIER, "statik3d", "gui")
    funde = []
    for name in sorted(os.listdir(gui)):
        if not name.endswith(".py") or name == "entsorgen.py":
            continue
        with open(os.path.join(gui, name), encoding="utf-8") as f:
            for nr, zeile in enumerate(f, 1):
                code = zeile.split("#", 1)[0]
                if re.search(r"\.deleteLater\(", code):
                    funde.append(f"{name}:{nr}")
    check("kein deleteLater in statik3d/gui an entsorgen() vorbei", not funde, ", ".join(funde))


def main():
    if "--kind" in sys.argv:
        _kind()
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
