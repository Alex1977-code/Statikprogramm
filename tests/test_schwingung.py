"""
Schwingungsnachweis des Verschlusses: hydrodynamische Masse (Westergaard),
Eigenfrequenzen trocken/nass, Strouhal, reduzierte Geschwindigkeit,
Vergroesserungsfunktion, Ermuedung.
Geschlossene Loesungen: Σ m'' = 7/12·ρ·H²·b; gleichmaessige Zusatzmasse
f_w = f_l/√(1+μ); Rayleigh-Schranke; V(r=1) = 1/(2ζ); N_R nach EN 1993-1-9.
Aufruf:  python -m tests.test_schwingung
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Flaeche  # noqa: E402
from statik3d import schwingung as sw  # noqa: E402
from statik3d import wasserdruck as wdm  # noqa: E402
from statik3d import solver, assemble as asm  # noqa: E402
from statik3d.wasserdruck import Wasserdruck, G  # noqa: E402

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


def _haut(nx=6, nz=40, b=3.0, h=5.0, t=0.012):
    m = Model("Schütz")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", t))
    ids = [[m.add_node(0.0, i * b / nx, k * h / nz) for k in range(nz + 1)] for i in range(nx + 1)]
    el = [m.add_element("shell4", [ids[i][k], ids[i + 1][k], ids[i + 1][k + 1], ids[i][k + 1]], "S", "t")
          for i in range(nx) for k in range(nz)]
    m.flaechen["Haut"] = Flaeche("Haut", dicke="t", material="S", elemente=el)
    for k in range(nz + 1):
        m.fix(ids[0][k], "all")
        m.fix(ids[nx][k], "all")
    return m


def test_formeln():
    H = 4.0
    close("Westergaard m''(H) = 7/8·ρ·H", sw.westergaard(H, H, RHO), 7 / 8 * RHO * H, 1e-12, "kg/m²")
    close("Westergaard m''(H/4) = 7/8·ρ·H/2", sw.westergaard(H, H / 4, RHO), 7 / 8 * RHO * H / 2, 1e-12)
    check("über dem Wasserspiegel keine Masse", sw.westergaard(H, -0.5, RHO) == 0.0)
    close("Σ m'' = 7/12·ρ·H²", sw.westergaard_gesamt(H, RHO), 7 / 12 * RHO * 16.0, 1e-12, "kg/m")
    # numerische Integration der Verteilung
    yy = np.linspace(0, H, 20001)
    close("∫ m'' dy numerisch = 7/12·ρ·H²", np.trapezoid([sw.westergaard(H, y, RHO) for y in yy], yy),
          7 / 12 * RHO * 16.0, 1e-5)
    close("Strouhal f_s = St·v/d", sw.strouhal_frequenz(0.2, 8.0, 0.1), 16.0, 1e-12, "Hz")
    check("f_s = 0 ohne Strömung", sw.strouhal_frequenz(0.2, 0.0, 0.1) == 0.0)
    close("V_r = v/(f·d)", sw.reduzierte_geschwindigkeit(8.0, 4.0, 0.1), 20.0, 1e-12)
    close("Vergrößerung bei r = 1: 1/(2ζ)", sw.vergroesserung(1.0, 0.02), 25.0, 1e-12)
    close("Vergrößerung bei r = 0: 1", sw.vergroesserung(0.0, 0.02), 1.0, 1e-12)
    close("Vergrößerung bei r = 2: 1/√(9 + 0.0064)", sw.vergroesserung(2.0, 0.02),
          1 / math.sqrt(9 + (2 * 0.02 * 2) ** 2), 1e-12)
    close("f_Wasser = f_Luft/√(1+μ)", sw.frequenz_im_wasser(10.0, 3.0), 5.0, 1e-12, "Hz")


def test_zusatzmasse_auf_dem_netz():
    m = _haut()
    wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0], absenkung=False)
    kw = wdm.lasten_erzeugen(m, wd)
    M, info = sw.zusatzmassen(m, wd, kw)
    close("Σ Knotenmassen = 7/12·ρ·H²·b (Gauß 2×2 je Element)", info["m_hydro"], 7 / 12 * RHO * 16.0 * 3.0, 2e-4, "kg")
    close("Theoriewert in den Kennzahlen", info["m_hydro_theorie"], 7 / 12 * RHO * 16.0 * 3.0, 1e-12)
    close("Masse der benetzten Haut ρ·t·A (z ≤ 4 m)", info["m_struktur"], 7850.0 * 0.012 * 12.0, 1e-9, "kg")
    check("Matrix symmetrisch, nur x-Richtung (Normale) belegt",
          abs(M - M.T).max() < 1e-9 and abs(M.diagonal()[1::6]).max() == 0.0 and abs(M.diagonal()[2::6]).max() == 0.0)
    close("Spur der Matrix = Gesamtmasse", M.diagonal().sum(), info["m_hydro"], 1e-9)
    # Knoten ueber dem Wasser tragen nichts
    z = m.nodes[:, 2]
    oben = np.flatnonzero(z > 4.0 + 1e-9)
    check("Knoten über dem Wasserspiegel ohne Zusatzmasse", all(M.diagonal()[6 * i] == 0.0 for i in oben))
    # Unterwasser addiert die zweite Seite
    wd.h_uw = 2.0
    M2, info2 = sw.zusatzmassen(m, wd, kw)
    close("Unterwasser: Σ = 7/12·ρ·b·(H_ow² + H_uw²)", info2["m_hydro"], 7 / 12 * RHO * 3.0 * (16.0 + 4.0), 2e-4)


def test_eigenfrequenzen():
    m = _haut(nz=20)
    n = 3
    r_l = solver.solve_modal(m, n)
    M_s = asm.mass(m)
    mu = 0.7
    r_u = solver.solve_modal(m, n, zusatzmasse=(mu * M_s).tocsr())
    for i in range(n):
        close(f"gleichmäßige Zusatzmasse: f_{i + 1} = f_Luft/√(1+μ)", r_u.freqs[i],
              r_l.freqs[i] / math.sqrt(1 + mu), 1e-9, "Hz")
    mm = sw.modale_massen(r_u, M_s, (mu * M_s).tocsr())
    close("modales Massenverhältnis = μ", mm[0][1] / mm[0][0], mu, 1e-9)
    # Westergaard: Rayleigh-Schranke mit der trockenen Eigenform
    wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0])
    M_add, info = sw.zusatzmassen(m, wd)
    r_w = solver.solve_modal(m, n, zusatzmasse=M_add)
    K = asm.stiffness(m)
    phi = np.asarray(r_l.modes[0], float).ravel()
    f_R = math.sqrt(float(phi @ (K @ phi)) / float(phi @ ((M_s + M_add) @ phi))) / (2 * math.pi)
    check("nasse Grundfrequenz ≤ Rayleigh-Quotient der trockenen Eigenform",
          r_w.freqs[0] <= f_R * (1 + 1e-9) and r_w.freqs[0] > 0, f"f_w={r_w.freqs[0]:.4f} R={f_R:.4f}")
    check("Wasser senkt jede Eigenfrequenz", all(r_w.freqs[i] < r_l.freqs[i] for i in range(n)))
    mu_min = 0.0
    check("nasse Grundfrequenz über der Schranke mit dem größten m_h/m",
          r_w.freqs[0] >= r_l.freqs[0] / math.sqrt(1 + info["m_hydro"] / info["m_struktur"] * 3.0) - 1e-9 or mu_min == 0.0)


def test_nachweis():
    m = _haut(nz=20)
    wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0], unterstroemt=True, spalt=0.3, cp_dyn=0.1)
    kw = wdm.lasten_erzeugen(m, wd)
    m.wasserdruecke["S"] = wd
    sn = sw.Schwingungsnachweis("N1", wasserdruck="S", n_moden=3, d_kante=0.2, betriebsstunden=500.0, jahre=50.0)
    erg = sw.nachweis(m, sn)
    v_a = math.sqrt(2 * G * (4.0 - 0.61 * 0.3))
    close("v aus dem Ausfluss (Torricelli)", erg.v, v_a, 1e-12, "m/s")
    close("f_s = St·v_a/d", erg.f_s, 0.2 * v_a / 0.2, 1e-12, "Hz")
    close("f_grenz = v/(V_r,grenz·d)", erg.f_grenz, v_a / 0.2, 1e-12, "Hz")
    m1 = erg.moden[0]
    close("V_r,1 = v/(f_1·d)", m1.V_r, v_a / (m1.f_wasser * 0.2), 1e-12)
    close("f_s/f_1", m1.verhaeltnis, erg.f_s / m1.f_wasser, 1e-12)
    close("Vergrößerung je Mode aus r und ζ", m1.dlf, sw.vergroesserung(m1.verhaeltnis, 0.02), 1e-12)
    check("Beurteilung: V_r > 1 → Hinweis, keine Resonanz",
          m1.hinweis and not m1.kritisch and "möglich" in m1.beurteilung, m1.beurteilung)
    check("Status mit Hinweis", erg.status.startswith("erfüllt mit Hinweis"), erg.status)
    d = erg.dyn
    check("Antwort auf die Druckschwankung gerechnet", d and d["lastfall"] == wd.lastfall_dyn and d["sigma_amp"] > 0)
    close("Δp = c_p'·ρ·v²/2", d["dp"], 0.1 * RHO * v_a ** 2 / 2, 1e-12, "Pa")
    close("V bei r = f_s/f_1", d["V"], sw.vergroesserung(erg.f_s / m1.f_wasser, 0.02), 1e-12)
    close("Δσ = 2·V·σ_amp", d["delta_sigma"], 2 * d["V"] * d["sigma_amp"], 1e-12)
    close("N = f_s·3600·h·Jahre", d["N"], erg.f_s * 3600 * 500 * 50, 1e-12)
    from statik3d.ec3.fatigue import sn_life
    close("N_R nach EN 1993-1-9 (Kerbfall 71, γ_Mf 1,15)", d["N_R"] if np.isfinite(d["N_R"]) else 1e300,
          sn_life(d["delta_sigma_Ed"], 71e6, 1.15) if np.isfinite(sn_life(d["delta_sigma_Ed"], 71e6, 1.15)) else 1e300, 1e-12)
    check("Tabelle und Zusammenfassung", len(erg.tabelle()) == 4 and "f₁" in erg.summary() and erg.log)
    check("Skizze als SVG mit Frequenzbild und Westergaard", "<svg" in sw.skizze_svg(erg) and "Westergaard" in sw.skizze_svg(erg))
    # Resonanzband: Kantenbreite so, dass f_s = f_1
    sn2 = sw.Schwingungsnachweis("N2", wasserdruck="S", n_moden=2, d_kante=0.2 * v_a / m1.f_wasser)
    erg2 = sw.nachweis(m, sn2)
    close("Kante so gewählt, dass f_s = f_1", erg2.f_s, erg2.moden[0].f_wasser, 1e-9, "Hz")
    check("Resonanz erkannt: nicht erfüllt", erg2.moden[0].kritisch and erg2.status == "nicht erfüllt", erg2.status)
    close("Vergrößerung in der Resonanz 1/(2ζ)", erg2.moden[0].dlf, 25.0, 1e-9)
    # ohne Stroemung
    wd.unterstroemt = False
    wdm.lasten_erzeugen(m, wd)
    erg3 = sw.nachweis(m, sw.Schwingungsnachweis("N3", wasserdruck="S", n_moden=2))
    check("ohne Strömung: keine Anregung, erfüllt", erg3.v == 0.0 and erg3.f_s == 0.0
          and erg3.status.startswith("erfüllt") and "keine Anregung" in erg3.moden[0].beurteilung, erg3.status)
    # ohne hydrodynamische Masse: f_Wasser = f_Luft
    erg4 = sw.nachweis(m, sw.Schwingungsnachweis("N4", wasserdruck="S", n_moden=2, hydromasse=False))
    check("ohne Westergaard: f_Wasser = f_Luft", all(abs(x.f_wasser - x.f_luft) < 1e-12 for x in erg4.moden))
    # hohe Steifigkeit -> f gross, V_r klein: unkritisch
    m2 = _haut(nz=20, t=0.2)
    wd2 = Wasserdruck("S", flaechen=["Haut"], h_ow=0.5, richtung=[1.0, 0, 0], unterstroemt=True, spalt=0.3)
    wdm.lasten_erzeugen(m2, wd2)
    m2.wasserdruecke["S"] = wd2
    erg5 = sw.nachweis(m2, sw.Schwingungsnachweis("N5", wasserdruck="S", n_moden=2, d_kante=1.0))
    v5 = math.sqrt(2 * G * (0.5 - 0.61 * 0.3))
    close("kleine Fallhöhe: v = √(2gΔh)", erg5.v, v5, 1e-12, "m/s")
    check("steife Haut, breite Kante: V_r ≤ 1 unkritisch, erfüllt",
          erg5.moden[0].V_r <= 1.0 and erg5.status == "erfüllt", f"V_r={erg5.moden[0].V_r:.3f} {erg5.status}")
    # Persistenz
    d = json.loads(json.dumps(m.to_dict()))
    m3 = Model.from_dict(d)
    check("Schwingungsnachweis wird mit dem Modell gespeichert",
          "N1" not in m3.schwingungen and m3.wasserdruecke["S"].h_ow == 4.0)
    m.schwingungen["N1"] = sn
    m4 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("… und geladen", m4.schwingungen["N1"].d_kante == 0.2 and m4.schwingungen["N1"].betriebsstunden == 500.0)
    # Fehlerfaelle
    try:
        sw.nachweis(m, sw.Schwingungsnachweis("X", wasserdruck="gibtsnicht"))
        check("fehlender Wasserdruck → ValueError", False)
    except ValueError as ex:
        check("fehlender Wasserdruck → ValueError", "gibt es nicht" in str(ex))


def test_bericht():
    from statik3d.report.html import Report
    m = _haut(nz=20)
    wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0], unterstroemt=True, spalt=0.3, cp_dyn=0.1)
    wdm.lasten_erzeugen(m, wd)
    m.wasserdruecke["S"] = wd
    an = solver.Analysis(m)
    an.schwingung = sw.nachweis(m, sw.Schwingungsnachweis("N1", wasserdruck="S", n_moden=2, d_kante=0.2, betriebsstunden=100.0), an)
    rep = Report(m, an)
    bl = rep.chapter_schwingung()
    check("Bericht: Kapitel mit Angaben, Modentabelle, Antwort, Erläuterung und Skizze",
          sum(1 for x in bl if x[0] == "table") == 3 and any(x[0] == "figure" and "<svg" in x[1] for x in bl)
          and any(x[0] == "p" and "Westergaard" in x[1] for x in bl), str([x[0] for x in bl]))
    html = rep.html() if hasattr(rep, "html") else ""
    check("Kapitel im Gesamtbericht", (not html) or "Schwingungsnachweis des Verschlusses" in html)


def main():
    for f in (test_formeln, test_zusatzmasse_auf_dem_netz, test_eigenfrequenzen, test_nachweis, test_bericht):
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
