"""
Zusammenfuehrung k10, Nachbesserung 1 (16.11.2026): Lasten, die unter der
Elementmaske entfallen, sind kein Anker fuer den Anschluss eines Stabendes
nach Theorie III. Ordnung.

theorie3._th3_wirkung (fix/k10-th3) zaehlt den Anschluss eines Stabendes an
einen Koerper auch dann, wenn nur das Stabende mittraegt und die
Koerperseite einen Lager- oder Lastknoten erreicht (theorie3._ankerknoten).
Als Lastknoten zaehlte jede Knotenlast der Rechnung - auch eine an einem
Knoten des abgeschalteten Koerpers, die assemble.load_vector unter der Maske
gar nicht anlegt (situationen.wirksame_knoten). Theorie III. Ordnung wies
dann ein Modell ab, das Theorie I. Ordnung, die Hand, Stand 65 (e2799fa2)
und fix/k10-maske2 (00ad5ed7) rechnen.

Pruefkoerper: Kragarm a-b (L = 3 m, eingespannt in a, E I = 210 GPa mal
8e-5 m^4), toter Arm c-d (eingespannt in c) in einer Situation abgeschaltet
oder als Stab „aus“; Q (3; 1; 0,5) ohne Element. 1 kN abwaerts an b.
* V1: RBE3 „Stabende“ Master b, Slaves d und Q, 2 kN an d.
* V2: starre Kopplung „Stabende“ b-d (Gruppe fugen.STABENDE_GRUPPE), 2 kN an d.
* V3: RBE3 wie V1 ohne Last an d, dazu RBE2 Q-P (P ohne Element), 2 kN an P.
Die Last an d bzw. P entfaellt unter der Maske (der Koerper ist
abgeschaltet und lebt ueber den Stab nicht wieder auf).

Sollwerte, je zwei Wege: w(b) = F L³/(3 E I) = 0,535714 mm (Hand) und
gleich Theorie I. Ordnung derselben Rechnung; Summe Rz = 1 000 N. Theorie
III. Ordnung rechnet (kein Rueckfall auf Theorie I. Ordnung), die
Modellpruefung (theorie3.kopplung_sperre_modell) meldet nichts.

Gegenproben, die weiter abweisen muessen: starre Kopplung „Stabende“ b-Q
mit 1 kN an Q (Q ohne Element, die Last wirkt) und die Rechnung ohne Maske
(der Arm c-d traegt, d ist wirksamer Koerperknoten).

Vor der Behebung: V1 bis V3 abgewiesen mit „Theorie III. Ordnung rechnet
keine Starrkörper“ bzw. „keine starren Knotenkopplungen“.

Aufruf:  python -m tests.test_th3_lastanker_k10e
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []

E = 210e9
L = 3.0
I = 8e-5
F = 1e3
W_HAND = F * L ** 3 / (3 * E * I) * 1e3     # mm


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:100s} {str(detail)[:240]}")
    return ok


def _still(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def basis(maske):
    """(Modell, a, b, c, d, Q); ``maske``: "situation", "aus" oder "" (ohne)."""
    from statik3d.model import Model, Material, Section, Situation
    m = Model("k10e")
    m.add_material(Material("ST", E=E, nu=0.3, rho=0.0, fy=355e6))
    m.add_section(Section("Q", A=1e-2, Iy=I, Iz=I, It=1e-5, zmax=0.1, ymax=0.1))
    m.design.imperfektionen = False
    m.netz.stabteilung = 1
    a = m.add_node(0, 0, 0)
    b = m.add_node(L, 0, 0)
    m.add_element("beam", [a, b], "ST", "Q")
    m.fix(a, "all")
    c = m.add_node(0, 2, 0)
    d = m.add_node(L, 2, 0)
    e_arm = m.add_element("beam", [c, d], "ST", "Q")
    if maske == "aus":
        m.add_member("S2", [e_arm], aus=True)
    m.fix(c, "all")
    m.add_load_case("LF1", "G")
    m.load_cases["LF1"].gravity = [0.0, 0.0, 0.0]
    if maske == "situation":
        m.situationen["s"] = Situation("s", "", [e_arm])
        m.load_cases["LF1"].situation = "s"
    q = m.add_node(L, 1, 0.5)
    m.load_node(b, Fz=-F, case="LF1")
    return m, a, b, c, d, q


def stabende(m, b, q):
    """Starre Kopplung „Stabende“ b-q (drei Verschiebungen, wie
    test_stabende_kopplung_k10.stabende)."""
    from statik3d.model import Kopplung
    from statik3d.fugen import STABENDE_GRUPPE
    eins = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    m.kopplungen.append(Kopplung(b, q, eins, [float("inf")] * 3, STABENDE_GRUPPE + f"K{b}"))


def variante(name, maske):
    from statik3d import stabeinleitung as se
    m, a, b, c, d, q = basis(maske)
    if name == "V1":
        m.add_starrkoerper(b, [d, q], "RBE3", name=se.STABENDE + "1")
        m.load_node(d, Fz=-2 * F, case="LF1")
    elif name == "V2":
        stabende(m, b, d)
        m.load_node(d, Fz=-2 * F, case="LF1")
    elif name == "V3":
        m.add_starrkoerper(b, [d, q], "RBE3", name=se.STABENDE + "1")
        p = m.add_node(L, 1.5, 0.5)
        m.add_starrkoerper(q, [p], "RBE2", name="RBE2 Q-P")
        m.load_node(p, Fz=-2 * F, case="LF1")
    elif name == "G1":
        stabende(m, b, q)
        m.load_node(q, Fz=-F, case="LF1")
    else:
        raise ValueError(name)
    return m, b


def kombination(m, maske):
    """Kombination K3 = LF1 nach Theorie III. Ordnung (in der Situation)."""
    m.add_combination("K3", {"LF1": 1.0}, "ULS", theorie="III")
    if maske == "situation":
        m.combinations["K3"].situation = "s"


def rechnen(m):
    """(Ergebnis LF1 nach Theorie I. Ordnung, Ergebnis K3 nach Theorie III.
    Ordnung oder None)."""
    from statik3d import solver
    an = _still(solver.solve_all, m, workers=1, design=False)
    return an.cases["LF1"], an.combinations.get("K3")


def main():
    from statik3d.theorie3 import kopplung_sperre_modell
    check(f"Hand F L³/(3 E I) = 0,535714 mm", abs(W_HAND - 0.535714) < 5e-7, f"{W_HAND:.6f}")
    for maske in ("situation", "aus"):
        for v in ("V1", "V2", "V3"):
            tag = f"{v}, {maske}"
            m, b = variante(v, maske)
            kombination(m, maske)
            sperre = kopplung_sperre_modell(m)
            r1, r3 = rechnen(m)
            u1 = np.asarray(r1.u).reshape(-1, 6)
            R1 = np.asarray(r1.reactions).reshape(-1, 6)
            w1 = -u1[b, 2] * 1e3
            check(f"{tag}: Theorie I w(b) = Hand 0,535714 mm", abs(w1 - W_HAND) < 1e-4, f"{w1:.6f}")
            check(f"{tag}: Theorie I Summe Rz = 1 000 N", abs(R1[:, 2].sum() - F) < 1e-3,
                  f"{R1[:, 2].sum():.3f}")
            check(f"{tag}: Modellpruefung meldet keine Abweisung", not sperre, str(sperre)[:200])
            if not check(f"{tag}: Theorie III gerechnet", r3 is not None, "" if r3 is not None else "kein Ergebnis"):
                continue
            fehler = r3.info.get("theorie_fehler")
            theorie = str(r3.info.get("theorie"))
            check(f"{tag}: Theorie III ohne Abweisung, kein Rueckfall",
                  not fehler and "III" in theorie, f"{theorie}: {str(fehler)[:160]}")
            u3 = np.asarray(r3.u).reshape(-1, 6)
            R3 = np.asarray(r3.reactions).reshape(-1, 6)
            w3 = -u3[b, 2] * 1e3
            check(f"{tag}: Theorie III w(b) = Hand und Theorie I", abs(w3 - W_HAND) < 1e-4
                  and abs(w3 - w1) < 1e-4, f"Th III {w3:.6f}, Th I {w1:.6f}, Hand {W_HAND:.6f}")
            check(f"{tag}: Theorie III Summe Rz = 1 000 N", abs(R3[:, 2].sum() - F) < 1e-3,
                  f"{R3[:, 2].sum():.3f}")
    # Gegenproben: die Abweisung bleibt, wo die Last wirkt bzw. der Koerper traegt
    for maske in ("situation", "aus"):
        m, b = variante("G1", maske)
        kombination(m, maske)
        sperre = kopplung_sperre_modell(m)
        r1, r3 = rechnen(m)
        check(f"G1 (Last an Q ohne Element), {maske}: Modellpruefung weist ab",
              any("starren Knotenkopplungen" in t for t in sperre), str(sperre)[:160])
        fehler = str((r3.info.get("theorie_fehler") if r3 is not None else "") or "")
        check(f"G1, {maske}: Theorie III weist ab", "starren Knotenkopplungen" in fehler, fehler[:160])
    for v, text in (("V1", "Starrkörper"), ("V2", "starren Knotenkopplungen")):
        m, b = variante(v, "")
        kombination(m, "")
        sperre = kopplung_sperre_modell(m)
        check(f"{v} ohne Maske (Koerper traegt): Modellpruefung weist ab",
              any(text in t for t in sperre), str(sperre)[:160])

    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
