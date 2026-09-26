"""Der Schnittstellenvertrag (docs/Schnittstellenvertrag_Statik3D_FCM.md) als Pruefung.

CI-Pflichttests nach Abschnitt 9, soweit sie das Hauptprogramm betreffen:

1. isinstance-Pruefungen der Protokolle fuer die Stubs und fuer die
   FE-Netz-Diskretisierung des Hauptprogramms - samt Gegenprobe: eine
   Klasse ohne Methode erfuellt das Protokoll nicht;
2. Import-Regeln (Abschnitt 1): das Vertragspaket importiert nur die
   Standardbibliothek und numpy;
3. die Stubs (Abschnitt 8) liefern Ergebnisse in den vereinbarten Formen,
   die Kopplung ist vektorisiert (10^5 Punkte unter 1 s), Balken- und
   Hertz-Formeln stimmen;
4. die Entry-Point-Registrierung (Abschnitt 7) findet den Stub, und die
   Versionspruefung (Abschnitt 9) weist eine fremde Major-Version ab.

Aufruf: python -m tests.contracts.test_vertrag
"""
from __future__ import annotations

import ast
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

RESULTS: list = []


def check(name: str, ok, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:74s} {detail}")
    return bool(ok)


def test_importregeln():
    """Abschnitt 1: statik3d_contracts importiert nur Standardbibliothek und numpy."""
    import statik3d_contracts as V
    ordner = os.path.dirname(os.path.abspath(V.__file__))
    erlaubt_fremd = {"numpy"}
    stdlib = set(sys.stdlib_module_names)
    verstoesse = []
    for name in sorted(os.listdir(ordner)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(ordner, name), encoding="utf-8") as f:
            baum = ast.parse(f.read(), filename=name)
        for kn in ast.walk(baum):
            module = []
            if isinstance(kn, ast.Import):
                module = [a.name for a in kn.names]
            elif isinstance(kn, ast.ImportFrom):
                if kn.level and kn.level > 0:
                    continue                     # eigenes Paket
                module = [kn.module or ""]
            for m in module:
                wurzel = m.split(".")[0]
                if wurzel and wurzel not in stdlib and wurzel not in erlaubt_fremd \
                        and wurzel != "statik3d_contracts":
                    verstoesse.append(f"{name}: {m}")
    check("Vertragspaket importiert nur Standardbibliothek und numpy", not verstoesse, "; ".join(verstoesse))
    check("Vertragsversion 2.0.0 (Abschnitt 9)", V.CONTRACT_VERSION == "2.0.0", V.CONTRACT_VERSION)
    check("Versionspruefung: gleiche Major passt, andere nicht",
          V.vertragsversion_passt("2.3.1") and not V.vertragsversion_passt("1.1.0") and not V.vertragsversion_passt(""),
          "")


def test_protokolle():
    """Abschnitt 9, Pflichttest 1: isinstance gegen die Protokolle - mit Gegenprobe."""
    from statik3d_contracts.coupling import GlobalFieldProvider
    from statik3d_contracts.discretization import Discretization
    from statik3d_contracts.solver import AssemblySolver, SolidDetailSolver
    from statik3d_contracts import testing as T
    check("StubSolidSolver erfuellt SolidDetailSolver", isinstance(T.StubSolidSolver(), SolidDetailSolver))
    check("StubGlobalFieldProvider erfuellt GlobalFieldProvider", isinstance(T.StubGlobalFieldProvider(), GlobalFieldProvider))
    check("StubAssemblySolver erfuellt AssemblySolver", isinstance(T.StubAssemblySolver(), AssemblySolver))
    check("StubDiscretization erfuellt Discretization",
          isinstance(T.StubDiscretization("d", 100.0, 3), Discretization))

    class Halb:                    # Gegenprobe: ohne solve ist es kein Loeser
        name = "halb"
        contract_version = "2.0.0"

        def estimate(self, spec):
            return {}

        def prepare(self, spec, material, progress=None):
            return None
    check("  Gegenprobe: eine Klasse ohne solve() erfuellt SolidDetailSolver nicht",
          not isinstance(Halb(), SolidDetailSolver))


