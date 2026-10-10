"""Netzabhaengige Spannungsspitzen erkennen: Kraft geht ohne Flaeche in ein Volumen.

Plan Singularitaeten vom 10.10.2026, Paket 1. Anlass ist der volle LF1 des
Drehlagers mit Netz Mittel: die 16 Ankerstaebe haengen ueber starre Scheiben
nur am oberen Lochrand ihrer Platte, und dort entstehen eps_p bis 39 % und
sigma_v bis 1 187 N/mm2 - Werte, die mit jeder Netzverfeinerung wachsen
(Entwurf am selben Ort: eps_p 2,7 bis 5,9 %). Der Anwender will solche
Stellen im Modell und im Bericht als unrealistisch gekennzeichnet sehen,
ohne dass sie die Rechnung verlaengern (Entscheidungen vom 10.10.2026).

**Die Regel.** An jeder Stelle, an der eine Kopplung, ein Stabende, eine
Knotenlast, ein Knoten- oder Linienlager oder eine Linienlast Kraft in
Volumenknoten S einleitet, gelten drei Groessen: die getragene Flaeche
A_trag (Summe der Randseiten, deren Ecken alle in S liegen), die Flaeche der
Huelle von S in ihrer Ausgleichsebene A_Huelle und die oertliche
Kantenlaenge h. Eine Stelle ist eine **Flaeche**, wenn A_trag >= 10 % von
A_Huelle und entweder A_trag >= 2 h^2 ist oder die getragenen Seiten eine ganze
ebene Flaeche des Koerpers decken (:func:`_ganze_flaeche` - wo das Netz nur
ein Element breit ist); sonst ein **Punkt**, wenn ihre Ausdehnung r
hoechstens 2 h betraegt, und sonst eine **Linie**. Flaechen sind keine
Stellen. Am Drehlager findet die Regel 112 Stellen (64 starre Scheiben ueber
Bohrungen, 48 Stabenden der Schrauben) und keine Flaeche; an den Beispielen
nur die Endlast der Konsole (Probe sing_werk/p2, p5).

**Vor der Rechnung** (:func:`kandidaten`, :func:`warnzeilen`) nennt die
Netzabnahme die Stellen gebuendelt als Warnung (:func:`abnahme_befunde` in
diagnose.abnahme); sie haelt die Rechnung nicht an. **Nach der Rechnung** (:func:`auswerten`,
aus solver._spitzenstellen_nachlauf) bestimmt das Programm je Stelle die
Kraft, die durch sie geht, die Zone (Elemente im Umkreis max(4 h; r) um die
Knoten, im selben zusammenhaengenden Netz), deren Spitzenwerte sigma_v (an
den Integrationspunkten, :class:`Punktspannungen`) und eps_p, das Verhaeltnis
F / (A_Huelle f_y) und den Rang nach sigma_v / f_y.
Stellen ohne Kraft fallen weg. **Auffaellig** ist eine Stelle nach der
Entscheidung des Anwenders vom 10.10.2026, wenn in ihrer Zone
sigma_v >= 2 f_y gilt oder die Pressung ueber die Huelle die Streckgrenze
erreicht, F / (A_Huelle f_y) >= 1 - am Drehlager genau die 16 Ankerringe der
Platten V1 bis V28. Die uebrigen bleiben zur Diagnose stehen, gelten aber
nicht als gekennzeichnet. Ohne f_y entfaellt die Pruefung fuer den Werkstoff
(f_y ist der des Werkstoffs, wie ihn der Anwender eingetragen hat, ohne
Dickenstufe - wie in der Plastizitaet).

Das Ergebnis steht in ``res.info["spitzenstellen"]`` (nur Zahlen, Texte und
numpy-Felder, damit es mit der Ergebnisdatei gespeichert und wieder geladen
wird). Paket 2 (Anzeige, Bericht, Nachweise) liest die Zonen ueber
:func:`zonen_elemente` / :func:`zonen_maske`, Paket 3 (Abbruchkriterium der
Plastizitaet) fragt waehrend der Iteration :func:`auffaellige_zonen`, das nur
die Elemente der Kandidatenzonen anfasst.
"""
from __future__ import annotations

import time

import numpy as np

#: Name der Pruefung in der Netzabnahme (diagnose.Befund.pruefung)
PRUEFUNG = "Kraft ohne Fläche"
#: Fassung des Eintrags in res.info - wer die Form aendert, zaehlt hoch
FASSUNG = 1
#: Einordnung (Plan, Abschnitt 2): Flaeche ab FLAECHE_H2 h^2 getragener
#: Flaeche, die mindestens FLAECHE_ANTEIL der Huelle deckt; Punkt bis zur
#: Ausdehnung PUNKT_H h
FLAECHE_H2 = 2.0
FLAECHE_ANTEIL = 0.10
PUNKT_H = 2.0
#: Knick [Grad], ab dem eine benachbarte Randseite nicht mehr zur selben
#: Flaeche zaehlt (_ganze_flaeche): eine Wuerfelkante hat 90 Grad, ein
#: Zylinder aus 48 Seiten 7,5 Grad
GANZE_FLAECHE_KNICK = 30.0
#: Zone: Elemente, deren Schwerpunkt hoechstens max(ZONE_H h; r) von einem
#: Knoten der Stelle entfernt ist
ZONE_H = 4.0
#: auffaellig (Entscheidung des Anwenders vom 10.10.2026)
GRENZE_SV_FY = 2.0
GRENZE_PRESSUNG = 1.0
#: Eine Stelle hat keine Kraft, wenn |F| hoechstens dieser Anteil der
#: Bezugskraft ist (Summe der Auflagerkraefte, mindestens die groesste
#: Stellenkraft). Am Knotenblech halten zwei Punktlager nur die Querbewegung
#: ohne Querlast (README des Referenzmodells): ihre Reaktion ist Rundung.
OHNE_KRAFT = 1e-6

STARRE_SCHEIBE = "starre Scheibe"
STABENDE = "Stabende"
KOPPLUNG = "Kopplung"
STARRKOERPER = "Starrkörper"
KNOTENLAST = "Knotenlast"
KNOTENLAGER = "Knotenlager"
LINIENLAGER = "Linienlager"
LINIENLAST = "Linienlast"
#: Reihenfolge der Arten in Warnung und Ausgabe
QUELLEN = (STARRE_SCHEIBE, STABENDE, KOPPLUNG, STARRKOERPER, KNOTENLAST, LINIENLAST,
           KNOTENLAGER, LINIENLAGER)


