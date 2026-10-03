"""
Unterer Bereich in einer Kopfzeile (Teilpaket 10b des Oberflaechenplans, 03.10.2026).

Befund am Stand 5734a94 (offscreen mit nachgeladener Segoe UI gemessen,
scratchpad/mit_schrift.py; Beispiel hall gerechnet, eine Kombination gezeigt):
unten standen untereinander die Gruppenleiste, die Register der Gruppe, eine
Werkzeugzeile je Tabelle (Zeilenzahl, Spalten…, Filter leeren, Kopieren, CSV…,
Excel…), die Filterzeile und unter jeder Tabelle mit Kennwerten die Zeilen Max
und Min - auch unter den Eingabetabellen Knoten, Stäbe, Flächen, Volumenkörper
und Schweißnähte. Von 270 px unten bei 1920 x 1080 blieben der Knotentabelle
78 px (2 Zeilen), den Stabkräften 108 px (3 Zeilen); in der Kompaktstufe
(aufgeklappt) 68 und 98 px, und der Inhalt war dort 260 px hoch in 217 px -
von Max/Min der Stabkräfte waren 3 von 46 px zu sehen.

Offscreen ohne nachgeladene Schrift malt Qt Kaestchen, etwa doppelt so breit
wie Segoe UI (Regel Block C): die Suite waehlt ihre Werte vorher danach, ob Qt
eine Schrift kennt, und nennt Werte ohne Schrift „Kästchenwert“.

Geprueft wird:

* Gruppe (Aufklappfeld), Reiter und die Knoepfe Spalten, Filter, Kopieren,
  CSV und Excel stehen in **einer** Zeile; keine zweite Registerzeile;
* die Tabelle gewinnt Hoehe (gemessen gegen den Stand vor 10b);
* die Filterzeile kommt und geht auf Knopfdruck, ein wirkender Filter bleibt
  sichtbar und der Knopf sagt es, die Filtersprache bleibt;
* der Zaehler steht klein am Reiter (nicht im Text), leere Reiter sind grau
  mit mindestens 3 : 1 Kontrast, ein gewaehlter leerer Reiter ist erkennbar,
  der Zaehler fuellt keine wartende Tabelle und nennt bei ihr mit Filter keine
  falsche Zahl;
* eine leere Tabelle sagt, wie sie sich fuellt, und ihre Verweise
  („Register → Knopf“, „Knopf“) stehen genau so im Ribbon bzw. an der Tabelle;
* Max/Min nur an Ergebnis- und Nachweistabellen und erst ab 5 Zeilen, an einer
  echten Nachweistabelle mit 6 Zeilen;
* in der Kompaktstufe (1366 x 768, 1280 x 720) ist alles erreichbar und
  nichts gekuerzt, auch in der Gruppe Protokoll ohne Reiter.

Aufruf:  python -m tests.test_unten_kopfzeile
         (mit Schrift: python scratchpad/mit_schrift.py <Baum> tests.test_unten_kopfzeile)
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ.pop("STATIK3D_FENSTER", None)
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_unten_kopf_"), "einstellungen.json")

RESULTS = []
_F = {}

#: Was vor 10b (Stand 5734a94) von der Tabelle zu sehen war: (sichtbare Hoehe
#: der Tabelle [px], sichtbare Datenzeilen, sichtbare ganze Zeilen Max/Min).
#: Offscreen, Beispiel hall mit solve_all(design=True), erste Kombination,
#: Kompaktstufe aufgeklappt (anordnung.unten_einklappen(False)); derselbe
#: Ablauf wie _hoehen() unten (scratchpad/pruef_hoehen2.py, 03.10.2026).
#: Mit Segoe UI (scratchpad/mit_schrift.py): in der Kompaktstufe war der
#: Inhalt 260 px hoch im 217 px hohen Bereich - von Max/Min der Knoten waren
#: 33 von 46 px zu sehen, von denen der Stabkraefte 3.
VORHER_SCHRIFT = {
    (1920, 1080): {"Knoten": (78, 2, 2), "Stabkräfte": (108, 3, 2)},
    (1366, 768): {"Knoten": (68, 1, 1), "Stabkräfte": (98, 2, 0)},
    (1280, 720): {"Knoten": (68, 1, 1), "Stabkräfte": (98, 2, 0)},
}
#: Dasselbe ohne Schrift - Kaestchenwerte (am Stand 5ee513d und 5734a94 gleich
#: gemessen); der Bereich rollte dabei bei 1366 x 768 um 401 px, mit Segoe UI
#: rollte er nicht.
VORHER_KAESTCHEN = {
    (1920, 1080): {"Knoten": (94, 2, 2), "Stabkräfte": (120, 3, 2)},
    (1366, 768): {"Knoten": (68, 1, 0), "Stabkräfte": (91, 2, 0)},
    (1280, 720): {"Knoten": (68, 1, 0), "Stabkräfte": (91, 2, 0)},
}
#: Zeilenhoehe der Tabellen [px] (Datentabelle: verticalHeader 22 px)
ZEILE = 22
#: Gruppen, deren Tabellen Ergebnisse tragen - nur dort gibt es Max/Min
ERGEBNISGRUPPEN = ("Ergebnisse", "Nachweise")


def _mit_schrift() -> bool:
    """Kennt Qt eine Schrift? Offscreen ohne nachgeladene Schrift ist die Liste
    leer, und Qt malt Kaestchen statt Buchstaben."""
    from PySide6 import QtGui
    _app()
    return bool(QtGui.QFontDatabase.families())


def _kontrast(a, b) -> float:
    """Kontrastverhaeltnis zweier QColor nach WCAG (1 … 21)."""
    def lum(c):
        teile = []
        for x in (c.redF(), c.greenF(), c.blueF()):
            teile.append(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4)
        return 0.2126 * teile[0] + 0.7152 * teile[1] + 0.0722 * teile[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:88s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ruhe(n: int = 6):
    app = _app()
    for _ in range(n):
        app.processEvents()


def _fenster():
    if "w" in _F:
        return _F["w"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    _app()
    w = MainWindow()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler = []
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b): die
    # Liste bekommt beide, w.meldungen wertet sie getrennt aus
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler)
    w.info = lambda *a, **k: None
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    w.show()
    _ruhe()
    _F["w"] = w
    return w


def _groesse(w, b, h):
    w.resize(b, h)
    _ruhe(8)
    w.anordnung.zuruecksetzen()
    _ruhe(8)


def _hall(w):
    """Beispiel hall, gerechnet, eine Kombination gezeigt (wie VORHER)."""
    from statik3d import solver
    w.load_example("hall")
    _ruhe()
    an = solver.solve_all(w.model, design=True)
    w._solve_done("all", an)
    _ruhe()
    for idx in range(w.cb_result.count()):
        if w.cb_result.itemData(idx)[0] in ("combo", "case"):
            w.cb_result.setCurrentIndex(idx)
            break
    w.show_results()
    _ruhe()


def _tabelle_von(tu, k):
    """Die Datentabelle im Eintrag k des unteren Bereichs (oder None)."""
    from statik3d.gui import tabellen as tab
    wi = tu.widget(k)
    if isinstance(wi, tab.Datentabelle):
        return wi
    return wi.findChild(tab.Datentabelle) if wi is not None else None


def _mitte_y(wi, bezug):
    from PySide6 import QtCore
    return wi.mapTo(bezug, QtCore.QPoint(0, wi.height() // 2)).y()


# --------------------------------------------------------------------------
def test_eine_kopfzeile():
    from PySide6 import QtWidgets
    w = _fenster()
    _groesse(w, 1920, 1080)
    w.tabelle_zeigen("Knoten")
    _ruhe()
    tu = w.tab_unten
    kopf, cb, rb, wz = tu.kopf, tu.gruppenwahl, tu.reiter, tu.werkzeug
    check("Gruppe ist ein Aufklappfeld mit den acht Gruppen, die Reiter zeigen die Tabellen der Gruppe",
          isinstance(cb, QtWidgets.QComboBox)
          and [cb.itemText(i) for i in range(cb.count())] == tu.gruppennamen()
          and tu.gruppennamen()[:2] == ["Protokoll", "Modell"] and cb.currentText() == "Modell"
          and [rb.tabText(j) for j in range(rb.count())] == tu.tabellen("Modell"),
          f"{tu.gruppennamen()} / {[rb.tabText(j) for j in range(rb.count())]}")
    knoepfe = {a.text(): wz.widgetForAction(a) for a in wz.actions()}
    soll = ["Spalten…", "Filter", "Kopieren", "CSV…", "Excel…"]
    check("Knöpfe Spalten, Filter, Kopieren, CSV und Excel stehen im Kopf, mit Tooltip",
          list(knoepfe) == soll and all(b is not None and b.isVisible() for b in knoepfe.values())
          and all(a.toolTip() for a in wz.actions()), str(list(knoepfe)))
    teile = [("Gruppe", cb), ("Reiter", rb)] + [(t, b) for t, b in knoepfe.items()]
    mitten = {t: _mitte_y(b, tu) for t, b in teile if b is not None}
    check("Gruppe, Reiter und Knöpfe in einer Zeile (Mittellinien höchstens 4 px auseinander)",
          len(mitten) == 7 and max(mitten.values()) - min(mitten.values()) <= 4, str(mitten))
    t = w.aktive_tabelle()
    oben = t.view.mapTo(tu, t.view.rect().topLeft()).y()
    unterkante = kopf.mapTo(tu, kopf.rect().bottomLeft()).y()
    check("die Tabelle beginnt direkt unter dem Kopf (höchstens 6 px dazwischen), der Kopf ist höchstens 40 px hoch",
          0 <= oben - unterkante <= 6 and kopf.height() <= 40, f"Kopf {kopf.height()} px, Tabelle ab {oben}, Kopf bis {unterkante}")
    zweite = [g for g, s in tu.seiten.items() if not s.tabBar().isHidden()]
    check("keine zweite Registerzeile unter dem Kopf (die Seiten der Gruppen zeigen keine eigenen Reiter)",
          not zweite, str(zweite))
    check("die eigene Werkzeugzeile der Tabelle ist im Kopf aufgegangen",
          t.werkzeug.isHidden() and t.filterzeile.isHidden(), f"Werkzeug {t.werkzeug.isHidden()}")
    w.tabelle_zeigen("Protokoll")
    _ruhe()
    check("Protokoll (eine Gruppe mit einem Eintrag, keine Tabelle): kein Reiter, keine Tabellenknöpfe",
          rb.isHidden() and wz.isHidden() and cb.currentText() == "Protokoll", f"{rb.isHidden()} {wz.isHidden()}")
    w.tabelle_zeigen("Nachweise EC3")
    _ruhe()
    check("Tabelle vorholen stellt Gruppe und Reiter um",
          cb.currentText() == "Nachweise" and rb.tabText(rb.currentIndex()) == "Nachweise EC3"
          and tu.currentWidget() is w.tbl_design, f"{cb.currentText()} / {rb.tabText(rb.currentIndex())}")
    cb.setCurrentIndex(tu.gruppennamen().index("Lasten"))
    _ruhe()
    rb.setCurrentIndex(tu.tabellen("Lasten").index("Kombinationen"))
    _ruhe()
    check("Gruppe im Aufklappfeld und Klick auf einen Reiter wählen die Tabelle",
          tu.currentGroup() == "Lasten" and tu.tabText(tu.currentIndex()) == "Kombinationen"
          and tu.currentWidget().isAncestorOf(w.tbl_kombi), tu.tabText(tu.currentIndex()))


def _hoehen(w, b, h):
    from PySide6 import QtWidgets
    _groesse(w, b, h)
    an = w.anordnung
    erg = {"kompakt": an.kompakt}
    if an.kompakt:
        erg["eingeklappt"] = w.unten_dock.height()
        an.unten_einklappen(False)
        _ruhe(8)
    erg["unten"] = w.unten_dock.height()
    for name in ("Knoten", "Stabkräfte"):
        w.tabelle_zeigen(name)
        _ruhe(8)
        t = w.aktive_tabelle()
        # was man sieht: der Bereich schneidet ab, was nicht hineinpasst
        hoehe = t.view.visibleRegion().boundingRect().height()
        zeilen = t.view.viewport().visibleRegion().boundingRect().height() // ZEILE
        fuss = 0 if t.fuss.isHidden() else t.fuss.visibleRegion().boundingRect().height()
        erg[name] = (hoehe, zeilen, fuss // ZEILE)
        erg[name + "_fuss_ganz"] = t.fuss.isHidden() or fuss >= t.fuss.height()
    rolle = w.unten_dock.widget()
    erg["rollt"] = (rolle.horizontalScrollBar().maximum()
                    if isinstance(rolle, QtWidgets.QScrollArea) else 0)
    return erg


def test_hoehe():
    w = _fenster()
    _hall(w)
    _F["hall"] = True
    schrift = _mit_schrift()
    print(f"     {'mit Schrift' if schrift else 'ohne Schrift - Kästchenwerte'}", flush=True)
    for (b, h), vorher in (VORHER_SCHRIFT if schrift else VORHER_KAESTCHEN).items():
        e = _hoehen(w, b, h)
        teile = []
        for name in ("Knoten", "Stabkräfte"):
            (h0, z0, m0), (h1, z1, m1) = vorher[name], e[name]
            teile.append(f"{name} {h0} -> {h1} px, Zeilen {z0} + {m0} Max/Min -> {z1} + {m1}")
        detail = f"unten {e['unten']} px: " + "; ".join(teile)
        print(f"     Messung {b} x {h}{' (Kompaktstufe, aufgeklappt)' if e['kompakt'] else ''}: {detail}",
              flush=True)
        # Knoten ist Eingabe und verliert Max/Min mit Absicht: dort zaehlen die
        # Datenzeilen, bei den Stabkraeften Daten und Max/Min zusammen
        check(f"{b} x {h}: mindestens zwei Zeilen mehr zu sehen (Knoten: Daten; Stabkräfte: Daten und "
              "Max/Min), keine Tabelle wird niedriger",
              e["Knoten"][1] >= vorher["Knoten"][1] + 2
              and sum(e["Stabkräfte"][1:]) >= sum(vorher["Stabkräfte"][1:]) + 2
              and all(e[n][0] >= vorher[n][0] for n in ("Knoten", "Stabkräfte")), detail)
        check(f"{b} x {h}: Max/Min ganz zu sehen, der Bereich rollt nicht waagerecht",
              e["Knoten_fuss_ganz"] and e["Stabkräfte_fuss_ganz"] and e["rollt"] == 0,
              f"rollt {e['rollt']} px")
        if e["kompakt"]:
            check(f"{b} x {h}: Kompaktstufe eingeklappt zeigt nur die Kopfzeile (höchstens 40 px)",
                  e["eingeklappt"] <= 40, f"{e['eingeklappt']} px")
    _groesse(w, 1920, 1080)


def _filtertabelle(w):
    if not _F.get("hall"):
        _hall(w)
        _F["hall"] = True
    _groesse(w, 1920, 1080)
    w.tabelle_zeigen("Knoten")
    _ruhe()
    return w.tbl_knoten


def test_filterzeile():
    from statik3d.gui import tabellen as tab
    w = _fenster()
    t = _filtertabelle(w)
    tu = w.tab_unten
    a = tu.act_filter
    n = t.zeilenzahl()
    check("Vorbedingung: Knotentabelle gefüllt, Filterzeile zu, Knopf Filter nicht gedrückt",
          n >= 10 and t.filterzeile.isHidden() and a.isCheckable() and not a.isChecked(), f"{n} Zeilen")
    a.trigger()
    _ruhe()
    check("Knopf Filter: die Filterzeile erscheint über der Kopfzeile der Tabelle",
          a.isChecked() and t.filterzeile.isVisible()
          and t.filterzeile.geometry().bottom() <= t.view.geometry().top(), str(t.filterzeile.geometry()))
    soll = sum(1 for r in t.modell.zeilen if tab.passt(r[0], "1..5"))
    t.felder[0].setText("1..5")
    _ruhe()
    zahl = tu.reiter.zahl(tu.reiter.currentIndex())
    check("Filter „1..5“ wirkt (Filtersprache wie bisher), der Zähler am Reiter nennt beide Zahlen",
          t.sichtbar() == soll and 0 < soll < n and zahl == f"{soll}/{n}"
          and f"{soll} von {n} Zeilen" in t.lbl_zeilen.text(), f"{t.sichtbar()} von {n}, Zähler {zahl!r}")
    knopf = tu.werkzeug.widgetForAction(a)
    check("… der Knopf zeigt, dass ein Filter wirkt (Text, Hervorhebung, Tooltip mit den Zahlen)",
          a.text() == "Filter aktiv" and knopf.property("aktiv") is True
          and f"{soll} von {n}" in a.toolTip(), f"{a.text()!r} / {a.toolTip()!r}")
    tu.reiter.setCurrentIndex(tu.tabellen("Modell").index("Linien"))
    _ruhe()
    zustand_linien = (a.isChecked(), a.text())
    tu.reiter.setCurrentIndex(tu.tabellen("Modell").index("Knoten"))
    _ruhe()
    check("Filterzustand gilt je Tabelle: in „Linien“ kein Filter, zurück in „Knoten“ wieder aktiv",
          zustand_linien == (False, "Filter") and a.isChecked() and a.text() == "Filter aktiv",
          f"Linien {zustand_linien}, Knoten {(a.isChecked(), a.text())}")
    a.trigger()
    _ruhe()
    check("Knopf Filter noch einmal: Filterzeile weg, und der Filter ist aufgehoben (alle Zeilen)",
          t.filterzeile.isHidden() and not a.isChecked() and t.sichtbar() == n and not t.filter_wirkt()
          and t.felder[0].text() == "" and a.text() == "Filter" and knopf.property("aktiv") is not True,
          f"{t.sichtbar()} von {n}")
    t.felder[0].setText("1..5")
    _ruhe()
    check("ein Filter, der anders gesetzt wird, holt die Filterzeile selbst herein (er bleibt sichtbar)",
          t.filterzeile.isVisible() and a.isChecked() and t.sichtbar() == soll, f"{t.sichtbar()}")
    w.tabelle_filter_leeren()
    _ruhe()
    check("„Filter leeren“ (Ribbon) hebt den Filter auf, die Filterzeile bleibt offen",
          t.sichtbar() == n and t.filterzeile.isVisible() and a.text() == "Filter", f"{t.sichtbar()}")
    hinweis = t.felder[1].toolTip()
    check("die Felder erklären die Filtersprache weiter am Zeiger", all(s in hinweis for s in ("> 0,9", "1..5", "!")),
          hinweis)
    t.felder[0].setText("999999")
    _ruhe()
    check("lässt der Filter nichts übrig, sagt die Tabelle es", t.lbl_leer.isVisible()
          and "passt zum Filter" in t.lbl_leer.text(), t.lbl_leer.text())
    t.filterzeile_zeigen(False)
    _ruhe()


def test_zaehler():
    from statik3d.gui import tabellen as tab
    w = _fenster()
    if not _F.get("hall"):
        _hall(w)
        _F["hall"] = True
    _groesse(w, 1920, 1080)
    w.tabelle_zeigen("Knoten")
    _ruhe()
    tu, rb = w.tab_unten, w.tab_unten.reiter
    namen = tu.tabellen("Modell")
    tabellen = {nm: _tabelle_von(tu, tu.indexOf(tu.seiten["Modell"].widget(j))) for j, nm in enumerate(namen)}
    zahlen = {nm: rb.zahl(j) for j, nm in enumerate(namen)}
    soll = {nm: zl_text(t.zeilenzahl()) for nm, t in tabellen.items()}
    check("je Reiter die Zeilenzahl der Tabelle", zahlen == soll, f"{zahlen}")
    check("der Zähler steht nicht im Text des Reiters (Namen bleiben, wie sie sind)",
          [rb.tabText(j) for j in range(rb.count())] == namen and all(z not in rb.tabText(j) for j, z in
                                                                     enumerate(zahlen.values()) if z != ""),
          str([rb.tabText(j) for j in range(rb.count())]))
    leer_alle = [nm for nm, t in tabellen.items() if t.zeilenzahl() == 0]
    check("leere Reiter sind als leer geführt, gefüllte nicht",
          leer_alle and all(rb.ist_leer(j) == (nm in leer_alle) for j, nm in enumerate(namen)), str(leer_alle))
    farben = _reiterfarben(w, namen)
    if farben is None:
        return
    grund, leer, voll, gewaehlt_leer, strich = farben
    k_leer = min(_kontrast(c, grund) for c in leer.values())
    k_voll = min(_kontrast(c, grund) for c in voll.values())
    check("leere Reiter sind grau: Schrift mindestens 3 : 1 gegen den Grund und klar heller als gefüllte "
          "(Bild auf deckendem Grund)", k_leer >= 3.0 and k_voll >= k_leer + 1.0,
          f"leer {k_leer:.2f} : 1, gefüllt {k_voll:.2f} : 1, Grund {grund.name()}")
    c, cl = gewaehlt_leer, next(iter(leer.values()))
    abstand = abs(c.red() - cl.red()) + abs(c.green() - cl.green()) + abs(c.blue() - cl.blue())
    check("ein gewählter leerer Reiter ist erkennbar: Strich in Akzentfarbe, blaue Schrift mit 3 : 1, "
          "anders als die übrigen leeren",
          strich >= 10 and c.blue() >= c.red() + 40 and _kontrast(c, grund) >= 3.0 and abstand >= 60,
          f"Strich {strich} Punkte, Schrift {c.name()} ({_kontrast(c, grund):.2f} : 1), übrige {cl.name()}")
    # Eine grosse Tabelle, die nicht zu sehen ist, wartet mit dem Fuellen bis
    # zum Anzeigen - der Zaehler nimmt ihre Zahl, ohne sie zu fuellen
    t = w.tbl_kombi
    alt = t.VERZOEGERT_AB
    t.VERZOEGERT_AB = 10
    try:
        # in der Gruppe Lasten liegt „Lastfälle“ vorn - die Kombinationen
        # bleiben verborgen und damit ungefuellt
        tu.seiten["Lasten"].setCurrentIndex(tu.tabellen("Lasten").index("Lastfälle"))
        bisher = t.modell.rowCount()
        zeilen = [[f"K{i}", "", "", ""] for i in range(bisher + 30)]
        t.setzen(zeilen)
        _ruhe()
        cb = tu.gruppenwahl
        cb.setCurrentIndex(tu.gruppennamen().index("Lasten"))
        _ruhe()
        j = tu.tabellen("Lasten").index("Kombinationen")
        zahl = rb.zahl(j)
        check("eine wartende Tabelle (noch nicht gefüllt) zeigt ihre neue Zeilenzahl am Reiter, ohne gefüllt zu werden",
              zahl == zl_text(bisher + 30) and t.modell.rowCount() == bisher and t.ausstehend(),
              f"Zähler {zahl!r}, im Modell {t.modell.rowCount()} (vorher {bisher})")
    finally:
        t.VERZOEGERT_AB = alt
        t._ausstehend = None
    w.refresh_all()
    _ruhe()
    _wartend_gefiltert(w)


def _reiterfarben(w, namen):
    """Farben der Reiterschrift im Bild des Kopfes (deckender Grund): (Grund,
    {leer: Farbe}, {gefuellt: Farbe}, gewaehlter leerer Reiter, Punkte des
    Strichs unter ihm). Je Reiter die dunkelste Stelle im Textfeld - bei
    Kaestchen die Linienfarbe, mit Schrift der Kern der Striche."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from statik3d.gui import tabellen as tab
    tu, rb = w.tab_unten, w.tab_unten.reiter
    frei = tab.reiter_frei(rb)
    ganz = [j for j in range(rb.count()) if frei.contains(rb.tabRect(j)) and j != rb.currentIndex()]
    leer_j = [j for j in ganz if rb.ist_leer(j)]
    voll_j = [j for j in ganz if not rb.ist_leer(j)]
    check("Vorbedingung: in der Gruppe Modell sind leere und gefüllte Reiter ganz zu sehen",
          leer_j and voll_j, f"{[namen[j] for j in leer_j]} / {[namen[j] for j in voll_j]}")
    if not (leer_j and voll_j):
        return None

    def farben(bild, j):
        opt = QtWidgets.QStyleOptionTab()
        rb.initStyleOption(opt, j)
        r = rb.style().subElementRect(QtWidgets.QStyle.SE_TabBarTabText, opt, rb)
        r = QtCore.QRect(rb.mapTo(tu.kopf, r.topLeft()), r.size())
        punkte = [bild.pixelColor(x, y) for x in range(r.left(), r.right() + 1)
                  for y in range(r.top(), r.bottom() + 1)]
        return min(punkte, key=lambda c: c.lightness())

    bild = tu.kopf.grab().toImage()
    r0 = rb.tabRect(voll_j[0])
    grund = bild.pixelColor(rb.mapTo(tu.kopf, QtCore.QPoint(r0.left() + 2, r0.top() + 2)))
    leer = {namen[j]: farben(bild, j) for j in leer_j}
    voll = {namen[j]: farben(bild, j) for j in voll_j}
    # ein leerer Reiter gewaehlt
    j = leer_j[0]
    seite = tu.seiten[tu.currentGroup()]
    vorher = seite.currentIndex()
    seite.setCurrentIndex(j)
    _ruhe()
    bild = tu.kopf.grab().toImage()
    gewaehlt = farben(bild, j)
    r = rb.tabRect(j)
    akzent = QtGui.QColor("#1467c6")
    strich = 0
    for x in range(r.left(), r.right() + 1):
        for y in range(r.bottom() - 3, r.bottom() + 1):
            c = bild.pixelColor(rb.mapTo(tu.kopf, QtCore.QPoint(x, y)))
            if abs(c.red() - akzent.red()) + abs(c.green() - akzent.green()) + abs(c.blue() - akzent.blue()) < 40:
                strich += 1
    seite.setCurrentIndex(vorher)
    _ruhe()
    return grund, leer, voll, gewaehlt, strich


