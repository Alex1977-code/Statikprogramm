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
    if sec.Iy_geo or sec.Iz_geo:
        # Werte im eigenen Bezug des Teils: Winkel in Schenkelrichtung, ein
        # Blechstreifen oder Polygon des freien Editors in dessen y-z, ein
        # schon zusammengesetzter Querschnitt in seinem Bezug - nicht die
        # Hauptwerte, deren Achsen gedreht liegen
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
                          "drehung": d[3], "spiegeln": d[4],
                          # Teile, die nicht aus der Datenbank kommen (Bleche,
                          # Polygone, eigene Profile), reisen mit
                          **({"teil": d[0]} if not profiles.family_of(d[0].name) else {})}
                         for d in data])
    return sec


# --------------------------------------------------------------------------
# Freie Profile: Blechstreifen (Elemente) und Polygone (Flaechen) aus Knoten
# --------------------------------------------------------------------------
def _hauptwerte(Iy, Iz, Iyz):
    m, d2 = (Iy + Iz) / 2.0, math.hypot((Iy - Iz) / 2.0, Iyz)
    alpha = 0.5 * math.atan2(2 * Iyz, Iy - Iz) if abs(Iyz) > 1e-18 * max(Iy, Iz, 1e-18) else 0.0
    return m + d2, m - d2, alpha


def segment(name: str, p1, p2, t: float) -> Section:
    """Ein duennwandiges **Element** des freien Editors: Blechstreifen der
    Dicke t vom Knoten p1 zum Knoten p2 (y, z in m).

    Rechteck L x t mit dem Schwerpunkt in der Mitte. Die Traegheitswerte
    stehen im y-z-Bezug des Editors (``Iy_geo``, ``Iz_geo``, ``Iyz_geo``):
    mit e = Richtung, I_l = t·L³/12 (um die Querachse) und I_q = L·t³/12
    gilt Iy = I_l·e_z² + I_q·e_y², Iz = I_l·e_y² + I_q·e_z²,
    Iyz = (I_l − I_q)·e_y·e_z. Torsion offen: It = L·t³/3.
    """
    y1, z1 = float(p1[0]), float(p1[1])
    y2, z2 = float(p2[0]), float(p2[1])
    L = math.hypot(y2 - y1, z2 - z1)
    if L <= 0 or t <= 0:
        raise ValueError(f"Element {name}: Laenge und Dicke muessen groesser null sein")
    ey, ez = (y2 - y1) / L, (z2 - z1) / L
    A = L * t
    Il, Iq = t * L ** 3 / 12.0, L * t ** 3 / 12.0
    Iy_g = Il * ez ** 2 + Iq * ey ** 2
    Iz_g = Il * ey ** 2 + Iq * ez ** 2
    Iyz = (Il - Iq) * ey * ez
    I1, I2, alpha = _hauptwerte(Iy_g, Iz_g, Iyz)
    zmax = abs(ez) * L / 2 + abs(ey) * t / 2
    ymax = abs(ey) * L / 2 + abs(ez) * t / 2
    return Section(name, A=A, Iy=I1, Iz=I2, It=L * t ** 3 / 3.0,
                   Asy=5.0 / 6.0 * A * ey ** 2, Asz=5.0 / 6.0 * A * ez ** 2,
                   zmax=zmax, ymax=ymax, typ="seg", h=L, b=t, tw=t, tf=t,
                   fabrication="welded",
                   yc=(y1 + y2) / 2.0, zc=(z1 + z2) / 2.0, alpha=alpha,
                   Iy_geo=Iy_g, Iz_geo=Iz_g, Iyz_geo=Iyz,
                   parts=[{"element": [[y1, z1], [y2, z2]], "t": float(t)}])


def _polygon_momente(P):
    """(A, Sy, Sz, Iyy, Izz, Iyz) eines geschlossenen Polygons um den Ursprung
    (Gauss/Green ueber die Kanten): Sy = ∫z dA, Sz = ∫y dA, Iyy = ∫z² dA,
    Izz = ∫y² dA, Iyz = ∫y·z dA. Der Umlaufsinn ist gleichgueltig."""
    P = np.atleast_2d(np.asarray(P, float))
    if len(P) < 3:
        raise ValueError("Ein Polygon braucht mindestens drei Knoten")
    y, z = P[:, 0], P[:, 1]
    y2, z2 = np.roll(y, -1), np.roll(z, -1)
    c = y * z2 - y2 * z
    A = 0.5 * float(c.sum())
    if abs(A) < 1e-30:
        raise ValueError("Polygon ohne Flaeche (Knoten auf einer Geraden?)")
    Sz = float((y + y2) @ c) / 6.0
    Sy = float((z + z2) @ c) / 6.0
    Izz = float((y * y + y * y2 + y2 * y2) @ c) / 12.0
    Iyy = float((z * z + z * z2 + z2 * z2) @ c) / 12.0
    Iyz = float((y * z2 + 2 * y * z + 2 * y2 * z2 + y2 * z) @ c) / 24.0
    if A < 0:
        A, Sy, Sz, Iyy, Izz, Iyz = -A, -Sy, -Sz, -Iyy, -Izz, -Iyz
    return A, Sy, Sz, Iyy, Izz, Iyz


