"""
Elementwahl zum Anhaken und Elementuebersicht (Paket E, 25.09.2026).

Wuensche des Anwenders:

* 23.09.2026: „ich möchte die zu verwendenden elemente anhaken können und je
  nach kompatibilität der elemente sollen dann die anhakmöglichkeiten
  ausgegraut werden … standard sollte tet10 und vq83 sein.“
* 25.09.2026, nach einem Drehlager-Lauf mit tet4: „auswahl der zu
  verwendenden elemente bei berechnung war nicht vorhanden; und nach der
  Berechnung sehe ich das auch nirgendwo … wie kann ich dem prüfer beweisen
  dass an dieser stelle dieses element verwendet wurde“.

Dieses Modul ist die Logik ohne Oberflaeche: welche Haken es gibt, welche
gesetzt und welche grau sind (mit Grund), wie die Wahl auf die **vorhandenen**
Netzeinstellungen abbildet, was der Import fragt, und die Zaehlung und
Faerbung des fertigen Netzes nach Elementtyp fuer Ansicht, Protokoll und
Bericht.

**Was die Wahl einstellen kann - und was nicht.** Der Vernetzer kennt eine
Ordnung fuer alles, was er selbst erzeugt (``Netzeinstellungen.ordnung``):
frei vernetzte Koerper werden tet4 oder tet10, abgebildete Sechsflaechner
(sechs Vierecke, acht Ecken, gerade Kanten) hex8 oder hex20, Flaechen
shell3/shell4 oder shell6/shell8 - alles mit derselben Ordnung. Der Sweep
(``Netzeinstellungen.sweep``, seit 25.09.2026 ein Wort "aus" | "sauber" |
"immer" und keine Option der Oberflaeche mehr) macht hex8/pent6.
Pyramiden als Uebergang schaltet ``Netzeinstellungen.pyramiden``. Ein
Tetraeder mit Ordnung p (tetp) entsteht nur durch Umwandlung eines tet10-
Netzes (elements.tetp.aus_tet10), nicht beim Vernetzen. Darum sind hier nur
tet4/tet10 und die Pyramiden anhakbar; VQ83, VQ203, tetp und die Schalen
folgen daraus und stehen grau mit ihrem Grund da. Die Vorgabe des Anwenders
„tet10 + VQ83“ heisst damit: tet10 frei, hex8 aus dem Sweep und jeder hex8
als VQ83 gerechnet - abgebildete Sechsflaechner werden bei tet10 aber hex20
(VQ203), das kann die Wahl ohne Aenderung am Vernetzer nicht trennen.

**Warum die RFEM-Datei keine Elementordnung vorgibt.** Die mesh.xml einer
.rf6 enthaelt Ziellaenge, Knotenabstand, Stabteilung, Seitenverhaeltnis,
Elementform der Flaechen und „abgebildetes Netz bevorzugen“ - aber keinen
Schluessel fuer lineare oder quadratische Elemente (nachgesehen am
25.09.2026 in beiden Drehlager-Dateien V15_4). Die Zeile „lineare Elemente
(shell3/shell4, tet4, hex8) (aus mesh.xml der RFEM-Datei)“ im Protokoll des
Drehlager-Laufs war die Vorgabe des Datenmodells (``ordnung = 1``), nicht die
der Datei. Die Rueckfrage beim Import fragt darum nur nach dem, was die Datei
wirklich vorgibt; die Ordnung ist die Statik3D-Vorgabe.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import elemente as EL

#: Statik3D-Vorgabe der Elementwahl (Anwender 23.09.2026): tet10 + VQ83
VORGABE = frozenset({"tet10", "hex8"})
VORGABE_TEXT = "tet10 + VQ83"
#: ... und was sie in den Netzeinstellungen heisst
VORGABE_ORDNUNG = 2

#: Die Haken der Maske: (Schluessel, Gruppe, Beschriftung). Die Gruppen sind
#: die Familien, in denen der Anwender denkt.
HAKEN = (
    ("tet4", "Volumen – Tetraeder", "tet4 – linear, 4 Knoten"),
    ("tet10", "Volumen – Tetraeder", "tet10 – quadratisch, 10 Knoten"),
    ("tetp", "Volumen – Tetraeder", "tetp – Ordnung p = 2 … 4 (hierarchisch)"),
    ("hex8", "Volumen – Sechsflächner", "VQ83 – hex8, entartet als pent6/pyr5/tet4"),
    ("hex20", "Volumen – Sechsflächner", "VQ203 – hex20, entartet als pent15/tet10"),
    ("pyr5", "Volumen – Übergang", "Pyramiden (pyr5) zwischen Vierecken und Tetraedern"),
    ("schale1", "Schalen", "linear – shell3/shell4"),
    ("schale2", "Schalen", "quadratisch – shell6/shell8"),
)
#: Haken, die der Anwender selbst setzt - die uebrigen folgen aus ihnen
ANHAKBAR = ("tet4", "tet10", "pyr5")
#: Haken -> Elementtyp fuer die Vertraeglichkeitstabelle (elemente.VERTRAEGLICH)
TYP = {"tet4": "tet4", "tet10": "tet10", "tetp": "tetp2", "hex8": "hex8", "hex20": "hex20",
       "pyr5": "pyr5"}


def _vertraeglich_text(a: str, b: str) -> str:
    """„neben tet10: passen nicht aneinander“ aus elemente.VERTRAEGLICH."""
    art = EL.VERTRAEGLICH.get((TYP[a], TYP[b]), "nein")
    return f"neben {a}: {EL.VERTRAEGLICH_TEXT[art]}"


def wahl_aus_netz(netz) -> set:
    """Die angehakten Elemente zu den Netzeinstellungen."""
    wahl = {"tet10" if int(getattr(netz, "ordnung", 1) or 1) >= 2 else "tet4"}
    if bool(getattr(netz, "pyramiden", False)):
        wahl.add("pyr5")
    return wahl


def sweep_an(netz) -> bool:
    """Ob der Sweep in diesen Netzeinstellungen an ist (25.09.2026).

    Seit das Feld ein Wort ist, waere bool(netz.sweep) auch fuer "aus" wahr -
    die Elementwahl zeigte dann „an“. Gelesen wie im Vernetzer
    (sweep.betriebsart): alles ausser "aus" sweept."""
    from types import SimpleNamespace
    from .sweep import betriebsart
    return betriebsart(SimpleNamespace(netz=netz)) != "aus"


def tetraeder(wahl) -> str:
    """Der gewaehlte Tetraeder: "tet10", "tet4" oder "" (keiner)."""
    return "tet10" if "tet10" in wahl else ("tet4" if "tet4" in wahl else "")


def zustand(wahl, sweep: bool = False) -> dict:
    """Je Haken {"an": angehakt, "frei": anklickbar, "grund": Klartext}.

    ``grund`` erklaert bei einem grauen Haken, warum er grau ist (Tooltip),
    bei einem freien, was er bewirkt. Grau ist, was nicht zur Wahl passt -
    nach der Vertraeglichkeitstabelle (elemente.VERTRAEGLICH) - oder was der
    Vernetzer nicht getrennt einstellen kann."""
    wahl = set(wahl or ())
    tet = tetraeder(wahl)
    z: dict = {}
    eine_ordnung = ("Eine Ordnung für alle frei vernetzten Körper (Netzeinstellungen → "
                    "Elementansatz): tet4 und tet10 gemischt gibt es nur je Körper "
                    "(Ordnung am Volumenkörper), nicht über diese Wahl")
    for a, b in (("tet4", "tet10"), ("tet10", "tet4")):
        if b in wahl:
            z[a] = {"an": False, "frei": False,
                    "grund": f"{eine_ordnung} – erst {b} abhaken ({_vertraeglich_text(b, a)})."}
        elif a == "tet4":
            z[a] = {"an": a in wahl, "frei": True,
                    "grund": "Konstante Dehnung je Element: die Spannung stimmt erst bei sehr "
                             "feinem Netz (Kragarm 22.09.2026: −266 / −166 / −70 N/mm² Abweichung "
                             "vom Sollwert 355 bei 90 / 405 / 2 295 FHG)."}
        else:
            z[a] = {"an": a in wahl, "frei": True,
                    "grund": "Statik3D-Vorgabe. Quadratischer Ansatz: am Kragarm +14 / +4 / +1 N/mm² "
                             "bei 405 / 2 295 / 15 147 FHG (22.09.2026); Flächen bekommen dann "
                             "shell6/shell8, abgebildete Sechsflächner hex20."}
    kein_weg = ("Der Vernetzer erzeugt keine tetp - sie entstehen nur aus einem tet10-Netz "
                "(elements.tetp.aus_tet10); in der Oberfläche noch nicht wählbar.")
    z["tetp"] = {"an": False, "frei": False,
                 "grund": (_vertraeglich_text(tet, "tetp") + " (die Rechnung hält dort an). "
                           if tet == "tet10" else "") + kein_weg}
    if tet == "tet4":
        neu = ("Neue hex8 entstehen in abgebildeten Sechsflächnern (sechs Vierecke, acht Ecken, "
               "gerade Kanten)" + (" und im Sweep." if sweep else
                                   "; der Sweep ist aus (seit 25.09.2026 keine Option der "
                                   "Oberfläche)."))
    else:
        neu = ("Neue hex8 entstehen nur im Sweep - " + (
            "der Sweep ist an (aus der Datei)." if sweep else
            "der Sweep ist aus (seit 25.09.2026 keine Option der Oberfläche), und die "
            "Elementwahl schaltet ihn nicht ein."))
    z["hex8"] = {"an": True, "frei": False,
                 "grund": "Jeder hex8 im Netz wird als VQ83 gerechnet: mit zusammenfallenden Knoten "
                          "als der Keil, die Pyramide oder der Tetraeder, der er ist (immer an). "
                          + neu + (f" {_vertraeglich_text(tet, 'hex8')}." if tet else "")}
    if tet == "tet10":
        z["hex20"] = {"an": True, "frei": False,
                      "grund": "Folgt dem Tetraeder: mit tet10 bekommen abgebildete Sechsflächner "
                               "(sechs Vierecke, acht Ecken, gerade Kanten) hex20 - der Vernetzer hat "
                               "eine Ordnung für beide. Mit zusammenfallenden Knoten wird ein hex20 "
                               "als pent15 oder tet10 gerechnet (VQ203). Gesweepte Körper bleiben hex8."}
    else:
        z["hex20"] = {"an": False, "frei": False,
                      "grund": "hex20 entsteht nur mit dem quadratischen Ansatz (tet10). "
                               + (_vertraeglich_text(tet, "hex20") + "." if tet else "")}
    z["pyr5"] = {"an": "pyr5" in wahl, "frei": True,
                 "grund": "Wo ein frei vernetzter Körper an die Vierecke eines gesweepten oder "
                          "abgebildeten Nachbarn stößt, bekommt jedes Viereck eine Pyramide "
                          "(Netzeinstellungen.pyramiden); ohne sie teilt der Tetraeder das Viereck "
                          "in zwei Dreiecke. " + (_vertraeglich_text(tet, "pyr5") + "." if tet else "")}
    folgt = ("Flächen folgen dem Ansatz der Tetraeder (Netzeinstellungen → Elementansatz): "
             "eine Ordnung für das ganze Netz.")
    z["schale1"] = {"an": tet == "tet4", "frei": False, "grund": folgt}
    z["schale2"] = {"an": tet == "tet10", "frei": False, "grund": folgt}
    return z


def auf_netz(netz, wahl):
    """Die Wahl in die Netzeinstellungen: nur ``ordnung`` und ``pyramiden``.

    Den Sweep und alles andere laesst sie, wie es ist. ValueError, wenn kein
    Tetraeder gewaehlt ist - frei vernetzte Koerper braeuchten einen."""
    tet = tetraeder(wahl)
    if not tet:
        raise ValueError("Für frei vernetzte Körper ist ein Tetraeder nötig: tet4 oder tet10 anhaken")
    return replace(netz, ordnung=2 if tet == "tet10" else 1, pyramiden="pyr5" in set(wahl))


def vorschau(wahl, sweep: bool = False) -> list:
    """So wird vernetzt - eine Zeile je Weg des Vernetzers."""
    tet = tetraeder(wahl)
    if not tet:
        return ["Kein Tetraeder gewählt - frei vernetzte Körper bekämen kein Element."]
    q = tet == "tet10"
    zeilen = [f"frei vernetzte Körper: {tet}"
              + (", Pyramiden (pyr5) an Vierecken der Nachbarn" if "pyr5" in wahl else ""),
              "abgebildete Sechsflächner: " + ("hex20 (VQ203)" if q else "hex8 (VQ83)"),
              "gesweepte Körper: " + ("hex8 und pent6 (VQ83)" if sweep else
                                      "keine - der Sweep ist aus"),
              "Flächen: " + ("shell6/shell8 (quadratisch)" if q else "shell3/shell4 (linear)"),
              "zusammenfallende Knoten: als pent6, pyr5, tet4 bzw. pent15, tet10 gerechnet"]
    return zeilen


def wahl_text(wahl) -> str:
    """Kurzname der Wahl fuer Protokoll und Rueckfrage: „tet10 + VQ83“."""
    tet = tetraeder(wahl) or "kein Tetraeder"
    return f"{tet} + VQ83" + (" + pyr5" if "pyr5" in set(wahl) else "")


# --------------------------------------------------------------------------
# Rueckfrage beim Import
# --------------------------------------------------------------------------
#: Felder der Netzeinstellungen, die eine Elementwahl sind (was eine Datei
#: vorgeben kann): Elementordnung und Elementform der Flaechen
ELEMENTFELDER = ("ordnung", "form")


def _feldtext(feld: str, wert) -> str:
    if feld == "ordnung":
        return ("quadratische Elemente (shell6/shell8, tet10, hex20)" if int(wert) >= 2
                else "lineare Elemente (shell3/shell4, tet4, hex8)")
    from .netzdichte import FORMEN
    return "Flächen " + FORMEN.get(int(wert), str(wert))


def statik3d_vorgabe(feld: str):
    """Die Statik3D-Vorgabe eines Elementfeldes."""
    if feld == "ordnung":
        return VORGABE_ORDNUNG
    from .model import Netzeinstellungen
    return getattr(Netzeinstellungen(), feld)


def abweichungen(aus_datei: dict) -> list:
    """[(Feld, Text der Datei, Text der Statik3D-Vorgabe)] fuer jedes
    Elementfeld, das die Datei vorgibt und das anders ist als die Vorgabe.
    ``aus_datei`` sind die Felder, die der Import wirklich aus der Datei
    gelesen hat (rfem6_db.mesh_info) - nicht die Netzeinstellungen danach,
    in denen die Vorgabe des Datenmodells steht."""
    aus = []
    for feld in ELEMENTFELDER:
        if feld not in (aus_datei or {}):
            continue
        soll = statik3d_vorgabe(feld)
        if int(aus_datei[feld]) != int(soll):
            aus.append((feld, _feldtext(feld, aus_datei[feld]), _feldtext(feld, soll)))
    return aus


def frage_text(datei: str, abw: list) -> str:
    """Text der Rueckfrage: was die Datei vorgibt, was Statik3D vorgibt."""
    teile = ", ".join(d for _f, d, _s in abw)
    vorgabe = ", ".join(s for _f, _d, s in abw)
    return (f"Die {datei} gibt {teile} vor.\n"
            f"Statik3D-Vorgabe: {VORGABE_TEXT} ({vorgabe}).\n\n"
            "Welche verwenden?")


def nach_import(netz, aus_datei: dict, datei_waehlen: bool, datei: str = "Datei") -> tuple:
    """(Netzeinstellungen, Protokollzeile) nach dem Import.

    Elementfelder, die die Datei nicht vorgibt, bekommen die Statik3D-
    Vorgabe; die, die sie vorgibt, je nach Antwort die der Datei
    (``datei_waehlen``) oder die Statik3D-Vorgabe. ``quelle`` sagt danach,
    woher die Elementwahl kommt - vorher stand dort nur „aus mesh.xml“, auch
    hinter der Ordnung, die gar nicht aus der Datei kam."""
    aus_datei = dict(aus_datei or {})
    werte = {}
    herkunft = []
    for feld in ELEMENTFELDER:
        if feld in aus_datei and datei_waehlen:
            werte[feld] = int(aus_datei[feld])
            herkunft.append(f"{_feldtext(feld, werte[feld])} aus der {datei}")
        else:
            werte[feld] = int(statik3d_vorgabe(feld))
            herkunft.append(f"{_feldtext(feld, werte[feld])} (Statik3D-Vorgabe"
                            + (", die Datei gibt es nicht vor)" if feld not in aus_datei else ")"))
    neu = replace(netz, **werte)
    quelle = str(getattr(netz, "quelle", "") or "")
    zusatz = ("Elementwahl der Datei" if datei_waehlen and any(f in aus_datei for f in ELEMENTFELDER)
              else f"Elementwahl Statik3D-Vorgabe {VORGABE_TEXT}")
    neu.quelle = f"{quelle}; {zusatz}" if quelle else zusatz
    zeile = "Elementwahl nach dem Import: " + "; ".join(herkunft)
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
