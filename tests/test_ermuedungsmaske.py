"""
Maske „Ermüdungslasten (Lastkollektiv)“ - die rechte Maske statt des modalen
Dialogs (Entwurf vom 24.09.2026, vom Anwender freigegeben).

Der alte Dialog konnte nur neu anlegen, nannte das Zaehlverfahren roh
(„spanne/rainflow/reservoir“), kannte das Wort Palmgren-Miner nicht und
ueberschrieb einen doppelten Namen still. Hier wird die Maske selbst geprueft
(offscreen, ohne Hauptfenster) und das Hauptfenster ueber seine Methoden mit
einer Attrappe fuer self - wie in tests/test_ermuedung_verlauf.py.

Aufruf:  python -m tests.test_ermuedungsmaske
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from statik3d.model import Model, Material, FatigueLoad, Joint  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402
from statik3d import mesher, solver  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _em():
    """Das Modul der Maske - fehlt es (alter Stand), reisst der Test hier."""
    import importlib
    return importlib.import_module("statik3d.gui.ermuedungsmaske")


def _kragarm():
    """IPE 200, 2 m, drei Lastfaelle mit Einzellast an der Spitze, dazu eine
    oder-verknuepfte Kombination (hat kein Einzelergebnis)."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (2, 0, 0), 4)
    m.fix(ids[0], [0, 1, 2, 3, 4, 5])
    m.case().category = "G"
    m.load_node(ids[-1], Fz=-10000.0)
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fz=-25000.0)
    m.add_load_case("LF3", "Q")
    m.load_node(ids[-1], Fz=-5000.0)
    m.add_member("Kragarm", list(range(4)), detail_category=71e6)
    k = m.add_combination("EK_oder", {}, "FAT")
    k.alternativen = [{"LF1": 1.0}, {"LF2": 1.0}]
    return m


def _mit_lasten():
    m = _kragarm()
    m.add_fatigue_load("Oben", "LF2", "LF3", cycles=2e6)
    m.add_fatigue_load("Global", "LF1", None, cycles=None)
    m.fatigue_loads["Folge"] = FatigueLoad("Folge", folge=["LF1", "LF2", "LF1"],
                                           wiederholungen=5e5, zaehlung="rainflow", factor=1.2)
    return m


class _Protokoll:
    """Haken fuer Aenderungen: zaehlt, was die Maske ueber aendern() schreibt."""

    def __init__(self):
        self.was = []

    def __call__(self, was, fn):
        self.was.append(was)
        return fn()


def _maske(m, **kw):
    _app()
    em = _em()
    haken = _Protokoll()
    mk = em.Ermuedungsmaske(lambda: m, aendern=haken, **kw)
    return mk, haken


def _zellen(mk):
    t = mk.tabelle
    return [[(t.item(r, c).text() if t.item(r, c) else "") for c in range(t.columnCount())]
            for r in range(t.rowCount())]


