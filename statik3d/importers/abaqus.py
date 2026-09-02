"""
Abaqus / CalculiX Eingabedateien (.inp).

Unterstuetzte Schluesselwoerter (Gross-/Kleinschreibung egal, '**' = Kommentar):
    *NODE [NSET=]                 Knoten (id, x, y[, z])
    *ELEMENT, TYPE=, [ELSET=]     B31/B32/B33/B21 -> beam, T3D2/T2D2 -> truss,
                                  S3/S3R/STRI3/STRI65 -> shell3, S4/S4R/S4R5 -> shell4,
                                  C3D4 -> tet4, C3D10/C3D10M -> tet10, C3D8* -> hex8
    *NSET / *ELSET [GENERATE]     Knoten-/Elementmengen (auch verschachtelt)
    *MATERIAL, *ELASTIC, *DENSITY, *EXPANSION, *PLASTIC (fy)
    *BEAM SECTION SECTION=RECT|CIRC|PIPE|BOX|I, *BEAM GENERAL SECTION
    *SHELL SECTION (Dicke), *SOLID SECTION (Flaeche bei Fachwerkstaeben)
    *BOUNDARY (Knoten/NSET, FHG von, FHG bis, Wert; ENCASTRE, PINNED, XSYMM ...)
    *STEP ... *END STEP           jeder Schritt -> Lastfall STEP-n
    *CLOAD                        Knotenlast (Knoten/NSET, FHG, Wert)
    *DLOAD                        P / Pn (Flaechendruck), GRAV, PX/PY/PZ (Stablast)
    *INCLUDE, INPUT=              Datei einfuegen
Einheiten: SI angenommen; 'unit_scale' skaliert nur die Koordinaten.
"""
from __future__ import annotations

import os
import re
from typing import Optional

import numpy as np

from ..model import Model, Material, Section
from ..elements.solid import normalize_tet10
from . import _common as C

ELEMENT_TYPES = {
    "beam": ("B31", "B31H", "B32", "B32H", "B33", "B33H", "B21", "B21H", "B22", "B23",
             "B31OS", "B32OS", "PIPE31", "PIPE32"),
    "truss": ("T3D2", "T3D2H", "T2D2", "T2D2H", "T3D3", "T2D3"),
    "shell3": ("S3", "S3R", "S3RS", "STRI3", "STRI65", "S6", "M3D3", "CPS3", "CPE3"),
    "shell4": ("S4", "S4R", "S4RS", "S4R5", "S4RSW", "S8R", "S8R5", "M3D4", "M3D4R",
               "CPS4", "CPS4R", "CPE4", "CPE4R"),
    "tet4": ("C3D4", "C3D4H"),
    "tet10": ("C3D10", "C3D10M", "C3D10H", "C3D10MH", "C3D10I"),
    "hex8": ("C3D8", "C3D8R", "C3D8I", "C3D8H", "C3D8RH", "C3D8IH", "C3D20", "C3D20R"),
}
_TYPE_MAP = {abq: typ for typ, names in ELEMENT_TYPES.items() for abq in names}
_CORNER_NODES = {"beam": 2, "truss": 2, "shell3": 3, "shell4": 4, "tet4": 4,
                 "tet10": 10, "hex8": 8}

_BOUNDARY_NAMES = {
    "ENCASTRE": [0, 1, 2, 3, 4, 5], "PINNED": [0, 1, 2],
    "XSYMM": [0, 4, 5], "YSYMM": [1, 3, 5], "ZSYMM": [2, 3, 4],
    "XASYMM": [1, 2, 3], "YASYMM": [0, 2, 4], "ZASYMM": [0, 1, 5],
}


# --------------------------------------------------------------------------
# Lexer: Keyword-Bloecke mit Datenzeilen
# --------------------------------------------------------------------------
class Block:
    __slots__ = ("keyword", "params", "lines")

    def __init__(self, keyword: str, params: dict, lines: list):
        self.keyword = keyword
        self.params = params
        self.lines = lines

    def get(self, key: str, default=None):
        return self.params.get(key.upper(), default)


def _parse_keyword(line: str) -> tuple[str, dict]:
    parts = [p.strip() for p in line[1:].split(",")]
    keyword = parts[0].upper().replace("  ", " ")
    keyword = re.sub(r"\s+", " ", keyword)
    params = {}
    for p in parts[1:]:
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip()
        else:
            params[p.upper()] = True
    return keyword, params


