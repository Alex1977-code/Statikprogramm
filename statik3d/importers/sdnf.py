"""
SDNF - Steel Detailing Neutral Format (.sdnf, .sdn).

Textformat fuer Stahlbaumodelle, geschrieben von HiCAD, Tekla Structures,
SDS/2, Advance Steel und StruCad. Anders als DSTV-NC traegt SDNF die **Lage im
Bauwerk**: jedes Bauteil steht mit seinen beiden Endpunkten in globalen
Koordinaten, dazu Profil, Werkstoff und Drehung.

Aufbau:

    Packet 00        Kopf (Programm, Version, Projekt, Einheiten)
    Packet 10        lineare Bauteile (Traeger, Stuetzen, Streben)
    Packet 20        Bleche (vier Eckpunkte und Dicke)
    Packet 21/22     Platten, Verbindungsbleche
    Packet 30/40/50  Schrauben, Schweissnaehte, Sonstiges
    Packet 99        Ende

Jedes Paket beginnt mit der Anzahl seiner Saetze; die Saetze haben innerhalb
einer Datei gleich viele Zeilen. Genau daran wird der Satzaufbau bestimmt
(Zeilenzahl = Zeilen des Pakets / Anzahl) - unabhaengig davon, welche
SDNF-Fassung das schreibende Programm verwendet. In einem Satz sind die
Zeichenketten in Anfuehrungszeichen die Bezeichner (Bauteilnummer, Profil,
Werkstoff), die sechs zusammenhaengenden Zahlen die beiden Endpunkte.

    from statik3d.importers.sdnf import import_sdnf, packets
    m = import_sdnf("bauwerk.sdnf", log=msgs)
"""
from __future__ import annotations

import os
import re

from ..model import Model
from . import _common as C

SDNF_EXT = (".sdnf", ".sdn")

#: Laengeneinheit -> Meter. SDNF schreibt die Einheit in Paket 00.
UNITS = {"1": 0.001, "2": 0.0254, "mm": 0.001, "inch": 0.0254, "in": 0.0254,
         "m": 1.0, "cm": 0.01, "ft": 0.3048}

_TOKEN = re.compile(r'"([^"]*)"|([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|(\S+)')


def tokens(line: str) -> list:
    """Zeile in Zeichenketten (in Anfuehrungszeichen) und Zahlen zerlegen."""
    out = []
    for q, num, word in _TOKEN.findall(line):
        if q or (not num and not word):
            out.append(("s", q))
        elif num:
            out.append(("n", float(num)))
        else:
            out.append(("s", word))
    return out


def _lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def packets(text: str) -> dict:
    """{Paketnummer: [Zeilen]} einer SDNF-Datei."""
    out: dict[str, list[str]] = {}
    key = None
    for line in _lines(text):
        m = re.match(r"(?i)^packet\s+(\d+)", line)
        if m:
            key = m.group(1).zfill(2)
            out.setdefault(key, [])
            continue
        if key is not None:
            out[key].append(line)
    return out


def is_sdnf(text: str) -> bool:
    return bool(re.search(r"(?im)^\s*packet\s+00\b", text[:4000]))


def records(body: list[str]) -> list[list[str]]:
    """Paketinhalt in Saetze zerlegen.

    Die erste Zeile nennt die Anzahl der Saetze. Ist die Zeilenzahl durch sie
    teilbar, hat jeder Satz gleich viele Zeilen - so steht der Satzaufbau fest,
    ohne die Feldreihenfolge einer bestimmten SDNF-Fassung zu unterstellen.
    """
    if not body:
        return []
    head = tokens(body[0])
    if len(head) == 1 and head[0][0] == "n" and float(head[0][1]).is_integer():
        n = int(head[0][1])
        rest = body[1:]
        if n <= 0:
            return []
        if len(rest) % n == 0:
            step = len(rest) // n
            return [rest[i * step:(i + 1) * step] for i in range(n)]
        # Zeilenzahl passt nicht: Saetze an der Bauteilnummer trennen
        groups, cur = [], []
        for line in rest:
            tk = tokens(line)
            if cur and tk and tk[0][0] == "s" and len(groups) < n:
                groups.append(cur)
                cur = []
            cur.append(line)
        if cur:
            groups.append(cur)
        return groups
    return [body]


def record_values(rec: list[str]) -> tuple[list[str], list[float]]:
    """(Zeichenketten, Zahlen) eines Satzes in Lesereihenfolge."""
    strings: list[str] = []
    numbers: list[float] = []
    for line in rec:
        for kind, val in tokens(line):
            (strings if kind == "s" else numbers).append(val)
    return strings, numbers


def number_run(rec: list[str], need: int) -> list[float]:
    """Laengste ununterbrochene Folge von Zahlen im Satz (mindestens ``need``).

    Ein SDNF-Satz beginnt mit Kennungen und Schluesselzahlen (Bauteilart,
    Status, Klasse); die Geometrie folgt als geschlossener Block von Zahlen.
    Statt eine feste Feldreihenfolge zu unterstellen, wird dieser Block
    gesucht - er ist der laengste Zahlenblock des Satzes.
    """
    best: list[float] = []
    cur: list[float] = []
    for line in rec:
        for kind, val in tokens(line):
            if kind == "n":
                cur.append(val)
            else:
                if len(cur) > len(best):
                    best = cur
                cur = []
    if len(cur) > len(best):
        best = cur
    return best if len(best) >= need else []


