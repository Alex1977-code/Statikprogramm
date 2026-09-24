"""Das Fenster mit der Liste der Lastfaelle: Postenliste, Marken, Konvergenz.

Waehrend einer Rechnung zeigte Statik3D einen Balken und das Protokoll. Bei
422 Lastfaellen sagt das wenig - welcher laeuft, wie lange brauchte der
vorige, wie weit ist er konvergiert, auf wie vielen Rechnern laeuft es. Das
Fenster fuehrt je Posten eine Zeile.

Geprueft wird hier sein Verstand, nicht seine Oberflaeche: welche Posten eine
Rechnung hat und was eine Meldung bedeutet. Das sind reine Funktionen ohne
Qt und laufen darum im gewoehnlichen Gesamtlauf mit.

Aufruf:  python -m tests.test_rechenliste
"""
import os
import sys

# Die Oberflaechenprobe unten braucht keinen Bildschirm - und soll auf dem
# Rechner des Anwenders waehrend des Gesamtlaufs kein Fenster aufblitzen
# lassen. Das muss vor der ersten QApplication stehen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.gui import rechenliste as rl                      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return ok


class _Kombi:
    def __init__(self, name):
        self.name = name


class _Modell:
    def __init__(self, faelle, kombis, aktiv=None):
        self.load_cases = faelle
        self.combinations = [_Kombi(k) for k in kombis]
        self.active_case = aktiv


def test_posten_aus_modell():
    """"all" rechnet Lastfaelle und danach Kombinationen, "case" nur den
    aktiven; fuer Eigenwerte und Beulen gibt es keine Liste."""
    m = _Modell(["LF1", "LF3", "LF5"], ["GZT1", "GZT2"], aktiv="LF3")
    alle = rl.posten_aus_modell(m, "all")
    check("all: erst die Lastfaelle, dann die Kombinationen",
          alle == [("LF1", "Lastfall"), ("LF3", "Lastfall"), ("LF5", "Lastfall"),
                   ("GZT1", "Kombination"), ("GZT2", "Kombination")], str(alle))
    check("case: nur der aktive Lastfall",
          rl.posten_aus_modell(m, "case") == [("LF3", "Lastfall")])
    check("modal und buckling haben keine Postenliste",
          rl.posten_aus_modell(m, "modal") == [] and rl.posten_aus_modell(m, "buckling") == [])
    leer = _Modell([], [], aktiv=None)
    check("ein Modell ohne Lastfaelle bleibt ohne Posten",
          rl.posten_aus_modell(leer, "all") == [] and rl.posten_aus_modell(leer, "case") == [])


def test_marke_lesen():
    """Die Fertigmeldung des Rechenkerns ist die einzige Marke, an der das
    Fenster einen Posten abschliesst (solver._solve_cases_innen,
    solve_combinations)."""
    check("Lastfall mit Zaehler",
          rl.marke_lesen("Lastfall LF3 (2/422)") == ("Lastfall", "LF3", 2, 422))
    check("Kombination mit Zaehler",
          rl.marke_lesen("Kombination GZT 1,35G+1,5Q (7/54)")
          == ("Kombination", "GZT 1,35G+1,5Q", 7, 54))
    check("Zusatz hinter dem Zaehler stoert nicht",
          rl.marke_lesen("Lastfall LF1 (1/3) – Situation Ankerausfall")
          == ("Lastfall", "LF1", 1, 3))
    for kein in ("Kontakt-Iteration 12: 13902 aktiv", "Plastizität: Laststufe 2/3, Schritt 1",
                 "Gleichungssystem aufgestellt (476214 aktive FHG)", ""):
        if not check("keine Marke: %r" % kein[:40], rl.marke_lesen(kein) is None):
            break


