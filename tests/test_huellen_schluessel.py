"""
Schluessel der Umhuellenden: nichts wird still ueberschrieben (Befund R1 der
Gegenpruefung von 11b, 04.10.2026).

Bis zum 04.10.2026 legte solve_all die Umhuellenden ihrer Art unter den
Schluesseln ULS, SLS_CH, SLS_FR, SLS_QP, FAT und CASES ab und danach die
Umhuellende jeder RFEM-Ergebniskombination unter ihrem Namen. Hiess eine
Ergebniskombination genau wie ein solcher Schluessel („ULS“, „FAT“),
ueberschrieb sie still die Umhuellende ihrer Art: die Umhuellende GZT war weg,
und Glasleiste, Tabellen, Bild, Bericht und Web zeigten unter „Umhüllende GZT“
die einer einzelnen Ergebniskombination.

Die Abnahme (vorher festgelegt, R1a bis R1f):

* R1a - Ergebniskombination „ULS“ (Typ GZT): die Umhuellende GZT umfasst alle
  GZT-Ergebnisse samt Alternativen, die Umhuellende der Ergebniskombination
  gibt es ebenfalls; beide stimmen mit einer unabhaengigen Auswertung aus den
  Einzelergebnissen ueberein (Min, Max und Herkunft per numpy gestapelt,
  bitgleich);
* R1b - dasselbe fuer FAT und jeden uebrigen Schluessel, den der Code kennt
  (SLS_CH, SLS_FR, SLS_QP, CASES), dazu der Schluessel eines unbekannten Typs
  aus einer Quelldatei;
* R1c - Ergebnisdatei speichern und laden: beide kommen unterscheidbar
  zurueck; eine mit 6791f9f geschriebene Datei ohne Kollision laedt
  unveraendert; eine mit Kollision nennt, was fehlt;
* R1d - Ergebnisauswahl oben rechts, unten (10c), Glasleiste, Modellbaum,
  Bericht und Web fuehren beide mit verschiedenem Namen, keine Zeile doppelt;
* R1e - Ermuedung aus einer FAT-Umhuellenden ohne Kollision: D und
  massgebende Stelle bitgleich mit 6791f9f;
* R1f - Beispiele frame, truss, hall, gate, contact: Lastfaelle,
  Kombinationen, Umhuellende, EC3 und Ermuedung bitgleich mit 6791f9f.

Nachbesserung nach der Gegenpruefung von dc80e1f (04.10.2026, R1g bis R1j):

* R1g (F1) - die Spalte Ausnutzung gehoert nicht zur Umhuellenden eines
  unbekannten Typs „XYZ“, wohl aber zur Umhuellenden der Ergebniskombination
  „XYZ“ vom Typ GZT;
* R1h (L1) - eine alte Ergebnisdatei, deren Ergebniskombination „ULS“ nach
  der Rechnung umbenannt oder geloescht wurde, wird erkannt und umgehaengt;
  bei den zwoelf Dateien der Gegenpruefung keine Fehlerkennung (Lesung wie
  dc80e1f);
* R1i - Sicherheitsnetz bis R2: Lastfall und Kombination gleichen Namens und
  eine Kombination „EK1 [2]“ neben der Ergebniskombination EK1 sind FEHLER der
  Modellpruefung; solve_all und „Berechnen“ starten nicht; die Beispiele
  melden nichts;
* R1j (S2, S3) - die Hinweiszeile nennt nur Umhuellende der Rechnung, das
  Protokoll jede Umhuellende mit ihrem Anzeigenamen wie Liste und Baum.

Die Referenz von 6791f9f liegt in tests/daten/huellen_schluessel_6791f9f
(erzeugen.py dort; Fingerabdruck = Hash der Bytes je Ergebnisfeld).

Aufruf:  python -m tests.test_huellen_schluessel
"""
import json
import os
import re
import runpy
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_huellen_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}

HIER = os.path.dirname(os.path.abspath(__file__))
REFERENZ = os.path.join(HIER, "daten", "huellen_schluessel_6791f9f")
_REF = {}

#: Typen, die solve_all in der Umhuellenden GZT (Schluessel ULS) sammelt
GZT_GRUPPE = ("ULS", "EQU", "ACC", "USER")
KOMPONENTEN = ("N", "Vy", "Vz", "Mt", "My", "Mz")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def ref():
    """Die Hilfen aus erzeugen.py (Modelle, Fingerabdruck) - dieselben, mit
    denen die Referenz auf 6791f9f entstand."""
    if not _REF:
        _REF.update(runpy.run_path(os.path.join(REFERENZ, "erzeugen.py")))
    return _REF


