"""T9: FcmSolver erfuellt den Vertrag (Abschnitt 7): Protokoll, Entry Point, Ablauf mit dem
Stub-Provider, Kopplungskontrolle, Abbruch, Fehlerfaelle; HybridAssemblySolver als Platzhalter.

Aufruf: python -m volumen3d.tests.test_vertrag_fcm
"""
from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def _spec(p=2, h=50.0, x0=200.0, x1=800.0):
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType
    geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "quader", "min": [x0 - 5, -50, -100], "max": [x1 + 5, 50, 100], "name": "balken"}})
    return DetailModelSpec(id="D1", name="Kragarm-Ausschnitt", geometry=geo, material_id="S355",
                           cut_planes=(CutPlane(np.array([x0, 0, 0]), np.array([-1.0, 0, 0])), CutPlane(np.array([x1, 0, 0]), np.array([1.0, 0, 0]))),
                           settings=FcmSettings(base_cell_size_mm=h, p=p))


def test_protokoll_und_registrierung():
    """Protokolle und Entry Points. Dass der Lader des Hauptprogramms 'fcm' vor dem Stub waehlt,
    prueft tests/contracts/test_vertrag.py - volumen3d importiert statik3d nie (Vertrag Abschnitt 1)."""
    from importlib import metadata
    import statik3d_contracts as V
    from statik3d_contracts.solver import ENTRY_POINT_ASSEMBLY, ENTRY_POINT_SOLID, AssemblySolver, SolidDetailSolver
    from volumen3d.api import FcmSolver, HybridAssemblySolver
    check("FcmSolver erfuellt SolidDetailSolver", isinstance(FcmSolver(), SolidDetailSolver))
    check("HybridAssemblySolver erfuellt AssemblySolver (Platzhalter, capabilities leer)",
          isinstance(HybridAssemblySolver(), AssemblySolver) and HybridAssemblySolver().capabilities == frozenset())
    check("Vertragsversion des Pakets passt zum installierten Vertrag (Major)",
          V.vertragsversion_passt(FcmSolver.contract_version) and FcmSolver.contract_version == V.CONTRACT_VERSION, FcmSolver.contract_version)
    geladen = {ep.name: ep.load() for ep in metadata.entry_points(group=ENTRY_POINT_SOLID)}
    check("Entry Point 'fcm' laedt FcmSolver", geladen.get("fcm") is FcmSolver, str(sorted(geladen)))
    geladen2 = {ep.name: ep.load() for ep in metadata.entry_points(group=ENTRY_POINT_ASSEMBLY)}
    check("Entry Point 'hybrid' laedt HybridAssemblySolver", geladen2.get("hybrid") is HybridAssemblySolver, str(sorted(geladen2)))


