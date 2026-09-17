"""Importhinweise (17.09.2026): was das Programm nach dem Import an der
Modellierung erkennt und dem Anwender **vorschlaegt** - nicht von selbst
aendert ("nicht automatisch beim Import setzen, da du nicht wissen kannst,
ob das vom User gewuenscht ist; als Hinweis zeigen und fragen").

Ein Hinweis ist ein Woerterbuch, das mit dem Modell gespeichert wird:

    {"art": "reibung" | "spiel",
     "text": "...",                              # was erkannt wurde und der Vorschlag
     "objekte": [["kontaktbedingung", "Deckel 1"], ["geokoerper_einzeln", "V61"]],
     "vorschlag": {...},                         # was "So einstellen" tut
     "erledigt": "" | "angewendet" | "verworfen"}

Regeln (gemessen am Drehlager, 17.09.2026):

* **reibung** - eine Kontaktfuge haftet in der Ebene (RFEM "schubstarr",
  Typ 4) an einem zylindrischen Bauteil. Ein Passstift traegt ueber
  Formschluss, nicht ueber eine schubstarre Fuge; die haftende Kante erzeugt
  die Spannungsspitze am Bohrungsaustritt. Vorschlag: Reibungsbehaftet mit
  mu = 0,2.
* **spiel** - ein zylindrisches Bauteil sitzt ohne Spiel in einer Bohrung
  (ein anderes Bauteil fuehrt Boegen mit demselben Radius auf derselben
  Achse; am Drehlager r = 12,500 mm beidseits). Vorschlag: Spiel geben,
  0,02 mm am Durchmesser (statik3d.spiel).

Die Regeln rechnen auf dem Modell, nicht auf der Quelldatei - sie gelten
darum fuer jeden Import und fuer von Hand gebaute Modelle.
"""
from __future__ import annotations

import numpy as np

#: Vorschlag fuer den Reibbeiwert Stahl auf Stahl
MU_VORSCHLAG = 0.2
#: Vorschlag fuer das Durchmesserspiel [m]
SPIEL_VORSCHLAG = 2e-5


def _zylinder_alle(model) -> dict:
    from . import spiel as sp
    aus = {}
    for name in (getattr(model, "koerper", None) or {}):
        z = sp.zylinder(model, name)
        if z.get("ok"):
            aus[name] = z
    return aus


def _kreise_je_koerper(model) -> dict:
    """{Koerper: [(Mitte, Radius, Normale)]} aller Boegen seiner Flaechen."""
    from . import spiel as sp
    aus: dict = {}
    for name, k in (getattr(model, "koerper", None) or {}).items():
        for fn in k.flaechen or []:
            f = model.flaechen.get(fn)
            if f is None:
                continue
            for ln in sp._linien_der_flaeche(f):
                L = model.lines.get(ln)
                if L is None:
                    continue
                try:
                    kr = sp._bogen_kreis(L, model)
                except ValueError:
                    kr = None
                if kr is not None:
                    aus.setdefault(name, []).append(kr)
    return aus


def _haftet_ohne_zug(kb) -> bool:
    """Schubstarr in der Ebene, aber Ausfall bei Zug - RFEM Typ 4."""
    b_n = kb.dof_behaviour(2)
    if b_n.typ in ("rigid", "spring"):
        return False                         # Verbund / ohne Trennung: verschweisst gedacht
    return any(kb.dof_behaviour(d).typ == "rigid" for d in (0, 1))


