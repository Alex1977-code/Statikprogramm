"""
Nachweisfuehrung fuer Staebe (Member) nach DIN EN 1993-1-1:
Querschnittsnachweise an allen Nachweisstellen und Stabilitaetsnachweise je
Stab fuer alle Kombinationen im Grenzzustand der Tragfaehigkeit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import os

import numpy as np

from ..model import Model, Member
from .section_class import classify
from .resistance import section_check
from .stability import member_stability
from . import woelb


@dataclass
class MemberCheck:
    member: str
    section: str
    material: str
    L: float
    cls: int = 1
    util: float = 0.0
    governing: dict = field(default_factory=dict)      # {"name","combo","x","util","text","kind"}
    section_checks: list = field(default_factory=list)  # je Kombination: massgebende Stelle
    stability: list = field(default_factory=list)       # je Kombination: dict
    extremes: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    elements: list = field(default_factory=list)
    #: Woelbkrafttorsion je Kombination: {"combo", "B_max", "sigma_w_max",
    #: "x_max", "anteil_woelb", "lamL", "rand", "hinweis"}
    woelb: list = field(default_factory=list)
    #: Warum dieser Nachweis **nicht gefuehrt** wurde - leer, wenn er lief.
    #: Ohne dieses Feld gab ``status()`` fuer einen uebersprungenen Stab
    #: "erfuellt" mit Ausnutzung 0,000 zurueck: ein Stab aus einem
    #: importierten Werkstoff ohne Streckgrenze ging so als bestandener
    #: Nachweis in das Statikdokument ein und senkte zugleich nichts, weil
    #: seine Null die groesste Ausnutzung nicht beruehrt (22.09.2026). Der
    #: Nachbarnachweis Volumen (ec3.volumen.VolumenCheck) unterscheidet an
    #: derselben Stelle seit jeher drei Faelle; hier waren es zwei.
    fehler: str = ""

    def status(self) -> str:
        if self.fehler:
            return "nicht geführt"
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class DesignResults:
    members: dict = field(default_factory=dict)
    combinations: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    #: Kombinationen, die nicht nachgewiesen werden konnten (kein Ergebnis),
    #: im Klartext - siehe _uls_results
    warnungen: list = field(default_factory=list)
    #: Eintraege, unter denen mehrere Namen dasselbe Ergebnis tragen und die
    #: darum nur einmal nachgewiesen wurden: {Eintrag: [alle Namen]} - siehe
    #: _gleiche_zusammenfassen. Ergebnisse von vor dem 23.09.2026 kennen das
    #: Feld nicht (getattr).
    gleiche: dict = field(default_factory=dict)

    @property
    def util_max(self) -> float:
        return max((m.util for m in self.members.values()), default=0.0)

    def util_by_element(self) -> dict:
        """Ausnutzung je Element fuer die Faerbung "Ausnutzung EC3" (Oberflaeche,
        Browser, Bild im Bericht).

        Ein nicht gefuehrter Stab (``fehler``) hat keine Ausnutzung und
        bekommt darum keinen Eintrag: seine Elemente bleiben ohne Wert
        (Oberflaeche grau, Bericht in Stabfarbe). Bis zum 23.09.2026 kam er
        mit seiner 0,0 hinein und wurde gruen (Klasse < 0,50) - ein Stab ohne
        f_y sah aus wie unbeansprucht (Befund B054, Traeger IPE 300 neben
        einem Stab aus Werkstoff ohne Streckgrenze).
        """
        out = {}
        for m in self.members.values():
            if m.fehler:
                continue
            for e in m.elements:
                out[e] = max(out.get(e, 0.0), m.util)
        return out

    def summary(self) -> str:
        if not self.members:
            return "Nachweise EC3: keine Staebe" + warnzeilen(self)
        # Nicht gefuehrte Staebe (``fehler``, etwa Werkstoff ohne
        # Streckgrenze) zaehlen weder als erfuellt noch fuer die groesste
        # Ausnutzung. Bis zum 22.09.2026 stand hier nur ``util > 1``: ein
        # Traeger mit 0,633 und ein Stab ohne f_y ergaben "max. Ausnutzung
        # 0.633 ... - alle erfuellt".
        # Die Zeile steht (main.py, Stand 23.09.2026) im Protokoll und in der
        # Statuszeile nach "Nachweise EC3" (_design_done), im Etikett der
        # Maske Nachweise (lbl_design, Gruppe "Nachweise fuehren", nicht unter
        # der Ergebnistabelle), im Textfeld der Maske Ergebnisse (txt_res,
        # show_results) und ueber Analysis.summary() im Protokoll und im
        # Textfeld der Maske Berechnung (txt_summary, _solve_done).
        # Wie VolumenResults.summary(): "alle erfuellt" nur, wenn nichts offen
        # blieb.
        gefuehrt = [m for m in self.members.values() if not m.fehler]
        ohne = [m for m in self.members.values() if m.fehler]
        nf = sum(1 for m in gefuehrt if m.util > 1.0)
        s = f"Nachweise EC3: {len(self.members)} Staebe, {len(self.combinations)} Kombinationen"
        if gefuehrt:
            worst = max(gefuehrt, key=lambda m: m.util)
            g = worst.governing
            s += (f", max. Ausnutzung {worst.util:.3f} ({worst.member}: {g.get('name', '')}, "
                  f"{g.get('combo', '')}, x = {g.get('x', 0):.2f} m)")
        if nf:
            s += f" - {nf} Staebe NICHT erfuellt"
        elif gefuehrt and not ohne:
            s += " - alle erfuellt"
        if ohne:
            # Namen und Grund, damit man weiss, wo man nachtragen muss; ein
            # Import kann Hunderte Staebe ohne f_y bringen - die Zeile steht
            # auch im Etikett der Maske Nachweise, darum hoechstens zehn Namen.
            namen = ", ".join(m.member for m in ohne[:10])
            if len(ohne) > 10:
                namen += f" und {len(ohne) - 10} weitere"
            gruende = list(dict.fromkeys(m.fehler for m in ohne))
            s += (f" - {len(ohne)} nicht geführt: {namen} ("
                  + "; ".join(gruende[:3]) + (" …" if len(gruende) > 3 else "") + ")")
        return s + warnzeilen(self)

    def table(self) -> list[list]:
        rows = [["Stab", "Querschnitt", "Material", "L [m]", "Klasse", "Ausnutzung",
                 "massgebender Nachweis", "Kombination", "x [m]", "Status"]]
        for m in self.members.values():
            g = m.governing
            rows.append([m.member, m.section, m.material, f"{m.L:.2f}", str(m.cls),
                         f"{m.util:.3f}", g.get("name", ""), g.get("combo", ""),
                         f"{g.get('x', 0):.2f}", m.status()])
        return rows


def warnzeilen(ergebnis) -> str:
    """Die Warnungen eines Nachweisergebnisses als eigene Zeilen "WARNUNG: ..."
    - leer ohne Warnung. getattr: aeltere Ergebnisdateien kennen das Feld
    ``warnungen`` noch nicht."""
    w = getattr(ergebnis, "warnungen", None) or []
    return "".join(f"\nWARNUNG: {x}" for x in w)


# --------------------------------------------------------------------------
def check_member(model: Model, member: Member, results: dict, n: int = None) -> MemberCheck:
    """Nachweise eines Stabes fuer alle uebergebenen Ergebnisse (name -> Results)."""
    ds = model.design
    n = n or ds.stations
    e0 = model.elements[member.elements[0]]
    sec = model.sections[e0.sec]
    mat = model.materials[e0.mat]
    L = model.member_length(member)
    mc = MemberCheck(member.name, sec.name, mat.name, L, elements=list(member.elements))
    fy = mat.yield_strength(sec.t_max)
    if not fy:
        mc.fehler = f"Werkstoff {mat.name} ohne Streckgrenze"
        # Der Hinweis sagt, was zu tun ist: er steht im Bericht in jedem Umfang
        # unter "Offene Hinweise und Warnungen" (report.html chapter_summary)
        # und ist oft die einzige Stelle, an der der Grund steht.
        mc.warnings.append(f"{mc.fehler} – Nachweis nicht geführt; Streckgrenze f_y am "
                           "Werkstoff eintragen oder am Stab „Nachweis nach EC3“ ausschalten")
        return mc
    Lcr_y = member.Lcr_y if member.Lcr_y else member.beta_y * L
    Lcr_z = member.Lcr_z if member.Lcr_z else member.beta_z * L
    L_LT = member.L_LT if member.L_LT else L
    zg = {"top": sec.h / 2, "bottom": -sec.h / 2}.get(member.load_position, 0.0)
    ext = {k: 0.0 for k in ("N_min", "N_max", "Vy_max", "Vz_max", "Mt_max", "My_max", "Mz_max")}
    worst_cls = 1
    for cname, res in results.items():
        mf = res.member_forces(member, n)
        x = mf["x"]
        N, Vy, Vz, Mt, My, Mz = (mf[k] for k in ("N", "Vy", "Vz", "Mt", "My", "Mz"))
        ext["N_min"] = min(ext["N_min"], float(N.min()))
        ext["N_max"] = max(ext["N_max"], float(N.max()))
        for k, arr in (("Vy_max", Vy), ("Vz_max", Vz), ("Mt_max", Mt), ("My_max", My), ("Mz_max", Mz)):
            ext[k] = max(ext[k], float(np.abs(arr).max()))
        # --- Woelbkrafttorsion (6.2.7) ---
        # Sie wird vor den Querschnittsnachweisen gerechnet, denn sie teilt das
        # Torsionsmoment auf: der St.-Venant-Anteil geht in die Schubspannung,
        # der Woelbanteil in sigma_w und tau_w.
        Mt_v, sig_w, tau_w = Mt, None, None
        if (member.woelb_check and sec.Iw > 0
                and float(np.abs(Mt).max()) > 0):
            wt = woelb.woelbnachweis(sec, mat.E, mat.G, L, x, Mt,
                                     (member.woelb_start, member.woelb_ende))
            v = wt["verlauf"]
            Mt_v = v.Mtv
            sig_w, tau_w = wt["sigma_w"], wt["tau_w"]
            mc.woelb.append({
                "combo": cname, "B_max": wt["B_max"], "x_max": wt["x_max"],
                "sigma_w_max": wt["sigma_w_max"], "anteil_woelb": v.anteil_woelb,
                "lamL": v.lamL, "lam": v.lam,
                "rand": (member.woelb_start, member.woelb_ende),
                "sektor": wt["sektor"], "hinweis": wt["grund"] or v.hinweis})
            if wt["grund"] and wt["grund"] not in mc.warnings:
                mc.warnings.append(
                    f"Wölbkrafttorsion: {wt['grund']} – der Momentenanteil wird "
                    "ausgewiesen, die Wölbspannungen nicht.")
            if v.hinweis and v.hinweis not in mc.warnings:
                mc.warnings.append(f"Wölbkrafttorsion: {v.hinweis}")

        # --- Querschnittsnachweise an allen Stellen ---
        best = None
        cls_c = 1
        for j in range(len(x)):
            cls = classify(sec, fy, N[j], My[j], Mz[j])
            cls_c = max(cls_c, cls.cls)
            sc = section_check(sec, fy, N[j], Vy[j], Vz[j], Mt_v[j], My[j], Mz[j],
                               ds.gamma_M0, cls, gamma_M1=ds.gamma_M1,
                               a_steifen=member.a_steifen,
                               starre_endsteife=member.starre_endsteife,
                               l_schale=Lcr_z,
                               sigma_w=float(sig_w[j]) if sig_w is not None else 0.0,
                               tau_w=float(tau_w[j]) if tau_w is not None else 0.0)
            if best is None or sc["util"] > best["util"]:
                best = {"combo": cname, "x": float(x[j]), "util": sc["util"],
                        "name": sc["governing"], "kind": "section", "cls": cls.cls,
                        "text": sc["checks"].get(sc["governing"], (0, ""))[1],
                        "checks": sc["checks"], "N": N[j], "Vy": Vy[j], "Vz": Vz[j],
                        "Mt": Mt[j], "My": My[j], "Mz": Mz[j], "class_text": cls.text(),
                        "warnings": cls.warnings,
                        # wirksame Querschnittswerte der Klasse 4 fuer den Bericht
                        "wirksam": (dict(cls.details.get("wirksam") or {},
                                         A=sec.A, A_eff=cls.A_eff,
                                         Wel_y=sec.Wel_y, Weff_y=cls.Weff_y,
                                         Wel_z=sec.Wel_z, Weff_z=cls.Weff_z,
                                         eN_y=cls.eN_y, eN_z=cls.eN_z,
                                         eps=cls.details.get("eps", 0.0))
                                    if cls.cls == 4 else {})}
        worst_cls = max(worst_cls, cls_c)
        mc.section_checks.append(best)
        for w in best.get("warnings", []):
            if w not in mc.warnings:
                mc.warnings.append(w)
        # --- Stabilitaet ---
        N_Ed = max(-float(N.min()), 0.0)
        My_Ed = float(np.abs(My).max())
        Mz_Ed = float(np.abs(Mz).max())
        if N_Ed > 0 or (My_Ed > 0 and sec.typ == "I" and member.lt_check):
            cls_s = classify(sec, fy, -N_Ed, My_Ed, Mz_Ed)
            st = member_stability(sec, mat.E, mat.G, fy, cls_s, N_Ed, My_Ed, Mz_Ed, My, Mz,
                                  Lcr_y, Lcr_z, L_LT, member.k_z, member.k_w, member.C1, zg,
                                  member.lt_check, ds.lt_method, member.sway_y, member.sway_z,
                                  ds.gamma_M1)
            st["combo"] = cname
            st["cls"] = cls_s.cls
            mc.stability.append(st)
    mc.cls = worst_cls
    # massgebend
    cands = []
    for b in mc.section_checks:
        cands.append({"name": b["name"], "combo": b["combo"], "x": b["x"], "util": b["util"],
                      "text": b["text"], "kind": "Querschnitt"})
    for st in mc.stability:
        if st["checks"]:
            g = st["governing"]
            cands.append({"name": g, "combo": st["combo"], "x": 0.0, "util": st["util"],
                          "text": st["checks"][g][1], "kind": "Stabilitaet"})
    if cands:
        mc.governing = max(cands, key=lambda c: c["util"])
        mc.util = mc.governing["util"]
    mc.extremes = ext
    return mc


def check_member_set(model: Model, names: list, results: dict, n: int = None) -> dict:
    return {nm: check_member(model, model.members[nm], results, n) for nm in names}


def _uls_results(model: Model, analysis, combos=None, warnungen: list = None) -> dict:
    """Die Ergebnisse, gegen die die GZT-Nachweise gefuehrt werden: {Name: Results}.

    Jede GZT-Kombination des Modells mit ihrem Ergebnis; eine
    Ergebniskombination ("A oder B oder ...") mit **jeder Alternative** als
    eigenem Eintrag "EK [k]" (solver.ergebnisse_der_alternativen). Auf die
    Lastfaelle wird nur zurueckgegriffen, wenn das Modell **gar keine**
    Kombination hat. Fehlt das Ergebnis einer Kombination, steht sie in
    ``warnungen`` als "nicht nachgewiesen" - sie wird nicht still ersetzt.
    Dasselbe Ergebnis kann so unter mehreren Namen stehen; check_members
    fasst es danach zusammen (_gleiche_zusammenfassen).

    Bis zum 22.09.2026 fiel die Funktion auf die Lastfaelle zurueck, sobald
    ``analysis.combinations`` leer war, und uebersah Ergebniskombinationen
    ganz: ein Modell nur mit "1,35·LF1 oder 1,35·LF1 + 1,5·LF2" wurde gegen
    LF1 und LF2 mit Faktor 1 nachgewiesen - Ausnutzung 0,170 statt 0,370
    (Befund FE11).
    """
    from ..solver import ergebnisse_der_alternativen
    warn = warnungen if warnungen is not None else []
    kombis = getattr(model, "combinations", None) or {}
    if combos is not None:
        src = analysis.all_results() if hasattr(analysis, "all_results") else analysis
        out = {}
        for k in combos:
            c = kombis.get(k)
            if c is not None and c.ist_umhuellende and hasattr(analysis, "cases"):
                alt, w = ergebnisse_der_alternativen(model, analysis, c)
                out.update(alt)
                warn.extend(w)
            else:
                out[k] = src[k]
        return out
    if not hasattr(analysis, "cases"):
        return dict(analysis)
    if not kombis:
        # gar keine Kombinationen im Modell: dann gelten die Lastfaelle selbst
        return dict(analysis.cases)
    ergebnisse = getattr(analysis, "combinations", None) or {}
    out = {}
    for n, c in kombis.items():
        if not c.is_uls:
            continue
        if c.ist_umhuellende:
            alt, w = ergebnisse_der_alternativen(model, analysis, c)
            out.update(alt)
            warn.extend(w)
        elif n in ergebnisse:
            out[n] = ergebnisse[n]
        else:
            warn.append(f"Kombination {n} nicht nachgewiesen: kein Ergebnis in der "
                        "Berechnung – „Alle Lastfälle + Kombinationen“ rechnen")
    if not out and not warn:
        warn.append("Das Modell hat Kombinationen, aber keine des Grenzzustands der "
                    "Tragfähigkeit – die GZT-Nachweise wurden nicht geführt")
    return out


def _gleich_name(namen: list) -> str:
    """Der Eintrag fuer mehrere Namen desselben Ergebnisses: "EK_A [1] =
    EK_B [1]"; ab fuenf Namen die ersten drei und die Zahl der weiteren (die
    volle Liste steht in DesignResults.gleiche)."""
    if len(namen) <= 4:
        return " = ".join(namen)
    return " = ".join(namen[:3]) + f" = … ({len(namen) - 3} weitere)"


def _gleiche_zusammenfassen(model: Model, analysis, results: dict) -> tuple:
    """Gleiche Ergebnisse nur einmal nachweisen - Rueckgabe
    ({Eintrag: Results}, {Eintrag: [alle Namen]} nur fuer zusammengefasste).

    Kommt ein Lastfall mit Faktor 1 als Alternative in mehreren
    Ergebniskombinationen vor, liefert _uls_results dasselbe Ergebnis unter
    jedem Namen, und der
    Nachweis lief bis zum 23.09.2026 ueber jeden: am Kragarm mit EK_A und
    EK_B, je {LF1} oder {1,35·LF1 + 1,5·LF2}, und K2 fuenf Eintraege statt
    drei (Befund B055). Das Ergebnis stimmte, die Arbeit war doppelt.

    Gleich heisst hier:

    * **dasselbe Objekt** - ein Lastfall mit Faktor 1 als Alternative ist
      das Lastfallergebnis selbst (ergebnisse_der_alternativen);
    * zwei **neu ueberlagerte** Alternativen mit denselben Faktoren - die
      Ueberlagerung derselben linearen Lastfaelle mit denselben Faktoren.
      Ueberlagert wird nur im linearen Modell, und die Lastfaelle einer
      Kombination gehoeren zu ihrer Situation; gleiche Faktoren heissen
      also gleiche Situation.

    Abgelegte Alternativen (``analysis.alternativen``: Theorie II./III.
    Ordnung, Kontaktmodell) und gewoehnliche Kombinationen werden nur ueber
    das Objekt verglichen: ihr Ergebnis haengt auch an der Theorie der
    Kombination bzw. am Startzustand der direkten Loesung, nicht allein an
    den Faktoren.

    Der Eintrag behaelt die Stelle des ersten Namens und heisst "EK_A [1] =
    EK_B [1]"; so steht er in design.combinations, im massgebenden Nachweis
    und in den Tabellen je Kombination.
    """
    from ..solver import alternativen_der_kombination
    abgelegt = getattr(analysis, "alternativen", None) or {}
    lastfaelle = {id(r) for r in (getattr(analysis, "cases", None) or {}).values()}
    faktoren = {}
    for c in (getattr(model, "combinations", None) or {}).values():
        if c.ist_umhuellende:
            for n, teile in alternativen_der_kombination(c):
                faktoren[n] = teile
    gruppen: dict = {}          # Schluessel -> [Namen], in Reihenfolge
    ergebnis: dict = {}         # Schluessel -> Results
    for name, res in results.items():
        # neu ueberlagert: eine Alternative, weder abgelegt noch das
        # Lastfallergebnis selbst
        ueberlagert = (name in faktoren and name not in abgelegt
                       and id(res) not in lastfaelle)
        schluessel = (("summe", tuple(sorted(faktoren[name].items()))) if ueberlagert
                      else ("objekt", id(res)))
        if schluessel in gruppen:
            gruppen[schluessel].append(name)
        else:
            gruppen[schluessel] = [name]
            ergebnis[schluessel] = res
    out, gleiche = {}, {}
    for schluessel, namen in gruppen.items():
        eintrag = _gleich_name(namen)
        out[eintrag] = ergebnis[schluessel]
        if len(namen) > 1:
            gleiche[eintrag] = list(namen)
    return out, gleiche


def _melde(progress, text: str, anteil: float = None) -> None:
    """Fortschritt melden - Text und, wenn bekannt, der Anteil (0…1).

    Wie ``solver._melde``: Empfaenger, die nur Text kennen (Protokoll,
    Browser, aeltere Aufrufer), bekommen weiterhin nur Text.
    """
    if progress is None:
        return
    if anteil is None:
        progress(text)
        return
    try:
        progress(text, float(anteil))
    except TypeError:
        progress(text)


def _anteil(anteil, bruch: float):
    """Den Bruchteil 0…1 in das Fenster ``anteil = (von, bis)`` legen; ohne
    Fenster None - dann bleibt es beim Text."""
    if anteil is None:
        return None
    von, bis = anteil
    return float(von) + (float(bis) - float(von)) * max(0.0, min(1.0, bruch))


def check_members(model: Model, analysis, combos: list = None, members: list = None,
                  progress=None, use_jobs: bool = None, workers: int = None,
                  anteil=None) -> DesignResults:
    """Nachweise aller Staebe (parallel/verteilt bei vielen Staeben).

    ``anteil=(von, bis)`` laesst den Fortschritt ausser dem Text auch den
    Anteil melden, auf dieses Fenster des Balkens abgebildet - die
    Oberflaeche gibt (0, 1), wenn die Nachweise allein laufen. Ohne Angabe
    kommt nur Text: in ``solve_all`` sind die Nachweise das letzte Stueck
    hinter der Rechnung, und ein Anteil von hier wuerfe den Balken zurueck.
    """
    from .. import parallel
    warnungen: list = []
    names = members if members is not None else [k for k, m in model.members.items() if m.design]
    # Ohne einen Stab mit Nachweis wird nichts nachgewiesen - dann darf auch
    # keine Kombination als "nicht nachgewiesen" gemeldet werden. Sonst kam
    # hier mit nur GZG-Kombinationen und allen Staeben auf design = False die
    # Warnung "keine GZT-Kombination", und das Gesamturteil des Berichts
    # kippte von "Alle Nachweise erfüllt." auf "nicht geführt: EC3"
    # (Gegenpruefung 23.09.2026, Kragarm und Halle).
    results = _uls_results(model, analysis, combos, warnungen=warnungen) if names else {}
    # dasselbe Ergebnis unter mehreren Namen nur einmal nachweisen (B055)
    results, gleiche = _gleiche_zusammenfassen(model, analysis, results)
    out = DesignResults(combinations=list(results), settings={
        "gamma_M0": model.design.gamma_M0, "gamma_M1": model.design.gamma_M1,
        "Methode": f"Anhang {model.design.interaction_method}",
        "BDK": model.design.lt_method}, warnungen=warnungen, gleiche=gleiche)
    if not names or not results:
        _melde(progress, "Nachweise EC3: keine Staebe mit Nachweis" if not names else
               "Nachweise EC3: keine Ergebnisse einer GZT-Kombination", _anteil(anteil, 1.0))
        return out
    st = parallel.settings()
    if use_jobs is None:
        use_jobs = st.backend == "farm" or (st.workers > 1 and len(names) >= 24)
    if use_jobs:
        from ..parallel import Job, run_jobs
        stripped = {}
        for k, r in results.items():
            rr = _strip(r)
            stripped[k] = rr
        nchunk = max(1, min(len(names), 4 * max(st.workers, 1)))
        size = int(np.ceil(len(names) / nchunk))
        chunks = [names[i:i + size] for i in range(0, len(names), size)]
        # Modell und Ergebnisse **einmal** in eine Datei, die Auftraege tragen
        # nur den Pfad. Vorher stand in jedem Auftrag ein eigenes
        # model.to_dict() - am Drehlager 239 MB je Auftrag, bei 64 Auftraegen
        # rund 15 GB durch die Prozess-Pipes. Der Lauf des Anwenders stand
        # nach 698 Minuten bei 94 % und kam nicht weiter; ein Arbeiter starb
        # vorher mit AssertionError in multiprocessing/connection.py
        # (_get_more_data, die Pipe brach) - 21.09.2026.
        paket = _paket_schreiben(model, stripped)
        try:
            jobs = [Job("design_members", {"paket": paket, "members": c})
                    for c in chunks]
            _melde(progress, f"Nachweise: {len(names)} Staebe in {len(jobs)} Auftraegen",
                   _anteil(anteil, 0.0))
            for r in run_jobs(jobs, workers=workers,
                              progress=(lambda a, b: _melde(progress, f"Nachweise {a}/{b}",
                                                            _anteil(anteil, a / max(1, b))))
                              if progress else None):
                if not r.ok:
                    raise RuntimeError(f"Nachweis fehlgeschlagen: {r.error}")
                out.members.update(r.result)
        finally:
            try:
                os.unlink(paket)
            except OSError:
                pass
        return out
    for k, nm in enumerate(names):
        out.members[nm] = check_member(model, model.members[nm], results)
        if progress and (k % 10 == 0 or k == len(names) - 1):
            _melde(progress, f"Nachweis {nm} ({k+1}/{len(names)})",
                   _anteil(anteil, (k + 1) / len(names)))
    return out


def _paket_schreiben(model, results: dict) -> str:
    """Modell und Ergebnisse einmal in eine Datei; der Pfad geht an die
    Auftraege.

    Dieselbe Loesung wie im stehenden Pool (parallel._init_worker_datei): der
    Arbeitsprozess liest das Modell **einmal**, statt es je Auftrag durch die
    Pipe zu bekommen und neu aufzubauen. Beim Drehlager sind das 239 MB je
    Auftrag; die Datei wird am Ende wieder geloescht.
    """
    import pickle
    import tempfile
    fd, pfad = tempfile.mkstemp(prefix="statik3d_nachweis_", suffix=".pkl")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump({"model": model.to_dict(), "results": results}, f,
                        protocol=pickle.HIGHEST_PROTOCOL)
    except BaseException:
        try:
            os.unlink(pfad)
        except OSError:
            pass
        raise
    return pfad


def _strip(r):
    """Results-Kopie ohne Modell/Cache fuer den Versand."""
    from ..solver import Results
    rr = Results(name=r.name, kind=r.kind, u=r.u, reactions=r.reactions,
                 beam_end=r.beam_end, beam_q=r.beam_q, info=dict(r.info))
    return rr
