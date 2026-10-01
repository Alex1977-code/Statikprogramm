"""Oeffentliche Einstiegspunkte des Volumenmoduls (Vertrag Abschnitt 7 und 7a).

``FcmSolver`` (Entry Point ``fcm``): Detailmodell aus CSG-Geometrie
(``GeometrySource.params`` nach packages/volumen3d/docs/Entwurf.md 3.7), Schnittebenen als
Halbraeume (Werkstoff gegen die Normale, wie ``CutPlane.normal``), Verschiebungskopplung ueber
den ``GlobalFieldProvider``: Normalkomponente punktweise ueber Nitsche, in der Ebene die drei
Resultierenden als Mittelwertzwaenge (Entwurf 3.6, Projektion ``schnitt``). Ergebnis an der
Oberflaechentriangulierung, Schnittgroessenkontrolle je Ebene, vollstaendiges Protokoll.

``HybridAssemblySolver`` (Entry Point ``hybrid``): bis Teilprojekt 7 ein ehrlicher Platzhalter
ohne Faehigkeiten.
"""
from __future__ import annotations

import dataclasses
import time
from typing import Any, Callable

import numpy as np
from statik3d_contracts import CONTRACT_VERSION
from statik3d_contracts.coupling import GlobalFieldProvider
from statik3d_contracts.detail import (DetailModelSpec, DetailResult, FcmSettings, GeometrySourceType, HotSpotResult,
                                       RefinementRegion)
from statik3d_contracts.discretization import DiscretizationKind
from statik3d_contracts.model import Material, ResultKey
from statik3d_contracts.nonlinear import AssemblyModelSpec, AssemblyResult, LoadPath, StepResult, SurfaceLoad, SurfaceSelector
from statik3d_contracts.solver import ProgressCallback, SolverCancelled, SolverError

from . import __version__
from .fcm import rand
from .fcm.gitter import Gitter, Verfeinerung
from .fcm.problem import FcmProblem, Werkstoff
from .geometry.csg import Csg, Operation, aus_params
from .geometry.oberflaeche import Flaechenquadratur
from .geometry.sdf import Halbraum
from .postprocess.auswertung import von_mises
from .postprocess.hotspot import Nahtpunkt, nahtgeometrie, strukturspannungen
from .postprocess.konvergenz import konvergenzaussage


def _flaeche_waehlen(pr: FcmProblem, sel: SurfaceSelector, detail_id: str, last_id: str) -> Flaechenquadratur:
    """Oberflaechenpunkte nach SurfaceSelector (Vertrag 6a/2.1.0): benannte Grundform, Box oder Zylinder
    (Achspunkt, Achsrichtung, Radius; Toleranz 2 % des Radius, mindestens 0,01 mm)."""
    if sel.body_id != detail_id:
        raise SolverError(f"Last {last_id!r}: body_id {sel.body_id!r} ist nicht das Detail {detail_id!r}")
    fq = pr.oberflaeche
    P = fq.punkte
    if sel.named_surface is not None:
        maske = fq.name.astype(str) == sel.named_surface
        if not maske.any():
            namen = sorted(set(fq.name.astype(str).tolist()))
            raise SolverError(f"Last {last_id!r}: keine Flaeche {sel.named_surface!r}; vorhanden: {namen}")
    elif sel.box is not None:
        lo, hi = (np.asarray(sel.box[0], float).reshape(3), np.asarray(sel.box[1], float).reshape(3))
        eps = 1e-9 * float(np.max(hi - lo)) if np.any(hi > lo) else 0.0
        maske = np.all((P >= lo - eps) & (P <= hi + eps), axis=1)
        if not maske.any():
            raise SolverError(f"Last {last_id!r}: die Box {lo.tolist()} .. {hi.tolist()} enthaelt keinen Oberflaechenpunkt")
    elif sel.cylinder is not None:
        a0 = np.asarray(sel.cylinder[0], float).reshape(3)
        a = np.asarray(sel.cylinder[1], float).reshape(3)
        a = a / np.linalg.norm(a)
        r = float(sel.cylinder[2])
        rel = P - a0
        radial = rel - (rel @ a)[:, None] * a
        rho = np.linalg.norm(radial, axis=1)
        e_r = radial / np.maximum(rho, 1e-300)[:, None]
        # zusaetzlich radiale Normale verlangen: sonst kommen Punkte ebener Flaechen im 2-%-Ring um die
        # Bohrung mit (Gutachten 28.09.2026: Kirsch h 20, Bohrung R 20: 345,6 statt 314,2 mm2, davon
        # 24,7 mm2 Plattenseiten und 6,8 mm2 Symmetrieebenen)
        maske = (np.abs(rho - r) <= max(0.02 * r, 0.01)) & (np.abs(np.einsum("ij,ij->i", fq.normalen, e_r)) >= 0.9)
        if not maske.any():
            raise SolverError(f"Last {last_id!r}: kein Oberflaechenpunkt auf dem Zylinder mit Radius {r} (Toleranz 2 %, radiale Normale)")
    else:
        raise SolverError(f"Last {last_id!r}: SurfaceSelector ohne named_surface, box oder cylinder")
    return fq.auswahl(maske)


def _traktionsfeld(last: SurfaceLoad, fq: Flaechenquadratur) -> np.ndarray:
    """Traktion (nq,3) an den Quadraturpunkten: Druck (t = -p n), globale Traktion und Resultierende.
    Resultierende (Vertrag 2.1.0): Kraft als konstante Traktion F/A, Moment als linear verteilte
    Traktion omega x (P - c) mit omega = (tr J I - J)^-1 M, J = int r r^T dA um den Schwerpunkt c -
    so ist int (P - c) x t dA = M und int t dA = F, jedes Teilfeld ohne Nebenwirkung."""
    n = len(fq.punkte)
    T = np.zeros((n, 3))
    if last.pressure is not None:
        T -= float(last.pressure) * fq.normalen
    if last.traction is not None:
        T += np.broadcast_to(np.asarray(last.traction, float).reshape(3), (n, 3))
    if last.resultant is not None:
        F = np.asarray(last.resultant[0], float).reshape(3)
        M = np.asarray(last.resultant[1], float).reshape(3)
        w = fq.gewichte
        A = float(w.sum())
        c = (w[:, None] * fq.punkte).sum(axis=0) / A
        r = fq.punkte - c
        J = np.einsum("q,qi,qj->ij", w, r, r)
        T += F / A
        if np.any(M != 0.0):
            omega = np.linalg.solve(np.trace(J) * np.eye(3) - J, M)
            T += np.cross(omega, r)
    return T


def _lasten_vorbereiten(spec: DetailModelSpec, pr: FcmProblem) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    """Rechte Seiten der Flaechenlasten je Lastfall-ID und ihr Protokoll (Flaeche, Resultierende)."""
    vektoren: dict[str, np.ndarray] = {}
    protokoll: list[dict[str, Any]] = []
    for last in spec.loads:
        fq = _flaeche_waehlen(pr, last.surface, spec.id, last.id)
        T = _traktionsfeld(last, fq)
        f = rand.flaechenlast(pr.gitter, fq, T)
        vektoren[last.load_case_id] = vektoren.get(last.load_case_id, 0.0) + f
        w = fq.gewichte
        F = (w[:, None] * T).sum(axis=0)
        c = (w[:, None] * fq.punkte).sum(axis=0) / float(w.sum())
        M = (w[:, None] * np.cross(fq.punkte - c, T)).sum(axis=0)
        protokoll.append({"id": last.id, "load_case_id": last.load_case_id, "points": int(len(fq.punkte)),
                          "area_mm2": float(w.sum()), "centroid": c, "force_N": F, "moment_about_centroid_Nmm": M})
    return vektoren, protokoll

Fortschritt = Callable[[str, float], None]


