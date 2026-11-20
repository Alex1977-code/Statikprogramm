"""Strafanteil der Starrkoerper und Verteilkopplungen fuer die Pruefung des
Residuums (Runde k10c, Nachbesserung 1, 16.11.2026).

Warum. Die Starrkoerper (RBE2) und Verteilkopplungen (RBE3, auch „Scheibe"
und „Stabende") stehen im Strafverfahren als k Gᵀ G in K, mit k bis zum
Vielfachen von 10 000 der groessten Hauptdiagonale (beim allgemeinen RBE3
kommt die Gewichtssumme im Quadrat dazu). Die Loeserpruefung verlangt
||K u - F|| <= 0,000001 ||F||. Schon die auf doppelte Genauigkeit gerundete
exakte Loesung hat aber im Strafanteil den Fehler k Gᵀ (G δu) mit
|δu| = eps |u|: bewegt sich ein Kreisring mit seinem Master als Ganzes um
einige Millimeter (Kragarm), liegt allein dieser Rundungsrest ueber der
Schranke, und ein gesundes Modell hiess „numerisch singulaer" (Residuum
0,039 am Kreisring mit 64 Slaves, bei Fy und Mx auch mit dem auf die Knoten
bezogenen Strafbeiwert noch 0,0000011 bis 0,0000017).

Was hier steht. Der Strafanteil getrennt, wie er gebaut wurde: je Kopplung
die FHG, G und k. Damit rechnet :meth:`LokalePruefung.residuum` das Residuum
als K₀ u + Σ k Gᵀ (G u) - F statt mit der Summenmatrix; jeder Rundungsrest
des Strafanteils liegt dann im Zeilenraum von G (in den Richtungen, in denen
die Kopplung haelt). :meth:`LokalePruefung.zerlegen` nimmt ihn heraus und
rechnet ihn in die Verletzung der Zwangsbedingung um, die er bedeutet
(Rest / Strafsteifigkeit, eine Laenge). Geprueft wird dann beides:

* der Rest ausserhalb des Zeilenraums gegen dieselbe Schranke
  0,000001 ||F|| wie bisher - dort liegt alles, was ein wirklich singulaeres
  System verraet (der Nullraum von K steht senkrecht auf dem Zeilenraum jeder
  Straffeder, denn K ⪰ k Gᵀ G);
* die Verletzung der Zwangsbedingung gegen 0,000001 der groessten
  Verschiebung.

Die Pruefung laeuft nur, wenn die bisherige an einem Modell mit Starrkoerpern
scheitert (LinearSolver.solve). Rechnet ein Modell schon heute, aendert sich
an ihm kein Bit.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse

#: Nur fuer Ruecknahmeproben (tests.test_rbe3_ring_k10, tests.test_numerik_k10):
#: False schaltet die Pruefung mit getrenntem Strafanteil ab - dann prueft
#: LinearSolver.solve wie vor Runde k10c. Im Programm immer True.
PRUEFUNG = True

#: Hoechstens so viele Nachiterationen mit dem getrennt gerechneten Residuum
#: (am Kreisring-RBE3 brauchte es 3 bis 5, am RBE2-Ring mit 100 Staeben
#: und Torsion rund 20 - jede kostet nur ein Ruecksetzen)
NACHITERATIONEN = 30


def schluessel(sk) -> str:
    """Schluessel einer Kopplung im Rest je Kopplung: Name und Master."""
    return f"{getattr(sk, 'name', '')}@{int(getattr(sk, 'master', -1))}"


class Kopplung:
    """Eine Straffeder k Gᵀ G auf den FHG ``fhg`` (global).

    ``knoten`` (nur RBE2): Lage des Masters und der Slaves - der Nullraum von
    G sind die sechs Starrkoerperbewegungen, der Zeilenraum ist sein
    Komplement (6 n Zeilen, eine Orthonormalbasis davon waere teuer).
    Die ersten sechs FHG sind die des Masters (wie in assemble.starrkoerper).
    ``name``: Name und Master des Starrkoerpers, als Schluessel des Rests
    (siehe :meth:`LokalePruefung.nachiterieren`)."""

    __slots__ = ("fhg", "G", "k", "art", "knoten", "name", "allgemein")

    def __init__(self, fhg, G, k: float, art: str, knoten=None, name: str = "", allgemein: bool = False):
        self.fhg = np.asarray(fhg, np.int64)
        self.G = sparse.csr_matrix(np.asarray(G, float))
        self.k = float(k)
        self.art = str(art).upper()
        self.knoten = None if knoten is None else np.asarray(knoten, float)
        self.name = str(name)
        #: frei definierter RBE3 (nicht Stabende/Scheibe): bis Nachbesserung 2
        #: trugen seine Zeilen die Gewichtssumme (am Master k mal deren
        #: Quadrat); seither je Zeile ein eigener Strafbeiwert, der in G steckt
        #: (assemble.rbe3_zeilen_master, k = 1)
        self.allgemein = bool(allgemein)


class Strafanteil:
    """Alle Straffedern der Starrkoerper eines Aufstellens (assemble.stiffness)
    und die Zeilen der Matrix ohne sie an den gekoppelten FHG.

    ``ref_ohne``: groesste Hauptdiagonale ohne die Straffedern der frei
    definierten RBE3 - der Bezug der automatischen Fesselung
    (assemble.gesperrte_und_automatische). Die Straffedern der RBE2 und der
    verteilenden Kopplungen bleiben darin wie bisher (1e4-mal die Elemente,
    wie die starre Knotenkopplung); nur der frei definierte RBE3 traegt k mal
    die Gewichtssumme im Quadrat (64 Slaves: 4096) und hob den Bezug so weit,
    dass Drehungen mit echter Steifigkeit als „ohne Steifigkeit" galten."""

    def __init__(self, kopplungen: list, K_ohne: sparse.spmatrix, ndof: int):
        self.kopplungen = [k for k in kopplungen if k.fhg.size]
        self.ndof = int(ndof)
        K_ohne = K_ohne.tocsr()
        d = np.abs(np.asarray(K_ohne.diagonal(), float).ravel()).copy()
        for kp in self.kopplungen:
            if not kp.allgemein:
                d[kp.fhg] += kp.k * np.asarray(kp.G.multiply(kp.G).sum(axis=0)).ravel()
        self.ref_ohne = float(d.max()) if d.size and d.max() > 0 else 0.0
        R = np.unique(np.concatenate([k.fhg for k in self.kopplungen])) if self.kopplungen \
            else np.zeros(0, np.int64)
        self.R = R
        self.K0R = K_ohne[R] if R.size else None

    def lokal(self, fi, zusatz=()) -> "LokalePruefung":
        """Die Pruefung im Raum des Gleichungssystems: ``fi`` die freien FHG
        (Spalten von Kff), ``zusatz`` globale Zusatzmatrizen, die in der
        faktorisierten Matrix stecken (Kontakt K_extra, Augmentierung).
        Die Matrix selbst (Kff, ggf. mit dem Lagrange-Rand dahinter) kommt erst
        mit :meth:`LokalePruefung.residuum` - es wird nichts gehalten und
        nichts gebaut, solange die bisherige Pruefung besteht."""
        return LokalePruefung(self, fi, zusatz)


