"""
Umstellung alter Dateien auf LF/LK/EK beim Laden - Paket R2-A2, 06.10.2026.

Entscheidung des Anwenders vom 04.10.2026: Lastfaelle heissen LF<Nr>,
Lastkombinationen LK<Nr>, Ergebniskombinationen EK<Nr>, der alte freie Name
wird Bezeichnung. **Alte Modelle und Ergebnisdateien werden beim Oeffnen
umgestellt**, alle Verweise gehen mit, das Protokoll zeigt die Tabelle
alt -> neu, gespeichert wird danach im neuen Format (Fassung 9).

Abnahme (vorher festgelegt, jede Zeile schlug auf ff99eb7 fehl):

* U1 - alle Modelldateien in tests/daten (Fassung 7 und 8, dazu der
  Pruefkoerper umstellung_ff99eb7) oeffnen: Namen LF<n>/LK<n>/EK<n>, alte
  Namen als Bezeichnung, Tabelle im Protokoll, Rechnung vor der Umstellung
  (alte Namen) gleich nach der Umstellung bis auf die Namen (bitgleich);
* U2 - Kopie von cbg.json (Desktop) und der Pruefkoerper: umstellen,
  speichern, wieder oeffnen - das zweite Oeffnen stellt nichts mehr um;
  Lastfaelle, Kombinationen (LK/EK nach Regel), Ermuedungslasten,
  Stellungen, Berichtsbilder, Wind und Wasserdruck vollstaendig umgestellt,
  Erzeugtes bleibt dem Generator; check() meldet nichts Neues;
* U3 - Kopie von drehlager.json (165 MB): nur laden, umstellen, check(),
  speichern und wieder laden; Zeit und Speicher (nur mit
  STATIK3D_R2_GROSS=1, sonst uebersprungen);
* U4 - alte Ergebnisdateien samt Modell: Ergebnisse unter neuen Namen,
  Zahlen bytegleich mit der Datei, Nachweise finden ihre Alternativen,
  R1-Schluessel richtig, Unsicheres verworfen und genannt;
* U5 - kreuzende Namen („LF2“, „A“, „LF1“; eine Kombination „LF2“; „lf2“
  neben „LF2“) und eine Stichprobe von 300 zufaelligen alten Modellen:
  eindeutige, stabile Vergabe, kein Verweis zeigt auf ein anderes Objekt;
* U6 - Rechenarbeiter (jobs.py) mit einem Modell der Fassung 9: kein
  Umstellen, keine Hinweise im Arbeiter;
* U7 - Speichern nach der Umstellung: Fassung 9, Felder gesetzt; ein
  Programm vor A2 liest die Datei (mit STATIK3D_R2_ALTBAUM=<Baum ff99eb7>
  gegen diesen Baum geprueft, sonst uebersprungen);
* U8 - Beispiele frame, truss, hall, gate, contact: A2 fasst sie nicht an,
  Umlauf ueber Fassung 9 ohne Umstellung, Rechnung bitgleich mit der
  Referenz aus tests/daten/huellen_schluessel_6791f9f.

Aufruf:  python -m tests.test_umstellung_lf_lk
"""
import glob
import json
import os
import random
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_umstellung_"), "einstellungen.json")

import numpy as np  # noqa: E402

RESULTS = []
_FENSTER = {}
HIER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.path.join(HIER, "daten")
PRUEFKOERPER = os.path.join(DATEN, "umstellung_ff99eb7", "hallenrahmen.json")
#: Ordner mit den echten Modellen des Anwenders (Kopien werden geprueft)
MODELLE = os.environ.get("STATIK3D_R2_MODELLE", r"C:\Users\alexanderm\Desktop\Statik3D")
_REF = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def skip(name, grund):
    print(f"SKIP {name:78s} {grund}")


def ref():
    """Fingerabdruck-Hilfen der Referenz von R1 (wert, ergebnis, huelle,
    analyse, verdichtet) - dieselben, mit denen tests/daten entstand."""
    if not _REF:
        _REF.update(runpy.run_path(os.path.join(DATEN, "huellen_schluessel_6791f9f", "erzeugen.py")))
    return _REF


def modelldateien() -> list:
    """Alle Modelldateien in tests/daten (Fassung 7 und 8)."""
    aus = []
    for p in sorted(glob.glob(os.path.join(DATEN, "**", "*.json"), recursive=True)):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and "nodes" in d:
            aus.append(p)
    return aus


def _roh(p) -> dict:
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _ohne_umstellung(quelle):
    """Das Modell mit seinen alten Namen - so, wie es ein Programm vor A2
    liest (ohne die Umstellung beim Oeffnen)."""
    from statik3d.model import Model
    return Model.load(quelle, umstellen=False) if isinstance(quelle, str) else Model.from_dict(quelle)


def _tabellen(m):
    tab = getattr(m, "_umbenennung", None) or {}
    return dict(tab.get("lastfaelle") or {}), dict(tab.get("kombinationen") or {})


def _abbilden(m):
    """name -> neuer Name fuer Lastfall, Kombination und Alternative."""
    lf, ko = _tabellen(m)

    def abb(n):
        if n in lf:
            return lf[n]
        if n in ko:
            return ko[n]
        t = re.fullmatch(r"(.+) \[(\d+)\]", str(n))
        if t and t.group(1) in ko:
            return f"{ko[t.group(1)]} [{t.group(2)}]"
        return n
    return abb


def _form_ok(m) -> tuple:
    """(True, "") wenn alle Lastfaelle LF<n> und alle Kombinationen LK<n>/EK<n>
    heissen, Art und Nummer zum Namen passen und keine Nummer doppelt ist."""
    fehler = []
    for n, lc in m.load_cases.items():
        t = re.fullmatch(r"LF([1-9]\d*)", n)
        if not t or lc.nummer != int(t.group(1)):
            fehler.append(f"{n}/Nr. {lc.nummer}")
    for n, c in m.combinations.items():
        # nach Situation geteilt: „EK5 (Grundstellung)“ mit der eigenen Situation
        t = re.fullmatch(r"(LK|EK)([1-9]\d*)(?: \((.+)\))?", n)
        if not t or c.art != t.group(1) or c.nummer != int(t.group(2))                 or (t.group(3) is not None and t.group(3) != (c.situation or "Grundstellung")):
            fehler.append(f"{n}/{c.art}{c.nummer}")
    fehler += m.doppelte_nummern()
    return not fehler, ", ".join(fehler[:6])


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    B = QtWidgets.QMessageBox
    for art in ("critical", "warning", "information"):
        setattr(B, art, staticmethod(lambda *a, **k: B.Ok))
    B.question = staticmethod(lambda *a, **k: B.No)
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.fehler_liste = []
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _kopie(pfad, ordner=None) -> str:
    """Modell und Ergebnisdatei in einen eigenen Ordner kopieren - die Dateien
    in tests/daten und auf dem Desktop bleiben unberuehrt."""
    from statik3d import ergebnisse
    ordner = ordner or tempfile.mkdtemp(prefix="statik3d_umstellung_kopie_")
    ziel = os.path.join(ordner, os.path.basename(pfad))
    shutil.copy(pfad, ziel)
    if os.path.exists(ergebnisse.pfad_zu(pfad)):
        shutil.copy(ergebnisse.pfad_zu(pfad), ergebnisse.pfad_zu(ziel))
    return ziel


# --------------------------------------------------------------------------
# Vergleich zweier Rechnungen bis auf die Namen
# --------------------------------------------------------------------------
def _huelle_zahlen(env) -> dict:
    R = ref()
    d = {f: R["wert"](getattr(env, f, None)) for f in R["HUELLEN_FELDER"] if f not in ("name", "names")}
    d["umag_max"] = R["wert"](env.umag_max)
    d["phimag_max"] = R["wert"](env.phimag_max)
    return d


def _nachweise(an, abb) -> dict:
    """Was die Nachweise sagen, mit den Namen durch *abb*: EC3 je Stab
    (Ausnutzung bitgenau, massgebend, Kombination, Stelle), GZG je Grenze,
    Theorie II. Ordnung je Zeile, Ermuedung ganz (sie nennt keine Kombination)."""
    R = ref()

    def eintrag(n):
        return " = ".join(abb(t) for t in str(n).split(" = "))
    aus = {}
    if an.design is not None:
        aus["design"] = {k: (float(mc.util).hex(), mc.governing.get("name"), eintrag(mc.governing.get("combo", "")),
                             float(mc.governing.get("x", 0.0)).hex()) for k, mc in an.design.members.items()}
        aus["design_kombinationen"] = [eintrag(n) for n in an.design.combinations]
    if an.gzg is not None:
        aus["gzg"] = {k: (float(c.util).hex(), abb(c.kombination),
                          [(abb(x["kombination"]), float(x["wert"]).hex()) for x in c.je_kombination])
                      for k, c in an.gzg.checks.items()}
    if an.theorie2 is not None:
        aus["theorie2"] = {abb(k): (abb(i.kombination), float(i.alpha_cr).hex(), float(i.zuwachs).hex())
                           for k, i in an.theorie2.kombinationen.items()}
    if an.fatigue is not None:
        aus["fatigue"] = R["wert"](an.fatigue)
    return aus


def _rechnung_gleich(vor, nach, abb) -> list:
    """Unterschiede zwischen der Rechnung *vor* (alte Namen) und *nach* (neue
    Namen) - leer, wenn alles bitgleich ist und jeder Name nach *abb* folgt."""
    R = ref()
    anders = []
    if sorted(abb(n) for n in vor.cases) != sorted(nach.cases):
        anders.append(f"Lastfälle {list(vor.cases)} → {list(nach.cases)}")
    if sorted(abb(n) for n in vor.combinations) != sorted(nach.combinations):
        anders.append(f"Kombinationen {list(vor.combinations)} → {list(nach.combinations)}")
    for gruppe in ("cases", "combinations", "alternativen"):
        for n, r in (getattr(vor, gruppe) or {}).items():
            r2 = (getattr(nach, gruppe) or {}).get(abb(n))
            if r2 is None or R["ergebnis"](r) != R["ergebnis"](r2):
                anders.append(f"{gruppe} {n}")
    from statik3d.solver import umhuellende_schluessel_im_modell
    sv = umhuellende_schluessel_im_modell(vor.model)
    sn = umhuellende_schluessel_im_modell(nach.model)
    rueck = {v: k for k, v in sv.items()}
    for k, env in vor.envelopes.items():
        k2 = sn.get(abb(rueck[k]), abb(rueck[k])) if k in rueck else k
        e2 = nach.envelopes.get(k2)
        if e2 is None or _huelle_zahlen(env) != _huelle_zahlen(e2) \
                or [abb(x) for x in env.names] != list(e2.names):
            anders.append(f"Umhüllende {k} → {k2}")
    if _nachweise(vor, abb) != _nachweise(nach, lambda n: n):
        anders.append("Nachweise")
    return anders