def erzeugen(model) -> list:
    """Die Hinweise zum Modell - neu gerechnet, ohne die alten zu kennen."""
    aus: list = []
    zyl = _zylinder_alle(model)
    if not zyl:
        return aus
    # reibung: haftende Fugen an Zylindern
    for name, kb in (getattr(model, "kontaktbedingungen", None) or {}).items():
        if not _haftet_ohne_zug(kb):
            continue
        beteiligt = list(kb.koerpernamen or []) + list(getattr(kb, "gegenkoerper", None) or [])
        zk = [k for k in beteiligt if k in zyl]
        if not zk:
            continue
        aus.append({
            "art": "reibung",
            "text": (f"Kontaktfuge „{name}“ haftet in der Fugenebene (RFEM: schubstarr) am zylindrischen "
                     f"Bauteil {', '.join(zk)}. Ein Passstift trägt über Formschluss auf der belasteten "
                     f"Seite, nicht über eine schubstarre Fuge; die haftende Kante macht die Spannungsspitze "
                     f"am Bohrungsaustritt. Vorschlag: Reibungsbehaftet mit μ = {MU_VORSCHLAG:g}."),
            "objekte": [["kontaktbedingung", name]] + [["geokoerper_einzeln", k] for k in zk],
            "vorschlag": {"kontakt": name, "standard": "Reibungsbehaftet", "mu": MU_VORSCHLAG},
            "erledigt": ""})
    # spiel: Zylinder ohne Spiel in einer Bohrung
    kreise = _kreise_je_koerper(model)
    for name, z in zyl.items():
        r, a, p0 = z["radius"], z["achse"], z["punkt"]
        bohrung = []
        for other, liste in kreise.items():
            if other == name:
                continue
            for m_, r_, n_ in liste:
                if abs(r_ - r) > 1e-6 * r + 1e-9:
                    continue
                d = np.asarray(m_, float) - p0
                quer = d - (d @ a) * a
                if float(np.linalg.norm(quer)) <= 1e-6 * r + 1e-9 and abs(abs(np.asarray(n_, float) @ a) - 1.0) < 1e-6:
                    bohrung.append(other)
                    break
        if not bohrung:
            continue
        aus.append({
            "art": "spiel",
            "text": (f"Zylinder {name} (r = {r * 1e3:.3f} mm) sitzt ohne Spiel in seiner Bohrung in "
                     f"{', '.join(bohrung)}: Stift und Bohrung haben denselben Radius, der Stift liegt "
                     f"rechnerisch am ganzen Umfang an. Vorschlag: Spiel geben, "
                     f"{SPIEL_VORSCHLAG * 1e3:g} mm am Durchmesser (Lager / Kontakt → Spiel geben)."),
            "objekte": [["geokoerper_einzeln", name]] + [["geokoerper_einzeln", b] for b in bohrung],
            "vorschlag": {"spiel": name, "mm": SPIEL_VORSCHLAG * 1e3},
            "erledigt": ""})
    return aus


def offen(model) -> list:
    return [h for h in (getattr(model, "importhinweise", None) or []) if not h.get("erledigt")]


def kurz(h: dict) -> str:
    """Eine Zeile fuer Modellbaum und Tabelle."""
    v = h.get("vorschlag") or {}
    if h.get("art") == "reibung":
        return f"{v.get('kontakt')}: Reibung μ = {v.get('mu', MU_VORSCHLAG):g} statt Haften"
    if h.get("art") == "spiel":
        return f"{v.get('spiel')}: Spiel {v.get('mm', SPIEL_VORSCHLAG * 1e3):g} mm"
    return str(h.get("text", ""))[:60]


def anwenden(model, h: dict, log: list = None) -> dict:
    """Den Vorschlag eines Hinweises ins Modell bringen. Rueckgabe
    {"ok", "koerper": [neu zu vernetzende Koerper], "kontakte": [neu
    auszufuehrende Kontaktbedingungen], "text"}."""
    v = h.get("vorschlag") or {}
    aus = {"ok": False, "koerper": [], "kontakte": [], "text": ""}
    if h.get("art") == "reibung":
        kb = (getattr(model, "kontaktbedingungen", None) or {}).get(v.get("kontakt"))
        if kb is None:
            aus["text"] = f"Kontaktbedingung {v.get('kontakt')} gibt es nicht mehr"
            return aus
        kb.standard_anwenden(str(v.get("standard", "Reibungsbehaftet")), float(v.get("mu", MU_VORSCHLAG)))
        kb.standard = str(v.get("standard", "Reibungsbehaftet"))
        kb.automatisch = False
        aus.update({"ok": True, "kontakte": [kb.name],
                    "text": f"{kb.name}: {kb.standard} mit μ = {float(v.get('mu', MU_VORSCHLAG)):g} gesetzt"})
    elif h.get("art") == "spiel":
        from . import spiel as sp
        name = str(v.get("spiel", ""))
        erg = sp.zylinder_spiel(model, name, float(v.get("mm", SPIEL_VORSCHLAG * 1e3)) / 1e3, log)
        if not erg.get("ok"):
            aus["text"] = erg.get("grund", "")
            return aus
        kont = [n for n, kb in (getattr(model, "kontaktbedingungen", None) or {}).items()
                if name in (kb.koerpernamen or []) or name in (getattr(kb, "gegenkoerper", None) or [])]
        for n in kont:
            model.kontaktbedingungen[n].automatisch = False
        aus.update({"ok": True, "koerper": [name], "kontakte": kont,
                    "text": f"{name}: Spiel {float(v.get('mm', SPIEL_VORSCHLAG * 1e3)):g} mm gegeben, "
                            f"r = {erg['radius_neu'] * 1e3:.3f} mm"})
    else:
        aus["text"] = f"unbekannte Hinweisart {h.get('art')}"
        return aus
    h["erledigt"] = "angewendet"
    if log is not None:
        log.append("Importhinweis angewendet - " + aus["text"])
    return aus


def verwerfen(h: dict) -> None:
    h["erledigt"] = "verworfen"
