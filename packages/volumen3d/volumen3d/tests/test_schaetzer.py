"""Teilprojekt 6a Phase 1: residuenbasierter Fehlerschaetzer (fcm/schaetzer.py), Plan 2026-10-06-tp6a-phase1-schaetzer.md.

Aufruf: python -m volumen3d.tests.test_schaetzer
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402


def test_hesse():
    """Hesse-Matrizen der Basis gegen den zentralen Differenzenquotienten der Gradienten; 1D geschlossen: N_j'' = sqrt((2j-1)/2) P'_{j-1}."""
    from volumen3d.fcm.basis import basis_3d, basis_3d_hesse, legendre_1d_d2
    rng = np.random.default_rng(3)
    xi = rng.uniform(-0.9, 0.9, (40, 3))
    for p in (1, 2, 3, 4):
        H = basis_3d_hesse(p, xi)
        d = 1e-5
        fd = np.empty_like(H)
        for b in range(3):
            e = np.zeros(3)
            e[b] = d
            _, dp = basis_3d(p, xi + e)
            _, dm = basis_3d(p, xi - e)
            fd[:, :, :, b] = (dp - dm) / (2 * d)
        rel = float(np.abs(H - fd).max() / max(float(np.abs(H).max()), 1.0))
        check(f"p {p}: Hesse-Matrizen gegen Differenzenquotient der Gradienten ({rel:.1e} < 1e-7), symmetrisch",
              rel < 1e-7 and np.allclose(H, H.transpose(0, 1, 3, 2)))
    x = rng.uniform(-1, 1, 20)
    d2 = legendre_1d_d2(4, x)
    check("1D geschlossen: N_0'' = N_1'' = 0, N_2'' = sqrt(3/2), N_3'' = sqrt(5/2) 3x, N_4'' = sqrt(7/2) (15x^2 - 3)/2",
          not d2[:, :2].any() and np.allclose(d2[:, 2], np.sqrt(1.5)) and np.allclose(d2[:, 3], np.sqrt(2.5) * 3 * x)
          and np.allclose(d2[:, 4], np.sqrt(3.5) * (15 * x ** 2 - 3) / 2))


def _wuerfel(p=1, h=50.0):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"}})
    return FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(210000.0, 0.3))


def test_lasten_aufgezeichnet():
    """Der Schaetzer braucht die Soll-Traktion je Oberflaechenpunkt und die Volumenlast; das Problem zeichnet sie neben dem Lastvektor auf."""
    pr = _wuerfel()
    pr.druck("q", 5.0)
    pr.volumenlast([0.0, 0.0, -7.85e-5])
    fq, T = pr.flaechenlasten[-1]
    check("druck: aufgezeichnete Traktion = -p n an allen Punkten, Volumenlast aufgezeichnet",
          len(pr.flaechenlasten) == 1 and np.allclose(T, -5.0 * fq.normalen) and len(fq.punkte) == len(pr.oberflaeche.punkte)
          and len(pr.volumenlasten) == 1 and np.allclose(pr.volumenlasten[0], [0.0, 0.0, -7.85e-5]))


def test_flaechen_paare():
    """Jede Flaeche zwischen zwei aktiven Zellen genau einmal, von der feineren Zelle aus; unabhaengige Gegenprobe ueber die Zellboxen (alle Paare mit
    gemeinsamer Flaeche positiven Inhalts)."""
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.fcm.schaetzer import flaechen_paare
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"}})
    pr = FcmProblem(g, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3), verfeinerung=Verfeinerung(bereiche=((np.zeros(3), 30.0, 12.5),)))
    G = pr.gitter
    paare = flaechen_paare(G)
    lo, hi = G.zellbox(np.arange(len(G.ijk)))
    tol = 1e-9 * G.h
    brute = set()
    for c in range(len(G.ijk)):
        for k in range(c + 1, len(G.ijk)):
            for a in range(3):
                b, d = [x for x in range(3) if x != a]
                beruehrt = abs(hi[c, a] - lo[k, a]) < tol or abs(hi[k, a] - lo[c, a]) < tol
                ueber = all(min(hi[c, x], hi[k, x]) - max(lo[c, x], lo[k, x]) > tol for x in (b, d))
                if beruehrt and ueber:
                    brute.add((c, k))
    gefunden = {(min(c, k), max(c, k)) for c, k, _, _ in paare}
    feiner = all(G.ebene[c] >= G.ebene[k] for c, k, _, _ in paare)
    check(f"flaechen_paare: {len(paare)} Paare, gleich der Gegenprobe ueber die Boxen ({len(brute)}), keine doppelt, immer von der feineren Zelle aus",
          gefunden == brute and len(paare) == len(gefunden) and feiner and len(set(G.ebene)) > 1)