def _torsion_naeherung(A, Sy, Sz, Iyy, Izz) -> float:
    """Saint-Venant: It ≈ A⁴ / (4π²·Ip) mit Ip um den eigenen Schwerpunkt -
    exakt fuer den Kreis, fuer ein Quadrat 8 % zu hoch."""
    Ip = (Iyy - Sy ** 2 / A) + (Izz - Sz ** 2 / A)
    return A ** 4 / (4.0 * math.pi ** 2 * Ip) if Ip > 0 else 0.0


def im_polygon(punkt, P) -> bool:
    """Liegt der Punkt (y, z) im Polygon? (Strahl nach +y)"""
    y, z = float(punkt[0]), float(punkt[1])
    P = np.atleast_2d(np.asarray(P, float))
    drin = False
    n = len(P)
    for i in range(n):
        y1, z1 = P[i]
        y2, z2 = P[(i + 1) % n]
        if (z1 > z) != (z2 > z):
            ys = y1 + (z - z1) * (y2 - y1) / (z2 - z1)
            if ys > y:
                drin = not drin
    return drin


def polygon(name: str, points, holes=()) -> Section:
    """Eine **Flaeche** des freien Editors: Vollquerschnitt aus einem
    geschlossenen Polygon (y, z in m), wahlweise mit Loechern.

    Flaeche, Schwerpunkt und Traegheitsmomente sind exakt (Green ueber die
    Kanten). Fuer die Torsion gibt es beim Polygon keine geschlossene Loesung;
    genommen wird die Naeherung nach Saint-Venant It ≈ A⁴/(4π²·Ip), mit
    Loechern als Differenz von Aussen- und Lochwert - das trifft fuer den
    duennen Ring den Bredtschen Wert. Wer It genauer kennt, traegt ihn in der
    Tabelle „Querschnitte" ein.
    """
    A, Sy, Sz, Iyy, Izz, Iyz = _polygon_momente(points)
    It = _torsion_naeherung(A, Sy, Sz, Iyy, Izz)
    for H in holes:
        Ah, Syh, Szh, Iyyh, Izzh, Iyzh = _polygon_momente(H)
        It -= _torsion_naeherung(Ah, Syh, Szh, Iyyh, Izzh)
        A, Sy, Sz = A - Ah, Sy - Syh, Sz - Szh
        Iyy, Izz, Iyz = Iyy - Iyyh, Izz - Izzh, Iyz - Iyzh
    if A <= 0:
        raise ValueError(f"Flaeche {name}: die Loecher sind groesser als die Flaeche")
    yc, zc = Sz / A, Sy / A
    Iy_g, Iz_g, Iyz_c = Iyy - A * zc ** 2, Izz - A * yc ** 2, Iyz - A * yc * zc
    I1, I2, alpha = _hauptwerte(Iy_g, Iz_g, Iyz_c)
    P = np.atleast_2d(np.asarray(points, float))
    zmax = float(np.max(np.abs(P[:, 1] - zc)))
    ymax = float(np.max(np.abs(P[:, 0] - yc)))
    return Section(name, A=A, Iy=I1, Iz=I2, It=max(It, 0.0),
                   Asy=5.0 / 6.0 * A, Asz=5.0 / 6.0 * A, zmax=zmax, ymax=ymax,
                   typ="poly", h=float(np.ptp(P[:, 1])), b=float(np.ptp(P[:, 0])),
                   fabrication="welded",
                   yc=yc, zc=zc, alpha=alpha, Iy_geo=Iy_g, Iz_geo=Iz_g, Iyz_geo=Iyz_c,
                   parts=[{"polygon": P.tolist(),
                           "loecher": [np.asarray(H, float).tolist() for H in holes]}])


def _teil(profil, nachschlagen=None) -> Section:
    """Ein Teil des Editors: Section, Name im Modell oder Profilbezeichnung."""
    if isinstance(profil, Section):
        return profil
    if isinstance(profil, dict):
        felder = {f.name for f in Section.__dataclass_fields__.values()}
        return Section(**{k: v for k, v in profil.items() if k in felder})
    name = str(profil)
    if nachschlagen is not None:
        s = nachschlagen(name) if callable(nachschlagen) else nachschlagen.get(name)
        if s is not None:
            return s
    return profiles.make_section(name)


