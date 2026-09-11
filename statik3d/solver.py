"""
Loeser: lineare Statik (viele Lastfaelle mit einer Faktorisierung),
Kombinationen (Superposition oder nichtlinear bei Kontakt), Umhuellende,
Eigenschwingungen, lineares Knicken, Kontakt-Iteration, Nachlaufrechnung.

Vorzeichen Schnittgroessen (Staebe, DIN 1080): am positiven Schnittufer wirken
positive Schnittgroessen in Richtung der positiven lokalen Achsen.
    N > 0 Zug, My > 0 Zug an der +z-Seite (Oberseite bei horizontalem Stab).

Ergebnisobjekte (Results) enthalten die *linear ueberlagerbaren* Rohgroessen
(Verschiebungen, Lagerkraefte, lokale Stabendkraefte, Schnittkraefte je
Schale, Spannungen je Volumenelement). Abgeleitete Groessen (Vergleichs-
spannung, Ausnutzung, Schnittgroessen an Zwischenstellen) werden bei Bedarf
aus den Rohgroessen berechnet.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu, eigsh

from .model import Model, NDOF, Combination, LoadCase, Member, GRUNDSTELLUNG
from . import assemble as asm
from .elements import beam3d as bm
from .elements import shell as sh
from .elements import solid as sl
from . import parallel


# ==========================================================================
# Linearer Gleichungsloeser (Faktorisierung wiederverwendbar)
# ==========================================================================
def mkl_threads() -> int:
    """Threads fuer den Mehrkern-Loeser: alle Kerne bis auf einen.

    Der eine bleibt der Oberflaeche - sonst ruckelt das Fenster waehrend der
    Faktorisierung. Ein selbst gesetztes MKL_NUM_THREADS/OMP_NUM_THREADS hat
    Vorrang; wer die Zahl von Hand vorgibt, meint es so.

    Muss **vor** dem ersten Laden von mkl_rt laufen: MKL liest die Umgebung
    beim Initialisieren, spaeteres Setzen bleibt wirkungslos.
    """
    import os
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        wert = os.environ.get(name, "").strip()
        if wert.isdigit() and int(wert) > 0:
            return int(wert)
    n = max(1, (os.cpu_count() or 2) - 1)
    for name in ("MKL_NUM_THREADS", "OMP_NUM_THREADS"):
        os.environ.setdefault(name, str(n))
    return n


def _find_mkl():
    """MKL-Laufzeitbibliothek fuer pypardiso finden (pip install mkl legt sie
    ausserhalb des Suchpfads ab; im PyInstaller-Bundle liegt sie neben der exe
    entpackt in sys._MEIPASS)."""
    import os
    import glob
    import sys
    mkl_threads()
    if os.environ.get("PYPARDISO_MKL_RT"):
        return
    basen = [sys.prefix, os.path.join(sys.prefix, "Library", "bin"),
             os.path.join(sys.prefix, "lib"), "/usr/local/lib", "/usr/lib"]
    mei = getattr(sys, "_MEIPASS", "")
    if mei:
        # Im Bundle liegen die DLLs beieinander; Windows findet die
        # Abhaengigkeiten von mkl_rt nur, wenn das Verzeichnis im Suchpfad ist.
        basen[:0] = [mei, os.path.join(mei, "Library", "bin")]
        if hasattr(os, "add_dll_directory") and os.path.isdir(mei):
            try:
                os.add_dll_directory(mei)
            except OSError:
                pass
    pats = []
    for base in basen:
        pats += [os.path.join(base, "libmkl_rt.so*"), os.path.join(base, "mkl_rt*.dll"),
                 os.path.join(base, "libmkl_rt*.dylib")]
    try:
        import site
        for sp_ in site.getsitepackages():
            pats += [os.path.join(sp_, "..", "..", "libmkl_rt.so*"),
                     os.path.join(sp_, "..", "..", "..", "Library", "bin", "mkl_rt*.dll")]
    except Exception:
        pass
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            os.environ["PYPARDISO_MKL_RT"] = os.path.abspath(hits[-1])
            return

def _melde(progress, text: str, anteil: float = None) -> None:
    """Fortschritt melden - Text und, wenn bekannt, der Anteil (0…1).

    Empfaenger, die nur Text kennen (Protokoll, Kommandozeile, aeltere
    Aufrufer), bekommen weiterhin nur Text; die Oberflaeche nimmt den Anteil
    und macht daraus einen Balken statt eines endlos wandernden Streifens.
    """
    if progress is None:
        return
    if anteil is None:
        progress(text)
        return
    try:
        progress(text, float(anteil))
    except TypeError:
        progress(text)


NAMEN = {"pardiso": "MKL PARDISO", "cholmod": "CHOLMOD", "superlu": "SuperLU",
         "none": "keiner"}


def loeser_verfuegbar() -> str:
    """Welcher Loeser stuende bereit - ohne zu faktorisieren.

    Fuer die Meldung beim Start einer Rechnung. Bisher stand dort, wie viele
    Kerne der **Prozesspool fuers Vernetzen** hat; ueber das Loesen sagte das
    nichts, und bei fehlendem MKL war es schlicht irrefuehrend.
    """
    try:
        _find_mkl()
        import pypardiso                                   # noqa: F401
        return f"MKL PARDISO, {mkl_threads()} Threads"
    except Exception:                                      # noqa: BLE001
        pass
    try:
        from sksparse.cholmod import cholesky              # noqa: F401
        return "CHOLMOD"
    except Exception:                                      # noqa: BLE001
        pass
    return "SuperLU, einkernig (kein MKL/CHOLMOD im Programm)"


class LinearSolver:
    """Faktorisiert K einmal; solve() fuer beliebig viele rechte Seiten.
    Backends: pypardiso (MKL, mehrere Threads), scikit-sparse CHOLMOD, SuperLU.

    ``threads`` sagt, mit wie vielen Threads tatsaechlich gerechnet wurde.
    SuperLU ist streng einkernig und meldet darum immer 1 - das ist keine
    Einstellungssache, sondern eine Eigenschaft des Loesers.
    """

    def __init__(self, K: sparse.spmatrix, backend: str = None):
        self.n = K.shape[0]
        self.backend = "none"
        self.threads = 1
        be = backend or parallel.settings().solver_backend
        self._solve = None
        self._K = None
        self._ps = None
        if self.n == 0:
            self._solve = lambda b: np.zeros_like(b)
            return
        K = K.tocsc()
        self._K = K.tocsr()
        if be in ("auto", "pardiso"):
            try:
                _find_mkl()
                import pypardiso
                ps = pypardiso.PyPardisoSolver()
                Kcsr = K.tocsr()
                ps.factorize(Kcsr)
                self._ps = ps
                self._solve = lambda b: ps.solve(Kcsr, b)
                self.backend = "pardiso"
                self.threads = mkl_threads()
            except Exception:
                if be == "pardiso":
                    raise
        if self._solve is None and be in ("auto", "cholmod"):
            try:
                from sksparse.cholmod import cholesky
                f = cholesky(K)
                self._solve = lambda b: f(b)
                self.backend = "cholmod"
            except Exception:
                if be == "cholmod":
                    raise
        if self._solve is None:
            # MMD_AT_PLUS_A statt COLAMD: die Steifigkeitsmatrix ist
            # strukturell symmetrisch, COLAMD ordnet fuer unsymmetrisches LU.
            # Am Wuerfel mit 19.494 FHG gemessen: 22,5 statt 25,3 Mio. Eintraege
            # in L+U (11 % weniger Speicher) bei 3,2 statt 4,9 s.
            lu = splu(K, permc_spec="MMD_AT_PLUS_A")
            self._solve = lu.solve
            self.backend = "superlu"

    def freigeben(self) -> None:
        """Den Speicher der Faktorisierung zurueckgeben.

        MKL haelt die Faktorisierung ausserhalb von Python; pypardiso gibt sie
        nur auf ausdruecklichen Aufruf frei, nie beim Einsammeln des Objekts.
        Am Drehlager (1 028 724 FHG, 7 GB je Faktorisierung) wuchs der Prozess
        in der Kontakt-Iteration mit jedem Schritt um diese 7 GB, bis Pardiso
        nach 33 Schritten bei 113 GB mit Fehler -2 aufgab und SuperLU im
        Rueckfall am Speicher scheiterte (11.09.2026).
        """
        ps, self._ps = self._ps, None
        self._solve = None
        if ps is not None:
            try:
                ps.free_memory(everything=True)
            except Exception:                   # noqa: BLE001 - beim Aufraeumen nie sperren
                pass

    def __del__(self):
        try:
            self.freigeben()
        except Exception:                       # noqa: BLE001
            pass

    def beschreibung(self) -> str:
        """Wie in Protokoll und Statuszeile: Loeser und Threads."""
        return NAMEN.get(self.backend, self.backend) + (
            f", {self.threads} Threads" if self.threads > 1 else ", einkernig")

    def solve(self, b: np.ndarray, check: bool = True) -> np.ndarray:
        if self._solve is None:
            raise RuntimeError("Loeser ist freigegeben - erneut faktorisieren")
        b = np.asarray(b, float)
        x = self._solve(b)
        if not np.all(np.isfinite(x)):
            raise RuntimeError("Singulaeres System - Lagerung oder Vernetzung pruefen "
                               "(kinematische Kette / freie Knoten).")
        if check and self._K is not None and b.ndim == 1:
            nb = np.linalg.norm(b)
            if nb > 0:
                r = np.linalg.norm(self._K @ x - b) / nb
                if r > 1e-6:
                    raise RuntimeError(
                        f"Gleichungssystem numerisch singulaer (Residuum {r:.1e}) - "
                        "Lagerung, freie Bauteile oder Kontaktdefinition pruefen.")
        return x


# ==========================================================================
# Ergebnisse
# ==========================================================================
@dataclass
class Results:
    name: str = ""
    kind: str = "case"                      # case | combination | modal | buckling
    u: np.ndarray = None                    # (nn, 6) Verschiebungen/Verdrehungen
    reactions: np.ndarray = None            # (nn, 6) Auflagerreaktionen
    beam_end: dict = field(default_factory=dict)    # elem -> lokale Stabendkraefte (12,)
    beam_q: dict = field(default_factory=dict)      # elem -> Abschnittslasten (n,8): a, b, q1, q2
    shell_res: dict = field(default_factory=dict)   # elem -> [nx ny nxy mx my mxy]
    solid_res: dict = field(default_factory=dict)   # elem -> Spannungen (6,)
    feder_res: dict = field(default_factory=dict)   # elem -> lokale Federkraefte (6,)
    grenzschicht_res: dict = field(default_factory=dict)  # elem -> (sn, st1, st2)
    bimomente: dict = field(default_factory=dict)   # elem -> (B Anfang, B Ende) [Nm^2]
    woelb: dict = field(default_factory=dict)       # Knoten -> Verwoelbung [1/m]
    contact: list = field(default_factory=list)
    contact_forces: np.ndarray = None       # (nn, 3)
    modes: np.ndarray = None                # (nmodes, nn, 6)
    freqs: np.ndarray = None                # [Hz]
    buckling_factors: np.ndarray = None
    buckling_modes: np.ndarray = None
    singular: list = field(default_factory=list)   # freie Bewegungen (singular.py)
    info: dict = field(default_factory=dict)
    model: Model = None
    _cache: dict = field(default_factory=dict, repr=False)

    # ---- Kompatible abgeleitete Groessen ------------------------------------
    @property
    def umag(self) -> np.ndarray:
        return np.linalg.norm(self.u[:, :3], axis=1)

    @property
    def beam_forces(self) -> dict:
        """elem -> dict(L, N, Vy, Vz, Mt, My, Mz (Werte an Anfang/Ende), sig_max, util)."""
        if "beam_forces" not in self._cache:
            self._cache["beam_forces"] = {i: beam_end_forces(self.model, i, fl)
                                          for i, fl in self.beam_end.items()}
        return self._cache["beam_forces"]

    @property
    def shell_stress(self) -> dict:
        if "shell_stress" not in self._cache:
            self._cache["shell_stress"] = {i: shell_derived(self.model, i, r)
                                           for i, r in self.shell_res.items()}
        return self._cache["shell_stress"]

    @property
    def solid_stress(self) -> dict:
        if "solid_stress" not in self._cache:
            self._cache["solid_stress"] = {
                i: {"s": s, "vM": sl.von_mises(s), "principal": sl.principal(s)}
                for i, s in self.solid_res.items()}
        return self._cache["solid_stress"]

    @property
    def node_vm(self) -> np.ndarray:
        """Gemittelte Vergleichsspannung (Volumen/Schalen) bzw. Randspannung (Staebe) je Knoten."""
        if "node_vm" not in self._cache:
            m = self.model
            acc = np.zeros(m.nn)
            cnt = np.zeros(m.nn)
            for i, d in self.beam_forces.items():
                for n in m.elements[i].nodes:
                    acc[n] += d["sig_max"]
                    cnt[n] += 1
            for i, d in self.shell_stress.items():
                for n in m.elements[i].nodes:
                    acc[n] += d["vM"]
                    cnt[n] += 1
            for i, d in self.solid_stress.items():
                for n in m.elements[i].nodes:
                    acc[n] += d["vM"]
                    cnt[n] += 1
            with np.errstate(invalid="ignore", divide="ignore"):
                self._cache["node_vm"] = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
        return self._cache["node_vm"]

    def stations(self, n: int = None) -> dict:
        """Schnittgroessen aller Stabelemente an n Stellen: elem -> dict(x, N, Vy, ...)."""
        n = n or self.model.design.stations
        key = ("stations", n)
        if key not in self._cache:
            self._cache[key] = {i: beam_station_forces(self.model, self, i, n)
                                for i in self.beam_end}
        return self._cache[key]

    def member_forces(self, member: Member, n: int = None) -> dict:
        return member_forces(self.model, self, member, n)

    def max_utilisation(self) -> Optional[float]:
        vals = [d["util"] for d in self.beam_forces.values() if d["util"] is not None]
        return max(vals) if vals else None

    # ---- Superposition ------------------------------------------------------
    @staticmethod
    def combine(model: Model, parts: list, name: str = "", kind: str = "combination") -> "Results":
        """Lineare Ueberlagerung: parts = [(Results, Faktor), ...]."""
        nn = model.nn
        out = Results(name=name, kind=kind, model=model)
        out.u = np.zeros((nn, NDOF))
        out.reactions = np.zeros((nn, NDOF))
        for r, f in parts:
            if not f:
                continue
            out.u += f * r.u
            out.reactions += f * r.reactions
            for i, v in r.beam_end.items():
                out.beam_end[i] = out.beam_end.get(i, 0.0) + f * v
            for i, v in r.beam_q.items():
                out.beam_q[i] = asm.abschnitte_zusammen(out.beam_q.get(i),
                                                        asm.skaliere_abschnitte(v, f))
            for i, v in r.shell_res.items():
                out.shell_res[i] = out.shell_res.get(i, 0.0) + f * v
            for i, v in r.solid_res.items():
                out.solid_res[i] = out.solid_res.get(i, 0.0) + f * v
        out.info = {"ndof": model.ndof, "superposition": True,
                    "factors": {r.name: f for r, f in parts}}
        return out

    def scaled(self, f: float, name: str = "") -> "Results":
        return Results.combine(self.model, [(self, f)], name or self.name, self.kind)

    # ---- Ausgabe --------------------------------------------------------------
    def summary(self) -> str:
        s = []
        if self.name:
            s.append(f"Ergebnis                : {self.name} ({self.kind})")
        s += [f"Freiheitsgrade gesamt   : {self.info.get('ndof', '?')}",
              f"davon aktiv             : {self.info.get('nfree', '?')}",
              f"Rechenzeit              : {self.info.get('time', 0):.3f} s"]
        if self.info.get("solver"):
            s.append(f"Gleichungsloeser        : {self.info['solver']}")
        if self.u is not None and self.u.size:
            i = int(np.argmax(self.umag))
            s.append(f"max. Verschiebung       : {self.umag[i]*1000:.4f} mm (Knoten {i})")
        try:
            nv = self.node_vm
            if nv is not None and nv.size and np.any(np.isfinite(nv)):
                s.append(f"max. Vergleichsspannung : {np.nanmax(nv)/1e6:.2f} MPa")
        except Exception:
            pass
        if self.reactions is not None and self.reactions.size:
            R = self.reactions[:, :3].sum(axis=0)
            s.append(f"Summe Auflagerkraefte   : [{R[0]:.1f}, {R[1]:.1f}, {R[2]:.1f}] N")
        if self.contact:
            from . import contact as ct
            s.append(ct.summary(self.contact))
            if self.info.get("contact_iterations"):
                s.append(f"Kontakt-Iterationen     : {self.info['contact_iterations']}"
                         + ("" if self.info.get("contact_converged", True)
                            else "  (NICHT konvergiert)"))
        if self.freqs is not None:
            s.append("Eigenfrequenzen [Hz]    : "
                     + ", ".join(f"{f:.3f}" for f in self.freqs[:10]))
        if self.buckling_factors is not None:
            s.append("Knicklastfaktoren       : "
                     + ", ".join(f"{f:.3f}" for f in self.buckling_factors[:10]))
        return "\n".join(s)


# ==========================================================================
# Abgeleitete Stabgroessen
# ==========================================================================
def beam_end_forces(model: Model, i: int, fl: np.ndarray) -> dict:
    e = model.elements[i]
    sec = model.sections[e.sec]
    mat = model.materials[e.mat]
    L = model.element_length(i)
    N = (-fl[0], fl[6])
    Vy = (-fl[1], fl[7])
    Vz = (-fl[2], fl[8])
    Mt = (-fl[3], fl[9])
    My = (-fl[4], fl[10])
    Mz = (-fl[5], fl[11])
    sig = max(abs(N[0]), abs(N[1])) / sec.A
    if sec.zmax > 0:
        sig += max(abs(My[0]), abs(My[1])) * sec.zmax / max(sec.Iy, 1e-20)
    if sec.ymax > 0:
        sig += max(abs(Mz[0]), abs(Mz[1])) * sec.ymax / max(sec.Iz, 1e-20)
    fy = mat.yield_strength(sec.t_max) if mat.fy else None
    return {"L": L, "N": N, "Vy": Vy, "Vz": Vz, "Mt": Mt, "My": My, "Mz": Mz,
            "sig_max": sig, "util": sig / fy if fy else None}


def beam_station_forces(model: Model, res: Results, i: int, n: int = 9) -> dict:
    """Schnittgroessen entlang eines Stabelements an n Stellen (x von 0 bis L).

    Gleichgewicht am Teilstab: Stabendkraefte am Anfang plus die Resultierende
    der Abschnittslasten ueber [0, x] und ihr Moment um x. Bei einer
    abschnittsweisen Last knickt der Querkraftverlauf an den Abschnittsenden;
    liegt ein Abschnittsende zwischen zwei Stellen, steht es nicht im Feld -
    die Stellen sind gleichmaessig verteilt, n hoch genug waehlen.
    """
    fl = res.beam_end[i]
    L = model.element_length(i)
    q = res.beam_q.get(i)
    x = np.linspace(0.0, L, n)
    # Lastresultierende ueber [0,x] und deren Moment um die Stelle x
    Q, Mq = asm.lastresultierende(q, x)                            # (n,3)
    N = -fl[0] - Q[:, 0]
    Vy = -fl[1] - Q[:, 1]
    Vz = -fl[2] - Q[:, 2]
    Mt = np.full(n, -fl[3])
    My = -fl[4] - fl[2] * x - Mq[:, 2]
    Mz = -fl[5] + fl[1] * x + Mq[:, 1]
    return {"x": x, "L": L, "N": N, "Vy": Vy, "Vz": Vz, "Mt": Mt, "My": My, "Mz": Mz}


def member_forces(model: Model, res: Results, member: Member, n: int = None) -> dict:
    """Schnittgroessen entlang eines Stabes (Kette von Elementen), x ab Stabanfang."""
    n = n or model.design.stations
    out = {k: [] for k in ("x", "N", "Vy", "Vz", "Mt", "My", "Mz")}
    out["elem"] = []
    x0 = 0.0
    for i in member.elements:
        st = beam_station_forces(model, res, i, n)
        for k in ("N", "Vy", "Vz", "Mt", "My", "Mz"):
            out[k].append(st[k])
        out["x"].append(st["x"] + x0)
        out["elem"].append(np.full(n, i))
        x0 += st["L"]
    for k in out:
        out[k] = np.concatenate(out[k]) if out[k] else np.zeros(0)
    out["L"] = x0
    return out


def shell_derived(model: Model, i: int, r: np.ndarray) -> dict:
    e = model.elements[i]
    t = model.shells[e.sec].t
    n_forces = r[:3]
    m_forces = r[3:]
    sig_mem = n_forces / t
    sig_bend = 6.0 * m_forces / t ** 2
    sig_top = sig_mem + sig_bend
    sig_bot = sig_mem - sig_bend

    def vm(s):
        sx, sy, sxy = s
        return float(np.sqrt(sx ** 2 - sx * sy + sy ** 2 + 3 * sxy ** 2))

    X = model.nodes[e.nodes]
    T3, _, _ = sh.shell_frame(X[0], X[1], X[2])
    return {"n": n_forces, "m": m_forces, "sig_top": sig_top, "sig_bot": sig_bot,
            "vM_top": vm(sig_top), "vM_bot": vm(sig_bot),
            "vM": max(vm(sig_top), vm(sig_bot)), "T3": T3}


# ==========================================================================
# Statisches System
# ==========================================================================
class StaticSystem:
    """Assemblierte und faktorisierte Steifigkeit fuer beliebig viele Lastfaelle."""

    def __init__(self, model: Model, workers: int = None, progress=None,
                 aktiv=None, situation: str = ""):
        t0 = time.time()
        self.model = model
        #: Situation: Maske der wirksamen Elemente (None = alle) und ihr Name
        self.aktiv = None if aktiv is None else np.asarray(aktiv, bool)
        self.situation = situation
        self.K = asm.stiffness(model, workers, self.aktiv)
        self.fixed, self.vals = asm.constrained_dofs(model, self.K)
        self.fi = np.where(~self.fixed)[0]
        self.si = np.where(self.fixed)[0]
        self.Kff = self.K[self.fi][:, self.fi].tocsc()
        self.Kfs = self.K[self.fi][:, self.si].tocsc() if np.any(self.vals[self.si]) else None
        if progress:
            _melde(progress, f"Gleichungssystem aufgestellt ({len(self.fi)} aktive FHG)", 0.20)
        self._solver = None
        self.backend = "-"
        #: Freie Bewegungen und ihre Hilfsfesselung - erst nach einem sonst
        #: unloesbaren System belegt (:meth:`hilfsfesselung`)
        self.singular: list = []
        #: "" (noch nicht gesucht) | "grob" (nur die Vorpruefung, ohne Befund)
        #: | "voll" (wirklich gesucht)
        self._gesucht = ""
        #: Die Hilfsfesselung als Lagrange-Rand: (m, n_frei)-Matrix der
        #: festgehaltenen Bewegungen, None solange keine noetig war.
        self._Vf = None
        self._V = None
        self._progress = progress
        self.t_assemble = time.time() - t0
        if not model.has_contact:
            _ = self.solver          # sofort faktorisieren (bei Kontakt erst mit Kc)

    @property
    def solver(self) -> LinearSolver:
        """Faktorisierung der Grundsteifigkeit (bei Bedarf)."""
        if self._solver is None:
            t0 = time.time()
            try:
                self._solver = LinearSolver(self.gerandet(self.Kff))
            except (RuntimeError, ValueError) as ex:
                # "Factor is exactly singular" sagt niemandem, was fehlt
                from .diagnose import singulaer_text
                raise RuntimeError(singulaer_text(self.model, ex, self)) from None
            self.backend = self._solver.backend
            self.t_assemble += time.time() - t0
            if self._progress:
                _melde(self._progress,
                       f"Faktorisiert ({self._solver.beschreibung()}, "
                       f"{time.time() - t0:.2f} s)", 0.32)
        return self._solver

    def gerandet(self, Kff):
        """Kff mit dem Lagrange-Rand der Hilfsfesselung.

        Aus K wird

            [ K    V^T ]   [ u ]   [ F ]
            [ V     0  ] * [ l ] = [ 0 ]

        Die Zusatzzeilen erzwingen ``V u = 0`` - der Starrkoerperanteil der
        freien Bewegungen ist damit exakt null statt nur klein. Die Haltekraft
        ist ``V^T l`` und verteilt sich damit ueber das Teil **wie die
        Bewegung selbst**; das ist die Traegheitsentlastung, und genau darum
        geht durch den Mittelschnitt eines frei schwebenden Stabes die halbe
        Last und nicht die ganze. Ein einzelner gesperrter Freiheitsgrad
        taete das nicht - er leitete alles in einen Punkt.

        Der Rand kostet zwei Eintraege je Nichtnull von V. Die fruehere
        Straffeder ``K + k*V^T V`` kostete deren Quadrat: am Drehlagermodell
        826 GB (siehe :func:`singular.stabilisieren`).
        """
        if self._Vf is None or self._Vf.shape[0] == 0:
            return Kff
        m = self._Vf.shape[0]
        return sparse.bmat([[Kff, self._Vf.T],
                            [self._Vf, sparse.csr_matrix((m, m))]], format="csc")

    @property
    def _rand(self) -> int:
        """Zahl der Randzeilen der Hilfsfesselung (0 = keine)."""
        return 0 if self._Vf is None else int(self._Vf.shape[0])

    def freie_bewegungen(self, erzwingen: bool = False) -> list:
        """Bewegungen, die das Modell nicht haelt - gesucht, nicht gefesselt.

        Die Suche laeuft hoechstens einmal je System. Nach einer geglueckten
        Rechnung soll sie nichts kosten: dann laeuft sie nur, wenn ueberhaupt
        ein Teiltragwerk **ohne jedes** feste Lager dasteht - zwei
        Topologielaeufe, die die Modellpruefung ohnehin macht.

        ``erzwingen`` hebt diese Vorpruefung auf. Nach einem Abbruch muss das
        sein: ein Bauteil kann ein Lager haben und trotzdem beweglich sein -
        eine Platte, die nur senkrecht gehalten ist, verschiebt sich in ihrer
        Ebene. Die grobe Vorpruefung saehe sie als gehalten an.
        """
        if self._gesucht == "voll" or (self._gesucht and not erzwingen):
            return self.singular
        from .diagnose import gehaltene_knoten, teiltragwerke
        from . import singular as sg
        try:
            if not erzwingen:
                fest, _kontakt = gehaltene_knoten(self.model)
                if all(set(g) & fest for g in teiltragwerke(self.model)):
                    self._gesucht = "grob"
                    return []
            self.singular = sg.restfreiheiten(self.model)
        except Exception:                 # noqa: BLE001 - eine Diagnose darf nie sperren
            self.singular = []
        self._gesucht = "voll"
        return self.singular

    def hilfsfesselung(self) -> bool:
        """Die freien Bewegungen mit je einer Zeile festhalten - als Rand.

        Statt abzubrechen wird weitergerechnet: jede Bewegung, die das Modell
        nicht haelt, bekommt eine Zeile ``v^T u = 0``. Weil K·v = 0 ist,
        bleiben Spannungen und Dehnungen davon unberuehrt - nur der
        Starrkoerperanteil der Verschiebung faellt weg, und der ist ohnehin
        willkuerlich (:meth:`ohne_starrkoerper` nimmt ihn zusaetzlich heraus,
        falls doch etwas uebrig bleibt).

        Hier stand bis zuletzt eine Straffeder ``K + k*V^T V``. Das aeussere
        Produkt hat so viele Eintraege wie die Zeile Nichtnullen im Quadrat;
        am Drehlagermodell waren das 6,9e10 - rund 826 GB, und der Rechner
        stand still. Der Rand leistet dasselbe exakt und kostet zwei Eintraege
        je Nichtnull (:meth:`gerandet`).

        Rueckgabe True, wenn eine Fesselung eingebaut wurde.
        """
        if self._Vf is not None:
            return False
        from . import singular as sg
        try:
            V, sing = sg.hilfsfesselung(self.model,
                                        self.freie_bewegungen(erzwingen=True),
                                        frei=self.fi)
        except Exception:                 # noqa: BLE001 - das darf nie sperren
            return False
        if not sing or V.shape[0] == 0:
            return False
        self.singular, self._V = sing, V
        self._Vf = sparse.csr_matrix(V[:, self.fi])
        for x in sing:
            x.gefesselt = True
        self._solver = None
        return True

    def ohne_starrkoerper(self, u: np.ndarray) -> np.ndarray:
        """Den willkuerlichen Starrkoerperanteil der Hilfsfesselung abziehen."""
        if self._V is None:
            return u
        from . import singular as sg
        return sg.bereinigen(self._V, u)

    def solve(self, F: np.ndarray, K_extra: sparse.spmatrix = None,
              F_extra: np.ndarray = None, us: np.ndarray = None) -> np.ndarray:
        """Loesen fuer Lastvektor F; optional zusaetzliche Steifigkeit (Kontakt)
        und vorgegebene Verschiebungen ``us`` des Lastfalls (Zwangsverformungen,
        wirksam nur an gesperrten FHG): K_ff u_f = F_f - K_fs u_s."""
        u = self.vals.copy()
        if us is not None:
            u[self.si] += us[self.si]
        rhs = F[self.fi]
        if F_extra is not None:
            rhs = rhs + F_extra[self.fi]
        vorgabe = np.any(u[self.si])
        try:
            if K_extra is None:
                if vorgabe:
                    if self.Kfs is None:
                        self.Kfs = self.K[self.fi][:, self.si].tocsc()
                    rhs = rhs - self.Kfs @ u[self.si]
                u[self.fi] = self._geloest(self.solver, rhs)
            else:
                Kt = (self.K + K_extra)
                Ktff = Kt[self.fi][:, self.fi].tocsc()
                if vorgabe:
                    Ktfs = Kt[self.fi][:, self.si]
                    rhs = rhs - Ktfs @ u[self.si]
                ls = LinearSolver(self.gerandet(Ktff))
                self.backend = ls.backend
                try:
                    u[self.fi] = self._geloest(ls, rhs)
                finally:
                    # Die Faktorisierung mit Kontaktsteifigkeit gilt nur fuer
                    # diesen Schritt - sofort zurueckgeben, nicht erst beim
                    # Einsammeln (siehe LinearSolver.freigeben)
                    ls.freigeben()
        except (RuntimeError, ValueError) as ex:
            # Singulaer (Faktorisierung oder Residuum): sagen, was dem Modell fehlt
            if "Teiltragwerk" in str(ex) or "ohne Netz" in str(ex):
                raise
            from .diagnose import singulaer_text
            raise RuntimeError(singulaer_text(self.model, ex, self)) from None
        return u

    def _geloest(self, ls: "LinearSolver", rhs: np.ndarray) -> np.ndarray:
        """Loesen mit dem Lagrange-Rand: rechte Seite auffuellen, Rand abschneiden.

        Die Randzeilen fordern ``V u = 0``; ihre rechte Seite ist null. Die
        Multiplikatoren am Ende der Loesung sind die Haltekraefte und gehen
        den Aufrufer nichts an.
        """
        m = self._rand
        if not m:
            return ls.solve(rhs)
        x = ls.solve(np.concatenate([rhs, np.zeros(m)]))
        return np.asarray(x, float).ravel()[:len(rhs)]

    def reactions(self, u: np.ndarray, F: np.ndarray, K_extra=None) -> np.ndarray:
        K = self.K if K_extra is None else (self.K + K_extra)
        R = np.zeros(self.model.ndof)
        R[self.si] = (K @ u)[self.si] - F[self.si]
        # Federlager (Knoten-, Linien- und Flaechenlager): Federkraft als Reaktion
        from . import supports as sup
        lin, _ = sup.split(sup.expand(self.model))
        for e in lin:
            if e.typ == "spring" and e.stiffness:
                R[e.index] += -e.stiffness * u[e.index]
        return R


# ==========================================================================
# Lasten eines Lastfalls / einer Kombination
# ==========================================================================
def case_loads(model: Model, factors: dict, aktiv=None) -> tuple:
    """(F, feq, q, temp) fuer eine Linearkombination von Lastfaellen.
    feq: elem -> lokale aequivalente Knotenlasten (unkondensiert),
    q: elem -> lokale Streckenlast (2,3), temp: elem -> dT.
    ``aktiv``: abgeschaltete Elemente einer Situation tragen keine Last."""
    F = np.zeros(model.ndof)
    feq: dict = {}
    q: dict = {}
    temp: dict = {}
    for name, f in factors.items():
        if not f:
            continue
        lc = model.case(name)
        F += f * asm.load_vector(model, lc, aktiv)
        for i, v in asm.element_equivalent_loads(model, lc, aktiv).items():
            feq[i] = feq.get(i, 0.0) + f * v
        for i, v in asm.element_distributed_loads(model, lc, aktiv).items():
            q[i] = asm.abschnitte_zusammen(q.get(i), asm.skaliere_abschnitte(v, f))
        for tl in lc.temp_loads:
            temp[tl.elem] = temp.get(tl.elem, 0.0) + f * tl.dT
        # Anfangsspannungen der Vorspannung in Volumen - fuer die Spannungs-
        # rueckrechnung (sigma = D eps - sigma0); unter dem Schluessel "sigma0",
        # damit die Elementnummern von temp unberuehrt bleiben
        for v in getattr(lc, "vorspannungen", None) or []:
            if getattr(v, "art", "stab") == "koerper" and v.kraft:
                sig = temp.setdefault("sigma0", {})
                for i, s0 in asm.solid_prestress(model, v).items():
                    sig[i] = sig.get(i, 0.0) + f * s0
    return F, feq, q, temp


def case_uebermass(model: Model, factors: dict) -> dict:
    """{Name der Fuge: Gesamtueberdeckung [m]} einer Linearkombination.

    Das Uebermass wird wie jede andere Last mit dem Faktor der Kombination
    vervielfacht. Geometrisch ist ein Uebermass zwar keine Last, sondern ein
    Mass - aber es steht in einem Lastfall, und ein Lastfall geht mit seinem
    Beiwert in die Kombination ein. Wer das nicht will, legt das Uebermass in
    einen staendigen Lastfall mit gamma = 1,0.
    """
    aus: dict = {}
    for name, f in (factors or {}).items():
        if not f or name not in model.load_cases:
            continue
        for u in (getattr(model.case(name), "uebermasse", None) or []):
            ziel = str(u.ziel)
            aus[ziel] = aus.get(ziel, 0.0) + float(f) * float(u.ueberdeckung)
    return {k: v for k, v in aus.items() if v}


def case_prescribed(model: Model, factors: dict, warn=None):
    """Vorgegebene Verschiebungen (Zwangsverformungen) einer Linearkombination
    von Lastfaellen als Vektor ueber alle FHG - oder None, wenn es keine gibt.
    ``warn(text)`` meldet vorgegebene FHG ohne Lager (dort unwirksam)."""
    us = np.zeros(model.ndof)
    gibt = False
    for name, f in factors.items():
        if not f:
            continue
        lc = model.case(name)
        if not lc.zwangsverformungen:
            continue
        gibt = True
        for zv in lc.zwangsverformungen:
            for d in zv.dofs:
                us[NDOF * int(zv.node) + int(d)] += f * float(zv.u[d])
        if warn is not None:
            ohne = model.zwang_ohne_lager(name)
            if ohne:
                namen = ("ux", "uy", "uz", "phix", "phiy", "phiz")
                warn(f"Zwangsverformung im Lastfall {name} ohne Lager - unwirksam: "
                     + ", ".join(f"Knoten {n} {namen[d]}" for n, d in ohne[:8])
                     + (" ..." if len(ohne) > 8 else ""))
    return us if gibt else None


# ==========================================================================
# Nachlaufrechnung
# ==========================================================================
def _post_chunk(model: Model, idx: list[int], extra: dict) -> list:
    u = extra["u"]
    feq = extra["feq"]
    temp = extra["temp"]
    out = []
    for i in idx:
        e = model.elements[i]
        mat = model.materials[e.mat]
        X = model.nodes[e.nodes]
        d = asm.element_dofs(e, model)
        ue = u[d]
        if e.typ in asm.LINE_TYPES:
            f0 = feq.get(i, np.zeros(12))
            if model.stab_woelbt(e):
                # 14 FHG: Stabendkraefte und die Bimomente an beiden Enden
                kl, T3, L = asm.beam_woelb_local(model, e)
                ul = asm.transform14(T3) @ ue
                A = asm.beam_versatz(e)
                if A is not None:
                    A14 = np.eye(14)
                    A14[:12, :12] = A
                    ul = A14 @ ul
                f14 = np.zeros(14)
                f14[:12] = f0
                fl = kl @ ul - f14
                out.append((i, "beam", fl[:12]))
                out.append((i, "bimoment", (-float(fl[12]), float(fl[13]))))
                continue
            kl, T3, T, L = asm.beam_local(model, e)
            ul = T @ ue
            A = asm.beam_versatz(e)
            if A is not None:
                ul = A @ ul                     # Verschiebung des Stabendes hinter dem Versatz
            kl_s, f_s, rec = kl, f0, None
            if getattr(e, "hinge_springs", None):
                kl_s, f_s, rec = asm.hinge_springs(kl, f0, e.hinge_springs)
            if e.hinges:
                _, _, cond = asm.condense(kl_s, f_s, e.hinges)
                c, r, Kcc_inv, Kcr = cond
                ul = ul.copy()
                ul[c] = Kcc_inv @ (f_s[c] - Kcr @ ul[r])
            if rec is not None:
                ul = asm.hinge_local_disp(rec, ul)      # Stabende hinter der Feder
            fl = kl @ ul - f0
            out.append((i, "beam", fl))
        elif e.typ in asm.SHELL_TYPES:
            prop = model.shells[e.sec]
            t = prop.t
            if asm.schalen_formulierung(e, prop) != "dkt":
                from .elements import shell_rm
                lam = asm.laminat_von(model, prop)
                st = shell_rm.stress_schale(e.typ, X, mat.E, mat.nu, t, ue, laminat=lam)
                acc = np.concatenate([np.asarray(st["n"], float), np.asarray(st["m"], float)])
                if i in temp:
                    A_ = lam.A if lam is not None else sh._material_matrices(mat.E, mat.nu, t)[0]
                    acc[:3] -= A_ @ (mat.alpha * temp[i] * np.array([1.0, 1.0, 0.0]))
                out.append((i, "shell", acc))
                continue
            tris = [(0, 1, 2)] if e.typ == "shell3" else [(0, 1, 2), (0, 2, 3)]
            acc = np.zeros(6)
            # Beim Viereck haben die beiden Dreiecke verschiedene lokale
            # Systeme (x laeuft einmal an der Kante, einmal an der Diagonale).
            # Vor dem Mitteln werden beide in das Elementsystem gedreht -
            # sonst werden Groessen aus zwei Systemen addiert.
            T3e, _xy, _A = sh.shell_frame(X[0], X[1], X[2])
            for tri in tris:
                idx6 = []
                for n in tri:
                    idx6.extend(range(6 * n, 6 * n + 6))
                st = sh.shell3_stress(X[tri[0]], X[tri[1]], X[tri[2]],
                                      mat.E, mat.nu, t, ue[idx6])
                n_v, m_v = st["n"], st["m"]
                if tri != (0, 1, 2):
                    T3t, _xy2, _A2 = sh.shell_frame(X[tri[0]], X[tri[1]], X[tri[2]])
                    phi = sh.frame_winkel(T3t, T3e)
                    n_v = sh.dreh_tensor(n_v, -phi)
                    m_v = sh.dreh_tensor(m_v, -phi)
                acc[:3] += n_v
                acc[3:] += m_v
            acc /= len(tris)
            if i in temp:
                Dm = sh._material_matrices(mat.E, mat.nu, t)[0]
                acc[:3] -= Dm @ (mat.alpha * temp[i] * np.array([1.0, 1.0, 0.0]))
            out.append((i, "shell", acc))
        elif e.typ in asm.SOLID_TYPES:
            mitte = sl.AUSWERTEPUNKTE[e.typ][0]
            s_ = sl.stress_points(e.typ, X, mat.E, mat.nu, ue, punkte=[mitte])[0]
            s_ = np.asarray(s_, float)
            if i in temp:
                s_ = s_ - sl.D_matrix(mat.E, mat.nu) @ (
                    mat.alpha * temp[i] * np.array([1.0, 1.0, 1.0, 0, 0, 0]))
            sig0 = temp.get("sigma0") if isinstance(temp, dict) else None
            if sig0 and i in sig0:
                s_ = s_ - np.asarray(sig0[i], float)      # Vorspannung: sigma = D eps - sigma0
            out.append((i, "solid", s_))
        elif e.typ in asm.PLANE_TYPES:
            from .elements import ebene
            t = model.shells[e.sec].t if e.sec and e.sec in model.shells else 1.0
            zustand = getattr(e, "zustand", "spannung")
            s_ = np.asarray(ebene.stress_ebene(e.typ, X, mat.E, mat.nu, t, zustand, ue), float)
            if i in temp:
                # Waermedehnung ohne Spannung: sigma = D (eps - eps_T)
                if zustand == "spannung":
                    k = mat.E * mat.alpha * temp[i] / (1.0 - mat.nu)
                    s_[0] -= k
                    s_[1] -= k
                else:
                    k = mat.E * mat.alpha * temp[i] / (1.0 - 2.0 * mat.nu)
                    s_[:3] -= k
            out.append((i, "solid", s_))
        elif e.typ == "feder":
            from .elements import verbindung as vb
            fp = model.federn[e.sec]
            T3 = vb.feder_achsen(X[0], X[1], fp.achse, e.roll)
            out.append((i, "feder", np.asarray(vb.feder_kraefte(fp.k, T3, ue), float)))
        elif e.typ in asm.GRENZSCHICHT_TYPES:
            from .elements import verbindung as vb
            gp = model.grenzschichten[e.sec]
            k = len(e.nodes) // 2
            out.append((i, "grenzschicht",
                        np.asarray(vb.grenzschicht_spannung(X[:k], X[k:], gp.kn, gp.kt, ue), float)))
    return out


def postprocess(model: Model, u: np.ndarray, res: Results, feq: dict = None,
                q: dict = None, temp: dict = None, workers: int = None, aktiv=None):
    """Rohgroessen je Element aus dem Verschiebungsvektor u (ndof,).
    Abgeschaltete Elemente (``aktiv`` False) bekommen Nullen: sie wirken nicht."""
    feq = feq if feq is not None else {}
    q = q if q is not None else {}
    temp = temp if temp is not None else {}
    idx = asm.aktive_indizes(model, aktiv)
    items = parallel.map_elements(_post_chunk, model, idx, workers=workers,
                                  extra={"u": u, "feq": feq, "temp": temp})
    if aktiv is not None:
        inaktiv = [i for i in range(len(model.elements)) if not aktiv[i]]
        res.info["inaktiv"] = inaktiv
        for i in inaktiv:
            e = model.elements[i]
            if e.typ in asm.LINE_TYPES:
                res.beam_end[i] = np.zeros(12)
            elif e.typ in asm.SHELL_TYPES:
                res.shell_res[i] = np.zeros(6)
            elif e.typ == "feder":
                res.feder_res[i] = np.zeros(6)
            elif e.typ in asm.GRENZSCHICHT_TYPES:
                res.grenzschicht_res[i] = np.zeros(3)
            else:
                res.solid_res[i] = np.zeros(6)
    for i, kind, val in items:
        if kind == "beam":
            res.beam_end[i] = val
            if i in q:
                res.beam_q[i] = np.asarray(q[i], float)
        elif kind == "bimoment":
            res.bimomente[i] = val
        elif kind == "shell":
            res.shell_res[i] = val
        elif kind == "feder":
            res.feder_res[i] = val
        elif kind == "grenzschicht":
            res.grenzschicht_res[i] = val
        else:
            res.solid_res[i] = val
    res._cache.clear()


# ==========================================================================
# Lineare Statik
# ==========================================================================
def _solve_loads(model: Model, system: StaticSystem, factors: dict, name: str,
                 kind: str, workers=None, progress=None) -> Results:
    t0 = time.time()
    aktiv = getattr(system, "aktiv", None)
    F, feq, q, temp = case_loads(model, factors, aktiv)
    us = case_prescribed(model, factors, warn=progress)
    ueber = case_uebermass(model, factors)
    res = Results(name=name, kind=kind, model=model)
    if getattr(system, "situation", ""):
        res.info["situation"] = system.situation
    def _rechnen():
        """Der Loesungsweg des Lastfalls - einmal wiederholbar."""
        if model.hat_ausfallstaebe():
            u_, R_, aktiv_, ausfall, alog, kontakt = solve_with_ausfall(
                model, system, F, us=us, progress=progress, uebermass=ueber)
            res.info["ausfall"] = ausfall
            res.info["ausfall_log"] = alog
            if kontakt is not None:
                res.contact, res.contact_forces, cinfo = kontakt
                res.info.update(cinfo)
            return u_, R_, aktiv_
        if model.has_contact:
            u_, R_, res.contact, res.contact_forces, cinfo = solve_with_contact(
                model, system, F, progress=progress, us=us, uebermass=ueber)
            res.info.update(cinfo)
            return u_, R_, aktiv
        u_ = system.solve(F, us=us)
        return u_, system.reactions(u_, F), aktiv

    try:
        u, R, aktiv_eff = _rechnen()
        system.freie_bewegungen()      # nur suchen - geloest ist geloest
    except RuntimeError:
        # Statt abzubrechen: die freien Bewegungen benennen, festhalten und
        # weiterrechnen. Der Nutzer sieht dann die Verformung und daneben,
        # welche Last in der Bewegung ins Nichts geht - und entscheidet selbst.
        if not system.hilfsfesselung():
            raise
        n_sg = len(system.singular)
        _melde(progress, f"{n_sg} freie Bewegung{'' if n_sg == 1 else 'en'} gefunden - "
               "wird mit Hilfsfesselung gerechnet")
        u, R, aktiv_eff = _rechnen()
        u = system.ohne_starrkoerper(u)
    if system.singular:
        from . import singular as _sg
        # Nach Schwere geordnet: oben steht, was die Rechnung zunichte macht,
        # nicht das erstbeste Teil nach Knotennummer.
        res.singular = _sg.wichtigste(_sg.auswerten(model, system.singular, F),
                                      hoechstens=len(system.singular))
        for x in res.singular:
            x.kegel = None            # ausgewertet - die Kegelmatrix kann weg
        res.info["singularitaeten"] = [singularitaet_info(x)
                                       for x in _sg.wichtigste(res.singular)]
    verschiebungen_eintragen(model, res, u, R)
    res.info.update({"ndof": model.ndof, "nfree": len(system.fi),
                     "solver": system.backend, "factors": dict(factors)})
    postprocess(model, u, res, feq, q, temp, workers, aktiv_eff)
    res.info["time"] = time.time() - t0 + system.t_assemble
    return res


def singularitaet_info(s) -> dict:
    """Eine freie Bewegung als einfaches Woerterbuch - fuer Bericht und Web.

    ``Results.singular`` haelt die Objekte fuer die Oberflaeche (sie braucht
    Richtung und Knoten, um den Pfeil zu zeichnen); hier steht dasselbe in
    Text und Zahlen, damit es auch durch ``to_dict`` und ueber die Farm kommt.
    """
    return {"art": s.art, "koerper": list(s.koerper), "text": s.text,
            "ursache": s.ursache, "befund": s.befund(), "kraft": float(s.kraft),
            "moment": float(s.moment), "gefesselt": bool(s.gefesselt),
            "knoten": len(s.knoten)}


def verschiebungen_eintragen(model: Model, res: Results, u: np.ndarray, R: np.ndarray) -> None:
    """u und R (ndof,) in die Ergebnisfelder (nn, 6) schreiben; die Woelb-FHG
    hinter den Knotenfreiheitsgraden landen in res.woelb."""
    n6 = model.nn * NDOF
    res.u = np.asarray(u[:n6], float).reshape(-1, NDOF)
    res.reactions = np.asarray(R[:n6], float).reshape(-1, NDOF)
    if len(u) > n6:
        res.woelb = {int(n): float(u[k]) for n, k in model.woelb_index().items()}


def _normalkraft(model: Model, e, u: np.ndarray) -> float:
    """Normalkraft (Zug positiv) eines Zug-/Druckstabs, Seils oder der
    Laengskraft einer Feder aus dem Verschiebungsvektor."""
    d = asm.element_dofs(e, model)[:12]
    X = model.nodes[e.nodes]
    if e.typ == "feder":
        from .elements import verbindung as vb
        fp = model.federn[e.sec]
        T3 = vb.feder_achsen(X[0], X[1], fp.achse, e.roll)
        return float(vb.feder_kraefte(fp.k, T3, u[d])[0])
    kl, T3, T, L = asm.beam_local(model, e)
    ul = T @ u[d]
    mat = model.materials[e.mat]
    sec = model.sections[e.sec]
    return float(mat.E * sec.A / L * (ul[6] - ul[0]))


def solve_with_ausfall(model: Model, system: StaticSystem, F: np.ndarray, us=None,
                       progress=None, max_iter: int = 50, uebermass: dict = None):
    """Aktivmengen-Iteration fuer Staebe, die nur Zug oder nur Druck aufnehmen
    (Fachwerkstab/Feder mit ``nur``, Seile).

    Gerechnet wird mit allen Staeben; wer die falsche Kraft traegt, wird
    herausgenommen (seine Steifigkeit wird als K_extra wieder abgezogen -
    das System muss nicht neu aufgestellt werden), und es wird neu geloest,
    bis sich die Menge nicht mehr aendert. Herausgenommene Staebe duerfen
    wieder hinein, wenn sie im naechsten Schritt die richtige Kraft
    truegen. Kontakt laeuft innen weiter mit.

    Rueckgabe (u, R, aktiv, ausgefallen, log, kontakt) - kontakt = None oder
    (contact, contact_forces, info) aus der Kontaktiteration.
    """
    ne = len(model.elements)
    kand = [i for i, e in enumerate(model.elements)
            if (getattr(e, "nur", "") or e.typ == "seil")
            and (system.aktiv is None or system.aktiv[i])]
    Ke = {}
    for i in kand:
        e = model.elements[i]
        Ke[i] = (asm.element_dofs(e, model), np.asarray(asm.element_matrix(model, e), float))
    aus: set = set()
    log: list[str] = []
    n = model.ndof
    u = R = None
    kontakt = None
    for it in range(1, max_iter + 1):
        K_aus = None
        if aus:
            rows, cols, vals = [], [], []
            for i in aus:
                d, K_e = Ke[i]
                r, c = np.meshgrid(d, d, indexing="ij")
                rows.append(r.ravel())
                cols.append(c.ravel())
                vals.append(-K_e.ravel())
            K_aus = sparse.coo_matrix(
                (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                shape=(n, n)).tocsr()
        if model.has_contact:
            u, R, cons, cf, cinfo = solve_with_contact(model, system, F, progress=progress,
                                                       uebermass=uebermass,
                                                       us=us, K_zusatz=K_aus)
            kontakt = (cons, cf, cinfo)
        else:
            u = system.solve(F, K_extra=K_aus, us=us)
            R = system.reactions(u, F, K_aus)
        kraefte = {i: _normalkraft(model, model.elements[i], u) for i in kand}
        gross = max([abs(v) for v in kraefte.values()] + [1.0])
        tol = 1e-9 * gross
        neu = set()
        for i, N in kraefte.items():
            art = getattr(model.elements[i], "nur", "") or "zug"
            if (art == "zug" and N < -tol) or (art == "druck" and N > tol):
                neu.add(i)
        if progress:
            progress(f"Ausfall-Iteration {it}: {len(neu)} von {len(kand)} Stäben ausgefallen")
        if neu == aus:
            break
        aus = neu
    else:
        log.append(f"Ausfall-Iteration nach {max_iter} Schritten nicht konvergiert")
    if aus:
        log.append(f"{len(aus)} Stäbe tragen nicht (nur Zug/Druck): "
                   + ", ".join(str(i) for i in sorted(aus)[:12])
                   + (" …" if len(aus) > 12 else ""))
    aktiv = np.ones(ne, dtype=bool) if system.aktiv is None else np.asarray(system.aktiv, bool).copy()
    for i in aus:
        aktiv[i] = False
    return u, R, aktiv, sorted(int(i) for i in aus), log, kontakt


# ==========================================================================
# Situationen: je Situation ein eigenes System
# ==========================================================================
def situationssystem(model: Model, name: str = "", workers: int = None,
                     progress=None) -> tuple:
    """(Modell, StaticSystem) der Situation: Stellung angewandt, abgeschaltete
    Elemente weggelassen. Fuer die Grundstellung ist das Modell das Original."""
    from .situationen import situationsmodell
    m_s, aktiv, log = situationsmodell(model, name)
    if progress:
        for z in log:
            progress(z.strip())
    system = StaticSystem(m_s, workers, progress, aktiv=aktiv, situation=name or GRUNDSTELLUNG)
    return m_s, system


def systeme_je_situation(model: Model, namen=None, workers: int = None, progress=None,
                         systeme: dict = None) -> dict:
    """{Situation: (Modell, System)} fuer die Situationen der genannten
    Lastfaelle (alle, wenn keine genannt). ``systeme`` wird ergaenzt."""
    systeme = systeme if systeme is not None else {}
    for sit in model.lastfaelle_je_situation(namen):
        if sit not in systeme:
            systeme[sit] = situationssystem(model, sit, workers, progress)
    return systeme


def solve_static(model: Model, progress=None, case: str = None,
                 workers: int = None, system: StaticSystem = None) -> Results:
    """Ein Lastfall (default: aktiver Lastfall; case='all': alle Lastfaelle mit
    Faktor 1 ueberlagert)."""
    system = system or StaticSystem(model, workers, progress)
    if case == "all":
        factors = {k: 1.0 for k in model.load_cases}
        name = "alle Lastfaelle"
    else:
        lc = model.case(case)
        factors = {lc.name: 1.0}
        name = lc.name
    res = _solve_loads(model, system, factors, name, "case", workers, progress)
    _melde(progress, "System gelöst", 1.0)
    return res


def solve_cases(model: Model, cases: list = None, workers: int = None,
                progress=None, system: StaticSystem = None, systeme: dict = None) -> dict:
    """Alle (oder ausgewaehlte) Lastfaelle loesen - je Situation mit ihrem
    System (eine Faktorisierung je Situation). Ein uebergebenes ``system``
    gilt fuer alle genannten Lastfaelle."""
    names = cases if cases is not None else list(model.load_cases)
    out = {}
    if system is not None:
        for k, name in enumerate(names):
            out[name] = _solve_loads(model, system, {name: 1.0}, name, "case", workers)
            _melde(progress, f"Lastfall {name} ({k + 1}/{len(names)})",
                   0.35 + 0.25 * (k + 1) / max(1, len(names)))
        return out
    systeme = systeme_je_situation(model, names, workers, progress, systeme)
    k = 0
    for sit, sit_names in model.lastfaelle_je_situation(names).items():
        m_s, sys_s = systeme[sit]
        for name in sit_names:
            out[name] = _solve_loads(m_s, sys_s, {name: 1.0}, name, "case", workers)
            k += 1
            _melde(progress, f"Lastfall {name} ({k}/{len(names)})"
                   + (f" – Situation {sit}" if sit != GRUNDSTELLUNG else ""),
                   0.35 + 0.25 * k / max(1, len(names)))
    return out


def _kombination_pruefen(model: Model, combo: Combination) -> str:
    """Die Situation der Kombination; ihre Lastfaelle muessen dazu gehoeren."""
    sit = combo.situation or GRUNDSTELLUNG
    fremd = [k for k in combo.lastfaelle() if k in model.load_cases
             and (model.load_cases[k].situation or GRUNDSTELLUNG) != sit]
    if fremd:
        raise ValueError(f"Kombination '{combo.name}' (Situation {sit}) enthält Lastfall "
                         f"{', '.join(fremd)} aus einer anderen Situation")
    return sit


def solve_combination(model: Model, combo: Combination, case_results: dict = None,
                      system: StaticSystem = None, workers: int = None,
                      progress=None, systeme: dict = None) -> Results:
    """Eine Kombination: Superposition (linear) oder direkte Loesung (Kontakt) -
    in der Situation der Kombination."""
    sit = _kombination_pruefen(model, combo)
    if not model.has_contact and case_results is not None \
            and all(k in case_results for k, f in combo.factors.items() if f):
        teile = [(case_results[k], f) for k, f in combo.factors.items() if f]
        basis = next((r.model for r, _f in teile if getattr(r, "model", None) is not None), model)
        res = Results.combine(basis, teile, combo.name)
        res.info["typ"] = combo.typ
        if sit != GRUNDSTELLUNG:
            res.info["situation"] = sit
        if teile and "inaktiv" in teile[0][0].info:
            res.info["inaktiv"] = list(teile[0][0].info["inaktiv"])
        return res
    if system is None:
        if systeme is not None and sit in systeme:
            model, system = systeme[sit]
        elif sit != GRUNDSTELLUNG or model.situation(sit).deaktiviert:
            model, system = situationssystem(model, sit, workers, progress)
        else:
            system = StaticSystem(model, workers, progress)
    res = _solve_loads(model, system, combo.factors, combo.name, "combination", workers,
                       progress)
    res.info["typ"] = combo.typ
    return res


def umhuellende_der_kombination(model: Model, combo: Combination, case_results: dict,
                                systeme: dict = None, workers: int = None,
                                progress=None) -> tuple:
    """Die Umhuellende einer Kombination mit Alternativen - Rueckgabe
    (Envelope, Zahl der zusaetzlich geloesten Alternativen).

    Eine Alternative aus genau einem Lastfall mit Faktor 1 **ist** dessen
    Lastfallergebnis: es wird wiederverwendet, nichts neu geloest. Am
    Drehlager sind das alle 720 Eintraege der 52 Ergebniskombinationen. Jede
    andere Alternative wird als voruebergehende Kombination gerechnet
    (Ueberlagerung; im Kontaktmodell direkte Loesung) und nach dem Einfalten
    verworfen - der Speicher haengt nicht von der Zahl der Alternativen ab.
    """
    from dataclasses import replace
    sit = _kombination_pruefen(model, combo)
    env = Envelope(model, {}, combo.name)
    geloest = 0
    for k, alt in enumerate(combo.alternativen, 1):
        teile = {a: f for a, f in alt.items() if f}
        if not teile:
            continue
        lc = next(iter(teile))
        if len(teile) == 1 and abs(teile[lc] - 1.0) < 1e-12 and case_results \
                and lc in case_results:
            env.aufnehmen(lc, case_results[lc])
        else:
            name = f"{combo.name} [{k}]"
            zwischen = replace(combo, name=name, factors=teile, alternativen=[])
            res = solve_combination(model, zwischen, case_results, workers=workers,
                                    systeme=systeme)
            env.aufnehmen(name, res)
            geloest += 1
        _melde(progress, f"Umhüllende {combo.name}: {k}/{len(combo.alternativen)}"
               + (f" – Situation {sit}" if sit != GRUNDSTELLUNG else ""),
               0.60 + 0.30 * k / max(1, len(combo.alternativen)))
    return env, geloest


def solve_combinations(model: Model, combos: list = None, case_results: dict = None,
                       system: StaticSystem = None, workers: int = None,
                       progress=None, use_jobs: bool = None, systeme: dict = None) -> dict:
    """Alle Kombinationen. Bei Kontakt (nichtlinear) werden die Kombinationen
    als Auftraege parallel bzw. auf der Farm gerechnet."""
    names = combos if combos is not None else list(model.combinations)
    # Kombinationen mit Alternativen sind Umhuellende - die bildet solve_all
    # (umhuellende_der_kombination), nicht ein einzelnes Ergebnis.
    names = [n for n in names if not model.combinations[n].ist_umhuellende]
    out = {}
    if not names:
        return out
    if not model.has_contact:
        if case_results is None:
            case_results = solve_cases(model, workers=workers, progress=progress,
                                       system=system, systeme=systeme)
        for n in names:
            out[n] = solve_combination(model, model.combinations[n], case_results,
                                       systeme=systeme)
        return out
    # nichtlinear: Auftraege
    st = parallel.settings()
    if use_jobs is None:
        use_jobs = (st.backend == "farm") or (st.workers > 1 and len(names) > 1)
    if use_jobs:
        from .parallel import Job, run_jobs
        jobs = [Job("solve_combination", {"model": model.to_dict(), "combination": n},
                    label=n) for n in names]
        results = run_jobs(jobs, workers=workers,
                           progress=(lambda a, b: progress(f"Kombination {a}/{b}"))
                           if progress else None)
        for n, r in zip(names, results):
            if not r.ok:
                raise RuntimeError(f"Kombination {n}: {r.error}")
            res = r.result
            res.model = model
            out[n] = res
        return out
    for k, n in enumerate(names):
        out[n] = solve_combination(model, model.combinations[n], None, system, workers,
                                   systeme=systeme)
        if progress:
            _melde(progress, f"Kombination {n} ({k + 1}/{len(names)})",
                   0.60 + 0.30 * (k + 1) / max(1, len(names)))
    return out


# ==========================================================================
# Kontakt-Iteration
# ==========================================================================
def _contact_singular(it: int, ex, cs, model=None) -> str:
    """Meldung zu einem singulaeren Schritt der Kontakt-Iteration.

    Der Hinweis richtet sich nach der Zahl der **offenen** Bedingungen. Sind
    null offen, ist jede Fuge geschlossen - dann kann nichts abheben, und die
    Bewegung liegt in der Fugenebene. Frueher stand hier in beiden Faellen
    derselbe Satz „vermutlich hebt ein Bauteil ab", auch bei null offenen
    Bedingungen; das widerspricht sich selbst.
    """
    n_zu = sum(1 for c in cs.cons if c.active)
    n_open = len(cs.cons) - n_zu
    if n_open:
        hinweis = (f"{n_open} von {len(cs.cons)} Kontaktbedingungen sind offen - "
                   "ein Bauteil hebt ab oder rutscht ohne Halt.")
    elif cs.cons:
        hinweis = (f"alle {len(cs.cons)} Kontaktbedingungen sind geschlossen - "
                   "abheben kann hier nichts. Die Bewegung liegt damit **in** "
                   "der Fugenebene: das Bauteil gleitet, oder die Fuge haelt "
                   "quer zu sich nichts.")
    else:
        hinweis = "es gibt keine Kontaktbedingungen - die Ursache liegt nicht am Kontakt."
    text = f"Kontakt-Iteration {it}: {ex}\nHinweis: {hinweis}"
    if model is not None and "Teiltragwerk" not in str(ex) and "ohne Netz" not in str(ex):
        from .diagnose import meldungen
        befund = [z for z in meldungen(model) if not z.startswith("Hinweis")]
        if befund:
            text += "\n" + "\n".join(befund)
    return text


def solve_with_contact(model: Model, system: StaticSystem, F: np.ndarray,
                       max_iter: int = 120, progress=None, us: np.ndarray = None,
                       K_zusatz: sparse.spmatrix = None, uebermass: dict = None):
    """Kontakt-Iteration; ``K_zusatz`` (z. B. die abgezogene Steifigkeit
    ausgefallener Zugstaebe) kommt in jedem Schritt zur Kontaktsteifigkeit.

    ``uebermass`` ist das Uebermass des Lastfalls je Fuge (siehe
    :func:`case_uebermass`): ein negativer Anfangsspalt, aus dem die
    Kontaktrechnung die Pressspannung und ueber den Reibbeiwert die
    Schubtragfaehigkeit macht.
    """
    from .contact import ContactSystem
    log: list[str] = []
    cs = ContactSystem(model, system.K, log, uebermass)
    cs.set_force_scale(float(np.abs(F).max()) if F.size else 1.0)
    cs.initialize()
    converged = False
    it = 0
    Kc = Fc = None

    def matrizen():
        Kc_, Fc_ = cs.matrices(model.ndof)
        if K_zusatz is not None:
            Kc_ = (Kc_ + K_zusatz) if Kc_ is not None else K_zusatz
        return Kc_, Fc_

    if not cs.cons:
        u = system.solve(F, K_extra=K_zusatz, us=us)
        R = system.reactions(u, F, K_zusatz)
        return u, R, [], np.zeros((model.nn, 3)), {"contact_iterations": 0,
                                                   "contact_converged": True,
                                                   "contact_log": log}
    u = None
    forced = False
    for it in range(1, max_iter + 1):
        Kc, Fc = matrizen()
        try:
            u = system.solve(F, Kc, Fc, us=us)
        except RuntimeError as ex:
            if it == 1 and not forced and cs.stabilise():
                # Im ersten Schritt haelt keine Bedingung - etwa eine Schraube,
                # die erst nach dem Durchfahren des Lochspiels traegt. Ein
                # Hilfsschritt mit allen Bedingungen als reine Federn zeigt,
                # wohin sich das Bauteil bewegen will; danach bleiben nur die
                # Bedingungen geschlossen, auf die es sich zubewegt.
                forced = True
                log.append("Hilfsschritt: Bewegungsrichtung bestimmt, weil im ersten "
                           "Schritt keine Kontaktbedingung haelt")
                Kc, Fc = matrizen()
                try:
                    u = system.solve(F, Kc, Fc, us=us)
                except RuntimeError as ex2:
                    raise RuntimeError(_contact_singular(it, ex2, cs, model)) from None
                cs.select_by_direction(u)
                Kc, Fc = matrizen()
                try:
                    u = system.solve(F, Kc, Fc, us=us)
                except RuntimeError as ex3:
                    raise RuntimeError(_contact_singular(it, ex3, cs, model)) from None
            else:
                raise RuntimeError(_contact_singular(it, ex, cs, model)) from None
        changed = cs.update(u)
        if progress:
            progress(f"Kontakt-Iteration {it}: {cs.n_active} aktiv")
        if not changed:
            converged = True
            break
    R = system.reactions(u, F + (Fc if Fc is not None else 0.0), Kc)
    # Einseitige Lager als Auflagerreaktionen ausweisen
    Rsup = cs.support_reactions(model.nn)
    n6 = model.nn * NDOF
    Rk = R[:n6].reshape(-1, NDOF)
    Rk[:, :3] += Rsup
    R[:n6] = Rk.ravel()
    if not converged:
        log.append(f"Kontakt-Iteration nach {max_iter} Schritten nicht konvergiert")
    log.extend(cs.warnings())
    return u, R, cs.results(), cs.nodal_forces(model.nn), {
        "contact_iterations": it, "contact_converged": converged, "contact_log": log}


# ==========================================================================
# Umhuellende
# ==========================================================================
class Envelope:
    """Extremwerte ueber mehrere Ergebnisse (Kombinationen) mit Herkunft.

    Gebildet wird **inkrementell**: :meth:`aufnehmen` faltet ein Ergebnis in
    das laufende Minimum und Maximum ein, :meth:`aufnehmen_umhuellende` eine
    ganze Umhuellende. Der Speicherbedarf haengt damit nicht von der Zahl der
    Ergebnisse ab - das Stapeln aller Ergebnisse (``np.stack``) hielte sie
    gleichzeitig im Speicher; eine RFEM-Ergebniskombination am Drehlager hat
    128 Alternativen, die Ermuedungskombinationen zusammen ueber 3500.

    Die Herkunft (``*_src``) ist der Index in ``names``. Bei Gleichstand
    gewinnt das **erste** Ergebnis - so wie ``argmin``/``argmax`` beim
    Stapeln; darum ist das laufende Verfahren bitgleich mit dem gestapelten
    (test_umhuellende). Ein Ergebnis, dem ein Stabelement fehlt, zaehlt dort
    mit Null - auch das wie beim Stapeln.

    ``Envelope(model, results, name)`` bleibt der Aufruf fuer alle, die schon
    ein Woerterbuch von Ergebnissen haben.
    """

    KOMPONENTEN = ("N", "Vy", "Vz", "Mt", "My", "Mz")

    def __init__(self, model: Model, results: dict = None, name: str = "Umhuellende",
                 n_stations: int = None):
        self.model = model
        self.name = name
        self.names: list = []
        self.n_stations = n_stations or model.design.stations
        nn = model.nn
        self.u_min = np.zeros((nn, NDOF))
        self.u_max = np.zeros((nn, NDOF))
        self.u_min_src = np.zeros((nn, NDOF), int)
        self.u_max_src = np.zeros((nn, NDOF), int)
        self.r_min = np.zeros((nn, NDOF))
        self.r_max = np.zeros((nn, NDOF))
        self.r_min_src = np.zeros((nn, NDOF), int)
        self.r_max_src = np.zeros((nn, NDOF), int)
        self.beam: dict = {}
        self.node_vm_max = np.zeros(nn)
        self.node_vm_src = np.zeros(nn, int)
        self.util: dict = {}
        for k, r in (results or {}).items():
            self.aufnehmen(k, r)

    # ---- Einfalten ------------------------------------------------------
    @staticmethod
    def _falten(mn, mx, imn, imx, wert, j):
        """Laufendes Min/Max eines Feldes mit Herkunft; Gleichstand bleibt beim
        aelteren Ergebnis (strenges < und >)."""
        kl = wert < mn
        gr = wert > mx
        return (np.where(kl, wert, mn), np.where(gr, wert, mx),
                np.where(kl, j, imn), np.where(gr, j, imx))

    def _stab_neu(self, x, j: int) -> dict:
        """Ein Stabelement, das erst im Ergebnis j auftaucht: die Ergebnisse
        davor zaehlen mit Null (Herkunft 0, das erste), wie beim Stapeln."""
        n = self.n_stations
        d: dict = {"x": x}
        null = np.zeros(n)
        for k in self.KOMPONENTEN:
            if j == 0:
                d[k] = None                      # wird gleich mit dem ersten Wert belegt
            else:
                d[k] = (null.copy(), null.copy(), np.zeros(n, int), np.zeros(n, int))
        return d

    def aufnehmen(self, name: str, r) -> None:
        """Ein Ergebnis einfalten: Verschiebungen, Auflagerkraefte,
        Stabschnittgroessen je Station, Vergleichsspannung, Ausnutzung."""
        j = len(self.names)
        self.names.append(name)
        n = self.n_stations
        u = np.asarray(r.u, float)
        R = np.asarray(r.reactions, float)
        vm = np.nan_to_num(np.asarray(r.node_vm, float))
        if j == 0:
            self.u_min, self.u_max = u.copy(), u.copy()
            self.r_min, self.r_max = R.copy(), R.copy()
            self.node_vm_max = vm.copy()
        else:
            self.u_min, self.u_max, self.u_min_src, self.u_max_src = self._falten(
                self.u_min, self.u_max, self.u_min_src, self.u_max_src, u, j)
            self.r_min, self.r_max, self.r_min_src, self.r_max_src = self._falten(
                self.r_min, self.r_max, self.r_min_src, self.r_max_src, R, j)
            gr = vm > self.node_vm_max
            self.node_vm_max = np.where(gr, vm, self.node_vm_max)
            self.node_vm_src = np.where(gr, j, self.node_vm_src)
        # Staebe: alle Elemente, die dieses oder ein frueheres Ergebnis kennt
        st = r.stations(n) if r.beam_end else {}
        null = np.zeros(n)
        for i in sorted(set(st) | set(self.beam)):
            p = st.get(i)
            d = self.beam.get(i)
            if d is None:
                d = self._stab_neu(p["x"] if p is not None else None, j)
                self.beam[i] = d
            if d["x"] is None and p is not None:
                d["x"] = p["x"]
            for k in self.KOMPONENTEN:
                wert = np.asarray(p[k], float) if p is not None else null
                if d[k] is None:
                    d[k] = (wert.copy(), wert.copy(), np.zeros(n, int), np.zeros(n, int))
                else:
                    d[k] = self._falten(*d[k], wert, j)
        # Ausnutzung (elastisch) je Stab: das Maximum ueber alle Ergebnisse
        bf = r.beam_forces if r.beam_end else {}
        for i in set(bf) | set(self.util):
            v = bf[i]["util"] if i in bf else None
            vorher = self.util.get(i)
            werte = [x for x in (vorher, v) if x is not None]
            self.util[i] = max(werte) if werte else None

    def aufnehmen_umhuellende(self, env: "Envelope") -> None:
        """Eine Umhuellende einfalten - die Herkunft zeigt danach auf deren
        Ergebnisse (ihre Namen werden angehaengt), nicht auf die Umhuellende."""
        if not env.names:
            return
        versatz = len(self.names)
        self.names.extend(env.names)
        n = self.n_stations
        if versatz == 0:
            self.u_min, self.u_max = env.u_min.copy(), env.u_max.copy()
            self.u_min_src, self.u_max_src = env.u_min_src.copy(), env.u_max_src.copy()
            self.r_min, self.r_max = env.r_min.copy(), env.r_max.copy()
            self.r_min_src, self.r_max_src = env.r_min_src.copy(), env.r_max_src.copy()
            self.node_vm_max, self.node_vm_src = env.node_vm_max.copy(), env.node_vm_src.copy()
            self.beam = {i: {k: (tuple(np.array(x) for x in v) if k != "x" else v)
                             for k, v in d.items()} for i, d in env.beam.items()}
            self.util = dict(env.util)
            return
        self.u_min, self.u_max, self.u_min_src, self.u_max_src = self._falten_umhuellende(
            (self.u_min, self.u_max, self.u_min_src, self.u_max_src),
            (env.u_min, env.u_max, env.u_min_src, env.u_max_src), versatz)
        self.r_min, self.r_max, self.r_min_src, self.r_max_src = self._falten_umhuellende(
            (self.r_min, self.r_max, self.r_min_src, self.r_max_src),
            (env.r_min, env.r_max, env.r_min_src, env.r_max_src), versatz)
        gr = env.node_vm_max > self.node_vm_max
        self.node_vm_max = np.where(gr, env.node_vm_max, self.node_vm_max)
        self.node_vm_src = np.where(gr, env.node_vm_src + versatz, self.node_vm_src)
        null = np.zeros(n)
        for i in sorted(set(env.beam) | set(self.beam)):
            d = self.beam.get(i)
            e = env.beam.get(i)
            if d is None:
                # Element nur in der eingefalteten Umhuellende: die eigenen
                # Ergebnisse davor zaehlen mit Null, Herkunft 0
                d = {"x": None}
                for k in self.KOMPONENTEN:
                    d[k] = (null.copy(), null.copy(), np.zeros(n, int), np.zeros(n, int))
                self.beam[i] = d
            if e is None:
                # Element nur hier: die Ergebnisse der Umhuellende zaehlen mit
                # Null, Herkunft = ihr erstes Ergebnis
                e = {"x": None}
                for k in self.KOMPONENTEN:
                    e[k] = (null, null, np.full(n, 0, int), np.full(n, 0, int))
            if d["x"] is None and e.get("x") is not None:
                d["x"] = e["x"]
            for k in self.KOMPONENTEN:
                d[k] = self._falten_umhuellende(d[k], e[k], versatz)
        for i in set(env.util) | set(self.util):
            werte = [x for x in (self.util.get(i), env.util.get(i)) if x is not None]
            self.util[i] = max(werte) if werte else None

    @staticmethod
    def _falten_umhuellende(eigen, fremd, versatz: int):
        mn, mx, imn, imx = eigen
        fmn, fmx, fimn, fimx = fremd
        kl = fmn < mn
        gr = fmx > mx
        return (np.where(kl, fmn, mn), np.where(gr, fmx, mx),
                np.where(kl, np.asarray(fimn) + versatz, imn),
                np.where(gr, np.asarray(fimx) + versatz, imx))

    # ---- Auswertung ------------------------------------------------------
    @property
    def umag_max(self) -> np.ndarray:
        return np.maximum(np.linalg.norm(self.u_max[:, :3], axis=1),
                          np.linalg.norm(self.u_min[:, :3], axis=1))

    def extreme_table(self) -> list[list]:
        """Zeilen: Element, Groesse, min, Kombination, max, Kombination."""
        rows = []
        for i, d in self.beam.items():
            for k in self.KOMPONENTEN:
                mn, mx, imn, imx = d[k]
                j1, j2 = int(np.argmin(mn)), int(np.argmax(mx))
                rows.append([i, k, float(mn[j1]), self.names[imn[j1]],
                             float(mx[j2]), self.names[imx[j2]]])
        return rows

    def summary(self) -> str:
        s = [f"{self.name}: {len(self.names)} Ergebnisse"]
        if self.u_max.size and self.names:
            um = self.umag_max
            i = int(np.argmax(um))
            s.append(f"max. Verschiebung       : {um[i]*1000:.3f} mm (Knoten {i})")
        if self.beam:
            for k in ("N", "My", "Mz"):
                mn = min(float(d[k][0].min()) for d in self.beam.values())
                mx = max(float(d[k][1].max()) for d in self.beam.values())
                unit = "kN" if k == "N" else "kNm"
                s.append(f"{k:2s} min/max              : {mn/1e3:.2f} / {mx/1e3:.2f} {unit}")
        if np.any(self.node_vm_max):
            s.append(f"max. Vergleichsspannung : {np.nanmax(self.node_vm_max)/1e6:.2f} MPa")
        return "\n".join(s)


# ==========================================================================
# Gesamtanalyse
# ==========================================================================
@dataclass
class Analysis:
    model: Model
    cases: dict = field(default_factory=dict)
    combinations: dict = field(default_factory=dict)
    envelopes: dict = field(default_factory=dict)
    design: object = None
    fatigue: object = None
    joints: object = None
    gzg: object = None
    beulen: object = None
    lasteinleitung: object = None
    volumen: object = None
    theorie2: object = None
    info: dict = field(default_factory=dict)
    #: je Situation das System und das Modell, mit dem gerechnet wurde
    #: (Grundstellung: das Modell selbst; Stellung: gedrehte Kopie)
    systeme: dict = field(default_factory=dict)
    modelle: dict = field(default_factory=dict)
    theorie3: object = None
    schwingung: object = None

    def all_results(self) -> dict:
        d = dict(self.cases)
        d.update(self.combinations)
        return d

    def envelope(self, typ: str = "ULS") -> Optional[Envelope]:
        return self.envelopes.get(typ)

    def summary(self) -> str:
        s = [f"Lastfaelle: {len(self.cases)}   Kombinationen: {len(self.combinations)}   "
             f"Rechenzeit: {self.info.get('time', 0):.2f} s ({self.info.get('parallel', '')})"]
        for k, env in self.envelopes.items():
            s.append(env.summary())
        if self.theorie2 is not None and getattr(self.theorie2, "kombinationen", None):
            s.append(self.theorie2.summary())
        if self.theorie3 is not None and getattr(self.theorie3, "kombinationen", None):
            s.append(self.theorie3.summary())
        if self.design is not None:
            s.append(self.design.summary())
        if self.fatigue is not None:
            s.append(self.fatigue.summary())
        if self.joints is not None:
            s.append(self.joints.summary())
        if self.gzg is not None:
            s.append(self.gzg.summary())
        if self.beulen is not None:
            s.append(self.beulen.summary())
        if self.lasteinleitung is not None:
            s.append(self.lasteinleitung.summary())
        if self.volumen is not None:
            s.append(self.volumen.summary())
        if self.theorie2 is not None and self.theorie2.kombinationen:
            s.append(self.theorie2.summary())
        return "\n".join(s)


def _lastfaelle_hoeherer_ordnung(model: Model, an, systeme: dict, progress=None):
    """Lastfaelle mit theorie II oder III: das lineare Ergebnis ersetzen."""
    from .theorie2 import solve_theorie2, Th2Results
    from .theorie3 import solve_theorie3, Th3Results
    ds = model.design
    for name, lc in model.load_cases.items():
        th = model.theorie_von(lc)
        if th not in ("II", "III") or name not in an.cases:
            continue
        m_s, sys_s = systeme[lc.situation or GRUNDSTELLUNG]
        try:
            if th == "II":
                res, info = solve_theorie2(m_s, {name: 1.0}, name, sys_s,
                                           imperfektionen=bool(getattr(ds, "imperfektionen", True)),
                                           elastisch=not getattr(ds, "th2_plastisch", False),
                                           richtung=getattr(ds, "th2_richtung", None),
                                           alle_vorkruemmungen=bool(getattr(ds, "th2_alle_vorkruemmungen", False)),
                                           progress=progress)
                if an.theorie2 is None:
                    an.theorie2 = Th2Results(settings={"modus": "je Lastfall/Kombination"})
                an.theorie2.kombinationen[name] = info
            else:
                res, info = solve_theorie3(m_s, {name: 1.0}, name,
                                           schritte=int(getattr(ds, "th3_schritte", 10) or 10),
                                           aktiv=getattr(sys_s, "aktiv", None), progress=progress)
                if an.theorie3 is None:
                    an.theorie3 = Th3Results(settings={"schritte": int(getattr(ds, "th3_schritte", 10) or 10)})
                an.theorie3.kombinationen[name] = info
        except ValueError as ex:
            an.info.setdefault("warnungen", []).append(f"Lastfall {name}: {ex}")
            continue
        if not info.fehler:
            res.kind = "case"
            if lc.situation:
                res.info["situation"] = lc.situation
            an.cases[name] = res


def solve_all(model: Model, workers: int = None, progress=None, combinations: bool = True,
              envelopes: bool = True, design: bool = False, fatigue: bool = False) -> Analysis:
    """Alle Lastfaelle, alle Kombinationen, Umhuellende, optional Nachweise."""
    t0 = time.time()
    an = Analysis(model)
    if model.joints:
        # Das Momenten-Rotations-Verhalten der Anschluesse gehoert in die
        # Rechnung, nicht erst in den Nachweis: nachgiebige Anschluesse sitzen
        # als Drehfeder am Stabende (EN 1993-1-8, 5.1.2).
        from .joints.anschluss import federn_setzen
        an.info["anschlussfedern"] = federn_setzen(model)
    # Je Situation ein System: die Grundstellung (unbewegt, alles aktiv) und
    # jede Situation, in der ein Lastfall steht
    systeme: dict = {}
    an.cases = solve_cases(model, workers=workers, progress=progress, systeme=systeme)
    if GRUNDSTELLUNG not in systeme:
        systeme[GRUNDSTELLUNG] = (model, StaticSystem(model, workers, progress))
    an.systeme = {k: v[1] for k, v in systeme.items()}
    an.modelle = {k: v[0] for k, v in systeme.items()}
    system = an.systeme[GRUNDSTELLUNG]
    if combinations and model.combinations:
        an.combinations = solve_combinations(model, case_results=an.cases, system=None,
                                             workers=workers, progress=progress,
                                             systeme=systeme)
        # Kombinationen mit Alternativen: je eine Umhuellende, keine Ergebnisse
        # in an.combinations. Sie stehen hinter den Art-Umhuellenden (unten).
        umhuellende_ek: dict = {}
        for n, c in model.combinations.items():
            if c.ist_umhuellende:
                env, geloest = umhuellende_der_kombination(model, c, an.cases, systeme,
                                                           workers, progress)
                umhuellende_ek[n] = env
                an.info.setdefault("umhuellende", {})[n] = {
                    "alternativen": len(c.alternativen), "geloest": geloest}
        an.info["_umhuellende_ek"] = umhuellende_ek
    # Theorie je Lastfall: II. oder III. Ordnung ersetzt das lineare Ergebnis
    _lastfaelle_hoeherer_ordnung(model, an, systeme, progress)
    th2 = [n for n, c in model.combinations.items() if model.theorie_von(c) == "II"]
    if th2 and an.combinations:
        # Gleichgewicht am verformten System: die Kombinationen werden
        # ersetzt, denn nach Theorie II. Ordnung gilt keine Superposition
        # mehr (EN 1993-1-1, 5.2). Danach erst die Umhuellenden bilden.
        # Ausdruecklich auf "II" gestellte Kombinationen werden immer
        # gerechnet, die uebrigen nach der Einstellung (auto: alpha_cr).
        from .theorie2 import check_theorie2
        erzwungen = {n for n in th2 if (model.combinations[n].theorie or "").upper() == "II"}
        t2 = check_theorie2(model, an, combos=th2, system=system, progress=progress,
                            systeme=systeme, erzwungen=erzwungen)
        if an.theorie2 is None:
            an.theorie2 = t2
        else:                       # Lastfaelle nach II. Ordnung stehen schon darin
            an.theorie2.kombinationen.update(t2.kombinationen)
            an.theorie2.settings.update(t2.settings)
    th3 = [n for n, c in model.combinations.items() if model.theorie_von(c) == "III"]
    if th3 and an.combinations:
        from .theorie3 import check_theorie3
        t3 = check_theorie3(model, an, combos=th3, progress=progress, systeme=systeme)
        if an.theorie3 is None:
            an.theorie3 = t3
        else:
            an.theorie3.kombinationen.update(t3.kombinationen)
            an.theorie3.settings.update(t3.settings)
    umhuellende_ek = an.info.pop("_umhuellende_ek", {}) or {}
    if envelopes:
        groups: dict[str, dict] = {}
        for n, r in an.combinations.items():
            typ = model.combinations[n].typ
            key = "ULS" if typ in ("ULS", "EQU", "ACC", "USER") else typ
            groups.setdefault(key, {})[n] = r
        for key, rs in groups.items():
            an.envelopes[key] = Envelope(model, rs, f"Umhuellende {key}")
        # Die Umhuellende einer Ergebniskombination gehoert in die Umhuellende
        # ihrer Art: so sehen die Nachweise (GZT, GZG, Ermuedung) auch die
        # Alternativen - wie in RFEM.
        for n, env in umhuellende_ek.items():
            typ = model.combinations[n].typ
            key = "ULS" if typ in ("ULS", "EQU", "ACC", "USER") else typ
            if key not in an.envelopes:
                an.envelopes[key] = Envelope(model, {}, f"Umhuellende {key}")
            an.envelopes[key].aufnehmen_umhuellende(env)
        if not an.combinations and not umhuellende_ek:
            an.envelopes["CASES"] = Envelope(model, an.cases, "Umhuellende Lastfaelle")
    for n, env in umhuellende_ek.items():
        an.envelopes[n] = env
    _melde(progress, "Umhüllende gebildet", 0.92)
    if design and model.members:
        from .ec3.design import check_members
        _melde(progress, "Nachweise EC3", 0.94)
        an.design = check_members(model, an, progress=progress)
    if fatigue and model.fatigue_loads:
        from .ec3.fatigue import check_fatigue
        an.fatigue = check_fatigue(model, an, progress=progress)
    if design and model.joints:
        # Anschluesse gehoeren zu den Nachweisen: sie laufen mit, sobald
        # Nachweise verlangt sind (DIN EN 1993-1-8 / -1-9).
        from .joints.anschluss import check_joints
        an.joints = check_joints(model, an, progress=progress, ermuedung=bool(fatigue))
    if design and model.verformungsgrenzen:
        from .gzg import check_verformung
        an.gzg = check_verformung(model, an, progress=progress)
    if design and model.beulfelder:
        from .ec3.beulen import check_beulen
        an.beulen = check_beulen(model, an, progress=progress)
    if design and model.lasteinleitungen:
        from .ec3.beulen import check_lasteinleitungen
        an.lasteinleitung = check_lasteinleitungen(model, an, progress=progress)
    if design and model.volumenbereiche:
        from .ec3.volumen import check_volumen
        an.volumen = check_volumen(model, an, progress=progress)
    an.info.update({"time": time.time() - t0, "parallel": parallel.describe(),
                    "solver": system.backend, "ndof": model.ndof,
                    "nfree": len(system.fi)})
    _melde(progress, f"Berechnung fertig ({time.time() - t0:.1f} s)", 1.0)
    return an


# ==========================================================================
# Modalanalyse
# ==========================================================================
def solve_modal(model: Model, nmodes: int = 8, progress=None, workers: int = None,
                aktiv=None, zusatzmasse=None) -> Results:
    """Eigenfrequenzen und Eigenformen. ``aktiv``: Elementmaske einer Situation;
    ``zusatzmasse``: zusaetzliche Massenmatrix (ndof x ndof), z. B. die
    hydrodynamische Masse eines Verschlusses (schwingung.zusatzmassen)."""
    t0 = time.time()
    K = asm.stiffness(model, workers, aktiv)
    M = asm.mass(model, workers, aktiv)
    if zusatzmasse is not None:
        M = (M + zusatzmasse).tocsr()
    fixed, vals = asm.constrained_dofs(model, K)
    md = np.asarray(M.diagonal()).ravel()
    fixed = fixed | (md <= 0)
    fi = np.where(~fixed)[0]
    Kff = K[fi][:, fi].tocsc()
    Mff = M[fi][:, fi].tocsc()
    if progress:
        _melde(progress, "Eigenwertproblem wird gelöst", 0.45)

    k = min(nmodes, Kff.shape[0] - 2)
    vals_, vecs = eigsh(Kff, k=k, M=Mff, sigma=0.0, which="LM")
    order = np.argsort(vals_)
    vals_ = np.maximum(vals_[order], 0.0)
    vecs = vecs[:, order]

    freqs = np.sqrt(vals_) / (2 * np.pi)
    modes = np.zeros((k, model.ndof))
    for i in range(k):
        modes[i, fi] = vecs[:, i]
        mx = np.abs(modes[i]).max()
        if mx > 0:
            modes[i] /= mx

    res = Results(name="Modalanalyse", kind="modal", model=model)
    res.u = np.zeros((model.nn, NDOF))
    res.reactions = np.zeros((model.nn, NDOF))
    res.freqs = freqs
    res.modes = modes[:, :model.nn * NDOF].reshape(k, model.nn, NDOF)
    res.info = {"ndof": model.ndof, "nfree": len(fi), "time": time.time() - t0,
                "zusatzmasse": zusatzmasse is not None}
    return res


# ==========================================================================
# Lineares Knicken
# ==========================================================================
def solve_buckling(model: Model, nmodes: int = 5, progress=None, case: str = None,
                   combination: str = None, workers: int = None) -> Results:
    """Lineares Verzweigungsproblem: (K + lambda*Kg) v = 0 (Stabtragwerke).
    Grundzustand: Lastfall (default aktiver) oder Kombination."""
    t0 = time.time()
    system = StaticSystem(model, workers, progress)
    if combination:
        static = solve_combination(model, model.combinations[combination], None, system, workers)
    else:
        static = solve_static(model, progress, case, workers, system)
    u = static.u.ravel()
    K = system.K
    Kg = asm.geometric_stiffness(model, u)
    fi = system.fi
    Kff = system.Kff
    Kgff = Kg[fi][:, fi].tocsc()
    if abs(Kgff).max() == 0:
        raise RuntimeError("Keine Normalkraefte vorhanden - Knicknachweis nicht moeglich")
    if progress:
        _melde(progress, "Verzweigungsproblem wird gelöst", 0.45)

    k = min(nmodes, Kff.shape[0] - 2)
    vals_, vecs = eigsh(Kff, k=k, M=-Kgff, sigma=0.0, which="LM")
    order = np.argsort(np.abs(vals_))
    vals_ = vals_[order]
    vecs = vecs[:, order]

    modes = np.zeros((k, model.ndof))
    for i in range(k):
        modes[i, fi] = vecs[:, i]
        mx = np.abs(modes[i]).max()
        if mx > 0:
            modes[i] /= mx

    res = static
    res.kind = "buckling"
    res.buckling_factors = vals_
    res.buckling_modes = modes[:, :model.nn * NDOF].reshape(k, model.nn, NDOF)
    res.info["time"] = time.time() - t0
    return res
