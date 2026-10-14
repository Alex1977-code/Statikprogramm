"""Stabenden verteilend in ein Volumen einleiten (seit 13.10.2026).

Ein Stabende, das auf oder in einem vernetzten Koerper liegt, haengt nach
:func:`fugen.stabenden_koppeln` wie in RFEM an den 1-3 Knoten des Elements, in
dem es liegt. Dort geht die ganze Stabkraft ueber einen Punkt in das Volumen,
und es entsteht eine Spannungsspitze, die mit jeder Netzverfeinerung waechst
(Drehlager, Netz Mittel: an V90 19,7 kN ueber 2 Knoten einer Stirnflaeche von
197,8 mm2).

**Entscheidung des Anwenders vom 13.10.2026**: eine Modelleinstellung, je
Stabende schaltbar; die Kopplung als RBE3 ohne Versteifung, flaechenanteilig
gewichtet; Einleitungsflaeche als Vorgabe die Stirnflaeche, wahlweise ein
Kreisring (Auflageflaeche). Bei Import und Rechenstart ein Hinweis, aber
nichts automatisch umstellen; im Ergebnis die Kraftsumme je gekoppeltem
Stabende pruefen und die gekoppelten Stabenden kennzeichnen. Ergaenzt am
selben Tag: Gewichte nach Ausschluss der gebundenen Randknoten neu normieren,
den Lastschwerpunkt auf der Stabachse halten, Kraftsumme **und** Moment je
Stabende pruefen.

**Die Kopplung** ist die vorhandene Verteilkopplung des Programms
(:class:`model.StarrKoerper` Art RBE3, :func:`elements.verbindung.starrkoerper_matrix`,
:func:`assemble.starrkoerper`) - keine zweite. Der Stabknoten ist der
Master; er folgt dem gewichteten Mittel der Flaechenknoten, die Flaeche wird
nicht starr. Gespeichert werden alle Knoten der Flaeche mit dem rohen
flaechenanteiligen Gewicht w_i = Integral N_i dA (konsistent: beim ebenen tri6
null an den Ecken und A/3 je Kantenmitte, beim tri3 A/3 je Ecke). Gerechnet
wird mit :func:`wirksame_gewichte`: gebundene Seitenmitten (Kontakt- und
Lagerseiten, assemble.mittelknoten_bindungen) fallen heraus, die uebrigen
Gewichte werden auf die Summe 1 normiert und mit der kleinsten Aenderung
(kleinste Quadrate, auf das Gewicht bezogen, mit Nebenbedingung) so
ausgeglichen, dass ihr Schwerpunkt im Durchstosspunkt der Stabachse durch die
Flaeche liegt. Erst dann geht eine reine Laengskraft gleichmaessig nach den
Gewichten in die Flaeche.

Der Strafbeiwert ist derselbe wie bei den starren Kopplungen der Stabenden
(1e4-mal die groesste Hauptdiagonale der Elemente, ohne die Straffedern der
Kopplungen), und die drei Momentenzeilen sind durch den Traegheitsradius
rho der Gewichte geteilt: so ist die Strafe fuer die Drehung des Masters
k rho^2 und nicht k rho^4 (bei rho = 8 mm waere sie sonst um den Faktor 1,6e4
weicher als gewollt und laege in der Groesse der Biegesteifigkeit eines Rund 16).
"""
from __future__ import annotations

import math

import numpy as np

#: Name der Kopplung eines Stabendes (wie die Gruppe der starren Kopplungen in
#: fugen.STABENDE_GRUPPE): "Stabende K<Knoten>"
STABENDE = "Stabende "
#: Knick [Grad], bis zu dem eine Randseite noch in der Ebene der Stirnflaeche
#: liegt (eine Zylinderflaeche aus 20 Abschnitten knickt um 18 Grad)
KNICK = 5.0
#: groesster Winkel [Grad] zwischen Stabachse und Flaechennormale - darueber
#: ist die Flaeche keine Stirnflaeche des Stabes, das Stabende bleibt an 1-3 Knoten
ACHSE = 30.0
#: Teilung der Ringbreite fuer die Seiten, die der Kreisring schneidet: so
#: viele Teilzellen je Ringbreite, mindestens 4 und hoechstens 64 je Seitenkante
RING_TEILUNG = 16
#: Strafbeiwert: so viel mal die groesste Hauptdiagonale der Elemente
STRAFE = 1e4

TEXTE = {"punkt": "an 1–3 Knoten wie RFEM", "stirn": "verteilt über die Stirnfläche",
         "ring": "verteilt über einen Kreisring"}


# --------------------------------------------------------------------------
# Einstellung je Stabende
# --------------------------------------------------------------------------
def ist_verteilkopplung(sk) -> bool:
    """Eine verteilende Kopplung eines Stabendes (RBE3 mit Namen "Stabende K…")."""
    return (str(getattr(sk, "art", "")).upper() == "RBE3"
            and str(getattr(sk, "name", "")).startswith(STABENDE))


def staebe_an_enden(model) -> dict:
    """{Knoten: (Stabname, "A" | "E")} der Enden aller Staebe. Anfang ist das
    Ende des ersten Elements, das nicht am zweiten haengt (bei einem Element
    sein erster Knoten), Ende entsprechend am letzten Element."""
    aus: dict = {}
    els = model.elements
    for name, mem in (getattr(model, "members", None) or {}).items():
        idx = [int(i) for i in (mem.elements or []) if 0 <= int(i) < len(els)]
        if not idx:
            continue
        a = [int(x) for x in els[idx[0]].nodes[:2]]
        e = [int(x) for x in els[idx[-1]].nodes[:2]]
        if len(idx) == 1:
            anfang, ende = a[0], a[1]
        else:
            n1 = {int(x) for x in els[idx[1]].nodes[:2]}
            anfang = a[0] if a[0] not in n1 else a[1]
            n2 = {int(x) for x in els[idx[-2]].nodes[:2]}
            ende = e[1] if e[1] not in n2 else e[0]
        aus.setdefault(anfang, (str(name), "A"))
        aus.setdefault(ende, (str(name), "E"))
    return aus


