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

Grenzen: nur Stab- und Fachwerkelemente (keine Schalen, Volumen), kein
Kontakt, keine Zwangsverformungen; kleine Dehnungen (linear-elastisch).
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
        kl, T3, T, L = asm.beam_local(model, e)
        fa = None if f_anf is None or not np.any(f_anf) else np.asarray(f_anf, float)
        # die Anfangsdehnung wie in asm.stablasten_einbauen: Federgelenke, dann
        # Gelenke kondensiert
        if getattr(e, "hinge_springs", None):
            kl, fa_, _rec = asm.hinge_springs(kl, np.zeros(12) if fa is None else fa, e.hinge_springs)
            fa = None if fa is None else fa_
        if e.hinges:
            kl, fa_, _c = asm.condense(kl, np.zeros(12) if fa is None else fa, e.hinges)
            fa = None if fa is None else fa_
        self.kl = kl
        self.f_anf = fa
        self.E0T = T3.T                   # Spalten: Ausgangsachsen ex, ey, ez
        self.L0 = L
        self.f0 = np.asarray(feq.get(i, np.zeros(12)), float)
        self.dofs = asm.element_dofs(e)

    def zustand(self, X: np.ndarray, R: np.ndarray):
        """(f_l, T, k_g, N, L) im mitgehenden System der aktuellen Lage; f_l
        ist der elastische Anteil k_l d_l, N die Normalkraft mit der
        Anfangsdehnung."""
        n1, n2 = self.nodes
        d = X[n2] - X[n1]
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
        T = bm.transform_matrix(E.T)
        return fl, T, kg, N, L


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
def solve_theorie3(model: Model, factors: dict, name: str, schritte: int = 10,
                   max_iter: int = 30, tol: float = 1e-6, imperfektionen: bool = None,
                   elastisch: bool = True, richtung=None, alle_vorkruemmungen: bool = False,
                   aktiv=None, progress=None):
    """Einen Lastfall oder eine Kombination (``factors``) nach Theorie III.
    Ordnung rechnen. Rueckgabe (Results, Th3Info)."""
    from .solver import case_loads, case_prescribed, Results
    from . import supports as sup
    t0 = time.time()
    info = Th3Info(name=name)
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
            Ke = T.T @ (st.kl + kg) @ T
            d = st.dofs
            f_int[d] += T.T @ (fl if st.f_anf is None else fl - st.f_anf)
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
