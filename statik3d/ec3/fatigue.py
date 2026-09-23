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
from .. import elemente as EL

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
    #: Warum dieser Nachweis **nicht gefuehrt** wurde - leer, wenn er lief.
    #: Ohne dieses Feld fiel ein Stab, zu dem keine Ermuedungslast beitrug,
    #: samt seinen Warnungen ganz aus ``out.members`` heraus
    #: (``if not sammlung: continue``): der Bericht zeigte ihn nicht, und
    #: niemand erfuhr, dass sein Nachweis fehlte (22.09.2026).
    fehler: str = ""
    #: Kollektiv am massgebenden Ort: [(Delta_sigma, n)], absteigend
    kollektiv: list = field(default_factory=list)
    kollektiv_shear: list = field(default_factory=list)
    #: Rechnerische Lebensdauer [Jahre] aus D und dem Bezugszeitraum
    jahre: float = float("inf")
    #: Bezugszeitraum, auf den die Lastspielzahlen sich beziehen [Jahre]
    bezugsjahre: float = 0.0
    #: Ermuedungslasten, die wegen eines fehlenden Ergebnisses nicht (oder
    #: nur mit einem Teil ihres Verlaufs) in D stehen. Ohne dieses Feld war
    #: ein Nachweis, dem von zwei Lasten eine fehlte, im Bericht "erfuellt"
    #: und im Gesamturteil "Alle Nachweise erfuellt." - der Hinweis stand nur
    #: darunter (Befund FE5, gemessen: D = 0,38334 allein aus der guten Last).
    fehlende_lasten: list = field(default_factory=list)

    def status(self) -> str:
        return _status(self)

    def tabelle(self) -> list:
        """Die Schadensakkumulation Stufe fuer Stufe am massgebenden Ort."""
        return schaedigungstabelle(self.kollektiv, self.category, self.gamma_Mf)

    def tabelle_shear(self) -> list:
        return schaedigungstabelle(self.kollektiv_shear, self.category_shear,
                                   self.gamma_Mf, shear=True)


@dataclass
class FatigueVolumen:
    """Ermuedungsnachweis eines Volumenkoerpers.

    Je Auswerteort die Schaedigung aus der vorzeichenbehafteten Hauptspannung
    mit dem groessten Betrag; massgebend der Ort mit dem groessten D. Der Ort
    ist nach der Regel "knoten" ein Knoten (geglaettete Knotenspannung), nach
    der Regel "element" ein Element (Elementwert) - siehe VOLUMEN_REGELN.
    """
    name: str
    category: float                                  # am massgebenden Ort
    gamma_Mf: float
    konzept: str = ""
    category_grund: float = 0.0                      # Kerbfall des Koerpers
    category_naht: float = 0.0                       # an verschweissten Beruehrungsstellen
    n_naht: int = 0                                  # Elemente an Beruehrungsstellen
    naht: bool = False                               # der massgebende Ort liegt dort
    #: Gerechnete Regel (VOLUMEN_REGELN). Ergebnisse aus der Zeit davor
    #: (Dateien vor dem 23.09.2026) kennen das Feld nicht - sie sind nach der
    #: Elementregel gerechnet, darum ist das die Vorgabe des Feldes.
    regel: str = "element"
    #: Regel "knoten": der massgebende Knoten (sonst -1); ``element`` ist dann
    #: ein Element des Koerpers an diesem Knoten
    knoten: int = -1
    #: Regel "knoten": die Knoten der Auswerteorte (je Knoten, Koerpergruppe
    #: und Werkstoff eine Zeile) und ihre groesste Schwingbreite [Pa]
    orte: object = None
    dsig_je_ort: object = None
    D: float = 0.0
    dsig_max: float = 0.0
    dsig_E2: float = 0.0
    util: float = 0.0
    element: int = -1
    n_elemente: int = 0
    #: Warum dieser Nachweis **nicht gefuehrt** wurde - leer, wenn er lief.
    #: Siehe FatigueMember.fehler; der Volumenzweig verlor seinen Koerper an
    #: derselben Stelle (``if not beitrag: continue``).
    fehler: str = ""
    #: (Delta_sigma, n, Name, Element) - nach der Regel "knoten" mit dem
    #: Knoten als fuenftem Eintrag
    ranges: list = field(default_factory=list)
    #: Kollektiv am massgebenden Ort: [(Delta_sigma, n)], absteigend
    kollektiv: list = field(default_factory=list)
    jahre: float = float("inf")
    bezugsjahre: float = 0.0
    warnings: list = field(default_factory=list)
    #: Elemente des Koerpers und ihre Schaedigung (float32) - fuer die
    #: Faerbung; nach der Regel "knoten" das groesste D an den Ecken des Elements
    elemente: list = field(default_factory=list)
    D_je_element: object = None
    #: Siehe FatigueMember.fehlende_lasten
    fehlende_lasten: list = field(default_factory=list)

    def status(self) -> str:
        return _status(self)

    def tabelle(self) -> list:
        return schaedigungstabelle(self.kollektiv, self.category, self.gamma_Mf)


def _status(n) -> str:
    """Status eines Ermuedungsnachweises (Stab oder Volumen).

    "nicht geführt": keine Last hat beigetragen (``fehler``) - D = 0 ist dann
    keine Aussage. "NICHT erfüllt": D > 1 aus den gerechneten Lasten - so
    stand es auch vorher da. "unvollständig": D <= 1, aber mindestens eine
    Last fehlt in D (``fehlende_lasten``); ihr Beitrag ist nicht bekannt, das
    Ergebnis darf darum nicht "erfüllt" heissen. Ergebnisse aus Dateien vor
    dem 22.09.2026 kennen die Felder nicht - daher getattr.
    """
    if getattr(n, "fehler", ""):
        return "nicht geführt"
    if n.util > 1.0:
        return "NICHT erfüllt"
    if getattr(n, "fehlende_lasten", None):
        return "unvollständig"
    return "erfüllt"


