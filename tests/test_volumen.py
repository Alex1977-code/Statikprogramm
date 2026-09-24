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
    # **335, nicht 355.** Der Prüfkörper ist ein Stab 100 x 100 mm; seine
    # Erzeugnisdicke ist damit 100 mm, und über 40 mm gilt für S355 nach
    # EN 1993-1-1 Tab. 3.1 nicht mehr 355 N/mm², sondern 335. Bis zum
    # 22.09.2026 stand hier 355e6: der Nachweis rechnete immer mit der
    # dünnsten Stufe und fiel damit **6,0 % zu günstig** aus. Die Prüfung
    # hielt den Fehler fest - siehe test_erzeugnisdicke_mindert_die_streckgrenze.
    close("f_y von S355 bei 100 mm Erzeugnisdicke",
          m.materials["S355"].yield_strength(0.100), 335e6, 1e-9, " Pa")
    close("Ausnutzung σ_v/(f_y/γ_M0)", c.util, soll / (335e6 / m.design.gamma_M0),
          1e-9)
    close("die angesetzte Erzeugnisdicke steht im Nachweis",
          w.get("dicke", 0.0), 0.100, 1e-9, " m")
    check("und der Bericht sagt, woher sie kommt",
          any("Erzeugnisdicke" in h and "335" in h for h in c.hinweise),
          str([h[:60] for h in c.hinweise]))
    check("die Spannung ist über den Bereich gleich", abs(w["spitze"] - 1.0) < 1e-6,
          f"Spitze/Mittel = {w['spitze']:.6f}")
    check("kein falscher Hinweis auf dreiachsigen Zug",
          not any("Dreiachsiger Zug" in h for h in c.hinweise), str(c.hinweise)[:60])
    check("Status erfüllt", c.status() == "erfüllt", f"η = {c.util:.3f}")
    check("das maßgebende Element ist benannt", c.element >= 0)

    # Material und Speichern
    check("das Material kommt aus dem Bereich",
          c.material == "S355" and abs(c.fy - 335e6) < 1e-6,
          f"{c.material}, f_y = {c.fy / 1e6:.0f} N/mm² (100 mm dick)")
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
    # Was in res.solid_res steht, ist das, was die **Anzeige** zeigt - und was
    # der Fehlerschaetzer des Vernetzers liest. Bis zum 20.09.2026 stand dort
    # die Elementmitte; beim Sechsflaechner unter Biegung ist das der
    # schlechteste Ort, den man waehlen kann (gemessen am Kragtraeger: 71,9 %
    # des Randwerts). Ohne die Aenderung faellt diese Pruefung durch.
    sr_max = 0.0
    for i in els:
        X = np.asarray(m.nodes[m.elements[i].nodes], float)
        if not 0.2 * 1.0 < float(X[:, 0].mean()) < 0.3 * 1.0:
            continue
        sr_max = max(sr_max, V.vergleichsspannung(np.asarray(res.solid_res[i], float)))
    check("res.solid_res trägt den maßgebenden Punkt, nicht die Mitte",
          sr_max >= 0.98 * rand_max,
          f"{sr_max / 1e6:.1f} gegen Rand {rand_max / 1e6:.1f} und Mitte "
          f"{mitte_max / 1e6:.1f} N/mm²")
    # Beim tet4 darf sich nichts aendern: ein Auswertepunkt, konstante
    # Spannung - das Drehlager rechnet mit 645.934 davon.
    m3, els3, _soll3 = zugkoerper()
    res3 = solver.solve_static(m3)
    u3 = np.asarray(res3.u).ravel()
    mat3 = m3.materials[m3.elements[els3[0]].mat]
    schlimmst = 0.0
    for i in els3[:40]:
        e3 = m3.elements[i]
        if e3.typ != "tet4":
            continue
        X3 = np.asarray(m3.nodes[e3.nodes], float)
        ue3 = np.concatenate([u3[int(nn) * 6:int(nn) * 6 + 3] for nn in e3.nodes])
        einzeln = np.asarray(sl.stress_points("tet4", X3, mat3.E, mat3.nu, ue3)[0], float)
        schlimmst = max(schlimmst, float(np.abs(
            einzeln - np.asarray(res3.solid_res[i], float)).max()))
    check("tet4: res.solid_res ist unverändert der eine Auswertepunkt",
          schlimmst <= 1e-6 * max(1.0, abs(_soll3)), f"größte Abweichung {schlimmst:.3e} Pa")

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


