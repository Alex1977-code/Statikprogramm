"""
Hinweis zur Schraubenguete beim Import (Entscheidung des Anwenders vom
13.10.2026: „hinweis beim import“ - gemeldet wird, umgestellt wird nichts).

Am Drehlager sind die Schrauben als Zugstab (Rund 16/20, S17-S64) mit einem
Schraubenkoerper (V37-V60, V65-V70, V80-V91, V96-V101) modelliert, beide aus
„Nullmaterial“, einem gewichtslosen Hilfswerkstoff mit f_y 355 N/mm². Ist eine
Schraube 8.8 oder 10.9 gemeint, rechnet das Modell mit der falschen
Streckgrenze - das soll beim Import auffallen.

Die Erkennungsregel:

* **Stab**: Querschnitt rund (Kreis) mit d <= 36 mm - M36 ist die groesste
  Schraube der Tabellen von EN 1993-1-8 und EN ISO 898-1 (joints.bolts.SIZES);
  die Ankerstaebe Rund 40 fallen damit heraus -, und mindestens ein Knoten
  des Stabes haengt an einem Volumen: er ist in eine Randflaeche des
  Volumens integriert (RFEM: integrierter Knoten, am Drehlager das Stabende
  auf der Stirnflaeche des Schraubenkoerpers) oder liegt auf ihren
  Randlinien.
* **Schraubenkoerper**: ein Volumen, an dem ein solcher Stab haengt und das
  quer zur Stabachse in einen Kreis von 36 mm passt (1 mm Toleranz fuer ein
  Stabende, das nicht genau in der Mitte der Stirnflaeche sitzt; am Drehlager
  bis 0,26 mm). Eine Platte, ein Deckel oder ein Lagerbock, an dem ein Stab
  haengt, ist breiter und zaehlt nicht; ein Passstift ohne Stab auch nicht -
  ob ein Zylinder Schraube oder Stift ist, sagt das Modell sonst nicht
  (18.09.2026).
* Gemeldet wird ein Stab bzw. Koerper, dessen Werkstoff 0 < f_y < 640 N/mm²
  hat: 640 ist f_yb der Festigkeitsklasse 8.8 (EN 1993-1-8, Tab. 3.1), der
  kleinsten, die vorgespannt werden darf. Ein Werkstoff ohne f_y bleibt
  ungenannt (er ist kein Stahl, oder f_y fehlt - das meldet der Nachweis).
"""
from __future__ import annotations

import re

import numpy as np

from ..zahlen import zahl_text

#: groesster Durchmesser einer Schraube [m] (M36)
D_MAX = 0.036
#: Toleranz fuer den Durchmesser des Schraubenkoerpers quer zur Stabachse [m]
TOL_KOERPER = 1e-3
#: f_yb der Festigkeitsklasse 8.8 [Pa]
FYB_MIN = 640e6

PRAEFIX = "Schraubengüte prüfen"


def _durchmesser(sec) -> float:
    """Durchmesser eines runden Vollquerschnitts [m], sonst 0."""
    if sec is None or getattr(sec, "typ", "") != "circle":
        return 0.0
    d = float(getattr(sec, "h", 0.0) or getattr(sec, "b", 0.0) or 0.0)
    if d <= 0 and float(getattr(sec, "A", 0.0) or 0.0) > 0:
        d = float(np.sqrt(4.0 * sec.A / np.pi))
    return d


def _koerper_je_knoten(model) -> dict:
    """{Knoten: {Koerper}} fuer die Knoten, die in eine Randflaeche eines
    Koerpers integriert sind oder auf ihren Randlinien liegen."""
    flaeche_koerper: dict = {}
    for kn, k in (getattr(model, "koerper", None) or {}).items():
        for f in k.flaechen:
            flaeche_koerper.setdefault(f, set()).add(kn)
    out: dict = {}
    for fn, koerper in flaeche_koerper.items():
        f = model.flaechen.get(fn)
        if f is None:
            continue
        knoten = {int(x) for x in (getattr(f, "integrierte_knoten", None) or [])}
        for ln in f.linien:
            line = model.lines.get(ln)
            if line is not None:
                knoten.update(int(x) for x in line.nodes)
        for x in knoten:
            out.setdefault(x, set()).update(koerper)
    return out


def _koerperdurchmesser(model, koerper, achse) -> float:
    """Durchmesser des kleinsten Kreises um den Mittelpunkt der Randpunkte
    des Koerpers, quer zur Achse [m] (Randlinien mit ihren Boegen abgetastet)."""
    teile = []
    for fn in koerper.flaechen:
        f = model.flaechen.get(fn)
        if f is not None:
            P = np.asarray(f.randpunkte(model, 16), float)
            if P.ndim == 2 and len(P):
                teile.append(P)
    if not teile:
        return float("inf")
    P = np.vstack(teile)
    a = np.asarray(achse, float)
    hilf = np.eye(3)[int(np.argmin(np.abs(a)))]
    u = np.cross(a, hilf)
    u /= np.linalg.norm(u)
    v = np.cross(a, u)
    Q = np.column_stack([P @ u, P @ v])
    mitte = 0.5 * (Q.min(axis=0) + Q.max(axis=0))
    return 2.0 * float(np.linalg.norm(Q - mitte, axis=1).max())