def _nicht_gerechnet(nachweis, fl, text: str, wirksam: bool = True) -> None:
    """Das Ergebnis einer Ermuedungslast fehlt: Warnung **und** Name der Last
    am Nachweis. Die Warnung allein reichte nicht - der Bericht setzte den
    Status aus D und schrieb "Nachweis erfüllt", obwohl eine Last fehlte.

    ``wirksam=False`` (0 Lastspiele bzw. Wiederholungen, z. B. die Sammlungen
    aus dem RFEM-Import): die Warnung bleibt wie bisher, die Last fehlt aber
    nicht in D - sie haette nichts beigetragen. Ohne diese Unterscheidung
    hiess ein Nachweis mit gewollt unwirksamer Sammlung "unvollständig"
    (gemessen am Pruefkoerper, test_volumen_ohne_beitrag_und_unvollstaendig).
    """
    nachweis.warnings.append(text)
    if wirksam:
        _fehlt_in_d(nachweis, fl)


def _fehlt_in_d(nachweis, fl) -> None:
    """Die Last *fl* steht nicht (vollstaendig) in D dieses Nachweises."""
    if fl.name not in nachweis.fehlende_lasten:
        nachweis.fehlende_lasten.append(fl.name)


def _aufzaehlen(namen: list, n: int = 5) -> str:
    """Die ersten *n* Namen, dahinter die Zahl der uebrigen."""
    kopf = ", ".join(namen[:n])
    return kopf + (f" und {len(namen) - n} weitere" if len(namen) > n else "")


@dataclass
class FatigueResults:
    members: dict = field(default_factory=dict)
    gamma_Ff: float = 1.0
    #: Ermuedungsnachweise der Volumenkoerper mit Kerbfall
    volumen: dict = field(default_factory=dict)
    #: Staebe und Volumen mit Kerbfall, zu denen keine Ermuedungslast
    #: beitraegt, obwohl kein Ergebnis fehlt (alle Lasten mit 0 Lastspielen
    #: bzw. Wiederholungen oder Verlauf mit weniger als zwei Zustaenden) -
    #: als "Stab <Name>" / "Volumen <Name>". Sie bekommen gewollt keinen
    #: Eintrag ("0 heisst unwirksam"); bis zum 22.09.2026 sagte die
    #: Zusammenfassung dann aber "keine Staebe oder Volumen mit Kerbfall",
    #: obwohl es sie gab (Befund SV5, Faelle D/E der Probe).
    ohne_wirksame_last: list = field(default_factory=list)

    def summary(self) -> str:
        # Stab- und Volumeneintraege mit Anzeigenamen; ein nicht gefuehrter
        # Eintrag (fehler) hat D = 0 und darf weder "max. Schaedigung" sein
        # noch die Zeile allein bestreiten - bis zum 22.09.2026 stand dann
        # "max. Schaedigung D = 0.000 (Volumen V1, Kerbfall 71)" da.
        alle = ([(f"Stab {m.member}", m) for m in self.members.values()]
                + [(f"Volumen {v.name}", v) for v in self.volumen.values()])
        ohne = list(getattr(self, "ohne_wirksame_last", None) or [])
        if not alle:
            if ohne:
                return (f"Ermüdung: kein Nachweis geführt - {len(ohne)} mit Kerbfall ohne "
                        f"wirksame Ermüdungslast ({_aufzaehlen(ohne)}): Lastspiele bzw. "
                        "Wiederholungen 0 oder Verlauf mit weniger als zwei Zuständen")
            return "Ermüdung: keine Stäbe oder Volumen mit Kerbfall"
        teile = ([f"{len(self.members)} Stäbe"] if self.members else []) + (
            [f"{len(self.volumen)} Volumen"] if self.volumen else [])
        text = f"Ermüdung: {', '.join(teile)}"
        gefuehrt = [(n, x) for n, x in alle if not getattr(x, "fehler", "")]
        if gefuehrt:
            wname, worst = max(gefuehrt, key=lambda nx: nx[1].util)
            text += (f", max. Schädigung D = {worst.util:.3f} "
                     f"({wname}, Kerbfall {worst.category/1e6:.0f})")
        offen = [n for n, x in alle if getattr(x, "fehler", "")]
        if offen:
            text += f"; nicht geführt: {_aufzaehlen(offen)}"
        teil = [n for n, x in gefuehrt if getattr(x, "fehlende_lasten", None)]
        if teil:
            text += f"; unvollständig (Ergebnis einer Last fehlt): {_aufzaehlen(teil)}"
        if ohne:
            text += f"; ohne wirksame Ermüdungslast: {_aufzaehlen(ohne)}"
        return text

    def table(self) -> list[list]:
        rows = [["Stab", "Kerbfall", "gamma_Mf", "max Delta-sigma [MPa]", "Delta-sigma_E,2 [MPa]",
                 "D (Miner)", "D Schub", "Ausnutzung", "massgebend"]]

        # Ein nicht gefuehrter Eintrag zeigt statt D 0.000 und "Element -1"
        # (so bis zum 22.09.2026) den Grund; einem unvollstaendigen wird die
        # fehlende Last an den massgebenden Ort gehaengt.
        def ort(x, text: str) -> str:
            fehlend = getattr(x, "fehlende_lasten", None)
            if fehlend:
                text += f" - unvollständig, nicht gerechnet: {_aufzaehlen(fehlend)}"
            return text

        for m in self.members.values():
            if getattr(m, "fehler", ""):
                rows.append([m.member, f"{m.category/1e6:.0f}", f"{m.gamma_Mf:.2f}",
                             "–", "–", "–", "–", "–", f"nicht geführt: {m.fehler}"])
                continue
            rows.append([m.member, f"{m.category/1e6:.0f}", f"{m.gamma_Mf:.2f}",
                         f"{m.dsig_max/1e6:.1f}", f"{m.dsig_E2/1e6:.1f}", f"{m.D:.3f}",
                         f"{m.D_shear:.3f}", f"{m.util:.3f}", ort(m, m.governing)])
        for v in self.volumen.values():
            kf = f"{v.category_grund/1e6:.0f}" + (f" / Naht {v.category_naht/1e6:.0f}"
                                                  if v.n_naht and v.category_naht else "")
            if getattr(v, "fehler", ""):
                rows.append([f"Volumen {v.name}", kf, f"{v.gamma_Mf:.2f}",
                             "–", "–", "–", "–", "–", f"nicht geführt: {v.fehler}"])
                continue
            rows.append([f"Volumen {v.name}", kf, f"{v.gamma_Mf:.2f}",
                         f"{v.dsig_max/1e6:.1f}", f"{v.dsig_E2/1e6:.1f}", f"{v.D:.3f}",
                         "0.000", f"{v.util:.3f}",
                         ort(v, (f"Knoten {v.knoten + 1}" if getattr(v, "regel", "element") == "knoten"
                                 and getattr(v, "knoten", -1) >= 0 else f"Element {v.element}")
                             + (" (Naht)" if v.naht else ""))])
        return rows

    def util_by_element(self, model: Model) -> dict:
        out = {}
        for m in self.members.values():
            for e in model.members[m.member].elements:
                out[e] = max(out.get(e, 0.0), m.util)
        for v in self.volumen.values():
            if v.D_je_element is not None:
                for e, u in zip(v.elemente, np.asarray(v.D_je_element, float).tolist()):
                    out[int(e)] = max(out.get(int(e), 0.0), float(u))
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
            # ob die Last in D fehlt, entscheidet der Aufrufer (Wiederholungen)
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
    """Ein Kollektiv aus einem Verlauf - nach dem gewaehlten Zaehlverfahren.

    ``"spanne"``: genau eine Stufe, Schwingbreite = Maximum minus Minimum ueber
    die Zustaende, ein Spiel je Durchlauf. Das ist die Schwingbreite, die RFEM
    aus einer Ergebniskombination fuer die Ermuedung bildet; sie haengt nicht
    von der Reihenfolge der Zustaende ab, und bei zwei Zustaenden ist sie mit
    Rainflow identisch. Rainflow zaehlt bei drei Zustaenden 1 -> 25 -> 5 zwei
    halbe Spiele verschiedener Groesse (20 und 15 als je 0,5) - fuer eine
    Ergebniskombination, deren Zustaende keine Zeitfolge sind, waere das ein
    Kollektiv ohne Grundlage.
    ``"rainflow"`` / ``"reservoir"``: EN 1993-1-9, Anhang A, fuer echte
    Verlaeufe (Ueberfahrt, Oeffnungsvorgang).
    """
    v = str(verfahren).lower()
    if v.startswith("span"):
        w = np.asarray(verlauf, float).ravel()
        if w.size < 2:
            return []
        return [(float(w.max() - w.min()), 1.0)]
    if v.startswith("res"):
        return reservoir(verlauf)
    return [(h, n) for h, _mittel, n in rainflow(verlauf)]


