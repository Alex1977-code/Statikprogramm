"""
Paket Q7 des Nachtrags (07.10.2026): Namen und Nummern.

Grundsatz wie in P12 (Fehlerliste vom 06.10.2026): keine Eingabe geht still
verloren oder wird still umgedeutet; Ungueltiges wird als Hinweis abgewiesen,
das Modell bleibt, und es entsteht kein leerer Rueckgaengig-Schritt.

* N12  Komma und Semikolon im Namen eines Stabs, einer Linie, Flaeche, eines
       Volumens, Lagers oder Gelenks (die Namen, die in getippten Listen
       stehen): ``Model.objektname_konflikt``, aufgerufen von Masken, Tabellen,
       alten Dialogen, Umbenennen im Modell und Browser. Ein vorhandener Name
       bleibt, wie er ist.
* N13  Nummern ausserhalb des Bereichs (Elemente eines Stabs, angeschlossene
       Knoten eines starren Koerpers) werden mit dem Eintrag gemeldet, statt
       wegzufallen.
* N14  Profileditor: eine doppelte Knotennummer sperrt OK.
* N15  Importe ersetzen Komma und Semikolon in Lastfall- und
       Kombinationsnamen und nennen es im Protokoll.
* N16  DIN-19704-Praefix mit Komma: Abweisung statt Endlosschleife.
* N17  Zeichenfehler im Docstring von ``_zahlenliste``.

Aufruf:  python -m tests.test_nachtrag_q7
"""
import os
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_q7_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


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
    w._ungespeichert_fragen = lambda *a, **k: True
    w._fragen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w)
    _FENSTER.update(w=w, app=app)
    return w, app


def _undo_n(w):
    return len(getattr(w, "_undo", []) or [])


def _maske_zu(w, app):
    try:
        w._leiste_weg()
    except Exception:                       # noqa: BLE001
        pass
    if w.maskenrand.maske is not None:
        w._maske_verwerfen(w.maskenrand.maske)
    app.processEvents()


def _modell(w, app):
    """Rahmen mit Linien, Flaechen, Volumen, einem Stab, einem Gelenk und
    benannten Lagern - alles mit Namen ohne Trenner."""
    w.load_example("frame"); app.processEvents()
    m = w.model
    n0 = m.nn
    m.add_nodes(np.array([[20, 0, 0], [21, 0, 0], [21, 1, 0], [20, 1, 0.]]))
    for nm, (a, b) in {"Q1": (0, 1), "Q2": (1, 2), "Q3": (2, 3), "Q4": (3, 0)}.items():
        m.add_line(nm, [n0 + a, n0 + b])
    for k in range(1, 5):
        m.add_flaeche(f"FQ{k}", ["Q1", "Q2", "Q3", "Q4"], teilung=[4, 4])
    m.add_koerper("VQ", ["FQ1", "FQ2", "FQ3", "FQ4"], teilung=[2, 2, 2])
    m.add_member("S1", [0, 1])
    m.add_hinge("G1", end=1, phiy="free")
    m.supports[0].name = "Lager A"
    m.add_line_support([n0, n0 + 1], name="LL A")
    w.refresh_all(); app.processEvents()
    return m


def _gerufen(fn):
    """(Ergebnis, None) oder (None, Ausnahme) - eine fehlende Funktion im
    Ausgangsstand soll als FAIL der Pruefung erscheinen, nicht alles abbrechen."""
    try:
        return fn(), None
    except Exception as ex:                 # noqa: BLE001
        return None, ex


# --------------------------------------------------------------------------
# N12
# --------------------------------------------------------------------------
def test_n12_modell():
    from statik3d.model import Model, NameVergeben
    m = Model()
    for wort in ("Stab", "Linie", "Fläche", "Volumen", "Lager", "Gelenk"):
        for nm in ("S, 1", "S,1", "S;1", "S1;"):
            grund, ex = _gerufen(lambda: m.objektname_konflikt(nm, "", wort))
            check(f"{wort} „{nm}“: abgewiesen, der Grund nennt Komma oder Semikolon und das Wort",
                  ex is None and bool(grund) and ("Komma" in grund or "Semikolon" in grund) and wort in grund,
                  str(ex or grund))
    grund, ex = _gerufen(lambda: m.objektname_konflikt("S 1", "", "Stab"))
    check("ein Name ohne Trenner ist frei", ex is None and grund == "", str(ex or grund))
    grund, ex = _gerufen(lambda: m.objektname_konflikt("S, 1", "S, 1", "Stab"))
    check("ein vorhandener Name mit Komma bleibt, wie er ist (neu == alt)", ex is None and grund == "",
          str(ex or grund))
    grund, ex = _gerufen(lambda: m.objektname_konflikt("S, 1", "S 1", "Stab"))
    check("… ein anderer Name mit Komma beim Umbenennen wird abgewiesen", ex is None and bool(grund))
    grund, ex = _gerufen(lambda: m.objektname_konflikt("", "S1", "Stab"))
    check("ein leerer Name ist keine Sache dieser Pruefung (die Aufrufer fangen ihn vorher)",
          ex is None and grund == "", str(ex or grund))