def test_flaechen_punkte():
    """Werkstoffanteil einer Zellflaeche: ganz im Werkstoff exakt die Flaeche; schraeg geschnitten auf erste Ordnung gegen das exakt geclippte Polygon."""
    from volumen3d.fcm.schaetzer import flaechen_paare, flaechen_punkte
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.polyeder import polygon_clippen
    pkt, nrm = np.array([50.0, 50.0, 50.0]), np.array([1.0, 0.5, 0.0])
    g = aus_params({"csg": {"typ": "schnitt", "teile": [{"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "q"},
                                                         {"typ": "halbraum", "punkt": list(pkt), "normale": list(nrm), "name": "s"}]}})
    G = FcmProblem(g, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3)).gitter
    voll = schraeg = 0
    fehler = 0.0
    for c, k, achse, seite in flaechen_paare(G):
        lo, hi = G.zellbox(int(c))
        a, b = [d for d in range(3) if d != achse]
        flaeche = (hi[a] - lo[a]) * (hi[b] - lo[b])
        ebene = hi[achse] if seite > 0 else lo[achse]
        ecken = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float)
        Q = np.empty((4, 3))
        Q[:, achse] = ebene
        Q[:, a] = lo[a] + ecken[:, 0] * (hi[a] - lo[a])
        Q[:, b] = lo[b] + ecken[:, 1] * (hi[b] - lo[b])
        # exakter Werkstoffanteil: Flaeche gegen den Halbraum und die sechs Quaderseiten clippen (polygon_clippen behaelt (x - p).n <= 0)
        R, _ = polygon_clippen(Q, pkt, nrm / np.linalg.norm(nrm), 1e-12)
        for x0, n0 in ((np.array([0.0, 0, 0]), np.array([-1.0, 0, 0])), (np.array([100.0, 0, 0]), np.array([1.0, 0, 0])),
                       (np.array([0.0, 0, 0]), np.array([0, -1.0, 0])), (np.array([0, 100.0, 0]), np.array([0, 1.0, 0])),
                       (np.array([0, 0, 0.0]), np.array([0, 0, -1.0])), (np.array([0, 0, 100.0]), np.array([0, 0, 1.0]))):
            if len(R) >= 3:
                R, _ = polygon_clippen(R, x0, n0, 1e-12)
        exakt = 0.5 * float(np.linalg.norm(np.cross(R[1:-1] - R[0], R[2:] - R[0]).sum(axis=0))) if len(R) >= 3 else 0.0
        P, W = flaechen_punkte(G, c, achse, seite, 2, tiefe=2)
        if abs(exakt - flaeche) < 1e-9 * flaeche:
            voll += 1
            fehler = max(fehler, abs(float(W.sum()) - flaeche) / flaeche)
        elif exakt > 0:
            # erste Ordnung: eine Gerade schneidet hoechstens 2 * 2^tiefe der 2^tiefe x 2^tiefe Unterquadrate, jedes irrt hoechstens um seine Flaeche
            schraeg += 1
            if abs(float(W.sum()) - exakt) > 2.0 * flaeche / 2 ** 2:
                fehler = max(fehler, 1.0)
    check(f"flaechen_punkte: {voll} Flaechen ganz im Werkstoff exakt ({fehler:.1e} < 1e-12), {schraeg} geschnittene innerhalb der Schranke erster Ordnung",
          voll > 0 and schraeg > 0 and fehler < 1e-12)


def _energie(pr, sig):
    from volumen3d.fcm.schaetzer import energiefehler
    return energiefehler(pr, np.zeros(pr.gitter.n_dof), sig)[1]