def _json(name):
    with open(os.path.join(REFERENZ, name), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Unabhaengige Auswertung: Einzelergebnisse stapeln, Min/Max per numpy
# --------------------------------------------------------------------------
def _art(typ) -> str:
    return "ULS" if typ in GZT_GRUPPE else typ


def _alternativen(m, an, c) -> list:
    """[(Name, Results)] der Alternativen einer Ergebniskombination: ein
    Lastfall mit Faktor 1 ist dessen Ergebnis, jede andere die Ueberlagerung
    (solve_combination), Name „EK [k]“ - so definiert es solver.py."""
    from statik3d import solver
    from statik3d.model import Combination
    aus = []
    for k, alt in enumerate(c.alternativen, 1):
        teile = {a: f for a, f in alt.items() if f}
        if not teile:
            continue
        if len(teile) == 1 and abs(next(iter(teile.values())) - 1.0) < 1e-12:
            lc = next(iter(teile))
            aus.append((lc, an.cases[lc]))
            continue
        name = f"{c.name} [{k}]"
        aus.append((name, solver.solve_combination(m, Combination(name, teile, c.typ), an.cases)))
    return aus


def _erwartet_art(m, an, art) -> list:
    """Was in die Umhuellende einer Art gehoert: die gewoehnlichen Kombinationen
    dieser Art (Reihenfolge der Ergebnisse), dann die Alternativen jeder
    Ergebniskombination dieser Art (Reihenfolge des Modells)."""
    liste = [(n, r) for n, r in an.combinations.items() if _art(m.combinations[n].typ) == art]
    for c in m.combinations.values():
        if c.ist_umhuellende and _art(c.typ) == art:
            liste += _alternativen(m, an, c)
    return liste


def _gleich(env, liste) -> tuple:
    """(True, "") wenn die Umhuellende bitgleich mit Min, Max und Herkunft der
    gestapelten Einzelergebnisse ist - sonst (False, was abweicht)."""
    namen = [n for n, _r in liste]
    if list(env.names) != namen:
        return False, f"names {list(env.names)} statt {namen}"
    res = [r for _n, r in liste]
    U = np.stack([np.asarray(r.u, float) for r in res])
    R = np.stack([np.asarray(r.reactions, float) for r in res])
    VM = np.stack([np.nan_to_num(np.asarray(r.node_vm, float)) for r in res])
    abw = []
    for feld, ist, soll in (("u_min", env.u_min, U.min(0)), ("u_max", env.u_max, U.max(0)),
                            ("u_min_src", env.u_min_src, U.argmin(0)),
                            ("u_max_src", env.u_max_src, U.argmax(0)),
                            ("r_min", env.r_min, R.min(0)), ("r_max", env.r_max, R.max(0)),
                            ("node_vm_max", env.node_vm_max, VM.max(0)),
                            ("umag_max", env.umag_max, np.linalg.norm(U[:, :, :3], axis=2).max(0))):
        if not np.array_equal(np.asarray(ist), np.asarray(soll)):
            abw.append(feld)
    n = env.n_stations
    st = [r.stations(n) for r in res]
    for i in sorted(set().union(*[set(s) for s in st])):
        d = env.beam.get(i)
        if d is None:
            abw.append(f"Stab {i} fehlt")
            continue
        for k in KOMPONENTEN:
            W = np.stack([np.asarray(s[i][k], float) if i in s else np.zeros(n) for s in st])
            if not (np.array_equal(d[k][0], W.min(0)) and np.array_equal(d[k][1], W.max(0))
                    and np.array_equal(d[k][2], W.argmin(0)) and np.array_equal(d[k][3], W.argmax(0))):
                abw.append(f"Stab {i} {k}")
    return not abw, ("bitgleich" if not abw else "Abweichung: " + ", ".join(abw[:6]))


def _ek_huellen(an, m, ek) -> list:
    """Die Schluessel der Umhuellenden, die genau die Alternativen der
    Ergebniskombination *ek* tragen - ausser der Umhuellenden ihrer Art: hat
    die Art sonst nichts (nur Lastfaelle und diese Ergebniskombination), traegt
    sie dieselben Namen."""
    c = m.combinations[ek]
    namen = [n for n, _r in _alternativen(m, an, c)]
    return [k for k, e in an.envelopes.items() if list(e.names) == namen and k != _art(c.typ)]


def _beide_pruefen(zeile, m, an, ek, art, art_da=True) -> None:
    """Die Pruefungen R1a/R1b fuer eine Ergebniskombination *ek*, deren Name
    ein Schluessel ist, und die Umhuellende ihrer Art *art*."""
    from statik3d import begriffe as bg
    texte = [bg.umhuellende_kurz(k) for k in an.envelopes]
    art_text = bg.umhuellende_kurz(art) if art in bg.UMHUELLENDE else f"Umhüllende {art}"
    if art_da:
        env = an.envelopes.get(art)
        soll = _erwartet_art(m, an, art)
        ok, detail = _gleich(env, soll) if env is not None else (False, "fehlt")
        check(f"{zeile}: „{art_text}“ da und umfasst alle Ergebnisse ihrer Art samt Alternativen",
              env is not None and list(env.names) == [n for n, _r in soll]
              and texte.count(art_text) == 1, f"{list(env.names) if env is not None else None}")
        check(f"{zeile}: „{art_text}“ = unabhängige Auswertung der Einzelergebnisse", ok, detail)
    else:
        # CASES: ohne gewoehnliche Kombinationen gibt es keine Umhuellende der
        # Lastfaelle, aber auch keine Ergebniskombination, die so heissen darf
        check(f"{zeile}: keine Umhüllende heißt „{art_text}“",
              art_text not in texte, str(texte))
        env_art = an.envelopes.get("ULS")
        soll = _erwartet_art(m, an, _art(m.combinations[ek].typ))
        ok, detail = _gleich(env_art, soll) if env_art is not None else (False, "fehlt")
        check(f"{zeile}: die Alternativen stehen in der „Umhüllende GZT“", ok, detail)
    ks = _ek_huellen(an, m, ek)
    k = ks[0] if len(ks) == 1 else None
    env_ek = an.envelopes.get(k) if k is not None else None
    text_ek = bg.umhuellende_kurz(k) if k is not None else ""
    check(f"{zeile}: Umhüllende der Ergebniskombination „{ek}“ unter eigenem Schlüssel",
          env_ek is not None and env_ek is not an.envelopes.get(art)
          and k not in bg.UMHUELLENDE, f"Schlüssel {ks}")
    check(f"{zeile}: … ihr Name nennt „{ek}“ und gleicht keinem anderen",
          bool(text_ek) and ek in text_ek and texte.count(text_ek) == 1 and text_ek != art_text,
          repr(text_ek))
    ok, detail = (_gleich(env_ek, _alternativen(m, an, m.combinations[ek])) if env_ek is not None
                  else (False, "fehlt"))
    check(f"{zeile}: … = unabhängige Auswertung ihrer Alternativen", ok, detail)
    check(f"{zeile}: alle Umhüllenden heißen verschieden", len(texte) == len(set(texte)), str(texte))


# --------------------------------------------------------------------------
# R1a, R1b - Rechnung
# --------------------------------------------------------------------------
def test_r1a_uls():
    from statik3d import solver
    m = ref()["kragarm"]("ULS", "ULS")
    an = solver.solve_all(m, design=False, fatigue=False)
    _beide_pruefen("R1a „ULS“", m, an, "ULS", "ULS")
    from statik3d import begriffe as bg
    ks = _ek_huellen(an, m, "ULS")
    check("R1a: Name der Ergebniskombination „Umhüllende ULS (Ergebniskombination)“",
          [bg.umhuellende_kurz(k) for k in ks] == ["Umhüllende ULS (Ergebniskombination)"],
          str([bg.umhuellende_kurz(k) for k in ks]))
    check("R1a: das Protokoll nennt den geänderten Namen",
          "„ULS“" in an.summary() and "Umhüllende ULS (Ergebniskombination)" in an.summary(),
          [z for z in an.summary().splitlines() if "Ergebniskombination" in z][:1])


#: R1b: (Name der Ergebniskombination, ihr Typ, Schluessel der Art, weitere
#: gewoehnliche Kombinationen, Umhuellende der Art vorhanden)
R1B_FAELLE = (
    ("FAT", "FAT", "FAT", (), True),
    ("SLS_CH", "SLS_CH", "SLS_CH", (), True),
    ("SLS_FR", "SLS_FR", "SLS_FR", ("SLS_FR",), True),
    ("SLS_QP", "SLS_QP", "SLS_QP", ("SLS_QP",), True),
    # eine Ergebniskombination vom Typ GZT, die wie die Umhuellende der
    # Ermuedung heisst
    ("FAT", "ULS", "FAT", (), True),
    # ein unbekannter Typ aus einer Quelldatei bildet eine eigene Umhuellende
    ("XYZ", "ULS", "XYZ", ("XYZ",), True),
)


def test_r1b_uebrige_schluessel():
    from statik3d import solver
    for ek, typ, art, typen, da in R1B_FAELLE:
        m = ref()["kragarm"](ek, typ, typen=typen)
        an = solver.solve_all(m, design=False, fatigue=False)
        _beide_pruefen(f"R1b „{ek}“ ({typ})", m, an, ek, art, da)
    # CASES: nur Lastfaelle und eine Ergebniskombination „CASES“ - die
    # Umhuellende der Lastfaelle entsteht dann nicht, der Name darf sie aber
    # auch nicht vortaeuschen
    m = ref()["kragarm"]("CASES", "ULS")
    for n in [n for n, c in m.combinations.items() if not c.ist_umhuellende]:
        del m.combinations[n]
    an = solver.solve_all(m, design=False, fatigue=False)
    _beide_pruefen("R1b „CASES“ (ULS)", m, an, "CASES", "CASES", art_da=False)


# --------------------------------------------------------------------------
# R1c - Ergebnisdatei
# --------------------------------------------------------------------------
def test_r1c_ergebnisdatei():
    from statik3d import solver, ergebnisse, begriffe as bg
    from statik3d.model import Model
    R = ref()
    m = R["kragarm"]("ULS", "ULS", weitere_ek={"FAT": "FAT"})
    an = solver.solve_all(m, design=False, fatigue=False)
    tmp = tempfile.mkdtemp(prefix="statik3d_huellen_datei_")
    pfad = os.path.join(tmp, "modell.json")
    m.save(pfad)
    ergebnisse.schreiben(ergebnisse.pfad_zu(pfad), m, an)
    m2 = Model.load(pfad)
    an2 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m2)
    vorher = {k: R["huelle"](e) for k, e in an.envelopes.items()}
    nachher = {k: R["huelle"](e) for k, e in an2.envelopes.items()}
    check("R1c: nach Speichern und Laden dieselben Umhüllenden, bitgleich",
          list(vorher) == list(nachher) and vorher == nachher,
          f"{list(vorher)} → {list(nachher)}")
    texte = [bg.umhuellende_kurz(k) for k in an2.envelopes]
    check("R1c: … alle mit verschiedenem Namen", len(texte) == len(set(texte)), str(texte))
    for ek, art in (("ULS", "ULS"), ("FAT", "FAT")):
        ks = _ek_huellen(an2, m2, ek)
        env = an2.envelopes.get(art)
        check(f"R1c: „{bg.umhuellende_kurz(art)}“ und Umhüllende der Ergebniskombination „{ek}“ "
              "kommen getrennt zurück",
              env is not None and len(ks) == 1 and an2.envelopes[ks[0]] is not env
              and _gleich(env, _erwartet_art(m2, an2, art))[0], f"{ks}")
    # eine Datei von 6791f9f ohne Kollision: laedt wie mit 6791f9f
    tmp = tempfile.mkdtemp(prefix="statik3d_huellen_alt_")
    for n in ("ohne_kollision.json", "ohne_kollision.ergebnisse",
              "mit_kollision.json", "mit_kollision.ergebnisse"):
        shutil.copy(os.path.join(REFERENZ, n), os.path.join(tmp, n))
    pfad = os.path.join(tmp, "ohne_kollision.json")
    m3 = Model.load(pfad)
    an3 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m3)
    soll = _json("ohne_kollision_geladen.json")
    ist = R["verdichtet"](R["analyse"](an3))
    check("R1c: Ergebnisdatei von 6791f9f ohne Kollision lädt unverändert (bitgleich)",
          ist == soll, str([k for k in soll if ist.get(k) != soll[k]]))
    check("R1c: … und meldet nichts", "Ergebniskombination" not in an3.summary(),
          [z for z in an3.summary().splitlines() if "Ergebniskombination" in z][:1])
    # eine Datei von 6791f9f mit Kollision: die Umhuellende unter ULS ist die
    # der Ergebniskombination - sie heisst jetzt so, und die fehlende
    # Umhuellende GZT wird benannt statt vorgetaeuscht
    pfad = os.path.join(tmp, "mit_kollision.json")
    m4 = Model.load(pfad)
    an4 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m4)
    alt_namen = [f"ULS [{k}]" for k in (1, 2, 3)]
    ks = [k for k, e in an4.envelopes.items() if list(e.names) == alt_namen]
    texte = [bg.umhuellende_kurz(k) for k in an4.envelopes]
    check("R1c: Datei von 6791f9f mit Kollision: Umhüllende der Ergebniskombination „ULS“ "
          "heißt „Umhüllende ULS (Ergebniskombination)“",
          [bg.umhuellende_kurz(k) for k in ks] == ["Umhüllende ULS (Ergebniskombination)"],
          f"{ks} {texte}")
    check("R1c: … keine „Umhüllende GZT“ vorgetäuscht", "Umhüllende GZT" not in texte, str(texte))
    s = an4.summary()
    check("R1c: … die Zusammenfassung sagt, dass die Umhüllende GZT fehlt",
          "Umhüllende GZT" in s and "neu" in s,
          [z for z in s.splitlines() if "fehlt" in z][:1])
    # im Fenster: dasselbe im Protokoll
    w, app = _fenster()
    ok = w.modell_laden(pfad, fragen=False)
    for _ in range(4):
        app.processEvents()
    log = w.log.toPlainText()
    check("R1c: … und das Protokoll beim Öffnen im Fenster",
          ok and "„ULS“" in log and "Umhüllende GZT" in log and "fehlt" in log,
          [z for z in log.splitlines() if "fehlt" in z][:1])