# --------------------------------------------------------------------------
def test_tabelle_listet_lasten():
    m = _mit_lasten()
    mk, _ = _maske(m)
    z = _zellen(mk)
    check("Maske listet alle Ermüdungslasten, eine Zeile je Last, in Modellreihenfolge",
          [r[0] for r in z] == ["Oben", "Global", "Folge"], str([r[0] for r in z]))
    kopf = [mk.tabelle.horizontalHeaderItem(c).text() for c in range(mk.tabelle.columnCount())]
    check("Spalten: Name, Art, Zustand/Verlauf, unterer Zustand, n, Zählverfahren, Schwingbeiwert",
          len(kopf) == 7 and kopf[0] == "Name" and "Schwingbeiwert" in kopf[6]
          and "Zählverfahren" in kopf[5], str(kopf))
    check("Art im Klartext: zwei Zustände / Verlauf",
          z[0][1] == "zwei Zustände" and z[2][1] == "Verlauf", f"{z[0][1]!r}, {z[2][1]!r}")
    check("unterer Zustand leer heißt „Nullzustand“", z[1][3] == "Nullzustand", z[1][3])
    check("Verlauf: Komma-Liste der Glieder", z[2][2] == "LF1, LF2, LF1", z[2][2])
    check("Lastspiele ohne wissenschaftliche Schreibweise: „2 000 000“",
          z[0][4] == "2 000 000", z[0][4])
    check("globale Lastspielzahl: „global (2 000 000)“", z[1][4] == "global (2 000 000)", z[1][4])
    check("kein „e+“ in irgendeiner Zelle", not any("e+" in c or "e6" in c for r in z for c in r),
          str([c for r in z for c in r if "e+" in c]))
    check("Kopfzeile nennt Palmgren-Miner und D = Σ nᵢ / Nᵢ",
          "Palmgren-Miner" in mk.lbl_miner.text() and "Σ nᵢ / Nᵢ" in mk.lbl_miner.text()
          and "D ≤ 1" in mk.lbl_miner.text(), mk.lbl_miner.text()[:80])
    check("Hinweis: Reihenfolge nur Anzeige, Summe hängt nicht daran",
          "Reihenfolge" in mk.lbl_reihenfolge.text(), mk.lbl_reihenfolge.text())


def test_zeile_bearbeiten_und_felder():
    from PySide6 import QtWidgets
    m = _mit_lasten()
    mk, _ = _maske(m, auswahl="Oben")
    check("Auswahl beim Öffnen: Zeile „Oben“ im Editor",
          mk.name.text() == "Oben" and mk.tabelle.currentRow() == 0, mk.name.text())
    check("eigenes n im Feld ohne e+06: „2 000 000“", mk.n.text() == "2 000 000", mk.n.text())
    check("oberer/unterer Zustand geladen",
          mk.oben.currentData() == "LF2" and mk.unten.currentData() == "LF3",
          f"{mk.oben.currentData()} / {mk.unten.currentData()}")
    oben = [mk.oben.itemData(i) for i in range(mk.oben.count())]
    unten = [mk.unten.itemText(i) for i in range(mk.unten.count())]
    check("oberer Zustand: Lastfälle, keine oder-EK", "EK_oder" not in oben
          and {"LF1", "LF2", "LF3"} <= set(oben), str(oben))
    check("unterer Zustand: „Nullzustand“ zuerst, keine oder-EK",
          unten[:1] == ["Nullzustand"] and "EK_oder" not in unten, str(unten))
    mk.zeile_waehlen("Global")
    check("globale Zeile: Haken an, Beschriftung nennt n = 2 000 000",
          mk.global_n.isChecked() and "2 000 000" in mk.global_n.text()
          and "e+" not in mk.global_n.text(), mk.global_n.text())
    mk.zeile_waehlen("Folge")
    check("Verlauf: Feld heißt „Durchläufe des Verlaufs“",
          "Durchläufe des Verlaufs" in mk.lbl_n.text() and mk.n.text() == "500 000",
          f"{mk.lbl_n.text()!r} {mk.n.text()!r}")
    check("Beiwert heißt „Schwingbeiwert / dynamischer Faktor“",
          "Schwingbeiwert / dynamischer Faktor" in mk.lbl_faktor.text(), mk.lbl_faktor.text())
    em = _em()
    texte = [mk.zaehlung.itemText(i) for i in range(mk.zaehlung.count())]
    daten = [mk.zaehlung.itemData(i) for i in range(mk.zaehlung.count())]
    from statik3d.model import ZAEHLVERFAHREN_TEXT
    check("Zählverfahren im Klartext, interne Werte bleiben",
          daten == ["spanne", "rainflow", "reservoir"]
          and texte == [ZAEHLVERFAHREN_TEXT[d] for d in daten]
          and texte[0].startswith("Größte Spanne je Durchlauf")
          and texte[1].startswith("Rainflow-Zählung"), str(texte))
    check("Verlauf „Folge“ steht auf rainflow", mk.zaehlung.currentData() == "rainflow",
          str(mk.zaehlung.currentData()))
    check("Tooltip des Zählverfahrens erklärt, wann welches passt",
          "Zeitfolge" in mk.zaehlung.toolTip() and "RFEM" in mk.zaehlung.toolTip(),
          mk.zaehlung.toolTip()[:60])
    check("Tabelle zeigt das Zählverfahren im Klartext",
          _zellen(mk)[2][5] == ZAEHLVERFAHREN_TEXT["rainflow"], _zellen(mk)[2][5])
    check("Lastspiele lesen: 2e6, 2000000, „2 000 000“, 1,5e5",
          em.lastspiele_lesen("2e6") == 2e6 and em.lastspiele_lesen("2000000") == 2e6
          and em.lastspiele_lesen("2 000 000") == 2e6
          and em.lastspiele_lesen("2 000 000") == 2e6
          and em.lastspiele_lesen("1,5e5") == 1.5e5)
    check("Lastspiele schreiben: 2e6 → „2 000 000“, 1,5 → „1,5“",
          em.lastspiele_text(2e6) == "2 000 000" and em.lastspiele_text(1.5) == "1,5",
          f"{em.lastspiele_text(2e6)!r} {em.lastspiele_text(1.5)!r}")
    check("Lastspielfeld ist ein Textfeld (nimmt „2 000 000“ an, ein Zahlvalidator nicht)",
          isinstance(mk.n, QtWidgets.QLineEdit) and mk.n.validator() is None)


