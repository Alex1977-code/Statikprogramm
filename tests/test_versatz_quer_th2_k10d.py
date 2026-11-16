"""
Versatz quer zur Stabachse nach Theorie II. Ordnung bei geteilten Stäben
(Runde k10d, Nachbesserung 3, Stand 74).

Befund der Gegenprüfung Runde 3 vom 16.11.2026 zu 2858a4e2: IPE 300, 6 m,
N = 200 kN, Versatz y = 0,1 m an beiden Enden, Gabellager auf der
Knotenlinie. Nach Theorie II. Ordnung rechnete das Programm, sobald der Stab
in mehreren Elementen lag (eigene Elemente oder interne Stabteilung):

- ohne Imperfektion Mz 53,57 (Stabteilung 10) bzw. 53,77 kNm (120 Elemente)
  statt 54,07 kNm, Randmoment 19,82 statt N e = 20,00 kNm;
- mit Vorkrümmung 64,80 statt 65,59 kNm (9,85 N/mm² auf der unsicheren
  Seite); seit Nachbesserung 2 (Zwangsteilung in 10 Teile) auch mit einem
  Element und Stabteilung 1.

Ursache: der Armanteil der geometrischen Steifigkeit (asm.versatz_arm_kg)
nahm in der Iteration die Stabendkraft ohne k_G. An einem Zwischenknoten,
dessen beide Arme zu demselben Punkt der Stabachse führen, summieren sich
diese Kräfte nicht zu 0 (es fehlt N θ), und V der Vorkrümmung am Arm zählte
als Kraft im Arm. Seither nimmt der Arm die Stabendkraft mit k + k_G des
vorigen Schritts, ohne V.

Bezüge je auf zwei Wegen (Fehlerschwelle 1 N/mm² am Rand, |ΔMz| / W_el,z):
geschlossen mit Schubverformung, M0/cos(kL/2) + q E I/N (1/cos(kL/2) − 1)
mit k² = N/(E I (1 − N/(G A_s))), und das gleichwertige Programmmodell mit
dem Balken auf y = 0,1 m in 120 Elementen und steifen Balken als Armen.

Aufruf:  python -m tests.test_versatz_quer_th2_k10d
"""
import contextlib
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


N = 200e3
L = 6.0
SEC = "IPE 300"


def _modell():
    from statik3d.model import Model, Material
    from statik3d.profiles import make_section
    m = Model("Q")
    m.add_material(Material.steel("S235"))
    m.add_section(make_section(SEC))
    return m


def stab(e_y=0.0, e_z=0.0, n_el=1, teilung=1, imp=True, mz_knoten=0.0):
    """IPE 300, 6 m, N = 200 kN Druck, Gabellager auf der Knotenlinie,
    Versatz (0, e_y, e_z) an beiden Enden jedes Elements. ``mz_knoten``:
    statt des Versatzes Knotenmomente Mz an den Enden."""
    from statik3d import mesher
    m = _modell()
    ids = mesher.line_of_beams(m, "S235", SEC, (0, 0, 0), (L, 0, 0), n_el)
    ne = len(m.elements)
    if e_y or e_z:
        for e in m.elements:
            e.exzentrizitaet = [[0.0, e_y, e_z], [0.0, e_y, e_z]]
    m.fix(ids[0], [0, 1, 2, 3])
    m.fix(ids[-1], [1, 2, 3])
    m.load_node(ids[-1], Fx=-N)
    if mz_knoten:
        m.load_node(ids[0], Mz=mz_knoten)
        m.load_node(ids[-1], Mz=-mz_knoten)
    mem = m.add_member("T1", list(range(ne)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = imp
    m.netz.stabteilung = teilung
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie="II")
    return m


def starr_arme(e_y, imp, n=120):
    """Weg 2: der Balken auf y = e_y in ``n`` Elementen, steife Balken als
    Arme von den Lagerknoten (y = 0) zu den Stabenden; die Vorkrümmung setzt
    das Programm am Stab aus den Balkenelementen an."""
    from statik3d import mesher
    from statik3d.profiles import make_section
    m = _modell()
    st = make_section(SEC)
    st.name = "STARR"
    for a in ("A", "Iy", "Iz", "It"):
        setattr(st, a, getattr(st, a) * 1e3)
    m.add_section(st)
    ids = mesher.line_of_beams(m, "S235", SEC, (0, e_y, 0), (L, e_y, 0), n)
    nb = len(m.elements)
    A, B = m.add_node(0, 0, 0), m.add_node(L, 0, 0)
    m.add_element("beam", [A, ids[0]], "S235", "STARR")
    m.add_element("beam", [B, ids[-1]], "S235", "STARR")
    m.fix(A, [0, 1, 2, 3])
    m.fix(B, [1, 2, 3])
    m.load_node(B, Fx=-N)
    mem = m.add_member("T1", list(range(nb)))
    mem.lt_check = True
    mem.design = True
    m.design.imperfektionen = imp
    m.netz.stabteilung = 1
    m.add_combination("K1", {m.active_case: 1.0}, "ULS", theorie="II")
    return m


def geschlossen(e, imp, achse="z"):
    """Weg 1: geschlossen mit Schubverformung. Endmoment M0 = N e:
    M(L/2) = M0/cos(kL/2); Vorkrümmung q = 8 N e0/L², e0 = L/250 (Knicklinie
    b, IPE 300 um z, elastisch): q E I/N (1/cos(kL/2) − 1)."""
    m = _modell()
    sec, mat = m.sections[SEC], m.materials["S235"]
    I = float(sec.Iz if achse == "z" else sec.Iy)
    As = float((sec.Asy if achse == "z" else sec.Asz) or 0.0)
    c = 1.0 - N / (mat.G * As) if As > 0 else 1.0
    k = math.sqrt(N / (mat.E * I * c))
    M = N * e / math.cos(k * L / 2.0)
    if imp:
        q = 8.0 * N * (L / 250.0) / L ** 2
        M += q * mat.E * I / N * (1.0 / math.cos(k * L / 2.0) - 1.0)
    return M


def rechnen(m, comp="Mz", workers=1):
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=workers, design=False)
    r = an.combinations["K1"]
    mf = solver.member_forces(m, r, m.members["T1"], n=241)
    return an, r, float(np.abs(mf[comp]).max()), mf