def einstellung(model, knoten: int, enden: dict = None) -> dict:
    """Wie das Stabende am ``knoten`` in ein Volumen geht: {"art", "d_innen",
    "d_aussen", "quelle"}. Die Einstellung des Stabendes (Member.einleitung)
    geht vor, sonst gilt die des Modells (Model.stabeinleitung). Ein Kreisring
    ohne eigene Durchmesser nimmt die des Modells."""
    from .model import EINLEITUNGEN
    st = getattr(model, "stabeinleitung", None)
    art = str(getattr(st, "art", "punkt") or "punkt")
    di = float(getattr(st, "d_innen", 0.0) or 0.0)
    da = float(getattr(st, "d_aussen", 0.0) or 0.0)
    quelle = "Modell"
    enden = staebe_an_enden(model) if enden is None else enden
    treffer = enden.get(int(knoten))
    if treffer is not None:
        name, ende = treffer
        mem = (getattr(model, "members", None) or {}).get(name)
        e = ((getattr(mem, "einleitung", None) or {}).get(ende) or {}) if mem is not None else {}
        if str(e.get("art", "")) in EINLEITUNGEN:
            art = str(e["art"])
            quelle = f"Stab {name}, {'Anfang' if ende == 'A' else 'Ende'}"
            if art == "ring" and float(e.get("d_aussen", 0.0) or 0.0) > 0.0:
                di = float(e.get("d_innen", 0.0) or 0.0)
                da = float(e.get("d_aussen", 0.0) or 0.0)
    if art not in EINLEITUNGEN:
        art = "punkt"
    return {"art": art, "d_innen": di, "d_aussen": da, "quelle": quelle}


def kennung(e: dict) -> str:
    """Kurze Kennung einer Einstellung - so steht sie vorn im Kommentar der
    Kopplung, und so vergleicht :func:`fugen.stabenden_erneuern` Soll und Ist."""
    art = str(e.get("art", "punkt"))
    if art == "ring":
        return f"ring {float(e.get('d_innen', 0.0)) * 1e3:.3f}/{float(e.get('d_aussen', 0.0)) * 1e3:.3f}"
    return art


def kennung_der_kopplung(sk) -> str:
    """Die Kennung, mit der eine verteilende Kopplung angelegt wurde."""
    return str(getattr(sk, "kommentar", "") or "").split(":", 1)[0].strip()


def mm(x: float, nk: int = 1) -> str:
    """Laenge [m] als „12,3“ in mm (nie wissenschaftlich)."""
    return f"{float(x) * 1e3:.{nk}f}".replace(".", ",")


def mm2(x: float) -> str:
    """Flaeche [m2] als „197,8“ in mm2."""
    return f"{float(x) * 1e6:.1f}".replace(".", ",")


def stabelemente_an(model) -> dict:
    """{Knoten: [Stabelemente]} - einmal je Elementliste (am Drehlager mit
    623 000 Elementen sonst je Stabende eine Schleife ueber alle)."""
    from .assemble import LINE_TYPES
    schl = (id(model.elements), len(model.elements))
    alt = getattr(model, "_stabelemente_an", None)
    if alt is not None and alt[0] == schl:
        return alt[1]
    an: dict = {}
    for i, e in enumerate(model.elements):
        if e.typ in LINE_TYPES:
            for x in e.nodes[:2]:
                an.setdefault(int(x), []).append(i)
    try:
        model._stabelemente_an = (schl, an)
    except AttributeError:
        pass
    return an


def stabachse(model, knoten: int) -> np.ndarray:
    """Einheitsvektor der Stabachse am Knoten, vom Knoten in den Stab hinein
    (Mittel ueber die Stabelemente dort); Null, wenn keiner dort endet."""
    X = np.asarray(model.nodes, float)
    v = np.zeros(3)
    for i in stabelemente_an(model).get(int(knoten), []):
        e = model.elements[i]
        nd = [int(x) for x in e.nodes[:2]]
        if int(knoten) in nd:
            anderer = nd[1] if nd[0] == int(knoten) else nd[0]
            d = X[anderer] - X[int(knoten)]
            ln = float(np.linalg.norm(d))
            if ln > 0:
                v += d / ln
    ln = float(np.linalg.norm(v))
    return v / ln if ln > 0 else v


# --------------------------------------------------------------------------
# Einleitungsflaeche
# --------------------------------------------------------------------------
def _randseiten(model, kname: str, cache: dict) -> dict:
    """Randseiten eines Koerpers (Seiten, die in seinen Elementen genau einmal
    vorkommen): je Seite die Knoten (Ecken zuerst), die Ecken und der
    Schwerpunkt des Elements dahinter. Je Koerper einmal (``cache``)."""
    from .elements import solid as sl
    if kname in cache:
        return cache[kname]
    k = (getattr(model, "koerper", None) or {}).get(kname)
    X = np.asarray(model.nodes, float)
    je_typ: dict = {}
    for i in (getattr(k, "elemente", None) or []):
        i = int(i)
        if 0 <= i < len(model.elements) and model.elements[i].typ in sl.FLAECHEN:
            je_typ.setdefault(model.elements[i].typ, []).append(i)
    schl, voll, ecken, innen = [], [], [], []
    for typ, idx in je_typ.items():
        E = np.asarray([model.elements[i].nodes for i in idx], np.int64)
        n_ecken = {"hex8": 8, "hex20": 8, "pent6": 6, "pent15": 6, "pyr5": 5}.get(typ, 4)
        mitte = X[E[:, :n_ecken]].mean(axis=1)
        for f, fe in zip(sl.FLAECHEN[typ], sl.FLAECHEN_ECKEN[typ]):
            C = E[:, list(fe)]
            S = np.sort(C, axis=1)
            if S.shape[1] == 3:
                S = np.hstack([S, np.full((len(S), 1), -1, np.int64)])
            schl.append(S)
            voll.extend(E[:, list(f)].tolist())
            ecken.extend(C.tolist())
            innen.append(mitte)
    if not schl:
        cache[kname] = {"voll": [], "ecken": [], "innen": np.zeros((0, 3))}
        return cache[kname]
    S = np.vstack(schl)
    _u, inv, zahl = np.unique(S, axis=0, return_inverse=True, return_counts=True)
    rand = np.flatnonzero(zahl[np.asarray(inv).ravel()] == 1)
    aus = {"voll": [voll[j] for j in rand.tolist()], "ecken": [ecken[j] for j in rand.tolist()],
           "innen": np.vstack(innen)[rand]}
    cache[kname] = aus
    return aus


