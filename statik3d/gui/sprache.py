"""Qt auf Deutsch: Uebersetzer laden und Tastenkuerzel deutsch anzeigen (02.10.2026).

Das Programm ist deutsch, Qt war es bis zum 02.10.2026 nicht: es lud keinen
QTranslator, und alles, was Qt selbst beschriftet, erschien englisch - die
Standardknoepfe „OK/Cancel/Yes/No“ jeder QMessageBox, das Kontextmenue der
Textfelder („Undo/Redo/Cut/Copy/Paste/Select All“), QDialogButtonBox, die
Farbauswahl; in Menues stand „Ctrl+Z“. Zwei Dinge gehoeren hierher:

* :func:`uebersetzer_laden` - Qts deutsche Texte (``qtbase_de.qm``, dazu der
  Sammelkatalog ``qt_de.qm``) beim Start der Anwendung installieren;
* :func:`kuerzel_text` - ein Tastenkuerzel fuer die **Anzeige** deutsch
  schreiben („Strg+Umschalt+C“, „Entf“, „Pos1“). Der Schluessel selbst
  (``QAction.setShortcut("Ctrl+Z")``) bleibt englisch: so heisst die
  Tastenfolge in Qt, und die Tests und der Code suchen sie so.

Die Anzeige hat eine eigene Tabelle und haengt nicht am Uebersetzer: Qt
uebersetzt ein Kuerzel nur, wenn qtbase_de geladen ist, und kennt fuer
Bild auf/ab und die Pfeile eigene Worte („Bild aufwaerts“), die das Handbuch
nicht benutzt. Der Hinweis am Knopf soll in jedem Fall dasselbe sagen wie das
Handbuch.

Wo die Dateien liegen: PySide6 bringt sie im Paket mit
(``PySide6/translations``, in den Linux-Raedern ``PySide6/Qt/translations``);
QLibraryInfo nennt den Ordner. In der exe sammelt
PyInstaller ``qt_de.qm`` und ``qtbase_de.qm`` ueber seinen Qt-Hook mit ein
(gemessen an build/Statik3D/Analysis-00.toc: ``PySide6\\translations\\...``),
sie liegen zur Laufzeit unter ``sys._MEIPASS/PySide6/translations`` (unter
Linux ``.../PySide6/Qt/translations``). Gesucht wird darum in dieser
Reihenfolge: QLibraryInfo, der Ordner des PySide6-Pakets, ``_MEIPASS``.
"""
from __future__ import annotations

import os
import sys
from typing import NamedTuple

from PySide6 import QtCore, QtGui

# qtbase: die eigentlichen Texte (QtCore, QtGui, QtWidgets); qt: der
# Sammelkatalog, er verweist auf die Kataloge der uebrigen Qt-Module im selben
# Ordner und ist selbst fast leer (91 Byte) - eine Zugabe, kein Muss
KATALOGE = ("qtbase", "qt")
PFLICHT = "qtbase"


class Ergebnis(NamedTuple):
    """Was :func:`uebersetzer_laden` getan hat.

    ``geladen``  die installierten Kataloge (Namen ohne Sprache und .qm);
    ``meldung``  leer, wenn alles da war - sonst **eine** Zeile fuer das
                 Protokoll (der Aufrufer schreibt sie, hier wird nicht gedruckt);
    ``orte``     die durchsuchten Ordner."""
    geladen: tuple
    meldung: str
    orte: tuple


def suchorte() -> list:
    """Die Ordner, in denen die Qt-Uebersetzungen liegen koennen, in der
    Reihenfolge der Suche, ohne Doppelte."""
    orte, gesehen = [], set()

    def dazu(ort):
        if not ort:
            return
        schluessel = os.path.normcase(os.path.normpath(ort))
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            orte.append(ort)

    try:
        dazu(QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.TranslationsPath))
    except Exception:                       # noqa: BLE001 - dann die anderen Orte
        pass
    try:
        import PySide6
        paket = os.path.dirname(PySide6.__file__)
        dazu(os.path.join(paket, "translations"))
        # die Linux-Raeder von PySide6 legen Qt unter PySide6/Qt ab
        dazu(os.path.join(paket, "Qt", "translations"))
    except Exception:                       # noqa: BLE001
        pass
    meipass = getattr(sys, "_MEIPASS", None)      # nur in der exe (PyInstaller)
    if meipass:
        dazu(os.path.join(meipass, "PySide6", "translations"))
        dazu(os.path.join(meipass, "PySide6", "Qt", "translations"))     # Linux
        dazu(os.path.join(meipass, "translations"))
    return orte


