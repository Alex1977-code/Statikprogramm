"""
Der lineare Tetraeder ohne volumetrische Versteifung (knotengemittelte Dilatation).

Der tet4 hat **konstante** Dehnung. Sein volumetrischer Anteil ist damit schon
konstant, und elementlokales B-bar bringt nichts - es gibt nichts zu mitteln.
Gemittelt werden muss ueber den Verband der Elemente an einem Knoten:

    n_I   = sum_e (K_e V_e / 4) * (m^T B_e)
    w_I   = sum_e (K_e V_e / 4)
    K_vol = sum_I (1 / w_I) n_I^T n_I

zusammen mit dem deviatorischen Anteil je Element. Gehoert zu einem Knoten nur
**ein** Element, faellt das genau auf den gewoehnlichen Tetraeder zurueck.

Warum das noetig ist (gemessen 20.09.2026, Kragtraeger 0,2 x 0,2 x 2,0 m,
480 Tetraeder, gegen die Balkenloesung):

    nu      gewoehnlich   knotengemittelt
    0,300      51,0 %          67,2 %
    0,450      30,2 %          62,4 %
    0,490      10,6 %          58,5 %
    0,499       2,1 %          51,1 %

Bei nu -> 0,5 ist der gewoehnliche Tetraeder praktisch starr. Genau dorthin
laeuft der Werkstoff beim Fliessen: von-Mises-Fliessen ist volumentreu.

Aufruf:  python -m tests.test_dilatation
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, solver                      # noqa: E402
from statik3d.elements import solid as sl                          # noqa: E402
from statik3d.model import Material, Model                         # noqa: E402

RESULTS = []

#: Die sechs Tetraeder eines Wuerfels (Kuhn-Zerlegung)
KUHN = [(0, 1, 3, 7), (0, 1, 7, 5), (0, 5, 7, 4), (0, 3, 2, 7), (0, 6, 4, 7), (0, 2, 6, 7)]


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:70s} {detail}")
    return ok


def _quader(nx, ny, nz, Lx, Ly, Lz, nu, E=210e9, stoerung=0.0, keim=7):
    """Quader aus Kuhn-Tetraedern; ``stoerung`` verschiebt innere Knoten."""
    m = Model("Q")
    m.add_material(Material("S", E=E, nu=nu, rho=0.0))
    rng = np.random.default_rng(keim)
    ids = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            for k in range(nz + 1):
                p = np.array([i * Lx / nx, j * Ly / ny, k * Lz / nz])
                if stoerung and 0 < i < nx and 0 < j < ny and 0 < k < nz:
                    p = p + rng.uniform(-1, 1, 3) * stoerung * min(Lx / nx, Ly / ny, Lz / nz)
                ids[(i, j, k)] = m.add_node(*p)
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                ec = [ids[(i + (x & 1), j + ((x >> 1) & 1), k + ((x >> 2) & 1))] for x in range(8)]
                for v in KUHN:
                    m.add_element("tet4", [ec[x] for x in v], "S", "")
    return m, ids


def _kragtraeger(nu, h=0.1, L=2.0, b=0.2):
    """Kragtraeger b x b x L, links eingespannt, Endlast quer - und die
    Balkenloesung F L^3 / (3 E I) dazu."""
    nx, ny, nz = int(round(L / h)), max(1, int(round(b / h))), max(1, int(round(b / h)))
    m, ids = _quader(nx, ny, nz, L, b, b, nu)
    for j in range(ny + 1):
        for k in range(nz + 1):
            m.fix(ids[(0, j, k)], [0, 1, 2, 3, 4, 5])
    F = -1000.0
    ende = [ids[(nx, j, k)] for j in range(ny + 1) for k in range(nz + 1)]
    for n in ende:
        m.load_node(n, Fz=F / len(ende))
    return m, F * L ** 3 / (3.0 * 210e9 * b * b ** 3 / 12.0)


def test_aufspaltung_ist_exakt():
    """D = D_dev + K m m^T - die Aufspaltung selbst aendert nichts. Erst die
    Mittelung ueber den Knotenverband tut es."""
    for nu in (0.0, 0.2, 0.3, 0.45, 0.499):
        D = sl.D_matrix(210e9, nu)
        Dd = sl.D_deviatorisch(210e9, nu)
        kap = sl.kompressionsmodul(210e9, nu)
        d = float(np.abs(D - (Dd + kap * np.outer(sl.VOIGT_M, sl.VOIGT_M))).max())
        check(f"nu = {nu}: D = D_dev + K m m^T", d <= 1e-12 * np.abs(D).max(),
              f"{d / np.abs(D).max():.2e} relativ")
    # Der deviatorische Anteil traegt keine Volumenaenderung
    Dd = sl.D_deviatorisch(210e9, 0.3)
    spur = float(np.abs(sl.VOIGT_M @ Dd).max())
    check("D_dev traegt keinen hydrostatischen Anteil (m^T D_dev = 0)",
          spur <= 1e-6 * np.abs(Dd).max(), f"{spur:.3e}")


def test_ein_element_bleibt_der_gewoehnliche_tetraeder():
    """Gehoert zu jedem Knoten nur **ein** Element, ist der Verband das
    Element selbst - dann muss genau der gewoehnliche tet4 herauskommen."""
    for nu in (0.3, 0.499):
        m = Model("T")
        m.add_material(Material("S", E=210e9, nu=nu, rho=0.0))
        ids = [m.add_node(*p) for p in [(0, 0, 0), (1.1, 0, 0), (0.2, 0.9, 0), (0.1, 0.3, 1.2)]]
        m.add_element("tet4", ids, "S", "")
        m.knotendilatation = False
        Ka = asm.stiffness(m).toarray()
        m.knotendilatation = True
        Kb = asm.stiffness(m).toarray()
        d = float(np.abs(Ka - Kb).max()) / float(np.abs(Ka).max())
        check(f"nu = {nu}: ein Tetraeder gibt dieselbe Steifigkeit wie gewoehnlich",
              d <= 1e-12, f"{d:.2e} relativ")


def test_patchtest():
    """Ein lineares Verschiebungsfeld muss exakt sein: konstante Dehnung,
    keine Restkraft an inneren Knoten. Das gilt auf einem **gestoerten** Netz,
    sonst prueft man nur die Symmetrie des Gitters."""
    A = np.array([[1e-4, 2e-5, 3e-5], [2e-5, -5e-5, 1e-5], [3e-5, 1e-5, 7e-5]])
    for nu in (0.3, 0.499):
        m, ids = _quader(3, 3, 3, 1.0, 1.0, 1.0, nu, stoerung=0.13)
        m.knotendilatation = True
        K = asm.stiffness(m)
        u = np.zeros(m.ndof)
        for n in range(m.nn):
            u[n * 6:n * 6 + 3] = A @ m.nodes[n]
        F = K @ u
        rand = {ids[(i, j, k)] for i in range(4) for j in range(4) for k in range(4)
                if i in (0, 3) or j in (0, 3) or k in (0, 3)}
        innen = [n for n in range(m.nn) if n not in rand]
        rest = max(abs(F[n * 6 + d]) for n in innen for d in range(3))
        bez = float(np.abs(F).max())
        check(f"nu = {nu}: Patchtest - keine Restkraft an {len(innen)} inneren Knoten",
              rest <= 1e-10 * bez, f"{rest / bez:.2e} relativ ({rest:.2e} N von {bez:.2e} N)")


def test_versteifung_ist_weg():
    """Der Kragtraeger: je naeher nu an 0,5, desto steifer wird der
    gewoehnliche Tetraeder - bis zur Starrheit. Mit der Mittelung bleibt er
    brauchbar."""
    werte = {}
    for nu in (0.3, 0.45, 0.499):
        m, soll = _kragtraeger(nu)
        m.knotendilatation = False
        a = solver.solve_static(m).u[:, 2].min() / soll
        m.knotendilatation = True
        b = solver.solve_static(m).u[:, 2].min() / soll
        werte[nu] = (a, b)
        check(f"nu = {nu}: knotengemittelt ist weicher als gewoehnlich",
              b > a * 1.05, f"{100 * a:.1f} % -> {100 * b:.1f} % der Balkenloesung")
    a3, b3 = werte[0.3]
    check("bei nu = 0,3 ist der Gewinn noch maessig (die Schubversteifung bleibt)",
          1.1 < b3 / a3 < 2.0, f"{b3 / a3:.2f}x")
    a5, b5 = werte[0.499]
    check("bei nu = 0,499 ist der gewoehnliche Tetraeder praktisch starr",
          a5 < 0.10, f"{100 * a5:.1f} % der Balkenloesung")
    check("und die Mittelung holt ihn zurueck", b5 > 0.4 and b5 / a5 > 5.0,
          f"{100 * b5:.1f} %, Faktor {b5 / a5:.1f}")


def test_gleichgewicht_und_spannung():
    """Gleichgewicht und mittlere Spannung muessen stimmen - die Spannung
    rechnet mit derselben gemittelten Volumendehnung wie die Steifigkeit."""
    for nu in (0.3, 0.499):
        m, ids = _quader(3, 3, 3, 0.3, 0.3, 0.3, nu)
        for i in range(4):
            for j in range(4):
                m.fix(ids[(i, j, 0)], [0, 1, 2])
        F = -3e5
        oben = [ids[(i, j, 3)] for i in range(4) for j in range(4)]
        for n in oben:
            m.load_node(n, Fz=F / len(oben))
        m.knotendilatation = True
        r = solver.solve_static(m)
        R = float(r.reactions[:, 2].sum())
        check(f"nu = {nu}: die Auflager tragen die Last", abs(R + F) <= 1e-6 * abs(F),
              f"{R:.1f} N gegen {-F:.1f} N")
        sz = np.array([v[2] for v in r.solid_res.values()])
        soll = F / (0.3 * 0.3)
        check(f"nu = {nu}: sigma_zz im Mittel = F/A",
              abs(sz.mean() - soll) <= 1e-6 * abs(soll),
              f"{sz.mean() / 1e6:.4f} MPa gegen {soll / 1e6:.4f} MPa")


def test_nur_tet4_ist_betroffen():
    """Andere Elementtypen rechnen unveraendert - die Mittelung greift nur
    dort, wo die konstante Dehnung das Problem ist."""
    m = Model("H")
    m.add_material(Material("S", E=210e9, nu=0.499, rho=0.0))
    ids = {}
    for i in range(3):
        for j in range(2):
            for k in range(2):
                ids[(i, j, k)] = m.add_node(i * 0.5, j * 0.3, k * 0.3)
    for i in range(2):
        ec = [ids[(i + (x & 1), (x >> 1) & 1, (x >> 2) & 1)] for x in range(8)]
        m.add_element("hex8", [ec[0], ec[1], ec[3], ec[2], ec[4], ec[5], ec[7], ec[6]], "S", "")
    m.knotendilatation = False
    Ka = asm.stiffness(m).toarray()
    m.knotendilatation = True
    Kb = asm.stiffness(m).toarray()
    check("ein Netz aus hex8 bleibt unveraendert",
          float(np.abs(Ka - Kb).max()) <= 1e-12 * float(np.abs(Ka).max()),
          f"{float(np.abs(Ka - Kb).max()):.2e}")


def test_der_preis_steht_in_der_matrix():
    """Der Verband koppelt Knoten, die vorher nichts miteinander zu tun
    hatten - die Matrix bekommt mehr Eintraege je Zeile. Das ist der Preis,
    und er gehoert gemessen."""
    m, _ids = _quader(4, 2, 2, 1.0, 0.5, 0.5, 0.3)
    m.knotendilatation = False
    Ka = asm.stiffness(m)
    m.knotendilatation = True
    Kb = asm.stiffness(m)
    ja, jb = Ka.nnz / Ka.shape[0], Kb.nnz / Kb.shape[0]
    check(f"mehr Eintraege je Zeile: {ja:.1f} -> {jb:.1f}", jb > ja * 1.5, f"Faktor {jb / ja:.2f}")
    check("die Matrix bleibt symmetrisch",
          abs((Kb - Kb.T)).max() <= 1e-6 * abs(Kb).max(), f"{abs((Kb - Kb.T)).max():.2e}")


def test_am_modell_gespeichert():
    """Die Einstellung haengt am Modell und ueberlebt Speichern und Laden."""
    import json
    import tempfile
    m, _ = _kragtraeger(0.3)
    m.knotendilatation = True
    d = m.to_dict()
    check("to_dict traegt die Einstellung", d.get("knotendilatation") is True, str(d.get("knotendilatation")))
    m2 = Model.from_dict(json.loads(json.dumps(d)))
    check("from_dict liest sie zurueck", m2.knotendilatation is True, str(m2.knotendilatation))
    m3 = Model.from_dict({k: v for k, v in d.items() if k != "knotendilatation"})
    check("ein altes Modell ohne die Einstellung rechnet wie bisher",
          m3.knotendilatation is False, str(m3.knotendilatation))
    del tempfile


def test_meldung_steht_im_ergebnis():
    """Befund B032 (24.09.2026): greift die Knotendilatation fuer einen
    Werkstoff nicht (die Regel verlangt 0 <= nu < 0,5), rechnet sein Bauteil mit
    dem gewoehnlichen Tetraeder weiter - bis dahin sagte das nur warnings.warn, und das erreichte
    weder Protokoll noch Bericht noch die exe. Jetzt steht es in res.info, in
    der Zusammenfassung und in den Hinweisen des Berichts. Geprueft mit
    nu = -0,1: bei nu = 0,5 rechnet schon der gewoehnliche tet4 nicht (laut,
    mit Elementnummer), die Meldung kaeme dort nie an."""
    from statik3d import solver
    for nu, soll in ((-0.1, True), (0.3, False)):
        m, _w = _kragtraeger(nu, h=0.2)
        m.knotendilatation = True
        an = solver.solve_all(m)
        res = next(iter(an.cases.values()))
        z = res.info.get("dilatation_hinweise") or []
        gebuendelt = solver.dilatation_gebuendelt(an.all_results().items())
        if soll:
            check("ν = −0,1: die Meldung steht im Ergebnis (Werkstoff, Querdehnzahl, Zahl der tet4)",
                  len(z) == 1 and "Querdehnzahl -0.1" in z[0] and "tet4)" in z[0], z[0] if z else "fehlt")
            check("… in der Zusammenfassung und gebündelt für den Bericht",
                  any("Knotendilatation:" in x for x in an.summary().splitlines()) and len(gebuendelt) == 1,
                  gebuendelt[0][:80] if gebuendelt else "")
        else:
            check("ν = 0,3: keine Meldung", not z and not gebuendelt)


def main():
    for t in (test_aufspaltung_ist_exakt, test_ein_element_bleibt_der_gewoehnliche_tetraeder,
              test_patchtest, test_versteifung_ist_weg, test_gleichgewicht_und_spannung,
              test_nur_tet4_ist_betroffen, test_der_preis_steht_in_der_matrix,
              test_am_modell_gespeichert, test_meldung_steht_im_ergebnis):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