def read_blocks(path: str, log: list = None, _depth: int = 0) -> list[Block]:
    """Datei in Keyword-Bloecke zerlegen (*INCLUDE wird aufgeloest)."""
    blocks: list[Block] = []
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    cur: Optional[Block] = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("**"):
            continue
        if s.startswith("*"):
            keyword, params = _parse_keyword(s)
            if keyword == "INCLUDE":
                inc = params.get("INPUT")
                if inc and _depth < 10:
                    inc_path = inc if os.path.isabs(inc) else \
                        os.path.join(os.path.dirname(path), inc)
                    if os.path.exists(inc_path):
                        blocks.extend(read_blocks(inc_path, log, _depth + 1))
                    else:
                        C.warn(log, f"*INCLUDE: Datei '{inc}' nicht gefunden")
                cur = None
                continue
            cur = Block(keyword, params, [])
            blocks.append(cur)
        elif cur is not None:
            cur.lines.append(s)
    return blocks


def _split(line: str) -> list[str]:
    return [p.strip() for p in line.split(",")]


def _join_continued(lines: list[str]) -> list[list[str]]:
    """Datenzeilen, die mit ',' enden, mit der Folgezeile verbinden."""
    out = []
    buf: list[str] = []
    for ln in lines:
        parts = _split(ln)
        cont = ln.rstrip().endswith(",")
        if cont:
            parts = parts[:-1]
        buf.extend(parts)
        if not cont:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
class _State:
    def __init__(self, model: Model, log, unit_scale: float, tol: float):
        self.model = model
        self.log = log
        self.scale = unit_scale
        self.nodes = C.NodeIndex(model, tol)
        self.nid: dict[int, int] = {}            # Abaqus-Knotennummer -> Index
        self.eid: dict[int, int] = {}            # Abaqus-Elementnummer -> Index
        self.nsets: dict[str, list[int]] = {}    # Name -> Abaqus-Knotennummern
        self.elsets: dict[str, list[int]] = {}   # Name -> Abaqus-Elementnummern
        self.materials: dict[str, Material] = {}
        self.cur_mat: Optional[Material] = None
        self.step = 0
        self.case = "LF1"
        self.sec_counter = 0
        self.unsupported: dict[str, int] = {}
        self.supports: dict[int, dict[int, float]] = {}   # Knotenindex -> {dof: Wert}

    def node(self, ref: str) -> Optional[int]:
        v = C.parse_number(ref)
        if v is None:
            return None
        return self.nid.get(int(v))

    def node_list(self, ref: str) -> list[int]:
        """Knotennummer oder NSET-Name -> Liste von Knotenindizes."""
        ref = ref.strip()
        v = C.parse_number(ref)
        if v is not None:
            idx = self.nid.get(int(v))
            return [idx] if idx is not None else []
        ids = self.nsets.get(ref.upper(), [])
        return [self.nid[n] for n in ids if n in self.nid]

    def elem_list(self, ref: str) -> list[int]:
        ref = ref.strip()
        v = C.parse_number(ref)
        if v is not None:
            idx = self.eid.get(int(v))
            return [idx] if idx is not None else []
        ids = self.elsets.get(ref.upper(), [])
        return [self.eid[e] for e in ids if e in self.eid]


def _read_set(block: Block, key: str, existing: dict, st: _State) -> None:
    name = block.get(key)
    if not name:
        return
    name = name.upper()
    ids = existing.setdefault(name, [])
    if block.get("GENERATE"):
        for parts in _join_continued(block.lines):
            nums = [C.parse_number(p) for p in parts if p]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 2:
                a, b = int(nums[0]), int(nums[1])
                step = int(nums[2]) if len(nums) > 2 and nums[2] else 1
                ids.extend(range(a, b + 1, max(1, step)))
    else:
        for parts in _join_continued(block.lines):
            for p in parts:
                if not p:
                    continue
                v = C.parse_number(p)
                if v is not None:
                    ids.append(int(v))
                else:                      # verschachtelte Menge
                    ids.extend(existing.get(p.upper(), []))


