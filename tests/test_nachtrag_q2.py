"""
Nachtrag zur Fehlerliste vom 06.10.2026, Paket Q2 (07.10.2026): Bericht und
Rechenliste einer Rechnung mit Fließen und Kontakt. Das Modell ist der Block
mit Reibung, der fließt, mit Lastfall LF1 und der direkt gerechneten
Kombination K1 = 1,35 · LF1 (tests.test_fehler_p8._modell).

* N31 test_n31_kombination_meldet: eine direkt gerechnete Kombination meldete
  keinen Fortschritt - solve_combinations rief solve_combination im
  nichtlinearen Weg ohne ``progress``. Zwischen den Marken „Lastfall LF1
  (1/1)“ und „Kombination K1 (1/1)“ stand nichts, in der Rechenliste blieben
  Schritte, Konvergenz und Meldung von K1 leer, und ein Abbruch griff erst
  nach der Kombination. Dazu: derselbe Lauf ohne Fortschritt rechnet bitgleich
  (der Rechenweg bleibt), und der Balken bleibt im Fenster der Kombinationen.
* N32 test_n32_bericht_nennt_plastizitaet: der Bericht sagte unter
  „Gültigkeitsbereich und Hinweise“ ohne Bedingung „Die Berechnung ist
  elastisch (keine Plastizität, …)“, auch wenn Elemente fließen.
* N33 test_n33_handbuchsatz_anfangsdehnung: das Benutzerhandbuch (und
  Theoriehandbuch § 5e.3) sagte, mit Anfangsdehnung bleibe „gemeinsam“
  bitgleich zu „verschachtelt“. Gemessen am ideal plastischen Block mit
  Reibung: nicht bitgleich, der Unterschied ist der Weg (andere Zahl
  Kontaktschritte), kein Rauschen (jeder Weg zweimal bitgleich).
* N36 test_n36_vorlauf_im_bericht: die Abbruchzeile eines gedeckelten
  elastischen Vorlaufs („… abgebrochen - das Ergebnis ist nicht
  auskonvergiert (Kontaktlauf 1)“) stand unter den Hinweisen des Berichts,
  auch wenn das Ergebnis konvergiert ist. Gegenprobe: ein gedeckelter Lauf,
  der zählt, heißt weiter „nicht auskonvergiert“.

Aufruf:  python -m tests.test_nachtrag_q2
"""
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
    tempfile.mkdtemp(prefix="statik3d_nachtrag_q2_"), "einstellungen.json")

RESULTS = []
_ERG = {}


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def _rechnung():
    """(Modell, Analyse, Strom [(Text, Anteil)]) des fließenden Blocks mit
    Reibung - einmal gerechnet, von N31 und N32 gelesen."""
    if "an" not in _ERG:
        from statik3d import solver
        from tests.test_fehler_p8 import _modell
        m = _modell("verschachtelt")
        strom = []
        an = solver.solve_all(m, progress=lambda text, *a: strom.append((str(text), a[0] if a else None)))
        _ERG.update(m=m, an=an, strom=strom)
    return _ERG["m"], _ERG["an"], _ERG["strom"]


def _rechenliste(m, an, strom) -> dict:
    """Den Strom in die echte Rechenliste einspielen und sie abschließen wie
    SolveWorker.finished_ok (fertig_mit); {Posten: {Spalte: Text}}."""
    from tests.test_fehler_p8 import _app
    _app()
    from statik3d.gui.rechenliste import Rechenliste, posten_aus_modell
    rl = Rechenliste()
    rl.posten_setzen(posten_aus_modell(m, "all"))
    for t, _a in strom:
        rl.melden(t)
    rl.fertig_mit(an)
    aus = {}
    for i in range(rl.tabelle.rowCount()):
        aus[rl.tabelle.item(i, 0).text()] = {
            "Zustand": rl.tabelle.item(i, rl.S_ZUSTAND).text(),
            "Schritte": rl.tabelle.item(i, rl.S_SCHRITTE).text(),
            "Konvergenz": rl.tabelle.item(i, rl.S_KONVERGENZ).text(),
            "Meldung": rl.tabelle.item(i, rl.S_MELDUNG).text()}
    rl.deleteLater()
    return aus