def test_fortschritt_aus_meldung():
    """Schritt und Konvergenzzahl kommen aus denselben Zeilen, die der
    Rechenkern ohnehin meldet - solver:2972 und plastizitaet:399. Die Zahl
    dahinter ist das, was der Anwender „Konvergenzstand" nennt."""
    d = rl.fortschritt_aus_meldung("Kontakt-Iteration 12: 13902 aktiv, Δu 3.2e-05, Matrix bleibt")
    check("Kontakt: Schrittnummer", d.get("kontakt") == 12, str(d))
    check("Kontakt: Delta u als Konvergenzmass", d.get("mass") == "Δu 3.2e-05", str(d))
    check("Kontakt ohne Konvergenzzahl bleibt ohne Mass",
          rl.fortschritt_aus_meldung("Kontakt-Iteration 1: 13902 aktiv, Matrix neu")
          == {"kontakt": 1})
    p = rl.fortschritt_aus_meldung(
        "Plastizität: Laststufe 2/3, Schritt 5: 184 Elemente fließen, Änderung 8.13e-07")
    check("Plastizitaet: Laststufe und Schritt",
          p.get("laststufe") == (2, 3) and p.get("plastisch") == 5, str(p))
    check("Plastizitaet: Aenderung als Konvergenzmass", p.get("mass") == "Änderung 8.13e-07", str(p))
    check("bezugslose Angabe mit Einheit: nur die Zahl",
          rl.fortschritt_aus_meldung("Kontakt-Iteration 3: 0 aktiv, Δu 1.0e-09 m, Matrix bleibt")
          .get("mass") == "Δu 1.0e-09")
    for kein in ("Gleichungssystem aufgestellt (476214 aktive FHG)", "System gelöst",
                 "Lastfall LF3 (2/422)", ""):
        if not check("kein Schritt in: %r" % kein[:40], rl.fortschritt_aus_meldung(kein) == {}):
            break


def test_schritte_text():
    """Beide Zaehler nebeneinander: am Drehlager kostet ein warmer Lastfall
    46 Kontaktschritte auf 19 Plastizitaetsschritte (gemessen 20.09.2026)."""
    check("nur Kontakt", rl.schritte_text({"kontakt": 46}) == "Kontakt 46")
    check("Kontakt und Plastizitaet",
          rl.schritte_text({"kontakt": 46, "plastisch": 19, "laststufe": (3, 3)})
          == "Kontakt 46 · Plast. 19 (Stufe 3/3)",
          rl.schritte_text({"kontakt": 46, "plastisch": 19, "laststufe": (3, 3)}))
    check("eine einzige Laststufe wird nicht erwaehnt",
          rl.schritte_text({"plastisch": 4, "laststufe": (1, 1)}) == "Plast. 4")
    check("nichts gemeldet, nichts geschrieben", rl.schritte_text({}) == "")


def test_zustand_aus_meldung():
    """„NICHT konvergiert" muss vor „konvergiert" geprueft werden, sonst
    verschluckt die Teilzeichenkette die Verneinung."""
    check("konvergiert wird erkannt",
          rl.zustand_aus_meldung("Kontakt-Iterationen 12 (konvergiert)", "") == "konvergiert")
    check("NICHT konvergiert wird nicht als konvergiert gelesen",
          rl.zustand_aus_meldung("Kontakt-Iterationen 40  (NICHT konvergiert)", "")
          == "nicht konvergiert")
    check("eine Meldung ohne Aussage laesst den Stand stehen",
          rl.zustand_aus_meldung("Kontakt-Iteration 7: 13902 aktiv", "konvergiert") == "konvergiert")
    check("die Verneinung klebt: ein gekappter Lauf zaehlt fuer den ganzen Posten",
          rl.zustand_aus_meldung("Kontakt-Iterationen 12 (konvergiert)", "nicht konvergiert")
          == "nicht konvergiert")


