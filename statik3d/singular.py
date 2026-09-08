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

Rechnen statt abbrechen
-----------------------

Ein Abbruch hilft niemandem: der Nutzer sieht keine Verformung und kann
darum nicht beurteilen, ob die freie Bewegung sein Ergebnis ueberhaupt
beruehrt. Darum wird gerechnet. Jede gefundene Bewegung bekommt **eine**
Zeile als Hilfsfesselung (:func:`hilfsfesselung`), die Steifigkeit dazu ist
k·v v^T.

Das faelscht nichts. Fuer eine Starrkoerperbewegung v eines ungehaltenen
Teils ist K·v = 0; die Zusatzsteifigkeit wirkt allein auf den
Starrkoerperanteil der Loesung, nicht auf Dehnungen und Spannungen. Der
Betrag von k geht darum auch nur in die Groesse dieses Anteils ein - und der
wird nach der Rechnung wieder abgezogen (:func:`bereinigen`).

Wie weit sich das Teil dabei verschiebt, sagt nichts aus - der Betrag haengt
allein an k. Was wirklich zaehlt, steht ohnehin schon in der Last
(:func:`auswerten`): die **unausgeglichene Last** in dieser Bewegung,

    Kraft = (Summe F) · t,     Moment = (Summe r x F) · omega

je Teil und Bewegung. Sie ist von k unabhaengig und braucht die Rechnung gar
nicht. Und sie entscheidet:

* **null** - die Last auf dem Teil steht in sich im Gleichgewicht. Spannungen
  und Verformungen sind richtig; unbestimmt ist nur die Lage des Teils im
  Raum. Ein Bauteil, an dem gar nichts angreift, faellt immer hierunter.
* **nicht null** - diese Kraft geht ins Nichts. Kein Lager, keine Fuge nimmt
  sie auf; im wirklichen Bauwerk wuerde sich das Teil bewegen. Die Rechnung
  liefert fuer dieses Teil nichts Brauchbares, und die Meldung sagt, welche
  Kraft an welchem Teil das ist. Der Nutzer entscheidet, ob er sie verwirft.

Was dieses Modul **nicht** tut
------------------------------

Es repariert nichts. Ob eine Fuge Reibung bekommt oder ein Bauteil ein Lager,
ist eine Modellierungsentscheidung. Die Hilfsfesselung ist kein Lager: sie
wird benannt, ausgewiesen und wieder herausgerechnet.

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

