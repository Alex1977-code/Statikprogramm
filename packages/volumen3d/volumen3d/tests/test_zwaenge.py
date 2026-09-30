"""U2: Zwangsaufloeser - haengende Flaechen/Kanten/Ecken, Spurabbildung, Patch-Test auf
verfeinerten Gittern (mit Aggregation), Vorrang der haengenden Zwaenge.

Aufruf: python -m volumen3d.tests.test_zwaenge
"""
from __future__ import annotations

import sys
import time

import numpy as np

from volumen3d.tests._pruef import check, lauf
from volumen3d.tests.test_patch import A, B0, E, NU, sigma_exakt, u_exakt


def test_zaehlung_und_spur():
    from volumen3d.fcm.gitter import Gitter, Verfeinerung
    from volumen3d.fcm.zwaenge import Zwaenge
    from volumen3d.fcm.basis import basis_3d
    from volumen3d.geometry.csg import aus_params
    w = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [40, 40, 40]}})
    G = Gitter(w, h=20.0, polster=0.0, verfeinerung=Verfeinerung(bereiche=((np.array([0.0, 0, 0]), 5.0, 10.0),)))
    for p in (1, 2, 3):
        G.moden_nummerieren(p)
        Z = Zwaenge(G)
        st = Z.statistik
        check(f"p={p}: eine geteilte Wurzelzelle -> 12 haengende Flaechen, keine losen Kanten/Ecken (Flaechen binden sie mit)",
              st["haengende_flaechen"] == 12 and st["haengende_kanten"] == 0 and st["haengende_ecken"] == 0, str(st))
        # Spur: zufaelliges Polynom vom Grad p auf der groben Zelle, per Zwang auf die feinen Zellen uebertragen,
        # muss an beliebigen Punkten der haengenden Flaeche mit dem groben Polynom uebereinstimmen
        rng = np.random.default_rng(p)
        u = np.zeros(G.n_dof)
        grob = np.flatnonzero(G.ebene == 0)
        for c in grob:
            u[G.zell_dofs(c)] = rng.normal(size=3 * (p + 1) ** 3) if c == grob[0] else u[G.zell_dofs(c)]
        # alle groben Zellen mit demselben zufaelligen Koeffizientensatz je Mode (stetig, da geteilte Moden)
        koeff = rng.normal(size=G.n_dof)
        frei = np.ones(G.n_dof, bool)
        for mode in Z.roh:
            frei[3 * mode:3 * mode + 3] = False
        # Zwang anwenden: U = C U_red mit U_red = freie Eintraege von koeff
        U = np.asarray(Z.C @ koeff[frei])
        # Punkte auf der haengenden Flaeche x = 20 zwischen Kind (1,0,0) [Ebene 1] und Wurzel (1,0,0) [Ebene 0]
        kind = int(np.flatnonzero((G.ebene == 1) & (G.ijk == [1, 0, 0]).all(axis=1))[0])
        wurzel = int(np.flatnonzero((G.ebene == 0) & (G.ijk == [1, 0, 0]).all(axis=1))[0])
        P = np.stack([np.full(25, 20.0), rng.uniform(0, 10, 25), rng.uniform(0, 10, 25)], axis=1)
        def wert(c):
            N, _ = basis_3d(p, G.lokal(P, np.full(len(P), c)))
            Uc = U[(3 * G.zell_moden[c][:, None] + np.arange(3)).ravel()].reshape(-1, 3)
            return N @ Uc
        check(f"p={p}: Spur des feinen Kindes auf der haengenden Flaeche = Spur der groben Zelle (1e-12)",
              np.abs(wert(kind) - wert(wurzel)).max() < 1e-12 * max(1.0, np.abs(wert(wurzel)).max()), f"{np.abs(wert(kind) - wert(wurzel)).max():.1e}")


def _problem(p, verfeinerung, h=20.0, extra=()):
    from volumen3d.fcm.problem import FcmProblem, Werkstoff
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "schnitt", "teile": [
        {"typ": "quader", "min": [0, 0, 0], "max": [100, 100, 100], "name": "quader"},
        {"typ": "halbraum", "punkt": [60, 50, 50], "normale": [1, 2, 3], "name": "s1"},
        {"typ": "halbraum", "punkt": [30, 40, 70], "normale": [-2, 1, 1.5], "name": "s2"}] + list(extra)}})
    pr = FcmProblem(g, h=h, p=p, werkstoff=Werkstoff(E, NU), verfeinerung=verfeinerung)
    pr.verschiebungsrand("alles", None, projektion="voll")
    return pr