def _seitenebene(X, ecken, innen) -> tuple:
    """(Einheitsnormale nach aussen, Flaechenmittelpunkt) einer Seite aus ihren Ecken."""
    P = X[ecken]
    if len(ecken) == 4:
        n = np.cross(P[2] - P[0], P[3] - P[1])
    else:
        n = np.cross(P[1] - P[0], P[2] - P[0])
    ln = float(np.linalg.norm(n))
    if ln <= 0:
        return None, P.mean(axis=0)
    n = n / ln
    c = P.mean(axis=0)
    if float(n @ (c - innen)) < 0:
        n = -n
    return n, c


def _in_seite(p, P, n, tol) -> bool:
    """Liegt der Punkt p (in der Ebene, Normale n) in der Seite mit den Ecken P
    (3 oder 4, im Umlauf) - bis ``tol`` ausserhalb? Der Umlauf darf links-
    oder rechtsherum zur Normale laufen."""
    k = len(P)
    eigen = (np.cross(P[2] - P[0], P[3] - P[1]) if k == 4 else np.cross(P[1] - P[0], P[2] - P[0]))
    if float(eigen @ n) < 0:
        n = -n
    for i in range(k):
        a, b = P[i], P[(i + 1) % k]
        kante = b - a
        lk = float(np.linalg.norm(kante))
        if lk <= 0:
            continue
        # Abstand nach aussen von der Kante a-b (in der Ebene)
        aussen = np.cross(kante, n) / lk
        if float((p - a) @ aussen) > tol:
            return False
    return True


def _teilregel(k: int, s: int) -> tuple:
    """Mittelpunktregel auf s x s Teilzellen der Bezugsseite (k = 3/6
    Dreieck mit Flaeche 1/2, k = 4/8 Viereck [-1, 1]^2)."""
    if k in (3, 6):
        GP, W = [], []
        for i in range(s):
            for j in range(s - i):
                GP.append(((i + 1.0 / 3.0) / s, (j + 1.0 / 3.0) / s))
                W.append(0.5 / (s * s))
                if j < s - i - 1:
                    GP.append(((i + 2.0 / 3.0) / s, (j + 2.0 / 3.0) / s))
                    W.append(0.5 / (s * s))
        return np.asarray(GP, float), np.asarray(W, float)
    t = -1.0 + (np.arange(s) + 0.5) * 2.0 / s
    GP = np.array([[a, b] for a in t for b in t])
    return GP, np.full(len(GP), 4.0 / (s * s))


