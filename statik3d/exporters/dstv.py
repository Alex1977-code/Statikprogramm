"""
Export nach DSTV-NC: je Stab eine Datei mit Kopfblock, Bohrungen und Kontur.

Geschrieben wird die "Standardbeschreibung Stahlbau-Teile fuer die
NC-Steuerung" des DSTV, wie sie Fertigung und CNC-Anlagen erwarten. Ziel ist
ein Ordner oder eine ZIP-Datei - eine NC-Datei beschreibt immer genau ein Teil.

    from statik3d.exporters.dstv import write_dstv
    write_dstv(m, "teile.zip")
"""
from __future__ import annotations

import io
import os
import zipfile

import numpy as np

from ..model import Model
from . import _common as C

#: Profilcode nach DSTV aus der Querschnittsart
CODE = {"I": "I", "RHS": "M", "CHS": "RO", "circle": "R", "rect": "B",
        "U": "U", "L": "L", "free": "SO"}


def _profile_code(sec) -> str:
    typ = (sec.typ or "free").upper()
    if typ in ("I",):
        return "I"
    if typ in ("RHS",):
        return "M"
    if typ in ("CHS",):
        return "RO"
    if typ in ("CIRCLE",):
        return "R"
    if typ in ("RECT",):
        return "B"
    name = (sec.name or "").upper()
    if name.startswith("U") or name.startswith("UPE") or name.startswith("UPN"):
        return "U"
    if name.startswith("L"):
        return "L"
    return "SO"


def nc_text(model: Model, name: str, elems: list, auftrag: str = "",
            zeichnung: str = "", stueck: int = 1) -> str:
    """Eine NC-Datei als Text."""
    e = model.elements[elems[0]]
    sec = model.sections.get(e.sec)
    mat = model.materials.get(e.mat)
    L = C.chain_length(model, elems) * 1000.0
    if sec is None:
        raise ValueError(f"Stab '{name}' ohne Querschnitt")
    werk = (mat.grade or mat.name) if mat else "S235"
    gewicht = (sec.A * (mat.rho if mat else 7850.0)) if sec else 0.0
    umfang = 2.0 * ((sec.h or 0.0) + (sec.b or 0.0))
    z = ["ST",
         f"  {auftrag or model.meta.get('projekt') or model.name}",
         f"  {zeichnung or model.meta.get('position') or '-'}",
         "  1",
         f"  {name}",
         f"  {werk}",
         f"  {int(stueck)}",
         f"  {sec.name}",
         f"  {_profile_code(sec)}",
         f"  {L:12.2f}",
         f"  {(sec.h or 0.0) * 1000:12.2f}",
         f"  {(sec.b or 0.0) * 1000:12.2f}",
         f"  {(sec.tf or 0.0) * 1000:12.2f}",
         f"  {(sec.tw or 0.0) * 1000:12.2f}",
         f"  {(sec.r or 0.0) * 1000:12.2f}",
         f"  {gewicht:12.3f}",
         f"  {umfang:12.3f}",
         "       0.00", "       0.00", "       0.00", "       0.00",
         "AK",
         f"  v      0.00      0.00      0.00",
         f"  v  {L:9.2f}      0.00      0.00",
         f"  v  {L:9.2f}  {(sec.h or 0.0) * 1000:9.2f}      0.00",
         f"  v      0.00  {(sec.h or 0.0) * 1000:9.2f}      0.00",
         f"  v      0.00      0.00      0.00",
         "EN"]
    return "\n".join(z) + "\n"


def write_dstv(model: Model, path: str, results=None, log: list = None, **_) -> str:
    """DSTV-NC schreiben: Ordner oder ZIP (an der Endung erkannt)."""
    ketten = [(n, e) for n, e in C.member_chains(model) if e]
    if not ketten:
        raise ValueError("Das Modell enthaelt keine Staebe.")
    als_zip = path.lower().endswith(".zip")
    if als_zip:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, elems in ketten:
                z.writestr(f"{_safe(name)}.nc1",
                           nc_text(model, name, elems).encode("latin-1", "replace"))
    else:
        ordner = path if os.path.isdir(path) or not os.path.splitext(path)[1] \
            else os.path.splitext(path)[0]
        os.makedirs(ordner, exist_ok=True)
        for name, elems in ketten:
            with open(os.path.join(ordner, f"{_safe(name)}.nc1"), "w",
                      encoding="latin-1", errors="replace") as f:
                f.write(nc_text(model, name, elems))
        path = ordner
    C.say(log, f"DSTV-NC geschrieben: {len(ketten)} Teile -> {path}")
    return path


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:60]
