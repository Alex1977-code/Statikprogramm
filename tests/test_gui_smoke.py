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
              j["state"]["nn"] == nn0 + 1 and w.model.nn == nn0 + 1 and f"Knoten: {nn0 + 1}" in w.lbl_info.text(),
              srv.local_url)
        w.stop_web_server()
        check("Web-Server beendet", w.web_server is None)
    except Exception as ex:
        check("Web-Server am GUI-Modell", False, str(ex))

    # Screenshot
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_gui_smoke.png")
    try:
        w.load_example("hall"); an = solver.solve_all(w.model, design=True); w._solve_done("all", an)
        w.cb_field.setCurrentText("Ausnutzung EC3"); w.cb_diagram.setCurrentText("My"); app.processEvents()
        w.plotter.screenshot(out)
        check("Screenshot", os.path.getsize(out) > 5000, out)
    except Exception as ex:
        check("Screenshot", False, str(ex))
    w.close()
    nok = sum(1 for r in RESULTS if r[1])
    print(f"Ergebnis: {nok}/{len(RESULTS)} GUI-Tests bestanden")
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
