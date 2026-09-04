"""
Aktualisierung auf die neueste Version von GitHub.

Zwei Installationsarten:

* **Windows-Programm** (Statik3D.exe, gebaut von GitHub Actions, Release "latest"):
  neue exe herunterladen, nach dem Beenden per Hilfsskript austauschen, neu starten.
* **Quellinstallation** (python run_gui.py): ``git pull``, wenn ein Klon vorliegt,
  sonst main.zip herunterladen und die Programmdateien ersetzen.

    from statik3d import update
    info = update.check()                       # UpdateInfo
    if info.available:
        update.apply(info, progress=print)      # exe: danach Programm beenden
                                                # Quelle: danach neu starten (restart_command)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional

from . import __version__

REPO = "Alex1977-code/Statikprogramm"
API_URL = f"https://api.github.com/repos/{REPO}"
RELEASE_TAG = "latest"
EXE_NAME = "Statik3D.exe"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/latest/download/{EXE_NAME}"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
USER_AGENT = f"Statik3D/{__version__}"
SKIP_DIRS = {".git", ".venv", "venv", "Projekte", "__pycache__", "build", "dist"}


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    kind: str                     # exe | source
    current_version: str
    current_sha: str
    latest_sha: str
    latest_date: str
    url: str
    size: int = 0
    available: bool = False
    notes: str = ""

    @property
    def message(self) -> str:
        cur = self.current_sha[:7] if self.current_sha else "unbekannt"
        new = self.latest_sha[:7] if self.latest_sha else "?"
        if not self.available:
            return f"Statik3D {self.current_version} ({cur}) ist auf dem neuesten Stand."
        when = self.latest_date[:10] if self.latest_date else ""
        return (f"Neue Version verfügbar: Stand {new}{' vom ' + when if when else ''}"
                f" (installiert: {self.current_version}, {cur}).")


# --------------------------------------------------------------------------
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> str:
    """Programmordner: bei der exe ihr Verzeichnis, sonst die Wurzel des Quellbaums."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_info() -> dict:
    """Installierte Version: Versionsnummer, Commit (aus _build.py oder git), Art."""
    sha, date = "", ""
    try:
        from . import _build  # type: ignore  # von GitHub Actions / apply() geschrieben
        sha, date = getattr(_build, "BUILD_SHA", ""), getattr(_build, "BUILD_DATE", "")
    except ImportError:
        pass
    root = app_dir()
    if not sha and not is_frozen() and os.path.isdir(os.path.join(root, ".git")) and shutil.which("git"):
        try:
            out = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True,
                                 text=True, timeout=10)
            if out.returncode == 0:
                sha = out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return {"version": __version__, "sha": sha, "date": date,
            "kind": "exe" if is_frozen() else "source", "dir": root}


def version_label(long: bool = False) -> str:
    """Versionsangabe fuer Fensterrahmen, Statuszeile und Bericht.

    "2.1.0 (Build a4b3c2d, 03.09.2026)" - ohne Build-Stempel nur die Version,
    bei einer Arbeitskopie mit dem Zusatz "Quellcode".
    """
    b = build_info()
    txt = b["version"]
    extra = []
    if b.get("sha"):
        extra.append(f"Build {b['sha'][:7]}")
    if b.get("date"):
        extra.append(_short_date(b["date"]))
    if long and b.get("kind") == "source":
        extra.append("Quellcode")
    return txt + (" (" + ", ".join(extra) + ")" if extra else "")


