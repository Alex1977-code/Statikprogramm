"""
Rueckfrage beim Import und Elementuebersicht (Paket E, 25.09.2026).

Wuensche des Anwenders:

* 23.09.2026: „ich möchte die zu verwendenden elemente anhaken können …
  standard sollte tet10 und vq83 sein.“
* 25.09.2026, nach einem Drehlager-Lauf mit tet4: „auswahl der zu
  verwendenden elemente bei berechnung war nicht vorhanden; und nach der
  Berechnung sehe ich das auch nirgendwo … wie kann ich dem prüfer beweisen
  dass an dieser stelle dieses element verwendet wurde“.
* 25.09.2026, danach: Stufen statt Haken („keep it simple“, „viel zu
  fummelig“). **Die Haken der Elementwahl sind damit ersetzt** durch das
  Auswahlfeld „Elemente“ (Entwurf / Mittel / Fein) in den
  Netzeinstellungen - Logik in :mod:`statik3d.elementstufe`. Hier bleiben
  die Rueckfrage beim Import (jetzt nach der Stufe) und die Zaehlung und
  Faerbung des fertigen Netzes nach Elementtyp fuer Ansicht, Protokoll und
  Bericht.

**Warum die RFEM-Datei keine Elementordnung vorgibt.** Die mesh.xml einer
.rf6 enthaelt Ziellaenge, Knotenabstand, Stabteilung, Seitenverhaeltnis,
Elementform der Flaechen und „abgebildetes Netz bevorzugen“ - aber keinen
Schluessel fuer lineare oder quadratische Elemente (nachgesehen am
25.09.2026 in beiden Drehlager-Dateien V15_4). Die Zeile „lineare Elemente
(shell3/shell4, tet4, hex8) (aus mesh.xml der RFEM-Datei)“ im Protokoll des
Drehlager-Laufs war die Vorgabe des Datenmodells (``ordnung = 1``), nicht die
der Datei. Die Rueckfrage beim Import fragt darum nur nach dem, was eine
Datei wirklich vorgibt; gibt sie eine Ordnung vor, ist das eine Stufe (1
Entwurf, 2 Mittel).
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import elemente as EL
from . import elementstufe as es

#: Statik3D-Vorgabe als Text fuer Rueckfrage und Hinweise (seit den Stufen
#: am 25.09.2026 die Stufe Mittel: tet10, hex20 (VQ203), Schalen quadratisch)
VORGABE_TEXT = es.NAME[es.VORGABE]


# --------------------------------------------------------------------------
# Rueckfrage beim Import
# --------------------------------------------------------------------------
#: Felder der Netzeinstellungen, die eine Elementwahl sind (was eine Datei
#: vorgeben kann): Elementordnung (= Stufe Entwurf oder Mittel) und
#: Elementform der Flaechen
ELEMENTFELDER = ("ordnung", "form")


def _stufe_der_ordnung(wert) -> str:
    return "mittel" if int(wert) >= 2 else "entwurf"


def _feldtext(feld: str, wert) -> str:
    if feld == "ordnung":
        s = _stufe_der_ordnung(wert)
        return f"{es.NAME[s]} ({'quadratische' if es.ORDNUNG[s] >= 2 else 'lineare'} Elemente)"
    from .netzdichte import FORMEN
    return "Flächen " + FORMEN.get(int(wert), str(wert))


def statik3d_vorgabe(feld: str, gesperrt: bool = False):
    """Die Statik3D-Vorgabe eines Elementfeldes. ``gesperrt``: das Modell hat
    Kontakt (elementstufe.quadratisch_gesperrt) - dann ist die Vorgabe
    Entwurf."""
    if feld == "ordnung":
        return es.ORDNUNG["entwurf" if gesperrt else es.VORGABE]
    from .model import Netzeinstellungen
    return getattr(Netzeinstellungen(), feld)


def abweichungen(aus_datei: dict, gesperrt: bool = False) -> list:
    """[(Feld, Text der Datei, Text der Statik3D-Vorgabe)] fuer jedes
    Elementfeld, das die Datei vorgibt und das anders ist als die Vorgabe.
    ``aus_datei`` sind die Felder, die der Import wirklich aus der Datei
    gelesen hat (rfem6_db.mesh_info) - nicht die Netzeinstellungen danach,
    in denen die Vorgabe des Datenmodells steht."""
    aus = []
    for feld in ELEMENTFELDER:
        if feld not in (aus_datei or {}):
            continue
        soll = statik3d_vorgabe(feld, gesperrt)
        if feld == "ordnung":
            gleich = _stufe_der_ordnung(aus_datei[feld]) == _stufe_der_ordnung(soll)
        else:
            gleich = int(aus_datei[feld]) == int(soll)
        if not gleich:
            aus.append((feld, _feldtext(feld, aus_datei[feld]), _feldtext(feld, soll)))
    return aus


def frage_text(datei: str, abw: list) -> str:
    """Text der Rueckfrage (25.09.2026): „Die Datei gibt Entwurf (lineare
    Elemente) vor. Statik3D-Vorgabe: Mittel. Welche verwenden?“"""
    teile = ", ".join(d for _f, d, _s in abw)
    vorgaben = []
    for f, _d, s in abw:
        # die Stufe mit ihrem Namen allein, wie im Auswahlfeld
        vorgaben.append(s.split(" (")[0] if f == "ordnung" else s)
    return (f"Die {datei} gibt {teile} vor.\n"
            f"Statik3D-Vorgabe: {', '.join(vorgaben)}.\n\n"
            "Welche verwenden?")


def nach_import(netz, aus_datei: dict, datei_waehlen: bool, datei: str = "Datei",
                gesperrt: bool = False) -> tuple:
    """(Netzeinstellungen, Protokollzeile) nach dem Import.

    Elementfelder, die die Datei nicht vorgibt, bekommen die Statik3D-
    Vorgabe; die, die sie vorgibt, je nach Antwort die der Datei
    (``datei_waehlen``) oder die Statik3D-Vorgabe. Die Ordnung wird als
    Stufe gesetzt (elementstufe.setzen: Ordnung, Sweep „sauber“). ``quelle``
    sagt danach, woher die Elemente kommen."""
    aus_datei = dict(aus_datei or {})
    werte = {}
    herkunft = []
    for feld in ELEMENTFELDER:
        if feld in aus_datei and datei_waehlen:
            werte[feld] = int(aus_datei[feld])
            herkunft.append(f"{_feldtext(feld, werte[feld])} aus der {datei}")
        else:
            werte[feld] = int(statik3d_vorgabe(feld, gesperrt))
            herkunft.append(f"{_feldtext(feld, werte[feld])} (Statik3D-Vorgabe"
                            + (", die Datei gibt es nicht vor)" if feld not in aus_datei else ")"))
    neu = es.setzen(replace(netz, form=werte["form"]), _stufe_der_ordnung(werte["ordnung"]))
    quelle = str(getattr(netz, "quelle", "") or "")
    zusatz = ("Elemente der Datei" if datei_waehlen and any(f in aus_datei for f in ELEMENTFELDER)
              else f"Elemente Statik3D-Vorgabe {VORGABE_TEXT}")
    neu.quelle = f"{quelle}; {zusatz}" if quelle else zusatz
    zeile = "Elemente nach dem Import: " + "; ".join(herkunft)
    return neu, zeile


# --------------------------------------------------------------------------
# Uebersicht des fertigen Netzes
# --------------------------------------------------------------------------
#: Name eines Elementtyps, wie ihn der Anwender kennt (VQ83/VQ203 aus InfoGraph)
KURZNAME = {"hex8": "hex8 (VQ83)", "hex20": "hex20 (VQ203)"}
#: Gruppe von Elementen ohne Koerper oder Flaeche (Stabzug, Import ohne Geometrie)
OHNE_KOERPER = "(ohne Körper)"


def kurzname(typ: str) -> str:
    return KURZNAME.get(typ, typ)


def ansatz(typ: str) -> str:
    """linear, quadratisch oder p = k (hierarchisch)."""
    a = EL.ELEMENTE.get(typ)
    if a is None:
        return "–"
    if typ.startswith("tetp"):
        return f"p = {a.ordnung} (hierarchisch)"
    return "quadratisch" if a.ordnung >= 2 else "linear"


def _typen_array(model) -> np.ndarray:
    return np.array([e.typ for e in model.elements], dtype=object)


def zaehlung(model) -> dict:
    """{"gesamt": N, "typen": {typ: n}, "koerper": {name: {typ: n}},
    "elemente": {typ: [Nummern]}} - Koerper ist die Gruppe des Elements
    (Volumenkoerper oder Flaeche), sonst OHNE_KOERPER. Typen in der
    Reihenfolge des Elementverzeichnisses."""
    typen: dict = {}
    koerper: dict = {}
    nummern: dict = {}
    for i, e in enumerate(model.elements):
        t = e.typ
        typen[t] = typen.get(t, 0) + 1
        g = str(getattr(e, "group", "") or "") or OHNE_KOERPER
        je = koerper.setdefault(g, {})
        je[t] = je.get(t, 0) + 1
        nummern.setdefault(t, []).append(i)
    reihe = list(EL.ELEMENTE)
    rang = {t: k for k, t in enumerate(reihe)}
    typen = dict(sorted(typen.items(), key=lambda kv: rang.get(kv[0], len(reihe))))
    return {"gesamt": len(model.elements), "typen": typen,
            "koerper": dict(sorted(koerper.items())), "elemente": nummern}


def typen_zaehlen(model) -> dict:
    """{"gesamt": N, "typen": {typ: n}} - nur die Typen, ohne Koerper und
    Nummern: bei 1 812 423 Elementen 0,17 statt 0,93 s fuer zaehlung
    (gemessen 25.09.2026); das Protokoll braucht es nach jeder Rechnung."""
    from collections import Counter
    rang = {t: k for k, t in enumerate(EL.ELEMENTE)}
    c = Counter(e.typ for e in model.elements)
    return {"gesamt": len(model.elements),
            "typen": dict(sorted(c.items(), key=lambda kv: rang.get(kv[0], len(rang))))}


def anteil_text(n: int, gesamt: int) -> str:
    """Anteil in Prozent mit Komma, nie wissenschaftlich: „12,3 %“."""
    from .zahlen import zahl_text
    if gesamt <= 0:
        return "–"
    p = 100.0 * n / gesamt
    return zahl_text(round(p, 1 if p >= 0.1 else 3)) + " %"


def zeilen(model, z: dict = None) -> list:
    """Eine Zeile je Elementtyp: {"typ", "name", "ansatz", "anzahl",
    "anteil", "koerper": {name: n}} - fuer Maske und Bericht."""
    z = z or zaehlung(model)
    aus = []
    for t, n in z["typen"].items():
        je = {k: d[t] for k, d in z["koerper"].items() if t in d}
        aus.append({"typ": t, "name": kurzname(t), "ansatz": ansatz(t), "anzahl": n,
                    "anteil": anteil_text(n, z["gesamt"]), "koerper": je})
    return aus


def protokollzeile(model, z: dict = None) -> str:
    """„Elemente dieser Rechnung: 12 345 tet10 (quadratisch, 97,2 %), …“ -
    nach jeder Rechnung ins Protokoll (25.09.2026: „nach der Berechnung sehe
    ich das auch nirgendwo“)."""
    from .zahlen import zahl_text
    z = z or typen_zaehlen(model)
    if not z["gesamt"]:
        return "Elemente dieser Rechnung: keine"
    teile = [f"{zahl_text(n)} {kurzname(t)} ({ansatz(t)}, {anteil_text(n, z['gesamt'])})"
             for t, n in z["typen"].items()]
    return f"Elemente dieser Rechnung ({zahl_text(z['gesamt'])}): " + ", ".join(teile)


# --------------------------------------------------------------------------
# Faerbung nach Elementtyp
# --------------------------------------------------------------------------
#: Eine Farbe je Elementtyp. Erzeugt aus CIELAB mit festen Helligkeiten L*
#: (22, 28, 34, … 91 - je Typ um 4 bis 6 verschieden) und wechselndem Farbton,
#: damit die Typen auch in Graustufen (Ausdruck, Fotokopie fuer den Pruefer)
#: verschieden hell sind; tests/test_elementuebersicht.py rechnet L* nach.
FARBEN = {
    "beam": "#003856", "hex20": "#064086", "tet4": "#a30229", "shell8": "#824693",
    "pent15": "#0b7776", "tetp4": "#aa6734", "hex8": "#038cc6", "tetp3": "#dc68ab",
    "shell4": "#99a14d", "pyr5": "#fc863d", "tet10": "#6dc769", "tetp2": "#ffa5ba",
    "shell6": "#5ddaee", "pent6": "#fdd43c", "shell3": "#d0f0a5",
    # seltener zusammen mit den obigen: an ihre naechsten Verwandten angelehnt
    "truss": "#3c3c3c", "seil": "#5a5a5a", "feder": "#8a8a8a",
    "ebene3": "#c2e6a0", "ebene4": "#8c9446", "ebene6": "#55c8da", "ebene8": "#733f82",
    "grenzschicht6": "#b8b8b8", "grenzschicht8": "#d8d8d8",
}
#: Farbe fuer einen unbekannten Typ
FARBE_SONST = "#9a9a9a"


def farbe(typ: str) -> str:
    return FARBEN.get(typ, FARBE_SONST)


def helligkeit(hexfarbe: str) -> float:
    """CIELAB-Helligkeit L* (0 schwarz … 100 weiss) einer Farbe #rrggbb."""
    h = hexfarbe.lstrip("#")
    rgb = [int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    Y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    return 116.0 * Y ** (1.0 / 3.0) - 16.0 if Y > 0.008856 else 903.3 * Y


def faerbung(model) -> dict:
    """{"codes": Code je Element (float), "typen": [Typ je Code],
    "farben": [#rrggbb je Code], "namen": {Code: Legendentext}} - nur die
    Typen, die im Netz vorkommen, in der Reihenfolge des Verzeichnisses."""
    z = typen_zaehlen(model)
    typen = list(z["typen"])
    code = {t: float(k) for k, t in enumerate(typen)}
    codes = np.array([code[e.typ] for e in model.elements], float) if model.elements \
        else np.zeros(0)
    from .zahlen import zahl_text
    namen = {float(k): f"{kurzname(t)} ({zahl_text(z['typen'][t])})" for k, t in enumerate(typen)}
    return {"codes": codes, "typen": typen, "farben": [farbe(t) for t in typen], "namen": namen}


# --------------------------------------------------------------------------
# Netzfeinheit und Fingerabdruck (Bericht)
# --------------------------------------------------------------------------
#: Eckkanten je Typ (Knotenindizes der Ecken) fuer die Kantenlaenge
_KANTEN = {
    "tet": ((0, 1), (1, 2), (0, 2), (0, 3), (1, 3), (2, 3)),
    "hex": ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)),
    "pent": ((0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3), (0, 3), (1, 4), (2, 5)),
    "pyr": ((0, 1), (1, 2), (2, 3), (3, 0), (0, 4), (1, 4), (2, 4), (3, 4)),
    "tri": ((0, 1), (1, 2), (2, 0)),
    "quad": ((0, 1), (1, 2), (2, 3), (3, 0)),
    "linie": ((0, 1),),
}


