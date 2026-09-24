"""
Verformungen und Verdrehungen im Modellbaum, Knopf „Ergebnisse“ in der
Glasleiste (24.09.2026).

Wunsch des Anwenders: „im modellbaum bei ergebnisse gehören auch die
verformungen und verdrehungen hin gesamt und achsbezogen, in die glasleiste
muss noch ein knopf um ergebnisse schnell an und ausschalten zu können“.

Geprueft wird ohne Fenster (viewport: Faerbung, Kennwerte, Liste fuer den
Baum) und mit dem echten Hauptfenster offscreen (Baum, Klick, Glasleiste,
Kopfzeile). Die Handrechnung ist der Kragarm: Verdrehung am Ende
phi = F L^2 / (2 E I) - auch mit Schubverformung (Timoshenko), denn die
Querkraft verdreht den Querschnitt nicht.

Aufruf:  python -m tests.test_ergebnisbaum
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("STATIK3D_NO_UPDATE_CHECK", "1")
os.environ.setdefault("STATIK3D_KEIN_BROWSER", "1")
# Einstellungen in eine Wegwerfdatei - die Pruefung darf die des Anwenders
# nicht ueberschreiben
os.environ["STATIK3D_EINSTELLUNGEN"] = os.path.join(
    tempfile.mkdtemp(prefix="statik3d_ergebnisbaum_"), "einstellungen.json")

import numpy as np  # noqa: E402

from statik3d.model import Model, Material, Section  # noqa: E402
from statik3d import solver, mesher  # noqa: E402
from statik3d import spannungen as spn  # noqa: E402

RESULTS = []
E, L, F = 210e9, 2.0, 10e3

#: die acht Eintraege der Gruppe „Verformungen“ in dieser Reihenfolge
TEXTE = ["u gesamt |u|", "ux", "uy", "uz", "φ gesamt |φ|", "φx", "φy", "φz"]
FELDER = ["|u| Verschiebung", "ux", "uy", "uz", "|φ| Verdrehung", "φx", "φy", "φz"]
OHNE_VOLUMEN = "keine Verdrehungen: nur Volumenkörper (Knoten ohne Drehfreiheitsgrad)"
KOPF_AUS = ("Ergebnisse ausgeblendet (Knopf „Ergebnisse“ in der Glasleiste oder "
            "Register Ergebnisse → „Ergebnisse zeigen“)")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FAIL'} {name:70s} {detail}")
    return ok


def _wissenschaftlich(text: str) -> bool:
    """Steht irgendwo eine Zahl der Form 2.3e-05 oder 1e+03?"""
    import re
    return re.search(r"\de[+-]\d", text) is not None


# --------------------------------------------------------------------------
# Modelle
# --------------------------------------------------------------------------
def _kragarm(n: int = 4):
    """Kragarm auf der x-Achse, eingespannt bei x = 0, drei Lastfaelle an der
    Spitze: LF1 Fz, LF2 Fy, LF3 Mx."""
    m = Model("Kragarm")
    m.add_material(Material("S", E=E, rho=0.0))
    sec = Section.rectangle("R", 0.1, 0.2)
    m.add_section(sec)
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (L, 0, 0), n)
    m.fix(ids[0], "all")
    spitze = ids[-1]
    m.add_load_case("LF1", "G")
    m.load_node(spitze, Fz=-F, case="LF1")
    m.add_load_case("LF2", "Q")
    m.load_node(spitze, Fy=F, case="LF2")
    m.add_load_case("LF3", "Q")
    m.load_node(spitze, Mx=0.5 * F, case="LF3")
    return m, ids, sec


def _wuerfel():
    """Reines Volumenmodell: 2x2x2 Hexaeder, unten fest, oben eine Last."""
    m = Model("Wuerfel")
    m.add_material(Material("S", E=E, rho=0.0))
    ids = mesher.grid_box(m, "S", 1.0, 1.0, 1.0, 2, 2, 2)
    for i in ids[:, :, 0].ravel():
        m.fix(int(i), [0, 1, 2])
    m.add_load_case("LF1", "G")
    m.load_node(int(ids[2, 2, 2]), Fz=-F, Fy=0.3 * F, case="LF1")
    return m, ids


def _gemischt():
    """Ein Hexaeder, unten fest, und ein Balken von seiner oberen Ecke zu
    einem eingespannten Punkt daneben; Last in Balkenmitte. Der Balken haengt
    am Volumenknoten gelenkig - das Modell ist trotzdem stabil."""
    m = Model("Gemischt")
    m.add_material(Material("S", E=E, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.grid_box(m, "S", 1.0, 1.0, 1.0, 1, 1, 1)
    for i in ids[:, :, 0].ravel():
        m.fix(int(i), [0, 1, 2])
    ecke = int(ids[1, 1, 1])
    mitte = m.add_node(2.0, 1.0, 1.0)
    ende = m.add_node(3.0, 1.0, 1.0)
    m.add_element("beam", [ecke, mitte], "S", "R")
    m.add_element("beam", [mitte, ende], "S", "R")
    m.fix(ende, "all")
    m.add_load_case("LF1", "G")
    m.load_node(mitte, Fz=-F, Fy=0.2 * F, case="LF1")
    volumen = sorted(int(i) for i in ids.ravel() if int(i) != ecke)
    return m, volumen, [ecke, mitte, ende]


# --------------------------------------------------------------------------
# Ohne Fenster
# --------------------------------------------------------------------------
def test_felder():
    from statik3d.gui.main import FIELDS
    i = FIELDS.index("uz") if "uz" in FIELDS else -1
    check("Färbungsliste: |φ| Verdrehung, φx, φy, φz direkt nach uz",
          i >= 0 and FIELDS[i + 1:i + 5] == ["|φ| Verdrehung", "φx", "φy", "φz"], str(FIELDS[:9]))
    check("… |u| Verschiebung bleibt der erste Eintrag", FIELDS[0] == "|u| Verschiebung")


def test_kragarm_verdrehung():
    from statik3d.gui import viewport as vp
    m, ids, sec = _kragarm()
    r = solver.solve_static(m, case="LF1")
    u = np.asarray(r.u, float)
    ps, cs, name = vp.result_field(m, r, "φy")
    check("φy am Stabmodell = u[:, 4]·1000, an jedem Knoten ein Wert",
          ps is not None and cs is None and np.all(np.isfinite(ps))
          and np.allclose(ps, u[:, 4] * 1000, rtol=0, atol=1e-12), name)
    check("… Beschriftung der Skala in mrad", name == "φy [mrad]", name)
    soll = F * L ** 2 / (2 * E * sec.Iy) * 1000
    ist = abs(float(ps[ids[-1]])) if ps is not None else float("nan")
    check("Handrechnung Kragarm: φ am Ende = F·L²/(2EI)",
          abs(ist - soll) <= 1e-6 * soll, f"num {ist:.6f} mrad, Hand {soll:.6f} mrad")
    check("… an der Einspannung 0", ps is not None and abs(float(ps[ids[0]])) < 1e-12)
    ps, _cs, name = vp.result_field(m, r, "|φ| Verdrehung")
    check("|φ| = Norm von u[:, 3:6]·1000",
          ps is not None and np.allclose(ps, np.linalg.norm(u[:, 3:6], axis=1) * 1000, atol=1e-12)
          and name == "|φ| [mrad]", name)
    for f, k in (("φx", 3), ("φz", 5)):
        ps, _cs, _n = vp.result_field(m, r, f)
        check(f"{f} = u[:, {k}]·1000 (hier null, aber ein Wert)",
              ps is not None and np.all(np.isfinite(ps)) and np.allclose(ps, u[:, k] * 1000))
    # Kennwerte im Bild: nur die gewaehlte Groesse, mrad, mit Knoten
    z = vp.kennwerte(m, r, feld="|φ| Verdrehung")
    phi = [s for s in z if s.startswith("phi ")]
    check("Kennwerte zu |φ|: größte Verdrehung mit Knoten in mrad",
          len(phi) == 1 and f"Knoten {ids[-1]}" in phi[0] and "[mrad]" in phi[0]
          and spn.dezimal(soll) in phi[0], str(z))
    z = vp.kennwerte(m, r, feld="φy")
    check("Kennwerte zu φy: eine Zeile phiy mit min und max in mrad",
          len([s for s in z if s.startswith("phiy")]) == 1
          and not any(s.startswith(("phix", "phiz", "phi ", "u ")) for s in z)
          and "[mrad]" in " ".join(z), str(z))
    check("Kennwerte ohne 2.3e-05", not _wissenschaftlich(" ".join(z)), str(z))
    z = vp.kennwerte(m, r, feld="ux")
    check("… zu ux keine Verdrehung", not any(s.startswith("phi") for s in z), str(z))


def test_liste_fuer_den_baum():
    from statik3d.gui import viewport as vp
    m, ids, _sec = _kragarm()
    r = solver.solve_static(m, case="LF1")
    liste = vp.verformungen_liste(m, r)
    check("Liste: acht Einträge in der Reihenfolge des Entwurfs",
          [e[0] for e in liste] == TEXTE and [e[2] for e in liste] == FELDER,
          str([e[0] for e in liste]))
    zus = [e[1] for e in liste]
    check("… Zusatz „min … max mm“ bzw. „mrad“",
          all("…" in z for z in zus) and all(z.endswith(" mm") for z in zus[:4])
          and all(z.endswith(" mrad") for z in zus[4:]), str(zus))
    check("… ohne e+/e-", not any(_wissenschaftlich(z) for z in zus), str(zus))
    check("… kein Eintrag grau am Stabmodell", not any(e[3] for e in liste))
    u = np.asarray(r.u, float) * 1000
    soll_uz = (f"{spn.dezimal(u[:, 2].min(), vorzeichen=True)} … "
               f"{spn.dezimal(u[:, 2].max(), vorzeichen=True)} mm")
    soll_phiy = (f"{spn.dezimal(u[:, 4].min(), vorzeichen=True)} … "
                 f"{spn.dezimal(u[:, 4].max(), vorzeichen=True)} mrad")
    check("… die Werte gehören zum Ergebnis (uz, φy)",
          zus[3] == soll_uz and zus[6] == soll_phiy, f"{zus[3]} / {zus[6]}")
    # sehr kleine Werte (ein Ergebnis mit 1e-9 der Verformung): trotzdem Dezimalzahl
    klein = type("R", (), {})()
    klein.u = np.asarray(r.u, float) * 1e-9
    zus = [e[1] for e in vp.verformungen_liste(m, klein)]
    check("… auch winzige Werte ohne e-", not any(_wissenschaftlich(z) for z in zus), str(zus[:2]))


def test_reines_volumenmodell():
    from statik3d.gui import viewport as vp
    m, _ids = _wuerfel()
    r = solver.solve_static(m, case="LF1")
    check("reines Volumenmodell: kein Knoten mit Drehsteifigkeit",
          not vp.drehknoten(m).any(), str(int(vp.drehknoten(m).sum())))
    check("… der Löser hat die Drehungen dort mit 0 gesperrt (darum grau statt Nullen)",
          np.all(np.asarray(r.u)[:, 3:6] == 0.0))
    for f in ("|φ| Verdrehung", "φx", "φy", "φz"):
        ps, _cs, _n = vp.result_field(m, r, f)
        check(f"{f}: kein Wert (NaN, grau) statt Nullen",
              ps is not None and not np.isfinite(ps).any(), "" if ps is None else str(ps[:3]))
    ps, _cs, _n = vp.result_field(m, r, "uz")
    check("… uz dagegen mit Werten", ps is not None and np.isfinite(ps).all())
    liste = vp.verformungen_liste(m, r)
    phi = [e for e in liste if e[2] in ("|φ| Verdrehung", "φx", "φy", "φz")]
    check("Liste: die φ-Einträge grau, Zusatz erklärt es",
          len(phi) == 4 and all(e[3] for e in phi) and all(e[1] == OHNE_VOLUMEN for e in phi),
          str([(e[1], e[3]) for e in phi][:1]))
    check("… die u-Einträge nicht", not any(e[3] for e in liste[:4])
          and all(e[1].endswith(" mm") for e in liste[:4]))
    z = vp.kennwerte(m, r, feld="φx")
    check("Kennwerte zu φx am Volumenmodell: keine Zahl, kein 0.000",
          not any(s.startswith("phix") and "0.000" in s for s in z), str(z))


def test_gemischtes_modell():
    from statik3d.gui import viewport as vp
    m, volumen, stab = _gemischt()
    r = solver.solve_static(m, case="LF1")
    d = vp.drehknoten(m)
    check("gemischtes Modell: genau die Stabknoten haben Drehsteifigkeit",
          sorted(np.flatnonzero(d).tolist()) == sorted(stab), str(np.flatnonzero(d).tolist()))
    ps, _cs, _n = vp.result_field(m, r, "φy")
    check("… Volumenknoten NaN (grau)", ps is not None and not np.isfinite(ps[volumen]).any())
    check("… Stabknoten mit Wert = u·1000",
          ps is not None and np.all(np.isfinite(ps[stab]))
          and np.allclose(ps[stab], np.asarray(r.u)[stab, 4] * 1000)
          and np.abs(ps[stab]).max() > 0, "" if ps is None else str(ps[stab]))
    ps, _cs, _n = vp.result_field(m, r, "|φ| Verdrehung")
    check("… |φ| ebenso", ps is not None and not np.isfinite(ps[volumen]).any()
          and np.all(np.isfinite(ps[stab])))
    liste = vp.verformungen_liste(m, r)
    check("… Liste nicht grau", not any(e[3] for e in liste), str([e[1] for e in liste][4:]))


def test_fachwerk_ohne_drehsteifigkeit():
    """Fachwerkstaebe tragen keine Biegung (beam3d.k_local_truss: Rotations-FHG
    leer) - ihre Knoten werden wie Volumenknoten mit 0 gesperrt."""
    from statik3d.gui import viewport as vp
    from statik3d.examples_lib import build_example
    m = build_example("truss")
    check("Fachwerk: kein Knoten mit Drehsteifigkeit", not vp.drehknoten(m).any())
    t = vp.ohne_verdrehung(m)
    check("… die Erklärung nennt nicht „nur Volumenkörper“",
          t.startswith("keine Verdrehungen") and "nur Volumenkörper" not in t, t)


def test_umhuellende():
    from statik3d.gui import viewport as vp
    m, _ids, _sec = _kragarm()
    cases = solver.solve_cases(m)
    env = solver.Envelope(m, cases, "U")
    ps, _cs, name = vp.result_field(m, env, "φx")
    soll = np.where(np.abs(env.u_max[:, 3]) > np.abs(env.u_min[:, 3]),
                    env.u_max[:, 3], env.u_min[:, 3]) * 1000
    check("Umhüllende: φx extrem (das betragsgrößere Extrem)",
          ps is not None and np.allclose(ps, soll) and name == "φx extrem [mrad]", name)
    check("… das ist die Torsion aus LF3",
          ps is not None and np.allclose(ps, np.asarray(cases["LF3"].u)[:, 3] * 1000, atol=1e-9)
          and np.abs(ps).max() > 0)
    check("Umhüllende führt phimag_max wie umag_max",
          hasattr(env, "phimag_max") and np.allclose(
              env.phimag_max, np.maximum(np.linalg.norm(env.u_max[:, 3:6], axis=1),
                                         np.linalg.norm(env.u_min[:, 3:6], axis=1))))
    ps, _cs, name = vp.result_field(m, env, "|φ| Verdrehung")
    check("… |φ| der Umhüllenden = phimag_max·1000",
          ps is not None and hasattr(env, "phimag_max")
          and np.allclose(ps, env.phimag_max * 1000) and name == "|φ| max [mrad]", name)
    zus = [e[1] for e in vp.verformungen_liste(m, env)]
    soll_x = (f"{spn.dezimal(env.u_min[:, 3].min() * 1000, vorzeichen=True)} … "
              f"{spn.dezimal(env.u_max[:, 3].max() * 1000, vorzeichen=True)} mrad")
    check("… Liste: φx von min(u_min) bis max(u_max)", len(zus) == 8 and zus[5] == soll_x,
          f"{zus[5] if len(zus) == 8 else zus} / {soll_x}")


# --------------------------------------------------------------------------
# Mit Hauptfenster (offscreen)
# --------------------------------------------------------------------------
_FENSTER = {}


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
    _FENSTER.update(w=w, app=app)
    return w, app


def _baumgruppe(w, gruppe: str):
    """Das Element der Ergebnisgruppe im Modellbaum (oder None)."""
    from PySide6 import QtCore
    baum = w.baum

    def lauf(it):
        if it.data(0, QtCore.Qt.UserRole) == "ergebnisgruppe" and it.text(0) == gruppe:
            return it
        for i in range(it.childCount()):
            x = lauf(it.child(i))
            if x is not None:
                return x
        return None
    for i in range(baum.topLevelItemCount()):
        x = lauf(baum.topLevelItem(i))
        if x is not None:
            return x
    return None


def test_baum_und_klick():
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    erg = w._ergebnisliste()
    gruppen = list(erg)
    check("Baum: Gruppe „Verformungen“ vorhanden", "Verformungen" in erg, str(gruppen))
    if "Verformungen" not in erg:
        return
    ver = erg["Verformungen"]
    check("… mit acht Einträgen in der Reihenfolge des Entwurfs",
          [e[0] for e in ver] == TEXTE, str([e[0] for e in ver]))
    check("… Schlüssel feld:<Färbung>", [e[2] for e in ver] == [f"feld:{f}" for f in FELDER],
          str([e[2] for e in ver]))
    iv = gruppen.index("Verformungen")
    vorher = [g for g in ("Umhüllende", "Kombinationen", "Lastfälle", "Nachweise") if g in gruppen]
    check("… nach Lastfällen/Nachweisen, vor Schnittgrößen",
          all(gruppen.index(g) < iv for g in vorher)
          and ("Schnittgrößen" not in gruppen or iv < gruppen.index("Schnittgrößen")), str(gruppen))
    zus = [e[1] for e in ver]
    check("… Zusatz ohne e+/e-", not any(_wissenschaftlich(z) for z in zus), str(zus))
    r = w.current_result()
    from statik3d.gui import viewport as vp
    check("… Zusatz gehört zum gezeigten Ergebnis",
          zus == [e[1] for e in vp.verformungen_liste(w.model, r)], w.cb_result.currentText())
    it = _baumgruppe(w, "Verformungen")
    kinder = [it.child(i).text(0) for i in range(it.childCount())] if it is not None else []
    check("… und steht so im Modellbaum", kinder == TEXTE, str(kinder))
    # Klick stellt die Faerbung ein
    w._baum_geklickt("ergebnis", "feld:ux"); app.processEvents()
    check("Klick „ux“ stellt die Färbung ux ein", w.cb_field.currentText() == "ux",
          w.cb_field.currentText())
    w._baum_geklickt("ergebnis", "feld:φy"); app.processEvents()
    check("Klick „φy“ stellt die Färbung φy ein, mit Skala",
          w.cb_field.currentText() == "φy" and len(w.plotter.scalar_bars) >= 1,
          f"{w.cb_field.currentText()}, {len(w.plotter.scalar_bars)} Skalen")
    kw = " ".join(getattr(w, "_kennwerte_zeilen", []) or [])
    check("… Kennwerte im Bild nennen φy in mrad", "phiy" in kw and "mrad" in kw, kw[:90])
    check("… die Umhüllende bleibt vorn (sie führt φ)",
          w.cb_result.currentText().startswith("Umhüllende"), w.cb_result.currentText())
    w._baum_geklickt("ergebnis", "feld:|φ| Verdrehung"); app.processEvents()
    kw = " ".join(getattr(w, "_kennwerte_zeilen", []) or [])
    check("Klick „φ gesamt“: Färbung |φ|, Kennwerte mit Knoten",
          w.cb_field.currentText() == "|φ| Verdrehung" and "phi " in kw and "Knoten" in kw, kw[:90])
    fehler = [z for z in w.log.toPlainText().splitlines()
              if z.startswith("FEHLER") or "Darstellung:" in z or "Kennwerte:" in z]
    check("… ohne Darstellungsfehler", not fehler, str(fehler[:2]))
    w._baum_geklickt("ergebnis", "feld:|u| Verschiebung"); app.processEvents()
    check("Klick „u gesamt“: Färbung |u|", w.cb_field.currentText() == "|u| Verschiebung")
    # Doppelklick uebernimmt in den Bericht (wie jedes Ergebnis). Die Aufnahme
    # selbst (Bildschirmfoto) haelt offscreen an - geprueft wird der Weg.
    aufnahmen = []
    w.ansicht_in_bericht = lambda: aufnahmen.append(w.cb_field.currentText())
    try:
        w._baum_bearbeiten("ergebnis", "feld:uz"); app.processEvents()
    finally:
        del w.ansicht_in_bericht
    check("Doppelklick „uz“: Färbung uz, dann in den Bericht",
          w.cb_field.currentText() == "uz" and aufnahmen == ["uz"], str(aufnahmen))
    # Eigenformen: keine Gruppe
    rm = solver.solve_modal(w.model, 2)
    w._solve_done("modal", rm); app.processEvents()
    check("bei Eigenformen keine Gruppe „Verformungen“",
          "Verformungen" not in w._ergebnisliste(), str(list(w._ergebnisliste())))


def test_volumenmodell_im_fenster():
    w, app = _fenster()
    w.load_example("solid"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()
    ver = w._ergebnisliste().get("Verformungen", [])
    phi = [e for e in ver if e[0].startswith("φ")]
    check("Volumenmodell: φ-Einträge mit der Erklärung als Zusatz",
          len(phi) == 4 and all(e[1] == OHNE_VOLUMEN for e in phi), str([e[1] for e in phi][:1]))
    from statik3d.gui import design as dsg
    it = _baumgruppe(w, "Verformungen")
    farben = {}
    if it is not None:
        for i in range(it.childCount()):
            c = it.child(i)
            farben[c.text(0)] = c.foreground(0).color().name()
    matt = dsg.FARBEN["matt"].lower()
    check("… im Baum grau, die u-Einträge nicht",
          all(farben.get(t) == matt for t in TEXTE[4:])
          and all(farben.get(t) != matt for t in TEXTE[:4]), str(farben))
    feld0 = w.cb_field.currentText()
    w._baum_geklickt("ergebnis", "feld:φx"); app.processEvents()
    check("… Klick: Meldung in der Statuszeile, Färbung bleibt",
          w.statusBar().currentMessage() == OHNE_VOLUMEN and w.cb_field.currentText() == feld0,
          f"{w.statusBar().currentMessage()[:70]!r}, {w.cb_field.currentText()}")
    # wer φ trotzdem in der Ergebnismaske waehlt, sieht keine Faerbung aus Nullen
    w.cb_field.setCurrentText("φx"); app.processEvents()
    akt = w.plotter.renderer.actors
    check("… φ in der Maske gewählt: keine Skala, keine Färbung mit Nullen",
          not len(w.plotter.scalar_bars), f"{len(w.plotter.scalar_bars)} Skalen, "
                                          f"{[a for a in akt if a.startswith('result')][:3]}")
    check("… und die Statuszeile sagt warum", w.statusBar().currentMessage() == OHNE_VOLUMEN,
          w.statusBar().currentMessage()[:80])
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()


def test_gemischtes_beispiel_im_fenster():
    """Reibbeispiel: Schalen und Hexaeder - alle φ-Faerbungen zeichnen ohne
    Fehler, Volumenknoten ohne Wert."""
    w, app = _fenster()
    w.load_example("friction"); app.processEvents()
    an = solver.solve_all(w.model, combinations=False)
    w._solve_done("all", an); app.processEvents()
    ver = w._ergebnisliste().get("Verformungen", [])
    check("Schalen + Volumen: φ-Einträge nicht grau",
          len(ver) == 8 and all(e[1].endswith(" mrad") for e in ver[4:]), str([e[1] for e in ver][4:5]))
    for f in FELDER:
        w.cb_field.setCurrentText(f); app.processEvents()
    fehler = [z for z in w.log.toPlainText().splitlines()
              if z.startswith("FEHLER") or "Darstellung:" in z or "Kennwerte:" in z]
    check("… alle acht Färbungen zeichnen ohne Fehler", not fehler, str(fehler[:2]))
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()


def test_glasleiste():
    w, app = _fenster()
    from PySide6 import QtCore, QtWidgets
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()
    w.act_ergebnisse.setChecked(False); app.processEvents()
    zeilen = [z.strip() for z in (w._kopfzeile_zeilen or [])]
    check("Kopfzeile bei „aus“ nennt beide Wege (Glasleiste und Register)",
          KOPF_AUS in zeilen, str(zeilen)[-120:])
    w.act_ergebnisse.setChecked(True); app.processEvents()
    kn = w.glasleiste.knoepfe
    b = kn.get("ergebnisse")
    check("Glasleiste: Knopf „ergebnisse“ vorhanden", b is not None, str(sorted(kn))[:90])
    if b is None:
        return
    check("… auf derselben Aktion wie das Ribbon",
          b.defaultAction() is w.act_ergebnisse and w.act_ergebnisse.isCheckable())
    check("… nur Symbol, Text beim Überfahren",
          b.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly and not b.icon().isNull()
          and b.toolTip().startswith("Ergebnisse zeigen / ausblenden"), b.toolTip()[:60])
    lay = w.glasleiste.lay
    check("… Index 0 die Lastfall-Liste, Index 1 der Knopf",
          lay.itemAt(0).widget() is w.cb_lastwahl and lay.itemAt(1).widget() is b,
          type(lay.itemAt(1).widget()).__name__)
    check("… kein neues Tastenkürzel", w.act_ergebnisse.shortcut().isEmpty(),
          w.act_ergebnisse.shortcut().toString())
    rib = [x for x in w.ribbon.findChildren(QtWidgets.QToolButton)
           if x.defaultAction() is w.act_ergebnisse]
    check("… das Ribbon hat den Schalter weiter", len(rib) == 1)
    n_skalen = len(w.plotter.scalar_bars)
    b.click(); app.processEvents()
    check("Klick: aus - keine Färbung, keine Skala",
          not w.ergebnisse_sichtbar() and not len(w.plotter.scalar_bars) and n_skalen >= 1
          and not any(a.startswith("result_") for a in w.plotter.renderer.actors),
          f"{n_skalen} -> {len(w.plotter.scalar_bars)} Skalen")
    check("… Ribbon und Glasleiste stehen gleich",
          b.isChecked() is False and all(x.isChecked() is False for x in rib))
    zeilen = [z.strip() for z in (w._kopfzeile_zeilen or [])]
    check("… Kopfzeile nennt beide Wege", KOPF_AUS in zeilen, str(zeilen)[-120:])
    check("… das Ergebnis ist nur versteckt", w.current_result() is not None)
    b.click(); app.processEvents()
    check("Klick: wieder an - Färbung und Skala zurück",
          w.ergebnisse_sichtbar() and len(w.plotter.scalar_bars) >= 1
          and b.isChecked() and all(x.isChecked() for x in rib)
          and not any("Ergebnisse ausgeblendet" in z for z in (w._kopfzeile_zeilen or [])))
    w.act_ergebnisse.setChecked(False); app.processEvents()
    check("Ribbon aus: der Glasknopf folgt", not b.isChecked())
    w.act_ergebnisse.setChecked(True); app.processEvents()


def main():
    # Haelt etwas an (ein Dialog offscreen), steht der Stapel im Protokoll
    # statt eines stummen Haengers
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_felder, test_kragarm_verdrehung, test_liste_fuer_den_baum,
              test_reines_volumenmodell, test_gemischtes_modell,
              test_fachwerk_ohne_drehsteifigkeit, test_umhuellende,
              test_baum_und_klick, test_volumenmodell_im_fenster,
              test_gemischtes_beispiel_im_fenster, test_glasleiste):
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
