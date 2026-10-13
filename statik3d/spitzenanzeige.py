"""Netzabhaengige Spannungsspitzen zeigen (Plan Singularitaeten vom 10.10.2026, Paket 2).

Paket 1 (:mod:`statik3d.spitzenstellen`) kennzeichnet je Ergebnis die
Stellen, an denen Kraft ohne Flaeche in ein Volumen geht, mit Kraft, Zone und
Spitze in ``res.info["spitzenstellen"]``. **Gekennzeichnet** werden nach der
Entscheidung des Anwenders vom 10.10.2026 nur die auffaelligen Stellen
(sigma_v >= 2 f_y in der Zone oder F / (A_Huelle f_y) >= 1) - am Drehlager
die 16 Ankerringe. Nichts wird verschwiegen: der Spitzenwert bleibt
sichtbar, steht aber getrennt und mit dem Vermerk :data:`VERMERK`.

Hier steht, was Ansicht, Ergebnisbaum, Zusammenfassung und Bericht daraus
brauchen; die Nachweise (ec3/volumen.py, ec3/fatigue.py) lesen die Zonen
unmittelbar ueber ``spitzenstellen.zonen_elemente``.

**Welche Groesse ausserhalb der Zonen?** Dieselbe, die die Ansicht faerbt
und die Zusammenfassung schon immer nennt: das Knotenmittel der
Elementwerte (``Results.node_vm`` bzw. ``spannungen.je_knoten``), ohne die
Knoten der Zonenelemente. Eine Legende muss zu den Farben passen. Die
**Spitze in den Zonen** ist ``sv_max`` aus Paket 1, der Wert an den
Integrationspunkten: als Eckwert eines Elements, das nicht fliesst, waechst
sie ueber jede Fliessflaeche hinaus (Paket 1: bis 740 N/mm2, wo die
Integrationspunkte hoechstens 426 haben). Bis zum 13.10.2026 zeigte sich
dieselbe Schwaeche auch ausserhalb der Zonen: Eckwerte nicht fliessender
tet10 erreichten am Drehlager 14 599 N/mm2 (V34) bei 343 N/mm2 an den
Integrationspunkten desselben Elements, das Knotenmittel 6 676 N/mm2 (V15).
Seitdem uebernimmt die Anzeige bei plastischer Rechnung die Werte der
Integrationspunkte auf die Knoten (spannungen.anzeige_knotenwerte, wie
ANSYS ERESX,NO); am Drehlager sind es ausserhalb der 16 Zonen 545,3 N/mm2
(V90) im Feld Volumen sigma_v.
"""
from __future__ import annotations

import numpy as np

#: Vermerk an jedem Spitzenwert einer auffaelligen Stelle
VERMERK = "netzabhängig, nicht für den Nachweis"
#: Ueberschrift im Ergebnisbaum und im Bericht
TITEL = "Netzabhängige Spannungsspitzen"


def eintrag(res) -> dict | None:
    """Der Eintrag ``res.info["spitzenstellen"]`` oder None."""
    e = (getattr(res, "info", None) or {}).get("spitzenstellen")
    return e if isinstance(e, dict) else None


def auffaellige(res) -> list:
    """Die auffaelligen Stellen eines Ergebnisses, nach Rang."""
    e = eintrag(res) or {}
    return sorted((s for s in e.get("stellen", []) or [] if s.get("auffaellig")),
                  key=lambda s: int(s.get("rang", 0) or 0))


def ergebnisse_der_umhuellenden(res, analysis) -> list:
    """Die Ergebnisse, aus denen eine Umhuellende besteht (ueber ihre Namen in
    der Analyse) - eine Umhuellende traegt selbst keinen Eintrag."""
    if analysis is None or eintrag(res) is not None or not getattr(res, "names", None):
        return []
    alle = analysis.all_results() if hasattr(analysis, "all_results") else {}
    return [alle[n] for n in res.names if n in alle]


def _quellen(res, analysis=None) -> list:
    if eintrag(res) is not None:
        return [res]
    return ergebnisse_der_umhuellenden(res, analysis)