def test_verlauf_liste_und_text_gekoppelt():
    m = _mit_lasten()
    mk, _ = _maske(m)
    mk.neue_zeile()
    mk.art.setCurrentIndex(mk.art.findData("verlauf"))
    verf = [mk.verfuegbar.item(i).text() for i in range(mk.verfuegbar.count())]
    check("links: verfügbare Zustände ohne oder-EK", "EK_oder" not in verf
          and {"LF1", "LF2", "LF3"} <= set(verf), str(verf))
    for name in ("LF1", "LF2", "LF1"):
        mk.verfuegbar.setCurrentRow(verf.index(name))
        mk.anfuegen()
    check("anfügen → schreibt die Komma-Liste", mk.folge_text.text() == "LF1, LF2, LF1",
          mk.folge_text.text())
    mk.verlauf.setCurrentRow(1)
    mk.verlauf_runter()
    check("↓ verschiebt im Verlauf, Text folgt", mk.folge_text.text() == "LF1, LF1, LF2",
          mk.folge_text.text())
    mk.verlauf.setCurrentRow(0)
    mk.entfernen()
    check("← entfernen, Text folgt", mk.folge_text.text() == "LF1, LF2", mk.folge_text.text())
    # Doppelklick links fuegt an
    mk.verfuegbar.itemDoubleClicked.emit(mk.verfuegbar.item(verf.index("LF3")))
    check("Doppelklick links fügt an", mk.folge_text.text() == "LF1, LF2, LF3", mk.folge_text.text())
    # Text -> Liste, unbekannte Namen rot
    mk.folge_text.setText("LF3, XY, LF1")
    mk.folge_text.textEdited.emit("LF3, XY, LF1")
    liste = [mk.verlauf.item(i).text() for i in range(mk.verlauf.count())]
    check("Text → Liste", liste == ["LF3", "XY", "LF1"], str(liste))
    rot = [mk.verlauf.item(i).foreground().color().name() for i in range(mk.verlauf.count())]
    check("unbekannter Name rot markiert (Liste und Textfeld)",
          rot[1] != rot[0] and "XY" in mk.lbl_folge.text() and mk.folge_text.property("fehler"),
          f"{rot}, {mk.lbl_folge.text()!r}")
    mk.folge_text.setText("LF3, LF1")
    mk.folge_text.textEdited.emit("LF3, LF1")
    check("… wieder bekannt: keine Markierung", not mk.folge_text.property("fehler")
          and "unbekannt" not in mk.lbl_folge.text(), mk.lbl_folge.text())


