"""Zusammenfuehrung vom 14.10.2026 (integ/gesamt): was zwei Zweige je fuer
sich gebaut hatten, gibt es nur noch einmal.

* Werkstoffart Spannstahl: nur ``Material.art`` (plast/verfestigung). Bis
  dahin kennzeichnete der RFEM-Import Spannstahl fuer die Vorspannkraft
  zusaetzlich in ``model.meta["spannstahl"]``, und der Vorschlag der Sollkraft
  (0,9·f_p0,1k·A) erkannte ihn daran oder am Werkstoffnamen - der
  Stabnachweis aber an ``Material.art``.
* Vorspannung als Last: ein Merkmal und eine Anzeige. Bis dahin nannte die
  Vorspannkraft eine als Temperatur stehende Vorspannung „aus Vorspannung
  952 kN, E = …, α = …“ (``TempLoad.vorspanntext``), der Import dieselbe Last
  „Vorspannung 952 kN (eingeprägte Dehnung, E = …, α = …)“
  (``TempLoad.vorspann_text``). Jetzt steht beides in der Form des Imports.
* Stabenden an 1-3 Knoten: am Rechenstart eine Warnung statt zwei (die
  netzabhaengige Spitze aus spitzenstellen und der Hinweis auf die
  verteilende Einleitung aus stabeinleitung).

Aufruf:  python -m tests.test_zusammenfuehrung
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Material, Model, Section, TempLoad   # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FEHLER'} {name:80s} {detail}")
    return ok


SATZ = "Vorspannung 952 kN (eingeprägte Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K)"


def _anker(name="Anker St 835/1030", art=""):
    """Ein Zugstab Rund 40 (Spannstahl-Kennwerte) mit Stabname A1."""
    m = Model()
    m.add_material(Material(name, E=170e9, nu=0.3, rho=7850.0, alpha=1e-5, fy=835e6, fu=1030e6, art=art))
    m.add_section(Section.circle("Rund 40", 0.04))
    a, b = m.add_node(0.0, 0.0, 0.0), m.add_node(0.0, 0.0, 3.0)
    e = m.add_element("truss", [a, b], name, "Rund 40")
    m.add_member("A1", [e])
    return m, e


def test_spannstahl_art():
    print("\n--- Werkstoffart Spannstahl: nur Material.art ---")
    from statik3d import vorspannkraft as vk
    from statik3d.ec3 import spannstahl as sp
    from statik3d.importers import rfem6_db as R6
    from tests.test_spannstahl import _rf6_spannstahl
    tmp = tempfile.mkdtemp()
    try:
        m = R6.read_rf6(_rf6_spannstahl(os.path.join(tmp, "anker.rf6")), log=[])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    mat = list(m.materials.values())[0]
    check("Import Typ 15: Werkstoffart Spannstahl am Werkstoff", getattr(mat, "art", "") == "Spannstahl",
          repr(getattr(mat, "art", None)))
    check("… und keine zweite Kennzeichnung in model.meta[\"spannstahl\"]",
          "spannstahl" not in (m.meta or {}), str((m.meta or {}).get("spannstahl")))
    A = 0.04 ** 2 * 3.141592653589793 / 4
    m1, _e = _anker(art="Spannstahl")
    soll = 0.9 * 835e6 * A
    v1 = vk.vorschlag_sollkraft(m1, "A1", 952e3)
    check("art = Spannstahl: Vorschlag 0,9·f_p0,1k·A", abs(v1 - soll) <= 1e-6 * soll,
          f"{v1 / 1e3:.3f} kN, soll {soll / 1e3:.3f} kN")
    m2, _e = _anker(name="Spannstahl St 835/1030", art="")
    v2 = vk.vorschlag_sollkraft(m2, "A1", 952e3)
    check("nur der Name sagt Spannstahl, die Art nicht: Vorschlag ist der RFEM-Wert",
          abs(v2 - 952e3) < 1e-6, f"{v2 / 1e3:.3f} kN")
    gleich = all(vk.ist_spannstahl(mm, n) == sp.ist_spannstahl(mm.materials[n])
                 for mm in (m1, m2) for n in mm.materials)
    check("Vorspannkraft und Stabnachweis sagen dasselbe, was Spannstahl ist", gleich)


def test_vorspannung_ein_merkmal():
    print("\n--- Vorspannung als Last: ein Merkmal, eine Anzeige ---")
    m, e = _anker(name="Material 3", art="Spannstahl")
    A = m.sections["Rund 40"].A
    dT = -952e3 / (170e9 * A * 1e-5)
    fall = m.active_case
    # wie der Import seit dem 13.10.2026: mit gespeichertem Merkmal
    m.load_temp(e, dT, case=fall, aus_vorspannung=952e3, vorspann_E=170e9, vorspann_alpha=1e-5)
    # wie eine Datei, die vor dem 13.10.2026 aus RFEM kam: nur die Temperatur
    m.load_temp(e, dT, case=fall)
    neu, alt = m.case(fall).temp_loads
    check("gespeichertes Merkmal: der Satz des Imports", neu.vorspann_text(m) == SATZ, neu.vorspann_text(m))
    check("nur die Temperatur (Datei von vorher): derselbe Satz", alt.vorspann_text(m) == SATZ,
          alt.vorspann_text(m))
    check("… Kraft und Umrechnung einzeln wie beim Import",
          alt.vorspann_kraft_text(model=m) == "952 kN"
          and alt.vorspann_umrechnung_text(model=m) == "eingeprägte Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K",
          f"{alt.vorspann_kraft_text(model=m)} | {alt.vorspann_umrechnung_text(model=m)}")
    check("ohne Modell: nur das gespeicherte Merkmal", neu.vorspann_text() == SATZ and alt.vorspann_text() == "",
          f"{neu.vorspann_text()!r} / {alt.vorspann_text()!r}")
    b_neu, b_alt = neu.bezug(m), alt.bezug(m)
    check("Bezug mit Merkmal: nur die Kraft", b_neu == f"Element {e}: {SATZ}", b_neu)
    check("Bezug ohne Merkmal: ΔT und dahinter derselbe Satz",
          b_alt == f"Element {e}: ΔT = {dT:+.1f} K → {SATZ}", b_alt)
    check("die alte Form „aus Vorspannung …, E = …“ gibt es nicht mehr",
          "aus Vorspannung" not in b_alt and not hasattr(TempLoad, "vorspanntext"))
    m3, e3 = _anker()
    m3.elements[e3].typ = "beam"
    balken = TempLoad(e3, 20.0)
    check("eine gewöhnliche Temperatur an einem Balken bleibt eine Temperatur",
          balken.vorspann_text(m3) == "" and balken.bezug(m3) == f"Element {e3}: ΔT = +20.0 K",
          balken.bezug(m3))
    from statik3d import vorspannkraft as vk
    log = []
    vk.import_hinweise(m, log=log)
    zeilen = [z for z in log if "als ΔT gerechnet" in z]
    check("Importhinweis der Umwandlung nennt die Vorspannung in derselben Form",
          zeilen and "als ΔT gerechnet: Vorspannung 952 kN (eingeprägte Dehnung" in zeilen[0], str(zeilen[:1]))


def test_stabenden_eine_warnung():
    print("\n--- Stabenden an 1-3 Knoten: eine Warnung am Rechenstart ---")
    from statik3d import diagnose, fugen, spitzenstellen
    from statik3d import stabeinleitung as SE
    from tests.test_stabeinleitung import lagern_frei, quader, zugstab
    m = quader(h=0.01)
    lagern_frei(m)
    zugstab(m)
    fugen.stabenden_koppeln(m, [])
    bef = diagnose.abnahme(m, warnungen=True)
    stab = [b for b in bef if (b.pruefung == spitzenstellen.PRUEFUNG and b.objekt == spitzenstellen.STABENDE)
            or b.pruefung == SE.PRUEFUNG]
    for b in stab:
        print(f"       {b.pruefung}: {b.text}")
    check("eine Warnung für das Stabende, nicht zwei", len(stab) == 1, f"{len(stab)} Warnungen")
    t = stab[0].text if stab else ""
    check("… sie nennt die mögliche netzabhängige Spannungsspitze",
          "Stabende hängt an" in t and "mögliche netzabhängige Spannungsspitzen" in t, t[:120])
    check("… und den Ausweg, die verteilende Einleitung",
          "Verteilende Einleitung über die Stirnfläche möglich (Modelleinstellung oder je Stabende)" in t, t[-120:])
    check("… als WARNUNG, die nichts anhält", stab and stab[0].stufe == "WARNUNG")


def main():
    for t in (test_spannstahl_art, test_vorspannung_ein_merkmal, test_stabenden_eine_warnung):
        try:
            t()
        except Exception as ex:          # noqa: BLE001 - jede Pruefung meldet sich
            import traceback
            traceback.print_exc()
            check(f"{t.__name__} ohne Ausnahme", False, f"{type(ex).__name__}: {ex}")
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print(f"\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
