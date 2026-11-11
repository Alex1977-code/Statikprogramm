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

from dataclasses import MISSING, dataclass, field, fields
from typing import Optional

import numpy as np

#: Eigenwerte unter diesem Anteil des groessten gelten als null (Stufe 1a).
NULLRAUM = 1e-6

#: Freiheitsgrade je Knoten (wie model.NDOF)
NDOF = 6

#: Hoechstzahl der Bewegungen, die **angezeigt** werden. Ein Modell mit 88
#: losen Teilen braucht keine 528 Meldungen, um verstanden zu werden -
#: :func:`wichtigste` waehlt die schwersten aus. Gesucht und gefesselt werden
#: dagegen immer alle: eine ungefesselte Bewegung liesse das System singulaer.
HOECHSTENS = 40

#: Kleinster Anteil, ab dem ein Drehanteil als Drehung gilt (sonst reine
#: Verschiebung). Bezogen auf |L·omega| gegen |t|.
DREH_ANTEIL = 1e-6


class MatrixdiagnoseUnmoeglich(Exception):
    """Stufe 2 konnte nicht rechnen: die Faktorisierung von K + eps·I oder ein
    Schritt der inversen Iteration ist gescheitert. Der Text nennt den Grund.

    **Keine leere Liste**: die hiesse „kein auffaellig weicher Modus", und
    genau das schloss diagnose.singulaer_text bis zum 23.09.2026 daraus -
    ueber eine Rechnung, die nie lief (gemessen am Wuerfelpaar aus
    tests/test_singular.py: Hauptfaktorisierung ueber PARDISO, in der
    Diagnose PARDISO und SuperLU verweigert - Meldung „… keinen auffaellig
    weichen Modus"; ebenso bei einer Ausnahme oder NaN in der Iteration).
    Bewusst keine RuntimeError, wie solver.LoeserAusfall: ein RuntimeError
    wird als singulaere Matrix gedeutet.
    """


@dataclass
class Halteguete:
    """Wie fest ein Teiltragwerk gehalten wird - nicht nur **ob**.

    wert:      lambda_min / lambda_max der 6x6-Haltematrix, 1 = allseitig
               gleich fest, 1e-5 = in einer Richtung fast nichts
    richtung:  der Eigenvektor zu lambda_min (6,) - erst Verschiebung, dann
               Verdrehung mal Bezugslaenge
    koerper:   Namen der Bauteile des Teils
    knoten:    seine Knoten
    mitte:     Schwerpunkt, auf den sich ``richtung`` bezieht
    laenge:    Bezugslaenge L
    text:      fertige Meldung
    """
    wert: float = 0.0
    richtung: np.ndarray = field(default_factory=lambda: np.zeros(6))
    koerper: list = field(default_factory=list)
    knoten: list = field(default_factory=list)
    mitte: np.ndarray = field(default_factory=lambda: np.zeros(3))
    laenge: float = 1.0
    text: str = ""


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
    #: Das Element, das die Bewegung traegt (-1 = keines) - nur bei
    #: art='numerisch'. Zu jedem Fehler gehoert das Element, nicht nur das
    #: Bauteil.
    element: int = -1
    #: Ausschlag a_e = max |u| ueber die Knoten dieses Elements
    ausschlag: float = 0.0
    #: Energie E_e = u_e^T K_e u_e [Nm] - grosser Ausschlag bei fast keiner
    #: Energie **ist** die Diagnose
    energie: float = 0.0
    #: dieselbe Energie dimensionslos: E_e / (a_e^2 * mittlere Diagonale K_e)
    anteil: float = 0.0
    #: Nur bei art='numerisch': warum die Diagnose-Faktorisierung auf einen
    #: anderen Loeser ausgewichen ist (LinearSolver.ausweichgrund) - leer,
    #: wenn nicht. Bis zum 23.09.2026 stand das nur im Fortschritt (wenn es
    #: einen gab) und in warnings.warn, das weder Protokollfenster noch exe
    #: erreicht; die Meldung ohne Fortschritt nannte es nicht.
    ausweichgrund: str = ""
    #: Nur bei einer Gelenkkette (Befund C8, 09.11.2026): die Stabendgelenke,
    #: die sich in der Bewegung oeffnen, als (Element, Knoten, lokaler FHG 0..5,
    #: Oeffnung bezogen auf den groessten Ausschlag) - leer, wenn keine.
    gelenke: list = field(default_factory=list)
    #: v^T K v / v^T diag(K) v der Bewegung - nahe null heisst Mechanismus
    bezogene_energie: float = 0.0

    def __setstate__(self, state):
        """Ergebnisdateien von vor dem 10.11.2026 kennen ``gelenke`` und
        ``bezogene_energie`` (Befund C8) nicht; Pickle setzt nur das
        Gespeicherte. Fehlende Felder bekommen ihren Vorgabewert, sonst brach
        jeder Zugriff darauf mit AttributeError ab (Nachkontrolle 11.11.2026)."""
        self.__dict__.update(state)
        for f in fields(self):
            if f.name in state:
                continue
            if f.default is not MISSING:
                setattr(self, f.name, f.default)
            elif f.default_factory is not MISSING:
                setattr(self, f.name, f.default_factory())

    def verschiebung(self) -> bool:
        """Reine Verschiebung (kein nennenswerter Drehanteil)?"""
        return float(np.linalg.norm(self.omega)) <= DREH_ANTEIL

    def bezeichnung(self) -> str:
        """Kurzform fuer den Modellbaum."""
        wo = ", ".join(self.koerper[:3]) + (" …" if len(self.koerper) > 3 else "")
        return f"{wo or 'Teil'} - {self.text}" if self.text else (wo or "Teil")

    def befund(self) -> str:
        """Was die unausgeglichene Last fuer die Rechnung bedeutet."""
        if self.art == "starr":
            # Starrkoerperbewegung im Ergebnis (17.10.2026)
            return ("Der Körper bewegt sich als Ganzes, ohne nennenswerte Verformung – er ist in dieser "
                    "Richtung nicht gehalten. Abhilfe: Reibbeiwert in der Fuge setzen, Federkonstante > 0 "
                    "oder seitliche Halterung.")
        if self.kraft <= 0.0 and self.moment <= 0.0:
            if self.art == "hebt ab":
                return ("Die Last drückt in die Fuge - das Bauteil bleibt liegen. "
                        "Gehalten ist es nur dadurch; fällt die Last weg oder kehrt "
                        "sie sich um, hebt es ab.")
            return ("Auf dem Teil steht die Last im Gleichgewicht - Spannungen und "
                    "Verformungen gelten, unbestimmt ist nur seine Lage im Raum.")
        teile = []
        if self.kraft > 0.0:
            teile.append(f"{_zahl(self.kraft / 1000.0)} kN")
        if self.moment > 0.0:
            teile.append(f"{_zahl(self.moment / 1000.0)} kNm")
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


def _kontaktzeilen(model, teil_von: dict, mitten: dict, laengen: dict,
                   reibung_annehmen: bool = False) -> dict:
    """Zeilen aus Kontaktpaaren und Spaltelementen, je Teiltragwerk.

    Rueckgabe {Teil: (Gleichungen, Ungleichungen, Namen der Fugen)}. Eine
    Kontaktnormale ist eine **Ungleichung** - die Fuge kann aufgehen. Haelt
    die Fuge in ihrer Ebene (haftend oder mit Reibbeiwert), kommen die beiden
    Tangenten als Gleichungen dazu.

    Die Paarung Slave-Knoten gegen Master-Facette wird hier neu gesucht statt
    aus dem Loeser uebernommen: die Vorabpruefung laeuft, **bevor** es ein
    Kontaktsystem gibt. Die Regel ist aber die des Loesers: ein Knoten
    bekommt eine Zeile nur gegen eine Facette, auf die er senkrecht faellt
    (Querversatz hoechstens ``DECKUNGSGLEICH`` mal Modellgroesse plus
    ``KANTENKEGEL`` mal Abstand laengs der Normalen), und unter diesen gegen
    die raeumlich naechste. Die Richtung ist die Normale der Facette, nicht
    die der wahren Flaeche; fuer eine Richtungsfrage genuegt das, der
    Hebelarm aendert sich hoechstens um eine Facettengroesse.

    ``reibung_annehmen`` (17.10.2026, :func:`kontakt_gehalten`): jede Fuge haelt
    so, als haette sie einen Reibbeiwert - die Frage, ob Reibung einen Koerper
    halten wuerde.
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

    from .contact import naechste_punkte_dreiecke, DECKUNGSGLEICH, KANTENKEGEL
    groesse = float(model.characteristic_size())
    for cp in getattr(model, "contact_pairs", None) or []:
        E, S, N, KN = _dreiecke(model, cp)
        if not len(S):
            continue
        haelt = (bool(getattr(cp, "haften", False)) or float(getattr(cp, "mu", 0.0)) > 0
                 or reibung_annehmen)
        verbund = bool(getattr(cp, "zug", False))
        radius = float(getattr(cp, "search_radius", 0.0) or 0.0) or 0.1 * groesse
        spalt = float(getattr(cp, "gap", 0.0) or 0.0)
        # Was weiter weg liegt als der Suchradius oder wo die Fuge offen
        # steht, haelt **nichts** - auch nicht gegen Druck. Ein Bauteil, das
        # ueber seiner Unterlage schwebt, ist frei und nicht etwa gelagert.
        offen = 1e-9 * groesse
        baum = cKDTree(S)
        # Gesucht wird wie im Loeser ueber **alle** Facetten in Reichweite:
        # steht ein Knoten im Suchradius auf einem Dreieck, liegt dessen
        # Schwerpunkt hoechstens Radius + Umkreis entfernt. Die paar naechsten
        # Schwerpunkte genuegen nicht mehr, seit nur zaehlt, worauf der Knoten
        # steht - neben einem fein vernetzten Streifen gehoeren sie alle dem
        # Streifen, und der Knoten fiele neben seiner eigenen Auflage heraus
        # (tests.test_singular, test_neben_der_gegenflaeche_haelt_nichts).
        umkreis = np.sqrt(((E - S[:, None, :]) ** 2).sum(2).max(1))
        weit = radius + float(umkreis.max())
        for sk in (cp.slave_nodes or []):
            k = int(sk)
            teil = teil_von.get(k)
            if teil is None:
                continue
            p = model.nodes[k]
            kand = np.asarray(baum.query_ball_point(p, weit), dtype=int)
            if kand.size:
                kand = kand[np.linalg.norm(S[kand] - p, axis=1) <= radius + umkreis[kand]]
            if not kand.size:
                continue                      # ausser Reichweite
            q, _w = naechste_punkte_dreiecke(p, E[kand, 0], E[kand, 1], E[kand, 2])
            # Halt gibt nur eine Facette, auf die der Knoten senkrecht faellt -
            # dieselbe Regel wie in contact.ContactSystem._build_pair, mit
            # derselben Rundung und demselben Kegel einer glatten Kante. Neben
            # der Gegenflaeche bekommt der Knoten dort keine Bedingung; zaehlte
            # er hier, stuende ein Teil als gehalten da, das im Loeser frei ist.
            weg = q - p
            laengs = np.einsum("ij,ij->i", weg, N[kand])
            quer = np.linalg.norm(weg - laengs[:, None] * N[kand], axis=1)
            dist = np.abs(laengs)
            auf = np.flatnonzero(quer <= DECKUNGSGLEICH * groesse + KANTENKEGEL * dist)
            if not auf.size:
                continue                      # neben der Gegenflaeche
            j = int(auf[np.argmin(np.linalg.norm(weg[auf], axis=1))])
            if dist[j] > radius:
                continue                      # ausser Reichweite, laengs der Normalen
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
            if float(getattr(g, "mu", 0.0)) > 0 or reibung_annehmen:
                for t in _tangent_basis(np.asarray(d, float)):
                    dazu(teil, _zeile(model.nodes[k], t, mitten[teil],
                                      laengen[teil]), "=", name)
    return aus


# --------------------------------------------------------------------------
# Stufe 1a und 1b
# --------------------------------------------------------------------------
#: Unter dieser Haltegüte wird gewarnt: das Teil ist zwar in allen sechs
#: Richtungen angefasst, in einer davon aber zehntausendmal weicher als in der
#: steifsten. Genau das trennt zwei aeusserlich gleiche Bauteile voneinander.
HALTEGUETE_MIN = 1e-4


def _nullraum(zeilen: list, spektrum: list = None) -> np.ndarray:
    """Nullraum der Zeilen als (6, k) - Bewegungen, die keine Zeile dehnt.

    ``spektrum`` nimmt, wenn angegeben, das Paar (Eigenwerte, Eigenvektoren)
    der Haltematrix A = Summe(a a^T) entgegen. Aus ihm kommt die
    **Haltegüte** (:func:`halteguete_von`): der Rang allein sagt nur, ob eine
    Richtung angefasst wird, nicht wie fest.
    """
    if not zeilen:
        if spektrum is not None:
            spektrum.append((np.zeros(6), np.eye(6)))
        return np.eye(6)
    A = np.zeros((6, 6))
    for a in zeilen:
        A += np.outer(a, a)
    w, V = np.linalg.eigh(A)
    if spektrum is not None:
        spektrum.append((w, V))
    grenze = NULLRAUM * max(float(w.max()), 1e-300)
    return V[:, w <= grenze]


def halteguete_von(w: np.ndarray) -> float:
    """lambda_min / lambda_max der Haltematrix - 1 heisst allseitig gleich fest.

    Die Zeilen sind auf Eins normiert, die Verdrehungsanteile mit der
    Bezugslaenge des Teils skaliert; die Eigenwerte sind damit dimensionslos
    und vergleichbar. Der Kehrwert ist die Konditionszahl der Haltematrix -
    und das ist die Zahl, die den Unterschied zwischen zwei aeusserlich
    gleichen Bauteilen sichtbar macht, **vor** dem Loesen.
    """
    w = np.asarray(w, float)
    if not w.size:
        return 0.0
    gross = float(w.max())
    return float(w.min()) / gross if gross > 0 else 0.0


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
        wie = f"Verschiebung längs {_vektor_text(richtung)}"
        bezug = np.asarray(mitte, float)
    else:
        e = w / np.linalg.norm(w)
        bezug = np.asarray(mitte, float) + np.cross(w, t) / float(w @ w)
        laengs = float(t @ e)
        wie = (f"Drehung um {_vektor_text(e)}"
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
                   # bis 08.11.2026 „hat weder Lager noch …“ - falsch, wenn Lager die
                   # Bewegung zulassen (Platte an einem Linienlager ohne Verdrehung)
                   "Kein Lager und keine Kopplung an ein gelagertes Teil hält diese Bewegung: "
                   "das Bauteil ist nicht gelagert, oder seine Lager lassen sie zu (etwa ein "
                   "Linienlager ohne Verdrehung – ein Gelenk um die Linie).")
    return text, ursache, bezug, t, w


def restfreiheiten(model, hoechstens: int = 0, guete: list = None) -> list:
    """Stufe 1a und 1b: was sich bewegen kann, bevor gerechnet wird.

    Rueckgabe eine Liste von :class:`Singularitaet`. Kostet eine
    6x6-Eigenwertaufgabe und ein kleines LP je Teiltragwerk.

    ``hoechstens = 0`` (Vorgabe) heisst: alle. Fuer die Hilfsfesselung muss
    das so sein - was nicht gefesselt wird, macht die Matrix weiter singulaer.
    Fuer die **Anzeige** waehlt :func:`wichtigste` daraus aus.

    ``guete`` nimmt, wenn angegeben, je Teiltragwerk eine :class:`Halteguete`
    entgegen - auch fuer die Teile, die **gehalten** sind und darum keine
    Singularitaet ergeben. Genau dort steckt die Auskunft: ein Teil kann in
    allen sechs Richtungen angefasst und in einer davon trotzdem
    zehntausendmal weicher sein als in der steifsten. Der Rang sieht das
    nicht, die Eigenwerte schon - und sie liegen hier ohnehin vor.
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
        spek: list = []
        frei = _nullraum(gl + ug, spek)
        koerper = sorted({gruppe_von[k] for k in knoten if k in gruppe_von})
        if guete is not None and spek and not frei.shape[1]:
            # Nur fuer die gehaltenen Teile: wo eine Bewegung frei ist, steht
            # sie schon als Singularitaet da, und lambda_min waere die Null.
            w, V = spek[-1]
            guete.append(Halteguete(
                wert=halteguete_von(w), richtung=np.asarray(V[:, 0], float),
                koerper=koerper, knoten=sorted(knoten),
                mitte=np.asarray(mitten[i], float), laenge=laengen[i],
                text=_guetetext(koerper, halteguete_von(w), V[:, 0])))
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


