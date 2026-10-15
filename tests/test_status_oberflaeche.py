"""
Ergebnisstatus in der Oberfläche: vorläufig und möglicherweise betroffen (16.10.2026).

Auftrag (16.10.2026): ein vorläufiger Fall in der Oberflächenprüfung - ein
kleines Modell, dessen Kontaktlauf am Deckel endet. Geprüft wird, dass die
Kopfzeile „berechnet · vorläufig“ und die Statuszeile „⚠ Ergebnis vorläufig …“
wirklich in der Oberfläche erscheinen - nach einer Rechnung über den Knopf
(Hintergrundrechnung wie beim Anwender) und nach dem Öffnen der Datei. Dazu der
Fall „möglicherweise betroffen“ (statik3d.rechenverfahren, Fehlerkorrektur des
Deckels): Kopfzeile, Statuszeile, Protokoll und Bericht nennen ihn, die
Ergebnisse bleiben sichtbar; eine neue Rechnung nimmt ihn weg.

Modell: Block mit Reibung (examples_lib.block_friction_example), der Deckel
der Kontaktläufe für die Prüfung auf 3 Runden (contact.MAX_CYCLES) - so endet
der Lauf am Deckel wie am Drehlager nach 40.

Aufruf:  python -m tests.test_status_oberflaeche
Auf dem Desktop (Schrift, echtes Fenster): hauptsitzung_werkzeug/desktop_lauf.sh
"""
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_status_ob_"), "einstellungen.json")

RESULTS = []
_F = {}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _fenster():
    if "w" in _F:
        return _F["w"], _F["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._fragen = lambda *a, **k: True
    w._abnahme_bestaetigen = lambda *a, **k: True
    w._trotzdem_rechnen = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, protokoll=True)
    _F.update(w=w, app=app)
    return w, app


def _warten(app, bedingung, hoechstens=120.0):
    t0 = time.time()
    while not bedingung() and time.time() - t0 < hoechstens:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return bedingung()


class _Deckel:
    """contact.MAX_CYCLES fuer die Pruefung herabsetzen."""

    def __init__(self, n):
        self.n = n

    def __enter__(self):
        from statik3d import contact
        self.alt = contact.MAX_CYCLES
        contact.MAX_CYCLES = self.n
        return self

    def __exit__(self, *_a):
        from statik3d import contact
        contact.MAX_CYCLES = self.alt
        return False


def _kopf(w) -> str:
    return w.kopf.marke_zustand.text()


def _status(w) -> str:
    return w.statusBar().currentMessage()


def test_vorlaeufig_nach_rechnung():
    print("\n--- vorläufig nach einer Rechnung über den Knopf (Hintergrundrechnung) ---")
    from statik3d.examples_lib import block_friction_example
    w, app = _fenster()
    w._modell_setzen(block_friction_example())
    w.refresh_all()
    app.processEvents()
    with _Deckel(3):
        w.do_solve("all")
        fertig = _warten(app, lambda: not getattr(w, "_rechnet_gerade", False) and w.analysis is not None)
    check("Rechnung fertig, Ergebnis da", fertig and w.analysis is not None and "LF1" in w.analysis.cases)
    from statik3d import solver
    r = w.analysis.cases.get("LF1") if w.analysis is not None else None
    check("(der Kontaktlauf endete am Deckel: Ergebnis vorläufig)",
          r is not None and bool(solver.kontakt_vorlaeufig(r.info)),
          solver.kontakt_vorlaeufig(r.info) if r is not None else "")
    check("Kopfzeile „berechnet · vorläufig“", "berechnet" in _kopf(w) and "· vorläufig" in _kopf(w), _kopf(w))
    check("Statuszeile „⚠ Ergebnis vorläufig …“", _status(w).startswith("⚠ Ergebnis vorläufig"), _status(w))
    check("… und im Protokoll", "⚠ Ergebnis vorläufig" in w.log.toPlainText())
    _F["vorl_analyse"] = w.analysis


