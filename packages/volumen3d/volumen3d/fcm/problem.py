"""FcmProblem: Geometrie + Gitter + Werkstoff + Raender + Lasten -> K, F -> Loesung.

Interne Schnittstelle des Volumenmoduls; ``api.FcmSolver`` setzt die Vertragstypen darauf
um. Alle Groessen in mm, N, N/mm2.
"""
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import scipy.sparse as sp

from ..geometry.oberflaeche import Flaechenquadratur

if TYPE_CHECKING:
    from ..postprocess.auswertung import Auswertung
from ..linalg.direkt import Direktloeser
from . import rand
from .aggregation import Zellaggregation
from .elastizitaet import assemblieren
from .gitter import CUT, Gitter, Verfeinerung
from .quadratur import Zellquadratur
from .zwaenge import Zwaenge


@dataclass(frozen=True)
class Werkstoff:
    E: float
    nu: float
    rho: float = 0.0          # kg/mm^3


@dataclass
class Verschiebungsrand:
    """projektion: 'voll' (alle Komponenten punktweise), 'normal' (Symmetrie, Gleitlager) oder
    'schnitt' (Normalkomponente punktweise + Starrkoerpermittelwerte in der Ebene, fuer die
    Kopplung an Stabquerschnitte, siehe rand.starrkoerper_moden)."""
    name: str
    quadratur: Flaechenquadratur
    projektion: str = "voll"
    moden: np.ndarray | None = None         # (nq,3,3) bei 'schnitt'
    zwang_start: int = -1                   # Zeile der Multiplikatoren im erweiterten System