# --------------------------------------------------------------------------
# Netz einmal aufbereitet
# --------------------------------------------------------------------------
class _Netz:
    """Die Volumenelemente als Matrizen je Typ - eine Schleife ueber die
    Elemente fuer alles, was die Regel braucht; jede Frage danach ist
    vektorisiert. Die ganze Vorabpruefung braucht am Drehlager (617 177
    tet10, 112 Stellen) 1,1 s (sp1_werk/a5_abnahme2.out)."""

    def __init__(self, model):
        from . import assemble as asm
        from .elements import solid as sl
        self.model = model
        nn = int(model.nn)
        self.nn = nn
        self.X = np.asarray(model.nodes[:nn], float).reshape(-1, 3)
        vol = set(asm.SOLID_TYPES)
        linie = set(asm.LINE_TYPES)
        je_typ: dict = {}
        self.stabknoten: dict = {}             # Knoten -> Stabelemente daran
        sonst = set()                          # Knoten an Schalen, Federn, ...
        for i, e in enumerate(model.elements):
            t = e.typ
            if t in vol:
                je_typ.setdefault(t, []).append(i)
            elif t in linie:
                for n in e.nodes:
                    self.stabknoten.setdefault(int(n), []).append(i)
            else:
                sonst.update(int(n) for n in e.nodes)
        self.sonstknoten = sonst
        self.typen = []                        # [(typ, Zeilen, Elemente, K, Ecken)]
        teile_el, teile_kc, start = [], [], 0
        for t, idx in je_typ.items():
            # Elemente mit falscher Knotenzahl oder unbekanntem Knoten meldet die
            # Abnahme selbst (diagnose.knotenzahl_falsch); hier bleiben sie aussen vor
            listen = [model.elements[int(i)].nodes for i in idx]
            try:
                soll = int(sl.knotenzahl(t))
            except Exception:                 # noqa: BLE001 - dann die haeufigste Zahl
                laengen = [len(x) for x in listen]
                soll = max(set(laengen), key=laengen.count)
            gut = [k for k, x in enumerate(listen) if len(x) == soll]
            if not gut:
                continue
            K = np.array([listen[k] for k in gut], dtype=np.int64).reshape(len(gut), soll)
            ok = ((K >= 0) & (K < nn)).all(axis=1)
            if not ok.any():
                continue
            idx = np.asarray(idx, np.int64)[gut][ok]
            K = K[ok]
            nk = len(sl.ECKEN_NATUERLICH.get(t, ())) or min(4, K.shape[1])
            zeilen = np.arange(start, start + len(idx))
            start += len(idx)
            self.typen.append((t, zeilen, idx, K, nk))
            kc = np.full((len(idx), 8), -1, np.int64)
            kc[:, :nk] = K[:, :nk]
            teile_el.append(idx)
            teile_kc.append(kc)
        self.n_vol = start
        self.el = np.concatenate(teile_el) if teile_el else np.zeros(0, np.int64)
        self.kc = np.concatenate(teile_kc) if teile_kc else np.zeros((0, 8), np.int64)
        self.zeile_von = np.full(len(model.elements), -1, np.int64)
        self.zeile_von[self.el] = np.arange(self.n_vol)
        self.volknoten = np.zeros(nn, bool)
        for _t, _z, _idx, K, _nk in self.typen:
            self.volknoten[K[(K >= 0) & (K < nn)]] = True
        self._mitte = None
        self._baum = None
        self._koerper = None
        self._fy = None

    # ---- Schwerpunkte, Koerper, Streckgrenzen -----------------------------
    @property
    def mitte(self) -> np.ndarray:
        if self._mitte is None:
            m = np.zeros((self.n_vol, 3))
            for _t, z, _idx, K, nk in self.typen:
                m[z] = self.X[K[:, :nk]].mean(axis=1)
            self._mitte = m
        return self._mitte

    @property
    def baum(self):
        if self._baum is None:
            from scipy.spatial import cKDTree
            self._baum = cKDTree(self.mitte)
        return self._baum

    def koerper_der_zeilen(self, zeilen) -> list:
        """Koerpernamen der Elemente in diesen Zeilen ("" ohne Koerper)."""
        if self._koerper is None:
            nr = np.full(self.n_vol, -1, np.int64)
            namen = []
            for k, (name, kp) in enumerate((getattr(self.model, "koerper", None) or {}).items()):
                namen.append(str(name))
                el = np.asarray([int(x) for x in (getattr(kp, "elemente", None) or [])], np.int64)
                el = el[(el >= 0) & (el < len(self.zeile_von))]
                z = self.zeile_von[el]
                nr[z[z >= 0]] = k
            self._koerper = (nr, namen)
        nr, namen = self._koerper
        return [namen[k] if k >= 0 else "" for k in nr[np.asarray(zeilen, np.int64)]]

    def fy_der_zeilen(self, zeilen) -> np.ndarray:
        """f_y [Pa] je Element, nan ohne f_y."""
        if self._fy is None:
            fy = np.full(self.n_vol, np.nan)
            werte: dict = {}
            mats = self.model.materials
            for z, i in enumerate(self.el.tolist()):
                name = self.model.elements[i].mat
                if name not in werte:
                    mat = mats.get(name)
                    f = float(getattr(mat, "fy", 0.0) or 0.0) if mat is not None else 0.0
                    werte[name] = f if f > 0 else np.nan
                fy[z] = werte[name]
            self._fy = fy
        return self._fy[np.asarray(zeilen, np.int64)]

    # ---- Elemente und Randseiten an Knoten --------------------------------
    def an_knoten(self, maske: np.ndarray) -> tuple:
        """(Zeilen der Elemente mit einem Knoten aus ``maske``, Randseiten
        dieser Elemente mit einem Knoten aus ``maske``: Knoten (m, 4) mit -1
        aufgefuellt, Flaeche (m,), mittlere Kantenlaenge (m,)) und je Zeile
        die mittlere Kantenlaenge des Elements.

        Rand heisst: die Seite gehoert zu genau einem Element. Gezaehlt wird
        nur unter den Elementen an ``maske`` - das genuegt, denn eine Seite
        mit einem Knoten aus ``maske`` liegt in jedem ihrer Elemente an
        diesem Knoten."""
        from .elements import solid as sl
        zeilen_alle, schl, seiten, flaeche, kante, h_el = [], [], [], [], [], []
        for t, z, _idx, K, nk in self.typen:
            treffer = maske[np.clip(K, 0, self.nn - 1)].any(axis=1)
            if not treffer.any():
                continue
            zz = z[treffer]
            Kt = K[treffer]
            zeilen_alle.append(zz)
            fl = sl.FLAECHEN_ECKEN.get(t) or [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)]
            summe = np.zeros(len(zz))
            zahl = np.zeros(len(zz))
            for f in fl:
                F = Kt[:, list(f)]                           # (n, 3|4) im Umlauf
                P = self.X[F]
                L = np.linalg.norm(P - np.roll(P, -1, axis=1), axis=2)   # (n, k)
                summe += L.sum(axis=1)
                zahl += L.shape[1]
                A = 0.5 * np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1)
                if F.shape[1] == 4:
                    A = A + 0.5 * np.linalg.norm(np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]), axis=1)
                pad = np.full((len(F), 4), -1, np.int64)
                pad[:, :F.shape[1]] = F
                schl.append(np.sort(pad, axis=1))
                seiten.append(pad)
                flaeche.append(A)
                kante.append(L.mean(axis=1))
            h_el.append(summe / np.maximum(zahl, 1))
        if not zeilen_alle:
            leer = np.zeros(0)
            return np.zeros(0, np.int64), np.zeros((0, 4), np.int64), leer, leer, leer
        zeilen = np.concatenate(zeilen_alle)
        S = np.concatenate(schl)
        _u, inv, zahl = np.unique(S, axis=0, return_inverse=True, return_counts=True)
        rand = zahl[np.asarray(inv).ravel()] == 1
        seite = np.concatenate(seiten)[rand]
        an = maske[np.clip(seite, 0, self.nn - 1)] & (seite >= 0)
        rand_an = an.any(axis=1)
        return (zeilen, seite[rand_an], np.concatenate(flaeche)[rand][rand_an],
                np.concatenate(kante)[rand][rand_an], np.concatenate(h_el))


def _csr(paare_zeile: np.ndarray, paare_wert: np.ndarray, n: int) -> tuple:
    """(Zeiger, Werte): je Zeile 0..n-1 die Werte - wie eine CSR-Struktur."""
    ordnung = np.argsort(paare_zeile, kind="stable")
    zeile = paare_zeile[ordnung]
    wert = paare_wert[ordnung]
    zeiger = np.zeros(n + 1, np.int64)
    np.add.at(zeiger, zeile + 1, 1)
    return np.cumsum(zeiger), wert


