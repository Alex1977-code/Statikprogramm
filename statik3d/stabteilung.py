"""Interne Stabteilung fuer Theorie II. und III. Ordnung (seit 12.11.2026).

Ein Biegestab in einem einzigen Element rechnet am verformten System mit
einer kubischen Biegelinie zwischen seinen Enden. Sind die Enden gehalten,
fehlt der Anteil der Stabkraft am Hebel der Durchbiegung ganz: der links
eingespannte, rechts gelenkige Einfeldtraeger mit Druck 0,6 N_cr und
q = 5 kN/m gab in einem Element 22,5 kNm (Theorie I) statt 44,2 kNm am
Lager, ohne Hinweis (Nachstellung vom 11.11.2026). Entscheidung des
Anwenders vom 12.11.2026: „interne Stabteilung sinnvoll vornehmen, z. B.
Anzahl Teilungen nach Länge des Stabes“.

Vorgehen: vor der Rechnung nach Theorie II. oder III. Ordnung bekommt jedes
Balkenelement intern Zwischenknoten, so dass jeder Stab (Member) mindestens
``model.netz.stabteilung`` Abschnitte hat (Vorgabe 10, wie RFEM „Teilungen
für Stäbe“; der RFEM-Import uebernimmt den Wert). Ein Element eines Stabs
der Laenge L_Stab mit der Laenge L bekommt ceil(L / (L_Stab / n)) Teile;
schon fein geteilte Staebe bleiben, wie sie sind. Ein Element ohne Stab
zaehlt als Stab fuer sich. Das Modell des Anwenders bleibt unberuehrt: die
Rechnung laeuft an einer Kopie, und das Ergebnis geht auf die Elemente und
Knoten des Modells zurueck (:func:`zurueck`). Die Schnittgroessen im Feld
setzt solver.beam_station_forces aus den Teilstuecken zusammen
(``Results.beam_teile``).

Nicht geteilt werden Fachwerkstaebe und Seile (keine Biegung), Staebe mit
Woelbkrafttorsion (eigener Freiheitsgrad) und Staebe mit Versatz der
Stabenden (Exzentrizitaet) - fuer sie bleibt der Hinweis „Stabteilung zu
grob“ (theorie2.stabteilung_grob).
"""
from __future__ import annotations

import copy
import math

import numpy as np

#: Vorgabe, wenn das Modell keine Netzeinstellungen fuehrt
TEILUNG_VORGABE = 10

#: Theorie III. Ordnung teilt doppelt so fein: das korotationale Element
#: traegt den Anteil der Stabkraft an der Durchbiegung im Element nur ueber
#: die Sehnendrehung seiner Teile. Gemessen am eingespannten, rechts
#: gelenkigen Einfeldtraeger mit Druck 0,6 N_cr und Streckenlast
#: (analytisch 44,207 kNm am Lager, 12.11.2026): 10 Teile 43,69 kNm
#: (-1,2 %), 20 Teile 44,07 kNm (-0,3 %); Theorie II. Ordnung mit 10 Teilen
#: 44,205 kNm.
FAKTOR_THEORIE3 = 2


def soll_teilung(model, faktor: int = 1) -> int:
    """Abschnitte je Stab (Netzeinstellungen.stabteilung mal ``faktor``,
    mindestens 1)."""
    try:
        n = int(getattr(getattr(model, "netz", None), "stabteilung", TEILUNG_VORGABE)
                or TEILUNG_VORGABE)
    except (TypeError, ValueError):
        n = TEILUNG_VORGABE
    return max(1, n * max(1, int(faktor)))


def teilbar(model, i: int) -> bool:
    """Wird das Element intern geteilt? Nur Balken (typ "beam") ohne
    Woelbkrafttorsion und ohne Versatz der Stabenden, mit Laenge > 0."""
    from .assemble import beam_versatz
    e = model.elements[i]
    if e.typ != "beam" or getattr(e, "woelb", False) or len(e.nodes) != 2:
        return False
    if beam_versatz(e) is not None:
        return False
    return model.element_length(i) > 0.0


#: Geteilt wird nur ein Balken, dessen Normalkraft nach Theorie I. Ordnung
#: mindestens diesen Anteil seiner Euler-Last pi² E I_min / L² (Element-
#: laenge) erreicht - nur dort aendert die Teilung das Ergebnis. Starre
#: Kurzstaebe (Anschluesse mit sehr grossem Querschnitt) bleiben so ganz:
#: zehnfach geteilt machten sie das Gleichungssystem numerisch singulaer
#: (tests/test_theorie_nebenbefund16.py, 12.11.2026). Bei einem
#: Tausendstel aendert die Teilung das Moment um weniger als etwa 0,1 %.
RELEVANZ = 1e-3

