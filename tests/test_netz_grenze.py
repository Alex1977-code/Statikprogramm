"""
Grenze in Unbekannten beim Vernetzen, selbsttaetig groeber (Paket F2, 07.10.2026).

Plan „Smartes Fein beim Vernetzen“ (PLAN-FEIN-SMART-2026-10-07, S2) und die
Entscheidung des Anwenders vom 07.10.2026: Ueberschreitet das Netz die Grenze,
wird **selbsttaetig groeber** vernetzt, nicht mit Meldung angehalten. Jede
Vergroeberung steht im Protokoll mit Stufe, Grund und erreichter Zahl.

Geprueft an 20 Pyramiden (frei vernetzt, also ueber die Arbeitsprozesse) und
an 20 Wuerfeln (abgebildet, im Hauptprozess), ohne Fenster ueber
``mesher.modell_vernetzen``, dazu die Maske der Netzeinstellungen und das
Vernetzen im Hauptfenster offscreen:

* Grenze unter dem Netz der Stufe 0: es wird frueh angehalten (weniger als alle
  Koerper vernetzt), kein halbes Netz steht zu Beginn der naechsten Stufe im
  Modell, das Ergebnis ist das Netz der Stufe 1 - Knoten fuer Knoten wie ohne
  Grenze mit den Einstellungen der Stufe 1 - und liegt unter der Grenze;
* Grenze ueber dem Netz: dasselbe Netz mit denselben Nummern wie ohne Grenze;
* auch die groebste Stufe ueber der Grenze: das Netz der groebsten Stufe und
  eine WARNUNG;
* Entwurf und Mittel (keine Stufen ueber 0): das Netz bleibt, wie es ist, mit
  WARNUNG;
* seriell (ein Prozess) und parallel;
* das Feld ``hoechstens_unbekannte`` (Vorgabe 4 Mio., aeltere Dateien die
  Vorgabe) und in der Maske das Zahlenfeld „Höchstzahl Unbekannte“.

Aufruf:  python -m tests.test_netz_grenze
"""
import os
import sys
import tempfile
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_netz_grenze_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import mesher  # noqa: E402
from statik3d.model import Material, Model, Netzeinstellungen  # noqa: E402

RESULTS = []
#: Kantenlaenge der Stufe 0 und der beiden groeberen Stufen des Pruefkoerpers
#: (gemessen 07.10.2026, tet4: 0,18 m 12 637 Knoten, 0,25 m 5 099 Knoten)
H_STUFEN = (0.18, 0.25, 0.35)


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {str(detail)[:150]}")
    return ok


# --------------------------------------------------------------------------
# Pruefkoerper
# --------------------------------------------------------------------------
class _Bauer:
    def __init__(self, m):
        self.m = m
        self.i = 0

    def linie(self, a, b):
        self.i += 1
        self.m.add_line(f"L{self.i}", [int(a), int(b)], "polyline")
        return f"L{self.i}"


def pyramiden(n: int = 20, h: float = H_STUFEN[0], ordnung: int = 1) -> Model:
    """``n`` Pyramiden nebeneinander, die groesste zuerst (Grundseite 1,95 bis
    1,0 m) - weder abgebildet noch sweepbar, also frei vernetzt und im
    parallelen Weg in den Arbeitsprozessen."""
    m = Model("Pyramiden")
    m.add_material(Material.steel("S235"))
    b = _Bauer(m)
    for i in range(n):
        s = 1.0 + 0.05 * (n - 1 - i)
        P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 1.0]]) * s + [3.0 * i, 0, 0]
        k = m.add_nodes(P)
        R = [b.linie(k[j], k[(j + 1) % 4]) for j in range(4)]
        S = [b.linie(k[j], k[4]) for j in range(4)]
        nm = f"P{i + 1:02d}"
        m.add_flaeche(f"{nm}_B", R, material="S235")
        seiten = []
        for j in range(4):
            m.add_flaeche(f"{nm}_S{j}", [R[j], S[(j + 1) % 4], S[j]], material="S235")
            seiten.append(f"{nm}_S{j}")
        m.add_koerper(nm, [f"{nm}_B"] + seiten, material="S235")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    m.netz.ordnung = ordnung
    return m


