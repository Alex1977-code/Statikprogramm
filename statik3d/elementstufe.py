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
* **Fein** - wie Mittel, feiner nur dort, wo es zaehlt (seit 07.10.2026,
  Paket F1): an Kontakt-, Lager- und Lastflaechen die halbe Kantenlaenge,
  an den Boegen der Kontakt- und Lagerflaechen 9 statt 18 Grad je
  Abschnitt, von dort mit 0,35 je m wachsend ins Feld von Mittel
  (:func:`wirksam`, netzfeld.fein_ziele). Bis zum 07.10.2026 halbierte
  Fein jede Kantenlaenge im ganzen Modell und liess die Bohrungen, wie sie
  waren. Ohne tetp (Anwender 25.09.2026: „Fein ohne tetp“).

Jede Stufe setzt ``netz.sweep = "sauber"``: „sweepen muss das programm doch
automatisch wenn das entsprechende element das verlangt … dass kann der user
doch nicht wissen“. „Sauber“ (Vernetzer-Sitzung, sweep.betriebsart) sweept
nur Koerper, deren jedes Element sauber wird, sonst Tetraeder. Welche
Elemente wirklich entstanden sind, zeigt danach die Elementuebersicht.

**Was Mittel und Fein noch sperrt - an einer Stelle.** Kontakt, Fugen und
Flaechenlager nehmen von einer Elementseite nur die Eckknoten. Seit dem
08.10.2026 (Paket Q1) sind an tet10, hex20 und pent15 die Seitenmitten jeder
Kontakt- und Lagerseite an ihre Ecken gebunden (assemble.mittelknoten_bindungen);
Kontaktpaare, Kontaktbedingungen (die Fuge trennt seit Paket Q2 auch die
Seitenmitten, fugen.SEITENMITTEN_GETRENNT) und Flaechenlager rechnen an Volumen
in jeder Stufe. Gesperrt bleiben quadratische **Schalen** an Kontakt oder
Flaechenlager (die Bindung wirkt nur in Volumen, Entscheidung E3 des
Bauplans). Der Anwender: „kontakt und plastizität
muss in allen stufen funktionieren“ - und nicht still herabstufen. An einem
gesperrten Modell sind Mittel und Fein sichtbar, aber gesperrt, und das
Modell steht mit Hinweis in Maske und Protokoll auf Entwurf. Die Sperre
haengt allein an :func:`quadratisch_gesperrt`. Bis zum 08.10.2026 sperrte
jede Kontaktbedingung, jedes Kontaktpaar und jedes Flaechenlager.

Die Plastizitaet rechnet mit tet4, tet10, hex8, hex20, pent6, pent15 und
pyr5 (plastizitaet.py) - also in jeder Stufe; ihr Haken bleibt, wie er ist.