def uebersetzer_laden(app=None, orte=None, sprache: str = "de") -> Ergebnis:
    """Die deutschen Qt-Texte in die Anwendung laden.

    ``app``  die QCoreApplication (Vorgabe: die laufende);
    ``orte`` die zu durchsuchenden Ordner (Vorgabe: :func:`suchorte`);
    ``sprache`` das Sprachkuerzel der Dateien (``qtbase_<sprache>.qm``).

    Mehrfach gerufen installiert es nichts doppelt: die Uebersetzer haengen
    mit Namen an der Anwendung, ein schon vorhandener wird uebernommen. Fehlt
    ``qtbase_de.qm`` (oder ist sie unlesbar), geht das Programm still weiter -
    Qt bleibt englisch - und ``Ergebnis.meldung`` sagt es in einer Zeile.
    ``qt_de.qm`` ist nur Zugabe, ihr Fehlen meldet nichts.
    """
    app = app or QtCore.QCoreApplication.instance()
    orte = list(orte) if orte is not None else suchorte()
    if app is None:
        return Ergebnis((), "Qt-Übersetzung nicht geladen: keine Anwendung", tuple(orte))
    geladen, gefunden_unlesbar = [], False
    for name in KATALOGE:
        objname = f"statik3d_{name}_{sprache}"
        if app.findChild(QtCore.QTranslator, objname) is not None:
            geladen.append(name)
            continue
        datei = f"{name}_{sprache}.qm"
        for ort in orte:
            if not os.path.isfile(os.path.join(ort, datei)):
                continue
            t = QtCore.QTranslator(app)
            t.setObjectName(objname)
            if t.load(datei, ort) and app.installTranslator(t):
                geladen.append(name)
                break
            t.setParent(None)
            if name == PFLICHT:
                gefunden_unlesbar = True
    meldung = ""
    if PFLICHT not in geladen:
        datei = f"{PFLICHT}_{sprache}.qm"
        warum = "nicht lesbar" if gefunden_unlesbar else "nicht gefunden"
        meldung = (f"Qt-Übersetzung {datei} {warum} (gesucht in: "
                   f"{'; '.join(orte) if orte else 'keinem Ordner'}) - "
                   f"die Standardtexte von Qt bleiben englisch")
    return Ergebnis(tuple(geladen), meldung, tuple(orte))


# ---------------------------------------------------------------------------
# Kuerzel fuer die Anzeige
# ---------------------------------------------------------------------------
_MODIFIKATOREN = {"Ctrl": "Strg", "Shift": "Umschalt", "Alt": "Alt", "Meta": "Meta"}
_TASTEN = {
    "Del": "Entf", "Delete": "Entf", "Ins": "Einfg", "Insert": "Einfg",
    "Home": "Pos1", "End": "Ende",
    "PgUp": "Bild auf", "PageUp": "Bild auf", "PgDown": "Bild ab", "PgDn": "Bild ab",
    "PageDown": "Bild ab",
    "Esc": "Esc", "Escape": "Esc", "Return": "Eingabe", "Enter": "Eingabe",
    "Backspace": "Rücktaste", "Space": "Leertaste",
    "Left": "Pfeil links", "Right": "Pfeil rechts", "Up": "Pfeil auf", "Down": "Pfeil ab",
    "Print": "Druck",
}


def _akkord(text: str) -> str:
    """Eine Tastenfolge ohne Komma („Ctrl+Shift+C“, „Ctrl++“) deutsch."""
    teile, rest = [], text.strip()
    weiter = True
    while weiter:
        weiter = False
        for en, de in _MODIFIKATOREN.items():
            # „Ctrl++“: nach „Ctrl+“ bleibt „+“ als Taste - nur abtrennen,
            # solange noch etwas dahinter steht
            if rest.startswith(en + "+") and len(rest) > len(en) + 1:
                teile.append(de)
                rest = rest[len(en) + 1:]
                weiter = True
                break
    teile.append(_TASTEN.get(rest, rest))
    return "+".join(teile)


def kuerzel_text(kuerzel) -> str:
    """Ein Tastenkuerzel fuer die Anzeige deutsch schreiben.

    ``kuerzel`` ist der Qt-Text („Ctrl+Shift+C“, „Del“) oder eine
    QKeySequence. „Ctrl+Shift+C“ wird „Strg+Umschalt+C“, „Del“ „Entf“,
    „PgUp“ „Bild auf“; mehrere Akkorde („Ctrl+K, Ctrl+C“) einzeln. F-Tasten,
    Buchstaben und unbekannte Namen bleiben, wie sie sind. Unabhaengig davon,
    ob der Qt-Uebersetzer geladen ist; die Tastenfolge der QAction aendert das
    nicht, es ist nur der Text fuer Hinweise und Menues.
    """
    if isinstance(kuerzel, QtGui.QKeySequence):
        kuerzel = kuerzel.toString(QtGui.QKeySequence.PortableText)
    kuerzel = str(kuerzel or "").strip()
    if not kuerzel:
        return ""
    return ", ".join(_akkord(a) for a in kuerzel.split(", "))
