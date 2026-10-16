"""Starre Scheiben ueber einer Bohrung: Lochrand starr oder Kreisring verteilend (seit 16.10.2026).

Anlass ist das Drehlager (G0, Netz Mittel, tet10): die 64 starren Scheiben
aus RFEM (SurfaceStiffnessRigid, Kreisscheibe genau ueber der Bohrung) haengen
die ganze Anker- bzw. Schraubenkraft nach fugen.starre_flaechen_koppeln starr
an den Lochrand - eine Linie. Im Spannschritt der plastischen Rechnung liefen
die Ankerplatten dort weg (Diagnose scratchpad dl_neu/scheiben_einleitung.md).

**Entscheidung des Anwenders vom 16.10.2026**, woertlich: „Mutterkraft an
allen 64 Scheiben über einen Kreisring einleiten, verteilend (RBE3,
flächenanteilig), nicht starr (eine starre Kopplung erzeugt Spitzen an den
Ringkanten). Innen-Ø = Bohrung, Außen-Ø = Auflage von Mutter bzw. Scheibe.
Maße liefere ich aus der Zeichnung. Bis dahin Normmaße der Mutter bzw.
Scheibe ansetzen und als Annahme kennzeichnen.“ Und: „Warnungen ‚Kraft ohne
Fläche‘ und ‚starre Scheibe koppelt nur Lochrand‘ in plastischen Rechnungen
vor dem Start deutlich hervorheben und bestätigen lassen, weil sie die
Konvergenz verhindern können. In elastischen Rechnungen bleibt es bei
Warnung und netzabhängiger Zone.“

Die Einstellung steht je Scheibe in ``Flaeche.einleitung``; leer heisst
„Lochrand starr (bisher)“, und so bleiben alte Dateien und neue RFEM-Importe.
Umgestellt wird nur auf Anweisung (:func:`umstellen`,
:func:`alle_auf_kreisring`, Rueckgaengig ueber :func:`zuruecksetzen`).
Gekoppelt wird in fugen.starre_flaechen_koppeln mit
stabeinleitung.ring_auf_ebene - dieselbe Integration, dieselben wirksamen
Gewichte, dieselbe Zwangsmatrix und dieselbe Pruefung von Kraftsumme und
Moment wie bei den verteilend eingeleiteten Stabenden.

**Normmasse als Annahme** (:func:`normmass`): aus dem Durchmesser des Stabs an
der Scheibe (Kreisquerschnitt, sonst aus der Flaeche), nie aus einem Namen.
Ist er ein Nennmass von ISO 7089, gilt der Aussendurchmesser d2 der
Unterlegscheibe - das Modell sagt nicht, ob Kopf oder Mutter aussen sitzt,
und beide liegen auf der Scheibe (M16 30 mm, M20 37 mm). Sonst ist es ein
Gewindestab (Drehlager: Ø 40, Spannstahl 835/1030); ein eindeutiges Normmass
der Ankermutter fand sich nicht (Herstellerangaben DYWIDAG und SAS nennen es
nicht oeffentlich, die Zulassungen liegen nicht vor). Dann gilt d_w der
Sechskantmutter nach ISO 4032 der naechsten Groesse darueber (Ø 40 -> M42,
d_w = 60 mm, s = 65 mm). Alles davon traegt das Kennzeichen „Annahme“, bis
der Anwender ein Mass eintraegt.
"""
from __future__ import annotations

import copy
import math

import numpy as np

LOCHRAND, RING = "lochrand", "ring"
TEXTE = {LOCHRAND: "Lochrand starr (bisher)", RING: "Kreisring verteilend (RBE3, flächenanteilig)"}
#: Mindestzahl tragender Knoten im Ring (Gewicht > 0). Gewaehlt, nicht
#: gemessen: drei Knoten bestimmen die Drehung des Masters, sechs geben in
#: jeder Richtung der Ebene ein Paar gegenueberliegender. Darunter kommt eine
#: WARNUNG; unter drei bleibt die Scheibe am Lochrand (fugen.starre_flaechen_koppeln).
MINDEST_KNOTEN = 6
#: Mittlere Pressung im Ring, ab der der Hinweis „Auflage prüfen
#: (Zeichnungsmaß)“ kommt - 3 f_y (Vorgabe von main, 16.10.2026: unter der
#: Mutter ist die Pressung gestuetzt, ueber dem Dreifachen ist das Mass zu
#: klein angenommen)
GRENZE_PRESSUNG_FY = 3.0
AUFLAGE_PRUEFEN = "Auflage prüfen (Zeichnungsmaß)"
#: Bis zu dieser Abweichung [m] ist ein Stabdurchmesser ein Nennmass
NENN_TOL = 1e-4
#: Abweichung der Randpunkte vom mittleren Radius, bis zu der eine starre
#: Flaeche eine Kreisscheibe ist (auf den Radius bezogen): die Sehnen der
#: Abtastung (fugen.STARR_ABTASTUNG) liegen weit darunter
KREIS_TOL = 0.02

