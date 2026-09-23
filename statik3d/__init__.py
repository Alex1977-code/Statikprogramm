"""Statik3D - FEM-Programm fuer Stab-, Flaechen- und Volumentragwerke."""
import os as _os

# MKL_CBWR=AUTO als Vorgabe (Entscheidung des Anwenders, 23.09.2026): MKL
# rechnet damit auf derselben Maschine bitgleich wiederholbar. Gemessen am
# Drehlager LF1 (22.09.2026): mit AUTO zwei Laeufe bitgleich, ohne hoechstens
# 0,0004 N/mm2 auseinander; Preis rund +11 % Rechenzeit. MKL liest die Variable
# nur beim ersten Laden - darum hier, beim ersten Import des Pakets, und fuer
# die Kettenprozesse (spawn), die das Paket ebenso zuerst importieren. Ein vom
# Anwender gesetzter Wert hat Vorrang (setdefault).
_os.environ.setdefault("MKL_CBWR", "AUTO")

from .model import Model, Material, Section, ShellProp, Element  # noqa: F401,E402
from .solver import solve_static, solve_modal, solve_buckling, Results  # noqa: F401,E402

__version__ = "2.1.0"
