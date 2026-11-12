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
    im_ergebnis: Optional[Callable[[Any, Any], Optional[str]]] = field(default=None, repr=False)
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
    #: Korrektur, die erst mit neu erzeugten Kombinationen wirkt (11.11.2026, Befunde 41,
    #: 42, 44 der Pruefagenten): die alten Faktoren stehen im Modell, ein Neurechnen
    #: aendert nichts. Die Pruefung am Modell gibt den Text des Status zurueck (wo, und
    #: was zu tun ist) oder "" - der Status gilt dann unabhaengig vom Alter der
    #: Ergebnisdatei, auch fuer eine neue Rechnung, bis die Kombinationen neu erzeugt sind
    im_modell: Optional[Callable[[Any], str]] = field(default=None, repr=False)
    #: bei einer solchen Korrektur am Modell, die nicht vom Import kommt (Windlasten eines
    #: aelteren Programmstands, 11.11.2026): warum das Modell betroffen ist; leer heisst
    #: „Modell vor dem <Datum> aus RFEM übernommen“
    modellgrund: str = ""

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


def _kontakt_mit_spannschritt(model) -> bool:
    """Kontakt und eine Vorspannung, die einen Spannschritt rechnet (Kraeftepaar,
    Summe der aeusseren Kraefte null) - nur dort wirkt der Gleichgewichtsbezug (PR #39)."""
    if not _hat_kontakt(model):
        return False
    for lc in (getattr(model, "load_cases", None) or {}).values():
        if getattr(lc, "vorspannzustand", None) or getattr(lc, "vorspannungen", None):
            return True
    return False


def _haltekraefte_im_ergebnis(model, an) -> Optional[str]:
    """Freie Bewegungen, die die Rechnung damals fand (Results.singular): nur dort hielt
    die Pivot-Regularisierung Freiheitsgrade numerisch. Ohne das Feld nicht pruefbar."""
    try:
        paare = list(an.all_results().items()) + list((getattr(an, "alternativen", None) or {}).items())
    except Exception:                                   # noqa: BLE001
        return None
    namen = []
    for n, r in paare:
        s = getattr(r, "singular", None)
        if s is None:
            return None
        if s:
            namen.append(str(n))
    if not namen:
        return ""
    return "freie Bewegungen numerisch gehalten in " + ", ".join(namen[:5]) + (" …" if len(namen) > 5 else "")


def _fuge_mit_kontaktpaar(model) -> bool:
    """Ein Kontaktpaar aus einer Kontaktbedingung (fugen._fuge_ueber_kontaktpaar):
    ungleiche Netze an einer Fuge. Passende Netze werden zu Spaltelementen."""
    kbs = getattr(model, "kontaktbedingungen", None) or {}
    return any(str(cp.name) in kbs for cp in (getattr(model, "contact_pairs", None) or []))


def _projiziert_auf_schale(model) -> bool:
    """Eine Flaechenlast „auf die Projektion“ an einer Schale (Flaeche mit Dicke
    oder Schalenelementen) - nur dort wirkte sie bis zum 08.11.2026 nicht."""
    flaechen = getattr(model, "flaechen", None) or {}
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for gl in getattr(lc, "geometrielasten", None) or []:
            if not getattr(gl, "projiziert", False) or getattr(gl, "art", "flaeche") != "flaeche":
                continue
            f = flaechen.get(str(gl.ziel))
            if f is not None and (getattr(f, "dicke", "") or getattr(f, "elemente", None)):
                return True
    return False


def _wind_auf_flaechen(model) -> bool:
    """Eine Windlast des Generators auf Gebaeudeflaechen (Schale oder
    Volumenrand), die mit einem aelteren Programmstand erzeugt ist - sie wirkt
    an Schalen gegen den Wind, an Volumen und shell8 mit falschen Rollen
    (Befunde A1, A2 der Pruefagenten), bis der Anwender sie neu erzeugt.
    Seit dem 11.11.2026 am Modell, nicht am Alter der Ergebnisdatei: die
    gespeicherte Last rechnete nach dem Oeffnen weiter verkehrt, und ein
    Neurechnen loeschte den Status (Befund 40)."""
    from .wind import alte_windlasten
    return bool(alte_windlasten(model))


def _alte_windlasten_im_ergebnis(model, _analyse) -> str:
    from .wind import alte_windlasten_text
    return alte_windlasten_text(model)


def _projiziert_negativ_an_volumen(model) -> bool:
    """Eine Flaechenlast „auf die Projektion“ mit p < 0 an einem Koerper oder einer
    Koerperrandflaeche - dort traf sie bis zum 09.11.2026 die abgewandte Seite
    (Befund A3 der Pruefagenten). Schalen sind nicht betroffen."""
    flaechen = getattr(model, "flaechen", None) or {}
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for gl in getattr(lc, "geometrielasten", None) or []:
            if not getattr(gl, "projiziert", False) or float(getattr(gl, "p", 0.0) or 0.0) >= 0.0:
                continue
            if getattr(gl, "art", "flaeche") != "flaeche":
                return True
            f = flaechen.get(str(gl.ziel))
            if f is not None and not (getattr(f, "dicke", "") or getattr(f, "elemente", None)):
                return True
    return False


def _temperaturunterschied_schale(model) -> bool:
    """Ein Temperaturunterschied dT_z (oben − unten) auf einer Schale - als Last
    auf eine Flaeche mit Dicke oder als Elementlast auf ein Schalenelement. Bis
    zum 09.11.2026 still verworfen (Befund A4 der Pruefagenten)."""
    from . import elemente as _EL
    flaechen = getattr(model, "flaechen", None) or {}
    elemente = getattr(model, "elements", None) or []
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for gl in getattr(lc, "geometrielasten", None) or []:
            if getattr(gl, "lastart", "") != "temperatur" or not float(getattr(gl, "dT_z", 0.0) or 0.0):
                continue
            f = flaechen.get(str(gl.ziel)) if getattr(gl, "art", "flaeche") == "flaeche" else None
            if f is not None and (getattr(f, "dicke", "") or getattr(f, "elemente", None)):
                return True
        for tl in getattr(lc, "temp_loads", None) or []:
            if (float(getattr(tl, "dT_z", 0.0) or 0.0) and 0 <= int(tl.elem) < len(elemente)
                    and elemente[int(tl.elem)].typ in _EL.SCHALEN_TYPEN):
                return True
    return False


def _kombination_610b(model) -> bool:
    """Eine Kombination nach Regel 6.10b - dort traf ξ bis zum 09.11.2026 auch
    die Vorspannung und das günstige G (Befund A6 der Pruefagenten)."""
    for c in (getattr(model, "combinations", None) or {}).values():
        if "6.10b" in str(getattr(c, "description", "") or ""):
            return True
    return False


def _xi_alte_faktoren(model) -> list:
    """Die Kombinationen des Generators nach Regel 6.10b (Beschreibung „auto: 6.10b…“),
    deren gespeicherte Faktoren noch der Regel vor dem 09.11.2026 folgen (Befund 41):
    eine Vorspannung oder Setzung - in einer Kombination „G günstig“ jede staendige
    Last - steht nicht mit ihrem γ ohne ξ darin. Erkannt an den Faktoren selbst, nicht
    am Alter der Datei: erst neu erzeugte Kombinationen tragen die richtigen."""
    from .combinations import _gamma
    ds = getattr(model, "design", None)
    faelle = getattr(model, "load_cases", None) or {}
    namen = []
    for name, c in (getattr(model, "combinations", None) or {}).items():
        desc = str(getattr(c, "description", "") or "")
        if not desc.startswith("auto") or "6.10b" not in desc:
            continue
        guenstig = "G guenstig" in desc or "G günstig" in desc
        for k, f in (getattr(c, "factors", None) or {}).items():
            lc = faelle.get(k)
            if lc is None or getattr(lc, "faktorisiert", False) or not lc.is_permanent:
                continue
            if not (guenstig or lc.category in ("P", "SET")):
                continue
            soll = _gamma(lc, ds, guenstig)
            if abs(float(f) - soll) > 1e-6 * max(1.0, abs(soll)):
                namen.append(str(name))
                break
    return namen


def _kurz(namen, n: int = 6) -> str:
    return ", ".join(namen[:n]) + (" …" if len(namen) > n else "")


def _xi_im_modell(model) -> str:
    from .combinations import gehoert_dem_generator
    namen = _xi_alte_faktoren(model)
    if not namen:
        return ""
    kombis = getattr(model, "combinations", None) or {}
    hand = [n for n in namen if not gehoert_dem_generator(kombis[n])]
    return (f"die Kombinationen {_kurz(namen)} tragen noch die Faktoren von vor dem 09.11.2026 "
            "(ξ auch auf P bzw. das günstige G) – Lasten › „EN 1990…“: die Kombinationen neu erzeugen"
            + (f" (von Hand geänderte ersetzt der Generator nicht: in {_kurz(hand)} die Faktoren prüfen)"
               if hand else "") + ", dann neu rechnen")


def _xi_im_ergebnis(model, an) -> str:
    """Gerechnete Kombinationen mit den alten 6.10b-Faktoren."""
    gerechnet = {str(n) for n in (getattr(an, "combinations", None) or {})}
    namen = [n for n in _xi_alte_faktoren(model) if n in gerechnet]
    return ("Kombinationen " + _kurz(namen)) if namen else ""


def _en1990_erzeugt(c) -> bool:
    """Vom Generator nach DIN EN 1990 erzeugt (aus Dateien ohne Fingerabdruck: die
    Beschreibung „auto…“)."""
    return (getattr(c, "erzeugt", "") == "EN 1990"
            or (not getattr(c, "erzeugt", "") and str(getattr(c, "description", "") or "").startswith("auto")))