def test_ablauf():
    from statik3d_contracts.discretization import Discretization, DiscretizationKind
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.solver import SolverCancelled, SolverError
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    spec = _spec()
    mat = Material("S355", "S355", 210000.0, 0.3, fy=355.0)
    est = s.estimate(spec)
    check("estimate: dofs, cells, cut_cells, memory_mb, backend", all(k in est for k in ("dofs", "cells", "cut_cells", "memory_mb", "backend")) and est["dofs"] > 0, str(est))
    meld = []
    disc = s.prepare(spec, mat, progress=lambda t, a: meld.append((t, a)))
    check("prepare -> Discretization FCM_OCTREE, Fortschritt bis 1.0", isinstance(disc, Discretization) and disc.kind == DiscretizationKind.FCM_OCTREE and abs(meld[-1][1] - 1) < 1e-12, str(meld[-1]))
    check("dof_count = estimate.dofs", disc.dof_count() == est["dofs"], f"{disc.dof_count()} / {est['dofs']}")
    zs = disc.summary()
    check("summary: cells, cut_cells, dofs, dofs_free, aggregated_cells, length_unit mm", all(k in zs for k in ("cells", "cut_cells", "dofs", "dofs_free", "aggregated_cells")) and zs["length_unit"] == "mm", str(zs))
    geo = disc.preview_geometry()
    check("preview: vertices (n,3), triangles (m,3), cell_boxes (k,6), cell_class (k,)",
          geo["vertices"].shape[1] == 3 and geo["triangles"].shape[1] == 3 and geo["cell_boxes"].shape[1] == 6 and len(geo["cell_class"]) == len(geo["cell_boxes"]) and len(geo["triangles"]) > 0,
          str({k: v.shape for k, v in geo.items()}))
    lo, hi = disc.bounding_box()
    check("bounding_box = Ausschnitt 600 x 100 x 200 (Schnittebenen beschneiden den Quader)", np.allclose(hi - lo, [600, 100, 200]), f"{hi - lo}")
    prov = StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0)
    keys = [ResultKey("LF1"), ResultKey("LF1", stellung_id="S2")]
    erg = s.solve(disc, prov, keys, progress=lambda t, a: None)
    n = len(erg[0].surface_points)
    check("je Key ein DetailResult mit Formen (n,3),(m,3),(n,3),(n,6),(n,)", len(erg) == 2 and erg[0].displacement.shape == (n, 3) and erg[0].stress.shape == (n, 6) and erg[0].von_mises.shape == (n,))
    cc = erg[0].coupling_check
    check("coupling_check je Schnittebene mit force/moment fcm und global, deviation, multipliers",
          len(cc["planes"]) == 2 and all(k in cc["planes"][0] for k in ("force_fcm", "force_global", "moment_fcm", "moment_global", "deviation_force", "deviation_moment", "multipliers")), str(cc)[:160])
    # Segment 3 h mit Euler-Bernoulli-Stub: Abweichung wie in test_kragarm (Timoshenko-Effekt), als Warnung ausgewiesen
    dm = cc["planes"][1]["deviation_moment"]
    check("Kopplungskontrolle weist die Abweichung zum schubstarren Stub aus (10 ... 60 %) und warnt ab 5 %",
          0.10 < dm < 0.60 and any("Schnittebene 1" in w for w in erg[0].warnings), f"{dm * 100:.1f} %, Warnungen: {erg[0].warnings}")
    pr = erg[0].protocol
    check("Protokoll: solver, contract_version, p, alpha, beta, tiefe, zellen, cut, dofs, loeser, aggregation, quadratur, Zeiten",
          all(k in pr for k in ("solver", "contract_version", "p", "alpha", "beta", "tiefe", "zellen", "cut", "dofs", "loeser", "aggregation", "quadratur", "t_assemblierung_s", "t_solve_s")), str(sorted(pr)))
    check("zweiter Key (andere Stellung, gleiches Feld beim Stub) liefert dasselbe Ergebnis", np.allclose(erg[0].displacement, erg[1].displacement))
    check("von Mises und Spannungen endlich, Verschiebungen in der Groessenordnung der Balkendurchbiegung",
          np.all(np.isfinite(erg[0].stress)) and np.all(np.isfinite(erg[0].von_mises)) and 0.1 < np.abs(erg[0].displacement[:, 2]).max() < 100.0, f"max |u_z| {np.abs(erg[0].displacement[:, 2]).max():.3f} mm")
    try:
        s.solve(disc, prov, keys, cancel=lambda: True)
        ab = False
    except SolverCancelled:
        ab = True
    check("cancel -> SolverCancelled", ab)

    class NaNProvider(StubGlobalFieldProvider):
        def displacement_at(self, P, key):
            u, r = super().displacement_at(P, key)
            u = np.array(u, float)
            u[0] = np.nan
            return u, r
    try:
        s.solve(disc, NaNProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0), keys[:1])
        f = False
    except SolverError as ex:
        f = "NaN" in str(ex)
    check("Provider liefert NaN -> SolverError mit Hinweis und Ort", f)
    from statik3d_contracts.detail import FcmSettings
    for schlecht, text in ((FcmSettings(base_cell_size_mm=50.0, p=7), "p"), (FcmSettings(base_cell_size_mm=-1.0), "base_cell_size"),
                           (FcmSettings(base_cell_size_mm=50.0, backend="gpu"), "backend"), (FcmSettings(base_cell_size_mm=50.0, coupling="forces"), "coupling")):
        try:
            s.estimate(dataclasses.replace(spec, settings=schlecht))
            f = False
        except SolverError:
            f = True
        check(f"ungueltige Einstellung ({text}) -> SolverError", f)
    from statik3d_contracts.detail import GeometrySource, GeometrySourceType
    try:
        s.estimate(dataclasses.replace(spec, geometry=GeometrySource(GeometrySourceType.STL, path="gibt_es_nicht.stl")))
        f = False
    except SolverError as ex:
        f = "Geometrie" in str(ex)
    check("STL-Quelle ohne Datei -> SolverError (Geometrie)", f)
    # echte STL-Datei (Wuerfel 100 mm) -> estimate rechnet damit
    import os
    import tempfile
    from volumen3d.geometry.sdf import Quader
    from volumen3d.geometry.stl import schreibe_stl
    V, T = Quader([0, 0, 0], [100, 100, 100]).dreiecke(None, None, 1.0)
    pfad = os.path.join(tempfile.mkdtemp(), "wuerfel.stl")
    schreibe_stl(pfad, V[T])
    e = s.estimate(dataclasses.replace(spec, geometry=GeometrySource(GeometrySourceType.STL, path=pfad), cut_planes=()))
    check("STL-Quelle (Wuerfel-Datei): estimate liefert Zellen und Freiheitsgrade", e.get("cells", 0) > 0 and e.get("dofs", 0) > 0, str({k: e[k] for k in list(e)[:6]}))


