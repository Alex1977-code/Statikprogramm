"""
Nicht erfuellte Nachweise fallen auf (Paket 2 des Oberflaechenplans,
24.09.2026).

Befund der Analyse: an der Stauwand stand D = 1,094 in der Tabelle Ermuedung
genauso da wie 0,035, und das Protokoll meldete „max. Schädigung D = 1.094“
ohne Urteil, direkt unter der EC3-Zeile „… - alle erfuellt“. Jetzt:

- Ampel in den Nachweistabellen (Ausnutzung, D, Status): bis 0,9 normal,
  ueber 0,9 bis 1,0 gelb hinterlegt, ueber 1,0 rot und fett, „NICHT“ rot.
- Tabelle Ermuedung mit Spalte „Status“ als vorletzter Spalte (die letzte
  bleibt „maßgebend“).
- Die Protokollzeile zur Ermuedung endet mit dem Urteil; das bildet die
  Oberflaeche, ec3/fatigue.py bleibt unberuehrt.
- Nach der Rechnung eine rote Sammelzeile „Nachweise: n NICHT erfüllt (…)“,
  nur wenn etwas nicht erfuellt ist, und dann springt unten die
  Nachweistabelle nach vorn - sonst bleibt unten, was offen war.
- Die Nachweistabellen starten absteigend nach Ausnutzung; Zeilen ohne Zahl
  (nicht gerechnet, nicht gefuehrt) stehen dabei hinter den Zahlen.

Modell: drei Kragarme IPE 200, 2 m, Kerbfall 71, Last an der Spitze 5, 10
und 9,3 kN im Lastfall LF2; die Ermuedungslast LF1 -> LF2 mit n Spielen.
Mit n = 1,08 Mio. ist D(Riegel 2) rund 1,2 (rot), D(Riegel 3) rund 0,94
(gelb), D(Riegel 1) rund 0,07 (normal) - bei konstanter Schwingbreite
oberhalb Delta-sigma_D waechst D linear mit n (gemessen: n = 1e5 ergibt
0,111 / 0,087 / 0,006).

Aufruf:  python -m tests.test_nachweisampel
"""
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_nachweisampel_"), "einstellungen.json")

from statik3d.model import Model, Material, FatigueLoad  # noqa: E402
from statik3d.profiles import make_section  # noqa: E402
from statik3d import solver, mesher  # noqa: E402

RESULTS = []

#: Lastspiele: Riegel 2 rot, Riegel 3 gelb, Riegel 1 normal
N_ROT = 1.08e6
#: Lastspiele: alle Ermuedungsnachweise erfuellt, keiner gelb
N_GRUEN = 5e5


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:74s} {detail}")
    return ok


def _modell(n: float, f2: float = 10e3):
    """Drei Kragarme nebeneinander, je ein Stab mit Kerbfall 71."""
    m = Model("Ampel")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    m.case().category = "G"
    lf1 = list(m.load_cases)[0]
    m.add_load_case("LF2", "Q")
    k = 0
    for i, F in enumerate((5e3, f2, 9.3e3)):
        ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, i, 0), (2, i, 0), 4)
        m.fix(ids[0], [0, 1, 2, 3, 4, 5])
        m.load_node(ids[-1], Fz=-1000.0, case=lf1)
        m.load_node(ids[-1], Fz=-F, case="LF2")
        m.add_member(f"Riegel {i + 1}", list(range(k, k + 4)), detail_category=71e6)
        k += 4
    m.fatigue_loads["Zyklus"] = FatigueLoad("Zyklus", folge=[lf1, "LF2"], wiederholungen=n)
    return m


# --------------------------------------------------------------------------
# Ohne Hauptfenster: Ampel und Sortierung im Tabellenmodell
# --------------------------------------------------------------------------
def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_ampelstufe():
    from statik3d.gui import tabellen as tab
    faelle = [(0.5, ""), (0.9, ""), (0.9001, "gelb"), (0.95, "gelb"), (1.0, "gelb"),
              (1.0001, "rot"), (1.094, "rot"), ("NICHT erfüllt", "rot"),
              ("erfüllt", ""), ("nicht geführt", ""), ("unvollständig", ""),
              ("–", ""), ("", ""), (None, "")]
    ist = [(w, tab.ampelstufe(w)) for w, _s in faelle]
    check("Ampelstufe: bis 0,9 normal, bis 1,0 gelb, darüber rot, „NICHT“ rot",
          all(s == soll for (_w, s), (_w2, soll) in zip(ist, faelle)),
          str([x for x, y in zip(ist, faelle) if x[1] != y[1]]))