def _wartend_gefiltert(w):
    """Nachbesserung 03.10.2026 (Gegenpruefung F1): eine wartende Tabelle mit
    wirkendem Filter nannte am Reiter die Gesamtzahl („19“) und im Tooltip des
    Knopfs „19 von 19 sichtbar“, obwohl Tabelle und Export gefiltert sind."""
    from statik3d.gui import tabellen as tab
    tu, rb, an = w.tab_unten, w.tab_unten.reiter, w.anordnung
    t = w.tbl_knoten
    t.VERZOEGERT_AB = 10
    try:
        w.tabelle_zeigen("Knoten")
        _ruhe()
        if not t.filterzeile_offen():
            tu.act_filter.trigger()
        t.felder[0].setText("1..5")
        _ruhe()
        n, soll = t.zeilenzahl(), t.sichtbar()
        j = tu.tabellen("Modell").index("Knoten")
        gefiltert = rb.zahl(j)
        rb.setCurrentIndex(tu.tabellen("Modell").index("Elemente"))   # seit 8c: „Elemente“ statt „Stäbe“
        _ruhe()
        w.refresh_all()
        _ruhe()
        marke = rb.tabButton(j, tab.Reiterleiste.RECHTS)
        check("wartende Tabelle mit Filter, eine andere vorn: am Reiter „?/n“ statt der Gesamtzahl",
              t.ausstehend() and t.filter_wirkt() and rb.zahl(j) == f"?/{zl_text(n)}"
              and marke.property("gefiltert") is True and "gefiltert" in t.lbl_zeilen.text(),
              f"vorher {gefiltert!r}, jetzt {rb.zahl(j)!r}, {t.lbl_zeilen.text()!r}")
        rb.setCurrentIndex(j)
        _ruhe()
        an.unten_einklappen(True)
        _ruhe()
        w.refresh_all()
        _ruhe()
        tip = tu.act_filter.toolTip()
        check("… eingeklappt mit der Tabelle vorn: „Filter aktiv“, der Tooltip nennt keine falsche Zahl",
              t.ausstehend() and tu.act_filter.text() == "Filter aktiv" and f"{n} von {n}" not in tip
              and "beim Anzeigen" in tip and rb.zahl(j) == f"?/{zl_text(n)}", f"{rb.zahl(j)!r} / {tip[:80]!r}")
        an.unten_einklappen(False)
        _ruhe(10)
        check("… beim Anzeigen gefüllt: wieder die echte Zahl am Reiter und im Tooltip",
              not t.ausstehend() and rb.zahl(j) == f"{zl_text(soll)}/{zl_text(n)}"
              and f"{zl_text(soll)} von {zl_text(n)}" in tu.act_filter.toolTip(), f"{rb.zahl(j)!r}")
    finally:
        t.VERZOEGERT_AB = tab.Datentabelle.VERZOEGERT_AB
        t.filterzeile_zeigen(False)
        _ruhe()


