"""
Verifikation der Tabellen: Filter, Zellformeln, Kennwerte und Export.

Geprueft wird der rechnende Teil von statik3d/gui/tabellen.py ohne
Oberflaeche - genau dafuer stehen diese Funktionen dort einzeln.

Aufruf:  python -m tests.test_tabellen
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.gui.tabellen import (      # noqa: E402
    Spalte, als_csv, als_xlsx, formel, kennwerte, passt, zahlen_wandeln)

RESULTS = []


def ja(name, bedingung, info=""):
    ok = bool(bedingung)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {info}")
    return ok


def gleich(name, ist, soll, tol=1e-12):
    ok = abs(float(ist) - float(soll)) <= tol
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} ist={ist} soll={soll}")
    return ok


# --------------------------------------------------------------------------
def test_filter():
    for wert, ausdruck, soll in (
            (1.5, "> 0.9", True), (0.5, "> 0.9", False),
            (0.9, ">= 0,9", True), (0.9, "> 0,9", False),
            (3.0, "< 10", True), (30.0, "< 10", False),
            (2.0, "<= 2", True), (2.0, "!= 2", False), (3.0, "!= 2", True),
            (3, "1..5", True), (7, "1..5", False),
            (1, "1..5", True), (5, "1..5", True),          # Grenzen gehoeren dazu
            (3, "5..1", True),                             # verdrehte Grenzen
            ("HEB 200", "heb", True), ("HEA 200", "heb", False),
            ("HEB 200", "!heb", False), ("HEA 200", "!heb", True),
            ("S355", "= s355", True), ("S235", "= s355", False),
            ("was auch immer", "", True),                  # leerer Filter laesst alles durch
            ("-", "> 0.9", False),                         # Text im Zahlenvergleich
            (-2.5, "< -1", True),
    ):
        ja(f"Filter {wert!r} gegen {ausdruck!r}", passt(wert, ausdruck) is soll,
           f"-> {passt(wert, ausdruck)}")
    ja("Doppelte Verneinung ist wieder ja", passt("HEB", "!!heb") is True)


def test_formel():
    gleich("Zelle: 3,25 wird gelesen", formel("3,25"), 3.25)
    gleich("Zelle: = 2*3,5", formel("= 2*3,5"), 7.0)
    gleich("Zelle: Klammern und Potenz", formel("= (1+2)**2"), 9.0)
    gleich("Zelle: Vorzeichen", formel("= -4/2"), -2.0)
    gleich("Zelle: pi", formel("= pi"), 3.141592653589793, 1e-12)
    gleich("Zelle: leer ist null", formel(""), 0.0)
    for schlecht, warum in (("= __import__('os')", "Aufrufe"),
                            ("= open('x')", "Funktionen"),
                            ("= a+1", "Namen"),
                            ("= 1/0", "Teilung durch null"),
                            ("= 1+", "unvollstaendig"),
                            ("Unfug", "keine Zahl")):
        try:
            formel(schlecht)
            ja(f"Zelle weist {warum} ab", False, schlecht)
        except ValueError as ex:
            ja(f"Zelle weist {warum} ab", True, str(ex)[:40])


def test_zahlen_und_kennwerte():
    sp = [Spalte("Element", "", "ganz"), Spalte("N", "kN", "zahl", 2),
          Spalte("Status")]
    z = zahlen_wandeln([["1", "3,50", "ok"], ["2", "-1,25", "ok"],
                        ["3", "-", "nicht geführt"]], sp)
    ja("Text in Zahlenspalten wird Zahl", z[0] == [1, 3.5, "ok"], str(z[0]))
    ja("Was keine Zahl ist, bleibt stehen", z[2][1] == "-", str(z[2]))
    hoch, tief = kennwerte(z, sp)
    gleich("Max ueber die Zahlenspalte", hoch[1], 3.5)
    gleich("Min ueber die Zahlenspalte", tief[1], -1.25)
    ja("Textspalte hat keinen Kennwert", hoch[2] == "" and tief[2] == "")
    ja("Kennwerte sind beschriftet", hoch[0] == "Max" and tief[0] == "Min")
    ja("Leere Tabelle hat keine Kennwerte", kennwerte([], sp) == ([], []))


def test_export():
    kopf = ["Element", "N [kN]"]
    zeilen = [[1, 3.5], [2, -1.25]]
    text = als_csv(kopf, zeilen)
    ja("CSV: Semikolon als Trenner", text.splitlines()[0] == "Element;N [kN]", text.splitlines()[0])
    ja("CSV: deutsches Dezimalkomma", text.splitlines()[1] == "1;3,5", text.splitlines()[1])
    ja("CSV: Zeilenzahl stimmt", len(text.strip().splitlines()) == 3)

    with tempfile.TemporaryDirectory() as d:
        pfad = os.path.join(d, "tabelle.xlsx")
        als_xlsx(pfad, "Stabkraefte", kopf, zeilen)
        ja("Excel: Datei geschrieben", os.path.getsize(pfad) > 500, f"{os.path.getsize(pfad)} B")
        from statik3d.importers.xlsx_reader import read_xlsx
        blaetter = read_xlsx(pfad)
        name = list(blaetter)[0]
        ja("Excel: Blattname aus dem Titel", name == "Stabkraefte", name)
        w = blaetter[name]
        ja("Excel: Kopfzeile steht drin", list(w[0])[:2] == kopf, str(w[0]))
        ja("Excel: Zahlen bleiben Zahlen", abs(float(w[1][1]) - 3.5) < 1e-12, str(w[1]))


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Tabellen (Filter, Zellformeln, Kennwerte, Export)")
    print("=" * 92)
    for t in (test_filter, test_formel, test_zahlen_und_kennwerte, test_export):
        print(f"\n--- {t.__name__} ---")
        t()
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 92)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
