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

from volumen3d.tests import (test_adaptiv, test_basis, test_elastizitaet, test_geometrie, test_gitter, test_hotspot, test_huelle,  # noqa: E402
                             test_knotenblech, test_oktree, test_paket, test_schale, test_step,
                             test_mehrgitter, test_operator, test_patch, test_quadratur, test_rueckgewinnung, test_stl, test_vertrag_fcm,
                             test_zwaenge)
from volumen3d.tests._pruef import lauf  # noqa: E402

TESTS = [
    test_paket.test_import, test_paket.test_entry_points, test_paket.test_importregeln,
    test_basis.test_1d, test_basis.test_3d, test_basis.test_gauss,
    test_geometrie.test_grundformen, test_geometrie.test_csg, test_geometrie.test_lokale_stuecke, test_geometrie.test_oberflaechenquadratur,
    test_gitter.test_klassifikation, test_gitter.test_moden_vollgitter, test_gitter.test_punktsuche,
    test_oktree.test_schnittzellen, test_oktree.test_bereich_und_duenn, test_oktree.test_punktsuche_und_box, test_oktree.test_moden_ueber_ebenen, test_oktree.test_rand_auf_zellflaechen,
    test_zwaenge.test_zaehlung_und_spur, test_zwaenge.test_leere_zellen, test_stl.test_kern_stl, test_operator.test_kern, test_mehrgitter.test_kern, test_mehrgitter.test_nullkandidaten,
    test_quadratur.test_polyeder, test_quadratur.test_ebene_geometrie_exakt, test_quadratur.test_kleine_radien, test_quadratur.test_inside_zelle,
    test_quadratur.test_momentfitting, test_zwaenge.test_wurzelwahl_rundungsfest,
    test_rueckgewinnung.test_patch_exakt, test_rueckgewinnung.test_reine_biegung, test_rueckgewinnung.test_mehrere_lastfaelle,
    test_quadratur.test_verschachtelter_baum, test_quadratur.test_innere_trennflaeche, test_hotspot.test_geometrie_und_lineares_feld, test_hotspot.test_uneindeutig,
    test_hotspot.test_exaktes_feld,
    test_adaptiv.test_konvergenzaussage, test_adaptiv.test_fahrplan, test_adaptiv.test_zyklen_ohne_naht,
    test_adaptiv.test_zyklen_mit_naht, test_adaptiv.test_zyklen_grenzen,
    test_step.test_tessellierung, test_step.test_vertragsweg_gegen_csg, test_step.test_block_mit_bohrung_gegen_csg, test_step.test_integrationswarnung,
    test_step.test_fehler,
    test_huelle.test_stammfunktionen, test_huelle.test_polyeder_momente, test_huelle.test_baum_und_zellquadratur, test_huelle.test_windungsbaum,
    test_huelle.test_flaeche_hinter_schnittebene,
    test_schale.test_kopplungsabweichung, test_schale.test_schale_achsparallel, test_schale.test_schale_geneigt, test_schale.test_schale_geneigt_p3,
    test_knotenblech.test_knotenblech_h10, test_knotenblech.test_knotenblech_konvergenz,
    test_elastizitaet.test_zellsteifigkeit, test_elastizitaet.test_starrkoerper,
    test_patch.test_patch, test_patch.test_kleine_schnittzellen, test_patch.test_normalprojektion,
    test_vertrag_fcm.test_protokoll_und_registrierung, test_vertrag_fcm.test_ablauf, test_vertrag_fcm.test_gutachten_faelle,
    test_vertrag_fcm.test_hybrid_platzhalter, test_vertrag_fcm.test_lasten, test_vertrag_fcm.test_zylinderauswahl, test_vertrag_fcm.test_loeserwahl,
]

if __name__ == "__main__":
    sys.exit(lauf(TESTS))
