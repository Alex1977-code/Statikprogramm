#!/usr/bin/env python3
"""Startet die Statik3D-Oberflaeche (Doppelklick, python run_gui.py oder Statik3D.exe).

    --version      Versionsnummer ausgeben
    --selbsttest   Pakete laden, Beispiel rechnen, statik3d_selbsttest.txt schreiben (Build-Pruefung)
    --rechenhilfe  nur das Fenster "Rechenhilfe": fuer einen Arbeitsplatz der Rechnerfarm mitrechnen
                   (--host, --port, --key, --kerne optional)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _absturzspur():
    """Bei einem harten Absturz den Python-Stapel in eine Datei schreiben.

    Am 07.09.2026 ist eine Rechnung nach neun Minuten mit einer
    Zugriffsverletzung in Qt6Gui.dll weggebrochen. Zurueck blieb ein
    Ereigniseintrag mit einer Adresse - ohne Absturzabbild und Debugger sagt
    der nichts darueber, was das Programm gerade tat.

    faulthandler kostet nichts und aendert am Ablauf nichts: er haengt sich in
    die Signale fuer Zugriffsverletzung, Busfehler und Abbruch und schreibt im
    Ernstfall die Aufrufkette aller Threads. Liegt der Absturz in Qt oder VTK,
    steht wenigstens da, welche Python-Zeile ihn ausgeloest hat.
    """
    try:
        import faulthandler
        basis = (os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
                 or os.path.join(os.path.expanduser("~"), ".local", "share"))
        ordner = os.path.join(basis, "Statik3D", "Protokolle")
        os.makedirs(ordner, exist_ok=True)
        # offen halten, solange das Programm laeuft - beim Absturz schreibt
        # faulthandler direkt in diesen Dateizeiger
        spur = open(os.path.join(ordner, "absturz.txt"), "a", encoding="utf-8")
        import datetime
        spur.write(f"\n=== Start {datetime.datetime.now():%d.%m.%Y %H:%M:%S} ===\n")
        spur.flush()
        faulthandler.enable(file=spur, all_threads=True)
        globals()["_ABSTURZSPUR"] = spur          # nicht einsammeln lassen
    except Exception:              # noqa: BLE001 - eine Diagnose darf nie sperren
        pass


_absturzspur()


def _selftest() -> int:
    """Alle Pakete laden, ein Beispiel rechnen, Ergebnis (oder Fehler) in
    statik3d_selbsttest.txt schreiben. Rueckgabe 0 = in Ordnung."""
    import traceback
    out = os.path.join(os.getcwd(), "statik3d_selbsttest.txt")
    lines, code = [], 0
    try:
        import numpy, scipy  # noqa: E401
        lines.append(f"numpy {numpy.__version__}, scipy {scipy.__version__}")
        import PySide6
        lines.append(f"PySide6 {PySide6.__version__}")
        import pyvista
        lines.append(f"pyvista {pyvista.__version__}")
        import pyvistaqt  # noqa: F401
        from statik3d import solver, examples_lib, update
        from statik3d.web import server  # noqa: F401
        lines.append(update.describe())
        # Welcher Gleichungsloeser steckt wirklich in dieser exe? Fehlt MKL,
        # rechnet SuperLU auf genau einem Kern - das ist beim Bau vom 07.09.
        # unbemerkt ausgeliefert worden und hat eine Rechnung neun Minuten
        # lang bei 20 % stehen lassen. Darum wird es hier geprueft und, wenn
        # es fehlt, mit Rueckgabe 1 zum Fehler des Baus gemacht.
        loeser = solver.loeser_verfuegbar()
        lines.append(f"Gleichungsloeser: {loeser}")
        r = solver.solve_static(examples_lib.frame_example())
        lines.append(f"Beispiel Rahmen: umax = {r.umag.max() * 1000:.3f} mm")
        if not loeser.startswith("MKL PARDISO"):
            lines.append("FEHLER: kein Mehrkern-Loeser im Programm - MKL fehlt im Bundle")
            code = 1
        # Die mitgelieferten Loeser der Auswahl: MKL PARDISO, PyAMG (MIT) und
        # SuperLU muessen in der exe stecken und rechnen ("Gleichungsloeser
        # mitinstallieren", 13.09.2026); die GPL-Loeser bleiben draussen, und
        # MUMPS (CeCILL-C) laedt das Programm beim Start nach - im Bundle ist
        # es nicht, wohl aber die Pruefsumme seines Rades (statik3d.werkzeuge).
        liste = {k: da for k, _n, da, *_r in solver.loeser_liste()}
        lines.append("Loeser in der exe: " + ", ".join(k for k, da in liste.items() if da))
        try:
            import mumps
            lines.append(mumps.beschreibung() + " (in dieser Umgebung installiert)")
        except ImportError:
            lines.append("MUMPS: nicht in der exe, wird beim Start nachgeladen")
        except Exception as ex:                  # noqa: BLE001 - steht dann als Fehler unten
            lines.append(f"MUMPS: {ex}")
        from statik3d import werkzeuge
        import re as _re
        if not _re.fullmatch(r"[0-9a-f]{64}", werkzeuge.WERKZEUGE["mumps"].rad_sha256 or ""):
            lines.append("FEHLER: keine 64-stellige Pruefsumme fuer das MUMPS-Rad in statik3d/werkzeuge.py")
            code = 1
        from statik3d import parallel
        for key in ("pyamg", "superlu"):
            if not liste.get(key):
                lines.append(f"FEHLER: Loeser {key} fehlt im Bundle")
                code = 1
                continue
            alt_backend = parallel.settings().solver_backend
            parallel.configure(solver_backend=key)
            try:
                r2 = solver.solve_static(examples_lib.frame_example())
            finally:
                parallel.configure(solver_backend=alt_backend)
            abw = abs(r2.umag.max() - r.umag.max()) / max(r.umag.max(), 1e-30)
            lines.append(f"Beispiel Rahmen mit {key}: umax = {r2.umag.max() * 1000:.3f} mm "
                         f"(Abweichung {abw:.1e})")
            if abw > 1e-6:
                lines.append(f"FEHLER: Loeser {key} weicht vom Mehrkern-Loeser ab")
                code = 1
        if code == 0:
            lines.append("OK")
    except BaseException:      # noqa: BLE001 - alles in die Datei, nie ein Meldungsfenster
        lines.append(traceback.format_exc())
        code = 1
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        print("\n".join(lines))
    except Exception:          # noqa: BLE001 - ohne Konsole
        pass
    return code


def _packerbild(text: str = None, schliessen: bool = False):
    """Das Startbild des Packers (PyInstaller) beschriften oder schliessen.

    Es gibt das Modul pyi_splash nur in der exe; ueberall sonst passiert nichts.
    """
    try:
        import pyi_splash          # noqa: PLC0415
        if text:
            pyi_splash.update_text(text)
        if schliessen:
            pyi_splash.close()
    except Exception:              # noqa: BLE001
        pass


def _start():
    if "--version" in sys.argv:
        _packerbild(schliessen=True)
        from statik3d import __version__
        print(__version__)
        sys.exit(0)
    if "--selbsttest" in sys.argv:
        _packerbild(schliessen=True)
        sys.exit(_selftest())
    if "--rechenhilfe" in sys.argv:
        # Nur das Rechenhilfe-Fenster: dieser Rechner rechnet fuer einen
        # Arbeitsplatz mit (statik3d.gui.rechenhilfe) - ohne Hauptfenster
        _packerbild(schliessen=True)
        from statik3d.gui import rechenhilfe
        sys.exit(rechenhilfe.main())
    # Startbild, solange Grafik und Rechenkern geladen werden - das dauert
    # in der exe zehn bis dreissig Sekunden, und ohne Bild klickt man ein
    # zweites Mal.
    _packerbild("Oberfläche wird geladen …")
    app = splash = None
    try:
        from PySide6 import QtWidgets
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        from statik3d.gui import start
        splash = start.Startbild()
        splash.show()
        splash.melden("Grafik und Rechenkern werden geladen …")
    except Exception:              # noqa: BLE001 - dann eben ohne Startbild
        splash = None
    try:
        from statik3d.gui.main import main
    except ImportError as ex:
        print("Fehlende Abhaengigkeit:", ex)
        print("Bitte installieren:  pip install -r requirements.txt")
        sys.exit(1)
    # Kommt der Start aus dem Austauschskript einer Aktualisierung, wartet
    # dieses auf eine Rueckmeldung. Sie wird hier gegeben - erst nachdem die
    # Pakete geladen sind, denn genau daran scheitert eine misslungene
    # Aktualisierung: die neue exe bricht ab, bevor Python laeuft.
    try:
        from statik3d import update
        update.melde_neustart()
    except Exception:          # noqa: BLE001 - eine Rueckmeldung haelt nichts auf
        pass
    main(app=app, splash=splash)


def _stroeme_sichern():
    """sys.stdout und sys.stderr duerfen in der exe nicht None sein.

    Die gepackte Oberflaeche laeuft ohne Konsole; PyInstaller setzt beide
    Stroeme dann auf None. Faellt in einem Arbeitsprozess eine Ausnahme an,
    schreibt **CPython selbst** den Traceback nach sys.stderr
    (multiprocessing/process.py, _bootstrap) - und stirbt dabei an
    "AttributeError: 'NoneType' object has no attribute 'write'". Der Anwender
    sieht dann einen Dialog "Unhandled exception in script" mit diesem
    nichtssagenden Fehler, waehrend der eigentliche Grund verdeckt bleibt
    (21.09.2026, Drehlager: die Ursache war eine gebrochene Pipe in den
    Stabnachweisen). Ein stiller Ersatzstrom haelt das auf.
    """
    import io as _io
    import sys as _sys
    for name in ("stdout", "stderr"):
        if getattr(_sys, name, None) is None:
            setattr(_sys, name, _io.TextIOWrapper(_io.BytesIO(), encoding="utf-8",
                                                  errors="replace", write_through=True))


if __name__ == "__main__":       # wichtig fuer multiprocessing (Windows: spawn / exe)
    import multiprocessing
    _stroeme_sichern()           # **vor** freeze_support: der Arbeiter erbt es
    multiprocessing.freeze_support()
    _start()
