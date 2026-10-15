"""Freie Ankerlaenge und Kraftverlust aus dem Verankerungsschlupf im Spannstahlnachweis
(Auftrag des Anwenders vom 15.10.2026).

Der Anwender traegt als Pressenkraft P0 = 944,4 kN ein (0,9 · 835 · 1 256,6 mm²) und
nimmt den Schlupf aus der Zulassung; der Nachweis soll die freie Ankerlaenge L [m],
den Schlupf Δs [mm] und den Kraftverlust ΔP [kN] zeigen - in der Ausgabe
(Protokoll, Maske Ergebnisse), im Bericht (Kennwerte des Stabs und Tabelle
„Spannstahl je Anker“).

Handrechnung (ein Anker zwischen Federn, wie tests/test_vorspannung_presse.py):
  E = 210 GPa, A_A = 1 000 mm², L = 1 m  -> k_A = E A / L = 210 kN/mm
  k_K = 4 k_A = 840 kN/mm, P0 = 500 kN, Δs = 0,5 mm
  ΔP = k_A · Δs · k_K / (k_A + k_K) = 105 · 840 / 1 050 = 84 kN
  N_verankert = P0 − ΔP = 416 kN  (= Ergebnis der Rechnung)
und fuer den Anker mit starrer Umgebung (Rund 40, L = 3,23 m, E = 170 GPa, Δs = 1 mm):
  k_A = 170 000 · 1 256,64 / 3 230 = 66,14 kN/mm, ΔP = 66,14 kN, 1 010,84 − 66,14 = 944,70 kN.

Aufruf:  python -m tests.test_spannstahl_schlupfanzeige
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")

from statik3d import solver                                           # noqa: E402
from statik3d.ec3 import spannstahl as sp                             # noqa: E402
from tests import test_vorspannung_presse as tp                       # noqa: E402

RESULTS = tp.RESULTS
check, nahe = tp.check, tp.nahe


def _federanker():
    """Ein Anker aus Spannstahl zwischen Federn (Handrechnung oben)."""
    m, H, el, eK = tp._federn(lasten=(("V", 0.0),))
    mat = m.materials["Stahl"]
    mat.art = "Spannstahl"
    mat.fy, mat.fu = 835e6, 1030e6
    m.add_combination("K1", {"V": 1.0}, "ULS")
    return m


def test_handrechnung_zwischen_federn():
    print("\n--- Anker zwischen Federn: ΔP = k_A·Δs·k_K/(k_A + k_K), P0 − ΔP = N_verankert ---")
    m = _federanker()
    an = solver.solve_all(m, design=True)
    mc = an.design.members["A1"]
    ang = getattr(mc, "schlupf", None) or []
    check("der Stab trägt eine Schlupfangabe", len(ang) == 1, str(ang))
    if not ang:
        return
    a = ang[0]
    dP = tp.K_A * tp.DS1 * tp.K_K / (tp.K_A + tp.K_K)
    nahe("freie Ankerlänge L = 1 m", a["L_frei"], 1.0, 1e-12, "m")
    nahe("Schlupf Δs = 0,5 mm", a["schlupf"], tp.DS1, 1e-12, "m")
    nahe("k_A = E·A/L = 210 kN/mm", a["k_A"], tp.K_A, 1e-12, "N/m")
    nahe("Verlust bei starrer Umgebung k_A·Δs = 105 kN", a["verlust_starr"], tp.K_A * tp.DS1, 1e-12, "N")
    nahe("Kraftverlust ΔP = 84 kN (Handrechnung)", a["verlust"], dP, 1e-9, "N")
    nahe("P0 − ΔP = 416 kN", a["P0"] - a["verlust"], 416e3, 1e-9, "N")
    st = tp._st(an.cases["V"], "A1")
    nahe("… und das ist die verankerte Kraft im Ergebnis", a["P0"] - a["verlust"], st["N_verankert"], 1e-9, "N")
    check("Herkunft: Ergebnis des Spannschritts", "Ergebnis" in a["herkunft"], a["herkunft"])


def test_ausgabe_zeile():
    print("\n--- Ausgabe: Zeile im Protokoll und in der Maske Ergebnisse ---")
    an = solver.solve_all(_federanker(), design=True)
    s = an.design.summary()
    zeilen = [z for z in s.splitlines() if "Verankerungsschlupf" in z]
    print("     " + "\n     ".join(zeilen))
    check("summary nennt den Verankerungsschlupf in einer Zeile", len(zeilen) == 1)
    z = zeilen[0] if zeilen else ""
    for t in ("A1", "freie Länge 1.000 m", "Δs = 0.50 mm", "ΔP = 84.00 kN", "P₀ = 500.00 kN",
              "416.00 kN"):
        check(f"… enthält „{t}“", t in z)


def test_ausgabe_gebuendelt():
    print("\n--- Ausgabe: gleiche Anker in einer Zeile ---")
    from statik3d.ec3.design import MemberCheck
    from statik3d.ec3.design import DesignResults
    d = DesignResults()
    for i in range(1, 17):
        mc = MemberCheck(f"S{i}", "Rund 40", "Spannstahl", 3.23)
        mc.art = "Spannstahl"
        mc.schlupf = [{"lastfall": "LF1", "P0": 944.4e3, "schlupf": 1e-3, "L_frei": 3.23, "k_A": 66.14e6,
                       "verlust_starr": 66.14e3, "verlust": 66.14e3, "herkunft": "starre Umgebung"}]
        d.members[mc.member] = mc
    zeilen = [z for z in d.summary().splitlines() if "Verankerungsschlupf" in z]
    check("16 gleiche Anker stehen in einer Zeile", len(zeilen) == 1, str(len(zeilen)))
    check("… mit dem Bereich der Namen", zeilen and "S1" in zeilen[0] and "S16" in zeilen[0],
          zeilen[0] if zeilen else "")


def test_starre_umgebung_ohne_ergebnis():
    print("\n--- Ohne Ergebnis des Spannschritts: ΔP = k_A·Δs (starre Umgebung) ---")
    m = tp._spannanker(1010.84e3, 1.0e-3)
    ang = sp.schlupfangaben(m, m.members["A1"], {})
    check("eine Angabe", len(ang) == 1, str(ang))
    if not ang:
        return
    a = ang[0]
    nahe("L = 3,23 m", a["L_frei"], tp.L_ANKER, 1e-12, "m")
    nahe("k_A = 66,14 kN/mm", a["k_A"], tp.E_ANKER * tp.A_NENN / tp.L_ANKER, 1e-9, "N/m")
    nahe("ΔP = 66,14 kN", a["verlust"], a["k_A"] * 1e-3, 1e-12, "N")
    nahe("P0 − ΔP = 944,70 kN", a["P0"] - a["verlust"], 944.70e3, 2e-6, "N")
    check("Herkunft: starre Umgebung", "starre Umgebung" in a["herkunft"], a["herkunft"])
    # Endvorspannung ohne Schlupf: keine Angabe
    m0 = tp._spannanker(944.7e3, None)
    check("Endvorspannung ohne Schlupf: keine Angabe", sp.schlupfangaben(m0, m0.members["A1"], {}) == [])


def test_bericht():
    print("\n--- Bericht: Kennwerte des Stabs und Tabelle „Spannstahl je Anker“ ---")
    from statik3d.report import Report
    m = tp._spannanker(944.7e3 + tp.E_ANKER * tp.A_NENN / tp.L_ANKER * 1e-3, 1e-3)
    an = solver.solve_all(m, design=True)
    html = Report(m, an).html()
    for t in ("Freie Ankerlänge", "3.230 m", "Kraftverlust ΔP", "66.14 kN",
              "L_frei [m]", "Δs [mm]", "ΔP [kN]"):
        check(f"Bericht enthält „{t}“", t in html)
    i = html.find("Spannstahl je Anker")
    teil = html[i:i + 8000]
    check("… die Tabelle „Spannstahl je Anker“ trägt die drei Spalten",
          all(t in teil for t in ("L_frei [m]", "Δs [mm]", "ΔP [kN]")))


def test_ohne_schlupf_unveraendert():
    print("\n--- Ohne Schlupf bleibt die Ausgabe, wie sie war ---")
    m = tp._spannanker(944.7e3, None)
    an = solver.solve_all(m, design=True)
    mc = an.design.members["A1"]
    check("keine Schlupfangabe", not (getattr(mc, "schlupf", None) or []))
    check("keine Zeile in summary", "Verankerungsschlupf" not in an.design.summary())
    from statik3d.report import Report
    html = Report(m, an).html()
    check("kein „Freie Ankerlänge“ im Bericht", "Freie Ankerlänge" not in html)
    check("keine zusätzlichen Spalten in „Spannstahl je Anker“", "L_frei [m]" not in html)


def main():
    for t in (test_handrechnung_zwischen_federn, test_ausgabe_zeile, test_ausgabe_gebuendelt,
              test_starre_umgebung_ohne_ergebnis, test_bericht, test_ohne_schlupf_unveraendert):
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