def _fehler(pr, U):
    aus = pr.auswertung(U)
    rng = np.random.default_rng(4)
    P = rng.uniform(0, 100, (6000, 3))
    P = P[pr.geometrie.abstand(P) < -0.5][:2000]
    eu = np.abs(aus.verschiebung(P) - u_exakt(P)).max() / np.abs(u_exakt(P)).max()
    es = np.abs(aus.spannung(P) - sigma_exakt()).max() / np.abs(sigma_exakt()).max()
    Po = pr.oberflaeche.punkte - 1e-6 * pr.gitter.h * pr.oberflaeche.normalen
    eo = np.abs(aus.spannung(Po[::5]) - sigma_exakt()).max() / np.abs(sigma_exakt()).max()
    return eu, es, eo


def test_patch_verfeinert():
    from volumen3d.fcm.gitter import Verfeinerung
    faelle = [("Schnittzellen eine Ebene", Verfeinerung(schnitt_ebenen=1)),
              ("Bereich Ebene 2 an einer Ecke", Verfeinerung(bereiche=((np.array([100.0, 100, 0]), 25.0, 5.0),))),
              ("Schnittzellen + Bereich + duenne Waende", Verfeinerung(schnitt_ebenen=1, bereiche=((np.array([0.0, 0, 100]), 30.0, 5.0),), duenne_waende=True))]
    for name, v in faelle:
        for p in (1, 2, 3):
            t = time.perf_counter()
            pr = _problem(p, v)
            U = pr.loesen({"alles": u_exakt})[:, 0]
            eu, es, eo = _fehler(pr, U)
            zw = pr.protokoll["zwaenge"]
            check(f"{name}, p={p}: u, sigma < 1e-6 mit haengenden Freiheitsgraden, keine Zwangszyklen",
                  eu < 1e-6 and es < 1e-6 and eo < 1e-6 and zw["zyklen_frei"] == 0,
                  f"u {eu:.1e}, sigma {es:.1e}, Rand {eo:.1e}; Ebenen {pr.protokoll['ebenen']}, haengend F/K/E "
                  f"{zw['haengende_flaechen']}/{zw['haengende_kanten']}/{zw['haengende_ecken']}, Moden haengend {zw['moden_haengend']}, "
                  f"aggregiert {zw['moden_aggregiert']}, frei {zw['moden_frei']} von {pr.gitter.n_moden}, Ketten {zw['kettenlaenge']}, "
                  f"Wurzelteilungen {pr.wurzel_teilungen}, {time.perf_counter() - t:.1f} s")
            if p == 2 and name.startswith("Schnittzellen +"):
                check("  dabei kommen haengende Kanten oder Ecken ohne Flaeche vor (Vorrangregel geprueft)",
                      zw["haengende_kanten"] + zw["haengende_ecken"] > 0, str(zw))
                # 27.09.2026: hier hatten 21 schlechte Zellen eine feinere Wurzel und geteilte Eckmoden wurden ueber
                # die Wurzel der feinen Zelle gebunden -> 53 Selbstbezuege. Jetzt: keine Wurzel feiner als ihre Zelle
                # (Zellen ohne solche Wurzel wuerden geteilt), Eigentuemer geteilter Moden ist die groebste Zelle.
                ag = pr.aggregation
                s = np.flatnonzero(ag.schlecht & (ag.wurzel >= 0))
                check("  keine Wurzel feiner als ihre Zelle, keine Zelle ohne Wurzel oder zu teilen",
                      (pr.gitter.ebene[ag.wurzel[s]] <= pr.gitter.ebene[s]).all() and ag.statistik["zellen_zu_teilen"] == 0
                      and ag.statistik["zellen_ohne_wurzel"] == 0, f"Wurzelteilungen {pr.wurzel_teilungen}, {ag.statistik}")
    # kleine Schnittzellen bleiben mit Verfeinerung exakt (Aggregation nach den haengenden Zwaengen)
    extra = ({"typ": "halbraum", "punkt": [80.0 + 2e-5, 0, 0], "normale": [1, 0, 0], "name": "s3"},)
    pr = _problem(2, Verfeinerung(schnitt_ebenen=1), extra=extra)
    U = pr.loesen({"alles": u_exakt})[:, 0]
    eu, es, eo = _fehler(pr, U)
    check("Schnittanteil 1e-6 auf verfeinertem Gitter: u, sigma < 1e-6", eu < 1e-6 and es < 1e-6 and eo < 1e-6, f"u {eu:.1e}, sigma {es:.1e}, Rand {eo:.1e}, {pr.protokoll['zwaenge']}")


