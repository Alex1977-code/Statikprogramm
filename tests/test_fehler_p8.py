"""
Fehlerliste vom 06.10.2026, Paket P8, Eintrag F12: die wählbare Iteration
„gemeinsam“ für Fließen und Kontakt nimmt nahe der Grenzlast einen anderen Weg
durch die Reibung als die Vorgabe „verschachtelt“, und beide Ergebnisse heißen
„konvergiert“ (Theoriehandbuch § 5e.3: bis 78 N/mm² Unterschied). Bis zum
06.10.2026 warnte davor nur der Tooltip der Auswahl.

Entscheidung der Hauptsitzung (06.10.2026): die Einstellung bleibt - alte
Modelle mit „gemeinsam“ laden und rechnen weiter -, die Oberfläche nennt sie
„gemeinsam (Versuch)“, die Vorgabe bleibt „verschachtelt“, und ein Ergebnis,
das mit „gemeinsam“ gerechnet ist, trägt eine Warnung. Sie geht die Wege, die
Hinweise eines Ergebnisses schon gehen: die Zusammenfassung des Ergebnisses
(Results.summary), die der Rechnung (Analysis.summary) und die Hinweisliste des
Berichts gebündelt über alle Ergebnisse (wie solver.ausweichen_gebuendelt),
und der Strom des Rechenkerns - Protokoll und Spalte „Meldung“ der
Rechenliste.

* test_gemeinsam_traegt_die_warnung: Block mit Reibung, der fließt (wie
  tests.test_plastizitaet._fliessendes_kontaktmodell), mit Lastfall und einer
  direkt gerechneten Kombination; das Modell geht durch to_dict/from_dict wie
  eine alte Datei.
* test_verschachtelt_ohne_warnung: Gegenprobe am selben Modell mit der
  Vorgabe - keine Warnung, Protokoll und Ergebnisschlüssel der Plastizität wie
  bisher, Zahlen wie am Stand d50592e.
* test_beschriftung_der_auswahl: die Auswahl unter Berechnung → Einstellungen
  (offscreen).

Aufruf:  python -m tests.test_fehler_p8
"""
import json
import os
import re
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_fehler_p8_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
_Q0 = {}


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _modell(kontakt: str):
    """Block mit Reibung, Streckgrenze auf 60 % der elastischen
    Vergleichsspannung (Kontakt **und** Fließen), dazu die Kombination K1 =
    1,35 · LF1 - mit Kontakt direkt gerechnet, also ebenfalls mit Fließen."""
    from statik3d import plastizitaet as pl, solver
    from statik3d.examples_lib import block_friction_example
    if "q0" not in _Q0:
        m0 = block_friction_example()
        r0 = solver.solve_static(m0)
        _Q0["q0"] = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
                        if m0.elements[i].mat == "S235")
    m = block_friction_example()
    m.materials["S235"].fy = 0.6 * _Q0["q0"]
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2, iterationen=40,
                                     toleranz=1e-4, kontakt=kontakt)
    lf = next(iter(m.load_cases))
    m.add_combination("K1", {lf: 1.35}, "ULS")
    return m


def _rechnen(m):
    """(Analysis, Textstrom) - der Strom so, wie ihn SolveWorker an Protokoll
    und Rechenliste weitergibt (str(text), ohne den Anteil)."""
    from statik3d import solver
    strom = []
    an = solver.solve_all(m, progress=lambda text, *_a: strom.append(str(text)))
    return an, strom


def _hinweisliste(html: str) -> list:
    """Die Punkte der Liste „Offene Hinweise und Warnungen“ des Berichts."""
    i = html.find("Offene Hinweise und Warnungen:")
    if i < 0:
        return []
    j = html.find("<ul>", i)
    k = html.find("</ul>", j)
    if j < 0 or k < 0:
        return []
    return re.findall(r"<li>(.*?)</li>", html[j:k], re.S)


def _rechenliste(m, strom):
    """Den Strom in die echte Rechenliste einspielen; {Posten: (Zustand, Meldung)}."""
    _app()
    from statik3d.gui.rechenliste import Rechenliste, posten_aus_modell
    rl = Rechenliste()
    rl.posten_setzen(posten_aus_modell(m, "all"))
    for t in strom:
        rl.melden(t)
    rl.beenden("fertig")
    aus = {}
    for i in range(rl.tabelle.rowCount()):
        aus[rl.tabelle.item(i, 0).text()] = (rl.tabelle.item(i, rl.S_ZUSTAND).text(),
                                             rl.tabelle.item(i, rl.S_MELDUNG).text())
    rl.deleteLater()
    return aus


