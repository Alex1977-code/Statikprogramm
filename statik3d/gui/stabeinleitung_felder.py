"""Felder der Masken fuer die Einleitung der Stabenden in Volumen (seit 13.10.2026).

Die Modelleinstellung steht in den Netzeinstellungen (ein Auswahlfeld und
die Durchmesser des Kreisrings), je Stabende in der Stabmaske - dort nur fuer
ein Ende, das in einem Volumen haengt oder eine eigene Einstellung hat, damit
die Maske eines gewoehnlichen Stabes so bleibt, wie sie war. Die Rechnung
steht in statik3d.stabeinleitung und fugen.stabenden_koppeln.
"""
from __future__ import annotations

from .. import stabeinleitung as SE
from .. import zahlen as zl
from ..model import EINLEITUNGEN, Stabeinleitung
from . import masken as msk

#: Eintrag „wie Modell“ der Stabmaske
WIE_MODELL = "wie Modell"
HINWEIS_MODELL = ("Wie ein Stabende, das auf oder in einem Volumen liegt, an dessen Netz hängt: an den "
                  "1–3 Knoten des Elements wie in RFEM – dort entsteht eine netzabhängige Spannungsspitze – "
                  "oder verteilt über die Stirnfläche bzw. einen Kreisring (RBE3 ohne Versteifung, "
                  "flächenanteilig gewichtet). Je Stabende lässt es sich in der Stabmaske umstellen; "
                  "wirksam beim nächsten Vernetzen oder Rechnen")
HINWEIS_RING = ("nur für „verteilt über einen Kreisring“: Innen- und Außendurchmesser der Auflagefläche "
                "(Scheibe, Mutter), getrennt mit „/“, etwa „17 / 30“")


def _art_aus_text(text: str, vorgabe: str = "") -> str:
    t = str(text or "")
    for art in EINLEITUNGEN:
        if t == SE.TEXTE[art]:
            return art
    return vorgabe


def ring_text(d_innen: float, d_aussen: float) -> str:
    """„17 / 30“ in mm, leer ohne Ring."""
    if not d_aussen:
        return ""
    return f"{zl.zahl_text(d_innen * 1e3)} / {zl.zahl_text(d_aussen * 1e3)}"


def ring_lesen(text: str, feld: str) -> tuple:
    """(d_innen, d_aussen) [m] aus „17 / 30“ [mm]; leer = (0, 0)."""
    t = str(text or "").strip()
    if not t:
        return 0.0, 0.0
    teile = [x.strip() for x in t.split("/")]
    if len(teile) != 2:
        raise zl.Eingabefehler(f"{feld}: zwei Durchmesser in mm, getrennt mit „/“ (etwa „17 / 30“)")
    di, da = (zl.feldwert(x, 0.0) for x in teile)
    if not 0.0 <= di < da:
        raise zl.Eingabefehler(f"{feld}: der Außendurchmesser muss größer sein als der innere (≥ 0)")
    return di / 1e3, da / 1e3


# --------------------------------------------------------------------------
# Netzeinstellungen: die Modelleinstellung
# --------------------------------------------------------------------------
def felder_netz(model) -> list:
    st = getattr(model, "stabeinleitung", None) or Stabeinleitung()
    F = msk.Feld
    return [F("stabenden", "Stabenden in Volumen", "wahl", SE.TEXTE.get(st.art, SE.TEXTE["punkt"]),
              [SE.TEXTE[a] for a in EINLEITUNGEN], hinweis=HINWEIS_MODELL),
            F("stabenden_ring", "Kreisring d innen / außen [mm]", "text",
              ring_text(st.d_innen, st.d_aussen), breite=90, hinweis=HINWEIS_RING)]


def netz_uebernehmen(model, w: dict, nur_pruefen: bool = False) -> bool:
    """Die Modelleinstellung aus der Maske; True, wenn sie sich geaendert hat.
    Wirft zl.Eingabefehler bei einem falschen Ring - ``nur_pruefen`` liest
    nur (vor dem Rueckgaengig-Schritt)."""
    if "stabenden" not in w:
        return False
    alt = getattr(model, "stabeinleitung", None) or Stabeinleitung()
    art = _art_aus_text(w.get("stabenden"), alt.art)
    di, da = ring_lesen(w.get("stabenden_ring", ""), "Kreisring")
    if art == "ring" and not da:
        raise zl.Eingabefehler("Kreisring: Innen- und Außendurchmesser angeben (etwa „17 / 30“)")
    neu = Stabeinleitung(art, di, da)
    if neu == alt or nur_pruefen:
        return neu != alt
    model.stabeinleitung = neu
    return True


