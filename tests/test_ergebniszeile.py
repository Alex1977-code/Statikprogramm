"""
Ergebniszeile unten, Stabkräfte und Auflager bei einer Umhüllenden,
Kombinationszelle (Teilpaket 10c des Oberflächenplans, 03.10.2026).

Befund am Stand 7a4a895 (Beispiel hall, gerechnet): Welches Ergebnis die
Tabellen unten zeigen, stand nur oben rechts (Ergebnissteuerung) und in der
Glasleiste. Bei einer Umhüllenden blieb „Stabkräfte“ leer mit dem Satz „die
Umhüllende zeigt ihre Extremwerte im Register „Umhüllende“ …“, und das
Register sprang auf „Umhüllende“. Die Auflagerkräfte einer Umhüllenden standen
als Text „-12,34 / 56,78“ in einer Zelle - nicht sortier- und filterbar wie
Zahlen, ohne Summe. Die Zelle „Kombination“ war nur Text.

Geprüft wird:

* die Ergebniswahl unten steht in der Kopfzeile der Gruppen Ergebnisse und
  Nachweise (nicht in den übrigen), führt dieselben Einträge wie die
  Ergebnissteuerung oben rechts und ist mit ihr und der Glasleiste in beiden
  Richtungen gleich - ein Wechsel füllt die Tabellen genau einmal;
* Stabkräfte bei einer Umhüllenden: je Element min und max von N, Vz, My, Mz
  mit der maßgebenden Kombination je Wert; die Zahlen gegen die Umhüllende und
  unabhängig gegen die Schnittgrößen der einzelnen Kombinationen geprüft;
* Auflager: einzelnes Ergebnis mit Summenzeile Σ (gegen die Summe der
  Reaktionen), Umhüllende mit min und max als Zahlenspalten und einer Zeile,
  die sagt, warum es dort keine Summe gibt;
* ein Klick auf die Zelle mit der maßgebenden Kombination schaltet das
  Ergebnis - Ergebniszeile, Ergebnissteuerung, Glasleiste, Bild und Tabellen;
* eine Umhüllende aus einer alten Ergebnisdatei ohne Stabschnittgrößen
  erklärt, warum „Stabkräfte“ leer ist;
* die Ergebniswahl kostet die Tabelle keine Höhe, und im Kopf bleibt alles
  erreichbar (Maße mit Schrift: python scratchpad/mit_schrift.py <Baum>
  tests.test_ergebniszeile; ohne Schrift sind Breiten Kästchenwerte).

Aufruf:  python -m tests.test_ergebniszeile
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ.pop("STATIK3D_FENSTER", None)
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ergebniszeile_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_F = {}

#: Spalten der Stabkräfte bei einer Umhüllenden - dieselben Größen wie beim
#: einzelnen Ergebnis (N, Vz, My, Mz), je min und max mit Kombination
STAB_HUELLE = ["Element"] + [x for g in ("N", "Vz", "My", "Mz")
                             for x in (f"{g} min", "Komb.", f"{g} max", "Komb.")] + ["Ausn."]
STAB_EINZEL = ["Element", "N1", "N2", "Vz1", "Vz2", "My1", "My2", "Mz max", "σ", "Ausn."]
AUFLAGER_EINZEL = ["Knoten", "Rx", "Ry", "Rz", "Mx", "My", "Mz"]
AUFLAGER_HUELLE = ["Knoten"] + [f"{g} {s}" for g in ("Rx", "Ry", "Rz", "Mx", "My", "Mz")
                                for s in ("min", "max")]


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
    w.meldungen = []
    w.error = lambda msg, *a, **k: w.fehler.append(str(msg))
    w.info = lambda msg, *a, **k: w.meldungen.append(str(msg))
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    w.show()
    _ruhe()
    w.resize(1920, 1080)
    _ruhe()
    _F["w"] = w
    return w


def _hall(w):
    """Beispiel hall, gerechnet mit EC3 (Kombinationen, vier Umhüllende)."""
    if _F.get("hall") is w.model and w.analysis is not None:
        return w.analysis
    from statik3d import solver
    w.load_example("hall")
    _ruhe()
    an = solver.solve_all(w.model, design=True)
    w._solve_done("all", an)
    _ruhe()
    _F["hall"] = w.model
    return an


def _index(w, art, name=None):
    """Der Eintrag der Ergebnissteuerung mit diesen Daten (oder der erste der Art)."""
    cb = w.cb_result
    for i in range(cb.count()):
        d = cb.itemData(i)
        if d and d[0] == art and (name is None or d[1] == name):
            return i
    return -1


def _namen(t):
    return [sp.name for sp in t.modell.spalten]


def _zeile(t, schluessel):
    for z in t.modell.zeilen:
        if int(z[0]) == int(schluessel):
            return z
    return None


# --------------------------------------------------------------------------
def test_ergebniszeile_gleich():
    from PySide6 import QtTest
    w = _fenster()
    an = _hall(w)
    tu = w.tab_unten
    cb = getattr(w, "cb_ergebnis_unten", None)
    if not check("Ergebniswahl unten vorhanden", cb is not None):
        return
    sichtbar = {}
    for tabelle in ("Stabkräfte", "Nachweise EC3", "Knoten", "Lasten", "Protokoll"):
        w.tabelle_zeigen(tabelle)
        _ruhe()
        sichtbar[tu.currentGroup()] = cb.isVisible()
    check("sie steht in den Gruppen Ergebnisse und Nachweise, in den übrigen nicht",
          sichtbar == {"Ergebnisse": True, "Nachweise": True, "Modell": False, "Lasten": False,
                       "Protokoll": False}, str(sichtbar))
    w.tabelle_zeigen("Stabkräfte")
    _ruhe()
    check("… in der Kopfzeile unten (dieselbe Zeile wie Gruppe und Reiter)",
          tu.kopf.isAncestorOf(cb), cb.parentWidget().objectName())
    oben = [(w.cb_result.itemText(i), w.cb_result.itemData(i)) for i in range(w.cb_result.count())]
    unten = [(cb.itemText(i), cb.itemData(i)) for i in range(cb.count())]
    check("dieselben Einträge wie die Ergebnissteuerung oben rechts (Umhüllende, Kombinationen, Lastfälle)",
          oben == unten and len(oben) == len(an.envelopes) + len(an.combinations) + len(an.cases),
          f"{len(unten)} Einträge, oben {len(oben)}")
    gezaehlt = {"fuellen": 0}
    alt_setzen = w.tbl_beam.setzen

    def zaehlen(*a, **k):
        gezaehlt["fuellen"] += 1
        return alt_setzen(*a, **k)
    w.tbl_beam.setzen = zaehlen
    spy_oben = QtTest.QSignalSpy(w.cb_result.currentIndexChanged)
    try:
        # oben rechts -> unten und Glasleiste
        k = _index(w, "combo", "GZT7")
        w.cb_result.setCurrentIndex(k)
        _ruhe()
        check("oben rechts gewählt (Kombination GZT7): unten und Glasleiste zeigen sie",
              cb.currentIndex() == k and cb.currentText() == w.cb_result.currentText()
              and tuple(w.cb_lastwahl.currentData() or ()) == ("combo", "GZT7"),
              f"unten {cb.currentText()[:30]!r}, Glasleiste {w.cb_lastwahl.currentData()}")
        # unten -> oben rechts und Glasleiste, genau einmal gefuellt
        gezaehlt["fuellen"] = 0
        n0 = spy_oben.count()
        k = _index(w, "env", "ULS")
        cb.setCurrentIndex(k)
        _ruhe()
        check("unten gewählt (Umhüllende GZT): oben rechts, Glasleiste und Bild folgen",
              w.cb_result.currentIndex() == k and tuple(w.cb_lastwahl.currentData() or ()) == ("env", "ULS")
              and w.current_result() is an.envelopes["ULS"] and w._lastwahl_ziel() == ("env", "ULS"),
              f"oben {w.cb_result.currentText()!r}, Glasleiste {w.cb_lastwahl.currentData()}")
        check("… ohne Schleife: oben rechts wechselt einmal, die Stabkräfte werden einmal gefüllt",
              spy_oben.count() - n0 == 1 and gezaehlt["fuellen"] == 1,
              f"Wechsel oben {spy_oben.count() - n0}, gefüllt {gezaehlt['fuellen']}")
        # Glasleiste -> oben und unten
        gl = w.cb_lastwahl
        j = next(i for i in range(gl.count()) if tuple(gl.itemData(i) or ()) == ("combo", "GZT3"))
        gezaehlt["fuellen"] = 0
        n0 = spy_oben.count()
        gl.setCurrentIndex(j)
        _ruhe()
        check("in der Glasleiste gewählt (Kombination GZT3): oben rechts und unten folgen, einmal gefüllt",
              w.cb_result.currentData() == ("combo", "GZT3") and cb.currentData() == ("combo", "GZT3")
              and spy_oben.count() - n0 == 1 and gezaehlt["fuellen"] == 1,
              f"unten {cb.currentData()}, Wechsel {spy_oben.count() - n0}, gefüllt {gezaehlt['fuellen']}")
    finally:
        del w.tbl_beam.setzen
    # neu gerechnet: die Liste wird neu gefuellt, unten zeigt, was oben steht
    from statik3d import solver
    an2 = solver.solve_all(w.model, design=True)
    w._solve_done("all", an2)
    _ruhe()
    check("nach neuer Rechnung (Liste neu gefüllt): unten dieselben Einträge und dieselbe Wahl wie oben",
          cb.count() == w.cb_result.count() and cb.currentIndex() == w.cb_result.currentIndex()
          and cb.currentText() == w.cb_result.currentText(), f"{cb.currentText()!r} / {w.cb_result.currentText()!r}")


def _huelle_unabhaengig(an, env, i, groesse):
    """min und max einer Schnittgröße eines Elements aus den einzelnen
    Kombinationen (ihren Stationen) - ohne die Umhüllende: (min, {Kombinationen
    mit min}, max, {Kombinationen mit max})."""
    n = env.n_stations
    werte = {}
    for name in env.names:
        st = an.combinations[name].stations(n)
        werte[name] = np.asarray(st[i][groesse], float) if i in st else np.zeros(n)
    mn = min(float(v.min()) for v in werte.values())
    mx = max(float(v.max()) for v in werte.values())
    tol = 1e-9 * max(1.0, abs(mn), abs(mx))
    return (mn, {k for k, v in werte.items() if abs(float(v.min()) - mn) <= tol},
            mx, {k for k, v in werte.items() if abs(float(v.max()) - mx) <= tol})


def test_stabkraefte_umhuellende():
    w = _fenster()
    an = _hall(w)
    env = an.envelopes["ULS"]
    w.tabelle_zeigen("Stabkräfte")
    _ruhe()
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    t = w.tbl_beam
    check("Umhüllende: „Stabkräfte“ zeigt Spalten min und max mit Kombination je Wert",
          _namen(t) == STAB_HUELLE, str(_namen(t)))
    check("… eine Zeile je Element der Umhüllenden, ohne Erklärsatz, das Register bleibt",
          t.zeilenzahl() == len(env.beam) > 0 and not t.lbl_leer.isVisible()
          and w.tab_unten.currentWidget() is t, f"{t.zeilenzahl()} Zeilen, Umhüllende {len(env.beam)}")
    namen = _namen(t)
    falsch, unabh = [], []
    n_unabh = 0
    for i, d in env.beam.items():
        z = _zeile(t, i)
        if z is None:
            falsch.append(f"Element {i} fehlt")
            continue
        for g in ("N", "Vz", "My", "Mz"):
            mn, mx, imn, imx = d[g]
            j1, j2 = int(np.argmin(mn)), int(np.argmax(mx))
            k = namen.index(f"{g} min")
            soll = (mn[j1] / 1e3, env.names[int(imn[j1])], mx[j2] / 1e3, env.names[int(imx[j2])])
            ist = (z[k], z[k + 1], z[k + 2], z[k + 3])
            if abs(ist[0] - soll[0]) > 1e-9 or abs(ist[2] - soll[2]) > 1e-9 or ist[1] != soll[1] \
                    or ist[3] != soll[3]:
                falsch.append(f"{i}/{g}: {ist} statt {soll}")
            # unabhaengig: aus den Kombinationen selbst
            n_unabh += 1
            u_mn, u_kmn, u_mx, u_kmx = _huelle_unabhaengig(an, env, i, g)
            if abs(ist[0] - u_mn / 1e3) > 1e-6 * max(1.0, abs(u_mn / 1e3)) or ist[1] not in u_kmn \
                    or abs(ist[2] - u_mx / 1e3) > 1e-6 * max(1.0, abs(u_mx / 1e3)) or ist[3] not in u_kmx:
                unabh.append(f"{i}/{g}: {ist[:2]} {ist[2:]} / {u_mn / 1e3:.4f} {sorted(u_kmn)[:2]} "
                             f"{u_mx / 1e3:.4f} {sorted(u_kmx)[:2]}")
    check("… die Werte und Kombinationen stimmen mit der Umhüllenden überein (alle Elemente, N, Vz, My, Mz)",
          not falsch, "; ".join(falsch[:3]))
    check("… und unabhängig mit min/max über die Stationen der einzelnen Kombinationen",
          not unabh and n_unabh == 4 * len(env.beam) > 0, f"{n_unabh} Werte; " + "; ".join(unabh[:2]))
    k = namen.index("Komb.")
    check("die Kombinationsspalten sind als anklickbar gekennzeichnet (Spalte „ergebnis“)",
          all(sp.ergebnis for sp in t.modell.spalten if sp.name == "Komb.")
          and not any(sp.ergebnis for sp in t.modell.spalten if sp.name != "Komb."), "")
    from PySide6 import QtCore
    tip = t.modell.data(t.modell.index(0, k), QtCore.Qt.ToolTipRole) or ""
    check("… mit Hinweis am Zeiger, dass ein Klick dieses Ergebnis zeigt",
          str(t.modell.zeilen[0][k]) in tip and "Klick" in tip, tip)
    check("Max/Min darunter (18 Elemente), die Zahlenspalten sind Zahlen",
          not t.fuss.isHidden() and t.fussmodell.rowCount() == 2
          and all(isinstance(t.modell.zeilen[0][namen.index(n)], float) for n in ("N min", "Mz max")),
          f"Fuß {t.fussmodell.rowCount()} Zeilen")
    # zurueck zu einer Kombination: die gewohnten Spalten, gefuellt aus beam_forces
    w.cb_result.setCurrentIndex(_index(w, "combo", "GZT7"))
    _ruhe()
    r = an.combinations["GZT7"]
    e0 = sorted(r.beam_forces)[0]
    z = _zeile(t, e0)
    check("zurück zur Kombination: die Spalten des einzelnen Ergebnisses, N1 aus den Stabendkräften",
          _namen(t) == STAB_EINZEL and z is not None and abs(z[1] - r.beam_forces[e0]["N"][0] / 1e3) < 1e-9,
          str(_namen(t)[:4]))


def test_auflager():
    from PySide6 import QtCore
    w = _fenster()
    an = _hall(w)
    w.tabelle_zeigen("Auflagerkräfte")
    _ruhe()
    t = w.tbl_react
    w.cb_result.setCurrentIndex(_index(w, "combo", "GZT7"))
    _ruhe()
    r = an.combinations["GZT7"]
    knoten = sorted({s.node for s in w.model.supports})
    fuss = t.fussmodell.zeilen
    summe = fuss[-1] if fuss else []
    soll = np.asarray(r.reactions, float)[knoten].sum(axis=0) / 1e3
    check("einzelnes Ergebnis: Spalten Rx … Mz, darunter die Summenzeile Σ",
          _namen(t) == AUFLAGER_EINZEL and not t.fuss.isHidden() and summe and str(summe[0]).startswith("Σ"),
          f"Fuß {[z[0] for z in fuss]}")
    check("… Σ Rx, Ry, Rz = Summe der Reaktionen aller Lagerknoten (aus r.reactions)",
          summe and all(abs(float(summe[1 + d]) - soll[d]) < 1e-9 for d in range(3)) and abs(soll[2]) > 1.0,
          f"Σ {[summe[1 + d] for d in range(3)] if summe else '-'} / {soll[:3]}")
    check("… Momente ohne Summe (Lagermomente ohne Hebelarm ergeben keine Gesamtgröße)",
          summe and all(summe[1 + d] == "" for d in range(3, 6)), str(summe[4:] if summe else ""))
    gezeigt = t.fussmodell.data(t.fussmodell.index(len(fuss) - 1, 3), QtCore.Qt.DisplayRole)
    check("… angezeigt mit Komma wie die Tabelle", "," in str(gezeigt) and "." not in str(gezeigt), str(gezeigt))
    export = t.zeilen_fuer_export()
    check("… Kopieren/CSV/Excel geben die Summenzeile mit aus", export and str(export[-1][0]).startswith("Σ"),
          str(export[-1][:4] if export else ""))
    # Filter: die Summe gilt fuer die sichtbaren Zeilen
    t.felder[0].setText(f"= {knoten[0]}")
    _ruhe()
    s1 = t.fussmodell.zeilen[-1]
    check("mit Filter auf einen Knoten: Σ ist dessen Reaktion (die Summe folgt dem Filter wie Max/Min)",
          abs(float(s1[3]) - r.reactions[knoten[0], 2] / 1e3) < 1e-9, f"{s1[3]} / {r.reactions[knoten[0], 2] / 1e3}")
    t.filterzeile_zeigen(False)
    _ruhe()
    # Umhuellende: min und max als Zahlenspalten
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    env = an.envelopes["ULS"]
    falsch = []
    for s in knoten:
        z = _zeile(t, s)
        for d, g in enumerate(("Rx", "Ry", "Rz", "Mx", "My", "Mz")):
            k = _namen(t).index(f"{g} min")
            if z is None or not isinstance(z[k], float) or abs(z[k] - env.r_min[s, d] / 1e3) > 1e-9 \
                    or abs(z[k + 1] - env.r_max[s, d] / 1e3) > 1e-9:
                falsch.append(f"{s}/{g}")
    check("Umhüllende: min und max je Komponente als Zahlenspalten (Werte gleich r_min und r_max)",
          _namen(t) == AUFLAGER_HUELLE and t.zeilenzahl() == len(knoten) and not falsch,
          f"{_namen(t)[:4]} … {falsch[:3]}")
    m = t.modell
    zellen = [str(m.data(m.index(r_, k))) for r_ in range(m.rowCount()) for k in range(1, m.columnCount())]
    check("… angezeigt mit Komma, ohne „/“ und ohne „-0,00“",
          zellen and all("," in z and "/" not in z and z != "-0,00" for z in zellen), str(zellen[:3]))
    fuss = t.fussmodell.zeilen
    lbl = getattr(t, "lbl_summe", None)
    text = lbl.text() if lbl is not None else ""
    tip = lbl.toolTip() if lbl is not None else ""
    # Seit der Nachbesserung (03.10.2026) ein Satz unter dem Fuss, ueber die
    # Breite der Tabelle und ohne mit ihr waagerecht zu rollen; vorher eine
    # Zeile des Fusses, die ueber alle Spalten reichte
    check("… statt einer Summe ein Satz Σ unter der Tabelle, der sagt warum; keine Σ-Zeile mit Zahlen",
          lbl is not None and lbl.isVisible() and text.startswith("Σ") and "keine Summe" in text
          and "Kombination" in tip and "nie zugleich" in tip
          and not any(str(z[0]).startswith("Σ") for z in fuss), f"{text[:70]!r} / {tip[:60]!r}")
    check("… er geht nicht in Kopieren/CSV/Excel (dort stehen nur Zahlen)",
          not any(str(z[0]).startswith("Σ") or "keine Summe" in str(z[0]) for z in t.zeilen_fuer_export()), "")


def test_kombinationszelle():
    from PySide6 import QtCore, QtTest
    w = _fenster()
    an = _hall(w)
    w.tabelle_zeigen("Stabkräfte")
    _ruhe()
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    t = w.tbl_beam
    namen = _namen(t)
    k = namen.index("My max") + 1
    q = t.filter.index(0, k)
    t.view.scrollTo(q)
    _ruhe()
    e = int(t.filter.index(0, 0).data(QtCore.Qt.UserRole))
    ziel = str(t.filter.index(0, k).data(QtCore.Qt.UserRole))
    check("Vorbedingung: die Zelle nennt eine Kombination des Modells", ziel in an.combinations, ziel)
    QtTest.QTest.mouseClick(t.view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            t.view.visualRect(q).center())
    _ruhe(10)
    check(f"Klick auf die Zelle „{ziel}“ (My max von Element {e}): oben rechts, unten und Glasleiste zeigen sie",
          w.cb_result.currentData() == ("combo", ziel) and w.cb_ergebnis_unten.currentData() == ("combo", ziel)
          and tuple(w.cb_lastwahl.currentData() or ()) == ("combo", ziel),
          f"{w.cb_result.currentData()} / {w.cb_lastwahl.currentData()}")
    check("… Bild und Tabellen zeigen die Kombination (current_result, Spalten des einzelnen Ergebnisses)",
          w.current_result() is an.combinations[ziel] and _namen(t) == STAB_EINZEL
          and w._lastwahl_ziel() == ("combo", ziel), str(_namen(t)[:3]))
    markiert = [int(i.data(QtCore.Qt.UserRole)) for i in t.view.selectionModel().selectedRows()]
    check("… das angeklickte Element bleibt gewählt, seine Zeile ist in der neuen Tabelle markiert",
          markiert == [e] and set(w.model.elements[e].nodes) <= set(int(n) for n in w.selection), str(markiert))
    # Register „Umhüllende“: die Kombinationszellen schalten ebenso
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    w.tabelle_zeigen("Umhüllende")
    _ruhe()
    te = w.tbl_env
    k = [sp.name for sp in te.modell.spalten].index("max") + 1
    q = te.filter.index(1, k)
    ziel2 = str(q.data(QtCore.Qt.UserRole))
    te.view.scrollTo(q)
    _ruhe()
    QtTest.QTest.mouseClick(te.view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            te.view.visualRect(q).center())
    _ruhe(10)
    check(f"Register „Umhüllende“: Klick auf „{ziel2}“ schaltet ebenso", w.cb_result.currentData() == ("combo", ziel2),
          str(w.cb_result.currentData()))
    # Nachweise EC3: die Spalte „Kombination“
    w.tabelle_zeigen("Nachweise EC3")
    _ruhe()
    td = w.tbl_design
    k = [sp.name for sp in td.modell.spalten].index("Kombination")
    q = td.filter.index(0, k)
    ziel3 = str(q.data(QtCore.Qt.UserRole))
    QtTest.QTest.mouseClick(td.view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            td.view.visualRect(q).center())
    _ruhe(10)
    check(f"Nachweise EC3: Klick auf die maßgebende Kombination „{ziel3}“ schaltet das Ergebnis",
          w.cb_result.currentData() == ("combo", ziel3) and w.cb_ergebnis_unten.currentData() == ("combo", ziel3),
          str(w.cb_result.currentData()))
    # Ergebnisse ausgeblendet: der Klick holt sie zurueck, sonst zeigte das Bild etwas anderes
    w.tabelle_zeigen("Stabkräfte")
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    w.act_ergebnisse.setChecked(False)
    _ruhe()
    q = t.filter.index(0, namen.index("N min") + 1)
    ziel4 = str(q.data(QtCore.Qt.UserRole))
    t.view.scrollTo(q)
    _ruhe()
    QtTest.QTest.mouseClick(t.view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            t.view.visualRect(q).center())
    _ruhe(10)
    check("bei ausgeblendeten Ergebnissen blendet der Klick sie ein, die Glasleiste zeigt die Kombination",
          w.ergebnisse_sichtbar() and tuple(w.cb_lastwahl.currentData() or ()) == ("combo", ziel4),
          f"{w.ergebnisse_sichtbar()} / {w.cb_lastwahl.currentData()}")
    # ein Name ohne eigenes Ergebnis (Alternative einer Ergebniskombination)
    vorher = w.cb_result.currentIndex()
    n0 = len(w.meldungen)
    w._ergebnis_aus_zelle("GZT1 [3]")
    _ruhe(6)
    check("ein Name ohne eigenes Ergebnis schaltet nicht und sagt es in der Statuszeile",
          w.cb_result.currentIndex() == vorher and len(w.meldungen) > n0 and "GZT1 [3]" in w.meldungen[-1],
          (w.meldungen[-1] if len(w.meldungen) > n0 else "")[:90])


def test_alte_ergebnisdatei():
    """Eine Umhüllende ohne Stabschnittgrößen (wie aus einer Ergebnisdatei,
    die sie nicht trägt): „Stabkräfte“ erklärt, warum sie leer ist."""
    import io
    import pickle
    from statik3d import ergebnisse as erg
    w = _fenster()
    an = _hall(w)
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_alt_erg_"), "hall.ergebnisse")
    erg.schreiben(pfad, w.model, an)
    an2 = erg.lesen(pfad, w.model)
    env = an2.envelopes["ULS"]
    # Zustand wie eine Datei ohne diese Daten: die Umhuellende durch ein
    # Pickle schicken, ohne Schnittgroessen je Stab, ohne Ausnutzung und ohne
    # Herkunft der Auflager (beam ganz zu streichen ginge nicht: das kennt jede
    # Ergebnisdatei, und Envelope.summary liest es)
    stand = {k: v for k, v in env.__dict__.items()
             if k not in ("util", "r_min_src", "r_max_src", "model")}
    stand["beam"] = {}
    from statik3d.solver import Envelope
    alt = Envelope.__new__(Envelope)
    alt.__setstate__(pickle.loads(pickle.dumps(stand)))
    alt.model = w.model
    an2.envelopes["ULS"] = alt
    w._solve_done("all", an2)
    _ruhe()
    w.tabelle_zeigen("Stabkräfte")
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    t = w.tbl_beam
    text = t.lbl_leer.text()
    check("alte Ergebnisdatei ohne Stabschnittgrößen: „Stabkräfte“ leer mit Erklärung und Weg",
          t.zeilenzahl() == 0 and t.lbl_leer.isVisible() and "Ergebnisdatei" in text and "Berechnen" in text,
          text[:100])
    tr = w.tbl_react
    check("… die Auflager zeigen ihre min und max trotzdem (r_min, r_max sind da)",
          tr.zeilenzahl() > 0 and _namen(tr) == AUFLAGER_HUELLE, f"{tr.zeilenzahl()} Zeilen")
    _F["hall"] = None


def test_hoehe_und_platz():
    """Die Ergebniswahl steht im Kopf: die Tabelle verliert keine Höhe, und im
    Kopf bleibt alles erreichbar (gewählter Reiter ganz, Knöpfe sichtbar oder
    im Menü »), auch in der Kompaktstufe."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from statik3d.gui import tabellen as tab
    w = _fenster()
    _hall(w)
    tu = w.tab_unten
    cb = w.cb_ergebnis_unten
    schrift = bool(QtGui.QFontDatabase.families())
    print(f"     {'mit Schrift' if schrift else 'ohne Schrift - Breiten sind Kästchenwerte'}", flush=True)
    for b, h in ((1920, 1080), (1366, 768), (1280, 720)):
        w.resize(b, h)
        _ruhe(8)
        w.anordnung.zuruecksetzen()
        _ruhe(8)
        if w.anordnung.kompakt:
            w.anordnung.unten_einklappen(False)
            _ruhe(8)
        for name in ("Stabkräfte", "Nachweise EC3"):
            w.tabelle_zeigen(name)
            _ruhe(6)
            t = w.aktive_tabelle()
            kopf = tu.kopf
            unterkante = kopf.mapTo(tu, kopf.rect().bottomLeft()).y()
            oben = t.view.mapTo(tu, t.view.rect().topLeft()).y()
            rb = tu.reiter
            frei = tab.reiter_frei(rb)
            gewaehlt_ganz = frei.contains(rb.tabRect(rb.currentIndex()))
            ext = tu.werkzeug.findChild(QtWidgets.QToolButton, "qt_toolbar_ext_button")
            menue = ext is not None and ext.isVisible()
            knoepfe = all((tu.werkzeug.widgetForAction(a) is not None
                           and tu.werkzeug.widgetForAction(a).isVisible()) or menue
                          for a in tu.werkzeug.actions())
            # mit Schrift ungekuerzt; ohne (Kaestchen, doppelt so breit) darf
            # das Feld bis auf seine Mindestbreite nachgeben und, wo selbst die
            # nicht mehr neben Gruppe, Reiter und Menue passt, wegfallen
            soll = cb.sizeHint().width() if schrift else cb.minimumSizeHint().width()
            cb_ganz = cb.isVisible() and cb.width() >= soll - 1 \
                and kopf.rect().contains(QtCore.QRect(cb.mapTo(kopf, QtCore.QPoint(0, 0)), cb.size()))
            if not schrift and cb.isHidden():
                cb_ganz = tu.zusatz_platz() < cb.minimumSizeHint().width()
                print(f"     (Kästchen: kein Platz für die Ergebniswahl, {tu.zusatz_platz()} px frei)")
            rolle = w.unten_dock.widget()
            rollt = (rolle.horizontalScrollBar().maximum()
                     if isinstance(rolle, QtWidgets.QScrollArea) else 0)
            breite = rolle.viewport().width() if isinstance(rolle, QtWidgets.QScrollArea) else w.unten_dock.width()
            hoehe = t.view.visibleRegion().boundingRect().height()
            detail = (f"Kopf {kopf.height()} px, Tabelle {hoehe} px ab {oben - unterkante} px unter dem Kopf, "
                      f"Ergebniswahl {cb.width()} px, Reiter {rb.width()} px")
            print(f"     {b} x {h}{' Kompaktstufe' if w.anordnung.kompakt else ''} {name}: {detail}", flush=True)
            check(f"{b} x {h}, {name}: Kopf höchstens 40 px, Tabelle direkt darunter, Ergebniswahl im Kopf"
                  + (" und ungekürzt" if schrift else ""),
                  kopf.height() <= 40 and 0 <= oben - unterkante <= 6 and cb_ganz, detail)
            check(f"{b} x {h}, {name}: der Kopf ist nicht breiter als der Bereich, nichts rollt waagerecht",
                  rollt == 0 and kopf.width() <= breite, f"rollt {rollt} px, Kopf {kopf.width()} von {breite} px")
            check(f"{b} x {h}, {name}: gewählter Reiter ganz zu sehen, Knöpfe sichtbar oder im Menü »",
                  gewaehlt_ganz and knoepfe, f"Reiter ganz {gewaehlt_ganz}, Menü {menue}")
    w.resize(1920, 1080)
    _ruhe(8)
    w.anordnung.zuruecksetzen()
    _ruhe(8)


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung von a5846e9 (03.10.2026), Abnahme B1-B14
# --------------------------------------------------------------------------
def _klicke(t, zeile, spalte):
    """Ein echter Mausklick auf die Zelle (zeile, spalte) der Ansicht."""
    from PySide6 import QtCore, QtTest
    q = t.filter.index(zeile, spalte)
    t.view.scrollTo(q)
    _ruhe(2)
    QtTest.QTest.mouseClick(t.view.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier,
                            t.view.visualRect(q).center())
    _ruhe(12)


