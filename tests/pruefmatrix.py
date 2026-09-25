"""
Pruefmatrix (Auftrag vom 25.09.2026): rechnet die Rechnung **richtig** - linear,
mit Kontakt, mit Plastizitaet und mit beidem - in jeder Elementstufe?

Die Matrix misst nur; sie aendert nichts an Rechnung, Elementen, Kontakt,
Plastizitaet oder Vernetzer. Sie steht nicht in tests.run_all, weil sie laenger
laeuft (Ziel unter 30 min, einkernig).

Stufen (wie sie gerade gebaut werden)
-------------------------------------
  Entwurf  tet4  + hex8   Kantenlaenge h,   Ordnung 1
  Mittel   tet10 + hex20  Kantenlaenge h,   Ordnung 2
  Fein     tet10 + hex20  Kantenlaenge h/2, Ordnung 2

Jede Zelle Stufe x Fall rechnet beide Familien (Tetraeder und Sechsflaechner).
Solange die Stufen-Oberflaeche nicht in main ist, stellt die Matrix die Stufe
direkt ueber ``model.netz.ordnung`` und die Kantenlaenge ein, Sweep aus:

* Quaderfoermige Koerper entstehen als **Geometrie** (Linien, Flaechen,
  Volumenkoerper) und gehen durch den Vernetzer des Programms: Tetraeder durch
  den freien Vernetzer (``mesher3d.mesh_koerper_frei`` mit h und Ordnung),
  Sechsflaechner durch den abgebildeten Pfad (``mesher.mesh_koerper``). Der
  abgebildete Pfad liest die Kantenlaenge nicht (er teilt nach
  ``Volumenkoerper.teilung``, Vorgabe 4 x 4 x 4 - gemessen 25.09.2026 am Quader
  1,0 x 0,1 x 0,2 m: h = 0,05 und h = 0,025 geben beide 64 hex8); die Matrix
  setzt darum die Linienteilung round(Laenge/h) ueber ``model.linienvorgabe``,
  so wie es die Lagenvorgabe des Sweeps tut.
* Gekruemmte Koerper (Rohr) kommen aus den Pruefkoerper-Bausteinen
  (tests/pruefkoerper.py, strukturiert, Kantenmitten auf dem Bogen): mit Sweep
  aus lehnt der abgebildete Pfad krumme Kanten ab, und die Matrix soll die
  Rechnung messen, nicht die Bogenteilung des freien Vernetzers.

Je Zelle festgehalten: konvergiert (Kontakt und Plastizitaet getrennt, aus
res.info), gestoerte Pivots (res.info["loeser_nachweis"]), Fehler gegen die
geschlossene Loesung (N/mm2 bzw. %; Spannung als geglaettete Knotenspannung
res.solid_knoten, wie der Nachweis sie liest), Unbekannte, Zeit. Ergebnis:

  gruen     konvergiert, jeder Fehler in seiner Grenze
  gelb      konvergiert, ein Fehler groesser (Diskretisierung, z. B. tet4 zu steif)
  rot       nicht konvergiert, Abbruch oder falsches Ergebnis (bei Faellen, die
            jedes Element exakt darstellen kann, ist jede Ueberschreitung falsch)
  gesperrt  Kontakt an quadratischen Seiten (fugen.QuadratischeSeiten) - den
            tet10/hex20-Kontakt baut die Loeser-Sitzung

Aufruf:
    python -m tests.pruefmatrix                 # alles, Tabellen auf die Konsole
    python -m tests.pruefmatrix --json out.json # dazu die Rohwerte
    python -m tests.pruefmatrix --fall K1 P2    # nur diese Faelle
"""
from __future__ import annotations

import os