def test_gutachten_faelle():
    """Befunde der zweiten Sicht vom 27.09.2026: schraege Schnittebene (Vorschau nur im Werkstoff,
    kein nackter ValueError), Detail ohne Schnittebene, Nullwerte des Globalmodells."""
    import numpy as np
    from statik3d_contracts.coupling import CutPlane, SectionForces
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.solver import SolverError
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3)
    geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "w"}})
    # (1) schraege Schnittebene durch die Mitte
    n = np.array([1.0, 1.0, 1.0]) / np.sqrt(3)
    spec = DetailModelSpec("S", "schraeg", geo, "S355", (CutPlane(np.array([50.0, 50, 50]), n),), FcmSettings(base_cell_size_mm=25.0, p=1))
    disc = s.prepare(spec, mat)
    V, T = disc.oberflaeche()
    d = disc.problem.geometrie.abstand(V)
    check("schraege Schnittebene: alle Vorschau-Ecken liegen auf der Werkstoffoberflaeche (|d| < 1e-6 h)", len(V) > 0 and np.abs(d).max() < 1e-6 * 25.0, f"{len(V)} Ecken, max |d| {np.abs(d).max():.2e}")

    class Starr(StubGlobalFieldProvider):
        def displacement_at(self, P, key):
            P = np.asarray(P, float)
            return np.stack([0.001 * P[:, 0], np.zeros(len(P)), np.zeros(len(P))], axis=1), np.zeros((len(P), 3))

        def section_forces(self, plane, key):
            return SectionForces(np.zeros(3), np.zeros(3))
    erg = s.solve(disc, Starr(1000.0, 100.0, 200.0, 210000.0, 10000.0), [ResultKey("LF1")])
    check("schraege Schnittebene: solve liefert ein Ergebnis mit endlichen Spannungen (kein ValueError)",
          len(erg) == 1 and np.all(np.isfinite(erg[0].stress)) and len(erg[0].surface_points) == len(V))
    # (3) Nullwerte des Globalmodells: Kennzahlen bleiben beschraenkt (Bezug: groesste beteiligte Groesse)
    cc = erg[0].coupling_check["planes"][0]
    check("Nullwerte des Globalmodells: deviation_force und deviation_moment <= 1 (kein 2,5e3)",
          0 <= cc["deviation_force"] <= 1.0 and 0 <= cc["deviation_moment"] <= 1.0 and "delta_force" in cc, f"{cc['deviation_force']:.3f}, {cc['deviation_moment']:.3f}")
    # (2) Detail ohne Schnittebene
    try:
        s.prepare(DetailModelSpec("O", "ohne", geo, "S355", (), FcmSettings(base_cell_size_mm=50.0, p=1)), mat)
        f = False
    except SolverError as ex:
        f = "Schnittebene" in str(ex)
    check("Detail ohne Schnittebene -> SolverError (ungelagert)", f)
    # (2b) ungelagertes Problem auf der internen Schnittstelle: Residuumspruefung greift
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    pr = FcmProblem(aus_params(geo.params), h=50.0, p=1, werkstoff=Werkstoff(210000.0, 0.3))
    stirn = pr.oberflaeche.auswahl(np.abs(pr.oberflaeche.punkte[:, 0] - 100.0) < 1e-9)
    pr.traktion(None, np.array([100.0, 0, 0]), quadratur=stirn)
    try:
        pr.loesen({})
        f = False
    except ValueError as ex:
        f = "Residuum" in str(ex) or "Starrkoerper" in str(ex)
    check("ungelagerter Quader unter Traktion -> ValueError mit Residuum/Starrkoerper statt 1e12 mm", f)