def _markiert(t):
    from PySide6 import QtCore
    return [int(i.data(QtCore.Qt.UserRole)) for i in t.view.selectionModel().selectedRows()]


def _im_bild(t, schluessel) -> bool:
    """Steht die Zeile mit diesem Schluessel ganz im Sichtfenster der Tabelle?"""
    from PySide6 import QtCore
    for r in range(t.filter.rowCount()):
        if int(float(t.filter.index(r, 0).data(QtCore.Qt.UserRole))) == int(schluessel):
            rect = t.view.visualRect(t.filter.index(r, 0))
            return rect.isValid() and rect.top() >= 0 and rect.bottom() <= t.view.viewport().height()
    return False


def _huelle_zeigen(w, schluessel="ULS", tabelle="Stabkräfte"):
    w.tabelle_zeigen(tabelle)
    _ruhe()
    w.cb_result.setCurrentIndex(_index(w, "env", schluessel))
    _ruhe()


def _aufraeumen(t):
    """Filter weg, nach Element aufsteigend (fuer die folgenden Pruefungen)."""
    from PySide6 import QtCore
    t.filterzeile_zeigen(False)
    t.view.sortByColumn(0, QtCore.Qt.AscendingOrder)
    _ruhe()


def test_b01_b02_zeile_im_bild():
    from PySide6 import QtCore
    w = _fenster()
    _hall(w)
    w.resize(1920, 1080)
    _ruhe()
    t = w.tbl_beam
    _huelle_zeigen(w)
    k_my = _namen(t).index("My max")
    t.view.sortByColumn(k_my, QtCore.Qt.DescendingOrder)
    _ruhe()
    e = int(t.filter.index(2, 0).data(QtCore.Qt.UserRole))
    _klicke(t, 2, k_my + 1)
    check("B1: nach „My max“ absteigend, Klick auf „Komb.“ in Zeile 3: Element 17 markiert und im Sichtfenster",
          e == 17 and _markiert(t) == [17] and _im_bild(t, 17),
          f"Element {e}, markiert {_markiert(t)}, im Bild {_im_bild(t, 17)}, "
          f"Rollwert {t.view.verticalScrollBar().value()}/{t.view.verticalScrollBar().maximum()}")
    _huelle_zeigen(w)
    _aufraeumen(t)
    t.filterzeile_zeigen(True)
    t.felder[0].setText("> 9")
    t.view.sortByColumn(_namen(t).index("My max"), QtCore.Qt.DescendingOrder)
    _ruhe()
    soll = sum(1 for z in t.modell.zeilen if int(z[0]) > 9)
    e = int(t.filter.index(2, 0).data(QtCore.Qt.UserRole))
    _klicke(t, 2, _namen(t).index("My max") + 1)
    check("B2: dasselbe mit Filter „Element > 9“: der Filter wirkt weiter, die Zeile ist markiert und sichtbar",
          w.cb_result.currentData()[0] == "combo" and t.felder[0].text() == "> 9" and t.filter_wirkt()
          and t.sichtbar() == soll and _markiert(t) == [e] and _im_bild(t, e),
          f"Filter {t.felder[0].text()!r}, {t.sichtbar()} von {soll}, markiert {_markiert(t)} / {e}, "
          f"im Bild {_im_bild(t, e)}")
    _aufraeumen(t)