def test_stub_solid():
    """Abschnitt 8: der Stub-Loeser liefert ein DetailResult in den vereinbarten Formen."""
    from statik3d_contracts.detail import DetailModelSpec, DetailResult, FcmSettings, GeometrySource, GeometrySourceType
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.solver import SolverCancelled
    from statik3d_contracts import testing as T
    spec = DetailModelSpec(id="D1", name="Wuerfel", geometry=GeometrySource(GeometrySourceType.CSG),
                           material_id="S355", cut_planes=(CutPlane(np.zeros(3), np.array([1.0, 0, 0])),),
                           settings=FcmSettings(base_cell_size_mm=25.0, p=2))
    mat = Material("S355", "S355", E=210_000.0, nu=0.3, fy=355.0)
    s = T.StubSolidSolver()
    est = s.estimate(spec)
    check("estimate nennt dofs, memory_mb, backend", all(k in est for k in ("dofs", "memory_mb", "backend")), str(est))
    meldungen = []
    disc = s.prepare(spec, mat, progress=lambda t, a: meldungen.append((t, a)))
    check("prepare meldet Fortschritt bis 1.0", meldungen and abs(meldungen[-1][1] - 1.0) < 1e-12, str(meldungen))
    geo = disc.preview_geometry()
    check("Vorschau: Ecken (8,3), Dreiecke (12,3), Zellen (8,6)",
          geo["vertices"].shape == (8, 3) and geo["triangles"].shape == (12, 3) and geo["cell_boxes"].shape == (8, 6),
          str({k: v.shape for k, v in geo.items()}))
    lo, hi = disc.bounding_box()
    check("bounding_box ist der Wuerfel 100 mm", np.allclose(hi - lo, 100.0), f"{lo} {hi}")
    prov = T.StubGlobalFieldProvider()
    keys = [ResultKey("LF1"), ResultKey("LF1", stellung_id="S2")]
    erg = s.solve(disc, prov, keys, progress=lambda t, a: None)
    n = len(geo["vertices"])
    check("solve: je Key ein DetailResult", len(erg) == 2 and all(isinstance(r, DetailResult) for r in erg))
    r = erg[0]
    check("Formen: Punkte (n,3), Dreiecke (m,3), u (n,3), Spannung (n,6), von Mises (n,)",
          r.surface_points.shape == (n, 3) and r.surface_triangles.shape == (12, 3) and r.displacement.shape == (n, 3)
          and r.stress.shape == (n, 6) and r.von_mises.shape == (n,), str(r.stress.shape))
    check("von Mises passt zur Spannung (100 N/mm2 einachsig)", np.allclose(r.von_mises, 100.0), str(r.von_mises[:3]))
    check("Protokoll nennt Loeser und Vertragsversion",
          r.protocol.get("solver") == "stub" and r.protocol.get("contract_version") == s.contract_version, str(r.protocol))
    try:
        s.solve(disc, prov, keys, cancel=lambda: True)
        abgebrochen = False
    except SolverCancelled:
        abgebrochen = True
    check("cancel() -> SolverCancelled", abgebrochen)


def test_stub_provider():
    """Abschnitt 5 und 8: Kragarm unter Endlast nach Balkentheorie, vektorisiert."""
    from statik3d_contracts.model import ResultKey
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts import testing as T
    L, b, h, E, F = 1000.0, 100.0, 200.0, 210_000.0, 10_000.0
    p = T.StubGlobalFieldProvider(L, b, h, E, F)
    I = b * h ** 3 / 12.0
    u, rot = p.displacement_at(np.array([[L, 0.0, 0.0], [L / 2, 0.0, 0.0], [-1.0, 0, 0], [L + 1, 0, 0]]), ResultKey("LF1"))
    w_L = -F * L ** 3 / (3 * E * I)
    check("Durchbiegung am freien Ende F L^3/(3 E I)", abs(u[0, 2] - w_L) < 1e-9 * abs(w_L), f"{u[0, 2]:.6f} mm gegen {w_L:.6f}")
    check("Neigung am freien Ende F L^2/(2 E I)", abs(-rot[0, 1] - (-F * L ** 2 / (2 * E * I))) < 1e-12, f"{rot[0, 1]:.3e}")
    check("Punkte ausserhalb 0..L sind NaN", np.isnan(u[2]).all() and np.isnan(u[3]).all())
    z = 50.0
    u2, _ = p.displacement_at(np.array([[L / 2, 0.0, z]]), ResultKey("LF1"))
    dw = -F * (L / 2) * (2 * L - L / 2) / (2 * E * I)
    check("Querschnittskinematik: u_x = -z w'(x)", abs(u2[0, 0] - (-z * dw)) < 1e-12, f"{u2[0, 0]:.6e}")
    P = np.random.default_rng(1).uniform([0, -50, -100], [L, 50, 100], size=(100_000, 3))
    t = time.perf_counter()
    p.displacement_at(P, ResultKey("LF1"))
    dt = time.perf_counter() - t
    check("10^5 Punkte unter 1 s (Zusage Abschnitt 5)", dt < 1.0, f"{dt * 1e3:.0f} ms")
    sf = p.section_forces(CutPlane(np.array([L / 2, 0, 0]), np.array([1.0, 0, 0])), ResultKey("LF1"))
    check("Schnittgroessen bei L/2: Querkraft F, Moment F L/2",
          abs(sf.force[2] + F) < 1e-9 and abs(sf.moment[1] - F * L / 2) < 1e-9, f"{sf.force} {sf.moment}")