def flaeche_finden(model, knoten: int, kname: str, e: dict, cache: dict = None,
                   toleranz: float = 1e-4) -> dict:
    """Die Einleitungsflaeche eines Stabendes am ``knoten`` im Koerper ``kname``.

    **Stirnflaeche**: die zusammenhaengenden Randseiten des Koerpers in der
    Ebene durch den Stabknoten - die Seite, in der er liegt, und alle
    Randseiten, die ueber gemeinsame Ecken daran haengen, bis ``toleranz`` in
    der Ebene und mit der Normale bis :data:`KNICK` Grad gegen ihre. Die
    Stabachse darf um hoechstens :data:`ACHSE` Grad von der Normale abweichen.
    **Kreisring**: davon die Teile zwischen d_innen/2 und d_aussen/2 um den
    Durchstosspunkt der Stabachse; Seiten, die der Ring schneidet, werden
    in Teilzellen integriert.

    Rueckgabe {"knoten", "gewichte" (Integral N_i dA [m2]), "momente"
    (Integral N_i (x - x_Stabknoten) dA [m3], seit 14.10.2026), "flaeche"
    [m2], "normale", "punkt" (Durchstosspunkt), "seiten"} - oder
    {"grund": Text}, wenn es die Flaeche nicht gibt."""
    from .elements import solid as sl
    cache = {} if cache is None else cache
    X = np.asarray(model.nodes, float)
    p = X[int(knoten)]
    achse = stabachse(model, knoten)
    R = _randseiten(model, kname, cache)
    if not R["voll"]:
        return {"grund": f"Volumen {kname} hat keine Randseiten"}
    nrm, mit = [], []
    for ek, inn in zip(R["ecken"], R["innen"]):
        n, c = _seitenebene(X, ek, inn)
        nrm.append(np.zeros(3) if n is None else n)
        mit.append(c)
    nrm = np.asarray(nrm)
    abst = np.einsum("ij,ij->i", p[None, :] - np.asarray([X[ek[0]] for ek in R["ecken"]]), nrm)
    saat = []
    for j in np.flatnonzero(np.abs(abst) <= toleranz).tolist():
        P = X[R["ecken"][j]]
        if _in_seite(p, P, nrm[j], toleranz):
            saat.append(j)
    if not saat:
        return {"grund": "das Stabende liegt auf keiner Randseite des Volumens (im Innern)"}
    n0 = nrm[saat].sum(axis=0)
    n0 = n0 / (np.linalg.norm(n0) or 1.0)
    if float(np.linalg.norm(achse)) > 0:
        winkel = math.degrees(math.acos(min(1.0, abs(float(achse @ n0)))))
        if winkel > ACHSE:
            return {"grund": f"der Stab steht {winkel:.0f}° schräg zur Fläche (Stirnfläche bis {ACHSE:.0f}°)"}
    cos_k = math.cos(math.radians(KNICK))
    ebene = [j for j in range(len(R["ecken"]))
             if float(nrm[j] @ n0) >= cos_k
             and np.all(np.abs((X[R["ecken"][j]] - p) @ n0) <= toleranz)]
    # zusammenhaengend ueber gemeinsame Ecken, ausgehend von der Seite am Stabknoten
    an: dict = {}
    for j in ebene:
        for q in R["ecken"][j]:
            an.setdefault(int(q), []).append(j)
    drin = set(saat)
    offen = list(saat)
    while offen:
        j = offen.pop()
        for q in R["ecken"][j]:
            for j2 in an.get(int(q), []):
                if j2 not in drin:
                    drin.add(j2)
                    offen.append(j2)
    seiten = sorted(drin)
    # Durchstosspunkt der Stabachse durch die Ebene
    P0 = p.copy()
    if float(np.linalg.norm(achse)) > 0 and abs(float(achse @ n0)) > 1e-9:
        t = float((X[R["ecken"][saat[0]][0]] - p) @ n0) / float(achse @ n0)
        P0 = p + t * achse
    gewicht: dict = {}
    moment: dict = {}
    ring = str(e.get("art")) == "ring"
    ri = 0.5 * float(e.get("d_innen", 0.0) or 0.0)
    ra = 0.5 * float(e.get("d_aussen", 0.0) or 0.0)
    if ring and not ra > ri:
        return {"grund": f"Kreisring ohne gültige Durchmesser (innen {mm(2 * ri)} mm, außen {mm(2 * ra)} mm)"}
    je_k: dict = {}
    for j in seiten:
        je_k.setdefault(len(R["voll"][j]), []).append(j)
    benutzt = 0
    for k, liste in je_k.items():
        for j in liste:
            voll = R["voll"][j]
            P = X[voll]
            if ring:
                kc = 4 if k in (4, 8) else 3
                Q = P[:kc] - P0
                Q = Q - np.outer(Q @ n0, n0)
                r_ecke = np.linalg.norm(Q, axis=1)
                # kleinster Abstand der Seite zum Mittelpunkt: 0, wenn er darin liegt
                if _in_seite(P0, P[:kc], n0, 0.0):
                    r_min = 0.0
                else:
                    r_min = float("inf")
                    for a_, b_ in zip(Q, np.roll(Q, -1, axis=0)):
                        d = b_ - a_
                        t_ = float(np.clip(-(a_ @ d) / max(float(d @ d), 1e-300), 0.0, 1.0))
                        r_min = min(r_min, float(np.linalg.norm(a_ + t_ * d)))
                r_max = float(r_ecke.max())
                if r_min >= ra or r_max <= ri:
                    continue                        # ganz ausserhalb des Rings
                if r_min >= ri and r_max <= ra:
                    d_ = sl.seiten_integration_stapel(P[None])
                    w = d_["knotenflaechen"][0]
                    s_ = np.einsum("m,mk,mj->kj", d_["dA"][0], d_["N"], d_["punkte"][0] - p)
                else:
                    h = float(np.max(np.linalg.norm(P[:kc] - np.roll(P[:kc], -1, axis=0), axis=1)))
                    s = int(min(64, max(4, math.ceil(RING_TEILUNG * h / (ra - ri)))))
                    d_ = sl.seiten_integration_stapel(P[None], regel=_teilregel(k, s))
                    pk = d_["punkte"][0] - P0
                    pk = pk - np.outer(pk @ n0, n0)
                    r = np.linalg.norm(pk, axis=1)
                    chi = ((r >= ri) & (r <= ra)).astype(float)
                    w = (d_["dA"][0] * chi) @ d_["N"]
                    s_ = np.einsum("m,mk,mj->kj", d_["dA"][0] * chi, d_["N"], d_["punkte"][0] - p)
                    if not np.any(chi):
                        continue
            else:
                d_ = sl.seiten_integration_stapel(P[None])
                w = d_["knotenflaechen"][0]
                s_ = np.einsum("m,mk,mj->kj", d_["dA"][0], d_["N"], d_["punkte"][0] - p)
            benutzt += 1
            for q, wq, sq in zip(voll, w.tolist(), s_):
                gewicht[int(q)] = gewicht.get(int(q), 0.0) + float(wq)
                moment[int(q)] = moment.get(int(q), np.zeros(3)) + sq
    if not gewicht:
        return {"grund": "der Kreisring trifft keine Randseite der Stirnfläche"}
    kn = sorted(gewicht)
    w = [gewicht[q] for q in kn]
    aus = {"knoten": kn, "gewichte": w, "momente": [[float(x) for x in moment[q]] for q in kn],
           "flaeche": float(sum(w)), "normale": n0, "punkt": P0, "seiten": benutzt}
    if ring:
        aus["flaeche_nenn"] = math.pi * (ra * ra - ri * ri)
    return aus


def verteilt_zeile(verteilt: list) -> str:
    """Die Protokollzeile der verteilend angeschlossenen Stabenden, je
    Flaeche gebuendelt - etwa „48 Stabenden verteilt eingeleitet (RBE3 ohne
    Versteifung, flächenanteilig): Stirnfläche 197,8 mm² mit 81 Knoten (24×),
    Stirnfläche 309,0 mm² mit 69–81 Knoten (24×)“."""
    from .begriffe import anzahl
    gruppen: dict = {}
    for _n, _s, _k, ken, zahl, A, A_nenn in verteilt:
        art = "Kreisring" if ken.startswith("ring") else "Stirnfläche"
        g = gruppen.setdefault((art, mm2(A), ken), [0, [], A_nenn])
        g[0] += 1
        g[1].append(int(zahl))
    teile = []
    for (art, A, ken), (n, zahlen, A_nenn) in sorted(gruppen.items(), key=lambda x: (-x[1][0], x[0])):
        lo, hi = min(zahlen), max(zahlen)
        kn = f"{lo}" if lo == hi else f"{lo}–{hi}"
        zusatz = ""
        if art == "Kreisring":
            di, da = ken.split(" ", 1)[1].split("/")
            zusatz = (f" (Ø {di.replace('.', ',').rstrip('0').rstrip(',')}/"
                      f"{da.replace('.', ',').rstrip('0').rstrip(',')} mm, Sollfläche {mm2(A_nenn)} mm²)")
        teile.append(f"{art} {A} mm²{zusatz} mit {kn} Knoten ({n}×)")
    return (f"{anzahl(len(verteilt), 'Stabende', 'Stabenden')} verteilt eingeleitet (RBE3 ohne "
            "Versteifung, flächenanteilig): " + ", ".join(teile[:8]) + (" …" if len(teile) > 8 else ""))


