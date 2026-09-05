"""
Strömungsnumerik im Schnitt.

Beide Lastgenerierer, Wasserdruck und Wind, rechnen ihre Druckverteilung
auf einem **Rechteckgitter in einer Schnittebene** durch das Modell:

* **Wasser** - Potentialströmung (reibungsfrei, drehungsfrei): Laplace-
  Gleichung Δφ = 0 mit Finite-Volumen auf dem Gitter, Zu- und Abfluss als
  vorgegebene Randgeschwindigkeiten, die Wasserspiegel als feste Deckel, der
  Verschluss als undurchlässiger Bereich, Sohle und Schwelle als Wand. Der
  Druck folgt aus Bernoulli p = ρ·g·(E − z) − ½·ρ·|v|² mit der Energiehöhe E
  des Ober- bzw. Unterwassers.
* **Wind** - Gitter-Boltzmann-Verfahren (D2Q9, BGK): eine zähe Strömung
  mit Grenzschicht, Nachlauf, Wirbelablösung, gegenseitiger Beeinflussung
  und Verschattung wie im Windkanal. Der Druck wird über die letzten
  Schritte zeitlich gemittelt und als Beiwert c_p = (p − p_∞)/(½·ρ·u_∞²)
  auf die Flächen gebracht.

Gemeinsam: die Rasterung der Modellgeometrie (Flächen, Körper) in die
Schnittebene (:func:`objekt_dreiecke`, :func:`rastern`), die Abtastung des
Zellfeldes an einem Punkt entlang der Flächennormale (:func:`wert_am_punkt`),
das Bild des Feldes für den Bericht (:func:`feld_svg`) und ein
Fortschrittsrückruf ``fortschritt(anteil, text) -> bool`` - gibt er False
zurück, wird mit :class:`Abgebrochen` angehalten.

Koordinaten: x' läuft in Strömungsrichtung (``ex``), z' quer dazu in der
Ebene (``ez``; beim Wasser lotrecht nach oben, im Grundriss waagerecht).
Zelle (k, i) hat ihre Mitte bei x' = (i + ½)·h, z' = (k + ½)·h.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib
from dataclasses import dataclass, asdict

import numpy as np

G = 9.81


class Abgebrochen(Exception):
    """Der Anwender hat die Berechnung abgebrochen."""


def _melden(fortschritt, anteil: float, text: str):
    if fortschritt is not None and fortschritt(float(anteil), str(text)) is False:
        raise Abgebrochen(text)


# ==========================================================================
# Schnittebene und Gitter
# ==========================================================================
@dataclass
class Schnitt:
    """Rechteckgitter in einer Ebene: Ursprung (Weltpunkt der Ecke x' = z' = 0),
    Achsen ``ex`` (Strömung) und ``ez`` (quer, in der Ebene), Zellgröße ``h``,
    ``nx`` × ``nz`` Zellen."""
    ursprung: list
    ex: list
    ez: list
    h: float
    nx: int
    nz: int

    def __post_init__(self):
        self.ursprung = [float(v) for v in np.asarray(self.ursprung, float).ravel()[:3]]
        ex = np.asarray(self.ex, float).ravel()[:3]
        ez = np.asarray(self.ez, float).ravel()[:3]
        self.ex = (ex / (np.linalg.norm(ex) or 1.0)).tolist()
        self.ez = (ez / (np.linalg.norm(ez) or 1.0)).tolist()
        self.h = float(self.h)
        self.nx, self.nz = int(self.nx), int(self.nz)

    @property
    def ey(self) -> np.ndarray:
        return np.cross(np.asarray(self.ex), np.asarray(self.ez))

    def xz(self, P):
        """Weltpunkte (n, 3) -> (x', z') je Punkt."""
        Q = np.atleast_2d(np.asarray(P, float))[:, :3] - np.asarray(self.ursprung)
        return Q @ np.asarray(self.ex), Q @ np.asarray(self.ez)

    def zelle(self, x, z):
        """Zellindex (i, k) zu Ebenenkoordinaten - auch ausserhalb des Gitters."""
        return (np.floor(np.asarray(x, float) / self.h).astype(int),
                np.floor(np.asarray(z, float) / self.h).astype(int))

    def drin(self, i, k) -> np.ndarray:
        return (np.asarray(i) >= 0) & (np.asarray(i) < self.nx) & (np.asarray(k) >= 0) & (np.asarray(k) < self.nz)

    def mitten(self):
        """(X, Z) der Zellmitten als (nz, nx)-Felder."""
        x = (np.arange(self.nx) + 0.5) * self.h
        z = (np.arange(self.nz) + 0.5) * self.h
        return np.meshgrid(x, z)

    def welt(self, x, z) -> np.ndarray:
        return (np.asarray(self.ursprung) + np.asarray(x, float)[..., None] * np.asarray(self.ex)
                + np.asarray(z, float)[..., None] * np.asarray(self.ez))

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Schnitt":
        return Schnitt(d["ursprung"], d["ex"], d["ez"], d["h"], d["nx"], d["nz"])


# ==========================================================================
# Geometrie in die Ebene rastern
# ==========================================================================
def objekt_dreiecke(model, flaechen, koerper=(), teilung: int = 12) -> list:
    """Alle Dreiecke (Weltkoordinaten, (3, 3)) der genannten Flächen und der
    Randflächen der Körper - aus den Schalenelementen, den Randseiten der
    Volumenelemente oder, ohne Netz, aus dem Randpolygon der Fläche."""
    from .assemble import SOLID_FACES
    namen = list(flaechen)
    for name in koerper:
        k = model.koerper.get(name)
        if k is not None:
            namen += [n for n in (k.flaechen or []) if n not in namen]
    tris = []
    for name in namen:
        f = model.flaechen.get(name)
        if f is None:
            continue
        hat_netz = False
        for e in f.elemente or []:
            if not 0 <= int(e) < len(model.elements):
                continue
            el = model.elements[int(e)]
            X = model.nodes[[int(n) for n in el.nodes]]
            if el.typ in ("shell3", "shell4"):
                hat_netz = True
                tris.append(X[[0, 1, 2]])
                if el.typ == "shell4":
                    tris.append(X[[0, 2, 3]])
        for e, seite in f.randseiten or []:
            if not 0 <= int(e) < len(model.elements):
                continue
            el = model.elements[int(e)]
            seiten = SOLID_FACES.get(el.typ)
            if not seiten:
                continue
            nd = seiten[int(seite) % len(seiten)]
            P = model.nodes[[int(el.nodes[j]) for j in nd]]
            hat_netz = True
            for j in range(1, len(P) - 1):
                tris.append(P[[0, j, j + 1]])
        if not hat_netz:
            try:
                P = np.asarray(f.randpunkte(model, teilung), float)
            except Exception:                    # noqa: BLE001
                P = np.zeros((0, 3))
            if len(P) >= 3:
                c = P.mean(axis=0)
                for j in range(len(P)):
                    tris.append(np.array([c, P[j], P[(j + 1) % len(P)]]))
    return tris


def rastern(schnitt: Schnitt, dreiecke, fortschritt=None, text: str = "Geometrie rastern") -> np.ndarray:
    """Belegte Zellen (nz, nx) der in die Ebene projizierten Dreiecke: Kanten
    dicht abgetastet, dazu die Zellmitten im Inneren grosser Dreiecke."""
    nz, nx, h = schnitt.nz, schnitt.nx, schnitt.h
    b = np.zeros((nz, nx), bool)
    n = len(dreiecke)
    for t, T in enumerate(dreiecke):
        x, z = schnitt.xz(T)
        # Kanten
        for a in range(3):
            x0, z0, x1, z1 = x[a], z[a], x[(a + 1) % 3], z[(a + 1) % 3]
            L = math.hypot(x1 - x0, z1 - z0)
            ns = max(2, int(L / (0.4 * h)) + 2)
            ts = np.linspace(0.0, 1.0, ns)
            i, k = schnitt.zelle(x0 + ts * (x1 - x0), z0 + ts * (z1 - z0))
            ok = schnitt.drin(i, k)
            b[k[ok], i[ok]] = True
        # Inneres
        i0, k0 = schnitt.zelle(x.min(), z.min())
        i1, k1 = schnitt.zelle(x.max(), z.max())
        i0, i1 = max(int(i0), 0), min(int(i1), nx - 1)
        k0, k1 = max(int(k0), 0), min(int(k1), nz - 1)
        if i1 - i0 >= 1 and k1 - k0 >= 1:
            xc = (np.arange(i0, i1 + 1) + 0.5) * h
            zc = (np.arange(k0, k1 + 1) + 0.5) * h
            XC, ZC = np.meshgrid(xc, zc)
            d = (x[1] - x[0]) * (z[2] - z[0]) - (x[2] - x[0]) * (z[1] - z[0])
            if abs(d) > 1e-14:
                l1 = ((x[1] - XC) * (z[2] - ZC) - (x[2] - XC) * (z[1] - ZC)) / d
                l2 = ((x[2] - XC) * (z[0] - ZC) - (x[0] - XC) * (z[2] - ZC)) / d
                l3 = 1.0 - l1 - l2
                tol = -1e-9
                innen = (l1 >= tol) & (l2 >= tol) & (l3 >= tol)
                b[k0:k1 + 1, i0:i1 + 1] |= innen
        if fortschritt is not None and (t % 2000 == 0 or t == n - 1):
            _melden(fortschritt, (t + 1) / max(1, n), f"{text} ({t + 1}/{n} Dreiecke)")
    return b


def verdicken(b: np.ndarray) -> np.ndarray:
    """Belegung um eine Zelle nach links und rechts erweitern - so wird aus
    einer nur diagonal zusammenhängenden (dünnen, schrägen) Wand eine dichte;
    nach oben und unten bleibt sie, wie sie ist, damit Krone und Öffnung
    unter dem Verschluss ihre Höhe behalten."""
    out = b.copy()
    out[:, 1:] |= b[:, :-1]
    out[:, :-1] |= b[:, 1:]
    return out


def _randfluss(fluss: np.ndarray, Z: np.ndarray, h: float, ks, i: int, z_von: float, z_bis: float,
               q: float, vorzeichen: float = 1.0) -> float:
    """Einen Durchfluss q [m³/(s·m)] auf die Zellen ``ks`` der Spalte ``i``
    legen, anteilig nach ihrer Überdeckung mit dem Band z_von … z_bis: die
    Geschwindigkeit ist dann q / Bandhöhe und in allen Zellen gleich - so wird
    ein Strahl, der nicht auf die Zellteilung passt, nicht zu schnell.
    Rückgabe: die Geschwindigkeit (0, wenn keine Zelle das Band trifft)."""
    ks = np.asarray(ks, int)
    if not len(ks) or q <= 0 or z_bis <= z_von:
        return 0.0
    unten = np.maximum(Z[ks, i] - 0.5 * h, z_von)
    oben = np.minimum(Z[ks, i] + 0.5 * h, z_bis)
    anteil = np.clip((oben - unten) / h, 0.0, 1.0)
    A = float(anteil.sum()) * h
    if A <= 1e-12:
        return 0.0
    v = q / A
    fluss[ks, i] += vorzeichen * v * anteil * h
    return v


# ==========================================================================
# Potentialströmung
# ==========================================================================
def potential(fluid: np.ndarray, fluss: np.ndarray, fortschritt=None) -> np.ndarray:
    """Δφ = 0 auf den Fluidzellen (Finite Volumen): je Zelle
    Σ_Nachbarn (φ_N − φ_P) + ``fluss``[P] = 0, wobei ``fluss`` die Summe der
    vorgegebenen **nach aussen** gerichteten Randgeschwindigkeiten mal h ist
    (Zufluss negativ); v = ∇φ. Undurchlässige und leere Zellen: kein Fluss.
    Je zusammenhängendem Gebiet wird eine Zelle auf φ = 0 gesetzt."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    from scipy import ndimage

    nz, nx = fluid.shape
    idx = -np.ones((nz, nx), int)
    N = int(fluid.sum())
    if N == 0:
        return np.full((nz, nx), np.nan)
    idx[fluid] = np.arange(N)
    rows, cols, vals = [], [], []
    diag = np.zeros(N)
    for dk, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        P = np.zeros((nz, nx), bool)
        Q = np.zeros((nz, nx), bool)
        ks = slice(max(0, -dk), nz - max(0, dk))
        kn = slice(max(0, dk), nz + min(0, dk))
        is_ = slice(max(0, -di), nx - max(0, di))
        in_ = slice(max(0, di), nx + min(0, di))
        both = fluid[ks, is_] & fluid[kn, in_]
        P[ks, is_] = both
        Q[kn, in_] = both
        a = idx[P]
        b = idx[Q]
        rows.append(a)
        cols.append(b)
        vals.append(np.ones(len(a)))
        np.add.at(diag, a, -1.0)
    rows.append(np.arange(N))
    cols.append(np.arange(N))
    vals.append(diag)
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(N, N))
    b = -np.asarray(fluss, float)[fluid]
    # je Gebiet eine Zelle festhalten
    marken, n_geb = ndimage.label(fluid)
    A = A.tolil()
    for g in range(1, n_geb + 1):
        zellen = np.flatnonzero((marken == g)[fluid])
        if not len(zellen):
            continue
        p0 = int(zellen[0])
        A.rows[p0] = [p0]
        A.data[p0] = [1.0]
        b[p0] = 0.0
    _melden(fortschritt, 0.0, f"Potentialströmung: {N} Zellen lösen")
    phi_v = spla.spsolve(A.tocsc(), b)
    phi = np.full((nz, nx), np.nan)
    phi[fluid] = phi_v
    return phi


