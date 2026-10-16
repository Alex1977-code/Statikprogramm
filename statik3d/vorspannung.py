"""Vorspannung je Anker: Definitionen, Verweise der Lastfaelle, Zuordnung (16.10.2026).

Vom Anwender freigegebener Entwurf (woertlich):

  „Vorspannung künftig einmal je Anker definieren (Pressenkraft, Schlupf),
  Lastfälle verweisen nur darauf. Nachweis beim Spannen (σ_p,max) zur
  Vorspannungsdefinition, nicht als Maximum über Lastfälle.“

  „Zustände 0 und ∞ plus P_max beim Spannen reichen. Sofortige Verluste
  rechnet das Programm (elastische Verkürzung, Verankerungsschlupf → P_0).
  Zeitabhängige Verluste sind Eingabe, wahlweise P_∞ absolut oder Verlust
  ΔP_t, Anzeige beider Werte. Der Import übernimmt 805 kN absolut. […]“

  „Nachweise nach Zustand: Spannen gegen σ_p,max mit P_max. Nach Verankern
  (0,85·f_p0,1k) und GZT gegen f_pd mit t = 0. Klaffen und Gleiten der Fuge,
  Passstifte und Ermüdung der Anker mit t = ∞. Obere/untere Werte nach
  EN 1992-1-1, 5.10.9 (r_sup/r_inf) als späteres Merkmal vormerken.“

**Rechnung.** Ein Verweis wird erst beim Rechnen in die Lastarten uebersetzt,
die es schon gibt (statik3d.vorspannkraft), und zwar je Anker der Definition:

* Zeitpunkt 0 - Anfangsvorspannung mit der Pressenkraft P_max, dem Schlupf Δs
  und der Spanngruppe der Definition. Der Spannschritt rechnet daraus P₀ nach
  dem Verankern (Schlupf, Rueckfedern der Umgebung, elastische Verkuerzung der
  frueher gespannten Gruppen).
* Zeitpunkt ∞ - Endvorspannung F_soll = P_∞, alle Anker in einer Gruppe: so
  traegt nach dem Verriegeln jeder Anker genau P_∞ (mit Spannfolge verloeren
  die frueheren wieder Kraft, und P_∞ waere nicht mehr der eingegebene Wert).
  Ist der Verlust ΔP_t eingegeben, gilt je Anker P_∞,i = P₀,i − ΔP_t. P₀,i ist
  der Zustand 0 **aller** Definitionen des Modells (so wird gespannt), am
  selben System gerechnet und dort gemerkt - unabhaengig davon, ob und in
  welcher Reihenfolge ein Lastfall im Zustand 0 gerechnet wird (Vorgabe von
  „main“ vom 16.10.2026; tests/test_vorspannung_je_anker.py: ∞ allein, 0 dann
  ∞, ∞ dann 0 geben dieselben Bits).

Beide Lastarten sind Sollkraefte; der Lastvektor des Lastfalls uebergeht sie
(assemble.element_equivalent_loads), nur vorspannkraft.sollkraefte liest sie.
Ein Lastfall ohne Verweis rechnet darum Bit fuer Bit wie bisher, und die
bisherigen Vorspannungslasten (Endvorspannung, Anfangsvorspannung, ΔT) bleiben
lesbar und rechnen wie zuvor.

**Zuordnung.** :func:`gruppen_finden` fasst die Vorspannungen an denselben
Staeben nach Wert zu Gruppen (am Drehlager 952 kN als ΔT in 128 Lastfaellen,
805 kN als ΔT in 293, 944,7 kN Endvorspannung in LF1) und nennt je Gruppe die
Kraft nach elastischer Verkuerzung. :func:`zuordnen` stellt erst auf
Anweisung des Anwenders um; ohne Zuordnung bleibt alles, wie es ist.
"""
from __future__ import annotations

import numpy as np

from .model import (VORSPANN_ALLE, VORSPANN_ENDWERT_ABSOLUT, VORSPANN_ENDWERT_VERLUST,
                    VORSPANN_PRESSE, VORSPANN_ZUSTAENDE, VORSPANN_ZUSTAND_0, VORSPANN_ZUSTAND_INF,
                    VorspannDefinition, Vorspannung)

#: Namen der Zustaende fuer den Anwender
ZUSTAND_TEXT = {VORSPANN_ZUSTAND_0: "Zeitpunkt 0", VORSPANN_ZUSTAND_INF: "Zeitpunkt ∞"}
#: kurz, in Nachweiszeilen
ZUSTAND_KURZ = {VORSPANN_ZUSTAND_0: "t = 0", VORSPANN_ZUSTAND_INF: "t = ∞"}
KEINE = "keine"
ENDWERT_TEXT = {VORSPANN_ENDWERT_ABSOLUT: "P_∞ absolut", VORSPANN_ENDWERT_VERLUST: "Verlust ΔP_t"}

