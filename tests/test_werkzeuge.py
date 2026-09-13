"""Werkzeuge nachladen (gmsh, Netgen, MMG3D) ohne pip: Radwahl nach Python
und Plattform, Entpacken in die Ordnung einer Python-Umgebung mit passendem
RECORD, Aktivieren ueber sys.path, Stand, Entfernen auch bei gesperrten
Dateien - alles ohne Netz (PyPI-Antwort, Download und Pruefung sind
ausgetauscht).

Mit STATIK3D_NETZTEST=1 laedt die Suite gmsh und Netgen wirklich von PyPI
in einen Wegwerfordner und vernetzt damit in einem eigenen Prozess (siehe
test_netz_wirklich; Messwerte im Benutzerhandbuch, Netzeinstellungen).
"""
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from statik3d import werkzeuge as wz                             # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:70s} {detail}")


def _rad(ordner, name, version, dateien, py="py3", abi="none", plat="win_amd64"):
    """Ein kuenstliches Rad schreiben; dateien = {Pfad im Rad: Bytes}."""
    p = os.path.join(ordner, f"{name}-{version}-{py}-{abi}-{plat}.whl")
    with zipfile.ZipFile(p, "w") as z:
        for k, v in dateien.items():
            z.writestr(k, v)
        z.writestr(f"{name}-{version}.dist-info/METADATA",
                   f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
        z.writestr(f"{name}-{version}.dist-info/RECORD", "")
    return p


class Wegwerf:
    """Wegwerfordner als Werkzeugordner; sys.path, sys.modules und die
    austauschbaren Funktionen des Moduls werden hinterher zurueckgesetzt."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="statik3d_werkzeuge_")
        self.env = os.environ.get("STATIK3D_WERKZEUGE")
        os.environ["STATIK3D_WERKZEUGE"] = self.tmp
        self.path = list(sys.path)
        self.module = set(sys.modules)
        self.funktionen = {k: getattr(wz, k) for k in ("_pypi", "_laden", "_pruefen")}
        self.werkzeuge = dict(wz.WERKZEUGE)
        return self.tmp

    def __exit__(self, *a):
        sys.path[:] = self.path
        for k in list(sys.modules):
            if k not in self.module and k.startswith("paket_probe"):
                del sys.modules[k]
        for k, f in self.funktionen.items():
            setattr(wz, k, f)
        wz.WERKZEUGE.clear()
        wz.WERKZEUGE.update(self.werkzeuge)
        if self.env is None:
            os.environ.pop("STATIK3D_WERKZEUGE", None)
        else:
            os.environ["STATIK3D_WERKZEUGE"] = self.env
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def test_radwahl():
    def eintrag(name, art="bdist_wheel", yanked=False):
        return {"filename": name, "url": "https://files/" + name, "size": 1, "packagetype": art, "yanked": yanked}

    liste = [eintrag("netgen_mesher-6.2.2607-cp310-cp310-win_amd64.whl"),
             eintrag("netgen_mesher-6.2.2607-cp311-cp311-win_amd64.whl"),
             eintrag("netgen_mesher-6.2.2607-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"),
             eintrag("netgen_mesher-6.2.2607-cp311-cp311-macosx_10_15_universal2.whl"),
             eintrag("netgen_mesher-6.2.2607-cp312-cp312-win_amd64.whl", yanked=True),
             eintrag("netgen_mesher-6.2.2607.tar.gz", art="sdist")]
    w = wz.rad_wahl(liste, (3, 11), "win32", "AMD64")
    check("Windows, Python 3.11: das cp311-win_amd64-Rad", w["filename"].endswith("cp311-cp311-win_amd64.whl"), w["filename"])
    w = wz.rad_wahl(liste, (3, 11), "linux", "x86_64")
    check("Linux x86_64: das manylinux-Rad", "manylinux" in w["filename"], w["filename"])
    w = wz.rad_wahl(liste, (3, 11), "darwin", "arm64")
    check("macOS arm64: das universal2-Rad", "universal2" in w["filename"], w["filename"])
    try:
        wz.rad_wahl(liste, (3, 12), "win32", "AMD64")
        check("zurueckgezogenes (yanked) Rad zaehlt nicht - Python 3.12 unter Windows findet keins", False)
    except wz.WerkzeugFehler as ex:
        check("zurueckgezogenes (yanked) Rad zaehlt nicht - Python 3.12 unter Windows findet keins",
              "3.12" in str(ex) and "cp312" in str(ex), str(ex)[:120])
    try:
        wz.rad_wahl(liste, (3, 11), "win32", "ARM64")
        check("Windows ARM64 ohne win_arm64-Rad: Fehler nennt die Angebote", False)
    except wz.WerkzeugFehler as ex:
        check("Windows ARM64 ohne win_arm64-Rad: Fehler nennt die Angebote", "angeboten" in str(ex))
    gmsh = [eintrag("gmsh-4.15.2-py2.py3-none-win_amd64.whl"), eintrag("gmsh-4.15.2-py2.py3-none-manylinux_2_24_x86_64.whl"),
            eintrag("gmsh-4.15.2-py2.py3-none-macosx_12_0_arm64.whl")]
    check("py2.py3-Rad passt zu jeder Python-3-Version (gmsh, Windows)",
          wz.rad_wahl(gmsh, (3, 13), "win32", "AMD64")["filename"].endswith("win_amd64.whl"))
    check("py2.py3-Rad unter Linux: manylinux x86_64",
          "manylinux" in wz.rad_wahl(gmsh, (3, 11), "linux", "x86_64")["filename"])
    beide = [eintrag("p-1.0-py3-none-win_amd64.whl"), eintrag("p-1.0-cp311-cp311-win_amd64.whl")]
    check("ein Rad fuer genau diese Python-Version geht vor dem py3-Rad",
          "cp311" in wz.rad_wahl(beide, (3, 11), "win32", "AMD64")["filename"])
    check("rad_passt: Quelltextarchiv und Fremdplattform fallen durch",
          not wz.rad_passt("p-1.0.tar.gz", (3, 11), "win32", "AMD64")
          and not wz.rad_passt("p-1.0-py3-none-win_amd64.whl", (3, 11), "linux", "x86_64"))


def test_entpacken_und_aktivieren():
    with Wegwerf() as tmp:
        rad = _rad(tmp, "paket_probe", "1.2.3", {
            "paket_probe/__init__.py": b"__version__ = '1.2.3'\n",
            "paket_probe-1.2.3.data/data/Lib/probe.dll": b"dll",
            "paket_probe-1.2.3.data/data/bin/TKProbe.dll": b"occ",
            "paket_probe-1.2.3.data/scripts/probe": b"#!python\n",
            "paket_probe-1.2.3.data/headers/probe.h": b"//",
            "paket_probe-1.2.3.data/purelib/probe_rein.py": b"x = 1\n",
        })
        ziel = os.path.join(tmp, "probe_ziel")
        geschrieben = wz.rad_entpacken(rad, ziel)
        site = os.path.join(ziel, "Lib", "site-packages")
        soll = [os.path.join(site, "paket_probe", "__init__.py"), os.path.join(ziel, "Lib", "probe.dll"),
                os.path.join(ziel, "bin", "TKProbe.dll"), os.path.join(ziel, "Scripts", "probe"),
                os.path.join(ziel, "include", "probe.h"), os.path.join(site, "probe_rein.py"),
                os.path.join(site, "paket_probe-1.2.3.dist-info", "METADATA")]
        check("Python-Anteil unter Lib/site-packages, Daten unter Lib und bin, Skripte unter Scripts, Header unter include",
              all(os.path.isfile(p) for p in soll) and len(geschrieben) == 8,
              str([p for p in soll if not os.path.isfile(p)]) + f" {len(geschrieben)}")
        with open(os.path.join(site, "paket_probe-1.2.3.dist-info", "RECORD"), encoding="utf-8") as f:
            record = f.read()
        check("RECORD nennt die Dateien relativ zu site-packages wie pip (../probe.dll, ../../bin/TKProbe.dll)",
              "paket_probe/__init__.py,," in record and "../probe.dll,," in record
              and "../../bin/TKProbe.dll,," in record and "../../Scripts/probe,," in record, record[:200])
        sys.path.insert(0, site)
        importlib.invalidate_caches()
        import importlib.metadata as md
        tk = [f for f in md.files("paket_probe") if f.match("*TK*")]
        p = tk[0].locate() if tk else None
        check("importlib.metadata findet die OCC-Bibliothek ueber RECORD (so sucht Netgen)",
              p is not None and os.path.isfile(p) and os.path.basename(str(p)) == "TKProbe.dll", str(p))
        check("Version aus den Metadaten", md.version("paket_probe") == "1.2.3")
        sys.path.remove(site)
        boese = _rad(tmp, "boese", "1.0", {"../hinaus.py": b""})
        try:
            wz.rad_entpacken(boese, os.path.join(tmp, "boese_ziel"))
            check("ein Rad mit ../-Pfad wird abgewiesen", False)
        except wz.WerkzeugFehler as ex:
            check("ein Rad mit ../-Pfad wird abgewiesen", "unzul" in str(ex))
        # Programmarchiv flach ablegen
        archiv = os.path.join(tmp, "mmg3d_O3-windows-x64.zip")
        with zipfile.ZipFile(archiv, "w") as z:
            z.writestr("mmg3d_O3.exe", b"MZ")
            z.writestr("LICENSE", b"LGPL")
            z.writestr("QUELLE.txt", "MMG v5.8.0\n")
        bin_ = os.path.join(tmp, "mmg3d", "bin")
        wz.archiv_entpacken(archiv, bin_)
        check("Programmarchiv: Dateien liegen flach unter bin",
              all(os.path.isfile(os.path.join(bin_, n)) for n in ("mmg3d_O3.exe", "LICENSE", "QUELLE.txt")))


def _quelle_einrichten(tmp, version, init=b"__version__ = '2.0'\n"):
    """PyPI-Antwort und Download durch ein Rad aus dem Wegwerfordner ersetzen."""
    quelle = os.path.join(tmp, "quelle")
    os.makedirs(quelle, exist_ok=True)
    rad = _rad(quelle, "paket_probe", version, {"paket_probe/__init__.py": init})
    with open(rad, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    eintrag = {"filename": os.path.basename(rad), "url": "file:///" + rad.replace(os.sep, "/"),
               "size": os.path.getsize(rad), "packagetype": "bdist_wheel", "digests": {"sha256": sha}}
    wz._pypi = lambda paket, timeout=0.0: (version, [eintrag])

    def laden(url, ziel, fortschritt=None, timeout=0.0):
        shutil.copy(rad, ziel)
        if fortschritt:
            fortschritt(os.path.getsize(rad), os.path.getsize(rad))
        return ziel
    wz._laden = laden
    wz.WERKZEUGE["probe"] = wz.Werkzeug("probe", "Probe", "Vernetzer", "MIT", "Wegwerfordner",
                                        pakete=("paket_probe",), modul="paket_probe")
    return eintrag


def test_installieren_ohne_netz():
    with Wegwerf() as tmp:
        eintrag = _quelle_einrichten(tmp, "2.0")
        meldungen = []
        s = wz.installieren("probe", fortschritt=lambda t, a=None: meldungen.append((t, a)))
        ziel = os.path.join(tmp, "probe")
        check("installiert: stand.json mit Version, Paketen und Quelle",
              s["version"] == "2.0" and s["pakete"] == {"paket_probe": "2.0"} and s["quellen"] == [eintrag["url"]]
              and wz.stand("probe") is not None and wz.stand("probe")["version"] == "2.0", str(s)[:160])
        check("die Pruefung hat das Modul aus dem Werkzeugordner geladen und seine Version gemeldet",
              s.get("gemeldet") == "2.0" and "paket_probe" in sys.modules
              and sys.modules["paket_probe"].__file__.startswith(ziel), str(s.get("gemeldet")))
        check("site-packages des Werkzeugs steht in sys.path; kein Rest .neu, keine downloads",
              wz.site_ordner("probe") in sys.path and not os.path.exists(ziel + ".neu")
              and not os.path.isdir(os.path.join(ziel, "downloads")))
        check("Fortschritt: laden, entpacken, pruefen, zuletzt Anteil 1,0",
              any("laden" in t for t, _ in meldungen) and any("entpacken" in t for t, _ in meldungen)
              and meldungen[-1][1] == 1.0 and "installiert" in meldungen[-1][0], str(meldungen[-1]))
        check("stand_alle und bericht nennen das Werkzeug",
              wz.stand_alle()["probe"]["version"] == "2.0" and "Probe" in wz.bericht() and "Version 2.0" in wz.bericht())
        check("neustart=False beim ersten Laden; ein zweites Installieren meldet neustart=True (Modul war geladen)",
              s["neustart"] is False and wz.installieren("probe")["neustart"] is True)
        # Pruefsumme falsch: nichts bleibt liegen
        alt = wz._pypi
        wz._pypi = lambda paket, timeout=0.0: ("2.1", [dict(eintrag, digests={"sha256": "00" * 32})])
        try:
            wz.installieren("probe")
            check("falsche Pruefsumme wird abgewiesen", False)
        except wz.WerkzeugFehler as ex:
            check("falsche Pruefsumme wird abgewiesen; die alte Fassung bleibt, kein .neu",
                  "Prüfsumme" in str(ex) and wz.stand("probe")["version"] == "2.0" and not os.path.exists(ziel + ".neu"),
                  str(ex)[:100])
        wz._pypi = alt
        # Pruefung scheitert: wieder entfernt
        wz._pruefen = lambda key: (_ for _ in ()).throw(RuntimeError("Import kaputt"))
        try:
            wz.installieren("probe")
            check("scheitert die Pruefung, wird das Werkzeug wieder entfernt", False)
        except wz.WerkzeugFehler as ex:
            check("scheitert die Pruefung, wird das Werkzeug wieder entfernt",
                  "wieder entfernt" in str(ex) and wz.stand("probe") is None and wz.site_ordner("probe") not in sys.path,
                  str(ex)[:100])
        wz._pruefen = lambda key: "2.0"
        try:
            wz.installieren("gibtsnicht")
            check("unbekanntes Werkzeug wird abgewiesen", False)
        except wz.WerkzeugFehler as ex:
            check("unbekanntes Werkzeug wird abgewiesen", "gmsh" in str(ex))
        # Entfernen bei gesperrter Datei: Stand weg, Rest faellt beim naechsten aktivieren()
        wz.installieren("probe")
        gesperrt = open(os.path.join(wz.site_ordner("probe"), "paket_probe", "__init__.py"), "rb")
        try:
            msg = wz.entfernen("probe")
            check("entfernen mit offener Datei: sofort 'nicht installiert', Meldung nennt den Rest",
                  wz.stand("probe") is None and wz.site_ordner("probe") not in sys.path
                  and ("Gebrauch" in msg or (os.name != "nt" and "entfernt" in msg)), msg)
        finally:
            gesperrt.close()
        wz.aktivieren()
        reste = [n for n in os.listdir(tmp) if n.startswith("probe")]
        check("aktivieren() raeumt den Rest weg", not reste, str(reste))
        check("entfernen ohne Installation meldet 'nicht installiert'", "nicht installiert" in wz.entfernen("probe"))


def test_programm_und_mmg3d_pfad():
    with Wegwerf() as tmp:
        from statik3d import vernetzer_extern as vx
        check("ohne Installation: kein Programm, MMG3D nur aus dem Suchpfad",
              wz.programm("mmg3d") == "" and vx.mmg3d_programm() == (vx.shutil.which("mmg3d_O3") or vx.shutil.which("mmg3d_O3.exe") or ""))
        bin_ = os.path.join(tmp, "mmg3d", "bin")
        os.makedirs(bin_)
        exe = os.path.join(bin_, "mmg3d_O3.exe" if os.name == "nt" else "mmg3d_O3")
        with open(exe, "wb") as f:
            f.write(b"MZ")
        with open(os.path.join(tmp, "mmg3d", "stand.json"), "w", encoding="utf-8") as f:
            json.dump({"werkzeug": "mmg3d", "version": "5.8.0"}, f)
        check("installiertes MMG3D: programm() nennt bin/mmg3d_O3", wz.programm("mmg3d") == exe, wz.programm("mmg3d"))
        check("vernetzer_extern findet es ohne Pfadangabe, verfuegbar() meldet MMG3D da",
              vx.mmg3d_programm() == exe and vx.verfuegbar()["mmg3d"][1])
        eigen = os.path.join(tmp, "eigenes_mmg3d.exe")
        with open(eigen, "wb") as f:
            f.write(b"MZ")
        check("ein ausdruecklich angegebener Pfad geht vor", vx.mmg3d_programm(eigen) == eigen)
        check("programm_url: Release werkzeuge, Datei je System",
              wz.programm_url(wz.WERKZEUGE["mmg3d"], "win32").endswith("/releases/download/werkzeuge/mmg3d_O3-windows-x64.zip")
              and wz.programm_url(wz.WERKZEUGE["mmg3d"], "linux").endswith("mmg3d_O3-linux-x64.zip"))
        check("Werkzeugordner: STATIK3D_WERKZEUGE geht vor, sonst Benutzerdaten/Statik3D/Werkzeuge",
              wz.ordner() == tmp and wz.datenordner().endswith("Statik3D"))
        check("Tabelle: gmsh GPL Vernetzer, Netgen LGPL Vernetzer (zwei Pakete), MMG3D LGPL Nachbesserer (Programm)",
              wz.WERKZEUGE["gmsh"].lizenz == "GPL" and wz.WERKZEUGE["netgen"].pakete == ("netgen-mesher", "netgen-occt")
              and wz.WERKZEUGE["mmg3d"].programm == "mmg3d_O3" and wz.WERKZEUGE["mmg3d"].aufgabe == "Nachbesserer")
        mu = wz.WERKZEUGE["mumps"]
        check("MUMPS: Gleichungsloeser, CeCILL-C, eigenes Rad aus dem Release mit 64-stelliger Pruefsumme",
              mu.aufgabe == "Gleichungslöser" and mu.lizenz == "CeCILL-C" and mu.rad.endswith("win_amd64.whl")
              and len(mu.rad_sha256) == 64 and all(c in "0123456789abcdef" for c in mu.rad_sha256)
              and wz.release_url(mu.rad).endswith("/releases/download/werkzeuge/" + mu.rad), str(mu)[:120])
        check("veraltet(): ohne Installation nein", not wz.veraltet("mumps"))


PROBE = r"""
import sys, time, numpy as np
site = sys.argv[1]; was = sys.argv[2]
sys.path.insert(0, site)
from statik3d import vernetzer_extern as vx
P = np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]], float)
T = np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
t0 = time.time()
if was == "gmsh":
    import gmsh
    assert gmsh.__file__.startswith(site), gmsh.__file__
    Pn, TET = vx.gmsh_tetraedern(P, T, 0.25)
