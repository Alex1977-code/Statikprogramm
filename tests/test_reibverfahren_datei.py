"""
Reibverfahren in der Ergebnisdatei (15.10.2026).

Seit dem 15.10.2026 rechnet die Reibung mit der konsistenten Tangente
(Plastizitaet.reibungstangente, Vorgabe an); das bisherige Verfahren bleibt nur
zum Vergleich. Die Einstellung steht mit ihrer Vorgabe nicht in der Modelldatei
(model.NEUE_FELDER) und zaehlt darum nicht in der Kennung der Ergebnisdatei:
eine Ergebnisdatei von davor passt weiter zu ihrem Modell - gerechnet ist sie
aber mit dem bisherigen Verfahren.

* Die Ergebnisdatei schreibt das Reibverfahren mit („konsistente Tangente“ oder
  „bisheriges Verfahren“).
* Eine aeltere Ergebnisdatei ohne die Angabe, deren Modell Reibung hat (Kontakt
  mit mu > 0, Lager mit Reibung), wird geladen - die Ergebnisse bleiben
  sichtbar - mit dem Hinweis „gerechnet mit dem bisherigen Reibverfahren – für
  aktuelle Ergebnisse neu rechnen“. Ohne Reibung kein Hinweis.
* Eine Datei, gerechnet, als die Vorgabe noch „aus“ war, mit ausdruecklich
  ``reibungstangente: true`` (am 15.10.2026 die Laeufe am Drehlager,
  scratchpad dl_neu/lauf_RT), traegt die Einstellung in ihrer Kennung; seit
  true die Vorgabe ist, fehlt sie in der Kennung des Modells. Sie galt darum
  als „seit der Rechnung geändert: Rechenart und Einstellungen“. true und
  Vorgabe gelten jetzt als gleich (model.FRUEHERE_VORGABEN).

Aufruf:  python -m tests.test_reibverfahren_datei
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_reibverfahren_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

HINWEIS = "gerechnet mit dem bisherigen Reibverfahren – für aktuelle Ergebnisse neu rechnen"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _ordner():
    return tempfile.mkdtemp(prefix="reibverfahren_")


def _klotz(tangente=True):
    """Stahlblock auf Platte, Kontaktpaar mit mu = 0,3, gerechnet."""
    from statik3d import examples_lib as ex, solver
    m = ex.block_friction_example()
    m.plastizitaet.reibungstangente = tangente
    return m, solver.solve_all(m, design=False)


def _rahmen():
    from statik3d import examples_lib as ex, solver
    m = ex.frame_example()
    return m, solver.solve_all(m, design=False)


def _inhalt(pfad, model):
    from statik3d import ergebnisse as erg
    with open(pfad, "rb") as fh:
        return erg._Leser(fh, model).load()


def _ohne_angabe(pfad, model):
    """So schrieb das Programm bis zum 15.10.2026: ohne „reibverfahren“."""
    from statik3d import ergebnisse as erg
    inhalt = _inhalt(pfad, model)
    inhalt.pop("reibverfahren", None)
    with open(pfad, "wb") as fh:
        erg._Schreiber(fh, model).dump(inhalt)


class _FruehereVorgabe:
    """Das Programm vom Stand 4073439 bis b24910b: reibungstangente mit der
    Vorgabe False - ein ausdrueckliches True stand in Modelldatei und Kennung."""

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


def test_angabe_geschrieben():
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "klotz.ergebnisse")
    erg.schreiben(p, m, an)
    check("Ergebnisdatei schreibt das Reibverfahren: „konsistente Tangente“",
          _inhalt(p, m).get("reibverfahren") == "konsistente Tangente", repr(_inhalt(p, m).get("reibverfahren")))
    a2, fehler = _laden(p, m)
    check("… geladen ohne Hinweis, Reibverfahren in der Analyse",
          a2 is not None and not a2.info.get("reibverfahren_vorbehalt")
          and a2.info.get("reibverfahren") == "konsistente Tangente",
          fehler or repr(a2.info.get("reibverfahren")))
    m, an = _klotz(False)
    p = os.path.join(d, "klotz_bisher.ergebnisse")
    erg.schreiben(p, m, an)
    check("… mit dem bisherigen Verfahren gerechnet: „bisheriges Verfahren“",
          _inhalt(p, m).get("reibverfahren") == "bisheriges Verfahren", repr(_inhalt(p, m).get("reibverfahren")))
    a2, fehler = _laden(p, m)
    check("… geladen ohne Hinweis (die Datei sagt es selbst)",
          a2 is not None and not a2.info.get("reibverfahren_vorbehalt")
          and a2.info.get("reibverfahren") == "bisheriges Verfahren", fehler)


def test_alte_datei_mit_reibung():
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "alt.ergebnisse")
    erg.schreiben(p, m, an)
    _ohne_angabe(p, m)
    a2, fehler = _laden(p, m)
    check("Ältere Datei ohne Angabe, Kontakt mit μ > 0: geladen, mit Hinweis",
          a2 is not None and a2.info.get("reibverfahren_vorbehalt") == HINWEIS,
          fehler or repr(a2.info.get("reibverfahren_vorbehalt")))
    check("… die Ergebnisse bleiben (LF1 mit Verschiebungen)",
          a2 is not None and "LF1" in a2.cases and getattr(a2.cases["LF1"], "u", None) is not None
          and len(a2.cases["LF1"].u) == len(an.cases["LF1"].u))
    # wieder gespeichert ohne neue Rechnung: die Angabe bleibt weg, der Hinweis kommt wieder
    p2 = os.path.join(d, "alt2.ergebnisse")
    erg.schreiben(p2, m, a2)
    a3, fehler = _laden(p2, m)
    check("… ohne neue Rechnung wieder gespeichert: keine Angabe, der Hinweis kommt wieder",
          "reibverfahren" not in _inhalt(p2, m) and a3 is not None
          and a3.info.get("reibverfahren_vorbehalt") == HINWEIS, fehler)
    # neu gerechnet: die Angabe steht, kein Hinweis
    from statik3d import solver
    p3 = os.path.join(d, "neu.ergebnisse")
    erg.schreiben(p3, m, solver.solve_all(m, design=False))
    a4, fehler = _laden(p3, m)
    check("… nach neuer Rechnung gespeichert: Angabe steht, kein Hinweis",
          _inhalt(p3, m).get("reibverfahren") == "konsistente Tangente" and a4 is not None
          and not a4.info.get("reibverfahren_vorbehalt"), fehler)


def test_alte_datei_ohne_reibung():
    from statik3d import ergebnisse as erg
    from statik3d.model import DofBehaviour
    d = _ordner()
    m, an = _rahmen()
    check("Rahmen ohne Kontakt und Lagerreibung: keine Reibung", not erg.modell_hat_reibung(m))
    p = os.path.join(d, "rahmen.ergebnisse")
    erg.schreiben(p, m, an)
    _ohne_angabe(p, m)
    a2, fehler = _laden(p, m)
    check("Ältere Datei ohne Angabe, Modell ohne Reibung: kein Hinweis",
          a2 is not None and not a2.info.get("reibverfahren_vorbehalt"), fehler)
    # Lager mit Reibung
    m.supports[0].behaviour = {0: DofBehaviour(typ="rigid", mu=0.2, mu_ref=2)}
    check("Lager mit Reibbeiwert: Reibung", erg.modell_hat_reibung(m))
    p = os.path.join(d, "rahmen_lager.ergebnisse")
    erg.schreiben(p, m, an)
    _ohne_angabe(p, m)
    a2, fehler = _laden(p, m)
    check("Ältere Datei ohne Angabe, Lager mit Reibung: Hinweis",
          a2 is not None and a2.info.get("reibverfahren_vorbehalt") == HINWEIS, fehler)
    # Kontaktpaar ohne Reibung, Kontaktlager mit Reibung
    from statik3d import examples_lib as ex
    k = ex.block_friction_example()
    k.contact_pairs[0].mu = 0.0
    check("Kontaktpaar mit μ = 0: keine Reibung", not erg.modell_hat_reibung(k))
    k.add_contact_support(0, mu=0.25)
    check("Kontaktlager mit μ = 0,25: Reibung", erg.modell_hat_reibung(k))


def test_true_aus_frueherem_stand():
    """Eine Datei mit ``reibungstangente: true``, gerechnet als die Vorgabe noch
    False war, gilt nicht als geaendert."""
    from statik3d import ergebnisse as erg
    d = _ordner()
    m, an = _klotz(True)
    p = os.path.join(d, "rt.ergebnisse")
    with _FruehereVorgabe():
        check("(früherer Stand: true steht in der Modelldatei)",
              m.to_dict(netz=False)["plastizitaet"].get("reibungstangente") is True)
        erg.schreiben(p, m, an)
    _ohne_angabe(p, m)
    a2, fehler = _laden(p, m)
    check("true aus dem früheren Stand gilt als gleich der Vorgabe: Datei passt",
          a2 is not None, fehler)
    check("… und ist mit der Tangente gerechnet: kein Hinweis auf das bisherige Verfahren",
          a2 is not None and not a2.info.get("reibverfahren_vorbehalt")
          and a2.info.get("reibverfahren") == "konsistente Tangente",
          repr(a2.info.get("reibverfahren_vorbehalt")) if a2 is not None else "")
    m.plastizitaet.reibungstangente = False
    a3, fehler = _laden(p, m)
    check("… Gegenprobe: Modell danach auf das bisherige Verfahren gestellt -> geändert",
          a3 is None and "seit der Rechnung geändert" in fehler and "Rechenart" in fehler, fehler)
    # derselbe fruehere Stand ohne den Schluessel (dort Vorgabe False): bisheriges Verfahren
    m2, an2 = _klotz(False)
    p2 = os.path.join(d, "pd.ergebnisse")
    with _FruehereVorgabe():
        erg.schreiben(p2, m2, an2)
        d2 = m2.to_dict(netz=False)["plastizitaet"]
    _ohne_angabe(p2, m2)
    m2.plastizitaet.reibungstangente = True         # so liest das Programm heute die Modelldatei ohne Schluessel
    a4, fehler = _laden(p2, m2)
    check("Früherer Stand, Schlüssel fehlt (bisheriges Verfahren): passt, mit Hinweis",
          "reibungstangente" not in d2 and a4 is not None and a4.info.get("reibverfahren_vorbehalt") == HINWEIS,
          fehler)


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
    _ohne_angabe(erg.pfad_zu(p), m)
    w, app = _fenster()
    me = w.meldungen
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("Fenster: ältere Ergebnisdatei mit Reibung geladen, Hinweis „bisheriges Reibverfahren“",
          w.analysis is not None and me.hinweis_mit(HINWEIS),
          f"analysis {'da' if w.analysis is not None else 'None'}, {me.alle[-2:]}")
    check("… die Ergebnisse sind sichtbar (LF1 in der Analyse, passt)",
          w.analysis is not None and "LF1" in w.analysis.cases and w._analyse_passt() == "passt",
          w._analyse_passt() if w.analysis is not None else "")
    # neue Datei: kein Hinweis
    erg.schreiben(erg.pfad_zu(p), m, an)
    me.leeren()
    w.modell_laden(p, fragen=False); app.processEvents()
    check("… dieselbe Datei mit Angabe: kein Hinweis",
          w.analysis is not None and not me.hinweis_mit("Reibverfahren"), str(me.alle[-2:]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_angabe_geschrieben, test_alte_datei_mit_reibung, test_alte_datei_ohne_reibung,
              test_true_aus_frueherem_stand, test_fenster):
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