def hauptspannungen(S: np.ndarray) -> np.ndarray:
    """Hauptspannungen (n, 3), absteigend, fuer n Tensoren (sx, sy, sz, txy, tyz, tzx).

    Geschlossen (Cardano, trigonometrisch) statt eigvalsh je Element: 200 000
    Tensoren in Bruchteilen einer Sekunde; eigvalsh in einer Python-Schleife
    braeuchte fuer die 2 Mio. Elemente des Drehlagers Minuten je Zustand.
    """
    S = np.asarray(S, float).reshape(-1, 6)
    sx, sy, sz, txy, tyz, tzx = S.T
    p = (sx + sy + sz) / 3.0
    dx, dy, dz = sx - p, sy - p, sz - p
    q = np.sqrt((dx * dx + dy * dy + dz * dz + 2.0 * (txy * txy + tyz * tyz + tzx * tzx)) / 6.0)
    q_ = np.where(q > 0.0, q, 1.0)                 # hydrostatisch: alle drei = p
    bx, by, bz, bxy, byz, bzx = dx / q_, dy / q_, dz / q_, txy / q_, tyz / q_, tzx / q_
    det = (bx * (by * bz - byz * byz) - bxy * (bxy * bz - byz * bzx)
           + bzx * (bxy * byz - by * bzx))
    phi = np.arccos(np.clip(det / 2.0, -1.0, 1.0)) / 3.0
    e1 = p + 2.0 * q * np.cos(phi)
    e3 = p + 2.0 * q * np.cos(phi + 2.0 * np.pi / 3.0)
    e2 = 3.0 * p - e1 - e3
    return np.sort(np.stack([e1, e2, e3], axis=1), axis=1)[:, ::-1]


def signalspannung(S: np.ndarray) -> np.ndarray:
    """Die vorzeichenbehaftete Hauptspannung mit dem groessten Betrag je Tensor.

    sigma_1, wenn |sigma_1| >= |sigma_3|, sonst sigma_3: ein Zugkoerper gibt
    +sigma, ein Druckkoerper -sigma, und die Schwingbreite zwischen zwei
    Zustaenden ist die Differenz - nicht die Differenz zweier Betraege.
    """
    h = hauptspannungen(S)
    return np.where(np.abs(h[:, 0]) >= np.abs(h[:, 2]), h[:, 0], h[:, 2])


def _n_vektor(delta, category, gamma_Mf: float = 1.0) -> np.ndarray:
    """Ertragbare Lastspielzahl N_R je Schwingbreite - sn_life vektorisiert
    (Normalspannung: m = 3 bis N_D, m = 5 bis N_L, darunter unendlich).
    ``category`` ist ein Wert oder ein Feld je Element (Naht am Rand)."""
    d = np.asarray(delta, float)
    dc = np.broadcast_to(np.asarray(category, float) / gamma_Mf, d.shape)
    dD = (2.0 / 5.0) ** (1.0 / 3.0) * dc
    dL = (5.0 / 100.0) ** 0.2 * dD
    N = np.full(d.shape, np.inf)
    hoch = d >= dD
    N[hoch] = 2e6 * (dc[hoch] / d[hoch]) ** 3
    mitte = (d >= dL) & ~hoch & (d > 0)
    N[mitte] = 5e6 * (dD[mitte] / d[mitte]) ** 5
    return N


def kontaktpaare(model: Model) -> set:
    """Koerperpaare mit Kontaktbedingung - siehe fugen.kontaktpaare."""
    from ..fugen import kontaktpaare as _kp
    return _kp(model)


