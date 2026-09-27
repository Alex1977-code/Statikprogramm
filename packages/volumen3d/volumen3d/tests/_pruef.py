"""Pruefhelfer der volumen3d-Suiten im Stil von tests/contracts/test_vertrag.py.

Jede Suite ruft ``lauf([...])`` mit ihren Pruefungen; ``check`` protokolliert eine Zeile
je Pruefung mit Messwert, damit ein Fehlschlag die Zahl gleich mitliefert.
"""
from __future__ import annotations

import sys
import traceback

RESULTS: list[tuple[str, bool]] = []


def check(name: str, ok, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok)))
    print(f"{'OK  ' if ok else 'FEHLER'} {name:74s} {detail}")
    sys.stdout.flush()
    return bool(ok)


def lauf(tests) -> int:
    for t in tests:
        print(f"\n--- {t.__name__} ---")
        try:
            t()
        except Exception as ex:              # noqa: BLE001 - jede Ausnahme ist ein Fehlschlag
            traceback.print_exc()
            check(f"{t.__name__} laeuft ohne Ausnahme", False, str(ex)[:120])
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1