def _guetetext(koerper: list, wert: float, v) -> str:
    """„V104: in Richtung x nur 3e-05 der steifsten Halterung"."""
    # "default" ist die Elementgruppe derer ohne Gruppe - kein Bauteilname.
    namen = [x for x in koerper if str(x) != "default"] or list(koerper)
    wo = ", ".join(namen[:3]) + (" …" if len(namen) > 3 else "") or "Ein Teil"
    v = np.asarray(v, float)
    t, w = v[:3], v[3:]
    achsen = ("x", "y", "z")
    if float(np.linalg.norm(t)) >= float(np.linalg.norm(w)):
        richtung = "Richtung " + achsen[int(np.argmax(np.abs(t)))]
    else:
        richtung = "Drehung um " + achsen[int(np.argmax(np.abs(w)))]
    return (f"{wo}: in {richtung} nur {bruchteil_text(wert)} der steifsten Halterung - "
            "gehalten, aber dort fast ohne Steifigkeit")


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
# Koerper, die seitlich nur ueber reibungsfreien Kontakt und Staebe ohne
# Quersteifigkeit gehalten sind (17.10.2026)
# --------------------------------------------------------------------------
# Anlass: die 16 Ankerplatten am Drehlager haengen nur am Anker (Fachwerkstab)
# und an einem reibungsfreien Kontakt zu V14, in RFEM genauso (Freigabe Typ 1,
# Federkonstante 0 in der Ebene). Plastisch am feinen Netz rutschte eine Platte
# weg; erst die Mechanismus-Erkennung meldete es. Der Anwender: „gut wäre ein
# verständlicher hinweis in statik3D wenn so etwas auftritt“.
#
# Die Vorabsuche oben (restfreiheiten) sieht das nicht: sie nimmt ein
# Teiltragwerk als starr, und ueber den Stab gehoert der Fuss mit seinem Lager
# dazu. Hier wird darum **je Koerper** gefragt, was ihn als starren Koerper
# haelt: Lager, Kontakte (Normale; tangential nur mit Reibung), Spaltelemente,
# Kopplungen, Knoten, die er mit anderen Elementen teilt, und Staebe - ein
# Fachwerkstab oder Seil nur laengs, auch hinter einer starren Scheibe oder
# einem starren Koerper. Bleibt eine Bewegung frei, die eine Reibung im Kontakt
# halten wuerde (oder die nur Staebe ohne Quersteifigkeit begleiten), steht ein
# Hinweis da. Am Kontakt selbst wird nichts geaendert.
REIBUNG_VORSCHLAG = "μ = 0,2 nach EN 1090-2, Klasse D"
#: Starrkoerperbewegung im Ergebnis (17.10.2026, Praezisierung des Anwenders):
#: gemeldet, wenn der Koerper sich als Ganzes um mehr als diesen Anteil seiner
#: Bezugslaenge (halbe Diagonale) bewegt ...
STARR_WEG_MIN = 1e-3
#: ... und die Verformung (Abweichung von der besten Starrkoerperbewegung)
#: hoechstens dieser Anteil der Starrkoerperbewegung ist
STARR_VERFORMUNG_MAX = 0.1


def _freigabe_zeilen(model, K: set, mitte, L: float) -> tuple:
    """Gedachte Zeilen der Freigaben mit Federkonstante 0: ein Lager, das an
    Knoten des Koerpers in mindestens einer Verschiebungsrichtung haelt, in
    einer anderen aber nicht (RFEM „Freigabe“, Federkonstante 0 in der Ebene).
    Rueckgabe (Zeilen, {Name: {Richtungen}})."""
    zeilen, namen = [], {}
    achsen = np.eye(3)
    for s in getattr(model, "supports", None) or []:
        k = int(getattr(s, "node", -1))
        if k not in K:
            continue
        wirkt = {d for d in range(3) if getattr(s.dof_behaviour(d), "acts", False)}
        if not wirkt or len(wirkt) == 3:
            continue
        nm = str(getattr(s, "name", "") or f"Lager K{k}")
        for d in sorted(set(range(3)) - wirkt):
            a = _zeile(model.nodes[k], achsen[d], mitte, L)
            if a is not None:
                zeilen.append(a)
                namen.setdefault(nm, set()).add(d)
    for lager in list(getattr(model, "line_supports", None) or []) \
            + list(getattr(model, "surface_supports", None) or []):
        kn = [int(k) for k in (getattr(lager, "nodes", None) or []) if int(k) in K]
        if not kn:
            continue
        beh = getattr(lager, "behaviour", None) or {}
        wirkt = {int(d) for d, b in beh.items() if int(d) < 3 and getattr(b, "acts", False)}
        if not wirkt or len(wirkt) == 3:
            continue
        nm = str(getattr(lager, "name", "") or "Linien- bzw. Flächenlager")
        for k in kn:
            for d in sorted(set(range(3)) - wirkt):
                a = _zeile(model.nodes[k], achsen[d], mitte, L)
                if a is not None:
                    zeilen.append(a)
                    namen.setdefault(nm, set()).add(d)
    return zeilen, namen


def koerper_der_elemente(model) -> dict:
    """{Koerpername: [Volumenelemente]} - die Koerper des Modells
    (Model.koerper), sonst die Elementgruppen der Volumenelemente."""
    from .elemente import VOLUMEN_TYPEN
    vol = set(VOLUMEN_TYPEN)
    aus: dict = {}
    zu: set = set()
    ne = len(model.elements)
    for name, kp in (getattr(model, "koerper", None) or {}).items():
        el = [int(i) for i in (getattr(kp, "elemente", None) or [])
              if 0 <= int(i) < ne and model.elements[int(i)].typ in vol]
        if el:
            aus[str(name)] = el
            zu |= set(el)
    for i, e in enumerate(model.elements):
        if e.typ in vol and i not in zu:
            aus.setdefault(str(getattr(e, "group", "") or "default"), []).append(i)
    return aus


def kontakt_gehalten(model) -> list:
    """Koerper, die in einer oder mehreren Richtungen nur ueber reibungsfreie
    Kontakte (bzw. Fugen ohne tangentiale Steifigkeit) und Staebe ohne
    Quersteifigkeit gehalten sind - je Gruppe gleichartiger Koerper ein
    Eintrag {"koerper", "anzahl", "bewegung", "art" (rutscht | kippt),
    "kontakte", "partner", "staebe", "reibungsfrei", "text"}. Leer, wenn
    alles gehalten ist. Ein Koerper ganz ohne Halt gehoert nicht dazu, den
    nennt die Vorabsuche (restfreiheiten). Kostet je Koerper eine
    6x6-Eigenwertaufgabe; die Kontaktzeilen einmal fuer alle."""
    from .elemente import VOLUMEN_TYPEN
    vol = set(VOLUMEN_TYPEN)
    koerper = koerper_der_elemente(model)
    if not koerper:
        return []
    nn = int(model.nn)
    X = np.asarray(model.nodes, float)
    namen = sorted(koerper, key=_natuerlich)
    knoten = {b: {int(k) for i in koerper[b] for k in model.elements[i].nodes if 0 <= int(k) < nn}
              for b in namen}
    el_koerper = {i: b for b in namen for i in koerper[b]}
    besitzer: dict = {}
    for b in namen:
        for k in knoten[b]:
            besitzer.setdefault(k, set()).add(b)
    # Elemente an den Knoten, die zu keinem Koerper gehoeren (Staebe, Schalen, Federn)
    fremd: dict = {}
    for i, e in enumerate(model.elements):
        if i in el_koerper:
            continue
        for k in e.nodes:
            fremd.setdefault(int(k), []).append(i)
    stab_name = {}
    for mn, mem in (getattr(model, "members", None) or {}).items():
        for ei in mem.elements:
            stab_name[int(ei)] = str(mn)
    teil_von = {k: namen.index(next(iter(sorted(bs)))) for k, bs in besitzer.items()}
    mitten, laengen = {}, {}
    for j, b in enumerate(namen):
        mitten[j], laengen[j] = _mitte_und_laenge(X[sorted(knoten[b])])
    kontakt = _kontaktzeilen(model, teil_von, mitten, laengen)
    hyp = _kontaktzeilen(model, teil_von, mitten, laengen, reibung_annehmen=True)
    # reibungsfreie Fugen und ihre Seiten
    reibfrei, seiten = set(), {}
    for cp in getattr(model, "contact_pairs", None) or []:
        if not (bool(getattr(cp, "haften", False)) or float(getattr(cp, "mu", 0.0)) > 0
                or bool(getattr(cp, "zug", False))):
            reibfrei.add(cp.name)
        s_b = {b for k in (cp.slave_nodes or []) for b in besitzer.get(int(k), ())}
        m_b = {el_koerper[int(i)] for i in (cp.master_elements or []) if int(i) in el_koerper}
        seiten[cp.name] = (s_b, m_b)
    for g in getattr(model, "gap_elements", None) or []:
        if float(getattr(g, "mu", 0.0)) <= 0:
            reibfrei.add(str(getattr(g, "group", "") or "Spaltelement"))
    achsen = np.eye(3)
    from .fugen import STABENDE_GRUPPE, STARR_GRUPPE

    def stabzeilen(kn, b, mitte, L, staebe):
        """Was am Knoten kn ausser dem Koerper b haengt: (Zeilen, voll)."""
        z, voll = [], False
        for i in fremd.get(kn, []):
            e = model.elements[i]
            if e.typ in ("truss", "seil"):
                a, c = (int(e.nodes[0]), int(e.nodes[-1]))
                z.append(_zeile(X[kn], X[c] - X[a], mitte, L))
                staebe.add(stab_name.get(i, f"Element {i}"))
            else:
                voll = True
        for bb in besitzer.get(kn, ()):
            if bb != b:
                voll = True
        return z, voll

    roh = []
    for j, b in enumerate(namen):
        K = knoten[b]
        mitte, L = mitten[j], laengen[j]
        gl, ug = _lagerzeilen(model, K, mitte, L)
        kg, ku, fugen = kontakt.get(j, ([], [], set()))
        hg, _hu, _hf = hyp.get(j, ([], [], set()))
        zeilen = list(gl) + list(ug) + list(kg) + list(ku)
        staebe: set = set()
        # Knoten des Koerpers, an denen anderes haengt
        for k in K:
            if k not in fremd and len(besitzer.get(k, ())) < 2:
                continue
            z, voll = stabzeilen(k, b, mitte, L, staebe)
            if voll:
                zeilen += [_zeile(X[k], achsen[d], mitte, L) for d in range(3)]
            zeilen += z
        # Kopplungen und starre Koerper: was am anderen Ende haelt
        master: dict = {}
        for kp in getattr(model, "kopplungen", None) or []:
            a, c = int(kp.node_a), int(kp.node_b)
            if (a in K) == (c in K):
                continue
            g = str(getattr(kp, "gruppe", "") or "")
            innen, aussen = (a, c) if a in K else (c, a)
            if g.startswith(STARR_GRUPPE) or g.startswith(STABENDE_GRUPPE):
                master.setdefault(aussen, True)
                continue
            for richtung, wert in kp.paare():
                if wert != 0:
                    zeilen.append(_zeile(X[innen], richtung, mitte, L))
        for sk in getattr(model, "starrkoerper", None) or []:
            m_, sl = int(sk.master), [int(x) for x in (sk.slaves or [])]
            if m_ not in K and any(x in K for x in sl):
                master.setdefault(m_, True)
            elif m_ in K and any(x not in K for x in sl):
                zeilen += [_zeile(X[m_], achsen[d], mitte, L) for d in range(3)]
        for m_ in master:
            z, voll = stabzeilen(m_, b, mitte, L, staebe)
            mg, mu_ = _lagerzeilen(model, {m_}, mitte, L)
            if voll:
                zeilen += [_zeile(X[m_], achsen[d], mitte, L) for d in range(3)]
                zeilen += [_drehzeile(achsen[d]) for d in range(3)]
            zeilen += z + list(mg) + list(mu_)
        zeilen = [x for x in zeilen if x is not None]
        if not zeilen:
            continue                              # ganz ohne Halt: die Vorabsuche
        frei = _nullraum(zeilen)
        if not frei.shape[1]:
            continue
        rf = sorted(f for f in fugen if f in reibfrei)
        hilft = bool(rf) and _nullraum(zeilen + list(hg)).shape[1] < frei.shape[1]
        fz, fnamen = _freigabe_zeilen(model, K, mitte, L)
        hilft_f = bool(fz) and _nullraum(zeilen + fz).shape[1] < frei.shape[1]
        if not hilft and not hilft_f and not staebe:
            continue
        partner = set()
        for f in (rf if hilft else []):
            s_b, m_b = seiten.get(f, (set(), set()))
            partner |= (m_b if b in s_b else s_b) - {b}
        roh.append({"koerper": b, "frei": frei, "kontakte": rf if hilft else [],
                    "freigaben": {n: sorted(d) for n, d in fnamen.items()} if hilft_f else {},
                    "partner": sorted(partner, key=_natuerlich), "staebe": sorted(staebe, key=_natuerlich)})
    return _kontakt_gehalten_gruppen(roh)


