"""
InfoCAD / InfoGraph: die Textausgabe von ``/ExportTxt`` lesen.

Die Projektdatei ``.fem`` ist ein proprietaeres Binaerformat und wird nicht
gelesen. InfoCAD schreibt aber auf Anforderung eine **Textfassung** seiner
Tabellen::

    InfoCADw64.exe modell.fem /ExportTxt:befehle.txt /Out:modell_export.txt

``befehle.txt`` enthaelt einen Tabellennamen je Zeile (ASCII, CRLF). Die
Ausgabe besteht aus Bloecken::

    BEGIN KNOTEN N=14679 TIME=04.09.26 18:07
    ?	?	?	?
    1	-0	0	0
    ...
    END KNOTEN

Gelesen wird daraus das **Modell**: Knoten, Schalen- und Stabelemente,
Werkstoffe, Schalendicken und die Layer. Ergebnisse (``REAK``, ``QUER``,
``SREAK``, ``AUFLR``, ``DEFORM``) rechnet Statik3D selbst und liest sie
nicht; Lager (``FESTH``) und Lasten fehlen, weil ihr Spaltenaufbau nicht
belegt ist - beides wird **benannt** und nicht stillschweigend uebergangen.

Vier Eigenheiten des Formats, die den Leser bestimmen:

* **Der Exitcode taugt nicht.** InfoCAD beendet den Export immer mit 13, auch
  wenn er geglueckt ist. Ob die Datei vollstaendig ist, entscheidet darum
  allein ihr Inhalt: jeder Block muss mit ``END <NAME>`` schliessen, und
  ``N=`` im Blockkopf muss zur Zahl der Datenzeilen passen. Beides wird
  geprueft und gemeldet.
* **Unbekannte Tabellennamen ueberspringt InfoCAD still.** Ein Tippfehler in
  der Befehlsdatei kostet eine ganze Tabelle, ohne eine Meldung. Dieser
  Leser macht es umgekehrt: er zaehlt auf, was er gelesen hat, und benennt
  jede Tabelle, die er gefunden, aber nicht verwertet hat.
* **Dezimalkomma und wechselnde Kodierung.** Die Zahlen stehen mit Komma, die
  Kodierung wechselt zwischen UTF-16, UTF-8 und cp1252.
* **Derselbe Typcode bedeutet in zwei Tabellen Verschiedenes.** In
  ``ELEMENTE`` ist 11 die Viereckschale, 8 die Dreieckschale, 2 der Stab; in
  ``QUERSW`` ist 2 die Schale. Ein Filter ``Typ == 2`` liefert also je nach
  Tabelle die Staebe oder alle Schalen - beides sieht plausibel aus. Die
  Codes stehen darum in zwei getrennten Tabellen (:data:`EL_TYPEN`,
  :data:`QS_SCHALE`) und werden nie voneinander uebernommen.

Quelle der Formatangaben ist die Uebergabe eines InfoCAD-Projekts vom
21.09.2026 (4498 Zeilen, an 45 von 48 Angaben belegt). Was dort **nicht**
steht, steht auch hier nicht: die Spalten von ``FESTH``, der Unterschied
``MAT``/``MAT2`` und die Einheiten der meisten Spalten. Wo eine Einheit
gedeutet werden muss (E-Modul, Wichte), sagt das Protokoll die gelesene Zahl
**und** die Deutung, damit ein Anwender den Fehlgriff sieht.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..model import Material, Model
from . import _common as C

#: Spalte 1 der Tabelle ELEMENTE (0-basiert gezaehlt) - an einem Export mit
#: 10 979 x 11, 438 x 8 und 56 x 2 abgezaehlt.
EL_TYPEN = {11: "shell4", 8: "shell3", 2: "beam"}
#: Spalte 1 der Tabelle QUERSW. **Nicht** dieselbe Bedeutung wie in ELEMENTE.
QS_SCHALE = 2

#: Ergebnistabellen: Statik3D rechnet selbst, liest sie also nicht.
ERGEBNISTABELLEN = ("REAK", "QUER", "SREAK", "AUFLR", "DEFORM", "EXTREMA",
                    "SPANN", "HAUPT")

_BEGIN = re.compile(r"^BEGIN\s+(\S+)(?:\s+N=(-?\d+))?(?:\s+TIME=(.*?))?\s*$")
_END = re.compile(r"^END\s+(\S+)\s*$")


@dataclass
class Block:
    """Ein BEGIN/END-Block der Exportdatei."""
    name: str
    n_soll: int = -1
    zeit: str = ""
    kopf: list = field(default_factory=list)
    zeilen: list = field(default_factory=list)
    abgeschlossen: bool = False

    @property
    def n_ist(self) -> int:
        return len(self.zeilen)

    def vollstaendig(self) -> bool:
        return self.abgeschlossen and (self.n_soll < 0 or self.n_ist == self.n_soll)


def _text_lesen(pfad: str) -> tuple:
    """(Text, Kodierung). Die Kodierung wechselt zwischen den Laeufen."""
    with open(pfad, "rb") as f:
        roh = f.read()
    if roh[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return roh.decode("utf-16"), "utf-16"
    try:
        return roh.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return roh.decode("cp1252", errors="replace"), "cp1252"


def _zahl(text: str):
    """Zahl mit Dezimalkomma; None, wenn es keine ist."""
    s = (text or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _ganz(text: str, standard: int = 0) -> int:
    z = _zahl(text)
    return int(round(z)) if z is not None else standard


def bloecke_lesen(pfad: str, log: list = None) -> dict:
    """Die BEGIN/END-Bloecke einer Exportdatei; Name -> :class:`Block`.

    Die Datei darf mehrere Laeufe aneinandergehaengt enthalten - sie besteht
    ja nur aus Bloecken. Kommt ein Name zweimal vor, wird der zweite als
    ``NAME#2`` gefuehrt und gemeldet; stillschweigend eines der beiden
    wegzuwerfen waere genau der Fehler, den dieses Format nahelegt.
    """
    text, kodierung = _text_lesen(pfad)
    C.say(log, f"InfoCAD-Textausgabe {os.path.basename(pfad)} ({kodierung}, "
               f"{len(text)} Zeichen)")
    bloecke: dict = {}
    offen = None
    erwartet_kopf = False
    for roh in text.splitlines():
        zeile = roh.rstrip("\r\n")
        mb = _BEGIN.match(zeile.strip())
        if mb:
            if offen is not None:
                C.warn(log, f"Tabelle {offen.name}: kein 'END {offen.name}' - der "
                            f"Block bricht bei {offen.n_ist} Zeilen ab (die Ausgabe "
                            "ist unvollstaendig, der Exitcode von InfoCAD sagt das "
                            "nicht)")
            name = mb.group(1)
            offen = Block(name, int(mb.group(2)) if mb.group(2) else -1,
                          (mb.group(3) or "").strip())
            erwartet_kopf = True
            schluessel = name
            k = 2
            while schluessel in bloecke:
                schluessel = f"{name}#{k}"
                k += 1
            if schluessel != name:
                C.warn(log, f"Tabelle {name} kommt mehrfach vor - die weitere wird "
                            f"als '{schluessel}' gefuehrt")
            bloecke[schluessel] = offen
            continue
        me = _END.match(zeile.strip())
        if me and offen is not None and me.group(1) == offen.name:
            offen.abgeschlossen = True
            offen = None
            continue
        if offen is None:
            continue
        if erwartet_kopf:
            # Direkt hinter BEGIN steht genau eine Kopfzeile - oft nur '?'
            offen.kopf = zeile.split("\t")
            erwartet_kopf = False
            continue
        if zeile.strip():
            offen.zeilen.append(zeile.split("\t"))
    if offen is not None:
        C.warn(log, f"Tabelle {offen.name}: die Datei endet mitten im Block "
                    f"({offen.n_ist} Zeilen gelesen)")
    for name, b in bloecke.items():
        if b.n_soll >= 0 and b.n_ist != b.n_soll:
            C.warn(log, f"Tabelle {name}: der Blockkopf sagt N={b.n_soll}, "
                        f"gelesen wurden {b.n_ist} Zeilen")
    return bloecke


def _werkstoffe(model: Model, bloecke: dict, log: list = None) -> dict:
    """MAT/MAT2 -> {InfoCAD-Nummer: Werkstoffname}.

    Spalten 'Nr Typ E G nu alpha_t gamma'. Die **Einheiten stehen nicht im
    Format**; gedeutet wird an der Groessenordnung, und das Protokoll sagt
    beides - die gelesene Zahl und die Deutung.
    """
    zuordnung: dict = {}
    for name in ("MAT", "MAT2"):
        b = bloecke.get(name)
        if b is None:
            continue
        for z in b.zeilen:
            nr = _ganz(z[0], -1)
            if nr < 0:
                continue
            E = _zahl(z[2]) if len(z) > 2 else None
            nu = _zahl(z[4]) if len(z) > 4 else None
            alpha = _zahl(z[5]) if len(z) > 5 else None
            gamma = _zahl(z[6]) if len(z) > 6 else None
            if not E or E <= 0:
                C.warn(log, f"Werkstoff {nr} aus {name} ohne E-Modul - uebergangen")
                continue
            if E < 1.0e7:      # 2,1e5 waere N/mm^2, 2,1e11 ist Pa
                C.say(log, f"Werkstoff {nr}: E = {E:.3e} gelesen, als N/mm² "
                           f"gedeutet -> {E * 1e6:.3e} Pa")
                E *= 1.0e6
            rho = 7850.0
            if gamma and gamma > 0:
                # Wichte: kN/m^3 (78,5) oder N/m^3 (78500)?
                g = gamma * 1.0e3 if gamma < 1.0e3 else gamma
                if gamma < 1.0e3:
                    C.say(log, f"Werkstoff {nr}: Wichte {gamma:.4g} gelesen, als "
                               f"kN/m³ gedeutet -> {g:.4g} N/m³")
                rho = g / 9.81
            mname = C.unique_name(model.materials, f"InfoCAD {nr}")
            model.add_material(Material(mname, E=float(E),
                                        nu=float(nu) if nu else 0.3,
                                        rho=float(rho),
                                        alpha=float(alpha) if alpha else 1.2e-5))
            zuordnung[nr] = mname
    return zuordnung


def _dicken(model: Model, bloecke: dict, log: list = None) -> dict:
    """QUERSW -> {Nummer: Name der Schalendicke}. Typ 2 ist die Schale, die
    Dicke steht in Spalte 3 (1-basiert gezaehlt) in **Metern**."""
    zuordnung: dict = {}
    b = bloecke.get("QUERSW")
    if b is None:
        return zuordnung
    for z in b.zeilen:
        nr = _ganz(z[0], -1)
        typ = _ganz(z[1], -1) if len(z) > 1 else -1
        if nr < 0 or typ != QS_SCHALE:
            continue
        t = _zahl(z[2]) if len(z) > 2 else None
        if t is None or t <= 0:
            C.warn(log, f"Querschnitt {nr}: Dicke {z[2] if len(z) > 2 else '?'} "
                        "ist nicht brauchbar - uebergangen")
            continue
        zuordnung[nr] = C.ensure_shell_prop(model, f"QS {nr}", float(t), log)
    return zuordnung


def _knoten(model: Model, bloecke: dict, z_nach_unten: bool,
            log: list = None) -> dict:
    """KNOTEN 'Nr x y z' in Metern -> {InfoCAD-Nummer: Knotenindex}."""
    b = bloecke.get("KNOTEN")
    if b is None:
        return {}
    knoten: dict = {}
    for z in b.zeilen:
        nr = _ganz(z[0], -1)
        if nr < 0 or len(z) < 4:
            continue
        x, y, zz = (_zahl(z[1]) or 0.0), (_zahl(z[2]) or 0.0), (_zahl(z[3]) or 0.0)
        if z_nach_unten:
            # Drehung um 180 Grad um die X-Achse - **keine** Spiegelung von z
            # allein: die waere linkshaendig und kehrte jede Flaechennormale um.
            y, zz = -y, -zz
        knoten[nr] = model.add_node(x, y, zz)
    return knoten


def _elemente(model: Model, bloecke: dict, knoten: dict, mat: dict, qs: dict,
              log: list = None) -> int:
    """ELEMENTE: 13 Spalten, auch bei Dreiecken.

    0 Nr, 1 Typ, 2-5 Knoten, 6-7 frei, 8 Material, 9 Querschnitt, 10-11 frei,
    12 Layercode (gepackt: ``Layer<<16 | FarbID<<8 | 1``). Der Layer wird die
    Elementgruppe - er ist in InfoCAD die Auswertungseinheit.
    """
    b = bloecke.get("ELEMENTE")
    if b is None:
        return 0
    standard_mat = None
    n = 0
    unbekannt: dict = {}
    for z in b.zeilen:
        typ = _ganz(z[1], -1) if len(z) > 1 else -1
        art = EL_TYPEN.get(typ)
        if art is None:
            unbekannt[typ] = unbekannt.get(typ, 0) + 1
            continue
        anzahl = {"shell4": 4, "shell3": 3, "beam": 2}[art]
        roh = [_ganz(z[2 + k], 0) for k in range(4) if len(z) > 2 + k]
        nd = [knoten.get(k) for k in roh[:anzahl]]
        if len(nd) != anzahl or any(k is None for k in nd):
            C.warn(log, f"Element {z[0] if z else '?'}: Knoten {roh[:anzahl]} gibt "
                        "es in der Tabelle KNOTEN nicht - uebergangen")
            continue
        if art == "shell3" and len(roh) > 3 and roh[3] not in (0, roh[2], roh[0]):
            C.warn(log, f"Element {z[0]}: als Dreieck gefuehrt (Typ {typ}), aber "
                        f"die vierte Knotenspalte traegt {roh[3]} - sie wird "
                        "uebergangen")
        mnr = _ganz(z[8], -1) if len(z) > 8 else -1
        mname = mat.get(mnr)
        if mname is None:
            if standard_mat is None:
                standard_mat = C.ensure_material(model, "InfoCAD (ohne Angabe)", log)
                C.warn(log, f"Werkstoff {mnr} ist in MAT nicht beschrieben - "
                            f"'{standard_mat}' eingesetzt")
            mname = standard_mat
        sec = qs.get(_ganz(z[9], -1)) if len(z) > 9 else None
        if art.startswith("shell") and sec is None:
            sec = C.ensure_shell_prop(model, None, None, log)
        code = _ganz(z[12], 0) if len(z) > 12 else 0
        gruppe = f"Layer {code >> 16}" if code else "default"
        model.add_element(art, nd, mname, sec, group=gruppe)
        n += 1
    for typ, k in sorted(unbekannt.items()):
        C.warn(log, f"ELEMENTE: {k} Elemente mit Typ {typ} - der Code ist nicht "
                    f"belegt (bekannt sind {', '.join(str(t) for t in EL_TYPEN)}) "
                    "und sie sind nicht gelesen")
    return n


def import_infocad_txt(path: str, model: Model = None, log: list = None,
                       z_nach_unten: bool = False, **options) -> Model:
    """Ein Modell aus der Textausgabe von InfoCADs ``/ExportTxt`` lesen.

    ``z_nach_unten``: Ist das InfoCAD-Modell mit der Z-Achse **nach unten**
    aufgebaut (bei Platten- und Verschlussmodellen ueblich), dreht der Import
    es um 180 Grad um die X-Achse in die Statik3D-Lage (Z nach oben). Das ist
    eine Angabe des Anwenders und keine Messung: in welcher Lage ein Modell
    aufgebaut wurde, steht in der Exportdatei nicht.
    """
    if not os.path.isfile(path):
        raise ImportError(f"{path}: Datei nicht gefunden")
    model = model or Model(os.path.splitext(os.path.basename(path))[0])
    bloecke = bloecke_lesen(path, log)
    if not bloecke:
        raise ImportError(
            f"{os.path.basename(path)} enthaelt keinen BEGIN/END-Block. Das ist "
            "keine Textausgabe von InfoCADs /ExportTxt.")
    if z_nach_unten:
        C.say(log, "Das Modell wird um 180° um die X-Achse gedreht (InfoCAD-Z "
                   "zeigt nach unten, Statik3D-Z nach oben)")
    mat = _werkstoffe(model, bloecke, log)
    qs = _dicken(model, bloecke, log)
    knoten = _knoten(model, bloecke, z_nach_unten, log)
    n_el = _elemente(model, bloecke, knoten, mat, qs, log)

    # Sich selbst abzaehlen - und benennen, was liegen blieb. InfoCAD
    # uebergeht unbekannte Tabellen still; dieser Leser tut es nicht.
    gelesen = {"KNOTEN", "ELEMENTE", "QUERSW", "MAT", "MAT2"}
    C.say(log, f"InfoCAD: {len(knoten)} Knoten, {n_el} Elemente, "
               f"{len(mat)} Werkstoffe, {len(qs)} Schalendicken")
    for name, b in bloecke.items():
        kurz = name.split(".")[0].split("#")[0]
        if kurz in gelesen:
            zustand = "vollstaendig" if b.vollstaendig() else "UNVOLLSTAENDIG"
            C.say(log, f"  {name}: {b.n_ist} Zeilen ({zustand})")
        elif kurz in ERGEBNISTABELLEN:
            C.say(log, f"  {name}: {b.n_ist} Zeilen - Ergebnistabelle, nicht "
                       "gelesen (Statik3D rechnet selbst)")
        else:
            C.warn(log, f"  {name}: {b.n_ist} Zeilen - diese Tabelle wird nicht "
                        "gelesen; ihr Spaltenaufbau ist nicht belegt")
    if not any(k.split(".")[0] in ("FESTH", "FESTHLAYER") for k in bloecke):
        C.warn(log, "Lager und Lasten stehen nicht in der Ausgabe und werden "
                    "nicht uebernommen - sie sind in Statik3D anzulegen")
    else:
        C.warn(log, "Lager (FESTH) sind in der Ausgabe enthalten, werden aber "
                    "nicht gelesen: der Spaltenaufbau der Tabelle ist nicht "
                    "belegt. Sie sind in Statik3D anzulegen")
    if not knoten:
        raise ImportError(
            f"{os.path.basename(path)}: keine Tabelle KNOTEN. Die Befehlsdatei "
            "von /ExportTxt braucht mindestens die Zeilen KNOTEN und ELEMENTE "
            "(unbekannte Namen ueberspringt InfoCAD ohne Meldung).")
    return model