# --------------------------------------------------------------------------
# Kandidaten: die Stellen vor der Rechnung
# --------------------------------------------------------------------------
def _buendeln(netz: _Netz, knoten) -> list:
    """Knoten zu zusammenhaengenden Gruppen: zwei Knoten gehoeren zusammen,
    wenn sie in einem gemeinsamen Volumenelement liegen."""
    from scipy import sparse
    from scipy.sparse.csgraph import connected_components
    knoten = np.unique(np.asarray(list(knoten), np.int64))
    knoten = knoten[(knoten >= 0) & (knoten < netz.nn)]
    knoten = knoten[netz.volknoten[knoten]]
    if not len(knoten):
        return []
    pos = np.full(netz.nn, -1, np.int64)
    pos[knoten] = np.arange(len(knoten))
    reihe, spalte = [], []
    nz = 0
    for _t, _z, _idx, K, _nk in netz.typen:
        P = pos[np.clip(K, 0, netz.nn - 1)]
        P[K < 0] = -1
        treffer = (P >= 0).any(axis=1)
        if not treffer.any():
            continue
        P = P[treffer]
        r = np.repeat(np.arange(nz, nz + len(P)), P.shape[1])
        c = P.ravel()
        gut = c >= 0
        reihe.append(r[gut])
        spalte.append(c[gut])
        nz += len(P)
    B = sparse.coo_matrix((np.ones(sum(len(r) for r in reihe)), (np.concatenate(reihe), np.concatenate(spalte))),
                          shape=(nz, len(knoten))).tocsr()
    G = (B.T @ B).tocsr()
    _n, lab = connected_components(G, directed=False)
    gruppen: dict = {}
    for k, l in zip(knoten.tolist(), lab.tolist()):
        gruppen.setdefault(l, []).append(k)
    return [np.asarray(v, np.int64) for _l, v in sorted(gruppen.items(), key=lambda x: min(x[1]))]


def _quellen(model, netz: _Netz) -> list:
    """Alle Stellen, an denen Kraft in Volumenknoten geht - noch ohne
    Einordnung: [dict(quelle, name, knoten, master, last_je_fall)]."""
    from . import fugen
    aus = []
    vk = netz.volknoten
    # Kopplungen je Gruppe (starre Scheiben, Stabenden, Kontaktfugen, ...)
    gruppen: dict = {}
    for k in getattr(model, "kopplungen", None) or []:
        g = gruppen.setdefault(str(getattr(k, "gruppe", "")), [set(), set()])
        g[0].add(int(k.node_a))
        g[1].add(int(k.node_b))
    belastet = {int(nl.node) for lc in (getattr(model, "load_cases", None) or {}).values()
                for nl in (getattr(lc, "nodal_loads", None) or [])}
    gelagert = {int(s.node) for s in getattr(model, "supports", None) or []}
    for g, (a, b) in gruppen.items():
        alle = np.asarray(sorted((a | b)), np.int64)
        alle = alle[(alle >= 0) & (alle < netz.nn)]
        S = alle[vk[alle]]
        if not len(S):
            continue
        frei = sorted(set(alle.tolist()) - set(S.tolist()))
        master = frei[0] if len(frei) == 1 else -1
        if g.startswith(fugen.STARR_GRUPPE):
            quelle = STARRE_SCHEIBE
        elif g.startswith(fugen.STABENDE_GRUPPE):
            # fugen.stabenden_koppeln schliesst auch Lastknoten und
            # Lagerknoten im Volumen an - die Art sagt, was dort haengt
            quelle = (STABENDE if master in netz.stabknoten else KNOTENLAST if master in belastet
                      else KNOTENLAGER if master in gelagert else KOPPLUNG)
        else:
            quelle = KOPPLUNG
        aus.append(dict(quelle=quelle, name=g, knoten=S, master=master))
    for sk in getattr(model, "starrkoerper", None) or []:
        alle = np.asarray([int(x) for x in sk.slaves if int(x) != int(sk.master)], np.int64)
        alle = alle[(alle >= 0) & (alle < netz.nn)]
        S = np.unique(alle[vk[alle]])
        if not len(S):
            continue
        aus.append(dict(quelle=STARRKOERPER, name=str(getattr(sk, "name", "")) or "Starrkörper",
                        knoten=S, master=int(sk.master)))
    # Knotenlasten auf Volumenknoten (ohne die aus Linienlasten verteilten),
    # ueber alle Lastfaelle gebuendelt: die Stelle ist ein Ort
    last: dict = {}
    for lc_name, lc in (getattr(model, "load_cases", None) or {}).items():
        for nl in getattr(lc, "nodal_loads", None) or []:
            n = int(nl.node)
            if getattr(nl, "_geo", False) or not 0 <= n < netz.nn or not vk[n]:
                continue
            d = last.setdefault(n, {})
            d[lc_name] = d.get(lc_name, np.zeros(3)) + np.asarray(nl.F[:3], float)
    for S in _buendeln(netz, last):
        jf: dict = {}
        for n in S.tolist():
            for lc_name, v in last[n].items():
                jf[lc_name] = jf.get(lc_name, np.zeros(3)) + v
        aus.append(dict(quelle=KNOTENLAST, name=_knotenname(S, ", ".join(sorted(jf))), knoten=S, master=-1,
                        last_je_fall=jf))
    # Linienlasten auf Linien, deren Knoten Volumenknoten sind
    cache: dict = {}
    for lc_name, lc in (getattr(model, "load_cases", None) or {}).items():
        for ll in getattr(lc, "linienlasten", None) or []:
            if getattr(ll, "art", "stab") != "linie":
                continue
            try:
                lasten = model._linienlast_legen(ll, cache)
            except Exception:                 # noqa: BLE001 - dann gibt es keine Knoten
                lasten = []
            je: dict = {}
            for nl in lasten:
                n = int(getattr(nl, "node", -1))
                if 0 <= n < netz.nn and vk[n]:
                    je[n] = je.get(n, np.zeros(3)) + np.asarray(nl.F[:3], float)
            for S in _buendeln(netz, je):
                F = sum((je[n] for n in S.tolist()), np.zeros(3))
                aus.append(dict(quelle=LINIENLAST, name=f"{lc_name}: {ll.ziel}", knoten=S, master=-1,
                                last_je_fall={lc_name: F}))
    # Knotenlager auf Volumenknoten, alle zusammen gebuendelt (die Symmetrie-
    # ebenen einer Hohlkugel sperren je eine andere Richtung und sind doch
    # eine Flaeche)
    lager = [int(s.node) for s in getattr(model, "supports", None) or []
             if 0 <= int(s.node) < netz.nn and vk[int(s.node)]]
    namen = {int(s.node): str(getattr(s, "name", "") or "") for s in getattr(model, "supports", None) or []}
    for S in _buendeln(netz, lager):
        nm = sorted({namen.get(int(n), "") for n in S.tolist()} - {""})
        aus.append(dict(quelle=KNOTENLAGER, name=_knotenname(S, ", ".join(nm[:3])), knoten=S, master=-1))
    # Ein Master, an dem mehr als eine Gruppe haengt, gibt die Kraft der
    # einzelnen nicht her - das Gleichgewicht am Knoten kennt nur die Summe
    zahl: dict = {}
    for q in aus:
        if q["master"] >= 0:
            zahl[q["master"]] = zahl.get(q["master"], 0) + 1
    for q in aus:
        q["master_geteilt"] = q["master"] >= 0 and zahl.get(q["master"], 0) > 1
    for ls in getattr(model, "line_supports", None) or []:
        kn = [int(n) for n in (getattr(ls, "nodes", None) or []) if 0 <= int(n) < netz.nn and vk[int(n)]]
        for S in _buendeln(netz, kn):
            aus.append(dict(quelle=LINIENLAGER, name=str(getattr(ls, "name", "")), knoten=S, master=-1))
    return aus


def _seitennormalen(X: np.ndarray, seite: np.ndarray) -> np.ndarray:
    """Einheitsnormale je Randseite (Knoten (m, 4), -1 aufgefuellt)."""
    if not len(seite):
        return np.zeros((0, 3))
    a, b, c = X[seite[:, 0]], X[seite[:, 1]], X[seite[:, 2]]
    n = np.cross(b - a, c - a)
    vier = seite[:, 3] >= 0
    if vier.any():
        d = X[seite[vier, 3]]
        n[vier] = np.cross(c[vier] - a[vier], d - b[vier])
    return n / np.maximum(np.linalg.norm(n, axis=1), 1e-300)[:, None]