def _w(achse="z"):
    from statik3d.profiles import make_section
    s = make_section(SEC)
    return float(s.Wel_z if achse == "z" else s.Wel_y)


def _sigma(a, b, achse="z"):
    return abs(a - b) / _w(achse) / 1e6


def _teile(r):
    t = (getattr(r, "info", None) or {}).get("stabteilung") or {}
    return sum(int(v) for v in t.values()) if t else 1


_BEZUG: dict = {}


def bezug(e_y, imp):
    key = (e_y, imp)
    if key not in _BEZUG:
        R1 = geschlossen(abs(e_y), imp)
        _a, _r, R2, _mf = rechnen(starr_arme(e_y, imp))
        _BEZUG[key] = (R1, R2)
    return _BEZUG[key]


def test_bezug():
    """Die beiden Wege stimmen überein (< 0,1 N/mm²)."""
    for e_y, imp in ((0.1, True), (0.1, False), (0.05, True)):
        R1, R2 = bezug(e_y, imp)
        check(f"Bezug y {e_y} m, Vorkrümmung {'an' if imp else 'aus'}: geschlossen und steifer Arm gleich",
              _sigma(R1, R2) < 0.1, f"{R1 / 1e3:.4f} / {R2 / 1e3:.4f} kNm")


def test_quer():
    """Versatz quer, Theorie II. Ordnung: Feldmoment wie die Bezüge, das
    Randmoment ist N e, in jeder Teilung."""
    for e_y, imp, faelle in ((0.1, True, ((1, 1), (1, 10), (10, 1))),
                             (0.1, False, ((1, 10), (10, 1), (40, 1))),
                             (0.05, True, ((1, 1), (10, 1)))):
        R1, R2 = bezug(e_y, imp)
        for ne, t in faelle:
            _a, r, M, mf = rechnen(stab(e_y=e_y, n_el=ne, teilung=t, imp=imp))
            Ma, Mb = abs(float(mf["Mz"][0])), abs(float(mf["Mz"][-1]))
            tag = f"Th II, y {e_y} m, {'mit' if imp else 'ohne'} Vorkrümmung, {ne} El., Stabteilung {t}"
            check(f"{tag}: Mz wie beide Bezüge (< 1 N/mm²)",
                  _sigma(M, R1) < 1.0 and _sigma(M, R2) < 1.0,
                  f"{M / 1e3:.4f} gegen {R1 / 1e3:.4f}/{R2 / 1e3:.4f} kNm, {_sigma(M, R1):.2f} N/mm², "
                  f"{_teile(r)} Teile")
            check(f"{tag}: Randmoment N e an beiden Enden (< 0,05 N/mm²)",
                  _sigma(Ma, N * e_y) < 0.05 and _sigma(Mb, N * e_y) < 0.05,
                  f"{Ma / 1e3:.4f} / {Mb / 1e3:.4f} gegen {N * e_y / 1e3:.4f} kNm")


