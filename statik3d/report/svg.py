"""
SVG-Zeichenhilfen fuer den statischen Bericht (reines Python, ohne matplotlib).

* Projection            orthographische Projektionen: Isometrie ("iso", Achsen
                        unter 30 Grad), Grundriss ("xy"), Ansicht ("xz"),
                        Seitenansicht ("yz") mit automatischer Einpassung
* draw_structure        Systemdarstellung: Staebe, Schalen, Volumen (Aussen-
                        facetten), Lager, Lasten eines Lastfalls, Verformung,
                        Ausnutzung, Knoten-/Elementnummern, Koordinatenkreuz
* draw_member_diagram   Schnittgroessenverlauf entlang eines Stabes mit
                        Umhuellender und Extremwerten
* draw_bar_chart        Balkendiagramm (Ausnutzungen)
* draw_sn_curve         Woehlerlinie nach DIN EN 1993-1-9 mit Lastpunkten

Alle Funktionen liefern einen vollstaendigen <svg>...</svg>-Ausschnitt als
Zeichenkette. Texte werden XML-sicher maskiert, Koordinaten auf eine
Nachkommastelle gerundet. Einheiten der Eingaben: SI (m, N, Pa); die
Beschriftungen erfolgen in kN, kNm, kN/m, mm, MPa.
"""
from __future__ import annotations

import itertools
import math
from xml.sax.saxutils import escape as _escape

import numpy as np

FONT = "Helvetica, Arial, sans-serif"

COL_BEAM = "#1f3b73"
COL_TRUSS = "#2e5c8a"
COL_SHELL_FILL = "#d9e6f2"
COL_SHELL_STROKE = "#5b7fa6"
COL_SOLID_FILL = "#c7d3e0"
COL_SOLID_STROKE = "#6f7f90"
COL_ORIG = "#9a9a9a"
COL_SUPPORT = "#222222"
COL_CONTACT = "#7f8c8d"
COL_LOAD = "#c0392b"
COL_TEXT = "#222222"
COL_GRID = "#d0d0d0"
COL_POS = "#2e86c1"
COL_NEG = "#c0392b"
COL_ENV = "#b8c9dc"

# Ausnutzungsklassen: (Obergrenze, Farbe, Beschriftung)
UTIL_CLASSES = ((0.5, "#2e8b57", "< 0.50"),
                (0.8, "#d4ac0d", "0.50 – 0.80"),
                (1.0, "#e67e22", "0.80 – 1.00"),
                (math.inf, "#c0392b", "≥ 1.00"))

_C30 = math.cos(math.radians(30.0))
_ids = itertools.count(1)


# ==========================================================================
# Grundhelfer
# ==========================================================================
def esc(text) -> str:
    """Text XML-sicher maskieren (auch fuer Attributwerte)."""
    return _escape(str(text), {'"': "&quot;", "'": "&apos;"})