def test_uebernehmen_pruefungen():
    m = _mit_lasten()
    vorher = {k: (v.case_max, v.case_min, v.cycles, v.factor, list(v.folge))
              for k, v in m.fatigue_loads.items()}

    def stand():
        return {k: (v.case_max, v.case_min, v.cycles, v.factor, list(v.folge))
                for k, v in m.fatigue_loads.items()}

    mk, haken = _maske(m)
    # doppelter Name
    mk.neue_zeile()
    mk.name.setText("Oben")
    mk.oben.setCurrentIndex(mk.oben.findData("LF1"))
    mk.anwenden()
    check("doppelter Name abgewiesen, nichts überschrieben",
          stand() == vorher and "gibt es schon" in mk.lbl_meldung.text() and not haken.was,
          mk.lbl_meldung.text())
    # Name leer
    mk.name.setText("  ")
    mk.anwenden()
    check("leerer Name abgewiesen", stand() == vorher and "Name" in mk.lbl_meldung.text(),
          mk.lbl_meldung.text())
    # n <= 0
    mk.name.setText("Neu")
    mk.global_n.setChecked(False)
    for t in ("0", "-5"):
        mk.n.setText(t)
        mk.anwenden()
        check(f"n = {t} abgewiesen", stand() == vorher and "größer als null" in mk.lbl_meldung.text(),
              mk.lbl_meldung.text())
    mk.n.setText("abc")
    mk.anwenden()
    check("n unlesbar abgewiesen", stand() == vorher and mk.lbl_meldung.text(), mk.lbl_meldung.text())
    mk.n.setText("1e5")
    mk.faktor.setText("0")
    mk.anwenden()
    check("Schwingbeiwert 0 abgewiesen", stand() == vorher and "Schwingbeiwert" in mk.lbl_meldung.text(),
          mk.lbl_meldung.text())
    mk.faktor.setText("1,1")
    # oberer Zustand fehlt
    mk.oben.setCurrentIndex(-1)
    mk.anwenden()
    check("zwei Zustände ohne oberen Zustand abgewiesen",
          stand() == vorher and "oberer Zustand" in mk.lbl_meldung.text(), mk.lbl_meldung.text())
    # Verlauf: <2, unbekannt, oder-EK
    mk.art.setCurrentIndex(mk.art.findData("verlauf"))
    for text, erwartet in (("LF1", "mindestens zwei"), ("LF1, WEG", "nicht gibt"),
                           ("LF1, EK_oder", "oder-verknüpfte")):
        mk.folge_text.setText(text)
        mk.folge_text.textEdited.emit(text)
        mk.anwenden()
        check(f"Verlauf „{text}“ abgewiesen ({erwartet})",
              stand() == vorher and erwartet in mk.lbl_meldung.text(), mk.lbl_meldung.text())
    # gueltig: Verlauf mit eigenem n
    mk.folge_text.setText("LF1, LF2, LF3")
    mk.folge_text.textEdited.emit("LF1, LF2, LF3")
    mk.zaehlung.setCurrentIndex(mk.zaehlung.findData("reservoir"))
    mk.n.setText("2 000 000")
    mk.anwenden()
    fl = m.fatigue_loads.get("Neu")
    check("gültiger Verlauf übernommen: Folge, Wiederholungen, Zählung, Beiwert",
          fl is not None and fl.folge == ["LF1", "LF2", "LF3"] and fl.wiederholungen == 2e6
          and fl.zaehlung == "reservoir" and abs(fl.factor - 1.1) < 1e-12,
          "fehlt" if fl is None else f"{fl}")
    check("… beim Verlauf landet n nicht in cycles, case_max leer",
          fl is not None and fl.cycles is None and fl.case_max == "" and fl.case_min is None,
          "" if fl is None else f"cycles {fl.cycles}, case_max {fl.case_max!r}")
    check("… über den Rückgängig-Haken (merken) geschrieben",
          haken.was and "Neu" in haken.was[-1], str(haken.was))
    check("… die Tabelle zeigt die neue Zeile", [r[0] for r in _zellen(mk)][-1] == "Neu",
          str([r[0] for r in _zellen(mk)]))
    # zwei Zustaende, bearbeiten einer vorhandenen Zeile
    mk.zeile_waehlen("Oben")
    mk.global_n.setChecked(True)
    mk.faktor.setText("1,3")
    mk.anwenden()
    fo = m.fatigue_loads["Oben"]
    check("vorhandene Zeile bearbeitet: global, Beiwert 1,3, Zustände bleiben",
          fo.cycles is None and abs(fo.factor - 1.3) < 1e-12 and fo.case_max == "LF2"
          and fo.case_min == "LF3", str(fo))


