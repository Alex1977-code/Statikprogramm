"""
Web-Server fuer die Bedienung im Browser und auf dem Handy.

Nur Standardbibliothek (http.server, json, threading). Der Zustand (Modell,
Analyse, laufender Auftrag, Protokoll) liegt in einem State-Objekt, das auch an
die Desktop-GUI gebunden werden kann (State.bound = MainWindow), damit Handy und
PC dasselbe Modell sehen.

API (JSON; Schluessel per Kopfzeile X-Statik-Key oder ?key=...):
    GET  /api/state                     Uebersicht (Modell, Lastfaelle, Auftrag, Protokoll)
    GET  /api/model      POST /api/model  Modell lesen / ersetzen (JSON-Format 2)
    GET  /api/geometry[?case=LF1]       Knoten, Linien, Dreiecke, Lager, Lastpfeile
    POST /api/op                        {"op": "...", ...}      Bearbeitung (siehe OPS)
    POST /api/example                   {"name": "hall"}
    POST /api/import?name=datei.dxf[&unit=0.001]     Dateiinhalt im Rumpf
    POST /api/solve                     {"kind": "all|case|modal|buckling", "design": true, ...}
    POST /api/design   POST /api/fatigue  Nachweise zur vorhandenen Analyse
    GET  /api/job                       Auftragsstatus, Fortschritt
    GET  /api/entries                   waehlbare Ergebnisse
    GET  /api/results?which=env:ULS&field=umag[&mode=0]
    GET  /api/diagram?which=...&quantity=My
    GET  /api/member?which=...&name=S1
    GET  /api/design                    Nachweistabellen und Einzelwerte
    GET  /api/report?fmt=html|pdf|md    Bericht als Datei
    GET  /api/download                  Modell als JSON-Datei
    GET  /api/profiles?family=IPE  /api/examples  /api/log  /api/check
"""
from __future__ import annotations

import json
import os
import re
import secrets
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import zipfile
from dataclasses import asdict, is_dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from ..model import (Model, Material, Section, ShellProp, NodalLoad, BeamLoad, FaceLoad,
                     TempLoad, Combination, ACTION_CATEGORIES, STEEL_GRADES, NDOF, DOF_NAMES)
from .. import solver, parallel, mesher, profiles
from ..assemble import SOLID_FACES
from ..elements import beam3d as bm
from ..examples_lib import EXAMPLES, build_example

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
KEY_HEADER = "X-Statik-Key"
FORCE_KEYS = ("N", "Vy", "Vz", "Mt", "My", "Mz")
MAX_ROWS = 400
VERSION = "2.1"

EXAMPLE_LABELS = {
    "frame": "Rahmen (Stab)", "truss": "Fachwerkbrücke", "plate": "Platte (Schale)",
    "solid": "Konsole (Volumen)", "hall": "Hallenrahmen HEB/IPE mit Nachweisen",
    "gate": "Stauwand (Stahlwasserbau)", "contact": "Träger auf Sockel (Kontakt)",
    "friction": "Block mit Reibung (Kontakt)",
}


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


