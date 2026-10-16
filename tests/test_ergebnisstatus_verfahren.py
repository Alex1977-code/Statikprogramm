"""
Ergebnisstatus: Modell geaendert gegen aelteres Rechenverfahren (16.10.2026).

Der Anwender (15.10.2026): „Bitte künftig zwei Fälle trennen. ‚Modell geändert‘
→ Ergebnisse ungültig. ‚Mit älterem Rechenverfahren gerechnet‘ (z. B. ohne
Reibungstangente oder mit altem Abbruchkriterium) → Ergebnisse gültig, mit
Hinweis.“

* Modell: Geometrie, Netz, Werkstoffe, Querschnitte, Lager, Lasten, Kontakte und
  jede Einstellung, die der Anwender nach der Rechnung selbst umgestellt hat -
  eine Aenderung dort macht die Ergebnisdatei ungueltig (Kennung).
* Rechenverfahren: was das Programm mit demselben Modell tut und sich seit der
  Rechnung geaendert hat (Vorgabe der Reibungstangente, Deckel des
  Kontaktlaufs, Abbruch der Plastizitaet). Die Tabelle steht in
  statik3d.rechenverfahren; die Ergebnisdatei schreibt Verfahrensstand und
  Merkmale mit. Solche Ergebnisse bleiben gueltig, Statuszeile und Protokoll
  nennen das Verfahren und dass eine neue Rechnung aktuelle Ergebnisse liefert.

Geprueft wird: Modellaenderung -> ungueltig; alte Datei mit Reibung ohne
Verfahrensangabe -> gueltig mit Hinweis; Datei vom 15.10.2026 mit
reibungstangente true -> gueltig ohne Hinweis auf das Reibverfahren; nach der
Rechnung vom Anwender auf das bisherige Reibverfahren umgestellt -> ungueltig
(auch bei einer Einstellung, die zugleich Verfahrensmerkmal ist); ein kuenftiger
Wechsel einer Vorgabe wird nur in der Tabelle eingetragen.

Aufruf:  python -m tests.test_ergebnisstatus_verfahren
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ergebnisstatus_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
_GERECHNET = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _ordner():
    return tempfile.mkdtemp(prefix="ergebnisstatus_")


def _klotz(tangente=True):
    """Stahlblock auf Platte, Kontaktpaar mit mu = 0,3, gerechnet (je
    Einstellung einmal gerechnet, danach kopiert)."""
    import copy
    from statik3d import examples_lib as ex, solver
    if tangente not in _GERECHNET:
        m = ex.block_friction_example()
        m.plastizitaet.reibungstangente = tangente
        _GERECHNET[tangente] = (m, solver.solve_all(m, design=False))
    m0, an0 = _GERECHNET[tangente]
    m = copy.deepcopy(m0)
    return m, an0


def _inhalt(pfad, model):
    from statik3d import ergebnisse as erg
    with open(pfad, "rb") as fh:
        return erg._Leser(fh, model).load()


def _umschreiben(pfad, model, aendern):
    from statik3d import ergebnisse as erg
    inhalt = _inhalt(pfad, model)
    aendern(inhalt)
    with open(pfad, "wb") as fh:
        erg._Schreiber(fh, model).dump(inhalt)


def _wie_15_10_abends(pfad, model):
    """So schrieb das Programm von a371cf2 bis b63e669: „reibverfahren“, aber
    noch keinen Verfahrensstand."""
    _umschreiben(pfad, model, lambda d: d.pop("verfahren", None))


def _vor_15_10(pfad, model):
    """So schrieb das Programm bis zum 15.10.2026 abends: ohne jede Angabe."""
    def weg(d):
        d.pop("verfahren", None)
        d.pop("reibverfahren", None)
    _umschreiben(pfad, model, weg)


class _FruehereVorgabe:
    """Das Programm vom Stand 4073439 bis b24910b (15.10.2026 mittags):
    reibungstangente mit der Vorgabe False - ein ausdrueckliches True stand in
    Modelldatei und Kennung (scratchpad dl_neu/lauf_RT, lauf_MU1)."""

    def __enter__(self):
        from statik3d import model as mdl
        from statik3d.plastizitaet import Plastizitaet
        self.pl, self.nf = dict(Plastizitaet.NEU_15_10), dict(mdl.NEUE_FELDER["plastizitaet"])
        Plastizitaet.NEU_15_10 = dict(self.pl, reibungstangente=False)
        mdl.NEUE_FELDER["plastizitaet"] = dict(self.nf, reibungstangente=False)
        return self

    def __exit__(self, *_a):
        from statik3d import model as mdl
        from statik3d.plastizitaet import Plastizitaet
        Plastizitaet.NEU_15_10 = self.pl
        mdl.NEUE_FELDER["plastizitaet"] = self.nf
        return False


def _laden(pfad, model):
    """(Analyse, Fehlertext)."""
    from statik3d import ergebnisse as erg
    try:
        return erg.lesen(pfad, model), ""
    except ValueError as ex:
        return None, str(ex)


def _hinweis(an) -> str:
    return str(((an.info if an is not None else {}) or {}).get("verfahren_hinweis") or "")


def _status(an) -> str:
    return str(((an.info if an is not None else {}) or {}).get("verfahren_betroffen") or "")


def test_tabelle_und_datei():
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    namen = [mk.name for mk in rv.MERKMALE]
    check("Tabelle der Verfahrensmerkmale: Reibverfahren, Deckel, Abbruch der Plastizität",
          {"reibverfahren", "deckel", "abbruch"} <= set(namen), str(namen))
    check("… jeder Wechsel trägt Stand, Datum und Commit",
          all(w.stand >= 1 and w.datum and w.commit for mk in rv.MERKMALE for w in mk.wechsel)
          and rv.VERFAHRENSSTAND == max(w.stand for mk in rv.MERKMALE for w in mk.wechsel),
          f"Stand {rv.VERFAHRENSSTAND}")
    check("… jeder Wechsel ist als Verbesserung oder Fehlerkorrektur eingestuft, jedes Merkmal nennt "
          "sein Modellmerkmal mit Prüffunktion",
          all(w.art in (rv.VERBESSERUNG, rv.FEHLERKORREKTUR) for mk in rv.MERKMALE for w in mk.wechsel)
          and all(mk.modellmerkmal and callable(mk.betrifft) for mk in rv.MERKMALE),
          str({mk.name: [w.art for w in mk.wechsel] for mk in rv.MERKMALE}))
    check("… Einstufung 16.10.2026: Abbruch Verbesserung; Reibungstangente und Deckel Fehlerkorrektur",
          rv.merkmal("abbruch").wechsel[-1].art == rv.VERBESSERUNG
          and rv.merkmal("reibverfahren").wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.merkmal("deckel").wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.merkmal("deckel").im_ergebnis is not None)
    neu = ("saitenform", "alpha_cr_aktiv", "seil_theorie3", "fachwerk_querlast", "import_lagerreibung",
           "import_stabtypen", "import_vorspannung", "import_lastkategorien")
    check("… dazu als Fehlerkorrektur: Saitenform, alpha_cr mit abgeschalteten Stäben, Seil Theorie III, "
          "Fachwerkstab mit Querlast, Importe Lagerreibung, Stabtypen, Vorspannung, Lastkategorien",
          all(rv.merkmal(n) is not None and rv.merkmal(n).wechsel[-1].art == rv.FEHLERKORREKTUR for n in neu)
          and all(rv.merkmal(n).import_korrektur for n in neu if n.startswith("import_")),
          str([n for n in neu if rv.merkmal(n) is None]))
    from statik3d import model as mdl
    check("… model.FRUEHERE_VORGABEN kommt aus der Tabelle",
          mdl.FRUEHERE_VORGABEN == rv.fruehere_vorgaben()
          and mdl.FRUEHERE_VORGABEN.get("plastizitaet", {}).get("reibungstangente") is False,
          repr(mdl.FRUEHERE_VORGABEN))
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "klotz.ergebnisse")
    erg.schreiben(p, m, an)
    v = _inhalt(p, m).get("verfahren")
    check("Ergebnisdatei schreibt Verfahrensstand und Merkmale",
          isinstance(v, dict) and v.get("stand") == rv.VERFAHRENSSTAND
          and v.get("merkmale", {}).get("reibverfahren") is True
          and v.get("merkmale", {}).get("deckel") == "alle_runden"
          and v.get("merkmale", {}).get("abbruch") == "ingenieurmaessig", repr(v))
    check("… und weiter „reibverfahren“ für das Programm vom 15.10.2026",
          _inhalt(p, m).get("reibverfahren") == "konsistente Tangente")
    a2, fehler = _laden(p, m)
    check("… geladen: gültig, ohne Hinweis", a2 is not None and not _hinweis(a2), fehler or _hinweis(a2))


def test_modell_geaendert():
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "klotz.ergebnisse")
    erg.schreiben(p, m, an)
    m.materials["S235"].E *= 1.01
    a2, fehler = _laden(p, m)
    check("Modell nach der Rechnung geändert (E-Modul des Blocks): ungültig",
          a2 is None and "seit der Rechnung geändert" in fehler and "Werkstoffe" in fehler, fehler)
    m, an = _klotz(True)
    erg.schreiben(p, m, an)
    m.contact_pairs[0].mu = 0.2
    a2, fehler = _laden(p, m)
    check("Kontakt geändert (μ 0,3 -> 0,2): ungültig", a2 is None and "Kontakt" in fehler, fehler)
    # auch eine alte Datei ohne Verfahrensangabe: Modellaenderung bleibt ungueltig
    m, an = _klotz(True)
    erg.schreiben(p, m, an)
    _vor_15_10(p, m)
    m.contact_pairs[0].mu = 0.2
    a2, fehler = _laden(p, m)
    check("… ebenso an einer alten Datei ohne Verfahrensangabe", a2 is None and "Kontakt" in fehler, fehler)


def test_alte_datei_mit_reibung():
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "alt.ergebnisse")
    erg.schreiben(p, m, an)
    _vor_15_10(p, m)
    a2, fehler = _laden(p, m)
    h = _status(a2)
    check("Alte Datei mit Reibung ohne Verfahrensangabe: Ergebnisse geladen, Status „möglicherweise betroffen“ "
          "(Reibungstangente ist Fehlerkorrektur)",
          a2 is not None and h.startswith("Ergebnis möglicherweise betroffen – neu rechnen")
          and "bisheriges Reibverfahren" in h and not _hinweis(a2), fehler or h)
    check("… der Status nennt das aktuelle Verfahren", "konsistente Reibungstangente" in h, h)
    check("… der Deckel ist in einer solchen Datei nicht sicher erkennbar: nicht genannt",
          a2 is not None and a2.info.get("rechenverfahren", {}).get("deckel") is None and "Deckel" not in h,
          repr(a2.info.get("rechenverfahren")) if a2 is not None else "")
    check("… die Ergebnisse bleiben (LF1 mit Verschiebungen)",
          a2 is not None and "LF1" in a2.cases and len(a2.cases["LF1"].u) == len(an.cases["LF1"].u))
    # ohne neue Rechnung wieder gespeichert: Merkmale bleiben, der Hinweis kommt wieder
    p2 = os.path.join(d, "alt2.ergebnisse")
    erg.schreiben(p2, m, a2)
    v = _inhalt(p2, m).get("verfahren") or {}
    a3, fehler = _laden(p2, m)
    check("… ohne neue Rechnung gespeichert: Merkmale der Datei bleiben, Status kommt wieder",
          v.get("merkmale", {}).get("reibverfahren") is False and v.get("merkmale", {}).get("deckel") is None
          and "reibverfahren" not in _inhalt(p2, m)      # das Programm vom 15.10.2026 sagt dann den Hinweis
          and a3 is not None and "bisheriges Reibverfahren" in _status(a3), fehler or repr(v))
    # neu gerechnet: kein Hinweis
    from statik3d import solver
    p3 = os.path.join(d, "neu.ergebnisse")
    erg.schreiben(p3, m, solver.solve_all(m, design=False))
    a4, fehler = _laden(p3, m)
    check("… nach neuer Rechnung gespeichert: kein Hinweis, kein Status",
          a4 is not None and not _hinweis(a4) and not _status(a4), fehler)


def test_alte_datei_ohne_reibung():
    from statik3d import ergebnisse as erg, examples_lib as ex, solver
    d = _ordner()
    m = ex.frame_example()
    an = solver.solve_all(m, design=False)
    p = os.path.join(d, "rahmen.ergebnisse")
    erg.schreiben(p, m, an)
    _vor_15_10(p, m)
    a2, fehler = _laden(p, m)
    check("Alte Datei, Modell ohne Kontakt und Reibung: gültig, kein Hinweis",
          a2 is not None and not _hinweis(a2), fehler or _hinweis(a2))


def test_datei_15_10_mit_tangente():
    """Die Dateien vom 15.10.2026 mit reibungstangente true."""
    from statik3d import ergebnisse as erg
    d = _ordner()
    # (a) Programm a371cf2..b63e669: „reibverfahren“ steht, Deckel ueber alle Runden
    m, an = _klotz(True)
    p = os.path.join(d, "abends.ergebnisse")
    erg.schreiben(p, m, an)
    _wie_15_10_abends(p, m)
    a2, fehler = _laden(p, m)
    check("Datei vom 15.10.2026 abends (reibverfahren: konsistente Tangente): gültig ohne Hinweis",
          a2 is not None and not _hinweis(a2) and a2.info.get("rechenverfahren", {}).get("deckel") == "alle_runden",
          fehler or _hinweis(a2))
    # (b) Programm 4073439..b24910b: true steht ausdruecklich in Modell und Kennung
    m, an = _klotz(True)
    p = os.path.join(d, "mittags.ergebnisse")
    with _FruehereVorgabe():
        check("(früherer Stand: true steht in der Modelldatei)",
              m.to_dict(netz=False)["plastizitaet"].get("reibungstangente") is True)
        erg.schreiben(p, m, an)
    _vor_15_10(p, m)
    a2, fehler = _laden(p, m)
    h = _hinweis(a2)
    check("Datei vom 15.10.2026 mittags mit reibungstangente true: gültig, ohne Hinweis",
          a2 is not None and a2.info.get("rechenverfahren", {}).get("reibverfahren") is True
          and not h and not a2.info.get("verfahren_betroffen"), fehler or h)
    check("… gerechnet vor 49cb8bb (alter Deckel erkannt), aber kein Lauf über 40 Runden: kein Status",
          a2 is not None and a2.info.get("rechenverfahren", {}).get("deckel") == "zustandswechsel"
          and not a2.info.get("verfahren_betroffen"), str(a2.info.get("verfahren_betroffen")) if a2 else "")
    # wieder gespeichert ohne Rechnung: die Kennung hat jetzt die heutige Form, die Merkmale bleiben
    p2 = os.path.join(d, "mittags2.ergebnisse")
    erg.schreiben(p2, m, a2)
    a3, fehler = _laden(p2, m)
    check("… ohne Rechnung wieder gespeichert: weiter gültig, Tangente, alter Deckel bleibt vermerkt",
          a3 is not None and a3.info.get("rechenverfahren", {}).get("reibverfahren") is True
          and a3.info.get("rechenverfahren", {}).get("deckel") == "zustandswechsel" and not _hinweis(a3)
          and _inhalt(p2, m).get("reibverfahren") == "konsistente Tangente", fehler or _hinweis(a3))


def test_anwender_stellt_um():
    """Nach der Rechnung stellt der Anwender eine Einstellung um, die zugleich
    Verfahrensmerkmal ist: das ist eine Modellaenderung."""
    from statik3d import ergebnisse as erg
    d = _ordner()
    for wie, vorbereiten in (("heutige Datei", lambda p, m: None),
                             ("Datei vom 15.10.2026 abends", _wie_15_10_abends)):
        m, an = _klotz(True)
        p = os.path.join(d, "umgestellt.ergebnisse")
        erg.schreiben(p, m, an)
        vorbereiten(p, m)
        m.plastizitaet.reibungstangente = False
        a2, fehler = _laden(p, m)
        check(f"{wie}, danach auf das bisherige Reibverfahren umgestellt: ungültig",
              a2 is None and "seit der Rechnung geändert" in fehler and "Rechenart" in fehler, fehler)
    # Datei vom 15.10.2026 mittags (true ausdruecklich), danach umgestellt
    m, an = _klotz(True)
    p = os.path.join(d, "mittags.ergebnisse")
    with _FruehereVorgabe():
        erg.schreiben(p, m, an)
    _vor_15_10(p, m)
    m.plastizitaet.reibungstangente = False
    a2, fehler = _laden(p, m)
    check("Datei vom 15.10.2026 mittags (true), danach umgestellt: ungültig",
          a2 is None and "seit der Rechnung geändert" in fehler, fehler)
    # alte Datei (bisheriges Verfahren), danach ausdruecklich auf das bisherige Verfahren gestellt
    m, an = _klotz(True)
    p = os.path.join(d, "alt.ergebnisse")
    erg.schreiben(p, m, an)
    _vor_15_10(p, m)
    m.plastizitaet.reibungstangente = False
    a2, fehler = _laden(p, m)
    check("Alte Datei, danach ausdrücklich auf das bisherige Reibverfahren gestellt: ungültig (Anwender)",
          a2 is None and "seit der Rechnung geändert" in fehler, fehler)
    # mit dem bisherigen Verfahren gerechnet und auf die Tangente zurueckgestellt
    m, an = _klotz(False)
    p = os.path.join(d, "bisher.ergebnisse")
    erg.schreiben(p, m, an)
    a2, fehler = _laden(p, m)
    check("Mit dem bisherigen Verfahren gerechnet (Einstellung des Anwenders): gültig, kein Hinweis",
          a2 is not None and not _hinweis(a2) and a2.info.get("rechenverfahren", {}).get("reibverfahren") is False,
          fehler or _hinweis(a2))
    m.plastizitaet.reibungstangente = True
    a2, fehler = _laden(p, m)
    check("… danach auf die Tangente gestellt: ungültig", a2 is None and "seit der Rechnung geändert" in fehler,
          fehler)
    # Abbruch der Plastizitaet: Einstellung und Verfahrensmerkmal
    m, an = _klotz(True)
    p = os.path.join(d, "abbruch.ergebnisse")
    erg.schreiben(p, m, an)
    m.plastizitaet.abbruch = "streng"
    a2, fehler = _laden(p, m)
    check("Abbruch der Plastizität nach der Rechnung auf „streng“ gestellt: ungültig",
          a2 is None and "seit der Rechnung geändert" in fehler, fehler)


def test_deckel_aus_protokoll():
    """Eine alte Datei, deren Kontaktlauf am Deckel endete: die Zeile nennt,
    welcher Deckel galt."""
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "deckel.ergebnisse")
    erg.schreiben(p, m, an)

    def alt(inhalt):
        inhalt.pop("verfahren", None)
        inhalt.pop("reibverfahren", None)
        lf = next(iter(inhalt["cases"]))
        info = inhalt["cases"][lf].setdefault("info", {})
        info["contact_log"] = list(info.get("contact_log") or []) + [
            "Kontakt: Nachpruefung der Reibung nach 40 Zustandswechseln abgebrochen"]
    _umschreiben(p, m, alt)
    a2, fehler = _laden(p, m)
    check("Alte Datei, Protokoll „nach 40 Zustandswechseln abgebrochen“: alter Deckel erkannt",
          a2 is not None and a2.info.get("rechenverfahren", {}).get("deckel") == "zustandswechsel", fehler)
    check("… der Lauf endete am Deckel (vorläufig), keiner galt mit mehr als 40 Runden: der Status nennt "
          "den Deckel nicht", a2 is not None and "Deckel" not in _status(a2), _status(a2))


def _langer_lauf(schritte=57, konvergiert=True):
    def aendern(inhalt):
        inhalt.pop("verfahren", None)
        inhalt.pop("reibverfahren", None)
        lf = next(iter(inhalt["cases"]))
        info = inhalt["cases"][lf].setdefault("info", {})
        info["laeufe"] = list(info.get("laeufe") or []) + [
            {"nr": 99, "art": "Probe", "schritte": schritte, "konvergiert": konvergiert, "grund": ""}]
    return aendern


def test_fehlerkorrektur_deckel():
    """Fehlerkorrektur: betroffen ist nur ein Kontaktlauf, der mehr als 40 Runden
    brauchte und trotzdem als konvergiert galt (Laufbuch je Lauf)."""
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    from statik3d.report.html import Report
    import re
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "lang.ergebnisse")
    erg.schreiben(p, m, an)
    _umschreiben(p, m, _langer_lauf(57, True))
    a2, fehler = _laden(p, m)
    st = str((a2.info if a2 is not None else {}).get("verfahren_betroffen") or "")
    check("Alte Datei, ein Lauf mit 57 Runden „konvergiert“: Status „möglicherweise betroffen – neu rechnen“",
          a2 is not None and st.startswith(rv.BETROFFEN) and "57 Runden" in st, fehler or st)
    check("… die Ergebnisse bleiben (LF1 geladen)", a2 is not None and "LF1" in a2.cases)
    check("… die Zusammenfassung (Protokoll) nennt ihn als WARNUNG",
          a2 is not None and any(z.startswith("WARNUNG") and rv.BETROFFEN in z for z in a2.summary().splitlines()))
    text = re.sub(r"<[^>]+>", " ", Report(m, a2).html()) if a2 is not None else ""
    check("… der Bericht nennt ihn", rv.BETROFFEN in text)
    p2 = os.path.join(d, "lang2.ergebnisse")
    erg.schreiben(p2, m, a2)
    a3, fehler = _laden(p2, m)
    check("… ohne neue Rechnung gespeichert: der Status kommt wieder",
          a3 is not None and str(a3.info.get("verfahren_betroffen") or "").startswith(rv.BETROFFEN), fehler)
    # genau 40 Runden: auch mit dem heutigen Deckel moeglich - kein Status
    erg.schreiben(p, m, an)
    _umschreiben(p, m, _langer_lauf(40, True))
    a2, fehler = _laden(p, m)
    check("Lauf mit genau 40 Runden konvergiert (auch heute möglich): kein Deckel im Status",
          a2 is not None and "Deckel" not in _status(a2), fehler or _status(a2))
    # 57 Runden, nicht konvergiert: vorlaeufig, kein Status der Fehlerkorrektur
    erg.schreiben(p, m, an)
    _umschreiben(p, m, _langer_lauf(57, False))
    a2, fehler = _laden(p, m)
    check("Lauf mit 57 Runden, nicht konvergiert: kein Deckel im Status",
          a2 is not None and "Deckel" not in _status(a2), fehler or _status(a2))
    # heutige Datei: kein Status (Angabe alle Runden)
    erg.schreiben(p, m, an)
    a2, fehler = _laden(p, m)
    check("Heutige Datei: kein Status", a2 is not None and not a2.info.get("verfahren_betroffen"), fehler)
    # Modell ohne Kontakt: das Merkmal fehlt - kein Status (Pruefung des Modellmerkmals)
    from statik3d import examples_lib as ex, solver
    mr = ex.frame_example()
    ar = solver.solve_all(mr, design=False)
    pr = os.path.join(d, "rahmen.ergebnisse")
    erg.schreiben(pr, mr, ar)
    _umschreiben(pr, mr, _langer_lauf(57, True))
    a2, fehler = _laden(pr, mr)
    check("Modell ohne Kontakt (Merkmal fehlt): kein Status, kein Hinweis",
          a2 is not None and not a2.info.get("verfahren_betroffen") and not _hinweis(a2), fehler)


def test_kuenftiger_wechsel():
    """Ein kuenftiger Wechsel einer Vorgabe wird nur in der Tabelle eingetragen
    (und, wie jede Vorgabe, an der Einstellung selbst): hier haft_faktor 1e3 -> 1e4."""
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    from statik3d import model as mdl
    from statik3d.plastizitaet import Plastizitaet
    d = _ordner()
    m, an = _klotz(True)
    p_vg = os.path.join(d, "vorgabe.ergebnisse")
    p_aus = os.path.join(d, "ausdruecklich.ergebnisse")
    erg.schreiben(p_vg, m, an)                     # haft_faktor mit der heutigen Vorgabe 1e3
    m2, _an = _klotz(True)
    m2.plastizitaet.haft_faktor = 1.0e4
    erg.schreiben(p_aus, m2, an)                   # 1e4 ausdruecklich (heute keine Vorgabe)
    alt = (list(rv.MERKMALE), rv.VERFAHRENSSTAND, dict(Plastizitaet.NEU_15_10),
           dict(mdl.NEUE_FELDER["plastizitaet"]), Plastizitaet.__dataclass_fields__["haft_faktor"].default)
    try:
        neu = rv.VERFAHRENSSTAND + 1
        rv.MERKMALE.append(rv.Merkmal(
            name="haftfeder", titel="Haftfeder",
            texte={1.0e3: "Haftfeder 1000-fach", 1.0e4: "Haftfeder 10000-fach"},
            einstellung=("plastizitaet", "haft_faktor"),
            wechsel=(rv.Wechsel(stand=neu, datum="01.01.2027", commit="(Prüfung)", alt=1.0e3, neu=1.0e4,
                                vorher_einstellung=True),)))
        rv.VERFAHRENSSTAND = neu
        Plastizitaet.NEU_15_10 = dict(alt[2], haft_faktor=1.0e4)
        mdl.NEUE_FELDER["plastizitaet"] = dict(alt[3], haft_faktor=1.0e4)
        mdl.FRUEHERE_VORGABEN = rv.fruehere_vorgaben()
        # die Modelldatei vom alten Stand ohne den Schluessel liest heute die neue Vorgabe
        m.plastizitaet.haft_faktor = 1.0e4
        a2, fehler = _laden(p_vg, m)
        h = _hinweis(a2)
        check("Künftiger Wechsel (nur Tabelle): alte Datei mit damaliger Vorgabe gültig, mit Hinweis",
              a2 is not None and "Haftfeder 1000-fach" in h and "Haftfeder 10000-fach" in h, fehler or h)
        a2, fehler = _laden(p_aus, m2)
        check("… alte Datei mit dem heutigen Wert ausdrücklich: gültig, ohne Hinweis",
              a2 is not None and not _hinweis(a2), fehler or _hinweis(a2))
        m2.plastizitaet.haft_faktor = 1.0e3
        a2, fehler = _laden(p_aus, m2)
        check("… nach der Rechnung vom Anwender umgestellt: ungültig",
              a2 is None and "seit der Rechnung geändert" in fehler, fehler)
    finally:
        rv.MERKMALE[:] = alt[0]
        rv.VERFAHRENSSTAND = alt[1]
        Plastizitaet.NEU_15_10 = alt[2]
        mdl.NEUE_FELDER["plastizitaet"] = alt[3]
        mdl.FRUEHERE_VORGABEN = rv.fruehere_vorgaben()


def _ohne_marken(inhalt):
    """So schrieb das Programm vor dem 14.10.2026 mittags: keine Angabe, keine Marke
    (gleichgewicht_global ab 9a96ea6, Th2Info.alpha_cr_stab ab d1d8ebb)."""
    inhalt.pop("verfahren", None)
    inhalt.pop("reibverfahren", None)
    for gruppe in ("cases", "combinations", "alternativen"):
        for d in (inhalt.get(gruppe) or {}).values():
            if isinstance(d.get("info"), dict):
                d["info"].pop("gleichgewicht_global", None)
    for i in (getattr(inhalt.get("theorie2"), "kombinationen", None) or {}).values():
        vars(i).pop("alpha_cr_stab", None)


def test_keine_reibung():
    from statik3d import ergebnisse as erg, examples_lib as ex, solver
    d = _ordner()
    m = ex.frame_example()
    an = solver.solve_all(m, design=False)
    p = os.path.join(d, "rahmen.ergebnisse")
    erg.schreiben(p, m, an)
    i = _inhalt(p, m)
    check("Modell ohne Reibung: die Ergebnisdatei trägt „keine Reibung im Modell“",
          i.get("reibverfahren") == "keine Reibung im Modell"
          and (i.get("verfahren") or {}).get("merkmale", {}).get("reibverfahren") == "keine_reibung",
          repr((i.get("reibverfahren"), (i.get("verfahren") or {}).get("merkmale", {}).get("reibverfahren"))))
    a2, fehler = _laden(p, m)
    check("… geladen ohne Hinweis und Status", a2 is not None and not _hinweis(a2) and not _status(a2), fehler)


def test_saitenform_und_querlast():
    from statik3d import ergebnisse as erg, examples_lib as ex, solver
    d = _ordner()
    m = ex.truss_bridge_example()
    m.case().theorie = "II"
    an = solver.solve_all(m, design=False)
    p = os.path.join(d, "fachwerk.ergebnisse")
    erg.schreiben(p, m, an)
    _umschreiben(p, m, lambda i: (i.pop("verfahren", None), i.pop("reibverfahren", None)))
    a2, fehler = _laden(p, m)
    check("Fachwerk mit Theorie II, Datei ohne Angabe, aber mit Marke (Th2Info.alpha_cr_stab): kein Status",
          a2 is not None and not _status(a2), fehler or _status(a2))
    erg.schreiben(p, m, an)
    _umschreiben(p, m, _ohne_marken)
    a2, fehler = _laden(p, m)
    st = _status(a2)
    check("… ohne Angabe und ohne Marke: Status, Saitenform „Alter nicht sicher erkennbar“ (lieber betroffen)",
          a2 is not None and "Saitenform" in st and "nicht sicher erkennbar" in st
          and "saitenform" in (a2.info.get("verfahren_unsicher") or []), fehler or st)
    check("… und das Einzelknicken der Fachwerk-Druckstäbe in alpha_cr (d1d8ebb)",
          a2 is not None and "Einzelknicken" in st and "einzelknicken" in (a2.info.get("verfahren_unsicher") or []),
          st)
    # nur Zugstaebe: kein Fachwerk-Druckstab, kein Einzelknicken
    mz = ex.truss_bridge_example()
    for e_ in mz.elements:
        e_.nur = "zug"
    from statik3d import rechenverfahren as rv
    check("Prüffunktion Fachwerk-Druckstab: nur Zugstäbe nein, Fachwerk ja",
          not rv._fachwerk_druckstaebe(mz) and rv._fachwerk_druckstaebe(m))
    # Theorie I: kein alpha_cr - die Saitenform beruehrt das Ergebnis nicht
    m1 = ex.truss_bridge_example()
    an1 = solver.solve_all(m1, design=False)
    p1 = os.path.join(d, "fachwerk1.ergebnisse")
    erg.schreiben(p1, m1, an1)
    _umschreiben(p1, m1, _ohne_marken)
    a2, fehler = _laden(p1, m1)
    check("Fachwerk nach Theorie I ohne Querlast, Datei ohne Marke: kein Status",
          a2 is not None and not _status(a2), fehler or _status(a2))
    # mit Eigengewicht: Querlast auf Fachwerkstaeben
    m2 = ex.truss_bridge_example()
    m2.case().gravity = [0.0, 0.0, -9.81]
    an2 = solver.solve_all(m2, design=False)
    p2 = os.path.join(d, "fachwerk2.ergebnisse")
    erg.schreiben(p2, m2, an2)
    _umschreiben(p2, m2, _ohne_marken)
    a2, fehler = _laden(p2, m2)
    check("Fachwerk mit Eigengewicht (Querlast), Datei ohne Marke: Status „Fachwerkstab mit Querlast“",
          a2 is not None and "qL²/8" in _status(a2), fehler or _status(a2))
    erg.schreiben(p2, m2, an2)
    a2, fehler = _laden(p2, m2)
    check("… heutige Datei: kein Status", a2 is not None and not _status(a2), fehler or _status(a2))
    # Eigengewicht nur in LF2, gerechnet ist nur LF1: die Querlast steckt in keinem Ergebnis
    from statik3d.model import LoadCase
    m3 = ex.truss_bridge_example()
    m3.load_cases["LF2"] = LoadCase("LF2", category="G")
    m3.load_cases["LF2"].gravity = [0.0, 0.0, -9.81]
    an3 = solver.solve_all(m3, design=False)
    an3.cases.pop("LF2", None)
    p3 = os.path.join(d, "fachwerk3.ergebnisse")
    erg.schreiben(p3, m3, an3)
    _umschreiben(p3, m3, _ohne_marken)
    a2, fehler = _laden(p3, m3)
    check("Querlast nur im nicht gerechneten LF2, Datei ohne Marke: kein Status (Rechenart nicht im Ergebnis)",
          a2 is not None and "Querlast" not in _status(a2), fehler or _status(a2))


def test_pruefungen_der_merkmale():
    from statik3d import examples_lib as ex, rechenverfahren as rv
    from statik3d.model import BeamLoad
    m = ex.truss_bridge_example()
    check("Prüffunktion Fachwerkstab: Fachwerk ja, Rahmen nein",
          rv._hat_fachwerk_oder_seil(m) and not rv._hat_fachwerk_oder_seil(ex.frame_example()))
    check("Prüffunktion abgeschaltete Stäbe: ohne nein", not rv._abgeschaltete_staebe(m))
    m.add_member("D1", [1], beta_y=1.0, beta_z=1.0)
    m.members["D1"].aus = True
    check("… Stab aus: ja", rv._abgeschaltete_staebe(m))
    s = ex.truss_bridge_example()
    s.elements[0].typ = "seil"
    check("Prüffunktion Seil mit Streckenlast: ohne Last nein", not rv._seil_mit_streckenlast(s))
    s.case().beam_loads.append(BeamLoad(elem=0, q=[0.0, 0.0, -1000.0]))
    check("… mit Last ja", rv._seil_mit_streckenlast(s) and rv._fachwerk_mit_querlast(s))
    v = ex.truss_bridge_example()
    v.meta["quelle"] = "C:/x/drehlager.rf6"
    v.importhinweise = [{"art": "vorspannung", "text": "…", "erledigt": False}]
    check("Prüffunktion Vorspannung aus RFEM: offener Hinweis ja, erledigt nein",
          rv._import_vorspannung(v) and not (v.importhinweise[0].update(erledigt=True)
                                              or rv._import_vorspannung(v)))


def test_rechenart_im_ergebnis():
    """(a) Markiert nur, wenn das Merkmal im Modell vorkommt UND die betroffene
    Rechenart im Ergebnis gerechnet wurde - an Ersatzanalysen gepruefte Funktionen."""
    from types import SimpleNamespace as NS
    from statik3d import examples_lib as ex, rechenverfahren as rv
    from statik3d.model import BeamLoad, Combination, LoadCase, Situation

    def an_(cases=(), combos=(), th2=(), th3=()):
        a = NS(cases={n: NS(info={}, kind="case") for n in cases},
               combinations={n: NS(info={}, kind="case") for n in combos}, alternativen={},
               theorie2=NS(kombinationen={n: NS(alpha_cr=5.0) for n in th2}) if th2 else None,
               theorie3=NS(kombinationen={n: NS() for n in th3}) if th3 else None)
        a.all_results = lambda: {**a.cases, **a.combinations}
        return a
    m = ex.truss_bridge_example()
    m.situationen["S1"] = Situation("S1", deaktiviert=[1])
    m.load_cases["LF2"] = LoadCase("LF2", category="G", situation="S1")
    m.combinations["K2"] = Combination("K2", {"LF2": 1.0}, situation="S1")
    check("alpha_cr mit abgeschalteten Stäben: alpha_cr nur in der Grundstellung (LF1) - nicht betroffen",
          rv._alpha_cr_aktiv_im_ergebnis(m, an_(cases=["LF1"], th2=["LF1"])) == "")
    check("… alpha_cr in der Situation S1 mit abgeschaltetem Element (K2) - betroffen",
          "K2" in (rv._alpha_cr_aktiv_im_ergebnis(m, an_(combos=["K2"], th2=["K2"])) or ""))
    s = ex.truss_bridge_example()
    s.elements[0].typ = "seil"
    s.load_cases["LF2"] = LoadCase("LF2", category="Q")
    s.load_cases["LF2"].beam_loads.append(BeamLoad(elem=0, q=[0.0, 0.0, -1000.0]))
    check("Seil-Streckenlast nur in LF2, Theorie III nur für LF1 - nicht betroffen",
          rv._seil_theorie3_im_ergebnis(s, an_(cases=["LF1"], th3=["LF1"])) == "")
    check("… Theorie III für LF2 - betroffen", "LF2" in (rv._seil_theorie3_im_ergebnis(s, an_(th3=["LF2"])) or ""))
    check("Saitenform: kein alpha_cr, keine Theorie II im Ergebnis - nicht betroffen",
          rv._alpha_cr_im_ergebnis(an_(cases=["LF1"], th3=["LF1"])) == "")
    check("Fachwerk-Querlast: LF2 mit Querlast gerechnet - betroffen, nur LF1 - nicht",
          "LF2" in (rv._querlast_im_ergebnis(s, an_(cases=["LF2"])) or "")
          and rv._querlast_im_ergebnis(s, an_(cases=["LF1"])) == "")


def test_importkorrekturen():
    from statik3d import ergebnisse as erg, examples_lib as ex, solver
    from statik3d.model import DofBehaviour, Model
    d = _ordner()
    # Lagerreibung: RFEM-Quelle ohne Merkmal, Lager mit Reibbeiwert
    m = ex.frame_example()
    m.meta["quelle"] = "C:/x/rahmen.rf6"
    m.meta["rfem_zugstaebe"] = m.meta["rfem_seile"] = True
    m.supports[0].behaviour = {0: DofBehaviour(typ="rigid", mu=0.2, mu_ref=2)}
    an = solver.solve_all(m, design=False)
    p = os.path.join(d, "rahmen.json")
    m.save(p)
    erg.schreiben(erg.pfad_zu(p), m, an)
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("Import Lagerreibung mit μ = 0,2 (nicht der RFEM-Vorgabewert): nie markiert",
          a2 is not None and "Lagerreibung" not in _status(a2), fehler or _status(a2))
    m.supports[0].behaviour = {0: DofBehaviour(typ="rigid", mu=0.1, mu_ref=2)}
    an = solver.solve_all(m, design=False)
    m.save(p)
    erg.schreiben(erg.pfad_zu(p), m, an)
    m2 = Model.load(p)
    a2, fehler = _laden(erg.pfad_zu(p), m2)
    st = _status(a2)
    check("Import Lagerreibung μ = 0,1 (RFEM-Vorgabe) vor dem 15.10.2026: Status, auch bei heutiger Datei, "
          "mit beiden Wegen", a2 is not None and "Lagerreibung aus RFEM" in st and "nachlesen" in st
          and "selbst gesetzt – behalten" in st, fehler or st)
    from statik3d import rechenverfahren as rv
    rv.lagerreibung_behalten(m2)
    check("„selbst gesetzt – behalten“: Quittung im Modell, Importhinweis erledigt",
          str(m2.meta.get("rfem_lagerreibung", "")).startswith("selbst gesetzt")
          and not any(h.get("art") == "lagerreibung" and not h.get("erledigt") for h in m2.importhinweise),
          repr(m2.meta.get("rfem_lagerreibung")))
    m2.save(p)
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("… nach Speichern und Öffnen: keine Markierung mehr, Ergebnisse weiter gültig (Quittung ändert die "
          "Rechnung nicht)", a2 is not None and "Lagerreibung" not in _status(a2), fehler or _status(a2))
    m.meta["rfem_lagerreibung"] = True
    m.save(p)
    erg.schreiben(erg.pfad_zu(p), m, an)
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("… mit Merkmal rfem_lagerreibung: kein Status zur Lagerreibung",
          a2 is not None and "Lagerreibung" not in _status(a2), fehler or _status(a2))
    # Stabtypen und Lastkategorien: RFEM-Quelle ohne die Merkmale vom 14.10.2026
    f = ex.truss_bridge_example()
    f.meta["quelle"] = "C:/x/fachwerk.rf6"
    f.meta["rfem_lagerreibung"] = True
    f.add_member("Gurt", [0], beta_y=1.0, beta_z=1.0)
    from statik3d.model import Combination
    f.combinations["K1"] = Combination("K1", {"LF1": 1.35})
    f.case().category = "Q"                       # so legte der alte Import jeden Lastfall an
    an = solver.solve_all(f, design=False)
    p = os.path.join(d, "fachwerk.json")
    f.save(p)
    erg.schreiben(erg.pfad_zu(p), f, an)
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    st = _status(a2)
    check("Import Stabtypen vor dem 14.10.2026: Status „Stabtypen aus RFEM“", "Stabtypen aus RFEM" in st,
          fehler or st)
    check("Import Lastkategorien vor dem 14.10.2026, alle Lastfälle Q, mit Kombinationen: Status",
          "Lastkategorien aus RFEM" in st, fehler or st)
    f.case().category = "G"
    f.save(p)
    erg.schreiben(erg.pfad_zu(p), f, solver.solve_all(f, design=False))
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("… alle Lastfälle G (nicht Q): kein Status zu den Lastkategorien",
          a2 is not None and "Lastkategorien" not in _status(a2), fehler or _status(a2))
    f.case().category = "Q"
    # gemischte Kategorien: nicht betroffen; nur ein Lastfall gerechnet: nicht beruehrt
    from statik3d.model import LoadCase
    f.load_cases["LF2"] = LoadCase("LF2", category="G")
    f.save(p)
    erg.schreiben(erg.pfad_zu(p), f, solver.solve_all(f, design=False))
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("… Lastfälle in verschiedenen Kategorien (vom Anwender geordnet): kein Status zu den Lastkategorien",
          a2 is not None and "Lastkategorien" not in _status(a2), fehler or _status(a2))
    f.load_cases.pop("LF2")
    an1 = solver.solve_all(f, design=False)
    an1.combinations.clear()
    f.save(p)
    erg.schreiben(erg.pfad_zu(p), f, an1)
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("… nur Lastfälle gerechnet, keine Kombination: kein Status zu den Lastkategorien",
          a2 is not None and "Lastkategorien" not in _status(a2), fehler or _status(a2))
    f.meta["rfem_zugstaebe"] = f.meta["rfem_seile"] = "beim Import gesetzt (14.10.2026)"
    f.save(p)
    erg.schreiben(erg.pfad_zu(p), f, an)
    a2, fehler = _laden(erg.pfad_zu(p), Model.load(p))
    check("… mit den Merkmalen vom 14.10.2026: kein Status", a2 is not None and not _status(a2),
          fehler or _status(a2))


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
    w._fragen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def test_fenster():
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "klotz.json")
    m.save(p)
    erg.schreiben(erg.pfad_zu(p), m, an)
    _vor_15_10(erg.pfad_zu(p), m)
    w, app = _fenster()
    me = w.meldungen
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("Fenster: alte Datei geladen, Ergebnisse gültig (passt)",
          w.analysis is not None and "LF1" in w.analysis.cases and w._analyse_passt() == "passt")
    check("… Status in Statuszeile und Protokoll: möglicherweise betroffen, bisheriges Reibverfahren",
          me.hinweis_mit("möglicherweise betroffen – neu rechnen", "bisheriges Reibverfahren")
          and "möglicherweise betroffen" in w.log.toPlainText(), str(me.alle[-2:]))
    erg.schreiben(erg.pfad_zu(p), m, an)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… dieselbe Datei nach heutigem Stand: kein Hinweis, kein Status",
          w.analysis is not None and not me.hinweis_mit("Rechenverfahren")
          and not me.hinweis_mit("möglicherweise betroffen"), str(me.alle[-2:]))
    m.plastizitaet.reibungstangente = False
    m.save(p)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… Modell danach auf das bisherige Reibverfahren gestellt: nicht geladen, „seit der Rechnung geändert“",
          w.analysis is None and me.hinweis_mit("seit der Rechnung geändert"), str(me.alle[-2:]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_tabelle_und_datei, test_modell_geaendert, test_alte_datei_mit_reibung,
              test_alte_datei_ohne_reibung, test_datei_15_10_mit_tangente, test_anwender_stellt_um,
              test_deckel_aus_protokoll, test_fehlerkorrektur_deckel, test_kuenftiger_wechsel,
              test_keine_reibung, test_saitenform_und_querlast, test_pruefungen_der_merkmale,
              test_rechenart_im_ergebnis, test_importkorrekturen, test_fenster):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    sys.stdout.flush()
    return 0 if not failed else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
