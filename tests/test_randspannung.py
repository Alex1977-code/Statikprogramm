"""
Randspannung an freien Oberflaechen (Auftrag B6, 23.09.2026): die
geglaettete Knotenspannung wird an freien Oberflaechen auf sigma n = 0
gezogen (solver.rand_projizieren), Einstellung Model.randspannung = "frei"
(Vorgabe) oder "gemittelt" (bisher).

Geprueft wird, dass nur wirklich freie Knoten projiziert werden (je Ausnahme
eine Pruefung), dass Kanten und Ecken alle Normalen zugleich erfuellen, dass
einspringende Kanten unangetastet bleiben, was es am Kirsch-Loch und am
Kragarm bringt (und wo es schadet), und dass Einstellung, Ueberlagerung und
Nachweis-Beschriftung stimmen.

Aufruf:  python -m tests.test_randspannung
"""
import os
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import solver                                       # noqa: E402
from statik3d.elements import solid as sl                         # noqa: E402
from statik3d.model import (FaceLoad, Kopplung, Model, StarrKoerper,  # noqa: E402
                            Zwangsverformung, ContactPair)
from tests import pruefkoerper as pk                              # noqa: E402
from tests import pruefkoerper_kirsch as kk                       # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------
def block(nx=6, ny=6, nz=2):
    """hex8-Quader 1 x 1 x 0,5 m, ohne Lager und Last (nur fuer die Auswahl)."""
    return pk.quader("hex8", nx, ny, nz, 1.0, 1.0, 0.5)


def knotentabelle(m, keim=1):
    """Eine geglaettete Knotentabelle wie randspannung_knoten sie liefert,
    mit zufaelligen Spannungen je Elementecke."""
    rng = np.random.default_rng(keim)
    ecken = {i: rng.normal(0, 1e8, (len(sl.ECKEN_NATUERLICH[e.typ]), 6))
             for i, e in enumerate(m.elements) if e.typ in sl.ECKEN_NATUERLICH}
    return solver.randspannung_knoten(m, ecken)


def projiziert(m, knoten, faelle=None):
    """{Knoten: (projiziert?, Spannung vorher, nachher)} fuer die gefragten Knoten."""
    sk = knotentabelle(m)
    vorher = np.asarray(sk["spannung"], float).copy()
    solver.rand_projizieren(m, sk, None, faelle)
    aus = {}
    for n in knoten:
        j = np.flatnonzero(np.asarray(sk["knoten"]) == n)
        if len(j) != 1:
            aus[n] = (False, None, None)
            continue
        j = int(j[0])
        aus[n] = (bool(sk["frei"][j]), vorher[j], np.asarray(sk["spannung"])[j])
    return aus


def tensor(s):
    return np.array([[s[0], s[3], s[5]], [s[3], s[1], s[4]], [s[5], s[4], s[2]]])