# --------------------------------------------------------------------------
# R1d - Oberflaeche, Bericht, Web
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
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _baum_huellen(w) -> list:
    from PySide6 import QtCore, QtWidgets
    aus = []
    it = QtWidgets.QTreeWidgetItemIterator(w.baum)
    while it.value() is not None:
        x = it.value()
        p = x.parent()
        if p is not None and p.data(0, QtCore.Qt.UserRole) == "ergebnisgruppe" \
                and p.text(0) == "Umhüllende":
            aus.append((x.text(0), x.data(0, QtCore.Qt.UserRole + 1)))
        it += 1
    return aus


def test_r1d_auswahl_bericht_web():
    from statik3d import solver, begriffe as bg
    w, app = _fenster()
    m = ref()["kragarm"]("ULS", "ULS", weitere_ek={"SLS_CH": "ULS"})
    w.model = m
    w.analysis = None
    w.results = None
    w.refresh_all(); app.processEvents()
    an = solver.solve_all(m, design=False, fatigue=False)
    w._solve_done("all", an); app.processEvents()
    env_gzt = an.envelopes.get("ULS")
    ks = _ek_huellen(an, m, "ULS")
    env_ek = an.envelopes.get(ks[0]) if len(ks) == 1 else None
    gzt_ok = env_gzt is not None and "K1" in env_gzt.names
    check("R1d: Rechnung hat Umhüllende GZT (mit K1) und die der Ergebniskombination „ULS“",
          gzt_ok and env_ek is not None and env_ek is not env_gzt, str(list(an.envelopes)))
    for titel, cb in (("oben rechts", w.cb_result), ("unten (10c)", w.cb_ergebnis_unten),
                      ("Glasleiste", w.cb_lastwahl)):
        eintr = [(cb.itemText(i), tuple(cb.itemData(i))) for i in range(cb.count())
                 if cb.itemData(i) is not None and cb.itemData(i)[0] == "env"]
        texte = [t for t, _d in eintr]
        check(f"R1d {titel}: alle Umhüllenden mit verschiedenem Namen, keine Zeile doppelt",
              len(eintr) == len(an.envelopes) and len(texte) == len(set(texte)), str(texte))
        gzt = [d for t, d in eintr if t == "Umhüllende GZT"]
        ek = [d for t, d in eintr if t == "Umhüllende ULS (Ergebniskombination)"]
        check(f"R1d {titel}: „Umhüllende GZT“ und „Umhüllende ULS (Ergebniskombination)“",
              len(gzt) == 1 and len(ek) == 1 and gzt != ek, f"{gzt} {ek}")
        if titel == "unten (10c)":
            continue        # dieselbe Liste wie oben rechts (geteiltes Modell)
        for text, soll in (("Umhüllende GZT", env_gzt), ("Umhüllende ULS (Ergebniskombination)", env_ek)):
            i = next((i for i in range(cb.count()) if cb.itemText(i) == text), -1)
            if i >= 0:
                cb.setCurrentIndex(i)
                app.processEvents()
            check(f"R1d {titel}: Wahl „{text}“ zeigt genau diese Umhüllende",
                  i >= 0 and soll is not None and w.current_result() is soll,
                  getattr(w.current_result(), "names", None))
    baum = _baum_huellen(w)
    texte = [t for t, _s in baum]
    check("R1d Modellbaum: Umhüllende mit verschiedenem Namen, beide da",
          len(texte) == len(set(texte)) == len(an.envelopes)
          and "Umhüllende GZT" in texte and "Umhüllende ULS (Ergebniskombination)" in texte, str(texte))
    # Ausnutzung EC3 nur zu GZT und zu Ergebniskombinationen der Art GZT:
    # die Ergebniskombination „SLS_CH“ ist vom Typ GZT, die Umhuellende SLS_CH
    # (GZG) nicht - bis 6791f9f lasen beide denselben Schluessel
    k_sls = _ek_huellen(an, m, "SLS_CH")
    check("R1d Tabellen: EC3-Ausnutzung zur Umhüllenden GZG nicht, zu den Ergebniskombinationen "
          "„ULS“ und „SLS_CH“ (Typ GZT) schon",
          not w._ausnutzung_zur_huelle("SLS_CH") and w._ausnutzung_zur_huelle("ULS")
          and len(ks) == 1 and w._ausnutzung_zur_huelle(ks[0])
          and len(k_sls) == 1 and w._ausnutzung_zur_huelle(k_sls[0]),
          f"{k_sls}")
    # Bericht: je Umhuellende ein Abschnitt mit eigenem Titel und ihren Ergebnissen
    from statik3d.report import Report
    bt = runpy.run_path(os.path.join(HIER, "daten", "fachbegriffe_68db45b", "erzeugen.py"))["bericht_text"]
    zeilen = bt(Report(m, an).html()).splitlines()
    abschnitte = {}
    for i, z in enumerate(zeilen):
        t = re.match(r"^\d+(?:\.\d+)+&nbsp;&nbsp;(Umhüllende .+)$", z)
        if t:
            folgt = next((x for x in zeilen[i + 1:i + 4] if x.startswith("Extremwerte aus")), "")
            abschnitte.setdefault(t.group(1), []).append(folgt)
    check("R1d Bericht: je Umhüllende ein Abschnitt, kein Titel doppelt",
          len(abschnitte) == len(an.envelopes) and all(len(v) == 1 for v in abschnitte.values()),
          str(list(abschnitte)))
    gzt = abschnitte.get("Umhüllende Grenzzustand der Tragfähigkeit (GZT)", [""])[0]
    ek = abschnitte.get("Umhüllende ULS (Ergebniskombination)", [""])[0]
    check("R1d Bericht: Umhüllende GZT mit K1, K2 und den Alternativen; die der "
          "Ergebniskombination nur mit ihren",
          "K1" in gzt and "K2" in gzt and "ULS [1]" in gzt
          and ek.startswith("Extremwerte aus 3 Ergebnissen") and "K1" not in ek, f"{gzt!r} {ek!r}")
    # Web
    from statik3d.web import server as S
    st = S.State(m)
    st.analysis = an
    eintr = [e for e in S.result_entries(st) if e["id"].startswith("env:")]
    texte = [e["label"] for e in eintr]
    check("R1d Web: Umhüllende mit verschiedenem Namen, beide da",
          len(texte) == len(set(texte)) == len(an.envelopes)
          and "Umhüllende GZT" in texte and "Umhüllende ULS (Ergebniskombination)" in texte, str(texte))
    ids = {e["label"]: e["id"] for e in eintr}
    check("R1d Web: jede Kennung liefert ihre Umhüllende",
          S.get_result(st, ids.get("Umhüllende GZT")) is env_gzt
          and S.get_result(st, ids.get("Umhüllende ULS (Ergebniskombination)")) is env_ek,
          str(ids))


