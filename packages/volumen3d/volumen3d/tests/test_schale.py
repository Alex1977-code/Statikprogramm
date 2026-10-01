"""B7: Schale -> Volumen ueber die Vertragsschicht (Vorgabe 10 Stufe 1, Vorgabe 13 "Kopplung", Plan TP 5 B7).

Der Provider ist ein Stub dieser Suite: ein Plattenstreifen (t 10, b 100, Laenge 200 mm zwischen den Schnittebenen) als Schalenmodell mit
Reissner-Mindlin-Kinematik - ``displacement_at`` liefert Mittelflaechenverschiebung plus Rotation mal Normalenabstand (lineare Verteilung ueber
die Dicke), ``section_forces`` die Schalenresultierenden je Breite, ueber die Schnittbreite integriert. Zustand: Membrandehnung eps0 und Kruemmung
kappa in x' bei freien Laengsraendern (Querkontraktion, antiklastische Kruemmung). Dieser Zustand ist die exakte 3D-Loesung des Streifens
bis auf die Dickendehnung, die der Provider nicht kennt und der Vertragsweg auch nicht verlangt (nur die Normalkomponente punktweise und die
Mittelwerte der Tangentialkomponenten sind festgelegt).

Faelle: (A) achsparallel (CSG), (B) um 30 Grad um y geneigt (STL-Huelle, schraege Schnittebenen). Je Fall Membran, Biegung, beides.

Aufruf: python -m volumen3d.tests.test_schale   (~1 min)
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

E, NU = 210000.0, 0.3
T, B, L = 10.0, 100.0, 200.0
SIGMA_M, SIGMA_B = 100.0, 150.0                                    # Membranspannung, Randspannung aus Biegung (N/mm2)
ZUSTAENDE = {"LF1": (SIGMA_M / E, 0.0), "LF2": (0.0, SIGMA_B / (E * T / 2)), "LF3": (SIGMA_M / E, SIGMA_B / (E * T / 2))}
MITTE = np.array([0.0, 50.0, 5.0])                                 # Ursprung der lokalen Schalenachsen (Mitte der ersten Schnittflaeche)


def _drehung_y(grad):
    a = np.deg2rad(grad)
    return np.array([[np.cos(a), 0.0, np.sin(a)], [0.0, 1.0, 0.0], [-np.sin(a), 0.0, np.cos(a)]])


class SchalenGeber:
    """Schalen-Provider des Plattenstreifens; R dreht die lokalen Achsen (x' Laenge, y' Breite, z' Normale) ins Globale."""

    def __init__(self, R):
        self.R = np.asarray(R, float)

    def available_keys(self):
        from statik3d_contracts.model import ResultKey
        return [ResultKey(k) for k in ZUSTAENDE]

    def _lokal(self, P):
        return (np.asarray(P, float).reshape(-1, 3) - MITTE) @ self.R                  # = R^T (P - MITTE)

    def displacement_at(self, points, key):
        eps0, kappa = ZUSTAENDE[key.load_case_id]
        x, y, z = self._lokal(points).T
        u0 = np.stack([eps0 * x, -NU * eps0 * y, -0.5 * kappa * (x ** 2 - NU * y ** 2)], axis=1)      # Mittelflaeche
        th = np.stack([NU * kappa * y, kappa * x, np.zeros_like(x)], axis=1)                          # Rotation der Normalen
        u = u0 + np.stack([th[:, 1] * z, -th[:, 0] * z, np.zeros_like(z)], axis=1)                    # + theta x (z e_z)
        return u @ self.R.T, th @ self.R.T

    def section_forces(self, plane, key):
        from statik3d_contracts.coupling import SectionForces
        eps0, kappa = ZUSTAENDE[key.load_case_id]
        s = float(np.sign(np.asarray(plane.normal, float) @ self.R[:, 0]))             # Normale des Details in lokalem +x' oder -x'
        n_x, m_x = E * T * eps0, E * T ** 3 * kappa / 12.0                             # je Breite: N/mm bzw. N mm/mm
        f_lok = s * np.array([n_x * B, 0.0, 0.0])
        m_lok = s * np.array([0.0, m_x * B, 0.0])                                      # M_y = int z' sigma_x' dA (Stabkonvention)
        return SectionForces(force=self.R @ f_lok, moment=self.R @ m_lok)


def _spec(R, h=25.0, p=2):
    from statik3d_contracts.coupling import CutPlane
    from statik3d_contracts.detail import DetailModelSpec, FcmSettings, GeometrySource, GeometrySourceType
    ex = R[:, 0]
    if np.allclose(R, np.eye(3)):
        csg = {"typ": "quader", "min": [-5.0, 0.0, 0.0], "max": [L + 5.0, B, T], "name": "streifen"}
    else:
        from volumen3d.tests.test_huelle import _wuerfel
        D = _wuerfel([-5.0, -B / 2, -T / 2], [L + 5.0, B / 2, T / 2]) @ R.T + MITTE
        csg = {"typ": "stl", "dreiecke": D.tolist(), "name": "streifen"}
    return DetailModelSpec(id="S", name="Plattenstreifen", geometry=GeometrySource(GeometrySourceType.CSG, params={"csg": csg}),
                           material_id="S355",
                           cut_planes=(CutPlane(MITTE.copy(), -ex), CutPlane(MITTE + L * ex, ex.copy())),
                           settings=FcmSettings(base_cell_size_mm=h, p=p))


def _spannung_lokal(erg, R):
    """Spannungen (n,6 Voigt xx yy zz xy yz xz) in die lokalen Schalenachsen drehen: sigma' = R^T sigma R."""
    s = erg.stress
    S = np.empty((len(s), 3, 3))
    for k, (i, j) in enumerate(((0, 0), (1, 1), (2, 2), (0, 1), (1, 2), (0, 2))):
        S[:, i, j] = S[:, j, i] = s[:, k]
    return np.einsum("ki,nkl,lj->nij", R, S, R)


def _fall(name, R, p=2):
    from statik3d_contracts.model import Material, ResultKey
    from volumen3d.api import FcmSolver
    t0 = time.perf_counter()
    s = FcmSolver()
    disc = s.prepare(_spec(R, p=p), Material("S355", "S355", E, NU, fy=355.0))
    erg = s.solve(disc, SchalenGeber(R), [ResultKey(k) for k in ZUSTAENDE])
    dauer = time.perf_counter() - t0
    schlimmste = {"kraft": 0.0, "moment": 0.0, "sigma": 0.0, "rest": 0.0, "gleichgewicht": 0.0}
    zeilen = []
    for e, (lf, (eps0, kappa)) in zip(erg, ZUSTAENDE.items()):
        # (1) Schnittgroessenkontrolle des Vertragswegs
        ebenen = e.coupling_check["planes"]
        dF = max(eb["deviation_force"] for eb in ebenen)
        dM = max(eb["deviation_moment"] for eb in ebenen)
        # (2) Spannung in lokalen Achsen gegen die Schalenverteilung
        P = e.surface_points
        z = (P - MITTE) @ R[:, 2]
        sig = _spannung_lokal(e, R)
        soll = E * (eps0 + kappa * z)
        gross = max(float(np.abs(soll).max()), 1e-12)
        d_sig = float(np.abs(sig[:, 0, 0] - soll).max()) / gross
        rest = sig.copy()
        rest[:, 0, 0] = 0.0
        d_rest = float(np.abs(rest).max()) / gross
        # (3) Gleichgewicht der beiden Resultierenden um die Streifenmitte
        X = MITTE + 0.5 * L * R[:, 0]
        F = [eb["force_fcm"] for eb in ebenen]
        M = [eb["moment_fcm"] + np.cross(cp.origin - X, eb["force_fcm"]) for eb, cp in zip(ebenen, _ebenen(R))]
        ref_m = max(max(float(np.linalg.norm(eb["moment_fcm"])) for eb in ebenen), max(float(np.linalg.norm(f)) for f in F) * L)
        ref_f = ref_m / L                                        # gemeinsames Lastmass wie in api._kopplungsabweichung (Hebel L)
        d_gl = max(float(np.linalg.norm(F[0] + F[1])) / ref_f, float(np.linalg.norm(M[0] + M[1])) / ref_m)
        koppl_warn = [w for w in e.warnings if "Schnittebene" in w]
        for k, v in (("kraft", dF), ("moment", dM), ("sigma", d_sig), ("rest", d_rest), ("gleichgewicht", d_gl)):
            schlimmste[k] = max(schlimmste[k], v)
        zeilen.append(f"{lf}: Kraft {dF:.1e}, Moment {dM:.1e}, sigma_x' {d_sig:.1e}, Rest {d_rest:.1e}, Gleichgewicht {d_gl:.1e}, "
                      f"Kopplungswarnungen {len(koppl_warn)}")
        schlimmste.setdefault("warn", 0)
        schlimmste["warn"] += len(koppl_warn)
    return schlimmste, zeilen, dauer, disc


def _ebenen(R):
    from statik3d_contracts.coupling import CutPlane
    ex = R[:, 0]
    return (CutPlane(MITTE.copy(), -ex), CutPlane(MITTE + L * ex, ex.copy()))


def test_schale_achsparallel():
    schl, zeilen, dauer, disc = _fall("A", np.eye(3))
    check(f"Schale -> Volumen, achsparallel (CSG, h 25 p 2): Schnittgroessen Kraft {schl['kraft']:.1e} und Moment {schl['moment']:.1e} (< 1 %), "
          f"keine Kopplungswarnung", schl["kraft"] < 0.01 and schl["moment"] < 0.01 and schl["warn"] == 0, "; ".join(zeilen) + f"; {dauer:.0f} s")
    check(f"achsparallel: sigma_x' gleich Schalenverteilung auf {schl['sigma']:.1e} (< 1 %), uebrige Komponenten {schl['rest']:.1e} (< 1 %)",
          schl["sigma"] < 0.01 and schl["rest"] < 0.01)
    # gemessen 1,9e-11 (Rundung); Schranke 1e-9 als Band um den Messwert
    check(f"achsparallel: Resultierende beider Ebenen im Gleichgewicht ({schl['gleichgewicht']:.1e} < 1e-9)", schl["gleichgewicht"] < 1e-9)


def test_schale_geneigt():
    """Geneigter Streifen, p 2: Schnittgroessen, Spannung und Gleichgewicht unter der Vorgabeschranke 1 %. Gemessen (01.10.2026, h 25):
    30 Grad Spannung 2,2e-4, Gleichgewicht 4,2e-3; 10 Grad Spannung 3,5e-3, Gleichgewicht 4,6e-4. Die im Plan vorab gesetzte Schranke 1e-6
    fuer das Gleichgewicht war geraten und wird hier nicht gehalten (Entscheidung des Anwenders): das Feld liegt im Ansatzraum, aber
    der p-2-Ansatz reproduziert es am schraegen Schnitt nur auf die Konsistenzfehler der Schnittzellen (unabhaengig von alpha, Fitting,
    Flaechenordnung und Tiefe, abhaengig von der Aggregationsschwelle); mit p 3 siehe die naechste Pruefung."""
    R = _drehung_y(30.0)
    schl, zeilen, dauer, disc = _fall("B", R)
    st = disc.problem.quadratur.statistik
    check(f"Schale -> Volumen, 30 Grad geneigt (STL-Huelle, schraege Ebenen, p 2): Schnittgroessen Kraft {schl['kraft']:.1e} und Moment {schl['moment']:.1e} "
          f"(< 1 %), keine Kopplungswarnung", schl["kraft"] < 0.01 and schl["moment"] < 0.01 and schl["warn"] == 0,
          "; ".join(zeilen) + f"; {dauer:.0f} s, Huellenzellen {st.get('huellenzellen')}, Punkttest {st['blaetter_punkttest']}")
    check(f"geneigt p 2: sigma_x' gleich Schalenverteilung auf {schl['sigma']:.1e} (< 1 %), uebrige Komponenten {schl['rest']:.1e} (< 1 %)",
          schl["sigma"] < 0.01 and schl["rest"] < 0.01)
    check(f"geneigt p 2: Resultierende beider Ebenen im Gleichgewicht ({schl['gleichgewicht']:.1e} < 1 %)", schl["gleichgewicht"] < 0.01)
    # alle Oberflaechenpunkte im Detail: keine Punkte hinter den Schnittebenen (Befund aus B7, test_huelle.test_flaeche_hinter_schnittebene)
    from statik3d_contracts.model import ResultKey
    from volumen3d.api import FcmSolver
    e = FcmSolver().solve(disc, SchalenGeber(R), [ResultKey("LF1")])[0]
    x_lokal = (e.surface_points - MITTE) @ R[:, 0]
    check(f"geneigt: alle {len(x_lokal)} Oberflaechenpunkte liegen zwischen den Schnittebenen (x' {x_lokal.min():.4f} bis {x_lokal.max():.4f}, Soll 0 bis 200)",
          x_lokal.min() > -1e-6 and x_lokal.max() < L + 1e-6)


def test_schale_geneigt_p3():
    """Geneigter Streifen, p 3 (10 und 30 Grad): das Feld wird bis auf Rundung reproduziert. Gemessen (01.10.2026, h 25): Spannung
    <= 2,5e-6, Schnittgroessen <= 6e-8, Gleichgewicht <= 2,2e-7; Schranke 1e-5 (rund das Vierfache des Messwerts, kein Herleitungswert)."""
    for grad in (10.0, 30.0):
        schl, zeilen, dauer, disc = _fall("B3", _drehung_y(grad), p=3)
        check(f"geneigt {grad:.0f} Grad p 3: Schnittgroessen Kraft {schl['kraft']:.1e}, Moment {schl['moment']:.1e}, sigma_x' {schl['sigma']:.1e}, Rest {schl['rest']:.1e}, "
              f"Gleichgewicht {schl['gleichgewicht']:.1e} (alle < 1e-5), keine Kopplungswarnung",
              max(schl[k] for k in ("kraft", "moment", "sigma", "rest", "gleichgewicht")) < 1e-5 and schl["warn"] == 0, f"{dauer:.0f} s")


def test_kopplungsabweichung():
    """Die Kontrollgroesse als reine Funktion (api._kopplungsabweichung): Bezuege und Grenzfaelle, Erwartungswerte von Hand
    (Flaeche 10 000 mm2 -> l = 100 mm)."""
    from volumen3d.api import _kopplungsabweichung as k
    z = np.zeros(3)
    # reine Biegung: Kraft im Globalmodell 0, Rundungsrest 1e-9 N im Detail, Moment 2,5e5 N mm stimmt: kein Scheinwert
    dF, dM, rf, rm = k(np.array([1e-9, 0, 0]), np.array([0, 2.5e5, 0]), z, np.array([0, 2.5e5, 0]), 1e4)
    check("reine Biegung (Kraft 0 gegen 1e-9 N): Kraftabweichung 1e-9 / 2500 = 4e-13 (Bezug M/l), Moment 0; vorher 1,0",
          abs(dF - 1e-9 / 2500.0) < 1e-20 and dM == 0.0 and abs(rf - 2500.0) < 1e-9 and abs(rm - 2.5e5) < 1e-6, f"{dF:.2e}, {dM:.2e}, {rf}, {rm}")
    # reiner Zug (Moment 0 beidseits): Bezug der Kraft die Kraft selbst, Wert wie bisher
    dF, dM, rf, rm = k(np.array([1e5 * 1.001, 0, 0]), z, np.array([1e5, 0, 0]), z, 1e4)
    check("reiner Zug, Kraft 0,1 % zu gross: Kraftabweichung 1e-3 / 1,001 (Bezug die groessere Kraft), Moment 0 (Bezug F l)",
          abs(dF - 100.0 / 100100.0) < 1e-12 and dM == 0.0 and abs(rf - 100100.0) < 1e-9, f"{dF:.6e}, {dM:.1e}, {rf}")
    # Kraft und Moment verschieden gross: das groessere Lastmass gilt fuer beide
    dF, dM, rf, rm = k(np.array([0, 0, 900.0]), np.array([0, 4e5, 0]), np.array([0, 0, 1000.0]), np.array([0, 4e5, 0]), 1e4)
    check("Querkraft 900 gegen 1000 N bei Moment 4e5 N mm (Lastmass max(4e5, 1000 * 100) = 4e5): Kraftabweichung 100 / 4000 = 2,5 %",
          abs(dF - 100.0 / 4000.0) < 1e-12 and dM == 0.0 and abs(rm - 4e5) < 1e-6, f"{dF:.4e}")
    # Nullwerte auf beiden Seiten: 0, keine Division
    dF, dM, rf, rm = k(z, z, z, z, 1e4)
    check("Nullwerte beidseits: 0 und 0 (Bezuege 0)", dF == 0.0 and dM == 0.0 and rf == 0.0 and rm == 0.0)
    # eigene Werte, Globalmodell null: gemeldete Kraft allein ist 100 % (keine Verschleierung)
    dF, dM, rf, rm = k(np.array([500.0, 0, 0]), z, z, z, 1e4)
    check("Detail meldet 500 N, Globalmodell 0, keine Momente: Kraftabweichung 1,0 (echte Abweichung bleibt sichtbar)", abs(dF - 1.0) < 1e-12 and dM == 0.0, f"{dF}")


TESTS = [test_kopplungsabweichung, test_schale_achsparallel, test_schale_geneigt, test_schale_geneigt_p3]

if __name__ == "__main__":
    sys.exit(lauf(TESTS))