#: Mit welchem Zustand der Vorspannung ein Nachweis zu fuehren ist (Entwurf des
#: Anwenders vom 16.10.2026). "P_max": Spannen mit der Pressenkraft. Wo es den
#: Nachweis im Programm (noch) nicht gibt, steht er hier trotzdem: Bericht und
#: Ergebnisanzeige nennen den Zustand, und ein kuenftiger Nachweis liest ihn hier.
NACHWEIS_ZUSTAND = {
    "spannen": ("Spannen (σ_p,max)", "P_max"),
    "verankert": ("nach dem Verankern (σ_pm0)", VORSPANN_ZUSTAND_0),
    "gzt": ("Spannstahl im GZT (f_pd)", VORSPANN_ZUSTAND_0),
    "fuge_klaffen": ("Klaffen der Fuge", VORSPANN_ZUSTAND_INF),
    "fuge_gleiten": ("Gleiten der Fuge", VORSPANN_ZUSTAND_INF),
    "passstifte": ("Passstifte (Bolzennachweis 3.13, vorgemerkt)", VORSPANN_ZUSTAND_INF),
    "ermuedung_anker": ("Ermüdung der Anker", VORSPANN_ZUSTAND_INF),
}
#: Nachweise, die es im Programm noch nicht gibt - nur die Zustandsangabe ist vorbereitet
NACHWEIS_NOCH_NICHT = ("fuge_klaffen", "fuge_gleiten", "passstifte")

#: Vermerk an Definitionen aus einer Zuordnung von RFEM-Werten
VERMERK_RFEM = "aus RFEM übernommen – prüfen"


# --------------------------------------------------------------------------
# Definitionen und Verweise
# --------------------------------------------------------------------------
def definitionen(model) -> dict:
    return getattr(model, "vorspann_definitionen", None) or {}


def verwiesene_definitionen(model, zustand: dict) -> list:
    """Die Namen der Definitionen, auf die ``zustand`` ({Definition oder
    VORSPANN_ALLE: Zustand}) verweist - „alle“ aufgeloest."""
    defs = definitionen(model)
    out = []
    for k in (zustand or {}):
        for n in (list(defs) if k == VORSPANN_ALLE else [k]):
            if n in defs and n not in out:
                out.append(n)
    return out


def verweise(model, lc) -> list:
    """[(Definition, Zustand)] eines Lastfalls; ein Eintrag zu einer Definition
    geht dem fuer „alle“ vor. Unbekannte Definitionen und Zustaende fallen weg
    (die Modellpruefung nennt sie: :func:`pruefen`)."""
    vz = getattr(lc, "vorspannzustand", None) or {}
    if not vz:
        return []
    defs = definitionen(model)
    out = []
    alle = vz.get(VORSPANN_ALLE)
    for name, d in defs.items():
        z = vz.get(name, alle)
        if z in VORSPANN_ZUSTAENDE:
            out.append((d, z))
    return out


def _anker(model, d: VorspannDefinition) -> list:
    return [s for s in (d.staebe or []) if s in (getattr(model, "members", None) or {})]


def vorspannungen_zustand(model, d: VorspannDefinition, zustand: str) -> list:
    """Die Lasten, in die ein Verweis beim Rechnen uebersetzt wird (siehe
    Moduldoku). Die Objekte tragen ``_verweis`` = (Definition, Zustand); bei
    ΔP_t steht in ``kraft`` −ΔP_t und ``_p0_aus_zustand0`` ist gesetzt: der
    Rechner zaehlt P₀,i dazu (vorspannkraft.rechnen)."""
    out = []
    for s in _anker(model, d):
        if zustand == VORSPANN_ZUSTAND_0:
            v = Vorspannung(s, "stab", float(d.P_max), None, "", True, int(d.gruppe or 1),
                            VORSPANN_PRESSE, float(d.schlupf or 0.0))
        elif zustand == VORSPANN_ZUSTAND_INF and d.ist_verlust():
            v = Vorspannung(s, "stab", -float(d.dP_t or 0.0), None, "", True, 1)
            v._p0_aus_zustand0 = True
        elif zustand == VORSPANN_ZUSTAND_INF:
            v = Vorspannung(s, "stab", float(d.P_inf), None, "", True, 1)
        else:
            continue
        v._verweis = (d.name, zustand)
        out.append(v)
    return out


def verweis_vorspannungen(model, lc) -> list:
    """Alle Lasten aus den Verweisen des Lastfalls (leer ohne Verweis)."""
    if not getattr(lc, "vorspannzustand", None):
        return []
    out = []
    for d, z in verweise(model, lc):
        out += vorspannungen_zustand(model, d, z)
    return out