def test_ampel_im_modell():
    from PySide6 import QtCore, QtGui
    from statik3d.gui import tabellen as tab
    _app()
    sp = [tab.Spalte("Ausnutzung", "", "zahl", 3, ampel=True), tab.Spalte("Status", ampel=True),
          tab.Spalte("σ", "", "zahl", 3)]
    zeilen = [[1.094, "NICHT erfüllt", 1.5], [0.95, "erfüllt", 0.95], [0.5, "erfüllt", 0.5]]
    mo = tab.TabellenModell(sp)
    mo.setzen(zeilen)
    Fg, Bg, Fo = QtCore.Qt.ForegroundRole, QtCore.Qt.BackgroundRole, QtCore.Qt.FontRole

    def farbe(x):
        if x is None:
            return None
        if isinstance(x, QtGui.QBrush):
            x = x.color()
        return QtGui.QColor(x).name()

    def fett(x):
        return x is not None and QtGui.QFont(x).bold()

    rot, gelb = QtGui.QColor(tab.AMPEL_ROT).name(), QtGui.QColor(tab.AMPEL_GELB).name()
    zeile = {str(mo.zeilen[r][0]): r for r in range(mo.rowCount())}
    r_rot, r_gelb, r_ok = zeile["1.094"], zeile["0.95"], zeile["0.5"]
    ix = mo.index
    check("über 1,0: rot und fett",
          farbe(mo.data(ix(r_rot, 0), Fg)) == rot and fett(mo.data(ix(r_rot, 0), Fo)),
          f"{farbe(mo.data(ix(r_rot, 0), Fg))}")
    check("0,9 bis 1,0: gelb hinterlegt, Schrift normal",
          farbe(mo.data(ix(r_gelb, 0), Bg)) == gelb and mo.data(ix(r_gelb, 0), Fg) is None
          and not fett(mo.data(ix(r_gelb, 0), Fo)), f"{farbe(mo.data(ix(r_gelb, 0), Bg))}")
    check("bis 0,9: keine Farbe",
          all(mo.data(ix(r_ok, 0), rolle) is None for rolle in (Fg, Bg, Fo)))
    check("„NICHT erfüllt“ steht rot, „erfüllt“ ohne Farbe",
          farbe(mo.data(ix(r_rot, 1), Fg)) == rot and mo.data(ix(r_gelb, 1), Fg) is None)
    check("Spalte ohne Ampel bleibt ohne Farbe, auch bei 1,5",
          all(mo.data(ix(r_rot, 2), rolle) is None for rolle in (Fg, Bg, Fo)))
    check("die Zahl selbst bleibt, wie sie war (Komma, drei Stellen)",
          mo.data(ix(r_rot, 0)) == "1,094" and mo.data(ix(r_rot, 1)) == "NICHT erfüllt",
          str(mo.data(ix(r_rot, 0))))
    ohne = tab.TabellenModell([tab.Spalte("Ausnutzung", "", "zahl", 3), tab.Spalte("Status"),
                               tab.Spalte("σ", "", "zahl", 3)])
    ohne.setzen(zeilen)
    kopf = [s.kopf() for s in sp]
    check("CSV mit und ohne Ampel gleich (die Farbe betrifft nur die Anzeige)",
          tab.als_csv(kopf, mo.zeilen_angezeigt(mo.zeilen))
          == tab.als_csv(kopf, ohne.zeilen_angezeigt(ohne.zeilen)))


def test_absteigend_text_hinten():
    """Absteigend nach Ausnutzung: die groesste Zahl oben, Zeilen ohne Zahl
    („–“ eines nicht gefuehrten Nachweises, leer vor der Rechnung) hinten -
    auch absteigend, sonst stuende „nicht geführt“ ueber dem roten Wert."""
    from PySide6 import QtCore
    from statik3d.gui import tabellen as tab
    _app()
    sp = [tab.Spalte("Stab"), tab.Spalte("Ausnutzung", "", "zahl", 3)]
    zeilen = [["A", 0.5], ["B", "–"], ["C", 1.2], ["D", ""], ["E", 0.9]]
    mo = tab.TabellenModell(sp)
    mo.setzen(zeilen)
    mo.sortieren(1, QtCore.Qt.DescendingOrder)
    ab = [z[0] for z in mo.zeilen]
    check("absteigend: Zahlen der Größe nach oben, Text dahinter",
          ab[:3] == ["C", "E", "A"] and set(ab[3:]) == {"B", "D"}, str(ab))
    mo.sortieren(1, QtCore.Qt.AscendingOrder)
    auf = [z[0] for z in mo.zeilen]
    check("aufsteigend wie bisher: Zahlen, dann Text",
          auf[:3] == ["A", "E", "C"] and set(auf[3:]) == {"B", "D"}, str(auf))
    dt = tab.Datentabelle(sp, "Probe")
    check("Datentabelle.absteigend_nach findet die Spalte",
          dt.absteigend_nach("Ausnutzung") and not dt.absteigend_nach("gibt es nicht"))
    dt.setzen(zeilen)
    check("… und neue Zeilen stehen gleich absteigend",
          [z[0] for z in dt.modell.zeilen][:3] == ["C", "E", "A"]
          and dt.modell.sortierung == (1, QtCore.Qt.DescendingOrder),
          str([z[0] for z in dt.modell.zeilen]))


def _sichtbar(dt, k=0) -> list:
    """Die Werte der Spalte k in der Folge, in der sie zu sehen sind (Proxy)."""
    f = dt.filter
    return [f.data(f.index(r, k)) for r in range(f.rowCount())]


