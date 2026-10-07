"""
Paket P12 der Fehlerliste (06.10.2026): Eingaben in Listen und Zahlenfeldern.

Grundsatz: keine Eingabe geht still verloren oder wird still umgedeutet.
Ungueltiges wird als Hinweis abgewiesen (9b, ``zahlen.Eingabefehler``), und die
Maske bleibt mit den Eingaben offen.

* F21  Lastfaelle mit Komma oder Semikolon im Namen: die Haken der Stellungs-
       und der Situationsmaske tragen die Namen als Liste (nicht als Text, den
       die Maske wieder an Kommas zerlegt); neue Namen mit Komma oder
       Semikolon weist die Namenspruefung ab (bis die Namensregel R2 Namen und
       Bezeichnungen trennt).
* F22  Nummernlisten ohne feste Anzahl (RBE-Slaves, Linienknoten,
       Stab-Elemente, Linientabelle): ein Eintrag, der keine ganze Zahl ist,
       wird abgewiesen statt wegzufallen.
* F23  Profileditor: Knoten- und Elementnummern nur als ganze Zahlen.
* F24  Teilung der Masken Flaeche, Volumen und der Sammelmaske: mindestens 1.
* F41  Zahlenfeld: eine bestaetigte Mehrdeutigkeit gilt nur fuer diesen Text.

Aufruf:  python -m tests.test_fehler_p12
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_p12_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
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
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b)
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w)
    _FENSTER.update(w=w, app=app)
    return w, app


def _undo_n(w):
    return len(getattr(w, "_undo", []) or [])


def _maske_zu(w, app):
    """Eine offene Maske ohne Rueckfrage schliessen."""
    try:
        w._leiste_weg()
    except Exception:                       # noqa: BLE001
        pass
    if w.maskenrand.maske is not None:
        w._maske_verwerfen(w.maskenrand.maske)
    app.processEvents()


def _komma_modell(w):
    """Ein kleines Modell mit Lastfaellen, deren Namen Komma und Semikolon
    tragen - wie aus einer aelteren Datei oder einem Import (die
    Namenspruefung weist sie beim Anlegen jetzt ab)."""
    from statik3d.model import Material, Section
    from statik3d.bridges.positions import Stellung
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    n = [m.add_node(4.0 * i, 0.0, 0.0) for i in range(3)]
    for i in range(2):
        m.add_element("beam", [n[i], n[i + 1]], "S355", "HEB 300")
    m.support(n[0], "all", name="Einspannung")
    m.load_node(n[-1], Fz=-5e3, case=next(iter(m.load_cases)))
    for nm in ("W, links", "S;1"):
        m.add_load_case(nm, "Q", activate=False)
        m.load_node(n[-1], Fy=1e3, case=nm)
    st = Stellung("S1")
    st.faelle = list(m.load_cases)
    m.stellungen.append(st)
    return m


# --------------------------------------------------------------------------
# F21
# --------------------------------------------------------------------------
def test_f21_namenspruefung():
    from statik3d.model import Model, NameVergeben
    m = Model()
    m.add_load_case("W, links", "Q", activate=False)      # wie aus einer alten Datei
    for art in ("lastfall", "kombination"):
        for nm in ("A, B", "A,B", "S;1", "A;"):
            grund = m.namenskonflikt(nm, "", art)
            check(f"Name „{nm}“ als {art}: abgewiesen, der Grund nennt Komma oder Semikolon",
                  bool(grund) and ("Komma" in grund or "Semikolon" in grund), grund)
    check("ein Name ohne Trenner ist frei", m.namenskonflikt("W links", "", "lastfall") == "")
    check("ein vorhandener Name mit Komma bleibt, wie er ist (Eigenschaften ändern geht)",
          m.namenskonflikt("W, links", "W, links", "lastfall") == "")
    try:
        m.lastfall_umbenennen("LF1", "X, Y")
        ok, text = False, "keine Ausnahme"
    except NameVergeben as ex:
        ok, text = "LF1" in m.load_cases and "X, Y" not in m.load_cases, str(ex)
    check("Umbenennen in „X, Y“ wirft NameVergeben, der Lastfall bleibt LF1", ok, text)
    ok = m.lastfall_umbenennen("W, links", "W links") is not None and "W links" in m.load_cases
    check("Umbenennen weg vom Komma geht", ok)
    # die Wege neben der Maske: Browser (add_case, edit_case) und die Generatoren
    from statik3d.web import server as srv
    try:
        srv._op_add_case(None, m, {"name": "A, B"})
        ok, text = False, "keine Ausnahme"
    except srv.ApiError as ex:
        ok, text = "Komma" in str(ex) and "A, B" not in m.load_cases, str(ex)
    check("Browser: add_case mit „A, B“ wird abgewiesen, es entsteht kein Lastfall", ok, text)
    try:
        srv._op_edit_case(None, m, {"name": "LF1", "fields": {"new_name": "S;1"}})
        ok, text = False, "keine Ausnahme"
    except srv.ApiError as ex:
        ok, text = "Semikolon" in str(ex) and "LF1" in m.load_cases, str(ex)
    check("Browser: edit_case in „S;1“ wird abgewiesen, der Lastfall heißt weiter LF1", ok, text)
    try:
        m.generator_lastfall("Wind W1", "A, B")
        ok, text = False, "keine Ausnahme"
    except NameVergeben as ex:
        ok, text = "A, B" not in m.load_cases, str(ex)
    check("Generator (Wind, Wasserdruck): ein getippter Lastfallname mit Komma wird abgewiesen", ok, text)
    m.add_load_case("Q;7", "Q", activate=False)
    t0 = time.time()
    frei = m.freier_name("Q;7_Kopie", "lastfall")
    check("freier_name mit Komma im Vorschlag: sofort ein Name ohne Trenner (Kopie)",
          time.time() - t0 < 2.0 and not any(z in frei for z in ",;") and m.namenskonflikt(frei, "", "lastfall") == "",
          f"{frei!r} in {time.time() - t0:.2f} s")


def test_f21_stellungsmaske():
    from PySide6 import QtCore
    w, app = _fenster()
    m = _komma_modell(w)
    namen = list(m.load_cases)
    w.refresh_all(); app.processEvents()
    w._objektmaske("stellung", "S1"); app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder.get("faelle")
    angehakt = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).checkState() == QtCore.Qt.Checked]
    check("Stellungsmaske: alle drei zugewiesenen Lastfälle sind angehakt, auch „W, links“ und „S;1“",
          angehakt == namen, str(angehakt))
    w.meldungen.leeren()
    mk.setzen("dx", 0.25)
    ok = mk.anwenden(); app.processEvents()
    st = w.model.stellung("S1")
    check("„Übernehmen“ ohne Änderung an den Haken: alle drei bleiben in der Stellung",
          st.faelle == namen and ok, str(st.faelle))
    w._objektmaske("stellung", "S1"); app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder.get("faelle")
    i_w = next(i for i in range(lw.count()) if lw.item(i).text() == "W, links")
    lw.item(i_w).setCheckState(QtCore.Qt.Unchecked); app.processEvents()
    mk.anwenden(); app.processEvents()
    check("„W, links“ abgehakt: nur dieser fällt heraus",
          w.model.stellung("S1").faelle == [n for n in namen if n != "W, links"],
          str(w.model.stellung("S1").faelle))
    w._objektmaske("stellung", "S1"); app.processEvents()
    mk = w.maskenrand.maske
    mk._felder["faelle_alle"].setChecked(True); app.processEvents()
    mk.anwenden(); app.processEvents()
    check("„Alle Lastfälle anhaken“ nimmt auch die mit Komma und Semikolon",
          w.model.stellung("S1").faelle == namen, str(w.model.stellung("S1").faelle))
    _maske_zu(w, app)


def test_f21_gelenk_und_lager_namen():
    """Dieselbe Liste „zum Anhaken“ tragen Gelenke und Lager: ein Lager mit
    Komma im Namen darf in der Stellung abgeschaltet bleiben."""
    from PySide6 import QtCore
    w, app = _fenster()
    m = _komma_modell(w)
    m.support(0, "all", name="Lager, oben")
    st = m.stellung("S1")
    st.lager_aus = ["Lager, oben"]
    w.refresh_all(); app.processEvents()
    w._objektmaske("stellung", "S1"); app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder.get("lager_aus")
    angehakt = [lw.item(i).text() for i in range(lw.count()) if lw.item(i).checkState() == QtCore.Qt.Checked]
    check("Stellungsmaske: das abgeschaltete Lager „Lager, oben“ ist angehakt", angehakt == ["Lager, oben"],
          str(angehakt))
    mk.setzen("dx", 0.1)
    mk.anwenden(); app.processEvents()
    check("… und bleibt nach „Übernehmen“ abgeschaltet", w.model.stellung("S1").lager_aus == ["Lager, oben"],
          str(w.model.stellung("S1").lager_aus))
    _maske_zu(w, app)


def test_f21_situationsmaske():
    from PySide6 import QtCore
    w, app = _fenster()
    m = _komma_modell(w)
    w.refresh_all(); app.processEvents()
    w.situation_neu(); app.processEvents()
    mk = w.maskenrand.maske
    lw = mk._felder["lastfaelle"]
    w.meldungen.leeren()
    mk.setzen("name", "SIT_P12")
    for i in range(lw.count()):
        lw.item(i).setCheckState(QtCore.Qt.Checked if lw.item(i).text() == "W, links" else QtCore.Qt.Unchecked)
    ok = mk.anwenden(); app.processEvents()
    check("Situationsmaske: „W, links“ angehakt wird übernommen, kein „Unbekannt“",
          ok and not w.meldungen.hinweis_mit("Unbekannt")
          and w.model.load_cases["W, links"].situation == "SIT_P12"
          and w.model.load_cases["S;1"].situation == "",
          f"{w.meldungen.alle[-1:]} {w.model.load_cases['W, links'].situation!r}")
    w.situation_neu(); app.processEvents()
    mk = w.maskenrand.maske
    mk.setzen("name", "SIT_P12b")
    mk.zusatzknoepfe["Alle Lastfälle und Kombinationen"].click(); app.processEvents()
    lw = mk._felder["lastfaelle"]
    gehakt = sum(1 for i in range(lw.count()) if lw.item(i).checkState() == QtCore.Qt.Checked)
    check("„Alle Lastfälle und Kombinationen“ hakt auch Namen mit Komma und Semikolon an",
          gehakt == len(w.model.load_cases), f"{gehakt} von {len(w.model.load_cases)}")
    mk.anwenden(); app.processEvents()
    check("… und schreibt sie alle in die Situation",
          all(lc.situation == "SIT_P12b" for lc in w.model.load_cases.values()),
          str([lc.situation for lc in w.model.load_cases.values()]))
    _maske_zu(w, app)


def test_f21_umbenennen_in_maske():
    """Das Umbenennen in der Maske eines Lastfalls: ein Name mit Komma wird als
    Hinweis abgewiesen, das Modell bleibt, die Maske behaelt die Eingabe."""
    w, app = _fenster()
    m = _komma_modell(w)
    w.refresh_all(); app.processEvents()
    w._objektmaske("lastfall", "LF1"); app.processEvents()
    mk = w.maskenrand.maske
    u0 = _undo_n(w)
    w.meldungen.leeren()
    mk.setzen("name", "A, B")
    ok = mk.anwenden(); app.processEvents()
    check("Lastfall in „A, B“ umbenennen: abgewiesen mit Hinweis (Komma)",
          not ok and w.meldungen.hinweis_mit("Komma"), str(w.meldungen.eintraege[-1:]))
    check("… der Lastfall heißt weiter LF1, kein Schritt zum Rückgängigmachen",
          "LF1" in w.model.load_cases and "A, B" not in w.model.load_cases and _undo_n(w) == u0,
          f"{list(w.model.load_cases)} {u0}->{_undo_n(w)}")
    check("… die Maske bleibt offen und trägt die Eingabe noch",
          w.maskenrand.maske is mk and mk._felder["name"].text() == "A, B")
    _maske_zu(w, app)


# --------------------------------------------------------------------------
# F22
# --------------------------------------------------------------------------
def test_f22_nummernlisten():
    from statik3d import zahlen as zl
    from statik3d.gui.main import MainWindow as G
    check("„1, 2 3“ bleibt [1, 2, 3]", G._zahlenliste("1, 2 3") == [1, 2, 3])
    check("„+3, -4“ bleibt [3, -4]", G._zahlenliste("+3, -4") == [3, -4])
    check("leer bleibt leer", G._zahlenliste("") == [] and G._zahlenliste(None) == [])
    for text, falsch in (("1, 2,5", "2,5"), ("3, 4, x, 5", "x"), ("0, 1x, 2", "1x"),
                         ("1.000, 2", "1.000"), ("1, 2 ,", None)):
        try:
            res = G._zahlenliste(text, feld="Knoten")
            ok, mel = falsch is None, str(res)
        except zl.Eingabefehler as ex:
            ok, mel = falsch is not None and f"„{falsch}“" in str(ex) and "ganze Zahl" in str(ex), str(ex)
        check(f"„{text}“: " + ("Eingabefehler, nennt den Eintrag" if falsch else "gilt"), ok, mel)


def test_f22_masken():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    m = w.model
    m.add_starrkoerper(0, [1, 2], "RBE2")
    m.add_line("L9", [3, 4])
    w.refresh_all(); app.processEvents()
    i = str(len(m.starrkoerper) - 1)
    for art, name, key, eingabe, lesen, falsch in (
            ("starrkoerper", i, "slaves", "1, 2,5", lambda: list(w.model.starrkoerper[int(i)].slaves), "2,5"),
            ("linie", "L9", "kn", "3, 4, x, 5", lambda: list(w.model.lines["L9"].nodes), "x")):
        _maske_zu(w, app)
        mk = w._objektmaske(art, name)
        vorher, u0 = lesen(), _undo_n(w)
        w.meldungen.leeren()
        mk.setzen(key, eingabe)
        ok = mk.anwenden(); app.processEvents()
        check(f"{art} {key} „{eingabe}“: abgewiesen mit Hinweis, der den Eintrag nennt",
              not ok and w.meldungen.hinweis_mit(f"„{falsch}“", "ganze Zahl"), str(w.meldungen.eintraege[-1:]))
        check("… das Modell bleibt, kein Schritt zum Rückgängigmachen; die Maske behält die Eingabe",
              lesen() == vorher and _undo_n(w) == u0 and w.maskenrand.maske is mk
              and mk._felder[key].text() == eingabe, f"{vorher} -> {lesen()}")
    _maske_zu(w, app)
    w.meldungen.leeren()
    u0 = _undo_n(w)
    w._objekt_uebernehmen("stab", "", {"name": "S9", "elemente": "0, 1x, 2", "kommentar": ""}, True)
    app.processEvents()
    check("Stab aus Elementen „0, 1x, 2“: abgewiesen, es entsteht kein Stab",
          w.meldungen.hinweis_mit("„1x“") and "S9" not in w.model.members and _undo_n(w) == u0,
          str(w.meldungen.eintraege[-1:]))
    w._objekt_uebernehmen("stab", "", {"name": "S9", "elemente": "0, 1", "kommentar": ""}, True)
    app.processEvents()
    check("… „0, 1“ legt ihn an", "S9" in w.model.members and list(w.model.members["S9"].elements) == [0, 1],
          str(w.model.members.get("S9")))


def test_f22_tabelle():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    m = w.model
    m.add_line("L9", [3, 4])
    w.refresh_all(); app.processEvents()
    z = next(k for k, r in enumerate(w.tbl_linie.modell.zeilen) if str(r[0]) == "L9")
    w.meldungen.leeren()
    u0 = _undo_n(w)
    ok = w._linie_aendern(z, 4, "3, 4, x, 5")
    check("Linientabelle, Knoten „3, 4, x, 5“: nicht übernommen, die Meldung nennt „x“",
          ok is False and any("„x“" in t for t in w.meldungen.alle), str(w.meldungen.eintraege[-1:]))
    check("… die Linie behält ihre Knoten, kein Schritt zum Rückgängigmachen",
          list(w.model.lines["L9"].nodes) == [3, 4] and _undo_n(w) == u0, str(w.model.lines["L9"].nodes))
    ok = w._linie_aendern(z, 4, "3, 4, 5")
    check("… „3, 4, 5“ wird übernommen", ok is True and list(w.model.lines["L9"].nodes) == [3, 4, 5],
          str(w.model.lines["L9"].nodes))


# --------------------------------------------------------------------------
# F23
# --------------------------------------------------------------------------
def test_f23_profileditor():
    from PySide6 import QtWidgets
    from statik3d import zahlen as zl
    from statik3d.gui.profilmaske import ProfilEditor
    w, app = _fenster()
    pe = ProfilEditor(None)

    def aufbauen():
        pe.setze()
        pe.knoten_zufuegen(1, 0.0, 0.0)
        pe.knoten_zufuegen(2, 100.0, 0.0)
        pe.knoten_zufuegen(3, 100.0, 100.0)
        pe.element_zufuegen(1, 2, 10.0)
        pe.element_zufuegen(2, 3, 10.0)
        pe.aktualisieren()

    def ok_frei():
        return pe.knoepfe.button(QtWidgets.QDialogButtonBox.Ok).isEnabled()

    aufbauen()
    check("Vorbereitung: drei Knoten, zwei Elemente, OK frei", ok_frei() and sorted(pe.inhalt()["knoten"]) == [1, 2, 3])
    pe.tb_knoten.item(2, 0).setText("2,5")
    pe.aktualisieren()
    try:
        pe.inhalt()
        ok, mel = False, "keine Ausnahme"
    except zl.Eingabefehler as ex:
        ok, mel = "2,5" in str(ex), str(ex)
    check("Knotennummer „2,5“: Eingabefehler statt Knoten 2", ok, mel)
    check("… OK ist gesperrt, die Kennwerte zeigen die Meldung",
          not ok_frei() and "2,5" in pe.lbl_werte.text() and "ganze Zahl" in pe.lbl_werte.text(),
          pe.lbl_werte.text()[:80])
    pe.tb_knoten.item(2, 0).setText("3")
    pe.tb_elemente.item(1, 0).setText("1,9")
    pe.aktualisieren()
    check("Element „von“ „1,9“: OK gesperrt, die Meldung nennt „1,9“ (nicht still Element 1)",
          not ok_frei() and "1,9" in pe.lbl_werte.text(), pe.lbl_werte.text()[:80])
    pe.tb_elemente.item(1, 0).setText("2")
    pe.tb_elemente.item(1, 1).setText("3.5")
    pe.aktualisieren()
    check("Element „bis“ „3.5“: OK gesperrt", not ok_frei() and "3.5" in pe.lbl_werte.text(),
          pe.lbl_werte.text()[:80])
    pe.tb_elemente.item(1, 1).setText("3")
    pe.flaeche_zufuegen([1, 2, 3])
    pe.tb_flaechen.item(0, 0).setText("1, 2.5, 3")
    pe.aktualisieren()
    check("Flächenpolygon „1, 2.5, 3“: OK gesperrt (nicht still Knoten 2)",
          not ok_frei() and "2.5" in pe.lbl_werte.text(), pe.lbl_werte.text()[:80])
    pe.tb_flaechen.item(0, 0).setText("1, 2, 3")
    pe.tb_knoten.item(1, 0).setText("2,0")
    pe.aktualisieren()
    check("Gültige Eingaben: „2,0“ ist die Nummer 2, OK frei; Knoten 1, 2, 3",
          ok_frei() and sorted(pe.inhalt()["knoten"]) == [1, 2, 3], pe.lbl_werte.text()[:60])
    pe.deleteLater()


# --------------------------------------------------------------------------
# F24
# --------------------------------------------------------------------------
def _flaechen_modell(w, app):
    w.load_example("frame"); app.processEvents()
    m = w.model
    n0 = m.nn
    m.add_nodes(np.array([[20, 0, 0], [21, 0, 0], [21, 1, 0], [20, 1, 0.]]))
    for nm, (a, b) in {"Q1": (0, 1), "Q2": (1, 2), "Q3": (2, 3), "Q4": (3, 0)}.items():
        m.add_line(nm, [n0 + a, n0 + b])
    m.add_flaeche("FQ", ["Q1", "Q2", "Q3", "Q4"], teilung=[4, 4])
    for k in range(2, 5):
        m.add_flaeche(f"FQ{k}", ["Q1", "Q2", "Q3", "Q4"], teilung=[4, 4])
    m.add_koerper("VQ", ["FQ", "FQ2", "FQ3", "FQ4"], teilung=[2, 2, 2])
    w.refresh_all(); app.processEvents()


def test_f24_masken():
    w, app = _fenster()
    _flaechen_modell(w, app)
    for art, name, eingabe, soll_alt, soll_neu, lesen in (
            ("geoflaeche", "FQ", "0, -3", [4, 4], [3, 5], lambda: list(w.model.flaechen["FQ"].teilung)),
            ("geoflaeche", "FQ", "0", [4, 4], [2, 2], lambda: list(w.model.flaechen["FQ"].teilung)),
            ("geokoerper_einzeln", "VQ", "2, 0, 2", [2, 2, 2], [3, 4, 5], lambda: list(w.model.koerper["VQ"].teilung)),
            ("geokoerper_einzeln", "VQ", "-1", [2, 2, 2], [2, 2, 2], lambda: list(w.model.koerper["VQ"].teilung))):
        _maske_zu(w, app)
        mk = w._objektmaske(art, name)
        u0 = _undo_n(w)
        w.meldungen.leeren()
        mk.setzen("teilung", eingabe)
        ok = mk.anwenden(); app.processEvents()
        check(f"{art} Teilung „{eingabe}“: abgewiesen mit Hinweis (mindestens 1)",
              not ok and w.meldungen.hinweis_mit("Teilung", "1"), str(w.meldungen.eintraege[-1:]))
        check("… gespeichert wird nichts, kein Schritt zum Rückgängigmachen, die Maske behält die Eingabe",
              lesen() == soll_alt and _undo_n(w) == u0 and w.maskenrand.maske is mk
              and mk._felder["teilung"].text() == eingabe, f"{lesen()} {u0}->{_undo_n(w)}")
    _maske_zu(w, app)
    for art, name, eingabe, soll, lesen in (
            ("geoflaeche", "FQ", "3, 5", [3, 5], lambda: list(w.model.flaechen["FQ"].teilung)),
            ("geokoerper_einzeln", "VQ", "3, 4, 5", [3, 4, 5], lambda: list(w.model.koerper["VQ"].teilung))):
        mk = w._objektmaske(art, name)
        mk.setzen("teilung", eingabe)
        ok = mk.anwenden(); app.processEvents()
        check(f"{art} Teilung „{eingabe}“ wird übernommen", ok and lesen() == soll, str(lesen()))
        _maske_zu(w, app)


def test_f24_sammelmaske():
    w, app = _fenster()
    _flaechen_modell(w, app)
    for art, namen, feld, wert, lesen, vorher, nachher in (
            ("flaeche", ["FQ"], "tu", 0, lambda: list(w.model.flaechen["FQ"].teilung), [4, 4], [3, 4]),
            ("flaeche", ["FQ"], "tv", -2, lambda: list(w.model.flaechen["FQ"].teilung), [3, 4], [3, 6]),
            ("volumen", ["VQ"], "tz", 0, lambda: list(w.model.koerper["VQ"].teilung), [2, 2, 2], [2, 2, 7])):
        _maske_zu(w, app)
        w.sammelmaske(art, namen); app.processEvents()
        mk = w.maskenrand.maske
        u0 = _undo_n(w)
        w.meldungen.leeren()
        mk.setzen(feld, wert)
        ok = mk.anwenden(); app.processEvents()
        check(f"Sammelmaske {art}, {feld} = {wert}: abgewiesen mit Hinweis (mindestens 1)",
              not ok and w.meldungen.hinweis_mit("Teilung", "1") and not w.meldungen.fehler,
              str(w.meldungen.eintraege[-1:]))
        check("… nichts geschrieben, kein Schritt zum Rückgängigmachen, die Maske bleibt mit der Eingabe",
              lesen() == vorher and _undo_n(w) == u0 and w.maskenrand.maske is mk
              and mk._felder[feld].text() == str(wert), f"{lesen()} {u0}->{_undo_n(w)}")
        mk.setzen(feld, {"tu": 3, "tv": 6, "tz": 7}[feld])
        ok = mk.anwenden(); app.processEvents()
        check(f"… {feld} = {{3, 6, 7}} wird übernommen", ok and lesen() == nachher, str(lesen()))
    _maske_zu(w, app)


# --------------------------------------------------------------------------
# F41
# --------------------------------------------------------------------------
def test_f41_zahlenfeld():
    from statik3d.gui import zahlenfeld as zf
    w, app = _fenster()
    f = zf.Zahlenfeld(0.0)
    f.setText("33.000")
    f.setModified(True)
    check("„33.000“ getippt: offene Frage", f.offene_frage() and f.wert() == 33.0)
    f.bestaetigen()
    check("bestätigt: keine offene Frage mehr", not f.offene_frage())
    f.setText("33.000")
    check("derselbe Text noch einmal gesetzt (nichts geändert): bleibt bestätigt", not f.offene_frage())
    f.setText("5")
    f.setText("33.000")
    f.setModified(True)
    check("danach „5“, dann wieder „33.000“: es wird erneut gefragt", f.offene_frage(), repr(f.meldung()))
    f.bestaetigen()
    f.setText("33.0000")
    f.setText("33.000")
    check("bestätigt, über einen anderen (gültigen) Text zurück: wieder eine Frage", f.offene_frage())
    # schreibt das Programm bei blockierten Signalen, kommt textChanged nicht an
    f.bestaetigen()
    f.blockSignals(True)
    f.setText("7")
    f.setText("33.000")
    f.blockSignals(False)
    check("… auch wenn dazwischen bei blockierten Signalen geschrieben wurde", f.offene_frage())
    # Maske: Hauptknopf zweimal (erstes Mal fragt, zweites bestaetigt) und danach wieder Frage
    fz = w.ld[2]
    fz.setText("1.000")
    fz.setModified(True)
    a = fz.offene_frage()
    fz.bestaetigen()
    b = fz.offene_frage()
    fz.setText("5")
    fz.setText("1.000")
    fz.setModified(True)
    check("Register Lasten Fz: „1.000“ fragt, bestätigt fragt nicht, nach „5“ fragt „1.000“ wieder",
          a and not b and fz.offene_frage(), f"{a} {b} {fz.offene_frage()}")
    fz.setzen(0.0)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_f21_namenspruefung, test_f21_stellungsmaske, test_f21_gelenk_und_lager_namen,
              test_f21_situationsmaske, test_f21_umbenennen_in_maske, test_f22_nummernlisten,
              test_f22_masken, test_f22_tabelle, test_f23_profileditor, test_f24_masken,
              test_f24_sammelmaske, test_f41_zahlenfeld):
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
