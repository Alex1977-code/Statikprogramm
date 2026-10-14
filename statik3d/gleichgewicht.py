"""Globale Gleichgewichtskontrolle nach jeder Rechnung (seit 14.10.2026).

Entscheidung des Anwenders vom 14.10.2026: nach jedem Lauf die Summe der
Kraefte und die Summe der Momente der Lasten und der Lagerkraefte ueber einen
festen Bezugspunkt ausgeben, mit Warnung bei Abweichung.

Bis dahin stand in der Zusammenfassung nur die Summe der Lagerkraefte, und der
Kontaktlauf pruefte beim Abschluss nur die Kraefte (solver.ABSCHLUSS_GLEICHGEWICHT).
Das Moment prueft niemand - und genau dort fiel die Kopplung versetzter Knoten
nur ueber ihre Verschiebungen auf (Befund b3): Ihre Kraefte haben die Summe
null, aber ein Moment. Am Drehlager (LF1, Netz Mittel, 09.10.2026) trugen die
Kopplungen zusammen 14,7 kNm, die keinem Teil des Modells das Gleichgewicht
hielten; die Kraftbilanz stimmte auf 2,5e-7.

**Was gerechnet wird.** Die Lasten sind der Lastvektor F der Rechnung (Knoten-
und Elementlasten, Temperatur, Eigengewicht - so, wie sie in die Gleichung
gehen), die Lagerkraefte die Reaktionen R des Ergebnisses (starre Lager,
Federlager, einseitige Lager, gesperrte FHG). An einem objektiven Modell gilt
fuer jede Starrkoerperbewegung Phi: Phi^T (F + R) = Phi^T K u = 0. Also

    Summe F_i + Summe R_i = 0,
    Summe (x_i - x0) x (F_i + R_i) + (M_i + M_R,i) = 0

ueber die Knoten, x0 = Mitte der Huelle aller Knoten (fester Bezugspunkt).
Zusatzfreiheitsgrade (Woelbung, Ordnung p) arbeiten unter einer
Starrkoerperbewegung nicht mit und zaehlen nicht.

**Schranke.** Die Abweichung wird bezogen auf den Umsatz: Summe der Betraege
aller Knotenlasten und Lagerkraefte (Kraft) bzw. ihrer Momente um x0
(Moment). Sie muss unter :data:`SCHRANKE` = 1e-4 bleiben, demselben Wert, mit
dem der Kontaktlauf beim Abschluss das Kraftgleichgewicht annimmt
(solver.ABSCHLUSS_GLEICHGEWICHT). Der Gleichungsloeser haelt das Residuum
unter 1e-6 ||F||, die Newton-Iteration der Plastizitaet und der
Kontaktlauf enden darueber; eine nicht objektive Kopplung dagegen fehlt um
ihre ganze Momentensumme (Befund b3: 24,7 von 30 kNm, Drehlager rund 1e-3 des
Momentenumsatzes). Ein Ergebnis aus Theorie II. Ordnung haelt das
Gleichgewicht am verformten System; dort zaehlen die Hebel x + u.
"""
from __future__ import annotations

import numpy as np

#: bezogene Abweichung, ab der gewarnt wird (siehe Modultext)
SCHRANKE = 1.0e-4
#: bezogene Abweichung, ab der das Ergebnis nicht gueltig ist (Entscheidung vom
#: 14.10.2026; solver.gueltigkeit). Warum 1e-2: Was richtig gerechnet ist, liegt
#: bei 1e-6 (Gleichungsloeser) bis 1e-4 (Abschluss des Kontaktlaufs, nicht ganz
#: auskonvergierte Newton-Iteration; Platte mit Reibkontakt und ausfallender
#: Strebe 8,5e-7). Eine nicht objektive Kopplung fehlt um ihre Momentensumme,
#: am Drehlager rund 1e-3 des Momentenumsatzes (Befund b3) - ein Modellmangel,
#: der gewarnt, aber nicht verworfen wird. 1e-2 liegt einen Faktor 10 darueber
#: und 100 ueber der Warnung: so viel fehlt nur, wenn Last ueberhaupt keinen
#: Weg in die Lager hat (am Zugstab „nur Zug“ unter Druck mit Last am freien
#: Kopf 1,0). Darunter bleibt es bei der Warnung.
UNGUELTIG = 1.0e-2


def _knotenteil(v, nn: int) -> np.ndarray:
    v = np.asarray(v, float).reshape(-1)
    n6 = nn * 6
    aus = np.zeros(n6)
    k = min(n6, len(v))
    aus[:k] = v[:k]
    return aus.reshape(-1, 6)


