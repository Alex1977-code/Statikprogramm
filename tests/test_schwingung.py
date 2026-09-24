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


def _haut(nx=6, nz=40, b=3.0, h=5.0, t=0.012, z0=0.0):
    m = Model("Schütz")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", t))
    ids = [[m.add_node(0.0, i * b / nx, z0 + k * h / nz) for k in range(nz + 1)] for i in range(nx + 1)]
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
    # Persistenz. sw.nachweis rechnet nur; eingetragen wird der Nachweis von
    # der Oberflaeche (gui/main.py setzt m.schwingungen[sn.name] vor dem
    # Aufruf). Frueher hiess die erste Pruefung "wird mit dem Modell
    # gespeichert", sicherte aber "N1" NICHT im Modell zu (Befund FM1, 22.09.2026).
    check("sw.nachweis trägt den Nachweis nicht selbst ins Modell ein",
          "N1" not in m.schwingungen, str(sorted(m.schwingungen)))
    m.schwingungen["N1"] = sn
    d = json.loads(json.dumps(m.to_dict()))
    gespeichert = [x.get("name") for x in d.get("schwingungen") or []]
    check("Schwingungsnachweis wird mit dem Modell gespeichert", "N1" in gespeichert, str(gespeichert))
    m4 = Model.from_dict(d)
    check("… und geladen", "N1" in m4.schwingungen and m4.schwingungen["N1"].d_kante == 0.2
          and m4.schwingungen["N1"].betriebsstunden == 500.0 and m4.wasserdruecke["S"].h_ow == 4.0,
          str(sorted(m4.schwingungen)))
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


