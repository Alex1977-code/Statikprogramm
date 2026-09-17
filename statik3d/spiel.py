"""Spiel geben (17.09.2026): zylindrische Bauteile geometrisch um ein
Durchmesserspiel verkleinern, ebene Flaechen um einen Spalt nach innen
versetzen - statt einer Sonderbedingung an der Fuge ("eigentlich ist das ein
Problem der Modellierung, denn es gibt nur eine Realitaet").

Am Drehlager haben Passstift und Bohrung beide r = 12,500 mm, und sie teilen
sich sogar die Kreisknoten (RFEM fuehrt Stift und Bohrung ueber dieselben
Knoten, teils dieselben Bogenlinien). Ein Stift, der verkleinert wird, muss
darum erst von seinen Nachbarn **getrennt** werden: geteilte Linien und
Knoten bekommen Kopien, die dem Stift gehoeren; die Bohrung behaelt ihre.
Danach wandern seine Kreisboegen (Line.geometrie["punkte"]) und die Knoten
auf dem Schaftradius um das halbe Spiel zur Achse. Das Netz des Koerpers
wird geloescht - er wird neu vernetzt.

Alles Rechnen liegt hier ohne Qt; die Oberflaeche (maske_spiel) ruft es,
vernetzt neu und fuehrt die Kontaktfugen wieder aus.
"""
from __future__ import annotations

import copy
import math

import numpy as np

#: relative Toleranz, bis zu der ein Radius als "der Schaftradius" gilt
TOL_RADIUS = 1e-6


def _v(p):
    return np.asarray(p, float).reshape(3)


def kreis_aus_punkten(P) -> tuple:
    """(Mitte, Radius, Normale) des Kreises durch drei Punkte (Bogen mit
    Anfang, Zwischenpunkt, Ende - so kommen Boegen aus RFEM)."""
    a, b, c = (_v(x) for x in P[:3])
    ab, ac = b - a, c - a
    n = np.cross(ab, ac)
    nn = float(np.linalg.norm(n))
    if nn <= 1e-30:
        raise ValueError("die drei Punkte des Bogens liegen auf einer Geraden")
    n /= nn
    # Mittelpunkt: Schnitt der Mittelsenkrechten in der Kreisebene
    M = np.array([ab, ac, n])
    rhs = np.array([ab @ (a + b) / 2.0, ac @ (a + c) / 2.0, n @ a])
    m = np.linalg.solve(M, rhs)
    return m, float(np.linalg.norm(a - m)), n


def _bogen_kreis(L, model):
    """(Mitte, Radius, Normale) einer Bogen-/Kreislinie - oder None."""
    g = L.geometrie or {}
    if L.typ not in ("arc", "circle"):
        return None
    if "mitte" in g and "radius" in g:
        n = _v(g.get("normale", (0, 0, 1)))
        return _v(g["mitte"]), float(g["radius"]), n / (np.linalg.norm(n) or 1.0)
    P = g.get("punkte")
    if P is None or len(P) < 3:
        if model is not None and len(L.nodes) >= 3:
            P = [model.nodes[int(i)] for i in L.nodes[:3]]
        else:
            return None
    return kreis_aus_punkten(P)