def geschwindigkeit(phi: np.ndarray, fluid: np.ndarray, h: float):
    """(u, w) an den Zellmitten aus φ: zentral, am Rand einseitig, sonst 0."""
    nz, nx = fluid.shape
    ph = np.where(fluid, phi, 0.0)
    u = np.zeros((nz, nx))
    w = np.zeros((nz, nx))
    fr = np.zeros((nz, nx), bool)
    fl = np.zeros((nz, nx), bool)
    fr[:, :-1] = fluid[:, 1:]
    fl[:, 1:] = fluid[:, :-1]
    r = np.zeros((nz, nx))
    l = np.zeros((nz, nx))
    r[:, :-1] = ph[:, 1:]
    l[:, 1:] = ph[:, :-1]
    beide = fluid & fr & fl
    u[beide] = (r[beide] - l[beide]) / (2 * h)
    nur_r = fluid & fr & ~fl
    u[nur_r] = (r[nur_r] - ph[nur_r]) / h
    nur_l = fluid & fl & ~fr
    u[nur_l] = (ph[nur_l] - l[nur_l]) / h
    fo = np.zeros((nz, nx), bool)
    fu = np.zeros((nz, nx), bool)
    fo[:-1, :] = fluid[1:, :]
    fu[1:, :] = fluid[:-1, :]
    o = np.zeros((nz, nx))
    un = np.zeros((nz, nx))
    o[:-1, :] = ph[1:, :]
    un[1:, :] = ph[:-1, :]
    beide = fluid & fo & fu
    w[beide] = (o[beide] - un[beide]) / (2 * h)
    nur_o = fluid & fo & ~fu
    w[nur_o] = (o[nur_o] - ph[nur_o]) / h
    nur_u = fluid & fu & ~fo
    w[nur_u] = (ph[nur_u] - un[nur_u]) / h
    return u, w


