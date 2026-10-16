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
    #: alte Verfahren es beruehrt haben kann - Rueckgabe ein Text, der sagt wo; ""
    #: heisst sicher nicht beruehrt (kein Status); None heisst nicht pruefbar (Status,
    #: lieber „möglicherweise betroffen“ als still gueltig). Ohne Funktion: jedes
    #: Ergebnis des Modells mit dem Merkmal.
    im_ergebnis: Optional[Callable[[Any], Optional[str]]] = field(default=None, repr=False)
    #: Marke einer Ergebnisdatei ohne Angabe „verfahren“, die sicher nach dem
    #: Wechsel gerechnet ist (etwa res.info["gleichgewicht_global"] ab 9a96ea6)
    marke: Optional[Callable[[dict], bool]] = field(default=None, repr=False)
    #: der heutige Wert, wenn er nicht einfach die Einstellung ist
    aktuell_fn: Optional[Callable[[Any], Any]] = field(default=None, repr=False)
    #: Korrektur am Import (16.10.2026): betroffen ist ein Modell, das vor dem Wechsel
    #: aus RFEM uebernommen und noch nicht nachgelesen ist (``betrifft``) - jedes
    #: Ergebnis dieses Modells, gleich wie alt; ``vorschlag`` nennt den Weg
    import_korrektur: bool = False
    vorschlag: str = ""

    def text(self, wert) -> str:
        return str(self.texte.get(wert, wert))

    def aktuell(self, model):
        """Der Wert, mit dem das Programm dieses Modell heute rechnet."""
        if self.aktuell_fn is not None:
            return self.aktuell_fn(model)
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


def _ergebnis_infos(an) -> list:
    try:
        infos = [(n, getattr(r, "info", None)) for n, r in an.all_results().items()]
        infos += [(n, getattr(r, "info", None)) for n, r in (getattr(an, "alternativen", None) or {}).items()]
    except Exception:                                   # noqa: BLE001
        return []
    return [(n, i) for n, i in infos if isinstance(i, dict)]


def _deckel_im_ergebnis(an) -> Optional[str]:
    infos = _ergebnis_infos(an)
    if not any(i.get("laeufe") for _n, i in infos):
        return None                     # ohne Laufbuch (vor dem 22.09.2026) nicht pruefbar
    lang = _lange_konvergierte(infos)
    if not lang:
        return ""
    namen = sorted({str(n) for n, _e in lang})
    return (f"{len(lang)} Kontaktl{'auf' if len(lang) == 1 else 'äufe'} mit mehr als {_deckel_grenze()} "
            f"Runden galt{'' if len(lang) == 1 else 'en'} als konvergiert (bis "
            f"{max(int(e.get('schritte', 0) or 0) for _n, e in lang)} Runden; "
            + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "") + ")")


def _staebe(model, typen=("truss", "seil")) -> list:
    return [i for i, e in enumerate(getattr(model, "elements", None) or []) if getattr(e, "typ", "") in typen]


def _hat_fachwerk_oder_seil(model) -> bool:
    """Fachwerkstab (auch Zug-/Druckstab, „trägt nur“) oder Seil."""
    return bool(_staebe(model))


def _hat_reibung_mu(model) -> bool:
    """Kontakt mit μ > 0 (Kontaktpaar, Kontaktlager, Kontaktelement) oder Lager mit
    Reibbeiwert - das Modellmerkmal der Reibungstangente."""
    return _hat_reibung(model)


def _reib_aktuell(model):
    """Das Reibverfahren heute: ohne Reibung im Modell „keine_reibung“ (16.10.2026),
    sonst die Einstellung (Vorgabe Tangente)."""
    if not _hat_reibung(model):
        return KEINE_REIBUNG
    return bool(_einstellung(model, "plastizitaet", "reibungstangente", vorgabe=True))


def _abgeschaltete_staebe(model) -> bool:
    """Ein Stab oder Element wirkt in einer Situation nicht (Member.aus, Situation.deaktiviert,
    Stellung mit abgeschalteten Staeben) - Merkmal fuer alpha_cr in Situationen."""
    try:
        namen = [""] + list(getattr(model, "situationen", None) or {})
        return any(not bool(model.aktive_elemente(n).all()) for n in namen)
    except Exception:                                   # noqa: BLE001
        return False


