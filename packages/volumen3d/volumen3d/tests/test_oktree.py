"""U1: Oktree - Verfeinerung an Schnittzellen, Nutzerbereichen und duennen Waenden, 2:1 ueber
26 Nachbarn, Punktsuche ueber Ebenen, ebenenfreie Ecken, Blaetter in Box.

Aufruf: python -m volumen3d.tests.test_oktree
"""
from __future__ import annotations

import sys

import numpy as np

from volumen3d.tests._pruef import check, lauf


def _kugel(h=10.0, **kw):
    from volumen3d.fcm.gitter import Gitter, Verfeinerung
    from volumen3d.geometry.csg import aus_params
    g = aus_params({"csg": {"typ": "kugel", "mitte": [0, 0, 0], "radius": 43.0}})
    return g, Gitter(g, h=h, polster=0.1, verfeinerung=Verfeinerung(**kw))


def _balance_pruefen(G) -> tuple[bool, int]:
    """Kein Blatt hat in einer der 26 Richtungen einen Nachbarn, der mehr als eine Ebene abweicht."""
    from volumen3d.fcm.gitter import _NACHBARN26
    schlecht = 0
    for c in range(len(G.ijk)):
        lo, hi = G.zellbox(c)
        m = 0.5 * (lo + hi)
        hl = G.h_zelle(c)
        for d in _NACHBARN26:
            n = int(G.zelle_finden((m + (0.5 * hl + 1e-6 * hl) * d)[None])[0])
            if n >= 0 and abs(int(G.ebene[n]) - int(G.ebene[c])) > 1:
                schlecht += 1
    return schlecht == 0, schlecht


def test_schnittzellen():
    from volumen3d.fcm.gitter import CUT, INSIDE
    g, G0 = _kugel()
    g, G1 = _kugel(schnitt_ebenen=1)
    check("gleichmaessig: alle Blaetter Ebene 0, Zahl wie in TP 1", G0.max_ebene == 0 and (G0.ebene == 0).all() and len(G0.ijk) == 549, str(len(G0.ijk)))
    check("schnitt_ebenen=1: keine CUT-Zelle mehr auf Ebene 0, INSIDE-Wurzelzellen bleiben (bis auf Balancierung)",
          not ((G1.klasse == CUT) & (G1.ebene == 0)).any() and ((G1.klasse == INSIDE) & (G1.ebene == 0)).any(), str(G1.ebenen_verteilung()))
    check("Kinder liegen in der Wurzelzelle: ijk >> ebene ist eine aktive Wurzelzelle",
          np.all(G0.alle_klassen[G1.flach(G1.ijk >> G1.ebene[:, None], 0)] != 0))
    ok, n = _balance_pruefen(G1)
    check("2:1 ueber 26 Nachbarn eingehalten", ok, f"{n} Verstoesse")
    check("Kantenlaenge je Ebene: h / 2^l", np.allclose(G1.h_zelle(np.arange(len(G1.ijk))), 10.0 / 2.0 ** G1.ebene))