def test_n12_umbenennen_im_modell():
    from statik3d.model import NameVergeben
    w, app = _fenster()
    m = _modell(w, app)
    for was, alt, neu, sammlung, rufen in (
            ("Stab", "S1", "S, 1", m.members, m.stab_umbenennen),
            ("Linie", "Q1", "Q, 1", m.lines, m.linie_umbenennen),
            ("Fläche", "FQ1", "F;1", m.flaechen, m.flaeche_umbenennen),
            ("Volumen", "VQ", "V, 1", m.koerper, m.koerper_umbenennen)):
        try:
            rufen(alt, neu)
            ok, text = False, "keine Ausnahme"
        except NameVergeben as ex:
            ok, text = alt in sammlung and neu not in sammlung, str(ex)
        except Exception as ex:             # noqa: BLE001
            ok, text = False, f"{type(ex).__name__}: {ex}"
        check(f"{was} {alt} -> „{neu}“: NameVergeben, der Name bleibt {alt}", ok, text)
    # ein vorhandener Name mit Komma darf weg vom Komma umbenannt werden
    m.add_member("S, 7", [2, 3])
    mit = m.stab_umbenennen("S, 7", "S7")
    check("ein Stab „S, 7“ (aus einer alten Datei) laesst sich in „S7“ umbenennen",
          "S7" in m.members and "S, 7" not in m.members, str(mit))


def test_n12_masken():
    w, app = _fenster()
    m = _modell(w, app)
    _maske_zu(w, app)
    fall = (
        ("stab", "S", {"name": "S, 2", "elemente": "4, 5", "kommentar": ""}, lambda: "S, 2" in m.members,
         "Stab"),
        ("linie", "L", {"name": "L, 9", "kn": "0 1", "kommentar": ""}, lambda: "L, 9" in m.lines, "Linie"),
        ("geoflaeche", "F", {"name": "F;9", "linien": "Q1, Q2, Q3, Q4", "teilung": "2 2", "kommentar": ""},
         lambda: "F;9" in m.flaechen, "Fläche"),
        ("geokoerper_einzeln", "V", {"name": "V, 9", "flaechen": "FQ1, FQ2, FQ3, FQ4", "teilung": "2 2 2",
                                     "kommentar": ""}, lambda: "V, 9" in m.koerper, "Volumen"),
        ("gelenk", "G", {"name": "G, 9"}, lambda: "G, 9" in m.hinges, "Gelenk"))
    for art, vorsilbe, werte, da, wort in fall:
        u0 = _undo_n(w)
        w.meldungen.leeren()
        w._objekt_uebernehmen(art, "", dict(werte), True)
        app.processEvents()
        check(f"{wort} neu „{werte['name']}“: Hinweis mit Komma/Semikolon, es entsteht nichts, kein Schritt",
              (w.meldungen.hinweis_mit("Komma") or w.meldungen.hinweis_mit("Semikolon"))
              and not da() and _undo_n(w) == u0, f"{w.meldungen.eintraege[-1:]} {u0}->{_undo_n(w)}")
    # Umbenennen
    fall = (
        ("stab", "S1", {"name": "S, 1", "elemente": "0, 1", "kommentar": ""}, lambda: "S1" in m.members
         and "S, 1" not in m.members, "Stab"),
        ("linie", "Q1", {"name": "Q, 1", "kn": ", ".join(str(n) for n in m.lines["Q1"].nodes),
                         "kommentar": ""}, lambda: "Q1" in m.lines and "Q, 1" not in m.lines, "Linie"),
        ("geoflaeche", "FQ1", {"name": "FQ;1", "linien": "Q1, Q2, Q3, Q4", "teilung": "4 4",
                               "kommentar": ""}, lambda: "FQ1" in m.flaechen and "FQ;1" not in m.flaechen,
         "Fläche"),
        ("geokoerper_einzeln", "VQ", {"name": "V, Q", "flaechen": "FQ1, FQ2, FQ3, FQ4", "teilung": "2 2 2",
                                      "kommentar": ""}, lambda: "VQ" in m.koerper and "V, Q" not in m.koerper,
         "Volumen"),
        ("gelenk", "G1", {"name": "G, 1"}, lambda: "G1" in m.hinges and "G, 1" not in m.hinges, "Gelenk"))
    for art, name, werte, unveraendert, wort in fall:
        u0 = _undo_n(w)
        w.meldungen.leeren()
        w._objekt_uebernehmen(art, name, dict(werte), False)
        app.processEvents()
        check(f"{wort} {name} -> „{werte['name']}“: Hinweis, der Name bleibt, kein Schritt zum Rückgängigmachen",
              (w.meldungen.hinweis_mit("Komma") or w.meldungen.hinweis_mit("Semikolon"))
              and unveraendert() and _undo_n(w) == u0, f"{w.meldungen.eintraege[-1:]} {u0}->{_undo_n(w)}")
    # Positivprobe: ein Name ohne Trenner geht, und ein vorhandener mit Komma bleibt bearbeitbar
    _maske_zu(w, app)
    w.meldungen.leeren()
    w._objekt_uebernehmen("stab", "", {"name": "S 2", "elemente": "2, 3", "kommentar": ""}, True)
    check("Stab „S 2“ (ohne Trenner) wird angelegt", "S 2" in m.members and not w.meldungen.alle,
          str(w.meldungen.eintraege[-1:]))
    m.add_member("S, 7", [4, 5])
    w.meldungen.leeren()
    w._objekt_uebernehmen("stab", "S, 7", {"name": "S, 7", "elemente": "4, 5", "kommentar": "",
                                           "design": False}, False)
    check("ein Stab „S, 7“ aus einer alten Datei: Übernehmen mit unverändertem Namen geht",
          "S, 7" in m.members and not m.members["S, 7"].design and not w.meldungen.hinweis_mit("Komma"),
          str(w.meldungen.eintraege[-1:]))
    w.meldungen.leeren()
    w._objekt_uebernehmen("stab", "S, 7", {"name": "S7", "elemente": "4, 5", "kommentar": ""}, False)
    check("… und weg vom Komma umbenennen geht ebenso", "S7" in m.members and "S, 7" not in m.members,
          str(w.meldungen.eintraege[-1:]))
    _maske_zu(w, app)


