"""Messung der eingebauten Beispiele fuer Paket R2-C1 (06.10.2026).

Misst die Rechenwerte jedes Beispiels - Lastfaelle, Kombinationen,
Umhuellende, EC3-Nachweis, Ermuedung - **ohne einen Namen**: ein Lastfall wird
ueber seinen alten Namen genannt (``alt``: heutiger Name -> Name vor R2-C1),
eine Kombination ueber ihre Faktoren („LF1*1.35|W_links*1.5“). So lassen sich
der Stand vor und nach der Umstellung der Erzeuger Zahl fuer Zahl vergleichen,
obwohl sich jeder Name geaendert hat.

Erzeugt wurde ``referenz.json`` auf dem Stand c5dbb10 (Sammelzweig mit R1 und
R2-A1, vor R2-C1), im Wurzelverzeichnis des Arbeitsbaums:

    python tests/daten/erzeuger_c5dbb10/erzeugen.py

Danach rechnet tests/test_namen_erzeuger.py (G1 und G5) jedes Beispiel neu und
vergleicht mit dieser Datei; ``messen`` ist dafuer importierbar.
"""
import json
import math
import os
import sys

import numpy as np

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(os.path.dirname(os.path.dirname(HIER)))
if WURZEL not in sys.path:
    sys.path.insert(0, WURZEL)

#: Beispiele und ihre Lastfaelle vor R2-C1 (alt) in der Reihenfolge des Modells;
#: nach R2-C1 heissen sie LF1, LF2, ... mit dem alten Namen als Bezeichnung
#: (LF1 des Hallenrahmens und des Stauwand-Beispiels: „Eigengewicht“)
BEISPIELE = ["frame", "plate", "solid", "truss", "contact", "friction", "hall", "gate"]
ALT_NAMEN = {"hall": ["LF1", "S", "W_links", "W_rechts", "Kran"],
             "gate": ["LF1", "Wasser", "Wasser_Wellen"]}


def _f(x) -> float:
    return float(f"{float(x):.14g}")


def faktorschluessel(faktoren: dict, alt: dict) -> str:
    """„LF1*1.35|W_links*1.5“ - Lastfallnamen in der alten Form, sortiert."""
    teile = sorted((alt.get(k, k), round(float(v), 9)) for k, v in faktoren.items())
    return "|".join(f"{k}*{v:g}" for k, v in teile)


def _ergebnis(r) -> dict:
    u = np.asarray(r.u, float).reshape(-1, 6)
    R = np.asarray(r.reactions, float).reshape(-1, 6)
    return {"u_norm_max": _f(np.linalg.norm(u[:, :3], axis=1).max()),
            "u_summe": _f(u.sum()), "u_betrag_summe": _f(np.abs(u).sum()),
            "r_betrag_max": _f(np.abs(R).max()), "r_summe": [_f(x) for x in R.sum(axis=0)]}


def _umhuellende(env, schluessel_von_name) -> dict:
    d = {"umag_max": _f(np.max(env._umag)),
         "u_max": _f(env.u_max.max()), "u_min": _f(env.u_min.min()),
         "u_betrag_summe": _f(np.abs(env.u_max).sum() + np.abs(env.u_min).sum()),
         "r_max": _f(env.r_max.max()), "r_min": _f(env.r_min.min())}
    my = [float(np.max(v["My"][1])) for v in env.beam.values() if v.get("My") is not None]
    if my:
        d["My_max"] = _f(max(my))
    i = int(np.argmax(env.u_max))
    d["massgebend_u"] = schluessel_von_name(env.names[int(env.u_max_src.flat[i])])
    d["ergebnisse"] = len(env.names)
    return d


def messen(m, alt: dict, solver) -> dict:
    """Die Rechenwerte des Modells *m*. ``alt``: Name im Modell -> alter Name."""
    from statik3d.ec3 import design as ec3d
    an = solver.solve_all(m, design=bool(m.members), fatigue=bool(m.fatigue_loads))

    def schluessel(name: str) -> str:
        if name in m.combinations:
            return "K:" + faktorschluessel(m.combinations[name].factors, alt)
        return "L:" + alt.get(name, name)
    out = {"faelle": {alt.get(n, n): _ergebnis(r) for n, r in an.cases.items()},
           "kombinationen": {faktorschluessel(m.combinations[n].factors, alt): _ergebnis(r)
                             for n, r in an.combinations.items()},
           "umhuellende": {k: _umhuellende(e, schluessel) for k, e in an.envelopes.items()}}
    if an.design is not None:
        d = an.design
        out["ec3"] = {"util_max": _f(d.util_max),
                      "staebe": {n: {"util": _f(mc.util), "massgebend": schluessel(
                          str((mc.governing or {}).get("combo") or (mc.governing or {}).get("name") or ""))}
                          for n, mc in d.members.items()}}
    if an.fatigue is not None:
        out["ermuedung"] = {n: {"D": _f(fm.D), "util": _f(fm.util), "dsig_max": _f(fm.dsig_max),
                                "fehler": fm.fehler}
                            for n, fm in an.fatigue.members.items()}
    out["anzahl"] = {"lastfaelle": len(m.load_cases), "kombinationen": len(m.combinations),
                     "ermuedungslasten": len(m.fatigue_loads)}
    return out


def alt_namen(name: str, m) -> dict:
    """Heutiger Name -> alter Name fuer das Beispiel *name* (Reihenfolge des Modells)."""
    namen = ALT_NAMEN.get(name)
    heute = list(m.load_cases)
    if namen is None:
        namen = heute
    assert len(namen) == len(heute), (name, namen, heute)
    return dict(zip(heute, namen))


def main() -> None:
    from statik3d import examples_lib, solver
    out = {}
    for name in BEISPIELE:
        m = examples_lib.build_example(name)
        out[name] = messen(m, alt_namen(name, m), solver)
        print(name, out[name]["anzahl"], flush=True)
    pfad = os.path.join(HIER, "referenz.json")
    with open(pfad, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, ensure_ascii=False)
    print("geschrieben:", pfad)


if __name__ == "__main__":
    main()