def test_b03_filter_und_sortierung_bleiben():
    from PySide6 import QtCore
    w = _fenster()
    _hall(w)
    t = w.tbl_beam
    _huelle_zeigen(w)
    _aufraeumen(t)
    t.filterzeile_zeigen(True)
    t.felder[0].setText("> 4")
    t.view.sortByColumn(0, QtCore.Qt.DescendingOrder)
    _ruhe()
    soll = sum(1 for z in t.modell.zeilen if int(z[0]) > 4)

    def stand():
        kopf = t.view.horizontalHeader()
        return (t.felder[0].text(), t.filter_wirkt(), t.sichtbar(), kopf.sortIndicatorSection(),
                kopf.sortIndicatorOrder() == QtCore.Qt.DescendingOrder,
                int(t.filter.index(0, 0).data(QtCore.Qt.UserRole)) if t.sichtbar() else None)
    erwartet = ("> 4", True, soll, 0, True, 17)
    w.cb_result.setCurrentIndex(_index(w, "combo", "GZT7"))
    _ruhe()
    zur_kombination = stand()
    w.cb_result.setCurrentIndex(_index(w, "env", "ULS"))
    _ruhe()
    zurueck = stand()
    check("B3: Umhüllende → GZT7 → Umhüllende mit Filter und absteigender Sortierung auf „Element“: beides bleibt",
          zur_kombination == erwartet and zurueck == erwartet, f"GZT7 {zur_kombination}, zurück {zurueck}")
    # die sortierte Spalte gibt es zur Kombination nicht: die Statuszeile sagt es
    t.view.sortByColumn(_namen(t).index("My max"), QtCore.Qt.DescendingOrder)
    _ruhe()
    n0 = len(w.meldungen)
    w.cb_result.setCurrentIndex(_index(w, "combo", "GZT7"))
    _ruhe()
    neu = w.meldungen[n0:]
    check("… fällt die sortierte Spalte weg („My max“), sagt die Statuszeile das",
          any("My max" in x and "Sortierung" in x for x in neu), str(neu[-1:])[:120])
    _huelle_zeigen(w)
    _aufraeumen(t)