# Einkernig rechnen (Auftrag: hoechstens zwei Prozesse, die Loeser-Sitzung
# rechnet parallel einen Kontrolllauf). Vor numpy/scipy/pypardiso setzen.
for _v in ("MKL_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json          # noqa: E402
import sys           # noqa: E402
import time          # noqa: E402
import traceback     # noqa: E402

import numpy as np   # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import fugen, mesher, mesher3d as M3, solver       # noqa: E402
from statik3d import plastizitaet as pl                          # noqa: E402
from statik3d.elements import solid as sl                        # noqa: E402
from statik3d.model import (ContactPair, DofBehaviour, Material,  # noqa: E402
                            Model, Uebermass)
from tests import pruefkoerper as pk                             # noqa: E402
from tests.messung_rohr_plastisch import Hill                    # noqa: E402

DATUM = "25.09.2026"
E_ST, NU_ST = pk.E_ST, pk.NU_ST
FY = 235e6
VERFESTIGUNG = 0.05          # E_t/E
MPA = 1e6

STUFEN = [
    ("Entwurf", [("tet", "tet4", 1, 1.0), ("hex", "hex8", 1, 1.0)]),
    ("Mittel", [("tet", "tet10", 2, 1.0), ("hex", "hex20", 2, 1.0)]),
    ("Fein", [("tet", "tet10", 2, 0.5), ("hex", "hex20", 2, 0.5)]),
]


# --------------------------------------------------------------------------
# Zahlen: nie wissenschaftlich, Komma
# --------------------------------------------------------------------------
def zahl(x, nd=2):
    if x is None:
        return "–"
    try:
        if not np.isfinite(x):
            return "–"
    except TypeError:
        return str(x)
    return f"{x:.{nd}f}".replace(".", ",")


def ganz(x):
    return f"{int(x):,}".replace(",", ".")


# --------------------------------------------------------------------------
# Geometrie: Quader als Volumenkoerper, gemeinsame Flaechen einmal
# --------------------------------------------------------------------------
class Geo:
    def __init__(self, m: Model):
        self.m = m
        self.kn: dict = {}
        self.li: dict = {}
        self.fl: dict = {}

    def knoten(self, p):
        key = tuple(np.round(np.asarray(p, float), 9))
        if key not in self.kn:
            self.kn[key] = self.m.add_node(*key)
        return self.kn[key]

    def linie(self, a, b):
        key = (min(a, b), max(a, b))
        if key not in self.li:
            name = f"L{len(self.li) + 1}"
            self.m.add_line(name, [a, b], "polyline")
            self.li[key] = name
        return self.li[key]

    def flaeche(self, ring, name=None):
        key = frozenset(ring)
        if key not in self.fl:
            name = name or f"F{len(self.fl) + 1}"
            linien = [self.linie(ring[i], ring[(i + 1) % 4]) for i in range(4)]
            self.m.add_flaeche(name, linien, material="S")
            self.fl[key] = name
        return self.fl[key]

    def quader(self, name, p0, p1, namen=None):
        """Quader [p0, p1]; ``namen`` {"x0"|"x1"|"y0"|...: Flaechenname}."""
        namen = namen or {}
        x = [p0[0], p1[0]]
        y = [p0[1], p1[1]]
        z = [p0[2], p1[2]]
        c = {(i, j, k): self.knoten((x[i], y[j], z[k])) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
        seiten = {
            "z0": [c[0, 0, 0], c[1, 0, 0], c[1, 1, 0], c[0, 1, 0]],
            "z1": [c[0, 0, 1], c[1, 0, 1], c[1, 1, 1], c[0, 1, 1]],
            "y0": [c[0, 0, 0], c[1, 0, 0], c[1, 0, 1], c[0, 0, 1]],
            "y1": [c[0, 1, 0], c[1, 1, 0], c[1, 1, 1], c[0, 1, 1]],
            "x0": [c[0, 0, 0], c[0, 1, 0], c[0, 1, 1], c[0, 0, 1]],
            "x1": [c[1, 0, 0], c[1, 1, 0], c[1, 1, 1], c[1, 0, 1]],
        }
        fl = [self.flaeche(r, namen.get(s)) for s, r in seiten.items()]
        return self.m.add_koerper(name, fl, material="S")


def geo_modell(ordnung, h, fy=None):
    m = Model("Pruefmatrix")
    m.add_material(Material("S", E=E_ST, nu=NU_ST, rho=0.0, fy=fy))
    m.netz.ordnung = int(ordnung)
    m.netz.sweep = False
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = float(h)
    m.netz.intelligent = False
    return m


def vernetzen(m: Model, koerper, familie, h, ordnung, log):
    """Das Netz der Stufe: Tetraeder frei, Sechsflaechner abgebildet."""
    cache: dict = {}
    if familie == "tet":
        for k in koerper:
            M3.mesh_koerper_frei(m, k, h=h, log=log, cache=cache, ordnung=ordnung)
    else:
        vorgabe = {}
        for name, ln in m.lines.items():
            P = m.nodes[[int(n) for n in ln.nodes]]
            L = float(np.sum(np.linalg.norm(P[1:] - P[:-1], axis=1)))
            vorgabe[name] = max(1, int(round(L / h)))
        m.linienvorgabe = vorgabe
        for k in koerper:
            mesher.mesh_koerper(m, k, log, cache=cache, h=h, ordnung=ordnung)
    typen = {e.typ for e in m.elements}
    if not m.elements:
        raise RuntimeError("Vernetzer: kein Element - " + "; ".join(str(z) for z in log[-3:]))
    m._pm_netz = konformitaet(m)
    return typen


def konformitaet(m: Model) -> dict:
    """Ist das Netz knotenkonform? Gezaehlt, **bevor** eine Fuge Knoten
    trennt: (a) Orte mit mehr als einem Knoten am Netz (z. B. Kantenmitten,
    die jeder Koerper selbst anlegt), (b) Elementseiten, die nur einem Element
    gehoeren und nicht auf der Aussenhuelle liegen - die Koerper der Matrix
    fuellen zusammen einen Quader, dessen Huelle die Begrenzungsebenen sind."""
    from collections import Counter
    X = np.asarray(m.nodes, float)
    im = am_netz(m)
    orte = Counter(tuple(np.round(X[n], 9)) for n in np.flatnonzero(im))
    doppelt = sum(1 for v in orte.values() if v > 1)
    lo, hi = X[im].min(axis=0), X[im].max(axis=0)
    c = Counter()
    for e in m.elements:
        for f in sl.FLAECHEN_ECKEN[e.typ]:
            c[tuple(sorted(int(e.nodes[a]) for a in f))] += 1
    tol = 1e-9 * float(np.max(hi - lo))
    offen = 0
    for k, v in c.items():
        if v != 1:
            continue
        P = X[list(k)]
        if not any(np.all(np.abs(P[:, d] - w) < tol) for d in range(3) for w in (lo[d], hi[d])):
            offen += 1
    return {"doppelknoten": int(doppelt), "offene_innenseiten": int(offen)}


def am_netz(m: Model):
    im = np.zeros(m.nn, bool)
    for e in m.elements:
        im[[int(n) for n in e.nodes]] = True
    return im


def ecken_am_netz(m: Model):
    s = set()
    for e in m.elements:
        s.update(int(n) for n in e.nodes[:len(sl.ECKEN_NATUERLICH[e.typ])])
    return s


def lagern(m: Model, bedingung, dofs, stiffness=None):
    X = np.asarray(m.nodes, float)
    im = am_netz(m)
    aus = []
    for n in np.flatnonzero(im):
        if bedingung(X[n]):
            if stiffness is None:
                m.fix(int(n), list(dofs))
            else:
                m.fix(int(n), list(dofs), stiffness=[stiffness] * len(dofs))
            aus.append(int(n))
    return aus


def quadratisch_machen(m: Model, mitte=None):
    """hex8 -> hex20 (Kantenmitten dazu). ``mitte(P, Q) -> Punkt`` legt die
    Mitte (z. B. auf den Bogen); Vorgabe die Sehnenmitte."""
    kanten = sl._KANTEN_QUADRATISCH["hex20"]
    mitten: dict = {}
    for e in m.elements:
        if e.typ != "hex8":
            continue
        c = [int(n) for n in e.nodes]
        neu = []
        for a, b in kanten:
            key = (min(c[a], c[b]), max(c[a], c[b]))
            if key not in mitten:
                P, Q = m.nodes[c[a]], m.nodes[c[b]]
                X = mitte(P, Q) if mitte is not None else 0.5 * (P + Q)
                mitten[key] = m.add_node(*X)
            neu.append(mitten[key])
        e.typ = "hex20"
        e.nodes = c + neu
    return m


# --------------------------------------------------------------------------
# Auswertung
# --------------------------------------------------------------------------
def knotenspannung(res, knoten):
    """Geglaettete Knotenspannung (Mittel der Zeilen dieses Knotens) - die
    Tabelle, aus der der Nachweis (res.solid_rand) liest."""
    sk = res.solid_knoten or {}
    kn = np.asarray(sk.get("knoten", []), np.int64)
    S = np.asarray(sk.get("spannung", []), float)
    aus = {}
    for n in knoten:
        z = np.flatnonzero(kn == int(n))
        if len(z):
            aus[int(n)] = S[z].mean(axis=0)
    return aus


def sv(S):
    return float(sl.von_mises(np.asarray(S, float)))


def u3(res, m):
    return np.asarray(res.u, float).reshape(m.nn, -1)[:, :3]


def metrik(name, wert, grenze, einheit):
    return {"name": name, "wert": float(wert), "grenze": float(grenze), "einheit": einheit}


# --------------------------------------------------------------------------
# Faelle
# --------------------------------------------------------------------------
class Fall:
    kurz = ""
    rechenart = ""
    name = ""
    soll = ""
    grenze_text = ""
    #: jedes Element stellt die Loesung exakt dar (homogener Zustand) - dann
    #: ist jede Ueberschreitung ein falsches Ergebnis (rot), nicht gelb
    exakt = False
    kontakt = False
    plastisch = False
    h = 0.5

    def bauen(self, familie, typ, ordnung, h, log):
        raise NotImplementedError

    def auswerten(self, m, res, meta):
        raise NotImplementedError


# ---- linear ---------------------------------------------------------------
class Kragarm(Fall):
    kurz, rechenart = "L1", "linear"
    name = "Kragarm aus einem Körper, σ_v an der Oberkante bei L/2 (Saint-Venant)"
    soll = ("σ_xx = M z/I = 355 N/mm² bei x = L/2 (Oberkante, Mitte der Breite); L 1,0 / B 0,1 / H 0,2 m; "
            "ausgewertet am Eckknoten der Oberkante, der (L/2, B/2, H) am nächsten liegt, gegen "
            "σ_xx an seinem x (Saint-Venant: an der Oberkante unabhängig von y)")
    grenze_text = "1 N/mm² (Ziel des Anwenders)"
    h = 0.05
    #: zwei Koerper mit gemeinsamer Flaeche bei L/2 - so sind Bauteile im
    #: Programm aufgebaut (Drehlager: 48 Koerper)
    geteilt = False

    def bauen(self, familie, typ, ordnung, h, log):
        kr = pk.Kragarm()
        m = geo_modell(ordnung, h)
        g = Geo(m)
        if self.geteilt:
            koerper = [g.quader("Links", (0, 0, 0), (0.5 * kr.L, kr.B, kr.H)),
                       g.quader("Rechts", (0.5 * kr.L, 0, 0), (kr.L, kr.B, kr.H))]
        else:
            koerper = [g.quader("Kragarm", (0, 0, 0), (kr.L, kr.B, kr.H))]
        vernetzen(m, koerper, familie, h, ordnung, log)
        tol = 1e-9
        lagern(m, lambda x: abs(x[0]) < tol, [0, 1, 2])
        seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 0] - kr.L) < tol)))
        pk.schubkraft_auf_seiten(m, seiten, kr.F, (0.0, 0.0, -1.0))
        return m, {"kr": kr}

    def auswerten(self, m, res, meta):
        kr = meta["kr"]
        X = np.asarray(m.nodes, float)
        ecken = ecken_am_netz(m)
        oben = [n for n in ecken if abs(X[n, 2] - kr.H) < 1e-9]
        P = kr.punkt()
        n = min(oben, key=lambda i: np.linalg.norm(X[i] - P))
        S = knotenspannung(res, [n])[n]
        soll = kr.sigma * (kr.L - X[n, 0]) / (kr.L - kr.x_nw)
        d = np.linalg.norm(X[n] - P)
        return [metrik("σ_v", (sv(S) - soll) / MPA, 1.0, "N/mm²")], \
            f"Knoten {n} bei x = {X[n, 0]:.4f}, y = {X[n, 1]:.4f} m (Abstand {d * 1e3:.1f} mm)".replace(".", ",")