def _kontakt_gehalten_gruppen(roh: list) -> list:
    """Gleichartige Koerper (dieselben freien Bewegungen, dieselben Gegenkoerper,
    Fugen und Freigaben) in eine Zeile, im Wortlaut der Praezisierung des
    Anwenders vom 17.10.2026: „Ankerplatte V… ist in der Ebene nicht gehalten.
    Sie liegt reibungsfrei auf (Fuge ‚Lagerbock-Unterlegbleche‘: Federkonstante
    0, kein Reibbeiwert). Bei symmetrischer Last bleibt sie in Ruhe, bei
    Querlast oder ungleichmäßigem Fließen kann sie wegrutschen. Abhilfe:
    Reibbeiwert in der Fuge setzen (z. B. μ = 0,2 nach EN 1090-2, Klasse D),
    Federkonstante > 0 oder seitliche Halterung.“"""
    gruppen: dict = {}
    for r in roh:
        S = r["frei"]
        bew = _bewegungstext(S)
        _u, s, vt = np.linalg.svd(S[3:, :], full_matrices=True)
        rang = int((s > 1e-3).sum())
        T = _unterraum(S[:3, :] @ vt[rang:].T) if rang < S.shape[1] else np.zeros((3, 0))
        art = "rutscht" if (T.shape[1] or "verschieblich" in bew) else "kippt"
        fg = tuple(sorted((n, tuple(d)) for n, d in r["freigaben"].items()))
        key = (bew, tuple(r["partner"]), tuple(r["kontakte"]), fg, art)
        g = gruppen.setdefault(key, {"koerper": [], "staebe": [], "T": T})
        g["koerper"].append(r["koerper"])
        g["staebe"] += [x for x in r["staebe"] if x not in g["staebe"]]
    aus = []
    for (bew, partner, kontakte, fg, art), g in gruppen.items():
        kn = sorted(g["koerper"], key=_natuerlich)
        st = sorted(g["staebe"], key=_natuerlich)
        n = len(kn)
        eins = n == 1
        wer = (f"Körper {kn[0]}" if eins else
               f"{n} Körper " + (", ".join(kn) if n <= 6 else f"{kn[0]}–{kn[-1]}"))
        T = g["T"]
        wo = ("in der Ebene" if T.shape[1] == 2 else
              f"in Richtung {_achse(T[:, 0])}" if T.shape[1] == 1 else
              "in keiner Richtung" if T.shape[1] == 3 else "gegen Verdrehen")
        er, Er = ("er", "Er") if eins else ("sie", "Sie")
        ist, liegt, bleibt, kann, haengt = (("ist", "liegt", "bleibt", "kann", "hängt") if eins else
                                            ("sind", "liegen", "bleiben", "können", "hängen"))
        stab = ""
        if st:
            stab = (f" und {haengt} an {'dem Stab' if len(st) == 1 else 'den Stäben'} "
                    f"{_namenstext(st, 'Stäbe')} ohne Quersteifigkeit")
        satz1 = f"{wer} {ist} {wo} nicht gehalten ({bew})."
        lage = f"Bei symmetrischer Last {bleibt} {er} in Ruhe, bei Querlast oder ungleichmäßigem Fließen {kann} {er} "
        if kontakte or fg:
            teile = [f"Fuge ‚{f}‘: Federkonstante 0, kein Reibbeiwert" for f in kontakte]
            teile += [f"Freigabe ‚{nm}‘: Federkonstante 0 in " + ", ".join(_ACHSEN[d] for d in dd) for nm, dd in fg]
            auf = f" auf {', '.join(partner)}" if partner else " auf"
            text = (f"{satz1} {Er} {liegt} reibungsfrei{auf} ({'; '.join(teile)}){stab}. {lage}wegrutschen. "
                    f"Abhilfe: Reibbeiwert in der Fuge setzen (z. B. {REIBUNG_VORSCHLAG}), Federkonstante > 0 oder "
                    "seitliche Halterung.")
        else:
            text = (f"{satz1} {'Ihn' if eins else 'Sie'} {'hält' if len(st) == 1 else 'halten'} dort nur "
                    f"{'der Stab' if len(st) == 1 else 'die Stäbe'} {_namenstext(st, 'Stäbe')} ohne "
                    f"Quersteifigkeit. {lage}wegrutschen oder kippen. Abhilfe: seitliche Halterung (Lager, Feder "
                    "mit Federkonstante > 0, Kopplung) oder eine Fuge mit Reibbeiwert.")
        aus.append({"koerper": kn, "anzahl": n, "bewegung": bew, "art": art, "kontakte": list(kontakte),
                    "freigaben": [nm for nm, _d in fg], "partner": list(partner), "staebe": st,
                    "reibungsfrei": bool(kontakte or fg), "text": text})
    aus.sort(key=lambda e: (-e["anzahl"], _natuerlich(e["koerper"][0])))
    return aus


def kontakt_gehalten_gemerkt(model) -> list:
    """:func:`kontakt_gehalten`, am Modell gemerkt, solange sich Netz, Fugen,
    Lager und Kopplungen nicht aendern (fuer die Pruefung je Ergebnis)."""
    sch = (int(model.nn), len(model.elements),
           tuple((cp.name, float(getattr(cp, "mu", 0.0)), bool(getattr(cp, "haften", False)),
                  len(cp.slave_nodes or [])) for cp in (getattr(model, "contact_pairs", None) or [])),
           len(getattr(model, "supports", None) or []), len(getattr(model, "kopplungen", None) or []),
           len(getattr(model, "starrkoerper", None) or []), len(getattr(model, "gap_elements", None) or []))
    alt = getattr(model, "_kontakt_gehalten_gemerkt", None)
    if alt is not None and alt[0] == sch:
        return alt[1]
    h = kontakt_gehalten(model)
    try:
        model._kontakt_gehalten_gemerkt = (sch, h)
    except AttributeError:
        pass
    return h


def starrkoerperbewegung(model, u, koerper_namen) -> list:
    """Bewegt sich ein Koerper als Ganzes (17.10.2026, Praezisierung des
    Anwenders: „Körper V… bewegt sich als Ganzes um x mm in Richtung … – nicht
    gehalten“, getrennt vom plastischen Mechanismus)? Je Koerper aus
    ``koerper_namen`` die beste Starrkoerperbewegung der Knotenverschiebungen
    ``u`` (nn x 6 oder flach) nach kleinsten Quadraten; gemeldet, wenn sie
    groesser als :data:`STARR_WEG_MIN` mal die Bezugslaenge ist und die
    Verformung hoechstens :data:`STARR_VERFORMUNG_MAX` davon. Rueckgabe je
    Koerper {"koerper", "weg" [m], "t" (Richtung), "omega" [rad], "verformung"
    [m], "knoten", "mitte", "laenge", "text"}."""
    from .zahlen import zahl_text as _z
    nn = int(model.nn)
    U = np.asarray(u, float).reshape(-1)
    if U.size < 6 * nn:
        return []
    U = U[:6 * nn].reshape(nn, 6)[:, :3]
    kk = koerper_der_elemente(model)
    X = np.asarray(model.nodes, float)
    aus = []
    for b in sorted(set(koerper_namen or []), key=_natuerlich):
        el = kk.get(b)
        if not el:
            continue
        P = np.unique(np.concatenate([np.asarray(model.elements[i].nodes, np.int64) for i in el]))
        P = P[(P >= 0) & (P < nn)]
        if len(P) < 3:
            continue
        mitte, L = _mitte_und_laenge(X[P])
        r = X[P] - mitte
        M = np.zeros((3 * len(P), 6))
        M[0::3, 0] = M[1::3, 1] = M[2::3, 2] = 1.0
        M[0::3, 4], M[0::3, 5] = r[:, 2] / L, -r[:, 1] / L
        M[1::3, 3], M[1::3, 5] = -r[:, 2] / L, r[:, 0] / L
        M[2::3, 3], M[2::3, 4] = r[:, 1] / L, -r[:, 0] / L
        Y = U[P].ravel()
        p, *_ = np.linalg.lstsq(M, Y, rcond=None)
        starr = (M @ p).reshape(-1, 3)
        rest = Y.reshape(-1, 3) - starr
        s_max = float(np.linalg.norm(starr, axis=1).max())
        v_max = float(np.linalg.norm(rest, axis=1).max())
        if s_max <= STARR_WEG_MIN * L or v_max > STARR_VERFORMUNG_MAX * s_max:
            continue
        t, w = p[:3], p[3:] / L
        weg = float(np.linalg.norm(t))
        teile = []
        if weg >= 0.1 * s_max:
            teile.append(f"um {_z(weg * 1e3, stellen=3)} mm in Richtung {_achse(t)}")
        if float(np.linalg.norm(w)) * L >= 0.1 * s_max:
            teile.append(f"dreht sich um {_achse(w)} um {_z(float(np.linalg.norm(w)) * 1e3, stellen=3)} mrad")
        text = f"Körper {b} bewegt sich als Ganzes " + " und ".join(teile) + " – nicht gehalten"
        aus.append({"koerper": b, "weg": weg, "t": [float(x) for x in t], "omega": [float(x) for x in w],
                    "verformung": v_max, "knoten": [int(k) for k in P], "mitte": [float(x) for x in mitte],
                    "laenge": float(L), "text": text})
    return aus