# --------------------------------------------------------------------------
# R1e - Ermuedung aus einer FAT-Umhuellenden
# --------------------------------------------------------------------------
def test_r1e_ermuedung():
    from statik3d import solver
    R = ref()
    soll = _json("ermuedung.json")
    m = R["hallenrahmen_ermuedung"]("EK_FAT")
    an = solver.solve_all(m, design=True, fatigue=True)
    check("R1e: Ermüdungslasten wie 6791f9f", sorted(m.fatigue_loads) == soll["fatigue_loads"],
          str(sorted(m.fatigue_loads)))
    lesbar = R["ermuedung_lesbar"](an.fatigue)
    check("R1e: D, Ausnutzung und maßgebende Stelle je Stab bitgleich mit 6791f9f",
          lesbar == soll["lesbar"],
          "; ".join(f"{k}: D = {v['D']!r}, {v['governing'][:30]}" for k, v in lesbar.items()))
    check("R1e: der ganze Ermüdungsnachweis bitgleich mit 6791f9f",
          R["wert"](an.fatigue) == soll["fatigue"], an.fatigue.summary())
    # Gegenstueck: dieselbe Ergebniskombination unter dem Namen „FAT“ - die
    # Ermuedung liest Lastfaelle, keine Umhuellende, und bleibt gleich
    m2 = R["hallenrahmen_ermuedung"]("FAT")
    an2 = solver.solve_all(m2, design=True, fatigue=True)
    check("R1e: mit der Ergebniskombination „FAT“ dieselbe Ermüdung",
          R["ermuedung_lesbar"](an2.fatigue) == lesbar, an2.fatigue.summary())


