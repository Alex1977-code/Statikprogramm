"""
Der Tetraeder mit Ordnung p in der Rechnung von Statik3D (solver.solve_static).

  * Model.ndof zaehlt die Zusatz-FHG, res.u bleibt (nn, 6)
  * Kragarm (Kuhn-Gitter, tetp3): Auflagerkraft = Last; sigma_v an der
    Oberkante aus dem Knotenmittel der Rechnung (res.solid_rand) gegen
    Saint-Venant auf 1 N/mm2
  * Eigengewicht: Auflagerkraft = rho g V
  * Uebergang tet4/tetp3 und Symmetrieebene: Patch-Test ueber die Rechnung
  * Temperatur: freie Dehnung ohne Spannung

Aufruf:  python -m tests.test_tetp_rechnung
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                         # noqa: E402
from statik3d.elements import tetp as tp                            # noqa: E402
from statik3d.model import Material, Model                          # noqa: E402

RESULTS = []
E_ST, NU_ST = 210e9, 0.3
KUHN = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:62s} {detail}")
    return ok


def sv(s):
    s = np.asarray(s, float)
    return float(np.sqrt(0.5 * ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2 + (s[2] - s[0]) ** 2)
                         + 3 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2)))


def quader(nx, ny, nz, L, B, H, typ_von, rho=7850.0, alpha=1.2e-5):
    m = Model("tetp")
    m.add_material(Material("S", E=E_ST, nu=NU_ST, rho=rho, alpha=alpha))
    ids = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                ids[(i, j, k)] = m.add_node(L * i / nx, B * j / ny, H * k / nz)
    X = np.asarray(m.nodes, float)
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                z = [ids[(i + (c & 1), j + ((c >> 1) & 1), k + ((c >> 2) & 1))] for c in range(8)]
                for tet in KUHN:
                    kn = [z[c] for c in tet]
                    Xe = X[kn]
                    if np.linalg.det(np.array([Xe[1] - Xe[0], Xe[2] - Xe[0], Xe[3] - Xe[0]])) < 0:
                        kn[1], kn[2] = kn[2], kn[1]
                    m.add_element(typ_von(X[kn].mean(axis=0)), kn, "S")
    return m


def seiten_auf(m, bedingung):
    """[(Element, Seite)] der Elementseiten, deren Ecken alle die Bedingung erfuellen."""
    aus = []
    X = np.asarray(m.nodes, float)
    for i, e in enumerate(m.elements):
        for s, ecken in enumerate(tp.SEITEN):
            if all(bedingung(X[e.nodes[a]]) for a in ecken):
                aus.append((i, s))
    return aus


def test_kragarm():
    """Wie tests/test_tetp.test_kragarm, aber durch den Loeser: 10 x 1 x 2
    Kuhn-Zellen, damit die Nachweisstelle (L/2, B/2, H) ein Knoten ist. Im
    Labor gemessen (22.09.2026, p = 3, 10 x 1 x 2): jedes Element dort
    hoechstens 0,075 N/mm2 daneben."""
    L, B, H = 1.0, 0.1, 0.2
    I = B * H ** 3 / 12
    F = 355e6 * I / (0.5 * L * 0.5 * H)
    m = quader(10, 2, 2, L, B, H, lambda c: "tetp3", rho=0.0)
    lc = m.add_load_case("LF1")
    lc.gravity = [0.0, 0.0, 0.0]
    for i, s in seiten_auf(m, lambda x: abs(x[0] - L) < 1e-9):
        m.load_face(i, F / (B * H), s, case="LF1", direction=(0.0, 0.0, -1.0))
    for n in range(m.nn):
        if abs(m.nodes[n][0]) < 1e-9:
            m.fix(n, [0, 1, 2])
    res = solver.solve_static(m, case="LF1")
    check("Model.ndof zaehlt die Zusatz-FHG, res.u bleibt (nn, 6)",
          m.ndof == 6 * m.nn + tp.anzahl_fhg(m) and np.asarray(res.u).shape == (m.nn, 6),
          f"ndof {m.ndof} = 6 * {m.nn} + {tp.anzahl_fhg(m)}")
    Fz = float(np.asarray(res.reactions)[:, 2].sum())
    check("Kragarm: Auflagerkraft = Last", abs(Fz - F) < 1e-6 * F, f"{Fz:.3f} N gegen {F:.3f} N")
    X = np.asarray(m.nodes, float)
    ziel = [n for n in range(m.nn) if np.linalg.norm(X[n] - [0.5 * L, 0.5 * B, H]) < 1e-9]
    rand = res.solid_rand
    werte = [sv(s) / 1e6 for i, (s, kn) in rand.items() if kn in ziel]
    abw = max(abs(w - 355.0) for w in werte) if werte else float("inf")
    check("Kragarm tetp3 durch den Loeser: Knotenmittel an der Oberkante auf 1 N/mm2",
          abw <= 1.0, f"{len(werte)} Elemente mit dieser Ecke, groesste Abweichung {abw:.3f} N/mm2")


def test_eigengewicht():
    m = quader(2, 1, 1, 1.0, 0.5, 0.4, lambda c: "tetp3" if c[0] > 0.5 else "tetp2")
    lc = m.add_load_case("G")
    lc.gravity = [0.0, 0.0, -9.81]
    for n in range(m.nn):
        if abs(m.nodes[n][2]) < 1e-9:
            m.fix(n, [0, 1, 2])
    res = solver.solve_static(m, case="G")
    Fz = float(np.asarray(res.reactions)[:, 2].sum())
    soll = 7850.0 * 9.81 * 0.2
    check("Eigengewicht tetp2/tetp3: Auflagerkraft = rho g V", abs(Fz - soll) < 1e-8 * soll,
          f"{Fz:.4f} N gegen {soll:.4f} N")


def test_patch_rechnung():
    """Lineares Verschiebungsfeld am ganzen Rand vorgegeben, innen tet4 und
    tetp3 gemischt: die Spannung jedes Elements ist die konstante des Feldes."""
    rng = np.random.default_rng(5)
    A = rng.normal(size=(3, 3)) * 1e-4
    m = quader(3, 3, 3, 1.0, 1.0, 1.0, lambda c: "tetp3" if c[0] > 0.4 else "tet4")
    lc = m.add_load_case("P")
    lc.gravity = [0.0, 0.0, 0.0]
    X = np.asarray(m.nodes, float)
    for n in range(m.nn):
        if min(X[n].min(), 1 - X[n].max()) < 1e-9:
            m.fix(n, [0, 1, 2], values=list(A @ X[n]))
    res = solver.solve_static(m, case="P")
    eps = np.array([A[0, 0], A[1, 1], A[2, 2], A[0, 1] + A[1, 0], A[1, 2] + A[2, 1], A[0, 2] + A[2, 0]])
    lam = E_ST * NU_ST / ((1 + NU_ST) * (1 - 2 * NU_ST))
    mu = E_ST / (2 * (1 + NU_ST))
    soll = np.array([lam * eps[:3].sum() + 2 * mu * eps[0], lam * eps[:3].sum() + 2 * mu * eps[1],
                     lam * eps[:3].sum() + 2 * mu * eps[2], mu * eps[3], mu * eps[4], mu * eps[5]])
    fehler = max(np.abs(np.asarray(s, float) - soll).max() for s in res.solid_res.values()) / np.abs(soll).max()
    typen = sorted({e.typ for e in m.elements})
    check("Patch-Test durch den Loeser, tet4 und tetp3 gemischt", fehler < 1e-9,
          f"rel. Fehler {fehler:.1e}, Typen {typen}")


def test_symmetrieebene():
    """Wuerfel unter gleichmaessigem Zug in x; gelagert nur die Normalen der
    drei Ebenen x = 0, y = 0, z = 0 (Symmetrie). Exakt: sigma_xx = p, alles
    andere null - in der Ebene darf keine Zusatz-FHG festgehalten sein."""
    m = quader(2, 2, 2, 1.0, 1.0, 1.0, lambda c: "tetp3", rho=0.0)
    lc = m.add_load_case("Z")
    lc.gravity = [0.0, 0.0, 0.0]
    X = np.asarray(m.nodes, float)
    for n in range(m.nn):
        d = [c for c in range(3) if abs(X[n, c]) < 1e-9]
        if d:
            m.fix(n, d)
    p = 100e6
    for i, s in seiten_auf(m, lambda x: abs(x[0] - 1.0) < 1e-9):
        m.load_face(i, p, s, case="Z", direction=(1.0, 0.0, 0.0))
    res = solver.solve_static(m, case="Z")
    soll = np.array([p, 0, 0, 0, 0, 0])
    fehler = max(np.abs(np.asarray(s, float) - soll).max() for s in res.solid_res.values()) / p
    check("Symmetrieebenen: einachsiger Zug exakt", fehler < 1e-9, f"rel. Fehler {fehler:.1e}")


def test_temperatur():
    """Frei gelagerter Wuerfel (statisch bestimmt), gleichmaessig erwaermt: keine Spannung."""
    m = quader(2, 2, 2, 1.0, 1.0, 1.0, lambda c: "tetp3")
    lc = m.add_load_case("T")
    lc.gravity = [0.0, 0.0, 0.0]
    X = np.asarray(m.nodes, float)
    a = [n for n in range(m.nn) if np.linalg.norm(X[n]) < 1e-9][0]
    b = [n for n in range(m.nn) if np.linalg.norm(X[n] - [1, 0, 0]) < 1e-9][0]
    c = [n for n in range(m.nn) if np.linalg.norm(X[n] - [0, 1, 0]) < 1e-9][0]
    m.fix(a, [0, 1, 2])
    m.fix(b, [1, 2])
    m.fix(c, [2])
    from statik3d.model import TempLoad
    for i in range(len(m.elements)):
        lc.temp_loads.append(TempLoad(i, 50.0))
    res = solver.solve_static(m, case="T")
    s_max = max(np.abs(np.asarray(s, float)).max() for s in res.solid_res.values())
    u = np.asarray(res.u, float)[:, :3]
    soll_u = 1.2e-5 * 50.0 * X
    check("Temperatur: freie Dehnung ohne Spannung", s_max < 1e-3 and np.abs(u - soll_u).max() < 1e-12,
          f"groesste Spannung {s_max:.2e} Pa, u-Abweichung {np.abs(u - soll_u).max():.1e} m")


# --------------------------------------------------------------------------
# Je Lastart: tetp2/3/4 gegen die geschlossene Loesung und gegen tet10
# (Auflage der Statik3D-Sitzung, 23.09.2026)
# --------------------------------------------------------------------------
def _wuerfel(typ, lagerung, n=2):
    """Wuerfel 1 m aus Kuhn-Zellen; typ "tet10" bekommt Kantenmitten."""
    m = quader(n, n, n, 1.0, 1.0, 1.0, lambda c: "tet4")
    if typ == "tet10":
        mitten = {}
        for e in m.elements:
            kn = list(e.nodes[:4])
            neu = []
            for a, b in ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)):
                k = (min(kn[a], kn[b]), max(kn[a], kn[b]))
                if k not in mitten:
                    mitten[k] = m.add_node(*(0.5 * (np.asarray(m.nodes[kn[a]]) + np.asarray(m.nodes[kn[b]]))))
                neu.append(mitten[k])
            e.typ, e.nodes = "tet10", kn + neu
    else:
        for e in m.elements:
            e.typ = typ
    m._tetp_version = getattr(m, "_tetp_version", 0) + 1
    X = np.asarray(m.nodes, float)
    if lagerung == "boden":
        for i in range(m.nn):
            if abs(X[i, 2]) < 1e-9:
                m.fix(i, [0, 1, 2])
    elif lagerung == "alle":
        for i in range(m.nn):
            if min(X[i].min(), 1 - X[i].max()) < 1e-9:
                m.fix(i, [0, 1, 2])
    elif lagerung == "frei":
        a = [i for i in range(m.nn) if np.linalg.norm(X[i]) < 1e-9][0]
        b = [i for i in range(m.nn) if np.linalg.norm(X[i] - [1, 0, 0]) < 1e-9][0]
        c = [i for i in range(m.nn) if np.linalg.norm(X[i] - [0, 1, 0]) < 1e-9][0]
        m.fix(a, [0, 1, 2])
        m.fix(b, [1, 2])
        m.fix(c, [2])
    return m


def _lastfall(m, name):
    lc = m.add_load_case(name)
    lc.gravity = [0.0, 0.0, 0.0]
    return lc


def test_lastarten():
    rho, g = 7850.0, 9.81
    E, nu, alpha, dT = E_ST, NU_ST, 1.2e-5, 30.0
    zeilen = []
    for typ in ("tetp2", "tetp3", "tetp4", "tet10"):
        # Eigengewicht, Boden eingespannt: Auflagerkraft = rho g V
        m = _wuerfel(typ, "boden")
        lc = _lastfall(m, "G")
        lc.gravity = [0.0, 0.0, -g]
        r = solver.solve_static(m, case="G")
        R_g = float(np.asarray(r.reactions)[:, 2].sum())
        # Seitendruck auf die Deckflaeche, einmal normal, einmal schraeg
        m = _wuerfel(typ, "boden")
        _lastfall(m, "D")
        d = np.array([1.0, 0.0, -1.0]) / np.sqrt(2.0)
        for i, s in seiten_auf(m, lambda x: abs(x[2] - 1.0) < 1e-9):
            m.load_face(i, 1e5, s, case="D")
            m.load_face(i, 2e5, s, case="D", direction=d)
        r = solver.solve_static(m, case="D")
        R_d = np.asarray(r.reactions)[:, :3].sum(axis=0)
        # Temperatur allseitig behindert: sigma = -E alpha dT / (1 - 2 nu)
        from statik3d.model import TempLoad
        m = _wuerfel(typ, "alle")
        lc = _lastfall(m, "T")
        for i in range(len(m.elements)):
            lc.temp_loads.append(TempLoad(i, dT))
        r = solver.solve_static(m, case="T")
        s_T = np.array([np.asarray(s, float) for s in r.solid_res.values()])
        # Vorspannung eines Koerpers (einachsig in z), allseitig behindert und frei
        import types
        from statik3d.model import Vorspannung
        s_V = []
        for lag in ("alle", "frei"):
            m = _wuerfel(typ, lag)
            m.koerper = {"K": types.SimpleNamespace(elemente=list(range(len(m.elements))))}
            lc = _lastfall(m, "V")
            lc.vorspannungen.append(Vorspannung("K", "koerper", 1e6, [0.0, 0.0, 1.0]))
            r = solver.solve_static(m, case="V")
            s_V.append(np.array([np.asarray(s, float) for s in r.solid_res.values()]))
        zeilen.append((typ, R_g, R_d, s_T, s_V))
    V = 1.0
    soll_T = -E * alpha * dT / (1 - 2 * nu)
    for typ, R_g, R_d, s_T, s_V in zeilen:
        ok_g = abs(R_g - rho * g * V) < 1e-9 * rho * g * V
        soll_d = -(np.array([0.0, 0.0, -1e5]) + 2e5 * d)        # Reaktion = - Last
        ok_d = np.abs(R_d - soll_d).max() < 1e-9 * 3e5
        ok_T = np.abs(s_T[:, :3] - soll_T).max() < 1e-9 * abs(soll_T) and np.abs(s_T[:, 3:]).max() < 1e-9 * abs(soll_T)
        # Vorspannung 1 MN auf A = 1 m2: behindert sigma_zz = +1 MPa (Zug im Koerper), frei 0
        ok_V = (np.abs(s_V[0][:, 2] - 1e6).max() < 1e-6 * 1e6 and np.abs(s_V[1]).max() < 1e-6 * 1e6)
        check(f"{typ}: Eigengewicht, Seitendruck (normal/schraeg), Temperatur, Vorspannung",
              ok_g and ok_d and ok_T and ok_V,
              f"G {R_g:.3f} N; D {np.round(R_d, 3)}; T {s_T[:, 2].mean() / 1e6:+.3f} MPa "
              f"(Soll {soll_T / 1e6:+.3f}); V behindert {s_V[0][:, 2].mean() / 1e6:+.4f}, frei "
              f"{np.abs(s_V[1]).max():.1e}")
    # tetp und tet10 gleich (dieselben Zahlen je Lastart)
    ref = zeilen[-1]
    gleich = all(abs(z[1] - ref[1]) < 1e-9 * abs(ref[1]) and np.abs(z[2] - ref[2]).max() < 1e-6
                 and abs(z[3][:, 2].mean() - ref[3][:, 2].mean()) < 1e-6 * abs(ref[3][:, 2].mean())
                 for z in zeilen[:-1])
    check("tetp2/3/4 und tet10: je Lastart dieselben Summen und Spannungen", gleich)


def test_linienlager_an_kante():
    """Starres Linienlager an einer tetp-Kante (beide Ecken gelagert, Kante auf
    dem Rand): die Zusatz-FHG der Kante sind in der gelagerten Richtung
    gesperrt. Federndes Linienlager: die Kante bleibt linear."""
    m = quader(2, 2, 2, 1.0, 1.0, 1.0, lambda c: "tetp3")
    X = np.asarray(m.nodes, float)
    linie = [i for i in range(m.nn) if abs(X[i, 0]) < 1e-9 and abs(X[i, 2]) < 1e-9]
    for i in linie:
        m.fix(i, [2])
    an = tp.anreicherung(m)
    ks = [k for k, (a, b) in enumerate(an.kanten) if a in linie and b in linie]
    fest = set(tp.gesperrte_fhg(m).tolist())
    ok = all(an.start_kante[k] + 3 * r + 2 in fest for k in ks for r in range(an.p_kante[k] - 1))
    frei_xy = all(an.start_kante[k] + 3 * r + c not in fest for k in ks for r in range(an.p_kante[k] - 1)
                  for c in (0, 1))
    check("starres Linienlager an tetp-Kanten: Zusatz-FHG in z gesperrt, in x, y frei", ok and frei_xy and ks,
          f"{len(ks)} Kanten")
    m2 = quader(2, 2, 2, 1.0, 1.0, 1.0, lambda c: "tetp3")
    for i in linie:
        m2.fix(i, [2], stiffness=[1e9])
    an2 = tp.anreicherung(m2)
    ks2 = [k for k, (a, b) in enumerate(an2.kanten) if a in linie and b in linie]
    check("federndes Linienlager an tetp-Kanten: Kanten bleiben linear",
          all(an2.p_kante[k] == 1 for k in ks2) and ks2, f"{len(ks2)} Kanten")


class _ZaehlListe(list):
    """Liste, die mitzaehlt, wie oft ueber sie gelaufen wird."""
    laeufe = 0

    def __iter__(self):
        _ZaehlListe.laeufe += 1
        return super().__iter__()


def test_ndof_ohne_tetp():
    """Ohne tetp ist Model.ndof wortwoertlich wie vorher (6 nn + Woelb-FHG),
    und wiederholte Aufrufe laufen nicht ueber die Elemente (Einwand der
    Statik3D-Sitzung 23.09.2026: ndof wird oft gefragt, das Drehlager hat
    645.934 Volumenelemente). Mit tetp an Ort und Stelle eingesetzt zaehlt
    ndof nach _tetp_version += 1 die Zusatz-FHG mit."""
    m = quader(2, 2, 2, 1.0, 1.0, 1.0, lambda c: "tet4")
    alt = m.nn * 6 + len(m.woelb_knoten())
    m.elements = _ZaehlListe(m.elements)
    erst = m.ndof
    vorher = _ZaehlListe.laeufe
    for _ in range(100):
        n = m.ndof
    check("ndof ohne tetp unveraendert, 100 Aufrufe ohne Lauf ueber die Elemente",
          erst == alt and n == alt and _ZaehlListe.laeufe == vorher,
          f"ndof {n} = {alt}; Laeufe ueber die Elemente {_ZaehlListe.laeufe - vorher}")
    m.elements[0].typ = "tetp3"
    m._tetp_version = getattr(m, "_tetp_version", 0) + 1
    check("tetp an Ort und Stelle eingesetzt: ndof zaehlt die Zusatz-FHG",
          m.ndof > alt, f"{m.ndof} > {alt}")
    # ... und OHNE den Zaehler: ndof merkt es nicht, stiffness bricht laut ab
    from statik3d import assemble as asm
    for neu_typ, text in (("tetp2", "tet4 -> tetp2"), ("tetp4", "tetp3 -> tetp4")):
        m2 = quader(2, 2, 2, 1.0, 1.0, 1.0, lambda c: "tet4" if neu_typ == "tetp2" else "tetp3")
        n_vorher = m2.ndof
        m2.elements[0].typ = neu_typ
        try:
            asm.stiffness(m2)
            check(f"Typ an Ort und Stelle ohne _tetp_version ({text}): stiffness laut", False,
                  "kein Fehler")
        except ValueError as ex:
            check(f"Typ an Ort und Stelle ohne _tetp_version ({text}): stiffness laut",
                  "_tetp_version" in str(ex), f"ndof vorher {n_vorher}; {str(ex)[:60]}")


def main():
    test_ndof_ohne_tetp()
    test_kragarm()
    test_eigengewicht()
    test_patch_rechnung()
    test_symmetrieebene()
    test_temperatur()
    test_lastarten()
    test_linienlager_an_kante()
    n_fail = sum(1 for _n, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} bestanden")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
