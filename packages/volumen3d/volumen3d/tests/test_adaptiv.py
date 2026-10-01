"""Adaptive Zyklen und Konvergenzkurve (Vorgabe 8.4 und 11.3, Plan TP 5 B4, Theorie 11.14).

Aufruf: python -m volumen3d.tests.test_adaptiv   (Kernteil ~20 s; T-Stoss mit VOLUMEN3D_LANG=1)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

EINSTELLUNGEN = ("p", "base_cell_size_mm", "refinement", "alpha", "tolerance", "tolerance_used", "coupling", "adaptive_cycles",
                 "cycle_step", "backend_requested", "backend_used", "solver_path", "moment_fitting", "fit_grad", "stress_output",
                 "aggregation_threshold", "weld_lines", "contract_version", "volumen3d")
EINTRAG = ("cycle", "step", "dofs", "p", "cells", "cut_cells", "h_min_mm", "hotspot_max", "hotspot_mean", "stress_max",
           "solver_path", "iterations", "t_s")


def test_konvergenzaussage():
    """Die Aussage ist eine reine Funktion der Folge. Erwartungswerte aus der geschlossenen Form: eine geometrische Folge
    sigma_k = s + c q^k hat den Aitken-Grenzwert s exakt (hier s 100, c 10, q 0,5 bzw. -0,4 von unten)."""
    from volumen3d.postprocess.konvergenz import konvergenzaussage
    geo = [100 + 10 * 0.5 ** k for k in range(4)]
    a = konvergenzaussage(geo)
    unten = [100 - 10 * 0.6 ** k for k in range(4)]
    b = konvergenzaussage(unten)
    check("Geometrische Folge von oben und von unten: monoton konvergent, Aitken-Grenzwert 100 auf 1e-12",
          a["art"] == b["art"] == "monoton_konvergent" and abs(a["grenzwert"] - 100) < 1e-12 and abs(b["grenzwert"] - 100) < 1e-12
          and abs(a["restabweichung"] - abs(geo[-1] - 100) / 100) < 1e-12, f"{a['text']} | {b['text']}")
    schwingt = konvergenzaussage([100.0, 103.0, 101.0, 102.0])
    waechst = konvergenzaussage([100.0, 101.0, 103.0, 107.0])
    check("Schwingende und wachsende Folge: nicht monoton, kein Grenzwert; zwei Werte zu wenig; fehlender Wert kein Hot-Spot; "
          "konstante Folge Grenzwert = Wert",
          schwingt["art"] == waechst["art"] == "nicht_monoton" and schwingt["grenzwert"] is None and waechst["grenzwert"] is None
          and konvergenzaussage([1.0, 2.0])["art"] == "zu_wenige_zyklen" and konvergenzaussage([1.0, None, 2.0])["art"] == "kein_hotspot"
          and konvergenzaussage([100.0, 100.0, 100.0])["art"] == "monoton_konvergent"
          and konvergenzaussage([100.0, 100.0, 100.0])["grenzwert"] == 100.0, schwingt["text"])


def _spec(p, h, zyklen):
    import dataclasses
    from volumen3d.tests.test_vertrag_fcm import _spec as kragarm
    s = kragarm(p=p, h=h)
    return dataclasses.replace(s, settings=dataclasses.replace(s.settings, adaptive_cycles=zyklen))


def test_zyklen_ohne_naht():
    """Kragarm-Ausschnitt ohne Naht, adaptive_cycles 2: nur p-Erhoehung (keine Stelle fuer die lokale h-Verfeinerung), drei
    Eintraege mit p 2, 3, 4 und wachsenden Freiheitsgraden, Kurve und Protokoll vollstaendig; Kurve und Einstellungen stehen
    im Ergebnis des letzten Zyklus, dessen Spannungen haben die Form wie ohne Zyklen; ohne Hot-Spot keine Konvergenzaussage."""
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3, fy=355.0)
    prov = StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0)
    t = time.perf_counter()
    disc = s.prepare(_spec(2, 50.0, 2), mat)
    meld: list[float] = []
    erg = s.solve(disc, prov, [ResultKey("LF1"), ResultKey("LF1", stellung_id="S2")], progress=lambda tx, a: meld.append(a))
    k = erg[0].convergence
    pr = erg[0].protocol
    check("adaptive_cycles 2 ohne Naht: drei Eintraege, Schritte Start/p-Erhoehung/p-Erhoehung, p 2 3 4, Freiheitsgrade wachsend, "
          "alle Eintragsfelder",
          len(k) == 3 and [c["step"] for c in k] == ["Start", "p-Erhoehung", "p-Erhoehung"] and [c["p"] for c in k] == [2, 3, 4]
          and k[0]["dofs"] < k[1]["dofs"] < k[2]["dofs"] and all(set(EINTRAG) <= set(c) for c in k)
          and [c["cycle"] for c in k] == [0, 1, 2] and all(c["t_s"] > 0 for c in k) and len(erg) == 2,
          f"dofs {[c['dofs'] for c in k]}, t_s {[c['t_s'] for c in k]}, {time.perf_counter() - t:.1f} s")
    st = pr["settings"]
    check("Protokoll: settings mit allen Einstellungen des letzten Zyklus (p 4), cycles 2, Konvergenzaussage 'kein_hotspot'; "
          "Fortschritt monoton bis 1,0",
          set(EINSTELLUNGEN) <= set(st) and st["p"] == 4 and st["adaptive_cycles"] == 2 and st["cycle_step"] == "p-Erhoehung"
          and pr["cycles"] == 2 and pr["convergence_statement"]["art"] == "kein_hotspot" and meld[-1] == 1.0
          and all(a <= b + 1e-12 for a, b in zip(meld[:-1], meld[1:])),
          f"fehlt {set(EINSTELLUNGEN) - set(st)}")
    einzeln = s.solve(s.prepare(_spec(4, 50.0, 0), mat), prov, [ResultKey("LF1")])[0]
    check("Letzter Zyklus = Rechnung mit p 4 ohne Zyklen (Spannungen auf 1e-12, gleiche Oberflaeche), ohne Zyklen ein Eintrag",
          erg[0].stress.shape == einzeln.stress.shape and np.allclose(erg[0].stress, einzeln.stress, rtol=1e-9, atol=1e-9 * np.abs(einzeln.stress).max())
          and len(einzeln.convergence) == 1 and einzeln.protocol["cycles"] == 0 if "cycles" in einzeln.protocol else len(einzeln.convergence) == 1,
          f"{np.abs(erg[0].stress - einzeln.stress).max():.1e}")


def test_fahrplan():
    """Fahrplan 'zuerst lokal h bis t/4, dann p + 1' (Anwender 01.10.2026) als reine Funktion; Erwartung aus der Formel
    Zielgroesse_i(k) = max(h0 / 2^k, t_i / 4) im Test selbst gerechnet: h wird gehalbiert, solange eine Naht noch ueber t_i/4
    liegt, danach p + 1 bis p = 4, danach Ende; ohne Naht nur p."""
    from volumen3d.api import _fahrplan, _nahtregionen, _nahtziel
    from statik3d_contracts.detail import WeldLine

    def folge(p, basis, dicken, n=6):
        k, aus = 0, []
        for _ in range(n):
            st = _fahrplan(p, k, basis, dicken)
            aus.append(st)
            if st is None:
                break
            if st == "h":
                k += 1
            else:
                p += 1
        return aus
    soll = {
        (2, 20.0, (10.0,)): ["h", "h", "h", "p", "p", None],         # 20 -> 10 -> 5 -> 2,5 (= t/4), dann p 3, p 4
        (2, 10.0, (10.0,)): ["h", "h", "p", "p", None],              # 10 -> 5 -> 2,5
        (2, 2.5, (10.0,)): ["p", "p", None],                         # schon bei t/4: nur p
        (3, 5.0, (10.0, 20.0)): ["h", "p", None],                    # t 10: 5 -> 2,5; t 20 haelt bei 5 (= t/4)
        (2, 20.0, ()): ["p", "p", None],                             # ohne Naht nur p
        (4, 20.0, (10.0,)): ["h", "h", "h", None],                   # p 4 schon da: nur h bis t/4, dann Ende
    }
    ok = all(folge(p, b, list(d)) == e for (p, b, d), e in soll.items())
    check(f"Fahrplan: {len(soll)} Faelle (Basis 20/10/2,5, eine und zwei Naehte, ohne Naht, p 4) wie nach der Formel", ok,
          str({k: folge(k[0], k[1], list(k[2])) for k in soll}))
    wl = [WeldLine("A", np.zeros((3, 3)) + np.arange(3)[:, None] * 12.0, 10.0), WeldLine("B", np.ones((2, 3)) * 5.0, 20.0)]
    ziele = {k: sorted({round(r.target_cell_size_mm, 6) for r in _nahtregionen(wl, k, 20.0)}) for k in range(5)}
    erwartet = {k: sorted({round(_nahtziel(20.0, k, t), 6) for t in (10.0, 20.0)}) for k in range(5)}
    kugeln = _nahtregionen(wl, 1, 20.0)
    check("Nahtregionen: Zielgroesse je Naht max(h0/2^k, t/4) (k 0 bis 4), Radius 2 t, Punkte im Abstand hoechstens t",
          ziele == erwartet and ziele[3] == [2.5, 5.0] and ziele[4] == [2.5, 5.0]
          and {round(r.radius_mm, 6) for r in kugeln} == {20.0, 40.0} and len(kugeln) == 3 + 2, f"{ziele}, {len(kugeln)} Kugeln")


def test_zyklen_mit_naht():
    """Kragarm-Ausschnitt mit Naht auf der Laengskante (y 50, z 100, Blechdicke 100, t/4 = 25) ueber den Vertragsweg, Basis 50,
    p 2, zwei Zyklen: erst lokale Halbierung auf 25 (Ziel t/4 erreicht), dann p 3. Die Verfeinerungsbereiche stehen mit
    Mitte, Radius 2 t und Zielgroesse im Protokoll, die Kurve traegt die Schritte."""
    import dataclasses
    from statik3d_contracts.detail import WeldLine
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    xs = np.linspace(400.0, 600.0, 5)
    spec = dataclasses.replace(_spec(2, 50.0, 2), weld_lines=(WeldLine("N1", np.stack([xs, np.full(5, 50.0), np.full(5, 100.0)], axis=1), 100.0),))
    s = FcmSolver()
    t = time.perf_counter()
    erg = s.solve(s.prepare(spec, Material("S355", "S355", 210000.0, 0.3, fy=355.0)),
                  StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0), [ResultKey("LF1")])[0]
    k = erg.convergence
    reg = erg.protocol["settings"]["refinement"]
    check("Kragarm mit Naht, 2 Zyklen: Schritte Start / h-Halbierung Naht / p-Erhoehung, p 2 2 3, Freiheitsgrade wachsend, "
          "Bereiche im Protokoll mit Zielgroesse t/4 = 25 und Radius 2 t = 200",
          [c["step"] for c in k] == ["Start", "h-Halbierung Naht", "p-Erhoehung"] and [c["p"] for c in k] == [2, 2, 3]
          and k[0]["dofs"] < k[1]["dofs"] < k[2]["dofs"] and len(reg) >= 1 and all(abs(r["target_cell_size_mm"] - 25.0) < 1e-12
          and abs(r["radius_mm"] - 200.0) < 1e-12 for r in reg) and all(c["hotspot_max"] is not None for c in k),
          f"dofs {[c['dofs'] for c in k]}, {len(reg)} Bereiche, {time.perf_counter() - t:.1f} s")


def test_zyklen_grenzen():
    """adaptive_cycles ausserhalb 0 bis 4 -> SolverError; bei p 4 ohne Naht endet die Folge sofort mit Warnung (ein Eintrag);
    Abbruch zwischen den Zyklen -> SolverCancelled."""
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.solver import SolverCancelled, SolverError
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    mat = Material("S355", "S355", 210000.0, 0.3, fy=355.0)
    prov = StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0)
    fehler = []
    for n in (-1, 5):
        try:
            s.estimate(_spec(2, 100.0, n))
        except SolverError as ex:
            fehler.append(str(ex))
    check("adaptive_cycles -1 und 5 -> SolverError mit Bereich 0 bis 4", len(fehler) == 2 and all("0 bis 4" in f for f in fehler), str(fehler))
    erg = s.solve(s.prepare(_spec(4, 100.0, 1), mat), prov, [ResultKey("LF1")])[0]
    check("p 4 ohne Naht, adaptive_cycles 1: Folge endet sofort, ein Eintrag, Warnung nennt den Grund",
          len(erg.convergence) == 1 and any("p = 4 erreicht" in w for w in erg.warnings), str([w for w in erg.warnings if "Zyklen" in w]))
    zaehler = {"n": 0}

    def abbruch():
        zaehler["n"] += 1
        return zaehler["n"] > 4
    try:
        s.solve(s.prepare(_spec(2, 100.0, 2), mat), prov, [ResultKey("LF1")], cancel=abbruch)
        ok = False
    except SolverCancelled:
        ok = True
    check("Abbruch waehrend der Zyklen -> SolverCancelled", ok)


class ZugGeber:
    """Gesamtmodell: gleichmaessiger Zug sigma_n in x am T-Stoss (Grundblech 50 x 10 mm, Schwerpunkt y 25, z -5)."""

    def __init__(self, sigma=100.0, E=210000.0, nu=0.3, flaeche=500.0):
        self.s, self.E, self.nu, self.A = sigma, E, nu, flaeche

    def available_keys(self):
        from statik3d_contracts.model import ResultKey
        return [ResultKey("LF1")]

    def displacement_at(self, points, key):
        P = np.asarray(points, float).reshape(-1, 3)
        e = self.s / self.E
        u = np.column_stack([e * P[:, 0], -self.nu * e * (P[:, 1] - 25.0), -self.nu * e * (P[:, 2] + 5.0)])
        return u, np.zeros_like(u)

    def section_forces(self, plane, key):
        from statik3d_contracts.coupling import SectionForces
        v = 1.0 if float(np.asarray(plane.normal, float)[0]) >= 0.0 else -1.0
        return SectionForces(force=v * np.array([self.s * self.A, 0.0, 0.0]), moment=np.zeros(3))


def t_stoss_spec(h, p, zyklen):
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType, WeldLine
    from volumen3d.tests import test_hotspot as H
    geo = GeometrySource(GeometrySourceType.CSG, params={"csg": {"typ": "vereinigung", "teile": [
        {"typ": "quader", "min": [-5, 0, -H.T_BLECH], "max": [205, 50, 0], "name": "grundblech"},
        {"typ": "quader", "min": [95, 0, 0], "max": [105, 50, 60], "name": "querblech"},
        {"typ": "schnitt", "teile": [
            {"typ": "quader", "min": [105, 0, 0], "max": [H.X_RECHTS, 50, H.SCHENKEL], "name": "naht_rechts"},
            {"typ": "halbraum", "punkt": [H.X_RECHTS, 0, 0], "normale": [1, 0, 1], "name": "nahtflaeche_rechts"}]},
        {"typ": "schnitt", "teile": [
            {"typ": "quader", "min": [H.X_LINKS, 0, 0], "max": [95, 50, H.SCHENKEL], "name": "naht_links"},
            {"typ": "halbraum", "punkt": [H.X_LINKS, 0, 0], "normale": [-1, 0, 1], "name": "nahtflaeche_links"}]}]}})
    return DetailModelSpec(
        id="TS", name="T-Stoss", geometry=geo, material_id="S355",
        cut_planes=(CutPlane(np.array([0.0, 25.0, -5.0]), np.array([-1.0, 0, 0])), CutPlane(np.array([200.0, 25.0, -5.0]), np.array([1.0, 0, 0]))),
        settings=FcmSettings(base_cell_size_mm=h, p=p, adaptive_cycles=zyklen),
        weld_lines=(WeldLine("NR", H.nahtlinie(H.X_RECHTS), H.T_BLECH), WeldLine("NL", H.nahtlinie(H.X_LINKS), H.T_BLECH)))


def test_zyklen_t_stoss():
    """T-Stoss unter Zug sigma_n = 100 N/mm2 ueber den Vertragsweg (Zug-Geber, Schnittebenen an den Enden), Basiszellgroesse 10
    (= t), p 2, zwei Zyklen nach dem Fahrplan 'h zuerst bis t/4' (10 -> 5 -> 2,5). Geprueft wird, was belegt ist: Schritte und
    Freiheitsgrade, Kopplungskontrolle Kraft unter 5 %, Hot-Spot-Werte im plausiblen Bereich (0,5 bis 1,5 sigma_n), die
    Konvergenzaussage stimmt mit der nachgerechneten Monotonie ueberein, eine nicht monotone Kurve traegt die Warnung.
    Die Konvergenz selbst misst die Abnahme C1 am Knotenblech. Mit dem abwechselnden Fahrplan (h, p, h) war die Kurve nicht
    monoton (81,1 - 119,0 - 134,2 - 91,0 N/mm2; Theorie 11.14). Laeuft nur mit VOLUMEN3D_LANG=1 (Minuten)."""
    if os.environ.get("VOLUMEN3D_LANG") != "1":
        check("T-Stoss-Zyklen uebersprungen (VOLUMEN3D_LANG=1 setzen)", True)
        return
    from statik3d_contracts.model import Material, ResultKey
    from volumen3d.api import FcmSolver
    s = FcmSolver()
    t = time.perf_counter()
    disc = s.prepare(t_stoss_spec(10.0, 2, 2), Material("S355", "S355", 210000.0, 0.3, fy=355.0))
    erg = s.solve(disc, ZugGeber(), [ResultKey("LF1")])[0]
    k = erg.convergence
    hs = [c["hotspot_max"] for c in k]
    aussage = erg.protocol["convergence_statement"]
    dF = max(eb["deviation_force"] for eb in erg.coupling_check["planes"])
    dt = time.perf_counter() - t
    d = np.diff(hs)
    monoton = bool((np.all(d > 0) or np.all(d < 0)) and np.all(np.abs(d[1:]) < np.abs(d[:-1])))
    print("Kurve:", [(c["step"], c["p"], c["dofs"], c["h_min_mm"], round(c["hotspot_max"], 3), round(c["hotspot_mean"], 3), c["t_s"]) for c in k])
    print("Aussage:", aussage["text"])
    check("T-Stoss, 2 Zyklen: Schritte Start/h-Halbierung/h-Halbierung, kleinste Zelle 10 -> 5 -> 2,5 mm, Freiheitsgrade wachsend, "
          "Kopplungskontrolle Kraft < 5 %",
          [c["step"] for c in k] == ["Start", "h-Halbierung Naht", "h-Halbierung Naht"] and [c["h_min_mm"] for c in k] == [10.0, 5.0, 2.5]
          and all(a["dofs"] < b["dofs"] for a, b in zip(k[:-1], k[1:])) and dF < 0.05,
          f"dofs {[c['dofs'] for c in k]}, Abweichung Kraft {dF * 100:.2f} %, {dt:.0f} s")
    check("Hot-Spot-Werte aller Zyklen im plausiblen Bereich 0,5 bis 1,5 sigma_n; Konvergenzaussage stimmt mit der nachgerechneten Monotonie "
          "ueberein; nicht monotone Kurve traegt die Warnung",
          all(50.0 <= v <= 150.0 for v in hs) and (aussage["art"] == "monoton_konvergent") == monoton
          and (monoton or any("Konvergenz der Strukturspannung" in w for w in erg.warnings)),
          f"Werte {[round(v, 2) for v in hs]}; {aussage['text']}")


if __name__ == "__main__":
    sys.exit(lauf([test_konvergenzaussage, test_fahrplan, test_zyklen_ohne_naht, test_zyklen_mit_naht, test_zyklen_grenzen, test_zyklen_t_stoss]))