def _din19704_fehlende(model) -> list:
    """[(Lastfall, Kategorie)] der Lastfaelle mit einer Einwirkung der DIN 19704, die
    der Generator nach DIN EN 1990 bis zum 09.11.2026 still wegliess (Befund A5 der
    Pruefagenten), und die noch fehlen - nur in einem Modell mit Kombinationen dieses
    Generators. Eigengewicht Ausruestung, Wasserdruck, Eis, Schwall, Wind bei
    Bewegung, Antriebsmoment, Anprall, Verklemmen: in keiner dieser Kombinationen;
    Erdbeben und Montage (fuer sie bildet er keine Kombination, Befund 44): in keiner
    Kombination des Modells. Bemessungslastfaelle zaehlen nicht."""
    from .model import KATEGORIEN_DIN19704_EN1990, KATEGORIEN_OHNE_EN1990
    kombis = list((getattr(model, "combinations", None) or {}).values())
    erzeugt = [c for c in kombis if _en1990_erzeugt(c)]
    if not erzeugt:
        return []

    def in_keiner(n, liste):
        return all(abs(float((getattr(c, "factors", None) or {}).get(n, 0.0))) < 1e-12
                   and not any(abs(float(a.get(n, 0.0))) >= 1e-12 for a in (getattr(c, "alternativen", None) or []))
                   for c in liste)
    aus = []
    for n, lc in (getattr(model, "load_cases", None) or {}).items():
        kat = getattr(lc, "category", "")
        if getattr(lc, "faktorisiert", False):
            continue
        if (kat in KATEGORIEN_DIN19704_EN1990 and in_keiner(n, erzeugt)) \
                or (kat in KATEGORIEN_OHNE_EN1990 and in_keiner(n, kombis)):
            aus.append((str(n), kat))
    return aus


def _din19704_kategorie_fehlt(model) -> bool:
    """Ein Lastfall mit einer Einwirkung der DIN 19704, der in keiner Kombination des
    Generators nach DIN EN 1990 steht (Erdbeben, Montage: in keiner Kombination) -
    :func:`_din19704_fehlende`."""
    return bool(_din19704_fehlende(model))


def _din19704_im_modell(model) -> str:
    from .model import KATEGORIEN_OHNE_EN1990
    fehlen = _din19704_fehlende(model)
    if not fehlen:
        return ""
    teile = []
    gen = [n for n, k in fehlen if k not in KATEGORIEN_OHNE_EN1990]
    ohne = [f"{n} ({'Erdbeben' if k == 'ERD' else 'Montage'})" for n, k in fehlen if k in KATEGORIEN_OHNE_EN1990]
    if gen:
        teile.append(f"{_kurz(gen)} in keiner nach EN 1990 erzeugten Kombination – Lasten › „EN 1990…“: "
                     "die Kombinationen neu erzeugen, dann neu rechnen")
    if ohne:
        teile.append(f"{_kurz(ohne)} in keiner Kombination – die Kombinationen "
                     "mit Lasten › „DIN 19704“ bilden oder von Hand anlegen, dann neu rechnen")
    return "; ".join(teile)


def _en1990_im_ergebnis(model, an) -> str:
    """Gerechnete Kombinationen des Generators nach DIN EN 1990."""
    kombis = getattr(model, "combinations", None) or {}
    namen = sorted(str(n) for n in (getattr(an, "combinations", None) or {})
                   if n in kombis and _en1990_erzeugt(kombis[n]))
    return ("Kombinationen " + _kurz(namen)) if namen else ""


def _laminat_gekoppelt_mit_temperatur(model) -> bool:
    """Eine geschichtete Schale mit Kopplung (unsymmetrischer Aufbau, B != 0)
    unter gleichmaessiger Temperatur dT - ihre Momente trugen bis zum
    09.11.2026 den Anteil B alpha dT zu viel (Nebenbefund 14)."""
    from . import assemble as asm
    from . import elemente as _EL
    gekoppelt = set()
    for name, prop in (getattr(model, "shells", None) or {}).items():
        try:
            lam = asm.laminat_von(model, prop)
        except Exception:        # noqa: BLE001 - unlesbarer Aufbau: nicht betroffen
            lam = None
        if lam is not None and float(abs(lam.B).max()) > 1e-9 * float(abs(lam.A).max()) * float(prop.t or 1.0):
            gekoppelt.add(str(name))
    if not gekoppelt:
        return False
    flaechen = getattr(model, "flaechen", None) or {}
    elemente = getattr(model, "elements", None) or []
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for gl in getattr(lc, "geometrielasten", None) or []:
            if getattr(gl, "lastart", "") != "temperatur" or not float(getattr(gl, "dT", 0.0) or 0.0):
                continue
            f = flaechen.get(str(gl.ziel)) if getattr(gl, "art", "flaeche") == "flaeche" else None
            if f is not None and str(getattr(f, "dicke", "") or "") in gekoppelt:
                return True
        for tl in getattr(lc, "temp_loads", None) or []:
            if (float(getattr(tl, "dT", 0.0) or 0.0) and 0 <= int(tl.elem) < len(elemente)
                    and elemente[int(tl.elem)].typ in _EL.SCHALEN_TYPEN
                    and str(elemente[int(tl.elem)].sec) in gekoppelt):
                return True
    return False


def _fu_anders_als_bisher(mat, t: float) -> bool:
    """Liest der Nachweis heute ein anderes f_u als bis zum 09.11.2026? Bisher
    Material.ultimate_strength (mit f_y und ohne Wert f_u: 1,3 f_y, auch wenn eine
    Stahlsorte angegeben ist), heute Material.zugfestigkeit_angegeben (Wert, Dicke,
    Stahlsorte, sonst keins). Verschieden ist es ohne f_u ganz und - Befund 1 der
    Pruefagenten, 11.11.2026 - bei f_y mit Stahlsorte ohne Wert f_u: dann gilt heute
    das f_u der Sorte statt 1,3 f_y (Schraubenstab M16, f_y 640, S355: η 1,7346
    statt 1,0633)."""
    neu = mat.zugfestigkeit_angegeben(t)
    alt = float(mat.ultimate_strength(t) or 0.0)
    return neu is None or abs(float(neu) - alt) > 1e-9 * max(1.0, alt)


def _schraubenstab_ohne_fu(model) -> bool:
    """Ein Stab mit Gewinde (Nachweis als Schraube), dessen Werkstoff f_y, aber
    keinen Wert f_u angibt - dort rechnete der Nachweis bis zum 09.11.2026 still
    mit f_ub = 1,3 f_y (Nebenbefund 15), auch neben einer Stahlsorte; jetzt nimmt
    er das f_u der Sorte oder wird ohne sie nicht gefuehrt (:func:`_fu_anders_als_bisher`)."""
    from .ec3 import schraubenstab as _ss
    from .joints.bolts import SIZES
    for e in getattr(model, "elements", None) or []:
        if getattr(e, "typ", "") not in ("beam", "beam_shear", "truss", "seil"):
            continue
        mat = (getattr(model, "materials", None) or {}).get(e.mat)
        sec = (getattr(model, "sections", None) or {}).get(e.sec)
        if mat is None or sec is None or not _ss.ist_schraube(sec, mat):
            continue
        d = SIZES[_ss.schraubengroesse(sec)][0] * 1e-3
        if mat.yield_strength(d) and _fu_anders_als_bisher(mat, d):
            return True
    return False


def _stab_mit_versatz(model) -> bool:
    """Ein Stabelement mit Versatz der Stabenden (Exzentrizitaet) - seine
    geometrische Steifigkeit wirkte bis zum 09.11.2026 auf die Knoten statt
    auf die Stabenden (Nebenbefund 16 b)."""
    from . import assemble as asm
    return any(getattr(e, "typ", "") in asm.LINE_TYPES and asm.beam_versatz(e) is not None
               for e in getattr(model, "elements", None) or [])


def _balken_mit_schubflaeche(model) -> bool:
    """Ein Balkenelement, dessen Querschnitt eine Schubflaeche hat - sein
    Feldanteil N w nach Theorie II. Ordnung liess bis zum 09.11.2026 die
    Schubverformung aus (Nebenbefund 16 c)."""
    schnitte = getattr(model, "sections", None) or {}
    for e in getattr(model, "elements", None) or []:
        sec = schnitte.get(e.sec) if getattr(e, "typ", "") in ("beam", "beam_shear") else None
        if sec is not None and (float(getattr(sec, "Asy", 0.0) or 0.0) > 0
                                or float(getattr(sec, "Asz", 0.0) or 0.0) > 0):
            return True
    return False


def _flaechen_teilstellen(model) -> bool:
    """Schalenflaechen, die sich ohne gemeinsame Linie beruehren (Befund A19):
    Knoten auf fremder Randlinie oder Randlinie in fremder Flaeche."""
    try:
        from . import mesher
        return bool(mesher.flaechen_teilstellen(model))
    except Exception:                       # noqa: BLE001
        return False


def _trennflaechen_getrennt(model) -> bool:
    """Zwei Koerper mit je einer eigenen Trennflaeche ueber denselben Randlinien, ohne
    Kontaktbedingung, und ein vorhandenes Netz, das dort getrennt ist (Befund A16)."""
    try:
        from . import mesher
        return any(not s["kontakt"] and mesher.trennstelle_getrennt(model, s)
                   for s in mesher.trennstellen(model))
    except Exception:                       # noqa: BLE001
        return False