def zustand0_alle(model) -> list:
    """Die Lasten des Zustands 0 aller Definitionen - der Spannvorgang, aus
    dem P₀,i fuer ΔP_t kommt."""
    out = []
    for d in definitionen(model).values():
        out += vorspannungen_zustand(model, d, VORSPANN_ZUSTAND_0)
    return out


def wirksame_vorspannungen(model, lc) -> list:
    """Die Vorspannungen eines Lastfalls: die eingegebenen und die aus Verweisen."""
    return list(getattr(lc, "vorspannungen", None) or []) + verweis_vorspannungen(model, lc)


def zustaende_der_faktoren(model, faktoren) -> dict:
    """{Definition: {Zustaende}} der Lastfaelle mit Faktor ≠ 0 - leer, wenn
    keiner verweist. Ein Name einer Kombination oder Umhuellenden („LK3
    [max]“) wird ueber ihre Faktoren aufgeloest."""
    out: dict = {}
    lcs = getattr(model, "load_cases", None) or {}
    for name, f in (faktoren or {}).items():
        lc = lcs.get(name)
        if lc is None or not f:
            continue
        for d, z in verweise(model, lc):
            out.setdefault(d.name, set()).add(z)
    return out


def faktoren_von(model, name: str) -> dict:
    """Die Lastfaelle eines Ergebnisnamens: ein Lastfall {Name: 1}, eine
    Kombination ihre Faktoren, sonst leer."""
    lcs = getattr(model, "load_cases", None) or {}
    if name in lcs:
        return {name: 1.0}
    c = (getattr(model, "combinations", None) or {}).get(str(name).split(" [")[0])
    return dict(getattr(c, "factors", None) or {})


def zustand_von(model, name: str) -> set:
    """Die Zustaende (aus Verweisen) eines Ergebnisses: Lastfall oder Kombination."""
    out = set()
    for zs in zustaende_der_faktoren(model, faktoren_von(model, name)).values():
        out |= zs
    return out


def zustand_kurz(zustaende) -> str:
    """„t = 0“, „t = ∞“, „t = 0 und t = ∞ gemischt“ oder leer."""
    zs = [z for z in VORSPANN_ZUSTAENDE if z in set(zustaende or ())]
    if not zs:
        return ""
    if len(zs) == 2:
        return "t = 0 und t = ∞ gemischt"
    return ZUSTAND_KURZ[zs[0]]


def zustand_lastfall_text(model, lc) -> str:
    """Der Zustand je Lastfall zum Lesen: „Zeitpunkt 0 (V1)“, „keine“."""
    vz = getattr(lc, "vorspannzustand", None) or {}
    if not vz:
        return KEINE
    teile = []
    for k, z in vz.items():
        wer = "alle Definitionen" if k == VORSPANN_ALLE else k
        teile.append(f"{ZUSTAND_TEXT.get(z, z)} ({wer})")
    return ", ".join(teile)


def lastfaelle_je_zustand(model, d: VorspannDefinition) -> dict:
    """{Zustand: [Lastfaelle]} der Verweise auf ``d``."""
    out = {z: [] for z in VORSPANN_ZUSTAENDE}
    for name, lc in (getattr(model, "load_cases", None) or {}).items():
        for dd, z in verweise(model, lc):
            if dd.name == d.name:
                out[z].append(name)
    return out


def gemischt_hinweis(model, faktoren) -> str:
    """Ein Hinweis, wenn eine Rechnung dieselbe Definition zu beiden Zeitpunkten
    traegt (eine Kombination aus Lastfaellen im Zustand 0 und ∞): die Kraefte
    zaehlen dann zusammen, das ist kein Zustand des Ankers."""
    zs = zustaende_der_faktoren(model, faktoren)
    beide = sorted(n for n, z in zs.items() if len(z) > 1)
    if not beide:
        return ""
    return (f"Vorspannung {', '.join(beide)} zugleich im Zeitpunkt 0 und ∞ – die Kräfte zählen zusammen; "
            "eine Kombination sollte nur Lastfälle eines Zeitpunkts enthalten")


