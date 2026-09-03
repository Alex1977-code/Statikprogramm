"""
Lastfallklassen und Kombinationen für Stahlwasserbauten und bewegliche Brücken
(DIN 19704, ZTV-ING).

**Was dieses Modul leistet und was es nicht leistet.** Es bildet das *Verfahren*
ab: die Einteilung der Einwirkungen, die drei Lastfallklassen, die Bildung der
Kombinationen daraus, die Zuordnung zu den Stellungen des Systems und die
Auswertung. Die *Zahlenwerte* der Teilsicherheits- und Kombinationsbeiwerte
stehen in einer Tabelle, die mitgeliefert, aber **vom Anwender gegen die
geltende Fassung der Norm zu bestätigen** ist: sie sind hier als Voreinstellung
geführt, nicht als Zitat. `FAKTOREN.quelle` sagt das bei jedem Wert, und der
Bericht weist ungeprüfte Werte aus.

Das ist Absicht. Ein Programm, das Beiwerte aus dem Gedächtnis behauptet, ist
schlimmer als eines, das die Tabelle offen zur Bestätigung vorlegt.

    Lastfallklassen (DIN 19704-1)
      LF1  Normalfall           regelmäßiger Betrieb
      LF2  Sonderfall           seltene, planmäßig mögliche Zustände
      LF3  außergewöhnlich      Bau-, Revisions- und Störfall

    from statik3d.bridges.din19704 import Einwirkungen, Regelwerk
    rw = Regelwerk()
    rw.faktor("LF1", "G", 1.35)          # eigenen Wert setzen
    kombis = rw.kombinationen(modell)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model import Model

#: Einwirkungsarten im Stahlwasserbau und bei beweglichen Brücken
EINWIRKUNGEN = {
    "G":      "Eigengewicht der Konstruktion",
    "G_A":    "Eigengewicht der Ausrüstung und des Antriebs",
    "W_S":    "Wasserdruck, ständig (Stauziel)",
    "W_V":    "Wasserdruck, veränderlich (Betriebswasserstände)",
    "Q":      "Verkehrslast",
    "Q_BEW":  "Betriebslast beim Bewegen",
    "A_M":    "Antriebsmoment, planmäßig",
    "A_MG":   "Antriebsmoment, Grenzmoment der Rutschkupplung",
    "W":   "Windlast im Ruhezustand",
    "WIND_B": "Windlast während der Bewegung",
    "EIS":    "Eisdruck, Eislast",
    "T":   "Temperatur",
    "SCHWALL": "Schwall und Sunk, Wellendruck",
    "ANPRALL": "Anprall (Schiff, Treibgut)",
    "KLEMM":  "Verklemmen, Blockieren eines Antriebsstrangs",
    "MONT":   "Montage- und Revisionszustand",
    "ERD":    "Erdbeben",
}

#: Welche Einwirkung gehört in welche Lastfallklasse (DIN 19704-1)
KLASSEN = {
    "LF1": ["G", "G_A", "W_S", "W_V", "Q", "Q_BEW", "A_M", "W", "T"],
    "LF2": ["G", "G_A", "W_S", "W_V", "Q", "Q_BEW", "A_M", "A_MG", "W", "WIND_B",
            "EIS", "T", "SCHWALL"],
    "LF3": ["G", "G_A", "W_S", "Q_BEW", "A_MG", "WIND_B", "EIS", "ANPRALL", "KLEMM",
            "MONT", "ERD"],
}

KLASSEN_TEXT = {
    "LF1": "Normalfall - regelmäßiger Betrieb",
    "LF2": "Sonderfall - seltene, planmäßig mögliche Zustände",
    "LF3": "außergewöhnlicher Fall - Bau-, Revisions- und Störfall",
}


@dataclass
class Faktor:
    """Ein Beiwert mit Herkunft. bestaetigt=False heißt: noch nicht geprüft."""
    wert: float
    quelle: str = "Voreinstellung - gegen die geltende Norm zu bestätigen"
    bestaetigt: bool = False

    def __float__(self) -> float:
        return float(self.wert)


def _f(w: float, quelle: str = "") -> Faktor:
    return Faktor(w, quelle or "Voreinstellung - gegen die geltende Norm zu bestätigen")


class Regelwerk:
    """Teilsicherheits- und Kombinationsbeiwerte je Lastfallklasse.

    Die mitgelieferten Werte sind **Voreinstellungen**. `faktor()` setzt einen
    Wert und kennzeichnet ihn als bestätigt; `offen()` nennt alle noch nicht
    bestätigten Werte, und `bericht()` schreibt die Tabelle mit Herkunft.
    """

    def __init__(self, name: str = "DIN 19704-1 / ZTV-ING"):
        self.name = name
        # gamma_F je Lastfallklasse und Einwirkung (unguenstig wirkend)
        self.gamma_F: dict[str, dict[str, Faktor]] = {
            "LF1": {"G": _f(1.35), "G_A": _f(1.35), "W_S": _f(1.35), "W_V": _f(1.50),
                    "Q": _f(1.50), "Q_BEW": _f(1.50), "A_M": _f(1.50), "W": _f(1.50),
                    "T": _f(1.50)},
            "LF2": {"G": _f(1.35), "G_A": _f(1.35), "W_S": _f(1.35), "W_V": _f(1.35),
                    "Q": _f(1.35), "Q_BEW": _f(1.35), "A_M": _f(1.35), "A_MG": _f(1.35),
                    "W": _f(1.35), "WIND_B": _f(1.35), "EIS": _f(1.35),
                    "T": _f(1.35), "SCHWALL": _f(1.35)},
            "LF3": {"G": _f(1.00), "G_A": _f(1.00), "W_S": _f(1.00), "Q_BEW": _f(1.00),
                    "A_MG": _f(1.00), "WIND_B": _f(1.00), "EIS": _f(1.00),
                    "ANPRALL": _f(1.00), "KLEMM": _f(1.00), "MONT": _f(1.00),
                    "ERD": _f(1.00)},
        }
        #: guenstig wirkendes Eigengewicht
        self.gamma_F_guenstig = _f(1.00)
        #: gamma_M je Lastfallklasse
        self.gamma_M: dict[str, dict[str, Faktor]] = {
            "LF1": {"M0": _f(1.00), "M1": _f(1.10), "M2": _f(1.25)},
            "LF2": {"M0": _f(1.00), "M1": _f(1.10), "M2": _f(1.25)},
            "LF3": {"M0": _f(1.00), "M1": _f(1.00), "M2": _f(1.10)},
        }
        #: Kombinationsbeiwerte psi_0 der veränderlichen Einwirkungen
        self.psi0: dict[str, Faktor] = {
            "Q": _f(0.80), "Q_BEW": _f(0.80), "W": _f(0.60), "WIND_B": _f(0.60),
            "EIS": _f(0.60), "T": _f(0.60), "W_V": _f(0.80), "SCHWALL": _f(0.60),
            "A_M": _f(1.00), "A_MG": _f(1.00),
        }
        #: ständige Einwirkungen (immer in jeder Kombination)
        self.staendig = {"G", "G_A", "W_S"}

    # -- Werte setzen und pruefen ----------------------------------------
    def faktor(self, klasse: str, einwirkung: str, wert: float,
               quelle: str = "vom Anwender bestätigt") -> Faktor:
        """Teilsicherheitsbeiwert setzen und als bestätigt kennzeichnen."""
        if klasse not in self.gamma_F:
            raise KeyError(f"Lastfallklasse '{klasse}' unbekannt: {sorted(self.gamma_F)}")
        f = Faktor(float(wert), quelle, True)
        self.gamma_F[klasse][einwirkung] = f
        return f

    def material_faktor(self, klasse: str, welcher: str, wert: float,
                        quelle: str = "vom Anwender bestätigt") -> Faktor:
        self.gamma_M.setdefault(klasse, {})[welcher] = Faktor(float(wert), quelle, True)
        return self.gamma_M[klasse][welcher]

    def kombinationsbeiwert(self, einwirkung: str, wert: float,
                            quelle: str = "vom Anwender bestätigt") -> Faktor:
        self.psi0[einwirkung] = Faktor(float(wert), quelle, True)
        return self.psi0[einwirkung]

    def offen(self) -> list[str]:
        """Alle noch nicht bestätigten Beiwerte."""
        out = []
        for kl, d in self.gamma_F.items():
            out += [f"gamma_F[{kl}][{e}] = {f.wert:g}" for e, f in d.items()
                    if not f.bestaetigt]
        for kl, d in self.gamma_M.items():
            out += [f"gamma_{w}[{kl}] = {f.wert:g}" for w, f in d.items()
                    if not f.bestaetigt]
        out += [f"psi_0[{e}] = {f.wert:g}" for e, f in self.psi0.items()
                if not f.bestaetigt]
        return out

    def bericht(self) -> str:
        z = [f"Beiwerte - {self.name}", "=" * 78,
             "Die Werte sind Voreinstellungen, soweit nicht als bestätigt "
             "gekennzeichnet.", ""]
        for kl in ("LF1", "LF2", "LF3"):
            z.append(f"{kl} - {KLASSEN_TEXT[kl]}")
            for e in KLASSEN[kl]:
                f = self.gamma_F[kl].get(e)
                if f is None:
                    continue
                z.append(f"    gamma_F  {e:<8s} {f.wert:5.2f}   "
                         f"{'bestätigt' if f.bestaetigt else 'zu bestätigen'}"
                         f"   {EINWIRKUNGEN.get(e, '')}")
            for w, f in self.gamma_M.get(kl, {}).items():
                z.append(f"    gamma_{w:<3s}          {f.wert:5.2f}   "
                         f"{'bestätigt' if f.bestaetigt else 'zu bestätigen'}")
            z.append("")
        z.append("Kombinationsbeiwerte psi_0:")
        for e, f in self.psi0.items():
            z.append(f"    {e:<8s} {f.wert:5.2f}   "
                     f"{'bestätigt' if f.bestaetigt else 'zu bestätigen'}"
                     f"   {EINWIRKUNGEN.get(e, '')}")
        offen = self.offen()
        z.append("")
        z.append(f"{len(offen)} Beiwerte sind noch zu bestätigen."
                 if offen else "Alle Beiwerte sind bestätigt.")
        return "\n".join(z)

    # -- Kombinationen ---------------------------------------------------
    def kombinationen(self, model: Model, klassen=None, praefix: str = "DIN ",
                      log: list = None) -> list[str]:
        """Kombinationen nach den Lastfallklassen bilden.

        Jeder Lastfall braucht in `LoadCase.category` seine Einwirkungsart
        (Schlüssel aus EINWIRKUNGEN). Für jede Lastfallklasse und jede
        veränderliche Einwirkung als Leiteinwirkung entsteht eine Kombination:

            sum gamma_F,i G_i  +  gamma_F,l Q_l  +  sum gamma_F,j psi_0,j Q_j

        Die Namen tragen den Präfix "DIN ", damit sie nicht mit den
        Lastfallnamen des Modells verwechselt werden.

        Rückgabe: Namen der angelegten Kombinationen.
        """
        klassen = list(klassen or ("LF1", "LF2", "LF3"))
        nach_art: dict[str, list[str]] = {}
        for name, lc in model.load_cases.items():
            nach_art.setdefault((lc.category or "Q").strip(), []).append(name)
        angelegt = []
        for kl in klassen:
            erlaubt = set(KLASSEN.get(kl, []))
            staendig = [(a, n) for a, ns in nach_art.items() if a in self.staendig
                        and a in erlaubt for n in ns]
            veraenderlich = [(a, n) for a, ns in nach_art.items()
                             if a not in self.staendig and a in erlaubt for n in ns]
            if not staendig and not veraenderlich:
                continue
            if not veraenderlich:
                faktoren = {n: float(self.gamma_F[kl].get(a, _f(1.0))) for a, n in staendig}
                nm = f"{praefix}{kl}"
                model.add_combination(nm, faktoren, typ="ULS",
                                      description=f"{kl} - nur ständige Einwirkungen")
                angelegt.append(nm)
                continue
            for k, (art_l, leit) in enumerate(veraenderlich, 1):
                faktoren = {n: float(self.gamma_F[kl].get(a, _f(1.0))) for a, n in staendig}
                faktoren[leit] = float(self.gamma_F[kl].get(art_l, _f(1.0)))
                for art_j, begleit in veraenderlich:
                    if begleit == leit:
                        continue
                    g = float(self.gamma_F[kl].get(art_j, _f(1.0)))
                    psi = float(self.psi0.get(art_j, _f(1.0)))
                    faktoren[begleit] = g * psi
                nm = f"{praefix}{kl}.{k}"
                model.add_combination(
                    nm, faktoren, typ="ULS",
                    description=f"{kl}, Leiteinwirkung {art_l} ({leit}) - "
                                f"{KLASSEN_TEXT[kl]}")
                angelegt.append(nm)
        if log is not None:
            log.append(f"{len(angelegt)} Kombinationen nach {self.name} gebildet "
                       f"({', '.join(klassen)})")
            for z in self.offen()[:5]:
                log.append(f"  zu bestätigen: {z}")
            if len(self.offen()) > 5:
                log.append(f"  ... und {len(self.offen()) - 5} weitere Beiwerte")
        return angelegt


#: ZTV-ING: zusätzliche Anforderungen an bewegliche Brücken, die das Programm
#: prüfen kann. Jede Angabe nennt, was geprüft wird und was der Anwender
#: festlegen muss.
ZTV_ING_PRUEFUNGEN = [
    ("stellungen", "Alle Betriebsstellungen sind zu untersuchen, nicht nur die "
                   "Endlagen.", "Stellungsreihe mit Zwischenstellungen anlegen"),
    ("antrieb", "Das Antriebsmoment ist als Einwirkung anzusetzen, im Störfall "
                "mit dem Grenzmoment der Rutschkupplung.",
     "Stellung.antrieb setzen, Einwirkung A_M bzw. A_MG"),
    ("wind_bewegung", "Während der Bewegung ist die dafür festgelegte Windlast "
                      "anzusetzen.", "Lastfall mit category='WIND_B'"),
    ("verklemmen", "Das Verklemmen eines Antriebsstrangs ist als "
                   "außergewöhnliche Einwirkung zu untersuchen.",
     "Lastfall mit category='KLEMM' in LF3"),
    ("ermuedung", "Für die Betriebsfestigkeit ist die Zahl der Bewegungen über "
                  "die Nutzungsdauer anzusetzen.",
     "Lastwechselzahl aus Bewegungen je Jahr mal Nutzungsdauer"),
    ("riegel", "Verriegelungen und Endlagerungen sind in ihren wirksamen und "
               "unwirksamen Zuständen zu untersuchen.",
     "Stellung.lager_aktiv bzw. lager_aus je Stellung"),
]


def bewegungen(je_jahr: float, jahre: float = 100.0) -> float:
    """Lastwechsel aus Bewegungen je Jahr und Nutzungsdauer.

    Eine Bewegung (Öffnen und Schließen) ergibt einen vollen Spannungswechsel
    in den Bauteilen, die dabei ihre Beanspruchung wechseln.
    """
    return float(je_jahr) * float(jahre)


def pruefliste(reihe=None, model: Model = None) -> list[tuple[str, bool, str]]:
    """ZTV-ING-Prüfliste gegen ein Modell und eine Stellungsreihe.

    Rückgabe: [(Thema, erfüllt, Hinweis)]. Was das Programm nicht selbst sehen
    kann, wird als offen ausgewiesen - nicht als erfüllt behauptet.
    """
    out = []
    arten = {(lc.category or "").strip() for lc in (model.load_cases.values()
                                                    if model else [])}
    n_st = len(reihe) if reihe is not None else 0
    zwischen = 0
    if reihe is not None:
        winkel = sorted(s.winkel for s in reihe.stellungen)
        zwischen = max(0, len(winkel) - 2)
    out.append(("Betriebsstellungen", n_st >= 3,
                f"{n_st} Stellungen, davon {zwischen} Zwischenstellungen"
                if n_st else "keine Stellungsreihe angelegt"))
    hat_antrieb = any(s.antrieb for s in reihe.stellungen) if reihe is not None else False
    quelle = []
    if hat_antrieb:
        quelle.append("Stellung.antrieb")
    if "A_M" in arten:
        quelle.append("Lastfall A_M")
    if "A_MG" in arten:
        quelle.append("Lastfall A_MG (Grenzmoment)")
    out.append(("Antriebsmoment", bool(quelle),
                "angesetzt über " + " und ".join(quelle) if quelle
                else "kein Antriebsmoment gefunden (Stellung.antrieb oder Lastfall A_M)"))
    if quelle and "A_MG" not in arten:
        out.append(("Grenzmoment der Kupplung", False,
                    "planmäßiges Antriebsmoment vorhanden, aber kein Lastfall "
                    "A_MG für das Grenzmoment der Rutschkupplung (LF3)"))
    out.append(("Wind während der Bewegung", "WIND_B" in arten,
                "Lastfall mit category='WIND_B' vorhanden" if "WIND_B" in arten
                else "kein Lastfall für Wind während der Bewegung"))
    out.append(("Verklemmen", "KLEMM" in arten,
                "als außergewöhnliche Einwirkung angesetzt" if "KLEMM" in arten
                else "kein Lastfall category='KLEMM'"))
    hat_riegel = any(s.lager_aus or s.lager_aktiv
                     for s in reihe.stellungen) if reihe is not None else False
    out.append(("Verriegelung und Endlagerung", hat_riegel,
                "Lagerzustände je Stellung geführt" if hat_riegel
                else "keine Stellung ändert die wirksamen Lager"))
    ermued = any(getattr(lc, "category", "") in ("Q_BEW",) for lc in
                 (model.load_cases.values() if model else []))
    out.append(("Betriebsfestigkeit", False,
                "Lastwechselzahl aus Bewegungen je Jahr festlegen "
                "(bewegungen()); vom Programm nicht ableitbar"))
    return out