def test_elementmittel():
    """res.solid_mittel ist das Elementmittel Integral sigma dV / V.

    Der Fehlerschaetzer liest es (netzfehler.MITTELFELD), wenn der Loeser es
    fuehrt - bis zum 22.09.2026 tat er das nicht, und der Schaetzer bekam fuer
    den elastischen hex8 das Eckmaximum aus solid_res. Bei Gleichspannung
    muss das Mittel N/A sein; unter Biegung liegt es zwischen den Randwerten
    und ist in einer Kombination exakt die Summe der Lastfaelle (linear in u).
    """
    m, els, soll = zugkoerper()
    res = solver.solve_static(m)
    abw = max(abs(float(res.solid_mittel[i][2]) - soll) for i in els) / soll
    check("hex8 unter Gleichzug: Elementmittel = N/A", abw < 1e-9, f"{abw:.1e}")
    m, els, _soll = biegebalken()
    an = solver.solve_all(m)
    res = an.combinations["K1"]
    ok = all(i in res.solid_mittel for i in els)
    innen = [i for i in els if float(np.asarray(m.nodes[m.elements[i].nodes])[:, 0].mean()) > 0.2]
    kleiner = all(V.vergleichsspannung(np.asarray(res.solid_mittel[i]))
                  <= V.vergleichsspannung(np.asarray(res.solid_res[i])) + 1e-6 for i in innen)
    check("hex8 unter Biegung: Mittel fuer jedes Element, nie ueber dem massgebenden Punkt",
          ok and kleiner)
    # K1 = 1,0 * Lastfall: das Mittel der Kombination ist das des Lastfalls
    lf = next(iter(an.cases.values()))
    abw = max(float(np.abs(np.asarray(res.solid_mittel[i]) - np.asarray(lf.solid_mittel[i])).max())
              for i in els)
    check("Kombination: solid_mittel wird mit ueberlagert", abw < 1e-6, f"{abw:.1e} Pa")