def zl_text(n):
    from statik3d import zahlen as zl
    return zl.zahl_text(n)


def _ribbon_beschriftungen(w):
    """Was im Ribbon auf den Knoepfen steht: {Register: {Knopf}} und
    {(Register, Menueknopf): {Eintrag}} - so, wie der Anwender es liest."""
    from PySide6 import QtWidgets
    knoepfe, menues = {}, {}
    for reg, seite in w.ribbon._register.items():
        for b in seite.findChildren(QtWidgets.QToolButton):
            if b.objectName() not in ("ribbongross", "ribbonklein"):
                continue
            knoepfe.setdefault(reg, set()).add(b.text())
            if b.menu() is not None:
                menues[(reg, b.text())] = {a.text() for a in b.menu().actions() if not a.isSeparator()}
    return knoepfe, menues


def _verweise_pruefen(w, text, seite):
    """Jeder Verweis nach „ – “ steht ganz so im Ribbon: „Register → Knopf“ oder
    „Register → Menüknopf ▾ → Eintrag“; mehrere mit „, dann“ oder „oder“. Jeder
    Knopf in „…“ steht sichtbar an der Tabelle. Verglichen werden ganze Namen
    (Gegenpruefung S4: bis dahin nur der Wortanfang)."""
    from PySide6 import QtWidgets
    knoepfe, menues = _ribbon_beschriftungen(w)
    fehlt = []
    teil = text.split(" – ", 1)[1] if " – " in text else ""
    if not teil:
        fehlt.append("kein „ – “ vor dem Verweis")
    for ref in re.split(r", dann | oder ", teil):
        if "→" not in ref:
            continue
        stuecke = [s.strip() for s in ref.split("→")]
        if len(stuecke) == 2:
            ok = stuecke[1] in knoepfe.get(stuecke[0], set())
        elif len(stuecke) == 3:
            ok = stuecke[2] in menues.get((stuecke[0], stuecke[1]), set())
        else:
            ok = False
        if not ok:
            fehlt.append(ref.strip())
    an_tabelle = {b.text() for b in seite.findChildren(QtWidgets.QAbstractButton) if b.isVisibleTo(seite)}
    for k in re.findall(r"„([^“]+)“", text):
        if k not in an_tabelle:
            fehlt.append(f"Knopf „{k}“")
    return fehlt