def wasserdruck_feld(schnitt: Schnitt, verschluss: np.ndarray, *, h_ow: float, h_uw, z_uk: float,
                     z_ok: float, ueberstroemt: bool = False, unterstroemt: bool = False,
                     spalt: float = 0.0, mu_ue: float = 0.62, mu_a: float = 0.61,
                     rho: float = 1000.0, unterdruck: bool = False, fortschritt=None) -> dict:
    """Druckfeld um einen Verschluss (Potentialströmung im lotrechten Schnitt).

    Alle Höhen sind **relativ zur Sohle** (z' = 0 ist die Sohle = untere
    Gitterkante): ``h_ow``, ``h_uw`` (None = trocken), ``z_uk`` (Dichtung),
    ``z_ok`` (Oberkante). ``verschluss`` ist die gerasterte (und verdickte)
    Belegung des Verschlusses. Zufluss links, Abfluss über die Krone
    (Überfall, Poleni) und/oder unter dem Verschluss (Ausfluss, Torricelli)
    oder am rechten Rand, wenn das Unterwasser den Strahl ertränkt.
    """
    nz, nx, h = schnitt.nz, schnitt.nx, schnitt.h
    X, Z = schnitt.mitten()
    spalten = np.flatnonzero(verschluss.any(axis=0))
    if not len(spalten):
        raise ValueError("Der Verschluss liegt nicht im Schnitt - benetzte Flächen prüfen")
    i0, i1 = int(spalten.min()), int(spalten.max())
    block = verschluss.copy()
    gate = slice(i0, i1 + 1)
    # Schwelle unter der Dichtung, wenn nicht unterströmt; Wand über der
    # Oberkante, wenn nicht überströmt (sonst liefe das Wasser oben drüber)
    if not unterstroemt:
        block[:, gate] |= Z[:, gate] < z_uk
    if not ueberstroemt:
        block[:, gate] |= Z[:, gate] > z_ok
    nass_uw = h_uw is not None and float(h_uw) > 0.0
    h_uw_ = float(h_uw) if nass_uw else 0.0
    nappe = bool(ueberstroemt) and h_ow > z_ok
    h_ue = max(0.0, h_ow - z_ok) if nappe else 0.0
    h_c = 2.0 / 3.0 * h_ue
    # Krone im Raster: Oberkante der belegten Verschlusszellen
    krone = float(Z[:, gate][verschluss[:, gate]].max()) + 0.5 * h if verschluss[:, gate].any() else z_ok
    deckel = np.full(nx, float(h_ow))
    if nappe:
        deckel[gate] = krone + h_c
    deckel[i1 + 1:] = h_uw_ if nass_uw else -1.0
    fluid = ~block & (Z < deckel[None, :])
    # Abfluesse
    a = float(spalt) if unterstroemt else 0.0
    strahl = mu_a * a
    q_ue = 2.0 / 3.0 * mu_ue * math.sqrt(2 * G) * h_ue ** 1.5 if nappe else 0.0
    unten = max(strahl, h_uw_)
    dh = max(0.0, h_ow - unten) if a > 0 else 0.0
    v_a = math.sqrt(2 * G * dh)
    q_a = mu_a * a * v_a if a > 0 else 0.0
    q = q_ue + q_a
    fluss = np.zeros((nz, nx))
    # Zufluss links, gleichmaessig ueber die Wassertiefe
    ein = np.flatnonzero(fluid[:, 0])
    U = _randfluss(fluss, Z, h, ein, 0, 0.0, float(h_ow), q, -1.0) if q > 0 else 0.0
    # Abflussflaechen: rechte Seite der Verschlussspalten gegen Luft (Nappe,
    # freier Strahl) und der rechte Gitterrand
    rest = q
    rechts_luft = np.zeros((nz, nx), bool)
    if i1 + 1 < nx:
        rechts_luft[:, i1] = fluid[:, i1] & ~fluid[:, i1 + 1]
    oben = np.flatnonzero(rechts_luft[:, i1] & (Z[:, i1] > krone - h))                # Nappe
    unten_k = np.flatnonzero(rechts_luft[:, i1] & (Z[:, i1] - 0.5 * h < strahl))      # freier Strahl
    if nappe and len(oben) and q_ue > 0:
        if _randfluss(fluss, Z, h, oben, i1, krone, krone + h_c, q_ue) > 0:
            rest -= q_ue
    if a > 0 and len(unten_k) and q_a > 0 and not (nass_uw and h_uw_ > z_uk):
        if _randfluss(fluss, Z, h, unten_k, i1, 0.0, strahl, q_a) > 0:
            rest -= q_a
    aus = np.flatnonzero(fluid[:, nx - 1])
    if rest > 1e-12:
        if len(aus):
            _randfluss(fluss, Z, h, aus, nx - 1, 0.0, float(deckel[nx - 1]), rest)
        elif len(oben) or len(unten_k):
            ziel = np.concatenate([oben, unten_k])
            fluss[ziel, i1] += rest / (len(ziel) * h) * h
        else:
            # kein Auslass: dann fliesst nichts (geschlossener Verschluss)
            fluss[:] = 0.0
            q = U = 0.0
    _melden(fortschritt, 0.05, "Wasserdruck: Gitter aufgebaut")
    phi = potential(fluid, fluss, fortschritt=lambda a_, t_: (fortschritt(0.1 + 0.5 * a_, t_)
                                                              if fortschritt else True))
    _melden(fortschritt, 0.65, "Wasserdruck: Geschwindigkeiten und Druck")
    u, w = geschwindigkeit(phi, fluid, h)
    E_ow = h_ow + U ** 2 / (2 * G)
    v_uw = q / h_uw_ if (nass_uw and q > 0) else 0.0
    E_uw = h_uw_ + v_uw ** 2 / (2 * G) if nass_uw else 0.0
    E = np.where(X <= (i1 + 1) * h, E_ow, E_uw)
    p = rho * G * (E - Z) - 0.5 * rho * (u ** 2 + w ** 2)
    if unterdruck:
        p = np.maximum(p, -0.7e5)
    else:
        p = np.maximum(p, 0.0)
    p[~fluid] = np.nan
    # Kraefte auf den Verschluss je m Breite (Zellseiten Fluid -> Verschluss)
    Fx = Fz = Mx = 0.0
    for dk, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        ks = slice(max(0, -dk), nz - max(0, dk))
        kn = slice(max(0, dk), nz + min(0, dk))
        is_ = slice(max(0, -di), nx - max(0, di))
        in_ = slice(max(0, di), nx + min(0, di))
        seite = fluid[ks, is_] & verschluss[kn, in_]
        pp = np.where(seite, p[ks, is_], 0.0)
        pp = np.nan_to_num(pp)
        Fx += float(pp.sum()) * h * di
        Fz += float(pp.sum()) * h * dk
        if di:
            Mx += float((pp * Z[ks, is_]).sum()) * h * di
    z_R = Mx / Fx if abs(Fx) > 1e-9 else z_uk
    vmag = np.sqrt(u ** 2 + w ** 2)
    vmag[~fluid] = 0.0
    # Druckverlauf auf der Oberwasserseite des Verschlusses: je Zeile die
    # Fluidzelle links vom ersten Verschlussfeld
    profil = []
    for k in range(nz):
        zeile = np.flatnonzero(verschluss[k, :])
        if not len(zeile):
            continue
        i = int(zeile.min()) - 1
        if i >= 0 and fluid[k, i]:
            profil.append((float(Z[k, i]), float(p[k, i])))
    _melden(fortschritt, 0.75, "Wasserdruck: Druckfeld fertig")
    return {"p": p, "u": u, "w": w, "fluid": fluid, "block": block, "verschluss": verschluss,
            "q": q, "q_ue": q_ue, "q_a": q_a, "U": U, "v_a": v_a, "h_ue": h_ue, "h_c": h_c,
            "E_ow": E_ow, "E_uw": E_uw, "v_max": float(vmag.max()) if vmag.size else 0.0,
            "p_max": float(np.nanmax(p)) if np.isfinite(p).any() else 0.0,
            "F_je_m": Fx, "Fz_je_m": Fz, "z_R": z_R, "profil": profil,
            "i_verschluss": (i0, i1), "n_fluid": int(fluid.sum())}


