"""
Kontakt: einseitige Lager, Knoten-Knoten-Spaltelemente, Knoten-Flaeche-Kontakt.

Formulierung: Penalty-Verfahren mit Aktiv-Mengen-Iteration.
Fuer jede Kontaktbedingung gilt der Spalt
    g(u) = g0 + c^T u
(c = Koeffizientenvektor ueber die beteiligten FHG). Ist g < 0, wird die
Steifigkeit  k_n c c^T  und die Last  -k_n g0 c  hinzugefuegt; die Kontaktkraft
ist  F_n = -k_n g >= 0.  Reibung (Coulomb): tangentiale Penalty-Steifigkeit
k_t bei Haften; bei |F_t| > mu F_n Gleiten mit konstanter Reibkraft mu F_n
entgegen der Gleitrichtung (elastisch-plastische Naeherung ohne Lastgeschichte,
geeignet fuer monoton aufgebrachte Lasten).

Die Iteration endet, wenn sich keine Kontaktzustaende (offen/Haften/Gleiten)
mehr aendern. Oszillierende Bedingungen werden nach einigen Wechseln
festgehalten (Warnung im Ergebnis).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import sparse

from .model import Model, NDOF, DOF_NAMES

PENALTY_FACTOR = 1.0e4       # automatische Kontaktsteifigkeit = Faktor * Diagonalsteifigkeit
TANGENT_FACTOR = 1.0         # k_t = TANGENT_FACTOR * k_n
SLIP_STIFFNESS = 1.0e-3      # Reststeifigkeit beim Gleiten (Regularisierung, Anteil von k_t)
SLIP_STIFFNESS_FINE = 1.0e-8  # Phase 2: haftende Nachbarn halten das Bauteil, Feder nur noch formal
SETTLE_ROUNDS = 8             # Phase 2: Nachlaufen der Normalkraefte in der Reibkraft mu*Fn
MAX_CYCLES = 40               # Phase 2: hoechstens so viele Zustandswechsel (je Runde einer)


# --------------------------------------------------------------------------
@dataclass
class Constraint:
    kind: str                      # support | gap | surface
    dofs: np.ndarray               # globale FHG
    cn: np.ndarray                 # Koeffizienten Normalrichtung (g = g0 + cn.u)
    ct: Optional[np.ndarray]       # (2, ndofs) Koeffizienten Tangentialrichtungen
    g0: float
    kn: float
    kt: float
    mu: float
    node: int
    normal: np.ndarray
    label: str = ""
    master: Optional[tuple] = None  # (Knotenliste, Gewichte)
    axes: Optional[np.ndarray] = None   # (2,3) globale Tangentialrichtungen; None = aus normal
    limit: float = 0.0             # Grenzkraft [N]/[Nm]; 0 = unbegrenzt (plastisches Fliessen)
    yielding: bool = False
    g_yield: float = 0.0
    dof: int = -1                  # Lager-FHG 0..5 bei kind 'dof'/'dof_rot'
    active: bool = False
    slip: bool = False
    slip_dir: Optional[np.ndarray] = None   # Gleitrichtung (2,) im Tangentialsystem
    dir_updates: int = 0
    Fn: float = 0.0
    Ft: np.ndarray = field(default_factory=lambda: np.zeros(2))
    g: float = 0.0
    toggles: int = 0
    frozen: bool = False


def contact_dofs(model, K=None) -> set:
    """Freiheitsgrade, die eine Kontaktbedingung halten kann.

    Sie duerfen nicht vorab gesperrt werden, auch wenn die lineare
    Steifigkeitsmatrix dort null ist: ihre Steifigkeit kommt erst aus der
    Kontaktiteration - so bei einer Schraube mit Lochspiel, deren Querhalt
    allein aus Reibung und Lochleibung stammt.

    Massgebend ist, welche Zeilen die Bedingung wirklich besetzt: die
    Normalenrichtung immer, die beiden Tangentialrichtungen nur bei Reibung.
    """
    out: set = set()
    if not getattr(model, "has_contact", False):
        return out
    if K is None:
        K = sparse.identity(model.ndof, format="csr")
    try:
        st = ContactSystem(model, K)
    except Exception:            # noqa: BLE001 - die Sperrung darf nie am Kontakt scheitern
        return out
    for c in st.cons:
        dofs = np.asarray(c.dofs, dtype=int)
        out.update(int(d) for d in dofs[np.abs(c.cn) > 1e-12])
        if c.ct is not None and c.mu > 0:
            for row in c.ct:
                out.update(int(d) for d in dofs[np.abs(row) > 1e-12])
    return out


def _group(c: "Constraint") -> str:
    return c.label.split(":")[0]


def _tangent_basis(n: np.ndarray):
    n = n / (np.linalg.norm(n) or 1.0)
    ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    t1 = np.cross(n, ref)
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    return t1, t2


def _axes_of(c: "Constraint"):
    """Globale Tangentialrichtungen (t1, t2) einer Bedingung."""
    if c.axes is not None:
        return c.axes[0], c.axes[1]
    return _tangent_basis(c.normal)


def _trans_dofs(node: int) -> list[int]:
    return [NDOF * node, NDOF * node + 1, NDOF * node + 2]


# --------------------------------------------------------------------------
# Geometrie: naechster Punkt auf Dreieck (Ericson, Real-Time Collision Detection)
# --------------------------------------------------------------------------
def closest_point_triangle(p, a, b, c):
    """Rueckgabe: naechster Punkt q auf dem Dreieck und baryzentrische Gewichte."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = ab @ ap, ac @ ap
    if d1 <= 0 and d2 <= 0:
        return a, np.array([1.0, 0, 0])
    bp = p - b
    d3, d4 = ab @ bp, ac @ bp
    if d3 >= 0 and d4 <= d3:
        return b, np.array([0, 1.0, 0])
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return a + v * ab, np.array([1 - v, v, 0])
    cp = p - c
    d5, d6 = ab @ cp, ac @ cp
    if d6 >= 0 and d5 <= d6:
        return c, np.array([0, 0, 1.0])
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return a + w * ac, np.array([1 - w, 0, w])
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return b + w * (c - b), np.array([0, 1 - w, w])
    denom = 1.0 / (va + vb + vc)
    v = vb * denom
    w = vc * denom
    return a + ab * v + ac * w, np.array([1 - v - w, v, w])


