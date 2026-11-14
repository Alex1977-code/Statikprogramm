"""Gemeinsame Hilfen der Exporter."""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..model import Model
from .. import elemente as EL


def say(log: Optional[list], msg: str) -> None:
    if log is not None:
        log.append(msg)


def warn(log: Optional[list], msg: str) -> None:
    """Eine Warnung ins Protokoll des Exports - wie bei den Importern
    (importers/_common.warn): was das Zielformat nicht darstellen kann, steht
    hier, statt still zu fehlen oder verfaelscht hinauszugehen."""
    say(log, "WARNUNG: " + msg)


# --------------------------------------------------------------------------
# Was ein Format nicht traegt, steht nach dem Export als Hinweis mit Anzahl da
# (Befunde B2 bis B5 der Pruefagenten, 09.11.2026: bis dahin fielen Gelenke,
# Fachwerkstaebe, Linien- und Flaechenlager, Stab- und Flaechenlasten beim
# Export ohne ein Wort weg).
# --------------------------------------------------------------------------
def anzahl(n: int, einzahl: str, mehrzahl: str = "") -> str:
    """„1 Stabendgelenk“, „4 Stabendgelenke“."""
    return f"{int(n)} {einzahl if int(n) == 1 else (mehrzahl or einzahl)}"


def gelenkenden(model: Model) -> list[tuple[int, int]]:
    """(Element, Ende 0|1) jedes Stabendes mit einem Gelenk oder einer
    Gelenkfeder (Element.hinges, Element.hinge_springs: lokale FHG 0..11)."""
    enden = set()
    for i, e in enumerate(model.elements):
        for d in getattr(e, "hinges", None) or []:
            enden.add((i, int(d) // 6))
        for eintrag in getattr(e, "hinge_springs", None) or []:
            enden.add((i, int(eintrag[0]) // 6))
    return sorted(enden)


def lager_nicht_starr(model: Model) -> list[int]:
    """Indizes der Knotenlager, die mehr sind als „diese FHG starr gehalten“:
    Feder, Ausfall, Schlupf, Reibung, Grenzkraft oder vorgegebene
    Verschiebung."""
    aus = []
    for k, s in enumerate(model.supports):
        feder = any(s.dof_behaviour(d).typ == "spring" for d in range(6))
        if feder or s.nonlinear or any(float(v) for v in (s.values or [])):
            aus.append(k)
    return aus


def lastzahl(model: Model, liste: str, nur_eigene: bool = False) -> int:
    """Zahl der Lasten einer Liste (``beam_loads``, ``face_loads`` ...) ueber
    alle Lastfaelle."""
    n = 0
    for lc in model.load_cases.values():
        lasten = getattr(lc, liste, None) or []
        n += sum(1 for l in lasten if not (nur_eigene and getattr(l, "_geo", False)))
    return n


def nicht_uebertragen(log: Optional[list], fmt: str, teile: list) -> None:
    """Der eine Hinweis am Ende jedes Exports: was im Modell steht und nicht
    in der Datei. ``teile``: [(Anzahl, Einzahl, Mehrzahl)] oder fertige
    Texte; Eintraege mit Anzahl 0 fallen weg. Ohne Eintrag kein Hinweis."""
    worte = []
    for t in teile:
        if isinstance(t, str):
            if t:
                worte.append(t)
        elif t and int(t[0]) > 0:
            worte.append(anzahl(*t))
    if worte:
        warn(log, f"{fmt}: nicht übertragen: " + ", ".join(worte) + ".")


def je_art(model: Model, idx) -> str:
    """Art und Anzahl der Elemente ``idx`` als Text: „ebene3: 1, ebene4: 2“."""
    zahl: dict[str, int] = {}
    for i in idx:
        t = model.elements[int(i)].typ
        zahl[t] = zahl.get(t, 0) + 1
    return ", ".join(f"{t}: {n}" for t, n in sorted(zahl.items()))


def elementhinweis(model: Model, idx, einzahl: str, mehrzahl: str, zusatz: str,
                   zusatz_mehrzahl: str = "") -> str:
    """Ein Eintrag fuer :func:`nicht_uebertragen`, der Anzahl und Art der
    Elemente ``idx`` nennt: „2 ebene Elemente (ebene3: 1, ebene4: 1) <zusatz>“.
    Ohne Elemente "" (Befund 17 der Pruefagenten, 11.11.2026: tetp2 bis tetp4
    und ebene3 bis ebene8 fehlten in Nastran, Abaqus, IFC und DXF ohne ein
    Wort)."""
    idx = list(idx)
    if not idx:
        return ""
    z = zusatz if len(idx) == 1 else (zusatz_mehrzahl or zusatz)
    return f"{anzahl(len(idx), einzahl, mehrzahl)} ({je_art(model, idx)}) {z}"


def von_weiteres(e) -> bool:
    """Elemente, die :func:`weiteres` schon zaehlt (Feder, Grenzschicht)."""
    return e.typ == "feder" or e.typ.startswith("grenzschicht")


def weiteres(model: Model) -> list:
    """Was keiner der Austauschexporte (DXF, IFC, Abaqus, Nastran) schreibt -
    fuer :func:`nicht_uebertragen`."""
    n_feder = sum(1 for e in model.elements if e.typ == "feder")
    n_grenz = sum(1 for e in model.elements if e.typ.startswith("grenzschicht"))
    n_nur = sum(1 for e in model.elements if getattr(e, "nur", ""))
    n_exz = sum(1 for e in model.elements
                if any(any(float(v) for v in x) for x in (getattr(e, "exzentrizitaet", None) or [])
                       if isinstance(x, (list, tuple))))
    return [
        (n_nur, "Stab mit Ausfall bei Zug oder Druck (geht als gewöhnlicher Stab hinaus)",
         "Stäbe mit Ausfall bei Zug oder Druck (gehen als gewöhnliche Stäbe hinaus)"),
        (n_exz, "Stabexzentrizität", "Stabexzentrizitäten"),
        (n_feder, "Federelement", "Federelemente"),
        (n_grenz, "Grenzschichtelement", "Grenzschichtelemente"),
        (len(getattr(model, "kopplungen", None) or []), "Kopplung", "Kopplungen"),
        (len(getattr(model, "starrkoerper", None) or []), "Starrkörper", "Starrkörper"),
        (len(getattr(model, "punktmassen", None) or []), "Punktmasse", "Punktmassen"),
        (len(getattr(model, "contact_pairs", None) or [])
         + len(getattr(model, "kontaktbedingungen", None) or [])
         + len(getattr(model, "contact_supports", None) or [])
         + len(getattr(model, "gap_elements", None) or []), "Kontaktdefinition",
         "Kontaktdefinitionen"),
        (lastzahl(model, "zwangsverformungen"), "Zwangsverformung", "Zwangsverformungen"),
        (lastzahl(model, "vorspannungen"), "Vorspannung", "Vorspannungen"),
        (lastzahl(model, "uebermasse"), "Übermaß", "Übermaße"),
    ]


def beam_elements(model: Model) -> list[int]:
    return [i for i, e in enumerate(model.elements) if e.typ in EL.STAB_TYPEN]


def shell_elements(model: Model) -> list[int]:
    return [i for i, e in enumerate(model.elements) if e.typ.startswith("shell")]


def solid_elements(model: Model) -> list[int]:
    return [i for i, e in enumerate(model.elements) if e.typ in EL.VOLUMEN_TYPEN]


def member_chains(model: Model) -> list[tuple[str, list[int]]]:
    """[(Name, Elementliste)] der Staebe; Elemente ohne Stab kommen einzeln dazu."""
    out = []
    belongs = set()
    for name, mem in model.members.items():
        els = [int(e) for e in mem.elements]
        out.append((name, els))
        belongs.update(els)
    for i in beam_elements(model):
        if i not in belongs:
            out.append((f"E{i + 1}", [i]))
    return out


def chain_ends(model: Model, elems: list[int]) -> tuple[int, int]:
    """Anfangs- und Endknoten einer Elementkette."""
    if not elems:
        raise ValueError("leere Elementkette")
    zaehler: dict[int, int] = {}
    for i in elems:
        for n in model.elements[i].nodes[:2]:
            zaehler[int(n)] = zaehler.get(int(n), 0) + 1
    enden = [n for n, c in zaehler.items() if c == 1]
    if len(enden) == 2:
        p = model.nodes[enden]
        return (enden[0], enden[1]) if p[0].tolist() <= p[1].tolist() else (enden[1], enden[0])
    first = model.elements[elems[0]].nodes
    last = model.elements[elems[-1]].nodes
    return int(first[0]), int(last[1])


def chain_length(model: Model, elems: list[int]) -> float:
    return float(sum(model.element_length(i) for i in elems))


def material_of(model: Model, elem: int) -> str:
    return model.elements[elem].mat


def section_of(model: Model, elem: int) -> str:
    return model.elements[elem].sec or ""


def steel_grade(model: Model, name: str) -> str:
    m = model.materials.get(name)
    if m is None:
        return "S235"
    return m.grade or name


def triangles(model: Model) -> list[tuple[int, int, int]]:
    """Alle Schalenelemente als Dreiecke (Vierecke aufgeteilt)."""
    out = []
    for i in shell_elements(model):
        n = [int(x) for x in model.elements[i].nodes]
        if len(n) >= 3:
            out.append((n[0], n[1], n[2]))
        if len(n) == 4:
            out.append((n[0], n[2], n[3]))
    return out


def solid_faces(model: Model) -> list[tuple]:
    """Aussenflaechen der Volumenelemente (Facetten, die nur einmal vorkommen)."""
    from .. import mesher
    try:
        return mesher.surface_facets(model)
    except Exception:            # noqa: BLE001
        return []


def bbox(model: Model):
    return model.bbox()
