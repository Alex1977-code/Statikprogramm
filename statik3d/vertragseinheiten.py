"""Einheiten an der Grenze zum Volumenmodul - die **einzige** Stelle der
Umrechnung (Vertrag 2.0.1, Abschnitt 2).

Statik3D rechnet innen in SI (m, N, Pa, kg/m3); der Vertrag mit ``volumen3d``
verlangt mm, N, N/mm2 (statik3d_contracts.units). Jede Uebergabe an das
Volumenmodul - Geometrie in ``diskretisierung``, Verschiebungen und
Schnittgroessen des ``GlobalFieldProvider`` - geht durch diese Funktionen und
sonst nirgends. Der Rundreisetest (tests/contracts/test_vertrag) belegt, dass
Hin- und Rueckumrechnung sich aufheben.
"""
from __future__ import annotations

import numpy as np

from statik3d_contracts.units import FORCE, LENGTH, STRESS

#: Laenge: 1 m = 1000 mm
MM_JE_M = 1000.0
#: Spannung: 1 N/mm2 = 1e6 Pa
PA_JE_NMM2 = 1.0e6
#: Dichte: 1 kg/m3 = 1e-9 kg/mm3
KG_MM3_JE_KG_M3 = 1.0e-9

assert LENGTH == "mm" and FORCE == "N" and STRESS == "N/mm2"   # Vertragseinheiten, gegen die hier umgerechnet wird


def laenge_nach_vertrag(x_m) -> np.ndarray:
    """m -> mm (Koordinaten, Verschiebungen, Spalte)."""
    return np.asarray(x_m, float) * MM_JE_M


def laenge_nach_si(x_mm) -> np.ndarray:
    """mm -> m."""
    return np.asarray(x_mm, float) / MM_JE_M


def kraft_nach_vertrag(f_n) -> np.ndarray:
    """N -> N (gleich, der Vollstaendigkeit halber an derselben Stelle)."""
    return np.asarray(f_n, float)


def kraft_nach_si(f_n) -> np.ndarray:
    return np.asarray(f_n, float)


def moment_nach_vertrag(m_nm) -> np.ndarray:
    """N*m -> N*mm."""
    return np.asarray(m_nm, float) * MM_JE_M


def moment_nach_si(m_nmm) -> np.ndarray:
    return np.asarray(m_nmm, float) / MM_JE_M


def spannung_nach_vertrag(s_pa) -> np.ndarray:
    """Pa -> N/mm2 (auch E-Modul)."""
    return np.asarray(s_pa, float) / PA_JE_NMM2


def spannung_nach_si(s_nmm2) -> np.ndarray:
    return np.asarray(s_nmm2, float) * PA_JE_NMM2


def dichte_nach_vertrag(rho_kg_m3) -> np.ndarray:
    """kg/m3 -> kg/mm3."""
    return np.asarray(rho_kg_m3, float) * KG_MM3_JE_KG_M3


def dichte_nach_si(rho_kg_mm3) -> np.ndarray:
    return np.asarray(rho_kg_mm3, float) / KG_MM3_JE_KG_M3


__all__ = ["MM_JE_M", "PA_JE_NMM2", "KG_MM3_JE_KG_M3",
           "laenge_nach_vertrag", "laenge_nach_si", "kraft_nach_vertrag", "kraft_nach_si",
           "moment_nach_vertrag", "moment_nach_si", "spannung_nach_vertrag", "spannung_nach_si",
           "dichte_nach_vertrag", "dichte_nach_si"]
