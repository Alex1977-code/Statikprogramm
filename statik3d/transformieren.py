"""Verschieben, Drehen, Spiegeln und Kopieren von Knoten, Linien, Staeben,
Flaechen und Volumen.

Wunsch vom 15.09.2026: „beim Modellieren sollte es möglich sein, per
Rechtsklick auf einen Knoten, Linie, Stab, Fläche, Volumen zu verschieben,
kopieren, spiegeln, drehen". Jede Abbildung ist x -> R x + t (R orthogonal;
det R = -1 bei einer Spiegelung). Gearbeitet wird auf der **Huelle** der
Auswahl: ein Volumen bringt seine Flaechen, die ihre Linien, die ihre Knoten
mit - und das Netz dazu.

Verschieben, Drehen und Spiegeln wirken **in place** auf die Knoten der
Huelle. Ein Knoten, den auch ein nicht gewaehltes Objekt benutzt, wandert mit
(so haengt eine Rippe an ihrem Blech) - wer das nicht will, kopiert.
Gespiegelte Schalen und Volumenelemente waeren umgestuelpt (negative
Jacobi-Determinante); ihr Netz wird darum geloescht, die Geometrie bleibt, und
man vernetzt neu. Stabelemente bleiben.

Kopieren legt neue Knoten, Linien, Flaechen, Volumen, Stabelemente und Staebe
an (fortlaufende Namen L…, F…, V…, S…) und nimmt das Netz mit, ausser bei
einer Spiegelung (siehe oben). Lager, Lasten und Kontaktbedingungen werden
nicht kopiert - Kontakte entstehen von selbst, wo die Kopie ein anderes
Volumen beruehrt (kontakte.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Elementtypen, deren Netz eine Spiegelung ueberlebt (zwei Knoten, keine Orientierung)
_STAEBE = {"beam", "truss", "seil", "feder"}
#: Punkte und Punktfolgen in Line.geometrie - werden wie Knoten abgebildet
_PUNKTFELDER = ("mitte", "anfang", "ende")
_PUNKTLISTEN = ("punkte", "steuerpunkte", "stuetzpunkte")
#: Richtungen in Line.geometrie - nur gedreht, nicht verschoben
_RICHTUNGEN = ("normale", "richtung", "a", "b")


@dataclass
class Auswahl:
    """Was abgebildet wird - Nummern bzw. Namen je Objektart."""
    knoten: list = field(default_factory=list)
    linien: list = field(default_factory=list)
    staebe: list = field(default_factory=list)
    flaechen: list = field(default_factory=list)
    koerper: list = field(default_factory=list)
    elemente: list = field(default_factory=list)

    def leer(self) -> bool:
        return not (self.knoten or self.linien or self.staebe or self.flaechen
                    or self.koerper or self.elemente)

    def text(self) -> str:
        teile = []
        for liste, was in ((self.koerper, "Volumen"), (self.flaechen, "Flächen"), (self.staebe, "Stäbe"),
                           (self.linien, "Linien"), (self.elemente, "Elemente"), (self.knoten, "Knoten")):
            if liste:
                teile.append(f"{len(liste)} {was}")
        return ", ".join(teile) or "nichts"


# --------------------------------------------------------------------------
# Abbildungen
# --------------------------------------------------------------------------
def _v(p) -> np.ndarray:
    return np.asarray(p, float).reshape(3)


def _einheit(v) -> np.ndarray:
    v = _v(v)
    n = float(np.linalg.norm(v))
    if n < 1e-14:
        raise ValueError("Die Richtung hat die Länge null")
    return v / n


def verschiebung(vektor) -> tuple:
    """x -> x + v."""
    return np.eye(3), _v(vektor)


def drehung(punkt, achse, winkel_grad: float) -> tuple:
    """Drehung um die Achse durch ``punkt`` in Richtung ``achse`` (Rodrigues)."""
    k = _einheit(achse)
    a = np.radians(float(winkel_grad))
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    R = np.eye(3) + np.sin(a) * K + (1 - np.cos(a)) * (K @ K)
    p = _v(punkt)
    return R, p - R @ p


def spiegelung(punkt, normale) -> tuple:
    """Spiegelung an der Ebene durch ``punkt`` mit Normale ``normale``."""
    n = _einheit(normale)
    R = np.eye(3) - 2.0 * np.outer(n, n)
    p = _v(punkt)
    return R, p - R @ p


def ist_spiegelung(R) -> bool:
    return float(np.linalg.det(np.asarray(R, float))) < 0


def verketten(R, t, k: int) -> tuple:
    """Die Abbildung k-mal hintereinander (fuer die k-te Kopie)."""
    Rk, tk = np.eye(3), np.zeros(3)
    for _ in range(int(k)):
        Rk, tk = R @ Rk, R @ tk + t
    return Rk, tk


def _geometrie_abbilden(g: dict, R, t) -> dict:
    """Line.geometrie (Mittelpunkt, Normale, Steuerpunkte …) mit abbilden -
    sonst bliebe ein Kreis stehen, dessen Knoten gewandert sind."""
    aus = dict(g or {})
    for key in _PUNKTFELDER:
        if key in aus and aus[key] is not None:
            aus[key] = (R @ _v(aus[key]) + t).tolist()
    for key in _PUNKTLISTEN:
        if key in aus and aus[key] is not None:
            aus[key] = [(R @ _v(p) + t).tolist() for p in aus[key]]
    for key in _RICHTUNGEN:
        if key in aus and aus[key] is not None:
            aus[key] = (R @ _v(aus[key])).tolist()
    return aus


# --------------------------------------------------------------------------
# Die Huelle der Auswahl
# --------------------------------------------------------------------------
def huelle(model, a: Auswahl) -> dict:
    """Alles, was zur Auswahl gehoert: Volumen -> Flaechen -> Linien ->
    Knoten, Staebe -> Elemente -> Knoten, dazu das Netz der Flaechen und
    Volumen. Rueckgabe {"koerper", "flaechen", "linien", "staebe",
    "elemente", "knoten"} - Listen in Modellreihenfolge, ``knoten`` sortiert."""
    koerper = [k for k in a.koerper if k in model.koerper]
    flaechen = list(dict.fromkeys([f for f in a.flaechen if f in model.flaechen]
                                  + [f for k in koerper for f in (model.koerper[k].flaechen or [])
                                     if f in model.flaechen]))
    linien = list(a.linien)
    for f in flaechen:
        fl = model.flaechen[f]
        linien += list(fl.linien or []) + [ln for loch in (fl.oeffnungen or []) for ln in loch]
    linien = list(dict.fromkeys([ln for ln in linien if ln in model.lines]))
    staebe = [s for s in a.staebe if s in model.members]
    elemente = [int(e) for e in a.elemente]
    for s in staebe:
        elemente += [int(e) for e in (model.members[s].elements or [])]
    for f in flaechen:
        elemente += [int(e) for e in (model.flaechen[f].elemente or [])]
    for k in koerper:
        elemente += [int(e) for e in (model.koerper[k].elemente or [])]
    # Stabelemente, die auf einer gewaehlten Linie liegen (RFEM: Element.line)
    if linien:
        lset = set(linien)
        elemente += [i for i, e in enumerate(model.elements) if str(getattr(e, "line", "") or "") in lset]
    elemente = [e for e in dict.fromkeys(elemente) if 0 <= e < len(model.elements)]
    knoten = {int(n) for n in a.knoten if 0 <= int(n) < model.nn}
    for ln in linien:
        knoten |= {int(n) for n in model.lines[ln].nodes if 0 <= int(n) < model.nn}
    for f in flaechen:
        knoten |= {int(n) for n in (model.flaechen[f].ecken or []) if 0 <= int(n) < model.nn}
    for e in elemente:
        knoten |= {int(n) for n in model.elements[e].nodes if 0 <= int(n) < model.nn}
    return {"koerper": koerper, "flaechen": flaechen, "linien": linien, "staebe": staebe,
            "elemente": elemente, "knoten": sorted(knoten)}


# --------------------------------------------------------------------------
# In place: verschieben, drehen, spiegeln
# --------------------------------------------------------------------------
def anwenden(model, a: Auswahl, R, t, log: list = None) -> dict:
    """Die Auswahl in place abbilden. Rueckgabe {"knoten": n, "netz_geloescht": n}."""
    R = np.asarray(R, float)
    t = _v(t)
    h = huelle(model, a)
    idx = h["knoten"]
    if idx:
        model.nodes[idx] = (R @ np.asarray(model.nodes[idx], float).T).T + t
    for ln in h["linien"]:
        model.lines[ln].geometrie = _geometrie_abbilden(model.lines[ln].geometrie, R, t)
    weg = 0
    if ist_spiegelung(R):
        # Umgestuelpte Schalen und Volumenelemente: das Netz geht, die Geometrie bleibt
        umgestuelpt = [e for e in h["elemente"] if model.elements[e].typ not in _STAEBE]
        if umgestuelpt:
            weg = model.elemente_loeschen(umgestuelpt)
            for f in h["flaechen"]:
                fl = model.flaechen[f]
                fl.elemente, fl.randseiten = [], []
            for k in h["koerper"]:
                model.koerper[k].elemente = []
    if log is not None:
        log.append(f"{a.text()} abgebildet: {len(idx)} Knoten"
                   + (f", {weg} umgestülpte Elemente gelöscht (neu vernetzen)" if weg else ""))
    return {"knoten": len(idx), "netz_geloescht": weg}


# --------------------------------------------------------------------------
# Kopieren
# --------------------------------------------------------------------------
def kopieren(model, a: Auswahl, R, t, anzahl: int = 1, mit_netz: bool = True, log: list = None) -> dict:
    """``anzahl`` Kopien der Auswahl anlegen, die k-te mit der k-fachen
    Abbildung. Rueckgabe: neue Namen je Art und die Zahl neuer Knoten und
    Elemente."""
    from .model import Flaeche, Line, Member, Volumenkoerper
    R = np.asarray(R, float)
    t = _v(t)
    h = huelle(model, a)
    spiegel = ist_spiegelung(R)
    aus = {"knoten": 0, "elemente": 0, "linien": [], "flaechen": [], "koerper": [], "staebe": [],
           "netz_uebergangen": 0}
    for k in range(1, max(int(anzahl), 1) + 1):
        Rk, tk = verketten(R, t, k)
        # Knoten
        alt = h["knoten"]
        neu_idx = model.add_nodes((Rk @ np.asarray(model.nodes[alt], float).T).T + tk) if alt else []
        kn = {int(o): int(n) for o, n in zip(alt, neu_idx)}
        aus["knoten"] += len(alt)
        # Linien
        lmap: dict = {}
        for ln in h["linien"]:
            alt_ln = model.lines[ln]
            name = model.naechster_name("L", model.lines)
            model.lines[name] = Line(name, [kn.get(int(n), int(n)) for n in alt_ln.nodes], alt_ln.typ,
                                     alt_ln.comment, _geometrie_abbilden(alt_ln.geometrie, Rk, tk))
            lmap[ln] = name
            aus["linien"].append(name)
        # Elemente (Volumen- und Schalenelemente nicht bei einer Spiegelung)
        emap: dict = {}
        gruppen = {}
        for f in h["flaechen"]:
            gruppen[f] = model.naechster_name("F", {**model.flaechen, **{x: 1 for x in gruppen.values()}})
        kgruppen = {}
        for kk in h["koerper"]:
            kgruppen[kk] = model.naechster_name("V", {**model.koerper, **{x: 1 for x in kgruppen.values()}})
        for e in h["elemente"]:
            el = model.elements[e]
            if not mit_netz and el.typ not in _STAEBE:
                continue
            if spiegel and el.typ not in _STAEBE:
                aus["netz_uebergangen"] += 1
                continue
            e2 = el.kopie()
            e2.nodes = [kn.get(int(n), int(n)) for n in el.nodes]
            grp = str(getattr(el, "group", "") or "")
            e2.group = kgruppen.get(grp, gruppen.get(grp, grp))
            if getattr(el, "line", ""):
                e2.line = lmap.get(el.line, el.line)
            model.elements.append(e2)
            emap[e] = len(model.elements) - 1
        aus["elemente"] += len(emap)
        # Flaechen
        for f in h["flaechen"]:
            fl = model.flaechen[f]
            name = gruppen[f]
            neu = Flaeche(name, [lmap.get(x, x) for x in (fl.linien or [])], typ=fl.typ, dicke=fl.dicke,
                          material=fl.material, teilung=list(fl.teilung or [4, 4]),
                          elemente=[emap[e] for e in (fl.elemente or []) if e in emap],
                          kommentar=fl.kommentar,
                          oeffnungen=[[lmap.get(x, x) for x in loch] for loch in (fl.oeffnungen or [])],
                          randseiten=[[emap[int(e)], int(s)] for e, s in (fl.randseiten or []) if int(e) in emap],
                          steifigkeit=fl.steifigkeit, ecken=[kn.get(int(n), int(n)) for n in (fl.ecken or [])],
                          quellart=fl.quellart,
                          gelenklinien=[lmap.get(x, x) for x in (fl.gelenklinien or [])],
                          gelenkwirkung=fl.gelenkwirkung)
            model.flaechen[name] = neu
            aus["flaechen"].append(name)
        # Volumen
        for kk in h["koerper"]:
            ko = model.koerper[kk]
            name = kgruppen[kk]
            neu = Volumenkoerper(name, [gruppen.get(x, x) for x in (ko.flaechen or [])], material=ko.material,
                                 teilung=list(ko.teilung or [4, 4, 4]),
                                 elemente=[emap[e] for e in (ko.elemente or []) if e in emap],
                                 kommentar=ko.kommentar, kerbfall=ko.kerbfall, kerbfall_konzept=ko.kerbfall_konzept,
                                 kerbfall_naht=ko.kerbfall_naht, assessment=ko.assessment,
                                 consequence=ko.consequence)
            model.koerper[name] = neu
            aus["koerper"].append(name)
        # Staebe mit Nachweis
        for s in h["staebe"]:
            mem = model.members[s]
            elems = [emap[e] for e in (mem.elements or []) if e in emap]
            if not elems:
                continue
            name = model.naechster_name("S", model.members)
            neu = Member(name, elems)
            for feld in ("design", "beta_y", "beta_z", "Lcr_y", "Lcr_z", "L_LT", "k_z", "k_w", "C1",
                         "load_position", "lt_check", "sway_y", "sway_z", "a_steifen"):
                if hasattr(mem, feld):
                    setattr(neu, feld, getattr(mem, feld))
            model.members[name] = neu
            aus["staebe"].append(name)
    if log is not None:
        log.append(f"{a.text()} {anzahl}× kopiert: {aus['knoten']} Knoten, {len(aus['linien'])} Linien, "
                   f"{len(aus['flaechen'])} Flächen, {len(aus['koerper'])} Volumen, {aus['elemente']} Elemente"
                   + (f"; {aus['netz_uebergangen']} Schalen-/Volumenelemente nicht mitgespiegelt (neu vernetzen)"
                      if aus["netz_uebergangen"] else ""))
    return aus