def erneuern(fenster) -> None:
    """Nach dem Umstellen: die Stabenden am vorhandenen Netz neu anschliessen
    (fugen.stabenden_erneuern), ins Protokoll; die Ergebnisse passen dann
    nicht mehr."""
    from .. import fugen
    log: list = []
    if fugen.stabenden_erneuern(fenster.model, log):
        fenster.analysis = None
        fenster.results = None
    for z in log:
        fenster.log.appendPlainText(z)


# --------------------------------------------------------------------------
# Stabmaske: je Stabende
# --------------------------------------------------------------------------
def _ende_im_volumen(model, knoten: int) -> bool:
    """Haengt das Stabende an einem Volumen (starre Kopplung oder RBE3)?"""
    from ..fugen import STABENDE_GRUPPE
    g = STABENDE_GRUPPE + f"K{int(knoten)}"
    return (any(str(getattr(k, "gruppe", "")) == g and int(k.node_a) == int(knoten)
                for k in (getattr(model, "kopplungen", None) or []))
            or any(SE.ist_verteilkopplung(sk) and int(sk.master) == int(knoten)
                   for sk in (getattr(model, "starrkoerper", None) or [])))


def felder_stab(model, name: str) -> list:
    """Je Ende des Stabs, das in einem Volumen haengt oder eine eigene
    Einstellung hat, die Auswahl und der Ring."""
    mem = (getattr(model, "members", None) or {}).get(name)
    if mem is None:
        return []
    enden = {e: n for n, (s, e) in SE.staebe_an_enden(model).items() if s == name}
    st = getattr(model, "stabeinleitung", None) or Stabeinleitung()
    F = msk.Feld
    aus = []
    for ende, wort in (("A", "Anfang"), ("E", "Ende")):
        n = enden.get(ende)
        eigen = (getattr(mem, "einleitung", None) or {}).get(ende) or {}
        if n is None or not (eigen or _ende_im_volumen(model, n)):
            continue
        wie = f"{WIE_MODELL} ({SE.TEXTE.get(st.art, st.art)})"
        wahl = SE.TEXTE.get(str(eigen.get("art", "")), wie)
        aus.append(F(f"einleitung_{ende}", f"Volumen am {wort} (K{n})", "wahl", wahl,
                     [wie] + [SE.TEXTE[a] for a in EINLEITUNGEN],
                     hinweis="Wie dieses Stabende in das Volumen geht – geht der Modelleinstellung "
                             "(Netzeinstellungen) vor. " + HINWEIS_MODELL))
        aus.append(F(f"ring_{ende}", f"Kreisring {wort} d innen / außen [mm]", "text",
                     ring_text(float(eigen.get("d_innen", 0.0) or 0.0), float(eigen.get("d_aussen", 0.0) or 0.0)),
                     breite=90, hinweis=HINWEIS_RING + "; leer = der Ring der Modelleinstellung"))
    return aus


def stab_pruefen(w: dict) -> None:
    """Die Ringe der Stabmaske lesen, ohne etwas zu setzen (wirft
    zl.Eingabefehler) - vor dem Rueckgaengig-Schritt."""
    for ende, wort in (("A", "Anfang"), ("E", "Ende")):
        if f"ring_{ende}" in w:
            ring_lesen(w.get(f"ring_{ende}", ""), f"Kreisring {wort}")


def stab_uebernehmen(model, name: str, w: dict) -> bool:
    """Die Einstellung je Stabende aus der Maske; True, wenn sie sich
    geaendert hat. Wirft zl.Eingabefehler bei einem falschen Ring."""
    mem = (getattr(model, "members", None) or {}).get(name)
    if mem is None:
        return False
    neu = dict(getattr(mem, "einleitung", None) or {})
    for ende, wort in (("A", "Anfang"), ("E", "Ende")):
        if f"einleitung_{ende}" not in w:
            continue
        art = _art_aus_text(w.get(f"einleitung_{ende}"), "")
        di, da = ring_lesen(w.get(f"ring_{ende}", ""), f"Kreisring {wort}")
        if not art:
            neu.pop(ende, None)
            continue
        e = {"art": art}
        if art == "ring" and da:
            e.update(d_innen=di, d_aussen=da)
        neu[ende] = e
    if neu == (getattr(mem, "einleitung", None) or {}):
        return False
    mem.einleitung = neu
    return True
