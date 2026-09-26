"""Einheiten und Konventionen (Vertrag Abschnitt 2).

Laenge mm, Kraft N, Spannung und E-Modul N/mm2 (= MPa), Moment N*mm, Dichte
kg/mm3 (intern), Winkel rad, Temperatur Grad C. Globales Koordinatensystem
rechtshaendig, Z nach oben; Zugspannung positiv; Spannungstensor in
Voigt-Notation in der Reihenfolge ``VOIGT_ORDER``; Punktlisten als
``ndarray`` der Form (n, 3), ``float64``; IDs nichtleere, je Typ eindeutige,
unveraenderliche Strings.

Achtung: Statik3D selbst rechnet intern in SI (m, N, Pa). An der Grenze zum
Volumenmodul gelten die Einheiten dieses Vertrags; die Umrechnung liegt beim
Hauptprogramm.
"""
from __future__ import annotations

from typing import Final

LENGTH: Final = "mm"
FORCE: Final = "N"
STRESS: Final = "N/mm2"
VOIGT_ORDER: Final = ("xx", "yy", "zz", "xy", "yz", "xz")

__all__ = ["LENGTH", "FORCE", "STRESS", "VOIGT_ORDER"]