def zylinder(model, name: str) -> dict:
    """Achse und Schaftradius eines zylindrischen Koerpers aus den Boegen
    seiner Flaechen: {"ok", "grund", "punkt", "achse", "radius", "boegen"}.

    Zylindrisch heisst: alle Boegen haben denselben Radius (auf TOL_RADIUS)
    und dieselbe Achse (Mittelpunkte auf einer Geraden laengs der gemeinsamen
    Normalen). Ein Bolzen mit Kopf hat zwei Radien - der groessere Kreis
    wird genannt, verkleinert wird nur der Schaft (der haeufigste Radius).
    """
    k = model.koerper.get(name)
    if k is None:
        return {"ok": False, "grund": f"Volumen {name} gibt es nicht"}
    kreise = []
    for fn in k.flaechen or []:
        f = model.flaechen.get(fn)
        if f is None:
            continue
        for ln in list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]:
            L = model.lines.get(ln)
            if L is None:
                continue
            try:
                kr = _bogen_kreis(L, model)
            except ValueError:
                kr = None
            if kr is not None:
                kreise.append((ln, kr[0], kr[1], kr[2]))
    if len(kreise) < 2:
        return {"ok": False, "grund": f"{name} hat keine Kreisboegen - kein Zylinder"}
    n0 = kreise[0][3]
    achse = np.mean([kr[3] * (1.0 if kr[3] @ n0 >= 0 else -1.0) for kr in kreise], axis=0)
    achse /= float(np.linalg.norm(achse)) or 1.0
    radien = np.array([kr[2] for kr in kreise])
    # Der Schaftradius ist der haeufigste (auf TOL_RADIUS gerundet)
    werte, zaehl = np.unique(np.round(radien / max(radien.max(), 1e-12) / TOL_RADIUS).astype(np.int64), return_counts=True)
    r = float(radien[np.argmax(zaehl[np.searchsorted(werte, np.round(radien / max(radien.max(), 1e-12) / TOL_RADIUS).astype(np.int64))])]) \
        if len(werte) > 1 else float(np.median(radien))
    mitten = np.array([kr[1] for kr in kreise if abs(kr[2] - r) <= TOL_RADIUS * r + 1e-9])
    punkt = mitten.mean(axis=0)
    # Alle Mittelpunkte auf der Achse?
    ab = mitten - punkt
    quer = ab - np.outer(ab @ achse, achse)
    if quer.size and float(np.linalg.norm(quer, axis=1).max()) > TOL_RADIUS * r + 1e-9:
        return {"ok": False, "grund": f"{name}: die Kreise liegen nicht auf einer Achse - kein Zylinder"}
    schief = [kr[0] for kr in kreise if abs(abs(kr[3] @ achse) - 1.0) > 1e-6]
    if schief:
        return {"ok": False, "grund": f"{name}: Boegen {', '.join(schief[:3])} stehen schraeg zur Achse - kein Zylinder"}
    # Ein Zylinder hat einen Mantel: Kreise an mindestens zwei Stellen laengs
    # der Achse. Eine Platte mit einer Bohrung hat ihre Boegen in einer Ebene.
    lage = mitten @ achse
    if float(lage.max() - lage.min()) <= 1e-9:
        return {"ok": False, "grund": f"{name}: alle Kreise liegen in einer Ebene (eine Bohrung, kein Zylinder)"}
    boegen = list(dict.fromkeys(kr[0] for kr in kreise if abs(kr[2] - r) <= TOL_RADIUS * r + 1e-9))
    andere = sorted({round(kr[2], 9) for kr in kreise if abs(kr[2] - r) > TOL_RADIUS * r + 1e-9})
    return {"ok": True, "grund": "", "punkt": punkt, "achse": achse, "radius": r,
            "boegen": boegen, "andere_radien": andere}


def _flaechen_von(model, name: str) -> list:
    k = model.koerper.get(name)
    return [fn for fn in (k.flaechen or []) if fn in model.flaechen] if k else []


def _linien_der_flaeche(f) -> list:
    return list(f.linien or []) + [x for loch in (f.oeffnungen or []) for x in loch]


def _fremde_nutzung(model, koerper: str, flaechen: list) -> tuple:
    """(Linien, Knoten), die ausser von ``flaechen`` auch von Flaechen anderer
    Koerper (oder nicht zum Koerper gehoerenden Flaechen) benutzt werden."""
    eigene = set(flaechen)
    fremde_linien: set = set()
    fremde_knoten: set = set()
    for fn, f in model.flaechen.items():
        if fn in eigene:
            continue
        for ln in _linien_der_flaeche(f):
            fremde_linien.add(ln)
            L = model.lines.get(ln)
            if L is not None:
                fremde_knoten.update(int(n) for n in L.nodes)
        fremde_knoten.update(int(n) for n in (f.ecken or []))
    return fremde_linien, fremde_knoten