# ---------------------------------------------------------------------------
# N31
# ---------------------------------------------------------------------------
def test_n31_kombination_meldet():
    from statik3d import solver
    from tests.test_fehler_p8 import _modell
    m, an, strom = _rechnung()
    texte = [t for t, _a in strom]
    i_lf = texte.index("Lastfall LF1 (1/1)") if "Lastfall LF1 (1/1)" in texte else -1
    i_k = next((k for k, t in enumerate(texte) if t.startswith("Kombination K1 (1/1)")), -1)
    dazwischen = strom[i_lf + 1:i_k] if 0 <= i_lf < i_k else []
    check("Aufbau: Marke LF1 vor Marke K1 im Strom", 0 <= i_lf < i_k, f"{i_lf} / {i_k}")
    check("N31 K1 meldet ihre Kontakt-Iterationen und Plastizitätsschritte",
          any(t.startswith("Kontakt-Iteration") for t, _a in dazwischen)
          and any(t.startswith("Plastizität: Laststufe") for t, _a in dazwischen),
          f"{len(dazwischen)} Zeilen zwischen den Marken: {[t[:40] for t, _a in dazwischen[:3]]}")
    anteile = [a for _t, a in dazwischen if a is not None]
    check("N31 … der Balken bleibt dabei im Fenster der Kombinationen (0,60 bis 0,90)",
          anteile and all(0.60 <= a <= 0.90 for a in anteile),
          f"{len(anteile)} Anteile, {min(anteile):.3f} bis {max(anteile):.3f}" if anteile else "keine")
    liste = _rechenliste(m, an, strom)
    k1, lf1 = liste.get("K1", {}), liste.get("LF1", {})
    # Den Zaehler „Plast.“ zeigt die Liste beim Newton-Verfahren auch beim
    # Lastfall nicht (seine Zeile heisst „Newton-Schritt“) - verglichen wird
    # darum mit LF1, nicht mit der Spaltenbeschreibung
    check("N31 Rechenliste: bei K1 stehen Schritte, Konvergenz und Meldung wie bei LF1",
          k1.get("Schritte", "").startswith("Kontakt ") and lf1.get("Schritte", "").startswith("Kontakt ")
          and k1.get("Konvergenz") and lf1.get("Konvergenz")
          and k1.get("Meldung", "").startswith("Plastizität: 14 Elemente fließen")
          and lf1.get("Meldung", "").startswith("Plastizität: 4 Elemente fließen"), f"K1 {k1}")
    check("N31 … und der Zustand von K1 wird gelesen wie der von LF1",
          k1.get("Zustand") == lf1.get("Zustand") and k1.get("Zustand") not in ("", "offen"),
          f"K1 {k1.get('Zustand')!r}, LF1 {lf1.get('Zustand')!r}")
    # Der Rechenweg bleibt: dasselbe Modell ohne Fortschritt, Feld fuer Feld
    m2 = _modell("verschachtelt")
    an2 = solver.solve_all(m2)
    gleich = []
    for n in ("LF1", "K1"):
        a, b = an.all_results()[n], an2.all_results()[n]
        pa, pb = a.info.get("plastizitaet") or {}, b.info.get("plastizitaet") or {}
        gleich.append(np.array_equal(a.u, b.u) and np.array_equal(a.reactions, b.reactions)
                      and np.array_equal(a.contact_forces, b.contact_forces)
                      and all(a.info.get(k) == b.info.get(k) for k in
                              ("contact_iterations", "contact_laeufe", "contact_factorisations"))
                      and all(pa.get(k) == pb.get(k) for k in
                              ("iterationen", "faktorisierungen", "fliessend", "konvergiert")))
    check("N31 mit und ohne Fortschritt bitgleich (u, Auflager- und Kontaktkräfte, Zähler)",
          all(gleich), str(gleich))
    r = an.all_results()["K1"]
    pz = r.info.get("plastizitaet") or {}
    ist = (float(np.abs(np.asarray(r.u, float)[:, :3]).max()), r.info.get("contact_iterations"),
           r.info.get("contact_laeufe"), pz.get("iterationen"), pz.get("faktorisierungen"))
    check("N31 K1 wie am Stand d50592e (tests.test_fehler_p8: u_max, Kontakt, Läufe, Newton, Zerlegungen)",
          abs(ist[0] - 7.844300353569184e-06) <= 1e-12 * 7.844300353569184e-06
          and ist[1:] == (90, 9, 7, 5), str(ist))

    # Ein Abbruch greift jetzt in der Kombination: bei der ersten
    # Kontakt-Iteration nach der Marke von LF1 halten
    class Halt(Exception):
        pass

    gesehen = []

    def prog(text, *_a):
        gesehen.append(str(text))
        if "Lastfall LF1 (1/1)" in gesehen and str(text).startswith("Kontakt-Iteration"):
            raise Halt()

    teil = None
    try:
        solver.solve_all(_modell("verschachtelt"), progress=prog)
    except Halt as ex:
        teil = getattr(ex, "teilanalyse", None)
    check("N31 Abbruch mitten in K1: LF1 bleibt, K1 ist nicht fertig",
          teil is not None and sorted(teil.cases) == ["LF1"] and not teil.combinations,
          "lief durch" if teil is None else f"{sorted(teil.cases)} / {sorted(teil.combinations)}")