def test_randspannung_geglaettet():
    """A4/B6 (22.09.2026): der Nachweis liest die **geglaettete** Eckspannung.

    Kragarm-Pruefkoerper (tests/pruefkoerper.py): Oberkante bei L/2, nach
    Saint-Venant exakt 355 N/mm2. Dort ist ein Knoten; seine geglaettete
    Spannung (Mittel der Elemente gleichen Koerpers und Werkstoffs) trifft
    beim hex8 8x2x4 auf 0,8 N/mm2, beim tet10 8x2x4 auf 4 N/mm2 (quadratisch,
    O(h^2)). Das Elementmaximum, das der Nachweis bis dahin las, lag beim hex8
    um 64 N/mm2 darueber.
    """
    from statik3d.elements import solid as sl
    from tests import pruefkoerper as pk
    kr = pk.Kragarm()
    for typ, netz, tol, alt_min in (("hex8", (8, 2, 4), 1.0, 20.0), ("tet10", (8, 2, 4), 5.0, 20.0)):
        m, ids = kr.modell(typ, *netz)
        res, _t = pk.loese(m)
        nx, ny, nz = netz
        n = ids[(nx // 2, ny // 2, nz)]
        sk = res.solid_knoten
        j = np.flatnonzero(np.asarray(sk["knoten"]) == n)
        sv = sl.von_mises(np.asarray(sk["spannung"])[j[0]]) if len(j) == 1 else float("nan")
        check(f"{typ} {nx}x{ny}x{nz}: geglaettete Spannung am Nachweispunkt auf {tol:g} N/mm2",
              abs(sv - kr.sigma) < tol * 1e6, f"{sv / 1e6:.2f} gegen {kr.sigma / 1e6:.1f} N/mm2")
        am_knoten = [i for i, e in enumerate(m.elements) if n in e.nodes]
        alt = max(sl.von_mises(np.asarray(res.solid_res[i])) for i in am_knoten)
        check(f"{typ}: das Elementmaximum (bisherige Regel) lag deutlich darueber",
              alt - kr.sigma > alt_min * 1e6, f"{alt / 1e6:.1f} N/mm2")
        rand = res.solid_rand
        check(f"{typ}: solid_rand je Element ist die groesste seiner geglaetteten Ecken",
              all(i in rand and sl.von_mises(rand[i][0]) >= sv - 1e-6 for i in am_knoten))
    # Kombination: die Knotenwerte werden ueberlagert
    m, ids = kr.modell("hex8", 4, 1, 2)
    m.add_combination("K2", {list(m.load_cases)[0]: 2.0}, typ="ULS")
    an = solver.solve_all(m)
    lf = next(iter(an.cases.values()))
    ko = an.combinations["K2"]
    check("Kombination 2,0 x Lastfall: Knotenwerte verdoppelt",
          np.allclose(np.asarray(ko.solid_knoten["spannung"]),
                      2.0 * np.asarray(lf.solid_knoten["spannung"]), rtol=1e-9, atol=1e-3))


def test_randspannung_fliessend():
    """Fliessende Elemente tragen ihren naechsten Integrationspunkt bei - der
    liegt auf der Fliessflaeche, eine Ecke schoss frueher darueber hinaus.

    hex8, eine Lage, reine Biegung 1,20 M_el, fuenf Lobatto-Punkte ueber die
    Dicke: die Randfaser nach der Momenten-Kruemmungs-Beziehung traegt 236,35
    N/mm2 (fy 235, E_t/E 2 %). Die geglaettete Spannung der oberen Knoten in
    Feldmitte trifft das auf 1 N/mm2, und kein Knotenwert liegt ueber der
    verfestigten Fliessgrenze des am staerksten gedehnten Punktes.
    """
    from statik3d import plastizitaet as pl
    from statik3d.elements import solid as sl
    from tests import pruefkoerper as pk
    fy, E, r = 235e6, 210e9, 0.02
    b = h = 0.2
    L = 1.0
    M = 1.2 * fy * b * h ** 2 / 6.0
    m, ids = pk.quader("hex8", 5, 1, 1, L, b, h, fy=fy)
    for k in [n for n in range(m.nn) if abs(m.nodes[n, 0]) < 1e-9]:
        m.fix(int(k), "all")
    seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - L) < 1e-9)))
    I = b * h ** 3 / 12
    pk.spannung_auf_seiten(m, seiten, lambda x: (M * (x[2] - h / 2) / I, 0.0, 0.0))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=r, laststufen=1, iterationen=30,
                                     toleranz=1e-9)
    res = solver.solve_static(m)
    sk = res.solid_knoten
    kn = np.asarray(sk["knoten"])
    S = np.asarray(sk["spannung"])
    oben = [ids[(i, j, 1)] for i in (2, 3) for j in (0, 1)]
    sv = [sl.von_mises(S[np.flatnonzero(kn == n)[0]]) for n in oben]
    check("fließend, eine Lage: geglättete Randspannung in Feldmitte auf 1 N/mm²",
          all(abs(v - 236.35e6) < 1e6 for v in sv),
          ", ".join(f"{v / 1e6:.2f}" for v in sv) + " gegen 236,35 N/mm²")
    ep = max(float(np.max(v)) for v in [np.asarray(x) for x in res.info["plastisch"].values()])
    grenze = fy + E * r / (1 - r) * ep
    alle = [sl.von_mises(x) for x in S]
    check("kein Knotenwert über der verfestigten Fließgrenze",
          max(alle) <= grenze * (1 + 1e-9), f"{max(alle) / 1e6:.2f} ≤ {grenze / 1e6:.2f} N/mm²")


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

    # Nachweis ausgeschaltet: gewollt nicht gefuehrt, kein Fehler (B058,
    # Gesamturteil in test_ausgeschalteter_bereich_im_gesamturteil)
    m.add_volumenbereich("Aus", els, design=False)
    an = solver.solve_all(m, design=True)
    c = an.volumen.bereiche["Aus"]
    check("ausgeschalteter Bereich heißt „ausgeschaltet“, nicht „nicht geführt“",
          c.status() == "ausgeschaltet" and getattr(c, "ausgeschaltet", False)
          and not c.fehler, f"{c.status()}, fehler „{c.fehler}“")

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


