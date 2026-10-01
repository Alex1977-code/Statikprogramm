"""STEP-Eingang ueber gmsh-Tessellierung (Vorgabe 3, Plan TP 5 B5, Theorie 11.15).

Aufruf: python -m volumen3d.tests.test_step   (~20 s; die gmsh-Pruefungen werden ohne gmsh uebersprungen; der Block mit Bohrung
durch den Vertragsweg nur mit VOLUMEN3D_LANG=1, ~40 s)
Modelle: (1) Block 210 x 200 x 200 mm (x -5 bis 205) mit Bohrung r 40 laengs z durch (100, 100) fuer die Tessellierung und - seit der
Huellenintegration ueber den Divergenzsatz (Plan TP 5 B6, Theorie 11.16) - fuer den Vertragsweg gegen CSG (K_t); (2) Quader
210 x 100 x 100 mm fuer den Vertragsweg gegen CSG mit ebenen Flaechen. Die STEP-Dateien entstehen im Test mit gmsh (OpenCASCADE) selbst.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

R, L_X, L_Y, L_Z = 40.0, 210.0, 200.0, 200.0
V_SOLL = L_X * L_Y * L_Z - np.pi * R ** 2 * L_Z                       # 7 394 690,4 mm3


def _gmsh_da() -> bool:
    from volumen3d.geometry.step import gmsh_verfuegbar
    return gmsh_verfuegbar()


def block_step(pfad: str) -> None:
    import gmsh
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("quelle")
        b = gmsh.model.occ.addBox(-5.0, 0.0, 0.0, L_X, L_Y, L_Z)
        z = gmsh.model.occ.addCylinder(100.0, 100.0, -1.0, 0.0, 0.0, L_Z + 2.0, R)
        gmsh.model.occ.cut([(3, b)], [(3, z)])
        gmsh.model.occ.synchronize()
        gmsh.write(pfad)
    finally:
        gmsh.finalize()


def _volumen(D):
    """Eingeschlossenes Volumen aus den Dreiecken (Divergenzsatz), unabhaengig von Stl."""
    return float(np.einsum("ij,ij->i", D[:, 0], np.cross(D[:, 1], D[:, 2])).sum() / 6.0)


def test_tessellierung():
    """Die Tessellierung des STEP-Blocks: (1) Volumen gegen die geschlossene Form (Bohrung als einbeschriebenes Polygon,
    Fehler <= Bohrungsvolumen * (2 pi / N)^2 / 6 bezogen auf das Gesamtvolumen: N 60 und 120), (2) wasserdicht - jede Kante
    gehoert zu genau zwei Dreiecken, (3) Dreiecke der Stirnflaeche x = -5 zeigen nach aussen, (4) Huellquader -5..205 x 0..200
    x 0..200 mm, ein Koerper, (5) die Einheit wird umgerechnet: dieselbe Datei mit auf Meter umdeklariertem Kopf ergibt
    das Tausendfache."""
    if not _gmsh_da():
        check("STEP-Tessellierung uebersprungen: gmsh nicht installiert (pip install \"gmsh>=4.11\")", True)
        return
    from volumen3d.geometry.step import tesselliere
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "block.step")
        block_step(pfad)
        for n in (60, 120):
            t = time.perf_counter()
            D, info = tesselliere(pfad, 25.0, n)
            v = _volumen(D)
            fehler = (v - V_SOLL) / V_SOLL
            grenze = np.pi * R ** 2 * L_Z * (2 * np.pi / n) ** 2 / 6.0 / V_SOLL
            ecken = np.round(D.reshape(-1, 3), 6)
            _, inv = np.unique(ecken, axis=0, return_inverse=True)
            tri = inv.reshape(-1, 3)
            kanten = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
            _, zahl = np.unique(kanten, axis=0, return_counts=True)
            nrm = np.cross(D[:, 1] - D[:, 0], D[:, 2] - D[:, 0])
            stirn = np.abs(D[:, :, 0] + 5.0).max(axis=1) < 1e-6
            check(f"STEP-Block N {n}: Volumen {100 * fehler:+.4f} % (Grenze +{100 * grenze:.4f} %, einbeschriebenes Polygon), wasserdicht "
                  f"(alle Kanten doppelt), Stirnflaeche nach aussen ({int(stirn.sum())} Dreiecke), {len(D)} Dreiecke",
                  0.0 <= fehler <= 1.1 * grenze and bool((zahl == 2).all()) and bool((nrm[stirn][:, 0] < 0).all()) and info["koerper"] == 1,
                  f"{time.perf_counter() - t:.1f} s")
        lo, hi = np.asarray(info["huellquader_min"]), np.asarray(info["huellquader_max"])
        check("Huellquader -5..205 x 0..200 x 0..200 mm auf 1e-9, Einheit mm im Protokoll",
              np.allclose(lo, [-5, 0, 0], atol=1e-9) and np.allclose(hi, [205, 200, 200], atol=1e-9) and info["einheit"].startswith("mm"), str(info))
        text = open(pfad, encoding="latin-1").read()
        assert "SI_UNIT(.MILLI.,.METRE.)" in text
        pfad_m = os.path.join(tmp, "block_m.step")
        with open(pfad_m, "w", encoding="latin-1") as f:
            f.write(text.replace("SI_UNIT(.MILLI.,.METRE.)", "SI_UNIT($,.METRE.)"))
        Dm, _ = tesselliere(pfad_m, 25000.0, 60)
        ausdehnung = Dm.reshape(-1, 3).max(axis=0) - Dm.reshape(-1, 3).min(axis=0)
        check("Kopf auf Meter umdeklariert: Ausdehnung 1000-mal (210 x 200 x 200 m in mm), die Einheit wird also umgerechnet",
              np.allclose(ausdehnung, [L_X * 1e3, L_Y * 1e3, L_Z * 1e3], rtol=1e-9), str(np.round(ausdehnung, 3).tolist()))


def quader_step(pfad: str) -> None:
    import gmsh
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("quader")
        gmsh.model.occ.addBox(-5.0, 0.0, 0.0, 210.0, 100.0, 100.0)
        gmsh.model.occ.synchronize()
        gmsh.write(pfad)
    finally:
        gmsh.finalize()


def _spec(art, pfad, h=25.0, p=2):
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType
    if art == "step":
        geo = GeometrySource(GeometrySourceType.STEP, path=pfad, params={"tessellation_mm": 25.0, "elements_per_circle": 120})
    else:
        geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "quader", "min": [-5, 0, 0], "max": [205, 100, 100], "name": "quader"}})
    return DetailModelSpec(id="Q", name="Quader", geometry=geo, material_id="S355",
                           cut_planes=(CutPlane(np.array([0.0, 50.0, 50.0]), np.array([-1.0, 0, 0])),
                                       CutPlane(np.array([200.0, 50.0, 50.0]), np.array([1.0, 0, 0]))),
                           settings=FcmSettings(base_cell_size_mm=h, p=p))


class ZugGeber:
    """Gleichmaessiger Zug sigma_n in x am Quader (Querschnitt 100 x 100 an den Schnittebenen)."""

    def __init__(self, sigma=100.0, E=210000.0, nu=0.3, flaeche=100.0 * 100.0):
        self.s, self.E, self.nu, self.A = sigma, E, nu, flaeche

    def available_keys(self):
        from statik3d_contracts.model import ResultKey
        return [ResultKey("LF1")]

    def displacement_at(self, points, key):
        P = np.asarray(points, float).reshape(-1, 3)
        e = self.s / self.E
        u = np.column_stack([e * P[:, 0], -self.nu * e * (P[:, 1] - 50.0), -self.nu * e * (P[:, 2] - 50.0)])
        return u, np.zeros_like(u)

    def section_forces(self, plane, key):
        from statik3d_contracts.coupling import SectionForces
        v = 1.0 if float(np.asarray(plane.normal, float)[0]) >= 0.0 else -1.0
        return SectionForces(force=v * np.array([self.s * self.A, 0.0, 0.0]), moment=np.zeros(3))


def test_vertragsweg_gegen_csg():
    """Quader unter Zug sigma_n = 100 N/mm2 (Schnittebenen x 0 und 200, Zug-Geber) ueber den Vertragsweg, einmal als STEP-Datei, einmal als
    CSG, gleiche Einstellungen (h 25, p 2). Ebene Flaechen sind im STL-Weg exakt: das Werkstoffvolumen der Zellquadratur stimmt auf
    1e-10, die Spannung sigma_xx an allen Oberflaechenpunkten ist in beiden Laeufen 100 N/mm2 (< 1e-6), die Verschiebungen sind gleich
    (< 1e-9 relativ), die Kopplungskontrolle (Kraft) bleibt unter 1e-6, das Protokoll nennt die Tessellierung."""
    if not _gmsh_da():
        check("STEP gegen CSG uebersprungen: gmsh nicht installiert (pip install \"gmsh>=4.11\")", True)
        return
    from statik3d_contracts.model import Material, ResultKey
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3, fy=355.0)
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "quader.step")
        quader_step(pfad)
        erg, vol = {}, {}
        for art in ("csg", "step"):
            t = time.perf_counter()
            disc = s.prepare(_spec(art, pfad), mat)
            vol[art] = float(disc.problem.quadratur.volumen())
            erg[art] = (s.solve(disc, ZugGeber(), [ResultKey("LF1")])[0], time.perf_counter() - t)
    soll = 200.0 * 100.0 * 100.0                       # die Schnittebenen x 0 und 200 stutzen den Quader (x -5 bis 205) auf 200 mm
    dv = abs(vol["step"] - vol["csg"]) / vol["csg"]
    e_step, e_csg = erg["step"][0], erg["csg"][0]
    ds = max(float(np.abs(e_step.stress[:, 0] - 100.0).max()), float(np.abs(e_csg.stress[:, 0] - 100.0).max()))
    # Verschiebungen an den Oberflaechenpunkten gegen das analytische Zugfeld, unabhaengig von der Triangulierung
    def feld(e):
        P = e.surface_points
        return np.column_stack([100.0 / 210000.0 * P[:, 0], -0.3 * 100.0 / 210000.0 * (P[:, 1] - 50.0), -0.3 * 100.0 / 210000.0 * (P[:, 2] - 50.0)])
    du = max(float(np.abs(e.displacement - feld(e)).max() / np.abs(feld(e)).max()) for e in (e_step, e_csg))
    dF = max(eb["deviation_force"] for e in (e_step, e_csg) for eb in e.coupling_check["planes"])
    info = e_step.protocol["step_tessellation"]
    check(f"Quader STEP gegen CSG (h 25, p 2): Volumen {vol['step']:.4f} = {vol['csg']:.4f} = {soll:.0f} (relativ {dv:.1e} < 1e-10), "
          f"sigma_xx an allen Oberflaechenpunkten 100 auf {ds:.1e} (< 1e-6), Verschiebung gegen das Zugfeld {du:.1e} (< 1e-6), "
          f"Kopplung Kraft {dF:.1e} (< 1e-6)",
          dv < 1e-10 and abs(vol["step"] / soll - 1) < 1e-10 and ds < 1e-6 and du < 1e-6 and dF < 1e-6,
          f"{erg['csg'][1]:.0f} s CSG, {erg['step'][1]:.0f} s STEP")
    check("Protokoll step_tessellation: Quelle, Dreiecke, Facettengroesse, Dreiecke je Vollkreis, gmsh-Version, Huellquader; CSG-Lauf ohne Eintrag; "
          "keine Integrationswarnung bei ebenen Flaechen",
          info is not None and {"quelle", "dreiecke", "facettengroesse_mm", "dreiecke_je_vollkreis", "gmsh", "koerper", "huellquader_min"} <= set(info)
          and info["dreiecke_je_vollkreis"] == 120 and e_csg.protocol["step_tessellation"] is None
          and not any("Punkttest" in w for w in e_step.warnings), str(info))


class _ZugGeberBlock(ZugGeber):
    """Zug sigma_n = 100 N/mm2 am Block 200 x 200 (Querschnitt an den Schnittebenen x 0 und 200, Querdehnung um (100, 100))."""

    def __init__(self):
        super().__init__(sigma=100.0, flaeche=200.0 * 200.0)

    def displacement_at(self, points, key):
        P = np.asarray(points, float).reshape(-1, 3)
        e = self.s / self.E
        u = np.column_stack([e * P[:, 0], -self.nu * e * (P[:, 1] - 100.0), -self.nu * e * (P[:, 2] - 100.0)])
        return u, np.zeros_like(u)


def _spec_block(art, pfad, h=25.0, p=2):
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType
    if art == "step":
        geo = GeometrySource(GeometrySourceType.STEP, path=pfad, params={"tessellation_mm": 25.0, "elements_per_circle": 120})
    else:
        geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "differenz", "teile": [
            {"typ": "quader", "min": [-5, 0, 0], "max": [205, 200, 200], "name": "block"},
            {"typ": "zylinder", "p0": [100, 100, -1], "p1": [100, 100, 201], "radius": R, "name": "bohrung"}]}})
    return DetailModelSpec(id="B", name="Block", geometry=geo, material_id="S355",
                           cut_planes=(CutPlane(np.array([0.0, 100.0, 100.0]), np.array([-1.0, 0, 0])),
                                       CutPlane(np.array([200.0, 100.0, 100.0]), np.array([1.0, 0, 0]))),
                           settings=FcmSettings(base_cell_size_mm=h, p=p))


def test_block_mit_bohrung_gegen_csg():
    """Die offene Planpruefung aus B5 (Plan TP 5, Pruefung (3) zu B6): der Block mit Bohrung unter Zug durch den Vertragsweg, einmal als
    STEP (N 120, 27 788 Dreiecke), einmal als CSG mit dem exakten Zylinder, gleiche Einstellungen (h 25, p 2). Gemessen am 01.10.2026:
    K_t = max sigma_xx am Bohrungsrand / sigma_n 2,7158 (STEP) gegen 2,7190 (CSG), 0,12 % (p 3: 2,7503 gegen 2,7573, 0,25 %); Schranke
    0,5 %. Dazu: kein Punkttest-Blatt im STEP-Lauf (vor B6 Minuten bis Stunden mit gemischter Lage), Werkstoffvolumen gleich dem
    Volumen der Tessellierung zwischen den Schnittebenen (7 395 035,38 - 2 * 5 * 200 * 200) auf 1e-10, prepare unter 40 s.
    Laeuft nur mit VOLUMEN3D_LANG=1 (~40 s)."""
    if os.environ.get("VOLUMEN3D_LANG") != "1":
        check("Block mit Bohrung STEP gegen CSG uebersprungen (VOLUMEN3D_LANG=1 setzen; gemessen K_t 0,12 % bei p 2, 0,25 % bei p 3)", True)
        return
    if not _gmsh_da():
        check("Block mit Bohrung STEP gegen CSG uebersprungen: gmsh nicht installiert (pip install \"gmsh>=4.11\")", True)
        return
    from statik3d_contracts.model import Material, ResultKey
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3, fy=355.0)
    kt, vol, st, dauer = {}, {}, {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "block.step")
        block_step(pfad)
        v_tess = _volumen(__import__("volumen3d.geometry.step", fromlist=["tesselliere"]).tesselliere(pfad, 25.0, 120)[0])
        for art in ("csg", "step"):
            t = time.perf_counter()
            disc = s.prepare(_spec_block(art, pfad), mat)
            dauer[art] = time.perf_counter() - t
            e = s.solve(disc, _ZugGeberBlock(), [ResultKey("LF1")])[0]
            P = e.surface_points
            am_rand = np.hypot(P[:, 0] - 100.0, P[:, 1] - 100.0) < R + 0.5
            kt[art] = float(e.stress[am_rand, 0].max()) / 100.0
            vol[art] = float(disc.problem.quadratur.volumen())
            st[art] = dict(disc.problem.quadratur.statistik)
    dk = abs(kt["step"] / kt["csg"] - 1)
    v_soll = v_tess - 2 * 5.0 * L_Y * L_Z
    check(f"Block mit Bohrung (h 25, p 2): K_t STEP {kt['step']:.4f} gegen CSG {kt['csg']:.4f}, Abweichung {dk * 100:.2f} % (< 0,5 %)",
          dk < 5e-3, f"prepare {dauer['csg']:.0f} s CSG, {dauer['step']:.0f} s STEP")
    check(f"STEP-Lauf: kein Punkttest-Blatt, {st['step'].get('huellenzellen')} Huellenzellen, Volumen = Tessellierung zwischen den Schnittebenen "
          f"(relativ {abs(vol['step'] / v_soll - 1):.1e} < 1e-10), prepare {dauer['step']:.0f} s (< 40 s)",
          st["step"]["blaetter_punkttest"] == 0 and st["step"].get("huellenzellen", 0) > 0 and abs(vol["step"] / v_soll - 1) < 1e-10
          and dauer["step"] < 40.0, f"{vol['step']:.3f} gegen {v_soll:.3f}")


def _boxen_step(pfad, boxen):
    import gmsh
    gmsh.initialize([], readConfigFiles=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("boxen")
        for b in boxen:
            gmsh.model.occ.addBox(*b)
        gmsh.model.occ.synchronize()
        gmsh.write(pfad)
    finally:
        gmsh.finalize()


def test_mehrere_koerper():
    """Befund G3-1 (Gutachten C2, 02.10.2026): eine STEP-Datei mit zwei sich durchdringenden Koerpern lief ohne Meldung durch und rechnete
    'A minus B' - die Huelle hatte doppelte Waende, B galt als Hohlraum (Verschachtelung an einer Facette in A bestimmt), Volumen 805 400 statt
    1 288 000 mm3. Mehrere Koerper werden jetzt vor dem Tessellieren vereinigt (OpenCASCADE fuse). Pruefung: A = [0,100]^3, B = [60,160] x
    [10,90] x [20,80] in beiden Reihenfolgen -> Volumen der Tessellierung (Divergenzsatz, unabhaengig von Stl) = Vereinigung 1 288 000 auf 1e-9,
    Punkte nur in B und in A ∩ B innen; beruehrende Koerper (gemeinsame Flaeche x = 100) -> 2 000 000."""
    if not _gmsh_da():
        check("mehrere Koerper uebersprungen: gmsh nicht installiert", True)
        return
    from volumen3d.geometry.step import tesselliere
    from volumen3d.geometry.stl import Stl
    soll = 1e6 + 100 * 80 * 60 - 40 * 80 * 60
    proben = np.array([[20.0, 50, 50], [80.0, 50, 50], [140.0, 50, 50], [140.0, 5, 50]])
    with tempfile.TemporaryDirectory() as tmp:
        erg = []
        for name, boxen in (("A_B", [(0, 0, 0, 100, 100, 100), (60, 10, 20, 100, 80, 60)]), ("B_A", [(60, 10, 20, 100, 80, 60), (0, 0, 0, 100, 100, 100)])):
            pfad = os.path.join(tmp, name + ".step")
            _boxen_step(pfad, boxen)
            D, info = tesselliere(pfad, 50.0, 60)
            s = Stl.aus_dreiecken(D, name)
            erg.append((_volumen(D), s.innen(proben).tolist(), info))
        pfad = os.path.join(tmp, "beruehrend.step")
        _boxen_step(pfad, [(0, 0, 0, 100, 100, 100), (100, 0, 0, 100, 100, 100)])
        Db, info_b = tesselliere(pfad, 50.0, 60)
    check(f"zwei sich durchdringende Koerper: Volumen {erg[0][0]:.1f} / {erg[1][0]:.1f} = Vereinigung {soll:.0f} (1e-9), nur-B und A∩B innen, aussen aussen",
          all(abs(v / soll - 1) < 1e-9 and inn == [True, True, True, False] for v, inn, _ in erg), f"{[(round(v, 1), inn) for v, inn, _ in erg]}")
    check(f"beruehrende Koerper: Volumen {_volumen(Db):.1f} = 2 000 000 (1e-9); Protokoll nennt zwei Koerper und die Vereinigung",
          abs(_volumen(Db) / 2e6 - 1) < 1e-9 and info_b["koerper"] == 2 and erg[0][2].get("vereinigt") is True, str(info_b))


def test_cache_und_gmsh_zustand():
    """Befund G3-6 (Gutachten C2, 02.10.2026): (a) der Cache-Schluessel war Pfad, Aenderungszeit und Groesse - eine gleich grosse Datei mit
    zurueckgesetzter Zeit (Kopie mit Zeitstempeln) lieferte die alte Tessellierung; (b) lief gmsh beim Aufrufer schon, galten dessen
    Optionen (MeshSizeFactor 4: 1 884 statt 27 788 Dreiecke, ElementOrder 2: 'keine Dreiecke'), das Protokoll nannte die eigenen.
    Jetzt Inhaltshash und eigene Netzoptionen auch bei laufendem gmsh (danach zurueckgesetzt)."""
    if not _gmsh_da():
        check("Cache und gmsh-Zustand uebersprungen: gmsh nicht installiert", True)
        return
    import gmsh
    from volumen3d.geometry import step as S
    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "q.step")
        quader_step(pfad)
        S._CACHE.clear()
        D0, _ = S.tesselliere(pfad, 25.0, 60)
        st = os.stat(pfad)
        roh = open(pfad, "rb").read()
        assert b"MILLI" in roh
        with open(pfad, "wb") as f:
            f.write(roh.replace(b"MILLI", b"CENTI"))           # gleiche Laenge, Einheit cm: zehnfache Ausdehnung
        os.utime(pfad, ns=(st.st_atime_ns, st.st_mtime_ns))
        D1, _ = S.tesselliere(pfad, 25.0, 60)
        ausdehnung = (float(np.ptp(D0[:, :, 0])), float(np.ptp(D1[:, :, 0])))
        with open(pfad, "wb") as f:
            f.write(roh)
        S._CACHE.clear()
        gmsh.initialize([], readConfigFiles=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.option.setNumber("Mesh.MeshSizeFactor", 4.0)
            gmsh.option.setNumber("Mesh.ElementOrder", 2)
            D2, _ = S.tesselliere(pfad, 25.0, 60)
            danach = (gmsh.option.getNumber("Mesh.MeshSizeFactor"), gmsh.option.getNumber("Mesh.ElementOrder"))
        finally:
            gmsh.finalize()
    check(f"gleich grosse Datei mit zurueckgesetzter Zeit (Einheit MILLI -> CENTI): neue Tessellierung (Ausdehnung x {ausdehnung[0]:g} -> {ausdehnung[1]:g}); "
          f"laufendes gmsh mit MeshSizeFactor 4 und ElementOrder 2: gleiche Dreiecke wie frei ({len(D2)} = {len(D0)}), Optionen danach zurueck {danach}",
          abs(ausdehnung[1] / ausdehnung[0] - 10.0) < 1e-9 and len(D2) == len(D0) and danach == (4.0, 2.0))


def test_integrationswarnung():
    """Die Warnung der Integrationsordnung: stille Zaehler -> keine Meldung, Blaetter im Punkttest oder Flaechenstuecke im Rueckfall -> Meldung mit
    beiden Zahlen und dem Hinweis auf STL/STEP (reine Funktion, Plan TP 5 B5)."""
    from volumen3d.api import _integrationswarnung
    stumm = _integrationswarnung({"blaetter_punkttest": 0}, {"rueckfall": 0})
    laut = _integrationswarnung({"blaetter_punkttest": 12}, {"rueckfall": 345})
    nur_flaeche = _integrationswarnung({"blaetter_punkttest": 0}, {"rueckfall": 3})
    check("Integrationswarnung: ohne Rueckfaelle None, sonst mit 12 und 345 bzw. 0 und 3 sowie STL/STEP im Text",
          stumm is None and laut is not None and "12 Blaetter" in laut and "345 Flaechenstuecke" in laut and "STEP" in laut
          and nur_flaeche is not None and "0 Blaetter" in nur_flaeche and "3 Flaechenstuecke" in nur_flaeche, str(laut)[:120])


def test_fehler():
    """Klare Fehler statt stiller Ersatz: ohne gmsh der Hinweis auf 'pip install gmsh' (simuliert), fehlende Datei, kein Pfad,
    eine Datei, die kein STEP ist, ein STEP ohne Volumenkoerper (nur eine Flaeche), ungueltige Tessellierungsangaben."""
    from statik3d_contracts.solver import SolverError
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    meldungen: dict[str, str] = {}

    def fange(name, spec):
        try:
            s.estimate(spec)
            meldungen[name] = "KEIN FEHLER"
        except SolverError as ex:
            meldungen[name] = str(ex)
    with tempfile.TemporaryDirectory() as tmp:
        text = os.path.join(tmp, "kein_step.stp")
        open(text, "w").write("das ist kein STEP\n")
        fange("fehlt", _spec("step", os.path.join(tmp, "gibt_es_nicht.step")))
        fange("kein_pfad", _spec("step", None))
        saved = sys.modules.get("gmsh", "fehlt")
        sys.modules["gmsh"] = None                                       # import gmsh wirft ImportError
        try:
            from volumen3d.geometry import step as step_modul
            step_modul._CACHE.clear()
            fange("ohne_gmsh", _spec("step", text))
        finally:
            if saved == "fehlt":
                del sys.modules["gmsh"]
            else:
                sys.modules["gmsh"] = saved
        if _gmsh_da():
            import gmsh
            fange("kein_step", _spec("step", text))
            flaeche = os.path.join(tmp, "flaeche.step")
            gmsh.initialize([], readConfigFiles=False)
            try:
                gmsh.option.setNumber("General.Terminal", 0)
                gmsh.model.add("f")
                gmsh.model.occ.addRectangle(0, 0, 0, 10, 10)
                gmsh.model.occ.synchronize()
                gmsh.write(flaeche)
            finally:
                gmsh.finalize()
            fange("nur_flaeche", _spec("step", flaeche))
            import dataclasses
            from statik3d_contracts.detail import GeometrySource, GeometrySourceType
            sp = _spec("step", flaeche)
            fange("klein", dataclasses.replace(sp, geometry=GeometrySource(GeometrySourceType.STEP, path=flaeche, params={"elements_per_circle": 3})))
    ok = ("nicht gefunden" in meldungen["fehlt"] and "braucht einen Pfad" in meldungen["kein_pfad"]
          and "pip install" in meldungen["ohne_gmsh"] and "gmsh" in meldungen["ohne_gmsh"])
    if _gmsh_da():
        ok = ok and "nicht lesbar" in meldungen["kein_step"] and "Volumenkoerper" in meldungen["nur_flaeche"] and "mindestens 8" in meldungen["klein"]
    check("Fehlerfaelle: fehlende Datei, kein Pfad, ohne gmsh mit Installationshinweis" + (", keine STEP-Datei, nur eine Flaeche, zu grobe Tessellierung"
                                                                                       if _gmsh_da() else " (gmsh-Faelle uebersprungen)"),
          ok, str({k: v[:90] for k, v in meldungen.items()}))


if __name__ == "__main__":
    sys.exit(lauf([test_tessellierung, test_vertragsweg_gegen_csg, test_block_mit_bohrung_gegen_csg, test_mehrere_koerper, test_cache_und_gmsh_zustand, test_integrationswarnung, test_fehler]))
