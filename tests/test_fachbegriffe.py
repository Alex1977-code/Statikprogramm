"""
Fachbegriffe statt Schluessel (Teilpaket 11b des Oberflaechenplans, 03.10.2026).

Bis zum 03.10.2026 las der Anwender an der Oberflaeche die internen Schluessel
der Kombinationstypen und Umhuellenden: „Umhüllende ULS“, „Umhüllende SLS_CH“,
„Umhüllende CASES“ in Modellbaum, Ergebnisauswahl, Glasleiste und Kopfzeile,
„ULS“ und „SLS_FR“ als Typ in Maske, Dialog und Tabellen, „Umhuellende ULS:
12 Ergebnisse“ im Protokoll. Nur der Bericht hatte Klartexte. Jetzt kommen
sie fuer alle aus statik3d/begriffe.py. Geprueft wird:

* das Modul liefert je Kombinationstyp und je Umhuellende die kurze und die
  lange Form, unbekannte Schluessel bleiben, wie sie sind - ausser ein Name
  lautet wie ein Fachbegriff, dann bekommt er „(Ergebniskombination)“;
* der Bericht nimmt seine Texte aus dem Modul; verglichen mit dem Bericht
  von 68db45b (tests/daten/fachbegriffe_68db45b) aendern sich genau die
  erwarteten Zeilen (BERICHT_AENDERUNGEN), alle anderen nicht;
* nach einer Rechnung mit Kombinationen aller Typen zeigen Ergebnisbaum,
  Ergebnisauswahl, Glasleiste, Kopfzeile, Kombinationsmaske, Dialog,
  Tabellen und Protokoll die Klartexte und keinen Schluessel;
* die Daten dahinter sind unveraendert (("env", "ULS"), env:ULS,
  Combination.typ), eine Auswahl waehlt weiter das richtige Ergebnis, und
  „Übernehmen“ schreibt den Schluessel;
* die Weboberflaeche nennt die Klartexte, die Kennungen (env:ULS) bleiben;
  ohne node reisst die Pruefung, ausser STATIK3D_OHNE_NODE=1 (wie test_web);
* Nachbesserung nach der Gegenpruefung (03.10.2026): gleichlautende
  Umhuellende (F2), die lange Form am Zeiger der Ergebnisauswahl (F3), der
  Dialog Verformungsnachweis (L2), Kombinationsdialog und -maske mit FAT und
  unbekanntem Typ (L3), eine alte Ergebnisdatei (S2).

Aufruf:  python -m tests.test_fachbegriffe
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_fachbegriffe_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

#: Was der Anwender liest - die kurze Form je Kombinationstyp ...
KURZ_TYP = {"ULS": "GZT (STR/GEO)", "EQU": "GZT (EQU)", "ACC": "außergewöhnlich",
            "SLS_CH": "GZG charakteristisch", "SLS_FR": "GZG häufig",
            "SLS_QP": "GZG quasi-ständig", "FAT": "Ermüdung", "USER": "benutzerdefiniert"}
#: ... und je Umhuellende
KURZ_HUELLE = {"ULS": "Umhüllende GZT", "SLS_CH": "Umhüllende GZG charakteristisch",
               "SLS_FR": "Umhüllende GZG häufig", "SLS_QP": "Umhüllende GZG quasi-ständig",
               "FAT": "Umhüllende Ermüdung", "CASES": "Umhüllende Lastfälle"}

#: Die Texte des Berichts bis zum 03.10.2026 (report/html.py auf 68db45b,
#: COMBO_TYPES und ENVELOPE_NAMES) - sie bleiben, FAT kommt dazu
BERICHT_TYPEN_ALT = {"ULS": "GZT (STR/GEO)", "EQU": "GZT (EQU)", "ACC": "außergewöhnlich",
                     "SLS_CH": "GZG charakteristisch", "SLS_FR": "GZG häufig",
                     "SLS_QP": "GZG quasi-ständig", "USER": "benutzerdefiniert"}
BERICHT_HUELLEN_ALT = {"ULS": "Grenzzustand der Tragfähigkeit (GZT)",
                       "SLS_CH": "Gebrauchstauglichkeit, charakteristisch",
                       "SLS_FR": "Gebrauchstauglichkeit, häufig",
                       "SLS_QP": "Gebrauchstauglichkeit, quasi-ständig",
                       "CASES": "Lastfälle"}

#: Referenz: Modell, Ergebnisdatei und Bericht von 68db45b (vor 11b)
REFERENZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten", "fachbegriffe_68db45b")

#: Die Zeilen, die sich im Bericht der Referenz aendern duerfen: (vorher,
#: nachher) -> Anzahl. Entscheidung der Hauptsitzung (03.10.2026): der Bericht
#: benutzt dieselben Begriffe wie die Oberflaeche.
BERICHT_AENDERUNGEN = {
    # Typ FAT: Tabelle Kombinationen (K7 und die Ergebniskombination
    # „Ermüdung“), im Kapitel und im Tabelleneintrag „Kombinationen“
    ("FAT", "Ermüdung"): 4,
    ("Kombination (FAT)", "Kombination (Ermüdung)"): 1,
    ("4.3.7&nbsp;&nbsp;Kombination K7 (FAT): 1.6·LF1 + 0.5·LF2",
     "4.3.7&nbsp;&nbsp;Kombination K7 (Ermüdung): 1.6·LF1 + 0.5·LF2"): 1,
    # die Umhuellende der Ermuedung heisst wie an der Oberflaeche
    ("4.4.5&nbsp;&nbsp;Umhüllende FAT", "4.4.5&nbsp;&nbsp;Umhüllende Ermüdung"): 1,
    # Ergebniskombinationen, die wie Fachbegriffe heissen (F2)
    ("4.4.6&nbsp;&nbsp;Umhüllende GZT", "4.4.6&nbsp;&nbsp;Umhüllende GZT (Ergebniskombination)"): 1,
    ("4.4.7&nbsp;&nbsp;Umhüllende Ermüdung",
     "4.4.7&nbsp;&nbsp;Umhüllende Ermüdung (Ergebniskombination)"): 1,
    # Zeile „Zeigt“ der uebernommenen Bilder
    ("Umhüllende ULS", "Umhüllende GZT"): 1,
    ("Umhüllende GZT", "Umhüllende GZT (Ergebniskombination)"): 1,
    # Hinweis einer Tabelle ohne passendes Ergebnis
    ("Auflagerkräfte gibt es zu Lastfall oder Kombination (env:SLS_CH).",
     "Auflagerkräfte gibt es zu Lastfall oder Kombination (Umhüllende GZG charakteristisch)."): 1,
    # Tabelleneintrag „Kombinationen“: der Typ im Klartext
    ("ULS", "GZT (STR/GEO)"): 2,
    ("EQU", "GZT (EQU)"): 1,
    ("ACC", "außergewöhnlich"): 1,
    ("SLS_CH", "GZG charakteristisch"): 1,
    ("SLS_FR", "GZG häufig"): 1,
    ("SLS_QP", "GZG quasi-ständig"): 1,
    ("USER", "benutzerdefiniert"): 1,
}

SCHLUESSEL = ("ULS", "EQU", "ACC", "SLS_CH", "SLS_FR", "SLS_QP", "FAT", "USER", "CASES")
_SCHLUESSEL_RE = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(SCHLUESSEL) + r")(?![A-Za-z0-9_])")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def schluessel_in(text) -> list:
    """Die Schluessel, die in *text* sichtbar stehen. „GZT (EQU)“ ist der
    Fachbegriff aus DIN EN 1990 (Lagesicherheit), kein Schluessel."""
    return _SCHLUESSEL_RE.findall(str(text).replace("GZT (EQU)", ""))


# --------------------------------------------------------------------------
# Das Modul
# --------------------------------------------------------------------------
def test_modul_kurz_und_lang():
    from statik3d import begriffe as bg
    for k, kurz in KURZ_TYP.items():
        check(f"Typ {k}: kurz „{kurz}“", bg.typ_kurz(k) == kurz, repr(bg.typ_kurz(k)))
        lang = bg.typ_lang(k)
        check(f"Typ {k}: lang vorhanden, länger als kurz, ohne bloßen Schlüssel",
              len(lang) > len(kurz) and lang != k, repr(lang))
        check(f"Typ {k}: „{kurz}“ führt zurück auf den Schlüssel",
              bg.typ_schluessel(kurz) == k and bg.typ_schluessel(k) == k,
              repr(bg.typ_schluessel(kurz)))
    check("die kurzen Formen der Typen sind verschieden",
          len(set(KURZ_TYP.values())) == len(KURZ_TYP))
    check("Typ FAT heißt Ermüdung", bg.typ_kurz("FAT") == "Ermüdung")
    for k, kurz in KURZ_HUELLE.items():
        check(f"Umhüllende {k}: kurz „{kurz}“", bg.umhuellende_kurz(k) == kurz,
              repr(bg.umhuellende_kurz(k)))
        lang = bg.umhuellende_lang(k)
        check(f"Umhüllende {k}: lang vorhanden, ohne bloßen Schlüssel",
              bool(lang) and lang != k and not schluessel_in(lang), repr(lang))
    check("lange Form der Umhüllenden GZT: „Grenzzustand der Tragfähigkeit (GZT)“",
          bg.umhuellende_lang("ULS") == "Grenzzustand der Tragfähigkeit (GZT)")
    check("unbekannter Typ bleibt, wie er ist",
          bg.typ_kurz("XY") == "XY" and bg.typ_lang("XY") == "XY"
          and bg.typ_schluessel("quatsch") == "quatsch")
    check("unbekannte Umhüllende (Ergebniskombination EK3) heißt „Umhüllende EK3“",
          bg.umhuellende_kurz("EK3") == "Umhüllende EK3" and bg.umhuellende_lang("EK3") == "EK3")
    check("Spaltenverzeichnis TYP_KURZ = kurze Formen", bg.TYP_KURZ == KURZ_TYP, str(bg.TYP_KURZ))


def test_bericht_vorher_nachher():
    from statik3d.report import html as H
    from statik3d import begriffe as bg
    check("Bericht: die Typen wie vor dem 03.10.2026, dazu FAT = Ermüdung",
          H.COMBO_TYPES == dict(BERICHT_TYPEN_ALT, FAT="Ermüdung"), str(H.COMBO_TYPES))
    check("Bericht: die Umhüllenden wie vor dem 03.10.2026, dazu FAT = Ermüdung",
          H.ENVELOPE_NAMES == dict(BERICHT_HUELLEN_ALT, FAT="Ermüdung"), str(H.ENVELOPE_NAMES))
    check("Bericht nimmt die Typen aus dem gemeinsamen Modul",
          all(H.COMBO_TYPES[k] == bg.typ_kurz(k) for k in bg.KOMBINATIONSTYPEN))
    check("Bericht nimmt die Umhüllenden aus dem gemeinsamen Modul",
          all(H.ENVELOPE_NAMES[k] == bg.umhuellende_lang(k) for k in bg.UMHUELLENDE))
    # Bericht aus Modell und Ergebnisdatei von 68db45b, Zeile fuer Zeile
    import collections
    import difflib
    import runpy
    from statik3d.model import Model
    from statik3d import ergebnisse
    from statik3d.report import Report
    ref = runpy.run_path(os.path.join(REFERENZ, "erzeugen.py"))
    pfad = os.path.join(REFERENZ, "modell.json")
    m = Model.load(pfad)
    an = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m)
    neu = ref["bericht_text"](Report(m, an).html()).splitlines()
    with open(os.path.join(REFERENZ, "bericht.txt"), encoding="utf-8") as f:
        alt = f.read().splitlines()
    paare, sonst = collections.Counter(), []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, alt, neu, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if op == "replace" and i2 - i1 == j2 - j1:
            paare.update(zip(alt[i1:i2], neu[j1:j2]))
        else:
            sonst.append((op, alt[i1:i2][:3], neu[j1:j2][:3]))
    check("Bericht 68db45b → jetzt: keine Zeile eingefügt oder entfernt", not sonst, str(sonst[:3]))
    unerwartet = paare - collections.Counter(BERICHT_AENDERUNGEN)
    fehlt = collections.Counter(BERICHT_AENDERUNGEN) - paare
    check("… genau die erwarteten Zeilen geändert, keine anderen",
          not unerwartet and not fehlt,
          f"unerwartet {dict(unerwartet)}, fehlt {dict(fehlt)}")
    check("… und es sind alle %d" % sum(BERICHT_AENDERUNGEN.values()),
          sum(paare.values()) == sum(BERICHT_AENDERUNGEN.values()), str(sum(paare.values())))
    # ein ganzer Bericht mit Kombinationen aller Typen
    from statik3d import solver
    from statik3d.report import Report
    m = _modell_alle_typen()
    an = solver.solve_all(m, design=False, fatigue=False)
    html = Report(m, an).html()
    for t in ("Umhüllende Grenzzustand der Tragfähigkeit (GZT)",
              "Umhüllende Gebrauchstauglichkeit, charakteristisch",
              "(GZT (STR/GEO))", "(GZT (EQU))", "(außergewöhnlich)", "(benutzerdefiniert)"):
        check(f"Bericht schreibt „{t}“", t in html)


def test_berichtseintrag_quelle():
    from statik3d.model import Berichtseintrag
    e = Berichtseintrag("Bild 1", "env:ULS", "|u| Verschiebung", "kein Verlauf", 10.0, "")
    check("Berichtseintrag aus der Umhüllenden GZT nennt den Klartext",
          e.quelle_text() == "Umhüllende GZT" and e.bezug() == "Umhüllende GZT · |u| Verschiebung",
          f"{e.quelle_text()!r} / {e.bezug()!r}")
    check("… die Quelle bleibt der Schlüssel env:ULS", e.quelle == "env:ULS")
    e2 = Berichtseintrag("Bild 2", "env:EK3", "", "", 0.0, "")
    check("… eine Umhüllende mit Namen (EK3) bleibt „Umhüllende EK3“",
          e2.quelle_text() == "Umhüllende EK3", e2.quelle_text())
    e3 = Berichtseintrag("Bild 3", "env:GZT", "", "", 0.0, "")
    check("… eine Ergebniskombination „GZT“ heißt „Umhüllende GZT (Ergebniskombination)“",
          e3.quelle_text() == "Umhüllende GZT (Ergebniskombination)", e3.quelle_text())


def test_namensgleiche_ergebniskombination():
    """Befund F2 der Gegenpruefung: eine Ergebniskombination, die wie ein
    Fachbegriff heisst („GZT“, „Ermüdung“), ergab zwei gleichlautende
    Umhuellende. Jetzt traegt sie den Zusatz „(Ergebniskombination)“ - in
    Web, Ergebnisauswahl, Glasleiste, Baum und Bericht (Referenz oben)."""
    from statik3d import begriffe as bg, solver
    from statik3d.model import Combination
    from statik3d.web import server as S
    check("Modul: „GZT“ und „Ermüdung“ als Ergebniskombination mit Zusatz",
          bg.umhuellende_kurz("GZT") == "Umhüllende GZT (Ergebniskombination)"
          and bg.umhuellende_kurz("Ermüdung") == "Umhüllende Ermüdung (Ergebniskombination)"
          and bg.umhuellende_lang("Ermüdung") == "Ermüdung (Ergebniskombination)"
          and bg.umhuellende_lang("Lastfälle") == "Lastfälle (Ergebniskombination)",
          f"{bg.umhuellende_kurz('GZT')!r} {bg.umhuellende_lang('Ermüdung')!r}")
    w, app, _an = _gerechnet()
    m = w.model
    lf = list(m.load_cases)
    m.combinations["GZT"] = Combination("GZT", {}, "ULS",
                                        alternativen=[{lf[0]: 1.35}, {lf[0]: 1.35, lf[1]: 1.5}])
    m.combinations["Ermüdung"] = Combination("Ermüdung", {}, "FAT",
                                             alternativen=[{lf[0]: 1.0}, {lf[1]: 1.0}])
    w.refresh_all()
    app.processEvents()
    an = solver.solve_all(m, design=False)
    st = S.State(m)
    st.analysis = an
    texte = [e["label"] for e in S.result_entries(st) if e["id"].startswith("env:")]
    check("Web: alle Umhüllenden heißen verschieden", len(texte) == len(set(texte)), str(texte))
    check("… die Ergebniskombinationen mit Zusatz",
          "Umhüllende GZT (Ergebniskombination)" in texte
          and "Umhüllende Ermüdung (Ergebniskombination)" in texte
          and "Umhüllende GZT" in texte and "Umhüllende Ermüdung" in texte, str(texte))
    w._solve_done("all", an)
    app.processEvents()
    for titel, cb in (("Ergebnisauswahl", w.cb_result), ("Glasleiste", w.cb_lastwahl)):
        t = [cb.itemText(i) for i in range(cb.count())
             if cb.itemData(i) is not None and cb.itemData(i)[0] == "env"]
        check(f"{titel}: alle Umhüllenden heißen verschieden",
              len(t) == len(set(t)) and "Umhüllende GZT (Ergebniskombination)" in t, str(t))
    # Baum: Ergebnisse > Umhüllende
    from PySide6 import QtCore
    baum = [x.text(0) for x in QtWidgets_iter(w.baum)
            if x.parent() is not None and x.parent().data(0, QtCore.Qt.UserRole) == "ergebnisgruppe"
            and x.parent().text(0) == "Umhüllende"]
    check("Modellbaum: alle Umhüllenden heißen verschieden",
          len(baum) == len(set(baum)) and "Umhüllende Ermüdung (Ergebniskombination)" in baum, str(baum))
    del m.combinations["GZT"], m.combinations["Ermüdung"]
    _FENSTER.pop("an", None)        # das Fenster zeigt jetzt diese Rechnung


def test_verformungsdialog():
    """Befund L2: der Dialog Verformungsnachweis zeigte „charakteristisch
    (SLS_CH)“; jetzt die Texte aus begriffe.py, die Daten bleiben."""
    from PySide6 import QtCore
    from statik3d.gui.dialogs import VerformungsgrenzeDialog
    from statik3d.examples_lib import hall_frame_example
    w, app = _fenster()
    d = VerformungsgrenzeDialog(w, hall_frame_example(), knoten=[])
    texte = [d.cb_sit.itemText(i) for i in range(d.cb_sit.count())]
    daten = [d.cb_sit.itemData(i) for i in range(d.cb_sit.count())]
    check("Verformungsnachweis: Bemessungssituation im Klartext",
          texte == ["GZG charakteristisch", "GZG häufig", "GZG quasi-ständig", "alle GZG-Kombinationen"],
          str(texte))
    check("… die Daten bleiben die Schlüssel", daten == ["SLS_CH", "SLS_FR", "SLS_QP", ""], str(daten))
    check("… die lange Form am Zeiger",
          "charakteristische Kombination" in str(d.cb_sit.itemData(0, QtCore.Qt.ToolTipRole)),
          str(d.cb_sit.itemData(0, QtCore.Qt.ToolTipRole)))
    d.deleteLater()


def test_alte_ergebnisdatei():
    """Befund S2: eine Ergebnisdatei von vor 11b traegt die Namen
    „Umhuellende ULS“ mit; beim Laden heissen bekannte Schluessel wie an der
    Oberflaeche, Protokoll und Zusammenfassung nennen den Klartext."""
    from statik3d.model import Model
    from statik3d import ergebnisse
    tmp = tempfile.mkdtemp(prefix="statik3d_fachbegriffe_datei_")
    for n in ("modell.json", "modell.ergebnisse"):
        shutil.copy(os.path.join(REFERENZ, n), os.path.join(tmp, n))
    pfad = os.path.join(tmp, "modell.json")
    m = Model.load(pfad)
    an = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m)
    namen = {k: v.name for k, v in an.envelopes.items()}
    check("alte Datei: bekannte Umhüllende heißen wie an der Oberfläche",
          all(namen[k] == KURZ_HUELLE[k] for k in namen if k in KURZ_HUELLE)
          and {"ULS", "FAT"} <= set(namen), str(namen))
    check("… die Umhüllenden der Ergebniskombinationen behalten ihren Namen",
          namen.get("GZT") == "GZT" and namen.get("Ermüdung") == "Ermüdung", str(namen))
    w, app = _fenster()
    ok = w.modell_laden(pfad, fragen=False)     # beginnt ein neues Protokoll
    for _ in range(4):
        app.processEvents()
    log = w.log.toPlainText().splitlines()
    umh = [z for z in log if z.startswith(("Umhüllende", "Umhuellende"))]
    check("alte Datei im Fenster geladen, Protokoll nennt „Umhüllende GZT: … Ergebnisse“",
          ok and any(z.startswith("Umhüllende GZT: ") for z in umh), str(umh[:3]))
    check("… keine Umhüllende mit Schlüssel im Protokoll und in der Zusammenfassung",
          not any(schluessel_in(z) for z in umh)
          and not schluessel_in(" ".join(z for z in w.txt_summary.toPlainText().splitlines()
                                         if z.startswith("Umh"))),
          str([z for z in umh if schluessel_in(z)]))
    _FENSTER.pop("an", None)


# --------------------------------------------------------------------------
# Oberflaeche
# --------------------------------------------------------------------------
def _modell_alle_typen(m=None):
    """Rahmen mit Wind, automatischen Kombinationen (GZT, GZG) und je einer
    Handkombination EQU, ACC, FAT, USER - Namen ohne Schluessel darin."""
    from statik3d import mesher
    from statik3d.combinations import generate_combinations
    from statik3d.examples_lib import frame_example
    m = m if m is not None else frame_example()
    if "W" not in m.load_cases:
        m.add_load_case("W", "W", "Wind von links", activate=False)
        n = int(mesher.select_nodes(m, xmin=-1e-6, xmax=1e-6, zmin=4 - 1e-6)[0])
        m.load_node(n, Fx=8000.0, case="W")
    generate_combinations(m)
    lf = list(m.load_cases)
    for name, typ in (("H1", "EQU"), ("H2", "ACC"), ("H3", "FAT"), ("H4", "USER")):
        m.add_combination(name, {lf[0]: 1.0, lf[1]: 0.5}, typ, "von Hand")
    return m


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
    w.fehler_liste = []
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b): die
    # Liste bekommt beide, w.meldungen wertet sie getrennt aus
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _gerechnet():
    """Fenster mit gerechnetem Rahmen (alle Kombinationstypen)."""
    if "an" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"], _FENSTER["an"]
    from statik3d import solver
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    _modell_alle_typen(w.model)
    w.refresh_all(); app.processEvents()
    _FENSTER["log0"] = len(w.log.toPlainText().splitlines())
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    _FENSTER["an"] = an
    return w, app, an


def _index(cb, daten) -> int:
    for i in range(cb.count()):
        d = cb.itemData(i)
        if d is not None and tuple(d) == tuple(daten):
            return i
    return -1


def test_ergebnisbaum_und_auswahl():
    from PySide6 import QtCore
    w, app, an = _gerechnet()
    erwartet = [k for k in an.envelopes]
    check("die Rechnung bildet die Umhüllenden GZT, GZG und Ermüdung",
          {"ULS", "SLS_CH", "FAT"} <= set(erwartet), str(erwartet))
    # -- Ergebnisbaum ---------------------------------------------------
    gruppe = None
    it = QtWidgets_iter(w.baum)
    for x in it:
        if x.data(0, QtCore.Qt.UserRole) == "ergebnisgruppe" and x.text(0) == "Umhüllende":
            gruppe = x
            break
    kinder = [gruppe.child(i) for i in range(gruppe.childCount())] if gruppe is not None else []
    texte = [k.text(0) for k in kinder]
    schl = [k.data(0, QtCore.Qt.UserRole + 1) for k in kinder]
    check("Ergebnisbaum: Umhüllende im Klartext",
          texte == [KURZ_HUELLE[k] for k in erwartet], str(texte))
    check("Ergebnisbaum: kein Schlüssel sichtbar (Text und Hinweis)",
          not any(schluessel_in(k.text(0)) or schluessel_in(k.toolTip(0)) for k in kinder),
          str([(k.text(0), k.toolTip(0)) for k in kinder]))
    check("Ergebnisbaum: die Schlüssel dahinter bleiben env:ULS …",
          schl == [f"env:{k}" for k in erwartet], str(schl))
    # -- Ergebnisauswahl rechts ------------------------------------------
    cbr = w.cb_result
    huellen = [(cbr.itemText(i), cbr.itemData(i)) for i in range(cbr.count())
               if (cbr.itemData(i) or ("",))[0] == "env"]
    check("Ergebnisauswahl: Umhüllende im Klartext",
          [t for t, _d in huellen] == [KURZ_HUELLE[k] for k in erwartet], str(huellen))
    check("Ergebnisauswahl: die Daten bleiben (\"env\", Schlüssel)",
          [tuple(d) for _t, d in huellen] == [("env", k) for k in erwartet], str(huellen))
    alle = [cbr.itemText(i) for i in range(cbr.count())]
    check("Ergebnisauswahl: kein Eintrag zeigt einen Schlüssel",
          not any(schluessel_in(t) for t in alle), str([t for t in alle if schluessel_in(t)]))
    # Befund F3: _aufklappliste_breit ueberschrieb die lange Form mit dem Namen
    tips = {d[1]: cbr.itemData(i, QtCore.Qt.ToolTipRole)
            for i in range(cbr.count()) for d in [cbr.itemData(i)] if d and d[0] == "env"}
    check("Ergebnisauswahl: am Zeiger Name und lange Form",
          tips.get("ULS") == "Umhüllende GZT\nGrenzzustand der Tragfähigkeit (GZT)"
          and tips.get("SLS_CH") == "Umhüllende GZG charakteristisch\nGebrauchstauglichkeit, charakteristisch",
          str(tips))
    i = _index(cbr, ("env", "SLS_CH"))
    cbr.setCurrentIndex(i); app.processEvents()
    check("Auswahl „Umhüllende GZG charakteristisch“ wählt die Umhüllende SLS_CH",
          w.current_result() is an.envelopes.get("SLS_CH"), cbr.currentText())
    zeilen = list(getattr(w, "_kopfzeile_zeilen", []) or [])
    check("Kopfzeile nennt „Umhüllende GZG charakteristisch“",
          bool(zeilen) and zeilen[0] == "Umhüllende GZG charakteristisch", str(zeilen[:2]))
    check("Kopfzeile ohne Schlüssel", not any(schluessel_in(z) for z in zeilen), str(zeilen))
    # -- Glasleiste ------------------------------------------------------
    cbl = w.cb_lastwahl
    check("Glasleiste steht auf derselben Umhüllenden",
          cbl.currentData() is not None and tuple(cbl.currentData()) == ("env", "SLS_CH")
          and cbl.currentText() == "Umhüllende GZG charakteristisch",
          f"{cbl.currentText()} {cbl.currentData()}")
    gl = [(cbl.itemText(i), cbl.itemData(i)) for i in range(cbl.count())]
    check("Glasleiste: Umhüllende im Klartext, Daten unverändert",
          [(t, tuple(d)) for t, d in gl if d is not None and d[0] == "env"]
          == [(KURZ_HUELLE[k], ("env", k)) for k in erwartet], str(gl))
    check("Glasleiste: kein Eintrag zeigt einen Schlüssel",
          not any(schluessel_in(t) for t, _d in gl), str([t for t, _d in gl if schluessel_in(t)]))
    j = _index(cbl, ("env", "FAT"))
    cbl.setCurrentIndex(j); app.processEvents()
    check("Wahl „Umhüllende Ermüdung“ in der Glasleiste wählt die Umhüllende FAT",
          w.current_result() is an.envelopes.get("FAT")
          and tuple(cbr.currentData()) == ("env", "FAT"), cbr.currentText())
    # -- Protokoll -------------------------------------------------------
    log = w.log.toPlainText().splitlines()[_FENSTER.get("log0", 0):]
    umh = [z for z in log if z.startswith(("Umhüllende", "Umhuellende"))]
    check("Protokoll nach der Rechnung: „Umhüllende GZT: … Ergebnisse“",
          any(z.startswith("Umhüllende GZT: ") for z in umh), str(umh))
    check("Protokoll: keine Umhüllende mit Schlüssel", not any(schluessel_in(z) for z in umh), str(umh))


def QtWidgets_iter(baum):
    """Alle Eintraege eines QTreeWidget."""
    from PySide6 import QtWidgets
    it = QtWidgets.QTreeWidgetItemIterator(baum)
    while it.value() is not None:
        yield it.value()
        it += 1


def test_kombinationsmaske():
    w, app, an = _gerechnet()
    m = w.model
    name = next(n for n, c in m.combinations.items() if c.typ == "SLS_FR")
    w._objektmaske("kombination", name); app.processEvents()
    mk = w.maskenrand.maske
    cb = (mk._felder if mk is not None else {}).get("typ")
    texte = [cb.itemText(i) for i in range(cb.count())] if cb is not None else []
    check("Kombinationsmaske: Typ als Klartext zur Wahl",
          texte == list(KURZ_TYP.values()), str(texte))
    check("Kombinationsmaske: der Typ der Kombination steht als „GZG häufig“",
          cb is not None and cb.currentText() == "GZG häufig", cb.currentText() if cb else "-")
    if cb is None:
        return
    mk.anwenden(); app.processEvents()
    check("„Übernehmen“ ohne Änderung: der Typ bleibt der Schlüssel SLS_FR",
          m.combinations[name].typ == "SLS_FR", repr(m.combinations[name].typ))
    w._objektmaske("kombination", name); app.processEvents()
    mk = w.maskenrand.maske
    mk._felder["typ"].setCurrentText("Ermüdung"); app.processEvents()
    mk.anwenden(); app.processEvents()
    check("„Ermüdung“ gewählt und übernommen: Combination.typ = FAT",
          m.combinations[name].typ == "FAT", repr(m.combinations[name].typ))
    m.combinations[name].typ = "SLS_FR"
    w.refresh_all(); app.processEvents()
    # der Zweig „Kombinationen“: die Typen als Angabe
    w._objektmaske("kombinationen", ""); app.processEvents()
    mk = w.maskenrand.maske
    typen = mk._felder.get("typen") if mk is not None else None
    text = typen.text() if typen is not None else ""
    check("Zweig Kombinationen: „Typen“ im Klartext",
          text and not schluessel_in(text) and "GZG häufig" in text and "Ermüdung" in text, text)
    if mk is not None:
        mk.schliessen(); app.processEvents()


def test_kombinationsdialog():
    from statik3d.gui.dialogs import CombinationDialog
    w, app, an = _gerechnet()
    m = w.model
    name = next(n for n, c in m.combinations.items() if c.typ == "SLS_QP")
    d = CombinationDialog(w, m, m.combinations[name])
    texte = [d.typ.itemText(i) for i in range(d.typ.count())]
    check("Kombinationsdialog: Typ als Klartext", not any(schluessel_in(t) for t in texte)
          and "GZG quasi-ständig" in texte, str(texte))
    check("… steht auf „GZG quasi-ständig“", d.typ.currentText() == "GZG quasi-ständig",
          d.typ.currentText())
    check("… das Ergebnis behält den Schlüssel SLS_QP", d.result().typ == "SLS_QP", d.result().typ)
    d.typ.setCurrentIndex(d.typ.findText("GZT (EQU)"))
    check("… „GZT (EQU)“ gewählt ergibt den Schlüssel EQU", d.result().typ == "EQU", d.result().typ)
    d.deleteLater()
    # Befund L3: aus FAT und aus einem unbekannten Typ wurde beim OK still ULS
    texte = None
    for typ in ("FAT", "XYZ"):
        c = m.combinations.get("H3")
        alt = c.typ
        c.typ = typ
        d = CombinationDialog(w, m, c)
        texte = [d.typ.itemText(i) for i in range(d.typ.count())]
        check(f"Kombinationsdialog mit Typ {typ}: steht auf „{KURZ_TYP.get(typ, typ)}“, "
              f"OK behält {typ}",
              d.typ.currentText() == KURZ_TYP.get(typ, typ) and d.result().typ == typ,
              f"{d.typ.currentText()!r} -> {d.result().typ!r}")
        d.deleteLater()
        c.typ = alt
    check("… der Dialog bietet dieselben Typen wie die Maske, auch Ermüdung",
          texte[:len(KURZ_TYP)] == list(KURZ_TYP.values()), str(texte))
    # dasselbe in der Maske: ein unbekannter Typ bleibt beim Übernehmen
    m.combinations["H3"].typ = "XYZ"
    w._objektmaske("kombination", "H3"); app.processEvents()
    mk = w.maskenrand.maske
    cb = mk._felder.get("typ")
    check("Kombinationsmaske mit unbekanntem Typ XYZ: steht auf „XYZ“",
          cb is not None and cb.currentText() == "XYZ", cb.currentText() if cb else "-")
    mk.anwenden(); app.processEvents()
    check("… „Übernehmen“ ohne Änderung behält XYZ", m.combinations["H3"].typ == "XYZ",
          m.combinations["H3"].typ)
    m.combinations["H3"].typ = "FAT"
    w.refresh_all(); app.processEvents()


def test_tabellen():
    from PySide6 import QtCore
    w, app, an = _gerechnet()
    m = w.model
    w.refresh_all(); app.processEvents()
    mod = w.tbl_kombi.modell
    namen = list(m.combinations)
    sp = [mod.data(mod.index(r, 1), QtCore.Qt.DisplayRole) for r in range(mod.rowCount())]
    check("Tabelle Kombinationen: Typ im Klartext",
          sp == [KURZ_TYP[m.combinations[n].typ] for n in namen], str(sp))
    check("… die Zeilen behalten den Schlüssel",
          [z[1] for z in mod.zeilen] == [m.combinations[n].typ for n in namen],
          str([z[1] for z in mod.zeilen]))
    t = w.tbl_comb
    sp2 = [t.item(r, 1).text() for r in range(t.rowCount())]
    check("Register Lastfälle, Liste Kombinationen: Typ im Klartext",
          sp2 == [KURZ_TYP[m.combinations[n].typ] for n in namen], str(sp2))


def test_web():
    from statik3d import solver
    from statik3d.web import server as S
    m = _modell_alle_typen()
    st = S.State(m)
    st.analysis = solver.solve_all(m, design=False)
    eintr = S.result_entries(st)
    huellen = [e for e in eintr if e["id"].startswith("env:")]
    check("Web: Umhüllende im Klartext, Kennung env:Schlüssel",
          [(e["id"], e["label"]) for e in huellen]
          == [(f"env:{k}", KURZ_HUELLE[k]) for k in st.analysis.envelopes], str(huellen))
    check("Web: kein Eintrag der Ergebnisliste zeigt einen Schlüssel",
          not any(schluessel_in(e["label"]) for e in eintr),
          str([e["label"] for e in eintr if schluessel_in(e["label"])]))
    zustand = json.loads(json.dumps(S.state_summary(st), default=str))
    ko = zustand["combinations"]
    check("Web: Kombinationen tragen den Schlüssel (typ) und den Klartext (typ_text)",
          all(c["typ"] == m.combinations[c["name"]].typ
              and c.get("typ_text") == KURZ_TYP[c["typ"]] for c in ko), str(ko[:2]))
    check("Web: die Typen zur Wahl kommen mit Klartext",
          [tuple(x[:2]) for x in zustand.get("kombinationstypen", [])] == list(KURZ_TYP.items()),
          str(zustand.get("kombinationstypen")))
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        # wie test_web (_ohne_node): ohne node reisst die Pruefung, ausser
        # STATIK3D_OHNE_NODE=1 erlaubt das Auslassen ausdruecklich
        if os.environ.get("STATIK3D_OHNE_NODE") == "1":
            print("SKIP Darstellung der Weboberflaeche: node fehlt (STATIK3D_OHNE_NODE=1)")
        else:
            check("Web: Darstellung geprüft (node vorhanden)", False,
                  "node nicht gefunden - node installieren oder STATIK3D_OHNE_NODE=1 setzen")
        return
    result = json.loads(json.dumps(S.result_payload(st, "env:ULS"), default=str))
    hier = os.path.dirname(os.path.abspath(__file__))
    app_js = os.path.join(os.path.dirname(hier), "statik3d", "web", "static", "app.js")
    skript = r"""