def _ganze_flaeche(seite, normale, bedeckt, offen) -> bool:
    """Decken die Seiten ``bedeckt`` eine ganze ebene Flaeche des Koerpers?
    Das heisst: keine nicht bedeckte Randseite schliesst an einer ihrer Kanten
    glatt an (Knick unter GANZE_FLAECHE_KNICK). Dann ist die getragene Flaeche
    die des Modells, nicht die einer Elementseite - auch wenn sie kleiner als
    2 h^2 ist, weil das Netz dort nur ein Element breit ist (Wuerfelpaar aus
    zwei hex8, Boden ganz gelagert). Unter einem Stabende liegt dagegen eine
    Elementseite mitten in der Stirnflaeche: ihre Nachbarn liegen in derselben
    Ebene."""
    if not len(bedeckt):
        return False
    cos_knick = np.cos(np.radians(GANZE_FLAECHE_KNICK))
    for f in bedeckt.tolist():
        ecken = [int(x) for x in seite[f] if x >= 0]
        for a, b in zip(ecken, ecken[1:] + ecken[:1]):
            nachbar = offen[(seite[offen] == a).any(axis=1) & (seite[offen] == b).any(axis=1)]
            if len(nachbar) and (np.abs(normale[nachbar] @ normale[f]) > cos_knick).any():
                return False
    return True


def _knotenname(S, vorsatz: str = "") -> str:
    """„LF1: K12“ bzw. „LF1: K12 … (7 Knoten)“."""
    t = f"K{int(S[0])}" + (f" … ({len(S)} Knoten)" if len(S) > 1 else "")
    return f"{vorsatz}: {t}" if vorsatz else t


def _huelle(P: np.ndarray) -> tuple:
    """(Flaeche der konvexen Huelle in der Ausgleichsebene, Mitte, Normale)."""
    c = P.mean(axis=0)
    if len(P) < 3:
        return 0.0, c, np.array([0.0, 0.0, 1.0])
    _u, s, vt = np.linalg.svd(P - c, full_matrices=False)
    if s[1] <= 1e-12 * max(s[0], 1e-300):
        return 0.0, c, vt[-1]
    Q = np.column_stack([(P - c) @ vt[0], (P - c) @ vt[1]])
    try:
        from scipy.spatial import ConvexHull
        return float(ConvexHull(Q).volume), c, vt[2] if len(vt) > 2 else np.cross(vt[0], vt[1])
    except Exception:                         # noqa: BLE001 - kollinear: keine Huelle
        return 0.0, c, vt[-1]


def _lochrand(model, name: str, P: np.ndarray, h: float) -> bool:
    """Liegen alle Knoten einer starren Scheibe auf (bis h/2 neben) ihrem
    Randkreis? Dann koppelt sie nur einen Rand - ueber einer Bohrung den
    Lochrand. Mit den Kopplungen von vor dem 10.10.2026 (vor
    fugen.STARR_TOL_RAND) liegen am Drehlager einzelne Knoten bis 2,46 mm
    daneben; h ist dort 11,6 mm (Ankerscheiben) bzw. rund 5 mm."""
    from . import fugen
    f = (getattr(model, "flaechen", None) or {}).get(name[len(fugen.STARR_GRUPPE):])
    if f is None:
        return False
    try:
        R = np.asarray(f.randpunkte(model, fugen._starre_teilung(model, f)), float).reshape(-1, 3)
    except Exception:                         # noqa: BLE001
        return False
    if len(R) < 3:
        return False
    c = R.mean(axis=0)
    _u, _s, vt = np.linalg.svd(R - c, full_matrices=False)
    e1, e2 = vt[0], vt[1]
    nrm = np.cross(e1, e2)
    D = P - c
    d2 = fugen._abstand_zum_vieleck(np.column_stack([(R - c) @ e1, (R - c) @ e2]),
                                    np.column_stack([D @ e1, D @ e2]))
    d = np.sqrt(d2 ** 2 + (D @ nrm) ** 2)
    return bool(len(d) and float(d.max()) <= 0.5 * h)


def kandidaten(model, zonen: bool = True, netz: _Netz = None) -> list:
    """Die Stellen „Kraft ohne Flaeche“ vor der Rechnung - nach der Regel des
    Moduls eingeordnet, Flaechen ausgenommen.

    Je Stelle ein Woerterbuch: ``nr``, ``quelle`` (QUELLEN), ``name``,
    ``art`` (Punkt | Linie), ``knoten`` (Volumenknoten S), ``n_knoten``,
    ``master`` (Knoten, ueber den die Kraft kommt, -1 ohne), ``koerper``,
    ``mitte``, ``h``, ``r``, ``A_trag``, ``A_huelle`` [m, m2],
    ``fy_stelle`` (kleinstes f_y der Elemente an S, None ohne),
    ``elemente_an`` (die Elemente an S), bei starren
    Scheiben ``lochrand``; mit ``zonen`` dazu ``zone`` (Elementnummern),
    ``zone_radius`` und ``zone_volumen``.

    ``zonen=False`` ist die Vorabpruefung der Netzabnahme: am Drehlager
    1,1 s; mit Zonen 1,6 s (65 102 Zonenelemente)."""
    netz = netz or _Netz(model)
    if not netz.n_vol:
        return []
    roh = _quellen(model, netz)
    if not roh:
        return []
    maske = np.zeros(netz.nn, bool)
    for q in roh:
        maske[q["knoten"]] = True
    zeilen, seite, A_seite, L_seite, h_el = netz.an_knoten(maske)
    # Knoten -> Randseiten und Knoten -> Elementzeilen (nur Knoten aus maske)
    gut = (seite >= 0) & maske[np.clip(seite, 0, netz.nn - 1)]
    s_zeile = np.repeat(np.arange(len(seite)), 4)[gut.ravel()]
    zs, zw = _csr(seite[gut], s_zeile, netz.nn)
    pos_z = np.full(netz.n_vol, -1, np.int64)
    pos_z[zeilen] = np.arange(len(zeilen))
    e_paare_k, e_paare_z = [], []
    for _t, z, _idx, K, _nk in netz.typen:
        sel = pos_z[z] >= 0
        if not sel.any():
            continue
        Kt = K[sel]
        zz = z[sel]
        tr = maske[np.clip(Kt, 0, netz.nn - 1)] & (Kt >= 0)
        rr, cc = np.nonzero(tr)
        e_paare_k.append(Kt[rr, cc])
        e_paare_z.append(zz[rr])
    ez, ew = _csr(np.concatenate(e_paare_k), np.concatenate(e_paare_z), netz.nn)
    normale = _seitennormalen(netz.X, seite)
    in_S = np.zeros(netz.nn, bool)
    aus = []
    for q in roh:
        S = q["knoten"]
        in_S[S] = True
        fl = np.unique(np.concatenate([zw[zs[n]:zs[n + 1]] for n in S.tolist()])) if len(S) else np.zeros(0, int)
        el = np.unique(np.concatenate([ew[ez[n]:ez[n + 1]] for n in S.tolist()]))
        ganz = np.zeros(len(fl), bool)
        if len(fl):
            ganz = (in_S[np.clip(seite[fl], 0, netz.nn - 1)] | (seite[fl] < 0)).all(axis=1)
            A_trag = float(A_seite[fl][ganz].sum())
            h = float(L_seite[fl].mean())
        else:
            A_trag = 0.0
            h = float(h_el[pos_z[el]].mean()) if len(el) else 0.0
        in_S[S] = False
        P = netz.X[S]
        A_huelle, c, _n = _huelle(P)
        r = float(np.linalg.norm(P - c, axis=1).max()) if len(S) > 1 else 0.0
        anteil = A_huelle > 0 and A_trag >= FLAECHE_ANTEIL * A_huelle
        if anteil and (A_trag >= FLAECHE_H2 * h * h
                       or _ganze_flaeche(seite, normale, fl[ganz], fl[~ganz])):
            continue                                    # eine Flaeche - keine Stelle
        art = "Punkt" if r <= PUNKT_H * h else "Linie"
        ko = netz.koerper_der_zeilen(el)
        ko = [k for k in ko if k]
        fy = netz.fy_der_zeilen(el)
        fy = fy[np.isfinite(fy)]
        s = dict(nr=len(aus) + 1, quelle=q["quelle"], name=q["name"], art=art,
                 knoten=np.asarray(S, np.int32), n_knoten=int(len(S)), master=int(q["master"]),
                 koerper=max(set(ko), key=ko.count) if ko else "",
                 mitte=[float(x) for x in c], h=h, r=r, A_trag=A_trag, A_huelle=float(A_huelle),
                 fy_stelle=float(fy.min()) if len(fy) else None,
                 elemente_an=np.sort(netz.el[el]).astype(np.int32), _zeilen=el)
        if "last_je_fall" in q:
            s["last_je_fall"] = {k: np.asarray(v, float) for k, v in q["last_je_fall"].items()}
        if s["quelle"] == STARRE_SCHEIBE:
            s["lochrand"] = _lochrand(model, q["name"], P, h)
        if s["master"] >= 0:
            s["master_staebe"] = [int(i) for i in netz.stabknoten.get(s["master"], [])]
            # Haengt am Master mehr als Staebe (ein Volumen, eine Schale, eine
            # Feder), laesst sich die Kraft nicht aus den Stabenden lesen
            s["master_nur_staebe"] = bool(not netz.volknoten[s["master"]]
                                          and s["master"] not in netz.sonstknoten
                                          and not q.get("master_geteilt"))
            s["master_last"] = _knotenlast_je_fall(model, s["master"])
        aus.append(s)
    if zonen:
        zonen_bestimmen(model, aus, netz)
    for s in aus:
        s.pop("_zeilen", None)
    return aus


