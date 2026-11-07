"""Netzhinweis: „Netzeinstellung wirksam erst nach Vernetzen“ (16.10.2026).

Anlass: Der Anwender uebernahm in der Maske Netzeinstellungen „Mittel“ (tet10);
gerechnet wurde danach, ohne einen Hinweis, mit dem alten tet4-Netz des Entwurfs.
Gefordert:

* das Modell merkt sich beim Vernetzen die Einstellung, mit der das Netz entstand;
* weicht die aktuelle Einstellung davon ab, kommt ein Hinweis beim Uebernehmen
  und beim Rechenstart (Protokoll und Statuszeile); gesperrt wird nichts;
* Bericht und Ergebnisdatei nennen die Elementtypen mit Anzahl und die
  Netzeinstellung beim Vernetzen.

Aufruf:  python -m tests.test_netzhinweis
"""
import contextlib
import io
import os
import sys
import tempfile
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import elementstufe as es                            # noqa: E402
from statik3d import mesher, netzhinweis as nh                     # noqa: E402
from statik3d.model import NEUE_FELDER, Model                      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:84s} {detail}")
    return ok


def vernetztes_modell(stufe="entwurf"):
    """Kleiner Koerper, mit der Stufe ``stufe`` ueber den Vernetzer erzeugt."""
    from tests.test_diagnose import _gestuft
    m, k = _gestuft(1.0, n=2)
    m.elemente_loeschen(list(range(len(m.elements))))
    k.elemente = []
    m.netz = es.setzen(m.netz, stufe)
    with contextlib.redirect_stdout(io.StringIO()):
        mesher.modell_vernetzen(m, [], workers=1)
    return m


def test_merken_beim_vernetzen():
    print("\n--- Das Netz merkt sich seine Einstellung ---")
    m = vernetztes_modell("entwurf")
    typen = {e.typ for e in m.elements}
    check("das Modell hat nach dem Vernetzen die Einstellung vermerkt",
          bool(m.netz.vernetzt_mit) and m.netz.vernetzt_mit.get("elemente") == "Entwurf",
          str(m.netz.vernetzt_mit)[:100])
    check("der Vermerk enthält die Beschreibung der Einstellung",
          "Elemente Entwurf" in str(m.netz.vernetzt_mit.get("beschreibung")), str(typen))
    check("gleiche Einstellung: kein Hinweis", nh.hinweis(m) == "" and nh.abweichungen(m) == [])
    # Einstellung aendern, nicht vernetzen
    m.netz = es.setzen(m.netz, "mittel")
    a = nh.abweichungen(m)
    check("Mittel eingestellt, Netz vom Entwurf: die Abweichung nennt Elemente Mittel statt Entwurf",
          any("Mittel" in z and "Entwurf" in z for z in a), str(a))
    t = nh.hinweis(m, "rechnen")
    check("der Hinweis sagt: wirksam erst nach dem Vernetzen",
          "erst nach dem Vernetzen" in t and "Mittel" in t and "Entwurf" in t, t[:160])
    check("er sperrt nichts: nur Text, der Rechenstart bleibt frei", isinstance(t, str) and t != "")
    # zurueckgestellt: kein Hinweis mehr
    m.netz = es.setzen(m.netz, "entwurf")
    check("zurück auf die Einstellung des Netzes: kein Hinweis", nh.hinweis(m) == "")
    # andere Dichte
    m.netz = replace(m.netz, dichte="fein")
    check("andere Netzdichte: Hinweis mit 'Netzdichte'",
          any("Netzdichte" in z for z in nh.abweichungen(m)), str(nh.abweichungen(m)))


def test_speichern_laden():
    print("\n--- Der Vermerk steht in der Datei, ohne die Ergebnisdatei zu entwerten ---")
    m = vernetztes_modell("entwurf")
    check("neues Feld nur über NEUE_FELDER: netz.vernetzt_mit mit Vorgabe {}",
          NEUE_FELDER["netz"].get("vernetzt_mit") == {})
    with tempfile.TemporaryDirectory() as d:
        pf = os.path.join(d, "m.json")
        m.save(pf)
        m2 = Model.load(pf)
        check("nach Speichern und Laden ist der Vermerk da", m2.netz.vernetzt_mit == m.netz.vernetzt_mit)
        # ein Modell ohne Vermerk bleibt in der Datei ohne den Schluessel
        m3 = Model("leer")
        d3 = m3.to_dict()
        check("ohne Vermerk steht der Schluessel nicht in der Datei", "vernetzt_mit" not in d3.get("netz", {}),
              str(d3.get("netz", {}).keys())[:80])
    from statik3d import ergebnisse as erg
    k1 = erg.kennung(m)
    m.netz = replace(m.netz, vernetzt_mit={})
    k2 = erg.kennung(m)
    check("der Vermerk zählt nicht in der Kennung der Ergebnisdatei", k1 == k2)


