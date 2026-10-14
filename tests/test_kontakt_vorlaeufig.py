"""Ergebnisse mit nicht konvergiertem Kontaktlauf sind vorlaeufig (14.10.2026).

Entscheidung des Anwenders vom 14.10.2026 (woertlich): „Ergebnisse des
Entwurf-Laufs (Ankerkraftverlust, Fließen der Ankerringe) gelten als
vorläufig, weil der Kontakt nicht konvergiert ist. Künftig jede Laststufe mit
nicht konvergiertem Kontaktlauf im Ergebnis kennzeichnen.“

Was hier belegt wird - jede Behauptung an einer Rechnung:

1. Reine Kontaktrechnung (Block mit Reibung, Deckel der Reibungsnachpruefung
   kuenstlich auf 1): ``res.info["vorlaeufig"]`` nennt den Kontaktlauf, die
   Zusammenfassung des Ergebnisses und die der Rechnung, der Konvergenzstand
   (Rechenliste), die Meldung der Rechenliste und der Bericht sagen
   „vorläufig – Kontakt nicht konvergiert …“. Die Ergebnisdatei behaelt die
   Kennzeichnung: nach Schreiben und Lesen steht sie unveraendert da.
2. Mit Plastizitaet (fliessender Reibblock, zwei Laststufen, Deckel 1 in den
   plastischen Laeufen, Halbieren aus): die Kennzeichnung nennt die Stufe mit
   nicht konvergiertem Kontaktlauf mit ihrem Lastanteil und den Abschluss -
   die erste Stufe nicht, ihr einziger Lauf ist konvergiert.
3. Konvergiert (derselbe Block ohne Deckel, und ein Lauf, in dem nur der
   elastische Vorlauf gedeckelt ist - er zaehlt nicht): keine Kennzeichnung.

Aufruf:  python -m tests.test_kontakt_vorlaeufig
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_vorl_"), "einstellungen.json")

RESULTS = []
VORL = "vorläufig – Kontakt nicht konvergiert"


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return ok


def _meldung(info) -> str:
    """gui.rechenliste.meldung_aus_info - ohne sie (Stand vor dem 14.10.2026) leer."""
    try:
        from statik3d.gui.rechenliste import meldung_aus_info
    except ImportError:
        return ""
    return meldung_aus_info(info)


def _vorl(info) -> str:
    v = (info or {}).get("vorlaeufig")
    return str(v.get("text", "")) if isinstance(v, dict) else ""


def test_reine_kontaktrechnung():
    print("\n--- Reine Kontaktrechnung, Deckel 1: vorläufig in Info, Zusammenfassung, Liste, Bericht, Datei ---")
    from statik3d import ergebnisse
    from statik3d.examples_lib import block_friction_example
    from statik3d.gui.rechenliste import posten_aus_modell, zustand_aus_info
    from statik3d.report.html import Report
    from tests import test_fehler_p15 as p15
    m = block_friction_example()
    an, meldungen = p15._rechnen(m, nur_vorlauf=False)
    r = an.cases["LF1"]
    t = _vorl(r.info)
    check("res.info['vorlaeufig'] nennt den nicht konvergierten Kontaktlauf",
          t.startswith(VORL) and "Kontaktlauf 1" in t, repr(t))
    zeilen = [z for z in r.summary().splitlines() if VORL in z]
    check("Zusammenfassung des Ergebnisses: eigene Zeile", len(zeilen) == 1, zeilen[0] if zeilen else "keine")
    s = an.summary()
    check("Zusammenfassung der Rechnung: WARNUNG mit dem Lastfall",
          any(z.startswith("WARNUNG") and VORL in z and "LF1" in z for z in s.splitlines()),
          next((z for z in s.splitlines() if VORL in z), "keine Zeile")[:120])
    z = zustand_aus_info(r.info)
    check("Konvergenzstand (Rechenliste): NICHT konvergiert, vorläufig",
          z.startswith("NICHT konvergiert") and VORL in z, z)
    check("Meldung der Rechenliste aus res.info", _meldung(r.info) == t, _meldung(r.info))
    w, app = p15._fenster()
    zust = p15._rechenliste_nach_lauf(w, app, posten_aus_modell(m, "all"), meldungen, an)
    check("Rechenliste am Fenster: Zustand nicht konvergiert, Meldung vorläufig",
          zust.get("LF1", ("", ""))[0] == "nicht konvergiert" and VORL in zust.get("LF1", ("", ""))[1],
          str(zust))
    rep = Report(m, an)
    html = rep.html()
    text = re.sub(r"<[^>]+>", " ", html)
    warn = "\n".join(getattr(rep, "_warnings", []) or [])
    check("Bericht: Kennwerte und Hinweise nennen es",
          VORL in text and any(VORL in x for x in warn.splitlines()),
          next((x[:110] for x in warn.splitlines() if VORL in x), "keine Warnung"))
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_vorl_"), "erg.s3e")
    ergebnisse.schreiben(pfad, m, an)
    an2 = ergebnisse.lesen(pfad, m)
    r2 = an2.cases["LF1"] if hasattr(an2, "cases") else None
    t2 = _vorl(getattr(r2, "info", None))
    check("Ergebnisdatei: nach Schreiben und Lesen dieselbe Kennzeichnung",
          t2 == t and any(VORL in x for x in r2.summary().splitlines()), repr(t2))


def _plastisch_mit_deckel():
    """Fliessender Reibblock, Deckel 1 nur in den plastischen Laeufen, Halbieren aus:
    jeder plastische Kontaktlauf endet am Deckel und zaehlt."""
    from statik3d import contact as _ct
    from statik3d import plastizitaet as pl
    from statik3d import solver
    from tests import test_fehler_p15 as p15
    m = p15._fliessender_block()
    m.plastizitaet.iterationen = 3
    alt_max, alt_pr, alt_h = _ct.MAX_CYCLES, solver._plastizitaet_rechnen, pl.HALBIEREN_MAX

    def plastisch_mit_deckel(*a, **k):
        _ct.MAX_CYCLES = 1
        try:
            return alt_pr(*a, **k)
        finally:
            _ct.MAX_CYCLES = alt_max
    solver._plastizitaet_rechnen = plastisch_mit_deckel
    pl.HALBIEREN_MAX = 0
    try:
        r = solver.solve_static(m)
    finally:
        solver._plastizitaet_rechnen, pl.HALBIEREN_MAX = alt_pr, alt_h
        _ct.MAX_CYCLES = alt_max
    return r


def test_plastizitaet_stufen():
    print("\n--- Plastizitaet: die Kennzeichnung nennt Stufe, Lastanteil und Abschluss ---")
    r = _plastisch_mit_deckel()
    t = _vorl(r.info)
    lb = [e for e in (r.info.get("laeufe") or []) if not e.get("konvergiert")]
    # Stufe 1 (50 %) endet im ersten Kontaktschritt ohne Wechsel und braucht keinen
    # Newton-Schritt: dort ist nichts gedeckelt, und sie wird nicht genannt
    st1 = [e for e in (r.info.get("laeufe") or []) if e.get("stufe") == 1]
    check("Stufe 2 mit ihrem Lastanteil genannt, die konvergierte Stufe 1 nicht",
          t.startswith(VORL) and "Stufe 2 (bis 100 % der Last)" in t and "Stufe 1" not in t
          and st1 and all(e.get("konvergiert") for e in st1), repr(t))
    check("… und der Abschluss", "Abschluss" in t, f"{len(lb)} Läufe am Deckel, Arten "
          f"{sorted({str(e.get('art')) for e in lb})}")
    stufen = (r.info.get("vorlaeufig") or {}).get("stellen") or []
    check("res.info['vorlaeufig']['stellen'] führt die Stellen einzeln, jede einmal",
          stufen == ["Stufe 2 (bis 100 % der Last)", "Abschluss"], str(stufen))


def test_konvergiert_ohne_kennzeichnung():
    print("\n--- Konvergiert: keine Kennzeichnung (auch nicht bei gedeckeltem Vorlauf) ---")
    from statik3d import solver
    from statik3d.examples_lib import block_friction_example
    from statik3d.gui.rechenliste import zustand_aus_info
    from tests import test_fehler_p15 as p15
    r = solver.solve_static(block_friction_example())
    check("Block mit Reibung ohne Deckel: kein Eintrag, keine Zeile",
          "vorlaeufig" not in r.info and "vorläufig" not in r.summary()
          and zustand_aus_info(r.info) == "konvergiert" and _meldung(r.info) == "",
          zustand_aus_info(r.info))
    an, _m = p15._rechnen(p15._fliessender_block(), nur_vorlauf=True)
    r = an.cases["LF1"]
    check("nur der elastische Vorlauf gedeckelt: kein Eintrag (er zählt nicht)",
          r.info.get("contact_vorlauf_nicht_konvergiert") == 1 and "vorlaeufig" not in r.info
          and "vorläufig" not in r.summary(), zustand_aus_info(r.info))


def main() -> int:
    for t in (test_reine_kontaktrechnung, test_plastizitaet_stufen, test_konvergiert_ohne_kennzeichnung):
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