# --------------------------------------------------------------------------
# Auswahl der freien Knoten
# --------------------------------------------------------------------------
def test_freie_flaeche_und_ausnahmen():
    """Auf der Deckflaeche (Ziel T) und weit davon (F): ohne
    Ausnahme werden beide projiziert, sigma n = 0 mit n = z. Jede Ausnahme an
    T sperrt T (und die Knoten der Seiten, die T beruehren), F bleibt frei."""
    m, ids = block()
    # T und F so weit auseinander, dass keine Seite an T eine Seite an F
    # beruehrt (die Regel sperrt alle Knoten einer nicht freien Seite)
    T, F = ids[(4, 4, 2)], ids[(1, 1, 2)]
    p = projiziert(m, [T, F])
    s = tensor(p[T][2])
    check("freie Deckfläche: T und F werden projiziert", p[T][0] and p[F][0])
    check("… und dort gilt σ·n = 0 (n = z)", np.abs(s @ [0, 0, 1.0]).max() < 1e-6,
          f"|σ n| {np.abs(s @ [0, 0, 1.0]).max():.1e} Pa")
    d = np.abs(p[T][2] - p[T][1])
    check("… die Tangentialanteile bleiben (σxx, σyy, σxy)", d[[0, 1, 3]].max() == 0.0)

    anderer = ids[(4, 4, 0)]

    def mit(name, aendern):
        m2, ids2 = block()
        aendern(m2, ids2)
        q = projiziert(m2, [T, F])
        check(f"Ausnahme {name}: T wird nicht projiziert, F schon", (not q[T][0]) and q[F][0],
              f"T {q[T][0]}, F {q[F][0]}")

    def elemente_an(m2, n):
        return [i for i, e in enumerate(m2.elements) if n in e.nodes]
    mit("Lager", lambda m2, i2: m2.fix(T, "all"))
    mit("Federlager", lambda m2, i2: m2.fix(T, [2], stiffness=[1e6]))
    mit("Knotenlast", lambda m2, i2: m2.load_node(T, Fz=-1.0))

    def seitenlast(m2, i2):
        i = elemente_an(m2, T)[0]
        e = m2.elements[i]
        for s_, f in enumerate(sl.FLAECHEN[e.typ]):
            if T in [e.nodes[a] for a in f] and all(abs(m2.nodes[e.nodes[a]][2] - 0.5) < 1e-9 for a in f):
                m2.case().face_loads.append(FaceLoad(elem=i, p=1e6, face=s_))
                return
        raise AssertionError("keine Deckseite an T")
    mit("Seitenlast an einer Seite mit T", seitenlast)
    mit("Zwangsverformung", lambda m2, i2: m2.case().zwangsverformungen.append(
        Zwangsverformung(node=T, dofs=[2], u=[0, 0, 1e-3, 0, 0, 0])))
    mit("Kopplung", lambda m2, i2: m2.kopplungen.append(Kopplung(node_a=T, node_b=anderer)))
    mit("Starrkörper", lambda m2, i2: m2.starrkoerper.append(StarrKoerper("SK", master=anderer, slaves=[T])))
    mit("Kontaktpaar (Slave)", lambda m2, i2: m2.contact_pairs.append(ContactPair("K", slave_nodes=[T])))
    mit("Kontaktpaar (Master-Element)", lambda m2, i2: m2.contact_pairs.append(
        ContactPair("K", master_elements=[elemente_an(m2, T)[0]])))
    mit("getrennte Fugenknoten", lambda m2, i2: m2.getrennte_knoten.update({"Fuge": [[T, anderer]]}))
    mit("Kontaktlager", lambda m2, i2: m2.contact_supports.append(SimpleNamespace(node=T)))
    mit("Spaltelement", lambda m2, i2: m2.gap_elements.append(SimpleNamespace(node_a=T, node_b=anderer)))
    mit("Linienlager", lambda m2, i2: m2.line_supports.append(SimpleNamespace(nodes=[T])))
    mit("Flächenlager", lambda m2, i2: m2.surface_supports.append(SimpleNamespace(nodes=[T])))
    mit("Punktmasse", lambda m2, i2: setattr(m2, "punktmassen", [SimpleNamespace(node=T)]))
    mit("Stab- oder Federelement am Knoten", lambda m2, i2: m2.add_element("feder", [T, anderer], "S"))

    def zwei_koerper(m2, i2):
        for i in elemente_an(m2, T)[:2]:
            m2.elements[i].group = "B"
    mit("Grenze zweier Körper (verschweißt)", zwei_koerper)

    def zwei_werkstoffe(m2, i2):
        from statik3d.model import Material
        m2.add_material(Material("S2", E=70e9, nu=0.33, rho=2700.0))
        for i in elemente_an(m2, T)[:2]:
            m2.elements[i].mat = "S2"
    mit("Grenze zweier Werkstoffe", zwei_werkstoffe)

    # Die Last eines anderen Lastfalls sperrt nur in dessen Rechnung
    m2, _i2 = block()
    m2.add_load_case("Q", "Q")
    m2.load_node(T, Fz=-1.0, case="Q")
    q_lf1 = projiziert(m2, [T], faelle=["LF1"])
    q_q = projiziert(m2, [T], faelle=["Q"])
    check("die Last aus Q sperrt T nur in der Rechnung von Q", q_lf1[T][0] and not q_q[T][0])