# --------------------------------------------------------------------------
# JSON-Hilfen
# --------------------------------------------------------------------------
def _clean(o):
    """numpy / dataclass -> JSON-faehige Grundtypen (NaN/inf -> null)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if np.isfinite(f) else None
    if is_dataclass(o) and not isinstance(o, type):
        return _clean(asdict(o))
    return o


def _f(d: dict, key: str, default=0.0) -> float:
    v = d.get(key, default)
    if v is None or v == "":
        return float(default) if default is not None else None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ApiError(f"Zahl erwartet für '{key}', erhalten: {v!r}")


def _i(d: dict, key: str, default=None) -> int:
    v = d.get(key, default)
    if v is None:
        raise ApiError(f"'{key}' fehlt")
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(f"ganze Zahl erwartet für '{key}', erhalten: {v!r}")


def _ilist(d: dict, key: str, required: bool = True) -> list[int]:
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise ApiError(f"'{key}' fehlt (leere Auswahl?)")
        return []
    if isinstance(v, str):
        v = re.split(r"[\s,;]+", v.strip())
        v = [x for x in v if x]
    try:
        return [int(x) for x in v]
    except (TypeError, ValueError):
        raise ApiError(f"Liste ganzer Zahlen erwartet für '{key}'")


def _vec(d: dict, key: str, n: int, default=None) -> list[float]:
    v = d.get(key, default)
    if v is None:
        return None
    if isinstance(v, str):
        v = [x for x in re.split(r"[\s,;]+", v.strip()) if x]
    try:
        v = [float(x) for x in v]
    except (TypeError, ValueError):
        raise ApiError(f"Vektor mit {n} Zahlen erwartet für '{key}'")
    if len(v) != n:
        raise ApiError(f"'{key}' braucht {n} Werte, erhalten {len(v)}")
    return v


# --------------------------------------------------------------------------
# Auftrag (Hintergrundberechnung)
# --------------------------------------------------------------------------
class Job:
    def __init__(self, label: str, func):
        self.label = label
        self.func = func
        self.status = "laeuft"
        self.messages: list[str] = []
        self.result = None
        self.error = None
        self.t0 = time.time()
        self.t1 = None
        self.thread = threading.Thread(target=self._run, name="statik3d-web-job", daemon=True)

    def progress(self, msg):
        self.messages.append(str(msg))

    def _run(self):
        try:
            self.result = self.func(self.progress)
            self.status = "fertig"
        except Exception as ex:      # noqa: BLE001 - Fehler an den Browser melden
            self.error = f"{type(ex).__name__}: {ex}"
            self.messages.append(traceback.format_exc())
            self.status = "fehler"
        self.t1 = time.time()

    def start(self) -> "Job":
        self.thread.start()
        return self

    def to_dict(self) -> dict:
        return {"label": self.label, "status": self.status,
                "messages": self.messages[-80:], "n_messages": len(self.messages),
                "error": self.error, "elapsed": (self.t1 or time.time()) - self.t0,
                "result": self.result if isinstance(self.result, str) else None}


# --------------------------------------------------------------------------
# Zustand
# --------------------------------------------------------------------------
class State:
    """Modell, Analyse, laufender Auftrag und Protokoll des Web-Servers.
    bound: Objekt mit Attributen model / analysis / results (Desktop-GUI); dann
    arbeiten Browser und GUI auf denselben Objekten."""

    def __init__(self, model: Model = None, key: str = None):
        self.lock = threading.RLock()
        self._model = model if model is not None else Model()
        self._analysis = None
        self._results = None
        self.bound = None
        self.job: Job = None
        self.log: list[str] = []
        self.version = 0
        self.key = key
        s = parallel.settings()
        self.settings = {"workers": s.workers, "backend": s.backend, "farm_host": s.farm_host,
                         "farm_port": s.farm_port, "farm_key": s.farm_key}
        self.tmpdir = tempfile.mkdtemp(prefix="statik3d_web_")

    # Modell / Analyse ggf. an die GUI gebunden
    @property
    def model(self) -> Model:
        return self.bound.model if self.bound is not None else self._model

    @model.setter
    def model(self, m: Model):
        if self.bound is not None:
            self.bound.model = m
        else:
            self._model = m

    @property
    def analysis(self):
        return self.bound.analysis if self.bound is not None else self._analysis

    @analysis.setter
    def analysis(self, a):
        if self.bound is not None:
            self.bound.analysis = a
        else:
            self._analysis = a

    @property
    def results(self):
        return self.bound.results if self.bound is not None else self._results

    @results.setter
    def results(self, r):
        if self.bound is not None:
            self.bound.results = r
        else:
            self._results = r

    def info(self, msg: str):
        with self.lock:
            self.log.append(time.strftime("%H:%M:%S ") + str(msg))
            del self.log[:-500]

    def touch(self):
        self.version += 1

    def busy(self) -> bool:
        return self.job is not None and self.job.status == "laeuft"

    def invalidate(self, what: str = "all"):
        if what == "all":
            self.analysis = None
            self.results = None
        elif what == "design" and self.analysis is not None:
            self.analysis.design = None
            self.analysis.fatigue = None


# --------------------------------------------------------------------------
# Uebersicht / Geometrie
# --------------------------------------------------------------------------
def _loads_of(lc, limit: int = 300) -> dict:
    return {
        "nodal": [_clean(asdict(l)) for l in lc.nodal_loads[:limit]],
        "beam": [_clean(asdict(l)) for l in lc.beam_loads[:limit]],
        "face": [_clean(asdict(l)) for l in lc.face_loads[:limit]],
        "temp": [_clean(asdict(l)) for l in lc.temp_loads[:limit]],
        "counts": {"nodal": len(lc.nodal_loads), "beam": len(lc.beam_loads),
                   "face": len(lc.face_loads), "temp": len(lc.temp_loads)},
    }


def _support_summary(m: Model) -> str:
    from .. import supports as sup
    try:
        return sup.summary(m)
    except Exception:      # noqa: BLE001 - Uebersicht darf nie stoeren
        return ""


def _export_formats() -> list:
    """[(Endung, Beschreibung)] aller Ausgabeformate fuer die Oberflaeche."""
    try:
        from ..exporters import formats
        return [{"ext": e, "text": t} for e, t in formats()]
    except Exception:      # noqa: BLE001 - Uebersicht darf nie stoeren
        return []


def export_bytes(st: State, ext: str) -> tuple[bytes, str, str]:
    """Modell in ein fremdes Format schreiben und als Datei zurueckgeben.

    Formate, die einen Ordner schreiben (.csv, .nc1), werden gepackt.
    Rueckgabe: (Daten, MIME-Typ, Dateiname).
    """
    from ..exporters import export_model, FORMATS
    ext = (ext or "").strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in FORMATS:
        raise ApiError(f"Format '{ext}' gibt es nicht: " + ", ".join(sorted(FORMATS)))
    with st.lock:
        m = st.model
        erg = st.results if st.results is not None else st.analysis
        name = _safe_name(m.name) or "modell"
        log: list = []
        with tempfile.TemporaryDirectory() as tmp:
            ziel = os.path.join(tmp, name + ext)
            try:
                pfad = export_model(m, ziel, results=erg, log=log)
            except Exception as ex:      # noqa: BLE001 - Meldung an die Oberflaeche
                raise ApiError(f"Export nicht moeglich: {ex}")
            if os.path.isdir(pfad):
                paket = os.path.join(tmp, name + "_" + ext.lstrip(".") + ".zip")
                with zipfile.ZipFile(paket, "w", zipfile.ZIP_DEFLATED) as z:
                    for wurzel, _dirs, dateien in os.walk(pfad):
                        for d in sorted(dateien):
                            voll = os.path.join(wurzel, d)
                            z.write(voll, os.path.relpath(voll, pfad))
                pfad = paket
            daten = open(pfad, "rb").read()
            fname = os.path.basename(pfad)
    for z in log:
        st.info(z)
    endung = os.path.splitext(fname)[1].lstrip(".").lower()
    return daten, MIME.get(endung, "application/octet-stream"), fname


def _stellungen_summary(st: State) -> dict:
    """Stellungen des Systems und, falls gerechnet, die Umhuellende."""
    liste = getattr(st, "stellungen", None) or []
    umh = getattr(st, "umhuellende", None)
    erg = {}
    if umh is not None:
        fuehrend = max(umh.reihe.ergebnisse, key=lambda x: x.eta,
                       default=None) if umh.reihe.ergebnisse else None
        for e in umh.reihe.ergebnisse:
            erg[e.stellung.name] = {"eta": float(e.eta), "u_max": float(e.u_max),
                                    "massgebend": e.massgebend, "fehler": e.fehler,
                                    "fuehrt": bool(fuehrend is not None
                                                   and e is fuehrend and not e.fehler)}
    out = {
        "liste": [{"name": s.name, "winkel": float(s.winkel),
                   "beschreibung": s.beschreibung,
                   "lager_aktiv": list(s.lager_aktiv), "lager_aus": list(s.lager_aus),
                   "faelle": list(s.faelle), "dreh_winkel": float(s.dreh_winkel),
                   "gruppen": list(s.dreh_gruppen),
                   "antrieb": bool(s.antrieb),
                   "ergebnis": erg.get(s.name)} for s in liste],
        "gerechnet": umh is not None,
    }
    if umh is not None:
        out.update({"eta": float(umh.eta), "u_max": float(umh.u_max),
                    "massgebende_stellung": umh.massgebende_stellung,
                    "kurve": [[float(w), float(e), float(u), n] for w, e, u, n in umh.kurve()],
                    "fehlerhaft": [x.stellung.name for x in umh.fehlerhaft],
                    "bericht": umh.bericht()})
    rw = getattr(st, "regelwerk", None)
    if rw is not None:
        from ..bridges.din19704 import EINWIRKUNGEN, KLASSEN, KLASSEN_TEXT
        out["regelwerk"] = {
            "name": rw.name, "offen": rw.offen()[:40], "offen_gesamt": len(rw.offen()),
            "klassen": [{"code": k, "text": KLASSEN_TEXT[k],
                         "beiwerte": [{"einwirkung": e, "text": EINWIRKUNGEN.get(e, ""),
                                       "wert": float(rw.gamma_F[k][e].wert),
                                       "quelle": rw.gamma_F[k][e].quelle,
                                       "bestaetigt": bool(rw.gamma_F[k][e].bestaetigt)}
                                      for e in KLASSEN[k] if e in rw.gamma_F[k]]}
                        for k in ("LF1", "LF2", "LF3")],
            "bericht": rw.bericht()}
    try:
        from ..bridges.din19704 import pruefliste
        from ..bridges.positions import Stellungsreihe
        reihe = getattr(st, "stellungsreihe", None)
        if reihe is None and liste:
            # noch nicht gerechnet: die angelegten Stellungen trotzdem beurteilen
            reihe = Stellungsreihe(st.model, st.model.name)
            for x in liste:
                reihe.add(x)
        out["ztv"] = [{"thema": t, "erfuellt": bool(ok), "hinweis": h}
                      for t, ok, h in pruefliste(reihe, st.model)]
    except Exception:      # noqa: BLE001 - Uebersicht darf nie stoeren
        out["ztv"] = []
    return out


def state_summary(st: State) -> dict:
    with st.lock:
        m = st.model
        an = st.analysis
        types: dict[str, int] = {}
        for e in m.elements:
            types[e.typ] = types.get(e.typ, 0) + 1
        cases = []
        for lc in m.load_cases.values():
            d = {"name": lc.name, "category": lc.category, "description": lc.description,
                 "exclusive_group": lc.exclusive_group, "psi": list(lc.psi_factors),
                 "gravity": [float(g) for g in lc.gravity], "n_loads": lc.n_loads,
                 "gamma_sup": lc.gamma_sup, "gamma_inf": lc.gamma_inf,
                 "loads": _loads_of(lc)}
            cases.append(d)
        members = []
        for mem in m.members.values():
            d = _clean(asdict(mem))
            d["L"] = float(m.member_length(mem)) if mem.elements else 0.0
            d["n_elements"] = len(mem.elements)
            members.append(d)
        analysis = None
        if an is not None:
            analysis = {"cases": list(an.cases), "combinations": list(an.combinations),
                        "envelopes": list(an.envelopes), "design": an.design is not None,
                        "fatigue": an.fatigue is not None, "info": _clean(an.info),
                        "summary": an.summary()}
        single = None
        if st.results is not None:
            r = st.results
            single = {"name": r.name, "kind": r.kind, "summary": r.summary()}
        return {
            "version": st.version, "server_version": VERSION,
            "name": m.name, "meta": dict(m.meta), "nn": int(m.nn), "ne": len(m.elements),
            "types": types,
            "materials": {k: _clean(asdict(v)) for k, v in m.materials.items()},
            "sections": {k: dict(_clean(asdict(v)), describe=v.describe())
                         for k, v in m.sections.items()},
            "shells": {k: _clean(asdict(v)) for k, v in m.shells.items()},
            "supports": [{"node": int(s.node), "dofs": list(s.dofs), "name": s.name,
                          "nonlinear": s.nonlinear,
                          "beschreibung": {DOF_NAMES[d]: s.dof_behaviour(d).describe()
                                           for d in range(NDOF) if s.dof_behaviour(d).acts}}
                         for s in m.supports[:MAX_ROWS]],
            "n_supports": len(m.supports),
            "load_cases": cases, "active_case": m.active_case,
            "combinations": [{"name": c.name, "typ": c.typ, "description": c.description,
                              "leading": c.leading, "formula": c.formula(),
                              "factors": _clean(c.factors)} for c in m.combinations.values()],
            "fatigue_loads": [_clean(asdict(f)) for f in m.fatigue_loads.values()],
            "members": members,
            "design": _clean(asdict(m.design)),
            "line_supports": [{"name": x.name, "nodes": list(x.nodes),
                               "dofs": {DOF_NAMES[d]: x.dof_behaviour(d).describe()
                                        for d in range(NDOF) if x.dof_behaviour(d).acts}}
                              for x in m.line_supports],
            "surface_supports": [{"name": x.name, "elements": list(x.elements), "face": x.face,
                                  "dofs": {DOF_NAMES[d]: x.dof_behaviour(d).describe()
                                           for d in range(NDOF) if x.dof_behaviour(d).acts}}
                                 for x in m.surface_supports],
            "hinges": [{"name": h.name, "end": h.end, "beschreibung": h.describe()}
                       for h in m.hinges.values()],
            "support_summary": _support_summary(m),
            "stellungen": _stellungen_summary(st),
            "countries": [{"code": c, "name": n, "norm": nn, "families": f}
                          for c, n, nn, f in profiles.countries()],
            "contact": {"supports": [_clean(asdict(c)) for c in m.contact_supports[:MAX_ROWS]],
                        "gaps": [_clean(asdict(g)) for g in m.gap_elements[:MAX_ROWS]],
                        "pairs": [_clean(asdict(p)) for p in m.contact_pairs]},
            "has_analysis": an is not None, "analysis": analysis, "single": single,
            "job": st.job.to_dict() if st.job is not None else None, "busy": st.busy(),
            "settings": dict(st.settings), "cpu": parallel.cpu_count(),
            "parallel": parallel.describe(),
            "categories": {k: {"text": v[0], "psi": list(v[1])} for k, v in ACTION_CATEGORIES.items()},
            "grades": list(STEEL_GRADES), "families": list(profiles.FAMILIES),
            "examples": {k: EXAMPLE_LABELS.get(k, k) for k in EXAMPLES},
            "export_formats": _export_formats(),
            "log": st.log[-80:],
        }


def _shell_normal(X: np.ndarray) -> np.ndarray:
    n = np.cross(X[1] - X[0], X[2] - X[0])
    ln = np.linalg.norm(n)
    return n / ln if ln > 0 else np.array([0.0, 0.0, 1.0])


def geometry(model: Model, case: str = None) -> dict:
    """Darstellungsgeometrie: Knoten, Linien (Staebe), Dreiecke (Schalen, Aussenflaechen
    der Volumen), Lager, Kontakt, Lastpfeile des Lastfalls."""
    nodes = np.asarray(model.nodes, float)
    lines, line_elem, tris, tri_elem = [], [], [], []
    face_count: dict[tuple, tuple] = {}
    for i, e in enumerate(model.elements):
        nd = list(e.nodes)
        if e.typ in ("beam", "truss"):
            lines.append([int(nd[0]), int(nd[1])]); line_elem.append(i)
        elif e.typ == "shell3":
            tris.append([int(x) for x in nd[:3]]); tri_elem.append(i)
        elif e.typ == "shell4":
            tris.append([int(nd[0]), int(nd[1]), int(nd[2])]); tri_elem.append(i)
            tris.append([int(nd[0]), int(nd[2]), int(nd[3])]); tri_elem.append(i)
        elif e.typ in SOLID_FACES:
            for fn in SOLID_FACES[e.typ]:
                f = [int(nd[k]) for k in fn]
                key = tuple(sorted(f))
                if key in face_count:
                    face_count[key] = None          # innere Flaeche
                else:
                    face_count[key] = (f, i)
    for v in face_count.values():
        if v is None:
            continue
        f, i = v
        tris.append(f[:3]); tri_elem.append(i)
        if len(f) == 4:
            tris.append([f[0], f[2], f[3]]); tri_elem.append(i)
    hinges = []
    for i, e in enumerate(model.elements):
        if e.typ == "beam" and e.hinges:
            if any(h in (3, 4, 5) for h in e.hinges):
                hinges.append([i, 0])
            if any(h in (9, 10, 11) for h in e.hinges):
                hinges.append([i, 1])
    size = float(model.characteristic_size()) if model.nn else 1.0
    arrows = []
    grav = False
    if case is None:
        case = model.active_case
    lc = model.load_cases.get(case)
    if lc is not None:
        grav = bool(np.any(np.asarray(lc.gravity, float)))
        for l in lc.nodal_loads:
            f = np.asarray(l.F[:3], float)
            if np.any(f) and 0 <= l.node < model.nn:
                arrows.append((nodes[l.node], f))
        for bl in lc.beam_loads:
            if bl.elem >= len(model.elements):
                continue
            e = model.elements[bl.elem]
            X = nodes[e.nodes[:2]]
            T3, L = bm.local_axes(X[0], X[1], e.roll)
            q1 = np.asarray(bl.q, float)
            q2 = np.asarray(bl.q2, float) if bl.q2 is not None else q1
            if bl.system == "local":
                q1, q2 = T3.T @ q1, T3.T @ q2
            for t in np.linspace(0.15, 0.85, 3):
                q = (1 - t) * q1 + t * q2
                if np.any(q):
                    arrows.append((X[0] + t * (X[1] - X[0]), q))
        for fl in lc.face_loads:
            if fl.elem >= len(model.elements) or fl.p == 0:
                continue
            e = model.elements[fl.elem]
            X = nodes[e.nodes]
            if e.typ in ("shell3", "shell4"):
                n = _shell_normal(X[:3])
                arrows.append((X.mean(axis=0), n * fl.p))
            elif e.typ in SOLID_FACES:
                faces = SOLID_FACES[e.typ]
                if 0 <= fl.face < len(faces):
                    P = X[list(faces[fl.face])]
                    n = _shell_normal(P[:3])
                    if np.dot(n, P.mean(axis=0) - X.mean(axis=0)) < 0:
                        n = -n
                    arrows.append((P.mean(axis=0), -n * fl.p))
    arr_out = []
    if arrows:
        vmax = max(float(np.linalg.norm(v)) for _, v in arrows) or 1.0
        for p, v in arrows:
            arr_out.append({"p": _clean(p), "v": _clean(v / vmax * 0.06 * size),
                            "f": float(np.linalg.norm(v))})
    member_of = {}
    for k, (name, mem) in enumerate(model.members.items()):
        for ei in mem.elements:
            member_of[int(ei)] = k
    bbox = model.bbox() if model.nn else ((0, 0, 0), (1, 1, 1))
    return {
        "nodes": _clean(nodes), "lines": lines, "line_elem": line_elem,
        "tris": tris, "tri_elem": tri_elem,
        "supports": [{"node": int(s.node), "dofs": list(s.dofs),
                      "spring": bool(s.stiffness)} for s in model.supports],
        "csupports": [{"node": int(c.node), "dir": _clean(c.direction)} for c in model.contact_supports],
        "gaps": [[int(g.node_a), int(g.node_b)] for g in model.gap_elements],
        "pair_nodes": [int(n) for p in model.contact_pairs for n in p.slave_nodes],
        "hinges": hinges, "arrows": arr_out, "gravity": grav, "case": case,
        "member_of": member_of, "member_names": list(model.members),
        "bbox": _clean(bbox), "size": size, "types": [e.typ for e in model.elements],
    }


# --------------------------------------------------------------------------
# Ergebnisse
# --------------------------------------------------------------------------
def result_entries(st: State) -> list[dict]:
    if st.results is not None:
        r = st.results
        return [{"id": "single", "label": f"{r.name} ({r.kind})"}]
    an = st.analysis
    if an is None:
        return []
    m = st.model
    out = []
    for k in an.envelopes:
        out.append({"id": f"env:{k}", "label": f"Umhüllende {k}"})
    for k in an.combinations:
        c = m.combinations.get(k)
        out.append({"id": f"combo:{k}", "label": f"{k}: {c.formula() if c else ''}"})
    for k in an.cases:
        out.append({"id": f"case:{k}", "label": f"Lastfall {k}"})
    return out


def get_result(st: State, which: str = None):
    entries = result_entries(st)
    if not entries:
        raise ApiError("Keine Ergebnisse vorhanden - zuerst berechnen", 404)
    if not which:
        which = entries[0]["id"]
    if which == "single":
        if st.results is None:
            raise ApiError("Kein Einzelergebnis vorhanden", 404)
        return st.results
    kind, _, key = which.partition(":")
    an = st.analysis
    if an is None:
        raise ApiError("Keine Analyse vorhanden", 404)
    src = {"env": an.envelopes, "combo": an.combinations, "case": an.cases}.get(kind)
    if src is None or key not in src:
        raise ApiError(f"Ergebnis '{which}' unbekannt", 404)
    return src[key]


def _displacement(r) -> np.ndarray:
    if getattr(r, "u", None) is not None:
        return r.u
    if hasattr(r, "u_max"):
        return np.where(np.abs(r.u_max) > np.abs(r.u_min), r.u_max, r.u_min)
    return None


def _util_map(st: State, field: str) -> dict:
    an = st.analysis
    if an is None:
        return {}
    if field == "util" and an.design is not None:
        return an.design.util_by_element()
    if field == "util_fat" and an.fatigue is not None:
        return an.fatigue.util_by_element(st.model)
    return {}


def result_payload(st: State, which: str = None, field: str = "umag", mode: int = 0) -> dict:
    with st.lock:
        r = get_result(st, which)
        m = st.model
        an = st.analysis
        out = {"which": which or result_entries(st)[0]["id"], "name": getattr(r, "name", ""),
               "kind": getattr(r, "kind", "envelope"), "summary": r.summary(), "field": field}
        U = None
        if getattr(r, "freqs", None) is not None:
            out["modes"] = [f"{i + 1}. Eigenform  f = {f:.3f} Hz" for i, f in enumerate(r.freqs)]
            mode = max(0, min(mode, len(r.freqs) - 1))
            U = r.modes[mode]
        elif getattr(r, "buckling_factors", None) is not None:
            out["modes"] = [f"{i + 1}. Knickform  η = {f:.3f}" for i, f in enumerate(r.buckling_factors)]
            mode = max(0, min(mode, len(r.buckling_factors) - 1))
            U = r.buckling_modes[mode]
        else:
            U = _displacement(r)
        out["mode"] = mode
        if U is None:
            U = np.zeros((m.nn, NDOF))
        U3 = np.asarray(U)[:, :3]
        out["u"] = _clean(U3)
        umag = np.linalg.norm(U3, axis=1)
        out["umax"] = float(umag.max()) if umag.size else 0.0
        is_mode = "modes" in out
        # ---- Skalarfeld ----
        sn = se = None
        label = ""
        if field == "umag":
            sn, label = (umag if is_mode else umag * 1000), ("|φ| [-]" if is_mode else "|u| [mm]")
        elif field in ("ux", "uy", "uz"):
            k = "xyz".index(field[1])
            sn, label = (U3[:, k] if is_mode else U3[:, k] * 1000), (field if is_mode else field + " [mm]")
        elif field == "vm":
            if hasattr(r, "node_vm_max"):
                sn, label = np.nan_to_num(r.node_vm_max) / 1e6, "σv max [MPa]"
            elif hasattr(r, "node_vm"):
                sn, label = np.nan_to_num(r.node_vm) / 1e6, "σv [MPa]"
        elif field in ("util", "util_fat"):
            um = _util_map(st, field)
            if um:
                se = {int(k): float(v) for k, v in um.items()}
                label = "Ausnutzung EC3 [-]" if field == "util" else "Ausnutzung Ermüdung [-]"
        elif field == "util_el":
            se = {}
            if hasattr(r, "util"):
                se = {int(k): float(v) for k, v in r.util.items() if v is not None}
            elif hasattr(r, "beam_forces"):
                se = {int(k): float(d["util"]) for k, d in r.beam_forces.items() if d["util"] is not None}
            label = "Ausnutzung elastisch [-]"
        elif field == "member":
            se = {int(ei): k for k, mem in enumerate(m.members.values()) for ei in mem.elements}
            label = "Stab"
        if sn is not None:
            sn = np.nan_to_num(np.asarray(sn, float))
            out["scalar_nodes"] = _clean(sn)
            out["smin"], out["smax"] = float(sn.min()), float(sn.max())
        if se is not None:
            out["scalar_elems"] = se
            vals = list(se.values())
            out["smin"], out["smax"] = (float(min(vals)), float(max(vals))) if vals else (0.0, 0.0)
        out["scalar_label"] = label
        # ---- Tabellen ----
        um = _util_map(st, "util")
        if hasattr(r, "beam_forces") and r.beam_forces:
            rows = []
            for e, d in sorted(r.beam_forces.items()):
                u = um.get(e, d["util"])
                rows.append([e, d["N"][0] / 1e3, d["N"][1] / 1e3, d["Vz"][0] / 1e3, d["Vz"][1] / 1e3,
                             d["My"][0] / 1e3, d["My"][1] / 1e3,
                             max(abs(d["Mz"][0]), abs(d["Mz"][1])) / 1e3, d["sig_max"] / 1e6,
                             u if u is not None else None])
                if len(rows) >= MAX_ROWS:
                    break
            out["beam_header"] = ["Elem", "N1 [kN]", "N2 [kN]", "Vz1 [kN]", "Vz2 [kN]", "My1 [kNm]",
                                  "My2 [kNm]", "|Mz| [kNm]", "σ [MPa]", "Ausn."]
            out["beam_rows"] = _clean(rows)
            out["beam_total"] = len(r.beam_forces)
        elif hasattr(r, "extreme_table"):
            rows = r.extreme_table()
            out["env_header"] = ["Elem", "Größe", "min", "Kombination", "max", "Kombination"]
            out["env_rows"] = _clean([[a, b, c / 1e3, d, e / 1e3, f] for a, b, c, d, e, f in rows[:MAX_ROWS]])
            out["env_total"] = len(rows)
        R = getattr(r, "reactions", None)
        if R is None and hasattr(r, "r_max"):
            R = np.where(np.abs(r.r_max) > np.abs(r.r_min), r.r_max, r.r_min)
        if R is not None:
            snodes = sorted({s.node for s in m.supports} | {c.node for c in m.contact_supports})
            out["react_header"] = ["Knoten", "Fx [kN]", "Fy [kN]", "Fz [kN]", "Mx [kNm]", "My [kNm]", "Mz [kNm]"]
            out["react_rows"] = _clean([[n] + [float(v) / 1e3 for v in R[n]] for n in snodes[:MAX_ROWS]])
            tot = np.asarray(R)[snodes].sum(axis=0) / 1e3 if snodes else np.zeros(6)
            out["react_sum"] = _clean(tot)
        contact = getattr(r, "contact", None)
        if contact:
            out["contact_header"] = ["Knoten", "Art", "Status", "Spalt [mm]", "Fn [kN]", "Ft [kN]"]
            out["contact_rows"] = _clean([[c["node"], c.get("label") or c["kind"], c["status"],
                                           c["gap"] * 1000, c["Fn"] / 1e3, c["Ft"] / 1e3]
                                          for c in contact[:MAX_ROWS]])
            out["contact_markers"] = [{"node": int(c["node"]), "status": c["status"]} for c in contact]
        if an is not None and an.design is not None:
            out["design_summary"] = an.design.summary()
        if an is not None and an.fatigue is not None:
            out["fatigue_summary"] = an.fatigue.summary()
        return out


def diagram_payload(st: State, which: str = None, quantity: str = "My", n: int = 9) -> dict:
    if quantity not in FORCE_KEYS:
        raise ApiError(f"Schnittgröße '{quantity}' unbekannt ({', '.join(FORCE_KEYS)})")
    with st.lock:
        r = get_result(st, which)
        m = st.model
        stations = r.stations(n) if hasattr(r, "stations") else None
        items = []
        vmax = 0.0
        for i, e in enumerate(m.elements):
            if e.typ not in ("beam", "truss"):
                continue
            if stations is not None:
                if i not in stations:
                    continue
                x = stations[i]["x"]
                v = np.asarray(stations[i][quantity], float)
            else:
                d = r.beam.get(i)
                if d is None:
                    continue
                x = d["x"]
                v = np.where(np.abs(d[quantity][1]) >= np.abs(d[quantity][0]),
                             d[quantity][1], d[quantity][0])
            items.append((i, e, np.asarray(x, float), v))
            vmax = max(vmax, float(np.abs(v).max()) if v.size else 0.0)
        size = float(m.characteristic_size()) if m.nn else 1.0
        scale = 0.08 * size / vmax if vmax > 0 else 0.0
        polys = []
        for i, e, x, v in items:
            X = m.nodes[e.nodes[:2]]
            T3, L = bm.local_axes(X[0], X[1], e.roll)
            direction = T3[1] if quantity in ("Mz", "Vy") else T3[2]
            sign = -1.0 if quantity == "My" else 1.0
            P0 = X[0] + np.outer(x, T3[0])
            P1 = P0 + np.outer(sign * v * scale, direction)
            polys.append({"elem": i, "base": _clean(P0), "tip": _clean(P1), "vals": _clean(v / 1e3)})
        return {"quantity": quantity, "unit": "kN" if quantity in ("N", "Vy", "Vz") else "kNm",
                "vmax": vmax / 1e3, "polys": polys}


def member_payload(st: State, which: str = None, name: str = "", n: int = None) -> dict:
    with st.lock:
        m = st.model
        if name not in m.members:
            raise ApiError(f"Stab '{name}' unbekannt", 404)
        mem = m.members[name]
        r = get_result(st, which)
        out = {"name": name, "elements": list(mem.elements), "L": float(m.member_length(mem))}
        if hasattr(r, "stations"):
            d = r.member_forces(mem, n)
            out["x"] = _clean(d["x"])
            for k in FORCE_KEYS:
                out[k] = _clean(np.asarray(d[k]) / 1e3)
        elif hasattr(r, "beam"):
            nn = n or m.design.stations
            xs, mn, mx = [], {k: [] for k in FORCE_KEYS}, {k: [] for k in FORCE_KEYS}
            x0 = 0.0
            for i in mem.elements:
                d = r.beam.get(i)
                L = m.element_length(i)
                if d is None:
                    x0 += L
                    continue
                xs.append(np.asarray(d["x"]) + x0)
                for k in FORCE_KEYS:
                    mn[k].append(np.asarray(d[k][0]) / 1e3)
                    mx[k].append(np.asarray(d[k][1]) / 1e3)
                x0 += L
            out["x"] = _clean(np.concatenate(xs)) if xs else []
            for k in FORCE_KEYS:
                out[k] = {"min": _clean(np.concatenate(mn[k])) if mn[k] else [],
                          "max": _clean(np.concatenate(mx[k])) if mx[k] else []}
            out["envelope"] = True
        an = st.analysis
        if an is not None and an.design is not None and name in an.design.members:
            out["design"] = _member_check_dict(an.design.members[name])
        if an is not None and an.fatigue is not None and name in an.fatigue.members:
            out["fatigue"] = _clean(asdict(an.fatigue.members[name]))
        return out


def _member_check_dict(mc) -> dict:
    d = _clean(asdict(mc))
    d["status"] = mc.status()
    return d


def design_payload(st: State) -> dict:
    with st.lock:
        an = st.analysis
        out = {"design": None, "fatigue": None, "has_analysis": an is not None,
               "n_members": len(st.model.members), "n_fatigue_loads": len(st.model.fatigue_loads)}
        if an is not None and an.design is not None:
            d = an.design
            out["design"] = {"summary": d.summary(), "table": d.table(), "util_max": float(d.util_max),
                             "combinations": list(d.combinations), "settings": _clean(d.settings),
                             "members": {k: _member_check_dict(v) for k, v in d.members.items()}}
        if an is not None and an.fatigue is not None:
            f = an.fatigue
            out["fatigue"] = {"summary": f.summary(), "table": f.table(), "gamma_Ff": float(f.gamma_Ff),
                              "members": {k: _clean(asdict(v)) for k, v in f.members.items()}}
        return out


# --------------------------------------------------------------------------
# Bearbeitungsoperationen
# --------------------------------------------------------------------------
OPS: dict = {}
KEEP_ALL = {"check", "meta", "rename", "select_box", "set_active_case"}
KEEP_DESIGN = {"design_settings", "set_member", "remove_member", "auto_members",
               "add_fatigue_load", "remove_fatigue_load"}
GEOM_OPS = {"new", "add_node", "move_node", "delete_nodes", "delete_elements", "clear_mesh",
            "add_element", "line_of_beams", "plate", "box", "support", "remove_support",
            "clear_supports", "hinges", "merge_nodes", "contact_support", "gap_element",
            "contact_pair", "remove_contact", "clear_contact", "nodal_load", "beam_load",
            "face_load", "temp_load", "gravity", "remove_load", "clear_loads", "set_active_case",
            "add_case", "remove_case", "copy_case", "auto_members", "set_member", "remove_member",
            "assign", "edit_case", "staebe_anschliessen"}


def op(name: str):
    def deco(fn):
        OPS[name] = fn
        return fn
    return deco


def _case(m: Model, d: dict):
    name = d.get("case") or m.active_case
    if name not in m.load_cases:
        raise ApiError(f"Lastfall '{name}' unbekannt")
    return m.load_cases[name]


def _check_nodes(m: Model, nodes: list[int]):
    bad = [n for n in nodes if n < 0 or n >= m.nn]
    if bad:
        raise ApiError(f"Knoten {bad[:5]} existieren nicht (0..{m.nn - 1})")


def _check_elems(m: Model, elems: list[int]):
    bad = [e for e in elems if e < 0 or e >= len(m.elements)]
    if bad:
        raise ApiError(f"Elemente {bad[:5]} existieren nicht (0..{len(m.elements) - 1})")


@op("new")
def _op_new(st, m, d):
    st.model = Model(d.get("name") or "Modell")
    return "Neues Modell"


@op("rename")
def _op_rename(st, m, d):
    m.name = str(d.get("name") or m.name)
    return f"Modellname: {m.name}"


@op("meta")
def _op_meta(st, m, d):
    for k, v in (d.get("fields") or {}).items():
        m.meta[str(k)] = str(v)
    if d.get("name"):
        m.name = str(d["name"])
    return "Projektdaten gespeichert"


@op("check")
def _op_check(st, m, d):
    return {"messages": m.check()}


@op("select_box")
def _op_select_box(st, m, d):
    kw = {k: _f(d, k, None) for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax") if d.get(k) not in (None, "")}
    ids = mesher.select_nodes(m, **kw)
    return {"nodes": [int(i) for i in ids], "message": f"{len(ids)} Knoten gewählt"}


# ---- Material / Querschnitt ----
@op("add_material")
def _op_add_material(st, m, d):
    if d.get("grade"):
        mat = Material.steel(d["grade"], d.get("name") or None)
    else:
        name = d.get("name")
        if not name:
            raise ApiError("Materialname fehlt")
        mat = Material(name, _f(d, "E", 210e9), _f(d, "nu", 0.3), _f(d, "rho", 7850.0),
                       _f(d, "alpha", 1.2e-5), _f(d, "fy", None), _f(d, "fu", None),
                       str(d.get("grade_name") or ""))
    m.add_material(mat)
    return f"Material {mat.name} angelegt"


@op("remove_material")
def _op_remove_material(st, m, d):
    name = d.get("name")
    if any(e.mat == name for e in m.elements):
        raise ApiError(f"Material '{name}' wird von Elementen verwendet")
    if m.materials.pop(name, None) is None:
        raise ApiError(f"Material '{name}' unbekannt")
    return f"Material {name} entfernt"


@op("add_section")
def _op_add_section(st, m, d):
    kind = (d.get("kind") or "profile").lower()
    name = d.get("name") or None
    if kind == "profile":
        des = d.get("designation") or ""
        if not des:
            raise ApiError("Profilbezeichnung fehlt (z.B. IPE 300)")
        sec = profiles.make_section(des, name)
    elif kind == "rect":
        sec = Section.rectangle(name or "Rechteck", _f(d, "b"), _f(d, "h"))
    elif kind == "circle":
        sec = Section.circle(name or "Rund", _f(d, "d"))
    elif kind == "pipe":
        sec = Section.pipe(name or "Rohr", _f(d, "d"), _f(d, "t"), d.get("fabrication") or "rolled")
    elif kind == "i":
        sec = Section.i_profile(name or "I", _f(d, "h"), _f(d, "b"), _f(d, "tw"), _f(d, "tf"),
                                _f(d, "r", 0.0))
    elif kind == "rhs":
        sec = Section.rhs(name or "RHS", _f(d, "h"), _f(d, "b"), _f(d, "t"))
    elif kind == "free":
        if not name:
            raise ApiError("Name fehlt")
        sec = Section(name, _f(d, "A"), _f(d, "Iy"), _f(d, "Iz"), _f(d, "It", 1e-6),
                      _f(d, "Asy", 0.0), _f(d, "Asz", 0.0), _f(d, "zmax", 0.0), _f(d, "ymax", 0.0))
    else:
        raise ApiError(f"Querschnittsart '{kind}' unbekannt")
    m.add_section(sec)
    return f"Querschnitt {sec.name} angelegt ({sec.describe()})"


@op("remove_section")
def _op_remove_section(st, m, d):
    name = d.get("name")
    if any(e.sec == name and e.typ in ("beam", "truss") for e in m.elements):
        raise ApiError(f"Querschnitt '{name}' wird von Elementen verwendet")
    if m.sections.pop(name, None) is None:
        raise ApiError(f"Querschnitt '{name}' unbekannt")
    return f"Querschnitt {name} entfernt"


@op("add_shell")
def _op_add_shell(st, m, d):
    name = d.get("name") or f"t{_f(d, 't') * 1000:g}"
    m.add_shell_prop(ShellProp(name, _f(d, "t", 0.01)))
    return f"Schalendicke {name} angelegt"


@op("remove_shell")
def _op_remove_shell(st, m, d):
    name = d.get("name")
    if any(e.sec == name and e.typ.startswith("shell") for e in m.elements):
        raise ApiError(f"Schalendicke '{name}' wird verwendet")
    if m.shells.pop(name, None) is None:
        raise ApiError(f"Schalendicke '{name}' unbekannt")
    return f"Schalendicke {name} entfernt"


# ---- Knoten / Elemente ----
@op("add_node")
def _op_add_node(st, m, d):
    i = m.add_node(_f(d, "x"), _f(d, "y"), _f(d, "z"))
    return {"node": int(i), "message": f"Knoten {i} angelegt"}


@op("move_node")
def _op_move_node(st, m, d):
    n = _i(d, "node")
    _check_nodes(m, [n])
    m.nodes[n] = [_f(d, "x"), _f(d, "y"), _f(d, "z")]
    return f"Knoten {n} verschoben"


def _remove_elements(m: Model, elems: set[int]):
    keep = [i for i in range(len(m.elements)) if i not in elems]
    new = {old: k for k, old in enumerate(keep)}
    m.elements = [m.elements[i] for i in keep]
    for lc in m.load_cases.values():
        for attr in ("beam_loads", "face_loads", "temp_loads"):
            kept = []
            for l in getattr(lc, attr):
                if l.elem in new:
                    l.elem = new[l.elem]
                    kept.append(l)
            setattr(lc, attr, kept)
    for name in list(m.members):
        mem = m.members[name]
        mem.elements = [new[e] for e in mem.elements if e in new]
        if not mem.elements:
            del m.members[name]
    for p in m.contact_pairs:
        p.master_elements = [new[e] for e in p.master_elements if e in new]


def _remove_nodes(m: Model, nodes: set[int]):
    used = {int(n) for e in m.elements for n in e.nodes}
    blocked = sorted(n for n in nodes if n in used)
    if blocked:
        raise ApiError(f"Knoten {blocked[:5]} gehören zu Elementen - zuerst Elemente löschen")
    keep = [i for i in range(m.nn) if i not in nodes]
    new = {old: k for k, old in enumerate(keep)}
    m.nodes = m.nodes[keep] if keep else np.zeros((0, 3))
    for e in m.elements:
        e.nodes = [new[int(n)] for n in e.nodes]
    m.supports = [s for s in m.supports if s.node in new]
    for s in m.supports:
        s.node = new[s.node]
    for lc in m.load_cases.values():
        lc.nodal_loads = [l for l in lc.nodal_loads if l.node in new]
        for l in lc.nodal_loads:
            l.node = new[l.node]
    m.contact_supports = [c for c in m.contact_supports if c.node in new]
    for c in m.contact_supports:
        c.node = new[c.node]
    m.gap_elements = [g for g in m.gap_elements if g.node_a in new and g.node_b in new]
    for g in m.gap_elements:
        g.node_a, g.node_b = new[g.node_a], new[g.node_b]
    for p in m.contact_pairs:
        p.slave_nodes = [new[n] for n in p.slave_nodes if n in new]
        p.master_faces = [[new[n] for n in f] for f in p.master_faces if all(n in new for n in f)]


@op("delete_nodes")
def _op_delete_nodes(st, m, d):
    nodes = set(_ilist(d, "nodes"))
    _check_nodes(m, list(nodes))
    _remove_nodes(m, nodes)
    return f"{len(nodes)} Knoten gelöscht"


@op("delete_elements")
def _op_delete_elements(st, m, d):
    elems = set(_ilist(d, "elems"))
    _check_elems(m, list(elems))
    _remove_elements(m, elems)
    if d.get("with_nodes"):
        used = {int(n) for e in m.elements for n in e.nodes}
        loose = {i for i in range(m.nn) if i not in used}
        if loose:
            _remove_nodes(m, loose)
    return f"{len(elems)} Elemente gelöscht"


@op("clear_mesh")
def _op_clear_mesh(st, m, d):
    m.nodes = np.zeros((0, 3))
    m.elements = []
    m.supports = []
    m.members = {}
    m.contact_supports, m.gap_elements, m.contact_pairs = [], [], []
    for lc in m.load_cases.values():
        lc.nodal_loads, lc.beam_loads, lc.face_loads, lc.temp_loads = [], [], [], []
    return "Netz, Lager und Lasten gelöscht"


def _need_mat(m: Model, d: dict) -> str:
    mat = d.get("mat") or (next(iter(m.materials)) if m.materials else None)
    if not mat:
        raise ApiError("Kein Material vorhanden - zuerst Material anlegen")
    if mat not in m.materials:
        raise ApiError(f"Material '{mat}' unbekannt")
    return mat


def _need_sec(m: Model, d: dict) -> str:
    sec = d.get("sec") or (next(iter(m.sections)) if m.sections else None)
    if not sec:
        raise ApiError("Kein Querschnitt vorhanden - zuerst Querschnitt anlegen")
    if sec not in m.sections:
        raise ApiError(f"Querschnitt '{sec}' unbekannt")
    return sec


def _need_prop(m: Model, d: dict) -> str:
    p = d.get("prop") or (next(iter(m.shells)) if m.shells else None)
    if not p:
        raise ApiError("Keine Schalendicke vorhanden - zuerst anlegen")
    if p not in m.shells:
        raise ApiError(f"Schalendicke '{p}' unbekannt")
    return p


@op("add_element")
def _op_add_element(st, m, d):
    typ = d.get("typ") or "beam"
    nodes = _ilist(d, "nodes")
    _check_nodes(m, nodes)
    need = {"beam": 2, "truss": 2, "shell3": 3, "shell4": 4, "tet4": 4, "hex8": 8, "tet10": 10}
    if typ not in need:
        raise ApiError(f"Elementtyp '{typ}' unbekannt")
    if len(nodes) != need[typ]:
        raise ApiError(f"{typ} braucht {need[typ]} Knoten")
    mat = _need_mat(m, d)
    if typ in ("beam", "truss"):
        sec = _need_sec(m, d)
    elif typ.startswith("shell"):
        sec = _need_prop(m, d)
    else:
        sec = None
    m.add_element(typ, nodes, mat, sec, roll=float(np.radians(_f(d, "roll_deg", 0.0))))
    return {"elem": len(m.elements) - 1, "message": f"Element {len(m.elements) - 1} ({typ}) angelegt"}


@op("line_of_beams")
def _op_line(st, m, d):
    mat, sec = _need_mat(m, d), _need_sec(m, d)
    p1, p2 = _vec(d, "p1", 3), _vec(d, "p2", 3)
    n = max(1, _i(d, "n", 1))
    n0 = len(m.elements)
    ids = mesher.line_of_beams(m, mat, sec, p1, p2, n)
    if d.get("merge", True):
        mesher.merge_nodes(m)
    return {"elems": list(range(n0, len(m.elements))), "message": f"Stabzug mit {n} Elementen erzeugt"}


@op("plate")
def _op_plate(st, m, d):
    mat, prop = _need_mat(m, d), _need_prop(m, d)
    origin = _vec(d, "origin", 3, [0, 0, 0])
    mesher.grid_plate(m, mat, prop, _f(d, "lx"), _f(d, "ly"), max(1, _i(d, "nx", 4)),
                      max(1, _i(d, "ny", 4)), origin=tuple(origin), quad=bool(d.get("quad", True)))
    mesher.merge_nodes(m)
    return "Platte erzeugt"


@op("box")
def _op_box(st, m, d):
    mat = _need_mat(m, d)
    origin = _vec(d, "origin", 3, [0, 0, 0])
    mesher.grid_box(m, mat, _f(d, "lx"), _f(d, "ly"), _f(d, "lz"), max(1, _i(d, "nx", 4)),
                    max(1, _i(d, "ny", 2)), max(1, _i(d, "nz", 2)), origin=tuple(origin),
                    typ=d.get("typ") or "hex8")
    mesher.merge_nodes(m)
    return "Quader erzeugt"


@op("assign")
def _op_assign(st, m, d):
    elems = _ilist(d, "elems")
    _check_elems(m, elems)
    mat, sec, prop = d.get("mat"), d.get("sec"), d.get("prop")
    if mat and mat not in m.materials:
        raise ApiError(f"Material '{mat}' unbekannt")
    if sec and sec not in m.sections:
        raise ApiError(f"Querschnitt '{sec}' unbekannt")
    if prop and prop not in m.shells:
        raise ApiError(f"Schalendicke '{prop}' unbekannt")
    for i in elems:
        e = m.elements[i]
        if mat:
            e.mat = mat
        if sec and e.typ in ("beam", "truss"):
            e.sec = sec
        if prop and e.typ.startswith("shell"):
            e.sec = prop
    return f"{len(elems)} Elemente zugewiesen"


@op("hinges")
def _op_hinges(st, m, d):
    elems = _ilist(d, "elems")
    _check_elems(m, elems)
    mode = _i(d, "mode", 0)
    h = {0: [], 1: [4, 5], 2: [10, 11], 3: [4, 5, 10, 11], 4: [3, 4, 5, 9, 10, 11]}.get(mode)
    if h is None:
        raise ApiError("Gelenkart 0..4 erwartet")
    n = 0
    for i in elems:
        if m.elements[i].typ == "beam":
            m.elements[i].hinges = list(h)
            n += 1
    return f"Gelenke an {n} Stabelementen gesetzt"


@op("merge_nodes")
def _op_merge(st, m, d):
    n = mesher.merge_nodes(m, _f(d, "tol", 1e-6))
    return f"{n} doppelte Knoten zusammengeführt"


# ---- Lager ----
@op("support")
def _op_support(st, m, d):
    nodes = _ilist(d, "nodes")
    _check_nodes(m, nodes)
    dofs = d.get("dofs", "all")
    if isinstance(dofs, str):
        dofs = {"all": [0, 1, 2, 3, 4, 5], "pinned": [0, 1, 2], "z": [2], "xz": [0, 2],
                "yz": [1, 2], "xyz": [0, 1, 2]}.get(dofs) or _ilist({"d": dofs}, "d")
    dofs = [int(x) for x in dofs]
    if not dofs or any(x < 0 or x > 5 for x in dofs):
        raise ApiError("Freiheitsgrade 0..5 erwartet")
    k = _f(d, "stiffness", 0.0)
    m.supports = [s for s in m.supports if s.node not in nodes]
    for n in nodes:
        m.fix(n, dofs, stiffness=[k] * len(dofs) if k > 0 else None)
    return f"Lager an {len(nodes)} Knoten gesetzt"


@op("support_nonlinear")
def _op_support_nonlinear(st, m, d):
    """Wirkung je Freiheitsgrad an Knotenlagern setzen (Ausfall/Schlupf/Reibung)."""
    from ..model import DofBehaviour, dof_index
    nodes = _ilist(d, "nodes")
    _check_nodes(m, nodes)
    beh = {}
    for key, val in (d.get("behaviour") or {}).items():
        dof = dof_index(key)
        v = dict(val)
        for num in ("stiffness", "slip", "mu", "limit"):
            if num in v and v[num] not in (None, ""):
                v[num] = _f(v, num)
        if v.get("mu_ref") in (None, ""):
            v.pop("mu_ref", None)
        else:
            v["mu_ref"] = dof_index(v["mu_ref"])
        beh[dof] = DofBehaviour(**{k: x for k, x in v.items() if x not in (None, "")})
    if not beh:
        raise ApiError("Keine Freiheitsgrade angegeben")
    for n in nodes:
        s = next((x for x in m.supports if x.node == n), None)
        if s is None:
            s = m.support(n, [])
        s.behaviour = dict(beh)
        s.dofs = sorted({dof for dof, b in beh.items() if b.acts})
    return f"Nichtlinearität an {len(nodes)} Lagern gesetzt"


@op("line_support")
def _op_line_support(st, m, d):
    from ..model import DofBehaviour, dof_index
    nodes = _ilist(d, "nodes")
    _check_nodes(m, nodes)
    if len(nodes) < 2:
        raise ApiError("Linienlager braucht mindestens zwei Knoten")
    ls = m.add_line_support(nodes, name=d.get("name") or "")
    for key, val in (d.get("behaviour") or {}).items():
        ls.behaviour[dof_index(key)] = DofBehaviour(**{k: (_f(val, k) if k in
                                                          ("stiffness", "slip", "mu", "limit")
                                                          else v)
                                                       for k, v in val.items() if v not in (None, "")})
    return f"Linienlager über {len(nodes)} Knoten angelegt"


@op("surface_support")
def _op_surface_support(st, m, d):
    from ..model import DofBehaviour, dof_index
    elems = _ilist(d, "elems")
    _check_elems(m, elems)
    ss = m.add_surface_support(elems, name=d.get("name") or "", face=_i(d, "face", -1))
    for key, val in (d.get("behaviour") or {}).items():
        ss.behaviour[dof_index(key)] = DofBehaviour(**{k: (_f(val, k) if k in
                                                           ("stiffness", "slip", "mu", "limit")
                                                           else v)
                                                        for k, v in val.items() if v not in (None, "")})
    return f"Flächenlager auf {len(elems)} Elementen angelegt"


@op("remove_line_support")
def _op_remove_line_support(st, m, d):
    i = _i(d, "index")
    if not 0 <= i < len(m.line_supports):
        raise ApiError("Index ungültig")
    del m.line_supports[i]
    return "Linienlager entfernt"


@op("remove_surface_support")
def _op_remove_surface_support(st, m, d):
    i = _i(d, "index")
    if not 0 <= i < len(m.surface_supports):
        raise ApiError("Index ungültig")
    del m.surface_supports[i]
    return "Flächenlager entfernt"


@op("add_hinge")
def _op_add_hinge(st, m, d):
    from ..model import dof_index
    name = (d.get("name") or f"G{len(m.hinges) + 1}").strip()
    h = m.add_hinge(name, end=_i(d, "end", 0))
    for key, val in (d.get("dofs") or {}).items():
        dof = dof_index(key)
        if isinstance(val, str) and val in ("free", "fixed"):
            h.typ[dof] = val
        elif val not in (None, ""):
            h.typ[dof] = "spring"
            h.stiffness[dof] = _f({"v": val}, "v")
    elems = _ilist(d, "elems", required=False)
    for e in elems:
        m.apply_hinge(e, h)
    return f"Gelenk {name} angelegt" + (f" und auf {len(elems)} Elemente gelegt" if elems else "")


# --------------------------------------------------------------------------
# Stellungen des Systems (bewegliche Bruecken)
# --------------------------------------------------------------------------
def _stellungen(st) -> list:
    """Stellungsliste des Zustands (wird im Zustand gehalten, nicht im Modell)."""
    if not hasattr(st, "stellungen"):
        st.stellungen = []
    return st.stellungen


@op("stellung")
def _op_stellung(st, m, d):
    """Stellung anlegen oder aendern."""
    from ..bridges.positions import Stellung
    name = (d.get("name") or "").strip()
    if not name:
        raise ApiError("Name der Stellung fehlt")
    liste = _stellungen(st)
    vorhanden = next((s for s in liste if s.name == name), None)
    antrieb = None
    kn = str(d.get("antrieb_knoten") or "").strip()
    treffer = re.findall(r"\d+", kn)
    if treffer:
        mv = [_f(d, "antrieb_mx", 0.0), _f(d, "antrieb_my", 0.0), _f(d, "antrieb_mz", 0.0)]
        antrieb = (int(treffer[0]) - 1, mv)
    neu = Stellung(
        name=name,
        winkel=_f(d, "winkel", 0.0),
        beschreibung=(d.get("beschreibung") or "").strip(),
        lager_aktiv=[x.strip() for x in (d.get("lager_aktiv") or "").split(",") if x.strip()],
        lager_aus=[x.strip() for x in (d.get("lager_aus") or "").split(",") if x.strip()],
        faelle=[x.strip() for x in (d.get("faelle") or "").split(",") if x.strip()],
        dreh_achse=(_f(d, "achse_x", 0.0), _f(d, "achse_y", 1.0), _f(d, "achse_z", 0.0)),
        dreh_punkt=(_f(d, "punkt_x", 0.0), _f(d, "punkt_y", 0.0), _f(d, "punkt_z", 0.0)),
        dreh_winkel=_f(d, "dreh_winkel", 0.0),
        dreh_gruppen=[x.strip() for x in (d.get("gruppen") or "").split(",") if x.strip()],
        antrieb=antrieb)
    if vorhanden is not None:
        liste[liste.index(vorhanden)] = neu
        return f"Stellung {name} geaendert"
    liste.append(neu)
    liste.sort(key=lambda s: s.winkel)
    return f"Stellung {name} angelegt ({neu.beschriftung()})"


@op("remove_stellung")
def _op_remove_stellung(st, m, d):
    name = (d.get("name") or "").strip()
    liste = _stellungen(st)
    vor = len(liste)
    liste[:] = [s for s in liste if s.name != name]
    if len(liste) == vor:
        raise ApiError(f"Stellung '{name}' gibt es nicht")
    return f"Stellung {name} entfernt"


@op("stellungen_rechnen")
def _op_stellungen_rechnen(st, m, d):
    """Alle Stellungen rechnen und die Umhuellende bilden."""
    from ..bridges.positions import Stellungsreihe
    liste = _stellungen(st)
    if not liste:
        raise ApiError("Es ist keine Stellung angelegt")
    reihe = Stellungsreihe(m, m.name)
    for s in liste:
        reihe.add(s)
    umh = reihe.rechnen(kombinationen=bool(d.get("kombinationen", True)),
                        nachweise=bool(d.get("nachweise", True)))
    st.stellungsreihe = reihe
    st.umhuellende = umh
    for z in reihe.log:
        st.log.append(z)
    return (f"{len(liste)} Stellungen gerechnet: eta = {umh.eta:.3f}"
            + (f", massgebend {umh.massgebende_stellung}" if umh.massgebende_stellung else ""))


@op("staebe_anschliessen")
def _op_staebe_anschliessen(st, m, d):
    """Freie Stabenden auf die Achse des naechsten Stabes loten und dort teilen."""
    from ..importers import hicad_szn as Z
    radius = _f(d, "radius", 0.06)
    if radius <= 0:
        raise ApiError("Radius muss groesser als null sein")
    log: list = []
    r = Z.an_staebe_anschliessen(m, radius, log)
    zus = Z.zusammenhang(m, log)
    for z in log:
        st.log.append(z)
    if not r["angeschlossen"]:
        return (f"Kein freies Stabende innerhalb von {radius * 1e3:.0f} mm - "
                "nichts geaendert")
    return (f"{r['angeschlossen']} Stabenden angeschlossen, {r['geteilt']} Staebe "
            f"geteilt, groesster Versatz {r['groesster_versatz'] * 1e3:.1f} mm; "
            f"das System hat noch {zus['teile']} Teile")


@op("din19704")
def _op_din19704(st, m, d):
    """Kombinationen nach DIN 19704 bilden."""
    from ..bridges.din19704 import Regelwerk
    rw = getattr(st, "regelwerk", None) or Regelwerk()
    st.regelwerk = rw
    faktoren = list(d.get("faktoren") or [])
    if d.get("klasse") and d.get("einwirkung") and d.get("wert") not in (None, ""):
        faktoren.append({"klasse": d["klasse"], "einwirkung": d["einwirkung"],
                         "wert": d["wert"]})
    for eintrag in faktoren:
        try:
            rw.faktor(eintrag["klasse"], eintrag["einwirkung"], float(eintrag["wert"]))
        except (KeyError, TypeError, ValueError) as ex:
            raise ApiError(f"Beiwert nicht setzbar: {ex}")
    klassen = d.get("klassen") or None
    log: list = []
    namen = rw.kombinationen(m, klassen=klassen, log=log)
    for z in log:
        st.log.append(z)
    offen = rw.offen()
    return (f"{len(namen)} Kombinationen nach DIN 19704 gebildet"
            + (f"; {len(offen)} Beiwerte sind noch zu bestaetigen" if offen else ""))


@op("export")
def _op_export(st, m, d):
    """Modell in ein fremdes Format schreiben (Endung bestimmt das Format)."""
    from ..exporters import export_model, FORMATS
    ziel = (d.get("path") or d.get("datei") or "").strip()
    if not ziel:
        raise ApiError("Kein Dateiname angegeben")
    ext = os.path.splitext(ziel)[1].lower()
    if ext not in FORMATS:
        raise ApiError(f"Endung '{ext or '(keine)'}' gehoert zu keinem Ausgabeformat. "
                       "Moeglich: " + ", ".join(sorted(FORMATS)))
    if not os.path.isabs(ziel):
        ziel = os.path.join(st.tmpdir, ziel)
    os.makedirs(os.path.dirname(os.path.abspath(ziel)) or ".", exist_ok=True)
    log: list = []
    an = st.analysis
    r = getattr(an, "static", None) if an is not None else None
    out = export_model(m, ziel, results=r, log=log)
    return " | ".join(log) or f"Geschrieben: {out}"


@op("composite_section")
def _op_composite(st, m, d):
    from .. import sections as sec_mod
    name = (d.get("name") or "").strip()
    if not name:
        raise ApiError("Name fehlt")
    parts = d.get("parts") or []
    if not parts:
        raise ApiError("Keine Teilquerschnitte angegeben")
    try:
        spec = [(p.get("profil"), _f(p, "dy", 0.0), _f(p, "dz", 0.0),
                 _f(p, "drehung", 0.0), bool(p.get("spiegeln"))) for p in parts]
        s = sec_mod.build(name, spec)
    except (KeyError, ValueError) as ex:
        raise ApiError(str(ex))
    m.add_section(s)
    return f"Zusammengesetzter Querschnitt {name}: {s.describe()}"


@op("remove_support")
def _op_remove_support(st, m, d):
    nodes = set(_ilist(d, "nodes"))
    n0 = len(m.supports)
    m.supports = [s for s in m.supports if s.node not in nodes]
    return f"{n0 - len(m.supports)} Lager entfernt"


@op("clear_supports")
def _op_clear_supports(st, m, d):
    n0 = len(m.supports)
    m.supports = []
    return f"{n0} Lager entfernt"


# ---- Lasten ----
@op("nodal_load")
def _op_nodal_load(st, m, d):
    lc = _case(m, d)
    nodes = _ilist(d, "nodes")
    _check_nodes(m, nodes)
    F = _vec(d, "F", 6)
    for n in nodes:
        lc.nodal_loads.append(NodalLoad(int(n), list(F)))
    return f"Knotenlast auf {len(nodes)} Knoten in Lastfall {lc.name}"


@op("beam_load")
def _op_beam_load(st, m, d):
    lc = _case(m, d)
    elems = _ilist(d, "elems")
    _check_elems(m, elems)
    q = _vec(d, "q", 3)
    q2 = _vec(d, "q2", 3, None)
    system = d.get("system") or "global"
    if system not in ("global", "local"):
        raise ApiError("system: global | local")
    n = 0
    for i in elems:
        if m.elements[i].typ in ("beam", "truss"):
            lc.beam_loads.append(BeamLoad(int(i), list(q), system, list(q2) if q2 else None))
            n += 1
    return f"Streckenlast auf {n} Stabelemente in Lastfall {lc.name}"


@op("face_load")
def _op_face_load(st, m, d):
    lc = _case(m, d)
    elems = _ilist(d, "elems")
    _check_elems(m, elems)
    p = _f(d, "p")
    face = _i(d, "face", 0)
    direction = _vec(d, "direction", 3, None)
    n = 0
    for i in elems:
        if m.elements[i].typ not in ("beam", "truss"):
            lc.face_loads.append(FaceLoad(int(i), p, face, direction))
            n += 1
    return f"Flächenlast auf {n} Elemente in Lastfall {lc.name}"


@op("temp_load")
def _op_temp_load(st, m, d):
    lc = _case(m, d)
    elems = _ilist(d, "elems")
    _check_elems(m, elems)
    for i in elems:
        lc.temp_loads.append(TempLoad(int(i), _f(d, "dT"), _f(d, "dT_z", 0.0)))
    return f"Temperaturlast auf {len(elems)} Elemente in Lastfall {lc.name}"


@op("gravity")
def _op_gravity(st, m, d):
    lc = _case(m, d)
    g = _vec(d, "g", 3, None)
    if g is None:
        g = [0.0, 0.0, _f(d, "gz", -9.81)]
    lc.gravity = [float(x) for x in g]
    return f"Eigengewicht in Lastfall {lc.name}: {'ein' if any(g) else 'aus'}"


@op("remove_load")
def _op_remove_load(st, m, d):
    lc = _case(m, d)
    kind = d.get("kind")
    attr = {"nodal": "nodal_loads", "beam": "beam_loads", "face": "face_loads", "temp": "temp_loads"}.get(kind)
    if attr is None:
        raise ApiError("kind: nodal | beam | face | temp")
    idx = _i(d, "index")
    lst = getattr(lc, attr)
    if idx < 0 or idx >= len(lst):
        raise ApiError("Lastindex ungültig")
    del lst[idx]
    return "Last entfernt"


@op("clear_loads")
def _op_clear_loads(st, m, d):
    lc = _case(m, d)
    lc.nodal_loads, lc.beam_loads, lc.face_loads, lc.temp_loads = [], [], [], []
    lc.gravity = [0.0, 0.0, 0.0]
    return f"Alle Lasten in Lastfall {lc.name} entfernt"


# ---- Lastfaelle / Kombinationen ----
@op("add_case")
def _op_add_case(st, m, d):
    name = (d.get("name") or "").strip()
    if not name:
        raise ApiError("Lastfallname fehlt")
    if name in m.load_cases:
        raise ApiError(f"Lastfall '{name}' existiert bereits")
    cat = d.get("category") or "Q"
    if cat not in ACTION_CATEGORIES:
        raise ApiError(f"Einwirkungskategorie '{cat}' unbekannt")
    psi = _vec(d, "psi", 3, None)
    m.add_load_case(name, cat, d.get("description") or "", activate=bool(d.get("activate", True)),
                    psi=psi, exclusive_group=d.get("exclusive_group") or "")
    return f"Lastfall {name} ({cat}) angelegt"


@op("edit_case")
def _op_edit_case(st, m, d):
    lc = _case(m, {"case": d.get("name")})
    f = d.get("fields") or {}
    if "category" in f:
        if f["category"] not in ACTION_CATEGORIES:
            raise ApiError(f"Einwirkungskategorie '{f['category']}' unbekannt")
        lc.category = f["category"]
    if "description" in f:
        lc.description = str(f["description"])
    if "exclusive_group" in f:
        lc.exclusive_group = str(f["exclusive_group"] or "")
    if "psi" in f:
        lc.psi = _vec(f, "psi", 3, None) if f["psi"] not in (None, "") else None
    for k in ("gamma_sup", "gamma_inf"):
        if k in f:
            setattr(lc, k, _f(f, k, None) if f[k] not in (None, "") else None)
    new = (f.get("new_name") or "").strip()
    if new and new != lc.name:
        if new in m.load_cases:
            raise ApiError(f"Lastfall '{new}' existiert bereits")
        old = lc.name
        lc.name = new
        m.load_cases = {(new if k == old else k): v for k, v in m.load_cases.items()}
        for c in m.combinations.values():
            if old in c.factors:
                c.factors = {(new if k == old else k): v for k, v in c.factors.items()}
        for fl in m.fatigue_loads.values():
            if fl.case_max == old:
                fl.case_max = new
            if fl.case_min == old:
                fl.case_min = new
        if m.active_case == old:
            m.active_case = new
    return f"Lastfall {lc.name} geändert"


@op("remove_case")
def _op_remove_case(st, m, d):
    name = d.get("name")
    if name not in m.load_cases:
        raise ApiError(f"Lastfall '{name}' unbekannt")
    m.remove_load_case(name)
    return f"Lastfall {name} entfernt"


@op("copy_case")
def _op_copy_case(st, m, d):
    lc = _case(m, {"case": d.get("name")})
    new = (d.get("new") or f"{lc.name} Kopie").strip()
    if new in m.load_cases:
        raise ApiError(f"Lastfall '{new}' existiert bereits")
    dd = lc.to_dict()
    dd["name"] = new
    from ..model import LoadCase
    m.load_cases[new] = LoadCase.from_dict(json.loads(json.dumps(_clean(dd))))
    m.active_case = new
    return f"Lastfall {new} angelegt"


@op("set_active_case")
def _op_set_active(st, m, d):
    lc = _case(m, {"case": d.get("name")})
    m.active_case = lc.name
    return f"Aktiver Lastfall: {lc.name}"


@op("auto_combinations")
def _op_auto_combos(st, m, d):
    from ..combinations import generate_combinations
    if d.get("rule"):
        m.design.combination_rule = d["rule"]
    combos = generate_combinations(m, uls=bool(d.get("uls", True)), sls=bool(d.get("sls", True)),
                                   accidental=bool(d.get("accidental", True)),
                                   rule=d.get("rule") or None)
    return f"{len(combos)} Kombinationen erzeugt ({m.design.combination_rule})"


@op("add_combination")
def _op_add_combo(st, m, d):
    name = (d.get("name") or "").strip()
    if not name:
        raise ApiError("Kombinationsname fehlt")
    factors = d.get("factors") or {}
    if isinstance(factors, str):
        fd = {}
        for part in re.split(r"[,;\n]+", factors):
            if "=" in part or ":" in part:
                k, v = re.split(r"[=:]", part, 1)
                fd[k.strip()] = _f({"v": v.strip()}, "v")
        factors = fd
    if not factors:
        raise ApiError("Faktoren fehlen, z.B. LF1=1.35, LF2=1.5")
    for k in factors:
        if k not in m.load_cases:
            raise ApiError(f"Lastfall '{k}' unbekannt")
    typ = d.get("typ") or "ULS"
    m.add_combination(name, {k: float(v) for k, v in factors.items()}, typ,
                      d.get("description") or "manuell", d.get("leading") or "")
    return f"Kombination {name} angelegt"


@op("remove_combination")
def _op_remove_combo(st, m, d):
    if m.combinations.pop(d.get("name"), None) is None:
        raise ApiError("Kombination unbekannt")
    return "Kombination entfernt"


@op("clear_combinations")
def _op_clear_combos(st, m, d):
    n = len(m.combinations)
    m.combinations = {}
    return f"{n} Kombinationen entfernt"


@op("add_fatigue_load")
def _op_add_fat(st, m, d):
    name = (d.get("name") or "").strip() or f"E{len(m.fatigue_loads) + 1}"
    cmax = d.get("case_max")
    if cmax not in m.load_cases:
        raise ApiError(f"Lastfall '{cmax}' unbekannt")
    cmin = d.get("case_min") or None
    if cmin and cmin not in m.load_cases:
        raise ApiError(f"Lastfall '{cmin}' unbekannt")
    m.add_fatigue_load(name, cmax, cmin, _f(d, "cycles", 2e6), _f(d, "factor", 1.0))
    return f"Ermüdungslast {name} angelegt"


@op("remove_fatigue_load")
def _op_remove_fat(st, m, d):
    if m.fatigue_loads.pop(d.get("name"), None) is None:
        raise ApiError("Ermüdungslast unbekannt")
    return "Ermüdungslast entfernt"


# ---- Staebe / Nachweise ----
MEMBER_FIELDS = {"design": bool, "beta_y": float, "beta_z": float, "Lcr_y": float, "Lcr_z": float,
                 "L_LT": float, "k_z": float, "k_w": float, "C1": float, "load_position": str,
                 "lt_check": bool, "sway_y": bool, "sway_z": bool, "detail_category": float,
                 "detail_category_shear": float, "fatigue_points": str, "consequence": str,
                 "assessment": str}


@op("auto_members")
def _op_auto_members(st, m, d):
    names = m.auto_members(d.get("prefix") or "S")
    return f"{len(names)} Stäbe erkannt"


@op("set_member")
def _op_set_member(st, m, d):
    name = (d.get("name") or "").strip()
    if not name:
        raise ApiError("Stabname fehlt")
    if name not in m.members:
        elems = _ilist(d, "elements")
        _check_elems(m, elems)
        m.add_member(name, elems)
    mem = m.members[name]
    if d.get("elements") not in (None, "") and name in m.members:
        elems = _ilist(d, "elements")
        _check_elems(m, elems)
        mem.elements = elems
    for k, v in (d.get("fields") or {}).items():
        if k not in MEMBER_FIELDS:
            raise ApiError(f"Stabfeld '{k}' unbekannt")
        t = MEMBER_FIELDS[k]
        if v in (None, ""):
            setattr(mem, k, None if t is float and k not in ("beta_y", "beta_z", "k_z", "k_w") else getattr(mem, k))
        elif t is bool:
            setattr(mem, k, bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "ja", "on"))
        elif t is float:
            setattr(mem, k, _f({"v": v}, "v"))
        else:
            setattr(mem, k, str(v))
    return f"Stab {name} gespeichert"


@op("remove_member")
def _op_remove_member(st, m, d):
    if m.members.pop(d.get("name"), None) is None:
        raise ApiError("Stab unbekannt")
    return "Stab entfernt"


@op("design_settings")
def _op_design_settings(st, m, d):
    ds = m.design
    for k, v in (d.get("fields") or {}).items():
        if not hasattr(ds, k):
            raise ApiError(f"Einstellung '{k}' unbekannt")
        cur = getattr(ds, k)
        if isinstance(cur, bool):
            setattr(ds, k, bool(v))
        elif isinstance(cur, int) and not isinstance(cur, bool):
            setattr(ds, k, _i({"v": v}, "v"))
        elif isinstance(cur, float):
            setattr(ds, k, _f({"v": v}, "v"))
        else:
            setattr(ds, k, str(v))
    return "Nachweiseinstellungen gespeichert"


# ---- Kontakt ----
@op("contact_support")
def _op_contact_support(st, m, d):
    nodes = _ilist(d, "nodes")
    _check_nodes(m, nodes)
    direction = _vec(d, "direction", 3, [0, 0, 1])
    for n in nodes:
        m.add_contact_support(n, direction, _f(d, "gap", 0.0), _f(d, "stiffness", 0.0),
                              _f(d, "mu", 0.0), d.get("group") or "default")
    return f"Einseitiges Lager an {len(nodes)} Knoten"


@op("gap_element")
def _op_gap(st, m, d):
    a, b = _i(d, "node_a"), _i(d, "node_b")
    _check_nodes(m, [a, b])
    m.add_gap_element(a, b, _vec(d, "direction", 3, None), _f(d, "gap", 0.0),
                      _f(d, "stiffness", 0.0), _f(d, "mu", 0.0), d.get("group") or "default")
    return f"Spaltelement {a}-{b} angelegt"


@op("contact_pair")
def _op_pair(st, m, d):
    name = (d.get("name") or f"K{len(m.contact_pairs) + 1}").strip()
    slaves = _ilist(d, "slave_nodes")
    _check_nodes(m, slaves)
    masters = _ilist(d, "master_elements", required=False)
    _check_elems(m, masters)
    if not masters and not d.get("master_faces"):
        raise ApiError("Master-Elemente fehlen")
    m.add_contact_pair(name, slaves, masters, master_faces=d.get("master_faces") or [],
                       stiffness=_f(d, "stiffness", 0.0), mu=_f(d, "mu", 0.0),
                       gap=_f(d, "gap", 0.0), flip_normal=bool(d.get("flip_normal", False)))
    return f"Kontaktpaar {name} angelegt"


@op("remove_contact")
def _op_remove_contact(st, m, d):
    kind = d.get("kind")
    idx = _i(d, "index")
    lst = {"support": m.contact_supports, "gap": m.gap_elements, "pair": m.contact_pairs}.get(kind)
    if lst is None:
        raise ApiError("kind: support | gap | pair")
    if idx < 0 or idx >= len(lst):
        raise ApiError("Index ungültig")
    del lst[idx]
    return "Kontaktdefinition entfernt"


@op("clear_contact")
def _op_clear_contact(st, m, d):
    m.contact_supports, m.gap_elements, m.contact_pairs = [], [], []
    return "Alle Kontaktdefinitionen entfernt"


def apply_op(st: State, d: dict) -> dict:
    """Bearbeitungsoperation ausfuehren; Rueckgabe: Nachricht, Uebersicht, Zusatzdaten."""
    name = d.get("op")
    fn = OPS.get(name)
    if fn is None:
        raise ApiError(f"Operation '{name}' unbekannt")
    with st.lock:
        if st.busy() and name not in KEEP_ALL:
            raise ApiError("Es läuft gerade eine Berechnung - bitte warten", 409)
        m = st.model
        try:
            res = fn(st, m, d)
        except ApiError:
            raise
        except (KeyError, ValueError, IndexError, TypeError) as ex:
            raise ApiError(str(ex).strip('"\''))
        if name not in KEEP_ALL:
            st.invalidate("design" if name in KEEP_DESIGN else "all")
            st.touch()
        extra = res if isinstance(res, dict) else {}
        msg = extra.get("message", res if isinstance(res, str) else name)
        if name not in ("check", "select_box"):
            st.info(msg)
        out = {"ok": True, "message": msg, "geometry_changed": name in GEOM_OPS or name == "new"}
        out.update({k: v for k, v in extra.items() if k != "message"})
        out["state"] = state_summary(st)
        return out


# --------------------------------------------------------------------------
# Berechnung / Import / Bericht
# --------------------------------------------------------------------------
def _apply_settings(st: State, opts: dict):
    s = st.settings
    for k in ("workers", "farm_port"):
        if opts.get(k) not in (None, ""):
            s[k] = max(1, _i(opts, k))
    for k in ("backend", "farm_host", "farm_key"):
        if opts.get(k) not in (None, ""):
            s[k] = str(opts[k])
    if s["backend"] not in ("local", "farm"):
        s["backend"] = "local"
    parallel.configure(workers=int(s["workers"]), backend=s["backend"], farm_host=s["farm_host"],
                       farm_port=int(s["farm_port"]), farm_key=s["farm_key"])
    if opts.get("solver_backend"):
        parallel.configure(solver_backend=str(opts["solver_backend"]))


def start_solve(st: State, opts: dict) -> dict:
    with st.lock:
        if st.busy():
            raise ApiError("Es läuft bereits eine Berechnung", 409)
        m = st.model
        problems = [x for x in m.check() if x.startswith("FEHLER")]
        if problems:
            raise ApiError("\n".join(problems))
        _apply_settings(st, opts)
        kind = opts.get("kind") or "all"
        if kind not in ("all", "case", "modal", "buckling"):
            raise ApiError("kind: all | case | modal | buckling")
        design = bool(opts.get("design", True)) and bool(m.members)
        fatigue = bool(opts.get("fatigue", True)) and bool(m.fatigue_loads)
        nmodes = max(1, _i(opts, "nmodes", 6))
        case = opts.get("case") or None
        if case and case not in m.load_cases:
            raise ApiError(f"Lastfall '{case}' unbekannt")
        label = {"all": "Alle Lastfälle + Kombinationen", "case": "Lastfall",
                 "modal": "Eigenschwingungen", "buckling": "Knicken"}[kind]

        def run(progress):
            progress(f"{label} gestartet ({parallel.describe()})")
            if kind == "all":
                an = solver.solve_all(m, progress=progress, design=design, fatigue=fatigue)
                text = an.summary()
                with st.lock:
                    st.analysis, st.results = an, None
            elif kind == "case":
                r = solver.solve_static(m, progress, case=case)
                an = solver.Analysis(m, cases={r.name: r})
                an.envelopes["CASES"] = solver.Envelope(m, an.cases, "Umhüllende Lastfälle")
                text = r.summary()
                with st.lock:
                    st.analysis, st.results = an, None
            elif kind == "modal":
                r = solver.solve_modal(m, nmodes, progress)
                text = r.summary()
                with st.lock:
                    st.results = r
            else:
                r = solver.solve_buckling(m, nmodes, progress, case=case)
                text = r.summary()
                with st.lock:
                    st.results = r
            st.touch()
            st.info(f"{label}: fertig")
            return text

        st.info(f"{label} gestartet")
        st.job = Job(label, run).start()
        return st.job.to_dict()


def start_design(st: State, fatigue: bool = False) -> dict:
    with st.lock:
        if st.busy():
            raise ApiError("Es läuft bereits eine Berechnung", 409)
        an = st.analysis
        m = st.model
        if an is None or not an.cases:
            raise ApiError("Zuerst berechnen (Alle Lastfälle + Kombinationen)")
        if fatigue and not m.fatigue_loads:
            raise ApiError("Keine Ermüdungslasten definiert")
        if not fatigue and not m.members:
            raise ApiError("Keine Stäbe definiert (Stäbe automatisch erkennen)")
        label = "Ermüdungsnachweis" if fatigue else "Nachweise EC3"

        def run(progress):
            if fatigue:
                from ..ec3.fatigue import check_fatigue
                res = check_fatigue(m, an, progress=progress)
                with st.lock:
                    an.fatigue = res
            else:
                from ..ec3.design import check_members
                res = check_members(m, an, progress=progress)
                with st.lock:
                    an.design = res
            st.touch()
            st.info(res.summary())
            return res.summary()

        st.info(f"{label} gestartet")
        st.job = Job(label, run).start()
        return st.job.to_dict()


def load_example(st: State, name: str) -> dict:
    if name not in EXAMPLES:
        raise ApiError(f"Beispiel '{name}' unbekannt: {list(EXAMPLES)}")
    with st.lock:
        if st.busy():
            raise ApiError("Es läuft gerade eine Berechnung", 409)
        st.model = build_example(name)
        st.invalidate()
        st.touch()
        st.info(f"Beispiel geladen: {EXAMPLE_LABELS.get(name, name)}")
        return {"ok": True, "message": f"Beispiel {name} geladen", "geometry_changed": True,
                "state": state_summary(st)}


def replace_model(st: State, d: dict) -> dict:
    with st.lock:
        if st.busy():
            raise ApiError("Es läuft gerade eine Berechnung", 409)
        try:
            m = Model.from_dict(d)
        except Exception as ex:      # noqa: BLE001
            raise ApiError(f"Modell ungültig: {ex}")
        st.model = m
        st.invalidate()
        st.touch()
        st.info(f"Modell geladen: {m.name} ({m.nn} Knoten, {len(m.elements)} Elemente)")
        return {"ok": True, "message": "Modell geladen", "geometry_changed": True,
                "state": state_summary(st)}


def _safe_name(s: str) -> str:
    s = re.sub(r"[^\wäöüÄÖÜß.-]+", "_", s or "modell").strip("_")
    return s[:60] or "modell"


def import_bytes(st: State, name: str, data: bytes, unit: float = None) -> dict:
    ext = os.path.splitext(name or "")[1].lower()
    if not ext:
        raise ApiError("Dateiname mit Endung erwartet")
    path = os.path.join(st.tmpdir, "import_" + _safe_name(os.path.basename(name)))
    with open(path, "wb") as f:
        f.write(data)
    msgs: list[str] = []
    opts = {"unit_scale": unit} if unit else {}
    from ..importers import import_file
    with st.lock:
        if st.busy():
            raise ApiError("Es läuft gerade eine Berechnung", 409)
        try:
            m = import_file(path, log=msgs, **opts)
        except Exception as ex:      # noqa: BLE001
            raise ApiError(f"Import fehlgeschlagen: {ex}\n" + "\n".join(msgs))
        st.model = m
        st.invalidate()
        st.touch()
        st.info(f"Import {os.path.basename(name)}: {m.nn} Knoten, {len(m.elements)} Elemente")
        for s in msgs:
            st.info("  " + s)
        return {"ok": True, "message": f"Import: {m.nn} Knoten, {len(m.elements)} Elemente",
                "messages": msgs, "geometry_changed": True, "state": state_summary(st)}


MIME = {"html": "text/html; charset=utf-8", "pdf": "application/pdf",
        "md": "text/markdown; charset=utf-8", "json": "application/json; charset=utf-8",
        "zip": "application/zip", "xlsx": "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet", "csv": "text/csv; charset=utf-8", "dxf": "image/vnd.dxf",
        "ifc": "application/x-step", "stl": "model/stl", "vtu": "application/xml",
        "sdnf": "text/plain; charset=utf-8", "inp": "text/plain; charset=utf-8",
        "bdf": "text/plain; charset=utf-8", "nc1": "text/plain; charset=utf-8",
        "sza": "application/octet-stream"}


def make_report(st: State, fmt: str = "html") -> tuple[bytes, str, str]:
    fmt = (fmt or "html").lower()
    if fmt not in ("html", "pdf", "md"):
        raise ApiError("fmt: html | pdf | md")
    with st.lock:
        m = st.model
        an = st.analysis if st.analysis is not None else st.results
        if an is None:
            raise ApiError("Keine Ergebnisse - zuerst berechnen")
        from ..report import write_report
        fname = _safe_name(m.name) + "_bericht." + fmt
        path = os.path.join(st.tmpdir, fname)
        try:
            write_report(m, an, path, fmt=fmt)
        except ImportError as ex:
            raise ApiError(f"PDF benötigt reportlab (pip install reportlab svglib): {ex}")
        with open(path, "rb") as f:
            data = f.read()
        st.info(f"Bericht erzeugt: {fname}")
        return data, MIME[fmt], fname


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
                ".webmanifest": "application/manifest+json", ".png": "image/png",
                ".json": "application/json; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = f"Statik3D-Web/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if not getattr(self.server, "quiet", True):
            super().log_message(fmt, *args)

    # ---- Antworten ----
    def _send(self, data: bytes, ctype: str, status: int = 200, extra: dict = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, status: int = 200):
        data = json.dumps(_clean(obj), ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(data, MIME["json"], status)

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 512 * 1024 * 1024:
            raise ApiError("Datei zu groß (max. 512 MB)", 413)
        return self.rfile.read(n) if n else b""

    def _body_json(self, body: bytes) -> dict:
        if not body:
            return {}
        try:
            d = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as ex:
            raise ApiError(f"JSON ungültig: {ex}")
        if not isinstance(d, dict):
            raise ApiError("JSON-Objekt erwartet")
        return d

    def _authorized(self, q: dict) -> bool:
        key = self.server.state.key
        if not key:
            return True
        given = self.headers.get(KEY_HEADER) or q.get("key") or ""
        return secrets.compare_digest(str(given), str(key))

    # ---- Verteilung ----
    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_HEAD(self):
        self._handle("GET")

    def _handle(self, method: str):
        try:
            url = urllib.parse.urlsplit(self.path)
            q = dict(urllib.parse.parse_qsl(url.query, keep_blank_values=True))
            path = url.path
            if path.startswith("/api/"):
                if not self._authorized(q):
                    return self._json({"error": "Schlüssel fehlt oder falsch", "auth": True}, 401)
                body = self._read_body() if method == "POST" else b""
                return self._api(method, path[5:].strip("/"), q, body)
            if method != "GET":
                return self._json({"error": "nicht gefunden"}, 404)
            return self._static(path)
        except ApiError as ex:
            self._json({"error": str(ex)}, ex.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as ex:      # noqa: BLE001 - Fehler an den Browser melden
            traceback.print_exc()
            try:
                self._json({"error": f"{type(ex).__name__}: {ex}"}, 500)
            except Exception:        # noqa: BLE001
                pass

    def _static(self, path: str):
        if path in ("", "/", "/index.html"):
            path = "/index.html"
        name = os.path.normpath(path.lstrip("/"))
        if name.startswith("..") or os.path.isabs(name):
            return self._json({"error": "nicht gefunden"}, 404)
        full = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(full):
            return self._json({"error": "nicht gefunden"}, 404)
        with open(full, "rb") as f:
            data = f.read()
        ctype = STATIC_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
        self._send(data, ctype)

    def _api(self, method: str, path: str, q: dict, body: bytes):
        st: State = self.server.state
        if path == "state":
            return self._json(state_summary(st))
        if path == "model":
            if method == "POST":
                return self._json(replace_model(st, self._body_json(body)))
            with st.lock:
                return self._json(st.model.to_dict())
        if path == "geometry":
            with st.lock:
                return self._json(geometry(st.model, q.get("case") or None))
        if path == "op":
            if method != "POST":
                raise ApiError("POST erwartet", 405)
            return self._json(apply_op(st, self._body_json(body)))
        if path == "example":
            d = self._body_json(body) if method == "POST" else q
            return self._json(load_example(st, d.get("name") or ""))
        if path == "import":
            if method != "POST":
                raise ApiError("POST erwartet", 405)
            unit = float(q["unit"]) if q.get("unit") else None
            return self._json(import_bytes(st, q.get("name") or "", body, unit))
        if path == "solve":
            if method != "POST":
                raise ApiError("POST erwartet", 405)
            return self._json({"ok": True, "job": start_solve(st, self._body_json(body))})
        if path in ("design", "fatigue"):
            if method == "POST":
                return self._json({"ok": True, "job": start_design(st, fatigue=(path == "fatigue"))})
            return self._json(design_payload(st))
        if path == "job":
            return self._json(st.job.to_dict() if st.job is not None else {"status": "keiner"})
        if path == "entries":
            with st.lock:
                return self._json(result_entries(st))
        if path == "results":
            return self._json(result_payload(st, q.get("which") or None, q.get("field") or "umag",
                                             int(q.get("mode") or 0)))
        if path == "diagram":
            return self._json(diagram_payload(st, q.get("which") or None, q.get("quantity") or "My",
                                              int(q.get("n") or 9)))
        if path == "member":
            return self._json(member_payload(st, q.get("which") or None, q.get("name") or ""))
        if path == "report":
            data, mime, fname = make_report(st, q.get("fmt") or "html")
            disp = "attachment" if q.get("download") else "inline"
            return self._send(data, mime, 200,
                              {"Content-Disposition": f'{disp}; filename="{fname}"'})
        if path == "export":
            daten, mime, fname = export_bytes(st, q.get("fmt") or q.get("format") or ".json")
            return self._send(daten, mime, 200,
                              {"Content-Disposition": f'attachment; filename="{fname}"'})
        if path == "download":
            with st.lock:
                m = st.model
                data = json.dumps(_clean(m.to_dict()), ensure_ascii=False, indent=1).encode("utf-8")
                fname = _safe_name(m.name) + ".json"
            return self._send(data, MIME["json"], 200,
                              {"Content-Disposition": f'attachment; filename="{fname}"'})
        if path == "profiles":
            fam = q.get("family") or None
            land = q.get("country") or None
            try:
                lst = profiles.list_profiles(fam, land) if (fam or land) else profiles.list_profiles()
            except KeyError as ex:
                raise ApiError(str(ex))
            return self._json({"family": fam, "country": land, "profiles": lst,
                               "families": [{"code": f, "text": profiles.FAMILY_INFO.get(f, (f,))[0]}
                                            for f in profiles.families(land)] if land else [],
                               "countries": [{"code": c, "name": n, "norm": nn, "families": ff}
                                             for c, n, nn, ff in profiles.countries()]})
        if path == "examples":
            return self._json({k: EXAMPLE_LABELS.get(k, k) for k in EXAMPLES})
        if path == "log":
            return self._json({"log": st.log[-200:]})
        if path == "check":
            with st.lock:
                return self._json({"messages": st.model.check()})
        if path == "settings":
            if method == "POST":
                with st.lock:
                    _apply_settings(st, self._body_json(body))
                    return self._json({"ok": True, "settings": st.settings, "parallel": parallel.describe()})
            return self._json({"settings": st.settings, "parallel": parallel.describe(),
                               "cpu": parallel.cpu_count()})
        if path == "update":
            from .. import update as upd
            try:
                if method == "POST":
                    d = self._body_json(body)
                    info = upd.check()
                    if not info.available and not d.get("force"):
                        return self._json({"ok": False, "message": info.message})
                    if info.kind == "exe":
                        raise ApiError("Das Windows-Programm aktualisiert sich über den Knopf "
                                       "„Update“ unten rechts im Programmfenster auf dem PC.")
                    msg = upd.apply(info, restart=False)
                    if st.bound is None:
                        threading.Timer(1.0, lambda: os.execv(sys.executable, upd.restart_command())).start()
                        msg += " Der Server startet neu; die Seite verbindet sich gleich wieder."
                    st.info(msg)
                    return self._json({"ok": True, "message": msg})
                info = upd.check()
            except upd.UpdateError as ex:
                raise ApiError(str(ex), 502)
            return self._json({"ok": True, "available": info.available, "message": info.message,
                               "kind": info.kind, "url": info.url, "current": upd.describe(),
                               "download": upd.DOWNLOAD_URL, "releases": upd.RELEASES_URL})
        if path == "farm":
            from ..farm import FarmClient
            s = st.settings
            try:
                c = FarmClient(s["farm_host"], int(s["farm_port"]), s["farm_key"])
                status = c.status()
                return self._json({"ok": True, "describe": c.describe(), "status": status})
            except Exception as ex:      # noqa: BLE001
                raise ApiError(f"Farm nicht erreichbar: {ex}", 502)
        raise ApiError(f"/api/{path} unbekannt", 404)


class WebServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, state: State, quiet: bool = True):
        super().__init__(addr, Handler)
        self.state = state
        self.quiet = quiet

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        host = self.server_address[0]
        if host in ("0.0.0.0", "", "::"):
            host = lan_ip()
        return f"http://{host}:{self.port}/"

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


def lan_ip() -> str:
    """IP-Adresse dieses Rechners im lokalen Netz (ohne Datenversand)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def qr_ascii(text: str) -> str:
    """QR-Code als Text (optional: pip install qrcode); sonst leerer String."""
    try:
        import qrcode  # type: ignore
    except ImportError:
        return ""
    try:
        import io as _io
        qr = qrcode.QRCode(border=1)
        qr.add_data(text)
        qr.make(fit=True)
        buf = _io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        return buf.getvalue()
    except Exception:      # noqa: BLE001
        return ""


