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
* Vorspannung (Kategorie P) geht mit gamma_P = 1,0 ein, nicht mit gamma_G,sup
  (Entscheidung des Anwenders vom 13.10.2026).
* Ein Lastfall ohne zugeordnete Einwirkung (Kategorie „nicht zugeordnet“) wird
  nicht kombiniert: der Generator weigert sich mit einem Bedienhinweis
  (KombinationGesperrt), statt ihn still wegzulassen.
* Ein Bemessungslastfall (LoadCase.faktorisiert) ist schon faktorisiert: er
  geht mit gamma = 1,0 und ohne psi ein und bildet eine eigene GZT-Kombination,
  er wird nicht mit anderen Lastfaellen ueberlagert.
"""
from __future__ import annotations

import itertools

from .model import Model, Combination, LoadCase, DesignSettings, KombinationGesperrt
from .begriffe import typ_kurz, lastfaelle_kurz


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
    if getattr(lc, "faktorisiert", False):
        return 1.0                    # schon Bemessungswert: kein zweites gamma
    if lc.category == "P":
        # Vorspannung: gamma_P, guenstig wie unguenstig (bis 13.10.2026 lief P
        # als staendige Einwirkung mit gamma_G,sup = 1,35)
        eigen = lc.gamma_inf if favourable else lc.gamma_sup
        return eigen if eigen is not None else float(getattr(ds, "gamma_P", 1.0))
    if lc.is_permanent:
        if favourable:
            return lc.gamma_inf if lc.gamma_inf is not None else ds.gamma_G_inf
        return lc.gamma_sup if lc.gamma_sup is not None else ds.gamma_G_sup
    if favourable:
        return ds.gamma_Q_fav
    return lc.gamma_sup if lc.gamma_sup is not None else ds.gamma_Q


def sperrhinweis_erzeugen(offen: list) -> str:
    """Der Bedienhinweis, wenn der Generator wegen Lastfaellen ohne Einwirkung
    nichts erzeugt (auch die Oberflaeche fragt vor dem Dialog danach)."""
    return (f"Kombinationen lassen sich nicht erzeugen: {lastfaelle_kurz(offen)} ohne zugeordnete "
            "Einwirkung – γ und ψ stehen nicht fest.\n"
            "So geht es weiter: Lastfall im Modellbaum anklicken und rechts unter „Einwirkung“ die "
            "Einwirkung wählen – oder, wenn seine Lasten schon Bemessungswerte sind, den Haken "
            "„Bemessungslastfall, bereits faktorisiert“ setzen.")


def generate_combinations(model: Model, uls: bool = True, sls: bool = True,
                          accidental: bool = True, rule: str = None,
                          g_favourable: bool = True, replace: bool = True,
                          max_combinations: int = 2000) -> list[Combination]:
    """Kombinationen erzeugen und im Modell ablegen (replace=True ersetzt
    vorhandene automatisch erzeugte Kombinationen).

    Kombiniert wird **je Situation**: Lastfaelle verschiedener Situationen
    (Stellung, abgeschaltete Elemente) stehen nie in einer Kombination; jede
    erzeugte Kombination traegt ihre Situation.

    **Namen** (Paket R2-C1, Entscheidung des Anwenders vom 04.10.2026: eine
    Lastkombination heisst LK und traegt ihre Nummer): jede erzeugte
    Kombination heisst LK<n> mit der naechsten freien Nummer, Art "LK". Der
    Typ (ULS, ACC, SLS_CH, SLS_FR, SLS_QP) bleibt ihr eigenes Merkmal, und die
    **Bezeichnung** sagt kurz, was sie ist - Art und Leiteinwirkung, bei
    Bedarf die Begleiteinwirkungen: „GZT, Leit LF3 (mit LF2, LF5)“,
    „GZG char., Leit LF3“, „GZT 6.10a (mit LF2)“, „GZG quasi-ständig, nur
    ständig“, „GZT außergew. LF9, Leit LF3“, dazu „, G günstig“, wenn die
    ständigen Lasten günstig angesetzt sind, und „[Situation]“ in einer
    Stellung. Warum so: Art und Leiteinwirkung sind das, wonach der Anwender
    in der Liste sucht; die Begleiteinwirkungen trennen Kombinationen mit
    gleicher Leiteinwirkung voneinander, und der Lastfall steht mit seinem
    **Namen** (LF3) da und nicht mit seiner Bezeichnung, damit sich die
    Bezeichnung des Lastfalls ohne Folgen ändern lässt. Bis zu diesem Stand
    hießen sie GZT<n>, GZT-A<n> und GZG<n> mit einem gemeinsamen Zähler;
    Reihenfolge und Zahl sind geblieben (Halle: GZT1…GZT42 sind LK1…LK42,
    GZG43…GZG72 sind LK43…LK72).

    **Nie etwas überschreiben, nur Eigenes ersetzen.** Die Nummer kommt aus
    der Folge der freien Nummern und überspringt jede vergebene - im Feld
    ``nummer`` und im Namen -: eine Handkombination LK5 bleibt, wie sie ist
    (R2-A1: bis dahin ersetzte der Generator still eine Handkombination
    „GZT2“, gemessen mit 9,99·LF2 in tests/test_namen_lf_lk.py, N6).
    Ersetzt wird nur, was dieser Generator selbst erzeugt hat und was seitdem
    niemand angefasst hat (:func:`gehoert_dem_generator`, über den
    **Fingerabdruck** ``erzeugt`` und ``unberuehrt``, nie über den Namen): eine
    erzeugte Kombination, die der Anwender umbenannt oder geändert hat,
    gehört ihm.

    **Nummern halten.** Ein erneuter Lauf gibt jeder Kombination ihre Nummer
    zurück, wenn ihr Inhalt (Typ, Situation, Faktoren) derselbe ist - eine
    Ermüdungslast auf LK17, ein Berichtseintrag oder eine Stellung zeigt dann
    weiter auf dieselbe Kombination. Neue Kombinationen füllen zuerst die
    Lücken, die ersetzte hinterlassen haben (niedrigste Nummer zuerst, in der
    Reihenfolge der Erzeugung), danach geht es hinter der höchsten weiter. Eine
    Nummer, die im Modell noch genannt wird (Ermüdungslast, Stellung,
    Berichtseintrag) und keiner Kombination mehr gehört, wird nie neu
    vergeben: der Verweis zeigt ins Leere, und Model.check sagt es, statt
    still auf eine andere Kombination zu zeigen."""
    ds = model.design
    rule = rule or ds.combination_rule
    # Lastfaelle ohne Einwirkung: gamma und psi stehen nicht fest. Der Generator
    # liesse sie sonst still weg (weder staendig noch veraenderlich) - er weigert
    # sich, bevor er vorhandene Kombinationen ersetzt.
    offen = model.lastfaelle_ohne_einwirkung()
    if offen:
        raise KombinationGesperrt(sperrhinweis_erzeugen(offen), lastfaelle=offen)
    # erst entwerfen, dann ersetzen: scheitert der Entwurf („Zu viele Kombinationen“),
    # bleibt das Modell, wie es ist
    entwuerfe: list = []
    seen: set = set()
    for sit, namen in model.lastfaelle_je_situation().items():
        faelle = [model.load_cases[k] for k in namen]
        _kombinationen_bilden(model, faelle, sit, uls, sls, accidental, rule, g_favourable,
                              max_combinations, entwuerfe, seen)
    ersetzt: list = []
    if replace:
        ersetzt = [c for c in model.combinations.values() if gehoert_dem_generator(c)]
        weg = {id(c) for c in ersetzt}
        for k in [k for k, c in model.combinations.items() if id(c) in weg]:
            del model.combinations[k]
    return kombinationen_anlegen(model, GENERATOR, entwuerfe, ersetzt)


#: Name dieses Generators in Combination.erzeugt
GENERATOR = "EN 1990"


def gehoert_dem_generator(c: Combination) -> bool:
    """Ob der Generator die Kombination *c* ersetzen darf: er hat sie selbst
    erzeugt, und niemand hat sie seitdem angefasst (Combination.unberuehrt -
    umbenannt, Faktoren, Typ, Beschreibung, Leiteinwirkung geaendert macht
    sie zur Kombination des Anwenders). Gefunden wird sie am Fingerabdruck,
    nie am Namen: nach der Umstellung beim Laden heisst jede erzeugte
    Kombination LK<n> und traegt ihren Fingerabdruck weiter.

    Eine Kombination aus einer Datei von vor dem 04.10.2026 traegt kein
    Merkmal. Fuer sie gilt die alte Regel - Beschreibung „auto…“ -, aber nur,
    solange sie noch den Namen des Generators traegt (GZT<n>, GZT-A<n>,
    GZG<n>): eine umbenannte bleibt. Mehr laesst sich ohne Merkmal nicht
    sagen; die Umstellung beim Laden (Paket R2-A2) setzt es."""
    import re
    if getattr(c, "erzeugt", ""):
        return c.unberuehrt(GENERATOR)
    return (str(c.description or "").startswith("auto")
            and re.fullmatch(r"(GZT|GZT-A|GZG)\d+", str(c.name)) is not None)


# ==========================================================================
# Nummern und Anlegen - gemeinsam fuer alle Kombinationsgeneratoren
# ==========================================================================
def inhaltsschluessel(typ: str, situation: str, faktoren: dict) -> tuple:
    """Woran der Generator eine Kombination wiedererkennt, wenn er sie neu
    erzeugt: Typ, Situation und Faktoren (auf sechs Stellen gerundet, wie der
    Generator sie legt) - nie ihr Name."""
    return (str(typ), str(situation or ""),
            tuple(sorted((str(k), round(float(v), 6)) for k, v in faktoren.items())))


def _kombinationen_genannt(model: Model) -> set:
    """Die Namen von Kombinationen, auf die im Modell etwas zeigt: Zustand und
    Verlauf einer Ermuedungslast, Kombinationsliste einer Stellung,
    Berichtseintrag „combo:“."""
    namen: set = set()
    for fl in model.fatigue_loads.values():
        namen.update(x for x in (fl.case_max, fl.case_min) if x)
        namen.update(x for x in (getattr(fl, "folge", None) or []) if x)
    for s in getattr(model, "stellungen", None) or []:
        namen.update(x for x in (getattr(s, "kombinationen", None) or []) if x)
    for e in getattr(model, "bericht", None) or []:
        q = str(getattr(e, "quelle", "") or "")
        if q.startswith("combo:"):
            namen.add(q[len("combo:"):])
    return namen


def kombinationen_anlegen(model: Model, generator: str, entwuerfe: list, ersetzt: list = ()) -> list:
    """Die Entwuerfe eines Generators als Lastkombinationen LK<n> im Modell
    ablegen und die angelegten Kombinationen zurueckgeben (R2-C1).

    *entwuerfe*: Woerterbuecher mit ``factors``, ``typ``, ``description``,
    ``leading``, ``situation`` und ``bezeichnung`` - ohne Namen und ohne Nummer.
    *ersetzt*: die Kombinationen, die der Generator eben aus dem Modell
    genommen hat (sie stehen nicht mehr in ``model.combinations``); ihre
    Nummern werden gehalten, wo der Inhalt derselbe ist
    (:func:`inhaltsschluessel`), sonst nach der Regel von
    :func:`generate_combinations` vergeben.

    Jede Kombination bekommt den Namen LK<Nummer> und die Art "LK" und traegt
    den Fingerabdruck des Generators (Combination.als_erzeugt). Eine vergebene
    Nummer - Feld oder Name, Lastfall oder Kombination - wird nie vergeben."""
    from .model import _namensnummer
    belegt: set = set()
    for c in model.combinations.values():
        if c.art == "LK":
            belegt.add(int(c.nummer or 0))
    for n in list(model.load_cases) + list(model.combinations):
        a, z = _namensnummer(n)
        if a == "LK":
            belegt.add(z)
    belegt.discard(0)
    gesperrt = {z for a, z in (_namensnummer(n) for n in _kombinationen_genannt(model))
                if a == "LK"} - belegt
    alte: dict = {}
    for c in ersetzt:
        nr = int(c.nummer or 0)
        if nr > 0 and c.art == "LK":
            alte.setdefault(inhaltsschluessel(c.typ, c.situation, c.factors), nr)
    nummern: list = [0] * len(entwuerfe)
    benutzt: set = set()
    for i, e in enumerate(entwuerfe):
        nr = alte.get(inhaltsschluessel(e["typ"], e["situation"], e["factors"]), 0)
        # dieselbe Nummer fuer denselben Inhalt - auch dann, wenn etwas auf sie
        # zeigt: der Verweis zeigt weiter auf dieselbe Kombination
        if nr and nr not in belegt and nr not in benutzt:
            nummern[i] = nr
            benutzt.add(nr)
    luecken = sorted(set(alte.values()) - benutzt - belegt - gesperrt)
    naechste = max(belegt | benutzt | set(alte.values()) | gesperrt, default=0) + 1
    li = 0
    for i in range(len(entwuerfe)):
        if nummern[i]:
            continue
        if li < len(luecken):
            nummern[i] = luecken[li]
            li += 1
        else:
            while naechste in belegt or naechste in benutzt or naechste in gesperrt:
                naechste += 1
            nummern[i] = naechste
            naechste += 1
        benutzt.add(nummern[i])
    angelegt: list = []
    for e, nr in zip(entwuerfe, nummern):
        c = Combination(f"LK{nr}", e["factors"], e["typ"], e["description"], e.get("leading", ""),
                        situation=e["situation"], nummer=nr, art="LK",
                        bezeichnung=e.get("bezeichnung", "")).als_erzeugt(generator)
        model.combinations[c.name] = c
        angelegt.append(c)
    return angelegt


def _bezeichnung(art: str, leit: str = "", begleit=(), nur: str = "", guenstig: bool = False,
                 situation: str = "") -> str:
    """Die kurze Bezeichnung einer erzeugten Kombination, etwa „GZT, Leit LF3
    (mit LF2, LF5), G günstig“ (Muster und Begruendung bei
    :func:`generate_combinations`)."""
    t = art
    if leit:
        t += f", Leit {leit}"
        if begleit:
            t += f" (mit {', '.join(begleit)})"
    elif begleit:
        t += f" (mit {', '.join(begleit)})"
    elif nur:
        t += f", nur {nur}"
    if guenstig:
        t += ", G günstig"
    if situation:
        t += f" [{situation}]"
    return t


def _kombinationen_bilden(model: Model, faelle: list, situation: str, uls: bool, sls: bool,
                          accidental: bool, rule: str, g_favourable: bool,
                          max_combinations: int, entwuerfe: list, seen: set):
    """Die Kombinationen einer Situation nach DIN EN 1990 (6.10, 6.10a/b,
    6.11b, 6.14b, 6.15b, 6.16b) als Entwuerfe ohne Namen und Nummer; die
    Namen vergibt :func:`kombinationen_anlegen`."""
    from .model import GRUNDSTELLUNG
    ds = model.design
    # Bemessungslastfaelle (schon faktorisiert) stehen fuer sich: sie werden
    # nicht mit anderen Lastfaellen ueberlagert, sondern gehen als eigene
    # GZT-Kombination mit 1,0 ein (unten)
    fakt = [lc for lc in faelle if getattr(lc, "faktorisiert", False)]
    faelle = [lc for lc in faelle if not getattr(lc, "faktorisiert", False)]
    perm = [lc for lc in faelle if lc.is_permanent]
    var = [lc for lc in faelle if lc.is_variable]
    acc = [lc for lc in faelle if lc.is_accidental]
    sit = "" if situation == GRUNDSTELLUNG else situation
    zusatz = f" [{situation}]" if sit else ""

    def add(art, factors, typ, desc, leading="", begleit=(), nur="", fav=False):
        factors = {k: round(v, 6) for k, v in factors.items() if abs(v) > 1e-12}
        if not factors:
            return
        key = (typ, sit, tuple(sorted(factors.items())))
        if key in seen:
            return
        seen.add(key)
        # Begleiteinwirkungen: nur die, die mit ihrem Faktor wirklich in der
        # Kombination stehen (psi = 0 laesst sie weg)
        begl = [lc.name for lc in begleit if lc.name in factors]
        entwuerfe.append({"factors": factors, "typ": typ, "description": "auto: " + desc + zusatz,
                          "leading": leading, "situation": sit,
                          "bezeichnung": _bezeichnung(art, leading, begl, nur, fav, sit)})

    g_variants = [False, True] if (g_favourable and var) else [False]
    var_sets = _variable_sets(var) if var else [[]]
    if len(var_sets) * max(1, len(var)) > max_combinations:
        raise RuntimeError(f"Zu viele Kombinationen ({len(var_sets)}); bitte "
                           f"Ausschlussgruppen verwenden oder Lastfaelle zusammenfassen")

    # ---------------- Bemessungslastfaelle ----------------
    if uls:
        for lc in fakt:
            add("GZT", {lc.name: 1.0}, "ULS",
                f"Bemessungslastfall {lc.name}, bereits faktorisiert (gamma 1,0, ohne psi)")

    # ---------------- GZT (STR/GEO) ----------------
    if uls:
        for fav in g_variants:
            gf = {lc.name: _gamma(lc, ds, fav) for lc in perm}
            gdesc = "G guenstig" if fav else "G unguenstig"
            if not var:
                add("GZT", gf, "ULS", f"6.10 nur staendig, {gdesc}", nur="ständig", fav=fav)
            for vs in var_sets:
                if not vs:
                    add("GZT", gf, "ULS", f"6.10 nur staendig, {gdesc}", nur="ständig", fav=fav)
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
                        add("GZT 6.10a", f_a, "ULS", f"6.10a, {gdesc}", begleit=vs, nur="ständig",
                            fav=fav)
                        f_b = {k: (v * ds.xi if k in gf else v) for k, v in f.items()}
                        add("GZT 6.10b", f_b, "ULS", f"6.10b Leit {lead.name}, {gdesc}", lead.name,
                            begleit=[lc for lc in vs if lc is not lead], fav=fav)
                    else:
                        add("GZT", f, "ULS", f"6.10 Leit {lead.name}, {gdesc}", lead.name,
                            begleit=[lc for lc in vs if lc is not lead], fav=fav)

    # ---------------- Aussergewoehnlich ----------------
    if accidental and acc:
        for a in acc:
            gf = {lc.name: 1.0 for lc in perm}
            gf[a.name] = 1.0
            for vs in var_sets:
                if not vs:
                    add(f"GZT außergew. {a.name}", gf, "ACC", f"6.11b {a.name} ohne Q", a.name)
                    continue
                for lead in vs:
                    f = dict(gf)
                    f[lead.name] = lead.psi_factors[1]
                    for lc in vs:
                        if lc is not lead:
                            f[lc.name] = lc.psi_factors[2]
                    add(f"GZT außergew. {a.name}", f, "ACC", f"6.11b {a.name}, Leit {lead.name}",
                        lead.name, begleit=[lc for lc in vs if lc is not lead])

    # ---------------- GZG ----------------
    if sls:
        gf = {lc.name: 1.0 for lc in perm}
        if not var:
            add("GZG char.", gf, "SLS_CH", "6.14b charakteristisch", nur="ständig")
        for vs in var_sets:
            if not vs:
                add("GZG char.", gf, "SLS_CH", "6.14b charakteristisch (nur G)", nur="ständig")
                add("GZG quasi-ständig", gf, "SLS_QP", "6.16b quasi-staendig (nur G)", nur="ständig")
                continue
            for lead in vs:
                f = dict(gf)
                f[lead.name] = 1.0
                for lc in vs:
                    if lc is not lead:
                        f[lc.name] = lc.psi_factors[0]
                rest = [lc for lc in vs if lc is not lead]
                add("GZG char.", f, "SLS_CH", f"6.14b charakteristisch, Leit {lead.name}", lead.name,
                    begleit=rest)
                f = dict(gf)
                f[lead.name] = lead.psi_factors[1]
                for lc in vs:
                    if lc is not lead:
                        f[lc.name] = lc.psi_factors[2]
                add("GZG häufig", f, "SLS_FR", f"6.15b haeufig, Leit {lead.name}", lead.name,
                    begleit=rest)
            f = dict(gf)
            for lc in vs:
                f[lc.name] = lc.psi_factors[2]
            add("GZG quasi-ständig", f, "SLS_QP", "6.16b quasi-staendig", begleit=vs, nur="ständig")


def combination_table(model: Model, theorie=None) -> list[list[str]]:
    """Tabellarische Darstellung (fuer Bericht/GUI): Kopfzeile + Zeilen.

    ``theorie``: Kombination -> Text der Spalte "Theorie". Ohne Angabe steht
    dort die Einstellung (``model.theorie_von``). Der Bericht gibt die
    **gerechnete** Theorie (Report._theorie_spalte): scheitert Theorie II/III
    einer Kombination, steht deren lineares Ergebnis, und die Einstellung
    allein wies weiter "II"/"III" aus (Befund B132, gemessen 23.09.2026)."""
    names = list(model.load_cases)
    head = ["Kombination", "Typ", "Leit", "Situation", "Theorie"] + names + ["Beschreibung"]
    rows = [head]
    if theorie is None:
        theorie = model.theorie_von if hasattr(model, "theorie_von") else (lambda _c: "I")
    for c in model.combinations.values():
        # der Typ im Klartext („GZT (STR/GEO)“) - bis zum 03.10.2026 der
        # Schluessel („ULS“), den der Bericht an einer Stelle nachtraeglich
        # uebersetzte und an der anderen (Tabelleneintrag) nicht
        rows.append([c.name, typ_kurz(c.typ), c.leading, getattr(c, "situation", "") or "Grundstellung",
                     theorie(c)]
                    + [f"{c.factors.get(n, 0):g}" if c.factors.get(n, 0) else "" for n in names]
                    + [c.description])
    return rows
