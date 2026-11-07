"""Mit welcher Einstellung ist das Netz entstanden? (16.10.2026)

Die Netzeinstellungen (Maske „Netzeinstellungen“, ``Model.netz``) wirken erst,
wenn vernetzt wird. Wer „Mittel“ (tet10) uebernimmt und gleich rechnet, rechnet
mit dem alten tet4-Netz des Entwurfs - und sah bisher keinen Hinweis, der
Anwender am 16.10.2026 ebensowenig: „Netzeinstellung wirksam erst nach
Vernetzen“.

Darum merkt sich das Modell beim Vernetzen die Einstellung, mit der das Netz
entstand (``Netzeinstellungen.vernetzt_mit``; Vorgabe leer, steht nur in der
Datei, wenn gesetzt - model.NEUE_FELDER). Weicht die aktuelle Einstellung ab,
nennt :func:`hinweis` den Unterschied beim Uebernehmen und beim Rechenstart.
Gesperrt wird nichts. :func:`ausweis` liefert fuer Bericht und Ergebnisdatei
die Elementtypen mit Anzahl und die Einstellung beim Vernetzen.

Ein Netz ohne Vermerk (Datei von davor, Import, von Hand gebaut) bleibt ohne
Hinweis: es gibt nichts zu vergleichen. Aendert der Anwender die Einstellung
an einem solchen Netz, gilt die **bisherige** Einstellung als die des Netzes
(:func:`vor_aenderung`) - das ist die einzige Annahme, die sich vertreten laesst.
"""
from __future__ import annotations


def _wert(netz, feld):
    """Wert eines Feldes, so wie er verglichen und gezeigt wird."""
    from . import elementstufe as es
    if feld == "elemente":
        return es.NAME[es.stufe(netz)]
    v = getattr(netz, feld, None)
    if isinstance(v, float):
        return round(v * 1e3, 3) if feld in ("ziellaenge", "h_min", "h_max") else round(v, 6)
    return v


#: (Feld, Wort in der Meldung, nur gueltig wenn ...) - die Angaben, die das Netz
#: bestimmen. Die Ziellaenge zaehlt nur bei der eigenen Dichte, h_min/h_max nur
#: bei intelligenter Anpassung.
FELDER = (
    ("elemente", "Elemente", None),
    ("dichte", "Netzdichte", None),
    ("ziellaenge", "Ziellänge [mm]", lambda n: str(getattr(n, "dichte", "")) == "eigene"),
    ("intelligent", "intelligente Anpassung", None),
    ("h_min", "kleinste Kantenlänge [mm]", lambda n: bool(getattr(n, "intelligent", True))),
    ("h_max", "größte Kantenlänge [mm]", lambda n: bool(getattr(n, "intelligent", True))),
    ("form", "Elementform", None),
    ("abgebildet", "abgebildetes Netz", None),
    ("vernetzer", "Vernetzer", None),
    ("nachbessern", "Nachbesserung", None),
    ("krafteinleitung_fein", "Krafteinleitungen feiner", None),
    ("krafteinleitung_stabenden", "Stabenden feiner", None),
)


def _zeigen(v) -> str:
    if isinstance(v, bool):
        return "an" if v else "aus"
    if isinstance(v, float):
        return f"{v:g}".replace(".", ",")
    return str(v)


def netzstand(netz) -> dict:
    """Die Einstellung, so wie sie im Modell vermerkt wird (JSON-faehig)."""
    d = {feld: _wert(netz, feld) for feld, _w, _g in FELDER}
    d["beschreibung"] = netz.beschreibung()
    return d


def merken(model) -> dict:
    """Die aktuelle Einstellung als die des Netzes vermerken - nach dem Vernetzen."""
    # An Ort und Stelle: die adaptive Vernetzung und die Oberflaeche halten das
    # Netzeinstellungen-Objekt und lesen es nach dem Vernetzen noch einmal
    # (tests.test_netzfehler); ein neues Objekt braeche diesen Bezug.
    model.netz.vernetzt_mit = netzstand(model.netz)
    return model.netz.vernetzt_mit


def vor_aenderung(model, neu=None) -> None:
    """Vor dem Uebernehmen neuer Einstellungen: hat das Netz keinen Vermerk, aber
    Elemente, gilt die bisherige Einstellung als die, mit der es entstand."""
    if model.elements and not getattr(model.netz, "vernetzt_mit", None):
        merken(model)


def abweichungen(model) -> list:
    """Zeilen „Elemente Mittel statt Entwurf“: was die aktuelle Einstellung vom
    Vermerk des Netzes unterscheidet. Leer ohne Netz, ohne Vermerk und ohne
    Unterschied."""
    vm = getattr(model.netz, "vernetzt_mit", None) or {}
    if not model.elements or not vm:
        return []
    aus = []
    for feld, wort, gilt in FELDER:
        if gilt is not None and not gilt(model.netz):
            continue
        if feld not in vm:
            continue
        jetzt, damals = _wert(model.netz, feld), vm[feld]
        if jetzt != damals:
            aus.append(f"{wort} {_zeigen(jetzt)} statt {_zeigen(damals)}")
    return aus


def hinweis(model, wann: str = "rechnen") -> str:
    """Der Hinweis, wenn die Einstellung vom vorhandenen Netz abweicht, sonst "".

    ``wann``: "uebernehmen" (Maske Netzeinstellungen) oder "rechnen" (Rechenstart).
    Der Text sperrt nichts - er sagt, womit gerechnet wird und wie das Netz die
    neue Einstellung bekommt."""
    a = abweichungen(model)
    if not a:
        return ""
    vm = model.netz.vernetzt_mit
    return ("Hinweis: Die Netzeinstellung wirkt erst nach dem Vernetzen. "
            + ("Gerechnet wird mit dem vorhandenen Netz" if wann == "rechnen"
               else "Das vorhandene Netz bleibt, wie es ist")
            + f" (entstanden mit: {vm.get('beschreibung', '')}). Eingestellt ist jetzt: "
              f"{'; '.join(a)}. Netz → Vernetzen wendet die Einstellung an.")


def ausweis(model) -> dict:
    """Fuer Bericht und Ergebnisdatei: {"gesamt", "elementtypen": {typ: n},
    "netzeinstellung": Text der Einstellung beim Vernetzen ("" wenn nicht
    bekannt), "abweichend": [Zeilen]}."""
    from . import elementauswahl as ea
    z = ea.typen_zaehlen(model)
    vm = getattr(model.netz, "vernetzt_mit", None) or {}
    return {"gesamt": int(z["gesamt"]), "elementtypen": {t: int(n) for t, n in z["typen"].items()},
            "netzeinstellung": str(vm.get("beschreibung", "") or ""),
            "abweichend": abweichungen(model)}


def ausweis_text(a: dict) -> str:
    """Der Satz zum Ausweis: Typen mit Anzahl und die Einstellung beim Vernetzen."""
    from .elemente import ELEMENTE
    from .zahlen import zahl_text
    teile = [f"{zahl_text(n)} {t}" for t, n in a.get("elementtypen", {}).items()]
    ein = a.get("netzeinstellung") or ""
    return (f"Elemente ({zahl_text(a.get('gesamt', 0))}): " + (", ".join(teile) or "keine")
            + ". Netzeinstellung beim Vernetzen: "
            + (ein if ein else "nicht bekannt (Netz ohne Vermerk, etwa aus einer Datei vor dem "
                               "16.10.2026 oder importiert)") + ".")


def ausweis_zeile(model) -> str:
    return ausweis_text(ausweis(model))