# ---------------------------------------------------------------------------
# N32
# ---------------------------------------------------------------------------
def _rechenart(html: str) -> str:
    """Der erste Punkt unter „Gültigkeitsbereich und Hinweise“ (die
    Überschrift im Text, nicht der Eintrag im Inhaltsverzeichnis)."""
    t = re.search(r"Gültigkeitsbereich und Hinweise</h\d>", html)
    i = t.start() if t else -1
    j = html.find("<li>", i)
    k = html.find("</li>", j)
    return _text(html[j:k]) if i >= 0 and j >= 0 and k >= 0 else ""


def test_n32_bericht_nennt_plastizitaet():
    from statik3d import solver
    from statik3d.examples_lib import block_friction_example
    from statik3d.report.html import Report
    from tests.test_fehler_p8 import _modell
    m, an, _strom = _rechnung()
    fl = {n: (r.info.get("plastizitaet") or {}).get("fliessend") for n, r in an.all_results().items()}
    check("Aufbau: LF1 und K1 mit Fließen gerechnet, in beiden fließen Elemente",
          fl.get("LF1", 0) > 0 and fl.get("K1", 0) > 0, str(fl))
    satz = _rechenart(Report(m, an).html())
    check("N32 der Satz sagt nicht mehr „elastisch (keine Plastizität …)“",
          satz and "keine Plastizität" not in satz and "ist elastisch (" not in satz, satz[:120])
    check("N32 … sondern: mit Plastizität, 2 von 2 Ergebnissen, Werkstoffgesetz, E_t/E",
          "Plastizität" in satz and "2 von 2 Ergebnissen" in satz and "von Mises" in satz
          and "isotroper linearer Verfestigung" in satz and "E_t/E = 5 %" in satz, satz[:220])
    check(f"N32 … mit der Zahl fließender Elemente (höchstens {max(fl.values())})",
          f"in 2 davon fließen Elemente, höchstens {max(fl.values())} je Ergebnis" in satz, satz[:260])
    check("N32 … Theorie wie bisher (keine Theorie III. Ordnung, Theorie I. Ordnung)",
          "keine Theorie III. Ordnung/große Verformungen" in satz
          and "Gerechnet wird nach Theorie I. Ordnung" in satz, "")
    # Plastizitaet an, aber nichts fliesst: gerechnet ist trotzdem mit Fliessen
    m3 = _modell("verschachtelt")
    m3.materials["S235"].fy *= 100.0
    an3 = solver.solve_all(m3)
    satz3 = _rechenart(Report(m3, an3).html())
    check("N32 Plastizität an, nichts fließt: „in keinem davon fließt ein Element“",
          "2 von 2 Ergebnissen" in satz3 and "in keinem davon fließt ein Element" in satz3, satz3[:220])
    # Gegenprobe: ohne Plastizitaet bleibt der Satz Wort fuer Wort
    m2 = block_friction_example()
    satz2 = _rechenart(Report(m2, solver.solve_all(m2)).html())
    check("N32 Gegenprobe elastisch: der Satz wie bisher",
          satz2.startswith("Die Berechnung ist elastisch (keine Plastizität, keine Theorie "
                           "III. Ordnung/große Verformungen). Gerechnet wird nach Theorie I. Ordnung"),
          satz2[:120])