def pruefen(model) -> list:
    """Zeilen fuer die Modellpruefung: Verweise auf unbekannte Definitionen,
    Definitionen ohne Anker oder ohne die Werte ihres Zustands."""
    out = []
    defs = definitionen(model)
    for name, lc in (getattr(model, "load_cases", None) or {}).items():
        for k, z in (getattr(lc, "vorspannzustand", None) or {}).items():
            if k != VORSPANN_ALLE and k not in defs:
                out.append(f"Lastfall {name}: Vorspannung „{k}“ gibt es nicht – der Verweis wirkt nicht")
            if z not in VORSPANN_ZUSTAENDE:
                out.append(f"Lastfall {name}: Zustand „{z}“ der Vorspannung unbekannt (0 oder ∞)")
    for d in defs.values():
        fehlt = [s for s in d.staebe or [] if s not in (getattr(model, "members", None) or {})]
        if fehlt:
            out.append(f"Vorspannung {d.name}: Stab {', '.join(fehlt[:4])} gibt es nicht")
        if not _anker(model, d):
            out.append(f"Vorspannung {d.name}: keine Anker")
        faelle = lastfaelle_je_zustand(model, d)
        if (faelle[VORSPANN_ZUSTAND_0] or d.ist_verlust()) and not d.P_max > 0:
            out.append(f"Vorspannung {d.name}: P_max fehlt (Zeitpunkt 0"
                       + (" und ΔP_t brauchen" if d.ist_verlust() else " braucht") + " die Pressenkraft)")
        if faelle[VORSPANN_ZUSTAND_INF] and not d.ist_verlust() and not d.P_inf > 0:
            out.append(f"Vorspannung {d.name}: P_∞ fehlt (Zeitpunkt ∞)")
    return out


# --------------------------------------------------------------------------
# P₀ und Anzeige
# --------------------------------------------------------------------------
def p0_starr(model, d: VorspannDefinition) -> dict:
    """{Anker: P_max − k_A·Δs} - P₀ gegen starre Umgebung, ohne Rueckfedern und
    ohne elastische Verkuerzung (Schaetzung vor der Rechnung)."""
    from .vorspannkraft import _elemente, k_stab
    out = {}
    for s in _anker(model, d):
        k = k_stab(model, _elemente(model, s)) if d.schlupf else 0.0
        out[s] = float(d.P_max) - k * float(d.schlupf or 0.0)
    return out


def p0_aus_ergebnissen(model, d: VorspannDefinition, ergebnisse: dict) -> tuple:
    """({Anker: P₀}, Herkunft) aus gerechneten Ergebnissen: N_verankert eines
    Lastfalls im Zeitpunkt 0, sonst P₀,i, mit dem ein Lastfall im Zeitpunkt ∞
    mit ΔP_t gerechnet hat. ({}, "") ohne solches Ergebnis."""
    faelle = lastfaelle_je_zustand(model, d)
    for zustand, schluessel in ((VORSPANN_ZUSTAND_0, "N_verankert"), (VORSPANN_ZUSTAND_INF, "P0_basis")):
        for fall in faelle[zustand]:
            res = (ergebnisse or {}).get(fall)
            st = (((getattr(res, "info", None) or {}).get("vorspannung") or {}).get("staebe") or {})
            werte = {s: float(st[s][schluessel]) for s in _anker(model, d)
                     if isinstance(st.get(s), dict) and st[s].get(schluessel) is not None}
            if werte and len(werte) == len(_anker(model, d)):
                return werte, f"aus dem Ergebnis {fall}"
    return {}, ""


def _kn(x) -> str:
    """Kraft [N] in kN mit einer Nachkommastelle zum Lesen („944,7“)."""
    from .zahlen import zahl_text
    return zahl_text(round(float(x) / 1e3, 1))


def _spanne_kn(werte) -> str:
    w = [float(x) for x in werte]
    if not w:
        return "–"
    lo, hi = _kn(min(w)), _kn(max(w))
    return f"{lo} kN" if lo == hi else f"{lo} bis {hi} kN"


def anzeige(model, d: VorspannDefinition, ergebnisse: dict = None) -> dict:
    """Die Werte einer Definition zum Lesen (Maske, Modellbaum, Bericht,
    Ergebnisse): P_max, P₀ (berechnet oder geschaetzt, mit Herkunft), P_∞ und
    ΔP_t - beide, der eingegebene und der daraus folgende (Entwurf: „Anzeige
    beider Werte“)."""
    p0, her = p0_aus_ergebnissen(model, d, ergebnisse or {})
    geschaetzt = not p0
    if geschaetzt:
        p0 = p0_starr(model, d)
        her = ("vor der Rechnung geschätzt: P_max − k_A·Δs gegen starre Umgebung, ohne Rückfedern und "
               "elastische Verkürzung – gerechnet wird P₀ im Spannschritt")
    if d.ist_verlust():
        p_inf = {s: x - float(d.dP_t or 0.0) for s, x in p0.items()}
        dp = {s: float(d.dP_t or 0.0) for s in p0}
        t_inf = f"P_∞ = P₀ − ΔP_t = {_spanne_kn(p_inf.values())} (folgt)"
        t_dp = f"ΔP_t = {_kn(float(d.dP_t or 0.0))} kN (Eingabe)"
    else:
        p_inf = {s: float(d.P_inf) for s in p0}
        dp = {s: x - float(d.P_inf) for s, x in p0.items()}
        t_inf = f"P_∞ = {_kn(float(d.P_inf))} kN (Eingabe, absolut)"
        t_dp = f"ΔP_t = P₀ − P_∞ = {_spanne_kn(dp.values())} (folgt)"
        if dp and min(dp.values()) < 0.0:
            # kein stilles Umstellen: der Anwender entscheidet den Sollwert
            t_dp += " – P_∞ liegt über P₀, der Verlust wäre negativ: P_∞ prüfen"
    faelle = lastfaelle_je_zustand(model, d)
    return {"P_max": float(d.P_max), "P0": p0, "P0_herkunft": her, "P0_geschaetzt": geschaetzt,
            "P_inf": p_inf, "dP_t": dp, "text_P_max": f"P_max = {_kn(float(d.P_max))} kN",
            "text_P0": f"P₀ = {_spanne_kn(p0.values())} ({her})", "text_P_inf": t_inf, "text_dP_t": t_dp,
            "faelle": faelle}


