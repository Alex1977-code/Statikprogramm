"""
Lastenheft nach DIN 19704 / ZTV-ING und automatische Lastfaelle:
Vollstaendigkeit der Einwirkungen, Lastfaelle mit Art und Nummer, Dokument
mit Kapiteln, Skizzen (wohlgeformtes SVG) und gekennzeichneten Vorgaben.
Aufruf:  python -m tests.test_lastenheft
"""
import os
import sys
import xml.dom.minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, ACTION_CATEGORIES  # noqa: E402
from statik3d.examples_lib import build_example  # noqa: E402
from statik3d.bridges.din19704 import EINWIRKUNGEN, KLASSEN, Regelwerk  # noqa: E402
from statik3d.bridges import lastenheft as lh  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def test_texte():
    keys = {e.key for e in lh.EINWIRKUNGSTEXTE}
    check("jede Einwirkung der DIN 19704 hat einen Text", keys == set(EINWIRKUNGEN), str(keys ^ set(EINWIRKUNGEN)))
    check("jede Einwirkung ist eine Einwirkungskategorie", keys <= set(ACTION_CATEGORIES))
    check("jede Einwirkung nennt Norm, Erläuterung und Ansatz",
          all(e.norm and e.erlaeuterung and e.ansatz for e in lh.EINWIRKUNGSTEXTE))
    check("Lastfallklassen aus KLASSEN abgeleitet",
          lh.TEXTE["KLEMM"].klassen == ["LF3"] and lh.TEXTE["G"].klassen == ["LF1", "LF2", "LF3"])
    check("Standardauswahl liegt in den Einwirkungen", set(lh.STANDARD) <= keys)
    for key, fn in lh.SKIZZEN.items():
        if fn is None:
            continue
        svg = fn("Test")
        try:
            xml.dom.minidom.parseString(svg)
            ok = svg.startswith("<svg") and svg.endswith("</svg>")
        except Exception as ex:          # noqa: BLE001
            ok = False
            svg = str(ex)
        check(f"Skizze {key} ist wohlgeformtes SVG", ok, svg[:60] if not ok else "")
    svg = lh.skizze_wasserdruck(1.0, 0.4)
    xml.dom.minidom.parseString(svg)
    check("Wasserdruck-Skizze mit Ober- und Unterwasser", "OW" in svg and "UW" in svg and "ρ·g·h" in svg)


def test_lastfaelle():
    m = Model("L")
    log = []
    namen = lh.lastfaelle_anlegen(m, log=log)
    # Seit R2-C1 (06.10.2026) heisst jeder Lastfall LF<Nr.> und traegt den
    # Schluessel der Einwirkung als Bezeichnung (bis dahin hiess er wie der Schluessel)
    schluessel = {n: m.load_cases[n].bezeichnung for n in namen}
    check("Standard-Lastfälle angelegt: LF2…LF10 mit dem Schlüssel als Bezeichnung",
          namen == [f"LF{i}" for i in range(2, len(lh.STANDARD) + 2)]
          and list(schluessel.values()) == lh.STANDARD, str(namen))
    check("Einwirkungsart = Schlüssel, Beschreibung = Einwirkung",
          all(m.load_cases[n].category == schluessel[n] and m.load_cases[n].description == EINWIRKUNGEN[schluessel[n]]
              for n in namen))
    # Seit R2-A1 (04.10.2026) gehoert Nr. 1 dem Vorgabelastfall LF1 (Name und
    # Feld); bis dahin bekam G noch einmal die Nr. 1 (Model.naechste_nummer)
    check("fortlaufende Nummern ab der nächsten freien (2, LF1 hat Nr. 1)",
          m.load_cases["LF1"].nummer == 1
          and [m.load_cases[n].nummer for n in namen] == list(range(2, len(namen) + 2)),
          str([m.load_cases[n].nummer for n in namen]))
    check("Eigengewicht mit g", m.load_cases["LF2"].gravity == [0.0, 0.0, -9.81]
          and m.load_cases["LF4"].gravity == [0.0, 0.0, 0.0])
    check("aktiver Lastfall bleibt gesetzt (vorhandener LF1)", m.active_case == "LF1", str(m.active_case))
    weitere = lh.lastfaelle_anlegen(m, ["G", "EIS", "XYZ"], start_nr=20, log=log)
    check("zweiter Aufruf legt neue Lastfälle an (nichts überschrieben, keine Zahl angehängt), "
          "unbekannte Art übersprungen, Nummer ab 20",
          weitere == ["LF20", "LF21"] and m.load_cases["LF20"].nummer == 20 and m.load_cases["LF21"].nummer == 21
          and [m.load_cases[n].bezeichnung for n in weitere] == ["G", "EIS"]
          and any("XYZ" in z for z in log), str((weitere, log[-2:])))
    rw = Regelwerk()
    k = rw.kombinationen(m)
    check("die Lastfälle lassen sich zu DIN-Kombinationen bilden", len(k) >= 3, str(len(k)))