def build_free(name: str, teile=(), knoten=None, elemente=(), flaechen=(),
               nachschlagen=None) -> Section:
    """Ein **frei zusammengesetztes Profil** des Editors.

    * ``teile``: Standardprofile oder Querschnitte des Modells mit Lage -
      (profil, dy, dz[, drehung[, spiegeln]]) oder dict mit diesen Schluesseln;
      dy, dz ist die Lage des Teilschwerpunkts [m].
    * ``knoten``: {Nr: (y, z)} [m].
    * ``elemente``: (von, bis, t) - Blechstreifen zwischen zwei Knoten.
    * ``flaechen``: ({"knoten": [Nr …], "loch": False}) - Polygone; ein Loch
      wird von der Flaeche abgezogen, in der es liegt.

    Alles wird nach dem Satz von Steiner vereinigt (``build``); das Ergebnis
    traegt in ``parts`` den Editorinhalt, damit es sich wieder oeffnen laesst.
    """
    kn = {int(k): (float(v[0]), float(v[1])) for k, v in (knoten or {}).items()}
    parts, editor_teile = [], []
    for t in teile:
        if isinstance(t, dict):
            profil = t.get("profil")
            dy, dz = float(t.get("dy", 0.0)), float(t.get("dz", 0.0))
            rot, mir = float(t.get("drehung", 0.0)), bool(t.get("spiegeln", False))
        else:
            profil = t[0]
            dy = float(t[1]) if len(t) > 1 else 0.0
            dz = float(t[2]) if len(t) > 2 else 0.0
            rot = float(t[3]) if len(t) > 3 else 0.0
            mir = bool(t[4]) if len(t) > 4 else False
        base = _teil(profil, nachschlagen)
        parts.append((base, dy, dz, rot, mir))
        editor_teile.append({"profil": base.name, "dy": dy, "dz": dz,
                             "drehung": rot, "spiegeln": mir})
    editor_elemente = []
    for e in elemente:
        a, b, t = int(e[0]), int(e[1]), float(e[2])
        if a not in kn or b not in kn:
            raise ValueError(f"Element {a}-{b}: Knoten unbekannt")
        s = segment(f"E{a}-{b}", kn[a], kn[b], t)
        parts.append((s, s.yc, s.zc, 0.0, False))
        editor_elemente.append([a, b, t])
    aussen, loecher, editor_flaechen = [], [], []
    for f in flaechen:
        nrn = [int(i) for i in (f.get("knoten", []) if isinstance(f, dict) else f[0])]
        loch = bool(f.get("loch", False)) if isinstance(f, dict) else (len(f) > 1 and f[1])
        fehlt = [i for i in nrn if i not in kn]
        if fehlt:
            raise ValueError(f"Flaeche: Knoten {fehlt} unbekannt")
        (loecher if loch else aussen).append([kn[i] for i in nrn])
        editor_flaechen.append({"knoten": nrn, "loch": loch})
    for k, P in enumerate(aussen):
        hs = [H for H in loecher if im_polygon(H[0], P)]
        s = polygon(f"F{k + 1}", P, hs)
        parts.append((s, s.yc, s.zc, 0.0, False))
    if not parts:
        raise ValueError("Nichts angegeben: Teil, Element oder Flaeche fehlt")
    if loecher and not aussen:
        raise ValueError("Ein Loch braucht eine Flaeche, in der es liegt")
    sec = build(name, parts)
    sec.parts.append({"editor": {"teile": editor_teile, "knoten": {k: list(v) for k, v in kn.items()},
                                 "elemente": editor_elemente, "flaechen": editor_flaechen}})
    return sec


def editor_inhalt(sec: Section):
    """Der Editorinhalt eines freien Profils - oder None."""
    for p in getattr(sec, "parts", None) or []:
        if isinstance(p, dict) and "editor" in p:
            return p["editor"]
    return None


# --------------------------------------------------------------------------
# Umriss zum Zeichnen
# --------------------------------------------------------------------------
def _kreis(r: float, n: int = 48) -> np.ndarray:
    w = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([r * np.cos(w), r * np.sin(w)])


