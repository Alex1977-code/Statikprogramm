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
    from statik3d.model import Model
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
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    zeilen = w._kennwerte_zeichnen(r)
    text = "\n".join(zeilen)
    check("Kennwerte im Bild: größte Verformung mit Knoten",
          any(z.startswith("u ") and "Knoten" in z for z in zeilen)
          and any(z.startswith("uz") for z in zeilen),
          zeilen[1] if len(zeilen) > 1 else "-")
    check("Kennwerte im Bild: nur die gewählte Schnittgröße",
          any(z.startswith("My ") for z in zeilen)
          and not any(z.startswith("Vz ") for z in zeilen), text[:80])
    ausn = next((z for z in zeilen if "Ausnutzung" in z), "")
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
        for zweig in ("Geometrie", "Knoten", "Linien", "Elemente", "Stäbe",
                      "Eigenschaften", "Querschnitte", "Werkstoffe", "Dicken",
                      "Lager", "Knotenlager", "Gelenke", "Einwirkungen",
                      "Lastfälle", "Kombinationen"):
            check(f"Modellbaum: Zweig „{zweig}“", zweig in namen)

        register = [w.tab_unten.tabText(i) for i in range(w.tab_unten.count())]
        for reg in ("Knoten", "Linien", "Elemente", "Lager", "Gelenke",
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
        check("Lastfallbeschreibung editierbar",
              w._lastfall_aendern(0, 2, "Eigenlast Dach")
              and list(mb.load_cases.values())[0].description == "Eigenlast Dach")

        # Modellbaum: Klick waehlt aus, Doppelklick oeffnet
        w._baum_geklickt("stabelemente", "beam")
        check("Klick auf „Stäbe“ wählt die Stabknoten", len(w.selection) > 0,
              f"{len(w.selection)} Knoten")
        w._baum_geklickt("lager_einzeln", "0")
        check("Klick auf ein Lager wählt seinen Knoten",
              list(w.selection) == [int(mb.supports[0].node)], str(w.selection))
        w._baum_geklickt("linie", "L1")
        check("Klick auf die Linie wählt ihre Knoten", len(w.selection) == 3,
              str(w.selection))
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
        for punkt in ([2.0, 0, 0], [4.0, 1.0, 0], [2.0, 2.0, 0], [0, 1.0, 0]):
            w._picked(punkt)
        check("vier Linien ausgewählt", w.sel_linien == ["L1", "L2", "L3", "L4"],
              str(w.sel_linien))
        w._picked([2.0, 0.0, 0.0])
        check("nochmaliger Klick nimmt die Linie wieder heraus",
              "L1" not in w.sel_linien, str(w.sel_linien))
        w._picked([2.0, 0.0, 0.0])

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
        check("Volumenkörper stehen im Modellbaum", "Volumenkörper" in zweige(w.baum))
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
        namen = zweige(w.baum)
        check("Ergebnisse stehen im Modellbaum", "Ergebnisse" in namen)
        check("Bericht steht im Modellbaum", "Bericht" in namen)
        w._baum_geklickt("ergebnis", "combo:GZT7")
        check("Klick im Baum stellt das Ergebnis ein",
              "GZT7" in w.cb_result.currentText(), w.cb_result.currentText()[:40])
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
        check("Bericht hat das Kapitel „Übernommene Ergebnisbilder“",
              "Übernommene Ergebnisbilder" in html)
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
        check("Lasten stehen im Modellbaum", "Lasten" in zweige(w.baum))
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
        check("alle drei Fangarten an", sorted(w.fang_arten) == ["knoten", "mitte", "raster"],
              str(w.fang_arten))
        w.fangart_umschalten("mitte", False)
        check("eine Fangart abschaltbar", "mitte" not in w.fang_arten, str(w.fang_arten))
        check("die Statuszeile nennt die Fangarten",
              "knoten" in w.lbl_fang.text() and "mitte" not in w.lbl_fang.text(),
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
        check("der Würfel bietet alle sechs Seiten und „180°“",
              set(richtungen) == {"vorne", "hinten", "links", "rechts",
                                  "oben", "unten", "kehren"}, str(richtungen))
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
        nachher = w._bildpunkt_in_welt(x_qt, hoehe - 1 - y_qt)
        pos_n = np.asarray(w.plotter.camera_position[0], float)
        ziel_n = np.asarray(w.plotter.camera_position[1], float)
        groesse = max(float(np.linalg.norm(pos_v - ziel_v)), 1e-9)
        check("Mausrad zoomt zum Zeiger: der Punkt darunter bleibt liegen",
              vorher is not None and nachher is not None
              and float(np.linalg.norm(nachher - vorher)) < 1e-6 * groesse,
              f"Wanderung {float(np.linalg.norm(nachher - vorher)):.3e} m "
              f"bei Bildgröße {groesse:.3g} m")
        check("und die Kamera kommt dabei wirklich näher",
              float(np.linalg.norm(pos_n - ziel_n)) < 0.9 * groesse,
              f"{groesse:.4g} m -> {float(np.linalg.norm(pos_n - ziel_n)):.4g} m")
        check("der Zielpunkt wandert dabei mit (nicht die Bildmitte)",
              float(np.linalg.norm(ziel_n - ziel_v)) > 1e-9 * groesse,
              f"{np.round(ziel_v, 4)} -> {np.round(ziel_n, 4)}")

        w.auswahlart_setzen("Linie")
        check("Auswahlart auch in der Glasleiste",
              w.cb_auswahlart_glas.currentText() == "Linie",
              w.cb_auswahlart_glas.currentText())
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
        check("Klick auf ein Lager öffnet die Lagermaske",
              w.eingaben_dock.windowTitle() == "Lager/Lasten",
              w.eingaben_dock.windowTitle())
        stab = list(w.model.members)[0]
        w._baum_geklickt("stab", stab)
        check("Klick auf einen Stab lässt seine Elemente aufleuchten",
              len(w.leuchtet) == len(w.model.members[stab].elements),
              f"{len(w.leuchtet)} Elemente")
        check("und öffnet die Nachweismaske",
              w.eingaben_dock.windowTitle() == "Nachweise",
              w.eingaben_dock.windowTitle())
        w.clear_selection()
        check("Auswahl aufheben löscht auch das Aufleuchten", not w.leuchtet)

        # Viele freie Knoten übertönen die Hervorhebung nicht
        w.new_model()
        w.model.add_nodes(np.array([[i, 0, 0] for i in range(20)], float))
        check("bei überwiegend freien Knoten keine Sonderfarbe",
              len(vpl.unbelegte_knoten(w.model)) > vpl.FREI_ANTEIL * w.model.nn)
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        check("Lasten, Fang, Glasleiste", False, str(ex)[:70])

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
