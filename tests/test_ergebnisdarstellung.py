"""
Ergebnisdarstellung (Paket 6b des Oberflaechenplans, 25.09.2026).

Befunde am Stand 562dc3a (Analyse bilder/036_…, vp_zoom/028_mitte.png,
vp_zoom/033_legende.png, vp_zoom/036_legende.png):

* Die Umhuellende zeigte im Schnittgroessenverlauf **eine** Linie mit dem
  betragsgroesseren Extrem je Stelle - weder die groessten noch die
  kleinsten Werte als Verlauf.
* Die Farbskala des Verlaufs lag nicht symmetrisch um 0 (Hallenrahmen My:
  -393 … 291 kNm, Mitte -51 kNm in Grau).
* Keine Max-/Min-Marken, keine Werte am Verlauf ohne eigenes Einschalten.
* Der Verlauf lag an der unverformten Achse, der Stab daneben verformt; die
  Knoten schwebten am unverformten Ort ueber dem verformten Koerper.
* Die Legende hiess „|u| max [mm]“ und war als „u max“ zu lesen; sie blieb
  bei mm/kN, auch wenn Ansicht → Einheiten cm oder N einstellte.
* Die Ueberhoehung war ein Schieber 0 … 100 ohne Einheit; der Bericht
  bekam dessen Stellung (30) statt des Faktors.
* Rechts gab es keine Ergebnissteuerung, die neben einer Maske stehen
  bleibt; nach F5 blieb das Ribbon, wo es war.

Aufruf:  python -m tests.test_ergebnisdarstellung
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
    tempfile.mkdtemp(prefix="statik3d_ergebnisdarstellung_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver  # noqa: E402

RESULTS = []
_FENSTER: dict = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:74s} {detail}")
    return ok


# --------------------------------------------------------------------------
# ohne Fenster
# --------------------------------------------------------------------------
def test_bezeichnungen_ohne_verlierbare_zeichen():
    from statik3d.gui import viewport as vp
    from statik3d import spannungen as spn
    namen = [("|u| Verschiebung", "|u| [mm]"), ("|u| Verschiebung", "|u| max [mm]"),
             ("ux", "ux extrem [mm]"), ("|φ| Verdrehung", "|φ| max [mrad]"),
             ("φy", "φy [mrad]"), ("Vergleichsspannung", "σv max [MPa]")]
    namen += [(spn.feldname(a, g), spn.beschriftung(a, g)) for a in spn.ARTEN for g in spn.GROESSEN[a]]
    schlecht = []
    for feld, name in namen:
        _f, titel = vp.skalentitel(feld, name)
        try:
            titel.encode("latin-1")
            ok = not any(z in titel for z in ("|u|", "|φ|", "φ", "σ", "τ", "?"))
        except UnicodeEncodeError:
            ok = False
        if not ok:
            schlecht.append(titel)
    check("Legende: jede Bezeichnung Latin-1, ohne „|u|“, φ, σ, τ", not schlecht, str(schlecht[:3]))
    _f, t = vp.skalentitel("|u| Verschiebung", "|u| max [mm]")
    check("… „|u| max [mm]“ heißt „u gesamt max [mm]“", t == "u gesamt max [mm]", t)
    _f, t = vp.skalentitel("|φ| Verdrehung", "|φ| [mrad]")
    check("… „|φ| [mrad]“ heißt „phi gesamt [mrad]“", t == "phi gesamt [mrad]", t)


def test_einheiten_der_legende():
    from statik3d.gui import viewport as vp
    from statik3d.einheiten import Einheiten
    E = Einheiten(verformung="cm", spannung="kN/cm²", kraft="N")
    f, t = vp.skalentitel("|u| Verschiebung", "|u| max [mm]", E)
    check("Verformung in cm: Faktor 0,1 auf mm, Titel [cm]", abs(f - 0.1) < 1e-12 and t.endswith("[cm]"),
          f"{f} {t}")
    f, t = vp.skalentitel("Vergleichsspannung", "σv [MPa]", E)
    check("Spannung in kN/cm²: Faktor 0,1 auf MPa, Titel „Vergleichsspannung [kN/cm²]“",
          abs(f - 0.1) < 1e-12 and t == "Vergleichsspannung [kN/cm²]", f"{f} {t}")
    f, e = vp.verlauf_einheit("My", E)
    check("Verlauf My mit Kraft N: Faktor 1 auf Nm, Einheit Nm", abs(f - 1.0) < 1e-12 and e == "Nm",
          f"{f} {e}")
    f, e = vp.verlauf_einheit("N", Einheiten())
    check("Verlauf N in der Vorgabe: kN", abs(f - 1e-3) < 1e-15 and e == "kN", f"{f} {e}")


def test_extremstellen_und_marken():
    from statik3d.gui import viewport as vp
    w = np.array([0.0, 3.0, np.nan, 7.5, 1.0])
    check("Betrag (alle ≥ 0): nur die Max-Stelle", vp.extremstellen(w) == (3, None),
          str(vp.extremstellen(w)))
    w = np.array([0.0, -2.0, -9.0, 1.0])
    check("mit Vorzeichen: Max und Min", vp.extremstellen(w) == (3, 2), str(vp.extremstellen(w)))
    maske = np.array([True, True, False, True])
    check("nur sichtbare Teile zählen", vp.extremstellen(w, maske) == (3, 1),
          str(vp.extremstellen(w, maske)))
    t = vp.marken_text("max", 2391.4567, "kNm")
    check("Marke: Wert und Einheit, nie wissenschaftlich", t == "max 2391 kNm" and "e" not in t[4:], t)
    t = vp.marken_text("min", -0.000123, "mm")
    check("… auch sehr kleine Werte", "e-" not in t and t.startswith("min -0.000") and t.endswith("mm"), t)
    check("symmetrische Skala: [-a, a]", vp.symmetrische_grenzen([-393.0, 291.0]) == [-393.0, 393.0],
          str(vp.symmetrische_grenzen([-393.0, 291.0])))


def test_lager_an_der_verformten_lage():
    import pyvista as pv
    from statik3d.gui import viewport as vp
    from statik3d.model import Model, Support
    m = Model()
    m.add_node(0, 0, 0)
    m.add_node(4, 0, 0)
    m.supports.append(Support(1, [1, 2]))
    lage = np.asarray(m.nodes, float) + np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]])
    pl = pv.Plotter(off_screen=True)
    try:
        vp.add_supports(pl, m, 4.0)
        vorher = np.asarray(pl.renderer.actors["supports0"].GetCenter())
        vp.add_supports(pl, m, 4.0, lage=lage)
        a = pl.renderer.actors.get("supports0")
        mitte = np.asarray(a.GetCenter()) if a is not None else None
        check("Lagersymbol an der verformten Lage des Knotens (um 0,5 m in x mitgenommen)",
              mitte is not None and np.allclose(mitte - vorher, [0.5, 0.0, 0.0], atol=1e-9),
              f"{vorher} -> {mitte}")
    finally:
        pl.close()


def test_bericht_nennt_den_faktor():
    """Die Zeile „Überhöhung“ eines übernommenen Bildes: der Faktor, nie mit
    Exponent (vorher f"{x:g}": 1480123.4 -> „1.48012e+06“)."""
    from statik3d import examples_lib
    from statik3d.model import Berichtseintrag
    from statik3d.report.html import Report
    from statik3d.gui import viewport as vp
    m = examples_lib.frame_example()
    r = solver.solve_static(m)
    m.bericht.append(Berichtseintrag(name="Bild 1", quelle="case:LF1", feld="uz",
                                     ueberhoehung=1480123.4, bild=""))
    html = Report(m, results=r).html()
    check("Bericht: „Überhöhung x1480123.4“, nicht „1.48012e+06“",
          "x1480123.4" in html and "1.48012e+06" not in html,
          " ".join(html[html.find("Überhöhung"):html.find("Überhöhung") + 80].split()))
    # Gegenpruefung 25.09.2026: round(…, 1) machte einen Faktor unter 0,05
    # zu 0 - die Zeile fiel weg; der Bericht schrieb „x30.0“ fuer 30
    check("ein kleiner Faktor behält zwei geltende Ziffern (0,034 statt 0)",
          vp.faktor_runden(0.0344) == 0.034 and vp.faktor_runden(17.63) == 17.6
          and vp.faktor_runden(0.0) == 0.0, f"{vp.faktor_runden(0.0344)} {vp.faktor_runden(17.63)}")
    m.bericht[-1].ueberhoehung = 0.034
    m.bericht.append(Berichtseintrag(name="Bild 2", quelle="case:LF1", feld="uz",
                                     ueberhoehung=30.0, bild=""))
    html = Report(m, results=r).html()
    check("Bericht: „x0.034“ und „x30“ (geltende Ziffern, kein angehängtes „.0“)",
          "x0.034" in html and "x30<" in html.replace(" ", "") and "x30.0" not in html,
          " | ".join(" ".join(html[i:i + 60].split()) for i in
                     [j for j in range(len(html)) if html.startswith("Überhöhung", j)][:2]))


def test_marken_kleiner_werte():
    """Gegenpruefung 25.09.2026: die Marken rundeten auf die Nachkommastellen
    der Kennwerte - „max 0.00 mm“ bei uy = 0,0015 mm, das Minuszeichen fiel
    weg. Unter einer halben Einheit der letzten Stelle: zwei geltende Ziffern."""
    from statik3d.gui import viewport as vp
    t_max = vp.marken_text("max", 0.0015, "mm", 2)
    t_min = vp.marken_text("min", -0.0015, "mm", 2)
    check("uy ±0,0015 mm mit 2 Nachkommastellen: „max 0.0015 mm“, „min -0.0015 mm“",
          t_max == "max 0.0015 mm" and t_min == "min -0.0015 mm", f"{t_max} / {t_min}")
    t = vp.marken_text("max", 0.063e-3, "m", 2)
    check("0,063 mm in m: „max 0.000063 m“ statt „max 0.00 m“", t == "max 0.000063 m", t)
    t = vp.marken_text("max", 73.5249, "mm", 2)
    check("… große Werte wie bisher mit den Nachkommastellen der Kennwerte", t == "max 73.52 mm", t)


def test_kennwerte_spannung_in_der_legendeneinheit():
    """Die Spannungszeile der Kennwerte steht in der Einheit der Legende und
    ohne Zeichen, die im Bild verloren gehen (Rücknahme: _einheit_umrechnen
    oder bildtext in vp.kennwerte weglassen)."""
    from statik3d import examples_lib
    from statik3d import spannungen as spn
    from statik3d.einheiten import Einheiten
    from statik3d.gui import viewport as vp
    m = examples_lib.solid_example()
    r = solver.solve_static(m)
    feld = spn.feldname("volumen", next(g for g in spn.GROESSEN["volumen"]
                                        if spn.kategorien("volumen", g) is None))
    ak = spn.feld(feld)
    werte = np.asarray(spn.je_knoten(m, r, ak[0], ak[1], "max"), float)
    zeilen = vp.kennwerte(m, r, feld=feld, einheiten=Einheiten(spannung="kN/cm²"))
    z = [x for x in zeilen if "Knoten" in x and "[" in x]
    soll = spn.dezimal(float(np.nanmax(werte)) * 0.1)
    check("Kennwert der Spannung in kN/cm² (Legendeneinheit), Wert ein Zehntel der N/mm²",
          bool(z) and z[-1].endswith("[kN/cm²]") and f"max {soll} " in z[-1], f"{z} / {soll}")
    check("… ohne σ, τ, φ (im Bild verloren)", bool(z) and not any(c in z[-1] for c in "στφ"),
          z[-1] if z else "")


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
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    # ein Fehlerfenster wuerde die Pruefung anhalten - es wird mitgeschrieben
    w._fehler = []
    w.error = lambda msg, *a, **k: w._fehler.append(str(msg))
    _FENSTER.update(w=w, app=app)
    return w, app


def _halle():
    w, app = _fenster()
    w.load_example("hall"); app.processEvents()
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an); app.processEvents()
    w.cb_diagram.setCurrentText("kein Verlauf")
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()
    return w, app, an


def _waehle(w, app, daten):
    cb = w.cb_result
    for i in range(cb.count()):
        if tuple(cb.itemData(i)) == tuple(daten):
            cb.setCurrentIndex(i)
            app.processEvents()
            return True
    return False


def _akteure(w) -> dict:
    """Die Darsteller - Beschriftungen (add_point_labels) heissen in pyvista
    „name-labels“ und „name-points“; hier stehen sie auch unter „name“."""
    akt = dict(w.plotter.renderer.actors)
    for k in list(akt):
        for zusatz in ("-labels", "-points"):
            if k.endswith(zusatz):
                akt.setdefault(k[:-len(zusatz)], akt[k])
    return akt


def _daten(a):
    return a.GetMapper().GetInput() if a is not None else None


def test_umhuellende_zwei_linien():
    import pyvista as pv
    from statik3d.gui import viewport as vp
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    akt = _akteure(w)
    check("Umhüllende, Verlauf My: zwei Linien diagram_max und diagram_min, keine gemischte",
          "diagram_max" in akt and "diagram_min" in akt and "diagram" not in akt,
          str(sorted(k for k in akt if k.startswith("diagram"))))
    if "diagram_max" not in akt:
        return
    rot = tuple(pv.Color(vp.FARBE_VERLAUF_MAX).float_rgb)
    blau = tuple(pv.Color(vp.FARBE_VERLAUF_MIN).float_rgb)
    f_max = tuple(akt["diagram_max"].GetProperty().GetColor())
    f_min = tuple(akt["diagram_min"].GetProperty().GetColor())
    check("… max rot, min blau", np.allclose(f_max, rot) and np.allclose(f_min, blau), f"{f_max} {f_min}")
    env = an.envelopes["ULS"]
    hi = max(float(np.max(d["My"][1])) for d in env.beam.values() if d.get("x") is not None) / 1e3
    lo = min(float(np.min(d["My"][0])) for d in env.beam.values() if d.get("x") is not None) / 1e3
    d_max = pv.wrap(_daten(akt["diagram_max"]))
    d_min = pv.wrap(_daten(akt["diagram_min"]))
    check("… die rote Linie trägt die größten Werte je Stelle (max My)",
          abs(float(np.max(d_max["wert"])) - hi) < 1e-9 * max(1.0, abs(hi)),
          f"{np.max(d_max['wert']):.3f} / {hi:.3f} kNm")
    check("… die blaue die kleinsten (min My)",
          abs(float(np.min(d_min["wert"])) - lo) < 1e-9 * max(1.0, abs(lo)),
          f"{np.min(d_min['wert']):.3f} / {lo:.3f} kNm")
    check("… die Kopfzeile sagt, was rot und was blau ist, mit Einheit",
          any("rot max, blau min" in z and "[kNm]" in z for z in w._kopfzeile_zeilen),
          str(w._kopfzeile_zeilen))


def test_skala_des_verlaufs_symmetrisch():
    w, app, an = _halle()
    _waehle(w, app, ("combo", "GZT4"))
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    a = _akteure(w).get("diagram")
    rng = tuple(a.GetMapper().GetScalarRange()) if a is not None else (0.0, 0.0)
    r = an.combinations["GZT4"]
    groesst = max(float(np.abs(d["My"]).max()) for d in r.stations().values()) / 1e3
    check("Kombination GZT4, My: Farbskala symmetrisch um 0",
          a is not None and abs(rng[0] + rng[1]) < 1e-9 * max(abs(rng[1]), 1.0) and rng[1] > 0,
          str(rng))
    check("… bis zum größten Betrag", abs(rng[1] - groesst) < 1e-6 * groesst, f"{rng[1]:.3f} / {groesst:.3f}")


def test_max_min_marken():
    from statik3d.gui import viewport as vp
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    akt = _akteure(w)
    marken = dict(getattr(w, "_extremmarken", []) or [])
    kw = [z for z in (w._kennwerte_zeilen or []) if z.startswith("u ")]
    kw_zahl = kw[0].split()[1] if kw else "?"
    check("Färbung u gesamt: Max-Marke mit Wert und Einheit wie der Kennwert (73.52 mm)",
          "marke_max" in akt and marken.get("marke_max") == f"max {kw_zahl} mm"
          and kw_zahl == "73.52", f"{marken} / Kennwert {kw_zahl}")
    check("… keine Min-Marke bei einem Betrag", "marke_min" not in akt, str(marken))
    ps, _c, _n = vp.result_field(w.model, an.envelopes["ULS"], "|u| Verschiebung")
    k = int(np.nanargmax(ps))
    s = float(getattr(w, "_ueberhoehung_faktor", float("nan")))
    u = w._bild_figur[1]
    soll = w.model.nodes[k] + s * u[k, :3]
    ist = (np.asarray(_daten(akt["marke_max-points"]).GetPoints().GetPoint(0))
           if "marke_max-points" in akt else None)
    check("… sie sitzt am Knoten des Größtwerts, an der verformten Lage",
          ist is not None and np.allclose(ist, soll, atol=1e-9), f"{ist} / {soll}")
    w.cb_field.setCurrentText("uz"); app.processEvents()
    marken = dict(getattr(w, "_extremmarken", []) or [])
    wz, _c, _n = vp.result_field(w.model, an.envelopes["ULS"], "uz")
    check("Färbung uz: Min-Marke mit dem kleinsten Wert",
          "marke_min" in _akteure(w)
          and marken.get("marke_min") == f"min {float(np.nanmin(wz)):.2f} mm", str(marken))
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    vm = dict(getattr(w, "_verlauf_marken", []) or [])
    env = an.envelopes["ULS"]
    hi = max(float(np.max(d["My"][1])) for d in env.beam.values() if d.get("x") is not None) / 1e3
    lo = min(float(np.min(d["My"][0])) for d in env.beam.values() if d.get("x") is not None) / 1e3
    check("Verlauf My: Max- und Min-Marke des Verlaufs mit kNm",
          "verlauf_max" in _akteure(w) and "verlauf_min" in _akteure(w)
          and vm.get("verlauf_max") == f"max {hi:.2f} kNm" and vm.get("verlauf_min") == f"min {lo:.2f} kNm",
          f"{vm} / {hi:.2f} {lo:.2f}")
    check("… nie wissenschaftlich", all("e+" not in t and "e-" not in t for t in vm.values()), str(vm))
    w.cb_extremmarken.setChecked(False); app.processEvents()
    akt = _akteure(w)
    check("Schalter Max/Min-Marken aus: keine Marke",
          not any(k in akt for k in ("marke_max", "marke_min", "verlauf_max", "verlauf_min")))
    w.cb_extremmarken.setChecked(True)
    w.cb_diagram.setCurrentText("kein Verlauf"); app.processEvents()


def test_werte_am_verlauf():
    w, app, an = _halle()
    cb = getattr(w, "cb_verlaufswerte", None)
    check("„Werte am Verlauf“ gibt es und ist vorab an", cb is not None and cb.isChecked())
    _waehle(w, app, ("combo", "GZT4"))
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    akt = _akteure(w)
    n = int(getattr(w, "_verlaufswerte", 0) or 0)
    check("Verlauf My: Werte stehen am Verlauf, ohne „Werte im Bild“ einzuschalten",
          "verlaufswerte" in akt and n > 0 and not w.act_werte_staebe.isChecked()
          and not any(k.startswith("ergebniswerte") for k in akt), f"{n} Werte")
    check("… je Stab höchstens zwei (größter und kleinster)", n <= 2 * max(1, len(w.model.members)),
          f"{n} für {len(w.model.members)} Stäbe")
    w.cb_diagram.setCurrentText("kein Verlauf"); app.processEvents()
    check("kein Verlauf: keine Werte am Verlauf", "verlaufswerte" not in _akteure(w))


def test_verlauf_am_unverformten_stab():
    from statik3d.gui import viewport as vp
    w, app, an = _halle()
    _waehle(w, app, ("combo", "GZT4"))
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    akt = _akteure(w)
    stab = akt.get("result_stabkoerper") or akt.get("result_netz")
    staebe = [i for i, e in enumerate(w.model.elements) if e.typ in vp.TYPEN_STAEBE]
    ref = vp.stab_koerper(w.model, staebe) if "result_stabkoerper" in akt else vp.teilnetz(w.model, staebe)
    b_ist = np.asarray(_daten(stab).GetBounds()) if stab is not None else None
    check("Verlauf My: der Stab ist unverformt gezeichnet, der Verlauf sitzt auf ihm",
          b_ist is not None and np.allclose(b_ist, np.asarray(ref.bounds), atol=1e-9),
          f"{b_ist} / {np.asarray(ref.bounds)}")
    check("… die Kopfzeile sagt „am unverformten System“",
          any("am unverformten System" in z for z in w._kopfzeile_zeilen), str(w._kopfzeile_zeilen))
    w.cb_diagram.setCurrentText("kein Verlauf"); app.processEvents()
    stab = _akteure(w).get("result_stabkoerper") or _akteure(w).get("result_netz")
    b_verf = np.asarray(_daten(stab).GetBounds()) if stab is not None else None
    check("ohne Verlauf: wieder die verformte Figur",
          b_verf is not None and not np.allclose(b_verf, np.asarray(ref.bounds), atol=1e-6), str(b_verf))


def test_knoten_und_auswahl_an_der_verformten_lage():
    from statik3d.gui import viewport as vp
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    w.act_knoten.setChecked(True); app.processEvents()
    u = w._bild_figur[1]
    # der Faktor „auto“ - so zeichnete auch der Stand vor Paket 6b (Schieber 30)
    s = float(getattr(w, "_ueberhoehung_faktor", None)
              or 0.08 * w.model.characteristic_size() / float(np.abs(np.asarray(u)[:, :3]).max()))
    lage = w.model.nodes + s * np.asarray(u, float)[:, :3]
    a = _akteure(w).get("knoten")
    kn = vp.konstruktionsknoten(w.model)
    P = np.asarray(pv_punkte(a)) if a is not None else None
    check("Knoten an der verformten Lage (nicht über dem verformten Stab schwebend)",
          P is not None and s > 0 and len(P) == len(kn) and np.allclose(P, lage[kn], atol=1e-9),
          f"Faktor {s}, {None if P is None else len(P)} Punkte")
    w.selection = np.array([3]); w.redraw(); app.processEvents()
    a = _akteure(w).get("selection")
    P = np.asarray(pv_punkte(a)) if a is not None else None
    check("gewählter Knoten ebenfalls verformt", P is not None and np.allclose(P[0], lage[3], atol=1e-9),
          f"{None if P is None else P[0]} / {lage[3]}")
    w.selection = np.array([], int); w.redraw(); app.processEvents()
    # der Fang (Klick, Sonde) sucht dort, wo der Knoten gezeichnet ist: der
    # Riegelknoten 14 liegt im Bild um 73,5 mm x Faktor 17,6 = 1,3 m tiefer
    # (offscreen gibt es keinen verlaesslichen Zeiger; geprueft wird, an
    # welchen Lagen die Bildschirmsuche sucht: sie meldet Knoten 14 nur,
    # wenn sie ihn an seiner gezeichneten Lage bekommt)
    k = 14
    suche = w._naechster_am_zeiger
    w._naechster_am_zeiger = lambda X, *a_, **k_: ((k, 0.0) if len(X) > k
                                                   and np.allclose(X[k], lage[k]) else None)
    try:
        p, art, i = w._fangpunkt()
    finally:
        w._naechster_am_zeiger = suche
    check("Klick auf den verformt gezeichneten Knoten 14 trifft Knoten 14 (Modellpunkt zurück)",
          art == "knoten" and i == k and np.allclose(p, w.model.nodes[k]),
          f"{art} {i} / im Bild {np.linalg.norm(lage[k] - w.model.nodes[k]):.2f} m verschoben")


def pv_punkte(a):
    import pyvista as pv
    return pv.wrap(_daten(a)).points


def test_legende_folgt_den_einheiten():
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    titel = list(w.plotter.scalar_bars.keys())
    check("Legende „u gesamt max [mm]“ statt „|u| max [mm]“", "u gesamt max [mm]" in titel, str(titel))
    E = w.model.einheiten
    alt = (E.verformung, E.kraft)
    try:
        E.verformung = "cm"
        w.einheiten_anwenden(); app.processEvents()
        titel = list(w.plotter.scalar_bars.keys())
        rng = [a.GetMapper().GetScalarRange() for n, a in _akteure(w).items()
               if n.startswith("result_") and a.GetMapper() is not None
               and a.GetMapper().GetScalarVisibility()]
        hoch = max((float(r_[1]) for r_ in rng), default=float("nan"))
        kw = [z for z in (w._kennwerte_zeilen or []) if z.startswith("u ")]
        check("Verformung in cm: Legende [cm], größter Wert 7.352", "u gesamt max [cm]" in titel
              and abs(hoch - 7.352) < 0.001, f"{titel} {hoch}")
        check("… Kennwert und Marke in derselben Einheit",
              kw and "[cm]" in kw[0] and dict(w._extremmarken).get("marke_max", "").endswith(" cm"),
              f"{kw} {w._extremmarken}")
        E.kraft = "N"
        _waehle(w, app, ("combo", "GZT4"))
        w.cb_diagram.setCurrentText("My"); app.processEvents()
        titel = list(w.plotter.scalar_bars.keys())
        a = _akteure(w).get("diagram")
        hi = float(a.GetMapper().GetScalarRange()[1]) if a is not None else 0.0
        r = an.combinations["GZT4"]
        groesst = max(float(np.abs(d["My"]).max()) for d in r.stations().values())
        check("Kraft in N: Verlauf „My [Nm]“ und Werte in Nm", "My [Nm]" in titel
              and abs(hi - groesst) < 1e-6 * groesst, f"{titel} {hi:.1f} / {groesst:.1f}")
    finally:
        E.verformung, E.kraft = alt
        w.cb_diagram.setCurrentText("kein Verlauf")
        w.einheiten_anwenden(); app.processEvents()


def test_ueberhoehung():
    from statik3d.gui import zahlenfeld as zf
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    ed = getattr(w, "ed_ueberhoehung", None)
    check("Überhöhung ist ein Zahlenfeld mit „auto“, „1:1“, „aus“",
          isinstance(ed, zf.Zahlenfeld) and set(getattr(w, "btn_ueberhoehung", {})) == {"auto", "1:1", "aus"})
    if ed is None:
        return
    u = w._bild_figur[1]
    umax = float(np.abs(np.asarray(u)[:, :3]).max())
    auto = 0.08 * w.model.characteristic_size() / umax
    check("auto: größte Verschiebung mit 8 % der Modellgröße, das Feld zeigt den Faktor",
          abs(w._ueberhoehung_faktor - auto) < 1e-9 * auto
          and abs(float(ed.text().replace(",", ".").replace(" ", "")) - round(auto, 1)) < 0.051,
          f"{w._ueberhoehung_faktor:.3f} / {auto:.3f}, Feld „{ed.text()}“")
    w.btn_ueberhoehung["1:1"].click(); app.processEvents()
    check("1:1: Faktor 1, die Kopfzeile nennt „Überhöhung x1.0“",
          w._ueberhoehung_faktor == 1.0 and any("Überhöhung x1.0" in z for z in w._kopfzeile_zeilen),
          str(w._kopfzeile_zeilen[:2]))
    w.btn_ueberhoehung["aus"].click(); app.processEvents()
    a = _akteure(w).get("knoten")
    check("aus: keine Verformung, keine Überhöhung in der Kopfzeile",
          w._ueberhoehung_faktor == 0.0 and not any("Überhöhung" in z for z in w._kopfzeile_zeilen),
          str(w._kopfzeile_zeilen[:2]))
    ed.setFocus(); ed.setText("250"); ed.setModified(True); ed.editingFinished.emit(); app.processEvents()
    check("getippt 250: fester Faktor 250", w._ueberhoehung_faktor == 250.0
          and w._ueberhoehung_art == "fest", f"{w._ueberhoehung_faktor} {w._ueberhoehung_art}")
    ed.setText("2.000.000"); ed.setModified(True); ed.editingFinished.emit(); app.processEvents()
    check("ungültig „2.000.000“: nichts ändert sich, das Feld ist rot",
          w._ueberhoehung_faktor == 250.0 and ed.ungueltig(), f"{w._ueberhoehung_faktor}")
    ed.setText("250"); ed.clearFocus(); app.processEvents()
    n = len(w.model.bericht)
    # offscreen gibt es kein Bildschirmfoto des Renderfensters - ein kleines
    # Bild genuegt, geprueft wird die Einstellung am Berichtseintrag
    foto = w.plotter.screenshot
    w.plotter.screenshot = lambda pfad, *a, **k: open(pfad, "wb").write(b"PNG-Probe")
    try:
        w.ansicht_in_bericht(); app.processEvents()
    finally:
        w.plotter.screenshot = foto
    e = w.model.bericht[-1] if len(w.model.bericht) > n else None
    check("der Bericht bekommt den Faktor der Zeichnung (250), nicht eine Schieberstellung",
          e is not None and e.ueberhoehung == 250.0, str(getattr(e, "ueberhoehung", None)))
    w.btn_ueberhoehung["auto"].click(); app.processEvents()
    check("auto: wieder der automatische Faktor", abs(w._ueberhoehung_faktor - auto) < 1e-9 * auto,
          f"{w._ueberhoehung_faktor:.3f}")


def test_ergebnissteuerung_oben_rechts():
    w, app = _fenster()
    w.load_example("hall"); app.processEvents()
    st = getattr(w, "ergebnissteuerung", None)
    check("ohne Ergebnis keine Ergebnissteuerung", st is not None and not st.isVisible())
    if st is None:
        return
    w, app, an = _halle()
    check("nach der Rechnung: oben rechts sichtbar, mit Ergebnis, Färbung und Überhöhung",
          st.isVisible() and w.eingaben_dock.isAncestorOf(st)
          and all(st.isAncestorOf(x) for x in (w.cb_result, w.cb_field, w.ed_ueberhoehung)))
    w.maske_knoten(); app.processEvents()
    mk = w.maskenrand.maske
    oben = st.mapTo(w, st.rect().bottomLeft()).y()
    unten = mk.mapTo(w, mk.rect().topLeft()).y() if mk is not None else -1
    check("eine Maske darunter: die Steuerung bleibt stehen, die Maske steht darunter",
          w.maskenrand.offen() and st.isVisible() and oben <= unten, f"{oben} / {unten}")
    w.maskenrand.schliessen(); app.processEvents()
    check("… Maske zu: die Steuerung bleibt", st.isVisible())
    w.new_model(); app.processEvents()
    check("neues Modell ohne Ergebnis: die Steuerung verschwindet", not st.isVisible())


def test_nach_f5_ribbon_ergebnisse():
    w, app = _fenster()
    w.load_example("hall"); app.processEvents()
    w.register_zeigen("Geometrie")
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an); app.processEvents()
    t = w.ribbon.tabs.tabText(w.ribbon.tabs.currentIndex())
    check("nach der Rechnung steht das Ribbon auf „Ergebnisse“", t == "Ergebnisse", t)


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung (25.09.2026)
# --------------------------------------------------------------------------
def _lage_soll(w):
    """Die Knotenlage der gezeichneten Figur, unabhaengig nachgerechnet."""
    u = np.asarray(w._bild_figur[1], float)
    s = float(w._ueberhoehung_faktor)
    return np.asarray(w.model.nodes, float) + s * u[:, :3], s


class _Mitschnitt:
    """Eine Funktion in viewport ersetzen und ihre Schluesselwort-Argumente
    mitschreiben - fuer Zeichenwege ohne pruefbaren Darsteller am
    Hallenrahmen (feste Lager bewegen sich nicht, Netzknoten gibt es nicht)."""

    def __init__(self, name):
        from statik3d.gui import viewport as vp
        self.vp, self.name, self.alt, self.aufrufe = vp, name, getattr(vp, name), []

    def __enter__(self):
        def ersatz(*a, **k):
            self.aufrufe.append(k)
            return self.alt(*a, **k)
        setattr(self.vp, self.name, ersatz)
        return self

    def __exit__(self, *_a):
        setattr(self.vp, self.name, self.alt)


def _auf_lage(P, lage) -> bool:
    """Liegt jeder Punkt von P auf einem Knoten der Lage?"""
    from scipy.spatial import cKDTree
    P = np.asarray(P, float)
    if not len(P):
        return False
    d, _j = cKDTree(np.asarray(lage, float)).query(P)
    return bool(np.all(d < 1e-9))


def test_zeichenwege_an_der_bildlage():
    """Gegenpruefung 25.09.2026: 14 Verhaltensaenderungen ohne Pruefung im
    Fenster. Hier je Zeichenweg die Lage, an der er zeichnet."""
    from statik3d.gui import viewport as vp
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    lage, s = _lage_soll(w)
    check("Ausgangslage: verformte Figur mit Faktor > 0", s > 0 and w._bildlage is not None, f"{s}")
    # Lager: die Lager der Halle sind fest und bewegen sich nicht - geprueft
    # wird, welche Lage das Fenster uebergibt
    with _Mitschnitt("add_supports") as ms:
        w.redraw(); app.processEvents()
    lg = ms.aufrufe[-1].get("lage") if ms.aufrufe else None
    check("Lagersymbole: das Fenster zeichnet sie an der verformten Lage",
          lg is not None and np.allclose(lg, lage, atol=1e-9), str(None if lg is None else len(lg)))
    # Netzknoten: dasselbe (die Halle hat keine)
    w.act_edges.setChecked(True); w.act_netzknoten.setChecked(True)
    with _Mitschnitt("add_netzknoten") as ms:
        w.redraw(); app.processEvents()
    lg = ms.aufrufe[-1].get("lage") if ms.aufrufe else None
    check("Netzknoten: an der verformten Lage", lg is not None and np.allclose(lg, lage, atol=1e-9))
    w.act_netzknoten.setChecked(False)
    # Werte im Bild: Lage und Einheiten
    w.act_werte_staebe.setChecked(True)
    with _Mitschnitt("ergebniswerte") as ms:
        w.redraw(); app.processEvents()
    k_ = ms.aufrufe[-1] if ms.aufrufe else {}
    check("Werte im Bild: an der verformten Lage", k_.get("lage") is not None
          and np.allclose(k_["lage"], lage, atol=1e-9))
    check("Werte im Bild: in der Einheiteneinstellung des Modells",
          k_.get("einheiten") is w._einheiten_modell())
    w.act_werte_staebe.setChecked(False)
    # Knotennummern
    w.act_nummern["Knoten"].setChecked(True); app.processEvents()
    a = _akteure(w).get("nummern:Knoten-points")
    check("Knotennummern an der verformten Lage", a is not None and _auf_lage(pv_punkte(a), lage)
          and not _auf_lage(pv_punkte(a), w.model.nodes), "kein Darsteller" if a is None else "")
    w.act_nummern["Knoten"].setChecked(False); app.processEvents()
    # Sonde: ein Knoten, dessen verformte Lage einem anderen Modellknoten
    # naeher liegt als dem eigenen - der Klick muss ihn trotzdem treffen
    from scipy.spatial import cKDTree
    # mit grossem Faktor: am Hallenrahmen liegt sonst jeder verformte
    # Knoten noch seinem eigenen Modellknoten am naechsten
    w.ueberhoehung_setzen("fest", 20.0 * s); app.processEvents()
    lage, _s = _lage_soll(w)
    _d, naechst = cKDTree(np.asarray(w.model.nodes, float)).query(lage)
    kand = [i for i in vp.konstruktionsknoten(w.model) if int(naechst[i]) != int(i)]
    check("Prüfknoten für die Sonde gefunden (verformt näher an einem anderen Knoten)", bool(kand))
    if kand:
        k = int(kand[0])
        fang = w._fangpunkt
        w._fangpunkt = lambda: (None, "", None)
        w.sonden = []
        try:
            w._sonde_setzen(lage[k])
        finally:
            w._fangpunkt = fang
        app.processEvents()
        check("Sonde am verformt gezeichneten Knoten gesetzt (nicht am Modellknoten daneben)",
              bool(w.sonden) and int(w.sonden[-1]["knoten"]) == k,
              f"{w.sonden[-1]['knoten'] if w.sonden else None} / {k}")
        a = _akteure(w).get("sonden-points")
        check("… und an der verformten Lage gezeichnet",
              a is not None and np.allclose(pv_punkte(a)[0], lage[k], atol=1e-9))
        w.sonden = []
    w.ueberhoehung_setzen("auto"); app.processEvents()
    lage, _s = _lage_soll(w)
    # Auswahl eines Stabs: die orange Linie liegt auf der verformten Figur
    stab = max(w.model.members, key=lambda n: float(np.max(np.abs(np.asarray(
        w._bild_figur[1])[[int(x) for e in w.model.members[n].elements
                           for x in w.model.elements[e].nodes], :3]))))
    w.sel_staebe = {stab}; w.redraw(); app.processEvents()
    a = _akteure(w).get("auswahl")
    check(f"gewählter Stab {stab}: die Hervorhebung liegt auf der verformten Figur",
          a is not None and _auf_lage(pv_punkte(a), lage) and not _auf_lage(pv_punkte(a), w.model.nodes))
    w.sel_staebe = set(); w.redraw(); app.processEvents()


def test_umriss_marke_verlauf_sichtbar():
    import pyvista as pv
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    w.cb_undeformed.setChecked(True); app.processEvents()
    mit = any(k.startswith("undeformed_") for k in _akteure(w))
    w.btn_ueberhoehung["aus"].click(); app.processEvents()
    ohne = not any(k.startswith("undeformed_") for k in _akteure(w))
    check("Überhöhung aus: kein Umriss des unverformten Systems (läge auf der Figur)",
          mit and ohne, f"mit auto {mit}, bei aus weg {ohne}")
    w.btn_ueberhoehung["auto"].click(); app.processEvents()
    # Max-Marke nur in sichtbaren Teilen: den Knoten des Groesstwerts mit
    # allen seinen Elementen ausblenden
    from statik3d.gui import viewport as vp
    ps, _c, _n = vp.result_field(w.model, an.envelopes["ULS"], "|u| Verschiebung")
    k = int(np.nanargmax(ps))
    weg = {i for i, e in enumerate(w.model.elements) if k in [int(n) for n in e.nodes]}
    w.verborgen["elemente"] = set(weg); w.redraw(); app.processEvents()
    lage, _s = _lage_soll(w)
    sicht = w._sichtbare_knoten()
    a = _akteure(w).get("marke_max-points")
    P = np.asarray(_daten(a).GetPoints().GetPoint(0)) if a is not None else None
    check("Max-Marke bei ausgeblendetem Größtwert-Knoten: an einem sichtbaren Knoten",
          P is not None and sicht is not None and k not in set(int(i) for i in sicht)
          and _auf_lage([P], lage[np.asarray(sorted(sicht), int)]),
          f"Knoten {k} ausgeblendet, Marke bei {P}")
    w.verborgen["elemente"] = set(); w.redraw(); app.processEvents()
    # Verlauf nur an sichtbaren Staeben
    _waehle(w, app, ("combo", "GZT4"))
    stab = next(iter(w.model.members))
    weg = {int(e) for e in w.model.members[stab].elements}
    w.verborgen["elemente"] = set(weg)
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    a = _akteure(w).get("diagram")
    el = set(int(x) for x in np.asarray(pv.wrap(_daten(a)).point_data["elem"])) if a is not None else None
    check(f"Stab {stab} ausgeblendet: sein Verlauf fehlt, die anderen sind da",
          el is not None and not (el & weg) and len(el) > 0, f"{None if el is None else len(el)} Elemente")
    w.verborgen["elemente"] = set()
    w.cb_diagram.setCurrentText("kein Verlauf"); app.processEvents()


def test_bildtext_kopfzeile():
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    kz = " ".join(w._kopfzeile_zeilen)
    check("Kopfzeile: „Färbung Verschiebung u gesamt“, kein „|u|“",
          "Färbung Verschiebung u gesamt" in kz and "|u|" not in kz, kz[:160])


def test_breite_mit_langer_kombination():
    """Gegenpruefung 25.09.2026 (hoch): die Auswahl „Ergebnis“ machte den
    rechten Bereich so breit wie ihren laengsten Eintrag - mit einer
    Kombination aus 8 Lastfaellen 993 px, die Ansicht bei 1366 x 768 139 px,
    jede Maske liess das Fenster wachsen."""
    w, app = _fenster()
    w.resize(1366, 768)
    for _ in range(4):
        app.processEvents()
    w.load_example("hall"); app.processEvents()
    lang = ("1.35·Eigengewicht + 1.5·Schnee + 0.9·Wind links + 1.5·Nutzlast Bühne + "
            "1.5·Ausbaulast Dach + 1.5·Temperatur Sommer + 1.5·Anprall Stapler + 1.5·Kran")
    k0 = next(iter(w.model.combinations))
    w.model.combinations[k0].formula = lambda: lang
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an)
    for _ in range(6):
        app.processEvents()
    ansicht = w.maskenrand.ansicht
    texte = [w.cb_result.itemText(i) for i in range(w.cb_result.count())]
    check("die lange Kombination steht in der Auswahl", any(lang in t for t in texte))
    check("die Auswahl „Ergebnis“ verlangt höchstens die Breite von 18 Zeichen",
          w.cb_result.minimumSizeHint().width() < 300, f"{w.cb_result.minimumSizeHint().width()} px")
    werte = []
    for schritt in ("F5", "Knoten", "Netz", "Wind"):
        if w.maskenrand.offen():
            w.maskenrand.schliessen()
        w.resize(1366, 768)
        for _ in range(4):
            app.processEvents()
        if schritt == "Wind":
            w.maske_wind()
        elif schritt == "Knoten":
            w.maske_knoten()
        elif schritt == "Netz":
            w.maske_zeigen("Netz")
        for _ in range(6):
            app.processEvents()
        werte.append((schritt, w.eingaben_dock.width(), ansicht.visibleRegion().boundingRect().width(),
                      w.width(), w.height()))
    # Wind ist auch ohne Ergebnis breiter (Maske 1119 px Mindestbreite) -
    # geprueft wird, dass die Steuerung nichts dazu tut
    ok = all(r <= 480 and s >= 500 and b <= 1366 for n, r, s, b, _h in werte if n != "Wind")
    check("1366 x 768, lange Kombination: rechts ≤ 480 px, Ansicht ≥ 500 px, Fenster nicht breiter "
          "(F5, Knoten, Netz)",
          ok, "; ".join(f"{n}: rechts {r}, Ansicht {s}, Fenster {b}x{h}" for n, r, s, b, h in werte))
    check("… Wind: das Fenster wird nicht breiter", werte[-1][3] <= 1366, str(werte[-1]))
    # Die Hoehe: ohne die Aufteilung aus Paket 5 (rechter Bereich ueber die
    # ganze Hoehe) laesst jede Steuerung ueber einer Maske das Fenster bei
    # 1366 x 768 wachsen - der rechte Bereich ist dort schon ohne sie bis
    # auf 23 px voll. Die Pruefung gilt darum erst nach dem Zusammenfuehren.
    try:
        import statik3d.gui.fenster  # noqa: F401 - Paket 5
        mit_p5 = True
    except ImportError:
        mit_p5 = False
    if mit_p5:
        check("… mit Paket 5: keine der Masken lässt das Fenster höher werden",
              all(h <= 768 for _n, _r, _s, _b, h in werte), str(werte))
    else:
        print("     Höhe mit Masken: erst mit Paket 5 prüfbar (statik3d.gui.fenster fehlt) - "
              + "; ".join(f"{n} {h} px" for n, _r, _s, _b, h in werte))
    cb = w.cb_result
    i = next((j for j, t in enumerate(texte) if lang in t), -1)
    check("… die Aufklappliste ist breit genug für den ganzen Namen, der Tooltip nennt ihn",
          i >= 0 and cb.view().minimumWidth() >= min(cb.fontMetrics().horizontalAdvance(texte[i]),
                                                      cb.screen().availableGeometry().width() - 40)
          and cb.itemData(i, QtCore_ToolTipRole()) == texte[i],
          f"Liste {cb.view().minimumWidth()} px")
    if w.maskenrand.offen():
        w.maskenrand.schliessen()
    w.resize(1600, 1000)
    for _ in range(4):
        app.processEvents()


def QtCore_ToolTipRole():
    from PySide6 import QtCore
    return QtCore.Qt.ToolTipRole


def test_fensterhoehe_nach_f5():
    """Gegenpruefung 25.09.2026: die Steuerung (157 px) machte das Fenster
    nach F5 hoeher - bei 1366 x 768 85 px ueber dem Bildschirm. Ohne
    Paket 5 steht der rechte Bereich ueber dem unteren, jede Zeile der
    Steuerung hebt die Mindesthoehe des Fensters; darum hat sie nur drei
    Zeilen (Mindesthoehe mit Steuerung 704 px statt vorher 760 px).
    Ruecknahme: Steuerung wieder 157 px hoch."""
    w, app = _fenster()
    for groesse in ((1366, 768), (1280, 720)):
        w.new_model()
        for _ in range(4):
            app.processEvents()
        w.resize(*groesse)
        for _ in range(4):
            app.processEvents()
        w.load_example("hall"); app.processEvents()
        h0 = w.height()
        an = solver.solve_all(w.model, design=bool(w.model.members))
        w._solve_done("all", an)
        for _ in range(6):
            app.processEvents()
        check(f"nach F5 bei {groesse[0]} x {groesse[1]}: das Fenster bleibt so hoch (Steuerung sichtbar)",
              w.ergebnissteuerung.isVisible() and w.height() <= h0, f"{h0} -> {w.height()}")
    check("die Steuerung ist höchstens 110 px hoch (drei Zeilen)",
          w.ergebnissteuerung.height() <= 110, f"{w.ergebnissteuerung.height()} px")
    w.resize(1600, 1000)
    for _ in range(4):
        app.processEvents()


def test_werteskala_in_fester_einheit():
    """Gegenpruefung 25.09.2026 (mittel): die gespeicherten Grenzen galten
    nach dem Umstellen der Einheit in der neuen Einheit - 875 Ueberschreitungen
    verschwanden still, die Statuszeile nannte [MPa] vor einer Zahl in kN/cm²."""
    import re
    from statik3d import spannungen as spn
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    E = w.model.einheiten
    alt = E.verformung
    w.model.werteskala = spn.Werteskala()
    w.model.werteskala.modus = "grenze"
    w.model.werteskala.grenze = 50.0             # mm
    w._werteskala_anzeigen()

    def zaehlen():
        w.statusBar().clearMessage()
        w.redraw(); app.processEvents()
        t = w.statusBar().currentMessage()
        z = re.search(r"(\d+) Knoten über", t)
        return (int(z.group(1)) if z else 0), t
    try:
        n_mm, t_mm = zaehlen()
        E.verformung = "cm"
        w.einheiten_anwenden(); app.processEvents()
        n_cm, t_cm = zaehlen()
        check("Grenze 50 mm: in mm und nach Umstellen auf cm gleich viele Knoten darüber",
              n_mm > 0 and n_cm == n_mm, f"{n_mm} / {n_cm}")
        check("… die Statuszeile nennt die Einheit ihrer Zahlen („[cm]“, „über 5“)",
              "[cm]" in t_cm and re.search(r"über 5(\.0+)? ", t_cm) is not None
              and "[mm]" not in t_cm, t_cm)
        check("… das Feld Grenze zeigt die feste Einheit „mm“",
              w.ed_skala_grenze.suffix().strip() == "mm", w.ed_skala_grenze.suffix())
        kz = " ".join(w._kopfzeile_zeilen)
        check("… die Kopfzeile sagt „Skala bis 50 mm“", "Skala bis 50 mm" in kz, kz[:200])
    finally:
        E.verformung = alt
        w.model.werteskala = spn.Werteskala()
        w._werteskala_anzeigen()
        w.einheiten_anwenden(); app.processEvents()


def test_ueberhoehungsfeld_nachbesserung():
    from PySide6 import QtCore
    from PySide6.QtTest import QTest
    w, app, an = _halle()
    _waehle(w, app, ("env", "ULS"))
    ed = w.ed_ueberhoehung
    w.btn_ueberhoehung["auto"].click(); app.processEvents()
    # getippter Rest ohne Enter, dann ein Knopf
    ed.setFocus(); app.processEvents()
    ed.setText("250"); ed.setModified(True)
    w.btn_ueberhoehung["1:1"].click(); app.processEvents()
    check("„250“ getippt ohne Enter, dann Knopf 1:1: Faktor 1, das Feld zeigt 1",
          w._ueberhoehung_faktor == 1.0 and ed.text() == "1", f"{w._ueberhoehung_faktor} „{ed.text()}“")
    ed.editingFinished.emit(); ed.clearFocus(); app.processEvents()
    check("… das Feld verlassen: es bleibt bei 1:1 (kein fester Faktor 250)",
          w._ueberhoehung_art == "1:1" and w._ueberhoehung_faktor == 1.0,
          f"{w._ueberhoehung_art} {w._ueberhoehung_faktor}")
    # Woerter tippen
    w.btn_ueberhoehung["auto"].click(); app.processEvents()
    ed.setFocus(); ed.selectAll()
    QTest.keyClicks(ed, "1:1")
    check("„1:1“ getippt steht als „1:1“ im Feld (nicht „11“)", ed.text() == "1:1", ed.text())
    QTest.keyClick(ed, QtCore.Qt.Key_Return); app.processEvents()
    check("… Enter: wahre Größe (Faktor 1), nicht Faktor 11",
          w._ueberhoehung_art == "1:1" and w._ueberhoehung_faktor == 1.0,
          f"{w._ueberhoehung_art} {w._ueberhoehung_faktor}")
    ed.selectAll(); QTest.keyClicks(ed, "aus"); QTest.keyClick(ed, QtCore.Qt.Key_Return)
    app.processEvents()
    check("„aus“ getippt und Enter: keine Verformung", w._ueberhoehung_art == "aus"
          and w._ueberhoehung_faktor == 0.0, f"{w._ueberhoehung_art}")
    ed.clearFocus()
    w.btn_ueberhoehung["auto"].click(); app.processEvents()
    # Verlauf: gezeichnet mit 0 - das Feld sagt es
    _waehle(w, app, ("combo", "GZT4"))
    w.cb_diagram.setCurrentText("My"); app.processEvents()
    check("Verlauf My: das Feld zeigt 0 und ist gesperrt (gezeichnet wird unverformt)",
          ed.text() == "0" and not ed.isEnabled() and w._ueberhoehung_faktor == 0.0,
          f"„{ed.text()}“ enabled={ed.isEnabled()}")
    w.cb_diagram.setCurrentText("kein Verlauf"); app.processEvents()
    check("kein Verlauf: das Feld ist wieder frei und zeigt den Faktor",
          ed.isEnabled() and ed.text() not in ("", "0") and w._ueberhoehung_faktor > 0, ed.text())


def test_tabfolge_steuerung_register():
    """Gegenpruefung 25.09.2026: von „aus“ sprang Tab in die 3D-Ansicht und
    blieb dort - das Register Ergebnisse darunter (Schnittgrößenverlauf,
    Werte am Verlauf, Max/Min-Marken) war per Tastatur nicht erreichbar."""
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtTest import QTest
    w, app, an = _halle()
    w.maske_zeigen("Ergebnisse"); app.processEvents()
    w.activateWindow(); app.processEvents()
    b = w.btn_ueberhoehung["aus"]
    b.setFocus(QtCore.Qt.TabFocusReason); app.processEvents()
    seite = w.tabs.currentWidget()
    weg = []
    erreicht = False
    for _ in range(25):
        fw = QtWidgets.QApplication.focusWidget() or b
        QTest.keyClick(fw, QtCore.Qt.Key_Tab); app.processEvents()
        fw = QtWidgets.QApplication.focusWidget()
        weg.append(type(fw).__name__ if fw is not None else "None")
        if fw is w.cb_diagram:
            erreicht = True
            break
    erstes = weg[0] if weg else ""
    check("Tab nach „aus“ führt ins Register Ergebnisse, weiter bis „Schnittgrößenverlauf“",
          erreicht and "QtInteractor" not in weg, " → ".join(weg[:12]))
    w.maske_knoten(); app.processEvents()
    w.maskenrand.schliessen(); app.processEvents()


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_bezeichnungen_ohne_verlierbare_zeichen, test_einheiten_der_legende,
              test_extremstellen_und_marken, test_lager_an_der_verformten_lage,
              test_bericht_nennt_den_faktor, test_marken_kleiner_werte,
              test_kennwerte_spannung_in_der_legendeneinheit,
              test_umhuellende_zwei_linien, test_skala_des_verlaufs_symmetrisch,
              test_max_min_marken, test_werte_am_verlauf, test_verlauf_am_unverformten_stab,
              test_knoten_und_auswahl_an_der_verformten_lage, test_legende_folgt_den_einheiten,
              test_ueberhoehung, test_ergebnissteuerung_oben_rechts, test_nach_f5_ribbon_ergebnisse,
              test_zeichenwege_an_der_bildlage, test_umriss_marke_verlauf_sichtbar,
              test_bildtext_kopfzeile, test_werteskala_in_fester_einheit,
              test_ueberhoehungsfeld_nachbesserung, test_tabfolge_steuerung_register,
              test_fensterhoehe_nach_f5, test_breite_mit_langer_kombination):
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
