"""
Verifikation des Spannungsnachweises fuer Volumenbereiche nach
DIN EN 1993-1-1, 6.2.1(5).

Geprueft wird gegen geschlossene Loesungen:

  * einachsiger Zug: sigma_v = N/A, sigma_1 = N/A, sigma_2 = sigma_3 = 0
  * reiner Schub: sigma_v = sqrt(3) tau, Hauptspannungen +-tau
  * hydrostatischer Druck: sigma_v = 0, obwohl die Spannungen gross sind
  * Tresca gegen von Mises: Verhaeltnis 1,0 bei einachsig, 2/sqrt(3) bei Schub
  * Mehrachsigkeit h = sigma_m/sigma_v und die Erkennung dreiachsigen Zugs
  * Biegung durch einen Volumenkoerper: die Randspannung an den Eckpunkten
    trifft M/W, die Elementmitte allein laege rund 28 % darunter

Aufruf:  python -m tests.test_volumen
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material                       # noqa: E402
from statik3d import solver                                      # noqa: E402
from statik3d.ec3 import volumen as V                            # noqa: E402

RESULTS = []


def check(name, ok, info=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {info}")
    return ok


def close(name, got, want, tol, unit=""):
    err = abs(got - want)
    rel = err / abs(want) if want else err
    return check(name, rel <= tol,
                 f"{got:.6g}{unit} / {want:.6g}{unit}  Abw. {rel * 100:.4f} %")


# --------------------------------------------------------------------------
def zugkoerper(a=0.1, b=0.1, L=0.4, nx=2, ny=2, nz=8, N=2500e3):
    """Quader unter Gleichlast, Symmetrierandbedingungen: einachsiger Zug."""
    m = Model("Zugkoerper")
    m.add_material(Material.steel("S355"))
    ids = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                ids[(i, j, k)] = m.add_node(a * i / nx, b * j / ny, L * k / nz)
    els = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                els.append(m.add_element("hex8", [
                    ids[(i, j, k)], ids[(i + 1, j, k)], ids[(i + 1, j + 1, k)],
                    ids[(i, j + 1, k)], ids[(i, j, k + 1)], ids[(i + 1, j, k + 1)],
                    ids[(i + 1, j + 1, k + 1)], ids[(i, j + 1, k + 1)]], "S355"))
    for k in range(nz + 1):
        for j in range(ny + 1):
            m.fix(ids[(0, j, k)], [0])          # Symmetrie x = 0
        for i in range(nx + 1):
            m.fix(ids[(i, 0, k)], [1])          # Symmetrie y = 0
    for j in range(ny + 1):
        for i in range(nx + 1):
            m.fix(ids[(i, j, 0)], [2])
    # konsistente Knotenlasten einer Gleichlast auf dem Raster: 1 : 2 : 4
    def w(i, n):
        return 1 if i in (0, n) else 2
    tot = sum(w(i, nx) * w(j, ny) for j in range(ny + 1) for i in range(nx + 1))
    for j in range(ny + 1):
        for i in range(nx + 1):
            m.load_node(ids[(i, j, nz)], Fz=N * w(i, nx) * w(j, ny) / tot)
    m.add_combination("K1", {list(m.load_cases)[0]: 1.0}, typ="ULS")
    return m, els, N / (a * b)


def test_spannungsformeln():
    """Die Kernfunktionen gegen die Lehrbuchwerte."""
    # einachsiger Zug
    d = V.punkt_nachweis([100e6, 0, 0, 0, 0, 0], 355e6, 1.0)
    close("σ_v bei einachsigem Zug = σ", d["sigma_v"], 100e6, 1e-12, " Pa")
    close("σ_1", d["s1"], 100e6, 1e-12, " Pa")
    check("σ_2 = σ_3 = 0", abs(d["s2"]) < 1e-6 and abs(d["s3"]) < 1e-6)
    close("τ_max = σ/2", d["tau_max"], 50e6, 1e-12, " Pa")
    close("Tresca = von Mises bei einachsig", d["eta_tresca"], d["eta"], 1e-12)
    close("h = σ_m/σ_v = 1/3", d["h"], 1 / 3, 1e-12)

    # reiner Schub
    tau = 60e6
    d2 = V.punkt_nachweis([0, 0, 0, tau, 0, 0], 355e6, 1.0)
    close("σ_v bei reinem Schub = √3 τ", d2["sigma_v"], math.sqrt(3) * tau, 1e-12, " Pa")
    close("σ_1 = +τ", d2["s1"], tau, 1e-9, " Pa")
    close("σ_3 = −τ", d2["s3"], -tau, 1e-9, " Pa")
    close("Tresca/Mises bei Schub = 2/√3", d2["eta_tresca"] / d2["eta"],
          2 / math.sqrt(3), 1e-9)
    check("h = 0 bei reinem Schub", abs(d2["h"]) < 1e-9, f"{d2['h']:.3e}")

    # hydrostatischer Druck: keine Gestaltaenderung
    p = 300e6
    d3 = V.punkt_nachweis([-p, -p, -p, 0, 0, 0], 355e6, 1.0)
    check("σ_v = 0 bei hydrostatischem Druck", d3["sigma_v"] < 1e-6,
          f"{d3['sigma_v']:.3e} Pa bei σ = -300 N/mm²")
    check("und die Ausnutzung ist null", d3["eta"] < 1e-9)

    # dreiachsiger Zug
    d4 = V.punkt_nachweis([200e6, 180e6, 160e6, 0, 0, 0], 355e6, 1.0)
    check("dreiachsiger Zug wird erkannt", d4["dreiachsiger_zug"])
    check("und als kritisch bewertet (h > 1/3)", d4["kritisch"],
          f"h = {d4['h']:.2f}")
    close("σ_v aus den Hauptspannungen", d4["sigma_v"],
          math.sqrt(0.5 * ((200 - 180) ** 2 + (180 - 160) ** 2
                           + (160 - 200) ** 2)) * 1e6, 1e-9, " Pa")
    # Rechenrauschen ist kein dreiachsiger Zug
    d5 = V.punkt_nachweis([100e6, 1e-8, 1e-8, 0, 0, 0], 355e6, 1.0)
    check("numerisches Rauschen gilt nicht als dreiachsiger Zug",
          not d5["dreiachsiger_zug"], f"σ_3 = {d5['s3']:.3e} Pa")

    # gamma_M0 geht ein
    d6 = V.punkt_nachweis([100e6, 0, 0, 0, 0, 0], 355e6, 1.1)
    close("η mit γ_M0 = 1,1", d6["eta"], 100e6 / (355e6 / 1.1), 1e-12)

    # Hauptrichtungen
    w_, vecs = V.hauptrichtungen([100e6, 0, 0, 0, 0, 0])
    close("größte Hauptspannung", float(w_[0]), 100e6, 1e-9, " Pa")
    check("die zugehörige Richtung ist x",
          abs(abs(float(vecs[0, 0])) - 1.0) < 1e-9, str(np.round(vecs[:, 0], 3)))


def test_zugkoerper():
    """Einachsiger Zug im Modell gegen N/A."""
    m, els, soll = zugkoerper()
    m.add_volumenbereich("Schaft", els, beschreibung="Zugkörper 100 x 100")
    an = solver.solve_all(m, design=True)
    check("die Volumennachweise laufen mit der Berechnung",
          an.volumen is not None and "Schaft" in an.volumen.bereiche)
    c = an.volumen.bereiche["Schaft"]
    w = c.werte
    close("σ_v trifft N/A", w["sigma_v"], soll, 1e-9, " Pa")
    close("σ_1 = N/A", w["s1"], soll, 1e-9, " Pa")
    check("σ_2 und σ_3 verschwinden",
          abs(w["s2"]) < 1e-6 * soll and abs(w["s3"]) < 1e-6 * soll,
          f"σ_2 = {w['s2'] / 1e6:.2e}, σ_3 = {w['s3'] / 1e6:.2e} MPa")
    close("Ausnutzung σ_v/(f_y/γ_M0)", c.util, soll / (355e6 / m.design.gamma_M0),
          1e-9)
    check("die Spannung ist über den Bereich gleich", abs(w["spitze"] - 1.0) < 1e-6,
          f"Spitze/Mittel = {w['spitze']:.6f}")
    check("kein falscher Hinweis auf dreiachsigen Zug",
          not any("Dreiachsiger Zug" in h for h in c.hinweise), str(c.hinweise)[:60])
    check("Status erfüllt", c.status() == "erfüllt", f"η = {c.util:.3f}")
    check("das maßgebende Element ist benannt", c.element >= 0)

    # Material und Speichern
    check("das Material kommt aus dem Bereich",
          c.material == "S355" and abs(c.fy - 355e6) < 1e-6)
    d = Model.from_dict(m.to_dict())
    check("der Volumenbereich übersteht Speichern und Laden",
          list(d.volumenbereiche) == ["Schaft"]
          and d.volumenbereiche["Schaft"].elemente == els)
    check("und die Modellkopie",
          m.copy().volumenbereiche["Schaft"].beschreibung.startswith("Zugkörper"))

    # hoehere Last -> Nachweis nicht erfuellt
    m2, els2, soll2 = zugkoerper(N=4000e3)
    m2.add_volumenbereich("Schaft", els2)
    an2 = solver.solve_all(m2, design=True)
    c2 = an2.volumen.bereiche["Schaft"]
    check("bei 400 N/mm² ist der Nachweis nicht erfüllt",
          c2.util > 1.0 and c2.status() == "NICHT erfüllt",
          f"σ_v = {c2.werte['sigma_v'] / 1e6:.1f} N/mm², η = {c2.util:.3f}")
    check("die Zusammenfassung nennt es",
          "NICHT erfüllt" in an2.volumen.summary(), an2.volumen.summary()[:90])


def biegebalken(b=0.05, h=0.10, L=1.0, nx=20, nz=4, P=5e3):
    """Kragarm aus Hexaedern: die Randspannung muss M/W treffen."""
    m = Model("Biegebalken")
    m.add_material(Material.steel("S355"))
    ids = {}
    for k in range(nz + 1):
        for j in range(2):
            for i in range(nx + 1):
                ids[(i, j, k)] = m.add_node(L * i / nx, b * j, h * k / nz)
    els = []
    for k in range(nz):
        for i in range(nx):
            els.append(m.add_element("hex8", [
                ids[(i, 0, k)], ids[(i + 1, 0, k)], ids[(i + 1, 1, k)], ids[(i, 1, k)],
                ids[(i, 0, k + 1)], ids[(i + 1, 0, k + 1)], ids[(i + 1, 1, k + 1)],
                ids[(i, 1, k + 1)]], "S355"))
    for k in range(nz + 1):
        for j in range(2):
            m.fix(ids[(0, j, k)], "all")
    for j in range(2):
        m.load_node(ids[(nx, j, nz)], Fz=-P / 4)
        m.load_node(ids[(nx, j, 0)], Fz=-P / 4)
    m.add_combination("K1", {list(m.load_cases)[0]: 1.0}, typ="ULS")
    return m, els, P * L / (b * h ** 2 / 6)


def test_randspannung():
    """Die Spannung wird an Mitte UND Eckpunkten ausgewertet."""
    from statik3d.elements import solid as sl
    m, els, soll = biegebalken()
    m.add_volumenbereich("Balken", els)
    an = solver.solve_all(m, design=True)
    c = an.volumen.bereiche["Balken"]
    check("der Auswertepunkt steht im Ergebnis", "punkt" in c.werte,
          str(c.werte.get("punkt")))

    # freies Feld (weit weg von der Einspannung): dort muss M/W stehen
    res = an.combinations["K1"]
    u = np.asarray(res.u).ravel()
    mat = m.materials["S355"]
    mitte_max = rand_max = 0.0
    x_soll = 0.0
    for i in els:
        e = m.elements[i]
        X = np.asarray(m.nodes[e.nodes], float)
        x = float(X[:, 0].mean())
        if not 0.2 * 1.0 < x < 0.3 * 1.0:      # freies Feld
            continue
        ue = np.concatenate([u[int(n) * 6:int(n) * 6 + 3] for n in e.nodes])
        sp = sl.stress_points("hex8", X, mat.E, mat.nu, ue)
        sv = [V.vergleichsspannung(q) for q in sp]
        if max(sv) > rand_max:
            rand_max, mitte_max, x_soll = max(sv), sv[0], x
    M = 5e3 * (1.0 - x_soll)
    s_soll = M / (0.05 * 0.10 ** 2 / 6)
    close("Randspannung im freien Feld trifft M/W", rand_max, s_soll, 0.03, " Pa")
    check("die Elementmitte allein läge deutlich darunter",
          mitte_max < 0.85 * s_soll,
          f"Mitte {mitte_max / 1e6:.1f} gegen Rand {rand_max / 1e6:.1f} "
          f"und M/W {s_soll / 1e6:.1f} N/mm²")
    check("der Nachweis nimmt den Randwert", c.werte["sigma_v"] >= rand_max,
          f"σ_v = {c.werte['sigma_v'] / 1e6:.1f} ≥ {rand_max / 1e6:.1f} N/mm²")

    # Auswertepunkte je Elementtyp
    check("Hexaeder wird an 9 Punkten ausgewertet",
          len(sl.AUSWERTEPUNKTE["hex8"]) == 9)
    check("Tet4 ist konstant, ein Punkt genügt",
          len(sl.AUSWERTEPUNKTE["tet4"]) == 1)
    check("Tet10 an Mitte und vier Ecken",
          len(sl.AUSWERTEPUNKTE["tet10"]) == 5)
    # bei gleichmaessiger Spannung sind alle Punkte gleich
    m2, els2, soll2 = zugkoerper()
    an2 = solver.solve_all(m2, design=True)
    e2 = m2.elements[els2[0]]
    X2 = np.asarray(m2.nodes[e2.nodes], float)
    u2 = np.asarray(an2.combinations["K1"].u).ravel()
    ue2 = np.concatenate([u2[int(n) * 6:int(n) * 6 + 3] for n in e2.nodes])
    sv2 = [V.vergleichsspannung(q) for q in
           sl.stress_points("hex8", X2, m2.materials["S355"].E,
                            m2.materials["S355"].nu, ue2)]
    check("bei Gleichspannung liefern alle Punkte dasselbe",
          max(sv2) - min(sv2) < 1e-6 * max(sv2),
          f"{min(sv2) / 1e6:.4f} … {max(sv2) / 1e6:.4f} N/mm²")


def test_fehlerfaelle():
    m, els, _soll = zugkoerper()
    try:
        m.add_volumenbereich("X", [])
        check("leerer Bereich wird abgewiesen", False)
    except ValueError:
        check("leerer Bereich wird abgewiesen", True)
    try:
        m.add_volumenbereich("Z", [len(m.elements) + 5])
        check("unbekanntes Element wird abgewiesen", False)
    except IndexError:
        check("unbekanntes Element wird abgewiesen", True)
    # Schalenelement ist kein Volumen (eigenes Modell, damit die Rechnung
    # unten nicht ueber das Zusatzelement stolpert)
    from statik3d.model import ShellProp
    ms = Model("Schale")
    ms.add_material(Material.steel("S355"))
    ms.add_shell_prop(ShellProp("t", 0.01))
    n = [ms.add_node(0.0, 0.0, 0.0), ms.add_node(1.0, 0.0, 0.0),
         ms.add_node(0.0, 1.0, 0.0)]
    sh = ms.add_element("shell3", n, "S355", "t")
    try:
        ms.add_volumenbereich("Y", [sh])
        check("Flächenelement wird abgewiesen", False)
    except ValueError:
        check("Flächenelement wird abgewiesen", True)

    # Nachweis ausgeschaltet
    m.add_volumenbereich("Aus", els, design=False)
    an = solver.solve_all(m, design=True)
    c = an.volumen.bereiche["Aus"]
    check("ausgeschalteter Bereich wird nicht geführt",
          c.status() == "nicht geführt" and "ausgeschaltet" in c.fehler, c.fehler)

    # als singulaer gekennzeichnet: nur berichtet
    m2, els2, _s = zugkoerper()
    m2.add_volumenbereich("Kerbe", els2, singular=True)
    an2 = solver.solve_all(m2, design=True)
    c2 = an2.volumen.bereiche["Kerbe"]
    check("singulärer Bereich wird nur berichtet",
          c2.status() == "nur berichtet" and c2.werte.get("sigma_v", 0) > 0,
          f"σ_v = {c2.werte.get('sigma_v', 0) / 1e6:.1f} N/mm²")
    check("und das steht als Hinweis dabei",
          any("singulär" in h for h in c2.hinweise), str(c2.hinweise)[:70])
    check("die Zusammenfassung nennt es",
          "nur berichtet" in an2.volumen.summary(), an2.volumen.summary()[:100])

    # zu grobes Netz gegen den Kerbradius
    m3, els3, _s3 = zugkoerper()
    m3.add_volumenbereich("Kerbe", els3, ausrundung=0.005)
    an3 = solver.solve_all(m3, design=True)
    c3 = an3.volumen.bereiche["Kerbe"]
    check("zu grobes Netz am Kerbradius wird benannt",
          any("zu grob" in h for h in c3.hinweise), str(c3.hinweise)[-90:])


def test_bericht():
    from statik3d.report import Report
    m, els, soll = zugkoerper()
    m.add_volumenbereich("Schaft", els, beschreibung="Bolzenauge, Schaft 100 x 100")
    an = solver.solve_all(m, design=True)
    html = Report(m, an).html()
    for text in ("Spannungsnachweise der Volumenbereiche",
                 "Volumenbereich Schaft", "von Mises", "Hauptspannungen σ_1 / σ_2 / σ_3",
                 "Mehrachsigkeit h = σ_m/σ_v", "Vergleich nach Tresca",
                 "DIN EN 1993-1-10", "Stabilität des Volumenkörpers",
                 "Spitzenspannung / Mittel", "Auswertepunkt",
                 "Mitte und an den Eckpunkten"):
        check(f"Bericht nennt „{text}“", text in html)
    check("Zusammenfassung nennt die Volumen",
          "Volumen (EN 1993-1-1, 6.2.1(5))" in an.summary())

    # ohne Bereiche kein Kapitel
    m2, _e2, _s2 = zugkoerper()
    an2 = solver.solve_all(m2, design=True)
    h2 = Report(m2, an2).html()
    check("ohne Volumenbereiche fehlt das Kapitel",
          "Spannungsnachweise der Volumenbereiche" not in h2)
    check("und es wird auch nichts behauptet",
          "Volumenbereich" not in h2)


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Volumennachweise (DIN EN 1993-1-1, 6.2.1(5))")
    print("=" * 92)
    for t in (test_spannungsformeln, test_zugkoerper, test_randspannung,
              test_fehlerfaelle, test_bericht):
        print()
        t()
    ok = sum(1 for _n, o in RESULTS if o)
    print()
    print("=" * 92)
    print(f"Ergebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    bad = [n for n, o in RESULTS if not o]
    if bad:
        print("FEHLGESCHLAGEN:", bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
