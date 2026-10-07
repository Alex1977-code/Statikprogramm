"""
Linienlasten und Linienlager auf die Knoten einer vernetzten Linie verteilen.

Eine Linie im Netz ist eine Kette von Elementkanten. Was eine Linienlast q(s)
an einem Knoten ausmacht, ist das Integral int N_i q ds mit den
Formfunktionen der Kante, an der er liegt - die konsistente Knotenlast, mit
der das Element rechnet:

* lineare Kante (zwei Knoten): N linear. Fuer eine linear veraenderliche
  Last ist das genau das Hebelgesetz (Resultierende und ihre Lage), wie es
  Model._linienlast_legen fuer solche Kanten unveraendert rechnet.
* quadratische Kante (Ecke, Kantenmitte, Ecke - tet10, hex20, pent15,
  shell6, shell8, ebene6, ebene8): N quadratisch. Bei gleichmaessiger Last
  L/6, 2L/3, L/6; Trapez und Teilstrecke ueber eine Gauss-Regel.

Ein federndes Linienlager verteilt seine Steifigkeit je Laenge mit denselben
Gewichten int N_i ds (Zeilensumme der konsistenten Bettungsmatrix): dann
haelt es eine gleichmaessige Verschiebung mit genau den Knotenkraeften, die
das Element bei gleichmaessiger Spannung an seiner Kante hat.

Bis zum 06.10.2026 wurde die Kette als Folge linearer Teilstuecke von
Knoten zu Knoten behandelt, auch ueber die Kantenmitte hinweg: L/4, L/2,
L/4 (Fehlerliste F11). Die Summe stimmte, die Verteilung nicht - gemessen
am Scheibenstreifen aus shell8 unter Zug in seiner Ebene: die gezogene
Kante verschob sich zwischen 186,0 und 203,0 um statt gleichmaessig um
190,5 um, mit federndem Linienlager wich die gelagerte Kante um 4,3 % ab
(tests/test_fehler_p7.py).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

#: 3-Punkt-Gauss auf [-1, 1]: exakt bis Grad 5. Der Integrand N_i(xi) q(s(xi))
#: s'(xi) einer quadratischen Kante mit linear veraenderlicher Last hat
#: hoechstens Grad 2 + 2 + 1 = 5.
_GAUSS = np.polynomial.legendre.leggauss(3)


@lru_cache(maxsize=1)
def kanten_mit_mitte() -> dict:
    """{Typ: ((Ecke a, Ecke b, Mitte), ...)} aller Elementtypen mit
    Kantenmitten, in Knotenindizes des Elements.

    Volumen aus ihren Seiten (solid.FLAECHEN: Ecken, dann die Mitten in
    Kantenreihenfolge), Schalen und Scheiben aus ihrem Umlauf (Ecken
    0..n-1, Mitte n+k auf der Kante k, k+1) - so steht es fuer jeden Typ im
    Elementverzeichnis, und ein neuer Typ kommt ohne eigene Liste hinzu."""
    from . import elemente as EL
    from .elements import solid as sl
    out: dict = {}
    for typ, art in EL.ELEMENTE.items():
        kanten: set = set()
        if typ in sl.FLAECHEN:
            for f, fe in zip(sl.FLAECHEN[typ], sl.FLAECHEN_ECKEN[typ]):
                ne = len(fe)
                for k in range(ne, len(f)):
                    a, b = fe[k - ne], fe[(k - ne + 1) % ne]
                    kanten.add((min(a, b), max(a, b), f[k]))
        elif art.familie in ("schale", "ebene") and art.ordnung >= 2 and art.knoten in (6, 8):
            ne = art.knoten // 2
            kanten = {(k, (k + 1) % ne, ne + k) for k in range(ne)}
        if kanten:
            out[typ] = tuple(sorted(kanten, key=lambda x: x[2]))
    return out


def kantenmitten_an(model, knoten, cache: dict = None) -> dict:
    """{Mitte: {frozenset((Ecke a, Ecke b)), ...}} der Elementkanten, deren
    Kantenmitte einer von ``knoten`` ist - leer ohne quadratische Elemente.

    ``cache`` (ein dict, anfangs leer) behaelt die Knotentabellen je Typ fuer
    weitere Aufrufe am selben Netz: ein Durchgang ueber alle Elemente je
    Lastverteilung statt einem je Linie (am Drehlager 646.000 Elemente)."""
    if cache is None:
        cache = {}
    tabellen = cache.get("kanten_mit_mitte")
    if tabellen is None:
        typen = kanten_mit_mitte()
        from .elemente import knotenzahl
        je_typ: dict = {}
        for e in model.elements:
            if e.typ in typen and len(e.nodes) == knotenzahl(e.typ):
                je_typ.setdefault(e.typ, []).append(e.nodes)
        tabellen = {t: np.asarray(v, dtype=np.int64) for t, v in je_typ.items()}
        cache["kanten_mit_mitte"] = tabellen
    out: dict = {}
    if not tabellen:
        return out
    gesucht = np.fromiter((int(n) for n in knoten), dtype=np.int64)
    if not gesucht.size:
        return out
    for typ, K in tabellen.items():
        for a, b, m in kanten_mit_mitte()[typ]:
            treffer = np.isin(K[:, m], gesucht)
            if not treffer.any():
                continue
            for ka, kb, km in zip(K[treffer, a].tolist(), K[treffer, b].tolist(),
                                  K[treffer, m].tolist()):
                out.setdefault(km, set()).add(frozenset((ka, kb)))
    return out


def linie_in_kanten(knoten, lage, mitten: dict) -> list:
    """Die Knotenkette einer Linie (Knoten und ihre Lagen s, nach s
    sortiert) als Folge von Elementkanten: das Indextupel (i, i+1, i+2) fuer
    eine quadratische Kante - der mittlere Knoten ist die Mitte einer
    Elementkante zwischen seinen beiden Nachbarn (``mitten`` aus
    :func:`kantenmitten_an`) -, sonst (i, i+1).

    Eine Kantenmitte, die laengs der Linie um ein Viertel der Kantenlaenge
    oder mehr neben der Mitte liegt, bleibt zwei lineare Stuecke: dort waere
    s(xi) auf der Kante nicht mehr monoton und die Lage nicht eindeutig. Der
    Vernetzer setzt die Mitte auf die Mitte der Kurve, das kommt nur bei
    fremden Netzen vor."""
    out: list = []
    i, n = 0, len(knoten)
    while i < n - 1:
        if i + 2 < n:
            a, m, b = int(knoten[i]), int(knoten[i + 1]), int(knoten[i + 2])
            s0, s1, s2 = float(lage[i]), float(lage[i + 1]), float(lage[i + 2])
            if s2 > s0 and frozenset((a, b)) in mitten.get(m, ()) \
                    and abs(s1 - 0.5 * (s0 + s2)) < 0.25 * (s2 - s0):
                out.append((i, i + 1, i + 2))
                i += 2
                continue
        out.append((i, i + 1))
        i += 1
    return out


def _formfunktionen(xi, k: int) -> np.ndarray:
    """N (k, len(xi)) der Kante mit k = 2 (linear) oder 3 Knoten (Ecke,
    Mitte, Ecke) an den Stellen xi in [-1, 1]."""
    xi = np.asarray(xi, float)
    if k == 2:
        return np.array([0.5 * (1.0 - xi), 0.5 * (1.0 + xi)])
    return np.array([0.5 * xi * (xi - 1.0), 1.0 - xi * xi, 0.5 * xi * (xi + 1.0)])


def kantenintegral(lage, lo: float, hi: float, q=None) -> np.ndarray:
    """int_lo^hi N_i q(s) ds je Knoten einer Kante mit den Lagen ``lage``
    (zwei Knoten linear; drei Knoten Ecke, Mitte, Ecke quadratisch).

    ``q``: Funktion der Lage s mit einem Wert (Zahl oder Vektor); None ist 1,
    das ergibt die Einflusslaengen. Rueckgabe (k,) bzw. (k, ...).

    Die Kante ist ueber die Lagen ihrer Knoten parametrisiert,
    s(xi) = sum N_i(xi) s_i, wie die Geometrie einer isoparametrischen
    Kante; bei mittiger Kantenmitte ist s linear in xi. Die Grenzen lo und hi
    werden auf xi zurueckgerechnet (s(xi) ist hoechstens quadratisch, die
    Wurzel in der ausloeschungsfreien Form), dann 3-Punkt-Gauss."""
    s = np.asarray(lage, float)
    k = len(s)
    if k == 2:
        sm, c1, c2 = 0.5 * (s[0] + s[1]), 0.5 * (s[1] - s[0]), 0.0
    else:
        sm, c1, c2 = s[1], 0.5 * (s[2] - s[0]), 0.5 * (s[0] + s[2]) - s[1]

    def xi_bei(x: float) -> float:
        # s(xi) = sm + c1 xi + c2 xi^2 = x  ->  xi = 2d / (c1 + sqrt(c1^2 + 4 c2 d))
        d = float(x) - sm
        w = max(c1 * c1 + 4.0 * c2 * d, 0.0)
        return float(np.clip(2.0 * d / (c1 + np.sqrt(w)), -1.0, 1.0))

    a, b = xi_bei(lo), xi_bei(hi)
    G, W = _GAUSS
    xi = 0.5 * (a + b) + 0.5 * (b - a) * G
    gewicht = 0.5 * (b - a) * W * (c1 + 2.0 * c2 * xi)     # ds = s'(xi) dxi
    N = _formfunktionen(xi, k)
    if q is None:
        return N @ gewicht
    werte = np.array([np.asarray(q(sm + c1 * x + c2 * x * x), float) for x in xi])
    return np.tensordot(N * gewicht, werte, axes=(1, 0))