def test_umbenennen_zieht_anschluesse_nach():
    m = _mit_lasten()
    m.joints["K1"] = Joint("K1", ermuedung=["Oben", "Folge"])
    m.joints["K2"] = Joint("K2", ermuedung=[])
    mk, haken = _maske(m, auswahl="Oben")
    mk.name.setText("Oben2")
    mk.anwenden()
    check("Umbenennen: alte Zeile weg, neue an derselben Stelle",
          list(m.fatigue_loads) == ["Oben2", "Global", "Folge"], str(list(m.fatigue_loads)))
    check("Joint.ermuedung zieht nach", m.joints["K1"].ermuedung == ["Oben2", "Folge"],
          str(m.joints["K1"].ermuedung))
    check("leere Liste (= alle) bleibt leer", m.joints["K2"].ermuedung == [],
          str(m.joints["K2"].ermuedung))
    mk.name.setText("Folge")
    mk.anwenden()
    check("Umbenennen auf vorhandenen Namen abgewiesen",
          list(m.fatigue_loads) == ["Oben2", "Global", "Folge"]
          and "gibt es schon" in mk.lbl_meldung.text(), mk.lbl_meldung.text())


def test_zeile_je_lastfall_und_reihenfolge():
    # Eine vorhandene Zeile „LF1 gegen Nullzustand“ bekommt keine zweite -
    # sie zaehlte die Schaedigung von LF1 doppelt
    m = _mit_lasten()
    mk, haken = _maske(m)
    n0 = len(m.fatigue_loads)
    neu = mk.zeilen_je_lastfall(["LF1"])
    check("LF1 hat schon die Zeile „Global“ gegen Null: keine zweite, Meldung nennt sie",
          not neu and len(m.fatigue_loads) == n0 and "Global" in mk.lbl_meldung.text()
          and not haken.was, mk.lbl_meldung.text())
    m = _kragarm()
    m.add_fatigue_load("Oben", "LF2", "LF3", cycles=2e6)
    m.fatigue_loads["Folge"] = FatigueLoad("Folge", folge=["LF1", "LF2", "LF1"], wiederholungen=5e5)
    m.add_fatigue_load("Global", "LF1", "LF2", cycles=None)
    mk, haken = _maske(m)
    mk.btn_je_lastfall.click()
    angebot = [mk.je_lastfall_liste.item(i).text() for i in range(mk.je_lastfall_liste.count())]
    check("„Zeile je Lastfall…“ bietet die Zustände ohne oder-EK an",
          "EK_oder" not in angebot and {"LF1", "LF2", "LF3"} <= set(angebot)
          and not mk.je_lastfall_panel.isHidden(), str(angebot))
    n0 = len(m.fatigue_loads)
    neu = mk.zeilen_je_lastfall(["LF1", "LF2", "LF3"])
    fl = [m.fatigue_loads[n] for n in neu]
    check("drei Lastfälle → drei Zeilen", len(m.fatigue_loads) == n0 + 3 and len(neu) == 3,
          str(list(m.fatigue_loads)))
    check("je Zeile: oben = Lastfall, unten = Nullzustand, n = global",
          [f.case_max for f in fl] == ["LF1", "LF2", "LF3"]
          and all(f.case_min is None and f.cycles is None and not f.folge for f in fl),
          str([(f.name, f.case_max, f.case_min, f.cycles) for f in fl]))
    check("… mit einem Rückgängig-Schritt", len(haken.was) == 1, str(haken.was))
    nochmal = mk.zeilen_je_lastfall(["LF1", "LF2"])
    check("zweimal: keine doppelten Zeilen", not nochmal and len(m.fatigue_loads) == n0 + 3,
          str(list(m.fatigue_loads)))
    mk.zeile_waehlen("Folge")
    mk.zeile_hoch()
    check("↑ ändert nur die Reihenfolge", list(m.fatigue_loads)[:3] == ["Folge", "Oben", "Global"]
          and len(m.fatigue_loads) == n0 + 3, str(list(m.fatigue_loads)))
    mk.zeile_runter()
    check("↓ zurück", list(m.fatigue_loads)[:3] == ["Oben", "Folge", "Global"],
          str(list(m.fatigue_loads)))
    mk.zeile_waehlen("Global")
    mk.zeile_loeschen()
    check("Zeile löschen", "Global" not in m.fatigue_loads, str(list(m.fatigue_loads)))


