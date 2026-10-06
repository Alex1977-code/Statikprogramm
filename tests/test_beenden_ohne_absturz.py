"""
Beenden ohne Absturz (Plan-Teilpaket C15, 03.10.2026).

Befund aus der Gegenpruefung von 8b: Pruefungen endeten sporadisch nach dem
Ergebnis mit einer Zugriffsverletzung beim Beenden (Exit -1073741819), oft auch
mit Exitcode 0 - zu sehen nur mit ``-X faulthandler`` als „Windows fatal
exception: access violation“. Ursache: Ein ``deleteLater``, das bei ``os._exit``
noch vorgemerkt ist, an einem Widget mit einem Lambda am Signal (PySide haengt
dafuer eine eigene Verbindung an ``destroyed``) oder an einem Fenster, das schon
zu sehen war. In einer Pruefung bleibt jedes ``deleteLater`` vorgemerkt, denn
``processEvents`` ausserhalb von ``exec`` loescht nichts. Seit C15 fuehrt
``os._exit`` in den Pruefungen (tests/__init__.py) vorher alle vorgemerkten
Loeschungen aus; das Programm selbst bleibt dabei unveraendert. Danach meldet
es die Python-Huellen bei shiboken6 ab: sonst las der statische
``~BindingManager`` beim Entladen von shiboken6 selten einen Nullzeiger
(test_stab_nachweis offscreen 17 von 222 Laeufen, mit Abmelden 0 von 222).

Die erste Fassung von C15 trennte stattdessen im Programm vor dem Loeschen alle
Signale und gab Fenster mit ``destroy()`` frei. Das liess die Rauchpruefung auf
dem Desktop beim normalen Ende (sys.exit) abstuerzen, schnitt Empfaenger ab,
die nach dem Schliessen noch an der Reihe waren, und liess Qts
Stilblatt-Zwischenspeicher wachsen. Diese Pruefung verlangt darum auch, dass
beim Schliessen nichts getrennt und kein Fenster nativ zerstoert wird.

Ablauf:

* Ein kleines Programm-Skript (``--kind``) laeuft in eigenen Prozessen,
  sechsmal mit ``os._exit(0)`` am Ende (wie die anderen Pruefungen) und dreimal
  mit ``w.close()`` und ``sys.exit(0)`` (wie die Rauchpruefung). Es oeffnet und
  schliesst eine Stab-Maske, eine Maske ueber ✕ und eine ueber „Abbrechen“
  (F44), eine Uebersicht aus dem Baum, eine Maske mit der
  Leiste „Übernehmen | Verwerfen“ (13m), das Kontextregister, die
  Ergebnissteuerung nach einer Rechnung mit Masken darunter, das
  Rechtsklickmenue, die Kuerzelliste, den Werkzeug-Dialog (Qt ersetzt dessen
  Knoepfe), ein Beulfeld mit geloeschter Zeile (Qt loescht das Zell-Widget) und
  die Maske „Darstellung“; es loescht in einer inneren Schleife und mitten in
  einer Signalausgabe. Verlangt wird in jedem Lauf Exitcode 0 und keine Zeile
  „Windows fatal exception“ oder „Fatal Python error“ von faulthandler.
* Der Ersatz von ``os._exit`` in tests/__init__.py allein, in reinem PySide6
  (``--ersatz``): ohne Vorgemerktes, mit Lambdas am Sender, mit einem gezeigten
  Dialog, aus einem anderen Faden und ohne QApplication, dazu ob die
  Python-Huellen vor dem echten ``os._exit`` abgemeldet sind; zur Gegenprobe
  dieselben Faelle mit dem echten ``os._exit``, die abstuerzen muessen.

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

    # das Kind laeuft als tests.test_beenden_ohne_absturz: das Paket tests ist
    # geladen, und os._exit holt die vorgemerkten Loeschungen nach
    _melden("ende_holt_loeschungen_nach", os._exit.__name__ == "_os_exit_nach_loeschen",
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

    # B. Loeschen in einer kurzen inneren Schleife: danach bleibt es bis zum
    #    Ende vorgemerkt. Danach laeuft keine Schleife mehr - alles, was ab
    #    hier geschlossen wird, wartet bis zum Ende auf sein deleteLater.
    innen = QtWidgets.QWidget(w)
    innen.show()
    knopf_innen = QtWidgets.QPushButton("x", innen)
    knopf_innen.clicked.connect(lambda *_a: None)
    merken("in_innerer_schleife", innen)
    schleife = QtCore.QEventLoop()

    def _in_der_schleife():
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

    # 1b. Eine Maske ueber ihr ✕ und eine Neu-Maske ueber „Abbrechen“ (F44,
    #     06.10.2026): sie gehen weg wie eine ersetzte, ihr deleteLater wartet
    #     wie dort bis zum Ende
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = _maske(w)
    _melden("knotenmaske_kreuz_offen", mk is not None, getattr(mk, "titel", ""))
    if mk is not None:
        merken("knotenmaske_kreuz", mk)
        mk.btn_zu.click()
        _ruhe(app)
        _melden("knotenmaske_kreuz_heraus", w.maskenrand.maske is None and w.maskenplatz.indexOf(mk) < 0)
    w._baum_neu("lastfaelle")
    _ruhe(app)
    mk = _maske(w)
    weg = False
    if mk is not None and getattr(mk, "btn_abbrechen", None) is not None:
        merken("neumaske_abbrechen", mk)
        mk.btn_abbrechen.click()
        _ruhe(app)
        weg = w.maskenrand.maske is None and w.maskenplatz.indexOf(mk) < 0
    _melden("neumaske_abbrechen_heraus", weg, getattr(mk, "titel", "") if mk is not None else "keine Maske")

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

    # 10. Loeschen mitten in einer Signalausgabe: wer danach an der Reihe ist,
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
    m_.angewendet.connect(lambda _x: (f_.log.append("zweiter loescht"), m_.deleteLater()))
    m_.angewendet.connect(f_.dritter)
    m_.angewendet.emit({})
    _melden("spaetere_empfaenger_bekommen_das_signal", f_.log == ["erster", "zweiter loescht", "dritter"],
            str(f_.log))
    merken("maske_mitten_im_signal", m_)

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
            if absturz:
                # zur Diagnose: was faulthandler im Kind meldete
                zeilen = text.splitlines()
                k = next(j for j, z in enumerate(zeilen) if "fatal" in z.lower())
                for z in zeilen[k:k + 14]:
                    print("     | " + z)
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


def _ersatz_kind(fall: str) -> None:
    """Reines PySide6, ohne Statik3D: der Ersatz von os._exit allein.

    leer        QApplication und ein Fenster, nichts vorgemerkt
    lambda      drei Widgets mit Lambda am Knopf, deleteLater vorgemerkt
    dialog      ein gezeigter, geschlossener QDialog, deleteLater vorgemerkt
    faden       wie lambda ohne Vorgemerktes, os._exit(7) aus einem anderen Faden
    ohne_app    keine QApplication, os._exit(5)
    huellen     wie lambda; meldet vor dem echten os._exit, wie viele Python-Huellen
                shiboken6 noch kennt (der Ersatz meldet sie ab)
    *_echt      lambda und dialog mit dem echten os._exit (Gegenprobe)
    """
    import faulthandler
    import threading
    import tests
    faulthandler.enable()
    print(f"ERSATZ {os._exit.__name__}", flush=True)
    if fall == "ohne_app":
        os._exit(5)
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    haupt = QtWidgets.QWidget()
    haupt.show()
    app.processEvents()
    if fall.startswith("lambda") or fall == "huellen":
        for _ in range(3):
            halter = QtWidgets.QWidget(haupt)
            knopf = QtWidgets.QPushButton("x", halter)
            knopf.clicked.connect(lambda *_a: haupt.update())
            halter.show()
            app.processEvents()
            halter.hide()
            halter.deleteLater()
            app.processEvents()
    elif fall.startswith("dialog"):
        d = QtWidgets.QDialog(haupt)
        d.show()
        app.processEvents()
        d.close()
        d.deleteLater()
        app.processEvents()
    elif fall == "faden":
        knopf = QtWidgets.QPushButton("x", haupt)
        knopf.clicked.connect(lambda *_a: haupt.update())
        print("fertig", flush=True)
        threading.Thread(target=lambda: os._exit(7)).start()
        threading.Event().wait(30)
    print("fertig", flush=True)
    sys.stdout.flush()
    if fall.endswith("_echt"):
        tests._os_exit_echt(0)
    if fall == "huellen":
        import shiboken6
        echt = tests._os_exit_echt
        print(f"HUELLEN_VORHER {len(shiboken6.getAllValidWrappers())}", flush=True)

        def _melden_und_beenden(code=0):
            print(f"HUELLEN_NACHHER {len(shiboken6.getAllValidWrappers())}", flush=True)
            echt(code)
        tests._os_exit_echt = _melden_und_beenden
    os._exit(0)


def _ersatz_lauf(fall: str) -> tuple:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONUTF8"] = "1"
    r = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "tests.test_beenden_ohne_absturz",
                        "--ersatz", fall], cwd=HIER, env=env, capture_output=True, timeout=300)
    text = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    absturz = ("Windows fatal exception" in text) or ("Fatal Python error" in text)
    return r.returncode, absturz, text


def test_ersatz_von_os_exit():
    """Der Ersatz in tests/__init__.py holt vorgemerkte Loeschungen nach - mit
    und ohne Vorgemerktes, mit Lambda am Sender und mit einem gezeigten Dialog;
    aus einem anderen Faden und ohne QApplication ruft er das echte os._exit."""
    import tests
    check("tests/__init__.py ersetzt os._exit", os._exit.__name__ == "_os_exit_nach_loeschen"
          and tests._os_exit_echt is not os._exit, os._exit.__name__)
    for fall, laeufe in (("leer", 2), ("lambda", 3), ("dialog", 3)):
        ergebnisse = [_ersatz_lauf(fall) for _ in range(laeufe)]
        ok = all(rc == 0 and not ab and "ERSATZ _os_exit_nach_loeschen" in t and "fertig" in t
                 for rc, ab, t in ergebnisse)
        check(f"Ersatz, {fall}: Exitcode 0, kein Absturz, in {laeufe} Läufen", ok,
              str([(rc, ab) for rc, ab, _t in ergebnisse]))
    rc, ab, t = _ersatz_lauf("faden")
    check("Ersatz, Aufruf aus einem anderen Faden: das echte os._exit mit seinem Code",
          rc == 7 and not ab and "fertig" in t, f"Exitcode {rc}, Absturz {ab}")
    rc, ab, t = _ersatz_lauf("huellen")
    vorher = re.search(r"HUELLEN_VORHER (\d+)", t)
    nachher = re.search(r"HUELLEN_NACHHER (\d+)", t)
    check("Ersatz meldet vor dem echten os._exit die Python-Hüllen bei shiboken6 ab",
          rc == 0 and not ab and vorher and nachher and int(vorher.group(1)) >= 20
          and int(nachher.group(1)) <= 5,
          f"{vorher.group(1) if vorher else '?'} -> {nachher.group(1) if nachher else '?'} Hüllen")
    rc, ab, t = _ersatz_lauf("ohne_app")
    check("Ersatz ohne QApplication: das echte os._exit mit seinem Code", rc == 5 and not ab,
          f"Exitcode {rc}, Absturz {ab}")
    # Gegenprobe: dieselben Faelle mit dem echten os._exit stuerzen ab (gemessen
    # 6 von 6); einer von zwei Laeufen genuegt als Nachweis
    for fall in ("lambda_echt", "dialog_echt"):
        ergebnisse = [_ersatz_lauf(fall) for _ in range(2)]
        check(f"Gegenprobe {fall}: mit dem echten os._exit stürzt es ab",
              any(ab for _rc, ab, _t in ergebnisse), str([(rc, ab) for rc, ab, _t in ergebnisse]))


def main():
    if "--ersatz" in sys.argv:
        _ersatz_kind(sys.argv[sys.argv.index("--ersatz") + 1])
        return 0
    if "--kind" in sys.argv:
        ende = sys.argv[sys.argv.index("--kind") + 1] if len(sys.argv) > sys.argv.index("--kind") + 1 else "os"
        _kind(ende)
        return 0
    for t in (test_ersatz_von_os_exit, test_beenden_nach_masken_ohne_absturz):
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
