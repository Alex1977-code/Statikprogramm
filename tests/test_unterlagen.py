"""Unterlagen (16.09.2026, "analog InfoCAD"): Dateien, uebernommene Ansichten
und Skizzen zum Modell - Modellklasse, Speichern und Laden, Kopie und die
Bloecke im Bericht (Skizze als Abbildung, Bild als Bild, PDF als Anlage,
fehlende Unterlage als Hinweis).

Aufruf:  python -m tests.test_unterlagen
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Berichtseintrag, Model, Unterlage   # noqa: E402
from statik3d import skizze as sk                               # noqa: E402
from statik3d.report.html import Report                          # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:66s} {detail}")
    return ok


def _modell() -> Model:
    m = Model("Unterlagenprobe")
    s = sk.neu(200, 100, massstab=10.0, einheit="cm")
    s["elemente"] = [{"art": "linie", "p1": [10, 20], "p2": [110, 20]},
                     {"art": "bemassung", "p1": [10, 20], "p2": [110, 20], "abstand": 8, "text": ""},
                     {"art": "text", "p": [10, 60], "text": "Blech t = 20", "groesse": 4}]
    m.unterlagen["Blech"] = Unterlage("Blech", art="skizze", typ="skizze", skizze=s, beschriftung="Blech mit Bohrung")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    m.unterlagen["Ansicht 1"] = Unterlage("Ansicht 1", art="bild", datei="Ansicht 1.png", typ="png",
                                          daten=base64.b64encode(png).decode("ascii"))
    m.unterlagen["Plan.pdf"] = Unterlage("Plan.pdf", art="datei", datei="Plan.pdf", typ="pdf",
                                         daten=base64.b64encode(b"%PDF-1.4 probe").decode("ascii"))
    m.unterlagen["Werte.csv"] = Unterlage("Werte.csv", art="datei", datei="Werte.csv", typ="csv",
                                          daten=base64.b64encode("a;b\n1;2\n".encode()).decode("ascii"))
    for name in ("Blech", "Ansicht 1", "Plan.pdf", "Werte.csv"):
        u = m.unterlagen[name]
        m.bericht.append(Berichtseintrag(name=name, art="unterlage", datei=name, typ=u.typ,
                                         beschriftung=u.beschriftung or u.bezug()))
    m.bericht.append(Berichtseintrag(name="weg", art="unterlage", datei="gibt es nicht"))
    return m


def test_modell():
    m = _modell()
    check("bezug: Skizze zaehlt die Elemente, Bild nennt Typ und Groesse, Datei den Namen",
          m.unterlagen["Blech"].bezug().startswith("Skizze: 1 Linien, 1 Maße, 1 Texte")
          and m.unterlagen["Ansicht 1"].bezug().startswith("Bild (png")
          and m.unterlagen["Plan.pdf"].bezug().startswith("Datei Plan.pdf (PDF"),
          " | ".join(u.bezug() for u in m.unterlagen.values()))
    check("Berichtseintrag der Art unterlage nennt die Unterlage", m.bericht[0].bezug() == "Unterlage Blech")
    d = m.to_dict()
    m2 = Model.from_dict(d)
    check("to_dict/from_dict: alle Unterlagen mit Skizze, Daten und Beschriftung",
          set(m2.unterlagen) == set(m.unterlagen) and m2.unterlagen["Blech"].skizze["elemente"][1]["art"] == "bemassung"
          and m2.unterlagen["Plan.pdf"].daten == m.unterlagen["Plan.pdf"].daten
          and m2.unterlagen["Blech"].beschriftung == "Blech mit Bohrung"
          and m2.bericht[0].art == "unterlage" and m2.bericht[0].datei == "Blech")
    m3 = m.copy()
    m3.unterlagen["Blech"].skizze["elemente"].append({"art": "kreis", "mitte": [50, 50], "r": 5})
    check("copy: die Skizze der Kopie ist eine eigene", len(m.unterlagen["Blech"].skizze["elemente"]) == 3)
    check("Modell ohne Unterlagen laedt aus altem dict", Model.from_dict({k: v for k, v in d.items() if k != "unterlagen"}).unterlagen == {})


def test_bericht():
    m = _modell()
    r = Report(m)
    bl = r._eintrag_bloecke(m.bericht[0], 1)
    fig = [b for b in bl if b[0] == "figure"]
    check("Skizze: eine Abbildung (SVG) mit der Masszahl 100 (100 mm x 10 = 1 m = 100 cm) und der Unterschrift",
          len(fig) == 1 and fig[0][1].startswith("<svg") and ">100</text>" in fig[0][1]
          and "Blech t = 20" in fig[0][1] and fig[0][2] == "Blech mit Bohrung",
          str([b[0] for b in bl]))
    check("… mit Ueberschrift aus dem Namen", any(b[0] == "h" and "Blech" in str(b) for b in bl), str(bl[0])[:80])
    bl = r._eintrag_bloecke(m.bericht[1], 2)
    bild = [b for b in bl if b[0] == "bild"]
    check("Bild: ein Bildblock mit den PNG-Daten", len(bild) == 1 and bild[0][1] == m.unterlagen["Ansicht 1"].daten
          and bild[0][4] == "png", str([b[0] for b in bl]))
    bl = r._eintrag_bloecke(m.bericht[2], 3)
    check("PDF: wird als Anlage genannt, nicht eingebettet", any(b[0] == "note" and "PDF" in b[1] for b in bl), str(bl)[:160])
    bl = r._eintrag_bloecke(m.bericht[3], 4)
    check("CSV: als Tabelle", any(b[0] == "table" and b[1] == [["a", "b"], ["1", "2"]] for b in bl), str(bl)[:160])
    bl = r._eintrag_bloecke(m.bericht[4], 5)
    check("fehlende Unterlage: ein Hinweis statt eines Absturzes",
          any(b[0] == "note" and "gibt es nicht mehr" in b[1] for b in bl), str(bl)[:120])
    # Skizze mit Hintergrundbild: das Bild steht im SVG
    m.unterlagen["Blech"].daten = m.unterlagen["Ansicht 1"].daten
    m.unterlagen["Blech"].skizze["bild"] = {"x": 0, "y": 0, "breite": 200, "hoehe": 100}
    bl = r._eintrag_bloecke(m.bericht[0], 1)
    fig = [b for b in bl if b[0] == "figure"]
    check("Skizze mit Hintergrundbild: das Bild liegt im SVG", fig and "<image" in fig[0][1] and "base64," in fig[0][1])


def main():
    for t in (test_modell, test_bericht):
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
