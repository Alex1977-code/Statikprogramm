"""
Kur der Pruefagenten-Befunde 12, 14, 27, 28, 29, 30 und 37 (11.11.2026):
Meldungen aus den Commits 6341224 (Gruppe 5 Meldungen, C2 bis C9), 7574d33
(Gruppe 5 Robustheit) und 8fdbe13 (A19). Geaendert ist nur, was gemeldet
wird - kein Rechenergebnis.

12 A19: Abnahme „Flächen ohne gemeinsame Linie“ und Protokoll des Vernetzers
   nennen den Knoten ab 0 wie Tabelle und Modellbaum (C13). Fläche A
   (0..1 × 0..1), Fläche B (1..2 × 0..0,5): die Ecke (1; 0,5) von B ist
   Knoten 6; vorher stand „Knoten 7“. Zweiter Weg: die Koordinaten des
   genannten Knotens.
14 Flächenlager mit Elementen ausserhalb des Netzes: „nennt 1 Element, das
   es nicht gibt“ (vorher „…, die es nicht gibt“), bei zweien „die“.
27 C4: Der Merker an Kontaktbedingung.verbindung haengt an den Seiten der
   Bedingung und am Netz: nach dem Umstellen von Koerper C (frei, 0
   gemeinsame Knoten) auf Koerper O (gemeinsame Flaeche mit A, 25 = 5 · 5)
   stehen 25 da, auch nach neuem Vernetzen (vorher 0, „zu weich“).
28 C4: Ein Balken auf der Oberseite des geloesten Koerpers verbindet die
   Fuge nicht: weiter 0 gemeinsame Knoten, „zu weich“ (vorher 1, „zu steif“).
29 C9: Ein entartetes Stabelement (Laenge 1e-13 m), das die Rechnung
   uebergeht, zaehlt beim Steifigkeitsunterschied nicht mit (vorher Faktor
   10 000 000 000 000); ein echter Unterschied von 1 000 000 bleibt sichtbar.
30 C5: „Stäbe werden elastisch gerechnet (4 Stabelemente)“ (vorher „4 Stäbe“
   fuer einen Stab aus vier Elementen).
37 C4: Eigene Trennflaechen ueber denselben Randlinien (Netz einer alten
   Datei, TRENNFLAECHEN_ZUSAMMENLEGEN aus): die Seiten teilen nur die 16
   Randknoten, die Flaeche dazwischen ist offen - „nur an einzelnen Knoten
   verbunden (zu weich)“ statt „durchverbunden … (zu steif)“. Zweiter Weg:
   die Rechnung, u_z oben 0,14536 mm gegen 0,09524 mm des durchgehenden
   Blocks (53 % weicher). Gegenprobe: mit gemeinsamer Flaeche bleibt es
   „zu steif“ und u_z gleich dem Block.

Aufruf:  python -m tests.test_kur_meldungen
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")

import numpy as np  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {detail}")
    return ok


def versuch(name, fn):
    """Eine Ausnahme am alten Stand zaehlt als FAIL, die Zaehlung bleibt gleich."""
    try:
        ok, detail = fn()
    except Exception as ex:                # noqa: BLE001
        ok, detail = False, f"{type(ex).__name__}: {ex}"[:200]
    return check(name, ok, detail)


def _still(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


# --------------------------------------------------------------------------
# 12 A19-Meldungen: Knotennummer ab 0
# --------------------------------------------------------------------------
def _zwei_flaechen():
    from statik3d.model import Model, Material, ShellProp
    m = Model("S")
    m.add_material(Material("S235", 210e9, 0.3, 7850, fy=235e6, fu=360e6))
    m.add_shell_prop(ShellProp("t12", 0.012))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0], [2, 0.5, 0], [1, 0.5, 0.]]))
    for n, (a, b) in {"a0": (0, 1), "a1": (1, 2), "a2": (2, 3), "a3": (3, 0),
                      "b0": (1, 4), "b1": (4, 5), "b2": (5, 6), "b3": (6, 1)}.items():
        m.add_line(n, [a, b])
    m.add_flaeche("A", ["a0", "a1", "a2", "a3"], material="S235", dicke="t12")
    m.add_flaeche("B", ["b0", "b1", "b2", "b3"], material="S235", dicke="t12")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = 0.25
    return m


def test_12():
    import re
    from statik3d import mesher, diagnose
    ecke = np.array([1.0, 0.5, 0.0])
    # Abnahme an einem Netz wie frueher: jede Flaeche fuer sich
    m = _zwei_flaechen()
    for f in m.flaechen.values():
        _still(mesher.mesh_flaeche, m, f, [], kanten={})
    ab = [b.text for b in diagnose._abnahme_schalen_ohne_linie(m)]
    nr = [int(x) for t in ab for x in re.findall(r"Knoten (\d+) von B", t)]
    check("12 Abnahme „Knoten 6 von B liegt auf der Linie a1 von A“ (ab 0; vorher Knoten 7)",
          nr == [6] and np.allclose(m.nodes[6], ecke),
          f"genannt {nr}, Knoten 6 = {m.nodes[6].tolist()}; " + (ab[0][:90] if ab else "keine Warnung"))
    # Protokoll des Vernetzers
    m = _zwei_flaechen()
    log = []
    _still(mesher.modell_vernetzen, m, log, workers=1)
    z = [str(x) for x in log if "Knoten auf Linie" in str(x) and "Linie a1" in str(x)]
    nr = [int(x) for t in z for x in re.findall(r"am Knoten (\d+) geteilt", t)]
    check("12 Vernetzer „Linie a1 (Fläche A) im Netz am Knoten 6 geteilt“ (vorher Knoten 7)",
          nr == [6] and np.allclose(m.nodes[nr[0]] if nr else np.nan, ecke),
          f"genannt {nr}; " + (z[0][:100] if z else "keine Zeile"))


# --------------------------------------------------------------------------
# 14 Flaechenlager mit Elementen ausserhalb des Netzes
# --------------------------------------------------------------------------
def test_14():
    from tests.test_gruppe5_robustheit import bettung, rechts_von, betten, fehler
    m = bettung()
    ne = len(m.elements)
    ss = betten(m, rechts_von(m) + [ne + 3])
    z1 = fehler(m, "Bettung", "es nicht gibt")
    ss.elements = rechts_von(m) + [ne + 3, ne + 4]
    z2 = fehler(m, "Bettung", "es nicht gibt")
    check("14 ein Element: „nennt 1 Element, das es nicht gibt (Element 11)“",
          len(z1) == 1 and f"nennt 1 Element, das es nicht gibt (Element {ne + 3})" in z1[0],
          z1[0][:110] if z1 else "keine Meldung")
    check("14 zwei Elemente: „nennt 2 Elemente, die es nicht gibt“",
          len(z2) == 1 and "nennt 2 Elemente, die es nicht gibt" in z2[0],
          z2[0][:110] if z2 else "keine Meldung")


# --------------------------------------------------------------------------
# 27/28 C4: Merker und Gegenseite
# --------------------------------------------------------------------------
def test_27():
    from tests import test_gruppe5_meldungen as G
    from statik3d import fugen, mesher
    m = G._c4_modell(True)
    G._quader(m, "C", 1.0, 1.2, 0, 0.2, 0, 0.1)
    kb = m.add_kontaktbedingung("F", koerpernamen=["C"])
    kb.standard_anwenden("Reibungsfrei")
    _still(mesher.modell_vernetzen, m, [], workers=1)
    v0, z0 = kb.verbindung(m), kb.zustand(m)
    kb.koerpernamen = ["O"]
    v1, z1, frisch = kb.verbindung(m), kb.zustand(m), fugen.verbindung_ohne_fuge(m, kb)
    check("27 Bedingung von C auf O umgestellt: 25 gemeinsame Knoten (= 5 · 5), „zu steif“ (vorher 0)",
          v0 == 0 and "zu weich" in z0 and v1 == 25 == frisch == 5 * 5 and z1 == "nicht ausgeführt - hier zu steif",
          f"C: {v0} „{z0}“; O: {v1} (frisch gezählt {frisch}) „{z1}“")
    log = []
    _still(mesher.modell_vernetzen, m, log, workers=1)
    warn = [z for z in log if "„F“" in z and "nicht ausgeführt" in z]
    v2 = kb.verbindung(m)
    check("27 neues Netz derselben Geometrie: Warnung „teilen im Netz 25 Knoten … (zu steif)“",
          v2 == 25 == fugen.verbindung_ohne_fuge(m, kb) and len(warn) == 1
          and "teilen im Netz 25 Knoten" in warn[0] and "(zu steif)" in warn[0],
          f"verbindung {v2}; " + (warn[0].strip()[-120:] if warn else "keine Warnung"))
    # dieselbe Bedingung, das Netz geaendert (neue Elemente bei gleicher Zahl)
    from statik3d.model import Element
    for i, e in enumerate(list(m.elements)):
        m.elements[i] = Element(**{k: getattr(e, k) for k in e.__dataclass_fields__})
    for e in m.elements:
        if str(getattr(e, "group", "")) == "A":
            e.group = "A2"            # A ist kein Koerper mehr: niemand teilt mit O
    v3 = kb.verbindung(m)
    check("27 neues Netz mit gleicher Element- und Knotenzahl wird neu gezählt",
          v3 == 0 == fugen.verbindung_ohne_fuge(m, kb), f"verbindung {v3}")


def test_28():
    from tests import test_gruppe5_meldungen as G
    from statik3d import fugen
    from statik3d.model import Section
    m, kb, _warn, _gem = G._c4_lauf(False)
    v0 = kb.verbindung(m)
    top = int(np.argmax(m.nodes[:, 2]))
    n2 = m.add_node(*(m.nodes[top] + [0, 0, 0.5]))
    sec = Section.i_profile("HEA200", 0.190, 0.200, 0.0065, 0.010)
    m.add_section(sec)
    m.add_element("beam", [top, n2], "S235", "HEA200")
    v1, z1, folge = kb.verbindung(m), kb.zustand(m), fugen.folge_ohne_fuge(m, kb)
    check("28 Balken auf der Oberseite von O: weiter 0 gemeinsame Knoten, „zu weich“ (vorher 1, zu steif)",
          v0 == 0 == v1 and z1 == "nicht ausgeführt - hier ohne Verbindung (zu weich)"
          and "(zu weich)" in folge and "zu steif" not in folge,
          f"vorher {v0}, mit Balken {v1}: „{z1}“")
    # Gegenprobe: an der gemeinsamen Flaeche bleibt es „zu steif“, auch mit Balken
    m, kb, _warn, _gem = G._c4_lauf(True)
    top = int(np.argmax(m.nodes[:, 2]))
    n2 = m.add_node(*(m.nodes[top] + [0, 0, 0.5]))
    m.add_section(sec)
    m.add_element("beam", [top, n2], "S235", "HEA200")
    check("28 Gegenprobe gemeinsame Fläche mit Balken: 25 gemeinsame Knoten, „zu steif“",
          kb.verbindung(m) == 25 and kb.zustand(m) == "nicht ausgeführt - hier zu steif",
          f"{kb.verbindung(m)} „{kb.zustand(m)}“")


# --------------------------------------------------------------------------
# 37 C4: eigene Trennflaechen ueber gemeinsamen Randlinien
# --------------------------------------------------------------------------
def test_37():
    from tests import test_a16_trennflaechen as T
    from statik3d import fugen, mesher
    alt = mesher.TRENNFLAECHEN_ZUSAMMENLEGEN
    try:
        for form, typ, zus, soll_weich in (("wuerfel", "hex8", False, True), ("prismen", "tet4", False, True),
                                           ("wuerfel", "hex8", True, False), ("prismen", "tet4", True, False)):
            mesher.TRENNFLAECHEN_ZUSAMMENLEGEN = zus
            m, _log, res, _geo = T._lauf(form, True)
            ku, ko, _d = T._fuge(m)
            uz = float(np.mean(T._oben(m, res)))
            kb = m.add_kontaktbedingung("Fuge", koerpernamen=["Oben"], gegenkoerper=["Unten"])
            kb.standard_anwenden("Reibungsfrei")
            n, z, folge = kb.verbindung(m), kb.zustand(m), fugen.folge_ohne_fuge(m, kb)
            typen = sorted({e.typ for e in m.elements})
            weich = uz > 1.05 * T.U_SOLL      # zweiter Weg: die Rechnung
            if soll_weich:
                ok = (typen == [typ] and n == len(ku & ko) and 0 < n < len(ko) and weich
                      and z == "nicht ausgeführt - hier nur an einzelnen Knoten verbunden (zu weich)"
                      and f"teilen im Netz nur {n} Knoten" in folge and "(zu weich)" in folge
                      and "durchverbunden" not in folge)
                name = (f"37 {form} {typ}, eigene Flächen über denselben Randlinien: "
                        "„nur an einzelnen Knoten verbunden (zu weich)“")
            else:
                ok = (typen == [typ] and n == len(ku & ko) == len(ko) and not weich
                      and abs(uz / T.U_SOLL - 1.0) < 1e-3
                      and z == "nicht ausgeführt - hier zu steif" and "(zu steif)" in folge)
                name = f"37 Gegenprobe {form} {typ}, Flächen im Netz zusammengelegt: weiter „zu steif“"
            check(name, ok, f"{typen}, Fugenknoten oben {len(ko)}, gemeinsam {n}; u_z oben {uz:.5f} mm, "
                            f"Block {T.U_SOLL:.5f} mm ({(uz / T.U_SOLL - 1) * 100:+.0f} %); „{z}“")
    finally:
        mesher.TRENNFLAECHEN_ZUSAMMENLEGEN = alt


# --------------------------------------------------------------------------
# 29 C9: entartete Elemente nicht im Steifigkeitsunterschied
# --------------------------------------------------------------------------
def _mit_entartetem(f):
    from tests import test_gruppe5_meldungen as G
    m, ids, sec = G._kragarm(f)
    k = m.add_node(*(m.nodes[ids[-1]] + [1e-13, 0, 0]))
    m.add_element("beam", [ids[-1], k], "S355", sec.name)
    return m


def test_29():
    from statik3d import diagnose as dg, assemble as asm
    m = _mit_entartetem(1.0)
    neu = len(m.elements) - 1
    ent = [i for i, _t, _g in dg.entartete_elemente(m)]
    z = m.check()
    warn = [x for x in z if "Steifigkeitsunterschied" in x]
    s = dg.steifigkeitsunterschied(m)
    check("29 entartetes Stabelement (1e-13 m): nicht in der Rechnung und keine Warnung Steifigkeitsunterschied",
          ent == [neu] and neu not in asm.aktive_indizes(m) and not warn
          # die fuenf gerechneten Elemente sind gleich steif: kein Paar (None)
          and (s is None or (neu not in (s["steif"][0], s["weich"][0]) and abs(s["faktor"] - 1.0) < 1e-9))
          and any("entartetes Element" in x for x in z),
          f"entartet {ent}; Faktor {s['faktor'] if s else None}; " + (warn[0][:90] if warn else "keine Warnung"))
    m = _mit_entartetem(1e6)
    warn = [x for x in m.check() if "Steifigkeitsunterschied" in x]
    check("29 der echte Unterschied (Faktor 1 000 000, Element 2 gegen 0) bleibt sichtbar",
          len(warn) == 1 and warn[0].startswith("WARNUNG: Steifigkeitsunterschied Faktor 1 000 000 zwischen "
                                                "Element 2 (beam, Werkstoff „X“) und Element 0"),
          warn[0][:120] if warn else "keine Warnung")


# --------------------------------------------------------------------------
# 30 C5: Stabelemente statt Staebe
# --------------------------------------------------------------------------
def test_30():
    from tests import test_gruppe5_meldungen as G
    from statik3d import plastizitaet as pl
    m, _ids, _sec = G._traeger(n=4)
    m.add_member("S1", [0, 1, 2, 3])
    zahl = pl.elastisch_gerechnet(m)
    t = pl.elastisch_text(zahl)
    eins = pl.elastisch_text({"staebe": 1})
    check("30 ein Stab aus vier Elementen: „Stäbe werden elastisch gerechnet (4 Stabelemente)“",
          zahl == {"staebe": 4} and len(m.elements) == 4
          and t.startswith("Stäbe werden elastisch gerechnet (4 Stabelemente):") and "4 Stäbe" not in t
          and "(1 Stabelement)" in eins, t[:80] + " | " + eins[:50])


def main():
    for t in (test_12, test_14, test_27, test_28, test_37, test_29, test_30):
        try:
            t()
        except Exception as ex:            # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} läuft durch", False, f"{type(ex).__name__}: {ex}"[:200])
    n = sum(1 for _name, ok in RESULTS if ok)
    print(f"\nErgebnis: {n}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