def nahtknoten(model: Model) -> dict:
    """{Koerper: Knoten an verschweissten Beruehrungsstellen}.

    Verschweisst ist, was ein anderer Koerper teilt: der Vernetzer teilt
    Knoten nur ueber eine gemeinsame Flaeche (RFEM: eine Flaeche zwischen zwei
    Volumen = durchverbunden), eine ausgefuehrte Kontaktfuge verdoppelt sie.
    Ausgenommen sind Paare mit eingegebener Kontaktbedingung. Ein Durchlauf
    ueber alle Elementknoten - am Drehlager 8 Mio. Eintraege, Sekunden.
    """
    koerper = [k for k in (getattr(model, "koerper", {}) or {}).values() if k.elemente]
    if len(koerper) < 2:
        return {}
    n_el = len(model.elements)
    wem: dict = {}                     # Knoten -> Koerper (der erste)
    mehrere: dict = {}                 # Knoten -> {Koerper}, wo es mehr als einer ist
    for k in koerper:
        for i in k.elemente:
            if i >= n_el:
                continue
            for nd in model.elements[i].nodes:
                nd = int(nd)
                a = wem.get(nd)
                if a is None:
                    wem[nd] = k.name
                elif a != k.name:
                    mehrere.setdefault(nd, {a}).add(k.name)
    kontakt = kontaktpaare(model)
    out: dict = {}
    for nd, namen in mehrere.items():
        namen = sorted(namen)
        for x in range(len(namen)):
            for y in range(x + 1, len(namen)):
                if frozenset((namen[x], namen[y])) in kontakt:
                    continue
                out.setdefault(namen[x], set()).add(nd)
                out.setdefault(namen[y], set()).add(nd)
    return out


def _wiederholungen(fl, ds) -> float:
    """Wiederholungen eines Verlaufs: der eigene Wert - fehlt er (None), die
    globale Lastspielzahl der Nachweiseinstellungen. 0 heisst unwirksam."""
    w = getattr(fl, "wiederholungen", 1.0)
    if w is None:
        return float(getattr(ds, "ermuedung_lastspiele", 2e6) or 0.0)
    return float(w or 0.0)


def _spiele(fl, ds) -> float:
    """Lastspiele zweier Zustaende: eigener Wert oder die globale Lastspielzahl."""
    c = getattr(fl, "cycles", 2e6)
    if c is None:
        return float(getattr(ds, "ermuedung_lastspiele", 2e6) or 0.0)
    return float(c or 0.0)


#: Die Spannung der Volumen-Ermuedung (DesignSettings.ermuedung_volumen).
#:
#: "knoten" (Vorgabe seit 23.09.2026): je Knoten die geglaettete
#: Knotenspannung des Loesers (res.solid_knoten: das Mittel der Elementwerte
#: gleichen Koerpers und Werkstoffs, an freien Oberflaechen auf sigma n = 0
#: gezogen, Model.randspannung) - dieselbe Spannung, die der statische
#: Volumennachweis liest (ec3/volumen.py, res.solid_rand). Sie ist linear in
#: u; Kombinationen tragen sie ueberlagert (Results.combine).
#: "element": der Elementwert (res.solid_res, das Element an seinem
#: Auswertepunkt mit der groessten Vergleichsspannung) - die Regel bis zum
#: 23.09.2026, waehlbar fuer den Vergleich mit aelteren Rechnungen.
#:
#: Warum (gemessen 23.09.2026, tests/test_ermuedung_verlauf.py,
#: test_volumen_randspannung_kragarm): am Kragarm-Pruefkoerper (Schwingbreite
#: 0 -> F, Koerper x >= L/2, Soll 355 N/mm2 nach Saint-Venant) lag die
#: groesste Schwingbreite nach der Elementregel bei 314,35 N/mm2 (hex8
#: 8x2x4) bzw. 333,31 (16x4x8), also 40,65 bzw. 21,69 N/mm2 auf der
#: unsicheren Seite.
VOLUMEN_REGELN = ("knoten", "element")


def _knotenorte(model: Model, idx: list):
    """Die Auswerteorte der Regel "knoten" fuer die Elemente ``idx`` eines
    Koerpers: je Eckknoten, Koerpergruppe (Element.group) und Werkstoff eine
    Zeile - so, wie solver.randspannung_knoten die Knotentabelle bildet.

    Rueckgabe {"knoten": (m,), "gruppe": (m,), "gruppen": [(Gruppe, Werkstoff)],
    "zeile_ort": (z,), "zeile_element": (z,), "element_je_ort": (m,)} - je
    Zeile z (Element, Ecke) der Ort und die Position des Elements in ``idx``;
    ``element_je_ort`` das erste Element an jedem Ort. None, wenn ein Element
    keine Eckknoten-Zuordnung hat (solid.ECKEN_NATUERLICH).
    """
    from ..elements import solid as sl
    kn_l, g_l, el_l = [], [], []
    gruppen: dict = {}
    for r, i in enumerate(idx):
        e = model.elements[i]
        ecken = sl.ECKEN_NATUERLICH.get(e.typ)
        if not ecken:
            return None
        nk = len(ecken)
        g = gruppen.setdefault((str(getattr(e, "group", "")), str(e.mat)), len(gruppen))
        kn_l.append(np.asarray(e.nodes[:nk], np.int64))
        g_l.append(np.full(nk, g, np.int64))
        el_l.append(np.full(nk, r, np.int64))
    if not kn_l:
        return None
    ng = max(1, len(gruppen))
    kn = np.concatenate(kn_l)
    el = np.concatenate(el_l)
    orte, erst, inv = np.unique(kn * ng + np.concatenate(g_l), return_index=True,
                                return_inverse=True)
    return {"knoten": orte // ng, "gruppe": orte % ng,
            "gruppen": [x for x, _j in sorted(gruppen.items(), key=lambda kv: kv[1])],
            "zeile_ort": inv.ravel(), "zeile_element": el, "element_je_ort": el[erst]}


