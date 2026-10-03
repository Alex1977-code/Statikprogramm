"""Knoten der Konstruktion und Knoten des FE-Netzes.

Ein Kriterium fuer alle, die „Knoten“ zeigen: den Modellbaum (Zweig „Knoten“
und die Zaehlzeile „FE-Netz → Netzknoten“, gui.design), die Ansicht (Schalter
„Knoten“ und „Netz → Netzknoten“, gui.viewport) und die Uebersicht des Zweigs
(Teilpaket 8b). Das Modul braucht keine Oberflaeche und kein pyvista; ein
reiner Baumtest zahlt den Import der Ansicht nicht.

**Kriterium** (Teilpaket 8c, Nachbesserung 03.10.2026). Ein Knoten gehoert
zur Konstruktion, wenn

1. er an keinem Element haengt, das das Vernetzen einer Flaeche oder eines
   Koerpers erzeugt hat (``Flaeche.elemente``, ``Volumenkoerper.elemente``) -
   frei gesetzte Knoten, Knoten direkt gesetzter Elemente und alle Knoten von
   Stabketten; oder
2. ein Modellobjekt ausser einem Netzelement auf ihn verweist: eine Linie,
   eine Ecke oder ein integrierter Knoten einer Flaeche, ein anderes Element
   (Stab, Feder, Grenzschicht, direkt gesetzte Schale), ein Knotenlager, ein
   Linien- oder Flaechenlager, das allein ueber Knoten gegeben ist, eine
   Knotenlast oder Zwangsverformung, ein einseitiges Lager, ein Spaltelement,
   eine Punktmasse, ein Daempfer, ein starrer Koerper (Master und Slaves),
   eine Lasteinleitung oder eine Verformungsgrenze.

Alle uebrigen Knoten sind **Netzknoten**: sie haengen nur an Netzelementen
und an Objekten, die das Vernetzen selbst setzt oder die ganze Flaechen von
Knoten sammeln - Kopplungen und Kontaktpaare der Kontaktfugen, getrennte
Knoten, Linien- und Flaechenlager mit Geometriebezug (sie bekommen ihre
Knoten nach jedem Vernetzen neu, supports.lager_auf_netz), Subsysteme und
Layer. Dieselbe Liste der Verweise fuehrt ``Model.netzknoten_loeschen``;
dort schuetzt sie Knoten vor dem Loeschen, hier ohne die erzeugten Objekte.

**Warum Stabketten ganz zur Konstruktion zaehlen.** Bis zum 03.10.2026 galten
die Zwischenknoten jedes Stabs aus mehr als einem Element als Netzknoten
(„Zwischenknoten eines geteilten Stabzugs“). Das Teilen hinterlaesst im
Modell aber keine Spur: ``mesher.line_of_beams`` legt Knoten und Elemente
an wie ein Anwender, ``Member`` kennt keine Teilung, und ein Stab, den
„Stäbe automatisch erkennen“ aus selbst gesetzten Elementen bildet, sieht
genauso aus. Am Beispiel „frame“ schrumpfte der Zweig „Knoten“ damit nach
dem Erkennen von 17 auf 4 Knoten. Ohne verlaessliches Merkmal gilt darum:
lieber ein Zwischenknoten zu viel im Zweig als ein selbst gesetzter Knoten
zu wenig. Ebenso fehlten Knoten mit Knotenlast, Punktmasse, Daempfer,
einseitigem Lager, Spaltelement, Lasteinleitung, Slave eines starren Koerpers
oder Federende, wenn sie an einem Netz lagen (Gegenpruefung 03.10.2026, am
Beispiel „contact“ der einzige Lastknoten K10).
"""
from __future__ import annotations

import itertools

import numpy as np

#: id(Modell) -> (Netzstand, Netzelemente, Knoten an Netzelementen, Knoten an
#: anderen Elementen). Zwei
#: Modelle, damit sich das Modell und seine Stellungskopie (Baum und Ansicht
#: fragen beide) nicht gegenseitig verdraengen.
_ZWISCHENSPEICHER: dict = {}
ZWISCHENSPEICHER_MODELLE = 2


def _netzstand(model) -> tuple:
    """Woran sich die Netzteile aendern: Element- und Knotenzahl, erstes und
    letztes Element, Zahl der Flaechen und Koerper und ihrer Elemente. Billig
    (keine Schleife ueber die Elemente)."""
    ne = len(model.elements)
    teile = list((getattr(model, "flaechen", None) or {}).values()) \
        + list((getattr(model, "koerper", None) or {}).values())
    return (ne, int(model.nn), len(teile), sum(len(x.elemente or []) for x in teile),
            tuple(int(i) for i in model.elements[0].nodes) if ne else (),
            tuple(int(i) for i in model.elements[-1].nodes) if ne else ())