def test_n12_lager():
    w, app = _fenster()
    m = _modell(w, app)
    _maske_zu(w, app)
    # Maske, Eigenschaften (Wirkung geaendert) und Beschriftung (nur der Name)
    for art, i, werte, geaendert in (
            ("lager_einzeln", "0", {"name": "Lager, oben"}, None),
            ("lager_einzeln", "0", {"name": "Lager;oben"}, {"name"}),
            ("linienlager_einzeln", "0", {"name": "LL, B"}, {"name"}),
            ("linienlager_einzeln", "0", {"name": "LL;B"}, None)):
        obj = w._lagerliste_von(art)[int(i)]
        vorher = (getattr(obj, "name", "") or "")
        u0 = _undo_n(w)
        w.meldungen.leeren()
        w._objekt_uebernehmen(art, i, dict(werte), False, geaendert)
        app.processEvents()
        check(f"{art} {i} -> „{werte['name']}“ ({'Beschriftung' if geaendert else 'Eigenschaften'}): "
              "Hinweis, Name bleibt, kein Schritt",
              (w.meldungen.hinweis_mit("Komma") or w.meldungen.hinweis_mit("Semikolon"))
              and (getattr(obj, "name", "") or "") == vorher and _undo_n(w) == u0,
              f"{w.meldungen.eintraege[-1:]} {vorher!r}->{obj.name!r} {u0}->{_undo_n(w)}")
    # Tabelle
    w.refresh_all(); app.processEvents()
    z = next(k for k, r in enumerate(w.tbl_lager.modell.zeilen) if str(r[0]) == "0")
    vorher, u0 = m.supports[0].name, _undo_n(w)
    w.meldungen.leeren()
    ok = w._lager_aendern(z, 2, "Lager, hinten")
    check("Lagertabelle, Name „Lager, hinten“: nicht übernommen, Hinweis, kein Schritt",
          ok is False and (w.meldungen.hinweis_mit("Komma")) and m.supports[0].name == vorher
          and _undo_n(w) == u0, f"{ok} {w.meldungen.eintraege[-1:]} {vorher!r}->{m.supports[0].name!r}")
    w.meldungen.leeren()
    ok = w._lager_aendern(z, 2, "Lager hinten")
    check("… „Lager hinten“ wird übernommen", ok is True and m.supports[0].name == "Lager hinten",
          f"{ok} {m.supports[0].name!r}")
    # Sammelmaske
    m.supports[0].name = "Lager A"
    w.sammelmaske("lager", [0, 1]); app.processEvents()
    mk = w.maskenrand.maske
    u0 = _undo_n(w)
    w.meldungen.leeren()
    mk.setzen("name", "Lager, X")
    mk.anwenden(); app.processEvents()
    check("Sammelmaske Lager, Name „Lager, X“: Hinweis (Komma), keine Namen geschrieben, kein Schritt",
          w.meldungen.hinweis_mit("Komma") and m.supports[0].name == "Lager A" and m.supports[1].name == ""
          and _undo_n(w) == u0, f"{w.meldungen.eintraege[-1:]} {[s.name for s in m.supports[:2]]}")
    _maske_zu(w, app)
    # das Modell selbst bleibt bei einem Namen mit Komma aus einer alten Datei offen
    m.supports[1].name = "Alt, Lager"
    w.refresh_all(); app.processEvents()
    w.meldungen.leeren()
    w._objekt_uebernehmen("lager_einzeln", "1", {"name": "Alt, Lager", "groesse": 2.0}, False, {"groesse"})
    check("ein Lager „Alt, Lager“ aus einer alten Datei: Symbolgröße ändern geht",
          not w.meldungen.hinweis_mit("Komma") and abs(m.supports[1].groesse - 2.0) < 1e-12,
          f"{w.meldungen.eintraege[-1:]} {m.supports[1].groesse}")
    _maske_zu(w, app)