#: ISO 7089 (Flache Scheiben, Normalreihe): Nennmass [mm] -> d2 [mm]
ISO_7089_D2 = {10: 20.0, 12: 24.0, 14: 28.0, 16: 30.0, 20: 37.0, 24: 44.0, 27: 50.0, 30: 56.0,
               36: 66.0, 42: 78.0, 48: 92.0}
#: ISO 4032 (Sechskantmuttern Typ 1): Gewinde [mm] -> (s, d_w,min) [mm]
ISO_4032 = {12: (18.0, 16.6), 16: (24.0, 22.5), 20: (30.0, 27.7), 24: (36.0, 33.3), 30: (46.0, 42.8),
            36: (55.0, 51.1), 42: (65.0, 60.0), 48: (75.0, 69.5), 56: (85.0, 78.7), 64: (95.0, 88.2)}


def _mm(x: float, nk: int = 1) -> str:
    return f"{float(x) * 1e3:.{nk}f}".replace(".", ",")


def _zahl(x: float, nk: int = 1) -> str:
    return f"{float(x):.{nk}f}".replace(".", ",")


def _knapp(x: float) -> str:
    """„60“ bzw. „27,7“ - Normmasse ohne nachlaufende Null."""
    t = _zahl(x, 1)
    return t[:-2] if t.endswith(",0") else t


# --------------------------------------------------------------------------
# Einstellung
# --------------------------------------------------------------------------
def einstellung(f) -> dict:
    """Die Einleitung der starren Flaeche ``f``: {"art", "d_innen", "d_aussen",
    "annahme", "quelle"}; leer oder unbekannt = Lochrand."""
    e = dict(getattr(f, "einleitung", None) or {})
    if str(e.get("art", "")) != RING or not float(e.get("d_aussen", 0.0) or 0.0) > 0.0:
        return {"art": LOCHRAND, "d_innen": 0.0, "d_aussen": 0.0, "annahme": False, "quelle": ""}
    return {"art": RING, "d_innen": float(e.get("d_innen", 0.0) or 0.0),
            "d_aussen": float(e.get("d_aussen", 0.0) or 0.0), "annahme": bool(e.get("annahme", False)),
            "quelle": str(e.get("quelle", "") or "")}


def kennung(e: dict, d_bohrung: float = 0.0) -> str:
    """„ring 51.000/60.000“ (Innen-Ø wirksam, aus der Bohrung, wenn 0) bzw. „lochrand“."""
    if e.get("art") != RING:
        return LOCHRAND
    di = float(e.get("d_innen", 0.0) or 0.0) or float(d_bohrung)
    return f"ring {di * 1e3:.3f}/{float(e['d_aussen']) * 1e3:.3f}"


# --------------------------------------------------------------------------
# Die Scheiben des Modells
# --------------------------------------------------------------------------
def _stab_an(model, knoten: int, stab_an: dict, mitglied: dict) -> tuple:
    """(Stabname, Element) des Stabs, der am ``knoten`` endet - ("", None) ohne.
    ``stab_an`` aus stabeinleitung.stabelemente_an, ``mitglied`` Element -> Stab."""
    for i in stab_an.get(int(knoten), []):
        return mitglied.get(int(i), f"E{i}"), model.elements[int(i)]
    return "", None


def stab_durchmesser(model, element) -> float:
    """Durchmesser [m] des Stabquerschnitts: Kreis (typ circle) die Hoehe h,
    sonst aus der Flaeche (d = sqrt(4 A / pi)); 0 ohne Querschnitt."""
    sec = (getattr(model, "sections", None) or {}).get(getattr(element, "sec", None)) if element is not None else None
    if sec is None:
        return 0.0
    if str(getattr(sec, "typ", "")) == "circle" and float(getattr(sec, "h", 0.0) or 0.0) > 0:
        return float(sec.h)
    A = float(getattr(sec, "A", 0.0) or 0.0)
    return math.sqrt(4.0 * A / math.pi) if A > 0 else 0.0


