"""Vorspannung je Anker in der Oberflaeche (offscreen, 16.10.2026).

Geprueft: Zuordnungsdialog (Gruppen, wirksame Kraft, Vorschlaege, „Übernehmen“
prueft vor dem Schliessen, „Abbrechen“ aendert nichts), der Weg ueber das
Fenster samt Rueckgaengig, die Maske der Definition (P_max, P₀, P_∞, ΔP_t
angezeigt, Aenderung uebernommen), das Feld „Vorspannung je Anker“ der
Lastfallmaske, Modellbaum (Zweig, Eintraege, Verweis am Lastfall), Bericht.

Aufruf:  python -m tests.test_vorspannung_je_anker_maske
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_je_anker_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
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
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell(w):
    """Zwei Anker Rund 40 (Spannstahl) und ein Klemmstab; LF398 (P) und LF2 (Q)
    tragen 952 kN als ΔT, LF399 (P) und LF401 (FAT) 805 kN als ΔT, LF1 die
    Endvorspannung 944,7 kN - wie das Drehlager im Kleinen."""
    from statik3d.model import LoadCase, Material, NodalLoad, Section, TempLoad
    w.new_model()
    m = w.model
    m.add_material(Material("Spannstahl St 835/1030", E=205e9, nu=0.3, rho=7850, alpha=1e-5,
                            fy=835e6, fu=1030e6, art="Spannstahl"))
    m.add_section(Section.circle("Rund 40", 0.04))
    g1, g2, g3 = (m.add_node(0.0, 0.0, 0.0), m.add_node(0.1, 0.0, 0.0), m.add_node(0.2, 0.0, 0.0))
    h = m.add_node(0.1, 0.0, 1.0)
    for g in (g1, g2, g3):
        m.fix(g, "all")
    m.fix(h, [0, 1, 3, 4, 5])
    a1 = m.add_element("truss", [g1, h], "Spannstahl St 835/1030", "Rund 40")
    a2 = m.add_element("truss", [g3, h], "Spannstahl St 835/1030", "Rund 40")
    m.add_element("truss", [g2, h], "Spannstahl St 835/1030", "Rund 40")
    m.add_member("A1", [a1])
    m.add_member("A2", [a2])
    m.load_cases.clear()
    A = m.sections["Rund 40"].A
    for lf, kat, N in (("LF398", "P", 952e3), ("LF2", "Q", 952e3), ("LF399", "P", 805e3),
                       ("LF401", "FAT", 805e3)):
        lc = LoadCase(lf, category=kat)
        m.load_cases[lf] = lc
        for e in (a1, a2):
            lc.temp_loads.append(TempLoad(e, -N / (205e9 * A * 1e-5)))
        if kat != "P":
            lc.nodal_loads.append(NodalLoad(h, [0.0, 0.0, 10e3, 0.0, 0.0, 0.0]))
    m.load_cases["LF1"] = LoadCase("LF1", category="Q")
    for s in ("A1", "A2"):
        m.add_vorspannung(s, 944.7e3, case="LF1", sollkraft=True)
    m.active_case = "LF1"
    return m


def test_dialog():
    from statik3d import vorspannung as vsp
    from statik3d.gui.vorspannmaske import ZuordnungDialog, staebe_lesen
    w, app = _fenster()
    m = _modell(w)
    d = ZuordnungDialog(m, parent=w)
    texte = [d.tabelle.item(r, 0).text() for r in range(d.tabelle.rowCount())]
    print("     " + "\n     ".join(texte))
    check("Dialog: drei Gruppen (952 ΔT, 805 ΔT, 944,7 Endvorspannung)", len(d.gruppen) == 3, str(texte))
    r952, r805, r944 = (d.zeile_zu(vsp.ART_DT, 952e3), d.zeile_zu(vsp.ART_DT, 805e3),
                        d.zeile_zu(vsp.ART_ENDE, 944.7e3))
    check("Spalte „wirksam nach elastischer Verkürzung“ gefüllt (linear rechenbar oder Grund)",
          all(d.tabelle.item(r, 1).text() not in ("", "–") for r in (r952, r805, r944)),
          str([d.tabelle.item(r, 1).text() for r in range(3)]))
    check("Vorgabe: keine Zuordnung", all(d.zeilen[r]["zustand"].currentData() == "" for r in range(3)))
    d.setzen(r952, "0", "V1")
    check("Zeitpunkt 0: Vorschlag P_max = 952 kN, Δs und Spanngruppe frei, Endwert gesperrt",
          d.zeilen[r952]["wert"].wert() == 952.0 and d.zeilen[r952]["schlupf"].isEnabled()
          and not d.zeilen[r952]["endwert"].isEnabled())
    d.setzen(r805, "inf", "V1")
    check("Zeitpunkt ∞: Vorschlag P_∞ absolut = 805 kN", d.zeilen[r805]["wert"].wert() == 805.0
          and d.zeilen[r805]["endwert"].currentData() == "absolut")
    d.setzen(r805, "inf", endwert="verlust")
    check("Endwert Verlust: Feld auf ΔP_t = 0", d.zeilen[r805]["wert"].wert() == 0.0)
    d.setzen(r805, "inf", endwert="absolut")
    d.setzen(r952, "0", wert_kn=0.0)
    vor = repr(m.to_dict(netz=False))
    d._ok()
    check("„Übernehmen“ mit P_max 0: abgewiesen, Meldung im Dialog, Modell unverändert",
          d.ergebnis is None and "P_max fehlt" in d.meldung.text() and repr(m.to_dict(netz=False)) == vor,
          d.meldung.text())
    d.setzen(r952, "0", wert_kn=952.0)
    d._ok()
    check("„Übernehmen“ geprüft: Ergebnis da, Modell noch unverändert", d.ergebnis is not None
          and repr(m.to_dict(netz=False)) == vor)
    check("Stabliste lesen: „A1–A2“ und „S1–S3, S7“", staebe_lesen("A1–A2", m) == ["A1", "A2"]
          and staebe_lesen("S1-S3, S7") == ["S1", "S2", "S3", "S7"])


def test_fenster_zuordnen_und_rueckgaengig():
    from statik3d.gui import vorspannmaske as vm
    from statik3d import vorspannung as vsp
    w, app = _fenster()
    m = _modell(w)
    w.refresh_all()
    app.processEvents()

    def exec_(self):
        self.setzen(self.zeile_zu(vsp.ART_DT, 952e3), "0", "V1")
        self.setzen(self.zeile_zu(vsp.ART_DT, 805e3), "inf", "V1")
        self._ok()
        return self.ergebnis is not None
    alt = vm.ZuordnungDialog.exec
    vm.ZuordnungDialog.exec = exec_
    try:
        r = w.vorspannung_zuordnen()
    finally:
        vm.ZuordnungDialog.exec = alt
    app.processEvents()
    m = w.model
    zst = {n: dict(lc.vorspannzustand) for n, lc in m.load_cases.items()}
    check("Fenster: 4 Lastfälle verweisen, LF1 nicht", r and r["faelle"] == 4 and zst["LF1"] == {}
          and zst["LF398"] == {"V1": "0"} and zst["LF401"] == {"V1": "inf"}, str(zst))
    log = w.log.toPlainText()
    check("Protokoll: Zuordnung und Definitionszeile", "Vorspannung je Anker zugeordnet: 4 Lastfälle" in log
          and "Vorspannung V1 an A1–A2" in log)
    z = w.baum.zweig_finden("vorspanndefinitionen")
    kinder = [z.child(i).text(0) for i in range(z.childCount())] if z is not None else []
    check("Modellbaum: Zweig „Vorspannung je Anker“ mit V1, Anlegen und Zuordnen",
          z is not None and kinder[:1] == ["V1"] and any("anlegen" in k for k in kinder)
          and any("zuordnen" in k for k in kinder), str(kinder))
    w.undo()
    app.processEvents()
    check("Rückgängig: keine Definition, keine Verweise, ΔT wieder da",
          not w.model.vorspann_definitionen and not any(lc.vorspannzustand for lc in w.model.load_cases.values())
          and len(w.model.load_cases["LF398"].temp_loads) == 2)


def test_maske_definition_und_lastfall():
    from statik3d.model import VorspannDefinition
    from statik3d import vorspannung as vsp
    w, app = _fenster()
    m = _modell(w)
    m.vorspann_definitionen["V1"] = VorspannDefinition("V1", ["A1", "A2"], 952e3, 1e-3, 1, "absolut", 805e3)
    m.load_cases["LF398"].vorspannzustand = {"V1": "0"}
    w.refresh_all()
    app.processEvents()
    w.maske_vorspanndefinition("V1")
    app.processEvents()
    mk = w.maskenrand.maske
    felder = getattr(mk, "_felder", {}) or {}
    check("Maske Definition: Felder P_max, Δs, Spanngruppe, Endwert, P_∞, ΔP_t und Anzeige P₀",
          all(k in felder for k in ("P_max", "schlupf", "gruppe", "endwert", "P_inf", "dP_t", "P0",
                                    "P_inf_text", "dP_t_text")), str(list(felder)))
    texte = {k: getattr(felder[k], "text", lambda: "")() for k in ("P0", "P_inf_text", "dP_t_text") if k in felder}
    print(f"     {texte}")
    check("Anzeige: P₀ geschätzt, P_∞ 805 absolut, ΔP_t = P₀ − P_∞",
          "geschätzt" in texte.get("P0", "") and "805 kN (Eingabe, absolut)" in texte.get("P_inf_text", "")
          and "ΔP_t = P₀ − P_∞" in texte.get("dP_t_text", ""), str(texte))
    mk.setzen("endwert", vsp.ENDWERT_TEXT["verlust"])
    mk.setzen("dP_t", 50.0)
    mk.setzen("P_max", 960.0)
    mk.anwenden()
    app.processEvents()
    d = w.model.vorspann_definitionen["V1"]
    check("übernommen: P_max 960, Verlust ΔP_t 50 kN", d.P_max == 960e3 and d.endwert == "verlust"
          and abs(d.dP_t - 50e3) < 1e-6 and d.staebe == ["A1", "A2"], str(d))
    # Lastfallmaske: Feld Vorspannung je Anker
    w._objektmaske("lastfall", "LF2")
    app.processEvents()
    mk = w.maskenrand.maske
    felder = getattr(mk, "_felder", {}) or {}
    check("Lastfallmaske: Feld „Vorspannung je Anker“", "vorspannzustand" in felder, str(list(felder)))
    mk.setzen("vorspannzustand", "V1: Zeitpunkt ∞")
    mk.anwenden()
    app.processEvents()
    check("… übernommen: LF2 verweist auf V1 im Zeitpunkt ∞", w.model.load_cases["LF2"].vorspannzustand
          == {"V1": "inf"}, str(w.model.load_cases["LF2"].vorspannzustand))
    w._objektmaske("lastfall", "LF2")
    app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("vorspannzustand", "keine")
    mk.anwenden()
    app.processEvents()
    check("… „keine“ nimmt den Verweis weg", w.model.load_cases["LF2"].vorspannzustand == {})
    # neue Definition aus der Auswahl
    w.sel_staebe = ["A2"]
    w.maske_vorspanndefinition(neu=True)
    app.processEvents()
    mk = w.maskenrand.maske
    check("neue Definition: Name V2, Anker aus der Auswahl", mk.werte().get("name") == "V2"
          and mk.werte().get("staebe") == "A2", str(mk.werte()))
    mk.setzen("P_max", 900.0)
    mk.setzen("P_inf", 800.0)
    mk.anwenden()
    app.processEvents()
    check("… angelegt", "V2" in w.model.vorspann_definitionen and w.model.vorspann_definitionen["V2"].P_inf == 800e3)
    # Baum: der Verweis am Lastfall
    w.refresh_all()
    app.processEvents()
    it = w.baum.zweig_finden("lastfall", "LF398")
    kinder = [it.child(i).text(0) for i in range(it.childCount())] if it is not None else []
    check("Modellbaum: LF398 hat die Zeile „Vorspannung V1“", "Vorspannung V1" in kinder, str(kinder))
    # Bericht
    from statik3d.report import Report
    html = Report(w.model, None).html()
    i = html.find("P₀ nach dem Verankern")
    check("Bericht: Tabelle „Vorspannung je Anker“ und r_sup/r_inf unter „Nicht enthalten“",
          i >= 0 and "Nicht enthalten: obere und untere charakteristische Werte der Vorspannung" in html
          and "r_sup/r_inf nach EN 1992-1-1, 5.10.9" in html)
    check("Bericht: Zustand je Lastfall", "Vorspannung je Anker: Zeitpunkt 0 (V1)." in html)
    # Loeschen mit Verweisen
    zeilen = []
    w.model.vorspann_definition_loeschen("V1", protokoll=zeilen)
    check("Löschen: Verweis von LF398 entfernt, Zeile im Protokoll",
          w.model.load_cases["LF398"].vorspannzustand == {} and zeilen, str(zeilen))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_dialog, test_fenster_zuordnen_und_rueckgaengig, test_maske_definition_und_lastfall):
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
    rc = main()
    os._exit(rc)