def starrkoerper_singularitaet(e: dict) -> "Singularitaet":
    """Ein Eintrag von :func:`starrkoerperbewegung` als freie Bewegung fuer die
    3D-Ansicht (Ergebnisse → Freie Bewegungen): Knoten des Koerpers
    hervorgehoben, Pfeil in Bewegungsrichtung."""
    t = np.asarray(e["t"], float)
    w = np.asarray(e["omega"], float)
    s = Singularitaet(art="starr", knoten=list(e["knoten"]), koerper=[e["koerper"]],
                      t=t / (np.linalg.norm(t) or 1.0) if np.linalg.norm(t) > 0 else np.zeros(3),
                      omega=w * float(e["laenge"]) / (np.linalg.norm(w) * float(e["laenge"]) or 1.0)
                      if np.linalg.norm(w) > 0 and np.linalg.norm(t) == 0 else np.zeros(3),
                      bezug=np.asarray(e["mitte"], float), mitte=np.asarray(e["mitte"], float),
                      laenge=float(e["laenge"]), text=e["text"],
                      ursache="der Körper bewegt sich als Ganzes, ohne nennenswerte Verformung")
    s.weg = float(e["weg"])
    return s


def kontakt_gehalten_zeilen(model) -> list:
    """Die Zeilen vor dem Start: INFORMATION bei elastischer, „WARNUNG – BITTE
    LESEN“ bei plastischer Rechnung (wie der Hinweis zum Kreisring)."""
    try:
        h = kontakt_gehalten(model)
    except Exception:                          # noqa: BLE001 - ein Hinweis sperrt nie
        return []
    pz = getattr(model, "plastizitaet", None)
    wort = "WARNUNG – BITTE LESEN" if (pz is not None and getattr(pz, "an", False)) else "INFORMATION"
    return [f"{wort}: {e['text']}" for e in h]


def kontakt_koerper_am_ort(model, element=None, knoten=None):
    """Der Eintrag von :func:`kontakt_gehalten`, zu dessen Koerper das Element
    bzw. der Knoten gehoert - fuer die Traglastmeldung - oder None."""
    if element is None and knoten is None:
        return None
    h = kontakt_gehalten_gemerkt(model)
    if not h:
        return None
    kk = koerper_der_elemente(model)
    gesucht = set()
    for b, el in kk.items():
        if element is not None and int(element) in set(el):
            gesucht.add(b)
        if knoten is not None and any(int(knoten) in [int(x) for x in model.elements[i].nodes] for i in el):
            gesucht.add(b)
    for e in h:
        treffer = [b for b in e["koerper"] if b in gesucht]
        if treffer:
            return dict(e, koerper_ort=treffer[0])
    return None


# --------------------------------------------------------------------------
# Stufe 2
# --------------------------------------------------------------------------
def _weichstes_element(model, voll: np.ndarray, knoten) -> tuple:
    """Das Element, das die Bewegung traegt: (Nummer, Ausschlag, Energie).

    Zwei Kennzahlen aus dem Modus:

        Ausschlag  a_e = max |u| ueber die Knoten von e   -> wo die Bewegung
                                                             sichtbar ist
        Energie    E_e = u_e^T K_e u_e                    -> wo sie kaum
                                                             Widerstand findet

    Gezeigt wird das Element mit dem groessten Ausschlag; die Energie steht
    daneben, denn grosser Ausschlag bei fast keiner Energie **ist** die
    Diagnose. Sie kommt zweimal zurueck: als Formaenderungsarbeit in Nm und
    als Anteil E_e / (a_e^2 * mittlere Diagonale von K_e) - dimensionslos und
    darum ohne Kenntnis des Werkstoffs lesbar. Gesucht wird nur unter den Elementen an den Knoten der Bewegung,
    und die Elementsteifigkeit wird nur fuer den Gewinner aufgestellt - ueber
    alle 489376 Elemente eines Volumenmodells waere es eine eigene Rechnung.
    """
    kn = {int(k) for k in (knoten if knoten is not None else [])}
    if not kn or voll.size < 3 * model.nn:
        return -1, 0.0, 0.0
    u3 = voll.reshape(-1, 6)[:, :3]
    bester, gross = -1, -1.0
    for i, e in enumerate(model.elements):
        nd = [int(x) for x in e.nodes]
        if kn.isdisjoint(nd):
            continue
        a = float(np.abs(u3[nd]).max())
        if a > gross:
            bester, gross = i, a
    if bester < 0:
        return -1, 0.0, 0.0
    energie, anteil = 0.0, 0.0
    try:
        from .assemble import element_dofs, element_matrix
        e = model.elements[bester]
        d = np.asarray(element_dofs(e, model), int)
        if d.max() < voll.size:
            ue = voll[d]
            # Die **volle** Elementmatrix, auch mit Model.knotendilatation:
            # dort liefert element_matrix nur den deviatorischen Anteil, der
            # volumetrische steht global in assemble.knotendilatation. Mit
            # ihm allein haette der Tetraeder einen Nullraum von 7 statt 6,
            # und eine voll gehaltene Aufweitung erschiene als "Bewegung ohne
            # Energie" (gemessen 20.09.2026: Energie 6,2e7 J -> -7,1e-12 J bei
            # nu = 0,499, mittlere |diag| um Faktor 151 kleiner).
            dil = getattr(model, "knotendilatation", False)
            try:
                model.knotendilatation = False
                Ke = np.asarray(element_matrix(model, e), float)
            finally:
                model.knotendilatation = dil
            # K_e ist positiv semidefinit; ein negatives Ergebnis ist
            # Ausloeschung um die Null herum - und genau die ist der Befund:
            # die Bewegung ist eine Starrkoerperbewegung dieses Elements und
            # kostet nichts.
            energie = max(0.0, float(ue @ (Ke @ ue)))
            nenner = gross * gross * float(np.mean(np.abs(np.diag(Ke))))
            anteil = energie / nenner if nenner > 0 else 0.0
    except Exception:                     # noqa: BLE001 - eine Zahl daneben
        energie, anteil = 0.0, 0.0        # darf die Diagnose nicht sperren
    return bester, gross, energie, anteil


# --------------------------------------------------------------------------
# Gelenkkette (Befund C8, 09.11.2026)
# --------------------------------------------------------------------------
#: Bezogene Energie v^T K v / v^T diag(K) v, unter der eine Bewegung als
#: Mechanismus gilt. Gemessen am 10.11.2026 (inverse Iteration, 20 Schritte):
#: Einfeldtraeger mit Mittelgelenk 1,5e-17, Zweifeldtraeger mit zwei Gelenken
#: in einem Feld 2,5e-16; derselbe Einfeldtraeger ohne Gelenk 7,7e-2, der
#: Gerbertraeger (Gelenk, aber tragfaehig) 1,9e-2; der Gerbertraeger mit einem
#: Stabelement vom 1e-6-fachen E-Modul 1,0e-7, vom 1e-9-fachen 4,8e-11 (das
#: bleibt „Bauteil mit Nullsteifigkeit“). Beim 1e-12-fachen (1,6e-13) trennt
#: das weiche Element den Traeger, und das Gelenk bildet wirklich eine Kette.
GELENK_NULLENERGIE = 1e-12
#: Ein Gelenk gilt als beteiligt, wenn es sich in der Bewegung um mehr als
#: diesen Anteil des groessten Ausschlags oeffnet (Drehung mal Elementlaenge).
GELENK_OEFFNUNG = 1e-3
#: Die Vorpruefung (gelenkketten) stellt die Steifigkeit auf und zerlegt sie:
#: nur bis zu dieser Zahl von Freiheitsgraden. Stabwerke liegen weit darunter.
GELENKKETTE_FHG_MAX = 60000
_GELENK_FHG = ("u_x", "u_y", "u_z", "φ_x", "φ_y", "φ_z")


def _stabname(model, nr: int) -> str:
    """„Stab „S1“ (Stabelement E3)“ oder „Stabelement E3“ - die Namen, unter
    denen die Oberflaeche Stab und Stabelement fuehrt."""
    for name, mb in (getattr(model, "members", None) or {}).items():
        if int(nr) in (getattr(mb, "elements", None) or []):
            return f"Stab „{name}“ (Stabelement E{int(nr)})"
    return f"Stabelement E{int(nr)}"