# --------------------------------------------------------------------------
# U1 - alle Dateien in tests/daten
# --------------------------------------------------------------------------
def test_u1_dateien_in_tests_daten():
    from statik3d.model import Model, FORMAT_VERSION
    from statik3d import solver
    dateien = modelldateien()
    check("U1 Modelldateien in tests/daten gefunden (Fassung 7 und 8, dazu der Prüfkörper)",
          len(dateien) >= 20 and PRUEFKOERPER in dateien
          and {_roh(p).get("format") for p in dateien} == {7, 8}, f"{len(dateien)} Dateien")
    check("U1 Dateifassung des Programms ist 9", FORMAT_VERSION == 9, str(FORMAT_VERSION))
    form_falsch, bez_falsch, tab_falsch, rechnung_anders = [], [], [], []
    for p in dateien:
        kurz = os.path.relpath(p, DATEN)
        roh = _roh(p)
        m = Model.load(p)
        ok, detail = _form_ok(m)
        if not ok:
            form_falsch.append(f"{kurz}: {detail}")
        lf, ko = _tabellen(m)
        alt_lf = [x["name"] for x in roh.get("load_cases", [])]
        alt_k = [x["name"] for x in roh.get("combinations", [])]
        if sorted(lf) != sorted(alt_lf) or sorted(ko) != sorted(alt_k):
            tab_falsch.append(f"{kurz}: Tabelle unvollständig")
            continue
        # der alte Name wird Bezeichnung, wenn er nicht schon der neue ist
        for alt, neu in list(lf.items()) + list(ko.items()):
            o = m.load_cases.get(neu) if alt in lf and lf[alt] == neu else m.combinations.get(neu)
            soll = alt if alt != neu else ""
            if o is None or o.bezeichnung != soll:
                bez_falsch.append(f"{kurz}: {alt} → {neu} ({getattr(o, 'bezeichnung', None)!r})")
        # Tabelle im Protokoll (die Hinweise, die die Oberflaeche ausgibt)
        text = "\n".join(m._ladehinweise)
        zeilen = [f"{a} → {b}" for a, b in list(lf.items()) + list(ko.items()) if a != b]
        if zeilen and ("Namen umgestellt" not in text or "beim Speichern im neuen Format" not in text
                       or any(z not in text for z in zeilen)):
            tab_falsch.append(f"{kurz}: Tabelle fehlt im Protokoll")
        # Rechnung vorher (alte Namen) gleich nachher (neue Namen)
        vor = solver.solve_all(_ohne_umstellung(p), design=True, fatigue=True)
        nach = solver.solve_all(m, design=True, fatigue=True)
        anders = _rechnung_gleich(vor, nach, _abbilden(m))
        if anders:
            rechnung_anders.append(f"{kurz}: {anders[:3]}")
    check(f"U1 {len(dateien)} Dateien: Namen LF<n>/LK<n>/EK<n>, Nummer = Zahl im Namen, keine doppelt",
          not form_falsch, "; ".join(form_falsch[:3]))
    check("U1 … der alte Name ist die Bezeichnung (wo er sich geändert hat)", not bez_falsch,
          "; ".join(bez_falsch[:3]))
    check("U1 … Tabelle alt → neu vollständig im Protokoll, mit „beim Speichern im neuen Format“",
          not tab_falsch, "; ".join(tab_falsch[:3]))
    check("U1 … Rechnung mit den alten Namen = Rechnung nach der Umstellung (bitgleich, Namen nach Tabelle)",
          not rechnung_anders, "; ".join(rechnung_anders[:3]))
    # Browser: ein hochgeladenes altes Modell sagt dasselbe
    from statik3d.web import server as S
    st = S.State(Model())
    S.replace_model(st, _roh(PRUEFKOERPER))
    weblog = " | ".join(st.log)
    check("U1 Browser: ein hochgeladenes altes Modell wird umgestellt, das Protokoll nennt die Tabelle",
          "Hinweis: Namen umgestellt auf LF/LK/EK (Datei der Fassung 8)" in weblog and "S → LF10" in weblog
          and "LF10" in st.model.load_cases, f"{len(st.log)} Zeilen")
    # im Fenster: das Protokoll beim Oeffnen
    w, app = _fenster()
    for p in (os.path.join(DATEN, "ergebnisdatei_e61b184", "kragarm_alt.json"),
              os.path.join(DATEN, "fachbegriffe_68db45b", "modell.json"), PRUEFKOERPER):
        kopie = _kopie(p)
        ok = w.modell_laden(kopie, fragen=False)
        app.processEvents()
        log = w.log.toPlainText()
        lf, ko = _tabellen(w.model)
        zeilen = [f"{a} → {b}" for a, b in list(lf.items()) + list(ko.items()) if a != b]
        check(f"U1 Fenster {os.path.relpath(p, DATEN)}: Protokoll zeigt die Tabelle alt → neu",
              ok and "Hinweis: Namen umgestellt" in log and all(z in log for z in zeilen)
              and "beim Speichern im neuen Format" in log,
              f"{len(zeilen)} Zeilen; {[z for z in log.splitlines() if '→' in z][:2]}")


# --------------------------------------------------------------------------
# U2 - cbg und der Pruefkoerper: umstellen, speichern, wieder oeffnen
# --------------------------------------------------------------------------
def _verweise_vollstaendig(m) -> list:
    """Verweise, die nicht auf ein Objekt des Modells zeigen."""
    fehlt = []
    for c in m.combinations.values():
        for k in list(c.factors) + [k for a in c.alternativen for k in a]:
            if k not in m.load_cases:
                fehlt.append(f"Kombination {c.name}: {k}")
        if c.leading and c.leading not in m.load_cases:
            fehlt.append(f"Leiteinwirkung {c.name}: {c.leading}")
    alle = set(m.load_cases) | set(m.combinations)
    for f in m.fatigue_loads.values():
        for k in [f.case_max, f.case_min] + list(f.folge or []):
            if k and k not in alle:
                fehlt.append(f"Ermüdungslast {f.name}: {k}")
    for s in m.stellungen:
        fehlt += [f"Stellung {s.name}: {k}" for k in s.faelle if k not in m.load_cases]
        fehlt += [f"Stellung {s.name}: {k}" for k in s.kombinationen if k not in m.combinations]
    for g in list(m.winde.values()) + list(m.wasserdruecke.values()):
        for feld in ("lastfall", "lastfall_dyn"):
            k = getattr(g, feld, "")
            if k and k not in m.load_cases:
                fehlt.append(f"{g.name} {feld}: {k}")
    from statik3d.solver import umhuellende_schluessel_im_modell
    envs = set(umhuellende_schluessel_im_modell(m).values()) | {"ULS", "SLS_CH", "SLS_FR", "SLS_QP", "FAT", "CASES"}
    for e in m.bericht:
        art, _, wert = (e.quelle or "").partition(":")
        if (art == "case" and wert not in m.load_cases) or (art == "combo" and wert not in m.combinations) \
                or (art == "env" and wert not in envs):
            fehlt.append(f"Bericht {e.name}: {e.quelle}")
    if m.active_case not in m.load_cases:
        fehlt.append(f"aktiver Lastfall {m.active_case}")
    return fehlt


def _umlauf(titel, quelle) -> tuple:
    """Kopie oeffnen (umstellen), speichern, wieder oeffnen - (Modell nach dem
    ersten, Modell nach dem zweiten Oeffnen, Dict der gespeicherten Datei,
    Sekunden fuer das erste Oeffnen)."""
    from statik3d.model import Model
    kopie = _kopie(quelle)
    t0 = time.time()
    m1 = Model.load(kopie)
    dauer = time.time() - t0
    m1.save(kopie)
    d = _roh(kopie)
    m2 = Model.load(kopie)
    return m1, m2, d, dauer


def _pruefe_umlauf(titel, quelle, mit_stellungen: bool):
    from statik3d.model import _namensnummer
    roh = _roh(quelle)
    m0 = _ohne_umstellung(quelle)
    m1, m2, d, dauer = _umlauf(titel, quelle)
    lf, ko = _tabellen(m1)
    ok, detail = _form_ok(m1)
    check(f"U2 {titel}: Namen LF<n>/LK<n>/EK<n>, Nummern = Zahl im Namen ({dauer:.1f} s)", ok, detail)
    # LK/EK nach der Regel: EK, wenn Alternativen oder schon EK<n>
    falsch = [c["name"] for c in roh.get("combinations", [])
              if m1.combinations[ko[c["name"]]].art
              != ("EK" if c.get("alternativen") or _namensnummer(c["name"])[0] == "EK" else "LK")]
    n_ek = sum(1 for c in m1.combinations.values() if c.art == "EK")
    check(f"U2 {titel}: Art nach der Regel (EK mit Alternativen oder schon EK<n>, sonst LK)",
          not falsch, f"{len(m1.combinations) - n_ek} LK, {n_ek} EK" + (f"; falsch: {falsch[:3]}" if falsch else ""))
    fehlt = _verweise_vollstaendig(m1)
    check(f"U2 {titel}: jeder Verweis zeigt auf ein Objekt (Kombinationen, Ermüdung, Stellungen, Bericht, "
          "Wind, Wasserdruck, aktiver Lastfall)", not fehlt, "; ".join(fehlt[:4]))
    # dieselben Objekte wie vorher, nur unter neuem Namen
    gleich = all(m1.fatigue_loads[n].case_max == (lf.get(f.case_max) or ko.get(f.case_max, f.case_max))
                 for n, f in m0.fatigue_loads.items() if not f.folge) \
        and all(m1.fatigue_loads[n].folge == [lf.get(x, x) for x in f.folge]
                for n, f in m0.fatigue_loads.items() if f.folge)
    check(f"U2 {titel}: Ermüdungslasten nennen die neuen Namen derselben Zustände "
          f"({len(m0.fatigue_loads)} Lasten)", gleich and len(m1.fatigue_loads) == len(m0.fatigue_loads),
          str([(f.case_max, f.folge[:2]) for f in list(m1.fatigue_loads.values())[:2]]))
    if mit_stellungen:
        s0, s1 = m0.stellungen[0], m1.stellungen[0]
        check(f"U2 {titel}: Stellung - Lastfälle und Kombinationen umgestellt",
              s1.faelle == [lf[x] for x in s0.faelle] and s1.kombinationen == [ko[x] for x in s0.kombinationen],
              f"{s0.faelle} → {s1.faelle}, {s0.kombinationen} → {s1.kombinationen}")
        b = [(e.quelle, e.beschriftung) for e in m1.bericht]
        check(f"U2 {titel}: Berichtsbilder - Quellen umgestellt, eingefrorene Texte über den Klartext",
              [q for q, _t in b] == ["case:" + lf["W_links"], "combo:" + ko["K1"], "env:" + ko["Bemessung GZT"],
                                     "env:ULS", "combo:" + ko["GZT3"]]
              and b[0][1] == f"Lastfall {lf['W_links']} · Verschiebung"
              and b[2][1] == f"Umhüllende {ko['Bemessung GZT']} · Verschiebung", str(b[:3]))
        check(f"U2 {titel}: Wind, Wasserdruck, aktiver Lastfall und Leiteinwirkung umgestellt",
              m1.winde["W1"].lastfall == lf["W_links"] and m1.wasserdruecke["WD1"].lastfall == lf["S"]
              and m1.wasserdruecke["WD1"].lastfall_dyn == lf["S"] and m1.active_case == lf["S"]
              and m1.combinations[ko["K1"]].leading == lf["S"],
              f"{m1.winde['W1'].lastfall} {m1.active_case} {m1.combinations[ko['K1']].leading}")
        from statik3d.combinations import gehoert_dem_generator
        erzeugt = [ko[n] for n in ("GZT1", "GZT2", "GZT3", "GZT4", "GZG43", "GZG44", "GZG45", "GZG46")]
        check(f"U2 {titel}: erzeugte Kombinationen bleiben dem Generator (Fingerabdruck), die von Hand nicht",
              all(gehoert_dem_generator(m1.combinations[n]) for n in erzeugt)
              and not gehoert_dem_generator(m1.combinations[ko["K1"]])
              and all(gehoert_dem_generator(m2.combinations[n]) for n in erzeugt),
              str(erzeugt))
    check(f"U2 {titel}: gespeichert in Fassung 9 mit Nummer, Art und Bezeichnung",
          d.get("format") == 9
          and all(x.get("nummer", 0) > 0 and "bezeichnung" in x for x in d["load_cases"])
          and all(x.get("nummer", 0) > 0 and x.get("art") in ("LK", "EK") for x in d["combinations"]),
          f"Fassung {d.get('format')}")
    check(f"U2 {titel}: das zweite Öffnen stellt nichts mehr um, alles gleich",
          getattr(m2, "_umbenennung", None) is None
          and not any("Namen umgestellt" in z for z in m2._ladehinweise)
          and [(n, lc.nummer, lc.bezeichnung) for n, lc in m2.load_cases.items()]
          == [(n, lc.nummer, lc.bezeichnung) for n, lc in m1.load_cases.items()]
          and [(n, c.nummer, c.art, c.bezeichnung, c.factors, c.alternativen) for n, c in m2.combinations.items()]
          == [(n, c.nummer, c.art, c.bezeichnung, c.factors, c.alternativen) for n, c in m1.combinations.items()],
          f"Hinweise beim zweiten Öffnen: {len(m2._ladehinweise)}")
    vorher = m0.check()
    neu = [z for z in m1.check() if z not in vorher]
    check(f"U2 {titel}: check() meldet nichts Neues", not neu, "; ".join(neu[:3]))