def test_b04_meldung_bei_eigenformen():
    from PySide6 import QtCore
    from statik3d import solver
    w = _fenster()
    _hall(w)
    rm = solver.solve_modal(w.model, 3)
    w._solve_done("modal", rm)
    _ruhe()
    w.tabelle_zeigen("Nachweise EC3")
    _ruhe()
    td = w.tbl_design
    k = _namen(td).index("Kombination")
    name = str(td.filter.index(0, k).data(QtCore.Qt.UserRole)) if td.filter.rowCount() else ""
    n0 = len(w.meldungen)
    if td.filter.rowCount():
        _klicke(td, 0, k)
    neu = w.meldungen[n0:]
    check(f"B4: Eigenformen gezeigt, Klick in Nachweise EC3 auf „{name}“: keine Meldung „kein einzeln "
          "gespeichertes Ergebnis“, sondern dass Eigenformen gezeigt werden",
          name == "GZT4" and not any("kein einzeln gespeichertes Ergebnis" in x for x in neu)
          and any("Eigen" in x and name in x for x in neu), str(neu)[:140])
    _F["hall"] = None


def _zahlnamen_modell():
    """Rahmen aus sechs Staeben, Lastfaelle „1“ und „2“, keine Kombination:
    die Umhuellende ueber die Lastfaelle nennt Namen, die wie Zahlen aussehen."""
    from statik3d.model import Model, Material, Section
    m = Model("zahlnamen")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(2.0 * i, 0.0, 0.0) for i in range(7)]
    for i in range(6):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300")
    m.fix(n[0], "all")
    m.fix(n[6], [0, 1, 2])
    for name in list(m.load_cases):
        del m.load_cases[name]
    m.add_load_case("1", "G")
    m.add_load_case("2", "Q", activate=False)
    m.load_node(n[3], Fz=-10e3, case="1")
    m.load_node(n[2], Fz=+4e3, case="2")
    m.load_node(n[4], Fy=3e3, case="2")
    m.active_case = "1"
    return m


