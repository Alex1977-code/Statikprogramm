"""Konvergenzaussage aus der Folge der Hot-Spot-Werte der adaptiven Zyklen (Vorgabe 11.3, Plan TP 5 B4).

Kein Raten: aus der Folge sigma_0 ... sigma_n wird nur dann ein Grenzwert angegeben, wenn die Aenderungen
Delta_k = sigma_k - sigma_(k-1) dasselbe Vorzeichen haben und im Betrag abnehmen (monotone Konvergenz). Dann gilt die
Aitken-Extrapolation

    sigma_inf = sigma_n + Delta_n r / (1 - r),   r = Delta_n / Delta_(n-1),

und die Restabweichung |sigma_n - sigma_inf| / |sigma_inf| sagt, wie weit der letzte Zyklus noch entfernt ist. Sonst steht
die Folge samt Begruendung im Protokoll, ohne Grenzwert. Zwei Werte sind keine Folge: zu wenige Zyklen.
"""
from __future__ import annotations

from typing import Any

_NULL = 1e-12


def konvergenzaussage(werte: list[float | None]) -> dict[str, Any]:
    """Aussage ueber die Folge ``werte`` (hotspot_max je Zyklus, Zyklus 0 zuerst). Schluessel: art, text, werte,
    aenderungen, grenzwert, restabweichung."""
    v = [None if w is None else float(w) for w in werte]
    aus: dict[str, Any] = {"werte": v, "aenderungen": [], "grenzwert": None, "restabweichung": None}
    if not v or any(w is None for w in v):
        aus.update(art="kein_hotspot", text="kein Hot-Spot-Wert in mindestens einem Zyklus (keine Naht oder Blechseite nicht "
                                            "eindeutig): keine Konvergenzaussage")
        return aus
    f = [w for w in v if w is not None]
    d = [b - a for a, b in zip(f[:-1], f[1:])]
    aus["aenderungen"] = d
    if len(f) < 3:
        aus.update(art="zu_wenige_zyklen", text=f"{len(f)} Zyklen: zu wenige fuer eine Konvergenzaussage (mindestens 3)")
        return aus
    bezug = max(abs(w) for w in f)
    if abs(d[-1]) <= _NULL * bezug:
        aus.update(art="monoton_konvergent", grenzwert=f[-1], restabweichung=0.0,
                   text=f"letzte Aenderung null (< {_NULL:g} des Betrags): Grenzwert {f[-1]:.6g} N/mm2")
        return aus
    gleiches_vorzeichen = all(x > 0 for x in d) or all(x < 0 for x in d)
    abnehmend = all(abs(b) < abs(a) for a, b in zip(d[:-1], d[1:]))
    if not (gleiches_vorzeichen and abnehmend):
        aus.update(art="nicht_monoton",
                   text="nicht monoton (Aenderungen " + ", ".join(f"{x:+.4g}" for x in d) + " N/mm2): keine Konvergenzaussage")
        return aus
    r = d[-1] / d[-2]
    grenz = f[-1] + d[-1] * r / (1.0 - r)
    rest = abs(f[-1] - grenz) / abs(grenz) if grenz != 0.0 else float("inf")
    aus.update(art="monoton_konvergent", grenzwert=grenz, restabweichung=rest,
               text=f"monoton konvergent (Aenderungen " + ", ".join(f"{x:+.4g}" for x in d) + f" N/mm2, Verhaeltnis der letzten "
                    f"beiden {r:.3f}): Grenzwert nach Aitken {grenz:.6g} N/mm2, letzter Zyklus {rest * 100:.2f} % davon entfernt")
    return aus


__all__ = ["konvergenzaussage"]