def test_n12_alte_dialoge():
    """Die alten Dialoge Linie, Flaeche, Volumen: der Name wird nach dem Schliessen
    geprueft; ein Hinweis, nichts entsteht, kein Schritt."""
    from statik3d.gui import dialogs as dg
    w, app = _fenster()
    m = _modell(w, app)
    _maske_zu(w, app)

    class Attrappe:
        inhalt: dict = {}

        def __init__(self, *a, **k):
            pass

        def exec(self):
            return True

        def werte(self):
            return dict(Attrappe.inhalt)

    alt = (dg.LinienDialog, dg.FlaechenDialog, dg.KoerperDialog)
    try:
        dg.LinienDialog = dg.FlaechenDialog = dg.KoerperDialog = Attrappe
        Attrappe.inhalt = {"name": "L, 5", "typ": "polyline", "nodes": [0, 1], "comment": ""}
        u0 = _undo_n(w)
        w.meldungen.leeren()
        w.add_linie()
        check("Dialog Linie neu „L, 5“: Hinweis, keine Linie, kein Schritt",
              w.meldungen.hinweis_mit("Komma") and "L, 5" not in m.lines and _undo_n(w) == u0,
              str(w.meldungen.eintraege[-1:]))
        Attrappe.inhalt = {"name": "Q;1", "typ": "polyline", "nodes": list(m.lines["Q1"].nodes), "comment": ""}
        w.meldungen.leeren()
        w.linie_bearbeiten("Q1")
        check("Dialog Linie Q1 -> „Q;1“: Hinweis, Q1 bleibt, kein Schritt",
              w.meldungen.hinweis_mit("Semikolon") and "Q1" in m.lines and "Q;1" not in m.lines
              and _undo_n(w) == u0, str(w.meldungen.eintraege[-1:]))
        Attrappe.inhalt = {"name": "F, 5", "linien": ["Q1", "Q2", "Q3", "Q4"], "typ": "eben", "dicke": "",
                          "material": "", "teilung": [2, 2], "kommentar": "", "vernetzen": False}
        w.sel_linien = ["Q1", "Q2", "Q3", "Q4"]
        w.meldungen.leeren()
        w.add_flaeche_aus_auswahl()
        check("Dialog Fläche neu „F, 5“: Hinweis, keine Fläche, kein Schritt",
              w.meldungen.hinweis_mit("Komma") and "F, 5" not in m.flaechen and _undo_n(w) == u0,
              str(w.meldungen.eintraege[-1:]))
        Attrappe.inhalt = {"name": "V, 5", "flaechen": ["FQ1", "FQ2", "FQ3", "FQ4"], "material": "",
                          "teilung": [2, 2, 2], "kommentar": "", "kerbfall": 0.0, "kerbfall_naht": 0.0,
                          "vernetzen": False}
        w.sel_flaechen = ["FQ1", "FQ2", "FQ3", "FQ4"]
        w.meldungen.leeren()
        w.add_koerper_aus_auswahl()
        check("Dialog Volumen neu „V, 5“: Hinweis, kein Volumen, kein Schritt",
              w.meldungen.hinweis_mit("Komma") and "V, 5" not in m.koerper and _undo_n(w) == u0,
              str(w.meldungen.eintraege[-1:]))
    finally:
        dg.LinienDialog, dg.FlaechenDialog, dg.KoerperDialog = alt
        w.sel_linien, w.sel_flaechen = [], []


