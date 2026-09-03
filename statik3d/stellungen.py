"""
Stellungen des Systems - bewegliche Bruecken.

Eine bewegliche Bruecke (Klapp-, Dreh-, Hub-, Faltbruecke) ist statisch nicht
ein System, sondern eine Schar von Systemen: In jeder Stellung steht das
bewegte Bauteil anders, es ist anders gelagert, und es wirken andere Lasten
(Antriebsmoment, Wind auf die aufgestellte Klappe, Verkehr nur in der
Verkehrsstellung). Massgebend ist die Umhuellende ueber alle Stellungen.

Dieses Modul bildet das ab:

    derive_model(model, stellung)   Modell in der betrachteten Stellung
                                    (Starrkoerperbewegung des bewegten Bauteils,
                                    Lager und Lastfaelle der Stellung)
    solve_stellungen(model, ...)    alle Stellungen rechnen und die Nachweise
                                    ueber die Stellungen umhuellen

Die Bewegung ist eine reine Starrkoerperbewegung der Ausgangsgeometrie; es
wird also je Stellung ein neues, geometrisch lineares System gerechnet und
nicht der Bewegungsvorgang selbst (keine Dynamik, keine Zwischenlagen ausser
den definierten Stellungen).

Grenze des Ermuedungsnachweises: Lastwechsel werden je Stellung aus den
Ermuedungslasten des Modells gebildet. Ein Lastspiel, das *ueber* zwei
Stellungen laeuft (Spannungswechsel geschlossen -> offen), entsteht dabei
nicht von selbst; dafuer ist ein Lastfallpaar innerhalb einer Stellung
anzulegen.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np

from .model import Model, Stellung
from . import solver, parallel
from .elements import beam3d as bm


# ==========================================================================
# Kinematik
# ==========================================================================
def rotation_matrix(axis_dir, angle_deg: float) -> np.ndarray:
    """Drehmatrix (3x3) um die Achsrichtung axis_dir, Winkel in Grad
    (Rechtsschraube um axis_dir, Formel von Rodrigues)."""
    a = np.asarray(axis_dir, dtype=float).ravel()
    n = np.linalg.norm(a)
    if n <= 0:
        raise ValueError("Achsrichtung ist der Nullvektor")
    a = a / n
    t = np.radians(float(angle_deg))
    c, s = np.cos(t), np.sin(t)
    K = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
    return np.eye(3) * c + s * K + (1.0 - c) * np.outer(a, a)


def moving_mask(model: Model, st: Stellung) -> np.ndarray:
    """Boolesche Maske (nn): welche Knoten bewegt diese Stellung?"""
    mask = np.zeros(model.nn, dtype=bool)
    if st.moving_groups:
        groups = set(st.moving_groups)
        for e in model.elements:
            if e.group in groups:
                for k in e.nodes:
                    if 0 <= k < model.nn:
                        mask[k] = True
    for k in st.moving_nodes:
        if 0 <= k < model.nn:
            mask[k] = True
    return mask


def transform_nodes(model: Model, st: Stellung) -> tuple[np.ndarray, np.ndarray]:
    """Knotenkoordinaten in der Stellung und die Maske der bewegten Knoten."""
    nodes = np.array(model.nodes, dtype=float, copy=True)
    mask = moving_mask(model, st)
    if not st.moves or not mask.any():
        return nodes, mask
    if st.kind == "rotate":
        R = rotation_matrix(st.axis_dir, st.angle)
        p0 = np.asarray(st.axis_point, dtype=float)
        nodes[mask] = (nodes[mask] - p0) @ R.T + p0
    elif st.kind == "translate":
        d = np.asarray(st.axis_dir, dtype=float)
        n = np.linalg.norm(d)
        if n <= 0:
            raise ValueError("Achsrichtung ist der Nullvektor")
        nodes[mask] = nodes[mask] + st.shift * d / n
    return nodes, mask


def _carry_roll(model: Model, st: Stellung, new_nodes: np.ndarray,
                mask: np.ndarray) -> dict[int, float]:
    """Querschnittslage der mitbewegten Staebe nachfuehren.

    Die lokalen Stabachsen werden aus der Stabrichtung und der globalen
    z-Achse gebildet (beam3d.local_axes). Dreht man einen Traeger als
    Starrkoerper auf, dann bleibt diese Bezugsrichtung stehen, und der Steg
    des Profils wuerde sich gegenueber dem Bauteil verdrehen - bei einer
    aufgestellten Klappe waere das grob falsch. Deshalb wird fuer jedes
    vollstaendig mitbewegte Stabelement der roll-Winkel so nachgefuehrt,
    dass die lokalen Achsen die Starrkoerperdrehung mitmachen.

    Rueckgabe: Elementnummer -> neuer roll [rad] (nur geaenderte Elemente).
    """
    if st.kind != "rotate" or not st.moves:
        return {}
    R = rotation_matrix(st.axis_dir, st.angle)
    out: dict[int, float] = {}
    for i, e in enumerate(model.elements):
        if e.typ not in ("beam", "truss") or len(e.nodes) < 2:
            continue
        if not all(0 <= k < model.nn and mask[k] for k in e.nodes[:2]):
            continue          # nur vollstaendig mitbewegte Staebe
        p1, p2 = model.nodes[e.nodes[0]], model.nodes[e.nodes[1]]
        q1, q2 = new_nodes[e.nodes[0]], new_nodes[e.nodes[1]]
        try:
            T0, _ = bm.local_axes(p1, p2, e.roll)
            Tn, _ = bm.local_axes(q1, q2, 0.0)
        except ValueError:
            continue          # Stab mit Laenge 0: unveraendert lassen
        ey_target = R @ T0[1]
        out[i] = float(np.arctan2(float(ey_target @ Tn[2]), float(ey_target @ Tn[1])))
    return out


# ==========================================================================
# Modell einer Stellung
# ==========================================================================
def derive_model(model: Model, st: Stellung, log: list = None) -> Model:
    """Das Modell, wie es in der Stellung `st` zu rechnen ist.

    * bewegtes Bauteil in die Stellung gedreht bzw. verschoben,
      Querschnittslage der mitbewegten Staebe nachgefuehrt
    * Lager der Stellung (je nach use_model_supports zusaetzlich oder statt
      der Lager des Modells), ebenso die einseitigen Lager
    * nur die in der Stellung wirkenden Lastfaelle; Kombinationen, die einen
      fehlenden Lastfall mit Faktor ungleich null enthalten, entfallen
    """
    m = model.copy()
    m.name = f"{model.name} - {st.label}"
    m.stellungen = {}
    m.active_stellung = ""

    new_nodes, mask = transform_nodes(model, st)
    m.nodes = new_nodes
    for i, roll in _carry_roll(model, st, new_nodes, mask).items():
        m.elements[i].roll = roll

    # Lagerung der Stellung
    if not st.use_model_supports:
        m.supports = []
        m.contact_supports = []
    m.supports = list(m.supports) + copy.deepcopy(st.supports)
    m.contact_supports = list(m.contact_supports) + copy.deepcopy(st.contact_supports)

    # wirkende Lastfaelle
    if st.cases:
        keep = [c for c in st.cases if c in m.load_cases]
        dropped = [k for k in m.load_cases if k not in keep]
        m.load_cases = {k: m.load_cases[k] for k in keep}
        if m.active_case not in m.load_cases:
            m.active_case = next(iter(m.load_cases), "")
        gone = []
        for name, c in list(m.combinations.items()):
            missing = [k for k, f in c.factors.items() if f and k not in m.load_cases]
            if missing:
                del m.combinations[name]
                gone.append(name)
        if log is not None:
            if dropped:
                log.append(f"{st.name}: {len(dropped)} Lastfaelle wirken nicht "
                           f"({', '.join(dropped[:6])}{' …' if len(dropped) > 6 else ''})")
            if gone:
                log.append(f"{st.name}: {len(gone)} Kombinationen entfallen "
                           f"(Lastfall wirkt in dieser Stellung nicht)")
    # Ermuedungslasten ohne Lastfall entfallen
    for name, f in list(m.fatigue_loads.items()):
        if f.case_max not in m.load_cases or (f.case_min and f.case_min not in m.load_cases):
            del m.fatigue_loads[name]
    return m


def moved_elements(model: Model, st: Stellung) -> int:
    """Anzahl der Elemente, die diese Stellung vollstaendig mitbewegt."""
    mask = moving_mask(model, st)
    if not mask.any():
        return 0
    return sum(1 for e in model.elements
               if e.nodes and all(0 <= k < model.nn and mask[k] for k in e.nodes))


# ==========================================================================
# Umhuellende ueber die Stellungen
# ==========================================================================
@dataclass
class MemberEnvelope:
    """Nachweis eines Stabes, umhuellt ueber alle gerechneten Stellungen."""
    member: str
    section: str = ""
    material: str = ""
    L: float = 0.0
    cls: int = 1
    util: float = 0.0                 # groesste Ausnutzung ueber alle Stellungen
    stellung: str = ""                # Stellung, in der sie auftritt
    governing: dict = field(default_factory=dict)
    per_stellung: dict = field(default_factory=dict)   # Stellung -> Ausnutzung
    util_fatigue: float = 0.0
    stellung_fatigue: str = ""
    fatigue_per_stellung: dict = field(default_factory=dict)

    def status(self) -> str:
        return "erfuellt" if self.util <= 1.0 else "NICHT erfuellt"


@dataclass
class StellungenAnalysis:
    """Ergebnis ueber alle Stellungen: je Stellung eine vollstaendige Analyse
    plus die Umhuellende der Nachweise."""
    model: Model
    stellungen: list = field(default_factory=list)          # Namen in Reihenfolge
    analyses: dict = field(default_factory=dict)            # Name -> solver.Analysis
    models: dict = field(default_factory=dict)              # Name -> Model der Stellung
    members: dict = field(default_factory=dict)             # Name -> MemberEnvelope
    info: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)

    @property
    def util_max(self) -> float:
        return max((m.util for m in self.members.values()), default=0.0)

    def worst(self) -> MemberEnvelope:
        return max(self.members.values(), key=lambda m: m.util, default=None)

    def angle_of(self, name: str) -> float:
        st = self.model.stellungen.get(name)
        return float(st.angle) if st is not None else 0.0

    def util_by_stellung(self) -> dict:
        """Stellung -> groesste Ausnutzung aller Staebe (Kurve ueber die Stellungen)."""
        out = {n: 0.0 for n in self.stellungen}
        for m in self.members.values():
            for n, u in m.per_stellung.items():
                out[n] = max(out.get(n, 0.0), u)
        return out

    def curve(self, member: str) -> list[tuple]:
        """(Stellung, Winkel, Ausnutzung) eines Stabes ueber die Stellungen."""
        me = self.members.get(member)
        if me is None:
            return []
        return [(n, self.angle_of(n), me.per_stellung.get(n, 0.0)) for n in self.stellungen]

    def table(self) -> list[list]:
        """Nachweistabelle wie in der Arbeitsflaeche: je Stab die massgebende
        Stellung mit dem massgebenden Nachweis."""
        rows = [["Stab", "Stellung", "massgebender Nachweis", "Ausnutzung",
                 "Kombination", "Stelle [m]", "Querschnitt", "Status"]]
        for m in sorted(self.members.values(), key=lambda x: -x.util):
            st = self.model.stellungen.get(m.stellung)
            lab = f"{m.stellung} · {st.value_text()}" if st is not None else m.stellung
            g = m.governing
            rows.append([m.member, lab, g.get("name", ""), f"{m.util:.3f}",
                         g.get("combo", ""), f"{g.get('x', 0):.2f}",
                         f"{m.section} · Kl. {m.cls}", m.status()])
        return rows

    def summary(self) -> str:
        s = [f"Stellungen: {len(self.stellungen)} gerechnet "
             f"({', '.join(self.stellungen)}), Rechenzeit {self.info.get('time', 0):.2f} s"]
        for n in self.stellungen:
            st = self.model.stellungen.get(n)
            an = self.analyses.get(n)
            u = self.util_by_stellung().get(n, 0.0)
            s.append(f"  {n:6s} {st.value_text() if st else '':>8s}  "
                     f"{len(an.combinations) if an else 0:3d} Kombinationen  "
                     f"max. Ausnutzung {u:.3f}")
        w = self.worst()
        if w is not None:
            st = self.model.stellungen.get(w.stellung)
            s.append(f"Umhuellende ueber alle Stellungen: max. Ausnutzung {w.util:.3f} "
                     f"({w.member}, Stellung {w.stellung}"
                     f"{' bei ' + st.value_text() if st else ''}, "
                     f"{w.governing.get('name', '')})")
            nf = sum(1 for m in self.members.values() if m.util > 1.0)
            s.append(f"{len(self.members)} Staebe nachgewiesen"
                     + (f" - {nf} NICHT erfuellt" if nf else " - alle erfuellt"))
        for msg in self.messages:
            s.append("Hinweis: " + msg)
        return "\n".join(s)


def _envelope_members(model: Model, sa: StellungenAnalysis):
    """Nachweise der einzelnen Stellungen zur Umhuellenden zusammenfassen."""
    for name in sa.stellungen:
        an = sa.analyses.get(name)
        if an is None or an.design is None:
            continue
        for mname, mc in an.design.members.items():
            me = sa.members.get(mname)
            if me is None:
                me = MemberEnvelope(mname, mc.section, mc.material, float(mc.L), int(mc.cls))
                sa.members[mname] = me
            me.per_stellung[name] = float(mc.util)
            if float(mc.util) >= me.util:
                me.util = float(mc.util)
                me.stellung = name
                me.governing = dict(mc.governing)
                me.section, me.material = mc.section, mc.material
                me.L, me.cls = float(mc.L), int(mc.cls)
    for name in sa.stellungen:
        an = sa.analyses.get(name)
        if an is None or an.fatigue is None:
            continue
        for mname, fm in an.fatigue.members.items():
            me = sa.members.get(mname)
            if me is None:
                me = MemberEnvelope(mname)
                sa.members[mname] = me
            u = float(getattr(fm, "util", 0.0) or 0.0)
            me.fatigue_per_stellung[name] = u
            if u >= me.util_fatigue:
                me.util_fatigue, me.stellung_fatigue = u, name


def solve_stellungen(model: Model, progress=None, design: bool = True,
                     fatigue: bool = True, workers: int = None,
                     only: list = None) -> StellungenAnalysis:
    """Alle aktiven Stellungen rechnen und die Nachweise umhuellen.

    only: Liste von Stellungsnamen (default: alle aktiven Stellungen).
    """
    t0 = time.time()
    names = list(only) if only else [s.name for s in model.active_stellungen()]
    if not names:
        raise ValueError("Keine aktive Stellung definiert")
    unknown = [n for n in names if n not in model.stellungen]
    if unknown:
        raise KeyError(f"Stellung(en) unbekannt: {', '.join(unknown)}")

    sa = StellungenAnalysis(model, stellungen=names)
    for k, name in enumerate(names, 1):
        st = model.stellungen[name]
        if progress:
            progress(f"Stellung {k}/{len(names)}: {st.label} bei {st.value_text()}")
        msgs: list[str] = []
        m = derive_model(model, st, log=msgs)
        sa.messages.extend(msgs)
        problems = [x for x in m.check() if x.startswith("FEHLER")]
        if problems:
            raise ValueError(f"Stellung '{name}' ist nicht rechenbar:\n" + "\n".join(problems))
        an = solver.solve_all(m, workers=workers, progress=progress,
                              design=design and bool(m.members),
                              fatigue=fatigue and bool(m.fatigue_loads))
        sa.models[name] = m
        sa.analyses[name] = an
        if progress:
            u = an.design.util_max if an.design is not None else 0.0
            progress(f"  {name}: max. Ausnutzung {u:.3f}")

    _envelope_members(model, sa)
    sa.info = {"time": time.time() - t0, "parallel": parallel.describe(),
               "n_stellungen": len(names),
               "n_members": len(sa.members), "util_max": sa.util_max}
    if progress:
        progress(f"Umhuellende ueber {len(names)} Stellungen: "
                 f"max. Ausnutzung {sa.util_max:.3f}")
    return sa


# ==========================================================================
# Hilfen fuer die Bedienoberflaeche
# ==========================================================================
def series(model: Model, prefix: str, start: float, end: float, steps: int,
           template: Stellung = None, kind: str = "rotate") -> list[Stellung]:
    """Stellungsserie anlegen (z.B. 0…82° in 6 Schritten).

    Die uebrigen Angaben (Drehachse, bewegtes Bauteil, Lager, Lastfaelle)
    werden aus `template` uebernommen - sonst aus der aktiven Stellung.
    """
    if steps < 2:
        raise ValueError("Eine Serie braucht mindestens 2 Schritte")
    if template is None and model.stellungen:
        template = model.stellung()
    out = []
    for i in range(steps):
        v = start + (end - start) * i / (steps - 1)
        name = f"{prefix}{i + 1}"
        kw = {}
        if template is not None:
            kw = {"axis_point": list(template.axis_point), "axis_dir": list(template.axis_dir),
                  "moving_groups": list(template.moving_groups),
                  "moving_nodes": list(template.moving_nodes),
                  "supports": copy.deepcopy(template.supports),
                  "use_model_supports": template.use_model_supports,
                  "contact_supports": copy.deepcopy(template.contact_supports),
                  "cases": list(template.cases)}
        st = model.add_stellung(name, "", kind, activate=(i == 0), **kw)
        if kind == "translate":
            st.shift = float(v)
        else:
            st.angle = float(v)
        out.append(st)
    return out