def _staebe_mit_last(model, typen) -> set:
    """Elemente der Typen ``typen`` mit einer Stablast (BeamLoad) in irgendeinem Lastfall."""
    st = set(_staebe(model, typen))
    out = set()
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for bl in getattr(lc, "beam_loads", None) or []:
            i = int(getattr(bl, "elem", -1))
            if i in st:
                out.add(i)
    return out


def _seil_mit_streckenlast(model) -> bool:
    return bool(_staebe_mit_last(model, ("seil",)))


def _fachwerk_mit_querlast(model) -> bool:
    """Fachwerkstab oder Seil mit Stablast - oder mit Eigengewicht, wenn er nicht
    senkrecht steht (Eigengewicht quer zur Achse): bis 4a6bba9 Ersatzlasten mit Momenten
    qL²/12, im Feld qL²/24 statt qL²/8."""
    if _staebe_mit_last(model, ("truss", "seil")):
        return True
    import numpy as np
    g = [np.asarray(getattr(lc, "gravity", None) or [0, 0, 0], float)
         for lc in (getattr(model, "load_cases", None) or {}).values()]
    g = [x for x in g if x.size == 3 and np.linalg.norm(x) > 0]
    if not g:
        return False
    X = np.asarray(getattr(model, "nodes", None), float).reshape(-1, 3)
    for i in _staebe(model):
        e = model.elements[i]
        d = X[int(e.nodes[1])] - X[int(e.nodes[0])]
        n = float(np.linalg.norm(d))
        if n <= 0:
            continue
        for gv in g:
            if np.linalg.norm(np.cross(d / n, gv / np.linalg.norm(gv))) > 1e-6:
                return True
    return False


def _alpha_cr_im_ergebnis(an) -> str:
    """alpha_cr, Theorie II. Ordnung oder Knicken im Ergebnis (geometrische Steifigkeit)."""
    th2 = getattr(an, "theorie2", None)
    komb = getattr(th2, "kombinationen", None) or {}
    namen = [str(n) for n, i in komb.items() if getattr(i, "alpha_cr", None) is not None]
    for n, r in (_ergebnis_paare(an)):
        if getattr(r, "kind", "") == "buckling" or str((getattr(r, "info", None) or {}).get("theorie", "")
                                                       ).startswith("II"):
            namen.append(str(n))
    namen = sorted(set(namen))
    return ("alpha_cr bzw. Theorie II. Ordnung: " + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "")
            if namen else "")


def _theorie3_im_ergebnis(an) -> str:
    th3 = getattr(an, "theorie3", None)
    namen = [str(n) for n in (getattr(th3, "kombinationen", None) or {})]
    for n, r in _ergebnis_paare(an):
        if str((getattr(r, "info", None) or {}).get("theorie", "")).startswith("III"):
            namen.append(str(n))
    namen = sorted(set(namen))
    return "Theorie III. Ordnung: " + ", ".join(namen[:6]) if namen else ""


def _ergebnis_paare(an) -> list:
    try:
        return list(an.all_results().items()) + list((getattr(an, "alternativen", None) or {}).items())
    except Exception:                                   # noqa: BLE001
        return []


def _marke_14_10(inhalt: dict) -> bool:
    """Eine Datei, sicher gerechnet nach den Korrekturen vom 14.10.2026 vormittags
    (5a5e8d0, fea5b8b, 878369b, 4a6bba9 - alle Vorfahren von 9a96ea6 und d1d8ebb): ein
    Ergebnis traegt die globale Gleichgewichtskontrolle (res.info["gleichgewicht_global"],
    seit 9a96ea6), oder ein Theorie-II-Eintrag kennt das Einzelknicken (Th2Info.alpha_cr_stab,
    seit d1d8ebb)."""
    if any("gleichgewicht_global" in i for i in _infos(inhalt)):
        return True
    th2 = inhalt.get("theorie2")
    for i in (getattr(th2, "kombinationen", None) or {}).values():
        if "alpha_cr_stab" in (getattr(i, "__dict__", None) or {}):
            return True
    return False


def _rfem(model) -> bool:
    meta = getattr(model, "meta", None) or {}
    return str(meta.get("quelle", "") or "").lower().endswith(".rf6")


def _importhinweis_offen(model, art: str) -> bool:
    return any(h.get("art") == art and not h.get("erledigt")
               for h in (getattr(model, "importhinweise", None) or []))