# ---------------------------------------------------------------------------
# N33
# ---------------------------------------------------------------------------
def test_n33_handbuchsatz_anfangsdehnung():
    from statik3d import solver
    from tests.handbuch import absatz
    from tests.test_plastizitaet import _block_mit_reibung
    r = {}
    for weg in ("verschachtelt", "gemeinsam"):
        m = _block_mit_reibung(-20e6, 4e6)
        m.plastizitaet.kontakt = weg
        r[weg] = solver.solve_static(m)
    rv, rg = r["verschachtelt"], r["gemeinsam"]
    pv, pg = rv.info["plastizitaet"], rg.info["plastizitaet"]
    av = [e["art"] for e in rv.info.get("laeufe") or []]
    ag = [e["art"] for e in rg.info.get("laeufe") or []]
    check("Aufbau: beide Wege rechnen Anfangsdehnung und konvergieren",
          pv.get("verfahren") == pg.get("verfahren") == "anfangsdehnung"
          and pv.get("konvergiert") and pg.get("konvergiert"), f"{pv.get('verfahren')} / {pg.get('verfahren')}")
    check("N33 gemeinsam: nichts abgekürzt, nur der Vorlauf entfällt (Laufbuch)",
          av[:1] == ["Vorlauf"] and "Vorlauf" not in ag
          and not any(e.get("abgekuerzt") for e in rg.info.get("laeufe") or []),
          f"{len(av)} / {len(ag)} Läufe")
    uv, ug = np.asarray(rv.u, float), np.asarray(rg.u, float)
    du, umax = float(np.abs(uv - ug).max()), float(np.abs(uv).max())
    check("N33 gemessen: nicht bitgleich, aber auf 1e-6 relativ gleich (anderer Weg)",
          not np.array_equal(uv, ug) and 0.0 < du <= 1e-6 * umax
          and rv.info.get("contact_iterations") != rg.info.get("contact_iterations"),
          f"max |Δu| {du:.2e} m bei u_max {umax:.2e} m, Kontaktschritte "
          f"{rv.info.get('contact_iterations')} / {rg.info.get('contact_iterations')}")
    bh = absatz("**Fließen und Kontakt: verschachtelt oder gemeinsam**")
    check("N33 Benutzerhandbuch: nicht mehr „das Ergebnis bleibt bitgleich“",
          bh and "das Ergebnis bleibt bitgleich" not in bh, "")
    check("N33 … sondern „nicht bitgleich“ mit der Messung und „Bis zum 07.10.2026“",
          "nicht bitgleich" in bh and "1,0·10⁻¹¹ m" in bh and "Bis zum 07.10.2026" in bh, "")
    th = absatz("1. Kein elastischer Vorlauf.", "Theoriehandbuch.md")
    check("N33 Theoriehandbuch § 5e.3: ebenso",
          th and "Ergebnis bleibt bitgleich" not in th and "nicht bitgleich" in th, th[:80])


# ---------------------------------------------------------------------------
# N36
# ---------------------------------------------------------------------------
def _mit_deckel(nur_vorlauf: bool):
    """solve_all mit Deckel 1 der Reibungsnachprüfung, nur im elastischen
    Vorlauf oder in jedem Lauf (wie tests.test_fehler_p15._rechnen, aber der
    Deckel kommt nach dem Fließen zurück: auch der Vorlauf von K1 ist
    gedeckelt)."""
    from statik3d import contact as _ct
    from statik3d import solver
    from tests.test_fehler_p8 import _modell
    m = _modell("verschachtelt")
    alt_max, alt_pr = _ct.MAX_CYCLES, solver._plastizitaet_rechnen

    def plastisch_ohne_deckel(*a, **k):
        _ct.MAX_CYCLES = alt_max
        try:
            return alt_pr(*a, **k)
        finally:
            _ct.MAX_CYCLES = 1

    _ct.MAX_CYCLES = 1
    if nur_vorlauf:
        solver._plastizitaet_rechnen = plastisch_ohne_deckel
    try:
        an = solver.solve_all(m, workers=1)
    finally:
        _ct.MAX_CYCLES = alt_max
        solver._plastizitaet_rechnen = alt_pr
    return m, an