def test_deckelmeldung_ist_nicht_konvergiert():
    """Die Deckelmeldung des Loesers las die Liste als „konvergiert“.

    Sie lautet „... abgebrochen - das Ergebnis ist nicht auskonvergiert“
    (solver.solve_with_contact). Geprueft wurde erst „nicht konvergiert“ -
    das steht nicht darin - und dann „konvergiert“ - das steht in
    „auskonvergiert“. Eine andere Meldung mit „konvergiert“ ohne Verneinung
    gibt es im Fortschrittsstrom nicht: die Liste zeigte „konvergiert“ also
    genau bei dem Lastfall, dessen Reibungsnachpruefung aufgegeben hatte
    (Nachpruefung der Loesersitzung, 22.09.2026)."""
    deckel = ("Kontakt: Nachprüfung der Reibung nach 40 Zustandswechseln abgebrochen - "
              "das Ergebnis ist nicht auskonvergiert")
    z = rl.zustand_aus_meldung(deckel, "")
    check("die Deckelmeldung des Loesers heisst nicht konvergiert",
          z == "nicht konvergiert", repr(z))
    z = rl.zustand_aus_meldung("Kontakt: Nachpruefung der Reibung nach 40 "
                               "Zustandswechseln abgebrochen", "")
    check("ebenso die Zeile des Kontaktsystems (ohne das Wort konvergiert)",
          z == "nicht konvergiert", repr(z))
    z = rl.zustand_aus_meldung("Kontakt-Iteration nach 120 Schritten nicht konvergiert", "")
    check("die Schrittgrenze der Kontakt-Iteration", z == "nicht konvergiert", repr(z))
    z = rl.zustand_aus_meldung("Plastizität: 3 Elemente fließen - NICHT KONVERGIERT", "")
    check("Grossschrift aendert nichts", z == "nicht konvergiert", repr(z))
    probe = ("Probelauf: ein Kontaktschritt gerechnet, nicht auskonvergiert - "
             "das Ergebnis ist ein Netzmaß, kein Nachweis")
    z = rl.zustand_aus_meldung(probe, "")
    check("der Probelauf heisst Probelauf - weder konvergiert noch gescheitert",
          z == "Probelauf", repr(z))
    z = rl.zustand_aus_meldung("Plastizität: Laststufe 1 nach 40 Schritten nicht konvergiert",
                               "Probelauf")
    check("und bleibt es: sein Ergebnis ist ein Netzmass, kein Nachweis",
          z == "Probelauf", repr(z))
    z = rl.zustand_aus_meldung("Vernetzen abgebrochen: 3 Volumen bleiben ohne Netz", "")
    check("ein Abbruch, der nicht die Reibung betrifft, sagt nichts ueber Konvergenz",
          z == "", repr(z))


def _mit_deckel(max_cycles, fn):
    """fn() mit einem kuenstlich niedrigen Deckel der Reibungsnachpruefung."""
    from statik3d import contact as _ct
    alt = _ct.MAX_CYCLES
    _ct.MAX_CYCLES = max_cycles
    try:
        return fn()
    finally:
        _ct.MAX_CYCLES = alt


def test_deckel_im_fortschrittsstrom():
    """Am echten Strom des Rechenkerns: der Block mit Reibung, Deckel 1 (so
    greift er nachweislich, test_kontakthalt). Was die Liste aus den
    Meldungen liest und was ``zustand_aus_info`` aus res.info liest, muss
    beides „nicht konvergiert“ sein."""
    from statik3d import solver
    from statik3d.examples_lib import block_friction_example
    meldungen = []
    r = _mit_deckel(1, lambda: solver.solve_static(block_friction_example(),
                                                   progress=meldungen.append))
    z = ""
    for t in meldungen:
        if isinstance(t, str):
            z = rl.zustand_aus_meldung(t, z)
    deckel = [t for t in meldungen if isinstance(t, str) and "abgebrochen" in t]
    check("der Deckel greift und steht im Fortschrittsstrom", bool(deckel),
          (deckel[0] if deckel else "keine Zeile")[:90])
    check("die Liste liest daraus nicht konvergiert", z == "nicht konvergiert", repr(z))
    zi = rl.zustand_aus_info(r.info)
    check("und aus res.info ebenso", zi.startswith("NICHT konvergiert"), zi)
    r0 = solver.solve_static(block_friction_example())
    zi = rl.zustand_aus_info(r0.info)
    check("ohne Deckel: konvergiert", zi == "konvergiert", zi)