# --------------------------------------------------------------------------
# Wirksame Gewichte: gebundene Mitten heraus, normiert, Schwerpunkt auf der Achse
# --------------------------------------------------------------------------
def wirksame_gewichte(model, sk, bindung=None) -> dict:
    """Die Slaves und Gewichte, mit denen eine verteilende Kopplung rechnet.

    1. Gebundene Seitenmitten (``bindung``: die Mitten aus
       assemble.mittelknoten_bindungen) fallen heraus - an ihnen rechnet kein
       Element (Kontakt- und Lagerseiten sind linear gebunden), und eine
       Kopplung dort braeche die Rechnung ab. Knoten mit Gewicht null auch.
    2. Die uebrigen Gewichte werden auf die Summe 1 normiert.
    3. Ihr Schwerpunkt wird in den Durchstosspunkt P der Stabachse durch die
       Flaeche gelegt, mit der kleinsten Aenderung: min sum (dw_i)^2 / |w_i|
       unter sum w = 1 und sum w_i (x_i - P) = 0 in der Ebene. Gewichte null
       bleiben null.

    4. (seit 14.10.2026) Traegt die Kopplung die Momentvektoren s_i
       (StarrKoerper.momente, Integral N_i (x - x_m) dA), gehen sie mit:
       ein Knoten bleibt auch mit Gewicht null, wenn sein s_i nicht null ist
       (die Ecken eines ebenen tri6 tragen keine Kraft, aber ihren Teil der
       linearen Spannung), gebundene Mitten fallen auch hier heraus, und die
       s_i werden mit demselben Faktor wie die Gewichte normiert.

    Rueckgabe {"slaves", "w", "s" ((n, 3) oder None: klassisch), "P",
    "normale", "ausgeschlossen", "abstand_vorher", "abstand_nachher" [m],
    "aenderung" (groesste Aenderung eines Gewichts, auf das groesste
    bezogen), "negativ" (Zahl negativer Gewichte nach dem Ausgleich)}."""
    X = np.asarray(model.nodes, float)
    m = int(sk.master)
    sl_ = [int(x) for x in sk.slaves]
    w0 = list(sk.gewichte or [])
    if len(w0) != len(sl_):
        w0 = [1.0] * len(sl_)
    if bindung is None:
        from . import assemble as asm
        bindung = {int(t[0]) for t in asm.mittelknoten_bindungen(model)}
    nn = len(X)
    m0 = list(getattr(sk, "momente", None) or [])
    mit_s = len(m0) == len(sl_) and len(sl_) > 0
    s0 = {int(s): np.asarray(v, float) for s, v in zip(sl_, m0)} if mit_s else {}
    paare = [(s, float(w)) for s, w in zip(sl_, w0) if 0 <= s < nn and s != m]
    # Gewicht null: die Ecken einer ebenen tri6-Seite (Integral N dA = 0, als
    # Rundung bis 1e-20 m2) - sie tragen nichts und bleiben aussen vor, es sei
    # denn, sie tragen einen Teil des Moments (s_i, seit 14.10.2026)
    klein = 1e-12 * max((abs(w) for _s, w in paare), default=0.0)
    klein_s = 1e-12 * max((float(np.linalg.norm(v)) for v in s0.values()), default=0.0)

    def traegt(s, w):
        return abs(w) > klein or (mit_s and float(np.linalg.norm(s0[s])) > klein_s)
    ausgeschlossen = sum(1 for s, w in paare if s in bindung and abs(w) > klein)
    paare = [(s, w) for s, w in paare if s not in bindung and traegt(s, w)]
    aus = {"slaves": np.zeros(0, np.int64), "w": np.zeros(0), "s": None,
           "P": X[m].copy() if 0 <= m < nn else np.zeros(3),
           "normale": np.zeros(3), "ausgeschlossen": ausgeschlossen, "abstand_vorher": 0.0,
           "abstand_nachher": 0.0, "aenderung": 0.0, "negativ": 0}
    if not paare or not 0 <= m < nn or not sum(w for _s, w in paare):
        return aus
    S = np.asarray([s for s, _w in paare], np.int64)
    w = np.asarray([w for _s, w in paare], float)
    summe = w.sum()
    w = w / summe
    s_neu = np.asarray([s0[int(s)] for s in S], float) / summe if mit_s else None
    Xs = X[S]
    # Ebene der Flaechenknoten (alle gespeicherten, damit sie nicht vom
    # Ausschluss abhaengt) und Durchstosspunkt der Stabachse
    alle = np.asarray([s for s in sl_ if 0 <= s < nn and s != m], np.int64)
    c = X[alle].mean(axis=0)
    if len(alle) >= 3:
        _u, _s, vt = np.linalg.svd(X[alle] - c, full_matrices=False)
        n = vt[-1]
    else:
        n = stabachse(model, m)
    n = n / (np.linalg.norm(n) or 1.0)
    a = stabachse(model, m)
    P = X[m].copy()
    if float(np.linalg.norm(a)) > 0 and abs(float(a @ n)) > 1e-9:
        P = X[m] + float((c - X[m]) @ n) / float(a @ n) * a
    else:
        P = X[m] - float((X[m] - c) @ n) * n
    e1 = np.cross(n, [1.0, 0.0, 0.0])
    if np.linalg.norm(e1) < 0.5:
        e1 = np.cross(n, [0.0, 1.0, 0.0])
    e1 = e1 / np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    A = np.vstack([np.ones(len(w)), (Xs - P) @ e1, (Xs - P) @ e2])
    vorher = float(np.linalg.norm(A[1:] @ w))
    Cw = np.abs(w)
    M = (A * Cw) @ A.T
    w_neu = w
    try:
        if np.linalg.cond(M) < 1e12:
            lam = np.linalg.solve(M, np.array([1.0, 0.0, 0.0]) - A @ w)
            w_neu = w + Cw * (A.T @ lam)
    except np.linalg.LinAlgError:
        w_neu = w
    aus.update({"slaves": S, "w": w_neu, "s": s_neu, "P": P, "normale": n, "abstand_vorher": vorher,
                "abstand_nachher": float(np.linalg.norm(A[1:] @ w_neu)),
                "aenderung": float(np.max(np.abs(w_neu - w)) / max(float(np.max(np.abs(w))), 1e-300)),
                "negativ": int(np.sum(w_neu < 0.0))})
    return aus


