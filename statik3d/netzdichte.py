"""
Netzdichte: die Elementgröße je Objekt aus den Netzeinstellungen und der
Geometrie („intelligente Vernetzung“).

Eine feste Ziellänge passt selten zu allen Teilen eines Modells: 5 cm sind
für einen 4 m langen Träger zu fein und für eine 8 cm dicke Lasche zu grob.
Darum leitet die **Netzdichte** (grob, mittel, fein) die Elementgröße aus der
Größe des Objekts ab - so viele Elemente über seine größte Abmessung, wie
die Stufe sagt - und die **intelligente** Anpassung zieht sie an kleinen
Kanten (Löcher, schmale Stege) weiter herunter, gedeckelt durch eine
kleinste und größte Elementgröße und eine Höchstzahl von Elementen je
Objekt. „Eigene“ Dichte nimmt die absolute Ziellänge (etwa aus RFEM).

Alles hier ist reine Rechnung; ``anwenden`` schreibt die Teilungen in die
Flächen und gibt die Kantenlängen der Volumen zurück, das Vernetzen selbst
bleibt beim Vernetzer.
"""
from __future__ import annotations

import math

import numpy as np

#: Elemente über die größte Abmessung eines Objekts je Dichtestufe
DICHTEN = {"grob": 8, "mittel": 16, "fein": 32}
STUFEN = ["grob", "mittel", "fein", "eigene"]
FORMEN = {0: "Dreiecke", 1: "Vierecke", 2: "Vierecke, sonst Dreiecke"}
#: Tetraedervolumen je h³ bei einem freien Netz (Erfahrungswert)
TET_JE_H3 = 0.12
STANDARDLAENGE = 0.5


def _knoten(model, obj) -> list:
    """Die Knoten eines Objekts (Fläche: Rand; Volumen: Ränder seiner Flächen)."""
    kn: set = set()
    flaechen = [obj] if hasattr(obj, "linien") else [model.flaechen.get(x) for x in getattr(obj, "flaechen", [])]
    for f in flaechen:
        if f is None:
            continue
        try:
            kn.update(int(k) for k in f.randknoten(model))
        except Exception:                 # noqa: BLE001
            pass
        for name in (getattr(f, "linien", None) or []):
            ln = model.lines.get(name)
            if ln is not None:
                kn.update(int(k) for k in ln.nodes if 0 <= int(k) < model.nn)
    return sorted(kn)


def objektgroesse(model, obj) -> float:
    """Diagonale des umschließenden Quaders [m]."""
    kn = _knoten(model, obj)
    if len(kn) < 2:
        return 0.0
    P = model.nodes[kn]
    return float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))


def _linien(model, obj) -> list:
    namen = list(getattr(obj, "linien", None) or [])
    for name in (getattr(obj, "oeffnungen", None) or []):
        namen += list(name) if isinstance(name, (list, tuple)) else [name]
    for fn in getattr(obj, "flaechen", None) or []:
        f = model.flaechen.get(fn)
        if f is not None:
            namen += list(f.linien or [])
    return [model.lines[n] for n in dict.fromkeys(namen) if n in model.lines]


def kleinste_kante(model, obj) -> float:
    """Kürzeste Randlinie des Objekts [m] (0 = keine Linien)."""
    laengen = []
    for ln in _linien(model, obj):
        try:
            L = float(ln.laenge(model))
        except Exception:                 # noqa: BLE001
            continue
        if L > 1e-9:
            laengen.append(L)
    return min(laengen) if laengen else 0.0


def flaechenmass(model, flaeche) -> float:
    """Fläche des Randpolygons [m²] (Newell)."""
    try:
        ring = [int(k) for k in flaeche.randknoten(model)]
    except Exception:                     # noqa: BLE001
        ring = []
    if len(ring) < 3:
        return 0.0
    P = model.nodes[ring]
    n = np.zeros(3)
    for i in range(len(P)):
        n += np.cross(P[i], P[(i + 1) % len(P)])
    return 0.5 * float(np.linalg.norm(n))


def volumenmass(model, koerper) -> float:
    """Rauminhalt aus den Randflächen (Divergenzsatz, Normalen nach außen
    unbekannt → Betrag); Rückfall: halber umschließender Quader."""
    total = 0.0
    ok = True
    for fn in koerper.flaechen:
        f = model.flaechen.get(fn)
        if f is None:
            ok = False
            break
        try:
            ring = [int(k) for k in f.randknoten(model)]
        except Exception:                 # noqa: BLE001
            ok = False
            break
        if len(ring) < 3:
            ok = False
            break
        P = model.nodes[ring]
        for i in range(1, len(P) - 1):
            total += float(np.dot(P[0], np.cross(P[i], P[i + 1]))) / 6.0
    if ok and abs(total) > 1e-15:
        return abs(total)
    kn = _knoten(model, koerper)
    if len(kn) < 2:
        return 0.0
    P = model.nodes[kn]
    return 0.5 * float(np.prod(np.maximum(P.max(axis=0) - P.min(axis=0), 1e-9)))