#: Zwei Balken ohne Stab gehoeren zu einer Kette, wenn ihre Achsen bis auf
#: diesen Winkel fluchten (cos)
FLUCHT_COS = 0.99995


def _ketten_laengen(model, ohne_stab: list) -> dict:
    """{Element: Laenge seiner Kette} fuer Balken, die zu keinem Stab
    (Member) gehoeren. Eine Kette ist eine gerade Folge von Balken: an jedem
    inneren Knoten treffen genau diese zwei Stabelemente zusammen, fluchtend,
    ohne Gelenk und ohne Lager. So zaehlt ein Stab, der schon in viele
    Elemente geteilt ist, als ein Stab - und wird nicht noch einmal je
    Element geteilt (12.11.2026: 64 Elemente zu je 20 Teilen machten 4,7 mm
    kurze Teile, und Theorie III. Ordnung kam ueber Rundungsrauschen nicht
    hinaus)."""
    from .assemble import LINE_TYPES
    frei = set(int(i) for i in ohne_stab)
    an_knoten: dict = {}
    for i, e in enumerate(model.elements):
        if e.typ in LINE_TYPES:
            for n in e.nodes[:2]:
                an_knoten.setdefault(int(n), []).append(i)
    # (eine Schleife ueber alle Elemente; am Drehlager 1,8 Mio. Volumen-
    # elemente, aber nur, wenn es ueberhaupt Balken ohne Stab gibt)
    gelagert = {int(s.node) for s in (getattr(model, "supports", None) or [])}
    eltern = {i: i for i in frei}

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    def gelenk_an(i, n) -> bool:
        e = model.elements[i]
        anfang = int(e.nodes[0]) == n
        return any((int(d) < 6) == anfang for d in (e.hinges or [])) or \
            any((int(d) < 6) == anfang for d, _k in (e.hinge_springs or []))

    def achse(i):
        a, b = (int(x) for x in model.elements[i].nodes[:2])
        d = model.nodes[b] - model.nodes[a]
        return d / (float(np.linalg.norm(d)) or 1.0)

    for n, els in an_knoten.items():
        if len(els) != 2 or n in gelagert:
            continue
        i, j = els
        if i not in frei or j not in frei:
            continue
        if abs(float(achse(i) @ achse(j))) < FLUCHT_COS or gelenk_an(i, n) or gelenk_an(j, n):
            continue
        ri, rj = wurzel(i), wurzel(j)
        if ri != rj:
            eltern[ri] = rj
    summe: dict = {}
    for i in frei:
        r = wurzel(i)
        summe[r] = summe.get(r, 0.0) + model.element_length(i)
    return {i: summe[wurzel(i)] for i in frei}


def relevant(model, i: int, N: float) -> bool:
    """Traegt Element ``i`` mit der Normalkraft N so viel, dass die Teilung
    zaehlt (:data:`RELEVANZ`)?"""
    e = model.elements[i]
    sec = model.sections.get(e.sec) if hasattr(model.sections, "get") else model.sections[e.sec]
    if sec is None:
        return True
    I = min(float(sec.Iy or 0.0), float(sec.Iz or 0.0))
    L = model.element_length(i)
    E = float(model.materials[e.mat].E)
    if I <= 0 or L <= 0 or E <= 0:
        return True
    return abs(float(N)) >= RELEVANZ * math.pi ** 2 * E * I / L ** 2


def kraefte_theorie1(model, system, factors: dict) -> dict:
    """{Balken: Normalkraft} nach Theorie I. Ordnung fuer ``factors`` -
    wie theorie2.normalkraefte_kg, samt Anfangsdehnung."""
    from .solver import case_loads, case_prescribed, anfangsnormalkraefte
    from .theorie2 import normalkraefte_kg
    aktiv = getattr(system, "aktiv", None)
    F, _feq, _q, _temp = case_loads(model, factors, aktiv)
    u = system.solve(F, us=case_prescribed(model, factors))
    return normalkraefte_kg(model, u, aktiv, anfangsnormalkraefte(model, factors, aktiv))