def _section_from_beam_block(block: Block, st: _State) -> Optional[Section]:
    kind = (block.get("SECTION") or "RECT").upper()
    dims = []
    if block.lines:
        dims = [C.parse_number(p) for p in _split(block.lines[0])]
        dims = [d for d in dims if d is not None]
    st.sec_counter += 1
    name = block.get("ELSET") or f"SEC-{st.sec_counter}"
    name = C.unique_name(st.model.sections, str(name))
    s = st.scale
    try:
        # Abaqus: a = Abmessung in Richtung n1 (Standard n1 = (0,0,-1) -> vertikal,
        # entspricht unserer lokalen z-Achse = Hoehe h), b = Abmessung in Richtung n2
        if kind == "RECT" and len(dims) >= 2:
            return Section.rectangle(name, dims[1] * s, dims[0] * s)
        if kind == "CIRC" and len(dims) >= 1:
            return Section.circle(name, 2 * dims[0] * s)
        if kind == "PIPE" and len(dims) >= 2:
            return Section.pipe(name, 2 * dims[0] * s, dims[1] * s)
        if kind == "BOX" and len(dims) >= 3:
            a, b = dims[0] * s, dims[1] * s
            t = dims[2] * s
            return Section.rhs(name, a, b, t, r_out=0.0, r_in=0.0)
        if kind == "I" and len(dims) >= 7:
            _, h, b1, b2, t1, t2, t3 = dims[:7]
            return Section.i_profile(name, h * s, max(b1, b2) * s, t3 * s,
                                     0.5 * (t1 + t2) * s, 0.0, fabrication="welded")
    except Exception as ex:
        C.warn(st.log, f"*BEAM SECTION {kind}: {ex}")
    C.warn(st.log, f"*BEAM SECTION SECTION={kind} mit {len(dims)} Werten nicht "
                   f"umsetzbar - {C.DEFAULT_PROFILE} verwendet")
    sec = C.section_from_designation(C.DEFAULT_PROFILE, name)
    return sec


def _apply_boundary(block: Block, st: _State) -> None:
    for parts in _join_continued(block.lines):
        if not parts or not parts[0]:
            continue
        targets = st.node_list(parts[0])
        if not targets:
            C.warn(st.log, f"*BOUNDARY: Knoten/NSET '{parts[0]}' unbekannt")
            continue
        spec = parts[1].upper() if len(parts) > 1 else ""
        value = C.parse_number(parts[3]) if len(parts) > 3 else None
        if spec in _BOUNDARY_NAMES:
            dofs = _BOUNDARY_NAMES[spec]
            value = 0.0
        else:
            d1 = C.parse_number(spec)
            if d1 is None:
                C.warn(st.log, f"*BOUNDARY: Angabe '{spec}' nicht verstanden")
                continue
            d2 = C.parse_number(parts[2]) if len(parts) > 2 and parts[2] else None
            d1 = int(d1)
            d2 = int(d2) if d2 is not None else d1
            dofs = [d - 1 for d in range(d1, d2 + 1) if 1 <= d <= 6]
            if not dofs:
                C.warn(st.log, f"*BOUNDARY: FHG {d1}..{d2} (nur 1-6 unterstuetzt) ignoriert")
                continue
        for n in targets:
            d = st.supports.setdefault(n, {})
            for dof in dofs:
                d[dof] = float(value or 0.0) * (st.scale if dof < 3 else 1.0)


def _apply_cload(block: Block, st: _State) -> None:
    for parts in _join_continued(block.lines):
        if len(parts) < 3:
            continue
        targets = st.node_list(parts[0])
        dof = C.parse_number(parts[1])
        val = C.parse_number(parts[2])
        if not targets or dof is None or val is None or not 1 <= int(dof) <= 6:
            C.warn(st.log, f"*CLOAD: Zeile '{', '.join(parts)}' nicht verwendbar")
            continue
        for n in targets:
            F = [0.0] * 6
            F[int(dof) - 1] = val
            st.model.load_node(n, *F, case=st.case)