def test_u2_cbg_und_pruefkoerper():
    _pruefe_umlauf("Prüfkörper Hallenrahmen", PRUEFKOERPER, mit_stellungen=True)
    cbg = os.path.join(MODELLE, "cbg.json")
    if not os.path.exists(cbg):
        skip("U2 cbg.json", f"nicht gefunden unter {MODELLE} (STATIK3D_R2_MODELLE)")
        return
    _pruefe_umlauf("cbg (Kopie)", cbg, mit_stellungen=False)
    # Datei vor R2-A1 ohne Fingerabdruck: „auto…“ mit Namen GZT/GZG bleibt erzeugt
    from statik3d.model import Model
    from statik3d.combinations import gehoert_dem_generator, generate_combinations
    d = _roh(PRUEFKOERPER)
    for c in d["combinations"]:
        for k in ("nummer", "art", "bezeichnung", "erzeugt", "erzeugt_merkmal"):
            c.pop(k, None)
    for x in d["load_cases"]:
        x.pop("bezeichnung", None)
        x["nummer"] = 0
    m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    lf, ko = _tabellen(m)
    erzeugt = [ko[n] for n in ("GZT1", "GZT2", "GZT3", "GZT4", "GZG43", "GZG44", "GZG45", "GZG46")]
    eigen = [n for n in m.combinations if n not in erzeugt]
    gehoert = all(gehoert_dem_generator(m.combinations[n]) for n in erzeugt) \
        and not any(gehoert_dem_generator(m.combinations[n]) for n in eigen)
    generate_combinations(m)
    check("U2 Datei vor R2-A1 (ohne Fingerabdruck): „auto…“ GZT/GZG bleibt nach der Umstellung erzeugt - "
          "der Generator ersetzt genau sie, die von Hand bleiben",
          gehoert and not any(n in m.combinations for n in erzeugt) and all(n in m.combinations for n in eigen),
          f"erzeugt {erzeugt[:3]}…, von Hand {eigen}")


# --------------------------------------------------------------------------
# U3 - Drehlager (nur mit STATIK3D_R2_GROSS=1)
# --------------------------------------------------------------------------
def _speicher_gb() -> tuple:
    """(Spitze, jetzt) des Arbeitsspeichers dieses Prozesses in GB (Windows)."""
    try:
        import ctypes
        import ctypes.wintypes as W

        class PMC(ctypes.Structure):
            _fields_ = [("cb", W.DWORD), ("PageFaultCount", W.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
                       [(f"f{i}", ctypes.c_size_t) for i in range(6)]
        ctypes.windll.kernel32.GetCurrentProcess.restype = W.HANDLE
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE, ctypes.POINTER(PMC), W.DWORD]
        p = PMC()
        p.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(p), p.cb)
        return p.PeakWorkingSetSize / 1e9, p.WorkingSetSize / 1e9
    except Exception:            # noqa: BLE001 - nicht unter Windows
        return float("nan"), float("nan")


def test_u3_drehlager():
    quelle = os.path.join(MODELLE, "drehlager.json")
    if os.environ.get("STATIK3D_R2_GROSS") != "1":
        skip("U3 drehlager.json", "nur mit STATIK3D_R2_GROSS=1 (165 MB, etwa eine Minute)")
        return
    if not os.path.exists(quelle):
        skip("U3 drehlager.json", f"nicht gefunden unter {MODELLE}")
        return
    from statik3d.model import Model
    roh_k = [c["name"] for c in _roh(quelle).get("combinations", [])]
    kopie = _kopie(quelle)
    t0 = time.time()
    m1 = Model.load(kopie)
    t_laden = time.time() - t0
    spitze, jetzt = _speicher_gb()
    lf, ko = _tabellen(m1)
    ok, detail = _form_ok(m1)
    print(f"     Drehlager: Laden mit Umstellung {t_laden:.1f} s, Speicher Spitze {spitze:.2f} GB, "
          f"danach {jetzt:.2f} GB; {sum(a != b for a, b in lf.items())} Lastfälle und "
          f"{sum(a != b for a, b in ko.items())} Kombinationen umbenannt")
    check(f"U3 Drehlager: Namen umgestellt ({len(m1.load_cases)} LF, {len(m1.combinations)} K; "
          f"{t_laden:.1f} s, Spitze {spitze:.2f} GB)", ok and sorted(ko) == sorted(roh_k), detail)
    fehlt = _verweise_vollstaendig(m1)
    check("U3 Drehlager: jeder Verweis zeigt auf ein Objekt (Ermüdung mit Verlauf, Stellung)", not fehlt,
          "; ".join(fehlt[:4]))
    t1 = time.time()
    c1 = m1.check()
    t_check = time.time() - t1
    check(f"U3 Drehlager: check() ohne FEHLER ({t_check:.1f} s)", not [z for z in c1 if z.startswith("FEHLER")],
          str([z for z in c1 if z.startswith("FEHLER")][:2]))
    t2 = time.time()
    m1.save(kopie)
    t_speichern = time.time() - t2
    t3 = time.time()
    m2 = Model.load(kopie)
    t_wieder = time.time() - t3
    check(f"U3 Drehlager: gespeichert ({t_speichern:.1f} s) und wieder geöffnet ({t_wieder:.1f} s) - "
          "nichts mehr umgestellt", getattr(m2, "_umbenennung", None) is None and list(m2.combinations) ==
          list(m1.combinations) and list(m2.load_cases) == list(m1.load_cases), "")
    print(f"     Drehlager: Speicher Spitze am Ende {_speicher_gb()[0]:.2f} GB")


# --------------------------------------------------------------------------
# U4 - alte Ergebnisdateien
# --------------------------------------------------------------------------
def _roh_ergebnisse(pfad_modell, m) -> dict:
    """Die Ergebnisdatei so, wie sie auf der Platte steht - entpackt, aber
    ohne Pruefung und ohne Umschluesseln."""
    from statik3d import ergebnisse as E
    with open(E.pfad_zu(pfad_modell), "rb") as fh:
        inhalt = E._Leser(fh, m).load()
    for g in E._ERGEBNISGRUPPEN:
        inhalt[g] = {n: E._entpacken_results(d, m) for n, d in (inhalt.get(g) or {}).items()}
    return inhalt


def test_u4_ergebnisdateien():
    from statik3d.model import Model
    from statik3d import ergebnisse as E, solver
    from statik3d.begriffe import UMHUELLENDE
    R = ref()
    dateien = [p for p in modelldateien() if os.path.exists(E.pfad_zu(p))]
    nicht_geladen, alte_namen, zahlen_anders, verworfen = [], [], [], {}
    for p in dateien:
        kurz = os.path.relpath(p, DATEN)
        m = Model.load(p)
        lf, ko = _tabellen(m)
        abb = _abbilden(m)
        try:
            an = E.lesen(E.pfad_zu(p), m)
        except Exception as ex:          # noqa: BLE001
            nicht_geladen.append(f"{kurz}: {ex}")
            continue
        roh = _roh_ergebnisse(p, m)
        # unter neuen Namen
        alt = [n for n in list(an.cases) + list(an.combinations) if n not in m.load_cases and n not in m.combinations]
        alt += [n for n in an.alternativen if re.fullmatch(r"(.+) \[\d+\]", n).group(1) not in m.combinations]
        if alt:
            alte_namen.append(f"{kurz}: {alt[:3]}")
        # Zahlen bytegleich mit der Datei
        for g in ("cases", "combinations", "alternativen"):
            for n, r in roh[g].items():
                r2 = getattr(an, g).get(abb(n))
                if r2 is None or R["ergebnis"](r) != R["ergebnis"](r2) or r2.name != abb(r.name):
                    zahlen_anders.append(f"{kurz}: {g} {n}")
        hinweise = [z for z in an.info.get("umstellung", []) if "verworfen" in z]
        if hinweise:
            verworfen[kurz] = hinweise
        for k, env in roh["envelopes"].items():
            gesucht = [e for e in an.envelopes.values() if _huelle_zahlen(e) == _huelle_zahlen(env)]
            if not gesucht:
                if not any(k in h for h in hinweise):
                    zahlen_anders.append(f"{kurz}: Umhüllende {k} fehlt ohne Hinweis")
                continue
            if list(gesucht[0].names) != [abb(x) for x in env.names]:
                zahlen_anders.append(f"{kurz}: Umhüllende {k} Herkunft {list(gesucht[0].names)}")
        # jede Umhuellende einer Ergebniskombination unter ihrem neuen Namen
        for k, env in an.envelopes.items():
            besitzer = getattr(env, "kombination", None)
            if besitzer in m.combinations and (k != besitzer or env.name != besitzer):
                zahlen_anders.append(f"{kurz}: Umhüllende {k} ({besitzer})")
            if besitzer is None and k not in UMHUELLENDE and k not in {c.typ for c in m.combinations.values()}:
                zahlen_anders.append(f"{kurz}: Umhüllende {k} ohne Besitzer")
    check(f"U4 {len(dateien)} alte Ergebnisdateien laden zum umgestellten Modell", not nicht_geladen,
          "; ".join(nicht_geladen[:2]))
    check("U4 … alle Ergebnisse unter den neuen Namen (Lastfälle, Kombinationen, Alternativen „EK<n> [k]“)",
          not alte_namen, "; ".join(alte_namen[:3]))
    check("U4 … Zahlen bytegleich mit der Datei, Herkunft der Umhüllenden nach der Tabelle",
          not zahlen_anders, "; ".join(zahlen_anders[:3]))
    soll_verworfen = {os.path.join("huellen_schluessel_6791f9f", "alt", "EK1_zu_ULS.json")}
    check("U4 … verworfen und genannt nur, was sich nicht sicher zuordnen lässt (EK1_zu_ULS: die alte "
          "„EK1“ war umbenannt, die neue EK1 ist eine andere)",
          set(verworfen) == soll_verworfen and all("verworfen" in h and "neu rechnen" in h
                                                  for hs in verworfen.values() for h in hs),
          str({k: [h[:60] for h in v] for k, v in verworfen.items()}))

    # R1-Schluessel: mit_kollision - die Umhuellende der EK „ULS“ (jetzt EK3)
    p = os.path.join(DATEN, "huellen_schluessel_6791f9f", "mit_kollision.json")
    m = Model.load(p)
    an = E.lesen(E.pfad_zu(p), m)
    _lf, ko = _tabellen(m)
    ek = ko["ULS"]
    env = an.envelopes.get(ek)
    s = an.summary()
    check(f"U4 R1: Umhüllende der Ergebniskombination „ULS“ unter {ek} (nicht „ULS (Ergebniskombination)“), "
          "die fehlende Umhüllende GZT wird genannt",
          env is not None and env.kombination == ek and list(env.names) == [f"{ek} [{k}]" for k in (1, 2, 3)]
          and "ULS (Ergebniskombination)" not in an.envelopes and "ULS" not in an.envelopes
          and f"„{ek}“ die „Umhüllende GZT“ überschrieben" in s,
          f"{list(an.envelopes)}; {[z for z in s.splitlines() if 'überschrieben' in z][:1]}")
    # ULS_geloescht: eine Umhuellende ohne Ergebniskombination im Modell bleibt, wie sie war
    p = os.path.join(DATEN, "huellen_schluessel_6791f9f", "alt", "ULS_geloescht.json")
    an = E.lesen(E.pfad_zu(p), Model.load(p))
    env = an.envelopes.get("ULS (Ergebniskombination)")
    check("U4 R1: Umhüllende einer gelöschten Ergebniskombination „ULS“ bleibt unter ihrem Schlüssel, "
          "nichts Neues vorgetäuscht",
          env is not None and env.kombination == "ULS" and list(env.names) == ["ULS [1]", "ULS [2]", "ULS [3]"],
          str(list(an.envelopes)))
    # fachbegriffe: die EK „GZT“ (jetzt EK1) - der Berichtseintrag findet seine Umhuellende
    p = os.path.join(DATEN, "fachbegriffe_68db45b", "modell.json")
    m = Model.load(p)
    an = E.lesen(E.pfad_zu(p), m)
    _lf, ko = _tabellen(m)
    quellen = [e.quelle.partition(":")[2] for e in m.bericht if e.quelle.startswith("env:")]
    check("U4 fachbegriffe: Ergebniskombination „GZT“ → EK1, die Berichtsbilder finden ihre Umhüllenden",
          ko["GZT"] == "EK1" and "EK1" in an.envelopes and an.envelopes["ULS"].name == "Umhüllende GZT"
          and all(q in an.envelopes for q in quellen), f"{quellen} in {list(an.envelopes)}")

    # Pruefkoerper: Nachweise finden ihre abgelegten Alternativen
    m = Model.load(PRUEFKOERPER)
    an = E.lesen(E.pfad_zu(PRUEFKOERPER), m)
    _lf, ko = _tabellen(m)
    ek = m.combinations[ko["Bemessung GZT"]]
    alt, warn = solver.ergebnisse_der_alternativen(m, an, ek)
    check("U4 Prüfkörper: die Nachweise finden die abgelegten Alternativen (Theorie II) unter den neuen Namen",
          list(alt) == [f"{ek.name} [{k}]" for k in (1, 2, 3)] and not warn
          and all(alt[k] is an.alternativen[k] for k in alt)
          and set(an.theorie2.kombinationen) == set(alt), f"{list(alt)} {warn[:1]}")
    from statik3d.ec3.design import check_members
    neu = check_members(m, an)
    abdruck = lambda d: {k: (float(mc.util).hex(), mc.governing.get("combo")) for k, mc in d.members.items()}  # noqa: E731
    check("U4 Prüfkörper: EC3 aus der geladenen Datei neu nachgewiesen = Nachweis der Datei (bitgleich, "
          "Kombinationen unter neuen Namen)", abdruck(neu) == abdruck(an.design) and not neu.warnungen
          and neu.combinations == an.design.combinations, str(abdruck(an.design)))
    check("U4 Prüfkörper: Nachweise nennen die neuen Namen (EC3, GZG, Theorie II), Warnungen ohne alte Namen",
          all(re.fullmatch(r"(LK|EK)\d+( \[\d+\])?", n) for n in an.design.combinations)
          and all(re.fullmatch(r"(LK|EK)\d+( \[\d+\])?", mc.governing["combo"]) for mc in an.design.members.values())
          and all(re.fullmatch(r"LK\d+", c.kombination) for c in an.gzg.checks.values())
          and all(re.fullmatch(r"EK\d+ \[\d\]", i.kombination) for i in an.theorie2.kombinationen.values()),
          f"{an.design.combinations[:4]} {[c.kombination for c in an.gzg.checks.values()]}")

    # Oberflaeche: oeffnen, speichern, wieder oeffnen - kein zweites Umschluesseln
    w, app = _fenster()
    kopie = _kopie(PRUEFKOERPER)
    ok = w.modell_laden(kopie, fragen=False)
    app.processEvents()
    log = w.log.toPlainText()
    eintraege = [w.cb_result.itemData(i) for i in range(w.cb_result.count())]
    check("U4 Fenster: Ergebnisse geladen, Auswahl mit neuen Namen, Hinweis im Protokoll",
          ok and w.analysis is not None and ("combo", ko["K1"]) in [tuple(e) for e in eintraege if e]
          and "Ergebnisse unter den beim Öffnen umgestellten Namen geladen" in log,
          str([e for e in eintraege if e][:4]))
    w.save_model()
    app.processEvents()
    k_neu = E.lesen(E.pfad_zu(kopie), Model.load(kopie))
    ok2 = w.modell_laden(kopie, fragen=False)
    app.processEvents()
    log2 = w.log.toPlainText()
    check("U4 Fenster: gespeichert und wieder geöffnet - Ergebnisse geladen, nichts mehr umgestellt",
          ok2 and w.analysis is not None and list(w.analysis.combinations) == list(an.combinations)
          and "Namen umgestellt" not in log2 and "umgestellten Namen" not in log2
          and "umstellung" not in k_neu.info, f"{list(w.analysis.combinations)[:4] if w.analysis else None}")

    # alte Ergebnisdatei neben einem Modell der Fassung 9: verworfen statt fremder Namen
    ordner = tempfile.mkdtemp(prefix="statik3d_umstellung_f9_")
    kopie = _kopie(os.path.join(DATEN, "huellen_schluessel_6791f9f", "ohne_kollision.json"), ordner)
    ergebnis_alt = E.pfad_zu(kopie) + ".alt"
    shutil.copy(E.pfad_zu(kopie), ergebnis_alt)
    Model.load(kopie).save(kopie)
    shutil.copy(ergebnis_alt, E.pfad_zu(kopie))
    try:
        E.lesen(E.pfad_zu(kopie), Model.load(kopie))
        grund = ""
    except ValueError as ex:
        grund = str(ex)
    check("U4 alte Ergebnisdatei neben einem Modell der Fassung 9: verworfen, mit Grund (keine Ergebnisse "
          "unter alten Namen)", "vor der Umstellung" in grund, grund[:100])