def pruefen(model, res, F, verformt: bool = False) -> dict:
    """Gleichgewicht der Lasten ``F`` (Lastvektor der Rechnung) und der
    Reaktionen ``res.reactions`` um die Mitte der Knotenhuelle. Rueckgabe -
    nur Zahlen und Listen, das Ergebnis wird gespeichert:
    {"x0", "F_last", "M_last", "F_lager", "M_lager", "dF", "dM", "umsatz_F",
    "umsatz_M", "rel_F", "rel_M", "schranke", "ok"}."""
    nn = int(model.nn)
    R = getattr(res, "reactions", None)
    if not nn or R is None or F is None:
        return {}
    X = np.asarray(model.nodes, float)[:nn]
    if verformt and getattr(res, "u", None) is not None:
        X = X + np.asarray(res.u, float).reshape(-1, 6)[:nn, :3]
    x0 = 0.5 * (X.min(axis=0) + X.max(axis=0))
    d = X - x0
    Fk = _knotenteil(F, nn)
    Rk = _knotenteil(R, nn)
    mF = np.cross(d, Fk[:, :3]) + Fk[:, 3:]
    mR = np.cross(d, Rk[:, :3]) + Rk[:, 3:]
    aus = {"x0": [float(x) for x in x0],
           "F_last": [float(x) for x in Fk[:, :3].sum(axis=0)],
           "M_last": [float(x) for x in mF.sum(axis=0)],
           "F_lager": [float(x) for x in Rk[:, :3].sum(axis=0)],
           "M_lager": [float(x) for x in mR.sum(axis=0)],
           "umsatz_F": float(np.linalg.norm(Fk[:, :3], axis=1).sum() + np.linalg.norm(Rk[:, :3], axis=1).sum()),
           "umsatz_M": float(np.linalg.norm(mF, axis=1).sum() + np.linalg.norm(mR, axis=1).sum()),
           "verformt": bool(verformt)}
    return bewerten(aus)


def bewerten(aus: dict) -> dict:
    """dF, dM, bezogene Werte und Urteil aus den Summen eines Eintrags."""
    dF = float(np.linalg.norm(np.add(aus["F_last"], aus["F_lager"])))
    dM = float(np.linalg.norm(np.add(aus["M_last"], aus["M_lager"])))
    uF, uM = float(aus.get("umsatz_F", 0.0)), float(aus.get("umsatz_M", 0.0))
    rel_F = dF / uF if uF > 0 else 0.0
    rel_M = dM / uM if uM > 0 else 0.0
    aus.update({"dF": dF, "dM": dM, "rel_F": rel_F, "rel_M": rel_M, "schranke": SCHRANKE,
                "ok": bool(rel_F <= SCHRANKE and rel_M <= SCHRANKE),
                "verletzt": bool(rel_F >= UNGUELTIG or rel_M >= UNGUELTIG)})
    return aus


def verletzt_text(g: dict) -> str:
    """„Gleichgewicht verletzt: ΣF 10,000 kN (bezogen 1), ΣM … – …“ oder "",
    wenn die Abweichung unter :data:`UNGUELTIG` liegt (auch fuer Eintraege von
    vor dem 14.10.2026 ohne das Feld ``verletzt``)."""
    if not g:
        return ""
    if not (g.get("verletzt") or float(g.get("rel_F", 0.0)) >= UNGUELTIG
            or float(g.get("rel_M", 0.0)) >= UNGUELTIG):
        return ""
    return (f"Gleichgewicht verletzt: ΣF {_z(g['dF'] / 1e3)} kN (bezogen {_rel(g['rel_F'])}), "
            f"ΣM {_z(g['dM'] / 1e3)} kNm (bezogen {_rel(g['rel_M'])}) – Lasten und Lagerkräfte "
            f"weichen um mindestens {_rel(UNGUELTIG)} des Umsatzes voneinander ab, ein Teil der "
            "Last hat keinen Weg in die Lager")


def ueberlagern(teile) -> dict:
    """Die Kontrolle einer linearen Ueberlagerung [(Results, Faktor)]: die
    Summen addieren sich mit den Faktoren, der Umsatz mit ihren Betraegen
    (eine obere Schranke). Leer, wenn ein Anteil sie nicht hat."""
    aus = None
    for r, f in teile:
        if not f:
            continue
        g = (getattr(r, "info", None) or {}).get("gleichgewicht_global")
        if not g:
            return {}
        if aus is None:
            aus = {"x0": list(g["x0"]), "F_last": [0.0] * 3, "M_last": [0.0] * 3, "F_lager": [0.0] * 3,
                   "M_lager": [0.0] * 3, "umsatz_F": 0.0, "umsatz_M": 0.0, "verformt": False}
        elif not np.allclose(aus["x0"], g["x0"]):
            return {}
        for k in ("F_last", "M_last", "F_lager", "M_lager"):
            aus[k] = [float(a + f * b) for a, b in zip(aus[k], g[k])]
        aus["umsatz_F"] += abs(f) * float(g["umsatz_F"])
        aus["umsatz_M"] += abs(f) * float(g["umsatz_M"])
    return bewerten(aus) if aus else {}