def _geometrie(spec: DetailModelSpec) -> tuple[Csg, list[str]]:
    """CSG des Details, geschnitten mit den Halbraeumen der Schnittebenen ('schnitt_i')."""
    if spec.geometry.type == GeometrySourceType.CSG:
        params = spec.geometry.params
    elif spec.geometry.type == GeometrySourceType.STL:
        if not spec.geometry.path:
            raise SolverError("GeometrySource STL braucht einen Pfad")
        params = {"csg": {"typ": "stl", "pfad": spec.geometry.path, "name": spec.geometry.params.get("name", "stl")}}
    elif spec.geometry.type == GeometrySourceType.STEP:
        # STEP ueber gmsh-Tessellierung und den STL-Weg (Plan TP 5 B5, Theorie 11.15); Angaben in params: tessellation_mm
        # (groesste Facette, Vorgabe: Basiszellgroesse), elements_per_circle (Dreiecke je Vollkreis, Vorgabe 120), name
        if not spec.geometry.path:
            raise SolverError("GeometrySource STEP braucht einen Pfad")
        from .geometry.step import KRUEMMUNG_STANDARD, tesselliere
        prm = spec.geometry.params
        try:
            D, step_info = tesselliere(spec.geometry.path, float(prm.get("tessellation_mm", spec.settings.base_cell_size_mm)),
                                       int(prm.get("elements_per_circle", KRUEMMUNG_STANDARD)))
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        params = {"csg": {"typ": "stl", "dreiecke": D, "name": prm.get("name", "step")}}
    else:
        raise SolverError(f"Geometriequelle {spec.geometry.type.value!r} ist nicht umgesetzt (CSG, STL und STEP gibt es)")
    try:
        basis = aus_params(params)
    except (ValueError, KeyError, TypeError, OSError) as ex:
        raise SolverError(f"Geometrie: {ex}") from ex
    basis.tessellierung = step_info if spec.geometry.type == GeometrySourceType.STEP else None
    for f in basis.grundformen():
        # Windungszahl-Defekt > 1/4: Innen/Aussen ist an der Stichprobe nicht mehr eindeutig
        if getattr(f, "defekt", 0.0) > 0.25:
            raise SolverError(f"STL {f.name!r}: Windungszahl weicht bis {f.defekt:.2f} von 0/1 ab - Huelle nicht geschlossen "
                              f"oder uneinheitlich orientiert")
    namen = [f"schnitt_{i}" for i in range(len(spec.cut_planes))]
    if not spec.cut_planes:
        return basis, namen
    teile = (basis.wurzel,) + tuple(Halbraum(np.asarray(cp.origin, float), np.asarray(cp.normal, float), n)
                                    for cp, n in zip(spec.cut_planes, namen))
    try:
        geschnitten = Csg(Operation("schnitt", teile))
    except ValueError as ex:
        raise SolverError(str(ex)) from ex
    geschnitten.tessellierung = basis.tessellierung
    return geschnitten, namen


def _verfeinerung(spec: DetailModelSpec) -> Verfeinerung:
    """RefinementRegion des Vertrags -> Bereiche des Oktrees (p je Bereich kommt mit der p-Adaptivitaet)."""
    bereiche = tuple((np.asarray(r.center, float).reshape(3), float(r.radius_mm), float(r.target_cell_size_mm))
                     for r in spec.refinement)
    for _, radius, ziel in bereiche:
        if radius <= 0 or ziel <= 0:
            raise SolverError("RefinementRegion: radius_mm und target_cell_size_mm muessen positiv sein")
    return Verfeinerung(bereiche=bereiche)


_MAX_ZYKLEN = 4


def _einstellungen_pruefen(s: FcmSettings) -> None:
    if not s.base_cell_size_mm > 0:
        raise SolverError("base_cell_size_mm muss positiv sein")
    if not 1 <= int(s.p) <= 4:
        raise SolverError(f"p = {s.p}: Teilprojekt 1 unterstuetzt p = 1 ... 4")
    if s.backend not in ("auto", "cpu", "gpu"):
        raise SolverError(f"backend {s.backend!r}: 'auto', 'cpu' oder 'gpu'")
    if s.coupling != "displacement":
        raise SolverError(f"coupling {s.coupling!r}: Kraftkopplung kommt mit Teilprojekt 5")
    if not 0.0 <= float(s.alpha) < 1.0:
        raise SolverError("alpha muss in [0, 1) liegen")
    if not 0 <= int(s.adaptive_cycles) <= _MAX_ZYKLEN:
        raise SolverError(f"adaptive_cycles = {s.adaptive_cycles}: 0 bis {_MAX_ZYKLEN} (Vorgabe 8.4: 2 bis 4 adaptive Zyklen)")


# 'auto' waehlt den im Gesamtweg (Aufbau + Loesen) schnelleren Weg. Messung A6 (30.09.2026, Plan TP 5), Commit
# a0a5c74, freie Maschine, je Fall ein Prozess, zwei Skripte mit gleichen Zeiten (Aufbau bis 6 %, Loesen bis 8 %),
# p 3, 23 Faelle von 65 000 bis 497 000 FHG: das GPU-Mehrgitter ist in 7 Faellen schneller, Summe direkt 523 s,
# Mehrgitter 509 s - aber beim kompakten Block (Summe der acht Faelle 0,85, ab 185 000 FHG 0,73 bis 0,88) und nicht
# bei der duennen Kirsch-Scheibe (Summe 1,10, nur 2 von 15 Faellen schneller). Die vorher festgelegte Regel (N0, ab
# dem das Mehrgitter in jedem Fall hoechstens das 1,05-fache braucht und in der Summe 10 % schneller ist) findet
# kein N0, der groesste Fall liegt bei 1,09: 'auto' bleibt beim Direktloeser. Bei 10^6 FHG ist das Mehrgitter in
# beiden Familien vorn (Block 115 statt 280 s bei 46 GB Hauptspeicher des Direktloesers nach A3, Kirsch 62 statt
# 83 s); zwischen 497 000 und 968 000 fehlt die Messung. Es spart die Faktorisierung samt Substitution (Block h 14
# 21,2 s, Kirsch h 10 6,1 s) und braucht dafuer Zelldaten.matrix, Einrichten und PCG (11,0 bzw. 7,9 s); die
# Zellmatrizen sind auf beiden Wegen der groesste Posten und aehnlich gross. p 2: Mehrgitter immer langsamer (1,16
# bis 1,66), p 4: in 3 von 4 Faellen schneller (0,81 bis 0,99).
# Der Mechanismus bleibt stehen und ist mit _AUTO_MEHRGITTER abgeschaltet; 'gpu' erzwingt das Mehrgitter.
_AUTO_MEHRGITTER = False
_AUTO_MIN_DOFS = 200_000

# Oberflaechenspannungen des Vertragswegs aus der L2-Projektion (Vorgabe 11.1, Plan TP 5 B2, Theorie 11.12): nach
# der vorher festgelegten Regel gemessen - Patch und reine Biegung exakt, an vier Lame-Faellen der groesste
# Oberflaechenfehler kleiner als roh (p 2 h 20: 15 statt 57 %, p 3 h 10: 2,23 statt 2,29 %), K_t der Kirsch-Scheibe
# hoechstens 0,41 % verschoben, Randresiduum |sigma.n| auf freien Flaechen im Mittel 17 bis 20 % kleiner.
_SPANNUNG_GEGLAETTET = True


def _gpu_frei_mb() -> float:
    """Freier GPU-Speicher in MB, 0 ohne nutzbare GPU."""
    try:
        from .fcm.operator_gpu import verfuegbar
        if not verfuegbar():
            return 0.0
        import cupy  # type: ignore[import-untyped, import-not-found, unused-ignore]  # CI ohne cupy
        frei, _ = cupy.cuda.Device().mem_info
        return float(frei) / 1e6 + float(cupy.get_default_memory_pool().free_bytes()) / 1e6
    except Exception:                                          # pragma: no cover - Treiber-/Importfehler
        return 0.0


def _gpu_speicher_mb(n_zellen: int, n_cut: int, p: int, n_frei: int) -> float:
    """Geschaetzter Hoechststand des GPU-Speichers beim Einrichten des Mehrgitters (MB), wenn der Speicher
    knapp ist (der Glaetteraufbau gibt den Pool dann nach jeder Groessengruppe frei).

    Posten: Zellmatrizen der Schnittzellen und Glaetterbloecke der Ebenen p bis 2, beide symmetrisch gepackt
    (8 Byte mal s (s + 1) / 2; Glaetterbloecke im Mittel 1,08 mal so gross wie die Zelle, gemessen 1,01 bis
    1,07), die Matrizen der Ebenen p-1 bis 2 (die feine Matrix geht nicht auf die GPU), Indexfelder und Puffer
    (24 Byte je Blockzeile), Vektoren, und 900 MB fuer Teilstapel und Arbeitsfelder der Inversion (gemessen
    640 bis 860 MB). Geeicht an neun Faellen p 3 (Kirsch h 14 bis 8, Block h 20 bis 14, 65 000 bis 500 000
    Freiheitsgrade, 29.09.2026): die Schaetzung liegt 3 bis 26 % ueber dem gemessenen Hoechststand (1,0 bis
    2,8 GB; Pool und Karte auf 60 MB gleich). Vor dem Packen und mit der feinen Matrix auf der GPU waren es
    1,4 bis 5,3 GB. p 2 und p 4 sind nicht gemessen. Ohne freie Koordinaten (estimate vor dem Aufbau) gilt
    n_frei = n_dof als obere Schranke."""
    def gepackt(s: float) -> float:
        return 8.0 * s * (s + 1.0) / 2.0

    m3 = 3 * (p + 1) ** 3
    k_cut = n_cut * gepackt(m3)
    # Glaetterbloecke auf den Ebenen p, p-1, ..., 2 (die Ebene 1 wird direkt geloest)
    stufen = [3 * (q + 1) ** 3 for q in range(2, p + 1)]
    glaetter = n_zellen * sum(gepackt(1.08 * sq) for sq in stufen)
    # Eintraege je Zeile: p 3 gemessen (310 bis 352 an acht Faellen, angesetzt 360); p 1, 2, 4 aus der Kopplung
    # im gleichmaessigen Gitter (81, 192, 648; Gutachten 28.09.2026). Die Ebene q hat rund (q/p)^3 der freien
    # Koordinaten; gemessen p 3 -> 2: 48 bis 54 Eintraege je feiner freier Koordinate, angesetzt 57
    je_zeile = {1: 81.0, 2: 192.0, 3: 360.0, 4: 648.0}
    matrizen = sum(12.0 * je_zeile.get(q, 648.0 * ((q + 1) / 5.0) ** 3) * n_frei * (q / p) ** 3 for q in range(2, p))
    index = 24.0 * n_zellen * (m3 + 1.08 * sum(stufen))
    vektoren = 100.0 * n_frei
    return (k_cut + glaetter + matrizen + index + vektoren) / 1e6 + 900.0