def zonen_elemente(res, analysis=None) -> np.ndarray:
    """Die Elemente der auffaelligen Zonen (bei einer Umhuellenden ueber ihre
    Ergebnisse vereinigt)."""
    from .spitzenstellen import zonen_elemente as ze
    teile = [ze(r) for r in _quellen(res, analysis)]
    return np.unique(np.concatenate(teile)).astype(np.int64) if teile else np.zeros(0, np.int64)


def nachweis_zonen(model, ergebnisse: dict) -> dict:
    """{Name: Menge der Zonenelemente} der Ergebnisse, die ein Nachweis liest.

    Ein Ergebnis ohne Eintrag - eine Alternative einer Ergebniskombination,
    die der Nachweis erst ueberlagert (solver.ergebnisse_der_alternativen),
    oder eines aus einer Ergebnisdatei von vor dem 10.10.2026 - wird hier
    ausgewertet (spitzenstellen.auswerten, einmal je Modell die Stellen):
    sonst laese der Nachweis seine Zone still mit. Gemessen an der Platte mit
    Loch und EK1 = 1,35 LF1: ohne das eta 19,803 statt 3,767
    (tests/test_spitzen_zeigen.py)."""
    from . import spitzenstellen as sp
    stellen = punkte = None
    aus: dict = {}
    for name, r in (ergebnisse or {}).items():
        if r is None:
            continue
        # ohne Eintrag oder mit einem aelterer Fassung (seit 13.10.2026: die
        # groessere Zone von davor) wird hier ausgewertet
        if (eintrag(r) is None or sp.veraltet(eintrag(r))) and getattr(r, "solid_res", None) \
                and getattr(r, "u", None) is not None:
            try:
                if stellen is None:
                    stellen = sp.kandidaten(model)
                    punkte = sp.punktspannungen_der_zonen(model, stellen)
                if stellen:
                    sp.auswerten(model, r, stellen, punkte)
            except Exception as ex:           # noqa: BLE001 - dann ohne Kennzeichnung, aber gesagt
                (getattr(r, "info", None) or {})["spitzenstellen_fehler"] = f"{type(ex).__name__}: {ex}"
        aus[name] = set(int(e) for e in sp.zonen_elemente(r).tolist())
    return aus


def zonenknoten(model, res, analysis=None) -> np.ndarray | None:
    """Maske (nn,) der Knoten aller Elemente der auffaelligen Zonen - None,
    wenn das Ergebnis keine auffaellige Stelle hat."""
    el = zonen_elemente(res, analysis)
    if not len(el):
        return None
    zk = np.zeros(int(model.nn), bool)
    for e in el.tolist():
        if 0 <= e < len(model.elements):
            kn = np.asarray(model.elements[e].nodes, np.int64)
            zk[kn[(kn >= 0) & (kn < model.nn)]] = True
    return zk


def spitze(res, analysis=None) -> dict | None:
    """Die Spitze der auffaelligen Stellen: ``sv`` [Pa] an den
    Integrationspunkten (sv_max aus Paket 1, nicht der Elementwert), ``eps_p``
    [-] und je die Stelle dazu, ``n`` die Zahl der Stellen. None ohne
    auffaellige Stelle."""
    st = [s for r in _quellen(res, analysis) for s in auffaellige(r)]
    if not st:
        return None
    a = max(st, key=lambda s: float(s.get("sv_max", 0.0) or 0.0))
    b = max(st, key=lambda s: float(s.get("eps_p_max", 0.0) or 0.0))
    return {"sv": float(a.get("sv_max", 0.0) or 0.0), "stelle_sv": a,
            "eps_p": float(b.get("eps_p_max", 0.0) or 0.0), "stelle_eps": b,
            "n": len({(s.get("nr"), s.get("name")) for s in st})}