# --------------------------------------------------------------------------
# R1f - Beispiele bitgleich mit 6791f9f
# --------------------------------------------------------------------------
def test_r1f_beispiele():
    from statik3d import solver
    from statik3d.examples_lib import build_example
    R = ref()
    soll = _json("beispiele.json")
    for b in R["BEISPIELE"]:
        an = solver.solve_all(build_example(b), design=True, fatigue=True)
        ist = R["verdichtet"](R["analyse"](an))
        anders = [f"{teil}/{k}" for teil in soll[b] if isinstance(soll[b][teil], dict)
                  for k in set(soll[b][teil]) | set(ist.get(teil) or {})
                  if (ist.get(teil) or {}).get(k) != soll[b][teil].get(k)]
        anders += [teil for teil in soll[b] if not isinstance(soll[b][teil], dict)
                   and ist.get(teil) != soll[b][teil]]
        check(f"R1f {b}: Verschiebungen, Kräfte, Umhüllende, EC3 und Ermüdung bitgleich mit 6791f9f",
              not anders, f"{len(ist['cases'])} LF, {len(ist['combinations'])} K, "
                          f"Umhüllende {ist['envelope_keys']}" + (f"; anders: {anders[:6]}" if anders else ""))


# --------------------------------------------------------------------------
# Nachbesserung 04.10.2026: R1g bis R1j
# --------------------------------------------------------------------------
def _ausnutzung(m, an, key) -> bool:
    """MainWindow._ausnutzung_zur_huelle mit Modell und Analysis (liest nur sie)."""
    import types
    from statik3d.gui.main import MainWindow
    return MainWindow._ausnutzung_zur_huelle(types.SimpleNamespace(model=m, analysis=an), key)