def test_zustand_aus_info():
    """Die Kennzeichnung eines fertigen Postens aus res.info - aus den Zahlen,
    die der Loeser je Kontaktlauf fuehrt, nicht aus dem Text.

    Regel: jeder gedeckelte Lauf zaehlt, **ausser dem elastischen Vorlauf**
    einer Rechnung mit Fliessen - dessen Kontaktzustand geht nicht weiter,
    und sein u wird ueberschrieben (gemessen in test_vorlauf_mit_deckel).
    Eine Stufe „eingeschraenkt“ gibt es nicht: ob ein Lastfall mit
    gedeckeltem Zwischenlauf als Nachweis gilt, entscheidet der Anwender."""
    Z = rl.zustand_aus_info
    check("ohne Kontakt und ohne Fliessen: konvergiert", Z({}) == "konvergiert", Z({}))
    check("None stuerzt nicht ab", Z(None) == "konvergiert")
    ok = {"contact_laeufe": 1, "contact_laeufe_nicht_konvergiert": 0,
          "contact_letzter_lauf_konvergiert": True, "contact_converged": True}
    check("ein konvergierter Kontaktlauf", Z(ok) == "konvergiert", Z(ok))
    gedeckelt = {"contact_laeufe": 1, "contact_laeufe_nicht_konvergiert": 1,
                 "contact_letzter_lauf_konvergiert": False, "contact_converged": False}
    z = Z(gedeckelt)
    check("ein gedeckelter Kontaktlauf: NICHT konvergiert mit Grund",
          z.startswith("NICHT konvergiert: ") and "Kontakt" in z, z)
    zwischen = {"contact_laeufe": 12, "contact_laeufe_nicht_konvergiert": 3,
                "contact_letzter_lauf_konvergiert": True, "contact_converged": False,
                "contact_vorlauf_laeufe": 1, "contact_vorlauf_nicht_konvergiert": 0,
                "plastizitaet": {"konvergiert": True}}
    z = Z(zwischen)
    check("gedeckelte Zwischenlaeufe zaehlen, auch wenn der letzte konvergiert",
          z.startswith("NICHT konvergiert") and "3 von 11" in z, z)
    letzter = dict(zwischen, contact_laeufe_nicht_konvergiert=1,
                   contact_letzter_lauf_konvergiert=False)
    z = Z(letzter)
    check("der letzte Lauf wird eigens genannt", "letzte" in z, z)
    vorlauf = dict(zwischen, contact_laeufe_nicht_konvergiert=1,
                   contact_vorlauf_nicht_konvergiert=1)
    z = Z(vorlauf)
    check("allein der Vorlauf gedeckelt: konvergiert", z == "konvergiert", z)
    ohne_vorlaufzahl = dict(vorlauf)
    del ohne_vorlaufzahl["contact_vorlauf_nicht_konvergiert"]
    z = Z(ohne_vorlaufzahl)
    check("ohne die Vorlaufzahl wird nichts herausgerechnet",
          z.startswith("NICHT konvergiert"), z)
    z = Z({"plastizitaet": {"konvergiert": False}})
    check("Plastizitaet nicht konvergiert", z.startswith("NICHT konvergiert")
          and "Plastizität" in z, z)
    z = Z({"contact_converged": False, "contact_iterations": 40})
    check("aeltere Ergebnisse ohne Laufzaehlung: die klebende Kennzahl gilt",
          z.startswith("NICHT konvergiert"), z)
    z = Z({"ausfall_log": ["Ausfall-Iteration nach 50 Schritten nicht konvergiert"]})
    check("Ausfall-Iteration nicht konvergiert", z.startswith("NICHT konvergiert")
          and "Ausfall" in z, z)
    z = Z(dict(gedeckelt, abbruch="kein statisches Gleichgewicht - Teil 1 hebt ab"))
    check("ein Abbruch ist nicht konvergiert und sagt es", z.startswith("NICHT konvergiert")
          and "abgebrochen" in z, z)
    z = Z(dict(gedeckelt, probelauf=True))
    check("Probelauf", z == "Probelauf", z)


