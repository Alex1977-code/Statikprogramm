"""
Symbole im Ribbon (Plan-Paket 12b, 03.10.2026).

Bis dahin trugen rund zehn grosse Knoepfe nur den Anfangsbuchstaben in einem
Kreis (die Plakette, die symbole.py fuer jeden Namen ohne Zeichnung malt), die
fuenf Lastknoepfe Vorspannung, Uebermass, Spiel geben, Passung und Wind alle
dasselbe Lastsymbol, und einige Symbole waren geraten statt gewaehlt
(Knotenlager zeigte „Knoten neu“, Werteskala „Oeffnen“).

Geprueft wird am laufenden Ribbon - Befehl -> Name der Zeichnung, gelesen aus
dem Zwischenspeicher von ``symbole.symbol``:

* kein grosser Knopf mehr mit Buchstaben-Plakette (auch im Kontextregister
  „Auswahl“);
* die fuenf Lastknoepfe: paarweise verschiedene Namen **und** Bilder;
* die korrigierten Symbole (Tabelle KORRIGIERT);
* jede neue Zeichnung zeichnet etwas (nicht leer, nicht eine volle Flaeche),
  in 16, 28 und 48 px, an und aus;
* in einer Gruppe tragen verschiedene Knoepfe verschiedene Symbole - ausser
  den namentlich genannten Ausnahmen;
* jeder Name, den der Quelltext einem Befehl gibt, hat eine Zeichnung.

Gemalt wird mit QPainter, ohne Schrift: die Pruefung laeuft offscreen.

Aufruf:  python -m tests.test_symbole_ribbon
"""
import math
import os
import sys
import tempfile
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_symbole_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}

Knopf = namedtuple("Knopf", "register gruppe art text symbol")

#: Die fuenf Lastknoepfe aus dem Plan: Text -> Name der Zeichnung
LASTKNOEPFE = {
    "Vorspannung": "vorspannung",
    "Übermaß": "uebermass",
    "Spiel geben": "spiel",
    "Passung": "passung",
    "Wind": "wind",
}

#: Befehle, deren Symbol falsch geraten war: Text -> Name der Zeichnung heute.
#: Wer hier etwas aendert, aendert eine Entscheidung (Begruendung im Commit
#: „12b“ und im Benutzerhandbuch, Abschnitt Ribbon).
KORRIGIERT = {
    "Knotenlager": "lager",                    # war „knoten_neu“
    "Linienlager…": "lager_linie",             # war „linie_neu“
    "Flächenlager…": "lager_flaeche",          # war „flaeche_neu“
    "Werteskala": "skala",                     # war „oeffnen“
    "Ergebnisse als CSV…": "csv",              # war „ergebnisse“
    "Schale": "flaechen",                      # war „hiddenline“ (ein Quader)
    "Linie aus Knoten…": "linien",             # war „knoten_neu“ (wie der Knopf daneben)
    "Neues KS…": "ks",                         # war „neu“ (neues Dokument)
    "Aus drei Knoten": "ks_knoten",            # war „knoten_neu“
    "Datei hinzufügen…": "anhang",             # war „oeffnen“ (wie „Unterlage öffnen“)
    "Neue Skizze": "skizze",                   # war „neu“ (neues Dokument)
    "Doppelte Knoten zusammenführen": "knoten_vereinen",   # war „knoten_neu“ (ein Plus)
    "Flächen verschneiden": "verschneiden",    # war „flaeche_neu“ (wie der Knopf daneben)
    "Kontakte zeigen": "ansicht",              # war „kontakt“ (wie der Hauptknopf)
    "Kontaktfugen ausführen": "netz_trennen",  # war „kontakt“ (wie Kontaktbedingung)
    "Lastfälle": "lastfall",                   # war „last“ (ein einzelner Pfeil)
    "Lastfälle nach DIN 19704…": "wasserdruck",  # war „last“ (wie Lastfälle)
    "Ermüdungslasten…": "ermuedung",           # war „last“ (wie Lastfälle)
    "Wasserdruck": "wasserdruck",              # war „flaechenlast“ (wie die Flächenlast)
    "Netzeinstellungen…": "einstellungen",     # war „netz“ (wie Netzqualität)
    "Adaptiv vernetzen…": "netz_adaptiv",      # war „vernetzen“ (wie Vernetzen)
    "Übernommene Bilder": "tabelle",           # war „bild“ (wie Ansicht übernehmen)
    "Layerliste": "layer",                     # war „bericht“ (ein Schriftstück)
    "Tastenkürzel": "tastatur",                # war „tabelle“
    "Abstand": "abstand",                      # war „linie_neu“ (eine neue Linie)
    "Linearmaß": "masslinie",                  # war „linie_neu“
    "Maßkette": "masskette",                   # war „linien“
    "Länge / Fläche": "laenge_flaeche",        # war „suchen“ (eine Lupe)
}

