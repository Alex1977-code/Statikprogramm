"""
Hintergrundrechnung (statik3d.gui.worker.SolveWorker): Ergebnis, Fehler und
Abbruch - ohne Fenster, nur mit einer QCoreApplication fuer die Signale.

Der Abbruch ist kooperativ: der Rueckruf ``progress`` wirft
:class:`Abgebrochen`, sobald ``abbrechen()`` gerufen wurde. Der Rechenkern
haelt damit beim naechsten Fortschrittsaufruf an und muss vom Abbrechen
nichts wissen.

Aufruf:  python -m tests.test_worker
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore                                          # noqa: E402

from statik3d.gui.worker import Abgebrochen, SolveWorker            # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:66s} {detail}")
    return bool(ok)


def _app():
    return QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(sys.argv)


def _laufen_lassen(func, abbrechen_nach: float = None, hoechstens: float = 20.0) -> dict:
    """Den Worker mit ``func`` laufen lassen und alle Signale einsammeln.

    ``abbrechen_nach`` (s): dann wird nach dieser Zeit abbrechen() gerufen.
    Rueckgabe: Woerterbuch mit den Listen der Signale und der Laufzeit.
    """
    app = _app()
    erg = {"ok": [], "failed": [], "abgebrochen": [], "texte": [], "anteile": []}
    w = SolveWorker(func)
    w.progress.connect(lambda t: erg["texte"].append(t))
    w.fortschritt.connect(lambda t, a: erg["anteile"].append((t, a)))
    w.finished_ok.connect(lambda r: erg["ok"].append(r))
    w.failed.connect(lambda m, tb: erg["failed"].append((m, tb)))
    w.abgebrochen.connect(lambda d: erg["abgebrochen"].append(d))
    t0 = time.time()
    w.start()
    abgebrochen_bei = None
    while (w.isRunning() or not (erg["ok"] or erg["failed"] or erg["abgebrochen"])) \
            and time.time() - t0 < hoechstens:
        app.processEvents()
        if abbrechen_nach is not None and abgebrochen_bei is None \
                and time.time() - t0 >= abbrechen_nach:
            w.abbrechen()
            abgebrochen_bei = time.time()
        time.sleep(0.005)
    w.wait(2000)
    app.processEvents()
    erg["dauer"] = time.time() - t0
    erg["abbruch_bis_ende"] = (time.time() - abgebrochen_bei) if abgebrochen_bei else None
    erg["worker"] = w
    return erg


def _lange_rechnung(schritte: int = 200, pause: float = 0.02):
    def func(progress):
        for i in range(schritte):
            progress(f"Schritt {i + 1}", (i + 1) / schritte)
            time.sleep(pause)
        return "fertig"
    return func


# ==========================================================================
def test_ergebnis_kommt_an():
    erg = _laufen_lassen(_lange_rechnung(10, 0.001))
    check("ohne Abbruch: finished_ok mit dem Ergebnis", erg["ok"] == ["fertig"], str(erg["ok"]))
    check("ohne Abbruch: kein failed, kein abgebrochen",
          not erg["failed"] and not erg["abgebrochen"])
    check("alle Schritte gemeldet, Text und Anteil",
          len(erg["texte"]) == 10 and len(erg["anteile"]) == 10
          and abs(erg["anteile"][-1][1] - 1.0) < 1e-12, f"{len(erg['texte'])} Texte")
    check("ohne Anteil kommt nur der Text",
          not _laufen_lassen(lambda p: p("nur Text"))["anteile"])


def test_abbruch_haelt_an():
    erg = _laufen_lassen(_lange_rechnung(200, 0.02), abbrechen_nach=0.3)
    w = erg["worker"]
    check("Abbruch: das Signal abgebrochen kommt - genau einmal",
          len(erg["abgebrochen"]) == 1, str(erg["abgebrochen"]))
    check("Abbruch: kein finished_ok, kein failed",
          not erg["ok"] and not erg["failed"], f"{erg['ok']} / {[m for m, _ in erg['failed']]}")
    check("Abbruch: die Rechnung lief nicht zu Ende (200 Schritte à 0,02 s = 4 s)",
          0 < len(erg["texte"]) < 200 and erg["dauer"] < 2.0,
          f"{len(erg['texte'])} Schritte, {erg['dauer']:.2f} s")
    check("Abbruch: das Ende folgt beim naechsten Schritt (< 0,2 s nach abbrechen())",
          erg["abbruch_bis_ende"] is not None and erg["abbruch_bis_ende"] < 0.2,
          f"{erg['abbruch_bis_ende']:.3f} s" if erg["abbruch_bis_ende"] else "-")
    check("Abbruch: die gemeldete Dauer ist die Laufzeit",
          erg["abgebrochen"] and 0.2 <= erg["abgebrochen"][0] <= erg["dauer"] + 0.01,
          f"{erg['abgebrochen'][0]:.2f} s" if erg["abgebrochen"] else "-")
    check("das Flag ist lesbar (fuer die Oberflaeche)", w.abbruch_angefordert)
    check("nach dem letzten Schritt kam kein weiterer Fortschritt",
          erg["texte"] == [f"Schritt {i + 1}" for i in range(len(erg["texte"]))])


def test_abbruch_in_fremder_verpackung():
    """Der Rechenkern faengt die Ausnahme und verpackt sie (RuntimeError aus
    einem Pool, ValueError aus einer Nachbearbeitung): gewollt war trotzdem
    der Abbruch - kein Fehler."""
    def func(progress):
        try:
            for i in range(200):
                progress(f"Schritt {i + 1}", (i + 1) / 200)
                time.sleep(0.01)
        except Exception as ex:                # noqa: BLE001 - genau das Verpacken
            raise RuntimeError(f"Nachweis fehlgeschlagen: {ex}") from ex
        return "fertig"
    erg = _laufen_lassen(func, abbrechen_nach=0.2)
    check("verpackter Abbruch: abgebrochen statt failed",
          len(erg["abgebrochen"]) == 1 and not erg["failed"] and not erg["ok"],
          f"{len(erg['abgebrochen'])} / {[m for m, _ in erg['failed']]}")


def test_fehler_bleibt_fehler():
    def func(progress):
        progress("gleich kracht es", 0.1)
        raise ValueError("entartetes Tet4")
    erg = _laufen_lassen(func)
    check("Fehler: failed mit Meldung und Traceback",
          len(erg["failed"]) == 1 and "entartetes Tet4" in erg["failed"][0][0]
          and "ValueError" in erg["failed"][0][1], str(erg["failed"])[:80])
    check("Fehler: kein abgebrochen, kein finished_ok",
          not erg["abgebrochen"] and not erg["ok"])
    check("ohne abbrechen() bleibt das Flag aus", not erg["worker"].abbruch_angefordert)


def test_abbruch_nach_dem_letzten_schritt():
    """Kommt der Abbruch erst, wenn der Kern nichts mehr meldet, ist das
    Ergebnis vollstaendig - dann gilt es."""
    def func(progress):
        progress("einziger Schritt", 0.5)
        time.sleep(0.4)
        return 42
    erg = _laufen_lassen(func, abbrechen_nach=0.15)
    check("Abbruch ohne weiteren Fortschrittsaufruf: das fertige Ergebnis kommt an",
          erg["ok"] == [42] and not erg["abgebrochen"] and not erg["failed"],
          f"{erg['ok']} / {erg['abgebrochen']}")


def test_ausnahme_direkt():
    """Die Ausnahme selbst: eine Exception, damit ``except Exception`` im
    Kern sie fangen darf, mit dem Text des unterbrochenen Schritts."""
    ex = Abgebrochen("Lastfall 3/12")
    check("Abgebrochen ist eine Exception mit dem Schritt als Text",
          isinstance(ex, Exception) and str(ex) == "Lastfall 3/12")

    w = SolveWorker(lambda p: None)
    w.abbrechen()
    check("abbrechen() setzt das Flag, ohne den Thread zu starten",
          w.abbruch_angefordert and not w.isRunning())


def main():
    print("=" * 92)
    print("STATIK3D - Hintergrundrechnung: Ergebnis, Fehler, Abbruch")
    print("=" * 92)
    for t in (test_ergebnis_kommt_an, test_abbruch_haelt_an, test_abbruch_in_fremder_verpackung,
              test_fehler_bleibt_fehler, test_abbruch_nach_dem_letzten_schritt,
              test_ausnahme_direkt):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:                     # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(t.__name__, False, str(ex)[:80])
    print("\n" + "=" * 92)
    nok = sum(1 for _n, ok in RESULTS if ok)
    print(f"Ergebnis: {nok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN: " + "; ".join(schlecht))
    return 0 if nok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