def test_n12_browser():
    from statik3d.web import server as srv
    from statik3d.model import Model
    w, app = _fenster()
    m = _modell(w, app)
    for was, rufen, lesen in (
            ("set_member", lambda: srv._op_set_member(None, m, {"name": "S, 5", "elements": [0, 1]}),
             lambda: "S, 5" in m.members),
            ("add_hinge", lambda: srv._op_add_hinge(None, m, {"name": "G, 5", "end": 0}),
             lambda: "G, 5" in m.hinges),
            ("line_support", lambda: srv._op_line_support(None, m, {"nodes": [0, 1], "name": "LL, 5",
                                                                     "behaviour": {"uz": {"typ": "rigid"}}}),
             lambda: any(x.name == "LL, 5" for x in m.line_supports)),
            ("surface_support", lambda: srv._op_surface_support(None, m, {"elems": [0], "name": "FL;5",
                                                                           "behaviour": {"uz": {"typ": "rigid"}}}),
             lambda: any(x.name == "FL;5" for x in m.surface_supports))):
        try:
            rufen()
            ok, text = False, "keine Ausnahme"
        except srv.ApiError as ex:
            ok, text = ("Komma" in str(ex) or "Semikolon" in str(ex)) and not lesen(), str(ex)
        except Exception as ex:             # noqa: BLE001
            ok, text = False, f"{type(ex).__name__}: {ex}"
        check(f"Browser: {was} mit Komma oder Semikolon im Namen wird abgewiesen, es entsteht nichts", ok, text)
    srv._op_set_member(None, m, {"name": "S 5", "elements": [0, 1]})
    check("Browser: set_member „S 5“ legt den Stab an", "S 5" in m.members)


# --------------------------------------------------------------------------
# N13
# --------------------------------------------------------------------------
def test_n13_stab_elemente():
    w, app = _fenster()
    m = _modell(w, app)
    _maske_zu(w, app)
    ne = len(m.elements)
    for eingabe, falsch in (("6, 99", "99"), (f"7, {ne}", str(ne)), ("8, -1", "-1")):
        u0 = _undo_n(w)
        w.meldungen.leeren()
        w._objekt_uebernehmen("stab", "", {"name": "SX", "elemente": eingabe, "kommentar": ""}, True)
        app.processEvents()
        check(f"Stab aus Elementen „{eingabe}“: Hinweis nennt „{falsch}“ und „gibt es nicht“, kein Stab, kein Schritt",
              w.meldungen.hinweis_mit(f"„{falsch}“", "gibt es nicht") and "SX" not in m.members
              and _undo_n(w) == u0, str(w.meldungen.eintraege[-1:]))
    # bestehender Stab: abgewiesenes Uebernehmen laesst ihn, wie er war
    vor = list(m.members["S1"].elements)
    u0 = _undo_n(w)
    w.meldungen.leeren()
    w._objekt_uebernehmen("stab", "S1", {"name": "S1", "elemente": "0, 1, 77", "kommentar": ""}, False)
    check("Stab S1 mit „0, 1, 77“ übernehmen: abgewiesen, S1 behält seine Elemente, kein Schritt",
          w.meldungen.hinweis_mit("„77“") and list(m.members["S1"].elements) == vor and _undo_n(w) == u0,
          f"{w.meldungen.eintraege[-1:]} {vor}->{m.members['S1'].elements}")
    # ein vorhandenes Element, das kein Stabelement ist, fiel ebenfalls still weg
    m.add_nodes(np.array([[30, 0, 0], [31, 0, 0], [31, 1, 0], [30, 1, 0.]]))
    ids = m.add_elements("shell4", [[m.nn - 4, m.nn - 3, m.nn - 2, m.nn - 1]], next(iter(m.materials)),
                         next(iter(m.shells), None) or "")
    schale = ids[0]
    w.meldungen.leeren()
    w._objekt_uebernehmen("stab", "", {"name": "SY", "elemente": f"6, {schale}", "kommentar": ""}, True)
    check(f"Stab aus „6, {schale}“ (das zweite ist eine Schale): Hinweis nennt „{schale}“ und „kein Stabelement“",
          w.meldungen.hinweis_mit(f"„{schale}“", "kein Stabelement") and "SY" not in m.members,
          str(w.meldungen.eintraege[-1:]))
    w.meldungen.leeren()
    w._objekt_uebernehmen("stab", "", {"name": "SZ", "elemente": "6, 7", "kommentar": ""}, True)
    check("… „6, 7“ legt den Stab an", "SZ" in m.members and list(m.members["SZ"].elements) == [6, 7],
          str(w.meldungen.eintraege[-1:]))
    _maske_zu(w, app)


