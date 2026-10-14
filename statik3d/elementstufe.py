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

**Krafteinleitungen ohne Flaeche** (seit 13.10.2026, Mittel und Fein): an
einer starren Scheibe ueber einer Bohrung (Kopplung nur am Lochrand) und an
einem Stabende auf einem Volumen legt :func:`wirksam` Quellen ins
Groessenfeld - am Lochrand 9 statt 18 Grad je Abschnitt, hoechstens die halbe
Kantenlaenge von Mittel, am Stabende die halbe, je zwei Elementringe weit
(netzfeld.krafteinleitungen, netzfeld.kraft_ziele). Anlass ist der Wunsch des
Anwenders vom 13.10.2026: „Netzabhängige Zonen sind zu groß, weil elementweise
auf grobem Netz bestimmt. Bitte über Radius bzw. max. 1–2 Elementringe
begrenzen und im Lochbereich feiner bzw. quadratisch vernetzen.“ Quadratisch
sind Mittel und Fein ohnehin (tet10); Entwurf bleibt linear und ohne diese
Quellen - es ist die schnelle Stufe fuer Verformungen, und tet4 neben tet10
in einem Netz gaebe keine vertraeglichen Elemente. Der Schalter ist
``Netzeinstellungen.krafteinleitung_fein`` (Vorgabe ein; aeltere Dateien
bekommen beim Laden die Vorgabe). Bis zum 13.10.2026 war Mittel dort so grob
wie ueberall.

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
              "Schalen quadratisch (shell6/shell8), feiner an Krafteinleitungen ohne Fläche "
              "(starre Scheiben über Bohrungen, Stabenden)",
    "fein": "wie Mittel (tet10, hex20 (VQ203), Schalen quadratisch), feiner an Kontakt-, Lager- und "
            "Lastflächen und an den Bögen der Kontakt- und Lagerflächen, dazu wie Mittel an "
            "Krafteinleitungen ohne Fläche",
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

    Eine Stufe allein vernetzt::

        with elementstufe.beim_vernetzen(model, log, k=k):
            mesher.modell_vernetzen(model, log)

    Die Netzeinstellungen einer Stufe allein gibt ``wirksam(netz, model,
    k=k)``, den Text fuer Maske und Protokoll ``fein_text(netz, model, k)``.
    Ueberschreitet das Netz die Grenze in Unbekannten, geht F2 die Stufen
    ueber :func:`fein_stufen` durch (seit 08.10.2026) - dort beginnt es mit
    k = 0, und die verdoppelte Teilung abgebildeter Koerper bleibt auch in
    der letzten Stufe (siehe dort).
    """
    k = min(max(int(k or 0), 0), FEIN_STUFEN_ANZAHL - 1)
    w, f = FEIN_STUFEN[k]
    return FeinStufe(k, float(w), float(f))


#: Die Stufen der Verfeinerung an Krafteinleitungen ohne Flaeche (seit
#: 13.10.2026): (Bogenwinkel je Abschnitt am Lochrand starrer Scheiben [Grad],
#: Anteil der Ringe, die ihn bekommen - die mit dem groessten Radius zuerst,
#: Kantenlaenge an Stabenden als Anteil von Mittel). j = 0 ist die volle
#: Verfeinerung. Wird das Netz zu gross (Grenze in Unbekannten), vergroebert
#: das Programm Stufe um Stufe: erst bekommen nur noch die groessten Ringe das
#: feinere Netz (ein Viertel), dann keiner, dann sind die Stabenden groeber
#: (h/1,5), zuletzt Mittel ohne Verfeinerung. Grund der Reihenfolge: der
#: Aufwand je Ring ist ungefaehr gleich (die Elemente im Kegel einer
#: Ringquelle zaehlen nach Abschnitten, nicht nach Radius), der Gewinn an
#: Zonentiefe (zwei Elementringe, 2 * r * Winkel) waechst aber mit dem Radius;
#: ein Stabende kostet dagegen nur wenige hundert Elemente.
KRAFT_STUFEN = ((9.0, 1.0, 0.5), (9.0, 0.25, 0.5), (9.0, 0.0, 0.5), (9.0, 0.0, 1.0 / 1.5), (9.0, 0.0, 1.0))
KRAFT_STUFEN_ANZAHL = len(KRAFT_STUFEN)


@dataclass(frozen=True)
class KraftStufe:
    """Eine Vergroeberungsstufe der Verfeinerung an Krafteinleitungen ohne
    Flaeche (:data:`KRAFT_STUFEN`)."""
    #: Nummer der Stufe, 0 = volle Verfeinerung
    j: int
    #: Bogenwinkel je Abschnitt am Lochrand starrer Scheiben [Grad]
    bogenwinkel: float
    #: Anteil der Ringe mit diesem Winkel (die groessten zuerst); 0 = keiner
    ringanteil: float
    #: Kantenlaenge an Stabenden als Anteil von Mittel
    stabfaktor: float

    @property
    def ist_mittel(self) -> bool:
        """Verfeinert diese Stufe nichts mehr (keine Ringe, Stabenden h)?"""
        return self.ringanteil <= 0.0 and self.stabfaktor >= 1.0


def kraft_stufe(j: int = 0) -> KraftStufe:
    """Die Stufe j der Verfeinerung an Krafteinleitungen ohne Flaeche; ein
    groesseres j gibt die letzte Stufe (Mittel), ein negatives Stufe 0."""
    j = min(max(int(j or 0), 0), KRAFT_STUFEN_ANZAHL - 1)
    w, a, f = KRAFT_STUFEN[j]
    return KraftStufe(j, float(w), float(a), float(f))


def kraft_an(netz) -> bool:
    """Werden Krafteinleitungen ohne Flaeche feiner vernetzt (seit
    13.10.2026)? Bei Mittel und Fein, solange der Schalter
    ``Netzeinstellungen.krafteinleitung_fein`` an ist (Vorgabe; eine aeltere
    Datei ohne das Feld hat ihn an). Entwurf nie."""
    return bool(getattr(netz, "krafteinleitung_fein", True)) and stufe(netz) in ("mittel", "fein")


def kraft_nr(netz, k: int) -> int:
    """Die Stufe j der Krafteinleitungen in der Stufe k der Grenze in
    Unbekannten. Mittel: j = k. Fein: die Krafteinleitungen bleiben auf
    Stufe 0, solange Fein selbst vergroebert (k = 0 bis zur letzten Stufe von
    Fein, die Mittel ist); danach geht es mit Stufe 1, 2 ... weiter, die Stufen
    von Fein setzen sich in denen von Mittel fort. So ist Fein nie groeber als
    Mittel an derselben Stelle."""
    k = max(int(k or 0), 0)
    if stufe(netz) == "fein":
        return max(0, k - (FEIN_STUFEN_ANZAHL - 1))
    return k


def _hat_stellen(kziele) -> bool:
    return bool(kziele) and bool(kziele.get("ringe") or kziele.get("punkte"))


def stufen_anzahl(netz, stellen: dict = None) -> int:
    """Wie viele Stufen die Grenze in Unbekannten fuer diese Netzeinstellungen
    hat (:func:`fein_stufen`): Entwurf 1, Mittel 1 und mit Krafteinleitungen
    ohne Flaeche :data:`KRAFT_STUFEN_ANZAHL`, Fein :data:`FEIN_STUFEN_ANZAHL`
    und mit Krafteinleitungen die Stufen von Mittel dahinter."""
    hat = kraft_an(netz) and bool(stellen) and bool(stellen.get("ringe") or stellen.get("punkte"))
    if stufe(netz) == "fein":
        return FEIN_STUFEN_ANZAHL + (KRAFT_STUFEN_ANZAHL - 1 if hat else 0)
    return KRAFT_STUFEN_ANZAHL if (stufe(netz) == "mittel" and hat) else 1


def _kraft(netz, model, k: int, stellen: dict = None) -> tuple:
    """(Quellen fuer ``verfeinerungen``, Ziele) an den Krafteinleitungen ohne
    Flaeche in der Stufe k der Grenze (:func:`kraft_nr`, :data:`KRAFT_STUFEN`).
    ([], None) ohne Modell, mit Schalter aus, an Entwurf und in der letzten
    Stufe. ``stellen``: die Krafteinleitungen (netzfeld.krafteinleitungen)
    oder eine Funktion ohne Argument, die sie liefert - die Maske merkt sie
    sich, damit eine Aenderung der Felder sie nicht jedes Mal neu bestimmt
    (am Drehlager gemessen 3 s)."""
    if model is None or not kraft_an(netz):
        return [], None
    st = kraft_stufe(kraft_nr(netz, k))
    if st.ist_mittel:
        return [], None
    from . import netzfeld
    if callable(stellen):
        stellen = stellen()
    ziele = netzfeld.kraft_ziele(model, netz, st.bogenwinkel, st.stabfaktor, stellen, st.ringanteil)
    return netzfeld.kraft_verfeinerungen(ziele), ziele


def _fein(netz, model, k: int, stellen: dict = None) -> tuple:
    """(Netzeinstellungen fuer die Dauer des Vernetzens, Ziele, Ziele an
    Krafteinleitungen) von Fein in der Stufe k - die Ziele
    (netzfeld.fein_ziele, netzfeld.kraft_ziele) None ohne Modell oder in der
    Stufe Mittel."""
    st = fein_stufe(k)
    ziele, zusatz = None, []
    if model is not None and not st.ist_mittel:
        from . import netzfeld
        ziele = netzfeld.fein_ziele(model, netz, st.bogenwinkel, st.flaechenfaktor)
        zusatz = netzfeld.fein_verfeinerungen(ziele)
    kraft, kziele = _kraft(netz, model, k, stellen)
    return (replace(netz, verfeinerungen=list(getattr(netz, "verfeinerungen", None) or []) + zusatz + kraft),
            ziele, kziele)


def _mittel(netz, model, k: int, stellen: dict = None) -> tuple:
    """(Netzeinstellungen fuer die Dauer des Vernetzens, Ziele an
    Krafteinleitungen) von Mittel in der Stufe k: ohne Krafteinleitungen
    ``netz`` selbst (bitgleich wie bis zum 13.10.2026)."""
    kraft, kziele = _kraft(netz, model, k, stellen)
    if not kraft:
        return netz, kziele
    return replace(netz, verfeinerungen=list(getattr(netz, "verfeinerungen", None) or []) + kraft), kziele


def wirksam(netz, model=None, k: int = 0, stellen: dict = None):
    """Die Netzeinstellungen, mit denen vernetzt wird.

    Entwurf: ``netz`` selbst. Mittel: ``netz`` selbst, an einem Modell mit
    Krafteinleitungen ohne Flaeche (seit 13.10.2026, Schalter
    ``krafteinleitung_fein``) eine Kopie mit ihren Quellen in
    ``verfeinerungen`` (:func:`_kraft`). Fein (seit 07.10.2026, Paket F1):
    eine Kopie mit **denselben Laengen wie Mittel** - Netzdichte,
    Ziellaenge, kleinste und groesste Elementgroesse, Kantenlaenge je
    Koerper, Netzverfeinerungen und Feldpunkte des Anwenders bleiben und
    wirken wie bei Mittel -, dazu in ``verfeinerungen`` die Quellen von Fein
    in der Vergroeberungsstufe ``k`` (:func:`fein_stufe`): halbe
    Kantenlaenge an Kontakt-, Lager- und Lastflaechen, 9 Grad je Abschnitt
    an den Boegen der Kontakt- und Lagerflaechen (netzfeld.fein_ziele), und
    wie bei Mittel die Quellen an Krafteinleitungen. Ohne ``model`` gibt es
    keine Quellen. Gespeichert wird davon nichts. ``stellen``: die
    Krafteinleitungen (netzfeld.krafteinleitungen), wenn schon bestimmt.

    Bis zum 07.10.2026 halbierte Fein hier jede Laenge des ganzen Modells
    (Netzdichte, Ziellaenge, h_min/h_max, Kantenlaenge je Koerper,
    Verfeinerungen, Feldpunkte), aber nicht den Bogenwinkel: am Drehlager
    wurde damit das Innere der grossen Teile feiner, die Bohrungen blieben,
    wie sie waren (Bauplan PLAN-FEIN-SMART-2026-10-07)."""
    s = stufe(netz)
    if s == "fein":
        return _fein(netz, model, k, stellen)[0]
    if s == "mittel":
        return _mittel(netz, model, k, stellen)[0]
    return netz


def _stabenden_text(f: float) -> str:
    teiler = round(1.0 / f, 3)
    return "h" if abs(teiler - 1.0) < 1e-9 else "h/" + f"{teiler:g}".replace(".", ",")


def _ringanteil_text(a: float) -> str:
    if a >= 1.0:
        return ""
    return {0.5: " (die größere Hälfte)", 0.25: " (das größte Viertel)"}.get(a, f" (die größten {a * 100:g} %)")


def stufe_text(k: int, s: str = "fein", kraft: bool = False) -> str:
    """Der Text einer Vergroeberungsstufe fuer das Protokoll, etwa „Fein
    Stufe 2: Bögen 18°, Flächen h/2“ oder (an Krafteinleitungen ohne Flaeche,
    seit 13.10.2026) „Mittel Stufe 1: Ringe 9° (das größte Viertel),
    Stabenden h/2“ - er steht in ``quelle`` der Netzeinstellungen, die
    :func:`fein_stufen` fuer diese Stufe liefert. ``kraft``: das Modell hat
    Krafteinleitungen ohne Flaeche; dann heissen die Stufen von Fein ab seiner
    letzten „Mittel Stufe j“ - sie setzen Fein an den Krafteinleitungen fort."""
    st = fein_stufe(k)
    if s == "fein" and not (kraft and st.letzte):
        return (f"Fein Stufe {st.k}: Bögen {st.bogenwinkel:g}°, Flächen {_stabenden_text(st.flaechenfaktor)}"
                + (" (wie Mittel)" if st.ist_mittel else ""))
    j = max(0, int(k) - (FEIN_STUFEN_ANZAHL - 1)) if s == "fein" else int(k)
    ks = kraft_stufe(j)
    if ks.ist_mittel:
        return f"Mittel Stufe {ks.j}: ohne Verfeinerung an Krafteinleitungen"
    ringe = (f"Ringe {ks.bogenwinkel:g}°{_ringanteil_text(ks.ringanteil)}" if ks.ringanteil > 0 else "ohne Ringe")
    return f"Mittel Stufe {ks.j}: {ringe}, Stabenden {_stabenden_text(ks.stabfaktor)}"


def fein_stufen(model, netz=None):
    """**Anschluss von Fein an die Grenze in Unbekannten** (Pakete F1 und F2,
    08.10.2026): die Vergroeberungsstufen als Funktion ``einstellung(k) ->
    Netzeinstellungen | None``, wie sie mesher.koerper_vernetzen,
    mesher.modell_vernetzen(stufen=...) und gui.main._vernetzen_netz(stufen=...)
    erwarten - oder None, wenn nicht mit Fein vernetzt wird (Entwurf, Mittel,
    Fein an einem gesperrten Modell, das :func:`beim_vernetzen` auf Entwurf
    gestellt hat). Ohne Stufen bleibt ueber der Grenze das Netz, mit Warnung.

    ``netz``: die Netzeinstellungen, mit denen vernetzt wird - innerhalb von
    :func:`beim_vernetzen` das, was es liefert::

        with elementstufe.beim_vernetzen(model, log) as w:
            mesher.modell_vernetzen(model, log, stufen=elementstufe.fein_stufen(model, w))

    sonst die gespeicherten (Vorgabe ``model.netz``). Die Quellen von Fein
    darin (Arten ``fein_*``) zaehlen nicht: einstellung(k) baut jede Stufe
    aus den Einstellungen ohne sie neu (:func:`wirksam` mit k, also
    :func:`fein_stufe`) und schreibt :func:`stufe_text` in ``quelle``; das
    Protokoll der Grenze nennt ihn. Fuer k jenseits der letzten Stufe (Mittel)
    gibt es None. Ohne Nebenwirkung: Modell und ``netz`` bleiben, wie sie
    sind, und jeder Aufruf rechnet nur die Ziele seiner Stufe
    (netzfeld.fein_ziele).

    **Teilung abgebildeter Koerper:** :func:`beim_vernetzen` verdoppelt sie
    bei Fein fuer die ganze Dauer des Vernetzens - am Objekt, nicht in den
    Netzeinstellungen. einstellung(k) darf das nicht aendern (ohne
    Nebenwirkung), und die Stufenschleife tauscht nur ``model.netz``; die
    Teilung bleibt darum auch in der letzten Stufe verdoppelt. Sie betrifft
    nur abgebildete Sechsflaechner (Quader mit sechs Vierecken und acht
    Ecken, hex20; mesher.mesh_koerper und sweep.lagenvorgabe lesen die
    Teilung nur dort) und Flaechen mit eigener Teilung, die vor den Volumen
    und ausserhalb der Schleife vernetzt werden - beide folgen dem
    Groessenfeld ohnehin nicht. Ein Modell mit solchen Koerpern ist in der
    letzten Stufe darum nicht bitgleich Mittel, sondern hat dort feinere
    Quader (Stand 08.10.2026).

    **Krafteinleitungen ohne Flaeche** (seit 13.10.2026): hat das Modell
    solche Stellen und ist der Schalter ``krafteinleitung_fein`` an, hat auch
    Mittel Stufen - die :data:`KRAFT_STUFEN`, nur fuer die Quellen an den
    Krafteinleitungen (:func:`_kraft`); die letzte ist Mittel ohne sie,
    bitgleich wie bis zum 13.10.2026. Ohne Stellen oder mit Schalter aus
    bleibt es bei None. Fein nimmt die Quellen an Krafteinleitungen mit der
    vollen Verfeinerung mit, solange es selbst vergroebert, und geht danach
    mit den Stufen von Mittel weiter (:func:`kraft_nr`) - Fein ist so nie
    gröber als Mittel. Ohne Stellen sind es wie bisher
    :data:`FEIN_STUFEN_ANZAHL` Stufen."""
    netz = model.netz if netz is None else netz
    s = stufe(netz)
    if s not in ("mittel", "fein") or not frei(model, s):
        return None
    stellen = None
    if kraft_an(netz):
        from . import netzfeld
        stellen = netzfeld.krafteinleitungen(model)
    anzahl = stufen_anzahl(netz, stellen)
    hat = anzahl > (FEIN_STUFEN_ANZAHL if s == "fein" else 1)
    if s == "mittel" and not hat:
        return None
    basis = replace(netz, verfeinerungen=[
        v for v in (getattr(netz, "verfeinerungen", None) or [])
        if not (isinstance(v, dict) and str(v.get("art", "")).startswith("fein_"))])

    def einstellung(k):
        k = int(k)
        if k < 0 or k >= anzahl:
            return None
        return replace(wirksam(basis, model, k, stellen), quelle=stufe_text(k, s, hat))
    return einstellung


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


def kraft_text(kziele: dict) -> str:
    """Was an den Krafteinleitungen ohne Flaeche feiner wird - fuer Maske und
    Protokoll („feiner an Krafteinleitungen ohne Fläche: 16 Ringe starrer
    Scheiben über Bohrungen (r 25,5 mm) mit 4 mm (9° je Abschnitt, höchstens
    die Hälfte von Mittel), …“); leer ohne Stellen."""
    if not _hat_stellen(kziele):
        return ""
    ringe, punkte = kziele.get("ringe") or [], kziele.get("punkte") or []
    f = float(kziele.get("faktor", 0.5))
    anteil = "die Hälfte" if abs(f - 0.5) < 1e-9 else f"das {f:.2f}-Fache".replace(".", ",")
    teile = []
    if ringe:
        gesamt = int(kziele.get("ringe_gesamt", len(ringe)) or len(ringe))
        if gesamt > len(ringe):
            # nur die groessten Ringe (Stufe der Grenze, KRAFT_STUFEN)
            wer = (f"{'größter Ring' if len(ringe) == 1 else 'größte Ringe'} von {gesamt} Ringen "
                   "starrer Scheiben über Bohrungen")
        else:
            wer = ("Ring einer starren Scheibe über einer Bohrung" if len(ringe) == 1
                   else "Ringe starrer Scheiben über Bohrungen")
        teile.append(f"{len(ringe)} {wer} (r {_spanne(s['r'] for s in ringe)}) mit "
                     f"{_spanne(s['h'] for s in ringe)} ({float(kziele['bogenwinkel']):g}° je Abschnitt, "
                     f"höchstens {anteil} von Mittel)")
    if punkte:
        teile.append(f"{_anzahl(len(punkte), 'Stabende', 'Stabenden')} auf Volumen mit "
                     f"{_spanne(s['h'] for s in punkte)} ({anteil} von Mittel)")
    return ("feiner an Krafteinleitungen ohne Fläche: " + ", ".join(teile)
            + " – je zwei Elementringe, von dort wachsend")


def fein_text(netz, model=None, k: int = 0, ziele: dict = None, kziele: dict = None, stellen=None) -> str:
    """Was Fein in der Stufe k verfeinert - fuer die Maske (wirksame
    Kantenlaenge) und das Protokoll beim Vernetzen. Mit Modell mit Zahl und
    Art der Flaechen, ihrer Kantenlaenge gegen Mittel und der Zahl der
    Boegen; ohne Modell die Regel. Dazu, was an Krafteinleitungen ohne
    Flaeche feiner wird (:func:`kraft_text`, seit 13.10.2026)."""
    st = fein_stufe(k)
    kt = ""
    if model is not None and kraft_an(netz):
        if kziele is None:
            kziele = _kraft(netz, model, k, stellen)[1]
        kt = kraft_text(kziele)
    if st.ist_mittel:
        return f"wie Mittel; {kt}" if kt else "wie Mittel (letzte Vergröberungsstufe: keine Verfeinerung)"
    text = _fein_text_flaechen(netz, model, k, ziele)
    return text + "; " + kt if kt else text


def _fein_text_flaechen(netz, model, k: int, ziele: dict) -> str:
    from .mesher3d import BOGENWINKEL
    st = fein_stufe(k)
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


def kantenlaenge_text(netz, model=None, k: int = 0, stellen=None) -> str:
    """Die wirksame Kantenlaenge fuer die Maske.

    Mit Modell (bis KANTEN_OBJEKTE Objekte): die Kantenlaenge im Feld, wie
    sie der Vernetzer je Koerper bzw. Flaeche mit Dicke nimmt
    (netzdichte.elementlaenge) - kleinste bis groesste. Sonst die Regel
    (Netzdichte oder Ziellaenge). Bei Fein ist die Kantenlaenge im Feld die
    von Mittel, und dahinter steht, was feiner wird (:func:`fein_text`) -
    bis zum 07.10.2026 stand hier die halbe Kantenlaenge. Bei Mittel steht
    dahinter, was an Krafteinleitungen ohne Flaeche feiner wird (seit
    13.10.2026), wenn das Modell solche Stellen hat. ``stellen``: wie bei
    :func:`_kraft`."""
    from . import netzdichte as nd
    zusatz = ""
    if stufe(netz) == "fein":
        zusatz = f"; Fein: {fein_text(netz, model, k, stellen=stellen)}"
    elif stufe(netz) == "mittel" and model is not None and kraft_an(netz):
        kt = kraft_text(_kraft(netz, model, k, stellen)[1])
        zusatz = f"; Mittel: {kt}" if kt else ""
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
    die die Sperre gesetzt hat. Geliefert werden die Netzeinstellungen, mit
    denen vernetzt wird; ``fein_stufen(model, w)`` macht daraus die Stufen
    fuer die Grenze in Unbekannten (seit 08.10.2026). Bei Mittel an einem
    Modell mit Krafteinleitungen ohne Flaeche kommen deren Quellen dazu, mit
    einer Zeile „Elemente Mittel: feiner an Krafteinleitungen ohne Fläche …“
    (seit 13.10.2026)."""
    zeile = sperre_anwenden(model)
    if zeile:
        log.append(zeile)
    gespeichert = model.netz
    teilungen: dict = {}
    stellen = None
    if model is not None and kraft_an(gespeichert):
        from . import netzfeld
        stellen = netzfeld.krafteinleitungen(model)
    letzte = stufen_anzahl(gespeichert, stellen) - 1
    if stufe(gespeichert) == "fein":
        st = fein_stufe(k)
        w, ziele, kziele = _fein(gespeichert, model, k, stellen)
        kopf = "Elemente Fein" + (f" (Stufe {int(k)} von {letzte}, vergröbert)" if int(k) else "")
        log.append(f"{kopf}: {fein_text(gespeichert, model, k, ziele, kziele)}")
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
    elif stufe(gespeichert) == "mittel":
        w, kziele = _mittel(gespeichert, model, k, stellen)
        kt = kraft_text(kziele)
        if kt:
            kopf = "Elemente Mittel" + (f" (Stufe {int(k)} von {letzte}, vergröbert)" if int(k) else "")
            log.append(f"{kopf}: {kt}")
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