# Reserve auf die Schaetzung gegen den freien GPU-Speicher (andere Anwendungen, Fragmentierung)
_GPU_RESERVE = 1.2

# Polynomgrade, fuer die 'auto' das Mehrgitter waehlen darf: nur gemessene. Bei p 1 gibt es nur eine Ebene,
# das "Mehrgitter" waere die volle Zerlegung plus PCG und damit strikt langsamer als direkt; p 2 und p 4 sind
# fuer Schwelle und Speicher nicht gemessen (Gutachten 28.09.2026)
_AUTO_GRADE = (3,)


def _gpu_aufraeumen(pr: FcmProblem) -> None:
    """Felder eines gescheiterten GPU-Versuchs freigeben, bevor der Direktloeser faktorisiert."""
    import gc
    for name in ("_zelldaten", "_operator", "_mehrgitter", "_gpu"):
        setattr(pr, name, None)
    gc.collect()
    try:
        import cupy  # type: ignore[import-untyped, import-not-found, unused-ignore]  # CI ohne cupy
        cupy.get_default_memory_pool().free_all_blocks()
    except Exception:                                          # pragma: no cover - ohne cupy
        pass


def _loeserwahl(backend: str, n_zellen: int, n_cut: int, p: int, n_dof: int,
                n_frei: int | None = None) -> tuple[str, str, str, list[str]]:
    """(loeser, geraet, Begruendung, Warnungen). 'cpu': Direktloeser. 'gpu': Mehrgitter auf der GPU,
    Rueckfall auf den Direktloeser ohne GPU oder bei zu wenig Speicher (Vorgabe 9). 'auto': der im
    Gesamtweg schnellere Weg - derzeit immer der Direktloeser (_AUTO_MEHRGITTER, Messung oben); eingeschaltet
    Mehrgitter auf der GPU ab _AUTO_MIN_DOFS Freiheitsgraden bei p in _AUTO_GRADE und genug Speicher."""
    if backend == "cpu":
        return "direkt", "cpu", "backend 'cpu'", []
    frei = _gpu_frei_mb()
    bedarf = _gpu_speicher_mb(n_zellen, n_cut, p, n_dof if n_frei is None else n_frei)
    if backend == "gpu":
        if frei <= 0:
            return "direkt", "cpu", "keine GPU", ["backend 'gpu': keine nutzbare GPU gefunden - Rueckfall auf den Direktloeser "
                                                  "der CPU (gleiche Ergebnisse, Vorgabe 9)"]
        if _GPU_RESERVE * bedarf > frei:
            return "direkt", "cpu", "GPU-Speicher zu klein", [f"backend 'gpu': geschaetzt {bedarf:.0f} MB GPU-Speicher, frei "
                                                              f"{frei:.0f} MB - Rueckfall auf den Direktloeser der CPU"]
        return "mehrgitter", "gpu", f"backend 'gpu', {bedarf:.0f} von {frei:.0f} MB", []
    if not _AUTO_MEHRGITTER:
        return "direkt", "cpu", ("auto: Direktloeser - in der Schlussmessung (23 Faelle bis 500 000 Freiheitsgrade) meist schneller als das "
                                 "GPU-Mehrgitter; bei 10^6 Freiheitsgraden ist das Mehrgitter vorn (Theorie 11.10, Plan TP 5 A6); backend 'gpu' "
                                 "erzwingt es"), []
    if frei > 0 and p in _AUTO_GRADE and n_dof >= _AUTO_MIN_DOFS and _GPU_RESERVE * bedarf <= frei:
        return "mehrgitter", "gpu", f"auto: {n_dof} Freiheitsgrade >= {_AUTO_MIN_DOFS}, GPU {bedarf:.0f} von {frei:.0f} MB", []
    grund = ("keine GPU" if frei <= 0 else
             f"p {p}: Umschaltschwelle nur fuer p {', '.join(str(q) for q in _AUTO_GRADE)} gemessen" if p not in _AUTO_GRADE else
             f"{n_dof} Freiheitsgrade < {_AUTO_MIN_DOFS}" if n_dof < _AUTO_MIN_DOFS else
             f"GPU-Speicher: geschaetzt {bedarf:.0f} MB, frei {frei:.0f} MB")
    return "direkt", "cpu", f"auto: {grund}", []


def _oberflaeche(problem: FcmProblem) -> tuple[np.ndarray, np.ndarray]:
    """Dreiecke der Gesamtoberflaeche fuer Vorschau und Auswertepunkte aus den geclippten
    Polygonen der Flaechenquadratur: Ecken auf der exakten Flaeche, nur Werkstoffoberflaeche,
    nach aussen orientiert (an Zellgrenzen mit Naehten, an CSG-Schnittkurven nicht wasserdicht;
    Marching Cubes in TP 5). Die rohe Tessellierung der Grundformen reichte bei schraegen
    Schnittebenen in den Leerraum (Gutachten 27.09.)."""
    V, T = problem.oberflaeche.dreiecke(problem.geometrie)
    ecken: np.ndarray = np.array(V, dtype=float).reshape(-1, 3)
    dreiecke: np.ndarray = np.array(T, dtype=int).reshape(-1, 3)
    return ecken, dreiecke