def test_stub_assembly():
    """Abschnitt 6a/7a/8: zwei Zylinder, Lastpfad, Hertz, Live-Anzeige, Abbruch."""
    from statik3d_contracts.detail import FcmSettings, GeometrySource, GeometrySourceType
    from statik3d_contracts.discretization import DiscretizationKind
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.nonlinear import (AssemblyModelSpec, AssemblyResult, Body, ContactPair, FeHexSettings,
                                              LinearElasticModel, LoadPath, LoadState, SurfaceSelector)
    from statik3d_contracts.solver import CAPABILITIES, SolverCancelled, SolverError
    from statik3d_contracts import testing as T
    geo = GeometrySource(GeometrySourceType.CSG)
    bolzen = Body("bolzen", "Bolzen", geo, LinearElasticModel("S355"), DiscretizationKind.FE_MESH, fe_settings=FeHexSettings())
    buchse = Body("buchse", "Buchse", geo, LinearElasticModel("S355"), DiscretizationKind.FCM_OCTREE,
                  fcm_settings=FcmSettings(base_cell_size_mm=5.0))
    paar = ContactPair("bolzen/buchse", SurfaceSelector("buchse", named_surface="bohrung"), SurfaceSelector("bolzen", named_surface="mantel"))
    spec = AssemblyModelSpec("A1", "Drehlager-Attrappe", (bolzen, buchse), contacts=(paar,))
    pfad = LoadPath("P1", (LoadState(ResultKey("EG")), LoadState(ResultKey("WD"), factor=1.0)))
    s = T.StubAssemblySolver()
    check("capabilities ist eine Teilmenge der vereinbarten Eintraege (Abschnitt 7a)",
          set(s.capabilities) <= set(CAPABILITIES), str(sorted(s.capabilities)))
    handle = s.prepare(spec, {"S355": Material("S355", "S355", 210_000.0, 0.3)})
    schritte = []
    erg = s.solve_path(handle, pfad, on_step=schritte.append, progress=lambda t, a: None)
    check("AssemblyResult mit 2 Zustaenden x 5 Schritten", isinstance(erg, AssemblyResult) and len(erg.steps) == 10, str(len(erg.steps)))
    check("on_step je Schritt gerufen", len(schritte) == len(erg.steps))
    p0, b = T.hertz_zylinder_ebene(s.F_JE_LAENGE, s.R_MM, s.E, s.NU)
    letzter = erg.steps[-1]
    check("Kontaktdruck am Ende = Hertz p0, Status haftend, Klaffung 0",
          abs(letzter.contacts[0].pressure.max() - p0) < 1e-9 * p0 and (letzter.contacts[0].status == 1).all()
          and np.allclose(letzter.contacts[0].gap, 0.0), f"{letzter.contacts[0].pressure.max():.1f} gegen {p0:.1f} N/mm2, b {b:.3f} mm")
    check("plastische Dehnung waechst monoton", all(erg.steps[i].bodies[0].plastic_strain_eq.max() <= erg.steps[i + 1].bodies[0].plastic_strain_eq.max() + 1e-15
                                                  for i in range(len(erg.steps) - 1)))
    check("max_plastic_strain und max_contact_pressure je Koerper/Paar",
          set(erg.max_plastic_strain) == {"bolzen", "buchse"} and set(erg.max_contact_pressure) == {"bolzen/buchse"})
    try:
        s.solve_path(handle, pfad, cancel=lambda: True)
        abgebrochen = False
    except SolverCancelled:
        abgebrochen = True
    check("cancel() -> SolverCancelled", abgebrochen)
    falsch = Body("x", "x", geo, LinearElasticModel("S355"), DiscretizationKind.FE_MESH)   # fe_settings fehlt
    try:
        s.prepare(AssemblyModelSpec("A2", "falsch", (falsch,)), {})
        fehler = False
    except SolverError:
        fehler = True
    check("Regel 6a: FE_MESH ohne fe_settings -> SolverError in prepare", fehler)