else:
    import netgen
    assert netgen.__file__.startswith(site), netgen.__file__
    Pn, TET = vx.netgen_tetraedern(P, T, 0.25)
print("TETS", len(TET), "PUNKTE", len(Pn), "ZEIT", round(time.time() - t0, 2))
"""


def test_netz_wirklich():
    """Nur mit STATIK3D_NETZTEST=1: gmsh und Netgen wirklich von PyPI laden."""
    if os.environ.get("STATIK3D_NETZTEST") != "1":
        print("     uebersprungen (STATIK3D_NETZTEST=1 setzt den Netztest in Gang)")
        return
    with Wegwerf() as tmp:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for key in ("gmsh", "netgen"):
            t0 = time.time()
            s = wz.installieren(key, fortschritt=lambda t, a=None: print("    ", t))
            dauer = time.time() - t0
            groesse = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(wz.werkzeug_ordner(key)) for f in fs) / 1e6
            check(f"{key} von PyPI geladen: Version {s['version']}, {groesse:.0f} MB in {dauer:.0f} s",
                  wz.stand(key) is not None, f"{s.get('gemeldet')}")
            r = subprocess.run([sys.executable, "-c", PROBE, wz.site_ordner(key), key], cwd=here,
                               capture_output=True, text=True, timeout=600)
            check(f"{key} aus dem Werkzeugordner vernetzt den Einheitswuerfel in einem eigenen Prozess",
                  r.returncode == 0 and "TETS" in r.stdout, (r.stdout.strip().splitlines() or [r.stderr[-300:]])[-1])


def test_einstellungen_gespeichert():
    """Loeser, Threads und „MUMPS nachladen" ueberleben den Programmstart
    (Benutzerdaten/Statik3D/einstellungen.json; STATIK3D_EINSTELLUNGEN fuer
    Pruefungen)."""
    from statik3d import parallel
    alt_env = os.environ.get("STATIK3D_EINSTELLUNGEN")
    alt = {k: getattr(parallel.settings(), k) for k in parallel.GESPEICHERT}
    tmp = tempfile.mkdtemp(prefix="statik3d_einst_")
    try:
        os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(tmp, "unter", "einstellungen.json")
        check("ohne Datei: laden liefert nichts und aendert nichts",
              parallel.einstellungen_laden() == {} and parallel.settings().solver_threads == alt["solver_threads"])
        parallel.configure(solver_backend="mumps", solver_threads=4, mumps_nachladen=False)
        p = parallel.einstellungen_speichern()
        parallel.configure(solver_backend="auto", solver_threads=0, mumps_nachladen=True)
        d = parallel.einstellungen_laden()
        check("gespeichert und wieder geladen: Loeser mumps, 4 Threads, Nachladen aus",
              os.path.isfile(p) and parallel.settings().solver_backend == "mumps"
              and parallel.settings().solver_threads == 4 and parallel.settings().mumps_nachladen is False
              and set(d) == set(parallel.GESPEICHERT), str(d))
        with open(p, "w", encoding="utf-8") as f:
            f.write("kaputt")
        check("unlesbare Datei: laden liefert nichts, die Einstellungen bleiben",
              parallel.einstellungen_laden() == {} and parallel.settings().solver_threads == 4)
    finally:
        parallel.configure(**alt)
        if alt_env is None:
            os.environ.pop("STATIK3D_EINSTELLUNGEN", None)
        else:
            os.environ["STATIK3D_EINSTELLUNGEN"] = alt_env
        shutil.rmtree(tmp, ignore_errors=True)


MUMPS_PROBE = r"""
import sys, time
site = sys.argv[1]
sys.path.insert(0, site)
import mumps
assert mumps.__file__.startswith(site), mumps.__file__
from statik3d import werkzeuge
print("BESCHREIBUNG", werkzeuge.mumps_probe(mumps))
if len(sys.argv) > 2:
    print("HALTE", flush=True)
    time.sleep(float(sys.argv[2]))