#: Die Zeichnungen, die 12b neu anlegt: jede muss etwas zeichnen
NEUE = (
    "pruefen", "verschieben", "lot", "fang_lot", "spalt", "passung", "uebermass", "spiel",
    "stellungen", "konfiguration", "verschluss", "einheiten", "fenster", "zuweisen",
    "vorspannung", "wind", "wasserdruck", "skala", "lager_linie", "lager_flaeche",
    "knoten_vereinen", "anhang", "skizze", "tastatur", "layer", "ks_knoten", "verschneiden",
    "abstand", "masslinie", "masskette", "netz_trennen", "netz_adaptiv", "laenge_flaeche",
    "bearbeiten",
)

#: Gruppen, in denen zwei Knoepfe bewusst dasselbe Symbol tragen:
#: (Register, Gruppe, Symbol) -> Grund
AUSNAHMEN = {
    ("Lasten", "Kombinationen", "kombination"):
        "dieselbe Handlung nach zwei Normen (EN 1990, DIN 19704); der Text sagt, welche",
    ("Messen", "Verwalten", "loeschen"):
        "zwei Arten zu loeschen (letzte, alle) - dieselbe Handlung",
    ("Extras", "Handbücher", "handbuch"):
        "drei Buecher, ein Symbol: Benutzer-, Theoriehandbuch, Schnittstellen",
    ("Auswahl", "Elemente", "loeschen"):
        "Elemente und Knoten loeschen - dieselbe Handlung, der Text sagt, was",
    ("Ergebnisse", "Auswahl", "ergebnisse"):
        "„Ergebnisse zeigen“ ist dieselbe Aktion wie der Schalter in der Glasleiste, die ihr Symbol "
        "setzt (main.py: leiste.knopf(self.act_ergebnisse, \"ergebnisse\", …)); ein anderes hier "
        "wuerde dort mitwandern",
}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w.fehler_liste = []
    # Fehler und Hinweise gemeinsam abfangen (tests/meldungen.py, Paket 9b): die
    # Liste bekommt beide, w.meldungen wertet sie getrennt aus
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    _FENSTER.update(w=w, app=app)
    return w, app


def _namen_der_zeichnungen() -> dict:
    """cacheKey eines Symbols -> sein Name. Die Symbole eines Befehls sind
    Kopien desselben QIcon, die Kopie behaelt den Schluessel."""
    from statik3d.gui import symbole as sym
    return {ic.cacheKey(): (k[1] if k[0] == "weiss" else k[0]) for k, ic in sym._ZWISCHEN.items()}


