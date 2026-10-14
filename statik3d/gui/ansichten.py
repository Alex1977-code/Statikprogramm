"""Gespeicherte Ansichten (Ansichtspaket C, 14.10.2026; Vorbild der
Ansichtspunkt von ediBIM, ``viewer/core/ansichtspunkt.ts``).

Eine Ansicht haelt fest, **wie** man auf das Modell schaut: Kamera samt
Projektion und Massstab, Ausgeblendetes (auch Geist und Layer), wahlweise die
Auswahl, Schnittebene und Schnittbox, Darstellungsart und Sichtbarkeit von
Staeben, Flaechen und Volumen, dazu das gezeigte Ergebnis mit Faerbung,
Verlauf und Eigenform - soweit es ohne Rechnung wiederherstellbar ist. Sie
steht im Modell (``Model.ansichten``, :class:`statik3d.model.Ansicht`).

:func:`erfassen` liest das aus dem Fenster, :func:`anwenden` stellt es wieder
her. Was es beim Aufrufen nicht mehr gibt (eine geloeschte Flaeche, ein
neues Netz, ein Ergebnis, das erst gerechnet werden muss), wird
uebersprungen und genannt - nichts davon bricht ab.
"""
from __future__ import annotations

import numpy as np

from ..model import Ansicht
from .. import begriffe as bg

#: Arten des Ausgeblendeten (MainWindow.versteckt): Nummern oder Namen
NUMMERN = ("elemente", "knoten")
NAMEN = (("linien", "lines", "Linie", "Linien"), ("flaechen", "flaechen", "Fläche", "Flächen"),
         ("koerper", "koerper", "Volumen", "Volumen"))
#: Listen der Auswahl, die eine Ansicht mitnehmen kann: Feld -> (Attribut am
#: Fenster, Sammlung am Modell oder None fuer Nummern, Einzahl, Mehrzahl)
AUSWAHL = {"knoten": ("selection", None, "gewählter Knoten", "gewählte Knoten"),
           "elemente": ("sel_elemente", None, "gewähltes Element", "gewählte Elemente"),
           "linien": ("sel_linien", "lines", "gewählte Linie", "gewählte Linien"),
           "flaechen": ("sel_flaechen", "flaechen", "gewählte Fläche", "gewählte Flächen"),
           "koerper": ("sel_koerper", "koerper", "gewähltes Volumen", "gewählte Volumen"),
           "staebe": ("sel_staebe", "members", "gewählter Stab", "gewählte Stäbe")}
#: Sichtbarkeitsschalter der Darstellung: Schluessel -> Aktion am Fenster
TYPEN = {"staebe": "act_staebe", "flaechen": "act_flaechen", "volumen": "act_volumen"}


def _liste(x) -> list:
    return [float(v) for v in x]


def _json(x):
    """Tupel und numpy-Werte so, wie sie nach Speichern und Laden sind."""
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_json(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, dict):
        return {str(k): _json(v) for k, v in x.items()}
    return x


def kamera_lesen(w) -> dict:
    kam = w.plotter.renderer.GetActiveCamera()
    return {"position": _liste(kam.GetPosition()), "ziel": _liste(kam.GetFocalPoint()),
            "oben": _liste(kam.GetViewUp()), "ortho": bool(kam.GetParallelProjection()),
            "massstab": float(kam.GetParallelScale()), "blickwinkel": float(kam.GetViewAngle())}


def kamera_setzen(w, k: dict) -> None:
    """Die Kamera einer Ansicht einstellen - erst die Projektion (sie haelt
    sonst die Bildgroesse und verschiebt die Kamera), dann Lage und Massstab."""
    if not k:
        return
    ren = w.plotter.renderer
    kam = ren.GetActiveCamera()
    ortho = bool(k.get("ortho", False))
    if bool(kam.GetParallelProjection()) != ortho:
        w.projektion_setzen(ortho, merken=False)
    if k.get("blickwinkel"):
        kam.SetViewAngle(float(k["blickwinkel"]))
    w.plotter.camera_position = [list(map(float, k["position"])), list(map(float, k["ziel"])),
                                 list(map(float, k["oben"]))]
    if k.get("massstab"):
        kam.SetParallelScale(float(k["massstab"]))
    ren.ResetCameraClippingRange()
    w._kamera_steht = True