def elementlaenge(model, netz, obj) -> dict:
    """Die Kantenlänge h für ein Objekt samt Begründung.

    Rückgabe {"h", "h_dichte", "kante", "groesse", "n", "grund"}; ``n`` ist
    die geschätzte Elementzahl."""
    ist_flaeche = hasattr(obj, "linien")
    D = objektgroesse(model, obj)
    dichte = getattr(netz, "dichte", "mittel") or "mittel"
    ziel = float(getattr(netz, "ziellaenge", 0.0) or 0.0) or STANDARDLAENGE
    grund = []
    if dichte in DICHTEN and D > 0:
        h = D / DICHTEN[dichte]
        grund.append(f"{dichte}: {DICHTEN[dichte]} Elemente über {D:.3f} m")
    else:
        h = ziel
        grund.append(f"Ziellänge {ziel * 1e3:.0f} mm")
    h_dichte = h
    kante = kleinste_kante(model, obj)
    if getattr(netz, "intelligent", True):
        h_min = float(getattr(netz, "h_min", 0.0) or 0.0) or h / 4.0
        h_max = float(getattr(netz, "h_max", 0.0) or 0.0) or h * 4.0
        if kante > 0 and kante < h:
            h = kante
            grund.append(f"kleinste Kante {kante * 1e3:.0f} mm")
        if h < h_min:
            h = h_min
            grund.append(f"nicht unter {h_min * 1e3:.0f} mm")
        if h > h_max:
            h = h_max
            grund.append(f"nicht über {h_max * 1e3:.0f} mm")
    if ist_flaeche:
        A = flaechenmass(model, obj)
        n = A / (h * h) if h > 0 else 0.0
    else:
        V = volumenmass(model, obj)
        n = V / (TET_JE_H3 * h ** 3) if h > 0 else 0.0
    max_el = int(getattr(netz, "max_elemente", 0) or 0)
    if max_el > 0 and n > max_el:
        if ist_flaeche:
            h = math.sqrt(A / max_el)
            n = max_el
        else:
            h = (V / (TET_JE_H3 * max_el)) ** (1.0 / 3.0)
            n = max_el
        grund.append(f"auf {max_el} Elemente begrenzt")
    return {"h": float(h), "h_dichte": float(h_dichte), "kante": float(kante), "groesse": float(D),
            "n": float(n), "grund": ", ".join(grund)}


def _seitenlaengen(model, flaeche):
    """(L_u, L_v) einer Fläche aus vier Randlinien - None sonst."""
    from .mesher import _seiten_aus_linien
    try:
        seiten = _seiten_aus_linien(model, flaeche)
    except Exception:                     # noqa: BLE001
        seiten = None
    if not seiten or len(seiten) != 4:
        return None

    def laenge(kn):
        P = model.nodes[[int(k) for k in kn]]
        return float(np.sum(np.linalg.norm(P[1:] - P[:-1], axis=1)))

    L = [laenge(s[0]) for s in seiten]
    return 0.5 * (L[0] + L[2]), 0.5 * (L[1] + L[3])


def teilung_flaeche(model, netz, flaeche, h: float = None):
    """(nu, nv) für ein abgebildetes Netz aus der Kantenlänge h - None, wenn
    die Fläche nicht vier Randlinien hat."""
    if h is None:
        h = elementlaenge(model, netz, flaeche)["h"]
    seiten = _seitenlaengen(model, flaeche)
    if seiten is None or h <= 0:
        return None
    return max(1, int(round(seiten[0] / h))), max(1, int(round(seiten[1] / h)))


def vorschau(model, netz, flaechen=None, koerper=None) -> dict:
    """Geschätzte Elementzahlen je Objekt und gesamt."""
    flaechen = list(flaechen) if flaechen is not None else list(model.flaechen.values())
    koerper = list(koerper) if koerper is not None else list(model.koerper.values())
    zeilen = []
    n_f = n_k = 0.0
    for f in flaechen:
        e = elementlaenge(model, netz, f)
        t = teilung_flaeche(model, netz, f, e["h"])
        n = float(t[0] * t[1]) if t else e["n"]
        n_f += n
        zeilen.append((f.name, "Fläche", e["h"], n, e["grund"], t))
    for k in koerper:
        e = elementlaenge(model, netz, k)
        n_k += e["n"]
        zeilen.append((k.name, "Volumen", e["h"], e["n"], e["grund"], None))
    return {"zeilen": zeilen, "flaechen": len(flaechen), "koerper": len(koerper),
            "n_flaechen": int(round(n_f)), "n_koerper": int(round(n_k)),
            "n": int(round(n_f + n_k))}


def anwenden(model, netz, flaechen, koerper, log: list = None) -> dict:
    """Teilungen der Flächen aus der Netzdichte setzen (wenn die Einstellung
    das will) und die Kantenlänge je Volumen bestimmen. Rückgabe {Name: h}."""
    aus = {}
    ueber = bool(getattr(netz, "teilung_uebersteuern", True))
    for f in flaechen:
        e = elementlaenge(model, netz, f)
        aus[f.name] = e["h"]
        if ueber:
            t = teilung_flaeche(model, netz, f, e["h"])
            if t is not None:
                f.teilung = [int(t[0]), int(t[1])]
                if log is not None:
                    log.append(f"Netzdichte Fläche {f.name}: h = {e['h'] * 1e3:.0f} mm ({e['grund']}) "
                               f"→ {t[0]} × {t[1]}")
    for k in koerper:
        e = elementlaenge(model, netz, k)
        aus[k.name] = e["h"]
        if log is not None:
            log.append(f"Netzdichte Volumen {k.name}: h = {e['h'] * 1e3:.0f} mm ({e['grund']}), "
                       f"≈ {e['n']:.0f} Elemente")
    return aus
