"""
Vernetzer und Nachbesserer aus Statik3D heraus nachladen.

gmsh (GPL), Netgen (LGPL) und MMG3D (LGPL) kommen nicht mit der exe
(Benutzerhandbuch Kap. 9, Lizenzen). Wer sie nutzen will, laedt sie auf
Wunsch aus dem Programm heraus von ihrer Quelle: gmsh und Netgen als
fertige Raeder von PyPI, MMG3D als Programm aus dem GitHub-Release
"werkzeuge" dieses Projekts (dort aus dem Quelltext von MmgTools/mmg
gebaut, .github/workflows/werkzeuge.yml). Sie landen in den Benutzerdaten
(%LOCALAPPDATA%/Statik3D/Werkzeuge, unter Linux ~/.local/share/Statik3D/
Werkzeuge), nicht neben der exe, und ueberleben ein Programm-Update.

Ein Rad wird **ohne pip** entpackt - die exe hat kein pip. Die Ablage folgt
der Ordnung einer Python-Umgebung, damit die Pakete ihre Bibliotheken
finden: Python-Dateien unter ``Lib/site-packages``, die Datenanteile des
Rades relativ dazu wie bei pip (gmsh-4.15.dll unter ``Lib``, die
OCC-Bibliotheken von Netgen unter ``bin``). RECORD wird zur Ablage passend
neu geschrieben, weil Netgen seine OCC-Bibliotheken ueber
``importlib.metadata`` sucht.

    from statik3d import werkzeuge
    werkzeuge.installieren("gmsh", fortschritt=print)   # laedt und prueft
    werkzeuge.stand_alle()      # {"gmsh": {"version": "4.15.2", ...}, "netgen": None, ...}
    werkzeuge.aktivieren()      # Suchpfade setzen; geschieht beim Import von vernetzer_extern
    werkzeuge.entfernen("gmsh")

Umgebungsvariable ``STATIK3D_WERKZEUGE`` legt den Ordner fest (Pruefungen).
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from typing import Callable, Optional

from . import update as upd

#: Release dieses Projekts, in dem die gebauten Programme (MMG3D) liegen
WERKZEUG_RELEASE = "werkzeuge"
PYPI_URL = "https://pypi.org/pypi/{paket}/json"


class WerkzeugFehler(Exception):
    pass


@dataclass(frozen=True)
class Werkzeug:
    key: str
    name: str
    aufgabe: str            # Vernetzer | Nachbesserer
    lizenz: str
    quelle: str             # fuer den Anwender lesbar
    pakete: tuple = ()      # PyPI-Pakete in Reihenfolge
    modul: str = ""         # Modul, dessen Import die Installation prueft
    programm: str = ""      # Programmname (ohne .exe) bei Programmen
    groesse_mb: int = 0     # ungefaehre Downloadgroesse (Windows)


WERKZEUGE = {
    "gmsh": Werkzeug("gmsh", "gmsh", "Vernetzer", "GPL", "PyPI, Paket gmsh",
                     pakete=("gmsh",), modul="gmsh", groesse_mb=42),
    "netgen": Werkzeug("netgen", "Netgen", "Vernetzer", "LGPL",
                       "PyPI, Pakete netgen-mesher und netgen-occt",
                       pakete=("netgen-mesher", "netgen-occt"), modul="netgen.meshing", groesse_mb=27),
    "mmg3d": Werkzeug("mmg3d", "MMG3D", "Nachbesserer", "LGPL",
                      f"GitHub-Release „{WERKZEUG_RELEASE}“ von {upd.REPO}, gebaut aus MmgTools/mmg",
                      programm="mmg3d_O3", groesse_mb=2),
}


# --------------------------------------------------------------------------
# Ablage
# --------------------------------------------------------------------------
def datenordner() -> str:
    """Benutzerdaten: %LOCALAPPDATA% unter Windows, sonst XDG_DATA_HOME oder
    ~/.local/share - gehoert dem Anwender, ueberlebt ein Update."""
    basis = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if not basis:
        basis = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(basis, "Statik3D")


def ordner() -> str:
    """Der Werkzeugordner (STATIK3D_WERKZEUGE, sonst Benutzerdaten/Werkzeuge)."""
    return os.environ.get("STATIK3D_WERKZEUGE") or os.path.join(datenordner(), "Werkzeuge")


def werkzeug_ordner(key: str) -> str:
    return os.path.join(ordner(), key)


def site_ordner(key: str) -> str:
    return _site_von(werkzeug_ordner(key))


def _site_von(ziel: str) -> str:
    return os.path.join(ziel, "Lib", "site-packages")


def programm(key: str) -> str:
    """Pfad des Programms eines installierten Werkzeugs (mmg3d_O3), sonst leer."""
    wz = WERKZEUGE.get(key)
    if wz is None or not wz.programm or stand(key) is None:
        return ""
    for name in (wz.programm + ".exe", wz.programm):
        p = os.path.join(werkzeug_ordner(key), "bin", name)
        if os.path.isfile(p):
            return p
    return ""


def stand(key: str) -> Optional[dict]:
    """Was von einem Werkzeug installiert ist (stand.json), sonst None."""
    p = os.path.join(werkzeug_ordner(key), "stand.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("version") else None
    except (OSError, ValueError):
        return None


def stand_alle() -> dict:
    return {key: stand(key) for key in WERKZEUGE}


def bericht() -> str:
    """Eine Zeile je Werkzeug fuer Protokoll und Befund."""
    zeilen = [f"Werkzeuge in {ordner()}:"]
    for key, wz in WERKZEUGE.items():
        s = stand(key)
        zeilen.append(f"  {wz.name:7s} {wz.aufgabe:13s} {wz.lizenz:5s} "
                      + (f"Version {s['version']} vom {str(s.get('datum', ''))[:10]}" if s else "nicht installiert"))
    return "\n".join(zeilen)


# --------------------------------------------------------------------------
# Suchpfade
# --------------------------------------------------------------------------
def aktivieren() -> list:
    """Die site-packages der installierten Werkzeuge in sys.path aufnehmen
    (hinten - eine eigene Python-Umgebung mit demselben Paket geht vor).
    Rueckgabe: die Schluessel der aktivierten Werkzeuge."""
    _aufraeumen()
    aktiv = []
    for key in WERKZEUGE:
        if stand(key) is None:
            continue
        site = site_ordner(key)
        if os.path.isdir(site):
            if site not in sys.path:
                sys.path.append(site)
            importlib.invalidate_caches()
        aktiv.append(key)
    return aktiv


def _deaktivieren(key: str) -> None:
    site = site_ordner(key)
    while site in sys.path:
        sys.path.remove(site)


def _aufraeumen() -> None:
    """Reste entfernen, die beim Entfernen gesperrt waren (stand.json fehlt)."""
    basis = ordner()
    if not os.path.isdir(basis):
        return
    for name in os.listdir(basis):
        p = os.path.join(basis, name)
        if not os.path.isdir(p):
            continue
        # <key> ohne stand.json (Rest eines Entfernens) oder <key>.alt-<zeit>;
        # <key>.neu gehoert einer laufenden Installation und bleibt
        verwaist = name in WERKZEUGE and stand(name) is None
        if verwaist or name.startswith(tuple(k + ".alt-" for k in WERKZEUGE)):
            shutil.rmtree(p, ignore_errors=True)


# --------------------------------------------------------------------------
# Raeder von PyPI
# --------------------------------------------------------------------------
def _rad_tags(dateiname: str) -> Optional[tuple]:
    """(python, abi, plattform) aus dem Dateinamen eines Rades."""
    stamm = dateiname[:-4] if dateiname.endswith(".whl") else dateiname
    teile = stamm.split("-")
    if len(teile) < 5:
        return None
    return teile[-3], teile[-2], teile[-1]


def rad_passt(dateiname: str, py=None, plattform: str = "", maschine: str = "") -> bool:
    """Passt das Rad zu Python-Version, Betriebssystem und Prozessor?"""
    py = tuple(py or sys.version_info[:2])
    plattform = plattform or sys.platform
    maschine = (maschine or platform.machine() or "").lower()
    t = _rad_tags(dateiname)
    if t is None:
        return False
    pytag, _abi, plat = t
    pys = pytag.split(".")
    if not (f"cp{py[0]}{py[1]}" in pys or f"py{py[0]}" in pys):
        return False
    arm = "arm" in maschine or "aarch64" in maschine
    if plattform.startswith("win"):
        return plat == ("win_arm64" if arm else "win_amd64")
    if plattform.startswith("linux"):
        return "manylinux" in plat and plat.endswith("aarch64" if arm else "x86_64")
    if plattform == "darwin":
        return plat.startswith("macosx") and (("arm64" if arm else "x86_64") in plat or "universal2" in plat)
    return False


def rad_wahl(dateien: list, py=None, plattform: str = "", maschine: str = "") -> dict:
    """Das passende Rad aus der Dateiliste von PyPI (Eintraege mit filename,
    url, size, digests); ein Rad fuer genau diese Python-Version geht vor
    einem py3-Rad."""
    py = tuple(py or sys.version_info[:2])
    treffer = [d for d in dateien
               if d.get("packagetype", "bdist_wheel") == "bdist_wheel" and not d.get("yanked")
               and rad_passt(str(d.get("filename", "")), py, plattform, maschine)]
    if not treffer:
        namen = sorted(str(d.get("filename", "")) for d in dateien)
        raise WerkzeugFehler(f"kein passendes Rad für Python {py[0]}.{py[1]} auf {plattform or sys.platform} "
                             f"({(maschine or platform.machine())}); angeboten: {', '.join(namen) or 'nichts'}")
    treffer.sort(key=lambda d: 0 if f"cp{py[0]}{py[1]}" in str(d["filename"]) else 1)
    return treffer[0]


def _pypi(paket: str, timeout: float = 20.0) -> tuple:
    """(Version, Dateiliste) des Pakets von PyPI."""
    d = _json(PYPI_URL.format(paket=paket), timeout)
    return str(d.get("info", {}).get("version", "")), list(d.get("urls", []))


def _json(url: str, timeout: float) -> dict:
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": upd.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except OSError as ex:
        raise WerkzeugFehler(f"Keine Verbindung zu {url.split('/')[2]} ({ex})") from ex
    except ValueError as ex:
        raise WerkzeugFehler(f"Antwort von {url.split('/')[2]} unlesbar: {ex}") from ex


def _laden(url: str, ziel: str, fortschritt: Callable = None, timeout: float = 60.0) -> str:
    try:
        return upd.download(url, ziel, progress=fortschritt, timeout=timeout)
    except upd.UpdateError as ex:
        raise WerkzeugFehler(str(ex)) from ex


def _sha256(pfad: str) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _pfad_pruefen(name: str) -> list:
    teile = name.split("/")
    if (not name or name.startswith("/") or (len(name) > 1 and name[1] == ":")
            or any(t in ("..", "") for t in teile) or "\\" in name):
        raise WerkzeugFehler(f"unzulässiger Pfad im Archiv: {name!r}")
    return teile


def rad_entpacken(rad: str, ziel: str) -> list:
    """Ein Rad ohne pip in den Werkzeugordner ``ziel`` legen.

    Reine Python-Anteile nach ``ziel/Lib/site-packages``, die Datenanteile
    (``<paket>.data/data/...``) nach ``ziel/...``, Skripte nach
    ``ziel/Scripts`` - dieselbe Ordnung wie eine Python-Umgebung unter
    Windows, in der pip das Rad ablegt. RECORD wird passend neu geschrieben.
    Rueckgabe: die geschriebenen Dateien.
    """
    site = _site_von(ziel)
    geschrieben = []
    with zipfile.ZipFile(rad) as z:
        namen = z.namelist()
        dist_info = next((n.split("/")[0] for n in namen if n.split("/")[0].endswith(".dist-info")), "")
        daten = next((n.split("/")[0] for n in namen if n.split("/")[0].endswith(".data")), "")
        for n in namen:
            if n.endswith("/"):
                continue
            teile = _pfad_pruefen(n)
            if daten and teile[0] == daten and len(teile) >= 3:
                art, rest = teile[1], teile[2:]
                if art in ("purelib", "platlib"):
                    out = os.path.join(site, *rest)
                elif art == "data":
                    out = os.path.join(ziel, *rest)
                elif art == "scripts":
                    out = os.path.join(ziel, "Scripts", *rest)
                elif art == "headers":
                    out = os.path.join(ziel, "include", *rest)
                else:
                    out = os.path.join(ziel, art, *rest)
            else:
                out = os.path.join(site, *teile)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as q, open(out, "wb") as f:
                shutil.copyfileobj(q, f)
            geschrieben.append(out)
    if dist_info:
        zeilen = [os.path.relpath(p, site).replace(os.sep, "/") + ",," for p in geschrieben]
        with open(os.path.join(site, dist_info, "RECORD"), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(zeilen) + "\n")
    return geschrieben


def archiv_entpacken(archiv: str, ziel: str) -> list:
    """Ein Programmarchiv (zip) flach nach ``ziel`` legen; Programme unter
    POSIX ausfuehrbar machen."""
    geschrieben = []
    with zipfile.ZipFile(archiv) as z:
        for n in z.namelist():
            if n.endswith("/"):
                continue
            teile = _pfad_pruefen(n)
            out = os.path.join(ziel, *teile)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as q, open(out, "wb") as f:
                shutil.copyfileobj(q, f)
            if os.name != "nt" and not os.path.splitext(out)[1]:
                os.chmod(out, 0o755)
            geschrieben.append(out)
    return geschrieben


def programm_url(wz: Werkzeug, plattform: str = "") -> str:
    """Download-Adresse des gebauten Programms im Release „werkzeuge“."""
    plattform = plattform or sys.platform
    system = "windows" if plattform.startswith("win") else "linux" if plattform.startswith("linux") else "macos"
    return f"https://github.com/{upd.REPO}/releases/download/{WERKZEUG_RELEASE}/{wz.programm}-{system}-x64.zip"


# --------------------------------------------------------------------------
# Installieren, pruefen, entfernen
# --------------------------------------------------------------------------
def _pruefen(key: str) -> str:
    """Das frisch installierte Werkzeug laden bzw. aufrufen; Rueckgabe die
    Version, die es selbst nennt."""
    wz = WERKZEUGE[key]
    if wz.modul:
        importlib.invalidate_caches()
        importlib.import_module(wz.modul)
        oben = sys.modules[wz.modul.split(".")[0]]
        return str(getattr(oben, "__version__", "") or getattr(oben, "GMSH_API_VERSION", "") or "?")
    exe = programm(key)
    if not exe:
        raise WerkzeugFehler(f"{wz.programm} fehlt nach dem Entpacken")
    try:
        r = subprocess.run([exe, "-h"], capture_output=True, text=True, timeout=60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as ex:
        raise WerkzeugFehler(f"{wz.programm} lässt sich nicht starten: {ex}") from ex
    text = (r.stdout or "") + (r.stderr or "")
    if "mmg" not in text.lower():
        raise WerkzeugFehler(f"{wz.programm} antwortet nicht wie erwartet: {text[:200]!r}")
    m = re.search(r"(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else "?"


def installieren(key: str, fortschritt: Callable = None, timeout: float = 60.0) -> dict:
    """Ein Werkzeug von seiner Quelle laden, ablegen, aktivieren und pruefen.

    ``fortschritt(text, anteil)`` wie beim Rechen-Worker (anteil 0…1 oder
    None). Rueckgabe der neue Stand (stand.json) mit ``neustart=True``, wenn
    das Modul in diesem Prozess schon geladen war - dann wirkt die neue
    Fassung erst nach einem Neustart.
    """
    if key not in WERKZEUGE:
        raise WerkzeugFehler(f"unbekanntes Werkzeug {key!r}; bekannt: {', '.join(WERKZEUGE)}")
    wz = WERKZEUGE[key]
    melden = fortschritt or (lambda text, anteil=None: None)
    ziel = werkzeug_ordner(key)
    neu = ziel + ".neu"
    shutil.rmtree(neu, ignore_errors=True)
    os.makedirs(os.path.join(neu, "downloads"))
    schritte = max(1, len(wz.pakete) or 1)
    vorher_geladen = bool(wz.modul) and wz.modul.split(".")[0] in sys.modules
    pakete, quellen, dateien = {}, [], []
    try:
        if wz.pakete:
            for i, paket in enumerate(wz.pakete):
                melden(f"{wz.name}: {paket} bei PyPI nachschlagen …", i / schritte)
                version, liste = _pypi(paket, timeout=min(timeout, 30.0))
                rad = rad_wahl(liste)
                mb = float(rad.get("size", 0) or 0) / 1e6
                datei = os.path.join(neu, "downloads", str(rad["filename"]))

                def lauf(geladen, gesamt, i=i, paket=paket, version=version, mb=mb):
                    g = gesamt or (mb * 1e6) or 1
                    melden(f"{wz.name}: {paket} {version} laden – {geladen / 1e6:.0f} von {g / 1e6:.0f} MB",
                           (i + 0.9 * min(1.0, geladen / g)) / schritte)

                melden(f"{wz.name}: {paket} {version} laden ({rad['filename']}, {mb:.0f} MB)", i / schritte)
                _laden(str(rad["url"]), datei, lauf, timeout)
                soll = str(rad.get("digests", {}).get("sha256", "") or "")
                if soll and _sha256(datei) != soll:
                    raise WerkzeugFehler(f"{rad['filename']}: Prüfsumme stimmt nicht (Download beschädigt?)")
                melden(f"{wz.name}: {paket} {version} entpacken …", (i + 0.95) / schritte)
                dateien += rad_entpacken(datei, neu)
                os.remove(datei)
                pakete[paket] = version
                quellen.append(str(rad["url"]))
            version = pakete[wz.pakete[0]]
        else:
            url = programm_url(wz)
            datei = os.path.join(neu, "downloads", os.path.basename(url))
            melden(f"{wz.name}: {os.path.basename(url)} laden …", 0.0)
            _laden(url, datei, lambda g, t: melden(f"{wz.name}: {g / 1e6:.1f} MB geladen", 0.9 * min(1.0, g / (t or 1))),
                   timeout)
            melden(f"{wz.name}: entpacken …", 0.95)
            dateien += archiv_entpacken(datei, os.path.join(neu, "bin"))
            os.remove(datei)
            quellen.append(url)
            version = "?"
            q = os.path.join(neu, "bin", "QUELLE.txt")
            if os.path.isfile(q):
                with open(q, encoding="utf-8", errors="replace") as f:
                    m = re.search(r"(\d+\.\d+\.\d+)", f.readline())
                version = m.group(1) if m else "?"
        shutil.rmtree(os.path.join(neu, "downloads"), ignore_errors=True)
        neuer_stand = {"werkzeug": key, "version": version, "pakete": pakete, "quellen": quellen,
                       "datum": time.strftime("%Y-%m-%dT%H:%M:%S"), "python": f"{sys.version_info[0]}.{sys.version_info[1]}",
                       "plattform": sys.platform, "dateien": len(dateien)}
        with open(os.path.join(neu, "stand.json"), "w", encoding="utf-8") as f:
            json.dump(neuer_stand, f, ensure_ascii=False, indent=1)
        # Alte Fassung weg, neue an ihren Platz
        _deaktivieren(key)
        if os.path.isdir(ziel):
            _entfernen_ordner(ziel)
        os.replace(neu, ziel)
    except Exception:
        shutil.rmtree(neu, ignore_errors=True)
        raise
    aktivieren()
    melden(f"{wz.name}: prüfen …", 0.98)
    try:
        gemeldet = _pruefen(key)
    except Exception as ex:                        # noqa: BLE001
        entfernen(key)
        raise WerkzeugFehler(f"{wz.name} wurde geladen, lässt sich aber nicht nutzen – wieder entfernt: {ex}") from ex
    neuer_stand["gemeldet"] = gemeldet
    neuer_stand["neustart"] = vorher_geladen
    with open(os.path.join(ziel, "stand.json"), "w", encoding="utf-8") as f:
        json.dump(neuer_stand, f, ensure_ascii=False, indent=1)
    melden(f"{wz.name} {version} installiert" + (" – wirksam nach dem Neustart" if vorher_geladen else ""), 1.0)
    return neuer_stand


def _entfernen_ordner(ziel: str) -> bool:
    """Ordner loeschen; ist etwas gesperrt (geladene DLL), bleibt der Rest
    ohne stand.json stehen und faellt beim naechsten aktivieren()."""
    try:
        os.remove(os.path.join(ziel, "stand.json"))
    except OSError:
        pass
    shutil.rmtree(ziel, ignore_errors=True)
    if os.path.isdir(ziel):
        try:
            os.replace(ziel, ziel + ".alt-" + str(int(time.time() * 1000)))
        except OSError:
            return False
    return True


def entfernen(key: str) -> str:
    """Ein Werkzeug entfernen. Rueckgabe eine Meldung fuer das Protokoll."""
    if key not in WERKZEUGE:
        raise WerkzeugFehler(f"unbekanntes Werkzeug {key!r}")
    ziel = werkzeug_ordner(key)
    _deaktivieren(key)
    if not os.path.isdir(ziel):
        return f"{WERKZEUGE[key].name}: nicht installiert"
    if _entfernen_ordner(ziel):
        return f"{WERKZEUGE[key].name} entfernt"
    return (f"{WERKZEUGE[key].name} entfernt; Dateien sind noch in Gebrauch und "
            "verschwinden beim nächsten Programmstart")