def _import_lagerreibung(model) -> bool:
    """Aus RFEM 6 vor edc00eb (15.10.2026) uebernommen (kein meta „rfem_lagerreibung“), ein
    Lager mit Reibbeiwert und der Hinweis „lagerreibung“ offen (model.lagerreibung_hinweis)."""
    meta = getattr(model, "meta", None) or {}
    if not _rfem(model) or meta.get("rfem_lagerreibung"):
        return False
    if any(h.get("art") == "lagerreibung" and h.get("erledigt") for h in (getattr(model, "importhinweise", None) or [])):
        return False
    from .model import NDOF
    for liste in ("supports", "line_supports", "surface_supports"):
        for s_ in getattr(model, liste, None) or []:
            if any(float(s_.dof_behaviour(d).mu or 0.0) > 0.0 for d in range(NDOF)):
                return True
    return False


def _import_stabtypen(model) -> bool:
    """Aus RFEM 6 vor a23f2c6/41ca33d (14.10.2026) uebernommen (meta „rfem_zugstaebe“ bzw.
    „rfem_seile“ fehlt), Fachwerkstaebe ohne „trägt nur“ und der Hinweis „zugstab“ nicht
    erledigt (model.zugstab_hinweis)."""
    meta = getattr(model, "meta", None) or {}
    if not _rfem(model) or (meta.get("rfem_zugstaebe") and meta.get("rfem_seile")):
        return False
    if any(h.get("art") == "zugstab" and h.get("erledigt") for h in (getattr(model, "importhinweise", None) or [])):
        return False
    for mem in (getattr(model, "members", None) or {}).values():
        els = [model.elements[int(i)] for i in mem.elements if 0 <= int(i) < len(model.elements)]
        if els and all(e.typ == "truss" and not getattr(e, "nur", "") for e in els):
            return True
    return False


def _import_vorspannung(model) -> bool:
    """Vorspannung aus RFEM als eingepraegte Dehnung (ΔT) mit offenem Hinweis - gespeichert
    (Import ab 13.10.2026) oder beim Oeffnen abgeleitet (Import davor; vorspannkraft)."""
    try:
        from .vorspannkraft import _rfem_hinweise, abgeleitete_hinweise
        if getattr(model, "_rfem_hinweise_abgeleitet", None) is None and _rfem(model):
            model._rfem_hinweise_abgeleitet = abgeleitete_hinweise(model)
        return any(not h.get("erledigt") for h in _rfem_hinweise(model))
    except Exception:                                   # noqa: BLE001
        return False


def _import_lastkategorien(model) -> bool:
    """Aus RFEM 6 vor 6706ef6 (13.10.2026) uebernommen - erkennbar nur daran, dass das
    Merkmal der Importe ab dem 14.10.2026 nicht „beim Import gesetzt“ ist (meta
    „rfem_zugstaebe“ fehlt oder ist „nachgelesen“; ein Merkmal des 13.10.2026 gibt es
    nicht: Importe zwischen 13.10. 23:09 und 14.10. 07:28 zaehlen mit) -, mit
    Kombinationen und mit Lastfaellen, die alle noch dieselbe Kategorie tragen (so
    legte der alte Import sie an; hat der Anwender sie geordnet, gilt es als erledigt)."""
    meta = getattr(model, "meta", None) or {}
    if not _rfem(model) or str(meta.get("rfem_zugstaebe", "") or "").startswith("beim Import"):
        return False
    if not (getattr(model, "combinations", None) or {}):
        return False
    kat = {str(getattr(lc, "category", "") or "") for lc in (getattr(model, "load_cases", None) or {}).values()}
    return len(kat) <= 1


def _kombinationen_im_ergebnis(an) -> str:
    """Die Kategorie wirkt nur ueber Teilsicherheits- und Kombinationsbeiwerte: betroffen
    sind gerechnete Kombinationen (und was aus ihnen folgt)."""
    namen = sorted(str(n) for n in (getattr(an, "combinations", None) or {}))
    return ("Kombinationen " + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "")) if namen else ""


#: Arten eines Wechsels (Wechsel.art)
VERBESSERUNG = "Verbesserung"
FEHLERKORREKTUR = "Fehlerkorrektur"
#: Status eines Ergebnisses, das mit einem Verfahren vor einer Fehlerkorrektur
#: gerechnet ist, und das Modell hat das betroffene Merkmal
BETROFFEN = "Ergebnis möglicherweise betroffen – neu rechnen"