def _apply_dload(block: Block, st: _State) -> None:
    model = st.model
    for parts in _join_continued(block.lines):
        if len(parts) < 3:
            continue
        label = parts[1].upper()
        mag = C.parse_number(parts[2])
        if mag is None:
            continue
        if label == "GRAV":
            vec = [C.parse_number(p) or 0.0 for p in parts[3:6]]
            while len(vec) < 3:
                vec.append(0.0)
            model.case(st.case).gravity = [mag * v for v in vec]
            if parts[0] and st.elem_list(parts[0]) and \
                    len(st.elem_list(parts[0])) < len(model.elements):
                C.say(st.log, "*DLOAD GRAV: Eigengewicht wirkt auf das gesamte Modell "
                              "(Elementmenge wird nicht unterschieden)")
            continue
        elems = st.elem_list(parts[0])
        if not elems:
            C.warn(st.log, f"*DLOAD: Element/ELSET '{parts[0]}' unbekannt")
            continue
        m = re.match(r"^P(\d*)$", label)
        if m:
            face = int(m.group(1)) - 1 if m.group(1) else 0
            for e in elems:
                el = model.elements[e]
                if el.typ.startswith("shell"):
                    # Abaqus: positiver Druck wirkt entgegen der Normalen -> -p
                    model.load_face(e, -mag, 0, case=st.case)
                elif el.typ in ("tet4", "tet10", "hex8"):
                    model.load_face(e, mag, max(0, face), case=st.case)
                else:
                    C.warn(st.log, f"*DLOAD {label} auf Stabelement ignoriert")
            continue
        m = re.match(r"^P([XYZ])$", label)
        if m:
            k = "XYZ".index(m.group(1))
            q = [0.0, 0.0, 0.0]
            q[k] = mag
            for e in elems:
                if model.elements[e].typ in ("beam", "truss"):
                    model.load_beam(e, *q, system="global", case=st.case)
            continue
        st.unsupported[f"*DLOAD {label}"] = st.unsupported.get(f"*DLOAD {label}", 0) + 1


