"""
Rauchtest der Oberflaeche ohne Benutzer (X-Server noetig, z.B. xvfb-run):
    xvfb-run -a python -m tests.test_gui_smoke
Laedt alle Beispiele, rechnet, schaltet alle Anzeigen durch, erzeugt Dialoge
und einen Screenshot.
"""
import io
import os

# Keine Pruefung oeffnet einen Browser: am 11.09.2026 stand beim Anwender
# nach jedem Lauf ein Browserfenster mit tests/_lastenheft_smoke.html, die der
# Lauf gleich wieder geloescht hatte ("Zugriff auf die Datei nicht moeglich").
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

RESULTS = []


def check(name, ok, info=""):
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name} {info}")
    return ok


def _kuerzel_pruefen(w, app):
    """Tastenkuerzel des Ribbons gelten in jedem Register, und keines ist doppelt.

    Gemessen 12.09.2026 (Sonde mit QTest.keyClick auf der echten Anzeige): Qt
    haelt einen ApplicationShortcut fuer inaktiv, solange keines der Widgets
    seiner Aktion sichtbar ist. War das einzige Widget der QToolButton im
    hinteren Register, waehlte Strg+A im Register „Ansicht“ 0 von 17 Knoten,
    im Register „Start“ 17 von 17 - ebenso stumm waren Strg+N/O/I/E/Q, Strg+R,
    Strg+B, Strg+Umschalt+C und Umschalt+F1..F7 ausserhalb ihres Registers.
    Und weil das Kontextregister „Auswahl“ eine Kopie von „Alles deselektieren“
    mit Esc trug, loeste Esc bei sichtbarem Kontextregister gar nichts aus
    („QAction::event: Ambiguous shortcut overload: Esc“). Ein Kuerzel loest
    nur bei aktivem Fenster aus; ohne aktives Fenster wird die Aktion direkt
    ausgeloest und das gesagt.
    """
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    w.load_example("frame")
    app.processEvents()
    nn = w.model.nn
    w.selection = np.arange(min(3, nn))
    w._auswahl_register()              # Kontextregister „Auswahl“ mit seiner Esc-Kopie
    w.ribbon.kontext_zeigen()
    app.processEvents()
    aktionen = [a for a in w.findChildren(QtGui.QAction) if not a.shortcut().isEmpty()]
    check("Kürzel: Aktionen mit Tastenkürzel gefunden", len(aktionen) >= 20, str(len(aktionen)))
    ohne = sorted({a.text() for a in aktionen if w not in a.associatedObjects()})
    check("Kürzel: jede Aktion mit Kürzel ist dem Hauptfenster zugeordnet - das Kürzel gilt in jedem Register",
          not ohne, str(ohne[:6]))

    def aktiv(a):
        return a.isEnabled() and any(
            isinstance(o, QtWidgets.QWidget) and o.isVisible() and o.isEnabled()
            for o in a.associatedObjects())
    je_folge = {}
    for a in aktionen:
        if aktiv(a):
            je_folge.setdefault(a.shortcut().toString(), []).append(a.text())
    doppelt = {k: v for k, v in je_folge.items() if len(v) > 1}
    check("Kürzel: keines doppelt - je Tastenfolge höchstens eine aktive Aktion (Kontextregister „Auswahl“ sichtbar)",
          not doppelt, str(doppelt))
    esc = [a for a in aktionen if a.shortcut().toString() == "Esc"]
    check("Kürzel: Esc trägt genau eine Aktion, „Alles deselektieren“ (die Kopie im Kontextregister ohne Kürzel)",
          [a.text() for a in esc] == ["Alles deselektieren"] and esc[0] is w.act_auswahl_weg,
          str([a.text() for a in esc]))
    strg_a = next((a for a in aktionen if a.shortcut().toString() == "Ctrl+A"), None)
    check("Kürzel: Strg+A ist „Alles auswählen“", strg_a is not None and strg_a.text() == "Alles auswählen",
          strg_a.text() if strg_a else "-")

    # Tastendruecke: Qt loest ein Kuerzel nur bei aktivem Fenster aus
    w.ribbon.zeigen("Ansicht")
    w.plotter.interactor.setFocus()
    app.processEvents()
    aktiv_fenster = w.isActiveWindow()
    print(f"     Fenster aktiv: {aktiv_fenster} (Tastendrücke {'werden' if aktiv_fenster else 'nicht'} geprüft)")
    w.selection = np.arange(0)
    if aktiv_fenster:
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
    else:
        strg_a.trigger()
    app.processEvents()
    check("Strg+A im Register „Ansicht“ wählt alle Knoten", len(w.selection) == nn,
          f"{len(w.selection)} von {nn}" + ("" if aktiv_fenster else " (Aktion direkt ausgelöst)"))
    w.selection = np.arange(min(3, nn))
    w._auswahl_register()
    w.ribbon.kontext_zeigen()
    w.plotter.interactor.setFocus()
    app.processEvents()
    if aktiv_fenster:
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_Escape)
    else:
        w.act_auswahl_weg.trigger()
    app.processEvents()
    check("Esc bei sichtbarem Kontextregister „Auswahl“ hebt die Auswahl auf - das Kürzel ist nicht mehrdeutig",
          len(w.selection) == 0, str(len(w.selection)) + ("" if aktiv_fenster else " (Aktion direkt ausgelöst)"))
    w.ribbon.zeigen("Ansicht")
    w.plotter.interactor.setFocus()
    app.processEvents()
    fang = w.act_fangart["knoten"]
    vorher = fang.isChecked()
    if aktiv_fenster:
        QtTest.QTest.keyClick(w, QtCore.Qt.Key_F1, QtCore.Qt.ShiftModifier)
    else:
        fang.trigger()
    app.processEvents()
    check("Umschalt+F1 im Register „Ansicht“ schaltet den Fang auf Knoten um",
          fang.isChecked() != vorher and ("knoten" in w.fang_arten) == fang.isChecked(),
          f"{vorher} -> {fang.isChecked()}, fang_arten {sorted(w.fang_arten)}")
    fang.setChecked(vorher)
    # Mit dem Cursor in einem Textfeld bleibt Strg+A beim Feld: Qt fragt erst
    # das Fokus-Widget (ShortcutOverride), und ein QLineEdit nimmt Strg+A fuer
    # „Text markieren“ - gemessen 12.09.2026: markiert „probe“, 0 Knoten.
    feld = w.ribbon.suche
    feld.setText("probe")
    feld.setFocus()
    app.processEvents()
    w.selection = np.arange(0)
    if aktiv_fenster:
        QtTest.QTest.keyClick(feld, QtCore.Qt.Key_A, QtCore.Qt.ControlModifier)
        app.processEvents()
        check("Strg+A mit dem Cursor im Textfeld markiert den Text und wählt keine Knoten",
              feld.selectedText() == "probe" and len(w.selection) == 0,
              f"markiert {feld.selectedText()!r}, {len(w.selection)} Knoten")
    feld.clear()
    w.plotter.interactor.setFocus()
    w.ribbon.zeigen("Start")
    app.processEvents()


def main():
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        print("Kein DISPLAY - Test uebersprungen (xvfb-run verwenden)")
        return 0
    # Keine Updatesuche im Test. Sie laeuft sonst 4 s nach dem Start von selbst
    # los, fragt GitHub und blendet den Knopf „Update verfügbar" in die
    # Statusleiste - dann scheitert die Pruefung „Fassung nicht mehr in der
    # Statusleiste" an einer richtigen Meldung statt an einem Fehler. Der Test
    # soll das Fenster pruefen, nicht den Stand des Netzes.
    os.environ["STATIK3D_NO_UPDATE_CHECK"] = "1"
    from PySide6 import QtWidgets, QtGui
    from statik3d import solver
    from statik3d.gui.main import MainWindow, FIELDS, DIAGRAMS
    from statik3d.gui import dialogs as dg
    from statik3d.model import Model
    # Gespeicherte Einstellungen (Loeser, Threads, Nachladen) in eine
    # Wegwerfdatei - die Pruefung darf die des Anwenders nicht ueberschreiben
    import tempfile as _tempfile
    os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(_tempfile.mkdtemp(prefix="statik3d_smoke_einst_"),
                                                        "einstellungen.json")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    app.processEvents()
    check("Fenster erzeugt", w.isVisible())
    # Netz aendern bei vorhandenen Ergebnissen fragt (Vernetzen / Abbrechen) -
    # im Durchlauf stimmt die Antwort zu; der eigene Abschnitt prueft die Frage
    w._fragen_knoepfe = lambda titel, text, ja="Ja", nein="Abbrechen": True

    for ex in ("frame", "truss", "plate", "solid", "hall", "gate", "contact", "friction"):
        t0 = time.time()
        w.load_example(ex)
        app.processEvents()
        m = w.model
        an = solver.solve_all(m, design=bool(m.members), fatigue=bool(m.fatigue_loads))
        w._solve_done("all", an)
        app.processEvents()
        n = w.cb_result.count()
        ok = n > 0 and w.analysis is not None
        for i in range(min(n, 4)):
            w.cb_result.setCurrentIndex(i)
            app.processEvents()
        w.cb_result.setCurrentIndex(0)
        for f in FIELDS:
            w.cb_field.setCurrentText(f)
            app.processEvents()
        for d in DIAGRAMS:
            w.cb_diagram.setCurrentText(d)
            app.processEvents()
        w.cb_diagram.setCurrentText("My")
        w.cb_field.setCurrentText(FIELDS[0])
        w.act_nodes.setChecked(True); w.act_elems.setChecked(True); w.act_members.setChecked(True)
        w.redraw(); app.processEvents()
        w.act_nodes.setChecked(False); w.act_elems.setChecked(False)
        check(f"Beispiel {ex}: geladen, gerechnet, dargestellt", ok,
              f"({n} Ergebnisse, {time.time()-t0:.1f} s, Protokollzeilen {w.log.blockCount()})")
        fehler = [l for l in w.log.toPlainText().splitlines() if l.startswith("FEHLER") or "Darstellung:" in l or "Verlauf:" in l]
        check(f"Beispiel {ex}: keine Darstellungsfehler", not fehler, str(fehler[:2]))

    # Modal / Knicken auf dem Rahmen
    w.load_example("frame"); app.processEvents()
    r = solver.solve_modal(w.model, 4)
    w._solve_done("modal", r); app.processEvents()
    for i in range(w.cb_mode.count()):
        w.cb_mode.setCurrentIndex(i); app.processEvents()
    check("Modalanalyse dargestellt", w.cb_mode.count() == 4)
    r = solver.solve_buckling(w.model, 3)
    w._solve_done("buckling", r); app.processEvents()
    check("Knicken dargestellt", w.cb_mode.count() == 3)
    # Eigenformen mit Kontakt: verklebt statt frei schwingend; ein Fehler steht rechts
    w.load_example("friction"); app.processEvents()
    r = solver.solve_modal(w.model, 4, kontakt=w._kontaktzustand_zuletzt())
    w._solve_done("modal", r); app.processEvents()
    check("Block mit Reibung: Eigenformen mit verklebtem Kontakt, erste Form nicht 0 Hz, Kontakt in der Zusammenfassung",
          w.cb_mode.count() == 4 and "0.000 Hz" not in w.cb_mode.itemText(0)
          and "Kontakt" in w.txt_summary.toPlainText(), w.cb_mode.itemText(0))
    # Tabellen Kontakt (je Knoten, mit Paar) und Kontaktpaare (je Paar) nach einer statischen Rechnung
    rs = solver.solve_static(w.model)
    w._solve_done("case", rs); app.processEvents()
    # der Lastfall, nicht die Umhuellende: Kontaktkraefte gibt es je Lastfall
    for i_ in range(w.cb_result.count()):
        if (w.cb_result.itemData(i_) or ("",))[0] == "case":
            w.cb_result.setCurrentIndex(i_)
            break
    w.show_results(); app.processEvents()
    w.tabelle_zeigen("Kontaktpaare"); app.processEvents()
    zp = list(w.tbl_kontaktpaare.modell.zeilen)
    check("Tabelle Kontaktpaare: Block/Platte mit ΣFn = 90 kN, |Ft| = 20 kN und mittlerer Pressung ΣFn/A",
          len(zp) == 1 and zp[0][0] == "Block/Platte" and abs(float(zp[0][6]) - 90.0) < 2.0
          and abs(float(zp[0][10]) - 20.0) < 1.0
          and abs(float(zp[0][12]) - float(zp[0][6]) * 1e3 / (float(zp[0][11]) * 1e2)) < 1e-3, str(zp[:1]))
    zk = list(w.tbl_contact.modell.zeilen)
    check("Tabelle Kontakt nennt je Knoten das Paar", bool(zk) and zk[0][-1] == "Block/Platte", str(zk[:1]))
    # Netz aendern bei vorhandenen Ergebnissen: Rueckfrage, Abbrechen laesst alles stehen
    w.new_model(); app.processEvents()
    mg_ = w.model
    mg_.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0.]]))
    for i_, (a_, b_) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
        mg_.add_line(f"L{i_ + 1}", [a_, b_])
    f_ = mg_.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke=list(mg_.shells)[0],
                         material=list(mg_.materials)[0], teilung=[4, 2])
    w._vernetzen([f_], []); w.refresh_all(); app.processEvents()
    for i_ in (0, 3):
        mg_.fix(i_, "all")
    mg_.load_node(1, Fz=-1000.0)
    w._solve_done("case", solver.solve_static(mg_)); app.processEvents()
    fragen_n = []
    w._fragen_knoepfe = lambda titel, text, ja="Ja", nein="Abbrechen": (fragen_n.append((titel, ja, nein, text)), False)[1]
    n_el = len(mg_.elements)
    w.geometrie_vernetzen(); app.processEvents()
    check("Vernetzen mit Ergebnissen: Rückfrage „Netz ändern“, Knöpfe Vernetzen/Abbrechen, sie nennt die Löschung",
          len(fragen_n) == 1 and fragen_n[0][0] == "Netz ändern" and fragen_n[0][1] == "Vernetzen"
          and fragen_n[0][2] == "Abbrechen" and "gelöscht" in fragen_n[0][3], str(fragen_n[:1])[:120])
    check("Abbrechen: Ergebnisse und Netz bleiben", w.analysis is not None and len(mg_.elements) == n_el)
    w.netz_loeschen_geometrie(); app.processEvents()
    check("Netz löschen fragt ebenso (Knopf „Netz löschen“) und lässt bei Abbrechen alles stehen",
          len(fragen_n) == 2 and fragen_n[1][1] == "Netz löschen" and w.analysis is not None
          and len(mg_.elements) == n_el, str(fragen_n[1:2])[:80])
    w._fragen_knoepfe = lambda titel, text, ja="Ja", nein="Abbrechen": True
    w.geometrie_vernetzen(); app.processEvents()
    check("Vernetzen bestätigt: die Ergebnisse sind verworfen (auch aus der Auswahl), das Netz neu",
          w.analysis is None and w.results is None and w.cb_result.count() == 0 and len(mg_.elements) > 0,
          f"{w.cb_result.count()} Ergebnisse, {len(mg_.elements)} Elemente")
    check("… ohne Ergebnisse wird nicht gefragt", not any(f[0] == "Netz ändern" for f in fragen_n[2:]))
    w.load_example("friction"); app.processEvents()
    w._solve_done("case", solver.solve_static(w.model)); app.processEvents()
    w._rechnet_gerade = True
    w._bg_failed("Probefehler: Faktorisierung gescheitert", "Traceback (Probe)")
    app.processEvents()
    check("gescheiterte Rechnung: der Grund steht rechts in der Maske Ergebnisse",
          "gescheitert" in w.txt_res.toPlainText() and "Probefehler" in w.txt_res.toPlainText()
          and w.tabs.tabText(w.tabs.currentIndex()) == "Ergebnisse" and not w._rechnet_gerade,
          w.txt_res.toPlainText()[:60])
    w.statusBar().clearMessage()

    # Hintergrund-Berechnung ueber den Worker
    w.load_example("hall"); app.processEvents()
    w.do_solve("all")
    t0 = time.time()
    while w.worker is not None and w.worker.isRunning() and time.time() - t0 < 120:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    check("Hintergrund-Berechnung beendet", w.analysis is not None and w.analysis.design is not None,
          f"({time.time()-t0:.1f} s)")

    # Eingabe-Aktionen: Auswahl, Lager, Lasten, Lastfaelle, Kontakt, Staebe
    w.new_model(); app.processEvents()
    w.beam_p2[0].set(6.0); w.beam_n.setValue(6); w.make_beams(); app.processEvents()
    w.sel[0].setText("0"); w.sel[1].setText("0"); w.do_select(); w.set_support(all_dofs=True)
    w.sel[0].setText("6"); w.sel[1].setText("6"); w.do_select(); w.ld[2].set(-10000); w.add_load()
    w.q[2].set(-2000); w.add_beam_load()
    w.cb_g.setChecked(True)
    w.model.add_load_case("Q", "Q_B"); w.refresh_all()
    w.tbl_lc.selectRow(1); app.processEvents()
    check("aktiver Lastfall umgeschaltet", w.model.active_case == "Q", w.model.active_case)
    w.ld[2].set(-5000); w.add_load()
    from statik3d.combinations import generate_combinations
    generate_combinations(w.model); w.refresh_all()
    w.sel[0].setText("3"); w.sel[1].setText("3"); w.do_select(); w.add_contact_support()
    w.auto_members()
    an = solver.solve_all(w.model, design=True)
    w._solve_done("all", an); app.processEvents()
    check("Eingabe-Aktionen: Modell rechnet", an.design is not None and len(w.model.combinations) > 0,
          f"({len(w.model.combinations)} Kombinationen, {len(w.model.contact_supports)} Kontaktlager)")
    w.show_results(); app.processEvents()
    check("Tabellen gefuellt", w.tbl_design.zeilenzahl() >= 1 and w.tbl_react.zeilenzahl() >= 1)

    # ---- Kennwerte im Bild und Schnittgroessen im Baum -------------------
    from statik3d.gui import viewport as _vp
    r = w.current_result()
    grenzen = _vp.schnittgroessen_grenzen(w.model, r)
    check("Grenzwerte aller sechs Schnittgrößen bestimmt",
          set(grenzen) == set(_vp.SCHNITTGROESSEN), str(sorted(grenzen)))
    # Gegenprobe von Hand: das groesste My aus allen Nachweisstellen
    # (bei einer Umhuellenden aus ihren Grenzwerten)
    quelle = r.stations() if hasattr(r, "stations") else r.beam
    my = max(float(np.max(np.asarray(d["My"], float))) for d in quelle.values())
    check("größtes My stimmt mit der Nachrechnung überein",
          abs(grenzen["My"][2] - my) < 1e-6 * max(abs(my), 1.0),
          f"{grenzen['My'][2]:.6g} / {my:.6g} Nm")
    check("und es steht der Stab dabei, nicht nur die Zahl",
          grenzen["My"][3] in range(len(w.model.elements)), str(grenzen["My"][3]))
    # Seit 15.09.2026 stehen nur die Werte des gewaehlten Ergebnisses im Bild:
    # die Faerbung wird darum ausdruecklich gewaehlt und danach zurueckgestellt
    feld_vorher = w.cb_field.currentText()
    w.cb_diagram.setCurrentText("My")
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()
    zeilen = w._kennwerte_zeichnen(r)
    text = "\n".join(zeilen)
    check("Kennwerte im Bild: zur Färbung |u| die größte Verformung mit Knoten",
          any(z.startswith("u ") and "Knoten" in z for z in zeilen),
          zeilen[0] if zeilen else "-")
    check("Kennwerte im Bild: nur die gewählte Schnittgröße",
          any(z.startswith("My ") for z in zeilen)
          and not any(z.startswith("Vz ") for z in zeilen), text[:80])
    w.cb_field.setCurrentText("uz"); app.processEvents()
    zeilen_uz = w._kennwerte_zeichnen(r)
    check("… zur Färbung uz die Zeile uz", any(z.startswith("uz") for z in zeilen_uz), str(zeilen_uz[:2]))
    w.cb_field.setCurrentText("Ausnutzung EC3"); app.processEvents()
    zeilen = w._kennwerte_zeichnen(r)
    ausn = next((z for z in zeilen if "Ausnutzung" in z), "")
    w.cb_field.setCurrentText(feld_vorher); app.processEvents()
    stab = next(iter(w.model.members), "")
    check("Kennwerte im Bild: größte Ausnutzung mit Ort",
          "max. Ausnutzung" in ausn and " an " in ausn, ausn or "-")
    check("und der Ort ist wirklich ein Stab des Modells",
          any(f" an {n}" in ausn for n in w.model.members) or " an El. " in ausn,
          f"{ausn} (Stäbe: {list(w.model.members)[:3]}, z. B. {stab})")
    w.act_kennwerte.setChecked(False); app.processEvents()
    check("und abschaltbar", not w._kennwerte_zeichnen(r))
    w.act_kennwerte.setChecked(True); app.processEvents()
    # Der Baum fuehrt die Schnittgroessen und ein Klick stellt sie ein
    erg = w._ergebnisliste()
    sg = [k for _t, _z, k in erg.get("Schnittgrößen", [])]
    check("Schnittgrößen stehen im Modellbaum",
          [f"schnittgroesse:{q}" for q in _vp.SCHNITTGROESSEN] ==
          [k for k in sg if not k.endswith("kein Verlauf")], str(sg))
    w.ergebnis_zeigen("schnittgroesse:Vz"); app.processEvents()
    check("ein Klick im Baum stellt den Verlauf ein",
          w.cb_diagram.currentText() == "Vz", w.cb_diagram.currentText())
    w.ergebnis_zeigen("schnittgroesse:kein Verlauf"); app.processEvents()
    check("und lässt sich dort auch wieder abschalten",
          w.cb_diagram.currentText() == "kein Verlauf", w.cb_diagram.currentText())
    w.cb_diagram.setCurrentText("My"); app.processEvents()

    # Dialoge erzeugen (ohne exec)
    d1 = dg.MaterialDialog(w); d1._grade_changed("S355"); mat = d1.result_material()
    d2 = dg.SectionDialog(w); d2.family.setCurrentText("HEB"); sec = d2.result_section()
    d3 = dg.LoadCaseDialog(w, existing=list(w.model.load_cases))
    d4 = dg.CombinationDialog(w, w.model)
    d5 = dg.AutoCombinationDialog(w, w.model.design)
    d6 = dg.FatigueLoadDialog(w, w.model)
    mem = next(iter(w.model.members.values()))
    d7 = dg.MemberDialog(w, mem, 6.0)
    # Wölbkrafttorsion: die Randbedingung der Verwölbung gehört in die Maske
    d7.w_start.setCurrentText("behindert")
    d7.apply(mem)
    check("Wölbrandbedingung aus der Stabmaske übernommen",
          mem.woelb_start == "behindert" and mem.woelb_ende == "frei"
          and mem.woelb_check,
          f"{mem.woelb_start}/{mem.woelb_ende}")
    mem.woelb_start = "frei"
    d7 = dg.MemberDialog(w, mem, 6.0); d7.apply(mem)
    d8 = dg.DesignSettingsDialog(w, w.model.design); d8.apply(w.model.design)
    d8.einfrieren.setChecked(False); d8.apply(w.model.design)
    check("Konfiguration Nachweise: Haken „Ermüdungszustände mit eingefrorenem Kontaktzustand“ wirkt",
          w.model.design.ermuedung_kontakt_einfrieren is False)
    d8.einfrieren.setChecked(True); d8.apply(w.model.design)
    d9 = dg.ContactPairDialog(w, w.model, 2)
    d10 = dg.ImportDialog(w, "test.dxf", w.model); opts = d10.options()
    d11 = dg.ReportDialog(w, w.model, "b.html"); ro = d11.options()
    check("Berichtsdialog: Umfang Kurzform ist die Vorgabe - Elementtabellen und Verlaeufe aus",
          ro.get("umfang") == "kurz" and ro["model_tables"] is False and ro["member_diagrams"] is False
          and ro["design"] is True, str({k: v for k, v in ro.items() if k in ("umfang", "model_tables")}))
    d11.umfang.setCurrentIndex(d11.umfang.findData("lang"))
    check("… Langform schaltet alles ein", d11.options()["model_tables"] is True
          and d11.options()["umfang"] == "lang")
    d11.checks["figures"].setChecked(False)
    check("… ein Haken von Hand macht eine eigene Auswahl", d11.options()["umfang"] == "eigene"
          and d11.options()["figures"] is False)
    d11.apply_meta(w.model)
    check("… der Umfang steht am Modell", w.model.berichtsrahmen().umfang == "eigene")
    d12 = dg.BerichtsrahmenDialog(w, w.model)
    d12.kopf.setText("{projekt} · {position}"); d12.r_links.set(22.0); d12.titel.setChecked(False)
    d12.apply(w.model)
    check("Rahmendialog: Kopfzeile, Rand und Titelblatt am Modell",
          w.model.bericht_rahmen.kopf == "{projekt} · {position}"
          and w.model.bericht_rahmen.rand_links_mm == 22.0 and w.model.bericht_rahmen.titelblatt is False)
    e_t = w.berichtstext_einfuegen("# Hinweis\nProbe", nach="general")
    e_b = w.berichtstabelle_einfuegen("Lastfälle")
    import tempfile as _tf
    _fd, _p = _tf.mkstemp(suffix=".csv"); os.close(_fd)
    with open(_p, "w", encoding="utf-8") as _fh:
        _fh.write("a;b\n1;2\n")
    e_d = w.berichtsdatei_einfuegen(_p)
    os.unlink(_p)
    check("Bericht: Text, Tabelle und Datei eingefuegt, Tabelle Bericht zeigt Art und Platz",
          e_t is not None and e_t.art == "text" and e_t.nach == "general"
          and e_b is not None and e_b.tabelle == "Lastfälle" and e_d is not None and e_d.typ == "csv"
          and [z[6] for z in w.tbl_bericht.modell.zeilen][-3:] == ["Text", "Tabelle", "Datei"]
          and w.tbl_bericht.modell.zeilen[-3][7] == "general",
          str([z[6] for z in w.tbl_bericht.modell.zeilen][-3:]))
    check("Bericht: Platz im Bericht ueber die Tabelle aenderbar, Unsinn abgewiesen",
          w._bericht_aendern(len(w.tbl_bericht.modell.zeilen) - 1, 7, "results")
          and w.model.bericht[-1].nach == "results"
          and not w._bericht_aendern(len(w.tbl_bericht.modell.zeilen) - 1, 7, "kapitelx"))
    check("Ribbon Bericht: Gliederung und Rahmen", getattr(w, "act_berichtsrahmen", None) is not None)
    del w.model.bericht[-3:]
    check("Dialoge erzeugt", mat.fy == 355e6 and sec.typ == "I" and "unit_scale" in opts and ro["design"],
          f"{mat.name} {sec.name}")

    # Neue Lager und Profilauswahl nach Land
    try:
        d = dg.SectionDialog(w)
        laender = [d.country.itemData(i) for i in range(d.country.count())]
        d.country.setCurrentIndex(laender.index("US"))
        us_profile = [d.profile.itemText(i) for i in range(d.profile.count())]
        d.country.setCurrentIndex(laender.index("EU"))
        eu_profile = [d.profile.itemText(i) for i in range(d.profile.count())]
        check("Querschnittsdialog: Laenderauswahl", len(laender) >= 3 and us_profile and eu_profile,
              f"{laender}, US {len(us_profile)} / EU {len(eu_profile)} Profile")
        from statik3d.model import DofBehaviour
        w.new_model()
        w.beam_p2[0].set(6.0); w.beam_n.setValue(4); w.make_beams(); app.processEvents()
        w.sel[0].setText("0"); w.sel[1].setText("0"); w.do_select()
        sup = w.model.support(int(w.selection[0]), [])
        nd = dg.SupportNonlinearDialog(w, sup, "Knotenlager")
        nd.rows[2][0].setCurrentIndex(1)          # uz starr
        nd.rows[2][2].setCurrentIndex(1)          # Ausfall bei Zug
        nd.rows[2][3].setText("2")                # Schlupf 2 mm
        nd.rows[0][0].setCurrentIndex(1)
        nd.rows[0][4].setText("0.3")              # Reibung ux
        nd.rows[0][5].setCurrentIndex(3)          # bezogen auf uz
        beh = nd.behaviours()
        check("Lagerdialog: Nichtlinearitaet",
              beh[2].failure == "zug" and abs(beh[2].slip - 0.002) < 1e-9
              and abs(beh[0].mu - 0.3) < 1e-9 and beh[0].mu_ref == 2,
              f"uz {beh[2].describe()}")
        nd.apply(sup)
        check("Lagerdialog uebernimmt", w.model.supports[-1].dof_behaviour(2).failure == "zug"
              and w.model.has_contact)
    except Exception as ex:
        check("Neue Lager und Profilauswahl", False, str(ex))

    # Web-Server (Browser / Handy) am GUI-Modell: Aenderung vom "Handy" erscheint in der GUI
    try:
        import json
        import urllib.request
        from statik3d.web import start_server_thread
        srv, th, st = start_server_thread(None, host="127.0.0.1", port=0, key=None, bound=w)
        w.web_server, w.web_thread, w.web_state = srv, th, st
        w.web_version = st.version
        nn0 = w.model.nn
        body = json.dumps({"op": "add_node", "x": 1, "y": 2, "z": 3}).encode("utf-8")
        req = urllib.request.Request(srv.local_url + "api/op", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode("utf-8"))
        w._web_poll(); app.processEvents()
        check("Web-Server am GUI-Modell: Handy-Aenderung uebernommen",
              j["state"]["nn"] == nn0 + 1 and w.model.nn == nn0 + 1
              and f"{nn0 + 1} Knoten" in w.lbl_netz.text(),
              srv.local_url)
        w.stop_web_server()
        check("Web-Server beendet", w.web_server is None)
    except Exception as ex:
        check("Web-Server am GUI-Modell", False, str(ex))

    # Anschlussdialog: Typ waehlen, Vorschlag rechnen
    try:
        from statik3d.gui.dialogs import JointDialog
        from statik3d.model import Section
        if "IPE 400" not in w.model.sections:
            w.model.add_section(Section.from_profile("IPE 400"))
        n0 = w.model.add_node(0.0, -3.0, 0.0)
        n1 = w.model.add_node(6.0, -3.0, 0.0)
        e = w.model.add_element("beam", [n0, n1], next(iter(w.model.materials)), "IPE 400")
        d = JointDialog(w, w.model, e, 1, {"N": -100e3, "Vz": 90e3, "My": 180e3})
        d.update_proposal()
        t = d.result_template()
        check("Anschlussdialog: Vorschlag erzeugt", t is not None,
              type(t).__name__ if t else "-")
        check("Anschlussdialog: Bericht mit Ausnutzung", "eta" in d.txt.toPlainText())
        d.cb_typ.setCurrentIndex(1)
        check("Anschlussdialog: Typwechsel rechnet neu",
              d.result_template() is not None and
              type(d.result_template()).__name__ == "Splice",
              type(d.result_template()).__name__)
        check("Anschlussdialog: Schnittgroessen ablesbar",
              abs(d.forces()["My"] - 180e3) < 1.0, str(d.forces()))
        d.close()
        w.selection = np.array([n1], dtype=int)
        el, end = w._selected_beam_end()
        check("Stabende aus der Auswahl bestimmt", el == e and end == 1, f"{el}/{end}")
    except Exception as ex:      # noqa: BLE001
        check("Anschlussdialog", False, str(ex)[:70])

    # Werkbank: Kopfzeile, Werkzeugleiste, Modellbaum, Filmstreifen, Stellungen
    try:
        from statik3d.bridges.positions import Stellung
        from statik3d.gui import design as dsg
        w.load_example("gate")
        w.model.meta["Bauteil"] = "Klappbruecke"
        w._stellungen_obj()[:] = [Stellung(name=f"S{i}", winkel=float(a), beschreibung=t)
                        for i, (a, t) in enumerate(((0, "geschlossen"), (32, "Zwischen"),
                                                    (82, "offen")), 1)]
        w.refresh_all()
        app.processEvents()
        check("Kopfzeile nennt Bauteil und Version",
              "Klappbruecke" in w.kopf.titel.text() and "Statik3D" in w.kopf.titel.text(),
              w.kopf.titel.text()[:60])
        check("Kopfzeile nennt Knoten, Elemente und Stellungen",
              "Stellungen" in w.kopf.marke_modell.text(), w.kopf.marke_modell.text())
        check("Ribbon sitzt neben der Kopfzeile im Menuewidget",
              w.menuWidget() is not None and w.ribbon.parent() is w.menuWidget(),
              str(type(w.ribbon.parent()).__name__))
        check("Kopfzeile und Ribbon teilen sich das Menuewidget",
              w.menuWidget().height() >= w.kopf.height() + 40,
              f"{w.menuWidget().height()} >= {w.kopf.height()} + 40")
        # Der Grund der Kopfzeile muss dunkel bleiben: ein schlichtes QWidget
        # zeichnet den Hintergrund aus dem Stilblatt nur mit WA_StyledBackground,
        # sonst zieht die allgemeine QWidget-Regel die Zeile hell.
        bild = w.kopf.grab().toImage()
        farbe = bild.pixelColor(max(1, bild.width() - 400), bild.height() // 2)
        check("Kopfzeile ist dunkel hinterlegt",
              farbe.red() < 90 and farbe.green() < 90 and farbe.blue() < 110,
              f"RGB {farbe.red()},{farbe.green()},{farbe.blue()}")
        logo = w.kopf.logo.grab().toImage()
        hell = max(logo.pixelColor(x, logo.height() // 2).lightness()
                   for x in range(0, logo.width(), 3))
        check("Programmname hebt sich vom Grund ab", hell > 180, f"Helligkeit {hell}")
        # Ribbon: jeder Befehl genau einmal, keine zweite Leiste daneben
        register = [w.ribbon.tabs.tabText(i) for i in range(w.ribbon.tabs.count())]
        check("Ribbon mit den Registern der Vorgabe",
              register[:6] == ["Datei", "Start", "Unterlagen", "Geometrie", "Struktur", "Lager / Kontakt"]
              and "Berechnung" in register and "Extras" in register, str(len(register)))
        check("Befehle im Ribbon vermerkt", len(w.ribbon.befehle) > 60,
              str(len(w.ribbon.befehle)))
        namen = [b.text for b in w.ribbon.befehle]
        check("Berechnen gibt es genau einmal", namen.count("Berechnen") == 1)
        check("Befehlssuche findet den Befehl",
              w.ribbon.finden("berechnen")[0].text == "Berechnen")
        check("Befehlssuche meldet Fehlgriff", w.ribbon.finden("gibtsnicht") == [])
        check("Schnellzugriff nutzt dieselben Aktionen",
              all(a in [b.aktion for b in w.ribbon.befehle]
                  for a in w.ribbon.schnellzugriff.actions()),
              str(len(w.ribbon.schnellzugriff.actions())))
        check("Keine Menueleiste und keine Werkzeugleiste mehr",
              not hasattr(w, "menu_bar") and not hasattr(w, "werkzeugleiste"))
        check("Maskenleiste rechts ist verschwunden", not w.tabs.tabBar().isVisible())
        w.maske_zeigen("Netz")
        check("Maske wird ueber den Docktitel benannt",
              w.eingaben_dock.windowTitle() == "Netz", w.eingaben_dock.windowTitle())
        check("Register des Ribbons anwaehlbar", w.register_zeigen("Berechnung")
              and w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex()) == "Berechnung")
        unten = [w.tab_unten.tabText(i) for i in range(w.tab_unten.count())]
        check("Werkstoffe, Querschnitte und Dicken stehen unten",
              {"Werkstoffe", "Querschnitte", "Dicken"} <= set(unten), str(unten))
        check("Tabelle laesst sich vorholen", w.tabelle_zeigen("Querschnitte")
              and w.tab_unten.tabText(w.tab_unten.currentIndex()) == "Querschnitte")
        check("Statusleiste zeigt Netz und Solver",
              "Knoten" in w.lbl_netz.text() and w.lbl_solver.text().startswith("Solver"),
              w.lbl_netz.text())
        check("Fassung nicht mehr in der Statusleiste",
              not w.btn_update.isVisible() and not w.lbl_version.isVisible(),
              f"Updateknopf {w.btn_update.isVisible()}, Version {w.lbl_version.isVisible()}")
        # Austausch nur, wenn nichts rechnet - und dann sofort (11.09.2026:
        # das Skript gab nach 120 s auf, die neue Fassung startete nicht)
        from statik3d import update as _upd
        alt_inst_ = _upd.andere_instanzen
        _upd.andere_instanzen = lambda: []          # auf dieser Maschine koennten Reste laufen
        check("Austausch erlaubt, wenn nichts läuft", w._update_moeglich() == "", w._update_moeglich())
        _upd.andere_instanzen = lambda: [4711]
        check("Austausch nicht neben einer weiteren Instanz (Reste einer früheren Sitzung)",
              "4711" in w._update_moeglich() and "Task-Manager" in w._update_moeglich(),
              w._update_moeglich())
        _upd.andere_instanzen = lambda: []
        w._rechnet_gerade = True
        check("Austausch nicht während einer Berechnung", "Berechnung" in w._update_moeglich(),
              w._update_moeglich())
        w._rechnet_gerade = False
        w._fortschritt_beginnen(10, "Test")
        check("Austausch nicht während einer Vernetzung", "Vernetzung" in w._update_moeglich(),
              w._update_moeglich())
        w._fortschritt_ende()
        check("und danach wieder", w._update_moeglich() == "", w._update_moeglich())
        aufrufe_ = []
        alt_helper_, alt_quit_ = _upd.start_helper, QtWidgets.QApplication.quit
        _upd.start_helper = lambda bat, new="": aufrufe_.append(("helper", bat))
        QtWidgets.QApplication.quit = staticmethod(lambda: aufrufe_.append(("quit", "")))
        try:
            w._update_bat = "x.bat"
            w._austausch_starten()
        finally:
            _upd.start_helper, QtWidgets.QApplication.quit = alt_helper_, alt_quit_
            _upd.andere_instanzen = alt_inst_
        check("Austausch: Skript gestartet, quit gerufen, sofortiges Ende vorgemerkt",
              [a for a, _ in aufrufe_] == ["helper", "quit"] and getattr(w, "_austausch_laeuft", False),
              str(aufrufe_))
        w._austausch_laeuft = False
        check("das Austauschskript wartet 300 s auf das Ende", "lss 300" in _upd.UPDATE_BAT)
        check("Modellbaum gefuellt", w.baum.topLevelItemCount() >= 1
              and w.baum.topLevelItem(0).childCount() >= 5,
              str(w.baum.topLevelItem(0).childCount()))
        check("Viewport bleibt frei - kein Filmstreifen mehr", not hasattr(w, "film"))
        def stellungszweig():
            """Der Zweig 'Stellungen' - nach jedem Auffrischen neu zu holen,
            weil der Baum dabei neu aufgebaut wird."""
            wurzel = w.baum.topLevelItem(0)
            for i in range(wurzel.childCount()):
                if wurzel.child(i).text(0) == "Stellungen":
                    return wurzel.child(i)
            return None

        zweig = stellungszweig()
        check("Stellungen stehen im Modellbaum",
              zweig is not None and zweig.childCount() == 4,
              str(zweig.childCount() if zweig else "kein Zweig"))
        check("Modellbaum bietet das Anlegen an",
              zweig.child(zweig.childCount() - 1).text(0).startswith("+ Stellung"))
        check("Stellungstabelle gefuellt", w.tbl_stellung.rowCount() == 3,
              str(w.tbl_stellung.rowCount()))

        w._stellung_gewaehlt("S2")
        check("Stellung auswaehlbar", w.tbl_stellung.currentRow() == 1
              and getattr(w, "gewaehlte_stellung", "") == "S2",
              str(w.tbl_stellung.currentRow()))
        # Stellung per Maus: Klick auf Stab, Flaeche oder Volumen schaltet aus und ein
        w._baum_geklickt("stellung", "S2"); app.processEvents()
        mk = w.maskenrand.maske
        check("Maske der Stellung: Klickmodus an (Stab, Fläche, Volumen in der Ansicht)",
              mk is not None and getattr(mk, "objekt_modus", "") == "stellung" and "klick" in mk._felder,
              str(getattr(mk, "objekt_modus", None)))
        if mk is not None:
            if w.model.members:
                art_k, obj_k, feld_k = "stab", next(iter(w.model.members)), "staebe_aus"
            elif w.model.flaechen:
                art_k, obj_k, feld_k = "flaeche", next(iter(w.model.flaechen)), "flaechen_aus"
            else:
                art_k, obj_k, feld_k = "volumen", next(iter(w.model.koerper), ""), "koerper_aus"
            mk.objekt_angeklickt(art_k, obj_k); app.processEvents()
            check(f"Klick auf {obj_k} schaltet es aus (steht in der Liste, Vorschau blendet aus)",
                  obj_k in w._namensliste(mk.werte().get(feld_k)),
                  f"{mk.werte().get(feld_k)!r}, {len(w.versteckt['elemente'])} Elemente ausgeblendet")
            mk.objekt_angeklickt(art_k, obj_k); app.processEvents()
            check("… noch ein Klick schaltet es wieder ein",
                  obj_k not in w._namensliste(mk.werte().get(feld_k)))
            check("Gelenke und Lager sind Listen zum Anhaken",
                  type(mk._felder.get("lager_aus")).__name__ == "QListWidget"
                  and type(mk._felder.get("gelenke_aus")).__name__ == "QListWidget")
            mk._felder["klick"].setChecked(False); app.processEvents()
            check("Haken aus: kein Klickmodus mehr", getattr(mk, "objekt_modus", "") == "")
        w.maskenrand.schliessen(); app.processEvents()
        # Situation: Lastfaelle und Kombinationen anhaken statt tippen
        w.situation_neu(); app.processEvents()
        mk = w.maskenrand.maske
        lf = next(iter(w.model.load_cases), "")
        check("Maske der Situation: Lastfälle und Kombinationen als Listen zum Anhaken",
              mk is not None and type(mk._felder.get("lastfaelle")).__name__ == "QListWidget"
              and type(mk._felder.get("kombinationen")).__name__ == "QListWidget"
              and mk._felder["lastfaelle"].count() == len(w.model.load_cases), str(len(w.model.load_cases)))
        if mk is not None and lf:
            mk.setzen("lastfaelle", lf)
            check("Anhaken eines Lastfalls: die Maske liefert seinen Namen",
                  mk.werte().get("lastfaelle") == lf, str(mk.werte().get("lastfaelle")))
            mk.zusatzknoepfe["Alle Lastfälle und Kombinationen"].click(); app.processEvents()
            check("„Alle Lastfälle und Kombinationen“ hakt alle an",
                  w._namensliste(mk.werte().get("lastfaelle")) == list(w.model.load_cases),
                  str(mk.werte().get("lastfaelle"))[:60])
        if mk is not None:
            mk.abbrechen(); app.processEvents()

        w.stellungen_rechnen()
        app.processEvents()
        u = getattr(w, "umhuellende", None)
        check("Stellungen gerechnet", u is not None and u.eta > 0,
              f"eta = {getattr(u, 'eta', 0):.3f}")
        check("Umhuellende in der Oberflaeche", "η" in w.lbl_umh.text(), w.lbl_umh.text()[:60])
        w.refresh_all()
        z2 = stellungszweig()
        marke = " ".join(z2.child(i).text(0) for i in range(z2.childCount()))
        check("Massgebende Stellung im Baum gekennzeichnet", "★" in marke, marke[:70])

        w.din19704_bilden()
        text = w.txt_regelwerk.toPlainText()
        check("DIN 19704: Beiwerte mit Zustand", "zu bestätigen" in text, text[:60])
        check("ZTV-ING-Pruefliste in der Oberflaeche", "ZTV-ING" in text)
        check("Kombinationen im Modell angelegt",
              any(k.startswith("DIN ") for k in w.model.combinations),
              str(len(w.model.combinations)))

        w.stellung_entfernen()
        check("Stellung entfernt", len(w._stellungen_obj()) == 2, str(len(w._stellungen_obj())))

        # Nicht-modale Masken: „Maske oder Klick“ (Vorgabe Kap. 3.8)
        w.load_example("frame")
        w.refresh_all()
        w.maske_knoten()
        m = w.maskenrand.maske
        check("Maske steht im rechten Eingabebereich, nicht über der Ansicht",
              m is not None and m.isVisible() and m.parent() is not w.centralWidget(),
              m.titel if m else "keine")
        nn0 = w.model.nn
        m.setzen("x", 9.0)
        m.setzen("z", 2.5)
        m.anwenden()
        check("Maske legt den Knoten aus den Werten an",
              w.model.nn == nn0 + 1
              and abs(float(w.model.nodes[-1][0]) - 9.0) < 1e-9
              and abs(float(w.model.nodes[-1][2]) - 2.5) < 1e-9,
              str(np.round(w.model.nodes[-1], 2)))
        check("Maske bleibt fuer das naechste Objekt offen", m.isVisible())

        w.maske_stab()
        m = w.maskenrand.maske
        check("Erzeuge-Befehl loest die vorige Maske ab",
              m.titel == "Stab" and m.n_knoten == 2)
        ne0 = len(w.model.elements)
        m.knoten_angeklickt(0)
        check("Erster Klick erzeugt noch nichts",
              len(w.model.elements) == ne0 and len(m.gewaehlt) == 1)
        m.knoten_angeklickt(3)
        check("Zweiter Klick erzeugt den Stab", len(w.model.elements) == ne0 + 1,
              str(len(w.model.elements) - ne0))
        check("Maske ist gleich fuer den naechsten Stab bereit",
              m.gewaehlt == [] and m.isVisible())
        e = w.model.elements[-1]
        check("Stab bekommt Querschnitt und Material aus der Maske",
              e.sec in w.model.sections and e.mat in w.model.materials,
              f"{e.sec} / {e.mat}")

        m.knoten_angeklickt(2)
        m.knoten_angeklickt(2)
        check("Erneutes Anklicken nimmt den Knoten wieder heraus", m.gewaehlt == [])
        w.maskenrand.schliessen()
        check("Maske laesst sich schliessen", w.maskenrand.maske is None)
        check("Ohne Maske geht der Klick wieder an die Auswahl",
              not w.maskenrand.knoten_angeklickt(1))

        # Kontextabhaengiges Register statt „Elemente ändern“ im Panel
        w.clear_selection()
        n_reg = w.ribbon.tabs.count()
        w._set_selection([0, 1, 2])
        check("Register „Auswahl“ erscheint mit der Auswahl",
              w.ribbon.tabs.count() == n_reg + 1
              and w.ribbon.tabs.tabText(w.ribbon.tabs.count() - 1) == "Auswahl: 3 Knoten",
              w.ribbon.tabs.tabText(w.ribbon.tabs.count() - 1))
        check("Zuweisen sitzt im Auswahlregister",
              any(b.text == "Zuweisen" and b.register.startswith("Auswahl")
                  for b in w.ribbon.befehle))
        check("Register laesst sich vorholen", w.ribbon.kontext_zeigen())
        w.clear_selection()
        check("Ohne Auswahl verschwindet das Register",
              w.ribbon.tabs.count() == n_reg,
              str(w.ribbon.tabs.count()))
        check("Befehle des Registers sind wieder abgemeldet",
              not any(b.register.startswith("Auswahl") for b in w.ribbon.befehle))

        # Rueckgaengig / Wiederholen
        w.load_example("frame")
        w.refresh_all()
        nn0 = w.model.nn
        w.merken("Testknoten")
        w.model.add_node(9.0, 9.0, 9.0)
        w.refresh_all()
        check("Aenderung wird gemerkt", w.act_undo.isEnabled() and w.model.nn == nn0 + 1)
        w.undo()
        check("Rueckgaengig nimmt sie zurueck", w.model.nn == nn0, str(w.model.nn))
        check("Wiederholen wird moeglich", w.act_redo.isEnabled())
        w.redo()
        check("Wiederholen legt sie wieder an", w.model.nn == nn0 + 1)
        w.undo()
        w.undo()
        check("Leerer Stapel stoert nicht",
              w.model.nn == nn0 and not w.act_undo.isEnabled())

        # Koordinatensystem, Arbeitsebene, Fang
        check("Statusleiste nennt Koordinatensystem und Fang",
              "global" in w.lbl_ks.text() and "Raster" in w.lbl_fang.text(),
              w.lbl_fang.text())
        w.arbeitsebene_setzen(ebene="xz", raster=0.25)
        check("Arbeitsebene laesst sich umstellen",
              w.arbeitsebene.ebene == "xz" and abs(w.arbeitsebene.raster - 0.25) < 1e-12
              and "0.25" in w.lbl_fang.text().replace(",", "."), w.lbl_fang.text())
        w.arbeitsebene_setzen(ebene="xy", raster=0.5)
        i0 = w.model.add_node(0.0, 0.0, 0.0)
        i1 = w.model.add_node(2.0, 0.0, 0.0)
        i2 = w.model.add_node(0.0, 3.0, 0.0)
        w._set_selection([i0, i1, i2])
        w.ks_aus_auswahl()
        check("Koordinatensystem aus drei Knoten",
              w.ks_aktiv != "global" and len(w.ks_liste) == 2, w.ks_aktiv)
        check("Aktives KS steht in der Statusleiste", w.ks_aktiv in w.lbl_ks.text())
        w.ks_waehlen("global")
        check("Zurueck auf global", w.ks_aktiv == "global")
        t = w._fangen((0.02, 0.01, 0.0))
        check("Fang zieht auf den Knoten", t.art == "knoten", t.text())
        w.fang_umschalten(False)
        check("Fang laesst sich abschalten",
              w._fangen((0.02, 0.01, 0.0)).art == "" and "aus" in w.lbl_fang.text())
        w.fang_umschalten(True)

        # Der Fang unter dem Mauszeiger wird in Bildschirmpunkten gemessen.
        # Genau das war vorher ungenau: gerechnet wurde in Metern, mit einem
        # Radius von 5 % der Modellgroesse.
        w.redraw()
        app.processEvents()
        xy, sichtbar = w._projizieren(w.model.nodes)
        breite, hoehe = w.plotter.render_window.GetSize()
        check("Knoten lassen sich auf das Fenster abbilden",
              bool(sichtbar.any())
              and bool(np.all(xy[sichtbar, 0] >= -breite))
              and bool(np.all(xy[sichtbar, 0] <= 2 * breite)),
              f"{int(sichtbar.sum())} von {len(xy)} sichtbar")
        ziel = int(np.flatnonzero(sichtbar)[0])
        w.plotter.iren.interactor.SetEventPosition(int(round(xy[ziel][0])),
                                                   int(round(xy[ziel][1])))
        treffer = w._naechster_am_zeiger(w.model.nodes)
        check("der Zeiger findet genau diesen Knoten",
              treffer is not None and treffer[0] == ziel,
              f"{treffer} statt {ziel}")
        w.plotter.iren.interactor.SetEventPosition(int(round(xy[ziel][0])) + 60,
                                                   int(round(xy[ziel][1])) + 60)
        check("und daneben faengt er nichts",
              w._naechster_am_zeiger(w.model.nodes) is None)

        # Linien: Bogen aus drei angeklickten Knoten
        w.clear_selection()
        w.maske_linie()
        m = w.maskenrand.maske
        check("Linienmaske verlangt drei Knoten",
              m.titel == "Linie" and m.n_knoten == 3)
        check("Vorgabe der Linienart ist die Polylinie",
              m.werte().get("art", "").startswith("Polylinie"),
              str(m.werte().get("art")))
        m.setzen("art", "Bogen (3 Knoten)")      # für diesen Test ausdrücklich
        a = w.model.add_node(2.0, 0.0, 6.0)
        b = w.model.add_node(0.0, 2.0, 6.0)
        c = w.model.add_node(-2.0, 0.0, 6.0)
        ne0, nl0 = len(w.model.elements), len(w.model.lines)
        m.knoten_angeklickt(a)
        m.knoten_angeklickt(b)
        m.knoten_angeklickt(c)
        check("Bogen wird angelegt", len(w.model.lines) == nl0 + 1,
              str(list(w.model.lines)))
        ln = list(w.model.lines.values())[-1]
        check("Bogenlaenge stimmt (Halbkreis r = 2)",
              abs(ln.laenge(w.model) - 2 * np.pi) < 1e-9,
              f"{ln.laenge(w.model):.6f}")
        check("Staebe entlang des Bogens erzeugt",
              len(w.model.elements) - ne0 == 8, str(len(w.model.elements) - ne0))
        w.undo()
        check("Linie laesst sich zuruecknehmen", len(w.model.lines) == nl0)

    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Werkbank", False, str(ex)[:70])

    # ---- Tabellen: Filter, Sortierung, Spalten, Export, Editieren -------
    try:
        import tempfile
        from PySide6 import QtCore
        from statik3d.gui import tabellen as tb

        w.load_example("hall")
        an = solver.solve_all(w.model, design=True)
        w._solve_done("all", an)
        for idx in range(w.cb_result.count()):     # eine Kombination, keine Umhuellende
            if w.cb_result.itemData(idx)[0] in ("combo", "case"):
                w.cb_result.setCurrentIndex(idx)
                break
        w.show_results()
        app.processEvents()
        t = w.tbl_beam
        n_alle = t.zeilenzahl()
        check("Ergebnistabelle ist eine Datentabelle", isinstance(t, tb.Datentabelle))
        check("Stabkraefte gefuellt", n_alle > 10, f"{n_alle} Zeilen")
        check("Tabelle startet aufsteigend, nicht verkehrt herum",
              [t.filter.data(t.filter.index(r, 0), QtCore.Qt.UserRole)
               for r in range(min(3, t.filter.rowCount()))] == [0.0, 1.0, 2.0],
              str([t.filter.data(t.filter.index(r, 0), QtCore.Qt.UserRole)
                   for r in range(min(3, t.filter.rowCount()))]))
        check("Zahlen sind Zahlen, kein Text",
              isinstance(t.modell.zeilen[0][1], float), type(t.modell.zeilen[0][1]).__name__)
        check("Anzeige mit deutschem Komma",
              "," in t.modell.data(t.modell.index(0, 1), QtCore.Qt.DisplayRole),
              t.modell.data(t.modell.index(0, 1), QtCore.Qt.DisplayRole))

        # Kennwerte stehen in der eigenen Fusszeile und wandern beim Sortieren nicht
        check("Fusszeile Max/Min sichtbar",
              not t.fuss.isHidden() and t.fussmodell.rowCount() == 2)
        n1 = [z[1] for z in t.modell.zeilen]
        check("Max der Fusszeile stimmt",
              abs(float(t.fussmodell.zeilen[0][1]) - max(n1)) < 1e-9,
              f"{t.fussmodell.zeilen[0][1]:.3f} / {max(n1):.3f}")
        check("Min der Fusszeile stimmt",
              abs(float(t.fussmodell.zeilen[1][1]) - min(n1)) < 1e-9)
        check("Kennwerte sind keine Tabellenzeilen", t.modell.rowCount() == n_alle)

        # Filter - die Schranke liegt in der Mitte der Werte, damit etwas
        # wegfaellt und etwas stehen bleibt
        n1 = [float(x) for x in n1]
        grenze = float(f"{min(n1) + 0.5 * (max(n1) - min(n1)):.6f}")
        t.felder[1].setText(f"> {grenze}")
        app.processEvents()
        n_gefiltert = t.sichtbar()
        soll = sum(1 for x in n1 if x > grenze)
        check(f"Kopfzeilenfilter „> {grenze:.2f}“ wirkt",
              n_gefiltert == soll and 0 < n_gefiltert < n_alle,
              f"{n_gefiltert} von {n_alle} (erwartet {soll})")
        check("Zeilenzaehler nennt beide Zahlen",
              f"{n_gefiltert} von {n_alle}" in t.lbl_zeilen.text(), t.lbl_zeilen.text())
        check("Kennwerte folgen dem Filter",
              float(t.fussmodell.zeilen[1][1]) > grenze,
              f"Min = {float(t.fussmodell.zeilen[1][1]):.3f} > {grenze:.3f}")
        csv_gefiltert = t.text()
        check("Export nimmt nur die sichtbaren Zeilen",
              len(csv_gefiltert.strip().splitlines()) == n_gefiltert + 3,
              f"{len(csv_gefiltert.strip().splitlines())} Zeilen (+ Kopf, Max, Min)")
        t.filter_leeren()
        app.processEvents()
        check("Filter leeren stellt alles wieder her", t.sichtbar() == n_alle)

        # Sortierung: nach Zahl, nicht nach Text
        t.view.sortByColumn(1, QtCore.Qt.AscendingOrder)
        app.processEvents()
        folge = [t.filter.data(t.filter.index(r, 1), QtCore.Qt.UserRole)
                 for r in range(t.filter.rowCount())]
        check("Sortierung ist numerisch",
              all(a <= b for a, b in zip(folge, folge[1:])),
              f"{folge[0]:.2f} … {folge[-1]:.2f}")
        t.view.sortByColumn(0, QtCore.Qt.AscendingOrder)

        # Spalten aus- und einblenden
        t.view.setColumnHidden(3, True)
        t._filterbreiten()
        check("Ausgeblendete Spalte blendet auch ihr Filterfeld aus",
              t.felder[3].isHidden())
        t.view.setColumnHidden(3, False)
        t._filterbreiten()
        check("Spalte laesst sich wieder einblenden", not t.felder[3].isHidden())

        # Export
        with tempfile.TemporaryDirectory() as d:
            pfad = t.export_csv(os.path.join(d, "stab.csv"))
            zeilen = open(pfad, encoding="utf-8-sig").read().strip().splitlines()
            check("CSV geschrieben", len(zeilen) == n_alle + 3,
                  f"{len(zeilen)} Zeilen")
            check("CSV-Kopf hat die Einheiten", zeilen[0].startswith("Element;N1 [kN]"), zeilen[0])
            xl = t.export_xlsx(os.path.join(d, "stab.xlsx"))
            check("Excel geschrieben", os.path.getsize(xl) > 1000, f"{os.path.getsize(xl)} B")
        check("Zwischenablage bekommt die Tabelle",
              t.in_zwischenablage().startswith("Element;"))
        w.tabelle_zeigen("Stabkräfte")
        app.processEvents()
        check("Ribbon findet die vordere Tabelle", w.aktive_tabelle() is t)
        w.tabelle_ausgeben("clip")
        check("Ribbon gibt sie aus", "Zeilen in der Zwischenablage" in w.log.toPlainText())
        w.tabelle_zeigen("Werkstoffe")
        app.processEvents()
        check("Auch die Eingabetabelle wird gefunden", w.aktive_tabelle() is w.tbl_mat)
        w.tabelle_zeigen("Stabkräfte")

        # Tabelle und Ansicht: hin und zurueck
        e0 = int(t.modell.zeilen[0][0])
        t.zeile_gewaehlt.emit(e0)
        app.processEvents()
        knoten = sorted(int(n) for n in w.model.elements[e0].nodes)
        check("Klick in der Tabelle waehlt das Element in der Ansicht",
              sorted(int(n) for n in w.selection) == knoten, str(knoten))
        check("Auswahl markiert die Zeile zurueck",
              [i.data(QtCore.Qt.UserRole) for i in t.view.selectionModel().selectedRows()] == [e0],
              str([i.data(QtCore.Qt.UserRole) for i in t.view.selectionModel().selectedRows()]))
        w._set_selection(sorted({int(n) for e in w.model.elements[:3] for n in e.nodes}))
        app.processEvents()
        check("Mehrere Zeilen bleiben zugleich markiert",
              len(t.view.selectionModel().selectedRows()) >= 2,
              f"{len(t.view.selectionModel().selectedRows())} Zeilen")
        w.tbl_react.zeile_gewaehlt.emit(int(w.tbl_react.modell.zeilen[0][0]))
        app.processEvents()
        check("Auflagerzeile waehlt den Knoten", len(w.selection) == 1, str(w.selection))
        w.clear_selection()

        # Nachweise: erste Spalte ist der Stabname
        if w.tbl_design.zeilenzahl():
            stab = str(w.tbl_design.modell.zeilen[0][0])
            w.tbl_design.zeile_gewaehlt.emit(stab)
            app.processEvents()
            check("Nachweiszeile waehlt den ganzen Stab",
                  len(w.selection) >= 2, f"{stab}: {len(w.selection)} Knoten")
            check("Nachweistabelle hat Kennwerte", w.tbl_design.fussmodell.rowCount() == 2)
            w.clear_selection()

        # Umhuellende: dieselbe Tabelle, anderes Ergebnis
        for idx in range(w.cb_result.count()):
            if w.cb_result.itemData(idx)[0] == "env":
                w.cb_result.setCurrentIndex(idx)
                break
        w.show_results()
        app.processEvents()
        check("Umhuellende fuellt ihre Tabelle", w.tbl_env.zeilenzahl() > 0,
              f"{w.tbl_env.zeilenzahl()} Zeilen")
        check("Stabkraefte sind dabei leer", w.tbl_beam.zeilenzahl() == 0)
        check("Leere Tabelle zeigt keine Kennwerte", w.tbl_beam.fuss.isHidden())

        # Eingabetabellen: editierbar, mit Formel, mit Grenzen, ruecknehmbar
        name = list(w.model.materials)[0]
        E0 = w.model.materials[name].E
        i = w.tbl_mat.modell.index(0, 1)
        check("Zelle ist editierbar",
              bool(w.tbl_mat.modell.flags(i) & QtCore.Qt.ItemIsEditable))
        check("Name bleibt geschuetzt",
              not (w.tbl_mat.modell.flags(w.tbl_mat.modell.index(0, 0))
                   & QtCore.Qt.ItemIsEditable))
        ok = w.tbl_mat.modell.setData(i, "= 210/1,05")
        check("Formel in der Zelle gerechnet",
              ok and abs(w.model.materials[name].E - 200e9) < 1e3,
              f"E = {w.model.materials[name].E / 1e9:.3f} GPa")
        nu0 = w.model.materials[name].nu
        schlecht = w.tbl_mat.modell.setData(w.tbl_mat.modell.index(0, 2), "0,9")
        check("Unmoeglicher Wert wird abgewiesen",
              not schlecht and w.model.materials[name].nu == nu0,
              f"ν = {w.model.materials[name].nu}")
        unfug = w.tbl_mat.modell.setData(w.tbl_mat.modell.index(0, 3), "Unfug")
        check("Text in einer Zahlenspalte wird abgewiesen", not unfug)
        w.undo()
        app.processEvents()
        check("Zellaenderung laesst sich zuruecknehmen",
              abs(w.model.materials[name].E - E0) < 1e3,
              f"E = {w.model.materials[name].E / 1e9:.3f} GPa")

        sname = list(w.model.sections)[0]
        A0 = w.model.sections[sname].A
        ok = w.tbl_sec.modell.setData(w.tbl_sec.modell.index(0, 2), "= 100*1,5")
        check("Querschnittsflaeche editierbar",
              ok and abs(w.model.sections[sname].A - 150e-4) < 1e-9,
              f"A = {w.model.sections[sname].A * 1e4:.2f} cm²")
        check("Von Hand geaenderter Querschnitt gilt als frei",
              w.model.sections[sname].typ == "free", w.model.sections[sname].typ)
        w.undo()
        app.processEvents()
        check("Querschnittsaenderung ruecknehmbar",
              abs(w.model.sections[sname].A - A0) < 1e-12)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Tabellen", False, str(ex)[:70])

    # ---- Anschlüsse: Modell, Baum, Tabelle, Nachweis --------------------
    try:
        from PySide6 import QtCore
        from statik3d.joints import anschluss as ans
        from statik3d.joints.templates import propose

        w.load_example("hall")
        r = w.model.members["Riegel"]
        t = propose("kopfplatte", w.model, r.elements[0], end=0,
                    N=-50e3, Vz=150e3, My=300e3)
        name = w._freier_name(t.name, w.model.joints)
        w.merken(f"Anschluss {name}")
        w.model.joints[name] = ans.als_joint(t, name)
        w.refresh_all()
        app.processEvents()
        check("Anschluss steht im Modell, nicht am Fenster",
              name in w.model.joints and not hasattr(w, "joints"), name)
        check("Anschlusstabelle unten gefüllt", w.tbl_joint.zeilenzahl() == 1,
              f"{w.tbl_joint.zeilenzahl()} Zeilen")
        check("vor der Rechnung steht „nicht gerechnet“",
              w.tbl_joint.modell.zeilen[0][-1] == "nicht gerechnet",
              str(w.tbl_joint.modell.zeilen[0][-1]))
        zweige = [w.baum.topLevelItem(0).child(i).text(0)
                  for i in range(w.baum.topLevelItem(0).childCount())]
        check("Anschlüsse stehen im Modellbaum", "Anschlüsse" in zweige, str(zweige[-3:]))
        check("Register „Anschlüsse“ unten vorhanden",
              w.tabelle_zeigen("Anschlüsse"))

        an = solver.solve_all(w.model, design=True, fatigue=True)
        w._solve_done("all", an)
        w.show_results()
        app.processEvents()
        check("Anschluss wird mit der Berechnung nachgewiesen",
              an.joints is not None and name in an.joints.joints)
        z = w.tbl_joint.modell.zeilen[0]
        check("Ausnutzung steht in der Tabelle",
              isinstance(z[5], float) and z[5] > 0 and z[6],
              f"eta = {z[5]:.3f}, {z[6]}")
        check("Ergebnisprotokoll nennt die Anschlüsse",
              "Anschlüsse:" in w.txt_res.toPlainText())

        # Baum -> Tabelle -> Ansicht
        w.clear_selection()
        w._baum_geklickt("anschluss", name)
        app.processEvents()
        check("Klick im Baum wählt den Stab des Anschlusses",
              len(w.selection) == 2, f"{len(w.selection)} Knoten")
        check("und markiert die Zeile",
              len(w.tbl_joint.view.selectionModel().selectedRows()) == 1)
        w.clear_selection()
        w.tbl_joint.zeile_gewaehlt.emit(name)
        app.processEvents()
        check("Klick in der Tabelle wählt den Stab", len(w.selection) == 2)
        w.clear_selection()

        # Momenten-Rotations-Verhalten steht in der Tabelle und in der Rechnung
        g = an.joints.joints[name].gelenk
        check("Steifigkeit des Anschlusses bestimmt", g is not None and g.S_j_ini > 0,
              f"S_j,ini = {g.S_j_ini / 1e6:.1f} MNm/rad" if g else "-")
        check("Klasse und M_j,Rd stehen in der Tabelle",
              w.tbl_joint.modell.zeilen[0][6] in ("starr", "nachgiebig", "gelenkig")
              and float(w.tbl_joint.modell.zeilen[0][7]) > 0,
              f"{w.tbl_joint.modell.zeilen[0][6]}, "
              f"M_j,Rd = {w.tbl_joint.modell.zeilen[0][7]} kNm")
        check("die Tabelle sagt, wie er in der Rechnung sitzt",
              "gerechnet" in str(w.tbl_joint.modell.zeilen[0][8])
              or "Drehfeder" in str(w.tbl_joint.modell.zeilen[0][8]),
              str(w.tbl_joint.modell.zeilen[0][8]))
        w.model.joints[name].modellierung = "feder"
        an = solver.solve_all(w.model, design=True, fatigue=True)
        w._solve_done("all", an)
        w.show_results()
        app.processEvents()
        e0 = w.model.elements[w.model.joints[name].elem]
        check("die Drehfeder sitzt danach am Stabende",
              any(d == DOF for d, _k in e0.hinge_springs for DOF in (4, 10)),
              str(e0.hinge_springs))
        w.model.joints[name].modellierung = "automatisch"

        # Rückgängig und Löschen
        nl = len(w.model.joints)
        w.undo()
        app.processEvents()
        check("Anschluss lässt sich zurücknehmen",
              len(w.model.joints) == nl - 1 and w.tbl_joint.zeilenzahl() == nl - 1)
        w.redo()
        app.processEvents()
        check("und wiederherstellen", len(w.model.joints) == nl)
        w.tbl_joint.view.selectRow(0)
        w.delete_joint()
        app.processEvents()
        check("Anschluss lässt sich löschen", not w.model.joints)
        w.undo()
        check("Löschen ist rücknehmbar", len(w.model.joints) == nl)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Anschlüsse", False, str(ex)[:70])

    # ---- Verformungsnachweise (GZG) -------------------------------------
    try:
        w.load_example("hall")
        m = w.model
        m.add_verformungsgrenze("Durchbiegung Riegel", "stab", stab="Riegel",
                                groesse="uz", grenzart="L/x", wert=300,
                                situation="SLS_CH")
        kopf = int(m.elements[m.members["Stiel links"].elements[-1]].nodes[1])
        m.add_verformungsgrenze("Stielkopf", "knoten", knoten=[kopf], groesse="ux",
                                grenzart="absolut", wert=0.030, situation="SLS_CH")
        w.refresh_all()
        app.processEvents()
        check("Verformungstabelle unten gefüllt", w.tbl_gzg.zeilenzahl() == 2,
              f"{w.tbl_gzg.zeilenzahl()} Zeilen")
        check("vor der Rechnung steht „nicht gerechnet“",
              w.tbl_gzg.modell.zeilen[0][-1] == "nicht gerechnet")
        zweige = [w.baum.topLevelItem(0).child(i).text(0)
                  for i in range(w.baum.topLevelItem(0).childCount())]
        check("Verformungsnachweise stehen im Modellbaum",
              "Verformungsnachweise" in zweige, str(zweige[-2:]))
        check("Register „Verformungen“ unten vorhanden",
              w.tabelle_zeigen("Verformungen"))

        an = solver.solve_all(m, design=True)
        w._solve_done("all", an)
        w.show_results()
        app.processEvents()
        check("Verformungen werden mit gerechnet",
              an.gzg is not None and len(an.gzg.checks) == 2)
        z = w.tbl_gzg.modell.zeilen[0]
        check("Wert, Grenze und Ausnutzung stehen in der Tabelle",
              isinstance(z[4], float) and z[4] > 0 and "L/300" in str(z[5])
              and isinstance(z[6], float),
              f"{z[4]:.2f} mm von {z[5]}, η = {z[6]:.3f}")
        check("Ergebnisprotokoll nennt die Verformungen",
              "Verformungen (GZG)" in w.txt_res.toPlainText())

        w.clear_selection()
        w.tbl_gzg.zeile_gewaehlt.emit("Durchbiegung Riegel")
        app.processEvents()
        check("Klick in der Tabelle wählt den Stab", len(w.selection) > 2,
              f"{len(w.selection)} Knoten")
        w.clear_selection()

        nv = len(m.verformungsgrenzen)
        w.tbl_gzg.view.selectRow(1)
        w.delete_verformungsgrenze()
        app.processEvents()
        check("Verformungsgrenze lässt sich löschen",
              len(m.verformungsgrenzen) == nv - 1)
        w.undo()
        app.processEvents()
        check("und zurücknehmen", len(w.model.verformungsgrenzen) == nv
              and w.tbl_gzg.zeilenzahl() == nv)

        d = dg.VerformungsgrenzeDialog(w, w.model,
                                       w.model.verformungsgrenzen["Stielkopf"])
        name, kw = d.result()
        check("Dialog liest die Grenze zurück",
              name == "Stielkopf" and kw["art"] == "knoten"
              and abs(kw["wert"] - 0.030) < 1e-9, f"{name}, {kw['wert']}")
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Verformungsnachweise", False, str(ex)[:70])

    # ---- Beulfelder (EN 1993-1-5) ---------------------------------------
    try:
        w.load_example("plate")
        m = w.model
        shells = [i for i, e in enumerate(m.elements) if e.typ.startswith("shell")]
        w._set_selection(sorted({int(n) for i in shells for n in m.elements[i].nodes}))
        app.processEvents()
        m.add_beulfeld("Feld 1", shells, beschreibung="ganze Platte als ein Feld")
        w.refresh_all()
        app.processEvents()
        check("Beulfeldtabelle unten gefüllt", w.tbl_beul.zeilenzahl() == 1,
              f"{w.tbl_beul.zeilenzahl()} Zeilen")
        check("Register „Beulfelder“ vorhanden", w.tabelle_zeigen("Beulfelder"))
        zweige = [w.baum.topLevelItem(0).child(i).text(0)
                  for i in range(w.baum.topLevelItem(0).childCount())]
        check("Beulfelder stehen im Modellbaum", "Beulfelder" in zweige, str(zweige[-2:]))

        an = solver.solve_all(m, design=True)
        w._solve_done("all", an)
        w.show_results()
        app.processEvents()
        check("Beulnachweise laufen mit", an.beulen is not None
              and "Feld 1" in an.beulen.felder)
        z = w.tbl_beul.modell.zeilen[0]
        check("Abmessungen und Schlankheit stehen in der Tabelle",
              isinstance(z[2], float) and z[2] > 0 and isinstance(z[8], float),
              f"a = {z[2]:.2f} m, b = {z[3]:.2f} m, λ̄_p = {z[8]:.3f}")
        check("Ergebnisprotokoll nennt das Beulen",
              "Beulen (EN 1993-1-5)" in w.txt_res.toPlainText())
        w.clear_selection()
        w.tbl_beul.zeile_gewaehlt.emit("Feld 1")
        app.processEvents()
        check("Klick in der Tabelle wählt das Feld", len(w.selection) > 3,
              f"{len(w.selection)} Knoten")
        # Steifen und Zylinder über den Dialog
        from statik3d.model import Beulsteife
        d = dg.BeulfeldDialog(w, w.model, w.model.beulfelder["Feld 1"])
        d._zeile("laengs", Beulsteife("laengs", lage=0.6, A_sl=0.001, I_sl=1.2e-6,
                                      I_T=3.3e-9, I_p=8e-6, name="L1"))
        name, kw = d.result()
        check("Dialog liest das Feld zurück",
              name == "Feld 1" and kw["art"] == "eben" and len(kw["steifen"]) == 1,
              f"{name}, {len(kw['steifen'])} Steifen")
        st = kw["steifen"][0]
        check("die Steife kommt in SI zurück",
              abs(st.lage - 0.6) < 1e-9 and abs(st.I_sl - 1.2e-6) < 1e-15,
              f"lage {st.lage}, I_sl {st.I_sl}")
        d.cb_art.setCurrentIndex(1)
        d.ed_r.set(500.0)
        _n, kw2 = d.result()
        check("Zylindermodus liefert Radius in Metern",
              kw2["art"] == "zylinder" and abs(kw2["r"] - 0.5) < 1e-9, str(kw2["r"]))

        # Lasteinleitung
        r_ = w.model.members["Riegel"] if "Riegel" in w.model.members else None
        knoten = 0
        w.model.add_lasteinleitung("LE1", knoten, typ="a", s_s=0.2)
        w.refresh_all()
        app.processEvents()
        check("Tabelle Lasteinleitung gefüllt", w.tbl_le.zeilenzahl() == 1)
        check("Register „Lasteinleitung“ vorhanden", w.tabelle_zeigen("Lasteinleitung"))
        dl = dg.LasteinleitungDialog(w, w.model, w.model.lasteinleitungen["LE1"])
        n2, kw3 = dl.result()
        check("Dialog liest die Stelle zurück",
              n2 == "LE1" and abs(kw3["s_s"] - 0.2) < 1e-9, f"{n2}, s_s = {kw3['s_s']}")
        w.tbl_le.view.selectRow(0)
        w.delete_lasteinleitung()
        check("Lasteinleitung lässt sich löschen", not w.model.lasteinleitungen)
        w.undo()
        check("und zurücknehmen", len(w.model.lasteinleitungen) == 1)

        w.tbl_beul.view.selectRow(0)
        w.delete_beulfeld()
        app.processEvents()
        check("Beulfeld lässt sich löschen", not w.model.beulfelder)
        w.undo()
        check("Löschen ist rücknehmbar", len(w.model.beulfelder) == 1)
        w.clear_selection()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Beulfelder", False, str(ex)[:70])

    # ---- Volumenbereiche (EN 1993-1-1, 6.2.1(5)) ------------------------
    try:
        from statik3d.model import Model, Material
        mv = Model("Volumen")
        mv.add_material(Material.steel("S355"))
        ids = {}
        for k in range(3):
            for j in range(2):
                for i in range(2):
                    ids[(i, j, k)] = mv.add_node(0.1 * i, 0.1 * j, 0.2 * k)
        els = []
        for k in range(2):
            els.append(mv.add_element("hex8", [
                ids[(0, 0, k)], ids[(1, 0, k)], ids[(1, 1, k)], ids[(0, 1, k)],
                ids[(0, 0, k + 1)], ids[(1, 0, k + 1)], ids[(1, 1, k + 1)],
                ids[(0, 1, k + 1)]], "S355"))
        for j in range(2):
            for i in range(2):
                mv.fix(ids[(i, j, 0)], "all")
                mv.load_node(ids[(i, j, 2)], Fz=250e3)
        mv.add_combination("K1", {list(mv.load_cases)[0]: 1.0}, typ="ULS")
        w.model = mv
        w.analysis = None
        w.refresh_all()
        app.processEvents()
        w._set_selection(sorted({int(n) for e in mv.elements for n in e.nodes}))
        app.processEvents()
        # add_volumenbereich() oeffnet einen modalen Dialog - im Test wird der
        # Bereich darum direkt angelegt und der Dialog unten fuer sich geprueft.
        mv.add_volumenbereich("Bereich 1", els, beschreibung="ganzer Körper")
        w.refresh_all()
        app.processEvents()
        check("Volumenbereich angelegt",
              len(mv.volumenbereiche) == 1
              and len(mv.volumenbereiche["Bereich 1"].elemente) == 2,
              str(list(mv.volumenbereiche)))
        check("Register „Volumen“ vorhanden", w.tabelle_zeigen("Volumen"))
        check("Volumentabelle gefüllt", w.tbl_vol.zeilenzahl() == 1,
              f"{w.tbl_vol.zeilenzahl()} Zeilen")
        zweige = [w.baum.topLevelItem(0).child(i).text(0)
                  for i in range(w.baum.topLevelItem(0).childCount())]
        check("Volumenbereiche stehen im Modellbaum",
              "Volumenbereiche" in zweige, str(zweige[-3:]))

        an = solver.solve_all(mv, design=True)
        w._solve_done("all", an)
        w.show_results()
        app.processEvents()
        name = list(mv.volumenbereiche)[0]
        check("Volumennachweise laufen mit",
              an.volumen is not None and name in an.volumen.bereiche)
        z = w.tbl_vol.modell.zeilen[0]
        check("Spannungen stehen in der Tabelle",
              isinstance(z[6], float) and z[6] > 0 and isinstance(z[8], float),
              f"σ_v = {z[6]:.1f} MPa, η = {z[8]:.3f}")
        check("Ergebnisprotokoll nennt die Volumen",
              "Volumen (EN 1993-1-1" in w.txt_res.toPlainText())
        w.clear_selection()
        w.tbl_vol.zeile_gewaehlt.emit(name)
        app.processEvents()
        check("Klick in der Tabelle wählt den Bereich", len(w.selection) >= 8,
              f"{len(w.selection)} Knoten")
        dv = dg.VolumenbereichDialog(w, mv, mv.volumenbereiche[name])
        dv.cb_sing.setChecked(True)
        dv.ed_r.set(5.0)
        n3, kw4 = dv.result()
        check("Dialog liest den Bereich zurück",
              n3 == name and kw4["singular"] is True
              and abs(kw4["ausrundung"] - 0.005) < 1e-9,
              f"{n3}, Kerbradius {kw4['ausrundung'] * 1e3:.1f} mm")
        w.tbl_vol.view.selectRow(0)
        w.delete_volumenbereich()
        check("Volumenbereich lässt sich löschen", not mv.volumenbereiche)
        w.undo()
        check("Löschen ist rücknehmbar", len(w.model.volumenbereiche) == 1)
        w.clear_selection()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Volumenbereiche", False, str(ex)[:70])

    # ---- Ansicht: Knoten, Darstellungsarten, Lagergroesse -----------------
    try:
        from statik3d.gui import viewport as vp
        w.new_model()
        mv = w.model
        mv.add_nodes(np.array([[0, 0, 0], [4, 0, 0], [8, 0, 0], [4, 3, 0.]]))
        mv.add_element("beam", [0, 1], "S235", "IPE 200")
        mv.support(0, [0, 1, 2, 3, 4, 5], name="Einspannung")
        mv.support(1, [0, 1, 2], name="Gelenk")
        w.refresh_all()
        app.processEvents()
        frei = list(vp.unbelegte_knoten(mv))
        check("gesetzte Knoten ohne Element werden erkannt", frei == [2, 3], str(frei))
        check("Knoten werden gezeichnet (Schalter an)", w.act_knoten.isChecked())
        check("Lagersymbol nach Freiheitsgraden",
              [vp.support_shape(x) for x in mv.supports] == ["einspannung", "gelenk"],
              str([vp.support_shape(x) for x in mv.supports]))
        for name in vp.DARSTELLUNGEN:
            w.darstellung_setzen(name)
            app.processEvents()
            check(f"Darstellung „{name}“", w.darstellung == name
                  and w.act_darstellung[name].isChecked())
        check("Drahtmodell zeichnet nur Kanten",
              vp.darstellung("Drahtmodell", True).get("style") == "wireframe")
        check("Transparent ist durchscheinend",
              0 < vp.darstellung("Transparent", True).get("opacity", 1) < 1)
        check("Hidden-Line zeigt Kanten und weisse Flächen",
              vp.darstellung("Hidden-Line", False).get("show_edges") is True
              and vp.darstellung("Hidden-Line", False).get("color") == "#ffffff")
        check("Hidden-Line überschreibt keine Ergebnisfarbe",
              "color" not in vp.darstellung("Hidden-Line", False, True))

        # Kanten gegen die Flaeche, auf der sie liegen: eine Bauteilkante ist
        # zweimal da - als Rand der Flaeche und als Linie -, beide auf
        # demselben Fleck im Tiefenspeicher. Ohne Polygonversatz frisst die
        # Flaeche die Linie stellenweise auf; am Drehlagermodell blieben von
        # den Koerperkanten in der Vollansicht nur 54 % uebrig.
        import vtk as _vtk
        check("die Einstellung „Kanten vor Flächen“ steht", vp.KANTEN_VORN
              and _vtk.vtkMapper.GetResolveCoincidentTopology() != 0,
              str(_vtk.vtkMapper.GetResolveCoincidentTopology()))

        def _kantenprobe():
            """Rotes Liniengitter genau in einer blauen Ebene - wie viele
            Bildpunkte der Linien ueberleben?"""
            import pyvista as _pv
            p_ = _pv.Plotter(off_screen=True, window_size=(500, 500))
            p_.background_color = "white"
            p_.add_mesh(_pv.Plane(center=(0, 0, 0), direction=(0, 0, 1),
                                  i_size=20, j_size=20, i_resolution=40, j_resolution=40),
                        color="#7fb3d5", opacity=1.0, lighting=False, show_edges=False)
            pkt, lin = [], []
            for k_, y_ in enumerate(np.linspace(-9, 9, 19)):
                pkt += [[-9.5, y_, 0.0], [9.5, y_, 0.0]]
                lin += [2, 2 * k_, 2 * k_ + 1]
            p_.add_mesh(_pv.PolyData(np.asarray(pkt, float), lines=np.asarray(lin)),
                        color="#ff0000", line_width=2, lighting=False)
            p_.camera.position = (0, -60, 40); p_.camera.focal_point = (0, 0, 0)
            p_.camera.up = (0, 0, 1)
            p_.renderer.ResetCameraClippingRange(-500, 500, -500, 500, -500, 500)
            b_ = np.asarray(p_.screenshot(return_img=True))[:, :, :3].astype(int)
            p_.close()
            return int(((b_[:, :, 0] > 200) & (b_[:, :, 1] < 80) & (b_[:, :, 2] < 80)).sum())

        _vtk.vtkMapper.SetResolveCoincidentTopologyToDefault()
        _ohne = _kantenprobe()
        vp.kanten_vor_flaechen()
        _mit = _kantenprobe()
        check("und sie holt die verschluckten Kanten zurück", _mit > 2 * _ohne,
              f"{_ohne} → {_mit} Bildpunkte ({_mit / max(1, _ohne):.1f}-fach)")

        w.darstellung_setzen("Voll")
        w.act_edges.setChecked(False)
        app.processEvents()
        check("FE-Netz abschaltbar", vp.darstellung("Voll", w.act_edges.isChecked())
              .get("show_edges") is False)
        w.act_edges.setChecked(True)
        # Lagergroesse: global und je Lager
        w.sl_lager.setValue(25)
        app.processEvents()
        check("Lagergröße global über den Schieber", abs(w.lagergroesse - 2.5) < 1e-9,
              f"{w.lagergroesse}")
        mv.supports[0].groesse = 3.0
        w.redraw()
        i = vp.support_at(mv, mv.nodes[0], mv.characteristic_size(), w.lagergroesse)
        check("Rechtsklick trifft das Lager", i == 0, str(i))
        check("Klick neben dem Lager trifft nichts",
              vp.support_at(mv, mv.nodes[3], mv.characteristic_size(),
                            w.lagergroesse) is None)
        check("Lagergröße wird mitgespeichert",
              Model.from_dict(mv.to_dict()).supports[0].groesse == 3.0)
        w.lagergroesse_zuruecksetzen()
        check("Zurücksetzen stellt die Grundgröße her",
              w.lagergroesse == 1.0 and mv.supports[0].groesse == 1.0)
        # lagergroesse_einstellen() oeffnet eine modale Maske und wird darum
        # hier nicht aufgerufen; geprueft ist der Weg dahinter (Schieber,
        # Support.groesse, Zuruecksetzen).
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Ansicht (Knoten, Darstellung, Lager)", False, str(ex)[:70])

    # ---- Modellbaum und Modelltabellen ------------------------------------
    try:
        from statik3d.model import MemberHinge
        w.load_example("hall")
        mb = w.model
        mb.add_line("L1", [0, 1, 2])
        mb.hinges["G1"] = MemberHinge("G1", 0, ["fixed"] * 4 + ["free", "free"], [0.0] * 6)
        w.refresh_all()
        app.processEvents()

        def zweige(baum):
            namen = []

            def lauf(it):
                namen.append(it.text(0))
                for i in range(it.childCount()):
                    lauf(it.child(i))
            for i in range(baum.topLevelItemCount()):
                lauf(baum.topLevelItem(i))
            return namen

        namen = zweige(w.baum)
        for zweig in ("Knoten", "Linien", "Stäbe", "Stäbe mit Nachweis", "Flächen",
                      "Volumen", "Eigenschaften", "Querschnitte", "Werkstoffe", "Dicken",
                      "Lager", "Knotenlager", "Gelenke", "Einwirkungen",
                      "Lastfälle", "Kombinationen"):
            check(f"Modellbaum: Zweig „{zweig}“", zweig in namen)

        register = [w.tab_unten.tabText(i) for i in range(w.tab_unten.count())]
        for reg in ("Knoten", "Linien", "Stäbe", "Lager", "Gelenke",
                    "Lastfälle", "Kombinationen"):
            check(f"Tabelle unten: „{reg}“", reg in register)
        check("Knotentabelle gefüllt", len(w.tbl_knoten.modell.zeilen) == mb.nn,
              f"{len(w.tbl_knoten.modell.zeilen)} von {mb.nn}")
        check("Elementtabelle gefüllt",
              len(w.tbl_elem.modell.zeilen) == len(mb.elements))
        check("Lagertabelle gefüllt", len(w.tbl_lager.modell.zeilen) == len(mb.supports))
        check("Linientabelle gefüllt", len(w.tbl_linie.modell.zeilen) == 1)
        check("Gelenktabelle gefüllt", len(w.tbl_gelenk.modell.zeilen) == 1,
              str(w.tbl_gelenk.modell.zeilen))
        check("Lastfalltabelle gefüllt",
              len(w.tbl_lastfall.modell.zeilen) == len(mb.load_cases))
        check("Kombinationstabelle gefüllt",
              len(w.tbl_kombi.modell.zeilen) == len(mb.combinations))
        check("Knoten ohne Element wird in der Tabelle als 0 geführt",
              all(isinstance(z[4], int) for z in w.tbl_knoten.modell.zeilen))

        # Editieren in den Tabellen
        x0 = float(mb.nodes[0][0])
        check("Knotenkoordinate editierbar", w._knoten_aendern(0, 1, x0 + 0.25)
              and abs(float(mb.nodes[0][0]) - (x0 + 0.25)) < 1e-9,
              f"x = {float(mb.nodes[0][0]):.3f}")
        w.undo()
        check("Änderung in der Tabelle ist rücknehmbar",
              abs(float(w.model.nodes[0][0]) - x0) < 1e-9)
        mb = w.model
        check("Elementdrehung editierbar", w._elem_aendern(0, 5, 30.0)
              and abs(np.degrees(mb.elements[0].roll) - 30.0) < 1e-6)
        check("unbekannter Werkstoff wird abgewiesen",
              not w._elem_aendern(0, 3, "GibtEsNicht"))
        check("Lagername editierbar", w._lager_aendern(0, 2, "Fußpunkt links")
              and mb.supports[0].name == "Fußpunkt links")
        check("Symbolgröße in der Tabelle editierbar",
              w._lager_aendern(0, 6, 2.5) and mb.supports[0].groesse == 2.5)
        # Die Tabelle ist nach der ersten Spalte sortiert - Zeile 0 ist der
        # Lastfall mit dem ersten Namen, nicht der zuerst angelegte
        lf0 = str(w.tbl_lastfall.modell.zeilen[0][0])
        check("Lastfallnummer in der Tabelle editierbar",
              w._lastfall_aendern(0, 1, 7) and mb.load_cases[lf0].nummer == 7,
              f"{lf0}: {mb.load_cases[lf0].nummer}")
        check("Lastfallbeschreibung editierbar",
              w._lastfall_aendern(0, 3, "Eigenlast Dach")
              and mb.load_cases[lf0].description == "Eigenlast Dach")

        # Modellbaum: Klick waehlt aus, Doppelklick oeffnet
        w._baum_geklickt("stabelemente", "beam")
        check("Klick auf „Stäbe“ wählt die Stabknoten", len(w.selection) > 0,
              f"{len(w.selection)} Knoten")
        w._baum_geklickt("lager_einzeln", "0")
        check("Klick auf ein Lager wählt seinen Knoten",
              list(w.selection) == [int(mb.supports[0].node)], str(w.selection))
        w._baum_geklickt("linie", "L1")
        check("Klick auf die Linie wählt die Linie", w.sel_linien == ["L1"]
              and w.auswahlart == "Linie", str(w.sel_linien))
        w.clear_selection()

        # Bearbeitungsmasken lassen sich bauen und lesen die Werte zurueck
        from statik3d.gui import dialogs as dgl
        d = dgl.KnotenDialog(w, mb.nodes[3], 3)
        check("Knotenmaske liest die Koordinaten",
              np.allclose(d.werte(), mb.nodes[3]), str(d.werte()))
        d = dgl.LinienDialog(w, mb.lines["L1"], mb.nn)
        check("Linienmaske liest die Linie zurück",
              d.werte()["nodes"] == [0, 1, 2] and d.werte()["name"] == "L1",
              str(d.werte()))
        d = dgl.DickeDialog(w, list(mb.shells.values())[0])
        check("Dickenmaske liest die Dicke zurück",
              abs(d.werte()[1] - list(mb.shells.values())[0].t) < 1e-12)
        d = dgl.GelenkDialog(w, mb.hinges["G1"])
        check("Gelenkmaske liest die Freigaben zurück",
              d.werte()["typ"] == ["fixed"] * 4 + ["free", "free"], str(d.werte()["typ"]))
        d = dgl.SupportNonlinearDialog(w, mb.supports[0], "Knotenlager", stammdaten=True)
        check("Lagermaske zeigt Name und Symbolgröße",
              d.name_ed.text() == "Fußpunkt links" and abs(d.groesse_ed.value() - 2.5) < 1e-9)
        d.name_ed.setText("Fußpunkt A")
        d.groesse_ed.set(1.4)
        d.apply(mb.supports[0])
        check("Lagermaske schreibt Name und Symbolgröße zurück",
              mb.supports[0].name == "Fußpunkt A" and abs(mb.supports[0].groesse - 1.4) < 1e-9)
        d = dgl.SectionDialog(w, mb.sections["HEB 300"])
        check("Querschnittsmaske findet das Profil in der Datenbank",
              d.tabs.currentIndex() == 0 and d.profile.currentText() == "HEB 300",
              d.profile.currentText())
        from statik3d.model import Section
        d = dgl.SectionDialog(w, Section.rectangle("R", 0.3, 0.5))
        check("Querschnittsmaske fällt bei freien Querschnitten auf „Parametrisch“",
              d.tabs.currentIndex() == 1 and abs(d.p[1].value() - 0.5) < 1e-9,
              f"{d.tabs.currentIndex()}, h = {d.p[1].value()}")

        # Loeschen in den Tabellen
        n_el = len(mb.elements)
        w.tbl_elem.view.selectRow(0)
        w.element_loeschen()
        check("Element aus der Tabelle löschbar", len(w.model.elements) == n_el - 1,
              f"{len(w.model.elements)} statt {n_el}")
        w.undo()
        check("Löschen ist rücknehmbar", len(w.model.elements) == n_el)
        w.new_model()
        w.model.add_nodes(np.array([[0, 0, 0], [1, 0, 0.]]))
        w.refresh_all()
        w.tbl_knoten.view.selectRow(1)
        w.knoten_loeschen()
        check("freier Knoten löschbar", w.model.nn == 1, f"{w.model.nn}")

        # Kontaktbedingungen: Modellobjekt, Baumzweig, Tabelle
        from statik3d.model import DofBehaviour
        w.model.add_kontaktbedingung(
            "Lagerbock-Grundplatte", flaechen=[1, 2, 3], volumen=[1], ziele=5,
            typ="4", behaviour={0: DofBehaviour("rigid"), 1: DofBehaviour("rigid"),
                                2: DofBehaviour("free", failure="zug")})
        w.refresh_all()
        app.processEvents()
        check("Kontaktbedingungen stehen im Modellbaum",
              "Kontaktbedingungen" in zweige(w.baum) and "Flächenkontakte" in zweige(w.baum))
        check("Register „Kontaktbedingungen“ vorhanden",
              "Kontaktbedingungen" in [w.tab_unten.tabText(i)
                                     for i in range(w.tab_unten.count())])
        z = w.tbl_freigabe.modell.zeilen
        check("Tabelle der Kontaktbedingungen gefüllt", len(z) == 1, str(z))
        check("Wirkung je Freiheitsgrad in der Tabelle",
              "uz=frei (Ausfall bei Zug)" in str(z[0][6]), str(z[0][6]))
        check("nicht ausgeführte Trennung wird als „nein“ geführt",
              z[0][7] == "nein", str(z[0][7]))
        fr = Model.from_dict(w.model.to_dict()).kontaktbedingungen["Lagerbock-Grundplatte"]
        check("Kontaktbedingung überlebt Speichern und Laden",
              fr.flaechen == [1, 2, 3] and fr.dof_behaviour(2).failure == "zug",
              fr.describe())
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Modellbaum und Modelltabellen", False, str(ex)[:70])

    # ---- Geometriekette und Objektauswahl in der Ansicht -------------------
    try:
        from statik3d.gui import viewport as vpg
        w.new_model()
        w.error = lambda msg: check("Geometrie: unerwarteter Fehler", False, str(msg)[:60])
        mg = w.model
        mg.netz.teilung_uebersteuern = False     # die Teilung der Flächen gilt hier
        mg.add_nodes(np.array([[0, 0, 0], [4, 0, 0], [4, 2, 0], [0, 2, 0.]]))
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            mg.add_line(f"L{i + 1}", [a, b])
        w.refresh_all()
        app.processEvents()
        # Auswahlart umschalten und Linien in der Ansicht anklicken
        w.auswahlart_setzen("Linie")
        check("Auswahlart umschaltbar", w.auswahlart == "Linie"
              and w.cb_auswahlart.currentText() == "Linie")
        check("Linie unter dem Zeiger gefunden",
              vpg.line_at(mg, [2.0, 0.0, 0.0], mg.characteristic_size()) == "L1")
        # Intelligente Auswahl (Vorgabe: an): ein Klick auf eine Linie des
        # geschlossenen Rands holt den ganzen Ring, der naechste nimmt ihn weg.
        # Der Klick sucht zuerst die Linie unter dem **echten** Zeiger; steht
        # der zufaellig ueber der Ansicht, traefe er eine andere Linie als der
        # uebergebene Punkt (Lauf 30: vier Klicks, [] statt vier Linien). Hier
        # zaehlt allein der Punkt.
        _linie_alt = w._linie_am_zeiger
        w._linie_am_zeiger = lambda: None
        w._picked([2.0, 0, 0])
        check("ein Klick wählt den geschlossenen Rand (intelligente Auswahl): vier Linien",
              sorted(w.sel_linien) == ["L1", "L2", "L3", "L4"], str(w.sel_linien))
        w._picked([2.0, 0.0, 0.0])
        check("nochmaliger Klick nimmt den ganzen Zug wieder heraus",
              not w.sel_linien, str(w.sel_linien))
        w.act_klug.setChecked(False)
        for punkt in ([2.0, 0, 0], [4.0, 1.0, 0], [2.0, 2.0, 0], [0, 1.0, 0]):
            w._picked(punkt)
        check("Schalter aus: vier Klicks, vier Linien", w.sel_linien == ["L1", "L2", "L3", "L4"],
              str(w.sel_linien))
        w._picked([2.0, 0.0, 0.0])
        check("Schalter aus: nochmaliger Klick nimmt nur die eine Linie heraus",
              "L1" not in w.sel_linien and len(w.sel_linien) == 3, str(w.sel_linien))
        w._picked([2.0, 0.0, 0.0])
        w.act_klug.setChecked(True)
        w._linie_am_zeiger = _linie_alt

        f = mg.add_flaeche("F1", w.sel_linien, dicke=list(mg.shells)[0],
                           material=list(mg.materials)[0], teilung=[8, 4])
        n = w._vernetzen([f], [])
        w.refresh_all()
        app.processEvents()
        check("Fläche aus Linien vernetzt", n == 32 and len(mg.elements) == 32,
              f"{n} Elemente")
        check("Flächen stehen im Modellbaum", "Flächen" in zweige(w.baum))
        check("Register „Flächen“ vorhanden",
              "Flächen" in [w.tab_unten.tabText(i) for i in range(w.tab_unten.count())])
        z = w.tbl_geoflaeche.modell.zeilen
        check("Flächentabelle gefüllt", len(z) == 1 and z[0][5] == 32, str(z[0][:6]))
        check("Flächeninhalt in der Tabelle", abs(z[0][6] - 8.0) < 1e-9, str(z[0][6]))

        # ---- Mouseover: das Objekt der gewählten Auswahlart leuchtet -------
        # Der Zeiger soll zeigen, was ein Klick treffen würde - und die Nummer
        # daneben stellen. Aufgelöst wird über dieselben Helfer wie beim Klick;
        # hier werden sie gesetzt, damit der Test ohne echte Maus auskommt.
        from PySide6 import QtCore as _Qc

        def akteure():
            return list(dict(w.plotter.renderer.actors))

        w.auswahlart_setzen("Fläche")
        w._hover_pos = _Qc.QPoint(40, 40)
        w._objekt_am_zeiger = lambda art: "F1" if art == "Fläche" else None
        treffer = w._hover_am_zeiger()
        check("Mouseover findet die Fläche unter dem Zeiger",
              treffer is not None and treffer[0] == ("Fläche", "F1"), str(treffer))
        check("die Beschriftung nennt Art und Nummer",
              treffer is not None and treffer[1] == "Fläche F1", str(treffer and treffer[1]))
        w._hover_suchen()
        app.processEvents()
        check("die Fläche leuchtet unter dem Zeiger auf", "hover" in akteure(), str(akteure()))
        check("die Nummer steht als Schild am Zeiger",
              w._hover_schild is not None and w._hover_schild.isVisible()
              and w._hover_schild.text() == "Fläche F1",
              w._hover_schild.text() if w._hover_schild else "kein Schild")
        # Das Schild folgt dem Zeiger und bleibt im Fenster
        check("das Schild steht neben dem Zeiger",
              w._hover_schild.x() >= 0 and w._hover_schild.y() >= 0,
              f"({w._hover_schild.x()}, {w._hover_schild.y()})")

        # Nichts mehr getroffen: Hervorhebung und Schild verschwinden
        w._objekt_am_zeiger = lambda art: None
        w._hover_suchen()
        app.processEvents()
        check("ohne Treffer erlischt die Hervorhebung", "hover" not in akteure(), str(akteure()))
        check("ohne Treffer verschwindet das Schild", not w._hover_schild.isVisible())

        # Ein Wechsel der Auswahlart räumt die alte Hervorhebung ab
        w._objekt_am_zeiger = lambda art: "F1" if art == "Fläche" else None
        w._hover_suchen()
        app.processEvents()
        check("wieder aufgeleuchtet", "hover" in akteure())
        w.auswahlart_setzen("Knoten")
        app.processEvents()
        check("Wechsel der Auswahlart räumt die Hervorhebung ab",
              "hover" not in akteure() and w._hover_stand is None, str(akteure()))

        # Auswahlart Netz: die Elementnummer steht am Zeiger
        w.auswahlart_setzen("Netz")
        w._element_am_zeiger = lambda: 3
        w._wenn_sichtbar = lambda art, name: name
        treffer = w._hover_am_zeiger()
        check("Mouseover nennt die Elementnummer",
              treffer is not None and treffer[1] == "Element 3", str(treffer))
        w._hover_suchen()
        app.processEvents()
        check("das Element leuchtet auf", "hover" in akteure())
        w._hover_aus()
        app.processEvents()
        check("_hover_aus räumt beides ab",
              "hover" not in akteure() and not w._hover_schild.isVisible())
        # Während des Drehens wird nicht gesucht - das ruckelte sonst
        w._vereinfacht = True
        check("beim Drehen ruht die Suche", not w._hover_bereit())
        w._vereinfacht = None
        del w._objekt_am_zeiger, w._element_am_zeiger, w._wenn_sichtbar
        w.auswahlart_setzen("Linie")
        w.auswahlart_setzen("Fläche")
        check("Fläche unter dem Zeiger gefunden",
              vpg.flaeche_at(mg, [2.0, 1.0, 0.0], mg.characteristic_size()) == "F1")
        w.netz_loeschen_geometrie()
        check("Netz löschbar, Geometrie bleibt",
              not mg.elements and not mg.flaechen["F1"].elemente and mg.lines)
        w.undo()
        check("Netz löschen ist rücknehmbar", len(w.model.elements) == 32)

        # Volumenkörper aus sechs Flächen
        w.new_model()
        mv2 = w.model
        P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
                      [0, 0, 1], [2, 0, 1], [2, 1, 1], [0, 1, 1.]])
        mv2.add_nodes(P)
        kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                  (0, 4), (1, 5), (2, 6), (3, 7)]
        for i, (a, b) in enumerate(kanten):
            mv2.add_line(f"K{i + 1}", [a, b])
        seiten = {"Boden": ["K1", "K2", "K3", "K4"], "Deckel": ["K5", "K6", "K7", "K8"],
                  "S1": ["K1", "K10", "K5", "K9"], "S2": ["K2", "K11", "K6", "K10"],
                  "S3": ["K3", "K12", "K7", "K11"], "S4": ["K4", "K9", "K8", "K12"]}
        for nme, ls in seiten.items():
            mv2.add_flaeche(nme, ls, material=list(mv2.materials)[0])
        kk = mv2.add_koerper("V1", list(seiten), material=list(mv2.materials)[0],
                             teilung=[4, 2, 2])
        n = w._vernetzen([], [kk])
        w.refresh_all()
        app.processEvents()
        check("Volumen aus Flächen vernetzt", n == 16, f"{n} Elemente")
        check("Volumen stehen im Modellbaum", "Volumen" in zweige(w.baum))
        zv = w.tbl_geokoerper.modell.zeilen
        check("Volumentabelle nennt das Volumen", abs(zv[0][5] - 2.0) < 1e-9, str(zv[0][5]))
        w.auswahlart_setzen("Volumen")
        check("Volumenkörper unter dem Zeiger gefunden",
              vpg.koerper_at(mv2, [1.0, 0.5, 0.5], mv2.characteristic_size()) == "V1")
        # Masken lesen die Objekte zurück
        from statik3d.gui import dialogs as dgg
        d = dgg.FlaechenDialog(w, mv2, flaeche=mv2.flaechen["Boden"])
        check("Flächenmaske liest die Randlinien zurück",
              sorted(d.werte()["linien"]) == ["K1", "K2", "K3", "K4"],
              str(d.werte()["linien"]))
        d = dgg.KoerperDialog(w, mv2, koerper=kk)
        check("Volumenmaske liest die Randflächen zurück",
              len(d.werte()["flaechen"]) == 6 and d.werte()["teilung"] == [4, 2, 2],
              str(d.werte()["teilung"]))

        # Kerbfall des Volumens: Maske, Tabelle, Dialog, Vorschlag - und der
        # Ermuedungsnachweis am Volumen (Hauptspannung im Element) samt
        # Tabelle Ermuedung, Faerbung und Auswahl per Klick (11.09.2026)
        w._objektmaske("geokoerper_einzeln", "V1"); app.processEvents()
        mk = w.maskenrand.maske
        check("Volumenmaske hat die Felder Kerbfall und Kerbfall Naht",
              mk is not None and "kerbfall" in mk._felder and "kerbfall_naht" in mk._felder,
              str(sorted(mk._felder)) if mk else "-")
        if mk is not None and "kerbfall" in mk._felder:
            mk.setzen("kerbfall", "71")
            mk.anwenden(); app.processEvents()
        kk = mv2.koerper["V1"]
        check("Kerbfall 71 N/mm² im Volumen, keine Vorschlagsmarke",
              abs(float(kk.kerbfall) - 71e6) < 1.0 and not kk.kerbfall_vorschlag, str(kk.kerbfall))
        w.refresh_all(); app.processEvents()
        spalten = [s.name for s in w.tbl_geokoerper.modell.spalten]
        zv = w.tbl_geokoerper.modell.zeilen
        check("Volumentabelle: Spalte Kerbfall mit 71", "Kerbfall" in spalten
              and abs(float(zv[0][spalten.index("Kerbfall")]) - 71.0) < 1e-9, str(zv[0]))
        d = dgg.KoerperDialog(w, mv2, koerper=kk)
        check("Volumendialog liest den Kerbfall",
              abs(float(d.werte().get("kerbfall", 0.0)) - 71e6) < 1.0, str(d.werte().get("kerbfall")))
        check("„Kerbfälle vorschlagen“ steht im Menüband",
              any(b.text == "Kerbfälle vorschlagen" for b in w.ribbon.befehle))
        kk.kerbfall = 0.0
        w.do_kerbfaelle(); app.processEvents()
        check("Vorschlag für das Volumen: 160 N/mm² Grundwerkstoff, Naht 90, markiert",
              abs(float(kk.kerbfall) - 160e6) < 1.0 and abs(float(kk.kerbfall_naht) - 90e6) < 1.0
              and kk.kerbfall_vorschlag, f"{kk.kerbfall} / {kk.kerbfall_naht}")
        spalten = [s.name for s in w.tbl_geokoerper.modell.spalten]
        check("Volumentabelle hat die Spalte Kerbfall Naht", "Kerbfall Naht" in spalten, str(spalten))
        kk.kerbfall = 71e6
        kk.kerbfall_vorschlag = False
        for nid in range(mv2.nn):
            if mv2.nodes[nid, 2] < 1e-9:
                mv2.fix(nid, [0, 1, 2])
        oben = [nid for nid in range(mv2.nn) if mv2.nodes[nid, 2] > 1.0 - 1e-9]
        mv2.case().category = "G"
        for nid in oben:
            mv2.load_node(nid, Fz=-20000.0)
        mv2.add_load_case("LF2", "Q")
        for nid in oben:
            mv2.load_node(nid, Fz=-5000.0)
        from statik3d.model import FatigueLoad as _FL
        mv2.fatigue_loads["Zyklus"] = _FL("Zyklus", folge=[list(mv2.load_cases)[0], "LF2"],
                                          wiederholungen=1e5)
        an_v = solver.solve_all(mv2, fatigue=True)
        w._solve_done("all", an_v); app.processEvents()
        fv = an_v.fatigue.volumen.get("V1") if an_v.fatigue is not None else None
        check("Ermüdung am Volumen gerechnet (16 Elemente, Kerbfall 71)",
              fv is not None and fv.n_elemente == 16 and fv.dsig_max > 0,
              str(fv.dsig_max if fv else None))
        zf = w.tbl_fat.modell.zeilen
        check("Tabelle Ermüdung führt das Volumen", any(str(z[0]) == "Volumen V1" for z in zf),
              str([z[0] for z in zf]))
        um = w._util_map("Ausnutzung Ermüdung")
        check("Färbung „Ausnutzung Ermüdung“ hat Werte für die 16 Volumenelemente",
              um is not None and len(um) == 16, str(len(um) if um else None))
        w._tabelle_stab("Volumen V1"); app.processEvents()
        check("Klick auf die Volumenzeile wählt die Knoten des Körpers",
              len(w.selection) == mv2.nn, f"{len(w.selection)} von {mv2.nn}")
        mv2.fatigue_loads.clear()

        # Listenfeld der Objektmaske: ein einzeiliges Feld stand bisher am
        # Zeilenende, und aus dreizehn Randflaechen las man "9, F64, ...".
        # Jetzt steht die Anzahl in der Beschriftung, der Zeiger zeigt die
        # ganze Liste, und der Textanfang ist sichtbar.
        w._objektmaske("geokoerper_einzeln", "V1"); app.processEvents()
        mk = w.maskenrand.maske if hasattr(w, "maskenrand") else None
        feld = mk._felder.get("flaechen") if mk is not None else None
        check("die Volumenmaske hat ein Listenfeld für die Randflächen",
              feld is not None and "flaechen" in (mk._listen if mk else {}),
              str(sorted((mk._listen or {}).keys())) if mk else "keine Maske")
        if feld is not None:
            lb, _t, _h = mk._listen["flaechen"]
            check("die Beschriftung nennt die Anzahl", "(6)" in lb.text(), lb.text())
            check("der Zeiger zeigt alle sechs Namen",
                  all(nm in feld.toolTip() for nm in seiten), feld.toolTip()[:80])
            check("und das Feld steht am Anfang, nicht am Zeilenende",
                  feld.cursorPosition() == 0, str(feld.cursorPosition()))
            mk.setzen("flaechen", ", ".join(list(seiten)[:3]))
            check("nach dem Anklicken in der Ansicht zählt die Beschriftung mit",
                  "(3)" in lb.text() and feld.cursorPosition() == 0, lb.text())
        w.maskenrand.schliessen()
        app.processEvents()

        # Schnittebene: von einem Volumennetz wird nur die Aussenhaut
        # gezeichnet - wer hineinsehen will, muss aufschneiden. Gemessen wird
        # der Huellquader des gezeichneten Gitters laengs der Schnittachse.
        typen_v, ausser_v = tuple(vpg.TYPEN_VOLUMEN), set()
        g0, _k0 = w._gitter(typen_v, ausser_v)
        b0 = list(g0.bounds)
        w.cb_schnittachse.setCurrentText("x")
        w.sl_schnitt.setValue(50)
        w.act_schnitt.setChecked(True); app.processEvents()
        check("die Schnittebene ist eingeschaltet", w.schnitt is not None, str(w.schnitt))
        g1, _k1 = w._gitter(typen_v, ausser_v)
        b1 = list(g1.bounds)
        check("der Schnitt nimmt längs x die halbe Ausdehnung weg",
              abs((b1[1] - b1[0]) - 0.5 * (b0[1] - b0[0])) < 0.06 * (b0[1] - b0[0]),
              f"{b1[1] - b1[0]:.3f} statt {b0[1] - b0[0]:.3f} m")
        check("quer dazu bleibt das Bauteil ganz",
              abs((b1[3] - b1[2]) - (b0[3] - b0[2])) < 1e-9,
              f"{b1[3] - b1[2]:.3f} / {b0[3] - b0[2]:.3f} m")
        w.act_schnittseite.setChecked(True); app.processEvents()
        g2, _k2 = w._gitter(typen_v, ausser_v)
        check("die andere Seite lässt die andere Hälfte stehen",
              abs(g2.bounds[0] - b1[0]) > 0.1 * (b0[1] - b0[0]),
              f"x von {g2.bounds[0]:.3f} statt {b1[0]:.3f} m")
        w.act_schnitt.setChecked(False)
        w.act_schnittseite.setChecked(False); app.processEvents()
        g3, _k3 = w._gitter(typen_v, ausser_v)
        # freie Schnittebene: schraeg durch die Mitte (viewport), dann ueber
        # Ribbon und Maske, aus der Ansicht, und als Werkzeug im Bild
        b0c = np.array([(b0[0] + b0[1]) / 2, (b0[2] + b0[3]) / 2, (b0[4] + b0[5]) / 2])
        n_frei = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)
        gs = vpg.schneiden(g0, "frei", 0.5, False, n_frei, b0c)
        mitten = gs.cell_centers().points if gs.n_cells else np.zeros((0, 3))
        check("viewport.schneiden „frei“: schräge Ebene durch die Mitte, es bleibt die Seite gegen die Normale",
              0 < gs.n_cells < g0.n_cells
              and float(((mitten - b0c) @ n_frei).max()) < 1e-6 * (b0[1] - b0[0]) + 1e-9,
              f"{gs.n_cells} von {g0.n_cells}")
        w.cb_schnittachse.setCurrentText("frei"); app.processEvents()
        mk = w.maskenrand.maske
        check("Achse „frei“ öffnet rechts die Maske „Schnittebene“",
              mk is not None and getattr(mk, "titel", "") == "Schnittebene", str(getattr(mk, "titel", None)))
        if mk is not None:
            for k, v in (("nx", "1"), ("ny", "1"), ("nz", "0"), ("ox", f"{b0c[0]:.4f}"),
                         ("oy", f"{b0c[1]:.4f}"), ("oz", f"{b0c[2]:.4f}")):
                mk.setzen(k, v)
            mk.anwenden(); app.processEvents()
        check("„Schneiden“: Schnitt frei mit normierter Normale durch den Ursprung, Schalter an",
              w.schnitt is not None and w.schnitt[0] == "frei" and np.allclose(w.schnitt[3], n_frei)
              and np.allclose(w.schnitt[4], b0c, atol=1e-3) and w.act_schnitt.isChecked(), str(w.schnitt))
        g4, _k4 = w._gitter(typen_v, ausser_v)
        check("… und die Ansicht ist schräg aufgeschnitten", 0 < g4.n_cells < g3.n_cells,
              f"{g4.n_cells} von {g3.n_cells}")
        if w.maskenrand.maske is mk and mk is not None:
            mk.setzen("quelle", "aus der Ansicht (senkrecht zum Blick, durch den Blickpunkt)")
            mk.anwenden(); app.processEvents()
        blick = np.asarray(w.plotter.renderer.GetActiveCamera().GetDirectionOfProjection(), float)
        check("„aus der Ansicht“: die Ebene liegt senkrecht zum Blick",
              w.schnitt is not None and np.allclose(w.schnitt[3], blick, atol=1e-6),
              str(w.schnitt[3] if w.schnitt else None))
        if w.maskenrand.maske is mk and mk is not None:
            mk.setzen("widget", True); mk.anwenden(); app.processEvents()
        n_wz = len(getattr(w.plotter, "plane_widgets", []) or [])
        check("„Ebene im Bild ziehen“ legt das Ebenen-Werkzeug an",
              n_wz == 1 and getattr(w, "_schnittwidget", None) is not None, str(n_wz))
        w._schnittwidget_bewegt((0.0, 0.0, 1.0), b0c + np.array([0.0, 0.0, 0.01])); app.processEvents()
        check("Ziehen der Ebene übernimmt Normale und Ursprung in den Schnitt",
              w.schnitt is not None and np.allclose(w.schnitt[3], (0.0, 0.0, 1.0))
              and abs(w.schnitt[4][2] - (b0c[2] + 0.01)) < 1e-9, str(w.schnitt))
        w.act_schnitt.setChecked(False); app.processEvents()
        check("Schnitt aus: das Werkzeug ist weg",
              not getattr(w.plotter, "plane_widgets", []) and getattr(w, "_schnittwidget", None) is None)
        w.maskenrand.schliessen()
        w.cb_schnittachse.setCurrentText("y"); app.processEvents()
        g3, _k3 = w._gitter(typen_v, ausser_v)
        check("ausgeschaltet steht das Bauteil wieder ganz da",
              abs(g3.bounds[1] - g3.bounds[0] - (b0[1] - b0[0])) < 1e-9,
              f"{g3.bounds[1] - g3.bounds[0]:.3f} / {b0[1] - b0[0]:.3f} m")
        # Eine berandende Fläche darf nicht einfach weg
        gemeldet = []
        w.error = lambda msg: gemeldet.append(str(msg))
        w.tbl_geoflaeche.view.selectRow(0)
        w._geometrie_loeschen(w.tbl_geoflaeche, mv2.flaechen)
        check("berandende Fläche wird nicht gelöscht",
              len(mv2.flaechen) == 6 and gemeldet
              and "Volumenkörper" in gemeldet[-1], gemeldet[-1] if gemeldet else "-")
        w.tbl_geokoerper.view.selectRow(0)
        w._geometrie_loeschen(w.tbl_geokoerper, mv2.koerper)
        check("Volumenkörper mit seinem Netz löschbar",
              not mv2.koerper and not w.model.elements)
        w.clear_selection()
        check("Auswahl aufheben leert auch die Objektauswahl",
              not w.sel_linien and not w.sel_flaechen and not w.sel_koerper)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Geometriekette", False, str(ex)[:70])

    # ---- Traege Grafik (12.09.2026): Knotenpruefung einmal je Netz, grosse
    # Tabellen erst beim Anzeigen, unverformtes System als Umriss ohne Netz
    try:
        from statik3d.gui import viewport as vpt
        from statik3d.gui import tabellen as tabt
        w.load_example("friction"); app.processEvents()
        mv = w.model
        f1 = vpt.unbelegte_knoten(mv)
        f2 = vpt.unbelegte_knoten(mv)
        getragen = set()
        for e in mv.elements:
            getragen.update(int(n) for n in e.nodes)
        check("unbelegte Knoten: einmal je Netz (Zwischenspeicher), gleich der Schleife",
              f1 is f2 and list(f1) == [n for n in range(mv.nn) if n not in getragen])
        mv.add_node(9.0, 9.0, 9.0)
        f3 = vpt.unbelegte_knoten(mv)
        check("… ein neuer Knoten ohne Element erneuert den Speicher", f3 is not f1 and int(f3[-1]) == mv.nn - 1)
        an = solver.solve_all(mv, combinations=False); w._solve_done("all", an); app.processEvents()
        w._baum_geklickt("ergebnis", f"case:{list(mv.load_cases)[0]}"); app.processEvents()
        w.cb_undeformed.setChecked(True); w.act_edges.setChecked(True); w.redraw(); app.processEvents()
        n_netz = w.plotter.renderer.actors["undeformed_netz"].mapper.dataset.n_cells
        w.act_edges.setChecked(False); w.redraw(); app.processEvents()
        u = w.plotter.renderer.actors.get("undeformed_netz")
        n_umriss = u.mapper.dataset.n_cells if u is not None else -1
        check("Netz aus: das unverformte System ist nur noch ein Umriss (weniger Zellen, Linien)",
              0 < n_umriss < n_netz and u.mapper.dataset.n_lines == n_umriss, f"{n_umriss} statt {n_netz}")
        w.act_edges.setChecked(True); w.redraw(); app.processEvents()
        # grosse Tabelle: verzoegert, solange sie nicht zu sehen ist
        alt_grenze = tabt.Datentabelle.VERZOEGERT_AB
        tabt.Datentabelle.VERZOEGERT_AB = 10
        try:
            w.tabelle_zeigen("Knoten"); app.processEvents()
            w.tbl_elem.setzen([[i, "hex8", 0, "S355", "-", 0.0] for i in range(40)])
            check("Tabelle hinten: 40 Zeilen (> Grenze) bleiben ausstehend, die Zeilenzahl sagt es",
                  w.tbl_elem.ausstehend() and "beim Anzeigen" in w.tbl_elem.lbl_zeilen.text()
                  and w.tbl_elem.modell.rowCount() != 40, w.tbl_elem.lbl_zeilen.text())
            w.tabelle_zeigen("Stäbe"); app.processEvents(); app.processEvents()
            check("… beim Anzeigen wird sie gefuellt", not w.tbl_elem.ausstehend()
                  and w.tbl_elem.modell.rowCount() == 40, str(w.tbl_elem.modell.rowCount()))
        finally:
            tabt.Datentabelle.VERZOEGERT_AB = alt_grenze
        w.refresh_all(); app.processEvents()
    except Exception as ex:
        import traceback
        traceback.print_exc()
        check("Traege Grafik", False, str(ex)[:80])

    # ---- Ergebnisse neben der Modelldatei (12.09.2026) -----------------------
    try:
        _alt_error = w.error
        w.error = lambda msg: check("Ergebnisdatei: unerwarteter Fehler (Dialog)", False, str(msg)[:90])
        import tempfile as _tf2
        from statik3d import ergebnisse as _erg
        w.load_example("frame"); app.processEvents()
        an = solver.solve_all(w.model, design=True); w._solve_done("all", an); app.processEvents()
        ordner = _tf2.mkdtemp()
        pfad = os.path.join(ordner, "rahmen.json")
        w.path = pfad
        w.save_model()
        app.processEvents()
        epfad = _erg.pfad_zu(pfad)
        check("Speichern schreibt die Ergebnisdatei neben das Modell",
              os.path.exists(pfad) and os.path.exists(epfad), epfad)
        n_res = w.cb_result.count()
        w.analysis = None; w.results = None; w.path = ""
        ok = w.modell_laden(pfad)
        app.processEvents()
        check("Öffnen lädt die Ergebnisse mit: Analyse da, Ergebnisliste wie vor dem Speichern",
              ok and w.analysis is not None and w.cb_result.count() == n_res and n_res > 0,
              f"{w.cb_result.count()} / {n_res}")
        w.analysis = None; w.results = None
        w.save_model(); app.processEvents()
        check("Speichern ohne Analyse entfernt die alte Ergebnisdatei", not os.path.exists(epfad))
    except Exception as ex:
        import traceback
        traceback.print_exc()
        check("Ergebnisse neben der Modelldatei", False, str(ex)[:80])
    finally:
        w.error = _alt_error

    # ---- Werte im Bild und Sonde (12.09.2026) --------------------------------
    try:
        _alt_error = w.error
        w.error = lambda msg: check("Werte im Bild: unerwarteter Fehler (Dialog)", False, str(msg)[:90])
        from statik3d.gui import viewport as vpw
        w.load_example("hall"); app.processEvents()
        an = solver.solve_all(w.model, design=True); w._solve_done("all", an); app.processEvents()
        erg = w._ergebnisliste()
        w._baum_geklickt("ergebnis", erg["Kombinationen"][0][2]); app.processEvents()
        w.cb_diagram.setCurrentText("My"); app.processEvents()
        check("Werte im Bild: Schalter Stäbe/Flächen/Volumen und Sonde im Ribbon, anfangs aus",
              all(getattr(w, f"act_werte_{a}", None) is not None and not getattr(w, f"act_werte_{a}").isChecked()
                  for a in ("staebe", "flaechen", "volumen")) and not w.act_sonde.isChecked()
              and not any(a.startswith("ergebniswerte") for a in w.plotter.renderer.actors))
        w.act_werte_staebe.setChecked(True); app.processEvents()
        n_extrem = int(getattr(w, "_werte_im_bild", 0))
        check("Stäbe an: Marken mit My an den Extremstellen, Kopfzeile nennt es",
              any(a.startswith("ergebniswerte") for a in w.plotter.renderer.actors) and 0 < n_extrem <= vpw.WERTE_MAX
              and "Werte im Bild: Stäbe (My)" in " ".join(w._kopfzeile_zeilen), f"{n_extrem} Marken")
        w.cb_werte_filter.setCurrentIndex(w.cb_werte_filter.findData("alle")); app.processEvents()
        n_alle = int(getattr(w, "_werte_im_bild", 0))
        check("Filter „alle Stellen“ zeigt mehr Marken als „Extremwerte“", n_alle > n_extrem, f"{n_alle} > {n_extrem}")
        w.sp_werte_n.setValue(2); app.processEvents()
        n_halb = int(getattr(w, "_werte_im_bild", 0))
        check("jeder 2. Wert: etwa die Hälfte", 0 < n_halb <= n_alle // 2 + 1, f"{n_halb}")
        w.sp_werte_n.setValue(1)
        w.ed_werte_schwelle.setValue(1e8); app.processEvents()
        check("Schwelle über allem: keine Marke, kein Darsteller",
              int(getattr(w, "_werte_im_bild", 0)) == 0
              and not any(a.startswith("ergebniswerte") for a in w.plotter.renderer.actors))
        w.ed_werte_schwelle.setValue(0.0)
        w.cb_werte_filter.setCurrentIndex(w.cb_werte_filter.findData("auswahl")); app.processEvents()
        check("nur Auswahl ohne Auswahl: keine Marke", int(getattr(w, "_werte_im_bild", 0)) == 0)
        e0 = next(i for i, e in enumerate(w.model.elements) if e.typ in vpw.TYPEN_STAEBE)
        w.sel_elemente = [e0]; w.redraw(); app.processEvents()
        check("nur Auswahl mit einem Element: dessen zwei Extremwerte", int(getattr(w, "_werte_im_bild", 0)) == 2,
              str(getattr(w, "_werte_im_bild", 0)))
        w.sel_elemente = []
        w.cb_werte_filter.setCurrentIndex(0)
        w.act_werte_staebe.setChecked(False)
        # Sonde: Klick auf einen Knoten setzt eine Marke mit dem Faerbungswert
        w.cb_field.setCurrentText(FIELDS[0]); app.processEvents()
        w.act_sonde.setChecked(True)
        k2 = 2
        xy_, _s = w._projizieren(np.atleast_2d(w.model.nodes[k2]))
        w.plotter.iren.interactor.SetEventInformation(int(round(xy_[0, 0])), int(round(xy_[0, 1])))
        w._picked(w.model.nodes[k2]); app.processEvents()
        check("Sonde: ein Klick setzt eine Marke am Knoten, mit Wert der Färbung",
              len(w.sonden) == 1 and any(a.startswith("sonden") for a in w.plotter.renderer.actors)
              and w.sonden[0]["knoten"] == k2, str(w.sonden))
        xy_, _s = w._projizieren(np.atleast_2d(w.model.nodes[5]))
        w.plotter.iren.interactor.SetEventInformation(int(round(xy_[0, 0])), int(round(xy_[0, 1])))
        w._picked(w.model.nodes[5] + 1e-4); app.processEvents()
        check("… zweite Sonde am nächsten Knoten", len(w.sonden) == 2 and w.sonden[1]["knoten"] == 5)
        w.cb_field.setCurrentText("Vergleichsspannung"); app.processEvents()
        check("die Sonden folgen der Färbung (bleiben beim Umschalten)", len(w.sonden) == 2
              and any(a.startswith("sonden") for a in w.plotter.renderer.actors))
        w.act_sonde.setChecked(False)
        w.sonden_loeschen(); app.processEvents()
        check("Sonden löschen räumt auf", not w.sonden
              and not any(a.startswith("sonden") for a in w.plotter.renderer.actors))
        # Volumen: ein Wert je Koerper
        w.load_example("friction"); app.processEvents()
        an = solver.solve_all(w.model, combinations=False); w._solve_done("all", an); app.processEvents()
        erg = w._ergebnisliste()
        w._baum_geklickt("ergebnis", f"case:{list(w.model.load_cases)[0]}"); app.processEvents()
        w.cb_field.setCurrentText("Vergleichsspannung"); app.processEvents()
        w.act_werte_volumen.setChecked(True); app.processEvents()
        n_vol = int(getattr(w, "_werte_im_bild", 0))
        check("Volumen an: ein Wert je Volumenkörper (oder einer für das ganze Netz)",
              n_vol == max(1, len([k for k in w.model.koerper.values() if k.elemente])), str(n_vol))
        w.act_werte_volumen.setChecked(False)
        w.act_werte_flaechen.setChecked(True); app.processEvents()
        n_fl = int(getattr(w, "_werte_im_bild", 0))
        check("Flächen an: eine Marke je Schalenelement",
              n_fl == sum(1 for e in w.model.elements if e.typ in vpw.TYPEN_FLAECHEN), str(n_fl))
        w.act_werte_flaechen.setChecked(False); app.processEvents()
    except Exception as ex:
        import traceback
        traceback.print_exc()
        check("Werte im Bild und Sonde", False, str(ex)[:80])
    finally:
        w.error = _alt_error

    # ---- Spannungen im Modellbaum und Werteskala (12.09.2026) ----------------
    try:
        _alt_error = w.error
        w.error = lambda msg: check("Spannungen: unerwarteter Fehler (Dialog)", False, str(msg)[:90])
        from statik3d import spannungen as spn
        from statik3d.model import Model as _Mdl
        from statik3d.gui import viewport as vpx

        def baumnamen(baum):
            namen = []

            def lauf(it):
                namen.append(it.text(0))
                for i in range(it.childCount()):
                    lauf(it.child(i))
            for i in range(baum.topLevelItemCount()):
                lauf(baum.topLevelItem(i))
            return namen
        w.load_example("friction"); app.processEvents()
        an = solver.solve_all(w.model, combinations=False)
        w._solve_done("all", an); app.processEvents()
        erg = w._ergebnisliste()
        namen0 = baumnamen(w.baum)
        check("die Spannungsgruppen stehen im Baum, solange die Umhüllende vorn steht",
              "Spannungen Volumen" in namen0, str([n for n in namen0 if "pannung" in n]))
        w._baum_geklickt("ergebnis", "spannung:volumen:s1"); app.processEvents()
        check("Klick auf eine Spannung bei gezeigter Umhüllender wechselt auf den Lastfall",
              hasattr(w.current_result(), "solid_res") and w.cb_field.currentText() == spn.feldname("volumen", "s1"),
              w.cb_result.currentText()[:40])
        lf0 = list(w.model.load_cases)[0]
        w._baum_geklickt("ergebnis", f"case:{lf0}"); app.processEvents()
        check("Ergebnisliste: Spannungen Volumen (12), Flächen (6), Kontaktspannungen (5); keine Stäbe",
              len(erg.get("Spannungen Volumen", [])) == 12 and len(erg.get("Spannungen Flächen", [])) == 6
              and len(erg.get("Kontaktspannungen", [])) == 5 and "Spannungen Stäbe" not in erg,
              str({k: len(v) for k, v in erg.items() if "pannung" in k}))
        namen = baumnamen(w.baum)
        check("… und sie stehen im Modellbaum", "Spannungen Volumen" in namen and "Kontaktspannungen" in namen
              and "σ_v (von Mises)" in namen, str([n for n in namen if "σ" in n][:4]))
        w._baum_geklickt("ergebnis", "spannung:volumen:sv"); app.processEvents()
        check("Klick im Baum stellt die Färbung ein", w.cb_field.currentText() == spn.feldname("volumen", "sv"),
              w.cb_field.currentText())
        r0 = w.current_result()
        soll = spn.je_knoten(w.model, r0, "volumen", "sv")
        akt = w.plotter.renderer.actors.get("result_netz")
        titel = spn.beschriftung("volumen", "sv")
        ds = akt.mapper.dataset if akt is not None else None
        werte = np.asarray(ds.point_data[titel], float) if ds is not None and titel in ds.point_data else None
        check("die Farbwerte sind die Vergleichsspannung je Knoten in N/mm² (spannungen.je_knoten)",
              werte is not None and np.isclose(np.nanmax(werte), np.nanmax(soll))
              and np.isclose(np.nanmin(werte), np.nanmin(soll)) and np.nanmax(werte) > 0.5,
              f"max {np.nanmax(werte) if werte is not None else None} / {np.nanmax(soll):.3f}")
        check("Skala automatisch: Grenzen = kleinster … größter Wert, 9 Farbstufen (ANSYS)",
              akt is not None and np.allclose(akt.mapper.scalar_range, (np.nanmin(soll), np.nanmax(soll)))
              and akt.mapper.lookup_table.n_values == 9, str(akt.mapper.scalar_range if akt else None))
        w.cb_skala.setCurrentIndex(w.cb_skala.findData("grenze")); app.processEvents()
        w.ed_skala_grenze.setValue(0.5); app.processEvents()
        akt = w.plotter.renderer.actors.get("result_netz")
        lut = akt.mapper.lookup_table
        check("Grenzwert 0,5: Skala 0 … 0,5, darüber magenta, Modell merkt sich die Einstellung",
              np.allclose(akt.mapper.scalar_range, (0.0, 0.5)) and lut.above_range_color is not None
              and str(lut.above_range_color.hex_rgb).lower() == spn.FARBE_UEBER
              and w.model.werteskala.modus == "grenze" and w.model.werteskala.grenze == 0.5,
              f"{akt.mapper.scalar_range} {lut.above_range_color}")
        check("Statuszeile nennt die Überschreitungen", "über 0.5" in w.statusBar().currentMessage()
              and "Knoten" in w.statusBar().currentMessage(), w.statusBar().currentMessage()[:80])
        check("Kopfzeile/Bericht nennen die Skala", "Skala bis 0.5" in w._werteskala_text(), w._werteskala_text())
        w.cb_nur_ueber.setChecked(True); app.processEvents()
        akt = w.plotter.renderer.actors.get("result_netz")
        werte = np.asarray(akt.mapper.dataset.point_data[titel], float)
        check("nur Überschreitungen: alles unter 0,5 ist NaN (grau), der Rest ab 0,5 gefärbt",
              np.isnan(werte).sum() > 0 and np.nanmin(werte) >= 0.5
              and np.allclose(akt.mapper.scalar_range[0], 0.5), f"{np.isnan(werte).sum()} NaN")
        w.cb_nur_ueber.setChecked(False)
        w.cb_skala.setCurrentIndex(w.cb_skala.findData("auto")); app.processEvents()
        check("„nur Überschreitungen“ ist auch im Modus automatisch anklickbar", w.cb_nur_ueber.isEnabled())
        w.cb_nur_ueber.setChecked(True); app.processEvents()
        check("… und schaltet die Skala selbst auf Grenzwert um",
              w.cb_skala.currentData() == "grenze" and w.model.werteskala.modus == "grenze"
              and w.model.werteskala.nur_ueber, str(w.cb_skala.currentData()))
        w.ed_skala_grenze.setValue(round(float(np.nanmax(soll)) + 1.0, 2)); app.processEvents()
        check("Grenze über allem: die Statuszeile sagt, dass nichts überschritten ist und alles grau bleibt",
              "keine Überschreitung" in w.statusBar().currentMessage()
              and "grau" in w.statusBar().currentMessage(), w.statusBar().currentMessage()[:90])
        w.cb_nur_ueber.setChecked(False)
        w.ed_skala_grenze.setValue(0.5); app.processEvents()
        # fest: Grenzen zwischen den Werten, damit es darunter und darueber etwas gibt
        # die Felder haben zwei Nachkommastellen (QDoubleSpinBox, decimals 2)
        u30, o70 = (round(float(np.nanpercentile(soll, 30)), 2), round(float(np.nanpercentile(soll, 70)), 2))
        w.cb_skala.setCurrentIndex(w.cb_skala.findData("fest"))
        w.ed_skala_unten.setValue(u30); w.ed_skala_oben.setValue(o70)
        app.processEvents()
        akt = w.plotter.renderer.actors.get("result_netz")
        lut = akt.mapper.lookup_table
        check("fest (30 % … 70 % der Werte): darunter und darüber je eigene Farbe",
              np.allclose(akt.mapper.scalar_range, (u30, o70), atol=1e-6)
              and lut.below_range_color is not None and lut.above_range_color is not None,
              f"{akt.mapper.scalar_range} unter {lut.below_range_color} über {lut.above_range_color}")
        d = w.model.to_dict(); m2 = _Mdl.from_dict(d)
        check("die Werteskala wird mit dem Modell gespeichert und geladen",
              m2.werteskala is not None and m2.werteskala.modus == "fest"
              and abs(m2.werteskala.oben - o70) < 1e-9)
        w.cb_skala.setCurrentIndex(w.cb_skala.findData("auto")); app.processEvents()
        w.cb_field.setCurrentText(spn.feldname("flaechen", "sx"))
        w.cb_seite.setCurrentIndex(w.cb_seite.findData("oben")); app.processEvents()
        titel = spn.beschriftung("flaechen", "sx", "oben")
        akt = w.plotter.renderer.actors.get("result_netz")
        check("Flächen σ_x oben: die Schalenseite steht im Titel der Skala",
              akt is not None and titel in akt.mapper.dataset.point_data, titel)
        w.cb_seite.setCurrentIndex(0)
        w.cb_field.setCurrentText(spn.feldname("kontakt", "p")); app.processEvents()
        akt = w.plotter.renderer.actors.get("result_netz")
        pw = np.asarray(akt.mapper.dataset.point_data[spn.beschriftung("kontakt", "p")], float)
        check("Kontaktdruck: nur die Kontaktknoten haben Werte, Größtwert > 0",
              np.isnan(pw).sum() > 0 and np.nanmax(pw) > 0, f"{np.isfinite(pw).sum()} Knoten mit Druck")
        check("Knoten ohne Wert sind neutral grau, die Skala schreibt Zahlen aus",
              tuple(round(c, 2) for c in list(akt.mapper.lookup_table.nan_color)[:3])
              == tuple(round(c, 2) for c in __import__("pyvista").Color(vpx.FARBE_OHNE_WERT).float_rgb)
              and next(iter(w.plotter.scalar_bars.values())).GetLabelFormat()
              == spn.skalenformat(*akt.mapper.scalar_range),
              next(iter(w.plotter.scalar_bars.values())).GetLabelFormat())
        # Kontaktmarken (Kugeln je Zustand) nur mit Schalter (12.09.2026)
        check("Kontaktmarken bleiben aus, solange der Schalter aus ist",
              not any(a.startswith("contact_") for a in w.plotter.renderer.actors)
              and not w.act_kontaktmarken.isChecked())
        w.act_kontaktmarken.setChecked(True); app.processEvents()
        check("Kontaktmarken mit Schalter, die Kopfzeile erklärt die Farben",
              any(a.startswith("contact_") for a in w.plotter.renderer.actors)
              and "Kontaktmarken: grün haftet" in " ".join(w._kopfzeile_zeilen))
        w.act_kontaktmarken.setChecked(False)
        w.cb_field.setCurrentText("Vergleichsspannung"); app.processEvents()
        check("… und nach dem Umschalten der Färbung sind sie weg",
              not any(a.startswith("contact_") for a in w.plotter.renderer.actors))
        # --- Ergebnisdarstellung ausschalten (14.09.2026) ---
        w.act_kontaktmarken.setChecked(True); app.processEvents()
        n_skalen = len(w.plotter.scalar_bars)
        w.act_ergebnisse.setChecked(False); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        modell_ = [a for a in akt_ if a.startswith("model_")]
        check("„Ergebnisse zeigen“ aus: keine Färbung, keine Skala, keine Kontaktmarken",
              not len(w.plotter.scalar_bars) and n_skalen >= 1
              and not any(a.startswith("contact_") for a in akt_)
              and not any(a.startswith("result_") for a in akt_),
              f"{len(w.plotter.scalar_bars)} Skalen, {sum(1 for a in akt_ if a.startswith('contact_'))} Marken, "
              f"{sum(1 for a in akt_ if a.startswith('result_'))} Ergebnisdarsteller")
        check("… das Modell bleibt im Bild und die Kopfzeile sagt, dass die Ergebnisse ausgeblendet sind",
              modell_ and "Ergebnisse ausgeblendet" in " ".join(w._kopfzeile_zeilen),
              f"{modell_}, {str(w._kopfzeile_zeilen)[:100]}")
        check("… und die Ergebnisse sind nur versteckt, nicht verworfen",
              w.current_result() is not None and not w.ergebnisse_sichtbar())
        w.act_ergebnisse.setChecked(True); app.processEvents()
        check("wieder an: Färbung und Skala sind zurück",
              len(w.plotter.scalar_bars) >= 1 and w.ergebnisse_sichtbar()
              and "Ergebnisse ausgeblendet" not in " ".join(w._kopfzeile_zeilen))
        w.act_kontaktmarken.setChecked(False); app.processEvents()
        w.cb_field.setCurrentText(spn.feldname("kontakt", "zustand")); app.processEvents()
        akt = w.plotter.renderer.actors.get("result_netz")
        lut = akt.mapper.lookup_table
        ann = [lut.GetAnnotation(i) for i in range(lut.GetNumberOfAnnotatedValues())]
        check("Kontakt Zustand: Klassenfärbung mit vier festen Farben und Beschriftung je Klasse",
              lut.n_values == 4 and np.allclose(akt.mapper.scalar_range, (-0.5, 3.5))
              and len(ann) == 4 and "haftet" in ann, f"{lut.n_values} {ann}")
        # Skala und Kennwerte nur fuer sichtbare Teile: die Platte (Schalen) ausblenden
        w.cb_field.setCurrentText("Vergleichsspannung"); app.processEvents()
        alle = np.asarray(w.plotter.renderer.actors["result_netz"].mapper.scalar_range, float)
        schalen = {i for i, e in enumerate(w.model.elements) if e.typ in vpx.TYPEN_FLAECHEN}
        w.versteckt["elemente"] = set(schalen); w.redraw(); app.processEvents()
        sicht = w._sichtbare_knoten()
        soll_max = float(np.nanmax(spn.je_knoten(w.model, w.current_result(), "volumen", "sv")[sicht]))
        rng = np.asarray(w.plotter.renderer.actors["result_netz"].mapper.scalar_range, float)
        check("ausgeblendete Platte: die Skala folgt nur den sichtbaren Knoten, Kopfzeile sagt es",
              np.isclose(rng[1], soll_max) and rng[1] <= alle[1] + 1e-9
              and "Skala: nur sichtbare Teile" in " ".join(w._kopfzeile_zeilen)
              and w._kennwerte_zeilen and w._kennwerte_zeilen[0] == "nur sichtbare Teile",
              f"{rng} statt {alle}")
        w.versteckt["elemente"] = set(); w.redraw(); app.processEvents()
        # Umhuellende: keine Komponenten - keine Faerbung, aber kein Fehler
        env = next((k for k, _z, key in erg.get("Umhüllende", []) for k in [key]), None) if erg.get("Umhüllende") else None
        if env:
            w._baum_geklickt("ergebnis", env); app.processEvents()
            w.cb_field.setCurrentText(spn.feldname("volumen", "s1")); app.processEvents()
            check("Umhüllende: Spannungskomponenten ohne Färbung, mit Hinweis statt Fehler",
                  "Umhüllenden" in w.statusBar().currentMessage()
                  and not [l for l in w.log.toPlainText().splitlines() if "Darstellung:" in l],
                  w.statusBar().currentMessage()[:70])
        w.cb_field.setCurrentText(FIELDS[0]); app.processEvents()
        check("Ribbon Ergebnisse: Knopf „Werteskala“", getattr(w, "act_werteskala", None) is not None
              and w.act_werteskala.text() == "Werteskala")
    except Exception as ex:
        import traceback
        traceback.print_exc()
        check("Spannungen und Werteskala", False, str(ex)[:80])
    finally:
        w.error = _alt_error

    # ---- Ergebnisse im Modellbaum und Übernahme in den Bericht -------------
    try:
        w.error = lambda msg: check("Bericht: unerwarteter Fehler", False, str(msg)[:60])
        w.load_example("hall")
        an = solver.solve_all(w.model, design=True)
        w._solve_done("all", an)
        app.processEvents()
        erg = w._ergebnisliste()
        for gruppe in ("Umhüllende", "Kombinationen", "Lastfälle", "Nachweise"):
            check(f"Ergebnisliste: „{gruppe}“", gruppe in erg and erg[gruppe],
                  f"{len(erg.get(gruppe, []))} Einträge")
        sg = [z for _n, z, _k in erg.get("Schnittgrößen", [])]
        check("Schnittgrößen im Baum als normale Dezimalzahl (kein 2.33e-13 im Modellbaum)",
              sg and not any("e-" in z or "e+" in z for z in sg) and all("…" in z for z in sg[:-1]),
              str(sg[:2]))
        namen = zweige(w.baum)
        check("Ergebnisse stehen im Modellbaum", "Ergebnisse" in namen)
        check("Bericht steht im Modellbaum", "Bericht" in namen)
        w._baum_geklickt("ergebnis", "combo:GZT7")
        check("Klick im Baum stellt das Ergebnis ein",
              "GZT7" in w.cb_result.currentText(), w.cb_result.currentText()[:40])
        # Ergebnistabellen (12.09.2026): die Umhüllende leert „Stabkräfte“ mit
        # Hinweis und stellt das Register auf „Umhüllende“; ein gewähltes Element
        # findet seine Zeile auch ohne die alte Grenze von 50 000 Elementen
        from statik3d.gui import viewport as vpx
        tabs = w.tab_unten
        tabs.setCurrentIndex(tabs.indexOf(w.tbl_beam)); app.processEvents()
        check("Kombination: „Stabkräfte“ gefüllt, ohne Hinweis",
              len(w.tbl_beam.modell.zeilen) > 0 and "Umhüllende" not in w.tbl_beam.lbl_zeilen.text(),
              w.tbl_beam.lbl_zeilen.text()[:60])
        env_key = erg["Umhüllende"][0][2]
        w._baum_geklickt("ergebnis", env_key); app.processEvents()
        check("Umhüllende: „Stabkräfte“ leer mit Hinweis, Register springt auf „Umhüllende“",
              len(w.tbl_beam.modell.zeilen) == 0 and "Umhüllende" in w.tbl_beam.lbl_zeilen.text()
              and tabs.currentWidget() is w.tbl_env and len(w.tbl_env.modell.zeilen) > 0,
              w.tbl_beam.lbl_zeilen.text()[:70])
        w._baum_geklickt("ergebnis", "combo:GZT7"); app.processEvents()
        check("zurück zur Kombination: Register wieder „Stabkräfte“, Hinweis weg",
              tabs.currentWidget() is w.tbl_beam and "Umhüllende" not in w.tbl_beam.lbl_zeilen.text(),
              w.tbl_beam.lbl_zeilen.text()[:60])
        mx = w.model
        e0 = next(i for i, e in enumerate(mx.elements) if e.typ in vpx.TYPEN_STAEBE)
        knoten = {int(n) for n in mx.elements[e0].nodes}
        brute = [i for i, e in enumerate(mx.elements) if {int(n) for n in e.nodes} <= knoten]
        check("_elemente_ganz_in: die Elemente, deren Knoten alle gewählt sind (wie die alte Schleife)",
              list(w._elemente_ganz_in(knoten)) == brute and e0 in brute, str(brute))
        alle = {int(n) for e in mx.elements for n in e.nodes}
        check("… und mit allen Knoten alle Elemente, vektorisiert",
              len(w._elemente_ganz_in(alle)) == len(mx.elements) and len(w._elemente_ganz_in(set())) == 0)
        w._set_selection(sorted(knoten)); app.processEvents()
        zeilen = [w.tbl_beam.filter.index(i.row(), 0).data()
                  for i in w.tbl_beam.view.selectionModel().selectedRows()]
        check("gewähltes Element: seine Zeile in „Stabkräfte“ ist markiert",
              any(int(float(str(z).replace(",", "."))) == e0 for z in zeilen), f"{zeilen[:3]} / {e0}")
        w._set_selection([]); app.processEvents()
        w.cb_field.setCurrentText("Ausnutzung EC3")
        w.cb_diagram.setCurrentText("My")
        app.processEvents()
        check("aktuelle Quelle wird erkannt", w._aktuelle_quelle() == "combo:GZT7",
              w._aktuelle_quelle())
        w.ansicht_in_bericht()
        app.processEvents()
        b = w.model.bericht
        check("Ansicht in den Bericht übernommen", len(b) == 1, f"{len(b)}")
        check("das Bild ist wirklich drin", len(b[0].bild) > 5000,
              f"{len(b[0].bild) // 1024} kB Base64")
        check("die Einstellung steht dabei",
              b[0].bezug() == "Kombination GZT7 · Ausnutzung EC3 · My", b[0].bezug())
        check("Tabelle „Bericht“ gefüllt", len(w.tbl_bericht.modell.zeilen) == 1)
        w._baum_geklickt("ergebnis", "env:GZT")
        w.cb_field.setCurrentText("|u| Verschiebung")
        app.processEvents()
        w.ansicht_in_bericht()
        check("zweites Bild übernommen", len(w.model.bericht) == 2)
        w.tbl_bericht.view.selectRow(1)
        w.berichtseintrag_schieben(-1)
        check("Reihenfolge lässt sich ändern",
              [x.name for x in w.model.bericht] == ["Bild 2", "Bild 1"],
              str([x.name for x in w.model.bericht]))
        check("Beschriftung editierbar",
              w._bericht_aendern(0, 3, "Verformung im GZG")
              and w.model.bericht[0].beschriftung == "Verformung im GZG")
        from statik3d.report.html import Report
        html = Report(w.model, w.analysis).html()
        check("Bericht hat das Kapitel „Übernommene Ergebnisse“ (bis 12.09.2026: Ergebnisbilder)",
              "Übernommene Ergebnisse" in html)
        check("die Bilder stehen im Bericht",
              html.count("data:image/png;base64") >= 2,
              f"{html.count('data:image/png;base64')} Bilder")
        check("die Bildunterschrift steht im Bericht", "Verformung im GZG" in html)
        w.tbl_bericht.view.selectRow(0)
        w.berichtseintrag_loeschen()
        check("Bild löschbar", len(w.model.bericht) == 1)
        w.undo()
        check("Löschen ist rücknehmbar", len(w.model.bericht) == 2)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Ergebnisse und Bericht", False, str(ex)[:70])

    # ---- Lasten, Fang, Glasleiste, Masken rechts --------------------------
    try:
        from statik3d.gui import viewport as vpl
        w.error = lambda msg: check("Ansicht: unerwarteter Fehler", False, str(msg)[:60])
        w.load_example("hall")
        app.processEvents()
        ml = w.model

        # Linien werden gezeichnet
        ml.add_line("L1", [0, 1, 2])
        w.refresh_all()
        app.processEvents()
        check("Schalter „Linien“ vorhanden und an", w.act_linien.isChecked())
        check("Linien stehen im Modellbaum", "Linien" in zweige(w.baum))

        # Lastentabelle
        check("Register „Lasten“ vorhanden",
              "Lasten" in [w.tab_unten.tabText(i) for i in range(w.tab_unten.count())])
        n_last = sum(lc.n_loads for lc in ml.load_cases.values())
        check("Lastentabelle gefüllt", len(w.tbl_last.modell.zeilen) == n_last,
              f"{len(w.tbl_last.modell.zeilen)} von {n_last}")
        arten = {z[2] for z in w.tbl_last.modell.zeilen}
        check("die Lastarten stehen dabei",
              {"Eigengewicht", "Streckenlast"} <= arten, str(sorted(arten)))
        check("Lasten stehen im Modellbaum als Unterpunkte der Lastfälle",
              any(t in zweige(w.baum) for t in ("Eigengewicht", "Stablasten", "Knotenlasten",
                                                  "Flächenlasten", "Linienlasten")),
              str([t for t in zweige(w.baum) if t.endswith("lasten") or t == "Eigengewicht"][:5]))
        # Unterpunkte je Lastart (#132): ein Klick zeigt rechts nur diese Lasten
        fall_ = next((n for n, lc in ml.load_cases.items() if lc.lasten_je_art().get("stab")), None)
        if fall_:
            w._baum_geklickt("lastart", f"{fall_}|stab")
            app.processEvents()
            mk_ = w.maskenrand.maske
            check("Unterpunkt „Stablasten“: rechts nur diese Lasten, Tabelle auf den Lastfall, Stäbe leuchten",
                  mk_ is not None and mk_.titel == f"Lastfall {fall_}: Stablasten" and w.rechts_zeigt() == "maske"
                  and w.cb_lastfilter.currentText() == fall_ and len(w.leuchtet) > 0
                  and "l0" in mk_.werte() and "q =" in mk_.werte()["l0"],
                  str(mk_.werte() if mk_ else None)[:160])
            mk_.anwenden()
            app.processEvents()
            mk_ = w.maskenrand.maske
            check("„Lastfall bearbeiten“ holt die Maske des Lastfalls: Nummer, Name, Beschreibung, Einwirkung, Lasten",
                  mk_ is not None and mk_.titel == f"Lastfall {fall_}" and "last_stab" in mk_.werte()
                  and list(mk_.werte())[:4] == ["nummer", "name", "beschreibung", "kategorie"],
                  str(list(mk_.werte())[:6] if mk_ else None))
        else:
            check("Beispiel hat Stablasten für den Unterpunkt-Test", False)
        # Vorspannung als Last (#131): Maske, Lastfall-Unterpunkt, Tabelle, Ansicht
        fehler_v = []
        alt_error_v = w.error
        w.error = lambda text: fehler_v.append(str(text))
        check("Ribbon Lasten hat „Vorspannung“",
              any(b.register == "Lasten" and b.text == "Vorspannung" for b in w.ribbon.befehle))
        w.maske_vorspannung()
        app.processEvents()
        mk_ = w.maskenrand.maske
        check("Vorspannungsmaske: Kraft, Achse, Bemerkung, Lastfall",
              mk_ is not None and all(k in mk_.werte() for k in ("F", "achse", "kommentar", "fall")),
              str(mk_.werte() if mk_ else None)[:120])
        mk_.anwenden()
        app.processEvents()
        check("Vorspannung ohne Auswahl: Hinweis", bool(fehler_v) and "wählen" in fehler_v[-1], str(fehler_v[-1:]))
        stab_ = next(iter(ml.members))
        w.sel_staebe = [stab_]
        mk_.setzen("F", 150.0)
        mk_.setzen("kommentar", "Zugstange")
        n_fv = len(fehler_v)
        mk_.anwenden()
        app.processEvents()
        lc_ = ml.case()
        check("„Last aufbringen“ legt die Vorspannung im aktiven Lastfall an",
              len(lc_.vorspannungen) == 1 and lc_.vorspannungen[0].ziel == stab_
              and abs(lc_.vorspannungen[0].kraft - 150e3) < 1e-6 and len(fehler_v) == n_fv,
              str((fehler_v[n_fv:], lc_.vorspannungen)))
        check("Modellbaum: Unterpunkt „Vorspannung“ am Lastfall", "Vorspannung" in zweige(w.baum))
        zv_ = [r for r in w.tbl_last.modell.zeilen if r[2] == "Vorspannung"]
        check("Lastentabelle nennt die Vorspannung mit F_v",
              len(zv_) == 1 and "150" in str(zv_[0][4]) and stab_ in str(zv_[0][3]), str(zv_[:1]))
        w._baum_geklickt("lastart", f"{lc_.name}|vorspannung")
        app.processEvents()
        mk_ = w.maskenrand.maske
        check("Unterpunkt „Vorspannung“: rechts die Last, der Stab leuchtet",
              mk_ is not None and mk_.titel == f"Lastfall {lc_.name}: Vorspannung"
              and "F_v = 150 kN" in mk_.werte().get("l0", "") and w.sel_staebe == [stab_],
              str(mk_.werte().get("l0") if mk_ else None))
        w.redraw()
        app.processEvents()
        check("Ansicht zeichnet die Vorspannung (Pfeile)", "vorspannung" in w.plotter.renderer.actors)
        fr_ = Model.from_dict(ml.to_dict())
        check("Vorspannung überlebt Speichern und Laden",
              len(fr_.case().vorspannungen) == 1 and fr_.case().vorspannungen[0].kommentar == "Zugstange")
        lc_.vorspannungen.clear()
        w.error = alt_error_v
        w.clear_selection()
        w.refresh_all()
        app.processEvents()
        # Lasten anklicken (#130): Auswahlart „Last“, Maske je Last, ändern, verschieben, löschen
        fehler_l = []
        alt_error_l = w.error
        w.error = lambda text: fehler_l.append(str(text))
        hatte_best = "_bestaetigen" in w.__dict__
        w._bestaetigen = lambda text: True
        check("Auswahlart „Last“ in der Glasleiste", "Last" in w.AUSWAHLARTEN and "Last" in w.act_auswahlart)
        fall_k = next((n for n, lc in ml.load_cases.items() if lc.lasten_je_art().get("knoten")), None)
        alt_aktiv = ml.active_case
        if fall_k:
            ml.active_case = fall_k
            w.refresh_all()
            w.redraw()
            app.processEvents()
            lc_k = ml.load_cases[fall_k]
            check("die Ansicht merkt sich die gezeichneten Lastsymbole",
                  any(x[0] == "nodal_loads" for x in w._lastpunkte), str(len(w._lastpunkte)))
            w.auswahlart_setzen("Last")
            k0 = next(i for i, l in enumerate(lc_k.nodal_loads) if not getattr(l, "_geo", False))
            w._picked(np.array(ml.nodes[int(lc_k.nodal_loads[k0].node)], float))
            app.processEvents()
            mk_ = w.maskenrand.maske
            check("Klick auf den Lastpfeil wählt die Knotenlast und öffnet rechts ihre Maske",
                  w.sel_lasten == [(fall_k, "nodal_loads", k0)] and mk_ is not None
                  and mk_.titel.startswith("Knotenlast K")
                  and all(k in mk_.werte() for k in ("Fx", "Fy", "Fz", "Mx", "My", "Mz", "fall")),
                  str((w.sel_lasten, mk_.titel if mk_ else None)))
            check("die angeklickte Last leuchtet in der Ansicht", "last_hervor" in w.plotter.renderer.actors)
            mk_.setzen("Fz", -33.0)
            mk_.anwenden()
            app.processEvents()
            check("„Übernehmen“ ändert die Kraft, die Maske bleibt offen",
                  abs(float(lc_k.nodal_loads[k0].F[2]) + 33e3) < 1e-6 and not fehler_l
                  and w.maskenrand.maske is not None and abs(float(w.maskenrand.maske.werte()["Fz"]) + 33.0) < 1e-9,
                  str((lc_k.nodal_loads[k0].F[2], fehler_l[:1])))
            mk_ = w.maskenrand.maske
            anderer = next(n for n in ml.load_cases if n != fall_k)
            n_alt, n_neu = len(lc_k.nodal_loads), len(ml.load_cases[anderer].nodal_loads)
            mk_.setzen("fall", anderer)
            mk_.anwenden()
            app.processEvents()
            check("ein anderer Lastfall in der Maske verschiebt die Last dorthin",
                  len(lc_k.nodal_loads) == n_alt - 1 and len(ml.load_cases[anderer].nodal_loads) == n_neu + 1
                  and w.sel_lasten and w.sel_lasten[0][0] == anderer, str(w.sel_lasten))
            w.undo()
            app.processEvents()
            ml = w.model
            w.undo()
            app.processEvents()
            ml = w.model
            check("Rückgängig stellt die Last zurück",
                  len(ml.load_cases[fall_k].nodal_loads) == n_alt
                  and abs(float(ml.load_cases[fall_k].nodal_loads[k0].F[2]) + 33e3) > 1.0,
                  str(ml.load_cases[fall_k].nodal_loads[k0].F[2]))
            fall_s = next((n for n, lc in ml.load_cases.items() if lc.lasten_je_art().get("stab")), None)
            ml.active_case = fall_s
            w.refresh_all()
            w.redraw()
            app.processEvents()
            eintrag = next(x for x in w._lastpunkte if x[0] == "beam_loads")
            w._picked(np.array(eintrag[2], float))
            app.processEvents()
            mk_ = w.maskenrand.maske
            check("Klick auf eine Streckenlast: Maske mit q, q2, Bezug, Abschnitt",
                  mk_ is not None and mk_.titel.startswith("Stablast E")
                  and all(k in mk_.werte() for k in ("qx", "qz", "trapez", "system", "a", "b")),
                  str(mk_.titel if mk_ else None))
            n_vor = len(ml.load_cases[fall_s].beam_loads)
            mk_.zusatzknoepfe["Löschen"].click()
            app.processEvents()
            check("„Löschen“ in der Lastmaske nimmt die Last heraus und schließt die Maske",
                  len(ml.load_cases[fall_s].beam_loads) == n_vor - 1 and not w.sel_lasten
                  and w.rechts_zeigt() != "maske", str((n_vor, len(ml.load_cases[fall_s].beam_loads))))
            w.undo()
            app.processEvents()
            ml = w.model
            w._picked(np.array([1e3, 1e3, 1e3]))
            app.processEvents()
            check("Klick ins Leere trifft keine Last", not w.sel_lasten)
            w._fenster_abbrechen()
            ml.active_case = alt_aktiv
        else:
            check("Beispiel hat Knotenlasten für den Klick-Test", False)
        w.auswahlart_setzen("Knoten")
        w.error = alt_error_l
        if not hatte_best:
            del w._bestaetigen
        w.clear_selection()
        w.refresh_all()
        app.processEvents()
        erster = list(ml.load_cases)[0]
        w.cb_lastfilter.setCurrentText(erster)
        app.processEvents()
        check("Lastfilter wirkt",
              {z[1] for z in w.tbl_last.modell.zeilen} == {erster},
              str({z[1] for z in w.tbl_last.modell.zeilen}))
        w.cb_lastfilter.setCurrentText("(alle)")
        app.processEvents()
        w.tbl_last.view.selectRow(1)
        w._tabelle_last(1)
        check("Klick auf eine Lastzeile wählt ihr Ziel", len(w.selection) > 0,
              f"{len(w.selection)} Knoten")
        n0 = len(w.tbl_last.modell.zeilen)
        w.tbl_last.view.selectRow(1)
        w.last_loeschen()
        check("Last löschbar", len(w.tbl_last.modell.zeilen) == n0 - 1,
              f"{len(w.tbl_last.modell.zeilen)} statt {n0}")
        w.undo()
        check("Löschen ist rücknehmbar", len(w.tbl_last.modell.zeilen) == n0)

        # Fang
        from statik3d import ks as ksm
        check("alle Fangarten an (Knoten, Mitte, Linie, Stab, Fläche, Volumen, Raster)",
              sorted(w.fang_arten) == sorted(ksm.FANGARTEN), str(w.fang_arten))
        check("die Statuszeile sagt dann „alle“", w.lbl_fang.text().startswith("Fang: alle"),
              w.lbl_fang.text())
        w.fangart_umschalten("mitte", False)
        check("eine Fangart abschaltbar", "mitte" not in w.fang_arten, str(w.fang_arten))
        check("die Statuszeile nennt die Fangarten mit Namen",
              "Knoten" in w.lbl_fang.text() and "Kantenmitte" not in w.lbl_fang.text(),
              w.lbl_fang.text())
        w.fangart_umschalten("mitte", True)
        check("und wieder an", "mitte" in w.fang_arten)

        # Glasleiste und Ansichtswürfel
        check("Glasleiste über der Ansicht", w.glasleiste.isVisible()
              and w.glasleiste.width() > 200, f"{w.glasleiste.width()} px")
        check("Ansichtswürfel vorhanden", w.ansichtswuerfel.isVisible())
        for richtung in ("xy", "xz", "yz", "iso"):
            w.ansichtswuerfel.gewaehlt.emit(richtung)
            app.processEvents()
        check("Blickrichtung über den Würfel", True)
        # Alle sechs Seiten und das Umkehren - die Rueckseite ist ein Klick
        richtungen = [r for _t, r, _h in w.ansichtswuerfel.RICHTUNGEN]
        check("der Würfel bietet +x +y +z -x -y -z und iso",
              set(richtungen) == {"+x", "+y", "+z", "-x", "-y", "-z", "iso"},
              str(richtungen))
        w.blickrichtung("vorne")
        app.processEvents()
        vorn = np.asarray(w.plotter.camera_position[0], float)
        blick = np.asarray(w.plotter.camera_position[1], float)
        check("Vorderansicht schaut aus −Y", vorn[1] < blick[1],
              f"{np.round(vorn, 3)} -> {np.round(blick, 3)}")
        w.blickrichtung("hinten")
        app.processEvents()
        hint = np.asarray(w.plotter.camera_position[0], float)
        check("Rückansicht schaut aus +Y", hint[1] > blick[1], str(np.round(hint, 3)))
        w.blickrichtung("iso")
        app.processEvents()
        vorher = np.asarray(w.plotter.camera_position[0], float)
        mitte = np.asarray(w.plotter.camera_position[1], float)
        w.blickrichtung("kehren")
        app.processEvents()
        nachher = np.asarray(w.plotter.camera_position[0], float)
        check("„180°“ kehrt die Ansicht am Blickpunkt um",
              float(np.linalg.norm(nachher - (2 * mitte - vorher))) < 1e-6,
              f"{np.round(vorher, 3)} -> {np.round(nachher, 3)}")
        # Mausrad: der Punkt unter dem Zeiger muss stehen bleiben
        w.blickrichtung("iso")
        app.processEvents()
        breite, hoehe = w.plotter.render_window.GetSize()
        x_qt, y_qt = breite * 0.25, hoehe * 0.25      # deutlich neben der Mitte
        vorher = w._bildpunkt_in_welt(x_qt, hoehe - 1 - y_qt)
        pos_v = np.asarray(w.plotter.camera_position[0], float)
        ziel_v = np.asarray(w.plotter.camera_position[1], float)
        w.zoom_zum_zeiger(2.0, x_qt, y_qt)
        app.processEvents()
        ren_z = w.plotter.renderer

        def bildpunkt(p):
            ren_z.SetWorldPoint(float(p[0]), float(p[1]), float(p[2]), 1.0)
            ren_z.WorldToDisplay()
            return np.asarray(ren_z.GetDisplayPoint()[:2], float)

        nachher = bildpunkt(vorher) if vorher is not None else None
        pos_n = np.asarray(w.plotter.camera_position[0], float)
        ziel_n = np.asarray(w.plotter.camera_position[1], float)
        groesse = max(float(np.linalg.norm(pos_v - ziel_v)), 1e-9)
        wanderung = (float(np.linalg.norm(nachher - np.array([x_qt, hoehe - 1 - y_qt])))
                     if nachher is not None else 1e9)
        check("Mausrad zoomt zum Zeiger: der Punkt darunter bleibt liegen (auf demselben Pixel)",
              vorher is not None and wanderung < 0.5, f"Wanderung {wanderung:.2f} px")
        # Der Blickpunkt rueckt beim Zoomen auf die Flaeche unter dem Zeiger;
        # ob die Kamera vorfaehrt, sagt darum ihre Bewegung, nicht der
        # Abstand zum Blickpunkt
        check("und die Kamera fährt dabei wirklich vor",
              float(np.linalg.norm(pos_n - pos_v)) > 0.25 * groesse,
              f"{float(np.linalg.norm(pos_n - pos_v)):.4g} m bei Bildgröße {groesse:.4g} m")
        check("der Zielpunkt wandert dabei mit (nicht die Bildmitte)",
              float(np.linalg.norm(ziel_n - ziel_v)) > 1e-9 * groesse,
              f"{np.round(ziel_v, 4)} -> {np.round(ziel_n, 4)}")
        # … und zwar auf die **Oberflaeche** unter dem Zeiger zu, nicht auf die
        # Brennebene: am Drehlager wurde die Bohrung ab dem zehnten Radschritt
        # wieder ferner, waehrend der Blickpunktabstand auf 0,4 mm schrumpfte
        w.blickrichtung("iso"); app.processEvents()
        X = np.asarray(w.model.nodes, float)
        ziel_pix = None
        for kn in range(min(int(w.model.nn), 60)):
            px = bildpunkt(X[kn])
            if (2 < px[0] < breite - 3 and 2 < px[1] < hoehe - 3
                    and w._oberflaeche_unter_zeiger(px[0], px[1]) is not None):
                ziel_pix = px
                break
        flaeche = w._oberflaeche_unter_zeiger(*ziel_pix) if ziel_pix is not None else None
        check("unter dem Zeiger liegt eine Fläche: der z-Puffer liefert ihren Weltpunkt",
              flaeche is not None and np.isfinite(flaeche).all(), str(ziel_pix))
        if flaeche is not None:
            kam = w.plotter.renderer.GetActiveCamera()
            abst = [float(np.linalg.norm(np.asarray(kam.GetPosition(), float) - flaeche))]
            for _ in range(25):
                w.zoom_zum_zeiger(w.RADSCHRITT, ziel_pix[0], hoehe - 1 - ziel_pix[1]); app.processEvents()
                abst.append(float(np.linalg.norm(np.asarray(kam.GetPosition(), float) - flaeche)))
            quot = np.array(abst[1:]) / np.maximum(np.array(abst[:-1]), 1e-12)
            check("25 Radschritte: der Abstand zur Fläche schrumpft in jedem Schritt um denselben Anteil "
                  "(1/1,15) und wird nie wieder größer",
                  bool(np.all(quot < 0.9)) and bool(np.all(quot > 0.84)) and abst[-1] < 0.05 * abst[0],
                  f"{abst[0]:.3f} -> {abst[-1]:.4f} m, Quotienten {quot.min():.3f} … {quot.max():.3f}")
            px2 = bildpunkt(flaeche)
            check("… die Fläche bleibt dabei unter dem Zeiger",
                  float(np.linalg.norm(px2 - ziel_pix)) < 1.0, f"{float(np.linalg.norm(px2 - ziel_pix)):.2f} px")
            # Der Flaechenpunkt wird je Schritt neu gelesen, und der Tiefenpuffer
            # ist grob (gemessen 2,8 mm Unterschied zweier Lesungen bei 1,27 m,
            # aus 40 m Abstand Zentimeter) - darum gegen den zuletzt gelesenen
            # Punkt mit 1 % pruefen. Vorher lag der Blickpunkt 0,4 mm vor der
            # Kamera, die Flaeche 0,34 m weit weg.
            richtung = np.asarray(kam.GetDirectionOfProjection(), float)
            fl2 = w._oberflaeche_unter_zeiger(*ziel_pix)
            tiefe = (float(np.dot(fl2 - np.asarray(kam.GetPosition(), float), richtung))
                     if fl2 is not None else -1.0)
            check("der Blickpunkt (Drehmitte) liegt in der Tiefe der Fläche",
                  fl2 is not None and abs(float(kam.GetDistance()) - tiefe) < 1e-2 * tiefe,
                  f"{kam.GetDistance():.4f} / {tiefe:.4f} m")
        w.blickrichtung("iso"); app.processEvents()

        w.auswahlart_setzen("Linie")
        check("die Glasleiste kommt ohne Auswahlfeld aus", getattr(w, "cb_auswahlart_glas", None) is None
              and w.cb_auswahlart.currentText() == w.auswahlart, w.auswahlart)
        w.auswahlart_setzen("Knoten")

        # Erzeuge-Maske steht rechts, nicht über der Ansicht
        w.maske_linie()
        app.processEvents()
        mk = w.maskenrand.maske
        check("Erzeuge-Maske im rechten Bereich",
              mk is not None and mk.parent() is not w.centralWidget())
        check("der Docktitel nennt sie", w.eingaben_dock.windowTitle() == "Linie",
              w.eingaben_dock.windowTitle())
        check("Vorgabe ist die Polylinie, nicht der Bogen",
              mk.werte().get("art", "").startswith("Polylinie"),
              str(mk.werte().get("art")))
        w.maskenrand.schliessen()
        app.processEvents()

        # Modellbaum: Klick öffnet rechts die passende Maske und lässt aufleuchten
        w._baum_geklickt("lager_einzeln", "0")
        check("Klick auf ein Lager öffnet rechts die Maske des Knotenlagers",
              w.eingaben_dock.windowTitle().startswith("Knotenlager")
              and w.maskenrand.maske is not None and "typ2" in w.maskenrand.maske.werte(),
              w.eingaben_dock.windowTitle())
        stab = list(w.model.members)[0]
        w._baum_geklickt("stab", stab)
        check("Klick auf einen Stab lässt seine Elemente aufleuchten",
              len(w.leuchtet) == len(w.model.members[stab].elements),
              f"{len(w.leuchtet)} Elemente")
        check("und öffnet rechts die Stabmaske",
              w.eingaben_dock.windowTitle() == f"Stab {stab}" and w.sel_staebe == [stab],
              w.eingaben_dock.windowTitle())
        w.clear_selection()
        check("Auswahl aufheben löscht auch das Aufleuchten", not w.leuchtet)

        # ---- Modellbaum: Zweige, Auswahl, Masken, Neu, Loeschen ----
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        wurzel = w.baum.topLevelItem(0)
        oben = [wurzel.child(i).text(0) for i in range(wurzel.childCount())]
        check("Baum: Knoten, Linien, Stäbe, Flächen, Volumen ganz oben, ohne Geometrie/Elemente",
              oben[:5] == ["Knoten", "Linien", "Stäbe", "Flächen", "Volumen"]
              and "Geometrie" not in oben and "Elemente" not in oben, str(oben[:7]))
        kn_zweig = wurzel.child(0)
        check("alle Knoten numerisch untereinander",
              kn_zweig.childCount() == m_.nn and kn_zweig.child(0).text(0) == "K0"
              and kn_zweig.child(m_.nn - 1).text(0) == f"K{m_.nn - 1}",
              f"{kn_zweig.childCount()} Einträge")
        st_zweig = wurzel.child(2)
        check("unter Stäbe zuerst die Stäbe mit Nachweis und die Schweißnähte, dann alle Stabelemente",
              st_zweig.child(0).text(0) == "Stäbe mit Nachweis" and st_zweig.child(1).text(0) == "Schweißnähte"
              and st_zweig.childCount() == 2 + sum(1 for e in m_.elements if e.typ in ("beam", "truss")),
              f"{st_zweig.childCount()} Einträge")
        w._baum_geklickt("knoten", "Knoten")
        check("Klick auf „Knoten“ wählt alle Knoten", len(w.selection) == m_.nn
              and w.eingaben_dock.windowTitle() == "Knoten", str(len(w.selection)))
        w._baum_geklickt("knoten", "3")
        mk = w.maskenrand.maske
        check("Klick auf K3 wählt nur K3 und zeigt Nummer und Koordinaten editierbar",
              list(w.selection) == [3] and mk is not None and mk.titel == "Knoten K3"
              and abs(mk.werte()["x"] - m_.nodes[3][0]) < 1e-9, str(mk.titel if mk else None))
        x_alt = m_.nodes[3].copy()
        w._objekt_uebernehmen("knoten", "3", {"nr": 3, "x": x_alt[0] + 0.25, "y": x_alt[1], "z": x_alt[2]})
        check("Übernehmen verschiebt den Knoten", abs(m_.nodes[3][0] - x_alt[0] - 0.25) < 1e-9)
        w._objekt_uebernehmen("knoten", "3", {"nr": 3, "x": x_alt[0], "y": x_alt[1], "z": x_alt[2]})
        x5 = m_.nodes[5].copy()
        w._objekt_uebernehmen("knoten", "3", {"nr": 5, "x": x_alt[0], "y": x_alt[1], "z": x_alt[2]})
        check("eine andere Nummer tauscht die Knoten", np.allclose(m_.nodes[5], x_alt)
              and np.allclose(m_.nodes[3], x5))
        w._objekt_uebernehmen("knoten", "5", {"nr": 3, "x": x_alt[0], "y": x_alt[1], "z": x_alt[2]})
        w._baum_geklickt("staebe", "Stäbe mit Nachweis")
        check("Klick auf „Stäbe mit Nachweis“ wählt alle Stäbe", set(w.sel_staebe) == set(m_.members)
              and w.auswahlart == "Stab")
        w._baum_geklickt("linien", "Linien")
        mk = w.maskenrand.maske
        check("Klick auf „Linien“ zeigt Anzahl und Namen von … bis",
              mk is not None and mk.werte().get("anzahl") == str(len(m_.lines))
              and "…" in str(mk.werte().get("spanne", "")) or len(m_.lines) < 2,
              str(mk.werte() if mk else None))
        # Neu: Knoten mit fortlaufender Nummer, OK und Abbrechen
        n0 = m_.nn
        w._baum_neu("knoten")
        mk = w.maskenrand.maske
        check("Neu: Knoten bekommt die nächste Nummer und eine Maske mit OK und Abbrechen",
              m_.nn == n0 + 1 and mk is not None and mk.titel == f"Neu: Knoten K{n0}"
              and mk.btn_abbrechen is not None, str(mk.titel if mk else None))
        mk.abbrechen()
        app.processEvents()
        check("Abbrechen nimmt den neuen Knoten zurück", m_.nn == n0)
        w._baum_neu("knoten")
        w.maskenrand.maske.setzen("x", 1.5)
        w.maskenrand.maske.setzen("y", 2.5)
        w.maskenrand.maske.setzen("z", 0.5)
        w.maskenrand.maske.anwenden()
        app.processEvents()
        check("OK übernimmt die Koordinaten des neuen Knotens",
              m_.nn == n0 + 1 and np.allclose(m_.nodes[n0], [1.5, 2.5, 0.5]))
        # Neu: Linie mit naechstem Namen, erst mit OK angelegt
        nl0 = len(m_.lines)
        w._baum_neu("linien")
        mk = w.maskenrand.maske
        neuname = mk.werte()["name"]
        check("Neu: Linie bekommt den nächsten Namen, wird erst mit OK angelegt",
              neuname == w.model.naechster_name("L", m_.lines) and len(m_.lines) == nl0,
              neuname)
        mk.setzen("kn", f"0, {n0}")
        mk.anwenden()
        app.processEvents()
        check("OK legt die Linie an", neuname in m_.lines and m_.lines[neuname].nodes == [0, n0])
        # Umbenennen samt Verweisen
        w._objekt_uebernehmen("linie", neuname, {"name": "Lx99", "kn": f"0, {n0}", "kommentar": "Test"})
        check("Umbenennen der Linie", "Lx99" in m_.lines and neuname not in m_.lines
              and m_.lines["Lx99"].comment == "Test")
        # Loeschen mit Rueckfrage: erst Nein, dann Ja; benutzte Knoten werden abgewiesen
        antworten = []
        w._bestaetigen = lambda text: (antworten.append(text), False)[1]
        w._baum_loeschen("linie", "Lx99")
        check("Löschen fragt nach - Nein lässt die Linie stehen", "Lx99" in m_.lines and antworten)
        w._bestaetigen = lambda text: True
        w._baum_loeschen("linie", "Lx99")
        check("Ja löscht die Linie", "Lx99" not in m_.lines)
        w._baum_loeschen("knoten", str(n0))
        check("und den freien Knoten", m_.nn == n0)
        fehler = []
        fehler_alt = w.error
        w.error = lambda msg: fehler.append(str(msg))
        w._baum_loeschen("knoten", "0")
        w.error = fehler_alt
        check("ein benutzter Knoten wird mit Grund abgewiesen", m_.nn == n0 and fehler
              and "benutzt" in fehler[0], str(fehler[:1]))
        # Entf-Taste im Baum loescht den gewaehlten Eintrag (mit Rueckfrage)
        w.refresh_all()
        app.processEvents()
        stab_zweig = w.baum.topLevelItem(0).child(2).child(0)
        eintrag = stab_zweig.child(0)
        stabname = eintrag.data(0, QtCore.Qt.UserRole + 1)
        w.baum.setCurrentItem(eintrag)
        ev = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Delete, QtCore.Qt.NoModifier)
        app.sendEvent(w.baum, ev)
        app.processEvents()
        check("Entf im Baum löscht den Stab mit Nachweis (nach Rückfrage)",
              stabname not in m_.members, str(stabname))
        check("Rechtsklickmenü kennt Neu und Löschen",
              "knoten" in w.baum.NEU_ARTEN and "geoflaeche" in w.baum.LOESCH_ARTEN)
        w.undo()
        del w._bestaetigen

        # ---- Wurzel des Baums, Auswahlart Netz, Fensterauswahl, Tabellen unten ----
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        w._baum_geklickt("modell", m_.name or "Modell")
        angaben = dict(w.modellangaben())
        check("Klick auf die Wurzel zeigt rechts das Register „Modell“ mit den Angaben",
              w.eingaben_dock.windowTitle() == "Modell" and not w.tabs.isHidden()
              and angaben["Knoten"] == str(m_.nn)
              and angaben["Stäbe mit Nachweis"] == str(len(m_.members))
              and "Abmessungen" in w.lbl_modellangaben.text(),
              f"{w.eingaben_dock.windowTitle()} {angaben.get('Knoten')}")
        from statik3d.gui import symbole as symq
        check("Auswahlart als Knöpfe in der Glasleiste, auch „Netz“",
              all(f"auswahl_{a}" in w.glasleiste.knoepfe for a in w.AUSWAHLARTEN)
              and set(w.act_auswahlart) == set(w.AUSWAHLARTEN)
              and "Netz" in w.AUSWAHLARTEN and symq.hat_zeichnung("fang_netz"),
              str([k for k in w.glasleiste.knoepfe if k.startswith("auswahl_")]))
        w.auswahlart_setzen("Netz")
        check("Auswahlart Netz schaltet den Knopf, die anderen aus",
              w.auswahlart == "Netz" and w.act_auswahlart["Netz"].isChecked()
              and not w.act_auswahlart["Knoten"].isChecked())
        # Fensterauswahl: Bildpunkte der Knoten (VTK zaehlt von unten, Qt von oben)
        w.clear_selection()
        w.plotter.view_isometric()
        w.plotter.reset_camera()
        w.redraw()
        app.processEvents()
        xy, sicht = w._projizieren(m_.nodes)
        hoehe = w.plotter.render_window.GetSize()[1]

        def qt(x, y):
            return QtCore.QPoint(int(round(x)), int(round(hoehe - 1 - y)))

        w.auswahlart_setzen("Knoten")
        drei = [0, 1, 2]
        x1, y1 = xy[drei].min(axis=0) - 4
        x2, y2 = xy[drei].max(axis=0) + 4
        rect = (x1, y1, x2, y2)
        w._fenster_beginnen(qt(x1, y2))
        check("Erste Ecke (links) öffnet das Gummiband",
              w._fenster_ecke is not None and not w._gummiband.isHidden()
              and not w._gummiband.kreuzend)
        w._fenster_nachziehen(qt(x2, y1))
        w._fenster_abschliessen(qt(x2, y1))
        erwartet = set(np.where(w._im_rechteck(xy, rect) & sicht)[0].tolist())
        check("Fenster links → rechts wählt genau die Knoten, die ganz im Fenster liegen",
              set(w.selection.tolist()) == erwartet and erwartet >= set(drei)
              and w._fenster_ecke is None and w._gummiband.isHidden(),
              f"{sorted(w.selection.tolist())[:8]} statt {sorted(erwartet)[:8]}")
        # Ein schmaler Streifen quer durchs Bild: kein Stab liegt ganz darin,
        # aber viele werden angeschnitten
        w.auswahlart_setzen("Stab")
        w.clear_selection()
        xm = 0.5 * (xy[sicht, 0].min() + xy[sicht, 0].max())
        ym = 0.5 * (xy[sicht, 1].min() + xy[sicht, 1].max())
        xa, xb = xy[sicht, 0].min() - 10, xy[sicht, 0].max() + 10
        w._fenster_beginnen(qt(xa, ym + 3))
        w._fenster_abschliessen(qt(xb, ym - 3))
        n_fenster = len(w.sel_staebe)
        w._fenster_beginnen(qt(xb, ym + 3))
        w._fenster_nachziehen(qt(xa, ym - 3))
        check("rechts → links: das Gummiband ist gestrichelt (kreuzend)", w._gummiband.kreuzend)
        w._fenster_abschliessen(qt(xa, ym - 3))
        n_kreuzend = len(w.sel_staebe)
        check("Streifen links → rechts trifft keinen Stab ganz, rechts → links die angeschnittenen",
              n_fenster == 0 and n_kreuzend > 0, f"{n_fenster} / {n_kreuzend}")
        # Netz: alle Elemente im grossen Fenster, gezeichnet als eigener Darsteller
        w.auswahlart_setzen("Netz")
        w.clear_selection()
        ya, yb = xy[sicht, 1].min() - 10, xy[sicht, 1].max() + 10
        w._fenster_beginnen(qt(xa, yb))
        w._fenster_abschliessen(qt(xb, ya))
        app.processEvents()
        check("Netz: das große Fenster nimmt alle Elemente, die Auswahl wird gezeichnet",
              len(w.sel_elemente) == len(m_.elements)
              and "auswahl_elemente" in dict(w.plotter.renderer.actors),
              f"{len(w.sel_elemente)} von {len(m_.elements)}")
        w._fenster_beginnen(qt(xa, yb))
        w._fenster_abbrechen()
        check("Esc bricht das Fenster ab", w._fenster_ecke is None and w._gummiband.isHidden())
        w.clear_selection()
        check("Auswahl aufheben leert auch die Elemente", not w.sel_elemente)
        # Der untere Bereich: Gruppen, darunter die Tabellen
        tu = w.tab_unten
        check("Tabellen unten in Gruppen statt 27 Register nebeneinander",
              tu.gruppennamen() == ["Protokoll", "Modell", "Eigenschaften", "Lager", "Lasten",
                                    "Ergebnisse", "Nachweise", "Bericht"]
              and tu.count() >= 25 and "Weitere" not in tu.gruppennamen(),
              str(tu.gruppennamen()))
        check("Tabelle vorholen wechselt die Gruppe",
              w.tabelle_zeigen("Nachweise EC3") and tu.currentGroup() == "Nachweise"
              and tu.tabText(tu.currentIndex()) == "Nachweise EC3"
              and tu.currentWidget() is w.tbl_design, tu.currentGroup())
        check("Reihenfolge in der Gruppe folgt der Vorgabe",
              tu.tabellen("Modell") == ["Knoten", "Linien", "Flächen", "Volumenkörper", "Stäbe",
                                        "Schweißnähte"],
              str(tu.tabellen("Modell")))
        check("eine Gruppe mit nur einer Tabelle zeigt keine zweite Leiste",
              tu.seiten["Protokoll"].tabBar().isHidden()
              and not tu.seiten["Modell"].tabBar().isHidden())
        w.do_check()
        check("Modellprüfung holt das Protokoll nach vorn", tu.currentGroup() == "Protokoll")

        # ---- Querschnitte: Maske rechts mit Normprofilen, Parametern, freiem Editor ----
        from statik3d.gui import profilmaske as pm
        from statik3d import sections as secs
        from statik3d.model import Section as Sec
        n0 = len(m_.sections)
        w._baum_geklickt("querschnitte", "Querschnitte")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Klick auf „Querschnitte“ zeigt rechts die Querschnittsmaske",
              isinstance(mk, pm.QuerschnittMaske) and w.eingaben_dock.windowTitle() == "Neuer Querschnitt",
              w.eingaben_dock.windowTitle())
        check("Normprofile nach Art: Doppel-T, U, Hohl, T, L",
              list(mk.typknoepfe) == ["Doppel-T", "U", "Hohl", "T", "L"])
        mk.typknoepfe["T"].click()
        app.processEvents()
        check("„T“ bietet die halbierten Doppel-T (IPET, HEAT, HEBT)",
              mk.cb_reihe.currentData() == "IPET" and mk.cb_profil.count() > 10,
              f"{mk.cb_reihe.currentData()} {mk.cb_profil.count()}")
        mk.typknoepfe["Hohl"].click()
        reihen = [mk.cb_reihe.itemData(i) for i in range(mk.cb_reihe.count())]
        mk.cb_reihe.setCurrentIndex(reihen.index("CHS"))
        mk.cb_profil.setCurrentText("CHS 168.3x5")
        app.processEvents()
        check("Bild (Außen und Loch) und Kennwerte des Normprofils",
              len(mk.bild_norm.umrisse) == 2 and "A = " in mk.lbl_norm.text(), mk.lbl_norm.text()[:40])
        mk.anwenden_norm()
        app.processEvents()
        check("„Anlegen“ nimmt das Normprofil ins Modell",
              "CHS 168.3x5" in m_.sections and len(m_.sections) == n0 + 1, str(sorted(m_.sections)))
        mk = w.maskenrand.maske
        check("Maske bleibt offen und zählt die Querschnitte mit",
              isinstance(mk, pm.QuerschnittMaske) and f"{n0 + 1} Querschnitte" in mk.lbl_vorhanden.text(),
              mk.lbl_vorhanden.text() if mk else None)
        fehler = []
        fehler_alt = w.error
        w.error = lambda msg: fehler.append(str(msg))
        mk.anwenden_norm()
        w.error = fehler_alt
        check("ein doppelter Name wird abgewiesen", bool(fehler) and "gibt es schon" in fehler[0])
        mk.cb_art.setCurrentText("T geschweißt")
        app.processEvents()
        check("Parameterprofil mit Vorschau und Wpl",
              len(mk.bild_param.umrisse) == 1 and "Wpl" in mk.lbl_param.text())
        for e, v in zip(mk.par, ("200", "100", "10", "12")):
            e.setText(v)
        mk.ed_name.setText("T-Eigen")
        mk.anwenden_parameter()
        app.processEvents()
        s_ = m_.sections.get("T-Eigen")
        check("Parameterprofil T 200/100/10/12 angelegt (A = b·tf + (h−tf)·tw)",
              s_ is not None and abs(s_.A - (0.1 * 0.012 + 0.188 * 0.01)) < 1e-12)
        w.undo()
        app.processEvents()
        m_ = w.model                      # Rueckgaengig setzt eine Kopie ein
        check("Rückgängig nimmt den Querschnitt zurück", "T-Eigen" not in m_.sections)
        # Der freie Editor: drei Blechstreifen = geschweisstes I
        ed = pm.ProfilEditor(w, vorhandene=m_.sections, name="Frei")
        h_, b_, tw_, tf_ = 0.4, 0.2, 0.01, 0.016
        hw_ = h_ - 2 * tf_
        ed.setze(knoten={1: (-b_ / 2, (h_ - tf_) / 2), 2: (b_ / 2, (h_ - tf_) / 2),
                         3: (-b_ / 2, -(h_ - tf_) / 2), 4: (b_ / 2, -(h_ - tf_) / 2),
                         5: (0, -hw_ / 2), 6: (0, hw_ / 2)},
                 elemente=[(1, 2, tf_), (3, 4, tf_), (5, 6, tw_)])
        app.processEvents()
        ref = Sec.i_profile("I", h_, b_, tw_, tf_, 0.0)
        check("Editor: drei Streifen ergeben das geschweißte I (Iy exakt)",
              ed.sec is not None and abs(ed.sec.Iy - ref.Iy) < 1e-10
              and ed.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).isEnabled(), ed.lbl_werte.text()[:60])
        ed.teil_zufuegen("IPE 200", 0, (h_ / 2 + 0.1) * 1e3)
        app.processEvents()
        check("Editor: Standardprofil dazu, das Bild zeigt alle Teile",
              ed.sec.A > ref.A and len(ed.bild.umrisse) == 4, str(len(ed.bild.umrisse)))
        ed.tb_elemente.item(0, 2).setText("abc")
        app.processEvents()
        check("Editor: Fehler wird gemeldet, OK gesperrt",
              ed.sec is None and not ed.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).isEnabled(),
              ed.lbl_werte.text()[:50])
        ed.tb_elemente.item(0, 2).setText("16")
        app.processEvents()
        sec_frei = ed.ergebnis()
        check("Editor: Ergebnis trägt den Editorinhalt",
              sec_frei is not None and secs.editor_inhalt(sec_frei) is not None and sec_frei.name == "Frei")
        w._querschnitt_anlegen(sec_frei)
        app.processEvents()
        ed2 = pm.ProfilEditor(w, vorhandene=m_.sections)
        check("Editor: ein freies Profil lässt sich wieder öffnen",
              ed2.laden(m_.sections["Frei"]) and ed2.tb_knoten.rowCount() == 6
              and abs(ed2.sec.Iy - sec_frei.Iy) < 1e-12)
        w._bestaetigen = lambda text: True
        w._baum_loeschen("querschnitt", "Frei")
        app.processEvents()
        check("Baum: ein unbenutzter Querschnitt lässt sich löschen", "Frei" not in m_.sections)
        fehler = []
        w.error = lambda msg: fehler.append(str(msg))
        w._baum_loeschen("querschnitt", "IPE 500")
        w.error = fehler_alt
        del w._bestaetigen
        check("Baum: ein benutzter Querschnitt wird mit Grund abgewiesen",
              "IPE 500" in m_.sections and bool(fehler) and "benutzt" in fehler[0], str(fehler[:1]))
        check("Baum: Neu und Löschen für Querschnitte",
              "querschnitte" in w.baum.NEU_ARTEN and "querschnitt" in w.baum.LOESCH_ARTEN)
        w.maskenrand.schliessen()

        # ---- Subsysteme und Situationen ----
        from statik3d.model import GRUNDSTELLUNG as GRUND, GESAMTSYSTEM as GESAMT
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        namen = zweige(w.baum)
        check("Baum: Subsysteme mit Gesamtsystem, Situationen mit Grundstellung",
              "Subsysteme" in namen and GESAMT in namen and "Situationen" in namen
              and GRUND in namen and "+ Subsystem anlegen" in namen and "+ Situation anlegen" in namen)
        stab = list(m_.members)[0]
        w._baum_geklickt("stab", stab)
        w._baum_geklickt("subsystem_neu", "+ Subsystem anlegen")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Neu: Subsystem-Maske zeigt die Auswahl und den Haken Berührung",
              mk is not None and mk.titel == "Neu: Subsystem" and "1 Stäbe" in mk.werte()["auswahl"]
              and mk.werte()["beruehrung"] is True and "Auswahl neu lesen" in mk.zusatzknoepfe,
              str(mk.werte() if mk else None))
        mk.setzen("name", "Stiel")
        mk.anwenden()
        app.processEvents()
        sub = m_.subsysteme.get("Stiel")
        els = set(m_.members[stab].elements)
        check("OK bildet das Subsystem: Elemente des Stabs, Berührungselemente, Knoten, Lager",
              sub is not None and els <= set(sub.elemente)
              and set(sub.beruehrung) == set(sub.elemente) - els and len(sub.beruehrung) >= 1
              and sub.staebe == [stab] and sub.knoten and sub.lager, sub.bezug() if sub else None)
        check("Subsystem in der Ansicht gewählt, Maske rechts, Eintrag im Baum",
              set(w.sel_elemente) == set(sub.elemente) and set(w.selection.tolist()) == set(sub.knoten)
              and w.maskenrand.maske.titel == "Subsystem Stiel" and "Stiel" in zweige(w.baum))
        w._baum_geklickt("subsystem", GESAMT)
        app.processEvents()
        check("Gesamtsystem wählt alles", len(w.sel_elemente) == len(m_.elements))
        w._baum_geklickt("subsystem", "Stiel")
        w.maskenrand.maske.setzen("name", "Stiel A")
        w.maskenrand.maske.anwenden()
        app.processEvents()
        check("Subsystem umbenennen", "Stiel A" in m_.subsysteme and "Stiel" not in m_.subsysteme)
        fehler = []
        w.error = lambda msg: fehler.append(str(msg))
        w._bestaetigen = lambda text: True
        w._baum_loeschen("subsystem", GESAMT)
        check("Gesamtsystem lässt sich nicht löschen", bool(fehler) and "Gesamtsystem" in fehler[0])
        w._baum_loeschen("subsystem", "Stiel A")
        app.processEvents()
        check("Subsystem löschen, Rückgängig holt es zurück", "Stiel A" not in m_.subsysteme
              and (w.undo() or True) and "Stiel A" in w.model.subsysteme)
        m_ = w.model
        # Stellung (Maske rechts): der Riegel wirkt nicht - ohne ihn bleibt die
        # Halle stabil (die Stiele stehen unten eingespannt), ohne Stiel nicht
        from statik3d.gui import masken as msk_
        stab = "Riegel"
        els = set(m_.members[stab].elements)
        w._baum_geklickt("stellung_neu", "+ Stellung anlegen")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Neu: Stellung-Maske rechts: Bezeichnung, Ausgangsstellung, Verschiebung, Verdrehung, "
              "deaktivierte Stäbe/Flächen/Volumen/Gelenke/Lager - mehr nicht",
              isinstance(mk, msk_.Maske) and mk.titel.startswith("Neu: Stellung")
              and {"name", "basis", "dx", "dy", "dz", "winkel", "ax", "ay", "az", "px", "py", "pz",
                   "staebe_aus", "flaechen_aus", "koerper_aus", "gelenke_aus", "lager_aus",
                   "linienlager_aus", "flaechenlager_aus"} <= set(mk.werte())
              and "beschreibung" not in mk.werte() and "faelle" not in mk.werte()
              and set(mk.zusatzknoepfe) == {"Auswahl deaktivieren", "Auswahl aktivieren", "Alle aktivieren"},
              str(sorted(mk.werte())))
        w.clear_selection()
        w.sel_staebe = [stab]
        mk.zusatzknoepfe["Auswahl deaktivieren"].click()
        app.processEvents()
        check("„Auswahl deaktivieren“: Stab in der Liste, seine Elemente im Bild ausgeblendet",
              stab in w._namensliste(mk.werte()["staebe_aus"]) and set(w.versteckt["elemente"]) == els,
              mk.werte()["staebe_aus"])
        mk.setzen("name", "ohne Riegel")
        mk.anwenden()
        app.processEvents()
        st = w.model.stellung("ohne Riegel")
        check("OK legt die Stellung an (Stab deaktiviert), Eintrag im Baum, ihre Maske bleibt offen und "
              "zeigt die Stellung ohne den Stab",
              st is not None and st.staebe_aus == [stab] and set(w.versteckt["elemente"]) == els
              and any("ohne Riegel" in t for t in zweige(w.baum))
              and w.maskenrand.maske.titel == "Stellung ohne Riegel", str((st, len(w.versteckt["elemente"]))))
        w.maskenrand.schliessen()
        app.processEvents()
        check("Maske zu: Sicht wieder hergestellt", not w.versteckt["elemente"], str(len(w.versteckt["elemente"])))
        m_ = w.model
        w._baum_geklickt("stellung_neu", "+ Stellung anlegen")
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("name", "hoch"); mk.setzen("basis", "ohne Riegel"); mk.setzen("dz", 0.5); mk.setzen("winkel", 10.0)
        mk.anwenden()
        app.processEvents()
        st2 = w.model.stellung("hoch")
        check("Stellung mit Ausgangsstellung, Verschiebung und Verdrehung",
              st2 is not None and st2.basis == "ohne Riegel" and st2.verschiebung == (0.0, 0.0, 0.5)
              and st2.dreh_winkel == 10.0 and st2.winkel == 10.0, str(st2))
        m_ = w.model
        wurzel_ = w.baum.topLevelItem(0)
        oben_ = [wurzel_.child(i).text(0) for i in range(wurzel_.childCount())]
        check("Baum: Subsysteme vor Stellungen vor Situationen",
              oben_.index("Subsysteme") < oben_.index("Stellungen") < oben_.index("Situationen"), str(oben_))
        # Situation: nur noch Stellung + Lastfaelle/Kombinationen
        w._baum_geklickt("situation_neu", "+ Situation anlegen")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Neu: Situation-Maske: Stellung, Lastfälle, Kombinationen - keine Deaktivierung mehr",
              mk.titel == "Neu: Situation" and mk.werte()["stellung"].startswith("–")
              and {"lastfaelle", "kombinationen"} <= set(mk.werte()) and "aus" not in mk.werte()
              and set(mk.zusatzknoepfe) == {"Alle Lastfälle und Kombinationen"}, str(sorted(mk.werte())))
        mk.setzen("name", "ohne Stiel"); mk.setzen("stellung", "ohne Riegel")
        mk.anwenden()
        app.processEvents()
        sit = m_.situationen.get("ohne Stiel")
        check("OK legt die Situation an: Stellung zugeordnet, Elemente der Stellung ohne Wirkung",
              sit is not None and sit.stellung == "ohne Riegel" and not w.versteckt["elemente"]
              and "ohne Stiel" in zweige(w.baum)
              and set(np.where(~m_.aktive_elemente("ohne Stiel"))[0]) == els, str(sit))
        d = dg.LoadCaseDialog(w, existing=list(m_.load_cases), situationen=m_.situationsnamen())
        check("Lastfalldialog bietet die Situationen",
              [d.situation.itemText(i) for i in range(d.situation.count())] == [GRUND, "ohne Stiel"])
        d.situation.setCurrentText("ohne Stiel")
        d.name.setText("LFS")
        name, cat, desc, grp = d.values()
        m_.add_load_case(name, cat, desc, exclusive_group=grp)
        m_.load_cases[name].situation = d.situation_name()
        m_.load_node(0, Fz=-1e3, case="LFS")
        w.refresh_all()
        app.processEvents()
        check("Lastfall trägt die Situation (Tabelle unten, Baum)",
              m_.load_cases["LFS"].situation == "ohne Stiel"
              and any("ohne Stiel" in str(z) for z in w.tbl_lastfall.modell.zeilen)
              and any("ohne Stiel" in t for t in zweige(w.baum)))
        dk = dg.CombinationDialog(w, m_)
        dk.situation.setCurrentText("ohne Stiel")
        check("Kombinationsdialog sperrt Lastfälle anderer Situationen",
              not dk.factors["LF1"].isEnabled() and dk.factors["LFS"].isEnabled())
        dk.factors["LFS"].set(1.35)
        dk.name.setText("KS")
        ck = dk.result()
        check("Kombination trägt die Situation", ck.situation == "ohne Stiel" and ck.factors == {"LFS": 1.35})
        m_.combinations["KS"] = ck
        # Eine Umhuellende (Alternativen aus RFEM): der Dialog sperrt die
        # Faktoren und gibt die Alternativen unveraendert zurueck
        from statik3d.model import Combination as _Komb
        m_.combinations["EK"] = _Komb("EK", {}, "ULS", alternativen=[{"LF1": 1.0}, {"LF1": 1.35}],
                                      bemessungssituation="GZT")
        de = dg.CombinationDialog(w, m_, m_.combinations["EK"])
        check("Kombinationsdialog: bei einer Umhüllenden sind die Faktoren gesperrt",
              not de.factors["LF1"].isEnabled() and not de.factors["LFS"].isEnabled())
        ce = de.result()
        check("und die Alternativen bleiben erhalten",
              ce.alternativen == [{"LF1": 1.0}, {"LF1": 1.35}] and ce.factors == {}
              and ce.bemessungssituation == "GZT", str(ce.alternativen))
        an_ = solver.solve_all(m_)
        w._solve_done("all", an_)
        app.processEvents()
        check("Ergebnisliste zeigt die Umhüllende der Kombination",
              any(w.cb_result.itemText(i) == "Umhüllende EK" for i in range(w.cb_result.count())),
              str([w.cb_result.itemText(i) for i in range(w.cb_result.count())][:6]))
        for i in range(w.cb_result.count()):
            if w.cb_result.itemText(i).endswith("LFS"):
                w.cb_result.setCurrentIndex(i)
                break
        app.processEvents()
        r_ = w.current_result()
        check("Ergebnis der Situation: Elemente der Stellung ohne Schnittgrößen, im Bild weggelassen",
              r_ is not None and r_.info.get("situation") == "ohne Stiel"
              and all(np.allclose(r_.beam_end[i], 0) for i in els)
              and set(r_.info.get("inaktiv", [])) == els, str(r_.name if r_ else None))
        w._baum_geklickt("situation", "ohne Stiel")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Situation zeigen: Maske nennt Lastfall und Kombination, Elemente der Stellung ausgeblendet",
              mk.titel == "Situation ohne Stiel" and "LFS" in mk.werte()["lastfaelle"]
              and "KS" in mk.werte()["kombinationen"] and set(w.versteckt["elemente"]) == els,
              str((mk.werte()["lastfaelle"], mk.werte()["kombinationen"])))
        mk.setzen("kombinationen", "")
        mk.anwenden()
        app.processEvents()
        check("Übernehmen: nicht mehr genannte Kombination fällt in die Grundstellung zurück, Sicht wieder da",
              m_.combinations["KS"].situation == "" and m_.load_cases["LFS"].situation == "ohne Stiel"
              and not w.versteckt["elemente"])
        fehler.clear()
        w._baum_loeschen("stellung", "ohne Riegel")
        check("eine benutzte Stellung wird abgewiesen", bool(fehler) and "benutzt" in fehler[0]
              and m_.stellung("ohne Riegel") is not None, str(fehler[:1]))
        fehler.clear()
        w._baum_loeschen("situation", "ohne Stiel")
        check("eine benutzte Situation wird abgewiesen", bool(fehler) and "benutzt" in fehler[0]
              and "ohne Stiel" in m_.situationen, str(fehler[:1]))
        w._baum_loeschen("situation", GRUND)
        check("die Grundstellung lässt sich nicht löschen", len(fehler) == 2 and "Grundstellung" in fehler[1])
        w._baum_loeschen("stellung", "hoch")
        check("eine freie Stellung lässt sich löschen", w.model.stellung("hoch") is None and len(fehler) == 2)
        m_ = w.model
        w.error = fehler_alt
        del w._bestaetigen
        check("Modellangaben nennen Subsysteme, Situationen, Stellungen",
              dict(w.modellangaben())["Situationen"] == "2" and dict(w.modellangaben())["Subsysteme"] == "2"
              and dict(w.modellangaben())["Stellungen"] == "1")
        w.maskenrand.schliessen()

        # ---- Knicklaengen aus der Knickfigur ----
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        beta_alt = {k: (mem.beta_y, mem.beta_z) for k, mem in m_.members.items()}
        w.knicklaengen = None
        rueck = w.do_knicklaengen()
        # Ohne Knickergebnis laeuft das Verzweigungsproblem im Hintergrund -
        # am Drehlager blockierte es sonst das Fenster ueber fuenf Minuten
        t0_ = time.time()
        while w.worker is not None and w.worker.isRunning() and time.time() - t0_ < 120:
            app.processEvents()
            time.sleep(0.05)
        app.processEvents()
        erg = getattr(w, "knicklaengen", None)
        check("Knicklängen: ohne Knickergebnis rechnet der Worker, nicht das Fenster",
              rueck is None and w.worker is not None and erg is not None,
              f"Rueckgabe {rueck!r}, Worker {w.worker is not None}")
        check("Knicklängen: Verzweigungsproblem gelöst und je Stab ausgewertet",
              erg is not None and set(erg.staebe) == set(m_.members)
              and w.results is not None and getattr(w.results, "buckling_modes", None) is not None
              and len(w.tbl_knick.modell.zeilen) == len(m_.members), str(erg.summary() if erg else None))
        check("Knicklängen: Tabelle vorn, Eintrag im Baum, Hinweis im Protokoll",
              w.tab_unten.tabText(w.tab_unten.currentIndex()) == "Knicklängen"
              and any("Knicklängen" in t for t in zweige(w.baum)))
        beteiligt = [k for k, v in erg.staebe.items() if v.beteiligt and (v.beta_y or v.beta_z)]
        w.knicklaengen_uebernehmen()
        app.processEvents()
        check("β übernehmen schreibt nur beteiligte Stäbe",
              bool(beteiligt) and all((m_.members[k].beta_y, m_.members[k].beta_z) != beta_alt[k]
                                      for k in beteiligt)
              and all((m_.members[k].beta_y, m_.members[k].beta_z) == beta_alt[k]
                      for k in m_.members if k not in beteiligt), str(beteiligt))
        w.undo()
        app.processEvents()
        check("Rückgängig stellt die β wieder her",
              all((w.model.members[k].beta_y, w.model.members[k].beta_z) == beta_alt[k]
                  for k in beta_alt))
        w.ergebnis_zeigen("nachweis:knicklaengen")
        check("Baumklick holt die Knicklängen-Tabelle", w.tab_unten.tabText(w.tab_unten.currentIndex()) == "Knicklängen")

        # ---- Theorie je Lastfall / Kombination ----
        w.load_example("frame")
        app.processEvents()
        m_ = w.model
        d = dg.LoadCaseDialog(w, existing=list(m_.load_cases), situationen=m_.situationsnamen())
        check("Lastfalldialog bietet die Theorie I, II, III",
              [d.theorie.itemData(i) for i in range(d.theorie.count())] == ["", "I", "II", "III"])
        d.theorie.setCurrentIndex(3)
        check("Theorie III wählbar", d.theorie_name() == "III")
        lf = list(m_.load_cases)[0]
        m_.load_cases[lf].theorie = "III"
        dk = dg.CombinationDialog(w, m_)
        dk.theorie.setCurrentIndex(2)
        dk.factors[lf].set(1.35)
        dk.name.setText("K2")
        ck = dk.result()
        check("Kombinationsdialog setzt die Theorie", ck.theorie == "II")
        m_.combinations["K2"] = ck
        w.refresh_all()
        app.processEvents()
        def zusaetze(baum):
            out = []

            def lauf(it):
                out.append(it.text(1))
                for i in range(it.childCount()):
                    lauf(it.child(i))
            for i in range(baum.topLevelItemCount()):
                lauf(baum.topLevelItem(i))
            return out
        check("Theorie steht in Tabelle und Baum",
              any("III" in str(z) for z in w.tbl_lastfall.modell.zeilen)
              and any("II" in str(z) for z in w.tbl_kombi.modell.zeilen)
              and any("III. O." in t for t in zusaetze(w.baum)))
        an_ = solver.solve_all(m_)
        w._solve_done("all", an_)
        app.processEvents()
        check("Lastfall nach Theorie III. Ordnung gerechnet, Kombination nach II.",
              an_.cases[lf].info.get("theorie") == "III. Ordnung"
              and an_.theorie3 is not None and lf in an_.theorie3.kombinationen
              and an_.theorie2 is not None and "K2" in an_.theorie2.kombinationen
              and "Theorie III" in w.txt_summary.toPlainText(),
              str(an_.cases[lf].info.get("theorie")))
        m_.load_cases[lf].theorie = ""
        m_.combinations["K2"].theorie = ""

        # ---- Lastgenerierer Wasserdruck ----
        from statik3d.model import ShellProp as ShP, Flaeche as Fl
        from statik3d.report.html import Report as Rep
        w.new_model()
        m_ = w.model
        m_.add_material(Material("S"))
        m_.add_shell_prop(ShP("t", 0.012))
        nx_, nz_, b_, h_ = 6, 20, 3.0, 5.0
        ids_ = [[m_.add_node(0.0, i * b_ / nx_, k * h_ / nz_) for k in range(nz_ + 1)] for i in range(nx_ + 1)]
        el_ = [m_.add_element("shell4", [ids_[i][k], ids_[i + 1][k], ids_[i + 1][k + 1], ids_[i][k + 1]], "S", "t")
               for i in range(nx_) for k in range(nz_)]
        m_.flaechen["Haut"] = Fl("Haut", dicke="t", material="S", elemente=el_)
        for k in range(nz_ + 1):
            m_.fix(ids_[0][k], "all")
            m_.fix(ids_[nx_][k], "all")
        w.refresh_all()
        app.processEvents()
        check("Baum: Lastgenerierer mit „+ Wasserdruck anlegen“",
              "Lastgenerierer" in zweige(w.baum) and "+ Wasserdruck anlegen" in zweige(w.baum))
        w.sel_flaechen = ["Haut"]
        w._baum_geklickt("wasserdruck_neu", "+")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Wasserdruck-Maske mit der gewählten Fläche und den Knöpfen (Anklicken, Kennwerte)",
              mk.titel == "Neu: Wasserdruck" and "Haut" in mk.werte()["ziele"]
              and set(mk.zusatzknoepfe) == {"Auswahl übernehmen", "Benetzt anklicken", "Dichtlinie anklicken",
                                            "OW-Fläche anklicken", "UW-Fläche anklicken", "Kennwerte"},
              str(sorted(mk.zusatzknoepfe)))
        check("Maske kennt Verfahren, Lastfall-Nr., Referenzflächen mit Seite, Sohle und Gitter",
              all(k in mk.werte() for k in ("verfahren", "fall_nr", "ow_flaeche", "ow_seite", "uw_flaeche",
                                             "uw_seite", "z_sohle", "gitter", "unterdruck"))
              and str(mk.werte()["verfahren"]).startswith("strömungsnumerisch")
              and int(mk.werte()["fall_nr"]) >= 1, str(mk.werte().get("verfahren")))
        # Klickmodus: Dichtlinie anklicken -> Linienklick geht an die Maske
        m_.add_line("Dicht", [ids_[0][0], ids_[nx_][0]])
        mk.zusatzknoepfe["Dichtlinie anklicken"].click()
        app.processEvents()
        check("Klickmodus Dichtlinie an (Maske will Linien)", w.maskenrand.objekt_modus() == "linie")
        mk.objekt_angeklickt("linie", "Dicht")
        app.processEvents()
        check("angeklickte Linie wird Dichtlinie und ist markiert",
              "Dicht" in mk.werte()["dichtung"] and w.sel_linien == ["Dicht"], str(mk.werte().get("dichtung")))
        mk.zusatzknoepfe["Dichtlinie anklicken"].click()
        app.processEvents()
        check("Klickmodus wieder aus", w.maskenrand.objekt_modus() == "")
        mk.setzen("h_ow", 4.0)
        mk.setzen("richtung", "global x")
        mk.setzen("absenkung", False)
        mk.setzen("fall_nr", 5)
        mk.zusatzknoepfe["Kennwerte"].click()
        app.processEvents()
        check("Kennwerte in der Maske: F = ½ρgh²b = 235,4 kN aus dem Druckfeld (numerisch)",
              "235.4 kN" in mk.werte()["kennwerte"] and "numerisch" in mk.werte()["kennwerte"],
              mk.werte()["kennwerte"])
        fortschritt_ = []
        alt_fort = w._fortschritt
        w._fortschritt = lambda wert, text: (fortschritt_.append(wert), alt_fort(wert, text))[1]
        mk.anwenden()
        app.processEvents()
        w._fortschritt = alt_fort
        wd_ = m_.wasserdruecke.get("W1")
        check("„Lasten erzeugen“: Generierer, Lastfall Nr. 5, Objektlast mit Druckfeld, Elementlasten nur unter Wasser",
              wd_ is not None and wd_.lastfall in m_.load_cases and m_.load_cases[wd_.lastfall].nummer == 5
              and any(gl.verlauf.get("art") == "wasser" and gl.verlauf.get("feld")
                      for gl in m_.load_cases[wd_.lastfall].geometrielasten)
              and len(m_.load_cases[wd_.lastfall].face_loads) == 6 * 16 and "W1" in zweige(w.baum),
              str(len(m_.load_cases[wd_.lastfall].face_loads) if wd_ else None))
        check("Fortschrittsbalken lief mit und ist wieder weg",
              fortschritt_ and max(fortschritt_) == 100 and not w.progress_bar.isVisible(), str(fortschritt_[-3:]))
        check("Lastfälle-Tabelle zeigt die Nummer",
              any(str(z[0]) == wd_.lastfall and z[1] == 5 for z in w.tbl_lastfall.modell.zeilen))
        # Abbruch: Modell bleibt unveraendert
        w._baum_geklickt("wasserdruck_neu", "+")
        app.processEvents()
        mk2 = w.maskenrand.maske
        mk2.setzen("name", "Wabbruch")
        mk2.setzen("h_ow", 3.0)
        w.sel_flaechen = ["Haut"]
        mk2.zusatzknoepfe["Auswahl übernehmen"].click()
        w._fortschritt = lambda wert, text: False
        mk2.anwenden()
        app.processEvents()
        w._fortschritt = alt_fort
        check("Abbrechen während der Strömungsberechnung lässt das Modell unverändert",
              "Wabbruch" not in m_.wasserdruecke and not w.progress_bar.isVisible()
              and "abgebrochen" in w.log.toPlainText())
        w._baum_geklickt("wasserdruck", "W1")
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("h_ow", 6.0)
        mk.setzen("ueber", True)
        mk.setzen("unter", True)
        mk.setzen("spalt", 0.4)
        mk.setzen("cp_dyn", 0.2)
        mk.setzen("absenkung", True)
        mk.anwenden()
        app.processEvents()
        wd_ = m_.wasserdruecke["W1"]
        check("Ändern: überströmt, unterströmt, Druckschwankung als eigener Lastfall",
              wd_.ueberstroemt and wd_.unterstroemt and wd_.lastfall_dyn in m_.load_cases
              and len(m_.wasserdruecke) == 1, str(list(m_.load_cases)))
        bl_ = Rep(m_, None).chapter_lastgenerierer()
        check("Bericht: Kapitel Lastgenerierer mit Tabelle, Erläuterung (Poleni, Potentialströmung), Druckfeld und Skizze",
              any(x[0] == "table" for x in bl_) and sum(1 for x in bl_ if x[0] == "figure" and "<svg" in x[1]) >= 2
              and any(x[0] == "p" and "Poleni" in x[1] for x in bl_)
              and any(x[0] == "p" and "Potentialströmung" in x[1] for x in bl_), str([x[0] for x in bl_]))
        w._bestaetigen = lambda text: True
        w._baum_loeschen("wasserdruck", "W1")
        app.processEvents()
        check("Löschen entfernt den Generierer samt Lasten",
              "W1" not in m_.wasserdruecke
              and not any(getattr(f, "_geo", False) for lc in m_.load_cases.values() for f in lc.face_loads))
        del w._bestaetigen
        w.undo()
        app.processEvents()
        check("Rückgängig holt den Generierer zurück", "W1" in w.model.wasserdruecke)

        # ---- Lastgenerierer Wind ----
        w.new_model()
        m_ = w.model
        m_.add_material(Material("S"))
        m_.add_shell_prop(ShP("t", 0.01))
        bq, dq, hq, nq = 8.0, 5.0, 6.0, 4

        def quaderflaeche(name, ecken, aussen):
            P0, P1, _P2, P3 = map(lambda a: np.asarray(a, float), ecken)
            u_, v_ = P1 - P0, P3 - P0
            if float(np.cross(u_, v_) @ np.asarray(aussen, float)) < 0:
                u_, v_ = v_, u_
            ids2 = [[m_.add_node(*(P0 + u_ * i / nq + v_ * k / nq)) for k in range(nq + 1)] for i in range(nq + 1)]
            el2 = [m_.add_element("shell4", [ids2[i][k], ids2[i + 1][k], ids2[i + 1][k + 1], ids2[i][k + 1]], "S", "t")
                   for i in range(nq) for k in range(nq)]
            m_.flaechen[name] = Fl(name, dicke="t", material="S", elemente=el2)
        quaderflaeche("Luv", [(0, 0, 0), (0, bq, 0), (0, bq, hq), (0, 0, hq)], (-1, 0, 0))
        quaderflaeche("Lee", [(dq, 0, 0), (dq, bq, 0), (dq, bq, hq), (dq, 0, hq)], (1, 0, 0))
        quaderflaeche("Seite1", [(0, 0, 0), (dq, 0, 0), (dq, 0, hq), (0, 0, hq)], (0, -1, 0))
        quaderflaeche("Seite2", [(0, bq, 0), (dq, bq, 0), (dq, bq, hq), (0, bq, hq)], (0, 1, 0))
        quaderflaeche("Dach", [(0, 0, hq), (dq, 0, hq), (dq, bq, hq), (0, bq, hq)], (0, 0, 1))
        w.refresh_all()
        app.processEvents()
        check("Baum: „+ Wind anlegen“ unter Lastgenerierer", "+ Wind anlegen" in zweige(w.baum))
        w.sel_flaechen = ["Luv", "Lee", "Seite1", "Seite2", "Dach"]
        w._baum_geklickt("wind_neu", "+")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Wind-Maske mit den gewählten Flächen und den Knöpfen",
              mk.titel == "Neu: Wind" and "Luv" in mk.werte()["ziele"] and "Dach" in mk.werte()["ziele"]
              and set(mk.zusatzknoepfe) == {"Auswahl übernehmen", "Kennwerte"}, str(mk.werte().get("ziele")))
        check("Wind-Maske kennt Verfahren (Norm/Windkanal), Schnitt, Gitter, Reynolds, Schritte, Lastfall-Nr.",
              all(k in mk.werte() for k in ("verfahren", "schnittart", "z_schnitt", "gitter", "re", "schritte",
                                             "fall_nr"))
              and str(mk.werte()["verfahren"]).startswith("Norm"), str(mk.werte().get("verfahren")))
        mk.setzen("zone", "Zone 2 (v_b,0 = 25 m/s)")
        mk.setzen("profil", "Binnenland")
        mk.setzen("richtung", "+x")
        mk.zusatzknoepfe["Kennwerte"].click()
        app.processEvents()
        kwt = mk.werte()["kennwerte"]
        check("Kennwerte in der Maske: v_b = 25 m/s, q_b = ½·1,25·25² = 391 N/m², h/d = 1,2 → c_pe,D = +0,80",
              "v_b = 25.0 m/s" in kwt and "q_b = 391 N/m²" in kwt and "c_pe,D = +0.80" in kwt, kwt)
        mk.anwenden()
        app.processEvents()
        wd_ = m_.winde.get("Wind1")
        lc_ = m_.load_cases.get(wd_.lastfall) if wd_ else None
        check("„Lasten erzeugen“: Generierer, Lastfall W, fünf Objektlasten, Elementlasten auf allen Flächen",
              wd_ is not None and lc_ is not None and lc_.category == "W"
              and sum(1 for gl in lc_.geometrielasten if gl.verlauf.get("art") == "wind") == 5
              and len(lc_.face_loads) == 5 * nq * nq and "Wind1" in zweige(w.baum),
              str((wd_ and wd_.lastfall, lc_ and lc_.category, lc_ and len(lc_.face_loads))))
        w._baum_geklickt("wind", "Wind1")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Wind-Maske zum Bearbeiten vorbelegt",
              mk.titel == "Wind Wind1" and mk.werte()["profil"] == "Binnenland" and mk.werte()["richtung"] == "+x",
              str((mk.titel, mk.werte()["profil"], mk.werte()["richtung"])))
        # Windkanal aus der Maske: kleines Gitter, wenige Schritte, Fortschritt
        mk.setzen("verfahren", w.WINDVERFAHREN[1])
        mk.setzen("gitter", 8)
        mk.setzen("schritte", 200)
        mk.setzen("re", 80.0)
        fort_ = []
        alt_fort = w._fortschritt
        w._fortschritt = lambda wert, text: (fort_.append(wert), alt_fort(wert, text))[1]
        mk.anwenden()
        app.processEvents()
        w._fortschritt = alt_fort
        wd_ = m_.winde.get("Wind1")
        lc_ = m_.load_cases.get(wd_.lastfall) if wd_ else None
        check("Windkanal aus der Maske: Generierer mit Verfahren, Lasten mit c_p-Feld an den Wänden, Fortschritt lief",
              wd_ is not None and wd_.windkanal() and lc_ is not None
              and sum(1 for gl in lc_.geometrielasten if gl.verlauf.get("feld")) == 4
              and fort_ and max(fort_) == 100 and "Windkanal" in w.log.toPlainText(),
              str((wd_ and wd_.verfahren, lc_ and sum(1 for gl in lc_.geometrielasten if gl.verlauf.get("feld")),
                   fort_[-2:])))
        w._baum_geklickt("wind", "Wind1")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Wind-Maske zeigt den Windkanal vorbelegt", str(mk.werte()["verfahren"]).startswith("numerisch")
              and int(mk.werte()["gitter"]) == 8)
        mk.setzen("verfahren", w.WINDVERFAHREN[0])
        mk.setzen("richtung", "Winkel [°] von +x")
        mk.setzen("winkel", 90.0)
        mk.setzen("c_pi", -0.3)
        mk.anwenden()
        app.processEvents()
        wd_ = m_.winde["Wind1"]
        check("Ändern: Anströmung unter 90° (+y), Innendruck c_pi",
              abs(wd_.richtung[1] - 1.0) < 1e-9 and abs(wd_.c_pi + 0.3) < 1e-12 and len(m_.winde) == 1,
              str((wd_.richtung, wd_.c_pi)))
        bl_ = Rep(m_, None).chapter_lastgenerierer()
        check("Bericht: Wind mit Tabellen, Erläuterung (Basiswindgeschwindigkeit) und Skizze",
              sum(1 for x in bl_ if x[0] == "table") >= 2 and any(x[0] == "figure" and "<svg" in x[1] for x in bl_)
              and any(x[0] == "p" and "Basiswindgeschwindigkeit" in x[1] for x in bl_), str([x[0] for x in bl_]))
        w._bestaetigen = lambda text: True
        w._baum_loeschen("wind", "Wind1")
        app.processEvents()
        check("Löschen entfernt den Wind samt Lasten",
              "Wind1" not in m_.winde
              and not any(gl.verlauf.get("art") == "wind" for lc in m_.load_cases.values() for gl in lc.geometrielasten)
              and not any(getattr(f, "_geo", False) for lc in m_.load_cases.values() for f in lc.face_loads))
        del w._bestaetigen
        w.undo()
        app.processEvents()
        check("Rückgängig holt den Wind zurück", "Wind1" in w.model.winde)

        # ---- Schwingungsnachweis des Verschlusses ----
        w.new_model()
        m_ = w.model
        m_.add_material(Material("S"))
        m_.add_shell_prop(ShP("t", 0.012))
        nx_, nz_, b_, h_ = 6, 20, 3.0, 5.0
        ids_ = [[m_.add_node(0.0, i * b_ / nx_, k * h_ / nz_) for k in range(nz_ + 1)] for i in range(nx_ + 1)]
        el_ = [m_.add_element("shell4", [ids_[i][k], ids_[i + 1][k], ids_[i + 1][k + 1], ids_[i][k + 1]], "S", "t")
               for i in range(nx_) for k in range(nz_)]
        m_.flaechen["Haut"] = Fl("Haut", dicke="t", material="S", elemente=el_)
        for k in range(nz_ + 1):
            m_.fix(ids_[0][k], "all")
            m_.fix(ids_[nx_][k], "all")
        w.refresh_all()
        app.processEvents()
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w.maske_schwingung()
        app.processEvents()
        check("Schwingung ohne Wasserdruck: Hinweis statt Maske", bool(fehler_) and "Wasserdruck" in fehler_[-1])
        w.sel_flaechen = ["Haut"]
        w._baum_geklickt("wasserdruck_neu", "+")
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("h_ow", 4.0)
        mk.setzen("richtung", "global x")
        mk.setzen("unter", True)
        mk.setzen("spalt", 0.3)
        mk.setzen("cp_dyn", 0.1)
        mk.anwenden()
        app.processEvents()
        w.maske_schwingung()
        app.processEvents()
        mk = w.maskenrand.maske
        check("Schwingungs-Maske mit dem Wasserdruck W1 vorbelegt",
              mk.titel == "Neu: Schwingungsnachweis" and mk.werte()["wasserdruck"] == "W1", str(mk.werte().get("wasserdruck")))
        mk.setzen("n_moden", 3)
        mk.setzen("d_kante", "0.2")
        mk.setzen("betriebsstunden", 500.0)
        mk.anwenden()
        app.processEvents()
        erg_ = w.schwingung
        check("„Nachweis führen“: 3 Moden nass/trocken, Angaben im Modell, Tabelle Schwingung, Eigenformen im Wasser",
              erg_ is not None and len(erg_.moden) == 3 and all(x.f_wasser < x.f_luft for x in erg_.moden)
              and m_.schwingungen["Schwingung1"].d_kante == 0.2
              and len(w.tbl_schwing.modell.zeilen) == 3 and w.tab_unten.currentGroup() == "Nachweise"
              and getattr(w.results, "modes", None) is not None and "Wasser" in w.results.name,
              str(fehler_[1:] or (erg_ and erg_.summary())))
        check("Schwingung im Baum unter Nachweise", any("Schwingung Verschluss" in z for z in zweige(w.baum)))
        w.maske_schwingung()
        app.processEvents()
        mk = w.maskenrand.maske
        check("Schwingungs-Maske zum Bearbeiten vorbelegt",
              mk.titel == "Schwingung Schwingung1" and mk.werte()["d_kante"] == "0.2", str(mk.werte().get("d_kante")))
        an_ = w.analysis if w.analysis is not None else solver.Analysis(m_)
        an_.schwingung = erg_
        bl_ = Rep(m_, an_).chapter_schwingung()
        check("Bericht: Kapitel Schwingungsnachweis mit drei Tabellen, Erläuterung und Frequenzbild",
              sum(1 for x in bl_ if x[0] == "table") == 3 and any(x[0] == "figure" and "<svg" in x[1] for x in bl_)
              and any(x[0] == "p" and "Westergaard" in x[1] for x in bl_), str([x[0] for x in bl_]))
        w.error = alt_error

        # ---- Klick in der Ansicht: Fangradius, Objekt unter dem Zeiger, Auswahlfenster ----
        from statik3d.model import Member as Mb
        from PySide6 import QtCore
        w.new_model()
        m_ = w.model
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        k0 = m_.add_node(0, 0, 0)
        k1 = m_.add_node(4, 0, 0)
        k2 = m_.add_node(4, 3, 0)
        e0 = m_.add_element("beam", [k0, k1], mat_, sec_)
        e1 = m_.add_element("beam", [k1, k2], mat_, sec_)
        m_.members["S1"] = Mb("S1", elements=[e0])
        m_.members["S2"] = Mb("S2", elements=[e1])
        w.refresh_all()
        w.blickrichtung("+z")
        w.zoom_alles()
        app.processEvents()
        s_ = w._pixelmass()
        h_qt = w.plotter.interactor.height()

        def klick_bei(x, y):
            """Linksklick an der VTK-Anzeigeposition (x, y) nachstellen."""
            w.plotter.iren.interactor.SetEventInformation(int(round(x)), int(round(y)))
            w._letzter_klick = QtCore.QPoint(int(round(x / s_)), int(round(h_qt - 1 - y / s_)))
            w._picked(None)
            app.processEvents()

        def px(P):
            xy, _ = w._projizieren(np.atleast_2d(P))
            return float(xy[0, 0]), float(xy[0, 1])

        xv, yv = w._qt_nach_vtk(QtCore.QPoint(10, 20))
        check("Qt-Bildpunkt → VTK-Anzeigepunkt: x·s, (h−y−1)·s",
              abs(xv - round(10 * s_)) < 1e-9 and abs(yv - round((h_qt - 21) * s_)) < 1e-9
              and abs(w._fangradius() - 14 * s_) < 1e-9, str((xv, yv, s_)))
        w.auswahlart_setzen("Knoten")
        w.selection = np.array([], int)
        x_, y_ = px(m_.nodes[k1])
        klick_bei(x_ + 5, y_ + 3)
        check("Klick 5 Bildpunkte neben dem Knoten trifft ihn", k1 in w.selection, str(w.selection))
        w.selection = np.array([], int)
        x_, y_ = px(0.5 * (m_.nodes[k0] + m_.nodes[k1]) + [0.6, 0, 0])
        klick_bei(x_, y_ + 4)
        check("Klick auf die Stabachse in Auswahlart Knoten wählt den Stab, Auswahlart folgt",
              w.auswahlart == "Stab" and w.sel_staebe == ["S1"], str((w.auswahlart, w.sel_staebe)))
        w.auswahlart_setzen("Netz")
        w.sel_elemente = []
        x_, y_ = px(0.5 * (m_.nodes[k1] + m_.nodes[k2]))
        w.plotter.iren.interactor.SetEventInformation(int(round(x_ + 4)), int(round(y_)))
        check("Netz: Stabelement 4 Bildpunkte neben der Linie gefunden", w._element_am_zeiger() == e1,
              str(w._element_am_zeiger()))
        klick_bei(x_ + 4, y_)
        check("… und der Klick wählt es (Elementnummer in der Anzeige)", w.sel_elemente == [e1], str(w.sel_elemente))
        w.auswahlart_setzen("Knoten")
        w.selection = np.array([], int)
        w.sel_staebe = []
        xy_, _ = w._projizieren(m_.nodes)
        xa, ya = float(xy_[:, 0].min()) - 40, float(xy_[:, 1].min()) - 40
        xb, yb = float(xy_[:, 0].max()) + 40, float(xy_[:, 1].max()) + 40
        w.selection = np.array([k0], int)
        klick_bei(xa, ya)
        check("kurzer Klick ins Leere hebt die Auswahl auf und beginnt kein Fenster (16.09.2026)",
              w._fenster_ecke is None and len(w.selection) == 0,
              f"Fenster {w._fenster_ecke}, Auswahl {w.selection}")
        qt_ = lambda x, y: QtCore.QPoint(int(round(x / s_)), int(round(h_qt - 1 - y / s_)))
        w._fenster_beginnen(qt_(xa, ya))
        w._fenster_abschliessen(qt_(xb, yb))
        check("das Auswahlfenster durch Ziehen fasst alle drei Knoten",
              w._fenster_ecke is None and sorted(int(i) for i in w.selection) == [k0, k1, k2], str(w.selection))
        w.selection = np.array([], int)
        w.auswahlart_setzen("Stab")
        w.sel_staebe = []
        xm_, ym_ = px(0.5 * (m_.nodes[k0] + m_.nodes[k1]))
        w._fenster_beginnen(qt_(xm_ + 30, ym_ + 30))     # gezogen, nicht geklickt (16.09.2026)
        w._fenster_abschliessen(qt_(xm_ - 30, ym_ - 30))
        check("kreuzendes Fenster (rechts nach links) über der Stabmitte wählt den Stab",
              w.sel_staebe == ["S1"], str(w.sel_staebe))
        P_ = w._weltpunkt(int(round(xm_ / s_)), int(round(h_qt - 1 - ym_ / s_)))
        check("Weltpunkt unter dem Qt-Punkt (Gerätepixel-Umrechnung) liegt auf der Stabmitte",
              P_ is not None and np.linalg.norm(P_[:2] - [2.0, 0.0]) < 0.3, str(P_))
        w.auswahlart_setzen("Knoten")
        w.sel_staebe = []
        w.sel_elemente = []

        # ---- Schweißnähte und Kerbfälle ----
        w.new_model()
        m_ = w.model
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        k0 = m_.add_node(0, 0, 0)
        k1 = m_.add_node(4, 0, 0)
        k2 = m_.add_node(8, 0, 0)
        e0 = m_.add_element("beam", [k0, k1], mat_, sec_)
        e1 = m_.add_element("beam", [k1, k2], mat_, sec_)
        m_.members["S1"] = Mb("S1", elements=[e0])
        m_.members["S2"] = Mb("S2", elements=[e1])
        w.refresh_all()
        app.processEvents()
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        check("Baum: Zweig Schweißnähte mit „+ Schweißnaht anlegen“",
              "Schweißnähte" in zweige(w.baum) and "+ Schweißnaht anlegen" in zweige(w.baum))
        w.sel_staebe = ["S1"]
        w._baum_geklickt("schweissnaht_neu", "+")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Schweißnaht-Maske mit dem gewählten Stab und den Knöpfen",
              mk.titel == "Neu: Schweißnaht" and "S1" in mk.werte()["ziele"]
              and set(mk.zusatzknoepfe) == {"Auswahl übernehmen", "Kerbfall ermitteln"}, str(mk.werte().get("ziele")))
        mk.setzen("art", "Kehlnaht")
        mk.setzen("lage", "quer")
        mk.setzen("l", 90.0)
        mk.setzen("t", 40.0)
        mk.zusatzknoepfe["Kerbfall ermitteln"].click()
        app.processEvents()
        kft = mk.werte()["kerbfall"]
        check("„Kerbfall ermitteln“: Kehlnaht quer ℓ = 90 → 63·(25/40)^0,2 = 57 N/mm², Δτ 80, Tab. 8.5",
              "57 N/mm²" in kft and "Δτ_C = 80" in kft and "8.5" in kft, kft)
        mk.anwenden()
        app.processEvents()
        ks_ = (25.0 / 40.0) ** 0.2
        check("„Übernehmen“: Naht im Modell, Kerbfall im Stab S1, S2 ohne; Tabelle Schweißnähte (Gruppe Modell)",
              "Naht1" in m_.schweissnaehte and m_.schweissnaehte["Naht1"].staebe == ["S1"]
              and abs(m_.members["S1"].detail_category - 63e6 * ks_) < 1 and m_.members["S2"].detail_category is None
              and len(w.tbl_naht.modell.zeilen) == 1 and w.tab_unten.currentGroup() == "Modell"
              and "Naht1" in zweige(w.baum), str(fehler_))
        w.sel_staebe = []
        w.maske_schweissnaht()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("art", "Stumpfnaht")
        mk.setzen("lage", "quer")
        mk.setzen("geprueft", True)
        mk.setzen("aequivalent", True)
        mk.anwenden()
        app.processEvents()
        check("äquivalente Naht ohne Zuordnung: S2 bekommt 90, S1 behält den ungünstigeren Wert",
              "Naht2" in m_.schweissnaehte and abs(m_.members["S2"].detail_category - 90e6) < 1
              and abs(m_.members["S1"].detail_category - 63e6 * ks_) < 1, str(fehler_))
        w._baum_geklickt("schweissnaht", "Naht1")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Schweißnaht-Maske zum Bearbeiten vorbelegt",
              mk.titel == "Schweißnaht Naht1" and mk.werte()["lage"] == "quer" and float(mk.werte()["l"]) == 90.0)
        bl_ = Rep(m_, None).chapter_system()
        check("Bericht: Tabellen „Schweißnähte“ und „Kerbfälle der Stäbe“ im Kapitel System",
              any(x[0] == "table" and x[2] == "Schweißnähte" for x in bl_)
              and any(x[0] == "table" and "Kerbfälle der Stäbe" in x[2] for x in bl_))
        w._bestaetigen = lambda text: True
        w._baum_loeschen("schweissnaht", "Naht1")
        app.processEvents()
        check("Löschen der Einzelnaht: S1 bekommt die äquivalente Naht (90)",
              "Naht1" not in m_.schweissnaehte and abs(m_.members["S1"].detail_category - 90e6) < 1)
        w._baum_loeschen("schweissnaht", "Naht2")
        app.processEvents()
        check("Löschen der letzten Naht: kein Kerbfall mehr in den Stäben",
              not m_.schweissnaehte and m_.members["S1"].detail_category is None)
        w.undo()
        app.processEvents()
        check("Rückgängig holt die Naht zurück (Schnappschuss vor dem Löschen)",
              "Naht2" in w.model.schweissnaehte)
        k3 = w.model.add_node(0, 3, 0)          # freier Knoten (kein Element haengt daran)
        nn0 = w.model.nn
        w._baum_loeschen("knoten", str(k3))
        app.processEvents()
        check("freien Knoten löschen", w.model.nn == nn0 - 1, str((nn0, w.model.nn, fehler_[-1:])))
        w.undo()
        app.processEvents()
        check("Rückgängig: Knoten wieder da (Schnappschuss vor dem Löschen)", w.model.nn == nn0, str(w.model.nn))
        del w._bestaetigen
        w.error = alt_error

        # ---- Vor dem Rechnen: unvernetzte Geometrie und Teiltragwerke ohne Lager ----
        w.new_model()
        m_ = w.model
        m_.netz.teilung_uebersteuern = False
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        k0 = m_.add_node(0, 0, 0)
        k1 = m_.add_node(2, 0, 0)
        k2 = m_.add_node(0, 3, 0)
        k3 = m_.add_node(2, 3, 0)
        m_.add_element("beam", [k0, k1], mat_, sec_)
        m_.add_element("beam", [k2, k3], mat_, sec_)
        m_.fix(k0, "all")
        m_.load_node(k1, Fz=-1000.0)
        m_.load_node(k3, Fz=-1000.0)     # auf dem ungelagerten Teil
        w.refresh_all()
        app.processEvents()
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        # Ein Teiltragwerk ohne Lager wird nicht mehr abgewiesen: das Programm
        # fragt, haelt die freien Bewegungen fest und weist danach aus, welche
        # Last in welcher Bewegung ins Nichts geht.
        gefragt_ = []
        w._fragen = lambda titel, text: (gefragt_.append(text), False)[1]
        w.do_solve("case")
        app.processEvents()
        check("„Berechnen“ bei einem Teiltragwerk ohne Lager: Rückfrage mit Knoten "
              "statt Solver-Abbruch",
              bool(gefragt_) and "Teiltragwerk" in gefragt_[-1] and "K2" in gefragt_[-1]
              and (w.worker is None or not w.worker.isRunning()), str(gefragt_[-1:])[:160])
        check("„Nein“ bricht ab und schreibt den Fehler ins Protokoll",
              "Teiltragwerk" in w.log.toPlainText(), "")
        w._fragen = lambda titel, text: True
        w.do_solve("case")
        t0_ = time.time()
        while w.worker is not None and w.worker.isRunning() and time.time() - t0_ < 120:
            app.processEvents()
            time.sleep(0.02)
        app.processEvents()
        sing_ = w.singularitaeten()
        check("„Ja“ rechnet trotzdem und nennt die freien Bewegungen",
              w.analysis is not None and len(sing_) == 6, f"{len(sing_)} Bewegungen")
        check("die Bewegung des ungelagerten Stabes trägt die Last, die ins Nichts geht",
              any(abs(x.kraft - 1000.0) < 1e-6 for x in sing_),
              "; ".join(f"{x.kraft:.1f} N" for x in sing_))
        check("und sie stehen im Modellbaum unter „Ergebnisse“",
              "Freie Bewegungen" in w._ergebnisliste(), str(list(w._ergebnisliste())))
        w.bewegung_zeigen(0)
        app.processEvents()
        check("ein Klick stellt die Bewegung in die Ansicht",
              any(str(nm).startswith("result_singular")
                  for nm in dict(w.plotter.renderer.actors)),
              str([nm for nm in dict(w.plotter.renderer.actors) if "singular" in str(nm)]))
        del w._fragen
        m_.fix(k2, "all")
        # Flaeche ohne Netz: Rueckfrage, Vernetzen, dann rechenbar
        for i, (a, b) in enumerate([(k0, k1), (k1, k3), (k3, k2), (k2, k0)]):
            m_.add_line(f"L{i + 1}", [a, b])
        f_ = m_.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke=list(m_.shells)[0],
                            material=mat_, teilung=[4, 4])
        fragen_ = []
        w._fragen = lambda titel, text: (fragen_.append(text), False)[1]
        check("Vor dem Rechnen: Fläche ohne Netz → Rückfrage; „Nein“ bricht ab",
              w._vor_rechnung_vernetzen() is False and fragen_ and "1 Flächen" in fragen_[-1], str(fragen_[-1:])[:120])
        w._fragen = lambda titel, text: True
        check("„Ja“ vernetzt die Fläche und gibt die Berechnung frei",
              w._vor_rechnung_vernetzen() is True and len(m_.flaechen["F1"].elemente or []) == 16
              and not [x for x in m_.check() if x.startswith("FEHLER")], str(len(m_.flaechen["F1"].elemente or [])))
        del w._fragen
        w.error = alt_error

        # ---- Messen und Bemaßen (Register Messen) ----
        w.new_model()
        m_ = w.model
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        k0 = m_.add_node(0, 0, 0)
        k1 = m_.add_node(4, 0, 0)
        k2 = m_.add_node(4, 3, 0)
        e0 = m_.add_element("beam", [k0, k1], mat_, sec_)
        e1 = m_.add_element("beam", [k1, k2], mat_, sec_)
        m_.members["S1"] = Mb("S1", elements=[e0])
        m_.members["S2"] = Mb("S2", elements=[e1])
        w.refresh_all()
        w.blickrichtung("+z")
        w.zoom_alles()
        app.processEvents()
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))

        def akteure():
            return list(w.plotter.renderer.actors)

        check("Ribbon-Register „Messen“ vorhanden", "Messen" in w.ribbon._register)
        w.messen("abstand")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Messmaske sammelt zwei Punkte statt Knoten",
              mk.titel == "Abstand messen" and mk.punkte and mk.n_knoten == 2 and w.maskenrand.will_punkte())
        w.maskenrand.punkt_angeklickt([0, 0, 0])
        w.maskenrand.punkt_angeklickt([3, 4, 0])
        app.processEvents()
        check("Abstand 3-4-5: Messung 5.000 m mit Δx/Δy, orange gezeichnet, Maske für die nächste Messung geleert",
              bool(w.messungen) and w.messungen[0]["text"].startswith("Abstand 5.000 m") and "Δx 3.000 m" in w.messungen[0]["text"]
              and "messung" in akteure() and any(a.startswith("messung_text") for a in akteure())
              and not mk.gewaehlt_punkte and "5.000 m" in mk.werte()["ergebnis"], str(w.messungen[:1]))
        nn0 = m_.nn
        xy_, _ = w._projizieren(np.atleast_2d(m_.nodes[k2]))
        w.plotter.iren.interactor.SetEventInformation(int(round(xy_[0, 0])), int(round(xy_[0, 1])))
        w._picked(None)
        app.processEvents()
        check("Klick auf Knoten K2 gibt der Messmaske den Punkt, ohne einen Knoten anzulegen",
              len(mk.gewaehlt_punkte) == 1 and np.allclose(mk.gewaehlt_punkte[0], [4, 3, 0]) and m_.nn == nn0,
              str((mk.gewaehlt_punkte, m_.nn)))
        w.messungen_loeschen()
        app.processEvents()
        check("„Messungen löschen“ nimmt sie aus der Ansicht", not w.messungen and "messung" not in akteure())
        w.messen("winkel")
        app.processEvents()
        for p_ in ([4, 0, 0], [0, 0, 0], [0, 3, 0]):
            w.maskenrand.punkt_angeklickt(p_)
        app.processEvents()
        check("Winkelmessung 90°", bool(w.messungen) and w.messungen[-1]["text"].startswith("Winkel 90.00°"))
        w.sel_staebe = ["S1", "S2"]
        t_ = w.messen_auswahl()
        check("Länge der gewählten Stäbe 4 + 3 = 7 m", bool(t_) and "Länge gesamt 7.0000 m" in t_, str(t_))
        w.bemassung_neu("linear")
        app.processEvents()
        w.maskenrand.punkt_angeklickt([0, 0, 0])
        w.maskenrand.punkt_angeklickt([4, 0, 0])
        app.processEvents()
        b_ = m_.bemassungen.get("M1")
        check("Linearmaß M1: Versatzrichtung aus der Blickrichtung festgehalten, gezeichnet, im Modellbaum",
              b_ is not None and b_.art == "linear" and b_.richtung is not None
              and abs(np.linalg.norm(b_.richtung) - 1) < 1e-9 and abs(float(np.dot(b_.richtung, [1, 0, 0]))) < 1e-9
              and "bemassung" in akteure() and any(a.startswith("bemassung_text") for a in akteure())
              and "M1" in zweige(w.baum) and "Bemaßungen" in zweige(w.baum), str((b_, fehler_)))
        w.bemassung_neu("hoehenkote")
        app.processEvents()
        w.maskenrand.punkt_angeklickt([4, 3, 2.5])
        app.processEvents()
        check("Höhenkote M2 z = 2.500 m", "M2" in m_.bemassungen and m_.bemassungen["M2"].bezug() == "Höhenkote z = 2.500 m")
        w.bemassung_neu("kette")
        app.processEvents()
        mk = w.maskenrand.maske
        for p_ in ([0, 0, 0], [2, 0, 0], [4, 0, 0]):
            w.maskenrand.punkt_angeklickt(p_)
        mk.anwenden()
        app.processEvents()
        check("Maßkette M3 mit „Anwenden“ abgeschlossen: 2 Glieder", "M3" in m_.bemassungen and "2 Glieder" in m_.bemassungen["M3"].bezug())
        w.bemassung_bearbeiten("M1")
        app.processEvents()
        mk = w.maskenrand.maske
        r0 = list(m_.bemassungen["M1"].richtung)
        mk.setzen("text", "L")
        mk.setzen("umkehren", True)
        mk.setzen("einheit", "cm")
        mk.anwenden()
        app.processEvents()
        b_ = m_.bemassungen["M1"]
        check("Bemaßung bearbeiten: Text, Einheit, Versatz umgekehrt",
              b_.text == "L" and b_.einheit == "cm" and np.allclose(b_.richtung, -np.array(r0)))
        w.bemassung_einstellungen()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("einheit", "mm")
        mk.setzen("nachkomma", 0)
        mk.anwenden()
        app.processEvents()
        e_ = m_.bemassung_einstellungen()
        check("Einstellungen übernommen: mm, 0 Nachkommastellen", e_.einheit == "mm" and e_.nachkomma == 0)
        import json as _json
        from statik3d.model import Model as _Modell
        m2_ = _Modell.from_dict(_json.loads(_json.dumps(m_.to_dict())))
        check("Bemaßungen und Einstellungen werden gespeichert",
              sorted(m2_.bemassungen) == ["M1", "M2", "M3"] and m2_.bemassung_einstellung.einheit == "mm")
        w._bestaetigen = lambda text: True
        w._baum_loeschen("bemassung", "M2")
        app.processEvents()
        check("Löschen über den Modellbaum", "M2" not in m_.bemassungen)
        w.undo()
        app.processEvents()
        check("Rückgängig holt M2 zurück", "M2" in w.model.bemassungen)
        w.bemassung_loeschen(None)
        app.processEvents()
        check("„Letzte Bemaßung löschen“ entfernt M3", "M3" not in w.model.bemassungen)
        w.bemassungen_alle_loeschen()
        app.processEvents()
        check("„Alle Bemaßungen löschen“", not w.model.bemassungen and "bemassung" not in akteure())
        del w._bestaetigen
        w.error = alt_error

        # ---- Fortschrittsbalken beim Vernetzen, Abbrechen ----
        w.new_model()
        m_ = w.model
        m_.netz.teilung_uebersteuern = False
        mat_ = list(m_.materials)[0]
        t_ = list(m_.shells)[0]
        for k in range(3):
            y0 = 3.0 * k
            ids_ = [m_.add_node(0, y0, 0), m_.add_node(2, y0, 0), m_.add_node(2, y0 + 2, 0), m_.add_node(0, y0 + 2, 0)]
            for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
                m_.add_line(f"L{k}{i}", [ids_[a], ids_[b]])
            m_.add_flaeche(f"F{k}", [f"L{k}{i}" for i in range(4)], dicke=t_, material=mat_, teilung=[4, 4])
        w.refresh_all()
        app.processEvents()
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w._bestaetigen = lambda text: True
        werte_ = []
        alt_setvalue = w.progress_bar.setValue
        w.progress_bar.setValue = lambda v: (werte_.append(int(v)), alt_setvalue(v))
        w.sel_flaechen = []
        w.geometrie_vernetzen()
        app.processEvents()
        check("Vernetzen: Balken nach Aufwand in Promille (0 … 1000, steigend), danach aus und wieder unbestimmt",
              werte_ and werte_[0] == 0 and werte_[-1] == 1000 and werte_ == sorted(werte_)
              and len(set(werte_)) >= 4 and not w.progress_bar.isVisible()
              and w.progress_bar.maximum() == 0 and all(len(m_.flaechen[f"F{k}"].elemente) == 16 for k in range(3)),
              str(werte_))
        check("Abbrechen-Knopf in der Statuszeile, nach dem Lauf versteckt",
              getattr(w, "btn_abbrechen", None) is not None and not w.btn_abbrechen.isVisible())
        for k in range(3):
            m_.flaechen[f"F{k}"].elemente = []
        werte_.clear()

        def setv_(v):
            alt_setvalue(v)
            werte_.append(int(v))
            if int(v) > 0 and not w._abbruch:       # nach der ersten Fläche
                w._fortschritt_abbrechen()
        w.progress_bar.setValue = setv_
        w.geometrie_vernetzen()
        app.processEvents()
        n_el = [len(m_.flaechen[f"F{k}"].elemente or []) for k in range(3)]
        check("Abbrechen nach der ersten Fläche: eine vernetzt, zwei ohne Netz, Protokoll nennt den Abbruch",
              n_el[0] == 16 and n_el[1] == 0 and n_el[2] == 0 and "abgebrochen" in w.log.toPlainText()
              and not w.progress_bar.isVisible() and not w._abbruch, str(n_el))
        w.progress_bar.setValue = alt_setvalue
        del w._bestaetigen
        w.error = alt_error

        # ---- Rechts nur Modellinformation; Ribbon Netz: Vernetzen, Netzeinstellungen, Generator-Masken ----
        w.new_model()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w._bestaetigen = lambda text: True

        def tab_():
            return w.tabs.tabText(w.tabs.currentIndex())

        check("Nach „Neues Modell“ steht rechts nichts - kein Register, keine Projektangaben",
              w.rechts_zeigt() == "leer" and not w.rechts_leer.isHidden(), w.rechts_zeigt())
        w.maske_zeigen("Netz")
        check("Ein Ribbon-Befehl holt sein Register nach vorn", w.rechts_zeigt() == "Netz", w.rechts_zeigt())
        w.clear_selection()
        app.processEvents()
        check("Auswahl aufheben ohne offene Maske lässt rechts nichts stehen (kein Netz-Panel)",
              w.rechts_zeigt() == "leer", w.rechts_zeigt())
        w._baum_geklickt("modell", m_.name or "Modell")
        check("Klick auf die Wurzel des Modellbaums holt die Projektangaben (Register „Modell“)",
              w.rechts_zeigt() == "Modell" and not w.tabs.isHidden(), w.rechts_zeigt())
        w.clear_selection()
        app.processEvents()
        check("… und ein Klick ins Leere nimmt sie wieder weg", w.rechts_zeigt() == "leer", w.rechts_zeigt())
        check("Ribbon Netz: Vernetzen, Netzeinstellungen; Generatoren als Masken - keine Netzvorschau mehr",
              all(hasattr(w, a) for a in ("geometrie_vernetzen", "maske_netzeinstellungen",
                                          "maske_stabzug", "maske_platte", "maske_quader"))
              and not hasattr(w, "netz_vorschau"))
        w.maske_platte()
        app.processEvents()
        mk = w.maskenrand.maske
        check("Offene Maske: rechts steht nur sie, die Register darunter sind weg",
              w.rechts_zeigt() == "maske" and w.tabs.isHidden() and w.rechts_leer.isHidden(),
              w.rechts_zeigt())
        mk.setzen("lx", 2.0)
        mk.setzen("ly", 1.0)
        mk.setzen("nx", 2)
        mk.setzen("ny", 1)
        mk.anwenden()
        app.processEvents()
        check("Platte-Maske erzeugt 2 Viereckelemente", len(m_.elements) == 2 and all(e.typ == "shell4" for e in m_.elements), str(fehler_))
        w.maske_stabzug()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("z1", 1.0)
        mk.setzen("x2", 3.0)
        mk.setzen("z2", 1.0)
        mk.setzen("n", 3)
        mk.anwenden()
        app.processEvents()
        check("Stabzug-Maske erzeugt 3 Balken und einen Stab mit Nachweis",
              sum(1 for e in m_.elements if e.typ == "beam") == 3 and len(m_.members) == 1, str(fehler_))
        w.maske_quader()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("nx", 1)
        mk.setzen("ny", 1)
        mk.setzen("nz", 1)
        mk.setzen("z0", 3.0)
        mk.anwenden()
        app.processEvents()
        check("Quader-Maske erzeugt einen Hexaeder", sum(1 for e in m_.elements if e.typ == "hex8") == 1, str(fehler_))
        w.maske_zeigen("Lastfälle")
        check("Ein Ribbon-Register löst die offene Maske ab",
              not w.maskenrand.offen() and w.rechts_zeigt() == "Lastfälle", w.rechts_zeigt())
        w.maske_quader()
        app.processEvents()
        w.maskenrand.schliessen()
        w.clear_selection()
        app.processEvents()
        check("Maske geschlossen, nichts gewählt: rechts nichts (keine Projektangaben)",
              w.rechts_zeigt() == "leer", w.rechts_zeigt())
        w.new_model()
        m_ = w.model
        mat_ = list(m_.materials)[0]
        t_ = list(m_.shells)[0]
        ids_ = [m_.add_node(0, 0, 0), m_.add_node(4, 0, 0), m_.add_node(4, 2, 0), m_.add_node(0, 2, 0)]
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            m_.add_line(f"L{i}", [ids_[a], ids_[b]])
        f_ = m_.add_flaeche("F1", ["L0", "L1", "L2", "L3"], dicke=t_, material=mat_, teilung=[2, 2])
        w.refresh_all()
        app.processEvents()
        w.maske_netzeinstellungen()
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("dichte", "eigene")
        mk.setzen("ziellaenge", 500)          # Maske in mm
        mk.setzen("h_min", "100")
        mk.setzen("intelligent", False)
        mk.setzen("form", "Dreiecke")
        check("Netzeinstellungen: kein Vorschau-Knopf und kein Vorschau-Feld mehr",
              "Vorschau" not in mk.zusatzknoepfe and "vorschau" not in mk._felder)
        # Vernetzer und Nachbesserung zur Auswahl; was fehlt, steht als "nicht installiert" dabei
        from statik3d import vernetzer_extern as vx_
        da_ = vx_.verfuegbar()
        wahl_v = [mk._felder["vernetzer"].itemText(i) for i in range(mk._felder["vernetzer"].count())]
        check("Netzeinstellungen: Auswahl Vernetzer (eigener, gmsh, Netgen) und Nachbesserung (MMG3D)",
              len(wahl_v) == 3 and wahl_v[0].startswith("eigener") and "nachbessern" in mk._felder
              and "mmg_pfad" not in mk._felder          # kein Pfadfeld: wo mmg3d_O3 liegt, weiss das Programm
              and all(("nicht installiert" in wahl_v[i]) != da_[k][1] for i, k in ((1, "gmsh"), (2, "netgen"))),
              str(wahl_v))
        if da_["gmsh"][1]:
            mk.setzen("vernetzer", wahl_v[1])
        mk.anwenden()
        app.processEvents()
        if da_["gmsh"][1]:
            check("Vernetzer gmsh übernommen (steht in der Netzbeschreibung)",
                  m_.netz.vernetzer == "gmsh" and "gmsh" in m_.netz.beschreibung(), m_.netz.beschreibung()[-60:])
            m_.netz.vernetzer = "eigener"
        w.maske_netzeinstellungen(); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("nachbessern", "MMG3D (nicht installiert)" if not da_["mmg3d"][1] else "keine")
        fehler_n = []
        alt_error = w.error
        w.error = lambda msg: fehler_n.append(str(msg))
        mk.anwenden(); app.processEvents()
        w.error = alt_error
        check("eine nicht installierte Nachbesserung wird abgewiesen, das Modell bleibt",
              (bool(fehler_n) and "nicht installiert" in fehler_n[0]) if not da_["mmg3d"][1] else not fehler_n,
              str(fehler_n[:1]))
        # --- Stabmaske: Knoten, Laenge, Querschnitt mit Massen und Kennwerten, Werkstoff -----
        w.load_example("hall"); app.processEvents()          # Hallenrahmen: Staebe mit Nachweis
        ms_ = w.model
        stabname_ = next(iter(ms_.members))
        w._objektmaske("stab", stabname_); app.processEvents()
        mk_s = w.maskenrand.maske
        qs_ = mk_s._felder["qs_info"].text()
        kn_ = mk_s._felder["knoten"].text()
        mem_s = ms_.members[stabname_]
        sec_s = ms_.sections[ms_.elements[mem_s.elements[0]].sec]
        check("Stabmaske nennt Knoten (Anfang → Ende mit Koordinaten) und Länge",
              kn_.startswith("K") and "→" in kn_ and " m" in kn_ and " m (" in mk_s._felder["laenge"].text(),
              kn_[:80] + " | " + mk_s._felder["laenge"].text())
        check("… den Querschnitt mit Bezeichnung, Maßen in mm und Kennwerten in cm-Einheiten",
              qs_.startswith(sec_s.name) and "mm)" in qs_ and "A " in qs_ and "cm²" in qs_ and "I_y" in qs_ and "cm⁴" in qs_
              and f"h {sec_s.h * 1e3:g}" in qs_, qs_[:120])
        check("… und den Werkstoff mit E und f_y",
              "E " in mk_s._felder["mat_info"].text() and "GPa" in mk_s._felder["mat_info"].text()
              and "f_y" in mk_s._felder["mat_info"].text(), mk_s._felder["mat_info"].text()[:80])
        w.new_model(); app.processEvents()

        # --- Knoten der Konstruktion gegen Netzknoten (Ribbon Netz -> Netzknoten) ---------
        w.new_model(); app.processEvents()
        mk_ = w.model
        mk_.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0.], [3, 0, 0.5]]))
        for i_, (a_, b_) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            mk_.add_line(f"L{i_ + 1}", [a_, b_])
        fk_ = mk_.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke=list(mk_.shells)[0],
                              material=list(mk_.materials)[0], teilung=[6, 3])
        w._vernetzen([fk_], [])
        w.act_knoten.setChecked(True); w.act_edges.setChecked(True); w.act_netzknoten.setChecked(False)
        w.refresh_all(); app.processEvents()

        def n_punkte_(name):
            akt = w.plotter.renderer.actors
            return akt[name].GetMapper().GetInput().GetNumberOfPoints() if name in akt else 0

        check("„Knoten“ zeigt die Konstruktion: die 5 gesetzten Knoten, nicht die Netzknoten der Fläche; Netz → Netzknoten ist aus",
              mk_.nn > 5 and n_punkte_("knoten") + n_punkte_("knoten_frei") == 5 and n_punkte_("netzknoten") == 0
              and not w.act_netzknoten.isChecked(),
              f"nn {mk_.nn}, knoten {n_punkte_('knoten')} + frei {n_punkte_('knoten_frei')}, netz {n_punkte_('netzknoten')}")
        _P, T_ = w._nummernmarken(mk_, "Knoten")
        check("Knotennummern nummerieren die gezeigten Knoten: 0 bis 4", sorted(T_, key=int) == ["0", "1", "2", "3", "4"], str(T_))
        w.act_netzknoten.setChecked(True); app.processEvents()
        check("Netz → Netzknoten an: alle übrigen Knoten als Netzknoten-Punkte, die Konstruktion bleibt bei 5",
              n_punkte_("netzknoten") == mk_.nn - 5 and n_punkte_("knoten") + n_punkte_("knoten_frei") == 5,
              f"netz {n_punkte_('netzknoten')} von {mk_.nn}")
        _P, T_ = w._nummernmarken(mk_, "Knoten")
        check("… und die Knotennummern nehmen die Netzknoten dazu (alle)", len(T_) == mk_.nn, f"{len(T_)} von {mk_.nn}")
        w.act_edges.setChecked(False); app.processEvents()
        check("FE-Netz aus: die Netzknoten verschwinden mit dem Netz, der Schalter bleibt an",
              n_punkte_("netzknoten") == 0 and w.act_netzknoten.isChecked())
        # --- FE-Netz aus: auch die Hervorhebung ohne Elementkanten (15.09.2026:
        # „wenn Netz ausgeschaltet, dann auch nicht anzeigen, wenn Volumen oder
        # Fläche selektiert ist oder aufleuchtet") ---
        w.sel_flaechen = ["F1"]; w.redraw(); app.processEvents()
        hv_ = dict(w.plotter.renderer.actors).get("auswahl_elemente")
        check("FE-Netz aus: die gewählte Fläche leuchtet ohne Elementkanten",
              hv_ is not None and not hv_.GetProperty().GetEdgeVisibility(),
              "kein Darsteller" if hv_ is None else f"Kanten {hv_.GetProperty().GetEdgeVisibility()}")
        w.act_edges.setChecked(True); w.redraw(); app.processEvents()
        hv_ = dict(w.plotter.renderer.actors).get("auswahl_elemente")
        check("… FE-Netz an: mit Elementkanten",
              hv_ is not None and bool(hv_.GetProperty().GetEdgeVisibility()))
        w.act_edges.setChecked(False); app.processEvents()
        w._hover_zeichnen(("Fläche", "F1"), [int(e) for e in fk_.elemente]); app.processEvents()
        ho_ = dict(w.plotter.renderer.actors).get("hover")
        check("… und beim Überfahren mit der Maus ebenso ohne Kanten",
              ho_ is not None and not ho_.GetProperty().GetEdgeVisibility(),
              "kein Darsteller" if ho_ is None else f"Kanten {ho_.GetProperty().GetEdgeVisibility()}")
        w.plotter.remove_actor("hover", render=False); w.sel_flaechen = []
        w.act_edges.setChecked(True); w.act_netzknoten.setChecked(False); app.processEvents()

        # --- Flaechenlasten als Flaeche erkennbar: durchscheinende Lastflaeche an den Pfeilenden ---
        mk_.add_geometrielast("F1", 5000.0, "flaeche")
        w.refresh_all(); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        n_pat = akt_["flaechenlasten"].GetMapper().GetInput().GetNumberOfCells() if "flaechenlasten" in akt_ else 0
        check("Flächenlast auf F1: eine durchscheinende Lastfläche (Vielecke der Fläche), nicht nur Pfeile",
              n_pat >= 1 and "loads" in akt_ and abs(akt_["flaechenlasten"].GetProperty().GetOpacity() - 0.3) < 1e-6,
              f"{n_pat} Vielecke")
        w.act_loads.setChecked(False); app.processEvents()
        check("Lasten aus: auch die Lastfläche ist weg", "flaechenlasten" not in dict(w.plotter.renderer.actors))
        w.act_loads.setChecked(True)
        mk_.case().geometrielasten.clear(); w.refresh_all(); app.processEvents()
        w.load_example("plate"); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        n_fl = len(w.model.case().face_loads)
        check("Elementweise Flächenlasten (Platte): je belastete Elementseite ein Vieleck der Lastfläche",
              "flaechenlasten" in akt_ and akt_["flaechenlasten"].GetMapper().GetInput().GetNumberOfCells() == n_fl > 0,
              f"{n_fl} Lasten")
        # zurueck zur vernetzten Platte mk_ - der naechste Block loest sie
        w.model = mk_; w.analysis = None; w.results = None; w.refresh_all(); app.processEvents()

        # --- Netzkanten 1 px, Transparent mit Ergebnis deckender und ohne Drahtnetz ---------
        for i_ in (0, 3):
            mk_.fix(i_, "all")
        mk_.load_node(1, Fz=-1000.0)
        w._solve_done("case", solver.solve_static(mk_)); app.processEvents()
        w.cb_field.setCurrentText("Vergleichsspannung"); app.processEvents()
        w.darstellung_setzen("Voll"); w.act_edges.setChecked(True); w.cb_undeformed.setChecked(True); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        pr_ = akt_["result_netz"].GetProperty() if "result_netz" in akt_ else None
        check("Schalennetz mit Ergebnis: Elementkanten 1 px breit (vorher 3 px, gemessen 3-4 px im Bild)",
              pr_ is not None and abs(pr_.GetLineWidth() - 1.0) < 1e-6 and bool(pr_.GetEdgeVisibility()),
              str(pr_.GetLineWidth() if pr_ else None))
        w.darstellung_setzen("Transparent"); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        pr_ = akt_["result_netz"].GetProperty() if "result_netz" in akt_ else None
        check("Transparent mit Ergebnis: Deckkraft 0,55 statt 0,35; das unverformte System nur als Umriss, kein Drahtnetz",
              pr_ is not None and abs(pr_.GetOpacity() - 0.55) < 1e-6
              and "undeformed_netz" in akt_ and akt_["undeformed_netz"].GetProperty().GetRepresentation() != 1,
              f"{pr_.GetOpacity() if pr_ else None}, undeformed {'undeformed_netz' in akt_}")
        w.darstellung_setzen("Voll"); app.processEvents()
        w.new_model(); app.processEvents()
        mm_ = w.model
        mm_.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0.], [3, 0, 0], [5, 0, 0.]]))
        for i_, (a_, b_) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            mm_.add_line(f"L{i_ + 1}", [a_, b_])
        fm_ = mm_.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke=list(mm_.shells)[0],
                              material=list(mm_.materials)[0], teilung=[2, 2])
        w._vernetzen([fm_], [])
        mm_.add_element("beam", [4, 5], list(mm_.materials)[0], list(mm_.sections)[0])
        w.darstellung_setzen("Hidden-Line"); w.act_edges.setChecked(True); w.refresh_all(); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        check("Stab und Schalen zusammen: zwei Darsteller - Schalennetz „netz“ und der Stab als Linie „netz_linien“",
              "model_netz" in akt_ and "model_netz_linien" in akt_
              and akt_["model_netz"].GetMapper().GetInput().GetNumberOfCells() == len(fm_.elemente)
              and akt_["model_netz_linien"].GetMapper().GetInput().GetNumberOfCells() == 1,
              str([k for k in akt_ if k.startswith("model_")]))
        mm_.add_element("beam", [0, 4], list(mm_.materials)[0], "")
        w.darstellung_setzen("Voll"); w.refresh_all(); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        check("Voll: Schalenkanten 1 px, ein Stab ohne Querschnitt bleibt Linie mit 3 px",
              "model_netz" in akt_ and abs(akt_["model_netz"].GetProperty().GetLineWidth() - 1.0) < 1e-6
              and "model_netz_linien" in akt_ and abs(akt_["model_netz_linien"].GetProperty().GetLineWidth() - 3.0) < 1e-6,
              str({k: akt_[k].GetProperty().GetLineWidth() for k in akt_ if k.startswith("model_")}))
        w.load_example("frame"); app.processEvents()
        w.darstellung_setzen("Hidden-Line"); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        check("reines Stabwerk: ein Gitter „netz“ wie bisher, kein „netz_linien“",
              "model_netz" in akt_ and "model_netz_linien" not in akt_, str([k for k in akt_ if k.startswith("model_")]))
        w.darstellung_setzen("Voll"); app.processEvents()
        # zurueck zum Modell des Netz-Blocks (F1 mit eigener Teilung 2 x 2, unvernetzt)
        w.model = m_; w.analysis = None; w.results = None; w.netzguete_feld = None
        w.refresh_all(); app.processEvents()

        # --- Werkzeuge nachladen: Zusatzknopf in der Maske, Ribbon Extras, Dialog ---------
        w.maske_netzeinstellungen(); app.processEvents()
        mk = w.maskenrand.maske
        check("Netzeinstellungen: Zusatzknopf „Vernetzer installieren…“ und der Befehl im Ribbon Extras",
              "Vernetzer installieren…" in mk.zusatzknoepfe and callable(getattr(w, "werkzeuge_dialog", None)))
        import tempfile as _tf
        from statik3d import werkzeuge as wz_
        from statik3d.gui.werkzeuge_dialog import WerkzeugeDialog
        wz_ordner_alt = os.environ.get("STATIK3D_WERKZEUGE")
        wz_tmp = _tf.mkdtemp(prefix="statik3d_smoke_werkzeuge_")
        os.environ["STATIK3D_WERKZEUGE"] = wz_tmp
        wz_inst_alt = wz_.installieren

        def wz_installieren_fake(key, fortschritt=None, timeout=0.0):
            # ohne Netz: nur einen Stand schreiben, wie es die echte Installation zuletzt tut
            os.makedirs(wz_.werkzeug_ordner(key), exist_ok=True)
            if fortschritt:
                fortschritt(f"{key}: laden", 0.5)
            s = {"werkzeug": key, "version": "9.9", "pakete": {}, "quellen": [], "datum": "2026-09-13T00:00:00",
                 "neustart": False, "rad": wz_.WERKZEUGE[key].rad, "sha256": wz_.WERKZEUGE[key].rad_sha256}
            with open(os.path.join(wz_.werkzeug_ordner(key), "stand.json"), "w", encoding="utf-8") as f_:
                json.dump(s, f_)
            if fortschritt:
                fortschritt(f"{key} 9.9 installiert", 1.0)
            return s
        wz_.installieren = wz_installieren_fake
        try:
            dlg = WerkzeugeDialog(w)
            dlg.geaendert.connect(w._werkzeuge_geaendert)   # wie werkzeuge_dialog(), nur nicht modal
            dlg.show(); app.processEvents()
            stand_txt = [dlg.tabelle.item(i, 4).text() for i in range(dlg.tabelle.rowCount())]
            check("Dialog: vier Zeilen gmsh (GPL, Vernetzer), Netgen (LGPL), MMG3D (LGPL, Nachbesserer), MUMPS (CeCILL-C, Gleichungslöser) - alle „nicht installiert“, Knopf „Installieren“",
                  dlg.tabelle.rowCount() == 4 and [dlg.tabelle.item(i, 0).text() for i in range(4)] == ["gmsh", "Netgen", "MMG3D", "MUMPS"]
                  and dlg.tabelle.item(0, 2).text() == "GPL" and dlg.tabelle.item(2, 1).text() == "Nachbesserer"
                  and dlg.tabelle.item(3, 1).text() == "Gleichungslöser" and dlg.tabelle.item(3, 2).text() == "CeCILL-C"
                  and all("nicht installiert" in s_ for s_ in stand_txt)
                  and all(b.text() == "Installieren" for b in dlg.knoepfe.values()), str(stand_txt))
            check("Dialog nennt Lizenzhinweis (auch MUMPS) und Ablageordner",
                  "GPL" in dlg.HINWEIS and "MUMPS" in dlg.HINWEIS and wz_tmp in dlg.findChildren(QtWidgets.QLabel)[0].text()
                  and dlg.windowTitle() == "Vernetzer, Nachbesserer und Gleichungslöser")
            # Kaestchen "MUMPS beim Programmstart nachladen": Einstellung und Datei
            from statik3d import parallel as parallel_w
            dlg.cb_nachladen.setChecked(False); app.processEvents()
            with open(os.environ["STATIK3D_EINSTELLUNGEN"], encoding="utf-8") as fh_:
                nachladen_datei = __import__("json").load(fh_).get("mumps_nachladen")
            check("Kästchen aus: mumps_nachladen False in den Einstellungen und gespeichert",
                  parallel_w.settings().mumps_nachladen is False and nachladen_datei is False)
            check("Kästchen aus: der Start lädt nicht nach", w._mumps_nachladen() is False)
            dlg.cb_nachladen.setChecked(True); app.processEvents()
            check("Kästchen an: Einstellung wieder an", parallel_w.settings().mumps_nachladen is True)
            geaendert_ = []
            dlg.geaendert.connect(lambda k: geaendert_.append(k))
            n_info = len(w.log.toPlainText())
            dlg.knoepfe["mmg3d"].click()
            t_ = time.time()
            while dlg.worker is not None and dlg.worker.isRunning() and time.time() - t_ < 20:
                app.processEvents(); time.sleep(0.02)
            app.processEvents()
            check("Installieren läuft im Hintergrund und endet: Zeile zeigt Version, Knopf wird „Entfernen“, Signal, Protokoll",
                  geaendert_ == ["mmg3d"] and "Version 9.9" in dlg.tabelle.item(2, 4).text()
                  and dlg.knoepfe["mmg3d"].text() == "Entfernen" and wz_.stand("mmg3d") is not None
                  and "Werkzeug MMG3D 9.9 installiert" in w.log.toPlainText()[n_info:],
                  dlg.tabelle.item(2, 4).text() + " | " + dlg.protokoll.toPlainText()[-120:])
            check("die offene Netzeinstellungen-Maske wurde neu aufgebaut",
                  w.maskenrand.maske is not mk and w.maskenrand.maske.titel == "Netzeinstellungen")
            dlg.knoepfe["mmg3d"].click(); app.processEvents()
            check("Entfernen: Stand weg, Knopf wieder „Installieren“, Protokoll",
                  wz_.stand("mmg3d") is None and dlg.knoepfe["mmg3d"].text() == "Installieren"
                  and "Werkzeug MMG3D entfernt" in w.log.toPlainText()[n_info:] and geaendert_ == ["mmg3d", "mmg3d"])
            dlg.close(); app.processEvents()
            # Nachladen beim Start (erzwungen, Quelle ausgetauscht): Balken, eine Protokollzeile, Maske neu
            n_info = len(w.log.toPlainText())
            check("Nachladen angestossen", w._mumps_nachladen(erzwingen=True) is True and w.progress_bar.isVisible())
            t_ = time.time()
            while w._update_worker is not None and w._update_worker.isRunning() and time.time() - t_ < 20:
                app.processEvents(); time.sleep(0.02)
            app.processEvents()
            check("MUMPS beim Start nachgeladen: Protokollzeile nennt Version, Größe, Dauer und den Weg zur Auswahl; Balken wieder weg",
                  "MUMPS 9.9 nachgeladen (18 MB" in w.log.toPlainText()[n_info:]
                  and "Gleichungslöser" in w.log.toPlainText()[n_info:] and not w.progress_bar.isVisible()
                  and wz_.stand("mumps") is not None, w.log.toPlainText()[n_info:][-160:])
            check("zweiter Start: installiert und nicht veraltet - kein Download",
                  w._mumps_nachladen() is False)
            # Die Loeserauswahl folgt dem Nachladen ohne Neustart
            from statik3d import solver as slv_w
            liste_alt = slv_w.loeser_liste
            mumps_da_ = {k: da for k, _n, da, *_r in liste_alt()}["mumps"]
            slv_w.loeser_liste = lambda: [(k, n, (False if k == "mumps" else da), li, a) for k, n, da, li, a in liste_alt()]
            w._loeserliste_neu()
            i_m = w.cb_loeser.findData("mumps")
            aus_ = not w.cb_loeser.model().item(i_m).isEnabled() and "nicht installiert" in w.cb_loeser.itemText(i_m)
            slv_w.loeser_liste = liste_alt
            w.cb_loeser.setCurrentIndex(w.cb_loeser.findData("superlu"))
            w._werkzeuge_geaendert("mumps")
            i_m = w.cb_loeser.findData("mumps")
            check("Löserauswahl wird nach dem Nachladen neu aufgebaut: MUMPS von „nicht installiert“ auf verfügbar, die Wahl bleibt",
                  aus_ and w.cb_loeser.model().item(i_m).isEnabled() == mumps_da_
                  and w.cb_loeser.currentData() == "superlu" and w.cb_threads.itemText(0).startswith("automatisch"),
                  f"{aus_} -> {w.cb_loeser.itemText(i_m)}, Wahl {w.cb_loeser.currentData()}")
            w.cb_loeser.setCurrentIndex(0)
            wz_.entfernen("mumps")
        finally:
            wz_.installieren = wz_inst_alt
            if wz_ordner_alt is None:
                os.environ.pop("STATIK3D_WERKZEUGE", None)
            else:
                os.environ["STATIK3D_WERKZEUGE"] = wz_ordner_alt
            __import__("shutil").rmtree(wz_tmp, ignore_errors=True)
        w.maske_netzeinstellungen(); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("dichte", "eigene")
        mk.setzen("ziellaenge", 500)
        mk.setzen("h_min", "100")
        mk.setzen("intelligent", False)
        mk.setzen("form", "Dreiecke")
        mk.anwenden()
        app.processEvents()
        check("Netzeinstellungen übernommen (Maske in mm: Ziellänge 500 mm = 0,5 m, kleinste 100 mm = 0,1 m; Dreiecke, ohne Anpassung)",
              m_.netz.dichte == "eigene" and m_.netz.ziellaenge == 0.5 and abs(m_.netz.h_min - 0.1) < 1e-12
              and not m_.netz.intelligent and m_.netz.form == 0, f"{m_.netz.ziellaenge} m, h_min {m_.netz.h_min} m {fehler_}")
        w.maske_netzeinstellungen(); app.processEvents()
        mk2 = w.maskenrand.maske
        check("die Maske zeigt die Längen in mm", float(mk2.werte()["ziellaenge"]) == 500.0
              and str(mk2.werte()["h_min"]).strip() == "100", str((mk2.werte()["ziellaenge"], mk2.werte()["h_min"])))
        # Gleichungsloeser zur Auswahl (Berechnung -> Einstellungen)
        from statik3d import solver as slv_
        from statik3d import parallel as parallel_
        eintraege = [w.cb_loeser.itemText(i) for i in range(w.cb_loeser.count())]
        liste_ = {k: da for k, _n, da, *_r in slv_.loeser_liste()}
        check("Gleichungslöser: automatisch + sechs Löser, nicht installierte grau",
              len(eintraege) == 7 and eintraege[0].startswith("automatisch")
              and all(w.cb_loeser.model().item(i + 1).isEnabled() == liste_[k]
                      for i, k in enumerate(("pardiso", "cholmod", "umfpack", "mumps", "pyamg", "superlu"))),
              str(eintraege))
        w.cb_loeser.setCurrentIndex(w.cb_loeser.findData("superlu"))
        w._apply_parallel_settings()
        check("die Auswahl kommt in den Einstellungen an", parallel_.settings().solver_backend == "superlu")
        # --- Rechnerfarm ohne Kommandozeile: einschalten, Rechenhilfe sucht und verbindet ------
        from statik3d import farm as farm_
        import socket as _socket
        _s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM); _s.bind(("127.0.0.1", 0)); farm_port_ = _s.getsockname()[1]; _s.close()
        _s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM); _s.bind(("127.0.0.1", 0)); such_port_ = _s.getsockname()[1]; _s.close()
        alt_udp_ = farm_.ANKUENDIGUNGS_PORT
        farm_.ANKUENDIGUNGS_PORT = such_port_
        w.ed_farm_port.setText(str(farm_port_)); w.ed_farm_key.setText("smoke")
        check("Einstellungen nennen den Weg für die Rechenhilfe (Extras, --rechenhilfe, Adresse)",
              "Als Rechenhilfe" in w.lbl_farm_hilfe.text() and "--rechenhilfe" in w.lbl_farm_hilfe.text()
              and w.btn_farm_start.text() == "Rechnerfarm einschalten")
        # --- Die Farmeinstellungen erscheinen erst mit der Farm (14.09.2026) ---
        w.cb_backend.setCurrentIndex(0); app.processEvents()
        check("Backend heißt „lokal“ und „lokal und Rechnerfarm“ - die Farm kommt dazu, sie ersetzt nichts",
              [w.cb_backend.itemText(i) for i in range(w.cb_backend.count())]
              == ["lokal", "lokal und Rechnerfarm"],
              str([w.cb_backend.itemText(i) for i in range(w.cb_backend.count())]))
        check("Server, Port, Schlüssel und die Farmknöpfe stehen zusammen in einem Rahmen",
              all(w.w_farm.isAncestorOf(x) for x in (w.ed_farm_host, w.ed_farm_port, w.ed_farm_key,
                                                     w.btn_farm_start, w.lbl_farm_hilfe)))
        check("lokal: der Rahmen ist zu - die sechs Felder sind nicht im Weg",
              w.w_farm.isHidden(), f"versteckt {w.w_farm.isHidden()}")
        w.cb_backend.setCurrentIndex(1); app.processEvents()
        check("umgeschaltet auf die Farm: der Rahmen erscheint",
              not w.w_farm.isHidden(), f"versteckt {w.w_farm.isHidden()}")
        w.cb_backend.setCurrentIndex(0); app.processEvents()
        check("und verschwinden wieder", w.w_farm.isHidden())
        w.cb_backend.setCurrentIndex(1); app.processEvents()
        n_info = len(w.log.toPlainText())
        w.farm_start_local(); app.processEvents()
        check("Rechnerfarm einschalten: Server, Worker, Ankündigung; Backend springt auf Farm; Protokoll nennt Adresse, Port, Schlüssel-Hinweis und Firewall",
              w._farm_ankuendigung is not None and w.cb_backend.currentIndex() == 1
              and w.btn_farm_start.text() == "Rechnerfarm läuft"
              and f":{farm_port_}" in w.log.toPlainText()[n_info:] and "Firewall" in w.log.toPlainText()[n_info:],
              w.log.toPlainText()[n_info:][:160])
        rh = w.rechenhilfe_fenster(); app.processEvents()
        rh.prozesse = False                                  # Threads statt Prozesse: schnell und im selben Prozess
        rh.suchport = such_port_
        check("Extras → Als Rechenhilfe arbeiten… öffnet das Fenster mit Suche, Port, Schlüssel, Kernen, Verbinden",
              rh.isVisible() and rh.windowTitle().endswith("Rechenhilfe") and rh.b_suchen.text() == "Arbeitsplatz suchen"
              and rh.sp_port.value() == farm_port_ and rh.ed_key.text() == "smoke" and rh.sp_kerne.value() >= 1)
        rh.suchen(4.0)                                         # Takt der Ankündigung 2 s
        t_ = time.time()
        while rh.worker is not None and rh.worker.isRunning() and time.time() - t_ < 15:
            app.processEvents(); time.sleep(0.02)
        app.processEvents()
        check("„Arbeitsplatz suchen“ findet den eigenen Arbeitsplatz über die Ankündigung (Host, Port, Stand)",
              len(rh.gefunden) >= 1 and all(d["port"] == farm_port_ for d in rh.gefunden)
              and rh.host() in {d["host"] for d in rh.gefunden} and rh.sp_port.value() == farm_port_, str(rh.gefunden)[:160])
        rh.sp_kerne.setValue(1)
        rh.verbinden()
        t_ = time.time()
        while rh.worker is not None and rh.worker.isRunning() and time.time() - t_ < 30:
            app.processEvents(); time.sleep(0.02)
        app.processEvents()
        check("„Verbinden“: Schlüssel geprüft, ein Rechenprozess arbeitet, Trennen wird möglich",
              rh.verbunden and rh.b_trennen.isEnabled() and not rh.b_verbinden.isEnabled()
              and "Verbunden" in rh.protokoll.toPlainText(), rh.protokoll.toPlainText()[-160:])
        c_ = farm_.FarmClient("127.0.0.1", farm_port_, "smoke")
        # auf den Worker der Rechenhilfe warten (die eigenen "gui#"-Worker sind schon da)
        t_ = time.time()
        namen_ = []
        while time.time() - t_ < 30:
            namen_ = [k for k, v in c_.status()["workers"].items() if "Rechenhilfe" in k and v.get("alive")]
            if namen_:
                break
            app.processEvents(); time.sleep(0.2)
        rh._stand_holen(); app.processEvents()
        check("die Rechenhilfe steht im Farm-Status mit Version und Stand, ihr Fenster zeigt den Stand",
              len(namen_) == 1 and c_.status()["workers"][namen_[0]].get("version") == farm_.__version__
              and "verbunden mit " in rh.lbl_stand.text() and f":{farm_port_}" in rh.lbl_stand.text()
              and "1 von 1 Prozessen aktiv" in rh.lbl_stand.text(),
              rh.lbl_stand.text())
        rh.ed_key.setText("falsch"); rh.trennen(); app.processEvents()
        check("Trennen: nicht verbunden, Verbinden wieder möglich", not rh.verbunden and rh.b_verbinden.isEnabled())
        rh.verbinden()
        t_ = time.time()
        while rh.worker is not None and rh.worker.isRunning() and time.time() - t_ < 30:
            app.processEvents(); time.sleep(0.02)
        app.processEvents()
        check("falscher Schlüssel: keine Verbindung, klare Meldung mit Firewall-Hinweis",
              not rh.verbunden and "Keine Verbindung" in rh.protokoll.toPlainText() and "Firewall" in rh.lbl_stand.text(),
              rh.protokoll.toPlainText()[-120:])
        rh.close(); app.processEvents()
        w._farm_ankuendigung.set(); w._farm_ankuendigung = None
        farm_.ANKUENDIGUNGS_PORT = alt_udp_
        w.cb_backend.setCurrentIndex(0); w.ed_farm_key.setText("statik3d"); w.ed_farm_port.setText("5555")
        w._apply_parallel_settings()
        # Threads des Gleichungsloesers: automatisch oder feste Zahl, wird gespeichert
        stufen_ = [w.cb_threads.itemData(i) for i in range(w.cb_threads.count())]
        check("Threads des Gleichungslösers: automatisch (nennt PARDISO und MUMPS) + Stufen bis zur Kernzahl",
              w.cb_threads.itemText(0).startswith("automatisch") and "MUMPS" in w.cb_threads.itemText(0)
              and stufen_[0] == 0 and stufen_[1:] == sorted(stufen_[1:]) and 1 in stufen_
              and stufen_[-1] == parallel_.cpu_count(), str(stufen_))
        w.cb_threads.setCurrentIndex(w.cb_threads.findData(2))
        w._apply_parallel_settings()
        import json as _json
        with open(os.environ["STATIK3D_EINSTELLUNGEN"], encoding="utf-8") as fh_:
            gespeichert_ = _json.load(fh_)
        check("2 Threads kommen in den Einstellungen an und stehen in der gespeicherten Datei",
              parallel_.settings().solver_threads == 2 and gespeichert_.get("solver_threads") == 2
              and gespeichert_.get("solver_backend") == "superlu", str(gespeichert_))
        w.cb_threads.setCurrentIndex(0)
        w.cb_loeser.setCurrentIndex(0)
        w._apply_parallel_settings()
        w.maskenrand.schliessen()
        w.sel_flaechen = []
        w.geometrie_vernetzen()
        app.processEvents()
        check("Vernetzen: Teilung 8 × 4 aus der Netzdichte (64 Dreieckelemente), die eigene Teilung 2 × 2 bleibt",
              f_.teilung == [2, 2] and len(f_.elemente) == 64 and all(m_.elements[e].typ == "shell3" for e in f_.elemente)
              and "Netzdichte Fläche F1" in w.log.toPlainText() and "→ 8 × 4" in w.log.toPlainText(),
              str((f_.teilung, len(f_.elemente))))
        m_.netz.dichte = "mittel"
        m_.netz.intelligent = True
        m_.netz.form = 2
        w.geometrie_vernetzen()
        app.processEvents()
        D_ = (16 + 4) ** 0.5
        check("Netzdichte mittel: 16 Elemente über die Diagonale → Netz 14 × 7 Vierecke, eigene Teilung bleibt",
              len(f_.elemente) == round(4 / (D_ / 16)) * round(2 / (D_ / 16)) and f_.teilung == [2, 2]
              and all(m_.elements[e].typ == "shell4" for e in f_.elemente),
              str((f_.teilung, len(f_.elemente))))
        del w._bestaetigen
        w.error = alt_error

        # ---- Lastwerte in der Ansicht; Kontextmenü der Auswahl mit Sammelmaske ----
        w.new_model()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w._bestaetigen = lambda text: True
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        k0 = m_.add_node(0, 0, 0)
        k1 = m_.add_node(4, 0, 0)
        k2 = m_.add_node(4, 3, 0)
        k3 = m_.add_node(0, 3, 0)
        k4 = m_.add_node(0, 6, 0)
        e0 = m_.add_element("beam", [k0, k1], mat_, sec_)
        e1 = m_.add_element("beam", [k1, k2], mat_, sec_)
        m_.members["S1"] = Mb("S1", elements=[e0])
        m_.members["S2"] = Mb("S2", elements=[e1], beta_y=2.0)
        m_.fix(k0, "all")
        m_.fix(k3, [0, 1, 2])
        for i, (a, b) in enumerate([(k0, k1), (k1, k2), (k2, k3), (k3, k0)]):
            m_.add_line(f"L{i}", [a, b])
        m_.load_node(k1, Fz=-12500.0)
        m_.load_node(k2, Fx=3000.0, Mx=2000.0)
        m_.load_beam(e0, qz=-5000.0)
        w.refresh_all()
        app.processEvents()
        ak_ = list(w.plotter.renderer.actors)
        check("Lastwerte als Zahlen an den Lasten, Einheiten [kN, kNm, kN/m] unter dem Lastfall",
              any(a.startswith("lastwerte") for a in ak_) and any("[kN, kNm, kN/m]" in z for z in w._kopfzeile_zeilen),
              str(w._kopfzeile_zeilen))
        w.act_lastwerte.setChecked(False)
        app.processEvents()
        check("Schalter „Lastwerte“ aus: keine Zahlen, Einheiten bleiben",
              not any(a.startswith("lastwerte") for a in w.plotter.renderer.actors)
              and any("[kN" in z for z in w._kopfzeile_zeilen))
        w.act_lastwerte.setChecked(True)
        w.selection = np.array([k0, k1], int)
        w.sel_linien = ["L0", "L1"]
        w.sel_staebe = ["S1", "S2"]
        menu_ = QtWidgets.QMenu()
        ok_ = w._auswahlmenue(menu_)
        texte_ = [a.text() for a in menu_.actions() if a.text()]
        check("Kontextmenü der Auswahl: „Selektiertes anzeigen“, „Selektiertes ausblenden“, dann die Gruppen",
              ok_ and texte_[:2] == ["Selektiertes anzeigen", "Selektiertes ausblenden"]
              and "Knoten (2)" in texte_ and "Knotenlager (1)" in texte_ and "Linien (2)" in texte_ and "Stäbe (2)" in texte_,
              str(texte_))
        check("… und Verschieben, Kopieren, Drehen, Spiegeln (15.09.2026)",
              all(t_ in texte_ for t_ in ("Verschieben…", "Kopieren…", "Drehen…", "Spiegeln…")), str(texte_))
        sub_ = next(a.menu() for a in menu_.actions() if a.text() == "Knoten (2)")
        check("Untermenü je Gruppe: Bearbeiten…, Löschen", [a.text() for a in sub_.actions()] == ["Bearbeiten…", "Löschen"])
        w.sammelmaske("knoten", [k0, k1])
        app.processEvents()
        mk = w.maskenrand.maske
        check("Sammelmaske Knoten: x verschieden (leer), z gleich", mk.werte()["x"] == "" and mk.werte()["z"] == "0", str(mk.werte()))
        mk.setzen("z", "1.5")
        mk.anwenden()
        app.processEvents()
        check("z = 1,5 für beide Knoten, x bleibt je Knoten", m_.nodes[k0][2] == 1.5 and m_.nodes[k1][2] == 1.5 and m_.nodes[k1][0] == 4.0)
        w.sammelmaske("stab", ["S1", "S2"])
        app.processEvents()
        mk = w.maskenrand.maske
        check("Sammelmaske Stäbe: β_y verschieden, β_z gleich", mk.werte()["beta_y"] == "" and mk.werte()["beta_z"] == "1")
        mk.setzen("beta_y", "0.7")
        mk.setzen("lt_check", "nein")
        mk.anwenden()
        app.processEvents()
        check("β_y = 0,7 und Biegedrillknicken aus für beide Stäbe",
              all(m_.members[s].beta_y == 0.7 and not m_.members[s].lt_check for s in ("S1", "S2")))
        w.sammelmaske("lager", [0, 1])
        app.processEvents()
        mk = w.maskenrand.maske
        check("Sammelmaske Lager: u_x bei beiden gesperrt, φ_x verschieden → „(unverändert)“",
              mk.werte()["d0"] == "ja" and mk.werte()["d3"] == "(unverändert)")
        mk.setzen("d3", "ja")
        mk.anwenden()
        app.processEvents()
        check("φ_x jetzt bei beiden Lagern gesperrt", all(3 in s.dofs for s in m_.supports))
        w.auswahl_loeschen("linie", ["L0", "L1"])
        app.processEvents()
        check("Löschen der Gruppe: beide Linien weg, Auswahl leer", "L0" not in m_.lines and "L1" not in m_.lines
              and "L2" in m_.lines and not w.sel_linien)
        w.undo()
        app.processEvents()
        check("Rückgängig holt beide Linien zurück", "L0" in w.model.lines and "L1" in w.model.lines)
        w.auswahl_loeschen("knoten", [k4])
        app.processEvents()
        check("Freien Knoten über das Menü löschen", w.model.nn == 4, str(w.model.nn))
        # --- 15.09.2026: Verschieben, Kopieren, Drehen, Spiegeln aus dem Rechtsklick / Ribbon ---
        m_ = w.model
        k_ = 0
        alt_k = m_.nodes[k_].copy()
        w._auswahl_leeren(); w.selection = np.array([k_], int)
        w.maske_transformieren("verschieben"); app.processEvents()
        mk = w.maskenrand.maske
        check("Maske „Verschieben“ rechts: dx, dy, dz und die Auswahl (1 Knoten), zwei Punkte anklickbar",
              mk is not None and mk.titel.startswith("Verschieben") and all(k in mk.werte() for k in ("dx", "dy", "dz"))
              and "1 Knoten" in mk.werte()["auswahl"] and mk.n_knoten == 2 and mk.punkte, str(mk.werte() if mk else None))
        mk.setzen("dx", 0.5); mk.anwenden(); app.processEvents()
        check("Anwenden verschiebt den Knoten um dx = 0,5",
              abs(m_.nodes[k_][0] - alt_k[0] - 0.5) < 1e-9 and abs(m_.nodes[k_][2] - alt_k[2]) < 1e-9, str(m_.nodes[k_]))
        w.maske_transformieren("verschieben"); app.processEvents()
        w.maskenrand.punkt_angeklickt(np.array([0.0, 0.0, 0.0])); w.maskenrand.punkt_angeklickt(np.array([0.0, 0.0, 1.5]))
        app.processEvents()
        check("zwei Punkte anklicken (von → nach) verschiebt sofort um ihren Abstand (0, 0, 1,5)",
              abs(m_.nodes[k_][2] - alt_k[2] - 1.5) < 1e-9, str(m_.nodes[k_]))
        m_.nodes[k_] = alt_k
        w._auswahl_leeren(); w.sel_linien = ["L0"]
        n_l, nn_ = len(m_.lines), m_.nn
        w.maske_transformieren("kopieren"); app.processEvents()
        mk = w.maskenrand.maske
        check("Maske „Kopieren“ mit Anzahl", mk is not None and mk.titel.startswith("Kopieren") and "anzahl" in mk.werte())
        z0_ = np.sort(m_.nodes[[int(x) for x in m_.lines["L0"].nodes], 2])
        mk.setzen("dz", 2.0); mk.setzen("anzahl", 2); mk.anwenden(); app.processEvents()
        check("Kopieren mit dz = 2, zweimal: zwei neue Linien auf vier neuen Knoten (z + 2, z + 4), das Original bleibt",
              len(m_.lines) == n_l + 2 and m_.nn == nn_ + 4 and "L0" in m_.lines
              and np.allclose(np.sort(m_.nodes[nn_:nn_ + 2, 2]), z0_ + 2.0)
              and np.allclose(np.sort(m_.nodes[nn_ + 2:, 2]), z0_ + 4.0),
              f"{len(m_.lines)} Linien, {m_.nn} Knoten, z {m_.nodes[nn_:, 2]}")
        w._auswahl_leeren(); w.selection = np.array([k_], int)
        w.maske_transformieren("drehen"); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("achse", "z"); mk.setzen("winkel", 180.0); mk.setzen("px", 1.0); mk.anwenden(); app.processEvents()
        check("Drehen 180° um z durch (1,0,0): x → 2 - x",
              abs(m_.nodes[k_][0] - (2.0 - alt_k[0])) < 1e-9 and abs(m_.nodes[k_][1] + alt_k[1]) < 1e-9, str(m_.nodes[k_]))
        m_.nodes[k_] = alt_k
        w.maske_transformieren("spiegeln"); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("ebene", "xy (z = Lage)"); mk.setzen("lage", 1.0); mk.setzen("kopie", True); mk.anwenden(); app.processEvents()
        check("Spiegeln an z = 1 als Kopie: ein neuer Knoten bei z = 2 - z, das Original bleibt",
              m_.nn == nn_ + 5 and abs(m_.nodes[-1][2] - (2.0 - alt_k[2])) < 1e-9 and np.allclose(m_.nodes[k_], alt_k),
              f"{m_.nn} Knoten, {m_.nodes[-1]}")
        w.undo(); app.processEvents()
        check("Rückgängig nimmt die Spiegelkopie zurück", w.model.nn == nn_ + 4, str(w.model.nn))
        w._auswahl_leeren()
        w.maske_transformieren("verschieben"); app.processEvents()
        check("ohne Auswahl: Hinweis statt Maske", fehler_ and "Zuerst" in fehler_[-1], str(fehler_[-1:]))
        del w._bestaetigen
        w.error = alt_error

        # Viele freie Knoten übertönen die Hervorhebung nicht
        w.new_model()
        w.model.add_nodes(np.array([[i, 0, 0] for i in range(20)], float))
        check("bei überwiegend freien Knoten keine Sonderfarbe",
              len(vpl.unbelegte_knoten(w.model)) > vpl.FREI_ANTEIL * w.model.nn)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Lasten, Fang, Glasleiste", False, str(ex)[:70])

    try:
        # ---- Kontur zeichnen (16.09.2026): Querschnitt aus dem Skizzenfenster ----
        from statik3d.gui import profilmaske as pm_k
        from statik3d import sections as secs_k
        w._baum_geklickt("querschnitte", "Querschnitte")
        app.processEvents()
        mk = w.maskenrand.maske
        m_ = w.model
        check("Querschnittsmaske: Aufklappliste „neue Kontur“ und Knopf „Kontur zeichnen …“",
              isinstance(mk, pm_k.QuerschnittMaske) and mk.cb_kontur.count() == 1
              and mk.btn_kontur.text().startswith("Kontur"), str(mk and mk.cb_kontur.count()))
        check("Parameterprofile wie in RFEM in der Aufklappliste (Doppel-T unsymmetrisch, Z, Hut, Ellipse, Sechskant)",
              all(mk.cb_art.findText(a) >= 0 for a in ("Doppel-T unsymmetrisch", "Z", "Hut", "Ellipse", "Sechskant"))
              and len(mk.par) == pm_k.PARAMETERFELDER)
        mk.cb_art.setCurrentText("Doppel-T unsymmetrisch")
        app.processEvents()
        check("Doppel-T unsymmetrisch: sechs Felder sichtbar, Bild und Kennwerte mit Wpl",
              all(e.isVisible() for e in mk.par[:6]) and len(mk.bild_param.umrisse) == 1 and "Wpl" in mk.lbl_param.text(),
              mk.lbl_param.text()[:60])
        mk.ed_name.setText("Kontur-Kasten")
        dk = mk.kontur_zeichnen()
        app.processEvents()
        check("Kontur: das Skizzenfenster öffnet mit leerem Blatt 400 × 400 mm",
              dk is not None and dk.isVisible() and not dk.skizze["elemente"] and dk.skizze["breite"] == 400.0)
        for a, b in (((50, 250), (250, 250)), ((250, 250), (250, 150)), ((250, 150), (50, 150)), ((50, 150), (50, 250))):
            dk.element_anfuegen({"art": "linie", "p1": list(a), "p2": list(b)})
        dk.element_anfuegen({"art": "kreis", "mitte": [150, 200], "r": 20})
        dk.ok()
        app.processEvents()
        m_ = w.model
        sk_ = m_.sections.get("Kontur-Kasten")
        check("Kontur: Rechteck 200 × 100 mit Kreisloch r = 20 wird zum Querschnitt (A = 200·100 − π·20²)",
              sk_ is not None and abs(sk_.A - (0.02 - np.pi * 0.02 ** 2)) < 2e-6, str(sk_ and sk_.A))
        mk = w.maskenrand.maske
        check("Kontur: die Skizze reist mit, die Aufklappliste bietet sie zum Bearbeiten an, Umriss mit Loch",
              secs_k.skizze_inhalt(sk_) is not None and mk.cb_kontur.count() == 2
              and sum(1 for _p, loch in secs_k.umriss(sk_) if loch) == 1, str(mk.cb_kontur.count()))
        check("Kontur: Wpl aus der plastischen Nulllinie größer als Wel", sk_.Wpl_y > sk_.Wel_y * 1.05)
        mk.cb_kontur.setCurrentIndex(1)
        dk2 = mk.kontur_zeichnen()
        app.processEvents()
        check("Kontur: die gezeichnete Kontur kommt mit ihren 5 Elementen zurück",
              len(dk2.skizze["elemente"]) == 5 and dk2.ed_name.text() == "Kontur-Kasten")
        dk2.skizze["elemente"].pop()            # das Loch weg
        dk2.ok()
        app.processEvents()
        m_ = w.model
        check("Kontur: Übernehmen ersetzt den Querschnitt gleichen Namens (A = 0,02 m²), kein Doppel",
              "Kontur-Kasten" in m_.sections and abs(m_.sections["Kontur-Kasten"].A - 0.02) < 1e-9
              and sum(1 for n in m_.sections if n.startswith("Kontur")) == 1, str(sorted(m_.sections)))
        mk = w.maskenrand.maske
        mk.cb_kontur.setCurrentIndex(0)
        mk.ed_name.setText("Offen")
        dk3 = mk.kontur_zeichnen()
        dk3.element_anfuegen({"art": "linie", "p1": [0, 0], "p2": [100, 0]})
        dk3.element_anfuegen({"art": "linie", "p1": [100, 0], "p2": [100, 50]})
        dk3.uebernehmen()
        app.processEvents()
        check("Kontur: eine offene Kontur wird im Fenster benannt, kein Querschnitt entsteht",
              "nicht geschlossen" in dk3.lbl_status.text() and "Offen" not in w.model.sections, dk3.lbl_status.text()[:80])
        dk3.close()
        w._bestaetigen = lambda text: True
        w._baum_loeschen("querschnitt", "Kontur-Kasten")
        del w._bestaetigen
        app.processEvents()
        check("Kontur: der gezeichnete Querschnitt lässt sich löschen", "Kontur-Kasten" not in w.model.sections)
        w.maskenrand.schliessen()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Kontur zeichnen", False, str(ex)[:70])

    try:
        # ---- Gelenke und Liniengelenke im Modellbaum (16.09.2026) ----
        from tests.test_fugen import _wuerfel as _wuerfel_g
        m_ = _wuerfel_g(0.5)               # ein Wuerfel mit Flaechen Boden, Deckel, M0..M3
        w.model = m_
        w.analysis = None
        w.results = None
        fn_ = "Deckel"
        f_ = m_.flaechen[fn_]
        f_.gelenklinien = list(f_.linien[:2])
        f_.gelenkwirkung = "ux=starr, uy=starr, uz=starr, phix=frei, phiy=frei, phiz=frei"
        w.refresh_all()
        app.processEvents()

        def zweige_g(baum):
            out_ = []

            def lauf_(it):
                out_.append(it.text(0))
                for i_ in range(it.childCount()):
                    lauf_(it.child(i_))
            for i_ in range(baum.topLevelItemCount()):
                lauf_(baum.topLevelItem(i_))
            return out_
        namen = zweige_g(w.baum)
        check("Modellbaum: Zweig „Gelenke“ auch ohne Gelenke, mit „+ Gelenk anlegen“",
              "Gelenke" in namen and "+ Gelenk anlegen" in namen and not m_.hinges)
        check("Modellbaum: Zweig „Liniengelenke“ mit der Fläche", "Liniengelenke" in namen and namen.count(fn_) >= 1)
        w._baum_geklickt("liniengelenk", fn_)
        app.processEvents()
        check("Liniengelenk: Klick lässt die Gelenklinien leuchten und zeigt die Maske mit Wirkung",
              sorted(w.sel_linien) == sorted(f_.gelenklinien) and w.sel_flaechen == [fn_]
              and w.eingaben_dock.windowTitle() == f"Liniengelenk an {fn_}", w.eingaben_dock.windowTitle())
        w._baum_geklickt("liniengelenke", "Liniengelenke")
        app.processEvents()
        check("Liniengelenke: der Zweig zeigt die Übersicht (Flächen, Linien, Wirkung)",
              w.eingaben_dock.windowTitle() == "Liniengelenke" and len(w.sel_linien) == 2)
        w._baum_geklickt("gelenk_neu", "+ Gelenk anlegen")
        app.processEvents()
        check("„+ Gelenk anlegen“ öffnet die Gelenkmaske", "Gelenk" in w.eingaben_dock.windowTitle(), w.eingaben_dock.windowTitle())
        w.maskenrand.schliessen()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Gelenke und Liniengelenke im Modellbaum", False, str(ex)[:70])

    try:
        # ---- Genauigkeit des Gleichungslösers (17.09.2026) ----
        from statik3d import parallel as par_g
        alt_g = (par_g.settings().solver_residuum, par_g.settings().solver_nachiterationen)
        check("Berechnung → Einstellungen: Genauigkeit (5 Stufen, Vorgabe normal 1e-6) und Nachiterationen (bis 3)",
              w.cb_genau.count() == 5 and w.cb_genau.currentData() == 1e-6 and "Vorgabe" in w.cb_genau.currentText()
              and w.cb_nachit.currentData() == 3, f"{w.cb_genau.currentText()} / {w.cb_nachit.currentText()}")
        w.cb_genau.setCurrentIndex(w.cb_genau.findData(1e-4))
        w.cb_nachit.setCurrentIndex(w.cb_nachit.findData(5))
        w._apply_parallel_settings()
        import json as json_g
        with open(par_g.einstellungsdatei(), encoding="utf-8") as fh_g:
            d_g = json_g.load(fh_g)
        check("Übernehmen setzt Schranke 1e-4 und 5 Nachiterationen und speichert beides",
              par_g.settings().solver_residuum == 1e-4 and par_g.settings().solver_nachiterationen == 5
              and d_g.get("solver_residuum") == 1e-4 and d_g.get("solver_nachiterationen") == 5, str(d_g))
        from statik3d import solver as slv_g
        check("der Löser nennt die eingestellte Genauigkeit", slv_g.LinearSolver.genauigkeit() == (1e-4, 5))
        w._genau_waehlen(3e-7)
        check("ein Wert außerhalb der Liste landet beim nächsten Eintrag (1e-6)", w.cb_genau.currentData() == 1e-6)
        w.cb_genau.setCurrentIndex(w.cb_genau.findData(alt_g[0]))
        w.cb_nachit.setCurrentIndex(w.cb_nachit.findData(alt_g[1]))
        w._apply_parallel_settings()
        check("zurückgestellt", par_g.settings().solver_residuum == alt_g[0])
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Genauigkeit des Gleichungslösers", False, str(ex)[:70])

    try:
        # ---- Passung: Spiel, Lochleibungsgrenze, Randabminderung - Maske und Sammelmaske (17.09.2026) ----
        from tests.test_fugen import zwei_bloecke as _zb_p
        m_ = _zb_p("eigene", 0.5, 0.15)
        w.model = m_
        w.analysis = None
        w.results = None
        w.refresh_all()
        app.processEvents()
        m_ = w.model
        kb_p = m_.add_kontaktbedingung("Fuge P").standard_anwenden("Reibungsbehaftet")
        kb_p.koerpernamen, kb_p.flaechennamen = ["Oben"], ["FugeO"]
        kb_p.gegenkoerper, kb_p.gegenflaechen = ["Unten"], ["FugeU"]
        w.refresh_all()
        app.processEvents()
        w._baum_geklickt("kontaktbedingung", "Fuge P")
        app.processEvents()
        mk = w.maskenrand.maske
        wv = mk.werte()
        check("Kontaktmaske: Felder Spiel, Lochleibungsgrenze, Randabminderung mit Vorgabe 0",
              all(k in wv for k in ("spiel", "grenzpressung", "rand_frei"))
              and float(str(wv["spiel"]).replace(",", ".")) == 0.0, str({k: wv.get(k) for k in ("spiel", "grenzpressung", "rand_frei")}))
        mk.setzen("spiel", "0,02")
        mk.setzen("grenzpressung", "355")
        mk.setzen("rand_frei", "1")
        mk.angewendet.emit(mk.werte())
        app.processEvents()
        kb_p = w.model.kontaktbedingungen["Fuge P"]
        cp_p = next((c for c in w.model.contact_pairs if c.name == "Fuge P"), None)
        check("Übernehmen speichert die Passung (m, N/m², Reihen) und führt die Fuge am Netz neu aus",
              abs(kb_p.spiel - 2e-5) < 1e-12 and abs(kb_p.grenzpressung - 355e6) < 1 and kb_p.rand_frei == 1
              and cp_p is not None and cp_p.spiel == kb_p.spiel and cp_p.grenzpressung == kb_p.grenzpressung
              and len(cp_p.rand_knoten) >= 4 and cp_p.knotenflaechen, str((kb_p.spiel, kb_p.grenzpressung, kb_p.rand_frei)))
        # Sammelmaske: Volumen waehlen, Passung fuer ihre Fugen setzen
        w.auswahlart_setzen("Volumen")
        w.sel_koerper = ["Oben"]
        w.maske_passung()
        app.processEvents()
        mp = w.maskenrand.maske
        check("Passung-Maske nennt die gewählten Volumen und ihre Fugen",
              mp is not None and "Fuge P" in str(mp.werte().get("kontakte")) and "Oben" in str(mp.werte().get("koerper")),
              str(mp.werte().get("kontakte")))
        mp.setzen("spiel", "0,05")
        mp.setzen("grenzpressung", "300")
        mp.setzen("rand_frei", "2")
        mp.angewendet.emit(mp.werte())
        app.processEvents()
        kb_p = w.model.kontaktbedingungen["Fuge P"]
        check("Anwenden setzt die Passung an jeder Fuge der gewählten Volumen und protokolliert es",
              abs(kb_p.spiel - 5e-5) < 1e-12 and abs(kb_p.grenzpressung - 300e6) < 1 and kb_p.rand_frei == 2
              and "Passung gesetzt an" in w.log.toPlainText(), str((kb_p.spiel, kb_p.grenzpressung, kb_p.rand_frei)))
        check("Ribbon: der Befehl „Passung“ steht neben „Übermaß“", any(a.text() == "Passung" for a in w.findChildren(QtGui.QAction)))
        w.maskenrand.schliessen()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Passung", False, str(ex)[:70])

    # ---- Neue Oberflaeche: Fang je Art, Wuerfel, Glasleiste, Ribbon, Sicht, Texte ----
    try:
        import pyvista as pvx
        from statik3d import ks as ksm
        from statik3d.gui import ribbon as ribm, symbole as symm
        from statik3d.model import Model as Mdl, Line, Flaeche
        w.fang_umschalten(True)
        for art in ksm.FANGARTEN:
            w.fangart_umschalten(art, True)
        # Fang Linie/Stab: der Fusspunkt auf der Strecke unter dem Zeiger
        w.load_example("hall")
        app.processEvents()
        w.blickrichtung("-y")
        w.zoom_alles()
        app.processEvents()
        A = np.array([[0.0, 0.0, 0.0]])
        B = np.array([[10.0, 0.0, 0.0]])
        xy, _sicht = w._projizieren(np.array([[4.0, 0.0, 0.0]]))
        w.plotter.iren.interactor.SetEventPosition(int(round(xy[0][0])), int(round(xy[0][1])))
        fuss = w._fusspunkt_am_zeiger(A, B)
        check("Fang Linie: Fusspunkt auf der Strecke unter dem Zeiger",
              fuss is not None and abs(fuss[0] - 4.0) < 0.6 and abs(fuss[1]) < 1e-9
              and abs(fuss[2]) < 1e-9, str(fuss))
        # Fang Flaeche: der Punkt auf der Schale unter dem Zeiger
        w.load_example("plate")
        app.processEvents()
        w.blickrichtung("+z")
        w.zoom_alles()
        app.processEvents()
        breite, hoehe = w.plotter.render_window.GetSize()
        w.plotter.iren.interactor.SetEventPosition(breite // 2, hoehe // 2)
        w.fang_arten = ["flaeche"]
        p_f, art_f, _i = w._fangpunkt()
        check("Fang Fläche: Punkt auf der Schale unter dem Zeiger",
              art_f == "flaeche" and p_f is not None, f"{art_f} {p_f}")
        w.fang_arten = ["volumen"]
        p_v, art_v, _i = w._fangpunkt()
        check("Fang Volumen greift auf einer Schale nicht", art_v == "", f"{art_v} {p_v}")
        w.fang_arten = list(ksm.FANGARTEN)

        # Ansichtswuerfel: Kamera bekannt, Ziehen dreht
        R = w.ansichtswuerfel.kamera()
        check("der Würfel kennt die Kamera", R is not None and len(R) == 3 and len(R[0]) == 3)
        w.blickrichtung("iso")
        app.processEvents()
        pos0 = np.asarray(w.plotter.camera_position[0], float)
        ziel0 = np.asarray(w.plotter.camera_position[1], float)
        w.ansichtswuerfel.gedreht.emit(40.0, 0.0)
        app.processEvents()
        pos1 = np.asarray(w.plotter.camera_position[0], float)
        ziel1 = np.asarray(w.plotter.camera_position[1], float)
        check("Ziehen auf dem Würfel dreht die Kamera um den Blickpunkt",
              np.linalg.norm(pos1 - pos0) > 1e-6
              and abs(np.linalg.norm(pos1 - ziel1) - np.linalg.norm(pos0 - ziel0)) < 1e-6
              and np.linalg.norm(ziel1 - ziel0) < 1e-9,
              f"{np.round(pos0, 2)} -> {np.round(pos1, 2)}")
        wf = w.ansichtswuerfel
        empfangen = []
        wf.gedreht.connect(lambda dx, dy: empfangen.append((dx, dy)))

        def maus(typ, pos, knopf, knoepfe):
            ev = QtGui.QMouseEvent(typ, QtCore.QPointF(pos), QtCore.QPointF(wf.mapToGlobal(pos)),
                                   knopf, knoepfe, QtCore.Qt.NoModifier)
            app.sendEvent(wf, ev)
        mitte = QtCore.QPoint(wf.WUERFEL // 2, wf.WUERFEL // 2)
        maus(QtCore.QEvent.MouseButtonPress, mitte, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        maus(QtCore.QEvent.MouseMove, mitte + QtCore.QPoint(12, 0), QtCore.Qt.NoButton,
             QtCore.Qt.LeftButton)
        maus(QtCore.QEvent.MouseMove, mitte + QtCore.QPoint(26, 3), QtCore.Qt.NoButton,
             QtCore.Qt.LeftButton)
        maus(QtCore.QEvent.MouseButtonRelease, mitte + QtCore.QPoint(26, 3),
             QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        app.processEvents()
        check("die Maus dreht den Würfel", len(empfangen) >= 1 and empfangen[-1][0] > 0,
              str(empfangen[:3]))
        for r_ in ("+x", "-x", "+y", "-y", "+z", "-z", "iso"):
            w.blickrichtung(r_)
        app.processEvents()
        w.blickrichtung("+z")
        app.processEvents()
        oben_pos = np.asarray(w.plotter.camera_position[0], float)
        oben_ziel = np.asarray(w.plotter.camera_position[1], float)
        check("+z schaut von oben (aus +Z) auf das Modell", oben_pos[2] > oben_ziel[2],
              f"{np.round(oben_pos, 2)}")

        # Glasleiste: Symbole mit Text beim Ueberfahren, mittig, ohne "Alles holen"
        kn = w.glasleiste.knoepfe
        check("Glasleiste: Darstellung, Sichtbarkeit, Sicht, Fang und Auswahlart als Knöpfe",
              all(k in kn for k in ("Voll", "Drahtmodell", "knoten", "staebe", "flaechen",
                                    "volumen", "netz", "auswahl_weg", "nur_auswahl", "ausblenden",
                                    "zurueck", "alles", "fang", "auswahl_Knoten",
                                    "auswahl_Volumen", "auswahl_Netz")), str(sorted(kn)))
        check("„Alles deselektieren“ steht in der Glasleiste und nicht mehr im Schnellzugriff",
              kn["auswahl_weg"].defaultAction() is w.act_auswahl_weg
              and w.act_auswahl_weg.text() == "Alles deselektieren"
              and w.act_auswahl_weg not in w.ribbon.schnellzugriff.actions(),
              str([a.text() for a in w.ribbon.schnellzugriff.actions()]))
        check("Glasleiste: nur Symbole, der Text kommt beim Überfahren",
              all((not b.icon().isNull()) and b.toolTip()
                  and b.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly
                  for b in kn.values()),
              str([k for k, b in kn.items() if b.icon().isNull() or not b.toolTip()]))
        # Lager ein- und ausblendbar, in der Leiste zwischen Volumen und Netz (12.09.2026)
        reihe = list(kn)
        check("Glasleiste: Schalter „Lager“ zwischen Volumen und FE-Netz, Aktion des Ribbons",
              "lager" in kn and reihe.index("lager") == reihe.index("volumen") + 1
              and reihe.index("netz") == reihe.index("lager") + 1
              and kn["lager"].defaultAction() is w.act_lager and w.act_lager.isChecked(),
              str(reihe))
        if not w.model.supports:
            w.model.support(0, [0, 1, 2], name="Probe")
        w.act_lager.setChecked(False); w.redraw()
        namen = [n for n in w.plotter.renderer.actors if "supports" in n]
        check("Lager aus: keine Lagersymbole im Bild", not namen, str(namen[:3]))
        check("… und ein ausgeblendetes Lager lässt sich nicht wählen (Wahlregel)",
              not w._dargestellt("Lager") and not w._objekt_sichtbar("Lager", 0))
        w.act_lager.setChecked(True); w.redraw()
        namen = [n for n in w.plotter.renderer.actors if "supports" in n]
        check("Lager an: die Lagersymbole sind wieder da", bool(namen) and w._dargestellt("Lager"),
              str(namen[:3]))
        # Lagerart als Farbe, Beschriftung schaltbar (12.09.2026)
        from statik3d.gui import viewport as vpl
        farben = {tuple(round(c, 2) for c in list(w.plotter.renderer.actors[n].prop.color)[:3])
                  for n in namen if n.startswith("supports") and n != "supports_nichtlinear"}
        soll = {tuple(round(c, 2) for c in __import__("pyvista").Color(vpl.lager_farbe(s)).float_rgb)
                for s in w.model.supports}
        check("Knotenlager sind nach Lagerart gefärbt", farben == soll, f"{farben} / {soll}")
        w.act_lagertext.setChecked(True); w.redraw()
        check("Lagerbeschriftung an: ein Darsteller mit Text je Knotenlager",
              any(a.startswith("lagertext") for a in w.plotter.renderer.actors))
        w.act_lagertext.setChecked(False); w.redraw()
        check("Lagerbeschriftung aus", not any(a.startswith("lagertext") for a in w.plotter.renderer.actors))
        check("„Alles holen“ ist aus der Glasleiste weg",
              not any("zoom" in k.lower() or "holen" in k.lower() for k in kn))
        ansicht = w.centralWidget()
        mitte_leiste = w.glasleiste.x() + w.glasleiste.width() / 2
        # mittig - oder, wenn der Wuerfel im Weg ist, knapp links von ihm; reicht
        # die Breite (seit die Tabellen dem Fenster keine Mindestbreite mehr
        # aufzwingen, ist es unter xvfb 1280 px breit) fuer beide nebeneinander
        # nicht, rueckt der Wuerfel unter die Leiste - ueberschneiden nie.
        gl0_, wf0_ = w.glasleiste.geometry(), w.ansichtswuerfel.geometry()
        frei_vom_wuerfel = gl0_.right() < wf0_.x()
        wuerfel_darunter = (not gl0_.intersects(wf0_)) and wf0_.y() >= gl0_.bottom()
        check("die Glasleiste steht mittig oben und nie unter dem Würfel",
              (abs(mitte_leiste - ansicht.width() / 2) <= 3 or
               (frei_vom_wuerfel and abs(mitte_leiste - ansicht.width() / 2) < 60)
               or wuerfel_darunter)
              and (frei_vom_wuerfel or wuerfel_darunter) and w.glasleiste.y() <= 16,
              f"Mitte {mitte_leiste:.0f} von {ansicht.width()} px, y = {w.glasleiste.y()}, "
              f"rechts {gl0_.right()} / Würfel x {wf0_.x()} y {wf0_.y()}")

        # Schmales Fenster: Leiste und Wuerfel duerfen sich nie ueberschneiden
        breite_alt = w.width()
        w.resize(1100, 900)
        app.processEvents()
        w.ansichtsrand.platzieren()
        app.processEvents()
        gl_, wf_ = w.glasleiste.geometry(), w.ansichtswuerfel.geometry()
        check("im schmalen Fenster rückt der Würfel unter die Leiste, nichts überschneidet sich",
              not gl_.intersects(wf_) and wf_.width() > 100 and wf_.height() > 80
              and wf_.right() <= w.centralWidget().width(),
              f"Leiste {gl_.x()}..{gl_.right()} x {gl_.y()}..{gl_.bottom()}, "
              f"Würfel {wf_.x()}..{wf_.right()} x {wf_.y()}..{wf_.bottom()}")
        w.resize(breite_alt, 980)
        app.processEvents()
        w.ansichtsrand.platzieren()
        app.processEvents()

        # Ribbon: gleiche Hoehe, Gruppentitel auf gleicher Hoehe, Symbole
        register = w.ribbon.findChildren(ribm.Register)
        hoehen = {r_.minimumHeight() for r_ in register}
        check("alle Ribbonregister gleich hoch", len(register) > 5 and len(hoehen) == 1,
              str(hoehen))
        gruppen = w.ribbon.findChildren(ribm.Gruppe)
        check("Gruppentitel auf gleicher Höhe",
              len(gruppen) > 5 and len({g.minimumHeight() for g in gruppen}) == 1,
              str({g.minimumHeight() for g in gruppen}))
        knoepfe = [b for r_ in register for b in r_.findChildren(QtWidgets.QToolButton)]
        mit = sum(1 for b in knoepfe if not b.icon().isNull())
        check("Ribbonbefehle tragen Symbol und Text",
              mit >= 0.95 * len(knoepfe) and all(b.text() for b in knoepfe),
              f"{mit} von {len(knoepfe)} mit Symbol")
        check("Programmsymbol ist eine eigene Zeichnung",
              not symm.programmsymbol().isNull()
              and symm.programmbild(16).width() == 16 and symm.programmbild(256).width() == 256)

        # Staebe: bei Voll und Transparent mit Querschnittskontur, sonst als Linie
        w.load_example("hall")
        app.processEvents()
        w.darstellung_setzen("Voll")
        app.processEvents()
        akt = dict(w.plotter.renderer.actors)
        check("Voll: Stäbe als Körper mit Querschnittskontur",
              "model_stabkoerper" in akt, str([k for k in akt if k.startswith("model")]))
        pd_k = pvx.wrap(akt["model_stabkoerper"].GetMapper().GetInput())
        check("der Stabkörper kennt Element und Knoten je Zelle und Punkt",
              "elem" in pd_k.cell_data and "knoten" in pd_k.point_data and pd_k.n_cells > 0)
        w.darstellung_setzen("Drahtmodell")
        app.processEvents()
        akt = dict(w.plotter.renderer.actors)
        check("Drahtmodell: Stäbe als Linien",
              "model_stabkoerper" not in akt and "model_netz" in akt,
              str([k for k in akt if k.startswith("model")]))
        w.darstellung_setzen("Transparent")
        app.processEvents()
        check("Transparent: Stäbe als Körper",
              "model_stabkoerper" in dict(w.plotter.renderer.actors))
        w.darstellung_setzen("Voll")
        app.processEvents()

        # Sicht: Auswahl ausblenden, nur Auswahl, zurueck, alles
        stab = list(w.model.members)[0]
        elems = {int(e) for e in w.model.members[stab].elements}
        alle = set(range(len(w.model.elements)))
        w.sel_staebe = [stab]
        w.auswahl_ausblenden()
        app.processEvents()
        check("Auswahl ausblenden nimmt die Stabelemente aus dem Bild",
              w.versteckt["elemente"] == elems and not w.sel_staebe,
              str(sorted(w.versteckt["elemente"])))
        akt = dict(w.plotter.renderer.actors)
        gezeigt = set()
        for nm in ("model_stabkoerper", "model_netz"):
            if nm in akt:
                gezeigt |= set(np.asarray(pvx.wrap(akt[nm].GetMapper().GetInput())
                                          .cell_data["elem"]).tolist())
        check("und die Darsteller zeigen sie nicht mehr",
              elems.isdisjoint(gezeigt) and (alle - elems) <= gezeigt,
              f"{len(gezeigt)} Elemente im Bild")
        check("Vorherige Sicht ist dann möglich", w.act_sicht_zurueck.isEnabled())
        w.sicht_zurueck()
        app.processEvents()
        check("Vorherige Sicht holt sie zurück", not w.versteckt["elemente"])
        w.sel_staebe = [stab]
        w.nur_auswahl_zeigen()
        app.processEvents()
        check("Selektion anzeigen blendet den Rest aus",
              w.versteckt["elemente"] == alle - elems, str(len(w.versteckt["elemente"])))
        check("… und hebt die Auswahl danach auf - die Aufgabe ist erledigt (15.09.2026)",
              not w.sel_staebe and not len(w.selection) and not w.sel_elemente,
              f"Stäbe {w.sel_staebe}, Knoten {len(w.selection)}")
        stabknoten = {int(n) for e in elems for n in w.model.elements[e].nodes}
        akt = dict(w.plotter.renderer.actors)
        punkte = np.asarray(akt["knoten"].GetMapper().GetInput().points) if "knoten" in akt else np.zeros((0, 3))
        # gezeichnet werden die Knoten der Konstruktion (Stabenden, Lager);
        # die Zwischenknoten des geteilten Stabs sind Netzknoten (13.09.2026)
        netz_ = set(np.flatnonzero(vp.netzknoten_maske(w.model)).tolist())
        check("… auch die Knoten des Restes: nur die Stabknoten der Konstruktion bleiben als Punkte",
              w.versteckt["knoten"] == set(range(w.model.nn)) - stabknoten
              and len(punkte) == len(stabknoten - netz_) and len(stabknoten - netz_) >= 2,
              f"{len(punkte)} Punkte, {len(stabknoten)} Stabknoten ({len(stabknoten - netz_)} Konstruktion), "
              f"{len(w.versteckt['knoten'])} versteckt")
        lager_akt = [a for a in akt if a.startswith("supports")]
        lager_da = {int(s_.node) for s_ in w.model.supports} & stabknoten
        check("… und Lager nur an sichtbaren Knoten",
              bool(lager_akt) == bool(lager_da), str((lager_akt, sorted(lager_da))))
        check("Befehl heißt „Selektion anzeigen“", w.act_nur_auswahl.text() == "Selektion anzeigen",
              w.act_nur_auswahl.text())
        w.alles_zeigen()
        app.processEvents()
        check("Alles zeigen räumt auf",
              not any(w.versteckt.values()) and not w.act_alles_zeigen.isEnabled())
        w.sel_staebe = []
        # Doppelklicks, Taste r und Mausbewegung ohne Taste (16.09.2026: "beim
        # Heranzoomen springt der Zoom auf die Vollansicht zurueck")
        from PySide6 import QtCore, QtGui, QtTest
        it_ = w.plotter.interactor
        stil_ = w.plotter.iren.style
        pos_ = QtCore.QPointF(it_.width() / 2, it_.height() / 2)
        alt_menu_ = w._viewport_menu
        w._viewport_menu = lambda p: None

        def maus2_(typ_, knopf_, p_=None, knoepfe_=None):
            p_ = pos_ if p_ is None else p_
            ev_ = QtGui.QMouseEvent(typ_, p_, it_.mapToGlobal(p_.toPoint()), knopf_,
                                    knopf_ if knoepfe_ is None else knoepfe_, QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(it_, ev_)
            app.processEvents()

        def abstand_():
            """Kameralage: Standort, Blickpunkt und Parallelmassstab, gerundet.
            Der Rad-Zoom schiebt Standort und Blickpunkt gemeinsam laengs des
            Sehstrahls - der Abstand der beiden bliebe gleich, der Standort nicht."""
            kam_ = w.plotter.renderer.GetActiveCamera()
            return (tuple(np.round(kam_.GetPosition(), 6).tolist()), tuple(np.round(kam_.GetFocalPoint(), 6).tolist()),
                    round(float(kam_.GetParallelScale()), 6))

        w.zoom_alles(); app.processEvents()
        d_voll = abstand_()
        w.zoom_zum_zeiger(3.0, pos_.x(), pos_.y()); app.processEvents()
        d0_ = abstand_()
        check("Vorbedingung: Heranzoomen ändert die Kamera", d0_ != d_voll, f"{d_voll} -> {d0_}")
        maus2_(QtCore.QEvent.MouseButtonDblClick, QtCore.Qt.RightButton)
        maus2_(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.RightButton, knoepfe_=QtCore.Qt.NoButton)
        z_rechts = stil_.GetState()
        for k_ in range(1, 20):
            maus2_(QtCore.QEvent.MouseMove, QtCore.Qt.NoButton, pos_ + QtCore.QPointF(0, -5 * k_), QtCore.Qt.NoButton)
        check("Doppelklick rechts lässt VTK nicht in Dolly hängen: Bewegung ohne Taste zoomt nicht",
              z_rechts == 0 and abstand_() == d0_,
              f"Zustand {z_rechts}, Kamera {d0_} -> {abstand_()} (voll {d_voll})")
        maus2_(QtCore.QEvent.MouseButtonDblClick, QtCore.Qt.LeftButton)
        maus2_(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.LeftButton, knoepfe_=QtCore.Qt.NoButton)
        for k_ in range(1, 20):
            maus2_(QtCore.QEvent.MouseMove, QtCore.Qt.NoButton, pos_ + QtCore.QPointF(5 * k_, 0), QtCore.Qt.NoButton)
        check("Doppelklick links lässt VTK nicht in Rotate hängen",
              stil_.GetState() == 0 and abstand_() == d0_, f"Zustand {stil_.GetState()}, Kamera {d0_} -> {abstand_()}")
        it_.setFocus(); app.processEvents()
        QtTest.QTest.keyClick(it_, QtCore.Qt.Key_R); app.processEvents()
        check("Taste r im Bild setzt die Kamera nicht mehr zurück (VTK-Standard abgeschaltet)",
              abstand_() == d0_, f"Kamera {d0_} -> {abstand_()} (voll {d_voll})")
        zaehler_ = []
        alt_zoom = w.zoom_alles
        w.zoom_alles = lambda: (zaehler_.append(1), alt_zoom())
        w._rad_zeit = 0.0
        maus2_(QtCore.QEvent.MouseButtonDblClick, QtCore.Qt.MiddleButton)
        maus2_(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.MiddleButton, knoepfe_=QtCore.Qt.NoButton)
        n1_ = len(zaehler_)
        maus2_(QtCore.QEvent.MouseButtonDblClick, QtCore.Qt.MiddleButton)
        maus2_(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.MiddleButton, pos_ + QtCore.QPointF(30, 20),
               QtCore.Qt.NoButton)
        n2_ = len(zaehler_)
        w._rad_zeit = time.time()
        maus2_(QtCore.QEvent.MouseButtonDblClick, QtCore.Qt.MiddleButton)
        maus2_(QtCore.QEvent.MouseButtonRelease, QtCore.Qt.MiddleButton, knoepfe_=QtCore.Qt.NoButton)
        n3_ = len(zaehler_)
        w.zoom_alles = alt_zoom
        w._viewport_menu = alt_menu_
        check("Doppelklick mit der mittleren Maustaste passt alles Sichtbare ein (links und rechts nicht)",
              n1_ == 1, str(n1_))
        check("… nicht aber mit Zug (Drehen) oder gleich nach einem Radschritt",
              n2_ == 1 and n3_ == 1, f"{n2_} {n3_}")

        # Drehen eines grossen Modells: Nebendarsteller bleiben kurz weg
        w.SCHNELLDREHEN_AB = 1
        w.redraw()
        app.processEvents()
        kn_akt = w.plotter.renderer.actors.get("knoten")
        w._interaktion_beginnt()
        check("beim Drehen bleiben die Knotenpunkte weg",
              kn_akt is not None and not kn_akt.GetVisibility())
        w._interaktion_endet()
        check("und kommen beim Loslassen wieder", kn_akt is not None and kn_akt.GetVisibility())
        w.plotter.iren.style.InvokeEvent("StartInteractionEvent")
        check("das Drehen meldet sich über den Interaktionsstil",
              kn_akt is not None and not kn_akt.GetVisibility())
        w.plotter.iren.style.InvokeEvent("EndInteractionEvent")
        check("und das Loslassen auch", kn_akt is not None and kn_akt.GetVisibility())
        del w.SCHNELLDREHEN_AB

        # Texte im Bild: Kopfzeile oben links, Kennwerte unten links, Skalen rechts
        an = solver.solve_all(w.model, design=True)
        w._solve_done("all", an)
        w.cb_field.setCurrentText("Ausnutzung EC3")
        w.cb_diagram.setCurrentText("My")
        app.processEvents()
        check("Kopfzeile oben links nennt das Ergebnis",
              bool(w._kopfzeile_zeilen)
              and w.cb_result.currentText().split(":")[0] in w._kopfzeile_zeilen[0],
              str(w._kopfzeile_zeilen))
        akt = dict(w.plotter.renderer.actors)
        hoehe = w.plotter.render_window.GetSize()[1]
        kopf, kw = akt.get("kopfzeile"), akt.get("kennwerte")
        check("die Kopfzeile steht oben", kopf is not None and kopf.GetPosition()[1] > hoehe * 0.55,
              str(kopf.GetPosition() if kopf is not None else None))
        check("die Kennwerte stehen unten links",
              kw is not None and kw.GetPosition()[1] < 30 and kw.GetPosition()[0] < 30,
              str(kw.GetPosition() if kw is not None else None))
        # Nur die Werte des gewaehlten Ergebnisses (15.09.2026)
        check("Kennwerte nennen nur, was gewählt ist: Ausnutzung EC3 und der Verlauf My",
              any(z.startswith("max. Ausnutzung") for z in w._kennwerte_zeilen)
              and any(z.startswith("My ") for z in w._kennwerte_zeilen)
              and not any(z.startswith(("Rz", "phiy", "u ", "uz", "sig_v", "N ")) for z in w._kennwerte_zeilen),
              str(w._kennwerte_zeilen))
        w.cb_diagram.setCurrentText("kein Verlauf")
        w.cb_field.setCurrentText("uz")
        app.processEvents()
        check("… Färbung uz ohne Verlauf: allein die Zeile uz",
              [z.split()[0] for z in w._kennwerte_zeilen if z != "nur sichtbare Teile"] == ["uz"],
              str(w._kennwerte_zeilen))
        w.cb_field.setCurrentText("keine Färbung")
        app.processEvents()
        check("… keine Färbung und kein Verlauf: keine Kennwerte",
              not [z for z in w._kennwerte_zeilen if z != "nur sichtbare Teile"], str(w._kennwerte_zeilen))
        w.cb_field.setCurrentText("Ausnutzung EC3")
        w.cb_diagram.setCurrentText("My")
        app.processEvents()
        skalen = w.plotter.scalar_bars
        namen = list(skalen.keys())
        check("Farbskalen stehen senkrecht am rechten Rand",
              bool(namen) and all(skalen[n].GetOrientation() == 1
                                  and skalen[n].GetPosition()[0] > 0.75 for n in namen),
              str([(n, skalen[n].GetPosition()) for n in namen]))
        check("Ergebnis: Stäbe als Körper eingefärbt", "result_stabkoerper" in akt,
              str([k for k in akt if k.startswith("result")]))

        # Protokoll: ein neues Modell faengt mit leerem Blatt an
        w.log.appendPlainText("ALTES PROTOKOLL")
        w.new_model()
        app.processEvents()
        text = w.log.toPlainText()
        check("Neues Modell leert das Protokoll",
              "ALTES PROTOKOLL" not in text and "Neues Modell" in text, text[:60])

        # Krumme Flaechen: Coons-Flaeche zwischen den Randseiten
        r_ = 0.5
        t_ = np.linspace(0, np.pi, 17)
        unten = np.stack([r_ * np.cos(t_), r_ * np.sin(t_), np.zeros_like(t_)], axis=1)
        rechts = np.array([[-r_, 0, 0], [-r_, 0, 1.0]])
        oben = unten[::-1] + [0, 0, 1.0]
        links = np.array([[r_, 0, 1.0], [r_, 0, 0]])
        Pc, Dc = vpl.coons_flaeche([unten, rechts, oben, links])
        rad = np.linalg.norm(Pc[:, :2], axis=1)
        check("Coons-Fläche trifft den Zylinder genau",
              abs(rad.min() - r_) < 1e-9 and abs(rad.max() - r_) < 1e-9 and len(Dc) == 32,
              f"r = {rad.min():.4f}..{rad.max():.4f}, {len(Dc)} Dreiecke")
        mz = Mdl("Zylinder")
        mz.add_nodes(np.array([[0.5, 0, 0], [-0.5, 0, 0], [-0.5, 0, 1], [0.5, 0, 1]], float))
        mz.lines["unten"] = Line("unten", [0, 1], "arc",
                                 geometrie={"punkte": [[0.5, 0, 0], [0, 0.5, 0], [-0.5, 0, 0]]})
        mz.lines["rechts"] = Line("rechts", [1, 2])
        mz.lines["oben"] = Line("oben", [2, 3], "arc",
                                geometrie={"punkte": [[-0.5, 0, 1], [0, 0.5, 1], [0.5, 0, 1]]})
        mz.lines["links"] = Line("links", [3, 0])
        mz.flaechen["Mantel"] = Flaeche("Mantel", linien=["unten", "rechts", "oben", "links"])
        check("ein Zylindermantel ist nicht eben", not mz.flaechen["Mantel"].eben(mz))
        seiten = mz.flaechen["Mantel"].randseiten_punkte(mz)
        check("vier Randseiten im Umlauf, Ende = Anfang der nächsten",
              len(seiten) == 4 and all(np.allclose(seiten[i][-1], seiten[(i + 1) % 4][0])
                                       for i in range(4)), str([len(x) for x in seiten]))
        pl = pvx.Plotter(off_screen=True)
        vpl.add_geometrie(pl, mz, raender={}, seiten={})
        geo = pvx.wrap(pl.renderer.actors["geo_flaechen"].GetMapper().GetInput())
        rad = np.linalg.norm(geo.points[:, :2], axis=1)
        check("die krumme Fläche kommt als Coons-Fläche ins Bild",
              geo.n_cells > 4 and abs(rad.min() - 0.5) < 1e-6 and abs(rad.max() - 0.5) < 1e-6
              and "flaeche" in geo.cell_data, f"{geo.n_cells} Zellen, r = {rad.min():.3f}..{rad.max():.3f}")
        pl.close()
        # Auch die **Hervorhebung** der Auswahl muss dem Bogen folgen: als ein
        # ebenes Vieleck der Randpunkte spannte sie bei einem Halbkreis die
        # Sehne durch den Koerper (14.09.2026, Bohrungen der Buchsen)
        alt_modell = w.model
        w.model = mz
        w.sel_flaechen = ["Mantel"]
        w.refresh_all(); w.redraw(); app.processEvents()
        akt_ = dict(w.plotter.renderer.actors)
        flaeche_ = pvx.wrap(akt_["auswahl_flaechen"].GetMapper().GetInput()).area if "auswahl_flaechen" in akt_ else 0.0
        rad_ = np.linalg.norm(pvx.wrap(akt_["auswahl_flaechen"].GetMapper().GetInput()).points[:, :2], axis=1) \
            if "auswahl_flaechen" in akt_ else np.zeros(1)
        check("gewählte krumme Fläche leuchtet als Mantel, nicht als Keil durch den Körper "
              "(Halbzylinder r = 0,5 m, h = 1 m: π·r·h = 1,571 m², die Sehnenfläche wäre 1,0 m²)",
              abs(flaeche_ - np.pi * 0.5) < 0.02 and abs(rad_.min() - 0.5) < 1e-6 and abs(rad_.max() - 0.5) < 1e-6,
              f"{flaeche_:.3f} m², r = {rad_.min():.3f}..{rad_.max():.3f} m")
        w.sel_flaechen = []
        w.model = alt_modell
        w.refresh_all(); app.processEvents()
        pl = pvx.Plotter(off_screen=True)
        vpl.add_geometrie(pl, mz, raender={}, seiten={}, ausser_flaechen={"Mantel"})
        check("eine ausgeblendete Fläche fehlt im Bild", "geo_flaechen" not in pl.renderer.actors)
        pl.close()
        # --- Gefuellte Flaechen sparen ihre Oeffnungen aus (14.09.2026) ---
        ml = Mdl("Flansch")
        ml.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0],
                               [0.5, 0.5, 0], [1.5, 0.5, 0], [1.5, 1.5, 0], [0.5, 1.5, 0.]], float))
        for i in range(4):
            ml.lines[f"a{i}"] = Line(f"a{i}", [i, (i + 1) % 4])
            ml.lines[f"i{i}"] = Line(f"i{i}", [4 + i, 4 + (i + 1) % 4])
        ml.flaechen["Flansch"] = Flaeche("Flansch", linien=[f"a{i}" for i in range(4)],
                                         oeffnungen=[[f"i{i}" for i in range(4)]])
        polys_ = vpl.flaechenpolygone(ml, ml.flaechen["Flansch"])
        A_ = 0.0
        for Q in polys_:
            Q = np.asarray(Q, float)
            n_ = np.zeros(3)
            for j in range(len(Q)):
                n_ = n_ + np.cross(Q[j], Q[(j + 1) % len(Q)])
            A_ += 0.5 * float(np.linalg.norm(n_))
        check("Fläche mit Loch: die Füllung lässt das Loch frei (2x2 m minus 1x1 m = 3 m²)",
              abs(A_ - 3.0) < 1e-9, f"{A_:.4f} m² aus {len(polys_)} Vielecken")

        # Fuenf Randseiten, von denen zwei eine sind: RFEM teilt eine gerade
        # Kante schon einmal in zwei Linien. Ohne Zusammenfassen faellt die
        # Flaeche auf den Faecher um den Schwerpunkt zurueck - und der spannt
        # bei einem Halbkreis die Sehne durch den Koerper.
        mz5 = Mdl("Zylinder5")
        mz5.add_nodes(np.array([[0.5, 0, 0], [-0.5, 0, 0], [-0.5, 0, 0.1],
                                [-0.5, 0, 1.0], [0.5, 0, 1.0]], float))
        mz5.lines["unten"] = Line("unten", [0, 1], "arc",
                                  geometrie={"punkte": [[0.5, 0, 0], [0, 0.5, 0], [-0.5, 0, 0]]})
        mz5.lines["r1"] = Line("r1", [1, 2])
        mz5.lines["r2"] = Line("r2", [2, 3])
        mz5.lines["oben"] = Line("oben", [3, 4], "arc",
                                 geometrie={"punkte": [[-0.5, 0, 1.0], [0, 0.5, 1.0], [0.5, 0, 1.0]]})
        mz5.lines["links"] = Line("links", [4, 0])
        mz5.flaechen["Mantel"] = Flaeche("Mantel",
                                         linien=["unten", "r1", "r2", "oben", "links"])
        s5 = mz5.flaechen["Mantel"].randseiten_punkte(mz5)
        check("der geteilte Rand liefert fünf Randseiten", len(s5) == 5,
              str([len(x) for x in s5]))
        vier = vpl.seiten_zusammenfassen(list(s5))
        check("an der glatten Ecke werden daraus vier", len(vier) == 4,
              str([len(x) for x in vier]))
        ring5 = mz5.flaechen["Mantel"].randpunkte(mz5)
        P5, Z5 = vpl.flaechen_dreiecke(ring5, s5, [])
        P5 = np.asarray(P5, float)
        rad5 = np.linalg.norm(P5[:, :2], axis=1)
        check("die gezeichnete Fläche liegt genau auf dem Zylinder",
              abs(rad5.min() - 0.5) < 1e-9 and abs(rad5.max() - 0.5) < 1e-9,
              f"r = {rad5.min():.9f}..{rad5.max():.9f}")

        def _flaecheninhalt(P, Z):
            P = np.asarray(P, float)
            i, A = 0, 0.0
            while i < len(Z):
                k = int(Z[i])
                Q = P[[int(x) for x in Z[i + 1:i + 1 + k]]]
                i += k + 1
                A += 0.5 * float(np.linalg.norm(
                    np.cross(Q, np.roll(Q, -1, axis=0)).sum(axis=0)))
            return A

        bogen = float(np.linalg.norm(np.diff(np.asarray(s5[0], float), axis=0), axis=1).sum())
        A5 = _flaecheninhalt(P5, Z5)
        check("und ihr Inhalt ist Bogenlänge mal Höhe (Regelfläche)",
              abs(A5 - bogen * 1.0) < 1e-9,
              f"{A5:.9f} m² / {bogen * 1.0:.9f} m²")
        # Der Faecher haette den Schwerpunkt des Randes als Ecke - und der
        # liegt beim Halbkreis 0,18 m innerhalb des Mantels: seine Dreiecke
        # laufen durch den Koerper. Am Drehlagermodell zeichnete er den
        # Bolzenmantel (F589) mit 2011 statt 645 cm², also 212 % zu gross.
        mitte = np.asarray(ring5, float).mean(axis=0)
        check("der Fächer um den Schwerpunkt liefe durch den Körper",
              abs(float(np.linalg.norm(mitte[:2])) - 0.5) > 0.1,
              f"Schwerpunkt bei r = {float(np.linalg.norm(mitte[:2])):.3f} m statt 0,5 m")

        # Was eben ist, sagt die Quelldatei - nicht eine Messung. Der
        # Planaritätstest hängt an seiner Eingabe: befragt man nur die vier
        # Eckknoten eines Bohrungsmantels, liegen sie in einer Ebene, obwohl
        # die Fläche sich um den Bohrungsradius wölbt.
        from statik3d.model import polygon_eben as _peben
        ecken4 = np.array([[0.5, 0, 0], [-0.5, 0, 0], [-0.5, 0, 1.0], [0.5, 0, 1.0]])
        check("die vier Eckknoten eines Zylindermantels liegen in einer Ebene",
              _peben(ecken4), str(np.round(ecken4, 3).tolist()))
        P_o, Z_o = vpl.flaechen_dreiecke(ecken4, seiten, [], typ="")
        check("wer nur sie befragt, hält den Mantel für eben",
              P_o is not None and len(Z_o) == 5, f"{len(Z_o)} Zelleinträge")
        P_t, Z_t = vpl.flaechen_dreiecke(ecken4, seiten, [], typ="regelflaeche")
        r_t = np.linalg.norm(np.asarray(P_t, float)[:, :2], axis=1)
        check("mit typ='regelflaeche' aus der Quelldatei liegt sie auf dem Zylinder",
              len(Z_t) > 5 and abs(r_t.min() - 0.5) < 1e-9 and abs(r_t.max() - 0.5) < 1e-9,
              f"{len(Z_t)} Zelleinträge, r = {r_t.min():.6f}..{r_t.max():.6f} m")
        P_g, _Z_g = vpl.flaechen_dreiecke(np.asarray(ring5, float), s5, [], typ="eben")
        r_g = np.linalg.norm(np.asarray(P_g, float)[:, :2], axis=1)
        check("und typ='eben' macht aus einer gewölbten Fläche keine ebene",
              abs(r_g.max() - 0.5) < 1e-9, f"größter Radius {r_g.max():.6f} m")

        # Fünf Randlinien, vier benannte Ecken: an den Ecken zerlegt, nicht geraten
        vier = vpl.seiten_an_ecken(s5, np.array([
            [0.5, 0, 0], [-0.5, 0, 0], [-0.5, 0, 1.0], [0.5, 0, 1.0]]))
        check("die vier benannten Ecken zerlegen fünf Randseiten in vier",
              len(vier) == 4 and all(np.allclose(vier[i][-1], vier[(i + 1) % 4][0])
                                     for i in range(4)),
              str([len(x) for x in vier]))
        check("ohne Ecken bleibt es beim Zusammenfassen an der glatten Ecke",
              not vpl.seiten_an_ecken(s5, None)
              and len(vpl.seiten_zusammenfassen(list(s5))) == 4, "")
        _ = P_o, P_t

        # Wo ein Netz steht, wird das Netz gezeichnet: die Randflaechen eines
        # vernetzten Koerpers liegen sonst deckungsgleich auf seiner Netzhaut.
        from statik3d.model import Volumenkoerper as VK, Material as Mat
        mk = Mdl("Wuerfel")
        mk.add_material(Mat.steel("S235"))
        E = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
        mk.add_nodes(E)
        ecken = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7)]
        for i, (a, b) in enumerate(ecken):
            mk.lines[f"L{i}"] = Line(f"L{i}", [a, b])
        seiten_k = {"unten": [0, 1, 2, 3], "oben": [4, 5, 6, 7],
                    "vorn": [0, 9, 4, 8], "rechts": [1, 10, 5, 9],
                    "hinten": [2, 11, 6, 10], "links": [3, 8, 7, 11]}
        for fn, ls in seiten_k.items():
            mk.flaechen[fn] = Flaeche(fn, linien=[f"L{i}" for i in ls], material="S235")
        mk.koerper["K"] = VK("K", flaechen=list(seiten_k), material="S235")
        pd_f, pd_r, _pd_k = vpl.geometrie_netze(mk, {}, {})
        check("ohne Netz werden die sechs Würfelflächen gemalt",
              pd_f is not None and pd_f.n_cells == 6, str(None if pd_f is None else pd_f.n_cells))
        mk.add_element("hex8", list(range(8)), "S235", group="K")
        mk.koerper["K"].elemente = [0]
        pd_f, pd_r, _pd_k = vpl.geometrie_netze(mk, {}, {})
        check("mit Netz keine einzige Fläche mehr - das Netz zeichnet sie",
              pd_f is None, str(None if pd_f is None else pd_f.n_cells))
        check("die Umrisse bleiben aber stehen",
              pd_r is not None and pd_r.n_cells == 24, str(None if pd_r is None else pd_r.n_cells))
        # und ein Klick auf das Netz findet trotzdem die richtige Flaeche
        vorher = w.model
        try:
            w.model = mk
            w._kflaechen_stand = None
            w._raender_stand = None
            treffer = [(w._flaeche_am_punkt("K", p), soll) for p, soll in (
                ((0.5, 0.5, 0.0), "unten"), ((0.5, 0.5, 1.0), "oben"),
                ((0.5, 0.0, 0.5), "vorn"), ((1.0, 0.5, 0.5), "rechts"),
                ((0.5, 1.0, 0.5), "hinten"), ((0.0, 0.5, 0.5), "links"))]
        finally:
            w.model = vorher
            w._kflaechen_stand = None
            w._raender_stand = None
        check("ein Punkt auf dem Netz nennt die Fläche, auf der er liegt",
              all(a == b for a, b in treffer), str(treffer))

        # Haltegüte: „gehalten" ist keine Ja-Nein-Auskunft
        from statik3d import singular as _sg
        zeilen0 = w.log.toPlainText().count("\n")
        w._halteguete_melden([
            _sg.Halteguete(wert=0.25, koerper=["V1"], text="V1: gut gehalten"),
            _sg.Halteguete(wert=0.02, koerper=["V2"], text="V2: mäßig gehalten")])
        text = w.log.toPlainText()
        check("über der Schwelle nennt das Protokoll das weichste Teil",
              "Haltegüte: am weichsten V2: mäßig gehalten" in text
              and "WARNUNG" not in text.split("Haltegüte: am weichsten")[-1],
              text.splitlines()[-1][:120])
        w._halteguete_melden([
            _sg.Halteguete(wert=1e-6, koerper=["V3"],
                           text="V3: in Richtung y nur 1.0e-06 der steifsten Halterung")])
        check("darunter wird gewarnt, mit Bauteil, Richtung und Wert",
              w.log.toPlainText().splitlines()[-1]
              == "WARNUNG: V3: in Richtung y nur 1.0e-06 der steifsten Halterung",
              w.log.toPlainText().splitlines()[-1][:120])
        _ = zeilen0
        # Die Darstellungsarten gelten auch fuer Flaechen und Volumen ohne Netz
        from statik3d.model import Volumenkoerper
        mz.koerper["K1"] = Volumenkoerper("K1", flaechen=["Mantel"])
        for modus in ("Voll", "Transparent", "Hidden-Line", "Drahtmodell"):
            pl = pvx.Plotter(off_screen=True)
            vpl.add_geometrie(pl, mz, raender={}, seiten={}, modus=modus)
            akt = dict(pl.renderer.actors)
            fl = akt.get("geo_flaechen")
            if modus == "Drahtmodell":
                ok = fl is None and "geo_raender" in akt
            else:
                deckkraft = fl.GetProperty().GetOpacity() if fl is not None else -1
                farbe = fl.GetProperty().GetColor() if fl is not None else None
                ok = fl is not None and "geo_raender" in akt and (
                    (modus == "Voll" and deckkraft >= 0.99 and farbe[0] < 0.7)
                    or (modus == "Transparent" and deckkraft < 0.6)
                    or (modus == "Hidden-Line" and deckkraft >= 0.99 and min(farbe) > 0.95))
            check(f"Geometrie ohne Netz folgt der Darstellungsart {modus}", ok,
                  str(sorted(akt)))
            pl.close()

        # Startbild
        from statik3d.gui import start as st
        pm = st.startbild("9.9.9", "abc1234")
        check("Startbild wird gezeichnet", not pm.isNull() and pm.width() == st.BREITE
              and pm.height() == st.HOEHE)
        check("Startbild: eine echte Schrift ist da (kein Kästchenbild)", st.schrift_vorhanden(),
              QtGui.QFontInfo(st.schrift(12)).family())
        sb = st.Startbild(version="9.9.9", stand="abc1234")
        sb.show()
        sb.melden("Grafik und Rechenkern werden geladen …")
        app.processEvents()
        check("Startbild zeigt die Meldung", sb.isVisible()
              and sb.message() == "Grafik und Rechenkern werden geladen …", sb.message())
        sb.fertig(w)
        app.processEvents()
        check("und schließt sich, sobald das Fenster steht", not sb.isVisible())
        check("ohne Packer bleibt packer_schliessen folgenlos",
              st.packer_schliessen() is None and st.packer_melden("x") is None)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Neue Oberfläche", False, str(ex)[:70])

    # ---- Lasten: Masken, Tabelle, Bild; Auswahl per Zellenpicker; Import-Haken ----
    try:
        import pyvista as pvx
        from statik3d.gui.dialogs import ImportDialog
        w.load_example("hall")
        app.processEvents()
        lc = w.model.case()
        stab = list(w.model.members)[0]
        n0 = len(lc.beam_loads)
        w.sel_staebe = [stab]
        w._linienlast_aufbringen({"qx": 0, "qy": 0, "qz": -10.0, "trapez": True, "q2x": 0,
                                  "q2y": 0, "q2z": -20.0, "system": "global", "von": 0.5,
                                  "bis": 0.0, "fall": lc.name})
        app.processEvents()
        check("Linienlast-Maske haengt die Last an den Stab und verteilt sie",
              len(lc.linienlasten) == 1 and lc.linienlasten[0].von == 0.5
              and len(lc.beam_loads) > n0 and all(getattr(b, "_geo", False)
                                                  for b in lc.beam_loads[n0:]),
              f"{len(lc.linienlasten)} Linienlasten, {len(lc.beam_loads) - n0} Elementlasten")
        w.sel_staebe = []
        meldungen = []
        fehler_alt = w.error
        w.error = lambda msg: meldungen.append(str(msg))
        w._linienlast_aufbringen({"qz": -1.0, "fall": lc.name})
        w.error = fehler_alt
        check("ohne Auswahl sagt die Maske es (keine zweite Last)",
              len(lc.linienlasten) == 1 and meldungen and "wählen" in meldungen[0])
        w.sel_staebe = [stab]
        w._temperaturlast_aufbringen({"dT": 25.0, "dTz": 0.0, "alle": False, "fall": lc.name})
        n_t = len(lc.temp_loads)
        check("Temperatur-Maske auf den gewaehlten Stab",
              n_t == len(w.model.members[stab].elements) and lc.temp_loads[0].dT == 25.0)
        w.sel_staebe = []
        knoten = int(w.model.supports[0].node)
        w._set_selection([knoten])
        w._zwangsverformung_aufbringen({"ux": 0, "uy": 0, "uz": -3.0, "px": 0, "py": 0,
                                        "pz": 0, "lager": True, "fall": lc.name})
        check("Zwangsverformungs-Maske am gewaehlten gelagerten Knoten",
              len(lc.zwangsverformungen) == 1 and lc.zwangsverformungen[0].dofs == [2]
              and abs(lc.zwangsverformungen[0].u[2] + 0.003) < 1e-12)
        w.clear_selection()
        # Lastentabelle: Objektlasten drin, abgeleitete Elementlasten nicht
        w.tabelle_zeigen("Lasten")
        app.processEvents()
        arten = [str(z[2]) for z in w.tbl_last.modell.zeilen]
        check("Lastentabelle zeigt Linienlast, Temperatur und Zwangsverformung",
              "Linienlast" in arten and "Zwangsverformung" in arten and "Temperatur" in arten,
              str(sorted(set(arten))))
        check("und keine abgeleiteten Elementlasten",
              sum(1 for z in w.tbl_last.modell.zeilen if str(z[2]) == "Streckenlast")
              == sum(len(c.eigene("beam_loads")) for c in w.model.load_cases.values()))
        akt = dict(w.plotter.renderer.actors)
        check("Lasten im Bild: Pfeile, Temperaturpunkte, Zwang",
              "loads" in akt and "temp_warm" in akt and "zwang" in akt,
              str([k for k in akt if k in ("loads", "temp_warm", "temp_kalt", "zwang")]))
        # Loeschen ueber die Tabelle nimmt die Objektlast samt Ableitungen
        zeile = next(i for i, z in enumerate(w.tbl_last.modell.zeilen) if str(z[2]) == "Linienlast")
        w.tbl_last.view.selectRow(zeile)
        w.last_loeschen()
        check("Loeschen der Linienlast nimmt ihre Elementlasten mit",
              not lc.linienlasten and len(lc.beam_loads) == n0,
              f"{len(lc.linienlasten)} Linienlasten, {len(lc.beam_loads)} statt {n0} Stablasten")
        w.sel_staebe = [stab]
        w.redraw()
        app.processEvents()
        check("die Auswahl leuchtet in einem einzigen Darsteller",
              "auswahl" in dict(w.plotter.renderer.actors)
              and not any(k.startswith("sel_") for k in dict(w.plotter.renderer.actors)))
        w.sel_staebe = []
        # Flaechenlast-Maske auf der Platte (Flaeche aus allen Schalen)
        w.load_example("plate")
        app.processEvents()
        from statik3d.model import Flaeche
        w.model.flaechen["F1"] = Flaeche("F1", linien=[], elemente=list(range(len(w.model.elements))))
        w.sel_flaechen = ["F1"]
        lcp = w.model.case()
        w._flaechenlast_aufbringen({"p": 2.0, "richtung": "senkrecht zur Fläche (Druck)",
                                    "projiziert": False, "verlauf": "linear von Punkt A nach B",
                                    "p2": 6.0, "ax": 0, "ay": 0, "az": 0, "bx": 3, "by": 0, "bz": 0,
                                    "fall": lcp.name})
        check("Flaechenlast-Maske: lineare Last auf die Flaeche, verteilt auf die Elemente",
              len(lcp.geometrielasten) == 1 and lcp.geometrielasten[0].verlauf
              and len([f for f in lcp.face_loads if getattr(f, "_geo", False)]) == len(w.model.elements))
        w.sel_flaechen = []
        # Auswahl per Zellenpicker: Klick auf die Platte trifft die Flaeche
        w.blickrichtung("+z")
        w.zoom_alles()
        app.processEvents()
        breite, hoehe = w.plotter.render_window.GetSize()
        w.plotter.iren.interactor.SetEventPosition(breite // 2, hoehe // 2)
        check("Zellenpicker findet die Flaeche unter dem Zeiger",
              w._objekt_am_zeiger("Fläche") == "F1", str(w._objekt_am_zeiger("Fläche")))
        w.auswahlart_setzen("Fläche")
        w._picked(np.array([1.5, 1.0, 0.0]))
        app.processEvents()
        check("und der Klick waehlt sie aus", w.sel_flaechen == ["F1"], str(w.sel_flaechen))
        w.auswahlart_setzen("Knoten")
        w.sel_flaechen = []
        # Importdialog: Z-Achse-Haken nur bei RFEM-Dateien, Option kommt an
        d = ImportDialog(w, "x.rf6", w.model)
        check("Importdialog rf6: Haken „Z nach unten“ vorbelegt und als Option",
              d.z_unten.isChecked() and d.options().get("z_drehen") is True)
        d.append.setChecked(True)
        check("beim Anhaengen ist der Haken gesperrt", not d.z_unten.isEnabled()
              and d.options().get("z_drehen") is False)
        d2 = ImportDialog(w, "x.dxf", w.model)
        check("bei anderen Dateien keine Drehung", d2.options().get("z_drehen") is False)
        # Drehung um x: Knoten und Lasten
        from statik3d.model import Model as Mdl
        mz = Mdl("Dreh")
        mz.add_nodes(np.array([[1.0, 2.0, 3.0]]))
        mz.load_node(0, Fx=1, Fy=2, Fz=3, Mx=4, My=5, Mz=6)
        mz.um_x_drehen()
        check("um_x_drehen: (x, y, z) -> (x, -y, -z), Kraefte und Momente mit",
              np.allclose(mz.nodes[0], [1, -2, -3])
              and mz.case().nodal_loads[0].F == [1, -2, -3, 4, -5, -6])
        # Ansichtswuerfel zeichnet sich mit Schatten und Knopfzeile
        pm = QtGui.QPixmap(w.ansichtswuerfel.size())
        pm.fill(QtGui.QColor("#ffffff"))
        w.ansichtswuerfel.render(pm)
        bild = pm.toImage()
        farben = {bild.pixelColor(x, y).name() for x in range(0, bild.width(), 4)
                  for y in range(0, bild.height(), 4)}
        check("der Ansichtswuerfel ist gezeichnet (viele Farbstufen)", len(farben) > 25, str(len(farben)))
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Lasten und Auswahl", False, str(ex)[:70])

    # ---- Eigenschaftsmasken rechts: Lastfall, Kombination, Werkstoff, Dicke ---
    try:
        from statik3d.model import ShellProp as ShP_
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w._bestaetigen = lambda text: True
        w._baum_geklickt("lastfall", "LF1")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Klick auf einen Lastfall: Eigenschaftsmaske rechts (Name, Nummer, Einwirkung, Situation, Theorie, g_z)",
              mk is not None and mk.titel == "Lastfall LF1" and w.eingaben_dock.windowTitle() == "Lastfall LF1"
              and all(k in mk.werte() for k in ("name", "nummer", "kategorie", "beschreibung", "situation",
                                                 "theorie", "g_z", "psi", "aktiv")), str(mk.titel if mk else None))
        mk.setzen("name", "LF!")
        mk.setzen("nummer", 3)
        mk.setzen("beschreibung", "umbenannt")
        mk.setzen("aktiv", True)
        mk.anwenden()
        app.processEvents()
        check("Umbenennen aus der Maske: Modell, Kombinationen und aktiver Lastfall folgen",
              "LF!" in m_.load_cases and "LF1" not in m_.load_cases and m_.load_cases["LF!"].nummer == 3
              and m_.active_case == "LF!" and all("LF1" not in c.factors for c in m_.combinations.values())
              and not fehler_, str(fehler_))
        w._baum_bearbeiten("lastfall", "LF1")
        app.processEvents()
        check("Bearbeiten eines nicht mehr vorhandenen Namens stürzt nicht (Zweigmaske)", not fehler_, str(fehler_))
        w._baum_neu("lastfaelle")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Neu aus dem Zweig: Maske „Neu: Lastfall“ mit OK und Abbrechen",
              mk is not None and mk.titel.startswith("Neu: Lastfall") and mk.btn_abbrechen is not None)
        n_lf = len(m_.load_cases)
        mk.anwenden()
        app.processEvents()
        check("OK legt den Lastfall an", len(m_.load_cases) == n_lf + 1 and not fehler_, str(fehler_))
        kname_ = list(m_.combinations)[0]
        w._baum_geklickt("kombination", kname_)
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("faktoren", "LF!: 1.35, S: 1.5")
        mk.anwenden()
        app.processEvents()
        check("Kombinationsmaske: Faktoren als Text übernommen",
              m_.combinations[kname_].factors == {"LF!": 1.35, "S": 1.5} and not fehler_, str(fehler_))
        mk.setzen("faktoren", "gibtsnicht: 1")
        mk.anwenden()
        app.processEvents()
        check("unbekannter Lastfall in den Faktoren wird abgewiesen", fehler_ and "gibtsnicht" in fehler_[-1])
        fehler_.clear()
        wname_ = list(m_.materials)[0]
        w._baum_geklickt("werkstoff", wname_)
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("name", "S355x")
        mk.setzen("fy", "355")
        mk.anwenden()
        app.processEvents()
        check("Werkstoffmaske: Umbenennen zieht die Elemente mit, f_y in N/mm²",
              "S355x" in m_.materials and all(e.mat != wname_ for e in m_.elements)
              and abs(m_.materials["S355x"].fy - 355e6) < 1 and not fehler_, str(fehler_))
        m_.add_shell_prop(ShP_("t9", 0.012))
        w.refresh_all()
        w._baum_geklickt("dicke", "t9")
        app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("t", 15.0)
        mk.anwenden()
        app.processEvents()
        check("Dickenmaske: t in mm", abs(m_.shells["t9"].t - 0.015) < 1e-12 and not fehler_, str(fehler_))
        w.selection = np.array([0, 1], int)
        w._auswahl_register()
        app.processEvents()
        w.selection = np.array([], int)
        w._auswahl_register()
        app.processEvents()
        w.refresh_all()
        app.processEvents()
        check("Kontextregister weg: refresh_all greift nicht auf gelöschte Felder zu", True)
        w.error = alt_error
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Eigenschaftsmasken rechts", False, str(ex)[:70])

    # ---- Tabellen unten direkt bearbeiten, Aufklapplisten ---------------------
    try:
        from PySide6 import QtCore
        from statik3d.model import Material as Mat_, ShellProp as ShP_
        from statik3d.schweissnaehte import Schweissnaht as Sn_
        w.new_model()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        mat_ = list(m_.materials)[0]
        m_.add_material(Mat_("S2"))
        t0_ = list(m_.shells)[0]
        m_.add_shell_prop(ShP_("t2", 0.02))
        ids_ = [m_.add_node(0, 0, 0), m_.add_node(4, 0, 0), m_.add_node(4, 2, 0), m_.add_node(0, 2, 0),
                m_.add_node(0, 0, 2)]
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            m_.add_line(f"L{i}", [ids_[a], ids_[b]])
        m_.add_flaeche("F1", ["L0", "L1", "L2", "L3"], dicke=t0_, material=mat_, teilung=[2, 2])
        e0 = m_.add_element("beam", [ids_[0], ids_[4]], mat_, list(m_.sections)[0])
        m_.schweissnaehte["N1"] = Sn_("N1", art="Kehlnaht", a=5.0)
        w.refresh_all()
        app.processEvents()
        check("Tabelle „Stäbe“ (statt „Elemente“) in der Gruppe Modell",
              "Stäbe" in w.tab_unten.tabellen("Modell") and "Elemente" not in w.tab_unten.tabellen("Modell"),
              str(w.tab_unten.tabellen("Modell")))

        def setz_(tbl, zeile, spalte, wert):
            md = tbl.modell
            ok = md.setData(md.index(zeile, spalte), wert, QtCore.Qt.EditRole)
            app.processEvents()
            return ok

        check("Linien: Knotenfolge und Bemerkung in der Zelle bearbeitbar",
              setz_(w.tbl_linie, 0, 4, f"{ids_[0]}, {ids_[2]}") and m_.lines["L0"].nodes == [ids_[0], ids_[2]]
              and setz_(w.tbl_linie, 0, 5, "Kante") and m_.lines["L0"].comment == "Kante")
        check("Linien: unbekannte Knoten werden abgewiesen", not setz_(w.tbl_linie, 0, 4, "99, 100"))
        z_e = [i for i, z in enumerate(w.tbl_elem.modell.zeilen) if int(z[0]) == e0][0]
        check("Stäbe: Knoten und Werkstoff in der Zelle bearbeitbar",
              setz_(w.tbl_elem, z_e, 2, f"{ids_[1]}, {ids_[4]}") and m_.elements[e0].nodes == [ids_[1], ids_[4]]
              and setz_(w.tbl_elem, z_e, 3, "S2") and m_.elements[e0].mat == "S2")
        sp_ = w.tbl_elem.modell.spalten
        check("Wahlspalten kennen die Aufklappwerte (Werkstoffe, Querschnitte je Zeile)",
              sp_[3].art == "wahl" and "S2" in sp_[3].wahlwerte(w.tbl_elem.modell.zeilen[z_e])
              and set(sp_[4].wahlwerte(w.tbl_elem.modell.zeilen[z_e])) == set(m_.sections))
        view_ = w.tbl_elem.view
        deleg_ = view_.itemDelegate()
        idx_ = w.tbl_elem.filter.mapFromSource(w.tbl_elem.modell.index(z_e, 3))
        ed_ = deleg_.createEditor(view_, QtWidgets.QStyleOptionViewItem(), idx_)
        check("Aufklappliste als Zelleditor der Wahlspalte", isinstance(ed_, QtWidgets.QComboBox) and ed_.count() >= 2)
        ed_.setCurrentText(mat_)
        deleg_.setModelData(ed_, w.tbl_elem.filter, idx_)
        app.processEvents()
        check("Auswahl aus der Aufklappliste landet im Modell", m_.elements[e0].mat == mat_)
        check("Flächen: Dicke, Werkstoff, Teilung in der Zelle bearbeitbar; falsche Randlinie abgewiesen",
              setz_(w.tbl_geoflaeche, 0, 2, "t2") and m_.flaechen["F1"].dicke == "t2"
              and setz_(w.tbl_geoflaeche, 0, 3, "S2") and m_.flaechen["F1"].material == "S2"
              and setz_(w.tbl_geoflaeche, 0, 4, "3 × 5") and m_.flaechen["F1"].teilung == [3, 5]
              and not setz_(w.tbl_geoflaeche, 0, 1, "L0, Lx, L2"))
        check("Schweißnähte: Nahtart, a und Lage in der Zelle bearbeitbar, Kerbfall folgt",
              setz_(w.tbl_naht, 0, 1, "Stumpfnaht") and m_.schweissnaehte["N1"].art == "Stumpfnaht"
              and setz_(w.tbl_naht, 0, 3, 7.0) and m_.schweissnaehte["N1"].a == 7.0
              and setz_(w.tbl_naht, 0, 2, "quer") and m_.schweissnaehte["N1"].lage == "quer")
        app.processEvents()
        check("Nahttabelle nach der Änderung neu gefüllt", w.tbl_naht.modell.zeilen[0][1] == "Stumpfnaht")
        w.undo()
        app.processEvents()
        check("Zelländerung ist rückgängig machbar", w.model.schweissnaehte["N1"].lage == "längs")
        w.error = alt_error
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Tabellen direkt bearbeiten", False, str(ex)[:70])

    # ---- Mehrfachauswahl, Randlinien anklicken, intelligente Auswahl, Leuchten --
    try:
        from PySide6 import QtCore
        from statik3d.gui import masken as msk_
        w.new_model()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        mat_, t0_, sec_ = list(m_.materials)[0], list(m_.shells)[0], list(m_.sections)[0]
        # Kette 0-1-2-3, an 3 Verzweigung nach 4 und 5; Ring 6-7-8-9 als Fläche F1
        P_ = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 1, 0), (4, -1, 0),
              (0, 3, 0), (2, 3, 0), (2, 5, 0), (0, 5, 0)]
        ids_ = [m_.add_node(*p) for p in P_]
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)]):
            m_.add_line(f"L{i}", [ids_[a], ids_[b]])
        for i, (a, b) in enumerate([(6, 7), (7, 8), (8, 9), (9, 6)]):
            m_.add_line(f"R{i}", [ids_[a], ids_[b]])
        m_.add_flaeche("F1", ["R0", "R1", "R2", "R3"], dicke=t0_, material=mat_, teilung=[2, 2])
        e_ = [m_.add_element("beam", [ids_[a], ids_[b]], mat_, sec_)
              for a, b in [(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)]]
        for i, e in enumerate(e_):
            m_.add_member(f"M{i}", [e])
        w.refresh_all(); app.processEvents()
        t_ = w.tbl_knoten
        check("Tabellen: Mehrfachauswahl mit Umschalt/Strg (ExtendedSelection)",
              t_.view.selectionMode() == QtWidgets.QAbstractItemView.ExtendedSelection)
        sm_ = t_.view.selectionModel(); sm_.clearSelection()
        for r in (0, 2, 5):
            sm_.select(t_.filter.index(r, 0), QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        t_._geklickt(t_.filter.index(5, 0)); app.processEvents()
        check("drei Knotenzeilen markiert -> drei Knoten in der Ansicht, Zeilen bleiben markiert",
              len(w.selection) == 3 and len(sm_.selectedRows()) == 3
              and sorted(int(x) for x in t_.gewaehlte_schluessel()) == sorted(int(x) for x in w.selection),
              str(w.selection.tolist()))
        t2_ = w.tbl_elem; sm2_ = t2_.view.selectionModel(); sm2_.clearSelection()
        for r in (0, 1):
            sm2_.select(t2_.filter.index(r, 0), QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        t2_._geklickt(t2_.filter.index(1, 0)); app.processEvents()
        check("zwei Stabzeilen -> die Knoten beider Elemente, Statuszeile nennt Tabellenzeilen",
              len(w.selection) == 3 and "2 Tabellenzeilen" in w.lbl_sel.text(), w.lbl_sel.text())
        enden_ = w._linienenden()
        check("Kette: L0 -> L0, L1, L2 (hält an der Verzweigung); Ring R0 -> alle vier; L3 allein",
              w._kette("L0", enden_, set(enden_)) == ["L0", "L1", "L2"]
              and sorted(w._kette("R0", enden_, set(enden_))) == ["R0", "R1", "R2", "R3"]
              and w._kette("L3", enden_, set(enden_)) == ["L3"])
        w.auswahlart_setzen("Linie"); w.sel_linien = []
        w.act_klug.setChecked(True)
        w._objekt_umschalten_klug(w.sel_linien, "L1", "Linien", enden_)
        w._objekt_umschalten_klug(w.sel_linien, "L3", "Linien", enden_)
        zug_ = list(w.sel_linien)
        w._objekt_umschalten_klug(w.sel_linien, "L2", "Linien", enden_)
        check("intelligente Auswahl: Klick auf L1 wählt L0..L2, L3 einzeln; Klick auf L2 wählt den Zug ab",
              set(zug_) == {"L0", "L1", "L2", "L3"} and w.sel_linien == ["L3"], str((zug_, w.sel_linien)))
        w.act_klug.setChecked(False)
        w._objekt_umschalten_klug(w.sel_linien, "L1", "Linien", enden_)
        check("Schalter aus: nur die angeklickte Linie", set(w.sel_linien) == {"L3", "L1"}, str(w.sel_linien))
        w._klick_umschalt = True
        w._objekt_umschalten_klug(w.sel_linien, "L0", "Linien", enden_)
        w._klick_umschalt = False
        check("Umschalt+Klick erzwingt die Kette (L0 mit L2 dazu)", set(w.sel_linien) == {"L3", "L1", "L0", "L2"},
              str(w.sel_linien))
        w.act_klug.setChecked(True)
        w.sel_linien = []; w.sel_staebe = []
        w._objekt_umschalten_klug(w.sel_staebe, "M0", "Stäbe", w._stabenden())
        check("Stabzug M0..M2 gewählt, hält an der Verzweigung", set(w.sel_staebe) == {"M0", "M1", "M2"},
              str(w.sel_staebe))
        check("„Intelligente Auswahl“ als Schalter in der Glasleiste mit Symbol",
              "auswahl_klug" in w.glasleiste.knoepfe
              and w.glasleiste.knoepfe["auswahl_klug"].defaultAction() is w.act_klug
              and not w.act_klug.icon().isNull() and w.act_klug.isCheckable())
        w.sel_staebe = []; w.sel_flaechen = ["F1"]; w.redraw(); app.processEvents()
        ak_ = list(w.plotter.renderer.actors)
        check("gewählte unvernetzte Fläche leuchtet als Polygon", "auswahl_flaechen" in ak_ and "auswahl" in ak_,
              str([a for a in ak_ if "auswahl" in a]))
        w.sel_flaechen = []; w.sel_staebe = ["M0"]; w.redraw(); app.processEvents()
        check("gewählter Stab leuchtet über seine Elemente", "auswahl_elemente" in list(w.plotter.renderer.actors))
        w.sel_staebe = []
        mk_ = w.flaeche_bearbeiten("F1"); app.processEvents()
        check("Doppelklick Fläche: Maske rechts (kein Dialog) mit „Randlinien anklicken“",
              isinstance(mk_, msk_.Maske) and mk_.titel == "Fläche F1" and w.maskenrand.maske is mk_
              and "Randlinien anklicken" in mk_.zusatzknoepfe, str(getattr(mk_, "titel", mk_)))
        w.activateWindow(); mk_._felder["linien"].setFocus(); app.processEvents()
        check("Klick ins Feld Randlinien: Maske erwartet Linien, das Feld ist scharf (15.09.2026)",
              mk_.objekt_modus == "linie" and "ff8800" in mk_._felder["linien"].styleSheet().lower(),
              f"{mk_.objekt_modus!r}")
        mk_._felder["kommentar"].setFocus(); app.processEvents()
        check("… ein anderes Feld beendet ihn wieder", mk_.objekt_modus == "", repr(mk_.objekt_modus))
        mk_.zusatzknoepfe["Randlinien anklicken"].click(); app.processEvents()
        check("Klickmodus: Maske erwartet Linien, die Randlinien leuchten",
              mk_.objekt_modus == "linie" and w.maskenrand.objekt_modus() == "linie"
              and set(w.sel_linien) == {"R0", "R1", "R2", "R3"}, str((mk_.objekt_modus, w.sel_linien)))
        mk_.objekt_angeklickt("linie", "R1")
        weg_ = "R1" not in w._namensliste(mk_.werte()["linien"]) and "R1" not in w.sel_linien
        w._linie_am_zeiger = lambda: "L1"
        w._maskenobjekt_klick("linie", np.zeros(3)); app.processEvents()
        check("Klick nimmt R1 heraus; Klick auf L1 bringt den Zug L0, L1, L2 in die Maske",
              weg_ and {"L0", "L1", "L2"} <= set(w._namensliste(mk_.werte()["linien"])), mk_.werte()["linien"])
        mk_.objekt_angeklickt("flaeche", "F1")
        mk_.zusatzknoepfe["Randlinien anklicken"].click(); app.processEvents()
        check("falsche Art abgewiesen, Klickmodus wieder aus", "F1" not in mk_.werte()["linien"] and mk_.objekt_modus == "")
        mk_.setzen("linien", "R0, R1, R2, R3"); mk_.setzen("vernetzen", True)
        mk_.anwenden(); app.processEvents()
        check("Übernehmen mit „gleich vernetzen“: F1 hat Elemente, keine Fehler",
              len(w.model.flaechen["F1"].elemente) > 0 and not fehler_, str(fehler_[:1]))
        w.undo(); app.processEvents()
        check("Rückgängig nimmt das Netz wieder", not w.model.flaechen["F1"].elemente)
        w.error = alt_error
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Mehrfachauswahl und intelligente Auswahl", False, str(ex)[:70])

    # ---- Masken rechts: Querschnitt, Gelenk, Berichtsbild, Kontaktbedingung; Ribbon Struktur --
    try:
        from statik3d.gui import masken as msk_
        from statik3d.model import Kontaktbedingung as Kb_, DofBehaviour as Db_
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w._bestaetigen = lambda text: True
        gruppen_ = list(dict.fromkeys(b.gruppe for b in w.ribbon.befehle if b.register == "Struktur"))
        texte_ = {(b.gruppe, b.text) for b in w.ribbon.befehle if b.register == "Struktur"}
        check("Ribbon Struktur nach Objektart: Stäbe, Flächen, Volumen, Gelenke, Eigenschaften",
              gruppen_ == ["Stäbe", "Flächen", "Volumen", "Gelenke", "Eigenschaften"]
              and {("Stäbe", "Stab"), ("Stäbe", "Stabzug"), ("Flächen", "Schale"), ("Flächen", "Fläche aus Linien"),
                   ("Volumen", "Volumen aus Flächen"), ("Gelenke", "Gelenk"), ("Gelenke", "Gelenke setzen…"),
                   ("Eigenschaften", "Querschnitte")} <= texte_, str(gruppen_))
        sec_ = list(m_.sections)[0]
        A_alt = m_.sections[sec_].A
        mk = w.querschnitt_bearbeiten(sec_)
        app.processEvents()
        check("Querschnitt: Maske rechts mit Kennwerten in cm und „Neu aus Profil“",
              isinstance(mk, msk_.Maske) and mk.titel == f"Querschnitt {sec_}"
              and abs(mk.werte()["A"] - A_alt * 1e4) < 1e-9 and "Neu aus Profil …" in mk.zusatzknoepfe
              and isinstance(w.leuchtet, list), str(mk.werte().get("A") if mk else None))
        mk.setzen("A", 123.4); mk.setzen("name", sec_ + "x")
        mk.anwenden()
        app.processEvents()
        check("Querschnitt übernommen: A in cm², umbenannt, Elemente und Tabelle nachgezogen",
              sec_ + "x" in w.model.sections and abs(w.model.sections[sec_ + "x"].A - 123.4e-4) < 1e-12
              and all(e.sec != sec_ for e in w.model.elements if e.typ == "beam") and not fehler_
              and any(str(z[0]) == sec_ + "x" for z in w.tbl_sec.modell.zeilen), str(fehler_[:1]))
        w.undo()
        app.processEvents()
        check("Querschnitt rückgängig", sec_ in w.model.sections and abs(w.model.sections[sec_].A - A_alt) < 1e-15)
        m_ = w.model
        mk = w.add_hinge()
        app.processEvents()
        check("Gelenk neu (Ribbon Struktur → Gelenk): Maske rechts mit sechs Freiheitsgraden",
              isinstance(mk, msk_.Maske) and mk.titel.startswith("Neu: Gelenk") and "typ4" in mk.werte()
              and "k4" in mk.werte() and mk.werte()["end"] == "Stabanfang")
        mk.setzen("name", "G1"); mk.setzen("end", "Stabende"); mk.setzen("typ4", "gelenkig")
        mk.setzen("typ5", "Feder"); mk.setzen("k5", 1500.0)
        mk.anwenden()
        app.processEvents()
        h_ = w.model.hinges.get("G1")
        check("Gelenk angelegt: Stabende, φy gelenkig, φz Feder 1500 kNm/rad; Baum verträgt Gelenke am Stabende",
              h_ is not None and h_.end == 1 and h_.typ[4] == "free" and h_.typ[5] == "spring"
              and abs(h_.stiffness[5] - 1.5e6) < 1e-6 and not fehler_ and "G1" in zweige(w.baum),
              str((h_, fehler_[:1])))
        m_ = w.model
        e0 = m_.members["Riegel"].elements[0]
        m_.apply_hinge(e0, "G1")
        mk = w.gelenk_bearbeiten("G1")
        app.processEvents()
        check("Gelenk bearbeiten: Maske nennt die Elemente, sie leuchten",
              mk.titel == "Gelenk G1" and f"E{e0}" in mk.werte()["elemente"] and w.leuchtet == [e0],
              str(mk.werte()["elemente"]))
        mk.setzen("typ4", "biegesteif")
        mk.anwenden()
        app.processEvents()
        check("Gelenk geändert: Element folgt (φy nicht mehr frei, Feder φz bleibt)",
              10 not in w.model.elements[e0].hinges and any(d == 11 for d, k in w.model.elements[e0].hinge_springs),
              str((w.model.elements[e0].hinges, w.model.elements[e0].hinge_springs)))
        w._baum_loeschen("gelenk", "G1")
        app.processEvents()
        check("Gelenk gelöscht: Element wieder biegesteif",
              "G1" not in w.model.hinges and not w.model.elements[e0].hinge_springs)
        m_ = w.model
        w.ansicht_in_bericht()
        app.processEvents()
        mk = w.berichtseintrag_bearbeiten("0") if m_.bericht else None
        app.processEvents()
        check("Berichtsbild: Maske rechts statt Dialog", isinstance(mk, msk_.Maske) and mk.titel == "Berichtsbild 1")
        mk.setzen("beschriftung", "Momente am Rahmen")
        mk.anwenden()
        app.processEvents()
        check("Bildunterschrift übernommen", w.model.bericht[0].beschriftung == "Momente am Rahmen")
        m_ = w.model
        m_.kontaktbedingungen["Fuge"] = Kb_("Fuge", flaechen=[1], volumen=[], ziele=1, typ="4",
                                           behaviour={0: Db_("rigid"), 2: Db_("free", failure="zug")})
        w.refresh_all()
        app.processEvents()
        w._baum_geklickt("kontaktbedingung", "Fuge")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Kontaktbedingung: Maske rechts mit Wirkung je FHG, Trennung und „Kontaktfugen ausführen“",
              mk.titel == "Kontaktbedingung Fuge" and "uz=frei (Ausfall bei Zug)" in mk.werte()["wirkung"]
              and "nicht ausgeführt" in mk.werte()["ausgefuehrt"] and "Kontaktfugen ausführen" in mk.zusatzknoepfe,
              str(mk.werte()))
        mk.setzen("beschreibung", "Lagerfuge")
        mk.anwenden()
        app.processEvents()
        check("Kontaktbedingung: Beschreibung übernommen, Warnzeichen vor dem Namen im Baum",
              w.model.kontaktbedingungen["Fuge"].beschreibung == "Lagerfuge" and not fehler_
              and any(t.startswith("⚠ Fuge") for t in zweige(w.baum)), str(fehler_[:1]))
        from tests.test_fugen import zwei_bloecke
        # ---- Kontaktmaske: zwei Koerper, Kontaktflaechen, Standardkontakte (#129) ----
        w.new_model()
        fehler_.clear()
        w.model = zwei_bloecke("eigene", 0.5, 0.15)
        w.refresh_all(); app.processEvents()
        m_ = w.model
        # --- 15.09.2026: Kontakte entstehen von selbst, wenn sich Volumen beruehren ---
        from statik3d import kontakte as kt_

        def baumfarbe_(text):
            def lauf(it):
                if it.text(0) == text:
                    return it.foreground(0).color().name()
                for i_ in range(it.childCount()):
                    r_ = lauf(it.child(i_))
                    if r_:
                        return r_
                return ""
            for i_ in range(w.baum.topLevelItemCount()):
                r_ = lauf(w.baum.topLevelItem(i_))
                if r_:
                    return r_
            return ""

        auto_ = "Oben–Unten starr"
        kb_a = m_.kontaktbedingungen.get(auto_)
        check("zwei Volumen berühren sich: „Oben–Unten starr“ entsteht von selbst (Verbund, automatisch, FugeO/FugeU)",
              kb_a is not None and kb_a.automatisch and kb_a.standard == "Verbund" and kb_a.flaechennamen == ["FugeO"]
              and kb_a.gegenflaechen == ["FugeU"] and kb_a.koerpernamen == ["Oben"] and kb_a.gegenkoerper == ["Unten"],
              str(sorted(m_.kontaktbedingungen)))
        check("… am vorhandenen Netz gleich ausgeführt: ein Kontaktpaar mit Zug und Haften",
              kb_a is not None and kb_a.ausgefuehrt and len(m_.contact_pairs) == 1
              and m_.contact_pairs[0].zug and m_.contact_pairs[0].haften, f"{len(m_.contact_pairs)} Paare")
        check("im Modellbaum steht er in der Farbe seiner Wirkung (starr = grau)",
              baumfarbe_(auto_) == kt_.WIRKUNGSFARBEN["starr"], baumfarbe_(auto_))
        check("das Protokoll nennt die Berührung", "Oben berührt Unten" in w.log.toPlainText())
        w._baum_geklickt("kontaktbedingung", auto_); app.processEvents()
        akt_b = dict(w.plotter.renderer.actors)
        # die Fugenflaechen tragen kein Schalennetz: sie leuchten als Vielecke (auswahl_flaechen)
        check("Klick auf den Kontakt: die Fuge leuchtet kräftig, die beiden Volumen blass dazu",
              ("auswahl_flaechen" in akt_b or "auswahl_elemente" in akt_b) and "auswahl_blass" in akt_b
              and abs(akt_b["auswahl_blass"].GetProperty().GetOpacity() - 0.22) < 1e-6
              and akt_b["auswahl_blass"].GetMapper().GetInput().GetNumberOfCells() > 0
              and "blass" in w.lbl_sel.text(),
              f"{sorted(a_ for a_ in akt_b if a_.startswith('auswahl'))} „{w.lbl_sel.text()}“")
        mk = w.maskenrand.maske
        mk.setzen("standard", "Reibungsfrei"); app.processEvents(); mk.anwenden(); app.processEvents()
        neu_ = "Oben–Unten nur Druck"
        check("Wirkung umgestellt: der Name folgt ihr („Oben–Unten nur Druck“), die Farbe wird rot",
              neu_ in m_.kontaktbedingungen and auto_ not in m_.kontaktbedingungen
              and m_.kontaktbedingungen[neu_].automatisch and baumfarbe_(neu_) == kt_.WIRKUNGSFARBEN["nur Druck"]
              and len(m_.contact_pairs) == 1 and not m_.contact_pairs[0].zug,
              f"{sorted(m_.kontaktbedingungen)}, {baumfarbe_(neu_)}")
        w._baum_geklickt("geokoerper_einzeln", "Oben"); app.processEvents()
        check("ein anderes Objekt im Baum: kein blasses Volumen mehr",
              "auswahl_blass" not in dict(w.plotter.renderer.actors))
        w._baum_loeschen("kontaktbedingung", neu_); app.processEvents()
        w.refresh_all(); app.processEvents()
        check("gelöscht bleibt gelöscht: der Kontakt entsteht nicht wieder (Ausnahme Oben/Unten gemerkt)",
              not m_.kontaktbedingungen and not m_.contact_pairs
              and ["Oben", "Unten"] in (getattr(m_, "kontakt_ausnahmen", None) or []),
              str((sorted(m_.kontaktbedingungen), getattr(m_, "kontakt_ausnahmen", None))))
        check("Modellbaum bietet „+ Kontaktbedingung anlegen“ an, sobald es Volumen gibt",
              "+ Kontaktbedingung anlegen" in zweige(w.baum) and "Flächenkontakte" in zweige(w.baum), str([z for z in zweige(w.baum) if "ontakt" in z]))
        w._baum_geklickt("kontaktbedingung_neu", ""); app.processEvents()
        mk = w.maskenrand.maske
        check("Neue Kontaktbedingung: Maske mit Körper A/B, Kontaktflächen, Standardkontakt, Zug, Schub x/y, Reibung, Verdrehungen, Suchradius, Spalt",
              mk is not None and mk.titel.startswith("Neu: Kontaktbedingung KB")
              and all(k in mk.werte() for k in ("standard", "koerper_a", "koerper_b", "flaechennamen", "zug", "schub_x", "schub_y", "mu", "dreh", "suchweite", "spalt"))
              and "Kontaktfugen ausführen" in mk.zusatzknoepfe, str(mk.werte() if mk else None)[:200])
        # --- 15.09.2026: „wenn neuer Kontakt angelegt wird, dann soll Volumen anklickbar
        # sein ... die Maske damit automatisch ausfüllen, Körper und Flächen";
        # „bei Klick in Feld Auswahl per Maus" ---
        from PySide6 import QtTest as _QtTk

        def rahmen_(feld):
            return "ff8800" in mk._felder[feld].styleSheet().lower()

        def scharf_():
            return [f_ for f_ in ("koerper_a", "koerper_b", "flaechennamen", "gegenflaechen") if rahmen_(f_)]

        check("neue Kontaktbedingung: das Feld Körper A ist scharf (orange), ein Klick in der Ansicht trifft Volumen",
              mk.objekt_modus == "volumen" and getattr(mk, "_klick_art", "") == "kontaktbedingung_a"
              and scharf_() == ["koerper_a"],
              f"{mk.objekt_modus!r} / {getattr(mk, '_klick_art', '')}, scharf {scharf_()}")
        alt_am_zeiger_ = w._objekt_am_zeiger
        w._objekt_am_zeiger = lambda art_: {"Volumen": "Oben", "Fläche": "MO1"}.get(art_)
        try:
            w._maskenobjekt_klick("volumen", np.zeros(3)); app.processEvents()
        finally:
            w._objekt_am_zeiger = alt_am_zeiger_
        check("Klick auf ein Volumen setzt Körper A (nicht die Fläche davor), leuchtet und geht zu Körper B",
              mk.werte()["koerper_a"] == "Oben" and getattr(mk, "_klick_art", "") == "kontaktbedingung_b"
              and scharf_() == ["koerper_b"] and w.sel_koerper == ["Oben"],
              f"A {mk.werte()['koerper_a']}, {getattr(mk, '_klick_art', '')}, scharf {scharf_()}, Auswahl {w.sel_koerper}")
        mk.objekt_angeklickt("volumen", "Unten"); app.processEvents()
        check("… Körper B gesetzt, weiter mit den Kontaktflächen",
              mk.werte()["koerper_b"] == "Unten" and getattr(mk, "_klick_art", "") == "kontaktbedingung"
              and mk.objekt_modus == "flaeche" and scharf_() == ["flaechennamen"],
              f"B {mk.werte()['koerper_b']}, {getattr(mk, '_klick_art', '')}, scharf {scharf_()}")
        mk.objekt_angeklickt("flaeche", "FugeO"); mk.objekt_angeklickt("flaeche", "FugeU"); app.processEvents()
        check("Flächenklick: die Fläche von Körper A wird Kontaktfläche, die des anderen Körpers Gegenfläche; beide leuchten",
              w._namensliste(mk.werte()["flaechennamen"]) == ["FugeO"]
              and w._namensliste(mk.werte()["gegenflaechen"]) == ["FugeU"]
              and sorted(w.sel_flaechen) == ["FugeO", "FugeU"],
              f"{mk.werte()['flaechennamen']!r} / {mk.werte()['gegenflaechen']!r}, Auswahl {w.sel_flaechen}")
        mk.setzen("koerper_a", "–"); mk.setzen("koerper_b", w.KONTAKT_ALLE)
        mk.setzen("flaechennamen", ""); mk.setzen("gegenflaechen", "")
        mk.objekt_angeklickt("flaeche", "FugeO"); mk.objekt_angeklickt("flaeche", "FugeU"); app.processEvents()
        check("… und füllt die Körper selbst: leere Maske, zwei Flächenklicks → Körper A Oben, Körper B Unten",
              mk.werte()["koerper_a"] == "Oben" and mk.werte()["koerper_b"] == "Unten"
              and w._namensliste(mk.werte()["flaechennamen"]) == ["FugeO"]
              and w._namensliste(mk.werte()["gegenflaechen"]) == ["FugeU"],
              str({k_: mk.werte()[k_] for k_ in ("koerper_a", "koerper_b", "flaechennamen", "gegenflaechen")}))
        mk.objekt_angeklickt("flaeche", "FugeU"); app.processEvents()
        check("ein zweiter Klick nimmt die Fläche wieder heraus, die Körper bleiben",
              not w._namensliste(mk.werte()["gegenflaechen"]) and mk.werte()["koerper_b"] == "Unten",
              repr(mk.werte()["gegenflaechen"]))
        w.activateWindow(); mk._felder["gegenflaechen"].setFocus(); app.processEvents()
        check("Klick ins Feld Gegenflächen: die Maus sammelt jetzt Gegenflächen, das Feld ist scharf",
              mk.objekt_modus == "flaeche" and getattr(mk, "_klick_art", "") == "kontaktbedingung_gegen"
              and scharf_() == ["gegenflaechen"],
              f"{mk.objekt_modus!r} / {getattr(mk, '_klick_art', '')}, scharf {scharf_()}")
        mk._felder["mu"].setFocus(); app.processEvents()
        check("Klick in ein Feld ohne Klickbedeutung (μ) beendet den Klickmodus, kein Feld bleibt scharf",
              not mk.objekt_modus and not scharf_(), f"{mk.objekt_modus!r}, scharf {scharf_()}")
        mk._felder["flaechennamen"].setFocus(); app.processEvents()
        _QtTk.QTest.keyClick(mk._felder["flaechennamen"], QtCore.Qt.Key_Escape); app.processEvents()
        check("Esc im scharfen Feld beendet nur den Klickmodus - die Maske bleibt offen",
              not mk.objekt_modus and not scharf_() and w.maskenrand.maske is mk and mk.isVisible(),
              f"{mk.objekt_modus!r}, Maske {w.maskenrand.maske is mk}")
        mk.setzen("koerper_a", "–"); mk.setzen("koerper_b", w.KONTAKT_ALLE)
        mk.setzen("flaechennamen", ""); mk.setzen("gegenflaechen", "")
        check("Vorgabe: reibungsbehaftet, μ = 0,2, abheben möglich",
              mk.werte()["standard"] == "Reibungsbehaftet" and abs(float(mk.werte()["mu"]) - 0.2) < 1e-9 and mk.werte()["zug"].startswith("abheben"), str(mk.werte()["standard"]))
        mk.setzen("standard", "Verbund"); app.processEvents()
        check("Standardkontakt „Verbund“ setzt Zug übertragen, Schub starr, Verdrehungen starr, μ = 0",
              mk.werte()["zug"].startswith("wird übertragen") and mk.werte()["schub_x"].startswith("starr") and mk.werte()["schub_y"].startswith("starr")
              and mk.werte()["dreh"] == "starr" and float(mk.werte()["mu"]) == 0, str(mk.werte())[:200])
        mk.setzen("schub_x", w.KONTAKT_SCHUB["frei"]); app.processEvents()
        check("Handänderung einer Richtung macht daraus „Benutzerdefiniert“", mk.werte()["standard"] == "Benutzerdefiniert", mk.werte()["standard"])
        mk.setzen("standard", "Reibungsbehaftet"); app.processEvents()
        mk.setzen("mu", 0.3)
        mk.setzen("koerper_a", "Oben"); mk.setzen("koerper_b", "Unten"); mk.setzen("flaechennamen", "")
        mk.anwenden(); app.processEvents()
        check("ohne Kontaktfläche: Hinweis statt Anlage", bool(fehler_) and "Kontaktfläche" in fehler_[-1] and not m_.kontaktbedingungen, str(fehler_[-1:]))
        mk = w.maskenrand.maske
        mk.setzen("flaechennamen", "FugeU"); mk.anwenden(); app.processEvents()
        check("Fläche eines anderen Körpers: Hinweis", "gehören nicht zu Körper A" in fehler_[-1], str(fehler_[-1:]))
        mk = w.maskenrand.maske
        mk.setzen("flaechennamen", "FugeO")
        n_f = len(fehler_)
        mk.anwenden(); app.processEvents()
        kb = m_.kontaktbedingungen.get("KB1")
        check("OK legt die Kontaktbedingung an: Körper A Oben, B Unten, Fläche FugeO, reibungsbehaftet μ = 0,3",
              kb is not None and kb.koerpernamen == ["Oben"] and kb.gegenkoerper == ["Unten"] and kb.flaechennamen == ["FugeO"]
              and kb.standard == "Reibungsbehaftet" and abs(kb.reibbeiwert() - 0.3) < 1e-9 and kb.dof_behaviour(2).failure == "zug" and len(fehler_) == n_f,
              str((fehler_[n_f:], kb.describe() if kb else None)))
        check("… und führt sie am vorhandenen Netz gleich aus: ein Kontaktpaar mit Reibung",
              kb is not None and kb.ausgefuehrt and len(m_.contact_pairs) == 1 and abs(m_.contact_pairs[0].mu - 0.3) < 1e-9 and not m_.contact_pairs[0].zug,
              f"{len(m_.contact_pairs)} Paare")
        mk = w.maskenrand.maske
        check("Rechts steht danach die Maske der neuen Kontaktbedingung mit „getrennt“",
              mk is not None and mk.titel == "Kontaktbedingung KB1" and "getrennt" in mk.werte()["ausgefuehrt"] and w.rechts_zeigt() == "maske",
              str(mk.werte()["ausgefuehrt"] if mk else None))
        # --- Nur die Fuge leuchtet; Gegenflaechen per Maus; Kontakte farbig zeigen ---
        w._baum_geklickt("kontaktbedingung", "KB1"); app.processEvents()
        check("Kontakt im Modellbaum: nur die Fuge leuchtet, nicht der ganze Körper",
              w.sel_flaechen == ["FugeO"] and not w.sel_koerper
              and "1 Kontaktflächen" in w.lbl_sel.text(),
              f"{w.sel_flaechen}, Volumen {w.sel_koerper}, „{w.lbl_sel.text()}“")
        mk = w.maskenrand.maske
        check("Kontaktmaske: Gegenflächen sind ein Listenfeld, das per Klick ins Feld die Maus sammeln lässt",
              "gegenflaechen" in mk.werte() and w.FELDKLICK["kontaktbedingung"]["gegenflaechen"] == "kontaktbedingung_gegen"
              and "Gegenflächen anklicken" not in mk.zusatzknoepfe, str(sorted(mk.zusatzknoepfe)))
        w.activateWindow(); mk._felder["gegenflaechen"].setFocus(); app.processEvents()
        check("Klickmodus Gegenflächen an", mk.objekt_modus == "flaeche" and mk._klick_art == "kontaktbedingung_gegen",
              f"{mk.objekt_modus} / {getattr(mk, '_klick_art', '')}")
        mk.objekt_angeklickt("flaeche", "FugeU"); app.processEvents()
        # seit 15.09.2026 leuchten beide Seiten der Fuge, nicht nur die angeklickte Liste
        check("angeklickte Fläche steht als Gegenfläche in der Maske und leuchtet mit der Kontaktfläche",
              w._namensliste(mk.werte()["gegenflaechen"]) == ["FugeU"] and sorted(w.sel_flaechen) == ["FugeO", "FugeU"],
              f"{mk.werte()['gegenflaechen']!r}, Auswahl {w.sel_flaechen}")
        mk._felder["flaechennamen"].setFocus(); app.processEvents()
        check("Klick ins Feld Kontaktflächen schaltet auf die andere Liste um, statt den Modus zu beenden",
              mk.objekt_modus == "flaeche" and mk._klick_art == "kontaktbedingung",
              f"{mk.objekt_modus} / {getattr(mk, '_klick_art', '')}")
        mk._felder["beschreibung"].setFocus(); app.processEvents()
        check("und ein Feld ohne Klickbedeutung beendet ihn", not mk.objekt_modus, str(mk.objekt_modus))
        n_f = len(fehler_)
        mk.anwenden(); app.processEvents()
        kb = m_.kontaktbedingungen.get("KB1")
        check("Übernehmen schreibt die angeklickte Gegenfläche in die Bedingung",
              kb is not None and kb.gegenflaechen == ["FugeU"] and len(fehler_) == n_f,
              f"{kb.gegenflaechen if kb else None}, {fehler_[n_f:]}")
        w._baum_geklickt("kontaktbedingung", "KB1"); app.processEvents()
        check("jetzt leuchten beide Seiten der Fuge - Kontaktfläche und Gegenfläche",
              w.sel_flaechen == ["FugeO", "FugeU"] and "1 Gegenflächen" in w.lbl_sel.text(),
              f"{w.sel_flaechen}, „{w.lbl_sel.text()}“")
        w.act_kontakte.setChecked(True); w.redraw(); app.processEvents()
        akt_ = [a for a in w.plotter.renderer.actors if a.startswith("kontakt")]
        check("„Kontakte zeigen“: die Fuge farbig im Bild, mit Schild aus Name und Wirkung",
              any(a.startswith("kontaktflaeche") for a in akt_) and any(a.startswith("kontakttext") for a in akt_)
              and "Kontakte: 1 Bedingungen" in w._sicht_text(), str(akt_))
        from PySide6 import QtGui as _QtGk
        soll_ = _QtGk.QColor(kt_.wirkungsfarbe(kb)).getRgbF()[:3]
        ist_ = dict(w.plotter.renderer.actors)["kontaktflaeche0"].GetProperty().GetColor()
        check("… in der Farbe ihrer Wirkung (Druck mit Reibung = orange), seit 15.09.2026",
              kt_.wirkungstext(kb) == "Druck, Reibung" and max(abs(a_ - b_) for a_, b_ in zip(ist_, soll_)) < 0.02,
              f"{kt_.wirkungstext(kb)} {ist_} / {soll_}")
        check("das Schild sagt, wie der Kontakt wirkt (Druck, abheben, gleiten, μ)",
              w.kontakt_kurztext(kb) == "Druck, abheben, gleiten, μ = 0.3", w.kontakt_kurztext(kb))
        w.act_kontakte.setChecked(False); w.redraw(); app.processEvents()
        check("aus: keine Kontaktfarben mehr im Bild",
              not any(a.startswith("kontaktflaeche") or a.startswith("kontakttext")
                      for a in w.plotter.renderer.actors))
        z = w.tbl_freigabe.modell.zeilen
        check("Tabelle nennt Standard, Körper A und B", len(z) == 1 and z[0][8] == "Reibungsbehaftet" and z[0][9] == "Oben" and z[0][10] == "Unten", str(z[0] if z else z))
        # --- Kontaktmaske: Typ/Ort nicht mehr rechts, Hinweise sagen, was gilt (15.09.2026) ---
        kb.typ, kb.ort = "3", "Anfang"
        w._baum_geklickt("kontaktbedingung", "KB1"); app.processEvents()
        mk = w.maskenrand.maske
        beschr_ = {lb.text(): lb.toolTip() for lb in mk.findChildren(QtWidgets.QLabel)}
        check("eine eingelesene Bedingung (Typ 3 / Anfang) zeigt rechts kein Feld „Typ / Ort“ mehr",
              "typ" not in mk.werte() and not any("Typ / Ort" in x for x in beschr_),
              str(sorted(mk.werte()))[:160])
        h_kf = mk._listen["flaechennamen"][2]
        h_gf = mk._listen["gegenflaechen"][2]
        h_sr = next((tip for txt, tip in beschr_.items() if txt.startswith("Suchradius")), "")
        check("Hinweis Kontaktflächen: leer nur mit Gegenflächen - nicht mehr „mindestens eine Fläche“",
              "Leer nur mit Gegenflächen" in h_kf and "mindestens eine" not in h_kf, h_kf)
        check("Hinweis Gegenflächen: genannt wirkt der Kontakt nur auf ihnen, leer wird gesucht",
              "nur auf ihnen" in h_gf and "Leer: die Gegenseite wird im Suchradius gesucht" in h_gf, h_gf)
        check("Hinweis Suchradius: was er begrenzt, Berührungsband, automatischer Wert steht im Protokoll",
              "noch zur Fuge" in h_sr and "Tausendstel" in h_sr and "Protokoll" in h_sr, h_sr)
        check("Maskentext beschreibt beide Wege der Kontaktseite und dass Kontakt nur gegenüber wirkt",
              "wenn leer" in mk.lbl_hinweis.text() and "nur, wo sich beide" in mk.lbl_hinweis.text(),
              mk.lbl_hinweis.text()[:160])
        w.refresh_all(); app.processEvents()
        z = w.tbl_freigabe.modell.zeilen
        check("… Typ und Ort stehen weiter in der Tabelle der Kontaktbedingungen",
              len(z) == 1 and z[0][1] == "3" and z[0][2] == "Anfang", str(z[0][:3] if z else z))
        kb.typ, kb.ort = "", "Anfang"
        w._baum_geklickt("kontaktbedingung", "KB1"); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("standard", "Verbund"); app.processEvents(); mk.anwenden(); app.processEvents()
        kb = m_.kontaktbedingungen.get("KB1")
        check("Übernehmen mit „Verbund“ ersetzt das Kontaktpaar: Zug und Haften",
              kb is not None and kb.standard == "Verbund" and len(m_.contact_pairs) == 1 and m_.contact_pairs[0].zug and m_.contact_pairs[0].haften, str(fehler_[n_f:]))
        fr = Model.from_dict(m_.to_dict()).kontaktbedingungen["KB1"]
        check("Standard, Gegenkörper, Suchradius und Spalt überleben Speichern und Laden",
              fr.standard == "Verbund" and fr.gegenkoerper == ["Unten"] and fr.suchweite == 0.0 and fr.spalt_schliessen is False, fr.describe())
        w._baum_loeschen("kontaktbedingung", "KB1"); app.processEvents()
        check("Löschen im Modellbaum nimmt Bedingung und Kontaktpaar", "KB1" not in m_.kontaktbedingungen and not m_.contact_pairs, str(fehler_[n_f:]))
        w.error = alt_error
        del w._bestaetigen
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Masken rechts (Querschnitt, Gelenk, Bericht, Kontakt)", False, str(ex)[:70])

    # ---- Lager: Auswahlart, Symbole, Lagerdichte, Maske mit Bettung ----------
    try:
        from statik3d.gui import masken as msk_, viewport as vp_
        w.new_model()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w._bestaetigen = lambda text: True
        mat_, t_ = list(m_.materials)[0], list(m_.shells)[0]
        m_.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [4, 0, 0], [6, 0, 0], [0, 2, 0], [2, 2, 0], [4, 2, 0], [6, 2, 0]], float))
        m_.support(0, [0, 1, 2, 3, 4, 5], name="Einspannung")
        m_.support(1, [0, 1, 2], name="Gelenk")
        m_.support(2, [1, 2], name="Rolle")
        m_.support(3, [0, 1, 2, 3, 5], name="Scharnier")
        e1_ = m_.add_element("shell4", [0, 1, 5, 4], mat_, t_)
        e2_ = m_.add_element("shell4", [1, 2, 6, 5], mat_, t_)
        m_.add_line_support([0, 1, 2, 3], uz=dict(typ="rigid"))
        m_.add_surface_support([e1_, e2_], uz=dict(typ="spring", stiffness=5e7, failure="zug"))
        w.refresh_all(); app.processEvents()
        check("Auswahlart „Lager“ in der Glasleiste mit Symbol",
              "Lager" in w.AUSWAHLARTEN and "auswahl_Lager" in w.glasleiste.knoepfe
              and not w.act_auswahlart["Lager"].icon().isNull())
        sym_ = [vp_.lager_symbol(s) for s in m_.supports]
        check("Lagersymbole: Einspannung Würfel, Gelenk Pyramide mit Kugel, Rolle mit Gleitebene in x, "
              "Scharnier Zylinder um y",
              sym_[0][1] == "einspannung" and sym_[1][1:3] == ("pyramide", "kugel")
              and sym_[2][3] == (0,) and sym_[3][2] == "zyl1", str(sym_))
        check("jedes Symbol ist ein gültiges Netz",
              all(vp_.lagerglyph(k, 0.1).n_cells > 0 for k in sym_))
        ak_ = list(w.plotter.renderer.actors)
        check("Linienlager entlang der ganzen Linie, Flächenlager im Raster über die Fläche",
              any(a.startswith("lsupports") for a in ak_) and any(a.startswith("lsupports_linie") for a in ak_)
              and any(a.startswith("fsupports") for a in ak_), str([a for a in ak_ if "support" in a]))
        n1_ = len(vp_.lager_punkte(m_, m_.surface_supports[0], m_.characteristic_size(), 1.0)[0])
        w._lagerdichte_geschoben(20); app.processEvents()
        n2_ = len(vp_.lager_punkte(m_, m_.surface_supports[0], m_.characteristic_size(), w.lagerdichte)[0])
        w.lagerdichte_zuruecksetzen()
        check("Lagerdichte 2,0 verdichtet die Symbole (Schieber im Register Ansicht)",
              n2_ > 2 * n1_ and w.lagerdichte == 1.0 and w.sl_lagerdichte.value() == 10, str((n1_, n2_)))
        w.auswahlart_setzen("Lager")
        w._picked([0.0, 0.0, 0.0]); app.processEvents()
        check("Klick auf ein Knotenlager wählt es, es leuchtet",
              w.sel_lager == [("lager", 0)] and "auswahl_lager" in list(w.plotter.renderer.actors), str(w.sel_lager))
        w._picked([5.0, 0.0, 0.0]); w._picked([3.0, 1.0, 0.0]); app.processEvents()
        check("Klick auf Linie und Fläche wählt Linien- und Flächenlager",
              ("linienlager", 0) in w.sel_lager and ("flaechenlager", 0) in w.sel_lager, str(w.sel_lager))
        gr_ = dict(w._auswahlgruppen())
        check("Auswahlgruppen (Rechtsklick) kennen die Lagerarten",
              gr_.get("lager") == [0] and gr_.get("linienlager") == [0] and gr_.get("flaechenlager") == [0], str(gr_))
        w.clear_selection(); app.processEvents()
        check("Alles deselektieren leert auch die Lager", not w.sel_lager)
        w._baum_geklickt("lager_einzeln", "1"); app.processEvents()
        mk = w.maskenrand.maske
        check("Knotenlager im Baum: Maske rechts (Wirkung, Feder, Ausfall je FHG, Bettung), Lager gewählt",
              isinstance(mk, msk_.Maske) and mk.titel == "Knotenlager Gelenk"
              and {"typ0", "k0", "aus0", "typ5", "beton", "E_cm", "d_bett", "A_bett", "groesse"} <= set(mk.werte())
              and mk.werte()["typ2"] == "starr" and mk.werte()["typ4"] == "frei"
              and w.sel_lager == [("lager", 1)] and w.auswahlart == "Lager"
              and set(mk.zusatzknoepfe) == {"Bettung übernehmen", "Schlupf, Reibung, Grenzkraft …", "Lager löschen"},
              str(getattr(mk, "titel", mk)))
        mk.setzen("typ2", "Feder"); mk.setzen("k2", 1000.0); mk.setzen("typ4", "starr"); mk.setzen("name", "Gelenk B")
        mk.anwenden(); app.processEvents()
        s1_ = w.model.supports[1]
        check("Übernehmen: uz Feder 1000 kN/m, φy starr, Name; Symbol zeigt die Feder",
              s1_.dof_behaviour(2).typ == "spring" and abs(s1_.dof_behaviour(2).stiffness - 1e6) < 1e-6
              and 4 in s1_.dofs and s1_.name == "Gelenk B" and vp_.lager_symbol(s1_)[4] == (2,) and not fehler_,
              str((s1_.dofs, fehler_[:1])))
        mk = w.maskenrand.maske
        mk.setzen("beton", "auf Beton (Druckkontakt)"); mk.setzen("E_cm", 33000.0)
        mk.setzen("d_bett", 100.0); mk.setzen("A_bett", 0.02)
        mk.zusatzknoepfe["Bettung übernehmen"].click(); app.processEvents()
        mk.anwenden(); app.processEvents()
        b2_ = w.model.supports[1].dof_behaviour(2)
        check("Bettung auf Beton: k = E_cm/d · A = 6,6e9 N/m in uz mit Ausfall bei Zug",
              b2_.typ == "spring" and abs(b2_.stiffness - 6.6e9) < 1e3 and b2_.failure == "zug", str(b2_))
        w._baum_geklickt("linienlager_einzeln", "0"); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("beton", "an Beton (Schubverbund)"); mk.setzen("b_bett", 0.5)
        mk.zusatzknoepfe["Bettung übernehmen"].click(); app.processEvents()
        mk.anwenden(); app.processEvents()
        ls_ = w.model.line_supports[0]
        kt_ = 33000e6 / (2 * 1.2) / 0.1 * 0.5
        check("Linienlager: Bettung an Beton k_t = G/d · b in ux und uy, uz bleibt starr",
              ls_.dof_behaviour(0).typ == "spring" and abs(ls_.dof_behaviour(0).stiffness - kt_) < 1.0
              and ls_.dof_behaviour(1).typ == "spring" and ls_.dof_behaviour(2).typ == "rigid" and not fehler_,
              str((ls_.dof_behaviour(0).stiffness, fehler_[:1])))
        w._tabelle_lager("1"); app.processEvents()
        check("Klick in der Lagertabelle wählt das Lager auch als Lager", w.sel_lager == [("lager", 1)], str(w.sel_lager))
        w._baum_geklickt("lager", "Knotenlager"); app.processEvents()
        check("Zweig Knotenlager: Übersichtsmaske, alle Knotenlager gewählt",
              w.maskenrand.maske.titel == "Knotenlager" and len(w.sel_lager) == 4)
        w._baum_loeschen("linienlager_einzeln", "0"); app.processEvents()
        check("Linienlager über den Baum gelöscht, Rückgängig holt es zurück",
              not w.model.line_supports and (w.undo() or True) and len(w.model.line_supports) == 1)
        w.error = alt_error
        del w._bestaetigen
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Lager: Auswahl, Symbole, Maske", False, str(ex)[:70])

    # ---- Lastfälle nach DIN 19704 und Lastenheft ----------------------------
    try:
        from statik3d.gui import masken as msk_
        w.load_example("gate")
        app.processEvents()
        m_ = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        n_alt = len(m_.load_cases)
        mk = w.maske_din19704_lastfaelle()
        app.processEvents()
        check("Lasten → „Lastfälle nach DIN 19704…“: Maske mit Haken je Einwirkung, Standard vorgehakt",
              isinstance(mk, msk_.Maske) and mk.werte().get("e_G") is True and mk.werte().get("e_EIS") is True
              and mk.werte().get("e_KLEMM") is False and "start" in mk.werte(),
              str([k for k, v in mk.werte().items() if k.startswith("e_") and v]))
        mk.setzen("e_ANPRALL", True)
        mk.anwenden()
        app.processEvents()
        m_ = w.model
        check("Lastfälle angelegt: Name = Kürzel, Art, Nummer fortlaufend, Eigengewicht mit g, Anprall dazu",
              len(m_.load_cases) == n_alt + 10 and "G" in m_.load_cases and m_.load_cases["G"].category == "G"
              and m_.load_cases["G"].gravity[2] < 0 and "ANPRALL" in m_.load_cases
              and m_.load_cases["EIS"].nummer > 0 and not fehler_, str((len(m_.load_cases), fehler_[:1])))
        check("Lastfalltabelle nennt sie", any(str(z[0]) == "EIS" for z in w.tbl_lastfall.modell.zeilen))
        w.undo()
        app.processEvents()
        check("Rückgängig nimmt die Lastfälle wieder", len(w.model.load_cases) == n_alt)
        pfad_ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lastenheft_smoke.html")
        geoeffnet_ = []
        alt_open_ = QtGui.QDesktopServices.openUrl
        QtGui.QDesktopServices.openUrl = staticmethod(lambda u: geoeffnet_.append(u.toString()) or True)
        try:
            out_ = w.make_lastenheft(pfad_)
            app.processEvents()
            html_ = open(pfad_, encoding="utf-8").read() if os.path.exists(pfad_) else ""
            check("Bericht → Lastenheft schreibt das Heft mit Einwirkungen und Skizzen",
                  out_ == pfad_ and "Lastenheft" in html_ and "W_S - Wasserdruck" in html_
                  and html_.count("<svg") >= 15 and not fehler_, str((len(html_), fehler_[:1])))
            check("und öffnet in der Prüfung keinen Browser (die Datei wird gleich gelöscht)",
                  not geoeffnet_ and "Browser nicht geöffnet" in w.log.toPlainText(), str(geoeffnet_))
        finally:
            QtGui.QDesktopServices.openUrl = alt_open_
            if os.path.exists(pfad_):
                os.remove(pfad_)
        check("Ribbon Bericht hat den Befehl „Lastenheft“",
              any(b.register == "Bericht" and b.text == "Lastenheft" for b in w.ribbon.befehle))
        w.error = alt_error
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Lastfälle nach DIN 19704 und Lastenheft", False, str(ex)[:70])

    # ---- Befunde des Menütests (#120): Löschen, Zuweisen, Stabmaske, Undo, Tabellen --
    try:
        from statik3d.gui import masken as msk_
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        # A1: Elemente und Knoten löschen bei Stäben mit Nachweis - ohne IndexError, rücknehmbar
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        n_el, n_kn, n_mem = len(m_.elements), m_.nn, len(m_.members)
        w._set_selection([0, 1])
        w.delete_elements()
        app.processEvents()
        ok_ = all(0 <= e < len(w.model.elements)
                  for mem in w.model.members.values() for e in mem.elements)
        check("Elemente löschen bei Stäben mit Nachweis: Verweise nachgezogen, kein Fehler",
              len(w.model.elements) < n_el and ok_ and not fehler_,
              str((len(w.model.elements), n_el, fehler_[:1])))
        w.undo(); app.processEvents()
        check("Elemente löschen ist rücknehmbar",
              len(w.model.elements) == n_el and len(w.model.members) == n_mem)
        w._set_selection([0])
        w.delete_nodes(); app.processEvents()
        check("Knoten löschen nimmt den Knoten und seine Elemente, die Nummern rücken auf",
              w.model.nn == n_kn - 1 and len(w.model.elements) < n_el and not fehler_
              and all(int(n) < w.model.nn for e in w.model.elements for n in e.nodes),
              str((w.model.nn, n_kn, fehler_[:1])))
        w.undo(); app.processEvents()
        check("Knoten löschen ist rücknehmbar", w.model.nn == n_kn and len(w.model.elements) == n_el)
        # B3: Doppelklick auf einen Stab mit Nachweis → Stabmaske mit β
        stab_ = next(iter(w.model.members))
        w._baum_bearbeiten("stab", stab_)
        app.processEvents()
        mk = w.maskenrand.maske
        check("Doppelklick auf einen Stab mit Nachweis öffnet rechts die Stabmaske mit β_y, β_z",
              isinstance(mk, msk_.Maske) and mk.titel == f"Stab {stab_}" and "beta_y" in mk.werte()
              and "Nachweisparameter …" in getattr(mk, "zusatzknoepfe", {}),
              str(getattr(mk, "titel", None)))
        mk.setzen("beta_y", 2.5); mk.anwenden(); app.processEvents()
        check("β_y aus der Stabmaske steht im Stab", abs(w.model.members[stab_].beta_y - 2.5) < 1e-9,
              str(w.model.members[stab_].beta_y))
        # B4: Dezimalkomma in den Kombinationsfaktoren
        lf_ = list(w.model.load_cases)[:2]
        k_ = next(iter(w.model.combinations))
        w._objektmaske("kombination", k_); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("faktoren", f"{lf_[0]}: 1,35, {lf_[1]}: 1,5")
        mk.anwenden(); app.processEvents()
        f_ = w.model.combinations[k_].factors
        check("Kombinationsfaktoren mit Dezimalkomma („LF1: 1,35, LF2: 1,5“)",
              abs(f_.get(lf_[0], 0) - 1.35) < 1e-9 and abs(f_.get(lf_[1], 0) - 1.5) < 1e-9 and not fehler_,
              str((f_, fehler_[:1])))
        # B1: Projektangaben, Zuweisen und Gelenke setzen tun etwas
        w.ribbon.finden("Projektangaben…")[0].aktion.trigger(); app.processEvents()
        check("Datei → Projektangaben… zeigt rechts die Maske „Modell“",
              w.eingaben_dock.windowTitle() == "Modell", w.eingaben_dock.windowTitle())
        w._set_selection([]); app.processEvents()
        n_f = len(fehler_)
        w.zuweisen_zeigen("querschnitt"); app.processEvents()
        check("„Querschnitt zuweisen…“ ohne Auswahl: Hinweis statt stummem Befehl",
              len(fehler_) == n_f + 1 and "wählen" in fehler_[-1], str(fehler_[-1:]))
        w._set_selection([0, 1]); app.processEvents()
        w.zuweisen_zeigen("dicke"); app.processEvents()
        check("„Dicke zuweisen…“ mit Auswahl: Kontextregister „Auswahl“ vorn, Aufklappliste Dicke da",
              w.ribbon._kontext is not None and w.ribbon.tabs.currentWidget() is w.ribbon._kontext
              and getattr(w, "cb_assign_shell", None) is not None)
        w.zuweisen_zeigen("gelenke"); app.processEvents()
        check("„Gelenke setzen…“ mit Auswahl zeigt die Maske Lager/Lasten",
              w.eingaben_dock.windowTitle() == "Lager/Lasten", w.eingaben_dock.windowTitle())
        # B8: Auswahl in der Ansicht markiert die Modelltabellen
        check("Auswahl in der Ansicht markiert die Zeilen der Knotentabelle",
              sorted(int(x) for x in w.tbl_knoten.gewaehlte_schluessel()) == [0, 1],
              str(w.tbl_knoten.gewaehlte_schluessel()))
        el_ = [i for i, e in enumerate(w.model.elements) if {int(n) for n in e.nodes} <= {0, 1}]
        check("… und der Stabtabelle",
              sorted(int(x) for x in w.tbl_elem.gewaehlte_schluessel()) == sorted(el_),
              str((w.tbl_elem.gewaehlte_schluessel(), el_)))
        # B9: nach dem Rechnen Statuszeile und Docktitel
        an = solver.solve_all(w.model)
        w._solve_done("all", an); app.processEvents()
        check("Nach dem Rechnen: Statuszeile nennt die Ergebnisse, rechts die Maske „Ergebnisse“",
              "Ergebnis" in w.lbl_solver.text() and w.eingaben_dock.windowTitle() == "Ergebnisse",
              str((w.lbl_solver.text(), w.eingaben_dock.windowTitle())))
        # C12: Rückgängig-Stapel beim Modellwechsel leer
        w.merken("Test")
        w.load_example("frame"); app.processEvents()
        check("Beispiel laden leert den Rückgängig-Stapel", not w._undo and not w.act_undo.isEnabled())
        # B5/C8: Rückgängig für die Erzeuge-Masken, „Neu: Knoten“ ein Schritt
        n_u = len(w._undo)
        w._maske_knoten_anlegen({"x": 1.0, "y": 2.0, "z": 0.0}); app.processEvents()
        check("Knotenmaske „Anlegen“ ist rücknehmbar", len(w._undo) == n_u + 1)
        n_u = len(w._undo)
        w._baum_neu("knoten"); app.processEvents()
        w.maskenrand.maske.anwenden(); app.processEvents()
        check("„Neu: Knoten“ braucht nur einen Rückgängig-Schritt", len(w._undo) == n_u + 1,
              str((len(w._undo), n_u)))
        # B2: Neu-Zweige Schweißnähte und Bemaßungen
        w.new_model(); app.processEvents()
        w._baum_neu("schweissnaehte"); app.processEvents()
        t_ = str(getattr(w.maskenrand.maske, "titel", ""))
        check("Modellbaum „Schweißnähte → Neu“ öffnet die Nahtmaske", "naht" in t_.lower(), t_)
        w._baum_neu("bemassungen"); app.processEvents()
        t_ = str(getattr(w.maskenrand.maske, "titel", ""))
        check("Modellbaum „Bemaßungen → Neu“ öffnet die Maßmaske", t_.startswith("Neu: Linearmaß"), t_)
        w.maskenrand.schliessen(); app.processEvents()
        # A2 + B6: Element einer vernetzten Fläche löschen; die eigene Teilung bleibt
        w.new_model(); app.processEvents()
        from statik3d.model import ShellProp as _SP
        mg = w.model
        mg.add_shell_prop(_SP("t12", 0.012))
        mg.add_nodes(np.array([[0, 0, 0], [3, 0, 0], [3, 2, 0], [0, 2, 0.]]))
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            mg.add_line(f"L{i + 1}", [a, b])
        mg.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke="t12",
                       material=next(iter(mg.materials)), teilung=[3, 2])
        mg.netz.teilung_uebersteuern = True
        mg.netz.dichte = "fein"
        w.refresh_all(); app.processEvents()
        w.sel_flaechen = ["F1"]
        w.geometrie_vernetzen(); app.processEvents()
        f1 = w.model.flaechen["F1"]
        check("Vernetzen nach Netzdichte lässt die eigene Teilung der Fläche stehen",
              list(f1.teilung) == [3, 2] and len(f1.elemente) > 6, str((f1.teilung, len(f1.elemente))))
        n_el = len(w.model.elements)
        w.tbl_elem.view.selectRow(0)
        w.element_loeschen(); app.processEvents()
        f1 = w.model.flaechen["F1"]
        check("Tabelle Stäbe → Element löschen zieht die Elementverweise der Fläche nach",
              len(w.model.elements) == n_el - 1 and len(f1.elemente) == n_el - 1
              and all(0 <= e < n_el - 1 for e in f1.elemente), str((len(f1.elemente), n_el)))
        # C10: Werkstoff mit vorhandenem Namen
        _gm = sys.modules["statik3d.gui.main"]      # gui.main() verdeckt das Modul

        class _FakeMat:
            def __init__(self, parent=None):
                pass

            def exec(self):
                return True

            def result_material(self):
                from statik3d.model import Material
                return Material.steel(next(iter(w.model.materials)))
        alt_md = _gm.MaterialDialog
        _gm.MaterialDialog = _FakeMat
        try:
            n_f = len(fehler_)
            w.add_material(); app.processEvents()
        finally:
            _gm.MaterialDialog = alt_md
        check("Werkstoff mit vorhandenem Namen: klare Meldung statt nacktem KeyError",
              len(fehler_) == n_f + 1 and "gibt es schon" in fehler_[-1], str(fehler_[-1:]))
        # C5/C6: jeder Befehl einmal, jeder mit Hinweis
        w._set_selection([]); app.processEvents()
        texte = [b.text for b in w.ribbon.befehle]
        doppelt = sorted({t for t in texte if texte.count(t) > 1})
        check("Ribbon: jeder Befehl steht genau einmal (Schalter „Knoten“ der Ansicht ausgenommen)",
              set(doppelt) <= {"Knoten"}, str(doppelt))
        ohne = [f"{b.register}/{b.text}" for b in w.ribbon.befehle if not b.hinweis]
        check("Ribbon: jeder Befehl hat einen Hinweistext", not ohne, str(ohne[:6]))
        check("Register Ergebnisse: die Tabellenbefehle heißen „Tabelle …“",
              bool(w.ribbon.finden("Tabelle Nachweise EC3")))
        check("Nachweise: Befehl „Volumenbereich“, Beispiel „Abhebendes Lager“",
              bool(w.ribbon.finden("Volumenbereich")) and bool(w.ribbon.finden("Abhebendes Lager")))
        w.error = alt_error
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Befunde des Menütests (#120)", False, str(ex)[:70])

    # ---- Volumen parallel vernetzen, Balken nach Aufwand, Abbrechen mittendrin (#122/#123) --
    try:
        w.new_model()
        app.processEvents()
        mg = w.model
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        n6 = 6
        wk_ = np.arange(n6) * 2 * np.pi / n6
        ring_ = np.column_stack([np.cos(wk_), np.sin(wk_)])
        mg.add_nodes(np.vstack([np.column_stack([ring_, np.full(n6, z)]) for z in (0.0, 1.0, 2.0)]))
        zaehl_ = [0]

        def linie_(a, b):
            zaehl_[0] += 1
            mg.add_line(f"L{zaehl_[0]}", [a, b])
            return f"L{zaehl_[0]}"
        E_ = [[linie_(o + i, o + (i + 1) % n6) for i in range(n6)] for o in (0, n6, 2 * n6)]
        V01_ = [linie_(i, i + n6) for i in range(n6)]
        V12_ = [linie_(i + n6, i + 2 * n6) for i in range(n6)]
        mat_ = next(iter(mg.materials))
        for j, nm in enumerate(("F0", "Fm", "F2")):
            mg.add_flaeche(nm, E_[j], material=mat_)
        unten_, oben_ = [], []
        for i in range(n6):
            mg.add_flaeche(f"A{i}", [E_[0][i], V01_[(i + 1) % n6], E_[1][i], V01_[i]], material=mat_)
            mg.add_flaeche(f"B{i}", [E_[1][i], V12_[(i + 1) % n6], E_[2][i], V12_[i]], material=mat_)
            unten_.append(f"A{i}")
            oben_.append(f"B{i}")
        mg.add_koerper("V1", ["F0", "Fm"] + unten_, material=mat_)
        mg.add_koerper("V2", ["Fm", "F2"] + oben_, material=mat_)
        mg.netz.dichte = "eigene"
        mg.netz.ziellaenge = 0.3
        w.refresh_all()
        app.processEvents()
        werte_ = []
        alt_setvalue = w.progress_bar.setValue
        w.progress_bar.setValue = lambda v: (werte_.append(int(v)), alt_setvalue(v))
        w.sel_koerper = []
        w.sel_flaechen = []
        w.geometrie_vernetzen()
        app.processEvents()
        w.progress_bar.setValue = alt_setvalue
        k1_, k2_ = mg.koerper["V1"], mg.koerper["V2"]
        check("Zwei freie Volumen vernetzt (parallel, wenn Kerne da sind) - ohne Fehler",
              len(k1_.elemente) > 100 and len(k2_.elemente) > 100 and not fehler_,
              str((len(k1_.elemente), len(k2_.elemente), fehler_[:1])))
        check("Der Balken ist nach Aufwand gewichtet: Promille, steigend bis 1000",
              werte_ and werte_[0] == 0 and werte_[-1] == 1000 and werte_ == sorted(werte_),
              str(werte_[:6]))
        meld_ = [z for z in w.log.toPlainText().split("\n") if z.startswith("Vernetzt:")]
        check("Das Protokoll meldet das Netz mit Laufzeit (und den Prozessen, wenn parallel)",
              meld_ and " s" in meld_[-1], str(meld_[-1:]))
        check("Das Protokoll nennt beide Volumen mit Tetraedern",
              sum(1 for z in w.log.toPlainText().split("\n") if z.startswith("Volumen V") and "Tetraeder" in z) >= 2)
        # Abbrechen beim ersten Volumen-Rückruf: Flächen bleiben, die Volumen ohne Netz
        alt_fort = w._fortschritt

        def stop_(wert, text):
            r = alt_fort(wert, text)
            if "Vernetze Volumen" in str(text) and not w._abbruch:
                w._fortschritt_abbrechen()
                return False
            return r
        w._fortschritt = stop_
        w.geometrie_vernetzen()
        app.processEvents()
        w._fortschritt = alt_fort
        check("Abbrechen mitten in den Volumen: kein Volumennetz, Protokoll nennt den Abbruch, Balken weg",
              not k1_.elemente and not k2_.elemente and "abgebrochen" in w.log.toPlainText()
              and not w.progress_bar.isVisible() and not w._abbruch,
              str((len(k1_.elemente), len(k2_.elemente))))
        w.error = alt_error
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Volumen parallel vernetzen (#122/#123)", False, str(ex)[:70])

    # ---- Klick und Ziehen; Bericht ohne Berechnung ---------------------------
    try:
        from PySide6 import QtCore, QtGui
        from statik3d.gui import dialogs as dlg_
        w.load_example("hall")
        app.processEvents()
        it_ = w.plotter.interactor
        treffer_ = []
        alt_picked = w._picked
        w._picked = lambda point, *a: treffer_.append(np.asarray(point))

        def maus_(typ, pos, knopf, knoepfe):
            ev = QtGui.QMouseEvent(typ, QtCore.QPointF(pos), QtCore.QPointF(pos), knopf, knoepfe,
                                   QtCore.Qt.NoModifier)
            QtWidgets.QApplication.sendEvent(it_, ev)
            app.processEvents()

        mitte_ = QtCore.QPoint(it_.width() // 2, it_.height() // 2)
        maus_(QtCore.QEvent.MouseButtonPress, mitte_, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        maus_(QtCore.QEvent.MouseButtonRelease, mitte_, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        check("Klick ohne Bewegung wählt (beim Loslassen)", len(treffer_) == 1 and w._klick_wartend is None,
              str(len(treffer_)))
        maus_(QtCore.QEvent.MouseButtonPress, mitte_, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        for d_ in (5, 15, 30):
            maus_(QtCore.QEvent.MouseMove, mitte_ + QtCore.QPoint(d_, d_), QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
        maus_(QtCore.QEvent.MouseButtonRelease, mitte_ + QtCore.QPoint(30, 30), QtCore.Qt.LeftButton,
              QtCore.Qt.NoButton)
        check("Klicken und Ziehen zieht ein Auswahlfenster auf, wählt aber nichts einzeln",
              len(treffer_) == 1 and w._fenster_ecke is None, str(len(treffer_)))

        # Befund N: links zieht nur das Fenster auf, rechts dreht
        stil_ = w.plotter.iren.style
        # VTKIS_NONE = 0. Aus den Ereignissen davor kann der Stil noch in einem
        # Zustand stehen; fuer die Pruefung wird er zurueckgesetzt.
        stil_.EndRotate()
        ruhe_ = 0
        maus_(QtCore.QEvent.MouseButtonPress, mitte_, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        maus_(QtCore.QEvent.MouseMove, mitte_ + QtCore.QPoint(40, 40), QtCore.Qt.NoButton,
              QtCore.Qt.LeftButton)
        check("die linke Taste dreht nicht mehr (VTK sieht sie nicht)",
              stil_.GetState() == ruhe_ and w._fenster_ecke is not None,
              f"Zustand {stil_.GetState()} (Ruhe {ruhe_}), Fenster "
              f"{w._fenster_ecke is not None}")
        maus_(QtCore.QEvent.MouseButtonRelease, mitte_ + QtCore.QPoint(40, 40),
              QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        check("und beim Loslassen ist das Fenster ausgewertet", w._fenster_ecke is None,
              str(w._fenster_ecke))
        stil_.EndRotate()
        menues_ = []
        alt_menu = w._viewport_menu
        w._viewport_menu = lambda p: menues_.append(QtCore.QPoint(p))
        # 15.09.2026: „bei gedrückter mittlerer Maustaste soll gedreht werden",
        # „gedrückte rechte Maustaste und halten soll schieben sein"
        # (VTKIS_ROTATE = 1, VTKIS_PAN = 2)
        maus_(QtCore.QEvent.MouseButtonPress, mitte_, QtCore.Qt.MiddleButton, QtCore.Qt.MiddleButton)
        check("die mittlere Taste versetzt VTK ins Drehen", stil_.GetState() == 1,
              f"Zustand {stil_.GetState()} (Drehen 1, Schieben 2)")
        maus_(QtCore.QEvent.MouseButtonRelease, mitte_ + QtCore.QPoint(30, 0),
              QtCore.Qt.MiddleButton, QtCore.Qt.NoButton)
        check("beim Loslassen der mittleren Taste endet das Drehen, ohne Menü",
              stil_.GetState() == ruhe_ and not menues_, f"Zustand {stil_.GetState()}, {len(menues_)} Menüs")
        maus_(QtCore.QEvent.MouseButtonPress, mitte_, QtCore.Qt.RightButton, QtCore.Qt.RightButton)
        check("die rechte Taste versetzt VTK ins Schieben", stil_.GetState() == 2,
              f"Zustand {stil_.GetState()} (Drehen 1, Schieben 2)")
        maus_(QtCore.QEvent.MouseButtonRelease, mitte_, QtCore.Qt.RightButton, QtCore.Qt.NoButton)
        check("beim Loslassen ohne Zug endet das Schieben und das Menü kommt",
              stil_.GetState() == ruhe_ and len(menues_) == 1,
              f"Zustand {stil_.GetState()}, {len(menues_)} Menüs")
        maus_(QtCore.QEvent.MouseButtonPress, mitte_, QtCore.Qt.RightButton, QtCore.Qt.RightButton)
        maus_(QtCore.QEvent.MouseButtonRelease, mitte_ + QtCore.QPoint(40, 10),
              QtCore.Qt.RightButton, QtCore.Qt.NoButton)
        check("mit Zug (geschoben) kommt kein Menü", len(menues_) == 1, f"{len(menues_)} Menüs")
        w._viewport_menu = alt_menu
        w._picked = alt_picked

        # Befund E: waehrend einer Rechnung oeffnet nichts Modales. error() ist
        # in diesem Test durch einen Melder ersetzt - geprueft wird darum die
        # Sperre selbst und der Weg von warnung() und _fragen().
        w._rechnet_gerade = True
        zeilen_ = w.log.toPlainText()
        MainWindow.error(w, "Etwas ist schiefgegangen")
        w.warnung("Und etwas anderes auch")
        antwort_ = w._fragen("Titel", "Trotzdem weiter?")
        w._rechnet_gerade = False
        neu_ = w.log.toPlainText()[len(zeilen_):]
        check("während der Rechnung geht der Fehler ins Protokoll statt in eine Box",
              "FEHLER: Etwas ist schiefgegangen" in neu_
              and "WARNUNG: Und etwas anderes auch" in neu_, neu_.strip()[:120])
        check("und eine Rückfrage, die niemand sehen kann, wird verneint",
              antwort_ is False and "während der Rechnung verneint" in neu_,
              str(antwort_))

        # Abnahme des Netzes vor dem Rechnen: jede Verletzung einzeln ins
        # Protokoll, die Rückfrage fasst nur zusammen
        from statik3d.model import ContactPair as CP_
        w.model.contact_pairs.append(CP_("Prüffuge", slave_nodes=[0],
                                         master_faces=[[0, 1, 2]], abdeckung=0.42))
        alt_fragen = w._fragen
        gefragt_ = []
        w._fragen = lambda t, x: (gefragt_.append((t, x)), False)[1]
        vorher_ = w.log.toPlainText()
        weiter_ = w._abnahme_bestaetigen()
        w._fragen = alt_fragen
        w.model.contact_pairs.pop()
        neu2_ = w.log.toPlainText()[len(vorher_):]
        check("die Abnahme nennt jede Verletzung einzeln im Protokoll",
              "FEHLER: [Abdeckung der Kontaktseite] Kontaktpaar Prüffuge: nur 42 %" in neu2_,
              next((z for z in neu2_.splitlines() if "Prüffuge" in z), neu2_[:100]))
        check("und die Rückfrage fasst sie zusammen; „Nein“ hält den Lauf an",
              weiter_ is False and len(gefragt_) == 1
              and "1x Abdeckung der Kontaktseite" in gefragt_[0][1],
              str(gefragt_)[:140])
        alt_exec = dlg_.ReportDialog.exec
        dlg_.ReportDialog.exec = lambda self: 0
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w.analysis = None
        w.results = None
        w.make_report()
        app.processEvents()
        dlg_.ReportDialog.exec = alt_exec
        w.error = alt_error
        check("Bericht ohne Berechnung: kein „Zuerst berechnen“, Dialog öffnet, Hinweis im Protokoll",
              not fehler_ and "Bericht ohne Berechnung" in w.log.toPlainText(), str(fehler_))
        from statik3d.report.html import Report as Rep_
        html_ = Rep_(w.model).html()
        check("Bericht ohne Ergebnisse enthält Modell und Einwirkungen und nennt fehlende Ergebnisse",
              "Einwirkungen" in html_ and "keine Berechnungsergebnisse" in html_, str(len(html_)))
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Klick und Ziehen / Bericht ohne Berechnung", False, str(ex)[:70])

    # ---- Einheiten und Genauigkeiten (Ansicht -> Einheiten) ----------------
    try:
        import json
        from statik3d.model import Member as Mb
        w.new_model()
        m_ = w.model
        w.error = lambda text: None
        w._bestaetigen = lambda text: True
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        k0 = m_.add_node(0, 0, 0)
        k1 = m_.add_node(4, 0, 0)
        k2 = m_.add_node(4, 3, 0)
        e0 = m_.add_element("beam", [k0, k1], mat_, sec_)
        e1 = m_.add_element("beam", [k1, k2], mat_, sec_)
        m_.members["S1"] = Mb("S1", elements=[e0])
        m_.members["S2"] = Mb("S2", elements=[e1])
        m_.fix(k0, "all")
        m_.fix(k2, [0, 1, 2])
        m_.load_node(k1, Fz=-12500.0)
        m_.load_beam(e0, qz=-5000.0)
        w.refresh_all()
        app.processEvents()
        mk_ = w.tbl_knoten.modell
        check("Vorgabe: Knotentabelle x [m] mit 4,000, Lasten [kN, kN/m]",
              w.tbl_knoten.kopfzeile()[1] == "x [m]" and mk_.data(mk_.index(1, 1)) == "4,000"
              and any("[kN, kN/m]" in z for z in w._kopfzeile_zeilen),
              str((w.tbl_knoten.kopfzeile()[:2], mk_.data(mk_.index(1, 1)), w._kopfzeile_zeilen)))
        an_ = solver.solve_all(m_, design=True)
        w._solve_done("all", an_)
        w.cb_field.setCurrentText("|u| Verschiebung")
        w.cb_diagram.setCurrentText("kein Verlauf")
        app.processEvents()
        check("Kennwerte unten links: u in [mm] - und nur u, weil |u| gewählt ist",
              any(z.startswith("u ") and "[mm]" in z for z in w._kennwerte_zeilen)
              and not any(z.startswith(("Rz", "ux", "sig_v")) for z in w._kennwerte_zeilen),
              str(w._kennwerte_zeilen[:3]))
        rk_ = w.tbl_react.modell
        # Auflagerkraefte stehen als „min / max“-Paar (Umhuellende) oder als Zahl
        roh_ = str(rk_.zeilen[0][3])
        rz_kN = float(roh_.split("/")[0].replace(",", "."))
        paar_ = "/" in roh_
        maske_ = w.maske_einheiten()
        check("Maske „Einheiten und Genauigkeiten“ rechts mit Kraft, Länge, Verformung, Spannung",
              w.eingaben_dock.windowTitle() == "Einheiten und Genauigkeiten"
              and all(k in maske_.werte() for k in ("kraft", "laenge", "verformung", "spannung", "nk_kraft")),
              str(sorted(maske_.werte())))
        w._einheiten_setzen({"kraft": "N", "laenge": "mm", "verformung": "cm", "spannung": "kN/cm²",
                             "nk_kraft": 0, "nk_last": 1, "nk_laenge": 1, "nk_verformung": 3,
                             "nk_spannung": 2, "nk_winkel": 1, "nk_ausnutzung": 2})
        app.processEvents()
        check("Modell trägt die Einheiten (N, mm, cm, kN/cm²)",
              m_.einheiten.kraft == "N" and m_.einheiten.laenge == "mm" and m_.einheiten.nk_kraft == 0)
        check("Tabellenköpfe folgen: x [mm], Rx [N], Mx [Nmm]",
              w.tbl_knoten.kopfzeile()[1] == "x [mm]" and w.tbl_react.kopfzeile()[1] == "Rx [N]"
              and w.tbl_react.kopfzeile()[4] == "Mx [Nmm]",
              str((w.tbl_knoten.kopfzeile()[1], w.tbl_react.kopfzeile()[1:5])))
        rz_zelle = str(rk_.data(rk_.index(0, 3)))
        check("Zellen folgen: x = 4000,0 mm; Rz in N ohne Nachkomma (auch als min/max-Paar)",
              mk_.data(mk_.index(1, 1)) == "4000,0"
              and rz_zelle.split("/")[0].strip() == f"{rz_kN * 1000:.0f}".replace(".", ","),
              str((mk_.data(mk_.index(1, 1)), rz_zelle, rz_kN)))
        if not paar_:
            check("Filter und Sortierung in der Anzeigeeinheit (UserRole = N)",
                  abs(float(rk_.data(rk_.index(0, 3), QtCore.Qt.UserRole)) - rz_kN * 1000) < 1e-6)
        csv_ = w.tbl_react.text().splitlines()
        check("CSV-Export in der Anzeigeeinheit: Kopf [N], Wert in N",
              csv_[0].startswith("Knoten;Rx [N];Ry [N];Rz [N];Mx [Nmm]")
              and abs(float(csv_[1].split(";")[3].split("/")[0].replace(",", ".")) - rz_kN * 1000) < 1e-6,
              str(csv_[:2]))
        check("Lasten oben links in [N, N/mm], Kennwerte u in [cm]",
              any("[N, N/mm]" in z for z in w._kopfzeile_zeilen)
              and any(z.startswith("u ") and "[cm]" in z for z in w._kennwerte_zeilen),
              str((w._kopfzeile_zeilen, w._kennwerte_zeilen[:2])))
        ok_ = mk_.setData(mk_.index(1, 1), "4500", QtCore.Qt.EditRole)
        check("Eingabe in der Tabelle in mm: 4500 -> Knoten x = 4,5 m",
              ok_ and abs(float(m_.nodes[1, 0]) - 4.5) < 1e-9, str(m_.nodes[1, 0]))
        m2_ = Model.from_dict(json.loads(json.dumps(m_.to_dict())))
        check("Einheiten werden mit dem Modell gespeichert",
              m2_.einheiten.kraft == "N" and m2_.einheiten.nk_last == 1 and m2_.einheiten.spannung == "kN/cm²")
        breiten_ = []
        for name_ in w.tab_unten.tabellen("Modell"):
            w.tab_unten.zeigen(name_)
            app.processEvents()
            breiten_.append(w.tab_unten.minimumSizeHint().width())
        check("Tabellen zwingen dem Fenster keine Mindestbreite auf (< 700 px, auch nach dem Durchgehen)",
              max(breiten_) < 700 and w.minimumSizeHint().width() < 900,
              str((breiten_, w.minimumSizeHint().width())))
        t_ = w.tbl_knoten
        check("Filterfelder liegen über den Spalten der Kopfzeile",
              all(abs(t_.felder[k].width() - (t_.view.columnWidth(k) - 2)) <= 2
                  for k in range(min(3, len(t_.felder)))) and t_.filterzeile.minimumWidth() == 0,
              str([(t_.felder[k].width(), t_.view.columnWidth(k)) for k in range(3)]))
        w.undo()
        w.undo()
        app.processEvents()
        # Rueckgaengig tauscht das Modellobjekt - darum ueber w.model pruefen
        check("Rückgängig stellt kN und m wieder her",
              w.model.einheiten.kraft == "kN" and w.tbl_knoten.kopfzeile()[1] == "x [m]"
              and w.tbl_react.kopfzeile()[1] == "Rx [kN]",
              str((w.model.einheiten.kraft, w.tbl_knoten.kopfzeile()[1])))
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Einheiten und Genauigkeiten", False, str(ex)[:70])

    # ---- Glasleiste rechts, Geist im Hintergrund, Wahlregel, Lagerdichte ----
    try:
        # ---- Glasleiste: „Alles deselektieren“ ganz rechts, Geist-Knopf ----------
        kn = w.glasleiste.knoepfe
        lay = w.glasleiste.lay
        letzter = lay.itemAt(lay.count() - 1).widget()
        check("Glasleiste: „Alles deselektieren“ steht ganz rechts",
              letzter is kn["auswahl_weg"], type(letzter).__name__)
        check("Glasleiste: Knopf „Verborgenes im Hintergrund“",
              "geist" in kn and kn["geist"].defaultAction() is w.act_geist and w.act_geist.isCheckable())

        # ---- Glasleiste: Aufklappliste fuer Lastfaelle und Kombinationen ---------
        from statik3d import solver as _slv
        w.load_example("hall")
        app.processEvents()
        cbl = w.cb_lastwahl
        check("Glasleiste: Aufklappliste ganz links",
              w.glasleiste.lay.itemAt(0).widget() is cbl
              and w.glasleiste.listen.get("lastwahl") is cbl,
              type(w.glasleiste.lay.itemAt(0).widget()).__name__)
        eintr = [(cbl.itemText(i), cbl.itemData(i)) for i in range(cbl.count())]
        check("sie führt jeden Lastfall und jede Kombination",
              len(eintr) == len(w.model.load_cases) + len(w.model.combinations)
              and eintr[0][1] == ("case", list(w.model.load_cases)[0])
              and any(d[0] == "combo" for _t, d in eintr),
              f"{len(eintr)} Einträge zu {len(w.model.load_cases)} Lastfällen "
              f"und {len(w.model.combinations)} Kombinationen")
        check("und steht auf dem, was die Ansicht zeigt",
              cbl.currentData() == ("case", w.model.active_case), str(cbl.currentData()))
        zweiter = next(i for i, (_t, d) in enumerate(eintr)
                       if d[0] == "case" and d[1] != w.model.active_case)
        cbl.setCurrentIndex(zweiter)
        app.processEvents()
        check("ein Lastfall daraus wird der aktive",
              w.model.active_case == eintr[zweiter][1][1], w.model.active_case)
        i_kombi = next(i for i, (_t, d) in enumerate(eintr) if d[0] == "combo")
        cbl.setCurrentIndex(i_kombi)
        app.processEvents()
        check("eine Kombination ohne Ergebnis sagt, woran es liegt",
              "sobald gerechnet ist" in w.log.toPlainText().splitlines()[-1],
              w.log.toPlainText().splitlines()[-1][:80])
        an_ = _slv.solve_all(w.model, design=bool(w.model.members))
        w._solve_done("all", an_)
        app.processEvents()
        cbl.setCurrentIndex(i_kombi)
        app.processEvents()
        check("mit Ergebnis schaltet sie die Ergebnisliste mit um",
              w.cb_result.currentData() == eintr[i_kombi][1],
              f"{w.cb_result.currentData()} statt {eintr[i_kombi][1]}")
        # und umgekehrt: was die Ergebnisliste zeigt, steht auch in der Leiste
        for i_ in range(w.cb_result.count()):
            if w.cb_result.itemData(i_)[0] == "case":
                w.cb_result.setCurrentIndex(i_)
                break
        app.processEvents()
        check("und die Leiste zieht nach, wenn das Ergebnis anders gewählt wird",
              cbl.currentData() == w.cb_result.currentData(),
              f"{cbl.currentData()} / {w.cb_result.currentData()}")
        # Das Ergebnis gehoert zu diesem Modell - der naechste Abschnitt setzt
        # ein anderes ein. Ohne Loeschen zeichnete die Ansicht Werte des alten
        # Modells auf das neue.
        w.analysis = None
        w.results = None

        # ---- Geist: Verborgenes blass im Hintergrund, nicht anklickbar -----------
        from statik3d import examples_lib as _ex
        from statik3d.gui import viewport as _vp
        import pyvista as pvx
        w.model = _ex.hall_frame_example()
        w.refresh_all()
        app.processEvents()
        stab = list(w.model.members)[0]
        elems = {int(e) for e in w.model.members[stab].elements}
        w.sel_staebe = [stab]
        w.auswahl_ausblenden()
        app.processEvents()
        check("Geist aus: kein Geist-Darsteller",
              not any(n.startswith("geist_") for n in dict(w.plotter.renderer.actors)))
        w.act_geist.setChecked(True)
        app.processEvents()
        akt = dict(w.plotter.renderer.actors)
        check("Geist an: die ausgeblendeten Elemente stehen als Geist im Bild",
              w.geist and "geist_netz" in akt, str([n for n in akt if n.startswith("geist")]))
        if "geist_netz" in akt:
            g_ = pvx.wrap(akt["geist_netz"].GetMapper().GetInput())
            check("Geist zeigt genau die ausgeblendeten Elemente",
                  set(np.asarray(g_.cell_data["elem"]).tolist()) == elems, str(len(elems)))
            check("Geist ist nicht anklickbar", not akt["geist_netz"].GetPickable())
            check("Geist ist blass", akt["geist_netz"].GetProperty().GetOpacity() < 0.3,
                  str(akt["geist_netz"].GetProperty().GetOpacity()))
        check("Zellenpicker kennt den Geist nicht: Ausgeblendetes ist nicht wählbar",
              not w._objekt_sichtbar("Stab", stab) and all(not w._objekt_sichtbar("Netz", e) for e in elems))
        andere = [n for n in w.model.members if n != stab]
        check("Sichtbare Stäbe bleiben wählbar", all(w._objekt_sichtbar("Stab", n) for n in andere))
        w.auswahlart_setzen("Stab")
        w.sel_staebe = []
        w.plotter.view_isometric()
        w.plotter.reset_camera()
        w.redraw()
        app.processEvents()
        xy_, _s = w._projizieren(w.model.nodes)
        rect_ = (xy_[:, 0].min() - 4, xy_[:, 1].min() - 4, xy_[:, 0].max() + 4, xy_[:, 1].max() + 4)
        n_ = w._fenster_auswaehlen(rect_, True)
        check("Fensterauswahl lässt den ausgeblendeten Stab aus",
              stab not in w.sel_staebe and n_ == len(andere), f"{n_} von {len(andere)}: {w.sel_staebe}")
        w.sel_staebe = []
        w.act_staebe.setChecked(False)
        app.processEvents()
        n_ = w._fenster_auswaehlen(rect_, True)
        check("Schalter „Stäbe“ aus: Stäbe sind nicht dargestellt und nicht wählbar",
              not w._dargestellt("Stab") and n_ == 0 and not w.sel_staebe, str(n_))
        w.act_staebe.setChecked(True)
        w.act_geist.setChecked(False)
        app.processEvents()
        check("Geist aus: Darsteller wieder weg",
              not w.geist and not any(n.startswith("geist_") for n in dict(w.plotter.renderer.actors)))
        w.alles_zeigen()
        w.auswahlart_setzen("Knoten")
        app.processEvents()

        # ---- Lagerdichte wirkt: Flächenlager über die Geometriefläche -------------
        from statik3d.model import Model as _M, Material as _Mat, ShellProp as _SP
        from statik3d import mesher as _me, supports as _su
        mp = _M("Platte auf Bettung")
        mp.add_material(_Mat("steif", E=210e12))
        mp.add_shell_prop(_SP("t", 0.2))
        mp.add_nodes([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0]])
        for i_ in range(4):
            mp.add_line(f"L{i_ + 1}", [i_, (i_ + 1) % 4], "polyline")
        fp = mp.add_flaeche("Platte", ["L1", "L2", "L3", "L4"], material="steif", dicke="t", teilung=[4, 2])
        _me.mesh_flaeche(mp, fp)
        ssp = mp.add_surface_support(name="Bettung", nodes=[0, 1, 2, 3], areas=[0.5] * 4,
                                     uz=dict(typ="spring", stiffness=1e8))
        ssp.flaechen = ["Platte"]
        _su.lager_auf_netz(mp)
        w.model = mp
        w.refresh_all()
        app.processEvents()
        size_ = mp.characteristic_size()
        n_duenn = len(_vp.lager_punkte(mp, ssp, size_, 0.5)[0])
        n_dicht = len(_vp.lager_punkte(mp, ssp, size_, 3.0)[0])
        check("Lagerdichte wirkt: mehr Symbole bei höherer Dichte",
              n_dicht > 4 * n_duenn > 0, f"{n_duenn} -> {n_dicht}")
        def _lagerpunkte():
            akt_ = dict(w.plotter.renderer.actors)
            return sum(akt_[n].GetMapper().GetInput().GetNumberOfPoints() for n in akt_ if n.startswith("fsupports"))
        w.sl_lagerdichte.setValue(5)
        app.processEvents()
        p_duenn = _lagerpunkte()
        w.sl_lagerdichte.setValue(30)
        app.processEvents()
        p_dicht = _lagerpunkte()
        check("Schieber „Dichte“ zeichnet sofort neu: mehr Symbole im Bild",
              w.lagerdichte == 3.0 and p_dicht > 2 * p_duenn > 0, f"{p_duenn} -> {p_dicht} Punkte")
        check("Schieber „Lager“ (Größe) steht daneben",
              w.sl_lager.isVisibleTo(w) or w.sl_lager.parent() is not None)
        w.lagerdichte_zuruecksetzen()
        app.processEvents()
        check("Lagerdichte zurücksetzen: 1,0 und Schieber auf 10",
              w.lagerdichte == 1.0 and w.sl_lagerdichte.value() == 10)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Geist, Glasleiste, Lagerdichte", False, str(ex)[:70])

    # ---- Elementtypen: Verbindungsobjekte, Stabmaske, Lagermaske ---------
    try:
        # --- Verbindungsobjekte in der Oberflaeche --------------------------------
        import numpy as _np
        from statik3d.model import Material as _Mat, Section as _Sec
        w.new_model()
        mv = w.model
        mv.add_material(_Mat("S235", E=210e9, nu=0.3, rho=7850))
        mv.add_section(_Sec("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5, Iw=1e-7))
        n0 = mv.add_node(0, 0, 0); n1 = mv.add_node(1, 0, 0); n2 = mv.add_node(2, 0, 0)
        mv.add_element("beam", [n0, n1], "S235", "R")
        mv.add_feder_prop("F1", [1e6, 1e6, 1e6, 0, 0, 0])
        mv.add_element("feder", [n1, n2], "S235", "F1")
        mv.add_punktmasse(n2, 250.0, [1.0, 2.0, 3.0])
        mv.add_daempfer(n2, -1, [40.0, 0, 0, 0, 0, 0])
        mv.add_starrkoerper(n0, [n1], "RBE2")
        mv.add_grenzschicht_prop("GS", 1e9, 5e8)
        w.refresh_all()
        app.processEvents()

        def _zweige(baum):
            aus = {}
            def lauf(x, tiefe=0):
                for k in range(x.childCount()):
                    kind = x.child(k)
                    aus[kind.text(0)] = kind
                    lauf(kind, tiefe + 1)
            lauf(baum.invisibleRootItem())
            return aus

        zw = _zweige(w.baum)
        check("Modellbaum: Zweig „Verbindungen“", "Verbindungen" in zw, str(sorted(zw)[:12]))
        for name in ("Punktmassen", "Dämpfer", "Federn", "Starre Körper", "Grenzschichten"):
            check(f"Modellbaum: Unterzweig „{name}“", name in zw)

        # Maske einer Punktmasse
        w._objektmaske("punktmasse", "0")
        mk = w.maskenrand.maske
        check("Punktmassenmaske öffnet", mk is not None and "Punktmasse" in mk.titel, str(mk and mk.titel))
        werte = mk.werte()
        check("Punktmassenmaske zeigt Masse und Drehträgheit",
              abs(float(werte["masse"]) - 250.0) < 1e-9 and abs(float(werte["Jy"]) - 2.0) < 1e-9,
              str({k: werte[k] for k in ("masse", "Jx", "Jy", "Jz")}))
        mk.setzen("masse", 400.0)
        w._objekt_uebernehmen("punktmasse", "0", mk.werte(), False)
        check("Punktmasse geändert", abs(w.model.punktmassen[0].masse - 400.0) < 1e-9,
              str(w.model.punktmassen[0].masse))

        # Feder
        w._objektmaske("feder", "F1")
        mk = w.maskenrand.maske
        check("Federmaske öffnet", mk is not None and "Feder" in mk.titel)
        mk.setzen("kx", 2.5e6)
        w._objekt_uebernehmen("feder", "F1", mk.werte(), False)
        check("Federsteifigkeit geändert", abs(w.model.federn["F1"].k[0] - 2.5e6) < 1e-6,
              str(w.model.federn["F1"].k[:3]))

        # Starrer Koerper
        w._objektmaske("starrkoerper", "0")
        mk = w.maskenrand.maske
        mk.setzen("art", "RBE3")
        w._objekt_uebernehmen("starrkoerper", "0", mk.werte(), False)
        check("Starrer Körper auf RBE3 umgestellt", w.model.starrkoerper[0].art == "RBE3",
              w.model.starrkoerper[0].art)

        # Grenzschicht
        w._objektmaske("grenzschicht", "GS")
        mk = w.maskenrand.maske
        mk.setzen("kn", 2e9)
        w._objekt_uebernehmen("grenzschicht", "GS", mk.werte(), False)
        check("Grenzschicht geändert", abs(w.model.grenzschichten["GS"].kn - 2e9) < 1e-3)

        # Klick im Baum waehlt die Knoten
        w._baum_objekt_waehlen("punktmasse", "0")
        check("Klick auf die Punktmasse wählt ihren Knoten",
              list(w.selection) == [n2], str(list(w.selection)))

        # --- Stabmaske: neue Felder ------------------------------------------------
        w._objektmaske("stabelement", "0")
        mk = w.maskenrand.maske
        werte = mk.werte()
        check("Stabmaske: Art, trägt nur, Versatz, Wölbkrafttorsion",
              all(k in werte for k in ("typ", "nur", "laenge0", "ex_a", "ex_e", "woelb")),
              str(sorted(werte)))
        check("Stabmaske: Seil ist wählbar", "Seil" in w.STABARTEN)
        mk.setzen("nur", "nur Zug")
        mk.setzen("typ", "Fachwerkstab")
        mk.setzen("ex_a", "0, 50")
        mk.setzen("woelb", True)
        w._objekt_uebernehmen("stabelement", "0", mk.werte(), False)
        e0 = w.model.elements[0]
        check("Stab: nur Zug übernommen", e0.nur == "zug" and e0.typ == "truss", f"{e0.typ}/{e0.nur}")
        check("Stab: Versatz in Metern gespeichert",
              abs(e0.exzentrizitaet[0][2] - 0.05) < 1e-12, str(e0.exzentrizitaet))
        check("Stab: Wölbkrafttorsion gesetzt", bool(e0.woelb))

        # --- Lagermaske: Woelbeinspannung -----------------------------------------
        w.model.fix(n0, "all")
        w.refresh_all()
        w._objektmaske("lager_einzeln", "0")
        mk = w.maskenrand.maske
        check("Lagermaske hat die Wölbeinspannung", "woelb" in mk.werte(), str(sorted(mk.werte()))[:120])
        mk.setzen("woelb", True)
        w._objekt_uebernehmen("lager_einzeln", "0", mk.werte(), False)
        check("Wölbeinspannung übernommen", bool(w.model.supports[0].woelb))

        # --- Netzeinstellungen: Elementansatz --------------------------------------
        check("Netzmaske: quadratisch nennt shell6/shell8 und hex20",
              any("shell8" in k and "hex20" in k for k in w.NETZORDNUNG),
              str(list(w.NETZORDNUNG)))
        w.new_model()

    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Verbindungsobjekte und neue Masken", False, str(ex)[:70])

    # ---- Nummerierung je Objektart: Ribbon, Zeichnen, Rechtsklick --------
    try:
        from statik3d.model import Material as _MatN, Section as _SecN
        w.new_model()
        mn = w.model
        mn.add_material(_MatN("S235", E=210e9, nu=0.3, rho=7850))
        mn.add_section(_SecN("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5, Iw=1e-7))
        # Quader aus zwoelf Linien und sechs Flaechen, dazu ein Stab und ein Lager
        P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
                      [0, 0, 1], [2, 0, 1], [2, 1, 1], [0, 1, 1.]])
        mn.add_nodes(P)
        kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                  (0, 4), (1, 5), (2, 6), (3, 7)]
        for i, (a, b) in enumerate(kanten):
            mn.add_line(f"K{i + 1}", [a, b])
        seiten = {"Boden": ["K1", "K2", "K3", "K4"], "Deckel": ["K5", "K6", "K7", "K8"],
                  "S1": ["K1", "K10", "K5", "K9"], "S2": ["K2", "K11", "K6", "K10"],
                  "S3": ["K3", "K12", "K7", "K11"], "S4": ["K4", "K9", "K8", "K12"]}
        for nme, ls in seiten.items():
            mn.add_flaeche(nme, ls, material="S235")
        kk = mn.add_koerper("V1", list(seiten), material="S235", teilung=[2, 1, 1])
        w._vernetzen([], [kk])
        a0 = mn.add_node(0, 0, 2); a1 = mn.add_node(2, 0, 2)
        e_stab = mn.add_element("beam", [a0, a1], "S235", "R")
        mn.add_member("St1", [e_stab])
        mn.fix(0, "all")
        w.refresh_all()
        app.processEvents()

        # --- Ribbon Ansicht: ein Schalter je Objektart --------------------------
        arten = list(w.NUMMERN)
        check("Ribbon Ansicht: Gruppe „Nummern“ mit einem Schalter je Objektart",
              sorted(w.act_nummern) == sorted(arten) and len(arten) == 7, str(arten))
        check("Nummernschalter sind Umschalter und anfangs aus",
              all(a.isCheckable() and not a.isChecked() for a in w.act_nummern.values()))
        check("Die alten Namen zeigen weiter auf Knoten und Elemente",
              w.act_nodes is w.act_nummern["Knoten"] and w.act_elems is w.act_nummern["Elemente"])
        check("Jeder Schalter hat einen Hinweis",
              all(len(w.NUMMERN[a][3]) > 10 for a in arten))
        check("und im Ribbon eine eigene Beschriftung - die Sichtbarkeitsschalter "
              "heißen schon „Knoten“, „Linien“, „Flächen“, „Volumen“",
              len({w.NUMMERN[a][4] for a in arten}) == 7
              and not ({w.NUMMERN[a][4] for a in arten} & set(arten)),
              str([w.NUMMERN[a][4] for a in arten]))
        check("Jede Art hat ihre eigene Schriftfarbe",
              len({w.NUMMERN[a][0] for a in arten}) == 7,
              str([w.NUMMERN[a][0] for a in arten]))

        # --- Marken je Art: Punkt und Beschriftung ------------------------------
        pk, tk = w._nummernmarken(mn, "Knoten", None)
        from statik3d.gui import viewport as vp_n
        n_konstr = len(vp_n.konstruktionsknoten(mn))
        check("Knoten: eine Nummer je Knoten der Konstruktion (Netzknoten des Körpers nicht), am Knoten",
              len(tk) == n_konstr and 0 < n_konstr < mn.nn and tk[0] == "0" and abs(pk[1][0] - 2.0) < 1e-9,
              f"{len(tk)} Marken, {n_konstr} Konstruktion von {mn.nn}")
        pe, te = w._nummernmarken(mn, "Elemente", None)
        check("Elemente: eine Nummer je Element, in seiner Mitte",
              len(te) == len(mn.elements) and te[0] == "0", f"{len(te)} Marken")
        pl, tl = w._nummernmarken(mn, "Linien", None)
        check("Linien: der Name an jeder Linie",
              sorted(tl) == sorted(f"K{i + 1}" for i in range(12)), str(sorted(tl)[:4]))
        check("Linienmarke sitzt auf der Linie",
              abs(pl[list(tl).index("K1")][1]) < 1e-9
              and 0.0 <= pl[list(tl).index("K1")][0] <= 2.0, str(pl[list(tl).index("K1")]))
        ps, ts = w._nummernmarken(mn, "Stäbe", None)
        check("Stäbe: der Name am Stab", list(ts) == ["St1"]
              and abs(ps[0][2] - 2.0) < 1e-9, f"{list(ts)} {ps}")
        pf, tf = w._nummernmarken(mn, "Flächen", None)
        check("Flächen: der Name an jeder Fläche",
              sorted(tf) == sorted(seiten), str(sorted(tf)))
        check("Flächenmarke liegt in der Fläche (Boden bei z = 0)",
              abs(pf[list(tf).index("Boden")][2]) < 1e-9, str(pf[list(tf).index("Boden")]))
        pv, tv = w._nummernmarken(mn, "Volumen", None)
        check("Volumen: der Name im Körper",
              list(tv) == ["V1"] and np.allclose(pv[0], [1.0, 0.5, 0.5]), str(pv))
        pg, tg = w._nummernmarken(mn, "Lager", None)
        check("Lager: die Nummer am Lagerknoten",
              list(tg) == ["1"] and np.allclose(pg[0], [0, 0, 0]), f"{list(tg)} {pg}")

        # --- Sichtbarkeit: keine Nummer ohne ihr Objekt --------------------------
        w.act_volumen.setChecked(False)
        check("Volumen ausgeschaltet: keine Volumennummern",
              not w._nummernmarken(mn, "Volumen", None)[1])
        check("Volumen ausgeschaltet: auch die Volumenelemente bekommen keine Nummer "
              "- nur das Stabelement bleibt",
              w._nummernmarken(mn, "Elemente", None)[1] == [str(e_stab)],
              str(w._nummernmarken(mn, "Elemente", None)[1])[:60])
        w.act_volumen.setChecked(True)
        w.versteckt["linien"] = {"K1"}
        tl2 = w._nummernmarken(mn, "Linien", None)[1]
        check("Ausgeblendete Linie bekommt keine Nummer",
              "K1" not in tl2 and len(tl2) == 11, str(len(tl2)))
        w.versteckt["linien"] = set()
        w.versteckt["flaechen"] = {"Deckel"}
        check("Ausgeblendete Fläche bekommt keine Nummer",
              "Deckel" not in w._nummernmarken(mn, "Flächen", None)[1])
        w.versteckt["flaechen"] = set()
        check("Nur die sichtbaren Knoten bekommen eine Nummer",
              list(w._nummernmarken(mn, "Knoten", [1, 3])[1]) == ["1", "3"])
        check("Lager an ausgeblendeten Knoten bekommen keine Nummer",
              not w._nummernmarken(mn, "Lager", [1, 3])[1])

        # --- Zeichnen: jede Art ein eigener Darsteller ---------------------------
        vorher = len(w.log.toPlainText())
        for a in w.act_nummern.values():
            a.setChecked(True)
        w.redraw(); app.processEvents()
        namen = set(w.plotter.renderer.actors)
        check("Jede Objektart bekommt ihren eigenen Darsteller",
              all(any(str(x).startswith(f"nummern:{art}") for x in namen) for art in arten),
              str(sorted(x for x in namen if str(x).startswith("nummern"))))
        check("Nummern zeichnen meldet keinen Fehler",
              "Nummern " not in w.log.toPlainText()[vorher:],
              w.log.toPlainText()[vorher:][:80])

        # --- Grenze: zu viele Marken bleiben aus und sagen es -------------------
        w.NUMMERN["Knoten"] = w.NUMMERN["Knoten"][:2] + (3,) + w.NUMMERN["Knoten"][3:]
        w.act_nodes.setChecked(False)
        w.act_nodes.setChecked(True)
        check("Zu viele Nummern bleiben aus", w._nummern_zuviel.get("Knoten") == n_konstr,
              str(w._nummern_zuviel))
        check("und die Statuszeile sagt, warum",
              "zu viele" in w.statusBar().currentMessage(),
              w.statusBar().currentMessage()[:70])
        w.NUMMERN["Knoten"] = w.NUMMERN["Knoten"][:2] + (3000,) + w.NUMMERN["Knoten"][3:]

        # --- Rechtsklickmenü im Viewport ---------------------------------------
        w.nummern_umlegen("Flächen")
        check("Rechtsklick: eine Art einzeln umlegen",
              not w.act_nummern["Flächen"].isChecked())
        w.nummern_umlegen("Flächen")
        check("und wieder an", w.act_nummern["Flächen"].isChecked())
        w.nummern_aus()
        check("„Alle Nummern aus“ schaltet alle sieben aus",
              not any(a.isChecked() for a in w.act_nummern.values()))
        check("und sagt es in der Statuszeile",
              "Nummern aus" in w.statusBar().currentMessage(),
              w.statusBar().currentMessage()[:60])
        w.nummern_aus()
        check("nochmals: es ist schon alles aus",
              "keine Nummern" in w.statusBar().currentMessage(),
              w.statusBar().currentMessage()[:60])
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Nummerierung je Objektart", False, str(ex)[:70])

    # ---- Alphanumerische Sortierung und die Fuge einer Kontaktbedingung ----
    try:
        from statik3d.gui import design as _dsg
        from statik3d.gui import tabellen as _tab
        from statik3d.model import Material as _MatS, ShellProp as _ShS

        check("Sortierschlüssel liest die Zahl als Zahl",
              sorted(["V10", "V2", "V1", "V21"], key=_dsg.natuerlich)
              == ["V1", "V2", "V10", "V21"],
              str(sorted(["V10", "V2", "V1", "V21"], key=_dsg.natuerlich)))
        check("Namen ohne Zahl bleiben alphabetisch",
              _dsg.namen({"Beton": 1, "Aluminium": 2, "S355": 3, "S235": 4})
              == ["Aluminium", "Beton", "S235", "S355"],
              str(_dsg.namen({"Beton": 1, "Aluminium": 2, "S355": 3, "S235": 4})))
        check("Zahl und Text nebeneinander vergleichen sich ohne Fehler",
              _dsg.namen({"2x": 1, "x2": 2, "12": 3, "3": 4}) is not None)

        # --- Modellbaum: jeder Zweig natürlich sortiert -------------------
        w.new_model()
        ms = w.model
        ms.add_material(_MatS("S355", E=210e9, nu=0.3, rho=7850))
        ms.add_material(_MatS("S235", E=210e9, nu=0.3, rho=7850))
        ms.add_nodes(np.array([[float(i), 0, 0] for i in range(13)]))
        for i in (1, 2, 10, 11, 3):            # bewusst durcheinander angelegt
            ms.add_line(f"L{i}", [i - 1, i])
        for i in (10, 2, 1):
            ms.add_shell_prop(_ShS(f"D{i}", t=0.01 * i))
        w.refresh_all()
        app.processEvents()

        def _kinder(baum, zweigname):
            for i in range(baum.topLevelItemCount()):
                st = [baum.topLevelItem(i)]
                while st:
                    x = st.pop()
                    if x.text(0) == zweigname:
                        return [x.child(k).text(0) for k in range(x.childCount())]
                    st += [x.child(k) for k in range(x.childCount())]
            return []

        check("Modellbaum: Linien natürlich sortiert",
              _kinder(w.baum, "Linien") == ["L1", "L2", "L3", "L10", "L11"],
              str(_kinder(w.baum, "Linien")))
        check("Modellbaum: Knoten numerisch, nicht alphabetisch",
              _kinder(w.baum, "Knoten")[:4] == ["K0", "K1", "K2", "K3"]
              and _kinder(w.baum, "Knoten")[-1] == "K12",
              str(_kinder(w.baum, "Knoten")[-3:]))
        check("Modellbaum: Dicken natürlich sortiert",
              _kinder(w.baum, "Dicken")[:3] == ["D1", "D2", "D10"],
              str(_kinder(w.baum, "Dicken")))
        check("Modellbaum: Werkstoffe alphabetisch",
              _kinder(w.baum, "Werkstoffe") == ["S235", "S355"],
              str(_kinder(w.baum, "Werkstoffe")))

        # --- Aufklapplisten der Masken ------------------------------------
        check("Aufklappliste der Dicken natürlich sortiert",
              [x for x in w.tbl_geoflaeche.modell.spalten
               if x.name == "Dicke"][0].wahlwerte()[:3] == ["D1", "D2", "D10"],
              str([x for x in w.tbl_geoflaeche.modell.spalten
                   if x.name == "Dicke"][0].wahlwerte()))

        # --- Tabellensortierung -------------------------------------------
        sp = [_tab.Spalte("Name", "", "text", 3)]
        mo = _tab.TabellenModell(sp) if hasattr(_tab, "TabellenModell") else None
        if mo is not None:
            mo.zeilen = [["L10"], ["L2"], ["L1"], ["L21"]]
            mo.sortierung = (0, QtCore.Qt.AscendingOrder)
            mo._sortieren()
            check("Modelltabelle: Namensspalte natürlich sortiert",
                  [z[0] for z in mo.zeilen] == ["L1", "L2", "L10", "L21"],
                  str([z[0] for z in mo.zeilen]))
            mo.zeilen = [["12"], ["2"], ["100"]]
            mo._sortieren()
            check("Zahlenspalten bleiben Zahlen",
                  [z[0] for z in mo.zeilen] == ["2", "12", "100"],
                  str([z[0] for z in mo.zeilen]))

        # --- Kontaktbedingung ohne Kontaktflächen ist sichtbar und isolierbar
        w.new_model()
        mc = w.model
        mc.add_material(_MatS("S235", E=210e9, nu=0.3, rho=7850))
        P = np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0],
                      [0, 0, 1], [2, 0, 1], [2, 1, 1], [0, 1, 1.]])
        mc.add_nodes(P)
        kanten = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                  (0, 4), (1, 5), (2, 6), (3, 7)]
        for i, (a, b) in enumerate(kanten):
            mc.add_line(f"K{i + 1}", [a, b])
        seiten = {"Boden": ["K1", "K2", "K3", "K4"], "Deckel": ["K5", "K6", "K7", "K8"],
                  "S1": ["K1", "K10", "K5", "K9"], "S2": ["K2", "K11", "K6", "K10"],
                  "S3": ["K3", "K12", "K7", "K11"], "S4": ["K4", "K9", "K8", "K12"]}
        for nme, ls in seiten.items():
            mc.add_flaeche(nme, ls, material="S235")
        mc.add_koerper("V1", list(seiten), material="S235", teilung=[2, 1, 1])
        n0 = mc.add_node(9, 9, 9); n1 = mc.add_node(9, 9, 10)
        mc.add_line("X1", [n0, n1])            # gehoert nicht zur Fuge
        kb = mc.add_kontaktbedingung("Lagerbock-Unterlegbleche", koerpernamen=["V1"],
                                     gegenflaechen=["Boden"])
        w.refresh_all()
        app.processEvents()
        check("Bezug nennt die Fuge statt „0 Flächen“",
              kb.fuge() == "V1 an 1 Flächen", kb.fuge())
        w._baum_objekt_waehlen("kontaktbedingung", "Lagerbock-Unterlegbleche")
        check("Klick wählt die zugeordneten Flächen - den gelösten Körper nicht mehr (14.09.2026: nur die Fuge leuchtet)",
              w.sel_flaechen == ["Boden"] and not w.sel_koerper,
              f"{w.sel_flaechen} / {w.sel_koerper}")
        gemeldet = []
        w.error = lambda msg: gemeldet.append(str(msg))
        w.nur_auswahl_zeigen()
        check("und lässt sich isolieren statt „Erst etwas auswählen“",
              not gemeldet and "X1" in w.versteckt["linien"],
              str(gemeldet)[:70] or str(sorted(w.versteckt["linien"]))[:70])
        check("… danach ist auch die gewählte Fläche abgewählt",
              not w.sel_flaechen and not w.sel_koerper, f"{w.sel_flaechen} / {w.sel_koerper}")
        w.alles_zeigen()
        w.error = lambda msg: None
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Sortierung und Kontaktfuge", False, str(ex)[:70])

    # ------------------------------------------------------------------
    # Fortschritt: Speichern, Laden und Rechnen zeigen, wie weit sie sind
    # ------------------------------------------------------------------
    try:
        import tempfile as _tf
        from statik3d.model import Material as _Material
        w.new_model()
        m = w.model
        m.add_material(_Material("S355", E=210e9, nu=0.3, rho=7850))
        for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                  (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]:
            m.add_node(*p)
        for t in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6)]:
            m.add_element("tet4", list(t), "S355")
        for k in (0, 1, 2, 3):
            m.fix(k, ["ux", "uy", "uz"])
        m.load_node(4, Fz=-1000.0)
        w.refresh_all()

        # Balken beim Speichern - ohne Abbrechen-Knopf, denn eine halb
        # geschriebene Datei waere kaputt
        pfad_json = os.path.join(_tf.mkdtemp(), "modell.json")
        w.path = pfad_json
        gesehen = []
        echt = w._dateifortschritt

        def merken(anteil, text):
            gesehen.append((anteil, text, w.progress_bar.isVisible(),
                            w.progress_bar.value(), w.progress_bar.maximum()))
            return echt(anteil, text)

        w._dateifortschritt = merken
        w.save_model()
        w._dateifortschritt = echt
        check("Speichern: der Fortschrittsbalken läuft mit",
              len(gesehen) >= 3 and all(g[2] for g in gesehen), f"{len(gesehen)} Meldungen")
        check("Speichern: der Balken ist bestimmt (0 … 1000)",
              all(g[4] == 1000 for g in gesehen), str(gesehen[0][4]) if gesehen else "")
        check("Speichern: die Werte steigen",
              all(b[3] >= a[3] for a, b in zip(gesehen, gesehen[1:])),
              f"{gesehen[0][3]} … {gesehen[-1][3]}" if gesehen else "")
        check("Speichern: kein Abbrechen-Knopf",
              getattr(w, "btn_abbrechen", None) is None or not w.btn_abbrechen.isVisible())
        check("Speichern: hinterher ist der Balken wieder weg",
              not w.progress_bar.isVisible())
        check("die Datei ist geschrieben", os.path.getsize(pfad_json) > 500,
              f"{os.path.getsize(pfad_json)} Bytes")

        # Balken beim Laden
        gesehen = []
        w._dateifortschritt = merken
        w._dateiname_zum_oeffnen = pfad_json
        alt_dialog = QtWidgets.QFileDialog.getOpenFileName
        QtWidgets.QFileDialog.getOpenFileName = staticmethod(
            lambda *a, **k: (pfad_json, "Statik3D (*.json)"))
        try:
            w.open_model()
        finally:
            QtWidgets.QFileDialog.getOpenFileName = alt_dialog
            w._dateifortschritt = echt
        check("Laden: der Fortschrittsbalken läuft mit",
              len(gesehen) >= 3 and all(g[2] for g in gesehen), f"{len(gesehen)} Meldungen")
        check("Laden: das Modell ist da", w.model.nn == 8 and len(w.model.elements) == 5,
              f"{w.model.nn} Knoten, {len(w.model.elements)} Elemente")
        check("Laden: hinterher ist der Balken wieder weg", not w.progress_bar.isVisible())

        # Berechnung: bestimmter Balken mit Prozentzahl
        w._rechnung_t0 = time.time()
        w._rechnung_name = "Berechnung"
        w.progress_bar.setRange(0, 1000)
        w.progress_bar.setVisible(True)
        w._rechnung_fortschritt("Gleichungssystem aufgestellt", 0.2)
        # Lebenszeichen: der Takt dreht ein Zeichen in der Balkenbeschriftung (12.09.2026)
        w._rechnung_takt_start(); w._rechnung_tick(); f1 = w.progress_bar.format(); w._rechnung_tick()
        check("Balken bestimmt, mit Laufzeit und drehendem Zeichen",
              w.progress_bar.maximum() == 1000 and w.progress_bar.isTextVisible()
              and any(z in f1 for z in w.TAKTZEICHEN) and ("s" in f1 or "min" in f1)
              and w.progress_bar.format() != f1 and w._rechnung_takt.isActive(), f1)
        check("Rechnung: der Balken zeigt den Anteil", w.progress_bar.value() == 200,
              str(w.progress_bar.value()))
        text = w.statusBar().currentMessage()
        check("Rechnung: die Statuszeile nennt Schritt, Prozent und Zeit",
              "Gleichungssystem" in text and "20 %" in text and "s)" in text, text[:80])
        w._rechnung_fortschritt("System gelöst", 1.0)
        check("Rechnung: 100 % kommen an", w.progress_bar.value() == 1000)
        w._rechnung_ende()
        check("Rechnungsende hält den Takt an, Beschriftung zurück", not w._rechnung_takt.isActive()
              and w.progress_bar.format() == "%p %")
        w._rechnung_ende()
        check("Rechnung: hinterher ist der Balken wieder weg und unbestimmt",
              not w.progress_bar.isVisible() and w.progress_bar.maximum() == 0)

        # Entartetes Element: klare Meldung statt Absturz mitten im Aufbau -
        # und die Rechnung laeuft trotzdem, denn es traegt ohnehin nichts
        w.model.add_element("tet4", [0, 1, 2, 3], "S355")
        zeilen = w.model.check()
        hinweis = [z for z in zeilen if "entartet" in z]
        check("Modellprüfung meldet das entartete Element vor dem Rechnen",
              len(hinweis) == 1, hinweis[0][:90] if hinweis else "")
        check("als Warnung - die Rechnung wird nicht gesperrt",
              bool(hinweis) and hinweis[0].startswith("WARNUNG")
              and not [z for z in zeilen if z.startswith("FEHLER")],
              hinweis[0][:40] if hinweis else "")
        from statik3d import assemble as _asm
        check("die Assemblierung übergeht es",
              len(_asm.aktive_indizes(w.model)) == len(w.model.elements) - 1,
              f"{len(_asm.aktive_indizes(w.model))} von {len(w.model.elements)}")
        w.new_model()

    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Fortschritt beim Speichern, Laden und Rechnen", False, str(ex)[:70])

    # ------------------------------------------------------------------
    # Abbrechen einer Hintergrundrechnung (Knopf und Esc), Balken bei
    # Import und Bericht, ehrlicher Text vor dem Auswerten grosser Dateien
    # ------------------------------------------------------------------
    try:
        import tempfile as _tf2
        from PySide6 import QtCore as _QtC
        from statik3d import update as _upd2
        from statik3d.gui import dialogs as _dlg
        from tests.test_rfem6 import INF as _INF, make_rf6 as _make_rf6

        def _warten(bedingung, hoechstens=15.0):
            t0 = time.time()
            while not bedingung() and time.time() - t0 < hoechstens:
                app.processEvents()
                time.sleep(0.01)
            app.processEvents()
            return time.time() - t0

        w.load_example("frame"); app.processEvents()
        w._solve_done("all", solver.solve_all(w.model)); app.processEvents()
        an_vorher_ = w.analysis
        check("Vorbereitung: ein Ergebnis liegt vor", an_vorher_ is not None)

        # 1) kuenstlich lange Rechnung: 200 Schritte à 0,02 s = 4 s
        def lang_(p):
            for i in range(200):
                p(f"Schritt {i + 1}", (i + 1) / 200)
                time.sleep(0.02)
            return "fertig"

        ergebnisse_ = []
        zeilen_vorher_ = w.log.blockCount()
        w._run_background(lang_, lambda r: ergebnisse_.append(r), "Probe-Rechnung")
        app.processEvents()
        check("Hintergrundrechnung: Abbrechen-Knopf und Balken sind sichtbar",
              w.btn_abbrechen.isVisible() and w.progress_bar.isVisible() and w._rechnet_gerade)
        check("… zuerst als Streifen (noch kein Anteil gemeldet)", w.progress_bar.maximum() == 0)
        _warten(lambda: w.progress_bar.maximum() == 1000, 3.0)
        check("… nach dem ersten Anteil ein bestimmter Balken mit Prozent",
              w.progress_bar.maximum() == 1000 and 0 < w.progress_bar.value() < 1000
              and w.progress_bar.isTextVisible(), f"Wert {w.progress_bar.value()}")
        alt_inst2_ = _upd2.andere_instanzen
        _upd2.andere_instanzen = lambda: []
        try:
            check("… kein Update während der Rechnung", "Berechnung" in w._update_moeglich(),
                  w._update_moeglich())
            w.btn_abbrechen.click()
            t_klick_ = time.time()
            app.processEvents()
            check("Klick auf Abbrechen: die Statuszeile sagt, dass angehalten wird",
                  "Abbruch angefordert" in w.statusBar().currentMessage(),
                  w.statusBar().currentMessage()[:70])
            dauer_ = _warten(lambda: not w._rechnet_gerade)
            neu_ = w.log.toPlainText().splitlines()[zeilen_vorher_:]
            check("Abbruch: die Rechnung endet beim nächsten Schritt, ohne Ergebnis",
                  dauer_ < 1.0 and not ergebnisse_, f"{dauer_:.2f} s nach dem Klick")
            check("Abbruch: Statuszeile und Protokoll melden „abgebrochen (nach x s)“",
                  "abgebrochen (nach" in w.statusBar().currentMessage()
                  and any(z.startswith("Probe-Rechnung abgebrochen (nach") for z in neu_),
                  w.statusBar().currentMessage()[:80])
            check("Abbruch: keine FEHLER-Zeile im Protokoll",
                  not any(z.startswith("FEHLER") for z in neu_),
                  str([z for z in neu_ if z.startswith("FEHLER")][:1]))
            check("Abbruch: Knöpfe frei, Balken und Abbrechen-Knopf weg, Ergebnis unverändert",
                  w.btn_solve.isEnabled() and not w.progress_bar.isVisible()
                  and not w.btn_abbrechen.isVisible() and not w._rechnet_gerade
                  and w.analysis is an_vorher_ and not w._abbruch)
            check("… und ein Update wäre wieder möglich", w._update_moeglich() == "",
                  w._update_moeglich())
        finally:
            _upd2.andere_instanzen = alt_inst2_

        # 2) Esc bricht ebenso ab - als echter Tastendruck (QTest.keyClick geht
        # wie die Tastatur ueber die Kurzbefehle; ein zugeschickter KeyPress
        # taete das nicht). Esc ist das Kuerzel von „Alles deselektieren“ und
        # verbrauchte den Druck bisher immer, auch waehrend eines Balkens.
        from PySide6 import QtTest as _QtT
        ergebnisse_ = []
        w._run_background(lang_, lambda r: ergebnisse_.append(r), "Probe-Rechnung")
        _warten(lambda: w.progress_bar.maximum() == 1000, 3.0)
        w.plotter.interactor.setFocus()
        _QtT.QTest.keyClick(w.plotter.interactor, _QtC.Qt.Key_Escape)
        dauer_ = _warten(lambda: not w._rechnet_gerade)
        check("Esc (Tastendruck im Bild) bricht die Hintergrundrechnung ab",
              not ergebnisse_ and "abgebrochen (nach" in w.statusBar().currentMessage()
              and dauer_ < 1.0 and w.analysis is an_vorher_, f"{dauer_:.2f} s")
        # Esc ist das Kuerzel der Aktion „Alles deselektieren“ (Ribbon und
        # Glasleiste); die Aktion verzweigt auf Laufendes. Ein Kuerzel loest
        # Qt nur bei aktivem Fenster aus - auf dem Desktop kann ein anderes
        # Fenster (zweiter Prueflauf, der Anwender) die Aktivierung nehmen;
        # darum wird die Aktion hier direkt ausgeloest und der Tastendruck nur
        # bei aktivem Fenster geprueft.
        check("Esc ist das Kürzel von „Alles deselektieren“",
              w.act_auswahl_weg.shortcut().toString() == "Esc",
              w.act_auswahl_weg.shortcut().toString())
        w._fortschritt_beginnen(10, "Probe-Balken")
        w.act_auswahl_weg.trigger()
        app.processEvents()
        esc_balken_ = w._abbruch
        w._fortschritt_ende()
        check("die Esc-Aktion bricht einen Balken im Oberflächen-Thread ab", esc_balken_)
        w.selection = np.arange(min(3, w.model.nn))
        w.act_auswahl_weg.trigger()
        app.processEvents()
        check("ohne Laufendes hebt die Esc-Aktion wie bisher die Auswahl auf",
              len(w.selection) == 0, str(len(w.selection)))
        if w.isActiveWindow():
            w._fortschritt_beginnen(10, "Probe-Balken")
            w.baum.setFocus()
            _QtT.QTest.keyClick(w.baum, _QtC.Qt.Key_Escape)
            app.processEvents()
            esc_balken_ = w._abbruch
            w._fortschritt_ende()
            check("Esc-Tastendruck mit Fokus im Modellbaum bricht den Balken ab (Fenster aktiv)",
                  esc_balken_)
        else:
            print("     Fenster nicht aktiv - Esc-Tastendruck im Modellbaum nicht prüfbar")

        # 3) ohne Abbruch kommt das Ergebnis wie bisher an
        ergebnisse_ = []
        w._run_background(lambda p: (p("halb", 0.5), "ok")[1],
                          lambda r: ergebnisse_.append(r), "Probe kurz")
        _warten(lambda: not w._rechnet_gerade)
        check("ohne Abbruch kommt das Ergebnis an, der Abbrechen-Knopf verschwindet",
              ergebnisse_ == ["ok"] and not w.btn_abbrechen.isVisible()
              and not w.progress_bar.isVisible())

        # 4) Import mit Balken und Phasen
        tmp2_ = _tf2.mkdtemp()
        rf6_ = _make_rf6(os.path.join(tmp2_, "probe.rf6"),
                         nodes=[(0, 0, 0), (2, 0, 0), (4, 0, 0)], lines=[[1, 2, 3]],
                         members=[(1, None, None)],
                         supports=[("Gelenkig", (_INF,) * 6, (0,) * 6, None, [1])])
        gesehen_ = []
        echt_ = w._dateifortschritt

        def merken_(anteil, text):
            gesehen_.append((anteil, text, w.progress_bar.isVisible(), w.progress_bar.value(),
                             getattr(w, "btn_abbrechen", None) is not None
                             and w.btn_abbrechen.isVisible()))
            return echt_(anteil, text)

        w._dateifortschritt = merken_
        alt_open2_ = QtWidgets.QFileDialog.getOpenFileName
        alt_iexec_ = _dlg.ImportDialog.exec
        QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (rf6_, ""))
        _dlg.ImportDialog.exec = lambda self: 1
        try:
            w.import_file()
            app.processEvents()
        finally:
            QtWidgets.QFileDialog.getOpenFileName = alt_open2_
            _dlg.ImportDialog.exec = alt_iexec_
            w._dateifortschritt = echt_
        texte_ = " | ".join(g[1] for g in gesehen_)
        check("Import: der Balken läuft während des Lesens mit und nennt die Phasen",
              len(gesehen_) >= 12 and all(g[2] for g in gesehen_)
              and all(s in texte_ for s in ("Knoten", "Stäbe", "Flächen", "Lasten", "Ansicht")),
              f"{len(gesehen_)} Meldungen: {texte_[:100]}")
        check("Import: die Werte steigen, am Ende über 950",
              all(b[3] >= a[3] for a, b in zip(gesehen_, gesehen_[1:])) and gesehen_[-1][3] >= 950,
              f"{gesehen_[0][3]} … {gesehen_[-1][3]}" if gesehen_ else "-")
        check("Import: kein Abbrechen-Knopf, hinterher ist der Balken weg",
              not any(g[4] for g in gesehen_) and not w.progress_bar.isVisible())
        check("Import: das Modell ist da", w.model.nn == 3 and len(w.model.elements) == 2,
              f"{w.model.nn} Knoten, {len(w.model.elements)} Elemente")

        # 5) Bericht mit Balken je Kapitel
        w.load_example("frame"); app.processEvents()
        w.path = os.path.join(tmp2_, "probe.json")
        gesehen_ = []
        w._dateifortschritt = merken_
        alt_rexec_ = _dlg.ReportDialog.exec
        _dlg.ReportDialog.exec = lambda self: 1
        try:
            w.make_report()
            app.processEvents()
        finally:
            _dlg.ReportDialog.exec = alt_rexec_
            w._dateifortschritt = echt_
            w.path = None
        bericht_ = os.path.join(tmp2_, "probe_bericht.html")
        check("Bericht: der Balken läuft je Kapitel mit, hinterher ist er weg",
              len(gesehen_) >= 18 and all(g[2] for g in gesehen_)
              and any("Kapitel 2 von" in g[1] for g in gesehen_)
              and not w.progress_bar.isVisible() and os.path.exists(bericht_),
              f"{len(gesehen_)} Meldungen")

        # 6) vor dem Auswerten einer grossen Datei: ehrlicher Text, sofort gezeichnet
        zaehler_pe_ = []
        alt_pe_ = QtWidgets.QApplication.processEvents
        QtWidgets.QApplication.processEvents = staticmethod(
            lambda *a: (zaehler_pe_.append(1), alt_pe_(*a))[1])
        try:
            w._fortschritt_beginnen(1000, "Probe", abbrechbar=False)
            w._fortschritt_tick = time.time()       # gerade erst ein Tick
            n_vor_ = len(zaehler_pe_)
            w._dateifortschritt(0.5, "Knoten aufbauen")
            n_normal_ = len(zaehler_pe_) - n_vor_
            w._fortschritt_tick = time.time()
            n_vor_ = len(zaehler_pe_)
            w._dateifortschritt(0.32, "Daten auswerten")
            n_sofort_ = len(zaehler_pe_) - n_vor_
            text_ = w.statusBar().currentMessage()
        finally:
            QtWidgets.QApplication.processEvents = alt_pe_
            w._fortschritt_ende()
        check("Öffnen: vor dem Auswerten steht der ehrliche Text („Minuten“, „antwortet nicht“)",
              "Minuten" in text_ and "antwortet" in text_, text_[:90])
        check("… und die Ereignisschleife lief dafür sofort, sonst erst nach 0,15 s",
              n_sofort_ >= 1 and n_normal_ == 0, f"{n_sofort_} / {n_normal_}")
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Abbrechen, Import- und Berichtsbalken", False, str(ex)[:70])

    # ------------------------------------------------------------------
    # Ribbon Netz: Netzqualität anzeigen
    # ------------------------------------------------------------------
    try:
        from statik3d.model import Material as _Mat
        from statik3d import netzguete as _ng
        w.new_model()
        m = w.model
        m.add_material(_Mat("S355", E=210e9, nu=0.3, rho=7850))
        for p in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                  (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]:
            m.add_node(*p)
        for t in [(0, 1, 3, 4), (1, 2, 3, 6), (1, 4, 5, 6), (3, 4, 6, 7), (1, 3, 4, 6)]:
            m.add_element("tet4", list(t), "S355")
        m.add_element("tet4", [0, 1, 2, 3], "S355")          # eben: Formgüte 0
        w.refresh_all()

        netzbefehle = [b for b in w.ribbon.befehle if b.register == "Netz"]
        check("Ribbon Netz hat den Befehl „Netzqualität…“",
              any("Netzqualität" in b.text for b in netzbefehle),
              str([b.text for b in netzbefehle])[:120])
        check("und er hat einen Hinweistext",
              all(b.hinweis for b in netzbefehle if "Netzqualität" in b.text))

        w.maske_netzguete()
        mk = w.maskenrand.maske
        werte = mk.werte()
        check("Netzqualität: Maske mit Maß, Grenze und Kennwerten",
              all(k in werte for k in ("mass", "grenze", "anzahl", "kennwerte",
                                       "stufen", "splitter", "schlecht")),
              str(sorted(werte)))
        check("Netzqualität: die Kennwerte stehen ohne Knopfdruck da",
              werte["anzahl"] == "6 von 6" and werte["kennwerte"] != "–",
              f"{werte['anzahl']} | {werte['kennwerte']}")
        check("Netzqualität: das entartete Element ist der schlechteste Wert",
              werte["kennwerte"].startswith("0.000") and "Nr. 6 (0.000)" in werte["schlecht"],
              f"{werte['kennwerte']} | {werte['schlecht'][:40]}")
        check("Netzqualität: Splitter werden gezählt",
              werte["splitter"].startswith("1 Splitter"), werte["splitter"])
        check("Netzqualität: die Kennwerte stehen im Protokoll",
              "Netzqualität (Formgüte)" in w.log.toPlainText())

        check("Netzqualität: vor „Anzeigen“ ist nichts eingefärbt", w.netzguete_feld is None)
        mk.angewendet.emit(mk.werte())
        check("Netzqualität: „Anzeigen“ färbt die Ansicht",
              w.netzguete_feld is not None
              and len(w.netzguete_feld["werte"]) == len(m.elements)
              and w.netzguete_feld["mass"] == "formguete",
              str(None if w.netzguete_feld is None else w.netzguete_feld["mass"]))

        mk.setzen("mass", "Seitenverhältnis (1 = alle Kanten gleich)")
        mk.angewendet.emit(mk.werte())
        check("Netzqualität: das Maß lässt sich wechseln",
              w.netzguete_feld["mass"] == "seitenverhaeltnis", w.netzguete_feld["mass"])
        mk.setzen("mass", "Längste Kante [m]")
        mk.angewendet.emit(mk.werte())
        check("Netzqualität: auch die Kantenlänge",
              w.netzguete_feld["mass"] == "kantenlaenge", w.netzguete_feld["mass"])

        knoepfe = {b.text(): b for b in mk.findChildren(QtWidgets.QPushButton)}
        check("Netzqualität: Knöpfe Anzeigen, Schlechte wählen, Aus",
              all(k in knoepfe for k in ("Anzeigen", "Schlechte wählen", "Aus")),
              str(sorted(knoepfe)))
        mk.setzen("mass", "Formgüte (1 = beste Form)")
        knoepfe["Schlechte wählen"].click()
        check("Netzqualität: „Schlechte wählen“ markiert das entartete Element",
              list(w.selection) == [5] and w.auswahlart == "Netz",
              f"{list(w.selection)} / {w.auswahlart}")
        knoepfe["Aus"].click()
        check("Netzqualität: „Aus“ nimmt die Einfärbung weg", w.netzguete_feld is None)

        mk.angewendet.emit(mk.werte())
        w.netz_loeschen_geometrie() if m.flaechen or m.koerper else w.clear_mesh()
        check("Netzqualität: nach dem Löschen des Netzes ist sie weg",
              w.netzguete_feld is None)
        w.new_model()

    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Netzqualität im Ribbon Netz", False, str(ex)[:70])

    # ------------------------------------------------------------------
    # Volumen ohne Rauminhalt halten die Rechnung nicht auf
    # ------------------------------------------------------------------
    try:
        from statik3d.model import Material as _Mat
        w.new_model()
        m = w.model
        m.add_material(_Mat("S235", E=210e9, nu=0.3, rho=7850))
        # Ein flacher Körper (RFEM-Hilfsobjekt) und ein gesunder daneben
        for pkt in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                    (5, 0, 0), (6, 0, 0), (5, 1, 0), (5, 0, 1)]:
            m.add_node(*pkt)
        kanten = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3),
                  (4, 5), (5, 6), (6, 4), (4, 7), (5, 7), (6, 7)]
        for i, (a, b) in enumerate(kanten):
            m.add_line(f"L{i}", [a, b])
        for nr, (nm, ls) in enumerate([("A1", ["L0", "L1", "L2"]), ("A2", ["L0", "L4", "L3"]),
                                       ("A3", ["L1", "L5", "L4"]), ("A4", ["L2", "L3", "L5"]),
                                       ("B1", ["L6", "L7", "L8"]), ("B2", ["L6", "L10", "L9"]),
                                       ("B3", ["L7", "L11", "L10"]), ("B4", ["L8", "L9", "L11"])]):
            m.add_flaeche(nm, ls, material="S235")
        m.add_koerper("V_flach", ["A1", "A2", "A3", "A4"], material="S235")
        m.add_koerper("V_gut", ["B1", "B2", "B3", "B4"], material="S235")
        w.refresh_all()

        from statik3d.diagnose import diagnose as _diag
        d = _diag(m)
        # Der flache Körper wird schon vor dem Vernetzen ausgenommen: die
        # Prüfung ist geometrisch, nicht am Netz. So wird gar nicht erst
        # angeboten, etwas zu vernetzen, was sich nicht vernetzen lässt.
        check("vor dem Vernetzen: nur der gesunde Körper gilt als unvernetzt",
              d["unvernetzte_koerper"] == ["V_gut"], str(d["unvernetzte_koerper"]))
        check("der flache steht von Anfang an unter „ohne Rauminhalt“",
              d["koerper_ohne_volumen"] == ["V_flach"], str(d["koerper_ohne_volumen"]))

        gefragt = []
        alt_fragen = w._fragen
        w._fragen = lambda t, x: (gefragt.append(t), True)[1]
        try:
            ok = w._vor_rechnung_vernetzen()
        finally:
            w._fragen = alt_fragen
        check("Vernetzen wird angeboten und ausgeführt", ok and len(gefragt) == 1, str(gefragt))
        check("der gesunde Körper hat jetzt ein Netz",
              bool(m.koerper["V_gut"].elemente), str(len(m.koerper["V_gut"].elemente)))
        check("der flache bekommt keines", not m.koerper["V_flach"].elemente)

        d = _diag(m)
        check("er zählt danach nicht als „weiterhin ohne Netz“",
              d["unvernetzte_koerper"] == [], str(d["unvernetzte_koerper"]))
        check("sondern als Volumen ohne Rauminhalt",
              d["koerper_ohne_volumen"] == ["V_flach"], str(d["koerper_ohne_volumen"]))

        # Der zweite Durchgang darf gar nicht mehr fragen - sonst laeuft man
        # in eine Schleife aus Nachfrage und FEHLER, wie am Drehlager-Modell
        gefragt, fehler = [], []
        alt_fragen, alt_fehler = w._fragen, w.error
        w._fragen = lambda t, x: (gefragt.append(t), True)[1]
        w.error = lambda t: fehler.append(t)
        try:
            ok = w._vor_rechnung_vernetzen()
        finally:
            w._fragen, w.error = alt_fragen, alt_fehler
        check("zweiter Durchgang: keine Nachfrage mehr", ok and not gefragt, str(gefragt))
        check("und kein FEHLER „weiterhin ohne Netz“", not fehler, str(fehler)[:90])

        # Die Meldung muss die Objekte beim Namen nennen - „das Protokoll sagt,
        # warum“ hilft bei tausend Zeilen niemandem
        m.koerper["V_gut"].elemente = []
        d = _diag(m)
        text = w._ohne_netz_text(d)
        check("die Meldung nennt das Volumen beim Namen",
              text == "1 Volumen (V_gut)", text)
        gefragt = []
        alt_fragen = w._fragen
        w._fragen = lambda t, x: (gefragt.append(x), False)[1]
        try:
            w._vor_rechnung_vernetzen()
        finally:
            w._fragen = alt_fragen
        check("und die Nachfrage auch", bool(gefragt) and "V_gut" in gefragt[0],
              (gefragt[0][:70] if gefragt else ""))
        check("die volle Liste steht im Protokoll",
              "--- Objekte ohne Netz ---" in w.log.toPlainText()
              and "Volumen V_gut: 4 Randflächen" in w.log.toPlainText())

        # Keine Sackgasse: ein Körper, den der Vernetzer nicht vernetzen kann,
        # darf die Rechnung nicht dauerhaft sperren
        from statik3d.model import OHNE_NETZ as _ON
        m.koerper["V_gut"].elemente = []
        m.koerper["V_gut"].kommentar = ""
        gefragt, gewarnt, fehler = [], [], []
        alt_fragen, alt_warn, alt_err = w._fragen, w.warnung, w.error
        w._fragen = lambda t, x: (gefragt.append(x), True)[1]
        w.warnung = lambda t: gewarnt.append(t)
        w.error = lambda t: fehler.append(t)
        alt_vernetzen = w.geometrie_vernetzen
        # Vernetzen, das den Körper ablehnt - wie beim Null-Volumen
        def _abgelehnt():
            m.koerper["V_gut"].kommentar = f"{_ON} Probe"
            m.koerper["V_gut"].elemente = []
        try:
            w.geometrie_vernetzen = lambda: None      # Netz bleibt aus
            ok = w._vor_rechnung_vernetzen()
        finally:
            w.geometrie_vernetzen = alt_vernetzen
            w._fragen, w.warnung, w.error = alt_fragen, alt_warn, alt_err
        check("nach erfolglosem Vernetzen wird trotzdem gerechnet", ok is True, str(ok))
        check("und es kommt eine Warnung statt eines Abbruchs",
              len(gewarnt) == 1 and not fehler,
              (gewarnt[0][:70] if gewarnt else "") + str(fehler)[:40])
        check("die Warnung nennt das Volumen und die Folge",
              bool(gewarnt) and "V_gut" in gewarnt[0] and "Lasten" in gewarnt[0],
              gewarnt[0][:90] if gewarnt else "")

        # Protokoll als Textdatei sichern
        ziel = os.path.join(_tf.mkdtemp(), "protokoll.txt")
        vorher = w.log.toPlainText()          # danach kommt die Bestätigungszeile dazu
        alt_dlg = QtWidgets.QFileDialog.getSaveFileName
        QtWidgets.QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: (ziel, "Text (*.txt)"))
        try:
            w.protokoll_speichern()
        finally:
            QtWidgets.QFileDialog.getSaveFileName = alt_dlg
        check("Extras → Protokoll speichern schreibt die Datei",
              os.path.exists(ziel) and os.path.getsize(ziel) > 50,
              f"{os.path.getsize(ziel) if os.path.exists(ziel) else 0} Bytes")
        check("und sie enthält das Protokoll wortgleich",
              io.open(ziel, encoding="utf-8").read() == vorher)
        check("die Bestätigung nennt Zeilenzahl und Pfad",
              "Protokoll gespeichert" in w.log.toPlainText()
              and os.path.basename(ziel) in w.log.toPlainText())
        check("Ribbon Extras hat den Befehl",
              any("Protokoll speichern" in b.text for b in w.ribbon.befehle),
              str([b.text for b in w.ribbon.befehle if "Protokoll" in b.text]))
        w.new_model()

    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Volumen ohne Rauminhalt halten die Rechnung nicht auf", False, str(ex)[:70])

    # ------------------------------------------------------------------
    # Mehrfachauswahl im Modellbaum; Teilnetz statt ganzem Netz beim Leuchten
    # ------------------------------------------------------------------
    try:
        import numpy as _np
        from PySide6 import QtCore as _Qc, QtGui as _Qg, QtWidgets as _Qw
        from statik3d.gui import viewport as _vp
        w.load_example("frame")
        w.refresh_all()
        app.processEvents()
        baum = w.baum

        def _eintraege(art):
            """Alle Baumeintraege einer Art - der Baum ist beliebig tief."""
            out = []
            stapel = [baum.topLevelItem(i) for i in range(baum.topLevelItemCount())]
            while stapel:
                it = stapel.pop()
                if it is None:
                    continue
                if baum._ist_eintrag(it) and baum._schluessel(it)[0] == art:
                    out.append(it)
                stapel += [it.child(i) for i in range(it.childCount())]
            return out

        check("Modellbaum erlaubt Mehrfachauswahl",
              baum.selectionMode() == _Qw.QAbstractItemView.ExtendedSelection,
              str(baum.selectionMode()))

        knoten = sorted(_eintraege("knoten"), key=lambda it: int(baum._schluessel(it)[1]))
        check("der Baum führt Knoten als einzelne Einträge", len(knoten) >= 3,
              str(len(knoten)))
        if len(knoten) >= 3:
            gemeldet = []
            baum.mehrfach.connect(lambda a, n: gemeldet.append((a, list(n))))
            baum.clearSelection()
            for it in knoten[:3]:
                it.setSelected(True)
            baum.setCurrentItem(knoten[2], 0, _Qc.QItemSelectionModel.NoUpdate)
            app.processEvents()
            art, namen = baum.gewaehlte_eintraege()
            check("gewaehlte_eintraege liefert alle drei Knoten",
                  art == "knoten" and len(namen) == 3, f"{art} {namen}")
            check("und das Signal „mehrfach“ ist gekommen",
                  bool(gemeldet) and gemeldet[-1][0] == "knoten"
                  and len(gemeldet[-1][1]) == 3, str(gemeldet[-1] if gemeldet else None))
            w._baum_mehrfach("knoten", namen)
            app.processEvents()
            check("alle drei sind im Viewport gewählt",
                  sorted(int(x) for x in w.selection) == sorted(int(x) for x in namen),
                  f"{sorted(int(x) for x in w.selection)} / {namen}")
            check("und die Statuszeile nennt die Zahl",
                  "3 Knoten" in w.lbl_sel.text(), w.lbl_sel.text())

        # Die Maske rechts darf dem Baum die Tastatur nicht wegnehmen.
        # Sie tat es: jeder Klick im Baum oeffnete rechts eine Maske, und die
        # rief setFocus() - danach gingen die Pfeiltasten ins Leere, obwohl
        # der Baum sie kann. Geprueft wird der Weg, den ein Klick nimmt.
        for art_, name_ in (("knoten", "0"), ("werkstoff", next(iter(w.model.materials), "")),
                            ("lastfall", next(iter(w.model.load_cases), ""))):
            if not name_:
                continue
            baum.setFocus(_Qc.Qt.MouseFocusReason)
            app.processEvents()
            w._baum_geklickt(art_, name_)
            app.processEvents()
            check(f"nach dem Klick auf {art_} bleibt die Tastatur im Baum",
                  w.focusWidget() is baum, type(w.focusWidget()).__name__)

        # Pfeiltaste runter bewegt und meldet, Umschalt+Pfeil nimmt dazu
        baum.setFocus(_Qc.Qt.MouseFocusReason)
        baum.clearSelection()
        baum.setCurrentItem(knoten[0])
        app.processEvents()
        getastet = []
        baum.angeklickt.connect(lambda a, n: getastet.append(("einzeln", a, n)))
        baum.mehrfach.connect(lambda a, n: getastet.append(("mehrfach", a, list(n))))
        app.sendEvent(baum, _Qg.QKeyEvent(_Qc.QEvent.KeyPress, _Qc.Qt.Key_Down,
                                          _Qc.Qt.NoModifier))
        app.processEvents()
        check("Pfeil runter schaltet auf den naechsten Eintrag und meldet ihn",
              baum._schluessel(baum.currentItem()) == ("knoten", "1")
              and getastet and getastet[-1] == ("einzeln", "knoten", "1"),
              str(getastet[-1] if getastet else None))
        app.sendEvent(baum, _Qg.QKeyEvent(_Qc.QEvent.KeyPress, _Qc.Qt.Key_Down,
                                          _Qc.Qt.ShiftModifier))
        app.processEvents()
        check("Umschalt+Pfeil nimmt den naechsten dazu",
              baum.gewaehlte_eintraege() == ("knoten", ["1", "2"])
              and getastet[-1] == ("mehrfach", "knoten", ["1", "2"]),
              f"{baum.gewaehlte_eintraege()} / {getastet[-1]}")
        # Strg+Klick nimmt einen einzelnen dazu, ohne die Strecke zu ziehen
        baum.clearSelection()
        knoten[0].setSelected(True)
        baum.setCurrentItem(knoten[0], 0, _Qc.QItemSelectionModel.NoUpdate)
        knoten[3].setSelected(True) if len(knoten) > 3 else None
        app.processEvents()
        if len(knoten) > 3:
            art_, namen_ = baum.gewaehlte_eintraege()
            check("Strg+Auswahl haelt zwei nicht benachbarte Eintraege",
                  art_ == "knoten" and namen_ == ["0", "3"], f"{art_} {namen_}")

        # Pfeiltasten: ein einzelner Eintrag muss sich auch melden
        baum.clearSelection()
        gemeldet_einzeln = []
        baum.angeklickt.connect(lambda a, n: gemeldet_einzeln.append((a, n)))
        baum.setCurrentItem(knoten[0])
        app.processEvents()
        check("ein einzeln gewählter Eintrag meldet sich (Pfeiltaste)",
              gemeldet_einzeln and gemeldet_einzeln[-1] == ("knoten", "0"),
              str(gemeldet_einzeln[-1] if gemeldet_einzeln else None))
        baum.setCurrentItem(knoten[1])
        app.processEvents()
        check("und der nächste ebenso - die Auswahl zieht mit",
              len(gemeldet_einzeln) >= 2 and gemeldet_einzeln[-1] == ("knoten", "1"),
              str(gemeldet_einzeln[-1] if gemeldet_einzeln else None))

        # Pos1 und Ende
        alle = baum._alle_eintraege()
        baum.keyPressEvent(_Qg.QKeyEvent(_Qc.QEvent.KeyPress, _Qc.Qt.Key_End,
                                         _Qc.Qt.NoModifier))
        app.processEvents()
        check("Ende springt auf den letzten Eintrag",
              baum.currentItem() is alle[-1],
              str(baum._schluessel(baum.currentItem())))
        baum.keyPressEvent(_Qg.QKeyEvent(_Qc.QEvent.KeyPress, _Qc.Qt.Key_Home,
                                         _Qc.Qt.NoModifier))
        app.processEvents()
        check("Pos1 auf den ersten", baum.currentItem() is alle[0],
              str(baum._schluessel(baum.currentItem())))

        # Eingabetaste öffnet den Eintrag zum Bearbeiten. Geprüft wird nur das
        # Signal: der Empfänger im Fenster öffnet einen modalen Dialog, und der
        # bliebe im Test stehen.
        bearbeitet = []
        baum.bearbeiten.disconnect(w._baum_bearbeiten)
        baum.bearbeiten.connect(lambda a, n: bearbeitet.append((a, n)))
        try:
            baum.setCurrentItem(knoten[2])
            baum.keyPressEvent(_Qg.QKeyEvent(_Qc.QEvent.KeyPress, _Qc.Qt.Key_Return,
                                             _Qc.Qt.NoModifier))
            app.processEvents()
        finally:
            baum.bearbeiten.connect(w._baum_bearbeiten)
        check("die Eingabetaste öffnet den Eintrag zum Bearbeiten",
              bearbeitet and bearbeitet[-1][0] == "knoten",
              str(bearbeitet[-1] if bearbeitet else None))

        # eintrag_waehlen: aus der Ansicht heraus, ohne Rückkopplung
        vorher = len(gemeldet_einzeln)
        got = baum.eintrag_waehlen("knoten", "1")
        app.processEvents()
        check("eintrag_waehlen findet den Eintrag und wählt ihn",
              got and baum._schluessel(baum.currentItem()) == ("knoten", "1"),
              f"{got}, {baum._schluessel(baum.currentItem())}")
        check("und meldet dabei nichts zurück (keine Rückkopplung)",
              len(gemeldet_einzeln) == vorher,
              f"{vorher} -> {len(gemeldet_einzeln)}")
        # hasFocus() setzt ein aktives Fenster voraus - unter xvfb ist keines
        # aktiv. Massgebend ist, welches Widget im Fenster den Fokus haelt.
        check("der Fokus liegt danach im Baum", w.focusWidget() is baum,
              type(w.focusWidget()).__name__)
        check("einen Eintrag, den es nicht gibt, meldet sie als False",
              baum.eintrag_waehlen("knoten", "999999") is False)

        # Flaechen und Volumen genauso - zwei Tetraeder aus Geometrie
        from statik3d.model import Material as _Mat2
        w.new_model()
        mm = w.model
        mm.add_material(_Mat2("S235", E=210e9, nu=0.3, rho=7850))
        for pkt in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1),
                    (5, 0, 0), (6, 0, 0), (5, 1, 0), (5, 0, 1)]:
            mm.add_node(*pkt)
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3),
                                    (4, 5), (5, 6), (6, 4), (4, 7), (5, 7), (6, 7)]):
            mm.add_line(f"L{i}", [a, b])
        for nm, ls in [("A1", ["L0", "L1", "L2"]), ("A2", ["L0", "L4", "L3"]),
                       ("A3", ["L1", "L5", "L4"]), ("A4", ["L2", "L3", "L5"]),
                       ("B1", ["L6", "L7", "L8"]), ("B2", ["L6", "L10", "L9"]),
                       ("B3", ["L7", "L11", "L10"]), ("B4", ["L8", "L9", "L11"])]:
            mm.add_flaeche(nm, ls, material="S235")
        mm.add_koerper("VA", ["A1", "A2", "A3", "A4"], material="S235")
        mm.add_koerper("VB", ["B1", "B2", "B3", "B4"], material="S235")
        w.refresh_all()
        app.processEvents()
        vol = _eintraege("geokoerper_einzeln")
        namen = sorted(baum._schluessel(it)[1] for it in vol)[:2]
        check("der Baum führt beide Volumen einzeln", len(vol) == 2, str(len(vol)))
        w._baum_mehrfach("geokoerper_einzeln", namen)
        check("zwei Volumen zusammen gewählt",
              sorted(w.sel_koerper) == sorted(namen), str(w.sel_koerper))
        check("und die Auswahlart folgt", w.auswahlart == "Volumen", w.auswahlart)
        fl = _eintraege("geoflaeche")
        namen = sorted(baum._schluessel(it)[1] for it in fl)[:3]
        check("der Baum führt alle acht Flächen einzeln", len(fl) == 8, str(len(fl)))
        w._baum_mehrfach("geoflaeche", namen)
        check("drei Flächen zusammen gewählt",
              sorted(w.sel_flaechen) == sorted(namen), str(w.sel_flaechen))
        # Löschen mehrerer auf einmal: eine Rückfrage, ein Bild, ein Bericht.
        # Flächen, die ein Volumen beranden, gehen nicht - und sagen warum.
        meldungen = []
        alt_best2, alt_info2 = w._bestaetigen, w.info
        w._bestaetigen = lambda *a, **k: True
        w.info = lambda t: meldungen.append(t)
        try:
            w._baum_viele_loeschen("geoflaeche", ["A1", "A2"])
        finally:
            w._bestaetigen, w.info = alt_best2, alt_info2
        check("berandende Flächen bleiben stehen und nennen den Grund",
              "A1" in mm.flaechen and "A2" in mm.flaechen and meldungen
              and "0 von 2" in meldungen[-1] and "berandet" in meldungen[-1],
              str(meldungen[-1] if meldungen else None)[:100])
        meldungen = []
        alt_best2, alt_info2 = w._bestaetigen, w.info
        w._bestaetigen = lambda *a, **k: True
        w.info = lambda t: meldungen.append(t)
        try:
            w._baum_viele_loeschen("geokoerper_einzeln", ["VA", "VB"])
        finally:
            w._bestaetigen, w.info = alt_best2, alt_info2
        check("beide Volumen auf einmal gelöscht - eine Rückfrage, eine Meldung",
              not mm.koerper and len(meldungen) == 1 and "2 von 2" in meldungen[-1],
              str(meldungen[-1] if meldungen else None)[:80])

        # Sammelbearbeitung und Sammellöschen
        w.load_example("frame")
        w.refresh_all()
        knoten = sorted(_eintraege("knoten"), key=lambda it: int(baum._schluessel(it)[1]))
        namen = [baum._schluessel(it)[1] for it in knoten[:2]]
        w._baum_viele_bearbeiten("knoten", namen)
        app.processEvents()
        offen = w.maskenrand.maske
        check("Sammelmaske für mehrere Knoten öffnet",
              offen is not None and "2 Knoten" in str(getattr(offen, "titel", "")),
              str(getattr(offen, "titel", None)))

        n_vorher = w.model.nn
        frei = [i for i in range(w.model.nn)
                if not any(i in (int(x) for x in e.nodes) for e in w.model.elements)]
        w.model.add_node(99.0, 99.0, 99.0)
        w.model.add_node(99.0, 99.0, 98.0)
        w.refresh_all()
        neu = [str(n_vorher), str(n_vorher + 1)]
        alt_best = w._bestaetigen
        w._bestaetigen = lambda *a, **k: True
        try:
            w._baum_viele_loeschen("knoten", neu)
        finally:
            w._bestaetigen = alt_best
        check("zwei Knoten auf einmal gelöscht", w.model.nn == n_vorher,
              f"{w.model.nn} / {n_vorher}")

        # Teilnetz: dieselben Zellen wie das ganze Gitter, nur ohne den Umweg
        m = w.model
        elemente = list(range(min(5, len(m.elements))))
        g_alt = _vp.to_grid(m).extract_cells(_np.asarray(elemente, int))
        g_neu = _vp.teilnetz(m, elemente)
        check("Teilnetz hat dieselben Zellen wie das ganze Gitter",
              g_alt.n_cells == g_neu.n_cells == len(elemente),
              f"{g_alt.n_cells} / {g_neu.n_cells}")
        c1 = _np.asarray(g_alt.cell_centers().points)
        c2 = _np.asarray(g_neu.cell_centers().points)
        o1, o2 = _np.lexsort(c1.T), _np.lexsort(c2.T)
        check("und dieselben Zellmitten", _np.allclose(c1[o1], c2[o2]),
              f"max {float(_np.abs(c1[o1] - c2[o2]).max()):.2e}")
        check("die Punkte bleiben alle Modellknoten (Knotenwerte passen weiter)",
              g_neu.n_points == m.nn, f"{g_neu.n_points} / {m.nn}")
        check("Elementnummern stehen am Teilnetz",
              sorted(int(x) for x in g_neu.cell_data["elem"]) == elemente,
              str(list(g_neu.cell_data["elem"])[:5]))
        check("ein leeres Teilnetz ist leer, kein Fehler",
              _vp.teilnetz(m, []).n_cells == 0)
        check("unbekannte Elementnummern werden übergangen",
              _vp.teilnetz(m, [-1, 10 ** 9]).n_cells == 0)

        # Bohrungen müssen im Bild ein Loch sein, keine Scheibe.
        # Geschlossener Wert: Platte 1 x 1 m mit Loch 0,4 x 0,4 m -> 0,84 m².
        import pyvista as _pv
        w.new_model()
        ml = w.model
        ml.add_material(_Mat2("S235", E=210e9, nu=0.3, rho=7850))
        for pkt in [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
                    (0.3, 0.3, 0), (0.7, 0.3, 0), (0.7, 0.7, 0), (0.3, 0.7, 0)]:
            ml.add_node(*pkt)
        for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            ml.add_line(f"L{i}", [a, b])
        for i, (a, b) in enumerate([(4, 5), (5, 6), (6, 7), (7, 4)]):
            ml.add_line(f"O{i}", [a, b])
        fl = ml.add_flaeche("F1", ["L0", "L1", "L2", "L3"], material="S235")
        fl.oeffnungen = [["O0", "O1", "O2", "O3"]]
        soll = fl.inhalt(ml)
        ringl = fl.randpunkte(ml)
        loecher = fl.oeffnungspunkte(ml)
        check("die Öffnung wird als Innenrand gelesen",
              len(loecher) == 1 and len(loecher[0]) == 4, str([len(x) for x in loecher]))

        def _flaeche(P, Z):
            return float(_pv.PolyData(_np.asarray(P, float),
                                      faces=_np.asarray(Z, int)).triangulate().area)

        P0, Z0 = _vp.flaechen_dreiecke(ringl, None, None)
        P1, Z1 = _vp.flaechen_dreiecke(ringl, None, loecher)
        check("ohne Innenränder füllt VTK das Polygon (eine Zelle)",
              len(Z0) == 5 and abs(_flaeche(P0, Z0) - 1.0) < 1e-9,
              f"{_flaeche(P0, Z0):.6f} m²")
        check("mit Innenrändern bleibt das Loch offen - Fläche = Sollwert",
              abs(_flaeche(P1, Z1) - soll) < 1e-9,
              f"{_flaeche(P1, Z1):.6f} / {soll:.6f} m²")
        w.refresh_all()
        app.processEvents()
        netze = _vp.geometrie_netze(ml)
        check("und die Ansicht baut die Fläche mit dem Loch",
              netze[0] is not None
              and abs(float(netze[0].triangulate().area) - soll) < 1e-9,
              f"{float(netze[0].triangulate().area):.6f} m²" if netze[0] is not None else "-")

        w.load_example("frame")
        w.refresh_all()
        m = w.model
        # Der Zeigerpfad darf nicht bei jeder Mausruhe alles durchgehen
        w._stabstrecken()
        idx = w._stabelemente()
        von_hand = [i for i, e in enumerate(m.elements)
                    if e.typ in _vp.TYPEN_STAEBE and len(e.nodes) >= 2]
        check("gepufferte Stabelemente sind dieselben wie die gesuchten",
              idx == von_hand, f"{len(idx)} / {len(von_hand)}")
        A, B = w._stabstrecken()
        check("und passen zu den Strecken", len(A) == len(idx), f"{len(A)} / {len(idx)}")
        w.load_example("hall")
        w.refresh_all()
        A2, B2, namen2 = w._stabstrecken_benannt()
        soll = sum(len(mem.elements or []) for mem in w.model.members.values())
        check("benannte Stabstrecken: je Stabelement ein Eintrag mit seinem Stab",
              len(A2) == len(B2) == len(namen2) == soll and soll > 0,
              f"{len(namen2)} / {soll}")
        check("und derselbe Aufruf gibt dasselbe Feld zurück (gepuffert)",
              w._stabstrecken_benannt()[2] is namen2)
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Mehrfachauswahl im Modellbaum", False, str(ex)[:70])

    # ---- 15.09.2026: Lot / Projektion, Fang „Lot", Geometrieart, Flaechen verschneiden ----
    try:
        from statik3d import ks as ksm
        fehler_ = []
        alt_error = w.error
        w.error = lambda msg: fehler_.append(str(msg))
        w.new_model(); app.processEvents()
        m_ = w.model
        m_.add_nodes(np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0], [0.5, 0.5, 1.0], [1.5, 0.25, 2.0]]))
        for i_, (a_, b_) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0)]):
            m_.add_line(f"L{i_ + 1}", [a_, b_])
        m_.add_flaeche("F1", ["L1", "L2", "L3", "L4"], dicke=list(m_.shells)[0], material=list(m_.materials)[0])
        w.refresh_all(); app.processEvents()
        check("Fangart „Lot“ gibt es (Umschalt+F8), in Ribbon und Statuszeile",
              "lot" in ksm.FANGARTEN and "lot" in w.act_fangart
              and w.act_fangart["lot"].shortcut().toString() == "Shift+F8" and ksm.FANG_TEXT["lot"] == "Lot",
              str(list(w.act_fangart)))
        w.fang_umschalten(True); w.fang_arten = ["lot"]
        w.blickrichtung("+z"); w.zoom_alles(); app.processEvents()
        w.maske_linie(); app.processEvents()
        w.maskenrand.maske.knoten_angeklickt(4); app.processEvents()
        xy_, _s = w._projizieren(np.array([[0.5, 0.0, 0.0]]))
        w.plotter.iren.interactor.SetEventPosition(int(round(xy_[0][0])), int(round(xy_[0][1])))
        p_, art_, _i = w._fangpunkt()
        check("Fang „Lot“: vom zuletzt gewählten Knoten (0,5; 0,5; 1) fällt das Lot auf L1 bei (0,5; 0; 0)",
              art_ == "lot" and p_ is not None and abs(p_[0] - 0.5) < 1e-6 and abs(p_[1]) < 1e-9 and abs(p_[2]) < 1e-9,
              f"{art_} {p_}")
        w.maskenrand.schliessen(); app.processEvents()
        p_, art_, _i = w._fangpunkt()
        check("… ohne Bezugspunkt (keine Maske offen) fängt „Lot“ nichts", art_ == "", f"{art_} {p_}")
        w.fang_arten = list(ksm.FANGARTEN)
        w._auswahl_leeren(); w.selection = np.array([4, 5], int)
        nn_ = m_.nn
        w.maske_lot(); app.processEvents()
        mk = w.maskenrand.maske
        check("Maske „Lot / Projektion“: Ziel, Objekt, Ergebnis, Lotlinie; zwei Knoten als Quelle",
              mk is not None and mk.titel.startswith("Lot")
              and all(k in mk.werte() for k in ("ziel", "objekt", "ergebnis", "lotlinie"))
              and "2 Knoten" in mk.werte()["quelle"], str(mk.werte() if mk else None))
        mk.setzen("ziel", "Arbeitsebene"); mk.setzen("lotlinie", True); mk.anwenden(); app.processEvents()
        check("Lot auf die Arbeitsebene (xy): zwei neue Knoten bei z = 0 unter den Quellknoten, zwei Lotlinien",
              m_.nn == nn_ + 2 and np.allclose(m_.nodes[nn_:, 2], 0)
              and np.allclose(m_.nodes[nn_:, :2], m_.nodes[[4, 5], :2])
              and sum(1 for ln in m_.lines.values() if sorted(int(x) for x in ln.nodes) in ([4, nn_], [5, nn_ + 1])) == 2,
              f"{m_.nn}, {sorted(m_.lines)}")
        w.selection = np.array([5], int)
        w.maske_lot(); app.processEvents()
        mk = w.maskenrand.maske
        w.activateWindow(); mk._felder["objekt"].setFocus(); app.processEvents()
        check("Klick ins Feld Objekt: die Maus sammelt Flächen, das Feld ist scharf",
              mk.objekt_modus == "flaeche" and "ff8800" in mk._felder["objekt"].styleSheet().lower(),
              repr(mk.objekt_modus))
        mk.objekt_angeklickt("flaeche", "F1"); app.processEvents()
        mk.setzen("ziel", "Ebene einer Fläche"); mk.setzen("ergebnis", "Knoten dorthin verschieben (projizieren)")
        mk.anwenden(); app.processEvents()
        check("Projektion auf die Ebene von F1: der Knoten (1,5; 0,25; 2) steht jetzt bei z = 0",
              mk.werte()["objekt"] == "F1" and abs(m_.nodes[5][2]) < 1e-9 and abs(m_.nodes[5][0] - 1.5) < 1e-9
              and m_.nn == nn_ + 2, str(m_.nodes[5]))
        m_.nodes[5] = [3.0, 0.5, 1.0]
        w.selection = np.array([5], int)
        w.maske_lot(); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("ziel", "Fläche (nächster Punkt)"); mk.setzen("objekt", "F1"); mk.anwenden(); app.processEvents()
        check("nächster Punkt der Fläche zu (3; 0,5; 1): neuer Knoten am Rand (2; 0,5; 0)",
              m_.nn == nn_ + 3 and np.allclose(m_.nodes[-1], [2.0, 0.5, 0.0]), str(m_.nodes[-1]))
        w.selection = np.array([5], int)
        w.maske_lot(); app.processEvents()
        mk = w.maskenrand.maske
        mk.setzen("ziel", "Linie (nächster Punkt)"); mk.setzen("objekt", "L2"); mk.anwenden(); app.processEvents()
        check("Lot auf die Linie L2 (x = 2): neuer Knoten (2; 0,5; 0)",
              m_.nn == nn_ + 4 and np.allclose(m_.nodes[-1], [2.0, 0.5, 0.0]), str(m_.nodes[-1]))
        w._auswahl_leeren(); w.maske_lot(); app.processEvents()
        check("ohne gewählte Knoten: Hinweis statt Maske", fehler_ and "Knoten" in fehler_[-1], str(fehler_[-1:]))
        w.flaeche_bearbeiten("F1"); app.processEvents()
        mk = w.maskenrand.maske
        check("Flächenmaske: Geometrieart eben / Regelfläche", "typ" in mk.werte() and mk.werte()["typ"] == "eben",
              str(mk.werte().get("typ")))
        # ohne „gleich vernetzen": sonst laegen Netzknoten auf der Schnittlinie unten
        mk.setzen("typ", "Regelfläche (Viereck, gewölbt)"); mk.setzen("vernetzen", False)
        mk.anwenden(); app.processEvents()
        check("Übernehmen setzt die Geometrieart", m_.flaechen["F1"].typ == "regelflaeche", m_.flaechen["F1"].typ)
        mk = w.maskenrand.maske
        mk.setzen("typ", "eben"); mk.setzen("vernetzen", False); mk.anwenden(); app.processEvents()
        check("… und zurück, ohne Netz", m_.flaechen["F1"].typ == "eben" and not m_.flaechen["F1"].elemente,
              f"{m_.flaechen['F1'].typ}, {len(m_.flaechen['F1'].elemente)} Elemente")
        b0_ = m_.nn
        m_.add_nodes(np.array([[1, -1, -1], [1, 2, -1], [1, 2, 1], [1, -1, 1.]]))
        for i_ in range(4):
            m_.add_line(f"Q{i_}", [b0_ + i_, b0_ + (i_ + 1) % 4])
        m_.add_flaeche("F2", ["Q0", "Q1", "Q2", "Q3"], material=list(m_.materials)[0])
        w.refresh_all(); app.processEvents()
        w._auswahl_leeren(); w.sel_flaechen = ["F1", "F2"]
        n_l, nn2_ = len(m_.lines), m_.nn
        alt_lines = set(m_.lines)
        w.flaechen_verschneiden(); app.processEvents()
        neu_l = [n for n in m_.lines if n not in alt_lines]
        kn_ = sorted(m_.nodes[[int(x) for x in m_.lines[neu_l[0]].nodes]].tolist()) if neu_l else []
        check("„Flächen verschneiden“: eine Schnittlinie von (1,0,0) nach (1,1,0) auf zwei neuen Knoten",
              len(neu_l) == 1 and m_.nn == nn2_ + 2 and np.allclose(kn_, [[1, 0, 0], [1, 1, 0]]),
              f"{neu_l} {kn_} {m_.nn - nn2_} Knoten")
        check("… die Schnittlinie ist danach gewählt, die Flächen nicht mehr",
              w.sel_linien == neu_l and not w.sel_flaechen, str(w.sel_linien))
        w.sel_flaechen = ["F1"]; w.flaechen_verschneiden(); app.processEvents()
        check("mit einer Fläche: Hinweis", "zwei" in fehler_[-1].lower(), str(fehler_[-1:]))
        w.error = alt_error
        w.new_model()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Lot, Fang Lot, Geometrieart, Verschneiden", False, str(ex)[:70])

    try:
        # ---- Abbruch der Kontakt-Iteration: letzte Verformung mit Zeiger (16.09.2026) ----
        from statik3d.examples_lib import block_friction_example as bfe_
        from types import SimpleNamespace as SN_
        m_ = bfe_()
        for l_ in m_.case().nodal_loads:
            l_.F[2] = abs(l_.F[2])                 # der Block wird nach oben gezogen
        w.model = m_; w.analysis = None; w.results = None; w.refresh_all(); app.processEvents()
        alt_hf = solver.StaticSystem.hilfsfesselung
        alt_halt = solver._freie_teile_halten
        solver.StaticSystem.hilfsfesselung = lambda self: False
        solver._freie_teile_halten = lambda *a, **k: False      # sonst haelt der Block an drei Punkten
        try:
            ex_ = None
            try:
                solver.solve_static(m_)
            except RuntimeError as e_:
                ex_ = e_
        finally:
            solver.StaticSystem.hilfsfesselung = alt_hf
            solver._freie_teile_halten = alt_halt
        check("Abbruch: die Ausnahme trägt das Teilergebnis der letzten Iteration",
              ex_ is not None and getattr(ex_, "teilergebnis", None) is not None
              and getattr(ex_, "iteration", 0) >= 1, str(ex_)[:80])
        w.worker = SN_(ausnahme=ex_, abbruch_angefordert=False, isRunning=lambda: False)
        w._bg_failed(str(ex_), "Traceback (Probe)"); app.processEvents()
        r_ = w.current_result()
        check("… Ergebnis „Abbruch“ in der Auswahl, Verformung der letzten Iteration sichtbar",
              r_ is not None and "Abbruch" in w.cb_result.currentText() and bool(r_.info.get("abbruch"))
              and r_.u is not None and float(np.abs(r_.u).max()) > 0, w.cb_result.currentText())
        s0_ = r_.singular[0] if r_ is not None and r_.singular else None
        check("… Zeiger: freie Bewegung „hebt ab“ nach oben mit dem Großteil der 90 kN, Pfeil eingestellt",
              s0_ is not None and s0_.art == "hebt ab" and s0_.t[2] > 0.5 and s0_.kraft > 60000
              and getattr(w, "_bewegung_index", None) == 0 and "Block/Platte" in " ".join(s0_.fugen),
              str(s0_ and (s0_.text, s0_.kraft)))
        check("… Protokoll nennt den Abbruch und die Zusammenfassung beginnt mit ABBRUCH",
              "ABBRUCH" in w.log.toPlainText() and r_.summary().startswith("ABBRUCH"))
        w.bewegung_aus(); w.worker = None
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Abbruch", False, str(ex)[:70])

    try:
        # ---- Unterlagen: Dateien, Ansichten, Skizzen (16.09.2026, analog InfoCAD) ----
        import base64 as b64_
        import tempfile as tmp_
        from PySide6 import QtGui as QtGui_
        namen_ = [w.ribbon.tabs.tabText(i) for i in range(w.ribbon.tabs.count())]
        check("Ribbon: Register Unterlagen zwischen Start und Geometrie",
              "Unterlagen" in namen_ and namen_.index("Unterlagen") == namen_.index("Start") + 1
              and namen_.index("Geometrie") == namen_.index("Unterlagen") + 1, str(namen_[:5]))
        w.new_model(); app.processEvents()
        m_ = w.model
        ordner_ = tmp_.mkdtemp(prefix="statik3d_unterlagen_")
        pfad_png = os.path.join(ordner_, "foto.png")
        img_ = QtGui_.QImage(40, 20, QtGui_.QImage.Format_RGB32)
        img_.fill(QtGui_.QColor("#4060a0"))
        img_.save(pfad_png)
        pfad_pdf = os.path.join(ordner_, "zeichnung.pdf")
        with open(pfad_pdf, "wb") as fh_:
            fh_.write(b"%PDF-1.4 probe")
        w.unterlage_datei_einfuegen(pfad_png); w.unterlage_datei_einfuegen(pfad_pdf); app.processEvents()
        check("Datei einfügen: Bild als Bild, PDF als Datei, beide mit Inhalt im Modell",
              set(m_.unterlagen) == {"foto.png", "zeichnung.pdf"} and m_.unterlagen["foto.png"].art == "bild"
              and m_.unterlagen["zeichnung.pdf"].art == "datei" and m_.unterlagen["zeichnung.pdf"].typ == "pdf"
              and b64_.b64decode(m_.unterlagen["zeichnung.pdf"].daten).startswith(b"%PDF"), str(list(m_.unterlagen)))
        w.unterlage_ansicht(); app.processEvents()
        bilder_ = [u for u in m_.unterlagen.values() if u.name.startswith("Ansicht")]
        check("Ansicht übernehmen: ein PNG der Ansicht liegt bei den Unterlagen",
              len(bilder_) == 1 and bilder_[0].art == "bild"
              and b64_.b64decode(bilder_[0].daten)[:8] == b"\x89PNG\r\n\x1a\n")
        f_ = w.unterlage_skizze_neu(name="Blech"); app.processEvents()
        check("Neue Skizze: Zeichenfenster offen, Blatt A4 quer", f_ is not None and f_.isVisible() and f_.skizze["breite"] == 297)
        f_.werkzeug_setzen("linie"); f_._klick(10, 10); f_._klick(110, 10); f_.abbrechen()
        f_.werkzeug_setzen("bemassung"); f_._klick(10, 10); f_._klick(110, 10); f_._klick(60, 0)
        f_.werkzeug_setzen("kreis"); f_._klick(150, 60); f_._klick(170, 60)
        f_.werkzeug_setzen("bogen"); f_._klick(200, 100); f_._klick(240, 100); f_._klick(220, 80)
        f_.sp_massstab.setValue(10.0); f_.cb_einheit.setCurrentText("cm")
        arten_ = [e["art"] for e in f_.skizze["elemente"]]
        check("Werkzeuge: Linie, Maß (Maßlinie oberhalb), Kreis und Bogen stehen auf dem Blatt",
              arten_ == ["linie", "bemassung", "kreis", "bogen"] and f_.skizze["elemente"][1]["abstand"] > 0
              and abs(f_.skizze["elemente"][2]["r"] - 20) < 1e-9, str(arten_))
        f_.werkzeug_setzen("auswahl"); f_._klick(150, 40)
        getroffen_ = f_.blatt.hervor
        f_.loeschen()
        check("Auswählen trifft den Kreis, Löschen nimmt ihn weg",
              getroffen_ == 2 and len(f_.skizze["elemente"]) == 3, f"{getroffen_} {len(f_.skizze['elemente'])}")
        f_.rueckgaengig()
        check("Rückgängig holt den Kreis zurück", len(f_.skizze["elemente"]) == 4)
        f_.ed_beschriftung.setText("Blech mit Bohrung")
        f_.ok(); app.processEvents()
        u_ = m_.unterlagen.get("Blech")
        check("OK übernimmt die Skizze ins Modell: 4 Elemente, Maßstab 10, Einheit cm, Beschriftung",
              u_ is not None and u_.art == "skizze" and len(u_.skizze["elemente"]) == 4 and u_.skizze["massstab"] == 10
              and u_.skizze["einheit"] == "cm" and u_.beschriftung == "Blech mit Bohrung", str(u_ and u_.bezug()))
        w.unterlage_in_bericht("Blech"); w.unterlage_in_bericht("zeichnung.pdf"); app.processEvents()
        eintr_ = [e for e in m_.bericht if getattr(e, "art", "") == "unterlage"]
        check("In den Bericht: zwei Einträge der Art Unterlage",
              len(eintr_) == 2 and {e.datei for e in eintr_} == {"Blech", "zeichnung.pdf"})
        from statik3d.report.html import Report as Rep_
        bl_ = Rep_(m_)._eintrag_bloecke(eintr_[0], 1)
        fig_ = [b for b in bl_ if b[0] == "figure"]
        check("Bericht zeichnet die Skizze als Abbildung mit der Maßzahl 100 (cm) und der Unterschrift",
              len(fig_) == 1 and "<svg" in fig_[0][1] and ">100</text>" in fig_[0][1] and fig_[0][2] == "Blech mit Bohrung",
              str([b[0] for b in bl_]))
        bl2_ = Rep_(m_)._eintrag_bloecke(eintr_[1], 2)
        check("Bericht nennt die PDF-Datei als Anlage", any(b[0] == "note" and "PDF" in b[1] for b in bl2_), str(bl2_)[:120])
        zeilen_ = list(w.tbl_unterlagen.modell.zeilen)
        check("Tabelle Unterlagen: vier Zeilen, die Skizze mit 1 im Bericht",
              len(zeilen_) == 4 and any(z[1] == "Blech" and int(z[8]) == 1 for z in zeilen_), str([(z[1], z[2]) for z in zeilen_]))
        d_ = m_.to_dict()
        m2_ = type(m_).from_dict(d_)
        check("Unterlagen werden mit dem Modell gespeichert und geladen",
              set(m2_.unterlagen) == set(m_.unterlagen) and len(m2_.unterlagen["Blech"].skizze["elemente"]) == 4)
        check("Modellbaum: Zweig Unterlagen mit der Skizze",
              any(it.child(i).text(0) == "Blech"
                  for it in w.baum.findItems("Unterlagen", QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive)
                  for i in range(it.childCount())))
        w.unterlage_loeschen("zeichnung.pdf"); app.processEvents()
        check("Entfernen nimmt die Unterlage und ihren Berichtseintrag weg",
              "zeichnung.pdf" not in m_.unterlagen
              and all(e.datei != "zeichnung.pdf" for e in m_.bericht if getattr(e, "art", "") == "unterlage"))
        f2_ = w.unterlage_bearbeiten("Blech"); app.processEvents()
        check("Bearbeiten öffnet die Skizze wieder mit ihren Elementen", f2_ is not None and len(f2_.skizze["elemente"]) == 4)
        f2_.close(); app.processEvents()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Unterlagen", False, str(ex)[:70])

    try:
        # ---- Layer: Aufklappliste, Layerliste, sichtbar und gesperrt (16.09.2026) ----
        from statik3d.model import Member as Mb_
        w.new_model(); app.processEvents()
        m_ = w.model
        mat_ = list(m_.materials)[0]
        sec_ = list(m_.sections)[0]
        ka_, kb_, kc_, kd_, ke_ = (m_.add_node(*xyz) for xyz in ((0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0), (8, 0, 0)))
        ea_ = m_.add_element("beam", [ka_, kb_], mat_, sec_)
        eb_ = m_.add_element("beam", [kb_, ke_], mat_, sec_)
        m_.members["S1"] = Mb_("S1", elements=[ea_])
        m_.members["S2"] = Mb_("S2", elements=[eb_])
        for nm_, (a_, b_) in (("L1", (ka_, kb_)), ("L2", (kb_, kc_)), ("L3", (kc_, kd_)), ("L4", (kd_, ka_))):
            m_.add_line(nm_, [a_, b_])
        m_.add_flaeche("F1", ["L1", "L2", "L3", "L4"], material=mat_)
        w.refresh_all(); app.processEvents()
        check("Ribbon Ansicht: Aufklappliste der Layer (leer: nur „Alle Layer“, gesperrt) und Layerliste",
              hasattr(w, "cb_layer") and w.cb_layer.count() == 1 and w.cb_layer.itemText(0) == "Alle Layer"
              and not w.cb_layer.isEnabled() and hasattr(w, "act_layerliste"))
        w._auswahl_leeren(); w.sel_flaechen = ["F1"]
        w.layer_aus_auswahl("Deckel"); app.processEvents()
        w._auswahl_leeren(); w.sel_staebe = ["S2"]; w.selection = np.array([ke_], int)
        w.layer_aus_auswahl("Traeger"); app.processEvents()
        check("Layer aus Auswahl: zwei Layer, die Aufklappliste nennt sie",
              set(m_.layer) == {"Deckel", "Traeger"} and m_.layer["Deckel"].flaechen == ["F1"]
              and m_.layer["Traeger"].staebe == ["S2"] and m_.layer["Traeger"].knoten == [ke_]
              and [w.cb_layer.itemText(i) for i in range(w.cb_layer.count())] == ["Alle Layer", "Deckel", "Traeger"],
              str([w.cb_layer.itemText(i) for i in range(w.cb_layer.count())]))
        w.cb_layer.setCurrentIndex(2); app.processEvents()
        v_ = w.verborgen
        check("Aufklappliste: nur Traeger im Bild - Fläche, Linien und der andere Stab verborgen; von Hand ist nichts ausgeblendet",
              w._layer_nur == "Traeger" and "F1" in v_["flaechen"] and {"L1", "L2", "L3", "L4"} <= v_["linien"]
              and ea_ in v_["elemente"] and eb_ not in v_["elemente"] and not any(w.versteckt.values())
              and not w._objekt_sichtbar("Fläche", "F1") and w._objekt_sichtbar("Stab", "S2"),
              f"{sorted(v_['flaechen'])} {sorted(v_['elemente'])}")
        w.cb_layer.setCurrentIndex(0); app.processEvents()
        check("„Alle Layer“ zeigt wieder alles",
              w._layer_nur == "" and w._objekt_sichtbar("Fläche", "F1") and not w._layer_versteckt())
        w.layer_sichtbar_setzen("Deckel", False); app.processEvents()
        check("Haken „sichtbar“ weg blendet den Layer aus, die Aufklappliste sagt es",
              "F1" in w.verborgen["flaechen"] and not w._objekt_sichtbar("Fläche", "F1")
              and w.cb_layer.itemText(1) == "Deckel (ausgeblendet)", w.cb_layer.itemText(1))
        w.layer_sichtbar_setzen("Deckel", True); app.processEvents()
        # Sperre
        w.layer_gesperrt_setzen("Traeger", True); app.processEvents()
        w._auswahl_leeren()
        w.auswahlart_setzen("Stab")
        w._objekt_umschalten(w.sel_staebe, "S2", "Stäbe")
        check("gesperrter Layer: Klick wählt den Stab nicht, _wenn_sichtbar gibt None",
              w.sel_staebe == [] and w._wenn_sichtbar("Stab", "S2") is None and w._wenn_sichtbar("Stab", "S1") == "S1",
              str(w.sel_staebe))
        w.sel_staebe = ["S1", "S2"]; w.selection = np.array([ka_, ke_], int); w._auswahl_register()
        check("… und die Sperre räumt Stab und Knoten des Layers aus jeder Auswahl",
              w.sel_staebe == ["S1"] and sorted(int(i) for i in w.selection) == [ka_], f"{w.sel_staebe} {w.selection}")
        fehler_ = []
        alt_error_ = w.error
        w.error = lambda msg: fehler_.append(str(msg))
        w.knoten_bearbeiten(ke_); app.processEvents()
        w._objektmaske("stab", "S2"); app.processEvents()
        w.error = alt_error_
        check("gesperrter Layer: Knotendialog und Stabmaske öffnen nicht, die Meldung nennt den Layer",
              len(fehler_) == 2 and all("Traeger" in f for f in fehler_), str(fehler_))
        # Layerliste
        w.layerliste_zeigen(); app.processEvents()
        f_ = w._layer_fenster
        check("Layerliste: Fenster mit beiden Layern, Haken „gesperrt“ bei Traeger gesetzt",
              f_ is not None and f_.isVisible() and f_.tabelle.rowCount() == 2
              and f_.tabelle.item(f_.zeile_von("Traeger"), 2).checkState() == QtCore.Qt.Checked)
        f_.tabelle.item(f_.zeile_von("Traeger"), 2).setCheckState(QtCore.Qt.Unchecked); app.processEvents()
        check("Haken „gesperrt“ im Fenster entsperrt den Layer", not m_.layer["Traeger"].gesperrt)
        f_.tabelle.item(f_.zeile_von("Deckel"), 1).setCheckState(QtCore.Qt.Unchecked); app.processEvents()
        check("Haken „sichtbar“ im Fenster blendet aus",
              not m_.layer["Deckel"].sichtbar and "F1" in w.verborgen["flaechen"])
        f_.tabelle.setCurrentCell(f_.zeile_von("Traeger"), 0)
        f_.knoepfe["Objekte wählen"].click(); app.processEvents()
        check("„Objekte wählen“ holt Stab und Knoten des Layers in die Auswahl, Auswahlart Stab",
              w.sel_staebe == ["S2"] and sorted(int(i) for i in w.selection) == [ke_] and w.auswahlart == "Stab",
              f"{w.sel_staebe} {w.selection} {w.auswahlart}")
        ok_ = w.layer_umbenennen("Traeger", "Träger"); app.processEvents()
        check("Umbenennen", ok_ and "Träger" in m_.layer and "Traeger" not in m_.layer and f_.zeile_von("Träger") >= 0)
        w.layer_loeschen("Träger"); app.processEvents()
        check("Löschen (Rückfrage bejaht) nimmt den Layer weg, die Objekte bleiben",
              "Träger" not in m_.layer and "S2" in m_.members and w.cb_layer.count() == 2 and f_.tabelle.rowCount() == 1)
        w.layer_alle_zeigen(); app.processEvents()
        check("Modellbaum: Zweig Layer mit dem Eintrag Deckel",
              any(it.child(i).text(0) == "Deckel"
                  for it in w.baum.findItems("Layer", QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive)
                  for i in range(it.childCount())))
        d_ = w.model.to_dict()
        check("Layer werden mit dem Modell gespeichert", any(x["name"] == "Deckel" for x in d_.get("layer", [])))
        f_.close(); app.processEvents()
        w._auswahl_leeren()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Layer", False, str(ex)[:70])

    try:
        _kuerzel_pruefen(w, app)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Tastenkürzel unabhängig vom Register", False, str(ex)[:70])

    # Screenshot
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gui_smoke.png")
    try:
        w.load_example("hall"); an = solver.solve_all(w.model, design=True); w._solve_done("all", an)
        w.cb_field.setCurrentText("Ausnutzung EC3"); w.cb_diagram.setCurrentText("My"); app.processEvents()
        w.plotter.screenshot(out)
        check("Screenshot", os.path.getsize(out) > 5000, out)
        fenster = os.path.join(os.path.dirname(out), "_gui_fenster.png")
        w.grab().save(fenster)
        check("Screenshot des Fensters", os.path.getsize(fenster) > 5000, fenster)
    except Exception as ex:
        check("Screenshot", False, str(ex))
    w.close()
    nok = sum(1 for r in RESULTS if r[1])
    print(f"Ergebnis: {nok}/{len(RESULTS)} GUI-Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
