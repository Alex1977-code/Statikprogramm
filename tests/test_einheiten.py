"""
Einheiten und Genauigkeiten: Faktoren aus SI, abgeleitete Einheiten (Moment,
Strecken-, Flaechenlast), Tabellenspalten in Grundeinheiten, Texte, Persistenz.
Aufruf:  python -m tests.test_einheiten
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model  # noqa: E402
from statik3d.einheiten import Einheiten  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def close(name, got, want, tol=1e-12):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6g} ana={want:.6g}")


def test_faktoren():
    e = Einheiten()
    close("kN aus N: 12500 N = 12.5 kN", e.aus_si(12500.0, "kraft"), 12.5)
    close("m bleibt m", e.aus_si(2.5, "laenge"), 2.5)
    close("Verformung mm aus m", e.aus_si(0.0032, "verformung"), 3.2)
    close("Spannung N/mm² aus Pa", e.aus_si(235e6, "spannung"), 235.0)
    close("Moment kNm aus Nm", e.aus_si(45000.0, "moment"), 45.0)
    close("Streckenlast kN/m aus N/m", e.aus_si(5000.0, "strecke"), 5.0)
    close("Flächenlast kN/m² aus Pa", e.aus_si(2500.0, "flaechenlast"), 2.5)
    check("abgeleitete Einheiten", e.einheit("moment") == "kNm" and e.einheit("strecke") == "kN/m"
          and e.einheit("flaechenlast") == "kN/m²")
    e2 = Einheiten(kraft="N", laenge="mm", verformung="cm", spannung="kN/cm²", nk_kraft=0, nk_last=0)
    close("N bleibt N", e2.aus_si(12500.0, "kraft"), 12500.0)
    close("mm aus m", e2.aus_si(2.5, "laenge"), 2500.0)
    close("Moment Nmm aus Nm", e2.aus_si(45000.0, "moment"), 45e6)
    close("Streckenlast N/mm aus N/m", e2.aus_si(5000.0, "strecke"), 5.0)
    close("Flächenlast N/mm² aus Pa", e2.aus_si(2.5e6, "flaechenlast"), 2.5)
    close("kN/cm² aus Pa (235 N/mm² = 23.5 kN/cm²)", e2.aus_si(235e6, "spannung"), 23.5)
    close("Verformung cm aus m", e2.aus_si(0.032, "verformung"), 3.2)
    check("Einheitentexte", e2.einheit("moment") == "Nmm" and e2.einheit("flaechenlast") == "N/mm²")
    e3 = Einheiten(kraft="MN", laenge="cm")
    close("MN aus N", e3.aus_si(2.5e6, "kraft"), 2.5)
    close("MN/cm² aus Pa: 1e6 Pa = 1e-4 MN/cm²", e3.aus_si(1e6, "flaechenlast"), 1e-4)


def test_texte_und_tabellen():
    e = Einheiten()
    check("Text mit Einheit und Nachkomma", e.text(12500.0, "kraft") == "12.50 kN" and e.text(0.0032, "verformung") == "3.20 mm")
    check("Kurzzahl ohne Nachkommanullen", e.zahl(12500.0, "kraft") == "12.5" and e.zahl(5000.0, "strecke") == "5" and e.zahl(0.0, "kraft") == "0")
    f, txt, nk = e.anzeige("kN", 2)
    check("Tabellenspalte kN unter Vorgabe: Faktor 1, kN, 2 Nachkommastellen", f == 1.0 and txt == "kN" and nk == 2)
    e2 = Einheiten(kraft="N", laenge="mm", nk_kraft=0, nk_laenge=1)
    f, txt, nk = e2.anzeige("kN", 2)
    check("Spalte kN bei Anzeige N: Faktor 1000, N, 0 Nachkommastellen", abs(f - 1000.0) < 1e-9 and txt == "N" and nk == 0, str((f, txt, nk)))
    f, txt, nk = e2.anzeige("m", 3)
    check("Spalte m bei Anzeige mm: Faktor 1000, mm, 1 Nachkommastelle", abs(f - 1000.0) < 1e-9 and txt == "mm" and nk == 1)
    f, txt, nk = e2.anzeige("kNm", 2)
    check("Spalte kNm bei N und mm: Faktor 1e6, Nmm", abs(f - 1e6) < 1e-3 and txt == "Nmm")
    f, txt, nk = e2.anzeige("N/mm²", 1)
    check("Spannungsspalte bleibt N/mm² (Faktor 1)", abs(f - 1.0) < 1e-12 and txt == "N/mm²")
    f, txt, nk = e2.anzeige("%", 1)
    check("unbekannte Einheit bleibt unverändert", f == 1.0 and txt == "%" and nk == 1)
    f, txt, nk = Einheiten(verformung="cm").anzeige("mm", 2)
    check("Verformungsspalte mm bei Anzeige cm: Faktor 0,1", abs(f - 0.1) < 1e-12 and txt == "cm")


def test_modell():
    m = Model()
    check("Vorgabe im Modell: kN, m, mm, N/mm²", m.einheiten.kraft == "kN" and m.einheiten.spannung == "N/mm²")
    m.einheiten.kraft = "N"
    m.einheiten.nk_kraft = 0
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Einheiten werden gespeichert und geladen", m2.einheiten.kraft == "N" and m2.einheiten.nk_kraft == 0)
    m3 = Model.from_dict({"format": 1, "name": "alt", "nodes": [], "elements": [], "materials": {}, "sections": {},
                          "shells": {}, "supports": [], "load_cases": [], "combinations": []})
    check("alte Datei ohne Einheiten lädt mit Vorgaben", m3.einheiten.kraft == "kN")
    check("Beschreibung", "Kraft N" in m.einheiten.beschreibung())


def main():
    for f in (test_faktoren, test_texte_und_tabellen, test_modell):
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