class FcmDiskretisierung:
    """Erfuellt ``Discretization`` (Vertrag Abschnitt 4) und haelt das aufgebaute Problem."""
    kind: DiscretizationKind = DiscretizationKind.FCM_OCTREE

    def __init__(self, spec: DetailModelSpec, problem: FcmProblem, schnittnamen: list[str],
                 lasten: dict[str, np.ndarray] | None = None, lasten_protokoll: list[dict[str, Any]] | None = None) -> None:
        self.subsystem_id = spec.id
        self.spec = spec
        self.problem = problem
        self.schnittnamen = schnittnamen
        self.lasten = lasten or {}                      # Lastfall-ID -> rechte Seite der Flaechenlasten (2.1.0)
        self.lasten_protokoll = lasten_protokoll or []
        self.loeserwahl: dict[str, Any] = {}
        # adaptive Zyklen (Plan TP 5 B4): Werkstoff und Ausgangsspezifikation, aus denen die naechsten Zyklen entstehen,
        # Schritt dieses Zyklus und die lokale Zielzellgroesse an den Naehten (None: noch nicht verfeinert)
        self.material: Material | None = None
        self.spec0: DetailModelSpec = spec
        self.schritt = "Start"
        self.k_h = 0                                      # Zahl der lokalen Halbierungen an den Naehten bisher
        self.uebersprungen: list[str] = []                # h-Schritte ohne Wirkung vor diesem Zyklus (Gutachten C2, G3-2)
        self._oberflaeche: tuple[np.ndarray, np.ndarray] | None = None
        self._naehte: list[tuple[Any, list[Nahtpunkt]]] | None = None
        self.naht_warnungen: list[str] = []

    def naehte(self) -> list[tuple[Any, list[Nahtpunkt]]]:
        """Nahtgeometrie je WeldLine mit method 'hot_spot', einmal je Diskretisierung (haengt nur an der Geometrie).
        Punkte ohne eindeutige Blechseite bleiben ohne Wert, ihre Gruende stehen in ``naht_warnungen``."""
        if self._naehte is None:
            self._naehte = []
            for wl in self.spec.weld_lines:
                if wl.method != "hot_spot":
                    self.naht_warnungen.append(f"Naht {wl.id!r}: Verfahren {wl.method!r} ist nicht umgesetzt (nur 'hot_spot', "
                                               f"IIW Typ a) - uebergangen")
                    continue
                try:
                    q = nahtgeometrie(self.problem.geometrie, np.asarray(wl.points, float), float(wl.plate_thickness_mm))
                except ValueError as ex:
                    self.naht_warnungen.append(f"Naht {wl.id!r}: {ex}")
                    continue
                schlecht = [(i, x.warnung) for i, x in enumerate(q) if not x.ok]
                if schlecht:
                    self.naht_warnungen.append(f"Naht {wl.id!r}: {len(schlecht)} von {len(q)} Punkten ohne Strukturspannung, "
                                               f"z. B. Punkt {schlecht[0][0]}: {schlecht[0][1]}")
                self._naehte.append((wl, q))
        return self._naehte

    def dof_count(self) -> int:
        return int(self.problem.gitter.n_dof)

    def bounding_box(self) -> tuple[np.ndarray, np.ndarray]:
        lo, hi = self.problem.geometrie.huellquader()
        return np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)

    def summary(self) -> dict[str, float | int | str]:
        g = self.problem.gitter
        ag = self.problem.aggregation
        zw = self.problem.zwaenge.statistik
        return {"kind": self.kind.value, "subsystem": self.subsystem_id, "p": int(g.p or 0), "cell_size_mm": g.h,
                "cells": int(len(g.ijk)), "inside_cells": int((g.klasse == 1).sum()), "cut_cells": int((g.klasse == 2).sum()),
                "levels": ", ".join(f"{l}: {n}" for l, n in sorted(g.ebenen_verteilung().items())),
                "max_level": int(g.max_ebene), "hanging_faces": int(zw["haengende_flaechen"]),
                "dofs": self.dof_count(), "dofs_free": int(zw["moden_frei"] * 3),
                "aggregated_cells": int(ag.statistik["zellen_schlecht"]) if ag is not None else 0,
                "quadrature_points": int(self.problem.quadratur.anzahl_punkte()),
                "surface_points": int(len(self.problem.oberflaeche.punkte)), "length_unit": "mm",
                "solver_path": str(self.loeserwahl.get("loeser", self.problem.loeser)),
                "backend": str(self.loeserwahl.get("geraet", self.problem.backend))}

    def oberflaeche(self) -> tuple[np.ndarray, np.ndarray]:
        if self._oberflaeche is None:
            self._oberflaeche = _oberflaeche(self.problem)
        return self._oberflaeche

    def preview_geometry(self) -> dict[str, np.ndarray]:
        V, T = self.oberflaeche()
        lo, hi = self.problem.gitter.zellbox(np.arange(len(self.problem.gitter.ijk)))
        return {"vertices": V, "triangles": T, "cell_boxes": np.concatenate([lo, hi], axis=1),
                "cell_class": self.problem.gitter.klasse.copy()}