# ==========================================================================
# Gitter-Boltzmann (Wind)
# ==========================================================================
_C = np.array([[0, 0], [1, 0], [0, 1], [-1, 0], [0, -1], [1, 1], [-1, 1], [-1, -1], [1, -1]], int)
_W = np.array([4 / 9] + [1 / 9] * 4 + [1 / 36] * 4)
_GEGEN = np.array([0, 3, 4, 1, 2, 7, 8, 5, 6], int)


def _feq(rho, ux, uz):
    """Gleichgewichtsverteilungen (9, nz, nx)."""
    usq = 1.5 * (ux ** 2 + uz ** 2)
    out = np.empty((9,) + rho.shape)
    for q in range(9):
        cu = 3.0 * (_C[q, 0] * ux + _C[q, 1] * uz)
        out[q] = _W[q] * rho * (1.0 + cu + 0.5 * cu ** 2 - usq)
    return out


def gitter_boltzmann(block: np.ndarray, *, u_lb: float = 0.08, re: float = 150.0, schritte: int = 3000,
                     mittel_ab: float = 0.6, boden: bool = False, fortschritt=None) -> dict:
    """Zweidimensionale Strömung um die belegten Zellen (D2Q9, BGK).

    Links strömt es mit ``u_lb`` (Gittereinheiten) ein, rechts frei aus, oben
    und unten herrscht die freie Anströmung (``boden``: unten eine Wand).
    Die Reynolds-Zahl bezieht sich auf die Querabmessung des Hindernisses;
    für die Stabilität des BGK-Verfahrens wird τ ≥ 0,52 gehalten (die
    wirksame Reynolds-Zahl steht in ``re``). Gemittelt wird ab dem Anteil
    ``mittel_ab`` der Schritte; Rückgabe ``cp`` = (p − p_∞)/(½·ρ·u_∞²) je
    Zelle, dazu die gemittelten Geschwindigkeiten und das Momentanbild.
    """
    nz, nx = block.shape
    block = block.copy()
    if boden:
        block[0, :] = True
    zeilen = np.flatnonzero(block[:, :].any(axis=1))
    L = float(zeilen.max() - zeilen.min() + 1) if len(zeilen) else float(nz)
    nu = u_lb * L / max(float(re), 1.0)
    tau = 3.0 * nu + 0.5
    if tau < 0.52:
        tau = 0.52
        nu = (tau - 0.5) / 3.0
    re_eff = u_lb * L / nu
    omega = 1.0 / tau
    rho = np.ones((nz, nx))
    ux = np.full((nz, nx), u_lb)
    uz = np.zeros((nz, nx))
    ux[block] = 0.0
    f = _feq(rho, ux, uz)
    ein = _feq(np.ones(nz), np.full(nz, u_lb), np.zeros(nz))    # (9, nz)
    n_mittel = 0
    rho_m = np.zeros((nz, nx))
    ux_m = np.zeros((nz, nx))
    uz_m = np.zeros((nz, nx))
    start = int(max(1, mittel_ab * schritte))
    for n in range(int(schritte)):
        rho = f.sum(axis=0)
        ux = (f[1] - f[3] + f[5] - f[6] - f[7] + f[8]) / rho
        uz = (f[2] - f[4] + f[5] + f[6] - f[7] - f[8]) / rho
        ux[block] = 0.0
        uz[block] = 0.0
        feq = _feq(rho, ux, uz)
        fneu = f - omega * (f - feq)
        # Haftbedingung: Rueckprall an belegten Zellen
        fneu[:, block] = f[_GEGEN][:, block]
        # Stroemen
        for q in range(9):
            fneu[q] = np.roll(np.roll(fneu[q], _C[q, 1], axis=0), _C[q, 0], axis=1)
        # Raender: links Zustrom, rechts Ausstrom (kopiert), oben/unten frei
        fneu[:, :, 0] = ein
        fneu[:, :, nx - 1] = fneu[:, :, nx - 2]
        rand_o = _feq(fneu[:, nz - 1, :].sum(axis=0), np.full(nx, u_lb), np.zeros(nx))
        fneu[:, nz - 1, :] = rand_o
        if not boden:
            rand_u = _feq(fneu[:, 0, :].sum(axis=0), np.full(nx, u_lb), np.zeros(nx))
            fneu[:, 0, :] = rand_u
        f = fneu
        if not np.isfinite(f).all():
            raise ValueError("Gitter-Boltzmann-Rechnung instabil - Reynolds-Zahl verringern oder "
                             "Gitter vergröbern")
        if n >= start:
            rho_m += rho
            ux_m += ux
            uz_m += uz
            n_mittel += 1
        if fortschritt is not None and (n % 25 == 0 or n == schritte - 1):
            _melden(fortschritt, (n + 1) / schritte, f"Windkanal: Schritt {n + 1} von {schritte}")
    if n_mittel:
        rho_m /= n_mittel
        ux_m /= n_mittel
        uz_m /= n_mittel
    else:
        rho_m, ux_m, uz_m = rho, ux, uz
    # Bezugsdruck: Zustrom weit vorn
    rho_ref = float(rho_m[:, 2].mean())
    cp = (rho_m - rho_ref) / 3.0 / (0.5 * u_lb ** 2)
    cp[block] = np.nan
    return {"cp": cp, "ux": ux_m / u_lb, "uz": uz_m / u_lb, "ux_jetzt": ux / u_lb, "uz_jetzt": uz / u_lb,
            "block": block, "tau": tau, "re": re_eff, "schritte": int(schritte), "u_lb": u_lb, "L": L}