def teilzahlen(model, aktiv=None, faktor: int = 1, kraefte: dict = None) -> dict:
    """{Element: Zahl der Teile > 1} - nach der Laenge des Stabs (Member;
    ohne Stab nach der Laenge der geraden Kette, :func:`_ketten_laengen`).
    ``kraefte`` {Element: Normalkraft nach Theorie I. Ordnung}: dann nur die
    Balken, an denen sie zaehlt (:func:`relevant`); ohne sie alle."""
    soll = soll_teilung(model, faktor)
    if soll <= 1:
        return {}
    ne = len(model.elements)
    stab_L: dict = {}
    for mem in (getattr(model, "members", None) or {}).values():
        idx = [int(i) for i in mem.elements if 0 <= int(i) < ne]
        Lm = sum(model.element_length(i) for i in idx)
        for i in idx:
            stab_L[i] = max(stab_L.get(i, 0.0), Lm)
    balken = [i for i, e in enumerate(model.elements) if e.typ == "beam"]
    balken = [i for i in balken if teilbar(model, i)]
    ohne = [i for i in balken if i not in stab_L]
    if ohne:
        stab_L.update(_ketten_laengen(model, ohne))
    out = {}
    for i in balken:
        if aktiv is not None and not aktiv[i]:
            continue
        if kraefte is not None and not relevant(model, i, kraefte.get(i, 0.0)):
            continue
        L = model.element_length(i)
        Lm = stab_L.get(i, 0.0) or L
        n = min(soll, max(1, math.ceil(L * soll / Lm - 1e-9)))
        if n > 1:
            out[i] = n
    return out


def _vorwaerts(model, elems: list, k: int) -> bool:
    """Laeuft Element elems[k] in Richtung der Kette des Stabs?"""
    a, b = (int(x) for x in model.elements[elems[k]].nodes[:2])
    if k + 1 < len(elems):
        nach = {int(x) for x in model.elements[elems[k + 1]].nodes[:2]}
        return b in nach or a not in nach
    if k > 0:
        vor = {int(x) for x in model.elements[elems[k - 1]].nodes[:2]}
        return a in vor or b not in vor
    return True


class Abbildung:
    """Wie die Teile im feinen Modell zu den Elementen des Modells gehoeren."""

    def __init__(self, nn: int, ne: int):
        self.nn = nn                    # Knoten des Modells (die ersten im feinen)
        self.ne = ne                    # Elemente des Modells (die ersten im feinen)
        self.teile: dict = {}           # Element -> [Teilelemente, Anfang zuerst]
        self.eltern: dict = {}          # Teilelement (>= ne) -> Element

    def element(self, j: int) -> int:
        """Das Element des Modells zu Element ``j`` des feinen Modells."""
        return int(self.eltern.get(int(j), int(j)))


def _last_teilen(bl, L: float, x0: float, x1: float, j: int):
    """Den Anteil einer Stablast ``bl`` auf dem Teilstueck [x0, x1] als
    Stablast auf Element ``j`` - oder None. q laeuft linear zwischen a und b."""
    a = max(0.0, float(getattr(bl, "a", 0.0) or 0.0))
    b = L if getattr(bl, "b", None) is None else min(float(bl.b), L)
    lo, hi = max(a, x0), min(b, x1)
    if hi <= lo:
        return None
    q1 = np.asarray(bl.q, float)
    q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
    def q_bei(x):
        t = 0.0 if b <= a else (x - a) / (b - a)
        return (1.0 - t) * q1 + t * q2
    neu = copy.copy(bl)
    neu.elem = int(j)
    neu.q = [float(v) for v in q_bei(lo)]
    neu.q2 = [float(v) for v in q_bei(hi)]
    h = x1 - x0
    tol = 1e-12 * max(L, 1.0)
    neu.a = 0.0 if lo - x0 <= tol else float(lo - x0)
    neu.b = None if x1 - hi <= tol else float(hi - x0)
    if neu.b is not None and neu.b >= h:
        neu.b = None
    return neu