"""


def test_mumps_rad_offline():
    """Das echte Rad aus packaging/ ueber die lokale Quelle in einen
    Wegwerfordner: entpacken, im eigenen Prozess laden, rechnen (1 2 3 4 5);
    falsche Pruefsumme -> abgelehnt und aufgeraeumt; Entfernen bei geladener
    DLL -> Rest faellt beim naechsten aktivieren()."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rad = os.path.join(here, "packaging", wz.WERKZEUGE["mumps"].rad)
    if not sys.platform.startswith("win") or not os.path.isfile(rad):
        print("     kein Windows oder kein Rad in packaging/ - uebersprungen")
        return
    alt_quelle = os.environ.get("STATIK3D_WERKZEUG_QUELLE")
    os.environ["STATIK3D_WERKZEUG_QUELLE"] = os.path.join(here, "packaging")
    try:
        with Wegwerf() as tmp:
            wz._pruefen = lambda key: "5.8.2"        # die echte Pruefung laeuft unten im eigenen Prozess
            meldungen = []
            s = wz.installieren("mumps", fortschritt=lambda t, a=None: meldungen.append(t))
            site = wz.site_ordner("mumps")
            check("Rad entpackt: Version 5.8.2 aus dem Dateinamen, Rad und Pruefsumme im Stand, Paket unter site-packages",
                  s["version"] == "5.8.2" and s["rad"] == wz.WERKZEUGE["mumps"].rad
                  and s["sha256"] == wz.WERKZEUGE["mumps"].rad_sha256
                  and os.path.isfile(os.path.join(site, "mumps", "__init__.py"))
                  and os.path.isdir(os.path.join(site, "mumps", "_lib")) and os.path.isdir(os.path.join(site, "mumps", "LIZENZ")),
                  str(s)[:160])
            check("nicht veraltet, solange die Pruefsumme die des Programms ist", not wz.veraltet("mumps"))
            r = subprocess.run([sys.executable, "-c", MUMPS_PROBE, site], cwd=here, capture_output=True, text=True,
                               timeout=300, env=dict(os.environ, PYTHONUTF8="1"))
            check("MUMPS aus dem Werkzeugordner laedt seine DLLs und rechnet 1 2 3 4 5 (eigener Prozess)",
                  r.returncode == 0 and "BESCHREIBUNG MUMPS 5.8.2" in r.stdout,
                  (r.stdout.strip().splitlines() or [r.stderr[-300:]])[-1][:160])
            # veraltet: ein anderer Stand in stand.json
            with open(os.path.join(wz.werkzeug_ordner("mumps"), "stand.json"), encoding="utf-8") as f:
                d = json.load(f)
            d["sha256"] = "00" * 32
            with open(os.path.join(wz.werkzeug_ordner("mumps"), "stand.json"), "w", encoding="utf-8") as f:
                json.dump(d, f)
            check("ein anderes Rad im Stand: veraltet() sagt ja", wz.veraltet("mumps"))
            # Entfernen, waehrend ein Prozess die DLLs haelt
            halter = subprocess.Popen([sys.executable, "-c", MUMPS_PROBE, site, "60"], cwd=here,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                      env=dict(os.environ, PYTHONUTF8="1"))
            try:
                zeile = halter.stdout.readline()
                while zeile and "HALTE" not in zeile:
                    zeile = halter.stdout.readline()
                msg = wz.entfernen("mumps")
                # Windows loescht eine geladene DLL nicht; der Ordner wird dann
                # umbenannt (mumps.alt-<zeit>) oder bleibt stehen - so oder so
                # ist der Stand sofort weg und die DLL noch da
                reste = [n for n in os.listdir(tmp) if n.startswith("mumps")]
                dll_da = any(os.path.isfile(os.path.join(tmp, n, "Lib", "site-packages", "mumps", "_lib", "libdmumps_seq.dll"))
                             for n in reste)
                check("entfernen bei geladener DLL: Stand sofort weg, die DLL bleibt bis zum naechsten Start liegen",
                      wz.stand("mumps") is None and halter.poll() is None and dll_da and reste,
                      f"{msg}; Reste {reste}")
            finally:
                halter.kill()
                halter.wait(timeout=30)
            # Windows gibt die DLL erst kurz nach dem Prozessende frei
            for _ in range(100):
                wz.aktivieren()
                reste = [n for n in os.listdir(tmp) if n.startswith("mumps")]
                if not reste:
                    break
                time.sleep(0.1)
            check("aktivieren() raeumt den Rest weg, sobald die DLL frei ist", not reste, str(reste))
            # falsche Pruefsumme im Programm: abgelehnt, nichts bleibt liegen
            from dataclasses import replace
            wz.WERKZEUGE["mumps"] = replace(wz.WERKZEUGE["mumps"], rad_sha256="00" * 32)
            try:
                wz.installieren("mumps")
                check("falsche Pruefsumme im Programm: Installation abgelehnt", False)
            except wz.WerkzeugFehler as ex:
                check("falsche Pruefsumme im Programm: Installation abgelehnt, nichts bleibt liegen",
                      "Prüfsumme" in str(ex) and wz.stand("mumps") is None
                      and not os.path.exists(wz.werkzeug_ordner("mumps") + ".neu"), str(ex)[:100])
    finally:
        if alt_quelle is None:
            os.environ.pop("STATIK3D_WERKZEUG_QUELLE", None)
        else:
            os.environ["STATIK3D_WERKZEUG_QUELLE"] = alt_quelle


def main():
    for t in (test_radwahl, test_entpacken_und_aktivieren, test_installieren_ohne_netz,
              test_programm_und_mmg3d_pfad, test_einstellungen_gespeichert, test_mumps_rad_offline,
              test_netz_wirklich):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    sys.exit(main())
