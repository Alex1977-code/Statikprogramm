"""Plastizitaet der Volumenelemente (17.09.2026): von Mises mit isotroper
linearer Verfestigung, gerechnet als **Anfangsdehnungs-Iteration**.

Warum so: der Loeser dieses Programms ist linear-elastisch plus Kontakt
(Aktivmengen-Iteration mit fester Faktorisierung). Ein Fliessen laesst sich
darauf setzen, ohne die Steifigkeitsmatrix anzufassen: die plastische
Dehnung eps_p jedes Elements ist eine Anfangsdehnung, genau wie eine
Temperaturdehnung oder die Vorspannung. Ihre aequivalenten Knotenlasten
F_p = ∫ Bᵀ D eps_p dV kommen zur aeusseren Last, die Spannung ist
σ = D (ε − eps_p). Die Iteration

    u_k = K⁻¹ (F + F_p(eps_p,k-1)),   eps_p,k = Rueckfuehrung(D ε(u_k) − D eps_p,k-1)

ist das Anfangssteifigkeitsverfahren: jeder Schritt ist eine lineare
Loesung (mit Kontakt eine Kontakt-Iteration, warm gestartet), die
Faktorisierung bleibt. Es konvergiert linear - langsam bei grossflaechigem
Fliessen, schnell bei oertlichem (Bohrungskanten, Lochleibung), und dafuer
ist es gedacht. Laststufen halten die Rueckfuehrung auf dem Pfad.

Rueckfuehrung (radial return, von Mises, isotrope Verfestigung H):

    s = dev σ_trial,  q = sqrt(3/2 s:s),  f = q − (fy + H ε_p,eq)
    f > 0:  Δγ = f / (3G + H),  n = 3/2 s / q,  σ = σ_trial − 2G Δγ n,
            Δε_p = Δγ n (Ingenieurgleitungen: doppelte Schubanteile),  Δε_p,eq = Δγ

Uniaxial: σ = fy + H ε_p und ε = σ/E + ε_p - die lineare Verfestigung mit der
Tangente E_t = E H / (E + H). Die Verfestigung wird als E_t/E angegeben.

Voigt-Reihenfolge wie in elements.solid: xx, yy, zz, xy, yz, xz; Dehnungen
mit Ingenieurgleitungen.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Voigt-Hilfen
_EINS = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
_SCHUB = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])


@dataclass
class Plastizitaet:
    """Einstellungen (am Modell): Fliessen rechnen, Verfestigung E_t/E,
    Laststufen, Iterationen je Stufe, Toleranz (Aenderung der plastischen
    Knotenlasten gegen die aeussere Last)."""
    an: bool = False
    verfestigung: float = 0.01
    laststufen: int = 3
    iterationen: int = 25
    toleranz: float = 1e-3

    def H(self, E: float) -> float:
        """Verfestigungsmodul H aus der Tangente E_t = r E: H = E r / (1 - r)."""
        r = max(0.0, min(float(self.verfestigung), 0.999))
        return float(E) * r / (1.0 - r)


def vergleichsspannung(sig) -> float:
    sig = np.asarray(sig, float)
    p = sig[:3].mean()
    s = sig - p * _EINS
    return float(np.sqrt(1.5 * (s[0] ** 2 + s[1] ** 2 + s[2] ** 2) + 3.0 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2)))


def rueckfuehrung(sig_trial, fy: float, H: float, G: float, eps_p_eq: float = 0.0) -> tuple:
    """Radial return. Rueckgabe (σ, Δε_p (Voigt, Ingenieurgleitungen), Δγ)."""
    sig = np.asarray(sig_trial, float)
    p = sig[:3].mean()
    s = sig - p * _EINS
    q = vergleichsspannung(sig)
    f = q - (float(fy) + float(H) * float(eps_p_eq))
    if f <= 0.0 or q <= 0.0:
        return sig.copy(), np.zeros(6), 0.0
    dgamma = f / (3.0 * float(G) + float(H))
    n = 1.5 * s / q                                   # Tensorkomponenten
    sig_neu = sig - 2.0 * float(G) * dgamma * n
    d_eps_p = dgamma * n * _SCHUB                     # Ingenieurgleitungen
    return sig_neu, d_eps_p, float(dgamma)


class Zustand:
    """Plastische Dehnungen je Element: {i: (eps_p (6), eps_p_eq)}."""

    def __init__(self):
        self.eps_p: dict = {}
        self.eps_p_eq: dict = {}

    def kopie(self) -> "Zustand":
        z = Zustand()
        z.eps_p = {i: v.copy() for i, v in self.eps_p.items()}
        z.eps_p_eq = dict(self.eps_p_eq)
        return z

    def fliessend(self) -> list:
        return [i for i, v in self.eps_p_eq.items() if v > 0]


def _solid_elemente(model, aktiv=None) -> list:
    from . import assemble as asm
    idx = asm.aktive_indizes(model, aktiv)
    return [i for i in idx if model.elements[i].typ in asm.SOLID_TYPES]


def schritt(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list, log: list = None) -> tuple:
    """Ein Schritt der Anfangsdehnungs-Iteration: aus u die Versuchsspannung
    D(ε − eps_p) je Element, Rueckfuehrung, neue eps_p, plastische
    Knotenlasten F_p = Σ ∫ Bᵀ D eps_p dV. Rueckgabe (F_p, Zustand, info)."""
    from . import assemble as asm
    from .elements import solid as sl
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fliesst = 0
    q_max = 0.0
    ohne_fy: set = set()
    for i in elemente:
        e = model.elements[i]
        mat = model.materials[e.mat]
        fy = getattr(mat, "fy", None)
        if not fy:
            ohne_fy.add(e.mat)
            continue
        E, nu = float(mat.E), float(mat.nu)
        G = E / (2.0 * (1.0 + nu))
        H = einst.H(E)
        X = model.nodes[e.nodes]
        ue = u[asm.element_dofs(e, model)]
        D = sl.D_matrix(E, nu)
        mitte = sl.AUSWERTEPUNKTE[e.typ][0]
        sig_el = np.asarray(sl.stress_points(e.typ, X, E, nu, ue, punkte=[mitte])[0], float)
        eps_p_alt = zustand.eps_p.get(i, np.zeros(6))
        sig_trial = sig_el - D @ eps_p_alt
        sig_neu, d_eps_p, dgamma = rueckfuehrung(sig_trial, float(fy), H, G, zustand.eps_p_eq.get(i, 0.0))
        q_max = max(q_max, vergleichsspannung(sig_neu))
        if dgamma > 0 or i in neu.eps_p:
            eps_p_neu = eps_p_alt + d_eps_p
            neu.eps_p[i] = eps_p_neu
            neu.eps_p_eq[i] = zustand.eps_p_eq.get(i, 0.0) + dgamma
            if dgamma > 0:
                n_fliesst += 1
            fe = asm.solid_initial_stress_loads(model, e, D @ eps_p_neu)
            d = asm.element_dofs(e, model)
            np.add.at(F_p, d, fe)
    if ohne_fy and log is not None:
        log.append("Plastizität: Werkstoffe ohne Streckgrenze bleiben elastisch - " + ", ".join(sorted(ohne_fy)))
    return F_p, neu, {"fliessend": n_fliesst, "q_max": q_max}


def iteration(model, F, loesen, einst: Plastizitaet, aktiv=None, log: list = None, progress=None) -> tuple:
    """Laststufen und Anfangsdehnungs-Iteration. ``loesen(F_ges)`` liefert u
    fuer die Gesamtlast (mit Kontakt: eine Kontakt-Iteration). Rueckgabe
    (u, Zustand, F_p, info) fuer die volle Last."""
    elemente = _solid_elemente(model, aktiv)
    zustand = Zustand()
    F = np.asarray(F, float)
    norm_F = float(np.linalg.norm(F)) or 1.0
    F_p = np.zeros(model.ndof)
    u = None
    info = {"laststufen": int(max(1, einst.laststufen)), "iterationen": 0, "konvergiert": True,
            "fliessend": 0, "eps_p_max": 0.0, "verlauf": []}
    if not elemente:
        u = loesen(F)
        return u, zustand, F_p, info
    stufen = int(max(1, einst.laststufen))
    for k in range(1, stufen + 1):
        lam = k / stufen
        F_k = lam * F
        # Aitken-Relaxation der Fixpunktfolge F_p: das Anfangssteifigkeits-
        # verfahren zieht sich mit dem Faktor E_t/E zusammen - bei 2 %
        # Verfestigung 0,98 je Schritt, 60 Schritte brachten 65 % des Wegs.
        # Aitken schaetzt den Faktor aus zwei Residuen und springt an den
        # Fixpunkt (Zugversuch: 6 statt > 60 Schritte); zwischen 0,5 und 200
        # begrenzt, je Laststufe neu begonnen.
        omega, r_alt = 1.0, None
        for it in range(1, int(max(1, einst.iterationen)) + 1):
            u = loesen(F_k + F_p)
            F_p_neu, zustand_neu, s_info = schritt(model, u, zustand, einst, elemente, log)
            r = F_p_neu - F_p
            diff = float(np.linalg.norm(r)) / norm_F
            info["iterationen"] += 1
            info["verlauf"].append((k, it, diff, s_info["fliessend"]))
            if progress is not None:
                progress(f"Plastizität: Laststufe {k}/{stufen}, Schritt {it}: {s_info['fliessend']} Elemente "
                         f"fließen, Änderung {diff:.2e}")
            if diff <= float(einst.toleranz):
                F_p, zustand = F_p_neu, zustand_neu
                break
            if r_alt is not None:
                d = r - r_alt
                dd = float(d @ d)
                if dd > 0:
                    omega = float(min(200.0, max(0.5, -omega * float(r_alt @ d) / dd)))
            F_p = F_p + omega * r
            zustand = zustand_neu
            r_alt = r
        else:
            info["konvergiert"] = False
            if log is not None:
                log.append(f"Plastizität: Laststufe {k} nach {einst.iterationen} Schritten nicht konvergiert "
                           f"(Änderung {diff:.2e} > {einst.toleranz:g})")
    # Die letzte Loesung gehoert zum letzten Zustand
    u = loesen(F + F_p)
    info["fliessend"] = len(zustand.fliessend())
    info["eps_p_max"] = float(max(zustand.eps_p_eq.values())) if zustand.eps_p_eq else 0.0
    if log is not None:
        log.append(f"Plastizität: {info['fliessend']} Elemente fließen, ε_p,eq max {info['eps_p_max'] * 100:.3f} %, "
                   f"{info['iterationen']} Schritte in {stufen} Laststufen"
                   + ("" if info["konvergiert"] else " - nicht konvergiert"))
    return u, zustand, F_p, info


def sigma0_je_element(model, zustand: Zustand) -> dict:
    """{Element: D eps_p} - die Anfangsspannung fuer den Spannungsnachlauf
    (σ = D ε − D eps_p), im Schluessel "sigma0" von temp."""
    from .elements import solid as sl
    aus = {}
    for i, eps_p in zustand.eps_p.items():
        e = model.elements[i]
        mat = model.materials[e.mat]
        aus[i] = sl.D_matrix(float(mat.E), float(mat.nu)) @ eps_p
    return aus