# ==========================================================================
# Abtastung am Punkt
# ==========================================================================
def wert_am_punkt(feld: np.ndarray, fluid: np.ndarray, schnitt: Schnitt, punkt, normale=None,
                  beidseitig: bool = False, reichweite: int = 3):
    """Feldwert an einem Weltpunkt: entlang der Flächennormale 1,5 … 3,5
    Zellen vor die Fläche gehen und die erste Fluidzelle nehmen; mit
    ``beidseitig`` (dünne Schale) die Rückseite abziehen - das Ergebnis ist
    der Nettodruck gegen die Normale. Ohne Normale die nächste Fluidzelle im
    Umkreis. Rückgabe 0.0, wo kein Fluid ist."""
    x, z = schnitt.xz(np.asarray(punkt, float).reshape(1, 3))
    x, z = float(x[0]), float(z[0])
    h = schnitt.h
    nz, nx = fluid.shape

    def zelle(xx, zz):
        i, k = schnitt.zelle(xx, zz)
        i, k = int(i), int(k)
        if 0 <= i < nx and 0 <= k < nz and fluid[k, i] and np.isfinite(feld[k, i]):
            return float(feld[k, i])
        return None

    nxz = None
    if normale is not None:
        n = np.asarray(normale, float).ravel()[:3]
        nxz = np.array([n @ np.asarray(schnitt.ex), n @ np.asarray(schnitt.ez)])
        L = float(np.linalg.norm(nxz))
        nxz = nxz / L if L > 0.3 else None

    def entlang(vorz: float):
        for s in (1.5, 2.5, 3.5):
            v = zelle(x + vorz * s * h * nxz[0], z + vorz * s * h * nxz[1])
            if v is not None:
                return v
        return None

    if nxz is not None:
        vorn = entlang(1.0)
        hinten = entlang(-1.0) if beidseitig else None
        if vorn is None and hinten is None:
            return 0.0
        return (vorn or 0.0) - (hinten or 0.0)
    # ohne Normale: naechste Fluidzelle
    i0, k0 = schnitt.zelle(x, z)
    i0, k0 = int(i0), int(k0)
    best, bestd = None, None
    for dk in range(-reichweite, reichweite + 1):
        for di in range(-reichweite, reichweite + 1):
            i, k = i0 + di, k0 + dk
            if 0 <= i < nx and 0 <= k < nz and fluid[k, i] and np.isfinite(feld[k, i]):
                d = di * di + dk * dk
                if bestd is None or d < bestd:
                    best, bestd = float(feld[k, i]), d
    return best if best is not None else 0.0


