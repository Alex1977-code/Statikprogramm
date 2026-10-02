"""
Fensteraufteilung des Programmfensters (Paket 5 des Oberflaechenplans, 25.09.2026).

Befund der Analyse (24.09.2026, offscreen gemessen am Stand 562dc3a): bei
1920 x 1080 maximiert bekam die Ansicht 1142 x 470 px, 26 % der Fensterflaeche;
bei 1366 x 768 blieben 588 x 158 px (9 %), bei 1280 x 720 (1920er Laptop mit
150 % Skalierung) 502 x 124 px (7 %). Die Docks behielten feste Masse
(Baum 290, rechts 472, unten 357 px), der untere Bereich lief unter dem Baum
und dem rechten Bereich durch, die Windmaske zog den rechten Bereich auf
1170 px, und ein 1600 x 980 grosses Startfenster war hoeher als ein
768er-Bildschirm.

Hier steht, was das aendert (Antwort 9 des Anwenders: „maximiert, rechts etwa
460 px, unten etwa 25 %, Ribbon im Register Start“):

* Start maximiert; der Modellbaum bekommt 16 % der Breite, rechts 460 px,
  unten 25 % der Hoehe. Baum und rechter Bereich reichen ueber die volle
  Hoehe (setCorner), der untere Bereich steht nur unter der Ansicht und hat
  keine eigene Titelzeile.
* Solange der Anwender keine Trennlinie zieht, folgen die Masse der
  Fenstergroesse; Groesse und Aufteilung werden beim Beenden in
  einstellungen.json gemerkt (Schluessel „fenster“, mit Fassungskennung) und
  beim Start gegen den Bildschirm geprueft.
* Ansicht → Fenster: Schalter je Zone, „Nur Ansicht“, „Ribbon einklappen“
  (Strg+F1) und „Anordnung zurücksetzen“.
* Eine Kompaktstufe: Fensterhoehe unter 900 px oder eine Ansicht, die mit den
  Sollmassen kleiner als 700 x 400 px bliebe - Ribbon eingeklappt, unten nur
  die Registerzeile, Ansichtswuerfel kleiner, Farbskala waagerecht.
* STATIK3D_FENSTER=fest haelt die Aufteilung beim Stand bis 24.09.2026
  (1600 x 980, nicht maximiert, feste Dockmasse, keine Kompaktstufe, nichts
  gemerkt) - fuer den Rauchtest und den Bildvergleich bilder.py, die mit
  290/616/376 px rechnen. Kopfzeile, Einklappen und Menue gibt es auch dort.
"""
from __future__ import annotations

import json
import os

from PySide6 import QtCore, QtWidgets

from .sprache import kuerzel_text

#: Kennung des gespeicherten Formats; eine andere Kennung wird verworfen
FASSUNG = 1
#: Sollmasse (Antwort 9 des Anwenders, 24.09.2026)
ANTEIL_BAUM = 0.16
RECHTS = 460
ANTEIL_UNTEN = 0.25
#: Mindestmasse ohne „fest“ (vorher 290 px Baum, 215 px unten). Baum 260 px
#: statt 16 % (Gegenpruefung 25.09.2026, Beispiel hall, alles aufgeklappt,
#: Segoe UI, 1366 x 768): bei 218 px waren 95 von 196 Namen abgeschnitten,
#: „Stiel…“ zweimal; mit 260 px und der begrenzten Zusatzspalte sind es 3
#: („+ … anlegen“), am Stand 562dc3a mit 290 px waren es 6. Die Ansicht
#: bleibt bei 1366 x 768 bei 630 x 627 px (38 % der Flaeche).
BAUM_MIN = 260
RECHTS_MIN = 400
UNTEN_MIN = 120
#: Zusatzspalte des Modellbaums: hoechstens dieser Anteil der Baumbreite,
#: zwischen 50 und 120 px (120 px ist der Deckel aus design.Modellbaum)
BAUMSPALTE_ANTEIL = 0.25
BAUMSPALTE_MIN = 50
BAUMSPALTE_MAX = 120
#: Kompaktstufe: Fensterhoehe darunter, oder Ansicht mit Sollmassen kleiner
KOMPAKT_HOEHE = 900
KOMPAKT_ANSICHT = (700, 400)