def _z(x: float, nk: int = 3) -> str:
    """Zahl mit Komma, nie wissenschaftlich."""
    return f"{x:,.{nk}f}".replace(",", " ").replace(".", ",")


def _rel(x: float) -> str:
    """Bezogene Abweichung lesbar: als Bruchteil mit genug Stellen."""
    if x == 0:
        return "0"
    stellen = max(1, min(12, int(-np.floor(np.log10(abs(x)))) + 1))
    return _z(x, stellen)


def zeile(g: dict) -> str:
    """Die Zeile der Zusammenfassung eines Ergebnisses."""
    if not g:
        return ""
    kopf = "Gleichgewicht global    : "
    text = (f"Lasten + Lager ΣF {_z(g['dF'] / 1e3)} kN (bezogen {_rel(g['rel_F'])}), "
            f"ΣM {_z(g['dM'] / 1e3)} kNm (bezogen {_rel(g['rel_M'])}) um "
            f"({_z(g['x0'][0])}; {_z(g['x0'][1])}; {_z(g['x0'][2])}) m"
            + (", am verformten System" if g.get("verformt") else ""))
    if g.get("ok"):
        return kopf + "erfüllt – " + text
    if verletzt_text(g):
        return (kopf + "NICHT GÜLTIG – " + text + f"; ab {_rel(UNGUELTIG)} des Umsatzes ist das "
                "Ergebnis nicht gültig: ein Teil der Last hat keinen Weg in die Lager")
    return (kopf + "WARNUNG – " + text + f"; Schranke {_rel(g['schranke'])} des Umsatzes überschritten: "
            "Lasten und Lagerkräfte sind nicht im Gleichgewicht (eine Kopplung oder Feder ohne "
            "Starrkörperbewegung, ein nicht auskonvergierter Lauf?)")


def gebuendelt(ergebnisse) -> list:
    """Eine Zeile ueber alle Ergebnisse [(Name, Results)] fuer die
    Zusammenfassung der Analyse: alle erfuellt, oder die Warnung mit Namen."""
    geprueft, schlecht = 0, []
    groesst = 0.0
    for name, r in ergebnisse:
        g = (getattr(r, "info", None) or {}).get("gleichgewicht_global")
        if not g:
            continue
        geprueft += 1
        groesst = max(groesst, float(g.get("rel_F", 0.0)), float(g.get("rel_M", 0.0)))
        if not g.get("ok"):
            schlecht.append((name, g))
    if not geprueft:
        return []
    ungueltig = [(n, g) for n, g in schlecht if verletzt_text(g)]
    vorne = []
    if ungueltig:
        vorne = [f"NICHT GÜLTIG: Gleichgewicht verletzt in {len(ungueltig)} von {geprueft} Ergebnissen: "
                 + "; ".join(f"{n} (ΣF {_z(g['dF'] / 1e3)} kN, ΣM {_z(g['dM'] / 1e3)} kNm)"
                             for n, g in ungueltig[:6]) + (" …" if len(ungueltig) > 6 else "")
                 + f" – ab {_rel(UNGUELTIG)} des Umsatzes"]
        schlecht = [(n, g) for n, g in schlecht if not verletzt_text(g)]
        if not schlecht:
            return vorne
    if not schlecht:
        return [f"Gleichgewicht global: {geprueft} Ergebnisse geprüft, Lasten und Lagerkräfte im "
                f"Gleichgewicht (ΣF und ΣM, größte bezogene Abweichung {_rel(groesst)}, Schranke "
                f"{_rel(SCHRANKE)})"]
    teile = [f"{n} (ΣF {_z(g['dF'] / 1e3)} kN, ΣM {_z(g['dM'] / 1e3)} kNm)" for n, g in schlecht[:6]]
    return vorne + [f"WARNUNG: Gleichgewicht global verletzt in {len(schlecht)} von {geprueft} Ergebnissen: "
            + "; ".join(teile) + (" …" if len(schlecht) > 6 else "")
            + f" – über der Schranke {_rel(SCHRANKE)} des Umsatzes"]


def bericht_saetze(ergebnisse) -> list:
    """Saetze fuer den Bericht (Kapitel Ergebnisse, Uebersicht)."""
    z = gebuendelt(ergebnisse)
    if not z:
        return []
    text = z[0]
    if text.startswith("WARNUNG: "):
        return [("note", "Globale Gleichgewichtskontrolle: " + text[len("WARNUNG: "):] + ".")]
    return [("note", "Globale Gleichgewichtskontrolle: " + text[len("Gleichgewicht global: "):]
             + ". Geprüft werden die Summe der Kräfte und die Summe der Momente aller Lasten und "
               "Lagerkräfte um die Mitte des Modells.")]