# ==========================================================================
# Speichern und Bild
# ==========================================================================
def feld_packen(schnitt: Schnitt, feld: np.ndarray, fluid: np.ndarray, block: np.ndarray,
                nachkomma: int = 1, **extra) -> dict:
    """Feld und Masken als JSON-taugliches dict (NaN -> None, Masken als Zeilen
    aus 0/1-Zeichen)."""
    werte = np.where(np.isfinite(feld), np.round(feld, nachkomma), np.nan)
    p = [[None if not np.isfinite(v) else float(v) for v in zeile] for zeile in werte]
    d = {"schnitt": schnitt.to_dict(), "p": p,
         "fluid": ["".join("1" if v else "0" for v in zeile) for zeile in fluid],
         "block": ["".join("1" if v else "0" for v in zeile) for zeile in block]}
    d.update(extra)
    return d


def feld_entpacken(d: dict):
    """Umkehrung von :func:`feld_packen`: (Schnitt, feld, fluid, block)."""
    schnitt = Schnitt.from_dict(d["schnitt"])
    p = np.array([[np.nan if v is None else float(v) for v in zeile] for zeile in d["p"]], float)
    fluid = np.array([[c == "1" for c in zeile] for zeile in d["fluid"]], bool)
    block = np.array([[c == "1" for c in zeile] for zeile in d["block"]], bool)
    return schnitt, p, fluid, block


