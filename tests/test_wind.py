"""
Lastgenerierer Wind nach DIN EN 1991-1-4/NA: Hoehenprofil, Beiwerte, Lasten.
Zahlenwerte von Hand aus den Formeln der Norm; Summen der Elementlasten auf
einem Gebaeude gegen die geschlossene Loesung.
Aufruf:  python -m tests.test_wind
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, ShellProp, Flaeche, Member, Section  # noqa: E402
from statik3d import wind as wm  # noqa: E402
from statik3d.wind import Wind, q_p, v_m, I_v, c_r, k_r, RHO  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6g} ana={want:.6g} Abw={err * 100:.4f}% {unit}")


def test_profil():
    w = Wind("W", zone=2, profil="II")
    close("Windzone 2: v_b = 25 m/s", wm.v_basis(w), 25.0, 1e-12)
    close("q_b = ½ ρ v_b² = 390,625 N/m²", wm.q_basis(w), 0.5 * 1.25 * 625.0, 1e-12)
    # Kategorie II, z = 10 m: k_r = 0,19; c_r = 0,19 ln(200); I_v = 1/ln(200)
    close("k_r(II) = 0,19", k_r(0.05), 0.19, 1e-12)
    cr = 0.19 * math.log(10.0 / 0.05)
    close("c_r(10, II) = 0,19·ln(200)", c_r(10.0, "II"), cr, 1e-12)
    close("v_m(10) = c_r v_b", v_m(10.0, w), cr * 25.0, 1e-12)
    iv = 1.0 / math.log(200.0)
    close("I_v(10) = 1/ln(200)", I_v(10.0, w), iv, 1e-12)
    close("q_p(10, II) = (1 + 7 I_v) ½ ρ v_m²", q_p(10.0, w), (1 + 7 * iv) * 0.5 * 1.25 * (cr * 25.0) ** 2, 1e-12)
    close("unter z_min gilt z_min", q_p(0.5, w), q_p(2.0, w), 1e-12)
    w3 = Wind("W", zone=2, profil="III")
    z0 = 0.3
    close("k_r(III) = 0,19 (0,3/0,05)^0,07", k_r(z0), 0.19 * (0.3 / 0.05) ** 0.07, 1e-12)
    check("Kategorie III rauer: q_p kleiner", q_p(10.0, w3) < q_p(10.0, w))
    # Mischprofil Binnenland (NA Tab. NA.B.2)
    wb = Wind("W", zone=2, profil="Binnenland")
    qb = 0.5 * 1.25 * 625.0
    close("Binnenland z ≤ 7 m: q_p = 1,5 q_b", q_p(5.0, wb), 1.5 * qb, 1e-12)
    close("Binnenland z = 20 m: 1,7 q_b (z/10)^0,37", q_p(20.0, wb), 1.7 * qb * 2.0 ** 0.37, 1e-12)
    close("Binnenland z = 100 m: 2,1 q_b (z/10)^0,24", q_p(100.0, wb), 2.1 * qb * 10.0 ** 0.24, 1e-12)
    wk = Wind("W", v_b=27.5, profil="Küste und Inseln der Ostsee")
    close("v_b unmittelbar", wm.v_basis(wk), 27.5, 1e-12)
    close("Küste z = 10 m: 2,3 q_b", q_p(10.0, wk), 2.3 * 0.5 * 1.25 * 27.5 ** 2, 1e-12)
    w.c_dir = 0.85
    close("c_dir wirkt auf v_b", wm.v_basis(w), 0.85 * 25.0, 1e-12)


def test_beiwerte():
    close("Rechteck d/b = 1: c_f,0 = 2,1", wm.cf0_rechteck(1.0), 2.1, 1e-12)
    close("Rechteck d/b = 0,7: c_f,0 = 2,4", wm.cf0_rechteck(0.7), 2.4, 1e-12)
    close("Rechteck d/b = 5: c_f,0 = 1,0", wm.cf0_rechteck(5.0), 1.0, 1e-12)
    check("Rechteck dazwischen log-linear", 2.1 > wm.cf0_rechteck(1.5) > 1.65)
    close("Zylinder unterkritisch 1,2", wm.cf0_zylinder(1e5, 1e-5), 1.2, 1e-12)
    c = 1.2 + 0.18 * math.log10(10 * 1e-5) / (1 + 0.4 * math.log10(1.0))
    close("Zylinder Gl. 7.19 bei Re = 10⁶, k/b = 10⁻⁵", wm.cf0_zylinder(1e6, 1e-5), c, 1e-12)
    close("Zylinder mindestens 0,4", wm.cf0_zylinder(5e5, 1e-5), 0.4, 1e-12)
    close("Reynolds Re = b v/ν", wm.reynolds(0.2, 30.0), 0.2 * 30.0 / 15e-6, 1e-12)
    close("Schlankheit l < 15 m: λ = 2 l/b", wm.schlankheit(6.0, 0.2), 60.0, 1e-12)
    close("Schlankheit gedeckelt 70", wm.schlankheit(10.0, 0.1), 70.0, 1e-12)
    close("Schlankheit l ≥ 50 m: 1,4 l/b", wm.schlankheit(60.0, 2.0), 42.0, 1e-12)
    close("ψ_λ(70, φ = 1) = 0,92", wm.psi_lambda(70.0, 1.0), 0.92, 1e-12)
    close("ψ_λ(10, φ = 1) = 0,70", wm.psi_lambda(10.0, 1.0), 0.70, 1e-12)
    check("ψ_λ bei kleinem φ nahe 1", 0.95 < wm.psi_lambda(10.0, 0.1) <= 1.0)
    close("c_pe,D bei h/d = 1: +0,8", wm.cpe_luv(1.0), 0.8, 1e-12)
    close("c_pe,D bei h/d = 0,25: +0,7", wm.cpe_luv(0.25), 0.7, 1e-12)
    close("c_pe,E bei h/d = 1: −0,5", wm.cpe_lee(1.0), -0.5, 1e-12)
    close("c_pe,E bei h/d = 5: −0,7", wm.cpe_lee(5.0), -0.7, 1e-12)
    close("c_pe,E bei h/d = 3: −0,6 (interpoliert)", wm.cpe_lee(3.0), -0.6, 1e-12)
    check("Seitenzonen A/B/C ab Luvkante", wm.zone_seite(0.1, 2.0) == "A" and wm.zone_seite(1.0, 2.0) == "B"
          and wm.zone_seite(3.0, 2.0) == "C")
    check("Flachdach F/G/H/I", wm.zone_flachdach(0.1, 0.1, 4.0) == "F" and wm.zone_flachdach(0.1, 2.0, 4.0) == "G"
          and wm.zone_flachdach(1.0, 2.0, 4.0) == "H" and wm.zone_flachdach(3.0, 2.0, 4.0) == "I")
    check("freistehende Wand A/B/C/D", wm.zone_freie_wand(0.1, 2.0) == "A" and wm.zone_freie_wand(1.0, 2.0) == "B"
          and wm.zone_freie_wand(5.0, 2.0) == "C" and wm.zone_freie_wand(9.0, 2.0) == "D")
    close("Fachwerk scharfkantig φ = 0,35: 1,6", wm.cf0_fachwerk(0.35), 1.6, 1e-12)


def _quader(b=8.0, d=5.0, h=6.0, n=4, dach_u=None, dach_v=None):
    """Quader aus vier Waenden und Flachdach (Schalen), Normalen nach aussen.
    dach_u/dach_v: Teilungspunkte (0..1) des Dachs, damit die Elementkanten
    auf den Zonengrenzen liegen."""
    from statik3d.elements import shell as sh
    m = Model("Halle")
    m.add_material(Material("S"))
    m.add_shell_prop(ShellProp("t", 0.01))

    def flaeche(name, ecken, aussen, tu=None, tv=None):
        P0, P1, P2, P3 = map(lambda a: np.asarray(a, float), ecken)
        u, v = P1 - P0, P3 - P0
        tu = list(tu) if tu is not None else [i / n for i in range(n + 1)]
        tv = list(tv) if tv is not None else [k / n for k in range(n + 1)]
        if float(np.cross(u, v) @ np.asarray(aussen, float)) < 0:
            u, v, tu, tv = v, u, tv, tu
        ids = [[m.add_node(*(P0 + u * a + v * c)) for c in tv] for a in tu]
        el = [m.add_element("shell4", [ids[i][k], ids[i + 1][k], ids[i + 1][k + 1], ids[i][k + 1]], "S", "t")
              for i in range(len(tu) - 1) for k in range(len(tv) - 1)]
        m.flaechen[name] = Flaeche(name, dicke="t", material="S", elemente=el)
        X = m.nodes[[int(x) for x in m.elements[el[0]].nodes]]
        T3, _xy, _A = sh.shell_frame(X[0], X[1], X[2])
        assert float(T3[2] @ np.asarray(aussen, float)) > 0.9
    flaeche("Luv", [(0, 0, 0), (0, b, 0), (0, b, h), (0, 0, h)], (-1, 0, 0))
    flaeche("Lee", [(d, 0, 0), (d, b, 0), (d, b, h), (d, 0, h)], (1, 0, 0))
    flaeche("Seite1", [(0, 0, 0), (d, 0, 0), (d, 0, h), (0, 0, h)], (0, -1, 0))
    flaeche("Seite2", [(0, b, 0), (d, b, 0), (d, b, h), (0, b, h)], (0, 1, 0))
    flaeche("Dach", [(0, 0, h), (d, 0, h), (d, b, h), (0, b, h)], (0, 0, 1), dach_u, dach_v)
    return m


def test_gebaeude():
    b, d, h = 8.0, 5.0, 6.0
    e = min(b, 2 * h)
    # Dachnetz mit Kanten auf den Zonengrenzen: x = e/10, e/2; y = e/4, b − e/4
    tu = sorted({0.0, e / 10 / d, (e / 10 / d + e / 2 / d) / 2, e / 2 / d, (e / 2 / d + 1) / 2, 1.0})
    tv = sorted({0.0, e / 4 / b / 2, e / 4 / b, 0.5, 1 - e / 4 / b, 1 - e / 4 / b / 2, 1.0})
    m = _quader(b, d, h, n=4, dach_u=tu, dach_v=tv)
    w = Wind("W1", zone=2, profil="Binnenland", richtung=[1, 0, 0],
             flaechen=["Luv", "Lee", "Seite1", "Seite2", "Dach"])
    kw = wm.lasten_erzeugen(m, w)
    check("Rollen aus den Normalen", kw["rollen"] == {"Luv": "luv", "Lee": "lee", "Seite1": "seite",
                                                       "Seite2": "seite", "Dach": "dach"}, str(kw["rollen"]))
    close("h/d = 1,2 -> c_pe,D = 0,8", kw["cpe_D"], 0.8, 1e-12)
    close("c_pe,E bei h/d = 1,2 interpoliert", kw["cpe_E"], -0.5 - 0.2 * 0.2 / 4.0, 1e-12)
    qb = 0.5 * RHO * 25.0 ** 2
    qp = 1.5 * qb                                        # Binnenland, z ≤ 7 m: konstant
    lc = m.load_cases[w.lastfall]
    check("Lastfall Wind mit Kategorie W", lc.category == "W" and len(lc.geometrielasten) == 5)
    # Luvwand: F = c_pe q_p A in +x; Leewand: Sog c_pe q_p A ebenfalls in +x
    F_luv = 0.8 * qp * b * h
    F_lee = -kw["cpe_E"] * qp * b * h
    # Dachsog nach oben (+z), Seitenwaende heben sich auf (y)
    e = min(b, 2 * h)
    A_F = 2 * (e / 10) * (e / 4)
    A_G = (e / 10) * (b - 2 * e / 4)
    A_H = (e / 2 - e / 10) * b
    A_I = (d - e / 2) * b if d > e / 2 else 0.0
    F_dach = qp * (1.8 * A_F + 1.2 * A_G + 0.7 * A_H + 0.2 * A_I)
    F = kw["kontrolle"]["F"]
    close("Summe x = Luvdruck + Leesog", F[0], F_luv + F_lee, 1e-9, "N")
    close("Summe y = 0 (Seiten heben sich auf)", F[1] / (qp * d * h), 0.0, 1e-9)
    close("Summe z = Dachsog nach oben (Zonen F/G/H/I)", F[2], F_dach, 1e-9, "N")
    check("Elementlasten auf allen Elementen", kw["elementlasten"] == len(m.elements))
    # Innendruck
    w.c_pi = 0.2
    kw = wm.lasten_erzeugen(m, w)
    close("Innendruck −c_pi auf allen Flächen: Summe x unverändert (Luv −, Lee +)",
          kw["kontrolle"]["F"][0], F_luv + F_lee, 1e-9, "N")
    close("Innendruck erhöht den Dachsog um c_pi q_p A", kw["kontrolle"]["F"][2], F_dach + 0.2 * qp * b * d, 1e-9, "N")
    check("Erneutes Erzeugen ersetzt", len(m.load_cases[w.lastfall].geometrielasten) == 5)
    # Andere Richtung: -y -> Seite2 wird Luv
    w2 = Wind("W2", zone=2, profil="Binnenland", richtung=[0, -1, 0], flaechen=list(w.flaechen))
    kw2 = wm.lasten_erzeugen(m, w2)
    check("Anströmung −y: Seite2 ist Luv, Seite1 Lee", kw2["rollen"]["Seite2"] == "luv" and kw2["rollen"]["Seite1"] == "lee"
          and kw2["rollen"]["Luv"] == "seite")
    close("−y: Summe y = −(Luv + Lee) mit h/d = h/b", kw2["kontrolle"]["F"][1],
          -(wm.cpe_luv(h / b) - wm.cpe_lee(h / b)) * qp * d * h, 1e-9, "N")
    # Speichern
    m2 = Model.from_dict(json.loads(json.dumps(m.to_dict())))
    check("Generierer ueberleben Speichern", set(m2.winde) == {"W1", "W2"} and m2.winde["W1"].c_pi == 0.2)
    m2.lasten_verteilen()
    close("nach dem Laden gleiche Summe", wm.kontrollsumme(m2, m2.winde["W1"])["F"][2],
          F_dach + 0.2 * qp * b * d, 1e-9, "N")
    text = wm.erlaeuterung(w, kw)
    check("Erläuterung nennt Zonen und q_p", any("c_pe,D" in t for t in text) and any("q_p" in t for t in text))
    svg = wm.skizze_svg(w, kw)
    check("Skizze: Höhenprofil und Grundriss", svg.startswith("<svg") and "Grundriss" in svg and "D +0.80" in svg)


def test_staebe():
    m = Model("Mast")
    m.add_material(Material("S"))
    sec = Section.pipe("CHS", 0.2, 0.006)
    m.add_section(sec)
    n = 6
    ids = [m.add_node(0, 0, i * 1.0) for i in range(n + 1)]
    el = [m.add_element("beam", [ids[i], ids[i + 1]], "S", "CHS") for i in range(n)]
    m.members["Mast"] = Member("Mast", el)
    m.fix(ids[0], "all")
    w = Wind("W", zone=3, profil="II", richtung=[1, 0, 0], staebe=["Mast"])
    kw = wm.lasten_erzeugen(m, w)
    sb = kw["staebe"][0]
    v = math.sqrt(2 * q_p(3.0, w) / RHO)
    close("Re aus q_p in halber Höhe", sb["Re"], 0.2 * v / 15e-6, 1e-12)
    close("b_ref = Durchmesser", sb["b_ref"], 0.2, 1e-12)
    close("λ = 2 l/b = 60", sb["lambda"], 60.0, 1e-12)
    cf0 = wm.cf0_zylinder(sb["Re"], 0.2e-3 / 0.2)
    close("c_f = c_f,0 ψ_λ", sb["cf"], cf0 * wm.psi_lambda(60.0, 1.0), 1e-12)
    close("w am Kopf = c_f q_p(6) b", sb["w2"], sb["cf"] * q_p(6.0, w) * 0.2, 1e-12, "N/m")
    lc = m.load_cases[w.lastfall]
    check("Linienlast am Stab, trapezförmig, global x",
          len(lc.linienlasten) == 1 and lc.linienlasten[0].system == "global"
          and abs(lc.linienlasten[0].q[0] - sb["w1"]) < 1e-9 and abs(lc.linienlasten[0].q2[0] - sb["w2"]) < 1e-9)
    close("Summe der Elementlasten = mittlere Last mal Länge", kw["kontrolle"]["F_staebe"], sb["F"], 1e-9, "N")
    # Wind parallel zum Stab: keine Last
    w.richtung = [0, 0, 1]
    try:
        wm.lasten_erzeugen(m, w)
        check("senkrechte Anströmung wird abgewiesen (horizontal angeben)", False)
    except ValueError:
        check("senkrechte Anströmung wird abgewiesen (horizontal angeben)", True)
    # Rechteckstab d/b = 2 quer zum Wind mit Vorgabe c_f
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    for e in el:
        m.elements[e].sec = "R"
    w = Wind("R", zone=2, profil="II", richtung=[1, 0, 0], staebe=["Mast"], cf_vorgabe=1.5)
    kw = wm.lasten_erzeugen(m, w)
    close("Vorgabe c_f,0 = 1,5, b_ref = 0,2", kw["staebe"][0]["cf0"], 1.5, 1e-12)
    w.cf_vorgabe = None
    kw = wm.lasten_erzeugen(m, w)
    close("Rechteck d/b = 0,5: c_f,0 nach Bild 7.23", kw["staebe"][0]["cf0"], wm.cf0_rechteck(0.5), 1e-12)


def main():
    for t in (test_profil, test_beiwerte, test_gebaeude, test_staebe):
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
