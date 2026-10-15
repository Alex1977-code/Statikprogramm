"""
Stabnachweis fuer Spannstahl nach EN 1992-1-1 bzw. Zulassung (13.10.2026).

Entscheidung des Anwenders vom 13.10.2026: die 16 Ankerstaebe Rund 40 des
Drehlagers (RFEM Material 3, Werkstofftyp 15, f_p0,1k 835, f_pk 1 030 N/mm²)
werden nicht nach EN 1993-1-1/-1-8 nachgewiesen, sondern als Spannstahl im
Spannungsquerschnitt A_s des Gewindes. Bis dahin lief ueber sie der
Querschnittsnachweis N_t,Rd = A f_y / gamma_M0 mit f_y = 835 N/mm².

Geprueft wird jeder Zustand, den das Programm kennt; massgebend ist der
unguenstigste (Ergaenzung des Anwenders vom selben Tag: „die Ankerkraft sinkt
unter Last, massgebend ist also der Vorspannzustand“):

* **Spannen** - sigma = N / A_s <= sigma_p,max = min(k1 f_pk; k2 f_p0,1k)
  mit k1 = 0,8, k2 = 0,9 (EN 1992-1-1, 5.10.2.1(1)). Herangezogen wird die
  eingegebene Vorspannkraft (``Vorspannung`` am Stab, oder die
  gleichwertige Temperaturlast eines Lastfalls der Kategorie P, wie der
  RFEM-Import sie schreibt) und jedes Ergebnis mit
  ``info["zustand"] == "spannen"`` (Schnittstelle fuer den kraftgesteuerten
  Spannschritt, Zweig vorspannung/kraft).
* **nach dem Verankern** - sigma <= sigma_pm0 = min(k7 f_pk; k8 f_p0,1k)
  mit k7 = 0,75, k8 = 0,85 (5.10.3(2)). Herangezogen wird das Ergebnis jedes
  Lastfalls, der nur Vorspannung traegt (am Drehlager LF398), und jedes
  Ergebnis mit ``info["zustand"] == "verankert"``. Gibt es keines, steht die
  eingegebene Vorspannkraft ohne Verluste da - mit Vermerk.
* **Lastzustand** - sigma <= f_pd = f_p0,1k / gamma_s, gamma_s = 1,15
  (3.3.6 bzw. Zulassung; Tab. 2.1N) in jeder GZT-Kombination, bei einer
  plastischen Rechnung in jeder abgelegten Laststufe
  (``info["laststufen"]``); sind keine abgelegt, gilt der Endzustand mit
  Vermerk.

Biegung im Gewinde gibt es in diesem Nachweis nicht: Momente werden genannt,
nicht nachgewiesen. Beide Spannungsgrenzen sind am Werkstoff ueberschreibbar
(``Material.sigma_pmax``/``sigma_pm0``), wenn die Zulassung abweicht.

Die Werkstoffart ist ``Material.art`` aus dem Paket plast/verfestigung
(6e11a7c): "Spannstahl" mit f_p0,1k in ``fy`` und f_pk in ``fu``. Rechnet die
kraftgesteuerte Vorspannung (Zweig vorspannung/kraft), stehen je Stab
``res.info["vorspannung"]["staebe"][Stab]`` mit N_spannen (gegen sigma_p,max)
und N_verankert (gegen sigma_pm0) - sie gehen vor die eingegebene Kraft.

Seit dem 14.10.2026 gibt es neben der Endvorspannung (bleibend nach dem
Verankern, bis dahin „Soll nach Verankerung“) die Anfangsvorspannung
(Pressenkraft P0) mit Verankerungsschlupf Δs (statik3d.vorspannkraft). Die
drei Zustaende sind dann: Spannen mit P0, nach dem Verankern N_verankert
(P0 minus Schlupf und elastische Verluste), Lastzustand N_Ed gegen f_pd. Ohne
Ergebnis des Spannschritts steht nach dem Verankern P0 − k_A·Δs da (starre
Umgebung). :func:`je_anker` fasst die drei Zustaende je Anker zu einer Zeile
zusammen (Bericht, Tabelle „Spannstahl je Anker“).
"""
from __future__ import annotations

import numpy as np

from ..zahlen import zahl_text

#: Teilsicherheitsbeiwert des Spannstahls, staendige und voruebergehende
#: Bemessungssituation (EN 1992-1-1, Tab. 2.1N)
GAMMA_S = 1.15
#: sigma_p,max = min(K1 f_pk; K2 f_p0,1k) beim Spannen (EN 1992-1-1, 5.10.2.1(1))
K1, K2 = 0.8, 0.9
#: sigma_pm0 = min(K7 f_pk; K8 f_p0,1k) nach dem Verankern (EN 1992-1-1, 5.10.3(2))
K7, K8 = 0.75, 0.85