def test_leere_zellen():
    """Wurzeln der Aggregation liegen nah, werkstoffferne leere Zellen bekommen keine, ihre Moden sind null.

    Befund 28.09.2026 an der Kirsch-Scheibe: Ketten reichten die Wurzel mit dem groessten Anteil weiter,
    auch durch leere Zellen im Loch, die nur wegen einer lockeren Abstandsschranke der Mengenoperation
    als geschnitten galten (0,6 mm statt 19 mm zum Werkstoff). Die Wurzel lag bis 38 Halbweiten entfernt,
    h 20 p 3 Versatz 0,6: |C| bis 8,4e7, h 8: 3,5e9, Diagonale der reduzierten Matrix bis 2,5e21 gegen
    einen Median von 1,4e5. Erwartet: Wurzelabstand hoechstens 4 Halbweiten (zwei Zellen), |C| unter
    1e5 (gemessen 3,4e4 bei Abstand 4 ueber Eck), werkstoffferne leere Zellen ohne Wurzel, und jeder
    null gesetzte Mode nur von Zellen ohne Werkstoff getragen (unabhaengig aus den Zellmoden gezaehlt).
    Die Exaktheit linearer Felder mit leeren Zellen prueft test_patch_verfeinert (duenne Waende)."""
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.tests.test_kirsch import D, T, _platte
    v = Verfeinerung(bereiche=((np.array([0.0, 0.0, T / 2]), D / 2 + 10.0, 5.0),))
    t0 = time.perf_counter()
    pr = _platte(3, 20.0, versatz=0.6, verfeinerung=v)
    ag, g, C = pr.aggregation, pr.gitter, pr.zwaenge.C.tocsr()
    mit = np.flatnonzero(ag.schlecht & (ag.wurzel >= 0))
    abstand = max(ag._abstand(int(c)) for c in mit)
    cmax = float(np.abs(C.data).max())
    fern_ohne = bool(np.all(ag.wurzel[ag.werkstofffern] < 0))
    check("Wurzeln hoechstens zwei Zellen entfernt, |C| < 1e5, werkstoffferne leere Zellen ohne Wurzel (vorher 38 Halbweiten, 8,4e7)",
          ag.werkstofffern.sum() > 0 and abstand <= 4.0 + 1e-12 and cmax < 1e5 and fern_ohne,
          f"{int(ag.leer.sum())} leere Zellen, {int(ag.werkstofffern.sum())} werkstofffern, Abstand max {abstand:.2f}, "
          f"|C| max {cmax:.3e}, {time.perf_counter() - t0:.1f} s")
    anteil_max = np.zeros(g.n_moden)
    for c in range(len(g.ijk)):
        np.maximum.at(anteil_max, g.zell_moden[c], ag.anteil[c])
    null_moden = np.flatnonzero(np.diff(C.indptr)[0::3] == 0)
    check("null gesetzte Moden liegen nur in Zellen ohne Werkstoff",
          len(null_moden) == ag.statistik["moden_null"] > 0 and float(anteil_max[null_moden].max()) == 0.0,
          f"{len(null_moden)} Moden null, groesster Werkstoffanteil ihrer Zellen {float(anteil_max[null_moden].max()):.1e}")