def test_sichtbare_folge():
    """Gegenpruefung 25.09.2026: sortiert wird in der Quelle, der Proxy bekam
    aber die Richtung mit - bei Spalte -1 und absteigend kehrte Qt die Folge
    um. Sichtbar stand der rote Wert unten und „–“/leer oben, obwohl
    modell.zeilen richtig lag; die Pruefungen oben lasen nur modell.zeilen.
    Hier die Folge, wie sie in der Ansicht steht."""
    from PySide6 import QtCore
    from statik3d.gui import tabellen as tab
    _app()
    sp = [tab.Spalte("Stab"), tab.Spalte("Ausnutzung", "", "zahl", 3)]
    zeilen = [["A", 0.5], ["B", "–"], ["C", 1.2], ["D", ""], ["E", 0.9]]
    dt = tab.Datentabelle(sp, "Probe")
    dt.absteigend_nach("Ausnutzung")
    dt.setzen(zeilen)
    s = _sichtbar(dt)
    check("sichtbar absteigend: 1,200 oben, dann 0,900 und 0,500, Text unten",
          s[:3] == ["C", "E", "A"] and set(s[3:]) == {"B", "D"}, str(s))
    kopie = [z[0] for z in dt.sichtbare_zeilen()]
    check("Kopieren/CSV (sichtbare Zeilen) in derselben Folge", kopie == s, str(kopie))
    dt.view.sortByColumn(0, QtCore.Qt.AscendingOrder)
    auf = _sichtbar(dt)
    dt.view.sortByColumn(0, QtCore.Qt.DescendingOrder)
    ab = _sichtbar(dt)
    check("Klick auf „Stab“: sichtbar A…E, dann E…A",
          auf == list("ABCDE") and ab == list("EDCBA"), f"{auf} / {ab}")
    dt.view.sortByColumn(1, QtCore.Qt.AscendingOrder)
    s = _sichtbar(dt)
    check("aufsteigend nach Ausnutzung: sichtbar 0,500 oben, Text unten",
          s[:3] == ["A", "E", "C"] and set(s[3:]) == {"B", "D"}, str(s))


def test_urteil_der_oberflaeche():
    """Das Urteil der Ermuedung bildet gui/main.py (ec3/fatigue.py wird gerade
    von einer anderen Arbeit umgebaut). Es muss dasselbe sagen wie der
    Status im Bericht (fatigue._status) - sonst stuende in Tabelle und
    Protokoll etwas anderes als im Statikdokument."""
    from statik3d.gui.main import MainWindow
    from statik3d.ec3 import fatigue as fat
    faelle = [SimpleNamespace(fehler="keine Last", util=0.0, fehlende_lasten=[]),
              SimpleNamespace(fehler="", util=1.2, fehlende_lasten=[]),
              SimpleNamespace(fehler="", util=1.2, fehlende_lasten=["L2"]),
              SimpleNamespace(fehler="", util=0.5, fehlende_lasten=["L2"]),
              SimpleNamespace(fehler="", util=1.0, fehlende_lasten=[]),
              SimpleNamespace(fehler="", util=0.3)]
    ist = [MainWindow._ermuedung_urteil(x) for x in faelle]
    soll = [fat._status(x) for x in faelle]
    check("Urteil der Oberfläche = Status des Berichts (sechs Fälle)", ist == soll,
          f"{ist} statt {soll}")
    check("… D > 1,0 heißt „NICHT erfüllt“, D = 1,0 noch „erfüllt“",
          ist[1] == "NICHT erfüllt" and ist[4] == "erfüllt", str(ist))
    zusatz = MainWindow._ermuedung_zusatz
    ergebnis = lambda *u: SimpleNamespace(members={f"S{i}": x for i, x in enumerate(u)},
                                          volumen={})
    ok = SimpleNamespace(fehler="", util=0.5, fehlende_lasten=[])
    check("Zeilenende: NICHT erfüllt vor allem anderen",
          zusatz(ergebnis(ok, faelle[1], faelle[0])) == " - NICHT erfüllt")
    check("Zeilenende: erfüllt nur, wenn alles erfüllt ist",
          zusatz(ergebnis(ok, ok)) == " - erfüllt"
          and zusatz(ergebnis(ok, faelle[3])) == " - unvollständig"
          and zusatz(ergebnis(ok, faelle[0])) == " - unvollständig"
          and zusatz(ergebnis(faelle[0])) == " - nicht geführt"
          and zusatz(ergebnis()) == "",
          str([zusatz(ergebnis(ok, faelle[3])), zusatz(ergebnis(faelle[0]))]))


# --------------------------------------------------------------------------
# Mit Hauptfenster (offscreen)
# --------------------------------------------------------------------------
_FENSTER = {}

#: Nachweistabellen und die Spalten mit Ampel
AMPEL = {"tbl_design": ["Ausnutzung", "Status"],
         "tbl_fat": ["D (Miner)", "D Schub", "Ausnutzung", "Status"],
         "tbl_joint": ["Ausnutzung", "D (Ermüdung)", "Status"],
         "tbl_gzg": ["Ausnutzung", "Status"],
         "tbl_beul": ["Ausnutzung", "Status"],
         "tbl_vol": ["Ausnutzung", "Status"],
         "tbl_le": ["Ausnutzung", "Status"]}


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    _FENSTER.update(w=w, app=app)
    return w, app


def _neue_zeilen(w, n0: int) -> list:
    return w.log.toPlainText().splitlines()[n0:]