'use strict';
const fs = require('fs'); const vm = require('vm');
const [appPfad, datenPfad] = process.argv.slice(2);
const daten = JSON.parse(fs.readFileSync(datenPfad, 'utf8'));
function element(id) { return {id, innerHTML: '', textContent: '', value: '', hidden: false,
  dataset: {}, style: {}, className: '', tagName: 'DIV', scrollTop: 0, files: [],
  classList: {add() {}, remove() {}, toggle() {}, contains() { return false; }, replace() {}},
  addEventListener() {}, removeEventListener() {}, appendChild() {}, remove() {},
  setPointerCapture() {}, getBoundingClientRect() { return {width: 800, height: 600, left: 0, top: 0}; },
  querySelector() { return null; }, querySelectorAll() { return []; }, closest() { return null; },
  requestSubmit() {}, focus() {}, click() {}}; }
const knoten = {};
const doc = {body: element('body'), addEventListener() {}, createElement: () => element('neu'),
  querySelector: s => (knoten[s] = knoten[s] || element(s)), querySelectorAll: () => []};
const ctx = {document: doc, console,
  window: {innerWidth: 1440, innerHeight: 900, addEventListener() {}, devicePixelRatio: 1},
  location: {search: '', host: 'test', reload() {}}, localStorage: {getItem: () => null, setItem() {}},
  fetch: () => Promise.reject(new Error('kein Netz')), setTimeout: () => 0, clearTimeout() {},
  setInterval: () => 0, ResizeObserver: function () { this.observe = () => {}; },
  requestAnimationFrame: () => 0, encodeURIComponent, Math, JSON, Set, Map, Number, Array,
  Object, String, Date};