def test_leere_tabelle():
    w = _fenster()
    w.new_model()
    _ruhe()
    _F["hall"] = False
    _groesse(w, 1920, 1080)
    w.tabelle_zeigen("Lasten")
    _ruhe()
    t = w.tbl_last
    check("leere Tabelle Lasten sagt, wie sie sich füllt",
          t.zeilenzahl() == 0 and t.lbl_leer.isVisible()
          and t.lbl_leer.text() == "Noch keine Lasten – Lasten → Knotenlast", t.lbl_leer.text())
    tu = w.tab_unten
    ohne, falsch = [], []
    for k in range(tu.count()):
        tb = _tabelle_von(tu, k)
        if tb is None:
            continue
        name = tu.tabText(k)
        if not tb.leertext:
            ohne.append(name)
            continue
        f = _verweise_pruefen(w, tb.leertext, tu.widget(k))
        if f:
            falsch.append(f"{name}: {f}")
    check("jede Tabelle unten hat einen Satz für den leeren Zustand", not ohne, str(ohne))
    seite = tu.widget(tu.indexOf(tu.currentWidget()))
    check("die Verweisprüfung weist Ungenaues ab (Wortanfang, angehängtes „ …“, falsches Register, "
          "falscher Menüeintrag)",
          all(_verweise_pruefen(w, f"X – {v}", seite) for v in (
              "Lasten → Knotenlas", "Lasten → Knotenlast …", "Geometrie → Knotenlast",
              "Nachweise → Verformung ▾ → Neu", "Nachweise → Verformung → Neu …")))
    check("jeder Verweis darin führt zu einem Befehl im Ribbon oder einem Knopf an der Tabelle",
          not falsch, "; ".join(falsch[:3]))
    w.tabelle_zeigen("Stabkräfte")
    _ruhe()
    tb = w.tbl_beam
    tb.setzen([])
    tb.hinweis_setzen("Probe: die Umhüllende zeigt ihre Extremwerte im Register „Umhüllende“")
    _ruhe()
    vorrang = tb.lbl_leer.text()
    tb.hinweis_setzen("")
    _ruhe()
    check("ein Hinweis zum gezeigten Ergebnis geht dem allgemeinen Satz vor, danach steht der wieder da",
          vorrang.startswith("Probe:") and tb.lbl_leer.text() == tb.leertext and tb.lbl_leer.isVisible(),
          f"{vorrang[:30]!r} / {tb.lbl_leer.text()[:30]!r}")
    _hall(w)
    _F["hall"] = True
    w.tabelle_zeigen("Knoten")
    _ruhe()
    check("eine gefüllte Tabelle zeigt keinen Leersatz", not w.tbl_knoten.lbl_leer.isVisible())