NORM_FPD = "EN 1992-1-1, 3.3.6 bzw. Zulassung"
NORM_SPANNEN = "EN 1992-1-1, 5.10.2.1"
NORM_VERANKERT = "EN 1992-1-1, 5.10.3"

ART = "Spannstahl"
GEWINDE_AUFGEWALZT = "aufgewalzt"
#: So steht die Auswahl in der Querschnittsmaske
GEWINDE_AUFGEWALZT_TEXT = "aufgewalzter Gewindestab (A_s = Nennquerschnitt)"

ZUSTAND_SPANNEN = "Spannen"
ZUSTAND_VERANKERT = "nach dem Verankern"
ZUSTAND_LAST = "Lastzustand"

#: Moment [Nm], ab dem ein Stab „Biegung“ hat: 1 Nmm - darunter ist es
#: Rundungsrest der Stabkraefte, kein Moment
M_GRENZE = 1e-3


def ist_spannstahl(mat) -> bool:
    """Werkstoffart Spannstahl (Material.werkstoffart, plast/verfestigung)."""
    if mat is None:
        return False
    art = mat.werkstoffart() if callable(getattr(mat, "werkstoffart", None)) else getattr(mat, "art", "")
    return art == ART


def f_p01k(mat) -> float:
    """f_p0,1k [Pa]: beim Spannstahl steht es in ``fy`` (RFEM-Import)."""
    return float(getattr(mat, "fy", None) or 0.0)


def f_pk(mat) -> float:
    """f_pk [Pa]: beim Spannstahl steht es in ``fu``."""
    return float(getattr(mat, "fu", None) or 0.0)


#: Ab hier sehen f_y / f_u aus wie f_p0,1k / f_pk eines Spannstahls [Pa]:
#: St 835/1030 am Drehlager; eine Schraube 10.9 (900/1000) liegt darunter
FY_SPANNSTAHL_AB, FU_SPANNSTAHL_UEBER = 800e6, 1000e6


def ladehinweise(model) -> list:
    """Zeilen fuers Protokoll beim Oeffnen: Werkstoffe ohne Art, deren f_y und
    f_u wie die eines Spannstahls aussehen (am Drehlager „Material 3 (DB 2309)“,
    vor dem 13.10.2026 importiert, 835/1030). Gesetzt wird nichts - die Art
    stellt der Anwender in der Werkstoffmaske."""
    from ..zahlen import zahl_text
    out = []
    for name, mat in (getattr(model, "materials", None) or {}).items():
        art = mat.werkstoffart() if callable(getattr(mat, "werkstoffart", None)) else getattr(mat, "art", "")
        fy, fu = float(mat.fy or 0.0), float(mat.fu or 0.0)
        if art or fy < FY_SPANNSTAHL_AB or fu <= FU_SPANNSTAHL_UEBER:
            continue
        out.append(f"Werkstoff „{name}“: f_y {zahl_text(fy / 1e6)} / f_u {zahl_text(fu / 1e6)} N/mm² sehen aus "
                   "wie f_p0,1k / f_pk eines Spannstahls, die Werkstoffart ist aber nicht gesetzt – ist es "
                   "Spannstahl, die Art in der Werkstoffmaske auf „Spannstahl“ stellen (dann gilt der "
                   "Stabnachweis nach EN 1992-1-1 bzw. Zulassung); gesetzt wurde nichts")
    return out


def f_pd(mat) -> float:
    return f_p01k(mat) / GAMMA_S


def _grenze(eingabe, a, fk, b, fp, formel):
    if eingabe:
        return float(eingabe), "Eingabe am Werkstoff (Zulassung)"
    kand = [w for w in ((a * fk) if fk else None, (b * fp) if fp else None) if w]
    return (min(kand) if kand else 0.0), formel


def sigma_p_max(mat) -> tuple:
    """(sigma_p,max [Pa], Herkunft): Eingabe am Werkstoff oder
    min(0,8 f_pk; 0,9 f_p0,1k) - am Drehlager min(824; 751,5) = 751,5 N/mm²."""
    return _grenze(getattr(mat, "sigma_pmax", None), K1, f_pk(mat), K2, f_p01k(mat),
                   f"min(0,8·f_pk; 0,9·f_p0,1k), {NORM_SPANNEN}")