def test_gleichwertig_knotenmoment():
    """Versatz −0,1 m mit Vorkrümmung ist dasselbe wie Knotenmomente N e ohne
    Versatz (der Arm überträgt keine Querkraft): gleiches Feldmoment; die
    Vorkrümmung wirkt hier gegen das Endmoment, geschlossen
    54,0717 − 11,5202 kNm."""
    R = geschlossen(0.1, False) - (geschlossen(0.1, True) - geschlossen(0.1, False))
    for ne, t in ((1, 1), (10, 1)):
        _a, _r, Mv, _mf = rechnen(stab(e_y=-0.1, n_el=ne, teilung=t))
        _a, _r, Mk, _mf = rechnen(stab(n_el=ne, teilung=t, mz_knoten=-N * 0.1))
        check(f"Th II, y −0,1 m, {ne} El., Stabteilung {t}: Mz wie Knotenmomente 20 kNm ohne Versatz "
              "und wie geschlossen", _sigma(Mv, Mk) < 0.1 and _sigma(Mv, R) < 1.0,
              f"{Mv / 1e3:.4f} / {Mk / 1e3:.4f} / {R / 1e3:.4f} kNm, {_sigma(Mv, Mk):.2f} N/mm²")


def test_reaktion():
    """Ohne Querlast keine Querkraft an den Lagern (Gleichgewicht am Stab)."""
    _a, r, _M, _mf = rechnen(stab(e_y=0.1, n_el=10, teilung=1))
    R = np.asarray(r.reactions, float) if not isinstance(r.reactions, dict) else None
    ry = float(np.abs(R[:, 1]).max()) if R is not None and R.ndim == 2 else float("nan")
    check("Th II, y 0,1 m, 10 El., Vorkrümmung: Lagerkraft quer |Ry| < 1 N", ry < 1.0, f"{ry:.3f} N")


def test_z_unveraendert():
    """Versatz z (starke Achse, ohne Vorkrümmung in dieser Achse): My wie
    geschlossen, auch in mehreren Elementen."""
    for e_z in (0.1, 0.3):
        R = geschlossen(e_z, False, "y")
        for ne, t in ((1, 1), (10, 1)):
            _a, _r, M, _mf = rechnen(stab(e_z=e_z, n_el=ne, teilung=t), comp="My")
            check(f"Th II, z {e_z} m, {ne} El., Stabteilung {t}: My wie geschlossen (< 0,1 N/mm²)",
                  _sigma(M, R, "y") < 0.1, f"{M / 1e3:.4f} gegen {R / 1e3:.4f} kNm")