class LameZylinder(Fall):
    kurz, rechenart = "L2", "linear"
    name = "Lamé-Rohr unter Innendruck, ebene Dehnung (ν = 0,3)"
    soll = "σ_v(a) = 355 N/mm² (p skaliert), u_r(a) nach Lamé; a 0,1 / b 0,2 m"
    grenze_text = "1 N/mm² an jedem Eckknoten der Innenfläche, u_r 1 %"
    h = 0.025

    def bauen(self, familie, typ, ordnung, h, log):
        n_r = max(1, int(round(0.1 / h)))
        n_t = 2 * n_r
        rz = pk.Hohlzylinder(p=1.0)
        rz = pk.Hohlzylinder(p=pk.SIGMA_BEZUG / rz.sv_innen())
        m = zylinder_modell(rz, typ, n_t, n_r, nu=NU_ST)
        return m, {"rz": rz, "netz": f"{n_t} × {n_r}"}

    def auswerten(self, m, res, meta):
        rz = meta["rz"]
        X = np.asarray(m.nodes, float)
        r = np.hypot(X[:, 0], X[:, 1])
        innen = [n for n in ecken_am_netz(m) if abs(r[n] - rz.a) < 1e-9]
        S = knotenspannung(res, innen)
        d_sv = max((sv(S[n]) - rz.sv_innen()) / MPA for n in S) if S else np.nan
        d_sv_min = min((sv(S[n]) - rz.sv_innen()) / MPA for n in S) if S else np.nan
        d = d_sv if abs(d_sv) >= abs(d_sv_min) else d_sv_min
        u = u3(res, m)
        ur = np.mean([(u[n, 0] * X[n, 0] + u[n, 1] * X[n, 1]) / r[n] for n in innen])
        du = (ur / rz.u_r(rz.a) - 1) * 100
        return [metrik("σ_v", d, 1.0, "N/mm²"), metrik("u_r", du, 1.0, "%")], f"Netz {meta['netz']} (n_t × n_r)"