def test_dokument():
    m = build_example("gate")
    lh.lastfaelle_anlegen(m)
    doc = lh.Lastenheft(m)
    html = doc.html()
    check("Titel Lastenheft, kein „Statischer Bericht“", "<h1 class=\"doctitle\">Lastenheft</h1>" in html
          and "Statischer Bericht" not in html)
    check("fünf Kapitel: Rahmen, Übersicht, Einwirkungen, Kombinationen, Prüfliste",
          html.count('class="chapter"') == 5)
    check("jede Einwirkung ein Abschnitt", all(f"{e.key} - {e.titel}" in html for e in lh.EINWIRKUNGSTEXTE))
    check("Skizzen enthalten", html.count("<svg") >= len(EINWIRKUNGEN) - 1, str(html.count("<svg")))
    check("Vorgaben sind gekennzeichnet", "zu bestätigen" in html and "* = Voreinstellung" in html)
    # G bekommt die naechste freie Nummer: LF1 bis LF3 des Beispiels haben die
    # Nr. 1 bis 3 (R2-A1, R2-C1) - der Lastfall heisst LF4
    check("Modellwerte: Wasserdruck-Generierer und Lastfälle genannt",
          "Wasserdruck " in html and "Lastfall LF4 (Nr. 4)" in html)
    check("normativer Rahmen nennt DIN 19704-1 und ZTV-ING", "DIN 19704-1" in html and "ZTV-ING" in html)
    md = doc.to_markdown()
    check("Markdown-Fassung", md.startswith("# Lastenheft") and "Eisdruck" in md)
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lastenheft_test.html")
    try:
        lh.lastenheft_schreiben(m, pfad)
        check("Datei geschrieben", os.path.getsize(pfad) > 50000)
        schritte = []
        lh.lastenheft_schreiben(m, pfad, fortschritt=lambda a, t: schritte.append((a, t)))
        anteile = [a for a, _t in schritte]
        texte = " | ".join(t for _a, t in schritte)
        check("Fortschritt: fünf Kapitel, Ausgabe, Schreiben - monoton 0 … 1",
              len(schritte) >= 5 + 3 and anteile[0] == 0.0 and anteile[-1] == 1.0
              and all(b >= a for a, b in zip(anteile, anteile[1:]))
              and "Kapitel 1 von 5: Rahmen" in texte and "Prüfliste" in texte
              and "geschrieben" in texte, f"{len(schritte)}: {texte[:120]}")
    finally:
        if os.path.exists(pfad):
            os.remove(pfad)
    for teil in html.split("<svg")[1:]:
        svg = "<svg" + teil.split("</svg>")[0] + "</svg>"
        xml.dom.minidom.parseString(svg)
    check("alle Skizzen des Dokuments wohlgeformt", True)


def main():
    for f in (test_texte, test_lastfaelle, test_dokument):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