def sigma_pm0(mat) -> tuple:
    """(sigma_pm0 [Pa], Herkunft): Eingabe am Werkstoff oder
    min(0,75 f_pk; 0,85 f_p0,1k) - am Drehlager min(772,5; 709,75) = 709,75 N/mm²."""
    return _grenze(getattr(mat, "sigma_pm0", None), K7, f_pk(mat), K8, f_p01k(mat),
                   f"min(0,75·f_pk; 0,85·f_p0,1k), {NORM_VERANKERT}")


def schraubengroessen() -> dict:
    """{"M12": A_s [m^2], …, "M36": …} nach EN ISO 898-1 (joints.bolts.SIZES:
    M16 157 mm², M20 245 mm²)."""
    from ..joints.bolts import SIZES
    return {k: v[1] * 1e-6 for k, v in SIZES.items() if 12.0 <= v[0] <= 36.0}


def schraubengroesse(sec) -> str:
    """Die Schraubengroesse des Querschnitts („M20“) oder ""."""
    g = str(getattr(sec, "gewinde", "") or "").strip().upper()
    return g if g in schraubengroessen() else ""


def gewinde_hinweis(sec) -> str:
    """Hinweis, wenn der Nenndurchmesser des gewaehlten Gewindes nicht zum
    Durchmesser eines Rundstahls passt (M20 an Rund 16), sonst "" (15.10.2026).
    Nur ein Hinweis, keine Sperre: der Anwender stellt das Gewinde allein ein
    (z. B. Gewinde kleiner als der Schaft bei einem abgesetzten Stab), und
    gerechnet wird mit dem, was er gewaehlt hat. Ohne Gewinde, bei einem
    aufgewalzten Gewindestab und bei einem Querschnitt, der kein Rundstahl ist
    (Durchmesser unbekannt), gibt es keinen Hinweis."""
    g = schraubengroesse(sec)
    if not g or getattr(sec, "typ", "") != "circle":
        return ""
    from ..joints.bolts import SIZES
    d_stab = float(getattr(sec, "h", 0.0) or 0.0) * 1e3
    d_gew = float(SIZES[g][0])
    if d_stab <= 0 or round(d_stab) == round(d_gew):
        return ""
    return (f"Gewinde {g} passt nicht zum Stabdurchmesser {zahl_text(d_stab, tausender=False)} mm "
            f"({getattr(sec, 'name', '')}): der Nenndurchmesser des Gewindes ist {zahl_text(d_gew, tausender=False)} mm "
            f"– Gewinde oder Querschnitt prüfen; gerechnet wird mit dem gewählten Gewinde "
            f"(A_s = {schraubengroessen()[g] * 1e6:.0f} mm²), gesperrt ist nichts")


def spannungsquerschnitt(sec) -> tuple:
    """(A_s [m^2], Vermerk, Meldung) fuer den Nachweis im Gewinde.

    Reihenfolge: Schraubengroesse (Tabelle EN ISO 898-1), aufgewalzter
    Gewindestab (A_s = Nennquerschnitt, ohne Meldung), Eingabe A_s aus der
    Zulassung; sonst der Nennquerschnitt A mit der Meldung „A_s aus
    Zulassung eintragen“ (Entscheidung des Anwenders vom 13.10.2026)."""
    A = float(getattr(sec, "A", 0.0) or 0.0)
    g = schraubengroesse(sec)
    if g:
        As = schraubengroessen()[g]
        return As, f"A_s = {As * 1e6:.0f} mm² (Schraube {g}, EN ISO 898-1)", ""
    if str(getattr(sec, "gewinde", "") or "") == GEWINDE_AUFGEWALZT:
        return A, "aufgewalzter Gewindestab: A_s = Nennquerschnitt", ""
    As = getattr(sec, "A_s", None)
    if As and float(As) > 0:
        return float(As), "A_s aus Eingabe (Zulassung)", ""
    return A, "A_s = Nennquerschnitt", (
        f"Querschnitt {getattr(sec, 'name', '')}: A_s aus Zulassung eintragen – gerechnet "
        f"mit dem Nennquerschnitt A = {A * 1e6:.1f} mm²")


# --------------------------------------------------------------------------
# Vorspannung im Modell
# --------------------------------------------------------------------------
def _temperatur_vorspannung(model, lc, elemente: set) -> float:
    """Groesste Vorspannkraft [N] aus Temperaturlasten der Elemente - nur in
    einem Lastfall der Kategorie P (Vorspannung): so schreibt der RFEM-Import
    die Stabvorspannung (dT = -N_0/(E A alpha)); eine Abkuehlung in einem
    Temperaturlastfall ist keine Vorspannung."""
    if getattr(lc, "category", "") != "P":
        return 0.0
    N = 0.0
    for t in lc.eigene("temp_loads") if hasattr(lc, "eigene") else (lc.temp_loads or []):
        if int(getattr(t, "elem", -1)) in elemente and hasattr(t, "vorspannkraft"):
            N = max(N, float(t.vorspannkraft(model)))
    return N