def test_gesamturteil_reines_volumenmodell():
    """Das Gesamturteil des Berichts an einem Modell **nur aus Volumen**.

    Bis zum 22.09.2026 fehlte der Volumennachweis in der Zusammenfassung des
    Berichts doppelt: in der Statuspruefung und in der Liste der gefuehrten
    Nachweise. Ein Modell ohne Staebe - am Drehlager der Regelfall - bekam
    darum "Es wurden keine Nachweise gefuehrt ..." mit gruener Klasse, auch
    wenn der Volumennachweis riss. test_report prueft den Status nur am
    Balkenmodell mit Stab; dort faellt der fehlende Eintrag in "gefuehrt"
    nicht auf (gemessen 22.09.2026: Volumen aus "gefuehrt" gestrichen, jene
    Pruefung besteht weiter 7/7).

    Zugkoerper 100 x 100 mm, S355, gemessen: N = 4000 kN -> Ausnutzung
    1,194; N = 2500 kN -> 0,746.
    """
    import re
    from statik3d.report import Report

    def status(N):
        m, els, _soll = zugkoerper(N=N)
        m.add_volumenbereich("Schaft", els)
        an = solver.solve_all(m, design=True)
        zeilen = re.findall(r'<div class="status (ok|nok)">(.*?)</div>',
                            Report(m, an).html(), re.S)
        return m, an.volumen.bereiche["Schaft"].util, zeilen

    m, util, zeilen = status(4000e3)
    check("reines Volumenmodell: keine Staebe, Volumennachweis reisst",
          not m.members and util > 1.0, f"{len(m.members)} Staebe, Ausnutzung {util:.3f}")
    check("genau eine Statuszeile im Bericht", len(zeilen) == 1, str(zeilen))
    klasse, text = zeilen[0] if zeilen else ("", "")
    check("reissender Volumennachweis: Statuszeile 'NICHT erfüllt', Klasse nok",
          klasse == "nok" and "NICHT erfüllt" in text, f"{klasse}: {text}")
    check("... und nicht 'keine Nachweise geführt'",
          "keine Nachweise geführt" not in text, text)

    _m2, util2, zeilen2 = status(2500e3)
    klasse2, text2 = zeilen2[0] if zeilen2 else ("", "")
    check("Gegenprobe erfuellter Volumennachweis: 'Alle Nachweise erfüllt.', Klasse ok",
          util2 <= 1.0 and klasse2 == "ok" and text2.strip() == "Alle Nachweise erfüllt.",
          f"Ausnutzung {util2:.3f}, {klasse2}: {text2}")