def test_bericht_klartext():
    from statik3d.report.html import Report
    from statik3d.model import ZAEHLVERFAHREN_TEXT
    m = _mit_lasten()
    an = solver.solve_all(m, design=False, fatigue=True)
    html = Report(m, an).html()
    check("Bericht: Zählverfahren im Klartext der Maske",
          ZAEHLVERFAHREN_TEXT["rainflow"] in html, "")
    check("Bericht: nicht mehr roh „rainflow“ in der Tabelle",
          "<td>rainflow</td>" not in html, "")


def test_miner_summe_zweier_zeilen():
    """Sicherung: die Rechnung bleibt unveraendert - D zweier Zeilen am Stab
    ist die Summe der Einzelrechnungen (Palmgren-Miner am selben Ort)."""
    m = _kragarm()
    m.add_fatigue_load("A", "LF2", None, cycles=1e5)
    m.add_fatigue_load("B", "LF1", None, cycles=3e5)
    D = solver.solve_all(m, design=False, fatigue=True).fatigue.members["Kragarm"].D
    einzeln = []
    for name in ("A", "B"):
        m2 = _kragarm()
        f = m.fatigue_loads[name]
        m2.add_fatigue_load(name, f.case_max, None, cycles=f.cycles)
        einzeln.append(solver.solve_all(m2, design=False, fatigue=True).fatigue.members["Kragarm"].D)
    check("Miner: D(A+B) = D(A) + D(B) am Stab",
          D > 0 and abs(D - sum(einzeln)) <= 1e-12 * D, f"{D:.6g} = {einzeln[0]:.6g} + {einzeln[1]:.6g}")


def _gui():
    import importlib
    return importlib.import_module("statik3d.gui.main")


