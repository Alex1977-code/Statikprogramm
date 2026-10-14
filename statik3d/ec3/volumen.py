"""
Spannungsnachweis fuer Volumenbereiche nach DIN EN 1993-1-1, 6.2.1(5),
mit den Hinweisen auf die Zaehigkeitsanforderungen nach DIN EN 1993-1-10.

Ein Volumen hat keinen Querschnitt: Klassifizierung, W_pl, Knicklaengen und
die Interaktionsformeln des Abschnitts 6 gehen darum nicht.  Was geht, ist
der **Spannungsnachweis am Punkt**, und den verlangt 6.2.1(5) ausdruecklich
als konservative Alternative:

    sigma_v,Ed = sqrt( sigma_x^2 + sigma_z^2 - sigma_x sigma_z + 3 tau^2 )
               <= f_y / gamma_M0

fuer den allgemeinen dreiachsigen Spannungszustand also die
Vergleichsspannung nach von Mises

    sigma_v = sqrt( 1/2 [ (s1-s2)^2 + (s2-s3)^2 + (s3-s1)^2 ] )

mit den Hauptspannungen s1 >= s2 >= s3.

Zusaetzlich ausgewiesen und beurteilt:

  * die **Hauptspannungen** und die groesste Schubspannung
    tau_max = (s1 - s3)/2 (Tresca als Vergleich),
  * die **Mehrachsigkeit** h = sigma_m / sigma_v mit
    sigma_m = (s1+s2+s3)/3.  Bei dreiachsigem Zug (s3 > 0) wird die
    Verformungsfaehigkeit stark eingeschraenkt; DIN EN 1993-1-10 verlangt
    dann eine Betrachtung der Stahlsorte und der Zaehigkeit.  Das Programm
    rechnet das nicht, sagt es aber deutlich.

**Spannungssingularitaeten**: An einspringenden Ecken, unter Einzellasten und
an Punktlagern waechst die Spannung mit jeder Netzverfeinerung; ein Nachweis
gegen f_y ist dort sinnlos.  Ein Volumenbereich kann darum als ``singular``
gekennzeichnet werden - dann werden die Spannungen berichtet, aber nicht als
Nachweis gefuehrt.  Unabhaengig davon prueft das Programm, wie stark die
Spitzenspannung ueber dem Mittel des Bereichs liegt, und weist auf eine
moegliche Singularitaet hin.

**Plastische Rechnung** (Entscheidung des Anwenders vom 13.10.2026): dort
ist die Spannung keine Nachweisgroesse. Nachgewiesen wird die groesste
plastische Hauptdehnung eps_p,1 an den Integrationspunkten gegen einen
Grenzwert (``Volumenbereich.eps_grenze``, Vorgabe 5 % nach EN 1993-1-5
Anh. C / EN 1993-1-14), eta = eps_p,1 / Grenzwert. Schrauben, Ankerstaebe und
Gewindeteile werden nicht ueber die Dehnung nachgewiesen, sondern ueber Kraft
bzw. Spannung nach EN 1993-1-8 (Stabnachweis, Anschluss). Bis zum 13.10.2026
stand der Bereich plastisch als „nicht bewertet“, davor mit der Spannung.

**Ausgenommen**: Koerper oder Werkstoffe mit dem Schalter „vom
Volumennachweis ausnehmen“ (Hilfs- oder Krafteinleitungskoerper, seit
13.10.2026) gehen in keinen Nachweis ein und werden mit Namen ausgewiesen.

**Nicht enthalten**: Stabilitaet des Volumenkoerpers (die geometrische
Steifigkeit ist nur fuer Stabelemente gebildet), Kriechen und
der Sproedbruchnachweis nach EN 1993-1-10 selbst. Die Ermuedung der Volumen
(Hauptspannung je Knoten aus derselben geglaetteten Spannung wie hier, seit
23.09.2026) steht in ec3/fatigue.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..begriffe import anzahl

#: Ab welchem Verhaeltnis Spitzenspannung / Mittelwert im Bereich auf eine
#: moegliche Singularitaet hingewiesen wird
SPITZE_GRENZE = 5.0

#: Anteil von sigma_v, ab dem sigma_3 als echter Zug gilt (Rechenrauschen)
ZUG_SCHWELLE = 0.02

#: Status eines Bereichs, dessen Ergebnisse aus einer plastischen Rechnung
#: stammen (Entscheidung des Anwenders vom 13.10.2026): die Spannung ist dort
#: keine Nachweisgroesse - am Drehlager las der Nachweis die geglaettete
#: Eckspannung nicht fliessender Elemente, ausserhalb der Zonen bis
#: 1 596 N/mm2. Bis zum 13.10.2026 stand hier ein Zahlenwert.
NICHT_BEWERTET = "nicht bewertet – plastische Rechnung"

#: Vorgabe des Grenzwerts der plastischen Hauptdehnung (13.10.2026) und die
#: Normstelle, aus der er stammt
EPS_GRENZE = 0.05
NORM_DEHNUNG = "EN 1993-1-5 Anh. C / EN 1993-1-14"


def prozent(x: float) -> str:
    """Eine Dehnung als Prozent ohne Exponent („5.0“, „2.5“, „0.125“)."""
    s = f"{float(x) * 100.0:.3f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def hauptdehnung_1(eps) -> np.ndarray:
    """Groesste Hauptdehnung je Zeile aus [eps_x, eps_y, eps_z, gamma_xy,
    gamma_yz, gamma_zx] - Ingenieurgleitungen wie plastizitaet.Zustand, im
    Tensor also gamma/2."""
    e = np.asarray(eps, float).reshape(-1, 6)
    T = np.zeros((len(e), 3, 3))
    T[:, 0, 0], T[:, 1, 1], T[:, 2, 2] = e[:, 0], e[:, 1], e[:, 2]
    T[:, 0, 1] = T[:, 1, 0] = 0.5 * e[:, 3]
    T[:, 1, 2] = T[:, 2, 1] = 0.5 * e[:, 4]
    T[:, 0, 2] = T[:, 2, 0] = 0.5 * e[:, 5]
    return np.linalg.eigvalsh(T)[:, -1] if len(e) else np.zeros(0)


def ip_dehnungen(res) -> tuple:
    """(Daten, Grund): die plastischen Dehnungen je Integrationspunkt eines
    Ergebnisses (``info["ip_dehnungen"]``, solver.ip_dehnungen_ablegen) oder
    der Grund, warum es sie nicht gibt."""
    info = getattr(res, "info", None) or {}
    if not info.get("plastizitaet"):
        return None, ("Überlagerung von Ergebnissen einer plastischen Rechnung - die plastische "
                      "Dehnung ist nicht überlagerbar; die Kombination selbst plastisch rechnen")
    d = info.get("ip_dehnungen")
    if d is None:
        return None, ("Ergebnis ohne plastische Dehnungen an den Integrationspunkten (gerechnet vor "
                      "dem 13.10.2026) - neu rechnen")
    return d, ""


def koerper_je_element(model) -> dict:
    """{Element: Koerpername} der Volumenelemente - Element.group, wenn es
    ein Koerper ist, sonst die Elementliste des Koerpers (wie
    spitzenanzeige.bauteil_des_elements, fuer alle Elemente auf einmal)."""
    koerper = getattr(model, "koerper", None) or {}
    aus: dict = {}
    for name, k in koerper.items():
        for e in (getattr(k, "elemente", None) or []):
            aus[int(e)] = str(name)
    for i, e in enumerate(model.elements):
        g = str(getattr(e, "group", "") or "")
        if g and g in koerper:
            aus[i] = g
    return aus


def ausgenommene(model, elemente, je_koerper: dict) -> tuple:
    """(uebrige Elemente, Namen, Zahl): die Elemente ohne die der Koerper und
    Werkstoffe mit ``nachweis_ausnehmen`` (13.10.2026). Die Namen lauten
    „Körper X“ bzw. „Werkstoff Y“; ein Element zaehlt beim Koerper, wenn
    beide gesetzt sind."""
    koerper = getattr(model, "koerper", None) or {}
    k_aus = {n for n, k in koerper.items() if getattr(k, "nachweis_ausnehmen", False)}
    w_aus = {n for n, mt in model.materials.items() if getattr(mt, "nachweis_ausnehmen", False)}
    if not k_aus and not w_aus:
        return list(elemente), [], 0
    rest, namen, n = [], {}, 0
    for e in elemente:
        kn = je_koerper.get(int(e), "")
        mt = model.elements[int(e)].mat
        if kn in k_aus:
            namen[f"Körper {kn}"] = None
        elif mt in w_aus:
            namen[f"Werkstoff {mt}"] = None
        else:
            rest.append(e)
            continue
        n += 1
    return rest, list(namen), n


def _dehnung_max(daten: dict, elemente: set) -> tuple:
    """(eps_p,1, Element, Punkt, Ort) des groessten Werts ueber die Punkte
    der ``elemente`` - (0.0, -1, -1, None), wenn dort nichts fliesst."""
    best = (0.0, -1, -1, None)
    for _schl, wert in (daten or {}).items():
        ids, eps = np.asarray(wert[0]), np.asarray(wert[1], float)
        orte = np.asarray(wert[2], float) if len(wert) > 2 else None
        if not len(ids):
            continue
        sel = np.fromiter((int(i) in elemente for i in ids.tolist()), bool, count=len(ids))
        if not sel.any():
            continue
        E = eps[sel]
        e1 = hauptdehnung_1(E.reshape(-1, 6)).reshape(E.shape[0], E.shape[1])
        a, p = np.unravel_index(int(np.argmax(e1)), e1.shape)
        if float(e1[a, p]) > best[0] or best[1] < 0:
            ort = orte[sel][a, p] if orte is not None else None
            best = (float(e1[a, p]), int(ids[sel][a]), int(p),
                    None if ort is None else [float(x) for x in ort])
    return best


def ist_plastisch(res, alle: dict = None) -> bool:
    """Stammt das Ergebnis aus einer plastischen Rechnung? Ja, wenn es selbst
    den Eintrag ``info["plastizitaet"]`` traegt oder wenn eine Ueberlagerung
    (``info["factors"]``) ein solches Ergebnis aus ``alle`` enthaelt - etwa
    eine Kombination oder die Alternative einer Ergebniskombination."""
    info = getattr(res, "info", None) or {}
    if info.get("plastizitaet"):
        return True
    faktoren = info.get("factors")
    if isinstance(faktoren, dict) and alle:
        for name, f in faktoren.items():
            r = alle.get(name)
            if f and r is not None and r is not res and (getattr(r, "info", None) or {}).get("plastizitaet"):
                return True
    return False


#: So stand ein ausgeschalteter Bereich bis zum 23.09.2026 in
#: ``VolumenCheck.fehler`` - nur noch zum Lesen alter Ergebnisdateien
_AUSGESCHALTET_ALT = "Nachweis für diesen Bereich ausgeschaltet"


def hauptspannungen(s) -> np.ndarray:
    """Hauptspannungen s1 >= s2 >= s3 aus [sx, sy, sz, txy, tyz, tzx]."""
    sx, sy, sz, txy, tyz, tzx = (float(x) for x in s)
    T = np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]])
    return np.sort(np.linalg.eigvalsh(T))[::-1]


def hauptrichtungen(s):
    """(Hauptspannungen, Richtungen als Spalten) - absteigend geordnet."""
    sx, sy, sz, txy, tyz, tzx = (float(x) for x in s)
    T = np.array([[sx, txy, tzx], [txy, sy, tyz], [tzx, tyz, sz]])
    w, v = np.linalg.eigh(T)
    o = np.argsort(w)[::-1]
    return w[o], v[:, o]


def vergleichsspannung(s) -> float:
    """von Mises aus dem Spannungsvektor [sx, sy, sz, txy, tyz, tzx]."""
    sx, sy, sz, txy, tyz, tzx = (float(x) for x in s)
    return math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                     + 3.0 * (txy ** 2 + tyz ** 2 + tzx ** 2))


def mehrachsigkeit(s1: float, s2: float, s3: float, sv: float) -> dict:
    """
    Mehrachsigkeit h = sigma_m/sigma_v und die Beurteilung.

    sigma_m ist die hydrostatische Spannung (s1+s2+s3)/3.  Bei h > 1/3 und
    dreiachsigem Zug ist die Verformungsfaehigkeit deutlich eingeschraenkt.

    "Dreiachsiger Zug" wird nur gemeldet, wenn die kleinste Hauptspannung
    wirklich Zug ist und nicht bloss Rechenrauschen: sie muss ueber
    ``ZUG_SCHWELLE`` der Vergleichsspannung und ueber 1 N/mm^2 liegen.
    Sonst meldete jeder einachsige Zugstab, dessen sigma_3 rechnerisch bei
    1e-14 N/mm^2 landet, einen dreiachsigen Zugzustand.
    """
    sm = (s1 + s2 + s3) / 3.0
    h = sm / sv if sv > 1e-9 else 0.0
    zug3 = s3 > max(ZUG_SCHWELLE * sv, 1e6)
    return {"sigma_m": sm, "h": h, "dreiachsiger_zug": bool(zug3),
            "kritisch": bool(zug3 and h > 1.0 / 3.0)}


def punkt_nachweis(s, fy: float, gamma_M0: float = 1.0) -> dict:
    """Spannungsnachweis an einem Punkt: alle Werte auf einen Blick."""
    s1, s2, s3 = hauptspannungen(s)
    sv = vergleichsspannung(s)
    fyd = fy / gamma_M0
    d = {"sigma": [float(x) for x in s], "s1": float(s1), "s2": float(s2),
         "s3": float(s3), "sigma_v": sv, "tau_max": float((s1 - s3) / 2.0),
         "f_yd": fyd, "eta": sv / fyd if fyd > 0 else 0.0,
         "eta_tresca": (float(s1 - s3) / fyd) if fyd > 0 else 0.0}
    d.update(mehrachsigkeit(s1, s2, s3, sv))
    return d


# ==========================================================================
@dataclass
class VolumenCheck:
    """Nachweis eines Volumenbereichs ueber alle GZT-Kombinationen."""
    name: str
    beschreibung: str = ""
    n_elemente: int = 0
    material: str = ""
    fy: float = 0.0
    util: float = 0.0
    kombination: str = ""
    element: int = -1
    werte: dict = field(default_factory=dict)
    je_kombination: list = field(default_factory=list)
    singular: bool = False
    hinweise: list = field(default_factory=list)
    fehler: str = ""
    #: Der Nachweis ist am Bereich ausgeschaltet (``Volumenbereich.design``,
    #: Schalter „Nachweis führen“) - **gewollt** nicht gefuehrt, anders als
    #: ``fehler`` (konnte nicht gefuehrt werden). Wie ein Stab mit
    #: design=False zaehlt er im Gesamturteil weder als erfuellt noch als
    #: offen. Bis zum 23.09.2026 stand das in ``fehler``: am Zugkoerper
    #: (N = 2500 kN) hiess es mit „Schaft“ und einem ausgeschalteten Bereich
    #: „Alle **geführten** Nachweise erfüllt – nicht geführt wurden:
    #: 1 Volumenbereiche“ statt „Alle Nachweise erfüllt.“, mit dem
    #: ausgeschalteten allein ebenso, obwohl kein Nachweis lief (Befund B058).
    ausgeschaltet: bool = False
    #: Netzabhaengige Spannungsspitzen (seit 10.10.2026, Plan Singularitaeten
    #: Paket 2): Elemente des Bereichs in den Zonen auffaelliger Stellen
    #: (spitzenstellen.zonen_elemente des Ergebnisses) gehen nicht in ``util``
    #: ein, sie sind nur berichtet - mit ihrer Spitze hier. Ergebnisdateien
    #: von davor kennen die Felder nicht; es gelten die Klassenvorgaben.
    zone_n: int = 0
    zone_sigma_v: float = 0.0
    zone_eta: float = 0.0
    zone_element: int = -1
    zone_kombination: str = ""
    #: Ergebnisse einer plastischen Rechnung ohne auswertbare Dehnungen
    #: (Ueberlagerung, Ergebnisdatei von vor dem 13.10.2026): die Namen; dann
    #: steht kein Zahlenwert da, ``fehler`` traegt den Grund
    nicht_bewertet: str = ""
    #: Kriterium des massgebenden Ergebnisses (seit 13.10.2026): "dehnung" =
    #: groesste plastische Hauptdehnung am Integrationspunkt gegen
    #: ``eps_grenze`` (plastische Rechnung), "" = Vergleichsspannung wie bisher
    kriterium: str = ""
    eps_grenze: float = 0.0
    eps_p1: float = 0.0
    #: der massgebende Integrationspunkt (0-basiert), sein Ort [m], Koerper
    #: und Werkstoff
    ip: int = -1
    ort: list = field(default_factory=list)
    bauteil: str = ""
    werkstoff_ort: str = ""
    #: Zone: groesste plastische Hauptdehnung dort (nur berichtet)
    zone_eps: float = 0.0
    #: ausgenommene Koerper und Werkstoffe („Körper X“, „Werkstoff Y“), die
    #: Zahl ihrer Elemente im Bereich, und ob es alle sind (13.10.2026)
    ausgenommen: list = field(default_factory=list)
    n_ausgenommen: int = 0
    alle_ausgenommen: bool = False

    def __setstate__(self, state):
        # Ergebnisdatei (ergebnisse.py, Pickle) von vor dem 23.09.2026: dort
        # fehlt das Feld, und der ausgeschaltete Bereich traegt den alten
        # Fehlertext - er wuerde nach dem Laden wieder als "nicht geführt"
        # gezaehlt
        self.__dict__.update(state)
        if "ausgeschaltet" not in state and state.get("fehler") == _AUSGESCHALTET_ALT:
            self.ausgeschaltet, self.fehler = True, ""
        # Listenfelder seit 13.10.2026 haben keinen Klassenwert
        self.__dict__.setdefault("ort", [])
        self.__dict__.setdefault("ausgenommen", [])

    def ort_text(self) -> str:
        """„Element 4, IP 2 (x/y/z = 362.5 / 12.3 / 87.7 mm)“ des
        massgebenden Punkts der Dehnung - „–“ ohne."""
        if self.element < 0:
            return "–"
        s = f"Element {self.element + 1}"
        if self.ip >= 0:
            s += f", IP {self.ip + 1}"
        if self.ort:
            s += " (x/y/z = " + " / ".join(f"{x * 1e3:.1f}" for x in self.ort) + " mm)"
        return s

    def status(self) -> str:
        if self.ausgeschaltet:
            return "ausgeschaltet"
        if getattr(self, "alle_ausgenommen", False):
            return "ausgenommen"
        if getattr(self, "nicht_bewertet", ""):
            return NICHT_BEWERTET
        if self.fehler:
            return "nicht geführt"
        if self.singular:
            return "nur berichtet"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class VolumenResults:
    bereiche: dict = field(default_factory=dict)
    kombinationen: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    #: Kombinationen ohne Ergebnis ("nicht nachgewiesen"), siehe
    #: design._uls_results
    warnungen: list = field(default_factory=list)

    @property
    def util_max(self) -> float:
        return max((c.util for c in self.bereiche.values()
                    if not c.singular), default=0.0)

    def summary(self) -> str:
        from .design import warnzeilen
        return self._summary() + warnzeilen(self)

    def _summary(self) -> str:
        if not self.bereiche:
            return "Volumennachweise: keine Bereiche festgelegt"
        gefuehrt = [c for c in self.bereiche.values()
                    if not c.singular and not c.fehler and not c.ausgeschaltet
                    and not getattr(c, "alle_ausgenommen", False)]
        schlecht = [c.name for c in gefuehrt if c.util > 1.0]
        nb = [c.name for c in self.bereiche.values() if getattr(c, "nicht_bewertet", "")]
        fehler = [c.name for c in self.bereiche.values() if c.fehler and c.name not in nb]
        nur = [c.name for c in self.bereiche.values()
               if c.singular and not c.ausgeschaltet]
        aus = [c.name for c in self.bereiche.values() if c.ausgeschaltet]
        ausg = [c for c in self.bereiche.values() if getattr(c, "ausgenommen", None)]
        nb_alle = [c.name for c in self.bereiche.values() if getattr(c, "nicht_bewertet", "")]
        if nb_alle and not gefuehrt:
            # plastische Rechnung (13.10.2026): das Urteil vorn - der
            # Ergebnisbaum zeigt nur die ersten 60 Zeichen
            s = (f"Volumen: {NICHT_BEWERTET} ({anzahl(len(nb_alle), 'Bereich', 'Bereiche')}: "
                 + ", ".join(nb_alle[:8]) + (" …" if len(nb_alle) > 8 else "") + ")")
            if aus:
                s += f" - {len(aus)} ausgeschaltet: " + ", ".join(aus)
            return s
        kriterien = {getattr(c, "kriterium", "") for c in gefuehrt}
        if kriterien == {"dehnung"}:
            kopf = "Volumen (plastische Hauptdehnung ε_p,1)"
        elif "dehnung" in kriterien:
            kopf = "Volumen (EN 1993-1-1, 6.2.1(5) bzw. plastische Hauptdehnung ε_p,1)"
        else:
            kopf = "Volumen (EN 1993-1-1, 6.2.1(5))"
        s = f"{kopf}: {anzahl(len(self.bereiche), 'Bereich', 'Bereiche')}"
        if gefuehrt:
            worst = max(gefuehrt, key=lambda c: c.util)
            if getattr(worst, "kriterium", "") == "dehnung":
                # plastische Rechnung (13.10.2026): die Dehnung, ihr Grenzwert und wo
                s += (f", max. Ausnutzung {worst.util:.3f} ({worst.name}: "
                      f"ε_p,1 = {worst.eps_p1 * 100:.3f} % von {prozent(worst.eps_grenze)} % "
                      f"nach {NORM_DEHNUNG}"
                      + (f", {worst.bauteil}" if worst.bauteil else "")
                      + (f", Element {worst.element + 1}" if worst.element >= 0 else "")
                      + (f", {worst.kombination}" if worst.kombination else "") + ")")
            else:
                s += (f", max. Ausnutzung {worst.util:.3f} ({worst.name}: "
                      f"σ_v = {worst.werte.get('sigma_v', 0) / 1e6:.1f} von "
                      f"{worst.werte.get('f_yd', 0) / 1e6:.1f} N/mm²"
                      + (f", {worst.kombination}" if worst.kombination else "") + ")")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif gefuehrt and not fehler:
            s += " - alle erfüllt"
        if nur:
            s += f" - {len(nur)} nur berichtet (Singularität): " + ", ".join(nur)
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        if nb:
            s += f" - {len(nb)} nicht bewertet (plastische Rechnung): " + ", ".join(nb)
        if aus:
            s += f" - {len(aus)} ausgeschaltet: " + ", ".join(aus)
        if ausg:
            # vom Nachweis ausgenommen (13.10.2026): mit Namen
            s += " - ausgenommen: " + "; ".join(
                f"{c.name}: {', '.join(c.ausgenommen)} ({anzahl(c.n_ausgenommen, 'Element', 'Elemente')})"
                for c in ausg)
        zonen = [c for c in self.bereiche.values() if getattr(c, "zone_n", 0)]
        if zonen:
            s += (" - netzabhängige Stellen nur berichtet: "
                  + ", ".join(f"{c.name} (ε_p,1 bis {c.zone_eps * 100:.3f} %)"
                              if getattr(c, "kriterium", "") == "dehnung"
                              else f"{c.name} (σ_v bis {c.zone_sigma_v / 1e6:.1f} N/mm²)" for c in zonen))
        return s

    def table(self) -> list[list]:
        rows = [["Bereich", "Elemente", "Material", "f_y [MPa]", "σ_v [MPa]",
                 "σ_1 [MPa]", "σ_3 [MPa]", "Ausnutzung", "Kombination", "Status"]]
        for c in self.bereiche.values():
            w = c.werte or {}
            if getattr(c, "nicht_bewertet", "") or getattr(c, "alle_ausgenommen", False):
                # plastisch ohne auswertbare Dehnung bzw. alles ausgenommen
                # (13.10.2026): kein Zahlenwert
                rows.append([c.name, str(c.n_elemente), c.material, f"{c.fy / 1e6:.0f}",
                             "–", "–", "–", "–", "", c.status()
                             + (": " + ", ".join(c.ausgenommen) if c.alle_ausgenommen else "")])
                continue
            if getattr(c, "kriterium", "") == "dehnung":
                # plastische Rechnung: Dehnung statt Spannung, keine Spannungsspalten
                rows.append([c.name, str(c.n_elemente), c.material, f"{c.fy / 1e6:.0f}",
                             "–", "–", "–", f"{c.util:.3f}", c.kombination, c.status()])
                if getattr(c, "zone_n", 0):
                    rows.append([f"{c.name} (netzabhängige Stellen)", str(c.zone_n), c.material,
                                 f"{c.fy / 1e6:.0f}", "–", "–", "–", f"{c.zone_eta:.3f}",
                                 c.zone_kombination, "nur berichtet"])
                if c.ausgenommen:
                    rows.append([f"{c.name} (ausgenommen)", str(c.n_ausgenommen), "", "", "–", "–", "–",
                                 "–", "", "ausgenommen: " + ", ".join(c.ausgenommen)])
                continue
            rows.append([c.name, str(c.n_elemente), c.material,
                         f"{c.fy / 1e6:.0f}",
                         f"{w.get('sigma_v', 0) / 1e6:.1f}",
                         f"{w.get('s1', 0) / 1e6:.1f}",
                         f"{w.get('s3', 0) / 1e6:.1f}",
                         f"{c.util:.3f}", c.kombination, c.status()])
            if getattr(c, "zone_n", 0):
                # die Zone steht getrennt da, nicht verschwiegen
                rows.append([f"{c.name} (netzabhängige Stellen)", str(c.zone_n), c.material,
                             f"{c.fy / 1e6:.0f}", f"{c.zone_sigma_v / 1e6:.1f}", "–", "–",
                             f"{c.zone_eta:.3f}", c.zone_kombination, "nur berichtet"])
            if getattr(c, "ausgenommen", None):
                rows.append([f"{c.name} (ausgenommen)", str(c.n_ausgenommen), "", "", "–", "–", "–",
                             "–", "", "ausgenommen: " + ", ".join(c.ausgenommen)])
        return rows


# --------------------------------------------------------------------------
def _ecke_ohne_zone(model, res, i: int, zonen_knoten) -> tuple | None:
    """(Spannung, Eckknoten) der groessten geglaetteten Ecke des Elements
    ``i`` ohne die Ecken auf Knoten der Zonen - None, wenn alle Ecken dort
    liegen. Liest dieselbe Knotentabelle wie Results.solid_rand."""
    from ..elements import solid as sl
    sk = getattr(res, "solid_knoten", None) or {}
    if not sk or "spannung" not in sk:
        return None
    cache = getattr(res, "_cache", None)
    zw = cache.get("ecke_ohne_zone_index") if isinstance(cache, dict) else None
    if zw is None:
        ng = max(1, len(sk["gruppen"]))
        pos = {int(k): j for j, k in enumerate(np.asarray(sk["knoten"], np.int64) * ng
                                                + np.asarray(sk["gruppe"], np.int64))}
        grp = {g: j for j, g in enumerate(sk["gruppen"])}
        zw = (ng, pos, grp, np.asarray(sk["spannung"], float))
        if isinstance(cache, dict):
            cache["ecke_ohne_zone_index"] = zw
    ng, pos, grp, S = zw
    e = model.elements[int(i)]
    if e.typ not in sl.ECKEN_NATUERLICH:
        return None
    g = grp.get((str(getattr(e, "group", "")), str(e.mat)))
    if g is None:
        return None
    nk = len(sl.ECKEN_NATUERLICH[e.typ])
    js = [pos.get(int(n) * ng + g) for n in e.nodes[:nk] if not zonen_knoten[int(n)]]
    js = [j for j in js if j is not None]
    if not js:
        return None
    j = max(js, key=lambda jj: vergleichsspannung(S[jj]))
    return S[j], int(sk["knoten"][j])


def _elementspannungen(model, res, elemente, zonen_knoten=None) -> list:
    """
    Massgebende Spannung je Element. Rueckgabe je Element ein Tripel
    (Elementnummer, Spannungsvektor, Auswertepunkt).

    **Seit dem 22.09.2026 die geglaettete Eckspannung** (res.solid_rand): an
    jedem Eckknoten das Mittel der Elementwerte gleichen Koerpers und
    Werkstoffs, und davon die groesste Ecke des Elements. Bis dahin nahm der
    Nachweis das Maximum ueber Mitte und Ecken **eines** Elements - bei
    linearem Ansatz zeigt die eine Ecke den Momentenverlauf zu hoch, die
    andere zu niedrig. Gemessen am Kragarm-Pruefkoerper (Oberkante bei L/2,
    Soll 355 N/mm2, tests/pruefkoerper.py): hex8 +173 / +65 / +31 N/mm2 bei
    90 / 405 / 2295 FHG, geglaettet -9,6 / +0,8 / +0,2. Fliessende Elemente
    tragen die Spannung ihres naechsten Integrationspunkts bei (dort ist der
    plastische Zustand bekannt, der Wert liegt auf der Fliessflaeche).

    Ohne Knotenwerte (aeltere Ergebnisdatei, Kombination verschiedener
    Situationen) bleibt es beim Elementwert aus res.solid_res.

    ``zonen_knoten`` (bool je Knoten, seit 14.10.2026): Ecken auf Knoten der
    Zonen netzabhaengiger Stellen zaehlen nicht - das Knotenmittel dort
    mischt Zonen- und Aussenelemente. Massgebend ist dann die groesste der
    uebrigen Ecken, ohne solche der Elementwert. Bis zum 14.10.2026 las der
    Nachweis an Aussenelementen auch diese gemischte Ecke: an der Platte mit
    Loch (elastisch) war sie massgebend, 1 315,9 statt 1 287,2 N/mm².
    """
    from ..elements import solid as sl
    u = np.asarray(getattr(res, "u", None))
    if u is None or u.size == 0:
        return []
    u = u.ravel()
    out = []
    rand = {}
    frei: set = set()
    try:
        rand = getattr(res, "solid_rand", {}) or {}
        frei = getattr(res, "solid_rand_frei", set()) or set()
    except Exception:          # noqa: BLE001 - dann der Elementwert, wie bisher
        rand = {}
    for i in elemente:
        if i in rand:
            S, knoten = rand[i]
            if zonen_knoten is not None and zonen_knoten[int(knoten)]:
                ohne = _ecke_ohne_zone(model, res, i, zonen_knoten)
                if ohne is None:
                    roh = getattr(res, "solid_res", {}).get(i)
                    if roh is not None:
                        out.append((i, np.asarray(roh, float), "Element (alle Ecken an der Zone)"))
                    continue
                S, knoten = ohne
                out.append((i, np.asarray(S, float), f"Knoten {int(knoten) + 1} (geglättet, ohne Zonenknoten)"))
                continue
            # an einer freien Oberflaeche auf sigma n = 0 gezogen (solver.rand_projizieren) -
            # der Bericht sagt, welche Randspannung gerechnet wurde
            art = "geglättet, σ·n = 0" if i in frei else "geglättet"
            out.append((i, np.asarray(S, float), f"Knoten {int(knoten) + 1} ({art})"))
            continue
        e = model.elements[i]
        mat = model.materials.get(e.mat)
        if mat is None:
            continue
        X = np.asarray(model.nodes[e.nodes], float)
        try:
            ue = np.concatenate([u[int(n) * 6:int(n) * 6 + 3] for n in e.nodes])
            sp = sl.stress_points(e.typ, X, mat.E, mat.nu, ue)
        except Exception:
            sp = []
        roh = getattr(res, "solid_res", {}).get(i)
        if not sp:
            if roh is None:
                continue
            out.append((i, np.asarray(roh, float), "Mitte"))
            continue
        k = int(np.argmax([vergleichsspannung(x) for x in sp]))
        name = "Mitte" if k == 0 else f"Eckpunkt {k}"
        if roh is not None:
            # ``res.solid_res`` traegt seit dem 20.09.2026 schon den
            # **massgebenden** Auswertepunkt (solver._post_chunk), und zwar
            # mit allem, was sigma = D B u hier weglassen wuerde: der
            # plastischen Vorspannung D eps_p und - mit
            # Model.knotendilatation - dem gemittelten volumetrischen Anteil.
            # Gemessen am Stauchwuerfel (384 tet4, S355, p = 420 MPa,
            # Fliessen an, 20.09.2026): sigma_v,max 381,2 MPa im Ergebnis
            # gegen 3300,7 MPa neu gerechnet - Ausnutzung 1,07 gegen 9,3.
            # Die Nachrechnung hier benennt nur noch die **Stelle**.
            out.append((i, np.asarray(roh, float), name))
            continue
        out.append((i, np.asarray(sp[k], float), name))
    return out


def _koerper(model):
    """Zuordnung Volumenelement -> zusammenhaengender Koerper.

    Zwei Volumenelemente gehoeren zum selben Koerper, wenn sie einen Knoten
    teilen - ueber Nachbarn auch mittelbar. Gerechnet wird das als
    Zusammenhangskomponente des zweiteiligen Graphen Element/Knoten
    (``scipy.sparse.csgraph``) und nicht mit einer eigenen Schleife: bei den
    288 Elementen einer Pruefung ist die Art der Rechnung gleich, bei den
    645 934 Volumenelementen des Drehlagers nicht.

    Rueckgabe: ``(marke, gruppen)`` - Element -> Koerpernummer und
    Koerpernummer -> Elementliste.
    """
    import numpy as _np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from ..elemente import VOLUMEN_TYPEN
    idx, zeilen, spalten = [], [], []
    for i, e in enumerate(model.elements):
        if e.typ not in VOLUMEN_TYPEN:
            continue
        r = len(idx)
        idx.append(i)
        for k in e.nodes:
            zeilen.append(r)
            spalten.append(int(k))
    m = len(idx)
    if not m:
        return {}, {}
    n = m + int(model.nn)
    G = coo_matrix((_np.ones(len(zeilen)),
                    (_np.asarray(zeilen, int), m + _np.asarray(spalten, int))),
                   shape=(n, n))
    _anz, lab = connected_components(G, directed=False)
    marke, gruppen = {}, {}
    for r, i in enumerate(idx):
        g = int(lab[r])
        marke[i] = g
        gruppen.setdefault(g, []).append(i)
    return marke, gruppen


def _erzeugnisdicke(model, elemente, koerper=None) -> float:
    """Die Erzeugnisdicke eines Volumenbereichs [m] - die **kleinste**
    Abmessung des umschliessenden Quaders des **ganzen Koerpers**, zu dem
    seine Elemente gehoeren.

    EN 1993-1-1 Tab. 3.1 mindert die Streckgrenze mit der Erzeugnisdicke ab
    (S355: 355 N/mm2 bis 40 mm, darueber 335). Ein Volumenbereich hat keine
    Dicke im Sinne eines Querschnitts; er ist aus einem Erzeugnis gefertigt,
    und dessen Dicke ist die kleinste Abmessung: bei einer Platte ihre Dicke,
    bei einem Rundstahl sein Durchmesser, bei einem Block seine kuerzeste
    Kante.

    **Warum der ganze Koerper und nicht die Auswahl?** Weil die Auswahl dem
    Anwender gehoert. An einem Block 300 x 300 x 200 mm, vernetzt mit
    6 x 6 x 8 Elementen, misst der ganze Koerper 200 mm (f_y = 335), eine
    einzelne Elementlage aber 25 mm (f_y = 355): dieselbe Stelle, 6,0 % auf
    der **unsicheren** Seite, nur weil weniger markiert war. Der Koerper ist
    dagegen unabhaengig davon, was der Anwender gerade ausgewaehlt hat.

    Bei einem **geschweissten** Bauteil ist der Koerper umgekehrt zu dick -
    massgebend ist dort die Blechdicke. Darum ist die Dicke am Volumenbereich
    angebbar (``Volumenbereich.dicke``), die selbst gesetzte steht im Nachweis
    (``werte["dicke"]``), und wenn sie die Streckgrenze abmindert, sagt es der
    Bericht als Hinweis.

    Bis zum 22.09.2026 wurde mit ``yield_strength(0.0)`` gerechnet, also
    **immer mit der duennsten Stufe**: ein Lagerblock von 80 mm wies sich mit
    355 statt 335 N/mm2 nach, eta fiel rund 6 % zu klein aus - auf der
    unsicheren Seite. Der Stabnachweis macht es seit jeher richtig
    (``design.py``: ``mat.yield_strength(sec.t_max)``).
    """
    import numpy as _np
    marke, gruppen = koerper if koerper is not None else _koerper(model)
    kn = set()
    for i in elemente:
        i = int(i)
        if not 0 <= i < len(model.elements):
            continue
        for j in gruppen.get(marke.get(i, -1), (i,)):
            kn.update(int(x) for x in model.elements[j].nodes)
    if not kn:
        return 0.0
    X = _np.asarray(model.nodes, float)[sorted(kn)]
    d = X.max(axis=0) - X.min(axis=0)
    return float(d.min())


def _material(model, elemente, dicke: float = 0.0):
    """(Materialname, f_y) des Bereichs; f_y der schwaechste im Bereich.

    ``dicke`` ist die Erzeugnisdicke [m] fuer die Abminderung nach
    EN 1993-1-1 Tab. 3.1 - siehe :func:`_erzeugnisdicke`.
    """
    namen, fy = [], []
    for i in elemente:
        e = model.elements[i]
        mat = model.materials.get(e.mat)
        if mat is None:
            continue
        if e.mat not in namen:
            namen.append(e.mat)
        f = mat.yield_strength(dicke) or 0.0
        if f > 0:
            fy.append(f)
    return "/".join(namen), (min(fy) if fy else 0.0)


def check_volumen(model, analysis, combos: list = None, progress=None) -> VolumenResults:
    """Alle Volumenbereiche des Modells ueber alle GZT-Kombinationen nachweisen."""
    from .design import _uls_results
    warnungen: list = []
    # Nur wenn ein Bereich einen Nachweis verlangt: sonst meldete
    # _uls_results fehlende Kombinationen fuer einen Nachweis, der gar nicht
    # gefuehrt wird (wie check_members, Gegenpruefung 23.09.2026)
    zu_pruefen = any(vb.design for vb in model.volumenbereiche.values())
    ergebnisse = (_uls_results(model, analysis, combos, warnungen=warnungen)
                  if zu_pruefen else {})
    ds = model.design
    out = VolumenResults(kombinationen=list(ergebnisse), settings={
        "gamma_M0": ds.gamma_M0,
        "Norm": "DIN EN 1993-1-1, 6.2.1(5) (Vergleichsspannung nach von Mises)"},
        warnungen=warnungen)
    koerper = _koerper(model)
    # Zonen auffaelliger netzabhaengiger Stellen je Ergebnis (seit 10.10.2026)
    from .. import spitzenanzeige as _sa
    zonen = _sa.nachweis_zonen(model, ergebnisse) if zu_pruefen else {}
    # Ergebnisse aus plastischer Rechnung: Nachweis ueber die plastische
    # Hauptdehnung, ohne auswertbare Dehnung nicht bewertet (13.10.2026)
    alle = analysis.all_results() if hasattr(analysis, "all_results") else {}
    plastisch = [k for k, r in ergebnisse.items() if ist_plastisch(r, alle)]
    dehnungen: dict = {}
    ohne_dehnung: dict = {}
    for k in plastisch:
        d, grund = ip_dehnungen(ergebnisse[k])
        if d is None:
            ohne_dehnung[k] = grund
        else:
            dehnungen[k] = d
    je_koerper = koerper_je_element(model) if zu_pruefen else {}
    for i, (name, vb) in enumerate(model.volumenbereiche.items()):
        c = VolumenCheck(name, beschreibung=vb.beschreibung,
                         n_elemente=len(vb.elemente), singular=bool(vb.singular))
        if not vb.design:
            # gewollt nicht gefuehrt - kein Fehler, siehe VolumenCheck.ausgeschaltet
            c.ausgeschaltet = True
            out.bereiche[name] = c
            continue
        # Die Erzeugnisdicke: entweder am Bereich angegeben oder aus dem
        # zusammenhaengenden Koerper bestimmt (siehe _erzeugnisdicke). Sie
        # geht in die Abminderung nach EN 1993-1-1 Tab. 3.1 und steht weiter
        # unten im Nachweis - **nicht hier**: c.werte wird in der Schleife
        # ueber die Kombinationen durch das Ergebnis der massgebenden
        # Kombination ersetzt, was hier hineingeschrieben wird, ist weg.
        # vom Nachweis ausgenommene Koerper und Werkstoffe (13.10.2026): sie
        # gehen weder in f_y noch in die Dicke noch in den Nachweis ein
        vb_el, c.ausgenommen, c.n_ausgenommen = ausgenommene(model, vb.elemente, je_koerper)
        if c.n_ausgenommen and not vb_el:
            c.alle_ausgenommen = True
            out.bereiche[name] = c
            continue
        gesetzt = float(getattr(vb, "dicke", 0.0) or 0.0) > 0
        t_erz = (float(vb.dicke) if gesetzt
                 else _erzeugnisdicke(model, vb_el, koerper))
        c.material, c.fy = _material(model, vb_el, t_erz)
        _mat0, fy_duenn = _material(model, vb_el, 0.0)
        if c.fy <= 0:
            c.fehler = ("kein Material mit Streckgrenze im Bereich - "
                        "der Nachweis braucht f_y")
            out.bereiche[name] = c
            continue
        if ohne_dehnung:
            # plastisch, aber keine auswertbare Dehnung: kein Zahlenwert
            namen = list(ohne_dehnung)
            c.nicht_bewertet = ", ".join(namen[:5]) + (" …" if len(namen) > 5 else "")
            gruende = list(dict.fromkeys(ohne_dehnung.values()))
            c.fehler = (f"{NICHT_BEWERTET}: {c.nicht_bewertet} - " + "; ".join(gruende))
            out.bereiche[name] = c
            continue
        if dehnungen:
            c.eps_grenze = float(getattr(vb, "eps_grenze", EPS_GRENZE))
            if not c.eps_grenze > 0.0:
                c.fehler = (f"Grenzwert der plastischen Hauptdehnung {prozent(c.eps_grenze)} % - er "
                            "muss größer 0 sein (Vorgabe 5 % nach " + NORM_DEHNUNG + ")")
                out.bereiche[name] = c
                continue
        in_zone: set = set()
        for kname, res in ergebnisse.items():
            # Elemente in den Zonen auffaelliger Stellen (Kraft ohne
            # Auflageflaeche, Plan Singularitaeten Paket 2): nur berichtet, mit
            # ihrer Spitze getrennt - ihr Wert ist eine Eigenschaft des Netzes
            zone = zonen.get(kname) or set()
            elemente = vb_el
            if kname in dehnungen:
                # plastische Rechnung: groesste plastische Hauptdehnung am
                # Integrationspunkt gegen den Grenzwert (13.10.2026)
                innen = {int(e) for e in vb_el if int(e) in zone}
                aussen = {int(e) for e in vb_el if int(e) not in zone}
                in_zone.update(innen)
                if innen:
                    ez, elz, _pz, _oz = _dehnung_max(dehnungen[kname], innen)
                    if ez / c.eps_grenze >= c.zone_eta:
                        c.zone_eta, c.zone_eps = float(ez / c.eps_grenze), float(ez)
                        c.zone_element, c.zone_kombination = int(elz), kname
                if not aussen:
                    continue
                e1, el, ip, ort = _dehnung_max(dehnungen[kname], aussen)
                eta = e1 / c.eps_grenze
                c.je_kombination.append({"kombination": kname, "element": el, "eps_p1": e1,
                                         "eta": eta, "kriterium": "dehnung"})
                if eta >= c.util:
                    c.util, c.kombination, c.element = float(eta), kname, int(el)
                    c.kriterium, c.eps_p1, c.ip, c.ort = "dehnung", float(e1), int(ip), list(ort or [])
                    c.werte = {"eps_p1": float(e1), "eps_grenze": c.eps_grenze}
                continue
            if zone:
                innen = [e for e in vb_el if int(e) in zone]
                elemente = [e for e in vb_el if int(e) not in zone]
                in_zone.update(int(e) for e in innen)
                zw = _elementspannungen(model, res, innen) if innen else []
                zk_ = np.zeros(int(model.nn), bool)
                for e_ in zone:
                    if 0 <= int(e_) < len(model.elements):
                        zk_[np.asarray(model.elements[int(e_)].nodes, np.int64)] = True
                if zw:
                    zsv = [vergleichsspannung(x) for _e, x, _pt in zw]
                    jz = int(np.argmax(zsv))
                    eta_z = zsv[jz] / (c.fy / ds.gamma_M0)
                    if eta_z >= c.zone_eta:
                        c.zone_eta, c.zone_sigma_v = float(eta_z), float(zsv[jz])
                        c.zone_element, c.zone_kombination = int(zw[jz][0]), kname
            werte = (_elementspannungen(model, res, elemente, zk_ if zone else None)
                     if elemente else [])
            if not werte:
                continue
            svs = np.array([vergleichsspannung(sp) for _e, sp, _pt in werte])
            j = int(np.argmax(svs))
            el, sp, punkt = werte[j]
            d = punkt_nachweis(sp, c.fy, ds.gamma_M0)
            d["sigma_v_mittel"] = float(svs.mean())
            d["spitze"] = float(svs[j] / svs.mean()) if svs.mean() > 0 else 1.0
            d["punkt"] = punkt
            c.je_kombination.append({"kombination": kname, "element": el,
                                     "sigma_v": d["sigma_v"], "eta": d["eta"],
                                     "s1": d["s1"], "s3": d["s3"]})
            if d["eta"] >= c.util:
                c.util, c.kombination, c.element, c.werte = (
                    d["eta"], kname, el, d)
                c.kriterium = ""
        c.zone_n = len(in_zone)
        zonentext = ""
        if c.zone_n:
            zonentext = (
                f"{anzahl(c.zone_n, 'Element', 'Elemente')} des Bereichs "
                f"{'liegt' if c.zone_n == 1 else 'liegen'} in netzabhängigen Stellen (Zonen "
                "auffälliger Stellen, an denen Kraft ohne Auflagefläche in das Volumen geht) und "
                f"{'ist' if c.zone_n == 1 else 'sind'} nur berichtet: dort σ_v bis "
                f"{c.zone_sigma_v / 1e6:.1f} N/mm², η = {c.zone_eta:.3f} ({c.zone_kombination}, "
                f"Element {c.zone_element + 1}) – netzabhängig, nicht für den Nachweis. "
                "Außerhalb zählen nur Elementecken, die nicht auf einem Knoten der Zonen liegen.")
        if not c.je_kombination and c.zone_n:
            c.fehler = ("alle Elemente des Bereichs liegen in netzabhängigen Stellen - "
                        "nur berichtet. " + zonentext)
            out.bereiche[name] = c
            continue
        if not c.je_kombination:
            c.fehler = ("keine Volumenspannungen in den Ergebnissen - "
                        "wurde mit Volumenelementen gerechnet?" if ergebnisse else
                        "kein Ergebnis einer GZT-Kombination - siehe Warnung")
            out.bereiche[name] = c
            continue
        if c.kriterium == "dehnung":
            _dehnung_abschliessen(model, c, vb, je_koerper)
            out.bereiche[name] = c
            if progress:
                progress(f"Volumenbereich {name} ({i + 1}/{len(model.volumenbereiche)})")
            continue
        w = c.werte
        w["dicke"] = t_erz
        w["dicke_gesetzt"] = gesetzt
        if not gesetzt and c.fy < fy_duenn:
            c.hinweise.append(
                f"Erzeugnisdicke {t_erz * 1e3:.0f} mm angesetzt - die kleinste "
                "Abmessung des Körpers, zu dem die Elemente gehören. Die "
                f"Streckgrenze ist damit nach EN 1993-1-1 Tab. 3.1 auf "
                f"{c.fy / 1e6:.0f} N/mm² abgemindert (dünnste Stufe: "
                f"{fy_duenn / 1e6:.0f}). Ist das Bauteil aus Blechen "
                "geschweißt, ist die Blechdicke maßgebend und nicht die "
                "Abmessung des Körpers - dann die Erzeugnisdicke am "
                "Volumenbereich angeben.")
        if w.get("dreiachsiger_zug"):
            c.hinweise.append(
                f"Dreiachsiger Zug (σ_3 = {w['s3'] / 1e6:.1f} N/mm² > 0) bei einer "
                f"Mehrachsigkeit h = σ_m/σ_v = {w['h']:.2f}. Die "
                "Verformungsfähigkeit ist dort eingeschränkt; die Zähigkeit des "
                "Stahls ist nach DIN EN 1993-1-10 zu beurteilen (Stahlsorte, "
                "Erzeugnisdicke, tiefste Bauteiltemperatur). Dieser Nachweis wird "
                "hier nicht geführt.")
        if w.get("spitze", 1.0) > SPITZE_GRENZE and not c.singular:
            c.hinweise.append(
                f"Die Spitzenspannung liegt um den Faktor {w['spitze']:.1f} über "
                "dem Mittel des Bereichs. Das deutet auf eine Spannungs-"
                "singularität hin (einspringende Ecke, Einzellast, Punktlager). "
                "Dort wächst die Spannung mit jeder Netzverfeinerung; der "
                "Nachweis gegen f_y ist dann nicht aussagekräftig. Entweder die "
                "Ausrundung modellieren oder den Bereich als „singulär“ "
                "kennzeichnen und gesondert beurteilen.")
        if vb.ausrundung > 0:
            V = _bereichsvolumen(model, vb.elemente)
            h = (V / max(len(vb.elemente), 1)) ** (1 / 3)
            c.werte["elementgroesse"] = h
            c.werte["ausrundung"] = vb.ausrundung
            if h > vb.ausrundung / 3.0:
                c.hinweise.append(
                    f"Mittlere Elementgröße {h * 1e3:.1f} mm gegen Kerbradius "
                    f"{vb.ausrundung * 1e3:.1f} mm: für die Kerbspannung sollten "
                    "mindestens drei Elemente über den Radius liegen "
                    f"(h ≤ {vb.ausrundung / 3 * 1e3:.1f} mm). Das Netz ist dort "
                    "zu grob, die Spitzenspannung wird unterschätzt.")
        if zonentext:
            c.hinweise.append(zonentext + f" Der Nachweis gilt außerhalb: η = {c.util:.3f}.")
        if c.singular:
            c.hinweise.append(
                "Der Bereich ist als singulär gekennzeichnet: die Spannungen "
                "werden berichtet, aber nicht als Nachweis geführt.")
        out.bereiche[name] = c
        if progress:
            progress(f"Volumenbereich {name} ({i + 1}/{len(model.volumenbereiche)})")
    return out


def _dehnung_abschliessen(model, c: VolumenCheck, vb, je_koerper: dict) -> None:
    """Bauteil, Werkstoff und Hinweise des Nachweises ueber die plastische
    Hauptdehnung (13.10.2026)."""
    if c.element >= 0:
        c.bauteil = je_koerper.get(c.element, "") or str(getattr(model.elements[c.element], "group", "") or "")
        c.werkstoff_ort = model.elements[c.element].mat
    if c.element < 0:
        c.hinweise.append("Im Bereich fließt kein Integrationspunkt: ε_p,1 = 0.")
    if c.zone_n:
        c.hinweise.append(
            f"{anzahl(c.zone_n, 'Element', 'Elemente')} des Bereichs "
            f"{'liegt' if c.zone_n == 1 else 'liegen'} in netzabhängigen Stellen (Zonen auffälliger "
            "Stellen, an denen Kraft ohne Auflagefläche in das Volumen geht) und "
            f"{'ist' if c.zone_n == 1 else 'sind'} nur berichtet: dort ε_p,1 bis "
            f"{c.zone_eps * 100:.3f} %, η = {c.zone_eta:.3f} ({c.zone_kombination}"
            + (f", Element {c.zone_element + 1}" if c.zone_element >= 0 else "")
            + f") – netzabhängig, nicht für den Nachweis. Der Nachweis gilt außerhalb: η = {c.util:.3f}.")
    if c.ausgenommen:
        c.hinweise.append(
            f"Vom Nachweis ausgenommen: {', '.join(c.ausgenommen)} "
            f"({anzahl(c.n_ausgenommen, 'Element', 'Elemente')}; Schalter „vom Volumennachweis "
            "ausnehmen“ am Werkstoff bzw. Körper).")
    if c.singular:
        c.hinweise.append(
            "Der Bereich ist als singulär gekennzeichnet: die Dehnungen "
            "werden berichtet, aber nicht als Nachweis geführt.")


def _bereichsvolumen(model, elemente) -> float:
    """Summe der Elementvolumina [m^3]."""
    from ..elements import solid as sl
    V = 0.0
    for i in elemente:
        e = model.elements[i]
        X = np.asarray(model.nodes[e.nodes], float)
        try:
            if e.typ == "tet4":
                _dN, v = sl.tet4_shape_grad(X)
                V += abs(v)
            else:
                # Naeherung ueber die Bounding-Box des Elements
                d = X.max(axis=0) - X.min(axis=0)
                V += float(np.prod(d)) * (1.0 / 6.0 if e.typ == "tet10" else 1.0)
        except Exception:
            continue
    return V
