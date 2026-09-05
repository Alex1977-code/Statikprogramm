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
    check("Standard-Lastfälle angelegt", namen == lh.STANDARD, str(namen))
    check("Einwirkungsart = Schlüssel, Beschreibung = Einwirkung",
          all(m.load_cases[n].category == n and m.load_cases[n].description == EINWIRKUNGEN[n] for n in namen))
    check("fortlaufende Nummern ab 1", [m.load_cases[n].nummer for n in namen] == list(range(1, len(namen) + 1)))
    check("Eigengewicht mit g", m.load_cases["G"].gravity == [0.0, 0.0, -9.81]
          and m.load_cases["W_S"].gravity == [0.0, 0.0, 0.0])
    check("aktiver Lastfall bleibt gesetzt (vorhandener LF1 oder G)", m.active_case in ("G", "LF1"), str(m.active_case))
    weitere = lh.lastfaelle_anlegen(m, ["G", "EIS", "XYZ"], start_nr=20, log=log)
    check("vorhandener Name bekommt eine Zahl, unbekannte Art übersprungen, Nummer ab 20",
          weitere == ["G 2", "EIS 2"] and m.load_cases["G 2"].nummer == 20 and m.load_cases["EIS 2"].nummer == 21
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
    check("Modellwerte: Wasserdruck-Generierer und Lastfälle genannt",
          "Wasserdruck " in html and "Lastfall G (Nr. 1)" in html)
    check("normativer Rahmen nennt DIN 19704-1 und ZTV-ING", "DIN 19704-1" in html and "ZTV-ING" in html)
    md = doc.to_markdown()
    check("Markdown-Fassung", md.startswith("# Lastenheft") and "Eisdruck" in md)
    pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lastenheft_test.html")
    try:
        lh.lastenheft_schreiben(m, pfad)
        check("Datei geschrieben", os.path.getsize(pfad) > 50000)
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
