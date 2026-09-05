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
    from PySide6 import QtWidgets, QtGui
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
        check("Klick auf ein Lager öffnet die Lagermaske",
              w.eingaben_dock.windowTitle() == "Lager/Lasten",
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
              w.eingaben_dock.windowTitle() == "Modell" and angaben["Knoten"] == str(m_.nn)
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
              tu.tabellen("Modell") == ["Knoten", "Linien", "Flächen", "Volumenkörper", "Elemente",
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
        # Situation: die Elemente des Stabs deaktivieren
        w._baum_geklickt("situation_neu", "+ Situation anlegen")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Neu: Situation-Maske mit Stellung, Deaktiviert und drei Knöpfen",
              mk.titel == "Neu: Situation" and mk.werte()["stellung"].startswith("–")
              and set(mk.zusatzknoepfe) == {"Auswahl deaktivieren", "Auswahl aktivieren", "Alle aktivieren"})
        w.clear_selection()
        w.sel_staebe = [stab]
        mk.zusatzknoepfe["Auswahl deaktivieren"].click()
        app.processEvents()
        check("„Auswahl deaktivieren“: Elemente in der Maske und im Bild ausgeblendet",
              f"{len(els)} Elemente" in mk.werte()["aus"] and set(w.versteckt["elemente"]) == els,
              mk.werte()["aus"])
        mk.setzen("name", "ohne Stiel")
        mk.anwenden()
        app.processEvents()
        sit = m_.situationen.get("ohne Stiel")
        check("OK legt die Situation an und stellt die Sicht wieder her",
              sit is not None and set(sit.deaktiviert) == els and not w.versteckt["elemente"]
              and "ohne Stiel" in zweige(w.baum), str(sit))
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
        an_ = solver.solve_all(m_)
        w._solve_done("all", an_)
        app.processEvents()
        for i in range(w.cb_result.count()):
            if w.cb_result.itemText(i).endswith("LFS"):
                w.cb_result.setCurrentIndex(i)
                break
        app.processEvents()
        r_ = w.current_result()
        check("Ergebnis der Situation: abgeschaltete Elemente ohne Schnittgrößen, im Bild weggelassen",
              r_ is not None and r_.info.get("situation") == "ohne Stiel"
              and all(np.allclose(r_.beam_end[i], 0) for i in els)
              and set(r_.info.get("inaktiv", [])) == els, str(r_.name if r_ else None))
        w._baum_geklickt("situation", "ohne Stiel")
        app.processEvents()
        mk = w.maskenrand.maske
        check("Situation zeigen: Maske und ausgeblendete Elemente",
              mk.titel == "Situation ohne Stiel" and set(w.versteckt["elemente"]) == els)
        mk.zusatzknoepfe["Alle aktivieren"].click()
        mk.anwenden()
        app.processEvents()
        check("Übernehmen: alles wieder aktiv", m_.situationen["ohne Stiel"].deaktiviert == []
              and not w.versteckt["elemente"])
        fehler.clear()
        w._baum_loeschen("situation", "ohne Stiel")
        check("eine benutzte Situation wird abgewiesen", bool(fehler) and "benutzt" in fehler[0]
              and "ohne Stiel" in m_.situationen, str(fehler[:1]))
        w._baum_loeschen("situation", GRUND)
        check("die Grundstellung lässt sich nicht löschen", len(fehler) == 2 and "Grundstellung" in fehler[1])
        w.error = fehler_alt
        del w._bestaetigen
        check("Modellangaben nennen Subsysteme, Situationen, Stellungen",
              dict(w.modellangaben())["Situationen"] == "2" and dict(w.modellangaben())["Subsysteme"] == "2"
              and "Stellungen" in dict(w.modellangaben()))
        w.maskenrand.schliessen()

        # ---- Knicklaengen aus der Knickfigur ----
        w.load_example("hall")
        app.processEvents()
        m_ = w.model
        beta_alt = {k: (mem.beta_y, mem.beta_z) for k, mem in m_.members.items()}
        erg = w.do_knicklaengen()
        app.processEvents()
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
        check("Wasserdruck-Maske mit der gewählten Fläche und den Knöpfen",
              mk.titel == "Neu: Wasserdruck" and "Haut" in mk.werte()["ziele"]
              and set(mk.zusatzknoepfe) == {"Auswahl übernehmen", "Kennwerte"}, str(mk.werte().get("ziele")))
        mk.setzen("h_ow", 4.0)
        mk.setzen("richtung", "global x")
        mk.setzen("absenkung", False)
        mk.zusatzknoepfe["Kennwerte"].click()
        app.processEvents()
        check("Kennwerte in der Maske: F = ½ρgh²b = 235,4 kN", "235.4 kN" in mk.werte()["kennwerte"],
              mk.werte()["kennwerte"])
        mk.anwenden()
        app.processEvents()
        wd_ = m_.wasserdruecke.get("W1")
        check("„Lasten erzeugen“: Generierer, Lastfall, Objektlast, Elementlasten nur unter Wasser",
              wd_ is not None and wd_.lastfall in m_.load_cases
              and any(gl.verlauf.get("art") == "wasser" for gl in m_.load_cases[wd_.lastfall].geometrielasten)
              and len(m_.load_cases[wd_.lastfall].face_loads) == 6 * 16 and "W1" in zweige(w.baum),
              str(len(m_.load_cases[wd_.lastfall].face_loads) if wd_ else None))
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
        check("Bericht: Kapitel Lastgenerierer mit Tabelle, Erläuterung (Poleni) und Skizze",
              any(x[0] == "table" for x in bl_) and any(x[0] == "figure" and "<svg" in x[1] for x in bl_)
              and any(x[0] == "p" and "Poleni" in x[1] for x in bl_), str([x[0] for x in bl_]))
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
        klick_bei(xa, ya)
        check("Klick ins Leere beginnt das Auswahlfenster", w._fenster_ecke is not None)
        klick_bei(xb, yb)
        check("zweiter Linksklick schließt das Fenster ab: alle drei Knoten gewählt",
              w._fenster_ecke is None and sorted(int(i) for i in w.selection) == [k0, k1, k2], str(w.selection))
        w.selection = np.array([], int)
        klick_bei(xa, ya)
        klick_bei(xa + 1, ya)
        check("Klick auf der ersten Ecke verwirft das Fenster", w._fenster_ecke is None and len(w.selection) == 0)
        w.auswahlart_setzen("Stab")
        w.sel_staebe = []
        xm_, ym_ = px(0.5 * (m_.nodes[k0] + m_.nodes[k1]))
        klick_bei(xm_ + 30, ym_ + 30)
        klick_bei(xm_ - 30, ym_ - 30)
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
        w.refresh_all()
        app.processEvents()
        fehler_ = []
        alt_error = w.error
        w.error = lambda text: fehler_.append(str(text))
        w.do_solve("case")
        app.processEvents()
        check("„Berechnen“ bei einem Teiltragwerk ohne Lager: Meldung mit Knoten statt Solver-Abbruch",
              bool(fehler_) and "Teiltragwerk" in fehler_[-1] and "K2" in fehler_[-1]
              and (w.worker is None or not w.worker.isRunning()), str(fehler_[-1:])[:160])
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
        check("Vernetzen: Fortschritt 0…3 je Fläche, Balken danach aus und wieder unbestimmt",
              werte_[:4] == [0, 0, 1, 2] and werte_[-1] == 3 and not w.progress_bar.isVisible()
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
            if int(v) == 1:
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

        check("Nach „Neues Modell“ steht rechts die Modellinformation", tab_() == "Modell", tab_())
        w.maske_zeigen("Netz")
        w.clear_selection()
        app.processEvents()
        check("Auswahl aufheben ohne offene Maske holt die Modellinformation zurück (kein Netz-Panel)",
              tab_() == "Modell", tab_())
        check("Ribbon Netz: Vernetzen, Netzeinstellungen, Vorschau; Generatoren als Masken",
              all(hasattr(w, a) for a in ("geometrie_vernetzen", "maske_netzeinstellungen", "netz_vorschau",
                                          "maske_stabzug", "maske_platte", "maske_quader")))
        w.maske_platte()
        app.processEvents()
        mk = w.maskenrand.maske
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
        w.maskenrand.schliessen()
        w.clear_selection()
        app.processEvents()
        check("Maske geschlossen, nichts gewählt: Modellinformation", tab_() == "Modell", tab_())
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
        mk.setzen("ziellaenge", 0.5)
        mk.setzen("intelligent", False)
        mk.setzen("form", "Dreiecke")
        mk.zusatzknoepfe["Vorschau"].click()
        app.processEvents()
        check("Netzeinstellungen: Vorschau schätzt 8 m² / 0,5² = 32 Elemente", "1 Flächen ≈ 32" in mk.werte()["vorschau"],
              mk.werte()["vorschau"])
        mk.anwenden()
        app.processEvents()
        check("Netzeinstellungen übernommen (eigene Ziellänge 0,5 m, Dreiecke, ohne Anpassung)",
              m_.netz.dichte == "eigene" and m_.netz.ziellaenge == 0.5 and not m_.netz.intelligent and m_.netz.form == 0, str(fehler_))
        w.maskenrand.schliessen()
        w.sel_flaechen = []
        w.geometrie_vernetzen()
        app.processEvents()
        check("Vernetzen: Teilung 8 × 4 aus der Netzdichte, 64 Dreieckelemente, Protokoll nennt die Netzdichte",
              f_.teilung == [8, 4] and len(f_.elemente) == 64 and all(m_.elements[e].typ == "shell3" for e in f_.elemente)
              and "Netzdichte Fläche F1" in w.log.toPlainText(), str((f_.teilung, len(f_.elemente))))
        v_ = w.netz_vorschau()
        check("Netzvorschau: 32 Elemente geschätzt", bool(v_) and v_["n"] == 32)
        m_.netz.dichte = "mittel"
        m_.netz.intelligent = True
        m_.netz.form = 2
        w.geometrie_vernetzen()
        app.processEvents()
        D_ = (16 + 4) ** 0.5
        check("Netzdichte mittel: 16 Elemente über die Diagonale → Teilung 14 × 7, Vierecke",
              f_.teilung == [round(4 / (D_ / 16)), round(2 / (D_ / 16))] and all(m_.elements[e].typ == "shell4" for e in f_.elemente),
              str(f_.teilung))
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
              and "Knoten (2)" in texte_ and "Lager (1)" in texte_ and "Linien (2)" in texte_ and "Stäbe (2)" in texte_,
              str(texte_))
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
                                    "volumen", "netz", "nur_auswahl", "ausblenden",
                                    "zurueck", "alles", "fang", "auswahl_Knoten",
                                    "auswahl_Volumen", "auswahl_Netz")), str(sorted(kn)))
        check("Glasleiste: nur Symbole, der Text kommt beim Überfahren",
              all((not b.icon().isNull()) and b.toolTip()
                  and b.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly
                  for b in kn.values()),
              str([k for k, b in kn.items() if b.icon().isNull() or not b.toolTip()]))
        check("„Alles holen“ ist aus der Glasleiste weg",
              not any("zoom" in k.lower() or "holen" in k.lower() for k in kn))
        ansicht = w.centralWidget()
        mitte_leiste = w.glasleiste.x() + w.glasleiste.width() / 2
        # mittig - oder, wenn der Wuerfel im Weg ist, knapp links von ihm
        frei_vom_wuerfel = w.glasleiste.geometry().right() < w.ansichtswuerfel.x()
        check("die Glasleiste steht mittig oben und nie unter dem Würfel",
              (abs(mitte_leiste - ansicht.width() / 2) <= 3 or
               (frei_vom_wuerfel and abs(mitte_leiste - ansicht.width() / 2) < 60))
              and frei_vom_wuerfel and w.glasleiste.y() <= 16,
              f"Mitte {mitte_leiste:.0f} von {ansicht.width()} px, y = {w.glasleiste.y()}, "
              f"rechts {w.glasleiste.geometry().right()} < Würfel {w.ansichtswuerfel.x()}")

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
        check("Nur Auswahl zeigen blendet den Rest aus",
              w.versteckt["elemente"] == alle - elems, str(len(w.versteckt["elemente"])))
        w.alles_zeigen()
        app.processEvents()
        check("Alles zeigen räumt auf",
              not any(w.versteckt.values()) and not w.act_alles_zeigen.isEnabled())
        w.sel_staebe = []

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
        check("Kennwerte nennen Auflagerkräfte und Verdrehungen",
              any(z.startswith("Rz") for z in w._kennwerte_zeilen)
              and any(z.startswith("phiy") for z in w._kennwerte_zeilen),
              str(w._kennwerte_zeilen[:3]))
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
        pl = pvx.Plotter(off_screen=True)
        vpl.add_geometrie(pl, mz, raender={}, seiten={}, ausser_flaechen={"Mantel"})
        check("eine ausgeblendete Fläche fehlt im Bild", "geo_flaechen" not in pl.renderer.actors)
        pl.close()
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
