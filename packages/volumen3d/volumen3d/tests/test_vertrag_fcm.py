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
                           (FcmSettings(base_cell_size_mm=50.0, backend="tpu"), "backend"), (FcmSettings(base_cell_size_mm=50.0, coupling="forces"), "coupling")):
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
    e_bs = s.solve(disc_b, prov, [ResultKey("LF2"), ResultKey("LF1", stellung_id="S2")], progress=lambda t, a: None)
    e_b = e_bs[0]
    Fb, _ = summe(e_b)
    Fb2, _ = summe(e_bs[1])
    V = 600.0 * 100.0 * 200.0
    check("Volumenlast: Summe der Schnittkraft-Aenderungen = -b V (< 10 %, Nitsche-Strafanteil)", np.linalg.norm((Fb - F2) + b * V) < 0.10 * np.linalg.norm(b * V),
          f"{Fb - F2} gegen {-b * V}")
    # body_load wirkt nach Vertrag 2.1.0 auf alle Keys (Gutachten 28.09.2026: bisher nur an einem Key geprueft);
    # der Stub liefert fuer beide Keys dieselben Randverschiebungen, also auch dieselben Schnittkraefte
    check("Volumenlast wirkt auf jeden Key (zweiter Key mit anderer Stellung: gleiche Schnittkraefte, Protokoll traegt body_load)",
          np.allclose(Fb2, Fb, rtol=1e-9, atol=1e-9) and all(e.protocol["body_load"] is not None for e in e_bs), f"{Fb2} / {Fb}")
    # Fehlerfaelle
    for last, text in ((SurfaceLoad("x", SurfaceSelector("D1", named_surface="gibt_es_nicht"), "LF1", pressure=1.0), "Flaeche"),
                       (SurfaceLoad("y", SurfaceSelector("D9", named_surface="balken"), "LF1", pressure=1.0), "body_id")):
        try:
            s.prepare(dataclasses.replace(spec0, loads=(last,)), mat, progress=lambda t, a: None)
            ok = False
        except SolverError as ex:
            ok = text in str(ex)
        check(f"Last mit unbekannter {text} -> SolverError", ok)


def test_zylinderauswahl():
    """SurfaceSelector.cylinder waehlt nur die Bohrungswand (Gutachten 28.09.2026: ohne Normalenpruefung
    kamen Punkte der ebenen Seiten im 2-%-Ring mit, Kirsch: 345,6 statt 314,2 mm2)."""
    import dataclasses
    from statik3d_contracts.detail import GeometrySource, GeometrySourceType
    from statik3d_contracts.model import Material
    from statik3d_contracts.nonlinear import SurfaceLoad, SurfaceSelector
    from volumen3d.api import FcmSolver
    geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "differenz", "teile": [
        {"typ": "quader", "min": [195, -50, -100], "max": [805, 50, 100], "name": "balken"},
        {"typ": "zylinder", "p0": [500, -60, 0], "p1": [500, 60, 0], "radius": 20.0, "name": "bohrung"}]}})
    spec = dataclasses.replace(_spec(p=2, h=50.0), geometry=geo)
    A_soll = 2 * np.pi * 20.0 * 100.0                      # Mantel der Bohrung durch die Dicke 100
    lasten = (SurfaceLoad("zyl", SurfaceSelector("D1", cylinder=(np.array([500.0, 0, 0]), np.array([0.0, 1, 0]), 20.0)), "LF1",
                          traction=np.array([0.0, 0.0, 1.0])),
              SurfaceLoad("name", SurfaceSelector("D1", named_surface="bohrung"), "LF2", traction=np.array([0.0, 0.0, 1.0])))
    disc = FcmSolver().prepare(dataclasses.replace(spec, loads=lasten), Material("S355", "S355", 210000.0, 0.3), progress=lambda t, a: None)
    p_zyl, p_name = disc.lasten_protokoll
    check("Zylinderauswahl: nur die Bohrungswand (Flaeche 2 pi r t auf 1e-4), gleich der benannten Flaeche 'bohrung'",
          abs(p_zyl["area_mm2"] / A_soll - 1) < 1e-4 and abs(p_zyl["area_mm2"] - p_name["area_mm2"]) < 1e-6 * A_soll
          and abs(p_zyl["force_N"][2] / A_soll - 1) < 1e-4,
          f"Zylinder {p_zyl['area_mm2']:.3f}, benannt {p_name['area_mm2']:.3f}, soll {A_soll:.3f} mm2")