def _knotenspannung(res, orte: dict):
    """Die geglaettete Spannung an den Orten ``orte`` aus res.solid_knoten:
    (S (m, 6), fehlt (m,) bool) - an einem Ort, den die Knotentabelle nicht
    fuehrt, Nullen und ``fehlt``. Fuehrt das Ergebnis keine Knotentabelle
    (Programmfassung vor dem 23.09.2026, von Results.combine verworfen),
    fehlen alle Orte.

    Warum je Ort und nicht "None, sobald ein Ort fehlt" (Gegenpruefung
    23.09.2026): in einer Situation mit abgeschalteten Elementen fuehrt die
    Tabelle die Knoten nicht, an denen nur abgeschaltete Elemente liegen
    (solver.randspannung_knoten mittelt ueber die wirkenden). Am Kragarm 8x2x4
    mit abgeschaltetem Eckelement fiel darum der ganze Koerper auf die
    Elementregel zurueck - bei jedem Neurechnen wieder -, waehrend der
    statische Nachweis am selben Ergebnis die geglaettete Spannung las. Was
    ein fehlender Ort bedeutet, entscheidet _volumen_nachweisen."""
    m = len(orte["knoten"])
    S = np.zeros((m, 6))
    fehlt = np.ones(m, bool)
    sk = getattr(res, "solid_knoten", None) or {}
    if "spannung" not in sk or "knoten" not in sk or "gruppe" not in sk or not len(sk["knoten"]):
        return S, fehlt
    gruppen = [tuple(g) for g in (sk.get("gruppen") or [])]
    ng = max(1, len(gruppen))
    wo = {g: j for j, g in enumerate(gruppen)}
    abb = np.array([wo.get(tuple(g), -1) for g in orte["gruppen"]], np.int64)
    g_ort = abb[orte["gruppe"]]
    schl = np.asarray(sk["knoten"], np.int64) * ng + np.asarray(sk["gruppe"], np.int64)
    ziel = orte["knoten"] * ng + g_ort
    ordnung = None
    if len(schl) > 1 and np.any(np.diff(schl) <= 0):
        ordnung = np.argsort(schl, kind="stable")
        schl = schl[ordnung]
    pos = np.minimum(np.searchsorted(schl, ziel), len(schl) - 1)
    # Eine Gruppe, die das Ergebnis nicht kennt (alle ihre Elemente
    # abgeschaltet), darf keinen Schluessel treffen - auch nicht zufaellig
    # einen fremden (ziel waere dort knoten * ng - 1)
    ok = (g_ort >= 0) & (schl[pos] == ziel)
    if ordnung is not None:
        pos = ordnung[pos]
    S[ok] = np.asarray(sk["spannung"], float)[pos[ok]]
    fehlt[ok] = False
    return S, fehlt


def _ohne_wirkendes_element(res, orte: dict, idx: list) -> np.ndarray:
    """Je Ort (bool, m): im Ergebnis wirkt keines der Koerperelemente an ihm -
    alle stehen in res.info["inaktiv"] (solver.postprocess: die in der
    Situation abgeschalteten Elemente)."""
    inaktiv = (getattr(res, "info", None) or {}).get("inaktiv") or ()
    m = len(orte["knoten"])
    if not len(inaktiv):
        return np.zeros(m, bool)
    el_zeile = np.asarray(idx, np.int64)[orte["zeile_element"]]
    wirkt = ~np.isin(el_zeile, np.asarray(list(inaktiv), np.int64))
    hat = np.zeros(m, bool)
    np.logical_or.at(hat, orte["zeile_ort"], wirkt)
    return ~hat


def _rueckfall_hinweis(res, name: str, orte: dict, offen) -> str:
    """Der Hinweis, warum ein Koerper nach der Elementregel gerechnet ist -
    mit der Ursache, die am Ergebnis vorliegt, und einer Abhilfe nur dort, wo
    sie hilft (Gegenpruefung 23.09.2026: der fruehere Text nannte fuer jeden
    Fall "Ergebnisdatei vor dem 22.09.2026 oder Kombination verschiedener
    Situationen" und riet neu zu rechnen - main fuehrt die Knotentabelle erst
    seit dem Merge 21ce779 am 23.09.2026, und eine Kombination verschiedener
    Situationen bricht in solve_all ab, solver._kombination_pruefen)."""
    sk = getattr(res, "solid_knoten", None) or {}
    folge = " - der Körper ist nach der Regel „element“ mit dem Elementwert gerechnet."
    if sk.get("verworfen"):
        return (f"Knotenwerte fehlen: die Überlagerung '{name}' hat sie verworfen, weil ihre "
                "Lastfälle verschiedene Knotentabellen führen" + folge)
    if "spannung" not in sk:
        return (f"Knotenwerte fehlen: das Ergebnis '{name}' führt keine (Ergebnisse aus "
                "Programmfassungen vor dem 23.09.2026 haben keine; neu gerechnet gilt dann die "
                "geglättete Knotenspannung wie im statischen Nachweis)" + folge)
    kn = np.asarray(orte["knoten"])[np.asarray(offen, bool)]
    return (f"Knotenwerte fehlen im Ergebnis '{name}' an {len(kn)} Knoten des Körpers, an "
            f"{'dem' if len(kn) == 1 else 'denen'} ein Element des Körpers wirkt (etwa Knoten "
            f"{int(kn[0]) + 1})" + folge)


def _benutzte_zustaende(model: Model, all_res: dict, ds) -> list:
    """Die Ergebnisse, deren Spannung der Volumennachweis wirklich liest - in
    der Reihenfolge der Lasten, jedes einmal (dieselben Bedingungen wie die
    Schleife in _volumen_nachweisen)."""
    namen: list = []
    for fl in model.fatigue_loads.values():
        if getattr(fl, "folge", None):
            teil = [f for f in fl.folge if f in all_res]
            if len(teil) >= 2 and _wiederholungen(fl, ds) > 0:
                namen.extend(teil)
            continue
        if (fl.case_max in all_res and _spiele(fl, ds) > 0
                and not (fl.case_min and fl.case_min not in all_res)):
            namen.extend([fl.case_max] + ([fl.case_min] if fl.case_min else []))
    return list(dict.fromkeys(namen))