class KragarmZweiKoerper(Kragarm):
    kurz = "L3"
    name = "Kragarm aus zwei Körpern (gemeinsame Fläche bei L/2), σ_v wie L1"
    soll = ("wie L1; die Körper teilen die Fläche x = L/2, der Nachweisknoten liegt auf ihr - "
            "misst, ob das Netz über die gemeinsame Fläche trägt")
    geteilt = True


def zylinder_modell(rz, typ, n_t, n_r, nu=NU_ST, fy=None):
    """pk.Hohlzylinder.modell, dazu hex20 (Mitten auf dem Bogen)."""
    if typ != "hex20":
        return rz.modell(typ, n_t, n_r, nu=nu, fy=fy)
    a, b, h = rz.a, rz.b, rz.h

    def form(i, j, k, p):
        r = a + (b - a) * i / n_r
        t = 0.5 * np.pi * j / n_t
        return np.array([r * np.cos(t), r * np.sin(t), h * k])
    m, _ids = pk.quader("hex8", n_r, n_t, 1, 1.0, 1.0, h, nu=nu, fy=fy, form=form)

    def mitte(P, Q):
        M = 0.5 * (P + Q)
        rp, rq = np.hypot(P[0], P[1]), np.hypot(Q[0], Q[1])
        if abs(rp - rq) < 1e-12 * b:
            f = rp / np.hypot(M[0], M[1])
            return np.array([M[0] * f, M[1] * f, M[2]])
        return M
    quadratisch_machen(m, mitte)
    X = np.asarray(m.nodes, float)
    tol = 1e-9 * b
    for n in range(m.nn):
        dofs = [d for d in (0, 1) if abs(X[n, d]) < tol]
        if abs(X[n, 2]) < tol or abs(X[n, 2] - h) < tol:
            dofs.append(2)
        if dofs:
            m.fix(int(n), dofs)
    innen = pk.randseiten(m, lambda P: bool(np.all(np.abs(np.hypot(P[:, 0], P[:, 1]) - a) < 1e-9 * b)))
    pk.spannung_auf_seiten(m, innen, lambda x: rz.p * np.array([x[0], x[1], 0.0]) / np.hypot(x[0], x[1]))
    return m


# ---- Kontakt über eine Fuge (Geometrie, Spaltelemente) --------------------
class FugeDruck(Fall):
    kurz, rechenart = "K1", "Kontakt"
    name = "Fuge ohne Zug, Druck geht durch (zwei Würfel, passende Netze)"
    soll = "σ_zz = −p = −100 N/mm² überall, u_oben = −p L/E (L = 2 m); Auflager = p A"
    grenze_text = "1 N/mm² an jedem Knoten, u 1 %, Auflager 1 %"
    exakt = True
    kontakt = True
    p = 100e6
    h = 0.5

    def modell(self, familie, ordnung, h, log, fy=None):
        m = geo_modell(ordnung, h, fy=fy)
        g = Geo(m)
        ku = g.quader("Unten", (0, 0, 0), (1, 1, 1), {"z1": "Fuge"})
        ko = g.quader("Oben", (0, 0, 1), (1, 1, 2), {"z0": "Fuge"})
        vernetzen(m, [ku, ko], familie, h, ordnung, log)
        t = DofBehaviour("free")
        kb = m.add_kontaktbedingung("Fuge", flaechennamen=["Fuge"], gegenflaechen=[],
                                    koerpernamen=["Oben"],
                                    behaviour={0: t, 1: t, 2: DofBehaviour("free", failure="zug")})
        b = fugen.kontaktfuge_ausfuehren(m, kb, log)
        if b.get("grund"):
            raise RuntimeError(f"Fuge nicht ausgeführt: {b['grund']}")
        return m, b

    def lagerung(self, m, p, federn=0.0):
        tol = 1e-9
        unten = lagern(m, lambda x: abs(x[2]) < tol, [2])
        lagern(m, lambda x: abs(x[0]) < tol, [0])
        lagern(m, lambda x: abs(x[1]) < tol, [1])
        oben = [n for n in np.flatnonzero(am_netz(m)) if abs(m.nodes[n, 2] - 2.0) < tol]
        if federn:
            k = federn / len(oben)
            for n in oben:
                m.fix(int(n), [0, 1, 2], stiffness=[k, k, k])
        seiten = pk.randseiten(m, lambda X: bool(np.all(np.abs(X[:, 2] - 2.0) < tol)))
        pk.spannung_auf_seiten(m, seiten, lambda x: np.array([0.0, 0.0, -p]))
        return unten, oben

    def bauen(self, familie, typ, ordnung, h, log):
        m, b = self.modell(familie, ordnung, h, log)
        unten, oben = self.lagerung(m, self.p)
        return m, {"unten": unten, "oben": oben, "spalt": b.get("spalt"), "p": self.p}

    def u_soll(self, p):
        return -p * 2.0 / E_ST

    def auswerten(self, m, res, meta):
        p = meta["p"]
        u = u3(res, m)
        uo = float(u[meta["oben"], 2].mean())
        du = (uo / self.u_soll(p) - 1) * 100
        S = knotenspannung(res, ecken_am_netz(m))
        dsv = max((abs(sv(s) - p) for s in S.values()), default=np.nan) / MPA
        R = float(res.reactions[meta["unten"], 2].sum())
        dR = (R / p - 1) * 100
        return [metrik("σ_v", dsv, 1.0, "N/mm²"), metrik("u_oben", du, 1.0, "%"),
                metrik("Auflager", dR, 1.0, "%")], f"{meta.get('spalt')} Spaltelemente"