def _knoepfe(w) -> list:
    """Alle grossen und kleinen Knoepfe aller Register, auch des Kontextregisters."""
    from PySide6 import QtWidgets
    rev = _namen_der_zeichnungen()
    rb = w.ribbon
    register = dict(rb._register)
    if rb._kontext is not None:
        register[rb._kontext_name] = rb._kontext
    aus = []
    for rname, reg in register.items():
        for b in reg.findChildren(QtWidgets.QToolButton):
            art = {"ribbongross": "gross", "ribbonklein": "klein"}.get(b.objectName())
            if art is None:
                continue
            g = b.parent()
            while g is not None and g.objectName() != "ribbongruppe":
                g = g.parent()
            gname = g._name if g is not None else "?"
            # das Kontextregister heisst „Auswahl: 12 Knoten“ - die Zahl wechselt
            reg_name = "Auswahl" if rname.startswith("Auswahl:") else rname
            aus.append(Knopf(reg_name, gname, art, b.text().replace("&&", "&"),
                             rev.get(b.icon().cacheKey())))
    return aus


def _gezeichnet(name) -> bool:
    from statik3d.gui import symbole as sym
    return bool(name) and name in sym.VORSCHRIFTEN


def _bild(name: str, groesse: int, an: bool = False):
    from PySide6 import QtCore, QtGui
    from statik3d.gui import symbole as sym
    zustand = QtGui.QIcon.On if an else QtGui.QIcon.Off
    return sym.symbol(name).pixmap(QtCore.QSize(groesse, groesse), QtGui.QIcon.Normal,
                                   zustand).toImage()


def _deckung(bild) -> float:
    """Anteil der Bildpunkte, die etwas zeigen (nicht durchsichtig)."""
    n = 0
    for y in range(bild.height()):
        for x in range(bild.width()):
            if bild.pixelColor(x, y).alpha() > 128:
                n += 1
    return n / float(bild.width() * bild.height())


def _unterschied(a, b) -> int:
    """Zahl der Bildpunkte, in denen zwei gleich grosse Bilder sichtbar verschieden sind."""
    if a.size() != b.size():
        return a.width() * a.height()
    n = 0
    for y in range(a.height()):
        for x in range(a.width()):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            d = (abs(ca.red() - cb.red()) + abs(ca.green() - cb.green())
                 + abs(ca.blue() - cb.blue()) + abs(ca.alpha() - cb.alpha()))
            if d > 120:
                n += 1
    return n


def _auswahl_an(w, app):
    w._set_selection(list(range(12)))
    app.processEvents()


def _auswahl_aus(w, app):
    w._set_selection([])
    app.processEvents()


# --------------------------------------------------------------------------
def test_grosse_knoepfe_haben_eine_zeichnung():
    w, app = _fenster()
    _auswahl_an(w, app)
    try:
        knoepfe = _knoepfe(w)
    finally:
        _auswahl_aus(w, app)
    gross = [k for k in knoepfe if k.art == "gross"]
    ohne = [f"{k.register} › {k.gruppe} › {k.text} ({k.symbol!r})" for k in gross
            if not _gezeichnet(k.symbol)]
    check(f"alle {len(gross)} großen Knöpfe tragen eine gezeichnete Figur, keinen Buchstaben im Kreis",
          not ohne and len(gross) >= 70, f"{len(ohne)} ohne: " + "; ".join(ohne))
    kontext = [k for k in gross if k.register.startswith("Auswahl")]
    check("… auch die im Kontextregister „Auswahl“ (Zuweisen)",
          len(kontext) >= 4 and all(_gezeichnet(k.symbol) for k in kontext),
          str([(k.text, k.symbol) for k in kontext]))
    zuweisen = [k for k in kontext if k.text == "Zuweisen"]
    check("… „Zuweisen“ hat ein eigenes Symbol („zuweisen“)",
          len(zuweisen) == 1 and zuweisen[0].symbol == "zuweisen",
          str([k.symbol for k in zuweisen]))
    namen = {(k.register, k.text): k.symbol for k in gross}
    erwartet = {
        ("Datei", "Übernehmen"): "import",
        ("Start", "Prüfen"): "pruefen",
        ("Geometrie", "Verschieben"): "verschieben",
        ("Geometrie", "Lot / Projektion"): "lot",
        ("Lager / Kontakt", "Spalt / Toleranz"): "spalt",
        ("Berechnung", "Alle Stellungen"): "stellungen",
        ("Nachweise", "Konfiguration"): "konfiguration",
        ("Nachweise", "Verschluss"): "verschluss",
        ("Ansicht", "Einheiten"): "einheiten",
        ("Ansicht", "Fenster ▾"): "fenster",
    }
    falsch = {k: (namen.get(k), v) for k, v in erwartet.items() if namen.get(k) != v}
    check("die zehn Platzhalter der festen Leiste: jeder mit dem vorgesehenen Symbol",
          not falsch, str(falsch))


