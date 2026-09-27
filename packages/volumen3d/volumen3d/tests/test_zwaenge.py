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
            check(f"{name}, p={p}: u, sigma < 1e-6 mit haengenden Freiheitsgraden", eu < 1e-6 and es < 1e-6 and eo < 1e-6,
                  f"u {eu:.1e}, sigma {es:.1e}, Rand {eo:.1e}; Ebenen {pr.protokoll['ebenen']}, haengend F/K/E "
                  f"{zw['haengende_flaechen']}/{zw['haengende_kanten']}/{zw['haengende_ecken']}, Moden haengend {zw['moden_haengend']}, "
                  f"aggregiert {zw['moden_aggregiert']}, frei {zw['moden_frei']} von {pr.gitter.n_moden}, Ketten {zw['kettenlaenge']}, {time.perf_counter() - t:.1f} s")
            if p == 2 and name.startswith("Schnittzellen +"):
                check("  dabei kommen haengende Kanten oder Ecken ohne Flaeche vor (Vorrangregel geprueft)",
                      zw["haengende_kanten"] + zw["haengende_ecken"] > 0, str(zw))
    # kleine Schnittzellen bleiben mit Verfeinerung exakt (Aggregation nach den haengenden Zwaengen)
    extra = ({"typ": "halbraum", "punkt": [80.0 + 2e-5, 0, 0], "normale": [1, 0, 0], "name": "s3"},)
    pr = _problem(2, Verfeinerung(schnitt_ebenen=1), extra=extra)
    U = pr.loesen({"alles": u_exakt})[:, 0]
    eu, es, eo = _fehler(pr, U)
    check("Schnittanteil 1e-6 auf verfeinertem Gitter: u, sigma < 1e-6", eu < 1e-6 and es < 1e-6 and eo < 1e-6, f"u {eu:.1e}, sigma {es:.1e}, Rand {eo:.1e}, {pr.protokoll['zwaenge']}")


if __name__ == "__main__":
    sys.exit(lauf([test_zaehlung_und_spur, test_patch_verfeinert]))
