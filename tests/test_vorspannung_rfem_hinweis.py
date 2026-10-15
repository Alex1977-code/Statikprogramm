"""Hinweis: Vorspannung aus RFEM übernommen – prüfen (seit 15.10.2026).

Nachtrag des Anwenders vom 15.10.2026, woertlich: „beim import des modells
und der lastfälle einen hinweis an den user, dass der wert von rfem übernommen
wurde und in statik3d zu prüfen und ggf anzupassen ist“.

Je Vorspannungswert ein gebuendelter Hinweis, etwa „Vorspannung 952 kN an
S1–S16 in 129 Lastfällen aus RFEM übernommen (als eingeprägte Dehnung,
E = 170 000 N/mm², α = 1,0e-5 1/K; …) – in Statik3D prüfen und ggf. als
Anfangsvorspannung (Pressenkraft) oder Endvorspannung anpassen“. Er steht im
Importprotokoll, als Importhinweis am Modell, beim Oeffnen der Datei im
Protokoll und als Vermerk „aus RFEM übernommen – prüfen“ in der Lastfallmaske
und der Lasttabelle der betroffenen Lastfaelle. Der Hinweis „… ergibt nach
elastischer Verkürzung X kN …“ (13./14.10.2026) geht darin auf.

Geprueft an einer synthetischen RFEM-Datei (Vorspannung 120 kN in zwei
Lastfaellen, 150 kN in einem dritten, ein Lastfall ohne) und, wenn die Datei
da ist, am Drehlager (nur Import, nichts gerechnet).

Nachtrag vom 15.10.2026 fuer aeltere Modelle: eine Datei, die vor dem
13.10.2026 aus RFEM uebernommen wurde, traegt keinen Importhinweis zur
Vorspannung und kein gespeichertes Merkmal an ihren ΔT-Lasten. Beim Oeffnen
leitet das Programm die Vorspannungen aus ΔT ab (TempLoad.vorspann_werte) und
gibt denselben Hinweis und denselben Vermerk, mit „aus ΔT abgeleitet“ in der
Klammer; die Datei aendert sich nicht. Geprueft an einer so nachgestellten
synthetischen Datei und, mit STATIK3D_DREHLAGER_JSON, am gespeicherten
Drehlager (nur lesend).

Aufruf:  python -m tests.test_vorspannung_rfem_hinweis
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_rfem_hinweis_"), "einstellungen.json")

RESULTS = []
_FENSTER = {}
TMP = tempfile.mkdtemp(prefix="statik3d_rfem_hinweis_dat_")

ENDE = " – in Statik3D prüfen und ggf. als Anfangsvorspannung (Pressenkraft) oder Endvorspannung anpassen"
T120 = ("Vorspannung 120 kN an S1–S2 in 2 Lastfällen aus RFEM übernommen (als eingeprägte Dehnung, "
        "E = 210 000 N/mm², α = 1,2e-5 1/K; nach elastischer Verkürzung 80 kN)" + ENDE)
T150 = ("Vorspannung 150 kN an S1 in 1 Lastfall aus RFEM übernommen (als eingeprägte Dehnung, "
        "E = 210 000 N/mm², α = 1,2e-5 1/K; nach elastischer Verkürzung 50 kN)" + ENDE)
VERMERK = "aus RFEM übernommen – prüfen"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:84s} {detail}")
    return ok


def _rf6():
    """Drei Zugstaebe in Reihe zwischen zwei festen Punkten (gleiches E A).
    LF1 und LF2: 120 kN in S1 und S2 -> X = 2/3·120 = 80 kN; LF3: 150 kN in
    S1 -> X = 150/3 = 50 kN; LF4 ohne Vorspannung."""
    from tests.test_rfem6 import INF, make_rf6
    return make_rf6(os.path.join(TMP, "anker.rf6"),
                    nodes=[(0, 0, 0), (4, 0, 0), (8, 0, 0), (12, 0, 0)],
                    lines=[[1, 2], [2, 3], [3, 4]],
                    members=[(1, None, None, "MemberImplTension"), (2, None, None, "MemberImplTension"),
                             (3, None, None, "MemberImplTension")],
                    supports=[("Fest", (INF,) * 6, (0,) * 6, None, [1, 4])],
                    load_cases=[("Vorspannung A", 1, 0.0), ("Vorspannung B", 2, 0.0), ("Einzeln", 3, 0.0),
                                ("Wind", 4, 0.0)],
                    prestress=[(1, [1, 2], 120e3), (2, [1, 2], 120e3), (3, [1], 150e3)])


def test_import():
    print("\n--- Synthetische RFEM-Datei: Importprotokoll und Importhinweis ---")
    from statik3d.importers import rfem6_db as R6
    log = []
    m = R6.read_rf6(_rf6(), log=log)
    zeilen = [z.strip() for z in log if "aus RFEM übernommen" in z]
    for z in zeilen:
        print(f"     {z}")
    check("Protokoll: je Vorspannungswert ein Hinweis (120 kN in LF1, LF2; 150 kN in LF3)", len(zeilen) == 2,
          str(len(zeilen)))
    check(f"Protokoll: Wortlaut 120 kN „{T120[:60]}…“", any(z == "HINWEIS: " + T120 for z in zeilen))
    check("Protokoll: Wortlaut 150 kN", any(z == "HINWEIS: " + T150 for z in zeilen))
    check("der alte Hinweis „… – in Endvorspannung umwandeln?“ ist darin aufgegangen",
          not any("umwandeln?" in z for z in log), str([z for z in log if "umwandeln?" in z][:1]))
    h = {round(x["N0"]): x for x in m.importhinweise if x.get("art") == "vorspannung"}
    check("Importhinweise am Modell: dieselben Texte, Stäbe und Lastfälle",
          h.get(120000, {}).get("text") == T120 and h.get(150000, {}).get("text") == T150
          and h[120000].get("faelle") == ["LF1", "LF2"] and h[120000].get("objekte") == ["S1", "S2"],
          str({k: (v.get("faelle"), v.get("objekte")) for k, v in h.items()}))
    from statik3d import vorspannkraft as vk
    p = vk.rfem_pruefen(m)
    check("betroffene Lastfälle: LF1, LF2, LF3 (nicht LF4)", sorted(p) == ["LF1", "LF2", "LF3"], str(sorted(p)))
    pfad = os.path.join(TMP, "anker.json")
    m.save(pfad)
    return pfad


def test_laden(pfad):
    print("\n--- Laden der Datei: die Hinweise im Protokoll, die Datei bleibt bitgleich ---")
    from statik3d.model import Model
    m = Model.load(pfad)
    z = [s for s in getattr(m, "_ladehinweise", []) if "aus RFEM übernommen" in s]
    check("beim Laden: beide Hinweise in den Ladehinweisen", T120 in z and T150 in z, str(z))
    # die erste Datei nach dem Import ergaenzt beim Laden Querschnittswerte (W_el,
    # W_pl des Rundstabs) - verglichen wird darum ab dem zweiten Speichern
    p2 = os.path.join(TMP, "anker2.json")
    m.save(p2)
    p2b = os.path.join(TMP, "anker2b.json")
    m2 = Model.load(p2)
    m2.save(p2b)
    with open(p2, "rb") as f1, open(p2b, "rb") as f2:
        check("Laden und Speichern bitgleich (der Hinweis ändert die Datei nicht)", f1.read() == f2.read())
    check("… die gespeicherten Hinweistexte bleiben, wie sie waren",
          [h.get("text") for h in m2.importhinweise] == [h.get("text") for h in Model.load(pfad).importhinweise])
    # Ein Hinweis in der Form vom 13./14.10.2026 (ohne Umrechnung und Grund):
    # beim Laden steht er in der neuen Form im Protokoll
    alt = Model.load(pfad)
    for x in alt.importhinweise:
        for k in ("umrechnung", "grund"):
            x.pop(k, None)
        x["text"] = "Anfangsvorspannung 120 kN ergibt nach elastischer Verkürzung 80 kN – in Sollkraft umwandeln?"
    p3 = os.path.join(TMP, "anker_alt.json")
    alt.save(p3)
    z3 = [s for s in getattr(Model.load(p3), "_ladehinweise", []) if "aus RFEM übernommen" in s]
    check("Hinweis aus einer Datei vom 14.10.2026: beim Laden in der neuen Form", T120 in z3, str(z3))


ABGELEITET = ("Vorspannung 120 kN an S1–S2 in 2 Lastfällen aus RFEM übernommen (als eingeprägte Dehnung, "
              "E = 210 000 N/mm², α = 1,2e-5 1/K, aus ΔT abgeleitet; die Kraft nach elastischer Verkürzung "
              "folgt nach der ersten Rechnung eines Lastfalls nur mit der Vorspannung: beim Öffnen nicht "
              "gerechnet)" + ENDE)


def test_alte_datei(pfad):
    print("\n--- Datei von vor dem 13.10.2026 (ohne Importhinweis und Merkmal): aus ΔT abgeleitet ---")
    from statik3d.model import Model
    from statik3d import vorspannkraft as vk
    m = Model.load(pfad)
    m.importhinweise = [h for h in m.importhinweise if h.get("art") != "vorspannung"]
    # die Quelle setzt der Import ueber statik3d.importers (Oberflaeche), read_rf6 allein nicht
    m.meta["quelle"] = os.path.join(TMP, "anker.rf6")
    for lc in m.load_cases.values():
        for t in lc.temp_loads:
            t.aus_vorspannung, t.vorspann_E, t.vorspann_alpha = 0.0, 0.0, 0.0
    alt = os.path.join(TMP, "anker_vor_1310.json")
    m.save(alt)
    alt2 = os.path.join(TMP, "anker_vor_1310_b.json")
    Model.load(alt).save(alt2)          # Querschnittswerte einmal ergaenzt (wie oben)
    m2 = Model.load(alt2)
    z = [s for s in getattr(m2, "_ladehinweise", []) if "aus RFEM übernommen" in s]
    for s in z:
        print(f"     {s}")
    check("beim Öffnen: je Wert ein Hinweis (120 kN und 150 kN)", len(z) == 2, str(len(z)))
    check("Wortlaut 120 kN mit „aus ΔT abgeleitet“", ABGELEITET in z, str(z[:1]))
    p = vk.rfem_pruefen(m2)
    check("Vermerk: LF1, LF2, LF3 (nicht LF4)", sorted(p) == ["LF1", "LF2", "LF3"], str(sorted(p)))
    check("kein gespeicherter Importhinweis entsteht", not [h for h in m2.importhinweise
                                                            if h.get("art") == "vorspannung"])
    alt3 = os.path.join(TMP, "anker_vor_1310_c.json")
    m2.save(alt3)
    with open(alt2, "rb") as f1, open(alt3, "rb") as f2:
        check("Datei von vor dem 13.10.2026: Öffnen und Speichern bitgleich", f1.read() == f2.read())
    vk.in_sollkraft_umwandeln(m2, faelle=["LF1"], kraft=120e3)
    check("nach dem Umwandeln von LF1: Vermerk nur noch LF2, LF3", sorted(vk.rfem_pruefen(m2)) == ["LF2", "LF3"],
          str(sorted(vk.rfem_pruefen(m2))))
    # ohne RFEM als Quelle: eine Abkuehlung eines Zugstabs ist kein Hinweis „aus RFEM“
    m3 = Model.load(alt2)
    m3.meta["quelle"] = ""
    eigen = os.path.join(TMP, "eigen.json")
    m3.save(eigen)
    z3 = [s for s in getattr(Model.load(eigen), "_ladehinweise", []) if "aus RFEM übernommen" in s]
    check("ein Modell ohne RFEM-Quelle bekommt keinen Hinweis", not z3, str(z3[:1]))
    return alt2


def test_drehlager_gespeichert():
    pfad = os.environ.get("STATIK3D_DREHLAGER_JSON", "")
    if not pfad or not os.path.exists(pfad):
        print("\n--- gespeichertes Drehlager: STATIK3D_DREHLAGER_JSON nicht gesetzt, übersprungen ---")
        return
    print(f"\n--- gespeichertes Drehlager {os.path.basename(pfad)}: nur lesend ---")
    from statik3d.model import Model
    from statik3d import vorspannkraft as vk
    m = Model.load(pfad)
    z = [s for s in getattr(m, "_ladehinweise", []) if "aus RFEM übernommen" in s]
    for s in z:
        print(f"     {s}")
    soll = {952: os.environ.get("STATIK3D_DREHLAGER_952", "128"), 805: os.environ.get("STATIK3D_DREHLAGER_805", "293")}
    for N, n in soll.items():
        a = (f"Vorspannung {N} kN an S1–S16 in {n} Lastfällen aus RFEM übernommen (als eingeprägte Dehnung, "
             f"E = 170 000 N/mm², α = 1,0e-5 1/K, aus ΔT abgeleitet; die Kraft nach elastischer Verkürzung "
             "folgt nach der ersten Rechnung eines Lastfalls nur mit der Vorspannung:")
        check(f"Drehlager gespeichert: {N} kN an S1–S16 in {n} Lastfällen, aus ΔT abgeleitet",
              any(s.startswith(a) and s.endswith(ENDE) for s in z), str(z)[:300])
    check("Drehlager gespeichert: genau zwei Hinweise", len(z) == 2, str(len(z)))
    p = vk.rfem_pruefen(m)
    check(f"Drehlager gespeichert: Vermerk in {int(soll[952]) + int(soll[805])} Lastfällen",
          len(p) == int(soll[952]) + int(soll[805]), str(len(p)))
    kopie = os.path.join(TMP, "drehlager_gespeichert.json")
    m.save(kopie)
    with open(pfad, "rb") as f1, open(kopie, "rb") as f2:
        check("Drehlager gespeichert: Öffnen und Speichern bitgleich", f1.read() == f2.read())
    os.remove(kopie)


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
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def test_oberflaeche(pfad):
    print("\n--- Oberfläche: Protokoll beim Öffnen, Vermerk in Lasttabelle und Lastfallmaske ---")
    w, app = _fenster()
    w.modell_laden(pfad, fragen=False)
    app.processEvents()
    log = w.log.toPlainText()
    check("Protokoll beim Öffnen: „Hinweis: Vorspannung 120 kN an S1–S2 … anpassen“", ("Hinweis: " + T120) in log,
          log[-300:])
    w.refresh_all()
    app.processEvents()
    zeilen = [list(map(str, r)) for r in w.tbl_last.modell.zeilen]
    mit = sorted({r[1] for r in zeilen if any(VERMERK in c for c in r)})
    check("Lasttabelle: Vermerk in den Zeilen von LF1, LF2, LF3", mit == ["LF1", "LF2", "LF3"], str(mit))
    for lf, soll in (("LF1", True), ("LF4", False)):
        w._objektmaske("lastfall", lf)
        app.processEvents()
        mk = w.maskenrand.maske
        felder = getattr(mk, "_felder", {}) or {}
        texte = " ".join(str(getattr(x, "text", lambda: "")() or "") for x in felder.values())
        ok = ("rfem_pruefen" in felder and VERMERK in texte) if soll else "rfem_pruefen" not in felder
        check(f"Lastfallmaske {lf}: " + ("Vermerk „aus RFEM übernommen – prüfen“" if soll else "kein Vermerk"),
              ok, texte[-160:] if soll else str(list(felder)))
    # umgewandelt: der Vermerk geht, die anderen Lastfaelle behalten ihn
    from statik3d import vorspannkraft as vk
    vk.in_sollkraft_umwandeln(w.model, faelle=["LF1"], kraft=120e3)
    w.refresh_all()
    app.processEvents()
    zeilen = [list(map(str, r)) for r in w.tbl_last.modell.zeilen]
    mit = sorted({r[1] for r in zeilen if any(VERMERK in c for c in r)})
    check("nach dem Umwandeln von LF1: Vermerk nur noch in LF2 und LF3", mit == ["LF2", "LF3"], str(mit))


def test_drehlager():
    rf6 = os.environ.get("STATIK3D_DREHLAGER_RF6") or os.path.join(
        os.path.expanduser("~"), "Desktop", "Statik3D", "RFEM_Modelle", "Lindaunis", "Drehlager_V15_4_export.rf6")
    if not os.path.exists(rf6):
        print(f"\n--- Drehlager: {rf6} nicht vorhanden, übersprungen ---")
        return
    print("\n--- Drehlager: Import (nur lesend) ---")
    from statik3d.importers import rfem6_db as R6
    log = []
    R6.read_rf6(rf6, log=log)
    zeilen = [z.strip() for z in log if "aus RFEM übernommen" in z]
    for z in zeilen:
        print(f"     {z}")
    a952 = ("HINWEIS: Vorspannung 952 kN an S1–S16 in 129 Lastfällen aus RFEM übernommen (als eingeprägte "
            "Dehnung, E = 170 000 N/mm², α = 1,0e-5 1/K; die Kraft nach elastischer Verkürzung folgt nach der "
            "ersten Rechnung eines Lastfalls nur mit der Vorspannung:")
    a805 = "HINWEIS: Vorspannung 805 kN an S1–S16 in 293 Lastfällen aus RFEM übernommen (als eingeprägte Dehnung"
    check("Drehlager: 952 kN an S1–S16 in 129 Lastfällen, Wortlaut", any(z.startswith(a952) and z.endswith(ENDE)
                                                                         for z in zeilen), str(zeilen[:1]))
    check("Drehlager: 805 kN an S1–S16 in 293 Lastfällen", any(z.startswith(a805) and z.endswith(ENDE)
                                                             for z in zeilen))
    check("Drehlager: genau zwei Hinweise (je Vorspannungswert einer)", len(zeilen) == 2, str(len(zeilen)))


def main():
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    pfad = None
    for t in (test_import, test_laden, test_alte_datei, test_oberflaeche, test_drehlager,
              test_drehlager_gespeichert):
        try:
            if t is test_import:
                pfad = t()
            elif t in (test_laden, test_alte_datei, test_oberflaeche):
                t(pfad)
            else:
                t()
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {type(ex).__name__}: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    sys.stdout.flush()
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    rc = main()
    os._exit(rc)
