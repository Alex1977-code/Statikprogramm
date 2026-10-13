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

**Import**: :func:`import_hinweise` nennt je Anfangsvorspannung die Kraft X
nach elastischer Verkuerzung (linear, Einflussmatrix), :func:`in_sollkraft_umwandeln`
stellt die ΔT-Last auf die Sollkraft um - nur auf Anweisung des Anwenders.
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

#: Spannstahl am Namen des Werkstoffs (der RFEM-Import kennzeichnet ihn
#: zusaetzlich in model.meta["spannstahl"], wenn die Datei f_p0,1k fuehrt)
SPANNSTAHL_NAMEN = ("spannstahl", "y1030", "y1050", "y1100", "y1230", "y1770", "y1860",
                    "st 835/1030", "st 950/1050", "st 1080/1230", "st 1470/1670", "st 1570/1770")


@dataclass
class Soll:
    """Eine Sollkraft eines Lastfalls oder einer Kombination (mit Faktor)."""
    stab: str
    kraft: float
    gruppe: int = 1


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
            k, g = je.get(v.ziel, (0.0, None))
            gv = int(getattr(v, "gruppe", 1) or 1)
            je[v.ziel] = (k + float(f) * float(v.kraft), gv if g is None else min(g, gv))
    return [Soll(s, k, g) for s, (k, g) in je.items() if k]


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
    Anfangsdehnung, Temperatur oder Verriegelung (die zaehlt der Aufrufer)."""
    e = model.elements[i]
    kl, _T3, T, _L = asm.beam_local(model, e)
    ul = T @ np.asarray(u, float)[asm.element_dofs(e, model)[:12]]
    A = asm.beam_versatz(e)
    if A is not None:
        ul = A @ ul
    return float((kl @ ul)[6])


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
        F_v, feq_v = _stablast(model, list(zip(staebe, P)), aktiv)
        sv._melde(progress, f"{name}: Vorspannkraft (Soll nach Verankerung) über die Einflussmatrix "
                            f"({len(staebe)} {'Stab' if len(staebe) == 1 else 'Stäbe'})")
        res = sv._solve_loads(model, system, factors, name, kind, start=start, start_von=start_von,
                              zusatz={"F": F_v, "feq": feq_v, "F_S": F_v}, **kw)
        N_v = A @ P
        info = {"weg": WEG_EINFLUSS, "reihenfolge": [staebe], "staebe": {}}
        for k, s in enumerate(soll):
            info["staebe"][s.stab] = {"F_soll": float(s.kraft), "gruppe": int(s.gruppe),
                                      "N_verankert": float(N_v[k]),
                                      "verlust": float(s.kraft - N_v[k]),
                                      "P_eingepraegt": float(P[k]),
                                      "N_ende": _n_ergebnis(res, els[s.stab])}
        res.info["vorspannung"] = info
        return res
    z = _spannzustand(model, system, soll, els, **kw)
    zusatz = {"F": z["F"], "feq": z["feq"], "F_S": z["F"], "n0": z["n0"], "plast_start": z["plast"]}
    st = z["kontakt"] if z["kontakt"] is not None else start
    res = sv._solve_loads(model, system, factors, name, kind, start=st,
                          start_von="Spannschritt" if z["kontakt"] is not None else start_von,
                          zusatz=zusatz, **kw)
    info = {"weg": WEG_SPANNEN, "reihenfolge": [list(g) for g in z["reihenfolge"]], "staebe": {},
            "zustaende": ["spannen", "verankert"], "zeit_spannen": float(z["zeit"])}
    for s in soll:
        d = dict(z["staebe"][s.stab])
        d["N_ende"] = _n_ergebnis(res, els[s.stab])
        info["staebe"][s.stab] = d
    res.info["vorspannung"] = info
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
    darum nach Theorie I. Ordnung gerechnet und gekennzeichnet."""
    soll = sollkraefte(model, factors)
    if not soll:
        return ""
    staebe = ", ".join(s.stab for s in soll[:6]) + (" …" if len(soll) > 6 else "")
    return (f"Vorspannkraft (Soll nach Verankerung) in {staebe}: nach Theorie {th}. Ordnung noch nicht "
            "gerechnet - es gilt das Ergebnis nach Theorie I. Ordnung, in dem jeder Stab nach dem "
            "Verankern F_soll trägt")


