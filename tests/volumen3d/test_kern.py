"""Kernsuite des Volumenmoduls volumen3d fuer tests.run_all und die CI (nur CPU, unter 5 min):
Paket, Basis, Geometrie, Gitter, Quadratur, Elastizitaet, Patch-Test, Vertragsschicht.
Die Abnahmen mit laengerer Laufzeit (Kragarm, Lame, Kirsch) laufen als eigene Suiten
(tests.volumen3d.test_kragarm, test_lame, test_kirsch) vor jedem Merge.

Aufruf: python -m tests.volumen3d.test_kern
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.volumen3d import (test_basis, test_elastizitaet, test_geometrie, test_gitter, test_paket,  # noqa: E402
                             test_patch, test_quadratur, test_vertrag_fcm)
from tests.volumen3d._pruef import lauf  # noqa: E402

TESTS = [
    test_paket.test_import, test_paket.test_entry_points, test_paket.test_importregeln,
    test_basis.test_1d, test_basis.test_3d, test_basis.test_gauss,
    test_geometrie.test_grundformen, test_geometrie.test_csg, test_geometrie.test_lokale_stuecke, test_geometrie.test_oberflaechenquadratur,
    test_gitter.test_klassifikation, test_gitter.test_moden_vollgitter, test_gitter.test_punktsuche,
    test_quadratur.test_polyeder, test_quadratur.test_ebene_geometrie_exakt, test_quadratur.test_inside_zelle,
    test_elastizitaet.test_zellsteifigkeit, test_elastizitaet.test_starrkoerper,
    test_patch.test_patch, test_patch.test_kleine_schnittzellen, test_patch.test_normalprojektion,
    test_vertrag_fcm.test_protokoll_und_registrierung, test_vertrag_fcm.test_ablauf, test_vertrag_fcm.test_hybrid_platzhalter,
]

if __name__ == "__main__":
    sys.exit(lauf(TESTS))