def test_lasten():
    """Vertrag 2.1.0: Flaechenlasten je Lastfall-ID (Druck per Box, Resultierende mit Moment auf der
    benannten Flaeche), Volumenlast; Gleichgewicht: Summe der Schnittkraft-Aenderungen an beiden
    Schnittebenen = minus Lastresultierende (F_fcm = Wirkung des Restes auf das Detail)."""
    import dataclasses
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.nonlinear import SurfaceLoad, SurfaceSelector
    from statik3d_contracts.solver import SolverError
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3, 7.85e-9)
    prov = StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0)
    spec0 = _spec(p=2, h=50.0, x0=200.0, x1=800.0)
    # Druck 0,5 N/mm2 auf die Oberseite z = 100 (Box), nur LF1; Resultierende (Kraft + Moment) auf der ganzen
    # benannten Flaeche 'balken', nur LF3
    # Box duenn halten: sie waehlt Quadraturpunkte, und eine Box von 0,1 mm Dicke griffe Punkte der
    # Seitenflaechen dicht an der Kante mit (gemessen 60 034 statt 60 000 mm2)
    druck = SurfaceLoad("wasser", SurfaceSelector("D1", box=(np.array([0.0, -60.0, 99.999]), np.array([1000.0, 60.0, 100.001]))), "LF1", pressure=0.5)
    F_res, M_res = np.array([0.0, 2000.0, -3000.0]), np.array([1.0e5, 0.0, 2.0e5])
    res = SurfaceLoad("res", SurfaceSelector("D1", named_surface="balken"), "LF3", resultant=(F_res, M_res))
    spec = dataclasses.replace(spec0, loads=(druck, res))
    disc = s.prepare(spec, mat, progress=lambda t, a: None)
    keys = [ResultKey("LF1"), ResultKey("LF2"), ResultKey("LF3")]
    erg = s.solve(disc, prov, keys, progress=lambda t, a: None)

    def summe(e):
        F = sum(np.asarray(pl["force_fcm"], float) for pl in e.coupling_check["planes"])
        M = sum(np.asarray(pl["moment_fcm"], float) + np.cross(np.asarray(cp.origin, float), np.asarray(pl["force_fcm"], float))
                for pl, cp in zip(e.coupling_check["planes"], spec.cut_planes))
        return F, M                                   # Moment um den Ursprung

    F1, M1 = summe(erg[0])
    F2, M2 = summe(erg[1])
    F3, M3 = summe(erg[2])
    A_top = 600.0 * 100.0
    F_druck = np.array([0.0, 0.0, -0.5 * A_top])       # Druck auf z = 100 wirkt in -z
    p1 = erg[0].protocol["loads"]
    check("LF1: Druck per Box auf der Oberseite 60 000 mm2 (< 1e-6), Protokoll nennt Flaeche und Resultierende",
          len(p1) == 1 and abs(p1[0]["area_mm2"] - A_top) < 1e-6 * A_top and np.linalg.norm(p1[0]["force_N"] - F_druck) < 1e-6 * np.linalg.norm(F_druck),
          str(p1)[:200])
    # Die Schnittkraefte der Kopplungskontrolle sind int sigma.n dA; der Strafanteil des Nitsche-Randes
    # fehlt darin (Theorie 11.6), gemessen 5 % bei h 50 p 2. Die Lastaufbringung selbst ist ueber die
    # exakten Resultierenden im Protokoll geprueft; hier zaehlt die Zuordnung je Lastfall-ID.
    check("LF1 gegen LF2 (ohne Last): Summe der Schnittkraft-Aenderungen = -Lastresultierende (< 10 %, Nitsche-Strafanteil)",
          np.linalg.norm((F1 - F2) + F_druck) < 0.10 * np.linalg.norm(F_druck), f"{F1 - F2} gegen {-F_druck}")
    p3 = erg[2].protocol["loads"]
    c3 = np.asarray(p3[0]["centroid"], float)
    check("LF3: Resultierende trifft F und M um den Schwerpunkt (Verteilung konstant + linear)",
          np.allclose(p3[0]["force_N"], F_res, rtol=1e-9, atol=1e-6) and np.allclose(p3[0]["moment_about_centroid_Nmm"], M_res, rtol=1e-9, atol=1e-3),
          f"{p3[0]['force_N']} / {p3[0]['moment_about_centroid_Nmm']}")
    M_last = M_res + np.cross(c3, F_res)
    check("LF3 gegen LF2: Kraft- und Momentenaenderung an den Schnittebenen = -Resultierende um den Ursprung (< 15 %, Nitsche-Strafanteil)",
          np.linalg.norm((F3 - F2) + F_res) < 0.15 * np.linalg.norm(F_res) and np.linalg.norm((M3 - M2) + M_last) < 0.15 * np.linalg.norm(M_last),
          f"dF {F3 - F2} gegen {-F_res}; dM {M3 - M2} gegen {-M_last}")
    check("LF2 ohne passende Lastfall-ID: keine Last im Protokoll", erg[1].protocol["loads"] == [])
    # Volumenlast (Eigengewicht) fuer alle Keys: Vergleich zweier Diskretisierungen
    b = np.array([0.0, 0.0, -7.85e-9 * 9810.0])
    disc_b = s.prepare(dataclasses.replace(spec0, body_load=b), mat, progress=lambda t, a: None)
    e_b = s.solve(disc_b, prov, [ResultKey("LF2")], progress=lambda t, a: None)[0]
    Fb, _ = summe(e_b)
    V = 600.0 * 100.0 * 200.0
    check("Volumenlast: Summe der Schnittkraft-Aenderungen = -b V (< 10 %, Nitsche-Strafanteil)", np.linalg.norm((Fb - F2) + b * V) < 0.10 * np.linalg.norm(b * V),
          f"{Fb - F2} gegen {-b * V}")
    # Fehlerfaelle
    for last, text in ((SurfaceLoad("x", SurfaceSelector("D1", named_surface="gibt_es_nicht"), "LF1", pressure=1.0), "Flaeche"),
                       (SurfaceLoad("y", SurfaceSelector("D9", named_surface="balken"), "LF1", pressure=1.0), "body_id")):
        try:
            s.prepare(dataclasses.replace(spec0, loads=(last,)), mat, progress=lambda t, a: None)
            ok = False
        except SolverError as ex:
            ok = text in str(ex)
        check(f"Last mit unbekannter {text} -> SolverError", ok)


def test_hybrid_platzhalter():
    from statik3d_contracts.nonlinear import AssemblyModelSpec
    from statik3d_contracts.solver import SolverError
    from volumen3d.api import HybridAssemblySolver
    hs = HybridAssemblySolver()
    est = hs.estimate(AssemblyModelSpec("A", "leer", ()))
    check("estimate nennt 'nicht umgesetzt'", "nicht umgesetzt" in str(est.get("status", "")), str(est))
    try:
        hs.prepare(AssemblyModelSpec("A", "leer", ()), {})
        f = False
    except SolverError as ex:
        f = "Teilprojekt 7" in str(ex)
    check("prepare wirft SolverError mit Verweis auf Teilprojekt 7", f)


if __name__ == "__main__":
    sys.exit(lauf([test_protokoll_und_registrierung, test_ablauf, test_gutachten_faelle, test_hybrid_platzhalter, test_lasten]))