def umriss(sec: Section, nachschlagen=None) -> list:
    """Der Umriss eines Querschnitts zum Zeichnen: [(Polygon (y, z), ist_loch)],
    im eigenen Bezug mit dem **Schwerpunkt im Ursprung**. Ausrundungen bleiben
    weg; fuer zusammengesetzte Querschnitte kommen die Teile mit Versatz,
    Drehung und Spiegelung."""
    h, b, tw, tf = sec.h, sec.b, sec.tw, sec.tf
    typ = sec.typ
    out = []
    if typ == "I":
        out.append((np.array([(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, -h / 2 + tf),
                              (tw / 2, -h / 2 + tf), (tw / 2, h / 2 - tf), (b / 2, h / 2 - tf),
                              (b / 2, h / 2), (-b / 2, h / 2), (-b / 2, h / 2 - tf),
                              (-tw / 2, h / 2 - tf), (-tw / 2, -h / 2 + tf),
                              (-b / 2, -h / 2 + tf)]), False))
    elif typ == "T":
        zc = sec.zc
        out.append((np.array([(-b / 2, zc), (b / 2, zc), (b / 2, zc - tf), (tw / 2, zc - tf),
                              (tw / 2, zc - h), (-tw / 2, zc - h), (-tw / 2, zc - tf),
                              (-b / 2, zc - tf)]), False))
    elif typ == "U":
        yc = sec.yc
        out.append((np.array([(-yc, -h / 2), (b - yc, -h / 2), (b - yc, -h / 2 + tf),
                              (tw - yc, -h / 2 + tf), (tw - yc, h / 2 - tf), (b - yc, h / 2 - tf),
                              (b - yc, h / 2), (-yc, h / 2)]), False))
    elif typ == "L":
        yc, zc, t = sec.yc, sec.zc, tw
        out.append((np.array([(-yc, -zc), (b - yc, -zc), (b - yc, t - zc), (t - yc, t - zc),
                              (t - yc, h - zc), (-yc, h - zc)]), False))
    elif typ == "RHS":
        out.append((np.array([(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]), False))
        if 0 < tw < min(b, h) / 2:
            bi, hi = b - 2 * tw, h - 2 * tw
            out.append((np.array([(-bi / 2, -hi / 2), (bi / 2, -hi / 2), (bi / 2, hi / 2),
                                  (-bi / 2, hi / 2)]), True))
    elif typ == "CHS":
        out.append((_kreis(h / 2), False))
        if 0 < tw < h / 2:
            out.append((_kreis(h / 2 - tw), True))
    elif typ == "rect":
        out.append((np.array([(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]), False))
    elif typ == "circle":
        out.append((_kreis(h / 2), False))
    elif typ == "seg" and sec.parts:
        (y1, z1), (y2, z2) = sec.parts[0]["element"]
        t = sec.parts[0]["t"]
        my, mz = (y1 + y2) / 2, (z1 + z2) / 2
        L = math.hypot(y2 - y1, z2 - z1) or 1.0
        ny, nz = -(z2 - z1) / L * t / 2, (y2 - y1) / L * t / 2
        out.append((np.array([(y1 - my + ny, z1 - mz + nz), (y2 - my + ny, z2 - mz + nz),
                              (y2 - my - ny, z2 - mz - nz), (y1 - my - ny, z1 - mz - nz)]), False))
    elif typ == "poly" and sec.parts:
        P = np.asarray(sec.parts[0]["polygon"], float) - [sec.yc, sec.zc]
        out.append((P, False))
        for H in sec.parts[0].get("loecher", []):
            out.append((np.asarray(H, float) - [sec.yc, sec.zc], True))
    elif typ == "composite":
        for p in sec.parts:
            if not isinstance(p, dict) or "profil" not in p:
                continue
            try:
                base = _teil(p.get("teil") or p["profil"], nachschlagen)
            except Exception:                    # noqa: BLE001
                continue
            a = math.radians(float(p.get("drehung", 0.0)))
            c, s = math.cos(a), math.sin(a)
            for P, loch in umriss(base, nachschlagen):
                Q = np.asarray(P, float).copy()
                if p.get("spiegeln"):
                    Q[:, 0] = -Q[:, 0]
                Q = np.column_stack([c * Q[:, 0] - s * Q[:, 1], s * Q[:, 0] + c * Q[:, 1]])
                Q += [float(p.get("dy", 0.0)) - sec.yc, float(p.get("dz", 0.0)) - sec.zc]
                out.append((Q, loch))
    else:
        # frei (nur Steifigkeiten): ein Rechteck gleicher Flaeche und Hoehe
        hh = 2 * sec.zmax if sec.zmax > 0 else math.sqrt(max(sec.A, 1e-12))
        bb = sec.A / hh if hh > 0 else hh
        out.append((np.array([(-bb / 2, -hh / 2), (bb / 2, -hh / 2), (bb / 2, hh / 2), (-bb / 2, hh / 2)]), False))
    return out


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
        if not isinstance(p, dict) or "profil" not in p:
            continue
        lines.append(f"  {p['profil']:20s} dy = {p['dy'] * 1000:+7.1f} mm  "
                     f"dz = {p['dz'] * 1000:+7.1f} mm"
                     + (f"  gedreht {p['drehung']:g}°" if p["drehung"] else "")
                     + ("  gespiegelt" if p["spiegeln"] else ""))
    return "\n".join(lines)
