"""
Nachweisfuehrung fuer Staebe (Member) nach DIN EN 1993-1-1:
Querschnittsnachweise an allen Nachweisstellen und Stabilitaetsnachweise je
Stab fuer alle Kombinationen im Grenzzustand der Tragfaehigkeit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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

    def status(self) -> str:
        return "erfüllt" if self.util <= 1.0 else "NICHT erfüllt"


@dataclass
class DesignResults:
    members: dict = field(default_factory=dict)
    combinations: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def util_max(self) -> float:
        return max((m.util for m in self.members.values()), default=0.0)

    def util_by_element(self) -> dict:
        out = {}
        for m in self.members.values():
            for e in m.elements:
                out[e] = max(out.get(e, 0.0), m.util)
        return out

    def summary(self) -> str:
        if not self.members:
            return "Nachweise EC3: keine Staebe"
        worst = max(self.members.values(), key=lambda m: m.util)
        nf = sum(1 for m in self.members.values() if m.util > 1.0)
        g = worst.governing
        return (f"Nachweise EC3: {len(self.members)} Staebe, {len(self.combinations)} Kombinationen, "
                f"max. Ausnutzung {worst.util:.3f} ({worst.member}: {g.get('name', '')}, "
                f"{g.get('combo', '')}, x = {g.get('x', 0):.2f} m)"
                + (f" - {nf} Staebe NICHT erfuellt" if nf else " - alle erfuellt"))

    def table(self) -> list[list]:
        rows = [["Stab", "Querschnitt", "Material", "L [m]", "Klasse", "Ausnutzung",
                 "massgebender Nachweis", "Kombination", "x [m]", "Status"]]
        for m in self.members.values():
            g = m.governing
            rows.append([m.member, m.section, m.material, f"{m.L:.2f}", str(m.cls),
                         f"{m.util:.3f}", g.get("name", ""), g.get("combo", ""),
                         f"{g.get('x', 0):.2f}", m.status()])
        return rows


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
        mc.warnings.append(f"Material {mat.name} ohne Streckgrenze - kein Nachweis")
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


def _uls_results(model: Model, analysis, combos=None) -> dict:
    if combos is not None:
        src = analysis.all_results() if hasattr(analysis, "all_results") else analysis
        return {k: src[k] for k in combos}
    if hasattr(analysis, "combinations") and analysis.combinations:
        return {k: r for k, r in analysis.combinations.items()
                if model.combinations[k].is_uls}
    if hasattr(analysis, "cases"):
        return dict(analysis.cases)
    return dict(analysis)


def check_members(model: Model, analysis, combos: list = None, members: list = None,
                  progress=None, use_jobs: bool = None, workers: int = None) -> DesignResults:
    """Nachweise aller Staebe (parallel/verteilt bei vielen Staeben)."""
    from .. import parallel
    results = _uls_results(model, analysis, combos)
    names = members if members is not None else [k for k, m in model.members.items() if m.design]
    out = DesignResults(combinations=list(results), settings={
        "gamma_M0": model.design.gamma_M0, "gamma_M1": model.design.gamma_M1,
        "Methode": f"Anhang {model.design.interaction_method}",
        "BDK": model.design.lt_method})
    if not names or not results:
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
        jobs = [Job("design_members", {"model": model.to_dict(), "members": c,
                                       "results": stripped}) for c in chunks]
        for r in run_jobs(jobs, workers=workers,
                          progress=(lambda a, b: progress(f"Nachweise {a}/{b}")) if progress else None):
            if not r.ok:
                raise RuntimeError(f"Nachweis fehlgeschlagen: {r.error}")
            out.members.update(r.result)
        return out
    for k, nm in enumerate(names):
        out.members[nm] = check_member(model, model.members[nm], results)
        if progress and (k % 10 == 0 or k == len(names) - 1):
            progress(f"Nachweis {nm} ({k+1}/{len(names)})")
    return out


def _strip(r):
    """Results-Kopie ohne Modell/Cache fuer den Versand."""
    from ..solver import Results
    rr = Results(name=r.name, kind=r.kind, u=r.u, reactions=r.reactions,
                 beam_end=r.beam_end, beam_q=r.beam_q, info=dict(r.info))
    return rr