def test_u4_nachweise_umschluesseln():
    """Die Felder aller Nachweisarten mit einem Namen - auch die, die der
    Pruefkoerper nicht rechnet (Beulen, Lasteinleitung, Volumen, Anschluesse):
    _namen_umschluesseln geht nach den Feldnamen, nicht nach der Klasse."""
    from statik3d import ergebnisse as E
    from statik3d.solver import Analysis
    from statik3d.model import Model
    from statik3d.ec3.beulen import BeulResults, BeulCheck, EinleitungResults, EinleitungCheck
    from statik3d.ec3.volumen import VolumenResults, VolumenCheck
    from statik3d.joints.anschluss import AnschlussResults, AnschlussCheck
    from statik3d.ec3.design import DesignResults, MemberCheck
    from statik3d.theorie3 import Th3Results, Th3Info
    m = Model()
    tab = {"lastfaelle": {"LF1": "LF1", "W": "LF2"}, "kombinationen": {"K1": "LK1", "Bem": "EK1"},
           "zweideutig": []}
    an = Analysis(m)
    an.beulen = BeulResults(felder={"F": BeulCheck("F", kombination="K1", je_kombination=[{"kombination": "Bem [2]"}],
                                                   hinweise=["Kombination K1 maßgebend"])},
                            kombinationen=["K1", "Bem [2]"], warnungen=["Kombination Bem [1] nicht nachgewiesen"])
    an.lasteinleitung = EinleitungResults(stellen={"S": EinleitungCheck("S", kombination="Bem [1]",
                                                                        interaktion={"kombination": "K1"})},
                                          kombinationen=["Bem [1]"])
    an.volumen = VolumenResults(bereiche={"V": VolumenCheck("V", kombination="W", je_kombination=[{"kombination": "W"}])},
                                kombinationen=["W"])
    an.joints = AnschlussResults(joints={"A": AnschlussCheck("A", kombination="K1",
                                                             je_kombination=[{"kombination": "K1", "eta": 0.5}],
                                                             hinweise=["Ermüdungslast 'K1' gibt es nicht",
                                                                       "Ermüdungslast K1: Ergebnis 'K1' fehlt"])},
                                 combinations=["K1"])
    an.design = DesignResults(members={"St": MemberCheck("St", "IPE", "S235", 1.0, governing={"combo": "Bem [1] = K1"},
                                                         stability=[{"combo": "K1"}])},
                              combinations=["Bem [1] = K1"], gleiche={"Bem [1] = K1": ["Bem [1]", "K1"]},
                              warnungen=["Ermüdungslast F: Ergebnis 'W' fehlt"])
    an.theorie3 = Th3Results(kombinationen={"W": Th3Info(name="W")})
    E._namen_umschluesseln(an, m, tab)
    ok = (an.beulen.felder["F"].kombination == "LK1" and an.beulen.felder["F"].je_kombination[0]["kombination"] == "EK1 [2]"
          and an.beulen.kombinationen == ["LK1", "EK1 [2]"] and an.beulen.felder["F"].hinweise == ["Kombination LK1 maßgebend"]
          and an.beulen.warnungen == ["Kombination EK1 [1] nicht nachgewiesen"]
          and an.lasteinleitung.stellen["S"].kombination == "EK1 [1]"
          and an.lasteinleitung.stellen["S"].interaktion["kombination"] == "LK1"
          and an.volumen.bereiche["V"].kombination == "LF2" and an.volumen.kombinationen == ["LF2"]
          and an.joints.joints["A"].kombination == "LK1" and an.joints.combinations == ["LK1"]
          and an.joints.joints["A"].je_kombination[0]["kombination"] == "LK1"
          and an.joints.joints["A"].hinweise == ["Ermüdungslast 'K1' gibt es nicht",
                                                 "Ermüdungslast K1: Ergebnis 'LK1' fehlt"]
          and an.design.members["St"].governing["combo"] == "EK1 [1] = LK1"
          and an.design.members["St"].stability[0]["combo"] == "LK1"
          and an.design.combinations == ["EK1 [1] = LK1"] and an.design.gleiche == {"EK1 [1] = LK1": ["EK1 [1]", "LK1"]}
          and an.design.warnungen == ["Ermüdungslast F: Ergebnis 'LF2' fehlt"]
          and list(an.theorie3.kombinationen) == ["LF2"] and an.theorie3.kombinationen["LF2"].name == "LF2")
    check("U4 Nachweise aller Arten (EC3 samt Zusammenfassung „A = B“, Beulen, Lasteinleitung, Volumen, "
          "Anschlüsse, Theorie III) und ihre Warnungen folgen der Tabelle - der Name einer Ermüdungslast "
          "(„Ermüdungslast 'K1'“) bleibt", ok,
          f"{an.beulen.kombinationen} {an.design.combinations} {an.design.warnungen}")
    # Ein Name, der einem neuen Namen gleicht, ohne in der Tabelle zu stehen:
    # der Nachweis wird verworfen und genannt
    an = Analysis(Model())
    m2 = Model()
    m2.add_combination("LK1", {"LF1": 1.0})
    an.gzg = __import__("statik3d.gzg", fromlist=["GZGResults"]).GZGResults(kombinationen=["LK1"])
    an.design = DesignResults(combinations=["K1"])
    E._namen_umschluesseln(an, m2, {"lastfaelle": {"LF1": "LF1"}, "kombinationen": {"K1": "LK1"}})
    check("U4 ein veralteter Name, der wie ein neuer heißt („LK1“ ohne Eintrag in der Tabelle): Nachweis "
          "verworfen und genannt, der übrige bleibt",
          an.gzg is None and an.design is not None and an.design.combinations == ["LK1"]
          and any("Verformungsnachweise (GZG) verworfen" in z for z in an.info["umstellung"]),
          str(an.info.get("umstellung")))


# --------------------------------------------------------------------------
# U5 - kreuzende Namen und Stichprobe
# --------------------------------------------------------------------------
def _altes_modell(lastfaelle, kombinationen=(), ermuedung=(), stellung=None, aktiv=None,
                  bericht=(), wind=None) -> dict:
    """Ein Modell der Fassung 8 als Dict, wie eine alte Datei es haelt -
    ohne Nummern (alles 0), mit den gegebenen Namen."""
    from statik3d.model import Model, Combination, FatigueLoad, Berichtseintrag
    from statik3d.bridges.positions import Stellung
    from statik3d.wind import Wind
    m = Model("alt")
    m.add_node(0, 0, 0)
    m.load_cases = {}
    for n in lastfaelle:
        m.add_load_case(n, "Q", activate=False)
    for n, faktoren, alternativen in kombinationen:
        m.combinations[n] = Combination(n, dict(faktoren), "ULS", alternativen=[dict(a) for a in alternativen])
    for n, cmax, cmin, folge in ermuedung:
        m.fatigue_loads[n] = FatigueLoad(n, cmax, cmin, folge=list(folge))
    if stellung is not None:
        m.stellungen.append(Stellung("S1", faelle=list(stellung[0]), kombinationen=list(stellung[1])))
    m.bericht = [Berichtseintrag(f"Bild {i}", q) for i, q in enumerate(bericht)]
    if wind is not None:
        m.winde["W1"] = Wind("W1", lastfall=wind)
    m.active_case = aktiv or lastfaelle[0]
    d = m.to_dict()
    d["format"] = 8
    for x in d["load_cases"]:
        x["nummer"] = 0
        x.pop("bezeichnung", None)
    for c in d["combinations"]:
        for k in ("nummer", "art", "bezeichnung", "erzeugt", "erzeugt_merkmal"):
            c.pop(k, None)
    return d


