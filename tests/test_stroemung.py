"""
Strömungsnumerik im Schnitt: Potentialströmung (Kanal, geschlossener und
unter-/überströmter Verschluss gegen geschlossene Lösungen), Gitter-Boltzmann
(Staupunkt, Nachlauf, Verschattung), Rasterung, Abtastung, Bild, Abbruch.
Aufruf:  python -m tests.test_stroemung
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from statik3d import stroemung as st  # noqa: E402

RESULTS = []
RHO, G = 1000.0, 9.81


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:66s} {detail}")
    return ok


def close(name, got, want, tol, unit=""):
    got, want = float(got), float(want)
    err = abs(got - want) / (abs(want) if abs(want) > 1e-12 else 1.0)
    return check(name, err <= tol, f"num={got:.6g} ana={want:.6g} Abw={err * 100:.4f}% {unit}")


def _verschluss(sch, z_uk, z_ok, i0=60, dicke=3):
    X, Z = sch.mitten()
    v = np.zeros((sch.nz, sch.nx), bool)
    v[:, i0:i0 + dicke] = (Z[:, i0:i0 + dicke] >= z_uk) & (Z[:, i0:i0 + dicke] <= z_ok)
    return v


def test_potential():
    nz, nx, h = 20, 60, 0.1
    fluid = np.ones((nz, nx), bool)
    fluss = np.zeros((nz, nx))
    U = 0.7
    fluss[:, 0] -= U * h
    fluss[:, -1] += U * h
    phi = st.potential(fluid, fluss)
    u, w = st.geschwindigkeit(phi, fluid, h)
    close("Kanal ohne Hindernis: u = U überall (min)", u.min(), U, 1e-9)
    close("Kanal ohne Hindernis: u = U überall (max)", u.max(), U, 1e-9)
    check("Kanal: keine Quergeschwindigkeit", abs(w).max() < 1e-9, f"{abs(w).max():.2e}")
    # zwei getrennte Gebiete: je eines festgehalten, loesbar
    fl2 = fluid.copy()
    fl2[:, 30] = False
    phi2 = st.potential(fl2, np.zeros((nz, nx)))
    check("zwei getrennte Gebiete ohne Fluss: φ = 0, endlich", np.isfinite(phi2[fl2]).all()
          and abs(phi2[fl2]).max() < 1e-9)


def test_wasser_geschlossen():
    h_ow, z_uk, z_ok = 4.0, 0.0, 5.0
    sch = st.Schnitt([0, 0, 0], [1, 0, 0], [0, 0, 1], 0.1, 120, 60)
    ver = _verschluss(sch, z_uk, z_ok)
    f = st.wasserdruck_feld(sch, ver, h_ow=h_ow, h_uw=None, z_uk=z_uk, z_ok=z_ok)
    close("geschlossen: F = ½ ρ g h² je m", f["F_je_m"], 0.5 * RHO * G * h_ow ** 2, 1e-9, "N/m")
    close("geschlossen: Angriffspunkt h/3", f["z_R"], h_ow / 3.0, 2e-3, "m")
    check("geschlossen: kein Fluss, keine Geschwindigkeit", f["q"] == 0.0 and f["v_max"] < 1e-9)
    close("groesster Druck an der Sohle (Zellmitte 0,05 m)", f["p_max"], RHO * G * (h_ow - 0.05), 1e-9, "Pa")
    check("über dem Wasserspiegel und im Verschluss kein Druck (NaN)",
          np.isnan(f["p"][~f["fluid"]]).all() and np.isfinite(f["p"][f["fluid"]]).all())
    f2 = st.wasserdruck_feld(sch, ver, h_ow=h_ow, h_uw=2.0, z_uk=z_uk, z_ok=z_ok)
    close("mit Unterwasser: F = ½ ρ g (h_ow² − h_uw²)", f2["F_je_m"], 0.5 * RHO * G * (16.0 - 4.0), 1e-9, "N/m")
    close("mit Unterwasser: Hebel (h_ow³ − h_uw³)/(3 (h_ow² − h_uw²))", f2["z_R"], 56.0 / 36.0, 2e-3, "m")
    # Druckprofil an der Oberwasserseite ist hydrostatisch
    prof = dict((round(z, 3), p) for z, p in f["profil"])
    close("Profil bei z = 1,05: ρ g (h − z)", prof[1.05], RHO * G * (h_ow - 1.05), 1e-9, "Pa")


def test_wasser_unterstroemt():
    sch = st.Schnitt([0, 0, -0.5], [1, 0, 0], [0, 0, 1], 0.1, 120, 65)
    ver = _verschluss(sch, 0.5, 5.5)
    f = st.wasserdruck_feld(sch, ver, h_ow=4.5, h_uw=None, z_uk=0.5, z_ok=5.5, unterstroemt=True,
                            spalt=0.5, mu_a=0.61)
    a = 0.5
    dh = 4.5 - 0.61 * a
    q_soll = 0.61 * a * math.sqrt(2 * G * dh)
    close("unterströmt: Abfluss nach Torricelli mit Kontraktion", f["q"], q_soll, 1e-12)
    check("Massenbilanz: Zufluss = Abfluss (U · Tiefe = q)", abs(f["U"] * 4.5 - f["q"]) < 1e-9,
          f"U={f['U']:.4f}")
    prof = dict((round(z, 3), p) for z, p in f["profil"])
    p_lip, p_hoch = prof[0.55], prof[2.55]
    check("an der Unterkante ist der Druck gegenüber hydrostatisch abgesenkt",
          0.0 < p_lip < 0.85 * RHO * G * 4.0, f"{p_lip:.0f} Pa von {RHO * G * 4.0:.0f}")
    check("zwei Meter über der Unterkante fast hydrostatisch",
          abs(p_hoch - RHO * G * 2.0) < 0.05 * RHO * G * 2.0, f"{p_hoch:.0f} Pa von {RHO * G * 2.0:.0f}")
    check("Resultierende kleiner als hydrostatisch, aber über 90 %",
          0.9 * 0.5 * RHO * G * 16.0 < f["F_je_m"] < 0.5 * RHO * G * 16.0, f"{f['F_je_m']:.0f}")
    check("größte Geschwindigkeit nahe der Strahlgeschwindigkeit", 0.7 * f["v_a"] < f["v_max"] <= 1.05 * f["v_a"],
          f"v_max={f['v_max']:.2f}, v_a={f['v_a']:.2f}")
    # Unterwasser ertraenkt den Strahl: Abfluss am rechten Rand, Netto kleiner
    f2 = st.wasserdruck_feld(sch, ver, h_ow=4.5, h_uw=2.0, z_uk=0.5, z_ok=5.5, unterstroemt=True,
                             spalt=0.5, mu_a=0.61)
    check("ertränkter Strahl: Netto-Resultierende kleiner als ohne Unterwasser", 0 < f2["F_je_m"] < f["F_je_m"])


def test_wasser_ueberstroemt():
    sch = st.Schnitt([0, 0, 0], [1, 0, 0], [0, 0, 1], 0.1, 120, 60)
    ver = _verschluss(sch, 0.0, 5.0)
    f = st.wasserdruck_feld(sch, ver, h_ow=6.0, h_uw=None, z_uk=0.0, z_ok=5.0, ueberstroemt=True, mu_ue=0.62)
    close("überströmt: Abfluss nach Poleni", f["q"], 2.0 / 3.0 * 0.62 * math.sqrt(2 * G) * 1.0, 1e-12)
    prof = dict((round(z, 3), p) for z, p in f["profil"])
    p_krone = prof[4.95]
    check("Druck an der Krone zwischen ⅔ ρ g h_ü (Naudascher) und ρ g h_ü (hydrostatisch)",
          0.6 * RHO * G * 1.05 <= p_krone <= 1.0 * RHO * G * 1.05, f"{p_krone:.0f} Pa")
    check("tief unten hydrostatisch", abs(prof[1.05] - RHO * G * (6.0 - 1.05)) < 0.03 * RHO * G * 4.95,
          f"{prof[1.05]:.0f}")


def test_gitter_boltzmann():
    blk = np.zeros((60, 160), bool)
    blk[24:36, 40:52] = True
    lb = st.gitter_boltzmann(blk, u_lb=0.08, re=100, schritte=1200)
    cp = lb["cp"]
    vorn = float(np.nanmean(cp[26:34, 38]))
    hinten = float(np.nanmean(cp[26:34, 53]))
    check("Staupunkt vor dem Hindernis: c_p ≈ 1", 0.6 < vorn < 1.2, f"{vorn:.2f}")
    check("Nachlauf hinter dem Hindernis: Sog", hinten < -0.2, f"{hinten:.2f}")
    check("Rückströmung im Nachlauf (Verwirbelung)", float(np.nanmean(lb["ux"][26:34, 60])) < 0.2,
          f"{float(np.nanmean(lb['ux'][26:34, 60])):.2f}")
    check("weit hinten wieder Anströmung", 0.8 < float(np.nanmean(lb["ux"][26:34, 150])) < 1.1)
    check("τ ≥ 0,52 gehalten, Re wirksam gemeldet", lb["tau"] >= 0.52 and lb["re"] > 0, f"τ={lb['tau']:.3f}")
    # Verschattung: zweiter Koerper im Nachlauf sieht weniger Staudruck
    blk2 = blk.copy()
    blk2[24:36, 70:82] = True
    lb2 = st.gitter_boltzmann(blk2, u_lb=0.08, re=100, schritte=1200)
    vorn2 = float(np.nanmean(lb2["cp"][26:34, 68]))
    check("Verschattung: der zweite Körper im Nachlauf hat deutlich weniger Staudruck", vorn2 < 0.5 * vorn,
          f"{vorn2:.2f} gegen {vorn:.2f}")


def test_rastern_abtasten_bild():
    sch = st.Schnitt([0, 0, 0], [1, 0, 0], [0, 0, 1], 0.1, 120, 60)
    # senkrechte Platte bei x = 6 als zwei Dreiecke (y-z-Ebene)
    tris = [np.array([[6.0, 0.0, 0.0], [6.0, 3.0, 0.0], [6.0, 3.0, 5.0]]),
            np.array([[6.0, 0.0, 0.0], [6.0, 3.0, 5.0], [6.0, 0.0, 5.0]])]
    b = st.rastern(sch, tris)
    # die Oberkante z = 5,0 liegt genau auf einer Zellgrenze: 50 oder 51 Zellen
    check("Platte rastert eine Spalte von z = 0 bis 5", b[:, 60].sum() in (50, 51) and b[:, 59].sum() == 0
          and b[:, 61].sum() == 0, str((b[:, 60].sum(), b[:, 59].sum(), b[:, 61].sum())))
    v = st.verdicken(b)
    check("verdickt: drei Spalten", v[:, 59].sum() == b[:, 60].sum() and v[:, 61].sum() == b[:, 60].sum()
          and v[:, 62].sum() == 0)
    # schraege Platte bleibt dicht (keine diagonalen Loecher)
    tris2 = [np.array([[3.0, 0.0, 0.0], [3.0, 3.0, 0.0], [7.0, 3.0, 5.0]]),
             np.array([[3.0, 0.0, 0.0], [7.0, 3.0, 5.0], [7.0, 0.0, 5.0]])]
    b2 = st.verdicken(st.rastern(sch, tris2))
    check("schräge Platte: jede Zeile belegt", all(b2[k, :].any() for k in range(50)))
    f = st.wasserdruck_feld(sch, v, h_ow=4.0, h_uw=None, z_uk=0.0, z_ok=5.0)
    p1 = st.wert_am_punkt(f["p"], f["fluid"], sch, [6.0, 1.0, 1.0], normale=[-1, 0, 0], beidseitig=True)
    close("Abtastung vor der Oberwasserseite: ρ g (h − z) (Zellmitte)", p1, RHO * G * (4.0 - 1.05), 1e-9, "Pa")
    p2 = st.wert_am_punkt(f["p"], f["fluid"], sch, [6.0, 1.0, 1.0], normale=[1, 0, 0], beidseitig=True)
    close("dünne Schale, Normale nach hinten: Netto negativ (Wasser drückt von hinten)", p2,
          -RHO * G * (4.0 - 1.05), 1e-9, "Pa")
    p3 = st.wert_am_punkt(f["p"], f["fluid"], sch, [6.0, 1.0, 1.0], normale=[1, 0, 0], beidseitig=False)
    check("Volumenseite nach hinten (trocken): kein Druck", p3 == 0.0)
    check("über dem Wasser kein Druck", st.wert_am_punkt(f["p"], f["fluid"], sch, [6.0, 1.0, 4.5],
                                                            normale=[-1, 0, 0]) == 0.0)
    svg = st.feld_svg(sch, f["p"], f["fluid"], f["block"], "wasser", titel="Test",
                      linien=[((0, 4.0), (6.0, 4.0), "#1467c6")], texte=[((0.1, 4.0), "OW", "#1467c6")])
    check("Feldbild als SVG mit eingebettetem PNG und Farbskala", svg.startswith("<svg")
          and "data:image/png;base64" in svg and "kN/m²" in svg and "OW" in svg)
    d = st.feld_packen(sch, f["p"], f["fluid"], f["block"], stempel="abc")
    s = json.dumps(d)
    sch2, p2_, fl2, bl2 = st.feld_entpacken(json.loads(s))
    check("Feld packen/entpacken über JSON verlustfrei (0,1 Pa)",
          np.allclose(np.nan_to_num(p2_), np.nan_to_num(np.round(f["p"], 1)))
          and (fl2 == f["fluid"]).all() and (bl2 == f["block"]).all() and sch2.nx == sch.nx, f"{len(s) // 1024} kB")


def test_abbruch():
    sch = st.Schnitt([0, 0, 0], [1, 0, 0], [0, 0, 1], 0.1, 120, 60)
    ver = _verschluss(sch, 0.0, 5.0)
    rufe = []

    def fortschritt(anteil, text):
        rufe.append((anteil, text))
        return len(rufe) < 2

    try:
        st.wasserdruck_feld(sch, ver, h_ow=4.0, h_uw=None, z_uk=0.0, z_ok=5.0, fortschritt=fortschritt)
        check("Abbruch über den Fortschrittsrückruf", False)
    except st.Abgebrochen:
        check("Abbruch über den Fortschrittsrückruf", True, str(len(rufe)))
    rufe.clear()
    try:
        st.gitter_boltzmann(np.zeros((30, 60), bool) | False, schritte=200,
                            fortschritt=lambda a, t: (rufe.append(a), False)[1])
        check("Windkanal: Abbruch", False)
    except st.Abgebrochen:
        check("Windkanal: Abbruch", True)
    voll = []
    st.wasserdruck_feld(sch, ver, h_ow=4.0, h_uw=None, z_uk=0.0, z_ok=5.0,
                        fortschritt=lambda a, t: (voll.append(a), True)[1])
    check("Fortschritt steigt monoton bis 0,75", voll == sorted(voll) and abs(voll[-1] - 0.75) < 1e-9, str(voll))


def main():
    for f in (test_potential, test_wasser_geschlossen, test_wasser_unterstroemt, test_wasser_ueberstroemt,
              test_gitter_boltzmann, test_rastern_abtasten_bild, test_abbruch):
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
