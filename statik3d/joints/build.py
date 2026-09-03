"""
Bausteine fuer Anschlussmodelle: Bleche, Schrauben, Kontakt, Naehte.

Die Schraube wird bewusst einfach und trotzdem wirklichkeitsnah abgebildet -
mit denselben Mitteln, die im Programm bereits geprueft sind:

    Schaft         Fachwerkstab zwischen den Blechen, EA/L_k des
                   Spannungsquerschnitts. Er nimmt Zug auf.
    Vorspannung    Temperaturlast auf den Schaft: dT = -F_p,C/(E A alpha).
                   Der Stab verkuerzt sich und presst die Bleche zusammen -
                   die Klemmkraft baut sich ab, sobald aeussere Zugkraft
                   dazukommt, genau wie in Wirklichkeit.
    Trennfuge      Spaltelemente zwischen den gegenueberliegenden
                   Blechknoten: nur Druck, mit Reibbeiwert mu. Daraus ergibt
                   sich die Gleitfestigkeit von selbst.
    Lochspiel      zwei gegenlaeufige Spaltelemente je Querrichtung mit dem
                   halben Lochspiel als Spalt. Die Bleche koennen sich um das
                   Lochspiel verschieben, danach traegt der Schaft.
                   Passschraube: Spiel 0,3 mm, Langloch entsprechend groesser.

Damit ergeben sich Abheben, Abstuetzkraefte (Prying), Gleiten und Lochleibung
aus der Rechnung statt aus einer Annahme.

    from statik3d.joints.build import plate_shells, add_bolt, contact_layer
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..model import Model, Material, ShellProp
from .bolts import Bolt


def _axes(normal, ref=None):
    """Rechtwinkliges Dreibein zu einer Normalen. Rueckgabe: (ex, ey, n)."""
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    r = np.asarray(ref, float) if ref is not None else None
    if r is None or abs(float(np.dot(r / np.linalg.norm(r), n))) > 0.99:
        r = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    ex = r - np.dot(r, n) * n
    ex = ex / np.linalg.norm(ex)
    ey = np.cross(n, ex)
    return ex, ey, n


def plate_shells(model: Model, origin, normal, width: float, height: float,
                 t: float, mat: str, nx: int = 8, ny: int = 8, ref=None,
                 prop: str = None, group: str = "blech") -> np.ndarray:
    """Rechteckiges Blech als Schalennetz. Rueckgabe: Knotengitter (nx+1, ny+1).

    origin liegt in der Mitte des Blechs; die Ebene wird durch die Normale
    aufgespannt, width laeuft in ex, height in ey.
    """
    ex, ey, _n = _axes(normal, ref)
    o = np.asarray(origin, float)
    prop = prop or f"t{t * 1e3:g}"
    if prop not in model.shells:
        model.add_shell_prop(ShellProp(prop, float(t)))
    ids = np.zeros((nx + 1, ny + 1), dtype=int)
    for i in range(nx + 1):
        u = (i / nx - 0.5) * width
        for j in range(ny + 1):
            v = (j / ny - 0.5) * height
            p = o + u * ex + v * ey
            ids[i, j] = model.add_node(*p)
    for i in range(nx):
        for j in range(ny):
            model.add_element("shell4", [ids[i, j], ids[i + 1, j],
                                         ids[i + 1, j + 1], ids[i, j + 1]],
                              mat, prop, group=group)
    return ids


def plate_solid(model: Model, origin, normal, width: float, height: float,
                t: float, mat: str, nx: int = 8, ny: int = 8, nz: int = 2,
                ref=None, group: str = "blech") -> np.ndarray:
    """Rechteckiges Blech als Volumennetz (hex8). Rueckgabe: (nx+1, ny+1, nz+1).

    Die Dicke laeuft in Richtung der Normalen, origin liegt in der Mitte der
    Blechebene auf der Rueckseite (Schicht k = 0).
    """
    ex, ey, n = _axes(normal, ref)
    o = np.asarray(origin, float)
    ids = np.zeros((nx + 1, ny + 1, nz + 1), dtype=int)
    for i in range(nx + 1):
        u = (i / nx - 0.5) * width
        for j in range(ny + 1):
            v = (j / ny - 0.5) * height
            for k in range(nz + 1):
                p = o + u * ex + v * ey + (k / nz) * t * n
                ids[i, j, k] = model.add_node(*p)
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                c = [ids[i, j, k], ids[i + 1, j, k], ids[i + 1, j + 1, k], ids[i, j + 1, k],
                     ids[i, j, k + 1], ids[i + 1, j, k + 1], ids[i + 1, j + 1, k + 1],
                     ids[i, j + 1, k + 1]]
                model.add_element("hex8", c, mat, group=group)
    return ids


def nearest_node(model: Model, point, nodes=None) -> int:
    """Knoten, der einem Punkt am naechsten liegt."""
    p = np.asarray(point, float)
    idx = np.asarray(nodes, dtype=int) if nodes is not None else np.arange(model.nn)
    d = np.linalg.norm(model.nodes[idx] - p, axis=1)
    return int(idx[int(np.argmin(d))])


@dataclass
class BoltInstance:
    """Eine eingebaute Schraube mit ihren Modellbestandteilen."""
    bolt: Bolt
    node_a: int
    node_b: int
    element: int                       # Schaft (Fachwerkstab)
    gaps: list = field(default_factory=list)     # Spaltelemente Lochspiel
    grip: float = 0.0
    material: str = ""
    section: str = ""
    preload: float = 0.0

    def describe(self) -> str:
        return (f"{self.bolt.describe()}, Klemmlaenge {self.grip * 1e3:.0f} mm"
                + (f", Vorspannung {self.preload / 1e3:.0f} kN" if self.preload else ""))


def add_bolt(model: Model, node_a: int, node_b: int, bolt: Bolt,
             case: str = None, shear: str = "lochleibung",
             log: list = None) -> BoltInstance:
    """Schraube zwischen zwei Knoten einbauen.

    Der Schaft laeuft mit dem Spannungsquerschnitt A_s ueber die Klemmlaenge.
    Ist die Schraube vorgespannt, wird F_p,C als Temperaturlast aufgebracht;
    die Klemmkraft baut sich unter aeusserer Zugkraft ab wie in Wirklichkeit.

    shear bestimmt, wie die Querkraft uebertragen wird:

      "lochleibung"  Regelfall. Der Schaft ist ein Balken und traegt die
                     Querkraft unmittelbar (Lochleibung). Das ist das
                     Bemessungsmodell der Kategorie A und der Zustand nach dem
                     Gleiten bei Kategorie B/C. Ist die Schraube vorgespannt,
                     traegt zusaetzlich die Reibung der Trennfuge, bis sie mit
                     mu*N erschoepft ist.
      "spiel"        Der Schaft ist ein Fachwerkstab; je Querrichtung kommen
                     zwei gegenlaeufige Spaltelemente mit dem halben Lochspiel
                     dazu. Damit wird das Durchfahren des Lochspiels
                     abgebildet. Vorsicht: ohne Reibung oder anderen Querhalt
                     ist die Verbindung waehrend des Gleitens frei
                     verschieblich; das Programm sagt das dann ausdruecklich.
      "keine"        Nur Zug, keine Querkopplung (z. B. Ankerschraube).
    """
    if shear is True:
        shear = "spiel"
    elif shear is False:
        shear = "keine"
    if shear not in ("lochleibung", "spiel", "keine"):
        raise ValueError("shear muss 'lochleibung', 'spiel' oder 'keine' sein")
    pa = model.nodes[node_a]
    pb = model.nodes[node_b]
    axis = np.asarray(pb, float) - np.asarray(pa, float)
    grip = float(np.linalg.norm(axis))
    if grip <= 0:
        raise ValueError("Schraubenknoten fallen zusammen - Klemmlaenge ist null.")
    axis = axis / grip
    matname = f"Schraube {bolt.grade}"
    if matname not in model.materials:
        model.add_material(Material(matname, E=210e9, nu=0.3, rho=7850.0,
                                    alpha=1.2e-5, fy=bolt.fyb, fu=bolt.fub,
                                    grade=""))
    secname = f"{bolt.size} Schaft"
    if secname not in model.sections:
        from ..model import Section
        d = math.sqrt(4.0 * bolt.As / math.pi)      # Ersatzdurchmesser zu A_s
        sec = Section.circle(secname, d)
        sec.A = bolt.As              # Spannungsquerschnitt statt Kreisflaeche
        model.add_section(sec)
    typ = "beam" if shear == "lochleibung" else "truss"
    e = model.add_element(typ, [node_a, node_b], matname, secname, group="schraube")
    inst = BoltInstance(bolt=bolt, node_a=node_a, node_b=node_b, element=e,
                        grip=grip, material=matname, section=secname)
    if bolt.preloaded and bolt.Fp_C > 0:
        mat = model.materials[matname]
        dT = -bolt.Fp_C / (mat.E * bolt.As * mat.alpha)
        model.load_temp(e, dT, case=case)
        inst.preload = bolt.Fp_C
    if shear == "spiel":
        ex, ey, _n = _axes(axis)
        s = 0.5 * bolt.clearance
        for direction in (ex, -ex, ey, -ey):
            g = model.add_gap_element(node_a, node_b, direction=list(direction),
                                      gap=s, group="lochspiel")
            inst.gaps.append(g)
    if log is not None:
        log.append("  " + inst.describe())
    return inst


def contact_layer(model: Model, nodes_a, nodes_b, mu: float = 0.0,
                  gap: float = 0.0, group: str = "trennfuge") -> list:
    """Trennfuge zwischen zwei Blechen: nur Druck, mit Reibung.

    nodes_a und nodes_b sind gleich lange Listen einander gegenueberliegender
    Knoten. Jedes Paar bekommt ein Spaltelement; die Richtung folgt aus der
    Geometrie.
    """
    out = []
    for a, b in zip(np.ravel(nodes_a), np.ravel(nodes_b)):
        a, b = int(a), int(b)
        if a == b:
            continue
        out.append(model.add_gap_element(a, b, gap=gap, mu=mu, group=group))
    return out


def weld_couple(model: Model, nodes_a, nodes_b, log: list = None) -> int:
    """Schweissnaht als starre Kopplung: die Knotenpaare werden verschmolzen.

    Die Naht selbst wird nicht als Volumen abgebildet; ihre Tragfaehigkeit wird
    nach EN 1993-1-8 aus den uebertragenen Schnittgroessen nachgewiesen
    (siehe joints/design.py). Rueckgabe: Anzahl verschmolzener Paare.
    """
    from ..importers import _common as C
    pairs = 0
    for a, b in zip(np.ravel(nodes_a), np.ravel(nodes_b)):
        a, b = int(a), int(b)
        if a == b:
            continue
        model.nodes[b] = model.nodes[a]
        pairs += 1
    if pairs:
        C.merge_duplicate_nodes(model)
    if log is not None:
        log.append(f"  Schweissnaht: {pairs} Knotenpaare starr verbunden")
    return pairs


def rigid_fan(model: Model, center: int, ring, mat: str, sec: str,
              group: str = "kopplung") -> list[int]:
    """Sternfoermige starre Kopplung: Balken vom Mittelknoten zu jedem Ringknoten.

    Damit wird eine Stabkraft in ein Schalen- oder Volumennetz eingeleitet,
    ohne die Lasteinleitung kuenstlich zu versteifen.
    """
    out = []
    for n in np.ravel(ring):
        n = int(n)
        if n != int(center):
            out.append(model.add_element("beam", [int(center), n], mat, sec, group=group))
    return out


def stiff_section(model: Model, name: str = "Kopplung", d: float = 0.05):
    """Sehr steifer Ersatzquerschnitt fuer starre Kopplungen."""
    from ..model import Section
    if name not in model.sections:
        s = Section.circle(name, d)
        s.A *= 100.0
        s.Iy *= 100.0
        s.Iz *= 100.0
        s.It *= 100.0
        model.add_section(s)
    return name
