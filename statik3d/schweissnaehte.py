"""
Schweißnähte im Modell und ihre Kerbfälle nach DIN EN 1993-1-9.

Eine Schweißnaht wird als Objekt angegeben (Nahtart, Lage zur Beanspruchung,
Ausführung, Prüfung, angeschlossene Teile) und den Stäben, Linien oder
Flächen zugeordnet, an denen sie liegt. Daraus folgt der **Kerbfall**
(Tabellen 8.2 bis 8.5 der EN 1993-1-9) für den Ermüdungsnachweis - der
Stab bekommt den ungünstigsten Kerbfall aller Nähte, die ihn betreffen.

Die Option **äquivalent** kennzeichnet eine Ersatznaht: eine Naht, die
stellvertretend für alle (nicht einzeln modellierten) Nähte eines Bauteils
oder des ganzen Modells steht. Sie gilt für alle Stäbe (oder die genannten)
als umhüllender Kerbfall; einzeln angegebene Nähte, die ungünstiger sind,
gehen vor.

Größeneinfluss: für Quernähte, Steifen und Kreuzstöße mit Blechdicken über
25 mm wird der Kerbfall mit k_s = (25/t)^0,2 abgemindert (Tab. 8.3 bis 8.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

#: Nahtarten, die das Programm kennt
NAHTARTEN = ["Stumpfnaht", "HV-Naht", "DHV-Naht", "Kehlnaht", "Doppelkehlnaht",
             "Steifenanschluss", "Längssteife", "Deckblech-Ende"]
LAGEN = ["längs", "quer"]
AUSFUEHRUNGEN = ["automatisch", "automatisch mit Ansatzstellen", "von Hand"]
DURCHGESCHWEISST = ("Stumpfnaht", "HV-Naht", "DHV-Naht")
KEHLNAEHTE = ("Kehlnaht", "Doppelkehlnaht")


@dataclass
class Schweissnaht:
    """Eine Schweißnaht (oder eine äquivalente Ersatznaht) im Modell."""
    name: str
    art: str = "Kehlnaht"
    lage: str = "längs"                 # zur Beanspruchungsrichtung
    a: float = 5.0                      # Nahtdicke a [mm] (Kehlnaht) bzw. 0 = ohne Angabe
    t: float = 0.0                      # Blechdicke [mm] (Größeneinfluss, Deckblech); 0 = unbekannt
    l_anschluss: float = 0.0            # Breite des angeschlossenen Teils in Beanspruchungsrichtung [mm]
    ausfuehrung: str = "von Hand"
    bearbeitet: bool = False            # blecheben geschliffen / Nahtende bearbeitet
    geprueft: bool = False              # zerstörungsfrei geprüft
    einseitig: bool = False             # Stumpfnaht von einer Seite
    gegenlage: bool = False             # mit Badsicherung (Gegenlage)
    unterbrochen: bool = False          # unterbrochene Kehlnaht
    freischnitt: bool = False           # Naht mit Freischnitten (Ausnehmungen)
    aequivalent: bool = False           # Ersatznaht fuer alle (oder die genannten) Staebe
    staebe: list = field(default_factory=list)
    linien: list = field(default_factory=list)
    flaechen: list = field(default_factory=list)
    kerbfall_vorgabe: Optional[float] = None        # Δσ_C [MPa]; None = aus der Nahtart
    kerbfall_schub_vorgabe: Optional[float] = None  # Δτ_C [MPa]
    kommentar: str = ""

    def bezug(self) -> str:
        t = f"{self.art}, {self.lage}"
        if self.a and self.art in KEHLNAEHTE:
            t += f", a = {self.a:g} mm"
        if self.aequivalent:
            t += ", äquivalent"
        ziele = self.staebe + self.linien + self.flaechen
        if ziele:
            t += ": " + ", ".join(ziele[:4]) + (" …" if len(ziele) > 4 else "")
        elif self.aequivalent:
            t += ": alle Stäbe"
        return t


# ==========================================================================
# Kerbfall
# ==========================================================================
def _nach_laenge(l_mm: float, stufen) -> float:
    """Kerbfall nach der Anschlussbreite ℓ: stufen = [(l_max, Δσ_C), …, (None, Δσ_C)]."""
    for grenze, wert in stufen:
        if grenze is None or l_mm <= grenze:
            return wert
    return stufen[-1][1]


def groesseneinfluss(t_mm: float) -> float:
    """k_s = (25/t)^0,2 für t > 25 mm (Tab. 8.3 bis 8.5), sonst 1."""
    return (25.0 / t_mm) ** 0.2 if t_mm and t_mm > 25.0 else 1.0


def kerbfall(n: Schweissnaht) -> dict:
    """Kerbfall Δσ_C, Δτ_C [MPa], Größeneinfluss und Fundstelle einer Naht."""
    ds, dt, detail, hinweis, wurzel = 0.0, 100.0, "", "", None
    groesse = False
    art, lage = n.art, n.lage
    if art in DURCHGESCHWEISST or (art in KEHLNAEHTE and lage == "längs"):
        if lage == "längs":
            # Tabelle 8.2: Längsnähte
            if n.unterbrochen and art in KEHLNAEHTE:
                ds, detail = 71.0, "Tab. 8.2, Detail 8 (unterbrochene Kehlnaht)"
            elif n.freischnitt:
                ds, detail = 63.0, "Tab. 8.2, Detail 9 (Naht mit Freischnitten ≤ 60 mm)"
            elif n.einseitig and art in DURCHGESCHWEISST:
                if n.ausfuehrung == "automatisch" and n.gegenlage:
                    ds, detail = 100.0, "Tab. 8.2, Detail 5 (einseitig automatisch mit Gegenlage)"
                elif n.gegenlage:
                    ds, detail = 80.0, "Tab. 8.2, Detail 5/6 (einseitig mit Gegenlage, Ansatzstellen)"
                else:
                    ds, detail = (80.0, "Tab. 8.2, Detail 6 (einseitig, Wurzel geprüft)") if n.geprueft \
                        else (71.0, "Tab. 8.2, Detail 6 (einseitig, ungeprüft)")
            elif n.ausfuehrung == "automatisch":
                ds, detail = 125.0, "Tab. 8.2, Detail 1/2 (automatisch, ohne Ansatzstellen)"
            elif n.ausfuehrung == "automatisch mit Ansatzstellen":
                ds, detail = 112.0, "Tab. 8.2, Detail 3 (automatisch mit Ansatzstellen)"
            else:
                ds, detail = 100.0, "Tab. 8.2, Detail 4 (Naht von Hand)"
            dt = 100.0 if art in DURCHGESCHWEISST else 80.0
            if art in KEHLNAEHTE:
                hinweis = "Schub in der Kehlnaht: Δτ_C = 80 (Tab. 8.5, Detail 8)"
        else:
            # Tabelle 8.3: Quernähte (durchgeschweißt)
            groesse = True
            if n.einseitig:
                if n.gegenlage:
                    ds, detail = 71.0, "Tab. 8.3, Detail 9 (einseitig mit Badsicherung)"
                elif n.geprueft:
                    ds, detail = 71.0, "Tab. 8.3, Detail 11 (einseitig, Wurzel geprüft)"
                else:
                    ds, detail = 36.0, "Tab. 8.3, Detail 11 (einseitig, ungeprüft)"
            elif n.bearbeitet and n.geprueft:
                ds, detail = 112.0, "Tab. 8.3, Detail 1 (blecheben bearbeitet, geprüft)"
            elif n.geprueft and not n.freischnitt:
                ds, detail = 90.0, "Tab. 8.3, Detail 2/3 (Überhöhung ≤ 10 %, geprüft)"
            else:
                ds, detail = 80.0, ("Tab. 8.3, Detail 4/5 (mit Freischnitten)" if n.freischnitt
                                    else "Tab. 8.3, Detail 5 (unbearbeitet, ungeprüft)")
            dt = 100.0
    elif art in KEHLNAEHTE:
        # Tabelle 8.5, Detail 1-3: Kreuz- und T-Stoß, Kehlnaht quer zur Beanspruchung
        groesse = True
        ds = _nach_laenge(n.l_anschluss or 0.0, [(50, 80.0), (80, 71.0), (100, 63.0), (120, 56.0),
                                                  (200, 50.0), (300, 45.0), (None, 40.0)])
        detail = "Tab. 8.5, Detail 3 (Kehlnaht quer, Kreuz-/T-Stoß)"
        wurzel = 36.0
        hinweis = "Nahtwurzel: Δσ_C = 36 in der Nahtdicke (Tab. 8.5, Detail 3); Schub Δτ_C = 80"
        dt = 80.0
    elif art == "Steifenanschluss":
        # Tabelle 8.4, Detail 6/7: Quersteife
        groesse = True
        ds = 80.0 if (n.l_anschluss or 0.0) <= 50.0 else 71.0
        detail = "Tab. 8.4, Detail 6/7 (Quersteife" + (" ℓ ≤ 50 mm" if ds == 80.0 else " 50 < ℓ ≤ 80 mm") + ")"
        dt = 100.0
    elif art == "Längssteife":
        # Tabelle 8.4, Detail 1/2: Längssteife (L in Beanspruchungsrichtung)
        ds = _nach_laenge(n.l_anschluss or 0.0, [(50, 80.0), (80, 71.0), (100, 63.0), (None, 56.0)])
        detail = "Tab. 8.4, Detail 1/2 (Längssteife, L = " + f"{n.l_anschluss:g} mm)"
        dt = 100.0
    elif art == "Deckblech-Ende":
        # Tabelle 8.5, Detail 5/6: Ende eines Deckblechs (t = Deckblechdicke)
        t = n.t or 0.0
        if n.bearbeitet and t <= 20.0:
            ds, detail = 71.0, "Tab. 8.5, Detail 6 (Deckblech-Ende mit bearbeiteter Stirnnaht)"
        else:
            ds = _nach_laenge(t, [(20, 56.0), (30, 50.0), (50, 45.0), (None, 40.0)])
            detail = "Tab. 8.5, Detail 5 (Deckblech-Ende, t = " + f"{t:g} mm)"
        dt = 80.0
    else:
        raise ValueError(f"Nahtart „{art}“ unbekannt - eine von {', '.join(NAHTARTEN)}")
    k_s = groesseneinfluss(n.t) if groesse else 1.0
    out = {"dsC": ds, "dtC": dt, "k_s": k_s, "dsC_wirksam": ds * k_s, "detail": detail,
           "hinweis": hinweis, "wurzel": wurzel, "vorgabe": False}
    if n.kerbfall_vorgabe:
        out.update({"dsC": float(n.kerbfall_vorgabe), "dsC_wirksam": float(n.kerbfall_vorgabe),
                    "k_s": 1.0, "vorgabe": True, "detail": detail + " - Vorgabe"})
    if n.kerbfall_schub_vorgabe:
        out["dtC"] = float(n.kerbfall_schub_vorgabe)
    return out


# ==========================================================================
# Zuordnung zu den Stäben
# ==========================================================================
def naehte_fuer_stab(model, stab: str) -> list:
    """Alle Nähte, die den Stab betreffen: genannt oder äquivalent für alle."""
    out = []
    for n in (getattr(model, "schweissnaehte", {}) or {}).values():
        if stab in n.staebe or (n.aequivalent and not n.staebe and not n.linien and not n.flaechen):
            out.append(n)
    return out


def kerbfaelle_je_stab(model) -> dict:
    """{Stab: {"dsC": Pa, "dtC": Pa, "naht": Name, "detail": …}} - der ungünstigste
    Kerbfall aller Nähte je Stab. Stäbe ohne Naht fehlen."""
    out = {}
    for name in (model.members or {}):
        best = None
        for n in naehte_fuer_stab(model, name):
            kf = kerbfall(n)
            if best is None or kf["dsC_wirksam"] < best[0]["dsC_wirksam"] - 1e-9:
                best = (kf, n)
            elif best is not None and abs(kf["dsC_wirksam"] - best[0]["dsC_wirksam"]) <= 1e-9 \
                    and kf["dtC"] < best[0]["dtC"]:
                best = (kf, n)
        if best is not None:
            kf, n = best
            dt = min(kerbfall(x)["dtC"] for x in naehte_fuer_stab(model, name))
            out[name] = {"dsC": kf["dsC_wirksam"] * 1e6, "dtC": dt * 1e6, "naht": n.name,
                         "detail": kf["detail"], "k_s": kf["k_s"], "aequivalent": n.aequivalent}
    return out


def kerbfaelle_uebernehmen(model, log: list = None) -> list:
    """Die Kerbfälle aus den Nähten in die Stäbe schreiben (detail_category,
    detail_category_shear). Stäbe ohne Naht behalten ihre Angabe.
    Rückgabe: die Stäbe, deren Kerbfall sich geändert hat."""
    geaendert = []
    for name, kf in kerbfaelle_je_stab(model).items():
        mem = model.members[name]
        alt = (mem.detail_category, mem.detail_category_shear)
        mem.detail_category = float(kf["dsC"])
        mem.detail_category_shear = float(kf["dtC"])
        if alt != (mem.detail_category, mem.detail_category_shear):
            geaendert.append(name)
            if log is not None:
                log.append(f"Stab {name}: Kerbfall {kf['dsC'] / 1e6:.0f} / Δτ {kf['dtC'] / 1e6:.0f} "
                           f"aus Naht {kf['naht']} ({kf['detail']})")
    return geaendert


def kerbfall_fuer_flaechen(model, flaechen, linien=None) -> Optional[float]:
    """Der ungünstigste Kerbfall [MPa] der Nähte an den genannten Flächen bzw.
    Linien (oder einer äquivalenten Naht ohne Zuordnung) - None, wenn keine."""
    flaechen = set(flaechen or [])
    linien = set(linien or [])
    werte = []
    for n in (getattr(model, "schweissnaehte", {}) or {}).values():
        passt = bool(flaechen & set(n.flaechen)) or bool(linien & set(n.linien)) \
            or (n.aequivalent and not n.staebe and not n.linien and not n.flaechen)
        if passt:
            werte.append(kerbfall(n)["dsC_wirksam"])
    return min(werte) if werte else None


def tabelle(model) -> list:
    """Zeilen (mit Kopf) für Bericht und Tabelle."""
    kopf = ["Naht", "Nahtart", "Lage", "a [mm]", "t [mm]", "ℓ [mm]", "Ausführung", "Merkmale",
            "gilt für", "Δσ_C [MPa]", "k_s", "Δτ_C [MPa]", "Fundstelle EN 1993-1-9"]
    rows = [kopf]
    for name, n in (getattr(model, "schweissnaehte", {}) or {}).items():
        kf = kerbfall(n)
        merk = [w for w, ok in (("bearbeitet", n.bearbeitet), ("geprüft", n.geprueft),
                                ("einseitig", n.einseitig), ("Gegenlage", n.gegenlage),
                                ("unterbrochen", n.unterbrochen), ("Freischnitt", n.freischnitt),
                                ("äquivalent", n.aequivalent)) if ok]
        ziele = n.staebe + n.linien + n.flaechen
        rows.append([name, n.art, n.lage, f"{n.a:g}" if n.a and n.art in KEHLNAEHTE else "–",
                     f"{n.t:g}" if n.t else "–", f"{n.l_anschluss:g}" if n.l_anschluss else "–",
                     n.ausfuehrung, ", ".join(merk) or "–",
                     ", ".join(ziele) if ziele else ("alle Stäbe" if n.aequivalent else "–"),
                     f"{kf['dsC_wirksam']:.0f}" + (f" ({kf['dsC']:.0f}·k_s)" if kf["k_s"] < 1 else ""),
                     f"{kf['k_s']:.3f}", f"{kf['dtC']:.0f}", kf["detail"]])
    return rows


def erlaeuterung(n: Schweissnaht, kf: dict = None) -> list:
    kf = kf or kerbfall(n)
    z = [f"Naht {n.name}: {n.art}, {n.lage} zur Beanspruchung, {n.ausfuehrung}"
         + (", blecheben bearbeitet" if n.bearbeitet else "") + (", geprüft" if n.geprueft else "")
         + (", einseitig" + (" mit Gegenlage" if n.gegenlage else "") if n.einseitig else "")
         + (", unterbrochen" if n.unterbrochen else "") + (", mit Freischnitten" if n.freischnitt else "") + ".",
         f"Kerbfall Δσ_C = {kf['dsC']:.0f} N/mm² ({kf['detail']})"
         + (f", Größeneinfluss k_s = (25/{n.t:g})^0,2 = {kf['k_s']:.3f} → {kf['dsC_wirksam']:.0f} N/mm²"
            if kf["k_s"] < 1 else "") + f"; Schub Δτ_C = {kf['dtC']:.0f} N/mm²."]
    if kf.get("hinweis"):
        z.append(kf["hinweis"] + ".")
    if n.aequivalent:
        z.append("Äquivalente Naht: steht stellvertretend für die nicht einzeln modellierten "
                 "Nähte" + (" der genannten Stäbe" if n.staebe else " aller Stäbe")
                 + "; ungünstigere Einzelnähte gehen vor.")
    return z