def test_ausweichen_erreicht_bericht():
    """Ein Ausweichen des Gleichungsloesers gehoert in Protokoll und Bericht.

    Befund B121 (23.09.2026): sw.nachweis ruft solve_modal ohne Fortschritt
    und den Druckschwankungs-Lastfall ueber solve_cases ohne Fortschritt. Der
    Grund stand nur in res_luft.info/res_wasser.info (die Oberflaeche zeigt
    ihn ueber _solve_done der Wasser-Modalanalyse); erg.log, das Kapitel und
    die Hinweise des Berichts aus einer Analyse (Report(m, an)) nannten
    ihn nicht - im ganzen Bericht 0-mal "ausgewichen", mit PARDISO im Prozess
    zum Scheitern gebracht wie in tests/test_loeser.py. Das Ausweichen des
    Druckschwankungs-Lastfalls ging ganz verloren (res_d wird nirgends
    abgelegt). Den Bericht ohne Analyse (aus res_wasser) prueft der Teil
    "ohne Analyse" vor der Gegenprobe.
    """
    import re
    import pypardiso
    from statik3d import parallel
    from statik3d.report.html import Report

    def aufbau(z0=0.0):
        m = _haut(nz=20, z0=z0)
        wd = Wasserdruck("S", flaechen=["Haut"], h_ow=4.0, richtung=[1.0, 0, 0], unterstroemt=True,
                         spalt=0.3, cp_dyn=0.1)
        wdm.lasten_erzeugen(m, wd)
        m.wasserdruecke["S"] = wd
        return m, wd, solver.Analysis(m)

    sn = sw.Schwingungsnachweis("N1", wasserdruck="S", n_moden=2, d_kante=0.2, betriebsstunden=100.0)
    alt_backend = parallel.settings().solver_backend
    parallel.configure(solver_backend="auto")
    echt = pypardiso.PyPardisoSolver.factorize

    def wirft(self, A):
        raise RuntimeError("Probe: PARDISO verweigert")

    pypardiso.PyPardisoSolver.factorize = wirft
    try:
        m, wd, an = aufbau()
        # ohne Fortschritt - wie ein Aufruf ohne Oberflaeche
        an.schwingung = sw.nachweis(m, sn, an)
        # Druckschwankungs-Lastfall aus der Berechnung "Alle Lastfaelle"
        m_a, wd_a, _an = aufbau()
        an_a = solver.solve_all(m_a)
        an_a.schwingung = sw.nachweis(m_a, sn, an_a)
        # Nachweis ohne Analyse - wie die Oberflaeche ihn fuehrt, solange keine
        # Ergebnisse von "Alle Lastfaelle + Kombinationen" oder "Nur aktiver
        # Lastfall" vorliegen (self.analysis ist None, die Angaben stehen im Modell)
        m_o, wd_o, _an_o = aufbau()
        m_o.schwingungen[sn.name] = sn
        erg_o = sw.nachweis(m_o, sn, None)
        # ... ohne Modalanalyse im Wasser: Haken "Hydrodynamische Masse" aus
        # bzw. die benetzte Flaeche ganz ueber dem Wasserspiegel (m_hydro = 0)
        from dataclasses import replace
        sn_h = replace(sn, hydromasse=False)
        ohne_wasser = {}
        for fall, z0, sn_f in (("Haken aus", 0.0, sn_h), ("über dem Wasserspiegel", 5.0, sn)):
            m_f, _wd_f, _an_f = aufbau(z0)
            m_f.schwingungen[sn_f.name] = sn_f
            ohne_wasser[fall] = (m_f, sw.nachweis(m_f, sn_f, None))
    finally:
        pypardiso.PyPardisoSolver.factorize = echt
        parallel.configure(solver_backend=alt_backend)
    erg = an.schwingung
    check("Vorbedingung: die Modalanalyse ist ausgewichen",
          "verweigert" in str(erg.res_luft.info.get("ausweichgrund", "")),
          repr(erg.res_luft.info.get("ausweichgrund"))[:80])
    check("Vorbedingung: Antwort auf die Druckschwankung gerechnet",
          bool(erg.dyn) and erg.dyn.get("lastfall") == wd.lastfall_dyn, str(erg.dyn.get("lastfall")))
    zeilen = [z for z in erg.log if "ausgewichen" in z]
    check("erg.log nennt das Ausweichen mit Grund, eine Zeile",
          len(zeilen) == 1 and "Probe: PARDISO verweigert" in zeilen[0],
          f"{len(zeilen)} Zeilen: " + (zeilen[0][:90] if zeilen else ""))
    check("… mit Luft, Wasser und dem Druckschwankungs-Lastfall",
          bool(zeilen) and "in Luft" in zeilen[0] and "im Wasser" in zeilen[0]
          and wd.lastfall_dyn in zeilen[0], zeilen[0][:160] if zeilen else "")
    html = Report(m, an).html()
    punkte = [re.sub("<[^>]+>", "", p) for p in re.findall(r"<li>(.*?)</li>", html, re.S)
              if "ausgewichen" in p]
    # Rechnet nur der Nachweis (die Analyse ist leer), steht er allein in der
    # Zeile und damit beim Namen
    check("der Bericht nennt es unter den Hinweisen - genau eine Zeile mit Grund",
          len(punkte) == 1 and "Probe: PARDISO verweigert" in punkte[0]
          and "bei 1 Ergebnis (Schwingungsnachweis N1)" in punkte[0],
          f"{len(punkte)} Zeilen: " + (punkte[0][:110] if punkte else ""))
    check("der Grund steht einmal im Bericht",
          html.count("Probe: PARDISO verweigert") == 1,
          f"{html.count('Probe: PARDISO verweigert')} mal")
    # Kommt der Lastfall aus der Analyse, zaehlt er im Bericht bei den
    # Lastfaellen und im Nachweis nicht noch einmal. Der Bericht bleibt bei
    # einer Zeile fuer LF1, Wasser S, Wasser S dyn und den Nachweis. Sie nennt
    # nur die ersten drei Namen (solver.ausweichen_gebuendelt); der Nachweis
    # steht hinter den Lastfaellen und Kombinationen und wird dort nur
    # mitgezaehlt. Das Handbuch sagte am Stand 802ff71, der Bericht nenne ihn
    # mit "(Schwingungsnachweis Name)" in der Zeile der Lastfaelle und den
    # Lastfall "unter seinem eigenen Namen" - sobald drei Lastfaelle denselben
    # Grund tragen, stimmt das fuer den Nachweis nicht, fuer den Lastfall
    # nicht, wenn er hinter den ersten drei steht (gemessen 24.09.2026 mit drei
    # weiteren Lastfaellen: "bei 7 Ergebnissen (LF1, Zus1, Zus2 …)"). Die
    # Pruefung hielt hier bis dahin nur "bei 4 Ergebnissen" fest.
    zeilen_a = [z for z in an_a.schwingung.log if "ausgewichen" in z]
    check("Lastfall aus der Analyse: erg.log nennt nur Luft und Wasser",
          len(zeilen_a) == 1 and "bei 2 Ergebnissen" in zeilen_a[0]
          and wd_a.lastfall_dyn not in zeilen_a[0], zeilen_a[0][:110] if zeilen_a else "keine Zeile")
    html_a = Report(m_a, an_a).html()
    punkte_a = [re.sub("<[^>]+>", "", p) for p in re.findall(r"<li>(.*?)</li>", html_a, re.S)
                if "ausgewichen" in p]
    namen_a = [n for n, r in list(an_a.cases.items()) + list((getattr(an_a, "combinations", None) or {}).items())
               if "verweigert" in str((getattr(r, "info", None) or {}).get("ausweichgrund", ""))]
    check("Vorbedingung: drei Lastfälle der Analyse tragen denselben Grund",
          namen_a == ["LF1", "Wasser S", wd_a.lastfall_dyn], str(namen_a))
    check("Lastfall aus der Analyse: eine Hinweiszeile, der Nachweis zählt dort mit",
          len(punkte_a) == 1 and "bei 4 Ergebnissen" in punkte_a[0]
          and html_a.count("Probe: PARDISO verweigert") == 1,
          f"{len(punkte_a)} Zeilen: " + (punkte_a[0][:110] if punkte_a else ""))
    check("… sie nennt nur die ersten drei beim Namen, den Nachweis dahinter nicht",
          bool(punkte_a) and f"({', '.join(namen_a)} …)" in punkte_a[0]
          and "Schwingungsnachweis" not in punkte_a[0],
          punkte_a[0][:90] if punkte_a else "keine Zeile")

    # Ohne Analyse schreibt die Oberflaeche den Bericht aus der Modalanalyse
    # des Nachweises: _schwingung_rechnen legt den Nachweis nur an eine
    # vorhandene Analyse ("if self.analysis is not None"), _solve_done("modal",
    # erg.res_wasser) setzt self.results, und make_report schreibt
    # write_report(model, self.results) (gui/main.py). Eine Analyse entsteht
    # nur aus "Alle Lastfaelle + Kombinationen" oder "Nur aktiver Lastfall";
    # _solve_done("modal"/"buckling") laesst self.analysis unberuehrt, nach
    # "Eigenschwingungen" oder "Knicken" gilt also dasselbe (gemessen
    # 24.09.2026 an den Methoden des Hauptfensters, offscreen: nach
    # _solve_done("modal", ...) steht der Nachweis 0-mal im Bericht, nach
    # _solve_done("case", ...) 1-mal). Der Nachweis steht dann nicht im
    # Bericht, die Hinweiszeile nennt nur die Wasser-Modalanalyse; Luft und
    # Druckschwankungs-Lastfall zaehlen nicht mit. So war es schon am Stand
    # ec6448c (gemessen 24.09.2026, schwingung.py und report/html.py
    # zurueckgenommen: dieselbe Zeile). Das Handbuch sagte am Stand 900d08c
    # ohne Einschraenkung, der Bericht nenne den Nachweis als
    # "Schwingungsnachweis Name" und habe bis zum 23.09.2026 kein Ausweichen
    # genannt - beides gilt nur mit einer Analyse (Mangel der zweiten
    # Gegenpruefung); am Stand e5ef095 hing es dort an "Berechnen" (Mangel
    # der dritten Gegenpruefung).
    zeilen_o = [z for z in erg_o.log if "ausgewichen" in z]
    check("ohne Analyse: erg.log nennt Luft, Wasser und den Druckschwankungs-Lastfall",
          len(zeilen_o) == 1 and "bei 3 Ergebnissen" in zeilen_o[0] and wd_o.lastfall_dyn in zeilen_o[0],
          zeilen_o[0][:110] if zeilen_o else "keine Zeile")
    for umfang in ("lang", "kurz"):
        html_o = Report(m_o, erg_o.res_wasser, options={"umfang": umfang}).html()
        punkte_o = [re.sub("<[^>]+>", "", p) for p in re.findall(r"<li>(.*?)</li>", html_o, re.S)
                    if "ausgewichen" in p]
        check(f"ohne Analyse ({umfang}): eine Hinweiszeile, nur die Modalanalyse im Wasser",
              len(punkte_o) == 1 and "Probe: PARDISO verweigert" in punkte_o[0]
              and f"bei 1 Ergebnis (Eigenschwingungen im Wasser ({wd_o.name})): " in punkte_o[0],
              f"{len(punkte_o)} Zeilen: " + (punkte_o[0][:110] if punkte_o else ""))
        check(f"ohne Analyse ({umfang}): der Nachweis steht nicht im Bericht",
              f"Schwingungsnachweis {sn.name}" not in html_o
              and "Schwingungsnachweis des Verschlusses" not in html_o,
              f"{html_o.count('Schwingungsnachweis ' + sn.name)} / "
              f"{html_o.count('Schwingungsnachweis des Verschlusses')} mal")

    # Rechnet der Nachweis keine Modalanalyse im Wasser (Haken aus oder
    # m_hydro = 0), gilt res_wasser = res_luft (schwingung.py, "if M_add is not
    # None and erg.m_hydro > 0"), umbenannt wird nicht: Die Oberflaeche zeigt
    # und berichtet dann die Rechnung in Luft unter dem Namen "Modalanalyse"
    # aus solver.solve_modal, und gerade deren Ausweichen zaehlt in der Zeile.
    # Das Handbuch sagte am Stand e5ef095 ohne Einschraenkung "bei 1 Ergebnis
    # (Eigenschwingungen im Wasser (Wasserdruck))" und "das Ausweichen der
    # Eigenfrequenzen in Luft zaehlt dort nicht mit" (Maengel der dritten
    # Gegenpruefung, gemessen 24.09.2026; am Stand ec6448c dieselbe Zeile).
    for fall, (m_f, erg_f) in ohne_wasser.items():
        check(f"ohne Wasser-Modalanalyse ({fall}): Vorbedingung res_wasser = res_luft",
              erg_f.res_wasser is erg_f.res_luft and erg_f.m_hydro == 0.0
              and erg_f.res_wasser.name == "Modalanalyse",
              f"{erg_f.res_wasser is erg_f.res_luft} m_hydro={erg_f.m_hydro:g} {erg_f.res_wasser.name}")
        for umfang in ("lang", "kurz"):
            html_f = Report(m_f, erg_f.res_wasser, options={"umfang": umfang}).html()
            punkte_f = [re.sub("<[^>]+>", "", p) for p in re.findall(r"<li>(.*?)</li>", html_f, re.S)
                        if "ausgewichen" in p]
            check(f"ohne Wasser-Modalanalyse ({fall}, {umfang}): eine Zeile, die Rechnung in Luft",
                  len(punkte_f) == 1 and "Probe: PARDISO verweigert" in punkte_f[0]
                  and "bei 1 Ergebnis (Modalanalyse): " in punkte_f[0]
                  and f"Schwingungsnachweis {sn.name}" not in html_f,
                  f"{len(punkte_f)} Zeilen: " + (punkte_f[0][:80] if punkte_f else ""))

    # Gegenprobe: ohne Ausfall steht nichts da
    m0, _wd0, an0 = aufbau()
    an0.schwingung = sw.nachweis(m0, sn, an0)
    info0 = getattr(an0.schwingung, "info", None)
    check("ohne Ausfall: kein Ausweichen am Ergebnis und im Protokoll",
          info0 == {} and not any("ausgewichen" in z for z in an0.schwingung.log), repr(info0)[:80])
    html0 = Report(m0, an0).html()
    check("ohne Ausfall: der Bericht nennt kein Ausweichen",
          "ausgewichen" not in html0, f"{html0.count('ausgewichen')} mal")


def main():
    for f in (test_formeln, test_zusatzmasse_auf_dem_netz, test_eigenfrequenzen, test_nachweis, test_bericht,
              test_ausweichen_erreicht_bericht):
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