def _zwang_an_feder(model) -> bool:
    """Eine Zwangsverformung an einem linearen Federlager - dort wirkte sie bis
    zum 09.11.2026 nicht (Befund A11 der Pruefagenten)."""
    faelle = [lc for lc in (getattr(model, "load_cases", None) or {}).values()
              if getattr(lc, "zwangsverformungen", None)]
    if not faelle:
        return False
    from . import supports as sup
    lin, _ = sup.split(sup.expand(model))
    federn = {e.index for e in lin if e.typ == "spring" and e.stiffness}
    starr = {e.index for e in lin if e.typ == "rigid"}
    for lc in faelle:
        for zv in lc.zwangsverformungen:
            for d in zv.dofs:
                i = 6 * int(zv.node) + int(d)
                if i in federn and i not in starr:
                    return True
    return False


def _anschluss_ohne_festigkeit(model) -> bool:
    """Ein nachzuweisender Anschluss, dessen Werkstoff f_y oder einen Wert f_u nicht
    angibt - dort rechnete der Nachweis bis zum 09.11.2026 still mit 1,3 f_y bzw.
    S355 (Befund A23 der Pruefagenten); jetzt nimmt er das f_u der Stahlsorte oder
    wird nicht gefuehrt (Befund 1, 11.11.2026: f_y mit Sorte, ohne Wert f_u -
    Lasche S235 f_u 360 statt 305,5 N/mm²)."""
    elemente = getattr(model, "elements", None) or []
    for j in (getattr(model, "joints", None) or {}).values():
        if not getattr(j, "design", True):
            continue
        i = int(getattr(j, "elem", -1))
        if not 0 <= i < len(elemente):
            continue
        e = elemente[i]
        mat = (getattr(model, "materials", None) or {}).get(e.mat)
        sec = (getattr(model, "sections", None) or {}).get(e.sec)
        if mat is None or sec is None:
            continue
        t = float(getattr(sec, "t_max", 0.0) or 0.0)
        if not mat.yield_strength(t) or _fu_anders_als_bisher(mat, t):
            return True
    return False


def _kontakt_nur_koerper(model) -> bool:
    """Eine Kontaktbedingung, die nur Koerper nennt (geloest und Gegenkoerper, keine
    Flaechen) - sie blieb bis zum 09.11.2026 unausgefuehrt (Befund A17)."""
    for kb in (getattr(model, "kontaktbedingungen", None) or {}).values():
        if (not getattr(kb, "flaechennamen", None) and not getattr(kb, "gegenflaechen", None)
                and getattr(kb, "koerpernamen", None) and getattr(kb, "gegenkoerper", None)
                and not getattr(kb, "aus", False)):
            return True
    return False


def _balken_mit_gelenk(model) -> bool:
    """Ein Balkenelement (nicht Fachwerkstab, Seil) mit Stabendgelenk oder
    Federgelenk - seine geometrische Steifigkeit war bis zum 09.11.2026 nicht
    kondensiert (Befund A7)."""
    for e in getattr(model, "elements", None) or []:
        if getattr(e, "typ", "") in ("beam", "beam_shear") and (e.hinges or getattr(e, "hinge_springs", None)):
            return True
    return False


def _balken(model) -> bool:
    """Ein Balkenelement (nicht Fachwerkstab, Seil) - seine Schnittgroessen nach
    Theorie II. Ordnung hatten bis zum 09.11.2026 keinen Anteil k_G u und N w (A8)."""
    return any(getattr(e, "typ", "") in ("beam", "beam_shear") for e in getattr(model, "elements", None) or [])


def _gelenk_feder_null(model) -> bool:
    """Ein Gelenk mit Federsteifigkeit 0, auf Elemente gelegt (Befund A10)."""
    for h in (getattr(model, "hinges", None) or {}).values():
        if not getattr(h, "elemente", None):
            continue
        if any(t == "spring" and not float(k) > 0 for t, k in zip(h.typ, h.stiffness)):
            return True
    return False


def _theorie2_gerechnet_im_ergebnis(model, an) -> str:
    """Ergebnisse, die nach Theorie II. Ordnung gerechnet sind (nicht nur alpha_cr)."""
    th2 = getattr(an, "theorie2", None)
    namen = [str(n) for n, i in (getattr(th2, "kombinationen", None) or {}).items()
             if getattr(i, "gerechnet", False)]
    for n, r in _ergebnis_paare(an):
        if str((getattr(r, "info", None) or {}).get("theorie", "")).startswith("II."):
            namen.append(str(n))
    namen = sorted(set(namen))
    return ("Theorie II. Ordnung: " + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "")) if namen else ""


def _balken_teilbar(model) -> bool:
    """Ein Balken, den die interne Stabteilung teilt (statik3d.stabteilung,
    12.11.2026) - bis dahin rechnete Theorie II./III. Ordnung ihn in seinen
    Elementen, mit einem Element je Stab ohne Anteil N w bei gehaltenen Enden."""
    try:
        from .stabteilung import teilzahlen
        return bool(teilzahlen(model))
    except Exception:                       # noqa: BLE001 - Pruefung, nie Abbruch
        return False


def _theorie2_oder_3_im_ergebnis(model, an) -> str:
    teile = [t for t in (_theorie2_gerechnet_im_ergebnis(model, an), _theorie3_im_ergebnis(model, an)) if t]
    return "; ".join(teile)


def _schalen(model) -> bool:
    """Ein Schalenelement - seine Komponenten sigma_x, n_x, m_x standen bis zum
    09.11.2026 in Elementachsen (Befund A20)."""
    return any(str(getattr(e, "typ", "")).startswith("shell") for e in getattr(model, "elements", None) or [])


def _schalen_uneinheitlich(model) -> bool:
    """Schalenelemente, die gegen ihre Flaeche oder ihr zusammenhaengendes
    Stueck liegen (statik3d.schalenlage, Stand 31). Nach einer Rechnung mit
    Stand 31 ist das Modell ausgerichtet und nicht mehr betroffen."""
    from .schalenlage import uneinheitlich
    return uneinheitlich(model)


def _quader_teilung_ungleich(model) -> bool:
    """Ein Koerper mit einer Teilung, die nicht in allen Richtungen gleich ist (A14)."""
    for k in (getattr(model, "koerper", None) or {}).values():
        t = list(getattr(k, "teilung", None) or [])
        if len(set(int(x) for x in t[:3])) > 1:
            return True
    return False


def _druck_quadratische_seiten(model) -> bool:
    """Eine Flaechenlast senkrecht auf eine Seite eines quadratischen
    Volumenelements (A15: bis 09.11.2026 laengs der Eckennormale)."""
    quad = {i for i, e in enumerate(getattr(model, "elements", None) or [])
            if getattr(e, "typ", "") in ("tet10", "hex20", "pent15")}
    if not quad:
        return False
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for fl in getattr(lc, "face_loads", None) or []:
            if int(getattr(fl, "elem", -1)) in quad and getattr(fl, "direction", None) is None:
                return True
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


def _deckel_im_ergebnis(model, an) -> Optional[str]:
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


def _fachwerk_druckstaebe(model) -> bool:
    """Fachwerkstab, der Druck tragen kann (truss, nicht „trägt nur Zug“) - das
    Einzelknicken (d1d8ebb) betrifft nur gedrueckte Fachwerkstaebe; Seile und
    Zugstaebe fallen bei Druck aus."""
    return any(getattr(e, "typ", "") == "truss" and getattr(e, "nur", "") != "zug"
               for e in getattr(model, "elements", None) or [])


def _lastfaelle_von(model, name) -> set:
    """Die Lastfaelle eines Ergebnisses: der Lastfall selbst oder die Lastfaelle mit
    Faktor in der Kombination (auch „EK [k]“-Alternativen)."""
    name = str(name)
    lcs = getattr(model, "load_cases", None) or {}
    if name in lcs:
        return {name}
    c = (getattr(model, "combinations", None) or {}).get(name.split(" [")[0])
    return {lf for lf, f in (getattr(c, "factors", None) or {}).items() if f}


def _situation_von(model, name) -> str:
    name = str(name)
    obj = (getattr(model, "load_cases", None) or {}).get(name) or \
        (getattr(model, "combinations", None) or {}).get(name.split(" [")[0])
    return str(getattr(obj, "situation", "") or "")


def _alpha_cr_namen(an) -> list:
    th2 = getattr(an, "theorie2", None)
    komb = getattr(th2, "kombinationen", None) or {}
    return [str(n) for n, i in komb.items() if getattr(i, "alpha_cr", None) is not None]


def _alpha_cr_aktiv_im_ergebnis(model, an) -> str:
    """alpha_cr eines Ergebnisses, in dessen Situation Elemente nicht wirken
    (Stab aus, Situation, Stellung) - nur dort stand bis 878369b ein abgeschalteter
    Stab in K_g."""
    namen = []
    for n in _alpha_cr_namen(an):
        try:
            if not bool(model.aktive_elemente(_situation_von(model, n)).all()):
                namen.append(n)
        except Exception:                               # noqa: BLE001
            namen.append(n)
    return ("alpha_cr in " + ", ".join(sorted(namen)[:6])) if namen else ""


def _seil_theorie3_im_ergebnis(model, an) -> str:
    """Theorie III. Ordnung fuer ein Ergebnis, dessen Lastfaelle eine Streckenlast auf
    einem Seil tragen (bis fea5b8b wirkte sie dort nicht)."""
    mit = _lastfaelle_mit(model, lambda lc: any(int(getattr(b, "elem", -1)) in set(_staebe(model, ("seil",)))
                                                for b in getattr(lc, "beam_loads", None) or []))
    th3 = getattr(an, "theorie3", None)
    namen = [str(n) for n in (getattr(th3, "kombinationen", None) or {})]
    for n, r_ in _ergebnis_paare(an):
        if str((getattr(r_, "info", None) or {}).get("theorie", "")).startswith("III"):
            namen.append(str(n))
    namen = sorted({n for n in namen if _lastfaelle_von(model, n) & mit})
    return ("Theorie III. Ordnung: " + ", ".join(namen[:6])) if namen else ""


