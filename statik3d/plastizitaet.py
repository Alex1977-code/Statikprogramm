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
    # (a + b + c) / 3 statt sig[:3].mean(): numpys mean kostet auf drei
    # Zahlen rund 5 µs Aufrufaufwand, bei 1,94 Mio. Aufrufen je
    # Plastizitaetsschritt also ueber 10 s (cProfile 19.09.2026)
    p = (sig[0] + sig[1] + sig[2]) / 3.0
    s = sig - p * _EINS
    return float(np.sqrt(1.5 * (s[0] ** 2 + s[1] ** 2 + s[2] ** 2) + 3.0 * (s[3] ** 2 + s[4] ** 2 + s[5] ** 2)))


def rueckfuehrung(sig_trial, fy: float, H: float, G: float, eps_p_eq: float = 0.0) -> tuple:
    """Radial return. Rueckgabe (σ, Δε_p (Voigt, Ingenieurgleitungen), Δγ)."""
    sig = np.asarray(sig_trial, float)
    p = (sig[0] + sig[1] + sig[2]) / 3.0
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


def _stapel(model, elemente: list, typ: str) -> dict:
    """Geometrie- und Werkstoffdaten eines Stapels gleichen Elementtyps.

    Haengt nur am Netz und an den Werkstoffen, nicht an der Verschiebung -
    darum wird es am Modell gemerkt und ueber die Schritte einer Rechnung
    wiederverwendet (am Drehlager kostet der Aufbau rund 5,7 s, jeder weitere
    Schritt danach 1,4 s statt 51,5 s).

    ``dN`` sind die Ableitungen am **Auswertepunkt** (der Mitte) - dort misst
    die Plastizitaet die Spannung. ``lasten`` traegt je Gausspunkt die
    Ableitungen und das Integrationsgewicht w*|det J|; daraus entstehen die
    plastischen Knotenlasten f = ∫ Bᵀ σ0 dV. Bei tet4 ist das ein Punkt und
    das Gewicht gleich dem Volumen, bei hex8 sind es acht.
    """
    from . import assemble as asm
    from .elements import solid as sl
    idx = np.asarray(elemente, dtype=np.int64)
    schluessel = (typ, len(model.elements), len(idx), int(idx[0]), int(idx[-1]))
    cache = getattr(model, "_plast_stapel", None)
    if cache is None:
        cache = model._plast_stapel = {}
    alt = cache.get(typ)
    if alt is not None and alt.get("schluessel") == schluessel:
        return alt
    k = sl._KNOTENZAHL[typ]
    knoten = np.asarray([model.elements[i].nodes[:k] for i in idx], dtype=np.int64)   # (n,k)
    X = np.asarray(model.nodes, float)[knoten]                                        # (n,k,3)
    fn, GP, W = sl._ISO[typ]

    def gradienten(r, s_, t):
        """dN (n,k,3) und |det J| (n,) an einem lokalen Punkt, ueber den Stapel."""
        _N, dNr = fn(r, s_, t)                       # (k,3), fuer alle Elemente gleich
        J = np.einsum("ki,nkj->nij", dNr, X)         # (n,3,3)
        det = np.abs(np.linalg.det(J))
        # dN = (J^-1 dNr^T)^T, blockweise geloest statt invertiert
        rechte = np.broadcast_to(dNr.T, (len(idx), 3, k))
        return np.linalg.solve(J, rechte).transpose(0, 2, 1), det

    r0, s0, t0 = sl.AUSWERTEPUNKTE[typ][0]
    dN, _det0 = gradienten(r0, s0, t0)
    lasten = []
    for (r, s_, t), w in zip(GP, W):
        dNg, detg = gradienten(r, s_, t)
        lasten.append((dNg, float(w) * detg))
    # Werkstoffwerte je Element als Felder
    n = len(idx)
    E = np.empty(n); nu = np.empty(n)
    fy = np.zeros(n); hat_fy = np.zeros(n, bool)
    ohne: set = set()
    for a, i in enumerate(idx):
        mat = model.materials[model.elements[i].mat]
        E[a], nu[a] = float(mat.E), float(mat.nu)
        f = getattr(mat, "fy", None)
        if f:
            fy[a], hat_fy[a] = float(f), True
        else:
            ohne.add(model.elements[i].mat)
    dofs = np.empty((n, 3 * k), dtype=np.int64)
    for a in range(k):
        for rr in range(3):
            dofs[:, 3 * a + rr] = asm.NDOF * knoten[:, a] + rr
    daten = {"schluessel": schluessel, "typ": typ, "idx": idx, "k": k, "dN": dN,
             "lasten": lasten, "dofs": dofs, "E": E, "nu": nu, "fy": fy,
             "hat_fy": hat_fy, "ohne_fy": ohne,
             "lam": E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu)), "mu": E / (2.0 * (1.0 + nu))}
    cache[typ] = daten
    return daten