def _knotenlast_je_fall(model, knoten: int) -> dict:
    out: dict = {}
    for lc_name, lc in (getattr(model, "load_cases", None) or {}).items():
        for nl in getattr(lc, "nodal_loads", None) or []:
            if int(nl.node) == knoten:
                out[lc_name] = out.get(lc_name, np.zeros(3)) + np.asarray(nl.F[:3], float)
    return out


def zonen_bestimmen(model, stellen: list, netz: _Netz = None) -> list:
    """Je Stelle die Zone: die Volumenelemente, deren Schwerpunkt hoechstens
    max(ZONE_H h; r) von einem Knoten der Stelle entfernt ist und die mit den
    Elementen an der Stelle zusammenhaengen (ueber gemeinsame Knoten, innerhalb
    des Umkreises). Ein anderer Koerper, der nur anliegt (Kontakt, Fuge),
    gehoert nicht dazu: in ihn geht die Kraft der Stelle nicht unmittelbar.
    Schreibt ``zone``, ``zone_radius``, ``zone_volumen`` in die Stellen."""
    from scipy import sparse
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    netz = netz or _Netz(model)
    if not stellen:
        return stellen
    alle = []
    for s in stellen:
        S = np.asarray(s["knoten"], np.int64)
        d = max(ZONE_H * float(s["h"]), float(s["r"]))
        c = np.asarray(s["mitte"], float)
        kand = np.asarray(netz.baum.query_ball_point(c, d + float(s["r"])), np.int64)
        if len(kand):
            dist, _j = cKDTree(netz.X[S]).query(netz.mitte[kand], k=1)
            kand = kand[dist <= d]
        saat = s.get("_zeilen")
        if saat is None:
            maske = np.zeros(netz.nn, bool)
            maske[S] = True
            saat = netz.an_knoten(maske)[0]
        saat_set = np.isin(kand, saat)
        if len(kand) and saat_set.any():
            Kc = netz.kc[kand]
            gut = Kc >= 0
            r_ = np.repeat(np.arange(len(kand)), Kc.shape[1])[gut.ravel()]
            kn, col = np.unique(Kc[gut], return_inverse=True)
            B = sparse.coo_matrix((np.ones(len(r_)), (r_, np.asarray(col).ravel())),
                                  shape=(len(kand), len(kn))).tocsr()
            G = sparse.bmat([[None, B], [B.T, None]]).tocsr()
            _n, lab = connected_components(G, directed=False)
            lab = lab[:len(kand)]
            kand = kand[np.isin(lab, np.unique(lab[saat_set]))]
        else:
            kand = np.zeros(0, np.int64)
        zone = np.sort(netz.el[kand]).astype(np.int32)
        s["zone"] = zone
        s["zone_radius"] = float(d)
        alle.append(zone)
    vereint = np.unique(np.concatenate(alle)) if alle else np.zeros(0, np.int64)
    if len(vereint):
        from .diagnose import elementvolumina
        V = elementvolumina(model, vereint)
        pos = {int(e): k for k, e in enumerate(vereint.tolist())}
        for s in stellen:
            s["zone_volumen"] = float(np.nansum(V[[pos[int(e)] for e in s["zone"]]])) if len(s["zone"]) else 0.0
    else:
        for s in stellen:
            s["zone_volumen"] = 0.0
    return stellen


# --------------------------------------------------------------------------
# Warnung vor der Rechnung
# --------------------------------------------------------------------------
def _spanne(werte) -> str:
    a, b = min(werte), max(werte)
    return f"{a}" if a == b else f"{a}–{b}"


def warnzeilen(stellen: list) -> list:
    """Eine Zeile je Art, gebuendelt - etwa „64 starre Scheiben koppeln nur
    einen Lochrand (40 Knoten)“, „48 Stabenden hängen an 1–3 Knoten“."""
    from .begriffe import anzahl
    zeilen = []
    for q in QUELLEN:
        sel = [s for s in stellen if s.get("quelle") == q]
        if not sel:
            continue
        n = len(sel)
        k = _spanne([int(s.get("n_knoten", 0)) for s in sel])
        if q == STARRE_SCHEIBE:
            loch = sum(1 for s in sel if s.get("lochrand"))
            wort = anzahl(n, "starre Scheibe koppelt", "starre Scheiben koppeln")
            if loch == n:
                zeilen.append(f"{wort} nur einen Lochrand ({k} Knoten)")
            elif loch:
                zeilen.append(f"{wort} nur einen Rand oder einzelne Knoten, davon {loch} einen "
                              f"Lochrand ({k} Knoten)")
            else:
                zeilen.append(f"{wort} nur einen Rand oder einzelne Knoten ({k} Knoten)")
        elif q == STABENDE:
            zeilen.append(f"{anzahl(n, 'Stabende hängt', 'Stabenden hängen')} an {k} Knoten")
        elif q == KOPPLUNG:
            zeilen.append(f"{anzahl(n, 'Kopplung hängt', 'Kopplungen hängen')} an {k} Knoten")
        elif q == STARRKOERPER:
            zeilen.append(f"{anzahl(n, 'Starrkörper hängt', 'Starrkörper hängen')} an {k} Knoten")
        elif q == KNOTENLAST:
            zeilen.append(f"{anzahl(n, 'Knotenlast greift', 'Knotenlasten greifen')} an {k} Knoten an")
        elif q == LINIENLAST:
            zeilen.append(f"{anzahl(n, 'Linienlast liegt', 'Linienlasten liegen')} auf {k} Knoten "
                          "einer Volumenkante")
        elif q == KNOTENLAGER:
            zeilen.append(f"{anzahl(n, 'Knotenlager hält', 'Knotenlager halten')} {k} Knoten")
        elif q == LINIENLAGER:
            zeilen.append(f"{anzahl(n, 'Linienlager hält', 'Linienlager halten')} {k} Knoten "
                          "einer Volumenkante")
    return zeilen


