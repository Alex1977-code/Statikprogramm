"""
Ein gespeichertes Statik3D-Modell (JSON) an ein vorhandenes anhaengen.

Bis zum 22.09.2026 (Befund SV11) uebertrug das Anhaengen nur Werkstoffe,
Querschnitte, Schalendicken, Knoten, Elemente, Knotenlager, Knoten-, Stab-,
Flaechen- und Temperaturlasten, das Eigengewicht und die Staebe - und auch
davon nicht alles: Elemente verloren ``nur``, Exzentrizitaet und
Gelenkfedern, Knotenlager ihre Nichtlinearitaet, Stablasten ihre Teilstrecke,
Staebe ihre Knicklaengen und Kerbfaelle, neue Lastfaelle ihre Eigenschaften.
Alles Uebrige blieb liegen. Gemessen am Hallenrahmen: 72 Kombinationen,
1 Linienlager, 1 Flaechenlager, 2 Ermuedungslasten und 1 Linienlast der
Quelle kamen mit 0 an, und das Protokoll nannte nur Knoten- und
Elementzahl - beide stimmten, also sah es vollstaendig aus.

Jetzt ist **jeder** Schluessel von ``Model.to_dict()`` hier eingeordnet:
uebertragen (:data:`UEBERTRAGEN`), als Einstellung des Ziels behalten
(:data:`ZIEL_BEHAELT`, Abweichungen der Quelle stehen im Protokoll) oder
mit Grund nicht uebertragen (:data:`NICHT_UEBERTRAGEN`, im Protokoll mit
Anzahl). ``tests.test_importers`` prueft, dass kein Schluessel fehlt - ein
kuenftig ergaenztes Modellfeld faellt so nicht wieder still weg.

Nummern: die Knoten der Quelle stehen hinter denen des Ziels (Versatz
``base``), die Elemente ebenso (``e_base``); danach werden Knoten der Quelle,
die auf einem Knoten des Ziels liegen, mit ihm zusammengefuehrt
(``_common.anschluss_zusammenfuehren``) - nur zwischen Ziel und Quelle, nie
innerhalb eines Teils: dort liegen Knoten absichtlich aufeinander (die
Seiten einer Kontaktfuge). Namen: was es im Ziel schon gibt, bekommt einen
eindeutigen neuen Namen (``S1`` -> ``S1_2``), und jeder Verweis der Quelle
folgt ihm - auch die Gruppe der Elemente (sie nennt den Koerper) und die
Zustaende der Ermuedungslasten, soweit sie Kombinationen sind. Koerper- und
Flaechennamen gelten auch dann als vergeben, wenn im Ziel nur eine
Elementgruppe so heisst. Stellungen
gehen nicht mit; nennt eine Situation der Quelle eine, die das Ziel unter
demselben Namen hat, zeigt sie auf einen neuen Namen, den die
Modellpruefung als unbekannt meldet (``_stellungsverweise``, auch bei einer
Stellung namens 'Grundstellung': von ihr wirken in einer Situation die
Abschaltungen, und die Warnung sagt, dass nur diese anzulegen sind).
Werkstoffe, Querschnitte, Dicken, Kombinationen und Ermuedungslasten mit
gleichem Namen **und** gleichem Inhalt werden nicht doppelt angelegt.
Lastfaelle gleichen Namens werden wie bisher zusammengelegt; weichen ihre
Eigenschaften ab, gelten die des Ziels, und das Protokoll nennt die
Abweichung.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, is_dataclass

import numpy as np

from ..model import Model, ACTION_CATEGORIES, GRUNDSTELLUNG
from . import _common as C

#: Uebertragene Schluessel von Model.to_dict() -> Bezeichnung im Protokoll
UEBERTRAGEN: dict[str, str] = {
    "nodes": "Knoten", "elements": "Elemente",
    "materials": "Werkstoffe", "sections": "Querschnitte", "shells": "Flächendicken",
    "federn": "Federeigenschaften", "grenzschichten": "Grenzschichteigenschaften",
    "supports": "Knotenlager", "line_supports": "Linienlager",
    "surface_supports": "Flächenlager",
    "lines": "Linien", "flaechen": "Flächen", "koerper": "Volumenkörper",
    "hinges": "Stabendgelenke", "members": "Stäbe",
    "load_cases": "Lastfälle", "combinations": "Kombinationen",
    "fatigue_loads": "Ermüdungslasten",
    "joints": "Anschlüsse", "verformungsgrenzen": "Verformungsgrenzen",
    "beulfelder": "Beulfelder", "volumenbereiche": "Volumenbereiche",
    "lasteinleitungen": "Lasteinleitungen",
    "kontaktbedingungen": "Kontaktbedingungen", "contact_supports": "einseitige Lager",
    "gap_elements": "Spaltelemente", "kopplungen": "Kopplungen",
    "contact_pairs": "Kontaktpaare", "getrennte_knoten": "getrennte Fugen",
    "kontakt_ausnahmen": "Kontaktausnahmen", "importhinweise": "Importhinweise",
    "punktmassen": "Punktmassen", "daempfer": "Dämpfer", "starrkoerper": "Starrkörper",
    "subsysteme": "Subsysteme", "layer": "Layer", "unterlagen": "Unterlagen",
    "situationen": "Situationen", "wasserdruecke": "Wasserdruck-Generierer",
    "winde": "Wind-Generierer", "schwingungen": "Schwingungsnachweise",
    "schweissnaehte": "Schweißnähte", "bemassungen": "Bemaßungen",
}

#: Einstellungen und Kopfangaben: es gelten die des Ziels. Weichen die der
#: Quelle ab, nennt das Protokoll sie (ausser Format, Name, Metadaten und dem
#: aktiven Lastfall - die sind keine Rechengroessen).
ZIEL_BEHAELT: dict[str, str] = {
    "format": "Dateiformat", "name": "Modellname", "meta": "Projektangaben",
    "active_case": "aktiver Lastfall",
    "netz": "Netzeinstellungen (Verfeinerungen, Feldpunkte und Kantenlängen je "
            "Körper der Quelle werden übertragen)",
    "design": "Nachweiseinstellungen", "plastizitaet": "Plastizität",
    "knotendilatation": "knotengemittelte Dilatation",
    "randspannung": "Randspannung der Volumen (σ·n = 0 an freien Oberflächen oder gemittelt)",
    "bemassung_einstellung": "Bemaßungseinstellung", "werteskala": "Werteskala",
    "bericht_rahmen": "Berichtsrahmen", "einheiten": "Einheiten",
}
_OHNE_VERGLEICH = ("format", "name", "meta", "active_case")

#: Nicht uebertragbar: (Bezeichnung, Grund und was zu tun ist)
NICHT_UEBERTRAGEN: dict[str, tuple[str, str]] = {
    "bericht": ("Berichtseinträge",
                "sie zeigen Ergebnisse und Ansichten des Quellmodells - im Ziel nach "
                "der Rechnung neu aus der Ansicht übernehmen"),
    # Was eine Stellung bewegt, so wie positions.Stellung._bewegte_knoten es
    # tut. Bis zum 23.09.2026 stand hier "bewegt das ganze System"; am
    # Beispiel 'frame' (17 Knoten) bewegt eine Gruppe aus 6 Elementen 7
    # Knoten, eine Stellung, die nur ein Lager abschaltet, keinen, und ohne
    # Gruppe auch die Knoten auf einem Linienlager (nur Knotenlager halten).
    "stellungen": ("Stellungen",
                   "eine Stellung, die verschiebt oder dreht, bewegt ohne Gruppenangabe "
                   "alle Knoten ohne Knotenlager, also auch die des Ziels (mit "
                   "Gruppenangabe die Knoten dieser Elementgruppen) - im Ziel neu anlegen; "
                   "Situationen, die eine Stellung nennen, meldet die Modellprüfung"),
}

#: Zusatz zur Warnung ueber umbenannte Stellungsverweise, wenn die Stellung
#: 'Grundstellung' heisst. Von ihr wirken in einer Situation nur die
#: Abschaltungen (Model.aktive_elemente); Lage, Lager und Gelenke uebergeht
#: situationen.situationsmodell. Wer sie ganz unter dem neuen Namen anlegt,
#: rechnet anders als in der Quelle. Gemessen am 24.09.2026 (Rahmen 'frame',
#: Stellung hebt um 1,0 m und schaltet den rechten Stiel ab, 10 kN
#: waagerecht): allein |u| = 3,8300 mm, ganz angelegt 12,5294 mm, nur die
#: Abschaltung angelegt 3,8300 mm.
_GRUNDSTELLUNG_HINWEIS = (
    f" Von einer Stellung namens '{GRUNDSTELLUNG}' wirken in einer Situation nur die "
    "abgeschalteten Stäbe, Flächen und Volumen, nicht ihre Lage (Ausgangsstellung, "
    "Verschiebung, Drehung), Lager und Gelenke - unter dem neuen Namen also nur die "
    "Abschaltungen anlegen, sonst rechnet die Situation anders als in der Quelle.")

#: Die Lastlisten eines Lastfalls (Schluessel von LoadCase.to_dict())
LASTLISTEN = ("nodal_loads", "beam_loads", "face_loads", "temp_loads", "geometrielasten",
              "linienlasten", "zwangsverformungen", "vorspannungen", "uebermasse", "gravity")

#: Alle Schluessel von LoadCase.to_dict(), die das Anhaengen behandelt
LASTFALL_EINGEORDNET = ("name",) + tuple(C.LASTFALL_EIGENSCHAFTEN) + LASTLISTEN

_EIGENSCHAFT_TEXT = {"category": "Einwirkung", "psi": "ψ-Beiwerte",
                     "exclusive_group": "Exklusivgruppe", "situation": "Situation",
                     "theorie": "Theorie", "grundlast": "Grundlast",
                     "gamma_sup": "γ_sup", "gamma_inf": "γ_inf"}
#: Eigenschaften ohne Einfluss auf die Rechnung - keine Meldung bei Abweichung
_OHNE_WIRKUNG = ("description", "nummer")


def _normal(x):
    """Zahlen und Folgen einheitlich: 7850 und 7850.0 sind derselbe Wert, ein
    Tupel im Speicher ist nach dem JSON-Umlauf eine Liste."""
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    if isinstance(x, dict):
        return {str(k): _normal(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_normal(v) for v in x]
    return str(x)


def _inhalt(obj) -> str:
    """Inhalt eines Objekts ohne seinen Namen - zum Vergleich gleichnamiger."""
    d = asdict(obj) if is_dataclass(obj) else dict(obj)
    d.pop("name", None)
    return json.dumps(_normal(d), sort_keys=True)


def _einstellung(m: Model, key: str) -> str:
    v = getattr(m, key, None)
    if v is None:
        return "null"
    if hasattr(v, "to_dict"):
        v = v.to_dict()
    elif is_dataclass(v):
        v = asdict(v)
    if key == "netz" and isinstance(v, dict):
        v = {k: x for k, x in v.items()
             if k not in ("verfeinerungen", "feldpunkte", "koerper_h", "quelle")}
    return json.dumps(v, sort_keys=True, default=str)


def _anzahl(v) -> int:
    if v is None:
        return 0
    if isinstance(v, (list, tuple, dict, set)):
        return len(v)
    return int(bool(v))


def _flach(obj):
    """Flache Kopie eines Datenobjekts samt aller Attribute im __dict__ (auch
    ``_geo``); Listen darin teilt sie noch mit dem Original - der Aufrufer
    ersetzt sie. Ohne den Umweg ueber __reduce_ex__ von copy.copy."""
    k = object.__new__(type(obj))
    k.__dict__.update(obj.__dict__)
    return k


def _schwere(g) -> list:
    if g is None:
        return [0.0, 0.0, 0.0]
    return [float(x) for x in np.asarray(g, float).ravel()]


class _Anhang:
    """Ein Anhaengevorgang: Versatz der Nummern und Karten der Umbenennungen."""

    def __init__(self, ziel: Model, quelle: Model, log):
        self.z, self.q, self.log = ziel, quelle, log
        self.base = ziel.nn
        self.e_base = len(ziel.elements)
        self.n_lager = (len(ziel.supports), len(ziel.line_supports),
                        len(ziel.surface_supports))
        self.umbenannt: dict[str, dict] = {}     # Art -> {alt: neu}
        self.gleich: dict[str, list] = {}        # Art -> gleich vorhandene Namen
        self.zusammengelegt: list = []           # Lastfaelle, die es im Ziel schon gab
        # Stellungsname in Situationen der Quelle -> neuer Name (siehe _stellungsverweise)
        self.stellungsverweis: dict[str, str] = {}

    # -- Nummern und Namen --------------------------------------------------
    def kn(self, n) -> int:
        return int(n) + self.base

    def kns(self, liste) -> list:
        return [self.kn(n) for n in (liste or [])]

    def el(self, e) -> int:
        return int(e) + self.e_base

    def els(self, liste) -> list:
        return [self.el(e) for e in (liste or [])]

    def neu(self, art: str, name):
        if not name:
            return name
        return self.umbenannt.get(art, {}).get(name, name)

    def neue(self, art: str, namen) -> list:
        return [self.neu(art, n) for n in (namen or [])]

    def namen_vergeben(self, art: str, vorhanden, namen, gleich=None) -> None:
        """Namen der Quelle, die es im Ziel schon gibt, eindeutig machen.

        ``gleich(name)`` sagt, ob das gleichnamige Objekt auch inhaltlich
        gleich ist - dann wird es nicht doppelt angelegt."""
        vorhanden = set(vorhanden)
        belegt = vorhanden | set(namen)
        karte, gl = {}, []
        for n in namen:
            if n not in vorhanden:
                continue
            if gleich is not None and gleich(n):
                gl.append(n)
                continue
            neu = C.unique_name(belegt, n)
            belegt.add(neu)
            karte[n] = neu
        self.umbenannt[art] = karte
        self.gleich[art] = gl

    # -- Ablauf -------------------------------------------------------------
    def ausfuehren(self, tol: float) -> None:
        self._namen()
        self._eigenschaften()
        self._netz()
        self._lager()
        self._geometrie()
        self._lastfaelle()
        self._nachweise()
        self._kontakte()
        self._uebrige()
        self._netzeinstellungen()
        self._melden()
        # Bis zur Nachbesserung vom 23.09.2026 lief hier merge_duplicate_nodes
        # ueber das ganze Modell (wie schon vor SV11). Es verschweisste auch,
        # was in einem Teil absichtlich aufeinanderliegt. Gemessen: ein
        # Spaltelement (1, 2) des Ziels wurde (1, 1); eine Quelle mit
        # ausgefuehrter Fuge "Ausfall bei Zug" (24 Spaltelemente, 200 kN Zug)
        # trug danach -198 152,7 N am Fundament statt 0,0 N, und die Fuge
        # stand weiter auf "ausgefuehrt" - fugen.kontaktfuge_ausfuehren lehnt
        # ein neues Trennen dann ab ("schon ausgeführt").
        # Jetzt schliesst nur die Quelle an das Ziel an.
        n, unklar = C.anschluss_zusammenfuehren(self.z, self.base, tol)
        if n == 1:
            C.say(self.log, "1 Knoten der Quelle lag auf einem Knoten des Ziels und "
                            "wurde zusammengeführt")
        elif n:
            C.say(self.log, f"{n} Knoten der Quelle lagen auf Knoten des Ziels und "
                            "wurden zusammengeführt")
        if unklar:
            x, y, z = unklar[0]
            C.warn(self.log,
                   f"An {len(unklar)} Stelle{'' if len(unklar) == 1 else 'n'} liegen in "
                   "Ziel oder Quelle schon mehrere Knoten aufeinander (etwa die beiden "
                   "Seiten einer Kontaktfuge), und ein Knoten des anderen Teils liegt "
                   "dazu. Dort wurde nichts "
                   "zusammengeführt, weil nicht eindeutig ist, welcher Knoten anschließen "
                   f"soll - die erste bei ({x:g}, {y:g}, {z:g}) m. Bitte dort prüfen, ob "
                   "Ziel und Quelle verbunden sein sollen.")

    def _namen(self) -> None:
        z, q = self.z, self.q
        for art in ("materials", "sections", "shells", "federn", "grenzschichten"):
            zd, qd = getattr(z, art), getattr(q, art)
            self.namen_vergeben(art, zd, list(qd),
                                lambda n, zd=zd, qd=qd: _inhalt(zd[n]) == _inhalt(qd[n]))
        # Die Elemente eines Koerpers oder einer Flaeche tragen deren Namen als
        # Gruppe (_netz), und fugen.py loest ueber die Gruppe. Also gilt ein
        # Name auch dann als vergeben, wenn im Ziel nur eine Elementgruppe so
        # heisst, ohne Koerper oder Flaeche (etwa ein DXF-Layer). Gemessen vor
        # dieser Zeile (23.09.2026): Zielbloecke mit der Gruppe 'V1' links an
        # einer Quelle mit Koerpern V1/V2 und Fuge KB1 auf V1 - KB1 haengte
        # auch den Zielblock um (Elemente [0, 2] statt [2]), und die beiden
        # Zielbloecke teilten danach 2 statt 4 Knoten, ohne Meldung.
        gruppen_z = {str(e.group) for e in z.elements if e.group}
        for art in ("lines", "flaechen", "koerper", "members", "hinges", "situationen",
                    "joints", "verformungsgrenzen", "beulfelder", "volumenbereiche",
                    "lasteinleitungen", "subsysteme", "layer", "unterlagen",
                    "wasserdruecke", "winde", "schwingungen", "schweissnaehte",
                    "bemassungen"):
            vorhanden = set(getattr(z, art) or {})
            if art in ("flaechen", "koerper"):
                vorhanden |= gruppen_z
            self.namen_vergeben(art, vorhanden, list(getattr(q, art) or {}))
        # Fugen: Kontaktbedingungen und Kontaktpaare teilen sich die Namen -
        # ein Uebermass, ein Spaltelement und eine Kopplung nennen die Fuge
        # beim Namen, gleich ob es eine Bedingung dazu gibt.
        fugen_z = set(z.kontaktbedingungen) | {str(c.name) for c in z.contact_pairs}
        fugen_q = list(q.kontaktbedingungen)
        for c in q.contact_pairs:
            if str(c.name) not in fugen_q:
                fugen_q.append(str(c.name))
        self.namen_vergeben("fugen", fugen_z, fugen_q)
        self._stellungsverweise()

        def kombi_gleich(n):
            k = copy.deepcopy(q.combinations[n])
            k.situation = self.neu("situationen", k.situation)
            return _inhalt(z.combinations[n]) == _inhalt(k)
        self.namen_vergeben("combinations", z.combinations, list(q.combinations), kombi_gleich)
        # Erst nach den Kombinationen: ein Zustand der Ermuedungslast darf eine
        # Kombination sein, und verglichen wird mit dem Namen, den sie im Ziel
        # bekommt - sonst galt FAT-Q der Quelle (auf ihre CO1) als gleich mit
        # FAT-Q des Ziels (auf dessen andere CO1) und fiel weg (Gegenprobe
        # 23.09.2026).
        self.namen_vergeben("fatigue_loads", z.fatigue_loads, list(q.fatigue_loads),
                            lambda n: _inhalt(z.fatigue_loads[n])
                            == _inhalt(self._ermuedung(q.fatigue_loads[n])))

    def _stellungsverweise(self) -> None:
        """Stellungen gehen nicht mit (:data:`NICHT_UEBERTRAGEN`). Nennt eine
        Situation der Quelle eine Stellung, die das Ziel unter demselben Namen
        hat, bekommt der Verweis einen neuen Namen, den es im Ziel nicht gibt -
        auch der Name GRUNDSTELLUNG (siehe den Kommentar in der Schleife).

        Warum: sonst loeste ``Model.stellung`` ihn still auf die Stellung des
        Ziels auf, und ``Model.check`` meldete nichts (es prueft nur, ob der
        Name existiert). Gemessen vor dieser Zeile (23.09.2026): Rahmen als
        Quelle, Stellung 'Offen' hebt die ungelagerten Knoten um 1,0 m,
        10 kN waagerecht in Situation 'S-offen'; das Ziel hat eine Stellung
        'Offen' ohne Verschiebung. Allein |u| = 4,7572 mm am Lastknoten,
        angehaengt 1,7876 mm - gerechnet in der Stellung des Ziels. Mit dem
        neuen Namen meldet die Modellpruefung die Situation ("Stellung ...
        unbekannt"), und die Rechnung bricht in ``situationsmodell`` mit
        derselben Meldung ab, bis der Anwender die Stellung unter diesem Namen
        anlegt oder die Situation umstellt.

        Auch eine inhaltlich gleiche Stellung des Ziels wird nicht benutzt:
        was sie trifft, haengt an Namen (Drehgruppen, abgeschaltete Staebe,
        Flaechen, Volumen), und gleichnamige Objekte der Quelle sind
        umbenannt. Ob sie im Gesamtmodell auf die Quelle wirkt wie allein,
        laesst sich am Inhalt nicht ablesen.

        Belegt sind fuer den neuen Namen auch die Stellungsnamen der Quelle
        selbst, damit zwei verschiedene Stellungen der Quelle nicht auf
        denselben Namen fallen."""
        z, q = self.z, self.q
        genannt = []
        for s in q.situationen.values():
            if s.stellung and s.stellung not in genannt:
                genannt.append(s.stellung)
        belegt = ({str(getattr(s, "name", "")) for s in (z.stellungen or [])}
                  | {str(getattr(s, "name", "")) for s in (q.stellungen or [])}
                  | set(genannt))
        for n in genannt:
            # Aufgeloest wird wie in Model.aktive_elemente (Model.stellung),
            # ohne Ausnahme fuer GRUNDSTELLUNG. situationen.situationsmodell
            # uebergeht bei diesem Namen nur Lage, Lager und Gelenke
            # (st.anwenden); die Abschaltung ihrer Staebe, Flaechen und
            # Volumen holt Model.aktive_elemente ueber den Namen. Bliebe der
            # Verweis stehen, rechnete die Situation still mit der Abschaltung
            # der gleichnamigen Stellung des Ziels. Gemessen am 24.09.2026 am
            # Stand 159edab, der den Namen ausnahm: Kragarm aus HEB 300 mit
            # Stuetzstab, die Stellung 'Grundstellung' der Quelle schaltet den
            # Stuetzstab ab, das Ziel hat eine leere 'Grundstellung'; allein
            # uz = -4,1412 mm, angehaengt -0,0064 mm, ohne Meldung. Was unter
            # dem neuen Namen anzulegen ist, sagt die Warnung in _melden.
            if z.stellung(n) is not None:
                neu = C.unique_name(belegt, n)
                belegt.add(neu)
                self.stellungsverweis[n] = neu

    def zustand(self, name):
        """Zustand einer Ermuedungslast: ein Lastfall behaelt seinen Namen
        (gleichnamige werden zusammengelegt), eine Kombination der Quelle
        folgt ihrer Umbenennung."""
        if name and name not in self.q.load_cases and name in self.q.combinations:
            return self.neu("combinations", name)
        return name

    def _ermuedung(self, f):
        """Kopie einer Ermuedungslast der Quelle mit den Zustaenden, wie sie
        im Ziel heissen. Gemessen vor dieser Zeile (23.09.2026): Quelle CO1 =
        {LF1: 1,0; LF2: 1,0}, Ziel CO1 = {LF1: 1,0; LF2: 0,1}; die Kombination
        der Quelle hiess danach CO1_2, ihre Ermuedungslast rechnete aber mit
        'CO1' des Ziels - ohne Meldung, Model.check() fand nichts. Am CBG sind
        20 von 20 Ermuedungslasten Kombinationszustaende."""
        k = copy.deepcopy(f)
        k.case_max = self.zustand(f.case_max)
        k.case_min = self.zustand(f.case_min)
        k.folge = [self.zustand(x) for x in (f.folge or [])]
        return k

    def _eigenschaften(self) -> None:
        for art in ("materials", "sections", "shells", "federn", "grenzschichten"):
            zd = getattr(self.z, art)
            for name, obj in getattr(self.q, art).items():
                neu = self.neu(art, name)
                if neu in zd:                  # gleich vorhanden
                    continue
                o = copy.deepcopy(obj)
                o.name = neu
                zd[neu] = o

    def _sec(self, e) -> str:
        """Querschnitt, Dicke, Feder- oder Grenzschichteigenschaft - je nach Typ."""
        s = e.sec
        if not s:
            return s
        typ = str(e.typ)
        if typ == "feder":
            arten = ("federn", "sections")
        elif typ.startswith("grenzschicht"):
            arten = ("grenzschichten", "shells")
        elif typ.startswith(("shell", "ebene")):
            arten = ("shells", "sections")
        else:
            arten = ("sections", "shells")
        for art in arten:
            if s in (getattr(self.q, art) or {}):
                return self.neu(art, s)
        return s

    def _netz(self) -> None:
        """Knoten und Elemente - jedes Element mit **allen** Feldern.

        Nicht ueber ``add_element`` Feld fuer Feld und nicht mit deepcopy:
        das kostete am Pruefnetz (90 000 hex8, 45 000 Flaechenlasten) 1,86 s
        gegen 0,57 s des alten, unvollstaendigen Wegs. Flach kopiert wie
        ``Element.kopie``, der Typ einmal vorab geprueft (dieselbe Meldung wie
        ``add_element``): 0,75 s gegen 0,59 s (22.09.2026, geteilte Maschine,
        zweiter von zwei Laeufen)."""
        from ..elemente import ELEMENTE
        z, q = self.z, self.q
        unbekannt = sorted({e.typ for e in q.elements} - set(ELEMENTE))
        if unbekannt:
            raise KeyError(f"Elementtyp '{unbekannt[0]}' unbekannt: {', '.join(ELEMENTE)}")
        if q.nn:
            z.add_nodes(q.nodes)
        base = self.base
        mat = self.umbenannt.get("materials", {})
        linien = self.umbenannt.get("lines", {})
        # Die Gruppe eines Elements nennt seinen Volumenkoerper (mesher3d,
        # sweep, rfem6_db: group=koerper.name) oder seine Flaeche (mesher,
        # rfem6_db); fugen.py sucht den Koerper einer Kontaktbedingung ueber
        # sie. Blieb sie beim Umbenennen stehen, trug der Koerper V1_2 der
        # Quelle Elemente der Gruppe 'V1', und ihre Fuge loeste den Block des
        # anderen Koerpers (gemessen 23.09.2026: allein unten geloest,
        # angehaengt oben). Wie transformieren.kopieren: Koerper vor Flaeche.
        gruppen = {**self.umbenannt.get("flaechen", {}), **self.umbenannt.get("koerper", {})}
        sec: dict = {}
        woelb = False
        for e in q.elements:
            k = _flach(e)
            k.nodes = [int(n) + base for n in e.nodes]
            k.hinges = list(e.hinges)
            k.hinge_springs = list(e.hinge_springs)
            if e.exzentrizitaet:
                k.exzentrizitaet = [list(x) if isinstance(x, (list, tuple)) else x
                                    for x in e.exzentrizitaet]
            else:
                k.exzentrizitaet = []
            k.mat = mat.get(e.mat, e.mat)
            if e.sec:
                s = sec.get((e.typ, e.sec))
                if s is None:
                    s = sec[(e.typ, e.sec)] = self._sec(e)
                k.sec = s
            if e.line:
                k.line = linien.get(e.line, e.line)
            if gruppen and e.group in gruppen:
                k.group = gruppen[e.group]
            woelb = woelb or bool(e.woelb)
            z.elements.append(k)
        if woelb:
            # wie add_element: der Zwischenspeicher der Woelbknoten gilt nicht mehr
            z._woelb_version = getattr(z, "_woelb_version", 0) + 1

    def _lager(self) -> None:
        z, q = self.z, self.q
        for s in q.supports:
            k = copy.deepcopy(s)
            k.node = self.kn(s.node)
            z.supports.append(k)
        for ls in q.line_supports:
            k = copy.deepcopy(ls)
            k.nodes = self.kns(ls.nodes)
            k.line = self.neu("lines", ls.line)
            k.linien = self.neue("lines", ls.linien)
            z.line_supports.append(k)
        for ss in q.surface_supports:
            k = copy.deepcopy(ss)
            k.elements = self.els(ss.elements)
            k.nodes = self.kns(ss.nodes)
            k.flaechen = self.neue("flaechen", ss.flaechen)
            k.gruppen = [[g[0], g[1], self.kns(g[2])] + copy.deepcopy(list(g[3:]))
                         for g in (ss.gruppen or [])]
            z.surface_supports.append(k)

    def _geometrie(self) -> None:
        z, q = self.z, self.q
        for name, ln in q.lines.items():
            k = copy.deepcopy(ln)
            k.name = self.neu("lines", name)
            k.nodes = self.kns(ln.nodes)
            z.lines[k.name] = k
        for name, f in q.flaechen.items():
            k = copy.deepcopy(f)
            k.name = self.neu("flaechen", name)
            k.linien = self.neue("lines", f.linien)
            k.oeffnungen = [self.neue("lines", o) for o in (f.oeffnungen or [])]
            k.gelenklinien = self.neue("lines", f.gelenklinien)
            k.integrierte_linien = self.neue("lines", f.integrierte_linien)
            k.dicke = self.neu("shells", f.dicke)
            k.material = self.neu("materials", f.material)
            k.elemente = self.els(f.elemente)
            k.randseiten = [[self.el(r[0])] + list(r[1:]) for r in (f.randseiten or [])]
            k.ecken = self.kns(f.ecken)
            k.integrierte_knoten = self.kns(f.integrierte_knoten)
            z.flaechen[k.name] = k
        for name, kp in q.koerper.items():
            k = copy.deepcopy(kp)
            k.name = self.neu("koerper", name)
            k.flaechen = self.neue("flaechen", kp.flaechen)
            k.material = self.neu("materials", kp.material)
            k.elemente = self.els(kp.elemente)
            z.koerper[k.name] = k
        for name, h in q.hinges.items():
            k = copy.deepcopy(h)
            k.name = self.neu("hinges", name)
            k.elemente = self.els(h.elemente)
            z.hinges[k.name] = k
        for name, m in q.members.items():
            k = copy.deepcopy(m)
            k.name = self.neu("members", name)
            k.elements = self.els(m.elements)
            z.members[k.name] = k
        for name, s in q.situationen.items():
            k = copy.deepcopy(s)
            k.name = self.neu("situationen", name)
            k.deaktiviert = self.els(s.deaktiviert)
            k.stellung = self.stellungsverweis.get(s.stellung, s.stellung)
            z.situationen[k.name] = k

    # -- Lastfaelle ---------------------------------------------------------
    def _lastfaelle(self) -> None:
        z, q = self.z, self.q
        schwere_vorher = {n: _schwere(lc.gravity) for n, lc in z.load_cases.items()}
        schwere_quelle = {n: _schwere(lc.gravity) for n, lc in q.load_cases.items()}
        for name, lc in q.load_cases.items():
            sit = self.neu("situationen", lc.situation)
            ziel = z.load_cases.get(name)
            if ziel is None:
                if lc.category not in ACTION_CATEGORIES:
                    C.warn(self.log, f"Lastfall '{name}': Einwirkung '{lc.category}' ist "
                                     "unbekannt - als 'Q' angelegt; bitte im Lastfall prüfen")
                ziel = C.get_or_add_case(z, name, vorlage=lc, situation=sit)
            else:
                self.zusammengelegt.append(name)
                self._eigenschaften_vergleichen(ziel, lc, sit)
            self._lasten(ziel, lc)
            if any(schwere_quelle[name]):
                ziel.gravity = list(schwere_quelle[name])
        # Das Eigengewicht gilt je Lastfall fuer **alle** Elemente. Hatten Ziel
        # und Quelle in einem Lastfall verschiedenes, erfasst es jetzt auch
        # die Elemente des anderen Teils - oder fehlt ihnen.
        if self.e_base and q.elements:
            for name, lc in z.load_cases.items():
                gz = schwere_vorher.get(name, [0.0, 0.0, 0.0])
                gq = schwere_quelle.get(name, [0.0, 0.0, 0.0])
                if np.allclose(gz, gq):
                    continue
                jetzt = _schwere(lc.gravity)
                C.warn(self.log,
                       f"Lastfall '{name}': Eigengewicht im Ziel {_g_text(gz)}, in der Quelle "
                       f"{_g_text(gq)} - es gilt jetzt {_g_text(jetzt)} für alle Elemente, "
                       "auch für die des anderen Teils. Bitte im Lastfall prüfen.")

    def _eigenschaften_vergleichen(self, ziel, lc, sit) -> None:
        abw = []
        for f in C.LASTFALL_EIGENSCHAFTEN:
            if f in _OHNE_WIRKUNG:
                continue
            a = getattr(ziel, f)
            b = sit if f == "situation" else getattr(lc, f)
            if json.dumps(a, default=str) != json.dumps(b, default=str):
                abw.append(f"{_EIGENSCHAFT_TEXT.get(f, f)} (Ziel {_wert(a)}, Quelle {_wert(b)})")
        if abw:
            C.warn(self.log, f"Lastfall '{lc.name}' gibt es im Ziel schon - die Lasten der "
                             "Quelle kommen dazu, es gelten die Eigenschaften des Ziels. "
                             "In der Quelle abweichend: " + "; ".join(abw)
                   + ". Bitte im Lastfall prüfen.")

    def _lasten(self, ziel, lc) -> None:
        # Auch die aus Objektlasten verteilten Elementlasten (``_geo``) gehen
        # mit: Model.from_dict hat sie beim Lesen der Quelle erzeugt, und das
        # Ziel hat schon ein Netz - vernetzt wird vor der Rechnung nur, was
        # keines hat. deepcopy behaelt das Kennzeichen.
        # Flach kopiert (das ``_geo``-Kennzeichen steht im __dict__ und geht
        # mit), die Listen darin neu - diese Lasten sind bei grossen Netzen
        # die Masse; deepcopy war der groessere Teil der 1,86 s (siehe _netz).
        for l in lc.nodal_loads:
            k = _flach(l)
            k.node = self.kn(l.node)
            k.F = list(l.F)
            ziel.nodal_loads.append(k)
        for l in lc.beam_loads:
            k = _flach(l)
            k.elem = self.el(l.elem)
            k.q = list(l.q)
            k.q2 = None if l.q2 is None else list(l.q2)
            ziel.beam_loads.append(k)
        for l in lc.face_loads:
            k = _flach(l)
            k.elem = self.el(l.elem)
            k.direction = None if l.direction is None else list(l.direction)
            ziel.face_loads.append(k)
        for l in lc.temp_loads:
            k = _flach(l)
            k.elem = self.el(l.elem)
            ziel.temp_loads.append(k)
        for g in lc.geometrielasten:
            k = copy.deepcopy(g)
            k.ziel = self.neu("koerper" if g.art == "koerper" else "flaechen", g.ziel)
            art = (k.verlauf or {}).get("art")
            if art in ("wasser", "wind") and k.verlauf.get("name"):
                k.verlauf["name"] = self.neu("wasserdruecke" if art == "wasser" else "winde",
                                             k.verlauf["name"])
            ziel.geometrielasten.append(k)
        for l in lc.linienlasten:
            k = copy.deepcopy(l)
            k.ziel = self.neu("lines" if l.art == "linie" else "members", l.ziel)
            ziel.linienlasten.append(k)
        for zv in lc.zwangsverformungen:
            k = copy.deepcopy(zv)
            k.node = self.kn(zv.node)
            ziel.zwangsverformungen.append(k)
        for v in (lc.vorspannungen or []):
            k = copy.deepcopy(v)
            k.ziel = self.neu("koerper" if v.art == "koerper" else "members", v.ziel)
            ziel.vorspannungen.append(k)
        for u in (lc.uebermasse or []):
            k = copy.deepcopy(u)
            k.ziel = self.neu("fugen", u.ziel)
            ziel.uebermasse.append(k)

    # -- Kombinationen, Ermuedung, Nachweisobjekte ---------------------------
    def _nachweise(self) -> None:
        z, q = self.z, self.q
        for name, c in q.combinations.items():
            if name in self.gleich["combinations"]:
                continue
            k = copy.deepcopy(c)
            k.name = self.neu("combinations", name)
            k.situation = self.neu("situationen", c.situation)
            z.combinations[k.name] = k
        for name, f in q.fatigue_loads.items():
            if name in self.gleich["fatigue_loads"]:
                continue
            k = self._ermuedung(f)
            k.name = self.neu("fatigue_loads", name)
            z.fatigue_loads[k.name] = k
        for name, j in q.joints.items():
            k = copy.deepcopy(j)
            k.name = self.neu("joints", name)
            k.elem = self.el(j.elem)
            k.ermuedung = self.neue("fatigue_loads", j.ermuedung)
            z.joints[k.name] = k
        for name, v in q.verformungsgrenzen.items():
            k = copy.deepcopy(v)
            k.name = self.neu("verformungsgrenzen", name)
            k.stab = self.neu("members", v.stab)
            k.knoten = self.kns(v.knoten)
            z.verformungsgrenzen[k.name] = k
        for name, b in q.beulfelder.items():
            k = copy.deepcopy(b)
            k.name = self.neu("beulfelder", name)
            k.elemente = self.els(b.elemente)
            z.beulfelder[k.name] = k
        for name, v in q.volumenbereiche.items():
            k = copy.deepcopy(v)
            k.name = self.neu("volumenbereiche", name)
            k.elemente = self.els(v.elemente)
            z.volumenbereiche[k.name] = k
        for name, le in q.lasteinleitungen.items():
            k = copy.deepcopy(le)
            k.name = self.neu("lasteinleitungen", name)
            k.knoten = self.kn(le.knoten)
            k.stab = self.neu("members", le.stab)
            z.lasteinleitungen[k.name] = k

    def _kontakte(self) -> None:
        z, q = self.z, self.q
        for name, kb in q.kontaktbedingungen.items():
            k = copy.deepcopy(kb)
            k.name = self.neu("fugen", name)
            k.flaechennamen = self.neue("flaechen", kb.flaechennamen)
            k.gegenflaechen = self.neue("flaechen", kb.gegenflaechen)
            k.koerpernamen = self.neue("koerper", kb.koerpernamen)
            k.gegenkoerper = self.neue("koerper", kb.gegenkoerper)
            z.kontaktbedingungen[k.name] = k
        for c in q.contact_supports:
            k = copy.deepcopy(c)
            k.node = self.kn(c.node)
            z.contact_supports.append(k)
        for g in q.gap_elements:
            k = copy.deepcopy(g)
            k.node_a, k.node_b = self.kn(g.node_a), self.kn(g.node_b)
            k.group = self.neu("fugen", g.group)
            z.gap_elements.append(k)
        for kp in q.kopplungen:
            k = copy.deepcopy(kp)
            k.node_a, k.node_b = self.kn(kp.node_a), self.kn(kp.node_b)
            k.gruppe = self.neu("fugen", kp.gruppe)
            z.kopplungen.append(k)
        for cp in q.contact_pairs:
            k = copy.deepcopy(cp)
            k.name = self.neu("fugen", cp.name)
            k.slave_nodes = self.kns(cp.slave_nodes)
            k.master_elements = self.els(cp.master_elements)
            k.master_faces = [self.kns(f) for f in (cp.master_faces or [])]
            k.gegenkoerper = self.neue("koerper", cp.gegenkoerper)
            k.knotenflaechen = {self.kn(n): float(a)
                                for n, a in (cp.knotenflaechen or {}).items()}
            k.rand_knoten = self.kns(cp.rand_knoten)
            z.contact_pairs.append(k)
        for name, paare in (q.getrennte_knoten or {}).items():
            z.getrennte_knoten.setdefault(self.neu("fugen", name), []).extend(
                [[self.kn(a), self.kn(b)] for a, b in paare])
        for a, b in (q.kontakt_ausnahmen or []):
            z.kontakt_ausnahmen.append([self.neu("koerper", a), self.neu("koerper", b)])

    def _uebrige(self) -> None:
        z, q = self.z, self.q
        z.importhinweise.extend(copy.deepcopy(list(q.importhinweise or [])))
        for pm in q.punktmassen:
            k = copy.deepcopy(pm)
            k.node = self.kn(pm.node)
            z.punktmassen.append(k)
        for d in q.daempfer:
            k = copy.deepcopy(d)
            k.node_a = self.kn(d.node_a)
            if int(d.node_b) >= 0:            # -1 = gegen den Boden
                k.node_b = self.kn(d.node_b)
            z.daempfer.append(k)
        for sk in q.starrkoerper:
            k = copy.deepcopy(sk)
            k.master, k.slaves = self.kn(sk.master), self.kns(sk.slaves)
            z.starrkoerper.append(k)
        n_s, n_ls, n_ss = self.n_lager
        for name, s in q.subsysteme.items():
            k = copy.deepcopy(s)
            k.name = self.neu("subsysteme", name)
            k.elemente, k.beruehrung = self.els(s.elemente), self.els(s.beruehrung)
            k.knoten = self.kns(s.knoten)
            k.linien, k.staebe = self.neue("lines", s.linien), self.neue("members", s.staebe)
            k.flaechen, k.koerper = self.neue("flaechen", s.flaechen), self.neue("koerper", s.koerper)
            k.lager = [int(i) + n_s for i in s.lager]
            k.linienlager = [int(i) + n_ls for i in s.linienlager]
            k.flaechenlager = [int(i) + n_ss for i in s.flaechenlager]
            k.kontakte = self.neue("fugen", s.kontakte)
            z.subsysteme[k.name] = k
        for name, ly in q.layer.items():
            k = copy.deepcopy(ly)
            k.name = self.neu("layer", name)
            k.knoten, k.elemente = self.kns(ly.knoten), self.els(ly.elemente)
            k.staebe, k.linien = self.neue("members", ly.staebe), self.neue("lines", ly.linien)
            k.flaechen, k.koerper = self.neue("flaechen", ly.flaechen), self.neue("koerper", ly.koerper)
            z.layer[k.name] = k
        for name, u in q.unterlagen.items():
            k = copy.deepcopy(u)
            k.name = self.neu("unterlagen", name)
            z.unterlagen[k.name] = k
        for name, w in (q.wasserdruecke or {}).items():
            k = copy.deepcopy(w)
            k.name = self.neu("wasserdruecke", name)
            k.situation = self.neu("situationen", w.situation)
            k.flaechen, k.koerper = self.neue("flaechen", w.flaechen), self.neue("koerper", w.koerper)
            k.dichtung = self.neue("lines", w.dichtung)
            k.ow_flaeche = self.neu("flaechen", w.ow_flaeche)
            k.uw_flaeche = self.neu("flaechen", w.uw_flaeche)
            z.wasserdruecke[k.name] = k
        for name, w in (q.winde or {}).items():
            k = copy.deepcopy(w)
            k.name = self.neu("winde", name)
            k.situation = self.neu("situationen", w.situation)
            k.flaechen = self.neue("flaechen", w.flaechen)
            k.freie_waende = self.neue("flaechen", w.freie_waende)
            k.schilder = self.neue("flaechen", w.schilder)
            k.staebe = self.neue("members", w.staebe)
            z.winde[k.name] = k
        for name, s in (q.schwingungen or {}).items():
            k = copy.deepcopy(s)
            k.name = self.neu("schwingungen", name)
            k.wasserdruck = self.neu("wasserdruecke", s.wasserdruck)
            z.schwingungen[k.name] = k
        for name, n in (q.schweissnaehte or {}).items():
            k = copy.deepcopy(n)
            k.name = self.neu("schweissnaehte", name)
            k.staebe, k.linien = self.neue("members", n.staebe), self.neue("lines", n.linien)
            k.flaechen = self.neue("flaechen", n.flaechen)
            z.schweissnaehte[k.name] = k
        for name, b in (q.bemassungen or {}).items():
            k = copy.deepcopy(b)
            k.name = self.neu("bemassungen", name)
            z.bemassungen[k.name] = k

    def _netzeinstellungen(self) -> None:
        """Was in den Netzeinstellungen an Objekten haengt, geht mit; der Rest
        (Ziellaenge, Vernetzer, ...) ist Einstellung des Ziels."""
        zn, qn = self.z.netz, self.q.netz
        karte = {"flaeche": "flaechen", "linie": "lines", "koerper": "koerper"}
        for v in (qn.verfeinerungen or []):
            k = copy.deepcopy(v)
            if isinstance(k, dict) and k.get("art") in karte and k.get("name"):
                k["name"] = self.neu(karte[k["art"]], k["name"])
            zn.verfeinerungen.append(k)
        zn.feldpunkte.extend(copy.deepcopy(list(qn.feldpunkte or [])))
        for name, h in (qn.koerper_h or {}).items():
            zn.koerper_h.setdefault(self.neu("koerper", name), h)

    # -- Protokoll ----------------------------------------------------------
    def _melden(self) -> None:
        z, q, log = self.z, self.q, self.log
        teile = []
        for key, text in UEBERTRAGEN.items():
            n = q.nn if key == "nodes" else _anzahl(getattr(q, key, None))
            n -= len(self.gleich.get(key, []))
            if n:
                teile.append(f"{text} {n}")
                if key == "load_cases" and self.zusammengelegt:
                    teile[-1] += (f" (davon {len(self.zusammengelegt)} mit dem "
                                  "gleichnamigen des Ziels zusammengelegt)")
        if teile:
            C.say(log, "Aus der Quelle übertragen: " + ", ".join(teile))
        namen = {"materials": "Werkstoffe", "sections": "Querschnitte", "shells": "Dicken",
                 "federn": "Federn", "grenzschichten": "Grenzschichten", "lines": "Linien",
                 "flaechen": "Flächen", "koerper": "Volumenkörper", "members": "Stäbe",
                 "hinges": "Gelenke", "situationen": "Situationen", "fugen": "Fugen",
                 "combinations": "Kombinationen", "fatigue_loads": "Ermüdungslasten"}
        umb = []
        for art, karte in self.umbenannt.items():
            if karte:
                paare = [f"{a} → {b}" for a, b in karte.items()]
                umb.append(f"{namen.get(art, UEBERTRAGEN.get(art, art))}: "
                           + ", ".join(paare[:8]) + (f" … ({len(paare)})" if len(paare) > 8 else ""))
        if umb:
            C.say(log, "Umbenannt, weil der Name im Ziel schon vergeben ist (die Verweise "
                       "der Quelle folgen): " + "; ".join(umb))
        gl = [f"{namen.get(art, art)} {', '.join(n)}" for art, n in self.gleich.items() if n]
        if gl:
            C.say(log, "Gleichnamig und gleich im Ziel vorhanden, nicht doppelt angelegt: "
                       + "; ".join(gl))
        for key, (text, grund) in NICHT_UEBERTRAGEN.items():
            n = _anzahl(getattr(q, key, None))
            if n:
                C.warn(log, f"{text}: {n} der Quelle nicht übertragen - {grund}.")
        if self.stellungsverweis:
            je: dict[str, list] = {}
            for name, s in q.situationen.items():
                if s.stellung in self.stellungsverweis:
                    je.setdefault(s.stellung, []).append(self.neu("situationen", name))
            teile = [f"Situation{'en' if len(sits) > 1 else ''} "
                     f"{', '.join(repr(x) for x in sits)}: Stellung '{alt}' → "
                     f"'{self.stellungsverweis[alt]}'" for alt, sits in je.items()]
            C.warn(log, "Situationen der Quelle nennen eine Stellung, die es im Ziel unter "
                        "demselben Namen gibt. Stellungen werden nicht übertragen; damit diese "
                        "Situationen nicht still in der Stellung des Ziels rechnen, zeigen sie "
                        "auf einen neuen Namen: " + "; ".join(teile) + ". Die Modellprüfung "
                        "meldet sie, bis die Stellung unter diesem Namen im Ziel angelegt oder "
                        "die Situation auf eine Stellung des Ziels umgestellt ist."
                        + (_GRUNDSTELLUNG_HINWEIS if GRUNDSTELLUNG in self.stellungsverweis
                           else ""))
        abw = [ZIEL_BEHAELT[k].split(" (")[0] for k in ZIEL_BEHAELT
               if k not in _OHNE_VERGLEICH and _einstellung(z, k) != _einstellung(q, k)]
        if abw:
            C.warn(log, "Es gelten die Einstellungen des Ziels; in der Quelle abweichend: "
                        + ", ".join(abw) + " - bei Bedarf im Ziel anpassen.")
        # Ein Modellfeld, das hier (noch) niemand kennt, darf nicht still
        # wegfallen: es wird genannt. tests.test_importers haelt die Tabellen
        # vollstaendig; das hier greift, wenn jemand die Pruefung uebergeht.
        bekannt = set(UEBERTRAGEN) | set(ZIEL_BEHAELT) | set(NICHT_UEBERTRAGEN)
        for key, v in vars(q).items():
            if key.startswith("_") or key in bekannt or not _anzahl(v):
                continue
            C.warn(log, f"Modellfeld '{key}' der Quelle ({_anzahl(v)}) wird beim Anhängen "
                        "nicht übertragen - das Anhängen kennt es nicht. Bitte melden.")


def _g_text(g) -> str:
    g = [float(x) for x in g]
    if not any(g):
        return "keines"
    return "(" + ", ".join(f"{x:g}" for x in g) + ") m/s²"


def _wert(v) -> str:
    if v is None:
        return "Vorgabe"
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if v == "":
        return "leer"
    return str(v)


def modell_anhaengen(ziel: Model, quelle: Model, tol: float = C.DEFAULT_TOL,
                     log: list = None) -> Model:
    """``quelle`` an ``ziel`` anhaengen - vollstaendig oder mit Meldung.

    Die Quelle wird dabei nicht veraendert (alles wird kopiert). Rueckgabe
    ist ``ziel``."""
    _Anhang(ziel, quelle, log).ausfuehren(tol)
    return ziel


__all__ = ["modell_anhaengen", "UEBERTRAGEN", "ZIEL_BEHAELT", "NICHT_UEBERTRAGEN",
           "LASTLISTEN", "LASTFALL_EINGEORDNET"]