class FugeZug(FugeDruck):
    kurz = "K2"
    name = "Fuge ohne Zug, Zug öffnet (zwei Würfel, oben in Federn)"
    soll = "Fundament trägt 0 (Zug −100 N/mm² auf dem Deckel), die Last hängt ganz in den Federn"
    grenze_text = "Fundamentkraft ≤ 1 % der Last (entspricht 1 N/mm² mittlerer Fugenspannung)"

    def bauen(self, familie, typ, ordnung, h, log):
        m, b = self.modell(familie, ordnung, h, log)
        unten, oben = self.lagerung(m, -self.p, federn=1e11)
        return m, {"unten": unten, "oben": oben, "spalt": b.get("spalt"), "p": -self.p}

    def auswerten(self, m, res, meta):
        F = self.p * 1.0
        R_f = float(res.reactions[meta["unten"], 2].sum())
        R_g = float(res.reactions[:, 2].sum())
        return [metrik("Fundament", R_f / F * 100, 1.0, "%"),
                metrik("Federn", (-R_g / F - 1) * 100, 1.0, "%")], f"{meta.get('spalt')} Spaltelemente"


# ---- Kontaktpaar mit Übermaß (strukturiert) ---------------------------------
def wuerfelpaar(typ, n, fy=None):
    """Zwei Einheitswuerfel uebereinander, jeder fuer sich vernetzt (eigene
    Knoten); Rueckgabe (m, Slave-Knoten, Master-Facetten)."""
    basis = "hex8" if typ == "hex20" else typ
    m, _ids = pk.quader(basis, n, n, n, 1.0, 1.0, 1.0, fy=fy)
    m.materials["S"].rho = 0.0
    nn0, ne0 = m.nn, len(m.elements)
    for i in range(nn0):
        m.add_node(*(m.nodes[i] + np.array([0.0, 0.0, 1.0])))
    for e in list(m.elements[:ne0]):
        m.add_element(e.typ, [int(k) + nn0 for k in e.nodes], "S", group="Oben")
    for e in m.elements[:ne0]:
        e.group = "Unten"
    if typ == "hex20":
        quadratisch_machen(m)
    unten_el = [i for i, e in enumerate(m.elements) if e.group == "Unten"]
    oben_el = [i for i, e in enumerate(m.elements) if e.group == "Oben"]
    tol = 1e-9
    X = np.asarray(m.nodes, float)
    master = []
    for i in unten_el:
        e = m.elements[i]
        for f in sl.FLAECHEN_ECKEN[e.typ]:
            kn = [int(e.nodes[a]) for a in f]
            if np.all(np.abs(X[kn, 2] - 1.0) < tol):
                master.append(kn)
    slave = sorted({int(k) for i in oben_el for k in m.elements[i].nodes if abs(X[int(k), 2] - 1.0) < tol})
    return m, slave, master


class UebermassFuge(Fall):
    kurz, rechenart = "K3", "Kontakt"
    name = "Presspassung, ebene Fuge (Kontaktpaar mit Übermaß)"
    soll = "σ = δ E/(2 L) = 355 N/mm² überall (δ = 3,38 mm), Auflager σ A"
    grenze_text = "1 N/mm² an jedem Knoten, Auflager 1 %"
    exakt = True
    kontakt = True
    h = 0.5
    sigma = pk.SIGMA_BEZUG

    def delta(self):
        return 2.0 * 1.0 * self.sigma / E_ST

    def modell(self, typ, h, fy=None):
        n = max(1, int(round(1.0 / h)))
        m, slave, master = wuerfelpaar(typ, n, fy=fy)
        m.contact_pairs.append(ContactPair("Fuge", slave_nodes=slave, master_faces=master,
                                           mu=0.0, search_radius=0.5 * h))
        tol = 1e-9
        unten = lagern(m, lambda x: abs(x[2]) < tol, [2])
        lagern(m, lambda x: abs(x[2] - 2.0) < tol, [2])
        lagern(m, lambda x: abs(x[0]) < tol, [0])
        lagern(m, lambda x: abs(x[1]) < tol, [1])
        lc = m.add_load_case("LF1")
        lc.gravity = [0, 0, 0]
        lc.uebermasse.append(Uebermass("Fuge", self.delta(), passmass="ebene Fuge"))
        return m, {"unten": unten, "n": n}

    def bauen(self, familie, typ, ordnung, h, log):
        return self.modell(typ, h)

    def sigma_soll(self):
        return self.sigma

    def auswerten(self, m, res, meta):
        s = self.sigma_soll()
        S = knotenspannung(res, ecken_am_netz(m))
        dsv = max((abs(sv(x) - s) for x in S.values()), default=np.nan) / MPA
        R = float(res.reactions[meta["unten"], 2].sum())
        return [metrik("σ_v", dsv, 1.0, "N/mm²"), metrik("Auflager", (R / s - 1) * 100, 1.0, "%")], \
            f"{meta['n']}³ Zellen je Würfel"