def test_bereich_und_duenn():
    from volumen3d.fcm.gitter import Gitter, Verfeinerung
    from volumen3d.geometry.csg import aus_params
    g, G = _kugel(bereiche=((np.array([43.0, 0, 0]), 8.0, 2.6),))
    lo, hi = G.zellbox(np.arange(len(G.ijk)))
    nah = np.linalg.norm(np.clip([43.0, 0, 0], lo, hi) - [43.0, 0, 0], axis=1) <= 8.0
    # geteilte Zellen liefern auch Kinder knapp ausserhalb des Bereichs (hoechstens eine Elternkante 5 mm entfernt)
    fern = np.linalg.norm(np.clip([43.0, 0, 0], lo, hi) - [43.0, 0, 0], axis=1) > 8.0 + 5.0
    check("Bereich (Radius 8, Ziel 2,6 mm): Blaetter im Bereich auf Ebene 2 (h 2,5), jenseits einer Elternkante hoechstens Ebene 1, weit weg Ebene 0",
          G.max_ebene == 2 and (G.ebene[nah] == 2).all() and (G.ebene[fern] <= 1).all() and (G.ebene == 0).sum() > 400, str(G.ebenen_verteilung()))
    ok, n = _balance_pruefen(G)
    check("Bereich: 2:1 eingehalten (Uebergangsring Ebene 1)", ok and (G.ebene == 1).any(), f"{n} Verstoesse")
    platte = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [60, 60, 3]}})
    Gd = Gitter(platte, h=10.0, verfeinerung=Verfeinerung(duenne_waende=True))
    check("duenne Platte 3 mm in h 10: Zellen mit Werkstoff geteilt (Ebene 2: 2,5 mm < 3 mm ist nicht mehr duenn nach der Regel 2 h)",
          Gd.max_ebene == 2 and (Gd.ebene >= 1).all(), str(Gd.ebenen_verteilung()))
    Gu = Gitter(platte, h=10.0)
    check("ohne Regel bleibt die Platte auf Ebene 0", (Gu.ebene == 0).all())
    # erzwungene Teilung einzelner Blaetter (Aggregation fordert sie fuer Zellen mit nur feineren Nachbarn)
    ziel = [(0, int(Gu.ijk[c, 0]), int(Gu.ijk[c, 1]), int(Gu.ijk[c, 2])) for c in (0, 5)]
    Gz = Gitter(platte, h=10.0, polster=0.1, verfeinerung=Verfeinerung(zellen=tuple(ziel)))
    kinder = [c for c in range(len(Gz.ijk)) if Gz.ebene[c] == 1 and (0, int(Gz.ijk[c, 0]) // 2, int(Gz.ijk[c, 1]) // 2, int(Gz.ijk[c, 2]) // 2) in ziel]
    check("Verfeinerung.zellen: genau die zwei genannten Blaetter geteilt (Kinder auf Ebene 1, 2:1 balanciert)",
          len(kinder) == len([c for c in range(len(Gz.ijk)) if Gz.ebene[c] == 1]) and 8 <= len(kinder) <= 16 and _balance_pruefen(Gz)[0],
          f"{Gz.ebenen_verteilung()}, Verstoesse {_balance_pruefen(Gz)[1]}")


def test_punktsuche_und_box():
    g, G = _kugel(schnitt_ebenen=2)
    rng = np.random.default_rng(3)
    P = rng.uniform(-45, 45, (10_000, 3))
    c = G.zelle_finden(P)
    innen = g.innen(P)
    check("jeder Werkstoffpunkt liegt in einem Blatt", (c[innen] >= 0).all(), f"{int((c[innen] < 0).sum())} ohne Blatt")
    lo, hi = G.zellbox(c[c >= 0])
    check("gefundenes Blatt enthaelt den Punkt", np.all((P[c >= 0] >= lo - 1e-9) & (P[c >= 0] <= hi + 1e-9)))
    # Eindeutigkeit: kein Punkt liegt in zwei Blaettern (Boxen ueberlappen nicht)
    alle_lo, alle_hi = G.zellbox(np.arange(len(G.ijk)))
    vol = np.prod(alle_hi - alle_lo, axis=1).sum()
    check("Blaetter ueberdecken das aktive Gebiet ohne Ueberlappung (Volumen der Blaetter = Summe je Ebene)",
          abs(vol - sum(G.h_zelle(i) ** 3 for i in range(len(G.ijk)))) < 1e-6)
    box_lo, box_hi = np.array([-12.0, -12, -12]), np.array([12.0, 12, 12])
    b = G.blaetter_in_box(box_lo, box_hi)
    blo, bhi = G.zellbox(b)
    schneidet = np.all((alle_lo <= box_hi) & (alle_hi >= box_lo), axis=1)
    check("blaetter_in_box liefert genau die schneidenden Blaetter", set(b.tolist()) == set(np.flatnonzero(schneidet).tolist()), f"{len(b)} / {int(schneidet.sum())}")
    # Punkt auf der Grenze zwischen grobem und feinem Blatt
    fein = int(np.flatnonzero(G.ebene == G.max_ebene)[0])
    flo, fhi = G.zellbox(fein)
    grenze = np.array([flo[0], 0.5 * (flo[1] + fhi[1]), 0.5 * (flo[2] + fhi[2])])
    n = int(G.zelle_finden(grenze[None])[0])
    check("Punkt auf einer Blattgrenze bekommt ein Blatt, das ihn enthaelt", n >= 0 and np.all(G.zellbox(n)[0] <= grenze + 1e-9) and np.all(G.zellbox(n)[1] >= grenze - 1e-9))


def test_moden_ueber_ebenen():
    from volumen3d.fcm.gitter import Gitter, Verfeinerung
    from volumen3d.geometry.csg import aus_params
    w = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [40, 40, 40]}})
    # eine Ecke des Wuerfels eine Ebene feiner: Bereich um (0,0,0)
    G = Gitter(w, h=20.0, polster=0.0, verfeinerung=Verfeinerung(bereiche=((np.array([0.0, 0, 0]), 5.0, 10.0),)))
    check("Wuerfel 2x2x2, eine Wurzelzelle geteilt: 7 + 8 = 15 Blaetter", len(G.ijk) == 15 and G.ebenen_verteilung() == {0: 7, 1: 8}, str(G.ebenen_verteilung()))
    p = 2
    G.moden_nummerieren(p)
    # feine Ecke auf grober Ecke: die Ecke (20,20,20) gehoert zu allen 8 Wurzelzellen bzw. zum feinen Kind (1,1,1)
    from volumen3d.fcm.basis import modenklassen
    abc = modenklassen(p)["abc"]
    ecke_111 = int(np.flatnonzero((abc == [1, 1, 1]).all(axis=1))[0])       # Mode an Ecke (+,+,+)
    kind = int(np.flatnonzero((G.ebene == 1) & (G.ijk == [1, 1, 1]).all(axis=1))[0])
    grob = int(np.flatnonzero((G.ebene == 0) & (G.ijk == [1, 1, 1]).all(axis=1))[0])
    ecke_000 = int(np.flatnonzero((abc == [0, 0, 0]).all(axis=1))[0])
    check("Ecke (20,20,20): feines Kind und grobe Zelle nennen dieselbe Modennummer (ebenenfreier Schluessel)",
          G.zell_moden[kind, ecke_111] == G.zell_moden[grob, ecke_000])
    # haengende Ecke (10,10,20) des Kindes: nicht mit der groben Zelle geteilt
    kind_000 = int(np.flatnonzero((G.ebene == 1) & (G.ijk == [0, 0, 0]).all(axis=1))[0])
    check("haengende Ecke (10,10,10) hat eine eigene Nummer (keine grobe Zelle traegt sie)",
          G.zell_moden[kind_000, ecke_111] not in set(G.zell_moden[G.ebene == 0].ravel()))
    check("Modennummern lueckenlos", set(G.zell_moden.ravel()) == set(range(G.n_moden)))