def zwangsmatrix(model, sk, bindung=None) -> tuple:
    """(G, FHG, wirksam) einer verteilenden Kopplung fuer das Strafverfahren:
    die sechs Zeilen des RBE3 (verbindung.starrkoerper_matrix) mit den
    wirksamen Gewichten, die drei Momentenzeilen durch den Traegheitsradius
    rho geteilt; Spalten: die sechs FHG des Masters, dann die drei
    Verschiebungen je Slave.

    **Konsistente Momentenzeilen (seit 14.10.2026).** Traegt die Kopplung die
    Vektoren s_i = Integral N_i (x - x_m) dA (StarrKoerper.momente), stehen
    sie statt w_i r_i in den Momentenzeilen: Ein Moment geht dann als
    konsistente Last der linear verteilten Spannung in die Flaeche (Biegung
    als Normalspannung linear im Abstand, Torsion als Schub linear im
    Abstand), auch ueber die Ecken eines tri6. Bis dahin ging es als
    f_i = w_i (lambda_f + lambda_m x r_i), und an der Stirnflaeche lag die
    Biegespannung 7 % ueber der konsistenten (Theoriehandbuch, b009aff).
    rho^2 ist dann sum |s_i| |r_i| (klassisch: sum |w_i| |r_i|^2)."""
    from .elements import verbindung as vb
    from .model import NDOF
    wk = wirksame_gewichte(model, sk, bindung)
    S, w = wk["slaves"], wk["w"]
    if not len(S):
        return None, None, wk
    X = np.asarray(model.nodes, float)
    m = int(sk.master)
    s = wk.get("s")
    G = vb.starrkoerper_matrix(X[m], X[S], "RBE3", w, momente=s)
    r = X[S] - X[m]
    if s is not None:
        rho = math.sqrt(max(float(np.linalg.norm(s, axis=1) @ np.linalg.norm(r, axis=1)), 0.0)) or 1.0
    else:
        rho = math.sqrt(max(float(np.abs(w) @ np.einsum("ij,ij->i", r, r)), 0.0)) or 1.0
    G[3:6] /= rho
    spalten = list(range(6)) + [6 * (i + 1) + j for i in range(len(S)) for j in range(3)]
    fhg = list(range(NDOF * m, NDOF * m + NDOF)) + [NDOF * int(s) + j for s in S for j in range(3)]
    wk["rho"] = rho
    return G[:, spalten], np.asarray(fhg, np.int64), wk