def test_n36_vorlauf_im_bericht():
    from statik3d import solver
    from statik3d.report.html import Report
    from tests.test_fehler_p8 import _hinweisliste
    m, an = _mit_deckel(nur_vorlauf=True)
    zust = {n: solver.konvergenz_zustand(r.info) for n, r in an.all_results().items()}
    check("Aufbau: nur der Vorlauf gedeckelt, LF1 und K1 konvergiert",
          zust == {"LF1": "konvergiert", "K1": "konvergiert"}
          and all(r.info.get("contact_vorlauf_nicht_konvergiert") == 1 for r in an.all_results().values()),
          str(zust))
    for titel, opt in (("Bericht", None), ("Bericht, K1 gebündelt", {"max_contact_results": 1})):
        html = Report(m, an, options=opt).html()
        text = _text(html)
        check(f"N36 {titel}: keine Zeile „nicht auskonvergiert“",
              "nicht auskonvergiert" not in text,
              next((z.strip()[:120] for z in text.splitlines() if "nicht auskonvergiert" in z), ""))
        hinweise = [_text(h) for h in _hinweisliste(html)]
        vorlauf = [h for h in hinweise if "abgebrochen" in h]
        check(f"N36 {titel}: jede Abbruchzeile nennt den Vorlauf und das konvergierte Ergebnis",
              len(vorlauf) >= 2 and all("nur im elastischen Vorlauf, der nicht zählt; das Ergebnis "
                                        "ist konvergiert" in h for h in vorlauf),
              (vorlauf[0][:200] if vorlauf else "keine"))
        if opt:
            # K1 steht nur in der gebuendelten Zeile, ohne Laufnummer
            check(f"N36 {titel}: die gebündelte Zeile nennt K1 und den Vorlauf",
                  any(h.startswith("Kontakt (1 weitere Ergebnisse, z. B. K1)") for h in vorlauf),
                  str([h[:60] for h in vorlauf]))
        else:
            check(f"N36 {titel}: die Zeile mit der Laufnummer steht da (LF1 und K1)",
                  all(any(h.startswith(f"Kontakt {n}:") and "(Kontaktlauf 1)" in h for h in vorlauf)
                      for n in ("LF1", "K1")),
                  str([h[:60] for h in vorlauf]))
    # Gegenprobe: jeder Lauf gedeckelt - die Laeufe, die zaehlen, heissen
    # weiter „nicht auskonvergiert“, der Vorlauf nur Vorlauf
    m2, an2 = _mit_deckel(nur_vorlauf=False)
    r2 = an2.cases["LF1"]
    rep = Report(m2, an2)
    text2 = _text(rep.html())
    warn = "\n".join(rep._warnings)
    check("Gegenprobe Aufbau: LF1 nicht konvergiert", not solver.kontakt_konvergiert(r2.info),
          solver.konvergenz_zustand(r2.info)[:80])
    check("N36 Gegenprobe: ein gedeckelter Lauf, der zählt, heißt weiter „nicht auskonvergiert“",
          re.search(r"nicht auskonvergiert \(Kontaktlauf ([2-9]|\d\d+)\)", text2) is not None
          and "Kontakt LF1: Iteration nicht konvergiert" in warn, "")
    check("N36 Gegenprobe: der Vorlauf heißt Vorlauf, ohne „konvergiert“ zu behaupten",
          "(Kontaktlauf 1) – im elastischen Vorlauf, der nicht zählt" in text2
          and "nicht auskonvergiert (Kontaktlauf 1)" not in text2
          and "Vorlauf, der nicht zählt; das Ergebnis ist konvergiert" not in text2, "")


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1500, exit=True)
    for t in (test_n31_kombination_meldet, test_n32_bericht_nennt_plastizitaet,
              test_n33_handbuchsatz_anfangsdehnung, test_n36_vorlauf_im_bericht):
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