def test_rand_auf_zellflaechen():
    """Randflaechen, die genau auf Zellflaechen liegen (Symmetrieebenen der verfeinerten Kirsch-Platte,
    27.09.2026: sym_x 2050 statt 1800 mm2, K_t 3,63 statt 3,08), zaehlen genau einmal - in der Zelle
    auf der Werkstoffseite."""
    from volumen3d.fcm.gitter import Gitter, Verfeinerung
    from volumen3d.geometry.csg import aus_params
    from volumen3d.geometry.oberflaeche import Flaechenquadratur
    w = aus_params({"csg": {"typ": "quader", "min": [0, 0, 0], "max": [10, 10, 10]}})
    # polster 1,0: Wuerfelflaechen auf Zellflaechen der Ebene 0; polster 0,5 + schnitt_ebenen: auf Ebene 1 bzw. 2
    for polster, kw, ebene in ((1.0, {}, 0), (0.5, {"schnitt_ebenen": 1}, 1), (0.5, {"schnitt_ebenen": 2}, 2)):
        G = Gitter(w, h=10.0, polster=polster, verfeinerung=Verfeinerung(**kw))
        fq = Flaechenquadratur.aus_geometrie(w, G, ordnung=3)
        A = fq.gewichte.sum()
        lo, hi = G.zellbox(fq.zelle)
        mitte = 0.5 * (lo + hi)
        # Werkstoffseite: Zellmitte liegt entgegen der Aussennormalen vom Punkt aus
        innen = np.einsum("ij,ij->i", mitte - fq.punkte, fq.normalen) < 0
        check(f"Wuerfelflaechen auf Zellflaechen der Ebene {ebene}: Oberflaeche 600 mm2 genau einmal ({A:.6f}), alle Punkte in Zellen der Werkstoffseite",
              abs(A - 600.0) < 1e-9 and innen.all(), f"{A:.6f}, {int((~innen).sum())} Punkte auf der Leerseite, Ebenen {G.ebenen_verteilung()}")
        fe = Flaechenquadratur.ebene(w, G, [0.0, 0.0, 0.0], [-1.0, 0.0, 0.0], ordnung=3)
        check(f"Schnittebene x = 0 auf Zellflaechen der Ebene {ebene}: 100 mm2 genau einmal", abs(fe.gewichte.sum() - 100.0) < 1e-9, f"{fe.gewichte.sum():.6f}")


