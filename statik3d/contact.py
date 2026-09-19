"""
Kontakt: einseitige Lager, Knoten-Knoten-Spaltelemente, Knoten-Flaeche-Kontakt.

Formulierung: Penalty-Verfahren mit Aktiv-Mengen-Iteration.
Fuer jede Kontaktbedingung gilt der Spalt
    g(u) = g0 + c^T u
(c = Koeffizientenvektor ueber die beteiligten FHG). Ist g < 0, wird die
Steifigkeit  k_n c c^T  und die Last  -k_n g0 c  hinzugefuegt; die Kontaktkraft
ist  F_n = -k_n g >= 0.  Reibung (Coulomb): tangentiale Penalty-Steifigkeit
k_t bei Haften; bei |F_t| > mu F_n Gleiten mit konstanter Reibkraft mu F_n
entgegen der Gleitrichtung (elastisch-plastische Naeherung ohne Lastgeschichte,
geeignet fuer monoton aufgebrachte Lasten).

Die Iteration endet, wenn sich keine Kontaktzustaende (offen/Haften/Gleiten)
mehr aendern. Oszillierende Bedingungen werden nach einigen Wechseln
festgehalten (Warnung im Ergebnis).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import sparse

from .model import Model, NDOF, DOF_NAMES

PENALTY_FACTOR = 1.0e4       # automatische Kontaktsteifigkeit = Faktor * Diagonalsteifigkeit
TANGENT_FACTOR = 1.0         # k_t = TANGENT_FACTOR * k_n
#: Anteil der Bezugskraft, ab dem ein Schubhalt am Ende als tragend gilt -
#: dieselbe Schwelle wie fuer Zug an gehaltenen Punkten (solver.ZUG_ANTEIL).
ZUG_ANTEIL = 0.05
SLIP_STIFFNESS = 1.0e-3      # Reststeifigkeit beim Gleiten (Regularisierung, Anteil von k_t)
SLIP_STIFFNESS_FINE = 1.0e-8  # Phase 2: haftende Nachbarn halten das Bauteil, Feder nur noch formal
SETTLE_ROUNDS = 8             # Phase 2: Nachlaufen der Normalkraefte in der Reibkraft mu*Fn
MAX_CYCLES = 40               # Phase 2: hoechstens so viele Zustandswechsel (je Runde einer)
#: Ein Slave-Knoten gilt als deckungsgleich mit einem Master-Knoten, wenn er
#: naeher als dieser Anteil der Modellgroesse liegt (Rundungsrauschen des
#: Vernetzers, nicht ein Spalt).
DECKUNGSGLEICH = 1e-6
#: Bis zu diesem Anteil des Suchradius gilt ein Spalt als Beruehrung.
AUFLIEGEND = 1e-3
#: Winkel [Grad] zwischen den Normalen zweier Facetten mit gemeinsamer Ecke,
#: bis zu dem sie zur selben glatten Flaeche gehoeren: nur solche Nachbarn
#: gehen in die Naeherung der wahren Flaeche ein (:class:`Flaechenquadriken`).
#: Darueber liegt eine Kante, und die wird nicht verrundet. Die Facetten
#: eines Zwoelfecks stehen 30 Grad auseinander, die eines 36-Ecks 10, eine
#: rechtwinklige Kante 90.
KNICK = 30.0
#: Wie weit ein Slave-Knoten neben seiner Gegenfacette liegen darf, als Anteil
#: seines Abstands laengs der Normalen: der Kegel, den ein abstehender Knoten
#: an einer glatten Kante zwischen zwei Facetten ueberstreicht. Steht er um d
#: vor der gemeinsamen Ecke zweier Facetten, die um den Winkel D abknicken,
#: liegt er neben beiden um d sin(D/2) bei einem Abstand d cos(D/2) - bis zum
#: Knickwinkel also hoechstens tan(KNICK/2) mal dem Abstand. Ein anliegender
#: Knoten (Abstand null) bekommt nichts nachgelassen.
KANTENKEGEL = float(np.tan(np.radians(0.5 * KNICK)))
#: Eine Stufe der Flaechenquadrik gilt nur, wenn ihr kleinster Singulaerwert
#: groesser ist als dieser Anteil des groessten (Spalten auf die Groesse des
#: Flecks bezogen). Gemessen an beiden Netzen des Drehlagers (15.09.2026, alle
#: 12 Fugen, 44 000 Facetten): bestimmte Quadriken liegen bei Konditionszahlen
#: bis 1e4 (mit x z, y z) bzw. 1e9, unbestimmte ab 1e12 - dazwischen nichts.
#: 1e-5 statt der Mitte der Luecke, weil gerundete Koordinaten die
#: unbestimmten nach unten ziehen: bei 0,1 µm Rauschen auf 50-mm-Flecken
#: kippte 1e-7 (313 µm), bei 1 µm 1e-6 (313 µm); 1e-5 hielt beide.
QUADRIK_GRENZE = 1e-5


# --------------------------------------------------------------------------
@dataclass
class Constraint:
    kind: str                      # support | gap | surface
    dofs: np.ndarray               # globale FHG
    cn: np.ndarray                 # Koeffizienten Normalrichtung (g = g0 + cn.u)
    ct: Optional[np.ndarray]       # (2, ndofs) Koeffizienten Tangentialrichtungen
    g0: float
    kn: float
    kt: float
    mu: float
    node: int
    normal: np.ndarray
    label: str = ""
    master: Optional[tuple] = None  # (Knotenliste, Gewichte)
    axes: Optional[np.ndarray] = None   # (2,3) globale Tangentialrichtungen; None = aus normal
    limit: float = 0.0             # Grenzkraft [N]/[Nm]; 0 = unbegrenzt (plastisches Fliessen)
    yielding: bool = False
    g_yield: float = 0.0
    dof: int = -1                  # Lager-FHG 0..5 bei kind 'dof'/'dof_rot'
    zug: bool = False              # Verbund: die Bedingung oeffnet nie (Zug wird uebertragen)
    haften: bool = False           # in der Fugenebene kein Gleiten
    active: bool = False
    slip: bool = False
    slip_dir: Optional[np.ndarray] = None   # Gleitrichtung (2,) im Tangentialsystem
    dir_updates: int = 0
    Fn: float = 0.0
    Ft: np.ndarray = field(default_factory=lambda: np.zeros(2))
    g: float = 0.0
    toggles: int = 0
    frozen: bool = False
    gehalten: bool = False         # von solver._freie_teile_halten geschlossen gehalten (17.09.2026)
    schub_halt: bool = False       # von solver._freie_teile_halten tangential gehalten
                                   # (19.09.2026): die Schubbindung des Stiftes wirkt,
                                   # die Normalbedingung bleibt offen


def verteilungstext(werte, aufliegend: float = 0.0) -> str:
    """Die Verteilung der Spaltmasse als Satz - nicht ihr Mittelwert.

    Ein Mittelwert ueber eine zweigipflige Verteilung beschreibt keinen
    Zustand. Liegen zwei Drittel einer Fuge auf null und der Rest bei 40 bis
    80 mm, steht dort „im Mittel 25 mm" - eine Zahl, die an keiner Stelle der
    Fuge vorkommt, und die verdeckt, dass ein Drittel gar nicht anliegt.
    Genannt werden darum der Anteil, der wirklich aufliegt, der Median, das
    90. Perzentil und der groesste Wert. ``aufliegend`` ist die Grenze, bis zu
    der ein Spalt als Beruehrung zaehlt.

    Die Werte tragen ihr **Vorzeichen**: negativ ist eine Durchdringung. Sie
    zaehlt nicht in die Spaltmasse, sondern wird mit Zahl und tiefster
    genannt. Bis zum 15.09.2026 kam hier der Betrag an; am Drehlager
    (gmsh-Netz) stand fuer die Achse „größter 0.62 mm", obwohl sie an 207
    Knoten bis 0,62 mm in der Buchse stak.
    """
    w = np.asarray(werte, float)
    if not w.size:
        return "kein Spalt gemessen"
    auf = int((np.abs(w) <= aufliegend).sum())
    tief = w[w < -aufliegend]
    spalt = np.maximum(w[w >= -aufliegend], 0.0)
    text = f"{100.0 * auf / w.size:.0f} % aufliegend"
    if spalt.size:
        text += (f", Median {float(np.median(spalt)) * 1e3:.2f} mm, 90 % unter "
                 f"{float(np.percentile(spalt, 90)) * 1e3:.2f} mm, größter "
                 f"{float(spalt.max()) * 1e3:.2f} mm")
    if tief.size:
        text += f"; {tief.size} durchdringend, tiefste {float(-tief.min()) * 1e3:.2f} mm"
    return text


def contact_dofs(model, K=None) -> set:
    """Freiheitsgrade, die eine Kontaktbedingung halten kann.

    Sie duerfen nicht vorab gesperrt werden, auch wenn die lineare
    Steifigkeitsmatrix dort null ist: ihre Steifigkeit kommt erst aus der
    Kontaktiteration - so bei einer Schraube mit Lochspiel, deren Querhalt
    allein aus Reibung und Lochleibung stammt.

    Massgebend ist, welche Zeilen die Bedingung wirklich besetzt: die
    Normalenrichtung immer, die beiden Tangentialrichtungen nur bei Reibung.
    """
    out: set = set()
    if not getattr(model, "has_contact", False):
        return out
    if K is None:
        K = sparse.identity(model.ndof, format="csr")
    try:
        st = ContactSystem(model, K)
    except Exception:            # noqa: BLE001 - die Sperrung darf nie am Kontakt scheitern
        return out
    for c in st.cons:
        dofs = np.asarray(c.dofs, dtype=int)
        out.update(int(d) for d in dofs[np.abs(c.cn) > 1e-12])
        if c.ct is not None and (c.mu > 0 or c.haften):
            for row in c.ct:
                out.update(int(d) for d in dofs[np.abs(row) > 1e-12])
    return out


def _group(c: "Constraint") -> str:
    return c.label.split(":")[0]


def _tangent_basis(n: np.ndarray):
    n = n / (np.linalg.norm(n) or 1.0)
    ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    t1 = np.cross(n, ref)
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    return t1, t2


def _axes_of(c: "Constraint"):
    """Globale Tangentialrichtungen (t1, t2) einer Bedingung."""
    if c.axes is not None:
        return c.axes[0], c.axes[1]
    return _tangent_basis(c.normal)


def _trans_dofs(node: int) -> list[int]:
    return [NDOF * node, NDOF * node + 1, NDOF * node + 2]


# --------------------------------------------------------------------------
# Geometrie: naechster Punkt auf Dreieck (Ericson, Real-Time Collision Detection)
# --------------------------------------------------------------------------
def closest_point_triangle(p, a, b, c):
    """Rueckgabe: naechster Punkt q auf dem Dreieck und baryzentrische Gewichte."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return a, np.array([1.0, 0, 0])
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return b, np.array([0, 1.0, 0])
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return a + v * ab, np.array([1 - v, v, 0])
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return c, np.array([0, 0, 1.0])
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return a + w * ac, np.array([1 - w, 0, w])
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + w * (c - b), np.array([0, 1 - w, w])
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    return a + ab * v + ac * w, np.array([1 - v - w, v, w])