def _rechnen(w, m, design=False):
    from statik3d import solver
    w._modell_setzen(m)
    w.refresh_all()
    _ruhe()
    an = solver.solve_all(w.model, design=design)
    w._solve_done("all", an)
    _ruhe()
    _F["hall"] = None
    return an


def test_b05_fuss_ohne_verweise():
    from PySide6 import QtCore
    w = _fenster()
    an = _rechnen(w, _zahlnamen_modell())
    _huelle_zeigen(w, "CASES")
    t = w.tbl_beam
    fm = t.fussmodell
    kk = [k for k, s in enumerate(t.modell.spalten) if s.name == "Komb."]
    texte = [[fm.data(fm.index(r, k), QtCore.Qt.DisplayRole) for k in kk] for r in range(fm.rowCount())]
    stil = [(fm.data(fm.index(r, k), QtCore.Qt.ForegroundRole), fm.data(fm.index(r, k), QtCore.Qt.FontRole),
             fm.data(fm.index(r, k), QtCore.Qt.ToolTipRole)) for r in range(fm.rowCount()) for k in kk]
    check("B5: Lastfälle „1“ und „2“, Umhüllende Lastfälle: unter „Komb.“ bleibt der Fuß leer, ohne Verweisstil",
          set(an.envelopes["CASES"].names) == {"1", "2"} and fm.rowCount() == 2 and kk
          and all(x in ("", None) for z in texte for x in z) and all(s == (None, None, None) for s in stil),
          f"Fuß {texte}, Stil {[s for s in stil if s != (None, None, None)][:2]}")


