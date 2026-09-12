"""Spannungsgroessen fuer die Anzeige (analog ANSYS Mechanical) und die Werteskala.

Reine numpy-Logik ohne Qt, damit sie ohne Oberflaeche gemessen werden kann
(``tests/test_spannungen.py``): Groessen je Element aus den Ergebnissen
(Grundspannungen, Hauptspannungen, Vergleichsspannung), ihre Mittelung auf die
Knoten, der Kontaktdruck aus Knotenkraft und Einflussflaeche, und die Grenzen
der Farbskala - automatisch, fest oder mit Grenzwert (355 fuer S355): was
darueber liegt, bekommt eine eigene Farbe, und die Skala nennt den
tatsaechlichen Groesstwert ueber der Grenze.

Einheiten der Anzeige: Spannungen in N/mm², Spalt in mm, Kraefte in kN.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

MPA = 1e-6
ARTEN = ("volumen", "flaechen", "staebe", "kontakt")
ART_TEXT = {"volumen": "Volumen", "flaechen": "Flächen", "staebe": "Stäbe", "kontakt": "Kontakt"}

#: Groessen je Art: Schluessel -> (Beschriftung, Einheit)
VOLUMEN = {"sx": ("σ_x", "N/mm²"), "sy": ("σ_y", "N/mm²"), "sz": ("σ_z", "N/mm²"),
           "txy": ("τ_xy", "N/mm²"), "tyz": ("τ_yz", "N/mm²"), "tzx": ("τ_zx", "N/mm²"),
           "s1": ("σ_1", "N/mm²"), "s2": ("σ_2", "N/mm²"), "s3": ("σ_3", "N/mm²"),
           "sv": ("σ_v (von Mises)", "N/mm²"), "sint": ("σ_int (σ_1 − σ_3, Tresca)", "N/mm²"),
           "tmax": ("τ_max", "N/mm²")}
FLAECHEN = {"sx": ("σ_x", "N/mm²"), "sy": ("σ_y", "N/mm²"), "txy": ("τ_xy", "N/mm²"),
            "s1": ("σ_1", "N/mm²"), "s2": ("σ_2", "N/mm²"), "sv": ("σ_v (von Mises)", "N/mm²")}
STAEBE = {"sx": ("σ_x Rand (|σ_N| + σ_My + σ_Mz)", "N/mm²"), "sn": ("σ_N = N/A", "N/mm²"),
          "smy": ("σ_My = |M_y| z_max/I_y", "N/mm²"), "smz": ("σ_Mz = |M_z| y_max/I_z", "N/mm²")}
KONTAKT = {"p": ("Kontaktdruck p", "N/mm²"), "tau": ("Reibspannung τ", "N/mm²"),
           "spalt": ("Spalt", "mm"), "fn": ("Kontaktkraft F_n", "kN"),
           "zustand": ("Zustand", "-")}
#: Kontaktzustand als Zahl (Faerbung in Klassen, 12.09.2026: "ich sehe nicht,
#: dass die Kontakte da wirken, wo sie sollen")
KONTAKT_ZUSTAND = {"offen": 0, "Kontakt": 1, "Haften": 1, "Verbund": 1, "ohne Trennung": 1,
                   "Gleiten": 2, "Fliessen": 3}
ZUSTAND_TEXT = {0: "offen", 1: "haftet", 2: "gleitet", 3: "fließt"}
ZUSTAND_FARBEN = ["#9e9e9e", "#2e7d32", "#e65100", "#b00020"]
GROESSEN = {"volumen": VOLUMEN, "flaechen": FLAECHEN, "staebe": STAEBE, "kontakt": KONTAKT}
SEITEN = ("max", "oben", "unten")
_KOMPONENTEN = {"sx": 0, "sy": 1, "sz": 2, "txy": 3, "tyz": 4, "tzx": 5}


def kategorien(art: str, groesse: str):
    """{Wert: Text} fuer eine Groesse in Klassen (Kontaktzustand), sonst None."""
    if art == "kontakt" and groesse == "zustand":
        return dict(ZUSTAND_TEXT)
    return None


def skalenformat(lo: float, hi: float) -> str:
    """Zahlenformat der Farbskala: ausgeschrieben statt „2.39e+03“ - die
    Nachkommastellen nach der Spanne (12.09.2026)."""
    try:
        spanne = max(abs(float(lo)), abs(float(hi)))
    except (TypeError, ValueError):
        return "%.3g"
    if not np.isfinite(spanne):
        return "%.3g"
    if spanne >= 100:
        return "%.0f"
    if spanne >= 10:
        return "%.1f"
    if spanne >= 1:
        return "%.2f"
    if spanne >= 0.01:
        return "%.3f"
    return "%.2e"


def schluessel(art: str, groesse: str) -> str:
    """Der Ergebnisschluessel im Modellbaum: ``spannung:<art>:<groesse>``."""
    return f"spannung:{art}:{groesse}"


def beschriftung(art: str, groesse: str, seite: str = "max") -> str:
    """Titel der Farbskala, z. B. ``Volumen σ_v (von Mises) [N/mm²]``."""
    text, einheit = GROESSEN[art][groesse]
    zusatz = ""
    if art == "flaechen" and seite in ("oben", "unten"):
        zusatz = f" {seite}"
    return f"{ART_TEXT[art]} {text}{zusatz} [{einheit}]"


# --------------------------------------------------------------------------
# Groessen je Element
# --------------------------------------------------------------------------
def volumen_werte(S, groesse: str) -> np.ndarray:
    """Eine Groesse je Tensor (n, 6) [sx, sy, sz, txy, tyz, tzx] - in der Einheit
    der Eingabe. Hauptspannungen vektorisiert (Cardano, ec3.fatigue)."""
    S = np.asarray(S, float).reshape(-1, 6)
    if groesse in _KOMPONENTEN:
        return S[:, _KOMPONENTEN[groesse]].copy()
    from .ec3.fatigue import hauptspannungen
    H = hauptspannungen(S)
    s1, s2, s3 = H[:, 0], H[:, 1], H[:, 2]
    if groesse == "s1":
        return s1
    if groesse == "s2":
        return s2
    if groesse == "s3":
        return s3
    if groesse == "sv":
        return np.sqrt(0.5 * ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2))
    if groesse == "sint":
        return s1 - s3
    if groesse == "tmax":
        return 0.5 * (s1 - s3)
    raise KeyError(groesse)


def _ebene_werte(S3: np.ndarray, groesse: str) -> np.ndarray:
    sx, sy, txy = S3[:, 0], S3[:, 1], S3[:, 2]
    if groesse == "sx":
        return sx.copy()
    if groesse == "sy":
        return sy.copy()
    if groesse == "txy":
        return txy.copy()
    m = 0.5 * (sx + sy)
    r = np.sqrt((0.5 * (sx - sy)) ** 2 + txy ** 2)
    if groesse == "s1":
        return m + r
    if groesse == "s2":
        return m - r
    if groesse == "sv":
        return np.sqrt(sx ** 2 - sx * sy + sy ** 2 + 3.0 * txy ** 2)
    raise KeyError(groesse)


def flaechen_werte(oben, unten, groesse: str, seite: str = "max") -> np.ndarray:
    """Eine Groesse je Flaechenelement aus den Spannungen (n, 3) [sx, sy, txy]
    der Ober- und Unterseite; ``seite`` max nimmt je Element den Wert mit dem
    groesseren Betrag (vorzeichenbehaftet)."""
    o = _ebene_werte(np.asarray(oben, float).reshape(-1, 3), groesse)
    if seite == "oben":
        return o
    u = _ebene_werte(np.asarray(unten, float).reshape(-1, 3), groesse)
    if seite == "unten":
        return u
    return np.where(np.abs(o) >= np.abs(u), o, u)


def stab_werte(model, res, groesse: str) -> tuple:
    """Eine Groesse je Stabelement an beiden Enden: (Elementnummern, Werte (n, 2))
    aus den Stabendkraeften (Results.beam_forces) und dem Querschnitt."""
    ids, werte = [], []
    for i, d in res.beam_forces.items():
        e = model.elements[i]
        sec = model.sections[e.sec]
        A = max(float(sec.A), 1e-20)
        N = np.asarray(d["N"], float)
        My = np.asarray(d["My"], float)
        Mz = np.asarray(d["Mz"], float)
        sn = N / A
        smy = np.abs(My) * sec.zmax / max(sec.Iy, 1e-20) if sec.zmax > 0 else np.zeros(2)
        smz = np.abs(Mz) * sec.ymax / max(sec.Iz, 1e-20) if sec.ymax > 0 else np.zeros(2)
        if groesse == "sn":
            w = sn
        elif groesse == "smy":
            w = smy
        elif groesse == "smz":
            w = smz
        elif groesse == "sx":
            w = np.abs(sn) + smy + smz
        else:
            raise KeyError(groesse)
        ids.append(int(i))
        werte.append(w)
    if not ids:
        return np.zeros(0, int), np.zeros((0, 2))
    return np.array(ids), np.array(werte, float).reshape(-1, 2)


# --------------------------------------------------------------------------
# Auf die Knoten
# --------------------------------------------------------------------------
def knotenmittel(nn: int, knoten, werte) -> np.ndarray:
    """Mittelwert je Knoten ueber alle Beitraege (Knoten, Wert); NaN ohne
    Beitrag. Vektorisiert (np.add.at) - fuer die 1,85 Mio. Elemente des
    Drehlagers in Sekunden statt Minuten."""
    knoten = np.asarray(knoten, int).ravel()
    werte = np.asarray(werte, float).ravel()
    acc = np.zeros(int(nn))
    cnt = np.zeros(int(nn))
    if knoten.size:
        np.add.at(acc, knoten, werte)
        np.add.at(cnt, knoten, 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, acc / np.maximum(cnt, 1.0), np.nan)


def _typen():
    from . import elemente as EL
    return set(EL.VOLUMEN_TYPEN), set(EL.SCHALEN_TYPEN), set(EL.EBENE_TYPEN)


def je_knoten(model, res, art: str, groesse: str, seite: str = "max") -> np.ndarray:
    """Die Groesse einer Art auf die Knoten gemittelt (nn,), NaN wo die Art
    keinen Beitrag hat - Spannungen in N/mm², Spalt in mm, Kraefte in kN."""
    nn = int(model.nn)
    if art == "kontakt":
        return kontakt_je_knoten(model, res, groesse)
    vol, schalen, ebene = _typen()
    kn, w = [], []
    if art == "volumen":
        ids = [i for i in res.solid_res if model.elements[i].typ in vol]
        if ids:
            S = np.array([res.solid_res[i] for i in ids], float).reshape(-1, 6)
            v = volumen_werte(S, groesse) * MPA
            for i, x in zip(ids, v):
                nodes = model.elements[i].nodes
                kn.extend(int(n) for n in nodes)
                w.extend([float(x)] * len(nodes))
    elif art == "flaechen":
        ss = res.shell_stress
        ids = [i for i in ss if model.elements[i].typ in schalen]
        if ids:
            o = np.array([ss[i]["sig_top"] for i in ids], float).reshape(-1, 3)
            u = np.array([ss[i]["sig_bot"] for i in ids], float).reshape(-1, 3)
            v = flaechen_werte(o, u, groesse, seite) * MPA
            for i, x in zip(ids, v):
                nodes = model.elements[i].nodes
                kn.extend(int(n) for n in nodes)
                w.extend([float(x)] * len(nodes))
        ids = [i for i in res.solid_res if model.elements[i].typ in ebene]
        if ids:
            S = np.array([res.solid_res[i] for i in ids], float).reshape(-1, 6)
            S3 = S[:, [0, 1, 3]]
            v = flaechen_werte(S3, S3, groesse, "oben") * MPA
            for i, x in zip(ids, v):
                nodes = model.elements[i].nodes
                kn.extend(int(n) for n in nodes)
                w.extend([float(x)] * len(nodes))
    elif art == "staebe":
        ids, v = stab_werte(model, res, groesse)
        for i, x in zip(ids, v):
            nodes = model.elements[int(i)].nodes
            kn.extend((int(nodes[0]), int(nodes[-1])))
            w.extend((float(x[0]) * MPA, float(x[1]) * MPA))
    else:
        raise KeyError(art)
    return knotenmittel(nn, kn, w)


# --------------------------------------------------------------------------
# Kontakt: Druck aus Knotenkraft und Einflussflaeche
# --------------------------------------------------------------------------
def kontaktflaechen(model, knoten) -> np.ndarray:
    """Einflussflaeche je Knoten (nn,) aus den Aussenflaechen der Volumen- und
    Schalenelemente, deren Eckknoten alle zu ``knoten`` gehoeren - die
    Kontaktflaeche, gleichmaessig auf die Eckknoten verteilt. Vektorisiert:
    Seiten je Elementtyp, innere Seiten (zweimal belegt) verworfen."""
    from .elements.solid import FLAECHEN_ECKEN
    vol, schalen, _ebene = _typen()
    nn = int(model.nn)
    drin = np.zeros(nn, bool)
    knoten = np.asarray(knoten, int).ravel()
    if knoten.size == 0:
        return np.zeros(nn)
    drin[knoten] = True
    gruppen: dict = {}
    for e in model.elements:
        if e.typ in vol or e.typ in schalen:
            gruppen.setdefault(e.typ, []).append(e.nodes)
    seiten = []
    for typ, liste in gruppen.items():
        N = np.asarray(liste, int)
        if typ in schalen:
            k = 4 if N.shape[1] >= 4 and typ.endswith(("4", "8", "9")) else 3
            F = np.full((N.shape[0], 4), -1, int)
            F[:, :k] = N[:, :k]
            seiten.append(F)
            continue
        for f in FLAECHEN_ECKEN.get(typ, ()):
            F = np.full((N.shape[0], 4), -1, int)
            F[:, :len(f)] = N[:, list(f)]
            seiten.append(F)
    if not seiten:
        return np.zeros(nn)
    F = np.vstack(seiten)
    key = np.sort(F, axis=1)
    _u, idx, cnt = np.unique(key, axis=0, return_index=True, return_counts=True)
    aussen = F[idx[cnt == 1]]
    gueltig = aussen >= 0
    ok = np.all(np.where(gueltig, drin[np.maximum(aussen, 0)], True), axis=1)
    aussen = aussen[ok]
    A = np.zeros(nn)
    if aussen.size == 0:
        return A
    P = model.nodes
    dreieck = aussen[:, 3] < 0
    flaeche = np.zeros(len(aussen))
    a, b, c = P[aussen[:, 0]], P[aussen[:, 1]], P[aussen[:, 2]]
    flaeche += 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if np.any(~dreieck):
        d = P[np.maximum(aussen[:, 3], 0)]
        flaeche[~dreieck] += 0.5 * np.linalg.norm(np.cross(c - a, d - a), axis=1)[~dreieck]
    ecken = np.where(dreieck, 3.0, 4.0)
    anteil = flaeche / ecken
    for j in range(4):
        m = aussen[:, j] >= 0
        np.add.at(A, aussen[m, j], anteil[m])
    return A


def kontakt_je_knoten(model, res, groesse: str) -> np.ndarray:
    """Kontaktdruck p = F_n/A, Reibspannung τ = F_t/A (N/mm²), Spalt (mm) oder
    Kontaktkraft (kN) je Kontaktknoten (nn,), NaN an allen anderen Knoten.
    A ist die Einflussflaeche des Knotens auf der Kontaktflaeche
    (kontaktflaechen); Summe p·A = Summe F_n."""
    nn = int(model.nn)
    out = np.full(nn, np.nan)
    eintraege = [c for c in (getattr(res, "contact", None) or []) if "node" in c]
    if not eintraege:
        return out
    knoten = np.array([int(c["node"]) for c in eintraege])
    Fn = np.array([float(c.get("Fn", 0.0)) for c in eintraege])
    Ft = np.array([float(c.get("Ft", 0.0)) for c in eintraege])
    gap = np.array([float(c.get("gap", 0.0)) for c in eintraege])
    if groesse == "spalt":
        out[knoten] = gap * 1e3
        return out
    if groesse == "fn":
        out[knoten] = Fn * 1e-3
        return out
    if groesse == "zustand":
        out[knoten] = [float(KONTAKT_ZUSTAND.get(str(c.get("status", "")), 1)) for c in eintraege]
        return out
    A = kontaktflaechen(model, knoten)[knoten]
    with np.errstate(invalid="ignore", divide="ignore"):
        if groesse == "p":
            out[knoten] = np.where(A > 0, Fn / np.maximum(A, 1e-30) * MPA, np.nan)
        elif groesse == "tau":
            out[knoten] = np.where(A > 0, Ft / np.maximum(A, 1e-30) * MPA, np.nan)
        else:
            raise KeyError(groesse)
    return out


# --------------------------------------------------------------------------
# Werteskala
# --------------------------------------------------------------------------
FARBE_UEBER = "#ff00ff"       # ueber der Grenze: Magenta, in keiner Farbtafel enthalten
FARBE_UNTER = "#00e5ff"       # unter der negativen Grenze


@dataclass
class Werteskala:
    """Einstellung der Farbskala der Ergebnisanzeige.

    modus ``auto``: Grenzen aus den Werten; ``fest``: unten/oben; ``grenze``:
    0 (bzw. −Grenze bei negativen Werten) bis Grenze, z. B. 355 fuer S355 -
    Werte darueber bekommen die Farbe FARBE_UEBER, und die Skala nennt ueber
    der Grenze den tatsaechlichen Groesstwert. ``stufen`` Farbstufen (ANSYS:
    9). ``nur_ueber``: nur die Ueberschreitungen faerben (Betrag ueber der
    Grenze, von der Grenze bis zum Groesstwert), alles andere grau.
    """
    modus: str = "auto"
    unten: float = 0.0
    oben: float = 100.0
    grenze: float = 355.0
    stufen: int = 9
    nur_ueber: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d) -> "Werteskala":
        w = cls()
        if isinstance(d, dict):
            for k in ("modus", "unten", "oben", "grenze", "stufen", "nur_ueber"):
                if k in d and d[k] is not None:
                    setattr(w, k, type(getattr(w, k))(d[k]))
        if w.modus not in ("auto", "fest", "grenze"):
            w.modus = "auto"
        w.stufen = int(min(max(w.stufen, 2), 256))
        return w


def _text(x: float) -> str:
    return f"{x:.4g}"


def grenzen(skala: Werteskala, werte, maske=None) -> dict:
    """Die Farbskala fuer diese Werte: ``clim``, ``n_colors``, ``n_labels``,
    ``above_color``/``above_label`` und ``below_color``/``below_label`` fuer
    Werte ausserhalb, ``werte`` (bei nur_ueber: nur die Ueberschreitungen als
    Betrag, sonst NaN), ``anzahl_ueber``/``anzahl_unter`` und ``wmin``/``wmax``.

    ``maske`` (bool je Wert) beschraenkt Grenzen und Zaehlung auf die
    sichtbaren Knoten - so bewertet man ein einzeln gezeigtes Bauteil an
    seiner eigenen Skala (12.09.2026); ``werte`` bleibt vollstaendig."""
    w = np.asarray(werte, float)
    if maske is not None:
        mk = np.asarray(maske, bool)
        g = w[mk] if mk.shape == w.shape else w
        g = g[np.isfinite(g)]
    else:
        g = w[np.isfinite(w)]
    out = {"clim": [0.0, 1.0], "n_colors": int(skala.stufen), "n_labels": int(skala.stufen) + 1,
           "above_color": None, "above_label": None, "below_color": None, "below_label": None,
           "werte": w, "anzahl_ueber": 0, "anzahl_unter": 0, "wmin": None, "wmax": None,
           "modus": skala.modus}
    if g.size == 0:
        return out
    wmin, wmax = float(g.min()), float(g.max())
    out["wmin"], out["wmax"] = wmin, wmax
    if skala.modus == "fest":
        lo, hi = float(skala.unten), float(skala.oben)
        if hi <= lo:
            hi = lo + 1.0
    elif skala.modus == "grenze":
        G = abs(float(skala.grenze)) or 1.0
        lo, hi = (-G if wmin < 0.0 else 0.0), G
        if skala.nur_ueber:
            betrag = np.abs(w)
            out["werte"] = np.where(betrag > G, betrag, np.nan)
            out["anzahl_ueber"] = int(np.sum(betrag[np.isfinite(betrag)] > G))
            hi2 = float(np.nanmax(out["werte"])) if out["anzahl_ueber"] else G + 1.0
            out["clim"] = [G, hi2 if hi2 > G else G + 1.0]
            return out
    else:
        lo, hi = wmin, wmax
        if hi <= lo:
            lo, hi = lo - 0.5, hi + 0.5
    out["clim"] = [lo, hi]
    out["anzahl_ueber"] = int(np.sum(g > hi))
    out["anzahl_unter"] = int(np.sum(g < lo))
    if out["anzahl_ueber"]:
        out["above_color"] = FARBE_UEBER
        out["above_label"] = _text(wmax)
    if out["anzahl_unter"]:
        out["below_color"] = FARBE_UNTER
        out["below_label"] = _text(wmin)
    return out


# --------------------------------------------------------------------------
# Eintraege der Faerbungsliste (Maske Ergebnisse) und des Modellbaums
# --------------------------------------------------------------------------
def feldname(art: str, groesse: str) -> str:
    """Eintrag der Faerbungsliste, z. B. ``Volumen σ_v (von Mises)``."""
    return f"{ART_TEXT[art]} {GROESSEN[art][groesse][0]}"


#: Faerbungseintrag -> (Art, Groesse), in der Reihenfolge Volumen, Flaechen, Staebe, Kontakt
FELDER = {feldname(a, g): (a, g) for a in ARTEN for g in GROESSEN[a]}
#: Gruppe im Modellbaum je Art
GRUPPE = {"volumen": "Spannungen Volumen", "flaechen": "Spannungen Flächen",
          "staebe": "Spannungen Stäbe", "kontakt": "Kontaktspannungen"}


def feld(text) -> tuple | None:
    """(Art, Groesse) zu einem Faerbungseintrag, sonst None."""
    return FELDER.get(str(text))


def arten_im_ergebnis(model, res) -> list:
    """Welche Arten dieses Ergebnis fuellen kann (Volumen, Flaechen, Staebe,
    Kontakt) - einmal je Ergebnis bestimmt und daran gemerkt, denn die Frage
    laeuft ueber alle Elemente (Drehlager: 1,8 Mio.)."""
    if res is None or not hasattr(res, "solid_res") or not hasattr(res, "beam_forces"):
        return []
    merk = getattr(res, "_spannungsarten", None)
    if merk is not None:
        return list(merk)
    vol, schalen, ebene = _typen()
    arten = []
    typen = {model.elements[i].typ for i in res.solid_res} if res.solid_res else set()
    if typen & vol:
        arten.append("volumen")
    if (typen & ebene) or any(model.elements[i].typ in schalen for i in res.shell_res):
        arten.append("flaechen")
    if res.beam_end:
        arten.append("staebe")
    if getattr(res, "contact", None):
        arten.append("kontakt")
    try:
        res._spannungsarten = tuple(arten)
    except AttributeError:
        pass
    return arten