def test_ohne_vermerk():
    print("\n--- Netz ohne Vermerk (Datei von davor, Import) ---")
    m = vernetztes_modell("entwurf")
    m.netz = replace(m.netz, vernetzt_mit={})
    check("ohne Vermerk kein Hinweis (es ist nichts zu vergleichen)", nh.hinweis(m) == "")
    z = nh.ausweis_zeile(m)
    check("der Ausweis sagt dann ehrlich 'nicht bekannt'", "nicht bekannt" in z, z[:140])
    # Beim Uebernehmen einer neuen Einstellung wird die alte als die des Netzes angenommen
    alt = m.netz
    neu = es.setzen(alt, "mittel")
    nh.vor_aenderung(m, neu)
    check("vor dem Übernehmen wird die bisherige Einstellung als die des vorhandenen Netzes vermerkt",
          m.netz.vernetzt_mit.get("elemente") == "Entwurf", str(m.netz.vernetzt_mit)[:90])
    m.netz = replace(neu, vernetzt_mit=m.netz.vernetzt_mit)
    check("danach meldet die neue Einstellung die Abweichung", nh.hinweis(m, "uebernehmen") != "")
    # ohne Elemente gibt es nichts zu vergleichen
    leer = Model("leer")
    leer.netz = es.setzen(leer.netz, "mittel")
    nh.vor_aenderung(leer, leer.netz)
    check("ein Modell ohne Netz bekommt keinen Hinweis", nh.hinweis(leer) == "" and not leer.netz.vernetzt_mit)


def test_ausweis():
    print("\n--- Bericht und Ergebnisdatei nennen Elementtypen und Netzeinstellung ---")
    m = vernetztes_modell("entwurf")
    a = nh.ausweis(m)
    n_ist = len(m.elements)
    check("Ausweis: Elementtypen mit Anzahl, Summe stimmt",
          a["gesamt"] == n_ist and sum(a["elementtypen"].values()) == n_ist, str(a["elementtypen"]))
    check("Ausweis: die Netzeinstellung beim Vernetzen", "Elemente Entwurf" in a["netzeinstellung"],
          a["netzeinstellung"][:80])
    z = nh.ausweis_zeile(m)
    check("Zeile für das Protokoll: Typ, Anzahl und Netzeinstellung",
          "hex8" in z and "Netzeinstellung beim Vernetzen" in z, z[:160])
    # Ergebnisdatei: die Analyse traegt den Ausweis in info
    from statik3d import solver
    m.case()
    an = solver.solve_all(m, workers=1)
    check("Analyse: info['netz'] mit Typen und Netzeinstellung",
          isinstance(an.info.get("netz"), dict) and an.info["netz"]["gesamt"] == n_ist
          and "Elemente Entwurf" in an.info["netz"]["netzeinstellung"], str(an.info.get("netz"))[:100])
    from statik3d import ergebnisse as erg
    with tempfile.TemporaryDirectory() as d:
        pf = os.path.join(d, "m.ergebnisse")
        erg.schreiben(pf, m, an)
        an2 = erg.lesen(pf, m)
    check("Ergebnisdatei: der Ausweis steht nach dem Lesen wieder da",
          isinstance(an2.info.get("netz"), dict) and an2.info["netz"]["gesamt"] == n_ist)
    # Bericht
    from statik3d.report.html import Report
    try:
        html = Report(m, an2).html()
    except Exception as ex:                  # noqa: BLE001
        html = f"{type(ex).__name__}: {ex}"
    check("Bericht: nennt die Netzeinstellung beim Vernetzen", "Netzeinstellung beim Vernetzen" in html,
          html[:100] if "Netzeinstellung" not in html else "")
    check("Bericht: nennt die Elementtypen mit Anzahl", "hex8" in html and str(n_ist) in html.replace(".", ""),
          "")


def main():
    test_merken_beim_vernetzen()
    test_speichern_laden()
    test_ohne_vermerk()
    test_ausweis()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