def _hall_ek():
    from statik3d.examples_lib import hall_frame_example
    from statik3d.model import Combination
    m = hall_frame_example()
    m.combinations["EK1"] = Combination("EK1", {}, "ULS", alternativen=[
        {"LF1": 1.35, "S": 1.5, "W_links": 0.9}, {"LF1": 1.0},
        {"LF1": 1.0, "W_links": 1.5}, {"LF1": 1.35, "S": 1.5, "W_rechts": 0.9}])
    return m


def test_b06_alternative_ohne_verweis():
    from PySide6 import QtCore
    w = _fenster()
    _rechnen(w, _hall_ek(), design=True)
    _huelle_zeigen(w, "EK1")
    t = w.tbl_beam
    treffer = [(r, k) for r in range(t.filter.rowCount()) for k, s in enumerate(t.modell.spalten)
               if s.name == "Komb." and str(t.filter.index(r, k).data(QtCore.Qt.UserRole)) == "EK1 [4]"]
    r, k = treffer[0] if treffer else (0, 0)
    q = t.filter.mapToSource(t.filter.index(r, k))
    m = t.modell
    vorder, schrift, tip = (m.data(q, QtCore.Qt.ForegroundRole), m.data(q, QtCore.Qt.FontRole),
                            m.data(q, QtCore.Qt.ToolTipRole))
    lf = [(rr, kk) for rr in range(t.filter.rowCount()) for kk, s in enumerate(t.modell.spalten)
          if s.name == "Komb." and str(t.filter.index(rr, kk).data(QtCore.Qt.UserRole)) == "LF1"]
    q2 = t.filter.mapToSource(t.filter.index(*lf[0])) if lf else None
    check("B6: Alternative „EK1 [4]“: gewöhnlicher Text, ohne Unterstreichung und ohne Tooltip „Klick zeigt …“",
          treffer and vorder is None and (schrift is None or not schrift.underline())
          and not (tip and "Klick" in str(tip)), f"{len(treffer)} Zellen, Tooltip {tip!r}")
    check("… ein Name mit eigenem Ergebnis daneben („LF1“) bleibt ein Verweis",
          q2 is not None and m.data(q2, QtCore.Qt.FontRole) is not None
          and m.data(q2, QtCore.Qt.FontRole).underline() and "Klick" in str(m.data(q2, QtCore.Qt.ToolTipRole)),
          str(m.data(q2, QtCore.Qt.ToolTipRole)) if q2 is not None else "kein LF1")


