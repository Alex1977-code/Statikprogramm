"""Skizzen: Linien, Boegen, Kreise, Bemassungen und Text auf einem Blatt
(16.09.2026, "wie in einem rudimentaeren CAD-Programm ... analog InfoCAD").

Eine Skizze ist ein Woerterbuch, das mit dem Modell gespeichert wird:

    {"breite": 297.0, "hoehe": 210.0,      # Blatt in mm, y nach unten wie im Bild
     "massstab": 1.0,                      # 1 mm auf dem Blatt = massstab mm am Bauteil
     "einheit": "mm",                      # Einheit der Masszahlen: mm, cm oder m
     "raster": 5.0,                        # Rasterschritt in mm (0 = ohne)
     "bild": {"x": 0, "y": 0, "breite": 297, "hoehe": 210},   # Lage eines Hintergrundbilds
     "elemente": [ {"art": "linie", "p1": [x, y], "p2": [x, y]},
                   {"art": "kreis", "mitte": [x, y], "r": r},
                   {"art": "bogen", "mitte": [x, y], "r": r, "von": grad, "bis": grad},
                   {"art": "bemassung", "p1": [x, y], "p2": [x, y], "abstand": mm, "text": ""},
                   {"art": "text", "p": [x, y], "text": "...", "groesse": 3.5} ]}

Winkel zaehlen in Grad gegen den Uhrzeigersinn, so wie man sie auf dem Blatt
sieht (die Blattachse y zeigt nach unten, darum steht in den Formeln
``-sin``). Ein Bogen laeuft von ``von`` nach ``bis`` gegen den Uhrzeigersinn.

Das Hintergrundbild (uebernommene Modelldarstellung, eingefuegtes Bild) liegt
als PNG in ``Unterlage.daten``; hier steht nur sein Rahmen. Alles Rechnen
(Fang, Treffer, Masstext, SVG) liegt in diesem Modul ohne Qt, damit es sich
ohne Oberflaeche pruefen laesst; das Zeichenfenster (gui/skizze.py) ruft es.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

#: Strichstaerken [mm] wie in einer Bauzeichnung: Linien mittel, Masse duenn
STRICH = {"linie": 0.35, "kreis": 0.35, "bogen": 0.35, "bemassung": 0.18, "text": 0.0}
#: Faktor Blatt-mm -> Anzeige-mm je Einheit der Masszahl
EINHEITEN = {"mm": 1.0, "cm": 0.1, "m": 0.001}
#: Pfeillaenge der Bemassung [mm] und Ueberstand der Masshilfslinien [mm]
PFEIL = 2.5
UEBERSTAND = 1.5
#: Schrifthoehe der Masszahl [mm]
MASSSCHRIFT = 3.0


def neu(breite: float = 297.0, hoehe: float = 210.0, massstab: float = 1.0,
        einheit: str = "mm", raster: float = 5.0) -> dict:
    """Ein leeres Blatt (Vorgabe A4 quer)."""
    return {"breite": float(breite), "hoehe": float(hoehe), "massstab": float(massstab),
            "einheit": einheit if einheit in EINHEITEN else "mm", "raster": float(raster),
            "bild": None, "elemente": []}


def pruefen(skizze) -> dict:
    """Fehlendes ergaenzen (aeltere Dateien, halbe Woerterbuecher)."""
    s = dict(neu())
    s.update({k: v for k, v in (skizze or {}).items() if v is not None or k == "bild"})
    s["elemente"] = [dict(e) for e in (s.get("elemente") or []) if isinstance(e, dict) and e.get("art")]
    if s.get("einheit") not in EINHEITEN:
        s["einheit"] = "mm"
    return s


# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------
def abstand(a, b) -> float:
    return math.hypot(float(b[0]) - float(a[0]), float(b[1]) - float(a[1]))


def winkel(mitte, p) -> float:
    """Winkel [Grad, 0..360) des Punkts p um mitte - gegen den Uhrzeigersinn auf dem Blatt."""
    return math.degrees(math.atan2(-(float(p[1]) - float(mitte[1])),
                                   float(p[0]) - float(mitte[0]))) % 360.0


def punkt_auf_kreis(mitte, r: float, grad: float) -> tuple:
    a = math.radians(grad)
    return (float(mitte[0]) + r * math.cos(a), float(mitte[1]) - r * math.sin(a))


def bogen_spanne(von: float, bis: float) -> float:
    """Ueberstrichener Winkel [Grad] von ``von`` nach ``bis`` gegen den Uhrzeigersinn."""
    return (float(bis) - float(von)) % 360.0 or 360.0


def auf_bogen(el: dict, grad: float) -> bool:
    """Liegt der Winkel im Bogen?"""
    return (float(grad) - float(el["von"])) % 360.0 <= bogen_spanne(el["von"], el["bis"]) + 1e-9


def bogen_durch_drei_punkte(a, b, c):
    """Der Kreisbogen von a nach b durch c: (mitte, r, von, bis) - oder None,
    wenn die drei Punkte auf einer Geraden liegen."""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    cx, cy = float(c[0]), float(c[1])
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    mitte = (ux, uy)
    r = abstand(mitte, a)
    wa, wb, wc = winkel(mitte, a), winkel(mitte, b), winkel(mitte, c)
    # gegen den Uhrzeigersinn von a nach b: liegt c dazwischen? sonst andersherum
    if (wc - wa) % 360.0 <= (wb - wa) % 360.0:
        von, bis = wa, wb
    else:
        von, bis = wb, wa
    return mitte, r, von, bis


def _lot_auf_strecke(p, a, b):
    """(Fusspunkt, Abstand) des Punkts p zur Strecke a-b."""
    ax, ay = float(a[0]), float(a[1])
    dx, dy = float(b[0]) - ax, float(b[1]) - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-18:
        return (ax, ay), abstand(p, a)
    t = max(0.0, min(1.0, ((float(p[0]) - ax) * dx + (float(p[1]) - ay) * dy) / L2))
    f = (ax + t * dx, ay + t * dy)
    return f, abstand(p, f)


def bemassungslinie(el: dict) -> tuple:
    """(d1, d2, n) der Bemassung: die Masslinie parallel zu p1-p2 im Abstand
    ``abstand`` (positiv: links der Richtung p1 -> p2 auf dem Blatt)."""
    p1, p2 = el["p1"], el["p2"]
    L = abstand(p1, p2)
    if L < 1e-12:
        return tuple(p1), tuple(p2), (0.0, -1.0)
    dx, dy = (float(p2[0]) - float(p1[0])) / L, (float(p2[1]) - float(p1[1])) / L
    n = (dy, -dx)                                   # links der Richtung (y nach unten)
    a = float(el.get("abstand", 8.0))
    d1 = (float(p1[0]) + n[0] * a, float(p1[1]) + n[1] * a)
    d2 = (float(p2[0]) + n[0] * a, float(p2[1]) + n[1] * a)
    return d1, d2, n


def masstext(wert_mm: float, einheit: str = "mm", nk: int = None) -> str:
    """Die Masszahl mit Komma: Millimeter ganz, Zentimeter und Meter mit zwei
    Stellen (Vorgabe); ohne Einheit im Text, die steht in der Legende."""
    f = EINHEITEN.get(einheit, 1.0)
    v = float(wert_mm) * f
    if nk is None:
        nk = 0 if einheit == "mm" else 2
    s = f"{v:.{nk}f}"
    if nk and "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def bemassung_text(el: dict, skizze: dict) -> str:
    """Der Text einer Bemassung: eigener Text oder die gemessene Laenge im Massstab."""
    if el.get("text"):
        return str(el["text"])
    L = abstand(el["p1"], el["p2"]) * float(skizze.get("massstab", 1.0))
    return masstext(L, skizze.get("einheit", "mm"))


# ---------------------------------------------------------------------------
# Fang und Treffer
# ---------------------------------------------------------------------------
def fangpunkte(skizze: dict) -> list:
    """Alle Punkte, an denen der Zeiger einrastet: (x, y, Art)."""
    out = []
    for el in skizze.get("elemente", []):
        art = el.get("art")
        if art == "linie":
            p1, p2 = el["p1"], el["p2"]
            out.append((float(p1[0]), float(p1[1]), "Ende"))
            out.append((float(p2[0]), float(p2[1]), "Ende"))
            out.append(((float(p1[0]) + float(p2[0])) / 2, (float(p1[1]) + float(p2[1])) / 2, "Mitte"))
        elif art == "kreis":
            m, r = el["mitte"], float(el["r"])
            out.append((float(m[0]), float(m[1]), "Mittelpunkt"))
            for g in (0, 90, 180, 270):
                x, y = punkt_auf_kreis(m, r, g)
                out.append((x, y, "Quadrant"))
        elif art == "bogen":
            m, r = el["mitte"], float(el["r"])
            out.append((float(m[0]), float(m[1]), "Mittelpunkt"))
            for g in (el["von"], el["bis"]):
                x, y = punkt_auf_kreis(m, r, float(g))
                out.append((x, y, "Ende"))
        elif art == "bemassung":
            for p in (el["p1"], el["p2"]):
                out.append((float(p[0]), float(p[1]), "Masspunkt"))
        elif art == "text":
            p = el["p"]
            out.append((float(p[0]), float(p[1]), "Text"))
    return out


def fangen(skizze: dict, p, radius: float = 2.0):
    """Der naechste Fangpunkt im Umkreis - (x, y, Art) - oder None."""
    best = None
    for x, y, art in fangpunkte(skizze):
        d = math.hypot(x - float(p[0]), y - float(p[1]))
        if d <= radius and (best is None or d < best[0]):
            best = (d, (x, y, art))
    return best[1] if best else None


def rastern(p, schritt: float):
    """Auf das Raster runden (schritt 0 = unveraendert)."""
    if not schritt or schritt <= 0:
        return (float(p[0]), float(p[1]))
    return (round(float(p[0]) / schritt) * schritt, round(float(p[1]) / schritt) * schritt)


def element_abstand(el: dict, p, skizze: dict = None) -> float:
    """Abstand des Punkts zum Element [mm] - fuer Auswaehlen und Loeschen."""
    art = el.get("art")
    if art == "linie":
        return _lot_auf_strecke(p, el["p1"], el["p2"])[1]
    if art == "kreis":
        return abs(abstand(el["mitte"], p) - float(el["r"]))
    if art == "bogen":
        g = winkel(el["mitte"], p)
        if auf_bogen(el, g):
            return abs(abstand(el["mitte"], p) - float(el["r"]))
        return min(abstand(p, punkt_auf_kreis(el["mitte"], float(el["r"]), float(el[k]))) for k in ("von", "bis"))
    if art == "bemassung":
        d1, d2, _n = bemassungslinie(el)
        return _lot_auf_strecke(p, d1, d2)[1]
    if art == "text":
        groesse = float(el.get("groesse", 3.5))
        breite = 0.6 * groesse * max(1, len(str(el.get("text", ""))))
        x, y = float(el["p"][0]), float(el["p"][1])
        dx = max(x - float(p[0]), float(p[0]) - (x + breite), 0.0)
        dy = max(y - groesse - float(p[1]), float(p[1]) - y, 0.0)
        return math.hypot(dx, dy)
    return float("inf")


def element_bei(skizze: dict, p, toleranz: float = 1.5):
    """Nummer des naechsten Elements im Umkreis - oder -1."""
    best, best_i = toleranz, -1
    for i, el in enumerate(skizze.get("elemente", [])):
        d = element_abstand(el, p, skizze)
        if d <= best:
            best, best_i = d, i
    return best_i


def grenzen(skizze: dict):
    """(xmin, ymin, xmax, ymax) aller Elemente - oder None, wenn leer."""
    xs, ys = [], []
    for x, y, _art in fangpunkte(skizze):
        xs.append(x)
        ys.append(y)
    for el in skizze.get("elemente", []):
        if el.get("art") in ("kreis", "bogen"):
            m, r = el["mitte"], float(el["r"])
            xs += [float(m[0]) - r, float(m[0]) + r]
            ys += [float(m[1]) - r, float(m[1]) + r]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------
def _n(v: float) -> str:
    return f"{float(v):.3f}".rstrip("0").rstrip(".")


def _pfeil(spitze, richtung, farbe: str) -> str:
    """Ein gefuellter Masspfeil an ``spitze``, Schaft in ``richtung`` (Einheitsvektor vom Ende weg)."""
    sx, sy = spitze
    rx, ry = richtung
    b = PFEIL * 0.18
    p1 = (sx + rx * PFEIL - ry * b, sy + ry * PFEIL + rx * b)
    p2 = (sx + rx * PFEIL + ry * b, sy + ry * PFEIL - rx * b)
    return (f'<polygon points="{_n(sx)},{_n(sy)} {_n(p1[0])},{_n(p1[1])} {_n(p2[0])},{_n(p2[1])}" '
            f'fill="{farbe}" stroke="none"/>')


def element_svg(el: dict, skizze: dict, farbe: str = "#1a1a1a", hervor: bool = False) -> str:
    """Ein Element als SVG-Text (Blatt-mm)."""
    art = el.get("art")
    farbe = "#ff8800" if hervor else farbe
    w = STRICH.get(art, 0.35) * (2.0 if hervor else 1.0)
    if art == "linie":
        return (f'<line x1="{_n(el["p1"][0])}" y1="{_n(el["p1"][1])}" x2="{_n(el["p2"][0])}" '
                f'y2="{_n(el["p2"][1])}" stroke="{farbe}" stroke-width="{_n(w)}" stroke-linecap="round"/>')
    if art == "kreis":
        return (f'<circle cx="{_n(el["mitte"][0])}" cy="{_n(el["mitte"][1])}" r="{_n(el["r"])}" '
                f'fill="none" stroke="{farbe}" stroke-width="{_n(w)}"/>')
    if art == "bogen":
        r = float(el["r"])
        a = punkt_auf_kreis(el["mitte"], r, float(el["von"]))
        b = punkt_auf_kreis(el["mitte"], r, float(el["bis"]))
        gross = 1 if bogen_spanne(el["von"], el["bis"]) > 180.0 else 0
        # gegen den Uhrzeigersinn auf dem Blatt (y nach unten) ist in SVG sweep 0
        return (f'<path d="M {_n(a[0])} {_n(a[1])} A {_n(r)} {_n(r)} 0 {gross} 0 {_n(b[0])} {_n(b[1])}" '
                f'fill="none" stroke="{farbe}" stroke-width="{_n(w)}" stroke-linecap="round"/>')
    if art == "bemassung":
        d1, d2, n = bemassungslinie(el)
        p1, p2 = el["p1"], el["p2"]
        a = float(el.get("abstand", 8.0))
        s = 1.0 if a >= 0 else -1.0
        teile = [f'<g stroke="{farbe}" stroke-width="{_n(w)}" fill="none">']
        for p, d in ((p1, d1), (p2, d2)):
            e = (d[0] + n[0] * UEBERSTAND * s, d[1] + n[1] * UEBERSTAND * s)
            teile.append(f'<line x1="{_n(p[0])}" y1="{_n(p[1])}" x2="{_n(e[0])}" y2="{_n(e[1])}"/>')
        teile.append(f'<line x1="{_n(d1[0])}" y1="{_n(d1[1])}" x2="{_n(d2[0])}" y2="{_n(d2[1])}"/>')
        teile.append("</g>")
        L = abstand(d1, d2)
        if L > 1e-9:
            rx, ry = (d2[0] - d1[0]) / L, (d2[1] - d1[1]) / L
            teile.append(_pfeil(d1, (rx, ry), farbe))
            teile.append(_pfeil(d2, (-rx, -ry), farbe))
            grad = -math.degrees(math.atan2(-ry, rx))         # Drehung des Textes im Bild
            if grad > 90.0 or grad <= -90.0:
                grad += 180.0
        else:
            grad = 0.0
        mx, my = (d1[0] + d2[0]) / 2, (d1[1] + d2[1]) / 2
        # Text ueber der Masslinie: zur Seite der Hilfslinien-Normalen hin versetzt
        tx, ty = mx + n[0] * 1.2 * s, my + n[1] * 1.2 * s
        text = bemassung_text(el, skizze)
        teile.append(f'<text x="{_n(tx)}" y="{_n(ty)}" font-size="{_n(MASSSCHRIFT)}" '
                     f'font-family="Arial, Helvetica, sans-serif" text-anchor="middle" fill="{farbe}" '
                     f'transform="rotate({_n(grad)} {_n(tx)} {_n(ty)})">{escape(text)}</text>')
        return "".join(teile)
    if art == "text":
        g = float(el.get("groesse", 3.5))
        x, y = float(el["p"][0]), float(el["p"][1])
        dreh = float(el.get("winkel", 0.0))
        t = f' transform="rotate({_n(-dreh)} {_n(x)} {_n(y)})"' if dreh else ""
        return (f'<text x="{_n(x)}" y="{_n(y)}" font-size="{_n(g)}" font-family="Arial, Helvetica, sans-serif" '
                f'fill="{farbe}"{t}>{escape(str(el.get("text", "")))}</text>')
    return ""


def svg(skizze: dict, bild_png_base64: str = "", hervor: int = -1, raster: bool = False,
        px_je_mm: float = 3.7795) -> str:
    """Die ganze Skizze als SVG (Blatt in mm, Anzeige in Bildpunkten)."""
    s = pruefen(skizze)
    W, H = s["breite"], s["hoehe"]
    teile = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
             f'viewBox="0 0 {_n(W)} {_n(H)}" width="{_n(W * px_je_mm)}" height="{_n(H * px_je_mm)}">',
             f'<rect x="0" y="0" width="{_n(W)}" height="{_n(H)}" fill="#ffffff" stroke="#9aa0a6" stroke-width="0.2"/>']
    if bild_png_base64 and s.get("bild"):
        b = s["bild"]
        teile.append(f'<image x="{_n(b.get("x", 0))}" y="{_n(b.get("y", 0))}" width="{_n(b.get("breite", W))}" '
                     f'height="{_n(b.get("hoehe", H))}" preserveAspectRatio="none" '
                     f'href="data:image/png;base64,{bild_png_base64}"/>')
    if raster and s.get("raster"):
        r = float(s["raster"])
        linien = []
        x = 0.0
        while x <= W + 1e-9:
            linien.append(f'M {_n(x)} 0 V {_n(H)}')
            x += r
        y = 0.0
        while y <= H + 1e-9:
            linien.append(f'M 0 {_n(y)} H {_n(W)}')
            y += r
        teile.append(f'<path d="{" ".join(linien)}" stroke="#dfe3e8" stroke-width="0.1" fill="none"/>')
    for i, el in enumerate(s["elemente"]):
        teile.append(element_svg(el, s, hervor=(i == hervor)))
    teile.append("</svg>")
    return "".join(teile)


def beschreibung(skizze: dict) -> str:
    """Kurz, was auf dem Blatt ist: "3 Linien, 1 Kreis, 2 Maße"."""
    s = pruefen(skizze)
    zaehler: dict = {}
    for el in s["elemente"]:
        zaehler[el["art"]] = zaehler.get(el["art"], 0) + 1
    namen = {"linie": "Linien", "kreis": "Kreise", "bogen": "Bögen", "bemassung": "Maße", "text": "Texte"}
    teile = [f"{n} {namen.get(a, a)}" for a, n in zaehler.items()]
    if s.get("bild"):
        teile.append("Bild")
    return ", ".join(teile) or "leer"
