"""
Test der Aktualisierung (statik3d.update) gegen einen lokalen Schein-GitHub-Server.
Aufruf:  python -m tests.test_update
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import update as upd  # noqa: E402

RESULTS = []
SHA = "0123456789abcdef0123456789abcdef01234567"


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:60s} {detail}")
    return ok


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Statikprogramm-main/statik3d/__init__.py", "__version__ = '9.9.9'\n")
        z.writestr("Statikprogramm-main/README.md", "neu\n")
        z.writestr("Statikprogramm-main/docs/Benutzerhandbuch.md", "# neu\n")
        z.writestr("Statikprogramm-main/Projekte/beispiel.json", "{}")
        z.writestr("Statikprogramm-main/.venv/x.txt", "x")
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    exe_bytes = b"MZ" + b"\0" * 1_100_000
    zip_bytes = _zip_bytes()

    def log_message(self, *a):
        pass

    def _send(self, data, ctype="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        if self.path.endswith("/releases/tags/latest"):
            self._send(json.dumps({"tag_name": "latest", "published_at": "2026-09-03T10:00:00Z",
                                   "body": f"Automatisch gebaut.\n\nbuild: {SHA}\n",
                                   "assets": [{"name": "Statik3D.exe", "size": len(self.exe_bytes),
                                               "browser_download_url": base + "/dl/Statik3D.exe"}]}).encode())
        elif self.path.endswith("/commits/main"):
            self._send(json.dumps({"sha": SHA, "commit": {"message": "Neues\n\nDetails",
                                   "committer": {"date": "2026-09-03T09:00:00Z"}}}).encode())
        elif self.path == "/dl/Statik3D.exe":
            self._send(self.exe_bytes, "application/octet-stream")
        elif self.path == "/dl/kaputt.exe":
            self._send(b"nicht MZ" * 200000, "application/octet-stream")
        elif self.path == "/dl/main.zip":
            self._send(self.zip_bytes, "application/zip")
        else:
            self.send_response(404)
            self.end_headers()


def test_befund_und_bat():
    """Update-Befund und Austauschskript."""
    import statik3d.update as upd
    txt = upd.diagnose(timeout=3)
    check("Befund nennt die Fassung", "Fassung" in txt and upd.__dict__["__doc__"] is not None,
          txt.splitlines()[1][:50])
    check("Befund nennt Ordner und Schreibrecht",
          "Schreibrecht" in txt and "Ordner" in txt)
    check("Befund nennt die Downloadadresse", upd.DOWNLOAD_URL in txt)

    # Austauschskript: Platzhalter, Wartezeit, Fehlerbehandlung
    bat = upd.UPDATE_BAT.format(exe=r"C:\Statik3D\Statik3D.exe",
                                new=r"C:\Statik3D\Statik3D.exe.new",
                                log=r"C:\Statik3D\statik3d_update.log")
    check("Skript: verzoegerte Erweiterung eingeschaltet",
          "enabledelayedexpansion" in bat)
    check("Skript: Zaehler mit ! statt % gelesen", "!n! lss 120" in bat, "!n!")
    check("Skript: Protokoll wird geschrieben", "statik3d_update.log" in bat)
    check("Skript: fehlende Datei wird gemeldet", "Die heruntergeladene Datei fehlt" in bat)
    check("Skript: Fehler beim Verschieben wird gemeldet", "errorlevel 1" in bat)
    check("Skript: startet danach neu", 'start "" "%EXE%"' in bat)

    # Ohne Schreibrecht wird abgelehnt, bevor 200 MB geladen werden.
    # Als root liefert os.access immer True - deshalb wird die Abfrage selbst
    # geprueft, nicht das Rechtesystem.
    import tempfile, os as _os, shutil as _sh
    d = tempfile.mkdtemp()
    exe = _os.path.join(d, "Statik3D.exe")
    with open(exe, "wb") as f:
        f.write(b"MZ" + b"\x00" * 10)
    echt = _os.access
    geladen = []
    echt_dl = upd.download

    def kein_recht(pfad, modus):
        if modus == _os.W_OK and _os.path.abspath(pfad) == _os.path.abspath(d):
            return False
        return echt(pfad, modus)

    def merker(*a, **kw):
        geladen.append(a)
        return echt_dl(*a, **kw)

    _os.access = kein_recht
    upd.download = merker
    try:
        info = upd.UpdateInfo("exe", "2.1.0", "aaaa", "bbbb", "", "http://x", 2_000_000)
        try:
            upd.apply_exe(info, restart=False, exe_path=exe)
            check("ohne Schreibrecht wird abgelehnt", False)
        except upd.UpdateError as ex:
            check("ohne Schreibrecht wird abgelehnt", "Schreibrecht" in str(ex),
                  str(ex)[:60])
        check("ohne Schreibrecht wird nichts geladen", not geladen,
              f"{len(geladen)} Downloads")
    finally:
        _os.access = echt
        upd.download = echt_dl
        _sh.rmtree(d, ignore_errors=True)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    api = base + "/repos/x/y"
    tmp = tempfile.mkdtemp(prefix="statik3d_upd_")
    try:
        b = upd.build_info()
        check("build_info liefert Version und Art", b["version"] == upd.__version__ and b["kind"] in ("exe", "source"))
        check("describe", "Statik3D" in upd.describe())
        # exe
        info = upd.check(api_url=api, kind="exe")
        check("check exe: neueste Version erkannt", info.kind == "exe" and info.latest_sha == SHA and info.available
              and info.url.endswith("/dl/Statik3D.exe") and info.size == len(Handler.exe_bytes))
        check("check exe: Meldung", "Neue Version" in info.message and SHA[:7] in info.message, info.message)
        exe = os.path.join(tmp, "Statik3D.exe")
        open(exe, "wb").write(b"MZalt")
        calls = []
        msg = upd.apply_exe(info, progress=lambda d, t: calls.append((d, t)), restart=False, exe_path=exe)
        new = exe + ".new"
        bat = os.path.join(tmp, "statik3d_update.bat")
        check("apply exe: neue Datei geladen, Fortschritt gemeldet",
              os.path.exists(new) and os.path.getsize(new) == len(Handler.exe_bytes) and calls and calls[-1][0] == calls[-1][1])
        text = open(bat, "rb").read()
        check("apply exe: Hilfsskript (CRLF, Pfade, Neustart)", b"\r\n" in text and exe.encode() in text
              and new.encode() in text and b'start "" "%EXE%"' in text and b"del" in text)
        check("apply exe: Meldung", "neu gestartet" in msg, msg)
        bad = upd.UpdateInfo("exe", "2", "", SHA, "", base + "/dl/kaputt.exe", 0, True)
        try:
            upd.apply_exe(bad, restart=False, exe_path=exe)
            check("apply exe: ungueltige Datei abgelehnt", False)
        except upd.UpdateError as ex:
            check("apply exe: ungueltige Datei abgelehnt", "kein Windows-Programm" in str(ex) and not os.path.exists(new + ".part"))
        # Quelle
        info = upd.check(api_url=api, kind="source")
        check("check Quelle: Commit erkannt", info.kind == "source" and info.latest_sha == SHA and info.notes == "Neues"
              and info.latest_date.startswith("2026-09-03"))
        root = os.path.join(tmp, "prog")
        os.makedirs(os.path.join(root, "statik3d"))
        os.makedirs(os.path.join(root, "Projekte"))
        open(os.path.join(root, "statik3d", "__init__.py"), "w").write("alt\n")
        open(os.path.join(root, "Projekte", "beispiel.json"), "w").write("meins")
        info.url = base + "/dl/main.zip"
        msg = upd.apply_source(info, restart=False, root=root)
        check("apply Quelle: Dateien ersetzt", "9.9.9" in open(os.path.join(root, "statik3d", "__init__.py")).read()
              and os.path.exists(os.path.join(root, "docs", "Benutzerhandbuch.md")), msg)
        check("apply Quelle: Projekte und .venv unangetastet",
              open(os.path.join(root, "Projekte", "beispiel.json")).read() == "meins" and not os.path.exists(os.path.join(root, ".venv")))
        stamp = open(os.path.join(root, "statik3d", "_build.py")).read()
        check("apply Quelle: Build-Stempel", f'BUILD_SHA = "{SHA}"' in stamp and "BUILD_DATE" in stamp)
        check("apply Quelle: Meldung Neustart", "neu starten" in msg.lower() or "neu" in msg, msg)
        # Vergleich mit installiertem Stand
        same = upd.UpdateInfo("source", "2", SHA, SHA, "", "", 0)
        same.available = same.latest_sha[:7] != same.current_sha[:7]
        check("gleicher Stand: kein Update", not same.available and "neuesten Stand" in same.message)
        cmd = upd.restart_command()
        check("Neustartbefehl", cmd and cmd[0] == sys.executable)
        test_befund_und_bat()
        # Fehlerfaelle
        try:
            upd.check(api_url="http://127.0.0.1:9/repos/x/y", kind="source", timeout=2)
            check("Kein Server: UpdateError", False)
        except upd.UpdateError as ex:
            check("Kein Server: UpdateError", "GitHub" in str(ex))
        check("Konstanten: Download-Link", upd.DOWNLOAD_URL.endswith("/releases/latest/download/Statik3D.exe"))
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(tmp, ignore_errors=True)
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
