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
                     arbeiter: int = 0, loeser_threads: int = 0,
                     referenzen: dict = None, einstellungen: dict = None):
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
    # Die Einstellungen des Hauptprozesses zuerst - unter spawn beginnt dieser
    # Prozess mit den Vorgaben (solver_backend "auto" statt des gespeicherten
    # "pardiso"). Unbekannte Schluessel eines neueren Hauptprozesses werden
    # uebergangen, nicht mit KeyError quittiert.
    st = parallel.settings()
    parallel.configure(**{k: v for k, v in (einstellungen or {}).items()
                          if hasattr(st, k)})
    if arbeiter:
        parallel.configure(workers=max(1, int(arbeiter)))
    if loeser_threads:
        parallel.configure(solver_threads=max(1, int(loeser_threads)))
    parallel.configure(ketten=1)          # in der Kette wird nicht weiter geteilt
    # Die Referenzen muessen mit: ohne sie rechnete jeder eingefrorene Zustand
    # der Kette voll nichtlinear, und zwar still. Bis zum 22.09.2026 gab
    # dieser Auftrag sie nicht weiter - das war der zweite Teil der Sperre,
    # der erste sass in _solve_cases_innen.
    out = solver.solve_cases(m, cases=list(cases or []),
                             referenzen=dict(referenzen or {}))
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


#: Zuletzt gelesenes Nachweispaket je Arbeitsprozess: (Pfad, Modell, Ergebnisse).
#: Ohne diesen Halt baut jeder Auftrag das Modell neu auf - am Drehlager
#: 239 MB, und bei 64 Auftraegen viermal je Arbeiter (21.09.2026).
_NACHWEIS_PAKET = (None, None, None)


@register_job("design_members")
def _job_design_members(members: list, paket: str = None, model: dict = None,
                        results: dict = None):
    """Nachweise fuer eine Gruppe von Staeben.

    ``paket`` ist der Pfad der Datei mit Modell und Ergebnissen
    (ec3.design._paket_schreiben); sie wird je Arbeitsprozess **einmal**
    gelesen. ``model``/``results`` sind der alte Weg - die Farm und aeltere
    Auftraege schicken sie noch im Auftrag mit.
    """
    global _NACHWEIS_PAKET
    from .model import Model
    from .ec3.design import check_member_set
    if paket is not None:
        if _NACHWEIS_PAKET[0] != paket:
            import pickle
            with open(paket, "rb") as f:
                d = pickle.load(f)
            _NACHWEIS_PAKET = (paket, Model.from_dict(d["model"]), d["results"])
        _pfad, m, results = _NACHWEIS_PAKET
    else:
        m = Model.from_dict(model)
    for r in results.values():
        r.model = m
    return check_member_set(m, members, results)


@register_job("ping")
def _job_ping(**kw):
    import platform
    return {"host": platform.node(), **kw}