def teilen(model, aktiv=None, zahlen: dict = None):
    """Das feine Modell: (Modell, Abbildung, aktiv) - oder None, wenn kein
    Element zu teilen ist. ``model`` bleibt unveraendert."""
    zahlen = teilzahlen(model, aktiv) if zahlen is None else zahlen
    if not zahlen:
        return None
    nn, ne = len(model.nodes), len(model.elements)
    abb = Abbildung(nn, ne)
    m2 = copy.copy(model)
    elemente = list(model.elements)
    neue_knoten = []
    neue_elemente = []
    for i in sorted(zahlen):
        n = int(zahlen[i])
        e = model.elements[i]
        n0, n1 = int(e.nodes[0]), int(e.nodes[1])
        X0, X1 = model.nodes[n0], model.nodes[n1]
        ids = [n0] + [nn + len(neue_knoten) + k for k in range(n - 1)] + [n1]
        for k in range(1, n):
            neue_knoten.append(X0 + (X1 - X0) * (k / n))
        anfang = [int(d) for d in (e.hinges or []) if int(d) < 6]
        # an beiden Enden frei (etwa die Torsion): das ungeteilte Element
        # uebertraegt dort nichts; die Kette bleibt am Ende angeschlossen,
        # sonst haetten ihre Zwischenknoten keine Steifigkeit in diesem FHG
        ende = [int(d) for d in (e.hinges or []) if int(d) >= 6 and int(d) - 6 not in anfang]
        f_anfang = [(int(d), k) for d, k in (e.hinge_springs or []) if int(d) < 6]
        f_ende = [(int(d), k) for d, k in (e.hinge_springs or []) if int(d) >= 6]
        teile = []
        for k in range(n):
            t = e.kopie()
            t.nodes = [ids[k], ids[k + 1]]
            t.hinges = (anfang if k == 0 else []) + (ende if k == n - 1 else [])
            t.hinge_springs = (f_anfang if k == 0 else []) + (f_ende if k == n - 1 else [])
            if k == 0:
                elemente[i] = t
                teile.append(i)
            else:
                j = ne + len(neue_elemente)
                neue_elemente.append(t)
                teile.append(j)
                abb.eltern[j] = i
        abb.teile[i] = teile
    m2.nodes = np.vstack([np.asarray(model.nodes, float), np.asarray(neue_knoten, float).reshape(-1, 3)])
    m2.elements = elemente + neue_elemente
    # Staebe: die Teile in Richtung der Kette
    staebe = {}
    for name, mem in (getattr(model, "members", None) or {}).items():
        neu = copy.copy(mem)
        els = [int(x) for x in mem.elements]
        liste = []
        for k, i in enumerate(els):
            t = abb.teile.get(i)
            if t is None:
                liste.append(i)
            else:
                liste.extend(t if _vorwaerts(model, els, k) else list(reversed(t)))
        neu.elements = liste
        staebe[name] = neu
    m2.members = staebe
    # Lastfaelle: Stablasten und Temperaturlasten auf die Teile
    faelle = {}
    for name, lc in model.load_cases.items():
        neu = copy.copy(lc)
        bls = []
        for bl in lc.beam_loads:
            t = abb.teile.get(int(bl.elem))
            if t is None:
                bls.append(bl)
                continue
            L = model.element_length(int(bl.elem))
            h = L / len(t)
            for k, j in enumerate(t):
                s = _last_teilen(bl, L, k * h, (k + 1) * h, j)
                if s is not None:
                    bls.append(s)
        tls = []
        for tl in lc.temp_loads:
            t = abb.teile.get(int(tl.elem))
            if t is None:
                tls.append(tl)
                continue
            for j in t:
                s = copy.copy(tl)
                s.elem = int(j)
                tls.append(s)
        neu.beam_loads = bls
        neu.temp_loads = tls
        faelle[name] = neu
    m2.load_cases = faelle
    m2._stabteilung_eltern = dict(abb.eltern)
    # Zwischenspeicher, die an der Elementzahl haengen, rechnet das feine
    # Modell selbst neu (Schluessel mit len(elements)); die der Situationen
    # und Pruefungen gelten nicht
    for attr in ("_federn_cache",):
        if attr in vars(m2):
            delattr(m2, attr)
    aktiv2 = None
    if aktiv is not None:
        a = np.asarray(aktiv, bool)
        aktiv2 = np.concatenate([a, np.array([a[abb.eltern[j]] for j in range(ne, len(m2.elements))],
                                             dtype=bool)])
    return m2, abb, aktiv2