#: „keine Reibung im Modell“ (16.10.2026): Wert des Reibverfahrens ohne Reibung
KEINE_REIBUNG = "keine_reibung"

#: Die Tabelle (Einstufung des Anwenders vom 16.10.2026). Stand 1: Abbruch der
#: Plastizitaet (a1194ef, 13.10.2026 19:32); Stand 1.5: die Korrekturen dazwischen
#: (13.10. 23:09 bis 15.10. 12:56) - eine Datei ohne Angabe erkennt sie nur an
#: Marken; Stand 2: Reibungstangente als Vorgabe und Deckel ueber alle Runden
#: (49cb8bb, 15.10.2026 19:49). Eine Datei mit der Angabe (Stand 2) und eine mit
#: „reibverfahren“ (ab a371cf2) sind nach allen gerechnet.
_KONTAKT = "Kontakt (Kontaktpaar, Kontaktlager, Lager mit Ausfall, Reibung oder Grenzkraft)"
MERKMALE: list = [
    Merkmal(
        name="reibverfahren", titel="Reibung",
        texte={True: "konsistente Reibungstangente",
               False: "bisheriges Reibverfahren ohne Reibungstangente",
               KEINE_REIBUNG: "keine Reibung im Modell"},
        einstellung=("plastizitaet", "reibungstangente"),
        # bis 4073439 gab es die Einstellung nicht (gerechnet wie False), von
        # 4073439 bis b24910b mit der Vorgabe False, seit 49cb8bb True. Fehlerkorrektur:
        # der alte Weg meldete falsche Konvergenz (Anwender 16.10.2026)
        wechsel=(Wechsel(stand=2, datum="15.10.2026", commit="49cb8bb", alt=False, neu=True,
                         vorher_einstellung=True, art=FEHLERKORREKTUR),),
        modellmerkmal="Kontakt mit μ > 0 (Kontaktpaar, Kontaktlager, Kontaktelement oder Lager mit Reibbeiwert)",
        betrifft=_hat_reibung_mu, aktuell_fn=_reib_aktuell),
    Merkmal(
        name="deckel", titel="Deckel des Kontaktlaufs",
        texte={"alle_runden": "Deckel über alle Runden des Kontaktlaufs (40)",
               "zustandswechsel": "Deckel nur über die Zustandswechsel der Reibung"},
        wechsel=(Wechsel(stand=2, datum="15.10.2026", commit="49cb8bb", alt="zustandswechsel",
                         neu="alle_runden", art=FEHLERKORREKTUR),),
        modellmerkmal=_KONTAKT, betrifft=_hat_kontakt,
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
        modellmerkmal="plastische Rechnung", betrifft=_fliessen),
    Merkmal(
        name="saitenform", titel="Geometrische Steifigkeit der Fachwerkstäbe",
        texte={"alt": "Balkenform 6/5 N/L auch für Fachwerkstab, Zug-/Druckstab und Seil",
               "neu": "Saitenform N/L für Fachwerkstab, Zug-/Druckstab und Seil"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="5a5e8d0", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Fachwerkstab, Zug-/Druckstab oder Seil, mit alpha_cr, Knicken oder Theorie II. Ordnung",
        betrifft=_hat_fachwerk_oder_seil, im_ergebnis=_alpha_cr_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="alpha_cr_aktiv", titel="alpha_cr mit abgeschalteten Stäben",
        texte={"alt": "abgeschaltete Stäbe in der geometrischen Steifigkeit von alpha_cr",
               "neu": "alpha_cr nur aus den wirksamen Elementen"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="878369b", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="abgeschaltete Stäbe oder Elemente (Stab aus, Situation, Stellung) mit alpha_cr "
                      "bzw. Theorie II. Ordnung",
        betrifft=_abgeschaltete_staebe, im_ergebnis=_alpha_cr_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="seil_theorie3", titel="Seil-Streckenlast nach Theorie III. Ordnung",
        texte={"alt": "Streckenlast auf dem Seil nach Theorie III. Ordnung nicht angesetzt",
               "neu": "Streckenlast auf dem Seil als Kettenlinienlast (sonst gesperrt)"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="fea5b8b", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Seil mit Streckenlast, Theorie III. Ordnung",
        betrifft=_seil_mit_streckenlast, im_ergebnis=_theorie3_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="fachwerk_querlast", titel="Fachwerkstab mit Querlast",
        texte={"alt": "Ersatzlasten mit Momenten qL²/12 (im Feld qL²/24, Lagermomente)",
               "neu": "Ersatzlasten als Kräfte, Stabmoment als Einfeldträger qL²/8"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="4a6bba9", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Fachwerkstab, Zug-/Druckstab oder Seil mit Stablast oder Eigengewicht quer zur Achse",
        betrifft=_fachwerk_mit_querlast, marke=_marke_14_10),
    # --- Korrekturen am Import: das Modell, nicht das Alter der Ergebnisdatei --------
    Merkmal(
        name="import_lagerreibung", titel="Lagerreibung aus RFEM",
        texte={"alt": "Reibbeiwert der RFEM-Lager auch ohne Reibungsart übernommen",
               "neu": "Reibbeiwert nur mit Reibungsart"},
        wechsel=(Wechsel(stand=1.5, datum="15.10.2026", commit="edc00eb", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="RFEM-Import ohne Merkmal rfem_lagerreibung, Lager mit Reibbeiwert",
        betrifft=_import_lagerreibung, import_korrektur=True,
        vorschlag="Datei › Austausch › „Aus RFEM nachlesen ▾“ › „Lager aus RFEM nachlesen…“"),
    Merkmal(
        name="import_stabtypen", titel="Stabtypen aus RFEM",
        texte={"alt": "RFEM-Zugstab und -Seil als Fachwerkstab mit Druck übernommen",
               "neu": "Zugstab trägt nur Zug, Seil als Seil"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="a23f2c6, 41ca33d", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="RFEM-Import ohne Merkmal rfem_zugstaebe/rfem_seile, Fachwerkstäbe ohne „trägt nur“",
        betrifft=_import_stabtypen, import_korrektur=True,
        vorschlag="Datei › Austausch › „Aus RFEM nachlesen ▾“ › „Stabtypen aus RFEM nachlesen…“"),
    Merkmal(
        name="import_vorspannung", titel="Vorspannung aus RFEM",
        texte={"alt": "Vorspannung als eingeprägte Dehnung (ΔT)",
               "neu": "Vorspannung als Kraft (Anfangs-/Endvorspannung)"},
        wechsel=(Wechsel(stand=1.5, datum="13.10.2026", commit="6706ef6", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="RFEM-Import mit Vorspannung als ΔT an Zug- oder Seilstäben, Hinweis offen",
        betrifft=_import_vorspannung, import_korrektur=True,
        vorschlag="Lasten › Vorspannung, Lastart umstellen"),
    Merkmal(
        name="import_lastkategorien", titel="Lastkategorien aus RFEM",
        texte={"alt": "jeder RFEM-Lastfall mit der Kennzahl 11 als Kategorie übernommen",
               "neu": "Kategorie aus der Einwirkung, sonst „nicht zugeordnet“"},
        wechsel=(Wechsel(stand=1.5, datum="13.10.2026", commit="6706ef6", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="RFEM-Import vor dem 14.10.2026 (rfem_zugstaebe fehlt oder „nachgelesen“), alle "
                      "Lastfälle in einer Kategorie, gerechnete Kombinationen",
        betrifft=_import_lastkategorien, import_korrektur=True, im_ergebnis=_kombinationen_im_ergebnis,
        vorschlag="die Kategorien der Lastfälle prüfen"),
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
    return {mk.name: _sicher(lambda: mk.aktuell(model)) for mk in MERKMALE if not mk.import_korrektur}


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
_REIBVERFAHREN_TEXT = {"konsistente Tangente": True, "bisheriges Verfahren": False,
                       "keine Reibung im Modell": KEINE_REIBUNG}


def _infos(inhalt: dict):
    for gruppe in ("cases", "combinations", "alternativen"):
        for d in (inhalt.get(gruppe) or {}).values():
            info = d.get("info") if isinstance(d, dict) else None
            if isinstance(info, dict):
                yield info


def _aus_datei(mk: Merkmal, inhalt: dict):
    """Was die Datei selbst sicher sagt (ohne die Angabe „verfahren“) - oder None."""
    if mk.marke is not None and _sicher(lambda: mk.marke(inhalt)):
        return mk.wechsel[-1].neu
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
        if mk.import_korrektur:
            continue
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
    """[(Merkmal, Wert der Datei, Wert heute, Wechsel)] fuer jedes Merkmal (ohne die
    Korrekturen am Import), das dieses Modell hat (``betrifft``) und mit dem die
    Datei anders gerechnet ist als heute; ``Wechsel`` ist der erste seither (seine
    ``art`` stuft ein). Ein unbekannter Wert (None) steht mit None darin."""
    aus = []
    for mk in MERKMALE:
        if mk.import_korrektur or not _sicher(lambda: mk.betrifft(model)):
            continue
        wert = (merkmale or {}).get(mk.name)
        jetzt = _sicher(lambda: mk.aktuell(model))
        if jetzt is None or wert == jetzt:
            continue
        w = next((w for w in mk.wechsel if w.alt == wert), mk.wechsel[-1])
        aus.append((mk, wert, jetzt, w))
    return aus


def _seit(mk, jetzt, w) -> str:
    return next((x.datum for x in reversed(mk.wechsel) if x.neu == jetzt), w.datum)


def bewerten(model, merkmale: dict, analyse=None) -> dict:
    """Hinweis (Verbesserungen), Status (Fehlerkorrekturen) und die Merkmale,
    deren Alter die Datei nicht sicher sagt und die darum als betroffen zaehlen
    (Grundsatz des Anwenders: lieber „möglicherweise betroffen“ als still gueltig).

    Rueckgabe {"hinweis": str, "betroffen": str, "unsicher": [Name], "teile": [...]}."""
    hinw, betr, unsicher = [], [], []
    for mk, wert, jetzt, w in aeltere(model, merkmale):
        if w.art != FEHLERKORREKTUR:
            if wert is not None:
                hinw.append(f"{mk.text(wert)} (aktuell: {mk.text(jetzt)}, seit {_seit(mk, jetzt, w)})")
            continue
        wo = None
        if mk.im_ergebnis is not None:
            wo = _sicher(lambda: mk.im_ergebnis(analyse)) if analyse is not None else None
            if wo == "":
                continue                # am Ergebnis sicher nicht beruehrt
        if wert is None:
            unsicher.append(mk.name)
            betr.append(f"{mk.titel}: Alter der Ergebnisdatei nicht sicher erkennbar, möglicherweise noch "
                        f"gerechnet mit „{mk.text(w.alt)}“" + (f" ({wo})" if wo else "")
                        + f", seit {_seit(mk, jetzt, w)} korrigiert: „{mk.text(jetzt)}“")
        else:
            betr.append(f"{mk.titel}: gerechnet mit „{mk.text(wert)}“" + (f" ({wo})" if wo else "")
                        + f", seit {_seit(mk, jetzt, w)} korrigiert: „{mk.text(jetzt)}“")
    for mk in MERKMALE:
        if mk.import_korrektur and _sicher(lambda: mk.betrifft(model)):
            wo = _sicher(lambda: mk.im_ergebnis(analyse)) if (mk.im_ergebnis is not None and analyse is not None)                 else None
            if wo == "":
                continue
            w = mk.wechsel[-1]
            betr.append(f"{mk.titel}: Modell vor dem {w.datum} aus RFEM übernommen ({mk.text('alt')}"
                        + (f"; {wo}" if wo else "") + f") – {mk.vorschlag}, danach neu rechnen")
    return {"hinweis": ("gerechnet mit älterem Rechenverfahren: " + "; ".join(hinw)
                        + " – die Ergebnisse gelten, eine neue Rechnung liefert sie nach dem aktuellen Verfahren")
            if hinw else "",
            "betroffen": BETROFFEN + ": " + "; ".join(betr) if betr else "",
            "unsicher": unsicher}


def hinweis(model, merkmale: dict) -> str:
    """Der Hinweis zu Ergebnissen eines aelteren Verfahrens, soweit die Wechsel
    seither Verbesserungen sind - oder ""."""
    return bewerten(model, merkmale)["hinweis"]


def betroffen(model, merkmale: dict, analyse=None) -> str:
    """Der Status „Ergebnis möglicherweise betroffen – neu rechnen: …“ - oder ""."""
    return bewerten(model, merkmale, analyse)["betroffen"]
