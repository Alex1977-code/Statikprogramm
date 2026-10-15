"""Verfahrensmerkmale der Rechnung und ihre Wechsel (16.10.2026).

Der Anwender (15.10.2026): „Bitte künftig zwei Fälle trennen. ‚Modell geändert‘
→ Ergebnisse ungültig. ‚Mit älterem Rechenverfahren gerechnet‘ (z. B. ohne
Reibungstangente oder mit altem Abbruchkriterium) → Ergebnisse gültig, mit
Hinweis.“

* **Modell** ist alles, was in der Modelldatei steht: Geometrie, Netz,
  Werkstoffe, Querschnitte, Lager, Lasten, Kontakte und jede Einstellung, die
  der Anwender gesetzt hat. Die Kennung der Ergebnisdatei
  (ergebnisse.rechenkennung) haelt es fest; eine Aenderung dort - auch eine,
  die der Anwender nach der Rechnung an einer Einstellung vornimmt, die
  zugleich ein Verfahrensmerkmal ist - macht die Ergebnisse ungueltig.
* **Rechenverfahren** ist, was das Programm mit demselben Modell tut. Es
  aendert sich, wenn eine Programmvorgabe wechselt (die Modelldatei traegt
  eine Einstellung mit ihrer Vorgabe nicht, model.NEUE_FELDER - nach dem
  Wechsel rechnet dieselbe Datei anders) oder wenn sich das Programm selbst
  aendert (Deckel des Kontaktlaufs). Ergebnisse eines aelteren Verfahrens
  bleiben gueltig; beim Oeffnen nennen Statuszeile und Protokoll das
  Verfahren und dass eine neue Rechnung aktuelle Ergebnisse liefert.

Diese Tabelle ist die einzige Stelle fuer einen Wechsel: wer eine Vorgabe
aendert (oder das Programm so, dass dasselbe Modell anders rechnet), traegt
hier einen :class:`Wechsel` mit dem naechsten Stand ein und zaehlt
:data:`VERFAHRENSSTAND` hoch. Daraus folgen model.FRUEHERE_VORGABEN (die
Kennung erkennt einen Wert, der damals ausdruecklich in der Datei stand und
heute Vorgabe ist), die Angabe in der Ergebnisdatei („verfahren“: Stand und
Merkmale) und der Hinweis beim Oeffnen.

Was eine Ergebnisdatei ohne die Angabe (vor dem 16.10.2026) sicher erkennen
laesst, steht je Merkmal (:func:`_aus_datei`); was sich nicht sicher erkennen
laesst, bleibt offen (None) und wird nicht genannt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Wechsel:
    """Ein Wechsel des Verfahrens: ab ``stand`` (Programmstand ``commit``,
    ``datum``) rechnet das Programm ``neu`` statt ``alt``.

    ``vorher_einstellung``: die Einstellung gab es schon vor dem Wechsel, mit
    der Vorgabe ``alt`` (reibungstangente: 4073439 bis b24910b mit False). Ein
    damals ausdruecklich gesetzter Wert, der heute die Vorgabe ist, stand dann
    in der Kennung der Ergebnisdatei und fehlt heute dort - die Kennung wird
    darum auch mit diesem Wert ausdruecklich gebildet (ergebnisse._pruefen).

    ``art`` (Anwender, 16.10.2026): „Verbesserung“ - das alte Verfahren war
    richtig, das neue ist besser oder schneller: Ergebnis gueltig, mit Hinweis;
    „Fehlerkorrektur“ - das alte Verfahren konnte falsch rechnen: Status
    „Ergebnis möglicherweise betroffen – neu rechnen“ (:data:`BETROFFEN`) in
    Kopfzeile, Statuszeile, Protokoll und Bericht, die Ergebnisse bleiben
    sichtbar."""
    stand: int
    datum: str
    commit: str
    alt: Any
    neu: Any
    vorher_einstellung: bool = False
    art: str = "Verbesserung"


@dataclass
class Merkmal:
    """Ein Merkmal des Rechenverfahrens.

    ``einstellung`` (Schluessel der Modelldatei, Feld): das Merkmal ist eine
    Einstellung am Modell; ihr Wert ist das Verfahren. Ohne sie ist es ein
    Verhalten des Programms (Deckel). ``texte``: Wert -> Text fuer den
    Hinweis. ``modellmerkmal``: das Merkmal des Modells, bei dem das Verfahren
    eine Rolle spielt (Reibkontakt, Kontakt, plastische Rechnung), und
    ``betrifft`` die Pruefung, ob das Modell es hat - ohne es kein Hinweis und
    kein Status."""
    name: str
    titel: str
    texte: dict
    wechsel: tuple
    einstellung: Optional[tuple] = None
    modellmerkmal: str = ""
    betrifft: Callable[[Any], bool] = field(default=lambda model: True, repr=False)
    #: nur bei einer Fehlerkorrektur: die Pruefung am Ergebnis (Analyse), ob das
    #: alte Verfahren es beruehrt haben kann - Rueckgabe ein Text, der sagt wo, oder
    #: "" (dann kein Status). None: jedes Ergebnis des Modells mit dem Merkmal.
    im_ergebnis: Optional[Callable[[Any], str]] = field(default=None, repr=False)

    def text(self, wert) -> str:
        return str(self.texte.get(wert, wert))

    def aktuell(self, model):
        """Der Wert, mit dem das Programm dieses Modell heute rechnet."""
        if self.einstellung is None:
            return self.wechsel[-1].neu
        return _einstellung(model, *self.einstellung, vorgabe=self.wechsel[-1].neu)


def _einstellung(model, schluessel: str, feld_: str, vorgabe=None):
    obj = getattr(model, schluessel, None)
    if isinstance(obj, dict):
        return obj.get(feld_, vorgabe)
    return getattr(obj, feld_, vorgabe)


def _hat_reibung(model) -> bool:
    from .ergebnisse import modell_hat_reibung
    return modell_hat_reibung(model)


def _hat_kontakt(model) -> bool:
    try:
        hc = model.has_contact                          # Eigenschaft am Modell
        return bool(hc() if callable(hc) else hc)
    except Exception:                                   # noqa: BLE001 - Stuempfe
        return False


def _fliessen(model) -> bool:
    return bool(getattr(getattr(model, "plastizitaet", None), "an", False))


def _laeufe(infos):
    """(Ergebnisname, Eintrag) aller Kontaktlaeufe im Laufbuch (res.info["laeufe"],
    seit dem 22.09.2026)."""
    for name, info in infos:
        for e in (info.get("laeufe") or []) if isinstance(info, dict) else []:
            if isinstance(e, dict):
                yield name, e


def _deckel_grenze() -> int:
    try:
        from .contact import MAX_CYCLES
        return int(MAX_CYCLES)
    except Exception:                                   # noqa: BLE001
        return 40


def _lange_konvergierte(infos) -> list:
    """Kontaktlaeufe, die mit mehr Runden als der Deckel (40) als konvergiert
    galten - das konnte nur der alte Deckel (nur Zustandswechsel der Reibung):
    seit 49cb8bb endet ein solcher Lauf am Deckel und ist vorlaeufig. Genau 40
    Runden sind auch heute moeglich (konvergiert in der letzten erlaubten)."""
    grenze = _deckel_grenze()
    return [(n, e) for n, e in _laeufe(infos)
            if bool(e.get("konvergiert")) and not e.get("abgekuerzt")
            and int(e.get("schritte", 0) or 0) > grenze]


def _deckel_im_ergebnis(an) -> str:
    try:
        infos = [(n, getattr(r, "info", None)) for n, r in an.all_results().items()]
        infos += [(n, getattr(r, "info", None)) for n, r in (getattr(an, "alternativen", None) or {}).items()]
    except Exception:                                   # noqa: BLE001
        return ""
    lang = _lange_konvergierte(infos)
    if not lang:
        return ""
    namen = sorted({str(n) for n, _e in lang})
    return (f"{len(lang)} Kontaktl{'auf' if len(lang) == 1 else 'äufe'} mit mehr als {_deckel_grenze()} "
            f"Runden galt{'' if len(lang) == 1 else 'en'} als konvergiert (bis "
            f"{max(int(e.get('schritte', 0) or 0) for _n, e in lang)} Runden; "
            + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "") + ")")


#: Arten eines Wechsels (Wechsel.art)
VERBESSERUNG = "Verbesserung"
FEHLERKORREKTUR = "Fehlerkorrektur"
#: Status eines Ergebnisses, das mit einem Verfahren vor einer Fehlerkorrektur
#: gerechnet ist, und das Modell hat das betroffene Merkmal
BETROFFEN = "Ergebnis möglicherweise betroffen – neu rechnen"


#: Die Tabelle. Stand 1: Abbruch der Plastizitaet (13.10.2026); Stand 2:
#: Reibungstangente als Vorgabe und Deckel ueber alle Runden (15.10.2026, beide
#: im selben Commit 49cb8bb). Einstufung (16.10.2026, zur Bestaetigung durch den
#: Anwender): Reibungstangente Verbesserung (Vorgabe des Anwenders), Deckel
#: Fehlerkorrektur (vorher konnte ein Lauf ohne Begrenzung als konvergiert
#: gelten), Abbruch Verbesserung (streng ist weiter waehlbar und richtig).
#: Nicht hier: Korrekturen am Import (Lagerreibung, Zugstaebe, Vorspannung aus
#: ΔT) - sie aendern die Modelldaten, nicht das Rechnen; ein so eingelesenes
#: Modell rechnet heute wie damals, der Ladehinweis nennt den Weg zur Korrektur,
#: und die Korrektur selbst ist eine Modellaenderung (Ergebnis ungueltig).
MERKMALE: list = [
    Merkmal(
        name="reibverfahren", titel="Reibung",
        texte={True: "konsistente Reibungstangente",
               False: "bisheriges Reibverfahren ohne Reibungstangente"},
        einstellung=("plastizitaet", "reibungstangente"),
        # bis 4073439 gab es die Einstellung nicht (gerechnet wie False), von
        # 4073439 bis b24910b mit der Vorgabe False, seit 49cb8bb True
        wechsel=(Wechsel(stand=2, datum="15.10.2026", commit="49cb8bb", alt=False, neu=True,
                         vorher_einstellung=True, art=VERBESSERUNG),),
        modellmerkmal="Reibkontakt (Kontakt mit μ > 0 oder Lager mit Reibbeiwert)",
        betrifft=_hat_reibung),
    Merkmal(
        name="deckel", titel="Deckel des Kontaktlaufs",
        texte={"alle_runden": "Deckel über alle Runden des Kontaktlaufs",
               "zustandswechsel": "Deckel nur über die Zustandswechsel der Reibung"},
        wechsel=(Wechsel(stand=2, datum="15.10.2026", commit="49cb8bb", alt="zustandswechsel",
                         neu="alle_runden", art=FEHLERKORREKTUR),),
        modellmerkmal="Kontakt (Kontaktpaar, Kontaktlager, Lager mit Ausfall, Reibung oder Grenzkraft)",
        betrifft=_hat_kontakt,
        # betroffen ist nur ein Lauf, der mehr als 40 Runden brauchte und trotzdem als
        # konvergiert galt (Laufbuch, Runden je Lauf seit dem 22.09.2026)
        im_ergebnis=_deckel_im_ergebnis),
    Merkmal(
        name="abbruch", titel="Abbruch der Plastizität",
        texte={"ingenieurmaessig": "ingenieurmäßiger Abbruch ohne netzabhängige Spitzen",
               "streng": "strenger Abbruch über das ganze Modell"},
        einstellung=("plastizitaet", "abbruch"),
        # vor a1194ef gab es die Einstellung nicht: gerechnet wurde streng
        wechsel=(Wechsel(stand=1, datum="13.10.2026", commit="a1194ef", alt="streng",
                         neu="ingenieurmaessig", art=VERBESSERUNG),),
        modellmerkmal="plastische Rechnung",
        betrifft=_fliessen),
]

#: Verfahrensstand dieses Programms: der hoechste Stand der Tabelle
VERFAHRENSSTAND = 2


def merkmal(name: str) -> Optional[Merkmal]:
    return next((mk for mk in MERKMALE if mk.name == name), None)


def fruehere_vorgaben() -> dict:
    """{Schluessel: {Feld: fruehere Vorgabe}} der Einstellungen, deren Vorgabe
    gewechselt hat, solange es sie schon gab (model.FRUEHERE_VORGABEN)."""
    aus: dict = {}
    for mk in MERKMALE:
        if mk.einstellung is None:
            continue
        for w in mk.wechsel:
            if w.vorher_einstellung:
                aus.setdefault(mk.einstellung[0], {})[mk.einstellung[1]] = w.alt
    return aus


def ausdruecklich_moeglich(stand_bis: Optional[int] = None) -> list:
    """Die Einstellungen (Schluessel, Feld, Stand des Wechsels), deren heutige
    Vorgabe eine Ergebnisdatei vom Stand ``stand_bis`` (None: unbekannt)
    ausdruecklich in ihrer Kennung tragen kann."""
    aus = []
    for mk in MERKMALE:
        if mk.einstellung is None:
            continue
        for w in mk.wechsel:
            if w.vorher_einstellung and (stand_bis is None or stand_bis < w.stand):
                aus.append((mk.einstellung[0], mk.einstellung[1], w.stand))
    return aus


def aktuelle_merkmale(model) -> dict:
    """{Name: Wert} - so rechnet das Programm dieses Modell heute."""
    return {mk.name: _sicher(lambda: mk.aktuell(model)) for mk in MERKMALE}


def angabe(model, merkmale: Optional[dict] = None) -> dict:
    """Die Angabe der Ergebnisdatei: Stand dieses Programms und die Merkmale,
    mit denen gerechnet wurde (ohne ``merkmale``: die heutigen; None je
    Merkmal heisst „nicht bekannt“)."""
    return {"stand": VERFAHRENSSTAND, "merkmale": dict(aktuelle_merkmale(model) if merkmale is None
                                                    else merkmale)}


def _sicher(f):
    try:
        return f()
    except Exception:                                   # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Erkennen in einer Ergebnisdatei
# ---------------------------------------------------------------------------

#: Text des Reibverfahrens in Dateien vom 15.10.2026 (a371cf2 bis b63e669)
_REIBVERFAHREN_TEXT = {"konsistente Tangente": True, "bisheriges Verfahren": False}


def _infos(inhalt: dict):
    for gruppe in ("cases", "combinations", "alternativen"):
        for d in (inhalt.get(gruppe) or {}).values():
            info = d.get("info") if isinstance(d, dict) else None
            if isinstance(info, dict):
                yield info


def _aus_datei(mk: Merkmal, inhalt: dict):
    """Was die Datei selbst sicher sagt (ohne die Angabe „verfahren“) - oder None."""
    if mk.name == "reibverfahren":
        return _REIBVERFAHREN_TEXT.get(inhalt.get("reibverfahren"))
    if mk.name == "deckel":
        if "reibverfahren" in inhalt:          # geschrieben ab a371cf2, also nach 49cb8bb
            return "alle_runden"
        if _lange_konvergierte(("", i) for i in _infos(inhalt)):
            return "zustandswechsel"           # mehr als 40 Runden konvergiert: nur der alte Deckel
        for info in _infos(inhalt):
            for z in info.get("contact_log") or []:
                z = str(z)
                if "Zustandswechseln abgebrochen" in z:
                    return "zustandswechsel"
                if "Runden abgebrochen" in z and "Nachpr" in z:
                    return "alle_runden"
        return None
    if mk.name == "abbruch":
        # res.info["plastizitaet"]["spitzen"]["abbruch"] (ab a1194ef, nur mit Stellen
        # „Kraft ohne Fläche“) - ohne den Eintrag nicht sicher erkennbar
        for info in _infos(inhalt):
            spz = (info.get("plastizitaet") or {}).get("spitzen") if isinstance(info.get("plastizitaet"), dict) \
                else None
            if isinstance(spz, dict) and spz.get("abbruch") in mk.texte:
                return spz["abbruch"]
        return None
    return None


def _ohne_angabe(mk: Merkmal, inhalt: dict):
    """Fallback fuer eine Datei ohne jede Angabe, wenn sonst nichts spricht."""
    if mk.name == "reibverfahren" and "reibverfahren" not in inhalt:
        # vor dem 15.10.2026 abends geschrieben: bisheriges Verfahren (a371cf2; die
        # Dateien von 49cb8bb bis a371cf2 - eineinhalb Stunden am 15.10.2026 auf dem
        # Zweig - rechneten schon mit der Tangente und sind hier nicht unterscheidbar)
        return False
    return None


def merkmale_der_datei(inhalt: dict, model, ausdruecklich=()) -> dict:
    """{Name: Wert oder None} - womit die Ergebnisse der Datei gerechnet sind.

    ``ausdruecklich``: die Einstellungen (Schluessel, Feld, Stand), die die
    Kennung nur mit ihrem heutigen Vorgabewert ausdruecklich traf
    (ergebnisse._pruefen): die Datei ist dann sicher vor diesem Stand
    geschrieben und mit diesem Wert gerechnet."""
    angabe_ = inhalt.get("verfahren") if isinstance(inhalt.get("verfahren"), dict) else None
    werte = dict((angabe_ or {}).get("merkmale") or {})
    stand = (angabe_ or {}).get("stand")
    stand = stand if isinstance(stand, int) else None
    # Grenzen des Stands, mit dem die Datei geschrieben ist
    unten = stand if stand is not None else (2 if "reibverfahren" in inhalt else 0)
    oben = stand if stand is not None else min([s for _s, _f, s in ausdruecklich] or [10 ** 9]) - 1
    gesetzt = {(s, f) for s, f, _st in ausdruecklich}
    aus = {}
    for mk in MERKMALE:
        if mk.name in werte:
            aus[mk.name] = werte[mk.name]
            continue
        wert = _aus_datei(mk, inhalt) if angabe_ is None else None
        if wert is None:
            erster, letzter = mk.wechsel[0], mk.wechsel[-1]
            jetzt = _sicher(lambda: mk.aktuell(model))
            if mk.einstellung is not None and tuple(mk.einstellung) in gesetzt:
                wert = jetzt                       # damals ausdruecklich gesetzt
            elif unten >= letzter.stand:
                wert = jetzt if mk.einstellung is not None else letzter.neu
            elif oben < erster.stand:
                # vor dem ersten Wechsel: eine Einstellung mit heutiger Vorgabe
                # fehlte in der Datei und rechnete mit der damaligen
                if mk.einstellung is None or jetzt == letzter.neu:
                    wert = erster.alt
                else:
                    wert = jetzt
            elif angabe_ is None:
                wert = _ohne_angabe(mk, inhalt)
        aus[mk.name] = wert
    return aus


def aeltere(model, merkmale: dict) -> list:
    """[(Merkmal, Wert der Datei, Wert heute, Wechsel)] fuer jedes Merkmal, das
    dieses Modell hat (``betrifft``) und mit dem die Datei anders gerechnet ist
    als heute; ``Wechsel`` ist der erste seither (seine ``art`` stuft ein). Ein
    unbekannter Wert (None) zaehlt nicht."""
    aus = []
    for mk in MERKMALE:
        wert = (merkmale or {}).get(mk.name)
        if wert is None or not _sicher(lambda: mk.betrifft(model)):
            continue
        jetzt = _sicher(lambda: mk.aktuell(model))
        if jetzt is None or wert == jetzt:
            continue
        w = next((w for w in mk.wechsel if w.alt == wert), mk.wechsel[-1])
        aus.append((mk, wert, jetzt, w))
    return aus


def _teil(mk, wert, jetzt, w) -> str:
    seit = next((x.datum for x in reversed(mk.wechsel) if x.neu == jetzt), w.datum)
    return f"{mk.text(wert)} (aktuell: {mk.text(jetzt)}, seit {seit})"


def hinweis(model, merkmale: dict) -> str:
    """Der Hinweis zu Ergebnissen eines aelteren Verfahrens, soweit die Wechsel
    seither Verbesserungen sind - oder ""."""
    alt = [x for x in aeltere(model, merkmale) if x[3].art != FEHLERKORREKTUR]
    if not alt:
        return ""
    return ("gerechnet mit älterem Rechenverfahren: " + "; ".join(_teil(*x) for x in alt)
            + " – die Ergebnisse gelten, eine neue Rechnung liefert sie nach dem aktuellen Verfahren")


def betroffen(model, merkmale: dict, analyse=None) -> str:
    """Der Status zu Ergebnissen, die vor einer Fehlerkorrektur gerechnet sind,
    deren Merkmal das Modell hat und - mit ``im_ergebnis`` - die das alte
    Verfahren beruehrt haben kann: „Ergebnis möglicherweise betroffen – neu
    rechnen: …“ - oder ""."""
    teile = []
    for mk, wert, jetzt, w in aeltere(model, merkmale):
        if w.art != FEHLERKORREKTUR:
            continue
        wo = ""
        if mk.im_ergebnis is not None:
            wo = _sicher(lambda: mk.im_ergebnis(analyse)) if analyse is not None else ""
            if not wo:
                continue
        seit = next((x.datum for x in reversed(mk.wechsel) if x.neu == jetzt), w.datum)
        teile.append(f"gerechnet mit {mk.text(wert)}" + (f" ({wo})" if wo else "")
                     + f", seit {seit} korrigiert: {mk.text(jetzt)}")
    return BETROFFEN + ": " + "; ".join(teile) if teile else ""
