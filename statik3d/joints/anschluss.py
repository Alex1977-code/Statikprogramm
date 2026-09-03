"""
Anschluesse als Teil des Modells: nachweisen und dokumentieren.

Die Rechenteile fuer Schrauben, Naehte und T-Stummel stehen in ``bolts.py``,
``welds.py``, ``tstub.py`` und ``design.py``; die Geometrievorschlaege in
``templates.py``. Dieses Modul schlaegt die Bruecke zum Modell:

* eine Vorlage (``EndPlate``, ``Splice``, ``Gusset``) wird zu einem
  ``model.Joint`` und wieder zurueck - dadurch wird der Anschluss
  **mitgespeichert** und ueberlebt Rueckgaengig, Speichern und Laden;
* die Schnittgroessen kommen aus der Rechnung, nicht aus einem Dialogfeld:
  jeder Anschluss wird ueber **alle GZT-Kombinationen** gefuehrt, die
  unguenstigste ist massgebend;
* die Ermuedung nutzt die Ermuedungslasten des Modells: je Last die
  Schwingbreite der Stabendschnittgroessen, die Schaedigungen werden nach
  Palmgren-Miner ueber alle Lasten aufsummiert.

    from statik3d.joints.anschluss import check_joints
    an = solver.solve_all(model, design=True)
    print(an.joints.summary())

Vorzeichen: die Stabendschnittgroessen werden so gedreht, dass eine positive
Normalkraft am betrachteten Ende **Zug** bedeutet - dieselbe Zaehlweise wie in
``solver.beam_end_forces``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields

from ..model import Model, Joint
from .bolts import Bolt
from .templates import TEMPLATES

#: Felder der Vorlagen, die nicht zur Geometrie gehoeren
NICHT_GEOMETRIE = {"name", "model", "elem", "end", "bolt", "grade", "fy", "fu",
                   "gamma_M0", "gamma_M2", "hinweise", "sec"}

#: Felder der Schraube, die im Modell stehen
SCHRAUBENFELDER = ("size", "grade", "hole", "preloaded", "mu", "shear_planes",
                   "threads_in_shear", "countersunk", "category")

#: Welches Schluesselwort die Ermuedung der jeweiligen Vorlage erwartet
ERMUEDUNGSGROESSE = {"kopfplatte": "dMy", "lasche": "dN", "diagonale": "dN"}

#: kurze Bezeichnung fuer Tabellen und Bericht
KURZ = {"kopfplatte": "Kopfplatte", "lasche": "Laschenstoß", "diagonale": "Knotenblech"}

#: Welche Schnittgroessen die Vorlage im Nachweis verwendet
KRAEFTE = {"kopfplatte": ("N", "Vz", "My"), "lasche": ("N", "Vz", "My"),
           "diagonale": ("N",)}


# --------------------------------------------------------------------------
# Vorlage <-> Modell
# --------------------------------------------------------------------------
def geometrie_von(t) -> dict:
    """Die Geometriefelder einer Vorlage als einfaches Woerterbuch."""
    return {f.name: getattr(t, f.name) for f in fields(t)
            if f.name not in NICHT_GEOMETRIE}


def schraube_von(b: Bolt) -> dict:
    return {k: getattr(b, k) for k in SCHRAUBENFELDER}


def als_joint(t, name: str = None, **kw) -> Joint:
    """Aus einer Vorlage das Modellobjekt machen."""
    typ = next((k for k, cls in TEMPLATES.items() if isinstance(t, cls)), "")
    if not typ:
        raise TypeError(f"{type(t).__name__} ist keine Anschlussvorlage")
    return Joint(name or t.name, typ, int(t.elem), int(t.end),
                 geometrie=geometrie_von(t), schraube=schraube_von(t.bolt), **kw)


def vorlage(model: Model, joint: Joint):
    """Aus dem Modellobjekt die rechenfaehige Vorlage bauen."""
    if joint.typ not in TEMPLATES:
        raise KeyError(f"Anschlusstyp '{joint.typ}' unbekannt: {sorted(TEMPLATES)}")
    e = model.elements[int(joint.elem)]
    if not e.sec or e.sec not in model.sections:
        raise ValueError(f"Element {joint.elem + 1} hat keinen Querschnitt")
    sec = model.sections[e.sec]
    mat = model.materials[e.mat]
    ds = model.design
    t = TEMPLATES[joint.typ](
        name=joint.name, model=model, elem=int(joint.elem), end=int(joint.end),
        grade=mat.grade or "S355",
        fy=mat.yield_strength(sec.t_max) or 355e6,
        fu=mat.ultimate_strength(sec.t_max) or 490e6,
        gamma_M0=ds.gamma_M0, gamma_M2=ds.gamma_M2, sec=sec)
    if joint.schraube:
        t.bolt = Bolt(**{k: v for k, v in joint.schraube.items()
                         if k in SCHRAUBENFELDER}, gamma_M2=ds.gamma_M2)
    for k, v in (joint.geometrie or {}).items():
        if hasattr(t, k):
            setattr(t, k, v)
    return t


# --------------------------------------------------------------------------
# Schnittgroessen am Stabende
# --------------------------------------------------------------------------
def endkraefte(res, elem: int, end: int) -> dict:
    """N, V_z und M_y am Stabende [N, Nm]. Positives N heisst Zug."""
    v = getattr(res, "beam_end", {}).get(int(elem))
    if v is None:
        return {}
    o, vz = (0, -1.0) if int(end) == 0 else (6, 1.0)
    return {"N": vz * float(v[o + 0]), "Vz": vz * float(v[o + 2]),
            "My": vz * float(v[o + 4])}


def _nur(kraefte: dict, typ: str) -> dict:
    return {k: kraefte.get(k, 0.0) for k in KRAEFTE.get(typ, ("N", "Vz", "My"))}


def _stab(model: Model, joint: Joint) -> str:
    """Der Stab, zu dem das Element des Anschlusses gehoert."""
    return next((n for n, m in model.members.items() if int(joint.elem) in m.elements), "")


#: Felder, die die Stuetze beschreibt
STUETZENFELDER = ("h", "b", "tw", "tf", "r", "A", "fy", "versteift", "schubfeld", "beta")


def stuetze_aufloesen(model: Model, joint: Joint) -> dict:
    """Die Angaben der Stuetze - aus dem Querschnitt des Modells oder von Hand.

    ``joint.stuetze = {"section": "HEB 300"}`` genuegt: die Abmessungen kommen
    dann aus der Profildatenbank des Modells. Einzelne Werte lassen sich
    daneben ueberschreiben.
    """
    st = dict(joint.stuetze or {})
    name = st.pop("section", "")
    if name:
        sec = model.sections.get(name)
        if sec is None:
            return {"fehler": f"Stützenquerschnitt „{name}“ gibt es im Modell nicht"}
        aus = {"h": sec.h, "b": sec.b, "tw": sec.tw, "tf": sec.tf, "r": sec.r,
               "A": sec.A}
        aus.update({k: v for k, v in st.items() if k in STUETZENFELDER})
        return aus
    return {k: v for k, v in st.items() if k in STUETZENFELDER}


def _I_b(model: Model, joint: Joint) -> float:
    e = model.elements[int(joint.elem)]
    sec = model.sections.get(e.sec)
    return float(sec.Iy) if sec is not None else 0.0


def _L_b(model: Model, joint: Joint) -> float:
    """Stuetzweite des angeschlossenen Traegers fuer die Klassifizierung.

    Massgebend ist die Laenge des **Stabes**, nicht die des einzelnen
    Elements - sonst faellt die Grenze 8 E I_b / L_b viel zu hoch aus.
    """
    name = _stab(model, joint)
    if name:
        try:
            return float(model.member_length(model.members[name]))
        except Exception:                # noqa: BLE001
            pass
    return float(model.element_length(int(joint.elem)))


# --------------------------------------------------------------------------
# Wie sitzt der Anschluss in der Rechnung?
# --------------------------------------------------------------------------
def modellierung(joint: Joint, gelenk=None) -> tuple:
    """(Art, Steifigkeit, Klartext) - wie der Anschluss abgebildet wird.

    Art: "starr" (nichts zu tun), "gelenkig" (Momentengelenk) oder
    "feder" (Drehfeder mit S_j).

    "automatisch" folgt der Klassifizierung nach 5.2.2: ein starrer Anschluss
    wird starr gerechnet, ein gelenkiger als Gelenk, ein nachgiebiger mit
    seiner Drehfeder S_j = S_j,ini/eta (5.1.2(4)).
    """
    wahl = (joint.modellierung or "automatisch").lower()
    if joint.S_j and wahl in ("automatisch", "feder"):
        return ("feder", float(joint.S_j),
                f"Drehfeder S_j = {float(joint.S_j) / 1e6:.1f} MNm/rad (von Hand)")
    if wahl == "starr":
        return ("starr", float("inf"), "starr gerechnet (vorgegeben)")
    if wahl == "gelenkig":
        return ("gelenkig", 0.0, "als Momentengelenk gerechnet (vorgegeben)")
    if wahl == "feder":
        S = float(getattr(gelenk, "S_j", 0.0) or 0.0)
        if S <= 0:
            return ("starr", float("inf"), "starr gerechnet (keine Steifigkeit bekannt)")
        return ("feder", S, f"Drehfeder S_j = {S / 1e6:.1f} MNm/rad (5.1.2(4))")
    # automatisch
    if gelenk is None or not gelenk.klasse:
        return ("starr", float("inf"), "starr gerechnet (nicht klassifiziert)")
    if gelenk.klasse == "starr":
        return ("starr", float("inf"), "starr gerechnet (Klasse starr nach 5.2.2.5)")
    if gelenk.klasse == "gelenkig":
        return ("gelenkig", 0.0, "als Momentengelenk gerechnet (Klasse gelenkig)")
    S = float(gelenk.S_j or 0.0)
    if not math.isfinite(S) or S <= 0:
        return ("starr", float("inf"), "starr gerechnet (Steifigkeit unendlich)")
    return ("feder", S,
            f"nachgiebig: Drehfeder S_j = {S / 1e6:.1f} MNm/rad (S_j,ini/η, 5.1.2(4))")


#: lokaler Freiheitsgrad der Biegung um die starke Achse am Stabende
DOF_MY = {0: 4, 1: 10}


def federn_setzen(model: Model, log: list = None) -> dict:
    """Die Anschluesse als Drehfeder oder Gelenk an die Stabenden legen.

    Wird vor jeder Berechnung aufgerufen und ist wiederholbar: die Wirkung
    haengt nur an den Anschluessen des Modells, frueher gesetzte Werte
    derselben Stabenden werden ersetzt.
    """
    gesetzt = {}
    for name, j in model.joints.items():
        if not j.design or not 0 <= int(j.elem) < len(model.elements):
            continue
        try:
            t = vorlage(model, j)
            st = stuetze_aufloesen(model, j)
            g = t.momenten_rotation(stuetze={} if st.get("fehler") else st,
                                    rahmen=j.rahmen, I_b=_I_b(model, j),
                                    L_b=_L_b(model, j))
        except Exception as ex:              # noqa: BLE001
            if log is not None:
                log.append(f"Anschluss {name}: Steifigkeit unbekannt ({ex})")
            continue
        art, S, text = modellierung(j, g)
        d = DOF_MY[int(j.end)]
        e = model.elements[int(j.elem)]
        federn = {k: v for k, v in (e.hinge_springs or []) if k != d}
        e.hinges = sorted(set(e.hinges) - {d})
        if art == "feder" and math.isfinite(S) and S > 0:
            federn[d] = S
        elif art == "gelenkig":
            e.hinges = sorted(set(e.hinges) | {d})
        e.hinge_springs = sorted(federn.items())
        gesetzt[name] = (art, S, text)
        if log is not None:
            log.append(f"Anschluss {name}: {text}")
    return gesetzt


# --------------------------------------------------------------------------
# Ergebnis
# --------------------------------------------------------------------------
@dataclass
class AnschlussCheck:
    """Alle Nachweise eines Anschlusses, ueber alle Kombinationen gefuehrt."""
    name: str
    typ: str = ""
    elem: int = 0
    end: int = 1
    ort: str = ""
    beschreibung: str = ""
    util: float = 0.0                 # groesste Ausnutzung im GZT
    D: float = 0.0                    # groesste Schaedigungssumme der Ermuedung
    kombination: str = ""             # massgebende Kombination
    massgebend: str = ""              # Name des massgebenden Nachweises
    kraefte: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    je_kombination: list = field(default_factory=list)
    ermuedung: list = field(default_factory=list)
    hinweise: list = field(default_factory=list)
    gelenk: object = None             # Gelenkkennwerte (Steifigkeit, Klasse, Rotation)
    modelliert: str = ""              # wie der Anschluss in der Rechnung sitzt
    fehler: str = ""

    @property
    def eta(self) -> float:
        """Die groessere der beiden Ausnutzungen - Tragfaehigkeit oder Ermuedung."""
        return max(self.util, self.D)

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.eta <= 1.0 else "NICHT erfüllt"


@dataclass
class AnschlussResults:
    joints: dict = field(default_factory=dict)
    combinations: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def util_max(self) -> float:
        return max((j.eta for j in self.joints.values()), default=0.0)

    def summary(self) -> str:
        if not self.joints:
            return "Anschlüsse: keine"
        schlecht = [j.name for j in self.joints.values() if j.eta > 1.0]
        fehler = [j.name for j in self.joints.values() if j.fehler]
        worst = max(self.joints.values(), key=lambda j: j.eta)
        wo = (f"Ermüdung, D = {worst.D:.3f}" if worst.D > worst.util
              else worst.massgebend + (f", {worst.kombination}" if worst.kombination else ""))
        s = (f"Anschlüsse: {len(self.joints)}, {len(self.combinations)} Kombinationen, "
             f"max. Ausnutzung {worst.eta:.3f} ({worst.name}: {wo})")
        if schlecht:
            s += f" - {len(schlecht)} NICHT erfüllt: " + ", ".join(schlecht)
        elif not fehler:
            s += " - alle erfüllt"
        if fehler:
            s += f" - {len(fehler)} nicht geführt: " + ", ".join(fehler)
        return s

    def table(self) -> list[list]:
        rows = [["Anschluss", "Typ", "Ort", "Ausnutzung", "massgebender Nachweis",
                 "Kombination", "D (Ermüdung)", "Status"]]
        for j in self.joints.values():
            rows.append([j.name, KURZ.get(j.typ, j.typ),
                         j.ort, f"{j.util:.3f}", j.massgebend or j.fehler,
                         j.kombination, f"{j.D:.3f}" if j.D else "-", j.status()])
        return rows


# --------------------------------------------------------------------------
# Nachweis
# --------------------------------------------------------------------------
def _checkliste(j) -> list:
    return [{"name": c.name, "E": float(c.E), "R": float(c.R), "einheit": c.einheit,
             "eta": float(c.eta), "hinweis": c.hinweis} for c in j.checks]


def _ermuedung_zusammenfassen(teile: list) -> list:
    """Schaedigungen gleicher Kerbfaelle ueber alle Ermuedungslasten summieren."""
    out: dict = {}
    for last, e in teile:
        k = (e["kerbfall"], e["steigung"], e["beschreibung"])
        z = out.setdefault(k, {"kerbfall": e["kerbfall"], "steigung": e["steigung"],
                               "beschreibung": e["beschreibung"],
                               "gamma_Mf": e["gamma_Mf"], "schaedigung": 0.0,
                               "stufen": [], "N_R": [], "lasten": []})
        z["schaedigung"] += float(e["schaedigung"])
        z["stufen"].extend(e["stufen"])
        z["N_R"].extend(e["N_R"])
        if last not in z["lasten"]:
            z["lasten"].append(last)
    for z in out.values():
        z["ok"] = z["schaedigung"] <= 1.0 + 1e-9
    return list(out.values())


def check_joint(model: Model, joint: Joint, results: dict, analysis=None,
                ermuedung: bool = True) -> AnschlussCheck:
    """Einen Anschluss ueber alle uebergebenen Ergebnisse nachweisen."""
    c = AnschlussCheck(joint.name, joint.typ, int(joint.elem), int(joint.end),
                       joint.ort())
    try:
        t = vorlage(model, joint)
    except Exception as ex:              # noqa: BLE001
        c.fehler = f"{type(ex).__name__}: {ex}"
        return c
    c.beschreibung = t.describe()
    fest = dict(joint.kraefte or {})

    # -- Momenten-Rotations-Verhalten (6.3, 6.2.7, 6.4) ------------------
    try:
        st = stuetze_aufloesen(model, joint)
        if st.get("fehler"):
            c.hinweise.append(st["fehler"])
            st = {}
        c.gelenk = t.momenten_rotation(stuetze=st, rahmen=joint.rahmen,
                                       I_b=_I_b(model, joint), L_b=_L_b(model, joint))
    except Exception as ex:              # noqa: BLE001
        c.hinweise.append(f"Momenten-Rotations-Verhalten nicht bestimmbar: "
                          f"{type(ex).__name__}: {ex}")
    c.modelliert = modellierung(joint, c.gelenk)[2]

    # -- Tragfaehigkeit: jede Kombination fuehren ------------------------
    faelle = []
    if fest:
        faelle.append(("von Hand", _nur(fest, joint.typ)))
    else:
        for name, res in results.items():
            k = endkraefte(res, joint.elem, joint.end)
            if k:
                faelle.append((name, _nur(k, joint.typ)))
    if not faelle:
        c.fehler = ("keine Stabendschnittgrößen für Element "
                    f"{joint.elem + 1} - wurde gerechnet?")
        return c

    bestes = None
    for name, k in faelle:
        try:
            j = t.design(**k)
        except Exception as ex:          # noqa: BLE001
            c.fehler = f"{type(ex).__name__}: {ex}"
            return c
        # Momententragfaehigkeit des Anschlusses (6.2.7) - sie gehoert zu den
        # Nachweisen, nicht nur in die Kennwerte.
        M_j = float(getattr(c.gelenk, "M_j_Rd", 0.0) or 0.0)
        if M_j > 0 and "My" in k:
            from .design import Check
            j.add(Check("Momententragfähigkeit M_j,Rd (6.2.7)", abs(k["My"]), M_j,
                        einheit="kNm",
                        hinweis=f"{c.gelenk.tragklasse}"
                                + (f", {c.gelenk.klasse}" if c.gelenk.klasse else "")))
        c.je_kombination.append({"kombination": name, "eta": float(j.eta),
                                 "massgebend": j.massgebend, **k})
        if bestes is None or j.eta > bestes[1].eta:
            bestes = (name, j, k)
    name, j, k = bestes
    c.util = float(j.eta)
    c.kombination = name
    c.massgebend = j.massgebend
    c.kraefte = dict(k)
    c.checks = _checkliste(j)
    # frueher gesammelte Hinweise (Steifigkeit, Stuetze) bleiben stehen
    c.hinweise += [h for h in j.hinweise if h not in c.hinweise]

    # -- Ermuedung: je Ermuedungslast die Schwingbreite -------------------
    if not ermuedung:
        return c
    alle = analysis.all_results() if hasattr(analysis, "all_results") else {}
    namen = joint.ermuedung or list(model.fatigue_loads)
    schluessel = ERMUEDUNGSGROESSE.get(joint.typ, "dN")
    teile = []
    for fn in namen:
        fl = model.fatigue_loads.get(fn)
        if fl is None:
            c.hinweise.append(f"Ermüdungslast '{fn}' gibt es nicht")
            continue
        if fl.case_max not in alle:
            c.hinweise.append(f"Ermüdungslast {fl.name}: Ergebnis "
                              f"'{fl.case_max}' fehlt")
            continue
        oben = endkraefte(alle[fl.case_max], joint.elem, joint.end)
        unten = (endkraefte(alle[fl.case_min], joint.elem, joint.end)
                 if fl.case_min and fl.case_min in alle else {})
        groesse = "My" if schluessel == "dMy" else "N"
        d = abs(oben.get(groesse, 0.0) - unten.get(groesse, 0.0)) * fl.factor
        if d <= 0:
            continue
        try:
            je = t.design(**k, n_cycles=fl.cycles, **{schluessel: d})
        except Exception as ex:          # noqa: BLE001
            c.hinweise.append(f"Ermüdung {fl.name}: {type(ex).__name__}: {ex}")
            continue
        for e in je.ermuedung:
            teile.append((fl.name, e))
        for h in je.hinweise:
            if h not in c.hinweise:
                c.hinweise.append(h)
    c.ermuedung = _ermuedung_zusammenfassen(teile)
    c.D = max((e["schaedigung"] for e in c.ermuedung), default=0.0)
    return c


def check_joints(model: Model, analysis, combos: list = None, progress=None,
                 ermuedung: bool = True) -> AnschlussResults:
    """Alle Anschluesse des Modells nachweisen."""
    from ..ec3.design import _uls_results
    results = _uls_results(model, analysis, combos)
    out = AnschlussResults(combinations=list(results), settings={
        "gamma_M0": model.design.gamma_M0, "gamma_M2": model.design.gamma_M2,
        "gamma_Ff": model.design.gamma_Ff,
        "Norm": "DIN EN 1993-1-8 (Tragfähigkeit), DIN EN 1993-1-9 (Ermüdung)"})
    namen = [n for n, j in model.joints.items() if j.design]
    for i, n in enumerate(namen):
        out.joints[n] = check_joint(model, model.joints[n], results, analysis,
                                    ermuedung=ermuedung)
        if progress:
            progress(f"Anschluss {n} ({i + 1}/{len(namen)})")
    return out
