"""
Stellungen des Systems - bewegliche Brücken und Stahlwasserbauten.

Eine Klappbrücke, eine Drehbrücke oder ein Hubtor ist in jeder Stellung ein
anderes Tragwerk: Lager greifen oder nicht, Riegel sind gezogen, das
Eigengewicht wirkt unter einem anderen Winkel, der Antrieb hält ein anderes
Moment. Deshalb wird jede **Stellung** als eigener Rechenlauf geführt und am
Ende die Umhüllende über alle Stellungen gebildet.

    Stellung        Name, Winkel, welche Lager greifen, welche Lastfälle gelten,
                    Drehachse und Drehwinkel für die bewegten Bauteile
    Stellungsreihe  alle Stellungen eines Bauwerks, gerechnet und ausgewertet
    Umhüllende      größte Ausnutzung, Schnittgröße und Auflagerkraft über alle
                    Stellungen, mit Angabe der maßgebenden Stellung

    from statik3d.bridges.positions import Stellung, Stellungsreihe
    reihe = Stellungsreihe(modell)
    reihe.add(Stellung("S1", 0.0,   "geschlossen", lager_aktiv=["Endauflager"]))
    reihe.add(Stellung("S3", 32.0,  "im Öffnen"))
    reihe.add(Stellung("S5", 82.0,  "offen", lager_aktiv=["Ruhelager"]))
    erg = reihe.rechnen()
    print(erg.bericht())
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..model import Model


def _massgebend(analyse, m: Model):
    """Das Ergebnis mit der groessten Verformung: Kombination, sonst Lastfall."""
    alle = analyse.all_results()
    if not alle:
        return None
    def betrag(r):
        if r is None or getattr(r, "u", None) is None:
            return -1.0
        return float(np.abs(np.asarray(r.u).reshape(-1, 6)[:, :3]).max())
    return max(alle.values(), key=betrag)


def drehmatrix(achse, winkel: float) -> np.ndarray:
    """Drehmatrix um eine Achse durch den Ursprung (Rodrigues), Winkel im Bogenmaß."""
    a = np.asarray(achse, float)
    n = np.linalg.norm(a)
    if n <= 0:
        return np.eye(3)
    a = a / n
    K = np.array([[0.0, -a[2], a[1]], [a[2], 0.0, -a[0]], [-a[1], a[0], 0.0]])
    return np.eye(3) + math.sin(winkel) * K + (1.0 - math.cos(winkel)) * (K @ K)


@dataclass
class Stellung:
    """Eine Stellung des Systems.

    name:         Kurzname, z. B. "S3"
    winkel:       Stellungswinkel in Grad (nur zur Beschriftung und für die
                  Kurve η über den Winkel)
    beschreibung: Klartext, z. B. "im Öffnen, Riegel gezogen"
    lager_aktiv:  Namen der Lager, die in dieser Stellung greifen. Leer =
                  alle Lager greifen. Lager ohne Namen bleiben immer aktiv.
    lager_aus:    Namen der Lager, die in dieser Stellung ausdrücklich nicht
                  greifen (wirkt zusätzlich zu lager_aktiv).
    faelle:       Lastfälle, die in dieser Stellung gelten. Leer = alle.
    kombinationen: Kombinationen, die in dieser Stellung gelten. Leer = alle,
                  die nur aus den geltenden Lastfällen bestehen.
    dreh_achse / dreh_punkt / dreh_winkel:
                  Drehung der bewegten Bauteile: Achse, ein Punkt darauf und der
                  Winkel in Grad. Gedreht werden die Knoten der Gruppen in
                  dreh_gruppen (leer = alle Knoten, die nicht gelagert sind).
    dreh_gruppen: Elementgruppen, die sich mitbewegen.
    antrieb:      (Knoten, Momentenvektor [Nm]) - das Antriebsmoment, das die
                  Stellung hält. Wird als Knotenlast in einem eigenen Lastfall
                  aufgebracht.
    """
    name: str
    winkel: float = 0.0
    beschreibung: str = ""
    lager_aktiv: list = field(default_factory=list)
    lager_aus: list = field(default_factory=list)
    faelle: list = field(default_factory=list)
    kombinationen: list = field(default_factory=list)
    dreh_achse: tuple = (0.0, 1.0, 0.0)
    dreh_punkt: tuple = (0.0, 0.0, 0.0)
    dreh_winkel: float = 0.0
    dreh_gruppen: list = field(default_factory=list)
    antrieb: tuple = None
    windlast: float = 0.0

    def beschriftung(self) -> str:
        t = f"{self.name} ({self.winkel:g}°)"
        return t + (f" - {self.beschreibung}" if self.beschreibung else "")

    # -- Modell fuer diese Stellung -------------------------------------
    def modell(self, basis: Model, log: list = None) -> Model:
        """Das Modell dieser Stellung: gedrehte Geometrie, wirksame Lager, Lasten."""
        m = basis.copy()
        m.name = f"{basis.name} - {self.name}"
        if self.dreh_winkel:
            self._drehen(m, log)
        self._lager(m, log)
        self._faelle(m, log)
        if self.antrieb:
            self._antrieb(m, log)
        return m

    def _bewegte_knoten(self, m: Model) -> np.ndarray:
        if self.dreh_gruppen:
            idx = set()
            for e in m.elements:
                if e.group in self.dreh_gruppen:
                    idx.update(int(n) for n in e.nodes)
            return np.fromiter(sorted(idx), dtype=int, count=len(idx))
        fest = {s.node for s in m.supports}
        return np.array([i for i in range(m.nn) if i not in fest], dtype=int)

    def _drehen(self, m: Model, log: list = None):
        idx = self._bewegte_knoten(m)
        if not len(idx):
            return
        R = drehmatrix(self.dreh_achse, math.radians(self.dreh_winkel))
        p0 = np.asarray(self.dreh_punkt, float)
        m.nodes[idx] = (m.nodes[idx] - p0) @ R.T + p0
        if log is not None:
            log.append(f"  {self.name}: {len(idx)} Knoten um {self.dreh_winkel:g}° "
                       f"um die Achse {tuple(self.dreh_achse)} gedreht")

    def _lager(self, m: Model, log: list = None):
        aus = set(self.lager_aus)
        ein = set(self.lager_aktiv)
        behalten = []
        entfernt = []
        for s in m.supports:
            nm = (s.name or "").strip()
            if nm and nm in aus:
                entfernt.append(nm)
                continue
            if ein and nm and nm not in ein:
                entfernt.append(nm)
                continue
            behalten.append(s)
        m.supports = behalten
        for coll, art in ((m.line_supports, "Linienlager"),
                          (m.surface_supports, "Flächenlager")):
            rest = []
            for s in coll:
                nm = (s.name or "").strip()
                if nm and (nm in aus or (ein and nm not in ein)):
                    entfernt.append(nm)
                    continue
                rest.append(s)
            coll[:] = rest
        if entfernt and log is not None:
            log.append(f"  {self.name}: Lager ohne Wirkung: " + ", ".join(sorted(set(entfernt))))

    def _faelle(self, m: Model, log: list = None):
        if not self.faelle:
            return
        behalten = set(self.faelle)
        for name in list(m.load_cases):
            if name not in behalten:
                m.remove_load_case(name)
        for name in list(m.combinations):
            c = m.combinations[name]
            if not set(c.factors) <= behalten:
                del m.combinations[name]
        if log is not None:
            log.append(f"  {self.name}: Lastfälle {', '.join(sorted(behalten))}")

    def _antrieb(self, m: Model, log: list = None):
        knoten, moment = self.antrieb
        name = f"Antrieb {self.name}"
        if name not in m.load_cases:
            m.add_load_case(name, "Q", f"Antriebsmoment in Stellung {self.name}",
                            activate=False)
        Mx, My, Mz = [float(v) for v in moment]
        m.load_node(int(knoten), Mx=Mx, My=My, Mz=Mz, case=name)
        for c in m.combinations.values():
            if any(f > 0 for f in c.factors.values()):
                c.factors.setdefault(name, 1.0)
        if log is not None:
            log.append(f"  {self.name}: Antriebsmoment |M| = "
                       f"{np.linalg.norm(moment) / 1e3:.1f} kNm an Knoten {knoten + 1}")


@dataclass
class StellungsErgebnis:
    """Ergebnis einer einzelnen Stellung."""
    stellung: Stellung
    modell: Model = None
    analyse: object = None
    ergebnis: object = None
    nachweise: object = None
    eta: float = 0.0
    massgebend: str = ""
    u_max: float = 0.0
    reaktion: np.ndarray = None
    fehler: str = ""

    @property
    def ok(self) -> bool:
        return not self.fehler and self.eta <= 1.0 + 1e-9


class Stellungsreihe:
    """Alle Stellungen eines Bauwerks: rechnen, umhüllen, auswerten.

    Jede Stellung wird als eigenes Modell gerechnet. Danach steht fest, welche
    Stellung für welchen Nachweis maßgebend ist - die Angabe, die bei
    beweglichen Brücken zählt.
    """

    def __init__(self, modell: Model, name: str = ""):
        self.basis = modell
        self.name = name or modell.name
        self.stellungen: list[Stellung] = []
        self.ergebnisse: list[StellungsErgebnis] = []
        self.log: list[str] = []

    def add(self, stellung: Stellung) -> Stellung:
        self.stellungen.append(stellung)
        return stellung

    def aus_winkeln(self, winkel, achse=(0, 1, 0), punkt=(0, 0, 0),
                    gruppen=None, praefix: str = "S") -> list:
        """Stellungsreihe aus einer Winkelliste erzeugen (gleiche Drehachse)."""
        out = []
        for i, w in enumerate(winkel, 1):
            out.append(self.add(Stellung(
                f"{praefix}{i}", float(w),
                "geschlossen" if abs(w) < 1e-9 else f"gedreht um {w:g}°",
                dreh_achse=achse, dreh_punkt=punkt, dreh_winkel=float(w),
                dreh_gruppen=list(gruppen or []))))
        return out

    # -- Rechnen ---------------------------------------------------------
    def rechnen(self, kombinationen: bool = True, nachweise: bool = False,
                workers: int = None, progress=None) -> "Umhuellende":
        """Alle Stellungen rechnen. Rueckgabe: Umhuellende ueber alle Stellungen."""
        from .. import solver
        self.ergebnisse = []
        self.log = []
        for i, st in enumerate(self.stellungen, 1):
            if progress:
                progress(f"Stellung {i}/{len(self.stellungen)}: {st.beschriftung()}")
            self.log.append(f"Stellung {st.beschriftung()}")
            e = StellungsErgebnis(stellung=st)
            try:
                m = st.modell(self.basis, self.log)
                e.modell = m
                fehler = [z for z in m.check() if z.startswith("FEHLER")]
                if fehler:
                    e.fehler = "; ".join(fehler[:3])
                    self.log.append(f"  {st.name}: {e.fehler}")
                    self.ergebnisse.append(e)
                    continue
                an = solver.solve_all(m, workers=workers,
                                      combinations=kombinationen and bool(m.combinations),
                                      envelopes=True)
                e.analyse = an
                r = _massgebend(an, m)
                e.ergebnis = r
                if r is not None and r.u is not None:
                    u = np.asarray(r.u).reshape(-1, 6)
                    e.u_max = float(np.abs(u[:, :3]).max())
                if r is not None and r.reactions is not None:
                    e.reaktion = np.asarray(r.reactions).reshape(-1, 6)
                if nachweise and m.members:
                    from ..ec3 import design as ec3d
                    e.nachweise = ec3d.check_members(m, an)
                    e.eta = float(e.nachweise.util_max)
                    schlimm = max(e.nachweise.members.values(),
                                  key=lambda x: x.util, default=None)
                    if schlimm is not None:
                        g = schlimm.governing or {}
                        e.massgebend = (f"{schlimm.member}: "
                                        + (g.get("name") or g.get("text") or "-"))
                self.log.append(f"  {st.name}: u_max = {e.u_max * 1e3:.3f} mm"
                                + (f", eta = {e.eta:.3f}" if nachweise else ""))
            except Exception as ex:      # noqa: BLE001
                e.fehler = str(ex)
                self.log.append(f"  {st.name}: FEHLER {ex}")
            self.ergebnisse.append(e)
        return Umhuellende(self)

    # -- Zugriff ---------------------------------------------------------
    def __len__(self) -> int:
        return len(self.stellungen)

    def ergebnis(self, name: str) -> StellungsErgebnis:
        for e in self.ergebnisse:
            if e.stellung.name == name:
                return e
        raise KeyError(f"Stellung '{name}' nicht gerechnet")


class Umhuellende:
    """Größte Werte über alle Stellungen, mit der maßgebenden Stellung."""

    def __init__(self, reihe: Stellungsreihe):
        self.reihe = reihe
        self.ergebnisse = [e for e in reihe.ergebnisse if not e.fehler]
        self.fehlerhaft = [e for e in reihe.ergebnisse if e.fehler]

    @property
    def eta(self) -> float:
        return max((e.eta for e in self.ergebnisse), default=0.0)

    @property
    def massgebende_stellung(self) -> str:
        if not self.ergebnisse:
            return ""
        e = max(self.ergebnisse, key=lambda x: x.eta)
        return e.stellung.beschriftung()

    @property
    def u_max(self) -> float:
        return max((e.u_max for e in self.ergebnisse), default=0.0)

    def stellung_mit_groesstem_u(self) -> str:
        if not self.ergebnisse:
            return ""
        return max(self.ergebnisse, key=lambda x: x.u_max).stellung.beschriftung()

    def reaktionen(self) -> dict:
        """Größte Auflagerkraft je Knoten und Richtung über alle Stellungen.

        Rueckgabe: {knoten: {"Fx": (wert, stellung), ...}} - nur Knoten mit Lager.
        """
        out: dict = {}
        for e in self.ergebnisse:
            if e.reaktion is None:
                continue
            for s in e.modell.supports:
                n = int(s.node)
                zeile = e.reaktion[n]
                d = out.setdefault(n, {})
                for k, name in enumerate(("Fx", "Fy", "Fz", "Mx", "My", "Mz")):
                    v = float(zeile[k])
                    alt = d.get(name)
                    if alt is None or abs(v) > abs(alt[0]):
                        d[name] = (v, e.stellung.beschriftung())
        return out

    def kurve(self) -> list:
        """[(Winkel, eta, u_max, Stellungsname)] - für die Kurve über den Winkel."""
        return sorted([(e.stellung.winkel, e.eta, e.u_max, e.stellung.name)
                       for e in self.ergebnisse])

    def bericht(self) -> str:
        z = [f"Stellungen des Systems - {self.reihe.name}", "=" * 78,
             f"{'Stellung':<10s}{'Winkel':>9s}{'u_max':>12s}{'eta':>9s}  Beschreibung"]
        for e in self.reihe.ergebnisse:
            st = e.stellung
            if e.fehler:
                z.append(f"{st.name:<10s}{st.winkel:>8.1f}°{'-':>12s}{'-':>9s}  "
                         f"FEHLER: {e.fehler[:40]}")
            else:
                z.append(f"{st.name:<10s}{st.winkel:>8.1f}°{e.u_max * 1e3:>10.3f} mm"
                         f"{e.eta:>9.3f}  {st.beschreibung}")
        z.append("-" * 78)
        z.append(f"Umhüllende: eta = {self.eta:.3f}"
                 + (f", maßgebend in {self.massgebende_stellung}"
                    if self.massgebende_stellung else ""))
        z.append(f"größte Verformung {self.u_max * 1e3:.3f} mm"
                 + (f" in {self.stellung_mit_groesstem_u()}" if self.ergebnisse else ""))
        r = self.reaktionen()
        if r:
            z.append("")
            z.append("Größte Auflagerkräfte über alle Stellungen:")
            z.append(f"{'Knoten':>8s}{'F_z [kN]':>12s}  maßgebend")
            for n in sorted(r):
                v, st = r[n].get("Fz", (0.0, ""))
                z.append(f"{n + 1:>8d}{v / 1e3:>12.2f}  {st}")
        if self.fehlerhaft:
            z.append("")
            z.append("Nicht gerechnet:")
            for e in self.fehlerhaft:
                z.append(f"  {e.stellung.beschriftung()}: {e.fehler[:60]}")
        return "\n".join(z)
