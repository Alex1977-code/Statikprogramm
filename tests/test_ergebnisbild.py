"""
Das Ergebnisbild ist eindeutig (Paket 6a des Oberflaechenplans, 24.09.2026).

Befunde am Stand ad19c87, in allen acht gerechneten Beispielen:

* Die Glasleiste zeigte „Lastfall LF1“, das Bild die „Umhüllende ULS“ - die
  Liste fuehrte keine Umhuellenden und blieb darum auf dem aktiven Lastfall
  stehen.
* Am Hallenrahmen nannte die Legende max |u| = 73,5 mm, die Kennwerte
  darunter 79,23 mm. Die 79,23 mm kommen in keiner Kombination vor: die
  Kennwerte bildeten |u| aus viewport.displacement_of, das je Richtung das
  betragsgroessere Extrem nimmt - am Knoten 14 ux = +29,71 mm aus GZT11 und
  uz = -73,45 mm aus GZT4, zusammen sqrt(29,71² + 73,45²) = 79,23 mm. Die
  Faerbung liest umag_max (laufendes Maximum der Betraege), 73,52 mm aus
  GZT4. Dasselbe Gemisch war auch die verformte Figur.
* Im Bild der Umhuellenden standen die Lasten von LF1.

Geprueft wird ohne Fenster (viewport: Kennwerte, Figur, Kopfzeile) und mit
dem echten Hauptfenster offscreen (Glasleiste, Ergebnismaske, Kopfzeile,
Lasten).

Aufruf:  python -m tests.test_ergebnisbild
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Einstellungen in eine Wegwerfdatei - die Pruefung darf die des Anwenders
# nicht ueberschreiben
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ergebnisbild_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver, examples_lib  # noqa: E402

RESULTS = []
_FENSTER: dict = {}
_HALLE: dict = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:70s} {detail}")
    return ok


def _halle():
    """Hallenrahmen einmal gerechnet (Modell, Analyse) - wie im Beispiel."""
    if not _HALLE:
        m = examples_lib.hall_frame_example()
        an = solver.solve_all(m, design=bool(m.members))
        _HALLE.update(m=m, an=an)
    return _HALLE["m"], _HALLE["an"]


def _zahl(zeile: str) -> float:
    """Die erste Zahl einer Kennwertzeile („u   73.52 Knoten 14 [mm]“)."""
    for t in zeile.split()[1:]:
        try:
            return float(t.replace(",", "."))
        except ValueError:
            continue
    return float("nan")


# --------------------------------------------------------------------------
# ohne Fenster
# --------------------------------------------------------------------------
def test_kennwerte_aus_dem_feld_der_faerbung():
    from statik3d.gui import viewport as vp
    m, an = _halle()
    env = an.envelopes["ULS"]
    ps, _c, name = vp.result_field(m, env, "|u| Verschiebung")
    soll = float(np.nanmax(ps))
    z = [x for x in vp.kennwerte(m, env, None, "", feld="|u| Verschiebung") if x.startswith("u ")]
    ist = _zahl(z[0]) if z else float("nan")
    check("Halle, Umhüllende ULS: Kennwert u = größter Wert der Färbung (73,52 mm)",
          abs(ist - round(soll, 2)) < 0.006 and abs(soll - 73.52) < 0.01,
          f"Kennwert {ist} / Färbung {soll:.4f} ({name})")
    check("… nicht das Gemisch der Richtungen (79,23 mm)", abs(ist - 79.23) > 1.0, str(z))
    # je Richtung: kleinster und groesster Wert wie die Faerbung ux/uy/uz
    for f in ("ux", "uy", "uz"):
        w, _c, _n = vp.result_field(m, env, f)
        zz = [x for x in vp.kennwerte(m, env, None, "", feld=f) if x.startswith(f)]
        teile = zz[0].split() if zz else []
        zahlen = [float(t) for t in teile[1:3]] if len(teile) >= 3 else []
        check(f"… {f}: min/max wie die Färbung",
              len(zahlen) == 2 and abs(zahlen[0] - round(float(np.nanmin(w)), 2)) < 0.006
              and abs(zahlen[1] - round(float(np.nanmax(w)), 2)) < 0.006,
              f"{zz} / {np.nanmin(w):.3f} … {np.nanmax(w):.3f}")
    # eine einzelne Kombination: unveraendert der Betrag ihres u
    r = an.combinations["GZT4"]
    z = [x for x in vp.kennwerte(m, r, None, "", feld="|u| Verschiebung") if x.startswith("u ")]
    soll = float(np.linalg.norm(r.u[:, :3], axis=1).max() * 1000)
    check("… Kombination GZT4: Kennwert u = ihr größtes |u|",
          z and abs(_zahl(z[0]) - round(soll, 2)) < 0.006, f"{z} / {soll:.3f}")


def test_figur_der_umhuellenden():
    from statik3d.gui import viewport as vp
    m, an = _halle()
    env = an.envelopes["ULS"]
    u, figur = vp.figur(an, env)
    check("Figur der Umhüllenden ULS: die maßgebende Kombination GZT4",
          figur == "GZT4", repr(figur))
    check("… ihre Verformung, kein Gemisch",
          u is not None and np.array_equal(u, an.combinations["GZT4"].u))
    check("… und ihr größtes |u| ist das der Färbung",
          u is not None and abs(np.linalg.norm(u[:, :3], axis=1).max() - env.umag_max.max()) < 1e-12)
    r = an.combinations["GZT7"]
    u2, f2 = vp.figur(an, r)
    check("Kombination: ihre eigene Verformung, keine Figur-Zeile",
          u2 is r.u and f2 == "", repr(f2))
    # ohne die Ergebnisse der Kombinationen (Ergebnisdatei, verworfene
    # Alternativen) gibt es keine maßgebende Figur - dann sagt es die Zeile
    u3, f3 = vp.figur(None, env)
    check("ohne Einzelergebnisse: Extremwerte je Richtung, und die Zeile sagt es",
          u3 is not None and f3 == vp.FIGUR_GEMISCHT, repr(f3))
    z = vp.kopfzeile(m, env, "Umhüllende ULS", "|u| Verschiebung", figur="GZT4")
    check("Kopfzeile: „Figur: GZT4“", any(x.strip() == "Figur: GZT4" for x in z), str(z))


# --------------------------------------------------------------------------
# mit Fenster
# --------------------------------------------------------------------------
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
    _FENSTER.update(w=w, app=app)
    return w, app


def _halle_im_fenster():
    w, app = _fenster()
    w.load_example("hall"); app.processEvents()
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an); app.processEvents()
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()
    return w, app, an


def _eintraege(cb) -> list:
    return [(cb.itemText(i), cb.itemData(i)) for i in range(cb.count())]


def _index(cb, daten) -> int:
    for i in range(cb.count()):
        d = cb.itemData(i)
        if d is not None and tuple(d) == tuple(daten):
            return i
    return -1


def test_glasleiste_fuehrt_alle_ergebnisse():
    from PySide6 import QtCore
    w, app, an = _halle_im_fenster()
    cbl, cbr = w.cb_lastwahl, w.cb_result
    check("nach der Rechnung zeigt die Ergebnismaske die Umhüllende ULS",
          cbr.currentData() == ("env", "ULS"), str(cbr.currentData()))
    check("Glasleiste steht auf demselben (nicht auf LF1)",
          cbl.currentData() == ("env", "ULS"), f"{cbl.currentText()} {cbl.currentData()}")
    eintr = _eintraege(cbl)
    daten = [tuple(d) for _t, d in eintr if d is not None]
    fehlt = [cbr.itemData(i) for i in range(cbr.count()) if tuple(cbr.itemData(i)) not in daten]
    check("… sie führt jeden Eintrag der Ergebnismaske", not fehlt, str(fehlt[:3]))
    m = w.model
    check("… und jeden Lastfall und jede Kombination des Modells",
          all(("case", n) in daten for n in m.load_cases)
          and all(("combo", n) in daten for n in m.combinations),
          f"{len(daten)} Einträge")
    check("… jeder Eintrag genau einmal", len(daten) == len(set(daten)))
    koepfe = [(i, t) for i, (t, d) in enumerate(eintr) if d is None]
    titel = [t for _i, t in koepfe]
    check("gegliedert: Lastfälle, Kombinationen, Umhüllende",
          titel == ["Lastfälle", "Kombinationen", "Umhüllende"], str(titel))
    mod = cbl.model()
    check("… die Überschriften sind nicht wählbar",
          all(not (mod.flags(mod.index(i, 0)) & QtCore.Qt.ItemIsEnabled) for i, _t in koepfe))
    check("… auf jede Überschrift folgt ein Eintrag",
          all(i + 1 < len(eintr) and eintr[i + 1][1] is not None for i, _t in koepfe))
    # rechts gewaehlt -> Glasleiste folgt, fuer jede Art
    for ziel in (("case", "S"), ("combo", "GZT4"), ("env", "SLS_CH"), ("env", "ULS")):
        cbr.setCurrentIndex(_index(cbr, ziel)); app.processEvents()
        check(f"Ergebnismaske auf {ziel[1]}: Glasleiste zeigt dasselbe",
              cbl.currentData() == cbr.currentData() == ziel, f"{cbl.currentData()} / {cbr.currentData()}")


def test_umhuellende_waehlen_laesst_den_lastfall():
    w, app, an = _halle_im_fenster()
    cbl, cbr = w.cb_lastwahl, w.cb_result
    cbl.setCurrentIndex(_index(cbl, ("case", "W_links"))); app.processEvents()
    check("Lastfall in der Glasleiste: er wird der aktive (wie bisher)",
          w.model.active_case == "W_links" and cbr.currentData() == ("case", "W_links"),
          f"{w.model.active_case} / {cbr.currentData()}")
    cbl.setCurrentIndex(_index(cbl, ("env", "SLS_CH"))); app.processEvents()
    check("Umhüllende in der Glasleiste: die Ergebnismaske folgt",
          cbr.currentData() == ("env", "SLS_CH"), str(cbr.currentData()))
    check("… der aktive Lastfall bleibt", w.model.active_case == "W_links", w.model.active_case)
    cbl.setCurrentIndex(_index(cbl, ("combo", "GZT4"))); app.processEvents()
    check("Kombination in der Glasleiste: Ergebnismaske folgt, aktiver Lastfall bleibt",
          cbr.currentData() == ("combo", "GZT4") and w.model.active_case == "W_links",
          f"{cbr.currentData()} / {w.model.active_case}")
    kopf = [i for i in range(cbl.count()) if cbl.itemData(i) is None]
    vorher = cbr.currentData()
    cbl.setCurrentIndex(kopf[0]); app.processEvents()
    check("eine Überschrift gewählt: nichts ändert sich, die Leiste springt zurück",
          cbr.currentData() == vorher and cbl.currentData() == vorher,
          f"{cbl.currentData()} / {cbr.currentData()}")


def test_kennwerte_und_figur_im_bild():
    w, app, an = _halle_im_fenster()
    w.cb_result.setCurrentIndex(_index(w.cb_result, ("env", "ULS"))); app.processEvents()
    zeilen = list(w._kopfzeile_zeilen or [])
    check("Kopfzeile der Umhüllenden nennt die Figur: GZT4",
          any(z.strip() == "Figur: GZT4" for z in zeilen), str(zeilen))
    u_bild = getattr(w, "_bild_figur", (None, None))[1]
    check("… das Bild zeigt die Verformung von GZT4",
          u_bild is not None and np.array_equal(u_bild, an.combinations["GZT4"].u))
    kw = [z for z in (w._kennwerte_zeilen or []) if z.startswith("u ")]
    skala = [a.mapper.scalar_range for n, a in w.plotter.renderer.actors.items()
             if n.startswith("result_") and a.mapper is not None
             and getattr(a.mapper, "scalar_visibility", False)]
    hoch = max((float(s[1]) for s in skala), default=float("nan"))
    check("Kennwert u = obere Grenze der Legende (73,52 mm)",
          kw and abs(_zahl(kw[0]) - round(hoch, 2)) < 0.006 and abs(hoch - 73.52) < 0.01,
          f"{kw} / Legende {hoch:.4f}")
    w.cb_result.setCurrentIndex(_index(w.cb_result, ("combo", "GZT7"))); app.processEvents()
    check("Kombination: keine Figur-Zeile (die Figur ist sie selbst)",
          not any("Figur" in z for z in (w._kopfzeile_zeilen or [])), str(w._kopfzeile_zeilen))


def test_lasten_im_ergebnisbild():
    w, app, an = _halle_im_fenster()
    cbr = w.cb_result
    a = getattr(w, "act_lasten_ergebnis", None)
    check("Schalter „Lasten im Ergebnisbild“ vorhanden, Vorgabe aus",
          a is not None and a.isCheckable() and not a.isChecked())
    if a is None:
        return
    for ziel in (("env", "ULS"), ("combo", "GZT4")):
        cbr.setCurrentIndex(_index(cbr, ziel)); app.processEvents()
        check(f"{ziel[1]}: keine Lasten im Bild, keine Lastzeile oben links",
              not w._lastpunkte and not any(z.strip().startswith("Lasten") and "[" in z
                                            for z in w._kopfzeile_zeilen),
              f"{len(w._lastpunkte)} Lastsymbole, {w._kopfzeile_zeilen}")
        # Nachbesserung 24.09.2026: dass sie fehlen, steht da (sonst sucht man
        # eine gerade angelegte Last vergeblich)
        check(f"… die Kopfzeile sagt, dass die Lasten ausgeblendet sind und wo sie herkommen",
              any(z.strip() == "Lasten ausgeblendet (Ergebnisse → Lasten im Ergebnisbild)"
                  for z in w._kopfzeile_zeilen), str(w._kopfzeile_zeilen))
    a.setChecked(True); app.processEvents()
    check("Schalter an: kein Hinweis „Lasten ausgeblendet“ mehr",
          not any("Lasten ausgeblendet" in z for z in w._kopfzeile_zeilen), str(w._kopfzeile_zeilen))
    akt = w.model.active_case
    check("Schalter an: die Lasten des aktiven Lastfalls, und die Kopfzeile nennt ihn",
          bool(w._lastpunkte) and any(z.strip().startswith(f"Lasten {akt} [")
                                      for z in w._kopfzeile_zeilen),
          f"{len(w._lastpunkte)} Lastsymbole, {w._kopfzeile_zeilen}")
    a.setChecked(False); app.processEvents()
    # ein Lastfall zeigt seine eigenen Lasten - und wird, rechts gewaehlt,
    # der aktive wie in der Glasleiste (Nachbesserung 24.09.2026: vorher blieb
    # LF1 aktiv, die Leiste zeigte „Lastfall W_links“ und eine neue Last ging
    # unsichtbar in LF1)
    w.model.active_case = "LF1"
    cbr.setCurrentIndex(_index(cbr, ("case", "W_links"))); app.processEvents()
    n_w = w.model.load_cases["W_links"].n_loads
    check("Lastfall W_links rechts gewählt: seine Lasten im Bild, die Kopfzeile nennt ihn",
          bool(w._lastpunkte) and any(z.strip().startswith("Lasten W_links [")
                                      for z in w._kopfzeile_zeilen)
          and getattr(w, "_lastfall_im_bild", None) == "W_links",
          f"{len(w._lastpunkte)} Symbole ({n_w} Lasten), {w._kopfzeile_zeilen}")
    check("… und er ist jetzt der aktive (wie bei der Wahl in der Glasleiste)",
          w.model.active_case == "W_links" and "W_links" in w.lbl_active.text()
          and w.cb_lastwahl.currentData() == ("case", "W_links"),
          f"{w.model.active_case} / {w.lbl_active.text()}")
    n_sym = len(w._lastpunkte)
    w.selection = np.array([3])
    for e, v in zip(w.ld, (0.0, 0.0, -10.0, 0.0, 0.0, 0.0)):
        try:
            e.setValue(v)
        except Exception:        # noqa: BLE001 - Feld ohne setValue
            e.setText(str(v))
    w.add_load(); app.processEvents()
    check("… eine neue Knotenlast landet in W_links und steht im Bild",
          w.model.load_cases["W_links"].n_loads == n_w + 1 and len(w._lastpunkte) == n_sym + 1,
          f"W_links {w.model.load_cases['W_links'].n_loads} Lasten, Symbole {n_sym} -> "
          f"{len(w._lastpunkte)}")
    w.undo(); app.processEvents()
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an); app.processEvents()
    cbr.setCurrentIndex(_index(cbr, ("case", "W_links"))); app.processEvents()
    # der aktive Lastfall wechselt in der Maske Lastfaelle: das gezeigte
    # Lastfall-Ergebnis folgt ihm
    w.tbl_lc.selectRow(list(w.model.load_cases).index("S")); app.processEvents()
    check("aktiver Lastfall in der Lastfalltabelle auf S: Ergebnis und Leiste folgen",
          w.model.active_case == "S" and cbr.currentData() == ("case", "S")
          and w.cb_lastwahl.currentData() == ("case", "S"),
          f"{w.model.active_case} / {cbr.currentData()} / {w.cb_lastwahl.currentData()}")
    cbr.setCurrentIndex(_index(cbr, ("case", "W_links"))); app.processEvents()
    # ein Klick auf einen dieser Pfeile trifft die Last von W_links, nicht
    # die gleichnummerige von LF1
    alt_art = w.auswahlart
    w.auswahlart_setzen("Last")
    liste, k, punkt = w._lastpunkte[0][:3]
    w._picked(np.asarray(punkt, float)); app.processEvents()
    check("… ein Klick auf einen Lastpfeil wählt die Last von W_links",
          bool(w.sel_lasten) and w.sel_lasten[0][0] == "W_links", str(w.sel_lasten[:1]))
    w.sel_lasten = []
    w.auswahlart_setzen(alt_art)
    w.maske_zeigen("Ergebnisse"); app.processEvents()
    w.act_loads.setChecked(False); app.processEvents()
    check("… der Schalter „Lasten“ nimmt sie weiter ganz weg", not w._lastpunkte)
    w.act_loads.setChecked(True); app.processEvents()
    # ohne Ergebnis wie bisher: der aktive Lastfall
    w.act_ergebnisse.setChecked(False); app.processEvents()
    check("Ergebnisse ausgeblendet: die Lasten des aktiven Lastfalls (W_links)",
          bool(w._lastpunkte) and getattr(w, "_lastfall_im_bild", None) == "W_links",
          str(getattr(w, "_lastfall_im_bild", None)))
    w.act_ergebnisse.setChecked(True); app.processEvents()


def test_ausgeblendet_steht_die_leiste_auf_dem_lastfall():
    """Nachbesserung 24.09.2026: Bei ausgeblendeten Ergebnissen zeigt das Bild
    den aktiven Lastfall - die Leiste auch. Vorher blieb sie auf „Umhüllende
    SLS_CH“, Bild und Kopfzeile zeigten LF1."""
    w, app, an = _halle_im_fenster()
    cbl, cbr = w.cb_lastwahl, w.cb_result
    cbr.setCurrentIndex(_index(cbr, ("env", "SLS_CH"))); app.processEvents()
    w.act_ergebnisse.setChecked(False); app.processEvents()
    akt = w.model.active_case
    check("Ergebnisse aus: Leiste auf dem aktiven Lastfall, wie Bild und Kopfzeile",
          cbl.currentData() == ("case", akt) and w._kopfzeile_zeilen
          and w._kopfzeile_zeilen[0].startswith(f"Lastfall {akt}"),
          f"{cbl.currentData()} / {w._kopfzeile_zeilen[:1]}")
    check("… die Wahl der Ergebnismaske bleibt gemerkt", cbr.currentData() == ("env", "SLS_CH"))
    w.act_ergebnisse.setChecked(True); app.processEvents()
    check("wieder an: Leiste zurück auf der Umhüllenden SLS_CH",
          cbl.currentData() == ("env", "SLS_CH"), str(cbl.currentData()))
    # ausgeblendet eine Kombination in der Leiste waehlen: sie zeigt sich
    w.act_ergebnisse.setChecked(False); app.processEvents()
    cbl.setCurrentIndex(_index(cbl, ("combo", "GZT4"))); app.processEvents()
    check("ausgeblendet Kombination GZT4 in der Leiste gewählt: Ergebnisse wieder an, "
          "Bild und Leiste zeigen GZT4",
          w.ergebnisse_sichtbar() and cbr.currentData() == ("combo", "GZT4")
          and cbl.currentData() == ("combo", "GZT4")
          and w._kopfzeile_zeilen and w._kopfzeile_zeilen[0] == "Kombination GZT4",
          f"{w.ergebnisse_sichtbar()} / {cbl.currentData()} / {w._kopfzeile_zeilen[:1]}")


def test_lastfall_ohne_ergebnis():
    """Nachbesserung 24.09.2026: nach der Rechnung einen Lastfall anlegen und
    in der Leiste waehlen. Vorher sprang die Leiste ohne Meldung auf die
    Umhuellende zurueck, der Lastfall wurde trotzdem aktiv, und eine Last
    darin erschien nirgends (0 Symbole)."""
    w, app, an = _halle_im_fenster()
    cbl = w.cb_lastwahl
    w.merken("Lastfall W_neu")
    w.model.add_load_case("W_neu", "W", "neu")
    w.refresh_all(); app.processEvents()
    n_log = len(w.log.toPlainText().splitlines())
    cbl.setCurrentIndex(_index(cbl, ("case", "W_neu"))); app.processEvents()
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("Lastfall W_neu (ohne Ergebnis) gewählt: er ist aktiv, die Leiste bleibt auf ihm",
          w.model.active_case == "W_neu" and cbl.currentData() == ("case", "W_neu"),
          f"{w.model.active_case} / {cbl.currentData()}")
    check("… die Ergebnisse sind ausgeblendet, das Protokoll sagt es",
          not w.ergebnisse_sichtbar() and any("Lastfall W_neu: noch kein Ergebnis" in z for z in neu),
          str(neu))
    w.selection = np.array([3])
    for e, v in zip(w.ld, (0.0, 0.0, -10.0, 0.0, 0.0, 0.0)):
        try:
            e.setValue(v)
        except Exception:        # noqa: BLE001
            e.setText(str(v))
    w.add_load(); app.processEvents()
    check("… eine Knotenlast darin steht im Bild, die Kopfzeile nennt W_neu",
          w.model.load_cases["W_neu"].n_loads == 1 and len(w._lastpunkte) == 1
          and w._kopfzeile_zeilen and w._kopfzeile_zeilen[0].startswith("Lastfall W_neu"),
          f"{len(w._lastpunkte)} Symbole, {w._kopfzeile_zeilen[:1]}")
    w.act_ergebnisse.setChecked(True); app.processEvents()
    check("Ergebnisse wieder an: das Bild zeigt die Umhüllende, die Leiste auch",
          cbl.currentData() == w.cb_result.currentData() == ("env", "ULS"),
          f"{cbl.currentData()} / {w.cb_result.currentData()}")


def test_kombination_vor_der_rechnung():
    """Eine Kombination ohne Ergebnis: Protokoll, und die Leiste springt auf
    das zurueck, was das Bild weiter zeigt (den aktiven Lastfall)."""
    w, app = _fenster()
    w.load_example("hall"); app.processEvents()
    cbl = w.cb_lastwahl
    akt = w.model.active_case
    cbl.setCurrentIndex(_index(cbl, ("combo", "GZT4"))); app.processEvents()
    check("vor der Rechnung Kombination GZT4 gewählt: Protokoll sagt, woran es liegt",
          "sobald gerechnet ist" in w.log.toPlainText().splitlines()[-1],
          w.log.toPlainText().splitlines()[-1][:80])
    check("… die Leiste steht wieder auf dem aktiven Lastfall",
          cbl.currentData() == ("case", akt) and w.model.active_case == akt,
          f"{cbl.currentData()} / {w.model.active_case}")


def test_statisch_dann_eigenformen():
    """Nachbesserung 24.09.2026: nach der statischen Rechnung Eigenformen (so
    auch der Schwingungsnachweis). Die Ergebnismaske fuehrt nur die Formen;
    die Leiste fuehrte die Umhuellenden weiter und meldete bei der Wahl
    „sobald gerechnet ist“, obwohl gerechnet war."""
    w, app, an = _halle_im_fenster()
    cbl = w.cb_lastwahl
    r = solver.solve_modal(w.model, 3)
    w._solve_done("modal", r); app.processEvents()
    daten = [tuple(d) for _t, d in _eintraege(cbl) if d is not None]
    koepfe = [t for t, d in _eintraege(cbl) if d is None]
    check("Eigenformen gezeigt: keine Umhüllende in der Leiste (die Maske führt keine)",
          not any(d[0] == "env" for d in daten) and "Umhüllende" not in koepfe
          and [w.cb_result.itemData(i) for i in range(w.cb_result.count())] == [("single", None)],
          str(koepfe))
    check("… Formen, Lastfälle und Kombinationen des Modells bleiben",
          sum(1 for d in daten if d[0] == "form") == 3
          and all(("case", n) in daten for n in w.model.load_cases)
          and all(("combo", n) in daten for n in w.model.combinations), f"{len(daten)} Einträge")
    n_log = len(w.log.toPlainText().splitlines())
    cbl.setCurrentIndex(_index(cbl, ("combo", "GZT4"))); app.processEvents()
    neu = w.log.toPlainText().splitlines()[n_log:]
    check("Kombination gewählt: die Meldung nennt die Eigenformen, nicht „sobald gerechnet ist“",
          neu and "Eigen- bzw. Knickformen" in neu[-1] and "sobald gerechnet" not in neu[-1],
          str(neu))
    check("… die Leiste springt auf die gezeigte Form zurück",
          cbl.currentData() == ("form", 0), str(cbl.currentData()))
    cbl.setCurrentIndex(_index(cbl, ("case", "W_links"))); app.processEvents()
    check("Lastfall gewählt: aktiv, Ergebnisse ausgeblendet, Leiste und Bild zeigen ihn",
          w.model.active_case == "W_links" and not w.ergebnisse_sichtbar()
          and cbl.currentData() == ("case", "W_links")
          and getattr(w, "_lastfall_im_bild", None) == "W_links",
          f"{w.model.active_case} / {w.ergebnisse_sichtbar()} / {cbl.currentData()}")
    cbl.setCurrentIndex(_index(cbl, ("form", 1))); app.processEvents()
    check("Form 2 gewählt: Ergebnisse wieder an, sie wird gezeigt",
          w.ergebnisse_sichtbar() and w.cb_mode.currentIndex() == 1
          and cbl.currentData() == ("form", 1), str(cbl.currentData()))


def test_rueckgaengig_leert_die_ergebnismaske():
    """Nachbesserung 24.09.2026: Rueckgaengig verwirft die Ergebnisse - die
    Maske Ergebnisse zeigte weiter „Kombination GZT4“, die Leiste LF1."""
    w, app, an = _halle_im_fenster()
    w.cb_lastwahl.setCurrentIndex(_index(w.cb_lastwahl, ("combo", "GZT4"))); app.processEvents()
    w.merken("Probe")
    w.undo(); app.processEvents()
    check("nach Rückgängig: Ergebnismaske leer, Leiste auf dem aktiven Lastfall",
          w.cb_result.count() == 0 and w.cb_mode.count() == 0
          and w.cb_lastwahl.currentData() == ("case", w.model.active_case),
          f"{w.cb_result.count()} Einträge, {w.cb_lastwahl.currentData()}")


def test_umhuellende_aus_einem_lastfall():
    """Nachbesserung 24.09.2026: Rahmen mit nur LF1 - die „Umhüllende CASES“
    ist dieser Lastfall und zeigt seine Lasten (vorher 33 -> 0 Symbole nach
    „Berechnen“; sechs der acht Beispiele)."""
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    vorher = len(w._lastpunkte or [])
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an); app.processEvents()
    env = w.current_result()
    check("Rahmen gerechnet: gezeigt wird eine Umhüllende aus genau LF1",
          w.cb_result.currentData()[0] == "env" and list(getattr(env, "names", [])) == ["LF1"],
          f"{w.cb_result.currentData()} {getattr(env, 'names', None)}")
    check("… ihre Lasten stehen im Bild wie vor der Rechnung, die Kopfzeile nennt LF1",
          vorher > 0 and len(w._lastpunkte) == vorher
          and any(z.strip().startswith("Lasten LF1 [") for z in w._kopfzeile_zeilen),
          f"{vorher} -> {len(w._lastpunkte)}, {w._kopfzeile_zeilen}")


def test_sichtbare_texte():
    """Nachbesserung 24.09.2026: Hinweistexte nachgezogen, „Figur“ nur mit Figur."""
    w, app, an = _halle_im_fenster()
    tip = w.cb_lastwahl.toolTip()
    check("Hinweis der Leisten-Liste nennt Umhüllende und Eigenform",
          "Umhüllende" in tip and "Eigenform" in tip, tip)
    check("Hinweis des Schalters „Lasten“ nennt „Lasten im Ergebnisbild“",
          "Lasten im Ergebnisbild" in w.act_loads.toolTip(), w.act_loads.toolTip())
    w.cb_result.setCurrentIndex(_index(w.cb_result, ("env", "ULS"))); app.processEvents()
    alt = w.sl_scale.value()
    w.sl_scale.setValue(0); app.processEvents()
    check("Überhöhung 0 (keine verformte Figur): keine Zeile „Figur: …“",
          not any("Figur" in z for z in w._kopfzeile_zeilen), str(w._kopfzeile_zeilen))
    w.sl_scale.setValue(alt); app.processEvents()
    check("… mit Überhöhung wieder „Figur: GZT4“",
          any(z.strip() == "Figur: GZT4" for z in w._kopfzeile_zeilen), str(w._kopfzeile_zeilen))


def test_eigenformen_in_der_glasleiste():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    r = solver.solve_modal(w.model, 4)
    w._solve_done("modal", r); app.processEvents()
    cbl = w.cb_lastwahl
    formen = [(t, tuple(d)) for t, d in _eintraege(cbl) if d is not None and d[0] == "form"]
    check("Eigenformen: die Glasleiste führt jede Form",
          len(formen) == w.cb_mode.count() == 4 and formen[0][0] == w.cb_mode.itemText(0),
          str(formen[:2]))
    check("… unter der Überschrift „Eigenformen“",
          "Eigenformen" in [t for t, d in _eintraege(cbl) if d is None])
    check("… und steht auf der gezeigten Form", cbl.currentData() == ("form", 0), str(cbl.currentData()))
    cbl.setCurrentIndex(_index(cbl, ("form", 2))); app.processEvents()
    check("Form 3 in der Glasleiste gewählt: die Ergebnismaske zeigt sie",
          w.cb_mode.currentIndex() == 2, str(w.cb_mode.currentIndex()))
    w.cb_mode.setCurrentIndex(1); app.processEvents()
    check("… und umgekehrt", cbl.currentData() == ("form", 1), str(cbl.currentData()))


def test_vor_der_rechnung():
    """Ohne Ergebnis wie bisher: Lastfaelle und Kombinationen, der aktive
    Lastfall ist gewaehlt."""
    w, app = _fenster()
    w.load_example("hall"); app.processEvents()
    cbl = w.cb_lastwahl
    daten = [tuple(d) for _t, d in _eintraege(cbl) if d is not None]
    check("vor der Rechnung: Lastfälle und Kombinationen, keine Umhüllende",
          len(daten) == len(w.model.load_cases) + len(w.model.combinations)
          and not any(d[0] == "env" for d in daten), f"{len(daten)} Einträge")
    check("… auf dem aktiven Lastfall", cbl.currentData() == ("case", w.model.active_case))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_kennwerte_aus_dem_feld_der_faerbung, test_figur_der_umhuellenden,
              test_glasleiste_fuehrt_alle_ergebnisse, test_umhuellende_waehlen_laesst_den_lastfall,
              test_kennwerte_und_figur_im_bild, test_lasten_im_ergebnisbild,
              test_ausgeblendet_steht_die_leiste_auf_dem_lastfall, test_lastfall_ohne_ergebnis,
              test_kombination_vor_der_rechnung, test_statisch_dann_eigenformen,
              test_rueckgaengig_leert_die_ergebnismaske, test_umhuellende_aus_einem_lastfall,
              test_sichtbare_texte,
              test_eigenformen_in_der_glasleiste, test_vor_der_rechnung):
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