def _vorspannungen_am_stab(model, member) -> list:
    """[(Lastfall, Vorspannung)] - die Vorspannungen am Stab."""
    out = []
    for name, lc in (getattr(model, "load_cases", None) or {}).items():
        for v in (getattr(lc, "vorspannungen", None) or []):
            if getattr(v, "art", "stab") == "stab" and str(getattr(v, "ziel", "")) == member.name:
                out.append((name, v))
    return out


def eingabe_art(model, member, fall: str = None) -> str:
    """Wie die Vorspannung am Stab eingegeben ist (Benennung vom 14.10.2026):
    „Anfangsvorspannung P₀“, „Endvorspannung“, „Vorspannung als eingeprägte
    Dehnung“ oder leer - im Lastfall ``fall`` oder in irgendeinem. Am
    Drehlager tragen LF398/LF399 die RFEM-Vorspannung als ΔT, LF1 die
    Endvorspannung: je Lastfall gefragt, heisst jede Zeile richtig."""
    vs = [v for n, v in _vorspannungen_am_stab(model, member) if fall is None or n == fall]
    if any(callable(getattr(v, "ist_presse", None)) and v.ist_presse() for v in vs):
        return "Anfangsvorspannung P₀"
    if any(getattr(v, "sollkraft", False) for v in vs):
        return "Endvorspannung"
    if vs or any(N for n, N in eingegebene_vorspannung(model, member) if fall is None or n == fall):
        return "Vorspannung als eingeprägte Dehnung"
    return ""


def eingabe_text(model, member) -> str:
    """Die Eingabe am Stab zum Lesen: „Anfangsvorspannung P₀ = 1 010,84 kN,
    Δs = 1,00 mm (LF_V)“ - je Lastfall, durch Semikolon getrennt."""
    teile = []
    for name, v in _vorspannungen_am_stab(model, member):
        kn = f"{float(v.kraft) / 1e3:.2f} kN"
        if callable(getattr(v, "ist_presse", None)) and v.ist_presse():
            teile.append(f"Anfangsvorspannung P₀ = {kn}, Δs = {float(v.schlupf or 0.0) * 1e3:.2f} mm ({name})")
        elif getattr(v, "sollkraft", False):
            teile.append(f"Endvorspannung F_soll = {kn} ({name})")
        else:
            teile.append(f"Vorspannung als eingeprägte Dehnung F_v = {kn} ({name})")
    return "; ".join(teile)


def eingegebene_endvorspannung(model, member) -> list:
    """[(Lastfall, N [N], Vermerk)] - die Kraft nach dem Verankern aus der
    Eingabe, ohne Rechnung: die Endvorspannung F_soll, bei der
    Anfangsvorspannung P0 − k_A·Δs (starre Umgebung, ohne ihr Rueckfedern und
    ohne elastische Verluste), sonst die eingegebene Kraft."""
    out = []
    presse = {}
    for name, v in _vorspannungen_am_stab(model, member):
        if callable(getattr(v, "ist_presse", None)) and v.ist_presse():
            presse[name] = v
    from ..vorspannkraft import _elemente, k_stab
    for name, N in eingegebene_vorspannung(model, member):
        v = presse.get(name)
        if v is not None:
            k = k_stab(model, _elemente(model, member.name))
            out.append((name, float(v.kraft) - k * float(v.schlupf or 0.0),
                        f"Anfangsvorspannung P₀ − k_A·Δs = {float(v.kraft) / 1e3:.1f} − "
                        f"{k / 1e6:.2f} kN/mm · {float(v.schlupf or 0.0) * 1e3:.2f} mm"))
        else:
            out.append((name, N, ""))
    return out


def eingegebene_vorspannung(model, member) -> list:
    """[(Lastfall, N_0 [N])] - die Vorspannkraft, die der Anwender (oder die
    Quelldatei) fuer diesen Stab eingegeben hat, je Lastfall - bei der
    Anfangsvorspannung die Pressenkraft P0 (Kraft beim Spannen)."""
    elemente = {int(e) for e in member.elements}
    out = []
    for name, lc in (getattr(model, "load_cases", None) or {}).items():
        N = 0.0
        for v in (getattr(lc, "vorspannungen", None) or []):
            if getattr(v, "art", "stab") == "stab" and str(getattr(v, "ziel", "")) == member.name:
                N = max(N, float(getattr(v, "kraft", 0.0) or 0.0))
        N = max(N, _temperatur_vorspannung(model, lc, elemente))
        if N > 0:
            out.append((name, N))
    return out