def _dehnung(dN, ue):
    """Voigt-Dehnungen (n,6) aus den Ableitungen (n,k,3) und den
    Knotenverschiebungen (n,k,3) - xx, yy, zz, xy, yz, zx mit
    Ingenieurgleitungen, wie in elements.solid._B_from_grad."""
    exx = np.einsum("nka,nka->n", dN[:, :, 0:1], ue[:, :, 0:1])
    eyy = np.einsum("nka,nka->n", dN[:, :, 1:2], ue[:, :, 1:2])
    ezz = np.einsum("nka,nka->n", dN[:, :, 2:3], ue[:, :, 2:3])
    gxy = (np.einsum("nk,nk->n", dN[:, :, 1], ue[:, :, 0])
           + np.einsum("nk,nk->n", dN[:, :, 0], ue[:, :, 1]))
    gyz = (np.einsum("nk,nk->n", dN[:, :, 2], ue[:, :, 1])
           + np.einsum("nk,nk->n", dN[:, :, 1], ue[:, :, 2]))
    gzx = (np.einsum("nk,nk->n", dN[:, :, 2], ue[:, :, 0])
           + np.einsum("nk,nk->n", dN[:, :, 0], ue[:, :, 2]))
    return np.stack([exx, eyy, ezz, gxy, gyz, gzx], axis=1)


def _spannung(lam, mu2, eps):
    """sigma = D eps (n,6), ohne die Werkstoffmatrix zu bauen."""
    spur = lam * (eps[:, 0] + eps[:, 1] + eps[:, 2])
    sig = np.empty_like(eps)
    sig[:, 0] = spur + 2.0 * mu2 * eps[:, 0]
    sig[:, 1] = spur + 2.0 * mu2 * eps[:, 1]
    sig[:, 2] = spur + 2.0 * mu2 * eps[:, 2]
    sig[:, 3] = mu2 * eps[:, 3]
    sig[:, 4] = mu2 * eps[:, 4]
    sig[:, 5] = mu2 * eps[:, 5]
    return sig


def _schritt_block(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list,
                   typ: str, log: list = None) -> tuple:
    """Ein Schritt fuer einen Stapel gleichen Typs - dieselbe Rechnung wie
    :func:`_schritt_schleife`, nur als Feldoperationen."""
    d = _stapel(model, elemente, typ)
    idx, dN, dofs, k = d["idx"], d["dN"], d["dofs"], d["k"]
    lam, mu2 = d["lam"], d["mu"]
    n = len(idx)
    ue = np.asarray(u, float)[dofs].reshape(n, k, 3)
    sig = _spannung(lam, mu2, _dehnung(dN, ue))
    # Bisherige plastische Dehnung und Versuchsspannung sigma - D eps_p
    eps_p = np.zeros((n, 6))
    eps_p_eq = np.zeros(n)
    hatte = np.zeros(n, bool)
    if zustand.eps_p:
        platz = {int(i): a for a, i in enumerate(idx)}
        for i, v in zustand.eps_p.items():
            a = platz.get(int(i))
            if a is not None:
                eps_p[a] = v
                eps_p_eq[a] = zustand.eps_p_eq.get(i, 0.0)
                hatte[a] = True
        sig -= _spannung(lam, mu2, eps_p)
    # Rueckfuehrung (von Mises, radial return) ueber den Stapel
    p_hyd = (sig[:, 0] + sig[:, 1] + sig[:, 2]) / 3.0
    dev = sig.copy()
    dev[:, 0] -= p_hyd
    dev[:, 1] -= p_hyd
    dev[:, 2] -= p_hyd
    q = np.sqrt(1.5 * (dev[:, 0] ** 2 + dev[:, 1] ** 2 + dev[:, 2] ** 2)
                + 3.0 * (dev[:, 3] ** 2 + dev[:, 4] ** 2 + dev[:, 5] ** 2))
    r = max(0.0, min(float(einst.verfestigung), 0.999))
    H = d["E"] * r / (1.0 - r)
    G = d["E"] / (2.0 * (1.0 + d["nu"]))
    f = q - (d["fy"] + H * eps_p_eq)
    fliesst = d["hat_fy"] & (f > 0.0) & (q > 0.0)
    dgamma = np.zeros(n)
    np.divide(f, 3.0 * G + H, out=dgamma, where=fliesst)
    q_sicher = np.where(q > 0.0, q, 1.0)
    richtung = 1.5 * dev / q_sicher[:, None]
    eps_p_neu = eps_p + dgamma[:, None] * richtung * _SCHUB[None, :]
    sig_neu = sig - 2.0 * G[:, None] * dgamma[:, None] * richtung
    p_neu = (sig_neu[:, 0] + sig_neu[:, 1] + sig_neu[:, 2]) / 3.0
    q_neu = np.sqrt(1.5 * ((sig_neu[:, 0] - p_neu) ** 2 + (sig_neu[:, 1] - p_neu) ** 2
                           + (sig_neu[:, 2] - p_neu) ** 2)
                    + 3.0 * (sig_neu[:, 3] ** 2 + sig_neu[:, 4] ** 2 + sig_neu[:, 5] ** 2))
    # Neuer Zustand und plastische Knotenlasten - nur fuer Elemente, die
    # fliessen oder schon eine Dehnung tragen
    neu = zustand.kopie()
    traegt = fliesst | hatte
    F_p = np.zeros(model.ndof)
    stellen = np.flatnonzero(traegt)
    if stellen.size:
        for a in stellen:
            neu.eps_p[int(idx[a])] = eps_p_neu[a]
            neu.eps_p_eq[int(idx[a])] = float(eps_p_eq[a] + dgamma[a])
        s0 = _spannung(lam[stellen], mu2[stellen], eps_p_neu[stellen])
        fe = np.zeros((len(stellen), k, 3))
        for dNg, gew in d["lasten"]:
            g = dNg[stellen]                                    # (m,k,3)
            w = gew[stellen][:, None]                           # (m,1)
            fe[:, :, 0] += w * (g[:, :, 0] * s0[:, 0, None] + g[:, :, 1] * s0[:, 3, None]
                                + g[:, :, 2] * s0[:, 5, None])
            fe[:, :, 1] += w * (g[:, :, 1] * s0[:, 1, None] + g[:, :, 0] * s0[:, 3, None]
                                + g[:, :, 2] * s0[:, 4, None])
            fe[:, :, 2] += w * (g[:, :, 2] * s0[:, 2, None] + g[:, :, 1] * s0[:, 4, None]
                                + g[:, :, 0] * s0[:, 5, None])
        np.add.at(F_p, dofs[stellen].ravel(), fe.reshape(-1))
    if d["ohne_fy"] and log is not None:
        log.append("Plastizität: Werkstoffe ohne Streckgrenze bleiben elastisch - "
                   + ", ".join(sorted(d["ohne_fy"])))
    # q_max zaehlt nur Werkstoffe mit Streckgrenze: die Schleife ueberspringt
    # die uebrigen ganz (19.09.2026, vom Vergleichstest gefunden)
    q_max = float(q_neu[d["hat_fy"]].max()) if (n and d["hat_fy"].any()) else 0.0
    return F_p, neu, {"fliessend": int(fliesst.sum()), "q_max": q_max}