def anker_text(staebe) -> str:
    from .importers.schraubenhinweis import _bereiche
    return _bereiche(list(staebe or []))


def definition_zeile(model, d: VorspannDefinition, ergebnisse: dict = None) -> str:
    """Eine Zeile je Definition (Protokoll, Ergebnisse, Modellbaum-Hinweis)."""
    from .zahlen import zahl_text
    a = anzeige(model, d, ergebnisse)
    n0, ninf = len(a["faelle"][VORSPANN_ZUSTAND_0]), len(a["faelle"][VORSPANN_ZUSTAND_INF])
    return (f"Vorspannung {d.name} an {anker_text(d.staebe)} (Spanngruppe {int(d.gruppe or 1)}): "
            f"{a['text_P_max']}, Δs = {zahl_text(round(float(d.schlupf or 0.0) * 1e3, 2))} mm"
            f"; {a['text_P0']}; {a['text_P_inf']}; {a['text_dP_t']}; "
            f"Zeitpunkt 0 in {n0}, Zeitpunkt ∞ in {ninf} Lastfällen"
            + (f" – {d.herkunft}" if d.herkunft else ""))


def ergebnis_zeilen(model, ergebnisse: dict = None) -> list:
    """Zeilen fuer Protokoll und Maske Ergebnisse: je Definition und, was je
    Nachweis an Zustand gilt."""
    defs = definitionen(model)
    if not defs:
        return []
    out = [definition_zeile(model, d, ergebnisse) for d in defs.values()]
    out.append("Zustand der Vorspannung je Nachweis: " + "; ".join(
        f"{t} mit {('P_max' if z == 'P_max' else ZUSTAND_KURZ[z])}"
        + (" (Nachweis noch nicht im Programm)" if k in NACHWEIS_NOCH_NICHT else "")
        for k, (t, z) in NACHWEIS_ZUSTAND.items()))
    return out


# --------------------------------------------------------------------------
# Zuordnung bei Import und alten Dateien
# --------------------------------------------------------------------------
ART_DT = "eingeprägte Dehnung als ΔT (RFEM)"
ART_DEHNUNG = "eingeprägte Dehnung F_v"
ART_ENDE = "Endvorspannung"
ART_PRESSE = "Anfangsvorspannung (Pressenkraft)"


def _art_vorspannung(v) -> str:
    if callable(getattr(v, "ist_presse", None)) and v.ist_presse():
        return ART_PRESSE
    return ART_ENDE if getattr(v, "sollkraft", False) else ART_DEHNUNG


