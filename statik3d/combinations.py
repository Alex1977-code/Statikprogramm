"""
Automatische Lastfallkombinationen nach DIN EN 1990 (Eurocode 0) mit
deutschem Nationalen Anhang.

Grenzzustand der Tragfaehigkeit (STR/GEO), Gl. 6.10:
    sum(gamma_G * G) + gamma_Q1 * Q1 + sum(gamma_Qi * psi0,i * Qi)
alternativ Gl. 6.10a / 6.10b:
    6.10a: sum(gamma_G * G) + sum(gamma_Qi * psi0,i * Qi)
    6.10b: sum(xi * gamma_G * G) + gamma_Q1 * Q1 + sum(gamma_Qi * psi0,i * Qi)
Aussergewoehnlich (6.11b):
    sum(G) + A + psi1,1 * Q1 + sum(psi2,i * Qi)
Gebrauchstauglichkeit:
    charakteristisch (6.14b): G + Q1 + sum(psi0,i Qi)
    haeufig          (6.15b): G + psi1,1 Q1 + sum(psi2,i Qi)
    quasi-staendig   (6.16b): G + sum(psi2,i Qi)

Regeln:
* Staendige Lasten werden gemeinsam guenstig (gamma_G,inf) oder unguenstig
  (gamma_G,sup) angesetzt (beide Varianten werden erzeugt).
* Veraenderliche Lasten wirken nur unguenstig (gamma_Q,fav = 0 -> weggelassen).
* Lastfaelle derselben 'exclusive_group' wirken nie gleichzeitig.
* Jede veraenderliche Einwirkung wird einmal als Leiteinwirkung angesetzt.
"""
from __future__ import annotations

import itertools

from .model import Model, Combination, LoadCase, DesignSettings


def _variable_sets(cases: list[LoadCase]) -> list[list[LoadCase]]:
    """Alle zulaessigen Teilmengen der veraenderlichen Lastfaelle unter
    Beachtung der Ausschlussgruppen (jede Gruppe: hoechstens ein Lastfall)."""
    groups: dict[str, list[LoadCase]] = {}
    singles: list[LoadCase] = []
    for lc in cases:
        if lc.exclusive_group:
            groups.setdefault(lc.exclusive_group, []).append(lc)
        else:
            singles.append(lc)
    # Fuer Gruppen: keins oder genau eins
    options = [[None] + g for g in groups.values()]
    out = []
    for choice in itertools.product(*options) if options else [()]:
        chosen = [c for c in choice if c is not None]
        for k in range(len(singles) + 1):
            for sub in itertools.combinations(singles, k):
                out.append(chosen + list(sub))
    # Duplikate entfernen (Reihenfolge stabil)
    seen = set()
    uniq = []
    for s in out:
        key = tuple(sorted(lc.name for lc in s))
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq


def _gamma(lc: LoadCase, ds: DesignSettings, favourable: bool) -> float:
    if lc.is_permanent:
        if favourable:
            return lc.gamma_inf if lc.gamma_inf is not None else ds.gamma_G_inf
        return lc.gamma_sup if lc.gamma_sup is not None else ds.gamma_G_sup
    if favourable:
        return ds.gamma_Q_fav
    return lc.gamma_sup if lc.gamma_sup is not None else ds.gamma_Q


def generate_combinations(model: Model, uls: bool = True, sls: bool = True,
                          accidental: bool = True, rule: str = None,
                          g_favourable: bool = True, replace: bool = True,
                          max_combinations: int = 2000) -> list[Combination]:
    """Kombinationen erzeugen und im Modell ablegen (replace=True ersetzt
    vorhandene automatisch erzeugte Kombinationen).

    Kombiniert wird **je Situation**: Lastfaelle verschiedener Situationen
    (Stellung, abgeschaltete Elemente) stehen nie in einer Kombination; jede
    erzeugte Kombination traegt ihre Situation."""
    ds = model.design
    rule = rule or ds.combination_rule
    combos: list[Combination] = []
    if replace:
        model.combinations = {k: c for k, c in model.combinations.items()
                              if not c.description.startswith("auto")}
    zaehler = [len(model.combinations)]
    seen: set = set()
    for sit, namen in model.lastfaelle_je_situation().items():
        faelle = [model.load_cases[k] for k in namen]
        _kombinationen_bilden(model, faelle, sit, uls, sls, accidental, rule, g_favourable,
                              max_combinations, combos, seen, zaehler)
    return combos