def _lastfaelle_mit(model, bedingung) -> set:
    return {n for n, lc in (getattr(model, "load_cases", None) or {}).items() if _sicher(lambda: bedingung(lc))}


def _querlast_lastfaelle(model) -> set:
    """Lastfaelle mit einer Querlast auf einem Fachwerkstab oder Seil: Stablast oder
    Eigengewicht quer zur Stabachse."""
    import numpy as np
    st = _staebe(model)
    stset = set(st)
    X = np.asarray(getattr(model, "nodes", None), float).reshape(-1, 3)
    out = set()
    for n, lc in (getattr(model, "load_cases", None) or {}).items():
        if any(int(getattr(b, "elem", -1)) in stset for b in getattr(lc, "beam_loads", None) or []):
            out.add(n)
            continue
        g = np.asarray(getattr(lc, "gravity", None) or [0, 0, 0], float)
        if g.size != 3 or np.linalg.norm(g) <= 0:
            continue
        for i in st:
            e = model.elements[i]
            d = X[int(e.nodes[1])] - X[int(e.nodes[0])]
            nd = float(np.linalg.norm(d))
            if nd > 0 and np.linalg.norm(np.cross(d / nd, g / np.linalg.norm(g))) > 1e-6:
                out.add(n)
                break
    return out


def _querlast_im_ergebnis(model, an) -> str:
    """Ein gerechnetes Ergebnis, dessen Lastfaelle eine Querlast auf einem
    Fachwerkstab oder Seil tragen (bis 4a6bba9 qL²/24 statt qL²/8)."""
    mit = _querlast_lastfaelle(model)
    namen = sorted({str(n) for n, _r in _ergebnis_paare(an) if _lastfaelle_von(model, n) & mit})
    return ("Querlast in " + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "")) if namen else ""


def _einzelknicken_im_ergebnis(model, an) -> str:
    namen = _alpha_cr_namen(an)
    return ("alpha_cr ohne Einzelknicken: " + ", ".join(sorted(namen)[:6])) if namen else ""


def _alpha_cr_im_ergebnis(an, _an2=None) -> str:
    """alpha_cr, Theorie II. Ordnung oder Knicken im Ergebnis (geometrische Steifigkeit);
    mit zwei Argumenten (Modell, Analyse) wie die uebrigen Pruefungen. Theorie III.
    Ordnung rechnete schon vor 5a5e8d0 mit der Saitenform."""
    if _an2 is not None:
        an = _an2
    th2 = getattr(an, "theorie2", None)
    komb = getattr(th2, "kombinationen", None) or {}
    namen = [str(n) for n, i in komb.items() if getattr(i, "alpha_cr", None) is not None]
    for n, r in (_ergebnis_paare(an)):
        th = str((getattr(r, "info", None) or {}).get("theorie", ""))
        # „III. Ordnung“ beginnt auch mit „II“ - Theorie III ist nicht gemeint (Befund 45)
        if getattr(r, "kind", "") == "buckling" or (th.startswith("II") and not th.startswith("III")):
            namen.append(str(n))
    namen = sorted(set(namen))
    return ("alpha_cr bzw. Theorie II. Ordnung: " + ", ".join(namen[:6]) + (" …" if len(namen) > 6 else "")
            if namen else "")


def _theorie3_im_ergebnis(model, an) -> str:
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


def _traglast_im_ergebnis(model, an) -> str:
    """Plastische Ergebnisse, die das alte Verfahren (vor plast/traglast, 16.10.2026)
    beruehrt haben kann: nicht konvergiert (heute: Traglast mit dem letzten
    konvergierten Zustand, bis dahin der Zustand der nicht konvergierten Stufe),
    ε_p,max ueber 20 % (heute nicht gueltig) und jeder Lastfall mit Endvorspannung im
    Spannschritt - ob dessen Spannstufen konvergierten, steht in einer alten
    Ergebnisdatei nicht (am Pruefblech meldete der Lastfall „konvergiert“ mit
    ε_p 2 399 aus einem nicht konvergierten Spannschritt)."""
    namen = []
    for n, r in _ergebnis_paare(an):
        inf = getattr(r, "info", None) or {}
        pz = inf.get("plastizitaet") if isinstance(inf, dict) else None
        if not isinstance(pz, dict):
            continue
        if (pz.get("konvergiert", True) is False or float(pz.get("eps_p_max", 0.0) or 0.0) > 0.2
                or (inf.get("vorspannung") or {}).get("weg") == "spannen und verriegeln"):
            namen.append(str(n))
    namen = sorted(set(namen))
    return ("plastisch, nicht konvergiert, ε_p über 20 % oder mit Spannschritt: " + ", ".join(namen[:6])
            + (" …" if len(namen) > 6 else "")) if namen else ""


def _mehrstufig(model) -> bool:
    """Rechnet ein Lastfall des Modells in mehreren Stufen: plastisch (Laststufen) oder
    mit Sollkraft (Spannschritt, Spannstufen)?"""
    if _fliessen(model):
        return True
    try:
        from .vorspannkraft import sollkraefte
        return any(sollkraefte(model, {n: 1.0}) for n in (getattr(model, "load_cases", None) or {}))
    except Exception:                                   # noqa: BLE001
        return False


def _reibung_mehrstufig(model) -> bool:
    """Kontakt mit μ > 0 und mehrstufiger Rechnung - das Merkmal des Gleitweg-Speichers."""
    return _hat_reibung_mu(model) and _mehrstufig(model)


def _gleitweg_im_ergebnis(model, an) -> str:
    """Ergebnisse, die ohne Gleitweg-Speicher (vor dem 17.10.2026) anders gerechnet sein
    koennen: plastisch (Laststufen) oder mit Spannschritt. Ob in einer frueheren Stufe ein
    Knoten glitt, steht in der Ergebnisdatei nicht - dann lieber „möglicherweise betroffen“."""
    namen = []
    for n, r in _ergebnis_paare(an):
        inf = getattr(r, "info", None) or {}
        if not isinstance(inf, dict):
            continue
        if isinstance(inf.get("plastizitaet"), dict) or (inf.get("vorspannung") or {}).get("weg") == "spannen und verriegeln":
            namen.append(str(n))
    namen = sorted(set(namen))
    return ("mit Reibung in mehreren Stufen (Spannschritt oder Laststufen): " + ", ".join(namen[:6])
            + (" …" if len(namen) > 6 else "")) if namen else ""


def _marke_traglast(inhalt: dict) -> bool:
    """Eine Datei, sicher nach plast/traglast gerechnet: ein plastisches Ergebnis traegt
    die Gueltigkeitsgrenze (res.info["plastizitaet"]["dehnungsgrenze"], seit 16.10.2026)."""
    return any(isinstance(i.get("plastizitaet"), dict) and "dehnungsgrenze" in i["plastizitaet"]
               for i in _infos(inhalt))


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


#: Reibbeiwert, den RFEM in jedem Lager traegt, auch ohne Reibungsart (Vorgabe 0,1)
RFEM_MU_VORGABE = 0.1
#: Quittung „selbst gesetzt – behalten“ (16.10.2026): steht im Merkmal des Imports
#: (meta „rfem_lagerreibung“), das die Datei ohnehin traegt - danach gibt es weder
#: Markierung noch Ladehinweis; die Rechnung aendert sie nicht (meta zaehlt nicht in
#: der Kennung)
LAGERREIBUNG_BEHALTEN = "selbst gesetzt – behalten"


def lagerreibung_behalten(model) -> None:
    """Die Reibbeiwerte der aus RFEM uebernommenen Lager sind selbst gesetzt und
    bleiben: Quittung im Modell, Importhinweis „lagerreibung“ erledigt."""
    import datetime
    meta = getattr(model, "meta", None)
    if meta is None:
        meta = model.meta = {}
    meta["rfem_lagerreibung"] = f"{LAGERREIBUNG_BEHALTEN} ({datetime.date.today():%d.%m.%Y})"
    for h in getattr(model, "importhinweise", None) or []:
        if h.get("art") == "lagerreibung":
            h["erledigt"] = True


def _import_lagerreibung(model) -> bool:
    """Aus RFEM 6 vor edc00eb (15.10.2026) uebernommen (kein meta „rfem_lagerreibung“, auch
    keine Quittung), ein Lager mit dem RFEM-Vorgabewert μ = 0,1 und der Hinweis
    „lagerreibung“ nicht erledigt. Ein anderes μ wird nie markiert (Anwender 16.10.2026):
    es ist ausdruecklich gesetzt."""
    meta = getattr(model, "meta", None) or {}
    if not _rfem(model) or meta.get("rfem_lagerreibung"):
        return False
    if any(h.get("art") == "lagerreibung" and h.get("erledigt") for h in (getattr(model, "importhinweise", None) or [])):
        return False
    from .model import NDOF
    for liste in ("supports", "line_supports", "surface_supports"):
        for s_ in getattr(model, liste, None) or []:
            if any(abs(float(s_.dof_behaviour(d).mu or 0.0) - RFEM_MU_VORGABE) <= 1e-9 for d in range(NDOF)):
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
    # so legte der alte Import jeden Lastfall an (Anwender 16.10.2026: nur „alle Q“;
    # gemischte Kategorien sind nicht betroffen)
    return kat == {"Q"}