def _png_base64(rgb: np.ndarray) -> str:
    """PNG (RGB, 8 Bit) ohne Fremdpaket - base64 fuer ein data:-URI."""
    H, W, _ = rgb.shape
    roh = b"".join(b"\x00" + rgb[y].astype(np.uint8).tobytes() for y in range(H))

    def chunk(art: bytes, daten: bytes) -> bytes:
        c = struct.pack(">I", len(daten)) + art + daten
        return c + struct.pack(">I", zlib.crc32(art + daten) & 0xffffffff)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(roh, 9)) + chunk(b"IEND", b""))
    return base64.b64encode(png).decode("ascii")


def _farbe(t: float, art: str) -> tuple:
    """Farbe (0..255) zu t in [0, 1]: Wasser blau -> weiss -> rot, Wind
    (c_p) blau (Sog) -> weiss -> rot (Druck)."""
    t = min(1.0, max(0.0, float(t)))
    if art == "wasser":
        stuetz = [(0.0, (225, 238, 250)), (0.5, (120, 170, 230)), (1.0, (200, 40, 30))]
    else:
        stuetz = [(0.0, (30, 80, 200)), (0.5, (245, 245, 245)), (1.0, (200, 40, 30))]
    for (t0, c0), (t1, c1) in zip(stuetz[:-1], stuetz[1:]):
        if t <= t1:
            a = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return tuple(int(round(c0[j] + a * (c1[j] - c0[j]))) for j in range(3))
    return stuetz[-1][1]