def naechste_punkte_dreiecke(p, A, B, C):
    """Naechster Punkt von p auf jedem Dreieck (A[i], B[i], C[i]) - vektorisiert.

    Dasselbe Verfahren wie :func:`closest_point_triangle` (Ericson, Real-Time
    Collision Detection 5.1.5), nur fuer viele Dreiecke auf einmal: die sieben
    Bereiche (drei Ecken, drei Kanten, das Innere) werden ueber Masken
    zugewiesen. ``p`` ist ein Punkt (3,) fuer alle Dreiecke oder je Dreieck
    einer (n, 3). Rueckgabe (q (n,3), w (n,3)) mit den baryzentrischen Gewichten.
    """
    A = np.asarray(A, float).reshape(-1, 3)
    B = np.asarray(B, float).reshape(-1, 3)
    C = np.asarray(C, float).reshape(-1, 3)
    p = np.asarray(p, float).reshape(-1, 3)
    ab, ac = B - A, C - A
    ap = p - A
    d1 = (ab * ap).sum(1)
    d2 = (ac * ap).sum(1)
    bp = p - B
    d3 = (ab * bp).sum(1)
    d4 = (ac * bp).sum(1)
    cp = p - C
    d5 = (ab * cp).sum(1)
    d6 = (ac * cp).sum(1)
    nq = len(A)
    q = np.empty((nq, 3))
    w = np.empty((nq, 3))
    fertig = np.zeros(nq, bool)
    with np.errstate(divide="ignore", invalid="ignore"):
        m = (d1 <= 0) & (d2 <= 0)                       # Ecke A
        q[m], w[m] = A[m], (1.0, 0.0, 0.0)
        fertig |= m
        m = ~fertig & (d3 >= 0) & (d4 <= d3)            # Ecke B
        q[m], w[m] = B[m], (0.0, 1.0, 0.0)
        fertig |= m
        vc = d1 * d4 - d3 * d2
        m = ~fertig & (vc <= 0) & (d1 >= 0) & (d3 <= 0)  # Kante AB
        v = np.where(m, d1 / np.where(d1 - d3 != 0, d1 - d3, 1.0), 0.0)
        q[m] = A[m] + v[m, None] * ab[m]
        w[m] = np.column_stack([1 - v[m], v[m], np.zeros(m.sum())])
        fertig |= m
        m = ~fertig & (d6 >= 0) & (d5 <= d6)            # Ecke C
        q[m], w[m] = C[m], (0.0, 0.0, 1.0)
        fertig |= m
        vb = d5 * d2 - d1 * d6
        m = ~fertig & (vb <= 0) & (d2 >= 0) & (d6 <= 0)  # Kante AC
        v = np.where(m, d2 / np.where(d2 - d6 != 0, d2 - d6, 1.0), 0.0)
        q[m] = A[m] + v[m, None] * ac[m]
        w[m] = np.column_stack([1 - v[m], np.zeros(m.sum()), v[m]])
        fertig |= m
        va = d3 * d6 - d5 * d4
        m = ~fertig & (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)   # Kante BC
        nenner = (d4 - d3) + (d5 - d6)
        v = np.where(m, (d4 - d3) / np.where(nenner != 0, nenner, 1.0), 0.0)
        q[m] = B[m] + v[m, None] * (C[m] - B[m])
        w[m] = np.column_stack([np.zeros(m.sum()), 1 - v[m], v[m]])
        fertig |= m
        m = ~fertig                                     # Inneres
        nenner = va + vb + vc
        nenner = np.where(nenner != 0, nenner, 1.0)
        v = vb / nenner
        u = vc / nenner
        q[m] = A[m] + ab[m] * v[m, None] + ac[m] * u[m, None]
        w[m] = np.column_stack([1 - v[m] - u[m], v[m], u[m]])
    return q, w


def facetten_felder(facetten) -> tuple:
    """Facetten (Knotenlisten mit 3 oder 4 Ecken) als Felder (K (nf, 4),
    gueltig (nf, 4)): mit dem ersten Knoten aufgefuellt - die Newell-Summe
    ueber vier Ecken mit P3 = P0 ist die des Dreiecks -, ``gueltig`` sagt,
    welche Eintraege echte Ecken sind. Quadratische Facetten (6 oder 8
    Knoten, Ecken zuerst) gehen mit ihren Ecken ein."""
    K = np.zeros((len(facetten), 4), dtype=int)
    gueltig = np.zeros((len(facetten), 4), dtype=bool)
    for i, f in enumerate(facetten):
        fk = [int(x) for x in f]
        fk = fk[:3] if len(fk) in (3, 6) else fk[:4]
        K[i, :len(fk)] = fk
        K[i, len(fk):] = fk[0]
        gueltig[i, :len(fk)] = True
    return K, gueltig


def knotennormalen(nodes, K, gueltig, bezug=None) -> tuple:
    """Flaechengewichtete Knotennormalen einer Facettenmenge - als Summen.

    Die Normale der **ganzen** Facette (Newell), nicht die ihrer Dreiecke:
    ein Viereck zerfaellt in zwei, und die Ecke, die in beiden vorkommt,
    bekaeme sonst das doppelte Gewicht - am Zwoelfeck genug, um die
    Knotennormale um 5 Grad zu kippen. ``K``/``gueltig`` wie aus
    :func:`facetten_felder`; ``bezug`` (nf, 3) richtet jede Facettennormale
    (gedreht, wenn sie ihm entgegen zeigt; null laesst den Umlauf gelten).
    Rueckgabe (Summe Flaeche * Normale (nn, 3), Summe der Flaechen (nn,)).
    """
    nodes = np.asarray(nodes, float)
    nsum = np.zeros((len(nodes), 3))
    asum = np.zeros(len(nodes))
    K = np.asarray(K, int).reshape(-1, 4)
    if not len(K):
        return nsum, asum
    P = nodes[K]                                                   # (nf, 4, 3)
    vf = 0.5 * np.cross(P, np.roll(P, -1, axis=1)).sum(axis=1)     # Newell
    af = np.linalg.norm(vf, axis=1)
    if bezug is not None:
        dreh = np.einsum("ij,ij->i", vf, np.asarray(bezug, float).reshape(-1, 3)) < 0
        vf[dreh] = -vf[dreh]
    g = np.asarray(gueltig, bool).reshape(-1, 4)
    for j in range(4):
        w = g[:, j]
        np.add.at(nsum, K[w, j], vf[w])
        np.add.at(asum, K[w, j], af[w])
    return nsum, asum


def einheitsnormalen(nsum, asum) -> np.ndarray:
    """Einheits-Knotennormalen aus den Summen; null, wo sich die Facetten
    aufheben (eine duenne Platte, deren beide Seiten zum selben Paar
    gehoeren) - dort gibt es keine Flaechennormale."""
    ln = np.linalg.norm(nsum, axis=1)
    ok = ln > 0.2 * np.asarray(asum, float)
    out = np.zeros_like(nsum)
    out[ok] = nsum[ok] / ln[ok, None]
    return out