def test_kennwerte():
    from PySide6 import QtWidgets
    from statik3d.gui import tabellen as tab
    from statik3d.gui.tabellen import Spalte
    w = _fenster()
    tu = w.tab_unten
    falsch = []
    for k in range(tu.count()):
        tb = _tabelle_von(tu, k)
        if tb is None:
            continue
        g = tu.gruppe_von(tu.tabText(k))
        if tb.kennwerte_zeigen != (g in ERGEBNISGRUPPEN):
            falsch.append(f"{g}/{tu.tabText(k)}: {tb.kennwerte_zeigen}")
    check("Max/Min nur an den Tabellen der Gruppen Ergebnisse und Nachweise", not falsch, "; ".join(falsch))
    if not _F.get("hall"):
        _hall(w)
        _F["hall"] = True
    _groesse(w, 1920, 1080)
    w.tabelle_zeigen("Knoten")
    _ruhe()
    w.tabelle_zeigen("Stabkräfte")
    _ruhe()
    check("Hallenrahmen: Knoten (Eingabe) ohne Max/Min, Stabkräfte (Ergebnis) mit",
          w.tbl_knoten.fuss.isHidden() and not w.tbl_beam.fuss.isHidden()
          and w.tbl_beam.fussmodell.rowCount() == 2, f"{w.tbl_knoten.zeilenzahl()} / {w.tbl_beam.zeilenzahl()}")
    t = tab.Datentabelle([Spalte("Nr", "", "ganz"), Spalte("N", "kN", "zahl", 2)], "Probe",
                         mit_kennwerten=True)
    halter = QtWidgets.QWidget()
    QtWidgets.QVBoxLayout(halter).addWidget(t)
    halter.show()
    t.setzen([[i, float(i)] for i in range(1, 5)])
    _ruhe()
    vier = (t.fuss.isHidden(), len(t.zeilen_fuer_export()))
    t.setzen([[i, float(i)] for i in range(1, 6)])
    _ruhe()
    check(f"Ergebnistabelle mit 4 Zeilen ohne Max/Min (auch im Export), ab {tab.Datentabelle.KENNWERTE_AB} "
          "Zeilen mit", vier == (True, 4) and not t.fuss.isHidden() and t.fussmodell.rowCount() == 2
          and len(t.zeilen_fuer_export()) == 7, f"4 Zeilen: {vier}, 5 Zeilen: {len(t.zeilen_fuer_export())}")
    t.felder[1].setText("<= 2")
    _ruhe()
    check("… die Kennwerte folgen dem Filter, die Zeile bleibt (die Tabelle hat 5 Zeilen)",
          not t.fuss.isHidden() and float(t.fussmodell.zeilen[0][1]) == 2.0, str(t.fussmodell.zeilen))
    halter.hide()
    _nachweistabelle_mit_kennwerten(w)