def fest() -> bool:
    """STATIK3D_FENSTER=fest: Aufteilung wie bis 24.09.2026."""
    return os.environ.get("STATIK3D_FENSTER", "").strip().lower() == "fest"


def soll(breite: int, hoehe: int) -> dict:
    """Sollmasse der Docks fuer ein Fenster dieser Groesse [px]."""
    return {"baum": max(BAUM_MIN, int(round(ANTEIL_BAUM * breite))), "rechts": RECHTS,
            "unten": max(UNTEN_MIN, int(round(ANTEIL_UNTEN * hoehe)))}


# --------------------------------------------------------------------------
# Speichern und Laden (einstellungen.json, Schluessel „fenster“)
# --------------------------------------------------------------------------
def _datei() -> str:
    from .. import parallel
    return parallel.einstellungsdatei()


def _lesen() -> dict:
    try:
        with open(_datei(), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def laden() -> dict | None:
    """Der gespeicherte Eintrag „fenster“ - None, wenn er fehlt oder eine
    andere Fassung hat."""
    f = _lesen().get("fenster")
    if not isinstance(f, dict) or f.get("fassung") != FASSUNG:
        return None
    return f


def schreiben(eintrag: dict) -> str:
    """Den Eintrag „fenster“ schreiben; die uebrigen Schluessel (Loeser,
    Threads …) bleiben stehen."""
    d = _lesen()
    d["fenster"] = dict(eintrag, fassung=FASSUNG)
    p = _datei()
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    return p


def _zahlen(x, n: int):
    if not isinstance(x, (list, tuple)) or len(x) != n:
        return None
    try:
        return [int(v) for v in x]
    except (TypeError, ValueError):
        return None


def pruefen(eintrag: dict | None, bildschirme: list) -> dict | None:
    """Einen gespeicherten Eintrag gegen die Bildschirme pruefen.

    ``bildschirme``: verfuegbare Flaechen als (x, y, Breite, Hoehe). Zurueck
    kommt, was davon gilt: ``geometrie`` (None = maximiert starten),
    ``maximiert``, ``docks`` (None = Sollmasse), ``zonen``, ``ribbon``.
    Ein Fenster, das auf keinen Bildschirm ganz passt (Bildschirm abgezogen,
    kleinere Aufloesung, hoehere Skalierung), startet maximiert; Dockmasse
    von einem anderen Bildschirm oder mit unsinnigen Werten gelten nicht.
    """
    if not isinstance(eintrag, dict) or eintrag.get("fassung") != FASSUNG:
        return None
    geo = _zahlen(eintrag.get("geometrie"), 4)
    schirm = None
    if geo is not None and geo[2] >= 640 and geo[3] >= 480:
        for b in bildschirme:
            bx, by, bb, bh = (int(v) for v in b)
            if (geo[0] >= bx - 8 and geo[1] >= by - 8 and geo[0] + geo[2] <= bx + bb + 8
                    and geo[1] + geo[3] <= by + bh + 8):
                schirm = (bb, bh)
                break
    if schirm is None:
        geo = None
    maximiert = bool(eintrag.get("maximiert", True)) or geo is None
    docks = None
    gespeichert_auf = _zahlen(eintrag.get("bildschirm"), 2)
    if gespeichert_auf is not None and any(
            (int(b[2]), int(b[3])) == tuple(gespeichert_auf) for b in bildschirme):
        d = {k: eintrag.get(k) for k in ("baum", "rechts", "unten")}
        try:
            d = {k: int(v) for k, v in d.items()}
        except (TypeError, ValueError):
            d = None
        bb, bh = gespeichert_auf
        if d is not None and (BAUM_MIN <= d["baum"] <= 0.4 * bb and RECHTS_MIN <= d["rechts"] <= 0.5 * bb
                              and UNTEN_MIN <= d["unten"] <= 0.6 * bh):
            docks = d
    zonen = eintrag.get("zonen") if isinstance(eintrag.get("zonen"), dict) else {}
    zonen = {k: bool(zonen.get(k, True)) for k in ("baum", "rechts", "unten")}
    return {"geometrie": geo, "maximiert": maximiert, "docks": docks, "zonen": zonen,
            "ribbon": bool(eintrag.get("ribbon_eingeklappt", False))}


def _bildschirme() -> list:
    out = []
    for s in QtWidgets.QApplication.screens():
        g = s.availableGeometry()
        out.append((g.x(), g.y(), g.width(), g.height()))
    return out


def normalgroesse_begrenzen(w, anteil: float = 0.9) -> None:
    """Das (noch nicht maximierte) Fenster auf hoechstens ``anteil`` der freien
    Bildschirmflaeche verkleinern und mittig setzen; passt es, bleibt es."""
    scr = w.screen() or QtWidgets.QApplication.primaryScreen()
    if scr is None:
        return
    a = scr.availableGeometry()
    b = min(w.width(), int(anteil * a.width()))
    h = min(w.height(), int(anteil * a.height()))
    if (b, h) == (w.width(), w.height()):
        return
    w.setGeometry(a.x() + (a.width() - b) // 2, a.y() + (a.height() - h) // 2, b, h)


def starten(w) -> None:
    """Das Hauptfenster zeigen: maximiert oder wie zuletzt gespeichert.

    Mit STATIK3D_FENSTER=fest wie bis 24.09.2026 (show in 1600 x 980)."""
    if fest():
        w.show()
        return
    g = pruefen(laden(), _bildschirme())
    anordnung = getattr(w, "anordnung", None)
    if g is not None and g["geometrie"] is not None and not g["maximiert"]:
        w.setGeometry(*g["geometrie"])
        w.show()
    else:
        # Die Groesse fuer „Verkleinern“ vorher setzen (Gegenpruefung
        # 25.09.2026): sonst blieb es bei den 1600 x 980 aus dem Aufbau - auf
        # 1366 x 768 hoeher als der Bildschirm, und eine gemerkte Normalgroesse
        # galt nicht. Die gemerkte, wenn pruefen() sie gelten laesst, sonst
        # hoechstens 90 % der freien Flaeche, mittig.
        if g is not None and g["geometrie"] is not None:
            w.setGeometry(*g["geometrie"])
        else:
            normalgroesse_begrenzen(w)
        w.showMaximized()
    if anordnung is not None and g is not None:
        anordnung.gespeichertes_anwenden(g)


# --------------------------------------------------------------------------
# Die Anordnung am Fenster
# --------------------------------------------------------------------------
class WaagerechtRollen(QtWidgets.QScrollArea):
    """Rollt nur waagerecht und verlangt keine Mindestbreite: der Inhalt
    bekommt die volle Hoehe und mindestens seine Mindestbreite."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

    def sizeHint(self) -> QtCore.QSize:
        w = self.widget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self) -> QtCore.QSize:
        w = self.widget()
        if w is None:
            return super().minimumSizeHint()
        return QtCore.QSize(120, w.minimumSizeHint().height())


class Fensteranordnung(QtCore.QObject):
    """Haelt die Aufteilung des Hauptfensters (siehe Modulkopf)."""

    def __init__(self, w):
        super().__init__(w)
        self.w = w
        self.fest = fest()
        #: die Masse folgen der Fenstergroesse, bis der Anwender eine
        #: Trennlinie zieht; ``_ziel``: gespeicherte Masse statt der Sollmasse
        self.automatisch = True
        self._ziel: dict | None = None
        self.kompakt = False
        self._ribbon_vor_kompakt = False
        self._vor_nur_ansicht: dict | None = None
        self._selbst = 0
        self._takt = QtCore.QTimer(self)
        self._takt.setSingleShot(True)
        self._takt.setInterval(0)
        self._takt.timeout.connect(self.nachfuehren)
        self._kopfzeile_zusammenlegen()
        self._menue_bauen()
        # Das Programm startet im Register „Start“ (Antwort 9) - die
        # haeufigsten Befehle stehen dort, nicht Neu/Oeffnen/Speichern
        w.ribbon.zeigen("Start")
        leiste = w.tab_unten.leiste
        #: Doppelklick auf die Leiste: der Zustand vor dessen erstem Klick und
        #: ein Merker fuer den Klick, den QTabBar danach noch sendet
        self._unten_vor_klick: tuple | None = None
        self._unten_doppel = False
        self._klickuhr = QtCore.QElapsedTimer()
        leiste.tabBarClicked.connect(self._unten_geklickt)
        leiste.tabBarDoubleClicked.connect(self._unten_doppelt)
        if self.fest:
            return
        # Baum und rechter Bereich ueber die volle Hoehe: die Ecken gehoeren
        # ihnen, der untere Bereich steht nur unter der Ansicht
        for ecke, bereich in ((QtCore.Qt.TopLeftCorner, QtCore.Qt.LeftDockWidgetArea),
                              (QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea),
                              (QtCore.Qt.TopRightCorner, QtCore.Qt.RightDockWidgetArea),
                              (QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)):
            w.setCorner(ecke, bereich)
        # Keine Titelzeile unten: „PROTOKOLL UND TABELLEN“ stand ueber einer
        # Gruppenleiste, die dasselbe sagt (rund 30 px). Der Name bleibt am Dock.
        leer = QtWidgets.QWidget(w.unten_dock)
        QtWidgets.QHBoxLayout(leer).setContentsMargins(0, 0, 0, 0)
        w.unten_dock.setTitleBarWidget(leer)
        # Der untere Bereich ist jetzt nur so breit wie die Ansicht. Seine
        # Knopfzeilen verlangten zusammen 1019 px (offscreen gemessen; unter
        # Windows mit Segoe UI etwa die Haelfte) - das Fenster liess sich dann
        # nicht schmaler als 1635 px ziehen. Reicht die Breite nicht, rollt
        # der Bereich waagerecht, statt das Fenster zu verbreitern.
        inhalt = w.unten_dock.widget()
        rolle = WaagerechtRollen(w.unten_dock)
        rolle.setWidget(inhalt)
        w.unten_dock.setWidget(rolle)
        w.tabs.setMinimumWidth(RECHTS_MIN)
        w.baum_dock.setMinimumWidth(BAUM_MIN)
        w.unten_dock.setMinimumHeight(UNTEN_MIN)
        w.installEventFilter(self)
        # Kompaktstufe: die waagerechte Farbskala steht ueber den Kennwerten
        # unten links, nicht auf ihnen (viewport.farbskalen_heben)
        plotter = getattr(w, "plotter", None)
        if plotter is not None:
            from . import viewport as vp
            vp.farbskalen_heben_einrichten(plotter, lambda: bool(getattr(w, "_farbskala_waagerecht", False)))
        # Die Zusatzspalte des Baums (Anzahl, Koordinaten) darf bis 120 px
        # breit werden; in einem schmalen Baum blieb vom Namen dann nichts
        # („Stiel…“ zweimal bei 1366 x 768). Sie bekommt hoechstens ein
        # Viertel der Baumbreite.
        baum = getattr(w, "baum", None)
        if baum is not None:
            baum.installEventFilter(self)
            self._baumspalte_begrenzen()

    # -- Kopfzeile ---------------------------------------------------------
    def _kopfzeile_zusammenlegen(self):
        schnell, suche = self.w.ribbon.kopf_abgeben()
        self.w.kopf.einbetten(schnell, suche)

    # -- Menue Ansicht → Fenster --------------------------------------------
    def _menue_bauen(self):
        w, rb = self.w, self.w.ribbon
        g = getattr(w, "_gruppe_fenster", None) or rb.register("Ansicht").gruppe("Fenster")
        akt = g.menue("Fenster ▾", [
            ("Modellbaum zeigen", lambda: self._zone_geschaltet("baum"),
             "Den Modellbaum links ein- oder ausblenden"),
            ("Rechten Bereich zeigen", lambda: self._zone_geschaltet("rechts"),
             "Den rechten Bereich (Masken und Einstellungen) ein- oder ausblenden"),
            ("Unteren Bereich zeigen", lambda: self._zone_geschaltet("unten"),
             "Protokoll und Tabellen unten ein- oder ausblenden"),
            ("Ribbon einklappen", self._ribbon_geschaltet,
             "Nur die Registerzeile zeigen; ein Klick auf einen Reiter öffnet das Register bis zum "
             "nächsten Befehl. Auch Doppelklick auf einen Reiter"),
            ("Nur Ansicht", self._nur_ansicht_geschaltet,
             "Baum, rechten und unteren Bereich ausblenden und das Ribbon einklappen - "
             "noch einmal: alles wie vorher"),
            ("Anordnung zurücksetzen", self.zuruecksetzen,
             "Alle Bereiche zeigen, Modellbaum 16 % der Breite, rechts 460 px, unten 25 % der Höhe"),
        ], hinweis="Bereiche des Fensters ein- und ausblenden, Ribbon einklappen, Anordnung zurücksetzen",
            symbol="fenster")
        self.act_zone = dict(zip(("baum", "rechts", "unten"), akt[:3]))
        self.act_ribbon, self.act_nur_ansicht, self.act_zuruecksetzen = akt[3:6]
        for a in akt[:5]:
            a.setCheckable(True)
        for name, dock in self._docks().items():
            self.act_zone[name].setChecked(True)
            dock.visibilityChanged.connect(lambda _v, n=name: self._zone_nachziehen(n))
        rb.kuerzel_setzen(self.act_ribbon, "Ctrl+F1")
        self.act_ribbon.setToolTip(self.act_ribbon.toolTip() + f"   ({kuerzel_text('Ctrl+F1')})")
        rb.eingeklappt_geaendert.connect(self._ribbon_nachziehen)

    def _docks(self) -> dict:
        w = self.w
        return {"baum": w.baum_dock, "rechts": w.eingaben_dock, "unten": w.unten_dock}

    @staticmethod
    def _setzen(a, an: bool):
        a.blockSignals(True)
        a.setChecked(bool(an))
        a.blockSignals(False)

    def zone_sichtbar(self, name: str) -> bool:
        return not self._docks()[name].isHidden()

    def zone_setzen(self, name: str, an: bool) -> None:
        dock = self._docks()[name]
        dock.setVisible(bool(an))
        self._zone_nachziehen(name)
        if an and self._vor_nur_ansicht is not None:
            # wer eine Zone zurueckholt, hat „Nur Ansicht“ verlassen
            self._vor_nur_ansicht = None
            self._setzen(self.act_nur_ansicht, False)
        if an and self.automatisch:
            self._takt.start()

    def _zone_geschaltet(self, name: str):
        self.zone_setzen(name, self.act_zone[name].isChecked())

    def _zone_nachziehen(self, name: str):
        self._setzen(self.act_zone[name], self.zone_sichtbar(name))

    def _ribbon_geschaltet(self):
        self._selbst += 1
        try:
            self.w.ribbon.einklappen(self.act_ribbon.isChecked())
        finally:
            self._selbst -= 1

    def _ribbon_nachziehen(self, an: bool):
        self._setzen(self.act_ribbon, an)
        if not self._selbst and self.kompakt:
            # in der Kompaktstufe von Hand umgeschaltet: das gilt danach
            self._ribbon_vor_kompakt = bool(an)

    def nur_ansicht(self, an: bool) -> None:
        """Alles ausser der Ansicht aus- (an) bzw. wie vorher einblenden."""
        rb = self.w.ribbon
        if an:
            if self._vor_nur_ansicht is None:
                # Gemerkt wird der Wunsch des Anwenders, nicht der Zustand der
                # Kompaktstufe (Gegenpruefung 25.09.2026: sonst blieb das Ribbon
                # nach „Nur Ansicht“ ueber die Kompaktgrenze hinweg eingeklappt)
                self._vor_nur_ansicht = {"zonen": {n: self.zone_sichtbar(n) for n in self._docks()},
                                         "ribbon": (self._ribbon_vor_kompakt if self.kompakt
                                                    else rb.eingeklappt())}
            for n, dock in self._docks().items():
                dock.hide()
                self._zone_nachziehen(n)
            self._selbst += 1
            try:
                rb.einklappen(True)
            finally:
                self._selbst -= 1
        else:
            vorher, self._vor_nur_ansicht = self._vor_nur_ansicht, None
            if vorher is None:
                vorher = {"zonen": {n: True for n in self._docks()}, "ribbon": False}
            for n, dock in self._docks().items():
                dock.setVisible(vorher["zonen"].get(n, True))
                self._zone_nachziehen(n)
            self._selbst += 1
            try:
                if self.kompakt:
                    # die Kompaktstufe gilt weiter; der Wunsch gilt nach ihr
                    self._ribbon_vor_kompakt = bool(vorher["ribbon"])
                    rb.einklappen(True)
                else:
                    rb.einklappen(vorher["ribbon"])
            finally:
                self._selbst -= 1
            if self.automatisch:
                self._takt.start()
        self._setzen(self.act_nur_ansicht, an)

    def _nur_ansicht_geschaltet(self):
        self.nur_ansicht(self.act_nur_ansicht.isChecked())

    def zuruecksetzen(self) -> None:
        """Alle Zonen zeigen, Sollmasse, Ribbon offen (ausser in der Kompaktstufe)."""
        self._vor_nur_ansicht = None
        self._setzen(self.act_nur_ansicht, False)
        for n, dock in self._docks().items():
            dock.show()
            self._zone_nachziehen(n)
        self.automatisch, self._ziel = True, None
        self._selbst += 1
        try:
            self.w.ribbon.einklappen(self.kompakt)
        finally:
            self._selbst -= 1
        self._ribbon_vor_kompakt = False
        if self.kompakt:
            self.unten_einklappen(True)
        else:
            self.unten_einklappen(False)
        self.masse_anwenden()

    # -- Unterer Bereich: nur Registerzeile -----------------------------------
    def unten_eingeklappt(self) -> bool:
        return self.w.tab_unten.stapel.isHidden()

    def unten_einklappen(self, an: bool) -> None:
        """Unten nur die Gruppenleiste zeigen (an) oder den ganzen Bereich.

        Ein Klick auf eine Gruppe klappt ihn wieder auf, ein Doppelklick auf
        die Leiste schaltet um."""
        w = self.w
        dock, tb = w.unten_dock, w.tab_unten
        if bool(an) == self.unten_eingeklappt():
            return
        if an:
            tb.stapel.hide()
            hoehe = tb.leiste.sizeHint().height() + 2
            dock.setMinimumHeight(0)
            dock.setMaximumHeight(hoehe + (0 if dock.titleBarWidget() is not None else 30))
        else:
            tb.stapel.show()
            dock.setMaximumHeight(16777215)
            dock.setMinimumHeight(215 if self.fest else UNTEN_MIN)
            ziel = (self._ziel or {}).get("unten") or soll(w.width(), w.height())["unten"]
            w.resizeDocks([dock], [int(ziel)], QtCore.Qt.Vertical)

    def unten_zeigen(self) -> None:
        """Den unteren Bereich zeigen und aufklappen - fuer Befehle, die dort
        eine Tabelle oder das Protokoll nach vorn holen (Gegenpruefung
        25.09.2026: in der Kompaktstufe wechselte sonst nur die Gruppe in der
        Leiste, die Tabelle blieb unsichtbar, der Befehl wirkte tot)."""
        dock = self.w.unten_dock
        if dock.isHidden():
            dock.show()
            self._zone_nachziehen("unten")
        self.unten_einklappen(False)

    def _unten_geklickt(self, _i: int):
        if self._unten_doppel:
            # der Klick, den QTabBar nach einem Doppelklick selbst sendet
            self._unten_doppel = False
            return
        self._unten_vor_klick = (self.unten_eingeklappt(), _i)
        self._klickuhr.start()
        if self.unten_eingeklappt():
            self.unten_einklappen(False)

    def _unten_doppelt(self, _i: int):
        """Doppelklick auf die Leiste schaltet um (Gegenpruefung 25.09.2026).

        Ein echter Doppelklick kommt als Klick, Doppelklick, Klick: der erste
        Klick klappte auf, der Doppelklick wieder zu, und der Klick danach
        wieder auf - sichtbar aenderte sich nichts. Massgebend ist darum der
        Zustand vor dem ersten Klick, und der Klick danach zaehlt nicht."""
        vorher = self.unten_eingeklappt()
        vk = self._unten_vor_klick
        if (vk is not None and vk[1] == _i and self._klickuhr.isValid()
                and self._klickuhr.elapsed() <= QtWidgets.QApplication.doubleClickInterval()):
            vorher = vk[0]
        self._unten_vor_klick = None
        self._unten_doppel = True
        QtCore.QTimer.singleShot(0, self._unten_doppel_vergessen)
        self.unten_einklappen(not vorher)

    def _unten_doppel_vergessen(self):
        self._unten_doppel = False

    # -- Masse ------------------------------------------------------------
    def masse_anwenden(self) -> None:
        """Die Docks auf die Soll- bzw. gespeicherten Masse setzen."""
        if self.fest:
            return
        w = self.w
        z = dict(soll(w.width(), w.height()))
        if self._ziel:
            z.update({k: v for k, v in self._ziel.items() if v})
        breit = [(d, z[n]) for n, d in (("baum", w.baum_dock), ("rechts", w.eingaben_dock))
                 if not d.isHidden()]
        if breit:
            w.resizeDocks([d for d, _ in breit], [int(v) for _, v in breit], QtCore.Qt.Horizontal)
        if not w.unten_dock.isHidden() and not self.unten_eingeklappt():
            w.resizeDocks([w.unten_dock], [int(z["unten"])], QtCore.Qt.Vertical)

    def gespeichertes_anwenden(self, g: dict) -> None:
        """Den geprueften Eintrag (pruefen) nach dem Zeigen anwenden."""
        if g.get("docks"):
            self._ziel = dict(g["docks"])
        for n, an in (g.get("zonen") or {}).items():
            if n in self._docks():
                self._docks()[n].setVisible(bool(an))
                self._zone_nachziehen(n)
        if g.get("ribbon"):
            self._selbst += 1
            try:
                self.w.ribbon.einklappen(True)
            finally:
                self._selbst -= 1
        self.nachfuehren()

    def eintrag(self) -> dict:
        """Was beim Beenden gemerkt wird."""
        w = self.w
        g = w.normalGeometry() if w.isMaximized() or w.isFullScreen() else w.geometry()
        scr = (w.screen() or QtWidgets.QApplication.primaryScreen()).availableGeometry()
        ziel = self._ziel or {}
        vor = self._vor_nur_ansicht
        zonen = vor["zonen"] if vor else {n: self.zone_sichtbar(n) for n in self._docks()}
        return {"geometrie": [g.x(), g.y(), g.width(), g.height()],
                "maximiert": bool(w.isMaximized()),
                "bildschirm": [scr.width(), scr.height()],
                "baum": w.baum_dock.width() if self.zone_sichtbar("baum") else ziel.get("baum"),
                "rechts": w.eingaben_dock.width() if self.zone_sichtbar("rechts") else ziel.get("rechts"),
                "unten": (w.unten_dock.height() if self.zone_sichtbar("unten") and not self.unten_eingeklappt()
                          else ziel.get("unten")),
                "zonen": zonen,
                "ribbon_eingeklappt": bool(vor["ribbon"] if vor else
                                           (self._ribbon_vor_kompakt if self.kompakt
                                            else w.ribbon.eingeklappt()))}

    def speichern(self) -> str | None:
        """Groesse und Aufteilung in einstellungen.json (nicht mit „fest“)."""
        if self.fest:
            return None
        try:
            e = self.eintrag()
            if self.automatisch and not self._ziel:
                # nichts von Hand gezogen: beim naechsten Start wieder anteilig
                e.update(baum=None, rechts=None, unten=None)
            return schreiben(e)
        except OSError:
            return None

    # -- Ereignisse -----------------------------------------------------------
    def _baumspalte_begrenzen(self):
        baum = self.w.baum
        grenze = max(BAUMSPALTE_MIN, min(BAUMSPALTE_MAX, int(BAUMSPALTE_ANTEIL * baum.width())))
        kopf = baum.header()
        if kopf.maximumSectionSize() != grenze:
            kopf.setMaximumSectionSize(grenze)

    def eventFilter(self, obj, ev):
        if obj is getattr(self.w, "baum", None):
            if ev.type() == QtCore.QEvent.Resize:
                self._baumspalte_begrenzen()
            return False
        if obj is self.w:
            t = ev.type()
            if t in (QtCore.QEvent.Resize, QtCore.QEvent.Show):
                self._takt.start()
            elif t == QtCore.QEvent.MouseButtonPress and self.w.childAt(ev.position().toPoint()) is None:
                # Druck auf eine Trennlinie zwischen den Bereichen: ab jetzt
                # gelten die Masse des Anwenders
                self.automatisch = False
        return False

    def nachfuehren(self) -> None:
        """Nach einer Groessenaenderung: Kompaktstufe pruefen, Masse nachziehen."""
        if self.fest:
            return
        self.kompakt_pruefen()
        if self.automatisch:
            self.masse_anwenden()

    def kompakt_noetig(self, breite: int = None, hoehe: int = None) -> bool:
        """Fensterhoehe unter 900 px, oder die Ansicht bliebe mit Sollmassen und
        offenem Ribbon kleiner als 700 x 400 px. Gerechnet wird mit den
        Sollmassen, nicht mit der jetzigen Ansicht - sonst schaltete die Stufe
        sich selbst wieder ab, sobald sie der Ansicht Platz gemacht hat."""
        w = self.w
        breite = w.width() if breite is None else int(breite)
        hoehe = w.height() if hoehe is None else int(hoehe)
        s = soll(breite, hoehe)
        from . import ribbon as rib
        kopf = (w.kopf.height() + w.ribbon.tabs.tabBar().sizeHint().height() + rib.Register.HOEHE)
        ansicht_b = breite - s["baum"] - s["rechts"]
        ansicht_h = hoehe - kopf - w.statusBar().sizeHint().height() - s["unten"]
        return (hoehe < KOMPAKT_HOEHE or ansicht_b < KOMPAKT_ANSICHT[0]
                or ansicht_h < KOMPAKT_ANSICHT[1])

    def kompakt_pruefen(self) -> None:
        an = self.kompakt_noetig()
        if an != self.kompakt:
            self.kompakt_setzen(an)

    def kompakt_setzen(self, an: bool) -> None:
        """Die Kompaktstufe ein- oder ausschalten."""
        w, rb = self.w, self.w.ribbon
        an = bool(an)
        if an == self.kompakt:
            return
        self._selbst += 1
        try:
            if an:
                vor = self._vor_nur_ansicht
                self._ribbon_vor_kompakt = bool(vor["ribbon"]) if vor is not None else rb.eingeklappt()
                self.kompakt = True
                if self._vor_nur_ansicht is None:
                    rb.einklappen(True)
            else:
                self.kompakt = False
                if self._vor_nur_ansicht is None:
                    rb.einklappen(self._ribbon_vor_kompakt)
        finally:
            self._selbst -= 1
        self.unten_einklappen(an)
        rand = getattr(w, "ansichtsrand", None)
        if rand is not None and hasattr(rand, "kompakt_setzen"):
            rand.kompakt_setzen(an)
        w._farbskala_waagerecht = an
        # Eine gezeigte Farbskala neu legen - nur, wenn es Ergebnisse gibt
        if getattr(w, "analysis", None) is not None or getattr(w, "results", None) is not None:
            try:
                w.redraw()
            except Exception:           # noqa: BLE001 - die Stufe darf nie scheitern
                pass