class FcmProblem:
    def __init__(self, geometrie, h: float, p: int, werkstoff: Werkstoff, alpha: float = 1e-8, tiefe: int = 2,
                 polster: float = 0.1, beta_faktor: float = 10.0, facette_mm: float | None = None,
                 ordnung_flaeche: int | None = None, aggregation: float | None = 0.25,
                 verfeinerung: Verfeinerung | None = None) -> None:
        if not 1 <= p <= 4:
            raise ValueError("p muss zwischen 1 und 4 liegen")
        self.geometrie = geometrie
        self.p = int(p)
        self.werkstoff = werkstoff
        self.alpha = float(alpha)
        self.tiefe = int(tiefe)
        self.beta_faktor = float(beta_faktor)
        self.verfeinerung = verfeinerung or Verfeinerung()
        # Gitter, Quadratur, Aggregation - und noch einmal, wenn die Aggregation Zellen teilen
        # muss (schlecht geschnitten, alle wohlgestellten Nachbarn feiner: eine feinere Wurzel
        # ergaebe Zwangszyklen, Entwurf 4b.2). Die Kinder liegen dann auf der Ebene der Nachbarn.
        zwang: tuple = tuple(self.verfeinerung.zellen)
        self.wurzel_teilungen = 0
        for runde in range(4):
            v = dataclasses.replace(self.verfeinerung, zellen=zwang) if zwang else self.verfeinerung
            self.gitter = Gitter(geometrie, h, polster, v)
            self.gitter.moden_nummerieren(self.p)
            self.quadratur = Zellquadratur(self.gitter, self.p, self.tiefe, self.alpha)
            # Zellaggregation (Vorgabe 8.3): Moden schlecht geschnittener Zellen an die Fortsetzung
            # des Nachbarpolynoms binden; None/0 = aus (nur zum Messen des alpha-Effekts)
            self.aggregation = Zellaggregation(self.gitter, self.quadratur, aggregation) if aggregation else None
            if self.aggregation is None or not self.aggregation.zu_teilen or runde == 3:
                break
            zwang = zwang + tuple(self.aggregation.zu_teilen)
            self.wurzel_teilungen += len(self.aggregation.zu_teilen)
        self.verfeinerung = v
        if self.aggregation is not None:
            # Mit Aggregation braucht alpha nur noch, was keine Wurzel hat (isolierte Splitter):
            # gebundene Zellen wuerden alpha auf die extrapolierten Wurzelmoden wirken lassen, und
            # in wohlgestellten Zellen tragen hohe Moden nur ~Anteil^(2p+1) ihrer Energie im
            # Werkstoff (0,28^7 = 1e-4 bei p = 3), sodass alpha = 1e-8 dort 1e-4 Fehler macht
            # (Patch-Test 27.09.2026). Ohne alpha ist die Rechnung fuer lineare Felder exakt.
            ag = self.aggregation
            behalten = ag.schlecht & (ag.wurzel < 0)
            self.quadratur.alpha_entfernen(np.flatnonzero((self.gitter.klasse == CUT) & ~behalten))
        # haengende Freiheitsgrade des Oktrees und Aggregation in einer Zwangsmatrix
        self.zwaenge = Zwaenge(self.gitter, self.aggregation)
        # int (sigma n).v exakt fuer v vom Tensorgrad p (Gesamtgrad 3p auf der Flaeche): 2n-1 >= 3p
        self.ordnung_flaeche = ordnung_flaeche or int(np.ceil((3 * self.p + 1) / 2))
        self.facette_mm = facette_mm
        self.oberflaeche = Flaechenquadratur.aus_geometrie(geometrie, self.gitter, self.ordnung_flaeche,
                                                           facette_mm=facette_mm, tiefe=self.tiefe)
        self.raender: dict[str, Verschiebungsrand] = {}
        self.lasten: list[np.ndarray] = []
        self.K: sp.csr_matrix | None = None
        self._loeser: Direktloeser | None = None
        self.protokoll: dict = {}

    # -- Raender und Lasten ------------------------------------------------------------
    @property
    def beta(self) -> float:
        return self.beta_faktor * self.werkstoff.E * self.p ** 2 / self.gitter.h

    def flaeche(self, namen) -> Flaechenquadratur:
        """Oberflaechenquadratur der genannten Grundformen (None = gesamte Oberflaeche)."""
        if namen is None:
            return self.oberflaeche
        namen = [namen] if isinstance(namen, str) else list(namen)
        return self.oberflaeche.auswahl(np.isin(self.oberflaeche.name.astype(str), namen))

    def verschiebungsrand(self, name: str, flaechen, projektion: str = "voll",
                          quadratur: Flaechenquadratur | None = None) -> None:
        fq = quadratur if quadratur is not None else self.flaeche(flaechen)
        if len(fq.punkte) == 0:
            raise ValueError(f"Verschiebungsrand {name!r}: keine Oberflaechenpunkte gefunden "
                             f"(Flaechen {flaechen!r}; vorhanden: {sorted(set(self.oberflaeche.name.astype(str)))})")
        if projektion == "schnitt":
            moden, _, _ = rand.starrkoerper_moden(fq)
            self.raender[name] = Verschiebungsrand(name, fq, projektion, moden)
        else:
            rand.projektionen(projektion, fq.normalen[:1])      # prueft die Art
            self.raender[name] = Verschiebungsrand(name, fq, projektion)
        self.K = None

    def traktion(self, flaechen, t, quadratur: Flaechenquadratur | None = None) -> None:
        fq = quadratur if quadratur is not None else self.flaeche(flaechen)
        if len(fq.punkte) == 0:
            raise ValueError(f"Traktion: keine Oberflaechenpunkte fuer {flaechen!r}")
        T = t(fq.punkte, fq.normalen) if callable(t) else np.broadcast_to(np.asarray(t, float), (len(fq.punkte), 3))
        self.lasten.append(rand.flaechenlast(self.gitter, fq, np.asarray(T, float)))

    def druck(self, flaechen, p_druck: float, quadratur: Flaechenquadratur | None = None) -> None:
        """Druck positiv = auf die Flaeche drueckend: t = -p n."""
        self.traktion(flaechen, lambda P, N: -float(p_druck) * N, quadratur)

    def volumenlast(self, b) -> None:
        self.lasten.append(rand.volumenlast(self.gitter, self.quadratur, np.asarray(b, float)))

    # -- Aufbau und Loesung -----------------------------------------------------------
    def aufbauen(self, fortschritt=None) -> None:
        t0 = time.perf_counter()
        K = assemblieren(self.gitter, self.quadratur, self.werkstoff.E, self.werkstoff.nu, fortschritt)
        n = self.gitter.n_dof
        K_rand: sp.csr_matrix = sp.csr_matrix((n, n))              # Nitsche-Anteil getrennt: der matrixfreie
        zwaenge = []                                                # Operator (TP 3) addiert ihn zur Zellsumme
        for r in self.raender.values():
            art = "normal" if r.projektion == "schnitt" else r.projektion
            K_rand = K_rand + rand.nitsche_steifigkeit(self.gitter, r.quadratur, self.werkstoff.E, self.werkstoff.nu,
                                                       self.beta_faktor, art).tocsr()
            if r.projektion == "schnitt":
                r.zwang_start = sum(len(z) for z in zwaenge)
                zwaenge.append(rand.mittelwert_zwaenge(self.gitter, r.quadratur, r.moden))
        K = (K + K_rand).tocsr()
        self.K = K
        self.K_rand = K_rand
        self._B = np.concatenate(zwaenge, axis=0) if zwaenge else None
        t1 = time.perf_counter()
        C = self.zwaenge.C
        K_red = (C.T @ K @ C).tocsr()
        if self._B is not None:
            # Sattelpunkt [[K, B^T], [B, 0]]: Multiplikatoren = Resultierende der Mittelwertzwaenge
            B_red = sp.csr_matrix(self._B @ C)
            nz = B_red.shape[0]
            K_red = sp.bmat([[K_red, B_red.T], [B_red, sp.csr_matrix((nz, nz))]], format="csr")
        self._loeser = Direktloeser(K_red)
        self._K_red = K_red
        self.n_zwaenge = 0 if self._B is None else int(self._B.shape[0])
        t2 = time.perf_counter()
        self.protokoll.update({
            "p": self.p, "h_mm": self.gitter.h, "alpha": self.alpha, "tiefe": self.tiefe,
            "beta": self.beta, "beta_faktor": self.beta_faktor, "ordnung_flaeche": self.ordnung_flaeche,
            "zellen": int(len(self.gitter.ijk)), "cut": int((self.gitter.klasse == CUT).sum()),
            "dofs": int(self.gitter.n_dof), "dofs_frei": int(3 * self.zwaenge.statistik["moden_frei"]), "nnz": int(K.nnz),
            "ebenen": self.gitter.ebenen_verteilung(), "wurzel_teilungen": int(self.wurzel_teilungen),
            "zwaenge": dict(self.zwaenge.statistik),
            "aggregation": dict(self.aggregation.statistik) if self.aggregation is not None else None,
            "quadraturpunkte": self.quadratur.anzahl_punkte(), "quadratur": dict(self.quadratur.statistik),
            "oberflaechenpunkte": int(len(self.oberflaeche.punkte)), "oberflaeche": dict(self.oberflaeche.statistik),
            "loeser": self._loeser.name,
            "t_assemblierung_s": round(t1 - t0, 3), "t_faktorisierung_s": round(t2 - t1, 3)})

    def rechte_seite(self, vorgaben: dict) -> np.ndarray:
        """vorgaben: Randname -> g(P) -> (n,3) oder Feld (n,3) oder Konstante; Lasten kommen immer dazu."""
        f = np.zeros(self.gitter.n_dof)
        for last in self.lasten:
            f = f + last
        d = np.zeros(getattr(self, "n_zwaenge", 0))
        for name, r in self.raender.items():
            g = vorgaben.get(name, 0.0)
            n_p = len(r.quadratur.punkte)
            G = np.asarray(g(r.quadratur.punkte) if callable(g) else np.broadcast_to(np.asarray(g, float), (n_p, 3)), float)
            art = "normal" if r.projektion == "schnitt" else r.projektion
            f = f + rand.nitsche_rechte_seite(self.gitter, r.quadratur, self.werkstoff.E, self.werkstoff.nu,
                                              self.beta_faktor, art, G)
            if r.projektion == "schnitt":
                d[r.zwang_start:r.zwang_start + 3] = rand.mittelwert_vorgabe(r.quadratur, r.moden, G)
        return np.concatenate([f, d]) if len(d) else f

    def loesen(self, vorgaben_je_key) -> np.ndarray:
        """Ein dict (ein Key) oder eine Liste von dicts -> U (n_dof, n_keys). Die Multiplikatoren
        der Schnittebenen (Resultierende in der Ebene) stehen danach in ``self.multiplikatoren``."""
        if self.K is None:
            self.aufbauen()
        liste = vorgaben_je_key if isinstance(vorgaben_je_key, list) else [vorgaben_je_key]
        t0 = time.perf_counter()
        F = np.stack([self.rechte_seite(v) for v in liste], axis=1)
        n = self.gitter.n_dof
        C = self.zwaenge.C
        F_red = np.asarray(C.T @ F[:n])
        if self.n_zwaenge:
            F_red = np.concatenate([F_red, F[n:]], axis=0)
        X = self._loeser.loesen(F_red)
        m = X.shape[0] - self.n_zwaenge
        self.multiplikatoren = X[m:] if self.n_zwaenge else np.zeros((0, len(liste)))
        U = np.asarray(C @ X[:m])
        self.protokoll["t_loesen_s"] = round(time.perf_counter() - t0, 3)
        # Residuum: Direktloeser liefern bei singulaerer Matrix endliche Zahlen (Gutachten 27.09.:
        # freier Quader unter Traktion, max |u| 1e12 mm ohne Fehler); ein relatives Residuum
        # ueber 1e-6 heisst: nicht zuverlaessig geloest, in der Regel freie Starrkoerperbewegung.
        R = self._K_red @ X - F_red
        norm_f = np.linalg.norm(F_red, axis=0)
        norm_r = np.linalg.norm(R, axis=0)
        residuum = np.where(norm_f > 0, norm_r / np.maximum(norm_f, 1e-300), norm_r)
        self.protokoll["residuum"] = float(residuum.max()) if len(residuum) else 0.0
        if not np.all(np.isfinite(U)) or self.protokoll["residuum"] > 1e-6:
            raise ValueError(f"Gleichungssystem nicht zuverlaessig geloest (relatives Residuum "
                             f"{self.protokoll['residuum']:.1e}): freie Starrkoerperbewegung, fehlender "
                             f"Verschiebungsrand oder singulaere Matrix")
        return U

    def auswertung(self, U: np.ndarray) -> "Auswertung":
        from ..postprocess.auswertung import Auswertung
        return Auswertung(self, U)


__all__ = ["Werkstoff", "Verschiebungsrand", "FcmProblem"]
