"""Vorspannkraft (Soll nach Verankerung): Spannen, Verriegeln, dann die Lasten.

Entscheidung des Anwenders vom 13.10.2026 (woertlich): „Vorspannung
kraftgesteuert eingeben. Neue Lastart „Vorspannkraft (Soll nach Verankerung)“
je Stab. Umsetzung als eigener Spannschritt vor den übrigen Lasten: Im
Spannschritt wirkt der Stab als Kräftepaar F_soll an beiden Enden
(Stabsteifigkeit inaktiv). Danach wird der Stab in der verformten Lage mit
Normalkraft F_soll aktiviert (Verriegeln), anschließend folgen die äußeren
Lasten. Optional gleichzeitiges oder reihenweises Spannen (dann mit Verlusten
früher gespannter Anker). Für linear-elastische Rechnungen alternativ
eingeprägte Dehnung, über die Einflussmatrix der Anker so skaliert, dass exakt
F_soll entsteht. Die bisherige RFEM-Logik (Anfangsvorspannung als eingeprägte
Dehnung) bleibt für den Import erhalten.“

Anlass: die Vorspannung als Anfangsdehnung (model.Vorspannung, RFEM-Import als
Abkuehlung) gibt dem Stab nicht seine Kraft, sondern F minus die elastische
Verkuerzung der Umgebung. Am Drehlager trugen die Anker bei voller Last 782 bis
833 statt 952 kN (Lauf 8adc629, scratchpad ff_werk).

**Spannen und Verriegeln** (:func:`rechnen`, nichtlinear oder reihenweise):

1. *Spannen*: ein System ohne die Staebe der Gruppe (und der spaeteren), an
   ihren Enden das Kraeftepaar ±F_soll in Stabrichtung - derselbe Lastvektor
   wie eine Vorspannung mit F_soll (Stabenden, Gelenke, Versaetze wie im
   Modell). Gerechnet bis zum Gleichgewicht mit Kontakt und Plastizitaet
   (solver._solve_loads); Ergebnis u_S, plastischer Zustand, Kontaktzustand.
2. *Verriegeln*: je Element die Kraft P = F_soll − N_el(u_S), mit N_el der
   elastischen Normalkraft E A Δl/L aus u_S. Das ist eine eingepraegte Dehnung
   ε0 = −P/(E A) je Element (nicht ueber ΔT): die spannungsfreie Laenge ist so
   gesetzt, dass bei u_S genau N = N_el + P = F_soll gilt. Gleichgewicht: im
   Spannschritt gilt f_int,Rest(u_S) = F_paar; mit dem aktiven Stab kommt
   K_Stab u_S = −paar(N_el) dazu, die Last ist paar(P) = F_paar − paar(N_el) -
   also K_ges u_S = F_lock + F_p(ε_p,S): u_S bleibt die Gleichgewichtslage.
3. *Lasten*: der Lastfall mit den Verriegelungskraeften (sofort voll), vom
   Kontakt- und plastischen Zustand des Spannschritts aus.

Reihenweise: Gruppe fuer Gruppe; die frueher verriegelten Staebe sind im
naechsten Spannschritt aktiv und verlieren Kraft - ausgewiesen je Stab.

**Einflussmatrix** (linear, gleichzeitig): A_ij = N_i unter der Vorspannung 1
(Anfangsdehnung) im Stab j - eine Zerlegung, n Loesungen. P = A⁻¹ F_soll ist
die eingepraegte Kraft je Stab, unter der Vorspannung allein traegt jeder
Stab genau F_soll. Linear ist das dasselbe wie Spannen und Verriegeln
(tests/test_vorspannkraft.py).

**Import**: :func:`import_hinweise` nennt je Vorspannung als eingepraegte
Dehnung (RFEM) die Kraft X nach elastischer Verkuerzung (linear,
Einflussmatrix), :func:`in_sollkraft_umwandeln` stellt die ΔT-Last auf die
Endvorspannung um - nur auf Anweisung des Anwenders. Bis zum 14.10.2026 hiess
die RFEM-Vorspannung im Hinweis „Anfangsvorspannung“; seitdem meint das Wort
nur die Pressenkraft P0 (Benennung des Anwenders: „vllt sollte man das
Anfangsvorspannung und Endvorspannung nennen mit erklärung“).

**Anfangsvorspannung (Pressenkraft P0) mit Verankerungsschlupf** (seit
14.10.2026, ``Vorspannung.kraftart`` = "presse", Vorgabe des Anwenders: „Bitte
im Spannschritt wahlweise „Pressenkraft + Verankerungsschlupf (mm)“
ermöglichen“). Die bisherige Sollkraft heisst in der Oberflaeche seitdem
„Endvorspannung (bleibend nach dem Verankern)“.

* Im Spannschritt wirkt P0 als Kraeftepaar (N_spannen = P0).
* Beim Verriegeln verliert der Stab den Schlupf: die spannungsfreie Laenge
  waechst um Δs, gegen starre Umgebung sinkt N um k_A Δs mit
  k_A = 1 / Σ L_i/(E_i A_i) ueber die Elemente des Stabs (bei einem
  Querschnitt E A / L). L ist die Stablaenge, also die Laenge zwischen den
  Ankerpunkten, ueber die sich die Dehnung des Spannglieds verteilt - dieselbe
  Laenge, mit der die Stabsteifigkeit rechnet. Nur so ist der Schlupf genau
  eine Verlaengerung um Δs; mit einer anderen „freien Laenge“ gehoerte zu
  derselben Kraft ein anderer Weg, und die Rechnung waere nicht mehr der
  Stab im Modell. Ziel beim Verriegeln ist N(u_S) = P0 − k_A Δs.
* Danach federt die Umgebung zurueck, der Stab gewinnt einen Teil wieder
  (Federverteilung, zwischen Federn N = P0 − k_A Δs k_K/(k_A + k_K)).
  N_verankert ist dieses Gleichgewicht: linear ueber die Einflussmatrix
  (der Schlupf ist eine eingepraegte Kraft −k_A Δs, P = A⁻¹ P0 − k Δs),
  nichtlinear in einem eigenen Verankerungsschritt am System des Lastfalls
  mit Kontakt und Plastizitaet - nur wenn die zuletzt gespannte Gruppe einen
  Schlupf hat; frueher gespannte Gruppen gleicht der naechste Spannschritt
  ohnehin aus. Elastische Verluste durch reihenweises Spannen kommen wie
  bisher dazu.
* Ohne Schlupf ist es Zahl fuer Zahl die Endvorspannung mit F_soll = P0.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field

import numpy as np

from . import assemble as asm
from .model import LoadCase, Vorspannung

WEG_EINFLUSS = "einflussmatrix"
WEG_SPANNEN = "spannen und verriegeln"

#: Namen der Lastarten fuer den Anwender (Benennung vom 14.10.2026, Maske,
#: Lasttabelle, Bericht, Handbuch). Bis dahin hiess die Endvorspannung
#: „Vorspannkraft (Soll nach Verankerung)“, und „Anfangsvorspannung“ stand fuer
#: die RFEM-Vorspannung als eingepraegte Dehnung.
LASTART_DEHNUNG = "Vorspannung als eingeprägte Dehnung (F_v)"
LASTART_ENDE = "Endvorspannung (bleibend nach dem Verankern)"
LASTART_PRESSE = "Anfangsvorspannung (Pressenkraft P₀)"
LASTART_UMWANDELN = "Eingeprägte Dehnung (RFEM, ΔT) in Endvorspannung umwandeln"
ERKLAERUNG_ENDE = "Kraft, die nach dem Verankern im Stab verbleibt, vor den äußeren Lasten."
ERKLAERUNG_PRESSE = ("Kraft der Presse beim Spannen, vor dem Verankern; nach dem Verankern verringert um "
                     "den Verankerungsschlupf Δs und die elastischen Verluste.")

#: Linear-elastisch und gleichzeitig gespannt: die eingepraegte Dehnung ueber
#: die Einflussmatrix (eine Zerlegung, n Loesungen). WEG_SPANNEN rechnet auch
#: dort Spannen und Verriegeln - gleiches Ergebnis, ein System mehr je Gruppe
#: (Gegenprobe in tests/test_vorspannkraft.py).
LINEAR_WEG = WEG_EINFLUSS

#: Groesste Modellgroesse [FHG], bis zu der der Import die Kraft X nach
#: elastischer Verkuerzung gleich rechnet (eine Zerlegung). Darueber, mit
#: Kontakt oder mit unvernetzten Koerpern folgt X nach der ersten Rechnung
#: eines Lastfalls, der nur die Vorspannung traegt. Am Drehlager braucht eine
#: Zerlegung 7 GB (solver.LinearSolver.freigeben, 11.09.2026) - beim Import
#: ist das zu viel, und der Kontakt macht es ohnehin nichtlinear.
X_FHG_GRENZE = 300_000



@dataclass
class Soll:
    """Eine Sollkraft eines Lastfalls oder einer Kombination (mit Faktor):
    ``kraft`` ist die Kraft im Spannschritt (Endvorspannung F_soll bzw.
    Pressenkraft P0), ``schlupf`` [m] der Verankerungsschlupf der
    Anfangsvorspannung (``presse``), mit demselben Faktor wie die Kraft."""
    stab: str
    kraft: float
    gruppe: int = 1
    schlupf: float = 0.0
    presse: bool = False


def sollkraefte(model, factors) -> list:
    """Die Sollkraefte der Lastfaelle in ``factors`` (Name -> Faktor), je
    Stab zusammengezaehlt - leer, wenn keiner eine traegt."""
    je: dict = {}
    for name, f in (factors or {}).items():
        if not f:
            continue
        lc = (getattr(model, "load_cases", None) or {}).get(name)
        if lc is None:
            continue
        for v in getattr(lc, "vorspannungen", None) or []:
            if not getattr(v, "sollkraft", False) or getattr(v, "art", "stab") != "stab" or not v.kraft:
                continue
            k, g, ds, pr = je.get(v.ziel, (0.0, None, 0.0, False))
            gv = int(getattr(v, "gruppe", 1) or 1)
            presse = callable(getattr(v, "ist_presse", None)) and v.ist_presse()
            ds_v = float(getattr(v, "schlupf", 0.0) or 0.0) if presse else 0.0
            je[v.ziel] = (k + float(f) * float(v.kraft), gv if g is None else min(g, gv),
                          ds + float(f) * ds_v, pr or presse)
    return [Soll(s, k, g, ds, pr) for s, (k, g, ds, pr) in je.items() if k]


def freie_laenge(model, elemente: list) -> float:
    """Freie Ankerlaenge L [m]: die Summe der Elementlaengen des Stabs - die
    Laenge, mit der :func:`k_stab` rechnet (k_A = E A / L bei einem
    Querschnitt). Sie steht im Spannstahlnachweis neben Δs und ΔP (15.10.2026)."""
    from .elements import beam3d as bm
    L = 0.0
    for i in elemente:
        e = model.elements[int(i)]
        _T3, Li = bm.local_axes(model.nodes[e.nodes][0], model.nodes[e.nodes][1], e.roll)
        L += float(Li)
    return L


def k_stab(model, elemente: list) -> float:
    """Laengssteifigkeit k_A [N/m] eines Stabs aus seinen Elementen in Reihe:
    1 / Σ (L_i/(E_i A_i) + 1/k_Feder) - bei einem Querschnitt E A / L, mit L
    der Stablaenge zwischen den Ankerpunkten (Anfangsvorspannung, 14.10.2026)."""
    from .elements import beam3d as bm
    nachgiebig = 0.0
    for i in elemente:
        e = model.elements[int(i)]
        mat, sec = model.materials[e.mat], model.sections[e.sec]
        X = model.nodes[e.nodes]
        _T3, L = bm.local_axes(X[0], X[1], e.roll)
        nachgiebig += float(L) / (float(mat.E) * float(sec.A))
        nachgiebig += sum(1.0 / float(k) for d, k in (getattr(e, "hinge_springs", None) or [])
                          if int(d) in (0, 6) and k and float(k) > 0)
    return 1.0 / nachgiebig if nachgiebig > 0 else 0.0


def _ziel(model, s: Soll, els: dict) -> tuple:
    """(Ziel N nach dem Verriegeln gegen starre Umgebung, k_A): F_soll bei der
    Endvorspannung, P0 − k_A Δs bei der Anfangsvorspannung."""
    if not s.schlupf:
        return float(s.kraft), 0.0
    k = k_stab(model, els[s.stab])
    return float(s.kraft) - k * float(s.schlupf), k


def _presse_info(model, s: Soll, els: dict) -> dict:
    """Eintraege der Anfangsvorspannung in res.info["vorspannung"]["staebe"]
    (nur dort - die Endvorspannung behaelt ihre Eintraege, wie sie waren)."""
    if not s.presse:
        return {}
    T, k = _ziel(model, s, els)
    k = k or k_stab(model, els[s.stab])
    return {"kraftart": "presse", "schlupf": float(s.schlupf), "k_A": float(k),
            "schlupfverlust": float(k * s.schlupf), "N_verriegelt": float(T)}


def _elemente(model, stab: str, aktiv=None) -> list:
    """Die Stabelemente eines Stabs (wirksam in ``aktiv``)."""
    mem = (getattr(model, "members", None) or {}).get(stab)
    out = []
    for i in (mem.elements if mem else []):
        i = int(i)
        if 0 <= i < len(model.elements) and model.elements[i].typ in asm.LINE_TYPES \
                and (aktiv is None or bool(aktiv[i])):
            out.append(i)
    return out


def _n_elastisch(model, i: int, u: np.ndarray) -> float:
    """Elastische Normalkraft E A Δl / L des Stabelements i aus u - ohne
    Anfangsdehnung, Temperatur oder Verriegelung (die zaehlt der Aufrufer).
    Dieselbe Funktion wie geometrische Steifigkeit und Ausfall-Iteration
    (asm.stab_normalkraft, 13.10.2026); bis dahin (k u)[6] - dieselbe Zahl bis
    auf die letzte Stelle."""
    return float(asm.stab_normalkraft(model, model.elements[i], u))


def _u_voll(model, res) -> np.ndarray:
    """Der Verschiebungsvektor (ndof,) eines Ergebnisses."""
    u = np.zeros(model.ndof)
    n6 = model.nn * 6
    u[:n6] = np.asarray(res.u, float).ravel()[:n6]
    return u


def _cache(system) -> dict:
    """Ablage am System: Einflussmatrizen und Spannzustaende werden je
    Rechnung einmal gebildet - am Drehlager tragen 422 Lastfaelle dieselben
    16 Anker."""
    c = getattr(system, "_vorspann_cache", None)
    if c is None:
        c = {}
        try:
            system._vorspann_cache = c
        except AttributeError:
            pass
    return c


def _stablast(model, eintraege, aktiv=None) -> tuple:
    """(F, feq) einer Vorspannung als Anfangsdehnung mit den Kraeften
    ``eintraege`` [(Stab, Kraft)] - das Kraeftepaar des Spannschritts bzw. die
    eingepraegte Dehnung der Einflussmatrix, ueber denselben Weg wie jede
    Vorspannung im Stab (asm.load_vector)."""
    lc = LoadCase(name="_vorspannkraft",
                  vorspannungen=[Vorspannung(str(s), "stab", float(k)) for s, k in eintraege])
    return asm.load_vector(model, lc, aktiv), asm.element_equivalent_loads(model, lc, aktiv)


def _verriegelung(model, P: dict) -> tuple:
    """(F, feq) der Verriegelung: je Element die Kraft P (eingepraegte
    Dehnung −P/(E A)), lokal [+P ... −P] wie eine Vorspannung im Stab."""
    feq = {}
    for i, p in P.items():
        f = np.zeros(12)
        f[0] = float(p)
        f[6] = -float(p)
        feq[int(i)] = f
    F = np.zeros(model.ndof)
    asm.stablasten_einbauen(model, feq, F)
    asm.mittelknoten_umlenken(model, F)
    return F, feq


def _n0_ausfall(model, P: dict) -> dict:
    """{Element: (N0, FHG, Werte)} der verriegelten Staebe, die ausfallen
    koennen (nur Zug/Druck, Seil) - fuer solver.solve_with_ausfall."""
    out = {}
    for i, p in P.items():
        e = model.elements[int(i)]
        if not (getattr(e, "nur", "") or e.typ == "seil"):
            continue
        F_i, _f = _verriegelung(model, {int(i): p})
        idx = np.nonzero(F_i)[0]
        out[int(i)] = (float(p), idx, F_i[idx])
    return out


# --------------------------------------------------------------------------
# Einflussmatrix (linear)
# --------------------------------------------------------------------------
def einflussmatrix(model, system, staebe: list) -> np.ndarray:
    """A_ij = Normalkraft im Stab i unter der Vorspannung 1 N (Anfangsdehnung)
    im Stab j - mit der Zerlegung des Systems, eine Loesung je Stab. Am System
    gemerkt."""
    staebe = [str(s) for s in staebe]
    c = _cache(system)
    key = ("einfluss", tuple(staebe))
    if key in c:
        return c[key]
    aktiv = getattr(system, "aktiv", None)
    els = {s: _elemente(model, s, aktiv) for s in staebe}
    leer = [s for s in staebe if not els[s]]
    if leer:
        raise ValueError("Vorspannkraft: " + ", ".join(leer) + " hat keine wirksamen Stabelemente")
    u0 = system.solve(np.zeros(model.ndof)) if np.any(getattr(system, "vals", 0.0)) else None
    n = len(staebe)
    A = np.zeros((n, n))
    for j, s in enumerate(staebe):
        f, _feq = _stablast(model, [(s, 1.0)], aktiv)
        u = np.asarray(system.solve(f), float)
        if u0 is not None:
            u = u - u0
        for i, t in enumerate(staebe):
            A[i, j] = float(np.mean([_n_elastisch(model, e, u) for e in els[t]])) + (1.0 if i == j else 0.0)
    c[key] = A
    return A


def _einfluss_loesen(A: np.ndarray, F: np.ndarray, staebe: list) -> np.ndarray:
    """P mit A P = F; ein Stab, den nichts haelt, kann keine Vorspannung
    tragen (A_jj = 0) - das wird gesagt, nicht geraten."""
    d = np.abs(np.diag(A))
    schwach = [s for s, x in zip(staebe, d) if x < 1e-9]
    if schwach:
        raise ValueError("Vorspannkraft: " + ", ".join(schwach) + " ist nicht gehalten - "
                         "der Stab verkürzt sich frei und kann keine Vorspannung tragen")
    return np.linalg.solve(A, F)


# --------------------------------------------------------------------------
# Rechnung
# --------------------------------------------------------------------------
#: Spannschritt in Stufen (14.10.2026, Entscheidung des Anwenders: „Vorspannung
#: als eigenen, ggf. gestuften Spannschritt vor den äußeren Lasten aufbringen“).
#: Bis dahin wirkte das Kraeftepaar F_soll im Spannschritt in einem Zug: mit
#: Kontakt ein Kontaktlauf von der Geometrie bis zur vollen Kraft, mit Fliessen
#: in jeder Laststufe der Plastizitaet die volle Kraft (F_S = F, stufenlast). In
#: n Stufen waechst es in n gleichen Schritten auf F_soll, und jede Stufe rechnet
#: Kontakt und Fliessen vom Zustand der vorigen aus bis zum Gleichgewicht.
#: Vorgabe (``Plastizitaet.spannstufen`` = 0): mit Kontakt oder Fliessen
#: SPANNSTUFEN_AUTOMATISCH Stufen, sonst eine. Warum: Reibung und Fliessen
#: haengen am Weg - gespannt wird mit der Presse allmaehlich, und eine Fuge, die
#: sich unter dem Anziehen schliesst und haftet, oder ein Lochrand, der unter der
#: Mutter fliesst, folgt dieser Geschichte, nicht einem Sprung von null auf
#: F_soll; dazu beginnt jede Stufe beim Zustand der vorigen, die Kontaktlaeufe
#: haben weniger Zustandswechsel vor sich. Ohne beides ist die Rechnung linear und
#: wegunabhaengig, eine Stufe ist dort exakt, und jede weitere kostete nur Zeit.
#: Drei wie die Vorgabe der Laststufen der Plastizitaet - gewaehlt, nicht gemessen.
SPANNSTUFEN_AUTOMATISCH = 3


def spannstufen(model) -> int:
    """Wie viele Stufen der Spannschritt hat (siehe :data:`SPANNSTUFEN_AUTOMATISCH`)."""
    from . import solver as sv
    try:
        n = int(getattr(getattr(model, "plastizitaet", None), "spannstufen", 0) or 0)
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return n
    return SPANNSTUFEN_AUTOMATISCH if (getattr(model, "has_contact", False) or sv._plastisch(model)) else 1


def weg(model, soll: list) -> str:
    """Welcher Weg: Spannen und Verriegeln bei Kontakt, Plastizitaet,
    Ausfallstaeben oder reihenweisem Spannen; sonst :data:`LINEAR_WEG`."""
    from . import solver as sv
    if sv._nichtlinear(model) or len({s.gruppe for s in soll}) > 1:
        return WEG_SPANNEN
    return WEG_SPANNEN if LINEAR_WEG == WEG_SPANNEN else WEG_EINFLUSS


def rechnen(model, system, factors: dict, name: str, kind: str, workers=None, progress=None,
            start=None, einfrieren=None, fenster=None, probelauf: bool = False, start_von=None):
    """Einen Lastfall (oder eine direkt geloeste Kombination) mit Sollkraeften
    rechnen - aus solver._solve_loads. Rueckgabe das Ergebnis des Lastfalls
    mit ``res.info["vorspannung"]``; Spannen und Verriegeln legt die Zustaende
    dazu in ``res.vorspannzustaende`` ({"spannen": [je Gruppe], "verankert"})."""
    from . import solver as sv
    soll = sollkraefte(model, factors)
    w = weg(model, soll)
    kw = dict(workers=workers, progress=progress, einfrieren=einfrieren, fenster=fenster,
              probelauf=probelauf)
    aktiv = getattr(system, "aktiv", None)
    staebe = [s.stab for s in soll]
    els = {s: _elemente(model, s, aktiv) for s in staebe}
    if w == WEG_EINFLUSS:
        A = einflussmatrix(model, system, staebe)
        Fs = np.array([s.kraft for s in soll], float)
        P = _einfluss_loesen(A, Fs, staebe)
        # Anfangsvorspannung: der Schlupf ist eine eingepraegte Kraft −k_A Δs
        # im Stab; A verteilt ihn auf Stab und Umgebung (14.10.2026)
        P = P - np.array([_ziel(model, s, els)[1] * s.schlupf for s in soll], float)
        F_v, feq_v = _stablast(model, list(zip(staebe, P)), aktiv)
        sv._melde(progress, f"{name}: End- bzw. Anfangsvorspannung über die Einflussmatrix "
                            f"({len(staebe)} {'Stab' if len(staebe) == 1 else 'Stäbe'})")
        res = sv._solve_loads(model, system, factors, name, kind, start=start, start_von=start_von,
                              zusatz={"F": F_v, "feq": feq_v, "F_S": F_v}, **kw)
        N_v = A @ P
        info = {"weg": WEG_EINFLUSS, "reihenfolge": [staebe], "staebe": {}}
        for k, s in enumerate(soll):
            # N_spannen: das Kraeftepaar des gleichwertigen Spannschritts (seit
            # 14.10.2026 auch hier; bis dahin nahm der Spannstahlnachweis die Eingabe)
            info["staebe"][s.stab] = {"F_soll": float(s.kraft), "gruppe": int(s.gruppe),
                                      "N_spannen": float(s.kraft),
                                      "N_verankert": float(N_v[k]),
                                      "verlust": float(s.kraft - N_v[k]),
                                      "P_eingepraegt": float(P[k]),
                                      "N_ende": _n_ergebnis(res, els[s.stab]),
                                      **_presse_info(model, s, els)}
        res.info["vorspannung"] = info
        return res
    z = _spannzustand(model, system, soll, els, **kw)
    zusatz = {"F": z["F"], "feq": z["feq"], "F_S": z["F"], "n0": z["n0"], "plast_start": z["plast"]}
    st = z["kontakt"] if z["kontakt"] is not None else start
    res = sv._solve_loads(model, system, factors, name, kind, start=st,
                          start_von="Spannschritt" if z["kontakt"] is not None else start_von,
                          zusatz=zusatz, **kw)
    info = {"weg": WEG_SPANNEN, "reihenfolge": [list(g) for g in z["reihenfolge"]], "staebe": {},
            "zustaende": ["spannen", "verankert"], "zeit_spannen": float(z["zeit"]),
            "spannstufen": int(z.get("spannstufen", 1))}
    if z.get("verankern"):
        info["verankerungsschritt"] = True
    for s in soll:
        d = dict(z["staebe"][s.stab])
        d["N_ende"] = _n_ergebnis(res, els[s.stab])
        info["staebe"][s.stab] = d
    res.info["vorspannung"] = info
    # Ein vorlaeufiger Spannzustand macht den Lastfall vorlaeufig: er startet von
    # ihm (Entscheidung des Anwenders vom 14.10.2026)
    sp_vorl = [str(x.info["vorlaeufig"].get("text", "")) for x in z["spannen"] + z.get("verankern", [])
               if isinstance(getattr(x, "info", {}).get("vorlaeufig"), dict)]
    if sp_vorl:
        v = dict(res.info.get("vorlaeufig") or {"grund": "kontakt", "stellen": []})
        v["stellen"] = ["Spannschritt"] + [x for x in (v.get("stellen") or []) if x != "Spannschritt"]
        v["text"] = f"{sv.VORLAEUFIG} in " + ", ".join(v["stellen"])
        res.info["vorlaeufig"] = v
    res.vorspannzustaende = {"spannen": list(z["spannen"]), "verankert": z["verankert"]}
    return res


def _n_ergebnis(res, elemente: list) -> float:
    """Normalkraft eines Stabs im Ergebnis (Mittel seiner Elemente, Stabende)."""
    werte = [float(np.asarray(res.beam_end[i], float)[6]) for i in elemente if i in res.beam_end]
    return float(np.mean(werte)) if werte else 0.0


def theorie_sperre(model, factors: dict, th: str) -> str:
    """Leer - oder der Grund, warum eine Rechnung nach Theorie ``th``
    ("II"/"III") mit Sollkraeften nicht gefuehrt wird (theorie2, theorie3).

    Den Spannschritt gibt es dort (noch) nicht, und die eingepraegte Dehnung
    der Einflussmatrix nach Theorie I. Ordnung trifft F_soll nach Theorie II./
    III. Ordnung nicht: am Rahmen aus tests/test_vorspannkraft.py (Zugband
    70 kN an einer Kragstuetze HEB 200) gab sie nach Theorie III. Ordnung
    62,56 statt 70 kN (-10,6 %; die eingepraegte Kraft ist dort 11-mal so gross
    wie die Stabkraft, und jede Aenderung der Laenge geht mit diesem Faktor in
    N ein), und nach Theorie II. Ordnung brach die Rechnung an alpha_cr = 0,16 ab -
    die geometrische Steifigkeit liest nur die elastische Normalkraft
    E A Δl/L, nicht die Vorspannung (assemble.geometric_stiffness), und sah
    das Zugband unter 684 kN Druck (gemessen 13.10.2026). Der Lastfall bleibt
    darum nach Theorie I. Ordnung gerechnet und gekennzeichnet.

    Nachgemessen am 14.10.2026, nachdem geometrische Steifigkeit und Theorie
    III. Ordnung die Anfangsdehnung lesen (asm.stab_normalkraft, theorie3):
    mit derselben eingepraegten Kraft (754,08 kN) traegt das Zugband im
    Lastfall nur mit Vorspannung nach Theorie II. Ordnung 69,77 kN (alpha_cr
    136,5) und nach Theorie III. Ordnung 69,57 kN statt 70 kN (-0,33 % und
    -0,61 %; scratchpad sad_werk/sperre_messen.py). Die Rechnung laeuft also,
    trifft F_soll nach dem Verankern aber nicht - dafuer braeuchte es den
    Spannschritt nach Theorie II./III. Ordnung. Die Sperre bleibt."""
    soll = sollkraefte(model, factors)
    if not soll:
        return ""
    staebe = ", ".join(s.stab for s in soll[:6]) + (" …" if len(soll) > 6 else "")
    # bis zum 14.10.2026: „Vorspannkraft (Soll nach Verankerung) in …“
    return (f"Endvorspannung bzw. Anfangsvorspannung (Spannschritt) in {staebe}: nach Theorie {th}. "
            "Ordnung noch nicht gerechnet - es gilt das Ergebnis nach Theorie I. Ordnung mit dem Spannschritt "
            "(Kraft jedes Stabs nach dem Verankern im Ergebnis)")


def _spannzustand(model, system, soll: list, els: dict, workers=None, progress=None,
                  einfrieren=None, fenster=None, probelauf: bool = False) -> dict:
    """Spannen und Verriegeln, Gruppe fuer Gruppe - am System gemerkt (alle
    Lastfaelle mit denselben Sollkraeften teilen den Spannzustand)."""
    from . import solver as sv
    c = _cache(system)
    n_st = spannstufen(model)
    key = ("spannen", tuple(sorted((s.stab, round(float(s.kraft), 6), int(s.gruppe))
                                   + ((round(float(s.schlupf), 12),) if s.schlupf else ()) for s in soll)),
           bool(probelauf), n_st)
    if key in c:
        return c[key]
    t0 = time.time()
    aktiv = getattr(system, "aktiv", None)
    basis = np.ones(len(model.elements), bool) if aktiv is None else np.asarray(aktiv, bool).copy()
    gruppen = sorted({int(s.gruppe) for s in soll})
    P: dict = {}                    # Element -> Verriegelungskraft
    F_lock = np.zeros(model.ndof)
    feq_lock: dict = {}
    n0: dict = {}
    plast = None
    kontakt = None
    spannen = []
    staebe = {s.stab: {"F_soll": float(s.kraft), "gruppe": int(s.gruppe), **_presse_info(model, s, els)}
              for s in soll}
    verankern = []          # der Verankerungsschritt (nur mit Schlupf in der letzten Gruppe)
    reihenfolge = []
    r = None
    u = None
    for g in gruppen:
        jetzt = [s for s in soll if s.gruppe == g]
        reihenfolge.append([s.stab for s in jetzt])
        maske = basis.copy()
        for s in soll:
            if s.gruppe >= g:
                maske[els[s.stab]] = False
        sv._melde(progress, f"Spannschritt Gruppe {g}: "
                            + ", ".join(s.stab for s in jetzt[:8]) + (" …" if len(jetzt) > 8 else "")
                            + " gespannt (Stäbe inaktiv, Kräftepaar F_soll"
                            + (f", in {n_st} Stufen)" if n_st > 1 else ")"))
        sys_s = sv.StaticSystem(model, workers, progress, aktiv=maske,
                                situation=getattr(system, "situation", "") or "")
        F_sp, _feq = _stablast(model, [(s.stab, s.kraft) for s in jetzt], basis)
        vorl = []               # Spannstufen vor der letzten mit nicht konvergiertem Kontakt
        try:
            # n gleiche Stufen (spannstufen); jede vom Kontakt- und plastischen
            # Zustand der vorigen aus, in ihr wirkt ihre Kraft sofort voll (F_S).
            # Mit einer Stufe ist es der Spannschritt bis zum 14.10.2026, Zahl
            # fuer Zahl (1.0 * F_sp ist F_sp)
            for k in range(1, n_st + 1):
                F_k = F_lock + (k / n_st) * F_sp
                zus = {"F": F_k, "feq": dict(feq_lock), "F_S": F_k, "n0": n0,
                       "plast_start": plast, "plast_merken": True, "ohne_grund": True}
                name = f"Spannschritt Gruppe {g}" + (f", Stufe {k}/{n_st}" if n_st > 1 else "")
                if n_st > 1:
                    sv._melde(progress, f"{name}: {100.0 * k / n_st:.4g} % von F_soll".replace(".", ","))
                r = sv._solve_loads(model, sys_s, {}, name, "case", workers,
                                    progress, start=kontakt, probelauf=probelauf,
                                    start_von=None if kontakt is None else "Spannschritt",
                                    zusatz=zus)
                plast = getattr(r, "_plast_ende", None) or plast
                if hasattr(r, "_plast_ende"):
                    del r._plast_ende
                kontakt = getattr(r, "kontaktzustand", None) or kontakt
                if k < n_st and isinstance(r.info.get("vorlaeufig"), dict):
                    vorl.append(f"Spannstufe {k}/{n_st}")
        finally:
            _freigeben(sys_s)
        if vorl:
            # Auch eine fruehere Stufe mit nicht konvergiertem Kontakt macht den
            # Spannzustand vorlaeufig (Entscheidung des Anwenders vom 14.10.2026)
            v = dict(r.info.get("vorlaeufig") or {"grund": "kontakt", "stellen": []})
            v["stellen"] = vorl + list(v.get("stellen") or [])
            v["text"] = f"{sv.VORLAEUFIG} in " + ", ".join(v["stellen"])
            r.info["vorlaeufig"] = v
        u = _u_voll(model, r)
        # im Spannzustand tragen die gespannten Staebe das Kraeftepaar F_soll
        for s in jetzt:
            for i in els[s.stab]:
                r.beam_end[i] = _stabend(s.kraft)
            staebe[s.stab]["N_spannen"] = float(s.kraft)
        r.info["zustand"] = "spannen"
        r.info["gruppe"] = int(g)
        r._cache.clear()
        spannen.append(r)
        # Verriegeln in der verformten Lage: N = N_el(u_S) + P = F_soll, bei
        # der Anfangsvorspannung P0 − k_A Δs (der Schlupf, 14.10.2026)
        for s in jetzt:
            T = _ziel(model, s, els)[0]
            for i in els[s.stab]:
                P[i] = T - _n_elastisch(model, i, u)
        F_lock, feq_lock = _verriegelung(model, P)
        n0 = _n0_ausfall(model, P)
    if any(s.schlupf for s in jetzt):
        # Verankerungsschritt: mit Schlupf ist u_S kein Gleichgewicht mehr - die
        # Umgebung federt zurueck. Gerechnet am System des Lastfalls (alle Staebe
        # wirksam) mit Kontakt und Plastizitaet vom Spannzustand aus; frueher
        # gespannte Gruppen gleicht der naechste Spannschritt ohnehin aus
        zus = {"F": F_lock, "feq": dict(feq_lock), "F_S": F_lock, "n0": n0,
               "plast_start": plast, "plast_merken": True, "ohne_grund": True}
        sv._melde(progress, "Verankern: Verankerungsschlupf, die Umgebung federt zurück")
        r = sv._solve_loads(model, system, {}, "Verankern", "case", workers, progress, start=kontakt,
                            probelauf=probelauf, start_von=None if kontakt is None else "Spannschritt",
                            zusatz=zus)
        plast = getattr(r, "_plast_ende", None) or plast
        if hasattr(r, "_plast_ende"):
            del r._plast_ende
        kontakt = getattr(r, "kontaktzustand", None) or kontakt
        u = _u_voll(model, r)
        verankern.append(r)
    # verankert: die Lage des letzten Spannschritts, alle Staebe verriegelt
    v = copy.copy(r)
    v.beam_end = dict(r.beam_end)
    v.info = dict(r.info)
    v._cache = {}
    v.info["zustand"] = "verankert"
    v.info.pop("gruppe", None)
    v.name = "Vorspannung verankert"
    alle = {i for s in soll for i in els[s.stab]}
    if "inaktiv" in v.info:
        v.info["inaktiv"] = [i for i in v.info["inaktiv"] if i not in alle]
    for s in soll:
        N = []
        for i in els[s.stab]:
            n = _n_elastisch(model, i, u) + P[i]
            v.beam_end[i] = _stabend(n)
            N.append(n)
        nv = float(np.mean(N))
        staebe[s.stab].update({"N_verankert": nv, "verlust": float(s.kraft) - nv,
                               "P_verriegelt": float(np.mean([P[i] for i in els[s.stab]]))})
    z = {"F": F_lock, "feq": feq_lock, "n0": n0, "plast": plast, "kontakt": kontakt,
         "spannen": spannen, "verankert": v, "staebe": staebe, "reihenfolge": reihenfolge,
         "zeit": time.time() - t0, "spannstufen": n_st, "verankern": verankern}
    c[key] = z
    return z


def _stabend(N: float) -> np.ndarray:
    """Lokale Stabendkraefte (12,) eines Stabs, der nur die Normalkraft N traegt."""
    f = np.zeros(12)
    f[0] = -float(N)
    f[6] = float(N)
    return f


def _freigeben(system) -> None:
    """Die Zerlegungen eines Hilfssystems zurueckgeben (PARDISO haelt sie
    ausserhalb von Python, siehe solver.LinearSolver.freigeben)."""
    try:
        system.kontakt_loeser_freigeben()
    except Exception:                       # noqa: BLE001 - Aufraeumen sperrt nie
        pass
    ls = getattr(system, "_solver", None)
    if ls is not None and hasattr(ls, "freigeben"):
        try:
            ls.freigeben()
        except Exception:                   # noqa: BLE001
            pass
    system._solver = None


# --------------------------------------------------------------------------
# Import: RFEM-Vorspannung als eingepraegte Dehnung (Temperatur) -> Hinweis und Umwandlung
# --------------------------------------------------------------------------
@dataclass
class TempVorspannung:
    """Eine Vorspannung, die als Temperatur im Stab steht (RFEM-Import:
    dT = −N0/(E A α)) - je Lastfall und Stab."""
    fall: str
    stab: str
    N0: float
    E: float
    alpha: float
    A: float
    lasten: list = field(default_factory=list)      # die TempLoads


def temperatur_vorspannungen(model, faelle=None, staebe=None) -> list:
    """Die Vorspannungen, die als Temperatur auf einem Zugstab stehen - so
    legt der RFEM-Import die Vorspannung als eingepraegte Dehnung an (TempLoad.vorspannkraft).
    Ein Stab zaehlt nur, wenn alle seine Elemente dieselbe Kraft tragen."""
    el_stab = {}
    for name, mem in (getattr(model, "members", None) or {}).items():
        for e in mem.elements:
            el_stab[int(e)] = name
    out = []
    for fall, lc in (getattr(model, "load_cases", None) or {}).items():
        if faelle is not None and fall not in faelle:
            continue
        je: dict = {}
        for tl in lc.eigene("temp_loads"):
            if tl.dT_z:
                continue
            N = tl.vorspannkraft(model)
            stab = el_stab.get(int(tl.elem))
            if abs(N) <= 1.0 or stab is None or (staebe is not None and stab not in staebe):
                continue
            je.setdefault(stab, []).append((tl, N))
        for stab, liste in je.items():
            alle = set(_elemente(model, stab))
            if {int(t.elem) for t, _n in liste} != alle:
                continue
            Ns = [n for _t, n in liste]
            if max(Ns) - min(Ns) > 1e-6 * max(abs(x) for x in Ns):
                continue
            e = model.elements[int(liste[0][0].elem)]
            mat, sec = model.materials[e.mat], model.sections[e.sec]
            # auf 1 mN gerundet: N0 kommt aus dT = -N0/(E A alpha) zurueck (120 kN -> 119999,99999999999 N)
            out.append(TempVorspannung(fall, stab, round(float(np.mean(Ns)), 3), float(mat.E),
                                       float(mat.alpha or 1.2e-5), float(sec.A),
                                       [t for t, _n in liste]))
    return out


def x_rechenbar(model) -> str:
    """Leer, wenn die Kraft nach elastischer Verkuerzung linear gerechnet
    werden kann - sonst der Grund, warum sie nach der ersten Rechnung folgt."""
    if getattr(model, "has_contact", False):
        return "das Modell hat Kontakt"
    ohne = [k for k, x in (getattr(model, "koerper", None) or {}).items() if not getattr(x, "elemente", None)]
    if ohne:
        return f"{len(ohne)} Volumenkörper sind noch nicht vernetzt"
    if model.ndof > X_FHG_GRENZE:
        return f"{model.ndof} Freiheitsgrade (eine Zerlegung beim Import erst bis {X_FHG_GRENZE})"
    return ""


def elastische_verkuerzung(model, eintraege: list, system=None) -> dict:
    """{(Lastfall, Stab): X} - die Stabkraft unter der Vorspannung allein,
    linear gerechnet ueber die Einflussmatrix (eine Zerlegung, je Stab eine
    Loesung). Leer, wenn das Modell dafuer nicht linear rechenbar ist."""
    if not eintraege or x_rechenbar(model):
        return {}
    from . import solver as sv
    if system is None:
        system = sv.StaticSystem(model)
    je_fall: dict = {}
    for t in eintraege:
        je_fall.setdefault(t.fall, []).append(t)
    out = {}
    for fall, liste in je_fall.items():
        staebe = [t.stab for t in liste]
        A = einflussmatrix(model, system, staebe)
        X = A @ np.array([t.N0 for t in liste], float)
        for t, x in zip(liste, X):
            out[(fall, t.stab)] = float(x)
    return out


def _kn(x: float) -> str:
    from .zahlen import zahl_text
    return zahl_text(round(float(x) / 1e3, 1))


#: Schluss des Importhinweises und Vermerk an den Lastfaellen (Nachtrag des
#: Anwenders vom 15.10.2026: „beim import des modells und der lastfälle einen
#: hinweis an den user, dass der wert von rfem übernommen wurde und in statik3d
#: zu prüfen und ggf anzupassen ist“)
RFEM_PRUEFEN = ("in Statik3D prüfen und ggf. als Anfangsvorspannung (Pressenkraft) oder Endvorspannung "
                "anpassen")
VERMERK_RFEM = "aus RFEM übernommen – prüfen"


def rfem_hinweis_text(N0: float, staebe, faelle, umrechnung: str = "", X=None, grund: str = "",
                      X_aus=None) -> str:
    """„Vorspannung 952 kN an S1–S16 in 129 Lastfällen aus RFEM übernommen
    (als eingeprägte Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K; nach
    elastischer Verkürzung X kN) – in Statik3D prüfen und ggf. als
    Anfangsvorspannung (Pressenkraft) oder Endvorspannung anpassen“ - je
    Vorspannungswert ein Hinweis (seit 15.10.2026). X ist ein Wert, eine
    Spanne (min, max) oder None; dann sagt ``grund``, warum es erst nach der
    ersten Rechnung folgt.

    Bis zum 15.10.2026 lautete der Hinweis „Vorspannung als eingeprägte
    Dehnung (RFEM) 952 kN ergibt nach elastischer Verkürzung X kN – in
    Endvorspannung umwandeln?“ mit Umfang und Umrechnung in Klammern dahinter,
    bis zum 14.10.2026 „Anfangsvorspannung 952 kN ergibt … – in Sollkraft
    umwandeln?“."""
    from .importers.schraubenhinweis import _bereiche
    n = len(list(faelle or []))
    teile = []
    if umrechnung:
        teile.append("als " + umrechnung)
    if X is not None:
        lo, hi = (_kn(min(X)), _kn(max(X))) if isinstance(X, (tuple, list)) else (_kn(X), _kn(X))
        x = f"{lo} kN" if lo == hi else f"{lo} bis {hi} kN"
        aus = list(X_aus or [])
        teile.append(f"nach elastischer Verkürzung {x}"
                     + (f", aus {', '.join(aus[:3])}{' …' if len(aus) > 3 else ''}" if aus else ""))
    elif grund:
        teile.append("die Kraft nach elastischer Verkürzung folgt nach der ersten Rechnung eines Lastfalls "
                     f"nur mit der Vorspannung: {grund}")
    return (f"Vorspannung {_kn(N0)} kN an {_bereiche(staebe or [])} in {n} {'Lastfall' if n == 1 else 'Lastfällen'} "
            "aus RFEM übernommen" + (f" ({'; '.join(teile)})" if teile else "") + f" – {RFEM_PRUEFEN}")


def hinweis_anzeige(model, h: dict) -> str:
    """Der Text eines Importhinweises zur Vorspannung in der Form vom
    15.10.2026 - auch fuer einen Hinweis, den eine aeltere Datei in der alten
    Form traegt. Der gespeicherte Hinweis bleibt, wie er ist (die Datei bleibt
    beim Speichern bitgleich)."""
    umrechnung = h.get("umrechnung")
    if umrechnung is None:
        t = next((t for t in temperatur_vorspannungen(model, h.get("faelle"), h.get("objekte"))
                  if round(t.N0, 3) == round(float(h.get("N0", 0.0)), 3)), None)
        umrechnung = t.lasten[0].vorspann_umrechnung_text(model=model) if t is not None else ""
    grund = h.get("grund")
    if grund is None and h.get("X") is None:
        grund = x_rechenbar(model) or "noch nicht gerechnet"
    return rfem_hinweis_text(float(h.get("N0", 0.0)), h.get("objekte") or [], h.get("faelle") or [],
                             umrechnung, h.get("X"), grund or "", h.get("X_aus"))


#: Merkmale in ``model.meta``, die der RFEM-6-Import seit dem 14.10.2026 setzt
#: (rfem6_db.ZUGSTAEBE_MERKMAL, SEILE_MERKMAL, LAGERREIBUNG_MERKMAL). Der
#: Import hielt die Vorspannung schon seit dem 13.10.2026 mit Merkmal fest.
MERKMALE_NEUER_IMPORT = ("rfem_zugstaebe", "rfem_seile", "rfem_lagerreibung")

#: Was der Anwender mit einer aus RFEM uebernommenen Vorspannung als eingepraegter
#: Dehnung tun kann (Protokoll, Statuszeile, Vorschlag am Hinweis; 15.10.2026)
WEG_UMSTELLEN = (f"Lasten › Vorspannung, Lastart „{LASTART_UMWANDELN}“ stellt sie auf die Endvorspannung um, "
                 f"mit „{LASTART_PRESSE}“ und Δs setzen Sie stattdessen die Pressenkraft; umgestellt wird nur auf "
                 "Ihre Anweisung")
#: Zusatz bei einer aus ΔT abgeleiteten Vorspannung: die alte Datei kennt die Herkunft nicht
HERKUNFT_UNSICHER = ("; die Datei hat die Herkunft nicht gespeichert: eine Abkühlung eines Zugstabs ist von einer "
                     "Vorspannung nicht zu unterscheiden – ist es eine echte Temperaturlast, bleibt sie, wie sie ist")

#: Vermerk in der Klammer eines Hinweises, dessen Kraft aus ΔT abgeleitet ist
#: (Datei von vor dem 13.10.2026 ohne gespeichertes Merkmal)
AUS_DT = "aus ΔT abgeleitet"


def abgeleitete_hinweise(model) -> list:
    """Hinweise fuer ein Modell, das vor dem 13.10.2026 aus RFEM uebernommen
    wurde (Quelle eine .rf6-Datei, kein Importhinweis zur Vorspannung): die
    Vorspannungen, die dort noch als ΔT an Zug- oder Seilstaeben stehen
    (TempLoad.vorspann_werte bzw. vorspannkraft), gebuendelt je Wert wie beim
    Import - mit „aus ΔT abgeleitet“ in der Klammer, wenn kein gespeichertes
    Merkmal da ist. X wird beim Oeffnen nicht gerechnet. Die Hinweise haengen
    nur am geoeffneten Modell (``model._rfem_hinweise_abgeleitet``), die Datei
    aendert sich nicht (Auftrag vom 15.10.2026: der Anwender arbeitet mit
    einem solchen gespeicherten Drehlager)."""
    meta = getattr(model, "meta", None) or {}
    if not str(meta.get("quelle", "") or "").lower().endswith(".rf6"):
        return []
    if any(h.get("art") == "vorspannung" for h in (getattr(model, "importhinweise", None) or [])):
        return []
    # Ein Import ab dem 14.10.2026 setzt Merkmale ans Modell (Zugstaebe, Seile,
    # Lagerreibung) und haelt jede Vorspannung mit ihrem Merkmal an der ΔT-Last
    # fest: dort ist eine ΔT ohne Merkmal eine echte Temperaturlast, keine
    # Vorspannung (15.10.2026). Nur eine Datei ohne diese Merkmale kann eine
    # Vorspannung als blosse ΔT tragen.
    if any(meta.get(k) for k in MERKMALE_NEUER_IMPORT):
        return []
    je: dict = {}
    for t in temperatur_vorspannungen(model):
        je.setdefault(round(t.N0, 3), []).append(t)
    grund = x_rechenbar(model) or "beim Öffnen nicht gerechnet"
    out = []
    for N0, liste in sorted(je.items(), key=lambda kv: -kv[0]):
        staebe = sorted({t.stab for t in liste})
        faelle = sorted({t.fall for t in liste})
        l0 = liste[0].lasten[0]
        umrechnung = l0.vorspann_umrechnung_text(model=model)
        if not all(getattr(x, "aus_vorspannung", 0.0) for t in liste for x in t.lasten):
            umrechnung += ", " + AUS_DT
        h = {"art": "vorspannung", "abgeleitet": True, "objekte": staebe, "faelle": faelle,
             "N0": float(N0), "umrechnung": umrechnung, "grund": grund, "X": None, "erledigt": False,
             "vorschlag": WEG_UMSTELLEN + HERKUNFT_UNSICHER}
        h["text"] = rfem_hinweis_text(N0, staebe, faelle, umrechnung, None, grund)
        out.append(h)
    return out


def _rfem_hinweise(model) -> list:
    """Die Hinweise zur Vorspannung aus RFEM: gespeicherte Importhinweise und
    die beim Oeffnen abgeleiteten (:func:`abgeleitete_hinweise`)."""
    return ([h for h in (getattr(model, "importhinweise", None) or []) if h.get("art") == "vorspannung"]
            + list(getattr(model, "_rfem_hinweise_abgeleitet", None) or []))


def vorspannung_ladehinweise(model) -> list:
    """Zeilen fuers Protokoll beim Oeffnen (Model._geoeffnet): die offenen
    Importhinweise zur Vorspannung aus RFEM (seit 15.10.2026), bei einem vor
    dem 13.10.2026 uebernommenen Modell die abgeleiteten - die setzt diese
    Funktion ans Modell (nicht in die Datei)."""
    model._rfem_hinweise_abgeleitet = abgeleitete_hinweise(model)
    offen = [h for h in _rfem_hinweise(model) if not h.get("erledigt")]
    out = [h["text"] if h.get("abgeleitet") else hinweis_anzeige(model, h) for h in offen]
    if offen:
        # eine Zeile mit dem Weg, einmal fuer alle Hinweise (15.10.2026); bei einer
        # abgeleiteten Vorspannung dazu, dass die Herkunft nicht sicher ist
        out.append(f"Vorspannung als eingeprägte Dehnung (ΔT): {WEG_UMSTELLEN}"
                   + (HERKUNFT_UNSICHER if any(h.get("abgeleitet") for h in offen) else ""))
    return out


def rfem_pruefen(model) -> dict:
    """{Lastfall: Hinweistext} - die Lastfaelle, in denen eine aus RFEM
    uebernommene Vorspannung noch als eingepraegte Dehnung steht und ihr
    Importhinweis offen ist (Vermerk „aus RFEM übernommen – prüfen“ in
    Lastfallmaske und Lasttabelle, 15.10.2026). Ist sie umgewandelt oder von
    Hand ersetzt, faellt der Lastfall heraus."""
    out: dict = {}
    lcs = getattr(model, "load_cases", None) or {}
    for h in _rfem_hinweise(model):
        if h.get("erledigt"):
            continue
        for f in h.get("faelle") or []:
            lc = lcs.get(f)
            if f in out or lc is None:
                continue
            if any(getattr(t, "aus_vorspannung", 0.0) or t.vorspannkraft(model) > 1.0
                   for t in (lc.temp_loads or []) if not t.dT_z):
                out[f] = str(h.get("text", ""))
    return out


def import_hinweise(model, log: list = None, system=None) -> list:
    """Nach dem Import: je Vorspannung als eingepraegte Dehnung (gleiche Kraft N0) ein Hinweis
    mit der Kraft X nach elastischer Verkuerzung, ins Protokoll und als
    Importhinweis ans Modell. Umgewandelt wird nichts - das loest der Anwender
    aus (:func:`in_sollkraft_umwandeln`). Rueckgabe die Hinweise."""
    eintraege = temperatur_vorspannungen(model)
    if not eintraege:
        return []
    grund = x_rechenbar(model)
    t0 = time.time()
    X = {}
    if not grund:
        try:
            X = elastische_verkuerzung(model, eintraege, system)
        except Exception as ex:             # noqa: BLE001 - der Hinweis kommt trotzdem
            grund = f"lineare Rechnung nicht möglich ({type(ex).__name__}: {str(ex)[:120]})"
    zeit = time.time() - t0
    je: dict = {}
    for t in eintraege:
        je.setdefault(round(t.N0, 3), []).append(t)
    out = []
    for N0, liste in sorted(je.items(), key=lambda kv: -kv[0]):
        xs = [X[(t.fall, t.stab)] for t in liste if (t.fall, t.stab) in X]
        staebe = sorted({t.stab for t in liste})
        faelle = sorted({t.fall for t in liste})
        t0_ = liste[0]
        umrechnung = t0_.lasten[0].vorspann_umrechnung_text(model=model)
        Xw = [float(min(xs)), float(max(xs))] if xs else None
        # seit 15.10.2026 ein Satz: Wert, Staebe, Lastfaelle, Umrechnung, X und
        # „in Statik3D prüfen …“ (rfem_hinweis_text); die Rechenzeit von X
        # steht nur noch im Hinweis (``zeit_X``), nicht im Text
        umfang = (f"{len(staebe)} {'Stab' if len(staebe) == 1 else 'Stäbe'} in {len(faelle)} "
                  f"{'Lastfall' if len(faelle) == 1 else 'Lastfällen'}")
        h = {"art": "vorspannung",
             "text": rfem_hinweis_text(N0, staebe, faelle, umrechnung, Xw, "" if xs else grund),
             "objekte": staebe, "umfang": umfang, "umrechnung": umrechnung, "grund": "" if xs else grund,
             "vorschlag": "prüfen und ggf. anpassen: Lasten › Vorspannung, Lastart "
                          f"„{LASTART_PRESSE}“ oder „{LASTART_ENDE}“, oder umwandeln mit "
                          f"„{LASTART_UMWANDELN}“",
             "erledigt": False, "N0": float(N0), "faelle": faelle, "X": Xw}
        if xs:
            h["zeit_X"] = round(zeit, 2)
        out.append(h)
        if log is not None:
            log.append("  HINWEIS: " + h["text"])
    alt = [x for x in (getattr(model, "importhinweise", None) or []) if x.get("art") != "vorspannung"]
    model.importhinweise = alt + out
    return out


def _nur_vorspannung(model, lc) -> bool:
    """Traegt der Lastfall nichts als Temperatur-Vorspannungen auf Zugstaeben?"""
    if any(float(x) for x in (lc.gravity or [])) or getattr(lc, "grundlast", False):
        return False
    for liste in ("nodal_loads", "beam_loads", "face_loads", "geometrielasten", "linienlasten",
                  "zwangsverformungen", "vorspannungen", "uebermasse"):
        if getattr(lc, liste, None):
            return False
    tl = list(lc.temp_loads or [])
    return bool(tl) and all(abs(t.vorspannkraft(model)) > 1.0 and not t.dT_z for t in tl)


def hinweise_nachreichen(model, ergebnisse: dict) -> list:
    """Nach einer Rechnung (solver.solve_all): die Kraft X nach elastischer
    Verkuerzung fuer die Importhinweise, die sie beim Import nicht rechnen
    konnten (Kontakt, Groesse) - aus den Ergebnissen der Lastfaelle, die nur
    diese Vorspannung tragen (am Drehlager LF398). Rueckgabe die neuen
    Hinweistexte (leer, wenn nichts nachzureichen war)."""
    offen = [h for h in (getattr(model, "importhinweise", None) or [])
             if h.get("art") == "vorspannung" and h.get("X") is None and not h.get("erledigt")]
    if not offen or not ergebnisse:
        return []
    je_N0: dict = {}
    for t in temperatur_vorspannungen(model):
        lc = model.load_cases.get(t.fall)
        res = ergebnisse.get(t.fall)
        if lc is None or res is None or not _nur_vorspannung(model, lc):
            continue
        els = _elemente(model, t.stab)
        if not els or any(i not in res.beam_end for i in els):
            continue
        je_N0.setdefault(round(t.N0, 3), []).append((t.fall, _n_ergebnis(res, els)))
    texte = []
    for h in offen:
        werte = je_N0.get(round(float(h.get("N0", 0.0)), 3))
        if not werte:
            continue
        xs = [x for _f, x in werte]
        faelle = sorted({f for f, _x in werte})
        h["X"] = [float(min(xs)), float(max(xs))]
        h["X_aus"] = faelle
        h["text"] = hinweis_anzeige(model, h)
        texte.append(h["text"])
    return texte


def ist_spannstahl(model, mat_name: str) -> bool:
    """Spannstahl ist ein Werkstoff der Art „Spannstahl“ (``Material.art``,
    plast/verfestigung) - dieselbe Frage wie im Stabnachweis
    (:func:`statik3d.ec3.spannstahl.ist_spannstahl`). Der RFEM-Import setzt die
    Art (Werkstofftyp 15 oder f_p0,1k statt f_y), sonst der Anwender in der
    Werkstoffmaske. Bis zur Zusammenfuehrung am 14.10.2026 las die Umwandlung
    eine eigene Kennzeichnung des Imports (``model.meta["spannstahl"]``) und
    den Werkstoffnamen (St 835/1030, Y1860 ...); ein Werkstoff ohne Art, der
    nur so heisst, bekommt jetzt den RFEM-Wert als Vorschlag, und das
    Protokoll nennt ihn beim Oeffnen (ec3.spannstahl.ladehinweise)."""
    from .ec3.spannstahl import ist_spannstahl as _art_spannstahl
    return _art_spannstahl((getattr(model, "materials", None) or {}).get(str(mat_name)))


def vorschlag_sollkraft(model, stab: str, N0: float) -> float:
    """Vorgeschlagene Sollkraft: 0,9·f_p0,1k·A bei Spannstahl (f_p0,1k = f_y des
    Werkstoffs, so liest der Import ihn), sonst der RFEM-Wert N0."""
    el = _elemente(model, stab)
    if el:
        e = model.elements[el[0]]
        mat, sec = model.materials.get(e.mat), model.sections.get(e.sec)
        if mat is not None and sec is not None and mat.fy and ist_spannstahl(model, mat.name):
            return 0.9 * float(mat.fy) * float(sec.A)
    return float(N0)


def in_sollkraft_umwandeln(model, staebe=None, faelle=None, kraft: float = None, gruppe: int = 1,
                           N0=None) -> int:
    """Die Temperatur-Vorspannung der Staebe (alle, wenn None) in den
    Lastfaellen (alle, wenn None) auf die Lastart „Vorspannkraft (Soll nach
    Verankerung)“ umstellen: die ΔT-Lasten des Stabs fallen weg, an ihre Stelle
    tritt die Sollkraft - ``kraft`` [N] oder der Vorschlag
    (:func:`vorschlag_sollkraft`). ``N0``: nur Vorspannungen mit diesen
    Kraeften [N] (am Drehlager 952 kN, nicht die 805 kN des Zeitpunkts 1).
    Rueckgabe: Zahl der umgestellten (Lastfall, Stab)-Paare. Nur auf
    Anweisung des Anwenders."""
    def passt(x):
        return N0 is None or any(abs(x - float(y)) <= 1e-6 * max(abs(float(y)), 1.0) for y in N0)
    n = 0
    for t in temperatur_vorspannungen(model, faelle, staebe):
        if not passt(t.N0):
            continue
        lc = model.load_cases[t.fall]
        weg_ = {id(x) for x in t.lasten}
        lc.temp_loads = [x for x in lc.temp_loads if id(x) not in weg_]
        F = float(kraft) if kraft is not None else vorschlag_sollkraft(model, t.stab, t.N0)
        lc.vorspannungen.append(Vorspannung(
            t.stab, "stab", F, None,
            f"umgewandelt aus Vorspannung als eingeprägte Dehnung (RFEM) {_kn(t.N0)} kN "
            f"(ΔT {t.lasten[0].dT:.3f} K)",
            True, int(gruppe or 1)))
        n += 1
    if n:
        rest = {round(t.N0, 3) for t in temperatur_vorspannungen(model)}
        for h in (getattr(model, "importhinweise", None) or []):
            if h.get("art") == "vorspannung" and round(float(h.get("N0", 0.0)), 3) not in rest:
                h["erledigt"] = True
    return n