def test_ausgeschalteter_bereich_im_gesamturteil():
    """Befund B058: ein Volumenbereich mit ausgeschaltetem Nachweis (Schalter
    „Nachweis führen“ aus, ``design=False``) ist **gewollt** nicht geführt.

    Ein Stab mit ``design=False`` faellt ganz aus den Nachweisen heraus
    (ec3/design.check_members) und kippt das Gesamturteil nicht. Der
    Volumenbereich trug dagegen ``fehler = "Nachweis für diesen Bereich
    ausgeschaltet"`` und zaehlte damit wie ein Bereich, der nicht gefuehrt
    werden **konnte**. Gemessen am Stand ec6448c (23.09.2026), Zugkoerper
    100 x 100 mm, S355, N = 2500 kN: „Schaft“ allein -> „Alle Nachweise
    erfüllt.“ (ok); „Schaft“ + „Aus“ -> „Alle **geführten** Nachweise erfüllt
    – nicht geführt wurden: 1 Volumenbereiche“ (nok); „Aus“ allein ->
    dieselbe Zeile, obwohl gar kein Nachweis lief.

    Geprueft wird die Zeile im Bericht und die Zusammenfassung, dazu die
    Gegenprobe: ein Bereich, dessen Nachweis nicht gefuehrt werden **kann**
    (kein Werkstoff mit Streckgrenze), zaehlt weiter als nicht gefuehrt.
    """
    import pickle
    import re
    from statik3d.report import Report

    def lauf(namen, ohne_fy=False):
        m, els, _soll = zugkoerper(N=2500e3)
        if ohne_fy:
            # vier Elemente ohne Streckgrenze - E wie S355, die Rechnung bleibt gleich
            m.add_material(Material("Ohne_fy", E=210e9, nu=0.3))
            for i in els[:4]:
                m.elements[i].mat = "Ohne_fy"
        for n in namen:
            auswahl = els[:4] if n == "Ohne" else (els[4:] if ohne_fy else els)
            m.add_volumenbereich(n, auswahl, design=(n != "Aus"))
        an = solver.solve_all(m, design=True)
        html = Report(m, an).html()
        zeilen = re.findall(r'<div class="status (ok|nok)">(.*?)</div>', html, re.S)
        return an, html, zeilen

    an, html, zeilen = lauf(["Schaft", "Aus"])
    c = an.volumen.bereiche.get("Aus")
    check("„Aus“ steht mit Status „ausgeschaltet“ im Ergebnis, ohne Fehler",
          c is not None and c.status() == "ausgeschaltet" and not c.fehler,
          f"{c.status() if c else '-'}, fehler „{c.fehler if c else ''}“")
    check("Schaft + ausgeschalteter Bereich: „Alle Nachweise erfüllt.“, Klasse ok",
          zeilen == [("ok", "Alle Nachweise erfüllt.")], str(zeilen))
    check("... der ausgeschaltete Bereich ist keine offene Warnung",
          "Volumenbereich Aus:" not in html, "keine Zeile „Volumenbereich Aus: …“")
    check("... steht aber in der Übersicht des Berichts als ausgeschaltet, η „–“",
          re.search(r"<td>Aus</td>(?:(?!</tr>).)*<td class=\"num\">–</td><td></td>"
                    r"<td>ausgeschaltet</td>", html, re.S) is not None,
          "Zeile „Aus … – ausgeschaltet“")
    check("... und im Einzelnen mit dem Satz, dass er ausgeschaltet ist",
          "Der Nachweis ist für diesen Bereich ausgeschaltet" in html)
    s = an.volumen.summary()
    check("Zusammenfassung: alle erfüllt, „Aus“ ausgeschaltet, nichts nicht geführt",
          "alle erfüllt" in s and "1 ausgeschaltet: Aus" in s and "nicht geführt" not in s, s)

    an2, _html2, zeilen2 = lauf(["Aus"])
    klasse2, text2 = zeilen2[0] if zeilen2 else ("", "")
    check("nur ausgeschalteter Bereich: „Es wurden keine Nachweise geführt …“",
          len(zeilen2) == 1 and text2.startswith("Es wurden keine Nachweise geführt"),
          f"{klasse2}: {text2}")
    check("... und nicht „Alle geführten Nachweise erfüllt“", "geführten" not in text2, text2)
    s2 = an2.volumen.summary()
    check("Zusammenfassung ohne geführten Bereich: ausgeschaltet, nicht „nicht geführt“",
          "1 ausgeschaltet: Aus" in s2 and "nicht geführt" not in s2
          and "alle erfüllt" not in s2, s2)

    # Gegenprobe: nicht fuehrbar (kein f_y) bleibt "nicht geführt" - und nur
    # dieser Bereich wird gezaehlt, der ausgeschaltete nicht. Seit B118 in der
    # Einzahl („1 Volumenbereich“; vorher „1 Volumenbereiche“).
    an3, html3, zeilen3 = lauf(["Schaft", "Aus", "Ohne"], ohne_fy=True)
    klasse3, text3 = zeilen3[0] if zeilen3 else ("", "")
    check("Gegenprobe ohne f_y: „nicht geführt wurden: 1 Volumenbereich“, Klasse nok",
          klasse3 == "nok" and "nicht geführt wurden: 1 Volumenbereich " in text3,
          f"{klasse3}: {text3}")
    s3 = an3.volumen.summary()
    check("... mit Warnung; die Zusammenfassung nennt nur „Ohne“ als nicht geführt",
          "Volumenbereich Ohne:" in html3 and "1 nicht geführt: Ohne" in s3, s3)

    # Ergebnisdatei von vor der Kur (ergebnisse.py pickelt die Nachweise): dort
    # steht der alte Fehlertext, das Feld ``ausgeschaltet`` fehlt
    alt = V.VolumenCheck("Aus", fehler="Nachweis für diesen Bereich ausgeschaltet")
    alt.__dict__.pop("ausgeschaltet", None)
    neu = pickle.loads(pickle.dumps(alt))
    check("alte Ergebnisdatei: der ausgeschaltete Bereich kommt als ausgeschaltet zurück",
          neu.status() == "ausgeschaltet" and not neu.fehler,
          f"{neu.status()}, fehler „{neu.fehler}“")


