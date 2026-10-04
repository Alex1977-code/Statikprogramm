"""Referenz fuer tests/test_huellen_schluessel.py (Befund R1, 04.10.2026):
Fingerabdruecke von Rechnungen und Ergebnisdateien des Stands **vor** der
Behebung (6791f9f).

Ein Fingerabdruck haelt je Ergebnisfeld einen Hash der Bytes: zwei gleiche
Fingerabdruecke heissen bitgleiche Zahlen, nicht nur aehnliche. Gleitkomma-
zahlen ausserhalb von Feldern stehen als float.hex() darin.

* ``beispiele.json`` - die Beispiele frame, truss, hall, gate und contact mit
  ``solve_all(design=True, fatigue=True)``: Lastfaelle, Kombinationen,
  Umhuellende, Nachweise EC3 und Ermuedung;
* ``ermuedung.json`` - der Hallenrahmen mit einer FAT-Ergebniskombination
  „EK_FAT“ und der Ermuedungslast, die der RFEM-Import daraus macht
  (``_ermuedungslasten_aus_fat``): Ermuedung aus einer FAT-Umhuellenden ohne
  Namenskollision;
* ``ohne_kollision.json/.ergebnisse`` - Kragarm mit Ergebniskombinationen
  „EK1“ (GZT) und „EK2“ (Ermuedung), Ergebnisdatei von 6791f9f, dazu in
  ``ohne_kollision_geladen.json`` der Fingerabdruck der Analyse, wie 6791f9f
  sie aus der Datei liest;
* ``mit_kollision.json/.ergebnisse`` - derselbe Kragarm mit der
  Ergebniskombination „ULS“: in dieser Datei steht unter dem Schluessel ULS
  die Umhuellende der Ergebniskombination, die Umhuellende GZT fehlt (der
  Befund).

Erzeugt mit dem Baum von 6791f9f:

    python tests/daten/huellen_schluessel_6791f9f/erzeugen.py <baum 6791f9f> <zielordner>
"""
import dataclasses
import hashlib
import json
import os
import sys

#: Felder eines Ergebnisses (Results), die der Fingerabdruck haelt - ohne
#: Name, Rechenzeit (info) und Zwischenwerte (_cache)
RESULTS_FELDER = ("u", "reactions", "beam_end", "beam_q", "shell_res", "solid_res",
                  "solid_mittel", "solid_knoten", "feder_res", "grenzschicht_res", "bimomente",
                  "woelb", "contact", "kontaktzustand", "contact_forces", "singular")
#: Felder einer Umhuellenden (Envelope)
HUELLEN_FELDER = ("name", "names", "n_stations", "u_min", "u_max", "u_min_src", "u_max_src",
                  "r_min", "r_max", "r_min_src", "r_max_src", "beam", "node_vm_max",
                  "node_vm_src", "util")

#: Beispiele fuer R1f
BEISPIELE = ("frame", "truss", "hall", "gate", "contact")


def _h(a) -> str:
    import numpy as np
    a = np.ascontiguousarray(np.asarray(a))
    if a.dtype == object:
        return "O" + hashlib.sha256(json.dumps(wert(a.tolist())).encode()).hexdigest()[:24]
    kopf = f"{a.dtype.str}{a.shape}".encode()
    return hashlib.sha256(kopf + a.tobytes()).hexdigest()[:24]


def wert(v):
    """Ein Wert als JSON-faehige, bitgenaue Form."""
    import numpy as np
    if isinstance(v, np.ndarray):
        return "A" + _h(v)
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v).hex()
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, dict):
        return [[str(k), wert(x)] for k, x in v.items()]
    if isinstance(v, (list, tuple, set)):
        return [wert(x) for x in (sorted(v, key=str) if isinstance(v, set) else v)]
    if type(v).__name__ == "Model":
        return "Model"
    if dataclasses.is_dataclass(v):
        return [[f.name, wert(getattr(v, f.name))] for f in dataclasses.fields(v)]
    return type(v).__name__


def huelle(env) -> dict:
    d = {f: wert(getattr(env, f, None)) for f in HUELLEN_FELDER}
    d["umag_max"] = wert(env.umag_max)
    d["phimag_max"] = wert(env.phimag_max)
    return d


def ergebnis(r) -> dict:
    return {f: wert(getattr(r, f, None)) for f in RESULTS_FELDER}


def analyse(an) -> dict:
    """Fingerabdruck einer Analyse: Ergebnisse, Umhuellende (mit Reihenfolge
    der Schluessel), Nachweise EC3 und Ermuedung."""
    return {
        "cases": {k: ergebnis(r) for k, r in an.cases.items()},
        "combinations": {k: ergebnis(r) for k, r in an.combinations.items()},
        "alternativen": {k: ergebnis(r) for k, r in (getattr(an, "alternativen", None) or {}).items()},
        "envelope_keys": list(an.envelopes),
        "envelopes": {k: huelle(e) for k, e in an.envelopes.items()},
        "design": wert(an.design),
        "fatigue": wert(an.fatigue),
    }


def _sha(x) -> str:
    return hashlib.sha256(json.dumps(x, ensure_ascii=False).encode()).hexdigest()[:24]


def verdichtet(abdruck: dict) -> dict:
    """Ein Hash je Ergebnis, Umhuellende und Nachweis - so bleibt die Referenz
    klein (der volle Fingerabdruck der Beispiele hat 1,2 MB). Reihenfolge und
    Namen der Umhuellenden stehen im Klartext dabei."""
    return {
        "envelope_keys": abdruck["envelope_keys"],
        "envelope_names": {k: e["name"] for k, e in abdruck["envelopes"].items()},
        "cases": {k: _sha(v) for k, v in abdruck["cases"].items()},
        "combinations": {k: _sha(v) for k, v in abdruck["combinations"].items()},
        "alternativen": {k: _sha(v) for k, v in abdruck["alternativen"].items()},
        "envelopes": {k: _sha(v) for k, v in abdruck["envelopes"].items()},
        "design": _sha(abdruck["design"]),
        "fatigue": _sha(abdruck["fatigue"]),
    }


