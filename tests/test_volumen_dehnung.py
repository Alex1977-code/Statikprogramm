"""
Volumennachweis bei plastischer Rechnung ueber die plastische Hauptdehnung
(Entscheidung des Anwenders vom 13.10.2026).

Wortlaut: „Danach Volumennachweis plastisch über die plastische Hauptdehnung
am Integrationspunkt, Grenzwert parametrierbar (Standard 5 % nach EN 1993-1-5
Anh. C / EN 1993-1-14). Schrauben, Ankerstäbe und Gewindeteile weiter über
Kraft bzw. Spannung nach EN 1993-1-8, nicht über Dehnung. Nullmaterial- und
Krafteinleitungskörper vom Nachweis ausnehmen und als ausgenommen
ausweisen.“

Bis zum 13.10.2026 stand eine plastische Rechnung im Volumennachweis als
„nicht bewertet – plastische Rechnung“ (tests/test_plastisch_nachweise.py),
davor mit der Spannung als Zahlenwert.

Prueffall: zwei getrennte Zugstaebe aus hex8 mit 100 x 100 mm Querschnitt,
Querdehnung frei gelagert, auf der Stirnseite die Zugspannung 1,2 f_y
(282 N/mm2): „Stab“ aus drei Elementen (300 mm, f_y = 235) und „Einleitung“
aus einem (100 mm, Werkstoff „Hilf“, f_y = 200 N/mm2). Getrennt, weil zwei
verbundene Werkstoffe verschieden fliessen und sich an der Fuge die
Querdehnung gegenseitig behindern - dann gilt die Formel nicht mehr (erster
Entwurf dieser Pruefung: bis 31,9 % Abweichung an den Punkten der Fuge).
Jeder Stab ist homogen, die Spannung statisch bestimmt. Mit linearer Verfestigung
E_t = r E, H = E r/(1 - r) (r = 0,01) ist die geschlossene Loesung

    eps_p,x = (sigma - f_y)/H,   eps_p,y = eps_p,z = -eps_p,x/2,
    eps_p,1 = eps_p,x,           eta = eps_p,1 / Grenzwert.

Stab: 47/2121,2 = 2,2157 %, Einleitung: 82/2121,2 = 3,8657 %.

Geprueft: die abgelegten Dehnungen je Integrationspunkt, eps_p,1 und eta
gegen die Formel, Ort und Bauteil, der einstellbare Grenzwert (gespeichert,
geladen, in der Maske), der ausgenommene Koerper und Werkstoff (Schalter nur
vom Anwender, nie nach dem Namen), Zonen nur berichtet, eine alte
Ergebnisdatei und eine Ueberlagerung („nicht bewertet“ mit Grund), Bericht und
Oberflaeche, und die elastische Rechnung, die bleibt, wie sie war.

Aufruf:  python -m tests.test_volumen_dehnung
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_volumen_dehnung_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d import solver, plastizitaet as pl  # noqa: E402
from statik3d.model import Material, Model, Volumenkoerper  # noqa: E402

RESULTS = []
_FENSTER = {}
FY, FY_H, L, B, H_ = 235e6, 200e6, 0.4, 0.1, 0.1
SIGMA = 1.2 * FY
R = 0.01
H_MOD = 210e9 * R / (1.0 - R)
EPS_S = (SIGMA - FY) / H_MOD
EPS_H = (SIGMA - FY_H) / H_MOD


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:78s} {detail}")
    return bool(ok)


def _fenster():
    if "w" in _FENSTER:
        return _FENSTER["w"], _FENSTER["app"]
    from PySide6 import QtWidgets
    from statik3d.gui.main import MainWindow
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    app.processEvents()
    w._fragen = lambda *a, **k: True
    w._fragen_knoepfe = lambda *a, **k: True
    w.fehler_liste = []
    from tests.meldungen import abfangen
    w.meldungen = abfangen(w, w.fehler_liste, protokoll=True)
    _FENSTER.update(w=w, app=app)
    return w, app


def _zugstab(plastisch: bool = True, sigma: float = SIGMA):
    from tests import pruefkoerper as pk
    from statik3d.mesher import grid_box
    m = Model("Zugstaebe")
    m.add_material(Material("S", 210e9, 0.3, 7850.0, fy=FY))
    m.add_material(Material("Hilf", 210e9, 0.3, 7850.0, fy=FY_H))
    grid_box(m, "S", 0.3, B, H_, 3, 1, 1, origin=(0.0, 0.0, 0.0))
    grid_box(m, "Hilf", 0.1, B, H_, 1, 1, 1, origin=(0.0, 0.3, 0.0))
    for i in range(3):
        m.elements[i].group = "Stab"
    m.elements[3].group = "Einleitung"
    m.koerper["Stab"] = Volumenkoerper("Stab", [], material="S", elemente=[0, 1, 2])
    m.koerper["Einleitung"] = Volumenkoerper("Einleitung", [], material="Hilf", elemente=[3])
    X = np.asarray(m.nodes, float)
    for n in range(m.nn):
        d = [k for k, wert in ((0, 0.0), (2, 0.0)) if abs(X[n, k] - wert) < 1e-9]
        if abs(X[n, 1]) < 1e-9 or abs(X[n, 1] - 0.3) < 1e-9:
            d.append(1)
        if d:
            m.fix(int(n), sorted(d))
    ende = {"S": 0.3, "Hilf": 0.1}
    seiten = [(i, kn) for i, kn in pk.randseiten(m, lambda P: True)
              if np.all(np.abs(np.asarray(m.nodes)[kn, 0] - ende[m.elements[i].mat]) < 1e-9)]
    pk.spannung_auf_seiten(m, seiten, lambda x: (sigma, 0.0, 0.0))
    m.add_volumenbereich("B1", list(range(4)))
    m.add_combination("GZT1", {list(m.load_cases)[0]: 1.0}, "ULS")
    if plastisch:
        m.plastizitaet = pl.Plastizitaet(an=True, verfestigung=R, laststufen=2, iterationen=40,
                                         toleranz=1e-9)
    an = solver.solve_all(m, design=True)
    return m, an


def _neu(m, an):
    from statik3d.ec3 import volumen as vol
    an.volumen = vol.check_volumen(m, an)
    return an.volumen.bereiche["B1"]


def test_geschlossen(fall):
    m, an = fall
    r = an.combinations["GZT1"]
    ipd = (r.info or {}).get("ip_dehnungen")
    check("Vorbereitung: plastisch gerechnet, alle vier Elemente fließen",
          bool(r.info.get("plastizitaet")) and len(r.info.get("plastisch") or {}) == 4,
          f"{len(r.info.get('plastisch') or {})} fließen")
    check("Ergebnis trägt die plastischen Dehnungen je Integrationspunkt (ip_dehnungen)",
          isinstance(ipd, dict) and bool(ipd), str(list((ipd or {}).keys())))
    if not ipd:
        return
    ids, eps, orte = next(iter(ipd.values()))
    ids = np.asarray(ids).tolist()
    soll = np.array([EPS_H if i == 3 else EPS_S for i in ids])
    ex = np.asarray(eps)[:, :, 0]
    ey = np.asarray(eps)[:, :, 1]
    check("… ε_p,x an jedem Punkt = (σ − f_y)/H (Stab 2,2157 %, Einleitung 3,8657 %)",
          np.allclose(ex, soll[:, None], rtol=1e-6, atol=0.0),
          f"max Abweichung {np.max(np.abs(ex - soll[:, None]) / soll[:, None]) * 100:.6f} %")
    check("… ε_p,y = −ε_p,x/2 (plastisch volumentreu)",
          np.allclose(ey, -0.5 * soll[:, None], rtol=1e-6, atol=0.0))
    k3 = ids.index(3)
    o3 = np.asarray(orte)[k3]
    check("… die Orte der Punkte liegen im Element (Element 4: x 0 … 100, y 300 … 400 mm)",
          np.all((o3[:, 0] > -1e-9) & (o3[:, 0] < 0.1 + 1e-9))
          and np.all((o3[:, 1] > 0.3 - 1e-9) & (o3[:, 1] < 0.4 + 1e-9))
          and np.all((o3[:, 2] > -1e-9) & (o3[:, 2] < 0.1 + 1e-9)),
          str(np.round(o3[:2] * 1e3, 1).tolist()))
    c = an.volumen.bereiche["B1"]
    check("Volumennachweis: Kriterium plastische Hauptdehnung",
          getattr(c, "kriterium", "") == "dehnung" and not getattr(c, "nicht_bewertet", ""),
          f"{getattr(c, 'kriterium', None)!r} {c.status()!r}")
    check("… ε_p,1 = 3,8657 % (Einleitung), η = ε_p,1/5 % = 0,7731",
          abs(c.eps_p1 - EPS_H) <= 1e-6 * EPS_H and abs(c.util - EPS_H / 0.05) <= 1e-6,
          f"ε_p,1 {c.eps_p1 * 100:.4f} %, η {c.util:.4f}")
    check("… Grenzwert 5 % (Vorgabe), Status erfüllt",
          abs(c.eps_grenze - 0.05) < 1e-15 and c.status() == "erfüllt", f"{c.eps_grenze} {c.status()}")
    check("… Ort: Element 4, ein Integrationspunkt, Bauteil „Einleitung“, Werkstoff „Hilf“",
          c.element == 3 and c.ip >= 0 and c.bauteil == "Einleitung" and "Hilf" in c.werkstoff_ort
          and 0.3 - 1e-9 <= c.ort[1] <= 0.4 + 1e-9,
          f"El {c.element + 1} IP {c.ip + 1} {c.bauteil} {c.werkstoff_ort} {np.round(np.asarray(c.ort) * 1e3, 1)}")
    zeile = [z for z in an.volumen.table() if z[0] == "B1"][0]
    check("… Tabelle: keine Spannung, η und Status",
          zeile[4] == "–" and zeile[7] == f"{EPS_H / 0.05:.3f}" and zeile[-1] == "erfüllt", str(zeile))
    s = an.volumen.summary()
    check("… Zusammenfassung nennt ε_p,1, Grenzwert und Bauteil, kein „nicht bewertet“",
          "ε_p,1" in s and "3.866 %" in s and "5.0 %" in s and "Einleitung" in s
          and "nicht bewertet" not in s and "e-0" not in s, s)


def test_grenzwert(fall):
    m, an = fall
    vb = m.volumenbereiche["B1"]
    vb.eps_grenze = 0.03
    c = _neu(m, an)
    check("Grenzwert 3 %: η = 3,8657/3 = 1,2886, NICHT erfüllt",
          abs(c.util - EPS_H / 0.03) <= 1e-6 and c.status() == "NICHT erfüllt" and abs(c.eps_grenze - 0.03) < 1e-15,
          f"η {c.util:.4f} {c.status()}")
    pfad = os.path.join(tempfile.mkdtemp(prefix="statik3d_vd_"), "m.json")
    m.koerper["Einleitung"].nachweis_ausnehmen = True
    m.materials["Hilf"].nachweis_ausnehmen = True
    m.save(pfad)
    m2 = Model.load(pfad)
    check("Grenzwert und Schalter werden gespeichert und geladen",
          abs(m2.volumenbereiche["B1"].eps_grenze - 0.03) < 1e-15
          and m2.koerper["Einleitung"].nachweis_ausnehmen is True
          and m2.materials["Hilf"].nachweis_ausnehmen is True
          and m2.koerper["Stab"].nachweis_ausnehmen is False and m2.materials["S"].nachweis_ausnehmen is False)
    m.koerper["Einleitung"].nachweis_ausnehmen = False
    m.materials["Hilf"].nachweis_ausnehmen = False
    alt = Model.load(pfad)
    roh = alt.to_dict()
    for x in roh.get("volumenbereiche", []):
        x.pop("eps_grenze", None)
    for v in roh.get("materials", {}).values():
        v.pop("nachweis_ausnehmen", None)
    for x in roh.get("koerper", []):
        x.pop("nachweis_ausnehmen", None)
    alt = Model.from_dict(roh)
    check("Datei ohne die Felder: Grenzwert 5 %, nichts ausgenommen",
          abs(alt.volumenbereiche["B1"].eps_grenze - 0.05) < 1e-15
          and not any(mt.nachweis_ausnehmen for mt in alt.materials.values())
          and not any(k.nachweis_ausnehmen for k in alt.koerper.values()))
    vb.eps_grenze = 0.0
    c = _neu(m, an)
    check("Grenzwert 0: nicht geführt mit Grund, kein η",
          c.status() == "nicht geführt" and "Grenzwert" in c.fehler and c.util == 0.0, repr(c.fehler))
    vb.eps_grenze = 0.03


def test_ausnehmen(fall):
    m, an = fall
    m.volumenbereiche["B1"].eps_grenze = 0.03
    m.koerper["Einleitung"].nachweis_ausnehmen = True
    c = _neu(m, an)
    check("Körper „Einleitung“ ausgenommen: maßgebend der Stab, η = 2,2157/3 = 0,7386, erfüllt",
          abs(c.util - EPS_S / 0.03) <= 1e-6 and c.bauteil == "Stab" and c.status() == "erfüllt",
          f"η {c.util:.4f} {c.bauteil} {c.status()}")
    check("… als ausgenommen ausgewiesen, mit Namen und Zahl",
          c.ausgenommen == ["Körper Einleitung"] and c.n_ausgenommen == 1, f"{c.ausgenommen} {c.n_ausgenommen}")
    s = an.volumen.summary()
    zeilen = an.volumen.table()
    check("… Zusammenfassung und Tabelle nennen den ausgenommenen Körper",
          "ausgenommen" in s and "Einleitung" in s
          and any(str(z[0]).startswith("B1 (ausgenommen") and "Einleitung" in str(z[-1]) for z in zeilen),
          f"{s} | {[z for z in zeilen if 'ausgenommen' in str(z)]}")
    m.koerper["Einleitung"].nachweis_ausnehmen = False
    m.materials["Hilf"].nachweis_ausnehmen = True
    c = _neu(m, an)
    check("Werkstoff „Hilf“ ausgenommen: ebenso der Stab maßgebend, „Werkstoff Hilf“ ausgewiesen",
          abs(c.util - EPS_S / 0.03) <= 1e-6 and c.ausgenommen == ["Werkstoff Hilf"] and c.n_ausgenommen == 1,
          f"η {c.util:.4f} {c.ausgenommen}")
    m.koerper["Stab"].nachweis_ausnehmen = True
    c = _neu(m, an)
    check("alles ausgenommen: Status „ausgenommen“, kein η, im Gesamturteil weder erfüllt noch offen",
          c.status() == "ausgenommen" and c.util == 0.0 and c.n_ausgenommen == 4
          and "NICHT" not in an.volumen.summary(), f"{c.status()} {an.volumen.summary()}")
    m.koerper["Stab"].nachweis_ausnehmen = False
    m.materials["Hilf"].nachweis_ausnehmen = False
    # nie nach dem Namen: ein Werkstoff „Nullmaterial“ mit ρ = 0 und ein
    # Körper „Krafteinleitung“ bleiben im Nachweis, bis der Anwender schaltet
    m.add_material(Material("Nullmaterial", 210e9, 0.3, 0.0, fy=FY_H))
    m.elements[3].mat = "Nullmaterial"
    m.koerper["Krafteinleitung"] = m.koerper.pop("Einleitung")
    m.koerper["Krafteinleitung"].name = "Krafteinleitung"
    c = _neu(m, an)
    check("nie nach dem Namen: „Nullmaterial“ (ρ = 0) und „Krafteinleitung“ bleiben im Nachweis",
          not c.ausgenommen and c.bauteil == "Krafteinleitung"
          and m.materials["Nullmaterial"].nachweis_ausnehmen is False,
          f"{c.ausgenommen} {c.bauteil}")
    m.elements[3].mat = "Hilf"
    del m.materials["Nullmaterial"]
    m.koerper["Einleitung"] = m.koerper.pop("Krafteinleitung")
    m.koerper["Einleitung"].name = "Einleitung"
    _neu(m, an)


def test_zone(fall):
    """Elemente in Zonen auffaelliger Stellen sind auch hier nur berichtet."""
    from statik3d import spitzenanzeige as sa
    m, an = fall
    m.volumenbereiche["B1"].eps_grenze = 0.05
    alt = sa.nachweis_zonen
    sa.nachweis_zonen = lambda model, ergebnisse: {k: {3} for k in ergebnisse}
    try:
        c = _neu(m, an)
    finally:
        sa.nachweis_zonen = alt
    check("Zone um Element 4: nur berichtet mit ε_p,1 3,8657 %, Nachweis außerhalb 2,2157 %",
          c.zone_n == 1 and abs(c.zone_eps - EPS_H) <= 1e-6 * EPS_H and abs(c.util - EPS_S / 0.05) <= 1e-6
          and c.bauteil == "Stab",
          f"zone {c.zone_n} {c.zone_eps * 100:.4f} %, η {c.util:.4f}")
    _neu(m, an)


def test_alt_und_ueberlagerung(fall):
    from statik3d.ec3.volumen import NICHT_BEWERTET
    m, an = fall
    gesichert = {k: r.info.pop("ip_dehnungen", None) for k, r in an.all_results().items()}
    try:
        c = _neu(m, an)
        check("Ergebnisdatei ohne Dehnungen (vor dem 13.10.2026): „nicht bewertet“, Grund nennt neu rechnen",
              c.status() == NICHT_BEWERTET and "neu rechnen" in c.fehler and "13.10.2026" in c.fehler
              and c.util == 0.0, repr(c.fehler))
    finally:
        for k, r in an.all_results().items():
            if gesichert.get(k) is not None:
                r.info["ip_dehnungen"] = gesichert[k]
    lf = an.cases[list(m.load_cases)[0]]
    gzt = an.combinations["GZT1"]
    an.combinations["GZT1"] = solver.Results.combine(m, [(lf, 1.0)], "GZT1", "combination")
    try:
        c = _neu(m, an)
        check("Überlagerung plastischer Ergebnisse: „nicht bewertet“, ε_p ist nicht überlagerbar",
              c.status() == NICHT_BEWERTET and "Überlagerung" in c.fehler and c.util == 0.0, repr(c.fehler))
    finally:
        an.combinations["GZT1"] = gzt
    _neu(m, an)


def _kapitel(html: str, titel: str) -> str:
    """Das Kapitel *titel* des Berichts (ab seiner Ueberschrift bis zur
    naechsten), nicht das Inhaltsverzeichnis."""
    import re
    a = re.search(r'class="chapter">[^<]*' + re.escape(titel), html)
    if a is None:
        return ""
    b = html.find('class="chapter"', a.end())
    return html[a.start():b if b > 0 else len(html)]


def test_bericht(fall):
    from statik3d.report import Report
    m, an = fall
    m.volumenbereiche["B1"].eps_grenze = 0.05
    m.koerper["Einleitung"].nachweis_ausnehmen = False
    _neu(m, an)
    html = Report(m, an).html()
    teil = _kapitel(html, "Spannungsnachweise der Volumenbereiche")
    check("Bericht: Kriterium mit Norm (EN 1993-1-5 Anh. C / EN 1993-1-14) und Grenzwert",
          "plastische Hauptdehnung" in teil and "EN 1993-1-5" in teil and "EN 1993-1-14" in teil
          and "5.0 %" in teil)
    check("… ε_p,1, η, Ort und Bauteil", "3.866 %" in teil and "0.773" in teil and "Einleitung" in teil
          and "Element 4" in teil and "IP " in teil, "")
    check("… keine Zahl in wissenschaftlicher Schreibweise", "e-0" not in teil and "e+0" not in teil)
    m.koerper["Einleitung"].nachweis_ausnehmen = True
    _neu(m, an)
    html = Report(m, an).html()
    teil = _kapitel(html, "Spannungsnachweise der Volumenbereiche")
    check("… ausgenommener Körper steht im Bericht mit Namen", "ausgenommen" in teil and "Körper Einleitung" in teil)
    m.koerper["Einleitung"].nachweis_ausnehmen = False
    _neu(m, an)


def test_oberflaeche(fall):
    from statik3d.gui.dialogs import VolumenbereichDialog
    m, an = fall
    w, app = _fenster()
    w._modell_setzen(m)
    w._solve_done("all", an)
    app.processEvents()
    w.refresh_volumen()
    kopf = [s.name for s in w.tbl_vol.modell.spalten]
    z = list(w.tbl_vol.modell.zeilen[0])
    check("Volumentabelle: ε_p,1 [%], Bauteil und Ort stehen da",
          any("ε_p,1" in str(k) for k in kopf) and any(isinstance(x, float) and abs(x - EPS_H * 100) < 1e-6 for x in z)
          and "Einleitung" in z and any("Element 4" in str(x) for x in z), f"{kopf} {z}")
    check("… Ausnutzung η und Status", isinstance(z[8], float) and abs(z[8] - EPS_H / 0.05) < 1e-6
          and z[-1] == "erfüllt", f"{z[8]} {z[-1]}")
    d = VolumenbereichDialog(w, m, m.volumenbereiche["B1"])
    check("Maske Volumenbereich: Feld Grenzwert ε_p,1 in %, Vorgabe 5",
          hasattr(d, "ed_eps") and abs(d.ed_eps.value() - 5.0) < 1e-12, "")
    if hasattr(d, "ed_eps"):
        d.ed_eps.set(3.0)
        check("… result() liefert eps_grenze 0,03", abs(d.result()[1].get("eps_grenze", 0) - 0.03) < 1e-12,
              str(d.result()[1]))
    d.deleteLater()
    mk = w._objektmaske("werkstoff", "Hilf") or w.maskenrand.maske
    feld = mk._felder.get("ausnehmen") if mk is not None else None
    check("Werkstoffmaske: Schalter „vom Volumennachweis ausnehmen (Hilfs- oder Krafteinleitungskörper)“",
          feld is not None and hasattr(feld, "setChecked") and "Volumennachweis ausnehmen" in (feld.text() or ""),
          type(feld).__name__)
    if feld is not None:
        rho_vor, fy_vor = m.materials["Hilf"].rho, m.materials["Hilf"].fy
        feld.setChecked(True)
        mk.anwenden()
        app.processEvents()
        mt = w.model.materials["Hilf"]
        check("… Übernehmen setzt den Schalter, sonst bleibt der Werkstoff",
              mt.nachweis_ausnehmen is True and mt.rho == rho_vor and mt.fy == fy_vor, f"{mt}")
        mt.nachweis_ausnehmen = False
    mk = w._objektmaske("geokoerper_einzeln", "Einleitung") or w.maskenrand.maske
    feld = mk._felder.get("ausnehmen") if mk is not None else None
    check("Volumenmaske: derselbe Schalter am Körper",
          feld is not None and hasattr(feld, "setChecked") and "Volumennachweis ausnehmen" in (feld.text() or ""),
          type(feld).__name__)
    if feld is not None:
        feld.setChecked(True)
        mk.anwenden()
        app.processEvents()
        check("… Übernehmen setzt ihn am Körper", w.model.koerper["Einleitung"].nachweis_ausnehmen is True)
        w.model.koerper["Einleitung"].nachweis_ausnehmen = False


def test_kennung(fall_el):
    """Eine Ergebnisdatei von vor den neuen Feldern passt weiter: mit der
    Vorgabe zaehlen sie in der Kennung nicht mit (ergebnisse.SPAETERE_FELDER).
    Ohne das wies das Oeffnen die gespeicherte Rechnung des Drehlagers ab
    („seit der Rechnung geändert: Werkstoffe, Linien, Flächen und Volumen“)."""
    from statik3d import ergebnisse as erg
    m, _an = fall_el
    jetzt, _ = erg.rechenkennung(m)
    orig = m.to_dict

    def ohne_neue(*a, **k):
        d = orig(*a, **k)
        for v in d["materials"].values():
            v.pop("nachweis_ausnehmen", None)
        for x in d.get("koerper", []):
            x.pop("nachweis_ausnehmen", None)
        for x in d.get("volumenbereiche", []):
            x.pop("eps_grenze", None)
        return d
    m.to_dict = ohne_neue
    try:
        vorher, _ = erg.rechenkennung(m)
    finally:
        del m.to_dict
    check("Kennung der Ergebnisdatei: neue Felder mit Vorgabe ändern sie nicht (alte Dateien passen)",
          jetzt == vorher, str([g for g in jetzt if jetzt[g] != vorher.get(g)]))
    for was, setzen, gruppe in (("Werkstoff", lambda v: setattr(m.materials["Hilf"], "nachweis_ausnehmen", v),
                                 "werkstoffe"),
                                ("Körper", lambda v: setattr(m.koerper["Einleitung"], "nachweis_ausnehmen", v),
                                 "geometrie"),
                                ("Grenzwert", lambda v: setattr(m.volumenbereiche["B1"], "eps_grenze",
                                                                0.03 if v else 0.05), "nachweise")):
        setzen(True)
        g, _ = erg.rechenkennung(m)
        setzen(False)
        check(f"… gesetzt zählt es mit: {was} ändert „{erg.GRUPPEN[gruppe]}“",
              g[gruppe] != jetzt[gruppe] and all(g[k] == jetzt[k] for k in g if k != gruppe),
              str([k for k in g if g[k] != jetzt[k]]))


def test_elastisch(fall_el):
    """Elastisch bleibt der Volumennachweis, wie er war: dieselbe Rechnung,
    dieselben Zahlen (bitgleich), keine Dehnungen im Ergebnis."""
    from statik3d.ec3 import volumen as vol
    m, an = fall_el
    r = an.combinations["GZT1"]
    c = an.volumen.bereiche["B1"]
    werte = vol._elementspannungen(m, r, list(range(4)))
    svs = np.array([vol.vergleichsspannung(sp) for _e, sp, _p in werte])
    j = int(np.argmax(svs))
    fy = min(m.materials[m.elements[e].mat].yield_strength(c.werte.get("dicke", 0.0)) for e in range(4))
    d = vol.punkt_nachweis(werte[j][1], fy, m.design.gamma_M0)
    check("elastisch: η = σ_v/f_yd wie bisher, bitgleich",
          c.util == d["eta"] and c.werte["sigma_v"] == d["sigma_v"] and getattr(c, "kriterium", "") != "dehnung",
          f"η {c.util!r} / {d['eta']!r}")
    check("… keine Dehnungen im Ergebnis, kein „nicht bewertet“",
          "ip_dehnungen" not in (r.info or {}) and not getattr(c, "nicht_bewertet", "")
          and "ε_p" not in an.volumen.summary(), an.volumen.summary())


def main():
    faelle = {}
    for k, plast, sig in (("pl", True, SIGMA), ("el", False, 0.9 * FY)):
        try:
            faelle[k] = _zugstab(plast, sig)
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((f"Zugstab rechnen {k} (Ausnahme: {ex})", False))
    for t, k in ((test_geschlossen, "pl"), (test_grenzwert, "pl"), (test_ausnehmen, "pl"),
                 (test_zone, "pl"), (test_alt_und_ueberlagerung, "pl"), (test_bericht, "pl"),
                 (test_oberflaeche, "pl"), (test_kennung, "el"), (test_elastisch, "el")):
        print(f"\n--- {t.__name__} ---")
        try:
            if k not in faelle:
                RESULTS.append((t.__name__ + " (ohne Rechnung)", False))
            else:
                t(faelle[k])
        except Exception as ex:      # noqa: BLE001
            import traceback
            traceback.print_exc()
            RESULTS.append((t.__name__ + f" (Ausnahme: {ex})", False))
    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"\n{'=' * 60}\nErgebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    schlecht = [n for n, ok in RESULTS if not ok]
    if schlecht:
        print("FEHLGESCHLAGEN:", schlecht)
    return 0 if not schlecht else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
