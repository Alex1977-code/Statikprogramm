"""
Zusammengesetzte Querschnitte.

Mehrere Grundquerschnitte (Profile aus der Datenbank oder eigene) werden mit
Versatz, Drehung und Spiegelung zu einem Querschnitt vereinigt. Die Werte
folgen dem Satz von Steiner; bei unsymmetrischen Anordnungen werden die
Hauptträgheitsmomente und der Hauptachsenwinkel ausgewiesen.

    from statik3d.sections import build, double_angle, double_channel, plated_i
    s = double_angle("2L 100x100x10", "L 100x100x10", gap=0.010)
    s = build("Kastentraeger", [("UPE 300", 0, +0.150), ("UPE 300", 0, -0.150, 180)])

Versatz: dy in lokaler y-Richtung (schwache Achse), dz in lokaler z-Richtung
(starke Achse), beide vom Schwerpunkt des Gesamtquerschnitts unabhaengig -
er wird berechnet. Drehung 'rot' in Grad um die Stabachse, 'mirror' spiegelt
den Teilquerschnitt an seiner z-Achse (fuer Winkel und U-Profile Ruecken an
Ruecken).

Grenzen: It und Iw werden als Summe der Teilquerschnitte angesetzt (offene
Profile ohne Verbund; bei geschlossenen Kaesten liegt It damit auf der
sicheren Seite). Wpl ist eine Naeherung. Die Querschnittsklasse wird fuer
zusammengesetzte Querschnitte nicht bestimmt - die Nachweise laufen elastisch.
"""
from __future__ import annotations

import math
from typing import Union

import numpy as np

from .model import Section
from . import profiles

PartSpec = Union[str, Section, tuple, list]


def _as_section(base) -> Section:
    if isinstance(base, Section):
        return base
    return profiles.make_section(str(base))


def _rotated(sec: Section, rot_deg: float, mirror: bool):
    """(A, Iy, Iz, Iyz, zmax, ymax, It, Iw) des gedrehten Teilquerschnitts."""
    Iy, Iz = sec.Iy, sec.Iz
    Iyz = 0.0
    if sec.typ == "L" and sec.Iy_geo:
        # Winkel: Katalogwerte liegen in Schenkelrichtung
        Iy, Iz, Iyz = sec.Iy_geo, sec.Iz_geo, sec.Iyz_geo
    if mirror:
        Iyz = -Iyz
    a = math.radians(rot_deg)
    c, s = math.cos(a), math.sin(a)
    R = np.array([[c, -s], [s, c]])
    I = R.T @ np.array([[Iy, Iyz], [Iyz, Iz]]) @ R
    zmax, ymax = sec.zmax or 0.0, sec.ymax or 0.0
    zr = abs(zmax * c) + abs(ymax * s)
    yr = abs(ymax * c) + abs(zmax * s)
    return sec.A, float(I[0, 0]), float(I[1, 1]), float(I[0, 1]), zr, yr, sec.It, sec.Iw


def build(name: str, parts: list, fabrication: str = "welded") -> Section:
    """Zusammengesetzter Querschnitt aus Teilen
    (Profil, dy, dz[, Drehung in Grad[, spiegeln]])."""
    if not parts:
        raise ValueError("Keine Teilquerschnitte angegeben")
    data = []
    for pt in parts:
        if isinstance(pt, (str, Section)):
            pt = (pt, 0.0, 0.0)
        base = _as_section(pt[0])
        dy = float(pt[1]) if len(pt) > 1 else 0.0
        dz = float(pt[2]) if len(pt) > 2 else 0.0
        rot = float(pt[3]) if len(pt) > 3 else 0.0
        mir = bool(pt[4]) if len(pt) > 4 else False
        data.append((base, dy, dz, rot, mir) + _rotated(base, rot, mir))
    A = sum(d[5] for d in data)
    yc = sum(d[5] * d[1] for d in data) / A
    zc = sum(d[5] * d[2] for d in data) / A
    Iy = Iz = Iyz = It = Iw = 0.0
    zmax = ymax = 0.0
    for base, dy, dz, rot, mir, a, iy, iz, iyz, zr, yr, it, iw in data:
        ey, ez = dy - yc, dz - zc
        Iy += iy + a * ez ** 2
        Iz += iz + a * ey ** 2
        Iyz += iyz + a * ey * ez
        It += it
        Iw += iw + iz * ez ** 2
        zmax = max(zmax, abs(ez) + zr)
        ymax = max(ymax, abs(ey) + yr)
    m, d2 = (Iy + Iz) / 2.0, math.hypot((Iy - Iz) / 2.0, Iyz)
    I1, I2 = m + d2, m - d2
    alpha = 0.5 * math.atan2(2 * Iyz, Iy - Iz) if abs(Iyz) > 1e-18 * max(Iy, 1e-18) else 0.0
    Wpl_y = sum(d[0].Wpl_y + d[0].A * abs(d[2] - zc) for d in data)
    Wpl_z = sum(d[0].Wpl_z + d[0].A * abs(d[1] - yc) for d in data)
    sec = Section(name, A=A, Iy=I1, Iz=I2, It=It,
                  Asy=sum(d[0].Asy for d in data), Asz=sum(d[0].Asz for d in data),
                  zmax=zmax, ymax=ymax, typ="composite",
                  h=2 * zmax, b=2 * ymax, Iw=Iw,
                  Wel_y=I1 / zmax if zmax else 0.0, Wel_z=I2 / ymax if ymax else 0.0,
                  Wpl_y=Wpl_y, Wpl_z=Wpl_z, fabrication=fabrication,
                  yc=yc, zc=zc, alpha=alpha, Iy_geo=Iy, Iz_geo=Iz, Iyz_geo=Iyz,
                  parts=[{"profil": d[0].name, "dy": d[1], "dz": d[2],
                          "drehung": d[3], "spiegeln": d[4]} for d in data])
    return sec