def _unit_scale(head: list[str], log: list = None) -> float:
    """Laengeneinheit aus Paket 00 (Voreinstellung mm)."""
    for line in head:
        for kind, val in tokens(line):
            if kind == "s" and str(val).strip().lower() in ("mm", "m", "cm", "inch", "in", "ft"):
                f = UNITS[str(val).strip().lower()]
                C.say(log, f"Laengeneinheit aus Paket 00: {val}")
                return f
    for line in head:
        if line.strip() in ("1", "2"):
            f = UNITS[line.strip()]
            C.say(log, f"Einheitenkennzahl {line.strip()} -> "
                       + ("Millimeter" if f == 0.001 else "Zoll"))
            return f
    C.say(log, "Keine Einheit in Paket 00 - Millimeter angenommen")
    return 0.001


def import_sdnf(path: str, model: Model = None, log: list = None,
                unit_scale: float = None, **_) -> Model:
    """SDNF-Datei einlesen: lineare Bauteile (Paket 10) und Bleche (Paket 20)."""
    with open(path, "r", encoding="latin-1", errors="ignore") as f:
        text = f.read()
    if not is_sdnf(text):
        raise ImportError(f"{os.path.basename(path)}: kein SDNF - der Kopf "
                          "'Packet 00' fehlt.")
    m = model or Model(os.path.splitext(os.path.basename(path))[0])
    pk = packets(text)
    C.say(log, "SDNF-Datei, Pakete: " + ", ".join(sorted(pk)))
    scale = unit_scale if unit_scale else _unit_scale(pk.get("00", []), log)
    idx = C.NodeIndex(m)
    n_mem = _members(pk.get("10", []), m, idx, scale, log)
    n_plate = 0
    for key in ("20", "21", "22"):
        n_plate += _plates(pk.get(key, []), m, idx, scale, log, key)
    idx.flush()
    for key, body in sorted(pk.items()):
        if key not in ("00", "10", "20", "21", "22", "99") and body:
            C.say(log, f"  Paket {key}: {len(records(body))} Saetze - "
                       "nicht uebernommen (Schrauben, Naehte, Zusatzangaben).")
    C.say(log, f"SDNF: {n_mem} Bauteile, {n_plate} Bleche uebernommen")
    if not n_mem and not n_plate:
        raise ImportError(f"{os.path.basename(path)}: SDNF erkannt, aber weder "
                          "Bauteile (Paket 10) noch Bleche (Paket 20) lesbar.")
    return m


def _members(body: list[str], m: Model, idx, scale: float, log: list) -> int:
    n = 0
    for rec in records(body):
        strings, _all = record_values(rec)
        numbers = number_run(rec, 6)
        if not numbers:
            continue
        p1 = [v * scale for v in numbers[:3]]
        p2 = [v * scale for v in numbers[3:6]]
        if all(abs(a - b) < 1e-12 for a, b in zip(p1, p2)):
            continue
        # SDNF fuehrt die Bauteilnummer als erste Zeichenkette des Satzes
        name = (strings[0].strip() if strings and strings[0].strip()
                else _first_text(strings)) or f"B{n + 1}"
        secname = _section_name(strings)
        matname = _material_name(strings)
        sec = C.ensure_section(m, secname, log)
        mat = C.ensure_material(m, matname, log, quiet=True)
        a = idx.add(*p1)
        b = idx.add(*p2)
        roll = 0.0
        if len(numbers) > 6:
            roll = numbers[6] * 3.141592653589793 / 180.0
        e = m.add_element("beam", [a, b], mat, sec, roll=roll)
        m.add_member(C.unique_name(m.members, name), [e])
        n += 1
    if n:
        C.say(log, f"  Paket 10: {n} lineare Bauteile")
    return n


def _plates(body: list[str], m: Model, idx, scale: float, log: list, key: str) -> int:
    n = 0
    for rec in records(body):
        strings, _all = record_values(rec)
        numbers = number_run(rec, 12)
        if not numbers:
            continue
        pts = [[v * scale for v in numbers[i:i + 3]] for i in range(0, 12, 3)]
        t = None
        for v in numbers[12:]:
            if 0.0 < v * scale < 0.5:
                t = v * scale
                break
        prop = C.ensure_shell_prop(m, f"t{(t or 0.010) * 1e3:g}", t or 0.010, log)
        mat = C.ensure_material(m, _material_name(strings), log, quiet=True)
        nodes = [idx.add(*p) for p in pts]
        idx.flush()
        if C.polygon_to_shells(m, nodes, mat, prop):
            n += 1
    if n:
        C.say(log, f"  Paket {key}: {n} Bleche")
    return n


def _first_text(strings: list[str]) -> str:
    for s in strings:
        s = s.strip()
        if s and not s.replace(".", "").replace("-", "").isdigit():
            return s
    return ""


def _section_name(strings: list[str]) -> str:
    """Profilbezeichnung: die Zeichenkette, die die Profildatenbank kennt."""
    for s in strings:
        if C.section_from_designation(s.strip()) is not None:
            return s.strip()
    for s in strings[1:]:
        t = s.strip()
        if t and re.search(r"\d", t) and not C.steel_grade_from_text(t):
            return t
    return ""


def _material_name(strings: list[str]) -> str:
    for s in strings:
        if C.steel_grade_from_text(s.strip()):
            return s.strip()
    return ""