class FcmSolver:
    name: str = "fcm"
    contract_version: str = CONTRACT_VERSION

    def estimate(self, spec: DetailModelSpec) -> dict[str, Any]:
        s = spec.settings
        _einstellungen_pruefen(s)
        g, _ = _geometrie(spec)
        try:
            G = Gitter(g, float(s.base_cell_size_mm), 0.1, _verfeinerung(spec))
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        G.moden_nummerieren(int(s.p))
        m = (int(s.p) + 1) ** 3
        nnz = len(G.ijk) * (3 * m) ** 2
        n_cut = int((G.klasse == 2).sum())
        loeser, geraet, grund, warn = _loeserwahl(s.backend, len(G.ijk), n_cut, int(s.p), int(G.n_dof))
        return {"dofs": int(G.n_dof), "cells": int(len(G.ijk)), "cut_cells": n_cut,
                "levels": G.ebenen_verteilung(),
                "memory_mb": round(nnz * 16 / 1e6 + G.n_dof * 8 * 40 / 1e6, 1), "backend": geraet, "solver": self.name,
                "solver_path": "pcg-mehrgitter (gpu)" if loeser == "mehrgitter" else "direkt",
                "gpu_memory_mb": round(_gpu_speicher_mb(len(G.ijk), n_cut, int(s.p), int(G.n_dof)), 1),
                "choice": grund, "warnings": warn,
                "note": "Speicher der Faktorisierung kommt beim Direktloeser hinzu"
                        + (f"; Groessen fuer Zyklus 0 - mit adaptive_cycles {int(s.adaptive_cycles)} wachsen Freiheitsgrade und Speicher je "
                           f"Zyklus (lokale h-Halbierung an den Naehten, p + 1 bis 4), am T-Stoss etwa auf das 80-Fache" if int(s.adaptive_cycles) > 0 else "")}

    def prepare(self, spec: DetailModelSpec, material: Material, progress: ProgressCallback | None = None) -> FcmDiskretisierung:
        s = spec.settings
        _einstellungen_pruefen(s)
        if not spec.cut_planes:
            raise SolverError("Detailmodell ohne Schnittebene: kein Verschiebungsrand, das Detail waere "
                              "ungelagert (Vertrag 2.1.0 kennt Lasten am Detail, aber keine Lagerungen)")
        for wl in spec.weld_lines:
            # sofort pruefen, nicht erst beim Verfeinerungsbereich des ersten Zyklus (Meldung zu RefinementRegion, Gutachten C2, G3-7)
            if not (np.isfinite(float(wl.plate_thickness_mm)) and float(wl.plate_thickness_mm) > 0.0):
                raise SolverError(f"Naht {wl.id!r}: Blechdicke {wl.plate_thickness_mm} mm - muss positiv sein")
        melden: Fortschritt = progress or (lambda t, a: None)
        g, namen = _geometrie(spec)
        melden("Gitter, Quadratur und Oberflaeche", 0.05)
        try:
            pr = FcmProblem(g, h=float(s.base_cell_size_mm), p=int(s.p),
                            werkstoff=Werkstoff(float(material.E), float(material.nu), float(material.rho)),
                            alpha=float(s.alpha), verfeinerung=_verfeinerung(spec))
            for n in namen:
                pr.verschiebungsrand(n, n, projektion="schnitt")
            # Lasten am Detail (Vertrag 2.1.0): Volumenlast fuer alle Keys, Flaechenlasten je Lastfall-ID
            if spec.body_load is not None:
                b = np.asarray(spec.body_load, float).reshape(3)
                if np.any(b != 0.0):
                    pr.volumenlast(b)
            lasten, lasten_protokoll = _lasten_vorbereiten(spec, pr)
        except ValueError as ex:
            raise SolverError(str(ex)) from ex
        # Loeserwahl: der im Gesamtweg schnellere Weg (Theorie 11.10) - Mehrgitter auf der GPU fuer grosse
        # Modelle, sonst der Direktloeser; 'cpu'/'gpu' erzwingen, 'gpu' faellt ohne GPU auf die CPU zurueck
        n_cut = int((pr.gitter.klasse == 2).sum())
        loeser, geraet, grund, warnungen = _loeserwahl(s.backend, len(pr.gitter.ijk), n_cut, int(pr.p), int(pr.gitter.n_dof),
                                                       int(pr.zwaenge.C.shape[1]))
        pr.loeser, pr.backend = loeser, geraet
        # Vertragstoleranz gilt fuer das relative Residuum; fuer Verschiebungen auf 1e-6 gegen den
        # Direktloeser (Vorgabe 9) rechnet das Mehrgitter bis 1e-12. Gemessen auf dem Stand mit
        # Aggregationsschwelle 0,4 (Kragarm-Ausschnitt h 25/16 ueber diese Schicht, Block h 25/20, 29.09.2026):
        # bei 1e-10 weichen die Verschiebungen um 1,5e-10 bis 1,7e-8 ab, bei 1e-12 um 7,6e-13 bis 9,7e-11, das
        # Loesen dauert 19 bis 29 % laenger. Vor der Aggregationskorrektur lagen sie bei 1e-10 bis 4,3e-6
        # daneben; der Kommentar hier behauptete 1e-8 (Gutachten 28.09.2026).
        pr.toleranz = min(float(s.tolerance), 1e-12)
        melden("Steifigkeit assemblieren", 0.3)
        gpu_fehler = ""
        try:
            pr.aufbauen(lambda t, a: melden(t, 0.3 + 0.6 * a))
        except Exception as ex:                                 # Speicher, NVRTC, cuBLAS, Treiber, Bloecke
            if geraet != "gpu":
                if isinstance(ex, ValueError):
                    raise SolverError(str(ex)) from ex
                raise
            gpu_fehler = f"{type(ex).__name__}: {ex}"
        if gpu_fehler:
            # ausserhalb des except-Blocks: der Traceback hielt sonst die Felder des gescheiterten Versuchs
            # (Ebenenmatrizen, Grobgitterzerlegung, GPU-Bloecke) waehrend der Faktorisierung fest
            _gpu_aufraeumen(pr)
            warnungen.append(f"GPU-Mehrgitter fehlgeschlagen ({gpu_fehler}); Rueckfall auf den Direktloeser der CPU")
            loeser, geraet, grund = "direkt", "cpu", grund + " -> Rueckfall CPU"
            pr.loeser, pr.backend = loeser, geraet
            try:
                pr.aufbauen(lambda t, a: melden(t, 0.3 + 0.6 * a))
            except ValueError as ex:
                raise SolverError(str(ex)) from ex
        melden("Diskretisierung bereit", 1.0)
        disc = FcmDiskretisierung(spec, pr, namen, lasten, lasten_protokoll)
        disc.material = material
        disc.loeserwahl = {"loeser": pr.protokoll.get("loeser", loeser), "geraet": geraet, "begruendung": grund,
                           "warnungen": list(warnungen)}
        return disc

    def solve(self, disc: FcmDiskretisierung, provider: GlobalFieldProvider, keys: list[ResultKey],
              progress: ProgressCallback | None = None, cancel: Callable[[], bool] | None = None) -> list[DetailResult]:
        """Loest alle Keys; mit ``adaptive_cycles`` > 0 folgen Zyklen mit lokaler h-Halbierung an den Naehten und p + 1 (Plan
        TP 5 B4, ohne Fehlerschaetzer - der kommt mit TP 6). Ergebnis ist der letzte Zyklus, ``convergence`` traegt alle."""
        melden: Fortschritt = progress or (lambda t, a: None)
        abbruch = cancel or (lambda: False)
        if not isinstance(disc, FcmDiskretisierung):
            raise SolverError("solve braucht die Diskretisierung aus FcmSolver.prepare")
        n_zyklen = int(disc.spec0.settings.adaptive_cycles)
        if n_zyklen == 0:
            ergebnisse = self._zyklus(disc, provider, keys, melden, abbruch)
            for e in ergebnisse:
                # dieselben Protokollschluessel wie mit Zyklen (Gutachten C2, G3-9): eine Rechnung ist eine Folge der Laenge 1
                e.protocol["cycles"] = 0
                e.protocol["convergence_statement"] = konvergenzaussage([c.get("hotspot_max") for c in e.convergence])
            return ergebnisse

        def im_zyklus(z: int, von: float = 0.0, bis: float = 1.0) -> Fortschritt:
            """Fortschritt des Zyklus z auf das Intervall [z + von, z + bis] von n_zyklen + 1 abgebildet (Vorbereitung und
            Loesen eines Zyklus melden je 0 bis 1 und bekommen je einen Teil, sonst sprang der Balken zurueck)."""
            return lambda text, a: melden(f"Zyklus {z}: {text}", (z + von + (bis - von) * min(max(a, 0.0), 1.0)) / (n_zyklen + 1))
        t_z = time.perf_counter()
        ergebnisse = self._zyklus(disc, provider, keys, im_zyklus(0), abbruch)
        kurven: list[list[dict[str, Any]]] = [[] for _ in keys]
        for k, e in enumerate(ergebnisse):
            kurven[k].append({**e.convergence[0], "t_s": round(time.perf_counter() - t_z, 3)})
        d = disc
        hinweise: list[str] = []
        for z in range(1, n_zyklen + 1):
            if abbruch():
                raise SolverCancelled(f"abgebrochen vor Zyklus {z}")
            t_z = time.perf_counter()
            if d is not disc:
                # die Faktorisierung des Vorzyklus wird nicht mehr gebraucht (seine Ergebnisse stehen fest): vor dem Aufbau des naechsten
                # freigeben, sonst lebten drei Diskretisierungen samt Faktorisierung zugleich (Gutachten C2, G3-7); die des Zyklus 0 gehoert
                # dem Aufrufer und bleibt
                _loeser_freigeben(d)
            try:
                nxt = self._naechster_zyklus(d, im_zyklus(z, 0.0, 0.4))
                if nxt is None:
                    hinweise.append(f"adaptive Zyklen nach {z - 1} beendet: lokale Zellgroesse an den Naehten bei t/4 (oder keine Naht) "
                                    f"und p = {_P_MAX} erreicht")
                    break
                neue = self._zyklus(nxt, provider, keys, im_zyklus(z, 0.4, 1.0), abbruch)
            except SolverCancelled:
                raise
            except SolverError as ex:
                # ein Fehler im spaeteren Zyklus verwarf vorher auch alle fertigen (G3-7); jetzt gilt der letzte fertige Zyklus mit Warnung
                hinweise.append(f"Zyklus {z} gescheitert ({ex}) - Ergebnis aus Zyklus {z - 1}")
                break
            d = nxt
            for schritt_ohne in getattr(nxt, "uebersprungen", []):
                hinweise.append(f"Zyklus {z}: {schritt_ohne} ohne Wirkung auf das Netz (an den Naehten ist es schon so fein, etwa durch "
                                f"eigene Verfeinerungsbereiche) - uebersprungen, der Fahrplan ging weiter")
            ergebnisse = neue
            for k, e in enumerate(ergebnisse):
                kurven[k].append({**e.convergence[0], "cycle": z, "t_s": round(time.perf_counter() - t_z, 3)})
        for k, e in enumerate(ergebnisse):
            kurve = kurven[k]
            for a, b in zip(kurve[:-1], kurve[1:]):
                ha, hb = a.get("hotspot_max"), b.get("hotspot_max")
                b["hotspot_change"] = (hb - ha) / abs(ha) if ha not in (None, 0.0) and hb is not None else None
            aussage = konvergenzaussage([c.get("hotspot_max") for c in kurve])
            e.convergence = kurve
            e.protocol["cycles"] = len(kurve) - 1
            e.protocol["convergence_statement"] = aussage
            e.warnings.extend(hinweise)
            if aussage["art"] in ("nicht_monoton", "ohne_aenderung"):
                e.warnings.append("Konvergenz der Strukturspannung: " + aussage["text"])
        melden("Zyklen abgeschlossen", 1.0)
        return ergebnisse

    def _naechster_zyklus(self, disc: FcmDiskretisierung, melden: Fortschritt) -> FcmDiskretisierung | None:
        """Diskretisierung des naechsten Zyklus nach ``_fahrplan``: zuerst lokale h-Halbierung an den Naehten bis t/4, dann
        p + 1 bis p = 4, danach None (Ende der Folge)."""
        s0 = disc.spec0
        if disc.material is None:
            raise SolverError("adaptive Zyklen brauchen die Diskretisierung aus FcmSolver.prepare")
        p = int(disc.spec.settings.p)
        naehte = [wl for wl in s0.weld_lines if len(np.asarray(wl.points).reshape(-1, 3)) > 0]
        basis = float(s0.settings.base_cell_size_mm)
        k_h = disc.k_h
        uebersprungen: list[str] = []
        while True:
            schritt = _fahrplan(p, k_h, basis, [float(wl.plate_thickness_mm) for wl in naehte])
            if schritt is None:
                return None
            if schritt == "h":
                k_h += 1
                spec = dataclasses.replace(s0, settings=disc.spec.settings,
                                           refinement=tuple(s0.refinement) + _nahtregionen(naehte, k_h, basis))
            else:
                spec = dataclasses.replace(disc.spec, settings=dataclasses.replace(disc.spec.settings, p=p + 1))
            neu = self.prepare(spec, disc.material, melden)
            # eine h-Halbierung, die das Netz nicht aendert (eigene Verfeinerung schon feiner), waere ein Zyklus ohne Wirkung - er brachte
            # die Aussage 'letzte Aenderung null, konvergent' (Gutachten C2, G3-2); uebergehen und den Fahrplan weiterschalten
            if schritt == "h" and len(neu.problem.gitter.ijk) == len(disc.problem.gitter.ijk) and neu.problem.gitter.n_dof == disc.problem.gitter.n_dof:
                uebersprungen.append(f"h-Halbierung auf {_nahtziel(basis, k_h, min(float(wl.plate_thickness_mm) for wl in naehte)):g} mm")
                continue
            break
        neu.spec0 = s0
        neu.k_h = k_h
        neu.schritt = "h-Halbierung Naht" if schritt == "h" else "p-Erhoehung"
        neu.uebersprungen = uebersprungen
        return neu

    def _zyklus(self, disc: FcmDiskretisierung, provider: GlobalFieldProvider, keys: list[ResultKey],
                melden: Fortschritt, abbruch: Callable[[], bool]) -> list[DetailResult]:
        """Ein Zyklus: rechte Seiten, Loesen, Auswertung fuer alle Keys (bisheriger Rumpf von ``solve``)."""
        pr = disc.problem
        t0 = time.perf_counter()
        vorgaben: list[dict[str, np.ndarray]] = []
        for k, key in enumerate(keys):
            if abbruch():
                raise SolverCancelled("abgebrochen vor der rechten Seite")
            v: dict[str, np.ndarray] = {}
            for n in disc.schnittnamen:
                P = pr.raender[n].quadratur.punkte
                u, _ = provider.displacement_at(P, key)
                u = np.asarray(u, float).reshape(-1, 3)
                schlecht = ~np.isfinite(u).all(axis=1)
                if schlecht.any():
                    i = int(np.flatnonzero(schlecht)[0])
                    raise SolverError(f"Provider liefert NaN fuer {key} auf Schnittebene {n} an {int(schlecht.sum())} "
                                      f"von {len(P)} Punkten, z. B. {P[i]} (Punkt ohne Zuordnung im Globalmodell?)")
                v[n] = u
            vorgaben.append(v)
            melden(f"Randverschiebungen {key.load_case_id}", 0.2 * (k + 1) / max(len(keys), 1))
        if abbruch():
            raise SolverCancelled("abgebrochen vor dem Loesen")
        # Flaechenlasten nur fuer Keys mit passender Lastfall-ID (Vertrag 2.1.0)
        zusatz = [disc.lasten.get(key.load_case_id) for key in keys]
        gpu_fehler = ""
        try:
            U = pr.loesen(vorgaben, zusatzlasten=zusatz)
        except Exception as ex:
            if isinstance(ex, ValueError) and (pr.backend != "gpu" or str(ex).startswith("Last nicht im Gleichgewicht")):
                raise SolverError(str(ex)) from ex
            if pr.backend != "gpu":
                raise
            gpu_fehler = f"{type(ex).__name__}: {ex}"
        if gpu_fehler:
            # GPU-Fehler im PCG (Speicher, Treiber, NaN, Stagnation): direkt neu aufbauen und loesen
            _gpu_aufraeumen(pr)
            pr.loeser, pr.backend = "direkt", "cpu"
            disc.loeserwahl.setdefault("warnungen", []).append(
                f"GPU-Mehrgitter beim Loesen fehlgeschlagen ({gpu_fehler}); Rueckfall auf den Direktloeser der CPU")
            disc.loeserwahl.update({"loeser": "direkt", "geraet": "cpu",
                                    "begruendung": str(disc.loeserwahl.get("begruendung", "")) + " -> Rueckfall CPU beim Loesen"})
            try:
                pr.aufbauen()
                U = pr.loesen(vorgaben, zusatzlasten=zusatz)
            except ValueError as ex:
                raise SolverError(str(ex)) from ex
        melden("Gleichungssystem geloest", 0.7)
        V, T = disc.oberflaeche()
        # Auswertepunkte minimal in den Werkstoff ruecken, damit die Punktsuche eine aktive Zelle findet
        Pe = V - 1e-7 * pr.gitter.h * pr.geometrie.gradient(V) if len(V) else V
        ergebnisse: list[DetailResult] = []
        # Rueckgewinnung fuer alle Keys in einem Aufruf: die rechten Seiten kosten je Aufruf eine Zellschleife (Block h 9,
        # 10^6 FHG: 12 s), die weiteren Spalten fast nichts (Messung B2/B3, 30.09.2026)
        X_alle = None
        if _SPANNUNG_GEGLAETTET and len(Pe):
            from .postprocess.rueckgewinnung import rueckgewinnung
            X_alle = rueckgewinnung(pr).knoten(U)
        for k, key in enumerate(keys):
            if abbruch():
                raise SolverCancelled("abgebrochen bei der Auswertung")
            aus = pr.auswertung(U[:, k])
            if X_alle is not None:
                aus.knoten_setzen(X_alle[:, :, k:k + 1])
            try:
                if len(Pe):
                    s_e, u_e = aus.spannung_und_verschiebung(Pe)
                    if _SPANNUNG_GEGLAETTET:
                        s_e = aus.spannung_geglaettet(Pe)
                else:
                    s_e, u_e = np.zeros((0, 6)), np.zeros((0, 3))
                ebenen = []
                warn: list[str] = list(disc.loeserwahl.get("warnungen", []))
                # Strukturspannung am Nahtuebergang (IIW Typ a, Vorgabe 11.2) aus derselben Spannung wie stress
                hot: list[HotSpotResult] = []
                naht_protokoll: dict[str, Any] = {}
                spannung_fn = aus.spannung_geglaettet if _SPANNUNG_GEGLAETTET else aus.spannung
                for wl, q in disc.naehte():
                    vorher = sum(1 for x in q if x.ok)
                    erg_n = strukturspannungen(q, spannung_fn, 1e-7 * pr.gitter.h)
                    if len(erg_n) < vorher:
                        warn.append(f"Naht {wl.id!r}: {vorher - len(erg_n)} Punkte ohne Strukturspannung, Referenzpunkt ausserhalb der Zellen")
                    hot += [HotSpotResult(weld_line_id=wl.id, position=np.asarray(np_.position, float).copy(), stress=hs,
                                          method="hot_spot IIW Typ a (0,4 t / 1,0 t, linear)") for np_, hs, _, _ in erg_n]
                    naht_protokoll[wl.id] = {"punkte": len(q), "ohne_wert": len(q) - len(erg_n), "blechdicke_mm": float(wl.plate_thickness_mm),
                                             "sigma_hs_max": _massgebend([hs for _, hs, _, _ in erg_n]),
                                             "sigma_04t": [s04 for _, _, s04, _ in erg_n], "sigma_10t": [s10 for _, _, _, s10 in erg_n]}
                warn += disc.naht_warnungen
                w_int = _integrationswarnung(pr.quadratur.statistik, pr.oberflaeche.statistik)
                if w_int:
                    warn.append(w_int)
                mg = getattr(pr, "_mehrgitter", None)
                if pr.loeser == "mehrgitter" and mg is not None:
                    warn += [str(w) for w in mg.statistik.get("warnungen", [])]
                for f in pr.geometrie.grundformen():
                    if getattr(f, "defekt", 0.0) > 1e-3:
                        warn.append(f"STL {f.name!r}: Huelle hat kleine Luecken (Windungszahl-Defekt {f.defekt:.3f}, "
                                    f"{getattr(f, 'offene_kanten', 0)} offene Kanten); Innen/Aussen bleibt eindeutig, die Zellen werden ohne "
                                    f"Huellenintegration (Zerlegung an lokalen Ebenen) integriert, Flaechenlasten auf der Luecke fehlen")
                    elif getattr(f, "offene_kanten", 0) > 0:
                        warn.append(f"STL {f.name!r}: Huelle nicht geschlossen ({f.offene_kanten} offene Kanten, Windungszahl-Defekt "
                                    f"{getattr(f, 'defekt', 0.0):.1e}); die Zellen werden ohne Huellenintegration integriert")
                for i, (n, cp) in enumerate(zip(disc.schnittnamen, disc.spec.cut_planes)):
                    fq = pr.raender[n].quadratur
                    F, M = aus.schnittgroessen(fq, cp.origin)
                    sf = provider.section_forces(cp, key)
                    f_g = np.asarray(sf.force, float).reshape(3)
                    m_g = np.asarray(sf.moment, float).reshape(3)
                    # Bezug fuer die relative Abweichung: groesste beteiligte Resultierende; Momente auch
                    # gegen Kraft mal Flaechenmass, damit reine Biegung (Q = 0) oder reiner Zug (M = 0)
                    # keine Scheinabweichung melden (Gutachten 27.09.: 2,5e3 bei Nullwerten)
                    kennwerte = _schnittkennwerte(fq, cp.origin, cp.normal)
                    dF, dM, ref_s = _kopplungsabweichung(F, M, f_g, m_g, kennwerte)
                    ref_f = ref_s * kennwerte["A"]
                    ref_m = ref_s * (float(np.linalg.eigvalsh(kennwerte["I"]).min()) / max(kennwerte["r_max"], 1e-300))
                    # Konvention der FCM-Seite: F = int sigma.n dA mit n aus dem Detail heraus, also die
                    # Kraft, die der abgeschnittene Teil auf das Detail ausuebt (Vorschlag zur Klarstellung:
                    # docs/vertrag-aenderungen/2026-09-27-lasten-und-schnittgroessen.md)
                    ebenen.append({"plane": i, "force_fcm": F, "force_global": f_g, "moment_fcm": M, "moment_global": m_g,
                                   "delta_force": F - f_g, "delta_moment": M - m_g,
                                   "deviation_force": dF, "deviation_moment": dM, "reference_force": ref_f, "reference_moment": ref_m,
                                   "reference_stress": ref_s, "deviation_measure": "stress: (|dN|+|dQ|)/A and max edge stress of dM, / reference stress",
                                   "convention": "force_fcm = int sigma.n dA, n out of the detail",
                                   "multipliers": np.asarray(pr.multiplikatoren[3 * i:3 * i + 3, k], float)})
            except ValueError as ex:
                raise SolverError(f"Auswertung fuer {key}: {ex}") from ex
            for i, eb in enumerate(ebenen):
                dF, dM = eb["deviation_force"], eb["deviation_moment"]
                if dM > 0.05 or dF > 0.05:
                    warn.append(f"Schnittebene {i}: Abweichung der Schnittgroessen Kraft {dF * 100:.1f} %, Moment {dM * 100:.1f} % "
                                f"> 5 % (Vorgabe 16.7: Schnittebenen weiter auseinander legen, schubweiches Globalmodell oder Kraftkopplung)")
            rg = getattr(pr, "_rueckgewinnung", None)
            protokoll: dict[str, Any] = dict(pr.protokoll)
            protokoll.update({"solver": self.name, "contract_version": self.contract_version, "volumen3d": __version__,
                              "key": str(key), "coupling": "displacement (normal pointwise + in-plane resultants)",
                              "geometry": spec_kurz(disc.spec), "step_tessellation": getattr(pr.geometrie, "tessellierung", None),
                              "t_solve_s": round(time.perf_counter() - t0, 3),
                              "loads": [dict(l) for l in disc.lasten_protokoll if l["load_case_id"] == key.load_case_id],
                              "solver_choice": dict(disc.loeserwahl),
                              "hot_spot": {"verfahren": "IIW Typ a: Referenzpunkte 0,4 t und 1,0 t auf der Blechoberflaeche senkrecht zur "
                                                        "Naht, sigma_hs = 5/3 sigma(0,4t) - 2/3 sigma(1,0t), Komponente senkrecht zur Naht",
                                           "spannung": "geglaettet (L2-Projektion)" if _SPANNUNG_GEGLAETTET else "roh",
                                           "naehte": naht_protokoll},
                              "settings": _einstellungen_protokoll(disc, rg is not None),
                              "stress_recovery": (dict(rg.statistik, ausgabe="geglaettet (L2-Projektion)")
                                                  if _SPANNUNG_GEGLAETTET and rg is not None else {"ausgabe": "roh (sigma = D B u)"}),
                              "body_load": None if disc.spec.body_load is None else np.asarray(disc.spec.body_load, float).reshape(3)})
            ergebnisse.append(DetailResult(detail_id=disc.subsystem_id, key=key, surface_points=V, surface_triangles=T,
                                           displacement=u_e, stress=s_e, von_mises=von_mises(s_e) if len(s_e) else np.zeros(0),
                                           hot_spots=hot,
                                           coupling_check={"planes": ebenen}, warnings=warn, protocol=protokoll,
                                           convergence=[{"cycle": 0, "step": disc.schritt, "dofs": int(pr.gitter.n_dof), "p": pr.p,
                                                         "cells": int(len(pr.gitter.ijk)), "cut_cells": int((pr.gitter.klasse == 2).sum()),
                                                         "h_min_mm": float(pr.gitter.h / 2.0 ** int(pr.gitter.ebene.max())),
                                                         "hotspot_max": _massgebend([h.stress for h in hot]),
                                                         "hotspot_mean": float(np.mean([h.stress for h in hot])) if hot else None,
                                                         "stress_max": float(von_mises(s_e).max()) if len(s_e) else None,
                                                         "solver_path": str(disc.loeserwahl.get("loeser", pr.loeser)),
                                                         "iterations": _iterationen(pr, k)}]))
            melden(f"Ergebnis {key.load_case_id}", 0.7 + 0.3 * (k + 1) / max(len(keys), 1))
        return ergebnisse