def _ziele(d) -> dict:
    """Wohin jeder Verweis der alten Datei zeigt: (Art, Position des Objekts in
    der Datei) - Lastfaelle und Kombinationen nach ihrer Reihenfolge."""
    lf = {x["name"]: i for i, x in enumerate(d["load_cases"])}
    ko = {x["name"]: i for i, x in enumerate(d["combinations"])}

    def zustand(n):           # Rechnung und Nachweis lesen die Kombination (all_results)
        return ("K", ko[n]) if n in ko else ("LF", lf.get(n))
    z = {"faktoren": [[("LF", lf[k]) for k in list(c["factors"]) + [k for a in c["alternativen"] for k in a]]
                      for c in d["combinations"]],
         "ermuedung": [[zustand(k) for k in [f["case_max"], f["case_min"]] + list(f["folge"] or []) if k]
                       for f in d["fatigue_loads"]],
         "stellung": [([("LF", lf[k]) for k in s["faelle"]], [("K", ko[k]) for k in s["kombinationen"]])
                      for s in d.get("stellungen") or []],
         "aktiv": ("LF", lf[d["active_case"]]),
         "bericht": [((e["quelle"].partition(":")[0]), ("LF", lf[e["quelle"][5:]]) if e["quelle"].startswith("case:")
                      else ("K", ko[e["quelle"][6:]])) for e in d.get("bericht") or []],
         "wind": [("LF", lf[w["lastfall"]]) for w in d.get("winde") or []]}
    return z


def _ziele_nachher(m) -> dict:
    lf = {n: i for i, n in enumerate(m.load_cases)}
    ko = {n: i for i, n in enumerate(m.combinations)}

    def zustand(n):
        return ("K", ko[n]) if n in ko else ("LF", lf.get(n))
    return {"faktoren": [[("LF", lf.get(k)) for k in list(c.factors) + [k for a in c.alternativen for k in a]]
                         for c in m.combinations.values()],
            "ermuedung": [[zustand(k) for k in [f.case_max, f.case_min] + list(f.folge or []) if k]
                          for f in m.fatigue_loads.values()],
            "stellung": [([("LF", lf.get(k)) for k in s.faelle], [("K", ko.get(k)) for k in s.kombinationen])
                         for s in m.stellungen],
            "aktiv": ("LF", lf.get(m.active_case)),
            "bericht": [(e.quelle.partition(":")[0], ("LF", lf.get(e.quelle[5:])) if e.quelle.startswith("case:")
                         else ("K", ko.get(e.quelle[6:]))) for e in m.bericht],
            "wind": [("LF", lf.get(w.lastfall)) for w in m.winde.values()]}


def test_u5_kreuzende_namen():
    from statik3d.model import Model
    # „LF2“, „A“, „LF1“ ohne Nummern: A soll nicht LF2 werden
    d = _altes_modell(["LF2", "A", "LF1"],
                      [("K1", {"A": 1.0, "LF2": 2.0, "LF1": 1.35}, ()),
                       ("E", {}, ({"A": 1.0}, {"LF2": 1.5, "LF1": 1.0}))],
                      [("F", "A", "LF2", ()), ("V", "", None, ("A", "LF2", "LF1"))],
                      (["A", "LF1"], ["K1", "E"]), "A", ("case:A", "combo:K1", "case:LF2"), "A")
    m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    check("U5 „LF2“, „A“, „LF1“: LF2 und LF1 bleiben, A wird LF3 (nicht LF2); K1 → LK1, E → EK1",
          list(m.load_cases) == ["LF2", "LF3", "LF1"] and m.load_cases["LF3"].bezeichnung == "A"
          and list(m.combinations) == ["LK1", "EK1"], f"{list(m.load_cases)} {list(m.combinations)}")
    check("U5 … kein Verweis zeigt auf einen anderen Lastfall (Faktoren, Alternativen, Ermüdung, Stellung, "
          "Bericht, Wind, aktiver Lastfall)", _ziele_nachher(m) == _ziele(d),
          str(m.combinations["LK1"].factors))
    m2 = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    check("U5 … stabil: zweimal geladen dieselbe Vergabe",
          list(m2.load_cases) == list(m.load_cases) and list(m2.combinations) == list(m.combinations)
          and _ziele_nachher(m2) == _ziele_nachher(m), "")

    # Eine Kombination heisst „LF2“, ein Lastfall soll LF2 werden: nur mit
    # Zwischennamen ohne Kreuzung
    d = _altes_modell(["LF1", "A"], [("LF2", {"A": 1.5}, ()), ("K9", {"LF1": 1.0}, ())],
                      [("F", "LF2", None, ())], (["A"], ["LF2"]), "A", ("combo:LF2", "case:A"), "A")
    m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    check("U5 Kombination „LF2“ neben Lastfall A, der LF2 wird: Kombination → LK1, A → LF2, ohne Kreuzung",
          list(m.load_cases) == ["LF1", "LF2"] and list(m.combinations) == ["LK1", "LK2"]
          and m.combinations["LK1"].factors == {"LF2": 1.5} and m.fatigue_loads["F"].case_max == "LK1"
          and _ziele_nachher(m) == _ziele(d), f"{list(m.load_cases)} {list(m.combinations)} "
                                              f"{m.combinations['LK1'].factors} {m.fatigue_loads['F'].case_max}")
    # andere Schreibweisen: „lf2“ neben „LF2“, „LF 3“
    d = _altes_modell(["lf2", "LF2", "LF 3", "B"], [("lk1", {"lf2": 1.0, "LF2": 2.0}, ()), ("LK1", {"B": 1.0}, ())],
                      aktiv="lf2", bericht=("case:lf2", "case:LF 3"))
    m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    check("U5 „lf2“ neben „LF2“, „LF 3“: LF2 bleibt, LF 3 → LF3, lf2 und B bekommen die nächsten; lk1 neben LK1",
          list(m.load_cases) == ["LF4", "LF2", "LF3", "LF5"] and list(m.combinations) == ["LK2", "LK1"]
          and m.load_cases["LF4"].bezeichnung == "lf2" and _ziele_nachher(m) == _ziele(d),
          f"{list(m.load_cases)} {list(m.combinations)}")
    # Lastfall und Kombination gleichen Namens, Kombination wie eine Alternative
    d = _altes_modell(["LF1", "X"], [("X", {"LF1": 0.2}, ()), ("E", {}, ({"LF1": 1.0}, {"X": 1.5})),
                                     ("E [2]", {"LF1": 0.1}, ())],
                      [("FX", "X", None, ())])
    m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    lf, ko = _tabellen(m)
    hinweise = " ".join(m._ladehinweise)
    check("U5 Lastfall und Kombination „X“, Kombination „E [2]“ neben EK E: getrennt umbenannt, "
          "Ermüdung zeigt auf die Kombination (so wurde gerechnet), beides im Protokoll",
          lf["X"] != ko["X"] and m.fatigue_loads["FX"].case_max == ko["X"]
          and "„X“ hießen gleich" in hinweise and "wie die Alternative 2" in hinweise
          and set(m._umbenennung["zweideutig"]) == {"X", "E [2]"} and _ziele_nachher(m) == _ziele(d),
          f"X → {lf['X']} / {ko['X']}, FX → {m.fatigue_loads['FX'].case_max}")

    # Stichprobe: 300 zufaellige alte Modelle
    zufall = random.Random(20261006)
    namen_lf = ["LF1", "LF2", "LF3", "lf2", "LF 3", "LF03", "LF0", "LF10", "Lf10", "A", "B", "W", "X",
                "LK1", "EK1", "K1", "EK1 [1]", "Umstellung R2 1"]
    namen_k = ["K1", "K2", "LK1", "LK2", "lk1", "LK 3", "EK1", "EK2", "EK 2", "ek3", "X", "A", "LF2", "LF4",
               "GZT1", "GZG2", "EK1 [1]", "EK2 [2]", "K1 [1]", "Umstellung R2 2"]
    fehler = []
    for lauf in range(300):
        lfs = zufall.sample(namen_lf, zufall.randint(1, 7))
        kos = []
        for n in zufall.sample(namen_k, zufall.randint(0, 7)):
            if zufall.random() < 0.4:
                alts = tuple({zufall.choice(lfs): 1.0 + k} for k in range(zufall.randint(1, 3)))
                kos.append((n, {}, alts))
            else:
                kos.append((n, {zufall.choice(lfs): 1.5}, ()))
        alle = lfs + [n for n, _f, _a in kos]
        erm = [(f"F{i}", zufall.choice(alle), zufall.choice([None] + lfs), ()) for i in range(zufall.randint(0, 2))]
        erm += [("V", "", None, tuple(zufall.sample(lfs, min(2, len(lfs)))))] if len(lfs) > 1 else []
        stellung = (zufall.sample(lfs, 1), [n for n, _f, _a in kos][:2])
        bericht = [f"case:{zufall.choice(lfs)}"] + ([f"combo:{kos[0][0]}"] if kos else [])
        d = _altes_modell(lfs, kos, erm, stellung, zufall.choice(lfs), bericht, zufall.choice(lfs))
        try:
            m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
        except Exception as ex:      # noqa: BLE001
            fehler.append(f"Lauf {lauf}: {type(ex).__name__} {ex} - {lfs} {[k[0] for k in kos]}")
            continue
        ok, detail = _form_ok(m)
        if not ok:
            fehler.append(f"Lauf {lauf}: {detail} - {lfs} {[k[0] for k in kos]}")
        elif _ziele_nachher(m) != _ziele(d):
            fehler.append(f"Lauf {lauf}: Verweis zeigt woanders hin - {lfs} {[k[0] for k in kos]}")
        else:
            m2 = Model.from_dict(m.to_dict(), umstellen=True)
            if getattr(m2, "_umbenennung", None) is not None or list(m2.load_cases) != list(m.load_cases):
                fehler.append(f"Lauf {lauf}: Fassung 9 erneut umgestellt")
            arten = {n: c.art for n, c in m.combinations.items()}
            from statik3d.model import _namensnummer
            for (alt, _f, alts), neu in zip(kos, m.combinations):
                soll = "EK" if alts or _namensnummer(alt)[0] == "EK" else "LK"
                if arten[neu] != soll:
                    fehler.append(f"Lauf {lauf}: {alt} → {neu} Art {arten[neu]} statt {soll}")
    check("U5 Stichprobe 300 alte Modelle (Namen aus LF/LK/EK-Formen, Schreibweisen, Kollisionen): keine "
          "Ausnahme, Formen und Nummern eindeutig, jeder Verweis auf dasselbe Objekt, Art nach Regel, Fassung 9 "
          "nicht erneut", not fehler, "; ".join(fehler[:3]))