def normmass(d_stab: float, d_innen: float) -> tuple:
    """(d_aussen [m], Quelle) des Normmasses fuer einen Stab vom Durchmesser
    ``d_stab`` - oder (0, Grund). Siehe Kopf des Moduls."""
    if not d_stab > 0:
        return 0.0, "kein Kreisquerschnitt am Stab – Außen-Ø bitte eintragen"
    d = d_stab * 1e3
    for nenn, d2 in ISO_7089_D2.items():
        if abs(d - nenn) <= NENN_TOL * 1e3:
            da = d2 * 1e-3
            quelle = f"ISO 7089 M{nenn}: Unterlegscheibe d₂ = {_knapp(d2)} mm"
            break
    else:
        groesser = [g for g in sorted(ISO_4032) if g >= d - NENN_TOL * 1e3]
        if not groesser:
            return 0.0, f"kein Normmaß für Ø {_zahl(d)} mm – Außen-Ø bitte eintragen"
        g = groesser[0]
        s, dw = ISO_4032[g]
        da = dw * 1e-3
        quelle = (f"ISO 4032 M{g} (nächste Größe zu Ø {_zahl(d, 0)} mm): Sechskantmutter "
                  f"d_w = {_knapp(dw)} mm, s = {_knapp(s)} mm")
    if not da > d_innen:
        return 0.0, (f"Normmaß {_mm(da)} mm nicht größer als die Bohrung {_mm(d_innen)} mm – "
                     "Außen-Ø bitte eintragen")
    return da, quelle


def _vorspannkraft(model, stab: str) -> float:
    """Die groesste Vorspannkraft [N] eines Lastfalls im Stab ``stab`` - die
    Kraft, mit der die Mutter auf die Scheibe drueckt, soweit sie vor der
    Rechnung feststeht; 0 ohne."""
    F = 0.0
    for lc in (getattr(model, "load_cases", None) or {}).values():
        for v in (getattr(lc, "vorspannungen", None) or []):
            if getattr(v, "art", "stab") == "stab" and str(getattr(v, "ziel", "")) == stab:
                F = max(F, abs(float(getattr(v, "kraft", 0.0) or 0.0)))
    return F


def fy_koerper(model, kname: str):
    """f_y [Pa] des Werkstoffs eines Koerpers (wie in der Plastizitaet ohne
    Dickenstufe) - None ohne."""
    k = (getattr(model, "koerper", None) or {}).get(kname)
    mat = (getattr(model, "materials", None) or {}).get(getattr(k, "material", "") if k is not None else "")
    fy = getattr(mat, "fy", None) if mat is not None else None
    return float(fy) if fy else None


def _koerper_der_knoten(model, gesucht: set) -> dict:
    """{Knoten: Koerper} fuer die Knoten ``gesucht`` - ein Durchgang ueber die
    Elemente der Koerper (nur fuer die Anzeige; am Drehlager einige Sekunden)."""
    aus: dict = {}
    if not gesucht:
        return aus
    for kname, k in (getattr(model, "koerper", None) or {}).items():
        for i in (getattr(k, "elemente", None) or []):
            i = int(i)
            if 0 <= i < len(model.elements):
                for x in model.elements[i].nodes:
                    if int(x) in gesucht:
                        aus.setdefault(int(x), kname)
    return aus


