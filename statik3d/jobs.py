"""Registrierte Auftragsarten fuer Prozess-Pool und Rechnerfarm."""
from __future__ import annotations

from .parallel import register_job


@register_job("solve_combination")
def _job_solve_combination(model: dict, combination: str):
    from .model import Model
    from . import solver
    m = Model.from_dict(model)
    res = solver.solve_combination(m, m.combinations[combination])
    res.model = None          # Modell nicht zuruecksenden
    return res


@register_job("solve_case")
def _job_solve_case(model: dict, case: str):
    from .model import Model
    from . import solver
    m = Model.from_dict(model)
    res = solver.solve_static(m, case=case)
    res.model = None
    return res


@register_job("solve_all")
def _job_solve_all(model: dict, design: bool = False, fatigue: bool = False):
    from .model import Model
    from . import solver
    m = Model.from_dict(model)
    an = solver.solve_all(m, design=design, fatigue=fatigue)
    return an.summary()


@register_job("design_members")
def _job_design_members(model: dict, members: list, results: dict):
    """Nachweise fuer eine Gruppe von Staeben (results: name -> Results ohne Modell)."""
    from .model import Model
    from .ec3.design import check_member_set
    m = Model.from_dict(model)
    for r in results.values():
        r.model = m
    return check_member_set(m, members, results)


@register_job("ping")
def _job_ping(**kw):
    import platform
    return {"host": platform.node(), **kw}
