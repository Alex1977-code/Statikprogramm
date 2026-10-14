"""Weiterverwendung der Zerlegung ueber Kontaktrunden (Kapazitaetsmatrix).

Jede Kontaktrunde loeste bis zum 09.10.2026 mit einer neuen Zerlegung, sobald sich
die Signatur des Kontaktzustands geaendert hatte - auch wenn nur eine Bedingung
oeffnete oder eine Gleitrichtung sich drehte. Am Drehlager (Mittel, 2,6 Mio.
Zeilen) kostet eine Zerlegung rund 100 s, das Loesen mit dem vorhandenen Faktor
6 bis 8 s; 77 bis 82 % der Rechenzeit eines Lastfalls waren Zerlegungen.

Das Sattelpunktsystem einer Runde ist ``[[Kff + E, B^T + D], [B, 0]]``
(StaticSystem.gerandet): ``Kff`` die Grundsteifigkeit, ``E`` alles, was der
Kontakt zum Steifigkeitsblock beitraegt (Kontaktsteifigkeit, Zusatzsteifigkeit,
Augmentierung C^T S C), ``B`` die Randzeilen (Hilfsfesselung, exakte Normal- und
Haftzeilen) und ``D`` die Kopplungsspalten der gleitenden Reibung. Zwischen zwei
Runden aendern sich nur die Bedingungen, die ihren Zustand wechseln: ein kleiner
Block von E auf ihren Freiheitsgraden, ihre Randzeilen (die kommen, gehen oder
eine andere Spalte D bekommen). Die Aenderung hat niedrigen Rang, aber die
Abmessung des Systems wechselt mit der Zahl der Randzeilen.

Weg (Sherman-Morrison-Woodbury in der Form der Kapazitaetsmatrix): Bezug ist die
zuletzt wirklich zerlegte Matrix A0 (die **Basis**). Die Matrix A1 dieser Runde
wird mit A0 in einen gemeinsamen Raum gebettet - Randzeilen, die es nur in A0
gibt, stehen in A1 als Identitaet (Multiplikator 0), neue Zeilen stehen in A0
als Identitaet hinten an. Dann unterscheiden sich beide nur auf der Menge T der
beruehrten Zeilen und Spalten: A1 = A0 + P_T M P_T^T, und

    A1^-1 y = x0 - Z (I + M Z_TT)^-1 M x0_T,   x0 = A0^-1 y,  Z = A0^-1 P_T.

Z sind |T| Loesungen mit dem vorhandenen Faktor (in einem Block); fuer neue
Zeilen ist die Spalte trivial. Die Spalten haengen nur an A0 und am Index, nicht
an der Runde: sie werden je Basis behalten, und eine Runde loest nur die Spalten,
die neu in T kommen. Pendelt die Aktivmenge, sind das keine.

Sicherheit: Die Loesung wird gegen die **neue** Matrix nachiteriert und muss das
Residuum der Basiszerlegung erreichen (hoechstens RESIDUUM, nie mehr als die
eingestellte Schranke). Gelingt das nicht, ist T zu gross, der Speicher zu knapp
oder die Kapazitaetsmatrix schlecht konditioniert (A1 singulaer, wo A0 es nicht
war), wirft die Nachfuehrung :class:`Abgelehnt`, und StaticSystem.solve zerlegt
neu wie bisher. Die Kontaktbedingung selbst bleibt unberuehrt: geloest wird
dasselbe System, nur auf anderem Weg.

Alle Grenzen sind Zahlen des Systems, keine Zeiten: derselbe Lauf nimmt immer
denselben Weg.
"""
from __future__ import annotations

import os

import numpy as np
from scipy import sparse
from scipy import linalg as sla

#: "auto": ab NNZ_FAKTOR_MIN Faktor-Nichtnullen mit PARDISO; "immer": jede Groesse
#: (Pruefungen); "nie": jede geaenderte Signatur zerlegt neu (Stand bis 09.10.2026).
#: Die Umgebungsvariable STATIK3D_NACHFUEHRUNG setzt den Wert beim Laden - so laesst
#: sich jede Pruefsuite mit "immer" gegen "nie" rechnen.
MODUS = os.environ.get("STATIK3D_NACHFUEHRUNG", "").strip().lower()
if MODUS not in ("auto", "immer", "nie"):
    MODUS = "auto"
