"""
Externe Vernetzer und Nachbesserer fuer Volumenkoerper - zur Auswahl in den
Netzeinstellungen neben dem eigenen Vernetzer (:mod:`statik3d.mesher3d`).

Alle drei arbeiten auf **derselben geschlossenen Dreieckshuelle**, die der
eigene Vernetzer bildet (:func:`mesher3d.randschale`): die Randpunkte bleiben
Punkt fuer Punkt erhalten, damit gemeinsame Randflaechen zweier Koerper
weiter dieselben Knoten teilen und die Kontaktbedingungen greifen.

* **gmsh** (GPL) - tetraedert die Huelle ueber seine Python-Schnittstelle;
  mehrkernig ueber den HXT-Algorithmus (``General.NumThreads``).
* **Netgen** (LGPL, Paket ``netgen-mesher``) - tetraedert die Huelle ueber
  ``netgen.meshing``.
* **MMG3D** (LGPL, Programm ``mmg3d_O3``) - kein Vernetzer, sondern ein
  Nachbesserer: er nimmt ein fertiges Tetraedernetz und optimiert die Form
  der Elemente, die Huelle bleibt fest (``-nosurf``). Das ist der Weg fuer
  eine Mindestguete aller Elemente, denn die schlechten Tetraeder sitzen auf
  der Huelle (Drehlager V5: alle 55 unter 0,1 mit vier Huellknoten).

Lizenzrechtlich: keines der drei wird mit der exe ausgeliefert. Auf Wunsch
laedt Statik3D sie nach (:mod:`statik3d.werkzeuge`, Dialog „Vernetzer und
Nachbesserer"): gmsh und Netgen als Raeder von PyPI, MMG3D als Programm aus
dem Release „werkzeuge" dieses Projekts - in die Benutzerdaten, nicht in
die exe. Wer eine eigene Python-Umgebung hat, kann sie auch dort
installieren (``pip install gmsh``, ``pip install netgen-mesher``); MMG3D
geht ebenso ueber den Suchpfad oder den Pfad in den Netzeinstellungen. Das
Programm ruft MMG3D als getrennten Prozess ueber Dateien im Medit-Format
auf. Was fehlt, steht in der Auswahl als „nicht installiert".

Gemessen an einer Platte 1 x 0,6 x 0,2 m mit Bohrung r = 0,1 m, Huelle
870 Punkte / 1 740 Dreiecke, h = 50 mm (13.09.2026): gmsh 4 414 Tetraeder,
Guete min 0,336, 0,1 s; Netgen 5 811 Tetraeder, Guete min 0,493, 0,4 s;
alle 870 Huellpunkte wiedergefunden. Der eigene Vernetzer kam an V5 des
Drehlagers auf Guete min 0,001.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import numpy as np

from . import werkzeuge

#: Schluessel der Auswahl „Vernetzer" -> (Name, Paket/Programm, Lizenz)
VERNETZER = {
    "eigener": ("eigener Vernetzer", "statik3d.mesher3d", "eigener Quelltext"),
    "gmsh": ("gmsh", "PyPI-Paket gmsh", "GPL - nicht in der exe, nachladbar"),
    "netgen": ("Netgen", "PyPI-Paket netgen-mesher", "LGPL - nicht in der exe, nachladbar"),
}
#: Schluessel der Auswahl „Nachbesserung" -> (Name, Programm, Lizenz)
NACHBESSERER = {
    "keine": ("keine", "", ""),
    "mmg3d": ("MMG3D", "mmg3d_O3 (mmgtools.org)", "LGPL - getrenntes Programm, nachladbar"),
}

# Nachgeladene Werkzeuge in den Suchpfad - auch in den Arbeitsprozessen,
# die dieses Modul beim Vernetzen importieren
werkzeuge.aktivieren()


def gmsh_verfuegbar() -> bool:
    try:
        import gmsh  # noqa: F401
        return True
    except Exception:                       # noqa: BLE001
        return False


def netgen_verfuegbar() -> bool:
    try:
        import netgen.meshing  # noqa: F401
        return True
    except Exception:                       # noqa: BLE001
        return False


def mmg3d_programm(pfad: str = "") -> str:
    """Der Pfad zu mmg3d_O3 - der angegebene, sonst das nachgeladene aus dem
    Werkzeugordner, sonst aus dem Suchpfad; leer, wenn es nicht da ist."""
    if pfad and os.path.isfile(pfad):
        return pfad
    nachgeladen = werkzeuge.programm("mmg3d")
    if nachgeladen:
        return nachgeladen
    for name in ("mmg3d_O3", "mmg3d_O3.exe", "mmg3d", "mmg3d.exe"):
        p = shutil.which(name)
        if p:
            return p
    return ""


def verfuegbar(mmg_pfad: str = "") -> dict:
    """{Schluessel: (Name, verfuegbar, Lizenz)} fuer Vernetzer und Nachbesserer."""
    out = {"eigener": ("eigener Vernetzer", True, "eigener Quelltext"),
           "gmsh": ("gmsh", gmsh_verfuegbar(), VERNETZER["gmsh"][2]),
           "netgen": ("Netgen", netgen_verfuegbar(), VERNETZER["netgen"][2]),
           "mmg3d": ("MMG3D", bool(mmg3d_programm(mmg_pfad)), NACHBESSERER["mmg3d"][2])}
    return out


def _threads() -> int:
    try:
        from . import parallel
        return max(1, min(int(parallel.settings().workers), parallel.cpu_count() - 1))
    except Exception:                       # noqa: BLE001
        return 1


# --------------------------------------------------------------------------
# gmsh
# --------------------------------------------------------------------------
def gmsh_tetraedern(P: np.ndarray, T: np.ndarray, h: float, h_min: float = 0.0,
                    threads: int = 0) -> tuple:
    """Die Huelle (P, T) mit gmsh tetraedern. Rueckgabe (Pn, TET): die ersten
    ``len(P)`` Punkte von Pn sind die Huellpunkte in ihrer Reihenfolge."""
    import gmsh
    P = np.asarray(P, float)
    T = np.asarray(T, int)
    n = len(P)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", int(threads or _threads()))
        gmsh.model.add("huelle")
        gmsh.model.addDiscreteEntity(2, 1)
        gmsh.model.mesh.addNodes(2, 1, list(range(1, n + 1)), P.ravel().tolist())
        gmsh.model.mesh.addElementsByType(1, 2, list(range(1, len(T) + 1)), (T + 1).ravel().tolist())
        gmsh.model.mesh.createTopology()
        loop = gmsh.model.geo.addSurfaceLoop([1])
        gmsh.model.geo.addVolume([loop])
        gmsh.model.geo.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(h))
        gmsh.option.setNumber("Mesh.MeshSizeMin", float(h_min) if h_min > 0 else float(h) / 4.0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)      # HXT: mehrkernig
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.option.setNumber("Mesh.OptimizeNetgen", 0)
        gmsh.model.mesh.generate(3)
        tags, coords, _ = gmsh.model.mesh.getNodes()
        X = np.asarray(coords, float).reshape(-1, 3)
        stelle = {int(t): i for i, t in enumerate(tags)}
        etypes, _etags, enodes = gmsh.model.mesh.getElements(dim=3)
        TET = np.zeros((0, 4), int)
        for et, en in zip(etypes, enodes):
            if int(et) == 4:
                en = np.asarray(en, int).reshape(-1, 4)
                TET = np.vectorize(stelle.get)(en)
    finally:
        gmsh.finalize()
    return _huelle_voran(P, X, TET)


# --------------------------------------------------------------------------
# Netgen
# --------------------------------------------------------------------------
def netgen_tetraedern(P: np.ndarray, T: np.ndarray, h: float, threads: int = 0) -> tuple:
    """Die Huelle (P, T) mit Netgen tetraedern. Rueckgabe (Pn, TET) wie bei gmsh."""
    from netgen.meshing import Element2D, FaceDescriptor, Mesh, MeshPoint, Pnt
    try:
        from netgen import libngpy   # noqa: F401
        from pyngcore import SetNumThreads
        SetNumThreads(int(threads or _threads()))
    except Exception:                   # noqa: BLE001 - dann eben so viele wie Netgen will
        pass
    P = np.asarray(P, float)
    T = np.asarray(T, int)
    ng = Mesh(dim=3)
    ids = [ng.Add(MeshPoint(Pnt(float(p[0]), float(p[1]), float(p[2])))) for p in P]
    fd = ng.Add(FaceDescriptor(surfnr=1, domin=1, bc=1))
    for tri in T:
        ng.Add(Element2D(fd, [ids[int(i)] for i in tri]))
    ng.GenerateVolumeMesh(maxh=float(h))
    X = np.array([[p[0], p[1], p[2]] for p in ng.Points()], float)
    TET = np.array([[int(v.nr) - 1 for v in e.vertices] for e in ng.Elements3D()], int).reshape(-1, 4)
    return _huelle_voran(P, X, TET)


def _huelle_voran(P: np.ndarray, X: np.ndarray, TET: np.ndarray) -> tuple:
    """Die Huellpunkte an den Anfang von Pn, Tetraeder positiv orientiert.

    Beide Vernetzer behalten die Huellpunkte, gmsh sogar ihre Nummern; hier
    wird die Zuordnung ueber die Koordinate geprueft (exakte Kopien) und die
    Nummerierung so gelegt, wie :func:`mesher3d.koerper_einbauen` sie
    erwartet: erst die Huelle, dann das Innere.
    """
    from scipy.spatial import cKDTree
    n = len(P)
    d, wo = cKDTree(X).query(P)
    if d.max() > 1e-9 * max(1.0, float(np.abs(P).max())) or len(np.unique(wo)) != n:
        raise RuntimeError("Der Vernetzer hat die Huellpunkte nicht erhalten - Netz verworfen")
    neu = np.full(len(X), -1, int)
    neu[wo] = np.arange(n)
    rest = np.flatnonzero(neu < 0)
    neu[rest] = n + np.arange(len(rest))
    Pn = np.empty_like(X)
    Pn[neu] = X
    TET = neu[np.asarray(TET, int)]
    a, b, c, d4 = Pn[TET[:, 0]], Pn[TET[:, 1]], Pn[TET[:, 2]], Pn[TET[:, 3]]
    vol = np.einsum("ij,ij->i", np.cross(b - a, c - a), d4 - a)
    falsch = vol < 0
    if falsch.any():
        TET[falsch] = TET[falsch][:, [0, 2, 1, 3]]
    return Pn, TET


# --------------------------------------------------------------------------
# MMG3D: Nachbesserung eines Tetraedernetzes bei fester Huelle
# --------------------------------------------------------------------------
def mesh_schreiben(pfad: str, Pn: np.ndarray, TET: np.ndarray, T: np.ndarray = None) -> None:
    """Medit-Format (.mesh), wie MMG es liest: Vertices, Tetrahedra, Triangles."""
    Pn = np.asarray(Pn, float)
    TET = np.asarray(TET, int)
    with open(pfad, "w", encoding="ascii") as f:
        f.write("MeshVersionFormatted 2\nDimension 3\n")
        f.write(f"Vertices\n{len(Pn)}\n")
        for p in Pn:
            f.write(f"{p[0]:.16g} {p[1]:.16g} {p[2]:.16g} 0\n")
        if T is not None and len(T):
            T = np.asarray(T, int)
            f.write(f"Triangles\n{len(T)}\n")
            for t in T:
                f.write(f"{t[0] + 1} {t[1] + 1} {t[2] + 1} 1\n")
        f.write(f"Tetrahedra\n{len(TET)}\n")
        for t in TET:
            f.write(f"{t[0] + 1} {t[1] + 1} {t[2] + 1} {t[3] + 1} 1\n")
        f.write("End\n")


def mesh_lesen(pfad: str) -> tuple:
    """(Punkte, Tetraeder, Dreiecke) aus einer Medit-Datei (.mesh)."""
    punkte, tets, tris = [], [], []
    with open(pfad, "r", encoding="ascii", errors="replace") as f:
        zeilen = [z.strip() for z in f]
    i = 0
    while i < len(zeilen):
        z = zeilen[i]
        if z in ("Vertices", "Tetrahedra", "Triangles"):
            n = int(zeilen[i + 1])
            block = zeilen[i + 2:i + 2 + n]
            if z == "Vertices":
                punkte = [[float(x) for x in b.split()[:3]] for b in block]
            elif z == "Tetrahedra":
                tets = [[int(x) - 1 for x in b.split()[:4]] for b in block]
            else:
                tris = [[int(x) - 1 for x in b.split()[:3]] for b in block]
            i += 2 + n
            continue
        i += 1
    return (np.asarray(punkte, float).reshape(-1, 3), np.asarray(tets, int).reshape(-1, 4),
            np.asarray(tris, int).reshape(-1, 3))


def mmg3d_nachbessern(Pn: np.ndarray, TET: np.ndarray, T: np.ndarray, h: float,
                      programm: str = "", h_min: float = 0.0, log: list = None) -> tuple:
    """Das Tetraedernetz mit MMG3D optimieren, die Huelle (Dreiecke T ueber
    die ersten len(T)-Punkte) bleibt unveraendert (-nosurf). Rueckgabe
    (Pn, TET) mit derselben Huellnummerierung.

    Aufruf als getrennter Prozess ueber Dateien - so bleibt MMG (LGPL) ein
    eigenes Programm und kein Teil der exe.
    """
    exe = mmg3d_programm(programm)
    if not exe:
        raise RuntimeError("MMG3D nicht gefunden (mmg3d_O3 im Suchpfad oder Pfad in den Netzeinstellungen)")
    n_rand = int(np.asarray(T, int).max()) + 1 if len(T) else 0
    ordner = tempfile.mkdtemp(prefix="statik3d_mmg_")
    ein = os.path.join(ordner, "netz.mesh")
    aus = os.path.join(ordner, "netz.o.mesh")
    try:
        mesh_schreiben(ein, Pn, TET, T)
        befehl = [exe, "-in", ein, "-out", aus, "-nosurf", "-optim", "-v", "0",
                  "-hmax", f"{float(h):.9g}"]
        if h_min > 0:
            befehl += ["-hmin", f"{float(h_min):.9g}"]
        lauf = subprocess.run(befehl, capture_output=True, text=True, timeout=3600)
        if lauf.returncode != 0 or not os.path.isfile(aus):
            raise RuntimeError(f"MMG3D gescheitert (Rückgabe {lauf.returncode}): "
                               f"{(lauf.stderr or lauf.stdout)[-300:]}")
        X, TET2, _tris = mesh_lesen(aus)
    finally:
        shutil.rmtree(ordner, ignore_errors=True)
    if log is not None:
        log.append(f"  MMG3D: {len(TET):,} -> {len(TET2):,} Tetraeder, {len(Pn):,} -> {len(X):,} Punkte")
    # Huellpunkte muessen an Ort und Nummer bleiben (-nosurf)
    P = np.asarray(Pn, float)[:n_rand]
    return _huelle_voran(P, X, TET2)