# --------------------------------------------------------------------------
# Haeufige Bauformen
# --------------------------------------------------------------------------
def double_angle(name: str, angle: str, gap: float = 0.010, back: str = "long") -> Section:
    """Zwei Winkel Ruecken an Ruecken mit Futterblechabstand 'gap'.
    back='long': die langen Schenkel liegen aneinander (Kreuzquerschnitt liegend)."""
    a = _as_section(angle)
    off = gap / 2.0 + (a.yc if back == "long" else a.zc)
    return build(name, [(a, -off, 0.0, 0.0, True), (a, +off, 0.0, 0.0, False)])


def double_channel(name: str, channel: str, gap: float = 0.0, back_to_back: bool = True) -> Section:
    """Zwei U-Profile: back_to_back=True Ruecken an Ruecken (Stege aussen),
    sonst Stege innen (Kastenquerschnitt) mit lichtem Abstand 'gap'."""
    c = _as_section(channel)
    off = gap / 2.0 + c.yc
    if back_to_back:
        return build(name, [(c, -off, 0.0, 0.0, True), (c, +off, 0.0, 0.0, False)])
    return build(name, [(c, -off, 0.0, 180.0, False), (c, +off, 0.0, 0.0, False)])


def plated_i(name: str, profile: str, plate_b: float, plate_t: float) -> Section:
    """I-Profil mit aufgeschweissten Gurtplatten oben und unten."""
    base = _as_section(profile)
    pl = Section.rectangle("Blech", plate_b, plate_t)
    dz = base.h / 2.0 + plate_t / 2.0
    return build(name, [(base, 0.0, 0.0), (pl, 0.0, +dz), (pl, 0.0, -dz)])


def box_from_plates(name: str, h: float, b: float, tw: float, tf: float) -> Section:
    """Geschweisster Kastenquerschnitt aus vier Blechen (Aussenmasse h x b)."""
    web = Section.rectangle("Steg", tw, h - 2 * tf)
    fl = Section.rectangle("Gurt", b, tf)
    return build(name, [(web, -(b - tw) / 2, 0.0), (web, +(b - tw) / 2, 0.0),
                        (fl, 0.0, +(h - tf) / 2), (fl, 0.0, -(h - tf) / 2)])


def describe(sec: Section) -> str:
    """Mehrzeilige Beschreibung eines zusammengesetzten Querschnitts."""
    lines = [f"{sec.name}: A = {sec.A * 1e4:.2f} cm², Iy = {sec.Iy * 1e8:.0f} cm⁴, "
             f"Iz = {sec.Iz * 1e8:.0f} cm⁴, It = {sec.It * 1e8:.1f} cm⁴"]
    if abs(sec.alpha) > 1e-6:
        lines.append(f"  Hauptachsen um {math.degrees(sec.alpha):+.2f}° gedreht "
                     f"(Stab mit roll = {sec.alpha:.4f} rad einbauen)")
    for p in sec.parts:
        lines.append(f"  {p['profil']:20s} dy = {p['dy'] * 1000:+7.1f} mm  "
                     f"dz = {p['dz'] * 1000:+7.1f} mm"
                     + (f"  gedreht {p['drehung']:g}°" if p["drehung"] else "")
                     + ("  gespiegelt" if p["spiegeln"] else ""))
    return "\n".join(lines)
