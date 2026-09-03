"""
Verformungsnachweise im Grenzzustand der Gebrauchstauglichkeit.

Die Kombinationen des GZG rechnet das Programm ohnehin; hier werden sie gegen
**Grenzwerte** gehalten. Drei Bezuege stehen zur Wahl:

**Stab** - die Durchbiegung w bezogen auf die **Sehne** zwischen den beiden
Stabenden. Sie wird nicht aus den Knotenwerten geschaetzt, sondern aus der
Momentenlinie gewonnen::

    w'' = M / (E I)   ->   zweifach integriert, danach die Gerade durch die
                           beiden Stabenden abgezogen

Damit ist das Ergebnis auch dann richtig, wenn ein Stab nur aus einem Element
besteht: M(x) enthaelt die Streckenlast exakt (linear veraenderlich), und der
Starrkoerperanteil faellt beim Abzug der Sehne heraus. Eine Ueberhoehung w_c
wird abgezogen (EN 1993-1-1, A.1.4.2: w = w_max - w_c).

**Knoten** - Verschiebung oder Verdrehung eines Knotens gegenueber der
Ausgangslage. Das ist der Nachweis fuer Kragarmspitzen und fuer die
Kopfverschiebung von Stuetzen.

**Punktpaar** - die Verschiebung zweier Knoten **gegeneinander**. Damit werden
Dichtungen, Fuehrungen, Fugen und Anschlaege nachgewiesen, wie sie DIN 19704
im Stahlwasserbau verlangt.

Grenzwerte sind entweder L/x (L = Stablaenge beziehungsweise Abstand der
beiden Knoten) oder ein absoluter Wert. Nachgewiesen wird gegen die
Kombinationen der gewaehlten Bemessungssituation - charakteristisch, haeufig
oder quasi-staendig -, und die unguenstigste ist massgebend.

    from statik3d.gzg import check_verformung
    an = solver.solve_all(model, design=True)
    print(an.gzg.summary())
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import Model, Verformungsgrenze
from . import solver as _s

#: Spaltenindex der Verformungsgroesse in der Verschiebungsmatrix u (n,6)
INDEX = {"ux": 0, "uy": 1, "uz": 2, "phix": 3, "phiy": 4, "phiz": 5}

#: Bemessungssituationen des GZG
SITUATIONEN = {"SLS_CH": "charakteristisch", "SLS_FR": "häufig",
               "SLS_QP": "quasi-ständig"}


# --------------------------------------------------------------------------
# Durchbiegung eines Stabes aus der Momentenlinie
# --------------------------------------------------------------------------
def _biegelinie_element(xs: np.ndarray, kappa: np.ndarray, theta0: float,
                        w0: float) -> tuple:
    """Zweifache Integration der Kruemmung ueber einem Element - **exakt**.

    Bei linear veraenderlicher Streckenlast ist M(x) hoechstens kubisch und
    EI im Element konstant; die Kruemmung wird darum durch ein Polynom
    dritten Grades genau beschrieben und laesst sich geschlossen integrieren.
    So bleibt das Ergebnis auch bei nur einem Element je Stab richtig.
    Rueckgabe: (w(x), theta am Elementende, w am Elementende).
    """
    p = np.polyfit(xs - xs[0], kappa, min(3, max(len(xs) - 1, 1)))
    P1 = np.polyint(p)
    P2 = np.polyint(P1)
    t = xs - xs[0]
    A = np.polyval(P1, t) - np.polyval(P1, 0.0)          # theta - theta0
    B = np.polyval(P2, t) - np.polyval(P2, 0.0) - np.polyval(P1, 0.0) * t
    w = w0 + theta0 * t + B
    return w, theta0 + A[-1], w[-1]


def durchbiegung(model: Model, res, member, n: int = 9) -> dict:
    """Durchbiegung eines Stabes bezogen auf die Sehne.

    Rueckgabe: {"x", "w_y", "w_z", "L"} - w_y und w_z sind die Durchbiegungen
    in den lokalen Achsen y und z [m], jeweils gegen die Gerade durch die
    beiden Stabenden. Die Ueberlagerung mit der Starrkoerperbewegung faellt
    beim Abzug der Sehne heraus.
    """
    n = max(int(n), 5)
    xs_ges, wz, wy = [], [], []
    tz = wz0 = ty = wy0 = 0.0
    x0 = 0.0
    for i in member.elements:
        st = _s.beam_station_forces(model, res, i, n)
        e = model.elements[int(i)]
        sec = model.sections.get(e.sec)
        mat = model.materials.get(e.mat)
        EIy = mat.E * sec.Iy if (sec is not None and mat is not None) else 0.0
        EIz = mat.E * sec.Iz if (sec is not None and mat is not None) else 0.0
        xs = np.asarray(st["x"], float) + x0
        kz = np.asarray(st["My"], float) / EIy if EIy > 0 else np.zeros(n)
        ky = np.asarray(st["Mz"], float) / EIz if EIz > 0 else np.zeros(n)
        w1, tz, wz0 = _biegelinie_element(xs, kz, tz, wz0)
        w2, ty, wy0 = _biegelinie_element(xs, ky, ty, wy0)
        xs_ges.append(xs)
        wz.append(w1)
        wy.append(w2)
        x0 += float(st["L"])
    if not xs_ges:
        leer = np.zeros(0)
        return {"x": leer, "w_y": leer, "w_z": leer, "L": 0.0}
    x = np.concatenate(xs_ges)
    L = float(x0)
    out = {"x": x, "L": L}
    for name, teile in (("w_z", wz), ("w_y", wy)):
        w = np.concatenate(teile)
        out[name] = w - (w[-1] * x / L if L > 0 else 0.0)     # Sehne abziehen
    return out


# --------------------------------------------------------------------------
# Ergebnis
# --------------------------------------------------------------------------
@dataclass
class GrenzeCheck:
    """Ein gefuehrter Verformungsnachweis."""
    name: str
    art: str = "stab"
    bezug: str = ""
    groesse: str = "uz"
    situation: str = ""
    L: float = 0.0
    grenze: float = 0.0            # zulaessiger Wert [m] oder [rad]
    grenztext: str = ""
    wert: float = 0.0              # groesster Betrag [m] oder [rad]
    util: float = 0.0
    kombination: str = ""
    stelle: str = ""
    je_kombination: list = field(default_factory=list)
    ueberhoehung: float = 0.0
    hinweise: list = field(default_factory=list)
    fehler: str = ""

    @property
    def winkel(self) -> bool:
        return self.groesse.startswith("phi")

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"

    def werttext(self) -> str:
        f, e = (1e3, "mrad") if self.winkel else (1e3, "mm")
        return f"{self.wert * f:.2f} {e}"


@dataclass
class GZGResults:
    checks: dict = field(default_factory=dict)
    kombinationen: list = field(default_factory=list)

    @property
    def util_max(self) -> float:
        return max((c.util for c in self.checks.values()), default=0.0)

    def summary(self) -> str:
        if not self.checks:
            return "Verformungsnachweise: keine Grenzwerte festgelegt"
        schlecht = [c.name for c in self.checks.values() if c.util > 1.0]
        fehler = [c.name for c in self.checks.values() if c.fehler]
        worst = max(self.checks.values(), key=lambda c: c.util)
        s = (f"Verformungen (GZG): {len(self.checks)} Nachweise, max. Ausnutzung "
             f"{worst.util:.3f} ({worst.name}: {worst.werttext()} von {worst.grenztext}"
             + (f", {worst.kombination}" if worst.kombination else "") + ")")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif not fehler:
            s += " - alle erfüllt"
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Nachweis", "Bezug", "Größe", "Situation", "Wert", "Grenzwert",
                 "Ausnutzung", "Kombination", "Stelle", "Status"]]
        for c in self.checks.values():
            rows.append([c.name, c.bezug, c.groesse,
                         SITUATIONEN.get(c.situation, c.situation or "alle GZG"),
                         c.werttext(), c.grenztext, f"{c.util:.3f}",
                         c.kombination, c.stelle, c.status()])
        return rows


# --------------------------------------------------------------------------
# Nachweis
# --------------------------------------------------------------------------
def _sls_results(model: Model, analysis, situation: str = "") -> dict:
    """Die GZG-Ergebnisse der gewaehlten Bemessungssituation."""
    combos = getattr(analysis, "combinations", None) or {}
    aus = {k: r for k, r in combos.items()
           if k in model.combinations and model.combinations[k].is_sls
           and (not situation or model.combinations[k].typ == situation)}
    if aus:
        return aus
    if situation:
        # eine bestimmte Situation wurde verlangt und fehlt - das wird gesagt,
        # nicht durch etwas anderes ersetzt
        return {}
    if combos:
        return {}
    # gar keine Kombinationen im Modell: dann gelten die Lastfaelle selbst
    return dict(getattr(analysis, "cases", None) or {})


def _knotenwert(res, knoten: int, groesse: str) -> float:
    u = getattr(res, "u", None)
    if u is None or knoten >= len(u):
        return None
    if groesse == "u":
        return float(np.linalg.norm(u[knoten, :3]))
    return float(u[knoten, INDEX[groesse]])


def check_grenze(model: Model, g: Verformungsgrenze, ergebnisse: dict) -> GrenzeCheck:
    """Eine Verformungsgrenze ueber alle uebergebenen Ergebnisse fuehren."""
    c = GrenzeCheck(g.name, g.art, g.bezug(), g.groesse, g.situation,
                    grenztext=g.grenztext(), ueberhoehung=g.ueberhoehung)
    if not ergebnisse:
        c.fehler = ("keine Ergebnisse der Bemessungssituation "
                    f"{SITUATIONEN.get(g.situation, g.situation or 'GZG')}")
        return c
    # -- Bezugslaenge -------------------------------------------------
    if g.art == "stab":
        mem = model.members.get(g.stab)
        if mem is None:
            c.fehler = f"Stab „{g.stab}“ gibt es nicht"
            return c
        c.L = float(model.member_length(mem))
    elif g.art == "punktpaar":
        a, b = int(g.knoten[0]), int(g.knoten[1])
        if max(a, b) >= model.nn:
            c.fehler = "Knoten gibt es nicht"
            return c
        c.L = float(np.linalg.norm(model.nodes[b] - model.nodes[a]))
    else:
        if not g.knoten or int(g.knoten[0]) >= model.nn:
            c.fehler = "Knoten gibt es nicht"
            return c
        c.L = 0.0

    if g.grenzart == "L/x":
        if c.L <= 0:
            c.fehler = "L/x verlangt eine Bezugslänge (Stab oder Punktpaar)"
            return c
        if g.wert <= 0:
            c.fehler = "Nenner der Grenze L/x muss größer als null sein"
            return c
        c.grenze = c.L / float(g.wert)
        c.grenztext = f"L/{g.wert:g} = {c.grenze * 1e3:.1f} mm  (L = {c.L:.2f} m)"
    else:
        c.grenze = float(g.wert)
    if c.grenze <= 0:
        c.fehler = "Grenzwert muss größer als null sein"
        return c

    # -- ueber alle Kombinationen -------------------------------------
    for name, res in ergebnisse.items():
        try:
            wert, stelle = _wert(model, g, res, c)
        except Exception as ex:            # noqa: BLE001
            c.fehler = f"{type(ex).__name__}: {ex}"
            return c
        if wert is None:
            continue
        wert = abs(wert) - (g.ueberhoehung if g.art == "stab" else 0.0)
        wert = max(wert, 0.0)
        c.je_kombination.append({"kombination": name, "wert": wert,
                                 "util": wert / c.grenze, "stelle": stelle})
        if wert / c.grenze > c.util:
            c.util, c.wert, c.kombination, c.stelle = (wert / c.grenze, wert,
                                                       name, stelle)
    if not c.je_kombination:
        c.fehler = "keine Verschiebungen in den Ergebnissen"
    if g.ueberhoehung and g.art == "stab":
        c.hinweise.append(f"Überhöhung w_c = {g.ueberhoehung * 1e3:.1f} mm abgezogen "
                          "(EN 1993-1-1, A.1.4.2)")
    return c


def _wert(model: Model, g: Verformungsgrenze, res, c: GrenzeCheck) -> tuple:
    """(Wert, Stelle) einer Grenze fuer ein Ergebnis."""
    if g.art == "knoten":
        return _knotenwert(res, int(g.knoten[0]), g.groesse), f"Knoten {g.knoten[0]}"
    if g.art == "punktpaar":
        a, b = int(g.knoten[0]), int(g.knoten[1])
        va, vb = _knotenwert(res, a, g.groesse), _knotenwert(res, b, g.groesse)
        if va is None or vb is None:
            return None, ""
        if g.groesse == "u":
            u = getattr(res, "u")
            return float(np.linalg.norm(u[b, :3] - u[a, :3])), f"{a} gegen {b}"
        return vb - va, f"{a} gegen {b}"
    mem = model.members[g.stab]
    if not hasattr(res, "beam_end") or not res.beam_end:
        return None, ""
    d = durchbiegung(model, res, mem)
    if g.groesse in ("uy", "phiy"):
        w = d["w_y"]
    elif g.groesse == "u":
        w = np.hypot(d["w_y"], d["w_z"])
    else:
        w = d["w_z"]
    if not w.size:
        return None, ""
    j = int(np.argmax(np.abs(w)))
    return float(w[j]), f"x = {d['x'][j]:.2f} m"


def check_verformung(model: Model, analysis, progress=None) -> GZGResults:
    """Alle Verformungsnachweise des Modells fuehren."""
    out = GZGResults()
    namen = list(model.verformungsgrenzen)
    situationen = {g.situation for g in model.verformungsgrenzen.values()}
    vorrat = {s: _sls_results(model, analysis, s) for s in situationen}
    out.kombinationen = sorted({k for v in vorrat.values() for k in v})
    for i, n in enumerate(namen):
        g = model.verformungsgrenzen[n]
        out.checks[n] = check_grenze(model, g, vorrat.get(g.situation, {}))
        if progress:
            progress(f"Verformung {n} ({i + 1}/{len(namen)})")
    return out
