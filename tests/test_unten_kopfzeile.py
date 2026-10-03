"""
Unterer Bereich in einer Kopfzeile (Teilpaket 10b des Oberflaechenplans, 03.10.2026).

Befund am Stand 5ee513d (offscreen gemessen, Beispiel hall gerechnet, eine
Kombination gezeigt): unten standen untereinander die Gruppenleiste, die
Register der Gruppe, eine Werkzeugzeile je Tabelle (Zeilenzahl, Spalten…,
Filter leeren, Kopieren, CSV…, Excel…), die Filterzeile und unter jeder
Tabelle mit Kennwerten die Zeilen Max und Min - auch unter den Eingabetabellen
Knoten, Stäbe, Flächen, Volumenkörper und Schweißnähte. Von 270 px unten bei
1920 x 1080 blieben der Knotentabelle 94 px (2 Zeilen), den Stabkräften 120 px
(3 Zeilen); in der Kompaktstufe (aufgeklappt) 68 und 94 px.

Geprueft wird:

* Gruppe (Aufklappfeld), Reiter und die Knoepfe Spalten, Filter, Kopieren,
  CSV und Excel stehen in **einer** Zeile; keine zweite Registerzeile;
* die Tabelle gewinnt Hoehe (gemessen gegen den Stand 5ee513d);
* die Filterzeile kommt und geht auf Knopfdruck, ein wirkender Filter bleibt
  sichtbar und der Knopf sagt es, die Filtersprache bleibt;
* der Zaehler steht klein am Reiter (nicht im Text), leere Reiter sind grau,
  der Zaehler fuellt keine wartende Tabelle;
* eine leere Tabelle sagt, wie sie sich fuellt, und ihre Verweise
  („Register → Befehl“, „Knopf“) gibt es wirklich;
* Max/Min nur an Ergebnis- und Nachweistabellen und erst ab 5 Zeilen;
* in der Kompaktstufe (1366 x 768, 1280 x 720) ist alles erreichbar und
  nichts gekuerzt.

Aufruf:  python -m tests.test_unten_kopfzeile
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

#: Was am Stand 5ee513d von der Tabelle zu sehen war, offscreen, Beispiel
#: hall mit solve_all(design=True), erste Kombination gezeigt; Kompaktstufe
#: aufgeklappt (anordnung.unten_einklappen(False)). Gemessen mit demselben
#: Ablauf wie _hoehen() unten (scratchpad/messung_unten.py, 03.10.2026):
#: (sichtbare Hoehe der Tabelle [px], sichtbare Datenzeilen, sichtbare Zeilen
#: Max/Min). In der Kompaktstufe war der Inhalt unten 244 px hoch, der Bereich
#: 202 px: unten fehlten 42 px - von Max/Min der Knoten waren 20 von 46 px zu
#: sehen (keine ganze Zeile), von denen der Stabkraefte nichts.
VORHER = {
    (1920, 1080): {"Knoten": (94, 2, 2), "Stabkräfte": (120, 3, 2)},
    (1366, 768): {"Knoten": (68, 1, 0), "Stabkräfte": (91, 2, 0)},
    (1280, 720): {"Knoten": (68, 1, 0), "Stabkräfte": (91, 2, 0)},
}
#: Zeilenhoehe der Tabellen [px] (Datentabelle: verticalHeader 22 px)
ZEILE = 22
#: Gruppen, deren Tabellen Ergebnisse tragen - nur dort gibt es Max/Min
ERGEBNISGRUPPEN = ("Ergebnisse", "Nachweise")


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
    w.error = lambda msg, *a, **k: w.fehler.append(str(msg))
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
    for (b, h), vorher in VORHER.items():
        e = _hoehen(w, b, h)
        teile = []
        for name in ("Knoten", "Stabkräfte"):
            (h0, z0, m0), (h1, z1, m1) = vorher[name], e[name]
            teile.append(f"{name} {h0} -> {h1} px, Zeilen {z0} + {m0} Max/Min -> {z1} + {m1}")
        detail = f"unten {e['unten']} px: " + "; ".join(teile)
        print(f"     Messung {b} x {h}{' (Kompaktstufe, aufgeklappt)' if e['kompakt'] else ''}: {detail}",
              flush=True)
        check(f"{b} x {h}: man sieht von jeder Tabelle mindestens zwei Zeilen mehr (Daten und Max/Min), "
              "und keine wird niedriger",
              all(sum(e[n][1:]) >= sum(vorher[n][1:]) + 2 and e[n][0] >= vorher[n][0]
                  for n in ("Knoten", "Stabkräfte")), detail)
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
    # im Bild nur Reiter, die ganz zu sehen sind (nicht unter den Rollpfeilen)
    frei = tab.reiter_frei(rb)
    ganz = [nm for j, nm in enumerate(namen) if frei.contains(rb.tabRect(j)) and j != rb.currentIndex()]
    leer = [nm for nm in ganz if nm in leer_alle]
    voll = [nm for nm in ganz if nm not in leer_alle]
    check("Vorbedingung: in der Gruppe Modell sind leere und gefüllte Reiter ganz zu sehen",
          leer and voll, f"{leer} / {voll}")
    if not (leer and voll):
        return
    bild = rb.grab().toImage()

    def dunkelster(j):
        r = rb.tabRect(j)
        knopf = rb.tabButton(j, rb.ButtonPosition.RightSide)
        rechts = knopf.geometry().left() if knopf is not None else r.right()
        werte = [bild.pixelColor(x, y).lightness() for x in range(r.left() + 2, rechts)
                 for y in range(r.top() + 2, r.bottom() - 3)]
        return min(werte) if werte else 255
    hell_leer = min(dunkelster(namen.index(nm)) for nm in leer)
    hell_voll = max(dunkelster(namen.index(nm)) for nm in voll)
    check("leere Reiter sind grau: ihre Schrift ist deutlich heller als die gefüllter Reiter (Bild)",
          hell_leer >= hell_voll + 40, f"dunkelster Punkt leer {hell_leer}, gefüllt {hell_voll}")
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


def zl_text(n):
    from statik3d import zahlen as zl
    return zl.zahl_text(n)


_VERWEIS = re.compile(r" → ")


def _verweise_pruefen(w, text, seite):
    """Jeder Verweis „Register → Befehl“ nennt einen Befehl, den es im Ribbon gibt,
    jeder Knopf in „…“ steht auf der Seite der Tabelle."""
    from PySide6 import QtWidgets
    fehlt = []
    befehle = [(b.register, b.text.rstrip("…").strip()) for b in w.ribbon.befehle]
    for m in _VERWEIS.finditer(text):
        vorn, hinten = text[:m.start()], text[m.end():]
        if not any(vorn.endswith(reg) and hinten.startswith(cmd) for reg, cmd in befehle if cmd):
            fehlt.append(f"{vorn[-20:]} → {hinten[:20]}")
    knoepfe = {b.text() for b in seite.findChildren(QtWidgets.QAbstractButton)}
    for k in re.findall(r"„([^“]+)“", text):
        if k not in knoepfe:
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
          and t.lbl_leer.text() == "Noch keine Lasten – Lasten → Knotenlast …", t.lbl_leer.text())
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
    from PySide6 import QtCore, QtTest
    p = leiste.tabRect(j).center()
    if doppelt:
        QtTest.QTest.mousePress(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
        QtTest.QTest.mouseRelease(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
        QtTest.QTest.mouseDClick(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
        QtTest.QTest.mouseRelease(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
    else:
        QtTest.QTest.mouseClick(leiste, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, p)
    _ruhe(6)


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
    check("Handbuch: Max/Min nur an Ergebnis- und Nachweistabellen ab 5 Zeilen",
          "ab 5 Zeilen" in d and "Bis zum 03.10.2026" in d, d[:90])


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