def test_vorlaeufig_nach_oeffnen():
    print("\n--- vorläufig nach dem Öffnen der Datei mit Ergebnissen ---")
    from statik3d import ergebnisse as erg
    w, app = _fenster()
    an = _F.get("vorl_analyse")
    if an is None:
        check("(Ergebnis aus dem vorigen Teil fehlt)", False)
        return
    p = os.path.join(tempfile.mkdtemp(prefix="status_ob_"), "block.json")
    w.model.save(p)
    erg.schreiben(erg.pfad_zu(p), w.model, an)
    w.modell_laden(p, fragen=False)
    app.processEvents()
    check("geöffnet, Ergebnis da", w.analysis is not None and "LF1" in w.analysis.cases)
    check("Kopfzeile „berechnet · vorläufig“", "· vorläufig" in _kopf(w), _kopf(w))
    check("Statuszeile nennt „⚠ Ergebnis vorläufig“ (nicht von „Ergebnisse geladen“ überschrieben)",
          "⚠ Ergebnis vorläufig" in _status(w), _status(w))
    _F["pfad"] = p


def test_moeglicherweise_betroffen():
    print("\n--- möglicherweise betroffen (Fehlerkorrektur Deckel) nach dem Öffnen ---")
    from statik3d import ergebnisse as erg, rechenverfahren as rv
    from statik3d.report.html import Report
    w, app = _fenster()
    m, an = _F["alt"]
    p = os.path.join(tempfile.mkdtemp(prefix="status_ob_"), "block_alt.json")
    m.save(p)
    erg.schreiben(erg.pfad_zu(p), m, an)
    # so schrieb das Programm vor dem 15.10.2026: ohne Angabe; ein Lauf galt nach 57 Runden
    # als konvergiert (moeglich nur mit dem alten Deckel)
    with open(erg.pfad_zu(p), "rb") as fh:
        inhalt = erg._Leser(fh, m).load()
    inhalt.pop("verfahren", None)
    inhalt.pop("reibverfahren", None)
    info = inhalt["cases"]["LF1"].setdefault("info", {})
    info["laeufe"] = list(info.get("laeufe") or []) + [{"nr": 9, "art": "Probe", "schritte": 57,
                                                         "konvergiert": True, "grund": ""}]
    with open(erg.pfad_zu(p), "wb") as fh:
        erg._Schreiber(fh, m).dump(inhalt)
    w.meldungen.leeren()
    w.modell_laden(p, fragen=False)
    app.processEvents()
    check("geöffnet: Ergebnisse bleiben sichtbar (LF1, passt)",
          w.analysis is not None and "LF1" in w.analysis.cases and w._analyse_passt() == "passt")
    check("Kopfzeile „möglicherweise betroffen – neu rechnen“",
          "möglicherweise betroffen – neu rechnen" in _kopf(w), _kopf(w))
    check("Statuszeile „⚠ Ergebnis möglicherweise betroffen – neu rechnen …“",
          _status(w).startswith("⚠ " + rv.BETROFFEN), _status(w)[:140])
    check("… Protokoll", rv.BETROFFEN in w.log.toPlainText())
    text = re.sub(r"<[^>]+>", " ", Report(w.model, w.analysis).html()) if w.analysis is not None else ""
    check("… Bericht", rv.BETROFFEN in text)
    # neu gerechnet: der Status ist weg
    w.do_solve("all")
    _warten(app, lambda: not getattr(w, "_rechnet_gerade", False))
    _warten(app, lambda: w.analysis is not None and not (w.analysis.info or {}).get("verfahren_betroffen"), 5.0)
    check("nach neuer Rechnung: kein Status mehr in der Kopfzeile",
          w.analysis is not None and "möglicherweise betroffen" not in _kopf(w), _kopf(w))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    # das Ergebnis fuer „möglicherweise betroffen“ vor dem Fenster rechnen: auf dem Desktop
    # hing die Zerlegung (PARDISO) einer Rechnung im Oberflaechen-Faden, nachdem die
    # Hintergrundrechnung des ersten Teils gelaufen war (16.10.2026, Spur im Bericht)
    from statik3d import solver
    from statik3d.examples_lib import block_friction_example
    m = block_friction_example()
    _F["alt"] = (m, solver.solve_all(m, design=False))
    for t in (test_vorlaeufig_nach_rechnung, test_vorlaeufig_nach_oeffnen, test_moeglicherweise_betroffen):
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