def _kantenart(typ: str) -> str:
    if typ.startswith("tet"):
        return "tet"
    if typ.startswith("hex") or typ == "grenzschicht8":
        return "hex"
    if typ.startswith("pent") or typ == "grenzschicht6":
        return "pent"
    if typ == "pyr5":
        return "pyr"
    if typ in ("shell3", "shell6", "ebene3", "ebene6"):
        return "tri"
    if typ in ("shell4", "shell8", "ebene4", "ebene8"):
        return "quad"
    return "linie"


def kantenlaengen(model, nummern) -> tuple:
    """(kleinste, mittlere, groesste) Eckkantenlaenge [m] der Elemente -
    die Netzfeinheit, wie sie im Netz wirklich ist (nicht die Vorgabe)."""
    X = np.asarray(model.nodes, float)
    je_art: dict = {}
    for i in nummern:
        e = model.elements[int(i)]
        je_art.setdefault(_kantenart(e.typ), []).append(e.nodes)
    werte = []
    for art, liste in je_art.items():
        kanten = _KANTEN[art]
        n_ecken = max(max(k) for k in kanten) + 1
        K = np.array([list(kn[:n_ecken]) for kn in liste], int)
        for a, b in kanten:
            werte.append(np.linalg.norm(X[K[:, a]] - X[K[:, b]], axis=1))
    if not werte:
        return (0.0, 0.0, 0.0)
    w = np.concatenate(werte)
    w = w[w > 0]
    if not w.size:
        return (0.0, 0.0, 0.0)
    return (float(w.min()), float(w.mean()), float(w.max()))


def fingerabdruck(model) -> str:
    """Netz-Fingerabdruck: derselbe Hash ueber Typ und Knoten jedes Elements,
    den die Ergebnisdatei in ihrer Kennung traegt (ergebnisse.elementhash)."""
    from .ergebnisse import elementhash
    return elementhash(model)