def test_wurzelwahl_rundungsfest():
    """Die Wurzel einer schlecht geschnittenen Zelle darf nicht an der Rundung des Werkstoffanteils haengen (Befund
    30.09.2026, Plan TP 5 B1): zwei volle Nachbarn unterschieden sich je nach Quadratur (Referenz gegen Moment
    Fitting) um 3e-15 im Anteil, der Zufallssieger aenderte die Zwangsmatrix und die Randspannungen am Lame-Zylinder
    um 4e-3. Hier: dieselbe Quadratur mit Gewichten mal (1 + 3e-15) muss dieselben Wurzeln liefern."""
    from volumen3d.fcm.aggregation import Zellaggregation
    from volumen3d.fcm.gitter import Gitter
    from volumen3d.fcm.quadratur import Zellquadratur
    from volumen3d.tests.test_lame import _geometrie

    class Gestoert:
        def __init__(self, q, faktor):
            self.q, self.alpha, self.faktor = q, q.alpha, faktor

        def zelle(self, c):
            P, W, I = self.q.zelle(c)
            return P, W * self.faktor, I

    G = Gitter(_geometrie(), h=20.0, polster=0.1)
    G.moden_nummerieren(3)
    Q = Zellquadratur(G, p=3, momentfitting=False)
    a = Zellaggregation(G, Q, 0.4)
    verschieden = 0
    for faktor in (1.0 + 3e-15, 1.0 - 3e-15, 1.0 + 7e-15):
        b = Zellaggregation(G, Gestoert(Q, faktor), 0.4)
        verschieden += int(not np.array_equal(a.wurzel, b.wurzel))
    check(f"Lame h 20 p 3: {int(a.schlecht.sum())} schlecht geschnittene Zellen, Wurzeln bei Gewichten mal (1 +- 3e-15, 7e-15) unveraendert",
          verschieden == 0 and a.schlecht.sum() > 0, f"{verschieden} von 3 Stoerungen aenderten Wurzeln")


def test_gebuendelte_nachbarsuche():
    """Die Nachbarn der Aggregation und die Probepunkte der haengenden Entitaeten werden in einem Aufruf von
    zelle_finden gesucht (vorher 81 380 Einzelaufrufe, 12 s von 23 s Konstruktor bei Kirsch h 8 p 3; A2 Plan
    TP 5). Die Suche ist punktweise: die gebuendelten Ergebnisse muessen den Einzelabfragen gleichen. Geprueft an
    der verfeinerten Kirsch-Scheibe (h 20, Versatz 0,6: schlechte Zellen und haengende Flaechen, Kanten, Ecken)."""
    from volumen3d.fcm.aggregation import _NACHBARN
    from volumen3d.fcm.gitter import Verfeinerung
    from volumen3d.tests.test_kirsch import D, T, _platte
    v = Verfeinerung(bereiche=((np.array([0.0, 0.0, T / 2]), D / 2 + 10.0, 5.0),))
    pr = _platte(3, 20.0, versatz=0.6, verfeinerung=v)
    g, ag, zw = pr.gitter, pr.aggregation, pr.zwaenge
    # Aggregation: Tabelle gegen Einzelsuche
    abw_n, n_n = 0, 0
    for c, zeile in list(ag._nachbar_tab.items()):
        lo, hi = g.zellbox(c)
        m = 0.5 * (lo + hi)
        hl = float(g.h_zelle(c))
        for i, d in enumerate(_NACHBARN):
            P = m + (0.5 * hl + 1e-4 * hl) * np.asarray(d, float)
            abw_n += int(g.zelle_finden(P[None])[0] != zeile[i])
            n_n += 1
    # Zwaenge: gebuendelte Probepunkte gegen Einzelsuche (jede fuenfte feine Zelle)
    fein = np.flatnonzero(g.ebene > 0)[::5]
    nb = zw._probepunkte(fein)
    lo, hi = g.zellbox(fein)
    m = 0.5 * (lo + hi)
    hl = np.asarray(g.h_zelle(fein), float)
    eps = zw.eps * hl
    abw_p, n_p = 0, 0
    for iF in range(len(fein)):
        for k, (d, s) in enumerate([(d, s) for d in range(3) for s in (-1, 1)]):
            P = m[iF].copy()
            P[d] += s * (0.5 * hl[iF] + eps[iF])
            abw_p += int(g.zelle_finden(P[None])[0] != nb[iF, k])
            n_p += 1
    check("gebuendelte Nachbarsuche = Einzelabfragen (Aggregation alle 26 Richtungen, haengende Flaechen)",
          n_n > 1000 and n_p > 100 and abw_n == 0 and abw_p == 0,
          f"Aggregation {n_n} Abfragen, {abw_n} verschieden; Flaechenproben {n_p}, {abw_p} verschieden")


if __name__ == "__main__":
    sys.exit(lauf([test_zaehlung_und_spur, test_leere_zellen, test_gebuendelte_nachbarsuche, test_wurzelwahl_rundungsfest, test_patch_verfeinert]))
