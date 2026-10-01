"""STEP-Eingang ueber gmsh-Tessellierung (Vorgabe 3, Plan TP 5 B5).

Eine STEP-Datei wird mit gmsh (OpenCASCADE) gelesen, die Oberflaeche zu Dreiecken tesselliert und als Huelle an den
bestehenden STL-Weg gegeben (geometry/stl.py: Windungszahl fuer innen/aussen, Orientierung, Abstand, Facettenpruefung).
Die Geometrie bleibt damit eine Innen/Aussen-Funktion; Krümmung steckt nur in der Tessellierung.

* Einheit: gmsh rechnet beim Lesen die in der Datei deklarierte Laengeneinheit nach mm um (``Geometry.OCCTargetUnit``),
  im Paket gilt durchgehend mm.
* Genauigkeit: ``Mesh.MeshSizeFromCurvature`` = Dreiecke je Vollkreis (Vorgabe ``KRUEMMUNG_STANDARD``); die Facetten liegen
  mit den Ecken auf der Flaeche (einbeschriebenes Polygon), der Volumenfehler einer Bohrung ist (2 pi / N)^2 / 6 ihres Volumens
  (gemessen am Block 200^3 mit Bohrung r 40: N 60 +0,019 %, 120 +0,0047 %, 240 +0,0012 % des Gesamtvolumens), die Dreieckszahl
  waechst mit N (8 000, 28 000, 108 000).
* Mehrere Koerper in einer Datei werden zu einer Huelle zusammengefasst; sich durchdringende Koerper sind nicht zulaessig.
* gmsh ist optional (Extra ``step``, GPL): ohne gmsh gibt es einen klaren Fehler, kein stiller Ersatz. Die Bibliothek wird
  nicht unterbrechbar initialisiert (Arbeitsfaeden) und ein bereits laufendes gmsh des Aufrufers bleibt unberuehrt: eigenes
  Modell, Optionen und aktuelles Modell werden zurueckgesetzt.
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np

KRUEMMUNG_STANDARD = 120
_CACHE: dict[tuple, tuple[np.ndarray, dict[str, Any]]] = {}
_CACHE_MAX = 4
_OPTIONEN_ZAHL = ("General.Terminal", "Mesh.MeshSizeMax", "Mesh.MeshSizeMin", "Mesh.MeshSizeFromCurvature",
                  "Mesh.MeshSizeExtendFromBoundary", "Mesh.MeshSizeFromPoints", "Mesh.MeshSizeFromParametricPoints")
_OPTIONEN_TEXT = ("Geometry.OCCTargetUnit",)
HINWEIS_GMSH = ("STEP braucht gmsh (optionales Extra 'step'): pip install \"gmsh>=4.11\" (GPL-Lizenz); "
                "bis dahin CSG, STL oder ein tessellierter Export der Datei")


def gmsh_verfuegbar() -> bool:
    try:
        import gmsh  # noqa: F401
    except ImportError:
        return False
    return True


def tesselliere(pfad: str, groesse_mm: float, kruemmung: int = KRUEMMUNG_STANDARD) -> tuple[np.ndarray, dict[str, Any]]:
    """(Dreiecke (n,3,3) in mm, Angaben fuers Protokoll). Wirft ValueError mit klarer Meldung (Datei, gmsh, Geometrie)."""
    if not os.path.isfile(pfad):
        raise ValueError(f"STEP-Datei {pfad!r} nicht gefunden")
    if not groesse_mm > 0 or int(kruemmung) < 8:
        raise ValueError("STEP-Tessellierung: Facettengroesse muss positiv und die Zahl der Dreiecke je Vollkreis mindestens 8 sein")
    schluessel = (os.path.abspath(pfad), os.path.getmtime(pfad), os.path.getsize(pfad), float(groesse_mm), int(kruemmung))
    if schluessel in _CACHE:
        D, info = _CACHE[schluessel]
        return D.copy(), dict(info)
    try:
        import gmsh
    except ImportError as ex:
        raise ValueError(HINWEIS_GMSH) from ex
    D, info = _mit_gmsh(gmsh, pfad, float(groesse_mm), int(kruemmung))
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[schluessel] = (D, info)
    return D.copy(), dict(info)


def _mit_gmsh(gmsh: Any, pfad: str, groesse_mm: float, kruemmung: int) -> tuple[np.ndarray, dict[str, Any]]:
    schon = bool(gmsh.isInitialized())
    if not schon:
        try:
            gmsh.initialize([], readConfigFiles=False, interruptible=False)
        except TypeError:                                    # aeltere gmsh ohne interruptible
            gmsh.initialize([], readConfigFiles=False)
    alt_modell = ""
    alt_zahl: dict[str, float] = {}
    alt_text: dict[str, str] = {}
    if schon:
        try:
            alt_modell = gmsh.model.getCurrent()
        except Exception:                                   # noqa: BLE001 - kein aktuelles Modell
            alt_modell = ""
        alt_zahl = {n: gmsh.option.getNumber(n) for n in _OPTIONEN_ZAHL}
        alt_text = {n: gmsh.option.getString(n) for n in _OPTIONEN_TEXT}
    name = f"volumen3d_step_{os.getpid()}"
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.model.add(name)
        try:
            gmsh.model.occ.importShapes(pfad)
            gmsh.model.occ.synchronize()
        except Exception as ex:                             # noqa: BLE001 - gmsh wirft einfache Exception
            raise ValueError(f"STEP-Datei {pfad!r} nicht lesbar: {ex}") from ex
        koerper = gmsh.model.getEntities(3)
        flaechen = gmsh.model.getEntities(2)
        if not koerper:
            raise ValueError(f"STEP-Datei {pfad!r} enthaelt keinen Volumenkoerper ({len(flaechen)} Flaechen): "
                             f"die Huelle muss ein geschlossener Koerper sein")
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(groesse_mm))
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", float(kruemmung))
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        try:
            gmsh.model.mesh.generate(2)
        except Exception as ex:                             # noqa: BLE001
            raise ValueError(f"STEP-Datei {pfad!r}: Tessellierung gescheitert: {ex}") from ex
        tags, xyz, _ = gmsh.model.mesh.getNodes()
        X = np.asarray(xyz, float).reshape(-1, 3)
        index = {int(t): i for i, t in enumerate(tags)}
        teile = []
        for _, ent in gmsh.model.getEntities(2):
            typen, _, knoten = gmsh.model.mesh.getElements(2, ent)
            for ty, kn in zip(typen, knoten):
                if int(ty) != 2:
                    continue
                tri = np.array([index[int(k)] for k in kn], dtype=np.int64).reshape(-1, 3)
                teile.append(X[tri])
        if not teile:
            raise ValueError(f"STEP-Datei {pfad!r}: die Tessellierung lieferte keine Dreiecke")
        D = np.concatenate(teile)
        lo, hi = D.reshape(-1, 3).min(axis=0), D.reshape(-1, 3).max(axis=0)
        info = {"quelle": os.path.basename(pfad), "dreiecke": int(len(D)), "koerper": int(len(koerper)), "flaechen": int(len(flaechen)),
                "facettengroesse_mm": float(groesse_mm), "dreiecke_je_vollkreis": int(kruemmung), "einheit": "mm (umgerechnet von der Dateieinheit)",
                "gmsh": str(getattr(gmsh, "__version__", "?")), "huellquader_min": lo.tolist(), "huellquader_max": hi.tolist()}
        return D, info
    finally:
        try:
            gmsh.model.remove()
        except Exception:                                   # noqa: BLE001
            pass
        if schon:
            for n, w in alt_zahl.items():
                gmsh.option.setNumber(n, w)
            for n, w in alt_text.items():
                gmsh.option.setString(n, w)
            if alt_modell:
                try:
                    gmsh.model.setCurrent(alt_modell)
                except Exception:                           # noqa: BLE001
                    pass
        else:
            gmsh.finalize()


__all__ = ["KRUEMMUNG_STANDARD", "HINWEIS_GMSH", "gmsh_verfuegbar", "tesselliere"]