def kragarm(ek_name: str = "EK1", ek_typ: str = "ULS", weitere_ek=None, typen=None):
    """Kragarm mit drei Lastfaellen in drei Richtungen (Min und Max je
    Freiheitsgrad aus verschiedenen Ergebnissen), zwei GZT-Kombinationen, je
    einer GZG- und Ermuedungskombination und einer RFEM-Ergebniskombination
    *ek_name* vom Typ *ek_typ* mit drei Alternativen. ``weitere_ek``:
    {Name: Typ} weiterer Ergebniskombinationen; ``typen``: Typen weiterer
    gewoehnlicher Kombinationen (je eine)."""
    from statik3d.model import Model, Material, Section, Combination
    from statik3d import mesher
    m = Model("Huellenschluessel")
    m.add_material(Material("S", E=210e9, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (2.0, 0, 0), 4)
    m.fix(ids[0], "all")
    m.case().category = "G"
    lf1 = m.active_case
    m.load_node(ids[-1], Fz=-10e3, case=lf1)
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fy=5e3, Fz=-2e3, case="LF2")
    m.add_load_case("LF3", "W")
    m.load_node(ids[-1], Mx=2e3, Fy=-3e3, case="LF3")
    m.add_combination("K1", {lf1: 1.35, "LF2": 1.5}, "ULS", "GZT 1")
    m.add_combination("K2", {lf1: 1.0, "LF3": 1.5}, "ULS", "GZT 2")
    m.add_combination("K3", {lf1: 1.0, "LF2": 1.0}, "SLS_CH", "GZG")
    m.add_combination("K4", {lf1: 1.0, "LF2": 0.6}, "FAT", "Ermuedung")
    for i, typ in enumerate(typen or ()):
        m.add_combination(f"K{5 + i}", {lf1: 1.0 + 0.1 * i, "LF3": 0.7}, typ, f"Typ {typ}")
    alternativen = [{lf1: 1.35}, {lf1: 1.35, "LF2": 1.5, "LF3": 0.9}, {"LF3": 1.5}]
    m.combinations[ek_name] = Combination(ek_name, {}, ek_typ, alternativen=alternativen)
    for i, (n, t) in enumerate((weitere_ek or {}).items()):
        m.combinations[n] = Combination(n, {}, t, alternativen=[{lf1: 1.0 + 0.2 * i},
                                                                 {"LF2": 1.2, "LF3": 0.5}])
    return m


def ermuedung_lesbar(fat) -> dict:
    """D, Ausnutzung und massgebende Stelle je Stab im Klartext (JSON haelt
    die Gleitkommazahlen mit repr, also bitgenau)."""
    return {k: {"D": float(x.D), "D_shear": float(x.D_shear), "util": float(x.util),
                "governing": x.governing, "x_governing": float(x.x_governing)}
            for k, x in fat.members.items()}


def hallenrahmen_ermuedung(ek_name: str = "EK_FAT"):
    """Hallenrahmen mit einer FAT-Ergebniskombination und der Ermuedungslast,
    die der RFEM-Import aus ihr macht (Verlauf ueber die Zustaende, spanne)."""
    from statik3d.examples_lib import hall_frame_example
    from statik3d.model import Combination
    from statik3d.importers.rfem6_db import _ermuedungslasten_aus_fat
    m = hall_frame_example()
    m.combinations[ek_name] = Combination(ek_name, {}, "FAT",
                                          alternativen=[{"Kran": 1.0}, {"LF1": 1.0}, {"S": 1.0}])
    _ermuedungslasten_aus_fat(m, [])
    return m


def main():
    baum = os.path.abspath(sys.argv[1])
    ziel = os.path.abspath(sys.argv[2])
    sys.path.insert(0, baum)
    import statik3d
    assert os.path.abspath(statik3d.__file__).startswith(baum), statik3d.__file__
    from statik3d import solver, ergebnisse
    from statik3d.examples_lib import build_example
    from statik3d.model import Model
    os.makedirs(ziel, exist_ok=True)

    def schreiben_json(name, d):
        with open(os.path.join(ziel, name), "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=False)
            f.write("\n")

    schreiben_json("beispiele.json", {
        b: verdichtet(analyse(solver.solve_all(build_example(b), design=True, fatigue=True)))
        for b in BEISPIELE})
    m = hallenrahmen_ermuedung()
    an = solver.solve_all(m, design=True, fatigue=True)
    schreiben_json("ermuedung.json", {"fatigue_loads": sorted(m.fatigue_loads),
                                      "fatigue": wert(an.fatigue),
                                      "lesbar": ermuedung_lesbar(an.fatigue),
                                      "summary": an.fatigue.summary()})
    for datei, ek in (("ohne_kollision", "EK1"), ("mit_kollision", "ULS")):
        m = kragarm(ek, "ULS", weitere_ek={"EK2": "FAT"})
        an = solver.solve_all(m, design=False, fatigue=False)
        pfad = os.path.join(ziel, datei + ".json")
        m.save(pfad)
        ergebnisse.schreiben(ergebnisse.pfad_zu(pfad), m, an)
        if datei == "ohne_kollision":
            m2 = Model.load(pfad)
            an2 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m2)
            schreiben_json("ohne_kollision_geladen.json", verdichtet(analyse(an2)))
        print(datei, "Umhuellende:", {k: v.name for k, v in an.envelopes.items()})
    print("geschrieben nach", ziel)


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