def abnahme_befunde(model) -> list:
    """Die Befunde der Netzabnahme: eine WARNUNG je Art (diagnose.Befund)."""
    from .diagnose import Befund
    t0 = time.perf_counter()
    stellen = kandidaten(model, zonen=False)
    if not stellen:
        return []
    dauer = time.perf_counter() - t0
    aus = []
    for q in QUELLEN:
        sel = [s for s in stellen if s["quelle"] == q]
        if not sel:
            continue
        zeile = warnzeilen(sel)[0]
        aus.append(Befund(
            pruefung=PRUEFUNG, objekt=q, wert=float(len(sel)), grenze=0.0, stufe="WARNUNG",
            knoten=[int(s["master"]) if s["master"] >= 0 else int(s["knoten"][0]) for s in sel][:20],
            text=(f"{zeile} – mögliche netzabhängige Spannungsspitzen: die Kraft geht dort ohne "
                  f"Auflagefläche in das Volumen ({sum(1 for s in sel if s['art'] == 'Linie')} als "
                  f"Linie, {sum(1 for s in sel if s['art'] == 'Punkt')} als Punkt; geprüft in "
                  f"{dauer:.1f} s). Die Rechnung läuft; danach stehen Kraft, Spitze und Zone je "
                  "Stelle beim Ergebnis.")))
    return aus


# --------------------------------------------------------------------------
# Nach der Rechnung
# --------------------------------------------------------------------------
def vergleichsspannung(S) -> np.ndarray:
    """sigma_v je Tensor (n, 6) [sx, sy, sz, txy, tyz, tzx]."""
    S = np.asarray(S, float).reshape(-1, 6)
    return np.sqrt(0.5 * ((S[:, 0] - S[:, 1]) ** 2 + (S[:, 1] - S[:, 2]) ** 2 + (S[:, 2] - S[:, 0]) ** 2)
                   + 3.0 * (S[:, 3] ** 2 + S[:, 4] ** 2 + S[:, 5] ** 2))


class Punktspannungen:
    """sigma_v an den **Integrationspunkten** der Zonenelemente, elastisch
    aus u: sigma = D (B u) - D alpha dT - sigma0 (wie solver._post_chunk).

    Warum nicht der Elementwert des Ergebnisses (``res.solid_res``)? Fuer ein
    elastisches Element ist er der groesste Auswertepunkt, also auch eine Ecke
    - und an einer Singularitaet laeuft die Ecke einer Rechnung mit Fliessen
    weit ueber die Fliessflaeche hinaus, ohne dass das Element fliesst
    (Theoriehandbuch § 5d: 3 006 N/mm2 an einem nicht fliessenden hex8). Am
    Drehlager (LF1 Mittel, 10.10.2026) erreichten drei Zonen von Stabenden so
    712 bis 740 N/mm2 >= 2 f_y, an den Integrationspunkten aber nur 413, 358
    und 426 N/mm2; ueber alle Zonen ausserhalb der 16 Ankerringe hoechstens
    561 N/mm2 (sp1_werk/a6_punkte.out). An den Integrationspunkten gilt die
    Fliessbedingung; dort misst die Regel. Fuer fliessende Elemente ist der
    Elementwert ohnehin der groesste Integrationspunkt (solver._post_chunk).

    Der Operator wird einmal je Modell und Elementmenge gebaut (am Drehlager
    57 532 elastische Zonenelemente in rund 3 s), jede Auswertung danach ist
    ein Produkt mit u."""

    def __init__(self, model, elemente):
        from . import plastizitaet as pl
        from .elements import solid as sl
        self.model = model
        je_typ: dict = {}
        for e in np.unique(np.asarray(elemente, np.int64)).tolist():
            typ = model.elements[int(e)].typ
            if typ in sl.OPERATOREN:
                je_typ.setdefault(typ, []).append(int(e))
        self.teile = []
        for typ, liste in je_typ.items():
            for op in sl.dehnungsoperator(model, typ, liste):
                self.teile.append((op, pl._stapel_teil(model, op)))
        self.elemente = set(int(i) for op, _d in self.teile for i in op.idx)

    def sigma_v(self, u, abzug: dict = None) -> dict:
        """{Element: groesstes sigma_v an seinen Integrationspunkten} fuer den
        FHG-Vektor ``u``; ``abzug`` {Element: (6,)} wird von jeder
        Punktspannung abgezogen (Temperatur, Vorspannung)."""
        from . import plastizitaet as pl
        from .elements import solid as sl
        u = np.asarray(u, float).reshape(-1)
        aus: dict = {}
        for op, d in self.teile:
            ue = u[d["dofs"]]
            n, P = op.n, op.P
            alpha = None
            if d.get("eas") is not None:
                alpha = pl._eas_alpha(d["eas"], d["lam"], d["mu"], np.zeros((P, n, 6)), d["lasten"], ue)
            ab = None
            if abzug:
                ab = np.zeros((n, 6))
                for a, i in enumerate(op.idx):
                    v = abzug.get(int(i))
                    if v is not None:
                        ab[a] = v
            q = np.zeros(n)
            for p in range(P):
                s = pl._spannung(d["lam"], d["mu"], sl.dehnung_mit_moden(op, p, ue, alpha))
                if ab is not None:
                    s = s - ab
                q = np.maximum(q, vergleichsspannung(s))
            for a, i in enumerate(op.idx):
                aus[int(i)] = float(q[a])
        return aus


def _abzug(model, faktoren: dict, elemente: set) -> dict:
    """{Element: (6,)} - was der Spannungsnachlauf von D eps abzieht:
    Temperatur D alpha dT (1,1,1,0,0,0) und die Anfangsspannung einer
    Vorspannung im Volumen (solver.case_loads, _post_chunk)."""
    from . import assemble as asm
    from .elements import solid as sl
    dT: dict = {}
    sig0: dict = {}
    for name, f in (faktoren or {}).items():
        lc = (getattr(model, "load_cases", None) or {}).get(name)
        if lc is None or not f:
            continue
        for tl in getattr(lc, "temp_loads", None) or []:
            if int(tl.elem) in elemente:
                dT[int(tl.elem)] = dT.get(int(tl.elem), 0.0) + float(f) * float(tl.dT)
        for v in getattr(lc, "vorspannungen", None) or []:
            if getattr(v, "art", "stab") == "koerper" and v.kraft:
                for i, s0 in asm.solid_prestress(model, v).items():
                    if int(i) in elemente:
                        sig0[int(i)] = sig0.get(int(i), 0.0) + float(f) * np.asarray(s0, float)
    aus: dict = {}
    for i, t in dT.items():
        mat = model.materials[model.elements[i].mat]
        aus[i] = sl.D_matrix(mat.E, mat.nu) @ (mat.alpha * t * np.array([1.0, 1.0, 1.0, 0, 0, 0]))
    for i, s0 in sig0.items():
        aus[i] = aus.get(i, 0.0) + s0
    return aus


def _lesen(quelle, elemente: np.ndarray) -> np.ndarray:
    """Werte je Element aus einem dict, einer Funktion oder einem Feld."""
    elemente = np.asarray(elemente, np.int64)
    if quelle is None:
        return np.zeros(len(elemente))
    if callable(quelle):
        return np.asarray(quelle(elemente), float).reshape(-1)
    if isinstance(quelle, dict):
        return np.array([float(quelle.get(int(e), 0.0)) for e in elemente.tolist()])
    return np.asarray(quelle, float)[elemente]