def _warnt(text: str) -> bool:
    """Die Warnung zu „gemeinsam“: nennt die Iteration als Versuch, den
    anderen Reibweg nahe der Grenzlast und die Gegenprobe mit „verschachtelt“."""
    t = str(text)
    return ("„gemeinsam“ (Versuch)" in t and "Grenzlast" in t and "Reibung" in t
            and "„verschachtelt“ gegenprüfen" in t)


def test_gemeinsam_traegt_die_warnung():
    from statik3d.model import Model
    from statik3d.report.html import Report
    from statik3d.gui import rechenliste as rlm
    alt = _modell("gemeinsam")
    m = Model.from_dict(json.loads(json.dumps(alt.to_dict())))
    check("ein Modell mit „gemeinsam“ lädt mit dieser Einstellung (wie eine alte Datei)",
          m.plastizitaet.kontakt == "gemeinsam", repr(m.plastizitaet.kontakt))
    an, strom = _rechnen(m)
    namen = sorted(an.all_results())
    check("Lastfall und Kombination sind gerechnet, beide mit Fließen",
          namen == ["K1", "LF1"]
          and all((r.info.get("plastizitaet") or {}).get("iterationen") for r in an.all_results().values()),
          str(namen))
    for n, r in sorted(an.all_results().items()):
        zeilen = [z for z in r.summary().splitlines() if z.startswith("WARNUNG") and _warnt(z)]
        check(f"{n}: die Zusammenfassung des Ergebnisses trägt die Warnung (WARNUNG …)",
              len(zeilen) == 1, zeilen[0][:110] if zeilen else "fehlt")
    zeilen = [z for z in an.summary().splitlines() if _warnt(z)]
    check("Zusammenfassung der Rechnung: eine Zeile für beide Ergebnisse, mit Namen",
          len(zeilen) == 1 and zeilen[0].startswith("WARNUNG") and "2 Ergebnissen" in zeilen[0]
          and "LF1" in zeilen[0] and "K1" in zeilen[0], zeilen[0][:110] if zeilen else "fehlt")
    hinweise = [h for h in _hinweisliste(Report(m, an).html()) if _warnt(h)]
    check("Bericht: die Warnung steht einmal in „Offene Hinweise und Warnungen“, mit Namen",
          len(hinweise) == 1 and "LF1" in hinweise[0] and "K1" in hinweise[0],
          hinweise[0][:110] if hinweise else "fehlt")
    # Der Strom: Lastfall und Kombination melden sich unterwegs. Bis zum
    # 07.10.2026 rechnete die Kombination ohne Fortschritt
    # (solver.solve_combinations reichte ``progress`` nicht an
    # solve_combination weiter, Nachtrag N31), und die Warnung stand dort nur
    # beim Lastfall. Ketten, Pool und Farm melden weiter nichts.
    warnzeilen = [z for z in strom if _warnt(z)]
    marken = [strom.index(t) if t in strom else -1
              for t in ("Lastfall LF1 (1/1)", "Kombination K1 (1/1)")]
    check("Strom des Rechenkerns (Protokoll): WARNUNG … als letzte Zeile vor „Lastfall LF1“ "
          "und vor „Kombination K1“",
          len(warnzeilen) == 2 and all(z.startswith("WARNUNG: ") and len(z) <= 160 for z in warnzeilen)
          and all(i > 0 and _warnt(strom[i - 1]) for i in marken),
          f"{len(warnzeilen)} Zeilen, Marken {marken}: " + (warnzeilen[0][:80] if warnzeilen else "fehlt"))
    check("die Zeile sagt nichts über die Konvergenz (Zustand der Rechenliste bleibt)",
          all(rlm.zustand_aus_meldung(z, x) == x and not rlm.fortschritt_aus_meldung(z)
              for z in warnzeilen for x in ("", rlm.KONVERGIERT, rlm.NICHT_KONVERGIERT)), "")
    liste = _rechenliste(m, strom)
    check("Rechenliste: in der Spalte „Meldung“ von LF1 und K1 steht am Ende die ganze Warnung",
          set(liste) == {"LF1", "K1"} and _warnt(liste["LF1"][1]) and _warnt(liste["K1"][1]),
          liste.get("K1", ("", ""))[1][:110])