class LokalePruefung:
    def __init__(self, sa: Strafanteil, fi, zusatz=()):
        self._sa, self._fi = sa, np.asarray(fi, np.int64)
        self._zusatz = tuple(z for z in (zusatz or ()) if z is not None)
        self._fertig = False

    # ------------------------------------------------------------------
    def _bauen(self, A):
        if self._fertig:
            return
        sa, fi = self._sa, self._fi
        N = int(A.shape[0])
        nf = len(fi)
        pos = -np.ones(sa.ndof, np.int64)
        pos[fi] = np.arange(nf)
        frei_R = pos[sa.R] >= 0
        R_glob = sa.R[frei_R]
        self.R = pos[R_glob]
        A0 = sa.K0R[np.where(frei_R)[0]]
        for z in self._zusatz:
            A0 = A0 + z.tocsr()[R_glob]
        self._zusatz = ()
        A0 = A0.tocsc()[:, fi].tocsr()
        if N > nf:
            rand = A.tocsr()[self.R][:, nf:]
            A0 = sparse.hstack([A0, rand], format="csr")
        self.A0R = A0
        self.n_u = nf
        self.teile = []
        for kp in sa.kopplungen:
            p = pos[kp.fhg]
            frei = p >= 0
            if not np.any(frei):
                continue
            Gf = kp.G[:, np.where(frei)[0]].tocsr()
            if Gf.nnz == 0:
                continue
            # Lage der Master-FHG (die ersten sechs) in d: {Komponente: Index}
            stelle = np.cumsum(frei) - 1
            master = {j: int(stelle[j]) for j in range(min(6, len(frei))) if frei[j]}
            teil = {"d": p[frei], "G": Gf, "k": kp.k, "name": kp.name, "master": master}
            if kp.art == "RBE2" and kp.knoten is not None:
                teil["N"] = _nullraum_rbe2(kp.knoten, frei)
            else:
                Gd = Gf.toarray()
                _U, s, Vt = np.linalg.svd(Gd, full_matrices=False)
                behalten = s > 1e-9 * (s[0] if s.size else 0.0)
                teil["Q"] = Vt[behalten]
                teil["M"] = kp.k * s[behalten] ** 2
            self.teile.append(teil)
        self._fertig = True

    # ------------------------------------------------------------------
    def residuum(self, x: np.ndarray, b: np.ndarray, A) -> np.ndarray:
        """A x - b, an den gekoppelten Zeilen als K₀ x + Σ k Gᵀ (G x) - b."""
        self._bauen(A)
        r = A @ x - b
        if self.R.size:
            pen = np.zeros(len(x))
            for t in self.teile:
                d = t["d"]
                pen[d] += t["k"] * (t["G"].T @ (t["G"] @ x[d]))
            r[self.R] = self.A0R @ x + pen[self.R] - b[self.R]
        return r

    def zerlegen(self, r: np.ndarray, am_master: list = None) -> tuple:
        """(Rest ausserhalb der Zeilenraeume, groesste Verletzung der
        Zwangsbedingung in Metern bzw. Bogenmass). Ueberlappen sich Kopplungen
        (ein Knoten in zweien), nimmt die Schleife die Anteile reihum heraus;
        drei Durchgaenge genuegen, weil jeder Rest im Zeilenraum nur eine
        Verletzung Rest/k bedeutet.

        ``am_master`` (Liste, wird gefuellt): je Kopplung der herausgenommene
        Anteil an den sechs FHG ihres Masters - um so viel weicht die aus u
        gerechnete Kopplungskraft k Gᵀ G u dort vom Gleichgewicht ab.
        Erst nach :meth:`residuum` (das baut)."""
        r = np.array(r, float, copy=True)
        if am_master is not None:
            am_master[:] = [np.zeros(6) for _t in self.teile]
        verl = np.zeros(len(self.teile))
        for _durchgang in range(3):
            for i, t in enumerate(self.teile):
                d = t["d"]
                rd = r[d]
                if "Q" in t:
                    c = t["Q"] @ rd
                    anteil = t["Q"].T @ c
                    v = float(np.linalg.norm(c / t["M"])) if c.size else 0.0
                else:
                    N = t["N"]
                    anteil = rd - (N @ (N.T @ rd) if N.size else 0.0)
                    # Die Zeilen eines RBE2 haben Singulaerwerte >= 1 (je
                    # Slave eine Einheitsmatrix): Verletzung <= Rest / k
                    v = float(np.linalg.norm(anteil)) / t["k"]
                r[d] = rd - anteil
                verl[i] += v
                if am_master is not None:
                    for j, z in t["master"].items():
                        am_master[i][j] += anteil[z]
        return r, (float(verl.max()) if verl.size else 0.0)

    def nachiterieren(self, loese, A, b: np.ndarray, x: np.ndarray, grenze: float,
                      schritte: int = NACHITERATIONEN) -> dict:
        """Nachiteration mit dem getrennt gerechneten Residuum und Pruefung wie
        oben. Rueckgabe {"ok", "x", "rest", "verletzung", "schritte"}; "rest"
        ist ||Rest||/||b||, "verletzung" bezogen auf max|u|."""
        nb = float(np.linalg.norm(b))
        bestes = None
        ohne_fortschritt = 0
        for i in range(schritte + 1):
            r = self.residuum(x, b, A)
            rest, verl = self.zerlegen(r)
            q = float(np.linalg.norm(rest)) / nb if nb > 0 else 0.0
            umax = float(np.abs(x[:self.n_u]).max()) if self.n_u else 0.0
            v = verl / umax if umax > 0 else (0.0 if verl == 0 else np.inf)
            guete = max(q, v)
            if bestes is None or guete < 0.9 * bestes["guete"]:
                ohne_fortschritt = 0
            else:
                ohne_fortschritt += 1
            if bestes is None or guete < bestes["guete"]:
                bestes = {"x": x, "rest": q, "verletzung": v, "schritte": i, "guete": guete}
            # Weiter, solange es deutlich besser wird: die Schranke ist die
            # Mindestforderung, die Nachiteration kostet nur Ruecksetzen.
            # Am Kreisring lag die Verschiebung bei Abbruch an der Schranke
            # bis 0,00009 mm neben der exakten Zwangsbedingung.
            if guete <= 1e-3 * grenze or ohne_fortschritt >= 2 or i == schritte:
                break
            dx = loese(r)
            if not np.all(np.isfinite(dx)):
                break
            x = x - dx
        bestes["ok"] = bestes["rest"] <= grenze and bestes["verletzung"] <= grenze
        # Je Kopplung, um wie viel die aus u gerechnete Kopplungskraft am
        # Master neben dem Gleichgewicht liegt (Kraft, Moment) - die
        # Kraftsummenpruefung der Stabenden (stabeinleitung.pruefen) rechnet
        # mit k Gᵀ G u und braucht diesen Rest als Aufloesung.
        am: list = []
        self.zerlegen(self.residuum(bestes["x"], b, A), am)
        bestes["rest_kopplung"] = {
            t["name"]: [float(np.linalg.norm(v[:3])), float(np.linalg.norm(v[3:]))]
            for t, v in zip(self.teile, am) if t["name"]}
        return bestes