def ist_reine_vorspannung(model, lc) -> bool:
    """Traegt der Lastfall nur Vorspannung? Vorspannungen am Stab oder Koerper
    in jeder Kategorie; Temperaturlasten nur, wenn sie in einem Lastfall der
    Kategorie P an Zugstaeben Vorspannung erzeugen (RFEM-Import, am Drehlager
    LF398 „Vorspannung der Zuganker zum Zeitpunkt 0“)."""
    try:
        arten = lc.lasten_je_art()
    except Exception:                    # noqa: BLE001 - fremdes Objekt
        return False
    if not arten or set(arten) - {"vorspannung", "temperatur"}:
        return False
    if "temperatur" in arten:
        if getattr(lc, "category", "") != "P":
            return False
        for t in arten["temperatur"]:
            if not hasattr(t, "vorspannkraft") or t.vorspannkraft(model) <= 0:
                return False
    return True


def zustaende_sammeln(model, analysis) -> dict:
    """{Name: (Results, "spannen" | "verankert")} - die Ergebnisse, die einen
    Vorspannzustand zeigen: Lastfaelle nur mit Vorspannung (nach dem
    Verankern) und jedes Ergebnis mit ``info["zustand"]`` (Spannschritt des
    kuenftigen kraftgesteuerten Vorspannens)."""
    out: dict = {}
    if not hasattr(analysis, "cases"):
        return out
    gruppen = [getattr(analysis, "cases", None) or {}, getattr(analysis, "combinations", None) or {},
               getattr(analysis, "alternativen", None) or {}]
    for g in gruppen:
        for name, res in g.items():
            info = getattr(res, "info", None) or {}
            z = str(info.get("zustand", "") or "")
            if z in ("spannen", "verankert"):
                out[name] = (res, z)
            elif isinstance(info.get("vorspannung"), dict) and (info["vorspannung"].get("staebe") or {}):
                # kraftgesteuerte Vorspannung (vorspannung/kraft): N_spannen und
                # N_verankert je Stab stehen im Ergebnis
                out[name] = (res, "vorspannkraft")
    for name, res in (getattr(analysis, "cases", None) or {}).items():
        lc = (getattr(model, "load_cases", None) or {}).get(name)
        if name not in out and lc is not None and ist_reine_vorspannung(model, lc):
            out[name] = (res, "verankert")
    return out


# --------------------------------------------------------------------------
# Nachweis
# --------------------------------------------------------------------------
def _eintrag(zustand, quelle, combo, N, x, A_s, grenze, grenzname, norm, herkunft=""):
    sigma = abs(float(N)) / A_s
    util = sigma / grenze if grenze > 0 else float("inf")
    text = (f"σ = |N| / A_s = {abs(N) / 1e3:.1f} kN / {A_s * 1e6:.1f} mm² = {sigma / 1e6:.1f} N/mm² "
            f"≤ {grenzname} = {grenze / 1e6:.2f} N/mm²" + (f" ({herkunft})" if herkunft else ""))
    return {"zustand": zustand, "quelle": quelle, "combo": combo, "N": float(N), "x": float(x),
            "sigma": sigma, "grenze": float(grenze), "grenzname": grenzname, "norm": norm,
            "util": float(util), "text": text}


#: Die drei Zustaende einer Ankerzeile (:func:`je_anker`) mit ihrem Namen fuer
#: den Anwender (Benennung vom 14.10.2026)
ANKER_SPALTEN = ((ZUSTAND_SPANNEN, "Anfangsvorspannung P₀ (Spannen)"),
                 (ZUSTAND_VERANKERT, "Endvorspannung nach dem Verankern"),
                 (ZUSTAND_LAST, "Lastzustand (GZT)"))


def je_anker(mc) -> dict:
    """{Zustand: Eintrag mit der groessten Ausnutzung} - die drei Zustaende
    eines Spannstahlstabs nebeneinander (Bericht, Tabelle „Spannstahl je
    Anker“); fehlt ein Zustand, fehlt sein Schluessel."""
    out = {}
    for e in (getattr(mc, "zustaende", None) or []):
        z = e.get("zustand")
        if z in (ZUSTAND_SPANNEN, ZUSTAND_VERANKERT, ZUSTAND_LAST) and (
                z not in out or e["util"] > out[z]["util"]):
            out[z] = e
    return out