def test_nachweis_nimmt_die_spannung_des_loesers():
    """Der Nachweis darf die Spannung nicht neu aus der Verschiebung rechnen.

    sigma = D B u laesst weg, was der Loeser beruecksichtigt: die plastische
    Vorspannung D eps_p (und, mit Model.knotendilatation, den gemittelten
    volumetrischen Anteil). Gemessen am Stauchwuerfel (384 tet4, S355,
    Fliessen an, 20.09.2026): sigma_v,max 381,2 MPa im Ergebnis gegen
    3300,7 MPa neu gerechnet - Ausnutzung 1,07 gegen 9,3. Der Nachweis war
    damit um Faktor 8,7 zu ungunstig, ohne dass es jemand gesehen haette.

    Die Mehrpunktauswertung bleibt trotzdem: beim Hexaeder unter Biegung
    liegt der Rand deutlich ueber der Mitte. Berichtigt wird um den
    **elementkonstanten** Versatz zwischen Ergebnis und Nachrechnung.
    """
    from statik3d import plastizitaet as pl
    kuhn = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]
    n, L, fy = 4, 0.1, 355e6
    m = Model("Stauchwuerfel")
    m.add_material(Material("S355", E=210e9, nu=0.3, rho=0.0, fy=fy))
    ids = {}
    for i in range(n + 1):
        for j in range(n + 1):
            for k in range(n + 1):
                ids[(i, j, k)] = m.add_node(i * L / n, j * L / n, k * L / n)
    for i in range(n):
        for j in range(n):
            for k in range(n):
                ec = [ids[(i + (x & 1), j + ((x >> 1) & 1), k + ((x >> 2) & 1))] for x in range(8)]
                for v in kuhn:
                    m.add_element("tet4", [ec[x] for x in v], "S355", "")
    for i in range(n + 1):
        for j in range(n + 1):
            m.fix(ids[(i, j, 0)], [0, 1, 2])
    F = -1.2 * fy * L * L
    oben = [ids[(i, j, n)] for i in range(n + 1) for j in range(n + 1)]
    for nd in oben:
        m.load_node(nd, Fz=F / len(oben))
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.01, laststufen=3,
                                     iterationen=25, toleranz=1e-3)
    r = solver.solve_static(m)
    info = r.info.get("plastizitaet") or {}
    check(f"Probe: {info.get('fliessend', 0)} von {len(m.elements)} Elementen fliessen",
          info.get("fliessend", 0) > 50, str(info.get("fliessend")))
    # Seit dem 22.09.2026 liest der Nachweis die geglaettete Eckspannung des
    # Loesers (res.solid_rand, siehe test_randspannung_geglaettet) - auch sie
    # traegt D eps_p und den gemittelten Volumenanteil, sie ist nur ueber die
    # Nachbarn eines Knotens gemittelt statt je Element das Maximum.
    loeser = max(pl.vergleichsspannung(np.asarray(v[0], float)) for v in r.solid_rand.values())
    elementweise = max(pl.vergleichsspannung(np.asarray(v, float)) for v in r.solid_res.values())
    sp = V._elementspannungen(m, r, list(range(len(m.elements))))
    nachweis = max(V.vergleichsspannung(q) for _i, q, _n in sp)
    check("der Nachweis nimmt dieselbe Spannung wie der Loeser (geglaettet)",
          abs(nachweis - loeser) <= 1e-6 * loeser,
          f"{nachweis / 1e6:.1f} gegen {loeser / 1e6:.1f} MPa "
          f"(elementweise {elementweise / 1e6:.1f})")
    # Gegenprobe: ohne die Berichtigung waere es um ein Vielfaches daneben
    from statik3d.elements import solid as sl
    roh = []
    for i in range(len(m.elements)):
        e = m.elements[i]
        mat = m.materials[e.mat]
        X = np.asarray(m.nodes[e.nodes], float)
        ue = np.concatenate([r.u.ravel()[int(x) * 6:int(x) * 6 + 3] for x in e.nodes])
        roh.append(max(V.vergleichsspannung(q)
                       for q in sl.stress_points(e.typ, X, mat.E, mat.nu, ue)))
    check("ohne Berichtigung laege der Nachweis um ein Vielfaches darueber",
          max(roh) > 1.5 * loeser, f"{max(roh) / 1e6:.1f} gegen {loeser / 1e6:.1f} MPa "
          f"(Faktor {max(roh) / loeser:.1f})")


