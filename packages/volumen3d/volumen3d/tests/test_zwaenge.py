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


if __name__ == "__main__":
    sys.exit(lauf([test_zaehlung_und_spur, test_leere_zellen, test_patch_verfeinert]))