def gruppen_finden(model, ergebnisse: dict = None, linear_rechnen: bool = False) -> list:
    """Die Vorspannungen an Staeben, nach Art, Wert und Staben zu Gruppen
    gefasst: [{"schluessel", "art", "N0" [N], "schlupf" [m], "staebe", "faelle",
    "kategorien" {Kategorie: Zahl}, "X" [min, max] | None, "X_herkunft"}].
    X ist die Kraft, die nach elastischer Verkuerzung wirkt - aus dem
    Importhinweis, aus einem Ergebnis eines Lastfalls nur mit dieser
    Vorspannung, bei der Endvorspannung F_soll selbst; mit ``linear_rechnen``
    linear ueber die Einflussmatrix, wenn das Modell es zulaesst."""
    from .vorspannkraft import _nur_vorspannung, _elemente, _n_ergebnis, _rfem_hinweise, \
        temperatur_vorspannungen, x_rechenbar
    lcs = getattr(model, "load_cases", None) or {}
    gruppen: dict = {}
    # Anker nach Name und Nummer (S1, S2, …, S10): nicht nach Text (S1, S10, S2)
    # und nicht in der Folge im Modell (am Drehlager aus RFEM S4, S3, S8, …)
    import re

    def schluessel(n):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(n))]

    def sortiert(staebe):
        return tuple(sorted(set(staebe), key=schluessel))

    def eintrag(key, art, N0, schlupf, stab_liste, fall):
        g = gruppen.setdefault(key, {"schluessel": key, "art": art, "N0": float(N0), "schlupf": float(schlupf),
                                     "staebe": list(stab_liste), "faelle": [], "kategorien": {},
                                     "X": None, "X_herkunft": ""})
        g["faelle"].append(fall)
        kat = str(getattr(lcs.get(fall), "category", "") or "?")
        g["kategorien"][kat] = g["kategorien"].get(kat, 0) + 1
    je_fall: dict = {}
    for t in temperatur_vorspannungen(model):
        je_fall.setdefault(t.fall, {}).setdefault(round(t.N0, 3), []).append(t.stab)
    for fall in lcs:
        for N0, staebe in (je_fall.get(fall) or {}).items():
            st = sortiert(staebe)
            eintrag(("dT", N0, 0.0, st), ART_DT, N0, 0.0, st, fall)
        je: dict = {}
        for v in getattr(lcs[fall], "vorspannungen", None) or []:
            if getattr(v, "art", "stab") != "stab" or not v.kraft:
                continue
            k = (_art_vorspannung(v), round(float(v.kraft), 3), round(float(v.schlupf or 0.0), 9))
            je.setdefault(k, []).append(v.ziel)
        for (art, N0, ds), staebe in je.items():
            st = sortiert(staebe)
            eintrag(("kraft", art, N0, ds, st), art, N0, ds, st, fall)
    out = sorted(gruppen.values(), key=lambda g: (-len(g["faelle"]), -g["N0"]))
    # X: Importhinweis, Ergebnis, Endvorspannung, linear
    hinweise = [h for h in _rfem_hinweise(model) if h.get("X")]
    for g in out:
        if g["art"] == ART_ENDE:
            g["X"], g["X_herkunft"] = [g["N0"], g["N0"]], "Endvorspannung: der Spannschritt trifft F_soll"
            continue
        h = next((h for h in hinweise if g["art"] == ART_DT
                  and abs(float(h.get("N0", 0.0)) - g["N0"]) <= 1e-6 * max(g["N0"], 1.0)), None)
        if h is not None:
            g["X"] = [float(min(h["X"])), float(max(h["X"]))]
            aus = list(h.get("X_aus") or [])
            g["X_herkunft"] = ("aus dem Ergebnis " + ", ".join(aus[:3])) if aus else "linear beim Import gerechnet"
            continue
        xs, aus = [], []
        for fall in g["faelle"]:
            res = (ergebnisse or {}).get(fall)
            lc = lcs.get(fall)
            if res is None or lc is None or not getattr(res, "beam_end", None):
                continue
            if g["art"] == ART_DT and not _nur_vorspannung(model, lc):
                continue
            if g["art"] != ART_DT and (lc.temp_loads or lc.nodal_loads or lc.beam_loads or any(lc.gravity or [])):
                continue
            for s in g["staebe"]:
                els = _elemente(model, s)
                if els and all(i in res.beam_end for i in els):
                    xs.append(_n_ergebnis(res, els))
            aus.append(fall)
        if xs:
            g["X"], g["X_herkunft"] = [min(xs), max(xs)], "aus dem Ergebnis " + ", ".join(aus[:3])
            continue
        grund = x_rechenbar(model)
        if linear_rechnen and not grund and g["art"] in (ART_DT, ART_DEHNUNG):
            try:
                X = _linear_x(model, g)
                g["X"], g["X_herkunft"] = [min(X), max(X)], "linear gerechnet (Einflussmatrix)"
                continue
            except Exception as ex:          # noqa: BLE001 - die Zeile kommt trotzdem
                grund = f"lineare Rechnung nicht möglich ({type(ex).__name__})"
        if g["art"] == ART_PRESSE:
            g["X_herkunft"] = "folgt aus dem Spannschritt (P₀ nach Schlupf und elastischer Verkürzung)"
        else:
            g["X_herkunft"] = ("folgt nach der ersten Rechnung eines Lastfalls nur mit dieser Vorspannung"
                               + (f": {grund}" if grund else ""))
    return out


def _linear_x(model, g) -> list:
    from . import solver as sv
    from .vorspannkraft import einflussmatrix
    system = sv.StaticSystem(model)
    A = einflussmatrix(model, system, list(g["staebe"]))
    return [float(x) for x in A @ np.full(len(g["staebe"]), float(g["N0"]))]


def gruppe_text(g: dict) -> str:
    kat = ", ".join(f"{k} {n}" for k, n in sorted(g["kategorien"].items()))
    return (f"{_kn(g['N0'])} kN {g['art']} an {anker_text(g['staebe'])} in "
            f"{len(g['faelle'])} {'Lastfall' if len(g['faelle']) == 1 else 'Lastfällen'} ({kat})")


def x_text(g: dict) -> str:
    if g.get("X"):
        return f"{_spanne_kn(g['X'])} ({g['X_herkunft']})"
    return g.get("X_herkunft", "")


