"""Lage der Schalenelemente: einheitlich zur Flaeche ausrichten (12.11.2026).

Der Anwender: „die lage von schalenelementen sollte der user frei bestimmen
können und sie dürfte grundsätzlich nicht an der berechnung ändern“.

Die Knotenfolge eines Schalenelements legt seine lokale z-Achse fest (oben,
unten). Bis zu diesem Stand rechnete das Programm an einigen Stellen mit der
Normalen des einzelnen Elements, wo die Flaeche gemeint war: eine
Flaechenlast „senkrecht zur Flaeche“ wirkte an einem gespiegelten Element
verkehrt herum (Platte 1 x 1 m, 8 x 8 shell4, ein Element gespiegelt:
ΣR_z 9 687,5 statt 10 000 N), ebenso dT_z, Wasserdruck und Wind an
Schalen, und die Knotenmittel von m_x, m_y, n_xy, τ_xy mischten Werte
verschieden gerichteter Elemente.

Darum werden die Schalenelemente ausgerichtet:

* **Elemente einer Flaeche** (``Flaeche.elemente``) zur Normalen der Flaeche
  aus ihrem Randumlauf (Newell, wie beim Vernetzen: der Vernetzer legt die
  Elemente im Umlauf des Randes an). Ausgerichtet wird je zusammenhaengendem
  Stueck ueber gemeinsame Kanten; das Vorzeichen entscheidet die
  Vektorflaeche des Stuecks gegen die Flaechennormale. Bei einer ebenen
  Flaeche ist das je Element n · N > 0; bei einer gewoelbten (Mantel einer
  Bohrung) ist die Vektorflaeche nach dem Satz von Stokes genau die halbe
  Newell-Summe ihres Randes - das Stueck folgt dem Umlauf. Ist die
  Flaechennormale null (geschlossener Mantel), bleibt das Element mit der
  kleinsten Nummer, wie es ist.
* **Elemente ohne Flaeche** (Nastran, Abaqus, gmsh): je zusammenhaengendem
  Stueck einheitlich zum Element mit der kleinsten Nummer. Verbunden sind
  zwei Elemente ueber eine Kante, an der genau sie beide liegen; an einer
  Kante mit drei und mehr Elementen (Steg auf Gurt) nur die, die in einer
  Ebene auf verschiedenen Seiten der Kante liegen.

Umgedreht wird so, dass die Physik bleibt (:data:`WENDEN`): der Umlauf
kehrt sich um, Knoten 0 bleibt (shell4 [0, 3, 2, 1] usw.). Die Umkehr ist
ihre eigene Umkehrung: ein gespiegeltes Element bekommt genau seine fruehere
Knotenfolge zurueck, mit derselben Diagonale 0-2 (an ihr haengen die
Kontaktfacetten, die Lastteilung der DKT-Vierecke und die Abtastung des
Wasserdrucks). Die lokale z-Achse kehrt sich um; die lokale x-Achse liegt
danach an der Kante vom Knoten 0 zum bisher letzten Eckknoten (Winkel g zur
alten x-Achse), y = z x x. Mit dem Element drehen:

* Elementlasten senkrecht (``FaceLoad`` ohne Richtung, p in lokal z): p -> -p.
  Eine Last mit globaler Richtung bleibt.
* Temperaturunterschied ``TempLoad.dT_z`` (oben - unten): dT_z -> -dT_z.
* Ein geschichteter Aufbau **am einzelnen Element** (``ShellProp.lagen``, von
  unten nach oben, Faserwinkel a zur lokalen x-Achse - etwa aus einem
  Nastran-PCOMP ohne Flaeche): Folge umgekehrt, Faserwinkel g - a (die Faser
  cos a x + sin a y liegt im neuen System bei g - a); isotrope Lagen behalten
  ihren Winkel. Ist der gewendete Aufbau ein anderer, bekommt das Element einen
  vorhandenen gleichen oder einen neuen „<Name> gewendet“.
* Ein Aufbau, der **der Flaeche** gehoert (Elementaufbau = ``Flaeche.dicke``),
  ist zur Flaechennormalen definiert, nicht zum Element (Entscheidung vom
  12.11.2026): das ausgerichtete Element behaelt ihn unveraendert.
* Aus Objektlasten abgeleitete Elementlasten (``_geo``) werden nicht
  gedreht, sondern neu verteilt (:meth:`Model.lasten_verteilen`): sie gehoeren
  zur Flaeche, und an der Flaeche ist jetzt jedes Element gleich gerichtet.

Was die Normale nicht kennt, bleibt: Flaechenlager (Einflussflaechen, in
Flaechenachsen ueber supports._facettennormalen schon lageunabhaengig),
Kontakt an Schalen (die Facette wird zum Slave gerichtet). Ergebnisse
entstehen in der Rechnung neu; die Oberflaeche erkennt am Modellstand (Knoten
je Element), dass ein altes Ergebnis nicht mehr passt.

Aufgerufen wird :func:`schalen_ausrichten` beim Vernetzen (je Flaeche), am
Ende jedes Imports, zu Beginn der Lastgeneratoren Wind und Wasserdruck und
vor jeder Rechnung (solver: solve_static, solve_cases, solve_all,
solve_modal, solve_buckling und jedes StaticSystem; die Oberflaeche vor dem
Festhalten des Modellstands).
"""
from __future__ import annotations