def make_server(host: str = "0.0.0.0", port: int = 8080, state: State = None, key: str = None,
                model: Model = None, quiet: bool = True) -> WebServer:
    if state is None:
        state = State(model, key)
    elif key is not None:
        state.key = key
    return WebServer((host, port), state, quiet)


def start_server_thread(model: Model = None, host: str = "0.0.0.0", port: int = 8080,
                        key: str = None, bound=None, state: State = None):
    """Server im Hintergrund-Thread. Rueckgabe: (server, thread, state).
    bound: Objekt mit model/analysis/results (Desktop-GUI) -> gemeinsamer Zustand."""
    if state is None:
        state = State(model, key)
    state.bound = bound
    server = make_server(host, port, state)
    t = threading.Thread(target=server.serve_forever, name="statik3d-web", daemon=True)
    t.start()
    return server, t, state


def banner(server: WebServer) -> str:
    st = server.state
    lines = ["Statik3D - Bedienung im Browser / auf dem Handy",
             f"  Auf diesem Rechner : {server.local_url}",
             f"  Im Netzwerk (Handy): {server.url}"]
    if st.key:
        lines.append(f"  Schlüssel          : {st.key}   (im Browser einmalig eingeben)")
    else:
        lines.append("  Schlüssel          : keiner  (empfohlen: --schluessel geheim)")
    lines.append("  Beenden mit Strg+C")
    qr = qr_ascii(server.url + ("?key=" + st.key if st.key else ""))
    if qr:
        lines.append("")
        lines.append(qr)
    return "\n".join(lines)


def serve(host: str = "0.0.0.0", port: int = 8080, key: str = None, model: Model = None,
          quiet: bool = True, out=print) -> int:
    server = make_server(host, port, key=key, model=model, quiet=quiet)
    out(banner(server))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        out("\nServer beendet")
    finally:
        server.server_close()
    return 0