def test_konsistenz():
    """Felder im Ansatzraum ergeben eta auf Rundungsniveau (Regel 3): Zellresiduum, Spruenge und Randreste verschwinden fuer die exakte Loesung. Schranken wie
    test_patch_hoeherer_ordnung: 1e-8 bei p 2, 1e-7 bei p 3 (die Zwangsmatrix gibt Polynome bei p 3 nur auf rund 1e-9 wieder, Theorie 11.21 H4)."""
    from volumen3d.fcm.schaetzer import schaetzen
    from volumen3d.tests import test_patch as T
    pr = T._problem(2, 1e-8)
    s0 = T.sigma_exakt()
    U = pr.loesen({"alles": T.u_exakt})[:, 0]
    eta = schaetzen(pr, U, {"alles": T.u_exakt}).gesamt
    ref = _energie(pr, lambda P: np.broadcast_to(s0, (len(P), 6)))
    check(f"Patch-Koerper p 2, lineares Feld: eta / ||u||_E = {eta / ref:.1e} (< 1e-8)", eta / ref < 1e-8)
    for p, k in ((2, 2), (3, 3)):
        u, sig, f, _ = T._polynomfeld(k)
        _, _, pr = T._polynomfehler(p, k)
        U = pr.loesen({"alles": u}, zusatzlasten=[T._lastvektor(pr, f)])[:, 0]
        eta = schaetzen(pr, U, {"alles": u}, volumenlast=f).gesamt
        ref = _energie(pr, sig)
        schranke = 1e-8 if p == 2 else 1e-7
        check(f"Patch-Koerper p {p}, Feld vom Grad {k} mit Volumenlast: eta / ||u||_E = {eta / ref:.1e} (< {schranke:.0e})", eta / ref < schranke)


def _lame_sigma(P):
    from volumen3d.tests import test_lame as L
    P = np.asarray(P, float).reshape(-1, 3)
    r = np.hypot(P[:, 0], P[:, 1])
    c, s = P[:, 0] / r, P[:, 1] / r
    sr, sphi = L._lame(r)
    o = np.zeros(len(P))
    return np.stack([sr * c * c + sphi * s * s, sr * s * s + sphi * c * c, L.NU * (sr + sphi), (sr - sphi) * s * c, o, o], axis=1)


def test_lame():
    """Lame p 2, h 20 und h 10: eta faellt, Effektivitaetsindex gegen die exakte Loesung in [0,1; 10] und zwischen beiden Gittern um hoechstens den Faktor 3."""
    from volumen3d.fcm.schaetzer import energiefehler, schaetzen
    from volumen3d.tests import test_lame as L
    werte = []
    for h in (20.0, 10.0):
        pr, aus = L._rechnen(2, h)
        eta = schaetzen(pr, aus.U).gesamt
        e = energiefehler(pr, aus.U, _lame_sigma)[1]
        werte.append((h, eta, e, eta / e))
    (_, eta1, e1, t1), (_, eta2, e2, t2) = werte
    check(f"Lame p 2: eta {eta1:.3e} -> {eta2:.3e}, ||e||_E {e1:.3e} -> {e2:.3e}, Effektivitaet {t1:.2f} / {t2:.2f}",
          eta2 < eta1 and e2 < e1 and all(0.1 < t < 10.0 for t in (t1, t2)) and max(t1, t2) / min(t1, t2) < 3.0)


def test_doerfler():
    """Doerfler: kleinste Menge der groessten Indikatoren, deren Summe mindestens theta der Gesamtsumme traegt."""
    from volumen3d.fcm.schaetzer import doerfler
    check("Doerfler theta 0,5 auf [1, 4, 2, 3]: Zellen 1 und 3 (4 + 3 >= 5); theta 1: alle; leer bei Summe 0",
          list(doerfler(np.array([1.0, 4.0, 2.0, 3.0]), 0.5)) == [1, 3] and list(doerfler(np.array([1.0, 4.0, 2.0, 3.0]), 1.0)) == [0, 1, 2, 3]
          and len(doerfler(np.zeros(3), 0.5)) == 0)