def test_verschachtelt_ohne_warnung():
    """Gegenprobe: dasselbe Modell mit der Vorgabe. Die Zahlen stehen fest wie am
    Stand d50592e (vor dieser Änderung, gemessen 06.10.2026, zweimal
    bitgleich): größte Verschiebung, Kontakt-Iterationen, Kontaktläufe,
    Newton-Schritte und Faktorisierungen der Plastizität. Bitgleich gegen
    d50592e (u und Auflagerkräfte als Feld) ist es außerdem in der Gegenprobe
    der Rückmeldung zu P8 verglichen."""
    from statik3d.report.html import Report
    m = _modell("verschachtelt")
    an, strom = _rechnen(m)
    for n, r in sorted(an.all_results().items()):
        check(f"{n}: keine Warnung in der Zusammenfassung des Ergebnisses",
              not any(_warnt(z) or "gemeinsam" in z for z in r.summary().splitlines()), "")
    check("keine Warnung in der Zusammenfassung der Rechnung",
          not any(_warnt(z) for z in an.summary().splitlines()), "")
    check("keine Warnung im Bericht",
          not any(_warnt(h) for h in _hinweisliste(Report(m, an).html())), "")
    check("keine Warnung im Strom und in der Rechenliste",
          not any(_warnt(z) for z in strom)
          and not any(_warnt(v[1]) for v in _rechenliste(m, strom).values()), "")
    soll = {"LF1": (2.9403970836312483e-06, 84, 7, 5, 3), "K1": (7.844300353569184e-06, 90, 9, 7, 5)}
    for n, (umax, it, laeufe, pl_it, fakt) in soll.items():
        r = an.all_results()[n]
        pz = r.info.get("plastizitaet") or {}
        ist = (float(np.abs(np.asarray(r.u, float)[:, :3]).max()), r.info.get("contact_iterations"),
               r.info.get("contact_laeufe"), pz.get("iterationen"), pz.get("faktorisierungen"))
        check(f"{n}: Zahlen wie am Stand d50592e (u_max, Kontakt, Läufe, Newton, Zerlegungen)",
              abs(ist[0] - umax) <= 1e-12 * umax and ist[1:] == (it, laeufe, pl_it, fakt)
              and pz.get("konvergiert") is True, f"{ist}")
        check(f"{n}: Protokoll und Schlüssel der Plastizität wie bisher (kein Eintrag „kontakt“)",
              "kontakt" not in pz and not any("WARNUNG" in z for z in pz.get("log") or []),
              str(sorted(pz)))


def test_beschriftung_der_auswahl():
    from statik3d.gui.main import MainWindow
    from statik3d.model import Model
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.fehler_liste = []
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER["w"] = w
    cb = w.cb_plast_kontakt
    texte = {cb.itemData(i): cb.itemText(i) for i in range(cb.count())}
    check("Auswahl „Verfahren mit Kontakt“: zwei Einträge, Werte unverändert",
          list(texte) == ["verschachtelt", "gemeinsam"], str(texte))
    check("„verschachtelt (Vorgabe)“ und „gemeinsam (Versuch)“",
          texte.get("verschachtelt") == "verschachtelt (Vorgabe)"
          and texte.get("gemeinsam") == "gemeinsam (Versuch)", str(texte))
    w.new_model()
    app.processEvents()
    check("ein neues Modell steht auf „verschachtelt“",
          cb.currentData() == "verschachtelt" and w.model.plastizitaet.kontakt == "verschachtelt",
          f"{cb.currentData()} / {w.model.plastizitaet.kontakt}")
    tip = cb.toolTip()
    check("der Tooltip nennt den Versuch und die Warnung im Ergebnis",
          "Versuch" in tip and "Warnung" in tip, "")
    alt = Model.from_dict(json.loads(json.dumps(_modell("gemeinsam").to_dict())))
    w._modell_setzen(alt)
    app.processEvents()
    check("ein Modell mit „gemeinsam“ zeigt „gemeinsam (Versuch)“",
          cb.currentText() == "gemeinsam (Versuch)", cb.currentText())
    w._plast_schreiben(w.model.plastizitaet)
    check("… und schreibt beim Übernehmen weiter „gemeinsam“ zurück",
          w.model.plastizitaet.kontakt == "gemeinsam", w.model.plastizitaet.kontakt)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_gemeinsam_traegt_die_warnung, test_verschachtelt_ohne_warnung,
              test_beschriftung_der_auswahl):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
