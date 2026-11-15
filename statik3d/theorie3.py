"""
Theorie III. Ordnung: Gleichgewicht am verformten System mit **grossen
Verformungen** (geometrisch nichtlinear) fuer Stabtragwerke.

Korotationale Formulierung (Crisfield): jedes Stabelement bekommt ein
mitgehendes Bezugssystem aus der aktuellen Sehne und der mittleren Drehung
seiner beiden Knoten. Was der Stab in diesem System an Verformung uebrig
behaelt - Laengenaenderung und die kleinen Knotendrehungen relativ zur
Sehne - ist die elastische Verformung; sie ist klein, auch wenn sich das
ganze Element weit bewegt und dreht. Darauf wird die lineare lokale
Steifigkeit (Timoshenko/Bernoulli, Gelenke kondensiert) angewandt:

    f_l = k_l · d_l,   d_l = (0, θ₁ˡ, ΔL, θ₂ˡ),   f_int = Tᵀ f_l.

Knotendrehungen sind endliche Drehungen: je Knoten eine Drehmatrix R, die
mit jedem Iterationsschritt multiplikativ fortgeschrieben wird
(R ← exp(Δθ)·R). Gleichgewicht: f_int(u, R) = F_S + λ·(F − F_S) + F_imp;
geloest mit Newton-Raphson in Laststufen λ = 1/n … 1, Tangente
T ᵀ (k_l + k_g(N)) T
(korotational mit geometrischer Steifigkeit; der Rest der konsistenten
Tangente fehlt, dafuer ist das Residuum exakt - die Iteration konvergiert
gegen das richtige Gleichgewicht, nur nicht quadratisch).

Lasten sind richtungstreu (konservativ) und werden als Knotenlasten der
Ausgangslage angesetzt; Ersatzimperfektionen nach EC3 5.3.2 (Schiefstellung,
Vorkruemmung) kommen wie bei Theorie II. Ordnung als gleichwertige Lasten
dazu und werden je Laststufe aus den Normalkraeften neu gebildet.

Temperaturlasten und Vorspannkraefte (F_S) wirken seit dem 10.10.2026 ab
der ersten Laststufe voll, gesteigert wird nur der Rest
(plastizitaet.stufenlast; bis dahin wuchsen sie mit λ mit). Ohne beides
rechnet jede Stufe wie bisher.

Versatz der Stabenden (Exzentrizitaet): seit dem 12.11.2026 ein starrer Arm
vom Knoten zum Stabende, der mit der Knotendrehung mitdreht; der Stab liegt
zwischen seinen Stabenden (bis dahin fiel der Versatz still weg).

Grenzen: nur Stab- und Fachwerkelemente (keine Schalen, Volumen), kein
Kontakt, keine Zwangsverformungen; kleine Dehnungen (linear-elastisch).
Keine Starrkoerper (RBE2/RBE3) und keine starren Knotenkopplungen: seit dem
15.11.2026 mit Klartext abgewiesen (kopplung_sperre); bis dahin fielen die
Starrkoerper still weg, und starre Kopplungen wirkten als Feder von 1e4 N/m.
Federnde Kopplungen rechnet es mit.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

from . import assemble as asm
from .elements import beam3d as bm
from .model import Model

NDOF = 6


# ==========================================================================
# Endliche Drehungen
# ==========================================================================
def rot_exp(theta) -> np.ndarray:
    """Drehmatrix zum Drehvektor (Rodrigues)."""
    t = np.asarray(theta, float)
    a = float(np.linalg.norm(t))
    K = np.array([[0.0, -t[2], t[1]], [t[2], 0.0, -t[0]], [-t[1], t[0], 0.0]])
    if a < 1e-12:
        return np.eye(3) + K + 0.5 * K @ K
    return np.eye(3) + math.sin(a) / a * K + (1.0 - math.cos(a)) / a ** 2 * K @ K


def rot_log(R) -> np.ndarray:
    """Drehvektor zur Drehmatrix (Umkehrung von rot_exp), auch nahe 0 und π."""
    R = np.asarray(R, float)
    c = (np.trace(R) - 1.0) / 2.0
    c = min(1.0, max(-1.0, c))
    a = math.acos(c)
    w = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    s = math.sin(a)
    if a < 1e-6:
        return 0.5 * w                       # kleine Drehung: Schiefsymmetrischer Teil
    if abs(s) > 1e-6 and a < math.pi - 1e-3:
        return a / (2.0 * s) * w
    # nahe π: Achse aus R + I
    M = R + np.eye(3)
    k = int(np.argmax(np.diag(M)))
    axis = M[:, k] / np.linalg.norm(M[:, k])
    if np.dot(axis, w) < 0:
        axis = -axis
    return a * axis


# ==========================================================================
# Ergebnisse
# ==========================================================================
@dataclass
class Th3Info:
    """Was bei einem Lastfall oder einer Kombination nach Theorie III. Ordnung passiert ist."""
    name: str = ""
    gerechnet: bool = False
    schritte: int = 0
    iterationen: int = 0
    konvergenz: float = 0.0
    u_max_I: float = 0.0
    u_max_III: float = 0.0
    zuwachs: float = 0.0
    drehung_max: float = 0.0           # groesste Knotendrehung [rad]
    schiefstellung: dict = field(default_factory=dict)
    vorkruemmung: dict = field(default_factory=dict)
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    def text(self) -> str:
        if self.fehler:
            return f"{self.name}: {self.fehler}"
        return (f"{self.name}: {self.schritte} Laststufen, {self.iterationen} Iterationen, "
                f"u_max {self.u_max_I * 1e3:.3f} → {self.u_max_III * 1e3:.3f} mm "
                f"({self.zuwachs * 100:+.1f} %), größte Drehung {math.degrees(self.drehung_max):.2f}°")


@dataclass
class Th3Results:
    kombinationen: dict = field(default_factory=dict)      # name -> Th3Info
    settings: dict = field(default_factory=dict)

    @property
    def zuwachs_max(self) -> float:
        return max((i.zuwachs for i in self.kombinationen.values()), default=0.0)

    def summary(self) -> str:
        if not self.kombinationen:
            return "Theorie III. Ordnung: nichts gerechnet"
        n = sum(1 for i in self.kombinationen.values() if i.gerechnet)
        return (f"Theorie III. Ordnung: {n} von {len(self.kombinationen)} gerechnet, "
                f"größter Zuwachs der Verformung {self.zuwachs_max * 100:+.1f} %")


# ==========================================================================
# Element
# ==========================================================================
class _Stab:
    """Ein Stabelement mit Ausgangslage, lokaler Steifigkeit und Lasten.

    ``f_anf``: die lokalen Stabendlasten seiner Anfangsdehnung (Temperatur,
    Vorspannung; solver.case_feq_sofort). Seit dem 13.10.2026 steckt die
    Anfangsdehnung in der inneren Kraft im mitgehenden System,
    f_int = T^T (k_l d_l - f_anf), und N = (k_l d_l - f_anf)[6] in k_g - wie
    im Ergebnis (asm.stab_normalkraft). Bis dahin stand sie als Knotenlast der
    Ausgangslage in F, drehte nicht mit, und k_g las nur den elastischen
    Anteil: eine vorgespannte Saite hatte quer keine Steifigkeit aus ihrer
    Vorspannung."""

    def __init__(self, model: Model, i: int, feq: dict, f_anf=None):
        e = model.elements[i]
        self.i = i
        self.nodes = [int(n) for n in e.nodes]
        self.typ = e.typ
        sec = model.sections[e.sec]
        self.A, self.Ip = sec.A, sec.Iy + sec.Iz
        # Versatz der Stabenden (Exzentrizitaet) als starrer Arm a_i (global,
        # Ausgangslage) vom Knoten zum Stabende; er dreht mit dem Knoten mit
        # (P_i = x_i + R_i a_i), der Stab liegt zwischen seinen Stabenden.
        # Bis zum 12.11.2026 fiel der Versatz hier still weg: Kragarm mit
        # Versatz 0,1 m unter Zug in der Knotenlinie hob sich nach Theorie I.
        # Ordnung um F e L²/(2 E I), nach Theorie III. Ordnung gar nicht
        # (tests/test_theorie3_versatz.py)
        self.arm = None
        punkte = None
        A_v = asm.beam_versatz(e)
        if A_v is not None:
            X = np.asarray(model.nodes[e.nodes], float)
            T3n, _Ln = bm.local_axes(X[0], X[1], e.roll)
            arme = []
            for k in range(2):
                S = -A_v[6 * k:6 * k + 3, 6 * k + 3:6 * k + 6]     # [r_k]x
                arme.append(T3n.T @ np.array([S[2, 1], S[0, 2], S[1, 0]]))
            self.arm = arme
            punkte = X + np.asarray(arme)
        kl, T3, T, L = asm.beam_local(model, e, punkte)
        # Gelenke und Federgelenke in der geometrischen Steifigkeit wie in der
        # elastischen (asm.stab_endkinematik, wie Theorie II. Ordnung seit A7).
        # Bis zum 09.11.2026 bekam die Tangente die volle Balkenform: mit einer
        # Pendelstuetze als Balken mit Gelenken neben einem Kragstiel
        # konvergierte die Rechnung ab 5/6 der Knicklast nicht mehr
        # (Nebenbefund 16 a, tests/test_theorie_nebenbefund16.py)
        self.C = None if e.typ == "truss" else asm.stab_endkinematik(model, e, kl)
        fa = None if f_anf is None or not np.any(f_anf) else np.asarray(f_anf, float)
        # Die Stablasten des Elements (Strecken-, Eigengewicht, Temperatur)
        # kondensiert wie die Steifigkeit und wie im Lastvektor
        # (asm.stablasten_einbauen). Bis zum 12.11.2026 stand hier die
        # unkondensierte Festeinspannkraft: am Stabendgelenk mit Streckenlast
        # gab das Ergebnis q L²/12 statt 0 aus (eingespannter Einfeldtraeger
        # in einem Element: 15,0 statt 0 kNm am Gelenk, 15,0 statt 22,5 kNm
        # am Stabanfang; Nachstellung vom 11.11.2026). Das Gleichgewicht der
        # Knoten stimmte, nur die Stabendkraefte nicht.
        f0 = np.asarray(feq.get(i, np.zeros(12)), float)
        # die Anfangsdehnung wie in asm.stablasten_einbauen: Federgelenke, dann
        # Gelenke kondensiert
        if getattr(e, "hinge_springs", None):
            kl0 = kl
            kl, fa_, _rec = asm.hinge_springs(kl0, np.zeros(12) if fa is None else fa, e.hinge_springs)
            fa = None if fa is None else fa_
            _k, f0, _r = asm.hinge_springs(kl0, f0, e.hinge_springs)
        if e.hinges:
            kl0 = kl
            kl, fa_, _c = asm.condense(kl0, np.zeros(12) if fa is None else fa, e.hinges)
            fa = None if fa is None else fa_
            _k, f0, _c = asm.condense(kl0, f0, e.hinges)
        self.kl = kl
        self.f_anf = fa
        self.E0T = T3.T                   # Spalten: Ausgangsachsen ex, ey, ez
        self.L0 = L
        self.f0 = f0
        self.dofs = asm.element_dofs(e)
        # Die Stablast am Stabende (ohne Anfangsdehnung, kondensiert), global in
        # festen Richtungen - mit Versatz geht sie ueber den mitgedrehten Arm
        # auf den Knoten (:meth:`arm_last`, Verfahrensstand 41)
        self.F_last = None
        if self.arm is not None:
            fl0 = f0 if fa is None else f0 - fa
            if np.any(fl0[[0, 1, 2, 6, 7, 8]]):
                self.F_last = [self.E0T @ fl0[0:3], self.E0T @ fl0[6:9]]

    def arm_last(self, R: np.ndarray, lam: float):
        """Was die Stablast (Faktor ``lam``) ueber den mitgedrehten Arm mehr auf
        die Knoten bringt als ueber den unverdrehten, der in F_ref steht
        (asm.stablasten_einbauen): je Stabende das Moment (R_i a_i - a_i) x F_i,
        und dessen Ableitung nach der Drehung [F_i]x [R_i a_i]x (wie die innere
        Kraft in :meth:`knoten`). Rueckgabe [(Knoten, dM (3,), dK (3, 3))] oder
        [] ohne Stablast am Stab mit Versatz.

        Bis zum 14.11.2026 blieb die Stablast eines Stabs mit Versatz eine
        feste Knotenlast mit dem unverdrehten Arm: Kragarm 4 m, Versatz 0,5 m,
        qz -400 kN/m, Einspannmoment 3061,42 statt 3171,17 kNm (Kurzstabmodell),
        auf der unsicheren Seite (tests/test_versatz_achsen_lotrecht.py)."""
        if self.F_last is None:
            return []
        aus = []
        for k, n in enumerate(self.nodes):
            F = lam * self.F_last[k]
            a_r = R[n] @ self.arm[k]
            aus.append((n, np.cross(a_r - self.arm[k], F), bm._skew(F) @ bm._skew(a_r)))
        return aus

    def zustand(self, X: np.ndarray, R: np.ndarray):
        """(f_l, T, k_g, N, L) im mitgehenden System der aktuellen Lage; f_l
        ist der elastische Anteil k_l d_l, N die Normalkraft mit der
        Anfangsdehnung. T wirkt auf die Stabenden (mit Versatz: hinter dem
        Arm, :meth:`knoten`)."""
        n1, n2 = self.nodes
        if self.arm is None:
            d = X[n2] - X[n1]
        else:
            d = (X[n2] + R[n2] @ self.arm[1]) - (X[n1] + R[n1] @ self.arm[0])
        L = float(np.linalg.norm(d))
        e1 = d / L
        Q1 = R[n1] @ self.E0T
        Q2 = R[n2] @ self.E0T
        phi = rot_log(R[n1].T @ R[n2])
        Qm = R[n1] @ rot_exp(0.5 * phi) @ self.E0T
        q2 = Qm[:, 1]
        e2 = q2 - float(q2 @ e1) * e1
        n = float(np.linalg.norm(e2))
        if n < 1e-9:
            q3 = Qm[:, 2]
            e2 = np.cross(q3, e1)
            n = float(np.linalg.norm(e2))
        e2 /= n
        e3 = np.cross(e1, e2)
        E = np.column_stack([e1, e2, e3])
        th1 = rot_log(E.T @ Q1)
        th2 = rot_log(E.T @ Q2)
        dl = np.concatenate([[0.0, 0.0, 0.0], th1, [L - self.L0, 0.0, 0.0], th2])
        fl = self.kl @ dl
        N = float(fl[6]) if self.f_anf is None else float(fl[6] - self.f_anf[6])
        if self.typ == "truss":
            # Saite N/L - dieselbe Form wie asm.geometric_stiffness (14.10.2026)
            kg = bm.kg_local_saite(N, L)
        else:
            kg = bm.kg_local_beam(N, L, self.A, self.Ip)
            if self.C is not None:
                kg = self.C.T @ kg @ self.C
        T = bm.transform_matrix(E.T)
        return fl, T, kg, N, L

    def knoten(self, R: np.ndarray, f_e: np.ndarray, K_e: np.ndarray):
        """Innere Kraefte und Tangente der Stabenden (global, 12) auf die
        Knoten: ohne Versatz unveraendert. Mit Versatz bewegt sich das
        Stabende starr mit dem Knoten, δu_ende = δu - [a_i]x δθ mit dem
        mitgedrehten Arm a_i = R_i a_i0 (wie bm.versatz_matrix, nur in der
        aktuellen Lage): f_knoten = Bᵀ f_e (Moment M + a_i × F),
        K = Bᵀ K_e B + [F_i]x [a_i]x im Drehblock (die Ableitung von a_i × F_i
        nach der Drehung des Arms)."""
        if self.arm is None:
            return f_e, K_e
        B = np.eye(12)
        Ka = np.zeros((12, 12))
        for k, n in enumerate(self.nodes):
            Sa = bm._skew(R[n] @ self.arm[k])
            B[6 * k:6 * k + 3, 6 * k + 3:6 * k + 6] = -Sa
            Ka[6 * k + 3:6 * k + 6, 6 * k + 3:6 * k + 6] = bm._skew(f_e[6 * k:6 * k + 3]) @ Sa
        return B.T @ f_e, B.T @ K_e @ B + Ka


class _Seil:
    """Ein Seil als elastische Kettenlinie (verbindung.seil_kettenlinie).

    Das Seil traegt nur Zug und haengt unter seinem Eigengewicht durch. Seine
    ungedehnte Laenge steht am Element (``laenge0``); ist sie 0, wird die
    Sehnenlaenge der Ausgangslage genommen - das Seil ist dann gerade
    gespannt und haengt nur unter seinem Gewicht durch.

    ``n_anfang``: die Kraft seiner Anfangsdehnung bei festgehaltenen Enden
    (Vorspannung, Temperatur; asm.anfangsnormalkraft). Sie verkuerzt die
    spannungsfreie Laenge auf L0/(1 + n_anfang/(E A)): gerade gespannt traegt
    das Seil dann genau n_anfang, wie nach Theorie I. Ordnung. Das Gewicht
    bleibt dasselbe (w L0 gleich). Bis zum 13.10.2026 fiel die Vorspannung
    eines Seils hier still weg (Befund 3: u_x und Seilkraft am Seil mit 70 kN
    Vorspannung bitgleich denen ohne).

    ``q_last``: eine gleichmaessige Streckenlast ueber die ganze Seillaenge,
    global [N/m] **je Bogenlaenge** (:func:`seil_streckenlasten`). Sie geht wie
    das Eigengewicht in die Kettenlinie, je ungedehnter Laenge, Summe q L0.
    Bis zum 14.10.2026 galt sie je Sehnenlaenge (w = q L/L0, Summe q L): ein
    Seil mit Laenge0 ueber der Sehne trug zu wenig (Spannweite 10 m,
    L0 = 10,42 m, 1 kN/m: Auflager 10,00 statt 10,42 kN, Horizontalzug 9,60
    statt 10,00 kN; mit Laenge0 = 0, der Sehne, ist beides dasselbe).

    ``p_last``: eine gleichmaessige Streckenlast **je Projektion** (RFEM
    „projizierte Länge“, BeamLoad.bezugslaenge = "projektion", seit dem
    14.10.2026), global [N/m]: das Seil rechnet dann als elastische Parabel
    (verbindung.seil_parabel), Summe p l mit der Projektion l. Kettenlinie
    und Parabel zugleich bildet das Element nicht ab - solve_theorie3 sperrt
    den Lastfall vorher.
    """

    def __init__(self, model: Model, i: int, g, n_anfang: float = 0.0, q_last=None, p_last=None):
        e = model.elements[i]
        mat = model.materials[e.mat]
        sec = model.sections[e.sec]
        self.i = i
        self.nodes = [int(n) for n in e.nodes]
        X = model.nodes[self.nodes]
        L = float(np.linalg.norm(X[1] - X[0]))
        self.L0 = float(getattr(e, "laenge0", 0.0) or 0.0) or L
        self.EA = float(mat.E * sec.A)
        # Streckenlast je ungedehnter Laenge: das Eigengewicht des Lastfalls
        self.w = np.asarray(g, float) * mat.rho * sec.A
        if q_last is not None:
            # je Bogenlaenge = je ungedehnter Laenge wie das Eigengewicht
            self.w = self.w + np.asarray(q_last, float)
        # je Projektion: die Parabel (die Projektion aendert keine Vorspannung)
        self.p = None if p_last is None or not np.any(p_last) else np.asarray(p_last, float)
        self.n_anfang = float(n_anfang or 0.0)
        if self.n_anfang:
            L0 = self.L0
            self.L0 = L0 / (1.0 + self.n_anfang / self.EA)
            self.w = self.w * (L0 / self.L0)
        self.dofs = np.array([NDOF * self.nodes[0] + k for k in range(3)]
                             + [NDOF * self.nodes[1] + k for k in range(3)], int)

    def zustand(self, X: np.ndarray):
        """(innere Knotenkraefte (6,), Tangente (6,6), Angaben) in dieser Lage."""
        from .elements.verbindung import seil_kettenlinie, seil_parabel
        if self.p is not None:
            return seil_parabel(X[self.nodes[0]], X[self.nodes[1]], self.L0, self.EA, self.p)
        return seil_kettenlinie(X[self.nodes[0]], X[self.nodes[1]], self.L0, self.EA, self.w)


def seil_streckenlasten(model: Model, factors: dict, aktiv=None) -> tuple:
    """Die Streckenlasten auf Seilen fuer Theorie III. Ordnung: ({Element:
    q global [N/m] je Bogenlaenge}, {Element: p global [N/m] je Projektion},
    [Zeilen]).

    Seit dem 14.10.2026 zaehlt der Bezug der Last (BeamLoad.bezugslaenge, aus
    RFEM „wahre“ bzw. „projizierte Länge“): je Bogenlaenge geht sie in die
    Kettenlinie, je Projektion in die Parabel (verbindung.seil_parabel). Eine
    lokale Last gilt je Bogenlaenge. Lasten je Projektion in verschiedenen
    Richtungen auf demselben Seil bildet die Parabel nicht ab - Zeile.

    Das Seil rechnet hier als Kettenlinie (verbindung.seil_kettenlinie), und
    die kennt nur eine gleichmaessige Streckenlast je Laenge in fester
    Richtung - wie das Eigengewicht. Eine Streckenlast, die ueber die ganze
    Seillaenge gleich ist (global oder lokal, die lokale Richtung in der
    Ausgangslage, richtungstreu wie alle Lasten hier), geht so hinein; mit
    ihrem Faktor der Kombination. Trapezfoermig oder abschnittsweise bildet
    die Kettenlinie sie nicht ab: als Knotenlast an den Seilenden ginge sie
    am Seil vorbei in die Lager (ein Seilelement zwischen zwei Festpunkten
    truege von ihr nichts), und ein Teilen des Seils in der Rechnung waere ein
    Umbau. Solche Lasten stehen als Zeile mit Seil, Lastfall und Betrag in
    der zweiten Liste; solve_theorie3 sperrt dann den Lastfall.

    Bis zum 14.10.2026 nahm solve_theorie3 die Lasten des Seils aus dem
    Lastvektor (das Eigengewicht steckt in der Kettenlinie) und mit ihnen
    jede Streckenlast: 10 kN quer auf ein Seil ergaben u = 0 und
    Auflager z = 0 (tests/test_stab_nachzug.py)."""
    from . import zahlen as zl
    from .solver import _stab_namen
    namen = None
    gleich: dict = {}
    projektion: dict = {}
    zeilen: list = []
    for lf, f in factors.items():
        lc = model.load_cases.get(lf)
        if lc is None or not f:
            continue
        for bl in lc.beam_loads:
            i = int(bl.elem)
            if not 0 <= i < len(model.elements):
                continue
            e = model.elements[i]
            if e.typ != "seil" or (aktiv is not None and not aktiv[i]):
                continue
            X = model.nodes[e.nodes]
            T3, L = bm.local_axes(X[0], X[1], e.roll)
            proj = bl.system == "global" and getattr(bl, "bezugslaenge", "") == "projektion"
            if proj:
                # je Projektion: die globale Last wie eingegeben (ohne die
                # Umrechnung je Stablaenge, asm.projektionsfaktor)
                q1 = T3 @ np.asarray(bl.q, float)
                q2 = T3 @ np.asarray(bl.q2 if bl.q2 is not None else bl.q, float)
            else:
                q1, q2 = asm.beam_load_local(model, e, bl)
            a = max(0.0, float(getattr(bl, "a", 0.0) or 0.0))
            b = L if getattr(bl, "b", None) is None else min(float(bl.b), L)
            if b <= a:
                continue                  # wirkt nirgends (wie in den Stablasten)
            groesse = max(float(np.abs(q1).max()), float(np.abs(q2).max()), 1e-300)
            konstant = float(np.abs(q1 - q2).max()) <= 1e-12 * groesse
            ganz = a <= 1e-9 * L and b >= L * (1.0 - 1e-9)
            if konstant and ganz and proj:
                neu = float(f) * (T3.T @ q1)
                alt = projektion.get(i)
                if alt is not None and np.any(alt) and np.any(neu) and float(
                        np.linalg.norm(np.cross(alt, neu))) > 1e-9 * float(np.linalg.norm(alt) * np.linalg.norm(neu)):
                    if namen is None:
                        namen = _stab_namen(model)
                    zeilen.append(f"Seil {namen.get(i, f'Element {i + 1}')}, Lastfall {lf}: je Projektion in "
                                  "einer anderen Richtung als die übrigen Lasten je Projektion")
                projektion[i] = (np.zeros(3) if alt is None else alt) + neu
                continue
            if konstant and ganz:
                gleich[i] = gleich.get(i, np.zeros(3)) + float(f) * (T3.T @ q1)
                continue
            if namen is None:
                namen = _stab_namen(model)
            b1 = zl.zahl_text(float(np.linalg.norm(q1)) / 1e3)
            b2 = zl.zahl_text(float(np.linalg.norm(q2)) / 1e3)
            art = ", ".join(([] if konstant else ["trapezförmig"]) + ([] if ganz else ["abschnittsweise"]))
            betrag = f"{b1} kN/m" if konstant else f"{b1} → {b2} kN/m"
            ort = "" if ganz else f" von {zl.zahl_text(a)} bis {zl.zahl_text(b)} m"
            zeilen.append(f"Seil {namen.get(i, f'Element {i + 1}')}, Lastfall {lf}: {art} {betrag}{ort}"
                          + (" je Projektion" if proj else ""))
    return gleich, projektion, zeilen


# ==========================================================================
# Loesung
# ==========================================================================
def woelb_sperre(model: Model, aktiv=None) -> str:
    """Leer - oder der Grund, warum Theorie III. Ordnung nicht rechnet: ein
    Balken mit Woelbkrafttorsion (model.stab_woelbt). Das mitgehende System
    (_Stab) kennt nur die 12 Stab-FHG, nicht die Verwoelbung; bis zum
    14.11.2026 brach die Rechnung mit „Gleichungssystem singulär: cannot
    reshape …“ ab (Befund B3). Entscheidung des Anwenders vom 14.11.2026:
    vorher erkennen und mit Klartext abweisen, auch in der Modellpruefung
    (Model.check). Elemente ab 0 gezaehlt wie Tabelle und Modellbaum."""
    els = [i for i, e in enumerate(model.elements)
           if (aktiv is None or aktiv[i]) and model.stab_woelbt(e)]
    if not els:
        return ""
    from .solver import _stab_namen
    i = els[0]
    name = _stab_namen(model).get(i)
    wo = f"Balken {name} (Element {i}, ab 0 gezählt)" if name else f"Balken (Element {i}, ab 0 gezählt)"
    mehr = f" und {len(els) - 1} weitere Elemente" if len(els) > 1 else ""
    return (f"Theorie III. Ordnung rechnet keine Wölbkrafttorsion – {wo}{mehr}; bitte nach "
            "Theorie II. Ordnung rechnen oder die Wölbkrafttorsion abschalten")


def _nur_staebe(model: Model, aktiv) -> bool:
    """Ob in der Rechnung mit ``aktiv`` nur Stabelemente (asm.LINE_TYPES)
    wirken. Sonst weist :func:`solve_theorie3` mit „nur für Stabtragwerke“ ab,
    und die Sperre fuer Starrkoerper und Kopplungen hat dort nichts zu sagen
    (die Einleitungen an Flaechen und Volumen sind auch Starrkoerper)."""
    return not any((aktiv is None or aktiv[i]) and e.typ not in asm.LINE_TYPES
                   for i, e in enumerate(model.elements))


def _wirksame_knoten_th3(model: Model, aktiv) -> np.ndarray:
    """Maske (nn,): Knoten, die in der Rechnung mit ``aktiv`` mittragen: an
    ihnen haengt ein wirksames Element (ohne Maske: irgendein Element), oder
    sie haengen ueber Starrkoerper und Kopplungen - auch ueber Knoten ohne
    Element hinweg - an einem solchen Knoten (Huelle bis zum Fixpunkt).

    Bis zur Gegenpruefung vom 15.11.2026 zaehlten nur Knoten mit Element.
    Ein Starrkoerper oder eine starre Kopplung zwischen zwei Knoten ohne
    Element blieb so ungezaehlt: Lastknoten P per RBE2 an Q, Q per federnder
    Kopplung am Kragarmende b - Theorie III. Ordnung w(b) = 0 mm statt
    F L³/(3 E I) = 0,5357 mm; mit starrer Kopplung P-Q statt RBE2 w(P) =
    100,5357 mm (Straffeder 1e4 N/m). Ein Starrkoerper oder eine Kopplung,
    deren ganze Kette an keinem wirksamen Element haengt, traegt nichts und
    bleibt weiter ungezaehlt (Situation mit abgeschaltetem Nebenarm).

    Ausloeser wie bisher: beim Starrkoerper Master oder ein Slave, bei der
    verteilenden Kopplung eines Stabendes nur ein Slave
    (stabeinleitung.ist_verteilkopplung); bei Kopplungen
    situationen.kopplung_bleibt."""
    from .situationen import aktive_knoten, kopplung_bleibt
    from . import stabeinleitung as _se
    maske = np.ones(len(model.elements), dtype=bool) if aktiv is None else np.asarray(aktiv, bool)
    kn = np.array(aktive_knoten(model, maske), dtype=bool, copy=True)
    nn = len(kn)
    # Ein Lagerknoten, an dem ueberhaupt kein Element haengt, traegt selbst:
    # P (Last) per RBE2 an den eingespannten Knoten Q, beide ohne Element -
    # Theorie III. Ordnung verlor die Last an P still (Summe Rz 1000 statt
    # 2000 N, Restluecke R1 der Gegenpruefung vom 15.11.2026). Ein Knoten mit
    # abgeschalteten Elementen zaehlt dagegen nicht (Situation).
    ueberhaupt = np.asarray(aktive_knoten(model, np.ones(len(model.elements), dtype=bool)), bool)
    for sp in (getattr(model, "supports", None) or []):
        n = int(sp.node)
        if 0 <= n < nn and not ueberhaupt[n]:
            kn[n] = True
    gruppen = []                         # (Ausloeser, alle Knoten) je Starrkoerper
    for sk in (getattr(model, "starrkoerper", None) or []):
        master = int(sk.master)
        slaves = [int(x) for x in (sk.slaves or []) if 0 <= int(x) < nn and int(x) != master]
        if not slaves:
            continue
        alle = slaves + ([master] if 0 <= master < nn else [])
        gruppen.append((slaves if _se.ist_verteilkopplung(sk) else alle, alle))
    kopp = [kp for kp in (getattr(model, "kopplungen", None) or [])
            if 0 <= int(kp.node_a) < nn and 0 <= int(kp.node_b) < nn]
    geaendert = True
    while geaendert:
        geaendert = False
        for ausloeser, alle in gruppen:
            if not all(kn[x] for x in alle) and any(kn[x] for x in ausloeser):
                kn[alle] = True
                geaendert = True
        for kp in kopp:
            a, b = int(kp.node_a), int(kp.node_b)
            if not (kn[a] and kn[b]) and kopplung_bleibt(model, kp, kn):
                kn[a] = kn[b] = True
                geaendert = True
    return kn


def _namen_liste(namen: list, n_max: int = 4) -> str:
    teil = ", ".join(namen[:n_max])
    return teil + (f" und {len(namen) - n_max} weitere" if len(namen) > n_max else "")


def starrkoerper_sperre(model: Model, aktiv=None) -> str:
    """Leer - oder der Grund, warum Theorie III. Ordnung nicht rechnet: ein
    wirksamer Starrkoerper (Model.starrkoerper, RBE2 oder RBE3).

    Das mitgehende System kennt nur Staebe, Seile, Federlager und die
    Knotenkopplungen; die Starrkoerper (assemble.starrkoerper) las es nie.
    Bis zum 15.11.2026 rechnete es sie still nicht mit: Kragstuetze 4 m mit
    Arm 0,3 m quer als RBE2, Theorie I. Ordnung 7,032 mm, Theorie III. Ordnung
    0,000 mm (der Kopfknoten hing an nichts); derselbe Arm als Balken STARR
    oder als Versatz 8,23 mm. Entscheidung des Anwenders (Runde k8): mit
    Klartext abweisen wie die Woelbkrafttorsion (:func:`woelb_sperre`).

    Es zaehlen nur Starrkoerper, an deren Knoten ein in der Rechnung
    wirksames Element haengt (Master oder ein Slave; bei der verteilenden
    Kopplung eines Stabendes ein Slave, wie situationen.kopplung_bleibt)."""
    sk_liste = getattr(model, "starrkoerper", None) or []
    if not sk_liste:
        return ""
    from . import stabeinleitung as _se
    kn = _wirksame_knoten_th3(model, aktiv)
    nn = len(kn)
    namen = []
    for sk in sk_liste:
        slaves = [int(x) for x in (sk.slaves or []) if 0 <= int(x) < nn and int(x) != int(sk.master)]
        if not slaves:
            continue
        master = int(sk.master)
        wirksam = any(kn[s] for s in slaves)
        if not _se.ist_verteilkopplung(sk) and 0 <= master < nn:
            wirksam = wirksam or bool(kn[master])
        if wirksam:
            namen.append(str(sk.name or "ohne Namen"))
    if not namen:
        return ""
    return (f"Theorie III. Ordnung rechnet keine Starrkörper (RBE2/RBE3: {_namen_liste(namen)}). "
            "Starrkörper durch Balken mit Querschnitt STARR oder Versatz der Stabenden ersetzen "
            "oder Theorie II. Ordnung wählen.")


def starre_kopplung_sperre(model: Model, aktiv=None) -> str:
    """Leer - oder der Grund, warum Theorie III. Ordnung nicht rechnet: eine
    wirksame starre Knotenkopplung (Model.kopplungen mit Steifigkeit ``inf``).

    asm.kopplungen setzt starre Richtungen als Straffeder mit 1e4-mal der
    groessten Hauptdiagonale der uebergebenen Matrix; Theorie III. Ordnung
    uebergibt eine leere Matrix, die Straffeder hat dort 1e4 N/m. Zwei
    Kragarme 3 m, im Feldpunkt starr gekoppelt, 1 kN: Theorie I. Ordnung und
    Hand 0,2679 mm, Theorie III. Ordnung bis zum 15.11.2026 0,5329 mm (nur
    ein Kragarm traegt). Kopplungen mit endlicher Federsteifigkeit rechnet sie
    richtig (wie Theorie I. Ordnung und Hand); sie bleiben. Es zaehlen nur
    Kopplungen, die in der Rechnung wirken (situationen.kopplung_bleibt)."""
    kopp = getattr(model, "kopplungen", None) or []
    if not kopp:
        return ""
    from .situationen import kopplung_bleibt
    kn = _wirksame_knoten_th3(model, aktiv)
    starr, gruppen = 0, []
    for kp in kopp:
        if not any(not np.isfinite(w) for _r, w in kp.paare()):
            continue
        if not kopplung_bleibt(model, kp, kn):
            continue
        starr += 1
        g = str(getattr(kp, "gruppe", "") or "").strip()
        if g and g not in gruppen:
            gruppen.append(g)
    if not starr:
        return ""
    wo = f"{starr} Kopplung" if starr == 1 else f"{starr} Kopplungen"
    if gruppen:
        wo += (", Gruppe " if len(gruppen) == 1 else ", Gruppen ") + _namen_liste(gruppen)
    return (f"Theorie III. Ordnung rechnet keine starren Knotenkopplungen ({wo}). Die Kopplung mit "
            "endlicher Federsteifigkeit ansetzen, durch Balken mit Querschnitt STARR ersetzen oder "
            "Theorie II. Ordnung wählen.")


def kopplung_sperre(model: Model, aktiv=None) -> str:
    """Starrkoerper und starre Knotenkopplungen (Runde k8, 15.11.2026):
    leer, oder der Text der Abweisung."""
    return " ".join(t for t in (starrkoerper_sperre(model, aktiv), starre_kopplung_sperre(model, aktiv)) if t)


def kopplung_sperre_modell(model: Model) -> dict:
    """{Text der Abweisung: [Lastfaelle und Kombinationen]} fuer alles, was
    nach Theorie III. Ordnung gestellt ist - je in seiner Situation (nur dort
    wirksame Starrkoerper und Kopplungen zaehlen). Fuer die Modellpruefung
    (Model.check) und die Verfahrenstabelle; leer, wenn nichts abgewiesen wird."""
    if not (getattr(model, "starrkoerper", None) or getattr(model, "kopplungen", None)):
        return {}
    objekte = [o for o in list(model.load_cases.values()) + list(model.combinations.values())
               if model.theorie_von(o) == "III"]
    out: dict = {}
    je_situation: dict = {}
    for o in objekte:
        sit = str(getattr(o, "situation", "") or "")
        if sit not in je_situation:
            try:
                aktiv = model.aktive_elemente(sit)
            except KeyError:                 # unbekannte Situation: wie die Grundstellung
                aktiv = None
            # mit Flaechen-, Volumen- oder Federelementen weist die Rechnung
            # zuerst „nur für Stabtragwerke“ ab (dieselbe Bedingung wie in
            # solve_theorie3): hier kein irrefuehrender FEHLER (Gegenpruefung
            # 15.11.2026, Schale mit RBE2-Lastknoten)
            je_situation[sit] = kopplung_sperre(model, aktiv) if _nur_staebe(model, aktiv) else ""
        text = je_situation[sit]
        if text:
            out.setdefault(text, []).append(str(o.name))
    return out


def solve_theorie3(model: Model, factors: dict, name: str, schritte: int = 10,
                   max_iter: int = 30, tol: float = 1e-6, imperfektionen: bool = None,
                   elastisch: bool = True, richtung=None, alle_vorkruemmungen: bool = False,
                   aktiv=None, progress=None, stabteilung: bool = True):
    """Einen Lastfall oder eine Kombination (``factors``) nach Theorie III.
    Ordnung rechnen. Rueckgabe (Results, Th3Info).

    ``stabteilung``: Balken intern teilen (statik3d.stabteilung, seit
    12.11.2026) - gerechnet wird am geteilten Modell, das Ergebnis gilt fuer
    die Knoten und Elemente von ``model``."""
    from .solver import case_loads, case_prescribed, Results
    from . import supports as sup
    # vor der Stabteilung: die Elementnummer ist die des Modells (B3)
    sperre_w = woelb_sperre(model, aktiv)
    if sperre_w:
        raise ValueError(sperre_w)
    # Starrkoerper und starre Kopplungen rechnet das mitgehende System nicht
    # (Runde k8, 15.11.2026): abweisen statt still ohne sie. Mit Flaechen-,
    # Volumen- oder Federelementen sagt die Pruefung „nur Stabtragwerke“ unten
    # den eigentlichen Grund (die Einleitungen dort sind auch Starrkoerper)
    if _nur_staebe(model, aktiv):
        sperre_k = kopplung_sperre(model, aktiv)
        if sperre_k:
            raise ValueError(sperre_k)
    ll_hinweise = []
    if stabteilung:
        from .stabteilung import (teilen, zurueck, teilzahlen, kraefte_theorie1, FAKTOR_THEORIE3,
                                  laengslast_hinweise)
        gemerkt: dict = {}

        def _kraefte():
            # Normalkraefte nach Theorie I. Ordnung - einmal, fuer Teilung und Hinweis
            if "n" not in gemerkt:
                try:
                    from .solver import StaticSystem
                    gemerkt["n"] = kraefte_theorie1(model, StaticSystem(model, aktiv=aktiv), factors)
                except Exception:          # noqa: BLE001 - ohne Bezug keine Teilung
                    gemerkt["n"] = None
            return gemerkt["n"]
        # Stab mit Last in Stabrichtung in weniger als vier gerechneten
        # Elementen: Hinweis, kein geaenderter Wert (Runde k7, 14.11.2026)
        ll_hinweise = laengslast_hinweise(model, factors, aktiv, FAKTOR_THEORIE3, kraefte=_kraefte)
        fein = None
        if teilzahlen(model, aktiv):
            kraefte = _kraefte()
            if kraefte is not None:
                fein = teilen(model, aktiv, teilzahlen(model, aktiv, FAKTOR_THEORIE3, kraefte))
        if fein is not None:
            m2, abb, aktiv2 = fein
            res2, info = solve_theorie3(m2, factors, name, schritte=schritte, max_iter=max_iter,
                                        tol=tol, imperfektionen=imperfektionen, elastisch=elastisch,
                                        richtung=richtung, alle_vorkruemmungen=alle_vorkruemmungen,
                                        aktiv=aktiv2, progress=progress, stabteilung=False)
            info.hinweise.extend(h for h in ll_hinweise if h not in info.hinweise)
            return zurueck(model, res2, abb), info
    t0 = time.time()
    info = Th3Info(name=name)
    info.hinweise.extend(ll_hinweise)
    ds = model.design
    if imperfektionen is None:
        imperfektionen = bool(getattr(ds, "imperfektionen", True))
    ne = len(model.elements)
    wirksam = [i for i in range(ne) if aktiv is None or aktiv[i]]
    fremd = [i for i in wirksam if model.elements[i].typ not in asm.LINE_TYPES]
    if fremd:
        raise ValueError("Theorie III. Ordnung gibt es nur für Stabtragwerke - "
                         f"{len(fremd)} Flächen-/Volumenelemente im Modell")
    if model.has_contact:
        raise ValueError("Theorie III. Ordnung nicht zusammen mit Kontakt")
    from .vorspannkraft import theorie_sperre
    sperre = theorie_sperre(model, factors, "III")
    if sperre:
        raise ValueError(sperre)         # Vorspannkraft (Soll nach Verankerung), 13.10.2026
    us = case_prescribed(model, factors)
    if us is not None and np.any(np.asarray(us) != 0):
        raise ValueError("Theorie III. Ordnung nicht mit Zwangsverformungen")
    F_ref, feq, q, temp = case_loads(model, factors, aktiv)
    nn, ndof = model.nn, model.ndof
    # Seile rechnen als Kettenlinie: ihr Eigengewicht steckt in der
    # Kettenlinie selbst und darf nicht noch einmal als Knotenlast wirken.
    g_ges = np.zeros(3)
    for lf, f in factors.items():        # nicht ``name``: der ist das Ergebnis
        lc = model.load_cases.get(lf)
        if lc is not None:
            g_ges = g_ges + float(f) * np.asarray(lc.gravity, float)
    # Anfangsdehnung (Temperatur, Vorspannung) je Stab und Seil: sie wirkt
    # seit dem 13.10.2026 in der inneren Kraft (_Stab) bzw. in der
    # spannungsfreien Laenge (_Seil) - nicht mehr als Knotenlast
    from .solver import case_sofort, case_feq_sofort
    feq_anf = case_feq_sofort(model, factors, aktiv)
    # Streckenlasten auf Seilen gehen wie das Eigengewicht in die
    # Kettenlinie; was sie nicht abbildet, sperrt den Lastfall (14.10.2026)
    q_seil, p_seil, nicht_abbildbar = seil_streckenlasten(model, factors, aktiv)
    if nicht_abbildbar:
        raise ValueError(
            "Theorie III. Ordnung: die Kettenlinie eines Seils trägt nur eine gleichmäßige "
            "Streckenlast über die ganze Seillänge – nicht gerechnet wegen "
            + "; ".join(nicht_abbildbar[:6]) + (" …" if len(nicht_abbildbar) > 6 else "")
            + ". Das Seil an den Laststellen in Elemente teilen (je Element gleichmäßig) oder "
              "die Last als Knotenlast ansetzen")
    # je Projektion (Parabel) und je Bogenlaenge (Kettenlinie, auch das
    # Eigengewicht) zugleich auf einem Seil bildet keins der beiden ab
    gemischt = []
    for i in sorted(p_seil):
        if not np.any(p_seil[i]):
            continue
        e = model.elements[i]
        gewicht = np.any(g_ges) and float(model.materials[e.mat].rho or 0.0) > 0.0
        if gewicht or (i in q_seil and np.any(q_seil[i])):
            from .solver import stab_name
            gemischt.append(f"Seil {stab_name(model, i)}: "
                            + ("Eigengewicht" if gewicht else "Streckenlast je Bogenlänge")
                            + " und Streckenlast je Projektion")
    if gemischt:
        raise ValueError(
            "Theorie III. Ordnung: ein Seil rechnet mit einer Streckenlast je Bogenlänge als "
            "Kettenlinie, mit einer je Projektion als Parabel – beides zugleich nicht; nicht "
            "gerechnet wegen " + "; ".join(gemischt[:6]) + (" …" if len(gemischt) > 6 else "")
            + ". Die Lasten auf einen Bezug bringen (etwa je Bogenlänge) oder getrennt rechnen")
    seile = [_Seil(model, i, g_ges, asm.anfangsnormalkraft(feq_anf[i]) if i in feq_anf else 0.0,
                   q_seil.get(i), p_seil.get(i))
             for i in wirksam if model.elements[i].typ == "seil"]
    for sl_ in seile:
        e = model.elements[sl_.i]
        kl, T3, T, L = asm.beam_local(model, e)
        F_ref[asm.element_dofs(e, model)[:12]] -= T.T @ np.asarray(feq.get(sl_.i, np.zeros(12)), float)
        feq.pop(sl_.i, None)
        q.pop(sl_.i, None)
    staebe = [_Stab(model, i, feq, feq_anf.get(i)) for i in wirksam
              if model.elements[i].typ != "seil"]
    staebe_arm_last = [st for st in staebe if st.F_last is not None]
    # Die Anfangsdehnung der Staebe aus F_ref: dieselbe Last, die
    # asm.load_vector eingebaut hat (asm.stablasten_einbauen)
    F_anf = None
    F_ref_voll = F_ref              # die Last mit Anfangsdehnung (Bezug I. Ordnung)
    mit_anf = {st.i: feq_anf[st.i] for st in staebe if st.f_anf is not None}
    if mit_anf:
        F_anf = np.zeros(ndof)
        asm.stablasten_einbauen(model, mit_anf, F_anf)
        asm.mittelknoten_umlenken(model, F_anf)
        F_ref = F_ref - F_anf
    # Temperaturlasten und Vorspannkraefte wirken ab der ersten Laststufe
    # voll (10.10.2026) - in Staeben und Seilen als Anfangsdehnung ohnehin;
    # was sonst sofort wirkt, steigert die Stufe nicht
    from .plastizitaet import SOFORT_VOLL, stufenlast
    F_S = case_sofort(model, factors, aktiv, ohne={sl_.i for sl_ in seile} | set(mit_anf))
    if F_S is not None or mit_anf or any(sl_.n_anfang for sl_ in seile):
        info.hinweise.append(SOFORT_VOLL)

    # Lager: starr (u = 0) und Federn
    lin, _ = sup.split(sup.expand(model))
    fixed = np.zeros(ndof, dtype=bool)
    feder_idx, feder_k = [], []
    for e in lin:
        if e.typ == "rigid":
            if e.value:
                raise ValueError("Theorie III. Ordnung nicht mit vorgegebenen Lagerverschiebungen")
            fixed[e.index] = True
        elif e.typ == "spring" and e.stiffness:
            feder_idx.append(int(e.index))
            feder_k.append(float(e.stiffness))
    feder_idx = np.array(feder_idx, int)
    feder_k = np.array(feder_k, float)
    Kk = asm.kopplungen(model, sparse.csr_matrix((ndof, ndof)), aktiv=aktiv)
    Kk = Kk.tocsr() if Kk is not None else None

    X0 = np.asarray(model.nodes, float).copy()
    u = np.zeros((nn, 3))
    R = np.tile(np.eye(3), (nn, 1, 1))

    def gesamtvektor():
        d = np.zeros((nn, NDOF))
        d[:, :3] = u
        for n in range(nn):
            d[n, 3:] = rot_log(R[n])
        return d.ravel()

    def aufbau():
        """Innere Kraefte und Tangente in der aktuellen Lage."""
        X = X0 + u
        f_int = np.zeros(ndof)
        rows, cols, vals = [], [], []
        zust = {}
        for sl_ in seile:
            f_e, Kt, info = sl_.zustand(X)
            d = sl_.dofs
            f_int[d] += f_e
            r, c = np.meshgrid(d, d, indexing="ij")
            rows.append(r.ravel())
            cols.append(c.ravel())
            vals.append(np.asarray(Kt, float).ravel())
            fl12 = np.zeros(12)
            fl12[0] = -float(info.get("H", 0.0))
            fl12[6] = float(info.get("Tmax", 0.0))
            zust[sl_.i] = (fl12, float(info.get("Tmax", 0.0)))
        for st in staebe:
            fl, T, kg, N, L = st.zustand(X, R)
            zust[st.i] = (fl, N)
            f_e, Ke = st.knoten(R, T.T @ (fl if st.f_anf is None else fl - st.f_anf),
                                T.T @ (st.kl + kg) @ T)
            d = st.dofs
            f_int[d] += f_e
            r, c = np.meshgrid(d, d, indexing="ij")
            rows.append(r.ravel())
            cols.append(c.ravel())
            vals.append(Ke.ravel())
        K = sparse.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                              shape=(ndof, ndof)).tocsr()
        dges = gesamtvektor()
        if len(feder_idx):
            f_int[feder_idx] += feder_k * dges[feder_idx]
            K = K + sparse.coo_matrix((feder_k, (feder_idx, feder_idx)), shape=(ndof, ndof)).tocsr()
        if Kk is not None:
            f_int += Kk @ dges
            K = K + Kk
        return f_int, K, zust

    # Freiheitsgrade ohne Steifigkeit (Fachwerkknoten, lose Knoten) festhalten
    _f0, K0, _z = aufbau()
    diag = np.abs(K0.diagonal())
    ref = diag.max() if diag.size and diag.max() > 0 else 1.0
    # automatisch gehalten: ohne Steifigkeit und kein Lager - was dort
    # ankommt, traegt kein Bauteil (solver.auto_gehalten_abtrennen, 14.10.2026)
    auto = (diag < ref * 1e-12) & ~fixed
    fixed |= diag < ref * 1e-12
    fi = np.where(~fixed)[0]
    if not len(fi):
        raise ValueError("Kein freier Freiheitsgrad")

    def ergebnis(zust, F_ges, f_int):
        res = Results(name=name, kind="combination", model=model)
        res.u = gesamtvektor().reshape(-1, NDOF).copy()
        Rk = f_int - F_ges
        Rk[fi] = 0.0
        res.reactions = Rk.reshape(-1, NDOF)
        for st in staebe:
            fl, _N = zust[st.i]
            res.beam_end[st.i] = fl - st.f0
            if st.i in q:
                res.beam_q[st.i] = np.asarray(q[st.i], float)
        for sl_ in seile:
            fl, _N = zust.get(sl_.i, (np.zeros(12), 0.0))
            res.beam_end[sl_.i] = fl
        if aktiv is not None:
            res.info["inaktiv"] = [i for i in range(ne) if not aktiv[i]]
            for i in res.info["inaktiv"]:
                res.beam_end[i] = np.zeros(12)
        return res

    # Theorie I. Ordnung als Bezug (u_max_I)
    try:
        lu0 = splu(K0[fi][:, fi].tocsc())
        u1 = np.zeros(ndof)
        u1[fi] = lu0.solve(F_ref_voll[fi])
        info.u_max_I = float(np.abs(u1[:, ].reshape(-1, NDOF)[:, :3]).max())
    except Exception as ex:                    # noqa: BLE001
        raise ValueError(f"Gleichungssystem singulär: {ex}") from ex

    lastnorm = float(np.linalg.norm(F_ref[fi])) or 1.0
    F_imp = np.zeros(ndof)
    zust = _z
    f_int = _f0
    F_ges = np.zeros(ndof)
    gesamt_it = 0
    for schritt in range(1, schritte + 1):
        lam = schritt / schritte
        konv = math.inf
        for it in range(1, max_iter + 1):
            f_int, K, zust = aufbau()
            if imperfektionen:
                from .theorie2 import ersatzlasten_schiefstellung, ersatzlasten_vorkruemmung
                res_t = ergebnis(zust, np.zeros(ndof), f_int)
                Fs, s_info = ersatzlasten_schiefstellung(model, res_t, richtung)
                Fv, v_info = ersatzlasten_vorkruemmung(model, res_t, elastisch, alle=alle_vorkruemmungen)
                F_imp = Fs + Fv
                info.schiefstellung, info.vorkruemmung = s_info, v_info
            F_stufe = stufenlast(F_ref, F_S, lam)
            F_ges = F_stufe + F_imp
            # Stablasten an Staeben mit Versatz: ueber den mitgedrehten Arm
            # (Verfahrensstand 41); ohne solche Staebe leer, alles wie bisher
            arm_k = [x for st in staebe_arm_last for x in st.arm_last(R, lam)]
            if arm_k:
                F_ges = F_ges.copy()
                ra, ca, va = [], [], []
                for n_, dM, dK in arm_k:
                    F_ges[NDOF * n_ + 3:NDOF * n_ + 6] += dM
                    dd_ = np.arange(NDOF * n_ + 3, NDOF * n_ + 6)
                    rr_, cc_ = np.meshgrid(dd_, dd_, indexing="ij")
                    ra.append(rr_.ravel())
                    ca.append(cc_.ravel())
                    va.append(-dK.ravel())
                K = K + sparse.coo_matrix((np.concatenate(va), (np.concatenate(ra), np.concatenate(ca))),
                                          shape=(ndof, ndof)).tocsr()
            r = F_ges - f_int
            # bezogen auf die Last der Stufe - mit voller Temperatur oder
            # Vorspannung ist das nicht mehr lam * |F|; die Anfangsdehnung der
            # Staebe zaehlt dabei mit wie bis zum 13.10.2026 (als Knotenlast)
            if F_anf is not None:
                bezug = float(np.linalg.norm((F_anf + F_stufe)[fi])) or 1.0
            else:
                bezug = (lam * lastnorm) if F_S is None else (float(np.linalg.norm(F_stufe[fi])) or 1.0)
            konv = float(np.linalg.norm(r[fi])) / bezug
            gesamt_it += 1
            if konv < tol:
                break
            try:
                dd = splu(K[fi][:, fi].tocsc()).solve(r[fi])
            except Exception as ex:            # noqa: BLE001
                info.fehler = f"Laststufe {schritt}: Gleichungssystem singulär ({ex})"
                break
            delta = np.zeros(ndof)
            delta[fi] = dd
            delta = delta.reshape(-1, NDOF)
            u += delta[:, :3]
            for n in range(nn):
                dth = delta[n, 3:]
                if np.any(dth):
                    R[n] = rot_exp(dth) @ R[n]
        else:
            info.hinweise.append(
                f"Laststufe {schritt}: nach {max_iter} Iterationen nicht konvergiert "
                f"(Residuum {konv * 100:.3g} % der Last) - mehr Laststufen wählen")
            info.fehler = info.fehler or "keine Konvergenz"
        info.konvergenz = konv
        if info.fehler:
            break
        if progress:
            progress(f"{name}: Laststufe {schritt}/{schritte} ({it} Iterationen)")
    info.schritte = schritte
    info.iterationen = gesamt_it
    info.gerechnet = not info.fehler
    f_int, K, zust = aufbau()
    res = ergebnis(zust, F_ges, f_int)
    from .solver import auto_gehalten_abtrennen
    auto_gehalten_abtrennen(model, auto, res, F_ges, aktiv, progress)
    info.u_max_III = float(np.abs(res.u[:, :3]).max())
    info.drehung_max = float(np.linalg.norm(res.u[:, 3:], axis=1).max())
    if info.u_max_I > 0:
        info.zuwachs = info.u_max_III / info.u_max_I - 1.0
    res.info.update({"theorie": "III. Ordnung", "schritte": schritte,
                     "iterationen": gesamt_it, "konvergenz": info.konvergenz,
                     "factors": dict(factors), "time": time.time() - t0,
                     "ndof": ndof, "nfree": len(fi), "solver": "SuperLU"})
    if info.fehler:
        res.info["fehler"] = info.fehler
    # Zug-/Druckstaebe: Theorie III. Ordnung iteriert den Ausfall nicht (das
    # Seil wird als Kettenlinie schlaff) - ein Zugstab mit Druck steht mit
    # Namen und Kraft im Ergebnis (13.10.2026)
    from .solver import zugstaebe_pruefen
    zugstaebe_pruefen(model, res, F_ref_voll, aktiv, progress=progress)
    return res, info


def check_theorie3(model: Model, analysis, combos: list = None, progress=None,
                   systeme: dict = None, schritte: int = None) -> Th3Results:
    """Alle Kombinationen mit theorie = "III" rechnen und die Ergebnisse der
    Berechnung **ersetzen** (nach Theorie III. Ordnung gilt keine Superposition).

    Eine Ergebniskombination (Alternativen, ``factors`` leer) wird wie in
    :func:`theorie2.check_theorie2` je Alternative "EK [k]" gerechnet und nach
    ``analysis.alternativen`` gelegt - nicht mit leeren Faktoren als
    Nullergebnis nach ``analysis.combinations`` (Befund FE12, 22.09.2026)."""
    from .model import GRUNDSTELLUNG
    from .solver import alternativen_der_kombination
    from .theorie2 import _alternative_ablegen
    ds = model.design
    out = Th3Results(settings={
        "imperfektionen": bool(getattr(ds, "imperfektionen", True)),
        "plastisch": bool(getattr(ds, "th2_plastisch", False)),
        "schritte": int(schritte or getattr(ds, "th3_schritte", 10) or 10),
        "Norm": "geometrisch nichtlinear, korotational; Imperfektionen DIN EN 1993-1-1, 5.3"})
    names = combos if combos is not None else [
        n for n, c in model.combinations.items() if (getattr(c, "theorie", "") or "").upper() == "III"]
    # (Zeile, Kombination, Faktoren, ist Alternative einer Ergebniskombination)
    auftraege = []
    for n in names:
        c = model.combinations[n]
        if c.ist_umhuellende:
            auftraege += [(name, n, teile, True) for name, teile in alternativen_der_kombination(c)]
        else:
            auftraege.append((n, n, dict(c.factors), False))
    for k, (zeile, n, faktoren, alternative) in enumerate(auftraege):
        combo = model.combinations[n]
        sit = getattr(combo, "situation", "") or GRUNDSTELLUNG
        m_c, aktiv = model, None
        if systeme and sit in systeme:
            m_c, sys_c = systeme[sit]
            aktiv = getattr(sys_c, "aktiv", None)
        if not any(f for f in faktoren.values()):
            # Nichts belastet: kein Nullergebnis als "III. Ordnung" ablegen
            out.kombinationen[zeile] = Th3Info(
                name=zeile, hinweise=["keine Lastfälle mit Faktor ≠ 0 – nichts nach "
                                      "Theorie III. Ordnung zu rechnen"])
            continue
        try:
            res, info = solve_theorie3(m_c, faktoren, zeile, schritte=out.settings["schritte"],
                                       imperfektionen=out.settings["imperfektionen"],
                                       elastisch=not out.settings["plastisch"],
                                       richtung=getattr(ds, "th2_richtung", None),
                                       alle_vorkruemmungen=bool(getattr(ds, "th2_alle_vorkruemmungen", False)),
                                       aktiv=aktiv, progress=progress)
        except ValueError as ex:
            info = Th3Info(name=zeile, fehler=str(ex))
            res = None
        out.kombinationen[zeile] = info
        if res is not None and not info.fehler and analysis is not None:
            res.info["typ"] = combo.typ
            if sit != GRUNDSTELLUNG:
                res.info["situation"] = sit
            if alternative:
                _alternative_ablegen(analysis, zeile, res)
            else:
                analysis.combinations[n] = res
        if progress:
            progress(f"{zeile}: Theorie III. Ordnung ({k + 1}/{len(auftraege)})")
    return out