def zuordnen(model, eintraege: list) -> dict:
    """Die Gruppen aus :func:`gruppen_finden` den Zustaenden und Definitionen
    zuordnen - nur auf Anweisung des Anwenders (Zuordnungsdialog).

    ``eintraege``: [{"gruppe": Gruppe (aus gruppen_finden), "zustand": "0" |
    "inf" | "" (bleibt), "definition": Name, "P_max", "schlupf", "spanngruppe",
    "endwert", "P_inf", "dP_t"}] - Kraefte in N, Schlupf in m. Zeitpunkt 0 setzt
    P_max, Δs und die Spanngruppe der Definition, Zeitpunkt ∞ ihren Endwert.
    Danach verweist jeder Lastfall der Gruppe auf die Definition, und die
    Vorspannungslasten der Gruppe fallen dort weg; alle anderen Lasten bleiben.
    Rueckgabe {"definitionen": [...], "faelle": Zahl, "je_gruppe": [...]}.
    Fehler in der Eingabe: ValueError, bevor etwas geaendert ist
    (:func:`zuordnung_pruefen`)."""
    from .vorspannkraft import temperatur_vorspannungen
    defs = definitionen(model)
    plan = zuordnung_pruefen(model, eintraege)
    # ab hier wird geaendert
    je_gruppe = []
    n_faelle = 0
    for name, p in plan.items():
        d = defs.get(name)
        if d is None:
            d = VorspannDefinition(name, list(p["staebe"]))
            model.vorspann_definitionen[name] = d
        e0, ei = p["0"], p["inf"]
        if e0:
            d.P_max = float(e0.get("P_max") or 0.0)
            d.schlupf = max(0.0, float(e0.get("schlupf") or 0.0))
            d.gruppe = max(1, int(e0.get("spanngruppe") or 1))
        if ei:
            d.endwert = str(ei.get("endwert") or VORSPANN_ENDWERT_ABSOLUT)
            if d.endwert == VORSPANN_ENDWERT_VERLUST:
                d.dP_t = float(ei.get("dP_t") or 0.0)
            else:
                d.P_inf = float(ei.get("P_inf") or 0.0)
        if p["rfem"] and not d.herkunft:
            d.herkunft = VERMERK_RFEM
        for g, z in p["gruppen"]:
            staebe = set(g["staebe"])
            for fall in g["faelle"]:
                lc = model.load_cases[fall]
                if g["art"] == ART_DT:
                    weg = {id(x) for t in temperatur_vorspannungen(model, [fall], sorted(staebe))
                           if abs(t.N0 - g["N0"]) <= 1e-6 * max(g["N0"], 1.0) for x in t.lasten}
                    lc.temp_loads = [x for x in lc.temp_loads if id(x) not in weg]
                else:
                    lc.vorspannungen = [
                        v for v in lc.vorspannungen
                        if not (getattr(v, "art", "stab") == "stab" and v.ziel in staebe
                                and _art_vorspannung(v) == g["art"]
                                and abs(float(v.kraft) - g["N0"]) <= 1e-6 * max(g["N0"], 1.0))]
                lc.vorspannzustand = dict(getattr(lc, "vorspannzustand", None) or {})
                lc.vorspannzustand[name] = z
                n_faelle += 1
            je_gruppe.append({"gruppe": gruppe_text(g), "zustand": z, "definition": name,
                              "faelle": len(g["faelle"])})
    if plan:
        rest = {round(t.N0, 3) for t in temperatur_vorspannungen(model)}
        for h in (getattr(model, "importhinweise", None) or []):
            if h.get("art") == "vorspannung" and round(float(h.get("N0", 0.0)), 3) not in rest:
                h["erledigt"] = True
    return {"definitionen": list(plan), "faelle": n_faelle, "je_gruppe": je_gruppe}