# --------------------------------------------------------------------------
# U6 - Rechenarbeiter
# --------------------------------------------------------------------------
def test_u6_rechenarbeiter():
    from statik3d.model import Model
    from statik3d.examples_lib import build_example
    from statik3d import jobs
    m = build_example("hall")
    d = m.to_dict()
    m2 = Model.from_dict(d)
    check("U6 to_dict schreibt Fassung 9, from_dict stellt nichts um (hall mit S, W_links, GZT1 …)",
          d.get("format") == 9 and getattr(m2, "_umbenennung", None) is None and not m2._ladehinweise
          and list(m2.load_cases) == list(m.load_cases) and list(m2.combinations) == list(m.combinations),
          f"Fassung {d.get('format')}, {list(m2.load_cases)}")
    r_lf = jobs._job_solve_case(d, "W_links")
    r_k = jobs._job_solve_combination(d, "GZT3")
    zusammen = jobs._job_solve_all(d)
    check("U6 Arbeiter (solve_case, solve_combination, solve_all) rechnen unter den Namen der Hauptsitzung, "
          "ohne Umstellung und ohne Hinweis",
          r_lf.name == "W_links" and r_k.name == "GZT3" and "Namen umgestellt" not in zusammen
          and "umgestellten Namen" not in zusammen, f"{r_lf.name} {r_k.name}")
    # Arbeiter mit einem Modell aus einer alten Datei: die Hauptsitzung hat
    # umgestellt, der Arbeiter bekommt Fassung 9 und rechnet unter LF/LK
    alt = Model.load(PRUEFKOERPER)
    d = alt.to_dict()
    lf, ko = _tabellen(alt)
    r = jobs._job_solve_combination(d, ko["K1"])
    check("U6 umgestelltes Modell an den Arbeiter: Fassung 9, kein zweites Umstellen, Name LK…",
          d.get("format") == 9 and r.name == ko["K1"] and Model.from_dict(d)._umbenennung is None, r.name)


# --------------------------------------------------------------------------
# U7 - Speichern nach der Umstellung, Lesen mit dem Stand vor A2
# --------------------------------------------------------------------------
def test_u7_speichern():
    from statik3d.model import Model
    kopie = _kopie(PRUEFKOERPER)
    m = Model.load(kopie)
    m.save(kopie)
    d = _roh(kopie)
    lf = {x["name"]: (x["nummer"], x["bezeichnung"]) for x in d["load_cases"]}
    ko = {x["name"]: (x["nummer"], x["art"], x["bezeichnung"]) for x in d["combinations"]}
    check("U7 gespeichert: Fassung 9, Nummer, Art und Bezeichnung in der Datei",
          d["format"] == 9 and lf["LF10"] == (10, "S") and lf["LF9"] == (9, "")
          and ko["LK9"] == (9, "LK", "K1") and ko["EK8"] == (8, "EK", "Bemessung GZT") and ko["EK7"] == (7, "EK", ""),
          f"{lf} {list(ko.items())[:3]}")
    altbaum = os.environ.get("STATIK3D_R2_ALTBAUM", "")
    if not altbaum or not os.path.isdir(os.path.join(altbaum, "statik3d")):
        skip("U7 Lesen mit dem Stand vor A2", "STATIK3D_R2_ALTBAUM=<Baum ff99eb7> nicht gesetzt")
        return
    skript = ("import sys, json; sys.path.insert(0, sys.argv[1]); from statik3d.model import Model, FORMAT_VERSION;"
              "m = Model.load(sys.argv[2]);"
              "print(json.dumps({'fassung': FORMAT_VERSION, "
              "'lf': [(n, lc.nummer, lc.bezeichnung) for n, lc in m.load_cases.items()],"
              "'k': [(n, c.nummer, c.art, c.bezeichnung, c.erzeugt) for n, c in m.combinations.items()],"
              "'fl': [(f.case_max, f.folge) for f in m.fatigue_loads.values()],"
              "'st': [(s.faelle, s.kombinationen) for s in m.stellungen], 'aktiv': m.active_case,"
              "'check': [z for z in m.check() if z.startswith('FEHLER')]}))")
    p = subprocess.run([sys.executable, "-c", skript, altbaum, kopie], capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ, PYTHONUTF8="1"), cwd=altbaum)
    try:
        alt = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:            # noqa: BLE001
        alt = {}
    check("U7 der Stand vor A2 (ff99eb7, Fassung 8) liest die Datei der Fassung 9: Namen, Nummern, Art, "
          "Bezeichnung, Verweise, ohne FEHLER",
          alt.get("fassung") == 8
          and alt.get("lf") == [[n, lc.nummer, lc.bezeichnung] for n, lc in m.load_cases.items()]
          and alt.get("k") == [[n, c.nummer, c.art, c.bezeichnung, c.erzeugt] for n, c in m.combinations.items()]
          and alt.get("fl") == [[f.case_max, f.folge] for f in m.fatigue_loads.values()]
          and alt.get("st") == [[s.faelle, s.kombinationen] for s in m.stellungen]
          and alt.get("aktiv") == m.active_case and alt.get("check") == [],
          (p.stderr.strip().splitlines() or [""])[-1][:120] if not alt else f"Fassung {alt.get('fassung')}")


# --------------------------------------------------------------------------
# U8 - Beispiele
# --------------------------------------------------------------------------
def test_u8_beispiele():
    from statik3d.model import Model
    from statik3d.examples_lib import build_example
    from statik3d import solver
    R = ref()
    soll = json.load(open(os.path.join(DATEN, "huellen_schluessel_6791f9f", "beispiele.json"), encoding="utf-8"))
    for b in ("frame", "truss", "hall", "gate", "contact"):
        m = build_example(b)
        namen = (list(m.load_cases), list(m.combinations))
        d = m.to_dict()
        m2 = Model.from_dict(json.loads(json.dumps(d)))
        unberuehrt = getattr(m, "_umbenennung", None) is None and getattr(m2, "_umbenennung", None) is None \
            and (list(m2.load_cases), list(m2.combinations)) == namen and d["format"] == 9
        an = solver.solve_all(m2, design=True, fatigue=True)
        ist = R["verdichtet"](R["analyse"](an))
        # Vergleich mit derselben Rechnung ohne den Umlauf ueber die Datei: die
        # gespeicherte Referenz (6791f9f) ist seit den Korrekturen an Ermuedung und
        # Kontakt im Sammelzweig ueberholt (08.11.2026: Sammelzweig 75b1200 ohne R2-A2
        # rechnet hall/gate/contact Fingerabdruck fuer Fingerabdruck wie mit R2-A2)
        soll_b = R["verdichtet"](R["analyse"](solver.solve_all(build_example(b), design=True, fatigue=True)))
        anders = [f"{teil}/{k}" for teil in soll_b if isinstance(soll_b[teil], dict)
                  for k in set(soll_b[teil]) | set(ist.get(teil) or {})
                  if (ist.get(teil) or {}).get(k) != soll_b[teil].get(k)]
        anders += [teil for teil in soll_b if not isinstance(soll_b[teil], dict) and ist.get(teil) != soll_b[teil]]
        check(f"U8 {b}: A2 fasst die eingebauten Namen nicht an (Umlauf über Fassung 9), Rechnung bitgleich "
              "mit der Referenz", unberuehrt and not anders,
              f"{namen[0][:5]} {namen[1][:2]}" + (f"; anders: {anders[:4]}" if anders else ""))


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung von 1fea7af (06.10.2026): V1 bis V8,
# S3 (Mutanten), S4 (Protokoll)
# --------------------------------------------------------------------------
KONTAKT = os.path.join(DATEN, "umstellung_ff99eb7", "kontakt.json")


def _alte_namen_in_meldungen(meldungen, m) -> list:
    """check()-Meldungen mit den alten Namen: neue Namen in Anfuehrung zurueck
    ueber die Tabelle, „verwaist: “ weg - so vergleichbar mit dem Stand vor
    der Umstellung."""
    lf, ko = _tabellen(m)
    rueck = {b: a for a, b in list(lf.items()) + list(ko.items())}
    return sorted(re.sub(r"'([^']*)'", lambda t: "'" + rueck.get(t.group(1), t.group(1)) + "'", z)
                  .replace(m.VERWAIST, "") for z in meldungen)


def _verwaist_dict() -> dict:
    """Ein altes Modell (Fassung 8) mit Verweisen auf geloeschte Objekte, wie
    verwaist_test.py der Gegenpruefung: Lastfall LF2 mit Berichtsbild und
    Wind angelegt und wieder geloescht; Kombination LK1 mit Ermuedungslast,
    Bild und Stellung angelegt und wieder geloescht (wie die Oberflaeche:
    del); dazu eine Kombination K9 mit dem nie angelegten Lastfall LF3."""
    from statik3d.examples_lib import build_example
    from statik3d.model import Combination, FatigueLoad, Berichtseintrag
    from statik3d.wind import Wind
    from statik3d.bridges.positions import Stellung
    m = build_example("hall")
    m.combinations = {n: c for n, c in m.combinations.items() if n in ("GZT1", "GZT2")}
    m.add_load_case("LF2", "Q", "Probe", activate=False)
    m.load_node(0, Fz=-1.0, case="LF2")
    m.bericht.append(Berichtseintrag("Bild LF2", "case:LF2", "Verschiebung",
                                     beschriftung="Lastfall LF2 · Verschiebung"))
    m.winde["W1"] = Wind("W1", lastfall="LF2", staebe=["Riegel"])
    m.remove_load_case("LF2")
    # Loeschen raeumt Wind-Verweis und Berichtsbild seit PR #20 (03.10.2026) selbst ab;
    # eine alte Datei kann beide noch tragen - so stehen sie hier
    m.winde["W1"].lastfall = "LF2"
    if not any(e.quelle == "case:LF2" for e in m.bericht):
        m.bericht.append(Berichtseintrag("Bild LF2", "case:LF2", "Verschiebung",
                                         beschriftung="Lastfall LF2 · Verschiebung"))
    m.combinations["LK1"] = Combination("LK1", {"S": 1.0}, "FAT", "Schnee als Ermüdung")
    m.fatigue_loads["FS"] = FatigueLoad("FS", "LK1", None, cycles=1e5)
    m.bericht.append(Berichtseintrag("Bild LK1", "combo:LK1", "Verschiebung",
                                     beschriftung="Kombination LK1 · Verschiebung"))
    m.stellungen.append(Stellung("S1", 0.0, "zu", faelle=["LF1"], kombinationen=["LK1"]))
    del m.combinations["LK1"]
    m.combinations["K9"] = Combination("K9", {"LF1": 1.0, "LF3": 2.0}, "ULS", "mit fehlendem LF3")
    d = m.to_dict()
    d["format"] = 8
    return json.loads(json.dumps(d))


def test_v9_aenderung_nach_dem_oeffnen():
    """Die Ergebnisdatei eines umgestellten Modells wird gegen den Stand mit den
    alten Namen geprueft - aber nur, solange das Modell seit der Umstellung
    unveraendert ist (08.11.2026, Zusammenfuehrung mit der Kennung N38)."""
    from statik3d.model import Model
    from statik3d import ergebnisse as E
    kopie = _kopie(PRUEFKOERPER)
    m = Model.load(kopie)
    try:
        an = E.lesen(E.pfad_zu(kopie), m)
        ok = an is not None and m._umbenennung is not None
    except ValueError as ex:
        ok = False
        print("   ", ex)
    check("V9 umgestelltes Modell, unverändert: die Ergebnisdatei passt", ok)
    m.add_load_case("Neu", "Q", "nach dem Öffnen angelegt", activate=False)
    try:
        E.lesen(E.pfad_zu(kopie), m)
        check("V9 … nach einer Änderung passt sie nicht mehr", False, "gelesen")
    except ValueError as ex:
        check("V9 … nach einer Änderung passt sie nicht mehr", "passt nicht" in str(ex), str(ex)[:90])


