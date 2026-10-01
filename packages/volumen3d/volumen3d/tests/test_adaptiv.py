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
    # Befund G3-2 (Gutachten C2, 02.10.2026): die letzte Aenderung null galt vor der Monotoniepruefung als Konvergenz - auch nach einem
    # Ueberschwinger [100, 120, 90, 90] und bei einer konstanten Folge, die nur zeigt, dass sich nichts geaendert hat (wirkungslose Zyklen)
    nach_schwung = konvergenzaussage([100.0, 120.0, 90.0, 90.0])
    konstant = konvergenzaussage([100.0, 100.0, 100.0])
    ruhig = konvergenzaussage([100.0, 110.0, 112.0, 112.0])
    check("Schwingende und wachsende Folge: nicht monoton, kein Grenzwert; zwei Werte zu wenig; fehlender Wert kein Hot-Spot; "
          "Null nach Ueberschwinger nicht monoton; konstante Folge 'ohne Aenderung' ohne Grenzwert; Null nach monotoner Annaeherung konvergent",
          schwingt["art"] == waechst["art"] == "nicht_monoton" and schwingt["grenzwert"] is None and waechst["grenzwert"] is None
          and konvergenzaussage([1.0, 2.0])["art"] == "zu_wenige_zyklen" and konvergenzaussage([1.0, None, 2.0])["art"] == "kein_hotspot"
          and nach_schwung["art"] == "nicht_monoton" and konstant["art"] == "ohne_aenderung" and konstant["grenzwert"] is None
          and ruhig["art"] == "monoton_konvergent" and ruhig["grenzwert"] == 112.0,
          f"{schwingt['text']} | {nach_schwung['text']} | {konstant['text']} | {ruhig['text']}")


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
    # Befund G3-4 (Gutachten C2, 02.10.2026): der Ausdruck stand als "A and ... and D if 'cycles' in protocol else E" und pruefte ohne
    # Zyklen nur E - der Spannungsvergleich lief nie; jetzt ausdruecklich, und ohne Zyklen stehen cycles 0 und die Aussage im Protokoll
    gleich_form = erg[0].stress.shape == einzeln.stress.shape
    d_s = float(np.abs(erg[0].stress - einzeln.stress).max()) if gleich_form else float("inf")
    # gemessen (02.10.2026): 9,2e-11 bis 3,7e-10 des Groesstwerts 12,3 N/mm2 (PARDISO parallel, Toleranz 1e-12); Schranke 1e-8
    check("Letzter Zyklus = Rechnung mit p 4 ohne Zyklen (Spannungen auf 1e-8 des Groesstwerts, gleiche Oberflaeche), ohne Zyklen ein Eintrag, "
          "cycles 0 und Konvergenzaussage im Protokoll",
          gleich_form and d_s <= 1e-8 * float(np.abs(einzeln.stress).max()) and len(einzeln.convergence) == 1
          and einzeln.protocol.get("cycles") == 0 and "convergence_statement" in einzeln.protocol, f"{d_s:.1e}")


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


def test_massgebender_hotspot():
    """Befund G3-5/G2-6 (Gutachten C2, 02.10.2026): hotspot_max war das vorzeichenbehaftete Maximum - unter Druck (alle sigma_hs < 0) der
    betragskleinste, also unmassgebende Punkt, auf den sich Kurve und Konvergenzaussage bezogen. Jetzt der betragsgroesste Wert mit Vorzeichen."""
    from volumen3d.api import _massgebend
    check("massgebender Hot-Spot: Druck -120 statt -3, gemischt -150 vor +100, Zug 130, leer None",
          _massgebend([-3.0, -120.0, -50.0]) == -120.0 and _massgebend([100.0, -150.0]) == -150.0 and _massgebend([10.0, 130.0]) == 130.0
          and _massgebend([]) is None)


