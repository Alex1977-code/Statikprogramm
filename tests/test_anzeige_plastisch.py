"""
Anzeige der Volumenspannungen bei plastischer Rechnung: die Werte der
Integrationspunkte auf die Knoten (Entscheidung des Anwenders vom 13.10.2026,
Nachtrag zu Paket 2 des Plans Singularitaeten), und Magenta fuer die
netzabhaengigen Stellen.

Wortlaut des Anwenders: „bei einer plastischen Rechnung deshalb die Werte der
Integrationspunkte auf die Knoten übernehmen“ - das Verfahren von ANSYS bei
Plastizitaet (ERESX,NO): jeder Knoten eines Elements bekommt den
Spannungstensor des ihm naechstgelegenen Integrationspunkts dieses Elements,
bei gleich nahen ihren Mittelwert; danach wird je Knoten ueber die Elemente
gemittelt wie bisher. Bis zum 13.10.2026 stand an allen Knoten eines
Elements, das nicht fliesst, sein groesster Auswertepunkt - eine Ecke, also
eine Extrapolation; am Drehlager (LF1 Mittel) bis 14 599 N/mm2, wo die
Punkte desselben Elements 343 N/mm2 haben. Elastische Rechnungen bleiben
bitgleich.

Geprueft wird:

* ein einzelnes Element (tet10, hex20; keine Mittelung): jeder Knoten hat
  genau den Wert seines naechstgelegenen Integrationspunkts - die Punkte
  unabhaengig ueber plastizitaet.punktspannungen (eps_p = 0), die
  Zuordnung unabhaengig nachgebaut; fliessend aus den Punkten, die der
  Loeser ablegt;
* die Platte mit Loch (0,4 MN, harter Ring mit f_y = 3 000 N/mm2, der nicht
  fliesst, sonst S355): Feld, Vergleichsspannung, Skala und Kennwerte aus
  den Integrationspunkten; das bisherige Maximum sass an einer Ecke nicht
  fliessender Elemente;
* eine Ergebnisdatei ohne abgelegte Punkte (vor dem 13.10.2026): fliessende
  Elemente zeigen ihren Elementwert, und das Programm zaehlt sie;
* elastisch bitgleich; die Nachweise lesen, was sie vorher lasen;
* Magenta hebt sich von jeder Farbe der Ergebnisskala ab.

Aufruf:  python -m tests.test_anzeige_plastisch
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_anzeige_plastisch_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver, plastizitaet as pl  # noqa: E402
from statik3d import spannungen as spn  # noqa: E402
from statik3d.model import Model, Material  # noqa: E402

RESULTS = []
_FENSTER = {}


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


def _sv(S):
    return spn.volumen_werte(np.asarray(S, float).reshape(-1, 6), "sv")


# --------------------------------------------------------------------------
# Zuordnung, unabhaengig nachgebaut: naechster Punkt im Bezugselement
# --------------------------------------------------------------------------
KNOTEN = {
    "tet10": [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (.5, 0, 0), (.5, .5, 0), (0, .5, 0),
              (0, 0, .5), (.5, 0, .5), (0, .5, .5)],
    "hex8": [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],
}
KNOTEN["hex20"] = KNOTEN["hex8"] + [
    (0, -1, -1), (1, 0, -1), (0, 1, -1), (-1, 0, -1), (0, -1, 1), (1, 0, 1), (0, 1, 1), (-1, 0, 1),
    (-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]


def _gewichte(typ, xi):
    X = np.asarray(KNOTEN[typ], float)
    P = np.asarray(xi, float)
    if typ.startswith("tet"):        # Volumenkoordinaten: das Bezugselement ist symmetrisch
        X = np.column_stack([1 - X.sum(axis=1), X])
        P = np.column_stack([1 - P.sum(axis=1), P])
    d = np.linalg.norm(X[:, None, :] - P[None, :, :], axis=2)
    W = (np.abs(d - d.min(axis=1, keepdims=True)) < 1e-9).astype(float)
    return W / W.sum(axis=1, keepdims=True)


def _einzelelement(typ, fy, F):
    """Ein Element, die Unterseite (z = min) fest, auf die Oberseite F schraeg
    nach oben."""
    m = Model(f"Einzelelement {typ}")
    m.add_material(Material("St", 210e9, 0.3, 7850, fy=fy))
    X = np.asarray(KNOTEN[typ], float)
    X = 0.05 * (X + 1.0) if typ.startswith("hex") else 0.1 * X
    m.add_nodes(X)
    e = m.add_element(typ, list(range(len(X))), "St")
    unten = [k for k in range(len(X)) if abs(X[k, 2] - X[:, 2].min()) < 1e-12]
    oben = [k for k in range(len(X)) if abs(X[k, 2] - X[:, 2].max()) < 1e-12]
    for k in unten:
        m.fix(k, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for k in oben:
        m.load_node(k, Fx=F / len(oben), Fz=F / len(oben), case="LF1")
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=2, iterationen=40,
                                     toleranz=1e-4)
    an = solver.solve_all(m)
    return m, an.cases["LF1"], e


def test_einzelelement():
    for typ in ("tet10", "hex20"):
        m, r, e = _einzelelement(typ, fy=5000e6, F=2e5)
        fl = r.info.get("plastisch") or {}
        z = pl.Zustand()
        z.eps_p[e] = np.zeros((1, 6))
        xi, sig = pl.punktspannungen(m, np.asarray(r.u, float).ravel(), z)[e]
        W = _gewichte(typ, xi)
        soll = _sv(W @ np.asarray(sig, float)) / 1e6
        ist = np.asarray(spn.je_knoten(m, r, "volumen", "sv"), float)
        print(f"   {typ}: {len(xi)} Punkte; Knoten 0 erhält Punkt {int(np.argmax(W[0]))} "
              f"(σ_v {soll[0]:.3f} N/mm²), bisher Elementwert {_sv(r.solid_res[e])[0] / 1e6:.3f}; "
              f"Knotenwerte {np.round(ist[:4], 3).tolist()} …")
        check(f"{typ}, ein Element, elastisch geblieben: jeder Knoten hat genau den Wert seines nächsten Punkts",
              bool(r.info.get("plastizitaet")) and not fl and np.allclose(ist, soll, rtol=1e-12, atol=1e-9),
              f"größte Abweichung {np.max(np.abs(ist - soll)):.9f} N/mm²")
        if typ == "tet10":
            L = np.column_stack([1 - np.sum(xi, axis=1), xi])
            check("… tet10: jede Ecke nimmt den Punkt mit ihrer Volumenkoordinate 0,585, jede Kantenmitte "
                  "das Mittel der Punkte ihrer beiden Ecken",
                  all(int(np.argmax(W[k])) == int(np.argmax(L[:, k])) for k in range(4))
                  and all(np.count_nonzero(W[k]) == 2 and np.allclose(W[k][W[k] > 0], 0.5) for k in range(4, 10)),
                  str(np.round(W, 2).tolist()))
    # fliessend: die Punkte, die der Loeser ablegt
    m, r, e = _einzelelement("tet10", fy=355e6, F=2.5e6)
    fl = r.info.get("plastisch") or {}
    abl = r.info.get("ip_spannungen") or {}
    S = None
    for ids, werte in abl.values():
        ids = list(np.asarray(ids).tolist())
        if e in ids:
            S = np.asarray(werte)[ids.index(e)]
    ok = e in fl and S is not None
    ok_abl = False
    if ok:
        from statik3d.elements import solid as sl
        xi = sl.dehnungsoperator(m, "tet10", [e])[0].xi
        soll = _sv(_gewichte("tet10", xi) @ S) / 1e6
        ist = np.asarray(spn.je_knoten(m, r, "volumen", "sv"), float)
        ok = np.allclose(ist, soll, rtol=1e-12, atol=1e-9)
        # die abgelegten Punkte sind die des Elementwerts: sein groesster Punkt
        ok_abl = abs(float(_sv(r.solid_res[e])[0]) - float(_sv(S).max())) <= 1e-6 * float(_sv(S).max())
        print(f"   tet10 fließend: ε_p {fl.get(e, 0) * 100:.2f} %, Knotenwerte {np.round(ist[:4], 1).tolist()} …")
    check("tet10, ein Element, fließend: Knoten aus den abgelegten Punkten des Lösers", ok,
          f"fließt {e in fl}, abgelegt {S is not None}")
    check("… die abgelegten Punkte passen zum Elementwert (dessen größter Punkt)", ok_abl)


# --------------------------------------------------------------------------
# Platte mit Loch
# --------------------------------------------------------------------------
def _platte(plastisch: bool):
    from tests.test_spitzenstellen import lochplatte
    from tests.test_fugen import _RING_A
    m, _ids, _mitte = lochplatte(vorspannung=0.4e6)
    m.add_material(Material("Hart", 210e9, 0.3, 7850, fy=3000e6))
    for e in m.elements:
        if e.typ == "hex8":
            rho = np.linalg.norm(np.asarray(m.nodes[e.nodes], float)[:, :2], axis=1).max()
            if rho <= _RING_A + 0.0125:
                e.mat = "Hart"
    if plastisch:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=2, iterationen=40,
                                         toleranz=1e-4)
    an = solver.solve_all(m)
    return m, an


def _soll_feld(m, r, hexa):
    """Knotenmittel der naechsten Punkte: nicht fliessende aus
    plastizitaet.punktspannungen (eps_p = 0), fliessende aus den abgelegten
    Punkten des Loesers."""
    fl = set(int(i) for i in (r.info.get("plastisch") or {}))
    z = pl.Zustand()
    for i in hexa:
        if i not in fl:
            z.eps_p[i] = np.zeros((1, 6))
    pkt = pl.punktspannungen(m, np.asarray(r.u, float).ravel(), z)
    xi0 = next(x for x, _s in pkt.values() if x is not None)
    for ids, S in (r.info.get("ip_spannungen") or {}).values():
        for i, s in zip(np.asarray(ids).tolist(), np.asarray(S)):
            pkt[int(i)] = (None, s)
    W = _gewichte("hex8", xi0)
    kn, w = [], []
    for i in hexa:
        v = _sv(W @ np.asarray(pkt[i][1], float)) / 1e6
        kn.extend(int(n) for n in m.elements[i].nodes)
        w.extend(v.tolist())
    return spn.knotenmittel(m.nn, kn, w)


def _feld_alt(m, r):
    """je_knoten nach dem Wortlaut bis zum 13.10.2026 (Elementwert an allen Knoten)."""
    from statik3d import elemente as EL
    ids = [i for i in r.solid_res if m.elements[i].typ in set(EL.VOLUMEN_TYPEN)]
    v = _sv([r.solid_res[i] for i in ids]) * spn.MPA
    kn, w = [], []
    for i, x in zip(ids, v):
        kn.extend(int(n) for n in m.elements[i].nodes)
        w.extend([float(x)] * len(m.elements[i].nodes))
    return spn.knotenmittel(m.nn, kn, w)


def _skala(w):
    bars = list(w.plotter.scalar_bars.values())
    return tuple(bars[0].GetLookupTable().GetRange()) if bars else None


def _zeigen(w, app, m, an):
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    for k in range(w.cb_result.count()):
        d = w.cb_result.itemData(k)
        if d and d[0] == "case" and d[1] == "LF1":
            w.cb_result.setCurrentIndex(k)
    w.cb_field.setCurrentIndex(w.cb_field.findText(spn.feldname("volumen", "sv")))
    app.processEvents()
    w.redraw()
    app.processEvents()


def test_plastisch(platte_pl):
    m, an = platte_pl
    r = an.cases["LF1"]
    hexa = [i for i, e in enumerate(m.elements) if e.typ == "hex8"]
    fl = set(int(i) for i in (r.info.get("plastisch") or {}))
    check("Platte: plastisch gerechnet, ein Teil fließt, der harte Ring nicht; Punkte abgelegt",
          bool(r.info.get("plastizitaet")) and 0 < len(fl) < len(hexa)
          and not any(m.elements[i].mat == "Hart" for i in fl) and bool(r.info.get("ip_spannungen")),
          f"{len(fl)} von {len(hexa)} fließen")
    soll = _soll_feld(m, r, hexa)
    alt = _feld_alt(m, r)
    ist = np.asarray(spn.je_knoten(m, r, "volumen", "sv"), float)
    ka, ks = int(np.nanargmax(alt)), int(np.nanargmax(soll))
    an_alt = [i for i in hexa if ka in m.elements[i].nodes]
    print(f"   bisher (Elementwert) max {alt[ka]:.1f} N/mm² am Knoten {ka}, nächste Punkte max {soll[ks]:.1f} "
          f"am Knoten {ks}, Anzeige max {np.nanmax(ist):.1f}")
    check("plastisch: das Feld sind die nächsten Integrationspunkte, gemittelt je Knoten",
          np.allclose(ist, soll, rtol=1e-10, atol=1e-9, equal_nan=True),
          f"größte Abweichung {np.nanmax(np.abs(ist - soll)):.6f} N/mm²")
    check("… das bisherige Maximum saß an einer Ecke nicht fließender Elemente und ist größer",
          alt[ka] > soll[ks] + 1.0 and not any(i in fl for i in an_alt),
          f"{alt[ka]:.1f} > {soll[ks]:.1f}; Elemente am Knoten fließen: {[i in fl for i in an_alt]}")
    nv = np.asarray(r.node_vm, float) / 1e6
    kn = sorted({int(n) for i in hexa for n in m.elements[i].nodes})
    check("… Vergleichsspannung (Zusammenfassung, Bericht) an den Knoten der Platte ebenso",
          np.allclose(nv[kn], soll[kn], rtol=1e-10, atol=1e-9), f"max {np.nanmax(nv[kn]):.1f}")
    check("… alle fließenden Elemente aus abgelegten Punkten (kein Rückfall)", spn.anzeige_rueckfall(m, r) == 0)
    w, app = _fenster()
    _zeigen(w, app, m, an)
    sk = _skala(w)
    check("Skala: ihr Maximum aus den Integrationspunkten, nicht aus der Ecke",
          sk is not None and abs(sk[1] - soll[ks]) <= 1e-9 * soll[ks], f"{sk}")
    kw = " ".join(getattr(w, "_kennwerte_zeilen", []) or [])
    check("… die Kennwerte ebenso", f"max {spn.dezimal(soll[ks])}" in kw, kw[:150])


def test_alte_datei(platte_pl):
    """Ohne abgelegte Punkte (Ergebnisdatei von vor dem 13.10.2026): die
    fliessenden Elemente zeigen ihren Elementwert (den groessten Punkt) an
    allen Knoten - gezaehlt und gesagt; die nicht fliessenden ihre Punkte."""
    m, an = platte_pl
    from statik3d.solver import Results
    r0 = an.cases["LF1"]
    r = Results(model=m, name=r0.name, u=r0.u, solid_res=r0.solid_res,
                info={k: v for k, v in r0.info.items() if k != "ip_spannungen"})
    fl = set(int(i) for i in (r.info.get("plastisch") or {}))
    kw = spn.anzeige_knotenwerte(m, r, "sv")
    zeilen: dict = {}
    for k, v in zip(kw[0].tolist(), kw[1].tolist()):
        zeilen.setdefault(k, []).append(v)
    e = sorted(fl)[0]
    soll = float(_sv(r.solid_res[e])[0])
    ok = all(any(abs(v - soll) <= 1e-9 * soll for v in zeilen[int(n)]) for n in m.elements[e].nodes)
    check("alte Ergebnisdatei: fließende Elemente mit ihrem Elementwert, gezählt",
          spn.anzeige_rueckfall(m, r) == len(fl) and ok, f"{spn.anzeige_rueckfall(m, r)} von {len(fl)}")
    s = r.summary()
    check("… die Zusammenfassung sagt es",
          f"{len(fl)} fließende Elemente" in s and "Integrationspunkte" in s,
          " | ".join(z for z in s.splitlines() if "Anzeige" in z))


def test_elastisch(platte_el):
    m, an = platte_el
    r = an.cases["LF1"]
    check("elastisch: keine Knotenwerte aus Punkten, die Tabelle nimmt solid_res selbst",
          not r.info.get("plastizitaet") and spn.anzeige_knotenwerte(m, r, "sv") is None
          and spn.anzeige_tensoren(m, r) is r.solid_res)
    alt = _feld_alt(m, r)
    ist = np.asarray(spn.je_knoten(m, r, "volumen", "sv"), float)
    check("… das Feld ist bitgleich wie bisher", np.array_equal(ist, alt, equal_nan=True))
    kn, wv = [], []
    for i, d in r.beam_forces.items():
        for n in m.elements[i].nodes:
            kn.append(int(n))
            wv.append(float(d["sig_max"]))
    ids = list(r.solid_res)
    vm = spn.volumen_werte(np.array([r.solid_res[i] for i in ids], float), "sv")
    for i, v in zip(ids, vm):
        for n in m.elements[i].nodes:
            kn.append(int(n))
            wv.append(float(v))
    check("… node_vm bitgleich", np.array_equal(np.asarray(r.node_vm), spn.knotenmittel(m.nn, kn, wv),
                                                equal_nan=True))
    w, app = _fenster()
    _zeigen(w, app, m, an)
    sk = _skala(w)
    check("… die Skala wie bisher", sk is not None and sk[1] == float(np.nanmax(alt)),
          f"{sk} / {np.nanmax(alt):.4f}")


def test_nachweise_unveraendert(platte_pl):
    """Volumennachweis und Ermuedung lesen in der plastischen Rechnung, was
    sie vorher lasen - die geglaettete Eckspannung (solid_rand) -, nicht die
    Anzeige."""
    from statik3d.ec3 import volumen as vol
    m, an = platte_pl
    r = an.cases["LF1"]
    hexa = [i for i, e in enumerate(m.elements) if e.typ == "hex8"]
    werte = vol._elementspannungen(m, r, hexa)
    rand = r.solid_rand
    gleich = all(np.array_equal(np.asarray(s), np.asarray(rand[e][0])) for e, s, _p in werte if e in rand)
    sv_n = max(vol.vergleichsspannung(s) for _e, s, _p in werte) / 1e6
    sv_a = float(np.nanmax(spn.je_knoten(m, r, "volumen", "sv")))
    print(f"   Volumennachweis liest σ_v bis {sv_n:.1f} N/mm² (geglättete Ecke), die Anzeige bis {sv_a:.1f}")
    check("Volumennachweis: liest weiter die geglättete Eckspannung (solid_rand), nicht die Anzeige",
          gleich and len(werte) == len(hexa))


def _farben_der_ansicht():
    """Die Farben, die in der Ergebnisansicht etwas bedeuten, ausser der Tafel."""
    from statik3d.gui import viewport as vp
    from statik3d.gui.main import MainWindow
    return {"über der Skala": spn.FARBE_UEBER, "unter der Grenze": spn.FARBE_UNTER,
            "netzabhängig": vp.FARBE_SPITZE, "ohne Wert": vp.FARBE_OHNE_WERT,
            "Geist": MainWindow.GEIST_FARBE, "Geist-Kante": MainWindow.GEIST_KANTE,
            "unverformt Netz": "#c8c8c8", "unverformt Umriss": "#b0b0b0",
            "Kanten": vp.darstellung("Voll", True, True).get("edge_color", "#202020"),
            "Hintergrund": "#ffffff", "Kennwerte": "#203040",
            "Marke max": vp.FARBE_MARKE_MAX, "Marke min": vp.FARBE_MARKE_MIN}


def test_farbe():
    """Netzabhaengige Stellen seit dem 13.10.2026 (Bild des Anwenders: „Grau
    ist doppelt belegt (über Skala und netzabhängig). Bitte trennen“): grau
    schraffiert, Umrandung, Zeichen und Hinweis in demselben dunklen Grau -
    dem Grau, das bis dahin „über der Grenze“ hiess (#646464). Bis zum
    13.10.2026 waren sie Magenta."""
    from matplotlib import colormaps
    from matplotlib.colors import to_rgb
    from statik3d.gui import viewport as vp
    g = np.array(to_rgb(vp.FARBE_SPITZE))
    T = colormaps["turbo"](np.linspace(0.0, 1.0, 256))[:, :3]
    dE_T = np.linalg.norm(_lab(T) - _lab(g), axis=1)
    andere = {k: v for k, v in _farben_der_ansicht().items() if k != "netzabhängig"}
    dE = {k: float(np.linalg.norm(_lab(g) - _lab(np.array(to_rgb(v))))) for k, v in andere.items()}
    print(f"   netzabhängig {vp.FARBE_SPITZE}: dE zur Tafel min {dE_T.min():.1f}; "
          + ", ".join(f"{k} {v:.1f}" for k, v in dE.items()))

    def lum(c):
        c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        return float(0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2])
    kontrast = (1.0 + 0.05) / (lum(g) + 0.05)
    check("netzabhängig: ein neutrales dunkles Grau (#646464), nicht Magenta",
          g[0] == g[1] == g[2] and vp.FARBE_SPITZE.lower() == "#646464", vp.FARBE_SPITZE)
    check("… dE ≥ 25 zu jeder Farbe der Tafel und zu den übrigen Farben der Ansicht (außer Kanten ≥ 25)",
          dE_T.min() >= 25.0 and min(dE.values()) >= 25.0,
          f"Tafel {dE_T.min():.1f}, übrige {min(dE.values()):.1f} ({min(dE, key=dE.get)})")
    check("… als Schrift auf Weiß lesbar (Kontrast ≥ 4,5:1)", kontrast >= 4.5, f"{kontrast:.2f}:1")


def _lab(rgb):
    """CIE-Lab (D65) aus sRGB in [0, 1] - fuer den Farbabstand dE wie das Auge."""
    c = np.asarray(rgb, float)
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def test_farbe_ueber_grenze():
    """„Über der Skala“ ist seit dem 13.10.2026 (Bild des Anwenders) wieder
    Magenta, beschriftet „> Skalenmax“ im Skalenfeld und in der Kopfzeile.
    Vom zweiten Nachtrag bis dahin war es ein Grau (#646464), das jetzt die
    netzabhaengigen Stellen tragen; davor Magenta. Keine Farbe ist doppelt
    belegt: die Farben der Legende dE ≥ 15 zu jeder Farbe der Ansicht, die
    beiden mit neuer Bedeutung ≥ 25 zu allen und zur Tafel turbo."""
    from matplotlib import colormaps
    from matplotlib.colors import to_rgb
    from statik3d.gui import viewport as vp
    g = np.array(to_rgb(spn.FARBE_UEBER))
    T = colormaps["turbo"](np.linspace(0.0, 1.0, 256))[:, :3]
    farben = _farben_der_ansicht()
    andere = {k: v for k, v in farben.items() if k != "über der Skala"}
    dE_T = np.linalg.norm(_lab(T) - _lab(g), axis=1)
    dE = {k: float(np.linalg.norm(_lab(g) - _lab(np.array(to_rgb(v))))) for k, v in andere.items()}
    print(f"   über der Skala {spn.FARBE_UEBER}: dE zur Tafel min {dE_T.min():.1f}, zum unteren Ende "
          f"{dE_T[0]:.1f}; " + ", ".join(f"{k} {v:.1f}" for k, v in dE.items()))
    check("über der Skala: Magenta (#ff00ff)", spn.FARBE_UEBER.lower() == "#ff00ff", spn.FARBE_UEBER)
    check("… mit dE ≥ 25 zu jeder Farbe der Tafel und zu den übrigen Farben der Ansicht",
          dE_T.min() >= 25.0 and min(dE.values()) >= 25.0,
          f"Tafel {dE_T.min():.1f}, übrige {min(dE.values()):.1f} ({min(dE, key=dE.get)})")
    # die Farben der Legende (Skalenfelder, Schraffur, ohne Wert) gegen alle;
    # die uebrigen Paare untereinander sind nicht Gegenstand (Befund 13.10.2026:
    # „ohne Wert“ #d0d4d8 und Geist-Kante #c9cfd5 liegen bei dE 2,3)
    legende = ("über der Skala", "unter der Grenze", "netzabhängig")
    paare = [(a, b, float(np.linalg.norm(_lab(np.array(to_rgb(farben[a]))) - _lab(np.array(to_rgb(farben[b]))))))
             for a in legende for b in farben if b != a]
    knapp = min(paare, key=lambda x: x[2])
    check("keine Farbe der Legende doppelt belegt: dE ≥ 15 zu jeder Farbe der Ansicht",
          knapp[2] >= 15.0, f"knappstes Paar {knapp[0]} / {knapp[1]}: {knapp[2]:.1f}")
    sk = spn.grenzen(spn.Werteskala(modus="grenze", grenze=355.0), np.array([100.0, 400.0]))
    check("… die Werteskala nimmt Magenta mit der Beschriftung „> Skalenmax“",
          sk["above_color"] == spn.FARBE_UEBER and sk["above_label"] == "> Skalenmax", str(sk["above_label"]))
    sk2 = vp.skala_umrechnen(sk, 0.1)
    check("… auch nach dem Umrechnen der Einheit", sk2["above_label"] == "> Skalenmax", str(sk2["above_label"]))
    w, app = _fenster()
    w.model.werteskala = spn.Werteskala(modus="grenze", grenze=355.0)
    text = w._werteskala_text()
    check("… Kopfzeile und Hinweis sagen „> Skalenmax“ magenta, nicht grau",
          "> Skalenmax" in text and "magenta" in text and "grau" not in text
          and "> Skalenmax" in w.cb_skala.toolTip() and "grau" not in w.cb_skala.toolTip(),
          f"{text!r} | {w.cb_skala.toolTip()[:80]!r}")


def main():
    platten = {}
    for k, plast in (("pl", True), ("el", False)):
        try:
            platten[k] = _platte(plast)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"Platte rechnen {k} (Ausnahme: {ex})", False))
    for t, k in ((test_einzelelement, None), (test_plastisch, "pl"), (test_alte_datei, "pl"),
                 (test_elastisch, "el"), (test_nachweise_unveraendert, "pl"), (test_farbe, None),
                 (test_farbe_ueber_grenze, None)):
        print(f"\n--- {t.__name__} ---")
        try:
            if k is None:
                t()
            elif k not in platten:
                RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
            else:
                t(platten[k])
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