def _stabkraft_am_knoten(model, e: int, fl: np.ndarray, knoten: int) -> np.ndarray:
    """Endkraft (global) des Stabelements ``e`` am Knoten aus den lokalen
    Stabendkraeften ``fl`` (12,) - die Kraft, die der Knoten auf den Stab
    ausuebt."""
    from .elements import beam3d as bm
    el = model.elements[int(e)]
    X = model.nodes[el.nodes]
    T3, _L = bm.local_axes(X[0], X[1], el.roll)
    fl = np.asarray(fl, float)
    teil = fl[0:3] if int(el.nodes[0]) == int(knoten) else fl[6:9]
    return T3.T @ teil


def kraefte(model, stellen: list, res=None, *, u=None, beam_end=None, reaktionen=None,
            faktoren=None, feq=None, temp=None) -> list:
    """Die Kraft (global, (3,)) durch jede Stelle - oder None, wo sie sich
    nicht bestimmen laesst.

    * Kopplung, Stabende, starre Scheibe, Starrkoerper: Gleichgewicht am
      Master, F = R + P - Summe der Stabendkraefte dort. Haengt am Master
      mehr als Staebe, None.
    * Knotenlast, Linienlast: Summe der Lasten mit den Faktoren des Ergebnisses.
    * Knoten- und Linienlager: Summe der Auflagerkraefte.

    Mit ``res`` (Results) kommt alles aus dem Ergebnis. Ohne (Paket 3, waehrend
    der Iteration) aus ``u`` (FHG-Vektor oder (nn, 6)): die Stabendkraefte
    rechnet derselbe Nachlauf wie im Loeser (solver._post_chunk) mit ``feq``
    und ``temp`` des Lastfalls (solver.case_loads)."""
    if res is not None:
        u = res.u
        beam_end = res.beam_end
        reaktionen = res.reactions
        faktoren = (res.info or {}).get("factors")
        if not isinstance(faktoren, dict):
            faktoren = {str(res.name): 1.0}
    nn = int(model.nn)
    R = None
    if reaktionen is not None:
        R = np.asarray(reaktionen, float).reshape(-1)[:nn * 6].reshape(-1, 6)
    faktoren = faktoren or {}
    staebe = sorted({int(e) for s in stellen if s.get("master", -1) >= 0 and s.get("master_nur_staebe")
                     for e in s.get("master_staebe", [])})
    enden = dict(beam_end or {})
    fehlen = [e for e in staebe if e not in enden]
    if fehlen and u is not None:
        from . import solver
        uu = np.asarray(u, float).reshape(-1)
        if len(uu) < model.ndof:
            uu = np.concatenate([uu, np.zeros(model.ndof - len(uu))])
        for i, art, wert in solver._post_chunk(model, fehlen, {"u": uu, "feq": feq or {},
                                                              "temp": temp or {}}):
            if art == "beam":
                enden[int(i)] = wert
    aus = []
    for s in stellen:
        q = s["quelle"]
        F = None
        if "last_je_fall" in s:
            F = np.zeros(3)
            for lc, v in s["last_je_fall"].items():
                F = F + float(faktoren.get(lc, 0.0) or 0.0) * np.asarray(v, float)
        elif q in (KNOTENLAGER, LINIENLAGER):
            if R is not None:
                F = R[np.asarray(s["knoten"], np.int64), :3].sum(axis=0)
        elif s.get("master", -1) >= 0 and s.get("master_nur_staebe"):
            m = int(s["master"])
            if all(e in enden for e in s.get("master_staebe", [])):
                F = np.zeros(3)
                if R is not None:
                    F = F + R[m, :3]
                for lc, v in (s.get("master_last") or {}).items():
                    F = F + float(faktoren.get(lc, 0.0) or 0.0) * np.asarray(v, float)
                for e in s.get("master_staebe", []):
                    F = F - _stabkraft_am_knoten(model, e, enden[e], m)
        aus.append(F)
    return aus


def bewerten(model, stellen: list, kraefte_, sigma_v, eps_p=None, bezug: float = None,
             sigma_v_auswertepunkte=None) -> dict:
    """Der Kern des Urteils - fuer den Nachlauf und fuer Paket 3.

    ``kraefte_``: je Stelle (3,) oder None (:func:`kraefte`); ``sigma_v``
    (an den Integrationspunkten, siehe :class:`Punktspannungen`) und
    ``eps_p``: je Element als dict, Funktion (Elementnummern -> Werte) oder
    Feld ueber alle Elemente - gelesen werden nur die Elemente der Zonen.
    ``bezug``: Bezugskraft fuer „ohne Kraft“ (sonst die groesste
    Stellenkraft). ``sigma_v_auswertepunkte``: der Elementwert des
    Ergebnisses (Ecken und Mitte) - nur berichtet.

    Rueckgabe der Eintrag fuer ``res.info["spitzenstellen"]``: ``stellen``
    (nach Rang; je Stelle zusaetzlich ``kraft``, ``kraft_vektor``,
    ``sv_max``, ``sv_element``, ``sv_auswertepunkt_max``, ``eps_p_max``,
    ``eps_p_element``, ``fy``, ``sv_fy``, ``fy_stelle``, ``pressung_fy``,
    ``auffaellig``, ``gruende``, ``rang``), ``auffaellig`` (Nummern),
    ``kandidaten``, ``ohne_kraft``, ``grenzen``."""
    betraege = [float(np.linalg.norm(k)) if k is not None else None for k in kraefte_]
    groesste = max([b for b in betraege if b is not None], default=0.0)
    bezug = max(float(bezug or 0.0), groesste)
    fy_cache: dict = {}

    def fy_von(elemente):
        out = np.empty(len(elemente))
        for j, e in enumerate(elemente.tolist()):
            name = model.elements[int(e)].mat
            if name not in fy_cache:
                mat = model.materials.get(name)
                f = float(getattr(mat, "fy", 0.0) or 0.0) if mat is not None else 0.0
                fy_cache[name] = f if f > 0 else np.nan
            out[j] = fy_cache[name]
        return out
    behalten = []
    ohne = 0
    for s, k, F in zip(stellen, kraefte_, betraege):
        if F is not None and (bezug <= 0.0 or F <= OHNE_KRAFT * bezug):
            ohne += 1
            continue
        x = {kk: v for kk, v in s.items() if not kk.startswith("_")}
        zone = np.asarray(s.get("zone", np.zeros(0)), np.int64)
        sv = _lesen(sigma_v, zone)
        ep = _lesen(eps_p, zone)
        fy = fy_von(zone)
        x["kraft"] = F
        x["kraft_vektor"] = [float(v) for v in k] if k is not None else None
        if len(zone):
            j = int(np.argmax(sv))
            x["sv_max"], x["sv_element"] = float(sv[j]), int(zone[j])
            j = int(np.argmax(ep))
            x["eps_p_max"], x["eps_p_element"] = float(ep[j]), int(zone[j])
            q = np.where(np.isfinite(fy), sv / np.where(np.isfinite(fy), fy, 1.0), -np.inf)
            j = int(np.argmax(q))
            x["sv_fy"] = float(q[j]) if np.isfinite(q[j]) else None
            x["fy"] = float(fy[j]) if np.isfinite(fy[j]) else None
        else:
            x.update(sv_max=0.0, sv_element=-1, eps_p_max=0.0, eps_p_element=-1, sv_fy=None, fy=None)
        x["sv_auswertepunkt_max"] = (float(_lesen(sigma_v_auswertepunkte, zone).max())
                                     if sigma_v_auswertepunkte is not None and len(zone) else None)
        # Pressung ueber die Huelle - nur, wo die Huelle groesser ist als eine
        # Elementseite (A_Huelle >= 2 h^2): am Punkt ist sie eine Seite des
        # Netzes, und F / A waechst mit jeder Verfeinerung
        # f_y der Elemente an der Stelle - aus den Werkstoffen von jetzt
        an = np.asarray(s.get("elemente_an", np.zeros(0)), np.int64)
        fy_an = fy_von(an) if len(an) else np.zeros(0)
        fy_an = fy_an[np.isfinite(fy_an)]
        fys = float(fy_an.min()) if len(fy_an) else None
        x["fy_stelle"] = fys
        A = float(s.get("A_huelle", 0.0))
        h = float(s.get("h", 0.0))
        x["pressung_fy"] = (F / (A * fys) if (F is not None and fys and A > 0 and A >= FLAECHE_H2 * h * h)
                            else None)
        gruende = []
        if x["sv_fy"] is not None and x["sv_fy"] >= GRENZE_SV_FY:
            gruende.append("σ_v ≥ 2·f_y")
        if x["pressung_fy"] is not None and x["pressung_fy"] >= GRENZE_PRESSUNG:
            gruende.append("F/(A·f_y) ≥ 1")
        x["gruende"] = gruende
        x["auffaellig"] = bool(gruende)
        behalten.append(x)
    behalten.sort(key=lambda x: (x["sv_fy"] is None, -(x["sv_fy"] or 0.0), -x["sv_max"], x["nr"]))
    for r, x in enumerate(behalten, 1):
        x["rang"] = r
    return {"fassung": FASSUNG, "kandidaten": len(stellen), "ohne_kraft": ohne,
            "stellen": behalten, "auffaellig": [x["nr"] for x in behalten if x["auffaellig"]],
            "grenzen": {"sv_fy": GRENZE_SV_FY, "pressung_fy": GRENZE_PRESSUNG, "zone_h": ZONE_H,
                        "flaeche_h2": FLAECHE_H2, "flaeche_anteil": FLAECHE_ANTEIL, "punkt_h": PUNKT_H}}


