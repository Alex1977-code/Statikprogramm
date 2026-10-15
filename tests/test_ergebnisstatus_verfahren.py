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
    check("… Reibungstangente Verbesserung, Deckel Fehlerkorrektur (mit Prüfung am Ergebnis)",
          rv.merkmal("reibverfahren").wechsel[-1].art == rv.VERBESSERUNG
          and rv.merkmal("deckel").wechsel[-1].art == rv.FEHLERKORREKTUR
          and rv.merkmal("deckel").im_ergebnis is not None)
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
    h = _hinweis(a2)
    check("Alte Datei mit Reibung ohne Verfahrensangabe: gültig, mit Hinweis",
          a2 is not None and "älterem Rechenverfahren" in h and "bisheriges Reibverfahren" in h
          and "neue Rechnung" in h, fehler or h)
    check("… der Hinweis nennt das aktuelle Verfahren", "konsistente Reibungstangente" in h, h)
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
    check("… ohne neue Rechnung gespeichert: Merkmale der Datei bleiben, Hinweis kommt wieder",
          v.get("merkmale", {}).get("reibverfahren") is False and v.get("merkmale", {}).get("deckel") is None
          and "reibverfahren" not in _inhalt(p2, m)      # das Programm vom 15.10.2026 sagt dann den Hinweis
          and a3 is not None and "bisheriges Reibverfahren" in _hinweis(a3), fehler or repr(v))
    # neu gerechnet: kein Hinweis
    from statik3d import solver
    p3 = os.path.join(d, "neu.ergebnisse")
    erg.schreiben(p3, m, solver.solve_all(m, design=False))
    a4, fehler = _laden(p3, m)
    check("… nach neuer Rechnung gespeichert: kein Hinweis", a4 is not None and not _hinweis(a4), fehler)


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
    check("… der Lauf endete am Deckel (vorläufig), keiner galt mit mehr als 40 Runden: kein Status",
          a2 is not None and not a2.info.get("verfahren_betroffen"), str(a2.info.get("verfahren_betroffen")))


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
    check("Lauf mit genau 40 Runden konvergiert (auch heute möglich): kein Status",
          a2 is not None and not a2.info.get("verfahren_betroffen"), fehler)
    # 57 Runden, nicht konvergiert: vorlaeufig, kein Status der Fehlerkorrektur
    erg.schreiben(p, m, an)
    _umschreiben(p, m, _langer_lauf(57, False))
    a2, fehler = _laden(p, m)
    check("Lauf mit 57 Runden, nicht konvergiert: kein Status der Fehlerkorrektur",
          a2 is not None and not a2.info.get("verfahren_betroffen"), fehler)
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
    check("… Hinweis in Statuszeile und Protokoll: älteres Verfahren, neue Rechnung",
          me.hinweis_mit("älterem Rechenverfahren", "bisheriges Reibverfahren", "neue Rechnung")
          and "älterem Rechenverfahren" in w.log.toPlainText(), str(me.alle[-2:]))
    erg.schreiben(erg.pfad_zu(p), m, an)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… dieselbe Datei nach heutigem Stand: kein Hinweis",
          w.analysis is not None and not me.hinweis_mit("Rechenverfahren"), str(me.alle[-2:]))
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
              test_deckel_aus_protokoll, test_fehlerkorrektur_deckel, test_kuenftiger_wechsel, test_fenster):
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
