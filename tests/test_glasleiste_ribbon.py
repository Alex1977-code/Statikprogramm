"""
Glasleiste und Ribbon passen auf den Bildschirm (Paket 7 des
Oberflaechenplans, 25.09.2026).

Befunde am Stand 562dc3a (offscreen gemessen mit Segoe UI aus
C:/Windows/Fonts, Werte in logischen Bildpunkten):

* Ribbon: das Register „Ansicht“ brauchte 3341 px, „Nachweise“ 2138 px,
  „Geometrie“ 1748, „Struktur“ 1626, „Lasten“ 1376. Bei 1366 px Fensterbreite
  standen gekuerzte Beschriftungen in fuenf Registern („Na…C3“, „F…z“),
  in „Ansicht“ 39 von 40 Knoepfen.
* Glasleiste: 1133 px breit bei 1002 px Ansicht (1920 x 1080) und 448 px
  Ansicht (1366 x 768) - „Alles deselektieren“ und die Auswahlart „Lager“
  lagen ausserhalb.
* Eingeschaltete Schalter trugen ein weisses Symbol auf hellblauem Grund
  (unsichtbar), „Berechnen“ ein blaues Dreieck auf blauem Grund.

Geprueft wird mit dem echten Hauptfenster (offscreen):

* kein Ribbon-Register kuerzt eine Beschriftung bei 1366 und 1280 px Breite
  (1280 = 1920 px bei 150 % Skalierung, dazu ein eigener Prozess mit
  QT_SCALE_FACTOR=1.5) - gemessen mit QFontMetrics; jedes Register braucht
  hoechstens 97 % der Breite (die Schrift unter Windows laeuft bis 2,9 %
  breiter als die offscreen gemessene, siehe RESERVE);
* die Registerzeile samt Kontextregister „Auswahl: 12 Knoten“ passt ohne
  Rollpfeile; die Ergebnisauswahl der Glasleiste zeigt jeden Namen der
  gerechneten Halle ganz; jeder Loeschbefehl hat einen Knopf dort, wohin die
  Suche schickt (Nachbesserung nach der Gegenpruefung, 25.09.2026);
* die Glasleiste liegt bei jeder Fensterbreite ganz in der Ansicht; was nicht
  passt, steht in der Ueberlaufliste „»“, keine Aktion geht verloren;
* Aufbau der Glasleiste (Menueknoepfe Darstellung, Zeigen, Klick waehlt),
  Ribbon „Ansicht“ und „Nachweise“ mit Menueknoepfen, rechte Maske
  „Darstellung“, doppelte Knoepfe nur noch in der Suche, sichtbares Symbol
  eingeschalteter Schalter, weisses Dreieck auf „Berechnen“, alle Kuerzel.

Aufruf:  python -m tests.test_glasleiste_ribbon
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Offscreen findet Qt unter Windows sonst keine Schrift und misst jedes Zeichen
# als Kasten: „Ansicht“ kam so auf 5460 statt 3341 px (25.09.2026). Mit den
# Schriften des Systems misst es dieselbe Segoe UI wie der Desktop.
if sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                                         "Fonts"))
# Einstellungen in eine Wegwerfdatei - die Pruefung darf die des Anwenders
# nicht ueberschreiben
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_glasleiste_"), "einstellungen.json")

RESULTS = []
_FENSTER: dict = {}

#: Anteil der Breite, den ein Register hoechstens brauchen darf. Die Breiten
#: der Analyse (Desktop, DirectWrite) lagen 0,7 bis 2,8 % ueber den
#: offscreen gemessenen (FreeType): Ansicht 3363/3341, Nachweise 2184/2138,
#: Geometrie 1760/1748, Struktur 1646/1626, Lasten 1415/1376. Die
#: Gegenpruefung (25.09.2026, Desktop bei 100 %) mass am neuen Stand bis
#: 2,9 %: Nachweise 1275/1239, Geometrie 1245/1230 - die 3 % Reserve
#: reichen knapp; bei 1280 px und 100 % bleiben dem Register 5 px Luft.
RESERVE = 0.97
#: Fenstergroessen der Abnahme: der kleine Bildschirm und 1920 px bei 150 %
BREITEN = ((1366, 768), (1280, 720))


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:74s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _ruhe(n: int = 4):
    app = _app()
    for _ in range(n):
        app.processEvents()


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = _app()
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    fehler = []
    w.error = lambda *a, **k: fehler.append(" ".join(str(x) for x in a)[:120])
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    w.load_example("hall")
    _ruhe()
    _FENSTER.update(w=w, app=app, fehler=fehler)
    return w, app


# --------------------------------------------------------------------------
# Messung: gekuerzte Beschriftungen
# --------------------------------------------------------------------------
def _textbedarf(b) -> tuple:
    """(Textbreite, Platz fuer den Text) eines Knopfs nach QFontMetrics.

    Der Stil zeichnet die Beschriftung in das Feld, das nach Rand, Innenabstand
    und Symbol bleibt; passt sie nicht, kuerzt er sie mit „…“. Den Rand liest
    die Messung aus der Wunschbreite (sizeHint = Rand + Inhalt)."""
    from PySide6 import QtCore, QtGui
    fm = QtGui.QFontMetrics(b.font())
    text = b.text().replace("&&", "&")
    tb = max((fm.horizontalAdvance(z) for z in text.split("\n")), default=0)
    stil = b.toolButtonStyle()
    ic = b.iconSize().width() if not b.icon().isNull() else 0
    if stil == QtCore.Qt.ToolButtonTextBesideIcon:
        inhalt = tb + (ic + 4 if ic else 0)
    elif stil == QtCore.Qt.ToolButtonTextUnderIcon:
        inhalt = max(tb, ic)
    else:
        inhalt = tb
    rand = b.sizeHint().width() - inhalt
    platz = b.width() - rand - (inhalt - tb)
    return tb, platz


def _gekuerzt(wurzel) -> list:
    """Alle sichtbaren Beschriftungen unter wurzel, die nicht ganz passen."""
    from PySide6 import QtCore, QtGui, QtWidgets
    aus = []
    for b in wurzel.findChildren(QtWidgets.QToolButton):
        if not b.isVisibleTo(wurzel) or not b.text() \
                or b.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly:
            continue
        tb, platz = _textbedarf(b)
        if tb > platz:
            aus.append(f"{b.text()} ({tb}>{platz})")
    for lb in wurzel.findChildren(QtWidgets.QLabel):
        if not lb.isVisibleTo(wurzel) or not lb.text() or lb.wordWrap():
            continue
        tb = QtGui.QFontMetrics(lb.font()).horizontalAdvance(lb.text())
        m = lb.contentsMargins()
        if tb > lb.width() - m.left() - m.right():
            aus.append(f"Titel {lb.text()} ({tb}>{lb.width()})")
    return aus


def _register_messen(w, app) -> list:
    """(Name, Wunschbreite, verfuegbare Breite, gekuerzte Texte) je Register.

    Gemessen wird das **aufgeklappte** Register - so, wie man es nach einem
    Klick auf den Reiter sieht. Seit Paket 5 ist das Ribbon in der
    Kompaktstufe (Fenster unter 900 px hoch, also bei 1366 x 768 und
    1280 x 720 immer) eingeklappt; gemessen wurde dann ein verborgener Stapel
    mit veralteten Breiten (Zusammenfuehrung 02.10.2026)."""
    from PySide6 import QtWidgets
    zeilen = []
    rb = w.ribbon
    war_zu = rb.eingeklappt()
    if war_zu:
        rb.einklappen(False)
        _ruhe()
    tabs = rb.tabs
    vorher = tabs.currentIndex()
    for i in range(tabs.count()):
        tabs.setCurrentIndex(i)
        _ruhe()
        reg = tabs.widget(i)
        if not reg.isVisible():
            zeilen.append((tabs.tabText(i), 10 ** 6, 1, ["Register beim Messen nicht sichtbar"]))
            continue
        zeilen.append((tabs.tabText(i), reg.sizeHint().width(), reg.width(), _gekuerzt(reg)))
    tabs.setCurrentIndex(vorher)
    if war_zu:
        rb.einklappen(True)
    _ruhe()
    return zeilen


def _schrift_ok() -> bool:
    from PySide6 import QtGui, QtWidgets
    w, _app_ = _fenster()
    knopf = w.ribbon.findChildren(QtWidgets.QToolButton)[0]
    return QtGui.QFontInfo(knopf.font()).family() == "Segoe UI"


def test_ribbon_ohne_kuerzung():
    from PySide6 import QtWidgets
    w, app = _fenster()
    if not check("Schrift wie auf dem Desktop (Segoe UI) - sonst misst die Prüfung Kästen",
                 _schrift_ok(), "QT_QPA_FONTDIR fehlt?"):
        return
    # auch das Kontextregister „Auswahl“ (erscheint mit einer Auswahl) - mit
    # zweistelliger Zahl, „Auswahl: 12 Knoten“ ist der breitere Reiter
    w._set_selection(list(range(12)))
    _ruhe()
    for breite, hoehe in BREITEN:
        w.resize(breite, hoehe)
        _ruhe()
        zeilen = _register_messen(w, app)
        zu_breit = [f"{n} {h}>{int(RESERVE * ist)}" for n, h, ist, _g in zeilen if h > RESERVE * ist]
        gekuerzt = [f"{n}: {g[:3]}" for n, _h, _ist, g in zeilen if g]
        check(f"{breite} px: kein Register braucht mehr als {RESERVE:.0%} der Breite",
              not zu_breit and len(zeilen) >= 14, "; ".join(zu_breit)[:160])
        check(f"{breite} px: keine gekürzte Beschriftung (QFontMetrics) in {len(zeilen)} Registern",
              not gekuerzt, "; ".join(gekuerzt)[:160])
        # Die Registerzeile: gekuerzt wird dort nie (ElideNone), sie laeuft
        # ueber - dann erscheinen Rollpfeile und der letzte Reiter liegt
        # dahinter. Bis 25.09.2026 stand hier „ElideNone or …“ und war damit
        # immer wahr (Befund der Gegenpruefung).
        tb = w.ribbon.tabs.tabBar()
        summe = sum(tb.tabRect(i).width() for i in range(tb.count()))
        pfeile = [k for k in tb.findChildren(QtWidgets.QToolButton) if k.isVisible()]
        check(f"{breite} px: die Registerzeile samt „{w.ribbon._kontext_name}“ passt (keine Rollpfeile, "
              f"{RESERVE:.0%})", summe <= RESERVE * tb.width() and not pfeile,
              f"Reiter {summe} px, Zeile {tb.width()} px, {len(pfeile)} Pfeile")
        print("   " + ", ".join(f"{n} {h}" for n, h, _i, _g in zeilen))
    w._set_selection([])
    _ruhe()


def test_150_prozent():
    """Eigener Prozess mit QT_SCALE_FACTOR=1.5: Fenster 1280 x 720 logisch =
    1920 x 1080 Bildpunkte. Gemessen wird dasselbe wie oben - die Schrift
    wird bei 1,5facher Aufloesung anders gerastert."""
    import subprocess
    stamm = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["QT_SCALE_FACTOR"] = "1.5"
    env["PYTHONPATH"] = stamm + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUTF8"] = "1"
    r = subprocess.run([sys.executable, "-m", "tests.test_glasleiste_ribbon", "--skaliert"],
                       cwd=stamm, env=env, capture_output=True, text=True, timeout=600,
                       encoding="utf-8", errors="replace")
    zeilen = [z for z in r.stdout.splitlines() if z.startswith("SKALIERT")]
    print("\n".join(zeilen[-6:]) or r.stdout[-800:] + r.stderr[-800:])
    ergebnis = [z for z in zeilen if z.startswith("SKALIERT ERGEBNIS")]
    check("150 % (QT_SCALE_FACTOR=1.5, 1280 px logisch): kein Register gekürzt, keines zu breit",
          r.returncode == 0 and ergebnis and ergebnis[-1].endswith("0 gekuerzt, 0 zu breit"),
          (ergebnis[-1] if ergebnis else r.stderr[-160:]))


def _skaliert_lauf():
    w, app = _fenster()
    print(f"SKALIERT dpr={app.primaryScreen().devicePixelRatio()} schrift_ok={_schrift_ok()}", flush=True)
    w.resize(1280, 720)
    _ruhe()
    zeilen = _register_messen(w, app)
    gekuerzt = [f"{n}: {g[:3]}" for n, _h, _i, g in zeilen if g]
    zu_breit = [f"{n} {h}" for n, h, ist, _g in zeilen if h > RESERVE * ist]
    for z in gekuerzt + zu_breit:
        print(f"SKALIERT {z}", flush=True)
    print(f"SKALIERT ERGEBNIS {len(zeilen)} Register, {len(gekuerzt)} gekuerzt, "
          f"{len(zu_breit)} zu breit", flush=True)
    return 0 if not gekuerzt and not zu_breit and _schrift_ok() else 1


# --------------------------------------------------------------------------
# Glasleiste
# --------------------------------------------------------------------------
def _glasaktionen(w) -> set:
    """Alle Aktionen, die die Glasleiste traegt - Knoepfe und Menues."""
    gl = w.glasleiste
    out = {id(b.defaultAction()) for b in gl.knoepfe.values() if b.defaultAction() is not None}
    out |= {id(a) for a in getattr(gl, "eintraege", {}).values()}
    return out


def _erreichbar(w) -> set:
    """Aktionen, die man in der Leiste gerade erreicht: sichtbare Knoepfe,
    ihre Menues und die Ueberlaufliste (samt Untermenues)."""
    gl = w.glasleiste

    def menue(m, aus):
        for a in m.actions():
            if a.menu() is not None:
                menue(a.menu(), aus)
            elif not a.isSeparator():
                aus.add(id(a))

    aus = set()
    for b in list(gl.knoepfe.values()) + list(getattr(gl, "menues", {}).values()):
        if b.isVisibleTo(gl):
            if b.defaultAction() is not None and b.menu() is None:
                aus.add(id(b.defaultAction()))
            if b.menu() is not None:
                menue(b.menu(), aus)
    if getattr(gl, "ueberlauf", None) is not None and gl.ueberlauf.isVisibleTo(gl):
        menue(gl.ueberlauf.menu(), aus)
    return aus


def test_glasleiste_aufbau():
    from PySide6 import QtCore, QtWidgets
    w, app = _fenster()
    w.resize(1920, 1080)
    _ruhe()
    gl = w.glasleiste
    check("Glasleiste: Menüknöpfe „Darstellung“, „Zeigen“, „Klick wählt“",
          all(k in getattr(gl, "menues", {}) for k in ("darstellung", "zeigen", "klickart")),
          str(sorted(getattr(gl, "menues", {}))))
    if not hasattr(gl, "menues") or "klickart" not in gl.menues:
        return
    men = gl.menues
    check("… „Darstellung ▾“ mit den vier Darstellungsarten (dieselben Aktionen wie das Ribbon)",
          men["darstellung"].text().startswith("Darstellung") and "▾" in men["darstellung"].text()
          and men["darstellung"].menu().actions() == list(w.act_darstellung.values()))
    zeigen = men["zeigen"].menu().actions()
    soll = [w.act_knoten, w.act_linien, w.act_staebe, w.act_flaechen, w.act_volumen,
            w.act_lager, w.act_edges, w.act_loads]
    check("… „Zeigen ▾“: Knoten, Linien, Stäbe, Flächen, Volumen, Lager, FE-Netz, Lasten",
          zeigen[:len(soll)] == soll, str([a.text() for a in zeigen]))
    check("… Lager steht im Menü zwischen Volumen und FE-Netz (wie vorher in der Leiste)",
          zeigen.index(w.act_lager) == zeigen.index(w.act_volumen) + 1
          and zeigen.index(w.act_edges) == zeigen.index(w.act_lager) + 1)
    check("… „Klick wählt: Knoten ▾“ mit allen Auswahlarten, genau eine an",
          men["klickart"].text() == f"Klick wählt: {w.auswahlart} ▾"
          and [a.text() for a in men["klickart"].menu().actions()] == list(w.AUSWAHLARTEN)
          and sum(a.isChecked() for a in men["klickart"].menu().actions()) == 1,
          men["klickart"].text())
    w.auswahlart_setzen("Lager")
    _ruhe()
    check("… die Beschriftung folgt der Auswahlart (auch aus dem Ribbon)",
          men["klickart"].text() == "Klick wählt: Lager ▾" and w.act_auswahlart["Lager"].isChecked(),
          men["klickart"].text())
    w.act_auswahlart["Stab"].trigger()
    _ruhe()
    check("… und dem Menüeintrag", w.auswahlart == "Stab" and men["klickart"].text() == "Klick wählt: Stab ▾")
    w.auswahlart_setzen("Knoten")
    alt = w.darstellung
    w.darstellung_setzen("Drahtmodell")
    _ruhe()
    bild_draht = men["darstellung"].icon().pixmap(20).toImage()
    w.darstellung_setzen("Voll")
    _ruhe()
    bild_voll = men["darstellung"].icon().pixmap(20).toImage()
    check("… das Symbol von „Darstellung ▾“ zeigt die gewählte Art", bild_draht != bild_voll)
    w.darstellung_setzen(alt)
    lay = gl.lay
    check("Reihenfolge: Index 0 die Ergebnisauswahl, Index 1 Ergebnisse an/aus",
          lay.itemAt(0).widget() is w.cb_lastwahl and lay.itemAt(1).widget() is gl.knoepfe["ergebnisse"])
    check("… „Alles deselektieren“ ganz rechts, „»“ davor",
          lay.itemAt(lay.count() - 1).widget() is gl.knoepfe["auswahl_weg"]
          and gl.ueberlauf.text() == "»"
          and lay.indexOf(gl.ueberlauf) < lay.count() - 1)
    oben = [x for x in list(gl.knoepfe.values()) + list(gl.menues.values()) if x.isVisibleTo(gl)]
    check("bei 1920 × 1080 höchstens 13 Knöpfe oben (vorher 27)",
          len(oben) + 1 <= 13, f"{len(oben)} Knöpfe + Auswahlliste")
    check("Knöpfe ohne Menü: nur Symbol, Text beim Überfahren",
          all(b.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly and not b.icon().isNull()
              and b.toolTip() for b in gl.knoepfe.values()))
    check("keine Aktion verloren: die Leiste trägt jede frühere Aktion",
          {id(a) for a in [*w.act_darstellung.values(), *soll, *w.act_auswahlart.values(),
                           w.act_nur_auswahl, w.act_auswahl_weg_sicht, w.act_sicht_zurueck,
                           w.act_alles_zeigen, w.act_geist, w.act_klug, w.act_fang,
                           w.act_auswahl_weg, w.act_ergebnisse]} <= _glasaktionen(w))


def test_glasleiste_passt():
    from PySide6 import QtWidgets
    w, app = _fenster()
    gl = w.glasleiste
    ansicht = gl.parentWidget()
    if not hasattr(gl, "ueberlauf"):
        check("Glasleiste hat eine Überlaufliste „»“", False)
    alle = _glasaktionen(w)
    fehler, stufen = [], []
    for breite, hoehe in ((1920, 1080), (1366, 768), (1280, 720), (1100, 800), (1600, 900)):
        w.resize(breite, hoehe)
        _ruhe()
        g = gl.geometry()
        drin = g.x() >= 0 and g.right() < ansicht.width()
        stufen.append(f"{breite}: Leiste {g.width()} / Ansicht {ansicht.width()}")
        if not drin:
            fehler.append(stufen[-1])
        if breite in (1920, 1366):
            check(f"{breite} px: Glasleiste ≤ Breite der Ansicht", drin, stufen[-1])
        if hasattr(gl, "ueberlauf"):
            erreichbar = _erreichbar(w)
            if not alle <= erreichbar:
                fehler.append(f"{breite}: {len(alle - erreichbar)} Aktionen nicht erreichbar")
            versteckt = [b for b in gl.knoepfe.values() if not b.isVisibleTo(gl)]
            if bool(versteckt) != gl.ueberlauf.isVisibleTo(gl):
                fehler.append(f"{breite}: »-Knopf {gl.ueberlauf.isVisibleTo(gl)} bei {len(versteckt)} versteckten")
    print("   " + "; ".join(stufen))
    check("bei jeder Fensterbreite: Leiste in der Ansicht, alles erreichbar, „»“ nur bei Bedarf",
          not fehler, "; ".join(fehler)[:160])
    # schmale Ansicht unmittelbar (Leiste und Ansicht allein, unabhaengig von
    # der Fensteraufteilung): 900 .. 220 px
    if hasattr(gl, "einpassen"):
        schmal = []
        # ohne Ereignisschleife dazwischen: sonst passt die Leiste sich gleich
        # wieder an die wirkliche Ansicht an (Layoutanfrage -> nachziehen)
        for b in range(900, 219, -40):
            gl.einpassen(b - 24)
            if gl.sizeHint().width() > b - 24 and b >= 260:
                schmal.append(f"{b}: {gl.sizeHint().width()}")
            if not alle <= _erreichbar(w):
                schmal.append(f"{b}: nicht alles erreichbar")
        check("Ansicht 900 … 260 px: die Leiste passt immer hinein (Rand 12 px je Seite)",
              not schmal, "; ".join(schmal)[:160])
        gl.einpassen(ansicht.width() - 24)
    w.resize(1920, 1080)
    _ruhe()


# --------------------------------------------------------------------------
# Ribbon Ansicht und Nachweise, Maske Darstellung
# --------------------------------------------------------------------------
def _ribbonknopf(w, register: str, anfang: str):
    from PySide6 import QtWidgets
    reg = w.ribbon._register[register]
    for b in reg.findChildren(QtWidgets.QToolButton):
        if b.text().startswith(anfang):
            return b
    return None


def test_ribbon_ansicht():
    from PySide6 import QtWidgets
    w, app = _fenster()
    anz = _ribbonknopf(w, "Ansicht", "Anzeigen")
    check("Ansicht: „Anzeigen ▾“ ist ein Menüknopf mit allen Anzeigeschaltern",
          anz is not None and anz.menu() is not None
          and {w.act_edges, w.act_knoten, w.act_linien, w.act_staebe, w.act_flaechen, w.act_volumen,
               w.act_lager, w.act_lagertext, w.act_loads, w.act_lastwerte, w.act_members}
          <= set(anz.menu().actions()))
    num = _ribbonknopf(w, "Ansicht", "Nummern")
    check("Ansicht: „Nummern ▾“ ist ein Menüknopf mit einem Schalter je Objektart",
          num is not None and num.menu() is not None
          and set(w.act_nummern.values()) <= set(num.menu().actions()))
    reg = w.ribbon._register["Ansicht"]
    check("Ansicht: keine Schieber mehr im Ribbon (Symbolgröße und Lagerdichte rechts)",
          not reg.findChildren(QtWidgets.QSlider) or
          all(s is getattr(w, "sl_schnitt", None) for s in reg.findChildren(QtWidgets.QSlider)),
          str([s.toolTip()[:20] for s in reg.findChildren(QtWidgets.QSlider)]))
    befehl = [b for b in w.ribbon.befehle if b.register == "Ansicht" and b.text.startswith("Symbolgrößen")]
    check("Befehl „Symbolgrößen…“ im Register Ansicht", len(befehl) == 1)
    if not befehl:
        return
    befehl[0].aktion.trigger()
    _ruhe()
    titel = w.eingaben_dock.windowTitle()
    check("… öffnet rechts die Maske „Darstellung“", titel == "Darstellung", titel)
    dock = w.eingaben_dock.widget()
    schieber = [s for s in dock.findChildren(QtWidgets.QSlider) if s.isVisibleTo(dock)]
    check("… mit den Schiebern Lagergröße und Lagerdichte", len(schieber) == 2, str(len(schieber)))
    if len(schieber) == 2:
        groesse, dichte = schieber
        groesse.setValue(25)
        _ruhe()
        check("… Schieber Größe wirkt sofort (2,5) und zieht den Ribbon-Stand mit",
              abs(w.lagergroesse - 2.5) < 1e-9 and w.sl_lager.value() == 25, f"{w.lagergroesse}")
        dichte.setValue(30)
        _ruhe()
        check("… Schieber Dichte wirkt sofort (3,0)", abs(w.lagerdichte - 3.0) < 1e-9, f"{w.lagerdichte}")
        w.lagerdichte_zuruecksetzen()
        w.lagergroesse_zuruecksetzen()
        _ruhe()
        check("… Zurücksetzen stellt auch die Schieber der Maske zurück",
              dichte.value() == 10 and groesse.value() == 10 and w.lagerdichte == 1.0,
              f"{groesse.value()} {dichte.value()}")
    for text in ("Lagergröße zurücksetzen", "Lagerdichte zurücksetzen"):
        check(f"„{text}“ findet die Suche weiter", bool(w.ribbon.finden(text)))
    if w.maskenrand.offen():
        w.maskenrand.schliessen()
    _ruhe()


#: Nachweisobjekt -> (Knopfbeschriftung, Tabelle unten, Namen in der Suche)
NACHWEISOBJEKTE = {
    "Verformung": ("Verformungen", ("Verformung", "Grenze ändern…", "Grenze löschen",
                                     "Tabelle Verformungen")),
    "Beulfeld": ("Beulfelder", ("Beulfeld", "Beulfeld ändern…", "Beulfeld löschen",
                                "Tabelle Beulfelder")),
    "Volumenbereich": ("Volumen", ("Volumenbereich", "Volumenbereich ändern…",
                                   "Volumenbereich löschen", "Tabelle Volumen")),
    "Lasteinleitung": ("Lasteinleitung", ("Lasteinleitung", "Lasteinleitung ändern…",
                                          "Lasteinleitung löschen", "Tabelle Lasteinleitung")),
}


def test_ribbon_nachweise():
    w, app = _fenster()
    for objekt, (tabelle, namen) in NACHWEISOBJEKTE.items():
        b = _ribbonknopf(w, "Nachweise", objekt)
        texte = [a.text() for a in b.menu().actions() if not a.isSeparator()] \
            if b is not None and b.menu() is not None else []
        check(f"Nachweise: großer Knopf „{objekt} ▾“ mit Neu | Ändern | Löschen | Tabelle",
              texte == ["Neu …", "Ändern …", "Löschen", "Tabelle"] and "▾" in b.text(), str(texte))
        if texte:
            gefunden = [w.ribbon.finden(n) for n in namen]
            check(f"… die Suche findet sie unter ihren Namen ({namen[1]})",
                  all(g and g[0].text == n for g, n in zip(gefunden, namen)))
            b.menu().actions()[-1].trigger()
            _ruhe()
            check(f"… „Tabelle“ holt unten „{tabelle}“ nach vorn",
                  w.tab_unten.tabText(w.tab_unten.currentIndex()) == tabelle,
                  w.tab_unten.tabText(w.tab_unten.currentIndex()))


#: Knoepfe, die aus dem Ribbon fallen: die Suche findet sie weiter
DOPPELT = ["Tabelle Gelenke", "Tabelle Anschlüsse", "Tabelle Lasten", "Tabelle Knicklängen",
           "Tabelle Schwingung", "Flächen vernetzen", "Volumen vernetzen",
           "Querschnitt zuweisen…", "Dicke zuweisen…", "Gelenke setzen…"]


def test_doppelte_knoepfe():
    from PySide6 import QtWidgets
    w, app = _fenster()
    w._set_selection([])
    _ruhe()
    texte = {b.text() for r in w.ribbon._register.values()
             for b in r.findChildren(QtWidgets.QToolButton)}
    noch = [t for t in DOPPELT if t in texte]
    check("doppelte Knöpfe („Tabelle …“, Vernetzen in Struktur, Zuweisen) nicht mehr im Ribbon",
          not noch, str(noch))
    fehlt = [t for t in DOPPELT if not any(b.text == t for b in w.ribbon.finden(t))]
    check("… die Befehlssuche findet jeden weiter", not fehlt, str(fehlt))
    w.ribbon.suche.setText("Tabelle Gelenke")
    w.ribbon._suche_ausfuehren()
    _ruhe()
    check("… und führt ihn aus („Tabelle Gelenke“ holt die Tabelle)",
          w.tab_unten.tabText(w.tab_unten.currentIndex()) == "Gelenke",
          w.tab_unten.tabText(w.tab_unten.currentIndex()))


def test_kuerzel_bleiben():
    from PySide6 import QtGui
    w, app = _fenster()
    soll = {"Ctrl+1": w.act_darstellung[list(w.act_darstellung)[0]], "F9": w.act_edges,
            "F3": w.act_fang, "Shift+F1": w.act_fangart["knoten"], "Shift+F7": w.act_fangart["volumen"],
            "Esc": w.act_auswahl_weg, "F5": w.act_rechnen}
    falsch = [k for k, a in soll.items() if a.shortcut() != QtGui.QKeySequence(k)]
    check("Kürzel unverändert (Strg+1, F9, F3, Umschalt+F1/F7, Esc, F5)", not falsch, str(falsch))
    folgen = [b.aktion.shortcut().toString() for b in w.ribbon.befehle
              if not b.aktion.shortcut().isEmpty()]
    doppelt = sorted({f for f in folgen if folgen.count(f) > 1})
    check("kein Kürzel doppelt belegt", not doppelt, str(doppelt))
    check("jede Aktion mit Kürzel hängt am Fenster (wirkt auch aus einem Menü)",
          all(a in w.actions() for a in soll.values()))


# --------------------------------------------------------------------------
# Symbole: eingeschaltete Schalter, Berechnen
# --------------------------------------------------------------------------
def _hell(c) -> float:
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()


def _deckung(bild, grund) -> float:
    """Mittlerer Helligkeitsabstand der gezeichneten Bildpunkte zum Grund."""
    summe = n = 0
    for y in range(bild.height()):
        for x in range(bild.width()):
            c = bild.pixelColor(x, y)
            if c.alpha() > 128:
                summe += abs(_hell(c) - _hell(grund))
                n += 1
    return summe / n if n else 0.0


def test_schalter_sichtbar():
    from PySide6 import QtGui
    from statik3d.gui import design as dsg
    w, app = _fenster()
    grund = QtGui.QColor(dsg.FARBEN["akzent_hell"])
    proben = {"FE-Netz": w.act_edges, "Fang": w.act_fang, "Lager": w.act_lager,
              "Kennwerte im Bild": w.act_kennwerte}
    for name, a in proben.items():
        ic = a.icon()
        an = ic.pixmap(QtCore_size(16), QtGui.QIcon.Normal, QtGui.QIcon.On).toImage()
        aus = ic.pixmap(QtCore_size(16), QtGui.QIcon.Normal, QtGui.QIcon.Off).toImage()
        d = _deckung(an, grund)
        check(f"„{name}“ eingeschaltet: Symbol hebt sich vom hellblauen Grund ab und trägt einen Haken",
              d > 0.25 and an != aus and _haken(an), f"Abstand {d:.2f}")


def QtCore_size(n):
    from PySide6 import QtCore
    return QtCore.QSize(n, n)


def _haken(bild) -> bool:
    """Unten rechts sitzt die Plakette: akzentblaue Scheibe mit weissem Haken."""
    from PySide6 import QtGui
    from statik3d.gui import design as dsg
    ak = QtGui.QColor(dsg.FARBEN["akzent"])
    b, h = bild.width(), bild.height()
    blau = weiss = 0
    for y in range(int(h * 0.6), h):
        for x in range(int(b * 0.6), b):
            c = bild.pixelColor(x, y)
            if c.alpha() < 200:
                continue
            if abs(c.red() - ak.red()) + abs(c.green() - ak.green()) + abs(c.blue() - ak.blue()) < 60:
                blau += 1
            elif min(c.red(), c.green(), c.blue()) > 225:
                weiss += 1
    return blau >= 3 and weiss >= 1


def test_berechnen_weiss():
    from PySide6 import QtWidgets
    w, app = _fenster()
    knoepfe = [b for b in w.ribbon.findChildren(QtWidgets.QToolButton)
               if b.defaultAction() is w.act_rechnen and b.property("rolle") == "start"]
    check("„Berechnen“: zwei blaue Startknöpfe (Start, Berechnung)", len(knoepfe) == 2, str(len(knoepfe)))
    for b in knoepfe:
        bild = b.icon().pixmap(QtCore_size(28)).toImage()
        mitte = bild.pixelColor(bild.width() // 2, bild.height() // 2)
        check("… mit weißem Dreieck", mitte.alpha() > 200 and min(mitte.red(), mitte.green(), mitte.blue()) > 230,
              f"RGB {mitte.red()},{mitte.green()},{mitte.blue()} A {mitte.alpha()}")
    w.act_rechnen.setEnabled(False)
    w.act_rechnen.setEnabled(True)
    _ruhe()
    bild = knoepfe[0].icon().pixmap(QtCore_size(28)).toImage() if knoepfe else None
    mitte = bild.pixelColor(bild.width() // 2, bild.height() // 2) if bild is not None else None
    check("… auch nachdem die Aktion gesperrt und wieder frei war",
          mitte is not None and min(mitte.red(), mitte.green(), mitte.blue()) > 230)
    sz = w.act_rechnen.icon().pixmap(QtCore_size(18)).toImage()
    m2 = sz.pixelColor(sz.width() // 2, sz.height() // 2)
    check("im Schnellzugriff (heller Grund) bleibt das Dreieck blau",
          m2.alpha() > 200 and m2.blue() > m2.red() + 60, f"RGB {m2.red()},{m2.green()},{m2.blue()}")


# --------------------------------------------------------------------------
# Nachbesserung nach der Gegenpruefung (25.09.2026)
# --------------------------------------------------------------------------
def _listenfeld(cb) -> int:
    """Breite des Textfelds einer Aufklappliste - dort, wo der Stil den
    gewaehlten Namen hinschreibt (ohne Pfeil und Rand)."""
    from PySide6 import QtWidgets
    opt = QtWidgets.QStyleOptionComboBox()
    cb.initStyleOption(opt)
    return cb.style().subControlRect(QtWidgets.QStyle.CC_ComboBox, opt,
                                     QtWidgets.QStyle.SC_ComboBoxEditField, cb).width()


def _abgeschnitten(cb) -> list:
    """Die waehlbaren Eintraege, die im Textfeld nicht ganz Platz haben."""
    from PySide6 import QtGui
    fm = QtGui.QFontMetrics(cb.font())
    feld = _listenfeld(cb)
    return [cb.itemText(i) for i in range(cb.count())
            if cb.itemData(i) is not None and fm.horizontalAdvance(cb.itemText(i)) > feld]


def test_ergebnisliste_lesbar():
    """Befund der Gegenpruefung: bei 1366 und 1536 px blieb die Liste nach dem
    Weichen der Hauptknoepfe bei 120 px, 75 von 81 Namen der gerechneten Halle
    waren abgeschnitten („Kombination GZ“), obwohl daneben Platz frei war."""
    from statik3d import solver
    w, app = _fenster()
    gl = w.glasleiste
    an = solver.solve_all(w.model, design=bool(w.model.members))
    w._solve_done("all", an)
    _ruhe()
    cb = w.cb_lastwahl
    n = sum(1 for i in range(cb.count()) if cb.itemData(i) is not None)
    check("gerechnete Halle: die Ergebnisauswahl führt Lastfälle und Kombinationen",
          n >= 40, f"{n} Einträge")
    for breite, hoehe in ((1366, 768), (1536, 864), (1920, 1080)):
        w.resize(breite, hoehe)
        _ruhe()
        weg = _abgeschnitten(cb)
        g = gl.geometry()
        check(f"{breite} px: kein Name der Ergebnisauswahl abgeschnitten",
              not weg and g.right() < gl.parentWidget().width(),
              f"Liste {cb.width()} px, Feld {_listenfeld(cb)} px, {len(weg)} von {n}: {weg[:2]}")
    w.resize(1920, 1080)
    _ruhe()


def test_klickart_im_ueberlauf():
    """Befund der Gegenpruefung: in „»“ stand „Klick wählt: Knoten“, auch wenn
    eine andere Auswahlart galt - das Untermenue behielt seinen ersten Titel."""
    w, app = _fenster()
    gl = w.glasleiste
    w.resize(1366, 768)
    _ruhe()
    w.auswahlart_setzen("Lager")
    _ruhe()
    menue = gl.menues["klickart"].menu()
    check("„Klick wählt“: das Menü heißt wie der Knopf („Klick wählt: Lager“)",
          menue.title() == "Klick wählt: Lager", menue.title())
    # wo der Knopf in „»“ steht, ist der Untermenuetitel die Anzeige
    gl.einpassen(300)
    titel = [a.text() for a in gl.ueberlauf.menu().actions() if a.menu() is menue]
    check("… und so steht es in der Überlaufliste „»“",
          titel == ["Klick wählt: Lager"], str(titel))
    w.auswahlart_setzen("Knoten")
    _ruhe()
    check("… nach dem Zurückstellen wieder „Klick wählt: Knoten“",
          menue.title() == "Klick wählt: Knoten", menue.title())
    gl.einpassen(gl.parentWidget().width() - 2 * gl.RAND)
    w.resize(1920, 1080)
    _ruhe()


def _traegt(knopf, aktion) -> bool:
    """Fuehrt dieser Knopf die Aktion - selbst oder in seinem Menue?"""
    if knopf.defaultAction() is aktion:
        return True
    stapel = [knopf.menu()] if knopf.menu() is not None else []
    while stapel:
        m = stapel.pop()
        for a in m.actions():
            if a is aktion:
                return True
            if a.menu() is not None:
                stapel.append(a.menu())
    return False


def test_loeschbefehle_haben_einen_knopf():
    """Befund der Gegenpruefung: „Elemente löschen“ stand nur noch in der
    Suche. Die Suche fuehrt Befehle mit Loeschwort aber nie aus, sondern nennt
    den Knopf in Register › Gruppe - den es dann nicht gab."""
    from PySide6 import QtWidgets
    w, app = _fenster()
    w._set_selection([0, 1])        # das Kontextregister „Auswahl“ ist dann da
    _ruhe()
    ohne = []
    for b in w.ribbon.befehle:
        if not b.nicht_aus_suche():
            continue
        reg = w.ribbon._register.get(b.register)
        if reg is None and b.register == w.ribbon._kontext_name:
            reg = w.ribbon._kontext
        knoepfe = reg.findChildren(QtWidgets.QToolButton) if reg is not None else []
        if not any(k.isVisibleTo(reg) and _traegt(k, b.aktion) for k in knoepfe):
            ohne.append(f"{b.text} ({b.register} › {b.gruppe})")
    check("jeder Befehl, den die Suche nicht ausführt, hat im genannten Register einen Knopf",
          not ohne, "; ".join(ohne)[:160])
    w._set_selection([])
    _ruhe()
    # die Zeile „Elemente löschen (Struktur › Eigenschaften)“ der Trefferliste
    meldungen = []
    w.ribbon.meldung.connect(meldungen.append)
    for b in w.ribbon.befehle:
        if b.text == "Elemente löschen":
            w.ribbon._ausfuehren(b)
    _ruhe()
    w.ribbon.meldung.disconnect(meldungen.append)
    reg = w.ribbon._register["Struktur"]
    da = [k for k in reg.findChildren(QtWidgets.QToolButton)
          if k.isVisibleTo(reg) and k.text() == "Elemente löschen"]
    check("„Elemente löschen“ aus der Suche: Meldung nennt Struktur › Eigenschaften, dort steht der Knopf",
          any("Struktur › Eigenschaften" in m for m in meldungen) and len(da) == 1,
          f"{meldungen[-1:]} Knopf {len(da)}")


def test_gelenkhinweise():
    """Befund der Gegenpruefung: zwei Hinweise nannten „Gelenke setzen“ im
    Register Struktur - den Knopf gibt es dort nicht mehr."""
    import inspect
    from statik3d.gui import design, main as hauptmodul
    alt = "„Gelenke setzen“ im Register Struktur"
    texte = inspect.getsource(hauptmodul) + inspect.getsource(design)
    check("kein Hinweis schickt mehr zu „Gelenke setzen“ im Register Struktur",
          alt not in texte and "Register Struktur → Gelenke setzen" not in texte)


def test_handbuch():
    stamm = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(stamm, "docs", "Benutzerhandbuch.md"), encoding="utf-8") as f:
        t = f.read()
    check("Handbuch: Glasleiste mit „»“ und den Menüknöpfen",
          "Überlaufliste „»“" in t and "Klick wählt" in t and "Zeigen ▾" in t)
    check("Handbuch: Maske „Darstellung“ für Symbolgrößen und Lagerdichte",
          "Maske „Darstellung“" in t and "Symbolgrößen" in t)
    check("Handbuch: Nachweisobjekte mit Neu | Ändern | Löschen | Tabelle",
          "Neu | Ändern | Löschen | Tabelle" in t)
    check("Handbuch: eingeschaltete Schalter tragen einen Haken",
          "Eingeschaltete Schalter tragen einen Haken" in t and "ein weißes\nDreieck" in t)
    check("Handbuch: Nachbesserung 25.09. (Liste wächst zurück, „Klick wählt: Lager“ in „»“, "
          "Elemente löschen, Registerzeile)",
          "bekommt die Ergebnisauswahl zurück" in t and "„Klick wählt: Lager“" in t
          and "*Elemente\nlöschen* bleibt ein Knopf" in t and "**Die Registerzeile passt**" in t
          and "braucht mehr als 1240 px" not in t)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    if "--skaliert" in sys.argv:
        return _skaliert_lauf()
    for t in (test_ribbon_ohne_kuerzung, test_150_prozent, test_glasleiste_aufbau,
              test_glasleiste_passt, test_ribbon_ansicht, test_ribbon_nachweise,
              test_doppelte_knoepfe, test_kuerzel_bleiben, test_schalter_sichtbar,
              test_berechnen_weiss, test_klickart_im_ueberlauf, test_loeschbefehle_haben_einen_knopf,
              test_gelenkhinweise, test_ergebnisliste_lesbar, test_handbuch):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
