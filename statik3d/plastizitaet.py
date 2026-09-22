"""Plastizitaet der Volumenelemente (17.09.2026): von Mises mit isotroper
linearer Verfestigung. Zwei Wege - die **Anfangsdehnungs-Iteration** bei
fester Steifigkeit (unten) und, seit dem 20.09.2026 als Vorgabe, **Newton
mit der konsistenten elastoplastischen Tangente** (ganz unten).

Der alte Weg zuerst, denn der zweite setzt darauf auf.

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

**Zweiter Weg - konsistente Tangente (20.09.2026):** die Anfangsdehnungs-
Iteration zieht sich mit dem Faktor 1 − E_t/E zusammen. Bei 1 % Verfestigung
sind das 0,99 je Schritt (rund 700 Schritte fuer 1e-3); die Aitken-
Beschleunigung ueberschiesst dort und bleibt bei einer Aenderung von 1e-1
stehen - der Zugversuch lag bei 1,5 fy um 28,5 % daneben. Darum wird die
Steifigkeit nun voreingestellt je Schritt neu aufgestellt und faktorisiert,
mit der zur Rueckfuehrung **konsistenten** elastoplastischen Tangente (Simo
& Hughes, Box 3.2), nicht mit der kontinuierlichen:

    D_ep = K δ⊗δ + 2G θ (I − δ⊗δ/3) − 2G θ̄ N⊗N
    θ = 1 − 3G Δγ / q_trial,  θ̄ = 1/(1 + H/3G) − (1 − θ),  N = s_trial/‖s_trial‖

Das ist die Ableitung der Rueckfuehrung nach der Gesamtdehnung. Die Folge
ist damit ein Newton-Verfahren und haengt nicht mehr an der Verfestigung:
der Zugversuch braucht bei 1 % zwei bis vier Schritte je Laststufe statt
"nicht konvergiert". Bezahlt wird es mit **einer Faktorisierung je Schritt**
statt einer je Rechnung - siehe :func:`iteration`.

ΔK ist seit dem Zustand je Gausspunkt (20.09.2026) fuer **jeden**
Volumentyp die exakte Ableitung −∂F_p/∂u: gemessen am 22.09.2026 gegen
zentrale Differenzen auf 0,8e-9 bis 1,7e-9 (tet4, hex8 mit Moden, tet10,
hex20, pent6, pent15, pyr5 - die Groesse des Differenzenfehlers), und der
Newton konvergiert quadratisch (Kragtraeger unter 1,20 M_el: hex8 1,8e-3 ->
2,5e-6 -> 2,3e-12, tet10 2,1e-3 -> 2,4e-6 -> 8,5e-12). Die fruehere Angabe
"bei tet10 bis 53 %, bei hex8 rund 1 % Abweichung" stammte aus der Zeit, als
eps_p an der Elementmitte hing, und galt seitdem nicht mehr
(tests/test_plastizitaet.py, test_tangente_exakt_fuer_jeden_typ und
test_newton_konvergiert_quadratisch).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Voigt-Hilfen
_EINS = np.array([1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
_SCHUB = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 2.0])

#: Deviatorischer Projektor I − δ⊗δ/3 als Voigt-Matrix. In dieser Schreibweise
#: ist D_AB = C_ijkl ohne Zusatzfaktoren, weil der Faktor 2 aus der Symmetrie
#: des zweiten Indexpaares in der Ingenieurgleitung steckt - darum 1/2 auf den
#: Schubplaetzen (Probe: mit θ = 1 und θ̄ = 0 kommt genau lam*P + diag(2G,2G,2G,G,G,G)
#: heraus, also die Matrix von :func:`_spannung`).
_P_DEV = np.array([
    [2.0 / 3.0, -1.0 / 3.0, -1.0 / 3.0, 0.0, 0.0, 0.0],
    [-1.0 / 3.0, 2.0 / 3.0, -1.0 / 3.0, 0.0, 0.0, 0.0],
    [-1.0 / 3.0, -1.0 / 3.0, 2.0 / 3.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.5, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.5, 0.0],
    [0.0, 0.0, 0.0, 0.0, 0.0, 0.5],
])

#: Die beiden Wege durch die Plastizitaet - siehe :func:`iteration`
WEGE = ("tangente", "anfangsdehnung")


@dataclass
class Plastizitaet:
    """Einstellungen (am Modell): Fliessen rechnen, Verfestigung E_t/E,
    Laststufen, Iterationen je Stufe, Toleranz (Aenderung der plastischen
    Knotenlasten gegen die aeussere Last).

    ``verfahren`` waehlt den Weg: ``"tangente"`` ist das Newton-Verfahren mit
    der konsistenten elastoplastischen Tangente (eine Faktorisierung je
    Schritt, dafuer wenige Schritte, unabhaengig von der Verfestigung),
    ``"anfangsdehnung"`` die Anfangsdehnungs-Iteration bei fester Steifigkeit
    (eine Faktorisierung je Rechnung, dafuer linear mit dem Faktor 1 − E_t/E).
    """
    an: bool = False
    verfestigung: float = 0.01
    laststufen: int = 3
    iterationen: int = 25
    toleranz: float = 1e-3
    verfahren: str = "tangente"
    #: Punkte ueber die Dicke des hex8 (Richtung t, im Sweep die Lagen), wenn
    #: Fliessen gerechnet wird: n >= 3 legt n Gauss-Lobatto-Punkte in t (die
    #: aeussersten auf der Oberflaeche), 2 laesst die 2x2x2-Gaussregel. Warum
    #: (Auftrag A2, gemessen 22.09.2026, Kragtraeger 200 x 200 mm unter
    #: 1,20 M_el, Randfaser nach der Momenten-Kruemmungs-Beziehung 236,35
    #: N/mm2 und eps_p 0,0315 %): mit 2x2x2 fliesst eine Lage **nicht** (der
    #: aeusserste Punkt bei 57,7 % der halben Hoehe zeigt 162 N/mm2), zwei
    #: Lagen auch nicht (219); mit fuenf Lobatto-Punkten trifft schon eine
    #: Lage die Randfaser auf -0,20 N/mm2, zwei auf -0,20, vier auf -0,07
    #: (eps_p -15 / -15 / -5 %). Drei Punkte reichen bei einer Lage nicht
    #: (+45 N/mm2: die Regel kennt nur Rand und Mitte und legt das ganze
    #: plastische Moment auf die Randfaser). Fuer Parallelepipede ist die
    #: elastische Steifigkeit mit jeder Regel >= 2 Punkten dieselbe.
    dicke_punkte: int = 5

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


def tangenten_differenz(dev, q, dgamma, G, H):
    """ΔD = D_ep − D_el (n,6,6) fuer fliessende Elemente, konsistent zur
    Rueckfuehrung in :func:`rueckfuehrung`.

    ``dev`` ist der Deviator der **Versuchsspannung** (Tensorkomponenten in
    Voigt-Reihenfolge), ``q`` ihre Vergleichsspannung, ``dgamma`` das Δγ der
    Rueckfuehrung. Mit θ = 1 − 3G Δγ/q und θ̄ = 1/(1 + H/3G) − (1 − θ):

        D_ep − D_el = 2G (θ − 1) (I − δ⊗δ/3) − 2G θ̄ N⊗N

    Der Kugelanteil faellt heraus - Fliessen ist volumentreu, D_ep und D_el
    unterscheiden sich nur deviatorisch. Darum traegt ΔK nur dort Eintraege,
    wo Elemente fliessen, und es bleibt duenn.

    Fuer H > 0 bleibt D_ep positiv definit: der Eigenwert in Richtung N ist
    2G(θ − θ̄) = 2G (H/3G)/(1 + H/3G) > 0, quer dazu 2Gθ = 2G (fy + H ε_p)/q > 0.
    """
    G = np.asarray(G, float)
    H = np.asarray(H, float)
    q = np.asarray(q, float)
    theta_1 = -3.0 * G * np.asarray(dgamma, float) / q          # θ − 1
    quer = 1.0 / (1.0 + H / (3.0 * G)) + theta_1                # θ̄
    N = np.asarray(dev, float) * (np.sqrt(1.5) / q)[:, None]    # s/‖s‖, ‖s‖ = q/√1,5
    dD = (2.0 * G * theta_1)[:, None, None] * _P_DEV[None, :, :]
    dD -= (2.0 * G * quer)[:, None, None] * (N[:, :, None] * N[:, None, :])
    return dD


def _B_stapel(g):
    """Verzerrungsmatrix B (m,6,3k) aus den Ableitungen g (m,k,3) - dieselbe
    Belegung wie elements.solid._B_from_grad, nur ueber einen Stapel."""
    m, k = g.shape[0], g.shape[1]
    B = np.zeros((m, 6, 3 * k))
    B[:, 0, 0::3] = g[:, :, 0]
    B[:, 1, 1::3] = g[:, :, 1]
    B[:, 2, 2::3] = g[:, :, 2]
    B[:, 3, 0::3] = g[:, :, 1]
    B[:, 3, 1::3] = g[:, :, 0]
    B[:, 4, 1::3] = g[:, :, 2]
    B[:, 4, 2::3] = g[:, :, 1]
    B[:, 5, 0::3] = g[:, :, 2]
    B[:, 5, 2::3] = g[:, :, 0]
    return B


def _dk_block(d, fliesst, dev, q, dgamma, G, H, ndof):
    """ΔK = Σ_gp ∫ Bᵀ (D_ep − D_el) B dV der fliessenden **Gausspunkte**.

    Das ist die konsistente Tangente: seit dem 20.09.2026 haengt eps_p an der
    Dehnung **an jedem Gausspunkt** (siehe :class:`Zustand`), also ist

        ∂F_p/∂u = Σ_gp w |J| Bᵀ_gp D (∂eps_p,gp/∂ε_gp) B_gp = −Σ_gp w |J| Bᵀ ΔD B.

    Vorher stand hier die Mittelpunktfassung V Bᵀ_m ΔD B_m, und das war zu
    ihrer Zeit richtig: eps_p hing allein an der Dehnung in der Mitte, F_p
    reagierte auf keine Biegemode, und die Gausspunktfassung war deshalb in
    genau diesen Moden zu weich - am Reibblock (hex8,
    tests.test_plastizitaet.test_kontakt) lief sie mit dem Faktor rund 100 je
    Schritt davon (1,7e0 → 1,0e36 in 19 Schritten), waehrend die
    Mittelpunktfassung in 4 Schritten konvergierte (20.09.2026). Mit dem
    Zustand je Gausspunkt faellt dieser Grund weg: F_p reagiert jetzt auf
    dieselben Moden, die ΔK weicher macht.

    ΔD ist negativ semidefinit und symmetrisch, K + ΔK also positiv definit -
    CHOLMOD im Loeser vertraegt keine unsymmetrische Matrix.

    Gerechnet wird in Bloecken von rund 16 MB je Zwischenfeld (ke, Zeilen,
    Spalten sind alle (m, 3k, 3k)): am Drehlager waeren 646.706 Tetraeder auf
    einmal 745 MB allein fuer die Zeilennummern, bei hex20 (60x60 je Element)
    das Fuenfundzwanzigfache.
    """
    from scipy import sparse
    nz = 3 * d["k"]
    zeilen, spalten, werte = [], [], []
    gr = max(1, 2_000_000 // (nz * nz))
    eas = d.get("eas")
    if eas is not None:
        # Mit inkompatiblen Moden muss ΔK **genauso kondensiert** werden wie K
        # selbst, sonst passt die Tangente nicht zur Last:
        #     ΔK = (Kuu+ΔKuu) − (Kua+ΔKua)(Kaa+ΔKaa)^-1 (Kua+ΔKua)ᵀ
        #          − [Kuu − Kua Kaa^-1 Kuaᵀ]
        # Ohne den kondensierten Anteil lief der Newton am Kragtraeger mit
        # vier hex8-Lagen auf 1e50 davon (20.09.2026); damit konvergiert er.
        betroffen = np.flatnonzero(fliesst.any(axis=0))
        if betroffen.size == 0:
            return sparse.csr_matrix((ndof, ndof))
        for a0 in range(0, betroffen.size, gr):
            teil = betroffen[a0:a0 + gr]
            mm = len(teil)
            na = eas["Ba"].shape[3]
            dKuu = np.zeros((mm, nz, nz))
            dKua = np.zeros((mm, nz, na))
            dKaa = np.zeros((mm, na, na))
            for gp, (_dNg, gew) in enumerate(d["lasten"]):
                maske = fliesst[gp][teil]
                if not maske.any():
                    continue
                qg = q[gp][teil]
                # tangenten_differenz ist bei dgamma = 0 **nicht** null (der
                # Term θ̄ bleibt stehen) - die nicht fliessenden Punkte
                # muessen darum ausdruecklich geloescht werden.
                dD = tangenten_differenz(dev[gp][teil], np.where(qg > 0.0, qg, 1.0),
                                         dgamma[gp][teil], G[gp][teil], H[gp][teil])
                dD[~maske] = 0.0
                B = _b_punkt(d, gp, teil)
                Ba = eas["Ba"][gp][teil]
                w = gew[teil][:, None, None]
                dDB = np.einsum("nij,njk->nik", dD, B)
                dDBa = np.einsum("nij,njk->nik", dD, Ba)
                dKuu += w * np.einsum("nji,njk->nik", B, dDB)
                dKua += w * np.einsum("nji,njk->nik", B, dDBa)
                dKaa += w * np.einsum("nji,njk->nik", Ba, dDBa)
            Kua_e = eas["Kua"][teil]
            Kaa_e = eas["Kaa"][teil]
            A1 = Kua_e + dKua
            ke = (dKuu
                  - np.einsum("nij,njk->nik", A1,
                              np.linalg.solve(Kaa_e + dKaa, A1.transpose(0, 2, 1)))
                  + np.einsum("nij,njk->nik", Kua_e,
                              np.linalg.solve(Kaa_e, Kua_e.transpose(0, 2, 1))))
            ke = 0.5 * (ke + ke.transpose(0, 2, 1))     # gegen Rundung symmetrisch
            dd = d["dofs"][teil]
            zeilen.append(np.repeat(dd, nz, axis=1).ravel())
            spalten.append(np.tile(dd, (1, nz)).ravel())
            werte.append(ke.reshape(-1))
        return sparse.coo_matrix((np.concatenate(werte),
                                  (np.concatenate(zeilen), np.concatenate(spalten))),
                                 shape=(ndof, ndof)).tocsr()
    for gp, (_dNg, gew) in enumerate(d["lasten"]):
        stellen = np.flatnonzero(fliesst[gp])
        if stellen.size == 0:
            continue
        for a0 in range(0, stellen.size, gr):
            teil = stellen[a0:a0 + gr]
            dd = d["dofs"][teil]
            B = _b_punkt(d, gp, teil)
            dD = tangenten_differenz(dev[gp][teil], q[gp][teil], dgamma[gp][teil],
                                     G[gp][teil], H[gp][teil])
            ke = gew[teil][:, None, None] * np.einsum(
                "nji,njk->nik", B, np.einsum("nij,njk->nik", dD, B))
            zeilen.append(np.repeat(dd, nz, axis=1).ravel())
            spalten.append(np.tile(dd, (1, nz)).ravel())
            werte.append(ke.reshape(-1))
    if not werte:
        return sparse.csr_matrix((ndof, ndof))
    return sparse.coo_matrix((np.concatenate(werte),
                              (np.concatenate(zeilen), np.concatenate(spalten))),
                             shape=(ndof, ndof)).tocsr()


class Zustand:
    """Plastische Dehnungen je **Gausspunkt**: {i: eps_p (P,6)}, {i: eps_p_eq (P,)}.

    Bis zum 20.09.2026 stand hier ein Wert je Element, gemessen in der
    Elementmitte. Beim ``tet4`` ist das dasselbe - ein Gausspunkt, konstante
    Dehnung -, beim Sechsflaechner war es falsch: unter reiner Biegung ist die
    Spannung in der Elementmitte **null**, und der Gradient der inkompatiblen
    Moden diag(-2r, -2s, -2t) verschwindet dort ebenfalls. Die Mitte ist genau
    der eine Punkt, an dem der hex8 seine Biegung nicht zeigt.

    Gemessen am Kragtraeger 200 x 200 mm unter reiner Biegung mit dem
    1,20-fachen des elastischen Grenzmoments (fy = 235 N/mm2, Randfaser also
    282 N/mm2 - sie **muss** fliessen), 20.09.2026:

        Lagen ueber die Hoehe    1       2       4       8    tet4 (4)
        sigma_v max [N/mm2]    0,0   146,0   223,5   239,3     235,7
        fliessende Elemente      0       0       0       8         2

    Mit einer hex8-Lage meldete das Programm null Spannung und kein
    fliessendes Element - unter einem Moment, das den Querschnitt
    plastifiziert. Die Durchbiegung stimmte dabei: das Element **trug**
    richtig, es berichtete nur nicht.
    """

    def __init__(self):
        self.eps_p: dict = {}
        self.eps_p_eq: dict = {}

    def kopie(self) -> "Zustand":
        z = Zustand()
        z.eps_p = {i: np.array(v, float, copy=True) for i, v in self.eps_p.items()}
        z.eps_p_eq = {i: np.array(v, float, copy=True) for i, v in self.eps_p_eq.items()}
        return z

    def fliessend(self) -> list:
        """Elemente, in denen **mindestens ein** Gausspunkt fliesst."""
        return [i for i, v in self.eps_p_eq.items() if float(np.max(v)) > 0.0]

    def eq_max(self) -> float:
        """Groesste plastische Vergleichsdehnung ueber alle Punkte."""
        if not self.eps_p_eq:
            return 0.0
        return float(max(float(np.max(v)) for v in self.eps_p_eq.values()))


def _punktfeld(v, P: int, spalten: int) -> np.ndarray:
    """Einen gespeicherten Zustandswert auf die Form (P,) bzw. (P,spalten)
    bringen - auch wenn er aus einer aelteren Rechnung je Element stammt."""
    a = np.asarray(v, float)
    ziel = (P,) if spalten == 0 else (P, spalten)
    if a.shape == ziel:
        return a
    if spalten == 0:
        return np.broadcast_to(a.reshape(-1)[:1], ziel).copy() if a.size == 1 \
            else np.broadcast_to(a.reshape(-1), ziel).copy()
    return np.broadcast_to(a.reshape(-1, spalten)[0], ziel).copy() if a.size == spalten \
        else a.reshape(ziel)


def _solid_elemente(model, aktiv=None) -> list:
    from . import assemble as asm
    idx = asm.aktive_indizes(model, aktiv)
    return [i for i in idx if model.elements[i].typ in asm.SOLID_TYPES]


def _stapel(model, elemente: list, typ: str) -> list:
    """Geometrie- und Werkstoffdaten der Elemente eines Typs - je Gruppe des
    Dehnungsoperators ein Eintrag (bei den isoparametrischen Typen genau einer).

    Die Kinematik kommt aus **dem** Operator des Elements
    (elements.solid.dehnungsoperator), den auch Steifigkeit und
    Spannungsrueckrechnung lesen. Bis zum 22.09.2026 stellte die Plastizitaet
    ihre Gradienten hier selbst aus _ISO auf - dieselben Zahlen, aber ein
    zweiter Weg: haette ein Element eine andere Kinematik bekommen (B-bar,
    mehr Punkte ueber die Dicke), haetten Steifigkeit und Fliessen still mit
    zwei verschiedenen gerechnet.

    Haengt nur am Netz und an den Werkstoffen, nicht an der Verschiebung -
    darum wird es am Modell gemerkt und ueber die Schritte einer Rechnung
    wiederverwendet (am Drehlager kostet der Aufbau rund 5,7 s, jeder weitere
    Schritt danach 1,4 s statt 51,5 s). Der Schluessel ist der Operator
    selbst (sein Fingerabdruck umfasst Elemente und Koordinaten) und die
    Werkstoffwerte - bis zum 22.09.2026 waren es Typ, Zahl, erstes und letztes
    Element, und ein geaenderter E-Modul blieb unbemerkt.

    ``lasten`` traegt je Integrationspunkt die Gradienten (oder None bei einem
    allgemeinen B) und das Gewicht w*|det J|; daraus entstehen die plastischen
    Knotenlasten f = ∫ Bᵀ σ0 dV. Bei tet4 ist das ein Punkt und das Gewicht
    gleich dem Volumen, bei hex8 sind es acht.
    """
    from .elements import solid as sl
    idx = np.asarray(elemente, dtype=np.int64)
    ops = sl.dehnungsoperator(model, typ, idx, merken=True)
    namen = tuple(model.elements[int(i)].mat for i in idx)
    wkey = (hash(namen), tuple(sorted(
        (nm, float(model.materials[nm].E), float(model.materials[nm].nu),
         getattr(model.materials[nm], "fy", None)) for nm in set(namen))))
    cache = getattr(model, "_plast_stapel", None)
    if cache is None:
        cache = model._plast_stapel = {}
    alt = cache.get(typ)
    if alt is not None and alt[0] is ops and alt[1] == wkey:
        return alt[2]
    daten_liste = []
    for op in ops:
        daten_liste.append(_stapel_teil(model, op))
    cache[typ] = (ops, wkey, daten_liste)
    return daten_liste


def _stapel_teil(model, op) -> dict:
    """Die Daten eines Operators: Werkstoffe je Element, FHG, Lasten, Moden."""
    from .elements import solid as sl
    idx = op.idx
    n = op.n
    E = np.empty(n); nu = np.empty(n)
    fy = np.zeros(n); hat_fy = np.zeros(n, bool)
    ohne: set = set()
    for a, i in enumerate(idx):
        mat = model.materials[model.elements[int(i)].mat]
        E[a], nu[a] = float(mat.E), float(mat.nu)
        f = getattr(mat, "fy", None)
        if f:
            fy[a], hat_fy[a] = float(f), True
        else:
            ohne.add(model.elements[int(i)].mat)
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    mu = E / (2.0 * (1.0 + nu))
    lasten = [(op.g[p] if op.nur_gradienten else None, op.w[p]) for p in range(op.P)]
    daten = {"typ": op.typ, "idx": idx, "k": op.k, "op": op,
             "lasten": lasten, "dofs": op.dofs(), "E": E, "nu": nu, "fy": fy,
             "hat_fy": hat_fy, "ohne_fy": ohne, "lam": lam, "mu": mu}
    if op.Ba is not None:
        daten["eas"] = _eas_daten(op, E, nu)
    return daten


#: Runden des Element-Newtons fuer die inkompatiblen Moden. Gemessen
#: 20.09.2026 am Kragtraeger und am Reibblock: drei bis vier Runden genuegen,
#: acht sind die Sicherung fuer schlecht geformte Elemente.
EAS_RUNDEN = 8
EAS_TOLERANZ = 1e-10


def _eas_daten(op, E, nu) -> dict:
    """Die inneren Moden eines Operators (hex8: Wilson-Moden) als Stapel:
    Ba je Integrationspunkt, Kua, Kaa, D.

    Der hex8 traegt seine Biegung ueber drei Wilson-Moden (1-r^2, 1-s^2,
    1-t^2), die in der Elementmatrix kondensiert werden. Rechnet die
    Plastizitaet ohne sie, passen plastische Lasten und Steifigkeit nicht
    zusammen: die Lasten regen Biegemoden an, in denen die kondensierte
    Steifigkeit viel weicher ist. Gemessen am Kragtraeger unter 1,20 M_el
    (20.09.2026, acht hex8-Lagen ueber die Hoehe): ohne die Moden in der
    Plastizitaet meldete das Programm 40 von 40 Elementen fliessend mit
    eps_p,eq 25,1 %, richtig sind 2 von 40 mit 0,025 %.

    Kua = Σ w |J| Bᵀ D Ba, Kaa = Σ w |J| Baᵀ D Ba - aus demselben Operator
    wie die Steifigkeit (elements.solid.matrizen_aus_operator).
    """
    from .elements import solid as sl
    D = sl.D_stapel(E, nu, op.n)
    _Kuu, Kua, Kaa = sl.matrizen_aus_operator(op, D, ohne_kuu=True)
    return {"Ba": op.Ba, "Kua": Kua, "Kaa": Kaa, "D": D}


def _b_punkt(d, p, stellen=None) -> np.ndarray:
    """B (m,6,3k) am Integrationspunkt p fuer die Elemente ``stellen``."""
    dNg = d["lasten"][p][0]
    if dNg is not None:
        return _B_stapel(dNg if stellen is None else dNg[stellen])
    B = d["op"].b(p)
    return B if stellen is None else B[stellen]


def _dehnung_punkt(d, p, ue_flach) -> np.ndarray:
    """Voigt-Dehnung (n,6) am Integrationspunkt p (ohne innere Moden)."""
    dNg = d["lasten"][p][0]
    if dNg is not None:
        return _dehnung(dNg, ue_flach.reshape(len(ue_flach), d["k"], 3))
    return (d["op"].b(p) @ ue_flach[:, :, None])[:, :, 0]


def _eas_alpha(eas, lam, mu2, eps_p, lasten, ue_flach) -> np.ndarray:
    """Die inneren Freiheitsgrade alpha (n,9) zu einer Verschiebung und einer
    plastischen Dehnung.

    Aus der Stationaritaet nach alpha (Σ Baᵀ sigma dV = 0) folgt
        Kaa alpha = h_p − Kuaᵀ u,      h_p = Σ w |J| Baᵀ D eps_p.
    """
    h = _eas_h(eas, lam, mu2, eps_p, lasten)
    rechts = h - np.einsum("nji,nj->ni", eas["Kua"], ue_flach)
    # numpy 2 deutet (n,9) neben (n,9,9) als Matrix, nicht als Stapel von
    # Vektoren - die letzte Achse muss ausgeschrieben werden.
    return np.linalg.solve(eas["Kaa"], rechts[..., None])[..., 0]


def _eas_h(eas, lam, mu2, eps_p, lasten) -> np.ndarray:
    """h_p = Σ_gp w |J| Baᵀ D eps_p  (n,9) - die plastische Last der Moden."""
    Ba = eas["Ba"]
    n = Ba.shape[1]
    h = np.zeros((n, Ba.shape[3]))
    for gp, (_dNg, gew) in enumerate(lasten):
        s0 = _spannung(lam, mu2, eps_p[gp])
        h += gew[:, None] * np.einsum("nji,nj->ni", Ba[gp], s0)
    return h


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
                   typ: str, log: list = None, tangente: bool = False) -> tuple:
    """Ein Schritt fuer einen Stapel gleichen Typs - dieselbe Rechnung wie
    :func:`_schritt_schleife`, nur als Feldoperationen.

    Gerechnet wird an **jedem Gausspunkt**, nicht in der Elementmitte (siehe
    :class:`Zustand`). Beim tet4 ist das ein Punkt und aendert nichts; beim
    hex8 sind es acht, und erst damit sieht die Plastizitaet die Biegung.

    ``tangente=True`` gibt in info["dK"] zusaetzlich
    ΔK = Σ_gp ∫ Bᵀ (D_ep − D_el) B dV der fliessenden Punkte zurueck.

    Liefert der Dehnungsoperator mehrere Gruppen (verschiedene Punkt- oder
    Knotenzahl), rechnet jede fuer sich; die Ergebnisse werden addiert.
    """
    teile = _stapel(model, elemente, typ)
    if len(teile) == 1:
        return _schritt_teil(model, u, zustand, einst, teile[0], log, tangente)
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fl, q_max, dK = 0, 0.0, None
    for d in teile:
        Fb, zb, ib = _schritt_teil(model, u, zustand, einst, d, log, tangente)
        F_p += Fb
        for i in d["idx"]:
            i = int(i)
            if i in zb.eps_p:
                neu.eps_p[i] = zb.eps_p[i]
                neu.eps_p_eq[i] = zb.eps_p_eq[i]
        n_fl += ib["fliessend"]
        q_max = max(q_max, ib["q_max"])
        if tangente:
            dK = ib["dK"] if dK is None else (dK + ib["dK"])
    info = {"fliessend": n_fl, "q_max": q_max}
    if tangente:
        info["dK"] = dK
    return F_p, neu, info


def _schritt_teil(model, u, zustand: Zustand, einst: Plastizitaet, d: dict,
                  log: list = None, tangente: bool = False) -> tuple:
    """:func:`_schritt_block` fuer eine Gruppe des Dehnungsoperators."""
    idx, dofs, k = d["idx"], d["dofs"], d["k"]
    lam, mu2 = d["lam"], d["mu"]
    lasten = d["lasten"]
    P = len(lasten)
    n = len(idx)
    ue_flach = np.asarray(u, float)[dofs]
    eps_p = np.zeros((P, n, 6))
    eps_p_eq = np.zeros((P, n))
    hatte = np.zeros(n, bool)
    if zustand.eps_p:
        platz = {int(i): a for a, i in enumerate(idx)}
        for i, v in zustand.eps_p.items():
            a = platz.get(int(i))
            if a is None:
                continue
            eps_p[:, a, :] = _punktfeld(v, P, 6)
            eps_p_eq[:, a] = _punktfeld(zustand.eps_p_eq.get(i, 0.0), P, 0)
            hatte[a] = True
    # Werkstoffwerte je (Gausspunkt, Element), P-fach gelegt
    m = P * n
    eqF = eps_p_eq.reshape(m)
    fyF = np.tile(d["fy"], P)
    hatF = np.tile(d["hat_fy"], P)
    EF = np.tile(d["E"], P)
    nuF = np.tile(d["nu"], P)
    r = max(0.0, min(float(einst.verfestigung), 0.999))
    H = EF * r / (1.0 - r)
    G = EF / (2.0 * (1.0 + nuF))
    eps_B = np.stack([_dehnung_punkt(d, p, ue_flach) for p in range(P)])      # (P,n,6)

    def rueckfuehren(alpha):
        """Versuchsspannung, Rueckfuehrung und neuer Zustand zu einem alpha."""
        sig = np.empty((P, n, 6))
        for q_ in range(P):
            e_ges = eps_B[q_] if alpha is None else \
                eps_B[q_] + np.einsum("nij,nj->ni", eas["Ba"][q_], alpha)
            sig[q_] = _spannung(lam, mu2, e_ges - eps_p[q_])
        sigF = sig.reshape(m, 6)
        p_hyd = (sigF[:, 0] + sigF[:, 1] + sigF[:, 2]) / 3.0
        dev = sigF.copy()
        dev[:, 0] -= p_hyd
        dev[:, 1] -= p_hyd
        dev[:, 2] -= p_hyd
        q = np.sqrt(1.5 * (dev[:, 0] ** 2 + dev[:, 1] ** 2 + dev[:, 2] ** 2)
                    + 3.0 * (dev[:, 3] ** 2 + dev[:, 4] ** 2 + dev[:, 5] ** 2))
        f = q - (fyF + H * eqF)
        fliesst = hatF & (f > 0.0) & (q > 0.0)
        dgamma = np.zeros(m)
        np.divide(f, 3.0 * G + H, out=dgamma, where=fliesst)
        richtung = 1.5 * dev / np.where(q > 0.0, q, 1.0)[:, None]
        eps_p_neu = (eps_p.reshape(m, 6) + dgamma[:, None] * richtung * _SCHUB[None, :]
                     ).reshape(P, n, 6)
        sig_neu = sigF - 2.0 * G[:, None] * dgamma[:, None] * richtung
        return sigF, dev, q, fliesst, dgamma, eps_p_neu, sig_neu

    # Beim hex8 gehoeren die inkompatiblen Moden in die Plastizitaet
    # (siehe _eas_daten). alpha und eps_p haengen voneinander ab und werden
    # **im Element gemeinsam** geloest: R(alpha) = Σ w Baᵀ sigma = 0, mit der
    # elastoplastischen Tangente als Jacobi-Matrix. Gestaffelt - alpha aus dem
    # vorigen eps_p - lief der Reibblock auf eps_p 1e15 % davon (20.09.2026).
    eas = d.get("eas")
    alpha = None
    if eas is not None:
        alpha = _eas_alpha(eas, lam, mu2, eps_p, lasten, ue_flach)
        gew_alle = np.stack([gew for _dNg, gew in lasten])           # (P,n)
        for _runde in range(EAS_RUNDEN):
            _sF, dv, qq, fl, dg, _ep, s_neu = rueckfuehren(alpha)
            s_neu_p = s_neu.reshape(P, n, 6)
            R = np.zeros((n, eas["Ba"].shape[3]))
            for q_ in range(P):
                R += gew_alle[q_][:, None] * np.einsum("nji,nj->ni", eas["Ba"][q_],
                                                       s_neu_p[q_])
            if float(np.abs(R).max()) <= EAS_TOLERANZ * max(1.0, float(np.abs(s_neu).max())):
                break
            dD = tangenten_differenz(dv, np.where(qq > 0.0, qq, 1.0), dg, G, H)
            dD[~fl] = 0.0
            dD = dD.reshape(P, n, 6, 6)
            J = np.zeros((n, eas["Ba"].shape[3], eas["Ba"].shape[3]))
            for q_ in range(P):
                Dep = eas["D"] + dD[q_]
                J += gew_alle[q_][:, None, None] * np.einsum(
                    "nji,njk->nik", eas["Ba"][q_],
                    np.einsum("nij,njk->nik", Dep, eas["Ba"][q_]))
            alpha = alpha - np.linalg.solve(J, R[..., None])[..., 0]
    sigF, dev, q, fliesst, dgamma, eps_p_neu, sig_neu = rueckfuehren(alpha)
    eq_neu = (eqF + dgamma).reshape(P, n)
    p_neu = (sig_neu[:, 0] + sig_neu[:, 1] + sig_neu[:, 2]) / 3.0
    q_neu = np.sqrt(1.5 * ((sig_neu[:, 0] - p_neu) ** 2 + (sig_neu[:, 1] - p_neu) ** 2
                           + (sig_neu[:, 2] - p_neu) ** 2)
                    + 3.0 * (sig_neu[:, 3] ** 2 + sig_neu[:, 4] ** 2 + sig_neu[:, 5] ** 2))
    # Neuer Zustand und plastische Knotenlasten - nur fuer Elemente, die an
    # mindestens einem Punkt fliessen oder schon eine Dehnung tragen
    neu = zustand.kopie()
    fliesst_e = fliesst.reshape(P, n).any(axis=0)
    traegt = fliesst_e | hatte
    F_p = np.zeros(model.ndof)
    stellen = np.flatnonzero(traegt)
    if stellen.size:
        for a in stellen:
            neu.eps_p[int(idx[a])] = eps_p_neu[:, a, :].copy()
            neu.eps_p_eq[int(idx[a])] = eq_neu[:, a].copy()
        # F_p = Σ_gp w |J| Bᵀ D eps_p - jeder Gausspunkt mit seiner eigenen
        # plastischen Dehnung. Vorher trug jedes Element **eine**; damit
        # reagierte F_p auf keine Biegemode, und die Gausspunktfassung der
        # Tangente lief deshalb davon (siehe _dk_block).
        fe = np.zeros((len(stellen), k, 3))
        fe_B = np.zeros((len(stellen), 3 * k))
        for q_, (dNg, gew) in enumerate(lasten):
            w = gew[stellen][:, None]                           # (m,1)
            s0 = _spannung(lam[stellen], mu2[stellen], eps_p_neu[q_][stellen])
            if dNg is None:
                # allgemeines B des Operators (etwa mit B-bar): f = Bᵀ s0
                fe_B += w * np.einsum("nji,nj->ni", d["op"].b(q_)[stellen], s0)
                continue
            g = dNg[stellen]                                    # (m,k,3)
            fe[:, :, 0] += w * (g[:, :, 0] * s0[:, 0, None] + g[:, :, 1] * s0[:, 3, None]
                                + g[:, :, 2] * s0[:, 5, None])
            fe[:, :, 1] += w * (g[:, :, 1] * s0[:, 1, None] + g[:, :, 0] * s0[:, 3, None]
                                + g[:, :, 2] * s0[:, 4, None])
            fe[:, :, 2] += w * (g[:, :, 2] * s0[:, 2, None] + g[:, :, 1] * s0[:, 4, None]
                                + g[:, :, 0] * s0[:, 5, None])
        fe = fe.reshape(len(stellen), 3 * k) + fe_B
        if eas is not None:
            # Kondensiert: F_p = Σ Bᵀ D eps_p dV − Kua Kaa^-1 h_p. Ohne den
            # zweiten Term traegt die Last Biegeanteile, die die kondensierte
            # Steifigkeit gar nicht sieht - die Iteration laeuft dann davon.
            h_neu = _eas_h(eas, lam, mu2, eps_p_neu, lasten)[stellen]
            fe = fe - np.einsum(
                "nij,nj->ni", eas["Kua"][stellen],
                np.linalg.solve(eas["Kaa"][stellen], h_neu[..., None])[..., 0])
        np.add.at(F_p, dofs[stellen].ravel(), fe.reshape(-1))
    if d["ohne_fy"] and log is not None:
        log.append("Plastizität: Werkstoffe ohne Streckgrenze bleiben elastisch - "
                   + ", ".join(sorted(d["ohne_fy"])))
    # q_max zaehlt nur Werkstoffe mit Streckgrenze: die Schleife ueberspringt
    # die uebrigen ganz (19.09.2026, vom Vergleichstest gefunden)
    q_max = float(q_neu[hatF].max()) if (m and hatF.any()) else 0.0
    info = {"fliessend": int(fliesst_e.sum()), "q_max": q_max}
    if tangente:
        info["dK"] = _dk_block(d, fliesst.reshape(P, n), dev.reshape(P, n, 6),
                               q.reshape(P, n), dgamma.reshape(P, n),
                               G.reshape(P, n), H.reshape(P, n), model.ndof)
    return F_p, neu, info


def schritt(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list, log: list = None,
            tangente: bool = False) -> tuple:
    """Ein Schritt der Anfangsdehnungs-Iteration: aus u die Versuchsspannung
    D(ε − eps_p) je Element, Rueckfuehrung, neue eps_p, plastische
    Knotenlasten F_p = Σ ∫ Bᵀ D eps_p dV. Rueckgabe (F_p, Zustand, info).

    ``tangente=True`` legt ΔK der konsistenten Tangente in info["dK"] dazu."""
    from . import assemble as asm
    from .elements import solid as sl
    # Blockweise: die Schleife kostet am Drehlager 80 µs je Element, und das
    # bei null fliessenden - es ist der Aufrufaufwand, nicht die Physik
    # (19.09.2026). Gerechnet wird je Elementtyp ein Stapel; die Schleife
    # bleibt fuer unbekannte Typen und als Referenz des Vergleichstests.
    if not elemente:
        from scipy import sparse
        leer = {"fliessend": 0, "q_max": 0.0}
        if tangente:
            leer["dK"] = sparse.csr_matrix((model.ndof, model.ndof))
        return np.zeros(model.ndof), zustand.kopie(), leer
    from .elements import solid as sl
    je_typ: dict = {}
    for i in elemente:
        je_typ.setdefault(model.elements[i].typ, []).append(i)
    if any(t not in sl.OPERATOREN for t in je_typ):
        if tangente:
            raise NotImplementedError("konsistente Tangente nur fuer die bekannten "
                                      "Volumenelementtypen")
        return _schritt_schleife(model, u, zustand, einst, elemente, log)
    if len(je_typ) == 1:
        typ, liste = next(iter(je_typ.items()))
        return _schritt_block(model, u, zustand, einst, liste, typ, log, tangente)
    # Gemischtes Netz: je Typ ein Stapel, die Ergebnisse zusammenlegen
    F_p = np.zeros(model.ndof)
    neu = zustand.kopie()
    n_fliesst, q_max = 0, 0.0
    dK = None
    for typ, liste in je_typ.items():
        Fb, zb, ib = _schritt_block(model, u, zustand, einst, liste, typ, log, tangente)
        F_p += Fb
        for i in liste:
            if i in zb.eps_p:
                neu.eps_p[i] = zb.eps_p[i]
                neu.eps_p_eq[i] = zb.eps_p_eq[i]
        n_fliesst += ib["fliessend"]
        q_max = max(q_max, ib["q_max"])
        if tangente:
            dK = ib["dK"] if dK is None else (dK + ib["dK"])
    info = {"fliessend": n_fliesst, "q_max": q_max}
    if tangente:
        info["dK"] = dK
    return F_p, neu, info


def _schritt_schleife(model, u, zustand: Zustand, einst: Plastizitaet, elemente: list,
                      log: list = None) -> tuple:
    """Derselbe Schritt, Element fuer Element und Gausspunkt fuer Gausspunkt -
    die Referenz fuer alles, was nicht im Stapel geht, und der Vergleich im
    Test (tests/test_plastizitaet.py).

    Bewusst ein eigener Weg: die B-Matrix wird hier je Punkt aufgestellt
    (``sl._ISO``), nicht ueber den Stapel. Stimmen beide ueberein, ist es
    keine gemeinsame Verwechslung.
    """
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
        D = sl.D_matrix(E, nu)
        k = sl._KNOTENZAHL[e.typ]
        X = np.asarray(model.nodes, float)[list(e.nodes)[:k]]
        dofs = asm.element_dofs(e, model)
        ue = np.asarray(u, float)[dofs]
        fn, GP, W = sl._ISO[e.typ]
        P = len(GP)
        eps_p_alt = _punktfeld(zustand.eps_p.get(i, np.zeros((P, 6))), P, 6)
        eq_alt = _punktfeld(zustand.eps_p_eq.get(i, 0.0), P, 0)
        eps_p_neu = np.array(eps_p_alt, float, copy=True)
        eq_neu = np.array(eq_alt, float, copy=True)
        # B-Matrix und Gewicht je Integrationspunkt aus dem Dehnungsoperator
        # **dieses einen** Elements - dieselbe Kinematik wie Steifigkeit und
        # Stapel (bei hex8 mit projizierter Volumendehnung, sonst stimmten
        # Steifigkeit und Fliessen nicht ueberein). Unabhaengig bleibt hier
        # die Rechnung: Element fuer Element, Punkt fuer Punkt, mit
        # rueckfuehrung() statt der Feldoperationen des Stapels.
        op1 = sl.dehnungsoperator(model, e.typ, [i])[0]
        if op1.P != P:
            GP = [None] * op1.P
            P = op1.P
            eps_p_alt = _punktfeld(zustand.eps_p.get(i, np.zeros((P, 6))), P, 6)
            eq_alt = _punktfeld(zustand.eps_p_eq.get(i, 0.0), P, 0)
            eps_p_neu = np.array(eps_p_alt, float, copy=True)
            eq_neu = np.array(eq_alt, float, copy=True)
        Bs = [op1.b(p_)[0] for p_ in range(P)]
        gew_p = [float(op1.w[p_][0]) for p_ in range(P)]
        # Mit inneren Moden (hex8) werden alpha und eps_p im Element gemeinsam
        # geloest (siehe _eas_daten); Kua, Kaa und Ba aus dem Einzeloperator.
        Ba_p, Kua, Kaa, alpha = None, None, None, None
        if op1.Ba is not None:
            _Kuu, Kua, Kaa = sl.matrizen_aus_operator(op1, D, ohne_kuu=True)
            Kua, Kaa = Kua[0], Kaa[0]
            Ba_p = [op1.Ba[p_][0] for p_ in range(P)]
            h_alt = sum(gew_p[gp] * (Ba_p[gp].T @ (D @ eps_p_alt[gp])) for gp in range(P))
            alpha = np.linalg.solve(Kaa, h_alt - Kua.T @ ue)

        def durchgang(alpha_):
            """Rueckfuehrung an allen Gausspunkten zu einem alpha."""
            erg = []
            for gp in range(P):
                eps_ges = Bs[gp] @ ue
                if Ba_p is not None:
                    eps_ges = eps_ges + Ba_p[gp] @ alpha_
                erg.append((D @ (eps_ges - eps_p_alt[gp]),)
                           + rueckfuehrung(D @ (eps_ges - eps_p_alt[gp]),
                                           float(fy), H, G, float(eq_alt[gp])))
            return erg

        if Ba_p is not None:
            for _runde in range(EAS_RUNDEN):
                erg = durchgang(alpha)
                R = sum(gew_p[gp] * (Ba_p[gp].T @ erg[gp][1]) for gp in range(P))
                gr = max(1.0, max(float(np.abs(x[1]).max()) for x in erg))
                if float(np.abs(R).max()) <= EAS_TOLERANZ * gr:
                    break
                Jm = np.zeros((Ba_p[0].shape[1], Ba_p[0].shape[1]))
                for gp in range(P):
                    sig_tr, _s_neu, _d_eps, dgam = erg[gp]
                    dD = np.zeros((6, 6))
                    if dgam > 0:
                        pm = (sig_tr[0] + sig_tr[1] + sig_tr[2]) / 3.0
                        dv = np.array(sig_tr, float, copy=True)
                        dv[:3] -= pm
                        dD = tangenten_differenz(dv[None, :],
                                                 np.array([vergleichsspannung(sig_tr)]),
                                                 np.array([dgam]), np.array([G]),
                                                 np.array([H]))[0]
                    Jm += gew_p[gp] * (Ba_p[gp].T @ ((D + dD) @ Ba_p[gp]))
                alpha = alpha - np.linalg.solve(Jm, R)
        fe = np.zeros(3 * k)
        fliesst_hier = False
        for gp, (_sig_tr, sig_neu, d_eps_p, dgamma) in enumerate(durchgang(alpha)):
            q_max = max(q_max, vergleichsspannung(sig_neu))
            if dgamma > 0:
                fliesst_hier = True
                eps_p_neu[gp] = eps_p_alt[gp] + d_eps_p
                eq_neu[gp] = float(eq_alt[gp]) + dgamma
            fe += gew_p[gp] * (Bs[gp].T @ (D @ eps_p_neu[gp]))
        if Ba_p is not None:
            h_neu = sum(gew_p[gp] * (Ba_p[gp].T @ (D @ eps_p_neu[gp])) for gp in range(P))
            fe = fe - Kua @ np.linalg.solve(Kaa, h_neu)
        if fliesst_hier or i in neu.eps_p:
            neu.eps_p[i] = eps_p_neu
            neu.eps_p_eq[i] = eq_neu
            if fliesst_hier:
                n_fliesst += 1
            np.add.at(F_p, dofs, fe)
    if ohne_fy and log is not None:
        log.append("Plastizität: Werkstoffe ohne Streckgrenze bleiben elastisch - " + ", ".join(sorted(ohne_fy)))
    return F_p, neu, {"fliessend": n_fliesst, "q_max": q_max}


def _newton(model, F, loesen, loesen_tangente, einst: Plastizitaet, elemente: list,
            norm_F: float, info: dict, log: list = None, progress=None) -> tuple:
    """Newton mit der konsistenten Tangente - siehe :func:`iteration`.

    Die Rueckfuehrung geht in jedem Schritt vom Zustand am **Anfang der
    Laststufe** aus (``basis``), nicht vom letzten Schritt: nur dann ist
    F_p eine Funktion von u allein und D_ep wirklich ihre Ableitung. Die
    Anfangsdehnungs-Iteration schreibt eps_p dagegen von Schritt zu Schritt
    fort - dasselbe im Grenzwert, aber nicht differenzierbar.
    """
    info["verfahren"] = "tangente"
    stufen = int(max(1, einst.laststufen))
    basis = Zustand()
    F_p = np.zeros(model.ndof)
    u = None
    diff = 0.0
    for k in range(1, stufen + 1):
        F_k = (k / stufen) * F
        # Startwert der Laststufe: elastische Loesung mit dem bisherigen F_p -
        # ein Rueckwaertseinsetzen auf der schon vorhandenen Faktorisierung
        u = loesen(F_k + F_p)
        F_p_stufe, zustand_stufe = F_p, basis
        for it in range(1, int(max(1, einst.iterationen)) + 1):
            F_p_neu, zustand_neu, s_info = schritt(model, u, basis, einst, elemente, log,
                                                   tangente=True)
            diff = float(np.linalg.norm(F_p_neu - F_p_stufe)) / norm_F
            F_p_stufe, zustand_stufe = F_p_neu, zustand_neu
            info["iterationen"] += 1
            info["verlauf"].append((k, it, diff, s_info["fliessend"]))
            if progress is not None:
                progress(f"Plastizität: Laststufe {k}/{stufen}, Newton-Schritt {it}: "
                         f"{s_info['fliessend']} Elemente fließen, Änderung {diff:.2e}")
            if diff <= float(einst.toleranz):
                break
            dK = s_info["dK"]
            if dK.nnz == 0:
                # Nichts fliesst gerade (etwa beim Entlasten): die Tangente ist
                # die elastische, und dafuer gibt es die Faktorisierung schon
                u = loesen(F_k + F_p_neu)
            else:
                u = loesen_tangente(F_k + F_p_neu + dK @ u, dK)
                info["faktorisierungen"] += 1
        else:
            info["konvergiert"] = False
            if log is not None:
                log.append(f"Plastizität: Laststufe {k} nach {einst.iterationen} Newton-Schritten "
                           f"nicht konvergiert (Änderung {diff:.2e} > {einst.toleranz:g})")
        basis, F_p = zustand_stufe, F_p_stufe
    # Die letzte Loesung gehoert zum letzten Zustand: im Gleichgewicht ist
    # K u = F + F_p, also genau diese elastische Loesung
    u = loesen(F + F_p)
    info["fliessend"] = len(basis.fliessend())
    info["eps_p_max"] = basis.eq_max()
    if log is not None:
        log.append(f"Plastizität: {info['fliessend']} Elemente fließen, ε_p,eq max "
                   f"{info['eps_p_max'] * 100:.3f} %, {info['iterationen']} Newton-Schritte in "
                   f"{stufen} Laststufen ({info['faktorisierungen']} Faktorisierungen, "
                   f"konsistente Tangente)"
                   + ("" if info["konvergiert"] else " - nicht konvergiert"))
    return u, basis, F_p, info


def iteration(model, F, loesen, einst: Plastizitaet, aktiv=None, log: list = None,
              progress=None, loesen_tangente=None) -> tuple:
    """Laststufen und Fliess-Iteration. ``loesen(F_ges)`` liefert u fuer die
    Gesamtlast bei der **elastischen** Steifigkeit (mit Kontakt: eine
    Kontakt-Iteration, die Faktorisierung bleibt). Rueckgabe
    (u, Zustand, F_p, info) fuer die volle Last.

    Zwei Wege, ``einst.verfahren`` waehlt:

    * ``"tangente"`` (Vorgabe) - Newton mit der konsistenten elastoplastischen
      Tangente. Braucht ``loesen_tangente(F_ges, dK)``: loest mit der
      Steifigkeit K + dK, also **je Schritt eine neue Faktorisierung**. Die
      Fortschreibung in Gesamtform ist

          (K + ΔK) u_{k+1} = F_k + F_p(u_k) + ΔK u_k,

      identisch zu ΔK-Newton auf dem Residuum F_k + F_p − K u (die
      Randbedingungen und der Kontakt bleiben dem Loeser ueberlassen). Die
      Rueckfuehrung geht in jedem Schritt vom Zustand am **Anfang der
      Laststufe** aus - nur so ist die Tangente wirklich die Ableitung.
    * ``"anfangsdehnung"`` - die alte Fixpunktfolge bei fester Steifigkeit
      mit Aitken-Relaxation. Eine Faktorisierung je Rechnung, aber linear mit
      dem Faktor 1 − E_t/E: bei 1 % Verfestigung 0,99 je Schritt.

    Ohne ``loesen_tangente`` (etwa aus einem Test, der nur ``system.solve``
    hergibt) faellt "tangente" auf "anfangsdehnung" zurueck.
    """
    elemente = _solid_elemente(model, aktiv)
    zustand = Zustand()
    F = np.asarray(F, float)
    norm_F = float(np.linalg.norm(F)) or 1.0
    F_p = np.zeros(model.ndof)
    u = None
    info = {"laststufen": int(max(1, einst.laststufen)), "iterationen": 0, "konvergiert": True,
            "fliessend": 0, "eps_p_max": 0.0, "verlauf": [], "faktorisierungen": 0,
            "verfahren": "anfangsdehnung"}
    if not elemente:
        u = loesen(F)
        return u, zustand, F_p, info
    from .elements import solid as sl
    # Ohne Verfestigung ist D_ep in Fliessrichtung singulaer (Eigenwert
    # 2G(θ − θ̄) = 2G (H/3G)/(1 + H/3G) = 0) - dann bleibt nur die
    # Anfangsdehnungs-Iteration. Ebenso bei einem Elementtyp ohne Stapel.
    kann_tangente = (loesen_tangente is not None and einst.H(1.0) > 0.0
                     and all(model.elements[i].typ in sl.OPERATOREN for i in elemente))
    if str(getattr(einst, "verfahren", "tangente")) == "tangente" and kann_tangente:
        return _newton(model, F, loesen, loesen_tangente, einst, elemente, norm_F, info,
                       log, progress)
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
    info["eps_p_max"] = zustand.eq_max()
    if log is not None:
        log.append(f"Plastizität: {info['fliessend']} Elemente fließen, ε_p,eq max {info['eps_p_max'] * 100:.3f} %, "
                   f"{info['iterationen']} Schritte in {stufen} Laststufen"
                   + ("" if info["konvergiert"] else " - nicht konvergiert"))
    return u, zustand, F_p, info


def sigma0_je_element(model, zustand: Zustand) -> dict:
    """{Element: D eps_p} - die Anfangsspannung fuer den Spannungsnachlauf
    (σ = D ε − D eps_p), im Schluessel "sigma0" von temp.

    Der Zustand haelt eps_p je Integrationspunkt; hier wird ueber sie
    gemittelt - **gewichtet** mit den Gewichten des Dehnungsoperators (seit
    22.09.2026; vorher ungewichtet, was bei einer Lobatto-Regel ueber die
    Dicke die Randpunkte mit 1/10 statt 9/90 bzw. die Mitte mit 1/5 statt
    32/45 zaehlte). Beim tet4 (ein Punkt) ist es derselbe Wert wie frueher,
    bei 2x2x2 an einem Parallelepiped ebenso (gleiche Gewichte)."""
    from .elements import solid as sl
    aus = {}
    je_typ: dict = {}
    for i in zustand.eps_p:
        je_typ.setdefault(model.elements[i].typ, []).append(int(i))
    for typ, liste in je_typ.items():
        gew = {}
        if typ in sl.OPERATOREN:
            for op in sl.dehnungsoperator(model, typ, liste):
                for a, i in enumerate(op.idx):
                    gew[int(i)] = op.w[:, a] / op.w[:, a].sum()
        for i in liste:
            e = model.elements[i]
            mat = model.materials[e.mat]
            ep = np.asarray(zustand.eps_p[i], float).reshape(-1, 6)
            w = gew.get(i)
            mittel = ep.mean(axis=0) if w is None or len(w) != len(ep) else w @ ep
            aus[i] = sl.D_matrix(float(mat.E), float(mat.nu)) @ mittel
    return aus


def punktspannungen(model, u, zustand: Zustand) -> dict:
    """{Element: (xi (P,3), sigma (P,6))} der Elemente mit plastischem Zustand -
    die Spannung an **jedem Integrationspunkt**, sigma = D (B u + B_a alpha - eps_p).

    Dort und nur dort ist der plastische Zustand bekannt; jeder dieser Werte
    liegt auf oder in der verfestigten Fliessflaeche. Die Auswertepunkte
    (Mitte, Ecken) liegen woanders - an einer Ecke waechst die Dehnung ueber
    die der Punkte hinaus, eps_p bleibt zurueck, und die gemeldete Spannung
    schoss ueber die Fliessflaeche (gemessen 20.09.2026 am Reibblock: 2,93
    gegen die Grenze 1,42 MPa). Darum nimmt der Nachlauf fuer fliessende
    Elemente diese Punkte (solver._post_chunk).

    Die inneren Moden (hex8) folgen aus der Stationaritaet bei festem eps_p:
    Kaa alpha = h_p - Kua^T u (siehe _eas_alpha) - im Gleichgewicht ist das
    dasselbe alpha, das der Element-Newton des letzten Schritts fand.
    """
    from .elements import solid as sl
    if not zustand.eps_p:
        return {}
    je_typ: dict = {}
    for i in zustand.eps_p:
        typ = model.elements[int(i)].typ
        if typ in sl.OPERATOREN:
            je_typ.setdefault(typ, []).append(int(i))
    u = np.asarray(u, float).ravel()
    aus = {}
    for typ, liste in je_typ.items():
        for op in sl.dehnungsoperator(model, typ, sorted(liste)):
            d = _stapel_teil(model, op)
            n, P = op.n, op.P
            ue_flach = u[d["dofs"]]
            eps_p = np.zeros((P, n, 6))
            for a, i in enumerate(op.idx):
                eps_p[:, a, :] = _punktfeld(zustand.eps_p[int(i)], P, 6)
            alpha = None
            if d.get("eas") is not None:
                alpha = _eas_alpha(d["eas"], d["lam"], d["mu"], eps_p, d["lasten"], ue_flach)
            sig = np.empty((n, P, 6))
            for p in range(P):
                eps = sl.dehnung_mit_moden(op, p, ue_flach, alpha)
                sig[:, p, :] = _spannung(d["lam"], d["mu"], eps - eps_p[p])
            xi = None if op.xi is None else np.asarray(op.xi, float)
            for a, i in enumerate(op.idx):
                aus[int(i)] = (xi, sig[a])
    return aus