#: In "auto" erst ab so vielen Nichtnullen des Faktors (iparm 18): darunter dauert
#: eine Zerlegung unter etwa einer Sekunde, und der Weg bleibt bitgleich wie bisher.
#: Gemessen 09.10.2026 (Pendelblock tet10, PARDISO 16 Threads): 2,1e8 Nichtnullen
#: 6,2 s Zerlegung, 0,29 s je Loesung; 5,3e8 Nichtnullen 26,6 s und 0,75 s.
NNZ_FAKTOR_MIN = 5.0e7
#: Hoechstens so viele Spalten Z je Runde neu loesen. Eine weitere Spalte im Block
#: kostet 0,2 bis 0,4 % einer Zerlegung (Messung wie oben: 200 Spalten 45 bis 77 %),
#: unter Fremdlast bis 0,7 %. 200 Spalten kosten also bis etwa eine Zerlegung - sie
#: werden aber behalten: pendelt die Aktivmenge, braucht jede weitere Runde keine
#: neue Spalte (Pendelblock h 0,0625: 260 Spalten je Runde gegen die vorige Runde,
#: gegen eine feste Basis 195 einmal und 33 danach, dann keine mehr).
SPALTEN_NEU_MAX = 200
#: Kehrt die Iteration zu einem Kontaktzustand (Aktivmenge, Haften/Gleiten, Fliessen)
#: zurueck, den sie in den letzten WIEDERKEHR_RUNDEN Runden schon geloest hat (sie
#: pendelt), gilt SPALTEN_NEU_MAX nicht: die Spalten werden in den folgenden Runden
#: wieder gebraucht. Es bleiben T_MAX und der Speicher. Am Pendelblock h 0,0625 brauchte
#: jede Runde 260 Spalten gegen die vorige - mit der festen Grenze wurde jede abgelehnt,
#: neu zerlegt und damit die Basis gewechselt.
WIEDERKEHR_RUNDEN = 8
#: Hoechstens so viele beruehrte Zeilen/Spalten (Groesse der Kapazitaetsmatrix)
T_MAX = 2000
#: Speicher fuer die behaltenen Spalten: hoechstens dieser Anteil am Faktor
#: (8 Byte je Nichtnull), mindestens SPEICHER_MIN. Am Drehlager (Mittel, 4e9
#: Nichtnullen) sind das 8 GB, rund 380 Spalten zu 2,6 Mio. Zeilen.
SPEICHER_ANTEIL = 0.25
SPEICHER_MIN = 512 * 2 ** 20
#: Hoechste Konditionszahl (1-Norm, geschaetzt) der Kapazitaetsmatrix. Darueber ist
#: die neue Matrix (fast) singulaer, und die Loesung haengt an der Rundung: dann wird
#: neu zerlegt, und PARDISO behandelt die Matrix wie bisher (gestoerte Pivots). Die
#: Platzhalter weggefallener und neuer Zeilen stehen dafuer in der Groesse ihrer Zeile
#: (Basis.nachfuehren); mit 1 lag die Kondition am Pendelblock bei 1e10 bis 1e20,
#: obwohl die neue Matrix regulaer war. Eine doppelte Zeile ergibt 7,7e17.
KONDITION_MAX = 1.0e12
#: Residuum, das die nachgefuehrte Loesung erreichen muss - oder das der
#: Basiszerlegung, wenn das groesser ist (dann ist mehr nicht erreichbar)
RESIDUUM = 1.0e-12
#: Hoechstens so viele Nachiterationen gegen die neue Matrix
NACHITERATIONEN = 4
#: Loeser, deren Faktor mehrere rechte Seiten auf einmal loest
LOESER = ("pardiso", "superlu")


class Abgelehnt(Exception):
    """Diese Runde rechnet die Nachfuehrung nicht - es wird neu zerlegt."""


def moeglich(ls) -> bool:
    """Taugt der Faktor ``ls`` (LinearSolver) als Basis?"""
    if MODUS == "nie" or ls is None or getattr(ls, "_solve", None) is None:
        return False
    if getattr(ls, "backend", "") not in LOESER:
        return False
    if MODUS == "immer":
        return True
    return ls.backend == "pardiso" and int(getattr(ls, "nnz_faktor", 0) or 0) >= NNZ_FAKTOR_MIN