def _zeilenfarbe(w, text: str):
    """Schriftfarbe des Protokollblocks mit genau diesem Text (oder None)."""
    doc = w.log.document()
    b = doc.begin()
    while b.isValid():
        if b.text() == text:
            it = b.begin()
            while not it.atEnd():
                f = it.fragment()
                if f.isValid() and f.text().strip():
                    return f.charFormat().foreground().color().name()
                it += 1
            return None
        b = b.next()
    return None


def test_spalten_und_sortierung():
    from PySide6 import QtCore
    w, _app_ = _fenster()
    for attr, soll in AMPEL.items():
        t = getattr(w, attr)
        mit = [s.name for s in t.modell.spalten if getattr(s, "ampel", False)]
        check(f"{attr}: Ampel auf {', '.join(soll)}", mit == soll, str(mit))
        k = [s.name for s in t.modell.spalten].index("Ausnutzung")
        check(f"{attr}: startet absteigend nach Ausnutzung",
              t.modell.sortierung == (k, QtCore.Qt.DescendingOrder), str(t.modell.sortierung))
    namen = [s.name for s in w.tbl_fat.modell.spalten]
    check("Tabelle Ermüdung: „Status“ vorletzte, „maßgebend“ letzte Spalte",
          namen[-2:] == ["Status", "maßgebend"], str(namen[-3:]))


def test_nicht_erfuellt_faellt_auf():
    from PySide6 import QtCore, QtGui
    from statik3d.gui import tabellen as tab
    w, app = _fenster()
    m = _modell(N_ROT)
    w._modell_setzen(m); app.processEvents()
    an = solver.solve_all(m, design=True, fatigue=True)
    D = {k: x.util for k, x in an.fatigue.members.items()}
    check("Vorbedingung: Riegel 2 über 1,0, Riegel 3 zwischen 0,9 und 1,0, Riegel 1 darunter",
          D["Riegel 2"] > 1.0 and 0.9 < D["Riegel 3"] <= 1.0 and D["Riegel 1"] <= 0.9
          and an.design is not None and an.design.util_max <= 0.9,
          ", ".join(f"{k} {v:.3f}" for k, v in D.items()))
    w.tabelle_zeigen("Knoten"); app.processEvents()
    n0 = len(w.log.toPlainText().splitlines())
    w._solve_done("all", an); app.processEvents()

    zeilen = w.tbl_fat.modell.zeilen
    k_st = [s.name for s in w.tbl_fat.modell.spalten].index("Status")
    k_u = [s.name for s in w.tbl_fat.modell.spalten].index("Ausnutzung")
    check("Tabelle Ermüdung startet mit dem größten D (Riegel 2)",
          [str(z[0]) for z in zeilen] == ["Riegel 2", "Riegel 3", "Riegel 1"],
          str([z[0] for z in zeilen]))
    check("… auch sichtbar in der Ansicht (Proxy): Riegel 2 oben",
          [str(x) for x in _sichtbar(w.tbl_fat)] == ["Riegel 2", "Riegel 3", "Riegel 1"],
          str(_sichtbar(w.tbl_fat)))
    # rechts (Maske Ergebnisse nach F5) und in der Maske Nachweise dasselbe
    # Urteil wie im Protokoll (Gegenpruefung 25.09.2026)
    res = [z for z in w.txt_res.toPlainText().splitlines() if z.startswith("Ermüdung:")]
    check("Maske Ergebnisse: Ermüdungszeile endet mit „NICHT erfüllt“",
          len(res) == 1 and res[0].endswith(" - NICHT erfüllt"), str(res))
    eti = [z for z in w.lbl_design.text().splitlines() if z.startswith("Ermüdung:")]
    check("Maske Nachweise: Ermüdungszeile endet mit „NICHT erfüllt“",
          len(eti) == 1 and eti[0].endswith(" - NICHT erfüllt"), str(eti))
    check("Status je Zeile wie im Bericht",
          all(z[k_st] == an.fatigue.members[str(z[0])].status() for z in zeilen)
          and zeilen[0][k_st] == "NICHT erfüllt",
          str([z[k_st] for z in zeilen]))
    check("„maßgebend“ bleibt die letzte Spalte (Text aus fatigue.table)",
          all(str(z[-1]) == str(r[-1]) for z, r in
              zip(zeilen, sorted(an.fatigue.table()[1:], key=lambda r: -float(r[7])))),
          str(zeilen[0][-1])[:50])
    mo = w.tbl_fat.modell
    Fg, Bg, Fo = QtCore.Qt.ForegroundRole, QtCore.Qt.BackgroundRole, QtCore.Qt.FontRole
    rot, gelb = QtGui.QColor(tab.AMPEL_ROT).name(), QtGui.QColor(tab.AMPEL_GELB).name()

    def farbe(r, k, rolle):
        x = mo.data(mo.index(r, k), rolle)
        if x is None:
            return None
        return (x.color() if isinstance(x, QtGui.QBrush) else QtGui.QColor(x)).name()

    check("Riegel 2: Ausnutzung rot und fett, Status rot",
          farbe(0, k_u, Fg) == rot and QtGui.QFont(mo.data(mo.index(0, k_u), Fo)).bold()
          and farbe(0, k_st, Fg) == rot)
    check("Riegel 3: Ausnutzung gelb hinterlegt", farbe(1, k_u, Bg) == gelb)
    check("Riegel 1: ohne Farbe", farbe(2, k_u, Fg) is None and farbe(2, k_u, Bg) is None)

    neu = _neue_zeilen(w, n0)
    erm = [z for z in neu if z.startswith("Ermüdung:")]
    check("Protokollzeile zur Ermüdung endet mit „NICHT erfüllt“",
          len(erm) == 1 and erm[0].endswith(" - NICHT erfüllt"), str(erm))
    sammel = [z for z in neu if z.startswith("Nachweise: ")]
    soll = "Nachweise: 1 NICHT erfüllt (Ermüdung Riegel 2)"
    check("rote Sammelzeile nach der Rechnung, einmal", sammel == [soll], str(sammel))
    check("… und sie steht rot im Protokoll", _zeilenfarbe(w, soll) == rot,
          str(_zeilenfarbe(w, soll)))
    w.log.appendPlainText("Probe danach")
    f_danach = _zeilenfarbe(w, "Probe danach")
    check("die Zeile danach ist nicht mehr rot", f_danach != rot, str(f_danach))
    # Klick in die rote Zeile setzt den Textcursor dorthin - die naechste
    # Zeile darf das Rot trotzdem nicht erben
    b = w.log.document().findBlockByLineNumber(0)
    while b.isValid() and b.text() != soll:
        b = b.next()
    c = w.log.textCursor()
    c.setPosition(b.position() + 3)
    w.log.setTextCursor(c)
    w.log.appendPlainText("Probe nach Klick")
    f_klick = _zeilenfarbe(w, "Probe nach Klick")
    check("… auch nicht, wenn der Cursor in der roten Zeile steht", f_klick != rot, str(f_klick))
    pfad = getattr(w, "_protokollpfad", "")
    if pfad and os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            datei = f.read()
        check("die Sammelzeile steht auch in der Protokolldatei", soll in datei)
    tu = w.tab_unten
    check("unten springt die Tabelle Ermüdung nach vorn (nicht das Protokoll)",
          tu.currentWidget() is w.tbl_fat, f"{tu.currentGroup()} / {tu.tabText(tu.currentIndex())}")

    # Gegenprobe: alles erfuellt - kein Sprung, keine Sammelzeile
    m2 = _modell(N_GRUEN)
    w._modell_setzen(m2); app.processEvents()
    an2 = solver.solve_all(m2, design=True, fatigue=True)
    check("Vorbedingung: alle Ermüdungsnachweise erfüllt",
          all(x.util <= 0.9 for x in an2.fatigue.members.values()))
    w.tabelle_zeigen("Knoten"); app.processEvents()
    n0 = len(w.log.toPlainText().splitlines())
    w._solve_done("all", an2); app.processEvents()
    neu = _neue_zeilen(w, n0)
    erm = [z for z in neu if z.startswith("Ermüdung:")]
    check("alles erfüllt: die Zeile endet mit „erfüllt“",
          len(erm) == 1 and erm[0].endswith(" - erfüllt"), str(erm))
    check("… keine Sammelzeile", not [z for z in neu if z.startswith("Nachweise: ")])
    check("… und unten bleibt, was offen war (Knoten)",
          tu.tabText(tu.currentIndex()) == "Knoten" and tu.currentGroup() == "Modell",
          f"{tu.currentGroup()} / {tu.tabText(tu.currentIndex())}")