def _volumen_nachweisen(model: Model, all_res: dict, ds, out: FatigueResults,
                        bezug: float, progress=None) -> None:
    """Ermuedungsnachweis der Volumenkoerper mit Kerbfall.

    Spannungsgroesse je Ort und Zustand ist die vorzeichenbehaftete
    Hauptspannung mit dem groessten Betrag (signalspannung). Der Ort ist nach
    der Regel "knoten" (Vorgabe, VOLUMEN_REGELN) ein Knoten mit der
    geglaetteten Knotenspannung des Loesers, nach der Regel "element" ein
    Element mit seinem Elementwert (res.solid_res). Aus dem Verlauf entsteht
    je Ort das Kollektiv wie beim Stab (spanne / rainflow / reservoir), die
    Schaedigung nach Palmgren-Miner mit der Woehlerlinie fuer
    Normalspannungen; massgebend je Koerper der Ort mit dem groessten D.
    Gerechnet wird je Koerper und Last vektorisiert ueber die Orte; Rainflow
    und Reservoir zaehlen je Ort einzeln und sind bei grossen Koerpern
    langsam.

    Ein Ort, an dem in einem Zustand kein Element des Koerpers wirkt (alle in
    der Situation abgeschaltet), traegt dort die Spannung 0 - wie das
    abgeschaltete Element nach der Elementregel. Fehlen einem benutzten
    Ergebnis Knotenwerte sonst (Programmfassung vor dem 23.09.2026, verworfene
    Ueberlagerung, ein Ort an einem wirkenden Element), rechnet der Koerper
    nach der Elementregel und sagt es mit der Ursache (_rueckfall_hinweis) - so
    bleiben aeltere Ergebnisdateien lesbar, ohne dass eine andere Regel still
    gilt.
    """
    koerper = [k for k in (getattr(model, "koerper", {}) or {}).values()
               if float(getattr(k, "kerbfall", 0.0) or 0.0) > 0 and k.elemente]
    if not koerper:
        return
    regel = str(getattr(ds, "ermuedung_volumen", "knoten") or "knoten")
    n_el = len(model.elements)
    benutzt = _benutzte_zustaende(model, all_res, ds)
    # Knoten an verschweissten Beruehrungsstellen - nur gebraucht, wenn ein
    # Koerper dort einen eigenen Kerbfall traegt
    knoten = nahtknoten(model) if any(float(getattr(k, "kerbfall_naht", 0.0) or 0.0) > 0
                                      for k in koerper) else {}
    for k in koerper:
        idx = [int(i) for i in k.elemente
               if 0 <= int(i) < n_el and model.elements[int(i)].typ in EL.VOLUMEN_TYPEN]
        if not idx:
            continue
        gMf = GAMMA_MF.get((getattr(k, "assessment", "damage_tolerant"),
                            getattr(k, "consequence", "low")), 1.15)
        fv = FatigueVolumen(k.name, float(k.kerbfall), gMf,
                            konzept=str(getattr(k, "kerbfall_konzept", "") or ""),
                            category_grund=float(k.kerbfall),
                            category_naht=float(getattr(k, "kerbfall_naht", 0.0) or 0.0))
        fv.bezugsjahre = bezug
        fv.n_elemente = len(idx)
        if regel not in VOLUMEN_REGELN:
            # Keine stille Ersatzregel: der Nachweis bleibt als "nicht
            # gefuehrt" mit dem Grund stehen
            fv.regel = regel
            fv.fehler = (f"Einstellung ermuedung_volumen '{regel}' unbekannt - erlaubt sind "
                         "'knoten' (geglättete Knotenspannung) und 'element' (Elementwert)")
            out.volumen[k.name] = fv
            continue
        # Kerbfall je Element: der des Koerpers, an der Naht der der Naht
        cat = np.full(len(idx), float(k.kerbfall))
        an_naht = np.zeros(len(idx), bool)
        kn = knoten.get(k.name)
        if kn:
            an_naht = np.array([any(int(nd) in kn for nd in model.elements[i].nodes) for i in idx])
            if fv.category_naht > 0:
                cat[an_naht] = fv.category_naht
        fv.n_naht = int(an_naht.sum())
        signale: dict = {}
        hinweise: list = []          # kommen erst nach der Rechnung an den Nachweis
        orte = None

        def knotensignal(name):
            """(Signal je Ort, "") nach der Regel "knoten" - oder (None,
            Rueckfall-Hinweis). Ein Ort, an dem im Zustand kein Element des
            Koerpers wirkt (in der Situation abgeschaltet), traegt dort die
            Spannung 0: so rechnet die Elementregel das abgeschaltete Element
            (solver.postprocess gibt ihm Nullen - es wirkt nicht)."""
            r = all_res[name]
            S, fehlt = _knotenspannung(r, orte)
            if fehlt.any():
                offen = fehlt & ~_ohne_wirkendes_element(r, orte, idx)
                if offen.any():
                    return None, _rueckfall_hinweis(r, name, orte, offen)
            return signalspannung(S), ""

        if regel == "knoten" and benutzt:
            orte = _knotenorte(model, idx)
            if orte is None:
                hinweise.append("Volumenelemente ohne Eckknoten-Zuordnung - der Körper ist nach "
                                "der Regel „element“ mit dem Elementwert gerechnet.")
            else:
                for name in benutzt:
                    s, grund = knotensignal(name)
                    if s is None:
                        hinweise.append(grund)
                        orte = None
                        signale.clear()
                        break
                    signale[name] = s
        if orte is not None:
            # Regel "knoten": die Orte sind die Knoten; Kerbfall "Naht" an den
            # Nahtknoten selbst (dort sitzt die Naht)
            n_ort = len(orte["knoten"])
            element_je_ort = np.asarray(idx, np.int64)[orte["element_je_ort"]]
            cat_ort = np.full(n_ort, float(k.kerbfall))
            naht_ort = np.zeros(n_ort, bool)
            if kn:
                naht_ort = np.isin(orte["knoten"], np.fromiter((int(x) for x in kn), np.int64))
                if fv.category_naht > 0:
                    cat_ort[naht_ort] = fv.category_naht
            cat, an_naht = cat_ort, naht_ort
            # Fliessende Elemente: wie im statischen Nachweis von sigma n = 0
            # ausgenommen (solver.rand_projizieren, fliessend) - hier nur gesagt.
            # Der Knoten traegt dabei das Mittel ueber die Elemente an ihm; ein
            # fliessendes steuert nur den Wert seines naechsten
            # Integrationspunkts bei (solver._post_chunk). Gemessen 23.09.2026
            # am Kragarm 8x2x4, fy = 400 N/mm2, 24 Elemente fliessend: Knoten
            # an 8 Elementen (2 elastisch) sigma_xx 333,99 N/mm2, der naechste
            # Integrationspunkt des fliessenden Elements 451,62 - die Meldung
            # sagte bis dahin, der Knoten trage diesen Punktwert.
            im_koerper = set(idx)
            fliessen = []
            for name in benutzt:
                pl = (getattr(all_res[name], "info", None) or {}).get("plastisch") or {}
                n_fl = sum(1 for i in pl if int(i) in im_koerper)
                if n_fl:
                    fliessen.append((name, n_fl))
            if fliessen:
                if len(fliessen) == 1:
                    wo = f"Im Zustand {fliessen[0][0]} fließen {fliessen[0][1]} Elemente des Körpers"
                else:
                    wo = (f"In {len(fliessen)} Zuständen fließen Elemente des Körpers ("
                          + _aufzaehlen([f"{a}: {b}" for a, b in fliessen]) + ")")
                hinweise.append(
                    wo + ". Sie tragen zum Knotenmittel den Wert ihres nächsten Integrationspunkts "
                    "bei, und ihre Knoten sind wie im statischen Nachweis nicht auf σ·n = 0 "
                    "gezogen; die Schwingbreite dort ist aus plastisch gerechneten Zuständen "
                    "gebildet.")

            def ort(j):
                return (int(element_je_ort[j]), int(orte["knoten"][j]))
        else:
            n_ort = len(idx)

            def ort(j):
                return (idx[j],)

        def signal(name):
            s = signale.get(name)
            if s is None:
                if orte is not None:
                    # Unerreichbar, solange _benutzte_zustaende dieselben
                    # Bedingungen prueft wie die Schleife - sonst laut statt
                    # still mit einer anderen Regel
                    s, grund = knotensignal(name)
                    if s is None:
                        raise RuntimeError(f"Ermüdung Volumen {k.name}: {grund}")
                    signale[name] = s
                    return s
                sr = all_res[name].solid_res
                S = np.zeros((len(idx), 6))
                for r, i in enumerate(idx):
                    v = sr.get(i)
                    if v is not None:
                        S[r] = v
                s = signale[name] = signalspannung(S)
            return s

        D = np.zeros(n_ort)
        dsig = np.zeros(n_ort)
        stufen: list = []            # (Delta je Ort, n) der vektorisierten Lasten
        extra: dict = {}             # Ort -> [(Delta, n)] aus Rainflow/Reservoir
        beitrag = False
        for fl in model.fatigue_loads.values():
            faktor = fl.factor * ds.gamma_Ff
            if getattr(fl, "folge", None):
                namen = [f for f in fl.folge if f in all_res]
                fehlt = [f for f in fl.folge if f not in all_res]
                wdh = _wiederholungen(fl, ds)
                if fehlt:
                    _nicht_gerechnet(fv, fl, f"Ermuedungslast {fl.name}: Ergebnis '{fehlt[0]}' fehlt",
                                     wirksam=wdh > 0)
                if len(namen) < 2 or wdh <= 0:
                    continue
                V = np.stack([signal(f) for f in namen], axis=1) * faktor     # (n, Zustaende)
                verfahren = str(getattr(fl, "zaehlung", "spanne")).lower()
                if verfahren.startswith("span"):
                    d = V.max(axis=1) - V.min(axis=1)
                    D += wdh / _n_vektor(d, cat, gMf)
                    dsig = np.maximum(dsig, d)
                    stufen.append((d, wdh))
                    j = int(np.argmax(d))
                    fv.ranges.append((float(d[j]), wdh, fl.name) + ort(j))
                else:
                    gross, jg = 0.0, 0
                    for r in range(n_ort):
                        for h, z in _zaehlen(V[r], verfahren):
                            D[r] += z * wdh / sn_life(h, float(cat[r]), gMf)
                            extra.setdefault(r, []).append((h, z * wdh))
                            if h > dsig[r]:
                                dsig[r] = h
                            if h > gross:
                                gross, jg = h, r
                    n_g = sum(z for h, z in extra.get(jg, []) if h == gross)
                    fv.ranges.append((float(gross), float(n_g), fl.name) + ort(jg))
                beitrag = True
                continue
            if fl.case_max not in all_res:
                _nicht_gerechnet(fv, fl, f"Ermuedungslast {fl.name}: Ergebnis '{fl.case_max}' fehlt",
                                 wirksam=_spiele(fl, ds) > 0)
                continue
            spiele = _spiele(fl, ds)
            if spiele <= 0:
                continue
            if fl.case_min and fl.case_min not in all_res:
                # Siehe den Stabzweig: angegeben und nicht gerechnet ist nicht
                # null, sondern eine Last, die im Nachweis fehlt.
                _nicht_gerechnet(fv, fl,
                                 f"Ermuedungslast {fl.name}: Ergebnis '{fl.case_min}' des "
                                 f"Mindestzustands fehlt - die Last wird nicht gerechnet")
                continue
            a = signal(fl.case_max)
            b = signal(fl.case_min) if fl.case_min else 0.0
            d = np.abs(a - b) * faktor
            D += spiele / _n_vektor(d, cat, gMf)
            dsig = np.maximum(dsig, d)
            stufen.append((d, spiele))
            j = int(np.argmax(d))
            fv.ranges.append((float(d[j]), spiele, fl.name) + ort(j))
            beitrag = True
        fv.regel = "knoten" if orte is not None else "element"
        if not beitrag:
            # Siehe den Stabzweig: ein Koerper mit Kerbfall, zu dem keine
            # Ermuedungslast beitraegt, gehoert als "nicht gefuehrt" in den
            # Bericht und nicht aus ihm heraus.
            if fv.warnings:
                fv.fehler = fv.warnings[0]
                out.volumen[k.name] = fv
            else:
                # Kein Ergebnis fehlt, alle Lasten sind unwirksam (0 Spiele,
                # Verlauf mit einem Zustand): gewollt kein Eintrag, aber die
                # Zusammenfassung muss den Koerper nennen koennen.
                out.ohne_wirksame_last.append(f"Volumen {k.name}")
            continue
        j = int(np.argmax(D))
        fv.D = float(D[j])
        fv.category = float(cat[j])
        fv.naht = bool(an_naht[j])
        fv.dsig_max = float(dsig.max())
        fv.kollektiv = kollektiv([(float(d[j]), n) for d, n in stufen] + list(extra.get(j, [])))
        fv.dsig_E2 = equivalent_range(fv.kollektiv)
        fv.util = fv.D
        fv.jahre = lebensdauer(fv.util, bezug) if bezug > 0 else float("inf")
        fv.elemente = idx
        if orte is not None:
            fv.element, fv.knoten = ort(j)
            # Faerbung je Element: das groesste D an seinen Ecken
            De = np.zeros(len(idx))
            np.maximum.at(De, orte["zeile_element"], D[orte["zeile_ort"]])
            fv.D_je_element = De.astype(np.float32)
            fv.orte = np.asarray(orte["knoten"], np.int64)
            fv.dsig_je_ort = dsig.copy()
        else:
            fv.element = idx[j]
            fv.D_je_element = D.astype(np.float32)
        fv.warnings.extend(hinweise)
        out.volumen[k.name] = fv
        if progress:
            progress(f"Ermuedung Volumen {k.name}: D = {fv.util:.3f}")