def _querschnitte_text(namen) -> str:
    """„Rund 16/20“ aus „Rund 16“ und „Rund 20“; sonst die Namen. Der Zusatz
    „_2“, mit dem der Import gleichnamige Querschnitte unterscheidet, faellt
    weg (Drehlager mit Kopfbolzen: „Rund 20“ und „Rund 20_2“)."""
    namen = sorted({re.sub(r"_\d+$", "", str(n)) for n in namen})
    teile = [re.match(r"^(.*?)(\d+(?:[.,]\d+)?)\s*$", n) for n in namen]
    if len(namen) > 1 and all(teile) and len({t.group(1) for t in teile}) == 1:
        zahlen = sorted((t.group(2) for t in teile), key=lambda z: float(z.replace(",", ".")))
        return teile[0].group(1) + "/".join(zahlen)
    return ", ".join(namen)


def _bereiche(namen) -> str:
    """„S17–S64“, „V37–V60, V65–V70“: aufeinanderfolgende Nummern als Bereich."""
    gruppen: dict = {}
    rest = []
    for n in namen:
        m = re.match(r"^(\D*)(\d+)$", str(n))
        if m:
            gruppen.setdefault(m.group(1), []).append(int(m.group(2)))
        else:
            rest.append(str(n))
    out = []
    for vor, zahlen in sorted(gruppen.items()):
        zahlen = sorted(set(zahlen))
        a = b = zahlen[0]
        for z in zahlen[1:] + [None]:
            if z is not None and z == b + 1:
                b = z
                continue
            out.append(f"{vor}{a}" if a == b else f"{vor}{a}–{vor}{b}")
            if z is not None:
                a = b = z
    return ", ".join(out + sorted(rest))


def _mehrzahl(art: str, n: int) -> str:
    formen = {"Zugstab": "Zugstäbe", "Fachwerkstab": "Fachwerkstäbe", "Stab": "Stäbe", "Seil": "Seile",
              "Balken": "Balken"}
    return art if n == 1 else formen.get(art, "Stäbe")


def schraubenhinweis(model, stabarten: dict = None) -> str:
    """Der gebuendelte Hinweis zur Schraubenguete - "" ohne Befund.

    ``stabarten``: {Stabname: Stabtyp im Klartext} aus der Quelldatei
    („Zugstab“); ohne Angabe heissen sie „Stäbe“."""
    if not (getattr(model, "members", None) and getattr(model, "koerper", None)):
        return ""
    an_knoten = _koerper_je_knoten(model)
    if not an_knoten:
        return ""
    X = np.asarray(model.nodes, float)
    staebe: dict = {}          # Werkstoff -> [(Stab, Querschnitt, Art)]
    koerper_d: dict = {}       # Schraubenkoerper -> Durchmesser quer zur Stabachse [m]
    fy_text: dict = {}
    for mn, mem in model.members.items():
        if not mem.elements:
            continue
        e0 = model.elements[int(mem.elements[0])]
        e1 = model.elements[int(mem.elements[-1])]
        sec = model.sections.get(getattr(e0, "sec", ""))
        d = _durchmesser(sec)
        if not (0.0 < d <= D_MAX + 1e-9):
            continue
        knoten = {int(x) for i in mem.elements for x in model.elements[int(i)].nodes}
        haengt = set()
        for x in knoten:
            haengt |= an_knoten.get(x, set())
        if not haengt:
            continue
        a, b = int(e0.nodes[0]), int(e1.nodes[-1])
        achse = X[b] - X[a]
        L = float(np.linalg.norm(achse))
        if L > 0:
            achse = achse / L
            for kn in haengt:
                dk = _koerperdurchmesser(model, model.koerper[kn], achse)
                if dk <= D_MAX + TOL_KOERPER:
                    koerper_d[kn] = min(dk, koerper_d.get(kn, dk))
        mat = model.materials.get(getattr(e0, "mat", ""))
        fy = float(mat.yield_strength(d) or 0.0) if mat is not None else 0.0
        if 0.0 < fy < FYB_MIN:
            staebe.setdefault(mat.name, []).append((mn, sec.name, (stabarten or {}).get(mn, "Stab")))
            fy_text[mat.name] = fy
    koerper: dict = {}         # Werkstoff -> [Koerper]
    for kn in sorted(koerper_d):
        mat = model.materials.get(getattr(model.koerper[kn], "material", ""))
        fy = float(mat.yield_strength(koerper_d[kn]) or 0.0) if mat is not None else 0.0
        if 0.0 < fy < FYB_MIN:
            koerper.setdefault(mat.name, []).append(kn)
            fy_text.setdefault(mat.name, fy)
    if not staebe and not koerper:
        return ""
    teile = []
    for wn in sorted(set(staebe) | set(koerper)):
        st, ko = staebe.get(wn, []), koerper.get(wn, [])
        was = []
        if st:
            arten = {a for _s, _q, a in st}
            art = arten.pop() if len(arten) == 1 else "Stab"
            was.append(f"{len(st)} {_mehrzahl(art, len(st))} ({_querschnitte_text(q for _s, q, _a in st)})")
        if ko:
            was.append(f"{len(ko)} Schraubenkörper")
        teile.append(" und ".join(was) + f" aus „{wn}“ (f_y {zahl_text(fy_text[wn] / 1e6)} N/mm²)")
    alle_staebe = [s for v in staebe.values() for s, _q, _a in v]
    alle_koerper = [k for v in koerper.values() for k in v]
    betroffen = []
    if alle_staebe:
        betroffen.append("Stäbe " + _bereiche(alle_staebe))
    if alle_koerper:
        betroffen.append("Volumen " + _bereiche(alle_koerper))
    return (f"{PRAEFIX}: " + "; ".join(teile) + ". Falls Schrauben z. B. 8.8 (f_yb 640 N/mm²) oder "
            "10.9 (f_yb 900 N/mm²) gemeint sind, bitte den Werkstoff im Modell anpassen; umgestellt "
            "wurde nichts. Betroffen: " + "; ".join(betroffen) + ".")
