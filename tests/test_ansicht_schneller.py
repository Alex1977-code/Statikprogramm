"""
Ansicht schneller (10.11.2026): die am Drehlager Z3c gemessenen Bremsen beim
Laden, beim Auffrischen und beim Zeigen der Ergebnisse - ohne ein Ergebnis zu
aendern.

(a) Knoten- und Elementtabelle bauen ihre Zeilen erst beim Anzeigen
    (tabellen.Zeilenquelle): am Drehlager kosteten die Zeilen bei jedem
    Modellstand rund 18 von 22 s, waehrend beide Register hinten lagen.
(c) spannungen.je_knoten haelt das Feld je Ergebnis und Groesse: die Ansicht
    fragt dasselbe Feld fuer die Farben und fuer die Kennwerte.
(d) assemble.bindungen_halten: die Bindungen der Mittelknoten werden fuer
    alle Stapel der Integrationspunktwerte einmal bestimmt statt je Stapel.
(e) model.zylinderachsen_je_seite und Model._seitenmitte ohne np.cross bzw.
    ndarray.mean - bitgleich, beim Laden je rund eine Million Aufrufe.
(f) refresh_all rief refresh_lasteinleitungen zweimal hintereinander.
(g) Das FE-Netz wird in Voll und Transparent mit halb deckenden Kanten
    gezeichnet (viewport.NETZ_DECKUNG): mit voll deckenden Kanten war das
    Drehlager in der Gesamtansicht schwarz, vom Bauteil und von den
    Ergebnisfarben blieb nichts. Kantenfarbe, Hidden-Line und Drahtmodell
    bleiben, wie sie waren.

Jede Pruefung verlangt beides: den eingesparten Aufruf **und** dasselbe
Ergebnis. Am Stand davor (6383a8e) schlaegt jede fehl.

Aufruf:  python -m tests.test_ansicht_schneller
"""
import contextlib
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ansicht_schneller_"), "einstellungen.json")

from statik3d import assemble as asm                               # noqa: E402
from statik3d import elementwahl                                   # noqa: E402
from statik3d import model as modellmodul                          # noqa: E402
from statik3d import solver                                        # noqa: E402
from statik3d import spannungen as spn                             # noqa: E402
from tests.pruefkoerper import quader                              # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:<78} {detail}")


def versuch(name, fn):
    """Eine Pruefung, die auch dann zaehlt, wenn sie mit einer Ausnahme endet."""
    try:
        ok, detail = fn()
    except Exception as exc:                                       # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    check(name, ok, detail)


class Zaehler:
    """Huellt eine Funktion ein und zaehlt ihre Aufrufe."""

    def __init__(self, f):
        self.f, self.n = f, 0

    def __call__(self, *a, **k):
        self.n += 1
        return self.f(*a, **k)