def test_v1_verwaiste_verweise():
    """F1: ein Verweis auf ein geloeschtes Objekt mit einem Namen der Form
    LF<n>/LK<n> wurde nach der Umstellung still gueltig - Ermuedung FS zeigte
    auf GZT1, Wind W1 schrieb in den Schneelastfall."""
    from statik3d.model import Model
    from statik3d import wind
    d = _verwaist_dict()
    vor = Model.from_dict(json.loads(json.dumps(d)))
    m = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    meld_vor = sorted(z for z in vor.check() if z.startswith(("FEHLER", "WARNUNG")))
    meld_nach = _alte_namen_in_meldungen([z for z in m.check() if z.startswith(("FEHLER", "WARNUNG"))], m)
    check("V1 check() meldet dieselben FEHLER und WARNUNGEN wie vor der Umstellung (Namen zurückgeführt)",
          meld_vor == meld_nach and any("'LK1'" in z for z in meld_vor),
          f"{len(meld_vor)} Meldungen; anders: {sorted(set(meld_vor) ^ set(meld_nach))[:2]}")
    v = m.VERWAIST
    check("V1 jeder verwaiste Verweis heißt „verwaist: …“ (Ermüdung, Stellung, Bild, Wind, Faktor)",
          m.fatigue_loads["FS"].case_max == v + "LK1" and m.stellungen[0].kombinationen == [v + "LK1"]
          and [e.quelle for e in m.bericht][-2:] == [f"case:{v}LF2", f"combo:{v}LK1"]
          and m.winde["W1"].lastfall == v + "LF2"
          and set(m.combinations[m._umbenennung["kombinationen"]["K9"]].factors) == {"LF1", v + "LF3"},
          f"FS {m.fatigue_loads['FS'].case_max!r}, Wind {m.winde['W1'].lastfall!r}")
    check("V1 … der Name gehört keinem Objekt, die neuen LF2, LK1 bleiben unberührt",
          not any(n.startswith(v) for n in list(m.load_cases) + list(m.combinations))
          and "LF2" in m.load_cases and "LK1" in m.combinations, str(list(m.load_cases)))
    check("V1 … das Protokoll nennt die verwaisten Verweise",
          any("verwaist" in z and "FS" in z for z in m._ladehinweise), "")
    vorher = {n: lc.n_loads for n, lc in m.load_cases.items()}
    wind.lasten_erzeugen(m, m.winde["W1"])
    nachher = {n: lc.n_loads for n, lc in m.load_cases.items()}
    fremd = [n for n in vorher if nachher[n] != vorher[n]]
    check("V1 Wind W1 schreibt in einen eigenen Lastfall, in keinen fremden (vorher: in den Schneelastfall)",
          not fremd and m.winde["W1"].lastfall not in vorher and nachher[m.winde["W1"].lastfall] > 0,
          f"geändert {fremd}, Wind in {m.winde['W1'].lastfall!r}")


def test_v2_anhaengen():
    """F2: beim Anhaengen wird die Quelle nicht umgestellt - umgestellt
    legte anhaengen ihre LF1/LF2 mit denen des Ziels zusammen."""
    from statik3d.model import Model
    from statik3d import importers
    q = Model("Quelle")
    a, b = q.add_node(10, 0, 0), q.add_node(12, 0, 0)
    q.lastfall_umbenennen("LF1", "G")
    q.load_node(a, Fz=-1000.0, case="G")
    q.add_load_case("W", "W", "Wind", activate=False)
    q.load_node(b, Fx=500.0, case="W")
    d = q.to_dict()
    d["format"] = 8
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_umstellung_anh_"), "quelle.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(d, f)
    z = Model("Ziel")
    n0, n1 = z.add_node(0, 0, 0), z.add_node(2, 0, 0)
    z.load_node(n0, Fz=-7000.0, case="LF1")
    z.add_load_case("LF2", "Q", "Nutzlast", activate=False)
    z.load_node(n1, Fz=-3000.0, case="LF2")
    log = []
    importers.import_file(pfad, model=z, log=log)
    lasten = {n: sorted(round(nl.F[0] + nl.F[2]) for nl in lc.nodal_loads) for n, lc in z.load_cases.items()}
    check("V2 Anhängen einer alten Datei: vier getrennte Lastfälle LF1, LF2, G, W wie vor A2",
          lasten == {"LF1": [-7000], "LF2": [-3000], "G": [-1000], "W": [500]}
          and not any("zusammengelegt" in z_ and "davon" in z_ and "(davon 0" not in z_ for z_ in log),
          str(lasten))


def test_v3_ausloeser():
    """L3: umgestellt wird beim Oeffnen einer Datei, gleich welcher Fassung -
    auch Fassung 9 mit freien Namen; from_dict ohne Wunsch, Rechenarbeiter
    und Kopien nie."""
    from statik3d.model import Model, Combination
    from statik3d.examples_lib import build_example
    from statik3d import jobs
    m = build_example("frame")
    m.add_load_case("W", "W", "Wind von Hand", activate=False, nummer=5)
    m.load_node(1, Fx=1000.0, case="W")
    m.combinations["K1"] = Combination("K1", {"LF1": 1.35, "W": 1.5}, "ULS", "von Hand")
    m.combinations["Bem"] = Combination("Bem", {}, "ULS", "EK von Hand", alternativen=[{"LF1": 1.35}, {"W": 1.5}])
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_umstellung_f9_"), "hand.json")
    m.save(pfad)
    m9 = Model.load(pfad)
    check("V3 Fassung 9 mit freien Namen wird beim Öffnen umgestellt (W mit Nr. 5 → LF5, K1 → LK1, Bem → EK1)",
          _roh(pfad)["format"] == 9 and list(m9.load_cases) == ["LF1", "LF5"]
          and list(m9.combinations) == ["LK1", "EK1"] and m9._umbenennung["geaendert"]
          and any("Namen umgestellt" in z for z in m9._ladehinweise),
          f"{list(m9.load_cases)} {list(m9.combinations)}")
    roh = Model.from_dict(_roh(pfad))
    kopie = m9.copy()
    check("V3 from_dict ohne Wunsch und eine Kopie stellen nichts um",
          list(roh.load_cases) == ["LF1", "W"] and roh._umbenennung is None and not roh._ladehinweise
          and list(kopie.load_cases) == list(m9.load_cases), f"{list(roh.load_cases)}")
    r = jobs._job_solve_combination(m.to_dict(), "K1")
    check("V3 Rechenarbeiter mit freien Namen im Speicher stellt nicht um", r.name == "K1", r.name)
    d = m.to_dict()
    d["format"] = 8
    d["combinations"].append({"name": "Bemessung GZT", "factors": {"LF1": 1.35}, "typ": "ULS",
                              "description": "Bemessung GZT (Ergebniskombination)", "alternativen": []})
    mr = Model.from_dict(d, umstellen=True)
    c = mr.combinations[mr._umbenennung["kombinationen"]["Bemessung GZT"]]
    check("V3 eine als Summe gespeicherte RFEM-Ergebniskombination („(Ergebniskombination)“) wird EK",
          c.art == "EK" and c.name.startswith("EK"), f"{c.name} {c.art}")
    m2 = Model.load(pfad)
    m2.save(pfad)
    m3 = Model.load(pfad)
    check("V3 regelgerecht gespeichert: das nächste Öffnen ändert nichts (auch keine Nummer)",
          m3._umbenennung is None and not m3._ladehinweise
          and [(n, lc.nummer) for n, lc in m3.load_cases.items()]
          == [(n, lc.nummer) for n, lc in m2.load_cases.items()], "")


def _geteilt_dict() -> dict:
    """Ein altes Modell mit einer nach Situation geteilten RFEM-
    Ergebniskombination („Bem (Grundstellung)“, „Bem (Ankerausfall)“), einem
    einzelnen Teil ohne Gegenstueck und einer RFEM-Ergebniskombination, die
    RFEM als Summe lieferte."""
    from statik3d.model import Model, Combination, Situation
    m = Model("geteilt")
    m.add_node(0, 0, 0)
    m.situationen["Ankerausfall"] = Situation("Ankerausfall")
    m.add_load_case("A", "Q", activate=False)
    m.load_cases["A"].situation = "Ankerausfall"
    m.combinations["K1"] = Combination("K1", {"LF1": 1.5}, "ULS", "Summe")
    m.combinations["Bem (Grundstellung)"] = Combination(
        "Bem (Grundstellung)", {}, "ULS", "Bem (Ergebniskombination)", alternativen=[{"LF1": 1.35}, {"LF1": 1.0}])
    m.combinations["Bem (Ankerausfall)"] = Combination(
        "Bem (Ankerausfall)", {}, "ULS", "Bem (Ergebniskombination)", situation="Ankerausfall",
        alternativen=[{"A": 1.35}, {"A": 1.0}])
    m.combinations["X"] = Combination("X", {"LF1": 1.0}, "ULS", "X (Ergebniskombination)")
    m.combinations["Y (Ankerausfall)"] = Combination(
        "Y (Ankerausfall)", {}, "SLS_CH", "Y", situation="Ankerausfall", alternativen=[{"A": 1.0}])
    d = m.to_dict()
    d["format"] = 8
    return json.loads(json.dumps(d))


def test_v4_geteilte_ergebniskombinationen():
    """L2: Teile einer nach Situation geteilten Ergebniskombination bekommen
    eine gemeinsame Nummer mit der Situation in Klammern (Variante a); eine
    RFEM-Ergebniskombination als Summe wird EK."""
    from statik3d.model import Model
    m = Model.from_dict(_geteilt_dict(), umstellen=True)
    vorher = Model.from_dict(_geteilt_dict()).check()
    k = {n: (c.art, c.nummer, c.bezeichnung) for n, c in m.combinations.items()}
    check("V4 „Bem (Grundstellung)“/„Bem (Ankerausfall)“ → EK1 (Grundstellung)/EK1 (Ankerausfall), "
          "Bezeichnung Bem; „X“ (Summe aus RFEM) → EK2; einzelner Teil Y → EK3; K1 → LK1",
          k == {"LK1": ("LK", 1, "K1"), "EK1 (Grundstellung)": ("EK", 1, "Bem"),
                "EK1 (Ankerausfall)": ("EK", 1, "Bem"), "EK2": ("EK", 2, "X"),
                "EK3": ("EK", 3, "Y (Ankerausfall)")}, str(k))
    neu = [z for z in m.check() if z.startswith(("FEHLER", "WARNUNG")) and z not in vorher]
    check("V4 … keine neue Meldung, auch keine Warnung „Nr. … gehört mehreren“", not neu, str(neu[:2]))
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_umstellung_geteilt_"), "g.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    check("V4 … gespeichert und wieder geöffnet: regelgerecht, nichts umgestellt",
          m2._umbenennung is None and list(m2.combinations) == list(m.combinations), str(list(m2.combinations)))
    quelle = os.path.join(MODELLE, "drehlager.json")
    if os.environ.get("STATIK3D_R2_GROSS") != "1" or not os.path.exists(quelle):
        skip("V4 Drehlager", "nur mit STATIK3D_R2_GROSS=1 und der Datei unter STATIK3D_R2_MODELLE")
        return
    md = Model.load(_kopie(quelle))
    lf, ko = _tabellen(md)
    teile = {a: b for a, b in ko.items() if "(Grundstellung)" in a or "(Ankerausfall)" in a}
    check("V4 Drehlager: die geteilten Ergebniskombinationen heißen EK5 (Grundstellung), EK5 (Ankerausfall), "
          "EK6 (Grundstellung), EK6 (Ankerausfall); 52 Nummern für 54 Kombinationen",
          sorted(teile.values()) == ["EK5 (Ankerausfall)", "EK5 (Grundstellung)", "EK6 (Ankerausfall)",
                                     "EK6 (Grundstellung)"]
          and len({c.nummer for c in md.combinations.values()}) == 52
          and not [z for z in md.doppelte_nummern()], str(teile))


def test_v5_bericht_und_felder():
    """L1: Results.info["factors"], Schwingung (dyn["lastfall"], log) und
    Knicklaengen (grundzustand) - der Bericht nennt danach die neuen Namen."""
    from statik3d.model import Model
    from statik3d import ergebnisse as E
    from statik3d.report import Report
    kopie = _kopie(PRUEFKOERPER)
    m = Model.load(kopie)
    an = E.lesen(E.pfad_zu(kopie), m)
    text = re.sub(r"<[^>]+>", " ", Report(m, an).html())
    faktoren = [" ".join(t.split()) for t in re.findall(r"Lastfaktoren\s+([^\n]{0,80})", text)]
    namen = {x for t in faktoren for x in re.findall(r"·(\S+)", t)}
    lf, _ko = _tabellen(m)
    check("V5 Bericht: „Lastfaktoren“ nennen die neuen Namen (LF10 statt S, LF11 statt W_links)",
          bool(faktoren) and namen <= set(m.load_cases) and lf["S"] in namen, str(sorted(namen)))
    check("V5 Knicklängen: Grundzustand S → LF10, im Bericht „Grundzustand: LF10“",
          an.knicklaengen.grundzustand == lf["S"] and f"Grundzustand: {lf['S']}." in text,
          repr(an.knicklaengen.grundzustand))
    from statik3d.solver import Analysis
    from statik3d.schwingung import SchwingungsErgebnis
    a2 = Analysis(Model())
    a2.schwingung = SchwingungsErgebnis("S1", "WD1", dyn={"lastfall": "Wasser S dyn", "D": 0.1},
                                        log=["Lastfall Wasser S dyn (Druckschwankung) gerechnet"])
    E._namen_umschluesseln(a2, Model(), {"lastfaelle": {"Wasser S dyn": "LF3"}, "kombinationen": {}})
    check("V5 Schwingung: dyn[„lastfall“] und Protokoll nennen den neuen Namen",
          a2.schwingung.dyn["lastfall"] == "LF3"
          and a2.schwingung.log == ["Lastfall LF3 (Druckschwankung) gerechnet"], str(a2.schwingung.log))