def test_ec3_und_ermuedung():
    """Zwei Nachweise nicht erfuellt: beide in der Sammelzeile, vorn die
    erste Nachweistabelle in der Folge des unteren Bereichs (Nachweise EC3)."""
    w, app = _fenster()
    m = _modell(1e5, f2=40e3)
    w._modell_setzen(m); app.processEvents()
    an = solver.solve_all(m, design=True, fatigue=True)
    check("Vorbedingung: Riegel 2 in EC3 und Ermüdung über 1,0",
          an.design.members["Riegel 2"].util > 1.0 and an.fatigue.members["Riegel 2"].util > 1.0,
          f"{an.design.members['Riegel 2'].util:.3f} / {an.fatigue.members['Riegel 2'].util:.3f}")
    w.tabelle_zeigen("Knoten"); app.processEvents()
    n0 = len(w.log.toPlainText().splitlines())
    w._solve_done("all", an); app.processEvents()
    sammel = [z for z in _neue_zeilen(w, n0) if z.startswith("Nachweise: ")]
    check("Sammelzeile nennt beide", sammel == [
        "Nachweise: 2 NICHT erfüllt (EC3 Riegel 2, Ermüdung Riegel 2)"], str(sammel))
    check("vorn steht die Tabelle Nachweise EC3", w.tab_unten.currentWidget() is w.tbl_design)
    check("… mit Riegel 2 oben, auch sichtbar",
          str(w.tbl_design.modell.zeilen[0][0]) == "Riegel 2"
          and str(_sichtbar(w.tbl_design)[0]) == "Riegel 2",
          f"{[z[0] for z in w.tbl_design.modell.zeilen]} / {_sichtbar(w.tbl_design)}")


