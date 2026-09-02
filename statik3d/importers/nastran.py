"""
Nastran Bulk Data (.bdf / .nas / .dat).

Formate: Small Field (8 Zeichen), Large Field ('*', 16 Zeichen), Free Field
(Kommas); Fortsetzungszeilen ('+', '*' oder leeres erstes Feld); '$' Kommentare;
'BEGIN BULK' / 'ENDDATA'; Zahlen wie '1.2-3' (= 1.2e-3).

Karten:
    GRID (inkl. PS), GRDSET
    CBAR/CBEAM + PBAR/PBEAM/PBARL/PBEAML (BAR, ROD, TUBE, BOX, I)
    CROD/CONROD + PROD                 -> Fachwerkstab
    CTRIA3/CQUAD4 + PSHELL             -> Schalen
    CTETRA (4/10 Knoten), CHEXA (8)    -> Volumen
    MAT1 (E, G, NU, RHO, A, ST -> fy)
    SPC / SPC1                         -> Lager (Komponenten 123456)
    FORCE / MOMENT (SID -> Lastfall 'SID n'), PLOAD2 / PLOAD4, GRAV
    LOAD                               -> Kombination
    TEMP / TEMPD                       -> ignoriert (Hinweis)
Achsen: Nastran-Ebene 1 (Orientierungsvektor) = lokale y-Achse; damit I1 -> Iz,
I2 -> Iy. Einheiten SI, 'unit_scale' skaliert die Koordinaten.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from ..model import Model, Material, Section
from ..elements.solid import normalize_tet10
from . import _common as C

_NUM_SHORT = re.compile(r"^([+-]?\d*\.?\d*)([+-]\d+)$")


# --------------------------------------------------------------------------
# Lesen
# --------------------------------------------------------------------------
def _num(s: str) -> Optional[float]:
    """Nastran-Zahl: '1.2-3' -> 1.2e-3, '1.D+3' -> 1000."""
    s = (s or "").strip().upper().replace("D", "E")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        m = _NUM_SHORT.match(s)
        if m and m.group(1) not in ("", "+", "-", "."):
            try:
                return float(m.group(1) + "E" + m.group(2))
            except ValueError:
                return None
    return None


def _int(s: str) -> Optional[int]:
    v = _num(s)
    return int(v) if v is not None else None


def _split_line(line: str) -> tuple[str, list[str], bool]:
    """Physische Zeile -> (Kartenname, Datenfelder, ist_Fortsetzung)."""
    if "," in line:
        fields = [f.strip() for f in line.split(",")]
        name = fields[0]
        large = name.endswith("*") or name.startswith("*")
        n = 4 if large else 8
        data = fields[1:]
        if data and data[-1].startswith(("+", "*")) and len(data) > n:
            data = data[:-1]                  # Fortsetzungsmarke (Feld 10)
        data = (data + [""] * n)[:n]          # Felder sind positionsgebunden
    else:
        line = line.rstrip("\n\r")
        name = line[0:8].strip()
        if name.startswith("*") or name.endswith("*"):
            data = [line[8:24], line[24:40], line[40:56], line[56:72]]
        else:
            data = [line[8 + 8 * k: 16 + 8 * k] for k in range(8)]
        data = [d.strip() for d in data]
    cont = name == "" or name[0] in "+*"
    return name.rstrip("*").upper(), data, cont


def read_cards(path: str, log: list = None, _depth: int = 0) -> list[list[str]]:
    """Alle Karten des Bulk-Data-Abschnitts: [Name, Feld1, Feld2, ...]."""
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if ln.strip().upper().startswith("BEGIN BULK"):
            start = i + 1
            break
    cards: list[list[str]] = []
    cur: Optional[list[str]] = None
    for ln in lines[start:]:
        s = ln.rstrip()
        if not s.strip() or s.lstrip().startswith("$"):
            continue
        up = s.strip().upper()
        if up.startswith("ENDDATA"):
            break
        if up.startswith("INCLUDE"):
            m = re.search(r"INCLUDE\s+'?([^']+)'?", s.strip(), re.IGNORECASE)
            if m and _depth < 10:
                inc = m.group(1).strip()
                inc_path = inc if os.path.isabs(inc) else os.path.join(os.path.dirname(path), inc)
                if os.path.exists(inc_path):
                    cards.extend(read_cards(inc_path, log, _depth + 1))
                else:
                    C.warn(log, f"INCLUDE: Datei '{inc}' nicht gefunden")
            continue
        name, data, cont = _split_line(s)
        if cont:
            if cur is not None:
                cur.extend(data)
            continue
        cur = [name] + data
        cards.append(cur)
    return cards


def _f(card: list[str], i: int) -> str:
    return card[i].strip() if i < len(card) else ""


def _expand_thru(fields: list[str]) -> list[int]:
    """['1', 'THRU', '5', '8'] -> [1, 2, 3, 4, 5, 8]."""
    out: list[int] = []
    i = 0
    while i < len(fields):
        s = fields[i].strip().upper()
        if not s:
            i += 1
            continue
        if s == "THRU" and out and i + 1 < len(fields):
            end = _int(fields[i + 1])
            if end is not None:
                out.extend(range(out[-1] + 1, end + 1))
            i += 2
            continue
        if s in ("BY", "EXCEPT"):
            i += 2
            continue
        v = _int(s)
        if v is not None:
            out.append(v)
        i += 1
    return out


def _dofs_from_components(s: str) -> list[int]:
    return sorted({int(ch) - 1 for ch in s.strip() if ch in "123456"})


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
def _section_from_pbarl(pid: int, typ: str, dims: list[float], scale: float,
                        log: list) -> Section:
    name = f"PID {pid}"
    s = scale
    typ = typ.upper()
    try:
        if typ == "BAR" and len(dims) >= 2:
            return Section.rectangle(name, dims[0] * s, dims[1] * s)   # b = DIM1 (y), h = DIM2 (z)
        if typ == "ROD" and len(dims) >= 1:
            return Section.circle(name, 2 * dims[0] * s)
        if typ == "TUBE" and len(dims) >= 2:
            return Section.pipe(name, 2 * dims[0] * s, (dims[0] - dims[1]) * s)
        if typ == "BOX" and len(dims) >= 4:
            b, h, t1, t2 = dims[:4]
            return Section.rhs(name, h * s, b * s, 0.5 * (t1 + t2) * s, r_out=0.0, r_in=0.0)
        if typ == "I" and len(dims) >= 6:
            h, b1, b2, tw, tf1, tf2 = dims[:6]
            return Section.i_profile(name, h * s, max(b1, b2) * s, tw * s,
                                     0.5 * (tf1 + tf2) * s, 0.0, fabrication="welded")
    except Exception as ex:
        C.warn(log, f"PBARL {pid} ({typ}): {ex}")
    C.warn(log, f"PBARL/PBEAML {pid}: Typ '{typ}' mit {len(dims)} Abmessungen nicht "
                f"umsetzbar - {C.DEFAULT_PROFILE} verwendet")
    return C.section_from_designation(C.DEFAULT_PROFILE, name)


def import_bdf(path: str, model: Model = None, log: list = None,
               unit_scale: float = 1.0, tol: float = C.DEFAULT_TOL,
               **_ignored) -> Model:
    """Nastran-Bulk-Data-Datei importieren."""
    if model is None:
        model = Model(os.path.splitext(os.path.basename(path))[0])
    scale = float(unit_scale)
    cards = read_cards(path, log)
    nodes = C.NodeIndex(model, tol)

    grids: dict[int, int] = {}                 # GRID-ID -> Knotenindex
    grid_ps: dict[int, str] = {}
    default_ps = ""
    mats: dict[int, str] = {}                  # MID -> Materialname
    props: dict[int, dict] = {}                # PID -> {'kind', 'mid', 'sec'/'t', ...}
    elems: dict[int, int] = {}                 # EID -> Elementindex
    elem_cards: list[list[str]] = []
    load_cards: list[list[str]] = []
    spc_cards: list[list[str]] = []
    unsupported: dict[str, int] = {}
    pbarl_raw: dict[int, tuple] = {}

    # ---- Durchlauf 1: Knoten, Materialien, Eigenschaften -------------------
    for card in cards:
        name = card[0]
        try:
            if name == "GRID":
                gid = _int(_f(card, 1))
                if gid is None:
                    continue
                xyz = [(_num(_f(card, k)) or 0.0) * scale for k in (3, 4, 5)]
                grids[gid] = nodes.add(*xyz)
                if _f(card, 7):
                    grid_ps[gid] = _f(card, 7)
                if _f(card, 2) and _int(_f(card, 2)):
                    unsupported["GRID mit CP != 0 (Koordinatensystem ignoriert)"] = \
                        unsupported.get("GRID mit CP != 0 (Koordinatensystem ignoriert)", 0) + 1
            elif name == "GRDSET":
                default_ps = _f(card, 7)
            elif name == "MAT1":
                mid = _int(_f(card, 1))
                if mid is None:
                    continue
                E = _num(_f(card, 2))
                G = _num(_f(card, 3))
                nu = _num(_f(card, 4))
                rho = _num(_f(card, 5))
                alpha = _num(_f(card, 6))
                st = _num(_f(card, 9))
                if nu is None and E and G:
                    nu = E / (2.0 * G) - 1.0
                m = Material(f"MAT {mid}", E or 210e9, nu if nu is not None else 0.3,
                             rho if rho else 7850.0, alpha if alpha is not None else 1.2e-5,
                             fy=st if st else None)
                model.add_material(m)
                mats[mid] = m.name
            elif name == "PBAR":
                pid = _int(_f(card, 1))
                vals = [_num(_f(card, k)) or 0.0 for k in (3, 4, 5, 6)]
                A, I1, I2, J = vals
                sec = Section(f"PID {pid}", A=A * scale ** 2, Iy=I2 * scale ** 4,
                              Iz=I1 * scale ** 4, It=(J or 1e-12) * scale ** 4)
                model.add_section(sec)
                props[pid] = {"kind": "beam", "mid": _int(_f(card, 2)), "sec": sec.name}
            elif name == "PBEAM":
                pid = _int(_f(card, 1))
                vals = [_num(_f(card, k)) or 0.0 for k in (3, 4, 5, 6, 7)]
                A, I1, I2, _I12, J = vals
                sec = Section(f"PID {pid}", A=A * scale ** 2, Iy=I2 * scale ** 4,
                              Iz=I1 * scale ** 4, It=(J or 1e-12) * scale ** 4)
                model.add_section(sec)
                props[pid] = {"kind": "beam", "mid": _int(_f(card, 2)), "sec": sec.name}
            elif name in ("PBARL", "PBEAML"):
                pid = _int(_f(card, 1))
                typ = _f(card, 4).upper()
                dims = []
                for k in range(9, len(card)):
                    v = _num(_f(card, k))
                    if v is None:
                        if _f(card, k):
                            break
                        continue
                    dims.append(v)
                pbarl_raw[pid] = (typ, dims)
                sec = _section_from_pbarl(pid, typ, dims, scale, log)
                model.add_section(sec)
                props[pid] = {"kind": "beam", "mid": _int(_f(card, 2)), "sec": sec.name}
            elif name == "PROD":
                pid = _int(_f(card, 1))
                A = _num(_f(card, 3)) or 0.0
                J = _num(_f(card, 4)) or 0.0
                sec = Section(f"PID {pid}", A=A * scale ** 2, Iy=1e-12, Iz=1e-12,
                              It=(J or 1e-12) * scale ** 4)
                model.add_section(sec)
                props[pid] = {"kind": "truss", "mid": _int(_f(card, 2)), "sec": sec.name}
            elif name == "PSHELL":
                pid = _int(_f(card, 1))
                t = (_num(_f(card, 3)) or 0.0) * scale
                props[pid] = {"kind": "shell", "mid": _int(_f(card, 2)), "t": t}
            elif name in ("PSOLID", "PLSOLID"):
                pid = _int(_f(card, 1))
                props[pid] = {"kind": "solid", "mid": _int(_f(card, 2))}
            elif name in ("CBAR", "CBEAM", "CROD", "CONROD", "CTRIA3", "CQUAD4",
                          "CTETRA", "CHEXA", "CTRIAR", "CQUADR"):
                elem_cards.append(card)
            elif name in ("FORCE", "MOMENT", "PLOAD2", "PLOAD4", "GRAV", "LOAD"):
                load_cards.append(card)
            elif name in ("SPC", "SPC1"):
                spc_cards.append(card)
            elif name in ("TEMP", "TEMPD"):
                unsupported[f"{name} (Temperaturlast ignoriert)"] = \
                    unsupported.get(f"{name} (Temperaturlast ignoriert)", 0) + 1
            elif name in ("PARAM", "SPCADD", "LOADADD", "EIGRL", "EIGR", "NLPARM",
                          "CORD2R", "CORD1R", "CORD2C", "CORD2S", "MAT2", "MAT8"):
                if name.startswith("CORD"):
                    unsupported["CORDxx (Koordinatensysteme nicht unterstuetzt)"] = \
                        unsupported.get("CORDxx (Koordinatensysteme nicht unterstuetzt)", 0) + 1
                elif name in ("MAT2", "MAT8"):
                    unsupported[f"{name} (nur MAT1 unterstuetzt)"] = \
                        unsupported.get(f"{name} (nur MAT1 unterstuetzt)", 0) + 1
            else:
                unsupported[name] = unsupported.get(name, 0) + 1
        except Exception as ex:
            C.warn(log, f"Karte {name} ({', '.join(card[1:4])}): {ex}")
    nodes.flush()

    default_mat = C.ensure_material(model, None, log, quiet=True)

    def mat_for(pid_info: Optional[dict]) -> str:
        if pid_info and pid_info.get("mid") in mats:
            return mats[pid_info["mid"]]
        return default_mat

    # ---- Elemente ------------------------------------------------------------
    for card in elem_cards:
        name = card[0]
        eid = _int(_f(card, 1))
        if eid is None:
            continue
        try:
            if name in ("CBAR", "CBEAM"):
                pid = _int(_f(card, 2))
                ga, gb = _int(_f(card, 3)), _int(_f(card, 4))
                na, nb = grids[ga], grids[gb]
                info = props.get(pid)
                if info is None or info["kind"] != "beam":
                    sec = C.ensure_section(model, None, log)
                    C.warn(log, f"{name} {eid}: Eigenschaft PID {pid} fehlt - {sec} verwendet")
                else:
                    sec = info["sec"]
                roll = 0.0
                x1 = _f(card, 5)
                if x1 and not _f(card, 6) and not _f(card, 7) and _int(x1) is not None \
                        and "." not in x1:
                    g0 = _int(x1)
                    if g0 in grids:
                        v = model.nodes[grids[g0]] - model.nodes[na]
                        roll = C.roll_from_vector(model.nodes[na], model.nodes[nb], v, "y")
                elif x1 or _f(card, 6) or _f(card, 7):
                    v = [_num(_f(card, k)) or 0.0 for k in (5, 6, 7)]
                    roll = C.roll_from_vector(model.nodes[na], model.nodes[nb], v, "y")
                elems[eid] = model.add_element("beam", [na, nb], mat_for(info), sec, roll=roll)
            elif name == "CROD":
                pid = _int(_f(card, 2))
                na, nb = grids[_int(_f(card, 3))], grids[_int(_f(card, 4))]
                info = props.get(pid)
                if info is None:
                    sec = C.ensure_section(model, None, log)
                    C.warn(log, f"CROD {eid}: PROD {pid} fehlt - {sec} verwendet")
                else:
                    sec = info["sec"]
                elems[eid] = model.add_element("truss", [na, nb], mat_for(info), sec)
            elif name == "CONROD":
                na, nb = grids[_int(_f(card, 2))], grids[_int(_f(card, 3))]
                mid = _int(_f(card, 4))
                A = (_num(_f(card, 5)) or 0.0) * scale ** 2
                sec = Section(f"CONROD {eid}", A=A, Iy=1e-12, Iz=1e-12, It=1e-12)
                model.add_section(sec)
                elems[eid] = model.add_element("truss", [na, nb], mats.get(mid, default_mat),
                                               sec.name)
            elif name in ("CTRIA3", "CQUAD4", "CTRIAR", "CQUADR"):
                pid = _int(_f(card, 2))
                nn = 3 if name.startswith("CTRIA") else 4
                ids = [grids[_int(_f(card, 3 + k))] for k in range(nn)]
                info = props.get(pid)
                t = info.get("t") if info else None
                prop = C.ensure_shell_prop(model, f"PID {pid}", t, log)
                elems[eid] = model.add_element("shell3" if nn == 3 else "shell4", ids,
                                               mat_for(info), prop)
            elif name == "CTETRA":
                pid = _int(_f(card, 2))
                gids = [_int(_f(card, 3 + k)) for k in range(10)]
                gids = [g for g in gids if g is not None]
                info = props.get(pid)
                if len(gids) >= 10:
                    ids = [grids[g] for g in gids[:10]]
                    ids = normalize_tet10(ids, model.nodes[ids])
                    elems[eid] = model.add_element("tet10", ids, mat_for(info))
                else:
                    ids = [grids[g] for g in gids[:4]]
                    elems[eid] = model.add_element("tet4", ids, mat_for(info))
            elif name == "CHEXA":
                pid = _int(_f(card, 2))
                gids = [_int(_f(card, 3 + k)) for k in range(8)]
                ids = [grids[g] for g in gids]
                elems[eid] = model.add_element("hex8", ids, mat_for(props.get(pid)))
        except KeyError as ex:
            C.warn(log, f"{name} {eid}: Knoten {ex} unbekannt")
        except Exception as ex:
            C.warn(log, f"{name} {eid}: {ex}")

    # ---- Lager -----------------------------------------------------------
    sup: dict[int, dict[int, float]] = {}
    for gid, ps in grid_ps.items():
        for d in _dofs_from_components(ps):
            sup.setdefault(grids[gid], {})[d] = 0.0
    if default_ps:
        for gid, idx in grids.items():
            if gid not in grid_ps:
                for d in _dofs_from_components(default_ps):
                    sup.setdefault(idx, {})[d] = 0.0
    spc_sids = set()
    for card in spc_cards:
        try:
            sid = _int(_f(card, 1))
            spc_sids.add(sid)
            if card[0] == "SPC":
                k = 2
                while k + 1 < len(card) and _f(card, k):
                    g = _int(_f(card, k))
                    comps = _f(card, k + 1)
                    val = (_num(_f(card, k + 2)) or 0.0)
                    if g in grids:
                        for d in _dofs_from_components(comps):
                            sup.setdefault(grids[g], {})[d] = val * (scale if d < 3 else 1.0)
                    k += 3
            else:  # SPC1
                dofs = _dofs_from_components(_f(card, 2))
                for g in _expand_thru(card[3:]):
                    if g in grids:
                        for d in dofs:
                            sup.setdefault(grids[g], {})[d] = 0.0
        except Exception as ex:
            C.warn(log, f"{card[0]}: {ex}")
    if len(spc_sids) > 1:
        C.say(log, f"SPC-Saetze {sorted(spc_sids)} wurden alle uebernommen "
                   f"(Auswahl per SUBCASE wird nicht ausgewertet)")
    for n, d in sup.items():
        dofs = sorted(d)
        vals = [d[k] for k in dofs]
        model.fix(n, dofs, values=vals if any(vals) else None)

    # ---- Lasten ------------------------------------------------------------
    def case_name(sid: int) -> str:
        nm = f"SID {sid}"
        C.get_or_add_case(model, nm, "G", f"Nastran Lastsatz SID {sid}")
        return nm

    load_combos: list[list[str]] = []
    for card in load_cards:
        name = card[0]
        try:
            sid = _int(_f(card, 1))
            if sid is None:
                continue
            if name in ("FORCE", "MOMENT"):
                g = _int(_f(card, 2))
                cid = _int(_f(card, 3))
                F = _num(_f(card, 4)) or 0.0
                vec = [(_num(_f(card, k)) or 0.0) * F for k in (5, 6, 7)]
                if cid:
                    C.warn(log, f"{name} SID {sid}: CID {cid} wird ignoriert (Basissystem)")
                if g not in grids:
                    C.warn(log, f"{name} SID {sid}: GRID {g} unbekannt")
                    continue
                comp = [0.0] * 6
                off = 0 if name == "FORCE" else 3
                comp[off:off + 3] = vec
                model.load_node(grids[g], *comp, case=case_name(sid))
            elif name == "PLOAD2":
                p = _num(_f(card, 2)) or 0.0
                for e in _expand_thru(card[3:]):
                    if e in elems:
                        model.load_face(elems[e], p, 0, case=case_name(sid))
            elif name == "PLOAD4":
                e1 = _int(_f(card, 2))
                pv = [_num(_f(card, k)) for k in (3, 4, 5, 6)]
                pv = [v for v in pv if v is not None]
                p = sum(pv) / len(pv) if pv else 0.0
                eids = [e1]
                if _f(card, 7).upper() == "THRU":
                    e2 = _int(_f(card, 8))
                    eids = list(range(e1, e2 + 1)) if e2 else [e1]
                    g1 = g34 = None
                else:
                    g1, g34 = _int(_f(card, 7)), _int(_f(card, 8))
                direction = None
                if any(_f(card, k) for k in (10, 11, 12)):
                    direction = [_num(_f(card, k)) or 0.0 for k in (10, 11, 12)]
                for e in eids:
                    if e not in elems:
                        continue
                    el = model.elements[elems[e]]
                    if el.typ.startswith("shell"):
                        model.load_face(elems[e], p, 0, case=case_name(sid), direction=direction)
                    else:
                        face = _solid_face(el, grids.get(g1), grids.get(g34))
                        if face is None:
                            C.warn(log, f"PLOAD4 SID {sid}: Flaeche von Element {e} nicht bestimmbar")
                        else:
                            model.load_face(elems[e], p, face, case=case_name(sid),
                                            direction=direction)
            elif name == "GRAV":
                a = _num(_f(card, 3)) or 0.0
                vec = [(_num(_f(card, k)) or 0.0) * a for k in (4, 5, 6)]
                model.load_cases[case_name(sid)].gravity = vec
            elif name == "LOAD":
                load_combos.append(card)
        except Exception as ex:
            C.warn(log, f"{name}: {ex}")
    for card in load_combos:
        try:
            sid = _int(_f(card, 1))
            s0 = _num(_f(card, 2)) or 1.0
            factors = {}
            k = 3
            while k + 1 < len(card) and _f(card, k):
                si = _num(_f(card, k)) or 0.0
                li = _int(_f(card, k + 1))
                if li is not None:
                    nm = f"SID {li}"
                    if nm not in model.load_cases:
                        C.get_or_add_case(model, nm, "G", f"Nastran Lastsatz SID {li}")
                    factors[nm] = factors.get(nm, 0.0) + s0 * si
                k += 2
            model.add_combination(f"LOAD {sid}", factors, "USER", "Nastran LOAD-Karte")
        except Exception as ex:
            C.warn(log, f"LOAD: {ex}")

    for k, n in sorted(unsupported.items()):
        C.say(log, f"{k}: {n} x nicht unterstuetzt (ignoriert)")
    C.say(log, f"BDF: {model.nn} Knoten, {len(model.elements)} Elemente, "
               f"{len(model.supports)} Lagerknoten, {len(model.load_cases)} Lastfaelle")
    return model


_TET_FACES = [(0, 1, 2), (0, 1, 3), (1, 2, 3), (0, 2, 3)]
_HEX_FACES = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _solid_face(el, n1: Optional[int], n34: Optional[int]) -> Optional[int]:
    """Flaechenindex eines Volumenelements aus PLOAD4 G1/G3(G4):
    Tetraeder: G1 auf der Flaeche, G3 = gegenueberliegende Ecke;
    Hexaeder: G1 und G3 diagonal gegenueber auf der Flaeche."""
    if n1 is None:
        return None
    if el.typ in ("tet4", "tet10"):
        for k, f in enumerate(_TET_FACES):
            fn = [el.nodes[i] for i in f]
            if n1 in fn and (n34 is None or n34 not in fn):
                return k
    elif el.typ == "hex8":
        for k, f in enumerate(_HEX_FACES):
            fn = [el.nodes[i] for i in f]
            if n1 in fn and (n34 is None or n34 in fn):
                return k
    return None
