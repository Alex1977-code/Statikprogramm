"""Konvergenzaussage aus der Folge der Hot-Spot-Werte der adaptiven Zyklen (Vorgabe 11.3, Plan TP 5 B4, Entscheidung O4 vom 02.10.2026).

Kriterium: die letzte relative Aenderung

    r = |sigma_n - sigma_(n-1)| / |sigma_(n-1)|        (wie ``hotspot_change`` der Kurve)

liegt unter der Schranke ``KONVERGENZ_SCHRANKE`` = 3 % (die Zahl der Vorgabe 13 fuer den Hot-Spot gegen Tet10, fuer die Konvergenz uebernommen, O4): ``konvergiert``, sonst ``nicht_konvergiert``. Die Monotonie
wird zusaetzlich genannt, ist aber keine Bedingung: alle Aenderungen Delta_k = sigma_k - sigma_(k-1) mit demselben Vorzeichen und im Betrag
abnehmend. Nur bei einer monotonen Folge gibt es den Grenzwert nach Aitken

    sigma_inf = sigma_n + Delta_n q / (1 - q),   q = Delta_n / Delta_(n-1),

und die Restabweichung |sigma_n - sigma_inf| / |sigma_inf|. Vorher (B4, bis 02.10.2026) gab es eine Aussage nur bei monotoner Folge; die
Messungen zeigen, dass die Folgen der frühen h-Schritte schwingen (Knotenblech 181 -> 175 -> 157 -> 142,6 -> 143,2, T-Stoss p-Phase 111,0 ->
107,4 -> 107,9), obwohl der letzte Schritt unter 0,5 % liegt - "nicht monoton, keine Aussage" sagte dem Anwender nicht, was er wissen muss.
Bekannte Schwaeche des Kriteriums: ein grosser Ueberschwinger vor einer kleinen letzten Aenderung gilt als konvergiert; darum nennt der Text
immer die Aenderungen der Folge und die Monotonie daneben. Nicht aussagefaehig sind ein Zyklus ohne Hot-Spot-Wert, weniger als drei Werte und eine
Folge, die sich nirgends geaendert hat (meist wirkungslose Zyklen, Netz unveraendert).
"""
from __future__ import annotations

from typing import Any

KONVERGENZ_SCHRANKE = 0.03          # 3 %: Zahl der Vorgabe 13 (Hot-Spot gegen Tet10), fuer die letzte Aenderung uebernommen (O4)
_NULL = 1e-12


def _aenderungen_text(d: list[float]) -> str:
    return ", ".join(f"{x:+.4g}" for x in d)


def konvergenzaussage(werte: list[float | None]) -> dict[str, Any]:
    """Aussage ueber die Folge ``werte`` (``hotspot_max`` je Zyklus, Zyklus 0 zuerst). Schluessel: art (``konvergiert``,
    ``nicht_konvergiert``, ``ohne_aenderung``, ``zu_wenige_zyklen``, ``kein_hotspot``), text, werte, aenderungen, letzte_aenderung (relativ),
    schranke, monoton, grenzwert, restabweichung (beide nur bei monotoner Folge)."""
    v = [None if w is None else float(w) for w in werte]
    aus: dict[str, Any] = {"werte": v, "aenderungen": [], "letzte_aenderung": None, "schranke": KONVERGENZ_SCHRANKE, "monoton": None,
                           "grenzwert": None, "restabweichung": None}
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
    bezug = max(max(abs(w) for w in f), 1e-300)
    null = [abs(x) <= _NULL * bezug for x in d]
    if all(null):
        # nichts hat sich geaendert - das belegt keine Konvergenz, sondern meist wirkungslose Zyklen (Netz unveraendert)
        aus.update(art="ohne_aenderung", text=f"der Wert hat sich in keinem Zyklus geaendert ({f[-1]:.6g} N/mm2): keine Konvergenzaussage "
                                               f"(Zyklen ohne Wirkung auf das Netz?)")
        return aus
    vorher = f[-2]
    r = 0.0 if null[-1] else (abs(d[-1]) / abs(vorher) if vorher != 0.0 else float("inf"))
    gleiches_vorzeichen = all(x > 0 for x in d) or all(x < 0 for x in d)
    abnehmend = all(abs(b) < abs(a) for a, b in zip(d[:-1], d[1:]))
    monoton = bool(gleiches_vorzeichen and abnehmend) or (null[-1] and _monoton_bis_null(d))
    art = "konvergiert" if r < KONVERGENZ_SCHRANKE else "nicht_konvergiert"
    aus.update(art=art, letzte_aenderung=r, monoton=monoton)
    if monoton and not null[-1]:
        q = d[-1] / d[-2]
        grenz = f[-1] + d[-1] * q / (1.0 - q)
        aus.update(grenzwert=grenz, restabweichung=abs(f[-1] - grenz) / abs(grenz) if grenz != 0.0 else float("inf"))
    elif monoton:
        aus.update(grenzwert=f[-1], restabweichung=0.0)
    urteil = (f"letzte relative Aenderung {r * 100:.2f} % {'<' if art == 'konvergiert' else '>='} {KONVERGENZ_SCHRANKE * 100:g} %: "
              f"{'konvergiert' if art == 'konvergiert' else 'nicht konvergiert'}")
    folge = (f"Folge monoton (Aenderungen {_aenderungen_text(d)} N/mm2)" if monoton
             else f"Folge nicht monoton (Aenderungen {_aenderungen_text(d)} N/mm2)")
    rest = ""
    if aus["grenzwert"] is not None and not null[-1]:
        rest = f"; Grenzwert nach Aitken {aus['grenzwert']:.6g} N/mm2, letzter Zyklus {aus['restabweichung'] * 100:.2f} % davon entfernt"
    elif aus["grenzwert"] is not None:
        rest = f"; Grenzwert {aus['grenzwert']:.6g} N/mm2"
    aus["text"] = f"{urteil}; {folge}{rest}"
    return aus


def _monoton_bis_null(d: list[float]) -> bool:
    """Die Aenderungen vor einer letzten Null haben dasselbe Vorzeichen und nehmen im Betrag ab (Annaeherung, dann Stillstand)."""
    k = [x for x in d[:-1]]
    if not k:
        return True
    return (all(x > 0 for x in k) or all(x < 0 for x in k)) and all(abs(b) < abs(a) for a, b in zip(k[:-1], k[1:]))


__all__ = ["konvergenzaussage", "KONVERGENZ_SCHRANKE"]