def schlupfangaben(model, member, zustaende: dict = None) -> list:
    """Freie Ankerlaenge, Schlupf und Kraftverlust je Anfangsvorspannung (Pressenkraft
    P0) am Stab (15.10.2026): [{"lastfall", "P0" [N], "schlupf" [m], "L_frei" [m],
    "k_A" [N/m], "verlust_starr" = k_A·Δs [N], "verlust" = ΔP [N], "N_verankert" [N],
    "herkunft"}].

    ΔP = k_A·Δs·k_K/(k_A + k_K) mit k_A = E·A/L_frei (k_K die Steifigkeit der
    Umgebung); im Ergebnis des Spannschritts steht N_verankert = P0 − ΔP, daraus
    wird ΔP gelesen (``zustaende``: spannstahl.zustaende_sammeln). Ohne dieses
    Ergebnis gilt die starre Umgebung, ΔP = k_A·Δs - wie die Zeile
    „nach dem Verankern“ ohne Ergebnis. Beim reihenweisen Spannen enthaelt
    P0 − N_verankert auch die elastischen Verluste der uebrigen Anker.
    Endvorspannung und RFEM-Vorspannung haben keinen Schlupf: keine Angabe."""
    from ..vorspannkraft import _elemente, freie_laenge, k_stab
    out = []
    for name, v in _vorspannungen_am_stab(model, member):
        if not (callable(getattr(v, "ist_presse", None)) and v.ist_presse()):
            continue
        ds = float(v.schlupf or 0.0)
        if ds <= 0.0:
            continue
        els = _elemente(model, member.name)
        k = k_stab(model, els)
        P0 = float(v.kraft)
        d = None
        z = (zustaende or {}).get(name)
        if z is not None and z[1] == "vorspannkraft":
            d = (((getattr(z[0], "info", None) or {}).get("vorspannung") or {}).get("staebe") or {}).get(member.name)
        N_ver = d.get("N_verankert") if isinstance(d, dict) and d.get("kraftart") == "presse" else None
        if N_ver is not None:
            verlust, herkunft = P0 - float(N_ver), "Ergebnis des Spannschritts (Umgebung federt zurück)"
        else:
            verlust, herkunft = k * ds, "starre Umgebung (kein Ergebnis des Spannschritts)"
        out.append({"lastfall": name, "P0": P0, "schlupf": ds, "L_frei": freie_laenge(model, els),
                    "k_A": float(k), "verlust_starr": float(k * ds), "verlust": float(verlust),
                    "N_verankert": P0 - float(verlust), "herkunft": herkunft})
    return out


def schlupf_zeilen(design) -> list:
    """Zeilen fuer Protokoll und Maske Ergebnisse (DesignResults.summary): je
    Gruppe gleicher Anker eine Zeile mit freier Laenge, Schlupf und Kraftverlust."""
    gruppen: dict = {}
    for nm, mc in (getattr(design, "members", None) or {}).items():
        for a in (getattr(mc, "schlupf", None) or []):
            key = (round(a["L_frei"], 4), round(a["schlupf"], 9), round(a["P0"], 3),
                   round(a["verlust"], 3), a["herkunft"].startswith("Ergebnis"))
            g = gruppen.setdefault(key, (a, [], []))
            if nm not in g[1]:
                g[1].append(nm)
            if a["lastfall"] not in g[2]:
                g[2].append(a["lastfall"])
    out = []
    for (a, namen, faelle) in gruppen.values():
        n = len(namen)
        wer = namen[0] if n == 1 else f"{namen[0]} bis {namen[-1]} ({n} Anker)" if n > 2 else " und ".join(namen)
        out.append(
            f"Verankerungsschlupf {wer} ({', '.join(faelle[:4])}{' …' if len(faelle) > 4 else ''}): freie Länge {a['L_frei']:.3f} m, "
            f"Δs = {a['schlupf'] * 1e3:.2f} mm, k_A = {a['k_A'] / 1e6:.2f} kN/mm, "
            f"Kraftverlust ΔP = {a['verlust'] / 1e3:.2f} kN "
            f"(P₀ = {a['P0'] / 1e3:.2f} kN → {(a['P0'] - a['verlust']) / 1e3:.2f} kN nach dem Verankern; "
            + ("ΔP = P₀ − N_verankert aus dem Ergebnis" if a["herkunft"].startswith("Ergebnis")
               else "starre Umgebung: ΔP = k_A·Δs") + ")")
    return out