def test_ermuedung_einzeln():
    """Ribbon „Ermüdung“ (do_fatigue -> _fatigue_done): dieselbe Zeile mit
    Urteil, dieselbe Sammelzeile, derselbe Sprung."""
    from statik3d.ec3.fatigue import check_fatigue
    w, app = _fenster()
    m = _modell(N_ROT)
    w._modell_setzen(m); app.processEvents()
    an = solver.solve_all(m, design=True, fatigue=False)
    w._solve_done("all", an); app.processEvents()
    w.tabelle_zeigen("Knoten"); app.processEvents()
    n0 = len(w.log.toPlainText().splitlines())
    w._fatigue_done(check_fatigue(m, an)); app.processEvents()
    neu = _neue_zeilen(w, n0)
    erm = [z for z in neu if z.startswith("Ermüdung:")]
    check("Ermüdung einzeln: Zeile endet mit „NICHT erfüllt“",
          erm and erm[0].endswith(" - NICHT erfüllt"), str(erm))
    check("… Sammelzeile", [z for z in neu if z.startswith("Nachweise: ")]
          == ["Nachweise: 1 NICHT erfüllt (Ermüdung Riegel 2)"])
    check("… Tabelle Ermüdung vorn", w.tab_unten.currentWidget() is w.tbl_fat)


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung (25.09.2026)
# --------------------------------------------------------------------------
def _formate_ab(w, n0: int) -> list:
    """[(Text, Farbe, fett)] der Protokollbloecke ab Blocknummer n0 - je Block
    das Format des ersten Zeichens mit Text."""
    doc = w.log.document()
    aus = []
    b = doc.findBlockByNumber(n0)
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            f = it.fragment()
            if f.isValid() and f.text().strip():
                cf = f.charFormat()
                aus.append((b.text(), cf.foreground().color().name(), cf.fontWeight() > 400))
                break
            it += 1
        b = b.next()
    return aus


def _block_markieren(w, nummer: int, rueckwaerts: bool = False) -> None:
    """Einen Protokollblock markieren wie mit einem Dreifachklick."""
    from PySide6 import QtGui
    b = w.log.document().findBlockByNumber(nummer)
    a, e = b.position(), b.position() + b.length() - 1
    c = w.log.textCursor()
    c.setPosition(e if rueckwaerts else a)
    c.setPosition(a if rueckwaerts else e, QtGui.QTextCursor.KeepAnchor)
    w.log.setTextCursor(c)


def test_markierte_rote_zeile():
    """Befund der Gegenpruefung: war die rote Sammelzeile markiert (zum
    Kopieren), wurden alle folgenden Zeilen rot und fett - oder die naechste
    Sammelzeile setzte die Markierung samt Rot auf Standard zurueck.
    Jetzt schreibt das Protokoll mit eigenem Cursor."""
    from statik3d.gui import tabellen as tab
    from PySide6 import QtGui
    w, app = _fenster()
    rot = QtGui.QColor(tab.AMPEL_ROT).name()
    for rueck in (False, True):
        richtung = "rückwärts" if rueck else "vorwärts"
        w._protokoll_rot("Probe rot A")
        n_a = w.log.document().blockCount() - 1
        _block_markieren(w, n_a, rueck)
        w.log.appendPlainText("nach Markierung")
        w.log.appendPlainText("noch eine Zeile")
        w._protokoll_rot("Probe rot B")
        w.log.appendPlainText("nach der zweiten")
        f = _formate_ab(w, n_a)
        check(f"Markierung {richtung}: die Zeilen danach schwarz und nicht fett",
              [x[1:] for x in f if x[0] in ("nach Markierung", "noch eine Zeile",
                                             "nach der zweiten")]
              == [(QtGui.QColor("black").name(), False)] * 3, str(f))
        check(f"Markierung {richtung}: beide roten Zeilen bleiben rot und fett",
              [x[1:] for x in f if x[0].startswith("Probe rot")] == [(rot, True)] * 2, str(f))
        check(f"Markierung {richtung}: die Markierung des Anwenders bleibt",
              w.log.textCursor().hasSelection()
              and w.log.textCursor().selectedText() == "Probe rot A",
              repr(w.log.textCursor().selectedText()))
        w.log.moveCursor(QtGui.QTextCursor.End)

    # Der echte Weg: Sammelzeile markieren, dann rechnen - einmal ohne Befund
    # (aktiver Lastfall), einmal wieder nicht erfuellt
    m = _modell(N_ROT)
    w._modell_setzen(m); app.processEvents()
    an = solver.solve_all(m, design=True, fatigue=True)
    w._solve_done("all", an); app.processEvents()
    soll = "Nachweise: 1 NICHT erfüllt (Ermüdung Riegel 2)"
    n_s = w.log.document().blockCount() - 1
    check("Vorbedingung: letzte Zeile ist die Sammelzeile",
          w.log.document().findBlockByNumber(n_s).text() == soll)
    _block_markieren(w, n_s)
    n0 = w.log.document().blockCount()
    w._solve_done("case", solver.solve_static(m)); app.processEvents()
    f = _formate_ab(w, n0)
    check("nach „aktiver Lastfall“: keine der neuen Zeilen rot",
          f and not any(x[1] == rot or x[2] for x in f), str([x for x in f if x[1] == rot][:3]))
    n0 = w.log.document().blockCount()
    w._solve_done("all", an); app.processEvents()
    f = _formate_ab(w, n0)
    check("wieder nicht erfüllt: die neue Sammelzeile rot und fett, die übrigen nicht",
          [x[1:] for x in f if x[0] == soll] == [(rot, True)]
          and not any(x[1] == rot for x in f if x[0] != soll), str([x for x in f if x[1] == rot]))
    check("… und die markierte alte Sammelzeile bleibt rot",
          _formate_ab(w, n_s)[0] == (soll, rot, True), str(_formate_ab(w, n_s)[:1]))
    w.log.moveCursor(QtGui.QTextCursor.End)