# ---- Plastizität ----------------------------------------------------------
def plastizitaet_an(m, laststufen=3, iterationen=60, toleranz=1e-6, verfestigung=VERFESTIGUNG):
    m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=verfestigung, laststufen=laststufen,
                                     iterationen=iterationen, toleranz=toleranz)


def sigma_eps_bilinear(sigma):
    """Einachsig: eps = sigma/E + (sigma - fy)/H."""
    H = pl.Plastizitaet(verfestigung=VERFESTIGUNG).H(E_ST)
    return sigma / E_ST + max(0.0, sigma - FY) / H


class Druckwuerfel(Fall):
    kurz, rechenart = "P1", "Plastizität"
    name = "Druckstab einachsig, bilinear verfestigend (fy 235, E_t/E 5 %)"
    soll = "p = 300 N/mm²: σ_v = p überall, u_oben = L (p/E + (p − fy)/H), L = 2 m"
    grenze_text = "1 N/mm² an jedem Knoten, u 1 %"
    exakt = True
    plastisch = True
    p = 300e6
    h = 0.5

    def bauen(self, familie, typ, ordnung, h, log):
        m = geo_modell(ordnung, h, fy=FY)
        g = Geo(m)
        k = g.quader("Stab", (0, 0, 0), (1, 1, 2))
        vernetzen(m, [k], familie, h, ordnung, log)
        unten, oben = FugeDruck.lagerung(self, m, self.p)
        plastizitaet_an(m)
        return m, {"unten": unten, "oben": oben, "p": self.p}

    def auswerten(self, m, res, meta):
        p = meta["p"]
        u = u3(res, m)
        uo = float(u[meta["oben"], 2].mean())
        soll = -2.0 * sigma_eps_bilinear(p)
        S = knotenspannung(res, ecken_am_netz(m))
        dsv = max((abs(sv(s) - p) for s in S.values()), default=np.nan) / MPA
        return [metrik("σ_v", dsv, 1.0, "N/mm²"), metrik("u_oben", (uo / soll - 1) * 100, 1.0, "%")], ""


class HillRohr(Fall):
    kurz, rechenart = "P2", "Plastizität"
    name = "Rohr unter Innendruck nach Hill, ideal plastisch (ν = 0,4999)"
    soll = "c/a = 1,5 bei p = 255,88 N/mm²: σ_v(b) = fy c²/b² = 199,69 N/mm², u_r(b) = k c²/(2 G b); fy 355"
    grenze_text = "1 N/mm² an jedem Eckknoten der Außenfläche, u_r 1 %"
    plastisch = True
    h = 0.025

    def bauen(self, familie, typ, ordnung, h, log):
        n_r = max(1, int(round(0.1 / h)))
        n_t = 2 * n_r
        hl = Hill()
        rz = pk.Hohlzylinder(p=hl.p(0.15))
        m = zylinder_modell(rz, typ, n_t, n_r, nu=0.4999, fy=hl.fy)
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.0, laststufen=1,
                                         iterationen=200, toleranz=1e-6)
        return m, {"hill": hl, "netz": f"{n_t} × {n_r}"}

    def auswerten(self, m, res, meta):
        hl = meta["hill"]
        c = 0.15
        X = np.asarray(m.nodes, float)
        r = np.hypot(X[:, 0], X[:, 1])
        aussen = [n for n in ecken_am_netz(m) if abs(r[n] - hl.b) < 1e-9]
        S = knotenspannung(res, aussen)
        s_soll = hl.punkt(c, hl.b)[0]
        werte = [(sv(S[n]) - s_soll) / MPA for n in S]
        d = max(werte, key=abs) if werte else np.nan
        u = u3(res, m)
        ur = np.mean([(u[n, 0] * X[n, 0] + u[n, 1] * X[n, 1]) / r[n] for n in aussen])
        du = (ur / hl.u_r(c, hl.b) - 1) * 100
        return [metrik("σ_v(b)", d, 1.0, "N/mm²"), metrik("u_r(b)", du, 1.0, "%")], \
            f"Netz {meta['netz']}, {(res.info.get('plastizitaet') or {}).get('verfahren', '')}"


# ---- Kontakt + Plastizität --------------------------------------------------
class FugeDruckPlastisch(FugeDruck):
    kurz, rechenart = "KP1", "Kontakt + Plastizität"
    name = "Fuge ohne Zug unter Druck, beide Würfel fließen (fy 235, E_t/E 5 %)"
    soll = "p = 300 N/mm²: σ_v = p überall, u_oben = L (p/E + (p − fy)/H), L = 2 m"
    grenze_text = "1 N/mm² an jedem Knoten, u 1 %, Auflager 1 %"
    plastisch = True
    p = 300e6

    def bauen(self, familie, typ, ordnung, h, log):
        m, b = self.modell(familie, ordnung, h, log, fy=FY)
        unten, oben = self.lagerung(m, self.p)
        plastizitaet_an(m)
        return m, {"unten": unten, "oben": oben, "spalt": b.get("spalt"), "p": self.p}

    def u_soll(self, p):
        return -2.0 * sigma_eps_bilinear(p)


class UebermassPlastisch(UebermassFuge):
    kurz, rechenart = "KP2", "Kontakt + Plastizität"
    name = "Presspassung, ebene Fuge, Übermaß bis ins Fließen (fy 235, E_t/E 5 %)"
    soll = "δ = 2 L ε(300 N/mm²) = 14,62 mm (ε_p 0,588 %): σ_v = 300 N/mm² überall, Auflager σ A"
    plastisch = True
    sigma = 300e6

    def delta(self):
        return 2.0 * 1.0 * sigma_eps_bilinear(self.sigma)

    def bauen(self, familie, typ, ordnung, h, log):
        m, meta = self.modell(typ, h, fy=FY)
        plastizitaet_an(m)
        return m, meta