def test_fuenf_lastknoepfe():
    from statik3d.gui import symbole as sym
    w, app = _fenster()
    knoepfe = [k for k in _knoepfe(w) if k.text in LASTKNOEPFE]
    gefunden = {k.text: k.symbol for k in knoepfe}
    check("alle fünf Knöpfe gibt es (Vorspannung, Übermaß, Spiel geben, Passung, Wind)",
          set(gefunden) == set(LASTKNOEPFE), str(sorted(gefunden)))
    check("… jeder trägt sein eigenes Symbol", gefunden == LASTKNOEPFE,
          str({t: (gefunden.get(t), n) for t, n in LASTKNOEPFE.items() if gefunden.get(t) != n}))
    check("… keiner mehr das Lastsymbol „lasten“", "lasten" not in gefunden.values())
    check("… die fünf Namen sind paarweise verschieden", len(set(gefunden.values())) == 5)
    namen = sorted(LASTKNOEPFE.values())
    for groesse, mindest in ((28, 40), (16, 15)):
        bilder = {n: _bild(n, groesse) for n in namen}
        paare = [(a, b, _unterschied(bilder[a], bilder[b]))
                 for i, a in enumerate(namen) for b in namen[i + 1:]]
        kleinster = min(paare, key=lambda p: p[2])
        check(f"… ihre Bilder unterscheiden sich in {groesse} px sichtbar (je Paar mindestens "
              f"{mindest} Bildpunkte)", kleinster[2] >= mindest,
              f"kleinster Abstand {kleinster[0]}/{kleinster[1]}: {kleinster[2]} Bildpunkte")
    # und gegen das Lastsymbol, das sie vorher alle trugen
    lasten = _bild("lasten", 28)
    check("… und alle fünf anders als das frühere gemeinsame Symbol „lasten“ (28 px)",
          all(_unterschied(_bild(n, 28), lasten) >= 40 for n in namen),
          str({n: _unterschied(_bild(n, 28), lasten) for n in namen}))
    check("… jede der fünf Zeichnungen gibt es", all(sym.hat_zeichnung(n) for n in namen))


def _gezeichnete_formen(name: str) -> list:
    """Die Grundformen, die eine Vorschrift zeichnet: (art, Koordinaten)."""
    from PySide6 import QtGui
    from statik3d.gui import symbole as sym

    class Mitschrift(sym.Stift):
        def __init__(self, p, farbe, akzent):
            super().__init__(p, farbe, akzent)
            self.formen = []

        def linie(self, x1, y1, x2, y2):
            self.formen.append(("linie", (x1, y1, x2, y2)))
            super().linie(x1, y1, x2, y2)

        def pfeil(self, x1, y1, x2, y2, kopf: float = 3.2):
            # die Spitze zeichnet pfeil() mit linie(); nur der Schaft zaehlt als Pfeil
            n = len(self.formen)
            super().pfeil(x1, y1, x2, y2, kopf)
            del self.formen[n:]
            self.formen.append(("pfeil", (x1, y1, x2, y2)))

        def kreis(self, x, y, r):
            self.formen.append(("kreis", (x, y, r)))
            super().kreis(x, y, r)

    bild = QtGui.QImage(48, 48, QtGui.QImage.Format_ARGB32_Premultiplied)
    bild.fill(0)
    p = QtGui.QPainter(bild)
    p.scale(2.0, 2.0)
    s = Mitschrift(p, QtGui.QColor("#333333"), QtGui.QColor("#1565c0"))
    try:
        sym.VORSCHRIFTEN[name](s)
    finally:
        p.end()
    return s.formen