def test_kanten_ecken_und_einspringend():
    """Konvexe Kante: beide Normalen zugleich; Ecke dreier freier Seiten:
    sigma = 0; einspringende Kante (L-Querschnitt): nicht angefasst."""
    m, ids = block()
    E, C = ids[(0, 3, 2)], ids[(0, 0, 2)]
    p = projiziert(m, [E, C])
    s = tensor(p[E][2])
    r = max(np.abs(s @ [0, 0, 1.0]).max(), np.abs(s @ [-1.0, 0, 0]).max())
    check("konvexe Kante (Deck- und Seitenfläche): σ·n₁ = σ·n₂ = 0 zugleich", p[E][0] and r < 1e-6,
          f"|σ n| {r:.1e} Pa")
    check("Ecke dreier freier Seiten: σ = 0", p[C][0] and np.abs(p[C][2]).max() < 1e-6,
          f"|σ| {np.abs(p[C][2]).max():.1e} Pa")
    # L-Querschnitt: Zellen i >= 3 und j >= 3 fehlen, die Kante bei (3, 3) springt ein
    m2, ids2 = block()
    m2.elements = [e for c, e in enumerate(m2.elements) if not ((c % 6) >= 3 and ((c // 6) % 6) >= 3)]
    kn = ids2[(3, 3, 1)]
    q = projiziert(m2, [kn, ids2[(0, 3, 1)]])
    check("einspringende Kante: nicht projiziert (die Spannung ist dort singulär)", not q[kn][0])
    check("… die konvexe Außenkante daneben schon", q[ids2[(0, 3, 1)]][0])


# --------------------------------------------------------------------------
# Wirkung
# --------------------------------------------------------------------------
def test_kirsch_loch():
    """Freier Lochrand unter Zug (Kirsch, exakt), σ_v bei 90 Grad in halber
    Dicke. Gemessen 23.09.2026: hex8 4 455 FHG -14,68 -> -1,10 N/mm2, tet10
    8 019 FHG -30,54 -> -19,41, tet4 16 575 FHG -24,07 -> -14,82."""
    for typ, nt, nr, grenze in (("hex8", 32, 8, 1.5), ("tet10", 16, 4, None), ("tet4", 64, 16, None)):
        werte = {}
        for weg in ("gemittelt", "frei"):
            m = kk.modell(typ, nt, nr)
            m.randspannung = weg
            res, _t = pk.loese(m)
            werte[weg] = kk.abweichung(m, res)[1]
        a, b = werte["gemittelt"], werte["frei"]
        txt = f"{a:+.2f} -> {b:+.2f} N/mm² ({pk.fhg(m)} FHG)"
        check(f"Kirsch-Loch {typ}: σ·n = 0 bringt die Spitze näher an die exakte Lösung",
              abs(b) < abs(a), txt)
        if grenze:
            check(f"… {typ} damit auf {grenze} N/mm²", abs(b) < grenze, txt)


def test_kragarm_und_schaden():
    """Biegung an der ebenen freien Seite (Kragarm, 355 N/mm2 nach Saint-
    Venant): tet10 und hex8 aendern sich kaum oder werden besser; der grobe
    tet4 (90 FHG) wird schlechter - gemessen 23.09.2026 -259,89 -> -277,95
    N/mm2; sein Wert taugt ohnehin nicht (260 N/mm2 daneben)."""
    kr = pk.Kragarm()
    for typ, netz, pruef in (("tet10", (8, 2, 4), "gleich"), ("hex8", (8, 2, 4), "besser"),
                             ("tet4", (4, 1, 2), "schaden")):
        w = {}
        for weg in ("gemittelt", "frei"):
            m, ids = kr.modell(typ, *netz)
            m.randspannung = weg
            res, _t = pk.loese(m)
            sk = res.solid_knoten
            n = ids[(netz[0] // 2, netz[1] // 2, netz[2])]
            j = int(np.flatnonzero(np.asarray(sk["knoten"]) == n)[0])
            w[weg] = sl.von_mises(np.asarray(sk["spannung"])[j]) / 1e6 - 355.0
        a, b = w["gemittelt"], w["frei"]
        txt = f"{a:+.2f} -> {b:+.2f} N/mm²"
        if pruef == "gleich":
            check(f"Kragarm {typ}: σ·n = 0 ändert die Randfaser um weniger als 0,1 N/mm²",
                  abs(b - a) < 0.1, txt)
        elif pruef == "besser":
            check(f"Kragarm {typ}: nicht schlechter", abs(b) <= abs(a) + 1e-9, txt)
        else:
            check(f"Kragarm {typ} grob (90 FHG): schlechter, aber unter 20 N/mm² (benannt)",
                  abs(b) > abs(a) and abs(b) - abs(a) < 20.0, txt)


def test_einstellung_ueberlagerung_und_nachweis():
    """Model.randspannung reist mit der Datei, "gemittelt" schaltet aus,
    Model.check lehnt Unbekanntes ab; die Kombination zweier Lastfaelle mit
    Lasten an verschiedenen Knoten wird ueberlagert (nicht verworfen), und
    der Nachweis nennt die Art der Randspannung."""
    m = Model("leer")
    check("Vorgabe: frei", m.randspannung == "frei")
    m.randspannung = "gemittelt"
    check("Umlauf to_dict/from_dict", Model.from_dict(m.to_dict()).randspannung == "gemittelt")
    d = m.to_dict()
    d.pop("randspannung", None)
    check("ältere Datei ohne das Feld: frei", Model.from_dict(d).randspannung == "frei")
    m.randspannung = "irgendwas"
    check("Model.check lehnt eine unbekannte Randspannung ab",
          any("Randspannung" in x for x in m.check()))

    mk = kk.modell("hex8", 16, 4)
    mk.randspannung = "gemittelt"
    r0, _t = pk.loese(mk)
    check("gemittelt: nichts projiziert, im Ergebnis genannt",
          not np.any(r0.solid_knoten.get("frei", [False])) and "Knotenmittel" in r0.info.get("randspannung", ""))
    # zwei Lastfaelle: die Kirsch-Last und eine Knotenlast am Loch
    mk = kk.modell("hex8", 16, 4)
    loch = kk.lochknoten(mk)
    X = np.asarray(mk.nodes)
    ziel = min(loch, key=lambda n: abs(X[n, 0]) + abs(X[n, 2] - kk.H / 2))
    mk.add_load_case("Q", "Q")
    mk.load_node(ziel, Fy=1e3, case="Q")
    mk.add_combination("K1", {"LF1": 1.0, "Q": 1.0}, "ULS")
    an = solver.solve_all(mk)
    r1, rq, rk = an.cases["LF1"], an.cases["Q"], an.combinations["K1"]
    sk1, skq, skk = r1.solid_knoten, rq.solid_knoten, rk.solid_knoten
    check("Kombination überlagert die Randspannung (nicht verworfen)",
          "spannung" in skk and np.allclose(skk["spannung"], np.asarray(sk1["spannung"]) + skq["spannung"],
                                            rtol=1e-12, atol=1e-3))
    j = int(np.flatnonzero(np.asarray(skk["knoten"]) == ziel)[0])
    check("… der in Q belastete Knoten heißt in der Summe nicht „σ·n = 0“",
          bool(sk1["frei"][j]) and not bool(skq["frei"][j]) and not bool(skk["frei"][j]))
    from statik3d.ec3 import volumen as vol
    werte = vol._elementspannungen(mk, r1, list(range(len(mk.elements))))
    check("der Nachweis nennt die Art der Randspannung",
          any("σ·n = 0" in w[2] for w in werte) and any(w[2].endswith("(geglättet)") for w in werte))


def main():
    print("=" * 100)
    print("STATIK3D - Randspannung an freien Oberflaechen (sigma n = 0)")
    print("=" * 100)
    for t in (test_freie_flaeche_und_ausnahmen, test_kanten_ecken_und_einspringend, test_kirsch_loch,
              test_kragarm_und_schaden, test_einstellung_ueberlagerung_und_nachweis):
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