import math

import numpy as np

SCHALEN = ("shell3", "shell4", "shell6", "shell8")
#: Neue Knotenfolge eines umgedrehten Elements (Indizes in die alte): der
#: Umlauf kehrt sich um, Knoten 0 bleibt, die Seitenmitten folgen ihren Kanten
#: (shell6: Mitten der Kanten 0-1, 1-2, 2-0; shell8: 0-1, 1-2, 2-3, 3-0). Jede
#: Folge ist ihre eigene Umkehrung.
WENDEN = {
    "shell3": [0, 2, 1],
    "shell4": [0, 3, 2, 1],
    "shell6": [0, 2, 1, 5, 4, 3],
    "shell8": [0, 3, 2, 1, 7, 6, 5, 4],
}
_ECKEN = {"shell3": 3, "shell4": 4, "shell6": 3, "shell8": 4}
#: zwei Elemente an einer Kante mit drei und mehr Elementen gelten als
#: Fortsetzung, wenn ihre Ebenen um hoechstens 10° abweichen
_KOPLANAR = math.cos(math.radians(10.0))
#: so viele Elementnummern stehen hoechstens in einer Meldung
_LISTE_MAX = 30


# --------------------------------------------------------------------------
# Geometrie
# --------------------------------------------------------------------------
def _schalen_indizes(model) -> list:
    return [i for i, e in enumerate(model.elements) if e.typ in _ECKEN and len(e.nodes) >= _ECKEN[e.typ]]


def _ecken(model, idx: list) -> tuple:
    """(Eckknoten (n, 4; beim Dreieck die vierte Spalte -1), Eckenzahl (n,))."""
    n = len(idx)
    C = np.full((n, 4), -1, np.int64)
    ne = np.zeros(n, np.int64)
    els = model.elements
    for p, i in enumerate(idx):
        e = els[i]
        k = _ECKEN[e.typ]
        C[p, :k] = e.nodes[:k]
        ne[p] = k
    return C, ne


def _vektorflaechen(model, idx: list, C=None, ne=None) -> np.ndarray:
    """Vektorflaeche je Element (Flaeche mal Normale, aus den Eckknoten)."""
    if C is None:
        C, ne = _ecken(model, idx)
    X = np.asarray(model.nodes, float)
    V = np.zeros((len(idx), 3))
    v4 = ne == 4
    if v4.any():
        c = C[v4]
        V[v4] = 0.5 * np.cross(X[c[:, 2]] - X[c[:, 0]], X[c[:, 3]] - X[c[:, 1]])
    v3 = ~v4
    if v3.any():
        c = C[v3]
        V[v3] = 0.5 * np.cross(X[c[:, 1]] - X[c[:, 0]], X[c[:, 2]] - X[c[:, 0]])
    return V


def flaechennormale(model, f):
    """Normale einer Flaeche aus ihrem Randumlauf (Newell, abgetastete
    Raender) - nicht normiert; None, wenn der Rand nicht zu lesen ist."""
    try:
        P = np.asarray(f.randpunkte(model), float)
    except Exception:                        # noqa: BLE001 - unlesbarer Rand: kein Bezug
        return None
    if P.ndim != 2 or len(P) < 3:
        return None
    return 0.5 * np.cross(P, np.roll(P, -1, axis=0)).sum(axis=0)