def _short_date(text: str) -> str:
    """ISO-Zeitstempel -> TT.MM.JJJJ (unveraendert, wenn nicht erkennbar)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(text))
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else str(text)


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except OSError as ex:
        raise UpdateError(f"Keine Verbindung zu GitHub ({ex})") from ex
    except ValueError as ex:
        raise UpdateError(f"Antwort von GitHub unlesbar: {ex}") from ex


def _sha_from_text(text: str) -> str:
    m = re.search(r"\b([0-9a-f]{40})\b", text or "")
    return m.group(1) if m else ""


def check(timeout: float = 10.0, api_url: str = API_URL, kind: str = None) -> UpdateInfo:
    """Neueste Version bei GitHub erfragen und mit der installierten vergleichen."""
    info = build_info()
    kind = kind or info["kind"]
    if kind == "exe":
        rel = _get_json(f"{api_url}/releases/tags/{RELEASE_TAG}", timeout)
        asset = next((a for a in rel.get("assets", []) if a.get("name") == EXE_NAME), None)
        if asset is None:
            raise UpdateError(f"Im Release '{RELEASE_TAG}' liegt keine {EXE_NAME}")
        sha = _sha_from_text(rel.get("body", "")) or str(rel.get("target_commitish", ""))
        ui = UpdateInfo("exe", info["version"], info["sha"], sha, rel.get("published_at", ""),
                        asset.get("browser_download_url", DOWNLOAD_URL), int(asset.get("size", 0) or 0),
                        notes=rel.get("body", ""))
    else:
        c = _get_json(f"{api_url}/commits/main", timeout)
        sha = str(c.get("sha", ""))
        cm = c.get("commit", {})
        date = cm.get("committer", {}).get("date", "") or cm.get("author", {}).get("date", "")
        ui = UpdateInfo("source", info["version"], info["sha"], sha, date, ZIP_URL,
                        notes=(cm.get("message", "") or "").splitlines()[0] if cm.get("message") else "")
    ui.available = (not ui.current_sha) or (ui.latest_sha[:7] != ui.current_sha[:7])
    return ui


def diagnose(timeout: float = 10.0) -> str:
    """Vollstaendiger Befund zum Update - fuer den Fall, dass es nicht geht.

    Genannt werden die installierte Fassung, die neueste bei GitHub, die
    Adressen, das Schreibrecht am Programmordner und die Erreichbarkeit von
    GitHub. Der Text laesst sich unveraendert weitergeben.
    """
    b = build_info()
    z = ["Statik3D - Update-Befund",
         f"  Fassung          {b['version']}",
         f"  Art              {'Programmdatei (exe)' if b['kind'] == 'exe' else 'Quellcode'}",
         f"  Build            {b['sha'][:12] or '(kein Build-Stempel)'}",
         f"  Datum            {b['date'] or '-'}",
         f"  Ordner           {b['dir']}",
         f"  Programmdatei    {sys.executable}",
         f"  Schreibrecht     {'ja' if os.access(os.path.dirname(os.path.abspath(sys.executable)), os.W_OK) else 'NEIN - hier kann nicht ausgetauscht werden'}",
         f"  Release-Adresse  {API_URL}/releases/tags/{RELEASE_TAG}",
         f"  Download         {DOWNLOAD_URL}"]
    try:
        ui = check(timeout)
        z.append(f"  Neueste Fassung  Build {ui.latest_sha[:12] or '-'} vom "
                 f"{_short_date(ui.latest_date)}")
        z.append(f"  Groesse          {ui.size / 1e6:.1f} MB" if ui.size else "")
        z.append(f"  Ergebnis         " + ("Update verfuegbar" if ui.available
                                           else "Sie haben bereits die neueste Fassung"))
        if not ui.available and not b["sha"]:
            z.append("  Hinweis          Ohne Build-Stempel wird immer aktualisiert.")
    except UpdateError as ex:
        z.append(f"  Ergebnis         Abfrage fehlgeschlagen: {ex}")
        z.append("  Hinweis          Firewall oder Proxy? Der Download geht auch "
                 "unmittelbar ueber die Adresse oben.")
    log = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                       "statik3d_update.log")
    if os.path.exists(log):
        try:
            with open(log, "r", encoding="ascii", errors="replace") as f:
                z.append("  Letzter Austausch:")
                z.extend("    " + l.rstrip() for l in f.readlines()[-12:])
        except OSError:
            pass
    return "\n".join(x for x in z if x)


def download(url: str, dest: str, progress: Callable = None, timeout: float = 60.0) -> str:
    """Datei mit Fortschrittsmeldung herunterladen (progress(geladen, gesamt))."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            t_last = 0.0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress and (time.time() - t_last > 0.2):
                    progress(done, total)
                    t_last = time.time()
        if progress:
            progress(done, total)
    except OSError as ex:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise UpdateError(f"Download fehlgeschlagen: {ex}") from ex
    os.replace(tmp, dest)
    return dest