def test_erzeugnisdicke_mindert_die_streckgrenze():
    """Ein dicker Volumenkörper weist sich mit der abgeminderten Streckgrenze
    nach - und die Dicke hängt nicht daran, wie viel ausgewählt war.

    `_material` rief `mat.yield_strength(0.0)` - also **immer die dünnste
    Stufe**. Nach EN 1993-1-1 Tab. 3.1 gilt für S355 bis 40 mm 355 N/mm²,
    darüber 335. Ein Lagerblock von 80 mm wies sich damit mit 355 statt 335
    nach, und η = σ_v/f_yd fiel **6,0 % zu klein** aus - auf der unsicheren
    Seite. Der Stabnachweis macht es seit jeher richtig (`design.py`:
    `mat.yield_strength(sec.t_max)`).

    Die Erzeugnisdicke eines Volumenbereichs ist eine **Festlegung**: die
    kleinste Abmessung des umschließenden Quaders des ganzen Körpers, zu dem
    die Elemente gehören. Nicht der Auswahl - sonst hinge das Ergebnis daran,
    wie viel der Anwender markiert hat, und zwar auf der unsicheren Seite
    (gemessen: Block 300 x 300 x 200 mm, eine Elementlage ausgewählt → 25 mm
    statt 200 mm → 355 statt 335 N/mm², 6,0 % zu günstig). Bei einem
    geschweißten Bauteil ist der Körper umgekehrt zu dick; darum ist die
    Dicke am Bereich angebbar.
    """
    from statik3d.model import Model, Material
    from statik3d.ec3.volumen import _erzeugnisdicke, _koerper, _material

    def block(name, a, b_, c_, nx=1, ny=1, nz=1, x0=0.0):
        """Ein Quader a x b x c aus nx*ny*nz Hexaedern, verschoben um x0."""
        ids, els = {}, []
        for k in range(nz + 1):
            for j in range(ny + 1):
                for i in range(nx + 1):
                    ids[(i, j, k)] = name.add_node(x0 + a * i / nx, b_ * j / ny,
                                                   c_ * k / nz)
        for k in range(nz):
            for j in range(ny):
                for i in range(nx):
                    els.append(name.add_element("hex8", [
                        ids[(i, j, k)], ids[(i + 1, j, k)], ids[(i + 1, j + 1, k)],
                        ids[(i, j + 1, k)], ids[(i, j, k + 1)],
                        ids[(i + 1, j, k + 1)], ids[(i + 1, j + 1, k + 1)],
                        ids[(i, j + 1, k + 1)]], "S355"))
        return els

    m = Model("block")
    m.add_material(Material.steel("S355"))
    # Block 0,30 x 0,30 x 0,20 m, fein vernetzt: die Elemente sind 25 mm dick,
    # der Koerper 200 mm. Genau hier trennt sich Auswahl von Koerper.
    els = block(m, 0.30, 0.30, 0.20, 6, 6, 8)
    kp = _koerper(m)

    t = _erzeugnisdicke(m, els, kp)
    check("die Erzeugnisdicke ist die kleinste Abmessung des Körpers",
          abs(t - 0.20) < 1e-12, f"{t * 1000:.1f} mm")
    t1 = _erzeugnisdicke(m, [els[0]], kp)
    check("ein einzelnes Element ergibt dieselbe Dicke",
          abs(t1 - 0.20) < 1e-12, f"{t1 * 1000:.1f} mm bei 1 von {len(els)}")
    lage = els[:36]
    t2 = _erzeugnisdicke(m, lage, kp)
    check("eine einzelne Elementlage auch",
          abs(t2 - 0.20) < 1e-12, f"{t2 * 1000:.1f} mm bei 36 von {len(els)}")
    # Die Probe ist scharf: aus der Auswahl allein kaeme 25 mm
    X = np.asarray(m.nodes, float)[sorted({int(x) for e in lage
                                           for x in m.elements[e].nodes})]
    aus_auswahl = float((X.max(axis=0) - X.min(axis=0)).min())
    check("die Probe ist scharf: aus der Auswahl allein käme 25 mm",
          abs(aus_auswahl - 0.025) < 1e-12, f"{aus_auswahl * 1000:.1f} mm")

    _n, fy_dick = _material(m, els, t)
    _n, fy_duenn = _material(m, els, 0.0)
    check("über 40 mm gilt die abgeminderte Streckgrenze",
          abs(fy_dick - 335e6) < 1e3, f"{fy_dick / 1e6:.1f} N/mm²")
    check("die Ausnutzung wäre sonst zu klein gewesen",
          abs((fy_duenn / fy_dick - 1.0) - 0.0597) < 0.002,
          f"{(fy_duenn / fy_dick - 1) * 100:.1f} % zu klein")

    # Zwei Koerper im selben Modell bleiben getrennt
    els2 = block(m, 0.30, 0.30, 0.012, 2, 2, 1, x0=1.0)
    kp2 = _koerper(m)
    check("ein zweiter Körper im Modell wird nicht mitgezählt",
          abs(_erzeugnisdicke(m, els2, kp2) - 0.012) < 1e-12
          and abs(_erzeugnisdicke(m, els, kp2) - 0.20) < 1e-12,
          f"{_erzeugnisdicke(m, els2, kp2) * 1000:.1f} mm neben "
          f"{_erzeugnisdicke(m, els, kp2) * 1000:.1f} mm")

    # Gegenprobe: ein duennes Blech behaelt die volle Streckgrenze
    _n, fy2 = _material(m, els2, _erzeugnisdicke(m, els2, kp2))
    check("ein 12-mm-Blech behält die volle Streckgrenze",
          abs(fy2 - 355e6) < 1e3, f"{fy2 / 1e6:.1f} N/mm²")