def test_stellungen_ohne_lastpfeile():
    """„Alle Stellungen“ zeigte bis zum 03.10.2026 drei Pfeile von oben auf einen
    Träger - der Anwender und die Sichtprüfung lasen das als Last. Jetzt: ein
    Teil in drei Stellungen um sein Drehlager."""
    _fenster()
    formen = _gezeichnete_formen("stellungen")
    nach_unten = [k for a, k in formen if a == "pfeil" and k[3] - k[1] > 0
                  and abs(k[2] - k[0]) < 0.3 * (k[3] - k[1])]
    check("„Alle Stellungen“ hat keinen senkrecht nach unten zeigenden Pfeil wie eine Last",
          not nach_unten, str(nach_unten))
    striche = [k for a, k in formen if a in ("linie", "pfeil")]
    anfaenge = [(round(k[0], 1), round(k[1], 1)) for k in striche]
    drehpunkt = max(set(anfaenge), key=anfaenge.count) if anfaenge else None
    stellungen = [k for k in striche if (round(k[0], 1), round(k[1], 1)) == drehpunkt]
    richtungen = {round(math.degrees(math.atan2(k[1] - k[3], k[2] - k[0]))) for k in stellungen}
    check("… drei Stellungen gehen von einem gemeinsamen Drehpunkt aus, in drei Richtungen",
          len(stellungen) >= 3 and len(richtungen) >= 3, f"{drehpunkt}: {sorted(richtungen)}")
    lager = [k for a, k in formen if a == "kreis" and drehpunkt
             and math.hypot(k[0] - drehpunkt[0], k[1] - drehpunkt[1]) < 0.6]
    check("… am Drehpunkt sitzt ein Lager (Kreis)", bool(lager), str(lager))
    lasten = _bild("lasten", 28)
    check("… und das Bild ist in 28 px deutlich anders als das Lastsymbol",
          _unterschied(_bild("stellungen", 28), lasten) >= 40,
          str(_unterschied(_bild("stellungen", 28), lasten)))


def test_falsch_geratene_symbole_korrigiert():
    w, app = _fenster()
    knoepfe = _knoepfe(w)
    nach_text = {}
    for k in knoepfe:
        nach_text.setdefault(k.text, set()).add(k.symbol)
    fehlt = [t for t in KORRIGIERT if t not in nach_text]
    check(f"alle {len(KORRIGIERT)} Knöpfe der Korrekturliste gibt es noch", not fehlt, str(fehlt))
    falsch = {t: (sorted(map(str, nach_text[t])), n) for t, n in KORRIGIERT.items()
              if t in nach_text and nach_text[t] != {n}}
    check("… jeder trägt das gewählte Symbol", not falsch, str(falsch)[:300])
    kn = nach_text.get("Knotenlager", set())
    check("Knotenlager zeigt ein Lager, nicht das Knoten-Symbol",
          kn == {"lager"} and not kn & {"knoten", "knoten_neu"}, str(kn))
    ws = nach_text.get("Werteskala", set())
    check("Werteskala zeigt eine Skala, nicht „öffnen“",
          ws == {"skala"} and "oeffnen" not in ws, str(ws))