def test_stuetze_seitlich():
    """Räumlich: Gelenkstütze 4 m in 16 Elementen mit Versatz z 0,3 m, α_cr
    1,4, Querlasten 1 kN in y und z in der Mitte (Prüfung A4 aus
    test_versatz_achsen_lotrecht). Bezug: der Stab auf z = 0,3 m, steife
    Balken als Arme an beiden Lagern und an der Lastmitte. Verdrehung φx und
    u_z in der Mitte wie dort."""
    from statik3d import theorie2
    from statik3d.model import Model, Material, Section
    from tests.test_versatz_achsen_lotrecht import _stuetze_seitlich, _p_fuer, E, NU
    Ls = 4.0
    P = _p_fuer(1.4)
    quer = {"Fy": 1e3, "Fz": 1e3}
    m, ids = _stuetze_seitlich(0.3, P, quer=quer)
    r, info = _still(theorie2.solve_theorie2, m, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False)
    u = np.asarray(r.u)[ids[len(ids) // 2]]
    g = Model("G")
    g.add_material(Material("ST", E=E, nu=NU, rho=0.0, fy=355e6))
    g.add_section(Section("Q", A=1e-2, Iy=1e-4, Iz=1e-4, It=1e-5, zmax=0.1, ymax=0.05))
    g.add_section(Section("S", A=1e2, Iy=1.0, Iz=1.0, It=0.1, zmax=0.1, ymax=0.05))
    g.design.imperfektionen = False
    g.netz.stabteilung = 1
    b = [g.add_node(Ls * k / 16, 0, 0.3) for k in range(17)]
    for k in range(16):
        g.add_element("beam", [b[k], b[k + 1]], "ST", "Q")
    A, B, C = g.add_node(0, 0, 0), g.add_node(Ls, 0, 0), g.add_node(Ls / 2, 0, 0)
    for k, z in ((A, b[0]), (B, b[-1]), (C, b[8])):
        g.add_element("beam", [k, z], "ST", "S")
    g.fix(A, [0, 1, 2, 3])
    g.fix(B, [1, 2])
    g.load_node(B, Fx=-P)
    g.load_node(C, **quer)
    g.load_cases["LF1"].theorie = "II"
    rg, _ig = _still(theorie2.solve_theorie2, g, {"LF1": 1.0}, "LF1", imperfektionen=False, stabteilung=False)
    ug = np.asarray(rg.u)[C]
    check("Th II, Stütze 16 El. mit Versatz z 0,3 m, α_cr 1,4: φx in der Mitte wie steife Arme (1 %)",
          info.gerechnet and abs(u[3] / ug[3] - 1) < 1e-2,
          f"{u[3] * 1e3:.5f} / {ug[3] * 1e3:.5f} mrad")
    check("Th II, Stütze 16 El. mit Versatz z 0,3 m, α_cr 1,4: u_z in der Mitte wie steife Arme (0,001 mm)",
          abs(u[2] - ug[2]) < 1e-6, f"{u[2] * 1e3:.4f} / {ug[2] * 1e3:.4f} mm")


def test_arbeitsprozesse():
    """Seriell und über Arbeitsprozesse: dasselbe Ergebnis, Mz_Ed wie der Bezug."""
    from statik3d import solver
    from statik3d.ec3.design import check_members
    R1, R2 = bezug(0.1, True)
    m = stab(e_y=0.1)
    m.design.stations = 241
    an = _still(solver.solve_all, m, workers=1, design=False)
    a = _still(check_members, m, an, use_jobs=False)
    b = _still(check_members, m, an, use_jobs=True, workers=2)
    sa, sb = a.members["T1"].stability[0], b.members["T1"].stability[0]
    check("Arbeitsprozesse, y 0,1 m: Ausnutzung und Mz_Ed bitgleich mit seriell",
          a.util_max == b.util_max and sa["Mz_Ed"] == sb["Mz_Ed"],
          f"{a.util_max!r} / {b.util_max!r}; {sa['Mz_Ed']!r} / {sb['Mz_Ed']!r}")
    check("Arbeitsprozesse, y 0,1 m: Mz_Ed wie beide Bezüge (< 1 N/mm²)",
          _sigma(abs(float(sb["Mz_Ed"])), R1) < 1.0 and _sigma(abs(float(sb["Mz_Ed"])), R2) < 1.0,
          f"{float(sb['Mz_Ed']) / 1e3:.4f} gegen {R1 / 1e3:.4f}/{R2 / 1e3:.4f} kNm")


def test_merkmal():
    from statik3d import rechenverfahren as rv
    mk = rv.merkmal("versatz_arm_endkraft_th2")
    check("Merkmal versatz_arm_endkraft_th2: Stand 74, Fehlerkorrektur",
          mk is not None and mk.wechsel[-1].stand == 74 and mk.wechsel[-1].art == rv.FEHLERKORREKTUR,
          f"{mk and mk.texte}")
    # Zusammenfuehrung k10 (16.11.2026): der Stand des Programms reicht den
    # Wechsel ein und ist der hoechste der Tabelle (spaetere Staende kommen dazu)
    check("Verfahrensstand mindestens 74 und der hoechste der Tabelle",
          rv.VERFAHRENSSTAND >= 74
          and rv.VERFAHRENSSTAND == max(w.stand for x in rv.MERKMALE for w in x.wechsel),
          f"{rv.VERFAHRENSSTAND}")
    if mk is not None:
        check("Merkmal versatz_arm_endkraft_th2: Modell mit Versatz betroffen, ohne Versatz nicht",
              mk.betrifft(stab(e_y=0.1)) and not mk.betrifft(stab()), "")


def main():
    for t in (test_bezug, test_quer, test_gleichwertig_knotenmoment, test_reaktion, test_z_unveraendert,
              test_stuetze_seitlich, test_arbeitsprozesse, test_merkmal):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
        sys.stdout.flush()
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
