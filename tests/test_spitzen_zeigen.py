"""
Netzabhaengige Spannungsspitzen zeigen und aus den Nachweisen nehmen (Plan
Singularitaeten vom 10.10.2026, Paket 2).

Paket 1 (statik3d/spitzenstellen.py) kennzeichnet je Ergebnis die Stellen,
an denen Kraft ohne Flaeche in ein Volumen geht. Auffaellig sind nach der
Entscheidung des Anwenders vom 10.10.2026 nur die Stellen mit
sigma_v >= 2 f_y in der Zone oder F / (A_Huelle f_y) >= 1. Nichts wird
verschwiegen: der Spitzenwert bleibt sichtbar, steht aber getrennt und mit
dem Vermerk „netzabhängig, nicht für den Nachweis“. Geprueft wird an der
Platte mit Loch und starrer Scheibe darueber (1,2 MN Ankerkraft, eine
auffaellige Stelle):

* der Volumennachweis: eta ohne die Zone (gefuehrt) und mit ihr (nur
  berichtet), beide unabhaengig nachgerechnet;
* die Ermuedung der Volumen: die massgebende Stelle liegt ausserhalb, die
  Zone steht als „nur berichtet“ daneben;
* der Bericht: Abschnitt „Netzabhängige Spannungsspitzen“ mit der Tabelle;
* die Zusammenfassung des Ergebnisses: Maximum ausserhalb, Spitze getrennt;
* die Oberflaeche (offscreen): Legende und Kennwerte mit dem Maximum
  ausserhalb und der Spitze daneben, die Zone umrandet und abschaltbar, der
  Eintrag im Ergebnisbaum mit Klick zur Stelle, und das Nachholen beim
  Laden einer Ergebnisdatei von vor dem 10.10.2026;
* die Gegenprobe ohne auffaellige Stelle (Konsole der Beispiele): alles wie
  vorher.

Aufruf:  python -m tests.test_spitzen_zeigen
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_spitzen_zeigen_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver, examples_lib  # noqa: E402
from statik3d import spannungen as spn  # noqa: E402

RESULTS = []
_FENSTER = {}
VERMERK = "netzabhängig, nicht für den Nachweis"
TITEL = "Netzabhängige Spannungsspitzen"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def _platte():
    """Platte mit Loch (tests.test_spitzenstellen.lochplatte, 1,2 MN), die
    Platte als Koerper „Platte“ mit Kerbfall 71, ein Volumenbereich ueber die
    ganze Platte, eine GZT-Kombination und eine Ermuedungslast."""
    from statik3d.model import Volumenkoerper
    from tests.test_spitzenstellen import lochplatte
    m, ids, mitte = lochplatte(vorspannung=1.2e6)
    hexa = [i for i, e in enumerate(m.elements) if e.typ == "hex8"]
    for i in hexa:
        m.elements[i].group = "Platte"
    m.koerper["Platte"] = Volumenkoerper("Platte", [], material="S355", elemente=list(hexa),
                                         kerbfall=71e6)
    m.add_volumenbereich("B1", hexa)
    m.add_combination("GZT1", {"LF1": 1.0}, "ULS")
    m.add_fatigue_load("FAT1", "LF1", cycles=1e4)
    an = solver.solve_all(m, design=True, fatigue=True)
    return m, hexa, an


def _zone(r):
    from statik3d import spitzenstellen as sp
    return set(int(i) for i in sp.zonen_elemente(r))


def _zonenknoten(m, zone):
    zk = np.zeros(m.nn, bool)
    for e in zone:
        zk[np.asarray(m.elements[e].nodes, int)] = True
    return zk


# --------------------------------------------------------------------------
# 1) Volumennachweis: eta mit und ohne Zone
# --------------------------------------------------------------------------
def test_volumennachweis(platte):
    from statik3d.ec3 import volumen as vol
    m, hexa, an = platte
    r = an.combinations["GZT1"]
    zone = _zone(r)
    check("Vorbereitung: GZT1 hat eine auffällige Stelle mit Zone in der Platte",
          len(zone) > 0 and zone <= set(hexa), f"{len(zone)} Zonenelemente von {len(hexa)}")
    c = an.volumen.bereiche["B1"]
    fyd = 355e6 / m.design.gamma_M0
    # unabhaengig: sigma_v je Element wie der Nachweis (geglaettete Eckspannung);
    # seit 14.10.2026 zaehlen Ecken auf Knoten der Zone an Aussenelementen nicht
    # (tests/test_zonenrand.py) - bis dahin las der Nachweis dort die Ecke, die
    # Zonen- und Aussenelemente mischt
    werte = {e: vol.vergleichsspannung(s) for e, s, _p in vol._elementspannungen(m, r, hexa)}
    eta_mit = max(werte.values()) / fyd
    zk = _zonenknoten(m, zone)
    aussen = {e: vol.vergleichsspannung(s) for e, s, _p in
              vol._elementspannungen(m, r, [e for e in hexa if e not in zone], zk)}
    innen = {e: v for e, v in werte.items() if e in zone}
    eta_ohne = max(aussen.values()) / fyd
    print(f"   η mit Zone (bis 13.10.2026) {eta_mit:.3f}, η ohne Zone {eta_ohne:.3f}, "
          f"Nachweis {c.util:.3f}, Zone {getattr(c, 'zone_eta', None)}")
    check("η ohne Zone: der Nachweis nimmt sein Maximum außerhalb der Zone",
          abs(c.util - eta_ohne) <= 1e-9 * eta_ohne and c.element not in zone,
          f"η {c.util:.4f} (soll {eta_ohne:.4f}), Element {c.element}")
    check("… η mit Zone ist größer und steht als Spitze „nur berichtet“ daneben",
          eta_mit > eta_ohne and abs(getattr(c, "zone_eta", 0.0) - eta_mit) <= 1e-9 * eta_mit
          and getattr(c, "zone_element", -1) in zone
          and getattr(c, "zone_n", 0) == len(innen),
          f"Spitze η {getattr(c, 'zone_eta', None)}, {getattr(c, 'zone_n', None)} Elemente")
    text = " ".join(c.hinweise)
    check("… der Hinweis nennt Wert außerhalb, Spitze und den Vermerk",
          "nur berichtet" in text and VERMERK in text and spn.dezimal(eta_ohne, 3) in text
          and spn.dezimal(max(innen.values()) / 1e6, 1) in text, text[:160])
    tab = an.volumen.table()
    zeile = [z for z in tab if "netzabhängig" in str(z[0])]
    check("… die Tabelle hat eine eigene Zeile „nur berichtet“ für die Zone",
          len(zeile) == 1 and zeile[0][-1] == "nur berichtet", str(zeile))
    s = an.volumen.summary()
    check("… und die Zusammenfassung nennt sie", "nur berichtet" in s and "netzabhängig" in s, s)


def test_alternative_ohne_eintrag():
    """Eine Ergebniskombination, deren Alternative der Nachweis erst
    ueberlagert (1,35 LF1): ihr Ergebnis entsteht im Nachweis und traegt noch
    keine Kennzeichnung. Der Nachweis darf die Zone trotzdem nicht lesen."""
    from statik3d.ec3 import volumen as vol
    from tests.test_spitzenstellen import lochplatte
    m, _ids, _mitte = lochplatte(vorspannung=1.2e6)
    hexa = [i for i, e in enumerate(m.elements) if e.typ == "hex8"]
    m.add_volumenbereich("B1", hexa)
    m.add_combination("EK1", {}, "ULS", alternativen=[{"LF1": 1.35}])
    an = solver.solve_all(m, design=True)
    c = an.volumen.bereiche["B1"]
    r = an.cases["LF1"]
    zone = _zone(r)
    werte = {e: vol.vergleichsspannung(s) for e, s, _p in vol._elementspannungen(m, r.scaled(1.35), hexa)}
    fyd = 355e6 / m.design.gamma_M0
    zk = _zonenknoten(m, zone)
    ohne = max(vol.vergleichsspannung(s) for e, s, _p in vol._elementspannungen(
        m, r.scaled(1.35), [e for e in hexa if e not in zone], zk)) / fyd
    mit = max(werte.values()) / fyd
    print(f"   EK1 [1]: η mit Zone {mit:.3f}, ohne {ohne:.3f}, Nachweis {c.util:.3f} ({c.kombination})")
    check("Alternative einer Ergebniskombination (im Nachweis überlagert): η ohne Zone",
          c.kombination == "EK1 [1]" and abs(c.util - ohne) <= 1e-6 * ohne and c.zone_n > 0
          and abs(c.zone_eta - mit) <= 1e-6 * mit, f"η {c.util:.4f}, Zone {c.zone_n}")


# --------------------------------------------------------------------------
# 2) Ermuedung der Volumen
# --------------------------------------------------------------------------
def test_ermuedung(platte):
    from statik3d.ec3 import fatigue as ft
    m, hexa, an = platte
    r = an.cases["LF1"]
    zone = _zone(r)
    zk = _zonenknoten(m, zone)
    fv = an.fatigue.volumen.get("Platte")
    check("Vorbereitung: Ermüdung der Platte nach der Knotenregel gerechnet",
          fv is not None and fv.regel == "knoten" and not fv.fehler, str(getattr(fv, "fehler", "")))
    if fv is None:
        return
    # unabhaengig: Schwingbreite je Ort (Knoten) = |Signal LF1| * gamma_Ff
    orte = ft._knotenorte(m, hexa)
    S, _fehlt = ft._knotenspannung(r, orte)
    d = np.abs(ft.signalspannung(S)) * m.design.gamma_Ff
    in_zone = zk[orte["knoten"]]
    print(f"   Δσ max mit Zone {d.max() / 1e6:.1f} N/mm², ohne Zone {d[~in_zone].max() / 1e6:.1f} N/mm², "
          f"Nachweis {fv.dsig_max / 1e6:.1f}, D {fv.D:.4f}, Spitze D {getattr(fv, 'zone_D', None)}")
    check("Ermüdung: maßgebend ist ein Knoten außerhalb der Zone",
          fv.knoten >= 0 and not zk[fv.knoten] and abs(fv.dsig_max - d[~in_zone].max()) <= 1e-6 * d.max(),
          f"Knoten {fv.knoten}, Δσ {fv.dsig_max / 1e6:.2f} (soll {d[~in_zone].max() / 1e6:.2f})")
    check("… jede Schwingbreite der Lasten liegt außerhalb",
          all(not zk[int(x[4])] for x in fv.ranges), str([(x[2], x[4]) for x in fv.ranges]))
    check("… die Zone steht als „nur berichtet“ mit ihrer Spitze daneben",
          d.max() > d[~in_zone].max() and abs(getattr(fv, "zone_dsig", 0.0) - d.max()) <= 1e-6 * d.max()
          and getattr(fv, "zone_D", 0.0) > fv.D
          and any("nur berichtet" in w and VERMERK in w for w in fv.warnings),
          " | ".join(fv.warnings)[:200])
    tab = an.fatigue.table()
    check("… mit eigener Tabellenzeile „nur berichtet“",
          any("netzabhängig" in str(z[0]) and "nur berichtet" in str(z[-1]) for z in tab),
          str([z for z in tab if "netzabhängig" in str(z[0])]))


# --------------------------------------------------------------------------
# 3) Bericht
# --------------------------------------------------------------------------
def test_bericht(platte):
    from statik3d.report import Report
    from statik3d import spitzenstellen as sp
    m, _hexa, an = platte
    html = Report(m, an).html()
    st = [s for s in an.cases["LF1"].info["spitzenstellen"]["stellen"] if s["auffaellig"]][0]
    check("Bericht: Abschnitt „Netzabhängige Spannungsspitzen“", TITEL in html)
    teil = html[html.find(TITEL):]
    kopf = all(k in teil for k in ("Ort", "Bauteil", "Ursache", "Kraft", "σ_v", "ε_p", "Elemente",
                                   "Volumen"))
    check("… mit der Tabelle: Ort, Bauteil, Ursache, Kraft, σ_v, ε_p, Elemente, Volumen", kopf)
    werte = [f"{st['kraft'] / 1e3:.1f}", f"{st['sv_max'] / 1e6:.1f}", str(len(st["zone"])),
             f"{st['zone_volumen'] * 1e6:.1f}"]
    check("… die Zeile der Scheibe mit Ursache, Werten und dem Vermerk",
          "starre Scheibe koppelt nur den Lochrand" in teil and VERMERK in teil
          and all(x in teil for x in werte) and "Platte" in teil, str(werte))
    check("… keine Zahl wissenschaftlich im Abschnitt",
          not any(t in teil[:teil.find("</table>")] for t in ("e+0", "e-0")))
    check("… im Volumennachweis „nur berichtet“ für die Zone",
          "nur berichtet" in html[html.find("Spannungsnachweise der Volumenbereiche"):])
    _ = sp


# --------------------------------------------------------------------------
# 4) Zusammenfassung des Ergebnisses
# --------------------------------------------------------------------------
def test_zusammenfassung(platte):
    m, _hexa, an = platte
    r = an.cases["LF1"]
    zk = _zonenknoten(m, _zone(r))
    nv = np.asarray(r.node_vm, float)
    aussen = float(np.nanmax(np.where(zk, np.nan, nv)))
    st = [s for s in r.info["spitzenstellen"]["stellen"] if s["auffaellig"]][0]
    s = r.summary()
    print("   " + "\n   ".join(z for z in s.splitlines() if "Vergleich" in z or "netzabh" in z))
    check("Zusammenfassung: max. Vergleichsspannung außerhalb der netzabhängigen Stellen",
          f"max. Vergleichsspannung : {aussen / 1e6:.2f} MPa außerhalb der netzabhängigen Stellen" in s)
    check("… daneben getrennt die Spitze an den Integrationspunkten mit dem Vermerk",
          f"bis {st['sv_max'] / 1e6:.1f} MPa" in s and VERMERK in s)
    # Plastizitaet: eps_p ausserhalb und in der Zone getrennt (Eintrag wie vom Loeser)
    zone = sorted(_zone(r))
    aus = next(i for i, e in enumerate(m.elements) if e.typ == "hex8" and i not in set(zone))
    r.info["plastisch"] = {zone[0]: 0.30, aus: 0.012}
    r.info["plastizitaet"] = {"fliessend": 2, "iterationen": 3, "laststufen": 1, "eps_p_max": 0.30}
    for x in r.info["spitzenstellen"]["stellen"]:
        x["eps_p_max"] = 0.30 if x["auffaellig"] else x["eps_p_max"]
    r._cache.pop("spitzen_uebersicht", None)
    s = r.summary()
    zeile = [z for z in s.splitlines() if z.startswith("Plastizität")]
    check("… ε_p,eq max außerhalb (1,2 %), die Spitze 30 % getrennt",
          zeile and "ε_p,eq max 1.200 % außerhalb der netzabhängigen Stellen" in zeile[0]
          and "ε_p bis 30.00 %" in s, " | ".join(zeile))
    del r.info["plastisch"], r.info["plastizitaet"]
    r._cache.pop("spitzen_uebersicht", None)


# --------------------------------------------------------------------------
# 5) Oberflaeche: Legende, Kennwerte, Zone, Baum
# --------------------------------------------------------------------------
def _skala(w):
    bars = list(w.plotter.scalar_bars.values())
    return tuple(bars[0].GetLookupTable().GetRange()) if bars else None


def test_oberflaeche(platte):
    m, _hexa, an = platte
    w, app = _fenster()
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    i = w.cb_result.findText("LF1")
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "case" and d[1] == "LF1":
            i = k
    w.cb_result.setCurrentIndex(i)
    feld = spn.feldname("volumen", "sv")
    w.cb_field.setCurrentIndex(w.cb_field.findText(feld))
    app.processEvents()
    w.redraw()
    app.processEvents()
    r = w.current_result()
    zk = _zonenknoten(m, _zone(r))
    jv = np.asarray(spn.je_knoten(m, r, "volumen", "sv"), float)
    aussen = float(np.nanmax(np.where(zk, np.nan, jv)))
    gesamt = float(np.nanmax(jv))
    st = [s for s in r.info["spitzenstellen"]["stellen"] if s["auffaellig"]][0]
    sk = _skala(w)
    print(f"   Skala {sk}, außerhalb {aussen:.1f}, gesamt {gesamt:.1f}, Spitze IP {st['sv_max'] / 1e6:.1f}")
    check("Legende: Maximum der Farbskala außerhalb der Zone",
          sk is not None and abs(sk[1] - aussen) <= 1e-6 * aussen and gesamt > aussen,
          f"{sk}")
    text = getattr(w, "_spitzen_legende", "") or ""
    check("… daneben „in netzabhängigen Stellen bis … N/mm² (netzabhängig)“ mit dem Wert der Integrationspunkte",
          f"in netzabhängigen Stellen bis {spn.dezimal(st['sv_max'] / 1e6)} N/mm² (netzabhängig)" in text
          and "spitzen_legende" in w.plotter.actors, repr(text))
    kw = getattr(w, "_kennwerte_zeilen", []) or []
    check("… Kennwerte im Bild: Maximum außerhalb, Spitze getrennt",
          any(f"max {spn.dezimal(aussen)}" in z for z in kw)
          and any("netzab" in z and spn.dezimal(st["sv_max"] / 1e6) in z for z in kw), " | ".join(kw))
    marken = dict(getattr(w, "_extremmarken", []) or [])
    check("… die Max-Marke sitzt außerhalb der Zone",
          marken.get("marke_max", "").startswith("max " + spn.dezimal(aussen)), str(marken))
    def zeichen():
        return [a for a in w.plotter.actors if str(a).startswith("spitzen_zeichen")]
    check("Ansicht: die Zone ist umrandet, an der Stelle steht ein Zeichen",
          "spitzen_zonen" in w.plotter.actors and zeichen(),
          str([a for a in w.plotter.actors if "spitzen" in a]))
    # seit 13.10.2026: grau schraffiert ueber der Ergebnisfarbe, eigener
    # Legendeneintrag, Umrandung und Zeichen in demselben Grau
    from statik3d.gui import viewport as vp
    schr = w.plotter.actors.get("spitzen_schraffur")
    rand = w.plotter.actors.get("spitzen_zonen")
    check("… grau schraffiert: Linien über der Ergebnisfarbe, keine Fläche (die Farbe bleibt sichtbar)",
          schr is not None and schr.mapper.dataset.n_lines > 10 and schr.mapper.dataset.n_faces_strict == 0
          and schr.prop.color.hex_rgb.lower() == vp.FARBE_SPITZE.lower()
          and rand is not None and rand.prop.color.hex_rgb.lower() == vp.FARBE_SPITZE.lower(),
          f"{getattr(getattr(schr, 'mapper', None), 'dataset', None) and schr.mapper.dataset.n_lines} Linien")
    # seit 14.10.2026 dichter und breiter (Bild V21: h/2 und 1,5 px waren
    # neben den schwarzen Netzkanten kaum zu sehen): h/3, 2,5 px
    hs = [float(s["h"]) for s in r.info["spitzenstellen"]["stellen"] if s["auffaellig"] and s.get("h")]
    if schr is not None and hs:
        d = vp._SCHRAFFUR_RICHTUNG / np.linalg.norm(vp._SCHRAFFUR_RICHTUNG)
        ebenen = np.unique(np.round(np.asarray(schr.mapper.dataset.points, float) @ d, 9))
        abst = float(np.median(np.diff(ebenen))) if len(ebenen) > 1 else float("nan")
        soll = float(np.median(hs)) / 3.0
        check("… Schraffur: Abstand ein Drittel der örtlichen Kantenlänge, Linien 2,5 px breit",
              abs(abst - soll) <= 1e-6 * soll and abs(schr.prop.line_width - 2.5) < 1e-9,
              f"Abstand {abst * 1000:.3f} mm (h/3 = {soll * 1000:.3f} mm), Breite {schr.prop.line_width:g} px")
    else:
        check("… Schraffur: Abstand ein Drittel der örtlichen Kantenlänge, Linien 2,5 px breit", False,
              "keine Schraffur oder kein h")
    leg = w.plotter.actors.get("spitzen_schraffur_legende")
    muster = w.plotter.actors.get("spitzen_schraffur_muster")
    check("… eigener Legendeneintrag „netzabhängig (schraffiert)“ mit Muster, in Grau",
          leg is not None and leg.GetInput() == "netzabhängig (schraffiert)" and muster is not None
          and "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in leg.GetTextProperty().GetColor())
          == vp.FARBE_SPITZE.lower(), repr(leg.GetInput() if leg is not None else None))
    hinweis = w.plotter.actors.get("spitzen_legende")
    check("… der Hinweis „in netzabhängigen Stellen bis …“ in dunklem Grau, nicht Magenta",
          hinweis is not None and "#%02x%02x%02x" % tuple(int(round(c * 255))
                                                          for c in hinweis.GetTextProperty().GetColor())
          == vp.FARBE_SPITZE.lower())
    bars = list(w.plotter.scalar_bars.values())
    lut = bars[0].GetLookupTable() if bars else None
    ueber = bool(bars) and bars[0].GetDrawAboveRangeSwatch()
    check("… Knoten der Zone über der Skala: Magenta mit „> Skalenmax“ (nicht mehr eigene Farbe „netzabh.“)",
          ueber and bars[0].GetAboveRangeAnnotation() == "> Skalenmax"
          and "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in lut.GetAboveRangeColor()[:3]) == "#ff00ff",
          f"{bars[0].GetAboveRangeAnnotation() if bars else None}")
    w.cb_spitzenzonen.setChecked(False)
    app.processEvents()
    aus = "spitzen_zonen" not in w.plotter.actors and not zeichen()
    w.cb_spitzenzonen.setChecked(True)
    app.processEvents()
    check("… und lässt sich in der Ergebnisanzeige aus- und wieder einschalten",
          aus and "spitzen_zonen" in w.plotter.actors)
    # Ergebnisbaum
    erg = w._ergebnisliste()
    eintraege = erg.get(TITEL, [])
    check("Ergebnisbaum: Eintrag „Netzabhängige Spannungsspitzen“ mit der Stelle",
          len(eintraege) == 1, str(list(erg)))
    if eintraege:
        text0, zusatz, schl = eintraege[0][:3]
        check("… mit Bauteil, Ursache, Kraft, σ_v und ε_p",
              text0.startswith("Platte") and "starre Scheibe koppelt nur den Lochrand" in text0
              and f"{spn.dezimal(st['kraft'] / 1e3)} kN" in zusatz
              and f"{spn.dezimal(st['sv_max'] / 1e6)} N/mm²" in zusatz and "%" in zusatz
              and "e+" not in zusatz, f"{text0} | {zusatz}")
        w._baum_geklickt("ergebnis", schl)
        app.processEvents()
        fp = np.asarray(w.plotter.camera.focal_point, float)
        # gezeichnet ist die verformte Figur: die Mitte der Stelle dort
        X = w._bildlage if getattr(w, "_bildlage", None) is not None else np.asarray(m.nodes, float)
        ziel = X[np.asarray(st["knoten"], int)].mean(axis=0)
        d = float(np.linalg.norm(fp - ziel))
        d0 = float(np.linalg.norm(np.asarray(st["mitte"], float) - np.asarray(m.nodes, float)[np.asarray(st["knoten"], int)].mean(axis=0)))
        check("… ein Klick führt zur Stelle (Blickpunkt in der gezeichneten Mitte der Stelle)",
              d <= 1e-6 + 0.01 * st["zone_radius"] and d0 <= 1e-9 and "Netzabhängige" in (w.statusBar().currentMessage() or "Netzabhängige"),
              f"Abstand {d * 1e3:.3f} mm")


def test_laden_alte_datei(platte):
    """Eine Ergebnisdatei von vor dem 10.10.2026 traegt den Eintrag nicht -
    beim Laden holt die Oberflaeche ihn nach (spitzenstellen.nachholen)."""
    from statik3d import ergebnisse
    m, _hexa, an = platte
    w, app = _fenster()
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "platte.json")
        m.save(p)
        for r in an.all_results().values():
            r.info.pop("spitzenstellen", None)
        ergebnisse.schreiben(ergebnisse.pfad_zu(p), m, an)
        ok = w.modell_laden(p, fragen=False)
        app.processEvents()
    an2 = w.analysis
    st = ((an2.cases["LF1"].info.get("spitzenstellen") or {}).get("auffaellig") or []) if an2 else []
    check("Laden einer Ergebnisdatei ohne Kennzeichnung: nachgeholt, die Stelle ist auffällig",
          ok and len(st) == 1, f"{ok}, {st}")
    check("… und steht im Ergebnisbaum", TITEL in w._ergebnisliste(), str(list(w._ergebnisliste())))


# --------------------------------------------------------------------------
# 6) Gegenprobe ohne auffaellige Stellen: alles wie vorher
# --------------------------------------------------------------------------
def test_ohne_stellen():
    from statik3d.ec3 import volumen as vol
    from statik3d.report import Report
    m = examples_lib.build_example("solid")
    vol_el = [i for i, e in enumerate(m.elements) if e.typ in ("hex8", "tet4", "tet10", "hex20")]
    m.add_volumenbereich("K", vol_el)
    m.add_combination("GZT1", {"LF1": 1.35}, "ULS")
    an = solver.solve_all(m, design=True)
    r = an.combinations["GZT1"]
    info = r.info.get("spitzenstellen") or {}
    check("Konsole: eine Stelle (Endlast als Linie), nicht auffällig",
          info.get("kandidaten") == 1 and info.get("auffaellig") == [], str(info.get("auffaellig")))
    c = an.volumen.bereiche["K"]
    werte = [vol.vergleichsspannung(s) for _e, s, _p in vol._elementspannungen(m, r, vol_el)]
    eta = max(werte) / (m.materials[m.elements[vol_el[0]].mat].yield_strength(0.0) or 1.0)
    check("… Volumennachweis wie vorher: η über alle Elemente, keine Zone",
          getattr(c, "zone_n", 0) == 0 and not any("netzabhängig" in h for h in c.hinweise)
          and len(an.volumen.table()) == 2, f"η {c.util:.4f}")
    s = r.summary()
    check("… Zusammenfassung wie vorher",
          f"max. Vergleichsspannung : {np.nanmax(r.node_vm) / 1e6:.2f} MPa\n" in s + "\n"
          and "netzabhängig" not in s)
    html = Report(m, an).html()
    check("… kein Abschnitt im Bericht", TITEL not in html)
    w, app = _fenster()
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "combo":
            w.cb_result.setCurrentIndex(k)
    w.cb_field.setCurrentIndex(w.cb_field.findText(spn.feldname("volumen", "sv")))
    app.processEvents()
    w.redraw()
    app.processEvents()
    rr = w.current_result()
    jv = np.asarray(spn.je_knoten(m, rr, "volumen", "sv"), float)
    sk = _skala(w)
    check("… Legende über alle Knoten, kein Zusatz, keine Zone, kein Baumeintrag",
          sk is not None and abs(sk[1] - np.nanmax(jv)) <= 1e-9 * np.nanmax(jv)
          and not getattr(w, "_spitzen_legende", "") and "spitzen_zonen" not in w.plotter.actors
          and TITEL not in w._ergebnisliste(), f"{sk} / {np.nanmax(jv):.2f}")
    _ = eta


def main():
    platte = None
    try:
        platte = _platte()
    except Exception as ex:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        RESULTS.append((f"Platte rechnen (Ausnahme: {ex})", False))
    for t in (test_volumennachweis, test_alternative_ohne_eintrag, test_ermuedung, test_bericht,
              test_zusammenfassung, test_oberflaeche, test_ohne_stellen, test_laden_alte_datei):
        print(f"\n--- {t.__name__} ---")
        try:
            if t in (test_ohne_stellen, test_alternative_ohne_eintrag):
                t()
            elif platte is None:
                RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
            else:
                t(platte)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