# --------------------------------------------------------------------------
# Pruefung im Ergebnis: Kraftsumme und Moment je Stabende
# --------------------------------------------------------------------------
def pruefen(model, res, F_norm: float = None) -> dict:
    """Kraftsumme und Moment um den Durchstosspunkt je verteilend gekoppeltem
    Stabende gegen die Stabendkraefte.

    Die Kopplungskraefte sind f = k G^T G u (k: der Strafbeiwert der
    Rechnung, assemble.starrkoerper legt ihn als ``model._stabende_strafe``
    ab). Sie sind fuer jedes G u im Gleichgewicht - das folgt aus dem Aufbau
    des RBE3 -, also ist die Summe an den Flaechenknoten genau die Kraft am
    Master. Was die Pruefung misst, ist darum das Gleichgewicht am Stabknoten:
    die Kraft, die die Kopplung in die Flaeche gibt (F_kopplung, M_kopplung
    um den Durchstosspunkt), gegen die Kraft, die der Stab in den Knoten gibt
    - die Gegenkraft seiner Stabendkraft (res.beam_end, global, hinter einem
    Versatz) - samt Knotenlasten am Stabknoten (F_stab, M_stab). Ein Zugstab
    zieht die Flaeche zu sich: F_stab zeigt vom Volumen in den Stab. **Toleranz**: die Residuumschranke des Gleichungsloesers
    (Vorgabe 1e-6, Berechnung → Einstellungen → Experten) mal der Norm des
    Lastvektors - um mehr kann das Gleichgewicht eines Knotens nach dem
    Loesen nicht verfehlt sein, ||K u - F|| <= Schranke ||F||; dazu 1e-9 der
    Stabkraft als Rundung. Momente in Nm gegen dieselbe Zahl (die Norm
    mischt N und Nm wie der Loeser).

    Rueckgabe {"anzahl", "geprueft", "toleranz", "max_dF", "max_dM",
    "max_rel", "abweichend": [...], "ungeprueft": [...], "je_stabende": [...]}
    - nur Zahlen, Listen und Texte (das Ergebnis wird gespeichert)."""
    from . import assemble as asm
    from .model import NDOF
    sks = [sk for sk in (getattr(model, "starrkoerper", None) or []) if ist_verteilkopplung(sk)]
    if not sks:
        return {}
    k = getattr(model, "_stabende_strafe", None)
    aus = {"anzahl": len(sks), "geprueft": 0, "abweichend": [], "ungeprueft": [], "je_stabende": [],
           "max_dF": 0.0, "max_dM": 0.0, "max_rel": 0.0}
    u = getattr(res, "u", None)
    if k is None or u is None:
        aus["ungeprueft"] = [str(sk.name) for sk in sks]
        aus["grund"] = "ohne Strafbeiwert der Rechnung (Ergebnis nicht in diesem Lauf gerechnet)"
        return aus
    try:
        from . import parallel
        grenze = float(getattr(parallel.settings(), "solver_residuum", 1e-6) or 1e-6)
    except Exception:                      # noqa: BLE001
        grenze = 1e-6
    uf = np.asarray(u, float).reshape(-1)
    bindung = {int(t[0]) for t in asm.mittelknoten_bindungen(model)}
    X = np.asarray(model.nodes, float)
    beam = getattr(res, "beam_end", None) or {}
    faktoren = dict((getattr(res, "info", None) or {}).get("factors") or {})
    gelagert = {int(s.node) for s in (getattr(model, "supports", None) or [])}
    F_norm = float(F_norm) if F_norm is not None else 0.0
    for sk in sks:
        m = int(sk.master)
        G, fhg, wk = zwangsmatrix(model, sk, bindung)
        if G is None or fhg.max() >= len(uf):
            aus["ungeprueft"].append(str(sk.name))
            continue
        f = float(k) * (G.T @ (G @ uf[fhg]))
        # Kraft der Kopplung auf die Flaechenknoten (ein Element wirkt mit -f)
        fs = -f[6:].reshape(-1, 3)
        S = wk["slaves"]
        P = wk["P"]
        F_k = fs.sum(axis=0)
        M_k = np.cross(X[S] - P, fs).sum(axis=0)
        # Stabendkraefte am Knoten (global): die Elemente wirken mit -f auf ihn
        F_s, M_s = np.zeros(3), np.zeros(3)
        stab = []
        for i in stabelemente_an(model).get(m, []):
            e = model.elements[i]
            if i not in beam:
                continue
            fl = np.asarray(beam[i], float)[:12]
            A = asm.beam_versatz(e)
            if A is not None:
                fl = A.T @ fl
            _kl, _T3, T, _L = asm.beam_local(model, e)
            fg = T.T @ fl
            j = 0 if int(e.nodes[0]) == m else 6
            F_s += fg[j:j + 3]
            M_s += fg[j + 3:j + 6]
            stab.append(i)
        # Knotenlasten am Stabknoten (mit den Faktoren der Rechnung)
        F_l, M_l = np.zeros(3), np.zeros(3)
        for lc_name, fak in faktoren.items():
            lc = model.load_cases.get(lc_name)
            for nl in (getattr(lc, "nodal_loads", None) or []) if lc is not None else []:
                if int(nl.node) == m:
                    F_l += float(fak) * np.asarray(nl.F[:3], float)
                    M_l += float(fak) * np.asarray(list(nl.F[3:6]) + [0.0] * 3, float)[:3]
        if not stab or m in gelagert:
            aus["ungeprueft"].append(str(sk.name))
            continue
        # Was der Stab ueber den Knoten in die Flaeche gibt: die Gegenkraft
        # seiner Stabendkraft, dazu Knotenlasten am Stabknoten
        F_soll = F_l - F_s
        M_soll = M_l - M_s + np.cross(X[m] - P, F_soll)      # um den Durchstosspunkt
        dF = float(np.linalg.norm(F_k - F_soll))
        dM = float(np.linalg.norm(M_k - M_soll))
        tol = grenze * F_norm + 1e-9 * float(np.linalg.norm(F_soll)) + 1e-9
        tol_m = grenze * F_norm + 1e-9 * float(np.linalg.norm(M_soll)) + 1e-9 * max(float(wk.get("rho", 0.0)), 1e-3)
        zeile = {"name": str(sk.name), "knoten": m, "F_stab": [float(x) for x in F_soll],
                 "F_kopplung": [float(x) for x in F_k], "M_stab": [float(x) for x in M_soll],
                 "M_kopplung": [float(x) for x in M_k], "dF": dF, "dM": dM, "toleranz": tol,
                 "toleranz_M": tol_m, "ausgeschlossen": int(wk["ausgeschlossen"]),
                 "abstand_vorher": float(wk["abstand_vorher"]), "abstand_nachher": float(wk["abstand_nachher"])}
        aus["je_stabende"].append(zeile)
        aus["geprueft"] += 1
        aus["max_dF"] = max(aus["max_dF"], dF)
        aus["max_dM"] = max(aus["max_dM"], dM)
        aus["max_rel"] = max(aus["max_rel"], dF / max(float(np.linalg.norm(F_soll)), 1e-300)
                             if np.linalg.norm(F_soll) > 0 else 0.0)
        if dF > tol or dM > tol_m:
            aus["abweichend"].append(zeile)
    aus["toleranz"] = grenze * F_norm
    aus["schranke"] = grenze
    return aus


def _n(x: float) -> str:
    """Kraft [N] als Dezimalzahl mit Komma, nie wissenschaftlich."""
    from .zahlen import zahl_text
    return zahl_text(float(x), stellen=4)


