"""
Singularitaeten auffindbar machen: **welches Bauteil** kann sich **wie** bewegen.

Bricht der Loeser mit „Factor is exactly singular" ab, half bisher nur eine
Liste von Vermutungen. Bei 108 Volumen und 88 Netzteilen ist das nicht
pruefbar. Dieses Modul nennt statt dessen das Teil, die Richtung und die
Ursache - und liefert die Bewegung als Vektor, damit die Ansicht sie zeigen
kann.

Drei Stufen
-----------

**Stufe 1a - Restfreiheiten je Teiltragwerk.** Ein Teil, das nur ueber
Elemente und Kopplungen zusammenhaengt (:func:`diagnose.teiltragwerke`), ist
in sich starr. Eine Starrkoerperbewegung ist

    u(p) = t + omega x r,      r = p - c   (c = Schwerpunkt des Teils)

Eine Halterung am Knoten p in Richtung d sperrt d·u(p) = d·t + omega·(r x d).
Auf den Unbekannten x = [t, L·omega] ist das die Zeile

    a = [ d , (r x d) / L ]        L = halbe Diagonale des umschliessenden Kastens

Die Skalierung mit L ist nicht kosmetisch: ohne sie haengt die
Rangentscheidung von der Laengeneinheit ab - dasselbe Modell waere in
Millimetern gehalten und in Metern beweglich.

Alle Zeilen auf Norm 1, A = Sum(a^T a) (6x6), Eigenzerlegung. Eigenwerte unter
:data:`NULLRAUM` mal dem groessten spannen den Nullraum: Bewegungen, die keine
einzige Halterung dehnt oder staucht - das Teil **gleitet**.

**Stufe 1b - Kegelpruefung.** Stufe 1a nimmt Kontaktnormalen als beidseitig.
Ein geschlossener Kontakt kann aber nur druecken; der zulaessige Bereich ist
ein Kegel

    C = { x :  a_i·x = 0  (Lager, haftende Tangenten)
               a_j·x >= 0 (Kontaktnormalen; >= 0 heisst: die Fuge oeffnet) }

Das Teil ist gehalten genau dann, wenn C = {0}. Geprueft wird als kleines LP
im Nullraum der Gleichungszeilen - hoechstens sechs Veraenderliche. Eine
Bewegung im Kegel, die nicht schon im Nullraum aus 1a liegt, oeffnet
mindestens einen Kontakt: das Teil **hebt ab**. Diese Unterscheidung fehlte
bisher ganz; die alte Meldung warf „hebt ab" und „rutscht" zusammen, obwohl
das verschiedene Ursachen und verschiedene Abhilfen sind.

**Stufe 2 - Matrixdiagnose nach dem Abbruch.** Fuer Faelle ohne
Starrkoerpermodus: weiche Mechanismen, Nullsteifigkeit, Splitterelemente.
Inverse Iteration auf K + eps·I liefert praktisch den niedrigsten Modus; die
Knoten mit der groessten Amplitude nennen das Bauteil. Kosten: eine
Faktorisierung.

Was dieses Modul **nicht** tut
------------------------------

Es repariert nichts. Ob eine Fuge Reibung bekommt oder ein Bauteil ein Lager,
ist eine Modellierungsentscheidung. Es stabilisiert auch nichts mit weichen
Federn - das versteckte genau das, was hier sichtbar werden soll.

Zur Reibung
-----------

Reibung ist kraftabhaengig: vor der Rechnung ist die Normalkraft null und die
Tangentialhaltung damit formal auch. Fuer die Vorabpruefung zaehlt ``mu > 0``
trotzdem als Haltung - sonst meldete jede reibungsbehaftete Fuge eine
Bewegung, die es unter Last nicht gibt. Der Text sagt es dazu („nur ueber
Reibung gehalten"), damit niemand die Meldung fuer einen Freibrief haelt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

#: Eigenwerte unter diesem Anteil des groessten gelten als null (Stufe 1a).
NULLRAUM = 1e-6

#: Hoechstzahl der Bewegungen, die eine Stufe zurueckgibt. Ein Modell mit 88
#: losen Teilen braucht keine 88 Meldungen, um verstanden zu werden.
HOECHSTENS = 40

#: Kleinster Anteil, ab dem ein Drehanteil als Drehung gilt (sonst reine
#: Verschiebung). Bezogen auf |L·omega| gegen |t|.
DREH_ANTEIL = 1e-6


@dataclass
class Singularitaet:
    """Eine Bewegung, die das Modell nicht haelt.

    art:     'gleitet' (alle Halterungen bleiben unverspannt) | 'hebt ab'
             (die Kontakte oeffnen dabei) | 'numerisch' (aus Stufe 2)
    knoten:  Knoten des betroffenen Teils
    koerper: Namen der Bauteile - fuer Baum und Text
    t:       Verschiebungsanteil (3,), auf 1 normiert
    omega:   Drehanteil (3,), in 1/L
    bezug:   Bezugspunkt: Schwerpunkt des Teils bzw. Punkt auf der Drehachse
    feld:    Knotenvektorfeld (nn, 3) - nur bei art='numerisch'
    text:    „Achse (V30) kann laengs der Achse gleiten"
    ursache: „Kontaktbedingung 'Achse': in der Fugenebene nichts gehalten"
    abhilfe: ('kontakt', Name) | ('lager', Knoten) | None
    """
    art: str = "gleitet"
    knoten: list = field(default_factory=list)
    koerper: list = field(default_factory=list)
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))
    omega: np.ndarray = field(default_factory=lambda: np.zeros(3))
    bezug: np.ndarray = field(default_factory=lambda: np.zeros(3))
    feld: Optional[np.ndarray] = None
    text: str = ""
    ursache: str = ""
    abhilfe: Optional[tuple] = None

    def verschiebung(self) -> bool:
        """Reine Verschiebung (kein nennenswerter Drehanteil)?"""
        return float(np.linalg.norm(self.omega)) <= DREH_ANTEIL

    def bezeichnung(self) -> str:
        """Kurzform fuer den Modellbaum."""
        wo = ", ".join(self.koerper[:3]) + (" …" if len(self.koerper) > 3 else "")
        return f"{wo or 'Teil'} - {self.text}" if self.text else (wo or "Teil")


# --------------------------------------------------------------------------
# Starrkoerperzeilen
# --------------------------------------------------------------------------
def _zeile(punkt, richtung, mitte, L: float) -> np.ndarray:
    """Die Zeile a = [d, (r x d)/L] einer Halterung in Richtung ``richtung``."""
    d = np.asarray(richtung, float)
    n = np.linalg.norm(d)
    if n <= 0:
        return None
    d = d / n
    r = np.asarray(punkt, float) - mitte
    a = np.concatenate([d, np.cross(r, d) / L])
    na = np.linalg.norm(a)
    return a / na if na > 0 else None


def _drehzeile(achse) -> np.ndarray:
    """Die Zeile einer gesperrten Knotenverdrehung: omega·e = 0."""
    e = np.asarray(achse, float)
    n = np.linalg.norm(e)
    return np.concatenate([np.zeros(3), e / n]) if n > 0 else None


def _mitte_und_laenge(P: np.ndarray) -> tuple:
    """Schwerpunkt und halbe Diagonale des umschliessenden Kastens."""
    mitte = P.mean(axis=0)
    L = 0.5 * float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    return mitte, (L if L > 0 else 1.0)


def _lagerzeilen(model, knoten: set, mitte, L: float) -> list:
    """Zeilen aus Knoten-, Linien- und Flaechenlagern des Teils.

    Eine Feder haelt genauso wie ein starres Lager - nur weicher; fuer die
    Frage, **ob** gehalten wird, zaehlt sie mit. Ein Lager mit Ausfall zaehlt
    dagegen nur als Ungleichung: es kann sich loesen.
    """
    zeilen, ungleich = [], []
    achsen = np.eye(3)
    for s in getattr(model, "supports", None) or []:
        k = int(getattr(s, "node", -1))
        if k not in knoten:
            continue
        p = model.nodes[k]
        for dof in range(6):
            b = s.dof_behaviour(dof)
            if not getattr(b, "acts", False):
                continue
            a = (_zeile(p, achsen[dof], mitte, L) if dof < 3
                 else _drehzeile(achsen[dof - 3]))
            if a is None:
                continue
            # Ausfall bei Zug/Druck: das Lager haelt nur in einer Richtung
            (ungleich if getattr(b, "failure", "") else zeilen).append(a)
    for ls in getattr(model, "line_supports", None) or []:
        zeilen += _flaechenlagerzeilen(model, ls, knoten, mitte, L)
    for ss in getattr(model, "surface_supports", None) or []:
        zeilen += _flaechenlagerzeilen(model, ss, knoten, mitte, L)
    return zeilen, ungleich


def _flaechenlagerzeilen(model, lager, knoten: set, mitte, L: float) -> list:
    """Zeilen eines Linien- oder Flaechenlagers - je Knoten und Richtung."""
    kn = [int(k) for k in (getattr(lager, "nodes", None) or []) if int(k) in knoten]
    if not kn:
        return []
    achsen = np.eye(3)
    aus = []
    beh = getattr(lager, "behaviour", None) or {}
    for dof, b in beh.items():
        d = int(dof)
        if not getattr(b, "acts", False) or d >= 3:
            continue
        for k in kn:
            a = _zeile(model.nodes[k], achsen[d], mitte, L)
            if a is not None:
                aus.append(a)
    return aus


def _dreiecke(model, cp) -> tuple:
    """(Ecken, Schwerpunkte, Normalen, Knoten) der Master-Seite, in Dreiecke zerlegt.

    Die Normale zeigt **aus dem Master heraus**, also zum Slave hin: eine
    Bewegung des Slaves in +n oeffnet die Fuge, eine des Masters in -n
    ebenso. Bei Volumenfacetten gibt der Elementschwerpunkt die Richtung
    (:func:`contact._solid_outward`); bei ausdruecklich gegebenen Facetten
    steht die Richtung schon in der Knotenreihenfolge - so legt
    :func:`fugen._fuge_ueber_kontaktpaar` sie ab.

    Vierecke werden wie im Loeser in zwei Dreiecke geteilt, damit der Abstand
    eines Knotens zur Flaeche derselbe ist wie dort.
    """
    from .contact import master_facets, _solid_outward
    facetten = master_facets(model, cp)
    if not facetten:
        return (np.zeros((0, 3, 3)), np.zeros((0, 3)), np.zeros((0, 3)), [])
    innen = _solid_outward(model, cp)
    E, S, N, KN = [], [], [], []
    for f in facetten:
        kn = [int(x) for x in f]
        key = tuple(sorted(kn))
        teile = [(0, 1, 2)] if len(kn) == 3 else [(0, 1, 2), (0, 2, 3)]
        for tri in teile:
            P = model.nodes[[kn[i] for i in tri]]
            nv = np.cross(P[1] - P[0], P[2] - P[0])
            ln = np.linalg.norm(nv)
            if ln <= 0:
                continue
            nv = nv / ln
            mitte = P.mean(axis=0)
            if key in innen and nv @ (innen[key] - mitte) > 0:
                nv = -nv
            E.append(P)
            S.append(mitte)
            N.append(nv)
            KN.append(kn)
    if not S:
        return (np.zeros((0, 3, 3)), np.zeros((0, 3)), np.zeros((0, 3)), [])
    return np.array(E), np.array(S), np.array(N), KN


def _kontaktzeilen(model, teil_von: dict, mitten: dict, laengen: dict) -> dict:
    """Zeilen aus Kontaktpaaren und Spaltelementen, je Teiltragwerk.

    Rueckgabe {Teil: (Gleichungen, Ungleichungen, Namen der Fugen)}. Eine
    Kontaktnormale ist eine **Ungleichung** - die Fuge kann aufgehen. Haelt
    die Fuge in ihrer Ebene (haftend oder mit Reibbeiwert), kommen die beiden
    Tangenten als Gleichungen dazu.

    Die Paarung Slave-Knoten gegen Master-Facette wird hier neu gesucht statt
    aus dem Loeser uebernommen: die Vorabpruefung laeuft, **bevor** es ein
    Kontaktsystem gibt. Gesucht wird ueber die naechste Facette; der genaue
    Projektionspunkt spielt fuer eine Richtungsfrage keine Rolle, der
    Hebelarm aendert sich hoechstens um eine Facettengroesse.
    """
    from scipy.spatial import cKDTree
    from .contact import _tangent_basis
    aus: dict = {}

    def dazu(teil, a, art, name):
        if a is None or teil is None:
            return
        g, u, namen = aus.setdefault(teil, ([], [], set()))
        (g if art == "=" else u).append(a)
        namen.add(name)

    from .contact import naechste_punkte_dreiecke
    groesse = float(model.characteristic_size())
    for cp in getattr(model, "contact_pairs", None) or []:
        E, S, N, KN = _dreiecke(model, cp)
        if not len(S):
            continue
        haelt = bool(getattr(cp, "haften", False)) or float(getattr(cp, "mu", 0.0)) > 0
        verbund = bool(getattr(cp, "zug", False))
        radius = float(getattr(cp, "search_radius", 0.0) or 0.0) or 0.1 * groesse
        spalt = float(getattr(cp, "gap", 0.0) or 0.0)
        # Was weiter weg liegt als der Suchradius oder wo die Fuge offen
        # steht, haelt **nichts** - auch nicht gegen Druck. Ein Bauteil, das
        # ueber seiner Unterlage schwebt, ist frei und nicht etwa gelagert.
        offen = 1e-9 * groesse
        baum = cKDTree(S)
        anzahl = min(8, len(S))
        for sk in (cp.slave_nodes or []):
            k = int(sk)
            teil = teil_von.get(k)
            if teil is None:
                continue
            p = model.nodes[k]
            kand = np.atleast_1d(baum.query(p, k=anzahl)[1]).astype(int)
            q, _w = naechste_punkte_dreiecke(p, E[kand, 0], E[kand, 1], E[kand, 2])
            d = np.linalg.norm(q - p, axis=1)
            j = int(np.argmin(d))
            if d[j] > radius:
                continue                      # ausser Reichweite
            n = N[kand[j]]
            if not (verbund or cp.anliegend) and float((p - q[j]) @ n) - spalt > offen:
                continue                      # die Fuge steht offen
            art = "=" if verbund else ">"
            dazu(teil, _zeile(p, n, mitten[teil], laengen[teil]), art, cp.name)
            if haelt or verbund:
                for t in _tangent_basis(n):
                    dazu(teil, _zeile(p, t, mitten[teil], laengen[teil]), "=", cp.name)
        # Die Gegenseite: an jeder Facette wirkt dieselbe Normale, nur
        # andersherum. Ohne sie stuende jedes Bauteil, das ausschliesslich
        # Gegenseite ist, faelschlich als ungehalten da.
        naeh = cKDTree(model.nodes[[int(x) for x in (cp.slave_nodes or [])]]) \
            if cp.slave_nodes else None
        for mitte_f, n, kn in zip(S, N, KN):
            teil = next((teil_von[k] for k in kn if k in teil_von), None)
            if teil is None:
                continue
            if naeh is not None and float(naeh.query(mitte_f)[0]) > radius:
                continue                      # kein Slave in Reichweite dieser Facette
            art = "=" if verbund else ">"
            dazu(teil, _zeile(mitte_f, -n, mitten[teil], laengen[teil]), art, cp.name)
            if haelt or verbund:
                for t in _tangent_basis(n):
                    dazu(teil, _zeile(mitte_f, t, mitten[teil], laengen[teil]), "=", cp.name)

    for g in getattr(model, "gap_elements", None) or []:
        a_, b_ = int(getattr(g, "node_a", -1)), int(getattr(g, "node_b", -1))
        d = getattr(g, "direction", None)
        if d is None:
            if not (0 <= a_ < model.nn and 0 <= b_ < model.nn):
                continue
            d = model.nodes[b_] - model.nodes[a_]
        name = str(getattr(g, "group", "") or "Spaltelement")
        for k, vz in ((a_, -1.0), (b_, 1.0)):
            teil = teil_von.get(k)
            if teil is None:
                continue
            dazu(teil, _zeile(model.nodes[k], vz * np.asarray(d, float),
                              mitten[teil], laengen[teil]), ">", name)
            if float(getattr(g, "mu", 0.0)) > 0:
                for t in _tangent_basis(np.asarray(d, float)):
                    dazu(teil, _zeile(model.nodes[k], t, mitten[teil],
                                      laengen[teil]), "=", name)
    return aus


# --------------------------------------------------------------------------
# Stufe 1a und 1b
# --------------------------------------------------------------------------
def _nullraum(zeilen: list) -> np.ndarray:
    """Nullraum der Zeilen als (6, k) - Bewegungen, die keine Zeile dehnt."""
    if not zeilen:
        return np.eye(6)
    A = np.zeros((6, 6))
    for a in zeilen:
        A += np.outer(a, a)
    w, V = np.linalg.eigh(A)
    grenze = NULLRAUM * max(float(w.max()), 1e-300)
    return V[:, w <= grenze]


def _im_kegel(N: np.ndarray, ungleich: list):
    """Eine Bewegung im Kegel { N·y : a·(N·y) >= 0 } ausser der Null - oder None.

    Das Machbarkeits-LP hat hoechstens sechs Veraenderliche. Die Normierung
    Summe(a·N)·y >= 1 schliesst die Null aus und zugleich die Richtungen, die
    **jede** Ungleichung mit Gleichheit erfuellen - die sind schon der
    Nullraum aus Stufe 1a und stehen dort als „gleitet".
    """
    if N.shape[1] == 0:
        return None
    if not ungleich:
        return N[:, 0]
    from scipy.optimize import linprog
    B = np.array([a @ N for a in ungleich])          # (m, k)
    if not np.any(np.abs(B) > 1e-12):
        return None
    # -B·y <= 0 und -(Summe B)·y <= -1
    A_ub = np.vstack([-B, -B.sum(axis=0)[None, :]])
    b_ub = np.concatenate([np.zeros(len(B)), [-1.0]])
    k = N.shape[1]
    r = linprog(np.zeros(k), A_ub=A_ub, b_ub=b_ub,
                bounds=[(-1e6, 1e6)] * k, method="highs")
    if not getattr(r, "success", False) or r.x is None:
        return None
    x = N @ np.asarray(r.x, float)
    nx = float(np.linalg.norm(x))
    return x / nx if nx > 1e-12 else None


def _klartext(x: np.ndarray, mitte, L: float, koerper: list, art: str,
              fugen: list) -> tuple:
    """(Text, Ursache, Bezugspunkt, t, omega) aus dem Bewegungsvektor.

    Schraubenzerlegung: ist der Drehanteil vernachlaessigbar, ist es eine
    Verschiebung; sonst eine Drehung um die Achse omega durch den Punkt
    c + (omega x t)/|omega|^2, gegebenenfalls mit einem Verschiebungsanteil
    laengs der Achse (Schraubbewegung).
    """
    t, w = np.asarray(x[:3], float), np.asarray(x[3:], float) / L
    wo = ", ".join(koerper[:3]) + (" …" if len(koerper) > 3 else "") or "Ein Bauteil"
    fug = ", ".join(sorted(fugen)[:3]) + (" …" if len(fugen) > 3 else "")
    lw = float(np.linalg.norm(w)) * L
    if lw <= DREH_ANTEIL:
        richtung = t / (np.linalg.norm(t) or 1.0)
        wie = f"Verschiebung längs ({richtung[0]:.2f}, {richtung[1]:.2f}, {richtung[2]:.2f})"
        bezug = np.asarray(mitte, float)
    else:
        e = w / np.linalg.norm(w)
        bezug = np.asarray(mitte, float) + np.cross(w, t) / float(w @ w)
        laengs = float(t @ e)
        wie = (f"Drehung um ({e[0]:.2f}, {e[1]:.2f}, {e[2]:.2f})"
               + (" mit Verschiebung längs derselben Achse (Schraubbewegung)"
                  if abs(laengs) > DREH_ANTEIL else ""))
    if art == "hebt ab":
        text = f"{wo} hebt ab: {wie}"
        ursache = ("Alle Kontakte öffnen bei dieser Bewegung"
                   + (f" (Fugen {fug})" if fug else "")
                   + " - kein Lager hält dagegen.")
    else:
        text = f"{wo}: {wie}"
        ursache = ((f"Die Fugen {fug} übertragen nur Druck senkrecht zur Fläche; "
                    "in der Fugenebene ist nichts gehalten (keine Reibung, keine Federn)."
                    ) if fug else
                   "Das Bauteil hat weder Lager noch eine Kopplung an ein gelagertes Teil.")
    return text, ursache, bezug, t, w


def restfreiheiten(model, hoechstens: int = HOECHSTENS) -> list:
    """Stufe 1a und 1b: was sich bewegen kann, bevor gerechnet wird.

    Rueckgabe eine Liste von :class:`Singularitaet`. Kostet eine
    6x6-Eigenwertaufgabe und ein kleines LP je Teiltragwerk.
    """
    from .diagnose import teiltragwerke
    teile = teiltragwerke(model)
    if not teile:
        return []
    teil_von, mitten, laengen = {}, {}, {}
    for i, g in enumerate(teile):
        for k in g:
            teil_von[int(k)] = i
        mitten[i], laengen[i] = _mitte_und_laenge(model.nodes[list(g)])
    kontakt = _kontaktzeilen(model, teil_von, mitten, laengen)
    gruppe_von = _gruppen_je_knoten(model)

    aus: list = []
    for i, g in enumerate(teile):
        knoten = {int(k) for k in g}
        gl, ug = _lagerzeilen(model, knoten, mitten[i], laengen[i])
        kg, ku, fugen = kontakt.get(i, ([], [], set()))
        gl = gl + kg
        ug = ug + ku
        # Stufe 1a: alles als Gleichung - findet die Gleitbewegungen
        frei = _nullraum(gl + ug)
        koerper = sorted({gruppe_von[k] for k in knoten if k in gruppe_von})
        for j in range(frei.shape[1]):
            text, ursache, bezug, t, w = _klartext(
                frei[:, j], mitten[i], laengen[i], koerper, "gleitet", sorted(fugen))
            aus.append(Singularitaet("gleitet", sorted(knoten), koerper, t, w, bezug,
                                     None, text, ursache, _abhilfe(fugen, knoten)))
            if len(aus) >= hoechstens:
                return aus
        if frei.shape[1]:
            continue                      # gleitet schon - der Kegel sagt nichts Neues
        # Stufe 1b: die Ungleichungen als das nehmen, was sie sind
        x = _im_kegel(_nullraum(gl), ug)
        if x is not None:
            text, ursache, bezug, t, w = _klartext(
                x, mitten[i], laengen[i], koerper, "hebt ab", sorted(fugen))
            aus.append(Singularitaet("hebt ab", sorted(knoten), koerper, t, w, bezug,
                                     None, text, ursache, _abhilfe(fugen, knoten)))
            if len(aus) >= hoechstens:
                return aus
    return aus


def _abhilfe(fugen, knoten) -> Optional[tuple]:
    """Wo man die Bewegung behebt: an der Fuge, sonst mit einem Lager."""
    if fugen:
        return ("kontakt", sorted(fugen)[0])
    return ("lager", min(knoten)) if knoten else None


def _gruppen_je_knoten(model) -> dict:
    """{Knoten: Name des Bauteils} aus der Elementgruppe."""
    aus = {}
    for e in model.elements:
        g = str(getattr(e, "group", "") or "")
        if not g:
            continue
        for k in e.nodes:
            aus.setdefault(int(k), g)
    return aus


# --------------------------------------------------------------------------
# Stufe 2
# --------------------------------------------------------------------------
def weichster_modus(K, model, frei=None, schritte: int = 20,
                    hoechstens: int = 1) -> list:
    """Stufe 2: der niedrigste Modus von K ueber inverse Iteration.

    Fuer Faelle ohne Starrkoerpermodus - weiche Mechanismen, Nullsteifigkeit,
    Splitterelemente. ``K + eps·I`` ist faktorisierbar, auch wenn K es nicht
    ist; die inverse Iteration konvergiert dann gegen den betragskleinsten
    Eigenvektor, und das ist die Bewegung, die fast keine Energie kostet.

    ``frei`` sind die Zeilen/Spalten, die nach dem Einbau der Lager bleiben
    (None = alle). Rueckgabe eine Liste von :class:`Singularitaet` mit
    ``feld`` als Knotenvektorfeld.
    """
    from scipy.sparse import identity
    from scipy.sparse.linalg import splu
    K = K.tocsc()
    n = K.shape[0]
    idx = np.arange(n) if frei is None else np.asarray(frei, int)
    Kf = K[idx][:, idx]
    if Kf.shape[0] == 0:
        return []
    diag = np.abs(Kf.diagonal())
    eps = 1e-10 * float(diag.max() if diag.size else 1.0)
    try:
        lu = splu((Kf + eps * identity(Kf.shape[0], format="csc")).tocsc())
    except Exception:                     # noqa: BLE001 - auch das darf nicht sperren
        return []
    rng = np.random.default_rng(0)
    v = rng.standard_normal(Kf.shape[0])
    v /= np.linalg.norm(v) or 1.0
    for _ in range(schritte):
        try:
            v = lu.solve(v)
        except Exception:                 # noqa: BLE001
            return []
        nv = np.linalg.norm(v)
        if not np.isfinite(nv) or nv <= 0:
            return []
        v = v / nv
    voll = np.zeros(n)
    voll[idx] = v
    feld = voll.reshape(-1, 6)[:, :3] if voll.size >= 6 * model.nn else None
    if feld is None or not feld.size:
        return []
    betrag = np.linalg.norm(feld, axis=1)
    gross = np.flatnonzero(betrag >= 0.5 * betrag.max()) if betrag.max() > 0 else []
    gruppe_von = _gruppen_je_knoten(model)
    koerper = sorted({gruppe_von[int(k)] for k in gross if int(k) in gruppe_von})
    wo = ", ".join(koerper[:3]) + (" …" if len(koerper) > 3 else "") or "Ein Bereich"
    s = Singularitaet(
        "numerisch", [int(k) for k in gross], koerper,
        feld[gross].mean(axis=0) if len(gross) else np.zeros(3), np.zeros(3),
        model.nodes[gross].mean(axis=0) if len(gross) else np.zeros(3), feld,
        f"{wo}: Bewegung fast ohne Steifigkeit",
        "Die Steifigkeitsmatrix ist hier nahezu singulär. Die gezeigte Bewegung "
        "kostet fast keine Energie - meist Splitterelemente oder ein Bauteil "
        "mit Nullsteifigkeit.",
        ("lager", int(gross[0])) if len(gross) else None)
    return [s][:hoechstens]