def test_neue_zeichnungen_zeichnen():
    from statik3d.gui import symbole as sym
    fehlen = [n for n in NEUE if not sym.hat_zeichnung(n)]
    check(f"alle {len(NEUE)} neuen Zeichnungen sind in symbole.py angelegt", not fehlen, str(fehlen))
    leer, voll, anaus = [], [], []
    for n in NEUE:
        if not sym.hat_zeichnung(n):
            continue
        for g in (16, 28, 48):
            d = _deckung(_bild(n, g))
            if d < 0.04:
                leer.append(f"{n}@{g}={d:.3f}")
            if d > 0.85:
                voll.append(f"{n}@{g}={d:.2f}")
        if _unterschied(_bild(n, 28, an=False), _bild(n, 28, an=True)) == 0:
            anaus.append(n)
    check("jede neue Zeichnung zeichnet in 16, 28 und 48 px mindestens 4 % des Felds", not leer,
          "; ".join(leer[:6]))
    check("… und keine füllt das ganze Feld", not voll, "; ".join(voll[:6]))
    check("… eingeschaltet (Haken-Plakette) sieht jede anders aus als ausgeschaltet", not anaus,
          str(anaus))
    # eine Plakette (Name ohne Zeichnung) ist nie leer, aber auch keine Zeichnung -
    # Vergleich: die neuen Zeichnungen unterscheiden sich von der Plakette „?“
    plakette = _bild("gibt_es_nicht", 28)
    gleich = [n for n in NEUE if sym.hat_zeichnung(n) and _unterschied(_bild(n, 28), plakette) < 40]
    check("… und keine sieht aus wie die Buchstaben-Plakette", not gleich, str(gleich))


def test_keine_gleichen_symbole_in_einer_gruppe():
    w, app = _fenster()
    _auswahl_an(w, app)
    try:
        knoepfe = _knoepfe(w)
    finally:
        _auswahl_aus(w, app)
    je_gruppe = {}
    for k in knoepfe:
        if _gezeichnet(k.symbol):
            je_gruppe.setdefault((k.register, k.gruppe), {}).setdefault(k.symbol, []).append(k.text)
    doppelt = []
    gebraucht = set()
    for (reg, gr), d in je_gruppe.items():
        for sy, texte in d.items():
            if len(texte) > 1:
                if (reg, gr, sy) in AUSNAHMEN:
                    gebraucht.add((reg, gr, sy))
                else:
                    doppelt.append(f"{reg} › {gr}: {sy} {texte}")
    check(f"in keiner der {len(je_gruppe)} Gruppen tragen zwei verschiedene Knöpfe dasselbe Symbol "
          f"(außer {len(AUSNAHMEN)} genannten Ausnahmen)", not doppelt, "; ".join(doppelt)[:300])
    veraltet = [a for a in AUSNAHMEN if a not in gebraucht]
    check("… und jede Ausnahme gibt es noch (keine veraltete Entschuldigung)", not veraltet, str(veraltet))


def test_jeder_genannte_name_hat_eine_zeichnung():
    """Ein Befehl, dem der Quelltext einen Namen gibt (symbol=…), dessen Zeichnung
    aber fehlt, bekommt still die Plakette - so lag „fang_lot“ (Fangart auf Lot)
    bis 12b im Menue Fangarten."""
    w, app = _fenster()
    rev = _namen_der_zeichnungen()
    fehlt = []
    for b in w.ribbon.befehle:
        ic = b.aktion.icon()
        if ic.isNull():
            continue
        n = rev.get(ic.cacheKey())
        if n and not _gezeichnet(n):
            fehlt.append(f"{b.register} › {b.gruppe} › {b.text}: {n}")
    check("jeder Name, den ein Befehl im Ribbon trägt, hat eine Zeichnung", not fehlt, "; ".join(fehlt))
    knoepfe = [k for k in _knoepfe(w) if k.symbol and not _gezeichnet(k.symbol)]
    check("… auch die Knöpfe (große und kleine) mit einem Namen ohne Zeichnung gibt es nicht",
          not knoepfe, str([(k.text, k.symbol) for k in knoepfe]))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(600, exit=True)
    for t in (test_grosse_knoepfe_haben_eine_zeichnung, test_fuenf_lastknoepfe,
              test_stellungen_ohne_lastpfeile, test_falsch_geratene_symbole_korrigiert, test_neue_zeichnungen_zeichnen,
              test_keine_gleichen_symbole_in_einer_gruppe, test_jeder_genannte_name_hat_eine_zeichnung):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    sys.stdout.flush()
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