def test_r1g_ausnutzung_unbekannter_typ():
    """Befund F1: die Umhuellende eines unbekannten Typs „XYZ“ bekam die Spalte
    Ausnutzung, weil eine Ergebniskombination vom Typ GZT „XYZ“ hiess."""
    from statik3d import solver, ergebnisse
    from statik3d.model import Model
    m = ref()["kragarm"]("XYZ", "ULS", typen=("XYZ",))
    an = solver.solve_all(m, design=False, fatigue=False)
    ks = _ek_huellen(an, m, "XYZ")
    a_art = _ausnutzung(m, an, "XYZ")
    a_ek = _ausnutzung(m, an, ks[0]) if len(ks) == 1 else None
    check("R1g: Umhüllende XYZ (unbekannter Typ): keine Spalte Ausnutzung", a_art is False,
          f"_ausnutzung_zur_huelle('XYZ') = {a_art} (names={list(an.envelopes['XYZ'].names)})")
    check("R1g: Umhüllende der Ergebniskombination „XYZ“ (Typ GZT): Spalte Ausnutzung",
          a_ek is True, f"_ausnutzung_zur_huelle({ks}) = {a_ek}")
    # dasselbe aus einer Ergebnisdatei von 6791f9f (dort ohne kombination)
    pfad = os.path.join(REFERENZ, "alt", "unbekannt.json")
    m2 = Model.load(pfad)
    an2 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m2)
    ks2 = [k for k, e in an2.envelopes.items() if getattr(e, "kombination", None) == "XYZ"]
    check("R1g: alte Datei: Umhüllende der Ergebniskombination „XYZ“ mit Spalte, GZT mit, "
          "GZG ohne",
          len(ks2) == 1 and _ausnutzung(m2, an2, ks2[0]) is True
          and _ausnutzung(m2, an2, "ULS") is True and _ausnutzung(m2, an2, "SLS_CH") is False,
          f"{ks2}")


def test_r1h_alte_datei_ohne_modellbezug():
    """Befund L1: _huellen_umhaengen erkannte nur Ergebniskombinationen, die
    das geladene Modell noch hat. War „ULS“ nach der Rechnung umbenannt oder
    geloescht, blieb ihre Umhuellende die „Umhüllende GZT“."""
    from statik3d import ergebnisse, begriffe as bg
    from statik3d.model import Model
    R = ref()
    alt = os.path.join(REFERENZ, "alt")
    for fall in ("ULS_zu_EK9", "ULS_geloescht"):
        pfad = os.path.join(alt, fall + ".json")
        m = Model.load(pfad)
        an = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m)
        anzeige = [bg.umhuellende_kurz(k) for k in an.envelopes]
        env = an.envelopes.get("ULS (Ergebniskombination)")
        check(f"R1h {fall}: Umhüllende der Ergebniskombination „ULS“ erkannt und umgehängt",
              env is not None and list(env.names) == ["ULS [1]", "ULS [2]", "ULS [3]"]
              and env.kombination == "ULS" and "ULS" not in an.envelopes
              and "Umhüllende GZT" not in anzeige, str(anzeige))
        s = an.summary()
        check(f"R1h {fall}: … mit Hinweis, dass die Umhüllende GZT fehlt",
              "„ULS“" in s and "„Umhüllende GZT“ überschrieben" in s and "fehlt" in s,
              [z for z in s.splitlines() if z.startswith("Hinweis")][-1:])
    # keine Fehlerkennung: die zwoelf Dateien wie dc80e1f, auch EK1 -> ULS
    soll = _json("alt_gelesen_dc80e1f.json")
    anders = []
    for fall in list(R["ALTE_DATEIEN"]) + ["EK1_zu_ULS"]:
        pfad = os.path.join(alt, fall + ".json")
        ist = R["gelesen"](ergebnisse.lesen(ergebnisse.pfad_zu(pfad), Model.load(pfad)))
        if ist != soll[fall]:
            anders.append(fall)
    check("R1h: keine Fehlerkennung - zwölf Dateien der Gegenprüfung und „EK1 → ULS“ wie dc80e1f",
          not anders, f"anders: {anders}" if anders else f"{len(R['ALTE_DATEIEN']) + 1} Dateien gleich")