def test_loeserwahl():
    """backend 'auto' waehlt den im Gesamtweg schnelleren Weg (Theorie 11.10): Mehrgitter auf der GPU ab
    _AUTO_MIN_DOFS Freiheitsgraden bei genug GPU-Speicher, sonst direkt; 'gpu' faellt ohne GPU oder bei zu
    wenig Speicher auf die CPU zurueck (Vorgabe 9), 'cpu' ist immer direkt."""
    import dataclasses
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d import api
    alt = api._gpu_frei_mb
    try:
        api._gpu_frei_mb = lambda: 8000.0
        n_gross = api._AUTO_MIN_DOFS + 1
        faelle = [("cpu", 10 ** 6, "direkt"), ("auto", 50_000, "direkt"), ("auto", n_gross, "mehrgitter"), ("gpu", 50_000, "mehrgitter")]
        ok = all(api._loeserwahl(b, 2000, 1500, 3, n)[0] == erw for b, n, erw in faelle)
        api._gpu_frei_mb = lambda: 0.0
        l0, g0, _, w0 = api._loeserwahl("gpu", 2000, 1500, 3, n_gross)
        la, _, grund_a, _ = api._loeserwahl("auto", 2000, 1500, 3, n_gross)
        api._gpu_frei_mb = lambda: 100.0                    # zu wenig Speicher fuer 2000 Zellen p 3
        l1, _, _, w1 = api._loeserwahl("gpu", 2000, 1500, 3, n_gross)
        check("Loeserwahl: cpu direkt, auto klein direkt, auto gross GPU-Mehrgitter, gpu GPU-Mehrgitter; ohne GPU bzw. mit "
              "zu wenig Speicher Rueckfall auf direkt mit Warnung",
              ok and l0 == "direkt" and g0 == "cpu" and w0 and la == "direkt" and "keine GPU" in grund_a and l1 == "direkt" and w1,
              f"{w0} / {grund_a} / {w1}")
    finally:
        api._gpu_frei_mb = alt
    # durchgehend: backend 'gpu' gegen 'cpu' am Kragarm-Ausschnitt (klein - 'auto' waehlt direkt)
    s = api.FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3, 7.85e-9)
    prov = StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0)
    spec = _spec(p=2, h=50.0)
    erg = {}
    for b in ("cpu", "gpu", "auto"):
        sp_b = dataclasses.replace(spec, settings=dataclasses.replace(spec.settings, backend=b))
        est = s.estimate(sp_b)
        disc = s.prepare(sp_b, mat, progress=lambda t, a: None)
        e = s.solve(disc, prov, [ResultKey("LF1")], progress=lambda t, a: None)[0]
        erg[b] = (est, disc, e)
    e_c, e_g = erg["cpu"][2], erg["gpu"][2]
    gpu_da = api._gpu_frei_mb() > 0
    f_s = np.abs(e_g.stress - e_c.stress).max() / np.abs(e_c.stress).max()
    f_u = np.abs(e_g.displacement - e_c.displacement).max() / np.abs(e_c.displacement).max()
    m_c = np.concatenate([pl["multipliers"] for pl in e_c.coupling_check["planes"]])
    m_g = np.concatenate([pl["multipliers"] for pl in e_g.coupling_check["planes"]])
    f_m = np.abs(m_g - m_c).max() / max(np.abs(m_c).max(), 1.0)
    wahl_g = e_g.protocol["solver_choice"]
    if gpu_da:
        ok_g = wahl_g["geraet"] == "gpu" and "mehrgitter" in erg["gpu"][1].summary()["solver_path"]
    else:
        ok_g = wahl_g["geraet"] == "cpu" and any("Rueckfall" in w for w in e_g.warnings)
    # Verschiebungen mit: Vorgabe 9 verlangt 1e-6 gegen den Direktloeser, und mit der frueheren Toleranz
    # 1e-10 lagen sie in den Mehrgitter-Tests bis 4,3e-6 daneben (Gutachten 28.09.2026)
    check(f"backend 'gpu' ({'GPU vorhanden' if gpu_da else 'ohne GPU: Rueckfall'}): Verschiebungen, Spannungen und Multiplikatoren "
          f"(< 1e-6) wie 'cpu'; 'auto' waehlt beim kleinen Modell direkt; estimate nennt den Weg ({erg['auto'][0]['solver_path']}, "
          f"{erg['auto'][0]['choice']})",
          ok_g and f_u < 1e-6 and f_s < 1e-6 and f_m < 1e-6 and erg["auto"][2].protocol["solver_choice"]["loeser"] in ("pardiso", "superlu")
          and erg["auto"][0]["solver_path"] == "direkt",
          f"Verschiebungen {f_u:.1e}, Spannungen {f_s:.1e}, Multiplikatoren {f_m:.1e}, Wahl gpu {wahl_g}")
    # 'auto' nur fuer gemessene Grade; Speicherschaetzung waechst mit p
    alt = api._gpu_frei_mb
    try:
        api._gpu_frei_mb = lambda: 1e9
        wahl_p = {p: api._loeserwahl("auto", 2000, 1500, p, api._AUTO_MIN_DOFS + 1)[0] for p in (1, 2, 3, 4)}
    finally:
        api._gpu_frei_mb = alt
    bedarf = [api._gpu_speicher_mb(2000, 1500, p, 300_000) for p in (1, 2, 3, 4)]
    check("'auto': Mehrgitter nur bei p 3 (gemessen), sonst direkt; Speicherschaetzung waechst mit p",
          wahl_p == {1: "direkt", 2: "direkt", 3: "mehrgitter", 4: "direkt"} and all(a < b for a, b in zip(bedarf, bedarf[1:])),
          f"{wahl_p}, Schaetzung {[round(b) for b in bedarf]} MB")
    # Rueckfall beim Aufbau: jeder Fehler des GPU-Wegs (hier erzwungen) fuehrt auf den Direktloeser
    from volumen3d.fcm import mehrgitter as mg_modul
    alt_wahl, alt_init = api._loeserwahl, mg_modul.PMehrgitter.__init__

    def kaputt(self, *a, **k):
        raise RuntimeError("Probe: GPU-Kompilat fehlt")

    try:
        api._loeserwahl = lambda *a, **k: ("mehrgitter", "gpu", "Probe", [])
        mg_modul.PMehrgitter.__init__ = kaputt
        disc_r = s.prepare(spec, mat, progress=lambda t, a: None)
    finally:
        api._loeserwahl, mg_modul.PMehrgitter.__init__ = alt_wahl, alt_init
    e_r = s.solve(disc_r, prov, [ResultKey("LF1")], progress=lambda t, a: None)[0]
    f_r = np.abs(e_r.stress - e_c.stress).max() / np.abs(e_c.stress).max()
    check("GPU-Fehler beim Aufbau: Rueckfall auf den Direktloeser mit Warnung, Ergebnis wie 'cpu'",
          disc_r.loeserwahl["geraet"] == "cpu" and disc_r.problem._zelldaten is None and f_r < 1e-12
          and any("Rueckfall" in w for w in e_r.warnings), f"{disc_r.loeserwahl}, Abweichung {f_r:.1e}")
    # Rueckfall beim Loesen: der GPU-Weg scheitert im PCG, solve baut direkt neu auf
    disc_l = s.prepare(spec, mat, progress=lambda t, a: None)
    pr_l = disc_l.problem
    pr_l.backend = "gpu"
    loesen_alt = type(pr_l).loesen

    def loesen_probe(self, *a, **k):
        if self.backend == "gpu":
            raise RuntimeError("Probe: CUDA-Fehler im PCG")
        return loesen_alt(self, *a, **k)

    try:
        type(pr_l).loesen = loesen_probe
        e_l = s.solve(disc_l, prov, [ResultKey("LF1")], progress=lambda t, a: None)[0]
    finally:
        type(pr_l).loesen = loesen_alt
    f_l = np.abs(e_l.stress - e_c.stress).max() / np.abs(e_c.stress).max()
    check("GPU-Fehler beim Loesen: Rueckfall auf den Direktloeser mit Warnung, Ergebnis wie 'cpu'",
          pr_l.backend == "cpu" and f_l < 1e-12 and any("beim Loesen" in w for w in e_l.warnings),
          f"Abweichung {f_l:.1e}, Warnungen {e_l.warnings}")


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
    sys.exit(lauf([test_protokoll_und_registrierung, test_ablauf, test_gutachten_faelle, test_hybrid_platzhalter, test_lasten, test_zylinderauswahl, test_loeserwahl]))