def feld_svg(schnitt: Schnitt, feld: np.ndarray, fluid: np.ndarray, block: np.ndarray, art: str = "wasser",
             breite: int = 620, titel: str = "", einheit: str = "kN/m²", faktor: float = 1e-3,
             grenzen=None, linien: list = None, texte: list = None) -> str:
    """Das Feld als Bild fuer den Bericht: Rasterbild (PNG im SVG) mit
    Farbskala, belegte Zellen dunkel, leere weiss; dazu Linien
    [((x1, z1), (x2, z2), Farbe), ...] und Texte [((x, z), Text, Farbe), ...]
    in Ebenenkoordinaten."""
    nz, nx = feld.shape
    werte = np.where(np.isfinite(feld) & fluid, feld, np.nan)
    if grenzen is None:
        lo = float(np.nanmin(werte)) if np.isfinite(werte).any() else 0.0
        hi = float(np.nanmax(werte)) if np.isfinite(werte).any() else 1.0
        if art != "wasser":
            m = max(abs(lo), abs(hi), 1e-9)
            lo, hi = -m, m
    else:
        lo, hi = float(grenzen[0]), float(grenzen[1])
    if hi - lo < 1e-12:
        hi = lo + 1.0
    rgb = np.full((nz, nx, 3), 255, np.uint8)
    t = (werte - lo) / (hi - lo)
    for k in range(nz):
        for i in range(nx):
            if block[k, i]:
                rgb[k, i] = (60, 60, 60)
            elif np.isfinite(t[k, i]):
                rgb[k, i] = _farbe(t[k, i], art)
    rgb = rgb[::-1]                      # z' nach oben
    bild = _png_base64(rgb)
    rand, skala = 34, 26
    sx = (breite - 2 * rand - skala - 40) / max(1, nx)
    sz = sx
    hoehe = int(nz * sz + 2 * rand + 22)
    ox, oz = rand, rand + (12 if titel else 0)

    def X(x):
        return ox + x / schnitt.h * sx

    def Y(z):
        return oz + (nz - z / schnitt.h) * sz

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
         f'width="{breite}" height="{hoehe + (12 if titel else 0)}" viewBox="0 0 {breite} {hoehe + (12 if titel else 0)}" '
         f'font-family="sans-serif" font-size="11">',
         f'<rect width="{breite}" height="{hoehe + (12 if titel else 0)}" fill="#fff"/>']
    if titel:
        s.append(f'<text x="{rand}" y="16" font-weight="bold">{titel}</text>')
    s.append(f'<image x="{ox}" y="{oz}" width="{nx * sx:.1f}" height="{nz * sz:.1f}" '
             f'style="image-rendering: pixelated; image-rendering: crisp-edges" '
             f'xlink:href="data:image/png;base64,{bild}"/>')
    s.append(f'<rect x="{ox}" y="{oz}" width="{nx * sx:.1f}" height="{nz * sz:.1f}" fill="none" stroke="#888"/>')
    for (a, b, farbe) in (linien or []):
        s.append(f'<line x1="{X(a[0]):.1f}" y1="{Y(a[1]):.1f}" x2="{X(b[0]):.1f}" y2="{Y(b[1]):.1f}" '
                 f'stroke="{farbe}" stroke-width="1.5"/>')
    for (q, text, farbe) in (texte or []):
        s.append(f'<text x="{X(q[0]) + 3:.1f}" y="{Y(q[1]) - 3:.1f}" fill="{farbe}">{text}</text>')
    # Farbskala rechts
    x0 = ox + nx * sx + 12
    n_st = 40
    for j in range(n_st):
        tt = 1.0 - j / (n_st - 1)
        c = _farbe(tt, art)
        y = oz + j * (nz * sz) / n_st
        s.append(f'<rect x="{x0}" y="{y:.1f}" width="{skala - 8}" height="{(nz * sz) / n_st + 0.5:.1f}" '
                 f'fill="rgb({c[0]},{c[1]},{c[2]})"/>')
    for tt, lab in ((1.0, hi), (0.5, 0.5 * (lo + hi)), (0.0, lo)):
        y = oz + (1.0 - tt) * nz * sz
        s.append(f'<text x="{x0 + skala - 4}" y="{y + 4:.1f}" font-size="10">{lab * faktor:.1f}</text>')
    s.append(f'<text x="{x0}" y="{oz + nz * sz + 14:.1f}" font-size="10">{einheit}</text>')
    s.append(f'<text x="{ox}" y="{oz + nz * sz + 14:.1f}" font-size="10">Gitter {nx} × {nz}, h = {schnitt.h:.3g} m</text>')
    s.append('</svg>')
    return "\n".join(s)