def test_modellbaum_und_hauptfenster():
    _app()
    from statik3d.gui import design as dsg
    G = _gui()
    m = _mit_lasten()
    baum = dsg.Modellbaum()
    baum.fuellen(m)
    from PySide6 import QtCore
    knoten = baum.findItems("Ermüdungslasten", QtCore.Qt.MatchRecursive)
    zweig = knoten[0] if knoten else None
    kinder = [] if zweig is None else [baum._schluessel(zweig.child(i)) for i in range(zweig.childCount())]
    check("Modellbaum: Knoten „Ermüdungslasten“ mit einem Eintrag je Last",
          zweig is not None and baum._schluessel(zweig)[0] == "ermuedungslasten"
          and [k for k in kinder if k[0] == "ermuedungslast"] ==
          [("ermuedungslast", n) for n in ("Oben", "Global", "Folge")], str(kinder))
    check("… Neu/Löschen im Kontextmenü",
          "ermuedungslasten" in baum.NEU_ARTEN and "ermuedungslast" in baum.LOESCH_ARTEN
          and baum.ELTERNART.get("ermuedungslast") == "ermuedungslasten")
    # Klick oeffnet die Maske mit dieser Zeile
    aufrufe = []
    s = types.SimpleNamespace(model=m, SYSTEM_ARTEN=G.MainWindow.SYSTEM_ARTEN,
                              maske_ermuedungslasten=lambda *a, **k: aufrufe.append((a, k)))
    s._baum_system_geklickt = lambda a, n: G.MainWindow._baum_system_geklickt(s, a, n)
    G.MainWindow._baum_geklickt(s, "ermuedungslast", "Global")
    check("Klick auf den Eintrag öffnet die Maske mit dieser Zeile",
          aufrufe and ("Global" in aufrufe[-1][0] or aufrufe[-1][1].get("name") == "Global"),
          str(aufrufe))
    G.MainWindow._baum_neu(s, "ermuedungslasten")
    check("„Neu“ am Zweig öffnet die Maske mit neuer Zeile",
          len(aufrufe) == 2 and aufrufe[-1][1].get("neu") is True, str(aufrufe))
    # Das Hauptfenster baut die Maske und schreibt ueber merken/refresh_all
    protokoll = []
    s2 = types.SimpleNamespace(model=m, merken=lambda was: protokoll.append(("merken", was)),
                               refresh_all=lambda: protokoll.append(("refresh", "")),
                               maske_erzeugen=lambda mk, fokus=True: mk,
                               log=types.SimpleNamespace(appendPlainText=lambda t: None))
    s2._ermuedung_aendern = lambda was, fn: G.MainWindow._ermuedung_aendern(s2, was, fn)
    mk = G.MainWindow.maske_ermuedungslasten(s2, "Global")
    check("Hauptfenster: Maske mit der Zeile „Global“", mk is not None and mk.name.text() == "Global",
          "" if mk is None else mk.name.text())
    mk.name.setText("Global2")
    mk.anwenden()
    check("… Übernehmen: merken vor der Änderung, danach refresh_all",
          [p[0] for p in protokoll] == ["merken", "refresh"] and "Global2" in m.fatigue_loads,
          str(protokoll))
    # Loeschen aus dem Baum
    s3 = types.SimpleNamespace(model=m, merken=lambda was: None, refresh_all=lambda: None,
                               _bestaetigen=lambda t: True, info=lambda t: None,
                               log=types.SimpleNamespace(appendPlainText=lambda t: None),
                               statusBar=lambda: types.SimpleNamespace(showMessage=lambda *a: None))
    try:
        G.MainWindow._baum_loeschen(s3, "ermuedungslast", "Folge")
    except AttributeError as ex:      # die Attrappe kennt nicht alles, was danach kommt
        print("   (Attrappe:", ex, ")")
    check("Baum „Löschen“ nimmt die Ermüdungslast heraus", "Folge" not in m.fatigue_loads,
          str(list(m.fatigue_loads)))
    # Quelltext: Ribbon und Register oeffnen die Maske, der alte Dialog ist weg
    quelle = open(G.__file__, encoding="utf-8").read()
    check("Ribbon „Ermüdungslasten…“ öffnet die Maske",
          'g.klein("Ermüdungslasten…", self.maske_ermuedungslasten' in quelle)
    check("der alte FatigueLoadDialog ist aus der Oberfläche verschwunden",
          "FatigueLoadDialog" not in quelle)
    dq = open(os.path.join(os.path.dirname(G.__file__), "dialogs.py"), encoding="utf-8").read()
    check("Konfiguration Nachweise nennt die Maske Ermüdungslasten",
          "Maske Ermüdungslasten" in dq and "Dialog Ermüdungslast" not in dq)


def main():
    for t in (test_tabelle_listet_lasten, test_zeile_bearbeiten_und_felder,
              test_verlauf_liste_und_text_gekoppelt, test_uebernehmen_pruefungen,
              test_umbenennen_zieht_anschluesse_nach, test_zeile_je_lastfall_und_reihenfolge,
              test_bericht_klartext, test_miner_summe_zweier_zeilen,
              test_modellbaum_und_hauptfenster):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
