"""Bausteine fuer Beispielmodelle (aus den Testmodellen vom 09.11.2026).

``Bau`` legt Knoten ohne Doppel und Linien je Knotenpaar einmal an und teilt
die Raender von Flaechen an allen Knoten, die darauf liegen. Die uebrigen
Hilfen legen Stabzuege, Lager, Kombinationen und Wasserdruck an, so wie es der
Anwender in der Oberflaeche taete.
"""
from __future__ import annotations

import math

import numpy as np

from ..model import DofBehaviour, ShellProp

RHO_G = 1000.0 * 9.81


class Bau:
    """Knoten (ohne Doppel), Linien (je Knotenpaar einmal), Flaechen mit
    selbsttaetiger Teilung der Raender an allen Knoten, die darauf liegen."""

    def __init__(self, m):
        self.m = m
        self.kn = {}
        self.li = {}
        self.n_li = 0
        self.faces = []

    def node(self, p):
        k = tuple(round(float(c), 6) for c in p)
        if k not in self.kn:
            self.kn[k] = self.m.add_node(*k)
        return self.kn[k]

    def line(self, a, b):
        k = (min(a, b), max(a, b))
        if k not in self.li:
            self.n_li += 1
            name = f"L{self.n_li}"
            self.m.add_line(name, [a, b])
            self.li[k] = name
        return self.li[k]

    def face(self, name, punkte, material, dicke):
        for p in punkte:
            self.node(p)
        self.faces.append((name, [np.asarray(p, float) for p in punkte], material, dicke))

    def faces_anlegen(self):
        X = self.m.nodes
        for name, P, mat, dicke in self.faces:
            linien = []
            for i in range(len(P)):
                p, q = P[i], P[(i + 1) % len(P)]
                d = q - p
                L2 = float(d @ d)
                t = (X - p) @ d / L2
                r = X - (p[None, :] + t[:, None] * d[None, :])
                auf = np.where((np.linalg.norm(r, axis=1) < 1e-6) & (t > 1e-9) & (t < 1 - 1e-9))[0]
                ia, ib = self.node(p), self.node(q)
                folge = [ia] + [int(j) for j in auf[np.argsort(t[auf])] if int(j) not in (ia, ib)] + [ib]
                for a, b in zip(folge[:-1], folge[1:]):
                    linien.append(self.line(a, b))
            self.m.add_flaeche(name, linien, material=mat, dicke=dicke)
        self.faces = []

    def linien_wo(self, bed):
        """Linien, deren beide Endknoten die Bedingung erfuellen."""
        X = self.m.nodes
        return [n for (a, b), n in self.li.items() if bed(X[a]) and bed(X[b])]


def stab(m, bau, name, punkte, mat, sec, h=1.5, typ="beam"):
    """Stab ueber die Punktfolge: je Abschnitt eine Linie, geteilt auf etwa h."""
    els = []
    for p, q in zip(punkte[:-1], punkte[1:]):
        a, b = bau.node(p), bau.node(q)
        ln = bau.line(a, b)
        L = float(np.linalg.norm(np.asarray(q, float) - np.asarray(p, float)))
        n = 1 if typ == "truss" else max(1, math.ceil(L / h))
        els += m.line_to_beams(ln, mat, sec, n=n, typ=typ, group=name)
    m.add_member(name, els)
    return els


def kombination(m, name, faktoren, text, nr):
    m.add_combination(name, faktoren, "ULS", text, nummer=nr)


def lager(m, knoten, dofs, name):
    return m.support(int(knoten), sorted(dofs), name=name)


def linienlager(m, name, linien, dofs):
    ls = m.add_line_support([], name=name)
    ls.linien = list(linien)
    for d in dofs:
        ls.behaviour[d] = DofBehaviour("rigid")
    return ls


def wasser(m, name, flaechen, nr, h_ow, h_uw, z_ok, breite, richtung, bezeichnung):
    """Wasserdruck ueber den Lastgenerierer des Programms (statisch, analytisch)."""
    from ..wasserdruck import Wasserdruck, lasten_erzeugen
    wd = Wasserdruck(name, lastfall_nr=nr, flaechen=list(flaechen), h_ow=h_ow, h_uw=h_uw,
                     richtung=[float(c) for c in richtung], verfahren="analytisch", absenkung=False,
                     z_uk=0.0, z_ok=z_ok, breite=breite)
    lasten_erzeugen(m, wd)
    lc = m.load_cases[wd.lastfall]
    lc.category = "H"
    lc.bezeichnung = bezeichnung
    return wd.lastfall