def ursache(s: dict) -> str:
    """Die Ursache einer Stelle im Klartext, etwa „starre Scheibe koppelt nur
    den Lochrand“."""
    from . import spitzenstellen as sp
    q = s.get("quelle", "")
    n = int(s.get("n_knoten", 0) or 0)
    kn = "1 Knoten" if n == 1 else f"{n} Knoten"
    if q == sp.STARRE_SCHEIBE:
        if s.get("lochrand"):
            return "starre Scheibe koppelt nur den Lochrand"
        return ("starre Scheibe koppelt nur einen Rand" if s.get("art") == "Linie"
                else f"starre Scheibe koppelt nur {kn}")
    if q == sp.STABENDE:
        return f"Stabende hängt an {kn}"
    if q == sp.KOPPLUNG:
        return f"Kopplung hängt an {kn}"
    if q == sp.STARRKOERPER:
        return f"Starrkörper hängt an {kn}"
    if q == sp.KNOTENLAST:
        return f"Knotenlast auf {kn}" + (" einer Linie" if s.get("art") == "Linie" else "")
    if q == sp.LINIENLAST:
        return "Linienlast auf einer Volumenkante"
    if q == sp.KNOTENLAGER:
        return f"Knotenlager hält {kn}"
    if q == sp.LINIENLAGER:
        return "Linienlager auf einer Volumenkante"
    return str(q)


def bauteil(s: dict) -> str:
    """Das Bauteil (Koerper) einer Stelle, „–“ ohne."""
    return str(s.get("koerper") or "") or "–"


def bauteil_des_elements(model, e: int) -> str:
    """Der Koerper eines Volumenelements: Element.group, sonst die Liste der
    Koerper; „“ ohne."""
    if not 0 <= int(e) < len(model.elements):
        return ""
    g = str(getattr(model.elements[int(e)], "group", "") or "")
    koerper = getattr(model, "koerper", None) or {}
    if g and g in koerper:
        return g
    for name, k in koerper.items():
        if int(e) in set(int(x) for x in (getattr(k, "elemente", None) or [])):
            return str(name)
    return g


def bauteil_des_knotens(model, k: int) -> str:
    """Der Koerper eines Knotens (das erste Volumenelement daran), an einem
    Knoten ohne Volumen „Stab <Name> (<Querschnitt>)“ des ersten Elements
    daran, „“ ohne."""
    from . import elemente as EL
    vol = set(EL.VOLUMEN_TYPEN)
    stab = None
    for i, e in enumerate(model.elements):
        if int(k) in e.nodes:
            if e.typ in vol:
                return bauteil_des_elements(model, i)
            if stab is None:
                name = next((str(n) for n, mm in (getattr(model, "members", None) or {}).items()
                             if i in (getattr(mm, "elements", None) or [])), "")
                sec = str(getattr(e, "sec", "") or "")
                stab = "Stab" + (f" {name}" if name else f" (Element {i})") + (f" ({sec})" if sec else "")
    return stab or ""


def uebersicht(model, res) -> dict | None:
    """Die Werte der Zusammenfassung mit auffaelligen Stellen (sonst None):
    ``sv`` (Pa, Knoten, Bauteil) - das groesste Knotenmittel der
    Vergleichsspannung (Results.node_vm) ausserhalb der Knoten der Zonen;
    ``eps_p`` (Wert, Element, Bauteil) - die groesste plastische Dehnung
    ausserhalb der Zonenelemente oder None ohne Plastizitaet; ``spitze``
    (:func:`spitze`). Einmal je Ergebnis gerechnet (res._cache)."""
    e = eintrag(res)
    if e is None or not e.get("auffaellig"):
        return None
    cache = getattr(res, "_cache", None)
    if isinstance(cache, dict) and cache.get("spitzen_uebersicht", (None,))[0] is e:
        return cache["spitzen_uebersicht"][1]
    zk = zonenknoten(model, res)
    el = set(int(i) for i in zonen_elemente(res).tolist())
    aus: dict = {"spitze": spitze(res), "sv": None, "eps_p": None}
    try:
        nv = np.asarray(res.node_vm, float)
    except Exception:                         # noqa: BLE001 - ohne Knotenwerte keine Zeile
        nv = None
    if nv is not None and nv.size and zk is not None and len(zk) == len(nv):
        w = np.where(zk, np.nan, nv)
        if np.isfinite(w).any():
            k = int(np.nanargmax(w))
            aus["sv"] = (float(w[k]), k, bauteil_des_knotens(model, k))
    pl = (getattr(res, "info", None) or {}).get("plastisch") or {}
    if pl:
        rest = [(float(v), int(i)) for i, v in pl.items() if int(i) not in el]
        if rest:
            v, i = max(rest)
            aus["eps_p"] = (v, i, bauteil_des_elements(model, i))
        else:
            aus["eps_p"] = (0.0, -1, "")
    if isinstance(cache, dict):
        cache["spitzen_uebersicht"] = (e, aus)
    return aus