# --------------------------------------------------------------------------
# Zusammenhang und relative Lage
# --------------------------------------------------------------------------
def _stuecke(model, idx: list, V: np.ndarray, C=None, ne=None) -> tuple:
    """Zusammenhaengende Stuecke der Elemente ``idx`` (aufsteigend) und ihre
    Lage relativ zum Element mit der kleinsten Nummer des Stuecks.

    Rueckgabe (stueck je Position, Bezugsposition je Stueck, s je Position
    +1/-1, Zahl widersprechender Elemente)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    n = len(idx)
    if n == 0:
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0, int), 0
    if C is None:
        C, ne = _ecken(model, idx)
    # gerichtete Eckkanten je Element: k -> k+1 (beim Dreieck 2 -> 0)
    nach = np.roll(C, -1, axis=1)
    drei = ne == 3
    nach[drei, 2] = C[drei, 0]
    pos = np.repeat(np.arange(n), 4)
    a = C.reshape(-1)
    b = nach.reshape(-1)
    gilt = (a >= 0) & (b >= 0) & (a != b)
    a, b, pos = a[gilt], b[gilt], pos[gilt]
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    rich = np.where(a < b, 1, -1)
    nn = int(hi.max()) + 1 if len(hi) else 1
    schl = lo * nn + hi
    ordnung = np.argsort(schl, kind="stable")
    schl_s = schl[ordnung]
    anfang = np.flatnonzero(np.r_[True, schl_s[1:] != schl_s[:-1]])
    anzahl = np.diff(np.r_[anfang, len(schl_s)])
    # Kanten an genau zwei Elementen: verbunden; gleiche Lage, wenn die beiden
    # die Kante gegenlaeufig durchlaufen
    zwei = anfang[anzahl == 2]
    i1, i2 = ordnung[zwei], ordnung[zwei + 1]
    ok = pos[i1] != pos[i2]
    a_l = [pos[i1][ok]]
    b_l = [pos[i2][ok]]
    g_l = [(rich[i1] != rich[i2])[ok]]
    # Kanten an drei und mehr Elementen (Steg auf Gurt): nur ebene
    # Fortsetzungen auf verschiedenen Seiten der Kante
    viele = np.flatnonzero(anzahl >= 3)
    if len(viele):
        Vn = V / np.maximum(np.linalg.norm(V, axis=1), 1e-300)[:, None]
        X = np.asarray(model.nodes, float)
        zus_a, zus_b, zus_g = [], [], []
        for gi in viele:
            g = ordnung[anfang[gi]:anfang[gi] + anzahl[gi]]
            m = 0.5 * (X[lo[g[0]]] + X[hi[g[0]]])
            t = X[hi[g[0]]] - X[lo[g[0]]]
            t = t / (np.linalg.norm(t) or 1.0)
            for u in range(len(g)):
                for v in range(u + 1, len(g)):
                    p, q = int(pos[g[u]]), int(pos[g[v]])
                    if p == q or abs(float(Vn[p] @ Vn[q])) < _KOPLANAR:
                        continue
                    cp = X[C[p, :ne[p]]].mean(axis=0) - m
                    cq = X[C[q, :ne[q]]].mean(axis=0) - m
                    cp -= (cp @ t) * t
                    cq -= (cq @ t) * t
                    if float(cp @ cq) >= 0.0:
                        continue
                    zus_a.append(p)
                    zus_b.append(q)
                    zus_g.append(rich[g[u]] != rich[g[v]])
        a_l.append(np.asarray(zus_a, np.int64))
        b_l.append(np.asarray(zus_b, np.int64))
        g_l.append(np.asarray(zus_g, bool))
    a = np.concatenate(a_l).astype(np.int64)
    b = np.concatenate(b_l).astype(np.int64)
    gl = np.concatenate(g_l).astype(bool)
    G = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
    n_st, stueck = connected_components(G, directed=False)
    # Doppelgraph: Knoten p (wie es ist) und p + n (umgedreht)
    a2 = np.concatenate([a[gl], a[gl] + n, a[~gl], a[~gl] + n])
    b2 = np.concatenate([b[gl], b[gl] + n, b[~gl] + n, b[~gl]])
    G2 = coo_matrix((np.ones(len(a2)), (a2, b2)), shape=(2 * n, 2 * n))
    _k, L = connected_components(G2, directed=False)
    bezug = np.full(n_st, n, np.int64)
    np.minimum.at(bezug, stueck, np.arange(n))
    s = np.where(L[:n] == L[bezug[stueck]], 1, -1)
    widerspruch = int(np.count_nonzero(L[:n] == L[n:]))
    return stueck, bezug, s, widerspruch


# --------------------------------------------------------------------------
# Plan: was umzudrehen ist
# --------------------------------------------------------------------------
def plan(model) -> list:
    """Was :func:`schalen_ausrichten` tun wuerde, ohne das Modell zu aendern.

    Rueckgabe [(art, name, umzudrehen, widerspruch)]: art "flaeche" (name =
    Flaechenname) oder "stueck" (name = Element mit der kleinsten Nummer des
    Stuecks ohne Flaeche); umzudrehen die Elementnummern (aufsteigend)."""
    alle = set(_schalen_indizes(model))
    if not alle:
        return []
    aus: list = []
    erledigt: set = set()
    for name, f in (getattr(model, "flaechen", None) or {}).items():
        idx = sorted({int(e) for e in (f.elemente or []) if int(e) in alle} - erledigt)
        if not idx:
            continue
        erledigt.update(idx)
        aus.extend(_plan_flaeche(model, f, idx))
    rest = sorted(alle - erledigt)
    if rest:
        C, ne = _ecken(model, rest)
        V = _vektorflaechen(model, rest, C, ne)
        stueck, bezug, s, wid = _stuecke(model, rest, V, C, ne)
        neg = np.flatnonzero(s < 0)
        if len(neg):
            je: dict = {}
            for p in neg.tolist():               # aufsteigend: die Nummern bleiben sortiert
                je.setdefault(int(stueck[p]), []).append(rest[p])
            for k in sorted(je, key=lambda k_: int(bezug[k_])):
                aus.append(("stueck", int(rest[int(bezug[k])]), je[k], 0))
        if wid:
            aus.append(("stueck", -1, [], wid))
    return aus


def _plan_flaeche(model, f, idx: list) -> list:
    C, ne = _ecken(model, idx)
    V = _vektorflaechen(model, idx, C, ne)
    stueck, bezug, s, wid = _stuecke(model, idx, V, C, ne)
    N = flaechennormale(model, f)
    if N is not None:
        # je Stueck: Vektorflaeche (relativ zum Bezugselement) gegen die
        # Flaechennormale; nahe null (geschlossener Mantel) bleibt das Bezugselement
        S = np.bincount(stueck, weights=s * (V @ N), minlength=len(bezug))
        groesse = np.bincount(stueck, weights=np.linalg.norm(V, axis=1),
                              minlength=len(bezug)) * float(np.linalg.norm(N))
        s = s * np.where(S < -1e-9 * groesse, -1, 1)[stueck]
    drehen = [idx[int(p)] for p in np.flatnonzero(s < 0)]
    if not drehen and not wid:
        return []
    return [("flaeche", f.name, sorted(drehen), wid)]


def gegen_flaeche(model, f) -> set:
    """Die Schalenelemente der Flaeche ``f``, die gegen ihre Flaeche liegen
    (die :func:`schalen_ausrichten` umdrehen wuerde)."""
    idx = sorted({int(e) for e in (f.elemente or [])
                  if 0 <= int(e) < len(model.elements) and model.elements[int(e)].typ in WENDEN})
    if not idx:
        return set()
    try:
        return {int(e) for _a, _n, drehen, _w in _plan_flaeche(model, f, idx) for e in drehen}
    except Exception:                        # noqa: BLE001 - nicht pruefbar: wie es ist
        return set()


def uneinheitlich(model) -> bool:
    """Gibt es Schalenelemente, die gegen ihre Flaeche bzw. ihr Stueck
    liegen? (Merkmal der Verfahrenstabelle, Stand 31)"""
    try:
        return any(drehen for _a, _n, drehen, _w in plan(model))
    except Exception:                        # noqa: BLE001 - nicht pruefbar: nicht betroffen
        return False


# --------------------------------------------------------------------------
# Umdrehen
# --------------------------------------------------------------------------
def _winkel(lage: dict) -> float:
    return float(lage.get("winkel", 0.0) or 0.0)


def _orthotrop(lage: dict) -> bool:
    return "E1" in lage


def _winkel_halb(w: float) -> float:
    """Faserwinkel auf (-pi/2, pi/2] - eine Faser hat kein Vorzeichen."""
    w = math.fmod(float(w), math.pi)
    if w <= -math.pi / 2:
        w += math.pi
    elif w > math.pi / 2:
        w -= math.pi
    return 0.0 if abs(w) < 1e-15 else w


def gewendete_lagen(lagen: list, g: float = 0.0) -> list:
    """Der Schichtaufbau, von der anderen Seite gesehen: Folge umgekehrt
    (unten wird oben). ``g`` ist der Winkel der neuen x-Achse zur alten (in
    der alten Ebene gemessen); der Faserwinkel a einer orthotropen Lage wird
    g - a. Isotrope Lagen behalten ihren Winkel."""
    out = []
    for lage in reversed(list(lagen or [])):
        neu = dict(lage)
        if _orthotrop(lage):
            neu["winkel"] = _winkel_halb(g - _winkel(lage))
        out.append(neu)
    return out


def _lagen_gleich(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if set(x) - {"winkel"} != set(y) - {"winkel"}:
            return False
        for k in x:
            if k != "winkel" and x[k] != y[k]:
                return False
        if _orthotrop(x):
            d = (_winkel(x) - _winkel(y)) % math.pi
            if min(d, math.pi - d) > 1e-9:
                return False
    return True


def _hat_orthotrop(prop) -> bool:
    return any(_orthotrop(x) for x in (getattr(prop, "lagen", None) or []))


def _aufbau_fuer_gewendet(model, name: str, g: float, merk: dict) -> str:
    """Name des Schalenaufbaus, den ein umgedrehtes Element mit Aufbau
    ``name`` braucht - derselbe, wenn der Aufbau von beiden Seiten gleich
    ist, sonst ein vorhandener gleicher oder ein neuer „<name> gewendet“."""
    prop = (getattr(model, "shells", None) or {}).get(name)
    if prop is None or not getattr(prop, "lagen", None):
        return name
    schl = (name, round(_winkel_halb(g), 9)) if _hat_orthotrop(prop) else (name,)
    if schl in merk:
        return merk[schl]
    neu = gewendete_lagen(prop.lagen, g)
    if _lagen_gleich(neu, prop.lagen):
        merk[schl] = name
        return name
    for anderer in model.shells.values():
        if (anderer.name != name and getattr(anderer, "lagen", None)
                and getattr(anderer, "formulierung", "") == getattr(prop, "formulierung", "")
                and _lagen_gleich(anderer.lagen, neu)):
            merk[schl] = anderer.name
            return anderer.name
    from .model import ShellProp
    basis = f"{name} gewendet"
    neu_name, k = basis, 2
    while neu_name in model.shells:
        neu_name = f"{basis} {k}"
        k += 1
    model.add_shell_prop(ShellProp(neu_name, float(prop.t), lagen=neu,
                                   formulierung=getattr(prop, "formulierung", "")))
    merk[schl] = neu_name
    return neu_name


def _neue_x_winkel(model, alt: list, neu: list) -> float:
    """Winkel der x-Achse des umgedrehten Elements (Kante neu 0 -> neu 1) zur
    x-Achse vorher (Kante alt 0 -> alt 1), in der Ebene des Elements."""
    from .elements import shell_rm
    X0 = np.asarray(model.nodes[[int(k) for k in alt]], float)
    T0 = shell_rm.schalen_frame(X0)[0]
    v = np.asarray(model.nodes[int(neu[1])] - model.nodes[int(neu[0])], float)
    return float(math.atan2(float(v @ T0[1]), float(v @ T0[0])))


def elemente_wenden(model, elemente) -> bool:
    """Die Elemente umdrehen und mitnehmen, was an ihren lokalen Achsen
    haengt (siehe Moduldoku). Rueckgabe: sind aus Objektlasten abgeleitete
    Elementlasten betroffen (dann muss neu verteilt werden)?"""
    menge = {int(i) for i in elemente
             if 0 <= int(i) < len(model.elements) and model.elements[int(i)].typ in WENDEN}
    if not menge:
        return False
    # der Aufbau der Flaeche gilt zur Flaechennormalen und bleibt
    flaechenaufbau: dict = {}
    for f in (getattr(model, "flaechen", None) or {}).values():
        if f.dicke:
            for e in (f.elemente or []):
                if int(e) in menge:
                    flaechenaufbau.setdefault(int(e), f.dicke)
    shells = getattr(model, "shells", None) or {}
    merk: dict = {}
    for i in sorted(menge):
        e = model.elements[i]
        w = WENDEN[e.typ]
        alt = list(e.nodes)
        e.nodes = [alt[j] for j in w] + alt[len(w):]
        if not e.sec or flaechenaufbau.get(i) == e.sec:
            continue
        prop = shells.get(e.sec)
        if prop is None or not getattr(prop, "lagen", None):
            continue
        g = _neue_x_winkel(model, alt, e.nodes) if _hat_orthotrop(prop) else 0.0
        e.sec = _aufbau_fuer_gewendet(model, e.sec, g, merk)
    geo = False
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for fl in lc.face_loads:
            if int(fl.elem) not in menge:
                continue
            if getattr(fl, "_geo", False):
                geo = True
            elif fl.direction is None:
                fl.p = -float(fl.p)
        for tl in lc.temp_loads:
            if int(tl.elem) not in menge:
                continue
            if getattr(tl, "_geo", False):
                geo = geo or bool(float(getattr(tl, "dT_z", 0.0) or 0.0))
            elif float(getattr(tl, "dT_z", 0.0) or 0.0):
                tl.dT_z = -float(tl.dT_z)
    return geo


def _liste(nummern: list) -> str:
    n = len(nummern)
    if n <= _LISTE_MAX:
        return ", ".join(str(x) for x in nummern)
    return ", ".join(str(x) for x in nummern[:_LISTE_MAX]) + f" … (insgesamt {n})"


def _mehrzahl(n: int, eins: str, viele: str) -> str:
    return eins if n == 1 else viele


def schalen_ausrichten(model, log: list = None, nur_flaeche=None) -> list:
    """Alle Schalenelemente ausrichten (siehe Moduldoku); Rueckgabe die
    Meldungen (leer, wenn nichts umzudrehen war). ``log`` bekommt sie
    zusaetzlich angehaengt; ``nur_flaeche`` beschraenkt auf eine Flaeche (nach
    ihrem Vernetzen)."""
    schritte = plan(model) if nur_flaeche is None else (
        _plan_flaeche(model, nur_flaeche,
                      sorted({int(e) for e in (nur_flaeche.elemente or [])
                              if 0 <= int(e) < len(model.elements)
                              and model.elements[int(e)].typ in WENDEN})))
    if not schritte:
        return []
    meldungen: list = []
    alle: list = []
    for art, name, drehen, wid in schritte:
        alle.extend(drehen)
        k = len(drehen)
        if art == "flaeche":
            if k:
                meldungen.append(
                    f"Fläche {name}: {k} {_mehrzahl(k, 'Schalenelement', 'Schalenelemente')} zur "
                    f"Flächennormalen umgedreht ({_mehrzahl(k, 'Element', 'Elemente')} {_liste(drehen)}); "
                    "Elementlasten in lokal z, ΔT_z und Schichtfolge drehen mit.")
            if wid:
                meldungen.append(f"Fläche {name}: {wid} Elemente lassen sich nicht widerspruchsfrei "
                                 "zu ihren Nachbarn ausrichten (Umlauf wie ein Möbiusband) - bitte prüfen.")
        elif name >= 0:
            meldungen.append(
                f"Schalenelemente ohne Fläche: {k} zum Element {name} ihres zusammenhängenden Stücks "
                f"ausgerichtet ({_mehrzahl(k, 'Element', 'Elemente')} {_liste(drehen)}); "
                "Elementlasten in lokal z, ΔT_z und Schichtfolge drehen mit.")
        elif wid:
            meldungen.append(f"Schalenelemente ohne Fläche: {wid} Elemente lassen sich nicht "
                             "widerspruchsfrei zu ihren Nachbarn ausrichten - bitte prüfen.")
    if alle and elemente_wenden(model, alle):
        model.lasten_verteilen()
        if meldungen:
            meldungen[-1] += " Die Lasten der Flächen sind neu verteilt."
    if log is not None:
        log.extend(meldungen)
    return meldungen


def vor_rechnung(model, progress=None) -> list:
    """Vor einer Rechnung: ausrichten und die Meldungen ueber ``progress``
    (Text) melden. Rueckgabe die Meldungen."""
    meldungen = schalen_ausrichten(model)
    if progress is not None:
        for z in meldungen:
            try:
                progress(z)
            except Exception:                # noqa: BLE001 - ein Empfaenger ohne Text: still
                pass
    return meldungen