def test_erzeugnisdicke_ist_angebbar():
    """Ist das Bauteil aus Blechen geschweißt, ist der Körper zu dick.

    Dann gilt die Blechdicke, und die wird am Volumenbereich angegeben. Die
    angegebene Dicke hat Vorrang vor der aus dem Körper bestimmten, sie steht
    im Nachweis und übersteht Speichern und Laden.
    """
    m, els, soll = zugkoerper()
    m.add_volumenbereich("Schaft", els, dicke=0.020)
    an = solver.solve_all(m, design=True)
    c = an.volumen.bereiche["Schaft"]
    check("die angegebene Dicke hat Vorrang vor der des Körpers",
          abs(c.werte.get("dicke", 0.0) - 0.020) < 1e-12,
          f"{c.werte.get('dicke', 0.0) * 1000:.1f} mm statt 100,0 mm")
    check("und damit gilt die volle Streckgrenze",
          abs(c.fy - 355e6) < 1e-6, f"{c.fy / 1e6:.0f} N/mm²")
    close("die Ausnutzung rechnet damit", c.util,
          soll / (355e6 / m.design.gamma_M0), 1e-9)
    check("der Hinweis auf die Abminderung entfällt",
          not any("Erzeugnisdicke" in h for h in c.hinweise),
          str([h[:50] for h in c.hinweise]))
    d = Model.from_dict(m.to_dict())
    check("die Erzeugnisdicke übersteht Speichern und Laden",
          abs(d.volumenbereiche["Schaft"].dicke - 0.020) < 1e-12,
          f"{d.volumenbereiche['Schaft'].dicke * 1000:.1f} mm")
    check("und die Modellkopie",
          abs(m.copy().volumenbereiche["Schaft"].dicke - 0.020) < 1e-12)


def main():
    print("=" * 92)
    print("STATIK3D - Verifikation Volumennachweise (DIN EN 1993-1-1, 6.2.1(5))")
    print("=" * 92)
    for t in (test_erzeugnisdicke_mindert_die_streckgrenze,
              test_erzeugnisdicke_ist_angebbar, test_spannungsformeln, test_zugkoerper, test_randspannung,
              test_nachweis_nimmt_die_spannung_des_loesers, test_elementmittel,
              test_randspannung_geglaettet, test_randspannung_fliessend,
              test_fehlerfaelle, test_bericht, test_gesamturteil_reines_volumenmodell,
              test_ausgeschalteter_bereich_im_gesamturteil):
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