def test_b07_fuss_folgt_der_spalte():
    from PySide6 import QtCore
    w = _fenster()
    _hall(w)
    w.tabelle_zeigen("Auflagerkräfte")
    w.cb_result.setCurrentIndex(_index(w, "combo", "GZT7"))
    _ruhe()
    t = w.tbl_react
    kopf, fk = t.view.horizontalHeader(), t.fuss.horizontalHeader()
    kopf.moveSection(kopf.visualIndex(3), 1)
    _ruhe()
    fm = t.fussmodell
    x = kopf.sectionViewportPosition(3) + 5
    k_f = fk.logicalIndexAt(x)
    unter = [fm.data(fm.index(r, k_f), QtCore.Qt.DisplayRole) for r in range(fm.rowCount())]
    soll = [fm.data(fm.index(r, 3), QtCore.Qt.DisplayRole) for r in range(fm.rowCount())]
    gleich = all(fk.visualIndex(k) == kopf.visualIndex(k) for k in range(kopf.count()))
    check("B7: Auflager GZT7, Rz an die zweite Stelle gezogen: darunter stehen Max, Min und Σ von Rz",
          kopf.visualIndex(3) == 1 and k_f == 3 and unter == soll and gleich and len(soll) == 3,
          f"unter Rz steht Spalte {t.modell.spalten[k_f].name}: {unter} (Rz: {soll})")
    kopf.moveSection(1, 3)
    _ruhe()


def test_b08_grenzen_der_umhuellenden():
    from statik3d.gui import viewport as vp
    w = _fenster()
    an = _hall(w)
    g = vp.schnittgroessen_grenzen(w.model, an.envelopes["ULS"])
    lo, _e1, hi, _e2 = g.get("N", (None,) * 4)
    check("B8: schnittgroessen_grenzen, Hallenrahmen, Umhüllende GZT: N max = −10 429,5 N, N min = −172 431,4 N",
          lo is not None and abs(hi - (-10429.5)) < 1.0 and abs(lo - (-172431.4)) < 1.0, f"{lo} … {hi}")
    alle = {q: g.get(q) for q in vp.SCHNITTGROESSEN}
    falsch = []
    env = an.envelopes["ULS"]
    for q, v in alle.items():
        mn = min(float(d[q][0].min()) for d in env.beam.values())
        mx = max(float(d[q][1].max()) for d in env.beam.values())
        if v is None or abs(v[0] - mn) > 1e-6 or abs(v[2] - mx) > 1e-6:
            falsch.append(q)
    check("… und alle Schnittgrößen gleich min und max der Umhüllenden (keine Herkunftsindizes als Werte)",
          not falsch, str(falsch))


def test_b09_auflager_nennen_kombination():
    from PySide6 import QtCore
    w = _fenster()
    an = _hall(w)
    env = an.envelopes["ULS"]
    _huelle_zeigen(w, "ULS", "Auflagerkräfte")
    t = w.tbl_react
    k = _namen(t).index("Rz min")
    r = next(rr for rr in range(t.filter.rowCount()) if int(t.filter.index(rr, 0).data(QtCore.Qt.UserRole)) == 0)
    q = t.filter.mapToSource(t.filter.index(r, k))
    tip = str(t.modell.data(q, QtCore.Qt.ToolTipRole))
    soll = env.names[int(env.r_min_src[0, 2])]
    _klicke(t, r, k)
    check("B9: Auflager der Umhüllenden, Rz min an Knoten 0: Tooltip nennt GZT27, ein Klick schaltet auf GZT27",
          soll == "GZT27" and "GZT27" in tip and w.cb_result.currentData() == ("combo", "GZT27"),
          f"Tooltip {tip!r}, danach {w.cb_result.currentData()}")


def test_b10_summensatz_ganz():
    from PySide6 import QtGui, QtWidgets
    w = _fenster()
    _hall(w)
    schrift = bool(QtGui.QFontDatabase.families())
    w.resize(1366, 768)
    _ruhe(8)
    w.anordnung.zuruecksetzen()
    _ruhe(8)
    if w.anordnung.kompakt:
        w.anordnung.unten_einklappen(False)
        _ruhe(8)
    _huelle_zeigen(w, "ULS", "Auflagerkräfte")
    _ruhe(6)
    t = w.tbl_react
    lbl = getattr(t, "lbl_summe", None)
    rolle = w.unten_dock.widget()
    rollt = rolle.horizontalScrollBar().maximum() if isinstance(rolle, QtWidgets.QScrollArea) else 0
    if lbl is None:
        check("B10: 1366 × 768 kompakt: Σ-Satz ganz sichtbar, Tooltip mit vollem Text", False, "kein Satzfeld")
    else:
        fm = lbl.fontMetrics()
        breite = fm.horizontalAdvance(lbl.text())
        ganz = lbl.isVisible() and not lbl.text().endswith("…") and breite <= lbl.contentsRect().width() \
            and lbl.visibleRegion().boundingRect().width() >= lbl.width() - 1
        detail = (f"{'mit Schrift' if schrift else 'Kästchenwert'}: Text {breite} px, Feld {lbl.width()} px, "
                  f"rollt {rollt} px, Tooltip {lbl.toolTip()[:50]!r}")
        print(f"     B10 {detail}", flush=True)
        voll = "nie zugleich" in lbl.toolTip() and "Lastfall oder Kombination" in lbl.toolTip()
        if schrift:
            check("B10: 1366 × 768 kompakt, mit Schrift: Σ-Satz ganz sichtbar ohne Rollen, Tooltip mit vollem Text",
                  w.anordnung.kompakt and ganz and rollt == 0 and voll, detail)
        else:
            check("B10 (ohne Schrift, Kästchen): Σ-Satz ganz oder mit „…“ gekürzt, nie gerollt, Tooltip voll",
                  w.anordnung.kompakt and lbl.isVisible() and rollt == 0 and voll, detail)
    w.resize(1920, 1080)
    _ruhe(8)
    w.anordnung.zuruecksetzen()
    _ruhe(8)