def stab_nachweis(model, member, results: dict, n: int, mc, sec, mat, zustaende: dict = None):
    """Den Spannstahlnachweis des Stabes in ``mc`` (MemberCheck) eintragen."""
    mc.art = ART
    A_s, vermerk, meldung = spannungsquerschnitt(sec)
    fp = f_p01k(mat)
    if fp <= 0 or A_s <= 0:
        mc.fehler = (f"Spannstahl {mat.name} ohne f_p0,1k" if fp <= 0
                     else f"Querschnitt {sec.name} ohne Fläche")
        mc.warnings.append(f"{mc.fehler} – Nachweis nicht geführt; f_p0,1k am Werkstoff bzw. A_s am "
                           "Querschnitt eintragen oder am Stab „Nachweis nach EC3“ ausschalten")
        return mc
    if meldung:
        mc.warnings.append(meldung)
    if gewinde_hinweis(sec):
        mc.warnings.append(gewinde_hinweis(sec))
    fpd = fp / GAMMA_S
    pmax, h_pmax = sigma_p_max(mat)
    pm0, h_pm0 = sigma_pm0(mat)
    ext = {k: 0.0 for k in ("N_min", "N_max", "Vy_max", "Vz_max", "Mt_max", "My_max", "Mz_max")}
    eintraege: list = []
    momente: list = []
    druck: list = []

    def aus_ergebnis(res, quelle, combo, zustand, grenze, grenzname, norm, herkunft="", extrem=False):
        mf = res.member_forces(member, n)
        N = np.asarray(mf["N"], float)
        if not len(N):
            return
        My, Mz = np.abs(np.asarray(mf["My"], float)), np.abs(np.asarray(mf["Mz"], float))
        if extrem:
            ext["N_min"] = min(ext["N_min"], float(N.min()))
            ext["N_max"] = max(ext["N_max"], float(N.max()))
            for k, key in (("Vy_max", "Vy"), ("Vz_max", "Vz"), ("Mt_max", "Mt"), ("My_max", "My"),
                           ("Mz_max", "Mz")):
                ext[k] = max(ext[k], float(np.abs(np.asarray(mf[key], float)).max()))
        if max(float(My.max()), float(Mz.max())) > M_GRENZE:
            momente.append((quelle, float(My.max()), float(Mz.max())))
        if float(N.min()) < -1.0:
            druck.append((quelle, float(N.min())))
        j = int(np.argmax(np.abs(N)))
        eintraege.append(_eintrag(zustand, quelle, combo, N[j], mf["x"][j], A_s, grenze, grenzname,
                                  norm, herkunft))

    # Lastzustaende: jede GZT-Kombination, bei plastischer Rechnung jede
    # abgelegte Laststufe
    for cname, res in (results or {}).items():
        info = getattr(res, "info", None) or {}
        stufen = info.get("laststufen") or []
        for k, st in enumerate(stufen, 1):
            lam = (getattr(st, "info", None) or {}).get("lam")
            q = f"{cname}, Laststufe {k}" + (f" (λ = {zahl_text(float(lam), tausender=False, stellen=4, punkt=True)})"
                                             if lam is not None else "")
            aus_ergebnis(st, q, cname, ZUSTAND_LAST, fpd, "f_pd", NORM_FPD, "f_p0,1k / γ_s")
        if info.get("plastizitaet") and not stufen:
            mc.warnings.append(f"Laststufen der Plastizität von {cname} nicht abgelegt – nachgewiesen "
                               "ist der Endzustand")
        aus_ergebnis(res, cname, cname, ZUSTAND_LAST, fpd, "f_pd", NORM_FPD, "f_p0,1k / γ_s", extrem=True)
    # Spannen: die eingegebene Vorspannkraft und Ergebnisse eines Spannschritts
    eingaben = eingegebene_vorspannung(model, member)
    # Benennung vom 14.10.2026: Anfangsvorspannung (Pressenkraft P0) und
    # Endvorspannung (bleibend nach dem Verankern); bis dahin „Vorspannkraft“
    for lcname, N0 in eingaben:
        art = eingabe_art(model, member, lcname) or "Vorspannkraft"
        eintraege.append(_eintrag(ZUSTAND_SPANNEN, f"{lcname}: eingegebene {art}", lcname, N0, 0.0,
                                  A_s, pmax, "σ_p,max", NORM_SPANNEN, h_pmax))
    verankert = False
    for name, (res, z) in (zustaende or {}).items():
        if z == "spannen":
            aus_ergebnis(res, f"{name} (Spannschritt)", name, ZUSTAND_SPANNEN, pmax, "σ_p,max",
                         NORM_SPANNEN, h_pmax)
        elif z == "verankert":
            verankert = True
            aus_ergebnis(res, f"{name} (Ergebnis, nur Vorspannung)", name, ZUSTAND_VERANKERT, pm0,
                         "σ_pm0", NORM_VERANKERT, h_pm0)
        elif z == "vorspannkraft":
            d = ((getattr(res, "info", None) or {}).get("vorspannung", {}).get("staebe") or {}).get(member.name)
            if not d:
                continue
            presse = d.get("kraftart") == "presse"
            if d.get("N_spannen") is not None:
                eintraege.append(_eintrag(
                    ZUSTAND_SPANNEN, f"{name}: N_spannen = " + ("Anfangsvorspannung P₀ (Pressenkraft, Spannschritt)"
                                                                if presse else "Endvorspannung (Spannschritt)"),
                    name, float(d["N_spannen"]), 0.0, A_s, pmax, "σ_p,max", NORM_SPANNEN, h_pmax))
            if d.get("N_verankert") is not None:
                verankert = True
                eintraege.append(_eintrag(
                    ZUSTAND_VERANKERT, f"{name}: N_verankert = Endvorspannung nach dem Verankern"
                    + (f" (P₀ − Schlupf Δs = {float(d.get('schlupf', 0.0)) * 1e3:.2f} mm und elastische Verluste)"
                       if presse else ""),
                    name, float(d["N_verankert"]), 0.0, A_s, pm0, "σ_pm0", NORM_VERANKERT, h_pm0))
    if not verankert:
        for lcname, N0, vermerk in eingegebene_endvorspannung(model, member):
            art = eingabe_art(model, member, lcname) or "Vorspannkraft"
            eintraege.append(_eintrag(
                ZUSTAND_VERANKERT, f"{lcname}: eingegebene {art}, "
                + (f"{vermerk} (starre Umgebung), ohne elastische Verluste" if vermerk
                   else "ohne Verluste angesetzt")
                + " (kein Ergebnis eines Lastfalls nur mit Vorspannung)", lcname, N0, 0.0, A_s, pm0,
                "σ_pm0", NORM_VERANKERT, h_pm0))
    mc.zustaende = eintraege
    # freie Ankerlaenge, Schlupf und Kraftverlust (15.10.2026) - ein Attribut wie
    # ``zustaende``, kein Feld (Abdruck der Stahlnachweise bleibt)
    mc.schlupf = schlupfangaben(model, member, zustaende)
    mc.extremes = ext
    # Befund Vorspannung (Ergaenzung des Anwenders vom 13.10.2026): liegt die
    # Kraft beim Spannen oder nach dem Verankern ueber ihrer Grenze, steht das
    # als eigene Zeile am Stab, mit der Kraft, die die Grenze zuliesse - am
    # Drehlager 0,9 · 835 · 1 256,64 = 944,36 kN beim Spannen und
    # 709,75 · 1 256,64 = 891,9 kN nach dem Verankern
    for zst in (ZUSTAND_SPANNEN, ZUSTAND_VERANKERT):
        ueber = [e for e in eintraege if e["zustand"] == zst and e["util"] > 1.0]
        if ueber:
            e = max(ueber, key=lambda x: x["util"])
            mc.warnings.append(
                f"Befund Vorspannung, {zst}: {e['quelle']} – N = {abs(e['N']) / 1e3:.1f} kN, "
                f"σ = {e['sigma'] / 1e6:.1f} N/mm² > {e['grenzname']} = {e['grenze'] / 1e6:.2f} N/mm² "
                f"(Verhältnis {e['util']:.4f}); zulässig wären {e['grenze'] * A_s / 1e3:.1f} kN mit "
                f"A_s = {A_s * 1e6:.1f} mm² – Vorspannkraft gegen die Zulassung prüfen")
    if momente:
        q, my, mz = max(momente, key=lambda t: max(t[1], t[2]))
        mc.warnings.append(f"Biegung im Gewinde wird nicht nachgewiesen: max |M_y| = {my / 1e3:.3f} kNm, "
                           f"max |M_z| = {mz / 1e3:.3f} kNm ({q}) – nachgewiesen ist nur σ = |N| / A_s")
    if druck:
        q, nmin = min(druck, key=lambda t: t[1])
        mc.warnings.append(f"Druck im Spannstahlstab: N_min = {nmin / 1e3:.1f} kN ({q}) – nachgewiesen ist "
                           "|N| / A_s, Knicken nicht")
    if not eintraege:
        return mc
    g = max(eintraege, key=lambda e: e["util"])
    mc.governing = {"name": f"Spannstahl, {g['zustand']}: σ ≤ {g['grenzname']} ({g['norm']}; {vermerk})",
                    "combo": g["combo"], "x": g["x"], "util": g["util"],
                    "text": g["text"] + f"; {g['quelle']}", "kind": ART}
    mc.util = g["util"]
    return mc