def zuordnung_pruefen(model, eintraege: list) -> dict:
    """Die Eintraege einer Zuordnung pruefen, ohne etwas zu aendern; Rueckgabe
    der Plan je Definition, Fehler als ValueError (der Dialog prueft so vor dem
    Schliessen, ohne das Modell zu kopieren)."""
    defs = definitionen(model)
    plan: dict = {}
    for e in eintraege or []:
        z = str(e.get("zustand") or "")
        if z not in VORSPANN_ZUSTAENDE:
            continue
        g = e["gruppe"]
        name = str(e.get("definition") or "").strip()
        if not name:
            raise ValueError(f"{gruppe_text(g)}: keine Definition genannt")
        p = plan.setdefault(name, {"staebe": None, "0": None, "inf": None, "gruppen": [], "rfem": False})
        if p["staebe"] is not None and set(p["staebe"]) != set(g["staebe"]):
            raise ValueError(f"Vorspannung {name}: die Gruppen liegen an verschiedenen Stäben "
                             f"({anker_text(p['staebe'])} und {anker_text(g['staebe'])}) – eine eigene "
                             "Definition je Ankergruppe wählen")
        p["staebe"] = list(g["staebe"])
        if p[z] is not None:
            raise ValueError(f"Vorspannung {name}: zwei Gruppen im {ZUSTAND_TEXT[z]} – je Definition "
                             "und Zeitpunkt eine Gruppe")
        p[z] = e
        p["gruppen"].append((g, z))
        p["rfem"] = p["rfem"] or g["art"] == ART_DT
    for name, p in plan.items():
        alt = defs.get(name)
        if alt is not None and set(alt.staebe) != set(p["staebe"]):
            raise ValueError(f"Vorspannung {name} gibt es schon an {anker_text(alt.staebe)}")
        e0, ei = p["0"], p["inf"]
        P_max = float(e0.get("P_max") or 0.0) if e0 else float(getattr(alt, "P_max", 0.0) or 0.0)
        if e0 and P_max <= 0:
            raise ValueError(f"Vorspannung {name}: P_max fehlt (Zeitpunkt 0)")
        if ei:
            ew = str(ei.get("endwert") or VORSPANN_ENDWERT_ABSOLUT)
            if ew == VORSPANN_ENDWERT_ABSOLUT and not float(ei.get("P_inf") or 0.0) > 0:
                raise ValueError(f"Vorspannung {name}: P_∞ fehlt (Zeitpunkt ∞)")
            if ew == VORSPANN_ENDWERT_VERLUST and P_max <= 0:
                raise ValueError(f"Vorspannung {name}: ΔP_t braucht P_max (P_∞ = P₀ − ΔP_t) – die Gruppe "
                                 "im Zeitpunkt 0 derselben Definition zuordnen oder P_∞ absolut eingeben")
    return plan


def vorschlag(g: dict, zustand: str) -> dict:
    """Vorschlag fuer die Werte einer Gruppe im Zuordnungsdialog: Zeitpunkt 0
    P_max = der Wert der Gruppe, Δs = 0 (bei der Anfangsvorspannung ihr Schlupf);
    Zeitpunkt ∞ P_∞ absolut = der Wert der Gruppe (Entwurf: „Der Import
    übernimmt 805 kN absolut“). Der Anwender aendert sie im Dialog."""
    if zustand == VORSPANN_ZUSTAND_0:
        return {"P_max": g["N0"], "schlupf": g.get("schlupf", 0.0), "spanngruppe": 1}
    if zustand == VORSPANN_ZUSTAND_INF:
        return {"endwert": VORSPANN_ENDWERT_ABSOLUT, "P_inf": g["N0"], "dP_t": 0.0}
    return {}


def zustaende_gebuendelt(ergebnisse) -> list:
    """Zeilen fuer Analysis.summary: je Definition und Zeitpunkt, wie viele
    Ergebnisse damit gerechnet sind („Vorspannung je Anker V1: Zeitpunkt 0 in
    128, Zeitpunkt ∞ in 293 Ergebnissen“), dazu Hinweise auf Kombinationen
    beider Zeitpunkte. Leer ohne Verweis."""
    je: dict = {}
    hinweise = []
    for name, res in ergebnisse:
        vs = ((getattr(res, "info", None) or {}).get("vorspannung") or {})
        for d, zs in (vs.get("verweise") or {}).items():
            for z in zs:
                je.setdefault(d, {}).setdefault(z, []).append(name)
        if vs.get("hinweis"):
            hinweise.append(f"{name}: {vs['hinweis']}")
    out = []
    for d, zz in je.items():
        teile = [f"{ZUSTAND_TEXT[z]} in {len(zz[z])}" for z in VORSPANN_ZUSTAENDE if z in zz]
        out.append(f"Vorspannung je Anker {d}: " + ", ".join(teile) + " Ergebnissen gerechnet")
    out += [f"HINWEIS: {h}" for h in hinweise[:5]]
    if len(hinweise) > 5:
        out.append(f"HINWEIS: … und {len(hinweise) - 5} weitere Ergebnisse mit beiden Zeitpunkten")
    return out


def vorspannung_vorhanden(model) -> bool:
    """Gibt es im Modell Vorspannung an Staeben (eingegeben, als ΔT an einem
    Zug- oder Seilstab, oder ein Verweis)? Fuer den Modellbaum: schnell, bricht
    beim ersten Fund ab."""
    for lc in (getattr(model, "load_cases", None) or {}).values():
        if getattr(lc, "vorspannzustand", None):
            return True
        if any(getattr(v, "art", "stab") == "stab" for v in (getattr(lc, "vorspannungen", None) or [])):
            return True
        for t in getattr(lc, "temp_loads", None) or []:
            if getattr(t, "aus_vorspannung", 0.0) or (not t.dT_z and t.vorspannkraft(model) > 1.0):
                return True
    return False