def scheiben(model, mit_koerper: bool = True) -> list:
    """Die starren Kreisscheiben mit einem Stabende in der Mitte, je Scheibe
    ein Woerterbuch: name, master, stab, d_stab, d_bohrung, mitte, normale,
    einleitung (:func:`einstellung`), d_innen (wirksam), d_aussen, annahme,
    quelle, vorschlag (Normmass) und vorschlag_quelle, F (Vorspannkraft),
    A_ring, pressung, koerper, fy, verhaeltnis (pressung / f_y), hinweis."""
    from scipy.spatial import cKDTree
    from . import fugen
    from .stabeinleitung import stabelemente_an
    aus = []
    starre = fugen.starre_flaechen(model)
    if not getattr(model, "nn", 0) or not starre:
        return aus
    X = np.asarray(model.nodes, float)
    stab_an = stabelemente_an(model)
    mitglied = {int(i): str(n) for n, mem in (getattr(model, "members", None) or {}).items()
                for i in (mem.elements or [])}
    baum = cKDTree(X)
    for f in starre:
        geo = fugen.scheibe_geometrie(model, f)
        if geo is None or not geo["kreis"]:
            continue
        c, r = geo["mitte"], geo["r"]
        nahe = [int(i) for i in baum.query_ball_point(c, max(0.5e-3, 0.1 * r))]
        master = next((i for i in sorted(nahe, key=lambda i: float(np.linalg.norm(X[i] - c)))
                       if i in stab_an), None)
        if master is None:
            continue
        stab, el = _stab_an(model, master, stab_an, mitglied)
        d_stab = stab_durchmesser(model, el)
        e = einstellung(f)
        d_bohr = 2.0 * r
        di = e["d_innen"] or d_bohr
        vorschlag, vq = normmass(d_stab, di)
        aus.append(dict(name=f.name, master=int(master), stab=stab, d_stab=d_stab, d_bohrung=d_bohr,
                        mitte=c, normale=geo["normale"], einleitung=e["art"], d_innen=di,
                        d_aussen=e["d_aussen"], annahme=e["annahme"], quelle=e["quelle"],
                        vorschlag=vorschlag, vorschlag_quelle=vq, F=_vorspannkraft(model, stab),
                        A_ring=0.0, pressung=None, koerper="", fy=None, verhaeltnis=None, hinweis=""))
    if mit_koerper and aus:
        # der Koerper unter der Scheibe: der eines gekoppelten Knotens (Ring
        # oder Lochrand) - ein Durchgang fuer alle Scheiben
        je: dict = {}
        for sk in (getattr(model, "starrkoerper", None) or []):
            je.setdefault(str(getattr(sk, "name", "")), []).extend(int(x) for x in sk.slaves[:4])
        for k in (getattr(model, "kopplungen", None) or []):
            g = str(getattr(k, "gruppe", ""))
            if g.startswith(fugen.STARR_GRUPPE) and len(je.get(g, [])) < 4:
                je.setdefault(g, []).append(int(k.node_b))
        knoten_von = {z["name"]: (je.get(_scheibe_name(z["name"])) or je.get(fugen.STARR_GRUPPE + z["name"]) or [])
                      for z in aus}
        ko = _koerper_der_knoten(model, {x for v in knoten_von.values() for x in v})
        for z in aus:
            k = next((ko[x] for x in knoten_von[z["name"]] if x in ko), "")
            if k:
                z["koerper"] = k
                z["fy"] = fy_koerper(model, k)
    for z in aus:
        pressung_setzen(z)
    return aus


def _scheibe_name(fname: str) -> str:
    from .stabeinleitung import SCHEIBE
    return SCHEIBE + str(fname)


def pressung_setzen(z: dict) -> dict:
    """Mittlere Pressung F / A_Ring [Pa] und ihr Verhaeltnis zu f_y in die
    Zeile ``z`` (Ring nach Einstellung, sonst nach dem Normmass); Hinweis
    „Auflage prüfen (Zeichnungsmaß)“ ab GRENZE_PRESSUNG_FY f_y."""
    da = z["d_aussen"] if z.get("einleitung") == RING else z.get("vorschlag", 0.0)
    di = z["d_innen"]
    A = math.pi / 4.0 * (da * da - di * di) if da > di else 0.0
    z["A_ring"] = A
    z["pressung"] = z["F"] / A if A > 0 and z.get("F") else None
    z["verhaeltnis"] = z["pressung"] / z["fy"] if z["pressung"] is not None and z.get("fy") else None
    z["hinweis"] = AUFLAGE_PRUEFEN if (z["verhaeltnis"] or 0.0) > GRENZE_PRESSUNG_FY else ""
    return z


def pressung_text(z: dict) -> str:
    """„1203,6 N/mm² = 3,39 f_y“ bzw. „–“."""
    if z.get("pressung") is None:
        return "–"
    t = f"{_zahl(z['pressung'] / 1e6)} N/mm²"
    if z.get("verhaeltnis") is not None:
        t += f" = {_zahl(z['verhaeltnis'], 2)} f_y"
    return t


def gruppen(zeilen: list) -> list:
    """Die Scheiben je Gruppe gleicher Bohrung (auf 0,1 mm) und gleichen
    Stabdurchmessers: [(Schluessel-Text, [Zeilen])], groesste Bohrung zuerst."""
    g: dict = {}
    for z in zeilen:
        schl = (round(z["d_bohrung"] * 1e4), round(z["d_stab"] * 1e4))
        g.setdefault(schl, []).append(z)
    aus = []
    for (b, s), liste in sorted(g.items(), key=lambda x: (-x[0][0], -x[0][1])):
        aus.append((f"Bohrung Ø {_zahl(b / 10)} mm, Stab Ø {_zahl(s / 10)} mm", liste))
    return aus


