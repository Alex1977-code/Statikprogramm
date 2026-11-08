"""
Oberflaechenpaket A (Bestellung des Anwenders vom 08.11.2026), Punkte 1 bis 5.

1. Klicken statt Abtippen: in den Masken Linie (Feld „Knoten“), Stabelement
   (Knoten), Stab (Stabelemente), Knotenlager (Knoten), Linienlager (Linien,
   ohne Linien Knoten) und Flaechenlager (Flaechen) setzt ein Klick in der
   Ansicht die Nummer bzw. den Namen ins Feld, solange das Feld die Tastatur
   hat. Die Lagermasken haben dafuer editierbare Felder (vorher stand der Ort
   nur da, Linien und Flaechen eines Lagers gar nicht).
2. Jede Eintragsmaske hat einen Knopf „Neu: <Art> …“.
3. Linien- und Flaechenlager stehen immer im Modellbaum, auch leer, mit
   Rechtsklick „Neu“ und Doppelklick-Anlegen wie die Knotenlager.
4. Jeder Zweig mit „Neu“ hat eine Zeile „+ … anlegen“.
5. „Neues Flächenlager“ las das versteckte Feld ``ed_elist`` und scheiterte
   praktisch immer; jetzt oeffnet es die Maske mit dem Feld „Flächen“.

Jede Modellaenderung ist mit Rueckgaengig zurueckzunehmen.

Aufruf:  python -m tests.test_paket_a   (offscreen)
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(tempfile.mkdtemp(prefix="statik3d_paket_a_"),
                                                    "einstellungen.json")

RESULTS = []
_FENSTER = {}
MAT, SEC = "S355", "HEB 300"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if "w" in _FENSTER:
        return _FENSTER["w"], app
    from statik3d.gui.main import MainWindow
    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _modell(w, app):
    """Platte 4 m x 3 m: Knoten K0..K3, Linien L1..L4, Flaeche F1; dazu ein Stab
    S1 aus dem Stabelement E0 von K0 nach K2 (S355, HEB 300)."""
    import numpy as np
    from statik3d.model import Material, Section
    w.new_model()
    m = w.model
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    for p in ((0, 0, 0), (4, 0, 0), (4, 3, 0), (0, 3, 0)):
        m.add_node(*p)
    for j in range(4):
        m.add_line(f"L{j + 1}", [j, (j + 1) % 4])
    m.add_flaeche("F1", ["L1", "L2", "L3", "L4"])
    w._maske_stab_anlegen({"knoten": [0, 2], "mat": MAT, "sec": SEC})
    w.refresh_all()
    _ruhe(app)
    w.maskenrand.schliessen()
    w.selection = np.array([], dtype=int)
    w.sel_linien, w.sel_flaechen = [], []
    w.fehler_liste.clear()
    _ruhe(app)
    return m


def _maske(w):
    return w.maskenrand.maske if w.maskenrand.offen() else None


def _baumzeilen(w):
    from PySide6 import QtCore, QtWidgets
    out = []
    it = QtWidgets.QTreeWidgetItemIterator(w.baum)
    while it.value():
        x = it.value()
        eltern = x.parent()
        out.append((str(x.data(0, QtCore.Qt.UserRole) or ""), x.text(0),
                    eltern.text(0) if eltern is not None else ""))
        it += 1
    return out


# ---------------------------------------------------------------------------
# Punkt 1: Klicken statt Abtippen
# ---------------------------------------------------------------------------
def _klick_knoten(w, app, i):
    """Ein Klick in der Ansicht auf Knoten i, so wie _picked ihn an eine Maske im
    Klickmodus gibt (_maskenobjekt_klick): der Zeiger steht auf dem Knoten."""
    alt = w._naechster_am_zeiger
    w._naechster_am_zeiger = lambda punkte, radius=None: (int(i), 0.0)
    try:
        w._maskenobjekt_klick(w.maskenrand.objekt_modus(), None)
    finally:
        w._naechster_am_zeiger = alt
    _ruhe(app)


def test_klicken_statt_abtippen():
    w, app = _fenster()
    m = _modell(w, app)
    # Linie: Feld „Knoten“
    w._objektmaske("linie", "L1")
    _ruhe(app)
    mk = _maske(w)
    w._maskenfeld_fokus(mk, "linie", "kn")
    check("Linie: Klick ins Feld „Knoten“ schaltet die Auswahl per Maus auf Knoten",
          mk.objekt_modus == "knoten", repr(mk.objekt_modus))
    _klick_knoten(w, app, 3)
    check("… ein Klick auf K3 in der Ansicht setzt 3 ins Feld", mk.werte().get("kn") == "0, 1, 3",
          repr(mk.werte().get("kn")))
    _klick_knoten(w, app, 3)
    check("… ein zweiter Klick nimmt ihn wieder heraus", mk.werte().get("kn") == "0, 1", repr(mk.werte().get("kn")))
    w.maskenrand.schliessen()
    # Stabelement: Feld „Knoten Anfang, Ende“
    w._objektmaske("stabelement", "0")
    _ruhe(app)
    mk = _maske(w)
    w._maskenfeld_fokus(mk, "stabelement", "kn")
    _klick_knoten(w, app, 2)
    _klick_knoten(w, app, 1)
    check("Stabelement: Knoten anklicken statt tippen („0, 2“ → „0, 1“)", mk.werte().get("kn") == "0, 1",
          repr(mk.werte().get("kn")))
    w.maskenrand.schliessen()
    # Stab: Feld „Elemente“ - Stabelement anklicken
    w._objektmaske("stab", "S1")
    _ruhe(app)
    mk = _maske(w)
    w._maskenfeld_fokus(mk, "stab", "elemente")
    check("Stab: Klick ins Feld „Elemente“ schaltet auf Stabelemente", mk.objekt_modus == "stabelement",
          repr(mk.objekt_modus))
    alt = w._element_am_zeiger
    w._element_am_zeiger = lambda: 0
    try:
        w._maskenobjekt_klick("stabelement", None)
    finally:
        w._element_am_zeiger = alt
    check("… ein Klick auf E0 nimmt es heraus (Feld leer)", mk.werte().get("elemente") == "",
          repr(mk.werte().get("elemente")))
    w.maskenrand.schliessen()
    # Knotenlager setzen: Feld „Knoten“
    w.selection = __import__("numpy").array([0], dtype=int)
    w.maske_lager()
    _ruhe(app)
    mk = _maske(w)
    check("Knotenlager setzen: Feld „Knoten“ mit der Auswahl", mk is not None and mk.werte().get("knoten_nr") == "0",
          repr(mk.werte().get("knoten_nr") if mk else None))
    w._maskenfeld_fokus(mk, "lager_setzen", "knoten_nr")
    _klick_knoten(w, app, 1)
    check("… ein Klick auf K1 nimmt ihn dazu", mk.werte().get("knoten_nr") == "0, 1", repr(mk.werte().get("knoten_nr")))
    mk.anwenden()
    _ruhe(app)
    check("… „Lager setzen“ setzt die Lager an K0 und K1", sorted(s.node for s in w.model.supports) == [0, 1],
          str([s.node for s in w.model.supports]))
    w.undo()
    _ruhe(app)
    check("… Rückgängig nimmt sie zurück", not w.model.supports)
    w.model.support(0, [0, 1, 2])
    w.refresh_all()
    _ruhe(app)
    # Knotenlager bearbeiten: Feld „Knoten“, der Klick ersetzt
    w._objektmaske("lager_einzeln", "0")
    _ruhe(app)
    mk = _maske(w)
    check("Knotenlager: der Knoten ist ein Feld (vorher nur Anzeige)",
          mk is not None and mk.werte().get("knoten_nr") == "0", repr(mk.werte().get("knoten_nr") if mk else None))
    w._maskenfeld_fokus(mk, "lager_einzeln", "knoten_nr")
    _klick_knoten(w, app, 2)
    check("… ein Klick auf K2 ersetzt den Knoten (ein Lager, ein Knoten)", mk.werte().get("knoten_nr") == "2",
          repr(mk.werte().get("knoten_nr")))
    mk.anwenden()
    _ruhe(app)
    check("… „Übernehmen“ setzt das Lager an K2", [s.node for s in w.model.supports] == [2],
          str([s.node for s in w.model.supports]))
    w.undo()
    _ruhe(app)
    check("… Rückgängig setzt es zurück an K0", [s.node for s in w.model.supports] == [0])
    # Linienlager: Feld „Linien“
    w.add_line_support()
    _ruhe(app)
    mk = _maske(w)
    w._maskenfeld_fokus(mk, "linienlager_einzeln", "linien")
    check("Linienlager: Feld „Linien“, Klick schaltet auf Linien", mk is not None and mk.objekt_modus == "linie",
          repr(getattr(mk, "objekt_modus", None)))
    mk.objekt_angeklickt("linie", "L1")
    mk.objekt_angeklickt("linie", "L2")
    check("… zwei Linien angeklickt", mk.werte().get("linien") == "L1, L2", repr(mk.werte().get("linien")))
    mk.anwenden()
    _ruhe(app)
    ll = w.model.line_supports
    check("… OK legt das Linienlager auf L1 und L2 an, Knoten in Linienfolge, ux uy uz starr",
          len(ll) == 1 and ll[0].linien == ["L1", "L2"] and ll[0].nodes == [0, 1, 2]
          and {d: b.typ for d, b in ll[0].behaviour.items()} == {0: "rigid", 1: "rigid", 2: "rigid"},
          str([(x.linien, x.nodes) for x in ll]))
    w._objektmaske("linienlager_einzeln", "0")
    _ruhe(app)
    mk = _maske(w)
    check("… seine Maske zeigt die Linien als Feld (vorher fehlte es)",
          mk is not None and mk.werte().get("linien") == "L1, L2", repr(mk.werte().get("linien") if mk else None))
    w.undo()
    _ruhe(app)
    check("… Rückgängig nimmt das Linienlager zurück", not w.model.line_supports)
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# Punkt 2: „Neu: … …“ in jeder Eintragsmaske
# ---------------------------------------------------------------------------
def test_neu_in_der_maske():
    w, app = _fenster()
    m = _modell(w, app)
    m.support(0, [0, 1, 2])
    w.refresh_all()
    _ruhe(app)
    faelle = [("knoten", "1", "Knoten"), ("linie", "L1", "Linie"), ("stab", "S1", "Stab"),
              ("stabelement", "0", "Stabelement"), ("geoflaeche", "F1", "Fläche"),
              ("werkstoff", MAT, "Werkstoff"), ("lager_einzeln", "0", "Knotenlager"),
              ("lastfall", m.active_case, "Lastfall")]
    fehlt = []
    for art, name, was in faelle:
        w._objektmaske(art, name)
        _ruhe(app)
        mk = _maske(w)
        knopf = (getattr(mk, "zusatzknoepfe", {}) or {}).get(f"Neu: {was} …")
        if knopf is None:
            fehlt.append(f"{art}: {list(getattr(mk, 'zusatzknoepfe', {}) or {})}")
        w.maskenrand.schliessen()
        _ruhe(app)
    check("Jede Eintragsmaske hat „Neu: <Art> …“ (Knoten, Linie, Stab, Stabelement, Fläche, Werkstoff, "
          "Knotenlager, Lastfall)", not fehlt, "; ".join(fehlt[:3]))
    w._objektmaske("linie", "L1")
    _ruhe(app)
    mk = _maske(w)
    knopf = (getattr(mk, "zusatzknoepfe", {}) or {}).get("Neu: Linie …")
    if knopf is not None:
        knopf.click()
        _ruhe(app)
    neu = _maske(w)
    check("… „Neu: Linie …“ öffnet die Maske „Neu: Linie L5“", neu is not None and neu.titel == "Neu: Linie L5",
          repr(getattr(neu, "titel", None)))
    check("… und legt dabei nichts an", sorted(w.model.lines) == ["L1", "L2", "L3", "L4"])
    w.maskenrand.schliessen()
    w._objektmaske("linie", "L1", neu=True)
    _ruhe(app)
    neu = _maske(w)
    check("Eine Neu-Maske selbst hat keinen Knopf „Neu …“",
          neu is not None and not any(t.startswith("Neu:") for t in neu.zusatzknoepfe), str(list(neu.zusatzknoepfe)))
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# Punkte 3 und 4: Baum
# ---------------------------------------------------------------------------
def test_baum_lager_und_anlegen():
    from statik3d.gui.design import Modellbaum
    w, app = _fenster()
    w.new_model()
    _ruhe(app)
    zeilen = _baumzeilen(w)
    arten = {a for a, _t, _e in zeilen}
    check("Leeres Modell: „Linienlager“ und „Flächenlager“ stehen im Baum (vorher nur, wenn es eines gab)",
          ("linienlager", "Linienlager", "Lager") in zeilen and ("flaechenlager", "Flächenlager", "Lager") in zeilen,
          str([z for z in zeilen if z[2] == "Lager"]))
    erwartet = {"knoten_neu": "Knoten", "linie_neu": "Linien", "stab_neu": "Stäbe", "geoflaeche_neu": "Flächen",
                "geokoerper_neu": "Volumen", "stabelement_neu": "Stabelemente", "werkstoff_neu": "Werkstoffe",
                "querschnitt_neu": "Querschnitte", "dicke_neu": "Dicken", "lager_neu": "Knotenlager",
                "linienlager_neu": "Linienlager", "flaechenlager_neu": "Flächenlager",
                "lastfall_neu": "Lastfälle", "kombination_neu": "Kombinationen"}
    falsch = [f"{a} unter {z}" for a, z in erwartet.items()
              if not any(x[0] == a and x[2] == z and x[1].startswith("+ ") and x[1].endswith(" anlegen")
                         for x in zeilen)]
    check("Jede Gruppe hat eine Zeile „+ … anlegen“ (Knoten, Linien, Stäbe, Flächen, Volumen, Stabelemente, "
          "Werkstoffe, Querschnitte, Dicken, Knoten-/Linien-/Flächenlager, Lastfälle, Kombinationen)",
          not falsch, "; ".join(falsch[:4]))
    check("… „+ Gelenk anlegen“ bleibt", "gelenk_neu" in arten)
    # Klick auf „+ Werkstoff anlegen“ wirkt wie Rechtsklick → Neu
    vorher = sorted(w.model.materials)
    w._baum_geklickt("werkstoff_neu", "+ Werkstoff anlegen")
    _ruhe(app)
    mk = _maske(w)
    check("Klick auf „+ Werkstoff anlegen“ öffnet „Neu: Werkstoff …“, ohne anzulegen",
          mk is not None and mk.titel.startswith("Neu: Werkstoff") and sorted(w.model.materials) == vorher,
          repr(getattr(mk, "titel", None)))
    w.maskenrand.schliessen()
    # Doppelklick-Anlegen und Rechtsklick „Neu“ fuer Linien- und Flaechenlager
    check("Linien- und Flächenlager: Doppelklick legt an wie bei Knotenlagern (BAUM_DOPPELKLICK_NEU)",
          {"lager", "linienlager", "flaechenlager"} <= set(w.BAUM_DOPPELKLICK_NEU))
    check("… und Rechtsklick „Neu“ (NEU_ARTEN)",
          Modellbaum.NEU_ARTEN.get("linienlager") == "Linienlager"
          and Modellbaum.NEU_ARTEN.get("flaechenlager") == "Flächenlager")
    from statik3d.gui import dialogs as dg
    modal = []
    alt = dg.SupportNonlinearDialog.exec
    dg.SupportNonlinearDialog.exec = lambda self_, *a: modal.append(1) or 0
    try:
        for zweig, titel in (("linienlager", "Neu: Linienlager"), ("flaechenlager", "Neu: Flächenlager")):
            w._baum_bearbeiten(zweig, {"linienlager": "Linienlager", "flaechenlager": "Flächenlager"}[zweig])
            w._baum_neu(zweig)
            _ruhe(app)
            mk = _maske(w)
            check(f"„Neu“ am Zweig „{titel[5:]}“: rechts die Maske „{titel} …“, kein modaler Dialog, "
                  "auch ohne Auswahl", mk is not None and mk.titel.startswith(titel) and not modal
                  and not w.fehler_liste, f"{getattr(mk, 'titel', None)} {modal} {w.fehler_liste[:1]}")
            w.maskenrand.schliessen()
            _ruhe(app)
    finally:
        dg.SupportNonlinearDialog.exec = alt


# ---------------------------------------------------------------------------
# Punkt 5: Flaechenlager anlegen
# ---------------------------------------------------------------------------
def test_flaechenlager_anlegen():
    w, app = _fenster()
    _modell(w, app)
    w.sel_flaechen = ["F1"]
    w.add_surface_support()
    _ruhe(app)
    mk = _maske(w)
    check("„Neues Flächenlager“ öffnet die Maske mit dem Feld „Flächen“ (die gewählte F1 schon darin)",
          mk is not None and mk.titel.startswith("Neu: Flächenlager") and mk.werte().get("flaechen") == "F1",
          f"{getattr(mk, 'titel', None)} {w.fehler_liste[:1]}")
    if mk is None:
        return
    mk.setzen("flaechen", "")
    w._maskenfeld_fokus(mk, "flaechenlager_einzeln", "flaechen")
    mk.objekt_angeklickt("flaeche", "F1")
    check("… F1 in der Ansicht angeklickt steht im Feld", mk.werte().get("flaechen") == "F1")
    mk.anwenden()
    _ruhe(app)
    fl = w.model.surface_supports
    check("… OK legt das Flächenlager auf F1 an: vier Knoten mit je 3 m² (4 m × 3 m)",
          len(fl) == 1 and fl[0].flaechen == ["F1"] and fl[0].nodes == [0, 1, 2, 3]
          and all(abs(a - 3.0) < 1e-9 for a in fl[0].areas), str([(x.flaechen, x.nodes, x.areas) for x in fl]))
    check("… keine Fehlermeldung „Keine Elemente angegeben“", not w.fehler_liste, str(w.fehler_liste[:2]))
    w.undo()
    _ruhe(app)
    check("… Rückgängig nimmt es zurück", not w.model.surface_supports)
    w.add_surface_support()
    _ruhe(app)
    mk = _maske(w)
    mk.setzen("flaechen", "F9")
    mk.anwenden()
    _ruhe(app)
    check("Eine unbekannte Fläche wird abgewiesen, nichts angelegt, kein leerer Rückgängig-Schritt",
          not w.model.surface_supports and any("F9" in str(x) for x in w.fehler_liste),
          str(w.fehler_liste[-1:]))
    w.maskenrand.schliessen()


# ---------------------------------------------------------------------------
# Punkt 9: Lagermomente
# ---------------------------------------------------------------------------
def test_lagermomente():
    """Kragarm 4 m, eingespannt an K0, F_z = -10 kN an K1: die Einspannung traegt
    R_z = 10 kN und M_y = ±40 kNm. Der Ergebnisbaum nennt beide (vorher gar keine
    Lagerreaktionen), die Tabelle hat M_x, M_y, M_z."""
    import numpy as np
    from statik3d import solver
    from statik3d.model import Material, Section
    w, app = _fenster()
    w.new_model()
    m = w.model
    m.add_material(Material.steel(MAT))
    m.add_section(Section.from_profile(SEC))
    m.add_node(0, 0, 0)
    m.add_node(4, 0, 0)
    w._maske_stab_anlegen({"knoten": [0, 1], "mat": MAT, "sec": SEC})
    m.support(0, [0, 1, 2, 3, 4, 5])
    m.load_node(1, case=m.active_case, Fz=-10e3)
    w.refresh_all()
    _ruhe(app)
    an = solver.solve_all(m, design=False)
    w._solve_done("all", an)
    _ruhe(app)
    huelle = {z[0]: z for z in w._ergebnisliste().get("Lagerreaktionen", [])}
    check("Zur Umhüllenden (min und max je Komponente): „Lagerreaktionen“ mit R_z und M_y = −40 kNm",
          "R_z" in huelle and huelle.get("M_y", ("", ""))[1].startswith("-40"), str(list(huelle.values())))
    w.ergebnis_zeigen(f"case:{m.active_case}")
    _ruhe(app)
    erg = w._ergebnisliste()
    zeilen = {z[0]: z for z in erg.get("Lagerreaktionen", [])}
    check("Ergebnisbaum (Lastfall): Gruppe „Lagerreaktionen“ mit R_z und M_y",
          "R_z" in zeilen and "M_y" in zeilen, str(list(erg)))
    my = zeilen.get("M_y", ("", ""))[1]
    rz = zeilen.get("R_z", ("", ""))[1]
    R = np.asarray(w.current_result().reactions)[0] / 1e3
    check("… M_y nennt das Einspannmoment −40 kNm (ein Lagerknoten: ein Wert, Einheit kNm)",
          my.startswith("-40") and "…" not in my and my.endswith(" kNm") and abs(R[4] + 40.0) < 1e-6,
          f"{my} / R = {R.round(3).tolist()}")
    check("… R_z nennt +10 kN", rz.startswith("+10") and rz.endswith(" kN"), rz)
    check("… und nur Komponenten, die nicht null sind (kein M_x, kein R_x)",
          "M_x" not in zeilen and "R_x" not in zeilen, str(list(zeilen)))
    w.ergebnis_zeigen(zeilen["M_y"][2] if "M_y" in zeilen else "lager:4")
    _ruhe(app)
    tu = w.tab_unten
    check("… ein Klick zeigt unten die Tabelle „Auflagerkräfte“",
          tu.tabText(tu.currentIndex()) == "Auflagerkräfte", tu.tabText(tu.currentIndex()))
    kopf = [s.name for s in w._auflager_spalten(False)]
    check("… und die hat die Spalten Mx, My, Mz", {"Mx", "My", "Mz"} <= set(kopf), str(kopf))


# ---------------------------------------------------------------------------
# Punkt 8: Stellungen anzeigen
# ---------------------------------------------------------------------------
def test_stellung_anzeigen():
    """Klick auf eine Stellung im Baum: das Bild zeigt die bewegten Teile in
    ihrer Lage, die Grundstellung blass dahinter; „Grundstellung zeigen“ in der
    Glasleiste schaltet zurueck. Das Modell bleibt unberuehrt."""
    import numpy as np
    from statik3d.bridges.positions import Stellung
    w, app = _fenster()
    m = _modell(w, app)
    m.support(0, [0, 1, 2])
    m.stellungen.append(Stellung("St1", verschiebung=(0.0, 0.0, 1.0)))
    w.refresh_all()
    _ruhe(app)
    vorher = np.array(m.nodes, float)
    a = getattr(w, "act_grundstellung", None)
    knopf = w.glasleiste.knoepfe.get("grundstellung")
    check("Glasleiste: Knopf „Grundstellung zeigen“ - ohne Stellung im Bild weg und gesperrt",
          a is not None and knopf is not None and not a.isEnabled() and not knopf.isVisibleTo(w.glasleiste),
          str(getattr(a, "isEnabled", lambda: None)()))
    w._baum_geklickt("stellung", "St1")
    _ruhe(app)
    am = w._anzeigemodell()
    dz = np.asarray(am.nodes, float)[:, 2] - vorher[:, 2]
    check("Klick auf „St1“: das Bild zeigt K1 bis K3 um 1 m gehoben, K0 (Knotenlager) bleibt",
          am is not w.model and np.allclose(dz, [0.0, 1.0, 1.0, 1.0]), str(dz.tolist()))
    check("… das Modell selbst bleibt, wie es war", np.array_equal(np.asarray(w.model.nodes, float), vorher))
    namen = set(w.plotter.actors) if hasattr(w.plotter, "actors") else set()
    check("… die Grundstellung steht blass dahinter", "stellung_grund" in namen
          or "stellung_grund_linien" in namen, str(sorted(n for n in namen if "stellung" in n)))
    check("… und der Knopf „Grundstellung zeigen“ steht in der Glasleiste und ist frei",
          a is not None and a.isEnabled() and knopf.isVisibleTo(w.glasleiste))
    netze, _aus = w._netze_bauen(am, None, w.darstellung)
    pz = [float(np.max(n.points[:, 2])) for n, _kn, _nm in netze if n.n_points]
    # Stab E0 von K0 (bleibt) nach K2 (+1 m), als Profilkoerper HEB 300 (halbe Hoehe 0,15 m)
    check("… das gezeichnete Netz liegt in der Stellung: der Stab reicht bis über z = 1 m",
          pz and 1.0 < max(pz) < 1.2, str(pz))
    if a is not None:
        a.trigger()
        _ruhe(app)
    namen = set(w.plotter.actors) if hasattr(w.plotter, "actors") else set()
    netze, _aus = w._netze_bauen(w._anzeigemodell(), None, w.darstellung)
    pz = [float(np.max(n.points[:, 2])) for n, _kn, _nm in netze if n.n_points]
    check("… und das Netz wieder in der Grundstellung (oberster Punkt die Profiloberkante 0,15 m)",
          pz and max(pz) < 0.2, str(pz))
    check("„Grundstellung zeigen“: wieder das Modell im Bild, ohne blasse Grundstellung, Knopf gesperrt",
          w._anzeigemodell() is w.model and "stellung_grund" not in namen
          and "stellung_grund_linien" not in namen and a is not None and not a.isEnabled()
          and not knopf.isVisibleTo(w.glasleiste))
    w.maskenrand.schliessen()


def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Klicken statt Abtippen")
    check("Handbuch: Klicken statt Abtippen, „Neu …“ in der Maske, „+ … anlegen“, Linien- und Flächenlager",
          "Ansicht" in a and "Neu:" in a and "+ … anlegen" in a and "Flächenlager" in a, a[:80])


def main():
    for t in (test_klicken_statt_abtippen, test_neu_in_der_maske, test_baum_lager_und_anlegen,
              test_flaechenlager_anlegen, test_lagermomente, test_stellung_anzeigen, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    w = _FENSTER.get("w")
    if w is not None:
        w.close()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
