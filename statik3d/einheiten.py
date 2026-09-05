"""
Einheiten und Genauigkeiten für Ansicht und Tabellen.

Gerechnet wird in SI (N, m, Pa); gezeigt wird, was der Anwender eingestellt
hat: Kraft in N, kN oder MN, Länge in m, cm oder mm, Verformung in mm, cm
oder m, Spannung in N/mm², MPa oder kN/cm². Moment, Strecken- und
Flächenlast folgen aus Kraft und Länge (kN·m, kN/m, kN/m²). Je Größe gibt es
Nachkommastellen.

Die Tabellen des unteren Bereichs führen ihre Spalten in Grundeinheiten
(kN, kNm, kN/m, kN/m², m, mm, N/mm²); ``anzeige`` sagt, mit welchem Faktor,
welcher Beschriftung und wie vielen Nachkommastellen eine solche Spalte
gezeigt wird. Die Ansicht rechnet aus SI mit ``aus_si``.
"""
from __future__ import annotations

from dataclasses import dataclass

KRAFT = {"N": 1.0, "kN": 1e-3, "MN": 1e-6}                # SI-Newton -> Einheit
LAENGE = {"m": 1.0, "cm": 100.0, "mm": 1000.0}            # SI-Meter -> Einheit
SPANNUNG = {"N/mm²": 1e-6, "MPa": 1e-6, "kN/cm²": 1e-7}   # SI-Pascal -> Einheit
WAHL = {"kraft": list(KRAFT), "laenge": list(LAENGE), "verformung": ["mm", "cm", "m"],
        "spannung": list(SPANNUNG)}


@dataclass
class Einheiten:
    kraft: str = "kN"
    laenge: str = "m"
    verformung: str = "mm"
    spannung: str = "N/mm²"
    winkel: str = "°"
    temperatur: str = "K"
    nk_kraft: int = 2
    nk_laenge: int = 3
    nk_verformung: int = 2
    nk_spannung: int = 1
    nk_winkel: int = 1
    nk_ausnutzung: int = 3
    nk_last: int = 2          # Lastwerte in der Ansicht (Kraft, Strecken-, Flächenlast)

    # -- Einheit und Faktor je Größe (aus SI) ---------------------------------
    def einheit(self, art: str) -> str:
        if art == "kraft":
            return self.kraft
        if art == "laenge":
            return self.laenge
        if art == "verformung":
            return self.verformung
        if art == "spannung":
            return self.spannung
        if art == "moment":
            return f"{self.kraft}{self.laenge}"
        if art == "strecke":
            return f"{self.kraft}/{self.laenge}"
        if art == "flaechenlast":
            return f"{self.kraft}/{self.laenge}²"
        if art == "winkel":
            return self.winkel
        if art == "temperatur":
            return self.temperatur
        if art == "zwang":
            return self.verformung
        return ""

    def faktor(self, art: str) -> float:
        """SI-Wert · Faktor = Anzeigewert."""
        fk, fl = KRAFT[self.kraft], LAENGE[self.laenge]
        if art == "kraft":
            return fk
        if art == "laenge":
            return fl
        if art in ("verformung", "zwang"):
            return LAENGE[self.verformung]
        if art == "spannung":
            return SPANNUNG[self.spannung]
        if art == "moment":
            return fk * fl
        if art == "strecke":
            return fk / fl
        if art == "flaechenlast":
            return fk / fl ** 2
        return 1.0

    def nk(self, art: str) -> int:
        return {"kraft": self.nk_kraft, "moment": self.nk_kraft, "laenge": self.nk_laenge,
                "verformung": self.nk_verformung, "zwang": self.nk_verformung,
                "spannung": self.nk_spannung, "winkel": self.nk_winkel,
                "ausnutzung": self.nk_ausnutzung, "strecke": self.nk_last,
                "flaechenlast": self.nk_last, "temperatur": 1}.get(art, 2)

    def aus_si(self, wert: float, art: str) -> float:
        return float(wert) * self.faktor(art)

    def text(self, wert_si: float, art: str, nk: int = None, mit_einheit: bool = True) -> str:
        n = self.nk(art) if nk is None else int(nk)
        s = f"{self.aus_si(wert_si, art):.{n}f}"
        return s + (f" {self.einheit(art)}" if mit_einheit and self.einheit(art) else "")

    def zahl(self, wert_si: float, art: str, nk: int = None) -> str:
        """Kurz und ohne Nachkommanullen - für Beschriftungen in der Ansicht."""
        n = self.nk(art) if nk is None else int(nk)
        s = f"{self.aus_si(wert_si, art):.{n}f}".rstrip("0").rstrip(".")
        return s or "0"

    # -- Tabellenspalten in Grundeinheiten -----------------------------------
    #: Grundeinheit einer Spalte -> (Größe, Faktor Grundeinheit -> SI)
    GRUND = {"kN": ("kraft", 1e3), "N": ("kraft", 1.0), "kNm": ("moment", 1e3), "Nm": ("moment", 1.0),
             "kN/m": ("strecke", 1e3), "kN/m²": ("flaechenlast", 1e3), "kN/m2": ("flaechenlast", 1e3),
             "m": ("laenge", 1.0), "mm": ("verformung", 1e-3), "N/mm²": ("spannung", 1e6),
             "MPa": ("spannung", 1e6), "N/mm2": ("spannung", 1e6)}

    def anzeige(self, grundeinheit: str, nk_basis: int = 3) -> tuple:
        """(Faktor, Beschriftung, Nachkommastellen) für eine Tabellenspalte,
        deren Werte in ``grundeinheit`` stehen; unbekannte Einheiten bleiben."""
        g = self.GRUND.get(grundeinheit or "")
        if g is None:
            return 1.0, grundeinheit or "", int(nk_basis)
        art, nach_si = g
        return nach_si * self.faktor(art), self.einheit(art), self.nk(art)

    def beschreibung(self) -> str:
        return (f"Kraft {self.kraft}, Länge {self.laenge}, Verformung {self.verformung}, "
                f"Spannung {self.spannung}; Nachkommastellen Kraft {self.nk_kraft}, Länge {self.nk_laenge}, "
                f"Verformung {self.nk_verformung}, Spannung {self.nk_spannung}, Ausnutzung {self.nk_ausnutzung}")