def steifigkeitsteil(K_extra, A_aug, fi) -> sparse.csr_matrix:
    """E = (K_extra + A_aug) auf den freien Freiheitsgraden - der Teil des
    Steifigkeitsblocks, der sich von Runde zu Runde aendert (Kff bleibt)."""
    E = K_extra if A_aug is None else (K_extra + A_aug)
    E = sparse.csr_matrix(E)[fi][:, fi].tocsr()
    E.sum_duplicates()
    return E


def randteile(Vf, Cf, Df, nf: int) -> tuple:
    """(B, G) des Randes wie in StaticSystem.gerandet: B die Randzeilen (erst die
    Hilfsfesselung, dann die Kontaktzeilen), G = B + D^T die Spalten rechts oben
    als Zeilen geschrieben. Beide csr, (m, nf)."""
    bloecke = [b for b in (Vf, Cf) if b is not None and b.shape[0] > 0]
    if not bloecke:
        leer = sparse.csr_matrix((0, nf))
        return leer, leer
    B = (bloecke[0] if len(bloecke) == 1 else sparse.vstack(bloecke, format="csr")).tocsr()
    G = B
    if Df is not None and Df.shape[1] > 0 and Df.nnz:
        rand = 0 if Vf is None else int(Vf.shape[0])
        Dt = sparse.csr_matrix(Df).T.tocsr()
        if rand:
            Dt = sparse.vstack([sparse.csr_matrix((rand, nf)), Dt], format="csr")
        G = (B + Dt).tocsr()
    B = B.tocsr()
    B.sort_indices()
    G = G.tocsr()
    G.sort_indices()
    return B, G


def faktor_loesen(ls, R: np.ndarray) -> np.ndarray:
    """A0^-1 R mit dem vorhandenen Faktor von ``ls`` (eine oder mehrere rechte Seiten).

    Bei PARDISO direkt die Loesungsphase 33: pypardiso.solve bildet bei jedem
    Aufruf eine SHA-1 ueber die ganze Matrix, um zu pruefen, ob sie schon zerlegt
    ist (am Drehlager 2,4 GB je Loesung) - hier ist das gewiss, der Faktor gehoert
    genau dieser Matrix. Es sind dieselben Aufrufe wie in pypardiso.solve, nur ohne
    die Pruefsumme; das Ergebnis ist bitgleich (tests/test_faktor_weiter)."""
    ps, A = getattr(ls, "_ps", None), getattr(ls, "_K", None)
    if getattr(ls, "backend", "") == "pardiso" and ps is not None and A is not None:
        try:
            ps._check_A(A)
            b = ps._check_b(A, np.asarray(R, float))
            ps.set_phase(33)
            return ps._call_pardiso(A, b)
        except AttributeError:          # andere pypardiso-Fassung: der gewoehnliche Weg
            pass
    return ls._solve(R)


def _zeilen_kennungen(B: sparse.csr_matrix) -> list:
    """Je Zeile ein Hash ueber Spalten und Werte - zum Zuordnen alter und neuer
    Randzeilen. Gleicher Hash heisst nur „vermutlich gleich“: die Differenz wird
    danach trotzdem gebildet, ein Zusammenstoss kostet nur Spalten, nie Richtigkeit."""
    ip, ix, dt = B.indptr, B.indices, B.data
    return [hash((ix[ip[i]:ip[i + 1]].tobytes(), dt[ip[i]:ip[i + 1]].tobytes()))
            for i in range(B.shape[0])]


def _zeilen_groesse(B: sparse.csr_matrix, zeilen: np.ndarray) -> np.ndarray:
    """Groesster Betrag je Zeile (1, wenn die Zeile leer ist) - die Diagonale der
    Platzhalter weggefallener und neuer Randzeilen."""
    if not len(zeilen):
        return np.zeros(0)
    g = np.asarray(abs(B[zeilen]).max(axis=1).todense(), float).ravel()
    return np.where(g > 0.0, g, 1.0)


def _eintraege(M) -> tuple:
    """(Zeilen, Spalten, Werte) der Nichtnullen einer duennen Matrix, ohne Nullen."""
    C = M.tocoo()
    m = C.data != 0.0
    return C.row[m].astype(np.int64), C.col[m].astype(np.int64), C.data[m]


