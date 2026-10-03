"""
Register Berechnung: Rechnen oben, Loeser, Threads und Rechnerfarm eingeklappt
unter „Experten“ (Teilpaket 13r des Oberflaechenplans, 03.10.2026).

Bis zum 02.10.2026 stand „BERECHNEN (F5)“ ganz unten, hinter dem Abschnitt
„Parallelisierung“ mit zehn Zeilen Loeser-, Thread- und Farmeinstellungen und
hinter der Plastizitaet; die Zusammenfassung stand darunter. Der Bereich war
873 px breit (gemessen), im rechten Bereich von 460 px rollte er waagerecht.

* oben steht, was gerechnet wird: Analyse, Nachweise, „Modell pruefen“,
  „BERECHNEN“, darunter die Zusammenfassung; danach die Plastizitaet;
* Loeser, Threads, Prozesse, Genauigkeit, Ketten und Rechnerfarm stehen in
  einem Abschnitt „Experten“, der zu ist, bis man ihn aufklappt - per Klick,
  Leertaste oder auf die graue Zeile daneben;
* die Widgets darin gibt es weiter, auch zugeklappt: Werte lesen und setzen,
  Rechnung und Speichern greifen auf sie zu wie vorher;
* der Zustand auf/zu steht in einstellungen.json (Schluessel „abschnitte“),
  Vorgabe zu, und ueberlebt den Neustart;
* im Register steht nichts zur Elementwahl (die steht in den
  Netzeinstellungen) und nichts haengt von ihr ab;
* der Bereich ist einspaltig und hoechstens etwa 460 px breit (mit echten
  Schriften geprueft; ohne Schrift im Offscreen-Lauf entfaellt diese Pruefung).

Nachzug nach der Gegenpruefung vom 03.10.2026:

* jeder Weg „Berechnung → Einstellungen → …“ zu Loeser, Threads, Prozessen und
  Farm nennt in Texten, Docstrings und Kommentaren von statik3d/ und in den
  Handbuechern auch „Experten“ (die Pruefung liest den Quelltext mit ast und
  tokenize und erkennt die Schreibweisen „→“, „->“ und „\\u2192“);
* die vier langen Auswahllisten (Loeser, Threads, Ketten, Arbeitsprozesse je
  Kette) nehmen die ganze Zeile und tragen den vollen aktuellen Text im Tooltip;
* die graue Zeile am Kopf „Experten“ nennt zugeklappt, was von der Vorgabe
  abweicht, und folgt jeder Aenderung;
* ein Lesefehler an einstellungen.json (nicht „fehlt“, nicht „kaputt“) laesst die
  Datei unberuehrt, und geschrieben wird atomar.

Aufruf:  python -m tests.test_register_berechnung
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ.pop("STATIK3D_FENSTER", None)      # „fest“ merkt nichts - hier wird gemerkt
EINSTELLUNGEN = os.path.join(tempfile.mkdtemp(prefix="statik3d_berechnung_"), "einstellungen.json")
os.environ["STATIK3D_EINSTELLUNGEN"] = EINSTELLUNGEN

RESULTS = []
_FENSTER = {}

#: Widgets, die in den Experten gehoeren (Loeser, Threads, Prozesse, Genauigkeit,
#: Ketten, Rechnerfarm)
EXPERTEN_WIDGETS = ("sp_workers", "cb_loeser", "cb_threads", "cb_genau", "cb_nachit", "cb_ketten",
                    "cb_kettenarb", "cb_backend", "w_farm", "ed_farm_host", "ed_farm_port",
                    "ed_farm_key", "btn_farm_start", "lbl_farm_hilfe")
#: Widgets, die oben bleiben (Rechnen) bzw. darunter (Plastizitaet)
RECHNEN_WIDGETS = ("cb_analysis", "sp_modes", "cb_do_design", "cb_do_fat", "btn_solve", "txt_summary")
PLASTIZITAET_WIDGETS = ("cb_dilat", "cb_plast", "cb_plast_weg", "cb_plast_kontakt", "sp_plast_verf",
                        "sp_plast_stufen", "sp_plast_it", "cb_plast_tol")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _schriften_laden() -> bool:
    """Eine echte Schrift laden, falls das System eine hat - der Offscreen-Lauf
    kennt sonst keine und zeichnet Kaestchen, deren Breite nichts aussagt."""
    from PySide6 import QtGui
    if QtGui.QFontDatabase.families():
        return True
    kandidaten = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/dejavu/DejaVuSans.ttf"]
    for pfad in kandidaten:
        if os.path.exists(pfad) and QtGui.QFontDatabase.addApplicationFont(pfad) >= 0:
            fam = QtGui.QFontDatabase.applicationFontFamilies(0)
            if fam:
                QtGui.QGuiApplication.setFont(QtGui.QFont(fam[0], 9))
            return True
    return False


def _fenster(neu=False):
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if "echte_schrift" not in _FENSTER:
        _FENSTER["echte_schrift"] = _schriften_laden()
    if "w" in _FENSTER and not neu:
        return _FENSTER["w"], app
    w = MainWindow()
    w.resize(1600, 980)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    w.error = lambda msg, *a, **k: (w.fehler_liste.append(str(msg)), w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _register(w, app):
    """Das Register Berechnung rechts zeigen; Rueckgabe (Rollflaeche, Inhalt)."""
    w.maske_zeigen("Berechnung")
    for _ in range(6):
        app.processEvents()
    sa = w.tabs.currentWidget()
    return sa, sa.widget()


def _y(w, wid, inhalt):
    from PySide6 import QtCore
    return wid.mapTo(inhalt, QtCore.QPoint(0, 0)).y()


def _gespeichert() -> dict:
    try:
        with open(EINSTELLUNGEN, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def test_reihenfolge():
    """Rechnen steht oben: Analyse, Knopf, Zusammenfassung, dann Plastizitaet,
    dann die Experten."""
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    check("Abschnitt „Experten“ im Register Berechnung vorhanden", ex is not None,
          type(ex).__name__)
    y_ana = _y(w, w.cb_analysis, inh)
    y_knopf = _y(w, w.btn_solve, inh)
    y_zus = _y(w, w.txt_summary, inh)
    y_plast = _y(w, w.cb_plast, inh)
    check("„BERECHNEN (F5)“ steht über der Plastizität (vorher ganz unten)", y_knopf < y_plast,
          f"Knopf y={y_knopf}, Plastizität y={y_plast}")
    check("Reihenfolge Analyse → BERECHNEN → Zusammenfassung", y_ana < y_knopf < y_zus,
          f"{y_ana} < {y_knopf} < {y_zus}")
    if ex is None:
        return
    y_ex = _y(w, ex, inh)
    check("Zusammenfassung und Plastizität stehen über den Experten", y_zus < y_ex and y_plast < y_ex,
          f"Zusammenfassung y={y_zus}, Plastizität y={y_plast}, Experten y={y_ex}")
    check("Der Knopf steht im oberen Drittel des Registers (nicht erst nach dem Rollen)",
          y_knopf < inh.height() / 3, f"y={y_knopf} von {inh.height()}")


def test_inhalt_der_experten():
    w, app = _fenster()
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Inhalt)", False)
        return
    fehlt = [n for n in EXPERTEN_WIDGETS if not hasattr(w, n)]
    check("Alle Widgets für Löser, Threads, Prozesse, Genauigkeit, Ketten und Farm gibt es weiter",
          not fehlt, str(fehlt))
    ausserhalb = [n for n in EXPERTEN_WIDGETS if hasattr(w, n) and not ex.inhalt.isAncestorOf(getattr(w, n))]
    check("… und sie stehen im Inhalt der Experten", not ausserhalb, str(ausserhalb))
    drin = [n for n in RECHNEN_WIDGETS + PLASTIZITAET_WIDGETS
            if hasattr(w, n) and ex.inhalt.isAncestorOf(getattr(w, n))]
    check("Analyse, Haken, Knopf, Zusammenfassung und Plastizität stehen nicht in den Experten",
          not drin, str(drin))


def test_vorgabe_zu():
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Vorgabe)", False)
        return
    check("Die Experten sind zu, solange man sie nicht aufklappt", not ex.ist_offen())
    check("… der Kopf „Experten“ ist zu sehen, der Inhalt nicht",
          ex.knopf.isVisible() and "Experten" in ex.knopf.text() and not ex.inhalt.isVisible(),
          ex.knopf.text())
    check("… Löser, Threads und Rechnerfarm sind nicht sichtbar",
          not any(getattr(w, n).isVisible() for n in ("cb_loeser", "cb_threads", "sp_workers", "cb_backend",
                                                      "ed_farm_host", "btn_farm_start")))
    check("… die übrigen Felder (Analyse, BERECHNEN, Plastizität) sind sichtbar",
          all(getattr(w, n).isVisible() for n in ("cb_analysis", "btn_solve", "txt_summary", "cb_plast")))
    check("… der Kopf trägt einen Pfeil nach rechts", ex.knopf.text().lstrip().startswith("▸"), ex.knopf.text())


def test_aufklappen():
    from PySide6 import QtCore, QtTest
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Aufklappen)", False)
        return
    ex.aufklappen(False)
    app.processEvents()
    h_zu = inh.sizeHint().height()
    QtTest.QTest.mouseClick(ex.knopf, QtCore.Qt.LeftButton)
    app.processEvents()
    h_auf = inh.sizeHint().height()
    check("Klick auf den Kopf klappt die Experten auf", ex.ist_offen() and ex.inhalt.isVisible())
    check("… das Register wird dabei höher (die Experten nehmen Platz, zugeklappt keinen)",
          h_auf > h_zu + 100, f"{h_zu} -> {h_auf} px")
    check("… Löser, Threads, Genauigkeit, Ketten und Prozesse sind zu sehen",
          all(getattr(w, n).isVisible() for n in ("cb_loeser", "cb_threads", "cb_genau", "cb_nachit",
                                                  "cb_ketten", "cb_kettenarb", "sp_workers", "cb_backend")))
    check("… der Pfeil zeigt nach unten", ex.knopf.text().lstrip().startswith("▾"), ex.knopf.text())
    # die Farmeinstellungen erscheinen weiter erst mit dem Backend (14.09.2026)
    w.cb_backend.setCurrentIndex(0)
    app.processEvents()
    check("… die Farmeinstellungen bleiben verborgen, solange das Backend „lokal“ ist",
          not w.w_farm.isVisible() and w.w_farm.isHidden())
    w.cb_backend.setCurrentIndex(1)
    app.processEvents()
    check("… und erscheinen mit „lokal und Rechnerfarm“", w.w_farm.isVisible() and w.ed_farm_host.isVisible())
    ex.aufklappen(False)
    app.processEvents()
    check("Zugeklappt sind die Farmeinstellungen weg, obwohl das Backend noch „Farm“ ist",
          not w.w_farm.isVisible() and not w.ed_farm_host.isVisible() and w.cb_backend.currentIndex() == 1)
    w.cb_backend.setCurrentIndex(0)
    # Tastatur: Fokus auf den Kopf, Leertaste
    ex.knopf.setFocus()
    app.processEvents()
    QtTest.QTest.keyClick(ex.knopf, QtCore.Qt.Key_Space)
    app.processEvents()
    check("Leertaste auf dem Kopf klappt auf", ex.ist_offen() and w.cb_loeser.isVisible())
    QtTest.QTest.keyClick(ex.knopf, QtCore.Qt.Key_Space)
    app.processEvents()
    check("… und wieder zu", not ex.ist_offen() and not w.cb_loeser.isVisible())
    # die graue Zeile neben dem Kopf gehört zum Kopf
    QtTest.QTest.mouseClick(ex.hinweis, QtCore.Qt.LeftButton)
    app.processEvents()
    check("Ein Klick auf die graue Zeile neben dem Kopf klappt ebenfalls auf", ex.ist_offen())
    ex.aufklappen(False)
    app.processEvents()
    check("Zugeklappt hat das Register wieder die kleine Höhe", inh.sizeHint().height() == h_zu,
          f"{inh.sizeHint().height()} px, vorher {h_zu} px")


def test_werte_zugeklappt():
    """Zugeklappt lassen sich die Werte lesen und setzen; die Rechnung nimmt sie."""
    from statik3d import parallel
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Werte)", False)
        return
    ex.aufklappen(False)
    app.processEvents()
    st = parallel.settings()
    alt = (st.workers, st.solver_threads, st.solver_residuum, st.solver_nachiterationen, st.ketten,
           st.ketten_arbeiter, st.solver_backend, st.backend, st.farm_key)
    try:
        i_t = w.cb_threads.findData(1)
        i_g = w.cb_genau.findData(1e-4)
        i_n = w.cb_nachit.findData(5)
        i_k = w.cb_ketten.findData(2)
        check("Werte lassen sich zugeklappt setzen (Threads, Genauigkeit, Nachiterationen, Ketten)",
              min(i_t, i_g, i_n, i_k) >= 0, f"{i_t} {i_g} {i_n} {i_k}")
        w.cb_threads.setCurrentIndex(i_t)
        w.cb_genau.setCurrentIndex(i_g)
        w.cb_nachit.setCurrentIndex(i_n)
        w.cb_ketten.setCurrentIndex(i_k)
        w.sp_workers.setValue(2)
        w.cb_loeser.setCurrentIndex(w.cb_loeser.findData("superlu"))
        w.ed_farm_key.setText("schluessel13r")
        check("… und lesen", w.cb_threads.currentData() == 1 and w.cb_genau.currentData() == 1e-4
              and w.sp_workers.value() == 2 and w.cb_loeser.currentData() == "superlu")
        w._apply_parallel_settings()
        st = parallel.settings()
        check("Die Rechnung übernimmt sie: Prozesse 2, Threads 1, Residuum 1e-4, bis 5 Nachiterationen, 2 Ketten",
              st.workers == 2 and st.solver_threads == 1 and st.solver_residuum == 1e-4
              and st.solver_nachiterationen == 5 and st.ketten == 2 and st.solver_backend == "superlu"
              and st.farm_key == "schluessel13r",
              f"{st.workers} {st.solver_threads} {st.solver_residuum} {st.solver_nachiterationen} {st.ketten}")
        d = _gespeichert()
        check("… und sie stehen in einstellungen.json (Löser, Threads, Genauigkeit, Ketten)",
              d.get("solver_threads") == 1 and d.get("solver_backend") == "superlu"
              and d.get("solver_residuum") == 1e-4 and d.get("ketten") == 2, str({k: d.get(k) for k in
                                                                                  ("solver_threads", "ketten")}))
        check("… die Experten sind dabei zugeblieben", not ex.ist_offen())
    finally:
        parallel.configure(workers=alt[0], solver_threads=alt[1], solver_residuum=alt[2],
                           solver_nachiterationen=alt[3], ketten=alt[4], ketten_arbeiter=alt[5],
                           solver_backend=alt[6], backend=alt[7], farm_key=alt[8])
        w.cb_threads.setCurrentIndex(max(0, w.cb_threads.findData(alt[1])))
        w.cb_genau.setCurrentIndex(max(0, w.cb_genau.findData(1e-6)))
        w.cb_nachit.setCurrentIndex(max(0, w.cb_nachit.findData(3)))
        w.cb_ketten.setCurrentIndex(max(0, w.cb_ketten.findData(1)))
        w.cb_loeser.setCurrentIndex(0)
        w.ed_farm_key.setText("statik3d")


def test_zustand_wird_gemerkt():
    from statik3d.gui import fenster as fen
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Merken)", False)
        return
    try:
        os.remove(EINSTELLUNGEN)
    except OSError:
        pass
    check("Ohne Eintrag in einstellungen.json beginnen die Experten zu", not fen.abschnitt_offen("berechnung_experten"))
    ex.aufklappen(True)
    app.processEvents()
    d = _gespeichert()
    check("Aufklappen schreibt den Zustand in einstellungen.json (Schlüssel „abschnitte“)",
          isinstance(d.get("abschnitte"), dict) and d["abschnitte"].get("berechnung_experten") is True, str(d.get("abschnitte")))
    w._apply_parallel_settings()
    d = _gespeichert()
    check("… das Speichern der Löser-Einstellungen löscht ihn nicht",
          isinstance(d.get("abschnitte"), dict) and d["abschnitte"].get("berechnung_experten") is True
          and "solver_threads" in d)
    w.anordnung.speichern()
    d = _gespeichert()
    check("… das Merken der Fensteraufteilung auch nicht",
          isinstance(d.get("abschnitte"), dict) and d["abschnitte"].get("berechnung_experten") is True
          and "fenster" in d, str(sorted(d)))
    # ein neues Fenster beginnt so, wie es zuletzt stand
    w.close()
    app.processEvents()
    _FENSTER.pop("w", None)
    w2, app = _fenster(neu=True)
    sa2, inh2 = _register(w2, app)
    ex2 = w2.experten
    check("Ein neues Fenster beginnt mit aufgeklappten Experten", ex2.ist_offen() and w2.cb_loeser.isVisible())
    ex2.aufklappen(False)
    app.processEvents()
    d = _gespeichert()
    check("Zuklappen schreibt „zu“", d["abschnitte"].get("berechnung_experten") is False, str(d.get("abschnitte")))
    w2.close()
    app.processEvents()
    _FENSTER.pop("w", None)
    w3, app = _fenster(neu=True)
    _register(w3, app)
    check("… das nächste Fenster beginnt wieder zu", not w3.experten.ist_offen() and not w3.cb_loeser.isVisible())
    # kaputte Einträge werfen nichts und gelten als „zu“
    for kaputt in (5, [1, 2], {"berechnung_experten": "vielleicht"}, None):
        with open(EINSTELLUNGEN, "w", encoding="utf-8") as f:
            json.dump({"abschnitte": kaputt}, f)
        try:
            ok = fen.abschnitt_offen("berechnung_experten") in (False, True)
            wert = fen.abschnitt_offen("berechnung_experten")
        except Exception as ex_:        # noqa: BLE001
            ok, wert = False, repr(ex_)
        check(f"Ein kaputter Eintrag ({kaputt!r}) wirft nichts und gilt als „zu“", ok and wert is False, str(wert))
    with open(EINSTELLUNGEN, "w", encoding="utf-8") as f:
        f.write("{kein json")
    check("Eine unlesbare Datei gilt als „zu“", fen.abschnitt_offen("berechnung_experten") is False)
    fen.abschnitt_merken("berechnung_experten", True)
    check("… und wird beim Merken neu geschrieben", fen.abschnitt_offen("berechnung_experten") is True)
    fen.abschnitt_merken("berechnung_experten", False)


def test_nichts_zur_elementwahl():
    """Die Elementwahl steht in den Netzeinstellungen; im Register Berechnung
    steht nichts dazu und die Rechnung liest sie nicht von dort."""
    from PySide6 import QtWidgets
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is not None:
        ex.aufklappen(True)
        app.processEvents()
    begriffe = ("Elementwahl", "Elementauswahl", "Elementstufe", "Elementordnung",
                "Entwurf", "tet10", "VQ83", "VQ203")
    texte = []
    for x in inh.findChildren(QtWidgets.QWidget):
        for t in (getattr(x, "text", lambda: "")() if not isinstance(x, QtWidgets.QPlainTextEdit) else "",
                  x.toolTip(), x.accessibleName()):
            if isinstance(t, str) and t:
                texte.append(t)
        if isinstance(x, QtWidgets.QComboBox):
            texte.extend(x.itemText(i) for i in range(x.count()))
    gefunden = sorted({b for b in begriffe for t in texte if b in t})
    # die Plastizität spricht vom „Tetraeder (tet4)“ und nennt tet10 als Abhilfe gegen die
    # Schubversteifung - das ist ein Hinweis zum Fließen, keine Wahl
    gefunden = [b for b in gefunden if b not in ("tet10",)]
    check("Im Register Berechnung steht keine Elementwahl (Stufen, Typen, Haken)", not gefunden, str(gefunden))
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske if w.maskenrand.offen() else None
    check("Die Elementwahl steht in den Netzeinstellungen (Feld „Elemente“)",
          mk is not None and "elemente" in mk._felder, str(list(getattr(mk, "_felder", {}))[:6]))
    if mk is not None:
        w.maskenrand.schliessen()
    _register(w, app)
    namen = [n for n in vars(w) if n.startswith(("cb_elem", "cb_stufe", "cb_ordnung", "sp_elem"))
             and w.tabs.currentWidget().widget().isAncestorOf(getattr(w, n))]
    check("… und kein Feld dafür", not namen, str(namen))
    if ex is not None:
        ex.aufklappen(False)
        app.processEvents()


def test_breite():
    """Einspaltig und hoechstens etwa 460 px: der Inhalt braucht zugeklappt
    nicht mehr als den Platz neben dem Rollbalken (Gegenprobe vor 13r: 873 px)."""
    w, app = _fenster()
    if not _FENSTER.get("echte_schrift"):
        print("--   Breitenprüfung entfällt: keine Schrift im System (Offscreen ohne Schriften zeichnet Kästchen)")
        return
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is not None:
        ex.aufklappen(False)
        app.processEvents()
    breit = inh.minimumSizeHint().width()
    check("Zugeklappt braucht das Register höchstens 450 px (460 px rechts, abzüglich Rollbalken)",
          breit <= 450, f"{breit} px")
    if ex is not None:
        ex.aufklappen(True)
        app.processEvents()
        breit = inh.minimumSizeHint().width()
        check("Aufgeklappt auch (Experten ohne Zeile über 450 px)", breit <= 450, f"{breit} px")
        ex.aufklappen(False)
        app.processEvents()
    app.processEvents()
    check("Kein waagerechter Rollbalken bei 460 px Breite des rechten Bereichs (zugeklappt)",
          w.eingaben_dock.width() >= 460 and not sa.horizontalScrollBar().isVisible(),
          f"Dock {w.eingaben_dock.width()} px, Balken {sa.horizontalScrollBar().isVisible()}")


# --------------------------------------------------------------------------
# Nachzug 03.10.2026
# --------------------------------------------------------------------------
PFEIL = r"(?:→|->)"
#: Ziele unter „Berechnung → Einstellungen“, die nicht in den Experten liegen
#: (die Plastizitaet steht sichtbar im Register)
AUSSERHALB_EXPERTEN = ("Plastizität", "Fließen", "Dilatation")


def _pfadfehler(text: str, streng: bool = True) -> list:
    """Die Stellen in einem Text, die einen Weg zu den Experten-Feldern ohne „Experten“ nennen.

    ``streng``: auch ein Weg „Berechnung → Einstellungen“ ohne Ziel gilt als Fehler (Quelltext);
    die Handbuecher nennen so auch das Register selbst, etwa fuer die Plastizitaet."""
    import re
    # Markdown-Sternchen und Zeilenumbrueche stoeren den Weg nicht
    text = re.sub(r"\s+", " ", text.replace("*", ""))
    nackt = re.compile(r"Berechnung\s*" + PFEIL + r"\s*Einstellungen(?!\s*" + PFEIL + r"\s*(?:Experten|"
                       + "|".join(AUSSERHALB_EXPERTEN) + "))")
    ziel = re.compile(r"Einstellungen\s*" + PFEIL + r"\s*(?!Experten)(?:Gleichungsl|Löser|Loeser|Threads|"
                      r"Prozesse|Rechnerfarm|Genauigkeit|Ketten|Backend|Nachiteration|Arbeitsprozesse)")
    alt = re.compile(r"Berechnung\s*" + PFEIL + r"\s*(?:Prozesse|Backend|Gleichungsl|Threads|Rechnerfarm)")
    regeln = (nackt, ziel, alt) if streng else (ziel, alt)
    return [text[max(0, m.start() - 25):m.end() + 30] for rx in regeln for m in rx.finditer(text)]


def test_pfade_nennen_experten():
    """Die Wege zu Loeser, Threads, Prozessen und Farm nennen „Experten“."""
    import ast
    import io
    import tokenize
    # die Regel selbst: erkennt sie die alten Schreibweisen, laesst sie die neuen durch?
    schlecht = ["Berechnung \u2192 Einstellungen \u2192 Gleichungslöser.", "Berechnung -> Einstellungen ein",
                "unter Berechnung → Einstellungen)", "GUI → Berechnung → Prozesse",
                "*Berechnung →\n  Einstellungen → Rechnerfarm einschalten*"]
    gut = ["Berechnung \u2192 Einstellungen \u2192 Experten \u2192 Gleichungslöser.",
           "Berechnung -> Einstellungen -> Experten ein", "*Berechnung →\n Einstellungen → Experten → Prozesse*",
           "Berechnung → Einstellungen → Plastizität", "Netzeinstellungen → Vernetzer"]
    check("Die Regel erkennt Wege ohne „Experten“ in jeder Schreibweise",
          all(_pfadfehler(s) for s in schlecht), str([bool(_pfadfehler(s)) for s in schlecht]))
    check("… und lässt Wege mit „Experten“ und zur Plastizität durch",
          not any(_pfadfehler(s) for s in gut) and not _pfadfehler("unter *Berechnung → Einstellungen*, Plastizität", False),
          str([_pfadfehler(s) for s in gut if _pfadfehler(s)]))
    stamm = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statik3d")
    funde, mit_experten, dateien = [], 0, 0
    for dp, dn, fn in os.walk(stamm):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for n in fn:
            if not n.endswith(".py"):
                continue
            dateien += 1
            p = os.path.join(dp, n)
            with io.open(p, encoding="utf-8") as f:
                src = f.read()
            texte = []
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.JoinedStr):
                    texte.append((node.lineno, "".join(v.value if isinstance(v, ast.Constant) else "{}"
                                                       for v in node.values)))
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    texte.append((node.lineno, node.value))
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT:
                    texte.append((tok.start[0], tok.string))
            for ln, text in texte:
                for stelle in _pfadfehler(text):
                    funde.append(f"{os.path.relpath(p, os.path.dirname(stamm))}:{ln} {stelle!r}")
                if "Einstellungen" in text and "Experten" in text:
                    mit_experten += 1
    check("In statik3d/ nennt jeder Weg zu Löser, Threads, Prozessen und Farm „Experten“ "
          "(Texte, Docstrings, Kommentare)", not funde, "; ".join(funde[:3]))
    check("… und die Prüfung hat etwas gelesen (viele Dateien, mehrere Wege mit „Experten“)",
          dateien > 50 and mit_experten >= 8, f"{dateien} Dateien, {mit_experten} Stellen mit Experten")
    # die Handbuecher
    docs = os.path.join(os.path.dirname(stamm), "docs")
    funde = []
    for n in sorted(os.listdir(docs)):
        if n.endswith(".md"):
            with io.open(os.path.join(docs, n), encoding="utf-8") as f:
                for stelle in _pfadfehler(f.read(), streng=False):
                    funde.append(f"{n} {stelle!r}")
    check("In docs/*.md nennt jeder Weg zu Löser, Threads, Prozessen und Farm „Experten“",
          not funde, "; ".join(funde[:3]))
    with io.open(os.path.join(docs, "Rechnerfarm.md"), encoding="utf-8") as f:
        farm = f.read()
    check("Rechnerfarm.md nennt die heutigen Namen: Backend „lokal und Rechnerfarm“, Knopf „Rechnerfarm einschalten“",
          "lokal und Rechnerfarm" in farm and farm.count("Rechnerfarm einschalten") >= 2
          and "Lokalen Server + Worker starten" not in farm)
    for n in ("Benutzerhandbuch.md", "Theoriehandbuch.md"):
        with io.open(os.path.join(docs, n), encoding="utf-8") as f:
            text = f.read()
        check(f"{n}: „Verfahren mit Kontakt“ in eigener Zeile statt „mit Kontakt“ neben dem Verfahren",
              "Verfahren mit Kontakt" in text
              and "*Berechnung → Einstellungen*, „mit Kontakt“" not in text)


def test_listen_breit_mit_tooltip():
    """Die vier langen Listen nehmen die Zeile und nennen ihren vollen Text im Tooltip."""
    from PySide6 import QtCore, QtWidgets
    from statik3d import solver
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Listen)", False)
        return
    ex.aufklappen(True)
    app.processEvents()
    listen = {"cb_loeser": "Gleichungslöser", "cb_threads": "Threads", "cb_ketten": "Ketten",
              "cb_kettenarb": "Arbeitsprozesse"}
    try:
        for name in listen:
            cb = getattr(w, name)
            zeile = cb.parentWidget()
            Exp = QtWidgets.QSizePolicy.Expanding
            check(f"{name}: Größenregel Expanding und Zeile mit Dehnfaktor 1",
                  cb.sizePolicy().horizontalPolicy() == Exp
                  and zeile.layout().stretch(zeile.layout().indexOf(cb)) == 1,
                  f"{cb.sizePolicy().horizontalPolicy()} / {zeile.layout().stretch(zeile.layout().indexOf(cb))}")
            rest = zeile.width() - cb.geometry().right() - 1
            check(f"{name}: die Liste reicht bis ans Ende der Zeile", 0 <= rest <= 6,
                  f"Zeile {zeile.width()} px, Liste bis {cb.geometry().right()}")
            check(f"{name}: der Tooltip nennt den vollen aktuellen Text",
                  cb.currentText() in cb.toolTip(), cb.toolTip()[:60].replace("\n", " "))
            check(f"{name}: … und behält die Erklärung der Liste",
                  len(cb.toolTip()) > len(cb.currentText()) + 40, f"{len(cb.toolTip())} Zeichen")
        # bei Wechsel nachziehen
        for name, ziel in (("cb_loeser", "superlu"), ("cb_ketten", 4), ("cb_kettenarb", 4)):
            cb = getattr(w, name)
            i = cb.findData(ziel)
            if i >= 0:
                cb.setCurrentIndex(i)
                app.processEvents()
                check(f"{name}: beim Wechsel zieht der Tooltip nach", cb.currentText() in cb.toolTip(),
                      cb.toolTip()[:60].replace("\n", " "))
        w.cb_threads.setCurrentIndex(w.cb_threads.count() - 1)
        check("cb_threads: beim Wechsel zieht der Tooltip nach", w.cb_threads.currentText() in w.cb_threads.toolTip(),
              w.cb_threads.toolTip()[:50].replace("\n", " "))
        # die Liste neu fuellen (Nachladen von MUMPS): Tooltip nennt wieder den gewaehlten Eintrag
        w._loeserliste_neu()
        app.processEvents()
        check("cb_loeser: nach dem Neufüllen der Liste stimmt der Tooltip noch",
              w.cb_loeser.currentText() in w.cb_loeser.toolTip() and "automatisch" in w.cb_threads.itemText(0)
              and w.cb_threads.currentText() in w.cb_threads.toolTip())
        i_m = w.cb_loeser.findData("superlu")
        tip = w.cb_loeser.itemData(i_m, QtCore.Qt.ToolTipRole)
        check("… die Lizenz-Tooltips der Einträge bleiben", isinstance(tip, str) and tip.startswith("Lizenz:"), str(tip)[:40])
        check("… und der Löser-Tooltip erklärt weiter die Auswahl (Vorgabe MKL PARDISO)",
              "Vorgabe MKL PARDISO" in w.cb_loeser.toolTip())
        if _FENSTER.get("echte_schrift"):
            app.processEvents()
            check("Aufgeklappt braucht das Register weiter höchstens 450 px",
                  inh.minimumSizeHint().width() <= 450, f"{inh.minimumSizeHint().width()} px")
            check("… und rollt bei 460 px nicht waagerecht", not sa.horizontalScrollBar().isVisible())
    finally:
        w.cb_loeser.setCurrentIndex(0)
        w.cb_threads.setCurrentIndex(0)
        w.cb_ketten.setCurrentIndex(max(0, w.cb_ketten.findData(1)))
        w.cb_kettenarb.setCurrentIndex(0)
        ex.aufklappen(False)
        app.processEvents()


def test_kopfzeile_abweichungen():
    """Zugeklappt nennt die graue Zeile, was von der Vorgabe abweicht."""
    from PySide6 import QtCore, QtTest
    from statik3d import parallel
    w, app = _fenster()
    sa, inh = _register(w, app)
    ex = getattr(w, "experten", None)
    if ex is None:
        check("Experten vorhanden (Kopfzeile)", False)
        return
    ex.aufklappen(False)
    # Vorgaben herstellen
    st0 = parallel.Settings()
    w.sp_workers.setValue(st0.workers)
    w.cb_loeser.setCurrentIndex(0)
    w.cb_threads.setCurrentIndex(0)
    w.cb_genau.setCurrentIndex(w.cb_genau.findData(1e-6))
    w.cb_nachit.setCurrentIndex(w.cb_nachit.findData(3))
    w.cb_ketten.setCurrentIndex(w.cb_ketten.findData(1))
    w.cb_kettenarb.setCurrentIndex(0)
    w.cb_backend.setCurrentIndex(0)
    app.processEvents()
    check("Alles auf Vorgabe: die graue Zeile sagt „Vorgaben“", ex.hinweis_text() == "Vorgaben", ex.hinweis_text())
    w.cb_loeser.setCurrentIndex(w.cb_loeser.findData("superlu"))
    check("Ein anderer Löser steht sofort in der Zeile („Löser: SuperLU“)",
          ex.hinweis_text() == "Löser: SuperLU", ex.hinweis_text())
    i_t = w.cb_threads.findData(1)
    w.cb_threads.setCurrentIndex(i_t)
    w.cb_ketten.setCurrentIndex(w.cb_ketten.findData(2))
    w.cb_backend.setCurrentIndex(1)
    app.processEvents()
    check("… dazu Threads, Ketten und die Rechnerfarm, getrennt durch „ · “",
          ex.hinweis_text() == "Löser: SuperLU · Threads 1 · 2 Ketten · Rechnerfarm", ex.hinweis_text())
    w.cb_genau.setCurrentIndex(w.cb_genau.findData(1e-4))
    w.cb_nachit.setCurrentIndex(w.cb_nachit.findData(5))
    w.cb_kettenarb.setCurrentIndex(w.cb_kettenarb.findData(4))
    w.sp_workers.setValue(2 if st0.workers != 2 else 3)
    app.processEvents()
    text = ex.hinweis_text()
    check("… ebenso Prozesse, Genauigkeit, Nachiterationen und Arbeitsprozesse je Kette",
          all(s in text for s in ("Prozesse ", "Genauigkeit locker (1e-4)", "Nachiterationen bis 5",
                                  "4 Arbeitsprozesse je Kette")), text)
    check("Die Zeile am Kopf trägt den ganzen Text im Tooltip (sie kürzt, statt zu verbreitern)",
          ex.hinweis.toolTip() == text, ex.hinweis.toolTip()[:50])
    check("… und die Mindestbreite des Registers bleibt klein (Zeile mit Ignored)",
          (not _FENSTER.get("echte_schrift")) or inh.minimumSizeHint().width() <= 450,
          f"{inh.minimumSizeHint().width()} px")
    # aufgeklappt steht der feste Text, zugeklappt wieder die Abweichungen
    ex.aufklappen(True)
    app.processEvents()
    check("Aufgeklappt steht der feste Text („Gleichungslöser, Threads, Prozesse, Rechnerfarm“)",
          ex.hinweis_text() == "Gleichungslöser, Threads, Prozesse, Rechnerfarm", ex.hinweis_text())
    ex.aufklappen(False)
    app.processEvents()
    check("Zugeklappt nennt sie wieder die Abweichungen", ex.hinweis_text() == text, ex.hinweis_text())
    QtTest.QTest.mouseClick(ex.hinweis, QtCore.Qt.LeftButton)
    app.processEvents()
    check("Ein Klick auf die graue Zeile klappt weiter auf", ex.ist_offen())
    ex.aufklappen(False)
    # zurueck auf Vorgabe
    w.sp_workers.setValue(st0.workers)
    w.cb_loeser.setCurrentIndex(0)
    w.cb_threads.setCurrentIndex(0)
    w.cb_genau.setCurrentIndex(w.cb_genau.findData(1e-6))
    w.cb_nachit.setCurrentIndex(w.cb_nachit.findData(3))
    w.cb_ketten.setCurrentIndex(w.cb_ketten.findData(1))
    w.cb_kettenarb.setCurrentIndex(0)
    w.cb_backend.setCurrentIndex(0)
    app.processEvents()
    check("Zurück auf die Vorgaben: wieder „Vorgaben“", ex.hinweis_text() == "Vorgaben", ex.hinweis_text())


def test_einstellungsdatei_schutz():
    """abschnitt_merken: Lesefehler lassen die Datei stehen, Schreiben ist atomar."""
    import builtins
    from statik3d.gui import fenster as fen
    pfad = EINSTELLUNGEN
    ordner = os.path.dirname(pfad)
    inhalt = {"solver_threads": 7, "solver_backend": "superlu",
              "fenster": {"fassung": fen.FASSUNG, "geometrie": [1, 2, 3, 4], "maximiert": False}}

    def schreibe(d):
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump(d, f)

    def lies():
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)

    def roh():
        with open(pfad, "rb") as f:
            return f.read()

    schreibe(inhalt)
    r = fen.abschnitt_merken("berechnung_experten", True)
    d = lies()
    check("abschnitt_merken lässt „solver_threads“ und „fenster“ stehen und schreibt „abschnitte“",
          r == pfad and d.get("solver_threads") == 7 and d.get("solver_backend") == "superlu"
          and d.get("fenster") == inhalt["fenster"] and d.get("abschnitte") == {"berechnung_experten": True}, str(sorted(d)))
    fen.abschnitt_merken("anderer", False)
    check("… ein zweiter Abschnitt kommt dazu, der erste bleibt",
          lies().get("abschnitte") == {"berechnung_experten": True, "anderer": False})
    check("… und es bleiben keine Hilfsdateien liegen", os.listdir(ordner) == [os.path.basename(pfad)],
          str(os.listdir(ordner)))
    # Lesefehler (nicht „fehlt“, nicht „kaputt“): nichts schreiben
    schreibe(inhalt)
    vorher = roh()
    echt_open = builtins.open
    zaehler = {"n": 0}

    def sperre(datei, mode="r", *a, **k):
        if str(datei) == pfad and "r" in mode and "b" not in mode:
            zaehler["n"] += 1
            raise PermissionError(13, "Zugriff verweigert", pfad)
        return echt_open(datei, mode, *a, **k)

    builtins.open = sperre
    try:
        r = fen.abschnitt_merken("berechnung_experten", True)
        gemerkt = fen.abschnitt_offen("berechnung_experten")
        ohne_merken = fen.abschnitt_offen("noch_nie_gemerkt")
    finally:
        builtins.open = echt_open
    check("Lesefehler (PermissionError): abschnitt_merken schreibt nichts, die Datei bleibt byteweise gleich",
          r is None and roh() == vorher and zaehler["n"] >= 1, f"Rückgabe {r}, gelesen {zaehler['n']}x")
    check("… der Zustand bleibt im Speicher: abschnitt_offen kennt ihn, ein unbekannter gilt als Vorgabe",
          gemerkt is True and ohne_merken is False, f"{gemerkt} / {ohne_merken}")
    check("… und nach dem Fehler schreibt der nächste Aufruf wieder, mit allen Schlüsseln",
          fen.abschnitt_merken("berechnung_experten", False) == pfad and lies().get("solver_threads") == 7
          and lies()["abschnitte"] == {"berechnung_experten": False} and lies().get("fenster") == inhalt["fenster"])
    # fenster.schreiben: derselbe Schutz
    schreibe(inhalt)
    vorher = roh()
    builtins.open = sperre
    try:
        try:
            fen.schreiben({"geometrie": [9, 9, 9, 9], "maximiert": True})
            wirft = False
        except OSError:
            wirft = True
    finally:
        builtins.open = echt_open
    check("fenster.schreiben bei Lesefehler: wirft OSError (der Aufrufer fängt es) und lässt die Datei stehen",
          wirft and roh() == vorher)
    # fehlende Datei und kaputtes JSON: wie bisher neu schreiben
    os.remove(pfad)
    check("Fehlende Datei: wird neu angelegt", fen.abschnitt_merken("a", True) == pfad and lies() == {"abschnitte": {"a": True}})
    with open(pfad, "w", encoding="utf-8") as f:
        f.write("{kein json")
    check("Kaputtes JSON: wie bisher neu geschrieben", fen.abschnitt_merken("a", True) == pfad
          and lies() == {"abschnitte": {"a": True}})
    # atomar: scheitert das Schreiben mittendrin, bleibt die alte Datei ganz
    schreibe(inhalt)
    vorher = roh()
    echt_dump = fen.json.dump

    def kaputt_dump(obj, fp, *a, **k):
        fp.write('{"abgebrochen": ')
        raise OSError(28, "Kein Speicherplatz mehr")

    fen.json.dump = kaputt_dump
    try:
        r = fen.abschnitt_merken("berechnung_experten", True)
        try:
            fen.schreiben({"geometrie": [1, 1, 1, 1]})
            wirft = False
        except OSError:
            wirft = True
    finally:
        fen.json.dump = echt_dump
    check("Atomar: scheitert das Schreiben mittendrin, bleibt die alte Datei ganz (abschnitt_merken und schreiben)",
          r is None and wirft and roh() == vorher, f"{len(roh())} gegen {len(vorher)} Byte")
    check("… und es bleibt keine halbe Hilfsdatei liegen", os.listdir(ordner) == [os.path.basename(pfad)], str(os.listdir(ordner)))
    # STATIK3D_FENSTER=fest: nichts geschrieben, nichts gelesen
    schreibe(inhalt)
    vorher = roh()
    alt = os.environ.get("STATIK3D_FENSTER")
    os.environ["STATIK3D_FENSTER"] = "fest"
    try:
        r = fen.abschnitt_merken("berechnung_experten", True)
        offen = fen.abschnitt_offen("berechnung_experten")
        offen_vorgabe = fen.abschnitt_offen("berechnung_experten", True)
    finally:
        if alt is None:
            os.environ.pop("STATIK3D_FENSTER", None)
        else:
            os.environ["STATIK3D_FENSTER"] = alt
    check("STATIK3D_FENSTER=fest: abschnitt_merken schreibt nichts, abschnitt_offen gibt die Vorgabe",
          r is None and roh() == vorher and offen is False and offen_vorgabe is True, f"{r} {offen} {offen_vorgabe}")
    schreibe({})


def main():
    for f in (test_reihenfolge, test_inhalt_der_experten, test_vorgabe_zu, test_aufklappen,
              test_werte_zugeklappt, test_zustand_wird_gemerkt, test_nichts_zur_elementwahl, test_breite,
              test_pfade_nennen_experten, test_listen_breit_mit_tooltip, test_kopfzeile_abweichungen,
              test_einstellungsdatei_schutz):
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {str(ex)[:100]}")
    w = _FENSTER.get("w")
    if w is not None:
        w.close()
    fehl = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(fehl)}/{len(RESULTS)} bestanden")
    if fehl:
        print("FEHLGESCHLAGEN:", *fehl, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