# --------------------------------------------------------------------------
# Umstellen (nur auf Anweisung)
# --------------------------------------------------------------------------
def umstellen(model, namen, art: str, d_aussen: float = None, d_innen: float = 0.0) -> dict:
    """Die Scheiben ``namen`` auf ``art`` stellen. Kreisring ohne ``d_aussen``:
    das Normmass als Annahme; mit ``d_aussen`` gilt es als eingetragen (das
    Kennzeichen „Annahme“ entfaellt). Rueckgabe {"vorher": {Name: Einleitung},
    "umgestellt": [Namen], "offen": [(Name, Grund)]} - ``vorher`` nimmt
    :func:`zuruecksetzen` zurueck."""
    zeilen = {z["name"]: z for z in scheiben(model, mit_koerper=False)}
    aus = {"vorher": {}, "umgestellt": [], "offen": []}
    for name in namen:
        f = (getattr(model, "flaechen", None) or {}).get(name)
        z = zeilen.get(name)
        if f is None or z is None:
            aus["offen"].append((name, "keine starre Kreisscheibe mit Stabende in der Mitte"))
            continue
        alt = copy.deepcopy(dict(getattr(f, "einleitung", None) or {}))
        if art == LOCHRAND:
            neu = {}
        else:
            di = float(d_innen or 0.0)
            di_wirk = di or z["d_bohrung"]
            if d_aussen:
                if not float(d_aussen) > di_wirk:
                    aus["offen"].append((name, f"Außen-Ø {_mm(d_aussen)} mm nicht größer als Innen-Ø "
                                               f"{_mm(di_wirk)} mm"))
                    continue
                neu = {"art": RING, "d_innen": di, "d_aussen": float(d_aussen), "annahme": False,
                       "quelle": "eingetragen"}
            else:
                da, quelle = normmass(z["d_stab"], di_wirk)
                if not da:
                    aus["offen"].append((name, quelle))
                    continue
                neu = {"art": RING, "d_innen": di, "d_aussen": da, "annahme": True, "quelle": quelle}
        if neu == alt:
            continue
        aus["vorher"][name] = alt
        f.einleitung = neu
        aus["umgestellt"].append(name)
    return aus


def alle_auf_kreisring(model) -> dict:
    """„alle auf Kreisring umstellen (Normmaße als Annahme)“: jede starre
    Kreisscheibe, die am Lochrand haengt, bekommt den Kreisring mit dem
    Normmass. Was schon auf Kreisring steht, bleibt (auch ein eingetragenes
    Mass). Rueckgabe wie :func:`umstellen`."""
    namen = [z["name"] for z in scheiben(model, mit_koerper=False) if z["einleitung"] == LOCHRAND]
    return umstellen(model, namen, RING)


def zuruecksetzen(model, vorher: dict) -> int:
    """Die Einleitungen von vor :func:`umstellen` wieder setzen; Zahl der Scheiben."""
    n = 0
    for name, e in (vorher or {}).items():
        f = (getattr(model, "flaechen", None) or {}).get(name)
        if f is not None:
            f.einleitung = copy.deepcopy(e)
            n += 1
    return n


def umstell_zeile(erg: dict) -> str:
    """Protokollzeile nach dem Umstellen."""
    from .begriffe import anzahl
    n = len(erg.get("umgestellt") or [])
    t = (f"{anzahl(n, 'starre Scheibe', 'starre Scheiben')} umgestellt "
         f"({', '.join(erg['umgestellt'][:8])}{' …' if n > 8 else ''})" if n else "keine Scheibe umgestellt")
    if erg.get("offen"):
        t += "; nicht umgestellt: " + "; ".join(f"{a}: {b}" for a, b in erg["offen"][:4]) \
             + (" …" if len(erg["offen"]) > 4 else "")
    return t