def erfassen(w, name: str, mit_auswahl: bool = False, kommentar: str = "") -> Ansicht:
    """Die Ansicht, wie sie gerade im Fenster steht."""
    m = w.model
    versteckt = {k: sorted(int(i) if k in NUMMERN else str(i) for i in v)
                 for k, v in w.versteckt.items()}
    versteckt["geist"] = bool(getattr(w, "geist", False))
    versteckt["layer_nur"] = str(getattr(w, "_layer_nur", "") or "")
    auswahl = {}
    if mit_auswahl:
        auswahl = {"art": str(getattr(w, "auswahlart", "") or "")}
        for feld, (attr, _samml, _e, _mz) in AUSWAHL.items():
            werte = list(getattr(w, attr, None) if getattr(w, attr, None) is not None else [])
            auswahl[feld] = [int(v) for v in werte] if feld in ("knoten", "elemente") \
                else [str(v) for v in werte]
    schnitt = {}
    if getattr(w, "schnitt", None) is not None:
        schnitt["ebene"] = _json(list(w.schnitt))
        schnitt["regler"] = {"achse": w.cb_schnittachse.currentText(), "lage": int(w.sl_schnitt.value()),
                             "andere_seite": bool(w.act_schnittseite.isChecked())}
        frei = getattr(w, "schnitt_frei", None)
        if frei:
            schnitt["frei"] = _json({k: v for k, v in frei.items() if v is not None})
    box = w.schnittbox_grenzen()
    if box is not None:
        schnitt["box"] = _liste(box)
    darstellung = {"art": str(getattr(w, "darstellung", "Voll")),
                   "typen": {k: bool(getattr(w, a).isChecked()) for k, a in TYPEN.items()
                             if getattr(w, a, None) is not None}}
    ergebnis = {"an": bool(w.ergebnisse_sichtbar()), "quelle": w._aktuelle_quelle(),
                "feld": w.cb_field.currentText(), "verlauf": w.cb_diagram.currentText(),
                "eigenform": int(max(0, w.cb_mode.currentIndex()))}
    return Ansicht(name=name, kamera=kamera_lesen(w), versteckt=versteckt, auswahl=auswahl,
                   schnitt=schnitt, darstellung=darstellung, ergebnis=ergebnis,
                   netz=[len(m.elements), int(m.nn)], kommentar=str(kommentar or ""))


def _setzen_still(widget, fn):
    """``fn(widget)`` ohne Signale (Regler, Haken)."""
    alt = widget.blockSignals(True)
    try:
        fn(widget)
    finally:
        widget.blockSignals(alt)


def _ergebnis_setzen(w, e: dict, fehlt: list) -> None:
    if not e:
        return
    a = getattr(w, "act_ergebnisse", None)
    if a is not None and bool(a.isChecked()) != bool(e.get("an", True)):
        a.setChecked(bool(e.get("an", True)))
    quelle = str(e.get("quelle") or "")
    art, _, wert = quelle.partition(":")
    if art in ("env", "combo", "case"):
        for i in range(w.cb_result.count()):
            d = w.cb_result.itemData(i)
            if d and d[0] == art and str(d[1]) == wert:
                if w.cb_result.currentIndex() != i:
                    w.cb_result.setCurrentIndex(i)
                break
        else:
            fehlt.append(f"Ergebnis {wert} (noch nicht gerechnet)")
    elif art in ("modal", "buckling") and not w.cb_mode.count():
        fehlt.append("Eigenformen (noch nicht gerechnet)")
    for cb, schl in ((w.cb_field, "feld"), (w.cb_diagram, "verlauf")):
        t = str(e.get(schl) or "")
        if t:
            i = cb.findText(t)
            if i >= 0 and cb.currentIndex() != i:
                cb.setCurrentIndex(i)
            elif i < 0 and art not in ("", "modell") and schl == "feld":
                fehlt.append(f"Färbung {t}")
    if w.cb_mode.count():
        i = min(int(e.get("eigenform") or 0), w.cb_mode.count() - 1)
        if w.cb_mode.currentIndex() != i:
            w.cb_mode.setCurrentIndex(i)


def _schnitt_setzen(w, s: dict) -> None:
    ebene = s.get("ebene")
    regler = s.get("regler") or {}
    if s.get("frei"):
        f = s["frei"]
        w.schnitt_frei = {"normale": tuple(f.get("normale") or (0.0, 1.0, 0.0)),
                          "ursprung": tuple(f["ursprung"]) if f.get("ursprung") is not None else None}
    if regler:
        _setzen_still(w.cb_schnittachse, lambda c: c.setCurrentText(str(regler.get("achse", "y"))))
        _setzen_still(w.sl_schnitt, lambda c: c.setValue(int(regler.get("lage", 50))))
        _setzen_still(w.act_schnittseite, lambda c: c.setChecked(bool(regler.get("andere_seite"))))
    if ebene:
        e = list(ebene)
        w.schnitt = (str(e[0]), float(e[1]), bool(e[2])) + tuple(tuple(map(float, x)) for x in e[3:5])
    else:
        w.schnitt = None
        w._schnittwidget_entfernen()
    _setzen_still(w.act_schnitt, lambda c: c.setChecked(w.schnitt is not None))
    w.schnittbox_setzen(s.get("box"), zeichnen=False)