def _kombinationen_bilden(model: Model, faelle: list, situation: str, uls: bool, sls: bool,
                          accidental: bool, rule: str, g_favourable: bool,
                          max_combinations: int, combos: list, seen: set, zaehler: list):
    """Die Kombinationen einer Situation nach DIN EN 1990 (6.10, 6.10a/b,
    6.11b, 6.14b, 6.15b, 6.16b)."""
    from .model import GRUNDSTELLUNG
    ds = model.design
    perm = [lc for lc in faelle if lc.is_permanent]
    var = [lc for lc in faelle if lc.is_variable]
    acc = [lc for lc in faelle if lc.is_accidental]
    sit = "" if situation == GRUNDSTELLUNG else situation
    zusatz = f" [{situation}]" if sit else ""

    def add(name_prefix, factors, typ, desc, leading=""):
        factors = {k: round(v, 6) for k, v in factors.items() if abs(v) > 1e-12}
        if not factors:
            return
        key = (typ, sit, tuple(sorted(factors.items())))
        if key in seen:
            return
        seen.add(key)
        zaehler[0] += 1
        c = Combination(f"{name_prefix}{zaehler[0]}", factors, typ, "auto: " + desc + zusatz,
                        leading, situation=sit)
        combos.append(c)
        model.combinations[c.name] = c

    g_variants = [False, True] if (g_favourable and var) else [False]
    var_sets = _variable_sets(var) if var else [[]]
    if len(var_sets) * max(1, len(var)) > max_combinations:
        raise RuntimeError(f"Zu viele Kombinationen ({len(var_sets)}); bitte "
                           f"Ausschlussgruppen verwenden oder Lastfaelle zusammenfassen")

    # ---------------- GZT (STR/GEO) ----------------
    if uls:
        for fav in g_variants:
            gf = {lc.name: _gamma(lc, ds, fav) for lc in perm}
            gdesc = "G guenstig" if fav else "G unguenstig"
            if not var:
                add("GZT", gf, "ULS", f"6.10 nur staendig, {gdesc}")
            for vs in var_sets:
                if not vs:
                    add("GZT", gf, "ULS", f"6.10 nur staendig, {gdesc}")
                    continue
                for lead in vs:
                    f = dict(gf)
                    f[lead.name] = _gamma(lead, ds, False)
                    for lc in vs:
                        if lc is not lead:
                            f[lc.name] = _gamma(lc, ds, False) * lc.psi_factors[0]
                    if rule == "6.10ab":
                        f_a = dict(gf)
                        for lc in vs:
                            f_a[lc.name] = _gamma(lc, ds, False) * lc.psi_factors[0]
                        add("GZT", f_a, "ULS", f"6.10a, {gdesc}")
                        f_b = {k: (v * ds.xi if k in gf else v) for k, v in f.items()}
                        add("GZT", f_b, "ULS", f"6.10b Leit {lead.name}, {gdesc}", lead.name)
                    else:
                        add("GZT", f, "ULS", f"6.10 Leit {lead.name}, {gdesc}", lead.name)

    # ---------------- Aussergewoehnlich ----------------
    if accidental and acc:
        for a in acc:
            gf = {lc.name: 1.0 for lc in perm}
            gf[a.name] = 1.0
            for vs in var_sets:
                if not vs:
                    add("GZT-A", gf, "ACC", f"6.11b {a.name} ohne Q", a.name)
                    continue
                for lead in vs:
                    f = dict(gf)
                    f[lead.name] = lead.psi_factors[1]
                    for lc in vs:
                        if lc is not lead:
                            f[lc.name] = lc.psi_factors[2]
                    add("GZT-A", f, "ACC", f"6.11b {a.name}, Leit {lead.name}", lead.name)

    # ---------------- GZG ----------------
    if sls:
        gf = {lc.name: 1.0 for lc in perm}
        if not var:
            add("GZG", gf, "SLS_CH", "6.14b charakteristisch")
        for vs in var_sets:
            if not vs:
                add("GZG", gf, "SLS_CH", "6.14b charakteristisch (nur G)")
                add("GZG", gf, "SLS_QP", "6.16b quasi-staendig (nur G)")
                continue
            for lead in vs:
                f = dict(gf)
                f[lead.name] = 1.0
                for lc in vs:
                    if lc is not lead:
                        f[lc.name] = lc.psi_factors[0]
                add("GZG", f, "SLS_CH", f"6.14b charakteristisch, Leit {lead.name}", lead.name)
                f = dict(gf)
                f[lead.name] = lead.psi_factors[1]
                for lc in vs:
                    if lc is not lead:
                        f[lc.name] = lc.psi_factors[2]
                add("GZG", f, "SLS_FR", f"6.15b haeufig, Leit {lead.name}", lead.name)
            f = dict(gf)
            for lc in vs:
                f[lc.name] = lc.psi_factors[2]
            add("GZG", f, "SLS_QP", "6.16b quasi-staendig")


def combination_table(model: Model) -> list[list[str]]:
    """Tabellarische Darstellung (fuer Bericht/GUI): Kopfzeile + Zeilen."""
    names = list(model.load_cases)
    head = ["Kombination", "Typ", "Leit", "Situation", "Theorie"] + names + ["Beschreibung"]
    rows = [head]
    for c in model.combinations.values():
        rows.append([c.name, c.typ, c.leading, getattr(c, "situation", "") or "Grundstellung",
                     model.theorie_von(c) if hasattr(model, "theorie_von") else "I"]
                    + [f"{c.factors.get(n, 0):g}" if c.factors.get(n, 0) else "" for n in names]
                    + [c.description])
    return rows
