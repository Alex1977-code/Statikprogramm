"""
Rauchtest der Oberflaeche ohne Benutzer (X-Server noetig, z.B. xvfb-run):
    xvfb-run -a python -m tests.test_gui_smoke
Laedt alle Beispiele, rechnet, schaltet alle Anzeigen durch, erzeugt Dialoge
und einen Screenshot.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

RESULTS = []


def check(name, ok, info=""):
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name} {info}")
    return ok


def main():
    if not os.environ.get("DISPLAY") and sys.platform.startswith("linux"):
        print("Kein DISPLAY - Test uebersprungen (xvfb-run verwenden)")
        return 0
    from PySide6 import QtWidgets
    from statik3d import solver
    from statik3d.gui.main import MainWindow, FIELDS, DIAGRAMS
    from statik3d.gui import dialogs as dg
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    app.processEvents()
    check("Fenster erzeugt", w.isVisible())

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
    check("Tabellen gefuellt", w.tbl_design.rowCount() >= 1 and w.tbl_react.rowCount() >= 1)

    # Dialoge erzeugen (ohne exec)
    d1 = dg.MaterialDialog(w); d1._grade_changed("S355"); mat = d1.result_material()
    d2 = dg.SectionDialog(w); d2.family.setCurrentText("HEB"); sec = d2.result_section()
    d3 = dg.LoadCaseDialog(w, existing=list(w.model.load_cases))
    d4 = dg.CombinationDialog(w, w.model)
    d5 = dg.AutoCombinationDialog(w, w.model.design)
    d6 = dg.FatigueLoadDialog(w, w.model)
    mem = next(iter(w.model.members.values()))
    d7 = dg.MemberDialog(w, mem, 6.0); d7.apply(mem)
    d8 = dg.DesignSettingsDialog(w, w.model.design); d8.apply(w.model.design)
    d9 = dg.ContactPairDialog(w, w.model, 2)
    d10 = dg.ImportDialog(w, "test.dxf", w.model); opts = d10.options()
    d11 = dg.ReportDialog(w, w.model, "b.html"); ro = d11.options()
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
        w.stellungen = [Stellung(name=f"S{i}", winkel=float(a), beschreibung=t)
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
              register[:5] == ["Datei", "Start", "Geometrie", "Struktur", "Lager / Kontakt"]
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
              not w.btn_update.isVisible() and not w.lbl_version.isVisible())
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
        check("Stellung entfernt", len(w.stellungen) == 2, str(len(w.stellungen)))

        # Nicht-modale Masken: „Maske oder Klick“ (Vorgabe Kap. 3.8)
        w.load_example("frame")
        w.refresh_all()
        w.maske_knoten()
        m = w.maskenrand.maske
        check("Maske schwebt ueber der Ansicht",
              m is not None and m.isVisible() and m.parent() is w.centralWidget(),
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

        # Linien: Bogen aus drei angeklickten Knoten
        w.clear_selection()
        w.maske_linie()
        m = w.maskenrand.maske
        check("Linienmaske verlangt drei Knoten",
              m.titel == "Linie" and m.n_knoten == 3)
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
