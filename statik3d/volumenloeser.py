"""Registrierung der Volumenloeser ueber Python Entry Points (Vertrag Abschnitt 7, 7a, 10.5).

Das Hauptprogramm kennt keine internen Module von ``volumen3d``: Loeser werden
ueber ``importlib.metadata.entry_points`` der Gruppen
``statik3d.solid_solvers`` (``SolidDetailSolver``) und
``statik3d.assembly_solvers`` (``AssemblySolver``) gefunden. Das Vertragspaket
traegt seine Stubs unter dem Namen ``stub`` ein; ``volumen3d`` traegt ``fcm``
und ``hybrid`` ein. Beide Pakete pruefen beim Start die Vertragsversion
(Major muss uebereinstimmen, Abschnitt 9).

Faellt die Registrierung aus (z. B. in der exe ohne Paket-Metadaten), stehen
die Stubs des Vertragspakets als Rueckfall bereit - sie sind Teil des
Vertrags, kein interner Import von ``volumen3d``.
"""
from __future__ import annotations

from importlib import metadata
from typing import Any

import statik3d_contracts as V
from statik3d_contracts.solver import (ENTRY_POINT_ASSEMBLY, ENTRY_POINT_SOLID, AssemblySolver,
                                       SolidDetailSolver)


class Vertragsfehler(RuntimeError):
    """Ein Loeser passt nicht zum Vertrag (Version oder Protokoll)."""


def entry_points_der_gruppe(gruppe: str) -> dict[str, Any]:
    """{Name: geladenes Objekt} aller Entry Points einer Gruppe; Ladefehler
    stehen als Ausnahme statt des Objekts, damit ein kaputtes Paket die
    anderen nicht mitreisst."""
    aus: dict[str, Any] = {}
    try:
        eps = metadata.entry_points(group=gruppe)
    except Exception:                        # noqa: BLE001 - keine Metadaten (exe)
        return aus
    for ep in eps:
        try:
            aus[ep.name] = ep.load()
        except Exception as ex:              # noqa: BLE001
            aus[ep.name] = ex
    return aus


def _rueckfall_stubs() -> dict[str, dict[str, Any]]:
    from statik3d_contracts import testing as T
    return {ENTRY_POINT_SOLID: {"stub": T.StubSolidSolver},
            ENTRY_POINT_ASSEMBLY: {"stub": T.StubAssemblySolver}}


def loeser_der_gruppe(gruppe: str) -> dict[str, Any]:
    """Die registrierten Loeserklassen einer Gruppe, ohne Ladefehler; ohne
    Registrierung die Stubs des Vertragspakets."""
    gefunden = {n: k for n, k in entry_points_der_gruppe(gruppe).items() if not isinstance(k, Exception)}
    if not gefunden:
        gefunden = dict(_rueckfall_stubs().get(gruppe, {}))
    return gefunden


def vertrag_pruefen(klasse: Any, protokoll: Any) -> Any:
    """Erzeugt den Loeser und prueft Vertragsversion (Major) und Protokoll."""
    version = str(getattr(klasse, "contract_version", "") or "")
    if not V.vertragsversion_passt(version):
        raise Vertragsfehler(f"{getattr(klasse, 'name', klasse)!s}: Vertragsversion {version or '?'} "
                             f"passt nicht zu {V.CONTRACT_VERSION} (Major muss uebereinstimmen)")
    loeser = klasse() if isinstance(klasse, type) else klasse
    if not isinstance(loeser, protokoll):
        raise Vertragsfehler(f"{getattr(klasse, 'name', klasse)!s} erfuellt {protokoll.__name__} nicht")
    return loeser


def volumenloeser(name: str | None = None) -> Any:
    """Ein ``SolidDetailSolver``: der genannte, sonst der erste registrierte
    echte Loeser (nicht 'stub'), sonst der Stub."""
    return _waehlen(loeser_der_gruppe(ENTRY_POINT_SOLID), name, SolidDetailSolver)


def baugruppenloeser(name: str | None = None) -> Any:
    """Ein ``AssemblySolver`` nach derselben Regel."""
    return _waehlen(loeser_der_gruppe(ENTRY_POINT_ASSEMBLY), name, AssemblySolver)


def _waehlen(kandidaten: dict[str, Any], name: str | None, protokoll: Any) -> Any:
    if not kandidaten:
        raise Vertragsfehler(f"kein Loeser fuer {protokoll.__name__} registriert")
    if name is None:
        echte = [n for n in kandidaten if n != "stub"]
        name = sorted(echte)[0] if echte else "stub"
    if name not in kandidaten:
        raise Vertragsfehler(f"Loeser {name!r} ist nicht registriert; vorhanden: {sorted(kandidaten)}")
    return vertrag_pruefen(kandidaten[name], protokoll)


def uebersicht() -> list[dict[str, str]]:
    """Fuer Protokoll und Oberflaeche: Name, Gruppe, Vertragsversion, Zustand je Loeser."""
    aus: list[dict[str, str]] = []
    for gruppe, protokoll in ((ENTRY_POINT_SOLID, SolidDetailSolver), (ENTRY_POINT_ASSEMBLY, AssemblySolver)):
        for n, k in sorted(entry_points_der_gruppe(gruppe).items()):
            if isinstance(k, Exception):
                aus.append({"name": n, "gruppe": gruppe, "version": "?", "zustand": f"Ladefehler: {k}"})
                continue
            try:
                vertrag_pruefen(k, protokoll)
                zustand = "bereit"
            except Vertragsfehler as ex:
                zustand = str(ex)
            aus.append({"name": n, "gruppe": gruppe, "version": str(getattr(k, "contract_version", "?")),
                        "zustand": zustand})
    return aus


__all__ = ["Vertragsfehler", "entry_points_der_gruppe", "loeser_der_gruppe", "vertrag_pruefen",
           "volumenloeser", "baugruppenloeser", "uebersicht"]