def _nachweistabelle_mit_kennwerten(w):
    """Eine echte Nachweistabelle mit mindestens 5 Zeilen zeigt Max und Min
    (Gegenpruefung S5: am Hallenrahmen hat Nachweise EC3 nur 3 Zeilen, der
    Zweig mit Fusszeile lief nie). Der Hallenrahmen mit je zwei Staeben fuer
    Stiele und Riegel ergibt 6 Nachweiszeilen."""
    from dataclasses import replace
    from statik3d import solver
    from statik3d.examples_lib import build_example
    m = build_example("hall")
    alt = dict(m.members)
    m.members.clear()
    for name, mem in alt.items():
        h = len(mem.elements) // 2
        for teil, els in (("a", mem.elements[:h]), ("b", mem.elements[h:])):
            m.members[f"{name} {teil}"] = replace(mem, name=f"{name} {teil}", elements=list(els))
    w._modell_setzen(m)
    _F["hall"] = False
    _ruhe()
    an = solver.solve_all(w.model, design=True)
    w._solve_done("all", an)
    _ruhe()
    for idx in range(w.cb_result.count()):
        if w.cb_result.itemData(idx)[0] in ("combo", "case"):
            w.cb_result.setCurrentIndex(idx)
            break
    w.show_results()
    _ruhe()
    w.tabelle_zeigen("Nachweise EC3")
    _ruhe()
    t = w.tbl_design
    namen = [sp.name for sp in t.modell.spalten]
    k = namen.index("Ausnutzung")
    werte = [float(z[k]) for z in t.modell.zeilen if isinstance(z[k], (int, float))]
    fuss = t.fussmodell.zeilen
    check("Nachweise EC3 mit 6 Stäben: Max/Min sichtbar, Max und Min der Ausnutzung stimmen",
          t.zeilenzahl() >= 5 and not t.fuss.isHidden() and t.fuss.isVisible() and len(fuss) == 2
          and werte and abs(float(fuss[0][k]) - max(werte)) < 1e-9 and abs(float(fuss[1][k]) - min(werte)) < 1e-9,
          f"{t.zeilenzahl()} Zeilen, Max {fuss[0][k] if fuss else '-'} / {max(werte) if werte else '-'}")
    export = t.zeilen_fuer_export()
    check("… und Kopieren/CSV/Excel geben Max und Min mit aus", len(export) == t.zeilenzahl() + 2
          and export[-2][0] == "Max" and export[-1][0] == "Min", f"{len(export)} Zeilen")
    w.tabelle_zeigen("Knoten")
    _ruhe()
    k_ex = w.tbl_knoten.zeilen_fuer_export()
    check("Eingabetabelle Knoten: Kopieren/CSV/Excel ohne Max und Min",
          len(k_ex) == w.tbl_knoten.zeilenzahl() and all(z[0] not in ("Max", "Min") for z in k_ex),
          f"{len(k_ex)} von {w.tbl_knoten.zeilenzahl()}")


