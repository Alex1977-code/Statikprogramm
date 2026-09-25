"""
Elementstufe: Entwurf, Mittel oder Fein (25.09.2026).

Der Anwender am 25.09.2026, nach den Haken der Elementwahl (Paket E): „was
hältst du von presets für die zu verwendenen elemente. zb entwurf tet4 etc
dann mittel tet10 und fein hex 20 plus die entsprechenden weiteren elemente
die in genauigkeit und rechenzeit zusammenpassen. das vq83 auch dort
einordnen wo es hingehört“ - „keep it simple“, „viel zu fummelig“. Ein
Auswahlfeld „Elemente“ in den Netzeinstellungen ersetzt darum den
Elementansatz linear/quadratisch und die Haken:

* **Entwurf** - tet4, Sechsflaechner hex8 (VQ83: entartete rechnen als
  Keil, Pyramide oder Tetraeder), Schalen linear.
* **Mittel** (Vorgabe) - tet10, Sechsflaechner hex20 (VQ203), Schalen
  quadratisch.
* **Fein** - wie Mittel mit halber Kantenlaenge. Ohne tetp (Anwender
  25.09.2026: „Fein ohne tetp“).

Jede Stufe setzt ``netz.sweep = "sauber"``: „sweepen muss das programm doch
automatisch wenn das entsprechende element das verlangt … dass kann der user
doch nicht wissen“. „Sauber“ (Vernetzer-Sitzung, sweep.betriebsart) sweept
nur Koerper, deren jedes Element sauber wird, sonst Tetraeder. Welche
Elemente wirklich entstanden sind, zeigt danach die Elementuebersicht.

**Kontakt sperrt Mittel und Fein - an einer Stelle.** Kontakt, Fugen und
Flaechenlager nehmen von einer Elementseite heute nur die Eckknoten;
an quadratischen Elementen bricht die Rechnung darum laut ab
(fugen.QuadratischeSeiten). Der Anwender: „kontakt und plastizität muss in
allen stufen funktionieren“ - und nicht still herabstufen. Solange die
Loeser-Sitzung den Kontakt fuer quadratische Seiten nicht geliefert hat,
sind Mittel und Fein an solchen Modellen sichtbar, aber gesperrt, und das
Modell steht mit Hinweis in Maske und Protokoll auf Entwurf. Die Sperre
haengt allein an :func:`quadratisch_gesperrt`; mit der Lieferung gibt sie
eine leere Liste zurueck, und alles andere bleibt.

Die Plastizitaet rechnet mit tet4, tet10, hex8, hex20, pent6, pent15 und
pyr5 (plastizitaet.py) - also in jeder Stufe; ihr Haken bleibt, wie er ist.

Gespeichert wird die Stufe in ``Netzeinstellungen.stufe`` (optional, leer =
aus der Ordnung: 1 Entwurf, 2 Mittel). Die Ordnung bleibt das Feld, das der
Vernetzer liest; widersprechen sich beide (etwa weil Code die Ordnung direkt
setzt), gilt die Ordnung.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

#: Die Stufen in der Reihenfolge der Auswahl
STUFEN = ("entwurf", "mittel", "fein")
#: Statik3D-Vorgabe (Anwender 23.09.2026: „standard sollte tet10 und vq83 sein“)
VORGABE = "mittel"
#: Name der Stufe
NAME = {"entwurf": "Entwurf", "mittel": "Mittel", "fein": "Fein"}
#: Eintrag im Auswahlfeld
AUSWAHL = {"entwurf": "Entwurf", "mittel": "Mittel (Vorgabe)", "fein": "Fein"}
#: Elementordnung der Stufe (Netzeinstellungen.ordnung, die der Vernetzer liest)
ORDNUNG = {"entwurf": 1, "mittel": 2, "fein": 2}
#: Welche Elemente die Stufe erzeugt
ELEMENTE = {
    "entwurf": "tet4, Sechsflächner hex8 (VQ83; entartete rechnen als Keil, Pyramide oder "
               "Tetraeder), Schalen linear (shell3/shell4)",
    "mittel": "tet10, Sechsflächner hex20 (VQ203; entartete als pent15 oder tet10), "
              "Schalen quadratisch (shell6/shell8)",
    "fein": "wie Mittel (tet10, hex20 (VQ203), Schalen quadratisch) mit halber Kantenlänge",
}
#: Wofuer die Stufe taugt (Anwender-Auftrag 25.09.2026, woertlich)
ZWECK = {
    "entwurf": "schnell; für Vorbemessung und Verformungen – Spannungen fallen zu niedrig aus",
    "mittel": "für die Nachweise",
    "fein": "für Bohrungen, Kerben und Ermüdung",
}
#: Sweep-Betriebsart, die jede Stufe setzt (Sechsflaechner nur, wo sauber)
SWEEP = "sauber"
#: Hinweis an gesperrten Stufen (woertlich aus dem Auftrag)
SPERRHINWEIS = "mit Kontakt noch nicht verfügbar – Kontakt für quadratische Elemente folgt"
#: Fein halbiert die Kantenlaenge
FEIN_FAKTOR = 0.5
#: Bis zu so vielen Objekten nennt die Maske die Kantenlaenge je Objekt
#: (gemessen 25.09.2026: 300 Wuerfel 0,48 s; am Drehlager nicht gemessen)
KANTEN_OBJEKTE = 300


def aus_text(text) -> str | None:
    """Die Stufe zu einem Eintrag des Auswahlfeldes (oder ihrem Namen)."""
    t = str(text or "").strip().lower()
    for s in STUFEN:
        if t == s or t == AUSWAHL[s].lower() or t.startswith(NAME[s].lower()):
            return s
    return None


def stufe(netz) -> str:
    """Die Stufe dieser Netzeinstellungen.

    ``netz.stufe`` gilt, wenn sie zur Ordnung passt; sonst (aeltere Datei
    ohne Stufe, unbekanntes Wort, Ordnung von Hand gesetzt) folgt sie der
    Ordnung: 1 Entwurf, 2 Mittel."""
    ordnung = int(getattr(netz, "ordnung", 1) or 1)
    s = str(getattr(netz, "stufe", "") or "").strip().lower()
    if s in STUFEN and ORDNUNG[s] == min(ordnung, 2):
        return s
    return "mittel" if ordnung >= 2 else "entwurf"


def setzen(netz, s: str):
    """Netzeinstellungen mit der Stufe ``s``: Ordnung, Sweep „sauber“ und die
    Stufe selbst; alles andere bleibt. Die Eingabe bleibt unveraendert."""
    s = str(s or "").strip().lower()
    if s not in STUFEN:
        raise ValueError(f"Unbekannte Elementstufe {s!r} - Entwurf, Mittel oder Fein")
    return replace(netz, stufe=s, ordnung=ORDNUNG[s], sweep=SWEEP)


# --------------------------------------------------------------------------
# Die Sperre (eine Stelle)
# --------------------------------------------------------------------------
def quadratisch_gesperrt(model) -> list:
    """Was quadratische Elemente heute sperrt - leer, wenn nichts.

    Kontaktbedingungen (ausser abgeschalteten und verschweissten an
    gemeinsamen Flaechen, die nichts trennen), Kontaktpaare und
    Flaechenlager: sie nehmen von einer Elementseite nur die Eckknoten, und
    an tet10/hex20/shell8 bricht die Rechnung darum laut ab
    (fugen.QuadratischeSeiten). Zurueckgegeben werden die Objekte mit
    Namen, damit Maske und Protokoll sagen koennen, woran es liegt.

    **Die eine Stelle** (25.09.2026): liefert die Loeser-Sitzung den Kontakt
    fuer quadratische Seiten, gibt diese Funktion eine leere Liste zurueck
    (bzw. nur noch das, was dann noch sperrt) - Maske, Vernetzen und Import
    fragen nur hier."""
    from .kontakte import ist_verschweisst
    gruende = []
    for kb in (getattr(model, "kontaktbedingungen", None) or {}).values():
        if getattr(kb, "aus", False) or ist_verschweisst(model, kb):
            continue
        gruende.append(f"Kontaktbedingung {kb.name}")
    for cp in (getattr(model, "contact_pairs", None) or []):
        gruende.append(f"Kontaktpaar {cp.name}")
    for ss in (getattr(model, "surface_supports", None) or []):
        gruende.append(f"Flächenlager {ss.name}")
    return gruende


def frei(model, s: str, gruende: list = None) -> bool:
    """Ob die Stufe ``s`` an diesem Modell waehlbar ist."""
    if ORDNUNG.get(s, 1) < 2:
        return True
    return not (quadratisch_gesperrt(model) if gruende is None else gruende)


def wirksame_stufe(model, gruende: list = None) -> str:
    """Die Stufe, mit der vernetzt wird: die eingestellte, an einem
    gesperrten Modell Entwurf."""
    s = stufe(model.netz)
    return s if frei(model, s, gruende) else "entwurf"


def gruende_text(gruende: list, hoechstens: int = 3) -> str:
    teile = list(gruende[:hoechstens])
    if len(gruende) > hoechstens:
        teile.append(f"und {len(gruende) - hoechstens} weitere")
    return ", ".join(teile)


def sperrtext(gruende: list) -> str:
    """Der Hinweis in der Maske: Hinweis, Grund und was stattdessen gilt."""
    return (f"Mittel und Fein: {SPERRHINWEIS} ({gruende_text(gruende)}). "
            "Dieses Modell wird mit Entwurf vernetzt.")


def sperre_anwenden(model) -> str:
    """Steht ein gesperrtes Modell auf Mittel oder Fein, wird es Entwurf -
    nie still: die Rueckgabe ist die Zeile fuer das Protokoll (leer, wenn
    nichts zu tun war)."""
    gruende = quadratisch_gesperrt(model)
    s = stufe(model.netz)
    if frei(model, s, gruende):
        return ""
    model.netz = setzen(model.netz, "entwurf")
    return (f"Elemente: Entwurf statt {NAME[s]} – {NAME[s]} ist {SPERRHINWEIS} "
            f"({gruende_text(gruende)}). Vernetzt wird mit tet4/hex8; die Stufe steht jetzt auf Entwurf.")


# --------------------------------------------------------------------------
# Fein: halbe Kantenlaenge
# --------------------------------------------------------------------------
def _halb(x):
    return float(x) * FEIN_FAKTOR if x else x


def wirksam(netz, model=None):
    """Die Netzeinstellungen, mit denen vernetzt wird.

    Entwurf und Mittel: ``netz`` selbst. Fein: eine Kopie mit halber
    Kantenlaenge - die Netzdichte eine Stufe feiner (grob 8 → mittel 16 →
    fein 32 Elemente ueber die Objektgroesse, netzdichte.DICHTEN), die
    Ziellaenge, die kleinste und groesste Elementgroesse, die Kantenlaenge je
    Koerper, die Netzverfeinerungen und die Feldpunkte halb. Steht die
    Netzdichte schon auf fein, gibt es keine feinere Stufe: dann bekommt
    jeder Koerper die Haelfte seiner Dichte-Laenge als eigene Kantenlaenge
    (dafuer braucht es ``model``); Flaechen mit Dicke bleiben dort bei der
    Dichte fein. Die Hoechstzahl Elemente je Objekt bleibt - sie ist ein
    Schutz, keine Kantenlaenge. Gespeichert wird davon nichts: die Maske
    zeigt die Einstellung fuer Mittel und daneben die wirksame Laenge."""
    if stufe(netz) != "fein":
        return netz
    from . import netzdichte as nd
    dichte = getattr(netz, "dichte", "mittel") or "mittel"
    koerper_h = {k: _halb(v) for k, v in (getattr(netz, "koerper_h", None) or {}).items()}
    if dichte in nd.DICHTEN:
        feiner = next((d for d, n in nd.DICHTEN.items() if n * FEIN_FAKTOR == nd.DICHTEN[dichte]), None)
        if feiner is not None:
            dichte = feiner
        elif model is not None:
            for k in (getattr(model, "koerper", None) or {}).values():
                if k.name in koerper_h:
                    continue
                D = nd.objektgroesse(model, k)
                if D > 0:
                    koerper_h[k.name] = D / nd.DICHTEN[dichte] * FEIN_FAKTOR
    verfeinerungen = []
    for v in (getattr(netz, "verfeinerungen", None) or []):
        v = dict(v)
        if v.get("h"):
            v["h"] = _halb(v["h"])
        verfeinerungen.append(v)
    feldpunkte = []
    for p in (getattr(netz, "feldpunkte", None) or []):
        p = list(p)
        if len(p) >= 4:
            p[3] = _halb(p[3])
        feldpunkte.append(p)
    return replace(netz, dichte=dichte, ziellaenge=_halb(netz.ziellaenge),
                   h_min=_halb(getattr(netz, "h_min", 0.0)), h_max=_halb(getattr(netz, "h_max", 0.0)),
                   koerper_h=koerper_h, verfeinerungen=verfeinerungen, feldpunkte=feldpunkte)


def _mm(x: float) -> str:
    from .zahlen import zahl_text
    v = float(x) * 1e3
    return zahl_text(round(v, 1 if v < 100 else 0)) + " mm"


def kantenlaenge_text(netz, model=None) -> str:
    """Die wirksame Kantenlaenge fuer die Maske.

    Mit Modell (bis KANTEN_OBJEKTE Objekte): die Kantenlaenge im Feld, wie
    sie der Vernetzer je Koerper bzw. Flaeche mit Dicke nimmt
    (netzdichte.elementlaenge) - kleinste bis groesste. Sonst die Regel
    (Netzdichte oder Ziellaenge). Bei Fein steht dabei, wovon es die Haelfte
    ist."""
    from . import netzdichte as nd
    w = wirksam(netz, model)
    fein = w is not netz
    dichte = getattr(w, "dichte", "mittel") or "mittel"
    if dichte in nd.DICHTEN:
        regel = f"Netzdichte {dichte}: {nd.DICHTEN[dichte]} Elemente über die Objektgröße"
    else:
        regel = f"Ziellänge {_mm(w.ziellaenge)}"
    if fein:
        d0 = getattr(netz, "dichte", "mittel") or "mittel"
        regel += (" (halbe Kantenlänge von "
                  + (f"Netzdichte {d0}" if d0 in nd.DICHTEN else f"{_mm(netz.ziellaenge)}") + ")")
    if model is None:
        return regel
    objekte = list((getattr(model, "koerper", None) or {}).values())
    objekte += [f for f in (getattr(model, "flaechen", None) or {}).values() if getattr(f, "dicke", None)]
    if not objekte or len(objekte) > KANTEN_OBJEKTE:
        return regel
    try:
        hs = [float(nd.elementlaenge(model, w, o)["h"]) for o in objekte]
    except Exception:                      # noqa: BLE001 - dann nur die Regel
        return regel
    hs = [h for h in hs if h > 0]
    if not hs:
        return regel
    was = f"{len(objekte)} Objekt{'e' if len(objekte) != 1 else ''}"
    feld = (_mm(min(hs)) if abs(max(hs) - min(hs)) < 1e-12 else f"{_mm(min(hs))} … {_mm(max(hs))}")
    return f"{feld} im Feld ({was}); {regel}"


@contextmanager
def beim_vernetzen(model, log: list):
    """Vernetzen mit der Stufe: erst die Sperre (Mittel/Fein an einem
    gesperrten Modell -> Entwurf, mit Zeile im Protokoll), dann bei Fein die
    halbe Kantenlaenge fuer die Dauer des Vernetzens. Danach stehen die
    gespeicherten Netzeinstellungen wieder da - ausser der Stufe, die die
    Sperre gesetzt hat."""
    zeile = sperre_anwenden(model)
    if zeile:
        log.append(zeile)
    gespeichert = model.netz
    w = wirksam(gespeichert, model)
    teilungen: dict = {}
    if w is not gespeichert:
        log.append("Elemente Fein: vernetzt mit halber Kantenlänge – " + kantenlaenge_text(gespeichert))
        # Abgebildete Sechsflaechner nehmen ihre Teilung aus dem Koerper
        # (Volumenkoerper.teilung, Vorgabe 4 x 4 x 4), nicht aus der
        # Netzdichte; eine Flaeche mit eigener Teilung ebenso, wenn die
        # Netzdichte sie nicht uebersteuert. Halbe Kantenlaenge heisst dort
        # doppelte Teilung - fuer die Dauer des Vernetzens (gemessen am
        # Wuerfel 1 m, Teilung 2: Mittel 8 hex20, Fein 64; 25.09.2026).
        for obj in list((getattr(model, "koerper", None) or {}).values()) \
                + list((getattr(model, "flaechen", None) or {}).values()):
            t = list(getattr(obj, "teilung", None) or [])
            if t:
                teilungen[id(obj)] = (obj, t)
                obj.teilung = [max(1, int(x)) * 2 for x in t]
    model.netz = w
    try:
        yield w
    finally:
        if model.netz is w:
            model.netz = gespeichert
        for obj, t in teilungen.values():
            obj.teilung = t