FAELLE = [Kragarm(), LameZylinder(), KragarmZweiKoerper(), FugeDruck(), FugeZug(), UebermassFuge(),
          Druckwuerfel(), HillRohr(), FugeDruckPlastisch(), UebermassPlastisch()]


# --------------------------------------------------------------------------
# Rechnen
# --------------------------------------------------------------------------
def unbekannte(m):
    return 3 * int(am_netz(m).sum())


def zelle(fall, stufe, familie, typ, ordnung, faktor, h=None):
    h = fall.h * faktor if h is None else h
    z = {"fall": fall.kurz, "rechenart": fall.rechenart, "stufe": stufe, "familie": familie,
         "typ": typ, "h": h, "unbekannte": None, "kontakt_konv": None, "plast_konv": None,
         "pivots": None, "metriken": [], "ergebnis": "", "befund": "", "zeit": 0.0,
         "zeit_netz": 0.0, "zusatz": ""}
    log: list = []
    t0 = time.perf_counter()
    try:
        m, meta = fall.bauen(familie, typ, ordnung, h, log)
        z["zeit_netz"] = time.perf_counter() - t0
        typen = sorted({e.typ for e in m.elements})
        z["typen"] = typen
        z["unbekannte"] = unbekannte(m)
        fremd = [t for t in typen if t != typ]
        if fremd:
            z["befund"] = f"Netz enthält {', '.join(fremd)} statt nur {typ}"
        res = solver.solve_static(m, workers=1)
    except fugen.QuadratischeSeiten as ex:
        z["zeit"] = time.perf_counter() - t0
        z["ergebnis"] = "gesperrt"
        z["befund"] = str(ex)[:160]
        return z
    except Exception as ex:                      # noqa: BLE001 - die Matrix hält alles fest
        z["zeit"] = time.perf_counter() - t0
        z["ergebnis"] = "rot"
        z["befund"] = f"Abbruch: {type(ex).__name__}: {str(ex)[:300]}"
        z["trace"] = traceback.format_exc()[-1500:]
        return z
    z["zeit"] = time.perf_counter() - t0
    info = res.info or {}
    if fall.kontakt:
        z["kontakt_konv"] = info.get("contact_converged")
    if fall.plastisch:
        pz = info.get("plastizitaet") or {}
        z["plast_konv"] = pz.get("konvergiert")
        z["plast"] = {k: pz.get(k) for k in ("iterationen", "laststufen", "fliessend", "eps_p_max", "verfahren")}
    nw = info.get("loeser_nachweis") or {}
    z["pivots"] = nw.get("gestoerte_pivots_summe")
    z["singular"] = len(getattr(res, "singular", None) or [])
    try:
        mets, zus = fall.auswerten(m, res, meta)
    except Exception as ex:                      # noqa: BLE001
        z["ergebnis"] = "rot"
        z["befund"] = f"Auswertung gescheitert: {type(ex).__name__}: {ex}"
        return z
    z["metriken"] = mets
    z["zusatz"] = zus
    raus = [x for x in mets if not (abs(x["wert"]) <= x["grenze"])]
    nicht_konv = []
    if fall.kontakt and z["kontakt_konv"] is not True:
        nicht_konv.append(f"Kontakt konvergiert = {z['kontakt_konv']}")
    if fall.plastisch and z["plast_konv"] is not True:
        nicht_konv.append(f"Plastizität konvergiert = {z['plast_konv']}")
    netz = getattr(m, "_pm_netz", None) or {}
    z["netz"] = netz
    nicht_konform = bool(netz.get("doppelknoten") or netz.get("offene_innenseiten"))
    konform_text = (f"Netz nicht knotenkonform: {netz.get('doppelknoten', 0)} Orte mit zwei Knoten, "
                    f"{netz.get('offene_innenseiten', 0)} offene Innenseiten") if nicht_konform else ""
    if nicht_konv:
        z["ergebnis"] = "rot"
        z["befund"] = "; ".join(nicht_konv + ([konform_text] if konform_text else []))
    elif not raus:
        z["ergebnis"] = "grün"
        if konform_text:
            z["befund"] = "Hinweis: " + konform_text
    elif nicht_konform:
        z["ergebnis"] = "rot"
        z["besitzer"] = "Vernetzer"
        z["befund"] = (konform_text + "; " + ", ".join(f"{x['name']} {zahl(x['wert'])} {x['einheit']}"
                                                         for x in raus))
    elif fall.exakt:
        z["ergebnis"] = "rot"
        z["befund"] = ("falsches Ergebnis (homogener Zustand, jedes Element stellt ihn exakt dar): "
                       + ", ".join(f"{x['name']} {zahl(x['wert'])} {x['einheit']}" for x in raus))
    else:
        z["ergebnis"] = "gelb"
    return z


def zeile(z):
    mets = "; ".join(f"{x['name']} {'+' if x['wert'] > 0 else ''}{zahl(x['wert'])} {x['einheit']}"
                     for x in z["metriken"])
    k = {None: "–", True: "ja", False: "NEIN"}
    return (f"{z['fall']:4s} {z['stufe']:8s} {z['typ']:6s} h {zahl(z['h'], 4)} | "
            f"{z['ergebnis']:8s} | {mets or z['befund'][:90]} | "
            f"Kontakt {k.get(z['kontakt_konv'], z['kontakt_konv'])}, Plast. {k.get(z['plast_konv'], z['plast_konv'])}, "
            f"Pivots {z['pivots'] if z['pivots'] is not None else '–'} | "
            f"{ganz(z['unbekannte']) if z['unbekannte'] else '–'} Unb. | {zahl(z['zeit'], 1)} s")