#: Hoechstzahl der Bewegungen, die **angezeigt** werden. Ein Modell mit 88
#: losen Teilen braucht keine 528 Meldungen, um verstanden zu werden -
#: :func:`wichtigste` waehlt die schwersten aus. Gesucht und gefesselt werden
#: dagegen immer alle: eine ungefesselte Bewegung liesse das System singulaer.
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
    bezug:   Punkt fuer die Darstellung: Schwerpunkt bzw. Punkt auf der Drehachse
    mitte:   Schwerpunkt des Teils - **darauf** beziehen sich t und omega
    feld:    Knotenvektorfeld (nn, 3) - nur bei art='numerisch'
    text:    „Achse (V30) kann laengs der Achse gleiten"
    ursache: „Kontaktbedingung 'Achse': in der Fugenebene nichts gehalten"
    abhilfe: ('kontakt', Name) | ('lager', Knoten) | None
    kraft:   Unausgeglichene Last in dieser Bewegung [N] - (Summe F)·t
    moment:  Unausgeglichenes Moment um ``mitte`` [Nm] - (Summe r x F)·omega.
             Sind beide nahe null, ist die Bewegung folgenlos: nur die Lage
             des Teils im Raum ist unbestimmt. Sonst geht genau diese Kraft
             ins Nichts, und fuer dieses Teil ist die Rechnung wertlos.
    gefesselt: Ohne eine Hilfsfesselung waere das System nicht loesbar gewesen
    laenge:  Bezugslaenge L des Teils (halbe Diagonale) - ``omega`` ist in 1/L
    fugen:   Namen der beteiligten Kontaktfugen
    kegel:   (N, B) der Kegelpruefung: zulaessig sind x = N·y mit B·y >= 0.
             Nur bei art='hebt ab' belegt; :func:`auswerten` sucht darin die
             Richtung, die die Last wirklich antreibt.
    """
    art: str = "gleitet"
    knoten: list = field(default_factory=list)
    koerper: list = field(default_factory=list)
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))
    omega: np.ndarray = field(default_factory=lambda: np.zeros(3))
    bezug: np.ndarray = field(default_factory=lambda: np.zeros(3))
    mitte: np.ndarray = field(default_factory=lambda: np.zeros(3))
    kraft: float = 0.0
    moment: float = 0.0
    gefesselt: bool = False
    laenge: float = 1.0
    fugen: list = field(default_factory=list)
    kegel: Optional[tuple] = None
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

    def befund(self) -> str:
        """Was die unausgeglichene Last fuer die Rechnung bedeutet."""
        if self.kraft <= 0.0 and self.moment <= 0.0:
            if self.art == "hebt ab":
                return ("Die Last drückt in die Fuge - das Bauteil bleibt liegen. "
                        "Gehalten ist es nur dadurch; fällt die Last weg oder kehrt "
                        "sie sich um, hebt es ab.")
            return ("Auf dem Teil steht die Last im Gleichgewicht - Spannungen und "
                    "Verformungen gelten, unbestimmt ist nur seine Lage im Raum.")
        teile = []
        if self.kraft > 0.0:
            teile.append(f"{self.kraft / 1000.0:.3g} kN")
        if self.moment > 0.0:
            teile.append(f"{self.moment / 1000.0:.3g} kNm")
        return (" und ".join(teile) + " gehen in dieser Bewegung ins Nichts - "
                "kein Lager und keine Fuge nimmt sie auf; für dieses Bauteil ist "
                "das Ergebnis nicht verwertbar.")


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
    dagegen nur als Ungleichung: es kann sich loesen. Wohin, sagt die
    Ausfallart - „Ausfall bei Zug" laesst den Knoten in die **positive**
    Achsrichtung los, „Ausfall bei Druck" in die negative. Ohne dieses
    Vorzeichen stuende ein einseitiges Lager mal als haltend, mal als offen
    da, je nachdem, wie die Achse zufaellig zeigt.
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
            aus = str(getattr(b, "failure", "") or "")
            if not aus:
                zeilen.append(a)
            else:
                ungleich.append(-a if aus == "druck" else a)
    for lager in list(getattr(model, "line_supports", None) or []) \
            + list(getattr(model, "surface_supports", None) or []):
        g, u = _flaechenlagerzeilen(model, lager, knoten, mitte, L)
        zeilen += g
        ungleich += u
    for cs in getattr(model, "contact_supports", None) or []:
        k = int(getattr(cs, "node", -1))
        if k not in knoten:
            continue
        d = np.asarray(getattr(cs, "direction", [0, 0, 1.0]), float)
        # Das Lager stuetzt in +d; in +d darf sich der Knoten loesen
        a = _zeile(model.nodes[k], d, mitte, L)
        if a is None:
            continue
        ungleich.append(a)
        if float(getattr(cs, "mu", 0.0)) > 0:
            from .contact import _tangent_basis
            for t in _tangent_basis(d / (np.linalg.norm(d) or 1.0)):
                zt = _zeile(model.nodes[k], t, mitte, L)
                if zt is not None:
                    zeilen.append(zt)
    return zeilen, ungleich


def _flaechenlagerzeilen(model, lager, knoten: set, mitte, L: float) -> tuple:
    """(Gleichungen, Ungleichungen) eines Linien- oder Flaechenlagers.

    Je Knoten und Richtung eine Zeile; ein Lager mit Ausfall zaehlt wie beim
    Knotenlager nur als Ungleichung in der Richtung, in der es loslaesst.
    """
    kn = [int(k) for k in (getattr(lager, "nodes", None) or []) if int(k) in knoten]
    if not kn:
        return [], []
    achsen = np.eye(3)
    gl, ug = [], []
    beh = getattr(lager, "behaviour", None) or {}
    for dof, b in beh.items():
        d = int(dof)
        if not getattr(b, "acts", False) or d >= 3:
            continue
        fehlt = str(getattr(b, "failure", "") or "")
        for k in kn:
            a = _zeile(model.nodes[k], achsen[d], mitte, L)
            if a is None:
                continue
            if not fehlt:
                gl.append(a)
            else:
                ug.append(-a if fehlt == "druck" else a)
    return gl, ug


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


def _im_kegel(N: np.ndarray, ungleich: list) -> tuple:
    """(Bewegung, B) im Kegel { N·y : a·(N·y) >= 0 } ausser der Null.

    Das Machbarkeits-LP hat hoechstens sechs Veraenderliche. Die Normierung
    Summe(a·N)·y >= 1 schliesst die Null aus und zugleich die Richtungen, die
    **jede** Ungleichung mit Gleichheit erfuellen - die sind schon der
    Nullraum aus Stufe 1a und stehen dort als „gleitet".

    Zurueck kommt neben der gefundenen Richtung die reduzierte Kegelmatrix
    B = [a_j · N]. Welche Richtung im Kegel die Last wirklich antreibt, laesst
    sich erst mit dem Lastvektor sagen (:func:`_getriebene_richtung`) - und
    dazu braucht es B. Ohne diese zweite Frage stuende jedes Bauteil, das auf
    seiner Unterlage liegt, als „hebt ab" da: **anheben** laesst es sich immer,
    nur zieht daran nichts.
    """
    if N.shape[1] == 0:
        return None, None
    if not ungleich:
        return N[:, 0], np.zeros((0, N.shape[1]))
    from scipy.optimize import linprog
    B = np.array([a @ N for a in ungleich])          # (m, k)
    if not np.any(np.abs(B) > 1e-12):
        return None, B
    # -B·y <= 0 und -(Summe B)·y <= -1
    A_ub = np.vstack([-B, -B.sum(axis=0)[None, :]])
    b_ub = np.concatenate([np.zeros(len(B)), [-1.0]])
    k = N.shape[1]
    r = linprog(np.zeros(k), A_ub=A_ub, b_ub=b_ub,
                bounds=[(-1e6, 1e6)] * k, method="highs")
    if not getattr(r, "success", False) or r.x is None:
        return None, B
    x = N @ np.asarray(r.x, float)
    nx = float(np.linalg.norm(x))
    return (x / nx if nx > 1e-12 else None), B


def _getriebene_richtung(kegel: tuple, g: np.ndarray):
    """Die Richtung im Kegel, die die Last am staerksten antreibt - oder None.

    Gesucht ist

        max  g·x   ueber  x = N·y,  B·y >= 0,  |x| <= 1

    Ist das Maximum null, drueckt die Last in **jede** zulaessige Richtung
    hinein: die Fugen halten, das Teil bleibt liegen, und die Bewegung ist
    kinematisch moeglich, aber unbelastet. Nur ein positives Maximum heisst,
    dass wirklich etwas ins Nichts geht - und x ist dann die Richtung, in die
    sich das Teil in Bewegung setzt.

    Geloest wird das nicht als LP, sondern als **Projektion auf den Kegel**.
    Mit N orthonormal ist |x| = |y|, und nach Moreau zerfaellt g in den Anteil
    im Kegel und den im Polarkegel:

        g = P_K(g) + P_K°(g),   K° = { -B^T mu : mu >= 0 }

    Das Maximum ist |P_K(g)| und wird bei y = P_K(g)/|P_K(g)| angenommen.
    P_K° ist eine nichtnegative Ausgleichsrechnung (``nnls``) mit hoechstens
    sechs Zeilen - sie bricht nach hoechstens sechs Schritten ab, gleichgueltig
    wie viele Ungleichungen der Kegel hat.

    Ein lineares Programm mit Kasten |y| <= 1 taete es hier nicht: es zieht
    die Richtung in die Ecken des Kastens und meldete fuer einen Wuerfel, an
    dem 100 kN ziehen, nur 82 kN.
    """
    if not kegel:
        return None
    N, B = kegel
    if N is None or N.shape[1] == 0:
        return None
    gt = np.asarray(N, float).T @ np.asarray(g, float)
    grenze = 1e-9 * (float(np.linalg.norm(gt)) or 1.0)
    if B is None or not len(B):
        p = gt
    else:
        from scipy.optimize import nnls
        A = -np.asarray(B, float).T
        try:
            mu, _rest = nnls(A, gt)
        except Exception:                 # noqa: BLE001 - lieber keine Aussage
            return None
        p = gt - A @ mu
    lp = float(np.linalg.norm(p))
    if lp <= grenze:
        return None                       # die Last haelt dagegen
    x = np.asarray(N, float) @ (p / lp)
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


def restfreiheiten(model, hoechstens: int = 0) -> list:
    """Stufe 1a und 1b: was sich bewegen kann, bevor gerechnet wird.

    Rueckgabe eine Liste von :class:`Singularitaet`. Kostet eine
    6x6-Eigenwertaufgabe und ein kleines LP je Teiltragwerk.

    ``hoechstens = 0`` (Vorgabe) heisst: alle. Fuer die Hilfsfesselung muss
    das so sein - was nicht gefesselt wird, macht die Matrix weiter singulaer.
    Fuer die **Anzeige** waehlt :func:`wichtigste` daraus aus.
    """
    hoechstens = hoechstens or 10 ** 9
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
        gemein = dict(knoten=sorted(knoten), koerper=koerper,
                      mitte=np.asarray(mitten[i], float), laenge=laengen[i],
                      fugen=sorted(fugen), abhilfe=_abhilfe(fugen, knoten))
        for j in range(frei.shape[1]):
            text, ursache, bezug, t, w = _klartext(
                frei[:, j], mitten[i], laengen[i], koerper, "gleitet", sorted(fugen))
            aus.append(Singularitaet(art="gleitet", t=t, omega=w, bezug=bezug,
                                     text=text, ursache=ursache, **gemein))
            if len(aus) >= hoechstens:
                return aus
        if frei.shape[1]:
            continue                      # gleitet schon - der Kegel sagt nichts Neues
        # Stufe 1b: die Ungleichungen als das nehmen, was sie sind
        N = _nullraum(gl)
        x, B = _im_kegel(N, ug)
        if x is not None:
            text, ursache, bezug, t, w = _klartext(
                x, mitten[i], laengen[i], koerper, "hebt ab", sorted(fugen))
            aus.append(Singularitaet(art="hebt ab", t=t, omega=w, bezug=bezug,
                                     text=text, ursache=ursache, kegel=(N, B),
                                     **gemein))
            if len(aus) >= hoechstens:
                return aus
    return aus


def wichtigste(sing: list, hoechstens: int = HOECHSTENS) -> list:
    """Die schwerwiegendsten Bewegungen zuerst, hoechstens ``hoechstens``.

    Reihenfolge: erst, wo wirklich Last ins Nichts geht (die groesste zuerst),
    dann die folgenlosen. So steht bei 88 losen Teilen oben, was die Rechnung
    zunichte macht, und nicht das erstbeste Teil nach Knotennummer.
    """
    return sorted(sing, key=lambda x: -(abs(x.kraft) + abs(x.moment)))[:hoechstens]


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
                    hoechstens: int = 1, melden=None) -> list:
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
    K = K.tocsc()
    n = K.shape[0]
    idx = np.arange(n) if frei is None else np.asarray(frei, int)
    Kf = K[idx][:, idx]
    if Kf.shape[0] == 0:
        return []
    diag = np.abs(Kf.diagonal())
    eps = 1e-10 * float(diag.max() if diag.size else 1.0)
    # Bewusst ueber LinearSolver, nicht ueber splu: dies ist eine **zweite**
    # volle Faktorisierung, und sie laeuft im Fehlerpfad - also gerade dann,
    # wenn der Anwender ohnehin schon wartet. Mit splu lief sie einkernig; an
    # einem Modell mit 237.198 Freiheitsgraden hat das den Fortschritt neun
    # Minuten lang bei 20 % stehen lassen, ohne ein Wort dazu.
    from .solver import LinearSolver
    try:
        lu = LinearSolver((Kf + eps * identity(Kf.shape[0], format="csc")).tocsc())
    except Exception:                     # noqa: BLE001 - auch das darf nicht sperren
        return []
    if melden:
        melden(f"Diagnose: weichster Modus ueber {lu.beschreibung()} "
               f"({Kf.shape[0]} Freiheitsgrade, {schritte} Schritte)")
    rng = np.random.default_rng(0)
    v = rng.standard_normal(Kf.shape[0])
    v /= np.linalg.norm(v) or 1.0
    for _ in range(schritte):
        try:
            # **Ohne** Residuumspruefung. K + eps*I ist hier mit Absicht fast
            # singulaer - das ist der Sinn der inversen Iteration. Die Pruefung
            # des Loesers schlug darum genau in den Faellen zu, fuer die diese
            # Diagnose ueberhaupt da ist: an zwei Wuerfeln mit einem
            # gemeinsamen Knoten stieg sie im ersten Schritt mit
            # "Residuum 2.3e-06" aus, und Stufe 2 lieferte nie einen Befund.
            v = lu.solve(v, check=False)
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
    schwer = (model.nodes[gross].mean(axis=0) if len(gross) else np.zeros(3))
    s = Singularitaet(
        art="numerisch", knoten=[int(k) for k in gross], koerper=koerper,
        t=(feld[gross].mean(axis=0) if len(gross) else np.zeros(3)),
        bezug=schwer, mitte=schwer, feld=feld,
        text=f"{wo}: Bewegung fast ohne Steifigkeit",
        ursache="Die Steifigkeitsmatrix ist hier nahezu singulär. Die gezeigte "
                "Bewegung kostet fast keine Energie - meist Splitterelemente oder "
                "ein Bauteil mit Nullsteifigkeit.",
        abhilfe=("lager", int(gross[0])) if len(gross) else None)
    return [s][:hoechstens]


# --------------------------------------------------------------------------
# Rechnen statt abbrechen
# --------------------------------------------------------------------------
def modenfeld(model, s: Singularitaet) -> np.ndarray:
    """Die Bewegung als Knotenverschiebung (len(s.knoten), 3).

    u(p) = t + omega x (p - Mitte), unnormiert: den Massstab setzt erst
    :func:`_orthonormieren`, und der muss den Drehanteil (der auf den
    Verdrehungs-FHG steht) mit erfassen - eine Normierung allein ueber die
    Verschiebungen brachte beides auseinander.
    """
    if s.feld is not None:
        return np.asarray(s.feld, float)[np.asarray(s.knoten, int)]
    kn = np.asarray(s.knoten, int)
    if not len(kn):
        return np.zeros((0, 3))
    r = model.nodes[kn] - np.asarray(s.mitte, float)
    return np.asarray(s.t, float)[None, :] + np.cross(
        np.broadcast_to(np.asarray(s.omega, float), r.shape), r)


def _orthonormieren(V, sing: list):
    """Zeilen von ``V`` orthonormieren (modifiziertes Gram-Schmidt, duenn besetzt).

    Erst damit ist die Auswertung eindeutig: bei orthonormalen Zeilen ist
    ``a = V u`` **der** Anteil der Bewegung i an der Loesung, und die
    Hilfskraft k·a_i·v_i gehoert genau zu ihr. Ohne die Orthonormierung
    zaehlten sich ueberlappende Moden gegenseitig mit.

    Die Zeilen sind schon fast orthogonal - Verschiebungen und Drehungen um
    den Schwerpunkt stehen aufeinander senkrecht, verschiedene Teile
    beruehren verschiedene Knoten. Die Korrektur ist also klein und macht aus
    einer benannten Bewegung keine andere. Eine Zeile, die dabei verschwindet,
    war eine Wiederholung; sie faellt mitsamt ihrer Bewegung weg.

    Rueckgabe (V_orth, sing_orth).
    """
    from scipy import sparse
    zeilen, behalten = [], []
    for i in range(V.shape[0]):
        r = V.getrow(i).astype(float)
        vorher = float(np.sqrt(r.multiply(r).sum()))
        for q in zeilen:
            c = float(q.multiply(r).sum())
            if c:
                r = r - c * q
        nr = float(np.sqrt(r.multiply(r).sum()))
        # Gemessen am eigenen Betrag, nicht an einer festen Schranke: sonst
        # entschiede die Laengeneinheit darueber, was als Wiederholung gilt.
        if nr <= 1e-8 * (vorher or 1.0):
            continue
        zeilen.append((r / nr).tocsr())
        behalten.append(i)
    if not zeilen:
        return sparse.csr_matrix((0, V.shape[1])), []
    return sparse.vstack(zeilen, format="csr"), [sing[i] for i in behalten]


def hilfsfesselung(model, sing: list, frei=None):
    """Zu jeder freien Bewegung eine Zeile ueber die Freiheitsgrade des Teils.

    Statt abzubrechen wird jede gefundene Bewegung mit **einer** Zeile
    festgehalten: der Starrkoerpermodus selbst, als Vektor ueber die
    Freiheitsgrade. Das ist der kleinstmoegliche Eingriff - ein
    Freiheitsgrad je Bewegung, sonst bleibt das Modell unveraendert.

    Und er faelscht nichts: fuer eine Starrkoerperbewegung v eines nicht
    gehaltenen Teils ist K·v = 0. Die Zusatzsteifigkeit k·v v^T wirkt darum
    nur auf den Starrkoerperanteil; die Spannungen und Dehnungen bleiben, was
    sie waeren. Was sich aendert, ist nur der Betrag der Starrkoerper-
    verschiebung - und der ist ohnehin willkuerlich und wird nach der
    Rechnung wieder herausgenommen (:func:`bereinigen`).

    **Die Verdrehungen gehoeren dazu.** Bei einem Stab ist die
    Starrkoerperdrehung erst dann eine, wenn sich die Knoten mitdrehen: die
    Zeile traegt an jedem Knoten omega auf den Verdrehungs-FHG. Ohne das
    waere die Zeile keine Nullmode von K (sie waere eine Biegung), und die
    Drehung um die **eigene** Stabachse - bei der sich kein Knoten
    verschiebt - haette ueberhaupt keine Zeile: das System bliebe singulaer.

    ``frei``: die Freiheitsgrade, die das Gleichungssystem wirklich fuehrt
    (None = alle). Bei Volumenknoten sind die Verdrehungen gesperrt, weil sie
    keine Steifigkeit haben; ihre Eintraege gehoeren dann auch nicht in die
    Zeile - sonst stimmte die Projektion in :func:`bereinigen` nicht mehr.

    Rueckgabe (V, sing) - eine duenn besetzte (m, ndof)-Matrix mit
    orthonormalen Zeilen und die Bewegungen dazu.
    """
    from scipy import sparse
    zeilen, spalten, werte, dabei = [], [], [], []
    for sg in sing:
        u = modenfeld(model, sg)
        kn = np.asarray(sg.knoten, int)
        w = np.asarray(sg.omega, float)
        if not len(kn) or not (np.any(np.abs(u) > 0) or np.any(np.abs(w) > 0)):
            continue
        dabei.append(sg)
        j0 = len(dabei) - 1
        for j in range(3):
            spalten.append(6 * kn + j)
            werte.append(u[:, j])
            zeilen.append(np.full(len(kn), j0))
            if w[j]:
                spalten.append(6 * kn + 3 + j)
                werte.append(np.full(len(kn), float(w[j])))
                zeilen.append(np.full(len(kn), j0))
    if not zeilen:
        return sparse.csr_matrix((0, model.ndof)), []
    V = sparse.csr_matrix(
        (np.concatenate(werte), (np.concatenate(zeilen), np.concatenate(spalten))),
        shape=(len(dabei), model.ndof))
    if frei is not None:
        maske = np.zeros(model.ndof)
        maske[np.asarray(frei, int)] = 1.0
        V = V.multiply(maske[None, :]).tocsr()
    return _orthonormieren(V, dabei)


def stabilisieren(K, V, faktor: float = 1e-6):
    """K + k·V^T V - die Hilfsfesselungen als Straffedern.

    ``k`` bemisst sich an der Hauptdiagonalen von K. Der Betrag ist
    unkritisch: weil K·v = 0 ist, geht k **nur** in den Starrkoerperanteil
    ein, nicht in die Spannungen. Gewaehlt ist er klein genug, dass die
    Kondition der Matrix nicht leidet, und gross genug, dass die
    Faktorisierung die Bewegung als gehalten sieht. Rueckgabe (K_stabil, k).

    **Nicht mehr im Rechenweg.** ``V^T V`` ist ein aeusseres Produkt: es hat so
    viele Eintraege, wie die Zeile Nichtnullen im Quadrat hat, und die Zeile
    einer freien Bewegung besetzt **alle** Freiheitsgrade ihres Teils. Am
    Wuerfelpaar gemessen waechst es genau quadratisch - 675 freie FHG:
    138.625 Eintraege (1,7 MB); 4.131 freie FHG: 4.756.725 (57,1 MB). Am
    Drehlagermodell schwebt ein Teil ueber 262.335 Freiheitsgraden: 6,9e10
    Eintraege, rund 826 GB. Der Lauf hat 44 Minuten gerechnet, 287,5 GB
    zugesichert und den Rechner zum Stillstand gebracht.

    Der Loeser haelt die Bewegungen darum ueber einen **Lagrange-Rand**
    (:meth:`StaticSystem.hilfsfesselung`): das ist dieselbe Bedingung, exakt
    statt als Straffeder, und kostet nur zwei Eintraege je Nichtnull von V.
    Diese Funktion bleibt fuer kleine Systeme und fuer den Vergleich in den
    Tests stehen.
    """
    from scipy import sparse
    if V.shape[0] == 0:
        return K, 0.0
    d = np.abs(np.asarray(K.diagonal()).ravel())
    k = float(faktor * (d.max() if d.size and d.max() > 0 else 1.0))
    return (K + k * (V.T @ V)).tocsr() if sparse.issparse(K) else K + k * (V.T @ V), k


def auswerten(model, sing: list, F: np.ndarray) -> list:
    """Die unausgeglichene Last je freier Bewegung nachtragen.

    Fuer eine Starrkoerperbewegung u(p) = t + omega x (p - c) ist die
    zugehoerige verallgemeinerte Kraft

        Q = t · Summe(F_k)  +  omega · Summe((p_k - c) x F_k)

    ueber die Knoten des Teils. Sie ist genau das, was keine Halterung
    aufnimmt: waere Q ungleich null und das Teil frei, kaeme es nie zur Ruhe.

    Der grosse Vorteil gegenueber jedem Wert aus der geloesten Rechnung: Q
    haengt nicht an der Steifigkeit der Hilfsfesselung. Er steht schon im
    Lastvektor - die Rechnung muss dafuer gar nicht laufen.

    **gleitet** - beide Richtungen sind frei, es zaehlt der Betrag.
    **hebt ab** - nur eine Richtung ist frei. Hier wird im Kegel die Richtung
    gesucht, die die Last am staerksten antreibt; findet sich keine, drueckt
    die Last in die Fuge und das Teil bleibt liegen. Ohne diesen Schritt
    stuende jedes Bauteil unter Eigengewicht als abhebend da.

    Knotenmomente zaehlen beim Drehanteil mit; Strecken- und Volumenlasten
    stehen im Lastvektor bereits als Knotenkraefte.
    """
    if F is None or not sing:
        return sing
    F = np.asarray(F, float).ravel()
    n6 = model.nn * 6
    K = F[:n6].reshape(-1, 6)
    kraefte, momente = K[:, :3], K[:, 3:]
    for sg in sing:
        kn = np.asarray(sg.knoten, int)
        sg.kraft = sg.moment = 0.0
        if not len(kn):
            continue
        Rf = kraefte[kn].sum(axis=0)
        Rm = (momente[kn].sum(axis=0)
              + np.cross(model.nodes[kn] - np.asarray(sg.mitte, float),
                         kraefte[kn]).sum(axis=0))
        if sg.art == "hebt ab":
            # x = [t, L·omega]; dazu passt g = [Summe F, Summe(r x F)/L]
            x = _getriebene_richtung(sg.kegel,
                                     np.concatenate([Rf, Rm / sg.laenge]))
            if x is None:
                sg.ursache = ("Die Bewegung ist kinematisch möglich, aber die Last "
                              "drückt in die Fuge - das Bauteil bleibt liegen. Ohne "
                              "Last in dieser Richtung hält es nichts.")
                continue
            text, ursache, bezug, t, w = _klartext(
                x, sg.mitte, sg.laenge, sg.koerper, "hebt ab", sg.fugen)
            sg.t, sg.omega, sg.bezug = t, w, bezug
            sg.text, sg.ursache = text, ursache
        t, w = np.asarray(sg.t, float), np.asarray(sg.omega, float)
        nt, nw = float(np.linalg.norm(t)), float(np.linalg.norm(w))
        sg.kraft = abs(float(Rf @ (t / nt))) if nt > 0 else 0.0
        sg.moment = abs(float(Rm @ (w / nw))) if nw > 0 else 0.0
    return sing


def bereinigen(V, u: np.ndarray) -> np.ndarray:
    """Den willkuerlichen Starrkoerperanteil aus ``u`` herausnehmen.

    Er kommt allein aus der Steifigkeit k der Hilfsfesselung und sagt nichts
    ueber das Tragwerk. Uebrig bleibt die Verformung, die das Teil wirklich
    erfaehrt; die Bewegung selbst steht daneben in der Liste.
    """
    if V is None or V.shape[0] == 0 or u is None:
        return u
    u = np.asarray(u, float).ravel()
    return u - np.asarray(V.T @ (V @ u), float).ravel()
