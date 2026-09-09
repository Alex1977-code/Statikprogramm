"""
Ermuedungsnachweis nach DIN EN 1993-1-9 (Nennspannungskonzept).

Woehlerlinien (Bild 7.1):
    Normalspannung: m = 3 bis N_D = 5e6 (Delta_sigma_D = 0.737 Delta_sigma_C),
                    m = 5 bis N_L = 1e8 (Delta_sigma_L = 0.549 Delta_sigma_D),
                    darunter keine Schaedigung.
    Schubspannung:  m = 5 bis N_L = 1e8 (Delta_tau_L = 0.457 Delta_tau_C).
Schadensakkumulation nach Palmgren-Miner: D = sum(n_i / N_Ri) <= 1.
Teilsicherheitsbeiwerte gamma_Mf nach Tabelle 3.1, gamma_Ff = 1.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..model import Model, Member

# Kerbfallklassen [MPa] (Tabellen 8.1 - 8.10, Auswahl)
DETAIL_CATEGORIES = [160, 140, 125, 112, 100, 90, 80, 71, 63, 56, 50, 45, 40, 36]
DETAIL_CATEGORIES_SHEAR = [100, 80]

GAMMA_MF = {("damage_tolerant", "low"): 1.00, ("damage_tolerant", "high"): 1.15,
            ("safe_life", "low"): 1.15, ("safe_life", "high"): 1.35}

DETAIL_EXAMPLES = {
    160: "Grundwerkstoff gewalzt, Oberflaeche geschliffen (Tab. 8.1, 1)",
    140: "Grundwerkstoff gewalzt, Walzhaut, scharfe Kanten entfernt (Tab. 8.1, 2)",
    125: "Laengsnaht durchgeschweisst, geprueft (Tab. 8.2); Brennschnitt maschinell (8.1, 3)",
    112: "Laengsnaht Kehl-/Stumpfnaht automatisch (Tab. 8.2, 3); Stumpfstoss bearbeitet (8.3, 1)",
    100: "Stumpfstoss quer, geprueft, Schweissnahtueberhoehung <= 10 % (Tab. 8.3, 3)",
    90: "Stumpfstoss quer ohne Bearbeitung (Tab. 8.3, 5); Laengssteife <= 50 mm",
    80: "Quersteife/Rippe angeschweisst, l <= 50 mm (Tab. 8.4, 7); Laengssteife 50-80 mm",
    71: "Quersteife > 50 mm, Laengssteife 80-100 mm (Tab. 8.4); Schraubenverbindung gleitfest",
    63: "Laengssteife > 100 mm (Tab. 8.4, 6); Deckblech Ende (8.5)",
    56: "Deckblech-Ende t <= 20 mm (Tab. 8.5, 1); Konsolanschluss",
    50: "Kehlnahtanschluss quer (Tab. 8.5); Schraube mit Zug (Tab. 8.1, 14: 50 fuer Schrauben)",
    45: "Deckblech Ende t > 20 mm; Halbrundnaht am Flanschrand (Tab. 8.5)",
    40: "Kehlnahtanschluss ohne Bearbeitung, dick (Tab. 8.5, 3)",
    36: "Kehlnaht auf Zug/Schub (Tab. 8.5, 8); Schraubengewinde unter Zug",
}


def sn_life(delta_sigma: float, category: float, gamma_Mf: float = 1.0,
            shear: bool = False) -> float:
    """Ertragbare Lastspielzahl N_R fuer eine Schwingbreite [Pa] und Kerbfall [Pa]."""
    dc = category / gamma_Mf
    if delta_sigma <= 0:
        return np.inf
    if shear:
        dL = (2.0 / 100.0) ** 0.2 * dc
        if delta_sigma < dL:
            return np.inf
        return 2e6 * (dc / delta_sigma) ** 5
    dD = (2.0 / 5.0) ** (1.0 / 3.0) * dc
    dL = (5.0 / 100.0) ** 0.2 * dD
    if delta_sigma >= dD:
        return 2e6 * (dc / delta_sigma) ** 3
    if delta_sigma >= dL:
        return 5e6 * (dD / delta_sigma) ** 5
    return np.inf


def damage(ranges: list[tuple[float, float]], category: float, gamma_Mf: float = 1.0,
           shear: bool = False) -> float:
    """Palmgren-Miner: ranges = [(Delta_sigma_i [Pa], n_i), ...]."""
    D = 0.0
    for ds, n in ranges:
        N = sn_life(ds, category, gamma_Mf, shear)
        if np.isfinite(N) and N > 0:
            D += n / N
    return D


def equivalent_range(ranges: list[tuple[float, float]], m: float = 3.0, N_ref: float = 2e6) -> float:
    """Schadensaequivalente Einstufen-Schwingbreite bei N_ref (Steigung m)."""
    s = sum(n * ds ** m for ds, n in ranges)
    return float((s / N_ref) ** (1.0 / m)) if s > 0 else 0.0


# --------------------------------------------------------------------------
# Zaehlverfahren (EN 1993-1-9, Anhang A)
# --------------------------------------------------------------------------
def umkehrpunkte(werte) -> list:
    """Nur die Umkehrpunkte eines Verlaufs - alles dazwischen zaehlt nicht mit.

    Eine Spannung, die von 0 ueber 40 auf 100 steigt, hat **ein** Spiel, nicht
    zwei: Zwischenwerte auf dem Weg nach oben sind keine Umkehr. Beide
    Zaehlverfahren beginnen damit.
    """
    x = [float(v) for v in (werte if werte is not None else [])]
    if len(x) < 2:
        return list(x)
    out = [x[0]]
    for a, b, c in zip(x[:-2], x[1:-1], x[2:]):
        if (b - a) * (c - b) < 0:        # Vorzeichenwechsel der Steigung
            out.append(b)
    out.append(x[-1])
    # Aufeinanderfolgende gleiche Werte tragen nichts bei
    knapp = [out[0]]
    for v in out[1:]:
        if v != knapp[-1]:
            knapp.append(v)
    return knapp


def rainflow(werte) -> list:
    """Rainflow-Zaehlung (EN 1993-1-9, A.2): [(Schwingbreite, Mittelwert, Zyklen)].

    Das Vier-Punkt-Verfahren: liegt die mittlere von vier aufeinanderfolgenden
    Umkehrungen ganz innerhalb der aeusseren, ist sie ein **geschlossenes
    Spiel** und wird herausgenommen; der Rest wird weiterverfolgt. Was am Ende
    uebrig bleibt (der „Rest"), sind halbe Spiele - sie zaehlen mit 0,5.

    Das ist das Verfahren, das aus einem Beanspruchungs**verlauf** ein
    Kollektiv macht: ohne es muesste der Aufsteller die Schwingbreiten von
    Hand paaren, und bei einer Zugueberfahrt mit vielen Zeitschritten ist das
    weder machbar noch nachpruefbar.

    Gezaehlt wird der Verlauf so, wie er kommt (Konvention nach ASTM E1049 -
    der Rest zaehlt mit halben Spielen); umgeordnet wird nichts. Am
    Lehrbuchbeispiel der Norm faellt damit genau das bekannte Kollektiv
    heraus. Wer die Ueberfahrt am groessten Wert beginnen und enden laesst,
    bekommt nur ganze Spiele - und dasselbe wie mit :func:`reservoir`.
    """
    p = umkehrpunkte(werte)
    spiele: list = []
    stapel: list = []
    for wert in p:
        stapel.append(wert)
        while len(stapel) >= 4:
            s1, s2, s3, s4 = stapel[-4:]
            if abs(s2 - s3) <= abs(s1 - s2) and abs(s2 - s3) <= abs(s3 - s4):
                spiele.append((abs(s2 - s3), 0.5 * (s2 + s3), 1.0))
                del stapel[-3:-1]        # s2 und s3 sind abgezaehlt
            else:
                break
    for a, b in zip(stapel[:-1], stapel[1:]):
        if a != b:
            spiele.append((abs(a - b), 0.5 * (a + b), 0.5))
    return spiele


def reservoir(werte) -> list:
    """Reservoir-Zaehlung (EN 1993-1-9, A.1): [(Schwingbreite, Zyklen)].

    Bildlich: der Verlauf ist ein Gefaess, das mit Wasser gefuellt wird; man
    zieht am tiefsten Punkt den Stoepsel, und was ausfliesst, ist ein Spiel
    mit der Hoehe des Wasserspiegels. Danach zerfaellt das Gefaess an dieser
    Stelle in **zwei** Reservoire - links und rechts vom Tiefpunkt -, und in
    jedem geht es von vorn los. Genau dieses Zerfallen macht das Verfahren
    aus; wer stattdessen weiter gegen die aeusseren Hochpunkte misst, zaehlt
    zu grosse Schwingbreiten.

    Ein geschlossener Verlauf (Anfang = Ende) wird zuvor am groessten Wert
    aufgeschnitten, damit das Gefaess einen Rand hat.

    **Beginnt und endet der Verlauf am groessten Wert, liefert das Verfahren
    genau dasselbe Kollektiv wie die Rainflow-Zaehlung** - das prueft der Test
    nach, und so soll eine Ueberfahrt auch angesetzt werden. Andernfalls
    duerfen beide auseinandergehen: was bei Rainflow als Rest offen bleibt und
    dort mit einem **halben** Spiel zaehlt, ist hier schon abgeflossen. Wer
    beide Zahlen nebeneinander sieht, sieht damit auch, wie gut der Verlauf
    fuer die Zaehlung zugeschnitten ist.
    """
    p = umkehrpunkte(werte)
    if len(p) < 2:
        return []
    if p[0] == p[-1] and len(p) > 2:
        k = int(max(range(len(p)), key=lambda i: p[i]))
        p = p[k:] + p[1:k + 1]
    spiele: list = []
    stapel = [list(p)]
    while stapel:
        teil = stapel.pop()
        if len(teil) < 3:
            continue                     # eine blosse Flanke ist kein Spiel
        i = min(range(1, len(teil) - 1), key=lambda j: teil[j])
        hoehe = min(max(teil[:i + 1]), max(teil[i:])) - teil[i]
        if hoehe > 0:
            spiele.append((float(hoehe), 1.0))
        # Der Tiefpunkt teilt das Gefaess in zwei eigene Reservoire
        stapel.append(umkehrpunkte(teil[:i + 1]))
        stapel.append(umkehrpunkte(teil[i:]))
    return [(h, n) for h, n in spiele if h > 0]


def kollektiv(spiele, klassen: int = 0) -> list:
    """Ein Kollektiv aus gezaehlten Spielen: [(Schwingbreite, Zyklen)], absteigend.

    Gleiche Schwingbreiten werden zusammengefasst. Mit ``klassen`` > 0 werden
    sie zusaetzlich in so viele gleich breite Stufen gerafft (die Stufe traegt
    ihre **obere** Grenze - das liegt auf der sicheren Seite).
    """
    paare = [(float(x[0]), float(x[-1])) for x in spiele if float(x[0]) > 0]
    if not paare:
        return []
    if klassen > 0:
        gross = max(h for h, _n in paare)
        breite = gross / klassen
        gerafft: dict = {}
        for h, n in paare:
            k = min(klassen, max(1, int(np.ceil(h / breite))))
            gerafft[k] = gerafft.get(k, 0.0) + n
        paare = [(k * breite, n) for k, n in gerafft.items()]
    else:
        summe: dict = {}
        for h, n in paare:
            summe[h] = summe.get(h, 0.0) + n
        paare = list(summe.items())
    return sorted(paare, key=lambda x: -x[0])


def schaedigungstabelle(ranges, category: float, gamma_Mf: float = 1.0,
                        shear: bool = False) -> list:
    """Die Schadensakkumulation Stufe fuer Stufe.

    [(Delta_sigma, n, N_R, D_i, D_kumuliert)] - so, wie eine Miner-Summe im
    Statikdokument nachvollziehbar wird: je Stufe die ertragbare Lastspielzahl
    aus der Woehlerlinie, der Anteil n/N und die laufende Summe. Stufen unter
    dem Schwellenwert (N_R unendlich) stehen mit D_i = 0 drin und sind damit
    nicht verschwiegen.
    """
    zeilen = []
    kum = 0.0
    for ds, n in sorted([(float(a), float(b)) for a, b in ranges], key=lambda x: -x[0]):
        N = sn_life(ds, category, gamma_Mf, shear)
        di = float(n / N) if np.isfinite(N) and N > 0 else 0.0
        kum += di
        zeilen.append((ds, float(n), N, di, kum))
    return zeilen


def lebensdauer(D: float, bezugsjahre: float) -> float:
    """Rechnerische Lebensdauer [Jahre] aus der Schaedigung eines Bezugszeitraums.

    D ist die Miner-Summe fuer ``bezugsjahre`` Jahre; die Schaedigung waechst
    linear, also ist die Lebensdauer ``bezugsjahre / D``. D = 0 heisst: keine
    Stufe liegt ueber dem Schwellenwert - dann gibt es rechnerisch kein Ende.
    """
    if D <= 0:
        return float("inf")
    return float(bezugsjahre) / float(D)


# --------------------------------------------------------------------------
@dataclass
class FatigueMember:
    member: str
    category: float
    category_shear: float
    gamma_Mf: float
    ranges: list = field(default_factory=list)       # (Delta_sigma, n, name, x)
    ranges_shear: list = field(default_factory=list)
    D: float = 0.0
    D_shear: float = 0.0
    dsig_max: float = 0.0
    dtau_max: float = 0.0
    dsig_E2: float = 0.0
    util: float = 0.0
    util_E2: float = 0.0
    governing: str = ""
    x_governing: float = 0.0
    warnings: list = field(default_factory=list)
    #: Kollektiv am massgebenden Ort: [(Delta_sigma, n)], absteigend
    kollektiv: list = field(default_factory=list)
    kollektiv_shear: list = field(default_factory=list)
    #: Rechnerische Lebensdauer [Jahre] aus D und dem Bezugszeitraum
    jahre: float = float("inf")
    #: Bezugszeitraum, auf den die Lastspielzahlen sich beziehen [Jahre]
    bezugsjahre: float = 0.0

    def tabelle(self) -> list:
        """Die Schadensakkumulation Stufe fuer Stufe am massgebenden Ort."""
        return schaedigungstabelle(self.kollektiv, self.category, self.gamma_Mf)

    def tabelle_shear(self) -> list:
        return schaedigungstabelle(self.kollektiv_shear, self.category_shear,
                                   self.gamma_Mf, shear=True)


@dataclass
class FatigueResults:
    members: dict = field(default_factory=dict)
    gamma_Ff: float = 1.0

    def summary(self) -> str:
        if not self.members:
            return "Ermuedung: keine Staebe mit Kerbfall"
        worst = max(self.members.values(), key=lambda m: m.util)
        return (f"Ermuedung: {len(self.members)} Staebe, max. Schaedigung D = {worst.util:.3f} "
                f"({worst.member}, Kerbfall {worst.category/1e6:.0f})")

    def table(self) -> list[list]:
        rows = [["Stab", "Kerbfall", "gamma_Mf", "max Delta-sigma [MPa]", "Delta-sigma_E,2 [MPa]",
                 "D (Miner)", "D Schub", "Ausnutzung", "massgebend"]]
        for m in self.members.values():
            rows.append([m.member, f"{m.category/1e6:.0f}", f"{m.gamma_Mf:.2f}",
                         f"{m.dsig_max/1e6:.1f}", f"{m.dsig_E2/1e6:.1f}", f"{m.D:.3f}",
                         f"{m.D_shear:.3f}", f"{m.util:.3f}", m.governing])
        return rows

    def util_by_element(self, model: Model) -> dict:
        out = {}
        for m in self.members.values():
            for e in model.members[m.member].elements:
                out[e] = max(out.get(e, 0.0), m.util)
        return out


def _stress_points(model: Model, res, member: Member, n: int):
    """Normalspannungen an den 4 Eckpunkten und Schubspannung entlang des Stabes."""
    mf = res.member_forces(member, n)
    e0 = model.elements[member.elements[0]]
    sec = model.sections[e0.sec]
    Wy = sec.Wel_y if sec.Wel_y > 0 else 1e-30
    Wz = sec.Wel_z if sec.Wel_z > 0 else 1e-30
    N, My, Mz = mf["N"], mf["My"], mf["Mz"]
    sig = np.stack([N / sec.A + sy * My / Wy + sz * Mz / Wz
                    for sy in (1, -1) for sz in (1, -1)])          # (4, nstat)
    Avz = sec.Asz if sec.Asz > 0 else sec.A
    Avy = sec.Asy if sec.Asy > 0 else sec.A
    tau = np.maximum(np.abs(mf["Vz"]) / Avz, np.abs(mf["Vy"]) / Avy)
    return mf["x"], sig, tau


def _verlauf(model: Model, all_res: dict, member: Member, fl, n: int, fm):
    """Spannungsverlauf einer Lastfallfolge: (x, sig (p, station, schritt), tau).

    Fuer jeden Zeitschritt der Folge die Spannungen an den vier Eckpunkten und
    die Schubspannung. Fehlende Lastfaelle werden benannt, nicht uebergangen.
    """
    sig_t, tau_t, x = [], [], None
    for fall in fl.folge:
        if fall not in all_res:
            fm.warnings.append(f"Ermuedungslast {fl.name}: Ergebnis '{fall}' fehlt")
            continue
        x, s_, t_ = _stress_points(model, all_res[fall], member, n)
        sig_t.append(s_)
        tau_t.append(t_)
    if len(sig_t) < 2:
        return None, None, None
    return x, np.stack(sig_t, axis=-1), np.stack(tau_t, axis=-1)


def _groesste_stufe(eigen: dict, name: str, x) -> tuple:
    """Die groesste Stufe einer Ermuedungslast: (Delta, n, Name, x).

    ``eigen`` sind die Spiele dieser Last je Ort. Gesucht ist die groesste
    Schwingbreite und - am selben Ort - **ihre gesamte** Spielzahl: eine
    Ueberfahrt 0 -> voll -> 0 zaehlt bei Rainflow als zwei halbe Spiele
    derselben Stufe, und das ist zusammen eines, nicht ein halbes.
    """
    gross, n, ort = 0.0, 0.0, None
    for o, spiele in eigen.items():
        for h, _z in spiele:
            if h > gross:
                gross, ort = h, o
    if ort is not None:
        n = sum(z for h, z in eigen[ort] if h == gross)
    xs = float(x[ort[1]]) if ort is not None and x is not None and ort[1] < len(x) else 0.0
    return (float(gross), float(n), name, xs)


def _zaehlen(verlauf, verfahren: str) -> list:
    """Ein Kollektiv aus einem Verlauf - nach dem gewaehlten Zaehlverfahren."""
    if str(verfahren).lower().startswith("res"):
        return reservoir(verlauf)
    return [(h, n) for h, _mittel, n in rainflow(verlauf)]


def check_fatigue(model: Model, analysis, progress=None, n: int = None) -> FatigueResults:
    """Ermuedungsnachweis aller Staebe mit Kerbfall fuer alle Ermuedungslasten.

    **Die Schaedigung wird am Ort aufsummiert, nicht ueber Orte hinweg.**
    Miner zaehlt, was ein Punkt des Bauteils erlebt; die groesste Schwingbreite
    aus Last A und die aus Last B liegen aber im Allgemeinen an verschiedenen
    Stellen des Stabes. Wer sie addiert, addiert die Schaedigung zweier
    verschiedener Punkte und erhaelt eine Zahl, die nirgends auftritt. Gerechnet
    wird darum D an **jeder** Nachweisstelle und an jedem der vier Eckpunkte
    des Querschnitts; massgebend ist der groesste Wert, und der Ort steht dabei.

    Eine Ermuedungslast beschreibt entweder zwei Zustaende (case_max gegen
    case_min) oder einen **Verlauf** (``folge``) - dann wird das Kollektiv mit
    Rainflow bzw. Reservoir gezaehlt (EN 1993-1-9, Anhang A).
    """
    ds = model.design
    n = n or ds.stations
    out = FatigueResults(gamma_Ff=ds.gamma_Ff)
    bezug = float(getattr(ds, "ermuedung_bezugsjahre", 0.0) or 0.0)
    # Kerbfaelle aus den Schweissnaehten des Modells (ungünstigste je Stab)
    if getattr(model, "schweissnaehte", None):
        from ..schweissnaehte import kerbfaelle_uebernehmen
        kerbfaelle_uebernehmen(model, out.warnings if hasattr(out, "warnings") else None)
    all_res = analysis.all_results() if hasattr(analysis, "all_results") else analysis
    for mname, member in model.members.items():
        if not member.design or member.detail_category is None:
            continue
        gMf = GAMMA_MF.get((member.assessment, member.consequence), 1.15)
        cat_s = member.detail_category_shear or 100e6
        fm = FatigueMember(mname, member.detail_category, cat_s, gMf)
        fm.bezugsjahre = bezug
        #: Kollektive je Ort: (Punkt, Station) -> [(Schwingbreite, Zyklen)]
        sammlung: dict = {}
        sammlung_t: dict = {}
        xs = None
        for fl in model.fatigue_loads.values():
            faktor = fl.factor * ds.gamma_Ff
            if getattr(fl, "folge", None):
                x, sig, tau = _verlauf(model, all_res, member, fl, n, fm)
                if sig is None:
                    continue
                xs = x
                wdh = float(getattr(fl, "wiederholungen", 1.0) or 1.0)
                verfahren = getattr(fl, "zaehlung", "rainflow")
                # Erst **diese** Last fuer sich zaehlen, dann anhaengen. Die
                # Uebersichtszeile darf nicht ueber die Sammlung messen: dort
                # stehen schon die Stufen der Lasten davor.
                eigen: dict = {}
                for p_ in range(sig.shape[0]):
                    for j in range(sig.shape[1]):
                        for h, z in _zaehlen(sig[p_, j, :] * faktor, verfahren):
                            eigen.setdefault((p_, j), []).append((h, z * wdh))
                eigen_t: dict = {}
                for j in range(tau.shape[0]):
                    for h, z in _zaehlen(tau[j, :] * faktor, verfahren):
                        eigen_t.setdefault(j, []).append((h, z * wdh))
                for ort_, v in eigen.items():
                    sammlung.setdefault(ort_, []).extend(v)
                for j, v in eigen_t.items():
                    sammlung_t.setdefault(j, []).extend(v)
                fm.ranges.append(_groesste_stufe(eigen, fl.name, x))
                fm.ranges_shear.append(
                    _groesste_stufe({(0, j): v for j, v in eigen_t.items()}, fl.name, x))
                continue
            if fl.case_max not in all_res:
                fm.warnings.append(f"Ermuedungslast {fl.name}: Ergebnis '{fl.case_max}' fehlt")
                continue
            x, s_max, t_max = _stress_points(model, all_res[fl.case_max], member, n)
            xs = x
            if fl.case_min and fl.case_min in all_res:
                _, s_min, t_min = _stress_points(model, all_res[fl.case_min], member, n)
            else:
                s_min = np.zeros_like(s_max)
                t_min = np.zeros_like(t_max)
            dsig = np.abs(s_max - s_min) * faktor          # (4, nstat)
            dtau = np.abs(t_max - t_min) * faktor          # (nstat,)
            for p_ in range(dsig.shape[0]):
                for j in range(dsig.shape[1]):
                    sammlung.setdefault((p_, j), []).append((float(dsig[p_, j]), fl.cycles))
            for j in range(dtau.shape[0]):
                sammlung_t.setdefault(j, []).append((float(dtau[j]), fl.cycles))
            j = int(np.argmax(dsig.max(axis=0)))
            fm.ranges.append((float(dsig[:, j].max()), fl.cycles, fl.name, float(x[j])))
            k = int(np.argmax(dtau))
            fm.ranges_shear.append((float(dtau[k]), fl.cycles, fl.name, float(x[k])))
        if not sammlung:
            continue
        # Massgebend ist der Ort mit der groessten Schaedigung - nicht die
        # groesste Schwingbreite irgendwo und die naechste woanders.
        schaden = {ort: damage(v, fm.category, gMf) for ort, v in sammlung.items()}
        ort = max(schaden, key=lambda o: schaden[o])
        fm.D = float(schaden[ort])
        fm.kollektiv = kollektiv(sammlung[ort])
        if sammlung_t:
            schaden_t = {j: damage(v, cat_s, gMf, shear=True) for j, v in sammlung_t.items()}
            jt = max(schaden_t, key=lambda o: schaden_t[o])
            fm.D_shear = float(schaden_t[jt])
            fm.kollektiv_shear = kollektiv(sammlung_t[jt])
        fm.dsig_max = max((h for v in sammlung.values() for h, _z in v), default=0.0)
        fm.dtau_max = max((h for v in sammlung_t.values() for h, _z in v), default=0.0)
        fm.dsig_E2 = equivalent_range(fm.kollektiv)
        fm.util_E2 = fm.dsig_E2 / (fm.category / gMf)
        # Normal- und Schubspannung zusammen (EN 1993-1-9, 8(3)): D_sig + D_tau <= 1
        fm.util = fm.D + fm.D_shear
        fm.jahre = lebensdauer(fm.util, bezug) if bezug > 0 else float("inf")
        x_ort = float(xs[ort[1]]) if xs is not None and ort[1] < len(xs) else 0.0
        fm.x_governing = x_ort
        gross = fm.kollektiv[0][0] if fm.kollektiv else 0.0
        fm.governing = (f"Eckpunkt {ort[0] + 1} bei x = {x_ort:.2f} m "
                        f"(größte Stufe Delta-sigma = {gross/1e6:.1f} MPa, "
                        f"{len(fm.kollektiv)} Stufen)")
        out.members[mname] = fm
        if progress:
            progress(f"Ermuedung {mname}: D = {fm.util:.3f}")
    return out