def master_facets(model: Model, cp) -> list[tuple[int, ...]]:
    """Facetten (Knotenlisten) der Master-Oberflaeche eines Kontaktpaares."""
    from .assemble import SOLID_FACES, SHELL_TYPES, SOLID_TYPES
    facets: list[tuple[int, ...]] = [tuple(int(n) for n in f) for f in cp.master_faces]
    faces: dict[tuple, tuple] = {}
    for ei in cp.master_elements:
        e = model.elements[ei]
        if e.typ in SHELL_TYPES:
            facets.append(tuple(e.nodes))
        elif e.typ in SOLID_TYPES:
            for f in SOLID_FACES[e.typ]:
                nodes = tuple(e.nodes[i] for i in f)
                key = tuple(sorted(nodes))
                if key in faces:
                    del faces[key]          # innere Flaeche
                else:
                    faces[key] = nodes
    facets.extend(faces.values())
    return facets


def _solid_outward(model: Model, cp) -> dict[tuple, np.ndarray]:
    """Fuer Volumen-Facetten: Schwerpunkt des zugehoerigen Elements (Orientierung)."""
    from .assemble import SOLID_FACES, SOLID_TYPES
    out = {}
    for ei in cp.master_elements:
        e = model.elements[ei]
        if e.typ in SOLID_TYPES:
            cen = model.nodes[e.nodes].mean(axis=0)
            for f in SOLID_FACES[e.typ]:
                out[tuple(sorted(e.nodes[i] for i in f))] = cen
    return out


