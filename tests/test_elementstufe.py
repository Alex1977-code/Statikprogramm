"""
Elementstufe Entwurf / Mittel / Fein statt Haken (25.09.2026).

Entscheidungen des Anwenders vom 25.09.2026:

* „was hältst du von presets für die zu verwendenen elemente. zb entwurf
  tet4 etc dann mittel tet10 und fein hex 20 …“ – „keep it simple“, „viel
  zu fummelig“: ein Auswahlfeld „Elemente“ ersetzt Elementansatz und Haken.
* „sweepen muss das programm doch automatisch wenn das entsprechende element
  das verlangt“: jede Stufe setzt den Sweep auf „sauber“.
* „Fein ohne tetp“.
* „kontakt und plastizität muss in allen stufen funktionieren“: Kontakt
  sperrt heute quadratische Seiten (fugen.QuadratischeSeiten). Darum sind
  Mittel und Fein an Modellen mit Kontakt sichtbar, aber gesperrt, und das
  Modell steht mit Hinweis auf Entwurf – statt dass das Vernetzen abbricht.
* „der haken zur plastizität kann in jedem fall bleiben“.
* Import mit abweichender Vorgabe: „Beim Import fragen“.

Geprueft ohne Fenster (statik3d.elementstufe, Vernetzen und Rechnen mit
Kontakt und Plastizitaet in jeder Stufe) und mit dem Hauptfenster offscreen
(Netzeinstellungen, Vernetzen, Import).

Aufruf:  python -m tests.test_elementstufe
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_elementstufe_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d.model import DofBehaviour, Material, Model, Netzeinstellungen  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:78s} {str(detail)[:140]}")
    return ok


def _es():
    from statik3d import elementstufe
    return elementstufe


def _wissenschaftlich(text: str) -> bool:
    return re.search(r"\de[+-]?\d", text) is not None


# --------------------------------------------------------------------------
# Pruefkoerper: Geometrie ohne Netz
# --------------------------------------------------------------------------
class _Bauer:
    def __init__(self, m):
        self.m = m
        self.i = 0

    def linie(self, a, b):
        self.i += 1
        self.m.add_line(f"L{self.i}", [a, b], "polyline")
        return f"L{self.i}"


def wuerfel(h: float = 0.5) -> Model:
    """Einheitswuerfel V1 (Boden z = 0, Deckel z = 1), noch ohne Netz."""
    m = Model("Wuerfel")
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                          [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]]))
    b = _Bauer(m)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4)]
    V = [b.linie(i, i + 4) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Deckel", R[1], material="S235")
    mantel = []
    for i in range(4):
        m.add_flaeche(f"M{i}", [R[0][i], V[(i + 1) % 4], R[1][i], V[i]], material="S235")
        mantel.append(f"M{i}")
    # abgebildeter Sechsflaechner: Teilung aus dem Koerper (2 x 2 x 2)
    m.add_koerper("V1", ["Boden", "Deckel"] + mantel, material="S235", teilung=[2, 2, 2])
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    return m


def pyramide(h: float = 0.25) -> Model:
    """Pyramide P (Grund 1 x 1 m bei z = 0, Spitze 1 m hoch) - weder
    abgebildet noch sweepbar: der freie Vernetzer macht Tetraeder. Groeber
    als 250 mm vernetzt er sie nicht (D/4), darum h = 250 mm: Mittel 306,
    Fein 2 509 Tetraeder (gemessen 25.09.2026)."""
    m = Model("Pyramide")
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 1.0]]))
    b = _Bauer(m)
    R = [b.linie(i, (i + 1) % 4) for i in range(4)]
    S = [b.linie(i, 4) for i in range(4)]
    m.add_flaeche("Boden", R, material="S235")
    seiten = []
    for i in range(4):
        m.add_flaeche(f"S{i}", [R[i], S[(i + 1) % 4], S[i]], material="S235")
        seiten.append(f"S{i}")
    m.add_koerper("P", ["Boden"] + seiten, material="S235")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    return m


def zwei_bloecke(h: float = 0.5) -> Model:
    """Zwei Einheitswuerfel uebereinander mit gemeinsamer Fuge, ohne Netz."""
    m = Model("Zwei Bloecke")
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                          [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
                          [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.]]))
    b = _Bauer(m)
    R = [[b.linie(o + i, o + (i + 1) % 4) for i in range(4)] for o in (0, 4, 8)]
    V01 = [b.linie(i, i + 4) for i in range(4)]
    V12 = [b.linie(i + 4, i + 8) for i in range(4)]
    m.add_flaeche("Boden", R[0], material="S235")
    m.add_flaeche("Dach", R[2], material="S235")
    m.add_flaeche("Fuge", R[1], material="S235")
    unten, oben = [], []
    for i in range(4):
        m.add_flaeche(f"MU{i}", [R[0][i], V01[(i + 1) % 4], R[1][i], V01[i]], material="S235")
        m.add_flaeche(f"MO{i}", [R[1][i], V12[(i + 1) % 4], R[2][i], V12[i]], material="S235")
        unten.append(f"MU{i}")
        oben.append(f"MO{i}")
    m.add_koerper("Unten", ["Boden", "Fuge"] + unten, material="S235")
    m.add_koerper("Oben", ["Fuge", "Dach"] + oben, material="S235")
    m.netz.dichte = "eigene"
    m.netz.ziellaenge = h
    return m


def fuge(m: Model, starr: bool = False):
    """Kontaktbedingung an der Fuge: senkrecht nur Druck, in der Ebene starr
    (wie eine Kontaktfuge aus RFEM). starr=True: in allen Richtungen starr -
    eine Schweissnaht an gemeinsamer Flaeche, die nichts trennt."""
    t = DofBehaviour("rigid")
    n = DofBehaviour("rigid") if starr else DofBehaviour("free", failure="zug")
    return m.add_kontaktbedingung("Fuge", flaechennamen=["Fuge"], gegenflaechen=[],
                                  koerpernamen=["Oben"], behaviour={0: t, 1: t, 2: n})


def _knoten_z(m: Model, z: float) -> list:
    im = np.zeros(m.nn, bool)
    im[[int(x) for e in m.elements for x in e.nodes]] = True
    return [int(i) for i in np.flatnonzero(im & (np.abs(m.nodes[:, 2] - z) < 1e-9))]


def vernetzen(m: Model) -> list:
    """Wie Netz -> Vernetzen, ohne Oberflaeche: Stufe (Sperre, Fein) und
    mesher.modell_vernetzen. Rueckgabe das Protokoll."""
    from statik3d import mesher
    es = _es()
    log = []
    with es.beim_vernetzen(m, log):
        mesher.modell_vernetzen(m, log, workers=1)
    return log


def druck(m: Model, oben: str, z_oben: float, p: float, plastisch: bool = False, mitte: bool = False):
    """Unten eingespannt, oben Druck p [N/m^2] auf die Flaeche ``oben`` -
    mitte=True nur auf das mittlere Viertel (0,25 … 0,75 m in x und y): dort
    fliesst es oertlich, der Rest bleibt elastisch."""
    from statik3d import plastizitaet as pl
    from statik3d import solver
    for i in _knoten_z(m, 0.0):
        m.fix(i, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    bereich = ({"art": "rechteck", "ursprung": [0, 0, z_oben], "u": [1, 0, 0], "v": [0, 1, 0],
                "von": [0.25, 0.25], "bis": [0.75, 0.75]} if mitte else None)
    m.add_geometrielast(oben, p, "flaeche", bereich=bereich, case="LF1")
    m.lasten_verteilen()
    if plastisch:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=0.02, laststufen=2,
                                         iterationen=60, toleranz=1e-6)
    return solver.solve_static(m, case="LF1")


# --------------------------------------------------------------------------
# 1) Die Stufen ohne Fenster
# --------------------------------------------------------------------------
def test_stufen_und_texte():
    es = _es()
    check("drei Stufen Entwurf / Mittel / Fein, Vorgabe Mittel",
          tuple(es.STUFEN) == ("entwurf", "mittel", "fein") and es.VORGABE == "mittel",
          str(es.STUFEN))
    check("Zweck Entwurf wörtlich",
          es.ZWECK["entwurf"] == "schnell; für Vorbemessung und Verformungen – Spannungen fallen zu "
                                 "niedrig aus", es.ZWECK["entwurf"])
    check("Zweck Mittel und Fein wörtlich", es.ZWECK["mittel"] == "für die Nachweise"
          and es.ZWECK["fein"] == "für Bohrungen, Kerben und Ermüdung")
    check("Entwurf: tet4, hex8 (VQ83) mit Entartung, Schalen linear",
          all(x in es.ELEMENTE["entwurf"] for x in ("tet4", "hex8", "VQ83", "linear")), es.ELEMENTE["entwurf"])
    check("Mittel: tet10, hex20 (VQ203), Schalen quadratisch",
          all(x in es.ELEMENTE["mittel"] for x in ("tet10", "hex20", "VQ203", "quadratisch")))
    check("Fein: wie Mittel mit halber Kantenlänge, ohne tetp",
          "halbe" in es.ELEMENTE["fein"] and "tetp" not in es.ELEMENTE["fein"])
    check("Auswahltexte: Mittel trägt „(Vorgabe)“",
          [es.AUSWAHL[s] for s in es.STUFEN] == ["Entwurf", "Mittel (Vorgabe)", "Fein"])
    check("aus_text liest die Auswahl zurück", [es.aus_text(es.AUSWAHL[s]) for s in es.STUFEN]
          == list(es.STUFEN) and es.aus_text("quatsch") is None)
    check("Sperrhinweis wörtlich",
          es.SPERRHINWEIS == "mit Kontakt noch nicht verfügbar – Kontakt für quadratische Elemente folgt")


def test_stufe_und_setzen():
    es = _es()
    check("alte Netzeinstellungen ordnung 1 → Entwurf", es.stufe(Netzeinstellungen(ordnung=1)) == "entwurf")
    check("alte Netzeinstellungen ordnung 2 → Mittel", es.stufe(Netzeinstellungen(ordnung=2)) == "mittel")
    check("Fein bleibt Fein (ordnung 2)", es.stufe(Netzeinstellungen(ordnung=2, stufe="fein")) == "fein")
    check("widersprüchlich (Fein, aber ordnung 1) → Entwurf: die Ordnung zählt",
          es.stufe(Netzeinstellungen(ordnung=1, stufe="fein")) == "entwurf")
    check("unbekanntes Wort → aus der Ordnung", es.stufe(Netzeinstellungen(ordnung=2, stufe="xy")) == "mittel")
    n0 = Netzeinstellungen(ziellaenge=0.05, dichte="eigene", vernetzer="gmsh", pyramiden=True)
    for s, o in (("entwurf", 1), ("mittel", 2), ("fein", 2)):
        n = es.setzen(n0, s)
        check(f"setzen {s}: ordnung {o}, sweep „sauber“, Stufe gespeichert",
              n.ordnung == o and n.sweep == "sauber" and n.stufe == s and es.stufe(n) == s,
              f"{n.ordnung} {n.sweep} {n.stufe}")
    n = es.setzen(n0, "fein")
    check("setzen lässt die übrigen Einstellungen (Ziellänge, Vernetzer, Pyramiden)",
          n.ziellaenge == 0.05 and n.vernetzer == "gmsh" and n.pyramiden and n.dichte == "eigene")
    check("setzen ändert die Eingabe nicht", n0.stufe == "" and n0.ordnung == 1 and n0.sweep == "aus")
    try:
        es.setzen(n0, "grob")
        check("unbekannte Stufe: Fehler", False)
    except ValueError as ex:
        check("unbekannte Stufe: Fehler im Klartext", "Entwurf" in str(ex), str(ex))


def test_laden_und_speichern():
    es = _es()
    m = Model("x")
    m.netz = es.setzen(m.netz, "fein")
    d = m.to_dict()
    check("gespeichert: stufe fein", d["netz"].get("stufe") == "fein", str(d["netz"].get("stufe")))
    m2 = Model.from_dict(d)
    check("geladen: Fein, sweep sauber", es.stufe(m2.netz) == "fein" and m2.netz.sweep == "sauber")
    for ordnung, soll in ((1, "entwurf"), (2, "mittel")):
        d2 = dict(d)
        d2["netz"] = {k: v for k, v in d["netz"].items() if k != "stufe"}
        d2["netz"]["ordnung"] = ordnung
        m3 = Model.from_dict(d2)
        check(f"ältere Datei ohne Stufe, ordnung {ordnung} → {soll}", es.stufe(m3.netz) == soll)


def test_beschreibung():
    es = _es()
    n = es.setzen(Netzeinstellungen(), "mittel")
    t = n.beschreibung()
    check("Beschreibung nennt die Stufe und die quadratischen Elemente",
          "Elemente Mittel" in t and "quadratische Elemente" in t, t)
    t = es.setzen(Netzeinstellungen(), "entwurf").beschreibung()
    check("… Entwurf: lineare Elemente", "Elemente Entwurf" in t and "lineare Elemente" in t, t)


def test_fein_halbe_kantenlaenge():
    """Fein = Mittel mit halber Kantenlaenge - gemessen an dem, was der
    Vernetzer je Objekt nimmt (netzdichte.elementlaenge)."""
    from statik3d import netzdichte as nd
    es = _es()
    m = wuerfel()
    k = m.koerper["V1"]
    n_mittel = es.setzen(m.netz, "mittel")
    check("Mittel: wirksam ist dieselbe Einstellung", es.wirksam(n_mittel, m) is n_mittel)
    check("Entwurf: wirksam ist dieselbe Einstellung",
          es.wirksam(es.setzen(m.netz, "entwurf"), m).ordnung == 1)
    for dichte in ("grob", "mittel", "fein", "eigene"):
        n = es.setzen(Netzeinstellungen(dichte=dichte, ziellaenge=0.4), "mittel")
        f = es.setzen(n, "fein")
        h_m = nd.elementlaenge(m, n, k)["h_dichte"]
        h_f = nd.elementlaenge(m, es.wirksam(f, m), k)["h_dichte"]
        check(f"Netzdichte {dichte}: Fein hat die halbe Kantenlänge von Mittel",
              abs(h_f - 0.5 * h_m) < 1e-12, f"{h_m * 1e3:.2f} → {h_f * 1e3:.2f} mm")
    f = es.setzen(Netzeinstellungen(dichte="eigene", ziellaenge=0.4, h_min=0.02, h_max=0.3,
                                    koerper_h={"V1": 0.1},
                                    verfeinerungen=[{"art": "kugel", "mitte": [0, 0, 0], "radius": 0.1,
                                                     "h": 0.01}],
                                    feldpunkte=[[0, 0, 0, 0.02], [1, 1, 1, 0.04, 0.2]]), "fein")
    w = es.wirksam(f, m)
    check("… kleinste/größte Elementgröße, Kantenlänge je Körper, Verfeinerungen, Feldpunkte halb",
          abs(w.h_min - 0.01) < 1e-15 and abs(w.h_max - 0.15) < 1e-15 and abs(w.koerper_h["V1"] - 0.05) < 1e-15
          and abs(w.verfeinerungen[0]["h"] - 0.005) < 1e-15 and abs(w.feldpunkte[0][3] - 0.01) < 1e-15
          and abs(w.feldpunkte[1][3] - 0.02) < 1e-15 and w.feldpunkte[1][4] == 0.2,
          f"{w.h_min} {w.h_max} {w.koerper_h} {w.verfeinerungen} {w.feldpunkte}")
    check("… die gespeicherte Einstellung bleibt", f.h_min == 0.02 and f.koerper_h == {"V1": 0.1}
          and f.feldpunkte[0][3] == 0.02)
    check("… die Höchstzahl je Objekt bleibt (Schutz, keine Kantenlänge)",
          w.max_elemente == f.max_elemente)
    t = es.kantenlaenge_text(es.setzen(Netzeinstellungen(dichte="eigene", ziellaenge=0.05), "fein"))
    check("Text der wirksamen Kantenlänge (eigene 50 mm, Fein): 25 mm", "25 mm" in t and "50" in t, t)
    t = es.kantenlaenge_text(es.setzen(Netzeinstellungen(dichte="eigene", ziellaenge=0.5), "fein"), m)
    check("… mit Modell: je Körper die Kantenlänge im Feld", "250 mm" in t, t)
    check("… ohne wissenschaftliche Zahl", not _wissenschaftlich(t))


def test_sperre():
    """Die eine Stelle, an der die Sperre haengt (elementstufe.quadratisch_gesperrt)."""
    es = _es()
    m = zwei_bloecke()
    check("ohne Kontakt: nichts gesperrt", es.quadratisch_gesperrt(m) == []
          and all(es.frei(m, s) for s in es.STUFEN))
    fuge(m)
    g = es.quadratisch_gesperrt(m)
    check("Kontaktbedingung (Druck, Abheben): gesperrt mit Namen", g == ["Kontaktbedingung Fuge"], str(g))
    check("… Entwurf frei, Mittel und Fein gesperrt",
          es.frei(m, "entwurf") and not es.frei(m, "mittel") and not es.frei(m, "fein"))
    m.kontaktbedingungen["Fuge"].aus = True
    check("abgeschaltete Bedingung sperrt nicht", es.quadratisch_gesperrt(m) == [])
    m2 = zwei_bloecke()
    fuge(m2, starr=True)
    check("verschweißt an gemeinsamer Fläche (trennt nichts) sperrt nicht", es.quadratisch_gesperrt(m2) == [],
          str(es.quadratisch_gesperrt(m2)))
    m3 = wuerfel()
    ss = m3.add_surface_support(name="Boden fest", ux=dict(typ="rigid"), uy=dict(typ="rigid"),
                                uz=dict(typ="rigid"))
    ss.flaechen = ["Boden"]
    check("Flächenlager (nimmt ebenfalls nur Eckknoten) sperrt", es.quadratisch_gesperrt(m3)
          == ["Flächenlager Boden fest"], str(es.quadratisch_gesperrt(m3)))
    m4 = wuerfel()
    m4.add_contact_pair("Paar", [0, 1], master_elements=[])
    check("Kontaktpaar sperrt", es.quadratisch_gesperrt(m4) == ["Kontaktpaar Paar"],
          str(es.quadratisch_gesperrt(m4)))
    # Sperre anwenden: Mittel -> Entwurf mit Protokollzeile, nie still
    m5 = zwei_bloecke()
    fuge(m5)
    m5.netz = es.setzen(m5.netz, "mittel")
    check("wirksame Stufe am Kontaktmodell: Entwurf", es.wirksame_stufe(m5) == "entwurf")
    z = es.sperre_anwenden(m5)
    check("sperre_anwenden: Modell steht auf Entwurf", es.stufe(m5.netz) == "entwurf"
          and m5.netz.ordnung == 1, m5.netz.stufe)
    check("… die Zeile nennt Hinweis, Stufe und Grund", es.SPERRHINWEIS in z and "Mittel" in z
          and "Entwurf" in z and "Kontaktbedingung Fuge" in z, z)
    check("… zweites Mal: nichts mehr zu tun", es.sperre_anwenden(m5) == "")
    m6 = zwei_bloecke()
    m6.netz = es.setzen(m6.netz, "fein")
    check("ohne Kontakt bleibt Fein", es.sperre_anwenden(m6) == "" and es.stufe(m6.netz) == "fein")


# --------------------------------------------------------------------------
# 2) Kontakt und Plastizitaet in jeder Stufe (Anwender 25.09.2026)
# --------------------------------------------------------------------------
def test_kontakt_in_jeder_stufe():
    """Jede Stufe, die der Anwender waehlen kann, vernetzt und rechnet ein
    Modell mit Kontaktfuge - Mittel und Fein ueber die Sperre als Entwurf."""
    from statik3d import fugen, mesher
    es = _es()
    p = 1.0e7
    for s in es.STUFEN:
        m = zwei_bloecke()
        fuge(m)
        m.netz = es.setzen(m.netz, s)
        try:
            log = vernetzen(m)
            ok, text = True, ""
        except Exception as ex:      # noqa: BLE001
            log, ok, text = [], False, f"{type(ex).__name__}: {ex}"
        typen = sorted({e.typ for e in m.elements})
        check(f"{s}: vernetzt ohne Abbruch, lineare Elemente", ok and typen
              and set(typen) <= {"tet4", "hex8", "pent6", "pyr5"}, text[:120] or str(typen))
        check(f"{s}: Kontaktfuge getrennt", m.kontaktbedingungen["Fuge"].ausgefuehrt)
        if s != "entwurf":
            check(f"{s}: das Protokoll nennt die Sperre und Entwurf",
                  any(es.SPERRHINWEIS in z and "Entwurf" in z for z in log))
        if not ok:
            continue
        r = druck(m, "Dach", 2.0, p)
        R = float(r.reactions[_knoten_z(m, 0.0), 2].sum())
        check(f"{s}: gerechnet, das Fundament trägt die Last (Druck über die Fuge)",
              abs(R - p) < 1e-6 * p, f"R = {R / 1e3:.3f} kN")
    # Beleg, was die Sperre verhindert: am Stand vor ihr brach das Vernetzen ab
    m = zwei_bloecke()
    fuge(m)
    m.netz.ordnung = 2
    try:
        mesher.modell_vernetzen(m, [], workers=1)
        abbruch = False
    except fugen.QuadratischeSeiten:
        abbruch = True
    check("ohne Stufe (ordnung 2 direkt) bricht das Vernetzen laut ab", abbruch)


def test_plastizitaet_in_jeder_stufe():
    """Das Fliessen rechnet in jeder Stufe - am Wuerfel (abgebildet: hex8
    bzw. hex20) und am Kontaktmodell (Entwurf ueber die Sperre)."""
    from statik3d import plastizitaet as pl
    es = _es()
    fy = 235e6
    zahl = {}
    for s in es.STUFEN:
        m = wuerfel()
        m.netz = es.setzen(m.netz, s)
        vernetzen(m)
        typen = sorted({e.typ for e in m.elements})
        zahl[s] = len(m.elements)
        r = druck(m, "Deckel", 1.0, 1.3 * fy, plastisch=True)
        info = r.info.get("plastizitaet") or {}
        check(f"{s}: {len(m.elements)} {'/'.join(typen)} - plastisch gerechnet, konvergiert, es fließt",
              info.get("konvergiert") and int(info.get("fliessend") or 0) > 0
              and set(typen) <= set(pl_typen()), str({k: info.get(k) for k in ("konvergiert", "fliessend")}))
    check("Fein hat die halbe Kantenlänge: 8-mal so viele Elemente wie Mittel",
          zahl.get("fein") == 8 * zahl.get("mittel", 0), str(zahl))
    # frei vernetzt: tet4 bzw. tet10
    soll = {"entwurf": {"tet4"}, "mittel": {"tet10"}, "fein": {"tet10"}}
    zahl = {}
    for s in es.STUFEN:
        m = pyramide()
        m.netz = es.setzen(m.netz, s)
        vernetzen(m)
        typen = {e.typ for e in m.elements}
        zahl[s] = len(m.elements)
        r = druck(m, "S0", 1.0, 1.2 * fy, plastisch=True)
        info = r.info.get("plastizitaet") or {}
        check(f"Pyramide {s}: {len(m.elements)} {'/'.join(sorted(typen))} - plastisch gerechnet, "
              "konvergiert, es fließt",
              typen == soll[s] and info.get("konvergiert") and int(info.get("fliessend") or 0) > 0,
              str({k: info.get(k) for k in ("konvergiert", "fliessend")}))
    check("Pyramide: Fein feiner als Mittel", zahl["fein"] > 4 * zahl["mittel"], str(zahl))
    # Kontakt und Fliessen zusammen: 2 fy auf das mittlere Viertel des Dachs
    # (gleichmaessig 1,3 fy ueber alles liess beide Bloecke ganz fliessen, und
    # die Kontakt-Iteration fand kein Gleichgewicht mehr - eine Frage der Last,
    # nicht der Stufe; gemessen 25.09.2026)
    m = zwei_bloecke()
    fuge(m)
    m.netz = es.setzen(m.netz, "mittel")
    vernetzen(m)
    r = druck(m, "Dach", 2.0, 2.0 * fy, plastisch=True, mitte=True)
    info = r.info.get("plastizitaet") or {}
    R = float(r.reactions[_knoten_z(m, 0.0), 2].sum())
    check("Kontakt und Plastizität zusammen (Mittel gewählt → Entwurf): konvergiert, es fließt",
          info.get("konvergiert") and int(info.get("fliessend") or 0) > 0 and es.stufe(m.netz) == "entwurf",
          str({k: info.get(k) for k in ("konvergiert", "fliessend")}))
    check("… das Fundament trägt die Last über die Fuge", abs(R - 0.5 * fy) < 1e-6 * fy,
          f"R = {R / 1e3:.1f} kN")
    _ = pl


def pl_typen():
    """Volumentypen mit Plastizitaet (plastizitaet.py, Operatoren je Typ)."""
    from statik3d.elements import solid as sl
    return set(sl.OPERATOREN)


# --------------------------------------------------------------------------
# 3) Rueckfrage beim Import (elementauswahl)
# --------------------------------------------------------------------------
def test_import_frage():
    from statik3d import elementauswahl as ea
    abw = ea.abweichungen({"ordnung": 1})
    text = ea.frage_text("Datei", abw)
    check("Frage wörtlich: „Die Datei gibt Entwurf (lineare Elemente) vor. Statik3D-Vorgabe: Mittel. "
          "Welche verwenden?“",
          text.startswith("Die Datei gibt Entwurf (lineare Elemente) vor.")
          and "Statik3D-Vorgabe: Mittel." in text and text.rstrip().endswith("Welche verwenden?"),
          text.replace("\n", " | "))
    check("eine Datei mit Mittel (ordnung 2) fragt nicht", ea.abweichungen({"ordnung": 2}) == [])
    check("… mit Sperre (Kontakt) ist die Vorgabe Entwurf: keine Frage nach der Stufe",
          ea.abweichungen({"ordnung": 1}, gesperrt=True) == [])
    n, z = ea.nach_import(Netzeinstellungen(), {"ordnung": 1}, datei_waehlen=True, datei="Datei")
    check("Antwort Datei-Vorgabe: Entwurf, sweep sauber", n.ordnung == 1 and n.stufe == "entwurf"
          and n.sweep == "sauber", z)
    n, z = ea.nach_import(Netzeinstellungen(), {"ordnung": 1}, datei_waehlen=False, datei="Datei")
    check("Antwort Statik3D-Vorgabe: Mittel", n.ordnung == 2 and n.stufe == "mittel", z)
    check("Protokollzeile nennt die Stufe", "Mittel" in z, z)


# --------------------------------------------------------------------------
# 4) Mit Hauptfenster (offscreen)
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
    w.error = lambda msg: FEHLER.append(str(msg))
    _FENSTER.update(w=w, app=app)
    return w, app


def _modell_ins_fenster(w, app, m):
    w.model = m
    w._MainWindow__init_defaults()
    w.analysis = None
    w.results = None
    w.refresh_all()
    app.processEvents()


def test_ribbon_und_neues_modell():
    es = _es()
    w, app = _fenster()
    netz = {b.text: b for b in w.ribbon.befehle if b.register == "Netz"}
    check("Ribbon Netz: „Elemente wählen…“ entfällt, „Elementübersicht…“ bleibt",
          "Elemente wählen…" not in netz and "Elementübersicht…" in netz, str(sorted(netz))[:140])
    check("Hinweis der Netzeinstellungen nennt die Elementstufe",
          "Entwurf" in netz["Netzeinstellungen…"].hinweis and "Fein" in netz["Netzeinstellungen…"].hinweis)
    check("Fenster ohne Methode maske_elementwahl", not hasattr(w, "maske_elementwahl"))
    w.new_model()
    app.processEvents()
    check("neues Modell: Stufe Mittel (Vorgabe), sweep sauber",
          es.stufe(w.model.netz) == "mittel" and w.model.netz.sweep == "sauber",
          f"{w.model.netz.stufe} {w.model.netz.ordnung} {w.model.netz.sweep}")


def test_maske():
    from PySide6 import QtCore
    es = _es()
    w, app = _fenster()
    m = wuerfel()
    m.netz = es.setzen(m.netz, "mittel")
    _modell_ins_fenster(w, app, m)
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    cb = mk._felder.get("elemente")
    check("Netzeinstellungen: Auswahlfeld „Elemente“, kein „Elementansatz“ mehr",
          cb is not None and "ordnung" not in mk._felder, ", ".join(mk._felder))
    eintraege = [cb.itemText(i) for i in range(cb.count())] if cb is not None else []
    check("… mit Entwurf / Mittel (Vorgabe) / Fein, alle wählbar",
          eintraege == ["Entwurf", "Mittel (Vorgabe)", "Fein"]
          and all(cb.model().item(i).isEnabled() for i in range(cb.count())), str(eintraege))
    check("… steht auf Mittel", cb is not None and cb.currentText() == "Mittel (Vorgabe)")
    check("… das erste Feld der Maske", list(mk._felder)[0] == "elemente", list(mk._felder)[:3])
    info = mk._felder["elemente_info"].text()
    check("Elemente und Zweck der Stufe stehen darunter", "tet10" in info and "für die Nachweise" in info, info)
    cb.setCurrentText("Fein")
    app.processEvents()
    info = mk._felder["elemente_info"].text()
    kl = mk._felder["kantenlaenge"].text()
    check("Fein gewählt: Text folgt (Bohrungen, Kerben, Ermüdung)", "für Bohrungen, Kerben und Ermüdung" in info,
          info)
    check("… die wirksame Kantenlänge ist halb (500 → 250 mm)", "250 mm" in kl, kl)
    mk.anwenden()
    app.processEvents()
    n = w.model.netz
    check("Übernehmen Fein: stufe fein, ordnung 2, sweep sauber",
          es.stufe(n) == "fein" and n.ordnung == 2 and n.sweep == "sauber", f"{n.stufe} {n.ordnung} {n.sweep}")
    check("… die gespeicherte Ziellänge bleibt (Fein halbiert beim Vernetzen)", abs(n.ziellaenge - 0.5) < 1e-12)
    # Vernetzen im Fenster: Fein halbiert, die Einstellung bleibt
    w._vernetzen([], [m.koerper["V1"]])
    app.processEvents()
    n_fein = len(m.elements)
    check("Vernetzen Fein: 64 hex20 (Kantenlänge 250 mm)", n_fein == 64
          and {e.typ for e in m.elements} == {"hex20"}, f"{n_fein} {sorted({e.typ for e in m.elements})}")
    check("… danach stehen die Netzeinstellungen wie vorher (Fein, 500 mm)",
          es.stufe(m.netz) == "fein" and abs(m.netz.ziellaenge - 0.5) < 1e-12 and m.netz.dichte == "eigene")
    check("… und die Teilung des Körpers (2 × 2 × 2; beim Vernetzen verdoppelt)",
          list(m.koerper["V1"].teilung) == [2, 2, 2], str(m.koerper["V1"].teilung))
    check("… das Protokoll nennt die halbe Kantenlänge", "halbe Kantenlänge" in w.log.toPlainText())
    m.netz = es.setzen(m.netz, "mittel")
    w._vernetzen([], [m.koerper["V1"]])
    check("Vernetzen Mittel: 8 hex20", len(m.elements) == 8 and {e.typ for e in m.elements} == {"hex20"},
          str(len(m.elements)))
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    mk._felder["elemente"].setCurrentText("Entwurf")
    mk.anwenden()
    app.processEvents()
    check("Übernehmen Entwurf: ordnung 1", es.stufe(w.model.netz) == "entwurf" and w.model.netz.ordnung == 1)
    w.undo()
    app.processEvents()
    check("Rückgängig nimmt die Stufe zurück", es.stufe(w.model.netz) == "mittel")
    w.maskenrand.schliessen()
    _ = QtCore


def test_maske_mit_kontakt():
    from PySide6 import QtCore
    es = _es()
    w, app = _fenster()
    m = zwei_bloecke()
    fuge(m)
    m.netz = es.setzen(m.netz, "mittel")     # etwa aus einer Datei
    _modell_ins_fenster(w, app, m)
    w.maske_netzeinstellungen()
    app.processEvents()
    mk = w.maskenrand.maske
    cb = mk._felder["elemente"]
    frei = [cb.model().item(i).isEnabled() for i in range(cb.count())]
    check("Kontakt: Mittel und Fein sichtbar, aber gesperrt", cb.count() == 3 and frei == [True, False, False],
          str(frei))
    tip = str(cb.itemData(1, QtCore.Qt.ToolTipRole) or "")
    check("… mit dem Hinweis am Eintrag", es.SPERRHINWEIS in tip, tip)
    check("… die Maske steht auf Entwurf", cb.currentText() == "Entwurf", cb.currentText())
    sperre = mk._felder.get("sperre")
    check("… und sagt es sichtbar in der Maske (mit Grund)",
          sperre is not None and es.SPERRHINWEIS in sperre.text() and "Kontaktbedingung Fuge" in sperre.text(),
          sperre.text() if sperre is not None else "-")
    mk.anwenden()
    app.processEvents()
    check("Übernehmen: Entwurf", es.stufe(w.model.netz) == "entwurf")
    # Vernetzen mit (aus der Datei) Mittel: Sperre im Protokoll, kein Abbruch
    m.netz = es.setzen(m.netz, "mittel")
    vorher = len(w.log.toPlainText())
    FEHLER.clear()
    w._vernetzen(list(m.flaechen.values()), list(m.koerper.values()))
    app.processEvents()
    neu = w.log.toPlainText()[vorher:]
    check("Vernetzen am Kontaktmodell mit Mittel: das Protokoll nennt die Sperre",
          es.SPERRHINWEIS in neu and "Entwurf" in neu, neu[:200].replace("\n", " | "))
    check("… Netz linear, Fuge getrennt, kein Fehler",
          {e.typ for e in m.elements} <= {"tet4", "hex8", "pent6", "pyr5"} and m.elements
          and m.kontaktbedingungen["Fuge"].ausgefuehrt and not FEHLER, str(FEHLER[:1]))
    check("… das Modell steht danach auf Entwurf", es.stufe(m.netz) == "entwurf")
    w.maskenrand.schliessen()


def test_import_im_fenster():
    from PySide6 import QtWidgets
    from statik3d.gui import dialogs as dg
    from tests.test_rfem6 import make_rf6
    es = _es()
    w, app = _fenster()
    tmp = tempfile.mkdtemp(prefix="statik3d_es_imp_")
    lager = [("Fest", (float("inf"),) * 6, (0,) * 6, None, [1])]
    f = make_rf6(os.path.join(tmp, "b.rf6"), nodes=[(0, 0, 0), (2, 0, 0)], lines=[[1, 2]],
                 members=[(1, None, None)], supports=lager)
    fragen = []
    alt_fk = w._fragen_knoepfe
    alt_open = QtWidgets.QFileDialog.getOpenFileName
    alt_exec = dg.ImportDialog.exec
    w._fragen_knoepfe = lambda titel, text, ja="Ja", nein="Abbrechen", **k: (fragen.append(text), False)[1]
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (f, ""))
    dg.ImportDialog.exec = lambda self: 1
    try:
        w.import_file()
        app.processEvents()
        # mesh.xml gibt keine Ordnung vor, nur die Flaechenform: gefragt wird
        # nur danach, die Stufe ist die Statik3D-Vorgabe
        check("Import: eine Rückfrage, nur nach der Flächenform (die Datei gibt keine Stufe vor)",
              len(fragen) == 1 and "Flächen Vierecke" in fragen[0] and "Entwurf" not in fragen[0],
              str(fragen)[:160])
        check("Statik3D-Vorgabe gewählt: Stufe Mittel, sweep sauber",
              es.stufe(w.model.netz) == "mittel" and w.model.netz.sweep == "sauber",
              w.model.netz.beschreibung())
    finally:
        w._fragen_knoepfe = alt_fk
        QtWidgets.QFileDialog.getOpenFileName = alt_open
        dg.ImportDialog.exec = alt_exec
    from statik3d.gui import elementmasken as elm
    m = zwei_bloecke()
    fuge(m)
    p = os.path.join(tmp, "kontakt.rf6")
    open(p, "wb").close()
    zeile = elm.elementwahl_nach_import(w, m, p)
    check("Import eines Kontaktmodells: Entwurf mit Hinweis in der Protokollzeile",
          es.stufe(m.netz) == "entwurf" and es.SPERRHINWEIS in zeile, zeile)


def main():
    import faulthandler
    faulthandler.dump_traceback_later(1200, exit=True)
    for t in (test_stufen_und_texte, test_stufe_und_setzen, test_laden_und_speichern, test_beschreibung,
              test_fein_halbe_kantenlaenge, test_sperre, test_kontakt_in_jeder_stufe,
              test_plastizitaet_in_jeder_stufe, test_import_frage, test_ribbon_und_neues_modell,
              test_maske, test_maske_mit_kontakt, test_import_im_fenster):
        print(f"\n--- {t.__name__} ---")
        try:
            t()
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
    sys.exit(main())