def _bezugskraft(reaktionen) -> float:
    if reaktionen is None:
        return 0.0
    R = np.asarray(reaktionen, float).reshape(-1, 6)
    return float(np.abs(R[:, :3]).sum())


def punktspannungen_der_zonen(model, stellen: list) -> Punktspannungen:
    """Der Operator fuer sigma_v an den Integrationspunkten aller Zonen -
    einmal je Modell, fuer jedes Ergebnis wiederverwendet."""
    teile = [np.asarray(s.get("zone", []), np.int64) for s in stellen]
    return Punktspannungen(model, np.unique(np.concatenate(teile)) if teile else np.zeros(0, np.int64))


def auswerten(model, res, stellen: list = None, punkte: Punktspannungen = None) -> dict:
    """Nachlauf je Ergebnis: Kraft, Zone, Spitze und Rang je Stelle in
    ``res.info["spitzenstellen"]`` (und als Rueckgabe). ``stellen`` aus
    :func:`kandidaten` und ``punkte`` aus :func:`punktspannungen_der_zonen` -
    beides einmal je Modell, nicht je Ergebnis.

    sigma_v ist der Wert an den Integrationspunkten: bei fliessenden
    Elementen der Elementwert des Ergebnisses (dort schon der groesste
    Integrationspunkt), bei den uebrigen aus u (:class:`Punktspannungen`).
    Daneben steht der Elementwert (Ecken und Mitte) als
    ``sv_auswertepunkt_max``."""
    t0 = time.perf_counter()
    if stellen is None:
        stellen = kandidaten(model)
    if punkte is None:
        punkte = punktspannungen_der_zonen(model, stellen)
    solid = getattr(res, "solid_res", None) or {}
    info = res.info or {}
    eps = info.get("plastisch") or {}
    inaktiv = set(int(i) for i in (info.get("inaktiv") or []))

    def element_sv(elemente):
        S = np.array([solid.get(int(e), np.zeros(6)) for e in np.asarray(elemente).tolist()], float)
        return vergleichsspannung(S) if len(S) else np.zeros(0)
    elastisch = [e for e in punkte.elemente if e not in eps and e not in inaktiv]
    faktoren = info.get("factors") if isinstance(info.get("factors"), dict) else {str(res.name): 1.0}
    ip = punkte.sigma_v(res.u, _abzug(model, faktoren, set(elastisch))) if elastisch else {}

    def sigma_v(elemente):
        el = element_sv(elemente)
        return np.array([0.0 if int(e) in inaktiv else
                         (ip[int(e)] if int(e) in ip and int(e) not in eps else float(w))
                         for e, w in zip(np.asarray(elemente).tolist(), el)])
    erg = bewerten(model, stellen, kraefte(model, stellen, res), sigma_v, eps,
                   bezug=_bezugskraft(getattr(res, "reactions", None)), sigma_v_auswertepunkte=element_sv)
    erg["sigma_v"] = "Integrationspunkte"
    erg["zeit_s"] = time.perf_counter() - t0
    res.info["spitzenstellen"] = erg
    return erg


def nachholen(model, analysis, stellen: list = None) -> int:
    """Jedes Ergebnis der Analyse ohne Eintrag auswerten - etwa nach dem
    Laden einer Ergebnisdatei von vor dem 10.10.2026. Rueckgabe: Zahl der
    ausgewerteten Ergebnisse."""
    n = 0
    punkte = None
    for gruppe in ("cases", "combinations", "alternativen"):
        for r in (getattr(analysis, gruppe, None) or {}).values():
            if r is None or "spitzenstellen" in (r.info or {}) or not getattr(r, "solid_res", None):
                continue
            if stellen is None:
                stellen = kandidaten(model)
            if punkte is None:
                punkte = punktspannungen_der_zonen(model, stellen)
            auswerten(model, r, stellen, punkte)
            n += 1
    return n


def auffaellige_zonen(model, stellen: list, u, sigma_v, eps_p=None, *, reaktionen=None, faktoren=None,
                      feq=None, temp=None, beam_end=None) -> list:
    """Schnittstelle fuer Paket 3: welche Kandidaten sind im **aktuellen**
    Zustand auffaellig? Rueckgabe die auffaelligen Stellen (wie in
    :func:`bewerten`, je mit ``zone``) nach Rang.

    ``stellen`` aus :func:`kandidaten` (mit Zonen, einmal vor der
    Iteration); ``u`` der aktuelle FHG-Vektor; ``sigma_v``/``eps_p`` je
    Element (dict, Funktion oder Feld; sigma_v an den Integrationspunkten,
    wie sie die Plastizitaet ohnehin hat) - abgefragt werden nur die
    Elemente der Zonen, die Stabendkraefte nur an den Mastern.
    ``reaktionen``, ``faktoren``, ``feq`` und ``temp`` wie im Loeser."""
    kr = kraefte(model, stellen, None, u=u, beam_end=beam_end, reaktionen=reaktionen,
                 faktoren=faktoren, feq=feq, temp=temp)
    erg = bewerten(model, stellen, kr, sigma_v, eps_p, bezug=_bezugskraft(reaktionen))
    return [x for x in erg["stellen"] if x["auffaellig"]]


def zonen_elemente(quelle, nur_auffaellig: bool = True) -> np.ndarray:
    """Die Elemente aller Zonen (sortiert) - aus einem Ergebnis (Results), dem
    Eintrag ``res.info["spitzenstellen"]`` oder einer Liste von Stellen.
    ``nur_auffaellig``: nur die gekennzeichneten (Entscheidung 2)."""
    if hasattr(quelle, "info"):
        quelle = (quelle.info or {}).get("spitzenstellen") or {}
    stellen = quelle.get("stellen", []) if isinstance(quelle, dict) else list(quelle or [])
    teile = [np.asarray(s.get("zone", []), np.int64) for s in stellen
             if not nur_auffaellig or s.get("auffaellig")]
    return np.unique(np.concatenate(teile)) if teile else np.zeros(0, np.int64)


def zonen_maske(model, quelle, nur_auffaellig: bool = True) -> np.ndarray:
    """Wie :func:`zonen_elemente`, als Maske ueber alle Elemente des Modells."""
    m = np.zeros(len(model.elements), bool)
    m[zonen_elemente(quelle, nur_auffaellig)] = True
    return m
