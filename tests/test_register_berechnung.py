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


def main():
    for f in (test_reihenfolge, test_inhalt_der_experten, test_vorgabe_zu, test_aufklappen,
              test_werte_zugeklappt, test_zustand_wird_gemerkt, test_nichts_zur_elementwahl, test_breite):
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
