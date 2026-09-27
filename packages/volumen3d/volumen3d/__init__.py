"""Volumenmodul volumen3d von Statik3D.

Finite-Cell-Methode (FCM), spaeter FE-Hexaeder, Kontakt und Plastizitaet. Verbindlich:
``docs/Schnittstellenvertrag_Statik3D_FCM.md`` und
``docs/Vorgabe_Statik3D_Abschnitt_FCM-Volumenloeser.md``; Umsetzung nach
``docs/Volumenmodul_Entwurf.md``. Einheiten mm, N, N/mm2.

Dieses Paket importiert ``statik3d_contracts`` und niemals ``statik3d`` (Vertrag Abschnitt 1;
``.importlinter`` prueft das).
"""
from __future__ import annotations

import statik3d_contracts as _V

__version__ = "0.1.0"

#: Vertragsversion, gegen die dieses Paket gebaut ist; die Major-Nummer muss zum
#: installierten Vertragspaket passen (Vertrag Abschnitt 9).
CONTRACT_VERSION = "2.0.1"

if not _V.vertragsversion_passt(CONTRACT_VERSION):
    raise ImportError(f"volumen3d ist fuer Vertrag {CONTRACT_VERSION} gebaut, installiert ist "
                      f"{_V.CONTRACT_VERSION} (Major muss uebereinstimmen)")

__all__ = ["__version__", "CONTRACT_VERSION"]