def netz_teile(model) -> tuple:
    """(Netzelemente, Knoten an Netzelementen, Knoten an anderen Elementen)
    als Masken ueber Elemente und Knoten. Netzelemente sind die Elemente
    einer Flaeche oder eines Koerpers.

    Einmal je Netzstand gerechnet und fuer zwei Modelle gehalten: am
    Drehlager laufen die Listen ueber 433 072 Elemente, das darf nicht bei
    jedem Bild und jedem Aufbau des Baums geschehen. Ebenso die Knoten der
    anderen Elemente: ein Modell aus vielen direkt gesetzten Elementen mit
    einer vernetzten Flaeche liefe sonst bei jedem Bild ueber alle."""
    stand = _netzstand(model)
    schluessel = id(model)
    treffer = _ZWISCHENSPEICHER.get(schluessel)
    if treffer is not None and treffer[0] == stand:
        _ZWISCHENSPEICHER[schluessel] = _ZWISCHENSPEICHER.pop(schluessel)   # zuletzt benutzt
        return treffer[1], treffer[2], treffer[3]
    ne, nn = len(model.elements), int(model.nn)
    netz_el = np.zeros(ne, bool)
    im_netz = np.zeros(nn, bool)
    teile = list((getattr(model, "flaechen", None) or {}).values()) \
        + list((getattr(model, "koerper", None) or {}).values())
    for x in teile:
        idx = np.fromiter((int(e) for e in (x.elemente or [])), int)
        netz_el[idx[(idx >= 0) & (idx < ne)]] = True
    an_anderen = np.zeros(nn, bool)
    if netz_el.any() and nn:
        flach = np.fromiter(itertools.chain.from_iterable(
            model.elements[i].nodes for i in np.flatnonzero(netz_el)), int)
        im_netz[flach[(flach >= 0) & (flach < nn)]] = True
        andere = np.flatnonzero(~netz_el)
        if len(andere):
            flach = np.fromiter(itertools.chain.from_iterable(
                model.elements[i].nodes for i in andere), int)
            an_anderen[flach[(flach >= 0) & (flach < nn)]] = True
    _ZWISCHENSPEICHER.pop(schluessel, None)
    while len(_ZWISCHENSPEICHER) >= ZWISCHENSPEICHER_MODELLE:
        _ZWISCHENSPEICHER.pop(next(iter(_ZWISCHENSPEICHER)))
    _ZWISCHENSPEICHER[schluessel] = (stand, netz_el, im_netz, an_anderen)
    return netz_el, im_netz, an_anderen


def bezogene_knoten(model) -> np.ndarray:
    """Maske der Knoten, auf die ein Modellobjekt ausser einem Netzelement
    verweist (Punkt 2 des Kriteriums). Die Knoten der anderen Elemente kommen
    aus :func:`netz_teile`; die uebrigen Objekte sind wenige (Linien, Lager,
    Lasten …) und werden je Aufruf gesammelt."""
    nn = int(model.nn)
    bez = np.zeros(nn, bool)
    if not nn:
        return bez
    # alles in eine Liste und einmal nach numpy: am Drehlager sind es gut
    # 6 000 kleine Folgen (Linien, Flaechenecken), je ein numpy-Aufruf kostete
    # 63 ms je Aufbau (gemessen 03.10.2026)
    sammel: list = []
    merke = sammel.extend

    bez |= netz_teile(model)[2]
    for ln in (getattr(model, "lines", None) or {}).values():
        merke(ln.nodes or [])
    for f in (getattr(model, "flaechen", None) or {}).values():
        merke(getattr(f, "ecken", None) or [])
        merke(getattr(f, "integrierte_knoten", None) or [])
    merke(s.node for s in (getattr(model, "supports", None) or []))
    for x in (getattr(model, "line_supports", None) or []):
        if not (getattr(x, "linien", None) or []):
            merke(x.nodes or [])
    for x in (getattr(model, "surface_supports", None) or []):
        if not (getattr(x, "flaechen", None) or []):
            merke(x.nodes or [])
    for lc in (getattr(model, "load_cases", None) or {}).values():
        merke(l.node for l in (getattr(lc, "nodal_loads", None) or []))
        merke(z.node for z in (getattr(lc, "zwangsverformungen", None) or []))
    merke(c.node for c in (getattr(model, "contact_supports", None) or []))
    for g in (getattr(model, "gap_elements", None) or []):
        merke((g.node_a, g.node_b))
    merke(pm.node for pm in (getattr(model, "punktmassen", None) or []))
    for d in (getattr(model, "daempfer", None) or []):
        merke((d.node_a, d.node_b))
    for sk in (getattr(model, "starrkoerper", None) or []):
        merke([sk.master] + list(sk.slaves or []))
    merke(x.knoten for x in (getattr(model, "lasteinleitungen", None) or {}).values())
    for x in (getattr(model, "verformungsgrenzen", None) or {}).values():
        merke(getattr(x, "knoten", None) or [])
    if sammel:
        a = np.fromiter((int(n) for n in sammel if n is not None), int, count=-1)
        bez[a[(a >= 0) & (a < nn)]] = True
    return bez


def netzknoten_maske(model) -> np.ndarray:
    """True fuer jeden Knoten, der **nur** zum FE-Netz gehoert (Kriterium
    oben). Ein Modell ohne Flaechen- und Koerpernetz hat keine Netzknoten."""
    im_netz = netz_teile(model)[1]
    if not im_netz.any():
        return im_netz.copy()
    return im_netz & ~bezogene_knoten(model)


def konstruktionsknoten(model) -> np.ndarray:
    """Die Nummern der Konstruktionsknoten, aufsteigend - der Inhalt des
    Zweigs „Knoten“ im Modellbaum und der Knotenpunkte der Ansicht."""
    return np.flatnonzero(~netzknoten_maske(model))
