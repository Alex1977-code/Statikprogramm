"""
Anschlussvorlagen: Typ waehlen, Stabende anklicken, fertig.

Jede Vorlage schlaegt aus dem Profil und den Schnittgroessen eine vollstaendige
Geometrie vor - Blechdicken, Schraubenbild, Nahtdicken -, die anschliessend
geaendert werden kann. Aus derselben Beschreibung entstehen das FE-Modell
(Schalen oder Volumen) und die Nachweise.

    Kopfplatte    Stirnplatte am Stabende, geschraubt, mit Steifen und Rippen
    Lasche        Laschenstoss mit Flansch- und Steglaschen
    Diagonale     Knotenblech (Gusset) fuer Streben und Verbaende

    from statik3d.joints.templates import EndPlate
    a = EndPlate.propose(model, elem=12, end=1, N=-250e3, Vz=80e3, My=120e3)
    print(a.describe())
    teil = a.build(kind="2d")        # FE-Modell des Anschlusses
    print(a.design(N=-250e3, Vz=80e3, My=120e3).report())

Alle Vorschlaege folgen den Regeln der EN 1993-1-8: Rand- und Lochabstaende
nach Tab. 3.3, Nahtdicken nach 4.5.1, Blechdicken so, dass der T-Stummel nicht
im Modus 1 versagt. Sie sind ein Vorschlag, kein Nachweis - massgebend ist
immer die Rechnung.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..model import Model, Material, Section, ShellProp
from .bolts import Bolt, BoltGeometry, min_spacing, check_spacing
from .welds import Fillet, min_throat, max_throat
from .tstub import TStub, effective_lengths
from .design import (Check, JointCheck, check_bolt, check_weld, check_net_section,
                     check_block_tearing, fatigue_check)
from . import build as B

#: Vorlagen: Schluessel -> (Klassenname, Beschreibung)
TYPES = {
    "kopfplatte": ("EndPlate", "Kopfplatte / Stirnplatte am Stabende, geschraubt"),
    "lasche": ("Splice", "Laschenstoss mit Flansch- und Steglaschen"),
    "diagonale": ("Gusset", "Diagonalanschluss ueber ein Knotenblech"),
}

#: uebliche Schraubengroessen fuer den Vorschlag, aufsteigend
BOLT_LADDER = ["M12", "M16", "M20", "M24", "M27", "M30", "M36"]


def _section_of(model: Model, elem: int) -> Section:
    e = model.elements[int(elem)]
    if not e.sec or e.sec not in model.sections:
        raise ValueError(f"Element {elem} hat keinen Querschnitt.")
    return model.sections[e.sec]


def _material_of(model: Model, elem: int) -> Material:
    return model.materials[model.elements[int(elem)].mat]


def _axes_at_end(model: Model, elem: int, end: int):
    """(Anschlusspunkt, Stabachse nach aussen, Achse y, Achse z) am Stabende."""
    e = model.elements[int(elem)]
    n0, n1 = int(e.nodes[0]), int(e.nodes[1])
    p0, p1 = model.nodes[n0], model.nodes[n1]
    if end == 0:
        p, axis = p0, p0 - p1
    else:
        p, axis = p1, p1 - p0
    L = np.linalg.norm(axis)
    if L <= 0:
        raise ValueError("Stabelement ohne Laenge")
    axis = axis / L
    up = np.array([0.0, 0.0, 1.0])
    if abs(float(axis @ up)) > 0.99:
        up = np.array([1.0, 0.0, 0.0])
    ey = np.cross(up, axis)
    ey = ey / np.linalg.norm(ey)
    ez = np.cross(axis, ey)
    return np.asarray(p, float), axis, ey, ez


@dataclass
class JointTemplate:
    """Gemeinsame Angaben aller Anschlussvorlagen."""
    name: str = "Anschluss"
    model: Model = None
    elem: int = 0
    end: int = 1
    bolt: Bolt = field(default_factory=lambda: Bolt("M20", "10.9"))
    grade: str = "S355"
    fy: float = 355e6
    fu: float = 490e6
    gamma_M0: float = 1.0
    gamma_M2: float = 1.25
    hinweise: list = field(default_factory=list)

    # -- Hilfen ---------------------------------------------------------
    def _bolt_for(self, F: float, n_min: int = 4, shear: bool = True) -> tuple[Bolt, int]:
        """Kleinste Schraube der Leiter, mit der n_min Schrauben die Kraft tragen."""
        for size in BOLT_LADDER:
            b = Bolt(size, self.bolt.grade, hole=self.bolt.hole,
                     preloaded=self.bolt.preloaded, mu=self.bolt.mu,
                     category=self.bolt.category)
            R = b.Fv_Rd() if shear else b.Ft_Rd()
            if R * n_min >= abs(F):
                return b, n_min
        b = Bolt(BOLT_LADDER[-1], self.bolt.grade, hole=self.bolt.hole,
                 preloaded=self.bolt.preloaded, mu=self.bolt.mu,
                 category=self.bolt.category)
        R = b.Fv_Rd() if shear else b.Ft_Rd()
        n = max(n_min, int(math.ceil(abs(F) / R)) if R else n_min)
        return b, n + n % 2

    def _weld(self, t: float, a: float = None) -> Fillet:
        a = a or max(min_throat(t), round(0.5 * t * 1000) / 1000.0)
        a = min(a, max_throat(t))
        return Fillet(a=a, length=0.0, fu=self.fu, grade=self.grade,
                      gamma_M2=self.gamma_M2)

    def describe(self) -> str:
        raise NotImplementedError

    def design(self, **forces) -> JointCheck:
        raise NotImplementedError

    def build(self, kind: str = "2d", **kw) -> Model:
        raise NotImplementedError


# ==========================================================================
# Kopfplatte / Stirnplatte
# ==========================================================================
@dataclass
class EndPlate(JointTemplate):
    """Geschraubte Kopfplatte am Stabende.

    tp:      Blechdicke [m]
    bp, hp:  Breite und Hoehe der Platte [m]
    rows:    Schraubenreihen als Abstand von der Plattenmitte in z [m],
             positiv nach oben (Zugflansch bei positivem Moment)
    w:       Schraubenabstand quer (Riss) [m]
    a_f, a_w: Nahtdicke am Flansch und am Steg [m]
    stiffeners: Anzahl der Rippen ueber und unter dem Flansch
    """
    tp: float = 0.020
    bp: float = 0.200
    hp: float = 0.400
    rows: list = field(default_factory=list)
    w: float = 0.100
    a_f: float = 0.006
    a_w: float = 0.004
    stiffeners: int = 0
    t_stiff: float = 0.010
    sec: Section = None
    ex: float = 0.045

    # -- Vorschlag ------------------------------------------------------
    @staticmethod
    def propose(model: Model, elem: int, end: int = 1, N: float = 0.0,
                Vz: float = 0.0, My: float = 0.0, bolt: Bolt = None,
                name: str = None) -> "EndPlate":
        """Vollstaendigen Vorschlag aus Profil und Schnittgroessen bilden."""
        sec = _section_of(model, elem)
        mat = _material_of(model, elem)
        fy = mat.yield_strength(sec.t_max) or 355e6
        fu = mat.ultimate_strength(sec.t_max) or 490e6
        h = sec.h or 0.300
        b = sec.b or 0.150
        tf = sec.tf or 0.012
        tw = sec.tw or 0.008
        a = EndPlate(name=name or f"Kopfplatte {model.elements[int(elem)].sec}",
                     model=model, elem=int(elem), end=int(end),
                     grade=mat.grade or "S355", fy=fy, fu=fu, sec=sec)
        a.bolt = bolt or Bolt("M20", "10.9", category="D")
        # Zugkraft im Flansch aus Moment und Normalkraft
        hebel = max(h - tf, 0.1 * h)
        anteil = (b * tf) / max(sec.A, 1e-9)      # Flanschanteil der Normalkraft
        Ft = abs(My) / hebel + max(N, 0.0) * anteil
        a.bolt, n = a._bolt_for(Ft, n_min=4, shear=False)
        d0 = a.bolt.d0
        ms = min_spacing(d0)
        # Riss quer: Flanschbreite ausnutzen, Mindestabstand einhalten
        a.w = max(2 * ms["e2"], min(b - 2 * ms["e2"], b - 0.5 * b) if b > 4 * ms["e2"]
                  else 2.2 * d0)
        a.w = max(a.w, 2.4 * d0)
        a.bp = max(b + 2 * ms["e2"], a.w + 2 * ms["e2"])
        a.ex = max(ms["e1"], 1.5 * d0)
        a.hp = h + 2 * (a.ex + 0.5 * d0) if abs(My) > 0 else h + 2 * ms["e1"]
        # Blechdicke: T-Stummel soll nicht im Modus 1 versagen ->
        # t >= sqrt(F_t,Rd * m / (l_eff * f_y))  (Modus 1 = Modus 3)
        m_arm = max(0.5 * (a.w - tw) - 0.8 * a.a_f * math.sqrt(2), 1.2 * d0)
        le = effective_lengths("innen", m=m_arm, e=0.5 * (a.bp - a.w))
        leff = min(le["cp"], le["nc"])
        t_req = math.sqrt(max(a.bolt.Ft_Rd() * 2 * m_arm / (leff * fy), 1e-9))
        a.tp = max(0.010, math.ceil(max(t_req, 0.6 * a.bolt.d) * 1000) / 1000.0)
        # Schraubenreihen: aussen und innen am Zugflansch, dazu am Druckflansch
        z_f = 0.5 * (h - tf)
        a.rows = [z_f + a.ex, z_f - max(ms["e1"], 1.5 * d0), -z_f, -z_f - a.ex] \
            if abs(My) > 0 else [z_f, -z_f]
        a.rows = [round(z, 4) for z in a.rows]
        # Naehte
        a.a_f = max(min_throat(tf), round(0.55 * tf * 1000) / 1000.0)
        a.a_w = max(min_throat(tw), round(0.55 * tw * 1000) / 1000.0)
        a.a_f = min(a.a_f, max_throat(tf))
        a.a_w = min(a.a_w, max_throat(tw))
        if abs(My) > 0.6 * fy * (sec.Wel_y or 1e-4):
            a.stiffeners = 2
            a.t_stiff = max(tw, 0.010)
            a.hinweise.append("hohes Moment - Rippen ueber und unter dem Zugflansch "
                              "vorgeschlagen")
        a.hinweise.append(f"Vorschlag aus {sec.name}: Zugkraft im Flansch "
                          f"F_t = {Ft / 1e3:.0f} kN, {n} Schrauben {a.bolt.size}")
        a.improve(N=N, Vz=Vz, My=My)
        return a

    def improve(self, rounds: int = 14, **forces) -> "EndPlate":
        """Vorschlag so lange nachbessern, bis alle Nachweise erfuellt sind.

        Nachgebessert wird jeweils das Bauteil, das der massgebende Nachweis
        nennt: Blechdicke beim T-Stummel, Schraube bei Schraubennachweisen,
        Nahtdicke bei den Naehten. Bleibt ein Nachweis unerfuellt, steht das im
        Hinweis - geraten wird nichts.
        """
        for _ in range(rounds):
            j = self.design(**forces)
            if j.ok:
                return self
            wo = j.massgebend
            if "T-Stummel" in wo or "Durchstanzen" in wo:
                self.tp = round(self.tp * 1000 + 2) / 1000.0
            elif "Kehlnaht" in wo:
                self.a_f = min(round(self.a_f * 1000 + 1) / 1000.0,
                               max_throat(self.sec.tf or 0.012))
                self.a_w = min(round(self.a_w * 1000 + 1) / 1000.0,
                               max_throat(self.sec.tw or 0.008))
            elif "Druckflansch" in wo:
                # Die Flanschkraft uebersteigt b t_f f_y - das ist der Traeger
                # selbst, nicht der Anschluss. Eine Druckrippe verteilt sie.
                if self.stiffeners < 2:
                    self.stiffeners = 2
                    self.t_stiff = max(self.sec.tw or 0.008, 0.010)
                else:
                    break
            elif "Zug F_t" in wo or "Abscheren" in wo or "Lochleibung" in wo \
                    or "Interaktion" in wo or "Gleitfestigkeit" in wo:
                if not self._next_bolt():
                    if len(self.rows) < 6:
                        self.rows = sorted(self.rows + [self.rows[1] - self.ex,
                                                        self.rows[-2] + self.ex],
                                           reverse=True)
                    else:
                        break
            else:
                break
        j = self.design(**forces)
        if not j.ok:
            self.hinweise.append(
                f"Vorschlag erreicht eta = {j.eta:.2f}; massgebend bleibt "
                f"'{j.massgebend}'. Bitte Geometrie von Hand anpassen.")
        return self

    def _next_bolt(self) -> bool:
        """Naechstgroessere Schraube waehlen. False, wenn schon die groesste."""
        try:
            i = BOLT_LADDER.index(self.bolt.size)
        except ValueError:
            return False
        if i + 1 >= len(BOLT_LADDER):
            return False
        self.bolt = Bolt(BOLT_LADDER[i + 1], self.bolt.grade, hole=self.bolt.hole,
                         preloaded=self.bolt.preloaded, mu=self.bolt.mu,
                         category=self.bolt.category)
        ms = min_spacing(self.bolt.d0)
        self.w = max(self.w, 2.4 * self.bolt.d0)
        self.bp = max(self.bp, self.w + 2 * ms["e2"])
        self.ex = max(self.ex, ms["e1"], 1.5 * self.bolt.d0)
        return True

    # -- Beschreibung ---------------------------------------------------
    def describe(self) -> str:
        z = ", ".join(f"{v * 1e3:+.0f}" for v in self.rows)
        t = [f"{self.name}: Blech {self.bp * 1e3:.0f} x {self.hp * 1e3:.0f} x "
             f"{self.tp * 1e3:.0f} mm, {self.grade}",
             f"  Schrauben {self.bolt.describe()}",
             f"  Reihen bei z = {z} mm, Riss w = {self.w * 1e3:.0f} mm",
             f"  Naehte: Flansch a = {self.a_f * 1e3:g} mm, Steg a = {self.a_w * 1e3:g} mm"]
        if self.stiffeners:
            t.append(f"  {self.stiffeners} Rippen, t = {self.t_stiff * 1e3:g} mm")
        for h in self.hinweise:
            t.append("  Hinweis: " + h)
        return "\n".join(t)

    def bolt_positions(self) -> list[tuple[float, float]]:
        """Schraubenlagen (y, z) in der Plattenebene [m]."""
        return [(sy * 0.5 * self.w, z) for z in self.rows for sy in (-1, 1)]

    # -- Nachweise ------------------------------------------------------
    def design(self, N: float = 0.0, Vz: float = 0.0, My: float = 0.0,
               n_cycles: float = 0.0, dMy: float = 0.0) -> JointCheck:
        """Nachweise der Kopfplatte fuer N, V_z und M_y."""
        j = JointCheck(self.name)
        sec = self.sec
        h = sec.h or 0.300
        tf = sec.tf or 0.012
        tw = sec.tw or 0.008
        b = sec.b or 0.150
        hebel = max(h - tf, 0.1 * h)
        anteil = (b * tf) / max(sec.A, 1e-9)
        zug = [z for z in self.rows if z > 0]
        n_zug = 2 * max(len(zug), 1)
        Ft_ges = abs(My) / hebel + max(N, 0.0) * anteil
        Ft = Ft_ges / n_zug
        n_all = 2 * max(len(self.rows), 1)
        Fv = abs(Vz) / n_all

        j.add(check_bolt(self.bolt, Fv_Ed=Fv, Ft_Ed=Ft,
                         geo=BoltGeometry(e1=self.ex, e2=0.5 * (self.bp - self.w),
                                          p1=abs(self.rows[0] - self.rows[1])
                                          if len(self.rows) > 1 else 0.0,
                                          p2=self.w),
                         t=self.tp, fu=self.fu, tp=self.tp))
        # T-Stummel der Zugzone
        m_arm = max(0.5 * (self.w - tw) - 0.8 * self.a_w * math.sqrt(2), 0.5 * self.bolt.d0)
        e_arm = 0.5 * (self.bp - self.w)
        le = effective_lengths("innen", m=m_arm, e=e_arm)
        ts = TStub(t=self.tp, fy=self.fy, m=m_arm, e=e_arm, leff_cp=le["cp"],
                   leff_nc=le["nc"], Ft_Rd=self.bolt.Ft_Rd(), n_bolts=2,
                   gamma_M0=self.gamma_M0)
        r = ts.resistance()
        j.add(Check("T-Stummel der Zugzone F_T,Rd", Ft_ges / max(len(zug), 1),
                    r["F_T_Rd"], hinweis=r["versagen"]))
        # Naehte: Flanschnaht traegt die Flanschkraft, Stegnaht die Querkraft
        nf = Fillet(a=self.a_f, length=2 * b, fu=self.fu, grade=self.grade,
                    gamma_M2=self.gamma_M2)
        j.add(check_weld(nf, N_perp=Ft_ges, V_perp=0.0, V_par=0.0))
        nw = Fillet(a=self.a_w, length=2 * max(h - 2 * tf, 0.05), fu=self.fu,
                    grade=self.grade, double=False, gamma_M2=self.gamma_M2)
        j.add(check_weld(nw, N_perp=0.0, V_perp=abs(Vz), V_par=0.0))
        # Druckflansch auf die Platte
        A_druck = b * tf
        F_druck = abs(My) / hebel + max(-N, 0.0) * anteil
        j.add(Check("Druckflansch auf die Platte", F_druck,
                    A_druck * self.fy / self.gamma_M0,
                    hinweis="Flanschkraft gegen b t_f f_y"))
        # Abstaende
        v = check_spacing(BoltGeometry(e1=self.ex, e2=e_arm,
                                       p1=abs(self.rows[0] - self.rows[1])
                                       if len(self.rows) > 1 else 0.0, p2=self.w),
                          self.bolt.d0, self.tp)
        j.hinweise.extend(v)
        if n_cycles and dMy:
            dFt = abs(dMy) / hebel / n_zug * self.bolt_range_factor()
            j.ermuedung.append(fatigue_check("schraube_zug", [(dFt, n_cycles)],
                                             area=self.bolt.As))
            if self.bolt.preloaded:
                j.hinweise.append(
                    "Ermuedung der Schrauben mit dem Faktor "
                    f"{self.bolt_range_factor():.2f} der aeusseren Schwingbreite "
                    "gerechnet (Vorspannung haelt die Fuge geschlossen). Genau "
                    "ergibt sich die Schwingbreite aus der Rechnung am Teilmodell.")
            else:
                j.hinweise.append(
                    "Schrauben nicht vorgespannt: die volle aeussere Schwingbreite "
                    "wirkt in der Schraube. Fuer ermuedungsbeanspruchte "
                    "Kopfplatten vorgespannte Schrauben verwenden.")
            j.ermuedung.append(fatigue_check("kopfplatte",
                                             [(abs(dMy) / max(sec.Wel_y, 1e-9), n_cycles)]))
        return j

    # -- FE-Modell ------------------------------------------------------
    def build(self, kind: str = "2d", model: Model = None, nx: int = 8, ny: int = 12,
              nz: int = 2, stub: float = None, log: list = None) -> Model:
        """Teilmodell des Anschlusses: Kopfplatte, Stabstueck, Schrauben, Fuge.

        kind="2d": Bleche als Schalen, Stabstueck als Balken mit sternfoermiger
        Lasteinleitung. kind="3d": Bleche als Volumen (hex8).
        Rueckgabe: das Modell (neu oder das uebergebene).
        """
        m = model or Model(self.name)
        src = self.model
        sec = self.sec
        h = sec.h or 0.300
        stub = stub if stub is not None else max(2.0 * h, 0.400)
        mat = _material_of(src, self.elem)
        if mat.name not in m.materials:
            m.add_material(Material(**{k: getattr(mat, k) for k in
                                       ("name", "E", "nu", "rho", "alpha", "fy", "fu", "grade")}))
        if sec.name not in m.sections:
            m.add_section(sec)
        p, axis, ey, ez = _axes_at_end(src, self.elem, self.end)
        # Zwei Kopfplatten Ruecken an Ruecken (Stoss) - die Gegenplatte bildet
        # den Anschlusspartner ab.
        if kind == "3d":
            g1 = B.plate_solid(m, p - axis * self.tp, axis, self.bp, self.hp, self.tp,
                               mat.name, nx=nx, ny=ny, nz=nz, ref=ey)
            g2 = B.plate_solid(m, p, axis, self.bp, self.hp, self.tp, mat.name,
                               nx=nx, ny=ny, nz=nz, ref=ey)
            face_a = g1[:, :, -1]
            face_b = g2[:, :, 0]
        else:
            g1 = B.plate_shells(m, p - axis * (0.5 * self.tp), axis, self.bp, self.hp,
                                self.tp, mat.name, nx=nx, ny=ny, ref=ey)
            g2 = B.plate_shells(m, p + axis * (0.5 * self.tp), axis, self.bp, self.hp,
                                self.tp, mat.name, nx=nx, ny=ny, ref=ey)
            face_a, face_b = g1, g2
        B.contact_layer(m, face_a, face_b, mu=self.bolt.mu if self.bolt.preloaded else 0.0)
        # Schrauben an ihren Lagen
        for (y, z) in self.bolt_positions():
            pa = p - axis * (self.tp if kind == "3d" else 0.5 * self.tp) + y * ey + z * ez
            pb = p + axis * (self.tp if kind == "3d" else 0.5 * self.tp) + y * ey + z * ez
            na = B.nearest_node(m, pa)
            nb = B.nearest_node(m, pb)
            B.add_bolt(m, na, nb, self.bolt, case=m.active_case,
                       shear="lochleibung", log=log)
        # Stabstueck als Balken mit sternfoermiger Einleitung in die Platte
        stiff = B.stiff_section(m)
        # Anschlusspunkt auf einen vorhandenen Blechknoten legen, damit kein
        # deckungsgleicher Zusatzknoten entsteht
        n_end = B.nearest_node(m, p - axis * self.tp * (1 if kind == "3d" else 0.5))
        n_far = m.add_node(*(p - axis * (stub + self.tp)))
        m.add_element("beam", [n_far, n_end], mat.name, sec.name, group="stab")
        ring = [B.nearest_node(m, p - axis * (self.tp if kind == "3d" else 0.5 * self.tp)
                               + y * ey + z * ez)
                for (y, z) in self._flange_points()]
        B.rigid_fan(m, n_end, ring, mat.name, stiff)
        # Gegenplatte halten
        for n in np.ravel(g2[:, :, -1] if kind == "3d" else g2):
            m.fix(int(n), "all")
        if log is not None:
            log.append(f"{self.name}: {len(m.elements)} Elemente, {m.nn} Knoten "
                       f"({'Volumen' if kind == '3d' else 'Schalen'})")
        return m

    def bolt_range_factor(self, k_plate_ratio: float = 5.0) -> float:
        """Anteil der aeusseren Schwingbreite, der in der Schraube ankommt.

        Solange die Fuge unter Vorspannung geschlossen bleibt, teilt sich die
        aeussere Kraft nach den Steifigkeiten von Schraube und geklemmtem Paket:
        Delta-F_S = Delta-F * k_S/(k_S + k_P). Mit dem ueblichen Verhaeltnis
        k_P ~ 5 k_S ergibt das rund 0,17. Ohne Vorspannung wirkt die volle
        Schwingbreite. Der genaue Wert folgt aus der Rechnung am Teilmodell.
        """
        if not self.bolt.preloaded:
            return 1.0
        return 1.0 / (1.0 + max(k_plate_ratio, 0.0))

    def _flange_points(self) -> list[tuple[float, float]]:
        sec = self.sec
        h = sec.h or 0.300
        b = sec.b or 0.150
        tf = sec.tf or 0.012
        z = 0.5 * (h - tf)
        return [(-0.4 * b, z), (0.0, z), (0.4 * b, z),
                (-0.4 * b, -z), (0.0, -z), (0.4 * b, -z), (0.0, 0.0)]


# ==========================================================================
# Laschenstoss
# ==========================================================================
@dataclass
class Splice(JointTemplate):
    """Laschenstoss: Flansch- und Steglaschen, geschraubt.

    t_fl, b_fl:  Dicke und Breite der Flanschlaschen [m]
    t_web, h_web: Dicke und Hoehe der Steglaschen [m]
    n_fl, n_web: Schrauben je Flanschlasche bzw. Steglasche und Stossseite
    p1, e1, p2:  Loch- und Randabstaende in Stabrichtung bzw. quer [m]
    inner_flange: Flanschlaschen auch innen (zweischnittig)
    """
    t_fl: float = 0.012
    b_fl: float = 0.150
    t_web: float = 0.010
    h_web: float = 0.200
    n_fl: int = 4
    n_web: int = 4
    p1: float = 0.070
    e1: float = 0.040
    p2: float = 0.080
    inner_flange: bool = True
    sec: Section = None

    @staticmethod
    def propose(model: Model, elem: int, end: int = 1, N: float = 0.0,
                Vz: float = 0.0, My: float = 0.0, bolt: Bolt = None,
                name: str = None) -> "Splice":
        """Laschenstoss aus Profil und Schnittgroessen vorschlagen.

        Die Flanschlaschen uebernehmen Normalkraft und Moment, die Steglaschen
        die Querkraft - die uebliche Aufteilung des Stosses (EN 1993-1-8, 6.2.7).
        """
        sec = _section_of(model, elem)
        mat = _material_of(model, elem)
        fy = mat.yield_strength(sec.t_max) or 355e6
        fu = mat.ultimate_strength(sec.t_max) or 490e6
        h = sec.h or 0.300
        b = sec.b or 0.150
        tf = sec.tf or 0.012
        tw = sec.tw or 0.008
        a = Splice(name=name or f"Laschenstoss {model.elements[int(elem)].sec}",
                   model=model, elem=int(elem), end=int(end),
                   grade=mat.grade or "S355", fy=fy, fu=fu, sec=sec)
        a.bolt = bolt or Bolt("M20", "10.9", category="C", mu=0.5)
        hebel = max(h - tf, 0.1 * h)
        F_flansch = abs(My) / hebel + abs(N) * (b * tf) / max(sec.A, 1e-9)
        schnitte = 2 if a.inner_flange else 1
        b0 = a.bolt
        a.bolt, a.n_fl = a._bolt_for(F_flansch / schnitte, n_min=4, shear=True)
        Fs = (a.bolt.Fs_Rd() if a.bolt.preloaded else a.bolt.Fv_Rd()) * schnitte
        if Fs > 0:
            a.n_fl = max(4, int(math.ceil(F_flansch / Fs)))
            a.n_fl += a.n_fl % 2
        Fq = a.bolt.Fs_Rd() if a.bolt.preloaded else a.bolt.Fv_Rd()
        a.n_web = max(2, int(math.ceil(abs(Vz) / (2.0 * Fq)))) if Fq else 2
        a.n_web += a.n_web % 2
        d0 = a.bolt.d0
        ms = min_spacing(d0)
        a.p1 = max(ms["p1"], 3.0 * d0)
        a.e1 = max(ms["e1"], 2.0 * d0)
        a.p2 = max(ms["p2"], min(b - 2 * ms["e2"], 3.0 * d0))
        a.t_fl = max(0.008, math.ceil(tf * (0.6 if a.inner_flange else 1.05) * 1000) / 1000.0)
        a.b_fl = b
        a.t_web = max(0.006, math.ceil(tw * 0.6 * 1000) / 1000.0)
        a.h_web = max(0.5 * h, (a.n_web / 2 - 1) * a.p1 + 2 * a.e1)
        a.hinweise.append(
            f"Vorschlag aus {sec.name}: Flanschkraft {F_flansch / 1e3:.0f} kN "
            f"-> {a.n_fl} Schrauben {a.bolt.size} je Flansch und Seite"
            + (" (zweischnittig)" if a.inner_flange else " (einschnittig)"))
        if a.bolt.preloaded:
            a.hinweise.append("gleitfeste Verbindung: massgebend ist die "
                              "Gleitfestigkeit, nicht das Abscheren")
        a.improve(N=N, Vz=Vz, My=My)
        return a

    def improve(self, rounds: int = 16, **forces) -> "Splice":
        """Laschen und Schraubenzahl nachbessern, bis die Nachweise erfuellt sind."""
        for _ in range(rounds):
            j = self.design(**forces)
            if j.ok:
                return self
            wo = j.massgebend
            if wo.startswith("Flansch des Traegers"):
                self.hinweise.append(
                    "Der Nettoquerschnitt des Traegerflansches ist massgebend, "
                    "nicht der Anschluss: die Loecher im Flansch mindern ihn unter "
                    "die Flanschkraft. Abhilfe: hoehere Stahlsorte, groesseres "
                    "Profil, vorgespannte Verbindung (Kategorie C) oder ein "
                    "geschweisster Stoss.")
                break
            if "Nettoquerschnitt" in wo or "Bruttoquerschnitt" in wo \
                    or "Blockversagen" in wo:
                self.t_fl = round(self.t_fl * 1000 + 2) / 1000.0
                self.t_web = round(self.t_web * 1000 + 1) / 1000.0
            elif "Gleitfestigkeit" in wo or "Abscheren" in wo or "Lochleibung" in wo:
                self.n_fl += 2
                self.n_web += 2
            else:
                break
        j = self.design(**forces)
        if not j.ok:
            self.hinweise.append(
                f"Vorschlag erreicht eta = {j.eta:.2f}; massgebend bleibt "
                f"'{j.massgebend}'.")
        return self

    def describe(self) -> str:
        t = [f"{self.name}: Flanschlaschen {self.b_fl * 1e3:.0f} x {self.t_fl * 1e3:.0f} mm"
             + (" aussen und innen" if self.inner_flange else " nur aussen"),
             f"  Steglaschen {self.h_web * 1e3:.0f} x {self.t_web * 1e3:.0f} mm, beidseitig",
             f"  Schrauben {self.bolt.describe()}",
             f"  je Flansch und Seite {self.n_fl}, je Steg und Seite {self.n_web}",
             f"  Abstaende p_1 = {self.p1 * 1e3:.0f} mm, e_1 = {self.e1 * 1e3:.0f} mm, "
             f"p_2 = {self.p2 * 1e3:.0f} mm"]
        for h in self.hinweise:
            t.append("  Hinweis: " + h)
        return "\n".join(t)

    def design(self, N: float = 0.0, Vz: float = 0.0, My: float = 0.0,
               n_cycles: float = 0.0, dN: float = 0.0) -> JointCheck:
        j = JointCheck(self.name)
        sec = self.sec
        h = sec.h or 0.300
        b = sec.b or 0.150
        tf = sec.tf or 0.012
        tw = sec.tw or 0.008
        hebel = max(h - tf, 0.1 * h)
        A_fl = b * tf
        F_flansch = abs(My) / hebel + abs(N) * A_fl / max(sec.A, 1e-9)
        schnitte = 2 if self.inner_flange else 1
        Fv = F_flansch / max(self.n_fl, 1)
        geo = BoltGeometry(e1=self.e1, e2=0.5 * (self.b_fl - self.p2),
                           p1=self.p1, p2=self.p2, inner_1=True)
        Lj = max(0.0, (self.n_fl / 2 - 1) * self.p1)
        j.add(check_bolt(Bolt(self.bolt.size, self.bolt.grade, hole=self.bolt.hole,
                              preloaded=self.bolt.preloaded, mu=self.bolt.mu,
                              category=self.bolt.category, shear_planes=schnitte),
                         Fv_Ed=Fv, geo=geo, t=min(tf, self.t_fl), fu=self.fu, Lj=Lj))
        # Steglaschen: Querkraft, zweischnittig
        Fw = abs(Vz) / max(self.n_web, 1) / 2.0
        j.add(check_bolt(Bolt(self.bolt.size, self.bolt.grade, hole=self.bolt.hole,
                              preloaded=self.bolt.preloaded, mu=self.bolt.mu,
                              category=self.bolt.category, shear_planes=2),
                         Fv_Ed=Fw,
                         geo=BoltGeometry(e1=self.e1, e2=self.e1, p1=self.p1,
                                          p2=self.p1, inner_1=True),
                         t=min(tw, 2 * self.t_web), fu=self.fu))
        # Netto- und Bruttoquerschnitt der Lasche und des Flansches
        n_reihen = max(1, self.n_fl // 2)
        A_lasche = self.b_fl * self.t_fl * schnitte
        A_netto = A_lasche - 2 * self.bolt.d0 * self.t_fl * schnitte
        for c in check_net_section(A_lasche, A_netto, self.fy, self.fu, F_flansch,
                                   category_C=(self.bolt.category == "C")):
            c.name = c.name.replace("Zug ", "Lasche: Zug ")
            j.add(c)
        A_fl_netto = A_fl - 2 * self.bolt.d0 * tf
        for c in check_net_section(A_fl, A_fl_netto, self.fy, self.fu, F_flansch,
                                   category_C=(self.bolt.category == "C"))[1:]:
            c.name = "Flansch des Traegers: " + c.name
            c.hinweis = ("Bauteilquerschnitt, nicht der Anschluss - Loecher im "
                         "Flansch mindern ihn")
            j.add(c)
        # Blockversagen der Lasche
        Ant = (0.5 * (self.b_fl - self.p2) + self.p2 - 1.5 * self.bolt.d0) * self.t_fl * schnitte
        Anv = 2 * ((n_reihen - 1) * self.p1 + self.e1
                   - (n_reihen - 0.5) * self.bolt.d0) * self.t_fl * schnitte
        j.add(check_block_tearing(F_flansch, max(Ant, 1e-9), max(Anv, 1e-9),
                                  self.fu, self.fy))
        v = check_spacing(geo, self.bolt.d0, min(tf, self.t_fl))
        j.hinweise.extend(v)
        if n_cycles and dN:
            detail = "gvp" if self.bolt.category == "C" else "blech_loch"
            dsig = abs(dN) / max(A_netto if detail == "blech_loch" else A_lasche, 1e-9)
            j.ermuedung.append(fatigue_check(detail, [(dsig, n_cycles)]))
            j.ermuedung.append(fatigue_check(
                "passschraube" if self.bolt.hole == "pass" else "schraube_abscheren",
                [(abs(dN) / max(self.n_fl, 1) / schnitte, n_cycles)], area=self.bolt.A))
        return j

    def build(self, kind: str = "2d", model: Model = None, log: list = None,
              **kw) -> Model:
        """Teilmodell des Stosses: zwei Flanschlaschen und Steglaschen mit Schrauben."""
        m = model or Model(self.name)
        src = self.model
        sec = self.sec
        mat = _material_of(src, self.elem)
        if mat.name not in m.materials:
            m.add_material(Material(**{k: getattr(mat, k) for k in
                                       ("name", "E", "nu", "rho", "alpha", "fy", "fu", "grade")}))
        h = sec.h or 0.300
        tf = sec.tf or 0.012
        b = sec.b or 0.150
        p, axis, ey, ez = _axes_at_end(src, self.elem, self.end)
        n_reihen = max(1, self.n_fl // 2)
        L = (n_reihen - 1) * self.p1 + 2 * self.e1
        z_fl = 0.5 * (h - tf)
        gitter = []
        for sgn in (1, -1):                      # Ober- und Untergurt
            for seite in ((1, -1) if self.inner_flange else (1,)):
                o = p + sgn * z_fl * ez + seite * (0.5 * tf + 0.5 * self.t_fl) * ez * sgn
                g = B.plate_shells(m, o, ez * sgn, 2 * L, self.b_fl, self.t_fl,
                                   mat.name, nx=max(4, 2 * n_reihen), ny=4, ref=axis)
                gitter.append((sgn, seite, g))
        # Gurte als Balkenstuecke links und rechts des Stosses
        if sec.name not in m.sections:
            m.add_section(sec)
        stiff = B.stiff_section(m)
        n_mid = m.add_node(*p)
        n_l = m.add_node(*(p - axis * L))
        n_r = m.add_node(*(p + axis * L))
        m.add_element("beam", [n_l, n_mid], mat.name, sec.name, group="stab")
        m.add_element("beam", [n_mid, n_r], mat.name, sec.name, group="stab")
        # Schrauben: je Reihe zwei Schrauben quer, beidseitig des Stosses
        n_b = 0
        for i in range(n_reihen):
            x = self.e1 + i * self.p1
            for vor in (-1, 1):
                for sgn, seite, g in gitter:
                    for y in (-0.5 * self.p2, 0.5 * self.p2):
                        pt = p + vor * x * axis + y * ey + sgn * z_fl * ez
                        na = B.nearest_node(m, pt + sgn * seite * 0.5 * self.t_fl * ez)
                        nb = B.nearest_node(m, pt - sgn * seite * 0.5 * self.t_fl * ez)
                        if na != nb:
                            B.add_bolt(m, na, nb, self.bolt, case=m.active_case,
                                       shear="lochleibung")
                            n_b += 1
        for n in (n_l,):
            m.fix(int(n), "all")
        if log is not None:
            log.append(f"{self.name}: {n_b} Schrauben, {len(m.elements)} Elemente, "
                       f"{m.nn} Knoten")
        return m


# ==========================================================================
# Diagonalanschluss (Knotenblech)
# ==========================================================================
@dataclass
class Gusset(JointTemplate):
    """Diagonalanschluss ueber ein Knotenblech.

    t_g:     Dicke des Knotenblechs [m]
    n_bolt:  Schrauben in der Diagonale
    p1, e1:  Lochabstand und Randabstand in Stabrichtung [m]
    p2, e2:  quer dazu [m]
    reihen:  Schraubenreihen quer (1 oder 2)
    a_w:     Nahtdicke des Blechs am Anschlussbauteil [m]
    welded:  geschweisster Anschluss statt geschraubt
    """
    t_g: float = 0.012
    n_bolt: int = 4
    p1: float = 0.070
    e1: float = 0.045
    p2: float = 0.070
    e2: float = 0.045
    reihen: int = 1
    a_w: float = 0.006
    welded: bool = False
    l_weld: float = 0.200
    sec: Section = None

    @staticmethod
    def propose(model: Model, elem: int, end: int = 1, N: float = 0.0,
                bolt: Bolt = None, welded: bool = False,
                name: str = None) -> "Gusset":
        """Knotenblech aus Profil und Stabkraft vorschlagen."""
        sec = _section_of(model, elem)
        mat = _material_of(model, elem)
        fy = mat.yield_strength(sec.t_max) or 355e6
        fu = mat.ultimate_strength(sec.t_max) or 490e6
        a = Gusset(name=name or f"Diagonalanschluss {model.elements[int(elem)].sec}",
                   model=model, elem=int(elem), end=int(end),
                   grade=mat.grade or "S355", fy=fy, fu=fu, sec=sec, welded=welded)
        a.bolt = bolt or Bolt("M20", "10.9", category="A")
        t_ref = max(sec.tw or 0.008, sec.tf or 0.010)
        a.t_g = max(0.008, math.ceil(max(t_ref, abs(N) / (0.6 * fy * 0.200)) * 1000) / 1000.0)
        if welded:
            fvw = (fu / math.sqrt(3.0)) / (0.9 * a.gamma_M2)
            a.a_w = max(min_throat(a.t_g), 0.004)
            a.l_weld = max(0.100, abs(N) / (2.0 * fvw * a.a_w)) if fvw * a.a_w else 0.200
            a.l_weld = math.ceil(a.l_weld * 1000) / 1000.0
            a.hinweise.append(f"geschweisst: 2 Flankenkehlnaehte a = {a.a_w * 1e3:g} mm, "
                              f"l = {a.l_weld * 1e3:.0f} mm je Seite")
            return a
        a.bolt, _n = a._bolt_for(abs(N), n_min=2, shear=True)
        R = a.bolt.Fs_Rd() if a.bolt.preloaded else a.bolt.Fv_Rd()
        a.n_bolt = max(2, int(math.ceil(abs(N) / R))) if R else 2
        a.reihen = 2 if a.n_bolt > 4 else 1
        if a.reihen == 2:
            a.n_bolt += a.n_bolt % 2
        d0 = a.bolt.d0
        ms = min_spacing(d0)
        a.p1 = max(ms["p1"], 3.0 * d0)
        a.e1 = max(ms["e1"], 2.0 * d0)
        a.p2 = max(ms["p2"], 2.5 * d0)
        a.e2 = max(ms["e2"], 1.5 * d0)
        a.a_w = max(min_throat(a.t_g), 0.004)
        a.hinweise.append(f"Vorschlag aus {sec.name}: Stabkraft {abs(N) / 1e3:.0f} kN "
                          f"-> {a.n_bolt} Schrauben {a.bolt.size} in {a.reihen} Reihe(n)")
        a.improve(N=N)
        return a

    def improve(self, rounds: int = 16, **forces) -> "Gusset":
        """Knotenblech und Schraubenzahl nachbessern."""
        for _ in range(rounds):
            j = self.design(**forces)
            if j.ok:
                return self
            wo = j.massgebend
            if "Nettoquerschnitt" in wo or "Bruttoquerschnitt" in wo \
                    or "Blockversagen" in wo or "Knotenblech" in wo \
                    or "Lochleibung" in wo:
                self.t_g = round(self.t_g * 1000 + 2) / 1000.0
                if self.n_je_reihe < 6:
                    self.n_bolt += self.reihen
            elif "Abscheren" in wo or "Gleitfestigkeit" in wo or "Kehlnaht" in wo:
                if self.welded:
                    self.l_weld = round(self.l_weld * 1000 + 20) / 1000.0
                else:
                    self.n_bolt += self.reihen
            else:
                break
        j = self.design(**forces)
        if not j.ok:
            self.hinweise.append(
                f"Vorschlag erreicht eta = {j.eta:.2f}; massgebend bleibt "
                f"'{j.massgebend}'. Bitte Geometrie von Hand anpassen.")
        return self

    @property
    def n_je_reihe(self) -> int:
        return max(1, self.n_bolt // max(self.reihen, 1))

    def whitmore_width(self) -> float:
        """Wirksame Breite des Knotenblechs (Whitmore, 30 Grad je Seite) [m]."""
        L = (self.n_je_reihe - 1) * self.p1
        breite = (self.reihen - 1) * self.p2
        return breite + 2.0 * L * math.tan(math.radians(30.0))

    def describe(self) -> str:
        if self.welded:
            t = [f"{self.name}: Knotenblech t = {self.t_g * 1e3:.0f} mm, {self.grade}",
                 f"  geschweisst, a = {self.a_w * 1e3:g} mm, l = {self.l_weld * 1e3:.0f} mm "
                 "je Flanke"]
        else:
            t = [f"{self.name}: Knotenblech t = {self.t_g * 1e3:.0f} mm, {self.grade}",
                 f"  Schrauben {self.bolt.describe()}",
                 f"  {self.n_bolt} Schrauben in {self.reihen} Reihe(n), "
                 f"p_1 = {self.p1 * 1e3:.0f} mm, e_1 = {self.e1 * 1e3:.0f} mm",
                 f"  wirksame Breite nach Whitmore: {self.whitmore_width() * 1e3:.0f} mm"]
        for h in self.hinweise:
            t.append("  Hinweis: " + h)
        return "\n".join(t)

    def design(self, N: float = 0.0, n_cycles: float = 0.0, dN: float = 0.0) -> JointCheck:
        j = JointCheck(self.name)
        sec = self.sec
        if self.welded:
            n = Fillet(a=self.a_w, length=self.l_weld, fu=self.fu, grade=self.grade,
                       double=True, gamma_M2=self.gamma_M2)
            j.add(check_weld(n, V_par=abs(N)))
        else:
            Fv = abs(N) / max(self.n_bolt, 1)
            geo = BoltGeometry(e1=self.e1, e2=self.e2, p1=self.p1, p2=self.p2,
                               inner_1=self.n_je_reihe > 1, inner_2=self.reihen > 1)
            Lj = (self.n_je_reihe - 1) * self.p1
            j.add(check_bolt(self.bolt, Fv_Ed=Fv, geo=geo,
                             t=min(self.t_g, sec.tw or self.t_g), fu=self.fu, Lj=Lj))
            # Knotenblech: Whitmore-Querschnitt und Nettoquerschnitt
            bw = self.whitmore_width()
            A_w = bw * self.t_g
            A_net = A_w - self.reihen * self.bolt.d0 * self.t_g
            j.add(check_net_section(A_w, max(A_net, 1e-9), self.fy, self.fu, abs(N),
                                    category_C=(self.bolt.category == "C")))
            # Blockversagen des Knotenblechs
            Ant = (self.p2 * (self.reihen - 1) + 2 * self.e2
                   - self.reihen * self.bolt.d0) * self.t_g
            Anv = 2 * ((self.n_je_reihe - 1) * self.p1 + self.e1
                       - (self.n_je_reihe - 0.5) * self.bolt.d0) * self.t_g
            j.add(check_block_tearing(abs(N), max(Ant, 1e-9), max(Anv, 1e-9),
                                      self.fu, self.fy))
            j.hinweise.extend(check_spacing(geo, self.bolt.d0, self.t_g))
            # Knicken des Knotenblechs bei Druck (Thornton, Ersatzstab)
            if N < 0:
                Lc = self.e1 + (self.n_je_reihe - 1) * self.p1 * 0.5
                i = self.t_g / math.sqrt(12.0)
                lam = (0.65 * Lc / i) / (math.pi * math.sqrt(210e9 / self.fy))
                chi = min(1.0, 1.0 / (0.5 * (1 + 0.34 * (lam - 0.2) + lam ** 2)
                                      + math.sqrt(max(1e-12,
                                                      (0.5 * (1 + 0.34 * (lam - 0.2) + lam ** 2)) ** 2
                                                      - lam ** 2))))
                j.add(Check("Knotenblech auf Druck (Ersatzstab)", abs(N),
                            chi * bw * self.t_g * self.fy / self.gamma_M0,
                            hinweis=f"lambda_quer = {lam:.2f}, chi = {chi:.2f}"))
        if n_cycles and dN:
            if self.welded:
                A = 2 * self.a_w * self.l_weld
                j.ermuedung.append(fatigue_check("kehlnaht_laengs",
                                                 [(abs(dN) / A, n_cycles)]))
            else:
                bw = self.whitmore_width()
                A_net = bw * self.t_g - self.reihen * self.bolt.d0 * self.t_g
                j.ermuedung.append(fatigue_check("blech_loch",
                                                 [(abs(dN) / max(A_net, 1e-9), n_cycles)]))
                j.ermuedung.append(fatigue_check(
                    "passschraube" if self.bolt.hole == "pass" else "schraube_abscheren",
                    [(abs(dN) / max(self.n_bolt, 1), n_cycles)], area=self.bolt.A))
        return j

    def build(self, kind: str = "2d", model: Model = None, log: list = None,
              **kw) -> Model:
        """Teilmodell: Knotenblech mit der angeschlossenen Diagonale."""
        m = model or Model(self.name)
        src = self.model
        sec = self.sec
        mat = _material_of(src, self.elem)
        if mat.name not in m.materials:
            m.add_material(Material(**{k: getattr(mat, k) for k in
                                       ("name", "E", "nu", "rho", "alpha", "fy", "fu", "grade")}))
        if sec.name not in m.sections:
            m.add_section(sec)
        p, axis, ey, ez = _axes_at_end(src, self.elem, self.end)
        L = 2 * self.e1 + (self.n_je_reihe - 1) * self.p1
        breite = max(self.whitmore_width() * 1.3, (self.reihen - 1) * self.p2 + 2 * self.e2)
        o = p - axis * (0.5 * L)
        g = B.plate_shells(m, o, ez, L, breite, self.t_g, mat.name,
                           nx=max(4, 2 * self.n_je_reihe), ny=4, ref=axis)
        stiff = B.stiff_section(m)
        n_far = m.add_node(*(p + axis * max(0.5, L)))
        n_end = B.nearest_node(m, p)
        m.add_element("beam", [n_end, n_far], mat.name, sec.name, group="diagonale")
        if self.welded:
            ring = [int(x) for x in g[0, :]]
            B.rigid_fan(m, n_end, ring, mat.name, stiff)
        else:
            punkte = []
            for i in range(self.n_je_reihe):
                x = -0.5 * L + self.e1 + i * self.p1
                for k in range(self.reihen):
                    y = (k - 0.5 * (self.reihen - 1)) * self.p2
                    punkte.append(B.nearest_node(m, p + x * axis + y * ey))
            B.rigid_fan(m, n_end, punkte, mat.name, stiff)
        for n in np.ravel(g[-1, :]):
            m.fix(int(n), "all")
        if log is not None:
            log.append(f"{self.name}: {len(m.elements)} Elemente, {m.nn} Knoten")
        return m


#: Vorlagenklassen zum Namen
TEMPLATES = {"kopfplatte": EndPlate, "lasche": Splice, "diagonale": Gusset}


def propose(kind: str, model: Model, elem: int, end: int = 1, **forces):
    """Vorlage nach Typ vorschlagen: kind aus TYPES."""
    if kind not in TEMPLATES:
        raise KeyError(f"Anschlusstyp '{kind}' unbekannt: {sorted(TEMPLATES)}")
    cls = TEMPLATES[kind]
    if cls is Gusset:
        forces = {k: v for k, v in forces.items() if k in ("N", "bolt", "welded", "name")}
    else:
        forces = {k: v for k, v in forces.items()
                  if k in ("N", "Vz", "My", "bolt", "name")}
    return cls.propose(model, elem, end, **forces)