class Flaechenquadriken:
    """Die wahre Flaeche hinter den Facetten - je Facette eine Quadrik durch
    die Knoten.

    Eine gekruemmte Flaeche (Bohrung, Zylinder, Kugel) liegt im Netz als
    Sehnen vor; ihre **Knoten** aber liegen auf der wahren Flaeche. Ein
    Knoten der Gegenseite, der ebenfalls auf ihr liegt, steht gegen die Sehne
    um deren Pfeilhoehe ab: bei 50-mm-Facetten auf r = 300 mm ein Millimeter.
    Als Spalt gelesen, stuende eine passgenaue Achse in ihrer Bohrung nur mit
    den Knoten an, die auf einer Ecke liegen; hinter der Sehne (Richtung
    Master) laege sie sogar "in" der Bohrung.

    Durch die Ecken einer Facette und die ihrer **glatten Nachbarn** -
    Facetten mit einer gemeinsamen Ecke, deren Normale hoechstens
    :data:`KNICK` Grad von ihrer abweicht; eine Kante bleibt eine Kante, ein
    Absatz wird nicht verrundet - wird im Rahmen der Facette (x, y in der
    Facette laengs der Hauptrichtungen der Punkte, z laengs der Normalen) die
    Quadrik

        z + A x^2 + B y^2 + C x y + D x + E y + G z^2 + H x z + J y z + I = 0

    nach kleinsten Quadraten gelegt (linear in den Beiwerten). Sie enthaelt
    die Ebene (alle Beiwerte null), jeden Zylinder - auch den, dessen Achse
    schief zur Facette steht, wie an einem frei triangulierten Mantel (ohne
    H und J blieben dort 20 µm) -, die Kugel und das Ellipsoid **genau**,
    nicht nur bis zur zweiten Ordnung:
    ein Hoehenfeld z = c0 + c1 x + ... + c5 y^2 liess an einem 36-Eck mit
    r = 300 mm noch 19 µm (das Glied x^4 / 8 r^3 ueber die Nachbarn), die
    Quadrik nichts. Bestimmen die Punkte eine Stufe nicht, gilt die naechste:
    ohne H und J, dann die **Zylinderform** G = A + B (die Achse liegt in der
    Facettenebene: x^2 und z^2 bzw. y^2 und z^2 mit demselben Beiwert), die
    auch den Kreis durch zwei Knotenringe festlegt; danach fallen die Glieder
    in y weg. Mit weniger als vier Punkten bleibt es bei der Facette.

    **Bestimmt heisst gut konditioniert, nicht voller Rang.** Liegen die
    Stuetzpunkte auf vier gleichmaessig verteilten Winkellagen - so vernetzt
    gmsh eine Bohrung -, ist z^2 dort gerade in x und von 1 und x^2 nicht zu
    unterscheiden. Die Spaltenmatrix hat dann die Kondition 1e14, der
    Rangtest von lstsq (Maschinengenauigkeit) nennt sie trotzdem voll, und
    zwischen den Punkten liegt die Flaeche beliebig daneben: am Drehlager
    bis 0,68 mm hinter der Bohrung V16, 207 von 550 Knoten "durchdrangen"
    die Buchse, einer trug 1289 kN (15.09.2026). Eine Stufe gilt darum nur,
    wenn ihr kleinster Singulaerwert ueber :data:`QUADRIK_GRENZE` mal dem
    groessten liegt.

    Knotennormalen taugen dafuer nicht (Phong-Tessellation, 13.09.2026
    verworfen): die flaechengewichtete Mittelung steht an einer
    unregelmaessig vernetzten Bohrung um einige Grad neben der Radialen, und
    die Verschiebung waechst mit dem Abstand zur Ecke - am Drehlager blieben
    0,3 mm Durchdringung, als Uebermass gelesen 7 MN Kontaktkraft.
    """

    #: Spalten: x^2, y^2, x y, x, y, z^2, 1, x^2 + z^2, y^2 + z^2, x z, y z -
    #: und die Stufen, in denen Glieder wegfallen, wenn die Punkte sie nicht
    #: bestimmen: allgemeine Quadrik, ohne x z und y z, Zylinderform, ohne
    #: y^2, ohne x y und y
    STUFEN = ((0, 1, 2, 3, 4, 5, 9, 10, 6), (0, 1, 2, 3, 4, 5, 6), (7, 8, 2, 3, 4, 6),
              (7, 2, 3, 4, 6), (7, 3, 6))

    def __init__(self, nodes, K, gueltig, bezug=None, knick: float = KNICK):
        self.nodes = np.asarray(nodes, float)
        self.K = np.asarray(K, int).reshape(-1, 4)
        self.g = np.asarray(gueltig, bool).reshape(-1, 4)
        nf = len(self.K)
        P = self.nodes[self.K] if nf else np.zeros((0, 4, 3))
        vf = 0.5 * np.cross(P, np.roll(P, -1, axis=1)).sum(axis=1)      # Newell
        if bezug is not None and nf:
            dreh = np.einsum("ij,ij->i", vf, np.asarray(bezug, float).reshape(-1, 3)) < 0
            vf[dreh] = -vf[dreh]
        ln = np.linalg.norm(vf, axis=1)
        ln[ln <= 0] = 1.0
        self.N = vf / ln[:, None]
        self.cos_knick = float(np.cos(np.radians(knick)))
        self._an: dict = {}                  # Knoten -> Facetten
        for i in range(nf):
            for j in range(4):
                if self.g[i, j]:
                    self._an.setdefault(int(self.K[i, j]), []).append(i)
        self._fit: dict = {}

    def _quadrik(self, i: int):
        """(o, e1, e2, n, s, c) der Facette i - oder None."""
        if i in self._fit:
            return self._fit[i]
        n = self.N[i]
        ecken = [int(self.K[i, j]) for j in range(4) if self.g[i, j]]
        punkte = set(ecken)
        for e in ecken:
            for f in self._an.get(e, ()):
                if f != i and float(self.N[f] @ n) >= self.cos_knick:
                    punkte.update(int(self.K[f, j]) for j in range(4) if self.g[f, j])
        P = self.nodes[sorted(punkte)]
        o = self.nodes[ecken].mean(axis=0)
        D = P - o
        z = D @ n
        Dq = D - z[:, None] * n
        aus = None
        if len(P) >= 4:
            # Hauptrichtungen der Punkte in der Facette: x laengs der
            # groessten Ausdehnung, damit bei einer einzelnen Reihe zuerst
            # die Glieder in y wegfallen koennen
            _u, _s, vt = np.linalg.svd(Dq, full_matrices=False)
            e1 = vt[0] - (vt[0] @ n) * n
            l1 = float(np.linalg.norm(e1))
            if l1 > 0:
                e1 = e1 / l1
                e2 = np.cross(n, e1)
                s = float(np.linalg.norm(Dq, axis=1).max()) or 1.0
                x, y, zs = (Dq @ e1) / s, (Dq @ e2) / s, z / s
                A = np.column_stack([x * x, y * y, x * y, x, y, zs * zs, np.ones_like(x),
                                     x * x + zs * zs, y * y + zs * zs, x * zs, y * zs])
                for cols in self.STUFEN:
                    if len(P) < len(cols):
                        continue
                    c, _r, rang, sv = np.linalg.lstsq(A[:, cols], -zs, rcond=None)
                    if rang == len(cols) and sv[-1] > QUADRIK_GRENZE * sv[0]:
                        cc = np.zeros(11)
                        cc[list(cols)] = c
                        # Zylinderform zurueck auf A, B, G
                        cc[0] += cc[7]
                        cc[1] += cc[8]
                        cc[5] += cc[7] + cc[8]
                        aus = (o, e1, e2, n, s, cc[[0, 1, 2, 3, 4, 5, 6, 9, 10]])
                        break
        self._fit[i] = aus
        return aus

    def punkt(self, q, fi) -> tuple:
        """Zu Punkten ``q`` (k, 3) auf den Facetten ``fi`` (k,): (q* (k, 3),
        n* (k, 3)) - Punkt und Normale auf der wahren Flaeche. Ohne
        Naeherung bleiben es der Punkt und die Facettennormale."""
        q = np.asarray(q, float).reshape(-1, 3)
        fi = np.asarray(fi, int).reshape(-1)
        qs = q.copy()
        ns = self.N[fi].copy()
        for i in np.unique(fi):
            fit = self._quadrik(int(i))
            if fit is None:
                continue
            o, e1, e2, n, s, c = fit
            w = np.flatnonzero(fi == i)
            D = q[w] - o
            x, y = (D @ e1) / s, (D @ e2) / s
            # G z^2 + b z + R = 0 mit b = 1 + H x + J y: die Wurzel nahe der
            # Facette (z klein)
            R = c[0] * x * x + c[1] * y * y + c[2] * x * y + c[3] * x + c[4] * y + c[6]
            G = c[5]
            b = 1.0 + c[7] * x + c[8] * y
            wurzel = b * b - 4.0 * G * R
            gut = (wurzel >= 0) & (b > 0)
            if not gut.all():
                w, x, y, R, b, wurzel = w[gut], x[gut], y[gut], R[gut], b[gut], wurzel[gut]
                D = D[gut]
            z = -2.0 * R / (b + np.sqrt(wurzel))
            qs[w] = q[w] + (z * s - D @ n)[:, None] * n
            gx = 2.0 * c[0] * x + c[2] * y + c[3] + c[7] * z
            gy = 2.0 * c[1] * y + c[2] * x + c[4] + c[8] * z
            gz = b + 2.0 * G * z
            nn = gx[:, None] * e1[None, :] + gy[:, None] * e2[None, :] + gz[:, None] * n[None, :]
            ln = np.linalg.norm(nn, axis=1)
            ln[ln <= 0] = 1.0
            ns[w] = nn / ln[:, None]
        return qs, ns


def _deckender_knoten(p, s, mbaum, mknoten, knorm, tol):
    """Der Master-Knoten, auf dem ``p`` liegt - oder None.

    Rueckgabe ([Knoten], [1.0], Normale, 0.0): ein Master, volles Gewicht,
    Spalt null. Die Normale ist die flaechengewichtete Mittelung der
    Master-Facetten in diesem Knoten (``knorm``). Stossen dort Facetten
    zusammen, die einander entgegen zeigen - eine duenne Platte, deren beide
    Seiten zum selben Kontaktpaar gehoeren -, hebt sich die Summe auf; dann
    gibt es keine Flaechennormale und es bleibt bei der Suche.
    """
    dd, ii = mbaum.query(p, k=2)
    for d0, i0 in zip(np.atleast_1d(dd), np.atleast_1d(ii)):
        if not np.isfinite(d0) or d0 > tol:
            break
        t = int(mknoten[int(i0)])
        if t == int(s):
            continue
        v = knorm[t]
        if not np.any(v):
            return None
        return [t], [1.0], np.array(v, float), 0.0
    return None