def test_n13_starrkoerper():
    w, app = _fenster()
    m = _modell(w, app)
    m.add_starrkoerper(0, [1, 2], "RBE2")
    w.refresh_all(); app.processEvents()
    i = str(len(m.starrkoerper) - 1)
    _maske_zu(w, app)
    mk = w._objektmaske("starrkoerper", i)
    vor, u0 = list(m.starrkoerper[int(i)].slaves), _undo_n(w)
    w.meldungen.leeren()
    mk.setzen("slaves", "1, 2, 9999")
    ok = mk.anwenden(); app.processEvents()
    check("starrer Körper, angeschlossene Knoten „1, 2, 9999“: abgewiesen, der Hinweis nennt „9999“",
          not ok and w.meldungen.hinweis_mit("„9999“", "gibt es nicht"), str(w.meldungen.eintraege[-1:]))
    check("… die Knoten bleiben [1, 2], kein Schritt, die Maske behält die Eingabe",
          list(m.starrkoerper[int(i)].slaves) == vor and _undo_n(w) == u0 and w.maskenrand.maske is mk
          and mk._felder["slaves"].text() == "1, 2, 9999", f"{vor} -> {m.starrkoerper[int(i)].slaves}")
    mk.setzen("slaves", "1, 2, 3")
    ok = mk.anwenden(); app.processEvents()
    check("… „1, 2, 3“ wird übernommen", ok and list(m.starrkoerper[int(i)].slaves) == [1, 2, 3],
          str(m.starrkoerper[int(i)].slaves))
    _maske_zu(w, app)
    # neu angelegt: ein Eintrag ausserhalb legt nichts an
    n0, u0 = len(m.starrkoerper), _undo_n(w)
    w.meldungen.leeren()
    w._objekt_uebernehmen("starrkoerper", "", {"name": "SKX", "art": "RBE2", "master": 0,
                                               "slaves": "1, 2, 9999", "gewichte": "", "kommentar": ""}, True)
    check("starrer Körper neu mit „1, 2, 9999“: abgewiesen, es entsteht keiner, kein Schritt",
          w.meldungen.hinweis_mit("„9999“") and len(m.starrkoerper) == n0 and _undo_n(w) == u0,
          str(w.meldungen.eintraege[-1:]))


def test_n13_zahlenliste():
    from statik3d import zahlen as zl
    from statik3d.gui.main import MainWindow as G
    r, ex = _gerufen(lambda: G._zahlenliste("1, 2 3", feld="Knoten", bereich=(10, "Knoten")))
    check("_zahlenliste mit bereich: „1, 2 3“ innerhalb von 10 gilt", ex is None and r == [1, 2, 3], str(ex or r))
    r, ex = _gerufen(lambda: G._zahlenliste("1, 12, 40", feld="Knoten", bereich=(10, "Knoten")))
    check("… „1, 12, 40“: Eingabefehler, nennt beide Einträge und den Bereich 0 bis 9",
          isinstance(ex, zl.Eingabefehler) and "„12“" in str(ex) and "„40“" in str(ex) and "0 bis 9" in str(ex),
          str(ex or r))
    r, ex = _gerufen(lambda: G._zahlenliste("0", feld="Knoten", bereich=(0, "Knoten")))
    check("… in einem Modell ohne Knoten: Eingabefehler „es gibt noch keine“",
          isinstance(ex, zl.Eingabefehler) and "noch keine" in str(ex), str(ex or r))
    r, ex = _gerufen(lambda: G._zahlenliste("1 2", feld="Knoten"))
    check("ohne bereich bleibt alles wie vorher", ex is None and r == [1, 2], str(ex or r))


# --------------------------------------------------------------------------
# N14
# --------------------------------------------------------------------------
def test_n14_profileditor():
    from PySide6 import QtWidgets
    from statik3d import zahlen as zl
    from statik3d.gui.profilmaske import ProfilEditor
    _fenster()
    pe = ProfilEditor(None)
    pe.setze()
    pe.knoten_zufuegen(1, 0.0, 0.0)
    pe.knoten_zufuegen(2, 100.0, 0.0)
    pe.knoten_zufuegen(3, 100.0, 100.0)
    pe.element_zufuegen(1, 2, 10.0)
    pe.element_zufuegen(2, 3, 10.0)
    pe.aktualisieren()

    def ok_frei():
        return pe.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).isEnabled()

    check("Vorbereitung: drei verschiedene Knoten, OK frei", ok_frei())
    pe.tb_knoten.item(2, 0).setText("2")
    pe.aktualisieren()
    try:
        pe.inhalt()
        ok, mel = False, "keine Ausnahme"
    except zl.Eingabefehler as ex:
        ok, mel = "2" in str(ex) and "Zeile" in str(ex), str(ex)
    except Exception as ex:                 # noqa: BLE001
        ok, mel = False, f"{type(ex).__name__}: {ex}"
    check("zweimal Knotennummer 2 (Zeilen 2 und 3): inhalt() wirft Eingabefehler mit Nummer und Zeilen", ok, mel)
    check("… OK ist gesperrt, die Kennwerte nennen die Nummer und beide Zeilen",
          not ok_frei() and "2" in pe.lbl_werte.text() and "Zeile 2" in pe.lbl_werte.text()
          and "3" in pe.lbl_werte.text(), pe.lbl_werte.text()[:100])
    pe.tb_knoten.item(2, 0).setText("3")
    pe.aktualisieren()
    check("wieder verschieden: OK frei, drei Knoten", ok_frei() and sorted(pe.inhalt()["knoten"]) == [1, 2, 3])
    # dieselbe Zahl in anderer Schreibweise ist dieselbe Nummer
    pe.tb_knoten.item(2, 0).setText("02")
    pe.aktualisieren()
    check("„02“ neben „2“ ist dieselbe Nummer: OK gesperrt", not ok_frei(), pe.lbl_werte.text()[:100])
    pe.tb_knoten.item(2, 0).setText("3")
    pe.aktualisieren()
    # über die Schnittstelle: knoten_zufuegen mit vorhandener Nummer
    pe.knoten_zufuegen(2, 50.0, 50.0)
    check("Knoten 2 ein zweites Mal hinzugefügt: OK gesperrt", not ok_frei(), pe.lbl_werte.text()[:100])
    pe.deleteLater()