def check_fatigue(model: Model, analysis, progress=None, n: int = None,
                  anteil=None) -> FatigueResults:
    """Ermuedungsnachweis aller Staebe mit Kerbfall fuer alle Ermuedungslasten.

    ``anteil=(von, bis)``: wie bei :func:`design.check_members` - dann meldet
    der Fortschritt auch den Anteil (Staebe 0…0,9 des Fensters, Volumen der
    Rest); ohne Angabe nur Text.

    **Die Schaedigung wird am Ort aufsummiert, nicht ueber Orte hinweg.**
    Miner zaehlt, was ein Punkt des Bauteils erlebt; die groesste Schwingbreite
    aus Last A und die aus Last B liegen aber im Allgemeinen an verschiedenen
    Stellen des Stabes. Wer sie addiert, addiert die Schaedigung zweier
    verschiedener Punkte und erhaelt eine Zahl, die nirgends auftritt. Gerechnet
    wird darum D an **jeder** Nachweisstelle und an jedem der vier Eckpunkte
    des Querschnitts; massgebend ist der groesste Wert, und der Ort steht dabei.

    Eine Ermuedungslast beschreibt entweder zwei Zustaende (case_max gegen
    case_min) oder einen **Verlauf** (``folge``) - dann wird das Kollektiv
    daraus gezaehlt: Vorgabe ist die Spanne Maximum minus Minimum (ein Spiel je
    Wiederholung), Rainflow und Reservoir (EN 1993-1-9, Anhang A) sind die
    Option fuer eine echte Zeitfolge. Die Schadensakkumulation ist immer
    Palmgren-Miner ueber alle Lasten am Ort.
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
    from .design import _anteil, _melde
    zu_pruefen = sum(1 for mem in model.members.values()
                     if mem.design and mem.detail_category is not None)
    _melde(progress, f"Ermuedung: {zu_pruefen} Staebe mit Kerbfall", _anteil(anteil, 0.0))
    geprueft = 0
    for mname, member in model.members.items():
        if not member.design or member.detail_category is None:
            continue
        geprueft += 1
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
                wdh = _wiederholungen(fl, ds)
                if wdh > 0 and any(fall not in all_res for fall in fl.folge):
                    # _verlauf hat die Warnung geschrieben; eine wirksame Last
                    # fehlt damit (ganz oder mit einem Teil ihres Verlaufs) in D
                    _fehlt_in_d(fm, fl)
                if sig is None:
                    continue
                xs = x
                if wdh <= 0:
                    # unwirksam - so kommen die Sammlungen aus dem RFEM-Import,
                    # damit ihre Ereignisse nicht doppelt zaehlen; frueher
                    # machte "or 1.0" aus 0 stillschweigend 1
                    continue
                verfahren = getattr(fl, "zaehlung", "spanne")
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
                _nicht_gerechnet(fm, fl, f"Ermuedungslast {fl.name}: Ergebnis '{fl.case_max}' fehlt",
                                 wirksam=_spiele(fl, ds) > 0)
                continue
            spiele = _spiele(fl, ds)
            if spiele <= 0:
                continue
            x, s_max, t_max = _stress_points(model, all_res[fl.case_max], member, n)
            xs = x
            if fl.case_min and fl.case_min not in all_res:
                # **Angegeben, aber nicht gerechnet ist nicht null.** Bis zum
                # 22.09.2026 fiel dieser Fall in denselben Zweig wie "kein
                # Mindestzustand angegeben" und setzte s_min = 0. Bei
                # wechselnder Beanspruchung - dem Regelfall - ist das die
                # halbe Schwingbreite: aus -80/+100 N/mm2 wurden 100 statt
                # 180. Da D mit der dritten bis fuenften Potenz eingeht, faellt
                # die Schaedigung um den Faktor 6 bis 25 zu klein aus, und
                # zwar auf der unsicheren Seite. Der fehlende HOECHSTzustand
                # wurde die ganze Zeit gemeldet - der Mindestzustand nicht.
                # Traegt eine andere Last bei, ist der Nachweis damit nicht
                # "nicht gefuehrt", sondern unvollstaendig (fehlende_lasten).
                _nicht_gerechnet(fm, fl,
                                 f"Ermuedungslast {fl.name}: Ergebnis '{fl.case_min}' des "
                                 f"Mindestzustands fehlt - die Last wird nicht gerechnet")
                continue
            if fl.case_min:
                _, s_min, t_min = _stress_points(model, all_res[fl.case_min], member, n)
            else:
                # Kein Mindestzustand angegeben: der Zustand schwingt gegen
                # null, und das ist hier richtig.
                s_min = np.zeros_like(s_max)
                t_min = np.zeros_like(t_max)
            dsig = np.abs(s_max - s_min) * faktor          # (4, nstat)
            dtau = np.abs(t_max - t_min) * faktor          # (nstat,)
            for p_ in range(dsig.shape[0]):
                for j in range(dsig.shape[1]):
                    sammlung.setdefault((p_, j), []).append((float(dsig[p_, j]), spiele))
            for j in range(dtau.shape[0]):
                sammlung_t.setdefault(j, []).append((float(dtau[j]), spiele))
            j = int(np.argmax(dsig.max(axis=0)))
            fm.ranges.append((float(dsig[:, j].max()), spiele, fl.name, float(x[j])))
            k = int(np.argmax(dtau))
            fm.ranges_shear.append((float(dtau[k]), spiele, fl.name, float(x[k])))
        if not sammlung:
            # Der Stab bleibt im Nachweis stehen - als **nicht gefuehrt**.
            # Vorher verschwand er hier samt seinen Warnungen, und der
            # Bericht zeigte ihn gar nicht: ein fehlender Nachweis sah aus
            # wie ein Stab ohne Ermuedungsbeanspruchung.
            if fm.warnings:
                fm.fehler = fm.warnings[0]
                out.members[mname] = fm
            else:
                # alle Lasten unwirksam - siehe FatigueResults.ohne_wirksame_last
                out.ohne_wirksame_last.append(f"Stab {mname}")
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
            _melde(progress, f"Ermuedung {mname}: D = {fm.util:.3f}",
                   _anteil(anteil, 0.9 * geprueft / max(1, zu_pruefen)))
    if anteil is not None:
        _melde(progress, "Ermuedung: Volumen", _anteil(anteil, 0.9))
    _volumen_nachweisen(model, all_res, ds, out, bezug, progress)
    if anteil is not None:
        _melde(progress, "Ermuedung fertig", _anteil(anteil, 1.0))
    return out
