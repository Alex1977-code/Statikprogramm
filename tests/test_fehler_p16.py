"""
Fehlerliste 06.10.2026, Paket P16 (Masken): F40 und F44.

F40 - Der Fussknopf „Schlupf, Reibung, Grenzkraft …“ der Lagermaske war im
rechten Bereich abgeschnitten. Die drei Zusatzknoepfe stehen in einer Zeile
ohne Umbruch; mit Segoe UI braucht der Knopf 211 px (sizeHint) und bekam
160 px, bei 1920 x 1000 und bei 1366 x 740 gleich (Maske 460 px breit). Der
Knopf heisst jetzt „Schlupf, Reibung …“ und nennt im Hinweis alles. Geprueft
wird mit nachgeladener Schrift: offscreen kennt Qt sonst keine und misst
Kaestchen, etwa doppelt so breit; ohne Segoe UI entfaellt die Breitenpruefung.

F44 - Masken, die ueber ✕ oder „Abbrechen“ zugingen, wurden nur versteckt
(Maske.schliessen) und vom Maskenrand vergessen, nie geloescht: nach dem
Abarbeiten aller vorgemerkten Loeschungen lebten 3 von 3 Masken weiter, samt
ihren Verbindungen, unsichtbar im rechten Bereich. Eine ersetzte Maske geht
dagegen ueber Maskenrand.schliessen weg (removeWidget, hide, geschlossen,
deleteLater). Jetzt nimmt der Rand eine selbst geschlossene Maske auf
demselben Weg heraus und entsorgt sie ueber deleteLater - nichts getrennt,
geschlossen genau einmal. Esc schliesst im Programmfenster keine Maske (das
Kuerzel heisst „Alles deselektieren“); das bleibt, ebenso das Ersetzen.
Was mit der Maske endet - Auswahl per Maus, Vorschau einer Stellung, die Ebene
im Bild, die Leiste „Übernehmen | Verwerfen“ -, endet auch ueber ✕.

Aufruf:  python -m tests.test_fehler_p16
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_UNGESPEICHERT"] = "verwerfen"
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_fehler_p16_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
#: Ausnahmen, die waehrend der Pruefung ueber sys.excepthook liefen
AUSNAHMEN = []

#: Schriften wie scratchpad/mit_schrift.py (Beleg der Fehlerliste)
SCHRIFTEN = ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "segoeuii.ttf", "segoeuil.ttf",
             "seguisym.ttf", "arial.ttf", "consola.ttf", "cour.ttf")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def _app():
    from PySide6 import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _schrift_laden() -> bool:
    """Segoe UI und verwandte Schriften nachladen (vor dem Fenster). True,
    wenn danach Segoe UI bekannt ist."""
    from PySide6 import QtGui
    _app()
    for f in SCHRIFTEN:
        pfad = os.path.join("C:/Windows/Fonts", f)
        if os.path.exists(pfad):
            QtGui.QFontDatabase.addApplicationFont(pfad)
    return "Segoe UI" in QtGui.QFontDatabase.families()


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    app = _app()
    _FENSTER["schrift"] = _schrift_laden()
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    w = MainWindow()
    w.resize(1600, 1000)
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    w._bestaetigen = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste)
    mb = QtWidgets.QMessageBox
    for name in ("critical", "warning", "information"):
        setattr(mb, name, staticmethod(lambda *a, **k: mb.StandardButton.Ok))
    mb.question = staticmethod(lambda *a, **k: mb.StandardButton.No)
    alt = sys.excepthook

    def haken(t, v, tb):
        AUSNAHMEN.append(f"{t.__name__}: {v}")
        alt(t, v, tb)
    sys.excepthook = haken
    _FENSTER.update(w=w, app=app)
    return w, app


def _ruhe(app, n=3):
    for _ in range(n):
        app.processEvents()


def _loeschungen(app):
    """Alle vorgemerkten Loeschungen ausfuehren - das, was die
    Ereignisschleife des Programms tut (in einer Pruefung laeuft keine)."""
    from PySide6 import QtCore
    for _ in range(3):
        app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        app.processEvents()


def _leben(masken) -> int:
    import shiboken6
    return sum(1 for m in masken if shiboken6.isValid(m))


def _zaehler():
    """Ein Empfaenger mit Methoden statt Lambdas (Regel aus C15)."""
    from PySide6 import QtCore

    class Zaehler(QtCore.QObject):
        def __init__(self):
            super().__init__()
            self.folge = []

        def geschlossen(self):
            self.folge.append("geschlossen")

        def abgebrochen(self):
            self.folge.append("abgebrochen")
    z = Zaehler()
    _FENSTER.setdefault("zaehler", []).append(z)
    return z


def _rahmen(w):
    """Ein kleines Modell: zwei Staebe S1, S2, ein Lager am Knoten 0."""
    from statik3d.model import Material, Section, Member
    w.new_model()
    m = w.model
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 200"))
    n = [m.add_node(3.0 * i, 0.0, 0.0) for i in range(3)]
    e0 = m.add_element("beam", [n[0], n[1]], "S355", "HEB 200")
    e1 = m.add_element("beam", [n[1], n[2]], "S355", "HEB 200")
    m.members["S1"] = Member("S1", [e0])
    m.members["S2"] = Member("S2", [e1])
    m.fix(n[0], "all")
    return m


def _ebenenwerkzeuge(w) -> list:
    """Die Ebenen-Werkzeuge im Bild (PyVista: Plotter.widgets.plane_widgets,
    aeltere Fassungen Plotter.plane_widgets)."""
    halter = getattr(w.plotter, "widgets", None)
    liste = getattr(halter, "plane_widgets", None) if halter is not None else None
    if liste is None:
        liste = getattr(w.plotter, "plane_widgets", None)
    return list(liste or [])


def _masken_im_fenster(w) -> list:
    """Alle Masken unter dem Fenster ausser der offenen (lebende Objekte)."""
    from statik3d.gui import masken as msk
    from statik3d.gui.profilmaske import QuerschnittMaske
    offen = w.maskenrand.maske
    return [x for x in w.findChildren(msk.Maske) + w.findChildren(QuerschnittMaske) if x is not offen]


# ---------------------------------------------------------------- F40 ----
def test_f40_lagerknopf():
    w, app = _fenster()
    _rahmen(w)
    w.refresh_all()
    _ruhe(app)
    schrift = _FENSTER.get("schrift")
    print(f"     {'mit Segoe UI' if schrift else 'ohne Segoe UI - Breiten wären Kästchenwerte'}")
    for breite, hoehe in ((1920, 1000), (1366, 740)):
        w.resize(breite, hoehe)
        _ruhe(app)
        w._objektmaske("lager_einzeln", "0")
        _ruhe(app)
        mk = w.maskenrand.maske
        if mk is None or not getattr(mk, "zusatzknoepfe", None):
            check(f"{breite}: Lagermaske mit Zusatzknöpfen offen", False, repr(mk))
            continue
        zeilen = [f"„{t}“ {b.width()}/{b.sizeHint().width()} px" for t, b in mk.zusatzknoepfe.items()]
        if schrift:
            ab = [t for t, b in mk.zusatzknoepfe.items() if b.width() < b.sizeHint().width()]
            check(f"{breite} x {hoehe}: kein Fußknopf der Lagermaske abgeschnitten (Breite ≥ sizeHint)",
                  not ab, f"Maske {mk.width()} px: " + "; ".join(zeilen))
        else:
            print("--   Breitenprüfung entfällt: Segoe UI fehlt (Kästchenwerte: " + "; ".join(zeilen) + ")")
        w.maskenrand.schliessen()
        _ruhe(app)
    w.resize(1600, 1000)
    _ruhe(app)

    w._objektmaske("lager_einzeln", "0")
    _ruhe(app)
    mk = w.maskenrand.maske
    knoepfe = dict(getattr(mk, "zusatzknoepfe", {}) or {})
    nl = [b for t, b in knoepfe.items() if t.startswith("Schlupf, Reibung")]
    check("der Knopf für Schlupf, Reibung und Grenzkraft ist da (mit „…“ für den Dialog)",
          len(nl) == 1 and nl[0].text().endswith("…"), str(list(knoepfe)))
    if not nl:
        return
    b = nl[0]
    tip = b.toolTip()
    check("… sein Hinweis nennt alles: Schlupf, Reibung und Grenzkraft je Freiheitsgrad",
          all(x in tip for x in ("Schlupf", "Reibung", "Grenzkraft", "Freiheitsgrad")), repr(tip))
    check("… die anderen Zusatzknöpfe bleiben, wie sie waren",
          {"Bettung übernehmen", "Lager löschen"} <= set(knoepfe) and len(knoepfe) == 3, str(list(knoepfe)))
    gerufen = []
    w._lager_nichtlinear = lambda art, i: gerufen.append((art, i))
    try:
        b.click()
        _ruhe(app)
    finally:
        del w._lager_nichtlinear
    check("… und öffnet weiter den Dialog dieses Lagers", gerufen == [("lager_einzeln", 0)], str(gerufen))
    w.maskenrand.schliessen()
    _loeschungen(app)


def test_f40_handbuch():
    from tests.handbuch import absatz
    t = absatz("Jedes Lager wirkt je Freiheitsgrad")
    check("Handbuch: der Knopf heißt „Schlupf, Reibung …“, früher abgeschnitten",
          "„Schlupf, Reibung …“" in t and "Bis zum 06.10.2026" in t and "abgeschnitten" in t, t[:80])


# ---------------------------------------------------------------- F44 ----
def test_f44_maskenrand_fuer_sich():
    """Der Maskenrand ohne Hauptfenster (laeuft vor dem Fenster: dessen
    Kuerzel „Alles deselektieren“ gilt in der ganzen Anwendung und naehme jedes
    Esc). Esc an der Maske selbst (Maske.keyPressEvent -> schliessen) geht
    denselben Weg wie ✕ - im Ziel und schwebend. Oeffnet ein Empfaenger von
    ``geschlossen`` waehrend des Schliessens schon die naechste Maske, bleibt
    diese offen."""
    from PySide6 import QtCore, QtGui, QtWidgets
    from statik3d.gui import masken as msk
    app = _app()
    for mit_ziel in (True, False):
        ansicht = QtWidgets.QWidget()
        _FENSTER.setdefault("behalten", []).append(ansicht)
        rand = msk.Maskenrand(ansicht, QtWidgets.QVBoxLayout(ansicht) if mit_ziel else None)
        mk = rand.zeigen(msk.Maske("Für sich", [msk.Feld("x", "x", "zahl", 1.0)]))
        _ruhe(app)
        QtWidgets.QApplication.sendEvent(mk, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape,
                                                             QtCore.Qt.NoModifier))
        # gleich danach: im Ereignis vorgemerkt, loescht schon das naechste
        # processEvents die Maske (wie ein echter Klick auf ✕ im Programm)
        zu = rand.maske is None and mk.isHidden()
        _ruhe(app)
        _loeschungen(app)
        check(f"Esc an der Maske selbst ({'im Ziel' if mit_ziel else 'schwebend'}, ohne Fenster): "
              "sie geht weg wie mit ✕", zu and _leben([mk]) == 0, f"zu {zu}, lebt {_leben([mk])}")

    class Folge(QtCore.QObject):
        """Oeffnet beim Schliessen der ersten Maske die zweite (vor dem Rand verbunden)."""
        def __init__(self, rand_):
            super().__init__()
            self.rand, self.zweite, self.n = rand_, None, 0

        def weiter(self):
            # nur einmal: das Ersetzen meldet die erste dabei noch einmal zu
            self.n += 1
            if self.n == 1:
                self.zweite = self.rand.zeigen(msk.Maske("Zweite", []))
    ansicht = QtWidgets.QWidget()
    _FENSTER.setdefault("behalten", []).append(ansicht)
    rand = msk.Maskenrand(ansicht, QtWidgets.QVBoxLayout(ansicht))
    folge = Folge(rand)
    _FENSTER["behalten"].append(folge)
    erste = msk.Maske("Erste", [])
    erste.geschlossen.connect(folge.weiter)
    rand.zeigen(erste)
    _ruhe(app)
    erste.btn_zu.click()
    _ruhe(app)
    _loeschungen(app)
    rest = [x.titel for x in ansicht.findChildren(msk.Maske)]
    check("eine Maske, die beim Schließen die nächste öffnen lässt: die nächste bleibt offen und lebt",
          folge.zweite is not None and rand.maske is folge.zweite and _leben([folge.zweite]) == 1
          and _leben([erste]) == 0 and rest == ["Zweite"],
          f"offen {getattr(rand.maske, 'titel', None)!r}, erste lebt {_leben([erste])}, unter der Ansicht {rest}")


def test_f44_kreuz():
    """✕: die Maske geht ganz weg, geschlossen kommt genau einmal."""
    w, app = _fenster()
    _rahmen(w)
    w.refresh_all()
    _ruhe(app)
    _loeschungen(app)
    masken, z = [], _zaehler()
    for _ in range(3):
        w.maske_knoten()
        _ruhe(app)
        mk = w.maskenrand.maske
        masken.append(mk)
        mk.geschlossen.connect(z.geschlossen)
        mk.btn_zu.click()
        _ruhe(app)
    imbereich = sum(1 for mk in masken if w.maskenplatz.indexOf(mk) >= 0)
    check("✕: rechts ist danach nichts offen, die Masken stehen nicht mehr im rechten Bereich",
          w.maskenrand.maske is None and not w.maskenrand.offen() and imbereich == 0
          and w.rechts_zeigt() == "leer", f"im Bereich {imbereich}, rechts {w.rechts_zeigt()!r}")
    check("✕: „geschlossen“ kam je Maske genau einmal", z.folge == ["geschlossen"] * 3, str(z.folge))
    _loeschungen(app)
    check("✕: nach den vorgemerkten Löschungen leben 0 von 3 Masken", _leben(masken) == 0,
          f"{_leben(masken)} von 3")


def test_f44_abbrechen():
    """„Abbrechen“: erst abgebrochen (der neue Knoten geht wieder), dann zu und weg."""
    w, app = _fenster()
    m = _rahmen(w)
    w.refresh_all()
    _ruhe(app)
    _loeschungen(app)
    n0 = m.nn
    w._baum_neu("knoten")
    _ruhe(app)
    mk = w.maskenrand.maske
    z = _zaehler()
    if mk is None or getattr(mk, "btn_abbrechen", None) is None:
        check("Neu: Knoten - Maske mit „Abbrechen“ offen", False, repr(mk))
        return
    mk.abgebrochen.connect(z.abgebrochen)
    mk.geschlossen.connect(z.geschlossen)
    n1 = w.model.nn
    mk.btn_abbrechen.click()
    _ruhe(app)
    check("Abbrechen: der schon angelegte Knoten geht wieder weg (wie bisher)",
          n1 == n0 + 1 and w.model.nn == n0, f"{n0} -> {n1} -> {w.model.nn}")
    check("Abbrechen: erst „abgebrochen“, dann „geschlossen“, je einmal",
          z.folge == ["abgebrochen", "geschlossen"], str(z.folge))
    check("Abbrechen: rechts ist nichts mehr offen, die Maske steht nicht mehr im Bereich",
          w.maskenrand.maske is None and w.maskenplatz.indexOf(mk) < 0)
    # ein zweiter Weg mit „Abbrechen“: neuer Lastfall (nichts angelegt)
    w._baum_neu("lastfaelle")
    _ruhe(app)
    mk2 = w.maskenrand.maske
    if getattr(mk2, "btn_abbrechen", None) is not None:
        mk2.btn_abbrechen.click()
        _ruhe(app)
    _loeschungen(app)
    check("Abbrechen: nach den vorgemerkten Löschungen leben 0 von 2 Masken (Knoten, Lastfall)",
          _leben([mk, mk2]) == 0, f"{_leben([mk, mk2])} von 2")


def test_f44_esc_und_ersetzen():
    """Esc im Fenster schliesst keine Maske und beendet bei laufender Auswahl
    per Maus nur diese; das Ersetzen nimmt die vorige weg - alles wie bisher."""
    from PySide6 import QtCore
    from PySide6.QtTest import QTest
    w, app = _fenster()
    _rahmen(w)
    w.refresh_all()
    _ruhe(app)
    _loeschungen(app)
    # Esc im Programmfenster: „Alles deselektieren“, die Maske bleibt
    w.maske_knoten()
    _ruhe(app)
    mk = w.maskenrand.maske
    feld = next(iter(mk._felder.values()))
    w.activateWindow()
    feld.setFocus()
    _ruhe(app)
    QTest.keyClick(feld, QtCore.Qt.Key_Escape)
    _ruhe(app)
    _loeschungen(app)
    check("Esc im Fenster schließt keine Maske (wie bisher): sie bleibt offen und lebt",
          w.maskenrand.maske is mk and w.maskenrand.offen() and _leben([mk]) == 1)
    # Esc mit laufender Auswahl per Maus (Lot: Feld „Objekt“): erst nur diese beenden
    w._set_selection([0])
    _ruhe(app)
    w.maske_lot()
    _ruhe(app)
    lot = w.maskenrand.maske
    _loeschungen(app)
    check("das Ersetzen nimmt die vorige Maske weg (wie bisher)", _leben([mk]) == 0 and lot is not mk)
    lot.feld_fokussiert.emit("objekt")
    _ruhe(app)
    an = lot.objekt_modus
    feld = lot._felder["objekt"]
    feld.setFocus()
    _ruhe(app)
    QTest.keyClick(feld, QtCore.Qt.Key_Escape)
    _ruhe(app)
    check("Esc bei laufender Auswahl per Maus beendet nur sie, die Maske bleibt (wie bisher)",
          an == "flaeche" and not lot.objekt_modus and w.maskenrand.maske is lot and w.maskenrand.offen(),
          f"vorher {an!r}, nachher {lot.objekt_modus!r}")
    # Ersetzen: geschlossen genau einmal, die neue bleibt
    z = _zaehler()
    w.maske_knoten()
    _ruhe(app)
    alt = w.maskenrand.maske
    alt.geschlossen.connect(z.geschlossen)
    w.maske_stab()
    _ruhe(app)
    neu = w.maskenrand.maske
    _loeschungen(app)
    check("Ersetzen: die vorige meldet „geschlossen“ einmal und lebt nicht mehr, die neue ist offen",
          z.folge == ["geschlossen"] and _leben([alt]) == 0 and neu is not None and _leben([neu]) == 1
          and w.maskenrand.offen(), f"{z.folge}, alt lebt {_leben([alt])}")
    w.maskenrand.schliessen()
    _loeschungen(app)


def test_f44_was_mit_der_maske_endet():
    """Vorschau, Ebene im Bild, Auswahl per Maus und Leiste enden ueber ✕
    wie beim Ersetzen."""
    from statik3d.bridges.positions import Stellung
    w, app = _fenster()
    m = _rahmen(w)
    m.stellungen.append(Stellung("S1", 0.0, "zu", staebe_aus=["S2"], faelle=list(m.load_cases)))
    w.refresh_all()
    _ruhe(app)
    _loeschungen(app)
    vorher = set(w.versteckt["elemente"])
    aus = set(m.members["S2"].elements)
    for weg in ("✕", "Ersetzen"):
        w._objektmaske("stellung", "S1")
        _ruhe(app)
        mk = w.maskenrand.maske
        offen = set(w.versteckt["elemente"])
        if weg == "✕":
            mk.btn_zu.click()
        else:
            w.maske_knoten()
        _ruhe(app)
        _loeschungen(app)
        check(f"Stellung, {weg}: die Vorschau blendet aus und kommt danach zurück, die Maske lebt nicht mehr",
              offen == aus and set(w.versteckt["elemente"]) == vorher and _leben([mk]) == 0,
              f"offen {sorted(offen)}, danach {sorted(w.versteckt['elemente'])}, lebt {_leben([mk])}")
    w.maskenrand.schliessen()
    _ruhe(app)

    # Auswahl per Maus (Lot, Feld „Objekt“): mit ✕ geht auch sie
    w._set_selection([0])
    _ruhe(app)
    w.maske_lot()
    _ruhe(app)
    lot = w.maskenrand.maske
    lot.feld_fokussiert.emit("objekt")
    _ruhe(app)
    an = w.maskenrand.objekt_modus()
    lot.btn_zu.click()
    _ruhe(app)
    check("Lot mit laufender Auswahl per Maus, ✕: der Maskenrand nimmt keine Klicks mehr",
          an == "flaeche" and w.maskenrand.objekt_modus() == "" and not w.maskenrand.knoten_angeklickt(1)
          and not w.maskenrand.will_punkte(), f"vorher {an!r}, nachher {w.maskenrand.objekt_modus()!r}")
    _loeschungen(app)
    check("… und die Maske lebt nicht mehr", _leben([lot]) == 0)

    # Ebene im Bild (Schnittebene, „Ebene im Bild ziehen“): ✕ nimmt sie weg
    w.maske_schnittebene()
    _ruhe(app)
    mk = w.maskenrand.maske
    if mk is not None and getattr(mk, "titel", "") == "Schnittebene":
        mk.setzen("widget", True)
        mk.anwenden()
        _ruhe(app)
        da = getattr(w, "_schnittwidget", None) is not None
        mk = w.maskenrand.maske
        mk.btn_zu.click()
        _ruhe(app)
        _loeschungen(app)
        check("Schnittebene: die Ebene im Bild war da, ✕ nimmt sie mit weg, die Maske lebt nicht mehr",
              da and getattr(w, "_schnittwidget", None) is None
              and not _ebenenwerkzeuge(w) and _leben([mk]) == 0,
              f"da {da}, danach {getattr(w, '_schnittwidget', None)!r}")
        w.act_schnitt.setChecked(False)
        _ruhe(app)
    else:
        check("Schnittebene: Maske offen", False, repr(mk))

    # Leiste „Übernehmen | Verwerfen“: ✕ an der geaenderten Maske nimmt sie mit
    w._objektmaske("knoten", "1")
    _ruhe(app)
    mk = w.maskenrand.maske
    mk.setzen("x", 7.5)
    _ruhe(app)
    w.baum.angeklickt.emit("knoten", "2")
    _ruhe(app)
    leiste = getattr(w, "aenderungsleiste", None)
    stand = leiste is not None and leiste.isVisible()
    mk.btn_zu.click()
    _ruhe(app)
    _loeschungen(app)
    check("Leiste stand, ✕ an der Maske: die Leiste geht mit, die Maske lebt nicht mehr, x unverändert",
          stand and not leiste.isVisible() and _leben([mk]) == 0 and w.maskenrand.maske is None
          and abs(float(w.model.nodes[1][0]) - 3.0) < 1e-12,
          f"Leiste vorher {stand}, x = {float(w.model.nodes[1][0])}")

    # Querschnittmaske (eigene Klasse, gleicher Rand)
    w.querschnitt_neu()
    _ruhe(app)
    q = w.maskenrand.maske
    zu = getattr(q, "findChildren", None)
    from PySide6 import QtWidgets
    kreuz = next((b for b in q.findChildren(QtWidgets.QToolButton) if b.text() == "✕"), None) if zu else None
    if kreuz is not None:
        kreuz.click()
    else:
        q.schliessen()
    _ruhe(app)
    _loeschungen(app)
    check("Querschnittmaske, ✕: sie lebt danach nicht mehr", _leben([q]) == 0)


def test_f44_keine_verborgenen_masken():
    """Wie im Beleg (p07): unter dem Fenster bleibt nach allem keine Maske liegen."""
    w, app = _fenster()
    w.maskenrand.schliessen()
    _loeschungen(app)
    rest = _masken_im_fenster(w)
    check("unter dem Fenster liegt keine verborgene Maske mehr", not rest,
          f"{len(rest)}: " + ", ".join(getattr(x, "titel", "?") for x in rest[:5]))
    check("keine Ausnahme in den Prüfungen oben", not AUSNAHMEN, str(AUSNAHMEN[:2]))
    fehler = list(getattr(w.meldungen, "fehler", []) or [])
    check("keine Fehlermeldung des Programms", not fehler, str(fehler[:2]))


def test_f44_handbuch():
    from tests.handbuch import absatz
    t = absatz("Querschnitt, Material, Dicke und Lastfall gelten")
    check("Handbuch: mit ✕ oder „Abbrechen“ geht die Maske ganz weg, früher nur versteckt",
          "ganz entfernt" in t and "Bis zum 06.10.2026" in t and "„Abbrechen“" in t, t[:80])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_f44_maskenrand_fuer_sich, test_f40_lagerknopf, test_f40_handbuch,
              test_f44_kreuz, test_f44_abbrechen,
              test_f44_esc_und_ersetzen, test_f44_was_mit_der_maske_endet,
              test_f44_keine_verborgenen_masken, test_f44_handbuch):
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
    sys.stdout.flush()
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