_P_MAX = 4


def _loeser_freigeben(disc: FcmDiskretisierung) -> None:
    """Faktorisierung und Mehrgitter einer Diskretisierung freigeben; ein spaeteres Loesen baut sie neu auf (K None -> aufbauen)."""
    pr = disc.problem
    for name in ("_loeser", "_mehrgitter", "_gpu", "_operator", "K"):
        if hasattr(pr, name):
            setattr(pr, name, None)


def _massgebend(werte: list[float]) -> float | None:
    """Betragsgroesster Wert mit Vorzeichen: der massgebende Hot-Spot fuer Kurve und Konvergenzaussage (``hotspot_max``,
    ``sigma_hs_max``). Vorher das vorzeichenbehaftete Maximum - unter Druck der betragskleinste Punkt (Gutachten C2, G3-5)."""
    if not werte:
        return None
    return float(max(werte, key=abs))


def _nahtziel(basis_mm: float, k_h: int, dicke_mm: float) -> float:
    """Zielzellgroesse an einer Naht nach k_h lokalen Halbierungen: h0 / 2^k, nie unter t/4 (Plan TP 5 B4, 01.10.2026)."""
    return max(basis_mm / 2.0 ** k_h, 0.25 * dicke_mm)


def _fahrplan(p: int, k_h: int, basis_mm: float, dicken: list[float]) -> str | None:
    """Naechster Schritt der adaptiven Zyklen: 'h' (lokale Halbierung an den Naehten), solange eine Naht noch eine Zielgroesse
    ueber t/4 hat (der Referenzpunkt 0,4 t liegt dann mindestens 1,6 Zellen vom Uebergang; Entscheidung des Anwenders
    01.10.2026), danach 'p' (p + 1) bis p = 4, danach None. Ohne Naht nur 'p'."""
    if any(basis_mm / 2.0 ** k_h > 0.25 * t * (1.0 + 1e-9) for t in dicken):
        return "h"
    return "p" if p < _P_MAX else None