def test_zustand_aus_info_abgekuerzt():
    """Gemeinsame Iteration von Fliessen und Kontakt (23.09.2026): abgekuerzte
    Laeufe stehen nicht unter den nicht konvergierten (solver._kontakt_info_
    sammeln) und zaehlen auch in "N von M" nicht mit - sonst stuende dort
    "1 von 19", wo 13 der 19 Laeufe mit Absicht nach einem Schritt endeten.
    Der letzte Lauf muss trotzdem konvergiert sein."""
    Z = rl.zustand_aus_info
    gemeinsam = {"contact_laeufe": 19, "contact_laeufe_abgekuerzt": 13,
                 "contact_laeufe_nicht_konvergiert": 0,
                 "contact_letzter_lauf_konvergiert": True, "contact_converged": True,
                 "plastizitaet": {"konvergiert": True}}
    z = Z(gemeinsam)
    check("abgekuerzte Laeufe allein: konvergiert", z == "konvergiert", z)
    z = Z(dict(gemeinsam, contact_laeufe_nicht_konvergiert=1,
               contact_letzter_lauf_konvergiert=False, contact_converged=False))
    check("der letzte Lauf gedeckelt: NICHT konvergiert, gezaehlt unter den vollen Laeufen",
          z.startswith("NICHT konvergiert") and "1 von 6" in z and "letzte" in z, z)


def test_zustand_aus_info_verworfen():
    """Gemeinsame Iteration (24.09.2026): gibt sie eine Laststufe auf, wird
    die Stufe vom Startwert an verschachtelt wiederholt, und die Laeufe des
    Versuchs sind verworfen - ihr u und ihr Kontaktzustand gehen nicht ins
    Ergebnis ein. Ein gedeckelter Lauf darunter macht den Posten nicht
    "NICHT konvergiert" (solver._lauf_zaehlt_nicht), und die vollen unter
    ihnen zaehlen in "N von M" nicht mit (``contact_laeufe_verworfen``; die
    abgekuerzten stehen schon unter ``contact_laeufe_abgekuerzt``)."""
    Z = rl.zustand_aus_info
    # 20 Laeufe: 9 abgekuerzt und verworfen, 2 volle verworfen (einer davon
    # gedeckelt - er zaehlt nicht), 9 volle der Wiederholung und des Rests
    info = {"contact_laeufe": 20, "contact_laeufe_abgekuerzt": 9, "contact_laeufe_verworfen": 2,
            "contact_laeufe_nicht_konvergiert": 0,
            "contact_letzter_lauf_konvergiert": True, "contact_converged": True,
            "plastizitaet": {"konvergiert": True}}
    z = Z(info)
    check("verworfene Laeufe allein: konvergiert", z == "konvergiert", z)
    z = Z(dict(info, contact_laeufe_nicht_konvergiert=1, contact_converged=False))
    check("ein gedeckelter Lauf der Wiederholung: NICHT konvergiert, 1 von 9",
          z.startswith("NICHT konvergiert") and "1 von 9" in z, z)