def kreis(m, tag, r, z):
    a = m.add_node(r, 0.0, z)
    c = m.add_node(-r, 0.0, z)
    m.add_line(f"{tag}1", [a, c], "arc", punkte=[(r, 0, z), (0, r, z), (-r, 0, z)])
    m.add_line(f"{tag}2", [c, a], "arc", punkte=[(-r, 0, z), (0, -r, z), (r, 0, z)])
    return a, c, [f"{tag}1", f"{tag}2"]


def mantel(m, tag, unten, oben, mat):
    au, cu, ku = unten
    ao, co, ko = oben
    m.add_line(f"{tag}N1", [au, ao])
    m.add_line(f"{tag}N2", [cu, co])
    m.add_flaeche(f"{tag} 1", [ku[0], f"{tag}N2", ko[0], f"{tag}N1"], material=mat, typ="regelflaeche")
    m.add_flaeche(f"{tag} 2", [ku[1], f"{tag}N1", ko[1], f"{tag}N2"], material=mat, typ="regelflaeche")
    return [f"{tag} 1", f"{tag} 2"]


def platten_raster(m, b, abb, S, H, d, riegel, bf, steifen_s, steifen_tiefe, voll_schotte,
                   t_haut, t_steg, t_gurt, t_steife, t_end):
    """Stauwand im lokalen System (s laengs, n zur Unterwasserseite, z hoch):
    Haut bei n = 0, Riegel als Steg und Gurt, Steifen bzw. Schotte, Endschotte.
    ``abb(s, n, z)`` bildet auf global ab. Rueckgabe: Namen der Hautflaechen."""
    Zs = sorted({0.0, H} | set(riegel) | {round(z + v, 6) for z in riegel for v in (-bf / 2, bf / 2)
                                           if 0.0 < z + v < H})
    Ss = sorted({0.0, S} | set(steifen_s))
    Ns = sorted({0.0, d} | ({steifen_tiefe} if steifen_tiefe and not voll_schotte else set()))
    haut, nr = [], 0

    def f(name, pts, dicke):
        b.face(name, [abb(*p) for p in pts], "S355", dicke)

    for i in range(len(Ss) - 1):
        for k in range(len(Zs) - 1):
            nr += 1
            nm = f"Haut {nr}"
            f(nm, [(Ss[i], 0, Zs[k]), (Ss[i + 1], 0, Zs[k]), (Ss[i + 1], 0, Zs[k + 1]), (Ss[i], 0, Zs[k + 1])],
              t_haut)
            haut.append(nm)
    for r, z in enumerate(riegel):
        for i in range(len(Ss) - 1):
            for j in range(len(Ns) - 1):
                f(f"Riegel {r + 1} Steg {i + 1}.{j + 1}",
                  [(Ss[i], Ns[j], z), (Ss[i + 1], Ns[j], z), (Ss[i + 1], Ns[j + 1], z), (Ss[i], Ns[j + 1], z)],
                  t_steg)
            for hlf, (z0, z1) in enumerate(((max(0.0, z - bf / 2), z), (z, min(H, z + bf / 2)))):
                f(f"Riegel {r + 1} Gurt {i + 1}.{hlf + 1}",
                  [(Ss[i], d, z0), (Ss[i + 1], d, z0), (Ss[i + 1], d, z1), (Ss[i], d, z1)], t_gurt)
    Zr = sorted({0.0, H} | set(riegel))
    tiefe = d if voll_schotte else steifen_tiefe
    for s in steifen_s:
        for k in range(len(Zr) - 1):
            f(f"{'Schott' if voll_schotte else 'Steife'} s={s:g} {k + 1}",
              [(s, 0, Zr[k]), (s, tiefe, Zr[k]), (s, tiefe, Zr[k + 1]), (s, 0, Zr[k + 1])], t_steife)
    Ze = Zs
    for s, nm in ((0.0, "Endschott A"), (S, "Endschott B")):
        for j in range(len(Ns) - 1):
            for k in range(len(Ze) - 1):
                f(f"{nm} {j + 1}.{k + 1}", [(s, Ns[j], Ze[k]), (s, Ns[j + 1], Ze[k]),
                                            (s, Ns[j + 1], Ze[k + 1]), (s, Ns[j], Ze[k + 1])], t_end)
    return haut


def dicken(m, werte):
    """Schalendicken [m] anlegen; zurueck {Dicke: Name}."""
    namen = {}
    for t in werte:
        if t in namen:
            continue
        nm = f"t = {t * 1000:g} mm"
        if nm not in m.shells:
            m.add_shell_prop(ShellProp(nm, t))
        namen[t] = nm
    return namen