def _nahtregionen(wls: list[Any], k_h: int, basis_mm: float) -> tuple[RefinementRegion, ...]:
    """Kugeln vom Radius 2 t um Punkte der Nahtlinien mit der Zielzellgroesse ``_nahtziel``: Mittelpunkte sind Polylinienpunkte im Abstand
    von mindestens t (und der letzte Punkt); bei Punktabstaenden ueber 2 t entstehen Luecken zwischen den Kugeln - es wird nicht
    interpoliert, die Hot-Spots werden ohnehin nur an den Polylinienpunkten ausgewertet (Gutachten C2, G3-9)."""
    regionen: list[RefinementRegion] = []
    for wl in wls:
        P = np.asarray(wl.points, float).reshape(-1, 3)
        t = float(wl.plate_thickness_mm)
        ziel = _nahtziel(basis_mm, k_h, t)
        wahl = [0]
        for i in range(1, len(P)):
            if float(np.linalg.norm(P[i] - P[wahl[-1]])) >= t:
                wahl.append(i)
        if wahl[-1] != len(P) - 1:
            wahl.append(len(P) - 1)
        regionen += [RefinementRegion(center=P[i].copy(), radius_mm=2.0 * t, target_cell_size_mm=ziel) for i in wahl]
    return tuple(regionen)


def _schnittkennwerte(fq: Any, ursprung: np.ndarray, normale: np.ndarray) -> dict[str, Any]:
    """Querschnittswerte einer Schnittflaeche fuer die Kopplungskontrolle: Flaeche A, Schwerpunkt c, Achsen e1, e2 in der Ebene,
    Traegheiten I11, I22, I12 um den Schwerpunkt (Quadratur), Randabstaende aus den Quadraturpunkten (die aeussersten liegen
    wenige Hundertstel Millimeter vor dem Rand; die Polygone der Ebenenquadratur reichen ueber den Werkstoff hinaus und taugen
    dafuer nicht - am Knotenblech 45 statt 5 mm), polares Moment und groesster Randabstand fuer die Torsion."""
    n = np.asarray(normale, float).reshape(3)
    n = n / np.linalg.norm(n)
    e1 = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    P = np.asarray(fq.punkte, float).reshape(-1, 3)
    w = np.asarray(fq.gewichte, float).ravel()
    A = float(w.sum())
    c = (w[:, None] * P).sum(axis=0) / A if A > 0 else np.asarray(ursprung, float).reshape(3)
    r1, r2 = (P - c) @ e1, (P - c) @ e2
    I11, I22, I12 = float(w @ (r1 * r1)), float(w @ (r2 * r2)), float(w @ (r1 * r2))
    rand = np.stack([r1, r2], axis=1)
    return {"A": A, "c": c, "o": np.asarray(ursprung, float).reshape(3), "n": n, "e1": e1, "e2": e2, "I": np.array([[I11, I12], [I12, I22]]),
            "rand": rand, "Ip": I11 + I22, "r_max": float(np.linalg.norm(rand, axis=1).max()) if len(rand) else 0.0}


