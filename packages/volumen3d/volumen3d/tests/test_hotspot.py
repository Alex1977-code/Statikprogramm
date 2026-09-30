"""Strukturspannung am Nahtuebergang nach IIW Typ a (Vorgabe 11.2, Plan TP 5 B3, Theorie 11.13).

Aufruf: python -m volumen3d.tests.test_hotspot   (~2 min)
Modell: T-Stoss aus Grundblech t 10 (x 0..200, y 0..50, z -10..0), Querblech t_a 10 bei x 95..105 bis z 60 und
beidseitigen Kehlnaehten mit Schenkel 8; Nahtuebergaenge bei x 113 (rechts) und x 87 (links) auf z = 0.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402

from volumen3d.tests._pruef import check, lauf  # noqa: E402

T_BLECH, SCHENKEL, E, NU = 10.0, 8.0, 210000.0, 0.3
X_RECHTS, X_LINKS = 105.0 + SCHENKEL, 95.0 - SCHENKEL
Y_NAHT = np.arange(5.0, 46.0, 5.0)


def t_stoss():
    from volumen3d.geometry.csg import aus_params
    return aus_params({"csg": {"typ": "vereinigung", "teile": [
        {"typ": "quader", "min": [0, 0, -T_BLECH], "max": [200, 50, 0], "name": "grundblech"},
        {"typ": "quader", "min": [95, 0, 0], "max": [105, 50, 60], "name": "querblech"},
        {"typ": "schnitt", "teile": [
            {"typ": "quader", "min": [105, 0, 0], "max": [X_RECHTS, 50, SCHENKEL], "name": "naht_rechts"},
            {"typ": "halbraum", "punkt": [X_RECHTS, 0, 0], "normale": [1, 0, 1], "name": "nahtflaeche_rechts"}]},
        {"typ": "schnitt", "teile": [
            {"typ": "quader", "min": [X_LINKS, 0, 0], "max": [95, 50, SCHENKEL], "name": "naht_links"},
            {"typ": "halbraum", "punkt": [X_LINKS, 0, 0], "normale": [-1, 0, 1], "name": "nahtflaeche_links"}]}]}})


def nahtlinie(x):
    return np.stack([np.full(len(Y_NAHT), x), Y_NAHT, np.zeros(len(Y_NAHT))], axis=1)


def test_geometrie_und_lineares_feld():
    """Synthetisches Spannungsfeld, linear in x (dazu Komponenten, die d.S.d nicht sehen duerfen): an beiden
    Nahtuebergaengen Blechseite richtig (d = +x rechts, -x links), Referenzpunkte bei 0,4 t und 1,0 t auf der
    Blechoberflaeche, sigma_hs = sigma_xx am Uebergang auf 1e-12. Werkstofftiefe: Blech 10 mm, unter der
    Nahtoberflaeche (45 Grad) laengs der Innennormalen bis zur Blechunterseite (0,7 t/sqrt2 + t) * sqrt2 = 21,1 mm."""
    from volumen3d.postprocess.hotspot import nahtgeometrie, strukturspannungen
    geo = t_stoss()

    def sigma(P):
        P = np.asarray(P, float).reshape(-1, 3)
        S = np.zeros((len(P), 6))
        S[:, 0] = 50.0 + 0.8 * P[:, 0]
        S[:, 1] = 30.0 + 0.2 * P[:, 1]              # sigma_yy: parallel zur Naht, geht nicht ein
        S[:, 4] = 7.0                                # tau_yz: geht nicht ein
        return S
    fehler, richtung, lage, tiefe_blech, tiefe_naht = 0.0, True, 0.0, 0.0, 0.0
    for x, vz in ((X_RECHTS, 1.0), (X_LINKS, -1.0)):
        q = nahtgeometrie(geo, nahtlinie(x), T_BLECH)
        erg = strukturspannungen(q, sigma, 0.0)
        richtung &= all(p.ok for p in q) and all(np.allclose(p.richtung, [vz, 0, 0], atol=1e-9) for p in q)
        for p in q:
            soll = p.position + np.outer([0.4, 1.0], [vz * T_BLECH, 0, 0])
            lage = max(lage, float(np.abs(p.referenz - soll).max()))
            tb, tn = sorted(p.tiefen, key=lambda d: abs(d - T_BLECH))
            tiefe_blech, tiefe_naht = max(tiefe_blech, abs(tb - T_BLECH)), max(tiefe_naht, abs(tn - (0.7 * T_BLECH / np.sqrt(2) + T_BLECH) * np.sqrt(2)))
        fehler = max(fehler, max(abs(h - (50.0 + 0.8 * x)) / (50.0 + 0.8 * x) for _, h, _, _ in erg))
    check(f"T-Stoss, {2 * len(Y_NAHT)} Nahtpunkte: Blechseite richtig (d = +x rechts, -x links), Referenzpunkte auf 1e-9 mm, "
          f"sigma_hs = sigma_xx am Uebergang (< 1e-12)", richtung and lage < 1e-9 and fehler < 1e-12,
          f"Lage {lage:.1e} mm, Fehler {fehler:.1e}")
    check("Werkstofftiefe unter dem Blech = t, unter der Nahtoberflaeche 21,1 mm (je < 0,01 mm)", tiefe_blech < 0.01 and tiefe_naht < 0.01,
          f"Abweichung Blech {tiefe_blech:.1e} mm, Naht {tiefe_naht:.1e} mm")


def test_uneindeutig():
    """Kein Wert statt eines geratenen: (1) mitten in einer ebenen Oberflaeche schneidet der Kreis die Flaeche in zwei
    gegenlaeufigen Aesten - kein Knick, also kein Nahtuebergang; (2) liegt die Linie im Werkstoff (x 150, z -5), gibt es
    keinen Oberflaechenast."""
    from volumen3d.postprocess.hotspot import nahtgeometrie
    geo = t_stoss()
    flach = nahtgeometrie(geo, np.array([[150.0, 10, 0], [150.0, 20, 0]]), T_BLECH)
    innen = nahtgeometrie(geo, np.array([[150.0, 10, -5], [150.0, 20, -5]]), T_BLECH)
    check("Punkt in ebener Oberflaeche: kein Wert, Warnung 'ohne Knick'; Punkt im Werkstoff: kein Wert, Warnung mit Zahl der Aeste",
          not any(q.ok for q in flach + innen) and all("ohne Knick" in q.warnung for q in flach)
          and all("Oberflaechenaeste" in q.warnung for q in innen), f"{flach[0].warnung} / {innen[0].warnung}")


def _problem(h, p=3, verfeinern=True):
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    v = None
    if verfeinern:
        v = Verfeinerung(bereiche=((np.array([X_RECHTS, 25.0, 0.0]), 2.0 * T_BLECH, h / 4),
                                   (np.array([X_LINKS, 25.0, 0.0]), 2.0 * T_BLECH, h / 4)))
    return FcmProblem(t_stoss(), h=h, p=p, werkstoff=Werkstoff(E, NU), verfeinerung=v)


def test_exaktes_feld():
    """Finite Zellen, p 3: u = (c x^2/2, 0, 0) mit konstanter Volumenkraft b = -(lambda + 2 mu) c e_x ist
    Gleichgewichtsloesung (sigma_xx = (lambda + 2 mu) c x, sigma_yy = sigma_zz = lambda c x) und im Ansatzraum; mit
    Dirichlet auf der ganzen Oberflaeche rechnet die FCM es exakt. sigma_hs muss sigma_xx am Uebergang treffen (< 1e-6),
    roh wie geglaettet (L2-Projektion eines linearen Felds ist exakt)."""
    from volumen3d.postprocess.hotspot import nahtgeometrie, strukturspannungen
    lam, mu = E * NU / ((1 + NU) * (1 - 2 * NU)), E / (2 * (1 + NU))
    c = 1e-5
    pr = _problem(20.0, verfeinern=False)
    pr.verschiebungsrand("alles", None, projektion="voll")
    pr.volumenlast(np.array([-(lam + 2 * mu) * c, 0.0, 0.0]))

    def u(P):
        P = np.asarray(P, float).reshape(-1, 3)
        return np.stack([0.5 * c * P[:, 0] ** 2, np.zeros(len(P)), np.zeros(len(P))], axis=1)
    t = time.perf_counter()
    U = pr.loesen({"alles": u})[:, 0]
    aus = pr.auswertung(U)
    f = {}
    for art, gl in (("roh", False), ("geglaettet", True)):
        fe = 0.0
        for x in (X_RECHTS, X_LINKS):
            erg = strukturspannungen(nahtgeometrie(pr.geometrie, nahtlinie(x), T_BLECH),
                                     lambda P: aus.spannung(P, geglaettet=gl), 1e-7 * pr.gitter.h)
            soll = (lam + 2 * mu) * c * x
            fe = max(fe, max(abs(hs - soll) / soll for _, hs, _, _ in erg))
        f[art] = fe
    check("Exaktes Feld, p 3: sigma_hs = (lambda + 2 mu) c x_Uebergang an beiden Naehten, roh und geglaettet (< 1e-6)",
          f["roh"] < 1e-6 and f["geglaettet"] < 1e-6, f"roh {f['roh']:.1e}, geglaettet {f['geglaettet']:.1e}, {time.perf_counter() - t:.1f} s")


def _zug(h):
    """T-Stoss unter Zug sigma_n = 100 N/mm2 an x = 200, Symmetrie x = 0 und y = 0 (Normalprojektion); frei bleibt
    nur die Verschiebung in z (wie bei der Kirsch-Scheibe, der Direktloeser legt sie fest)."""
    pr = _problem(h)
    o = pr.oberflaeche
    P = o.punkte
    pr.verschiebungsrand("sym_x", None, projektion="normal", quadratur=o.auswahl(np.abs(P[:, 0]) < 1e-6))
    pr.verschiebungsrand("sym_y", None, projektion="normal", quadratur=o.auswahl(np.abs(P[:, 1]) < 1e-6))
    pr.traktion(None, np.array([100.0, 0, 0]), quadratur=o.auswahl(np.abs(P[:, 0] - 200.0) < 1e-6))
    return pr


def _linearisiert(aus, x, y=25.0, n=24):
    """Ueber die Blechdicke linearisierte Strukturspannung an der Oberseite (Membran + Biegung, Vergleichsgroesse)."""
    from volumen3d.fcm.basis import gauss_1d
    xi, w = gauss_1d(n)
    z = -0.5 * T_BLECH * (1 - xi)                                 # z von -t bis 0
    S = aus.spannung(np.stack([np.full(n, x), np.full(n, y), z], axis=1))[:, 0]
    wz = 0.5 * T_BLECH * w
    s_m = float(wz @ S) / T_BLECH
    s_b = 6.0 * float(wz @ (S * (z + 0.5 * T_BLECH))) / T_BLECH ** 2
    return s_m + s_b


def test_zug_handrechnung():
    """T-Stoss mit nicht tragenden Kehlnaehten unter Zug, Handrechnung sigma_n = F/(b t) = 100 N/mm2. Geprueft (Regel
    vorher im Plan): fern der Naht (x 180, Ober- und Unterseite) sigma_xx = sigma_n auf 1 %; sigma_hs an allen Punkten
    beider Nahtuebergaenge zwischen sigma_n und 1,5 sigma_n; sigma_hs zwischen h 10 und h 5 um weniger als 3 % anders.
    Zum Vergleich ohne Kriterium: die ueber die Dicke linearisierte Strukturspannung im Uebergangsschnitt."""
    from volumen3d.postprocess.hotspot import nahtgeometrie, strukturspannungen
    werte = {}
    for h in (10.0, 5.0):
        t = time.perf_counter()
        pr = _zug(h)
        U = pr.loesen({})[:, 0]
        aus = pr.auswertung(U)
        fern = aus.spannung(np.array([[180.0, 25.0, -1e-6], [180.0, 25.0, -T_BLECH + 1e-6]]), geglaettet=True)[:, 0]
        hs = {}
        for name, x in (("rechts", X_RECHTS), ("links", X_LINKS)):
            erg = strukturspannungen(nahtgeometrie(pr.geometrie, nahtlinie(x), T_BLECH),
                                     lambda P: aus.spannung(P, geglaettet=True), 1e-7 * pr.gitter.h)
            hs[name] = np.array([v for _, v, _, _ in erg])
        werte[h] = (fern, hs, _linearisiert(aus, X_RECHTS), pr.gitter.n_dof, time.perf_counter() - t)
    f10, hs10, lin10, n10, t10 = werte[10.0]
    f5, hs5, lin5, n5, t5 = werte[5.0]
    alle5 = np.concatenate([hs5["rechts"], hs5["links"]])
    alle10 = np.concatenate([hs10["rechts"], hs10["links"]])
    check("Fern der Naht (x 180) sigma_xx = sigma_n auf 1 % an Ober- und Unterseite, h 10 und h 5",
          np.abs(f10 / 100.0 - 1).max() < 0.01 and np.abs(f5 / 100.0 - 1).max() < 0.01, f"h 10 {f10}, h 5 {f5}")
    check(f"sigma_hs an allen {len(alle5)} Nahtpunkten zwischen sigma_n und 1,5 sigma_n (h 10 und h 5)",
          len(alle5) == 2 * len(Y_NAHT) and len(alle10) == len(alle5) and alle5.min() >= 100.0 and alle5.max() <= 150.0
          and alle10.min() >= 100.0 and alle10.max() <= 150.0,
          f"h 10: {alle10.min():.2f} bis {alle10.max():.2f}, h 5: {alle5.min():.2f} bis {alle5.max():.2f} N/mm2")
    d = float(np.abs(alle5 / alle10 - 1).max())
    check("sigma_hs zwischen h 10 und h 5 um weniger als 3 % anders", d < 0.03,
          f"groesste Aenderung {d * 100:.2f} %; Mittel rechts {hs10['rechts'].mean():.2f} -> {hs5['rechts'].mean():.2f}, links "
          f"{hs10['links'].mean():.2f} -> {hs5['links'].mean():.2f}; linearisiert im Schnitt x 113 (y 25): {lin10:.2f} -> {lin5:.2f}; "
          f"{n10} / {n5} FHG, {t10:.0f} / {t5:.0f} s")


if __name__ == "__main__":
    sys.exit(lauf([test_geometrie_und_lineares_feld, test_uneindeutig, test_exaktes_feld, test_zug_handrechnung]))