class Basis:
    """Die zuletzt zerlegte Matrix A0 eines Kontaktlaufs und was die Nachfuehrung
    von ihr braucht: den Faktor, E0, die Randzeilen und die behaltenen Spalten
    Z = A0^-1 e_t."""

    def __init__(self, ls, Kff, E, B, G, rest=None):
        self.ls = ls
        self.Kff = Kff
        self.nf = int(Kff.shape[0])
        self.E, self.B, self.G = E, B, G
        self.m0 = int(B.shape[0])
        self.n0 = self.nf + self.m0
        #: Was ausser der Signatur zum Schluessel gehoert (Hilfsfesselung)
        self.rest = rest
        self._zeilen: dict = {}
        for i, k in enumerate(_zeilen_kennungen(B)):
            self._zeilen.setdefault(k, []).append(i)
        #: behaltene Spalten: Index t -> (Block, Spalte im Block)
        self._spalte: dict = {}
        self._bloecke: list = []
        self._k = 0
        nnz = max(int(getattr(ls, "nnz_faktor", 0) or 0), 0)
        self.speicher_max = max(SPEICHER_MIN, SPEICHER_ANTEIL * 8.0 * nnz)
        #: zuletzt aufgebaute Nachfuehrung (gleiche Matrix in der naechsten Runde:
        #: Setzrunden, Nachfuehren der Reibkraft - dann nichts neu)
        self._letzte = None
        #: Zaehler fuer Protokoll und Pruefungen
        self.spalten_geloest = 0

    @property
    def spalten(self) -> int:
        return self._k

    def freigeben(self) -> None:
        self._bloecke, self._spalte, self._k, self._letzte = [], {}, 0, None

    def _loesen(self, R: np.ndarray) -> np.ndarray:
        X = np.asarray(faktor_loesen(self.ls, R), float)
        if not np.all(np.isfinite(X)):
            raise Abgelehnt("der alte Faktor liefert keine endliche Lösung")
        return X.reshape(R.shape)

    def _spalten_sichern(self, fehlend: np.ndarray) -> None:
        """A0^-1 e_t fuer die fehlenden t in einem Block loesen und behalten."""
        if not len(fehlend):
            return
        R = np.zeros((self.n0, len(fehlend)), order="F")
        R[fehlend, np.arange(len(fehlend))] = 1.0
        X = self._loesen(R)
        X = np.ascontiguousarray(X.reshape(self.n0, len(fehlend)))
        b = len(self._bloecke)
        self._bloecke.append(X)
        for j, t in enumerate(fehlend.tolist()):
            self._spalte[int(t)] = (b, j)
        self._k += len(fehlend)
        self.spalten_geloest += len(fehlend)

    def nachfuehren(self, E1, B1, G1, grenze: float = 1e-6, wiederkehr: bool = False) -> "Nachfuehrung":
        """Die Nachfuehrung fuer die Matrix [[Kff + E1, G1^T], [B1, 0]] bauen - oder
        Abgelehnt, wenn sie sich nicht lohnt oder nicht sicher ist. ``wiederkehr``:
        der Zustand wurde vor kurzem schon geloest (WIEDERKEHR_RUNDEN)."""
        nf, n0 = self.nf, self.n0
        if E1.shape != (nf, nf) or B1.shape[1] != nf:
            raise Abgelehnt("andere Zahl freier Freiheitsgrade")
        # 1. Randzeilen zuordnen: gleicher Inhalt von B -> dieselbe Stelle
        frei = {k: list(v) for k, v in self._zeilen.items()}
        m1 = int(B1.shape[0])
        stelle = np.empty(m1, np.int64)
        alt_j, alt_i, neu_j = [], [], []
        for j, k in enumerate(_zeilen_kennungen(B1)):
            lst = frei.get(k)
            if lst:
                i = lst.pop(0)
                stelle[j] = nf + i
                alt_j.append(j)
                alt_i.append(i)
            else:
                stelle[j] = n0 + len(neu_j)
                neu_j.append(j)
        weg = np.array(sorted(i for v in frei.values() for i in v), np.int64)
        n_neu = len(neu_j)
        # 2. Aenderung als Eintraege im gemeinsamen Raum (Laenge n0 + n_neu)
        zr, zc, zv = [], [], []
        r, c, v = _eintraege(E1 - self.E)
        zr.append(r), zc.append(c), zv.append(v)
        if alt_j:
            aj, ai = np.array(alt_j), np.array(alt_i)
            pos = nf + ai
            # Zeilen (B): bei gleichem Hash gleich, aber nachgeprueft
            r, c, v = _eintraege(B1[aj] - self.B[ai])
            zr.append(pos[r]), zc.append(c), zv.append(v)
            # Spalten (B^T + D): die Kopplung der Reibung dreht sich mit der Richtung
            r, c, v = _eintraege(G1[aj] - self.G[ai])
            zr.append(c), zc.append(pos[r]), zv.append(v)
        # Die Platzhalter (Multiplikator 0) stehen nicht mit 1 auf der Diagonale, sondern
        # mit der Groesse ihrer Zeile (Diagonalsteifigkeit der Knoten, ~1e10): mit 1
        # reichten die Eintraege der Kapazitaetsmatrix von 1e-10 bis 1e4, und ihre
        # geschaetzte Kondition lag am Pendelblock bei 1e10 bis 1e20, obwohl die neue
        # Matrix regulaer war. Eine Zeilen- und Spaltenskalierung der Kapazitaetsmatrix
        # haette das ebenfalls gedrueckt, aber auch eine wirklich singulaere Matrix
        # (doppelte Zeile) auf Kondition 8 gebracht - das Rundungsrauschen der grossen
        # Eintraege verdeckt dann den Rangabfall.
        sig_weg = _zeilen_groesse(self.B, weg)
        if len(weg):
            # weggefallene Zeile: in A1 ein Platzhalter statt der alten Zeile und Spalte
            pos = nf + weg
            r, c, v = _eintraege(self.B[weg])
            zr.append(pos[r]), zc.append(c), zv.append(-v)
            r, c, v = _eintraege(self.G[weg])
            zr.append(c), zc.append(pos[r]), zv.append(-v)
            zr.append(pos), zc.append(pos), zv.append(sig_weg)
        nj = np.array(neu_j, np.int64)
        sig_neu = _zeilen_groesse(B1, nj)
        if n_neu:
            # neue Zeile: in A0 stand der Platzhalter, in A1 die Zeile und Spalte
            pos = n0 + np.arange(n_neu)
            r, c, v = _eintraege(B1[nj])
            zr.append(pos[r]), zc.append(c), zv.append(v)
            r, c, v = _eintraege(G1[nj])
            zr.append(c), zc.append(pos[r]), zv.append(v)
            zr.append(pos), zc.append(pos), zv.append(-sig_neu)
        zr, zc, zv = np.concatenate(zr), np.concatenate(zc), np.concatenate(zv)
        T = np.unique(np.concatenate([zr, zc]))
        if len(T) > T_MAX:
            raise Abgelehnt(f"{len(T)} berührte Zeilen und Spalten (höchstens {T_MAX})")
        T_alt = T[T < n0]
        fehlend = np.array([t for t in T_alt.tolist() if t not in self._spalte], np.int64)
        if not wiederkehr and len(fehlend) > SPALTEN_NEU_MAX:
            raise Abgelehnt(f"{len(fehlend)} neue Spalten (höchstens {SPALTEN_NEU_MAX} je Runde)")
        if (self._k + len(fehlend)) * 8.0 * n0 > self.speicher_max:
            raise Abgelehnt(f"Speicher der Spalten ({self._k + len(fehlend)} Spalten) über "
                            f"{self.speicher_max / 2 ** 30:.2f} GiB")
        M = sparse.coo_matrix((zv, (np.searchsorted(T, zr), np.searchsorted(T, zc))),
                              shape=(len(T), len(T))).toarray()
        self._spalten_sichern(fehlend)
        # Dieselbe Matrix wie in der vorigen Runde (Setzrunden, Nachfuehren der
        # Reibkraft im Lastvektor): A1 = A0 + P_T M P_T^T ist dieselbe, die
        # Kapazitaetsmatrix auch. Verglichen wird der Inhalt, nicht ein Hash.
        teile = (T, M, stelle, weg, sig_weg, sig_neu)
        if self._letzte is not None and self._letzte[2] == n_neu and \
                all(a.shape == b.shape and np.array_equal(a, b) for a, b in zip(self._letzte[0], teile)):
            return self._letzte[1]
        nf_ = Nachfuehrung(self, E1, B1, G1, T, M, stelle, weg, n_neu, grenze, sig_weg, sig_neu)
        self._letzte = (teile, nf_, n_neu)
        return nf_

    def anwenden_Z(self, w_je_t: dict, n: int) -> np.ndarray:
        """Z w fuer Gewichte je behaltenem Index t (nur die alten Zeilen, Laenge n0)."""
        aus = np.zeros(n)
        je_block: dict = {}
        for t, w in w_je_t.items():
            b, j = self._spalte[t]
            je_block.setdefault(b, ([], []))
            je_block[b][0].append(j)
            je_block[b][1].append(w)
        for b, (js, ws) in je_block.items():
            aus += self._bloecke[b][:, js] @ np.asarray(ws, float)
        return aus

    def zeilen_Z(self, zeilen: np.ndarray, t: int) -> np.ndarray:
        b, j = self._spalte[int(t)]
        return self._bloecke[b][zeilen, j]