def _schnittspannungen(F: np.ndarray, M: np.ndarray, k: dict[str, Any]) -> tuple[float, float]:
    """(Kraftanteil, Momentanteil) als Spannungen: |N|/A + |Q|/A und groesste Randspannung aus Biegung plus Torsion (tau = T r_max / I_p,
    fuer duenne Querschnitte eine Unterschaetzung - nur Massstab). Das Moment wird vom Bezugspunkt der Schnittebene auf den Schwerpunkt
    umgerechnet (M_c = M - (c - o) x F)."""
    if k["A"] <= 0.0:
        return 0.0, 0.0
    F = np.asarray(F, float).reshape(3)
    Mc = np.asarray(M, float).reshape(3) - np.cross(k["c"] - k["o"], F)
    N = float(F @ k["n"])
    Q = F - N * k["n"]
    s_kraft = (abs(N) + float(np.linalg.norm(Q))) / k["A"]
    Mt = float(Mc @ k["n"])
    M1, M2 = float(Mc @ k["e1"]), float(Mc @ k["e2"])
    # sigma(r) = b1 r1 + b2 r2 mit int sigma r2 = M1, -int sigma r1 = M2 (r x sigma n, e1 x n = -e2): [[I11, I12], [I12, I22]] b = [-M2, M1]
    try:
        b = np.linalg.solve(k["I"], np.array([-M2, M1]))
    except np.linalg.LinAlgError:
        b = np.linalg.lstsq(k["I"], np.array([-M2, M1]), rcond=None)[0]
    s_biegung = float(np.abs(k["rand"] @ b).max()) if len(k["rand"]) else 0.0
    s_torsion = abs(Mt) * k["r_max"] / k["Ip"] if k["Ip"] > 0 else 0.0
    return s_kraft, s_biegung + s_torsion


def _kopplungsabweichung(F: np.ndarray, M: np.ndarray, f_g: np.ndarray, m_g: np.ndarray, kennwerte: dict[str, Any]) -> tuple[float, float, float]:
    """Relative Abweichung der Schnittgroessen (Kraft, Moment) gegen das Globalmodell, als Spannungen bewertet, und die Bezugsspannung.

    Kraftabweichung (|dN| + |dQ|)/A, Momentabweichung groesste Randspannung aus dM (Biegung mit den Traegheiten der Schnittflaeche plus
    Torsion), beide bezogen auf die groessere der Referenzspannungen von Detail und Globalmodell (Summe aus Kraft- und Momentanteil).
    Vorher (B7) ein gemeinsames Lastmass mit dem Hebel sqrt(A): an duennen Blechen ist das zwolfmal das Biegemoment, ein Detail mit nur
    40 % des Moments meldete 4,7 % statt einer Warnung (Gutachten C2, G3-3). Nullwerte beidseits: 0."""
    s_f, s_m = _schnittspannungen(F, M, kennwerte)
    g_f, g_m = _schnittspannungen(f_g, m_g, kennwerte)
    d_f, d_m = _schnittspannungen(np.asarray(F, float) - np.asarray(f_g, float), np.asarray(M, float) - np.asarray(m_g, float), kennwerte)
    bezug = max(s_f + s_m, g_f + g_m)
    if bezug <= 0.0:
        return 0.0, 0.0, 0.0
    return d_f / bezug, d_m / bezug, bezug


def _integrationswarnung(quad: dict[str, Any], flaeche: dict[str, Any]) -> str | None:
    """Warnung, wenn die Geometrie nur in erster Ordnung integriert wurde: Blaetter der Volumenintegration im Punkttest oder
    Flaechenstuecke im Rueckfall. Typisch fuer STL- und STEP-Huellen mit unregelmaessig tesselliertem gekruemmtem Rand (die
    lokale Lage ist dort 'gemischt', die Zerlegung an wenigen Ebenen scheitert; Theorie 11.15)."""
    n_pt = int(quad.get("blaetter_punkttest", 0))
    n_rf = int(flaeche.get("rueckfall", 0))
    if n_pt == 0 and n_rf == 0:
        return None
    return (f"Geometrie: {n_pt} Blaetter der Volumenintegration im Punkttest (erste Ordnung, Volumenfehler bis 0,5 %) und {n_rf} "
            f"Flaechenstuecke im Rueckfall - typisch fuer STL- und STEP-Huellen mit unregelmaessig tesselliertem gekruemmtem Rand; "
            f"feinere Zellen, gleichmaessigere Tessellierung oder CSG verbessern das")


def _iterationen(pr: FcmProblem, k: int) -> int | None:
    it = pr.protokoll.get("iterationen")
    if isinstance(it, (list, tuple)) and len(it) > k:
        return int(it[k])
    return None


def _einstellungen_protokoll(disc: FcmDiskretisierung, rueckgewinnung: bool) -> dict[str, Any]:
    """Alle Einstellungen des Zyklus, damit Nachweise pruefbar sind (Vorgabe 11.3): Vertragseinstellungen, Verfeinerung,
    verwendeter Rechenweg und Ausgabeart der Spannungen, Naehte, Versionen."""
    spec, s, pr = disc.spec, disc.spec.settings, disc.problem
    return {"p": int(s.p), "base_cell_size_mm": float(s.base_cell_size_mm),
            "refinement": [{"center": np.asarray(r.center, float).tolist(), "radius_mm": float(r.radius_mm),
                            "target_cell_size_mm": float(r.target_cell_size_mm)} for r in spec.refinement],
            "alpha": float(s.alpha), "tolerance": float(s.tolerance), "tolerance_used": float(pr.toleranz),
            "coupling": str(s.coupling), "adaptive_cycles": int(disc.spec0.settings.adaptive_cycles), "cycle_step": disc.schritt,
            "backend_requested": str(s.backend), "backend_used": str(disc.loeserwahl.get("geraet", pr.backend)),
            "solver_path": str(disc.loeserwahl.get("loeser", pr.loeser)),
            "moment_fitting": bool(pr.quadratur.momentfitting), "fit_grad": int(pr.quadratur.fit_grad) if pr.quadratur.momentfitting else None,
            "stress_output": "geglaettet (L2-Projektion)" if _SPANNUNG_GEGLAETTET and rueckgewinnung else "roh (sigma = D B u)",
            "aggregation_threshold": None if pr.aggregation is None else float(pr.aggregation.schwelle),
            "weld_lines": [{"id": wl.id, "points": int(len(np.asarray(wl.points).reshape(-1, 3))),
                            "plate_thickness_mm": float(wl.plate_thickness_mm), "method": wl.method} for wl in spec.weld_lines],
            "contract_version": CONTRACT_VERSION, "volumen3d": __version__}


def spec_kurz(spec: DetailModelSpec) -> dict[str, Any]:
    return {"id": spec.id, "name": spec.name, "source": spec.geometry.type.value, "cut_planes": len(spec.cut_planes),
            "material_id": spec.material_id, "base_cell_size_mm": spec.settings.base_cell_size_mm, "p": spec.settings.p,
            "alpha": spec.settings.alpha}


class HybridAssemblySolver:
    """Platzhalter bis Teilprojekt 7: registriert, aber ohne Faehigkeiten (die Oberflaeche graut alles aus)."""
    name: str = "hybrid"
    contract_version: str = CONTRACT_VERSION
    capabilities: frozenset[str] = frozenset()

    def estimate(self, spec: AssemblyModelSpec) -> dict[str, Any]:
        return {"dofs": 0, "memory_mb": 0.0, "backend": "cpu", "solver": self.name,
                "status": "nicht umgesetzt (Teilprojekt 7 des Volumenmoduls)"}

    def prepare(self, spec: AssemblyModelSpec, materials: dict[str, Material],
                progress: ProgressCallback | None = None) -> object:
        raise SolverError("HybridAssemblySolver ist noch nicht umgesetzt (Teilprojekt 7 des Volumenmoduls); "
                          "fuer die Oberflaeche steht der Stub des Vertragspakets bereit")

    def solve_path(self, handle: object, path: LoadPath, provider: GlobalFieldProvider | None = None,
                   progress: ProgressCallback | None = None, cancel: Callable[[], bool] | None = None,
                   on_step: Callable[[StepResult], None] | None = None) -> AssemblyResult:
        raise SolverError("HybridAssemblySolver ist noch nicht umgesetzt (Teilprojekt 7 des Volumenmoduls)")


__all__ = ["FcmSolver", "FcmDiskretisierung", "HybridAssemblySolver"]
