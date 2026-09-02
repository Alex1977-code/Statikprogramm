"""
Datenmodell fuer Statik3D.

Einheiten (konsistent, SI):
    Laenge  m
    Kraft   N
    Spannung Pa (N/m^2)
    Dichte  kg/m^3

Freiheitsgrade pro Knoten (immer 6, ungenutzte werden automatisch gesperrt):
    0 ux, 1 uy, 2 uz, 3 rx, 4 ry, 5 rz
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

DOF_NAMES = ["ux", "uy", "uz", "rx", "ry", "rz"]
NDOF = 6


# --------------------------------------------------------------------------
# Material / Querschnitt
# --------------------------------------------------------------------------
@dataclass
class Material:
    name: str
    E: float = 210e9          # Elastizitaetsmodul [Pa]
    nu: float = 0.3           # Querdehnzahl [-]
    rho: float = 7850.0       # Dichte [kg/m^3]
    alpha: float = 1.2e-5     # Waermeausdehnung [1/K]
    fy: Optional[float] = None  # Streckgrenze [Pa], nur fuer Ausnutzungsgrad

    @property
    def G(self) -> float:
        return self.E / (2.0 * (1.0 + self.nu))


@dataclass
class Section:
    """Stabquerschnitt. Lokale Achsen: x = Stabachse, y/z = Hauptachsen."""
    name: str
    A: float = 1e-2           # Flaeche [m^2]
    Iy: float = 1e-5          # Traegheitsmoment um lokale y (Biegung in x-z) [m^4]
    Iz: float = 1e-5          # Traegheitsmoment um lokale z (Biegung in x-y) [m^4]
    It: float = 1e-5          # Torsionstraegheitsmoment [m^4]
    Asy: float = 0.0          # Schubflaeche in y (0 = Schubstarr / Bernoulli)
    Asz: float = 0.0          # Schubflaeche in z
    # Randabstaende fuer Spannungsnachweis [m]
    zmax: float = 0.0
    ymax: float = 0.0

    @staticmethod
    def rectangle(name: str, b: float, h: float) -> "Section":
        a = min(b, h)
        c = max(b, h)
        beta = 1.0 / 3.0 - 0.21 * (a / c) * (1 - (a / c) ** 4 / 12.0)
        return Section(
            name=name, A=b * h,
            Iy=b * h ** 3 / 12.0, Iz=h * b ** 3 / 12.0,
            It=beta * c * a ** 3,
            Asy=5.0 / 6.0 * b * h, Asz=5.0 / 6.0 * b * h,
            zmax=h / 2.0, ymax=b / 2.0,
        )

    @staticmethod
    def circle(name: str, d: float) -> "Section":
        A = np.pi * d ** 2 / 4.0
        I = np.pi * d ** 4 / 64.0
        return Section(name, A=A, Iy=I, Iz=I, It=2 * I,
                       Asy=0.9 * A, Asz=0.9 * A, zmax=d / 2, ymax=d / 2)

    @staticmethod
    def pipe(name: str, d: float, t: float) -> "Section":
        di = d - 2 * t
        A = np.pi * (d ** 2 - di ** 2) / 4.0
        I = np.pi * (d ** 4 - di ** 4) / 64.0
        return Section(name, A=A, Iy=I, Iz=I, It=2 * I,
                       Asy=0.5 * A, Asz=0.5 * A, zmax=d / 2, ymax=d / 2)

    @staticmethod
    def i_profile(name: str, h: float, b: float, tw: float, tf: float) -> "Section":
        """Doppel-T (I/H) mit Steghoehe h, Flanschbreite b."""
        hw = h - 2 * tf
        A = 2 * b * tf + hw * tw
        Iy = (b * h ** 3 - (b - tw) * hw ** 3) / 12.0
        Iz = (2 * tf * b ** 3 + hw * tw ** 3) / 12.0
        It = (2 * b * tf ** 3 + hw * tw ** 3) / 3.0
        return Section(name, A=A, Iy=Iy, Iz=Iz, It=It,
                       Asy=hw * tw, Asz=2 * b * tf,
                       zmax=h / 2, ymax=b / 2)


@dataclass
class ShellProp:
    """Eigenschaften eines Flaechenelements."""
    name: str
    t: float = 0.01           # Dicke [m]


# --------------------------------------------------------------------------
# Elemente
# --------------------------------------------------------------------------
@dataclass
class Element:
    """
    typ:  'beam'   2 Knoten,  Balken/Stab 3D (12 FHG)
          'truss'  2 Knoten,  Fachwerkstab (nur Normalkraft)
          'shell3' 3 Knoten,  ebenes Schalenelement (CST + DKT)
          'shell4' 4 Knoten,  in 2 shell3 zerlegt
          'tet4'   4 Knoten,  linearer Tetraeder
          'tet10' 10 Knoten,  quadratischer Tetraeder
          'hex8'   8 Knoten,  Trilinearer Hexaeder
    """
    typ: str
    nodes: list[int]
    mat: str
    sec: Optional[str] = None       # Section-Name (beam/truss) oder ShellProp (shell)
    roll: float = 0.0               # Verdrehung der lokalen Achsen [rad], nur Stab
    group: str = "default"


@dataclass
class Support:
    node: int
    dofs: list[int]                 # gesperrte FHG-Indizes 0..5
    values: Optional[list[float]] = None   # vorgegebene Verschiebungen (default 0)
    stiffness: Optional[list[float]] = None  # optional Federsteifigkeiten statt starr


@dataclass
class NodalLoad:
    node: int
    F: list[float] = field(default_factory=lambda: [0.0] * 6)  # Fx Fy Fz Mx My Mz


@dataclass
class BeamLoad:
    """Gleichstreckenlast auf Stabelement.
    system: 'global' (auf projizierte Laenge nein - auf wahre Laenge) oder 'local'.
    """
    elem: int
    q: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # qx qy qz [N/m]
    system: str = "global"


@dataclass
class FaceLoad:
    """Flaechenlast (Druck) auf Schalen- oder Volumen-Oberflaeche.
    Bei Schalen: p wirkt in lokale z-Richtung (+ = in Normalenrichtung).
    Bei Volumen: face = lokale Flaechennummer, p in Normalenrichtung (+ = Druck nach innen).
    """
    elem: int
    p: float = 0.0
    face: int = 0


# --------------------------------------------------------------------------
# Gesamtmodell
# --------------------------------------------------------------------------
class Model:
    def __init__(self, name: str = "Modell"):
        self.name = name
        self.nodes: np.ndarray = np.zeros((0, 3))
        self.elements: list[Element] = []
        self.materials: dict[str, Material] = {}
        self.sections: dict[str, Section] = {}
        self.shells: dict[str, ShellProp] = {}
        self.supports: list[Support] = []
        self.nodal_loads: list[NodalLoad] = []
        self.beam_loads: list[BeamLoad] = []
        self.face_loads: list[FaceLoad] = []
        self.gravity: np.ndarray = np.zeros(3)   # z.B. [0,0,-9.81]

    # ---------------- Aufbau ----------------
    def add_node(self, x: float, y: float, z: float) -> int:
        self.nodes = np.vstack([self.nodes, [x, y, z]])
        return len(self.nodes) - 1

    def add_nodes(self, coords) -> np.ndarray:
        coords = np.asarray(coords, dtype=float).reshape(-1, 3)
        i0 = len(self.nodes)
        self.nodes = np.vstack([self.nodes, coords])
        return np.arange(i0, len(self.nodes))

    def add_material(self, m: Material) -> Material:
        self.materials[m.name] = m
        return m

    def add_section(self, s: Section) -> Section:
        self.sections[s.name] = s
        return s

    def add_shell_prop(self, s: ShellProp) -> ShellProp:
        self.shells[s.name] = s
        return s

    def add_element(self, typ: str, nodes, mat: str, sec: str = None,
                    roll: float = 0.0, group: str = "default") -> int:
        self.elements.append(Element(typ, [int(n) for n in nodes], mat, sec, roll, group))
        return len(self.elements) - 1

    def add_elements(self, typ: str, conn, mat: str, sec: str = None,
                     group: str = "default") -> list[int]:
        ids = []
        for row in np.asarray(conn):
            ids.append(self.add_element(typ, row, mat, sec, group=group))
        return ids

    def fix(self, node: int, dofs="all", values=None):
        if dofs == "all":
            dofs = [0, 1, 2, 3, 4, 5]
        elif dofs == "pinned":
            dofs = [0, 1, 2]
        self.supports.append(Support(int(node), list(dofs),
                                     list(values) if values is not None else None))

    def load_node(self, node: int, Fx=0.0, Fy=0.0, Fz=0.0, Mx=0.0, My=0.0, Mz=0.0):
        self.nodal_loads.append(NodalLoad(int(node), [Fx, Fy, Fz, Mx, My, Mz]))

    def load_beam(self, elem: int, qx=0.0, qy=0.0, qz=0.0, system="global"):
        self.beam_loads.append(BeamLoad(int(elem), [qx, qy, qz], system))

    def load_face(self, elem: int, p: float, face: int = 0):
        self.face_loads.append(FaceLoad(int(elem), p, face))

    def set_gravity(self, gz: float = -9.81):
        self.gravity = np.array([0.0, 0.0, gz])

    # ---------------- Hilfen ----------------
    @property
    def nn(self) -> int:
        return len(self.nodes)

    @property
    def ndof(self) -> int:
        return self.nn * NDOF

    def element_nodes(self, e: Element) -> np.ndarray:
        return self.nodes[e.nodes]

    def bbox(self):
        if self.nn == 0:
            return np.zeros(3), np.ones(3)
        return self.nodes.min(axis=0), self.nodes.max(axis=0)

    def characteristic_size(self) -> float:
        lo, hi = self.bbox()
        d = float(np.linalg.norm(hi - lo))
        return d if d > 0 else 1.0

    def check(self) -> list[str]:
        """Einfache Modellpruefung. Gibt Liste von Warnungen/Fehlern zurueck."""
        msgs = []
        if self.nn == 0:
            msgs.append("FEHLER: keine Knoten definiert")
        if not self.elements:
            msgs.append("FEHLER: keine Elemente definiert")
        if not self.supports:
            msgs.append("FEHLER: keine Lagerung definiert (System kinematisch)")
        used = np.zeros(self.nn, dtype=bool)
        for i, e in enumerate(self.elements):
            if e.mat not in self.materials:
                msgs.append(f"FEHLER: Element {i}: Material '{e.mat}' unbekannt")
            if e.typ in ("beam", "truss") and e.sec not in self.sections:
                msgs.append(f"FEHLER: Element {i}: Querschnitt '{e.sec}' unbekannt")
            if e.typ in ("shell3", "shell4") and e.sec not in self.shells:
                msgs.append(f"FEHLER: Element {i}: Schalendicke '{e.sec}' unbekannt")
            for n in e.nodes:
                if n < 0 or n >= self.nn:
                    msgs.append(f"FEHLER: Element {i}: Knoten {n} existiert nicht")
                else:
                    used[n] = True
        free = np.where(~used)[0]
        if len(free):
            msgs.append(f"WARNUNG: {len(free)} Knoten ohne Elementanschluss")
        return msgs

    # ---------------- Speichern / Laden ----------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "nodes": self.nodes.tolist(),
            "elements": [asdict(e) for e in self.elements],
            "materials": {k: asdict(v) for k, v in self.materials.items()},
            "sections": {k: asdict(v) for k, v in self.sections.items()},
            "shells": {k: asdict(v) for k, v in self.shells.items()},
            "supports": [asdict(s) for s in self.supports],
            "nodal_loads": [asdict(l) for l in self.nodal_loads],
            "beam_loads": [asdict(l) for l in self.beam_loads],
            "face_loads": [asdict(l) for l in self.face_loads],
            "gravity": self.gravity.tolist(),
        }

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1)

    @staticmethod
    def load(path: str) -> "Model":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        m = Model(d.get("name", "Modell"))
        m.nodes = np.asarray(d["nodes"], dtype=float).reshape(-1, 3)
        m.elements = [Element(**e) for e in d["elements"]]
        m.materials = {k: Material(**v) for k, v in d["materials"].items()}
        m.sections = {k: Section(**v) for k, v in d["sections"].items()}
        m.shells = {k: ShellProp(**v) for k, v in d.get("shells", {}).items()}
        m.supports = [Support(**s) for s in d["supports"]]
        m.nodal_loads = [NodalLoad(**l) for l in d["nodal_loads"]]
        m.beam_loads = [BeamLoad(**l) for l in d["beam_loads"]]
        m.face_loads = [FaceLoad(**l) for l in d.get("face_loads", [])]
        m.gravity = np.asarray(d.get("gravity", [0, 0, 0]), dtype=float)
        return m
