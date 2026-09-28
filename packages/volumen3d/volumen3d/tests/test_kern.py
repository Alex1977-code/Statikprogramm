"""Kernsuite des Volumenmoduls volumen3d fuer tests.run_all und die CI (nur CPU, unter 5 min):
Paket, Basis, Geometrie, Gitter, Quadratur, Elastizitaet, Patch-Test, Vertragsschicht.
Die Abnahmen mit laengerer Laufzeit (Kragarm, Lame, Kirsch) laufen als eigene Suiten
(volumen3d.tests.test_kragarm, test_lame, test_kirsch) vor jedem Merge.

Aufruf: python -m volumen3d.tests.test_kern
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from volumen3d.tests import (test_basis, test_elastizitaet, test_geometrie, test_gitter, test_oktree, test_paket,  # noqa: E402
                             test_mehrgitter, test_operator, test_patch, test_quadratur, test_stl, test_vertrag_fcm, test_zwaenge)
from volumen3d.tests._pruef import lauf  # noqa: E402

TESTS = [
    test_paket.test_import, test_paket.test_entry_points, test_paket.test_importregeln,
    test_basis.test_1d, test_basis.test_3d, test_basis.test_gauss,
    test_geometrie.test_grundformen, test_geometrie.test_csg, test_geometrie.test_lokale_stuecke, test_geometrie.test_oberflaechenquadratur,
    test_gitter.test_klassifikation, test_gitter.test_moden_vollgitter, test_gitter.test_punktsuche,
    test_oktree.test_schnittzellen, test_oktree.test_bereich_und_duenn, test_oktree.test_punktsuche_und_box, test_oktree.test_moden_ueber_ebenen, test_oktree.test_rand_auf_zellflaechen,
    test_zwaenge.test_zaehlung_und_spur, test_zwaenge.test_leere_zellen, test_stl.test_kern_stl, test_operator.test_kern, test_mehrgitter.test_kern, test_mehrgitter.test_nullkandidaten,
    test_quadratur.test_polyeder, test_quadratur.test_ebene_geometrie_exakt, test_quadratur.test_kleine_radien, test_quadratur.test_inside_zelle,
    test_elastizitaet.test_zellsteifigkeit, test_elastizitaet.test_starrkoerper,
    test_patch.test_patch, test_patch.test_kleine_schnittzellen, test_patch.test_normalprojektion,
    test_vertrag_fcm.test_protokoll_und_registrierung, test_vertrag_fcm.test_ablauf, test_vertrag_fcm.test_gutachten_faelle,
    test_vertrag_fcm.test_hybrid_platzhalter, test_vertrag_fcm.test_lasten, test_vertrag_fcm.test_zylinderauswahl, test_vertrag_fcm.test_loeserwahl,
]

if __name__ == "__main__":
    sys.exit(lauf(TESTS))