def test_registrierung():
    """Abschnitt 7 und 10.5: Entry Points finden den Stub; Versionspruefung."""
    from statik3d import volumenloeser as VL
    from statik3d_contracts.solver import ENTRY_POINT_ASSEMBLY, ENTRY_POINT_SOLID, SolidDetailSolver
    from statik3d_contracts import testing as T
    eps = VL.entry_points_der_gruppe(ENTRY_POINT_SOLID)
    check("Entry Point 'stub' der Gruppe statik3d.solid_solvers registriert (pip install -e packages/statik3d_contracts)",
          eps.get("stub") is T.StubSolidSolver, str({k: getattr(v, '__name__', v) for k, v in eps.items()}))
    eps2 = VL.entry_points_der_gruppe(ENTRY_POINT_ASSEMBLY)
    check("Entry Point 'stub' der Gruppe statik3d.assembly_solvers registriert",
          eps2.get("stub") is T.StubAssemblySolver, str(list(eps2)))
    l = VL.volumenloeser()
    check("volumenloeser() liefert einen SolidDetailSolver (ohne echten Loeser den Stub)",
          isinstance(l, SolidDetailSolver) and l.name == "stub", getattr(l, "name", "?"))
    check("uebersicht() nennt Name, Gruppe, Version, Zustand",
          any(e["name"] == "stub" and e["zustand"] == "bereit" for e in VL.uebersicht()), str(VL.uebersicht()[:2]))

    class Fremd(T.StubSolidSolver):
        contract_version = "1.1.0"
    try:
        VL.vertrag_pruefen(Fremd, SolidDetailSolver)
        abgewiesen = False
    except VL.Vertragsfehler:
        abgewiesen = True
    check("Versionspruefung beim Start: Major 1 gegen 2 wird abgewiesen", abgewiesen)
    try:
        VL.volumenloeser("gibt_es_nicht")
        fehlt = False
    except VL.Vertragsfehler:
        fehlt = True
    check("unbekannter Loesername -> Vertragsfehler mit Liste", fehlt)


def test_fe_netz_diskretisierung():
    """Abschnitt 4 und 10.2: das FE-Netz des Hauptprogramms hinter Discretization."""
    from statik3d_contracts.discretization import Discretization, DiscretizationKind
    from statik3d.model import Model, Material
    from statik3d import mesher
    from statik3d.diskretisierung import aus_modell
    m = Model()
    m.add_material(Material.steel("S235"))
    mesher.grid_box(m, "S235", 1.0, 0.5, 0.25, 2, 1, 1)           # 2 hex8, 1 x 0,5 x 0,25 m
    d = aus_modell(m, "global")
    check("FeNetzDiskretisierung erfuellt Discretization, kind FE_MESH",
          isinstance(d, Discretization) and d.kind == DiscretizationKind.FE_MESH)
    check("dof_count = model.ndof", d.dof_count() == m.ndof, f"{d.dof_count()} / {m.ndof}")
    lo, hi = d.bounding_box()
    check("bounding_box in mm (1000 x 500 x 250)", np.allclose(hi - lo, [1000.0, 500.0, 250.0]), f"{hi - lo}")
    s = d.summary()
    check("summary: nodes 12, elements 2, hex8 2, length_unit mm",
          s.get("nodes") == 12 and s.get("elements") == 2 and s.get("hex8") == 2 and s.get("length_unit") == "mm", str(s))
    geo = d.preview_geometry()
    check("preview: 12 Ecken in mm, 20 Dreiecke der freien Seiten (10 Vierecke), keine innere Seite",
          geo["vertices"].shape == (12, 3) and geo["triangles"].shape == (20, 3) and abs(geo["vertices"][:, 0].max() - 1000.0) < 1e-9,
          str({k: v.shape for k, v in geo.items()}))
    m2 = Model()
    m2.add_material(Material.steel("S235"))
    mesher.grid_box(m2, "S235", 1.0, 1.0, 1.0, 2, 2, 2, typ="tet4")
    g2 = aus_modell(m2).preview_geometry()
    dreiecke = g2["triangles"]
    X = g2["vertices"]
    auf_huelle = np.all(np.any(np.isclose(X[dreiecke], 0.0) | np.isclose(X[dreiecke], 1000.0), axis=2), axis=1)
    check("tet4-Wuerfel: alle Vorschau-Dreiecke liegen auf der Huelle", bool(auf_huelle.all()) and len(dreiecke) > 0,
          f"{len(dreiecke)} Dreiecke")


def main() -> int:
    for t in (test_importregeln, test_protokolle, test_stub_solid, test_stub_provider, test_stub_assembly,
              test_registrierung, test_fe_netz_diskretisierung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:             # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