def master_facets(model: Model, cp) -> list[tuple[int, ...]]:
    """Facetten (Knotenlisten) der Master-Oberflaeche eines Kontaktpaares."""
    from .assemble import SOLID_FACES, SHELL_TYPES, SOLID_TYPES
    facets: list[tuple[int, ...]] = [tuple(int(n) for n in f) for f in cp.master_faces]
    faces: dict[tuple, tuple] = {}
    for ei in cp.master_elements:
        e = model.elements[ei]
        if e.typ in SHELL_TYPES:
            facets.append(tuple(e.nodes))
        elif e.typ in SOLID_TYPES:
            for f in SOLID_FACES[e.typ]:
                nodes = tuple(e.nodes[i] for i in f)
                key = tuple(sorted(nodes))
                if key in faces:
                    del faces[key]          # innere Flaeche
                else:
                    faces[key] = nodes
    facets.extend(faces.values())
    return facets


def _solid_outward(model: Model, cp) -> dict[tuple, np.ndarray]:
    """Fuer Volumen-Facetten: Schwerpunkt des zugehoerigen Elements (Orientierung)."""
    from .assemble import SOLID_FACES, SOLID_TYPES
    out = {}
    for ei in cp.master_elements:
        e = model.elements[ei]
        if e.typ in SOLID_TYPES:
            cen = model.nodes[e.nodes].mean(axis=0)
            for f in SOLID_FACES[e.typ]:
                out[tuple(sorted(e.nodes[i] for i in f))] = cen
    return out


# --------------------------------------------------------------------------
#: Betrag der mittleren Facettennormalen, unter dem eine Fuge als
#: zylindrisch gilt. Bei einer ebenen Fuge zeigen alle Normalen in dieselbe
#: Richtung (Betrag 1), bei einer Bohrung heben sie sich weitgehend auf; 0,7
#: entspricht einem Bogen von rund 160 Grad. Eine Bohrung und ein Passstift
#: umschliessen mehr, ein leicht gewoelbtes Blech weniger.
ZYLINDRISCH = 0.7