# --------------------------------------------------------------------------
# N15
# --------------------------------------------------------------------------
def _saf_mit_komma(pfad):
    from tests.test_importers import saf_sheets
    from statik3d.importers.xlsx_reader import write_xlsx
    sheets = saf_sheets()
    tausch = {"LC2": "Nutzlast, links", "LC3": "Wind; quer"}
    for blatt, zeilen in sheets.items():
        for zeile in zeilen[1:]:
            for k, v in enumerate(zeile):
                if isinstance(v, str) and v in tausch:
                    zeile[k] = tausch[v]
    write_xlsx(pfad, sheets)


def test_n15_import():
    from statik3d.importers import import_file
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "komma.xlsx")
        _saf_mit_komma(p)
        log = []
        m, ex = _gerufen(lambda: import_file(p, log=log))
        if ex is not None:
            check("SAF mit Lastfällen „Nutzlast, links“ und „Wind; quer“ lässt sich importieren", False, str(ex))
            return
        namen = list(m.load_cases)
        check("kein Lastfall trägt nach dem Import Komma oder Semikolon im Namen",
              not any(z in n for n in namen for z in ",;"), str(namen))
        check("… „Nutzlast, links“ heißt „Nutzlast links“, „Wind; quer“ heißt „Wind quer“",
              "Nutzlast links" in m.load_cases and "Wind quer" in m.load_cases, str(namen))
        check("… die Kombination CO1 zeigt auf den neuen Namen",
              m.combinations["CO1"].factors == {"LC1": 1.35, "Nutzlast links": 1.5},
              str(m.combinations["CO1"].factors))
        n_wind = m.load_cases["Wind quer"].n_loads if "Wind quer" in m.load_cases else -1
        n_nutz = m.load_cases["Nutzlast links"].n_loads if "Nutzlast links" in m.load_cases else -1
        check("… die Lasten (Knotenkraft, Streckenlast, Flächenlast) blieben an ihren Lastfällen",
              n_wind >= 1 and n_nutz >= 2, f"{n_wind} {n_nutz}")
        text = "\n".join(log)
        check("Das Importprotokoll nennt beide alten Namen und die neuen",
              "Nutzlast, links" in text and "Nutzlast links" in text and "Wind; quer" in text
              and "Wind quer" in text, text[-400:])


def test_n15_modell():
    from statik3d.model import Model
    m = Model()
    m.add_load_case("A, B", "Q", activate=False)
    m.add_load_case("A B", "Q", activate=False)               # der Name, den die Ersetzung wollte
    m.add_load_case("S;1", "Q", activate=False)
    m.add_load_case("Alt, vorhanden", "Q", activate=False)
    m.add_combination("K, 1", {"A, B": 1.0, "S;1": 1.5}, "ULS")
    m.add_fatigue_load("E1", "A, B", "S;1")
    fn, ex = _gerufen(lambda: m.namenstrenner_ersetzen(ausser={"Alt, vorhanden"}))
    if ex is not None:
        check("Model.namenstrenner_ersetzen läuft", False, f"{type(ex).__name__}: {ex}")
        return
    namen = list(m.load_cases)
    check("Lastfälle mit Trenner sind umbenannt, eindeutig: „A, B“ -> „A B 2“, „S;1“ -> „S 1“",
          "A B 2" in namen and "S 1" in namen and "A B" in namen and "A, B" not in namen
          and "S;1" not in namen, str(namen))
    check("… ein Name aus der Menge ausser bleibt, wie er ist", "Alt, vorhanden" in namen, str(namen))
    check("… die Kombination heißt „K 1“ und zeigt auf die neuen Lastfälle",
          "K 1" in m.combinations and "K, 1" not in m.combinations
          and m.combinations["K 1"].factors == {"A B 2": 1.0, "S 1": 1.5}, str(m.combinations.keys()))
    fl = m.fatigue_loads["E1"]
    check("… die Ermüdungslast zeigt auf die neuen Namen", (fl.case_max, fl.case_min) == ("A B 2", "S 1"),
          f"{fl.case_max} {fl.case_min}")
    check("… die Rückgabe sind Protokollzeilen mit altem und neuem Namen",
          any("A, B" in z and "A B 2" in z for z in fn) and any("K, 1" in z and "K 1" in z for z in fn)
          and not any("Alt, vorhanden" in z for z in fn), str(fn))
    fn2 = m.namenstrenner_ersetzen(ausser={"Alt, vorhanden"})
    check("ein zweiter Lauf findet nichts mehr", fn2 == [], str(fn2))


