"""
Hinweis: Theorie II. Ordnung, alpha_cr und Knicken enthalten kein
Biegedrillknicken (Runde k8, 15.11.2026, vom Anwender freigegeben, „2 ja“).

Die geometrische Steifigkeit der Balken (elements/beam3d.kg_local_beam,
assemble.geometric_stiffness) enthaelt nur die Normalkraft - samt Wagner-
Glied N I_p/A fuer das Drillknicken -, nicht das Momentenglied M ∫v'φ' dx,
das Biegung, seitliches Ausweichen und Verdrillen koppelt. Auch mit dem
siebten Freiheitsgrad (Woelbkrafttorsion) wirkt k_G nur auf die 12 Stabend-
FHG. Theorie III. Ordnung (korotational) enthaelt die Kopplung. Gemessen
(Hintergrund ag_k8_starr1/2): Kragstuetze mit exzentrischer Last,
Verzweigungsfaktor ohne Momentenglied 5 bis 8 % zu hoch, Verschiebung 3,5 bis
6 % zu klein.

Kein Wert wird geaendert. Ein biegesteifer Stab mit Druck und Biegung, dessen
Biegedrillknicken nicht anderweitig erfasst ist, bekommt einen Hinweis -
eine Zeile je Rechnung mit der Zahl der Staebe und den ersten Namen.

Kriterium (je Stab bzw. gerader Kette von Balken ohne Stab):

1. Nur Balken (Fachwerkstab und Seil haben keine Biegung).
2. Erfasst: Stab vom Querschnittstyp I mit Nachweis nach EC3 und Haken
   „Biegedrillknicken“ - der Ersatzstabnachweis 6.3.2/6.3.3 fuehrt chi_LT
   auch mit Schnittgroessen nach Theorie II. Ordnung (ec3.design.
   check_member, ec3.stability.member_stability).
3. Nicht gefaehrdet: Hohlprofile (RHS, CHS) und Querschnitte ohne starke
   Achse (I_y = I_z, etwa Kreis, Quadrat) - DIN EN 1993-1-1, 6.3.2.1(2)
   (quadratische und runde Hohlprofile, Kastenquerschnitte) und 6.3.1.4(1)
   (Drill- und Biegedrillknicken nur bei offenen Querschnitten).
4. Im Grundzustand (Theorie I. Ordnung) Druck N (ueber RELEVANZ N_cr,schwach)
   und Biegemoment M um die starke Achse. Der gekoppelte Verzweigungsfaktor
   des gabelgelagerten doppeltsymmetrischen Stabs unter N und konstantem M
   (C1 = 1, der kleinste Fall) folgt aus

       (1 - l N/N_cr,z) (1 - l N/N_cr,T) = (l M/M_cr)²,

   M_cr² = i_0² N_cr,z N_cr,T. Hinweis, wenn er unter GRENZE_FAKTOR = 25
   liegt (darueber gilt N/N_cr <= 0,04 und M/M_cr <= 0,04 - nach
   EN 1993-1-1 6.3.1.2(4) und 6.3.2.2(4) mit lambda_LT,0 = 0,2 darf die
   Stabilitaet dann vernachlaessigt werden) und mindestens GRENZE_ABFALL =
   2 % unter dem Faktor ohne Momentenglied, min(N_cr,z; N_cr,T)/N.
   Laengen: Knicklaenge um die schwache Achse und Abstand der seitlichen
   Halterungen L_LT am Stab, sonst die Stablaenge.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np

#: Woran der Hinweis zu erkennen ist (Sammeln fuer Protokoll und Zusammenfassung)
BDK_KENNUNG = "enthalten kein Biegedrillknicken"

#: gekoppelter Verzweigungsfaktor ab dem kein Hinweis kommt: N/N_cr <= 0,04
#: und M/M_cr <= 0,04 (EN 1993-1-1 6.3.1.2(4), 6.3.2.2(4), lambda_LT,0 = 0,2)
GRENZE_FAKTOR = 25.0

#: so viel muss das Momentenglied den Verzweigungsfaktor mindestens senken
#: (wie der Hinweis zur Laengslast: unter 2 % keine Meldung)
GRENZE_ABFALL = 0.02

#: Druck zaehlt ab diesem Anteil der Knicklast um die schwache Achse (wie
#: stabteilung.RELEVANZ)
RELEVANZ = 1e-3

#: so viele Namen nennt der Hinweis
NAMEN = 3

#: Hohlprofile - EN 1993-1-1 6.3.2.1(2), 6.3.1.4(1)
GESCHLOSSEN = ("RHS", "CHS")

#: Querschnitte ohne starke Achse: I_schwach / I_stark ab hier
OHNE_STARKE_ACHSE = 0.99

TH2_WO = "Theorie II. Ordnung und α_cr"
KNICK_WO = "Die Knickfaktoren"


def verzweigungsfaktoren(r_z: float, r_T: float, r_LT: float) -> tuple:
    """(gekoppelt, ohne Momentenglied) - die kleinsten positiven
    Verzweigungsfaktoren l von (1 - l r_z)(1 - l r_T) = (l r_LT)² bzw. mit
    r_LT = 0; r_z = N/N_cr,z, r_T = N/N_cr,T, r_LT = M/M_cr (alle >= 0).
    Stabile Form der Wurzel: l = 2 / (r_z + r_T + sqrt((r_z - r_T)² + 4 r_LT²))."""
    r_z, r_T, r_LT = (max(float(x), 0.0) for x in (r_z, r_T, r_LT))
    s = r_z + r_T
    d = math.sqrt((r_z - r_T) ** 2 + 4.0 * r_LT ** 2)
    gek = 2.0 / (s + d) if s + d > 0 else math.inf
    ohne = 1.0 / max(r_z, r_T) if max(r_z, r_T) > 0 else math.inf
    return gek, ohne


def bdk_text(namen: list, wo: str = TH2_WO) -> str:
    """Die Zeile zu den Staeben ``namen`` (alle; genannt werden die ersten
    :data:`NAMEN`)."""
    from .begriffe import anzahl
    n = len(namen)
    liste = ", ".join(namen[:NAMEN])
    teil = (f"{anzahl(n, 'Stab', 'Stäbe')} mit Druck und Biegung"
            + (f", z. B. {liste}." if n > NAMEN else f": {liste}."))
    return (f"{wo} {BDK_KENNUNG} (Momentenglied der geometrischen Steifigkeit fehlt): {teil} "
            "Biegedrillknicken mit χ_LT nachweisen oder Theorie III. Ordnung rechnen.")


def _erfasst(model, name: str, sec) -> bool:
    """Biegedrillknicken anderweitig erfasst oder nicht maßgebend (Punkte 2
    und 3 des Kriteriums)?"""
    typ = getattr(sec, "typ", "")
    if typ in GESCHLOSSEN:
        return True
    Iy, Iz = float(sec.Iy or 0.0), float(sec.Iz or 0.0)
    if max(Iy, Iz) <= 0 or min(Iy, Iz) >= OHNE_STARKE_ACHSE * max(Iy, Iz):
        return True
    mem = (getattr(model, "members", None) or {}).get(name) if name else None
    return bool(mem is not None and typ == "I" and mem.design and mem.lt_check)


def kandidaten(model, aktiv=None) -> list:
    """[(Anzeige, Name, [Balken], Querschnitt, Werkstoff)] der Staebe (und
    geraden Ketten von Balken ohne Stab: Name "", Anzeige "Element n" ab 0),
    deren Biegedrillknicken nicht anderweitig erfasst ist - ohne Rechnung."""
    from .stabteilung import _stabgruppen
    out = []
    for name, els in _stabgruppen(model, aktiv):
        balken = [int(i) for i in els if model.elements[int(i)].typ == "beam"]
        if not balken:
            continue
        e0 = model.elements[balken[0]]
        sec = model.sections.get(e0.sec)
        mat = model.materials.get(e0.mat)
        if sec is None or mat is None or _erfasst(model, name, sec):
            continue
        out.append((name or f"Element {min(balken)}", name, balken, sec, mat))
    return out


def _stab_bewerten(model, name: str, balken: list, sec, mat, kraefte) -> bool:
    """Punkt 4 des Kriteriums fuer einen Stab; ``kraefte(i)`` liefert die
    Schnittgroessen des Grundzustands an den Stellen von Balken i."""
    Iy, Iz = float(sec.Iy), float(sec.Iz)
    stark_y = Iy >= Iz
    I_s = Iz if stark_y else Iy
    N_ed = 0.0
    M_ed = 0.0
    for i in balken:
        f = kraefte(i)
        N_ed = max(N_ed, -float(np.min(f["N"])))
        M_ed = max(M_ed, float(np.max(np.abs(f["My"] if stark_y else f["Mz"]))))
    if N_ed <= 0.0 or M_ed <= 0.0:
        return False
    L = sum(model.element_length(i) for i in balken)
    mem = (getattr(model, "members", None) or {}).get(name) if name else None
    if mem is not None:
        if stark_y:
            L_s = mem.Lcr_z if mem.Lcr_z else mem.beta_z * L
        else:
            L_s = mem.Lcr_y if mem.Lcr_y else mem.beta_y * L
        L_LT = mem.L_LT if mem.L_LT else L
    else:
        L_s, L_LT = L, L
    if L_s <= 0 or L_LT <= 0 or float(sec.A) <= 0:
        return False
    E, G = float(mat.E), float(mat.G)
    Iw = float(getattr(sec, "Iw", 0.0) or 0.0)
    It = float(sec.It or 0.0)
    i0 = (Iy + Iz) / float(sec.A)
    Ncr_s = math.pi ** 2 * E * I_s / L_s ** 2
    if N_ed <= RELEVANZ * Ncr_s:
        return False
    Ncr_s_LT = math.pi ** 2 * E * I_s / L_LT ** 2
    Ncr_T = (G * It + math.pi ** 2 * E * Iw / L_LT ** 2) / i0
    Mcr = math.sqrt(max(Ncr_s_LT * Ncr_T * i0, 0.0))
    r_LT = M_ed / Mcr if Mcr > 0 else math.inf
    if not math.isfinite(r_LT):
        return True
    gek, ohne = verzweigungsfaktoren(N_ed / Ncr_s, N_ed / Ncr_T if Ncr_T > 0 else math.inf, r_LT)
    return gek < GRENZE_FAKTOR and gek < (1.0 - GRENZE_ABFALL) * ohne


def bdk_staebe(model, aktiv=None, res=None, u=None, feq=None, q=None) -> list:
    """Die Namen der Staebe mit Druck und Biegung, deren Biegedrillknicken
    die Rechnung mit K_G nicht enthaelt (Kriterium oben). Grundzustand:
    ``res`` (Results mit beam_end/beam_q) oder ``u`` mit den Stablasten
    ``feq`` und den Abschnittslasten ``q`` (solver.case_loads). Ein Hinweis
    sperrt nie eine Rechnung: bei einem Fehler die leere Liste."""
    try:
        kand = kandidaten(model, aktiv)
        if not kand:
            return []
        from .solver import beam_station_forces
        if res is None:
            if u is None:
                return []
            from .assemble import stab_endkraefte_linear
            uu = np.asarray(u, float).ravel()
            feq = feq or {}
            q = q or {}
            ende, last = {}, {}
            for _a, _n, balken, _s, _m in kand:
                for i in balken:
                    ende[i] = stab_endkraefte_linear(model, model.elements[i], uu, feq.get(i))[0]
                    if i in q:
                        last[i] = np.asarray(q[i], float)
            res = SimpleNamespace(beam_end=ende, beam_q=last)

        def kraefte(i):
            return beam_station_forces(model, res, i, 9)
        return [anzeige for anzeige, name, balken, sec, mat in kand
                if _stab_bewerten(model, name, balken, sec, mat, kraefte)]
    except Exception:                       # noqa: BLE001 - ein Hinweis sperrt keine Rechnung
        return []


def hinweis(model, aktiv=None, wo: str = TH2_WO, **grund) -> tuple:
    """(Text oder "", Namen) - :func:`bdk_staebe` und :func:`bdk_text`."""
    namen = bdk_staebe(model, aktiv, **grund)
    return (bdk_text(namen, wo) if namen else ""), namen


def merken(info, text: str, namen: list) -> None:
    """Den Hinweis an Th2Info haengen; die Namen fuer die eine Zeile je
    Rechnung (solver._bdk_hinweise_sammeln)."""
    if not text:
        return
    if text not in info.hinweise:
        info.hinweise.append(text)
    alt = list(getattr(info, "bdk_staebe", None) or [])
    info.bdk_staebe = alt + [n for n in namen if n not in alt]