def test_modellwechsel_leert_nachweistabellen():
    """Befund der Gegenpruefung: nach dem Wechsel auf ein Modell ohne
    Ermuedungsnachweis standen die roten Zeilen des vorigen weiter da."""
    w, app = _fenster()
    m = _modell(N_ROT)
    w._modell_setzen(m); app.processEvents()
    w._solve_done("all", solver.solve_all(m, design=True, fatigue=True)); app.processEvents()
    check("Vorbedingung: Nachweise EC3 und Ermüdung gefüllt",
          w.tbl_fat.zeilenzahl() == 3 and w.tbl_design.zeilenzahl() == 3)
    # dasselbe Modell ohne Nachweise gerechnet (F5 ohne EC3 und Ermuedung)
    w._solve_done("all", solver.solve_all(m, design=False, fatigue=False)); app.processEvents()
    check("Rechnung ohne Nachweise: beide Tabellen leer",
          w.tbl_fat.zeilenzahl() == 0 and w.tbl_design.zeilenzahl() == 0,
          f"{w.tbl_fat.zeilenzahl()} / {w.tbl_design.zeilenzahl()}")
    w._solve_done("all", solver.solve_all(m, design=True, fatigue=True)); app.processEvents()
    w.load_example("frame"); app.processEvents()
    check("anderes Modell geladen (Beispiel): beide Tabellen leer",
          w.tbl_fat.zeilenzahl() == 0 and w.tbl_design.zeilenzahl() == 0,
          f"{w.tbl_fat.zeilenzahl()} / {w.tbl_design.zeilenzahl()}")


def test_fuenf_weitere_nachweisarten():
    """Befund der Gegenpruefung: Anschluesse, Verformungen, Beulfelder,
    Volumen und Lasteinleitung haengen in _nachweise_nicht_erfuellt an
    Feldnamen als Text - ein umbenanntes Feld schaltete die Sammelzeile still
    ab. Die Attrappe steckt deshalb in den echten Ergebnisklassen."""
    from statik3d.joints.anschluss import AnschlussResults
    from statik3d.gzg import GZGResults
    from statik3d.ec3.beulen import BeulResults, EinleitungResults
    from statik3d.ec3.volumen import VolumenResults
    w, app = _fenster()
    x = SimpleNamespace(status=lambda: "NICHT erfüllt")
    arten = [("joints", AnschlussResults(joints={"X1": x}), "Anschluss", w.tbl_joint),
             ("gzg", GZGResults(checks={"X1": x}), "Verformung", w.tbl_gzg),
             ("beulen", BeulResults(felder={"X1": x}), "Beulfeld", w.tbl_beul),
             ("volumen", VolumenResults(bereiche={"X1": x}), "Volumen", w.tbl_vol),
             ("lasteinleitung", EinleitungResults(stellen={"X1": x}), "Lasteinleitung", w.tbl_le)]
    alt = w.analysis
    try:
        for attr, erg, vorsatz, tabelle in arten:
            an = SimpleNamespace(design=None, fatigue=None, joints=None, gzg=None,
                                 beulen=None, volumen=None, lasteinleitung=None)
            setattr(an, attr, erg)
            w.analysis = an
            w.tabelle_zeigen("Knoten"); app.processEvents()
            n0 = len(w.log.toPlainText().splitlines())
            w._nachweise_melden(); app.processEvents()
            sammel = [z for z in _neue_zeilen(w, n0) if z.startswith("Nachweise: ")]
            vorn = w.tab_unten.currentWidget()
            check(f"{vorsatz}: Sammelzeile und unten die richtige Tabelle",
                  sammel == [f"Nachweise: 1 NICHT erfüllt ({vorsatz} X1)"]
                  and vorn is not None and (vorn is tabelle or vorn.isAncestorOf(tabelle)),
                  f"{sammel} / {w.tab_unten.tabText(w.tab_unten.currentIndex())}")
    finally:
        w.analysis = alt

    # ein echter Fall: Verformungsgrenze L/30000 an der Halle
    w.load_example("hall"); app.processEvents()
    m = w.model
    m.add_verformungsgrenze("Durchbiegung Riegel", "stab", stab="Riegel", groesse="uz",
                            grenzart="L/x", wert=30000, situation="SLS_CH")
    w.refresh_all(); app.processEvents()
    an = solver.solve_all(m, design=True)
    check("Vorbedingung: Verformung nicht erfüllt",
          "NICHT" in an.gzg.checks["Durchbiegung Riegel"].status())
    w.tabelle_zeigen("Knoten"); app.processEvents()
    n0 = len(w.log.toPlainText().splitlines())
    w._solve_done("all", an); app.processEvents()
    sammel = [z for z in _neue_zeilen(w, n0) if z.startswith("Nachweise: ")]
    vorn = w.tab_unten.currentWidget()
    check("Halle mit L/30000: Sammelzeile nennt die Verformung, unten „Verformungen“",
          len(sammel) == 1 and "Verformung Durchbiegung Riegel" in sammel[0]
          and vorn is not None and (vorn is w.tbl_gzg or vorn.isAncestorOf(w.tbl_gzg)),
          f"{sammel} / {w.tab_unten.tabText(w.tab_unten.currentIndex())}")