def _n(v) -> str:
    """Koordinate als kurze Zeichenkette (eine Nachkommastelle, ohne -0)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(v):
        return "0"
    s = f"{v:.1f}"
    if s in ("-0.0", "0.0"):
        return "0"
    return s[:-2] if s.endswith(".0") else s


def _pts(P) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in P)


def _kn(v, digits=2) -> str:
    """N -> kN als kompakte Zahl (ohne Nachkomma-Nullen)."""
    s = f"{float(v) / 1e3:.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def util_colour(u) -> str:
    try:
        u = float(u)
    except (TypeError, ValueError):
        return COL_BEAM
    if not math.isfinite(u):
        return UTIL_CLASSES[-1][1]
    for lim, col, _ in UTIL_CLASSES:
        if u < lim:
            return col
    return UTIL_CLASSES[-1][1]


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(int(min(max(c, 0), 255)) for c in rgb)


def shade_colour(h: str, f: float) -> str:
    """Farbe abdunkeln (f < 1) bzw. beibehalten (f = 1)."""
    return _rgb_to_hex([c * f for c in _hex_to_rgb(h)])


_RAMP = [(0.0, (44, 123, 182)), (0.25, (171, 217, 233)), (0.5, (255, 255, 191)),
         (0.75, (253, 174, 97)), (1.0, (215, 25, 28))]


def ramp_colour(t: float) -> str:
    """Farbverlauf blau -> gelb -> rot fuer t in [0, 1]."""
    t = min(max(float(t) if math.isfinite(t) else 0.0, 0.0), 1.0)
    for (t0, c0), (t1, c1) in zip(_RAMP[:-1], _RAMP[1:]):
        if t <= t1:
            w = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return _rgb_to_hex([a + w * (b - a) for a, b in zip(c0, c1)])
    return _rgb_to_hex(_RAMP[-1][1])


def svg_open(width: int, height: int, title: str = "") -> str:
    w, h = int(width), int(height)
    s = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
         f'viewBox="0 0 {w} {h}" font-family="{FONT}" font-size="11">')
    if title:
        s += f"<title>{esc(title)}</title>"
    s += f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>'
    return s


def text(x, y, s, size=11, anchor="start", colour=COL_TEXT, weight=None, rotate=None,
         family=None, baseline=None) -> str:
    a = [f'x="{_n(x)}"', f'y="{_n(y)}"', f'font-size="{size}"', f'fill="{colour}"']
    if anchor != "start":
        a.append(f'text-anchor="{anchor}"')
    if weight:
        a.append(f'font-weight="{weight}"')
    if family:
        a.append(f'font-family="{esc(family)}"')
    if baseline:
        a.append(f'dominant-baseline="{baseline}"')
    if rotate:
        a.append(f'transform="rotate({_n(rotate)} {_n(x)} {_n(y)})"')
    return f"<text {' '.join(a)}>{esc(s)}</text>"


def line(x1, y1, x2, y2, colour=COL_TEXT, width=1.0, dash=None, cap=None, opacity=None) -> str:
    a = [f'x1="{_n(x1)}"', f'y1="{_n(y1)}"', f'x2="{_n(x2)}"', f'y2="{_n(y2)}"',
         f'stroke="{colour}"', f'stroke-width="{_n(width)}"']
    if dash:
        a.append(f'stroke-dasharray="{dash}"')
    if cap:
        a.append(f'stroke-linecap="{cap}"')
    if opacity is not None:
        a.append(f'stroke-opacity="{_n(opacity)}"')
    return f"<line {' '.join(a)}/>"


def arrow(x1, y1, x2, y2, colour=COL_LOAD, width=1.3, head=6.0) -> str:
    """Pfeil von (x1,y1) nach (x2,y2) mit Spitze am Ende."""
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return ""
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    bx, by = x2 - ux * head, y2 - uy * head
    tri = [(x2, y2), (bx + px * head * 0.45, by + py * head * 0.45),
           (bx - px * head * 0.45, by - py * head * 0.45)]
    return (line(x1, y1, bx, by, colour, width)
            + f'<polygon points="{_pts(tri)}" fill="{colour}"/>')


def _nice_step(span: float, n: int = 6) -> float:
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(n, 1)
    mag = 10.0 ** math.floor(math.log10(raw))
    for f in (1.0, 2.0, 2.5, 5.0, 10.0):
        if f * mag >= raw:
            return f * mag
    return 10.0 * mag


def _fmt_tick(v: float) -> str:
    if abs(v) < 1e-12:
        return "0"
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ==========================================================================
# Projektion
# ==========================================================================
class Projection:
    """Orthographische Projektion von Modellkoordinaten (x, y, z) auf
    Seitenkoordinaten (px, py; py nach unten) mit automatischer Einpassung.

    kind: "iso" (Isometrie: x unter -30 Grad nach rechts, y unter -30 Grad nach
          links, z senkrecht), "xy" (Grundriss), "xz" (Ansicht), "yz" (Seite).
    """

    _AX = {
        "iso": ((_C30, -0.5), (-_C30, -0.5), (0.0, -1.0)),
        "xy": ((1.0, 0.0), (0.0, -1.0), (0.0, 0.0)),
        "xz": ((1.0, 0.0), (0.0, 0.0), (0.0, -1.0)),
        "yz": ((0.0, 0.0), (1.0, 0.0), (0.0, -1.0)),
    }
    # Blickrichtung (groessere Werte = weiter vom Betrachter entfernt)
    _VIEW = {
        "iso": (1.0 / math.sqrt(3), 1.0 / math.sqrt(3), -1.0 / math.sqrt(3)),
        "xy": (0.0, 0.0, -1.0),
        "xz": (0.0, 1.0, 0.0),
        "yz": (-1.0, 0.0, 0.0),
    }
    LABELS = {"iso": "Isometrie", "xy": "Grundriss (x-y)", "xz": "Ansicht (x-z)",
              "yz": "Seitenansicht (y-z)"}

    def __init__(self, kind: str = "iso", width: int = 800, height: int = 520,
                 margin=(40, 36, 40, 46)):
        if kind not in self._AX:
            raise KeyError(f"Projektion '{kind}' unbekannt: {list(self._AX)}")
        self.kind = kind
        self.width = int(width)
        self.height = int(height)
        if isinstance(margin, (int, float)):
            margin = (margin, margin, margin, margin)
        self.margin = tuple(float(m) for m in margin)      # links, oben, rechts, unten
        self.M = np.array(self._AX[kind], dtype=float)      # (3, 2)
        self.view = np.array(self._VIEW[kind], dtype=float)
        self.light = np.array([-0.45, -0.6, 0.66])
        self.light /= np.linalg.norm(self.light)
        self.scale = 1.0
        self.offset = np.zeros(2)

    @property
    def label(self) -> str:
        return self.LABELS[self.kind]

    # ---- Abbildung -------------------------------------------------------
    def raw(self, P) -> np.ndarray:
        """Unskalierte 2D-Koordinaten (n, 2)."""
        return np.asarray(P, dtype=float).reshape(-1, 3) @ self.M

    def vec(self, v) -> np.ndarray:
        """Richtungsvektor (3,) -> Seitenrichtung (2,), nicht normiert."""
        return np.asarray(v, dtype=float).reshape(3) @ self.M

    def unit(self, v):
        """Normierte Seitenrichtung oder None, wenn der Vektor in Blickrichtung liegt."""
        d = self.vec(v)
        n = float(np.hypot(d[0], d[1]))
        if n < 1e-9:
            return None
        return d / n

    def fit(self, points) -> "Projection":
        """Massstab und Verschiebung so waehlen, dass alle Punkte in den
        Zeichenbereich (innerhalb der Raender) passen."""
        P = np.asarray(points, dtype=float).reshape(-1, 3)
        ml, mt, mr, mb = self.margin
        aw = max(self.width - ml - mr, 10.0)
        ah = max(self.height - mt - mb, 10.0)
        if P.size == 0:
            self.scale = 1.0
            self.offset = np.array([ml + aw / 2, mt + ah / 2])
            return self
        R = self.raw(P)
        lo, hi = R.min(axis=0), R.max(axis=0)
        span = hi - lo
        sx = aw / span[0] if span[0] > 1e-12 else math.inf
        sy = ah / span[1] if span[1] > 1e-12 else math.inf
        s = min(sx, sy)
        if not math.isfinite(s):
            s = 1.0
        self.scale = s
        c = (lo + hi) / 2.0
        self.offset = np.array([ml + aw / 2 - c[0] * s, mt + ah / 2 - c[1] * s])
        return self

    def project(self, P) -> np.ndarray:
        """Seitenkoordinaten (n, 2) nach fit()."""
        return self.raw(P) * self.scale + self.offset

    def point(self, p):
        q = self.project(np.asarray(p, dtype=float).reshape(1, 3))[0]
        return float(q[0]), float(q[1])

    def depth(self, P) -> np.ndarray:
        """Tiefe in Blickrichtung (groesser = weiter hinten)."""
        return np.asarray(P, dtype=float).reshape(-1, 3) @ self.view

    def shade(self, normal) -> float:
        """Helligkeitsfaktor 0.55 .. 1.0 aus der Flaechennormale."""
        n = np.asarray(normal, dtype=float)
        ln = float(np.linalg.norm(n))
        if ln <= 0:
            return 0.8
        return 0.55 + 0.45 * abs(float(n @ self.light) / ln)

    # ---- Koordinatenkreuz ---------------------------------------------------
    def triad(self, x0: float, y0: float, size: float = 22.0) -> str:
        out = []
        for name, v in (("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1))):
            d = self.unit(v)
            if d is None:
                continue
            x1, y1 = x0 + d[0] * size, y0 + d[1] * size
            out.append(arrow(x0, y0, x1, y1, "#444444", 1.2, 5))
            out.append(text(x1 + d[0] * 7, y1 + d[1] * 7 + 3, name, 10, "middle", "#444444"))
        return "".join(out)


# ==========================================================================
# Systemdarstellung
# ==========================================================================
def _element_groups(model):
    beams, shells, solids = [], [], []
    for i, e in enumerate(model.elements):
        if e.typ in ("beam", "truss"):
            beams.append(i)
        elif e.typ in ("shell3", "shell4"):
            shells.append(i)
        elif e.typ in ("tet4", "tet10", "hex8"):
            solids.append(i)
    return beams, shells, solids


def _facet_normal(X) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if len(X) < 3:
        return np.zeros(3)
    return np.cross(X[1] - X[0], X[2] - X[0])


def _polygons(proj, X, P, facets, fill, stroke, width=0.5, shade=True, dashed=False,
              colours=None):
    """Facetten (Knotentupel) sortiert nach Tiefe zeichnen (Maler-Algorithmus)."""
    if not facets:
        return ""
    items = []
    for f in facets:
        idx = list(f[1]) if isinstance(f, tuple) and len(f) == 2 and isinstance(f[1], (list, tuple)) \
            else list(f)
        key = f[0] if isinstance(f, tuple) and len(f) == 2 and isinstance(f[1], (list, tuple)) else None
        Xf = X[idx]
        d = float(proj.depth(Xf.mean(axis=0))[0])
        items.append((d, idx, key))
    items.sort(key=lambda t: -t[0])
    out = []
    if dashed:
        out.append(f'<g fill="none" stroke="{stroke}" stroke-width="{_n(width)}" '
                   f'stroke-dasharray="4,3">')
        for _, idx, _k in items:
            out.append(f'<polygon points="{_pts(P[idx])}"/>')
        out.append("</g>")
        return "".join(out)
    out.append(f'<g stroke="{stroke}" stroke-width="{_n(width)}" stroke-linejoin="round">')
    for _, idx, key in items:
        col = fill
        if colours is not None and key is not None and key in colours:
            col = colours[key]
        if shade:
            col = shade_colour(col, proj.shade(_facet_normal(X[idx])))
        out.append(f'<polygon points="{_pts(P[idx])}" fill="{col}"/>')
    out.append("</g>")
    return "".join(out)


def _support_dir(proj, dofs):
    """Seitenrichtung (2D, normiert) vom Knoten zur Lagerbasis: bevorzugt
    entgegen der gehaltenen z-, sonst x-, sonst y-Richtung."""
    for ax in (2, 0, 1):
        if ax in dofs:
            v = np.zeros(3)
            v[ax] = -1.0
            d2 = proj.unit(v)
            if d2 is not None:
                return d2
    return np.array([0.0, 1.0])


def _triangle(p, d2, size=11.0, colour=COL_SUPPORT, fill="#ffffff", dashed=False,
              ground=True) -> str:
    """Lagerdreieck mit Spitze in p, Basis in Richtung d2 (Seitenvektor, normiert)."""
    px, py = float(p[0]), float(p[1])
    dx, dy = float(d2[0]), float(d2[1])
    qx, qy = -dy, dx
    w = size * 0.55
    bx, by = px + dx * size, py + dy * size
    tri = [(px, py), (bx + qx * w, by + qy * w), (bx - qx * w, by - qy * w)]
    dash = ' stroke-dasharray="3,2"' if dashed else ""
    s = (f'<polygon points="{_pts(tri)}" fill="{fill}" stroke="{colour}" '
         f'stroke-width="1.2"{dash}/>')
    if ground:
        gx, gy = px + dx * (size + 2.5), py + dy * (size + 2.5)
        s += line(gx + qx * (w + 3), gy + qy * (w + 3), gx - qx * (w + 3), gy - qy * (w + 3),
                  colour, 1.2, "3,2" if dashed else None)
    return s


def _square(p, size=7.0, colour=COL_SUPPORT) -> str:
    return (f'<rect x="{_n(p[0] - size / 2)}" y="{_n(p[1] - size / 2)}" width="{_n(size)}" '
            f'height="{_n(size)}" fill="{colour}" stroke="{colour}"/>')


def _ranges(ids) -> str:
    """Zusammenhaengende Bereiche kompakt: 0-5, 8, 10-12."""
    ids = sorted(set(int(i) for i in ids))
    if not ids:
        return ""
    parts = []
    a = b = ids[0]
    for i in ids[1:]:
        if i == b + 1:
            b = i
        else:
            parts.append(f"{a}–{b}" if b > a else f"{a}")
            a = b = i
    parts.append(f"{a}–{b}" if b > a else f"{a}")
    return ", ".join(parts)


def _legend_util(x, y) -> str:
    out = [text(x, y, "Ausnutzung", 10, "start", COL_TEXT, "bold")]
    for k, (_, col, lab) in enumerate(UTIL_CLASSES):
        yy = y + 8 + k * 13
        out.append(f'<rect x="{_n(x)}" y="{_n(yy)}" width="12" height="9" fill="{col}"/>')
        out.append(text(x + 16, yy + 8, lab, 9))
    return "".join(out)


def _legend_ramp(x, y, vmin, vmax, unit, label) -> str:
    gid = f"grad{next(_ids)}"
    stops = "".join(f'<stop offset="{int(t * 100)}%" stop-color="{_rgb_to_hex(c)}"/>'
                    for t, c in _RAMP)
    return (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">{stops}'
            f'</linearGradient></defs>'
            + text(x, y, label, 10, "start", COL_TEXT, "bold")
            + f'<rect x="{_n(x)}" y="{_n(y + 6)}" width="90" height="9" fill="url(#{gid})" '
              f'stroke="#888888" stroke-width="0.5"/>'
            + text(x, y + 25, f"{_fmt_tick(vmin)} {unit}", 9)
            + text(x + 90, y + 25, f"{_fmt_tick(vmax)} {unit}", 9, "end"))


def draw_structure(model, projection="iso", width: int = 800, height: int = 520,
                   results=None, scale: float = None, field: str = None, util: dict = None,
                   show_nodes: bool = False, show_numbers: bool = False,
                   show_supports: bool = True, show_loads: bool = True, case=None,
                   title: str = "") -> str:
    """Systemdarstellung als SVG.

    projection : "iso" | "xy" | "xz" | "yz" oder Projection-Objekt
    results    : Results -> verformte Lage (gestrichelt: Ausgangslage)
    scale      : Ueberhoehungsfaktor (None = automatisch, max. |u| ~ 8 % der Modellgroesse)
    field      : "util" (Farbe je Stab aus util bzw. results), "umag" (Verschiebung), None
    util       : dict Element -> Ausnutzung (Farbe: gruen/gelb/orange/rot)
    case       : LoadCase, Lastfallname oder None (aktiver Lastfall) fuer die Lasten
    """
    own_proj = not isinstance(projection, Projection)
    proj = Projection(projection, width, height) if own_proj else projection
    W, H = proj.width, proj.height
    out = [svg_open(W, H, title)]
    nn = model.nn
    # Lastfall aufloesen (Raender haengen davon ab)
    lc = None
    if show_loads and model.load_cases:
        if case is None:
            try:
                lc = model.case()
            except KeyError:
                lc = None
        elif isinstance(case, str):
            lc = model.load_cases.get(case)
        else:
            lc = case
    if lc is not None and lc.n_loads == 0:
        lc = None
    legend_planned = bool(util) or field in ("util", "umag")
    if own_proj:
        ml, mt, mr, mb = proj.margin
        if lc is not None:
            ml, mt, mr, mb = max(ml, 70), max(mt, 64), max(mr, 70), max(mb, 50)
        if legend_planned:
            mr = max(mr, 130)
        proj.margin = (ml, mt, mr, mb)
    if nn == 0 or not model.elements:
        out.append(text(W / 2, H / 2, "kein Modell", 12, "middle", "#888888"))
        if title:
            out.append(text(10, 16, title, 13, "start", COL_TEXT, "bold"))
        out.append("</svg>")
        return "".join(out)

    X0 = np.asarray(model.nodes, dtype=float).reshape(-1, 3)
    size = model.characteristic_size()
    notes = []

    # ---- Verformung ---------------------------------------------------------
    X1 = None
    factor = 0.0
    umax = 0.0
    if results is not None and getattr(results, "u", None) is not None \
            and len(results.u) == nn:
        d = np.asarray(results.u, dtype=float)[:, :3]
        umax = float(np.linalg.norm(d, axis=1).max()) if d.size else 0.0
        if umax > 0 and np.isfinite(umax):
            factor = float(scale) if scale else 0.08 * size / umax
            X1 = X0 + factor * d
    proj.fit(X0 if X1 is None else np.vstack([X0, X1]))
    P0 = proj.project(X0)
    P1 = proj.project(X1) if X1 is not None else None

    beams, shells, solids = _element_groups(model)

    # ---- Farben -------------------------------------------------------------
    colours = {}
    legend = ""
    if field == "util" or (field is None and util):
        udict = util
        if udict is None and results is not None:
            try:
                udict = {i: d["util"] for i, d in results.beam_forces.items()
                         if d.get("util") is not None}
            except Exception:
                udict = {}
        for i, u in (udict or {}).items():
            colours[int(i)] = util_colour(u)
        if udict:
            legend = "util"
    elif field == "umag" and results is not None and X1 is not None:
        um = np.linalg.norm(np.asarray(results.u, dtype=float)[:, :3], axis=1)
        lo, hi = float(um.min()), float(um.max())
        rng = hi - lo if hi > lo else 1.0
        for i, e in enumerate(model.elements):
            t = (float(um[e.nodes].mean()) - lo) / rng
            colours[i] = ramp_colour(t)
        legend = "umag"
        legend_vals = (lo * 1e3, hi * 1e3)

    Amax = max((s.A for s in model.sections.values() if s.A > 0), default=1.0)

    def lw(e):
        sec = model.sections.get(e.sec) if e.sec else None
        a = sec.A if sec is not None and sec.A > 0 else Amax
        return 1.2 + 2.6 * math.sqrt(min(a / Amax, 1.0))

    def draw_beams(P, dashed=False):
        if not beams:
            return ""
        items = []
        for i in beams:
            e = model.elements[i]
            n1, n2 = e.nodes[0], e.nodes[1]
            dep = float(proj.depth((X0[n1] + X0[n2]) / 2.0)[0])
            items.append((dep, i, n1, n2))
        items.sort(key=lambda t: -t[0])
        parts = []
        if dashed:
            parts.append(f'<g stroke="{COL_ORIG}" stroke-width="1" stroke-dasharray="5,3" '
                         f'fill="none">')
            for _, i, n1, n2 in items:
                parts.append(f'<line x1="{_n(P[n1, 0])}" y1="{_n(P[n1, 1])}" '
                             f'x2="{_n(P[n2, 0])}" y2="{_n(P[n2, 1])}"/>')
            parts.append("</g>")
            return "".join(parts)
        parts.append('<g stroke-linecap="round" fill="none">')
        for _, i, n1, n2 in items:
            e = model.elements[i]
            col = colours.get(i, COL_TRUSS if e.typ == "truss" else COL_BEAM)
            parts.append(f'<line x1="{_n(P[n1, 0])}" y1="{_n(P[n1, 1])}" '
                         f'x2="{_n(P[n2, 0])}" y2="{_n(P[n2, 1])}" stroke="{col}" '
                         f'stroke-width="{_n(lw(e))}"/>')
        parts.append("</g>")
        return "".join(parts)

    shell_facets = [(i, tuple(model.elements[i].nodes)) for i in shells]
    solid_facets = []
    if solids:
        from ..mesher import surface_facets
        solid_facets = [(None, tuple(f)) for f in surface_facets(model)]

    # ---- Ausgangslage (gestrichelt) bei Verformung --------------------------
    if P1 is not None:
        if len(solid_facets) <= 400:
            out.append(_polygons(proj, X0, P0, solid_facets, "none", COL_ORIG, 0.6, False, True))
        out.append(_polygons(proj, X0, P0, shell_facets, "none", COL_ORIG, 0.6, False, True))
        out.append(draw_beams(P0, dashed=True))
    P = P1 if P1 is not None else P0

    # ---- Elemente -----------------------------------------------------------
    out.append(_polygons(proj, X0, P, solid_facets, COL_SOLID_FILL, COL_SOLID_STROKE, 0.5, True))
    out.append(_polygons(proj, X0, P, shell_facets, COL_SHELL_FILL, COL_SHELL_STROKE, 0.6, True,
                         colours=colours if legend == "umag" else None))
    out.append(draw_beams(P))

    # ---- Lager --------------------------------------------------------------
    if show_supports:
        for s in model.supports:
            if s.node < 0 or s.node >= nn:
                continue
            p = P0[s.node]
            trans = [d for d in s.dofs if d < 3]
            rot = [d for d in s.dofs if d >= 3]
            spring = bool(s.stiffness) and any(k for k in s.stiffness)
            if trans:
                d2 = _support_dir(proj, trans)
                out.append(_triangle(p, d2, 11, COL_SUPPORT,
                                     "#555555" if len(trans) == 3 else "#ffffff", spring))
            if rot:
                out.append(_square(p, 7, COL_SUPPORT))
        for cs in model.contact_supports:
            if cs.node < 0 or cs.node >= nn:
                continue
            d2 = proj.unit(-np.asarray(cs.direction, dtype=float))
            if d2 is None:
                d2 = np.array([0.0, 1.0])
            out.append(_triangle(P0[cs.node], d2, 11, COL_CONTACT, "none", True))
        for g in model.gap_elements:
            if max(g.node_a, g.node_b) >= nn:
                continue
            a, b = P0[g.node_a], P0[g.node_b]
            out.append(line(a[0], a[1], b[0], b[1], COL_CONTACT, 1.2, "3,2"))
            for q in (a, b):
                out.append(f'<circle cx="{_n(q[0])}" cy="{_n(q[1])}" r="2.5" fill="none" '
                           f'stroke="{COL_CONTACT}" stroke-width="1"/>')
        for cp in model.contact_pairs:
            for sn in cp.slave_nodes:
                if 0 <= sn < nn:
                    q = P0[sn]
                    out.append(f'<circle cx="{_n(q[0])}" cy="{_n(q[1])}" r="2.5" fill="none" '
                               f'stroke="{COL_CONTACT}" stroke-width="1"/>')

    # ---- Lasten -------------------------------------------------------------
    if lc is not None:
        out.append(_draw_loads(model, lc, proj, P0, X0, nn, notes))

    # ---- Knoten / Nummern ---------------------------------------------------
    if show_nodes:
        out.append(f'<g fill="#ffffff" stroke="{COL_BEAM}" stroke-width="0.8">')
        for k in range(nn):
            out.append(f'<circle cx="{_n(P0[k, 0])}" cy="{_n(P0[k, 1])}" r="2"/>')
        out.append("</g>")
    if show_numbers:
        if nn <= 400 and len(model.elements) <= 400:
            out.append('<g font-size="8" fill="#444444">')
            for k in range(nn):
                out.append(f'<text x="{_n(P0[k, 0] + 3)}" y="{_n(P0[k, 1] - 3)}">{k}</text>')
            out.append("</g>")
            out.append('<g font-size="8" fill="#a03060" font-style="italic">')
            for i, e in enumerate(model.elements):
                c = P0[e.nodes].mean(axis=0)
                out.append(f'<text x="{_n(c[0] + 2)}" y="{_n(c[1] + 3)}">{i}</text>')
            out.append("</g>")
        else:
            notes.append("Nummerierung wegen Modellgröße unterdrückt")

    # ---- Beschriftung -------------------------------------------------------
    if title:
        out.append(text(10, 16, title, 13, "start", COL_TEXT, "bold"))
    out.append(text(W - 10, 16, proj.label, 10, "end", "#666666"))
    for k, note in enumerate(notes[:6]):
        out.append(text(W - 10, 30 + k * 12, note, 9, "end", "#555555"))
    out.append(proj.triad(30, H - 30, 22))
    cap = ""
    if P1 is not None:
        f_txt = f"{factor:.0f}" if factor >= 10 else f"{factor:.1f}"
        cap = f"Verformte Lage, Überhöhung {f_txt}-fach (max |u| = {umax * 1e3:.2f} mm)"
        out.append(text(70, H - 8, cap, 10, "start", "#333333"))
    if legend == "util":
        out.append(_legend_util(W - 110, H - 66))
    elif legend == "umag":
        out.append(_legend_ramp(W - 115, H - 44, legend_vals[0], legend_vals[1], "mm",
                                "Verschiebung |u|"))
    out.append("</svg>")
    return "".join(out)


def _draw_loads(model, lc, proj, P0, X0, nn, notes) -> str:
    out = []
    # Knotenlasten
    nl = [l for l in lc.nodal_loads if 0 <= l.node < nn]
    Fmax = max((float(np.linalg.norm(l.F[:3])) for l in nl), default=0.0)
    for l in nl:
        F = np.asarray(l.F[:3], dtype=float)
        M = np.asarray(l.F[3:6], dtype=float)
        p = P0[l.node]
        fn = float(np.linalg.norm(F))
        if fn > 0:
            d2 = proj.unit(F)
            L = 28 + 22 * (fn / Fmax if Fmax > 0 else 1.0)
            if d2 is None:
                out.append(f'<circle cx="{_n(p[0])}" cy="{_n(p[1])}" r="4" fill="none" '
                           f'stroke="{COL_LOAD}" stroke-width="1.3"/>')
                out.append(f'<circle cx="{_n(p[0])}" cy="{_n(p[1])}" r="1.2" fill="{COL_LOAD}"/>')
                out.append(text(p[0] + 7, p[1] - 6, f"F = {_kn(fn)} kN", 9, "start", COL_LOAD))
            else:
                x1, y1 = p[0] - d2[0] * L, p[1] - d2[1] * L
                out.append(arrow(x1, y1, p[0], p[1], COL_LOAD, 1.5, 7))
                out.append(text(x1 - d2[0] * 4, y1 - d2[1] * 4 - 3, f"F = {_kn(fn)} kN", 9,
                                "middle" if abs(d2[1]) > 0.7 else ("end" if d2[0] > 0 else "start"),
                                COL_LOAD))
        mn = float(np.linalg.norm(M))
        if mn > 0:
            out.append(f'<circle cx="{_n(p[0])}" cy="{_n(p[1])}" r="7" fill="none" '
                       f'stroke="{COL_LOAD}" stroke-width="1.3" stroke-dasharray="9,3"/>')
            out.append(arrow(p[0] + 7, p[1] - 2, p[0] + 7, p[1] + 3, COL_LOAD, 1.3, 5))
            out.append(text(p[0] + 10, p[1] + 12, f"M = {_kn(mn)} kNm", 9, "start", COL_LOAD))

    # Streckenlasten
    bl = [l for l in lc.beam_loads if 0 <= l.elem < len(model.elements)]
    qmax = 0.0
    for l in bl:
        q1 = np.asarray(l.q, dtype=float)
        q2 = np.asarray(l.q2 if l.q2 is not None else l.q, dtype=float)
        qmax = max(qmax, float(np.linalg.norm(q1)), float(np.linalg.norm(q2)))
    labelled = set()
    if bl:
        from ..elements.beam3d import local_axes
    for l in bl:
        e = model.elements[l.elem]
        if len(e.nodes) < 2:
            continue
        a3, b3 = X0[e.nodes[0]], X0[e.nodes[1]]
        q1 = np.asarray(l.q, dtype=float)
        q2 = np.asarray(l.q2 if l.q2 is not None else l.q, dtype=float)
        if l.system == "local":
            try:
                T3, _ = local_axes(a3, b3, e.roll)
                g1 = T3.T @ q1
                g2 = T3.T @ q2
            except ValueError:
                continue
        else:
            g1, g2 = q1, q2
        gm = g1 if np.linalg.norm(g1) >= np.linalg.norm(g2) else g2
        a, b = P0[e.nodes[0]], P0[e.nodes[1]]
        Lpx = float(np.hypot(b[0] - a[0], b[1] - a[1]))
        d2 = proj.unit(gm) if np.linalg.norm(gm) > 0 else None
        key = (tuple(np.round(q1, 6)), tuple(np.round(q2, 6)), l.system)
        n_arr = int(min(max(Lpx / 16.0, 2), 14))
        if d2 is None:
            for k in range(n_arr + 1):
                t = k / n_arr
                c = a + (b - a) * t
                out.append(f'<circle cx="{_n(c[0])}" cy="{_n(c[1])}" r="2.2" fill="none" '
                           f'stroke="{COL_LOAD}" stroke-width="1"/>')
            tails = None
        else:
            tails = []
            for k in range(n_arr + 1):
                t = k / n_arr
                c = a + (b - a) * t
                qv = float(np.linalg.norm(g1 + (g2 - g1) * t))
                Lk = 10 + 16 * (qv / qmax if qmax > 0 else 1.0)
                t0 = (c[0] - d2[0] * Lk, c[1] - d2[1] * Lk)
                tails.append(t0)
                if qv > 0:
                    out.append(arrow(t0[0], t0[1], c[0], c[1], COL_LOAD, 1.0, 5))
            out.append(f'<polyline points="{_pts(tails)}" fill="none" stroke="{COL_LOAD}" '
                       f'stroke-width="1"/>')
        if key not in labelled:
            labelled.add(key)
            v1, v2 = float(np.linalg.norm(q1)), float(np.linalg.norm(q2))
            lab = f"q = {_kn(v1)} kN/m" if abs(v1 - v2) < 1e-9 else \
                f"q = {_kn(v1)} … {_kn(v2)} kN/m"
            if l.system == "local":
                lab += " (lokal)"
            c = (a + b) / 2.0
            if tails is not None:
                tm = np.mean(np.asarray(tails), axis=0)
                lx, ly = tm[0] - d2[0] * 8, tm[1] - d2[1] * 8
                anchor = "middle" if abs(d2[1]) > 0.7 else ("end" if d2[0] > 0 else "start")
            else:
                lx, ly, anchor = c[0], c[1] - 8, "middle"
            out.append(text(lx, ly, lab, 9, anchor, COL_LOAD))

    # Flaechenlasten
    fl = [l for l in lc.face_loads if 0 <= l.elem < len(model.elements)]
    pmax = max((abs(float(l.p)) for l in fl), default=0.0)
    labelled_p = set()
    n_solid_faces = 0
    for l in fl:
        e = model.elements[l.elem]
        if e.typ not in ("shell3", "shell4"):
            n_solid_faces += 1
            continue
        Xe = X0[e.nodes]
        c3 = Xe.mean(axis=0)
        if l.direction is not None:
            dirv = np.asarray(l.direction, dtype=float) * (1.0 if l.p >= 0 else -1.0)
        else:
            nrm = _facet_normal(Xe)
            ln = float(np.linalg.norm(nrm))
            dirv = nrm / ln * (1.0 if l.p >= 0 else -1.0) if ln > 0 else np.zeros(3)
        c = proj.project(c3.reshape(1, 3))[0]
        d2 = proj.unit(dirv) if np.linalg.norm(dirv) > 0 else None
        if d2 is None:
            out.append(f'<circle cx="{_n(c[0])}" cy="{_n(c[1])}" r="1.8" fill="{COL_LOAD}"/>')
        else:
            Lk = 8 + 12 * (abs(float(l.p)) / pmax if pmax > 0 else 1.0)
            out.append(arrow(c[0] - d2[0] * Lk, c[1] - d2[1] * Lk, c[0], c[1], COL_LOAD, 0.9, 4))
        key = round(float(l.p), 6)
        if key not in labelled_p:
            labelled_p.add(key)
            out.append(text(c[0] + 6, c[1] - 6, f"p = {_kn(l.p)} kN/m²", 9, "start", COL_LOAD))
    if n_solid_faces:
        notes.append(f"{n_solid_faces} Flächenlasten auf Volumenelementen")

    # Hinweise
    g = np.asarray(lc.gravity, dtype=float)
    if np.any(g):
        notes.append(f"Eigengewicht g = ({g[0]:.2f}, {g[1]:.2f}, {g[2]:.2f}) m/s²")
    if lc.temp_loads:
        dts = sorted(set(round(float(t.dT), 3) for t in lc.temp_loads))
        dt_txt = f"ΔT = {dts[0]:g} K" if len(dts) == 1 else f"ΔT = {dts[0]:g} … {dts[-1]:g} K"
        notes.append(f"{len(lc.temp_loads)} Temperaturlasten ({dt_txt})")
    if nl or bl or fl:
        notes.insert(0, f"Lastfall {lc.name}")
    return "".join(out)


# ==========================================================================
# Schnittgroessenverlauf
# ==========================================================================
def _with_crossings(x, v):
    """Nulldurchgaenge einfuegen, damit positive/negative Flaechen sauber enden."""
    xs, vs = [x[0]], [v[0]]
    for k in range(1, len(x)):
        if v[k - 1] * v[k] < 0:
            t = v[k - 1] / (v[k - 1] - v[k])
            xs.append(x[k - 1] + t * (x[k] - x[k - 1]))
            vs.append(0.0)
        xs.append(x[k])
        vs.append(v[k])
    return np.asarray(xs), np.asarray(vs)


def draw_member_diagram(x, values, quantity: str = "My", unit: str = "kNm", width: int = 700,
                        height: int = 180, envelope=None, title: str = "") -> str:
    """Verlauf einer Schnittgroesse entlang eines Stabes.

    x        : Stationen [m]
    values   : Werte in N bzw. Nm (werden durch 1e3 geteilt -> kN, kNm)
    envelope : (min-Array, max-Array) derselben Laenge fuer die Umhuellende
    """
    x = np.asarray(x, dtype=float).ravel()
    v = np.asarray(values, dtype=float).ravel() / 1e3
    n = min(len(x), len(v))
    out = [svg_open(width, height, title)]
    if n < 2:
        out.append(text(width / 2, height / 2, "keine Daten", 11, "middle", "#888888"))
        out.append("</svg>")
        return "".join(out)
    x, v = x[:n], v[:n]
    v = np.nan_to_num(v)
    mn = mx = None
    if envelope is not None:
        mn = np.nan_to_num(np.asarray(envelope[0], dtype=float).ravel()[:n] / 1e3)
        mx = np.nan_to_num(np.asarray(envelope[1], dtype=float).ravel()[:n] / 1e3)
        if len(mn) != n or len(mx) != n:
            mn = mx = None
    ml, mr = 64, 26
    mt = 26 if title else 14
    mb = 28
    Wp = width - ml - mr
    Hp = height - mt - mb
    xmin, xmax = float(x.min()), float(x.max())
    if xmax - xmin < 1e-12:
        xmax = xmin + 1.0
    allv = [v] + ([mn, mx] if mn is not None else [])
    vmin = min(0.0, min(float(a.min()) for a in allv))
    vmax = max(0.0, max(float(a.max()) for a in allv))
    if vmax - vmin < 1e-9:
        vmin, vmax = -1.0, 1.0
    pad = 0.08 * (vmax - vmin)
    vmin_a, vmax_a = vmin - pad, vmax + pad

    def X(xx):
        return ml + (xx - xmin) / (xmax - xmin) * Wp

    def Y(vv):
        return mt + (vmax_a - vv) / (vmax_a - vmin_a) * Hp

    y0 = Y(0.0)
    # Rahmen / Gitter
    out.append(f'<rect x="{_n(ml)}" y="{_n(mt)}" width="{_n(Wp)}" height="{_n(Hp)}" '
               f'fill="#fbfbfb" stroke="#bbbbbb" stroke-width="0.6"/>')
    step_x = _nice_step(xmax - xmin, 8)
    k = math.ceil(xmin / step_x - 1e-9)
    while k * step_x <= xmax + 1e-9:
        xx = k * step_x
        out.append(line(X(xx), mt, X(xx), mt + Hp, COL_GRID, 0.5))
        out.append(text(X(xx), mt + Hp + 12, _fmt_tick(xx), 9, "middle", "#444444"))
        k += 1
    step_y = _nice_step(vmax_a - vmin_a, 4)
    k = math.ceil(vmin_a / step_y - 1e-9)
    while k * step_y <= vmax_a + 1e-9:
        vv = k * step_y
        out.append(line(ml, Y(vv), ml + Wp, Y(vv), COL_GRID, 0.5))
        out.append(text(ml - 5, Y(vv) + 3, _fmt_tick(vv), 9, "end", "#444444"))
        k += 1
    # Umhuellende
    if mn is not None:
        poly = [(X(xx), Y(vv)) for xx, vv in zip(x, mx)] + \
               [(X(xx), Y(vv)) for xx, vv in zip(x[::-1], mn[::-1])]
        out.append(f'<polygon points="{_pts(poly)}" fill="{COL_ENV}" fill-opacity="0.55" '
                   f'stroke="#7f9bb8" stroke-width="0.6"/>')
    # Flaechen positiv / negativ
    xc, vc = _with_crossings(x, v)
    pos = [(X(xx), Y(max(vv, 0.0))) for xx, vv in zip(xc, vc)]
    neg = [(X(xx), Y(min(vv, 0.0))) for xx, vv in zip(xc, vc)]
    base = [(X(xc[-1]), y0), (X(xc[0]), y0)]
    if np.any(vc > 0):
        out.append(f'<polygon points="{_pts(pos + base)}" fill="{COL_POS}" fill-opacity="0.35" '
                   f'stroke="none"/>')
    if np.any(vc < 0):
        out.append(f'<polygon points="{_pts(neg + base)}" fill="{COL_NEG}" fill-opacity="0.35" '
                   f'stroke="none"/>')
    # Nulllinie und Verlauf
    out.append(line(ml, y0, ml + Wp, y0, "#222222", 1.0))
    out.append(f'<polyline points="{_pts([(X(xx), Y(vv)) for xx, vv in zip(x, v)])}" '
               f'fill="none" stroke="#1a3d6d" stroke-width="1.4" stroke-linejoin="round"/>')
    # Extremwerte
    imax, imin = int(np.argmax(v)), int(np.argmin(v))
    eps = 1e-9 * max(abs(vmax), abs(vmin), 1.0)
    marks = []
    if v[imax] > eps:
        marks.append((imax, True))
    if v[imin] < -eps:
        marks.append((imin, False))
    for idx, above in marks:
        px, py = X(x[idx]), Y(v[idx])
        out.append(f'<circle cx="{_n(px)}" cy="{_n(py)}" r="2.5" fill="#1a3d6d"/>')
        lab = f"{v[idx]:.2f} {unit} (x = {x[idx]:.2f} m)"
        ty = py - 6 if above else py + 13
        if above and ty < mt + 9:
            ty = py + 13
        elif not above and ty > mt + Hp - 2:
            ty = py - 6
        anchor = "middle"
        if px < ml + 60:
            anchor = "start"
        elif px > ml + Wp - 60:
            anchor = "end"
        out.append(text(px, ty, lab, 9, anchor, "#1a3d6d", "bold"))
    # Achsenbeschriftung, Titel
    out.append(text(13, mt + Hp / 2, f"{quantity} [{unit}]", 10, "middle", "#222222",
                    rotate=-90))
    out.append(text(ml + Wp, mt + Hp + 24, "x [m]", 9, "end", "#444444"))
    if mn is not None:
        out.append(text(ml + Wp, mt - 4, "Umhüllende min/max (grau)", 9, "end", "#666666"))
    if title:
        out.append(text(10, 15, title, 12, "start", COL_TEXT, "bold"))
    out.append("</svg>")
    return "".join(out)


# ==========================================================================
# Balkendiagramm
# ==========================================================================
def draw_bar_chart(labels, values, width: int = 620, height: int = None, limit: float = 1.0,
                   title: str = "") -> str:
    """Horizontale Balken (z.B. Ausnutzung je Stab); Balken ueber 'limit' rot."""
    labels = [str(l) for l in labels]
    vals = [float(v) if v is not None and math.isfinite(float(v)) else 0.0 for v in values]
    n = min(len(labels), len(vals))
    row = 17
    top = 28 if title else 12
    if height is None:
        height = top + row * max(n, 1) + 26
    out = [svg_open(width, height, title)]
    if n == 0:
        out.append(text(width / 2, height / 2, "keine Daten", 11, "middle", "#888888"))
        out.append("</svg>")
        return "".join(out)
    lab_w = min(max(max(len(l) for l in labels[:n]) * 6.2 + 12, 60), 0.4 * width)
    x0 = lab_w + 8
    bar_w = width - x0 - 70
    vmax_axis = max(max(vals[:n]) * 1.05, (limit or 0.0) * 1.15, 1e-9)

    def X(v):
        return x0 + v / vmax_axis * bar_w

    step = _nice_step(vmax_axis, 5)
    k = 0
    while k * step <= vmax_axis + 1e-9:
        xx = X(k * step)
        out.append(line(xx, top - 2, xx, top + row * n, COL_GRID, 0.5))
        out.append(text(xx, top + row * n + 12, _fmt_tick(k * step), 9, "middle", "#444444"))
        k += 1
    for i in range(n):
        y = top + i * row
        v = vals[i]
        col = util_colour(v * (1.0 / limit) if limit else v) if limit else COL_POS
        out.append(text(x0 - 6, y + 12, labels[i], 10, "end"))
        out.append(f'<rect x="{_n(x0)}" y="{_n(y + 3)}" width="{_n(max(X(v) - x0, 0.5))}" '
                   f'height="{row - 6}" fill="{col}"/>')
        out.append(text(X(v) + 4, y + 12, f"{v:.3f}", 9, "start", "#222222"))
    if limit and limit <= vmax_axis:
        xl = X(limit)
        out.append(line(xl, top - 4, xl, top + row * n, "#c0392b", 1.2, "5,3"))
        out.append(text(xl, top - 6, f"Grenze {limit:g}", 9, "middle", "#c0392b"))
    if title:
        out.append(text(10, 15, title, 12, "start", COL_TEXT, "bold"))
    out.append("</svg>")
    return "".join(out)


# ==========================================================================
# Woehlerlinie
# ==========================================================================
_SUP = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def draw_sn_curve(category: float, points=None, gamma_Mf: float = 1.0, width: int = 560,
                  height: int = 320, title: str = "", shear: bool = False) -> str:
    """Woehlerlinie (log-log) nach DIN EN 1993-1-9 fuer Kerbfall 'category' [Pa]
    mit Dauerfestigkeit (Delta_sigma_D bei 5e6) und Schwellenwert (Delta_sigma_L
    bei 1e8) sowie den Lastpunkten points = [(Delta_sigma [Pa], n[, Name]), ...]."""
    from ..ec3.fatigue import sn_life
    cat = float(category)
    gMf = float(gamma_Mf) if gamma_Mf else 1.0
    dc = cat / gMf
    if shear:
        dD = None
        dL = (2.0 / 100.0) ** 0.2 * dc
    else:
        dD = (2.0 / 5.0) ** (1.0 / 3.0) * dc
        dL = (5.0 / 100.0) ** 0.2 * dD
    lN0, lN1 = 4.0, 9.0
    ds_lo, ds_hi = 10.0, 1000.0
    lS0, lS1 = math.log10(ds_lo), math.log10(ds_hi)
    ml, mr = 58, 18
    mt = 28 if title else 16
    mb = 34
    Wp, Hp = width - ml - mr, height - mt - mb

    def X(N):
        return ml + (math.log10(max(N, 1.0)) - lN0) / (lN1 - lN0) * Wp

    def Y(ds_mpa):
        return mt + (lS1 - math.log10(max(ds_mpa, 1e-9))) / (lS1 - lS0) * Hp

    out = [svg_open(width, height, title)]
    out.append(f'<rect x="{_n(ml)}" y="{_n(mt)}" width="{_n(Wp)}" height="{_n(Hp)}" '
               f'fill="#fbfbfb" stroke="#bbbbbb" stroke-width="0.6"/>')
    # Gitter (Dekaden)
    for k in range(int(lN0), int(lN1) + 1):
        xx = X(10.0 ** k)
        out.append(line(xx, mt, xx, mt + Hp, COL_GRID, 0.6))
        out.append(text(xx, mt + Hp + 13, "10" + str(k).translate(_SUP), 9, "middle", "#444444"))
        for j in (2, 5):
            if k < lN1:
                xj = X(j * 10.0 ** k)
                out.append(line(xj, mt, xj, mt + Hp, "#e6e6e6", 0.4))
    for k in range(int(lS0), int(lS1) + 1):
        yy = Y(10.0 ** k)
        out.append(line(ml, yy, ml + Wp, yy, COL_GRID, 0.6))
        out.append(text(ml - 5, yy + 3, _fmt_tick(10.0 ** k), 9, "end", "#444444"))
        for j in (2, 5):
            if k < lS1:
                yj = Y(j * 10.0 ** k)
                out.append(line(ml, yj, ml + Wp, yj, "#e6e6e6", 0.4))
                out.append(text(ml - 5, yj + 3, _fmt_tick(j * 10.0 ** k), 8, "end", "#888888"))
    # Kurve: Schwingbreiten absteigend abtasten, N aus sn_life
    m1 = 5.0 if shear else 3.0
    ds_start = dc * (2e6 / 10.0 ** lN0) ** (1.0 / m1)        # Schwingbreite bei N = 1e4
    ds_start = min(ds_start, ds_hi * 1e6)
    pts = []
    for ds in np.geomspace(ds_start, max(dL, 1.0), 160):
        N = sn_life(float(ds), cat, gMf, shear)
        if not np.isfinite(N) or N < 10.0 ** lN0:
            continue
        pts.append((X(min(N, 10.0 ** lN1)), Y(ds / 1e6)))
    pts.append((X(10.0 ** lN1), Y(dL / 1e6)))
    if pts:
        out.append(f'<polyline points="{_pts(pts)}" fill="none" stroke="#1a3d6d" '
                   f'stroke-width="1.8" stroke-linejoin="round"/>')
    # Kennwerte
    marks = [(dc, 2e6, ("Δτ_C" if shear else "Δσ_C") + f" = {dc / 1e6:.1f} MPa")]
    if dD is not None:
        marks.append((dD, 5e6, f"Δσ_D = {dD / 1e6:.1f} MPa (N = 5·10⁶)"))
    marks.append((dL, 1e8, ("Δτ_L" if shear else "Δσ_L") + f" = {dL / 1e6:.1f} MPa (N = 10⁸)"))
    for ds, N, lab in marks:
        xx, yy = X(N), Y(ds / 1e6)
        out.append(line(ml, yy, xx, yy, "#888888", 0.7, "4,3"))
        out.append(line(xx, yy, xx, mt + Hp, "#888888", 0.7, "4,3"))
        out.append(f'<circle cx="{_n(xx)}" cy="{_n(yy)}" r="2.5" fill="#888888"/>')
        if xx > ml + 0.72 * Wp:
            out.append(text(xx - 5, yy - 4, lab, 9, "end", "#555555"))
        else:
            out.append(text(xx + 5, yy - 4, lab, 9, "start", "#555555"))
    # Lastpunkte
    for k, pt in enumerate(points or []):
        try:
            ds, n = float(pt[0]), float(pt[1])
        except (TypeError, ValueError, IndexError):
            continue
        if ds <= 0 or n <= 0:
            continue
        name = str(pt[2]) if len(pt) > 2 else ""
        xx = X(min(max(n, 10.0 ** lN0), 10.0 ** lN1))
        yy = Y(min(max(ds / 1e6, ds_lo), ds_hi))
        NR = sn_life(ds, cat, gMf, shear)
        ok = not (np.isfinite(NR) and n > NR)
        col = "#2e8b57" if ok else "#c0392b"
        out.append(f'<circle cx="{_n(xx)}" cy="{_n(yy)}" r="4.5" fill="{col}" '
                   f'fill-opacity="0.85" stroke="#222222" stroke-width="0.8"/>')
        lab = f"{name + ': ' if name else ''}Δσ = {ds / 1e6:.1f} MPa, n = {n:.3g}"
        if xx > ml + 0.6 * Wp:
            out.append(text(xx - 7, yy + 4 + 11 * (k % 2), lab, 9, "end", col))
        else:
            out.append(text(xx + 7, yy + 4 + 11 * (k % 2), lab, 9, "start", col))
    # Beschriftung
    out.append(text(ml, mt - 4, ("Δτ" if shear else "Δσ") + " [MPa]", 10, "start", "#222222"))
    out.append(text(ml + Wp, mt + Hp + 27, "Lastspielzahl N", 9, "end", "#444444"))
    out.append(text(ml + Wp, mt - 4, f"Kerbfall {cat / 1e6:.0f}, γ_Mf = {gMf:.2f}" +
                    (", Schub (m = 5)" if shear else ", m = 3 / 5"), 9, "end", "#666666"))
    if title:
        out.append(text(10, 15, title, 12, "start", COL_TEXT, "bold"))
    out.append("</svg>")
    return "".join(out)