@contextlib.contextmanager
def ersetzt(objekt, name, neu):
    alt = getattr(objekt, name)
    setattr(objekt, name, neu)
    try:
        yield
    finally:
        setattr(objekt, name, alt)


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.resize(1280, 860)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _kragarm(typ="hex8", nx=6, ny=2, nz=2):
    """Quader, bei x = 0 gehalten, am freien Ende eine Querlast."""
    m, ids = quader(typ, nx, ny, nz, 0.6, 0.1, 0.1)
    for j in range(ny + 1):
        for k in range(nz + 1):
            m.fix(ids[(0, j, k)], [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for j in range(ny + 1):
        for k in range(nz + 1):
            m.load_node(ids[(nx, j, k)], Fz=-1000.0, case="LF1")
    return m, ids


# --------------------------------------------------------------------------
# (a) Zeilenquelle
# --------------------------------------------------------------------------
def test_zeilenquelle():
    _app()
    from statik3d.gui import tabellen as tab

    def tabelle(ab):
        t = tab.Datentabelle([tab.Spalte("Nr", "", "ganz"), tab.Spalte("Wert", "m", "zahl", 2)], "Probe")
        t.VERZOEGERT_AB = ab
        return t

    roh = [[i, "1,5" if i % 2 else 0.25 * i] for i in range(10)]

    def verzoegert():
        bauen = Zaehler(lambda: [list(z) for z in roh])
        t = tabelle(5)
        t.setzen(tab.Zeilenquelle(10, bauen))
        vorher = (bauen.n, t.ausstehend(), t.zaehler()[0])
        geholt = t.nachholen()
        direkt = tabelle(10 ** 6)
        direkt.setzen([list(z) for z in roh])
        gleich = t.modell.zeilen == direkt.modell.zeilen and len(t.modell.zeilen) == 10
        ok = vorher == (0, True, 10) and geholt and bauen.n == 1 and gleich and not t.ausstehend()
        return ok, (f"vor dem Anzeigen {vorher[0]} Aufrufe, ausstehend {vorher[1]}, Zähler {vorher[2]}; "
                    f"danach {bauen.n} Aufruf, Zeilen gleich: {gleich}")

    versuch("a  nicht sichtbare große Tabelle: Zeilen erst beim Nachholen, einmal, gleich", verzoegert)

    def sofort():
        bauen = Zaehler(lambda: [list(z) for z in roh])
        t = tabelle(10 ** 6)
        t.setzen(tab.Zeilenquelle(10, bauen))
        direkt = tabelle(10 ** 6)
        direkt.setzen([list(z) for z in roh])
        gleich = t.modell.zeilen == direkt.modell.zeilen
        return bauen.n == 1 and not t.ausstehend() and gleich, f"{bauen.n} Aufruf, Zeilen gleich: {gleich}"

    versuch("a  kleine Tabelle: Zeilenquelle wird sofort und einmal gebaut", sofort)

    def laenge():
        q = tab.Zeilenquelle(7, lambda: [[1], [2], [3]])
        vor = (len(q), q.gebaut())
        erste = q[0]
        return vor == (7, False) and len(q) == 3 and q.gebaut() and erste == [1] and list(q) == [[1], [2], [3]], \
            f"vorher Länge {vor[0]}, nach dem Bauen {len(q)}"

    versuch("a  Zeilenquelle: Länge vorab aus der Angabe, danach aus den Zeilen", laenge)


def _soll_knotenzeilen(m):
    """Die Zeilen der Knotentabelle, unabhaengig nachgebaut (Schleife statt bincount)."""
    zahl = [0] * m.nn
    for e in m.elements:
        for k in e.nodes:
            if 0 <= int(k) < m.nn:
                zahl[int(k)] += 1
    lager = {}
    for i, sp in enumerate(m.supports):
        if int(sp.node) not in lager:
            lager[int(sp.node)] = sp.name or f"Lager {i + 1}"
    return [[i, float(m.nodes[i][0]), float(m.nodes[i][1]), float(m.nodes[i][2]), zahl[i], lager.get(i, "")]
            for i in range(m.nn)]


def test_modelltabellen():
    def lauf():
        w, app = _fenster()
        m, _ids = _kragarm()
        w._modell_setzen(m)
        app.processEvents()
        for t in (w.tbl_knoten, w.tbl_elem):
            t.VERZOEGERT_AB = 1
        sichtbar = [t.isVisible() for t in (w.tbl_knoten, w.tbl_elem)]
        if any(sichtbar):
            return False, f"Register Knoten/Elemente sind sichtbar ({sichtbar}) - die Prüfung braucht sie hinten"
        masse = Zaehler(w._elementmasse)
        with ersetzt(w, "_elementmasse", masse):
            w.refresh_modelltabellen()
            ohne = masse.n
            zaehler = (w.tbl_knoten.zaehler()[0], w.tbl_elem.zaehler()[0])
            aus = (w.tbl_knoten.ausstehend(), w.tbl_elem.ausstehend())
            w.tbl_knoten.nachholen()
            w.tbl_elem.nachholen()
            mit = masse.n
        soll_k = _soll_knotenzeilen(m)
        ist_k = [list(z) for z in w.tbl_knoten.modell.zeilen]
        ist_e = [list(z) for z in w.tbl_elem.modell.zeilen]
        vol = 0.6 * 0.1 * 0.1 / len(m.elements)
        elem_ok = (len(ist_e) == len(m.elements)
                   and all(z[0] == i and z[1] == "hex8" and z[3] == "S"
                           and z[2] == ", ".join(str(int(n)) for n in m.elements[i].nodes)
                           and abs(float(z[6]) - vol) < 1e-12 for i, z in enumerate(ist_e)))
        ok = (ohne == 0 and mit == 1 and aus == (True, True) and zaehler == (m.nn, len(m.elements))
              and ist_k == soll_k and elem_ok)
        return ok, (f"Elementmaße beim Auffrischen {ohne}-mal, nach dem Anzeigen {mit}-mal; "
                    f"Zähler {zaehler}; Knotenzeilen gleich: {ist_k == soll_k}; Elementzeilen: {elem_ok}")

    versuch("a  Auffrischen baut keine Knoten-/Elementzeilen; beim Anzeigen dieselben Zeilen", lauf)

    def mit_koerper():
        # Am Drehlager aufgefallen (10.11.2026): die Koerpertabelle braucht die
        # Elementmasse sofort - ohne sie scheiterte jedes Auffrischen eines
        # Modells mit vernetztem Volumenkoerper, und die Datei ging nicht auf.
        w, app = _fenster()
        m, _ids = _kragarm()
        m.koerper["K1"] = modellmodul.Volumenkoerper("K1", material="S", elemente=list(range(len(m.elements))))
        w._modell_setzen(m)
        app.processEvents()
        w.tbl_elem.VERZOEGERT_AB = 1
        if w.tbl_elem.isVisible():
            return False, "Register Elemente ist sichtbar - die Prüfung braucht es hinten"
        masse = Zaehler(w._elementmasse)
        with ersetzt(w, "_elementmasse", masse):
            w.refresh_modelltabellen()
            beim = masse.n
            w.tbl_elem.nachholen()
            danach = masse.n
        zeile = [list(z) for z in w.tbl_geokoerper.modell.zeilen if z[0] == "K1"]
        vol = float(zeile[0][5]) if zeile else float("nan")
        elem = float(sum(float(z[6]) for z in w.tbl_elem.modell.zeilen))
        ok = (beim == 1 and danach == 1 and len(zeile) == 1 and int(zeile[0][4]) == len(m.elements)
              and abs(vol - 0.006) < 1e-12 and abs(elem - 0.006) < 1e-12)
        return ok, (f"Elementmaße beim Auffrischen {beim}-mal, nach dem Anzeigen {danach}-mal; "
                    f"Volumen K1 {vol * 1000:.3f} dm³ (Soll 6.000), Summe Elementtabelle {elem * 1000:.3f} dm³")

    versuch("a  vernetzter Volumenkörper: Auffrischen gelingt, Volumen stimmt, Maße einmal", mit_koerper)

    def doppelt():
        w, app = _fenster()
        z = Zaehler(w.refresh_lasteinleitungen)
        with ersetzt(w, "refresh_lasteinleitungen", z):
            w.refresh_all()
            app.processEvents()
        return z.n == 1, f"{z.n} Aufruf(e) je refresh_all"

    versuch("f  refresh_all frischt die Lasteinleitungen einmal auf", doppelt)


# --------------------------------------------------------------------------
# (c) je_knoten einmal je Ergebnis
# --------------------------------------------------------------------------
def test_je_knoten():
    m, _ids = _kragarm()
    an = solver.solve_all(m)
    r = an.cases["LF1"]

    def einmal():
        r._cache.clear()
        mittel = Zaehler(spn.knotenmittel)
        with ersetzt(spn, "knotenmittel", mittel):
            a = spn.je_knoten(m, r, "volumen", "sv")
            b = spn.je_knoten(m, r, "volumen", "sv")
        frisch = spn._je_knoten(m, r, "volumen", "sv")
        gleich = np.array_equal(a, b) and np.array_equal(a, frisch) and float(np.max(a)) > 0
        return mittel.n == 1 and gleich, f"gerechnet {mittel.n}-mal bei zwei Abfragen, Werte gleich: {gleich}"

    versuch("c  dasselbe Feld zweimal gefragt: einmal gerechnet, Werte unverändert", einmal)

    def kopie():
        r._cache.clear()
        a = spn.je_knoten(m, r, "volumen", "sv")
        soll = a.copy()
        a[:] = -1.0
        b = spn.je_knoten(m, r, "volumen", "sv")
        halt = len(r._cache["je_knoten"])
        return np.array_equal(b, soll) and halt == 1, f"zweite Abfrage unberührt: {np.array_equal(b, soll)}"

    versuch("c  die Rückgabe ist eine Kopie: Ändern wirkt nicht auf die nächste Abfrage", kopie)

    def grenze():
        r._cache.clear()
        groessen = ["sv"] + [g for g in spn.VOLUMEN if g != "sv"][:spn.JE_KNOTEN_MERKEN + 1]
        felder = {}
        for g in groessen:
            felder[g] = spn.je_knoten(m, r, "volumen", g)
        halt = len(r._cache["je_knoten"])
        verschieden = not np.array_equal(felder["sv"], felder["sx"])
        mittel = Zaehler(spn.knotenmittel)
        with ersetzt(spn, "knotenmittel", mittel):
            wieder = spn.je_knoten(m, r, "volumen", "sv")        # das aelteste flog hinaus: neu gerechnet
        r._cache.clear()
        leer = "je_knoten" not in r._cache
        ok = (halt == spn.JE_KNOTEN_MERKEN and halt < len(groessen) and verschieden
              and mittel.n == 1 and np.array_equal(wieder, felder["sv"]) and leer)
        return ok, f"{len(groessen)} Größen gefragt, {halt} gehalten; andere Größe = anderes Feld: {verschieden}"

    versuch("c  höchstens JE_KNOTEN_MERKEN Felder je Ergebnis; Leeren des Zwischenspeichers wirkt", grenze)


# --------------------------------------------------------------------------
# (d) Bindungen der Mittelknoten ueber die Stapel halten
# --------------------------------------------------------------------------
def _gemischt():
    """Kragarm aus tet4, die Haelfte zu tet10 gewandelt: an der Grenze sind
    die Mittelknoten gebunden (mittelknoten_bindungen nicht leer)."""
    m, _ids = _kragarm("tet4", 4, 2, 2)
    for e in m.elements:
        e.group = "A" if float(np.mean([m.nodes[int(k)][0] for k in e.nodes])) < 0.3 else "B"
    elementwahl.tet4_zu_tet10(m, koerper={"A"})
    return m


@contextlib.contextmanager
def _ohne_halten(model):
    yield


def test_bindungen_halten():
    def lauf():
        m = _gemischt()
        bind = asm.mittelknoten_bindungen(m)
        an = solver.solve_all(m)
        r = an.cases["LF1"]
        elemente = [i for i, e in enumerate(m.elements) if e.typ == "tet10"]
        with ersetzt(spn, "IP_STAPEL", 2):
            schl = Zaehler(asm.netz_schluessel)
            with ersetzt(asm, "netz_schluessel", schl):
                mit = spn._ip_spannungen(m, r.u, elemente)
            gehalten = schl.n
            frei = getattr(m, "_mittelknoten_gehalten", "fehlt")
            schl2 = Zaehler(asm.netz_schluessel)
            with ersetzt(asm, "netz_schluessel", schl2), ersetzt(asm, "bindungen_halten", _ohne_halten):
                ohne = spn._ip_spannungen(m, r.u, elemente)
        gleich = (len(mit) == len(ohne) and len(mit) > 1
                  and all(np.array_equal(a[0], b[0]) and np.array_equal(a[2], b[2]) for a, b in zip(mit, ohne)))
        stapel = -(-len(elemente) // 2)
        ok = (len(bind) > 0 and gehalten <= 2 and schl2.n >= stapel and gleich and frei is None)
        return ok, (f"{len(bind)} Bindungen, {stapel} Stapel: Netzschlüssel {gehalten}-mal statt {schl2.n}-mal; "
                    f"Spannungen bitgleich: {gleich}; danach freigegeben: {frei is None}")

    versuch("d  Integrationspunktwerte in Stapeln: Bindungen einmal bestimmt, Werte bitgleich", lauf)

    def verschachtelt():
        m = _gemischt()
        with asm.bindungen_halten(m):
            aussen = m._mittelknoten_gehalten
            with asm.bindungen_halten(m):
                innen = m._mittelknoten_gehalten
            nach_innen = m._mittelknoten_gehalten
            wert = asm.mittelknoten_bindungen(m)
        ende = m._mittelknoten_gehalten
        ok = (aussen is not None and innen is aussen and nach_innen is aussen and wert is aussen and ende is None)
        return ok, f"innen derselbe Wert: {innen is aussen}; nach dem inneren Block weiter gehalten: {nach_innen is aussen}"

    versuch("d  verschachtelt bleibt der äußere Halt gültig; am Ende freigegeben", verschachtelt)

    def fehler():
        m = _gemischt()
        try:
            with asm.bindungen_halten(m):
                raise RuntimeError("Abbruch in der Auswertung")
        except RuntimeError:
            pass
        return m._mittelknoten_gehalten is None, "nach einer Ausnahme im Block freigegeben"

    versuch("d  auch nach einer Ausnahme ist der Halt aufgehoben", fehler)


# --------------------------------------------------------------------------
# (e) Kreuzprodukt und Seitenmitte
# --------------------------------------------------------------------------
class _Zaehlfeld(np.ndarray):
    """Knotenfeld, das die Aufrufe von mean zaehlt."""
    aufrufe = 0

    def mean(self, *a, **k):
        _Zaehlfeld.aufrufe += 1
        return np.asarray(self).mean(*a, **k)


def test_bitgleich():
    def kreuz():
        rng = np.random.default_rng(11)
        echt = np.cross
        zahl = Zaehler(echt)
        ungleich, n = 0, 0
        with ersetzt(np, "cross", zahl):
            for _ in range(4000):
                x = rng.normal(size=3)
                x /= np.linalg.norm(x)
                aus = modellmodul.zylinderachsen_je_seite(rng.normal(size=3) * 3.0, rng.normal(size=3), x)
                if aus is None:
                    continue
                n += 1
                if not np.array_equal(aus[1], echt(aus[0], aus[2])):
                    ungleich += 1
        return zahl.n == 0 and ungleich == 0 and n == 4000, \
            f"{n} Zufallslagen, davon {ungleich} nicht bitgleich zu np.cross; np.cross {zahl.n}-mal gerufen"

    versuch("e  zylinderachsen_je_seite: ohne np.cross, bitgleich zu np.cross", kreuz)

    def mitte():
        ungleich, n = 0, 0
        _Zaehlfeld.aufrufe = 0
        for typ in ("hex8", "tet4", "tet10", "pent6"):
            m, _ids = quader(typ, 3, 2, 2, 0.731, 0.213, 0.117, verzerrung=0.2)
            X = np.asarray(m.nodes, float).copy()
            m.nodes = X.view(_Zaehlfeld)
            for i, e in enumerate(m.elements):
                seiten = asm.SOLID_FACES[e.typ]
                for s in range(len(seiten)):
                    n += 1
                    soll = X[[int(e.nodes[j]) for j in seiten[s]]].mean(axis=0)
                    if not np.array_equal(np.asarray(m._seitenmitte(i, s)), soll):
                        ungleich += 1
        return _Zaehlfeld.aufrufe == 0 and ungleich == 0 and n > 500, \
            f"{n} Seiten, davon {ungleich} nicht bitgleich zu mean; mean {_Zaehlfeld.aufrufe}-mal gerufen"

    versuch("e  Model._seitenmitte: ohne ndarray.mean, bitgleich zu mean", mitte)


# --------------------------------------------------------------------------
# (g) FE-Netz mit halb deckenden Kanten
# --------------------------------------------------------------------------
def _kanten_im_fenster(w):
    """Deckung der sichtbaren Elementkanten je Darsteller des Modells."""
    werte = {}
    for name, a in dict(w.plotter.renderer.actors).items():
        if name.startswith(("model_", "result_")) and hasattr(a, "GetProperty"):
            p = a.GetProperty()
            if p.GetEdgeVisibility():
                werte[name] = round(float(p.GetEdgeOpacity()), 6)
    return werte


def test_netzdeckung():
    from statik3d.gui import viewport as vp

    def angaben():
        d = getattr(vp, "NETZ_DECKUNG", None)
        if d is None:
            return False, "viewport.NETZ_DECKUNG fehlt - die Kanten decken voll"
        voll, farbig = vp.darstellung("Voll", True), vp.darstellung("Voll", True, True)
        durch = vp.darstellung("Transparent", True)
        ok = (0.0 < d < 1.0
              and voll == {"show_edges": True, "edge_opacity": d} and farbig == voll
              and durch == {"opacity": 0.35, "show_edges": True, "edge_opacity": d}
              and vp.darstellung("Transparent", True, True) == {"opacity": 0.55, "show_edges": True,
                                                                "edge_opacity": d})
        return ok, f"Deckung {d}; Voll {voll}; Transparent {durch}"

    versuch("g  FE-Netz in Voll und Transparent: Kanten halb deckend, keine eigene Kantenfarbe", angaben)

    def unveraendert():
        ohne = (vp.darstellung("Voll", False), vp.darstellung("Transparent", False),
                vp.darstellung("Transparent", False, True))
        hl = vp.darstellung("Hidden-Line", True)
        hlf = vp.darstellung("Hidden-Line", False, True)
        draht = vp.darstellung("Drahtmodell", True)
        ok = (ohne == ({"show_edges": False}, {"opacity": 0.35, "show_edges": False},
                       {"opacity": 0.55, "show_edges": False})
              and hl == {"show_edges": True, "edge_color": "#202020", "line_width": 2, "lighting": False,
                         "color": "#ffffff"}
              and hlf == {"show_edges": True, "edge_color": "#202020", "line_width": 2, "lighting": False}
              and draht == {"style": "wireframe", "line_width": 2}
              and hasattr(vp, "NETZ_DECKUNG"))
        return ok, f"ohne Netz {ohne[0]}; Hidden-Line {hl}; Drahtmodell {draht}"

    versuch("g  ohne FE-Netz keine Kantenangabe; Hidden-Line und Drahtmodell unverändert", unveraendert)

    def fenster():
        w, app = _fenster()
        m, _ids = _kragarm()
        w._modell_setzen(m)
        w.act_edges.setChecked(True)
        w.darstellung_setzen("Voll")
        w.redraw()
        app.processEvents()
        voll = _kanten_im_fenster(w)
        w.darstellung_setzen("Hidden-Line")
        app.processEvents()
        hl = _kanten_im_fenster(w)
        w.darstellung_setzen("Voll")
        w.act_edges.setChecked(False)
        w.redraw()
        app.processEvents()
        ohne = _kanten_im_fenster(w)
        w.act_edges.setChecked(True)
        w.redraw()
        app.processEvents()
        d = getattr(vp, "NETZ_DECKUNG", None)
        ok = (d is not None and bool(voll) and all(abs(x - d) < 1e-6 for x in voll.values())
              and bool(hl) and all(abs(x - 1.0) < 1e-6 for x in hl.values()) and not ohne)
        return ok, f"Voll {voll}; Hidden-Line {hl}; ohne FE-Netz {ohne}"

    versuch("g  im Fenster: Kanten des Modells in Voll halb deckend, in Hidden-Line deckend", fenster)


def main():
    for t in (test_zeilenquelle, test_je_knoten, test_bindungen_halten, test_bitgleich, test_modelltabellen,
              test_netzdeckung):
        try:
            t()
        except Exception as exc:                                   # noqa: BLE001
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(exc).__name__}: {exc}")
    n = sum(RESULTS)
    print(f"Ergebnis: {n}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    kode = main()
    sys.stdout.flush()
    os._exit(kode)