def trennen(model, koerper: str, flaechen: list = None, log: list = None) -> dict:
    """Die Geometrie der Flaechen eines Koerpers von anderen Koerpern loesen:
    geteilte Linien bekommen Kopien (neue Namen), geteilte Knoten Kopien
    (neue Nummern), und nur die Flaechen des Koerpers zeigen darauf.
    Rueckgabe {"linien": n, "knoten": n, "flaechen": n} - Zahl der Kopien."""
    flaechen = list(flaechen if flaechen is not None else _flaechen_von(model, koerper))
    # Eine Flaeche, die auch einem anderen Koerper gehoert (gemeinsame
    # Trennflaeche), bekommt zuerst eine Kopie fuer diesen Koerper
    k = model.koerper.get(koerper)
    n_fl = 0
    flaechen_neu: dict = {}
    for i, fn in enumerate(list(flaechen)):
        andere = [kn for kn, kk in model.koerper.items() if kn != koerper and fn in (kk.flaechen or [])]
        if not andere:
            continue
        f = model.flaechen[fn]
        neu = model.naechster_name("F", model.flaechen)
        f2 = copy.deepcopy(f)
        f2.name = neu
        f2.elemente, f2.randseiten = [], []
        model.flaechen[neu] = f2
        if k is not None:
            k.flaechen = [neu if x == fn else x for x in (k.flaechen or [])]
        flaechen[i] = neu
        flaechen_neu[fn] = neu
        n_fl += 1
    fremde_linien, fremde_knoten = _fremde_nutzung(model, koerper, flaechen)
    # Linien
    umbenannt: dict = {}
    n_l = 0
    for fn in flaechen:
        f = model.flaechen[fn]
        for attr in ("linien",):
            neu_liste = []
            for ln in (getattr(f, attr) or []):
                if ln in fremde_linien and ln in model.lines:
                    if ln not in umbenannt:
                        L = model.lines[ln]
                        neu = model.naechster_name("L", model.lines)
                        L2 = copy.deepcopy(L)
                        L2.name = neu
                        model.lines[neu] = L2
                        umbenannt[ln] = neu
                        n_l += 1
                    neu_liste.append(umbenannt[ln])
                else:
                    neu_liste.append(ln)
            setattr(f, attr, neu_liste)
        f.oeffnungen = [[umbenannt.get(ln, ln) if ln in fremde_linien else ln for ln in loch]
                        for loch in (f.oeffnungen or [])]
    # Knoten: die der eigenen Linien (nach dem Kopieren) und der Ecken
    eigene_linien = {ln for fn in flaechen for ln in _linien_der_flaeche(model.flaechen[fn])}
    kopie: dict = {}
    n_k = 0
    for ln in eigene_linien:
        L = model.lines[ln]
        neu_nodes = []
        for n in L.nodes:
            n = int(n)
            if n in fremde_knoten:
                if n not in kopie:
                    kopie[n] = model.add_node(*[float(x) for x in model.nodes[n]])
                    n_k += 1
                neu_nodes.append(kopie[n])
            else:
                neu_nodes.append(n)
        L.nodes = neu_nodes
    for fn in flaechen:
        f = model.flaechen[fn]
        f.ecken = [kopie.get(int(n), int(n)) for n in (f.ecken or [])]
    if log is not None and (n_l or n_k or n_fl):
        log.append(f"{koerper}: von den Nachbarn getrennt - {n_fl} Flächen, {n_l} Linien und {n_k} Knoten "
                   "bekamen eigene Kopien")
    return {"linien": n_l, "knoten": n_k, "flaechen": n_fl, "knotenkopie": kopie, "flaechen_neu": flaechen_neu}


def _netz_weg(model, koerper: str, flaechen: list) -> int:
    k = model.koerper.get(koerper)
    weg = list(k.elemente or []) if k else []
    for fn in flaechen:
        weg += list(model.flaechen[fn].elemente or [])
    n = model.elemente_loeschen(weg) if weg else 0
    if k is not None:
        k.elemente = []
    for fn in flaechen:
        f = model.flaechen[fn]
        f.elemente, f.randseiten = [], []
    return n


def zylinder_spiel(model, koerper: str, spiel: float, log: list = None) -> dict:
    """Einem zylindrischen Koerper das Durchmesserspiel ``spiel`` [m] geben:
    Schaftradius r -> r - spiel/2 (Knoten und Boegen), nach dem Trennen von
    den Nachbarn; das Netz des Koerpers wird geloescht."""
    z = zylinder(model, koerper)
    if not z["ok"]:
        if log is not None:
            log.append(f"Spiel nicht gegeben: {z['grund']}")
        return z
    if spiel <= 0:
        return {"ok": False, "grund": "Spiel muss groesser als null sein"}
    flaechen = _flaechen_von(model, koerper)
    tr = trennen(model, koerper, flaechen, log)
    p0, a, r = z["punkt"], z["achse"], z["radius"]
    ds = 0.5 * float(spiel)

    def naeher(P):
        P = _v(P)
        d = P - p0
        ax = (d @ a) * a
        rad = d - ax
        rr = float(np.linalg.norm(rad))
        if abs(rr - r) > TOL_RADIUS * r + 1e-9:
            return P, False
        return p0 + ax + rad * ((r - ds) / rr), True

    linien = {ln for fn in flaechen for ln in _linien_der_flaeche(model.flaechen[fn])}
    knoten = {int(n) for ln in linien for n in model.lines[ln].nodes}
    n_k = 0
    for n in knoten:
        P, ok = naeher(model.nodes[n])
        if ok:
            model.nodes[n] = P
            n_k += 1
    n_b = 0
    for ln in linien:
        L = model.lines[ln]
        g = L.geometrie or {}
        if "punkte" in g and g["punkte"] is not None:
            neu = []
            getroffen = False
            for P in g["punkte"]:
                Q, ok = naeher(P)
                getroffen |= ok
                neu.append([float(x) for x in Q])
            g["punkte"] = neu
            n_b += int(getroffen and L.typ in ("arc", "circle"))
        if "radius" in g and abs(float(g["radius"]) - r) <= TOL_RADIUS * r + 1e-9:
            g["radius"] = float(g["radius"]) - ds
            n_b += 1
        L.geometrie = g
    weg = _netz_weg(model, koerper, flaechen)
    if log is not None:
        log.append(f"{koerper}: Zylinder r = {r * 1e3:.3f} mm, Achse ({a[0]:.2f}, {a[1]:.2f}, {a[2]:.2f}) - Spiel "
                   f"{spiel * 1e3:.3f} mm am Durchmesser: r = {(r - ds) * 1e3:.3f} mm, {n_k} Knoten und {n_b} Bögen "
                   f"zur Achse gesetzt" + (f", {weg} Elemente gelöscht (neu vernetzen)" if weg else "")
                   + (f"; andere Radien bleiben: {', '.join(f'{x * 1e3:.3f}' for x in z['andere_radien'])} mm"
                      if z.get("andere_radien") else ""))
    return {"ok": True, "grund": "", "radius": r, "radius_neu": r - ds, "knoten": n_k, "boegen": n_b,
            "getrennt": tr, "netz_geloescht": weg}