def schritt(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list, log: list = None) -> tuple:
    """Ein Schritt der Anfangsdehnungs-Iteration: aus u die Versuchsspannung
    D(ε − eps_p) je Element, Rueckfuehrung, neue eps_p, plastische
    Knotenlasten F_p = Σ ∫ Bᵀ D eps_p dV. Rueckgabe (F_p, Zustand, info)."""
    from . import assemble as asm
    from .elements import solid as sl
    # Blockweise: die Schleife kostet am Drehlager 80 µs je Element, und das
    # bei null fliessenden - es ist der Aufrufaufwand, nicht die Physik
    # (19.09.2026). Gerechnet wird je Elementtyp ein Stapel; die Schleife
    # bleibt fuer unbekannte Typen und als Referenz des Vergleichstests.
    if not elemente:
        return np.zeros(model.ndof), zustand.kopie(), {"fliessend": 0, "q_max": 0.0}
    from .elements import solid as sl
    je_typ: dict = {}
    for i in elemente:
        je_typ.setdefault(model.elements[i].typ, []).append(i)
    if any(t not in sl._ISO for t in je_typ):
        return _schritt_schleife(model, u, zustand, einst, elemente, log)
    if len(je_typ) == 1:
        typ, liste = next(iter(je_typ.items()))
        return _schritt_block(model, u, zustand, einst, liste, typ, log)
    # Gemischtes Netz: je Typ ein Stapel, die Ergebnisse zusammenlegen
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fliesst, q_max = 0, 0.0
    for typ, liste in je_typ.items():
        Fb, zb, ib = _schritt_block(model, u, zustand, einst, liste, typ, log)
        F_p += Fb
        for i in liste:
            if i in zb.eps_p:
                neu.eps_p[i] = zb.eps_p[i]
                neu.eps_p_eq[i] = zb.eps_p_eq[i]
        n_fliesst += ib["fliessend"]
        q_max = max(q_max, ib["q_max"])
    return F_p, neu, {"fliessend": n_fliesst, "q_max": q_max}


def _schritt_schleife(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list,
                      log: list = None) -> tuple:
    """Derselbe Schritt, Element fuer Element - die Referenz fuer alles, was
    nicht tet4 ist, und der Vergleich im Test (tests/test_plastizitaet.py)."""
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