def _spannzustand(model, system, soll: list, els: dict, workers=None, progress=None,
                  einfrieren=None, fenster=None, probelauf: bool = False) -> dict:
    """Spannen und Verriegeln, Gruppe fuer Gruppe - am System gemerkt (alle
    Lastfaelle mit denselben Sollkraeften teilen den Spannzustand)."""
    from . import solver as sv
    c = _cache(system)
    key = ("spannen", tuple(sorted((s.stab, round(float(s.kraft), 6), int(s.gruppe)) for s in soll)),
           bool(probelauf))
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
    staebe = {s.stab: {"F_soll": float(s.kraft), "gruppe": int(s.gruppe)} for s in soll}
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
                            + " gespannt (Stäbe inaktiv, Kräftepaar F_soll)")
        sys_s = sv.StaticSystem(model, workers, progress, aktiv=maske,
                                situation=getattr(system, "situation", "") or "")
        F_sp, _feq = _stablast(model, [(s.stab, s.kraft) for s in jetzt], basis)
        zus = {"F": F_lock + F_sp, "feq": dict(feq_lock), "F_S": F_lock + F_sp, "n0": n0,
               "plast_start": plast, "plast_merken": True, "ohne_grund": True}
        try:
            r = sv._solve_loads(model, sys_s, {}, f"Spannschritt Gruppe {g}", "case", workers,
                                progress, start=kontakt, probelauf=probelauf,
                                start_von=None if kontakt is None else "Spannschritt",
                                zusatz=zus)
        finally:
            _freigeben(sys_s)
        u = _u_voll(model, r)
        plast = getattr(r, "_plast_ende", None) or plast
        if hasattr(r, "_plast_ende"):
            del r._plast_ende
        kontakt = getattr(r, "kontaktzustand", None) or kontakt
        # im Spannzustand tragen die gespannten Staebe das Kraeftepaar F_soll
        for s in jetzt:
            for i in els[s.stab]:
                r.beam_end[i] = _stabend(s.kraft)
            staebe[s.stab]["N_spannen"] = float(s.kraft)
        r.info["zustand"] = "spannen"
        r.info["gruppe"] = int(g)
        r._cache.clear()
        spannen.append(r)
        # Verriegeln in der verformten Lage: N = N_el(u_S) + P = F_soll
        for s in jetzt:
            for i in els[s.stab]:
                P[i] = float(s.kraft) - _n_elastisch(model, i, u)
        F_lock, feq_lock = _verriegelung(model, P)
        n0 = _n0_ausfall(model, P)
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
         "zeit": time.time() - t0}
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
# Import: Anfangsvorspannung als Temperatur -> Hinweis und Umwandlung
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
    legt der RFEM-Import die Anfangsvorspannung an (TempLoad.vorspannkraft).
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


def hinweis_text(N0: float, X=None) -> str:
    """„Anfangsvorspannung 952 kN ergibt nach elastischer Verkürzung X kN – in
    Sollkraft umwandeln?“ - X ein Wert, eine Spanne (min, max) oder None
    (dann folgt er nach der ersten Rechnung)."""
    if X is None:
        x = "X kN (folgt nach der ersten Rechnung eines Lastfalls nur mit der Vorspannung)"
    elif isinstance(X, (tuple, list)):
        lo, hi = _kn(min(X)), _kn(max(X))
        x = f"{lo} kN" if lo == hi else f"{lo} bis {hi} kN"
    else:
        x = f"{_kn(X)} kN"
    return f"Anfangsvorspannung {_kn(N0)} kN ergibt nach elastischer Verkürzung {x} – in Sollkraft umwandeln?"


def import_hinweise(model, log: list = None, system=None) -> list:
    """Nach dem Import: je Anfangsvorspannung (gleiche Kraft N0) ein Hinweis
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
        text = hinweis_text(N0, (min(xs), max(xs)) if xs else None)
        staebe = sorted({t.stab for t in liste})
        faelle = sorted({t.fall for t in liste})
        t0_ = liste[0]
        umfang = (f"{len(staebe)} {'Stab' if len(staebe) == 1 else 'Stäbe'} in {len(faelle)} "
                  f"{'Lastfall' if len(faelle) == 1 else 'Lastfällen'}; als ΔT gerechnet "
                  f"{t0_.lasten[0].vorspanntext(model)}")
        zusatz = (f"X nach der ersten Rechnung: {grund}" if not xs and grund else
                  f"X linear in {zeit:.2f} s" if xs else "")
        h = {"art": "vorspannung", "text": f"{text} ({umfang}" + (f"; {zusatz}" if zusatz else "") + ")",
             "objekte": staebe, "umfang": umfang,
             "vorschlag": "in Sollkraft umwandeln: Lasten › Vorspannung, Lastart "
                          "„ΔT-Vorspannung in Sollkraft umwandeln“",
             "erledigt": False, "N0": float(N0), "faelle": faelle,
             "X": [float(min(xs)), float(max(xs))] if xs else None}
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
        quelle = "X aus " + ", ".join(faelle[:3]) + (" …" if len(faelle) > 3 else "")
        umfang = str(h.get("umfang", "") or "")
        h["text"] = (hinweis_text(float(h["N0"]), (min(xs), max(xs)))
                     + f" ({umfang + '; ' if umfang else ''}{quelle})")
        texte.append(h["text"])
    return texte


def ist_spannstahl(model, mat_name: str) -> bool:
    """Spannstahl: vom RFEM-Import gekennzeichnet (model.meta["spannstahl"],
    Werkstoff mit f_p0,1k) oder am Namen erkannt (:data:`SPANNSTAHL_NAMEN`)."""
    if str(mat_name) in ((getattr(model, "meta", None) or {}).get("spannstahl") or []):
        return True
    n = str(mat_name).lower()
    return any(k in n for k in SPANNSTAHL_NAMEN)


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
            f"umgewandelt aus Anfangsvorspannung {_kn(t.N0)} kN (ΔT {t.lasten[0].dT:.3f} K)",
            True, int(gruppe or 1)))
        n += 1
    if n:
        rest = {round(t.N0, 3) for t in temperatur_vorspannungen(model)}
        for h in (getattr(model, "importhinweise", None) or []):
            if h.get("art") == "vorspannung" and round(float(h.get("N0", 0.0)), 3) not in rest:
                h["erledigt"] = True
    return n
