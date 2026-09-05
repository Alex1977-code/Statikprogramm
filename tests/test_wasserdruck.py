"""
Lastgenerierer Wasserdruck: Druckverlauf, Kennwerte, Lasten auf dem Netz.
Geschlossene Loesungen: Rechteckschuetz F = ½ρgh²b mit Angriffspunkt h/3,
Netto mit Unterwasser, Poleni, Torricelli.
Aufruf:  python -m tests.test_wasserdruck
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Flaeche, Situation  # noqa: E402
from statik3d import wasserdruck as wdm  # noqa: E402
from statik3d.wasserdruck import Wasserdruck, druck, kennwerte, G  # noqa: E402

RESULTS = []
RHO = 1000.0


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6g} ana={want:.6g} Abw={err * 100:.4f}% {unit}")


def test_druckverlauf():
    wd = Wasserdruck("S", h_ow=4.0, z_uk=0.0, z_ok=5.0, breite=3.0, absenkung=False)
    close("hydrostatisch p(0) = ρ g h", druck(wd, 0.0), RHO * G * 4.0, 1e-12, "Pa")
    close("hydrostatisch p(1) = ρ g (h − z)", druck(wd, 1.0), RHO * G * 3.0, 1e-12, "Pa")
    check("ueber dem Wasserspiegel kein Druck", druck(wd, 4.5) == 0.0)
    wd.h_uw = 2.0
    close("netto mit Unterwasser p(0) = ρ g (h_ow − h_uw)", druck(wd, 0.0), RHO * G * 2.0, 1e-12, "Pa")
    close("netto oberhalb UW p(3) = ρ g (h_ow − z)", druck(wd, 3.0), RHO * G * 1.0, 1e-12, "Pa")
    # Ueberstroemt mit Absenkung
    wd = Wasserdruck("Ü", h_ow=6.0, z_uk=0.0, z_ok=5.0, breite=3.0, ueberstroemt=True, absenkung=True)
    close("Krone: p = ⅔ ρ g h_ü (Geschwindigkeitshöhe abgezogen)", druck(wd, 5.0),
          2.0 / 3.0 * RHO * G * 1.0, 1e-12, "Pa")
    close("2 h_ü unter der Krone wieder hydrostatisch", druck(wd, 3.0), RHO * G * 3.0, 1e-12, "Pa")
    close("dazwischen linear", druck(wd, 4.0), RHO * G * 2.0 - RHO * G / 3.0 * 0.5, 1e-12, "Pa")
    wd.absenkung = False
    close("ohne Absenkung hydrostatisch bis zur Krone", druck(wd, 5.0), RHO * G * 1.0, 1e-12, "Pa")
    # Unterstroemt mit Absenkung, UW trocken
    wd = Wasserdruck("U", h_ow=4.0, z_uk=0.0, z_ok=5.0, breite=3.0, unterstroemt=True, spalt=0.5,
                     mu_a=0.61, absenkung=True)
    close("Unterkante: Druck des kontrahierten Strahls ρ g μ_a a", druck(wd, 0.0),
          RHO * G * 0.61 * 0.5, 1e-12, "Pa")
    close("2 a über der Unterkante wieder hydrostatisch", druck(wd, 1.0), RHO * G * 3.0, 1e-12, "Pa")
    wd.h_uw = 1.5
    close("mit Unterwasser: an der Unterkante Nettodruck null", druck(wd, 0.0), 0.0, 1e-12, "Pa")


def test_kennwerte():
    wd = Wasserdruck("S", h_ow=4.0, z_uk=0.0, z_ok=5.0, breite=3.0, absenkung=False)
    kw = kennwerte(wd)
    close("Rechteckschütz F = ½ ρ g h² b", kw["F"], 0.5 * RHO * G * 16.0 * 3.0, 1e-6, "N")
    close("Angriffspunkt h/3 über der Dichtung", kw["hebel"], 4.0 / 3.0, 1e-6, "m")
    wd.h_uw = 2.0
    kw = kennwerte(wd)
    close("netto F = ½ ρ g b (h_ow² − h_uw²)", kw["F"], 0.5 * RHO * G * 3.0 * (16.0 - 4.0), 1e-6, "N")
    close("netto Hebel (h_ow³ − h_uw³)/(3 (h_ow² − h_uw²))", kw["hebel"], 56.0 / 36.0, 1e-6, "m")
    wd = Wasserdruck("Ü", h_ow=6.0, z_uk=0.0, z_ok=5.0, breite=3.0, ueberstroemt=True, mu_ue=0.62)
    kw = kennwerte(wd)
    close("Poleni q = ⅔ μ √(2g) h_ü^1,5", kw["q_ue"], 2 / 3 * 0.62 * math.sqrt(2 * G) * 1.0, 1e-12)
    close("Q = q b", kw["Q_ue"], kw["q_ue"] * 3.0, 1e-12)
    close("kritische Geschwindigkeit v_c = √(g ⅔ h_ü)", kw["v_c"], math.sqrt(G * 2 / 3), 1e-12)
    check("Fr = 1 auf der Krone", abs(kw["Fr_c"] - 1.0) < 1e-12)
    wd = Wasserdruck("U", h_ow=4.0, z_uk=0.0, z_ok=5.0, breite=3.0, unterstroemt=True, spalt=0.5, mu_a=0.61)
    kw = kennwerte(wd)
    dh = 4.0 - 0.61 * 0.5
    close("Torricelli v = √(2 g Δh)", kw["v_a"], math.sqrt(2 * G * dh), 1e-12)
    close("Ausfluss q = μ a v", kw["q_a"], 0.61 * 0.5 * math.sqrt(2 * G * dh), 1e-12)
    close("Froude des Strahls", kw["Fr_a"], kw["v_a"] / math.sqrt(G * 0.61 * 0.5), 1e-12)
    wd.cp_dyn = 0.2
    kw = kennwerte(wd)
    close("Druckschwankung Δp = c_p' ρ v²/2", kw["dp_dyn"], 0.2 * RHO * kw["v_a"] ** 2 / 2, 1e-12, "Pa")
    text = wdm.erlaeuterung(wd, kw)
    check("Erläuterung nennt Torricelli und Druckschwankung",
          any("Torricelli" in t for t in text) and any("Druckschwankung" in t for t in text))
    svg = wdm.skizze_svg(wd, kw)
    check("Skizze als SVG mit Resultierender", svg.startswith("<svg") and "F =" in svg and "v_a" in svg)


def _haut(nx: int = 6, nz: int = 40, b: float = 3.0, h: float = 5.0):
    """Senkrechte Haut in der y-z-Ebene bei x = 0 als Flaeche mit Schalen."""
    m = Model("Schütz")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", 0.012))
    ids = [[m.add_node(0.0, i * b / nx, k * h / nz) for k in range(nz + 1)] for i in range(nx + 1)]
    el = []
    for i in range(nx):
        for k in range(nz):
            el.append(m.add_element("shell4", [ids[i][k], ids[i + 1][k], ids[i + 1][k + 1], ids[i][k + 1]],
                                    "S", "t"))
    m.flaechen["Haut"] = Flaeche("Haut", dicke="t", material="S", elemente=el)
    for k in range(nz + 1):
        m.fix(ids[0][k], "all")
        m.fix(ids[nx][k], "all")
    return m, el


def test_lasten_auf_dem_netz():
    m, el = _haut()
    wd = Wasserdruck("Schütz", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0], absenkung=False)
    kw = wdm.lasten_erzeugen(m, wd)
    check("Geometrie aus den Flächen: Dichtung 0, Oberkante 5, Breite 3",
          kw["z_uk"] == 0.0 and kw["z_ok"] == 5.0 and abs(kw["breite"] - 3.0) < 1e-12, str((kw["z_uk"], kw["z_ok"], kw["breite"])))
    F = 0.5 * RHO * G * 16.0 * 3.0
    close("Summe der Elementlasten = ½ ρ g h² b", kw["kontrolle"]["F"][0], F, 1e-9, "N")
    check("Elementlasten nur auf den benetzten Elementen (32 von 40 Reihen)",
          kw["elementlasten"] == 6 * 32, str(kw["elementlasten"]))
    close("Angriffspunkt aus den Elementlasten ≈ h/3", kw["kontrolle"]["M"][1] / kw["kontrolle"]["F"][0],
          4.0 / 3.0, 1e-3, "m")
    check("Lastfall angelegt und Generierer im Modell",
          wd.lastfall in m.load_cases and "Schütz" in m.wasserdruecke
          and any(gl.verlauf.get("art") == "wasser" for gl in m.load_cases[wd.lastfall].geometrielasten))
    # Neuvernetzen / Verteilen erzeugt keine doppelten Lasten
    m.lasten_verteilen()
    k2 = wdm.kontrollsumme(m, wd)
    close("erneutes Verteilen: gleiche Summe", k2["F"][0], F, 1e-9, "N")
    kw = wdm.lasten_erzeugen(m, wd)
    close("erneutes Erzeugen ersetzt statt zu verdoppeln", kw["kontrolle"]["F"][0], F, 1e-9, "N")
    check("nur eine Objektlast je Fläche", sum(1 for gl in m.load_cases[wd.lastfall].geometrielasten) == 1)
    # Situation und Unterwasser
    m.situationen["S1"] = Situation("S1", "", [])
    wd2 = Wasserdruck("Betrieb", situation="S1", flaechen=["Haut"], h_ow=4.0, h_uw=2.0,
                      richtung=[1.0, 0.0, 0.0], absenkung=False)
    kw2 = wdm.lasten_erzeugen(m, wd2)
    close("Netto mit Unterwasser auf dem Netz", kw2["kontrolle"]["F"][0],
          0.5 * RHO * G * 3.0 * (16.0 - 4.0), 1e-9, "N")
    check("Lastfall traegt die Situation", m.load_cases[wd2.lastfall].situation == "S1")
    try:
        wdm.lasten_erzeugen(m, Wasserdruck("x", situation="gibt es nicht", flaechen=["Haut"], h_ow=1.0))
        check("unbekannte Situation wird abgewiesen", False)
    except ValueError:
        check("unbekannte Situation wird abgewiesen", True)
    # Druckschwankung als eigener Lastfall
    wd3 = Wasserdruck("Unter", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0.0, 0.0],
                      unterstroemt=True, spalt=0.5, cp_dyn=0.2)
    kw3 = wdm.lasten_erzeugen(m, wd3)
    lc = m.load_cases.get(wd3.lastfall_dyn)
    check("Druckschwankung als eigener Lastfall", lc is not None and kw3["dp_dyn"] > 0
          and lc.face_loads and abs(abs(lc.face_loads[0].p) - kw3["dp_dyn"]) < 1e-9, str(kw3["dp_dyn"]))
    # Senkrecht zur Flaeche statt Richtung: gleicher Betrag
    wd4 = Wasserdruck("Normal", flaechen=["Haut"], h_ow=4.0, absenkung=False)
    kw4 = wdm.lasten_erzeugen(m, wd4)
    close("Druck senkrecht zur Fläche: gleicher Betrag", kw4["kontrolle"]["betrag"], F, 1e-9, "N")
    # Speichern
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Generierer und Lasten ueberleben Speichern", set(m2.wasserdruecke) == set(m.wasserdruecke)
          and m2.wasserdruecke["Unter"].spalt == 0.5
          and any(gl.verlauf.get("art") == "wasser" for gl in m2.load_cases[wd.lastfall].geometrielasten))
    m2.lasten_verteilen()
    close("nach dem Laden: Lasten neu verteilt, gleiche Summe", wdm.kontrollsumme(m2, wd)["F"][0], F, 1e-9, "N")


def main():
    for t in (test_druckverlauf, test_kennwerte, test_lasten_auf_dem_netz):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