def test_verfeinerung_nach():
    """Die markierte Zelle wird geteilt: im neuen Gitter liegen in ihrer Box acht Blaetter der naechsten Ebene. Eine Zelle ganz im Werkstoff, damit kein Kind
    als OUTSIDE wegfaellt."""
    from volumen3d.fcm.gitter import INSIDE
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.fcm.schaetzer import verfeinerung_nach
    pr = _wuerfel(p=1, h=25.0)                      # bei h 50 ist keine Zelle INSIDE (Kugeltest der Klassifikation ueber die halbe Raumdiagonale)
    c = int(np.flatnonzero((pr.gitter.ebene == 0) & (pr.gitter.klasse == INSIDE))[0])
    lo, hi = pr.gitter.zellbox(c)
    v = verfeinerung_nach(pr.gitter, pr.verfeinerung, [c])
    G2 = FcmProblem(pr.geometrie, h=25.0, p=1, werkstoff=Werkstoff(210000.0, 0.3), verfeinerung=v).gitter
    lo2, hi2 = G2.zellbox(np.arange(len(G2.ijk)))
    m = 0.5 * (lo2 + hi2)
    drin = np.flatnonzero(((m > lo) & (m < hi)).all(axis=1))
    check(f"verfeinerung_nach: Zelle {c} geteilt, {len(drin)} Blaetter der Ebene 1 in ihrer Box", len(drin) == 8 and (G2.ebene[drin] == 1).all())


def test_aggregate_ergaenzen():
    """Eine markierte aggregierte Zelle zieht ihre Wurzel und alle Zellen derselben Wurzel nach sich; eine markierte Wurzel alle an ihr haengenden Zellen; ohne
    Aggregation bleibt die Menge, wie sie ist."""
    from volumen3d.fcm.schaetzer import aggregate_ergaenzen
    from volumen3d.tests import test_lame as L
    pr, _ = L._rechnen(2, 20.0)
    w = pr.aggregation.wurzel
    c = int(np.flatnonzero(w >= 0)[0])
    r = int(w[c])
    gruppe = set(np.flatnonzero(w == r).tolist()) | {r}
    a = set(aggregate_ergaenzen(pr, [c]).tolist())
    b = set(aggregate_ergaenzen(pr, [r]).tolist())
    ohne = [int(x) for x in aggregate_ergaenzen(types.SimpleNamespace(aggregation=None), [5, 3, 5])]   # Problem ohne Aggregation
    check(f"aggregate_ergaenzen: Zelle {c} mit Wurzel {r} -> Aggregat aus {len(gruppe)} Zellen; Wurzel allein ebenso; ohne Aggregation bleibt die Menge {ohne}",
          a == gruppe and b == gruppe and len(gruppe) > 1 and ohne == [3, 5])


def test_teilen_ohne_fehlerzunahme():
    """O21, Regel B4: ein Doerfler-Schritt an Lame h 20 p 2 erhoeht den wahren Fehler nicht, wenn ganze Aggregate geteilt werden. Zum Vergleich ohne die Kur: dort
    steigt er (Phase 1: 2,049 -> 2,184), sonst waere die Pruefung leer."""
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.fcm.schaetzer import aggregate_ergaenzen, doerfler, energiefehler, schaetzen, verfeinerung_nach
    from volumen3d.tests import test_lame as L
    pr0, aus0 = L._rechnen(2, 20.0)
    e0 = energiefehler(pr0, aus0.U, _lame_sigma)[1]
    mark = doerfler(schaetzen(pr0, aus0.U).zelle ** 2, 0.5)
    werte = {}
    for name, zellen in (("mit Kur", aggregate_ergaenzen(pr0, mark)), ("ohne Kur", mark)):
        pr = FcmProblem(L._geometrie(), h=20.0, p=2, werkstoff=Werkstoff(L.E, L.NU), verfeinerung=verfeinerung_nach(pr0.gitter, pr0.verfeinerung, zellen))
        for s in ("sym_x", "sym_y", "sym_z0", "sym_z1"):
            pr.verschiebungsrand(s, s, projektion="normal")
        pr.druck("innen", L.PI)
        werte[name] = (energiefehler(pr, pr.loesen({})[:, 0], _lame_sigma)[1], len(zellen))
    check(f"Lame h 20 p 2, ein Doerfler-Schritt: ||e||_E {e0:.4f} -> mit Kur {werte['mit Kur'][0]:.4f} ({werte['mit Kur'][1]} Zellen geteilt), "
          f"ohne Kur {werte['ohne Kur'][0]:.4f} ({werte['ohne Kur'][1]} Zellen)", werte["mit Kur"][0] <= e0 and werte["ohne Kur"][0] > e0)


if __name__ == "__main__":
    sys.exit(lauf([test_hesse, test_lasten_aufgezeichnet, test_flaechen_paare, test_flaechen_punkte, test_konsistenz, test_lame, test_doerfler,
                   test_verfeinerung_nach, test_aggregate_ergaenzen, test_teilen_ohne_fehlerzunahme]))