ctx.globalThis = ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(appPfad, 'utf8'), ctx, {filename: 'app.js'});
ctx.__d = daten;
vm.runInContext('S.state = __d.state; S.entries = __d.entries; S.result = __d.result; '
  + 'view = {opts: {}, draw(){}, resize(){}, fit(){}, setGeometry(){}};', ctx);
const aus = {};
for (const fn of ['renderLasten', 'renderErgebnisse', 'renderRechnen']) {
  try { aus[fn] = vm.runInContext(fn + '()', ctx); } catch (e) { aus[fn] = 'FEHLER ' + e.message; }
}
console.log(JSON.stringify(aus));
"""
    with tempfile.TemporaryDirectory() as tmp:
        js = os.path.join(tmp, "zeigen.js")
        with open(js, "w", encoding="utf-8") as f:
            f.write(skript)
        pfad = os.path.join(tmp, "daten.json")
        with open(pfad, "w", encoding="utf-8") as f:
            json.dump({"state": zustand, "entries": eintr, "result": result}, f)
        p = subprocess.run([node, js, app_js, pfad], capture_output=True, text=True,
                           timeout=120, encoding="utf-8")
    try:
        aus = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:        # noqa: BLE001
        aus = {}
    import html as _html

    def sichtbar(h):
        # was im Browser zu lesen ist: ohne Tags und Attribute
        return _html.unescape(re.sub(r"<[^>]*>", " ", str(h or "")))

    # im Register Lasten ab den Kombinationen (davor steht die Auswahl der
    # Einwirkungskategorie mit „FAT“ - die Kategorie eines Lastfalls, kein
    # Kombinationstyp); dahinter die Zustaende der Ermuedungslasten
    roh = str(aus.get("renderLasten") or "")
    lasten = sichtbar(roh[roh.find("<summary>Kombinationen"):]) if "<summary>Kombinationen" in roh else ""
    erg, rech = (sichtbar(aus.get(k)) for k in ("renderErgebnisse", "renderRechnen"))
    check("Web, Register Lasten: Kombinationen mit Typ im Klartext",
          "GZG häufig" in lasten and "Ermüdung" in lasten and "GZT (STR/GEO)" in lasten,
          (p.stderr or lasten)[-300:])
    check("Web, Register Lasten: kein Schlüssel sichtbar", not schluessel_in(lasten),
          str(schluessel_in(lasten)))
    check("Web, Register Ergebnisse: Auswahl und Zusammenfassung im Klartext",
          "Umhüllende GZT" in erg and "Umhüllende GZG charakteristisch" in erg,
          (p.stderr or erg)[-300:])
    check("Web, Register Ergebnisse: kein Schlüssel sichtbar", not schluessel_in(erg),
          str(schluessel_in(erg)))
    check("Web, Register Rechnen: letzte Analyse ohne Schlüssel",
          "Umhüllende GZT" in rech and not schluessel_in(rech), str(schluessel_in(rech)))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_modul_kurz_und_lang, test_bericht_vorher_nachher, test_berichtseintrag_quelle,
              test_ergebnisbaum_und_auswahl, test_kombinationsmaske, test_kombinationsdialog,
              test_tabellen, test_web, test_namensgleiche_ergebniskombination,
              test_verformungsdialog, test_alte_ergebnisdatei):
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
    sys.stderr.flush()
    # ohne Aufraeumen der Fenster beenden - keine Rueckfrage beim Schliessen
    os._exit(code)