def _erreichbar(w):
    """Was im unteren Bereich nicht erreichbar oder gekuerzt ist."""
    from PySide6 import QtCore, QtWidgets
    tu = w.tab_unten
    kopf, cb, rb, wz = tu.kopf, tu.gruppenwahl, tu.reiter, tu.werkzeug
    maengel = []
    rolle = w.unten_dock.widget()
    if isinstance(rolle, QtWidgets.QScrollArea) and rolle.horizontalScrollBar().maximum() > 0:
        maengel.append(f"unten rollt waagerecht ({rolle.horizontalScrollBar().maximum()} px)")
    breite = rolle.viewport().width() if isinstance(rolle, QtWidgets.QScrollArea) else w.unten_dock.width()
    if kopf.width() > breite:
        maengel.append(f"Kopf {kopf.width()} px breiter als der Bereich {breite} px")
    if not cb.isVisible() or cb.width() < cb.sizeHint().width() - 1:
        maengel.append(f"Gruppe gekürzt ({cb.width()} von {cb.sizeHint().width()} px)")
    ext = wz.findChild(QtWidgets.QToolButton, "qt_toolbar_ext_button")
    menue = ext is not None and ext.isVisible()
    if tu.aktive_tabelle() is None:
        # Protokoll: keine Tabelle, keine Tabellenknoepfe
        if wz.isVisible():
            maengel.append("Tabellenknöpfe ohne Tabelle")
        return maengel
    for a in wz.actions():
        b = wz.widgetForAction(a)
        da = (b is not None and b.isVisible()
              and kopf.rect().contains(QtCore.QRect(b.mapTo(kopf, QtCore.QPoint(0, 0)), b.size())))
        if not da and not menue:
            maengel.append(f"Knopf {a.text()} weder sichtbar noch im Menü »")
        if da and b.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly and not a.toolTip():
            maengel.append(f"Symbol {a.text()} ohne Tooltip")
    if rb.isVisible():
        if rb.elideMode() != QtCore.Qt.ElideNone:
            maengel.append("Reiter werden gekürzt")
        noetig = sum(rb.tabSizeHint(j).width() for j in range(rb.count()))
        if noetig > rb.width() and not rb.usesScrollButtons():
            maengel.append("Reiter passen nicht und es gibt keine Rollpfeile")
        for j in range(rb.count()):
            if rb.tabRect(j).width() < rb.tabSizeHint(j).width() - 1:
                maengel.append(f"Reiter {rb.tabText(j)} gekürzt")
        from statik3d.gui import tabellen as tab
        r = rb.tabRect(rb.currentIndex())
        if not tab.reiter_frei(rb).contains(r):
            maengel.append(f"gewählter Reiter {rb.tabText(rb.currentIndex())} nicht ganz im Bild")
    return maengel


def _klick(leiste, j, doppelt=False):
    _klick_bei(leiste, leiste.tabRect(j).center(), doppelt)