def _kombinationen_im_ergebnis(model, an) -> str:
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
#: „reibverfahren“ (ab a371cf2) sind nach allen gerechnet. Stand 3: Traglast, Mechanismus,
#: Gueltigkeitsgrenze und Gleichgewicht mit inneren Kraeften (plast/traglast, 16.10.2026).
#: Stand 4: Gleitweg-Speicher der Reibungstangente (kontakt/pendeln-rt, 17.10.2026).
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
        # plast/traglast (16.10.2026, Auftrag des Anwenders): bis dahin rechnete der
        # Newton nach einer nicht konvergierten Laststufe mit deren Zustand weiter,
        # ein nicht konvergierter Spannschritt ging unbemerkt in den Lastfall
        # (Pruefblech 900 kN: „konvergiert“ mit ε_p 2 399), und die Gleichgewichts-
        # kontrolle pruefte nur Φᵀ(F + R), was fuer jedes u null ist
        name="traglast", titel="Plastische Rechnung über der Traglast",
        texte={"alt": "nicht konvergierte Lauf- und Spannstufen weitergerechnet, Gleichgewicht nur als "
                      "Summe der Lasten und Lagerkräfte",
               "neu": "Traglast mit letztem konvergiertem Zustand, Mechanismus, Gültigkeitsgrenze ε_p, "
                      "Gleichgewicht mit inneren Kräften"},
        wechsel=(Wechsel(stand=3, datum="16.10.2026", commit="045d1bc, 5d747de", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="plastische Rechnung", betrifft=_fliessen, im_ergebnis=_traglast_im_ergebnis,
        marke=_marke_traglast),
    Merkmal(
        # kontakt/pendeln-rt (17.10.2026, Auftrag des Anwenders): die Reibungstangente
        # rechnete ohne Gedaechtnis des Gleitwegs - in der Stufe nach einer Stufe mit Gleiten
        # zog die Haftfeder zur Ausgangslage zurueck, die Reibkraft trieb die Bewegung an
        # (Klotz mit Reibung: 17 von 17 Knoten mit negativer Dissipation, gleitet statt zu
        # haften; tests/test_gleitweg)
        name="gleitweg", titel="Gleitweg der Reibung über Stufen",
        texte={"alt": "Haftfeder auf den ganzen Weg seit der Ausgangslage (ohne Gleitweg)",
               "neu": "Gleitweg je Reibknoten, fortgeschrieben am Ende jeder Stufe"},
        wechsel=(Wechsel(stand=4, datum="17.10.2026", commit="a0bd908", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Kontakt mit μ > 0 und mehrstufiger Rechnung (Spannschritt oder Plastizität)",
        betrifft=_reibung_mehrstufig, im_ergebnis=_gleitweg_im_ergebnis),
    Merkmal(
        # kontakt/master-voll (06.11.2026): die Gegenseite einer Fuge war nur das, was die
        # Schwerpunkte der Kontaktseite als Naechstes trafen; auf einer gekruemmten Fuge
        # wanderte der Masterpunkt der Randknoten um L/3 (Drehlager Mittel: 177 statt 663
        # Bedingungen, 34,7 kNm Momentenluecke; tests/test_master_voll)
        name="gegenseite", titel="Gegenseite der Kontaktfugen",
        texte={"alt": "Gegenfacetten nur, soweit eine Facette der Kontaktseite sie als nächste traf; "
                      "fast ganz überdeckte Facetten einer gekrümmten Fuge als Rand der Überdeckung",
               "neu": "die ganze Gegenfläche; Überdeckung mit der Facettenkrümmung beurteilt"},
        wechsel=(Wechsel(stand=5, datum="06.11.2026", commit="kontakt/master-voll-2026-11-06", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Kontakt: Fuge mit Kontaktpaar (ungleiche Netze)", betrifft=_fuge_mit_kontaktpaar),
    Merkmal(
        # f70703c (06.11.2026, mit kontakt/master-voll integriert, Stand 5): res.solid_res und
        # res.solid_knoten einer plastischen Rechnung trugen bis dahin die Elementecken - am
        # Drehlager (Mittel) 14 379 N/mm2 an einer Ecke mit det J das 0,006-Fache, die
        # Gausspunkte desselben Elements hoechstens 344 N/mm2 (tests/test_plastisch_gausspunkte).
        # Beide stehen in der Ergebnisdatei: Fehlerkorrektur (Anwender 08.11.2026)
        name="gausspunkte", titel="Elementwert und Knotentabelle plastischer Rechnungen",
        texte={"alt": "Elementwert und Knotentabelle aus den Elementecken",
               "neu": "Elementwert und Knotentabelle aus den Integrationspunkten"},
        wechsel=(Wechsel(stand=5, datum="06.11.2026", commit="f70703c", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="plastische Rechnung", betrifft=_fliessen),
    Merkmal(
        # 0dcf399 (16.10.2026, mit plast/traglast integriert, Stand 3): Kraft und Moment der nur
        # numerisch gehaltenen Freiheitsgrade (Pivot-Regularisierung, weiche Feder unter 1e-9
        # der Hauptdiagonale) fehlten in der globalen Gleichgewichtskontrolle; ein so
        # gehaltenes Modell konnte als im Gleichgewicht gelten. Welche Freiheitsgrade es
        # waren, zeigt Results.singular (freie Bewegungen der Rechnung): nur ein Ergebnis mit
        # solchen traegt den Status (Fehlerkorrektur, Anwender 08.11.2026; test_frei_drehbar_streng)
        name="haltekraefte", titel="Numerisch gehaltene Freiheitsgrade im Gleichgewicht",
        texte={"alt": "Gleichgewichtskontrolle ohne die Kräfte nur numerisch gehaltener Freiheitsgrade",
               "neu": "Gleichgewichtskontrolle mit Kraft und Moment nur numerisch gehaltener Freiheitsgrade"},
        wechsel=(Wechsel(stand=3, datum="16.10.2026", commit="0dcf399", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="freie Bewegung, die nur die Pivot-Regularisierung hielt (Results.singular)",
        im_ergebnis=_haltekraefte_im_ergebnis),
    Merkmal(
        # PR #39 (08.11.2026, 7f92425): das Ingenieurkriterium des Kontaktlaufs bezog das
        # Gleichgewicht auf |Summe F|; im Spannschritt (Kraeftepaar) ist sie null, und jeder
        # Abschluss wurde abgelehnt. Am Drehlager mit mu = 1 gleiche Ergebnisse auf zwei Wegen,
        # 618 statt 863 Zerlegungen: Verbesserung (Anwender 08.11.2026)
        name="gleichgewichtsbezug", titel="Gleichgewichtsbezug im Spannschritt",
        texte={"alt": "Ingenieurkriterium bezieht das Gleichgewicht auf die Summe der äußeren Kräfte",
               "neu": "bei Kräftesumme null bezieht es das Gleichgewicht auf die Druckkräfte des Kontakts"},
        wechsel=(Wechsel(stand=6, datum="08.11.2026", commit="7f92425", alt="alt", neu="neu",
                         art=VERBESSERUNG),),
        modellmerkmal="Kontakt mit Spannschritt (Vorspannung als Kraft)", betrifft=_kontakt_mit_spannschritt),
    Merkmal(
        # Nebenbefund Oberflaechenpaket B (08.11.2026): der Windschatten einer projizierten
        # Flaechenlast fragte die Aussennormale einer Volumenseite; an einer Schale gibt es
        # keine, und die Last erzeugte nichts - Schnee 5 kN/m2 auf einem Dach von 2 m2
        # Grundriss gab 0 statt 10 kN (tests/test_paket_b_neben). Fehlerkorrektur
        name="projiziert_schale", titel="Flächenlast auf die Projektion an Schalen",
        texte={"alt": "projizierte Flächenlast an einer Schale ohne Wirkung",
               "neu": "projizierte Flächenlast an einer Schale mit p · A · |n · d|"},
        wechsel=(Wechsel(stand=7, datum="08.11.2026", commit="fix/paket-b-nebenbefunde", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Flächenlast auf die Projektion an einer Schale", betrifft=_projiziert_auf_schale),
    Merkmal(
        # Befunde A1/A2 der Pruefagenten (09.11.2026): der Windgenerator gab fuer Schalen p
        # „gegen die Aussennormale“, die Schalenlast wirkt mit der Elementnormalen - Luvdruck,
        # Leesog und Dachsog wirkten gegen den Wind (Gebaeude 10 x 20 x 8 m: ΣF −135/−127
        # statt +135/+127 kN); an Volumen und shell8 waren alle Flaechen „Seite“. Fehlerkorrektur.
        # Seit dem 11.11.2026 (Befund 40, fix/k-wind) eine Korrektur am Modell: die Last steht mit
        # dem Modell in der Datei und rechnet nach dem Oeffnen und jedem Neurechnen weiter
        # verkehrt - der Status haengt an den Windlasten ohne Aussenseite und bleibt, bis sie
        # neu erzeugt sind (wind.alte_windlasten); dazu ein Ladehinweis
        name="wind_flaechen", titel="Windlast auf Flächen",
        texte={"alt": "Wind an Schalen gegen die Windrichtung, an Volumen und shell8 ohne Rollen",
               "neu": "Wind in die Hülle hinein (Druck) bzw. heraus (Sog), Außenseite je Fläche aus der "
                      "Mitte ihres Baukörpers, Rollen an allen Flächen"},
        wechsel=(Wechsel(stand=8, datum="09.11.2026", commit="1b213f9, fix/k-wind", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Windlast des Generators auf Gebäudeflächen, mit einem älteren Programmstand erzeugt "
                      "(ohne Außenseite)",
        betrifft=_wind_auf_flaechen, import_korrektur=True, im_ergebnis=_alte_windlasten_im_ergebnis,
        modellgrund="Windlasten mit einem älteren Programmstand erzeugt",
        vorschlag="Lasten › Wind: den Wind öffnen und die Windlasten neu erzeugen"),
    Merkmal(
        # Befund A3 der Pruefagenten (09.11.2026): der Windschatten der projizierten Last nahm
        # die Achse ohne das Vorzeichen von p - „global Z, p = −5 kN/m²“ traf am Block die
        # Unterseite statt das Dach. Summe gleich, Angriffspunkt falsch. Fehlerkorrektur
        name="projiziert_vorzeichen", titel="Projizierte Flächenlast mit negativem Wert an Volumen",
        texte={"alt": "Last trifft die der Kraft abgewandte Seite",
               "neu": "Last trifft die der Kraft p · d zugewandte Seite"},
        wechsel=(Wechsel(stand=9, datum="09.11.2026", commit="fix/netz-alt-pruefen", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Flächenlast auf die Projektion mit negativem Wert an einem Körper",
        betrifft=_projiziert_negativ_an_volumen),
    Merkmal(
        # Befund A4 der Pruefagenten (09.11.2026): die Schale trug nur den gleichmaessigen
        # Anteil ΔT, ΔT_z wurde still verworfen (Kragstreifen 0 statt 12 mm). Jetzt die
        # Anfangskruemmung α ΔT_z / t in Last und Momentenrueckrechnung. Fehlerkorrektur
        name="temperatur_schale_dTz", titel="Temperaturunterschied oben − unten auf Schalen",
        texte={"alt": "ΔT_z auf Schalen ohne Wirkung",
               "neu": "ΔT_z auf Schalen als Krümmung α · ΔT_z / t"},
        wechsel=(Wechsel(stand=10, datum="09.11.2026", commit="fix/netz-alt-pruefen", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Temperaturunterschied ΔT_z auf einer Schale",
        betrifft=_temperaturunterschied_schale),
    Merkmal(
        # Befund A6 der Pruefagenten (09.11.2026): Regel 6.10b nahm ξ = 0,85 auf jeden
        # staendigen Faktor, auch auf γ_P und auf das guenstige G (beides 0,85 statt 1,0,
        # auf der unsicheren Seite). Fehlerkorrektur
        name="kombination_xi", titel="Abminderungsbeiwert ξ in Regel 6.10b",
        texte={"alt": "ξ auf alle ständigen Lasten, auch P und günstiges G",
               "neu": "ξ nur auf ungünstige ständige Lasten (ξ · γ_G,sup)"},
        wechsel=(Wechsel(stand=11, datum="09.11.2026", commit="fix/netz-alt-pruefen", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Kombination nach Regel 6.10b",
        # Befund 41 (11.11.2026): die Faktoren stehen in den gespeicherten Kombinationen;
        # erst neu erzeugte sind richtig - Status am Modell, bis dahin auch nach dem Neurechnen
        betrifft=_kombination_610b, im_modell=_xi_im_modell, im_ergebnis=_xi_im_ergebnis,
        vorschlag="Lasten › „EN 1990…“: die Kombinationen neu erzeugen, dann neu rechnen"),
    Merkmal(
        # Befund A11 der Pruefagenten (09.11.2026): eine Zwangsverformung wirkte nur an
        # starren gesperrten FHG; an einer Feder blieb sie still ohne Wirkung. Jetzt
        # verschiebt sie den Fusspunkt der Feder (Kraft k (u − d)). Fehlerkorrektur
        name="zwang_feder", titel="Zwangsverformung an Federlagern",
        texte={"alt": "Zwangsverformung an einer Feder ohne Wirkung",
               "neu": "Zwangsverformung verschiebt den Fußpunkt der Feder"},
        wechsel=(Wechsel(stand=12, datum="09.11.2026", commit="fix/netz-alt-pruefen", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Zwangsverformung an einem Federlager",
        betrifft=_zwang_an_feder),
    Merkmal(
        # Befund A23 der Pruefagenten (09.11.2026): ohne f_u rechnete der Anschlussnachweis
        # still mit 1,3 f_y, ganz ohne Festigkeiten mit S355 (Lasche η 1,048 -> 1,573).
        # Festlegung des Anwenders: Meldung statt Vorgabewert. Fehlerkorrektur
        name="anschluss_festigkeit", titel="Festigkeiten im Anschlussnachweis",
        texte={"alt": "fehlendes f_u als 1,3 f_y (auch neben einer Stahlsorte), fehlende Festigkeiten als S355",
               "neu": "f_y und f_u aus dem Wert oder der Stahlsorte, ohne sie kein Anschlussnachweis, mit Meldung"},
        wechsel=(Wechsel(stand=13, datum="09.11.2026", commit="fix/netz-alt-pruefen", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Anschluss mit Werkstoff ohne f_y oder ohne Wert f_u",
        betrifft=_anschluss_ohne_festigkeit),
    Merkmal(
        # Befund A17 der Pruefagenten (09.11.2026): eine Kontaktbedingung nur mit Koerpern
        # blieb unausgefuehrt; mit einer zweiten Halterung lief die Last still daran vorbei.
        # Jetzt sind die Flaechen der Gegenkoerper die Gegenseite. Fehlerkorrektur
        name="kontakt_nur_koerper", titel="Kontaktbedingung nur mit Körpern",
        texte={"alt": "Kontaktbedingung nur mit Körpern nicht ausgeführt",
               "neu": "Fuge = Seiten des gelösten Körpers auf den Gegenkörpern"},
        wechsel=(Wechsel(stand=14, datum="09.11.2026", commit="fix/netz-alt-pruefen", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Kontaktbedingung, die nur Körper nennt",
        betrifft=_kontakt_nur_koerper),
    # Befund A7 der Pruefagenten (09.11.2026): die geometrische Steifigkeit
    # eines Balkens mit Stabendgelenk war nicht kondensiert - Pendelstuetze als
    # Balken alpha_cr 1,667 statt 2,000, gezogener Gelenkstab bis +37 %.
    # Jetzt K_G = C^T k_G C wie die elastische Steifigkeit. Fehlerkorrektur
    Merkmal(
        name="theorie2_gelenke", titel="Geometrische Steifigkeit an Stabendgelenken",
        texte={"alt": "K_G eines Balkens ohne Rücksicht auf seine Gelenke",
               "neu": "K_G kondensiert wie die elastische Steifigkeit"},
        wechsel=(Wechsel(stand=15, datum="09.11.2026", commit="fix/theorie2-gruppe3", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Balken mit Stabendgelenk oder Federgelenk, mit alpha_cr, Knicken oder Theorie II. Ordnung",
        betrifft=_balken_mit_gelenk, im_ergebnis=_alpha_cr_im_ergebnis),
    # Befund A8 (09.11.2026): Stabend- und Feldmomente nach Theorie II.
    # Ordnung ohne k_G u und ohne N w (Kragarm +7,9 %, Feld bis -35 % bei einem
    # Element). Fehlerkorrektur
    Merkmal(
        name="theorie2_schnittgroessen", titel="Schnittgrößen nach Theorie II. Ordnung",
        texte={"alt": "Stabendkräfte k u, Feld ohne N·w",
               "neu": "Stabendkräfte (k + k_G) u, Feld mit N·w"},
        wechsel=(Wechsel(stand=16, datum="09.11.2026", commit="fix/theorie2-gruppe3", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Balken, nach Theorie II. Ordnung gerechnet",
        betrifft=_balken, im_ergebnis=_theorie2_gerechnet_im_ergebnis),
    # Befund A10 (09.11.2026): ein Federgelenk mit k = 0 wirkte biegesteif
    # (Skript, Web). Jetzt ist es ein Gelenk; aeltere Dateien ziehen es beim
    # Oeffnen nach (Model._gelenke_feder_null_nachziehen). Fehlerkorrektur
    Merkmal(
        name="gelenk_feder_null", titel="Federgelenk mit Steifigkeit 0",
        texte={"alt": "Federgelenk mit k = 0 biegesteif", "neu": "Federgelenk mit k = 0 gelenkig"},
        wechsel=(Wechsel(stand=17, datum="09.11.2026", commit="fix/theorie2-gruppe3", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Gelenk mit Federsteifigkeit 0",
        betrifft=_gelenk_feder_null),
    # Befund A20 (09.11.2026): sigma_x, sigma_y, tau_xy, n_x, m_x der Flaechen
    # in Elementachsen (erste Kante), so auf die Knoten gemittelt. Jetzt im
    # Flaechensystem (x = globale X-Achse in der Ebene). Fehlerkorrektur
    Merkmal(
        name="flaechen_achsen", titel="Achsen der Flächenspannungen",
        texte={"alt": "Komponenten in Elementachsen (erste Kante)",
               "neu": "Komponenten im Flächensystem (x = globale X-Achse in der Ebene)"},
        wechsel=(Wechsel(stand=18, datum="09.11.2026", commit="fix/theorie2-gruppe3", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Schalenelemente", betrifft=_schalen),
    # Befund A14 (09.11.2026): Teilung [nx, ny, nz] eines abgebildeten Quaders
    # in der Reihenfolge seiner Flaechen statt in x, y, z. Fehlerkorrektur
    Merkmal(
        name="quader_teilung_achsen", titel="Teilung des abgebildeten Quaders",
        texte={"alt": "Teilung in der Reihenfolge der Flächen", "neu": "Teilung in x, y, z"},
        wechsel=(Wechsel(stand=19, datum="09.11.2026", commit="fix/theorie2-gruppe3", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Körper mit ungleicher Teilung", betrifft=_quader_teilung_ungleich),
    # Befund A15 (09.11.2026): Druck auf gekruemmten quadratischen
    # Volumenseiten laengs der Eckennormale. Fehlerkorrektur
    Merkmal(
        name="flaechenlast_gekruemmt", titel="Flächenlast auf gekrümmten Volumenseiten",
        texte={"alt": "Druck längs der Normale der Ecken", "neu": "Druck längs der örtlichen Normale"},
        wechsel=(Wechsel(stand=20, datum="09.11.2026", commit="fix/theorie2-gruppe3", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Flächenlast senkrecht auf quadratische Volumenelemente",
        betrifft=_druck_quadratische_seiten),
    # Befund A5 (09.11.2026): der Generator nach DIN EN 1990 kannte die
    # Einwirkungen der DIN 19704 nicht und liess solche Lastfaelle still aus
    # jeder Kombination. Fehlerkorrektur; beheben heisst hier: Kombinationen
    # neu erzeugen, dann neu rechnen
    Merkmal(
        name="kategorien_din19704", titel="Einwirkungen der DIN 19704 im Generator nach EN 1990",
        texte={"alt": "Lastfälle mit Einwirkungen der DIN 19704 fehlen in den erzeugten Kombinationen",
               "neu": "G_A, W_S ständig; W_V, Eis, Schwall, Wind bei Bewegung, Antriebsmoment "
                      "veränderlich; Anprall, Verklemmen außergewöhnlich"},
        wechsel=(Wechsel(stand=21, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Lastfall mit einer Einwirkung der DIN 19704, der in keiner nach EN 1990 "
                      "erzeugten Kombination steht (Erdbeben, Montage: in keiner Kombination)",
        # Befunde 42 und 44 (11.11.2026): Status am Modell, bis die Kombinationen neu
        # erzeugt sind - ein Neurechnen allein aendert nichts
        betrifft=_din19704_kategorie_fehlt, im_modell=_din19704_im_modell, im_ergebnis=_en1990_im_ergebnis,
        vorschlag="Lasten › „EN 1990…“: die Kombinationen neu erzeugen, dann neu rechnen"),
    # Nebenbefund 14 (09.11.2026): die Rueckrechnung der Schalenmomente zog
    # bei einem Laminat mit Kopplung (B != 0) den Anteil B alpha dT nicht ab -
    # die frei gedehnte Platte zeigte ein Moment. Fehlerkorrektur
    Merkmal(
        name="laminat_temperatur", titel="Momente geschichteter Schalen unter Temperatur",
        texte={"alt": "Momente mit dem Anteil B·α·ΔT zu viel", "neu": "Momente ohne den Anteil B·α·ΔT"},
        wechsel=(Wechsel(stand=22, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="geschichtete Schale mit unsymmetrischem Aufbau unter Temperaturänderung",
        betrifft=_laminat_gekoppelt_mit_temperatur),
    # Nebenbefund 15 (09.11.2026): der Nachweis eines Stabes mit Gewinde nahm
    # bei einem Werkstoff mit f_y ohne f_u still f_ub = 1,3 f_y. Jetzt Meldung
    # statt Vorgabewert (Festlegung des Anwenders). Fehlerkorrektur
    Merkmal(
        name="schraubenstab_fu", titel="Zugfestigkeit im Nachweis der Stäbe mit Gewinde",
        texte={"alt": "ohne Wert f_u im Werkstoff mit 1,3·f_y nachgewiesen, auch neben einer Stahlsorte",
               "neu": "f_u aus dem Wert oder der Stahlsorte, ohne beides kein Nachweis, sondern Meldung"},
        wechsel=(Wechsel(stand=23, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Stab mit Gewinde, dessen Werkstoff f_y, aber keinen Wert f_u angibt",
        betrifft=_schraubenstab_ohne_fu),
    # Nebenbefund 16 b (09.11.2026): die geometrische Steifigkeit eines Stabes
    # mit Versatz wirkte auf die Knoten statt auf die Stabenden - Druckstab
    # 0,2 m neben der Knotenlinie alpha_cr 1,158 statt 2,000. Fehlerkorrektur
    Merkmal(
        name="theorie2_versatz", titel="Geometrische Steifigkeit an Stäben mit Versatz",
        texte={"alt": "K_G an den Knoten, ohne den Versatz der Stabenden",
               "neu": "K_G an den Stabenden, mit dem Versatz"},
        wechsel=(Wechsel(stand=24, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Stab mit Versatz der Stabenden, mit alpha_cr, Knicken oder Theorie II. Ordnung",
        betrifft=_stab_mit_versatz, im_ergebnis=_alpha_cr_im_ergebnis),
    # Nebenbefund 16 c (09.11.2026): der Feldanteil N w nach Theorie II.
    # Ordnung liess die Schubdurchbiegung aus - Einfeldtraeger mit
    # N_E/(G A_s) = 0,1 und Druck 0,6 N_cr in einem Element -12 %. Fehlerkorrektur
    Merkmal(
        name="theorie2_feld_schub", titel="Feldmoment nach Theorie II. Ordnung an schubweichen Balken",
        texte={"alt": "Feldanteil N·w ohne die Schubdurchbiegung",
               "neu": "Feldanteil N·w mit der Schubdurchbiegung"},
        wechsel=(Wechsel(stand=25, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Balken mit Schubfläche, nach Theorie II. Ordnung gerechnet",
        betrifft=_balken_mit_schubflaeche, im_ergebnis=_theorie2_gerechnet_im_ergebnis),
    # Nebenbefund 16 a (09.11.2026): Theorie III. Ordnung kondensierte die
    # geometrische Steifigkeit an Stabendgelenken nicht (wie Theorie II.
    # Ordnung vor A7) - mit einer Pendelstuetze als Balken mit Gelenken
    # konvergierte die Rechnung ab 5/6 der Knicklast nicht. Die Tangente
    # aendert den Weg der Iteration, nicht den konvergierten Zustand.
    # Fehlerkorrektur
    Merkmal(
        name="theorie3_gelenke", titel="Tangente der Theorie III. Ordnung an Stabendgelenken",
        texte={"alt": "geometrische Steifigkeit ohne Rücksicht auf die Gelenke",
               "neu": "geometrische Steifigkeit an den Gelenken kondensiert"},
        wechsel=(Wechsel(stand=26, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Balken mit Stabendgelenk oder Federgelenk, nach Theorie III. Ordnung gerechnet",
        betrifft=_balken_mit_gelenk, im_ergebnis=_theorie3_im_ergebnis),
    # Nachstellung vom 11.11.2026, Entscheidung des Anwenders vom 12.11.2026
    # („interne stabteilung sinnvoll vornehmen“): Theorie II./III. Ordnung
    # teilen Balken intern, jeder Stab mindestens netz.stabteilung (10)
    # Abschnitte, Theorie III. Ordnung doppelt so viele. Eingespannter
    # Einfeldtraeger mit Gelenk, Druck 0,6 N_cr, q in einem Element: 22,5
    # statt 44,2 kNm. Fehlerkorrektur
    Merkmal(
        name="stabteilung_theorie", titel="Interne Stabteilung nach Theorie II./III. Ordnung",
        texte={"alt": "Balken in seinen Elementen gerechnet (ein Element je Stab: ohne N·w bei gehaltenen Enden)",
               "neu": "Balken intern geteilt, jeder Stab mindestens in die Stabteilung der Netzeinstellungen"},
        wechsel=(Wechsel(stand=29, datum="12.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Balken in weniger Elementen je Stab als die Stabteilung, nach Theorie II. oder III. "
                      "Ordnung gerechnet",
        betrifft=_balken_teilbar, im_ergebnis=_theorie2_oder_3_im_ergebnis),
    # Nachstellung vom 11.11.2026: Theorie III. Ordnung gab am Stabendgelenk
    # mit Streckenlast q L²/12 statt 0 aus (Festeinspannkraft nicht
    # kondensiert, seit 05.09.2026); das Gleichgewicht der Knoten stimmte,
    # die Stabendkraefte nicht. Fehlerkorrektur
    Merkmal(
        name="theorie3_gelenk_last", titel="Stabendkräfte nach Theorie III. Ordnung am Gelenk mit Stablast",
        texte={"alt": "Stablast am Gelenk nicht kondensiert (Moment q L²/12 statt 0)",
               "neu": "Stablast wie die Steifigkeit kondensiert"},
        wechsel=(Wechsel(stand=30, datum="12.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Balken mit Stabendgelenk oder Federgelenk, nach Theorie III. Ordnung gerechnet",
        betrifft=_balken_mit_gelenk, im_ergebnis=_theorie3_im_ergebnis),
    # Auftrag vom 12.11.2026 („die lage von schalenelementen sollte der user frei
    # bestimmen können und sie dürfte grundsätzlich nicht an der berechnung
    # ändern“): an einem gespiegelten Element wirkten Flaechenlast senkrecht zur
    # Flaeche, dT_z, Wasserdruck und Wind verkehrt herum (Platte 8 x 8 shell4,
    # ein Element gespiegelt: ΣR_z 9 687,5 statt 10 000 N), die Knotenmittel
    # mischten Werte verschieden gerichteter Elemente. Vor jeder Rechnung werden
    # die Schalen jetzt ausgerichtet (statik3d.schalenlage). Fehlerkorrektur
    Merkmal(
        name="schalenlage", titel="Lage der Schalenelemente",
        texte={"alt": "jedes Schalenelement in der Lage seiner Knotenfolge gerechnet",
               "neu": "Schalenelemente vor der Rechnung zur Fläche bzw. ihrem Stück ausgerichtet"},
        wechsel=(Wechsel(stand=31, datum="12.11.2026", commit="fix/k2-schalenlage", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Schalenelemente, die gegen ihre Fläche oder ihr zusammenhängendes Stück liegen",
        betrifft=_schalen_uneinheitlich),
    # Befund A19 (09.11.2026): Schalenflaechen, die sich ohne gemeinsame Linie
    # beruehren, waren im Netz nicht verbunden - Stoss mit ungeteilter Linie
    # 0,742 statt 0,143 mm, Rippe auf ungeteilter Platte 33,1 statt 0,52 mm.
    # Der Vernetzer teilt jetzt im Netz (Knoten auf Linie, Linie in Flaeche).
    # Wirkt erst nach dem Neuvernetzen. Fehlerkorrektur
    Merkmal(
        name="flaechen_teilen", titel="Schalenflächen ohne gemeinsame Linie",
        texte={"alt": "im Netz nicht verbunden (nur gemeinsame Linien)",
               "neu": "im Netz geteilt und verbunden (Knoten auf Linie, Linie in Fläche); "
                      "gilt nach dem Neuvernetzen"},
        wechsel=(Wechsel(stand=27, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Schalenflächen, die sich ohne gemeinsame Linie berühren",
        betrifft=_flaechen_teilstellen),
    # Befund A16 (09.11.2026): zwei Koerper mit je einer eigenen Trennflaeche
    # ueber denselben Randlinien hingen ohne Kontaktbedingung nur ueber die
    # Randlinien zusammen - zwei Wuerfel unter Zug 52 % zu weich. Der Vernetzer
    # legt die Flaechen jetzt im Netz zusammen. Wirkt erst nach dem
    # Neuvernetzen. Fehlerkorrektur
    Merkmal(
        name="trennflaechen_zusammenlegen", titel="Deckungsgleiche Trennflächen zweier Körper",
        texte={"alt": "jede Fläche für sich vernetzt, Körper nur über die Randlinien verbunden",
               "neu": "als eine gemeinsame Fläche vernetzt (ohne Kontaktbedingung); "
                      "gilt nach dem Neuvernetzen"},
        wechsel=(Wechsel(stand=28, datum="09.11.2026", commit="fix/befunde-rest", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="zwei Körper mit eigenen, deckungsgleichen Trennflächen ohne Kontaktbedingung, "
                      "Netz dort getrennt",
        betrifft=_trennflaechen_getrennt),
    Merkmal(
        name="saitenform", titel="Geometrische Steifigkeit der Fachwerkstäbe",
        texte={"alt": "Balkenform 6/5 N/L auch für Fachwerkstab, Zug-/Druckstab und Seil",
               "neu": "Saitenform N/L für Fachwerkstab, Zug-/Druckstab und Seil"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="5a5e8d0", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Fachwerkstab, Zug-/Druckstab oder Seil, mit alpha_cr, Knicken oder Theorie II. Ordnung",
        betrifft=_hat_fachwerk_oder_seil, im_ergebnis=_alpha_cr_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="einzelknicken", titel="Einzelknicken der Fachwerk-Druckstäbe",
        texte={"alt": "alpha_cr nur des Systems, ohne Knicken der Fachwerk-Druckstäbe zwischen ihren Knoten",
               "neu": "alpha_cr = min(System; Einzelstab)"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="d1d8ebb", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Fachwerk-Druckstäbe (truss, nicht nur Zug) mit alpha_cr-Ergebnis",
        betrifft=_fachwerk_druckstaebe, im_ergebnis=_einzelknicken_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="alpha_cr_aktiv", titel="alpha_cr mit abgeschalteten Stäben",
        texte={"alt": "abgeschaltete Stäbe in der geometrischen Steifigkeit von alpha_cr",
               "neu": "alpha_cr nur aus den wirksamen Elementen"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="878369b", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="abgeschaltete Stäbe oder Elemente (Stab aus, Situation, Stellung) mit alpha_cr "
                      "bzw. Theorie II. Ordnung",
        betrifft=_abgeschaltete_staebe, im_ergebnis=_alpha_cr_aktiv_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="seil_theorie3", titel="Seil-Streckenlast nach Theorie III. Ordnung",
        texte={"alt": "Streckenlast auf dem Seil nach Theorie III. Ordnung nicht angesetzt",
               "neu": "Streckenlast auf dem Seil als Kettenlinienlast (sonst gesperrt)"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="fea5b8b", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Seil mit Streckenlast, Theorie III. Ordnung",
        betrifft=_seil_mit_streckenlast, im_ergebnis=_seil_theorie3_im_ergebnis, marke=_marke_14_10),
    Merkmal(
        name="fachwerk_querlast", titel="Fachwerkstab mit Querlast",
        texte={"alt": "Ersatzlasten mit Momenten qL²/12 (im Feld qL²/24, Lagermomente)",
               "neu": "Ersatzlasten als Kräfte, Stabmoment als Einfeldträger qL²/8"},
        wechsel=(Wechsel(stand=1.5, datum="14.10.2026", commit="4a6bba9", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="Fachwerkstab, Zug-/Druckstab oder Seil mit Stablast oder Eigengewicht quer zur Achse",
        betrifft=_fachwerk_mit_querlast, im_ergebnis=_querlast_im_ergebnis, marke=_marke_14_10),
    # --- Korrekturen am Import: das Modell, nicht das Alter der Ergebnisdatei --------
    Merkmal(
        name="import_lagerreibung", titel="Lagerreibung aus RFEM",
        texte={"alt": "Reibbeiwert der RFEM-Lager auch ohne Reibungsart übernommen",
               "neu": "Reibbeiwert nur mit Reibungsart"},
        wechsel=(Wechsel(stand=1.5, datum="15.10.2026", commit="edc00eb", alt="alt", neu="neu",
                         art=FEHLERKORREKTUR),),
        modellmerkmal="RFEM-Import ohne Merkmal rfem_lagerreibung, Lager mit μ = 0,1 (RFEM-Vorgabewert)",
        betrifft=_import_lagerreibung, import_korrektur=True,
        vorschlag="Datei › Austausch › „Aus RFEM nachlesen ▾“ › „Lager aus RFEM nachlesen…“: dort "
                  "„Lager nachlesen“ oder „selbst gesetzt – behalten“"),
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
                      "Lastfälle in Kategorie Q, gerechnete Kombinationen",
        betrifft=_import_lastkategorien, import_korrektur=True, im_ergebnis=_kombinationen_im_ergebnis,
        vorschlag="die Kategorien der Lastfälle prüfen"),
]

#: Verfahrensstand dieses Programms: der hoechste Stand der Tabelle
VERFAHRENSSTAND = 31


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
    ``art`` stuft ein). Ein unbekannter Wert (None) steht mit None darin. Merkmale, die
    erst mit neu erzeugten Kombinationen wirken (``im_modell``), stehen nicht darin:
    ihren Status sagt das Modell selbst (:func:`modell_teile`), nicht das Alter der Datei."""
    aus = []
    for mk in MERKMALE:
        if mk.import_korrektur or mk.im_modell is not None or not _sicher(lambda: mk.betrifft(model)):
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


def modell_teile(model, analyse=None) -> list:
    """Die Teile des Status aus Korrekturen, die erst mit neu erzeugten Kombinationen
    wirken (``Merkmal.im_modell``, Befunde 41, 42, 44 vom 11.11.2026): solange das
    Modell die alten Kombinationen traegt, gilt der Status fuer jede Ergebnisdatei
    und fuer eine neue Rechnung. Mit ``analyse`` nur, wenn eine betroffene
    Kombination gerechnet ist."""
    teile = []
    for mk in MERKMALE:
        if mk.im_modell is None:
            continue
        wo = _sicher(lambda: mk.im_modell(model))
        if not wo:
            continue
        if analyse is not None and mk.im_ergebnis is not None                 and _sicher(lambda: mk.im_ergebnis(model, analyse)) == "":
            continue                    # keine betroffene Kombination gerechnet
        teile.append(f"{mk.titel}: {wo}")
    for mk in MERKMALE:
        # Korrekturen am Modell, die nicht vom Import kommen (``modellgrund``, alte
        # Windlasten, Befund 40): auch eine neue Rechnung traegt den Status, bis der
        # Grund im Modell behoben ist - nicht erst nach dem erneuten Oeffnen
        if not (mk.import_korrektur and mk.modellgrund) or not _sicher(lambda: mk.betrifft(model)):
            continue
        wo = (_sicher(lambda: mk.im_ergebnis(model, analyse))
              if (mk.im_ergebnis is not None and analyse is not None) else None)
        if wo == "":
            continue
        teile.append(f"{mk.titel}: {mk.modellgrund} ({mk.text('alt')}"
                     + (f"; {wo}" if wo else "") + f") – {mk.vorschlag}, danach neu rechnen")
    return teile


def modell_betroffen(model, analyse=None) -> str:
    """Der Status einer neuen Rechnung aus :func:`modell_teile` - oder ""."""
    teile = _sicher(lambda: modell_teile(model, analyse)) or []
    return BETROFFEN + ": " + "; ".join(teile) if teile else ""


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
            wo = _sicher(lambda: mk.im_ergebnis(model, analyse)) if analyse is not None else None
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
        if mk.import_korrektur and not mk.modellgrund and _sicher(lambda: mk.betrifft(model)):
            wo = (_sicher(lambda: mk.im_ergebnis(model, analyse))
                  if (mk.im_ergebnis is not None and analyse is not None) else None)
            if wo == "":
                continue
            w = mk.wechsel[-1]
            grund = f"Modell vor dem {w.datum} aus RFEM übernommen"
            betr.append(f"{mk.titel}: {grund} ({mk.text('alt')}"
                        + (f"; {wo}" if wo else "") + f") – {mk.vorschlag}, danach neu rechnen")
    betr += _sicher(lambda: modell_teile(model, analyse)) or []
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
