"""Statik3D - FEM-Programm fuer Stab-, Flaechen- und Volumentragwerke."""
from .model import Model, Material, Section, ShellProp, Element  # noqa: F401
from .solver import solve_static, solve_modal, solve_buckling, Results  # noqa: F401

__version__ = "2.0.0"