def write_build_stamp(sha: str, date: str, package_dir: str = None) -> str:
    package_dir = package_dir or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(package_dir, "_build.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'BUILD_SHA = "{sha}"\nBUILD_DATE = "{date}"\nVERSION = "{__version__}"\n')
    return path


# --------------------------------------------------------------------------
UPDATE_BAT = r"""@echo off
setlocal enabledelayedexpansion
rem Die internen Variablen des PyInstaller-Ladeteils gehoeren nicht in die neue
rem exe: sie beschreiben den alten Programmlauf. Erbt die neue Fassung sie,
rem haelt sie sich fuer einen Kindprozess und bricht mit
rem "Security validation failure: parent process has different executable!" ab.
rem Das Skript raeumt sie darum selbst weg - auch wenn es von Hand laeuft.
set "_PYI_APPLICATION_HOME_DIR="
set "_PYI_ARCHIVE_FILE="
set "_PYI_PARENT_PROCESS_LEVEL="
set "_PYI_SPLASH_IPC="
set "_PYI_LINUX_PROCESS_NAME="
set "_MEIPASS2="
set "EXE={exe}"
set "NEW={new}"
set "LOG={log}"
echo [%date% %time%] Austausch beginnt> "%LOG%"
echo   alt: "%EXE%">> "%LOG%"
echo   neu: "%NEW%">> "%LOG%"
echo Statik3D wird aktualisiert - bitte warten ...
if not exist "%NEW%" (
    echo [Fehler] Die heruntergeladene Datei fehlt.>> "%LOG%"
    echo Die heruntergeladene Datei fehlt: "%NEW%"
    pause
    exit /b 2
)
set /a n=0
:warten
timeout /t 1 /nobreak >nul
del "%EXE%" >nul 2>&1
if exist "%EXE%" (
    set /a n+=1
    if !n! lss 120 goto warten
    echo [Fehler] Programm laeuft nach 120 s noch.>> "%LOG%"
    echo Statik3D laeuft noch. Bitte das Programm beenden und diese Datei
    echo erneut starten:  "%~f0"
    echo Die neue Fassung liegt bereit als: "%NEW%"
    pause
    exit /b 1
)
move /y "%NEW%" "%EXE%" >nul 2>&1
if errorlevel 1 (
    echo [Fehler] Umbenennen fehlgeschlagen ^(Schreibrecht^?^).>> "%LOG%"
    echo Die neue Fassung konnte nicht an die Stelle der alten geschoben werden.
    echo Sie liegt hier: "%NEW%"
    echo Bitte von Hand umbenennen in: "%EXE%"
    pause
    exit /b 3
)
echo [%date% %time%] Austausch erfolgreich>> "%LOG%"
cd /d "%~dp0"
start "" "%EXE%"
if errorlevel 1 (
    echo [Fehler] Neustart fehlgeschlagen.>> "%LOG%"
    echo Der Austausch hat geklappt, der Neustart nicht.
    echo Bitte von Hand starten:  "%EXE%"
    pause
    exit /b 4
)
echo [%date% %time%] neu gestartet>> "%LOG%"
rem Das Skript loescht sich selbst und schliesst sein Fenster. (goto) verlaesst
rem den Skriptzusammenhang, damit die Datei beim Loeschen nicht mehr in
rem Benutzung ist; das anschliessende exit schliesst die Eingabeaufforderung
rem auch dann, wenn sie interaktiv geoeffnet wurde - sonst bleibt sie mit einer
rem Eingabezeile stehen und sieht aus, als sei etwas schiefgegangen.
(goto) 2>nul & del "%~f0" & exit
"""


def apply(info: UpdateInfo, progress: Callable = None, restart: bool = True,
          target: str = None) -> str:
    """Aktualisierung ausfuehren. exe: neue Datei laden und Hilfsskript starten (das
    Programm muss sich danach beenden). Quelle: git pull oder Dateien ersetzen; bei
    restart=True wird ein neuer Prozess gestartet (Aufrufer beendet sich)."""
    if info.kind == "exe":
        return apply_exe(info, progress, restart, target)
    return apply_source(info, progress, restart, target)


def apply_exe(info: UpdateInfo, progress: Callable = None, restart: bool = True,
              exe_path: str = None) -> str:
    exe = os.path.abspath(exe_path or sys.executable)
    ordner = os.path.dirname(exe)
    # Schreibrecht vor dem Laden pruefen - 200 MB umsonst zu laden hilft niemandem
    if not os.access(ordner, os.W_OK):
        raise UpdateError(
            f"Im Ordner '{ordner}' darf nicht geschrieben werden. Statik3D.exe an "
            "eine Stelle legen, an der Sie Schreibrecht haben (z. B. auf den "
            "Schreibtisch), oder die neue Fassung von Hand austauschen: " + info.url)
    new = exe + ".new"
    download(info.url, new, progress)
    with open(new, "rb") as f:
        head = f.read(2)
    if head != b"MZ" or os.path.getsize(new) < 1_000_000:
        os.remove(new)
        raise UpdateError("Heruntergeladene Datei ist kein Windows-Programm")
    log = os.path.join(ordner, "statik3d_update.log")
    bat = os.path.join(ordner, "statik3d_update.bat")
    with open(bat, "w", encoding="ascii", errors="replace", newline="\r\n") as f:
        f.write(UPDATE_BAT.format(exe=exe, new=new, log=log))
    if restart:
        start_helper(bat, new)
    return ("Neue Version heruntergeladen. Statik3D wird jetzt beendet, ausgetauscht "
            f"und neu gestartet.\nProtokoll des Austauschs: {log}")


def helper_path(exe_path: str = None) -> str:
    """Pfad des Austauschskripts neben der exe."""
    exe = os.path.abspath(exe_path or sys.executable)
    return os.path.join(os.path.dirname(exe), "statik3d_update.bat")


#: Umgebungsvariablen, die der PyInstaller-Ladeteil einer laufenden exe setzt.
#: Sie beschreiben **diesen** Programmlauf - das entpackte Verzeichnis, die
#: Archivdatei und die Stellung im Prozessbaum.
PYI_VARIABLEN = ("_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE",
                 "_PYI_PARENT_PROCESS_LEVEL", "_PYI_SPLASH_IPC",
                 "_PYI_LINUX_PROCESS_NAME", "_MEIPASS2", "_PYI_BUILDER_CLEANUP")


def saubere_umgebung(basis: dict = None) -> dict:
    """Umgebung ohne die internen Variablen des PyInstaller-Ladeteils.

    Eine gepackte exe laeuft in zwei Prozessen: der aeussere entpackt sich
    nach ``_MEIxxxx`` und startet sich selbst noch einmal. Der innere erkennt
    an ``_PYI_PARENT_PROCESS_LEVEL``, dass er das Kind ist, und prueft dann -
    seit PyInstaller 6 - ob sein Elternprozess **dieselbe** exe ist.

    Gibt man diese Variablen an einen fremden Prozess weiter, erbt der sie:
    ein daraus gestartetes Statik3D haelt sich faelschlich fuer ein Kind,
    findet als Elternprozess cmd.exe und bricht mit
    „Security validation failure: parent process has different executable!"
    ab. Genau das ist beim Selbstupdate passiert.

    Darum wird hier alles entfernt, was der Ladeteil gesetzt hat.
    """
    umgebung = dict(os.environ if basis is None else basis)
    for name in list(umgebung):
        if name in PYI_VARIABLEN or name.startswith("_PYI"):
            umgebung.pop(name, None)
    # Unter Linux/macOS legt der Ladeteil den urspruenglichen Suchpfad zur
    # Seite; fuer einen fremden Prozess gilt wieder der urspruengliche.
    for pfad in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        alt_wert = umgebung.pop(pfad + "_ORIG", None)
        if alt_wert is not None:
            umgebung[pfad] = alt_wert
        elif pfad + "_ORIG" in os.environ:
            umgebung.pop(pfad, None)
    return umgebung


def start_helper(bat: str, new: str = "") -> None:
    """
    Das Austauschskript starten - erst aufrufen, wenn Statik3D wirklich geht.

    Die Befehlszeile wird als **eine Zeichenkette** uebergeben. Mit einer
    Argumentliste setzt ``subprocess`` unter Windows ``list2cmdline`` an; das
    versieht die Anfuehrungszeichen im Pfad mit Gegenschraegstrichen, und
    cmd.exe sucht dann eine Datei namens \"C:\...\statik3d_update.bat\"
    - genau der Fehler "konnte nicht gefunden werden".

    ``start ""`` mit leerem Titel ist Absicht: sonst deutet cmd.exe den
    ersten Pfad in Anfuehrungszeichen als Fenstertitel.

    Die Umgebung wird von den PyInstaller-Variablen befreit
    (siehe ``saubere_umgebung``) - sonst erbt die neu gestartete exe die
    Angaben dieses Programmlaufs und bricht mit einer Sicherheitsmeldung ab.
    """
    if os.name != "nt":
        raise UpdateError("Austausch der exe nur unter Windows")
    if not os.path.isfile(bat):
        raise UpdateError(f"Das Austauschskript fehlt: {bat}")
    try:
        subprocess.Popen(f'cmd.exe /c start "" /min "{bat}"', close_fds=True,
                         env=saubere_umgebung(),
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    except OSError as ex:
        raise UpdateError(
            f"Das Austauschskript liess sich nicht starten ({ex}). Die neue "
            + (f"Fassung liegt bereit: {new}\n" if new else "")
            + f"Bitte Statik3D beenden und '{bat}' von Hand ausfuehren.") from ex


def apply_source(info: UpdateInfo, progress: Callable = None, restart: bool = True,
                 root: str = None) -> str:
    root = os.path.abspath(root or app_dir())
    if os.path.isdir(os.path.join(root, ".git")) and shutil.which("git"):
        try:
            out = subprocess.run(["git", "-C", root, "pull", "--ff-only"], capture_output=True,
                                 text=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as ex:
            raise UpdateError(f"git pull fehlgeschlagen: {ex}") from ex
        if out.returncode != 0:
            raise UpdateError("git pull fehlgeschlagen: " + (out.stderr.strip() or out.stdout.strip()))
        lines = [ln for ln in out.stdout.strip().splitlines() if ln.strip()]
        msg = "git pull: " + (lines[-1] if lines else "aktualisiert")
    else:
        tmpdir = tempfile.mkdtemp(prefix="statik3d_update_")
        zpath = download(info.url, os.path.join(tmpdir, "main.zip"), progress)
        n = 0
        try:
            with zipfile.ZipFile(zpath) as z:
                names = [m for m in z.namelist() if not m.endswith("/")]
                for m in names:
                    parts = m.split("/", 1)
                    if len(parts) < 2:
                        continue
                    rel = parts[1]
                    if any(p in SKIP_DIRS for p in rel.split("/")[:-1]):
                        continue
                    dest = os.path.join(root, *rel.split("/"))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(m) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    n += 1
        except (zipfile.BadZipFile, OSError) as ex:
            raise UpdateError(f"Entpacken fehlgeschlagen: {ex}") from ex
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        msg = f"{n} Dateien aktualisiert"
        write_build_stamp(info.latest_sha, info.latest_date, os.path.join(root, "statik3d"))
    if restart:
        subprocess.Popen(restart_command(), cwd=root, close_fds=True)
    return msg + ". Bitte Statik3D neu starten." if not restart else msg + ". Statik3D startet neu."


def restart_command() -> list[str]:
    if is_frozen():
        return [sys.executable] + sys.argv[1:]
    return [sys.executable] + sys.argv


def restart_now() -> None:
    """Das Programm an Ort und Stelle neu starten.

    Ueber ``execve`` mit gesaeuberter Umgebung: ``execv`` wuerde die Variablen
    des PyInstaller-Ladeteils mitnehmen, und der neue Lauf hielte sich fuer
    einen Kindprozess (siehe ``saubere_umgebung``).
    """
    befehl = restart_command()
    os.execve(befehl[0], befehl, saubere_umgebung())


def describe() -> str:
    b = build_info()
    sha = b["sha"][:7] if b["sha"] else "unbekannt"
    art = "Windows-Programm" if b["kind"] == "exe" else "Quellinstallation"
    return f"Statik3D {b['version']} ({art}, Stand {sha}{', ' + b['date'][:10] if b['date'] else ''})"