# --------------------------------------------------------------------------
class ContactSystem:
    def __init__(self, model: Model, K: sparse.csr_matrix, log: list = None):
        self.model = model
        self.log = log if log is not None else []
        self.phase = 1          # 1: Aktivmenge und Gleitrichtungen, 2: monotone Nachpruefung
        self.stabilising = False   # Hilfsschritt ohne Spaltkraft (siehe stabilise)
        self.cycles = 0
        self.settle = 0
        self.dF_slip = 0.0      # groesste Aenderung von mu*Fn an gleitenden Knoten je Runde
        self.f_ref = 1.0
        self.diag = np.asarray(K.diagonal()).ravel()
        self.cons: list[Constraint] = []
        self.size = model.characteristic_size()
        self.tol = 1e-12 * self.size          # Spalt-Toleranz (Aktivierung)
        self.f_tol = 1.0                      # Kraft-Toleranz (Freigabe), wird vom Loeser gesetzt
        self._build()

    # ---- Aufbau ----------------------------------------------------------
    def _auto_k(self, nodes) -> float:
        d = []
        for n in nodes:
            d.extend(self.diag[_trans_dofs(n)])
        d = np.abs(np.asarray(d))
        ref = d.max() if d.size and d.max() > 0 else (np.abs(self.diag).max() or 1.0)
        return PENALTY_FACTOR * ref

    def _build(self):
        m = self.model
        for cs in m.contact_supports:
            n = np.asarray(cs.direction, float)
            n /= np.linalg.norm(n) or 1.0
            dofs = np.array(_trans_dofs(cs.node))
            kn = cs.stiffness if cs.stiffness > 0 else self._auto_k([cs.node])
            t1, t2 = _tangent_basis(n)
            self.cons.append(Constraint(
                "support", dofs, n.copy(), np.vstack([t1, t2]) if cs.mu > 0 else None,
                float(cs.gap), kn, TANGENT_FACTOR * kn, cs.mu, cs.node, n,
                f"Einseitiges Lager Knoten {cs.node}"))
        for ge in m.gap_elements:
            if ge.direction is not None:
                n = np.asarray(ge.direction, float)
            else:
                n = m.nodes[ge.node_b] - m.nodes[ge.node_a]
            ln = np.linalg.norm(n)
            if ln <= 0:
                self.log.append(f"Spaltelement {ge.node_a}-{ge.node_b}: Richtung unbestimmt "
                                "(Knoten fallen zusammen) - bitte 'direction' angeben")
                continue
            n = n / ln
            dofs = np.array(_trans_dofs(ge.node_a) + _trans_dofs(ge.node_b))
            cn = np.concatenate([-n, n])
            kn = ge.stiffness if ge.stiffness > 0 else self._auto_k([ge.node_a, ge.node_b])
            ct = None
            if ge.mu > 0:
                t1, t2 = _tangent_basis(n)
                ct = np.vstack([np.concatenate([-t1, t1]), np.concatenate([-t2, t2])])
            g0 = float(ge.gap)
            if ge.direction is None:
                g0 += 0.0   # Abstand ist bereits geometrisch (Knoten getrennt) -> gap zusaetzlich
            self.cons.append(Constraint("gap", dofs, cn, ct, g0, kn, TANGENT_FACTOR * kn,
                                        ge.mu, ge.node_b, n,
                                        f"Spaltelement {ge.node_a}-{ge.node_b}",
                                        master=([ge.node_a], [1.0])))
        for cp in m.contact_pairs:
            self._build_pair(cp)
        self._build_dof_supports()

    def _build_dof_supports(self):
        """Nichtlineare Lager-FHG (Ausfall bei Zug/Druck, Schlupf, Reibung, Grenzkraft)
        aus Knoten-, Linien- und Flaechenlagern in Kontaktbedingungen umsetzen."""
        from . import supports as sup
        _, nlin = sup.split(sup.expand(self.model, self.log))
        if not nlin:
            return
        by_node: dict[int, list] = {}
        for e in nlin:
            by_node.setdefault(e.node, []).append(e)
        for node, entries in sorted(by_node.items()):
            used = set()
            # 1) FHG mit Ausfall/Schlupf: eigene Bedingung, ggf. mit Reibung
            for e in entries:
                if e.mu > 0 and not e.failure and e.slip <= 0:
                    continue                     # reiner Reibungs-FHG: unten behandelt
                used.add(id(e))
                tang = [t for t in entries if t.mu > 0 and id(t) not in used
                        and (t.mu_ref is None or t.mu_ref == e.dof) and t.dof < 3]
                if e.dof >= 3:
                    tang = []                    # Rotations-FHG: keine Reibung
                for t in tang:
                    used.add(id(t))
                self._add_dof_constraint(e, tang)
            # 2) Reibungs-FHG ohne zugehoerigen Ausfall-FHG
            rest = [e for e in entries if id(e) not in used]
            for e in rest:
                self.log.append(f"{e.label} {DOF_NAMES[e.dof]}: Reibung ohne Bezugskraft "
                                f"(mu_ref) - der FHG wird starr gehalten")

    def _add_dof_constraint(self, e, tang):
        """Eine Bedingung fuer einen Lager-FHG. Vorzeichen: das Lager wirkt entlang
        +Achse; 'zug' (Ausfall bei Zug) laesst nur Druck zu (Knoten drueckt hinein),
        'druck' nur Zug. Ohne Ausfall, aber mit Schlupf entstehen zwei Bedingungen
        (beidseitiger Spalt)."""
        node, dof = e.node, e.dof
        rot = dof >= 3
        base = np.zeros(3)
        if not rot:
            base[dof] = 1.0
        kn = e.stiffness if e.stiffness > 0 else self._auto_k([node])
        dirs = []
        if e.failure == "zug":
            dirs = [+1.0]
        elif e.failure == "druck":
            dirs = [-1.0]
        else:
            dirs = [+1.0, -1.0] if e.slip > 0 else [+1.0]
        for sgn in dirs:
            dofs = [NDOF * node + dof]
            cn = np.array([sgn])
            ct = None
            axes = None
            if tang and not rot:
                rows = []
                ax = []
                for t in tang:
                    dofs.append(NDOF * node + t.dof)
                    v = np.zeros(3)
                    v[t.dof] = 1.0
                    ax.append(v)
                while len(rows) < 2:
                    row = np.zeros(len(dofs))
                    k = len(rows)
                    if k < len(tang):
                        row[1 + k] = 1.0
                    rows.append(row)
                while len(ax) < 2:
                    ax.append(np.zeros(3))
                ct = np.vstack(rows[:2])
                axes = np.vstack(ax[:2])
                cn = np.concatenate([[sgn], np.zeros(len(dofs) - 1)])
            mu = max((t.mu for t in tang), default=0.0)
            kind = "dof_rot" if rot else "dof"
            what = {"zug": "Ausfall bei Zug", "druck": "Ausfall bei Druck"}.get(
                e.failure, f"Schlupf {'+' if sgn > 0 else '-'}")
            label = f"{e.label} {DOF_NAMES[dof]} ({what})"
            self.cons.append(Constraint(
                kind, np.array(dofs), cn, ct, float(e.slip), kn, TANGENT_FACTOR * kn,
                mu, node, base * sgn, label, axes=axes, limit=float(e.limit), dof=dof))

    def _build_pair(self, cp):
        m = self.model
        facets = master_facets(m, cp)
        if not facets:
            self.log.append(f"Kontaktpaar '{cp.name}': keine Master-Facetten")
            return
        cen_of = _solid_outward(m, cp)
        radius = cp.search_radius if cp.search_radius else 0.1 * self.size
        tris = []   # (nodes(3), P(3,3), n, facet_key)
        for f in facets:
            key = tuple(sorted(f))
            if len(f) == 3:
                parts = [(f[0], f[1], f[2])]
            else:
                parts = [(f[0], f[1], f[2]), (f[0], f[2], f[3])]
            for tri in parts:
                P = m.nodes[list(tri)]
                nv = np.cross(P[1] - P[0], P[2] - P[0])
                a2 = np.linalg.norm(nv)
                if a2 <= 0:
                    continue
                nv = nv / a2
                if key in cen_of:            # Volumen: Normale nach aussen
                    if nv @ (cen_of[key] - P.mean(axis=0)) > 0:
                        nv = -nv
                tris.append((tri, P, nv, key))
        n_paired = 0
        for s in cp.slave_nodes:
            p = m.nodes[s]
            best = None
            for tri, P, nv, key in tris:
                if s in tri:
                    continue
                q, w = closest_point_triangle(p, P[0], P[1], P[2])
                dist = np.linalg.norm(p - q)
                if dist > radius:
                    continue
                if best is None or dist < best[0]:
                    best = (dist, tri, w, nv, q, key)
            if best is None:
                self.log.append(f"Kontaktpaar '{cp.name}': Knoten {s} ohne Master-Facette "
                                f"im Suchradius {radius:.3g} m")
                continue
            dist, tri, w, nv, q, key = best
            n = nv.copy()
            d = (p - q) @ n
            if cp.flip_normal:
                n = -n
                d = -d
            elif key not in cen_of and abs(d) > 1e-9 * self.size:
                # Schalen/explizite Facetten: Normale zum Slave-Knoten orientieren
                if d < 0:
                    n = -n
                    d = -d
            g0 = d - cp.gap
            dofs = np.array(_trans_dofs(s) + sum((_trans_dofs(t) for t in tri), []))
            cn = np.concatenate([n] + [-wi * n for wi in w])
            kn = cp.stiffness if cp.stiffness > 0 else self._auto_k([s])
            ct = None
            if cp.mu > 0:
                t1, t2 = _tangent_basis(n)
                ct = np.vstack([np.concatenate([t1] + [-wi * t1 for wi in w]),
                                np.concatenate([t2] + [-wi * t2 for wi in w])])
            self.cons.append(Constraint("surface", dofs, cn, ct, float(g0), kn,
                                        TANGENT_FACTOR * kn, cp.mu, s, n,
                                        f"{cp.name}: Knoten {s} -> Facette {tri}",
                                        master=(list(tri), list(w))))
            n_paired += 1
        self.log.append(f"Kontaktpaar '{cp.name}': {n_paired} von {len(cp.slave_nodes)} "
                        f"Slave-Knoten zugeordnet")

    # ---- Zustand ---------------------------------------------------------
    def initialize(self):
        """Anfangszustand: beruehrende oder durchdringende Bedingungen aktiv."""
        for c in self.cons:
            c.active = c.g0 <= self.tol
            c.slip = False
            c.slip_dir = None
            c.dir_updates = 0
            c.toggles = 0
            c.frozen = False

    @property
    def n_active(self) -> int:
        return sum(1 for c in self.cons if c.active)

    def stabilise(self) -> bool:
        """Hilfsschritt, wenn im ersten Schritt kein Halt besteht.

        Alle Bedingungen werden geschlossen, aber **ohne** die Kraft aus dem
        Spaltmass: sie wirken als reine Federn an ihrer jetzigen Lage. Der
        Loesungsschritt danach zeigt nur, wohin sich das Bauteil bewegen will;
        aus dieser Richtung wird in select_by_direction die richtige Bedingung
        gewaehlt. Das ist der Startschritt fuer eine Schraube, die erst nach
        dem Durchfahren des Lochspiels traegt.
        """
        self.stabilising = True
        changed = False
        for c in self.cons:
            if not c.active:
                c.active = True
                c.stabilised = True
                changed = True
        return changed

    def select_by_direction(self, u: np.ndarray) -> None:
        """Nach dem Hilfsschritt: nur die Bedingungen halten, auf die sich das
        Bauteil zubewegt (cn * u < 0). Die uebrigen werden wieder geoeffnet."""
        self.stabilising = False
        for c in self.cons:
            if not getattr(c, "stabilised", False):
                continue
            c.stabilised = False
            c.active = float(c.cn @ u[c.dofs]) < -1e-14

    def matrices(self, ndof: int):
        """Kontaktsteifigkeit Kc (csr) und Kontaktlastvektor Fc."""
        rows, cols, vals = [], [], []
        Fc = np.zeros(ndof)
        full_slip = self._full_slip_groups()
        for c in self.cons:
            if not c.active:
                continue
            r, cc = np.meshgrid(c.dofs, c.dofs, indexing="ij")
            if c.yielding:
                # Grenzkraft erreicht: konstante Kraft, nur Reststeifigkeit (plastisch)
                kmat = SLIP_STIFFNESS_FINE * c.kn * np.outer(c.cn, c.cn)
                Fc[c.dofs] += c.limit * c.cn
            else:
                kmat = c.kn * np.outer(c.cn, c.cn)
                if not (self.stabilising and getattr(c, "stabilised", False)):
                    Fc[c.dofs] += -c.kn * c.g0 * c.cn
            if c.ct is not None and c.mu > 0:
                if not c.slip:
                    kmat = kmat + c.kt * (np.outer(c.ct[0], c.ct[0]) + np.outer(c.ct[1], c.ct[1]))
                else:
                    # Gleiten: konstante Reibkraft mu*Fn entgegen der Gleitrichtung
                    # + Reststeifigkeit (haelt das System regulaer); in Phase 2 so klein,
                    # dass ihr Kraftanteil vernachlaessigbar ist
                    fr = c.mu * max(c.Fn, 0.0)
                    k_res = self._k_res(c, full_slip)
                    f_t = fr * c.slip_dir
                    Fc[c.dofs] += -(f_t[0] * c.ct[0] + f_t[1] * c.ct[1])
                    kmat = kmat + k_res * (np.outer(c.ct[0], c.ct[0]) + np.outer(c.ct[1], c.ct[1]))
            rows.append(r.ravel())
            cols.append(cc.ravel())
            vals.append(kmat.ravel())
        if rows:
            Kc = sparse.coo_matrix((np.concatenate(vals),
                                    (np.concatenate(rows), np.concatenate(cols))),
                                   shape=(ndof, ndof)).tocsr()
        else:
            Kc = sparse.csr_matrix((ndof, ndof))
        return Kc, Fc

    def _k_res(self, c: Constraint, full_slip: dict) -> float:
        """Reststeifigkeit eines gleitenden Knotens: grob in Phase 1 und fuer vollstaendig
        rutschende Gruppen (nur sie haelt das Bauteil), sonst in Phase 2 vernachlaessigbar
        klein, damit die Reibkraft exakt mu*Fn betraegt."""
        if self.phase == 2 and not full_slip.get(_group(c), False):
            return SLIP_STIFFNESS_FINE * c.kt
        return SLIP_STIFFNESS * c.kt

    def _full_slip_groups(self) -> dict:
        """Kontaktgruppe -> True, wenn alle aktiven Reibknoten gleiten (Bauteil rutscht;
        dann haelt nur die Reststeifigkeit, keine Fixpunkt-Korrektur)."""
        groups: dict[str, bool] = {}
        for c in self.cons:
            if c.mu > 0 and c.active and c.ct is not None:
                g = _group(c)
                groups[g] = groups.get(g, True) and c.slip
        return groups

    def set_force_scale(self, f_ref: float):
        """Bezugskraft fuer die Freigabe aktiver Bedingungen (Zugkraft > 1e-6 f_ref)."""
        self.f_tol = 1e-6 * max(abs(f_ref), 1e-30)
        self.f_ref = max(abs(f_ref), 1e-30)

    def update(self, u: np.ndarray) -> bool:
        """Zustaende aus der Loesung u aktualisieren. Rueckgabe: True, solange weiter
        iteriert werden muss.

        Phase 1 (grobe Reststeifigkeit): Aktivmenge, Haften/Gleiten und Gleitrichtungen
        wie ueblich (unterrelaxiert) bis nichts mehr wechselt.
        Phase 2 (Reststeifigkeit vernachlaessigbar): Gleitrichtungen bleiben fest; je
        Runde geht hoechstens der am staerksten ueber der Reibgrenze liegende haftende
        Knoten ins Gleiten ueber (monoton, kann nicht flattern). Ergebnis: Gleichgewicht
        exakt, |Ft| <= mu*Fn an jedem Knoten, Ft = mu*Fn an gleitenden Knoten."""
        changed = self._update_states(u)
        if self.phase == 1:
            if changed:
                return True
            full = self._full_slip_groups()
            if any(c.active and c.slip and not full.get(_group(c), False) for c in self.cons):
                self.phase = 2
                self.cycles = 0
                return True
            return False
        if not changed:
            # Setzrunden: die konstante Reibkraft mu*Fn wurde mit der Normalkraft der
            # vorigen Runde aufgestellt - solange sie sich merklich aendert, nachrechnen
            if self.dF_slip > 1e-4 * self.f_ref and self.settle < SETTLE_ROUNDS:
                self.settle += 1
                return True
            return False
        self.cycles += 1
        if self.cycles >= MAX_CYCLES:
            self.log.append("Kontakt: Nachpruefung der Reibung nach "
                            f"{MAX_CYCLES} Zustandswechseln abgebrochen")
            return False
        return True

    def _update_states(self, u: np.ndarray) -> bool:
        changed = False
        worst = None            # Phase 2: (Verhaeltnis, Bedingung, dt) des staerksten Verstosses
        self.dF_slip = 0.0
        for c in self.cons:
            ue = u[c.dofs]
            g = c.g0 + c.cn @ ue
            c.g = g
            if c.active:
                Fn = c.limit if c.yielding else -c.kn * g
                if c.slip:
                    self.dF_slip = max(self.dF_slip, c.mu * abs(max(Fn, 0.0) - c.Fn))
                new_active = Fn > -self.f_tol   # Druckkraft (bzw. winziger Zug) -> bleibt
                c.Fn = max(Fn, 0.0)
                if c.limit > 0:
                    if not c.yielding and new_active and -c.kn * g > c.limit:
                        c.yielding = True       # Grenzkraft erreicht -> plastisch
                        c.g_yield = g
                        changed = True
                    elif c.yielding and g > c.g_yield + self.tol:
                        c.yielding = False      # Entlastung -> wieder elastisch
                        changed = True
            else:
                c.Fn = 0.0
                new_active = g < -self.tol
            if c.frozen:
                new_active = c.active
            if new_active != c.active:
                c.toggles += 1
                if c.toggles > 8:
                    c.frozen = True
                    new_active = True
                    self.log.append(f"{c.label}: Zustand oszilliert, wird als aktiv gehalten")
                c.active = new_active
                changed = True
                if not c.active:
                    c.slip = False
                    c.slip_dir = None
                    c.yielding = False
                    c.Ft[:] = 0
            if c.active and c.ct is not None and c.mu > 0:
                dt = np.array([c.ct[0] @ ue, c.ct[1] @ ue])
                Ft_el = c.kt * dt
                limit = c.mu * c.Fn
                nrm = np.linalg.norm(dt)
                if not c.slip:
                    c.Ft = Ft_el
                    if np.linalg.norm(Ft_el) > limit * (1 + 1e-6) and limit >= 0:
                        if self.phase == 1:
                            c.slip = True
                            c.slip_dir = dt / nrm if nrm > 0 else np.array([1.0, 0.0])
                            c.dir_updates = 0
                            c.Ft = limit * c.slip_dir
                            changed = True
                        else:
                            ratio = np.linalg.norm(Ft_el) / limit if limit > 0 else np.inf
                            if worst is None or ratio > worst[0]:
                                worst = (ratio, c, dt)
                elif self.phase == 1:
                    if nrm > 0 and (dt @ c.slip_dir) < 0:
                        # Bewegung entgegen Gleitrichtung -> wieder Haften
                        c.slip = False
                        c.slip_dir = None
                        c.Ft = np.zeros(2)
                        changed = True
                    else:
                        if nrm > 0 and c.dir_updates < 12:
                            # Gleitrichtung unterrelaxiert nachfuehren (Fixpunkt-Iteration);
                            # nach 12 Anpassungen wird die Richtung festgehalten
                            nd = dt / nrm
                            blend = 0.5 * c.slip_dir + 0.5 * nd
                            bn = np.linalg.norm(blend)
                            blend = blend / bn if bn > 0 else nd
                            if np.linalg.norm(blend - c.slip_dir) > 0.05:   # ~3 Grad
                                c.slip_dir = blend
                                c.dir_updates += 1
                                changed = True
                        c.Ft = limit * c.slip_dir
                else:
                    c.Ft = limit * c.slip_dir      # Phase 2: Gleiten bleibt, Richtung fest
            elif not c.active:
                c.Ft = np.zeros(2)
        # Phase 2: je Runde nur der staerkste Verstoss Haften -> Gleiten (monoton)
        if worst is not None:
            ratio, c, dt = worst
            nrm = np.linalg.norm(dt)
            c.slip = True
            c.slip_dir = dt / nrm if nrm > 0 else np.array([1.0, 0.0])
            c.dir_updates = 0
            c.Ft = c.mu * c.Fn * c.slip_dir
            changed = True
        return changed

    # ---- Ergebnisse --------------------------------------------------------
    def warnings(self) -> list[str]:
        """Hinweise: vollstaendig gleitende Kontaktpaare (Gleichgewicht nur durch
        Reststeifigkeit) und eingefrorene Bedingungen."""
        out = []
        groups: dict[str, list[Constraint]] = {}
        for c in self.cons:
            if c.mu > 0:
                groups.setdefault(c.label.split(":")[0], []).append(c)
        for name, cs in groups.items():
            act = [c for c in cs if c.active]
            if act and all(c.slip for c in act):
                out.append(f"{name}: alle aktiven Kontaktknoten gleiten - Reibung reicht "
                           "nicht fuer das Gleichgewicht (Bauteil rutscht; nahe der "
                           "Reibkapazitaet mu*N urteilt das Verfahren konservativ)")
        return out

    def results(self) -> list[dict]:
        out = []
        for c in self.cons:
            if not c.active:
                status = "offen"
            elif c.yielding:
                status = "Fliessen"
            elif c.mu > 0 and c.slip:
                status = "Gleiten"
            elif c.mu > 0:
                status = "Haften"
            else:
                status = "Kontakt"
            out.append({"kind": c.kind, "label": c.label, "node": int(c.node),
                        "master": c.master, "gap": float(c.g), "Fn": float(c.Fn),
                        "Ft": float(np.linalg.norm(c.Ft)), "status": status,
                        "normal": c.normal.tolist(), "frozen": c.frozen,
                        "dof": int(c.dof), "limit": float(c.limit)})
        return out

    def nodal_forces(self, nn: int) -> np.ndarray:
        """Kontaktkraefte auf die Knoten (nn,3), global."""
        F = np.zeros((nn, 3))
        for c in self.cons:
            if not c.active or c.kind == "dof_rot":
                continue
            f = c.Fn * c.normal
            if c.ct is not None:
                t1, t2 = _axes_of(c)
                f = f - (c.Ft[0] * t1 + c.Ft[1] * t2)
            if c.kind in ("support", "dof"):
                F[c.node] += f
            elif c.kind == "gap":
                F[c.node] += f
                F[c.master[0][0]] -= f
            else:
                F[c.node] += f
                for nd, w in zip(*c.master):
                    F[nd] -= w * f
        return F

    def support_reactions(self, nn: int) -> np.ndarray:
        """Nur einseitige Lager (fuer die Auflagerkraftsumme)."""
        R = np.zeros((nn, 3))
        for c in self.cons:
            if c.active and c.kind in ("support", "dof"):
                f = c.Fn * c.normal
                if c.ct is not None:
                    t1, t2 = _axes_of(c)
                    f = f - (c.Ft[0] * t1 + c.Ft[1] * t2)
                R[c.node] += f
        return R


def summary(results: list[dict]) -> str:
    if not results:
        return "keine Kontaktbedingungen"
    n_act = sum(1 for r in results if r["status"] != "offen")
    n_slip = sum(1 for r in results if r["status"] == "Gleiten")
    fmax = max((r["Fn"] for r in results), default=0.0)
    return (f"Kontakt: {n_act} von {len(results)} Bedingungen aktiv"
            + (f", {n_slip} gleitend" if n_slip else "")
            + f", max. Kontaktkraft {fmax/1e3:.2f} kN")
