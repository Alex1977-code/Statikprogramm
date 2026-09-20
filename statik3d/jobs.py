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


@register_job("solve_kette")
def _job_solve_kette(pfad: str = "", model: dict = None, cases: list = None,
                     arbeiter: int = 0, loeser_threads: int = 0):
    """Eine **Kette** von Lastfaellen: nacheinander, in sich warm gestartet.

    Der Warmstart ist der groesste Einzelgewinn je Lastfall (Drehlager:
    kalt 112 Kontaktrunden, warm 41 bis 48). Wer alle Lastfaelle als einzelne
    Auftraege verteilt, macht jeden kalt und verliert mehr, als die
    Parallelitaet bringt. Darum kommt eine ganze Folge in einen Auftrag: der
    erste Lastfall der Kette ist kalt, alle weiteren warm.

    ``pfad`` ist das gepickelte Modell in einer Datei - so wie der stehende
    Pool es macht. Es je Auftrag mitzupickeln kostete am Drehlager mehr als
    die Rechnung (parallel.Arbeiter, 13.09.2026). Ueber die Farm gibt es
    keine gemeinsame Datei; dort kommt ``model`` als Woerterbuch.
    """
    import pickle
    from .model import Model
    from . import parallel, solver
    if pfad:
        with open(pfad, "rb") as f:
            m = pickle.load(f)
    else:
        m = Model.from_dict(model)
    if arbeiter:
        parallel.configure(workers=max(1, int(arbeiter)))
    if loeser_threads:
        parallel.configure(solver_threads=max(1, int(loeser_threads)))
    parallel.configure(ketten=1)          # in der Kette wird nicht weiter geteilt
    out = solver.solve_cases(m, cases=list(cases or []))
    for r in out.values():
        r.model = None                    # Modell nicht zuruecksenden
    return out


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