def test_vorlauf_mit_deckel():
    """Gemessen statt behauptet: ein gedeckelter elastischer Vorlauf aendert
    das Ergebnis einer Rechnung mit Fliessen nicht. Block mit Reibung,
    Streckgrenze auf 60 % der elastischen Vergleichsspannung (wie
    test_plastizitaet), der Deckel 1 nur waehrend des Vorlaufs."""
    import numpy as np
    from statik3d import contact as _ct
    from statik3d import plastizitaet as pl
    from statik3d import solver
    from statik3d.examples_lib import block_friction_example

    def modell():
        m0 = block_friction_example()
        r0 = solver.solve_static(m0)
        q0 = max(pl.vergleichsspannung(np.asarray(v, float)) for i, v in r0.solid_res.items()
                 if m0.elements[i].mat == "S235")
        m = block_friction_example()
        m.materials["S235"].fy = 0.6 * q0
        # Den Vorlauf hat nur die verschachtelte Iteration (die Vorgabe); die
        # gemeinsame (waehlbar seit dem 23.09.2026) laesst ihn weg
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.05, laststufen=2,
                                         iterationen=40, toleranz=1e-4, kontakt="verschachtelt")
        return m

    m_frei, m_vor = modell(), modell()
    r = solver.solve_static(m_frei)
    check("mit Fliessen: ein Vorlauf, konvergiert, und zustand_aus_info sagt konvergiert",
          r.info.get("contact_vorlauf_laeufe") == 1
          and r.info.get("contact_vorlauf_nicht_konvergiert") == 0
          and rl.zustand_aus_info(r.info) == "konvergiert",
          f"{r.info.get('contact_vorlauf_laeufe')} / "
          f"{r.info.get('contact_vorlauf_nicht_konvergiert')}")

    alt_max, alt_pr = _ct.MAX_CYCLES, solver._plastizitaet_rechnen

    def plastisch_ohne_deckel(*a, **k):
        _ct.MAX_CYCLES = alt_max
        return alt_pr(*a, **k)

    _ct.MAX_CYCLES = 1
    solver._plastizitaet_rechnen = plastisch_ohne_deckel
    try:
        r1 = solver.solve_static(m_vor)
    finally:
        _ct.MAX_CYCLES = alt_max
        solver._plastizitaet_rechnen = alt_pr
    check("der Vorlauf ist wirklich gedeckelt",
          r1.info.get("contact_vorlauf_nicht_konvergiert") == 1,
          str(r1.info.get("contact_vorlauf_nicht_konvergiert")))
    check("die klebende Kennzahl contact_converged meldet das",
          r1.info.get("contact_converged") is False, str(r1.info.get("contact_converged")))
    du = float(np.abs(r1.u - r.u).max())
    check("das Ergebnis ist dasselbe wie ohne Deckel (max |du| = 0)", du == 0.0,
          f"max |du| = {du:.3e} m bei max |u| = {float(np.abs(r.u).max()):.3e} m")
    z = rl.zustand_aus_info(r1.info)
    check("darum zaehlt der Vorlauf nicht: konvergiert", z == "konvergiert", z)


def test_farm_text():
    """Der Stand der Rechnerfarm aus farm._State.status - nur die lebenden
    Worker zaehlen als aktiv (`alive`: seit unter 30 s gesehen)."""
    st = {"workers": {"pc1": {"alive": True, "jobs": 7}, "pc2": {"alive": True, "jobs": 5},
                      "pc3": {"alive": False, "jobs": 2}},
          "queued": 18, "stats": {"done": 14}}
    check("aktive Rechner, wartende und erledigte Auftraege",
          rl.farm_text(st) == "2 von 3 Rechnern aktiv, 18 Aufträge wartend, 14 erledigt",
          rl.farm_text(st))
    check("ohne Farm bleibt die Zeile leer statt falsch",
          rl.farm_text({}) == "0 von 0 Rechnern aktiv, 0 Aufträge wartend, 0 erledigt",
          rl.farm_text({}))
    check("None stuerzt nicht ab", isinstance(rl.farm_text(None), str))