def wuerfel(n: int = 20) -> Model:
    """``n`` Einheitswuerfel nebeneinander, abgebildet (Teilung 4 x 4 x 4) -
    vernetzt im Hauptprozess, vor den freien Koerpern."""
    m = Model("Wuerfel")
    m.add_material(Material.steel("S235"))
    b = _Bauer(m)
    for i in range(n):
        P = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]]) + [2.0 * i, 0, 0]
        k = m.add_nodes(P)
        R = [[b.linie(k[o + j], k[o + (j + 1) % 4]) for j in range(4)] for o in (0, 4)]
        V = [b.linie(k[j], k[j + 4]) for j in range(4)]
        nm = f"W{i + 1:02d}"
        m.add_flaeche(f"{nm}_B", R[0], material="S235")
        m.add_flaeche(f"{nm}_D", R[1], material="S235")
        mantel = []
        for j in range(4):
            m.add_flaeche(f"{nm}_M{j}", [R[0][j], V[(j + 1) % 4], R[1][j], V[j]], material="S235")
            mantel.append(f"{nm}_M{j}")
        m.add_koerper(nm, [f"{nm}_B", f"{nm}_D"] + mantel, material="S235")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = 0.25
    m.netz.ordnung = 1
    return m


def stufen_von(netz0, hs=H_STUFEN):
    """Die Testfolge der Vergroeberung: Stufe k hat die Ziellaenge hs[k]; ueber
    die letzte hinaus gibt es keine (None). Stufe 0 ist ``netz0`` selbst."""
    def einstellung(k):
        if k <= 0:
            return netz0
        if k >= len(hs):
            return None
        return replace(netz0, ziellaenge=hs[k], quelle=f"Prüfstufe {k}: Ziellänge {hs[k] * 1e3:.0f} mm")
    return einstellung


def netzbild(m):
    """Was „dasselbe Netz mit denselben Nummern“ heisst: Knotenkoordinaten in
    ihrer Folge, Elemente mit Art und Knoten in ihrer Folge, Elemente je
    Koerper."""
    return (np.array(m.nodes, float).copy(),
            [(e.typ, tuple(int(x) for x in e.nodes)) for e in m.elements],
            {k.name: list(k.elemente or []) for k in m.koerper.values()})


def gleich(a, b) -> bool:
    return (a[0].shape == b[0].shape and np.array_equal(a[0], b[0]) and a[1] == b[1] and a[2] == b[2])


def vernetzen(m, workers, stufen=None):
    """Vernetzen ueber den Weg ohne Oberflaeche; Rueckgabe (Ergebnis, Protokoll)."""
    log = []
    kw = {"stufen": stufen} if stufen is not None else {}
    try:
        erg = mesher.modell_vernetzen(m, log, workers=workers, **kw)
    except TypeError as ex:              # Stand ohne Stufen
        log.append(f"(modell_vernetzen ohne Stufen: {ex})")
        erg = mesher.modell_vernetzen(m, log, workers=workers)
    return erg, log


class Laeufe:
    """Haelt fest, wie das Modell zu Beginn jedes Laufs einer Stufe aussieht und
    was der Lauf zurueckgab (mesher._koerper_lauf, der Lauf einer Stufe)."""

    def __init__(self):
        self.echt = getattr(mesher, "_koerper_lauf", None)
        self.zu_beginn = []
        self.ergebnisse = []

    def __enter__(self):
        if self.echt is not None:
            def lauf(model, koerper, *a, **k):
                self.zu_beginn.append((len(model.elements), int(model.nn),
                                       sum(len(x.elemente or []) for x in koerper),
                                       float(model.netz.ziellaenge)))
                aus = self.echt(model, koerper, *a, **k)
                self.ergebnisse.append(dict(aus))
                return aus
            mesher._koerper_lauf = lauf
        return self

    def __exit__(self, *a):
        if self.echt is not None:
            mesher._koerper_lauf = self.echt