def test_b11_ein_neuzeichnen():
    w = _fenster()
    _hall(w)
    t = w.tbl_beam
    _huelle_zeigen(w)
    _aufraeumen(t)
    zaehler = {"n": 0}
    alt = w.redraw

    def redraw(*a, **k):
        zaehler["n"] += 1
        return alt(*a, **k)
    w.redraw = redraw
    try:
        _klicke(t, 0, _namen(t).index("N min") + 1)
    finally:
        del w.redraw
    check("B11: Klick auf eine Kombinationszelle zeichnet genau einmal",
          w.cb_result.currentData()[0] == "combo" and zaehler["n"] == 1, f"{zaehler['n']}× gezeichnet")


def test_b12_einblenden_oben_rechts():
    w = _fenster()
    _hall(w)
    _huelle_zeigen(w)
    w.act_ergebnisse.setChecked(False)
    _ruhe()
    i = _index(w, "combo", "GZT10")
    # wie die Wahl in der Liste: erst der neue Eintrag, dann „activated“
    w.cb_result.setCurrentIndex(i)
    w.cb_result.activated.emit(i)
    _ruhe()
    check("B12: Ergebnisse ausgeblendet, Wahl oben rechts (GZT10): eingeblendet, Glasleiste und unten gleich",
          w.ergebnisse_sichtbar() and tuple(w.cb_lastwahl.currentData() or ()) == ("combo", "GZT10")
          and w.cb_ergebnis_unten.currentData() == ("combo", "GZT10"),
          f"sichtbar {w.ergebnisse_sichtbar()}, Glasleiste {w.cb_lastwahl.currentData()}")
    w.act_ergebnisse.setChecked(True)
    _ruhe()


def test_b13_veraltete_liste():
    from PySide6 import QtCore
    w = _fenster()
    _hall(w)
    _huelle_zeigen(w)
    tm = w.tbl_mat
    ok = tm.modell.setData(tm.modell.index(0, 1), "205000", QtCore.Qt.EditRole)
    _ruhe()
    reste = {n: _namen(getattr(w, n)) for n in ("tbl_beam", "tbl_react")
             if any(" min" in x or x == "Komb." for x in _namen(getattr(w, n)))}
    zeilen = {n: getattr(w, n).zeilenzahl() for n in ("tbl_beam", "tbl_react", "tbl_env")}
    check("B13: E-Modul in der Zelle geändert: keine Tabelle zeigt Spalten der alten Umhüllenden, Listen leer",
          ok and w.analysis is None and not reste and not any(zeilen.values())
          and w.cb_result.count() == 0 and not w.cb_ergebnis_unten.isVisible(),
          f"Reste {reste}, Zeilen {zeilen}, Liste {w.cb_result.count()}")
    _F["hall"] = None


def test_b14_ausnutzung_nur_gzt():
    w = _fenster()
    _hall(w)
    _huelle_zeigen(w, "SLS_CH")
    gzg = _namen(w.tbl_beam)
    _huelle_zeigen(w, "ULS")
    gzt = _namen(w.tbl_beam)
    tip = next((sp.hinweis for sp in w.tbl_beam.modell.spalten if sp.name == "Ausn."), "")
    check("B14: Umhüllende GZG ohne Spalte „Ausn.“, Umhüllende GZT mit, und ihr Hinweis nennt EC3",
          "Ausn." not in gzg and "Ausn." in gzt and "EC3" in tip, f"GZG {gzg[-2:]}, GZT {gzt[-2:]}, {tip!r}")


def test_handbuch():
    from tests.handbuch import absatz
    a = absatz("**Ergebniszeile unten.**")
    check("Handbuch: Ergebniswahl unten, dieselbe wie oben rechts und in der Glasleiste, Stand vorher genannt",
          "Glasleiste" in a and "oben rechts" in a and "Bis zum 03.10.2026" in a, a[:90])
    b = absatz("**Stabkräfte und Auflager einer Umhüllenden.**")
    check("Handbuch: min und max mit Kombination, Σ-Zeile, keine Summe bei der Umhüllenden, Klick schaltet",
          "min" in b and "Σ" in b and "keine Summe" in b and "Klick" in b and "Bis zum 03.10.2026" in b, b[:90])
    check("Handbuch: Nachbesserung - Verweis nur mit eigenem Ergebnis, Filter und Sortierung bleiben, "
          "Auflager nennen die Kombination, Ausn. nur im GZT, einmal gezeichnet",
          "EK1 [4]" in b and "Filter und Sortierung bleiben" in b and "nennt am Zeiger die Kombination" in b
          and "Ausn." in b and "einmal gezeichnet" in b and "Nachbesserung am 03.10.2026" in b, b[-90:])
    c = absatz("Unter jeder Ergebnistabelle")
    check("Handbuch: Max und Min nur unter Zahlenspalten, der Fuß wandert mit verschobenen Spalten",
          "nur unter Zahlenspalten" in c and "wandern ihre Werte im Fuß mit" in c, c[-90:])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    nur = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv[:-1] else ""
    for t in (test_ergebniszeile_gleich, test_stabkraefte_umhuellende, test_auflager, test_kombinationszelle,
              test_alte_ergebnisdatei, test_hoehe_und_platz,
              test_b01_b02_zeile_im_bild, test_b03_filter_und_sortierung_bleiben, test_b04_meldung_bei_eigenformen,
              test_b07_fuss_folgt_der_spalte, test_b08_grenzen_der_umhuellenden, test_b09_auflager_nennen_kombination,
              test_b10_summensatz_ganz, test_b11_ein_neuzeichnen, test_b12_einblenden_oben_rechts,
              test_b14_ausnutzung_nur_gzt, test_b13_veraltete_liste, test_b05_fuss_ohne_verweise,
              test_b06_alternative_ohne_verweis, test_handbuch):
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