# --------------------------------------------------------------------------
# Protokoll nach dem Koppeln
# --------------------------------------------------------------------------
def ring_zeilen(ringe: list) -> list:
    """Die Protokollzeilen der ueber Kreisring eingeleiteten Scheiben, je
    gleichem Ring, gleicher Quelle und gleicher Pressung gebuendelt; je
    Buendel mit „Auflage prüfen (Zeichnungsmaß)“ ab 3 f_y eine WARNUNG."""
    from .begriffe import anzahl
    if not ringe:
        return []
    g: dict = {}
    for r in ringe:
        schl = (r["kennung"], r["quelle"], r["annahme"], _zahl((r["pressung"] or 0.0) / 1e6),
                _zahl(r["verhaeltnis"], 2) if r["verhaeltnis"] is not None else "")
        g.setdefault(schl, []).append(r)
    zeilen = [f"{anzahl(len(ringe), 'starre Scheibe', 'starre Scheiben')} über einen Kreisring "
              "eingeleitet (RBE3 ohne Versteifung, flächenanteilig; Bezugsknoten das Stabende):"]
    warn = []
    for (ken, quelle, annahme, _p, _v), liste in sorted(g.items(), key=lambda x: -len(x[1])):
        r0 = liste[0]
        di, da = ken.split(" ", 1)[1].split("/")
        kn = sorted(r["tragend"] for r in liste)
        knt = f"{kn[0]}" if kn[0] == kn[-1] else f"{kn[0]}–{kn[-1]}"
        A = sorted(r["flaeche"] for r in liste)
        t = (f"  Ø {_zahl(float(di))}/{_zahl(float(da))} mm"
             + (f" ({'Annahme ' if annahme else ''}{quelle})" if quelle else "")
             + f", Fläche {_zahl(A[0] * 1e6)} mm² (Soll {_zahl(r0['flaeche_nenn'] * 1e6)}), {knt} Knoten")
        if r0["pressung"] is not None:
            t += f", mittlere Pressung aus Vorspannung {pressung_text(r0)}"
        t += f" ({len(liste)}×: {', '.join(r['name'] for r in liste[:6])}{' …' if len(liste) > 6 else ''})"
        zeilen.append(t)
        if (r0["verhaeltnis"] or 0.0) > GRENZE_PRESSUNG_FY:
            warn.append(f"WARNUNG: {AUFLAGE_PRUEFEN}: mittlere Pressung {pressung_text(r0)} über "
                        f"{_zahl(GRENZE_PRESSUNG_FY, 0)} f_y an {anzahl(len(liste), 'Scheibe', 'Scheiben')} "
                        f"mit Ø {_zahl(float(di))}/{_zahl(float(da))} mm"
                        + (" – das Normmaß ist eine Annahme" if annahme else ""))
    return zeilen + warn


# --------------------------------------------------------------------------
# Plastische Rechnung: deutlicher Hinweis vor dem Start
# --------------------------------------------------------------------------
def plastisch_pruefen(model, stellen: list = None) -> dict:
    """Was vor einer plastischen Rechnung deutlich zu sagen ist: die Stellen
    „Kraft ohne Fläche“ (spitzenstellen.kandidaten ohne Zonen) und die
    Kreisscheiben, die am Lochrand haengen. Rueckgabe {"stellen": [...],
    "zeilen": [Warnzeilen der Stellen], "lochrand": [Namen], "text": Text
    fuer Dialog und Protokoll (leer = nichts zu sagen)}."""
    from . import spitzenstellen as sp
    if stellen is None:
        try:
            stellen = sp.kandidaten(model, zonen=False)
        except Exception:                      # noqa: BLE001 - der Hinweis haelt nichts auf
            stellen = []
    lochrand = [z["name"] for z in scheiben(model, mit_koerper=False) if z["einleitung"] == LOCHRAND]
    zeilen = sp.warnzeilen(stellen) if stellen else []
    if not zeilen and not lochrand:
        return {"stellen": stellen, "zeilen": [], "lochrand": [], "text": ""}
    text = ("Plastische Rechnung mit Kraft ohne Fläche: " + "; ".join(zeilen) if zeilen
            else "Plastische Rechnung mit starren Scheiben am Lochrand")
    if lochrand:
        text += (f". {len(lochrand)} starre {'Scheibe hängt' if len(lochrand) == 1 else 'Scheiben hängen'} "
                 "nur am Lochrand")
    text += (". Dort fließt der Werkstoff netzabhängig, und das kann die Konvergenz der plastischen "
             "Rechnung verhindern (Drehlager G0, Mittel: die Ankerplatten liefen am Lochrand weg).")
    if lochrand:
        text += " Abhilfe: die Scheiben über einen Kreisring einleiten (Modell → Scheiben einleiten)."
    return {"stellen": stellen, "zeilen": zeilen, "lochrand": lochrand, "text": text}


def plastisch_zeile(model) -> str:
    """Die deutliche Protokollzeile fuer Rechnungen ohne Oberflaeche - leer,
    wenn nichts zu sagen ist."""
    h = plastisch_pruefen(model)
    return f"WARNUNG – BITTE LESEN: {h['text']}" if h["text"] else ""
