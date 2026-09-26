"""Schnittstellenvertrag Statik3D <-> Volumenmodul ``volumen3d``.

Nur dieser Vertrag als Code: Typen (``dataclasses``), Protokolle
(``typing.Protocol``) und Stubs - keine Logik. Verbindlich ist
``docs/Schnittstellenvertrag_Statik3D_FCM.md`` (Vertragsversion 2.0.0);
Aenderungen nur per eigenem Pull Request mit Versionserhoehung (Abschnitt 9).

Abhaengigkeitsregel (Abschnitt 1): dieses Paket importiert nur die
Standardbibliothek und ``numpy``. ``tests/contracts`` prueft das.
"""
from __future__ import annotations

from typing import Final

#: Semantische Version des Vertrags (Abschnitt 9): Patch = Doku, Minor = neue
#: optionale Felder/Methoden, Major = Umbenennen, Entfernen, geaenderte Bedeutung.
CONTRACT_VERSION: Final = "2.0.0"


def major(version: str) -> int:
    """Die Major-Nummer einer semantischen Version, 0 bei unlesbarem Text."""
    try:
        return int(str(version).split(".")[0])
    except (ValueError, IndexError):
        return 0


def vertragsversion_passt(andere: str) -> bool:
    """Beide Pakete pruefen beim Start die Vertragsversion: die Major-Nummer
    muss uebereinstimmen (Abschnitt 9)."""
    return major(andere) == major(CONTRACT_VERSION)


__all__ = ["CONTRACT_VERSION", "major", "vertragsversion_passt"]