def _modell_lastfall_wie_kombination(name="X"):
    m = ref()["kragarm"]("EK1", "ULS")
    m.add_load_case("X", "Q", activate=False)
    m.load_node(4, Fz=-30e3, case="X")
    m.add_combination(name, {"LF1": 0.2}, "ULS", "klein")
    m.add_fatigue_load("FX", "X", None, 2e6)
    return m


def _modell_kombination_wie_alternative(name="EK1 [2]"):
    m = ref()["kragarm"]("EK1", "ULS")
    m.add_combination(name, {"LF1": 0.1}, "ULS", "klein")
    return m


def test_r1i_sicherheitsnetz():
    """Bis zur Namensregel LF/LK/EK (R2): Namen, unter denen Ergebnisse
    einander verdecken, sind FEHLER der Modellpruefung, und die Rechnung
    startet nicht (Gegenpruefung R1: Ermuedung D = 0 statt 27,6; EC3 1,10
    statt 1,49, beides ohne Meldung)."""
    from statik3d import solver
    from statik3d.examples_lib import EXAMPLES, build_example
    faelle = (("Lastfall und Kombination „X“", _modell_lastfall_wie_kombination, "X",
               ("Lastfall 'X'", "Kombination 'X'", "umbenennen")),
              ("Kombination „EK1 [2]“ neben der Ergebniskombination EK1",
               _modell_kombination_wie_alternative, "EK1 [2]",
               ("Kombination 'EK1 [2]'", "Ergebniskombination 'EK1'", "umbenennen")))
    for titel, bauen, name, teile in faelle:
        m = bauen(name)
        fehler = [z for z in m.check() if z.startswith("FEHLER")]
        check(f"R1i {titel}: check() meldet FEHLER, nennt beide, sagt „umbenennen“",
              any(all(t in z for t in teile) for z in fehler), str(fehler[-1:]))
        try:
            solver.solve_all(m, design=False, fatigue=False)
            ausnahme = None
        except ValueError as ex:
            ausnahme = str(ex)
        check(f"R1i {titel}: solve_all startet nicht", ausnahme is not None
              and all(t in ausnahme for t in teile), str(ausnahme)[:120])
        # im Fenster: „Berechnen“ weist ab, nichts wird gestartet
        w, app = _fenster()
        w.model = m
        w.analysis = None
        w.results = None
        w.refresh_all(); app.processEvents()
        w.meldungen.leeren()
        gestartet = []
        w._run_background = lambda *a, **k: gestartet.append(a)
        try:
            w.do_solve("all")
            app.processEvents()
        finally:
            del w._run_background
        check(f"R1i {titel}: „Berechnen“ startet nicht, die Meldung nennt den FEHLER",
              not gestartet and w.analysis is None and w.meldungen.fehler_mit(*teile),
              str(w.meldungen.fehler[-1:])[:160])
        # Gegenstueck: anders benannt meldet nichts und rechnet
        m2 = bauen("X_K" if name == "X" else "K_x")
        neu = [z for z in m2.check() if "heißen gleich" in z or "wie die Alternative" in z]
        an2 = solver.solve_all(m2, design=False, fatigue=False)
        check(f"R1i {titel}: Gegenstück mit anderem Namen meldet nichts und rechnet",
              not neu and an2 is not None and len(an2.combinations) > 0, str(neu))
    neu = {b: [z for z in build_example(b).check() if "heißen gleich" in z or "wie die Alternative" in z]
           for b in EXAMPLES}
    check("R1i: die Beispiele melden nichts Neues", not any(neu.values()),
          f"{len(EXAMPLES)} Beispiele: " + ", ".join(EXAMPLES))