def anwenden(w, a: Ansicht) -> list:
    """Die Ansicht ``a`` im Fenster einstellen und einmal zeichnen. Rueckgabe:
    was uebersprungen wurde, weil es nicht mehr da ist (Texte)."""
    m = w.model
    fehlt: list = []
    netz_gleich = not a.netz or list(a.netz) == [len(m.elements), int(m.nn)]
    v = a.versteckt or {}
    neu = {k: set() for k in w.versteckt}
    for k in NUMMERN:
        werte = [int(i) for i in v.get(k) or []]
        ein, mehr = ("Element", "Elemente") if k == "elemente" else ("Knoten", "Knoten")
        if not netz_gleich and werte:
            fehlt.append(f"{bg.anzahl(len(werte), ein, mehr)} (Netz seither geändert)")
            continue
        grenze = len(m.elements) if k == "elemente" else int(m.nn)
        gut = {i for i in werte if 0 <= i < grenze}
        if len(gut) < len(werte):
            fehlt.append(bg.anzahl(len(werte) - len(gut), ein, mehr))
        if k in neu:
            neu[k] = gut
    for k, samml, ein, mehr in NAMEN:
        da = getattr(m, samml, None) or {}
        werte = [str(n) for n in v.get(k) or []]
        weg = [n for n in werte if n not in da]
        fehlt.extend(f"{ein} {n}" for n in weg)
        if k in neu:
            neu[k] = {n for n in werte if n in da}
    w._sicht_merken()
    w.versteckt = neu
    geist = bool(v.get("geist", False))
    w.geist = geist
    if getattr(w, "act_geist", None) is not None:
        _setzen_still(w.act_geist, lambda c: c.setChecked(geist))
    nur = str(v.get("layer_nur") or "")
    if nur and nur not in (getattr(m, "layer", None) or {}):
        fehlt.append(f"Layer {nur}")
        nur = ""
    w._layer_nur = nur
    cb = getattr(w, "cb_layer", None)
    if cb is not None:
        i = cb.findText(nur) if nur else 0
        _setzen_still(cb, lambda c: c.setCurrentIndex(max(0, i)))
    w._layer_version = getattr(w, "_layer_version", 0) + 1
    # Auswahl (nur, wenn die Ansicht eine mitgenommen hat)
    if a.auswahl:
        w._auswahl_vergessen()
        for feld, (attr, samml, ein, mehr) in AUSWAHL.items():
            werte = a.auswahl.get(feld) or []
            if feld in ("knoten", "elemente"):
                if not netz_gleich and werte:
                    fehlt.append(f"{bg.anzahl(len(werte), ein, mehr)} (Netz seither geändert)")
                    continue
                grenze = int(m.nn) if feld == "knoten" else len(m.elements)
                gut = [int(i) for i in werte if 0 <= int(i) < grenze]
                if len(gut) < len(werte):
                    fehlt.append(bg.anzahl(len(werte) - len(gut), ein, mehr))
                setattr(w, attr, np.asarray(gut, dtype=int) if feld == "knoten" else gut)
            else:
                da = getattr(m, samml, None) or {}
                fehlt.extend(f"{ein} {n}" for n in werte if n not in da)
                setattr(w, attr, [str(n) for n in werte if n in da])
    # Darstellung
    d = a.darstellung or {}
    art = str(d.get("art") or "")
    from . import viewport as vp
    if art in vp.DARSTELLUNGEN:
        w.darstellung = art
        for k_, act in getattr(w, "act_darstellung", {}).items():
            _setzen_still(act, lambda c, k_=k_: c.setChecked(k_ == art))
    for k_, an in (d.get("typen") or {}).items():
        act = getattr(w, TYPEN.get(k_, ""), None)
        if act is not None:
            _setzen_still(act, lambda c, an=an: c.setChecked(bool(an)))
    # Schnitt
    _schnitt_setzen(w, a.schnitt or {})
    # Ergebnis: jeder Wechsel zeichnete neu - gesammelt wird einmal am Ende
    sammeln = getattr(w, "_auswahl_sammeln", False)
    w._auswahl_sammeln = True
    try:
        _ergebnis_setzen(w, a.ergebnis or {}, fehlt)
    finally:
        w._auswahl_sammeln = sammeln
    try:
        w._sicht_knoepfe()
    except Exception:                       # noqa: BLE001
        pass
    w.redraw()
    kamera_setzen(w, a.kamera or {})
    try:
        w.plotter.render()
    except Exception:                       # noqa: BLE001
        pass
    return fehlt
