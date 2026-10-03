"""
Paket F des Oberflaechenplans vom 01.10.2026: vier Fehler, die beim Abgleich
des Plans mit dem Quelltext aufgefallen sind. Jede Pruefung reisst ohne die
Behebung.

* F1 Der Dialog „Schlupf, Reibung, Grenzkraft …“ hatte keine Spalte fuer die
  Grenzkraft: ein OK setzte eine aus RFEM gelesene Grenzkraft still auf
  0 = unbegrenzt.
* F2 Ein Gelenk liess sich in der Desktop-Oberflaeche keinem Stab zuweisen:
  „Gelenke setzen…“ zeigte die Maske Lager/Lasten ohne Gelenkfeld.
* F3 Die Unterzweige Punktmassen, Daempfer, Federn, Starre Koerper und
  Grenzschichten trugen die Art „kontakt“ und oeffneten das Register Kontakt
  statt ihrer Uebersicht.
* F4 Linien- und Flaechenlager anlegen liess sich nicht rueckgaengig machen.

Aufruf:  python -m tests.test_paket_f
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_paket_f_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w.fehler_liste = []
    w.error = lambda msg: (w.fehler_liste.append(str(msg)), w.log.appendPlainText("FEHLER: " + str(msg)))
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell(w):
    from statik3d.model import Material, Section, ShellProp
    w.new_model()
    m = w.model
    m.add_material(Material("S235", E=210e9, nu=0.3, rho=7850))
    m.add_section(Section("R", A=1e-2, Iy=1e-5, Iz=1e-5, It=1e-5, Iw=1e-7))
    m.add_shell_prop(ShellProp("t10", 0.01))
    n = [m.add_node(0, 0, 0), m.add_node(1, 0, 0), m.add_node(2, 0, 0), m.add_node(1, 1, 0)]
    m.add_element("beam", [n[0], n[1]], "S235", "R")
    m.add_element("beam", [n[1], n[2]], "S235", "R")
    m.add_element("shell3", [n[0], n[1], n[3]], "S235", "t10")
    return m, n


def test_grenzkraft_bleibt():
    from PySide6 import QtWidgets
    from statik3d.model import Model
    from statik3d.gui import dialogs as dg
    _fenster()
    m = Model("F1")
    m.add_node(0, 0, 0)
    s = m.support(0, "pinned", uz=dict(typ="rigid", failure="zug", limit=50e3))
    d = dg.SupportNonlinearDialog(None, s, "Knotenlager")
    check("F1 Dialog hat eine Spalte Grenzkraft",
          d.tbl.columnCount() == 7 and "Grenzkraft" in d.tbl.horizontalHeaderItem(6).text(),
          str(d.tbl.columnCount()))
    d.apply(s)
    check("F1 OK ohne Änderung behält die Grenzkraft 50 kN (bisher still 0 = unbegrenzt)",
          abs(s.dof_behaviour(2).limit - 50e3) < 1e-6, str(s.dof_behaviour(2).limit))
    d = dg.SupportNonlinearDialog(None, s, "Knotenlager")
    d.grenzen[2].set(20.0)
    d.apply(s)
    check("F1 Grenzkraft im Dialog geändert: 20 kN im Lager",
          abs(s.dof_behaviour(2).limit - 20e3) < 1e-6, str(s.dof_behaviour(2).limit))
    gewarnt = []
    alt = QtWidgets.QMessageBox.warning
    QtWidgets.QMessageBox.warning = lambda *a, **k: gewarnt.append(a[2] if len(a) > 2 else "")
    try:
        for zeile, fall, erwartet in ((1, "negativ", "Betrag"), (3, "frei", "freien"),
                                      (0, "starr ohne Ausfall und Schlupf", "nur Druck")):
            d = dg.SupportNonlinearDialog(None, s, "Knotenlager")
            d.grenzen[zeile].set(-5.0 if fall == "negativ" else 30.0)
            n = len(gewarnt)
            d.accept()
            check(f"F1 Grenzkraft {fall}: Hinweis, Dialog bleibt offen",
                  len(gewarnt) == n + 1 and erwartet in gewarnt[-1] and d.result() != QtWidgets.QDialog.Accepted,
                  str(gewarnt[-1:]))
        d = dg.SupportNonlinearDialog(None, s, "Knotenlager")
        d.rows[0][3].set(2.0)                   # Schlupf 2 mm an ux
        d.grenzen[0].set(30.0)
        n = len(gewarnt)
        d.accept()
        d.apply(s)
        check("F1 Grenzkraft mit Schlupf: angenommen und im Lager",
              len(gewarnt) == n and abs(s.dof_behaviour(0).limit - 30e3) < 1e-6, str(gewarnt[n:]))
    finally:
        QtWidgets.QMessageBox.warning = alt


def test_gelenk_zuweisen():
    w, app = _fenster()
    m, n = _modell(w)
    m.add_hinge("G1", end=1, phiy="free", phiz="free")
    w.refresh_all(); app.processEvents()
    w._set_selection([n[0], n[1]]); app.processEvents()
    w.zuweisen_zeigen("gelenke"); app.processEvents()
    mk = w.maskenrand.maske
    check("F2 „Gelenke setzen…“ mit Auswahl zeigt die Gelenkmaske (bisher Lager/Lasten ohne Gelenkfeld)",
          mk is not None and "Gelenk G1" in mk.titel, str(mk and mk.titel))
    knopf = (getattr(mk, "zusatzknoepfe", None) or {}).get("Auf gewählte Stäbe setzen")
    check("F2 die Gelenkmaske hat „Auf gewählte Stäbe setzen“", knopf is not None,
          str(sorted(getattr(mk, "zusatzknoepfe", {}) or {})))
    if knopf is None:
        return
    vorher = len(w._undo)
    knopf.click(); app.processEvents()
    e0, e1 = m.elements[0], m.elements[1]
    check("F2 das Gelenk sitzt am gewählten Stab (Ende: φy, φz frei), der andere bleibt biegesteif",
          set(e0.hinges) == {10, 11} and not e1.hinges and m.hinges["G1"].elemente == [0],
          f"{e0.hinges} / {e1.hinges} / {m.hinges['G1'].elemente}")
    check("F2 ein Rückgängig-Schritt", len(w._undo) == vorher + 1, f"{vorher} -> {len(w._undo)}")
    w.undo(); app.processEvents()
    m = w.model
    check("F2 Rückgängig nimmt das Gelenk vom Stab", not m.elements[0].hinges and not m.hinges["G1"].elemente,
          str(m.elements[0].hinges))
    # Ein Stab aus mehreren Elementen: das Gelenk gehoert an sein Ende, nicht an
    # jede Elementgrenze (Gegenpruefung, 01.10.2026)
    from statik3d.model import Member
    m.members["S1"] = Member("S1", [0, 1])
    m.add_hinge("G2", end=0, phiy="free")
    w.refresh_all(); app.processEvents()
    w._set_selection([n[0], n[1], n[2]]); app.processEvents()
    w._gelenk_auf_auswahl("G1"); app.processEvents()
    check("F2 ganzer Stab über seine Knoten gewählt: Gelenk „Stabende“ nur am letzten Element",
          not w.model.elements[0].hinges and set(w.model.elements[1].hinges) == {10, 11},
          f"{w.model.elements[0].hinges} / {w.model.elements[1].hinges}")
    w.undo(); app.processEvents()
    w._set_selection([]); app.processEvents()
    w.sel_staebe = ["S1"]
    w._gelenk_auf_auswahl("G2"); app.processEvents()
    check("F2 Auswahlart Stab: Gelenk „Stabanfang“ nur am ersten Element",
          set(w.model.elements[0].hinges) == {4} and not w.model.elements[1].hinges,
          f"{w.model.elements[0].hinges} / {w.model.elements[1].hinges}")
    w.undo(); app.processEvents()
    w.sel_staebe = []
    w._set_selection([]); app.processEvents()
    w._objektmaske("gelenk", "G1"); app.processEvents()
    n_f = len(w.fehler_liste)
    w.maskenrand.maske.zusatzknoepfe["Auf gewählte Stäbe setzen"].click(); app.processEvents()
    check("F2 ohne Auswahl: Hinweis, nichts gesetzt",
          len(w.fehler_liste) == n_f + 1 and "wählen" in w.fehler_liste[-1] and not w.model.elements[0].hinges,
          str(w.fehler_liste[-1:]))


def test_verbindungszweige():
    from PySide6 import QtCore, QtWidgets
    w, app = _fenster()
    m, n = _modell(w)
    m.add_feder_prop("F1", [1e6, 1e6, 1e6, 0, 0, 0])
    m.add_element("feder", [n[1], n[2]], "S235", "F1")
    m.add_punktmasse(n[2], 250.0, [1.0, 2.0, 3.0])
    m.add_daempfer(n[2], -1, [40.0, 0, 0, 0, 0, 0])
    m.add_starrkoerper(n[0], [n[1]], "RBE2")
    m.add_grenzschicht_prop("GS", 1e9, 5e8)
    w.refresh_all(); app.processEvents()
    zweige = {}

    def lauf(x):
        for k in range(x.childCount()):
            kind = x.child(k)
            zweige.setdefault(kind.text(0), kind)
            lauf(kind)
    lauf(w.baum.invisibleRootItem())
    for text in ("Punktmassen", "Dämpfer", "Federn", "Starre Körper", "Grenzschichten"):
        it = zweige.get(text)
        if not check(f"F3 Unterzweig „{text}“ steht im Baum", it is not None):
            continue
        art = it.data(0, QtCore.Qt.UserRole)
        w._baum_geklickt(art, ""); app.processEvents()
        mk = w.maskenrand.maske
        check(f"F3 Klick auf „{text}“ zeigt seine Übersicht (bisher das Register Kontakt)",
              art != "kontakt" and mk is not None and mk.titel == text,
              f"Art {art}, Maske {mk and mk.titel}, Dock {w.eingaben_dock.windowTitle()}")
        knoepfe = [b.text() for b in mk.findChildren(QtWidgets.QPushButton)] if mk is not None else []
        check(f"F3 Übersicht „{text}“ ohne stummen Knopf „Neue …“",
              not any(t.startswith("Neue") for t in knoepfe), str(knoepfe))


def test_lager_rueckgaengig():
    from statik3d.gui import dialogs as dg
    w, app = _fenster()
    m, n = _modell(w)
    w.refresh_all(); app.processEvents()
    alt = dg.SupportNonlinearDialog.exec
    dg.SupportNonlinearDialog.exec = lambda self: 1
    try:
        w._set_selection([n[0], n[1], n[2]]); app.processEvents()
        vorher = len(w._undo) if hasattr(w, "_undo") else 0
        w.add_line_support(); app.processEvents()
        check("F4 Linienlager angelegt, ein Rückgängig-Schritt",
              len(w.model.line_supports) == 1 and len(w._undo) == vorher + 1,
              f"{len(w.model.line_supports)} Lager, Schritte {vorher} -> {len(w._undo)}")
        w.undo(); app.processEvents()
        check("F4 Rückgängig entfernt das Linienlager wieder", len(w.model.line_supports) == 0,
              str(len(w.model.line_supports)))
        if getattr(w, "ed_elist", None) is not None:
            w.ed_elist.setText("")
        w._set_selection([n[0], n[1], n[3]]); app.processEvents()
        vorher = len(w._undo)
        w.add_surface_support(); app.processEvents()
        check("F4 Flächenlager angelegt, ein Rückgängig-Schritt",
              len(w.model.surface_supports) == 1 and len(w._undo) == vorher + 1,
              f"{len(w.model.surface_supports)} Lager, Schritte {vorher} -> {len(w._undo)}")
        w.undo(); app.processEvents()
        check("F4 Rückgängig entfernt das Flächenlager wieder", len(w.model.surface_supports) == 0,
              str(len(w.model.surface_supports)))
    finally:
        dg.SupportNonlinearDialog.exec = alt


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_grenzkraft_bleibt, test_gelenk_zuweisen, test_verbindungszweige, test_lager_rueckgaengig):
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