def gelenkkette(model, voll) -> "dict | None":
    """Oeffnen sich in der Bewegung ``voll`` freie Stabendgelenke?

    Fuer jedes Stabelement mit freien Gelenken wird die Bewegung des Stabendes
    aus der Kondensation zurueckgerechnet (assemble.stab_endkinematik) und mit
    der des Knotens verglichen: der Sprung ist die Oeffnung des Gelenks. Eine
    Drehung zaehlt mit der Elementlaenge als Weg. Rueckgabe None oder
    {"gelenke": [(Element, Knoten, lokaler FHG, Oeffnung)], "elemente",
    "knoten"} mit allen Gelenken, die sich um mindestens ein Zehntel der
    groessten Oeffnung oeffnen."""
    try:
        from . import assemble as asm
        voll = np.asarray(voll, float).ravel()
        n6 = 6 * model.nn
        if voll.size < n6:
            return None
        u = voll[:n6].reshape(-1, 6)
        amax = float(np.abs(u[:, :3]).max()) if u.size else 0.0
        if not amax > 0:
            return None
        funde = []
        for i, e in enumerate(model.elements):
            hg = getattr(e, "hinges", None)
            if not hg or e.typ not in asm.LINE_TYPES or model.stab_woelbt(e):
                continue
            kl, _T3, T, L = asm.beam_local(model, e)
            C = asm.stab_endkinematik(model, e, kl)
            if C is None:
                continue
            ul = T @ u[[int(k) for k in e.nodes]].reshape(-1)
            A = asm.beam_versatz(e)
            if A is not None:
                ul = A @ ul
            sprung = C @ ul - ul
            for c in hg:
                c = int(c)
                weg = abs(float(sprung[c])) * (float(L) if c % 6 >= 3 else 1.0)
                funde.append((weg, i, int(e.nodes[c // 6]), c % 6))
    except Exception:                     # noqa: BLE001 - eine Diagnose darf nie sperren
        return None
    if not funde:
        return None
    gross = max(f[0] for f in funde)
    if gross < GELENK_OEFFNUNG * amax:
        return None
    bet = sorted((f for f in funde if f[0] >= 0.1 * gross), key=lambda f: (f[1], f[3]))
    return {"gelenke": [(i, k, d, w / amax) for w, i, k, d in bet],
            "elemente": sorted({f[1] for f in bet}),
            "knoten": sorted({f[2] for f in bet})}


def _gelenkkette_text(model, kette: dict, knoten_max: int) -> tuple:
    """(Text, Ursache) der Meldung „Gelenkkette: … beweglich“."""
    el, kn = kette["elemente"], kette["knoten"]
    staebe = ", ".join(_stabname(model, i) for i in el[:4]) + (" …" if len(el) > 4 else "")
    knoten = ", ".join(f"K{k}" for k in kn[:6]) + (" …" if len(kn) > 6 else "")
    eins = len({(i, k) for i, k, _d, _w in kette["gelenke"]}) == 1     # ein Gelenk, auch mit zwei freien Drehungen
    text = (f"Gelenkkette: {staebe} mit {'Stabendgelenk' if eins else 'Stabendgelenken'} "
            f"an {'Knoten' if len(kn) == 1 else 'den Knoten'} {knoten} {'ist' if len(el) == 1 else 'sind'} "
            f"beweglich")
    fhg = sorted({_GELENK_FHG[d] for _i, _k, d, _w in kette["gelenke"]})
    ursache = ("Die Stabendgelenke bilden mit den Lagern eine kinematische Kette: die gezeigte Bewegung "
               f"öffnet {'das Gelenk' if eins else 'die Gelenke'} "
               f"({', '.join(fhg)} frei), ohne dass ein Bauteil Widerstand leistet"
               + (f"; der größte Ausschlag liegt an Knoten K{int(knoten_max)}" if knoten_max >= 0 else "")
               + ". Ein Gelenk schließen (biegesteifer Anschluss oder Drehfeder) oder ein Lager ergänzen.")
    return text, ursache


def gelenkketten(model) -> list:
    """Vorpruefung: bilden die Stabendgelenke eine kinematische Kette?

    „Freie Bewegungen“ (restfreiheiten) rechnet je Teiltragwerk mit starren
    Koerpern und kennt keine Stabendgelenke: der Einfeldtraeger mit
    Mittelgelenk galt als gehalten (Befund C8). Hier wird die Steifigkeit
    aufgestellt und ihr weichster Modus gesucht (weichster_modus); eine
    Meldung gibt es nur, wenn er keine Energie kostet und ein Gelenk oeffnet.

    Leer ohne freie Stabendgelenke, mit Kontakt oder nichtlinearen Lagern (dort
    haelt erst die Rechnung) und ueber GELENKKETTE_FHG_MAX Freiheitsgraden -
    dann nennt die Rechnung die Kette, wenn sie daran scheitert."""
    try:
        from . import assemble as asm
        if not any(getattr(e, "hinges", None) for e in model.elements):
            return []
        if getattr(model, "has_contact", False) or model.ndof > GELENKKETTE_FHG_MAX:
            return []
        from . import supports as sup
        _lin, nichtlinear = sup.split(sup.expand(model))
        if nichtlinear:
            return []
        aktiv = model.grundmaske() if hasattr(model, "grundmaske") else None
        K = asm.stiffness(model, 1, aktiv)
        fixed, _vals, _auto = asm.gesperrte_und_automatische(model, K)
        moden = weichster_modus(K, model, np.where(~fixed)[0])
    except Exception:                     # noqa: BLE001 - eine Diagnose darf nie sperren
        return []
    return [s for s in moden if getattr(s, "gelenke", None)]


def weichster_modus(K, model, frei=None, schritte: int = 20,
                    hoechstens: int = 1, melden=None) -> list:
    """Stufe 2: der niedrigste Modus von K ueber inverse Iteration.

    Fuer Faelle ohne Starrkoerpermodus - weiche Mechanismen, Nullsteifigkeit,
    Splitterelemente. ``K + eps·I`` ist faktorisierbar, auch wenn K es nicht
    ist; die inverse Iteration konvergiert dann gegen den betragskleinsten
    Eigenvektor, und das ist die Bewegung, die fast keine Energie kostet.

    ``frei`` sind die Zeilen/Spalten, die nach dem Einbau der Lager bleiben
    (None = alle). Rueckgabe eine Liste von :class:`Singularitaet` mit
    ``feld`` als Knotenvektorfeld; ist die Diagnose-Faktorisierung
    ausgewichen, steht der Grund in ``ausweichgrund`` - unabhaengig von
    ``melden``. Scheitert die Faktorisierung oder die Iteration, geht
    :class:`MatrixdiagnoseUnmoeglich` hinaus, keine leere Liste.
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
    except Exception as ex:               # noqa: BLE001 - jede Art heisst: nicht gerechnet
        # Nicht sperren heisst nicht schweigen: der Aufrufer
        # (diagnose._matrixbefund) faengt das und schreibt „nicht möglich".
        raise MatrixdiagnoseUnmoeglich(
            f"die Faktorisierung von K + ε·I ({Kf.shape[0]} Freiheitsgrade) "
            f"scheiterte - {type(ex).__name__}: {ex}") from ex
    if melden:
        melden(f"Diagnose: weichster Modus über {lu.beschreibung()} "
               f"({Kf.shape[0]} Freiheitsgrade, {schritte} Schritte)")
    rng = np.random.default_rng(0)
    v = rng.standard_normal(Kf.shape[0])
    v /= np.linalg.norm(v) or 1.0
    for schritt in range(1, schritte + 1):
        try:
            # **Ohne** Residuumspruefung. K + eps*I ist hier mit Absicht fast
            # singulaer - das ist der Sinn der inversen Iteration. Die Pruefung
            # des Loesers schlug darum genau in den Faellen zu, fuer die diese
            # Diagnose ueberhaupt da ist: an zwei Wuerfeln mit einem
            # gemeinsamen Knoten stieg sie im ersten Schritt mit
            # "Residuum 2.3e-06" aus, und Stufe 2 lieferte nie einen Befund.
            v = lu.solve(v, check=False)
        except Exception as ex:           # noqa: BLE001
            raise MatrixdiagnoseUnmoeglich(
                f"die inverse Iteration scheiterte in Schritt {schritt} über "
                f"{lu.beschreibung()} - {type(ex).__name__}: {ex}") from ex
        nv = np.linalg.norm(v)
        if not np.isfinite(nv) or nv <= 0:
            raise MatrixdiagnoseUnmoeglich(
                f"die inverse Iteration lieferte in Schritt {schritt} keinen "
                f"endlichen Vektor (Norm {nv:g}) über {lu.beschreibung()}")
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
    nr, ausschlag, energie, anteil = _weichstes_element(model, voll, gross)
    art = str(getattr(model.elements[nr], "typ", "")) if nr >= 0 else ""
    # Gelenkkette (Befund C8): die Bewegung kostet keine Energie und oeffnet
    # ein Stabendgelenk - dann ist es kein Splitterelement und keine
    # Nullsteifigkeit, sondern eine kinematische Kette.
    nenner = float(v @ (diag * v))
    bezogen = float(v @ (Kf @ v)) / nenner if nenner > 0 else 0.0
    kette = gelenkkette(model, voll) if abs(bezogen) <= GELENK_NULLENERGIE else None
    if kette:
        ktext, kursache = _gelenkkette_text(model, kette, int(np.argmax(betrag)))
        s = Singularitaet(
            art="numerisch", knoten=[int(k) for k in gross], koerper=koerper,
            t=(feld[gross].mean(axis=0) if len(gross) else np.zeros(3)),
            bezug=schwer, mitte=schwer, feld=feld,
            element=nr, ausschlag=ausschlag, energie=energie, anteil=anteil,
            ausweichgrund=str(getattr(lu, "ausweichgrund", "") or ""),
            text=ktext, ursache=kursache,
            abhilfe=("lager", int(kette["knoten"][0])))
        s.gelenke = list(kette["gelenke"])
        s.bezogene_energie = bezogen
        return [s][:hoechstens]
    s = Singularitaet(
        art="numerisch", knoten=[int(k) for k in gross], koerper=koerper,
        t=(feld[gross].mean(axis=0) if len(gross) else np.zeros(3)),
        bezug=schwer, mitte=schwer, feld=feld,
        element=nr, ausschlag=ausschlag, energie=energie, anteil=anteil,
        ausweichgrund=str(getattr(lu, "ausweichgrund", "") or ""),
        text=f"{wo}" + (f", Element {nr} ({art})" if nr >= 0 else "")
             + ": Bewegung fast ohne Steifigkeit",
        ursache="Die Steifigkeitsmatrix ist hier nahezu singulär. Die gezeigte "
                "Bewegung kostet fast keine Energie - meist Splitterelemente oder "
                "ein Bauteil mit Nullsteifigkeit."
                + (f" Ausschlag {_zahl(ausschlag)} bei {bruchteil_text(anteil)} der mittleren "
                   f"Steifigkeit dieses Elements ({_zahl(energie)} Nm "
                   f"Formänderungsarbeit)." if nr >= 0 else ""),
        abhilfe=("lager", int(gross[0])) if len(gross) else None)
    s.bezogene_energie = bezogen
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


# --------------------------------------------------------------------------
# Stufe 3 - frei bewegliche Teile aus den gestoerten Pivots (B5, 08.10.2026)
# --------------------------------------------------------------------------
#: Schalter der Suche. Nur die Pruefungen schalten ihn aus, um zu zeigen, dass
#: die Rechnung mit und ohne Suche bitgleich bleibt; im Programm steht er immer
#: an.
PIVOTBEFUND = True

#: Hoechstzahl der zufaelligen rechten Seiten. Ein Bauteil hat hoechstens sechs
#: freie Starrkoerperbewegungen; mit sechs Loesungen sind sie alle aufloesbar.
#: Weniger gestoerte Pivots brauchen weniger (Zahl der Pivots + 1, mindestens 2).
PIVOT_LOESUNGEN_MAX = 6

#: Die Antworten der Knoten (Betrag ueber alle rechten Seiten) fallen in zwei
#: Haufen, wenn etwas frei ist: die gesunden und die um die Verstaerkung des
#: angehobenen Pivots groesseren. Getrennt wird im Logarithmus nach Otsu (die
#: Schwelle, die die Streuung innerhalb der beiden Haufen am kleinsten macht);
#: es gilt nur, wenn die Haufenmitten mindestens PIVOT_DEKADEN Zehnerpotenzen
#: auseinander liegen und die Trennung PIVOT_TRENNUNG der Gesamtstreuung
#: erklaert. Eine feste Verstaerkung gegen den Median taugt nicht: sind mehr als
#: drei Viertel der Knoten frei (ein Block auf einer Platte, nur ueber Kontakt),
#: liegt der Median selbst im verstaerkten Haufen. Gemessen am Drehlager
#: (zerlegung_entwurf_pivot, 08.10.2026): die freien Platten standen 8e8-mal
#: ueber dem Median (rund 8 Zehnerpotenzen), in den kleinen Modellen der
#: Pruefung liegen die Haufen 13 bis 14 auseinander; die gesunden Beispiele
#: kommen auf hoechstens 3,3 (Tor), die meisten auf unter 1
#: (tests/test_freie_teile.py misst beides und druckt die Zahlen). Die
#: Trennung allein taugt nicht: gesunde Modelle liegen dort bei 0,72 bis 0,91.
PIVOT_DEKADEN = 5.0
PIVOT_TRENNUNG = 0.8

#: Ein Bauteil gilt als frei bewegt, wenn mindestens dieser Anteil seiner Knoten
#: verstaerkt ist ...
PIVOT_KOERPERANTEIL = 0.5

#: ... und eine Starrkoerperbewegung (6 Parameter) seine verstaerkte
#: Verschiebung so gut erklaert (1 - Fehler/Betrag, fuer jede rechte Seite).
#: Am Drehlager lag sie bei 1 - 7e-11 und besser.
PIVOT_STARR = 0.999

#: Singulaerwerte unter diesem Anteil des groessten zaehlen nicht als eigene
#: freie Richtung. Die Amplituden der Richtungen eines Bauteils streuen um
#: ein bis zwei Zehnerpotenzen (Drehlager: 1,0 gegen 0,014 zwischen zwei
#: Platten), das Rauschen liegt bei 1e-9.
PIVOT_RANG = 1e-5

#: „Frei drehbar“ streng (Vorgabe des Anwenders vom 16.10.2026): ein
#: Freiheitsgrad ist **nur numerisch gehalten**, wenn seine wirksame
#: Steifigkeit - die Antwort des vorhandenen Faktors auf eine Einheitslast dort
#: - unter diesem Anteil seiner Hauptdiagonale liegt. Die Hauptdiagonale traegt
#: die Kopplung (Strafbeiwert 1e4 mal die groesste Diagonale); was das Tragwerk
#: dahinter haelt, liegt einige Zehnerpotenzen darunter, ein angehobener Pivot
#: bei 1e-13 der Matrix und tiefer. Gemessen am Drehlager-Entwurf mit Lochrand:
#: Ankerkopf K157 0,36 bis 0,48 Nm/rad (eine Richtung sogar negativ) gegen
#: 3,2e13 Nm/rad auf der Diagonale, also 1e-14; das Blech mit Bohrung voll
#: gelagert (tests/test_frei_drehbar_streng) liegt weit ueber 1e-9.
ZWANG_ANTEIL = 1e-9
#: So viele Proben (rechte Seiten mit zufaelligen Vorzeichen auf den
#: Freiheitsgraden der geprueften Knoten) je Art (Verschiebung, Drehung).
ZWANG_PROBEN = 2
#: Unter diesem Anteil der groessten Antwort zaehlt eine Richtung am Knoten
#: nicht als frei (die Kopplung an andere freie Knoten streut darunter).
ZWANG_RANG = 1e-3

_ACHSEN = "xyz"


def _einheit(v) -> np.ndarray:
    v = np.asarray(v, float)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _zahl(x, stellen: int = 3) -> str:
    """Eine Zahl in einer Meldung: Dezimalkomma, ``stellen`` gueltige Ziffern,
    nie wissenschaftlich (Befund C7, 09.11.2026: bis dahin „1.2e+03 kN“)."""
    from .zahlen import zahl_text
    return zahl_text(x, stellen=stellen)


def _vektor_text(v) -> str:
    """„(0,50; 0,00; 0,87)“: Dezimalkomma, die Werte durch Strichpunkt getrennt."""
    return "(" + "; ".join(f"{float(x):.2f}".replace(".", ",") for x in v) + ")"


def bruchteil_text(x) -> str:
    """Ein sehr kleiner Anteil als Bruch statt mit Exponent (Befund C7,
    09.11.2026): „1/1 000 000 der steifsten Halterung“ statt „1.0e-06“. Ab
    einem Tausendstel als Dezimalzahl („0,0025“)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return str(x)
    if not np.isfinite(x) or x <= 0.0 or x >= 1e-3:
        return _zahl(x, 2)
    return "1/" + _zahl(1.0 / x, 2)


def _vek(v) -> str:
    """„(0,50; 0,00; 0,87)“ - das Vorzeichen so, dass die groesste Komponente positiv ist."""
    v = _einheit(v)
    if v[int(np.argmax(np.abs(v)))] < 0:
        v = -v
    w = np.round(v, 2) + 0.0                      # + 0.0 macht aus -0.0 eine Null
    return _vektor_text(w)


def _achse(v) -> str:
    """„z“, wenn v auf einer Koordinatenachse liegt, sonst der Vektor."""
    v = _einheit(v)
    i = int(np.argmax(np.abs(v)))
    return _ACHSEN[i] if abs(v[i]) >= 0.999 else _vek(v)


def _ebene(Q: np.ndarray) -> str:
    """Eine Ebene (zwei Richtungen als Spalten): „(x, y)“ oder „senkrecht zu (a, b, c)“."""
    n = _einheit(np.cross(Q[:, 0], Q[:, 1]))
    i = int(np.argmax(np.abs(n)))
    if abs(n[i]) >= 0.999:
        return "(" + ", ".join(a for j, a in enumerate(_ACHSEN) if j != i) + ")"
    return "senkrecht zu " + _vek(n)


def _unterraum(Q: np.ndarray) -> np.ndarray:
    """Orthonormale Basis (3 x d) der Spalten von Q ohne die Rauschrichtungen."""
    if Q.shape[1] == 0:
        return np.zeros((3, 0))
    u, s, _vt = np.linalg.svd(Q, full_matrices=False)
    d = int((s > 1e-6 * max(float(s[0]), 1e-300)).sum())
    return u[:, :d]


def _verschiebungstext(T: np.ndarray) -> str:
    d = T.shape[1]
    if d == 0:
        return ""
    if d == 1:
        return f"in Richtung {_achse(T[:, 0])} frei verschieblich"
    if d == 2:
        return f"in der Ebene {_ebene(T)} frei verschieblich"
    return "in allen drei Richtungen frei verschieblich"


def _drehtext(R: np.ndarray) -> str:
    d = R.shape[1]
    if d == 0:
        return ""
    if d == 1:
        return f"um {_achse(R[:, 0])} frei drehbar"
    if d == 2:
        n = _einheit(np.cross(R[:, 0], R[:, 1]))
        i = int(np.argmax(np.abs(n)))
        if abs(n[i]) >= 0.999:
            a, b = (x for j, x in enumerate(_ACHSEN) if j != i)
            return f"um {a} und {b} frei drehbar"
        return "um alle Achsen senkrecht zu " + _vek(n) + " frei drehbar"
    return "um alle Achsen frei drehbar"


def _bewegungstext(S: np.ndarray) -> str:
    """Die freien Bewegungen eines starren Bauteils in Worten.

    ``S`` (6 x r) ist eine orthonormale Basis der freien Bewegungen in den
    Unbekannten [t, L·omega] (Verschiebung des Schwerpunkts, Drehung mal
    Bezugslaenge). Eine Verschiebung ohne Drehanteil und eine Drehung um eine
    Achse durch den Schwerpunkt werden getrennt genannt; was sich so nicht
    trennen laesst (Drehung um eine Achse, die den Schwerpunkt nicht trifft),
    steht als gekoppelte Bewegung dabei.
    """
    r = S.shape[1]
    if r == 0:
        return ""
    # reine Verschiebungen: Linearkombinationen S c, deren Drehanteil null ist
    _u, s, vt = np.linalg.svd(S[3:, :], full_matrices=True)
    rang = int((s > 1e-3).sum())
    T = _unterraum(S[:3, :] @ vt[rang:].T) if rang < r else np.zeros((3, 0))
    # reine Drehungen: Verschiebungsanteil null
    _u, s, vt = np.linalg.svd(S[:3, :], full_matrices=True)
    rang = int((s > 1e-3).sum())
    R = _unterraum(S[3:, :] @ vt[rang:].T) if rang < r else np.zeros((3, 0))
    teile = [x for x in (_verschiebungstext(T), _drehtext(R)) if x]
    gekoppelt = r - T.shape[1] - R.shape[1]
    if gekoppelt > 0:
        teile.append(f"{gekoppelt} gekoppelte Bewegung{'en' if gekoppelt > 1 else ''} "
                     "(Drehung um eine Achse, die den Schwerpunkt nicht trifft)")
    return ", ".join(teile)


def _natuerlich(name: str) -> list:
    """Sortierschluessel, der „V2“ vor „V10“ stellt."""
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(name))]


def _namenstext(namen: list, mehr: str = "Bauteile") -> str:
    """„V1, V2, V3, V4, V5, V6 … V28 (28 Bauteile)“ - bis sechs Namen vollstaendig."""
    if len(namen) <= 6:
        return ", ".join(namen)
    return ", ".join(namen[:6]) + f" … {namen[-1]} ({len(namen)} {mehr})"


def _halter(model, knoten, cache: dict) -> list:
    """Was an diesen Knoten ein Lager oder eine Fuge ist - und was sie traegt.

    Gesagt wird nur, was im Modell steht: Kontaktpaare (Name, Reibung) und
    Lager (Art, Name, Reibung des Flaechenlagers).
    """
    from .contact import master_facets
    maske = np.zeros(int(model.nn), bool)
    maske[np.asarray(knoten, int)] = True
    aus: list = []

    def zahl(x) -> str:
        return f"{float(x):g}".replace(".", ",")

    for cp in getattr(model, "contact_pairs", None) or []:
        kn = cache.get(id(cp))
        if kn is None:
            teile = [int(k) for k in (cp.slave_nodes or [])]
            for f in master_facets(model, cp):
                teile.extend(int(k) for k in f)
            kn = cache[id(cp)] = np.unique(np.asarray(teile, int))
        kn = kn[(kn >= 0) & (kn < model.nn)]
        if kn.size and maske[kn].any():
            haften = bool(getattr(cp, "haften", False) or getattr(cp, "zug", False))
            wie = ("haftend" if haften else
                   f"Reibung μ = {zahl(cp.mu)}" if cp.mu else
                   "reibungsfrei: trägt nur senkrecht zur Fläche")
            aus.append(f"Fuge „{cp.name}“ ({wie})")
    for art, liste in (("Knotenlager", getattr(model, "supports", None) or []),
                       ("Linienlager", getattr(model, "line_supports", None) or []),
                       ("Flächenlager", getattr(model, "surface_supports", None) or [])):
        for s in liste:
            kn = [int(k) for k in (getattr(s, "nodes", None) or [getattr(s, "node", -1)])
                  if 0 <= int(k) < model.nn]
            if kn and maske[kn].any():
                mus = [float(getattr(b, "mu", 0.0) or 0.0)
                       for b in (getattr(s, "behaviour", None) or {}).values()]
                mu = max(mus) if mus else 0.0
                nm = str(getattr(s, "name", "") or "")
                aus.append(art + (f" „{nm}“" if nm else "")
                           + (f" (Reibung μ = {zahl(mu)})" if mu else ""))
    return list(dict.fromkeys(aus))


def zufallsantworten(model, fi, ls, zahl: int, seed: int = 20261008):
    """Die Antwort des vorhandenen Faktors auf ``zahl`` zufaellige rechte Seiten.

    Rueckgabe ``(zahl, nn, 6)``: je Lösung die Knotenverschiebungen und
    -verdrehungen; ``None``, wenn eine Lösung nicht endlich ist. Die rechten
    Seiten sind normalverteilt auf den Steifigkeitsfreiheitsgraden und null
    auf den Randzeilen (Hilfsfesselung, Kontaktbedingungen); gelesen wird nur,
    der Faktor bleibt, wie er ist.
    """
    nn, nf, n = int(model.nn), len(fi), int(ls.n)
    rng = np.random.default_rng(seed)
    A = np.zeros((zahl, nn, 6))
    for j in range(zahl):
        b = np.zeros(n)
        b[:nf] = rng.standard_normal(nf)
        x = np.asarray(ls._solve(b), float).ravel()
        if x.size < nf or not np.all(np.isfinite(x[:nf])):
            return None
        U = np.zeros(model.ndof)
        U[fi] = x[:nf]
        A[j] = U[:nn * 6].reshape(nn, 6)
    # gebundene Seitenmitten haben keine eigenen Unbekannten: u_m = (u_a + u_b)/2
    from . import assemble as asm
    bind = asm.mittelknoten_bindungen(model)
    if bind:
        t = np.asarray(bind, np.int64)
        for r in range(3):
            A[:, t[:, 0], r] = 0.5 * (A[:, t[:, 1], r] + A[:, t[:, 2], r])
    return A


def verstaerkte_knoten(a: np.ndarray) -> tuple:
    """Die Knoten im oberen Haufen der Antworten - ``(Maske, Abstand, Trennung)``.

    ``a`` ist der Betrag der Antwort je Knoten (ueber alle zufaelligen rechten
    Seiten). Getrennt wird im Logarithmus nach Otsu in zwei Haufen; die Maske
    ist nur belegt, wenn die Haufenmitten mindestens :data:`PIVOT_DEKADEN`
    Zehnerpotenzen auseinander liegen und die Trennung mindestens
    :data:`PIVOT_TRENNUNG` der Gesamtstreuung erklaert. ``Abstand`` und
    ``Trennung`` (0 ... 1) stehen immer da, auch bei leerer Maske - an ihnen
    laesst sich ablesen, wie weit ein gesundes Modell von der Schwelle liegt.
    """
    a = np.asarray(a, float)
    keine = np.zeros(a.shape, bool)
    pos = a > 0
    m = int(pos.sum())
    if m < 3:
        return keine, 0.0, 0.0
    v = np.sort(np.log10(a[pos]))
    c1, c2 = np.cumsum(v), np.cumsum(v * v)
    i = np.arange(m - 1)
    n0, n1 = i + 1, m - i - 1
    m0, m1 = c1[i] / n0, (c1[-1] - c1[i]) / n1
    innen = (c2[i] - n0 * m0 ** 2) + ((c2[-1] - c2[i]) - n1 * m1 ** 2)
    gesamt = c2[-1] - m * (c1[-1] / m) ** 2
    if gesamt <= 0:
        return keine, 0.0, 0.0
    b = int(np.argmin(innen))
    abstand = float(m1[b] - m0[b])
    trennung = 1.0 - float(innen[b]) / gesamt
    if abstand < PIVOT_DEKADEN or trennung < PIVOT_TRENNUNG:
        return keine, abstand, trennung
    return a > 10.0 ** (0.5 * (v[b] + v[b + 1])), abstand, trennung


def zwang_je_knoten(model, knoten) -> tuple:
    """Was die Knoten ``knoten`` durch eine **Zwangsbedingung** bindet und was
    nur durch eine **weiche Feder**: ``(zwang, feder)``, je ``{Knoten: [Namen]}``.

    Zwangsbedingung heisst: eine starre Kopplung (alle Steifigkeiten ``inf``;
    die starre Scheibe einer starren Flaeche, das Stabende am Volumen), ein
    starrer Koerper (RBE2/RBE3), eine Kopplung in der Kontaktfuge ohne endliche
    Feder. Eine Kopplung mit endlicher Steifigkeit, ein Federelement und ein
    Lager mit Feder sind weiche Federn - sie halten nur so weit, wie die Feder
    steif ist, und zaehlen nicht als Zwangsbedingung."""
    wollen = {int(k) for k in knoten}
    zwang: dict = {k: [] for k in wollen}
    feder: dict = {k: [] for k in wollen}

    def merke(ziel, n, name):
        if int(n) in wollen and name not in ziel[int(n)]:
            ziel[int(n)].append(name)
    for kp in (getattr(model, "kopplungen", None) or []):
        a, b = int(kp.node_a), int(kp.node_b)
        if a not in wollen and b not in wollen:
            continue
        steif = [float(s) for s in (kp.steifigkeiten or []) if float(s) != 0.0]
        starr = bool(steif) and all(np.isinf(s) for s in steif)
        name = str(getattr(kp, "gruppe", "") or "Kopplung").strip() or "Kopplung"
        for n in (a, b):
            merke(zwang if starr else feder, n, name if starr else name + " (endliche Steifigkeit)")
    for sk in (getattr(model, "starrkoerper", None) or []):
        glieder = [int(sk.master)] + [int(x) for x in (sk.slaves or [])]
        if wollen.isdisjoint(glieder):
            continue
        for n in glieder:
            merke(zwang, n, str(getattr(sk, "art", "RBE2")) + (f" {sk.name}" if getattr(sk, "name", "") else ""))
    for s in (getattr(model, "supports", None) or []):
        if int(s.node) in wollen:
            try:
                if any(s.dof_behaviour(d).typ == "spring" for d in range(6)):
                    merke(feder, s.node, "Federlager")
            except Exception:                  # noqa: BLE001 - fremdes Lager
                pass
    return {k: v for k, v in zwang.items() if v}, {k: v for k, v in feder.items() if v}


def last_je_knoten(model, knoten) -> dict:
    """Die groessten Beträge von Kraft und Moment an den Knoten ``knoten`` über
    alle Lastfälle: ``{Knoten: (F[3], M[3])}``; nur Knoten mit Last. (Eine
    Zwangsverformung braucht ein Lager und gehört nicht zu einem freien Knoten.)"""
    wollen = {int(k) for k in knoten}
    aus: dict = {}
    for lc in model.load_cases.values():
        for l in lc.nodal_loads:
            n = int(l.node)
            if n in wollen:
                F, M = aus.setdefault(n, (np.zeros(3), np.zeros(3)))
                w = np.abs(np.asarray(list(l.F) + [0.0] * 6, float)[:6])
                F[:] = np.maximum(F, w[:3])
                M[:] = np.maximum(M, w[3:])
    return aus


def stufe_freier_knoten(model, k: int, Vt, Vr, lasten: dict, zwang: dict, feder: dict,
                        numerisch=None) -> tuple:
    """Die Stufe der Meldung „Knoten k frei beweglich“: ``("INFORMATION", Halt)``
    oder ``("WARNUNG", Grund)``.

    **Information** nur, wenn (a) an der freien Bewegung weder Kraft noch Moment
    angreift - die Last (aus allen Lastfaellen) hat keinen Anteil in den freien
    Verschiebungs- und Drehrichtungen ``Vt``/``Vr`` - und (b) der Knoten ueber
    eine Zwangsbedingung gebunden ist, keine weiche Feder (:func:`zwang_je_knoten`).
    Der Gleichungsloeser hebt dort einen Pivot an; ohne Last und mit starr
    gebundenem Knoten bleibt die Rechnung eindeutig in allem, was zaehlt. Sonst
    **Warnung**: mit Last ginge sie ins Nichts, ohne Zwangsbedingung hielte den
    Knoten nur der angehobene Pivot, und eine weiche Feder haelt nur so weit,
    wie sie steif ist.

    Streng (Vorgabe des Anwenders vom 16.10.2026): „Information nur bei echter
    Zwangsbedingung“ - der Freiheitsgrad muss durch die Bedingung **bestimmt**
    sein, mit nicht verschwindender Steifigkeit, nicht nur durch einen
    angehobenen Pivot. ``numerisch``: das Mass dafuer (:func:`numerisch_gehalten`)
    - ein Eintrag (dict mit ``k_eff``, ``k_diag``) heisst nur numerisch gehalten,
    False heisst gemessen und bestimmt, "unbekannt" heisst nicht gemessen (dann im
    Zweifel Warnung). None (Vorgabe) rechnet wie bis zum 16.10.2026 mittags, fuer
    Aufrufe ohne Faktor."""
    F, M = lasten.get(int(k), (np.zeros(3), np.zeros(3)))
    kraft = float(np.linalg.norm(np.asarray(Vt).T @ F)) if np.asarray(Vt).shape[1] else 0.0
    moment = float(np.linalg.norm(np.asarray(Vr).T @ M)) if np.asarray(Vr).shape[1] else 0.0
    # Schranke relativ zur Last am Knoten (16.10.2026): eine gemessene Richtung
    # traegt Rundung (1e-6 einer senkrechten Last ist kein Anteil an ihr)
    s_F = 1e-9 + 1e-6 * float(np.linalg.norm(F))
    s_M = 1e-9 + 1e-6 * float(np.linalg.norm(M))
    last = ""
    if kraft > s_F or moment > s_M:
        last = "an der freien Bewegung greift " + (
            "ein Moment" if moment > s_M and kraft <= s_F else
            "eine Kraft" if kraft > s_F and moment <= s_M else "Kraft und Moment") + " an"
    if last and not isinstance(numerisch, dict):
        return "WARNUNG", last
    if isinstance(numerisch, dict):
        from .zahlen import zahl_text as _z
        wer = (" – die Zwangsbedingung " + ", ".join(zwang[int(k)]) + " bestimmt diese Bewegung nicht"
               if int(k) in zwang else "")
        einheit = str(numerisch.get("einheit") or ("Nm/rad" if np.asarray(Vr).shape[1] else "N/m"))
        k_eff = float(numerisch.get("k_eff", 0.0))
        return "WARNUNG", (f"nur numerisch gehalten (angehobener Pivot, Pivot-Regularisierung; wirksame "
                           f"Steifigkeit etwa {_z(k_eff, stellen=3) if k_eff > 0 else 'null oder negativ'} "
                           f"{einheit} gegen {_z(float(numerisch.get('k_diag', 0.0)), stellen=3)} {einheit} "
                           f"auf der Hauptdiagonale{wer})" + (f"; {last}" if last else ""))
    if int(k) in feder and int(k) not in zwang:
        return "WARNUNG", "nur eine weiche Feder bindet den Knoten (" + ", ".join(feder[int(k)]) + ")"
    if int(k) in zwang and numerisch == "unbekannt":
        return "WARNUNG", ("nur numerisch gehalten (angehobener Pivot; ob die Zwangsbedingung "
                           + ", ".join(zwang[int(k)]) + " die Bewegung bestimmt, ist nicht gemessen)")
    if int(k) in zwang:
        return "INFORMATION", ", ".join(zwang[int(k)])
    return "WARNUNG", "keine Zwangsbedingung bindet den Knoten"


def numerische_haltung(model, F, freie_teile, auto_gehalten=None):
    """Kraft und Moment, die nur **numerisch** gehalten werden (Vorgabe des
    Anwenders vom 16.10.2026: „Kraft bzw. Moment in numerischen Haltungen in die
    Gleichgewichtskontrolle aufnehmen“) - als Vektor ueber alle FHG.

    * Angehobener Pivot: je Eintrag von ``freie_teile`` (pivotbefund) mit freier
      Bewegung (``modus``) der Anteil der Last ``F``, der auf diese Bewegung
      faellt. An einer freien Bewegung gilt Φᵀ K = 0, also haelt Φᵀ F allein der
      angehobene Pivot. Am Knoten die Projektion von Kraft und Moment auf die
      freien Richtungen, am Bauteil die Projektion der Knotenkraefte auf seine
      freien Starrkoerperbewegungen. Information (echte Zwangsbedingung) traegt
      keinen Modus.
    * Automatisch gehaltene FHG (solver.auto_gehalten_abtrennen): die Last dort.
    * Die Mindesttangente der Plastizitaet (plastizitaet.H_TANGENTE) haelt keine
      Kraft im Ergebnis: sie wirkt nur in der Tangente, die inneren Kraefte des
      Residuums rechnen mit dem wahren Werkstoff.

    Rueckgabe (r, Zahl der Eintraege) oder (None, 0) ohne numerische Haltung."""
    if F is None:
        return None, 0
    Fv = np.asarray(F, float).ravel()
    r = np.zeros(Fv.size)
    n = 0
    nn = int(model.nn)
    X = np.asarray(model.nodes, float)
    for e in freie_teile or []:
        for md in e.get("modus") or []:
            if md.get("art") == "knoten":
                k = int(md["knoten"])
                if not 0 <= k < nn or NDOF * k + 6 > Fv.size:
                    continue
                for d0, schl in ((0, "Vt"), (3, "Vr")):
                    V = np.asarray(md.get(schl) or [], float).reshape(-1, 3)
                    if len(V):
                        f = Fv[NDOF * k + d0:NDOF * k + d0 + 3]
                        r[NDOF * k + d0:NDOF * k + d0 + 3] += V.T @ (V @ f)
                n += 1
            elif md.get("art") == "koerper":
                gr = str(md.get("gruppe", ""))
                kn = sorted({int(x) for el in model.elements if str(getattr(el, "group", "") or "") == gr
                             for x in el.nodes if 0 <= int(x) < nn})
                S = np.asarray(md.get("S") or [], float)
                if not kn or S.size == 0:
                    continue
                P = np.asarray(kn, np.int64)
                L = float(md.get("L", 1.0)) or 1.0
                rr = X[P] - np.asarray(md.get("mitte"), float)
                M = np.zeros((3 * len(P), 6))
                M[0::3, 0] = M[1::3, 1] = M[2::3, 2] = 1.0
                M[0::3, 4], M[0::3, 5] = rr[:, 2] / L, -rr[:, 1] / L
                M[1::3, 3], M[1::3, 5] = -rr[:, 2] / L, rr[:, 0] / L
                M[2::3, 3], M[2::3, 4] = rr[:, 1] / L, -rr[:, 0] / L
                Phi = M @ S.reshape(6, -1)
                idx = (NDOF * P[:, None] + np.arange(3)[None, :]).ravel()
                f = Fv[idx]
                c, *_ = np.linalg.lstsq(Phi.T @ Phi, Phi.T @ f, rcond=None)
                r[idx] += Phi @ c
                n += 1
    for a in auto_gehalten or []:
        i = NDOF * int(a["knoten"]) + int(a["fhg"])
        if 0 <= i < r.size:
            r[i] += float(a.get("last", 0.0))
            n += 1
    # Unter der Residuumschranke des Gleichungsloesers (1e-6 der Last) ist es
    # Rundung - eine gemessene Richtung streift eine senkrechte Last (am Blech mit
    # 50 kN senkrecht 0,5 mN, 1e-8)
    if not n or float(np.linalg.norm(r)) <= 1e-6 * max(float(np.linalg.norm(Fv)), 1e-300):
        return None, 0
    return r, n


def zwangsknoten(model) -> list:
    """Die Knoten, die eine Zwangsbedingung bindet und an denen kein Element eine
    Drehung haelt (16.10.2026): der Kopf einer starren Scheibe oder eines starren
    Koerpers (Master), der Knoten a einer starren Kopplung - mit nur
    Fachwerkstaeben, Seilen oder gar keinem Element. Fuer sie misst
    :func:`numerisch_gehalten`, ob die Bedingung sie bestimmt."""
    kand = set()
    for kp in (getattr(model, "kopplungen", None) or []):
        steif = [float(x) for x in (kp.steifigkeiten or []) if float(x) != 0.0]
        if steif and all(np.isinf(x) for x in steif):
            kand.add(int(kp.node_a))
    for sk in (getattr(model, "starrkoerper", None) or []):
        kand.add(int(sk.master))
    nn = int(model.nn)
    kand = {k for k in kand if 0 <= k < nn}
    if not kand:
        return []
    dreh = set()
    for e in model.elements:
        if e.typ in ("truss", "seil"):
            continue
        for n in e.nodes:
            if int(n) in kand:
                dreh.add(int(n))
    return sorted(kand - dreh)


def numerisch_gehalten(model, fi, ls, K, knoten, seed: int = 20261016) -> dict:
    """Welche Freiheitsgrade der ``knoten`` haelt nur der angehobene Pivot?
    (Vorgabe des Anwenders vom 16.10.2026, „frei drehbar“ streng.)

    Je Art (Verschiebung, Drehung) :data:`ZWANG_PROBEN` Loesungen ueber den
    **vorhandenen** Faktor ``ls`` mit Einheitslasten zufaelligen Vorzeichens auf
    den freien Freiheitsgraden aller Knoten zugleich; die groesste Antwort am
    Freiheitsgrad ist seine Nachgiebigkeit (die Kopplung an andere Knoten streut
    darunter), ihr Kehrwert die wirksame Steifigkeit k_eff. Nur numerisch
    gehalten, wenn k_eff < :data:`ZWANG_ANTEIL` mal der Hauptdiagonale von ``K``.
    Nichts wird gelagert oder neu faktorisiert.

    Rueckgabe {Knoten: {"Vt", "Vr" (3 x d, die nur numerisch gehaltenen
    Richtungen), "k_eff", "k_diag" (der kleinste Anteil), "dofs"}} - nur Knoten
    mit mindestens einer solchen Richtung. Ein leeres Woerterbuch auch dann,
    wenn die Probe nicht endlich war."""
    if K is None or not knoten:
        return {}
    nf, n = len(fi), int(ls.n)
    pos = np.full(model.ndof, -1, np.int64)
    pos[np.asarray(fi, np.int64)] = np.arange(nf)
    diag = np.abs(np.asarray(K.diagonal(), float).ravel())
    rng = np.random.default_rng(seed)
    knoten = [int(k) for k in knoten]
    antwort: dict = {}                          # FHG -> [Antwort je Probe]
    for d0 in (0, 3):
        dofs = np.array([NDOF * k + d for k in knoten for d in range(d0, d0 + 3)
                         if pos[NDOF * k + d] >= 0], np.int64)
        if not dofs.size:
            continue
        for _j in range(ZWANG_PROBEN):
            b = np.zeros(n)
            b[pos[dofs]] = rng.choice((-1.0, 1.0), size=dofs.size)
            x = np.asarray(ls._solve(b), float).ravel()
            if x.size < nf or not np.all(np.isfinite(x[:nf])):
                return {}
            for d, v in zip(dofs.tolist(), x[pos[dofs]].tolist()):
                antwort.setdefault(d, []).append(v)
    aus: dict = {}
    for k in knoten:
        e = {}
        for d0, schl in ((0, "Vt"), (3, "Vr")):
            R = np.array([antwort.get(NDOF * k + d, [0.0] * ZWANG_PROBEN) for d in range(d0, d0 + 3)], float)
            c = np.abs(R).max(axis=1)
            kd = diag[NDOF * k + d0:NDOF * k + d0 + 3]
            num = [(d0 + i) for i in range(3)
                   if c[i] > 0 and kd[i] > 0 and 1.0 / c[i] < ZWANG_ANTEIL * kd[i]]
            if not num:
                e[schl] = np.zeros((3, 0))
                continue
            u, sv, _vt = np.linalg.svd(R, full_matrices=False)
            r = int((sv > ZWANG_RANG * max(float(sv[0]), 1e-300)).sum())
            e[schl] = u[:, :max(r, 1)]
            anteil = [(1.0 / c[d - d0]) / kd[d - d0] for d in num]
            i = int(np.argmin(anteil))
            if "k_eff" not in e or anteil[i] < e["_anteil"]:
                e.update({"k_eff": float(1.0 / c[num[i] - d0]), "k_diag": float(kd[num[i] - d0]),
                          "_anteil": float(anteil[i]), "einheit": "Nm/rad" if d0 == 3 else "N/m"})
            e.setdefault("dofs", []).extend(NDOF * k + d for d in num)
        if e.get("dofs"):
            e.pop("_anteil", None)
            aus[k] = e
    return aus


def pivotbefund(model, fi, ls, gestoert: int, seed: int = 20261008, K=None) -> tuple:
    """Stufe 3: welche Teile hat die Faktorisierung freigelassen?

    PARDISO hebt ein Pivot, das null wuerde, auf einen winzigen Wert an und
    zaehlt es (iparm(14)) - das System bleibt loesbar, jede Richtung, die die
    Matrix nicht haelt, aber wird bei jeder Loesung um etwa 1/(1e-13·‖A‖)
    verstaerkt. Die Zahl sagt, **dass** etwas frei ist; wo, sagt eine Handvoll
    zufaelliger rechter Seiten ueber den vorhandenen Faktor: die Antwort ist
    dort um viele Zehnerpotenzen groesser als irgendwo sonst. Gemessen am
    Drehlager (Entwurf, 39 gestoerte Pivots, sechs Loesungen, 12 s): der
    groesste Betrag stand 8e8-mal ueber dem Median, auf den Lastverteilplatten
    V1-V28 zu 1 - 7e-11 eine Starrkoerperbewegung.

    Die Vorabsuche (:func:`restfreiheiten`) sieht das nicht: sie zaehlt Reibung
    und ein Flaechenlager mit Reibung als Halt, und gleitet ein Teil, traegt
    Reibung in der Gleitrichtung keine Steifigkeit bei. Hier steht die
    Messung an der Matrix selbst.

    Es wird nichts gelagert und nichts an der Rechnung geaendert: gelesen wird
    mit dem Faktor, der schon da ist; die rechten Seiten sind null ausser auf
    den Steifigkeitsfreiheitsgraden. Rueckgabe ``(Liste, Suche)``; ``Liste``
    nennt je Gruppe gleich bewegter Teile ``art`` (``koerper`` | ``stab`` |
    ``knoten``), ``namen``, ``bewegung``, ``haltung``, ``text``; ``Suche``
    haelt Zahlen fuer das Protokoll.
    """
    import itertools
    nn = int(model.nn)
    zahl = int(min(PIVOT_LOESUNGEN_MAX, max(2, gestoert + 1)))
    suche = {"gestoerte_pivots": int(gestoert), "zusatzloesungen": zahl}
    A = zufallsantworten(model, fi, ls, zahl, seed)
    if A is None:
        suche["grund"] = "die Zufallslösung war nicht endlich"
        return [], suche

    # ---- welche Knoten sind verstaerkt? --------------------------------
    g_t, d_t, tr_t = verstaerkte_knoten(np.sqrt((A[:, :, :3] ** 2).sum(axis=(0, 2))))
    g_r, d_r, tr_r = verstaerkte_knoten(np.sqrt((A[:, :, 3:] ** 2).sum(axis=(0, 2))))
    gross = g_t | g_r
    suche["knoten_verstaerkt"] = int(gross.sum())
    suche["abstand_dekaden"] = float(max(d_t, d_r))
    # „Frei drehbar“ streng (16.10.2026): an den Knoten, die eine Zwangsbedingung
    # bindet, wird gemessen, ob die Bedingung sie bestimmt oder nur der angehobene
    # Pivot (numerisch_gehalten) - auch wenn die Antworten keinen Haufen bilden (am
    # Drehlager-Entwurf mit 357 gestoerten Pivots: kein Knoten verstaerkt, der
    # Ankerkopf K157 trotzdem mit 0,4 Nm/rad nur numerisch gehalten)
    zk = set(zwangsknoten(model))
    if gross.any():
        zw_g, _fe_g = zwang_je_knoten(model, np.flatnonzero(gross).tolist())
        zk |= set(zw_g)
    num: dict = {}
    gemessen = K is not None
    if gemessen and zk:
        num = numerisch_gehalten(model, fi, ls, K, sorted(zk))
        suche["zwangsknoten"] = len(zk)
        suche["numerisch_gehalten"] = len(num)
    if not gross.any() and not num:
        return [], suche

    # ---- Bauteile der verstaerkten Knoten ------------------------------
    els = model.elements
    ne = len(els)
    laengen = np.fromiter((len(e.nodes) for e in els), int, count=ne)
    flach = np.fromiter(itertools.chain.from_iterable(e.nodes for e in els), int,
                        count=int(laengen.sum()))
    elem = np.repeat(np.arange(ne), laengen)
    ok = (flach >= 0) & (flach < nn)
    flach, elem = flach[ok], elem[ok]
    codes: dict = {}
    code = np.empty(ne, np.int64)
    for i, e in enumerate(els):
        code[i] = codes.setdefault(str(getattr(e, "group", "") or ""), len(codes))
    namen_von_code = list(codes)
    from .elemente import STAB_TYPEN
    ist_stab = np.fromiter((e.typ in STAB_TYPEN for e in els), bool, count=ne)
    stab_name: dict = {}
    for mname, mem in (getattr(model, "members", None) or {}).items():
        for ei in mem.elements:
            stab_name[int(ei)] = str(mname)
    cache: dict = {}
    roh: list = []                  # (art, bewegung, namen, knoten, halter)
    im_koerper = np.zeros(nn, bool)
    fg = code[elem]
    treffer = np.unique(fg[gross[flach]])
    for c in treffer:
        gruppe = namen_von_code[int(c)]
        sel = fg == c
        P = np.unique(flach[sel])
        anteil = float(gross[P].mean())
        stabig = bool(ist_stab[elem[sel]].mean() > 0.5)
        if anteil < PIVOT_KOERPERANTEIL or stabig:
            continue                          # einzelne Knoten: unten
        X = model.nodes[P]
        mitte = X.mean(axis=0)
        L = 0.5 * float(np.linalg.norm(X.max(axis=0) - X.min(axis=0))) or 1.0
        r = X - mitte
        M = np.zeros((3 * len(P), 6))
        M[0::3, 0] = M[1::3, 1] = M[2::3, 2] = 1.0
        # u = t + omega x r;  Unbekannte [t, L·omega]
        M[0::3, 4], M[0::3, 5] = r[:, 2] / L, -r[:, 1] / L
        M[1::3, 3], M[1::3, 5] = -r[:, 2] / L, r[:, 0] / L
        M[2::3, 3], M[2::3, 4] = r[:, 1] / L, -r[:, 0] / L
        Y = A[:, P, :3].reshape(zahl, -1).T
        p, *_ = np.linalg.lstsq(M, Y, rcond=None)
        ny = np.linalg.norm(Y, axis=0)
        guete = 1.0 - np.linalg.norm(M @ p - Y, axis=0) / np.where(ny > 0, ny, 1.0)
        name = gruppe or "Bauteil ohne Namen"
        im_koerper[P] = True
        halter = _halter(model, P, cache)
        bew = ""
        if float(guete.min()) >= PIVOT_STARR:
            u_, s_, _v = np.linalg.svd(p, full_matrices=False)
            rang = int((s_ > PIVOT_RANG * s_[0]).sum())
            bew = _bewegungstext(u_[:, :rang]) if rang else ""
        if not bew:
            bew = (f"ohne Steifigkeit verformbar (kein Starrkörper; {int(gross[P].sum())} von "
                   f"{len(P)} Knoten verstärkt)")
        modus = []
        if float(guete.min()) >= PIVOT_STARR and bew and not bew.startswith("ohne Steifigkeit"):
            # die freie Starrkoerperbewegung fuer die Gleichgewichtskontrolle
            # (numerische_haltung): Kraft und Moment, die nur der Pivot haelt
            modus = [{"art": "koerper", "gruppe": gruppe, "mitte": [float(c) for c in mitte], "L": float(L),
                      "S": u_[:, :rang].tolist()}]
        roh.append(("koerper", bew, [name], [int(k) for k in P[gross[P]][:6]], halter,
                    "WARNUNG", "", modus))

    # ---- einzelne Knoten (Staebe, Knoten ohne Bauteil) -----------------
    # dazu die Zwangsknoten, die nur numerisch gehalten sind (16.10.2026)
    rest = np.flatnonzero(gross & ~im_koerper)
    nur_num = sorted(k for k in num if not gross[k] and not im_koerper[k])
    if rest.size or nur_num:
        alle = rest.tolist() + nur_num
        in_rest = np.zeros(nn, bool)
        in_rest[alle] = True
        lasten = last_je_knoten(model, alle)
        zwang, feder = zwang_je_knoten(model, alle)
        sel = in_rest[flach]
        je_knoten: dict = {}
        for k, e in zip(flach[sel].tolist(), elem[sel].tolist()):
            je_knoten.setdefault(k, []).append(e)
        for k in alle:
            es = je_knoten.get(k, [])
            teile = []
            if gross[k]:
                Vt = _unterraum(A[:, k, :3].T) if g_t[k] else np.zeros((3, 0))
                Vr = _unterraum(A[:, k, 3:].T) if g_r[k] else np.zeros((3, 0))
            else:
                Vt, Vr = num[k]["Vt"], num[k]["Vr"]
            # gemessen: nur numerisch gehalten (Eintrag), bestimmt (False); ohne
            # Messung im Zweifel numerisch ("unbekannt")
            nmess = num.get(k, False) if (gemessen and k in zk) else ("unbekannt" if k in zwang else None)
            achse = None
            for e in es:
                if ist_stab[e] and len(els[e].nodes) >= 2:
                    q = model.nodes[int(els[e].nodes[-1])] - model.nodes[int(els[e].nodes[0])]
                    if float(np.linalg.norm(q)) > 0:
                        achse = _einheit(q)
                        break
            if Vt.shape[1]:
                if (achse is not None and Vt.shape[1] == 2
                        and abs(float(_einheit(np.cross(Vt[:, 0], Vt[:, 1])) @ achse)) >= 0.999):
                    teile.append(f"quer zur Stabachse {_ebene(Vt)} frei verschieblich")
                elif (achse is not None and Vt.shape[1] == 1
                        and abs(float(Vt[:, 0] @ achse)) <= 0.01):
                    teile.append(f"quer zur Stabachse in Richtung {_achse(Vt[:, 0])} "
                                 "frei verschieblich")
                else:
                    teile.append(_verschiebungstext(Vt))
            if Vr.shape[1]:
                teile.append(_drehtext(Vr))
            bew = ", ".join(teile) or "ohne Steifigkeit verformbar"
            mnamen = sorted({stab_name[e] for e in es if e in stab_name}, key=_natuerlich)
            if mnamen:
                art, namen = "stab", mnamen
            else:
                gr = sorted({namen_von_code[int(code[e])] or "Bauteil ohne Namen" for e in es},
                            key=_natuerlich)
                art, namen = "knoten", (gr or ["Knoten ohne Element"])
            stufe, halt = stufe_freier_knoten(model, k, Vt, Vr, lasten, zwang, feder, numerisch=nmess)
            modus = ([{"art": "knoten", "knoten": int(k), "Vt": np.asarray(Vt).T.tolist(),
                       "Vr": np.asarray(Vr).T.tolist()}] if stufe != "INFORMATION" else [])
            roh.append((art, bew, namen, [k], _halter(model, np.array([k]), cache), stufe, halt, modus))

    # ---- gleich bewegte Teile zu einer Zeile -----------------------------
    gruppen: dict = {}
    for art, bew, namen, knoten, halter, stufe, halt, modus in roh:
        g = gruppen.setdefault((art, bew, stufe), {"namen": [], "knoten": [], "halter": [],
                                                   "grund": [], "modus": []})
        g["modus"].extend(modus)
        for nm in namen:
            if nm not in g["namen"]:
                g["namen"].append(nm)
        g["knoten"].extend(knoten)
        for h in halter:
            if h not in g["halter"]:
                g["halter"].append(h)
        if halt and halt not in g["grund"]:
            g["grund"].append(halt)
    liste = []
    for (art, bew, stufe), g in gruppen.items():
        namen = sorted(g["namen"], key=_natuerlich)
        kn = sorted(set(g["knoten"]))
        if art == "koerper":
            wer = _namenstext(namen)
            bitte = "bitte lagern (Lager, Feder oder Reibung in diesen Richtungen)"
        else:
            wer = (_namenstext(namen, "Stäbe") + ": Knoten "
                   + ", ".join(f"K{k}" for k in kn[:6])
                   + (f" … ({len(kn)} Knoten)" if len(kn) > 6 else ""))
            bitte = "bitte lagern (Lager, Feder oder Kopplung in diesen Richtungen)"
        haltung = "; ".join(g["halter"]) if g["halter"] else "kein Lager und keine Fuge"
        if stufe == "INFORMATION":
            # Seit 16.10.2026: keine Last und kein Moment an dieser Bewegung, und
            # der Knoten ist ueber eine Zwangsbedingung gebunden - dann ist es
            # nichts, was der Anwender lagern muesste (Kopf der Anker S1-S16,
            # Drehung um die Stabachse an der starren Scheibe)
            haltung = "Zwangsbedingung: " + "; ".join(g["grund"])
            text = (f"{wer}: {bew} - Information: über eine {haltung} an das Bauteil gebunden, "
                    "das diese Bewegung bestimmt; weder Kraft noch Moment greift an dieser "
                    "Bewegung an, nichts zu lagern")
        else:
            text = f"{wer}: {bew} - gehalten nur durch: {haltung}; {bitte}"
            if art != "koerper" and g["grund"]:
                text += " (" + "; ".join(g["grund"]) + ")"
        liste.append({"art": art, "namen": namen, "anzahl": len(namen),
                      "knoten_anzahl": len(kn), "knoten": [int(k) for k in kn[:8]],
                      "bewegung": bew, "haltung": haltung, "text": text, "stufe": stufe,
                      # die freien Bewegungen fuer die Gleichgewichtskontrolle (16.10.2026)
                      **({"modus": g["modus"]} if g["modus"] else {})})
    liste.sort(key=lambda e: (-e["anzahl"], _natuerlich(e["namen"][0])))
    suche["teile"] = len(liste)
    return liste, suche