class Nachfuehrung:
    """Loeser-Ersatz fuer eine Runde: rechnet wie LinearSolver.solve, aber ueber
    den Faktor der Basis und die Kapazitaetsmatrix. Gibt die Eigenschaften der
    Basis weiter, die der Loeser-Nachweis liest (Loeser, Threads, gestoerte
    Pivots); ``solve`` wirft Abgelehnt, wenn das Residuum nicht erreicht wird."""

    def __init__(self, basis: Basis, E1, B1, G1, T, M, stelle, weg, n_neu, grenze, sig_weg=None,
                 sig_neu=None):
        self.basis = basis
        ls = basis.ls
        self.backend = ls.backend
        self.threads = getattr(ls, "threads", 1)
        self.mtype = getattr(ls, "mtype", None)
        self.ausweichgrund = getattr(ls, "ausweichgrund", "")
        self.gestoerte_pivots = getattr(ls, "gestoerte_pivots", None)
        self.pardiso_kennzahlen = getattr(ls, "pardiso_kennzahlen", {})
        self.nnz_faktor = getattr(ls, "nnz_faktor", 0)
        self.residuum = float("nan")
        self.nachiterationen = 0
        self.n = basis.nf + int(B1.shape[0])
        self.E1, self.B1, self.G1 = E1, B1, G1
        self.G1t = G1.T.tocsr()
        self.T, self.M = T, M
        self.stelle, self.weg, self.n_neu = stelle, weg, int(n_neu)
        #: Diagonale der Platzhalter: weggefallene Zeilen in A1, neue Zeilen in A0
        self.sig_weg = np.ones(len(weg)) if sig_weg is None else np.asarray(sig_weg, float)
        self.sig_neu = np.ones(self.n_neu) if sig_neu is None else np.asarray(sig_neu, float)
        n0 = basis.n0
        self.n_ext = n0 + self.n_neu
        self._T_alt = T[T < n0]
        self._a_alt = np.flatnonzero(T < n0)
        self._a_neu = np.flatnonzero(T >= n0)
        # Z_TT: Zeilen T der Spalten A0ext^-1 e_t (neue Zeilen: Einheitsvektor)
        k = len(T)
        Z_TT = np.zeros((k, k))
        for a in self._a_alt.tolist():
            Z_TT[self._a_alt, a] = basis.zeilen_Z(self._T_alt, int(T[a]))
        # neue Zeilen: in A0ext steht der Platzhalter sigma, A0ext^-1 e_t = e_t / sigma
        self._sig_T_neu = self.sig_neu[T[self._a_neu] - n0] if len(self._a_neu) else np.zeros(0)
        Z_TT[self._a_neu, self._a_neu] = 1.0 / self._sig_T_neu
        self.kapazitaet = np.eye(k) + M @ Z_TT
        if k:
            if not np.all(np.isfinite(self.kapazitaet)):
                raise Abgelehnt("Kapazitätsmatrix nicht endlich")
            self._lu = sla.lu_factor(self.kapazitaet, check_finite=False)
            norm1 = float(np.abs(self.kapazitaet).sum(0).max())
            rc, info = sla.lapack.dgecon(self._lu[0], norm1, norm="1")
            self.kondition = float("inf") if rc <= 0.0 else 1.0 / float(rc)
            if not self.kondition <= KONDITION_MAX:
                raise Abgelehnt(f"Kapazitätsmatrix schlecht konditioniert ({self.kondition:.1e}) - "
                                "die neue Matrix ist (fast) singulär")
        else:
            self._lu = None
            self.kondition = 1.0
        r_basis = getattr(ls, "residuum", float("nan"))
        r_basis = float(r_basis) if r_basis is not None and np.isfinite(r_basis) else 0.0
        #: Ziel der Nachiteration: so genau wie die Basiszerlegung, hoechstens die Schranke
        self.ziel = min(float(grenze), max(RESIDUUM, r_basis))
        # Fuer die Freigabe (LinearSolver.freigeben wird an Faktoren gerufen)
        self._solve = self._anwenden_neu

    # -- Abbildung neue Anordnung <-> gemeinsamer Raum ----------------------
    def _in_ext(self, y: np.ndarray) -> np.ndarray:
        nf = self.basis.nf
        z = np.zeros(self.n_ext)
        z[:nf] = y[:nf]
        z[self.stelle] = y[nf:]
        return z

    def _aus_ext(self, z: np.ndarray) -> np.ndarray:
        nf = self.basis.nf
        return np.concatenate([z[:nf], z[self.stelle]])

    def _W(self, y_ext: np.ndarray) -> np.ndarray:
        """Naeherung A1ext^-1 y_ext ueber den alten Faktor und die Kapazitaetsmatrix."""
        b = self.basis
        n0 = b.n0
        x = np.empty(self.n_ext)
        x[:n0] = b._loesen(y_ext[:n0])
        x[n0:] = y_ext[n0:] / self.sig_neu
        if self._lu is None:
            return x
        w = sla.lu_solve(self._lu, self.M @ x[self.T], check_finite=False)
        if len(self._a_alt):
            x[:n0] -= b.anwenden_Z({int(self.T[a]): float(w[a]) for a in self._a_alt.tolist()}, n0)
        if len(self._a_neu):
            x[self.T[self._a_neu]] -= w[self._a_neu] / self._sig_T_neu
        return x

    def matvec(self, x: np.ndarray) -> np.ndarray:
        """A1 x in der Anordnung der neuen Matrix [u; Rand]."""
        nf = self.basis.nf
        u, lam = x[:nf], x[nf:]
        oben = self.basis.Kff @ u + self.E1 @ u
        if len(lam):
            oben = oben + self.G1t @ lam
        return np.concatenate([oben, self.B1 @ u])

    def _anwenden_neu(self, y: np.ndarray) -> np.ndarray:
        return self._aus_ext(self._W(self._in_ext(np.asarray(y, float))))

    def solve(self, b: np.ndarray, check: bool = True) -> np.ndarray:
        b = np.asarray(b, float)
        if b.ndim == 2:
            return np.column_stack([self.solve(b[:, j], check) for j in range(b.shape[1])])
        nb = float(np.linalg.norm(b))
        if nb == 0.0:
            self.residuum = 0.0
            return np.zeros_like(b)
        y_ext = self._in_ext(b)
        x_ext = self._W(y_ext)
        r_vor = None
        schritte = 0
        while True:
            x = self._aus_ext(x_ext)
            if not np.all(np.isfinite(x)):
                raise Abgelehnt("Lösung nicht endlich")
            r = b - self.matvec(x)
            # Platzhalter weggefallener Zeilen: sigma * Multiplikator = 0
            r_weg = (-self.sig_weg * x_ext[self.basis.nf + self.weg]) if len(self.weg) else np.zeros(0)
            rel = float(np.sqrt(r @ r + r_weg @ r_weg)) / nb
            if rel <= self.ziel:
                break
            if schritte >= NACHITERATIONEN or (r_vor is not None and not rel < 0.5 * r_vor):
                self.residuum = rel
                raise Abgelehnt(f"Residuum {rel:.1e} nach {schritte} Nachiterationen über dem Ziel "
                                f"{self.ziel:.0e}")
            r_ext = self._in_ext(r)
            if len(self.weg):
                r_ext[self.basis.nf + self.weg] = r_weg
            x_ext = x_ext + self._W(r_ext)
            r_vor = rel
            schritte += 1
        self.residuum = rel
        self.nachiterationen = schritte
        return x

    def beschreibung(self) -> str:
        return (f"Zerlegung nachgeführt ({len(self.T)} berührte Zeilen/Spalten, "
                f"{self.basis.spalten} Spalten behalten)")

    def freigeben(self) -> None:
        """Gibt nichts frei: der Faktor gehoert der Basis."""
        return None