# --------------------------------------------------------------------------
# Feld der Netzeinstellungen
# --------------------------------------------------------------------------
def test_feld():
    n = Netzeinstellungen()
    check("Netzeinstellungen: Feld hoechstens_unbekannte, Vorgabe 4 000 000",
          getattr(n, "hoechstens_unbekannte", None) == 4_000_000, getattr(n, "hoechstens_unbekannte", "fehlt"))
    m = pyramiden(n=1)
    if hasattr(m.netz, "hoechstens_unbekannte"):
        m.netz.hoechstens_unbekannte = 123_456
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_grenze_"), "m.json")
    m.save(pfad)
    m2 = Model.load(pfad)
    check("Speichern und Laden behalten die Grenze (123 456)",
          getattr(m2.netz, "hoechstens_unbekannte", None) == 123_456, getattr(m2.netz, "hoechstens_unbekannte", "fehlt"))
    import json
    with open(pfad, encoding="utf-8") as f:
        d = json.load(f)
    d.get("netz", {}).pop("hoechstens_unbekannte", None)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(d, f)
    m3 = Model.load(pfad)
    check("ältere Datei ohne das Feld: Vorgabe 4 000 000",
          getattr(m3.netz, "hoechstens_unbekannte", None) == 4_000_000, getattr(m3.netz, "hoechstens_unbekannte", "fehlt"))
    check("mesher.unbekannte: drei je Knoten", hasattr(mesher, "unbekannte")
          and mesher.unbekannte(m3) == 3 * m3.nn, f"{3 * m3.nn}")


# --------------------------------------------------------------------------
# Pyramiden: vergroebern, bitgleich, groebste Stufe, ohne Stufen
# --------------------------------------------------------------------------
def _referenzen(workers):
    """Die Netze jeder Stufe ohne Grenze: (Bild, Unbekannte) je Stufe."""
    ref = []
    for h in H_STUFEN:
        m = pyramiden(h=h)
        m.netz.hoechstens_unbekannte = 0
        vernetzen(m, workers)
        ref.append((netzbild(m), 3 * m.nn))
    return ref