def test_zyklen_ohne_wirkung():
    """Befund G3-2 (Gutachten C2): hat der Anwender die Naht schon selbst auf t/4 verfeinert, aenderten die h-Schritte das Netz nicht; zwei
    wirkungslose Zyklen wurden gerechnet und die Aussage hiess 'monoton konvergent, letzte Aenderung null'. Jetzt wird ein h-Schritt ohne
    Wirkung uebersprungen (der Fahrplan geht weiter) und im Protokoll genannt. Kragarm h 100 p 1, Naht t 100 mit eigenem Bereich Radius 400
    auf 25, zwei Zyklen: beide sind p-Erhoehungen (p 1, 2, 3), Freiheitsgrade wachsen, Warnung nennt die uebersprungenen h-Schritte."""
    import dataclasses
    from statik3d_contracts.detail import RefinementRegion, WeldLine
    from statik3d_contracts.model import Material, ResultKey
    from statik3d_contracts.testing import StubGlobalFieldProvider
    from volumen3d.api import FcmSolver
    xs = np.linspace(400.0, 600.0, 5)
    s0 = _spec(1, 100.0, 2)
    spec = dataclasses.replace(s0, weld_lines=(WeldLine("N1", np.stack([xs, np.full(5, 50.0), np.full(5, 100.0)], axis=1), 100.0),),
                               refinement=(RefinementRegion(center=np.array([500.0, 50.0, 100.0]), radius_mm=400.0, target_cell_size_mm=25.0),))
    s = FcmSolver()
    t = time.perf_counter()
    erg = s.solve(s.prepare(spec, Material("S355", "S355", 210000.0, 0.3, fy=355.0)),
                  StubGlobalFieldProvider(1000.0, 100.0, 200.0, 210000.0, 10000.0), [ResultKey("LF1")])[0]
    k = erg.convergence
    hinweis = [w for w in erg.warnings if "ohne Wirkung" in w]
    check("eigene Verfeinerung auf t/4: h-Schritte ohne Wirkung uebersprungen, Zyklen p 1 -> 2 -> 3 mit wachsenden Freiheitsgraden, Hinweis im Ergebnis",
          [c["step"] for c in k] == ["Start", "p-Erhoehung", "p-Erhoehung"] and [c["p"] for c in k] == [1, 2, 3]
          and k[0]["dofs"] < k[1]["dofs"] < k[2]["dofs"] and len(hinweis) >= 1,
          f"Schritte {[c['step'] for c in k]}, dofs {[c['dofs'] for c in k]}, {hinweis}, {time.perf_counter() - t:.1f} s")


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
    # Abbruch genau zwischen Zyklus 0 und 1 (Befund G3-4: der Zaehler loeste vorher erst innerhalb von Zyklus 1 aus, die Abfrage zwischen
    # den Zyklen war ungeprueft): nach dem ersten Zyklus wird der Abbruch wahr, die Meldung muss den naechsten Zyklus nennen
    zustand = {"fertig": False}
    zyklus_orig = s._zyklus

    def zyklus_mit_marke(*a, **kw):
        erg_z = zyklus_orig(*a, **kw)
        zustand["fertig"] = True
        return erg_z
    s._zyklus = zyklus_mit_marke
    try:
        s.solve(s.prepare(_spec(2, 100.0, 2), mat), prov, [ResultKey("LF1")], cancel=lambda: zustand["fertig"])
        meldung = ""
    except SolverCancelled as ex:
        meldung = str(ex)
    finally:
        s._zyklus = zyklus_orig
    check("Abbruch zwischen den Zyklen -> SolverCancelled 'vor Zyklus 1'", "vor Zyklus 1" in meldung, meldung)
    # Befund G3-7: Blechdicke 0 fiel erst im ersten Zyklus auf (Meldung zu RefinementRegion); ein Fehler im spaeteren Zyklus verwarf alles
    import dataclasses
    from statik3d_contracts.detail import WeldLine
    try:
        s.prepare(dataclasses.replace(_spec(2, 100.0, 1), weld_lines=(WeldLine("N0", np.array([[400.0, 50, 100], [600.0, 50, 100]]), 0.0),)), mat)
        dicke = ""
    except SolverError as ex:
        dicke = str(ex)
    zyklen_orig = s._zyklus
    aufrufe = {"n": 0}

    def zyklus_scheitert_spaet(*a, **kw):
        aufrufe["n"] += 1
        if aufrufe["n"] == 2:
            raise SolverError("Probe: Zyklus 1 scheitert")
        return zyklen_orig(*a, **kw)
    s._zyklus = zyklus_scheitert_spaet
    try:
        erg2 = s.solve(s.prepare(_spec(2, 100.0, 2), mat), prov, [ResultKey("LF1")])[0]
    finally:
        s._zyklus = zyklen_orig
    check("Blechdicke 0 -> SolverError in prepare mit 'Blechdicke'; scheitert Zyklus 1, gilt Zyklus 0 mit Warnung (ein Eintrag)",
          "Blechdicke" in dicke and len(erg2.convergence) == 1 and any("Zyklus 1 gescheitert" in w for w in erg2.warnings),
          f"{dicke[:60]} | {[w for w in erg2.warnings if 'gescheitert' in w]}")


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
    sys.exit(lauf([test_konvergenzaussage, test_fahrplan, test_zyklen_ohne_naht, test_zyklen_mit_naht, test_zyklen_grenzen, test_massgebender_hotspot,
                   test_zyklen_ohne_wirkung, test_zyklen_t_stoss]))