def fein_system(model, system, factors: dict):
    """(feines Modell, sein StaticSystem, Abbildung) zu ``model``, ``system``
    und den Lastfaktoren ``factors`` (sie bestimmen ueber die Normalkraefte
    nach Theorie I. Ordnung, welche Balken geteilt werden) - je System und
    Teilung gemerkt - oder None ohne zu teilendes Element."""
    aktiv = getattr(system, "aktiv", None)
    if not teilzahlen(model, aktiv):
        return None
    zahlen = teilzahlen(model, aktiv, kraefte=kraefte_theorie1(model, system, factors))
    if not zahlen:
        return None
    schluessel = (len(model.nodes), len(model.elements), tuple(sorted(zahlen.items())),
                  None if aktiv is None else np.asarray(aktiv, bool).tobytes())
    alt = getattr(system, "_stabteilung", None) if system is not None else None
    if alt is not None and alt[0] == schluessel:
        return alt[1]
    from .solver import StaticSystem
    m2, abb, aktiv2 = teilen(model, aktiv, zahlen)
    sys2 = StaticSystem(m2, aktiv=aktiv2, situation=getattr(system, "situation", "") or "")
    fein = (m2, sys2, abb)
    if system is not None:
        try:
            system._stabteilung = (schluessel, fein)
        except AttributeError:
            pass
    return fein


def zurueck(model, res2, abb: Abbildung):
    """Das Ergebnis des feinen Modells auf die Knoten und Elemente von
    ``model``: Verschiebungen und Reaktionen der Knoten des Modells,
    Stabendkraefte je Element aus dem ersten und letzten Teil, die Teile
    selbst in ``beam_teile`` fuer das Feld."""
    from .solver import Results
    res = Results(name=res2.name, kind=res2.kind, model=model)
    nn, ne = abb.nn, abb.ne
    if res2.u is not None:
        res.u = np.asarray(res2.u)[:nn].copy()
    if res2.reactions is not None:
        res.reactions = np.asarray(res2.reactions)[:nn].copy()
    for attr in ("shell_res", "solid_res", "solid_mittel", "feder_res", "grenzschicht_res",
                 "bimomente"):
        setattr(res, attr, {i: v for i, v in getattr(res2, attr).items() if int(i) < ne})
    res.solid_knoten = res2.solid_knoten
    res.woelb = {k: v for k, v in res2.woelb.items() if int(k) < nn}
    for attr in ("contact", "kontaktzustand", "contact_forces", "singular", "modes", "freqs",
                 "buckling_factors", "buckling_modes"):
        setattr(res, attr, getattr(res2, attr))
    if res.contact_forces is not None:
        res.contact_forces = np.asarray(res.contact_forces)[:nn]
    res.info = dict(res2.info)
    if "inaktiv" in res.info:
        res.info["inaktiv"] = [int(i) for i in res.info["inaktiv"] if int(i) < ne]
    res.info["stabteilung"] = {int(i): len(t) for i, t in abb.teile.items()}
    teile_th2 = getattr(res2, "beam_th2", None) or {}
    beam_teile = {}
    for i in range(ne):
        t = abb.teile.get(i)
        if t is None:
            if i in res2.beam_end:
                res.beam_end[i] = res2.beam_end[i]
            if i in res2.beam_q:
                res.beam_q[i] = res2.beam_q[i]
            if i in teile_th2:
                res.beam_th2[i] = teile_th2[i]
            continue
        if not all(j in res2.beam_end for j in t):
            continue
        a, b = np.asarray(res2.beam_end[t[0]], float), np.asarray(res2.beam_end[t[-1]], float)
        res.beam_end[i] = np.concatenate([a[:6], b[6:]])
        L = model.element_length(i)
        h = L / len(t)
        zeilen = []
        for k, j in enumerate(t):
            q = res2.beam_q.get(j)
            if q is not None:
                q = np.asarray(q, float).reshape(-1, 8).copy()
                q[:, :2] += k * h
                zeilen.append(q)
        if zeilen:
            res.beam_q[i] = np.vstack(zeilen)
        if all(j in teile_th2 for j in t):
            ua, ub = np.asarray(teile_th2[t[0]], float), np.asarray(teile_th2[t[-1]], float)
            res.beam_th2[i] = np.concatenate([ua[:6], ub[6:]])
        beam_teile[i] = {
            "h": h,
            "end": np.array([np.asarray(res2.beam_end[j], float) for j in t]),
            "q": [None if res2.beam_q.get(j) is None else np.asarray(res2.beam_q[j], float)
                  for j in t],
            "th2": (np.array([np.asarray(teile_th2[j], float) for j in t])
                    if all(j in teile_th2 for j in t) else None),
        }
    res.beam_teile = beam_teile
    res._cache.clear()
    return res