def import_inp(path: str, model: Model = None, log: list = None,
               unit_scale: float = 1.0, tol: float = C.DEFAULT_TOL,
               **_ignored) -> Model:
    """Abaqus/CalculiX-Datei importieren."""
    if model is None:
        model = Model(os.path.splitext(os.path.basename(path))[0])
    st = _State(model, log, float(unit_scale), tol)
    blocks = read_blocks(path, log)

    # ---- Durchlauf 1: Knoten, Elemente, Mengen, Materialien ----------------
    elem_blocks: list[tuple[Block, str]] = []
    for b in blocks:
        try:
            if b.keyword == "NODE":
                if b.get("SYSTEM") and str(b.get("SYSTEM")).upper() != "R":
                    C.warn(log, "*NODE, SYSTEM=C/S wird nicht unterstuetzt (als kartesisch gelesen)")
                nset = b.get("NSET")
                ids = st.nsets.setdefault(nset.upper(), []) if nset else None
                for parts in _join_continued(b.lines):
                    nums = [C.parse_number(p) for p in parts]
                    if not nums or nums[0] is None:
                        continue
                    xyz = [(v or 0.0) * st.scale for v in nums[1:4]]
                    while len(xyz) < 3:
                        xyz.append(0.0)
                    n = int(nums[0])
                    st.nid[n] = st.nodes.add(*xyz)
                    if ids is not None:
                        ids.append(n)
            elif b.keyword == "ELEMENT":
                typ_abq = (b.get("TYPE") or "").upper()
                typ = _TYPE_MAP.get(typ_abq)
                if typ is None:
                    st.unsupported[f"*ELEMENT TYPE={typ_abq}"] = \
                        st.unsupported.get(f"*ELEMENT TYPE={typ_abq}", 0) + 1
                    continue
                elem_blocks.append((b, typ))
            elif b.keyword == "NSET":
                _read_set(b, "NSET", st.nsets, st)
            elif b.keyword == "ELSET":
                _read_set(b, "ELSET", st.elsets, st)
            elif b.keyword == "MATERIAL":
                name = str(b.get("NAME") or f"MAT-{len(st.materials) + 1}")
                st.cur_mat = Material(name, 210e9, 0.3, 7850.0, 1.2e-5)
                st.materials[name.upper()] = st.cur_mat
            elif b.keyword == "ELASTIC" and st.cur_mat is not None:
                if (b.get("TYPE") or "ISO").upper() not in ("ISO", "ISOTROPIC"):
                    C.warn(log, f"*ELASTIC, TYPE={b.get('TYPE')} - nur isotrop unterstuetzt, "
                                f"erste beiden Werte als E, nu gelesen")
                if b.lines:
                    vals = [C.parse_number(p) for p in _split(b.lines[0])]
                    if vals and vals[0]:
                        st.cur_mat.E = vals[0]
                    if len(vals) > 1 and vals[1] is not None:
                        st.cur_mat.nu = vals[1]
            elif b.keyword == "DENSITY" and st.cur_mat is not None and b.lines:
                v = C.parse_number(_split(b.lines[0])[0])
                if v:
                    st.cur_mat.rho = v
            elif b.keyword == "EXPANSION" and st.cur_mat is not None and b.lines:
                v = C.parse_number(_split(b.lines[0])[0])
                if v is not None:
                    st.cur_mat.alpha = v
            elif b.keyword == "PLASTIC" and st.cur_mat is not None and b.lines:
                v = C.parse_number(_split(b.lines[0])[0])
                if v:
                    st.cur_mat.fy = v
                    grade = C.steel_grade_from_text(st.cur_mat.name)
                    if grade:
                        st.cur_mat.grade = grade
        except Exception as ex:
            C.warn(log, f"*{b.keyword}: {ex}")
    st.nodes.flush()
    for m in st.materials.values():
        model.add_material(m)
    default_mat = C.ensure_material(model, None, log, quiet=True)

    # ---- Elemente (Material/Querschnitt wird spaeter zugewiesen) ------------
    elem_abq_type: dict[int, str] = {}
    for b, typ in elem_blocks:
        elset = b.get("ELSET")
        ids = st.elsets.setdefault(str(elset).upper(), []) if elset else None
        need = _CORNER_NODES[typ]
        for parts in _join_continued(b.lines):
            nums = [C.parse_number(p) for p in parts if p]
            if not nums or nums[0] is None:
                continue
            eid = int(nums[0])
            conn = [int(v) for v in nums[1:] if v is not None]
            try:
                if typ == "beam" and len(conn) >= 3 and (b.get("TYPE") or "").upper() \
                        .startswith(("B32", "B22")):
                    conn = [conn[0], conn[2]]           # Mittelknoten ignorieren
                elif typ == "shell3" and len(conn) > 3:
                    conn = conn[:3]
                elif typ == "shell4" and len(conn) > 4:
                    conn = conn[:4]
                elif typ == "hex8" and len(conn) > 8:
                    conn = conn[:8]
                if len(conn) < need:
                    C.warn(log, f"Element {eid}: {len(conn)} Knoten, {need} erwartet")
                    continue
                idx = [st.nid[n] for n in conn[:need]]
                if typ == "tet10":
                    # Abaqus: 5..10 = (1,2),(2,3),(3,1),(1,4),(2,4),(3,4)
                    idx = normalize_tet10(idx, model.nodes[idx])
                e = model.add_element(typ, idx, default_mat, None,
                                      group=str(elset or "default"))
                st.eid[eid] = e
                elem_abq_type[e] = (b.get("TYPE") or "").upper()
                if ids is not None:
                    ids.append(eid)
            except KeyError as ex:
                C.warn(log, f"Element {eid}: Knoten {ex} unbekannt")

    # ---- Durchlauf 2: Querschnitte, Lager, Lasten, Schritte ----------------
    sec_assigned: set[int] = set()
    for b in blocks:
        try:
            kw = b.keyword
            if kw in ("BEAM SECTION", "BEAM GENERAL SECTION", "SHELL SECTION",
                      "SOLID SECTION", "MEMBRANE SECTION"):
                elems = st.elem_list(str(b.get("ELSET") or ""))
                mat_name = str(b.get("MATERIAL") or "")
                mat = None
                for k, m in st.materials.items():
                    if k == mat_name.upper():
                        mat = m.name
                if mat is None:
                    mat = default_mat
                    if mat_name:
                        C.warn(log, f"*{kw}: Material '{mat_name}' unbekannt")
                if not elems:
                    C.warn(log, f"*{kw}: ELSET '{b.get('ELSET')}' leer oder unbekannt")
                    continue
                sec_name = None
                if kw == "BEAM SECTION":
                    sec = _section_from_beam_block(b, st)
                    if sec is not None:
                        model.add_section(sec)
                        sec_name = sec.name
                    if len(b.lines) > 1:
                        C.say(log, f"*BEAM SECTION {b.get('ELSET')}: Richtungskosinus "
                                   f"'{b.lines[1]}' wird ignoriert (Verdrehung 0)")
                elif kw == "BEAM GENERAL SECTION":
                    vals = [C.parse_number(p) for p in _split(b.lines[0])] if b.lines else []
                    vals = [v or 0.0 for v in vals]
                    s = st.scale
                    st.sec_counter += 1
                    name = C.unique_name(model.sections, str(b.get("ELSET") or f"SEC-{st.sec_counter}"))
                    # Datenzeile: A, I11, I12, I22, J  (1-Achse ~ lokale z, 2-Achse ~ lokale y)
                    if len(vals) >= 5:
                        model.add_section(Section(name, A=vals[0] * s ** 2,
                                                  Iy=vals[1] * s ** 4, Iz=vals[3] * s ** 4,
                                                  It=vals[4] * s ** 4))
                        sec_name = name
                elif kw == "SHELL SECTION":
                    t = C.parse_number(_split(b.lines[0])[0]) if b.lines else None
                    t = (t or 0.0) * st.scale
                    sec_name = C.ensure_shell_prop(
                        model, C.unique_name(model.shells, str(b.get("ELSET") or "t")), t, log)
                elif kw == "SOLID SECTION":
                    area = C.parse_number(_split(b.lines[0])[0]) if b.lines else None
                    if area and any(model.elements[e].typ == "truss" for e in elems):
                        st.sec_counter += 1
                        name = C.unique_name(model.sections,
                                             str(b.get("ELSET") or f"SEC-{st.sec_counter}"))
                        model.add_section(Section(name, A=area * st.scale ** 2,
                                                  Iy=1e-12, Iz=1e-12, It=1e-12))
                        sec_name = name
                for e in elems:
                    el = model.elements[e]
                    el.mat = mat
                    sec_assigned.add(e)
                    if el.typ in ("beam", "truss") and sec_name in model.sections:
                        el.sec = sec_name
                    elif el.typ.startswith("shell") and sec_name in model.shells:
                        el.sec = sec_name
            elif kw == "STEP":
                st.step += 1
                name = str(b.get("NAME") or f"STEP-{st.step}")
                if name in model.load_cases:
                    name = C.unique_name(model.load_cases, name)
                C.get_or_add_case(model, name, "G" if st.step == 1 else "Q",
                                  f"Abaqus *STEP {st.step}")
                st.case = name
            elif kw == "END STEP":
                st.case = "LF1"
            elif kw == "BOUNDARY":
                _apply_boundary(b, st)
            elif kw == "CLOAD":
                if st.case not in model.load_cases:
                    C.get_or_add_case(model, st.case, "G")
                _apply_cload(b, st)
            elif kw == "DLOAD":
                if st.case not in model.load_cases:
                    C.get_or_add_case(model, st.case, "G")
                _apply_dload(b, st)
            elif kw in ("NODE", "ELEMENT", "NSET", "ELSET", "MATERIAL", "ELASTIC",
                        "DENSITY", "EXPANSION", "PLASTIC", "HEADING", "PREPRINT",
                        "STATIC", "END STEP", "OUTPUT", "NODE OUTPUT", "ELEMENT OUTPUT",
                        "NODE PRINT", "EL PRINT", "NODE FILE", "EL FILE", "RESTART",
                        "SYSTEM", "PART", "END PART", "ASSEMBLY", "END ASSEMBLY",
                        "INSTANCE", "END INSTANCE", "TRANSVERSE SHEAR STIFFNESS",
                        "SECTION CONTROLS", "ORIENTATION", "SURFACE", "CONTROLS"):
                pass
            else:
                st.unsupported[f"*{kw}"] = st.unsupported.get(f"*{kw}", 0) + 1
        except Exception as ex:
            C.warn(log, f"*{b.keyword}: {ex}")

    # ---- fehlende Querschnitte ---------------------------------------------
    missing_beam = [i for i, e in enumerate(model.elements)
                    if e.typ in ("beam", "truss") and e.sec not in model.sections]
    if missing_beam:
        fb = C.ensure_section(model, None, log)
        for i in missing_beam:
            model.elements[i].sec = fb
        C.warn(log, f"{len(missing_beam)} Stabelemente ohne *BEAM SECTION - {fb} zugewiesen")
    missing_shell = [i for i, e in enumerate(model.elements)
                     if e.typ.startswith("shell") and e.sec not in model.shells]
    if missing_shell:
        sp = C.ensure_shell_prop(model, None, None, log)
        for i in missing_shell:
            model.elements[i].sec = sp
        C.warn(log, f"{len(missing_shell)} Schalenelemente ohne *SHELL SECTION - '{sp}' zugewiesen")

    # ---- Lager -----------------------------------------------------------
    for n, d in st.supports.items():
        dofs = sorted(d)
        vals = [d[k] for k in dofs]
        model.fix(n, dofs, values=vals if any(vals) else None)

    for k, n in sorted(st.unsupported.items()):
        C.say(log, f"{k}: {n} x nicht unterstuetzt (ignoriert)")
    C.say(log, f"INP: {model.nn} Knoten, {len(model.elements)} Elemente, "
               f"{len(model.supports)} Lagerknoten, {len(model.load_cases)} Lastfaelle")
    return model