def _unabhaengig_pruefen(G) -> tuple[int, int, int, int]:
    """Gitter ohne Gitter-Methoden pruefen: jedes Blatt wird auf seine Teilzellen der feinsten vorhandenen Ebene abgebildet (Woerterbuch Teilzelle -> Blatt).
    Rueckgabe: (Ueberlappungen, fehlende Teilzellen einer aktiven Wurzel, die nicht OUTSIDE sind, 2:1-Verstoesse ueber 26 Richtungen, hoechste Ebene).
    Nicht benutzt werden `zelle_finden` und `_unbalanciert`, die der Aufbau selbst verwendet."""
    from volumen3d.fcm.gitter import OUTSIDE
    L = int(G.ebene.max())
    belegt: dict[tuple[int, int, int], int] = {}
    ueberlappung = 0
    for c in range(len(G.ijk)):
        f = 2 ** (L - int(G.ebene[c]))
        i0 = [int(v) * f for v in G.ijk[c]]
        for a in range(f):
            for b in range(f):
                for d in range(f):
                    k = (i0[0] + a, i0[1] + b, i0[2] + d)
                    ueberlappung += k in belegt
                    belegt[k] = c
    # Ueberdeckung: jede Teilzelle einer aktiven Wurzelzelle, die kein Blatt traegt, muss laut Geometrie OUTSIDE sein
    fehlt = []
    n_wurzel = G.n
    aktiv = np.flatnonzero(G.alle_klassen != OUTSIDE)
    for w in aktiv:
        iw = [int(w // (n_wurzel[1] * n_wurzel[2])), int((w // n_wurzel[2]) % n_wurzel[1]), int(w % n_wurzel[2])]
        f = 2 ** L
        for a in range(f):
            for b in range(f):
                for d in range(f):
                    k = (iw[0] * f + a, iw[1] * f + b, iw[2] * f + d)
                    if k not in belegt:
                        fehlt.append(k)
    luecken = 0
    if fehlt:
        kl = G._klassen(np.full(len(fehlt), L), np.array(fehlt, int))
        luecken = int((kl != OUTSIDE).sum())
    # 2:1: alle angrenzenden Teilzellen jedes Blattes in 26 Richtungen tragen Blaetter, die hoechstens eine Ebene groeber sind
    verstoss = 0
    for c in range(len(G.ijk)):
        l = int(G.ebene[c])
        f = 2 ** (L - l)
        i0 = [int(v) * f for v in G.ijk[c]]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == dy == dz == 0:
                        continue
                    bereiche = [range(i0[a], i0[a] + f) if dd == 0 else ([i0[a] + f] if dd > 0 else [i0[a] - 1]) for a, dd in enumerate((dx, dy, dz))]
                    for x in bereiche[0]:
                        for y in bereiche[1]:
                            for z in bereiche[2]:
                                n = belegt.get((x, y, z))
                                if n is not None and int(G.ebene[n]) < l - 1:
                                    verstoss += 1
    return ueberlappung, luecken, verstoss, L


def test_verfeinerung_drei_ebenen():
    """O15 (02.10.2026): `Gitter._aufbauen` teilte in der 2:1-Balancierung mit der Maske der sortierten Felder die unsortierten lokalen - andere Zellen als
    gemeint. Bei zwei Ebenen ohne Folge, ab drei Ebenen Blaetter ueber max_ebene und eine Kaskade ohne Ende (Kugel Radius 43, h 10, Bereich Radius 8, Ziel 1,3 mm:
    nach 40 Durchlaeufen Blaetter der Ebenen 4 und 5 bei max_ebene 3). Geprueft ohne die Gitter-Methoden des Aufbaus: Teilzellen-Abbildung."""
    from volumen3d.fcm.gitter import Gitter
    for ziel, ebenen in ((2.6, 2), (1.3, 3)):
        g, G = _kugel(bereiche=((np.array([43.0, 0, 0]), 8.0, ziel),))
        ueber, luecken, verstoss, hoechste = _unabhaengig_pruefen(G)
        check(f"Kugel, Bereich Ziel {ziel} mm ({ebenen} Ebenen): Aufbau endet, max_ebene {G.max_ebene}, hoechste Blattebene {hoechste} (nicht darueber), alle Ebenen vorhanden",
              G.max_ebene == ebenen and hoechste == ebenen and set(np.unique(G.ebene).tolist()) == set(range(ebenen + 1)), str(G.ebenen_verteilung()))
        check(f"  unabhaengige Pruefung ueber die feinsten Teilzellen: Ueberlappungen {ueber}, fehlende Teilzellen mit Werkstoff {luecken}, 2:1-Verstoesse ueber 26 Richtungen {verstoss}",
              ueber == 0 and luecken == 0 and verstoss == 0, f"{len(G.ijk)} Blaetter")
    # die Obergrenze der Durchlaeufe schlaegt an, wenn die Balancierung nie fertig wird (Rueckfall in die Kaskade waere sonst ein Aufbau ohne Ende)
    orig = Gitter._unbalanciert
    try:
        Gitter._unbalanciert = lambda self: np.arange(len(self.ijk)) == 0       # meldet in jedem Durchlauf ein Blatt, nie fertig
        try:
            _kugel(bereiche=((np.array([43.0, 0, 0]), 8.0, 2.6),))
            meldung = ""
        except RuntimeError as ex:
            meldung = str(ex)
    finally:
        Gitter._unbalanciert = orig
    check("Balancierung, die nie aufhoert: RuntimeError mit Durchlaufgrenze statt Aufbau ohne Ende", "Balancierung" in meldung and "Durchlaeufe" in meldung, meldung)


if __name__ == "__main__":
    sys.exit(lauf([test_schnittzellen, test_bereich_und_duenn, test_punktsuche_und_box, test_moden_ueber_ebenen, test_rand_auf_zellflaechen, test_verfeinerung_drei_ebenen]))