def _nullraum_rbe2(knoten: np.ndarray, frei: np.ndarray) -> np.ndarray:
    """Orthonormalbasis des Nullraums von G eines RBE2 auf den freien FHG:
    die Starrkoerperbewegungen der Knoten [Master, Slaves...] (je 6 FHG), soweit
    sie an den gesperrten FHG null sind."""
    X = np.asarray(knoten, float)
    c = X.mean(axis=0)
    n = len(X)
    B = np.zeros((6 * n, 6))
    for j, x in enumerate(X):
        r = x - c
        z = 6 * j
        B[z:z + 3, 0:3] = np.eye(3)
        # Drehung e_a: u = e_a x r, theta = e_a
        B[z:z + 3, 3:6] = -np.array([[0, -r[2], r[1]], [r[2], 0, -r[0]], [-r[1], r[0], 0]])
        B[z + 3:z + 6, 3:6] = np.eye(3)
    gesperrt = ~np.asarray(frei, bool)
    if np.any(gesperrt):
        _U, s, Vt = np.linalg.svd(B[gesperrt], full_matrices=True)
        rang = int(np.sum(s > 1e-12 * max(1.0, s[0] if s.size else 1.0)))
        Z = Vt[rang:].T
        B = B @ Z
    B = B[np.asarray(frei, bool)]
    if B.shape[1] == 0:
        return B
    Q, Rr = np.linalg.qr(B)
    keep = np.abs(np.diag(Rr)) > 1e-12 * max(1.0, float(np.abs(np.diag(Rr)).max()))
    return Q[:, keep]