def test_v6_laufzeit():
    """S1: die Umstellung waechst linear - 4000 Kombinationen in hoechstens
    5 s (gemessen in der Gegenpruefung von 1fea7af: 50 s), cbg hoechstens 1 s."""
    from statik3d.model import Model, Combination
    m = Model("s")
    m.add_node(0, 0, 0)
    for i in range(20):
        m.add_load_case(f"Fall {i}", "Q", activate=False)
    for i in range(4000):
        m.combinations[f"Kombi {i}"] = Combination(f"Kombi {i}", {f"Fall {i % 20}": 1.0}, "ULS")
    d = m.to_dict()
    d["format"] = 8
    d = json.loads(json.dumps(d))
    t = time.perf_counter()
    m2 = Model.from_dict(d, umstellen=True)
    dauer = time.perf_counter() - t
    check(f"V6 4000 Kombinationen und 20 Lastfälle: Umstellung in {dauer:.2f} s (höchstens 5 s)",
          dauer <= 5.0 and list(m2.combinations)[-1] == "LK4000", "")
    cbg = os.path.join(MODELLE, "cbg.json")
    if not os.path.exists(cbg):
        skip("V6 cbg", f"nicht gefunden unter {MODELLE}")
        return
    kopie = _kopie(cbg)
    t0 = time.perf_counter()
    Model.load(kopie, umstellen=False)
    t1 = time.perf_counter()
    mc = Model.load(kopie)
    t2 = time.perf_counter()
    check(f"V6 cbg: Öffnen mit Umstellung {t2 - t1:.2f} s, ohne {t1 - t0:.2f} s (höchstens 1 s)",
          t2 - t1 <= 1.0 and mc._umbenennung["geaendert"], "")


def test_v7_geaendert():
    """S2: nach einer Umstellung gilt das Modell als geaendert - Stern im
    Titel, Rueckfrage beim Schliessen mit dem Grund „Namen umgestellt“."""
    w, app = _fenster()
    kopie = _kopie(PRUEFKOERPER)
    ok = w.modell_laden(kopie, fragen=False)
    app.processEvents()
    grund = w.ungespeichert()
    check("V7 nach dem Öffnen einer umgestellten Datei: geändert, Stern im Titel",
          ok and "Namen umgestellt" in grund and "*" in w.windowTitle(), f"{grund!r} {w.windowTitle()!r}")
    gefragt = []
    alt_env = os.environ.pop("STATIK3D_UNGESPEICHERT", None)
    w._frage_speichern_verwerfen = lambda anlass, g: (gefragt.append((anlass, g)), "abbrechen")[1]
    try:
        weiter = w._ungespeichert_fragen("Beenden")
    finally:
        del w._frage_speichern_verwerfen
        if alt_env is not None:
            os.environ["STATIK3D_UNGESPEICHERT"] = alt_env
    check("V7 Schließen fragt mit dem Grund „Namen umgestellt“ (Abbrechen hält an)",
          not weiter and gefragt and "Namen umgestellt" in gefragt[0][1], str(gefragt))
    w.save_model()
    app.processEvents()
    check("V7 nach dem Speichern: nichts mehr ungespeichert, kein Stern", not w.ungespeichert()
          and "*" not in w.windowTitle(), w.windowTitle())
    w.modell_laden(kopie, fragen=False)
    app.processEvents()
    check("V7 wieder geöffnet (Fassung 9, regelgerecht): nicht geändert", not w.ungespeichert(), w.ungespeichert())


def test_v8_webstart_kommandozeile():
    """L4/L5: der Webstart mit --modell zeigt den Ladehinweis; die
    Kommandozeile nimmt einen alten Lastfallnamen ueber die Bezeichnung an
    und meldet einen unbekannten verstaendlich."""
    from statik3d.model import Model
    from statik3d.web import server as S
    kopie = _kopie(PRUEFKOERPER)
    st = S.State(Model.load(kopie))
    check("V8 Webstart: das Protokoll des Browsers zeigt den Ladehinweis",
          any("Hinweis: Namen umgestellt" in z for z in st.log), f"{len(st.log)} Zeilen")
    umg = dict(os.environ, PYTHONUTF8="1")
    wurzel = os.path.dirname(HIER)
    p = subprocess.run([sys.executable, "-m", "statik3d.cli", kopie, "--analyse", "lastfall", "--lastfall", "S"],
                       capture_output=True, text=True, encoding="utf-8", env=umg, cwd=wurzel)
    check("V8 Kommandozeile: alter Name „S“ über die Bezeichnung eindeutig → LF10, gerechnet",
          p.returncode == 0 and "Lastfall „S“ heißt jetzt LF10" in p.stdout,
          (p.stdout + p.stderr).strip().splitlines()[-1:] if p.returncode else "")
    p = subprocess.run([sys.executable, "-m", "statik3d.cli", kopie, "--analyse", "lastfall", "--lastfall",
                        "Quatsch"], capture_output=True, text=True, encoding="utf-8", env=umg, cwd=wurzel)
    check("V8 Kommandozeile: unbekannter Name - verständliche Meldung, kein Traceback",
          p.returncode == 2 and "„Quatsch“ gibt es nicht" in p.stderr and "Traceback" not in p.stderr,
          p.stderr.strip()[:120])


def test_s3_mutanten():
    """S3: Pruefungen fuer die Stellen, die in der Gegenpruefung kein Test
    bemerkte (mutanten_ergebnis.txt): contact_frozen_from, grundlast,
    kontakt_eingefroren, start_angeboten_von (Klartext in Results.info),
    lastfall_nr, info["umhuellende"], info["umhuellende_schluessel"] und die
    Nummernfelder einer alten Datei."""
    from statik3d.model import Model
    from statik3d import ergebnisse as E
    kopie = _kopie(KONTAKT)
    m = Model.load(kopie)
    an = E.lesen(E.pfad_zu(kopie), m)
    lf, _ko = _tabellen(m)
    eg, hub, h3 = lf["Eigengewicht"], lf["Hub 1"], lf["H3"]
    info = {n: an.cases[n].info for n in an.cases}
    check("S3 Kontaktmodell: Lastfälle umgestellt (Eigengewicht, Hub 1, H3 → LF6, LF7, LF8; LF5 bleibt)",
          (eg, hub, h3) == ("LF6", "LF7", "LF8") and "LF5" in m.load_cases, str(lf))
    check("S3 contact_frozen_from nennt den neuen Lastfall",
          info["LF5"].get("contact_frozen_from") == hub and info[h3].get("contact_frozen_from") == hub,
          str({n: i.get("contact_frozen_from") for n, i in info.items()}))
    check("S3 grundlast nennt den neuen Lastfall",
          all(info[n].get("grundlast") == [eg] for n in (hub, "LF5", h3)),
          str({n: i.get("grundlast") for n, i in info.items()}))
    check("S3 info[„kontakt_eingefroren“] unter den neuen Namen",
          an.info.get("kontakt_eingefroren") == {"LF5": hub, h3: hub}, str(an.info.get("kontakt_eingefroren")))
    check("S3 start_angeboten_von (Klartext) nennt den neuen Lastfall",
          info["LF5"].get("start_angeboten_von") == f"Lastfall {hub}"
          and info[eg].get("start_angeboten_von") == f"Lastfall {h3}",
          str({n: i.get("start_angeboten_von") for n, i in info.items()}))
    kopie = _kopie(PRUEFKOERPER)
    m = Model.load(kopie)
    an = E.lesen(E.pfad_zu(kopie), m)
    lf, ko = _tabellen(m)
    check("S3 Wind: lastfall_nr folgt der neuen Nummer (3 → 11)",
          m.winde["W1"].lastfall == lf["W_links"] and m.winde["W1"].lastfall_nr == 11, str(m.winde["W1"].lastfall_nr))
    check("S3 info[„umhuellende“] unter den neuen Namen (Bemessung GZT → EK8)",
          set(an.info.get("umhuellende") or {}) == {ko["Bemessung GZT"], "EK7"}, str(an.info.get("umhuellende")))
    p = os.path.join(DATEN, "huellen_schluessel_6791f9f", "mit_kollision.json")
    an = E.lesen(E.pfad_zu(p), Model.load(p))
    check("S3 info[„umhuellende_schluessel“]: kein R1-Hinweis mehr für die umbenannte „ULS“ (jetzt EK3)",
          "umhuellende_schluessel" not in an.info and "der Name „ULS“ ist im Programm schon vergeben" not in an.summary(),
          str(an.info.get("umhuellende_schluessel")))
    d = _roh(PRUEFKOERPER)
    for x in d["load_cases"]:
        x["nummer"] = {"S": 2, "W_links": 3, "Kran": 2}.get(x["name"], x.get("nummer", 0))
    mn = Model.from_dict(d, umstellen=True)
    check("S3 alte Datei mit Nummernfeldern (S und Kran mit Nr. 2, W_links mit Nr. 3): sie zählen nicht, "
          "dieselbe Vergabe wie ohne",
          list(mn.load_cases) == list(m.load_cases) and [lc.nummer for lc in mn.load_cases.values()]
          == [lc.nummer for lc in m.load_cases.values()], f"{list(mn.load_cases)}")


def test_s4_protokoll():
    """S4: die ersten zehn Zeilen stehen nicht doppelt im Protokoll, die erste
    Zeile ist kurz."""
    from statik3d.model import Model, Combination
    m = Model("viele")
    m.add_node(0, 0, 0)
    for i in range(25):
        m.combinations[f"K{i}"] = Combination(f"K{i}", {"LF1": 1.0 + i}, "ULS")
    d = m.to_dict()
    d["format"] = 8
    m2 = Model.from_dict(json.loads(json.dumps(d)), umstellen=True)
    erst, weiter = m2._ladehinweise[0], m2._ladehinweise[1]
    def tabellenzeilen(t):
        return [z.strip() for z in t.splitlines() if z.startswith("    ") and " → " in z]
    zeilen = tabellenzeilen(erst)
    check("S4 erste Zeile kurz, zehn Zeilen im ersten Hinweis, keine davon im zweiten, die übrigen 15 dort",
          len(erst.splitlines()[0]) <= 60 and len(zeilen) == 10
          and not set(zeilen) & set(tabellenzeilen(weiter)) and len(tabellenzeilen(weiter)) == 15,
          repr(erst.splitlines()[0]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1800, exit=True)
    for t in (test_u1_dateien_in_tests_daten, test_u2_cbg_und_pruefkoerper, test_u3_drehlager,
              test_u4_ergebnisdateien, test_u4_nachweise_umschluesseln, test_u5_kreuzende_namen,
              test_u6_rechenarbeiter, test_u7_speichern, test_u8_beispiele,
              test_v1_verwaiste_verweise, test_v9_aenderung_nach_dem_oeffnen, test_v2_anhaengen, test_v3_ausloeser,
              test_v4_geteilte_ergebniskombinationen, test_v5_bericht_und_felder, test_v6_laufzeit,
              test_v7_geaendert, test_v8_webstart_kommandozeile, test_s3_mutanten, test_s4_protokoll):
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
    # ohne Aufraeumen beenden: kein Fenster und keine Rueckfrage bleibt stehen
    os._exit(code)