# --------------------------------------------------------------------------
# N16
# --------------------------------------------------------------------------
def _mit_zeitgrenze(fn, sekunden=5.0):
    """(fertig, Ergebnis, Ausnahme): fn in einem Faden - eine Endlosschleife
    haelt die Pruefung nicht an (der Faden ist Daemon, os._exit am Ende)."""
    erg = {}

    def lauf():
        try:
            erg["r"] = fn()
        except BaseException as ex:         # noqa: BLE001
            erg["ex"] = ex
    t = threading.Thread(target=lauf, daemon=True)
    t.start()
    t.join(sekunden)
    return (not t.is_alive()), erg.get("r"), erg.get("ex")


def test_n16_din19704():
    from statik3d.bridges.din19704 import Regelwerk
    from statik3d.model import Model, NameVergeben
    for praefix in ("DIN, ", "DIN;", " DIN "):
        m = Model()
        m.add_load_case("EG", "G", activate=False)
        m.add_load_case("V", "Q", activate=False)
        rw = Regelwerk()
        log = []
        t0 = time.time()
        fertig, r, ex = _mit_zeitgrenze(lambda: rw.kombinationen(m, praefix=praefix, log=log))
        check(f"Präfix {praefix!r}: kehrt zurück statt endlos zu laufen", fertig,
              f"{time.time() - t0:.1f} s")
        check("… mit NameVergeben, der Grund nennt das Präfix; es entsteht keine Kombination",
              fertig and isinstance(ex, NameVergeben) and "Präfix" in str(ex) and not m.combinations,
              f"{type(ex).__name__ if ex else ex} {ex} {list(m.combinations)}")
    m = Model()
    m.add_load_case("EG", "G", activate=False)
    m.add_load_case("V", "Q", activate=False)
    fertig, r, ex = _mit_zeitgrenze(lambda: Regelwerk().kombinationen(m, praefix="DIN "))
    check("das Vorgabepräfix „DIN “ bildet weiter Kombinationen", fertig and ex is None and bool(r) and
          all(n.startswith("DIN ") for n in r), f"{ex} {r}")
    fertig, r, ex = _mit_zeitgrenze(lambda: Regelwerk().kombinationen(m, praefix="Norm "))
    check("ein Präfix „Norm “ ohne Trenner geht", fertig and ex is None and bool(r) and
          all(n.startswith("Norm ") for n in r), f"{ex} {r}")


# --------------------------------------------------------------------------
# N17
# --------------------------------------------------------------------------
def test_n17_zeichen():
    from statik3d.gui.main import MainWindow as G
    doku = G._zahlenliste.__doc__ or ""
    fremd = [c for c in doku if "֐" <= c <= "ۿ"]
    check("Docstring von _zahlenliste trägt kein hebräisches oder arabisches Zeichen", not fremd,
          repr(fremd[:3]))
    check("… dort steht „×“ trennt immer (Teilung „4 × 4“)",
          "„×“ trennt immer" in re.sub(r"\s+", " ", doku), repr(doku[-120:]))
    # kein Quelltext des Programms traegt solche Zeichen
    wurzel = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statik3d")
    treffer = []
    for ordner, _d, dateien in os.walk(wurzel):
        for f in dateien:
            if not f.endswith(".py"):
                continue
            pfad = os.path.join(ordner, f)
            with open(pfad, encoding="utf-8") as fh:
                for nr, zeile in enumerate(fh, 1):
                    if re.search("[֐-ۿ]", zeile):
                        treffer.append(f"{os.path.relpath(pfad, wurzel)}:{nr}")
    check("kein Quelltext unter statik3d/ enthält hebräische oder arabische Buchstaben", not treffer,
          ", ".join(treffer[:5]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_n12_modell, test_n12_umbenennen_im_modell, test_n12_masken, test_n12_lager,
              test_n12_alte_dialoge, test_n12_browser, test_n13_zahlenliste, test_n13_stab_elemente,
              test_n13_starrkoerper, test_n14_profileditor, test_n15_import, test_n15_modell,
              test_n17_zeichen, test_n16_din19704):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
