"""Fremde Vernetzer (gmsh, Netgen) und die Nachbesserung (MMG3D): dieselbe
Huelle, Randpunkte bleiben, Tetraeder positiv, Volumen stimmt; was nicht
installiert ist, wird uebersprungen und gemeldet.

Gemessen (13.09.2026, Platte 1 x 0,6 x 0,2 m mit Bohrung r = 0,1 m, h = 50 mm,
Huelle 870 Punkte / 1 740 Dreiecke): gmsh 4 411 Tetraeder, Guete min 0,418;
Netgen 5 811, Guete min 0,493; alle Huellpunkte wiedergefunden.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from statik3d.model import Model, Material                    # noqa: E402
from statik3d import mesher3d as m3, vernetzer_extern as vx     # noqa: E402
from test_mesher3d import prisma, kreis_punkte, netzvolumen     # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:70s} {detail}")


def _platte():
    m = Model()
    m.add_material(Material.steel("S235"))
    k = prisma(m, [[(0, 0), (1, 0), (1, 0.6), (0, 0.6)], kreis_punkte(0.1, 24, 0.5, 0.3, umgekehrt=True)], 0.2)
    return m, k


def test_verfuegbarkeit_und_lizenz():
    da = vx.verfuegbar()
    check("die Auswahl nennt eigener, gmsh, netgen, mmg3d", set(da) == {"eigener", "gmsh", "netgen", "mmg3d"}, str(da))
    check("der eigene Vernetzer ist immer da", da["eigener"][1])
    check("gmsh ist als GPL, Netgen und MMG3D als LGPL gekennzeichnet, keiner in der exe",
          "GPL" in da["gmsh"][2] and "nicht in der exe" in da["gmsh"][2] and "LGPL" in da["netgen"][2]
          and "LGPL" in da["mmg3d"][2], str({k: v[2] for k, v in da.items()}))


def test_huelle_voran_und_orientierung():
    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.]])
    X = np.array([[0, 0, 1.], [0.2, 0.2, 0.2], [1, 0, 0], [0, 1, 0], [0, 0, 0]])
    TET = np.array([[4, 2, 3, 0], [4, 3, 2, 1]])          # zweiter verkehrt orientiert
    Pn, T2 = vx._huelle_voran(P, X, TET)
    check("Huellpunkte stehen voran, in ihrer Reihenfolge", np.allclose(Pn[:4], P) and len(Pn) == 5)
    V = m3.tetraedervolumen(Pn, T2)
    check("alle Tetraeder positiv orientiert", bool((V > 0).all()), str(np.round(V, 4)))
    try:
        vx._huelle_voran(P, X[1:], TET[:1] - 1)
        check("fehlende Huellpunkte werden abgewiesen", False)
    except RuntimeError as ex:
        check("fehlende Huellpunkte werden abgewiesen", "nicht erhalten" in str(ex))


def test_mesh_rundlauf():
    m, k = _platte()
    P, T, ber = m3.randschale(m, k, 0.1, [])
    Pn, TET, tb = m3.tetraedern(P, T, 0.1)[0], None, None
    Pn, TET, _b = m3.tetraedern(P, T, 0.1)
    pfad = os.path.join(tempfile.gettempdir(), "statik3d_probe_rundlauf.mesh")
    vx.mesh_schreiben(pfad, Pn, TET, T)
    X2, TET2, T2 = vx.mesh_lesen(pfad)
    os.remove(pfad)
    check("Medit-Datei: Punkte, Tetraeder und Dreiecke ueberleben Schreiben und Lesen",
          np.allclose(X2, Pn) and np.array_equal(TET2, np.asarray(TET, int)) and np.array_equal(T2, np.asarray(T, int)),
          f"{len(X2)} Punkte, {len(TET2)} Tetraeder, {len(T2)} Dreiecke")
    # "ohne Programm" heisst: weder ein eigener Pfad noch das nachgeladene aus
    # dem Werkzeugordner noch eines im Suchpfad - der Werkzeugordner des
    # Anwenders (seit 13.09.2026 mit MMG3D) darf hier nicht hineinspielen
    alt_wz = os.environ.get("STATIK3D_WERKZEUGE")
    alt_which = vx.shutil.which
    os.environ["STATIK3D_WERKZEUGE"] = tempfile.mkdtemp(prefix="statik3d_ohne_werkzeuge_")
    vx.shutil.which = lambda name: None
    try:
        vx.mmg3d_nachbessern(Pn, TET, T, 0.1, programm="C:/gibt/es/nicht/mmg3d_O3.exe")
        check("MMG3D ohne Programm: Meldung statt Absturz", False)
    except RuntimeError as ex:
        check("MMG3D ohne Programm: Meldung statt Absturz", "nicht gefunden" in str(ex), str(ex)[:60])
    finally:
        vx.shutil.which = alt_which
        if alt_wz is None:
            os.environ.pop("STATIK3D_WERKZEUGE", None)
        else:
            os.environ["STATIK3D_WERKZEUGE"] = alt_wz


#: Ein Kind, das meldet, ob es eine Konsole hat (0 = keine).
KONSOLENFRAGE = "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"

#: Der Fensterprozess dazwischen - er startet das Kind so, wie Statik3D es tut
KONSOLENPROBE = """import json, subprocess, sys
ziel, exe, kw = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
kw["capture_output"] = kw["text"] = True
r = subprocess.run([exe, "-c", %r], **kw)
open(ziel, "w").write(r.stdout.strip() or "?")
""" % KONSOLENFRAGE


def _konsole_im_kind(kw: dict) -> str:
    """Aus einem **Fensterprozess** (pythonw, wie die Statik3D-exe) ein
    Konsolenprogramm mit den Argumenten ``kw`` starten und melden, was dessen
    ``GetConsoleWindow()`` liefert: „0" heisst, es gibt kein Fenster.

    Der Umweg ueber pythonw ist der Kern der Sache: von einem Prozess **mit**
    Konsole erbt das Kind deren Fenster und es entsteht keines; erst ein
    Fensterprogramm - und das ist Statik3D - laesst Windows ein neues
    anlegen. Gemessen am 14.09.2026: ohne Schalter Fenstergriff 136842, mit
    CREATE_NO_WINDOW null.
    """
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        return ""
    ordner = tempfile.mkdtemp(prefix="statik3d_konsole_")
    skript = os.path.join(ordner, "probe.py")
    ziel = os.path.join(ordner, "antwort.txt")
    try:
        with open(skript, "w", encoding="utf-8") as fh:
            fh.write(KONSOLENPROBE)
        subprocess.run([pyw, skript, ziel, sys.executable, json.dumps(kw)], timeout=300)
        return open(ziel, encoding="utf-8").read().strip() if os.path.isfile(ziel) else "?"
    finally:
        shutil.rmtree(ordner, ignore_errors=True)


def test_kein_konsolenfenster():
    """Ein Fremdprogramm darf kein schwarzes Fenster aufmachen.

    Statik3D ist ein Fensterprogramm (die exe wird ohne Konsole gebaut).
    Startet ein Fensterprogramm ein **Konsolenprogramm**, legt Windows dafuer
    eine eigene Konsole an - beim Vernetzen mit Nachbesserung je Koerper eine
    (14.09.2026: „beim Vernetzen mit gmsh und MMG3D geht bei jedem Volumen
    eine Eingabeaufforderung auf").

    Gemessen wird nicht am Fenster, sondern am Kind: ``GetConsoleWindow()``
    ist dort null, wenn es keine Konsole hat - und der Elternprozess der
    Messung ist pythonw, damit die Lage dieselbe ist wie in der exe. Der
    zweite Teil nimmt die Argumente, mit denen der Nachbesserer MMG3D
    wirklich startet; ohne den Schalter kommt dort ein Fenstergriff heraus.
    """
    from statik3d import werkzeuge as wz
    zusatz = wz.ohne_fenster()
    if sys.platform != "win32":
        check("außerhalb von Windows gibt es keine Konsole zu unterdrücken", zusatz == {}, str(zusatz))
        return
    kein = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    check("unter Windows steht CREATE_NO_WINDOW in den Zusatzargumenten",
          bool(kein) and zusatz.get("creationflags", 0) & kein == kein, str(zusatz))
    grund = {"capture_output": True, "text": True, "timeout": 120}
    ohne = _konsole_im_kind(dict(grund))
    if not ohne:
        check("ohne pythonw lässt sich der Fensterprozess nicht nachstellen - Messung übersprungen", True)
        return
    check("aus einem Fensterprogramm heraus bekommt ein Konsolenprogramm ein eigenes Fenster",
          ohne not in ("0", "?"), f"GetConsoleWindow() = {ohne!r}")
    mit = _konsole_im_kind(dict(grund, **zusatz))
    check("mit den Zusatzargumenten entsteht keines", mit == "0", f"GetConsoleWindow() = {mit!r}")

    # 2) Mit **den** Argumenten, mit denen der Nachbesserer MMG3D startet
    gesehen = {}
    echt = subprocess.run

    def statt(befehl, **kw):
        gesehen["kw"] = kw
        raise RuntimeError("Probe: hier wird nicht weitergerechnet")

    P = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.]])
    TET = np.array([[0, 1, 2, 3]])
    T = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]])
    vx.subprocess.run = statt
    try:
        vx.mmg3d_nachbessern(P, TET, T, 0.5, programm=sys.executable)
    except RuntimeError:
        pass
    finally:
        vx.subprocess.run = echt
    kw = gesehen.get("kw", {})
    mmg = _konsole_im_kind(dict(kw, timeout=120)) if kw else ""
    check("MMG3D wird so gestartet, dass sein Fenster gar nicht erst entsteht",
          mmg == "0", f"Argumente {sorted(kw)}, GetConsoleWindow() = {mmg!r}")


def _fremd(name, fn):
    m, k = _platte()
    P, T, ber = m3.randschale(m, k, 0.05, [])
    Pn, TET = fn(P, T, 0.05)
    V = m3.tetraedervolumen(Pn, TET)
    q = m3.guete(Pn, TET)
    check(f"{name}: Huellpunkte voran und erhalten", np.allclose(Pn[:len(P)], P), f"{len(P)} Punkte")
    check(f"{name}: Tetraeder positiv, Volumen = Huellvolumen",
          bool((V > 0).all()) and abs(V.sum() - ber["volumen"]) < 1e-6 * ber["volumen"],
          f"{len(TET)} Tetraeder, {V.sum():.5f} / {ber['volumen']:.5f} m³")
    check(f"{name}: kein Splitter (Guete min ueber 0,1)", float(q.min()) > 0.1, f"min {q.min():.3f}")
    # ueber die Netzeinstellungen bis ins Modell
    m2, k2 = _platte()
    m2.netz.ziellaenge = 0.05
    m2.netz.dichte = "eigene"
    m2.netz.vernetzer = name
    log = []
    els = m3.mesh_koerper_frei(m2, k2, log=log)
    check(f"{name} ueber die Netzeinstellungen: Koerper vernetzt, Protokoll nennt den Vernetzer",
          len(els) > 100 and any(name in z.lower() for z in log)
          and abs(netzvolumen(m2, els) - ber["volumen"]) < 1e-6 * ber["volumen"],
          f"{len(els)} Elemente")


def test_gmsh():
    if not vx.gmsh_verfuegbar():
        print("    gmsh: nicht installiert, uebersprungen")
        return
    _fremd("gmsh", vx.gmsh_tetraedern)


def test_netgen():
    if not vx.netgen_verfuegbar():
        print("    netgen: nicht installiert, uebersprungen")
        return
    _fremd("netgen", vx.netgen_tetraedern)


def test_nicht_installiert_faellt_zurueck():
    m, k = _platte()
    m.netz.ziellaenge = 0.1
    m.netz.dichte = "eigene"
    m.netz.vernetzer = "gibtsnicht"
    log = []
    els = m3.mesh_koerper_frei(m, k, log=log)
    check("unbekannter Vernetzer: der eigene uebernimmt, das Protokoll sagt es",
          len(els) > 0 and any("nicht installiert" in z for z in log), str([z for z in log if "nicht" in z][:1]))


def test_mmg_grund_nennt_den_fehler():
    """MMG3D sucht neben der Eingabe von sich aus eine gleichnamige `.sol` und
    warnt am **Ende** seiner Ausgabe, wenn keine da ist. Wer nur die letzten
    Zeichen meldet, nennt genau diese Warnung und verdeckt den Fehler - am
    Drehlager stand darum „netz.sol NOT FOUND" im Protokoll, obwohl die Metrik
    geschrieben war (21.09.2026)."""
    from statik3d.vernetzer_extern import _mmg_grund

    class Lauf:
        def __init__(self, out, err=""):
            self.stdout, self.stderr = out, err
    warnung = "** C:/tmp/statik3d_mmg_x/netz.sol  NOT FOUND. USE DEFAULT METRIC."
    g = _mmg_grund(Lauf("MMG3D: laeuft\n## Error: wrong volume element 17\n" + warnung))
    check("der Fehler wird genannt, nicht die Warnung am Ende",
          "wrong volume" in g and "NOT FOUND" not in g, g[:90])
    g2 = _mmg_grund(Lauf("MMG3D: laeuft\nMISMATCH OPTIONS: -optim und Metrik\n" + warnung))
    check("auch MISMATCH OPTIONS wird erkannt", "MISMATCH" in g2, g2[:90])
    g3 = _mmg_grund(Lauf("etwas ging schief\n" + warnung))
    check("ohne erkennbaren Fehler bleibt die Warnung außen vor",
          "NOT FOUND" not in g3 and "schief" in g3, g3[:90])
    g4 = _mmg_grund(Lauf("", warnung))
    check("steht nur die Warnung da, wird sie genannt - lieber das als nichts",
          bool(g4.strip()), g4[:90])


def main():
    for t in (test_verfuegbarkeit_und_lizenz, test_huelle_voran_und_orientierung, test_mesh_rundlauf,
              test_kein_konsolenfenster,
              test_gmsh, test_netgen, test_nicht_installiert_faellt_zurueck, test_mmg_grund_nennt_den_fehler):
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
