"""
Vertraeglichkeit der Volumentypen an einer gemeinsamen Seite
(elemente.VERTRAEGLICH, Auftrag VQ83/VQ203 vom 23.09.2026) - die Tabelle
gegen die Rechnung.

Fuer jedes Typpaar mit gleich geformter Seite liegen zwei Elemente an einer
gemeinsamen Seite; zufaellige Knotenverschiebungen, die Kantenmitten so
gebunden, wie die Assemblierung es tut (assemble.mittelknoten_bindungen),
und die Spur der Verschiebung auf der Seite von beiden Seiten verglichen:
gleich genau dann, wenn die Tabelle "direkt" oder "bindung" sagt; bei
"bindung" klafft sie ohne die Bindung (Ruecknahmeprobe). Dazu die
Tetraeder mit Ordnung p: neben tet4 rechnet es ("linear"), neben tet10 haelt
die Rechnung an ("nein"). Und die Vorgabe der Oberflaeche, tet10 + VQ83.

Aufruf:  python -m tests.test_vertraeglich
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm                              # noqa: E402
from statik3d import elemente as EL                               # noqa: E402
from statik3d import solver                                       # noqa: E402
from statik3d.elements import solid as sl                         # noqa: E402
from statik3d.model import Material, Model                        # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")


TYPEN = ("tet4", "tet10", "hex8", "hex20", "pent6", "pent15", "pyr5")
ZIEL = {"dreieck": np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], float),
        "viereck": np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)}


def knoten_natuerlich(typ):
    """Natuerliche Koordinaten aller Knoten: Ecken, dann Kantenmitten."""
    ecken = np.array(sl.ECKEN_NATUERLICH[typ], float)
    kanten = sl._KANTEN_QUADRATISCH.get(typ, ())
    return np.vstack([ecken] + [0.5 * (ecken[a] + ecken[b])[None] for a, b in kanten])


def form(seite):
    return "viereck" if len(seite) in (4, 8) else "dreieck"


def an_die_seite(typ, f, oben):
    """Knotenkoordinaten eines Elements, dessen lokale Seite f auf der
    Bezugsseite z = 0 liegt, das Element darueber (oben) oder darunter."""
    nat = knoten_natuerlich(typ)
    ecken = list(sl.FLAECHEN_ECKEN[typ][f])
    Z = ZIEL[form(ecken)]
    mitte = nat[:len(sl.ECKEN_NATUERLICH[typ])].mean(axis=0)
    ziel_mitte = np.array([0.4, 0.4, 0.7 if oben else -0.7])
    for folge in (list(range(len(ecken))), [0] + list(range(len(ecken) - 1, 0, -1))):
        # affine Abbildung aus drei Seitenecken und dem Schwerpunkt
        Q = np.array([nat[ecken[0]], nat[ecken[1]], nat[ecken[-1]], mitte])
        R = np.array([Z[folge[0]], Z[folge[1]], Z[folge[-1]], ziel_mitte])
        A = np.linalg.solve(np.hstack([Q, np.ones((4, 1))]), R)
        X = np.hstack([nat, np.ones((len(nat), 1))]) @ A
        if sl.jacobi_volumen(typ, X)["V"] > 0.0:
            return X
    raise AssertionError(f"{typ}: keine Lage mit positivem Volumen")


def paar(ta, fa, tb, fb):
    """Modell aus zwei Elementen an der gemeinsamen Bezugsseite."""
    m = Model("paar")
    m.add_material(Material("S", E=210e9, nu=0.3, rho=0.0))
    knoten: dict = {}

    def kn(p):
        k = tuple(np.round(p, 9))
        if k not in knoten:
            knoten[k] = m.add_node(*p)
        return knoten[k]
    for typ, f, oben in ((ta, fa, False), (tb, fb, True)):
        X = an_die_seite(typ, f, oben)
        m.add_element(typ, [kn(p) for p in X], "S")
    return m


def spur(m, i, f, u, x):
    """Verschiebung der Seite f von Element i am Punkt x (auf der Seite)."""
    e = m.elements[i]
    seite = [e.nodes[a] for a in sl.FLAECHEN[e.typ][f]]
    k = len(seite)
    P = np.asarray(m.nodes, float)[seite]
    if k in (3, 6):
        M = np.column_stack([P[1] - P[0], P[2] - P[0]])
        ab = np.linalg.lstsq(M, x - P[0], rcond=None)[0]
    else:
        M = np.column_stack([P[1] - P[0], P[3] - P[0]])
        ab = 2.0 * np.linalg.lstsq(M, x - P[0], rcond=None)[0] - 1.0
    N, _dN = sl.seite_N_dN(k, ab[0], ab[1])
    return N @ u[seite]


def test_tabelle_gegen_spur():
    rng = np.random.default_rng(11)
    geprueft, falsch = 0, []
    for ta in TYPEN:
        for tb in TYPEN:
            for fa, sa in enumerate(sl.FLAECHEN_ECKEN[ta]):
                for fb, sb in enumerate(sl.FLAECHEN_ECKEN[tb]):
                    if form(sa) != form(sb):
                        continue
                    # je Typpaar und Form nur die erste passende Seite
                    if any(form(sl.FLAECHEN_ECKEN[ta][g]) == form(sa) for g in range(fa)) or \
                            any(form(sl.FLAECHEN_ECKEN[tb][g]) == form(sb) for g in range(fb)):
                        continue
                    soll = EL.seiten_vertraeglich(
                        [s for s in EL.SEITENFORMEN[ta] if (s.startswith("quad")) == (form(sa) == "viereck")][0],
                        [s for s in EL.SEITENFORMEN[tb] if (s.startswith("quad")) == (form(sb) == "viereck")][0])
                    m = paar(ta, fa, tb, fb)
                    bind = asm.mittelknoten_bindungen(m)
                    u = rng.normal(size=(m.nn, 3))
                    frei = u.copy()
                    for mm, a, b in bind:
                        u[mm] = 0.5 * (u[a] + u[b])
                    Z = ZIEL[form(sa)]
                    pkt = [Z.mean(axis=0), 0.7 * Z[0] + 0.3 * Z[1], 0.2 * Z[0] + 0.3 * Z[1] + 0.5 * Z[-1]]
                    luecke = max(float(np.abs(spur(m, 0, fa, u, x) - spur(m, 1, fb, u, x)).max()) for x in pkt)
                    ohne = max(float(np.abs(spur(m, 0, fa, frei, x) - spur(m, 1, fb, frei, x)).max()) for x in pkt)
                    geprueft += 1
                    if soll == "direkt" and not (luecke < 1e-12 and not bind):
                        falsch.append(f"{ta}/{tb} direkt: Lücke {luecke:.1e}, {len(bind)} Bindungen")
                    if soll == "bindung" and not (luecke < 1e-12 and bind and ohne > 1e-3):
                        falsch.append(f"{ta}/{tb} bindung: Lücke {luecke:.1e}, ohne Bindung {ohne:.1e}")
    check(f"Tabelle gegen Spur: {geprueft} Typpaare an gleich geformter Seite, "
          "„direkt“ und „Bindung“ konform", geprueft >= 40 and not falsch, "; ".join(falsch[:3]))


def test_tetp_und_vorgabe():
    """tetp neben tet4 rechnet (linear), neben tet10 haelt es an (nein); die
    Vorgabe der Oberflaeche tet10 + VQ83 (hex8, entartbar) ist zulaessig."""
    for tb, soll_laeuft in (("tet4", True), ("tet10", False)):
        m = paar("tet4", 0, tb, 0)
        # das untere Element wird zum tetp2 (dieselben vier Ecken)
        e = m.elements[0]
        e.typ, e.nodes = "tetp2", list(e.nodes[:4])
        m._tetp_version = getattr(m, "_tetp_version", 0) + 1
        for n in range(m.nn):
            if m.nodes[n][2] <= 1e-12:
                m.fix(int(n), "all")
        top = int(np.argmax(np.asarray(m.nodes)[:, 2]))
        m.load_node(top, Fz=-1e3)
        try:
            next(iter(solver.solve_all(m).cases.values()))
            lief, text = True, "rechnet"
        except Exception as ex:                  # noqa: BLE001
            lief, text = False, str(ex)[:80]
        art = EL.VERTRAEGLICH[("tetp2", tb)]
        check(f"tetp2 neben {tb}: Tabelle „{art}“, die Rechnung {'läuft' if soll_laeuft else 'hält an'}",
              lief == soll_laeuft and (art == "linear") == soll_laeuft, text)
    check("Vorgabe tet10 + VQ83: zulässig (über Pyramiden, Keile mit Bindung, Tetraeder mit Bindung)",
          EL.VERTRAEGLICH[("tet10", "hex8")] == "uebergang"
          and EL.VERTRAEGLICH[("tet10", "pent6")] == "bindung"
          and EL.VERTRAEGLICH[("tet10", "tet4")] == "bindung"
          and EL.VERTRAEGLICH[("tet10", "pyr5")] == "bindung")
    sym = all(EL.VERTRAEGLICH[(a, b)] == EL.VERTRAEGLICH[(b, a)] for a in EL.SEITENFORMEN
              for b in EL.SEITENFORMEN)
    check("die Tabelle ist symmetrisch", sym)


def main():
    print("=" * 100)
    print("STATIK3D - Vertraeglichkeit der Volumentypen an einer gemeinsamen Seite")
    print("=" * 100)
    for t in (test_tabelle_gegen_spur, test_tetp_und_vorgabe):
        try:
            t()
        except Exception as ex:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    ok = sum(1 for _n, o in RESULTS if o)
    print(f"\nErgebnis: {ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