def tet4_reihe(fall, faktoren=(0.5, 0.25, 0.125)):
    """Zusatz: bei welcher Feinheit erreicht tet4 die Grenze (wenn billig)?
    Halbe Kantenlaenge heisst rund achtmal so viele Unbekannte; weiter geht
    es nur, solange der naechste Lauf voraussichtlich unter 3 min bleibt."""
    aus = []
    for f in faktoren:
        z = zelle(fall, "Zusatz", "tet", "tet4", 1, f)
        print(zeile(z), flush=True)
        aus.append(z)
        if z["ergebnis"] != "gelb" or 8 * z["zeit"] > 180:
            break
    return aus


def markdown(alle, faelle, laufzeit):
    """Die Tabellen fuer docs/Pruefmatrix.md."""
    zeichen = {"grün": "grün", "gelb": "gelb", "rot": "**rot**", "gesperrt": "gesperrt"}
    k = {None: "–", True: "ja", False: "**nein**"}
    out = []
    arten = ["linear", "Kontakt", "Plastizität", "Kontakt + Plastizität"]
    stufen = [s for s, _f in STUFEN]
    out.append("| Rechenart | " + " | ".join(stufen) + " |")
    out.append("|---|" + "---|" * len(stufen))
    for art in arten:
        zeile_ = [art]
        for st in stufen:
            zs = [z for z in alle if z["rechenart"] == art and z["stufe"] == st]
            if not zs:
                zeile_.append("–")
                continue
            n = {e: sum(1 for z in zs if z["ergebnis"] == e) for e in ("grün", "gelb", "rot", "gesperrt")}
            zeile_.append(", ".join(f"{v} {zeichen[e]}" for e, v in n.items() if v))
        out.append("| " + " | ".join(zeile_) + " |")
    out.append("")
    out.append("Je Fall und Stufe (Tetraeder · Sechsflächner):")
    out.append("")
    out.append("| Fall | Rechenart | " + " | ".join(stufen) + " |")
    out.append("|---|---|" + "---|" * len(stufen))
    for f in faelle:
        zeile_ = [f"{f.kurz} {f.name}", f.rechenart]
        for st in stufen:
            zs = [z for z in alle if z["fall"] == f.kurz and z["stufe"] == st]
            zeile_.append(" · ".join(f"{z['typ']} {zeichen.get(z['ergebnis'], z['ergebnis'])}" for z in zs))
        out.append("| " + " | ".join(zeile_) + " |")
    out.append("")
    for f in faelle:
        out.append(f"### {f.kurz} {f.name}")
        out.append("")
        out.append(f"Soll: {f.soll}. Grenze: {f.grenze_text}."
                   + (" Homogener Zustand: jedes Element stellt ihn exakt dar, jede Überschreitung ist rot."
                      if f.exakt else ""))
        out.append("")
        out.append("| Stufe | Element | h [m] | Ergebnis | Fehler | Kontakt konv. | Plast. konv. | "
                   "gest. Pivots | Unbekannte | Zeit [s] | Bemerkung |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for z in [z for z in alle if z["fall"] == f.kurz]:
            mets = "; ".join(f"{x['name']} {'+' if x['wert'] > 0 else ''}{zahl(x['wert'])} {x['einheit']}"
                             for x in z["metriken"]) or "–"
            bem = z.get("befund") or ""
            if z["ergebnis"] == "gesperrt":
                bem = "fugen.QuadratischeSeiten: " + bem.split(":")[0]
            zus = z.get("zusatz") or ""
            bem = "; ".join(x for x in (bem, zus) if x).replace("|", "/")
            piv = "–" if z["pivots"] is None else ganz(z["pivots"])
            unb = ganz(z["unbekannte"]) if z["unbekannte"] else "–"
            out.append(f"| {z['stufe']} | {z['typ']} | {zahl(z['h'], 4)} | {zeichen.get(z['ergebnis'], z['ergebnis'])} | "
                       f"{mets} | {k.get(z['kontakt_konv'], z['kontakt_konv'])} | "
                       f"{k.get(z['plast_konv'], z['plast_konv'])} | {piv} | {unb} | {zahl(z['zeit'], 1)} | {bem} |")
        out.append("")
    out.append(f"Laufzeit gesamt {zahl(laufzeit / 60, 1)} min (einkernig, {DATUM}).")
    return "\n".join(out)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fall", nargs="*", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--ohne-zusatz", action="store_true")
    ap.add_argument("--md", default=None)
    a = ap.parse_args(argv)
    faelle = [f for f in FAELLE if not a.fall or f.kurz in a.fall]
    print(f"Prüfmatrix {DATUM}: {len(faelle)} Fälle x 3 Stufen x 2 Familien, "
          f"MKL_NUM_THREADS={os.environ.get('MKL_NUM_THREADS')}", flush=True)
    t0 = time.perf_counter()
    alle = []
    for fall in faelle:
        for stufe, familien in STUFEN:
            for familie, typ, ordnung, faktor in familien:
                z = zelle(fall, stufe, familie, typ, ordnung, faktor)
                print(zeile(z), flush=True)
                if z["ergebnis"] == "rot" and z.get("trace"):
                    print("   " + z["trace"].strip().splitlines()[-1], flush=True)
                alle.append(z)
        if not a.ohne_zusatz:
            e = next((z for z in alle if z["fall"] == fall.kurz and z["typ"] == "tet4"), None)
            if e is not None and e["ergebnis"] == "gelb":
                alle.extend(tet4_reihe(fall))
    gesamt = time.perf_counter() - t0
    print(f"Laufzeit gesamt {zahl(gesamt / 60, 1)} min", flush=True)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(markdown(alle, faelle, gesamt) + "\n")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"datum": DATUM, "laufzeit_s": gesamt, "zellen": alle,
                       "faelle": [{"kurz": f.kurz, "rechenart": f.rechenart, "name": f.name,
                                   "soll": f.soll, "grenze": f.grenze_text, "exakt": f.exakt,
                                   "h": f.h} for f in faelle]},
                      fh, ensure_ascii=False, indent=1, default=str)
    return alle


if __name__ == "__main__":
    main()