def zusammenfassung_zeilen(model, res) -> list:
    """Die Zeilen der Zusammenfassung (Results.summary) zu den auffaelligen
    Stellen: das Maximum ausserhalb und getrennt die Spitze. Leer ohne."""
    u = uebersicht(model, res)
    if u is None:
        return []
    z = []
    if u["sv"] is not None:
        v, k, b = u["sv"]
        z.append(f"max. Vergleichsspannung : {v / 1e6:.2f} MPa außerhalb der netzabhängigen Stellen "
                 f"(Knoten {k}" + (f", {b})" if b else ")"))
    sp_ = u["spitze"]
    if sp_ is not None:
        a = sp_["stelle_sv"]
        z.append(f"Netzabhängige Stellen   : {sp_['n']}, σ_v bis {sp_['sv'] / 1e6:.1f} MPa "
                 f"({bauteil(a)}, Integrationspunkte)"
                 + (f", ε_p bis {sp_['eps_p'] * 100:.2f} % ({bauteil(sp_['stelle_eps'])})"
                    if sp_["eps_p"] > 0 else "")
                 + f" – {VERMERK}")
    return z


def eps_p_ausserhalb(model, res) -> tuple | None:
    """(eps_p, Element, Bauteil) ausserhalb der Zonen fuer die Zeile
    Plastizitaet der Zusammenfassung - None ohne auffaellige Stelle."""
    u = uebersicht(model, res)
    return None if u is None else u["eps_p"]


def legende_text(spitze_: dict, faktor: float = 1.0, einheit: str = "N/mm²") -> str:
    """„in netzabhängigen Stellen bis 1187 N/mm² (netzabhängig)“ - die Spitze
    an den Integrationspunkten in der Einheit der Legende (``faktor`` von
    N/mm² dorthin)."""
    from .spannungen import dezimal
    return f"in netzabhängigen Stellen bis {dezimal(spitze_['sv'] / 1e6 * faktor)} {einheit} (netzabhängig)"


def stellen_zum_zeigen(res, analysis=None) -> list:
    """Die auffaelligen Stellen eines Ergebnisses - bei einer Umhuellenden aus
    ihren Ergebnissen, je Stelle die mit dem groessten sigma_v - nach Rang."""
    je: dict = {}
    for r in _quellen(res, analysis):
        for s in auffaellige(r):
            k = (s.get("nr"), s.get("name"))
            if k not in je or float(s.get("sv_max", 0.0) or 0.0) > float(je[k].get("sv_max", 0.0) or 0.0):
                je[k] = s
    return sorted(je.values(), key=lambda s: (-(s.get("sv_fy") or 0.0), -float(s.get("sv_max", 0.0) or 0.0)))


def baum_eintraege(res) -> list:
    """Die Zeilen des Ergebnisbaums zu einem Ergebnis (:func:`baum_eintraege_fuer`)."""
    return baum_eintraege_fuer(auffaellige(res))


def baum_eintraege_fuer(stellen: list) -> list:
    """Die Zeilen des Ergebnisbaums: (Text, Zusatz, Schluessel) je
    auffaelliger Stelle - Bauteil und Ursache, dazu Kraft, sigma_v und eps_p
    (Punkt als Dezimalzeichen wie alle Texte des Baums)."""
    from .spannungen import dezimal
    aus = []
    for s in stellen:
        F = s.get("kraft")
        teile = [f"F {dezimal(F / 1e3)} kN" if F is not None else "F –",
                 f"σ_v {dezimal(float(s.get('sv_max', 0.0)) / 1e6)} N/mm²",
                 f"ε_p {dezimal(float(s.get('eps_p_max', 0.0)) * 100, 2)} %"]
        aus.append((f"{bauteil(s)}: {ursache(s)}", " · ".join(teile) + " (netzabhängig)",
                    f"spitze:{int(s.get('nr', 0))}"))
    return aus


def stelle_nach_nummer(res, nr: int) -> dict | None:
    for s in auffaellige(res):
        if int(s.get("nr", -1)) == int(nr):
            return s
    return None