def flaechen_spiel(model, koerper: str, flaechen: list, spalt: float, log: list = None) -> dict:
    """Ebene Flaechen eines Koerpers um ``spalt`` [m] nach innen versetzen
    (in den Koerper hinein, weg vom Nachbarn) - nach dem Trennen von den
    Nachbarn; das Netz des Koerpers wird geloescht."""
    k = model.koerper.get(koerper)
    if k is None:
        return {"ok": False, "grund": f"Volumen {koerper} gibt es nicht"}
    flaechen = [fn for fn in flaechen if fn in (k.flaechen or [])]
    if not flaechen:
        return {"ok": False, "grund": f"keine der Flächen gehört zu {koerper}"}
    if spalt <= 0:
        return {"ok": False, "grund": "Spalt muss groesser als null sein"}
    tr = trennen(model, koerper, flaechen, log)
    # Die Flaechen koennen beim Trennen neue Namen bekommen haben
    flaechen = [tr["flaechen_neu"].get(fn, fn) for fn in flaechen]
    # Schwerpunkt des Koerpers aus allen seinen Randpunkten - fuer "innen"
    alle = []
    for fn in k.flaechen or []:
        try:
            alle.extend(np.asarray(model.flaechen[fn].randpunkte(model, 8), float).reshape(-1, 3))
        except Exception:                 # noqa: BLE001
            pass
    schwer = np.mean(alle, axis=0) if alle else np.zeros(3)
    n_k = 0
    verschoben: set = set()
    for fn in flaechen:
        f = model.flaechen[fn]
        P = np.asarray(f.randpunkte(model, 8), float).reshape(-1, 3)
        if len(P) < 3:
            continue
        c = P.mean(axis=0)
        _u, _s, vt = np.linalg.svd(P - c)
        n = vt[2]
        if n @ (schwer - c) < 0:
            n = -n                        # nach innen
        d = n * float(spalt)
        for ln in _linien_der_flaeche(f):
            L = model.lines[ln]
            for nd in L.nodes:
                nd = int(nd)
                if nd not in verschoben:
                    model.nodes[nd] = model.nodes[nd] + d
                    verschoben.add(nd)
                    n_k += 1
            g = L.geometrie or {}
            for key in ("punkte", "steuerpunkte", "stuetzpunkte"):
                if key in g and g[key] is not None:
                    g[key] = [[float(x) for x in (_v(p) + d)] for p in g[key]]
            for key in ("mitte", "anfang", "ende"):
                if key in g and g[key] is not None:
                    g[key] = [float(x) for x in (_v(g[key]) + d)]
            L.geometrie = g
    weg = _netz_weg(model, koerper, list(k.flaechen or []))
    if log is not None:
        log.append(f"{koerper}: Flächen {', '.join(flaechen[:6])} um {spalt * 1e3:.3f} mm nach innen versetzt "
                   f"({n_k} Knoten)" + (f", {weg} Elemente gelöscht (neu vernetzen)" if weg else ""))
    return {"ok": True, "grund": "", "knoten": n_k, "flaechen": flaechen, "getrennt": tr, "netz_geloescht": weg}


def zylinder_im_modell(model) -> list:
    """Namen aller Koerper, die :func:`zylinder` als Zylinder erkennt."""
    return [n for n in model.koerper if zylinder(model, n).get("ok")]