def test_fenster():
    """Die Probe an der echten Tabelle (ohne Bildschirm): landet, was der
    Rechenkern meldet, in der Zeile des laufenden Postens und in der
    richtigen Spalte?"""
    try:
        from PySide6 import QtWidgets
    except Exception as ex:                                  # noqa: BLE001
        print(f"  (PySide6 nicht vorhanden: {ex} - uebersprungen)")
        return
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    f = rl.Rechenliste()
    S = rl.Rechenliste

    def zelle(i, j):
        eintrag = f.tabelle.item(i, j)
        return eintrag.text() if eintrag is not None else ""

    f.rechner_setzen("Prozesspool: lokal, 31 von 32 Kernen")
    check("die Kopfzeile nennt die Rechner",
          "31 von 32 Kernen" in f.kopf_rechner.text(), f.kopf_rechner.text())
    f.posten_setzen([("LF1", "Lastfall"), ("LF3", "Lastfall"), ("GZT1", "Kombination")])
    check("drei Zeilen", f.tabelle.rowCount() == 3)
    check("der erste Posten laeuft sofort", zelle(0, S.S_ZUSTAND) == rl.LAEUFT)
    check("die uebrigen stehen auf offen", zelle(2, S.S_ZUSTAND) == rl.OFFEN)

    f.melden("Kontakt-Iteration 12: 13902 aktiv, Δu 3.2e-05, Matrix bleibt")
    check("Schritte in der Zeile des Laufenden", zelle(0, S.S_SCHRITTE) == "Kontakt 12",
          zelle(0, S.S_SCHRITTE))
    check("Konvergenz in ihrer eigenen Spalte", zelle(0, S.S_KONVERGENZ) == "Δu 3.2e-05",
          zelle(0, S.S_KONVERGENZ))
    check("und die Meldung im Klartext daneben",
          zelle(0, S.S_MELDUNG).startswith("Kontakt-Iteration 12"))

    f.melden("Lastfall LF1 (1/3)")
    check("die Marke schliesst ihre Zeile ab", zelle(0, S.S_ZUSTAND) == rl.FERTIG)
    check("und schreibt eine Zeit hinein", zelle(0, S.S_ZEIT) != "")
    check("der naechste Posten laeuft", zelle(1, S.S_ZUSTAND) == rl.LAEUFT)

    f.melden("Plastizität: Laststufe 2/3, Schritt 5: 184 Elemente fließen, Änderung 8.13e-07")
    check("die zweite Zeile fuellt sich", zelle(1, S.S_SCHRITTE) == "Plast. 5 (Stufe 2/3)",
          zelle(1, S.S_SCHRITTE))
    check("die erste bleibt stehen, wie sie war", zelle(0, S.S_SCHRITTE) == "Kontakt 12")

    f.beenden("abgebrochen")
    check("der Abbruch trifft die laufende Zeile", zelle(1, S.S_ZUSTAND) == "abgebrochen")
    check("der Abbruchknopf ist danach aus", not f.btn_abbrechen.isEnabled())
    f.close()


def test_dauer_text():
    check("unter einer Stunde m:ss", rl.dauer_text(343.4) == "5:43", rl.dauer_text(343.4))
    check("ab einer Stunde h:mm:ss", rl.dauer_text(4169.6) == "1:09:30", rl.dauer_text(4169.6))
    check("null bleibt 0:00", rl.dauer_text(0.0) == "0:00")
    check("negatives wird nicht negativ", rl.dauer_text(-5.0) == "0:00")


def main():
    for t in (test_posten_aus_modell, test_marke_lesen, test_fortschritt_aus_meldung,
              test_schritte_text, test_zustand_aus_meldung,
              test_deckelmeldung_ist_nicht_konvergiert, test_zustand_aus_info,
              test_zustand_aus_info_abgekuerzt, test_zustand_aus_info_verworfen,
              test_deckel_im_fortschrittsstrom, test_vorlauf_mit_deckel,
              test_farm_text, test_dauer_text, test_fenster):
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
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