def test_design_einzeln_und_eigenformen():
    """Befund der Gegenpruefung: die Sammelzeile nach „Nachweise EC3“ aus dem
    Menueband und ihr Ausbleiben nach Eigenformen/Knicken waren ungeprueft."""
    from statik3d.ec3.design import check_members
    w, app = _fenster()
    m = _modell(1e5, f2=40e3)
    w._modell_setzen(m); app.processEvents()
    w._solve_done("all", solver.solve_all(m, design=False, fatigue=False)); app.processEvents()
    w.tabelle_zeigen("Knoten"); app.processEvents()
    n0 = len(w.log.toPlainText().splitlines())
    w._design_done(check_members(m, w.analysis)); app.processEvents()
    sammel = [z for z in _neue_zeilen(w, n0) if z.startswith("Nachweise: ")]
    check("Nachweise EC3 einzeln: Sammelzeile, unten Nachweise EC3",
          sammel == ["Nachweise: 1 NICHT erfüllt (EC3 Riegel 2)"]
          and w.tab_unten.currentWidget() is w.tbl_design, str(sammel))
    n0 = len(w.log.toPlainText().splitlines())
    w._solve_done("modal", solver.solve_modal(m, 2)); app.processEvents()
    check("danach Eigenformen: keine zweite Sammelzeile",
          not [z for z in _neue_zeilen(w, n0) if z.startswith("Nachweise: ")]
          and w.analysis.design is not None)


def test_freie_bewegung_behaelt_statuszeile():
    """Befund der Gegenpruefung: die Sammelzeile verdraengte die Warnung zu
    freien Bewegungen mit Last aus der Statuszeile. Die Warnung bleibt; die
    Sammelzeile steht im Protokoll, unten springt die Tabelle."""
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    w, app = _fenster()
    m = Model("frei")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section("IPE 200"))
    m.case().category = "G"
    ids = mesher.line_of_beams(m, "S235", "IPE 200", (0, 0, 0), (4, 0, 0), 4)
    m.fix(ids[0], [0, 1, 2, 3, 4, 5])
    m.load_node(ids[-1], Fz=-80e3)
    m.add_member("Kragarm", list(range(4)))
    ids2 = mesher.line_of_beams(m, "S235", "IPE 200", (0, 3, 0), (2, 3, 0), 2)   # schwebt frei
    m.load_node(ids2[-1], Fz=-1e3)
    m.add_combination("K1", {list(m.load_cases)[0]: 1.35}, "ULS")
    w._modell_setzen(m); app.processEvents()
    an = solver.solve_all(m, design=True)
    check("Vorbedingung: EC3 Kragarm nicht erfüllt",
          "NICHT" in an.design.members["Kragarm"].status())
    n0 = len(w.log.toPlainText().splitlines())
    w._solve_done("all", an); app.processEvents()
    msg = w.statusBar().currentMessage()
    check("Statuszeile: die Warnung zu freien Bewegungen bleibt", msg.startswith("⚠"), msg[:100])
    check("… die Sammelzeile steht trotzdem im Protokoll",
          [z for z in _neue_zeilen(w, n0) if z.startswith("Nachweise: ")]
          == ["Nachweise: 1 NICHT erfüllt (EC3 Kragarm)"])
    # Gegenprobe: ohne freie Bewegung steht die Sammelzeile in der Statuszeile
    m2 = _modell(N_ROT)
    w._modell_setzen(m2); app.processEvents()
    w._solve_done("all", solver.solve_all(m2, design=True, fatigue=True)); app.processEvents()
    check("ohne freie Bewegung: die Sammelzeile in der Statuszeile",
          w.statusBar().currentMessage() == "Nachweise: 1 NICHT erfüllt (Ermüdung Riegel 2)",
          w.statusBar().currentMessage()[:100])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_ampelstufe, test_ampel_im_modell, test_absteigend_text_hinten,
              test_sichtbare_folge,
              test_urteil_der_oberflaeche, test_spalten_und_sortierung,
              test_nicht_erfuellt_faellt_auf, test_ec3_und_ermuedung,
              test_ermuedung_einzeln, test_markierte_rote_zeile,
              test_modellwechsel_leert_nachweistabellen, test_fuenf_weitere_nachweisarten,
              test_design_einzeln_und_eigenformen, test_freie_bewegung_behaelt_statuszeile):
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