def _klick_bei(wi, p, doppelt=False):
    from PySide6 import QtCore, QtTest
    leiste = wi
    if doppelt:
        QtTest.QTest.mousePress(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
        QtTest.QTest.mouseRelease(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
        QtTest.QTest.mouseDClick(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
        QtTest.QTest.mouseRelease(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
    else:
        QtTest.QTest.mouseClick(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
    _ruhe(6)


def _protokoll_kopf(w, b, h):
    """Gruppe Protokoll, eingeklappt (so startet das Programm bei 1366 x 768):
    das Aufklappfeld ist so breit wie der Name (Gegenpruefung S1: 626 statt
    91 px mit Segoe UI), und ein Klick bzw. Doppelklick auf den freien Kopf
    klappt auf und zu (L1: ohne Reiter ging das vorher nicht)."""
    from PySide6 import QtCore
    tu, an = w.tab_unten, w.anordnung
    tu.zeigen("Protokoll")
    an.unten_einklappen(True)
    _ruhe()
    cb, kopf = tu.gruppenwahl, tu.kopf
    check(f"{b} x {h}, Protokoll: Aufklappfeld so breit wie der Name und links im Kopf, kein Reiter",
          cb.width() <= cb.sizeHint().width() + 2 and cb.x() <= 8 and tu.reiter.isHidden(),
          f"Feld {cb.width()} px bei x = {cb.x()}, Name braucht {cb.sizeHint().width()} px, "
          f"Kopf {kopf.width()} px")
    p = QtCore.QPoint(cb.geometry().right() + 40, kopf.height() // 2)
    frei = kopf.childAt(p) is None and p.x() < kopf.width()
    _klick_bei(kopf, p)
    auf = not an.unten_eingeklappt()
    _klick_bei(kopf, p, doppelt=True)
    zu = an.unten_eingeklappt()
    _klick_bei(kopf, p, doppelt=True)
    wieder = not an.unten_eingeklappt() and w.log.isVisible()
    check(f"{b} x {h}, Protokoll: Klick auf den freien Kopf klappt auf, Doppelklick zu und wieder auf",
          frei and auf and zu and wieder, f"frei {frei}, auf {auf}, zu {zu}, wieder {wieder}")
    an.unten_einklappen(True)
    _ruhe()


def test_kompaktstufe():
    w = _fenster()
    if not _F.get("hall"):
        _hall(w)
        _F["hall"] = True
    an = w.anordnung
    tu = w.tab_unten
    for b, h in ((1366, 768), (1280, 720)):
        _groesse(w, b, h)
        check(f"{b} x {h}: Kompaktstufe, unten eingeklappt auf die Kopfzeile",
              an.kompakt and an.unten_eingeklappt() and w.unten_dock.height() <= 40
              and tu.kopf.isVisible() and w.unten_dock.height() >= tu.kopf.height(),
              f"unten {w.unten_dock.height()} px, Kopf {tu.kopf.height()} px")
        _protokoll_kopf(w, b, h)
        for gruppe, tabelle in (("Modell", "Knoten"), ("Nachweise", "Lasteinleitung"),
                                ("Ergebnisse", "Kontaktpaare")):
            tu.zeigen(tabelle)
            _ruhe()
            m = _erreichbar(w)
            check(f"{b} x {h}, eingeklappt, {gruppe} → {tabelle}: alles erreichbar, nichts gekürzt",
                  not m, "; ".join(m[:4]))
        rb = tu.reiter
        tu.zeigen("Knoten")
        _ruhe()
        _klick(rb, 1)
        check(f"{b} x {h}: ein Klick auf einen Reiter klappt unten auf",
              not an.unten_eingeklappt() and w.unten_dock.height() >= 150 and tu.currentWidget().isVisible(),
              f"unten {w.unten_dock.height()} px")
        maengel = []
        for k in range(tu.count()):
            name = tu.tabText(k)
            tu.zeigen(name)
            _ruhe(3)
            maengel += [f"{name}: {x}" for x in _erreichbar(w)]
            t = _tabelle_von(tu, k)
            if t is not None and not t.fuss.isHidden() and \
                    t.fuss.visibleRegion().boundingRect().height() < t.fuss.height():
                maengel.append(f"{name}: Max/Min abgeschnitten")
        check(f"{b} x {h}, aufgeklappt, alle {tu.count()} Einträge der Reihe nach vorn: alles erreichbar, "
              "nichts gekürzt, nichts rollt", not maengel, "; ".join(maengel[:4]))
        tu.zeigen("Knoten")
        _ruhe()
        _klick(rb, 1, doppelt=True)
        check(f"{b} x {h}: ein echter Doppelklick auf die Reiter klappt wieder zu",
              an.unten_eingeklappt() and w.unten_dock.height() <= 40, f"{w.unten_dock.height()} px")
        # wie die Wahl in der Liste: erst der neue Eintrag, dann „activated“
        i = tu.gruppennamen().index("Lasten")
        tu.gruppenwahl.setCurrentIndex(i)
        tu.gruppenwahl.activated.emit(i)
        _ruhe()
        check(f"{b} x {h}: eine Gruppe im Aufklappfeld wählen klappt unten auf",
              not an.unten_eingeklappt() and tu.currentGroup() == "Lasten", f"{w.unten_dock.height()} px")
        an.unten_einklappen(True)
        _ruhe()
        tu.zeigen("Knoten")
        _ruhe()
        tu.act_filter.trigger()
        _ruhe()
        check(f"{b} x {h}: Knopf Filter im eingeklappten Bereich klappt auf und zeigt die Filterzeile",
              not an.unten_eingeklappt() and w.tbl_knoten.filterzeile.isVisible(), f"{w.unten_dock.height()} px")
        tu.act_filter.trigger()
        _ruhe()
    _groesse(w, 1920, 1080)


def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Kopfzeile unten.**")
    check("Handbuch: eine Kopfzeile mit Gruppe, Reitern und Knöpfen, Stand vorher genannt",
          "Aufklappfeld" in a and "Spalten" in a and "Excel" in a and "»" in a
          and "Bis zum 03.10.2026" in a, a[:90])
    b = absatz("**Filterzeile auf Knopfdruck.**")
    check("Handbuch: Filterzeile auf Knopfdruck, „Filter aktiv“, Ausblenden hebt den Filter auf",
          "Filter aktiv" in b and "aufgehoben" in b and "Bis zum 03.10.2026" in b, b[:90])
    c = absatz("**Zähler am Reiter.**")
    check("Handbuch: Zeilenzahl am Reiter, leere Reiter grau, Satz in der leeren Tabelle",
          "grau" in c and "Noch keine Lasten" in c, c[:90])
    d = absatz("Unter jeder Ergebnistabelle")
    check("Handbuch: Max/Min nur an Ergebnis- und Nachweistabellen ab 5 Zeilen, auch Kopieren und Export",
          "ab 5 Zeilen" in d and "Bis zum 03.10.2026" in d and "Kopieren" in d and "Excel" in d, d[:90])
    e = absatz("**Ansicht → Fenster**")
    check("Handbuch: Doppelklick auf eine freie Stelle der Kopfzeile unten, auch beim Protokoll",
          "freie Stelle" in e and "Protokoll" in e, e[:90])
    check("Handbuch: Messwerte mit Schrift, keine Kästchenwerte mehr (78 und 108 px vorher)",
          "78 px" in a and "108 px" in a and "215 px" not in a, a[:90])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1200, exit=True)
    nur = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv[:-1] else ""
    for t in (test_eine_kopfzeile, test_hoehe, test_filterzeile, test_zaehler, test_leere_tabelle,
              test_kennwerte, test_kompaktstufe, test_handbuch):
        if nur and nur not in t.__name__:
            continue
        print(f"\n--- {t.__name__} ---", flush=True)
        try:
            t()
        except Exception as ex:      # noqa: BLE001 - eine fehlende Funktion darf die Suite nicht abbrechen
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    sys.stderr.flush()
    # ohne close(): keine Rueckfrage „Ungespeicherte Änderungen“ (Regel Block C)
    os._exit(0 if not schlecht else 1)


if __name__ == "__main__":
    main()
