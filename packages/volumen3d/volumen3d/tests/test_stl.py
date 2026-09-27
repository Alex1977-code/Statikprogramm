"""U4: STL-Eingang - Lesen/Schreiben, Windungszahl (auch mit Luecke), Abstand, lokale Ebenen,
exaktes Volumen eines Wuerfel-STL, Lame aus einem tessellierten Viertelzylinder gegen CSG.

Aufruf: python -m volumen3d.tests.test_stl   (~3 min)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

import numpy as np

from volumen3d.tests._pruef import check, lauf


def _wuerfel_dreiecke(lo=0.0, hi=10.0):
    from volumen3d.geometry.sdf import Quader
    V, T = Quader([lo, lo, lo], [hi, hi, hi]).dreiecke(None, None, 1.0)
    return V[T]


def test_lesen_und_windungszahl():
    from volumen3d.geometry.stl import Stl, lies_stl, schreibe_stl, windungszahl
    D = _wuerfel_dreiecke()
    ordner = tempfile.mkdtemp()
    pfad = os.path.join(ordner, "wuerfel.stl")
    schreibe_stl(pfad, D)
    D2, N2 = lies_stl(pfad)
    check("binaeres STL: 12 Dreiecke rund gelesen", D2.shape == (12, 3, 3) and np.allclose(D2, D) and N2.shape == (12, 3))
    with open(os.path.join(ordner, "w.stl"), "w", encoding="utf-8") as f:
        f.write("solid w\n")
        for t in D:
            f.write("  facet normal 0 0 0\n    outer loop\n" + "".join(f"      vertex {v[0]} {v[1]} {v[2]}\n" for v in t) + "    endloop\n  endfacet\n")
        f.write("endsolid w\n")
    D3, _ = lies_stl(os.path.join(ordner, "w.stl"))
    check("ASCII-STL gelesen", D3.shape == (12, 3, 3) and np.allclose(D3, D))
    P = np.array([[5, 5, 5], [15, 5, 5], [5, 5, 10.0], [10, 10, 5.0], [10, 10, 10.0]])
    w = windungszahl(P, D)
    check("Windungszahl: innen 1, aussen 0, auf der Flaeche 1/2, auf der Kante 1/4, an der Ecke 1/8",
          np.allclose(w, [1, 0, 0.5, 0.25, 0.125], atol=1e-9), str(np.round(w, 4)))
    s = Stl.aus_dreiecken(D[:, [0, 2, 1], :])                 # absichtlich falsch orientiert (innen w = -1)
    check("Orientierung wird ueber |Windungszahl| nach aussen gedreht (Facettennormale auf der Seite x = 10 zeigt +x), Defekt 0",
          np.allclose(s.gradient(np.array([[10.0, 5, 5]]))[0], [1, 0, 0]) and s.defekt < 1e-9 and bool(s.innen(np.array([[5.0, 5, 5]]))[0]),
          f"{s.gradient(np.array([[10.0, 5, 5]]))[0]}, Defekt {s.defekt:.2e}")
    # eine einzelne Facette verkehrt gewickelt: die Windungszahl an ihrer Probe merkt das nicht (eigener
    # Raumwinkel +-1/2), die Kantenwicklung schon; Punkte 1 mm unter ihr muessen innen bleiben
    D_e = D.copy()
    D_e[8] = D_e[8][[0, 2, 1]]
    s_e = Stl.aus_dreiecken(D_e)
    s_ok = Stl.aus_dreiecken(D)
    unter = D[8].mean(axis=0) - np.array([1.0, 0, 0])            # Facette 8 liegt auf x = 10
    check("eine verkehrt gewickelte Facette wird ueber die Kantennachbarn gewendet (umgedreht 1, Normalen wie beim heilen Wuerfel, innen richtig)",
          s_e.umgedreht == 1 and np.allclose(np.sort(s_e.normalen, axis=0), np.sort(s_ok.normalen, axis=0)) and bool(s_e.innen(unter[None])[0])
          and s_e.defekt < 1e-9, f"umgedreht {s_e.umgedreht}, Defekt {s_e.defekt:.2e}")
    # Hohlkoerper: Wuerfel 30 mit Hohlraum 10 (beide Schalen gleich gewickelt geliefert): der Hohlraum muss
    # nach innen zeigen -> Wand innen, Hohlraum aussen, Defekt 0
    D_h = np.concatenate([_wuerfel_dreiecke(0.0, 30.0), _wuerfel_dreiecke(10.0, 20.0)])
    s_h = Stl.aus_dreiecken(D_h)
    check("Hohlwuerfel: Hohlraumschale nach innen gerichtet, Wand innen, Hohlraum aussen, Defekt 0",
          bool(s_h.innen(np.array([[5.0, 5, 5]]))[0]) and not bool(s_h.innen(np.array([[15.0, 15, 15]]))[0]) and s_h.defekt < 1e-9
          and abs(s_h.abstand(np.array([[15.0, 15, 15]]))[0] - 5.0) < 1e-12, f"umgedreht {s_h.umgedreht}, Defekt {s_h.defekt:.2e}")
    # Luecke: eine Facette der Seite x = 10 fehlt (halbe Seite offen, 1/12 der Oberflaeche)
    D_l = D[[i for i in range(12) if i != 8]]
    w_l = windungszahl(P[:2], D_l)
    check("Wuerfel mit Luecke: Windungszahl innen 11/12, aussen 1/12 (Summe 1) -> Innen/Aussen bleibt richtig (ein Strahltest durch die Luecke saehe innen als aussen)",
          w_l[0] > 0.9 and w_l[1] < 0.1 and abs(w_l[0] + w_l[1] - 1) < 1e-9 and abs(w_l[0] - 11 / 12) < 1e-9, str(np.round(w_l, 4)))
    s_l = Stl.aus_dreiecken(D_l)
    # Defekt an der Stichprobe (Facettenmitten +- eps): nahe der Luecke groesser als 1/12 in der Wuerfelmitte, gemessen 0,0968
    check("Stl mit Luecke: innen/aussen an Punkten dicht an der Luecke richtig, Defekt gemeldet (0,08 < Defekt < 0,25)",
          bool(s_l.innen(np.array([[9.0, 8, 8]]))[0]) and not bool(s_l.innen(np.array([[11.0, 8, 8]]))[0]) and 0.08 < s_l.defekt < 0.25,
          f"Defekt {s_l.defekt:.4f}")


def test_abstand_und_ebenen():
    from volumen3d.geometry.stl import Stl
    s = Stl.aus_dreiecken(_wuerfel_dreiecke())
    P = np.array([[5, 5, 5], [13, 5, 5], [13, 13, 5], [13, 13, 13.0], [5, 5, 9.0]])
    check("Abstand: innen -5, Seite 3, Kante 3 sqrt2, Ecke 3 sqrt3, nahe Deckel -1",
          np.allclose(s.abstand(P), [-5, 3, 3 * np.sqrt(2), 3 * np.sqrt(3), -1]), str(s.abstand(P)))
    g = s.gradient(P)
    check("Gradient nach aussen (Seite, Kante, Ecke, Deckel)",
          np.allclose(g[1], [1, 0, 0]) and np.allclose(g[2], [1, 1, 0] / np.sqrt(2)) and np.allclose(g[3], [1, 1, 1] / np.sqrt(3)) and np.allclose(g[4], [0, 0, 1]), str(g))
    eb = s.lokale_ebenen(np.array([10.0, 5, 5]), 1.0)
    check("lokale Ebenen an der Seite x = 10: genau eine (koplanare Facetten zusammengefasst)", len(eb) == 1 and np.allclose(eb[0][1], [1, 0, 0]), str(eb))
    eb = s.lokale_ebenen(np.array([10.0, 10, 5]), 1.0)
    check("an der Kante: zwei Ebenen, konvex", len(eb) == 2 and s.lokal_konvex(np.array([10.0, 10, 5]), 1.0))
    # einspringende Kante: L-foermiger Koerper aus zwei Quadern (Vereinigung) als STL-Oberflaeche
    from volumen3d.geometry.sdf import Quader
    a = Quader([0, 0, 0], [10, 10, 10]).dreiecke(None, None, 1.0)
    b = Quader([10, 0, 0], [20, 5, 10]).dreiecke(None, None, 1.0)
    D = np.concatenate([a[0][a[1]], b[0][b[1]]])
    # gemeinsame Seite x = 10 bei y in [0,5] entfernen: hier vereinfacht: beide Koerper behalten ihre Seite ->
    # innere Doppelflaeche; die Windungszahl bleibt trotzdem richtig (Beitraege heben sich auf)
    s2 = Stl.aus_dreiecken(D)
    check("L-Koerper mit innerer Doppelflaeche: Windungszahl innen 1 (Beitraege der Doppelflaeche heben sich auf)",
          abs(s2.windungszahl(np.array([[5.0, 2, 5]]))[0] - 1) < 1e-9 and abs(s2.windungszahl(np.array([[15.0, 2, 5]]))[0] - 1) < 1e-9)
    check("einspringende Kante (10, 5, z): lokal nicht konvex -> Rueckfall angezeigt", not s2.lokal_konvex(np.array([10.0, 5, 5]), 1.0))


def test_volumen_und_quadratur():
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.stl import Stl
    D = _wuerfel_dreiecke(1.0, 31.0)
    g = aus_params({"csg": {"typ": "stl", "dreiecke": D.tolist(), "name": "w"}})
    G = Gitter(g, h=10.0)
    Q = Zellquadratur(G, p=2, alpha=0.0)
    check("Wuerfel-STL 30^3 im Gitter h 10 (Kanten und Ecken in Zellen): Volumen exakt (< 1e-10)", abs(Q.volumen() / 27000.0 - 1) < 1e-10,
          f"{Q.volumen():.6f}, {Q.statistik}")
    check("dabei nur ebene Blaetter, kein Punkttest", Q.statistik["blaetter_punkttest"] == 0 and Q.statistik["blaetter_eben"] > 0)
    # schraeg: gedrehter Wuerfel (Rotation um z um 30 Grad und um x um 20 Grad)
    rz = np.deg2rad(30.0)
    rx = np.deg2rad(20.0)
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
    Dr = (D - 16.0) @ (Rx @ Rz).T + 16.0
    gr = aus_params({"csg": {"typ": "stl", "dreiecke": Dr.tolist()}})
    Gr = Gitter(gr, h=10.0)
    Qr = Zellquadratur(Gr, p=2, alpha=0.0)
    check("gedrehter Wuerfel-STL: Volumen exakt (< 1e-10), Kanten und Ecken als konvexe Schnitte", abs(Qr.volumen() / 27000.0 - 1) < 1e-10,
          f"{Qr.volumen():.6f}, {Qr.statistik}")
    # echter L-Koerper (eine einspringende Kante bei (20, 10, z)): dort Rueckfall auf den Punkttest,
    # ueberall sonst ebene Stuecke; Volumen 40*10*20 + 20*10*20 = 12 000
    D2 = _prisma([(0, 0), (40, 0), (40, 10), (20, 10), (20, 20), (0, 20)], 20.0)
    g2 = aus_params({"csg": {"typ": "stl", "dreiecke": D2.tolist()}})
    G2 = Gitter(g2, h=10.0)
    Q2 = Zellquadratur(G2, p=2, alpha=0.0)
    f2 = abs(Q2.volumen() / 12000.0 - 1)
    # Rueckfall-Blaetter liegen alle in Reichweite der einspringenden Kante (20, 10, z): Zellumkugel r = h sqrt3/2
    abstand_kante = np.array([np.hypot(m[0] - 20.0, m[1] - 10.0) - r for m, r in Q2.punkttest_orte])
    # konkave Kante: Werkstoff = Vereinigung der Halbraeume (exakt); an den zwei Ecken, wo die Kante
    # den Boden/Deckel trifft (gemischte Lage), zerlegt die binaere Raumteilung - Rueckfall hoechstens dort
    check("L-Koerper (einspringende Kante): Volumen 12 000 auf 1e-8, Rueckfall hoechstens an Blaettern, deren Umkugel die Kante erreicht",
          f2 < 1e-8 and (len(abstand_kante) == 0 or (abstand_kante <= 1e-9).all()),
          f"{Q2.volumen():.6f} ({f2 * 100:.6f} %), {Q2.statistik}" + (f", max Abstand Kante {abstand_kante.max():.2f}" if len(abstand_kante) else ""))


def _prisma(ecken, hoehe):
    """Wasserdichte Facetten eines Prismas ueber dem Polygon ``ecken`` (gegen den Uhrzeigersinn,
    sternfoermig zur ersten Ecke), Normalen nach aussen."""
    P = np.asarray(ecken, float)
    D = []
    for k in range(1, len(P) - 1):
        a, b, c = P[0], P[k], P[k + 1]
        D.append([[*a, 0.0], [*c, 0.0], [*b, 0.0]])                                   # Boden: -z
        D.append([[*a, hoehe], [*b, hoehe], [*c, hoehe]])                             # Deckel: +z
    for k in range(len(P)):
        a, b = P[k], P[(k + 1) % len(P)]
        D.append([[*a, 0.0], [*b, 0.0], [*b, hoehe]])                                 # Wand: (b-a) x z zeigt nach rechts = aussen
        D.append([[*a, 0.0], [*b, hoehe], [*a, hoehe]])
    return np.asarray(D)


def _viertelzylinder_stl(ri, ra, t, facette):
    """Wasserdichte Tessellierung des Viertelrings (x, y >= 0, 0 <= z <= t)."""
    n = max(8, int(np.ceil(0.5 * np.pi * ra / facette)))
    th = np.linspace(0, 0.5 * np.pi, n + 1)
    D = []

    def ring(r, z):
        return np.stack([r * np.cos(th), r * np.sin(th), np.full_like(th, z)], axis=1)

    def viereck(a, b, c, d):                                  # Normale (b-a) x (c-a)
        D.append([a, b, c])
        D.append([a, c, d])
    ai, ao, bi, bo = ring(ri, 0.0), ring(ra, 0.0), ring(ri, t), ring(ra, t)
    for k in range(n):
        viereck(ai[k], bi[k], bi[k + 1], ai[k + 1])           # innen:  z x (z + th) = -r
        viereck(ao[k], ao[k + 1], bo[k + 1], bo[k])           # aussen: th x (th + z) = +r
        viereck(ai[k], ai[k + 1], ao[k + 1], ao[k])           # Boden:  th x (th + r) = -z
        viereck(bi[k], bo[k], bo[k + 1], bi[k + 1])           # Deckel: r x (r + th) = +z
    viereck(ai[0], ao[0], bo[0], bi[0])                       # Seite y = 0:  x x (x + z) = -y
    viereck(ai[-1], bi[-1], bo[-1], ao[-1])                   # Seite x = 0:  z x (z + y) = -x
    return np.asarray(D)


def test_lame_aus_stl():
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    from volumen3d.tests.test_lame import E, NU, PI, RA, RI, T, _fehler, _rechnen
    D = _viertelzylinder_stl(RI, RA, T, 1.0)
    from volumen3d.geometry.stl import Stl
    s = Stl.aus_dreiecken(D)
    check("Viertelring-STL: Windungszahl in der Wand 1, in der Bohrung 0", abs(s.windungszahl(np.array([[60.0, 30, 10]]))[0] - 1) < 1e-9 and abs(s.windungszahl(np.array([[20.0, 20, 10]]))[0]) < 1e-9)
    # Symmetrieebenen als Halbraeume (benannt) um das STL: Schnitt -> die ebenen STL-Seiten liegen darauf
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "stl", "dreiecke": D.tolist(), "name": "ring"},
        {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [-1, 0, 0], "name": "sym_x"},
        {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, -1, 0], "name": "sym_y"},
        {"typ": "halbraum", "punkt": [0, 0, 0], "normale": [0, 0, -1], "name": "sym_z0"},
        {"typ": "halbraum", "punkt": [0, 0, T], "normale": [0, 0, 1], "name": "sym_z1"}]}})
    t0 = time.perf_counter()
    pr = FcmProblem(g, h=10.0, p=3, werkstoff=Werkstoff(E, NU))
    for n in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
        pr.verschiebungsrand(n, n, projektion="normal")
    # Bohrungswand = Facetten auf den Sehnen des Innenradius (Sagitta 1/(8*50) = 0,0025 mm); Deckel und
    # Seiten des STL tragen denselben Namen "ring" und duerfen keinen Druck bekommen
    radius = np.hypot(pr.oberflaeche.punkte[:, 0], pr.oberflaeche.punkte[:, 1])
    innen = pr.oberflaeche.auswahl((pr.oberflaeche.name.astype(str) == "ring") & (np.abs(radius - RI) < 0.05))
    pr.druck(None, PI, quadratur=innen)
    U = pr.loesen({})[:, 0]
    er, ep, eu, ez = _fehler(pr.auswertung(U))
    pr_csg, aus_csg = _rechnen(3, 10.0)
    er2, ep2, eu2, ez2 = _fehler(aus_csg)
    check("Lame aus STL (Facette 1 mm), p=3: sigma_r, sigma_phi gegen Lame < 1 %", er < 0.01 and ep < 0.01,
          f"STL sigma_r {er * 100:.3f} %, sigma_phi {ep * 100:.3f} %, u_r {eu * 100:.3f} %; CSG {er2 * 100:.3f} / {ep2 * 100:.3f} %; "
          f"{pr.protokoll['quadraturpunkte']} Punkte, Rueckfall {pr.protokoll['quadratur']['blaetter_punkttest']}, {time.perf_counter() - t0:.0f} s")
    # Die Facetten sind exakte Ebenen des STL-Koerpers (Sagitta 0,0025 mm), die CSG-Zylinderflaeche wird
    # bei Tiefe 2 durch Tangentialebenen mit Fehler (2,5/50)^2 genaehert (Theorie 11.7: sigma_r 0,32 %):
    # das STL darf also nicht schlechter sein als CSG, gemessen 27.09.2026 sigma_r 0,066 % gegen 0,316 %
    check("STL hoechstens so ungenau wie CSG (+0,2 Prozentpunkte), Sehnen 1 mm", er <= er2 + 0.002 and ep <= ep2 + 0.002,
          f"sigma_r {er * 100:.3f} % / CSG {er2 * 100:.3f} %, sigma_phi {ep * 100:.3f} % / CSG {ep2 * 100:.3f} %")


def test_suchbaum():
    """BVH (numba) und Schwerpunkt-Index (numpy) liefern dieselben naechsten Punkte wie die volle
    Suche - fern, nahe der Huelle und genau auf Facetten; numba- und numpy-Windungszahl stimmen."""
    from volumen3d.geometry import stl as stlmod
    from volumen3d.geometry.stl import Stl, _DreieckIndex, _naechster_punkt_dreieck, _windungszahl_np, naechste_punkte, windungszahl
    from volumen3d.tests.test_lame import RA, RI, T
    D = _viertelzylinder_stl(RI, RA, T, 3.0)
    s = Stl.aus_dreiecken(D)
    rng = np.random.default_rng(7)
    P = np.concatenate([rng.uniform([-5, -5, -5], [105, 105, 25], (1500, 3)),
                        D.reshape(-1, 3)[rng.integers(0, 3 * len(D), 500)] + rng.normal(0, 0.3, (500, 3)),
                        D.mean(axis=1)[rng.integers(0, len(D), 500)]])
    d_voll, q_voll, _ = naechste_punkte(P, D)
    for name, index in ((type(s._index).__name__, s._index), ("_DreieckIndex", _DreieckIndex(np.ascontiguousarray(D)))):
        d, q, t = index.naechste(P)
        check(f"{name}: Abstaende und naechste Punkte wie die volle Suche (2500 Punkte, {len(D)} Facetten)",
              np.abs(d - d_voll).max() < 1e-10 and np.allclose(q, q_voll, atol=1e-9) and (0 <= t).all() and (t < len(D)).all(),
              f"max |dd| {np.abs(d - d_voll).max():.1e}")
        gleich = 0
        for p in P[1500:1560]:
            Qd = _naechster_punkt_dreieck(p[None], D)[0]
            voll = np.flatnonzero(np.linalg.norm(Qd - p, axis=1) <= 4.0 * (1 + 1e-9))
            gleich += int(np.array_equal(voll, index.beruehrende(p, 4.0)))
        check(f"{name}: beruehrende Facetten (r = 4) wie die volle Rechnung an 60 Punkten nahe der Huelle", gleich == 60, f"{gleich}/60")
    w_np = _windungszahl_np(P, D)
    w = windungszahl(P, D)
    check(f"Windungszahl: {'numba' if stlmod._NUMBA else 'numpy'}-Fassung gegen numpy blockweise < 1e-11 (auch genau auf Facetten)",
          np.abs(w - w_np).max() < 1e-11, f"max {np.abs(w - w_np).max():.1e}, numba {stlmod._NUMBA}")


def test_kern_stl():
    """Kurzfassung fuer die Kernsuite (ohne Lame): Windungszahl, Abstand, exaktes Wuerfelvolumen, Suchbaum."""
    test_lesen_und_windungszahl()
    test_abstand_und_ebenen()
    test_suchbaum()


if __name__ == "__main__":
    sys.exit(lauf([test_lesen_und_windungszahl, test_abstand_und_ebenen, test_suchbaum, test_volumen_und_quadratur, test_lame_aus_stl]))