def pruefzeilen(info: dict) -> list:
    """Die Zeilen der Pruefung fuer Protokoll und Zusammenfassung."""
    if not info or not info.get("anzahl"):
        return []
    z = []
    n, g = int(info["anzahl"]), int(info.get("geprueft", 0))
    wort = "Stabende" if n == 1 else "Stabenden"
    if g:
        z.append(f"Stabenden verteilt      : {n} {wort} über RBE3 eingeleitet, Kraftsumme und Moment "
                 f"geprüft: größte Abweichung {_n(info.get('max_dF', 0.0))} N und "
                 f"{_n(info.get('max_dM', 0.0))} Nm (Toleranz {_n(info.get('toleranz', 0.0))}, "
                 "Residuumschranke mal Lastvektor)")
    for zeile in info.get("abweichend") or []:
        z.append(f"WARNUNG                 : {zeile['name']}: Kraftsumme der Kopplung weicht um "
                 f"{_n(zeile['dF'])} N, das Moment um {_n(zeile['dM'])} Nm von der Stabendkraft ab "
                 f"(Toleranz {_n(zeile['toleranz'])})")
    if info.get("ungeprueft"):
        z.append(f"Stabenden verteilt      : {len(info['ungeprueft'])} nicht geprüft"
                 + (f" ({info['grund']})" if info.get("grund") else
                    " (Lager oder kein Stab am Stabknoten)"))
    return z


def pruefung_gebuendelt(ergebnisse) -> list:
    """Die Pruefung ueber alle Ergebnisse einer Rechnung in einer Zeile (und
    je Abweichung einer WARNUNG) - fuer Analysis.summary."""
    infos = [(str(n), (getattr(r, "info", None) or {}).get("stabenden_kraftsumme")) for n, r in ergebnisse]
    infos = [(n, i) for n, i in infos if i and i.get("anzahl")]
    if not infos:
        return []
    n_end = max(int(i["anzahl"]) for _n, i in infos)
    dF = max(float(i.get("max_dF", 0.0)) for _n, i in infos)
    dM = max(float(i.get("max_dM", 0.0)) for _n, i in infos)
    tol = min((float(i.get("toleranz", 0.0)) for _n, i in infos if i.get("geprueft")), default=0.0)
    z = [f"Stabenden verteilt: {n_end} {'Stabende' if n_end == 1 else 'Stabenden'} über RBE3 eingeleitet, "
         f"Kraftsumme und Moment in {len(infos)} {'Ergebnis' if len(infos) == 1 else 'Ergebnissen'} geprüft: "
         f"größte Abweichung {_n(dF)} N und {_n(dM)} Nm (kleinste Toleranz {_n(tol)})"]
    for n, i in infos:
        for zeile in i.get("abweichend") or []:
            z.append(f"WARNUNG: {n}: {zeile['name']} - Kraftsumme der Kopplung weicht um {_n(zeile['dF'])} N, "
                     f"das Moment um {_n(zeile['dM'])} Nm von der Stabendkraft ab (Toleranz {_n(zeile['toleranz'])})")
    return z


# --------------------------------------------------------------------------
# Hinweis bei Import und Rechenstart
# --------------------------------------------------------------------------
#: Name der Pruefung in der Netzabnahme (diagnose.Befund.pruefung)
PRUEFUNG = "Stabenden an wenigen Knoten"
HINWEIS = ("verteilende Einleitung über die Stirnfläche möglich (Modelleinstellung oder je Stabende)")


def hinweis(model) -> str:
    """Der gebuendelte Hinweis fuer Stabenden, die an 1-3 Volumenknoten
    haengen - etwa „48 Stabenden hängen an 1–3 Volumenknoten – verteilende
    Einleitung über die Stirnfläche möglich (Modelleinstellung oder je
    Stabende)“. Leer, wenn es keine gibt. Gezaehlt werden die angeschlossenen
    Stabenden mit starren Kopplungen (fugen.stabenden_koppeln); ohne Netz die
    Stabenden, die RFEM als integrierte Knoten auf einer Randflaeche eines
    Volumens fuehrt - sie haengen nach dem Vernetzen so. Umgestellt wird
    nichts."""
    from .begriffe import anzahl
    stabknoten = set(stabelemente_an(model))
    zahl: dict = {}
    for kp in (getattr(model, "kopplungen", None) or []):
        g = str(getattr(kp, "gruppe", "") or "")
        a = int(kp.node_a)
        if g.startswith(STABENDE) and a in stabknoten:
            zahl[a] = zahl.get(a, 0) + 1
    if zahl:
        n = len(zahl)
        lo, hi = min(zahl.values()), max(zahl.values())
        spanne = f"{lo}" if lo == hi else f"{lo}–{hi}"
        return (f"{anzahl(n, 'Stabende hängt', 'Stabenden hängen')} an {spanne} "
                f"Volumenknoten – {HINWEIS}")
    if any(str(getattr(kp, "gruppe", "") or "").startswith(STABENDE)
           for kp in (getattr(model, "kopplungen", None) or [])) \
            or any(ist_verteilkopplung(sk) for sk in (getattr(model, "starrkoerper", None) or [])):
        return ""
    # ohne Anschluesse: integrierte Knoten auf den Randflaechen der Volumen
    flaechen_im_volumen = {str(f) for k in (getattr(model, "koerper", None) or {}).values()
                           for f in (getattr(k, "flaechen", None) or [])}
    integriert = {int(n) for name, f in (getattr(model, "flaechen", None) or {}).items()
                  if name in flaechen_im_volumen for n in (getattr(f, "integrierte_knoten", None) or [])}
    enden = staebe_an_enden(model)
    kand = [n for n in sorted(integriert & stabknoten)
            if einstellung(model, n, enden)["art"] == "punkt"]
    if not kand:
        return ""
    return (f"{anzahl(len(kand), 'Stabende liegt', 'Stabenden liegen')} auf Volumen und "
            f"{'hängt' if len(kand) == 1 else 'hängen'} nach dem Vernetzen an 1–3 Volumenknoten – {HINWEIS}")


def abnahme_befund(model) -> list:
    """Der Hinweis als Befund der Netzabnahme (Stufe WARNUNG - er haelt nichts
    an, und umgestellt wird nichts)."""
    text = hinweis(model)
    if not text:
        return []
    from .diagnose import Befund
    zahl = int(text.split(" ", 1)[0]) if text.split(" ", 1)[0].isdigit() else 0
    return [Befund(pruefung=PRUEFUNG, objekt="Stabende", wert=float(zahl), grenze=0.0, stufe="WARNUNG",
                   text=text)]