def test_r1j_hinweis_und_protokoll():
    """Befunde S2 und S3: die Hinweiszeile nannte die „Umhüllende Lastfälle“
    neben einer Ergebniskombination „CASES“, die es nicht gab; das Protokoll
    nannte die Umhuellende einer Ergebniskombination mit ihrem blossen Namen
    („ULS: 3 Ergebnisse“), Liste und Baum mit „Umhüllende ULS
    (Ergebniskombination)“."""
    import re as _re
    from statik3d import solver, begriffe as bg
    m = ref()["kragarm"]("CASES", "ULS")
    for n in [n for n, c in m.combinations.items() if not c.ist_umhuellende]:
        del m.combinations[n]
    an = solver.solve_all(m, design=False, fatigue=False)
    hinweise = [z for z in an.summary().splitlines() if z.startswith("Hinweis")]
    anzeigen = {bg.umhuellende_kurz(k) for k in an.envelopes}
    genannt = _re.findall(r"„(Umhüllende [^“]+)“", " ".join(hinweise))
    check("R1j „CASES“: die Hinweiszeile nennt nur Umhüllende dieser Rechnung",
          bool(hinweise) and all(g in anzeigen for g in genannt), str(hinweise))
    for titel, ek, weitere in (("„CASES“", None, None), ("„ULS“ und EK1", "ULS", {"EK1": "ULS"})):
        if ek is not None:
            m = ref()["kragarm"](ek, "ULS", weitere_ek=weitere)
            an = solver.solve_all(m, design=False, fatigue=False)
        zeilen = an.summary().splitlines()
        fehlt = [bg.umhuellende_kurz(k) for k in an.envelopes
                 if not any(z.startswith(f"{bg.umhuellende_kurz(k)}: ") for z in zeilen)]
        nackt = [z for z in zeilen if _re.match(r"^(ULS|CASES|EK1): \d+ Ergebnis", z)]
        check(f"R1j {titel}: das Protokoll nennt jede Umhüllende mit ihrem Anzeigenamen",
              not fehlt and not nackt,
              f"fehlt {fehlt}, nackt {nackt}" if fehlt or nackt
              else str([z for z in zeilen if z.startswith("Umhüllende")]))
    # im Fenster: Protokoll und Text zur gewaehlten Umhuellenden
    w, app = _fenster()
    w.model = m
    w.analysis = None
    w.results = None
    w.refresh_all(); app.processEvents()
    w._solve_done("all", an); app.processEvents()
    log = w.log.toPlainText().splitlines()
    i = next((i for i in range(w.cb_result.count())
              if w.cb_result.itemText(i) == "Umhüllende ULS (Ergebniskombination)"), -1)
    if i >= 0:
        w.cb_result.setCurrentIndex(i); app.processEvents()
    text = w.txt_res.toPlainText().splitlines()
    check("R1j Fenster: Protokoll „Umhüllende ULS (Ergebniskombination): 3 Ergebnisse“, "
          "der Text zur Wahl ebenso",
          "Umhüllende ULS (Ergebniskombination): 3 Ergebnisse" in log
          and "Umhüllende EK1: 2 Ergebnisse" in log
          and bool(text) and text[0] == "Umhüllende ULS (Ergebniskombination): 3 Ergebnisse",
          str(text[:1]))


# --------------------------------------------------------------------------
# Zusatz: Lastfaelle und gewoehnliche Kombinationen mit reservierten Namen
# --------------------------------------------------------------------------
def test_zusatz_lastfall_und_kombination_reserviert():
    """Ein Lastfall „ULS“ oder „CASES“ und eine gewoehnliche Kombination „FAT“
    oder „SLS_CH“ stehen in an.cases und an.combinations - eigene
    Woerterbuecher, keine Umhuellende. Nichts davon ueberschreibt etwas,
    auch nicht in der Ergebnisdatei."""
    from statik3d import solver, ergebnisse, begriffe as bg
    from statik3d.model import Model
    m = ref()["kragarm"]("EK1", "ULS")
    m.add_load_case("ULS", "Q", activate=False)
    m.load_node(4, Fz=-1e3, case="ULS")
    m.add_load_case("CASES", "Q", activate=False)
    m.load_node(4, Fy=1e3, case="CASES")
    m.add_combination("FAT", {"ULS": 1.5, "CASES": 1.0}, "ULS", "heisst wie die Ermuedung")
    m.add_combination("SLS_CH", {"ULS": 1.0}, "FAT", "heisst wie GZG")
    an = solver.solve_all(m, design=False, fatigue=False)
    check("Zusatz: alle Lastfälle und Kombinationen haben ihr Ergebnis",
          list(an.cases) == list(m.load_cases)
          and set(an.combinations) == {n for n, c in m.combinations.items() if not c.ist_umhuellende},
          f"{list(an.cases)} {list(an.combinations)}")
    check("Zusatz: Kombination „FAT“ (GZT) in der Umhüllenden GZT, „SLS_CH“ (Ermüdung) in der "
          "der Ermüdung",
          "FAT" in an.envelopes["ULS"].names and "SLS_CH" in an.envelopes["FAT"].names
          and _gleich(an.envelopes["ULS"], _erwartet_art(m, an, "ULS"))[0]
          and _gleich(an.envelopes["FAT"], _erwartet_art(m, an, "FAT"))[0],
          str({k: list(e.names) for k, e in an.envelopes.items()}))
    texte = [bg.umhuellende_kurz(k) for k in an.envelopes]
    check("Zusatz: alle Umhüllenden heißen verschieden", len(texte) == len(set(texte)), str(texte))
    tmp = tempfile.mkdtemp(prefix="statik3d_huellen_lf_")
    pfad = os.path.join(tmp, "modell.json")
    m.save(pfad)
    ergebnisse.schreiben(ergebnisse.pfad_zu(pfad), m, an)
    an2 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), Model.load(pfad))
    R = ref()
    check("Zusatz: Ergebnisdatei hält alle Ergebnisse und Umhüllenden bitgleich",
          R["verdichtet"](R["analyse"](an2)) == R["verdichtet"](R["analyse"](an))
          and list(an2.cases) == list(an.cases) and list(an2.combinations) == list(an.combinations))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_r1a_uls, test_r1b_uebrige_schluessel, test_r1c_ergebnisdatei,
              test_r1d_auswahl_bericht_web, test_r1e_ermuedung, test_r1f_beispiele,
              test_r1g_ausnutzung_unbekannter_typ, test_r1h_alte_datei_ohne_modellbezug,
              test_r1i_sicherheitsnetz, test_r1j_hinweis_und_protokoll,
              test_zusatz_lastfall_und_kombination_reserviert):
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