class ContactSystem:
    def __init__(self, model: Model, K: sparse.csr_matrix, log: list = None,
                 uebermass: dict = None):
        self.model = model
        self.log = log if log is not None else []
        #: {Name der Fuge: Gesamtueberdeckung [m]} des gerechneten Lastfalls
        self.uebermass = {str(k): float(v) for k, v in (uebermass or {}).items() if v}
        self.phase = 1          # 1: Aktivmenge und Gleitrichtungen, 2: monotone Nachpruefung
        self.stabilising = False   # Hilfsschritt ohne Spaltkraft (siehe stabilise)
        self.cycles = 0
        self.settle = 0
        self.warm = False       # nach zustand_setzen: Phase 2 mit gesichertem Zustand
        self.dF_slip = 0.0      # groesste Aenderung von mu*Fn an gleitenden Knoten je Runde
        self.f_ref = 1.0
        self.diag = np.asarray(K.diagonal()).ravel()
        self.cons: list[Constraint] = []
        self.size = model.characteristic_size()
        self.tol = 1e-12 * self.size          # Spalt-Toleranz (Aktivierung)
        self.f_tol = 1.0                      # Kraft-Toleranz (Freigabe), wird vom Loeser gesetzt
        self._build()

    # ---- Aufbau ----------------------------------------------------------
    def _auto_k(self, nodes) -> float:
        d = []
        for n in nodes:
            d.extend(self.diag[_trans_dofs(n)])
        d = np.abs(np.asarray(d))
        ref = d.max() if d.size and d.max() > 0 else (np.abs(self.diag).max() or 1.0)
        return PENALTY_FACTOR * ref

    def _build(self):
        m = self.model
        for cs in m.contact_supports:
            n = np.asarray(cs.direction, float)
            n /= np.linalg.norm(n) or 1.0
            dofs = np.array(_trans_dofs(cs.node))
            kn = cs.stiffness if cs.stiffness > 0 else self._auto_k([cs.node])
            t1, t2 = _tangent_basis(n)
            self.cons.append(Constraint(
                "support", dofs, n.copy(), np.vstack([t1, t2]) if cs.mu > 0 else None,
                float(cs.gap), kn, TANGENT_FACTOR * kn, cs.mu, cs.node, n,
                f"Einseitiges Lager Knoten {cs.node}"))
        for ge in m.gap_elements:
            if ge.direction is not None:
                n = np.asarray(ge.direction, float)
            else:
                n = m.nodes[ge.node_b] - m.nodes[ge.node_a]
            ln = np.linalg.norm(n)
            if ln <= 0:
                self.log.append(f"Spaltelement {ge.node_a}-{ge.node_b}: Richtung unbestimmt "
                                "(Knoten fallen zusammen) - bitte 'direction' angeben")
                continue
            n = n / ln
            dofs = np.array(_trans_dofs(ge.node_a) + _trans_dofs(ge.node_b))
            cn = np.concatenate([-n, n])
            kn = ge.stiffness if ge.stiffness > 0 else self._auto_k([ge.node_a, ge.node_b])
            ct = None
            if ge.mu > 0:
                t1, t2 = _tangent_basis(n)
                ct = np.vstack([np.concatenate([-t1, t1]), np.concatenate([-t2, t2])])
            g0 = float(ge.gap)
            if ge.direction is None:
                g0 += 0.0   # Abstand ist bereits geometrisch (Knoten getrennt) -> gap zusaetzlich
            self.cons.append(Constraint("gap", dofs, cn, ct, g0, kn, TANGENT_FACTOR * kn,
                                        ge.mu, ge.node_b, n,
                                        f"Spaltelement {ge.node_a}-{ge.node_b}",
                                        master=([ge.node_a], [1.0])))
        for cp in m.contact_pairs:
            self._build_pair(cp)
        self._build_dof_supports()

    def _build_dof_supports(self):
        """Nichtlineare Lager-FHG (Ausfall bei Zug/Druck, Schlupf, Reibung, Grenzkraft)
        aus Knoten-, Linien- und Flaechenlagern in Kontaktbedingungen umsetzen."""
        from . import supports as sup
        _, nlin = sup.split(sup.expand(self.model, self.log))
        if not nlin:
            return
        by_node: dict[int, list] = {}
        for e in nlin:
            by_node.setdefault(e.node, []).append(e)
        for node, entries in sorted(by_node.items()):
            used = set()
            # 1) FHG mit Ausfall/Schlupf: eigene Bedingung, ggf. mit Reibung
            for e in entries:
                if e.mu > 0 and not e.failure and e.slip <= 0:
                    continue                     # reiner Reibungs-FHG: unten behandelt
                used.add(id(e))
                tang = [t for t in entries if t.mu > 0 and id(t) not in used
                        and (t.mu_ref is None or t.mu_ref == e.dof) and t.dof < 3]
                if e.dof >= 3:
                    tang = []                    # Rotations-FHG: keine Reibung
                for t in tang:
                    used.add(id(t))
                self._add_dof_constraint(e, tang)
            # 2) Reibungs-FHG ohne zugehoerigen Ausfall-FHG
            rest = [e for e in entries if id(e) not in used]
            for e in rest:
                self.log.append(f"{e.label} {DOF_NAMES[e.dof]}: Reibung ohne Bezugskraft "
                                f"(mu_ref) - der FHG wird starr gehalten")

    def _add_dof_constraint(self, e, tang):
        """Eine Bedingung fuer einen Lager-FHG. Vorzeichen: das Lager wirkt entlang
        +Achse; 'zug' (Ausfall bei Zug) laesst nur Druck zu (Knoten drueckt hinein),
        'druck' nur Zug. Ohne Ausfall, aber mit Schlupf entstehen zwei Bedingungen
        (beidseitiger Spalt)."""
        node, dof = e.node, e.dof
        rot = dof >= 3
        base = np.zeros(3)
        if not rot:
            base[dof] = 1.0
        kn = e.stiffness if e.stiffness > 0 else self._auto_k([node])
        dirs = []
        if e.failure == "zug":
            dirs = [+1.0]
        elif e.failure == "druck":
            dirs = [-1.0]
        else:
            dirs = [+1.0, -1.0] if e.slip > 0 else [+1.0]
        for sgn in dirs:
            dofs = [NDOF * node + dof]
            cn = np.array([sgn])
            ct = None
            axes = None
            if tang and not rot:
                rows = []
                ax = []
                for t in tang:
                    dofs.append(NDOF * node + t.dof)
                    v = np.zeros(3)
                    v[t.dof] = 1.0
                    ax.append(v)
                while len(rows) < 2:
                    row = np.zeros(len(dofs))
                    k = len(rows)
                    if k < len(tang):
                        row[1 + k] = 1.0
                    rows.append(row)
                while len(ax) < 2:
                    ax.append(np.zeros(3))
                ct = np.vstack(rows[:2])
                axes = np.vstack(ax[:2])
                cn = np.concatenate([[sgn], np.zeros(len(dofs) - 1)])
            mu = max((t.mu for t in tang), default=0.0)
            kind = "dof_rot" if rot else "dof"
            what = {"zug": "Ausfall bei Zug", "druck": "Ausfall bei Druck"}.get(
                e.failure, f"Schlupf {'+' if sgn > 0 else '-'}")
            label = f"{e.label} {DOF_NAMES[dof]} ({what})"
            self.cons.append(Constraint(
                kind, np.array(dofs), cn, ct, float(e.slip), kn, TANGENT_FACTOR * kn,
                mu, node, base * sgn, label, axes=axes, limit=float(e.limit), dof=dof))

    def _fugen_uebermass(self, cp, normalen) -> float:
        """Wirksames Uebermass der Fuge [m] - bei einer Bohrung die Haelfte.

        Angegeben wird immer die **Gesamtueberdeckung**. Bei einer ebenen Fuge
        muss die Fuge sie ganz schliessen. Bei einer zylindrischen ist sie das
        Uebermass am **Durchmesser** - so steht es in jeder Passungstabelle -,
        und radial schliesst die Fuge davon die Haelfte.

        Erkannt wird die Form am Betrag der mittleren Facettennormalen
        (:data:`ZYLINDRISCH`); das Protokoll sagt, was erkannt wurde und
        womit gerechnet wird - eine Verwechslung waere sonst ein Faktor zwei
        in der Pressspannung, den niemand bemerkt.
        """
        name = str(cp.name or "")
        u = self.uebermass.get(name)
        if u is None:
            # Eine Fuge kann in mehrere Kontaktpaare aufgeteilt sein (ein Paar
            # je Freigabetyp); die tragen den Namen der Fuge als Vorsatz.
            u = next((v for k, v in self.uebermass.items() if name.startswith(k)), 0.0)
        u = float(u or 0.0)
        if not u:
            return 0.0
        if not len(normalen):
            return 0.0
        mittel = float(np.linalg.norm(np.asarray(normalen, float).mean(axis=0)))
        zyl = mittel < ZYLINDRISCH
        self.log.append(
            f"Kontaktpaar '{name}': Übermaß {u * 1e6:.4g} µm Gesamtüberdeckung, Fuge "
            + (f"zylindrisch - radial wirken {0.5 * u * 1e6:.4g} µm" if zyl
               else "eben - sie wirkt in voller Höhe")
            + f" (mittlere Facettennormale {mittel:.3f})")
        return 0.5 * u if zyl else u

    def _bedingung(self, cp, s, tri, wj, n, d, normalen, marke, band: float = 0.0):
        """Eine Kontaktbedingung fuer Slave-Knoten ``s`` gegen ``tri``/``wj``.

        Gemeinsamer Teil beider Wege: der deckungsgleiche Knoten (ein Master,
        Gewicht 1) und die Projektion auf eine Facette (drei Master mit
        baryzentrischen Gewichten) unterscheiden sich nur darin, wer der
        Master ist und woher die Richtung kommt.

        ``band`` ist das Beruehrungsband: ein Anfangsspalt, der dem Betrag
        nach darunter liegt - Spalt wie Durchdringung -, wird zu null gesetzt
        (ANSYS: ICONT). Es ist dieselbe Grenze, bis zu der das Protokoll einen
        Knoten "aufliegend" nennt (ein Tausendstel des Suchradius): was das
        Protokoll als Beruehrung zaehlt, rechnet der Loeser auch so. Der Rest
        der Facettenbereinigung liegt weit darunter; ohne das Band waere er
        bei Durchdringung ein Uebermass von einigen Mikrometern und damit
        eine Pressspannung, die es nicht gibt.
        """
        g0 = 0.0 if (cp.anliegend or cp.zug) else float(d) - cp.gap
        if abs(g0) <= band:
            g0 = 0.0
        # Passung (17.09.2026): das Spiel kommt zum bereinigten Anfangsspalt
        # dazu - bei einer Bohrung das radiale Spiel; ein Verbund kennt keins
        spiel = float(getattr(cp, "spiel", 0.0) or 0.0)
        if spiel > 0 and not cp.zug:
            g0 += spiel
        dofs = np.array(_trans_dofs(s) + sum((_trans_dofs(t) for t in tri), []))
        cn = np.concatenate([n] + [-wi * n for wi in wj])
        kn = cp.stiffness if cp.stiffness > 0 else self._auto_k([s])
        # Randabminderung: ein Knoten am Rand der Kontaktseite haftet nicht
        # und reibt nicht - er gleitet, die Kantensingularitaet bleibt aus
        am_rand = bool(getattr(cp, "rand_knoten", None)) and int(s) in self._rand_von(cp)
        mu = 0.0 if am_rand else cp.mu
        haften = False if am_rand else bool(cp.haften)
        ct = None
        if mu > 0 or haften:
            t1, t2 = _tangent_basis(n)
            ct = np.vstack([np.concatenate([t1] + [-wi * t1 for wi in wj]),
                            np.concatenate([t2] + [-wi * t2 for wi in wj])])
        # Lochleibungsgrenze: Grenzpressung mal Einflussflaeche des Knotens;
        # darueber fliesst die Bedingung mit konstanter Kraft
        grenze = float(getattr(cp, "grenzpressung", 0.0) or 0.0)
        limit = 0.0
        if grenze > 0:
            a_s = float((getattr(cp, "knotenflaechen", None) or {}).get(int(s), 0.0) or 0.0)
            limit = grenze * a_s
        normalen.append(n)
        self.cons.append(Constraint("surface", dofs, cn, ct, float(g0), kn,
                                    TANGENT_FACTOR * kn, mu, s, n, marke,
                                    master=(list(tri), list(wj)), limit=limit,
                                    zug=bool(cp.zug), haften=haften))

    def _rand_von(self, cp) -> set:
        """Die Randknoten eines Kontaktpaars als Menge (einmal gebaut)."""
        cache = getattr(self, "_rand_cache", None)
        if cache is None:
            cache = self._rand_cache = {}
        key = id(cp)
        if key not in cache:
            cache[key] = {int(x) for x in (getattr(cp, "rand_knoten", None) or [])}
        return cache[key]

    def _build_pair(self, cp):
        """Ein Kontaktpaar in Bedingungen umsetzen: jeder Slave-Knoten gegen
        die naechste Master-Facette im Suchradius.

        Die Suche laeuft ueber einen KD-Baum der Facettenschwerpunkte und den
        vektorisierten naechsten Punkt (:func:`naechste_punkte_dreiecke`) - bei
        Tausenden Knoten gegen Tausende Facetten sonst Minuten. Der Suchradius
        ist der des Paares (aus der Kontaktbedingung: Pinball) oder ein Zehntel
        der Modellgroesse. ``anliegend`` und ``zug`` setzen den Anfangsspalt auf
        null: der Knoten gilt in seiner Lage als anliegend (ANSYS „auf
        Beruehrung setzen“), ein Verbund misst nur die Relativverschiebung.
        """
        from scipy.spatial import cKDTree
        m = self.model
        facets = master_facets(m, cp)
        if not facets:
            self.log.append(f"Kontaktpaar '{cp.name}': keine Master-Facetten")
            return
        from .assemble import SHELL_TYPES
        cen_of = _solid_outward(m, cp)
        # Schalen haben kein Innen: ihre Facetten werden zum Slave-Knoten hin
        # gerichtet. Alle anderen Facetten sind gerichtet - Volumenseiten
        # ueber den Elementschwerpunkt, explizite Facetten ueber den Umlauf
        # ihrer Knoten (fugen._nach_normale) - und bleiben es: ein Knoten
        # hinter der Facette ist eine Durchdringung, kein Spalt mit
        # umgekehrter Richtung.
        schalen = {tuple(sorted(int(x) for x in m.elements[ei].nodes))
                   for ei in cp.master_elements if m.elements[ei].typ in SHELL_TYPES}
        radius = cp.search_radius if cp.search_radius else 0.1 * self.size
        band = AUFLIEGEND * radius
        tris, ecken = [], []   # (nodes(3), n, facet_key, facet_index), (A, B, C)
        bezug = []             # je Facette: Richtung nach aussen (Volumen) oder null
        for fi, f in enumerate(facets):
            key = tuple(sorted(f))
            if len(f) == 3:
                parts = [(f[0], f[1], f[2])]
            else:
                parts = [(f[0], f[1], f[2]), (f[0], f[2], f[3])]
            for tri in parts:
                P = m.nodes[list(tri)]
                nv = np.cross(P[1] - P[0], P[2] - P[0])
                a2 = np.linalg.norm(nv)
                if a2 <= 0:
                    continue
                nv = nv / a2
                if key in cen_of:            # Volumen: Normale nach aussen
                    if nv @ (cen_of[key] - P.mean(axis=0)) > 0:
                        nv = -nv
                tris.append((tri, nv, key, fi))
                ecken.append(P)
            bezug.append(m.nodes[list(f)].mean(axis=0) - cen_of[key]
                         if key in cen_of else np.zeros(3))
        if not tris:
            self.log.append(f"Kontaktpaar '{cp.name}': alle Master-Facetten entartet")
            return
        # Knotennormalen der Master-Oberflaeche (flaechengewichtet ueber die
        # ganzen Facetten, :func:`knotennormalen`): Richtung fuer
        # deckungsgleiche Knoten und Kruemmung fuer den Facettenspalt.
        K4, gueltig = facetten_felder(facets)
        knorm = einheitsnormalen(*knotennormalen(m.nodes, K4, gueltig, bezug))
        quadriken = Flaechenquadriken(m.nodes, K4, gueltig, bezug)
        E = np.array(ecken)                       # (T, 3, 3)
        A, B, Cc = E[:, 0], E[:, 1], E[:, 2]
        S = E.mean(axis=1)
        R = np.sqrt(((E - S[:, None, :]) ** 2).sum(2).max(1))   # Umkreis (grob)
        N = np.array([t[1] for t in tris], dtype=float)          # Normale je Dreieck
        rmax = float(R.max())
        knoten = np.array([t[0] for t in tris], dtype=int)
        baum = cKDTree(S)
        # Deckungsgleiche Knoten brauchen weder Suche noch Projektion: liegt
        # ein Slave-Knoten auf einem Master-Knoten, ist der Spalt null und der
        # Master dieser eine Knoten - der ANSYS-Weg fuer ein passendes Netz.
        # Was dabei uebrig bleibt, ist die Richtung. Sie aus einer der
        # Facetten zu nehmen, die dort zusammenstossen, waere Zufall: an einem
        # gekruemmten Master (Bohrung, Zylinder) stehen sie im Beispielmodell
        # im Mittel 41 Grad auseinander, an einer Fugenkante bis 90 Grad. Die
        # Flaechennormale der Oberflaeche im Knoten ist der flaechengewichtete
        # Mittelwert - fuer den gekruemmten Master die bessere Naeherung als
        # jede einzelne Facette, und vor allem eindeutig.
        mknoten = np.unique(knoten)
        mbaum = cKDTree(m.nodes[mknoten])
        tol_deck = DECKUNGSGLEICH * self.size
        deckend = 0
        spalte: list = []
        n_paired = 0
        ohne: list = []
        neben: list = []
        erste = len(self.cons)          # ab hier gehoeren die Bedingungen zu cp
        normalen: list = []
        for s in cp.slave_nodes:
            p = m.nodes[s]
            fund = _deckender_knoten(p, s, mbaum, mknoten, knorm, tol_deck)
            if fund is not None:
                tri, wj, n, d = fund
                if cp.flip_normal:
                    n = -n
                deckend += 1
                spalte.append(0.0)
                self._bedingung(cp, s, tri, wj, n, d, normalen,
                                f"{cp.name}: Knoten {s} -> Knoten {tri[0]}", band)
                n_paired += 1
                continue
            idx = np.asarray(baum.query_ball_point(p, radius + rmax), dtype=int)
            if idx.size:
                idx = idx[~np.any(knoten[idx] == s, axis=1)]       # nicht gegen sich selbst
            if idx.size:
                idx = idx[np.linalg.norm(S[idx] - p, axis=1) <= radius + R[idx]]
            if not idx.size:
                ohne.append(int(s))
                continue
            q, w = naechste_punkte_dreiecke(p, A[idx], B[idx], Cc[idx])
            # Der Abstand zaehlt **laengs der Master-Normalen**; was quer dazu
            # liegt, ist Versatz in der Fugenebene und kein Abheben. Und der
            # Knoten muss **auf** der Facette liegen - senkrecht auf sie
            # fallen. Neben der Gegenflaeche steht ihm nichts gegenueber, und
            # Kontakt wirkt dort nie. Bis zum 15.09.2026 durfte er den Umkreis
            # der Facette weit daneben liegen (die Regel der Facettensuche,
            # fugen.gegenseite_finden): am Drehlager trugen Knoten der Achse
            # bis 25 mm hinter dem Ende der Buchse V29 1982 kN, und der Rand
            # eines Passstiftlochs 3 mm hinter dem Stiftende 708 kN auf einem
            # Knoten. Nachgelassen wird die Rundung und der Kegel einer
            # glatten Kante (:data:`KANTENKEGEL`).
            weg = q - p
            laengs = np.einsum("ij,ij->i", weg, N[idx])
            quer = np.linalg.norm(weg - laengs[:, None] * N[idx], axis=1)
            dist = np.abs(laengs)
            auf = quer <= DECKUNGSGLEICH * self.size + KANTENKEGEL * dist
            if not auf.any():
                neben.append(int(s))
                continue
            wahl = np.flatnonzero(auf)
            # Gewaehlt wird die raeumlich naechste Facette - wie bisher; nur
            # der Abstand, der daraus als Spalt wird, zaehlt laengs der Normalen.
            j = int(wahl[np.argmin(np.linalg.norm(weg[wahl], axis=1))])
            if dist[j] > radius:
                ohne.append(int(s))
                continue
            tri, nv, key, fi = tris[int(idx[j])]
            # Der Spalt zur **wahren** Flaeche, nicht zur Sehne der Facette
            # (:class:`Flaechenquadriken`): auf einer gekruemmten Gegenseite
            # stuende der Knoten sonst um die Pfeilhoehe ab - am Drehlager ein
            # Millimeter, und die Achse hinge nur an den Knoten, die auf einer
            # Ecke der Bohrung liegen. Die Richtung ist die Normale der
            # wahren Flaeche dort - auf einer ebenen Facette genau deren.
            qs, ns_ = quadriken.punkt(q[j], fi)
            qj, wj = qs[0], w[j]
            n = ns_[0]
            d = (p - qj) @ n
            if cp.flip_normal:
                n = -n
                d = -d
            elif key in schalen and abs(d) > 1e-9 * self.size and d < 0:
                # Schalen: Normale zum Slave-Knoten orientieren
                n = -n
                d = -d
            spalte.append(float(d))          # mit Vorzeichen: negativ durchdringt
            self._bedingung(cp, s, list(tri), list(wj), n, d, normalen,
                            f"{cp.name}: Knoten {s} -> Facette {tri}", band)
            n_paired += 1
        # Das Uebermass erst jetzt: welche Form die Fuge hat, sagen die
        # Facetten, die wirklich gepaart wurden - nicht alle Aussenflaechen des
        # Masters. Ein Hexaeder hat sechs davon, und alle sechs zusammen saehen
        # aus wie eine Bohrung.
        ueber = self._fugen_uebermass(cp, normalen)
        if ueber and not cp.zug:
            # Ein Uebermass ist ein **negativer** Anfangsspalt: die Fuge steht
            # schon vor der Last unter Druck. Ein Verbund kennt beides nicht.
            for c in self.cons[erste:]:
                c.g0 -= ueber
        self.log.append(
            f"Kontaktpaar '{cp.name}': {n_paired} von {len(cp.slave_nodes)} "
            f"Slave-Knoten zugeordnet, davon {deckend} deckungsgleich"
            + (f"; Spalt {verteilungstext(spalte, band)}, bis {band * 1e3:.2g} mm als "
               "Berührung gesetzt" if spalte else "")
            + (f" - {len(ohne)} ohne Master-Facette im Suchradius "
               f"{radius:.3g} m (z. B. Knoten {', '.join(str(x) for x in ohne[:5])})"
               if ohne else "")
            + (f" - {len(neben)} liegen neben der Gegenfläche: dort steht ihnen nichts "
               f"gegenüber, sie tragen nicht (z. B. Knoten {', '.join(str(x) for x in neben[:5])})"
               if neben else ""))

    # ---- Zustand ---------------------------------------------------------
    def initialize(self):
        """Anfangszustand: beruehrende oder durchdringende Bedingungen aktiv."""
        for c in self.cons:
            c.active = True if c.zug else c.g0 <= self.tol
            c.slip = False
            c.slip_dir = None
            c.dir_updates = 0
            c.toggles = 0
            c.frozen = False

    @property
    def n_active(self) -> int:
        return sum(1 for c in self.cons if c.active)

    # ---- Zustand sichern, wiederverwenden, kennzeichnen ----------------------
    def _kennung(self) -> tuple:
        """Woran eine Sicherung erkennt, dass sie zu diesen Bedingungen gehoert:
        Zahl und eine Stichprobe der Bezeichnungen."""
        schritt = max(1, len(self.cons) // 16)
        return (len(self.cons), tuple(c.label for c in self.cons[::schritt]))

    def zustand(self) -> dict:
        """Der Kontaktzustand als Sicherung fuer den Warmstart des naechsten
        Lastfalls (solve_with_contact(start=...)): Aktivmenge, Gleiten mit
        Richtung, Fliessen und die Normalkraefte, aus denen die Reibkraft
        mu*Fn aufgebaut wird."""
        return {"kennung": self._kennung(), "phase": self.phase,
                "aktiv": np.array([c.active for c in self.cons], bool),
                "gleitet": np.array([c.slip for c in self.cons], bool),
                "fliesst": np.array([c.yielding for c in self.cons], bool),
                "g_yield": np.array([c.g_yield for c in self.cons], float),
                "Fn": np.array([c.Fn for c in self.cons], float),
                "eingefroren": np.array([c.frozen for c in self.cons], bool),
                "wechsel": np.array([c.toggles for c in self.cons], int),
                "richtung": [None if c.slip_dir is None else np.array(c.slip_dir, float)
                             for c in self.cons]}

    def zustand_setzen(self, z) -> bool:
        """Eine Sicherung uebernehmen - der Startpunkt der Iteration statt der
        Geometrie. Rueckgabe False, wenn sie nicht zu diesen Bedingungen
        passt (anderes Modell, andere Situation): dann bleibt der Anfangszustand.
        Verbund bleibt zu, Zaehler und Marken beginnen von vorn. Es geht in
        der Phase der Sicherung weiter (2 nach einer konvergierten Rechnung):
        der erste Schritt loest mit derselben Matrix wie der letzte des
        vorigen Lastfalls, Gleitrichtungen bleiben fest, neue Verstoesse
        kommen monoton hinzu; ob die Richtungen noch stimmen, prueft
        warmstart_verstoesse nach der Konvergenz. Gemessen (12.09.2026): so
        braucht der Block mit Reibung fuer den Folgezustand 5 statt 21
        Schritte; Phase 1 mit grober Reststeifigkeit 20 (kein Gewinn), Phase 1
        mit feiner Reststeifigkeit und Phase 2 mit nachgefuehrten Richtungen
        konvergierten nicht (120 bzw. 40 Schritte). Am Drehlager passten die
        Richtungen des Zustands LF401 nicht zu LF404: der Warmstart wurde
        verworfen und kalt gerechnet - fuer die Ermuedungszustaende ist das
        Einfrieren des Kontaktzustands der Weg (solver, einfrieren)."""
        if not z or z.get("kennung") != self._kennung():
            return False
        for i, c in enumerate(self.cons):
            if c.zug:
                continue
            c.active = bool(z["aktiv"][i])
            c.slip = bool(z["gleitet"][i])
            c.yielding = bool(z["fliesst"][i])
            c.g_yield = float(z["g_yield"][i])
            c.Fn = float(z["Fn"][i])
            r = z["richtung"][i]
            c.slip_dir = None if r is None else np.array(r, float)
            c.dir_updates = 0
            # eingefrorene Bedingungen (oszillierten) bleiben eingefroren -
            # sonst wechseln sie gleich wieder und die Iteration beginnt von vorn
            c.toggles = int(z["wechsel"][i]) if "wechsel" in z else 0
            c.frozen = bool(z["eingefroren"][i]) if "eingefroren" in z else False
        self.phase = int(z.get("phase", 2) or 2)
        self.warm = True
        self.cycles = 0
        self.settle = 0
        return True

    def warmstart_verstoesse(self, u: np.ndarray, zuruecksetzen: bool = False) -> int:
        """Gleitende Knoten, die sich gegen ihre festgehaltene Gleitrichtung
        bewegen - der Warmstart hat dann einen anderen Lastfall vor sich als
        der Zustand annahm (Phase 1 setzt solche Knoten zurueck auf Haften,
        Phase 2 nicht). Mit ``zuruecksetzen`` werden sie auf Haften gesetzt;
        die Iteration findet ihre Richtung dann neu."""
        n = 0
        for c in self.cons:
            if c.active and c.slip and c.ct is not None and c.slip_dir is not None:
                ue = u[c.dofs]
                dt = np.array([c.ct[0] @ ue, c.ct[1] @ ue])
                nrm = float(np.linalg.norm(dt))
                if nrm > 0 and float(dt @ c.slip_dir) < -1e-9 * nrm:
                    n += 1
                    if zuruecksetzen:
                        c.slip = False
                        c.slip_dir = None
                        c.dir_updates = 0
                        c.Ft = np.zeros(2)
        return n

    @property
    def n_slip(self) -> int:
        return sum(1 for c in self.cons if c.active and c.slip)

    def signatur(self) -> tuple:
        """Woran die Kontaktsteifigkeit Kc haengt: Phase, Aktivmenge, Gleiten,
        Fliessen und die ganz rutschenden Gruppen. Normalkraefte und
        Gleitrichtungen stehen nur im Lastvektor Fc. Gleiche Signatur heisst
        gleiche Matrix - die Faktorisierung kann bleiben (StaticSystem.solve)."""
        a = np.array([c.active for c in self.cons], bool)
        s = np.array([c.slip for c in self.cons], bool)
        y = np.array([c.yielding for c in self.cons], bool)
        return (self.phase, hash(a.tobytes()), hash(s.tobytes()), hash(y.tobytes()),
                tuple(sorted(self._full_slip_groups().items())))

    def stabilise(self) -> bool:
        """Hilfsschritt, wenn im ersten Schritt kein Halt besteht.

        Alle Bedingungen werden geschlossen, aber **ohne** die Kraft aus dem
        Spaltmass: sie wirken als reine Federn an ihrer jetzigen Lage. Der
        Loesungsschritt danach zeigt nur, wohin sich das Bauteil bewegen will;
        aus dieser Richtung wird in select_by_direction die richtige Bedingung
        gewaehlt. Das ist der Startschritt fuer eine Schraube, die erst nach
        dem Durchfahren des Lochspiels traegt.
        """
        self.stabilising = True
        changed = False
        for c in self.cons:
            if not c.active:
                c.active = True
                c.stabilised = True
                changed = True
        return changed

    def select_by_direction(self, u: np.ndarray) -> None:
        """Nach dem Hilfsschritt: nur die Bedingungen halten, auf die sich das
        Bauteil zubewegt (cn * u < 0). Die uebrigen werden wieder geoeffnet."""
        self.stabilising = False
        for c in self.cons:
            if not getattr(c, "stabilised", False):
                continue
            c.stabilised = False
            c.active = float(c.cn @ u[c.dofs]) < -1e-14

    def schub_halt_loesen(self) -> int:
        """Den Schubhalt aller Gruppen loesen, die wieder eine geschlossene
        Bedingung haben. Rueckgabe: Zahl der geloesten Bedingungen.

        Der Halt ist fuer den Schritt gedacht, nicht fuer das Ergebnis: sobald
        der Stift wieder irgendwo anliegt, traegt die gewoehnliche Haftbindung,
        und der Halt darf keinen Schub mehr erfinden."""
        traegt = {_group(c) for c in self.cons if c.active}
        geloest = 0
        for c in self.cons:
            if c.schub_halt and _group(c) in traegt:
                c.schub_halt = False
                geloest += 1
        return geloest

    def schub_unter_last(self, u: np.ndarray) -> list:
        """[(Fuge, Zahl der Bedingungen, Schubkraft [N])] je Gruppe, die am
        Ende noch am Schubhalt haengt und dort merklich Kraft traegt.

        Der Schubhalt haelt einen Stift, dessen Normalbedingungen in einem
        Zwischenschritt alle offen stehen. Steht er am Schluss immer noch offen
        und traegt Schub, dann stuetzt sich das Ergebnis auf eine Bindung, die
        es nicht gibt - und das gehoert gesagt, nicht verschwiegen. Die
        Schwelle ist dieselbe wie fuer Zug an gehaltenen Punkten."""
        je_gruppe: dict = {}
        for c in self.cons:
            if not (c.schub_halt and c.ct is not None):
                continue
            ue = u[c.dofs]
            ft = c.kt * np.array([float(c.ct[0] @ ue), float(c.ct[1] @ ue)])
            n, kraft = je_gruppe.get(_group(c), (0, 0.0))
            je_gruppe[_group(c)] = (n + 1, kraft + float(np.linalg.norm(ft)))
        grenze = ZUG_ANTEIL * float(getattr(self, "f_ref", 1.0))
        return [(g, n, k) for g, (n, k) in sorted(je_gruppe.items()) if k > grenze]

    def matrices(self, ndof: int):
        """Kontaktsteifigkeit Kc (csr) und Kontaktlastvektor Fc."""
        rows, cols, vals = [], [], []
        Fc = np.zeros(ndof)
        full_slip = self._full_slip_groups()
        for c in self.cons:
            if not c.active:
                if not (c.schub_halt and c.ct is not None):
                    continue
                # Schubhalt: der Stift steckt in der Bohrung und traegt dort
                # Schub, auch wenn in diesem Schritt alle seine
                # Normalbedingungen offen stehen. Nur die Tangentialsteifigkeit,
                # keine Normalfeder und kein Lastanteil aus dem Spaltmass - die
                # Komplementaritaet in Normalrichtung bleibt unberuehrt. Am
                # Drehlager haelt der Schub aller Bedingungen die sechs
                # Starrkoerperbewegungen mit 0,54 bis 0,71, drei Bedingungen
                # dagegen mit 2e-18, also gar nicht (19.09.2026).
                kmat = c.kt * (np.outer(c.ct[0], c.ct[0]) + np.outer(c.ct[1], c.ct[1]))
                r, cc = np.meshgrid(c.dofs, c.dofs, indexing="ij")
                rows.append(r.ravel())
                cols.append(cc.ravel())
                vals.append(kmat.ravel())
                continue
            r, cc = np.meshgrid(c.dofs, c.dofs, indexing="ij")
            if c.yielding:
                # Grenzkraft erreicht: konstante Kraft, nur Reststeifigkeit (plastisch)
                kmat = SLIP_STIFFNESS_FINE * c.kn * np.outer(c.cn, c.cn)
                Fc[c.dofs] += c.limit * c.cn
            else:
                kmat = c.kn * np.outer(c.cn, c.cn)
                if not (self.stabilising and getattr(c, "stabilised", False)):
                    Fc[c.dofs] += -c.kn * c.g0 * c.cn
            if c.ct is not None and (c.mu > 0 or c.haften):
                if not c.slip:
                    kmat = kmat + c.kt * (np.outer(c.ct[0], c.ct[0]) + np.outer(c.ct[1], c.ct[1]))
                else:
                    # Gleiten: konstante Reibkraft mu*Fn entgegen der Gleitrichtung
                    # + Reststeifigkeit (haelt das System regulaer); in Phase 2 so klein,
                    # dass ihr Kraftanteil vernachlaessigbar ist
                    fr = c.mu * max(c.Fn, 0.0)
                    k_res = self._k_res(c, full_slip)
                    f_t = fr * c.slip_dir
                    Fc[c.dofs] += -(f_t[0] * c.ct[0] + f_t[1] * c.ct[1])
                    kmat = kmat + k_res * (np.outer(c.ct[0], c.ct[0]) + np.outer(c.ct[1], c.ct[1]))
            rows.append(r.ravel())
            cols.append(cc.ravel())
            vals.append(kmat.ravel())
        if rows:
            Kc = sparse.coo_matrix((np.concatenate(vals),
                                    (np.concatenate(rows), np.concatenate(cols))),
                                   shape=(ndof, ndof)).tocsr()
        else:
            Kc = sparse.csr_matrix((ndof, ndof))
        return Kc, Fc

    def _k_res(self, c: Constraint, full_slip: dict) -> float:
        """Reststeifigkeit eines gleitenden Knotens: grob in Phase 1 und fuer vollstaendig
        rutschende Gruppen (nur sie haelt das Bauteil), sonst in Phase 2 vernachlaessigbar
        klein, damit die Reibkraft exakt mu*Fn betraegt."""
        if self.phase == 2 and not full_slip.get(_group(c), False):
            return SLIP_STIFFNESS_FINE * c.kt
        return SLIP_STIFFNESS * c.kt

    def _full_slip_groups(self) -> dict:
        """Kontaktgruppe -> True, wenn alle aktiven Reibknoten gleiten (Bauteil rutscht;
        dann haelt nur die Reststeifigkeit, keine Fixpunkt-Korrektur)."""
        groups: dict[str, bool] = {}
        for c in self.cons:
            if c.mu > 0 and c.active and c.ct is not None:
                g = _group(c)
                groups[g] = groups.get(g, True) and c.slip
        return groups

    def set_force_scale(self, f_ref: float):
        """Bezugskraft fuer die Freigabe aktiver Bedingungen (Zugkraft > 1e-6 f_ref)."""
        self.f_tol = 1e-6 * max(abs(f_ref), 1e-30)
        self.f_ref = max(abs(f_ref), 1e-30)

    def update(self, u: np.ndarray) -> bool:
        """Zustaende aus der Loesung u aktualisieren. Rueckgabe: True, solange weiter
        iteriert werden muss.

        Phase 1 (grobe Reststeifigkeit): Aktivmenge, Haften/Gleiten und Gleitrichtungen
        wie ueblich (unterrelaxiert) bis nichts mehr wechselt.
        Phase 2 (Reststeifigkeit vernachlaessigbar): Gleitrichtungen bleiben fest; je
        Runde geht hoechstens der am staerksten ueber der Reibgrenze liegende haftende
        Knoten ins Gleiten ueber (monoton, kann nicht flattern). Ergebnis: Gleichgewicht
        exakt, |Ft| <= mu*Fn an jedem Knoten, Ft = mu*Fn an gleitenden Knoten."""
        changed = self._update_states(u)
        if self.phase == 1:
            if changed:
                return True
            full = self._full_slip_groups()
            if any(c.active and c.slip and not full.get(_group(c), False) for c in self.cons):
                self.phase = 2
                self.cycles = 0
                return True
            return False
        if not changed:
            # Setzrunden: die konstante Reibkraft mu*Fn wurde mit der Normalkraft der
            # vorigen Runde aufgestellt - solange sie sich merklich aendert, nachrechnen
            if self.dF_slip > 1e-4 * self.f_ref and self.settle < SETTLE_ROUNDS:
                self.settle += 1
                return True
            return False
        self.cycles += 1
        if self.cycles >= MAX_CYCLES:
            self.log.append("Kontakt: Nachpruefung der Reibung nach "
                            f"{MAX_CYCLES} Zustandswechseln abgebrochen")
            return False
        return True

    def _update_states(self, u: np.ndarray) -> bool:
        changed = False
        worst = None            # Phase 2: (Verhaeltnis, Bedingung, dt) des staerksten Verstosses
        self.dF_slip = 0.0
        for c in self.cons:
            ue = u[c.dofs]
            g = c.g0 + c.cn @ ue
            c.g = g
            if c.active:
                Fn = c.limit if c.yielding else -c.kn * g
                if c.slip:
                    self.dF_slip = max(self.dF_slip, c.mu * abs(max(Fn, 0.0) - c.Fn))
                new_active = Fn > -self.f_tol   # Druckkraft (bzw. winziger Zug) -> bleibt
                # Im Verbund bleibt die Bedingung auch unter Zug zu - und die
                # Zugkraft gehoert ins Ergebnis, nicht auf null gekappt
                c.Fn = Fn if c.zug else max(Fn, 0.0)
                if c.limit > 0:
                    if not c.yielding and new_active and -c.kn * g > c.limit:
                        c.yielding = True       # Grenzkraft erreicht -> plastisch
                        c.g_yield = g
                        changed = True
                    elif c.yielding and g > c.g_yield + self.tol:
                        c.yielding = False      # Entlastung -> wieder elastisch
                        changed = True
            else:
                c.Fn = 0.0
                new_active = g < -self.tol
            if c.frozen or c.zug:
                new_active = c.active
            if new_active != c.active:
                c.toggles += 1
                if c.toggles > 8:
                    c.frozen = True
                    new_active = True
                    self.log.append(f"{c.label}: Zustand oszilliert, wird als aktiv gehalten")
                c.active = new_active
                changed = True
                if not c.active:
                    c.slip = False
                    c.slip_dir = None
                    c.yielding = False
                    c.Ft[:] = 0
            if c.active and c.ct is not None and c.haften:
                # Haften: die Fugenebene ist eine Feder, nie ein Gleiten
                dt = np.array([c.ct[0] @ ue, c.ct[1] @ ue])
                c.Ft = c.kt * dt
            elif c.active and c.ct is not None and c.mu > 0:
                dt = np.array([c.ct[0] @ ue, c.ct[1] @ ue])
                Ft_el = c.kt * dt
                limit = c.mu * max(c.Fn, 0.0)
                nrm = np.linalg.norm(dt)
                if not c.slip:
                    c.Ft = Ft_el
                    if np.linalg.norm(Ft_el) > limit * (1 + 1e-6) and limit >= 0:
                        if self.phase == 1:
                            c.slip = True
                            c.slip_dir = dt / nrm if nrm > 0 else np.array([1.0, 0.0])
                            c.dir_updates = 0
                            c.Ft = limit * c.slip_dir
                            changed = True
                        else:
                            ratio = np.linalg.norm(Ft_el) / limit if limit > 0 else np.inf
                            if worst is None or ratio > worst[0]:
                                worst = (ratio, c, dt)
                elif self.phase == 1:
                    if nrm > 0 and (dt @ c.slip_dir) < 0:
                        # Bewegung entgegen Gleitrichtung -> wieder Haften
                        c.slip = False
                        c.slip_dir = None
                        c.Ft = np.zeros(2)
                        changed = True
                    else:
                        if nrm > 0 and c.dir_updates < 12:
                            # Gleitrichtung unterrelaxiert nachfuehren (Fixpunkt-Iteration);
                            # nach 12 Anpassungen wird die Richtung festgehalten
                            nd = dt / nrm
                            blend = 0.5 * c.slip_dir + 0.5 * nd
                            bn = np.linalg.norm(blend)
                            blend = blend / bn if bn > 0 else nd
                            if np.linalg.norm(blend - c.slip_dir) > 0.05:   # ~3 Grad
                                c.slip_dir = blend
                                c.dir_updates += 1
                                changed = True
                        c.Ft = limit * c.slip_dir
                else:
                    c.Ft = limit * c.slip_dir      # Phase 2: Gleiten bleibt, Richtung fest
            elif not c.active:
                c.Ft = np.zeros(2)
        # Phase 2: je Runde nur der staerkste Verstoss Haften -> Gleiten (monoton)
        if worst is not None:
            ratio, c, dt = worst
            nrm = np.linalg.norm(dt)
            c.slip = True
            c.slip_dir = dt / nrm if nrm > 0 else np.array([1.0, 0.0])
            c.dir_updates = 0
            c.Ft = c.mu * c.Fn * c.slip_dir
            changed = True
        return changed

    # ---- Ergebnisse --------------------------------------------------------
    def warnings(self) -> list[str]:
        """Hinweise: vollstaendig gleitende Kontaktpaare (Gleichgewicht nur durch
        Reststeifigkeit) und eingefrorene Bedingungen."""
        out = []
        groups: dict[str, list[Constraint]] = {}
        for c in self.cons:
            if c.mu > 0:
                groups.setdefault(c.label.split(":")[0], []).append(c)
        for name, cs in groups.items():
            act = [c for c in cs if c.active]
            if act and all(c.slip for c in act):
                out.append(f"{name}: alle aktiven Kontaktknoten gleiten - Reibung reicht "
                           "nicht fuer das Gleichgewicht (Bauteil rutscht; nahe der "
                           "Reibkapazitaet mu*N urteilt das Verfahren konservativ)")
        return out

    def results(self) -> list[dict]:
        out = []
        for c in self.cons:
            if not c.active:
                status = "offen"
            elif c.yielding:
                status = "Fliessen"
            elif c.zug and c.haften:
                status = "Verbund"
            elif c.zug:
                status = "ohne Trennung"
            elif c.mu > 0 and c.slip:
                status = "Gleiten"
            elif c.mu > 0 or c.haften:
                status = "Haften"
            else:
                status = "Kontakt"
            # Die Kraft auf den Kontaktknoten, global, wie in nodal_forces:
            # Normalkraft laengs n, Reibkraft entgegen den Tangentialrichtungen
            f = np.zeros(3)
            if c.active and c.kind != "dof_rot":
                f = c.Fn * c.normal
                if c.ct is not None:
                    t1, t2 = _axes_of(c)
                    f = f - (c.Ft[0] * t1 + c.Ft[1] * t2)
            out.append({"kind": c.kind, "label": c.label, "node": int(c.node),
                        "master": c.master, "gap": float(c.g), "Fn": float(c.Fn),
                        "Ft": float(np.linalg.norm(c.Ft)), "status": status,
                        "normal": c.normal.tolist(), "frozen": c.frozen,
                        "dof": int(c.dof), "limit": float(c.limit),
                        "F_vek": [float(x) for x in f]})
        return out

    def nodal_forces(self, nn: int) -> np.ndarray:
        """Kontaktkraefte auf die Knoten (nn,3), global."""
        F = np.zeros((nn, 3))
        for c in self.cons:
            if not c.active or c.kind == "dof_rot":
                continue
            f = c.Fn * c.normal
            if c.ct is not None:
                t1, t2 = _axes_of(c)
                f = f - (c.Ft[0] * t1 + c.Ft[1] * t2)
            if c.kind in ("support", "dof"):
                F[c.node] += f
            elif c.kind == "gap":
                F[c.node] += f
                F[c.master[0][0]] -= f
            else:
                F[c.node] += f
                for nd, w in zip(*c.master):
                    F[nd] -= w * f
        return F

    def support_reactions(self, nn: int) -> np.ndarray:
        """Nur einseitige Lager (fuer die Auflagerkraftsumme)."""
        R = np.zeros((nn, 3))
        for c in self.cons:
            if c.active and c.kind in ("support", "dof"):
                f = c.Fn * c.normal
                if c.ct is not None:
                    t1, t2 = _axes_of(c)
                    f = f - (c.Ft[0] * t1 + c.Ft[1] * t2)
                R[c.node] += f
        return R


def summary(results: list[dict]) -> str:
    if not results:
        return "keine Kontaktbedingungen"
    n_act = sum(1 for r in results if r["status"] != "offen")
    n_slip = sum(1 for r in results if r["status"] == "Gleiten")
    fmax = max((r["Fn"] for r in results), default=0.0)
    return (f"Kontakt: {n_act} von {len(results)} Bedingungen aktiv"
            + (f", {n_slip} gleitend" if n_slip else "")
            + f", max. Kontaktkraft {fmax/1e3:.2f} kN")