def test_pyramiden(workers):
    art = "seriell" if workers == 1 else f"parallel ({workers} Prozesse)"
    print(f"   [{art}]")
    ref = _referenzen(workers)
    u0, u1, u2 = (r[1] for r in ref)
    check(f"{art}: Referenzen ohne Grenze werden gröber (Stufe 0 > 1 > 2)", u0 > u1 > u2,
          f"{u0} / {u1} / {u2} Unbekannte")
    # Wiederholbar: zweimal ohne Grenze dasselbe Netz - sonst sagt „bitgleich“ nichts
    m = pyramiden()
    m.netz.hoechstens_unbekannte = 0
    vernetzen(m, workers)
    check(f"{art}: ohne Grenze zweimal dasselbe Netz (Voraussetzung)", gleich(netzbild(m), ref[0][0]))

    # 1) Grenze ueber dem Netz: dasselbe Netz, dieselben Nummern, keine Warnung
    m = pyramiden()
    m.netz.hoechstens_unbekannte = u0
    erg, log = vernetzen(m, workers, stufen_von(m.netz))
    check(f"{art}: Grenze = Netz (nicht überschritten): bitgleich wie ohne Grenze", gleich(netzbild(m), ref[0][0]),
          f"{3 * m.nn} Unbekannte")
    check(f"{art}: … keine Warnung, keine Vergröberung im Protokoll",
          not [z for z in log if "Netzgrenze" in z or "Unbekannte über" in z], [z for z in log if "Netzgrenze" in z][:1])

    # 2) Grenze zwischen Stufe 1 und Stufe 0: vergroebert auf Stufe 1
    m = pyramiden()
    m.netz.hoechstens_unbekannte = u1
    with Laeufe() as lf:
        erg, log = vernetzen(m, workers, stufen_von(m.netz))
    check(f"{art}: Grenze {u1} unter Stufe 0 ({u0}): Netz der Stufe 1, bitgleich mit der Referenz",
          gleich(netzbild(m), ref[1][0]), f"{3 * m.nn} Unbekannte")
    check(f"{art}: … das Ergebnis liegt unter der Grenze", 3 * m.nn <= u1, f"{3 * m.nn} ≤ {u1}")
    check(f"{art}: … das Ergebnis nennt Stufe 1 und die Unbekannten",
          erg.get("stufe") == 1 and erg.get("unbekannte") == 3 * m.nn,
          f"stufe {erg.get('stufe')}, unbekannte {erg.get('unbekannte')}")
    check(f"{art}: … zwei Läufe (Stufe 0 angehalten, Stufe 1 fertig)", len(lf.ergebnisse) == 2,
          f"{len(lf.ergebnisse)} Läufe")
    if lf.ergebnisse:
        e0 = lf.ergebnisse[0]
        check(f"{art}: … Stufe 0 früh angehalten: weniger als alle 20 Körper vernetzt",
              e0.get("ueber_grenze") and e0.get("fertig", 99) < 20,
              f"{e0.get('fertig')} von 20, {e0.get('unbekannte')} Unbekannte")
    if len(lf.zu_beginn) == 2:
        (el0, kn0, ke0, h0), (el1, kn1, ke1, h1) = lf.zu_beginn
        check(f"{art}: … kein halbes Netz zu Beginn der Stufe 1 (Elemente, Knoten wie vor Stufe 0)",
              (el1, kn1, ke1) == (el0, kn0, ke0) and ke1 == 0, f"vor 0: {el0}/{kn0}/{ke0}, vor 1: {el1}/{kn1}/{ke1}")
        check(f"{art}: … Stufe 1 lief mit ihrer Einstellung (Ziellänge 250 mm)",
              abs(h0 - H_STUFEN[0]) < 1e-12 and abs(h1 - H_STUFEN[1]) < 1e-12, f"{h0} / {h1}")
    else:
        check(f"{art}: … Läufe der Stufen beobachtet", False, f"{len(lf.zu_beginn)} Läufe")
    zeilen = [z for z in log if "Netzgrenze" in z]
    check(f"{art}: … Protokoll: Stufe 0, Grund (Unbekannte über der Grenze) und erreichte Zahl",
          any("Stufe 0" in z and "über der Grenze" in z and "Unbekannte" in z for z in zeilen),
          zeilen[0] if zeilen else "keine Zeile")
    check(f"{art}: … Protokoll nennt die größten Körper mit ihren Knoten (nicht 0)",
          any("größte: P" in z and "(0 Knoten)" not in z for z in zeilen), zeilen[0][-90:] if zeilen else "")
    check(f"{art}: … Protokoll: vernetzt mit Stufe 1 und ihre Zahl",
          any("Stufe 1" in z and _zahl(3 * m.nn) in z for z in zeilen), zeilen[-1] if zeilen else "keine Zeile")
    check(f"{art}: … nach dem Vernetzen stehen die Netzeinstellungen wie vorher",
          abs(m.netz.ziellaenge - H_STUFEN[0]) < 1e-12, m.netz.ziellaenge)

    # 3) Grenze unter allen Stufen: das Netz der groebsten Stufe und eine Warnung
    m = pyramiden()
    m.netz.hoechstens_unbekannte = u2 - 1
    with Laeufe() as lf:
        erg, log = vernetzen(m, workers, stufen_von(m.netz))
    check(f"{art}: Grenze unter der gröbsten Stufe: Netz der gröbsten Stufe (2), bitgleich",
          gleich(netzbild(m), ref[2][0]) and erg.get("stufe") == 2, f"{3 * m.nn} Unbekannte, stufe {erg.get('stufe')}")
    warn = [z for z in log if z.startswith("WARNUNG") and "Unbekannte" in z]
    check(f"{art}: … deutliche WARNUNG mit Zahl und Grenze", any(_zahl(3 * m.nn) in z and _zahl(u2 - 1) in z
                                                               for z in warn), warn[0] if warn else "keine")
    check(f"{art}: … die Stufen 0 und 1 früh angehalten",
          len(lf.ergebnisse) == 3 and all(e.get("ueber_grenze") and e.get("fertig", 99) < 20
                                          for e in lf.ergebnisse[:2]),
          [(e.get("fertig"), e.get("ueber_grenze")) for e in lf.ergebnisse])

    # 4) Ohne Stufen (Entwurf, Mittel): das Netz bleibt, mit Warnung
    m = pyramiden()
    m.netz.hoechstens_unbekannte = u0 // 2
    with Laeufe() as lf:
        erg, log = vernetzen(m, workers)
    check(f"{art}: ohne Stufen über der Grenze: Netz unverändert (bitgleich wie ohne Grenze)",
          gleich(netzbild(m), ref[0][0]), f"{3 * m.nn} Unbekannte")
    warn = [z for z in log if z.startswith("WARNUNG") and "Unbekannte" in z]
    check(f"{art}: … mit WARNUNG (Zahl und Grenze)", any(_zahl(3 * m.nn) in z and _zahl(u0 // 2) in z for z in warn),
          warn[0] if warn else "keine")
    check(f"{art}: … ein einziger Lauf, nicht angehalten",
          len(lf.ergebnisse) == 1 and not lf.ergebnisse[0].get("ueber_grenze"), f"{len(lf.ergebnisse)} Läufe")


def _zahl(n):
    from statik3d.zahlen import zahl_text
    return zahl_text(int(n))


def test_quadratisch():
    """tet10: die Kantenmitten zaehlen mit, und die Schaetzung der fertigen,
    noch nicht eingebauten Koerper haelt nie ein Netz an, das passt."""
    m = pyramiden(h=0.25, ordnung=2)
    m.netz.hoechstens_unbekannte = 0
    vernetzen(m, 3)
    ref, u = netzbild(m), 3 * m.nn
    check("tet10: Kantenmitten zählen (Knoten > 2 × Eckknoten des tet4-Netzes)", u > 2 * 15297, f"{u} Unbekannte")
    m = pyramiden(h=0.25, ordnung=2)
    m.netz.hoechstens_unbekannte = u
    erg, log = vernetzen(m, 3, stufen_von(m.netz, (0.25, 0.4)))
    check("tet10: Grenze genau auf dem Netz: kein Halt, bitgleich", gleich(netzbild(m), ref) and erg.get("stufe") == 0,
          f"stufe {erg.get('stufe')}")
    m = pyramiden(h=0.25, ordnung=2)
    m.netz.hoechstens_unbekannte = u - 3
    with Laeufe() as lf:
        erg, log = vernetzen(m, 3, stufen_von(m.netz, (0.25, 0.4)))
    check("tet10: drei Unbekannte darunter: vergröbert auf Stufe 1, unter der Grenze",
          erg.get("stufe") == 1 and 3 * m.nn <= u - 3, f"stufe {erg.get('stufe')}, {3 * m.nn} Unbekannte")


# --------------------------------------------------------------------------
# Wuerfel: abgebildet im Hauptprozess
# --------------------------------------------------------------------------
def test_wuerfel():
    m = wuerfel()
    m.netz.hoechstens_unbekannte = 0
    vernetzen(m, 2)
    ref, u = netzbild(m), 3 * m.nn
    check("20 Würfel abgebildet (hex8, 4 × 4 × 4)", len(m.elements) == 20 * 64, f"{len(m.elements)} Elemente, {u} Unb.")
    m = wuerfel()
    m.netz.hoechstens_unbekannte = u // 4
    with Laeufe() as lf:
        erg, log = vernetzen(m, 2, stufen_von(m.netz, (0.25, 0.5)))
    check("Würfel über der Grenze: Stufe 0 im Hauptprozess früh angehalten",
          bool(lf.ergebnisse) and lf.ergebnisse[0].get("ueber_grenze") and lf.ergebnisse[0].get("fertig", 99) < 20,
          [(e.get("fertig"), e.get("ueber_grenze")) for e in lf.ergebnisse])
    check("… die Teilung hängt nicht an der Ziellänge: gröbste Stufe = dasselbe Netz, mit WARNUNG",
          gleich(netzbild(m), ref) and any(z.startswith("WARNUNG") and "Unbekannte" in z for z in log),
          f"stufe {erg.get('stufe')}")
    if len(lf.zu_beginn) == 2:
        check("… kein halbes Netz zu Beginn der Stufe 1", lf.zu_beginn[1][:3] == lf.zu_beginn[0][:3],
              f"{lf.zu_beginn}")


# --------------------------------------------------------------------------
# Oberflaeche: Maske und Vernetzen im Fenster
# --------------------------------------------------------------------------
_FENSTER = {}
FEHLER = []


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    w._fragen_knoepfe = lambda *a, **k: True
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, FEHLER)
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell_ins_fenster(w, app, m):
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()


def test_maske():
    w, app = _fenster()
    m = pyramiden(n=2)
    _modell_ins_fenster(w, app, m)
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    f = mk._felder.get("hoechstens_unbekannte")
    check("Maske Netzeinstellungen: Zahlenfeld „Höchstzahl Unbekannte“", f is not None
          and getattr(mk, "_feldtexte", {}).get("hoechstens_unbekannte") == "Höchstzahl Unbekannte",
          ", ".join(mk._felder))
    if f is not None:
        check("… zeigt die Vorgabe 4 000 000", abs(float(mk.werte()["hoechstens_unbekannte"]) - 4e6) < 0.5,
              mk.werte()["hoechstens_unbekannte"])
        hinweis = getattr(mk, "_hinweise", {}).get("hoechstens_unbekannte", "")
        check("… mit Hinweis (gröber vernetzen, 0 = keine Grenze)",
              "gröber" in hinweis and "0" in hinweis, hinweis)
        reihe = list(mk._felder)
        check("… steht neben „Höchstzahl Elemente je Objekt“",
              reihe.index("hoechstens_unbekannte") == reihe.index("max_elemente") + 1, reihe)
        f.setText("123456")
        mk.anwenden()
        app.processEvents()
        check("Übernehmen: hoechstens_unbekannte = 123 456",
              getattr(w.model.netz, "hoechstens_unbekannte", None) == 123456,
              getattr(w.model.netz, "hoechstens_unbekannte", "fehlt"))
    w.maskenrand.schliessen()


def test_fenster_vernetzen():
    """Vernetzen im Fenster ueber der Grenze: Netz bleibt (Mittel/Entwurf haben
    keine Stufen), Protokoll mit WARNUNG und die Warnung als Meldung."""
    w, app = _fenster()
    m = pyramiden(n=4, h=0.25)
    m.netz.hoechstens_unbekannte = 300
    _modell_ins_fenster(w, app, m)
    gewarnt = []
    alt = w.warnung
    w.warnung = lambda msg: gewarnt.append(str(msg))
    w._netzaenderung_bestaetigen = lambda *a, **k: True
    try:
        w.geometrie_vernetzen()
        app.processEvents()
    finally:
        w.warnung = alt
    text = w.log.toPlainText()
    check("Fenster: vernetzt (Netz bleibt)", len(m.elements) > 0, f"{len(m.elements)} Elemente")
    check("… Protokoll mit WARNUNG zur Grenze", "WARNUNG" in text and "Höchstzahl Unbekannte" in text,
          [z for z in text.splitlines() if "Unbekannte" in z][-1:])
    check("… und eine Warnung als Meldung mit Zahl und Grenze",
          bool(gewarnt) and _zahl(3 * m.nn) in gewarnt[0] and _zahl(300) in gewarnt[0], gewarnt[:1])


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1500, exit=True)
    for t, a in ((test_feld, ()), (test_pyramiden, (3,)), (test_pyramiden, (1,)), (test_quadratisch, ()),
                 (test_wuerfel, ()), (test_maske, ()), (test_fenster_vernetzen, ())):
        print(f"\n--- {t.__name__}{a if a else ''} ---")
        try:
            t(*a)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    failed = [n for n, ok in RESULTS if not ok]
    if failed:
        print("FEHLGESCHLAGEN:", failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