Gespeichert wird die Stufe in ``Netzeinstellungen.stufe`` (optional, leer =
aus der Ordnung: 1 Entwurf, 2 Mittel). Die Ordnung bleibt das Feld, das der
Vernetzer liest; widersprechen sich beide (etwa weil Code die Ordnung direkt
setzt), gilt die Ordnung.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace

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
    "fein": "wie Mittel (tet10, hex20 (VQ203), Schalen quadratisch), feiner an Kontakt-, Lager- und "
            "Lastflächen und an den Bögen der Kontakt- und Lagerflächen",
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
#: Die Stufen von Fein (Paket F1, 07.10.2026): (Bogenwinkel je Abschnitt an
#: den Boegen der Kontakt- und Lagerflaechen [Grad], Kantenlaenge an Kontakt-,
#: Lager- und Lastflaechen als Anteil von Mittel). k = 0 ist Fein; wird das
#: Netz zu gross, vergroebert das Paket F2 Stufe um Stufe - erst die Boegen
#: (9 -> 12 -> 18 Grad, 18 ist Mittel), dann die Flaechen (h/2 -> h/1,5 -> h).
#: Die letzte Stufe ist Mittel. Siehe :func:`fein_stufe`.
FEIN_STUFEN = ((9.0, 0.5), (12.0, 0.5), (18.0, 0.5), (18.0, 1.0 / 1.5), (18.0, 1.0))
FEIN_STUFEN_ANZAHL = len(FEIN_STUFEN)
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

    Seit dem 08.10.2026 (Paket Q1) nur noch zweierlei: Kontaktbedingungen,
    Kontaktpaare und Flaechenlager an **Schalen** (Flaechen mit Dicke bzw.
    Schalenelemente) - die Bindung der Seitenmitten wirkt nur in Volumen,
    an shell6/shell8 bricht die Rechnung laut ab (fugen.QuadratischeSeiten).
    Trennende Kontaktbedingungen an Volumen sperren nur, solange das Trennen
    einer Fuge die Seitenmitten nicht mittrennt (fugen.SEITENMITTEN_GETRENNT;
    seit Paket Q2 tut es das). Kontaktbedingungen, Kontaktpaare und
    Flaechenlager an tet10, hex20 und pent15 sperren nicht mehr. Zurueckgegeben werden die Objekte mit
    Namen, damit Maske und Protokoll sagen koennen, woran es liegt.

    **Die eine Stelle** (25.09.2026) - Maske, Vernetzen und Import fragen nur
    hier. Bis zum 08.10.2026 sperrte jede Kontaktbedingung, jedes
    Kontaktpaar und jedes Flaechenlager."""
    from .kontakte import ist_verschweisst
    from .fugen import SEITENMITTEN_GETRENNT
    schalen = _schalen_an(model)
    gruende = []
    for kb in (getattr(model, "kontaktbedingungen", None) or {}).values():
        if getattr(kb, "aus", False) or ist_verschweisst(model, kb):
            continue
        if schalen(flaechen=list(kb.flaechennamen or []) + list(kb.gegenflaechen or [])):
            gruende.append(f"Kontaktbedingung {kb.name} (an Schalen)")
        elif not SEITENMITTEN_GETRENNT:
            gruende.append(f"Kontaktbedingung {kb.name}")
    for cp in (getattr(model, "contact_pairs", None) or []):
        if schalen(elemente=cp.master_elements,
                   knoten=list(cp.slave_nodes or []) + [n for f in (cp.master_faces or []) for n in f]):
            gruende.append(f"Kontaktpaar {cp.name} (an Schalen)")
    for ss in (getattr(model, "surface_supports", None) or []):
        if schalen(flaechen=getattr(ss, "flaechen", None) or [], elemente=ss.elements,
                   knoten=ss.nodes):
            gruende.append(f"Flächenlager {ss.name} (an Schalen)")
    return gruende


def _schalen_an(model):
    """f(flaechen=, elemente=, knoten=) -> bool: liegt das Objekt an einer
    Schale - eine genannte Flaeche traegt als Schale (Model.flaeche_traegt),
    ein genanntes Element ist eine Schale, oder ein genannter Knoten haengt an
    einer? Die Schalenknoten werden nur gesammelt, wenn es Schalen gibt."""
    from . import elemente as EL
    schalentypen = set(EL.SCHALEN_TYPEN)
    traegt = getattr(model, "flaeche_traegt", None)
    els = getattr(model, "elements", None) or []
    knoten_s = None

    def an(flaechen=(), elemente=(), knoten=()):
        nonlocal knoten_s
        if traegt is not None and any(traegt(str(f)) for f in (flaechen or [])):
            return True
        if any(0 <= int(i) < len(els) and els[int(i)].typ in schalentypen for i in (elemente or [])):
            return True
        if not knoten:
            return False
        if knoten_s is None:
            knoten_s = {int(n) for e in els if e.typ in schalentypen for n in e.nodes}
        return bool(knoten_s) and any(int(n) in knoten_s for n in knoten)
    return an


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
# Fein: Mittel plus Quellen an Kontakt, Lagern, Lasten und Boegen (F1)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FeinStufe:
    """Eine Vergroeberungsstufe von Fein (:data:`FEIN_STUFEN`)."""
    #: Nummer der Stufe, 0 = Fein
    k: int
    #: Bogenwinkel je Abschnitt an den Boegen der Kontakt- und Lagerflaechen [Grad]
    bogenwinkel: float
    #: Kantenlaenge an Kontakt-, Lager- und Lastflaechen als Anteil von Mittel
    flaechenfaktor: float

    @property
    def letzte(self) -> bool:
        """Die letzte Stufe - groeber geht es nicht."""
        return self.k >= FEIN_STUFEN_ANZAHL - 1

    @property
    def ist_mittel(self) -> bool:
        """Verfeinert diese Stufe nichts mehr (Boegen 18 Grad, Flaechen h)?"""
        from .mesher3d import BOGENWINKEL
        return self.bogenwinkel >= BOGENWINKEL and self.flaechenfaktor >= 1.0


def fein_stufe(k: int = 0) -> FeinStufe:
    """**Schnittstelle fuer das Paket F2** (selbsttaetig groeber vernetzen,
    Anwender 07.10.2026): die Fein-Einstellungen in der Vergroeberungsstufe k.

    * k = 0 ist Fein: an den Boegen der Kontakt- und Lagerflaechen 9 Grad je
      Abschnitt, an Kontakt-, Lager- und Lastflaechen die halbe Kantenlaenge
      von Mittel (eine Elementlage, von dort mit 0,35 je m wachsend).
    * Hoehere Stufen werden zuerst an den Boegen groeber - k = 1: 12 Grad,
      k = 2: 18 Grad, also wie Mittel -, dann an den Flaechen - k = 3:
      h/1,5, k = 4: h.
    * Die letzte Stufe (k = FEIN_STUFEN_ANZAHL - 1 = 4) ist Mittel
      (``letzte`` und ``ist_mittel`` sind wahr): keine Quellen, keine
      verdoppelte Teilung abgebildeter Koerper, das Netz ist bitgleich das
      von Mittel (tests/test_fein_smart.py). Ein groesseres k gibt die
      letzte Stufe, ein negatives Stufe 0.

    So vernetzt F2 eine Stufe - und wenn das Netz die Grenze ueberschreitet,
    dieselbe mit k + 1, bis ``fein_stufe(k).letzte``::

        with elementstufe.beim_vernetzen(model, log, k=k):
            mesher.modell_vernetzen(model, log)

    Die Netzeinstellungen einer Stufe allein gibt ``wirksam(netz, model,
    k=k)``, den Text fuer Maske und Protokoll ``fein_text(netz, model, k)``.
    """
    k = min(max(int(k or 0), 0), FEIN_STUFEN_ANZAHL - 1)
    w, f = FEIN_STUFEN[k]
    return FeinStufe(k, float(w), float(f))


def _fein(netz, model, k: int) -> tuple:
    """(Netzeinstellungen fuer die Dauer des Vernetzens, Ziele) von Fein in
    der Stufe k - die Ziele (netzfeld.fein_ziele) None ohne Modell oder in
    der Stufe Mittel."""
    st = fein_stufe(k)
    ziele, zusatz = None, []
    if model is not None and not st.ist_mittel:
        from . import netzfeld
        ziele = netzfeld.fein_ziele(model, netz, st.bogenwinkel, st.flaechenfaktor)
        zusatz = netzfeld.fein_verfeinerungen(ziele)
    return replace(netz, verfeinerungen=list(getattr(netz, "verfeinerungen", None) or []) + zusatz), ziele


def wirksam(netz, model=None, k: int = 0):
    """Die Netzeinstellungen, mit denen vernetzt wird.

    Entwurf und Mittel: ``netz`` selbst. Fein (seit 07.10.2026, Paket F1):
    eine Kopie mit **denselben Laengen wie Mittel** - Netzdichte,
    Ziellaenge, kleinste und groesste Elementgroesse, Kantenlaenge je
    Koerper, Netzverfeinerungen und Feldpunkte des Anwenders bleiben und
    wirken wie bei Mittel -, dazu in ``verfeinerungen`` die Quellen von Fein
    in der Vergroeberungsstufe ``k`` (:func:`fein_stufe`): halbe
    Kantenlaenge an Kontakt-, Lager- und Lastflaechen, 9 Grad je Abschnitt
    an den Boegen der Kontakt- und Lagerflaechen (netzfeld.fein_ziele). Ohne
    ``model`` gibt es keine Quellen. Gespeichert wird davon nichts.

    Bis zum 07.10.2026 halbierte Fein hier jede Laenge des ganzen Modells
    (Netzdichte, Ziellaenge, h_min/h_max, Kantenlaenge je Koerper,
    Verfeinerungen, Feldpunkte), aber nicht den Bogenwinkel: am Drehlager
    wurde damit das Innere der grossen Teile feiner, die Bohrungen blieben,
    wie sie waren (Bauplan PLAN-FEIN-SMART-2026-10-07)."""
    if stufe(netz) != "fein":
        return netz
    return _fein(netz, model, k)[0]


def _mm(x: float) -> str:
    from .zahlen import zahl_text
    v = float(x) * 1e3
    return zahl_text(round(v, 1 if v < 100 else 0)) + " mm"


def _spanne(werte) -> str:
    werte = [float(x) for x in werte]
    lo, hi = min(werte), max(werte)
    return _mm(lo) if abs(hi - lo) <= 1e-9 * max(hi, 1e-12) else f"{_mm(lo)} … {_mm(hi)}"


def _anzahl(n: int, eins: str, mehr: str) -> str:
    return f"{n} {eins if n == 1 else mehr}"


def fein_text(netz, model=None, k: int = 0, ziele: dict = None) -> str:
    """Was Fein in der Stufe k verfeinert - fuer die Maske (wirksame
    Kantenlaenge) und das Protokoll beim Vernetzen. Mit Modell mit Zahl und
    Art der Flaechen, ihrer Kantenlaenge gegen Mittel und der Zahl der
    Boegen; ohne Modell die Regel."""
    from .mesher3d import BOGENWINKEL
    st = fein_stufe(k)
    if st.ist_mittel:
        return "wie Mittel (letzte Vergröberungsstufe: keine Verfeinerung)"
    if abs(st.flaechenfaktor - 0.5) < 1e-9:
        anteil = "die Hälfte"
    else:
        anteil = f"das {st.flaechenfaktor:.2f}-Fache".replace(".", ",")
    boegen_regel = (f"{st.bogenwinkel:g}° statt {BOGENWINKEL:g}° je Abschnitt" if st.bogenwinkel < BOGENWINKEL
                    else f"Bögen wie Mittel ({BOGENWINKEL:g}° je Abschnitt)")
    if model is None:
        return (f"wie Mittel, feiner an Kontakt-, Lager- und Lastflächen ({anteil} der Kantenlänge) und an den "
                f"Bögen der Kontakt- und Lagerflächen ({boegen_regel})")
    if ziele is None:
        from . import netzfeld
        ziele = netzfeld.fein_ziele(model, netz, st.bogenwinkel, st.flaechenfaktor)
    fl = [fn for fn in ziele["flaechen"] if fn in ziele["h"]]
    if not fl:
        return "wie Mittel – an diesem Modell keine Kontakt-, Lager- oder Lastflächen"
    arten = []
    for art in ("Kontakt", "Lager", "Last"):
        n = sum(1 for fn in fl if ziele["flaechen"][fn] == art)
        if n:
            arten.append(f"{art} {n}")
    flaechen = (f"{_anzahl(len(fl), 'Fläche', 'Flächen')} ({', '.join(arten)}) mit "
                f"{_spanne(ziele['h'][fn] for fn in fl)} statt {_spanne(ziele['h_mittel'][fn] for fn in fl)}"
                f" ({anteil} von Mittel, eine Elementlage, von dort wachsend)")
    nb = len(ziele["boegen"])
    if st.bogenwinkel >= BOGENWINKEL:
        boegen = boegen_regel
    elif nb:
        boegen = f"an {_anzahl(nb, 'Bogen', 'Bögen')} der Kontakt- und Lagerflächen {boegen_regel}"
    else:
        boegen = "keine Bögen an Kontakt- und Lagerflächen"
    return f"wie Mittel, feiner an {flaechen}; {boegen}"


def kantenlaenge_text(netz, model=None, k: int = 0) -> str:
    """Die wirksame Kantenlaenge fuer die Maske.

    Mit Modell (bis KANTEN_OBJEKTE Objekte): die Kantenlaenge im Feld, wie
    sie der Vernetzer je Koerper bzw. Flaeche mit Dicke nimmt
    (netzdichte.elementlaenge) - kleinste bis groesste. Sonst die Regel
    (Netzdichte oder Ziellaenge). Bei Fein ist die Kantenlaenge im Feld die
    von Mittel, und dahinter steht, was feiner wird (:func:`fein_text`) -
    bis zum 07.10.2026 stand hier die halbe Kantenlaenge."""
    from . import netzdichte as nd
    zusatz = f"; Fein: {fein_text(netz, model, k)}" if stufe(netz) == "fein" else ""
    dichte = getattr(netz, "dichte", "mittel") or "mittel"
    if dichte in nd.DICHTEN:
        regel = f"Netzdichte {dichte}: {nd.DICHTEN[dichte]} Elemente über die Objektgröße"
    else:
        regel = f"Ziellänge {_mm(netz.ziellaenge)}"
    if model is None:
        return regel + zusatz
    objekte = list((getattr(model, "koerper", None) or {}).values())
    objekte += [f for f in (getattr(model, "flaechen", None) or {}).values() if getattr(f, "dicke", None)]
    if not objekte or len(objekte) > KANTEN_OBJEKTE:
        return regel + zusatz
    try:
        hs = [float(nd.elementlaenge(model, netz, o)["h"]) for o in objekte]
    except Exception:                      # noqa: BLE001 - dann nur die Regel
        return regel + zusatz
    hs = [h for h in hs if h > 0]
    if not hs:
        return regel + zusatz
    was = f"{len(objekte)} Objekt{'e' if len(objekte) != 1 else ''}"
    feld = (_mm(min(hs)) if abs(max(hs) - min(hs)) < 1e-12 else f"{_mm(min(hs))} … {_mm(max(hs))}")
    return f"{feld} im Feld ({was}); {regel}{zusatz}"


@contextmanager
def beim_vernetzen(model, log: list, k: int = 0):
    """Vernetzen mit der Stufe: erst die Sperre (Mittel/Fein an einem
    gesperrten Modell -> Entwurf, mit Zeile im Protokoll), dann bei Fein die
    Quellen der Vergroeberungsstufe ``k`` (:func:`fein_stufe`, Vorgabe 0)
    fuer die Dauer des Vernetzens, mit einer Zeile im Protokoll, die Zahl und
    Art der verfeinerten Flaechen und die Zahl der Boegen nennt. Danach
    stehen die gespeicherten Netzeinstellungen wieder da - ausser der Stufe,
    die die Sperre gesetzt hat."""
    zeile = sperre_anwenden(model)
    if zeile:
        log.append(zeile)
    gespeichert = model.netz
    teilungen: dict = {}
    if stufe(gespeichert) == "fein":
        st = fein_stufe(k)
        w, ziele = _fein(gespeichert, model, k)
        kopf = "Elemente Fein" + (f" (Stufe {st.k} von {FEIN_STUFEN_ANZAHL - 1}, vergröbert)" if st.k else "")
        log.append(f"{kopf}: {fein_text(gespeichert, model, k, ziele)}")
        if not st.ist_mittel:
            # Abgebildete Sechsflaechner nehmen ihre Teilung aus dem Koerper
            # (Volumenkoerper.teilung, Vorgabe 4 x 4 x 4) und folgen dem
            # Groessenfeld nicht; eine Flaeche mit eigener Teilung ebenso,
            # wenn die Netzdichte sie nicht uebersteuert. Fuer sie bleibt Fein
            # die doppelte Teilung - fuer die Dauer des Vernetzens (gemessen
            # am Wuerfel 1 m, Teilung 2: Mittel 8 hex20, Fein 64; 25.09.2026).
            for obj in list((getattr(model, "koerper", None) or {}).values()) \
                    + list((getattr(model, "flaechen", None) or {}).values()):
                t = list(getattr(obj, "teilung", None) or [])
                if t:
                    teilungen[id(obj)] = (obj, t)
                    obj.teilung = [max(1, int(x)) * 2 for x in t]
    else:
        w = gespeichert
    model.netz = w
    try:
        yield w
    finally:
        if model.netz is w:
            model.netz = gespeichert
        for obj, t in teilungen.values():
            obj.teilung = t
