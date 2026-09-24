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
#: so lang war die Zeile vor dem Knopf - laenger laeuft sie in einer schmalen
#: Ansicht rechts aus dem Bild (die Kopfzeile wird nicht umbrochen)
KOPF_BREIT = len("    Ergebnisse ausgeblendet (Register Ergebnisse → „Ergebnisse zeigen“)")


def _kopf_aus(w) -> bool:
    """Nennt die Kopfzeile beide Wege, und ist keine Zeile breiter als frueher?"""
    zeilen = list(w._kopfzeile_zeilen or [])
    text = " ".join(" ".join(zeilen).split())
    return KOPF_AUS in text and max(len(z) for z in zeilen) <= KOPF_BREIT


def _dreh_aus_assemblierung(m):
    """Knoten mit Drehsteifigkeit so, wie die Assemblierung sie sieht: nicht
    alle drei Dreh-FHG unter 1e-12 der groessten Hauptdiagonale (wie „weak“
    in assemble.constrained_dofs) - unabhaengig von viewport.drehknoten."""
    from statik3d import assemble as asm
    d = np.abs(asm.stiffness(m).diagonal())
    schwach = (d < d.max() * 1e-12)[: m.nn * 6].reshape(m.nn, 6)[:, 3:6]
    return ~schwach.all(axis=1)


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
    # |phi| und |u| je Knoten: das Maximum ueber die Einzelergebnisse - nicht
    # der Betrag aus u_max/u_min, deren Komponenten aus verschiedenen
    # Lastfaellen stammen (dort an der Spitze +13 %, Befund 24.09.2026)
    soll_phi = np.max([np.linalg.norm(np.asarray(c.u)[:, 3:6], axis=1) for c in cases.values()], axis=0)
    soll_u = np.max([np.linalg.norm(np.asarray(c.u)[:, :3], axis=1) for c in cases.values()], axis=0)
    alt_phi = np.maximum(np.linalg.norm(env.u_max[:, 3:6], axis=1),
                         np.linalg.norm(env.u_min[:, 3:6], axis=1))
    check("Umhüllende: phimag_max = max über die Lastfälle von |φ|",
          hasattr(env, "phimag_max") and np.allclose(env.phimag_max, soll_phi, rtol=1e-12, atol=0),
          f"Spitze {env.phimag_max[-1] * 1000:.6f} mrad, Soll {soll_phi[-1] * 1000:.6f}, "
          f"aus u_max/u_min {alt_phi[-1] * 1000:.6f}")
    check("… der Kragarm unterscheidet beides (sonst prüfte das nichts)",
          abs(alt_phi[-1] - soll_phi[-1]) > 1e-3 * soll_phi[-1])
    check("… umag_max = max über die Lastfälle von |u|",
          np.allclose(env.umag_max, soll_u, rtol=1e-12, atol=0))
    # ueber aufnehmen_umhuellende (Umhuellende aus Umhuellenden) dasselbe
    teil = solver.Envelope(m, {"LF1": cases["LF1"]}, "A")
    rest = solver.Envelope(m, {k: v for k, v in cases.items() if k != "LF1"}, "B")
    ges = solver.Envelope(m, {}, "G")
    ges.aufnehmen_umhuellende(teil)
    ges.aufnehmen_umhuellende(rest)
    check("… auch eingefaltet aus zwei Umhüllenden",
          np.allclose(ges.phimag_max, soll_phi, rtol=1e-12, atol=0)
          and np.allclose(ges.umag_max, soll_u, rtol=1e-12, atol=0))
    ps, _cs, name = vp.result_field(m, env, "|φ| Verdrehung")
    check("… |φ| der Umhüllenden = phimag_max·1000",
          ps is not None and hasattr(env, "phimag_max")
          and np.allclose(ps, env.phimag_max * 1000) and name == "|φ| max [mrad]", name)
    zus = [e[1] for e in vp.verformungen_liste(m, env)]
    ok = len(zus) == 8
    for i, (f, z) in enumerate(zip(FELDER, zus)):
        # der Zusatz nennt die Grenzen dessen, was der Klick zeigt
        w, _c, _n = vp.result_field(m, env, f)
        vz = not f.startswith("|")
        soll = (f"{spn.dezimal(np.nanmin(w), vorzeichen=vz)} … "
                f"{spn.dezimal(np.nanmax(w), vorzeichen=vz)} {'mrad' if 'φ' in f else 'mm'}")
        ok = ok and z == soll
    check("… Liste: jeder Zusatz = Grenzen der Färbung, die der Klick zeigt", ok, str(zus))
    # Gegenlaeufige Lastfaelle (Fz nach unten und nach oben): min(u_min) …
    # max(u_max) naennte +0.96 mm, das Bild zeigt je Knoten das
    # betragsgroessere Extrem - der Zusatz muss dem Bild folgen
    m2, ids2, _sec2 = _kragarm()
    m2.add_load_case("LF4", "Q")
    m2.load_node(ids2[-1], Fz=0.5 * F, case="LF4")
    env2 = solver.Envelope(m2, solver.solve_cases(m2), "U2")
    w, _c, _n = vp.result_field(m2, env2, "uz")
    z = vp.verformungen_liste(m2, env2)[3][1]
    soll = f"{spn.dezimal(np.nanmin(w), vorzeichen=True)} … {spn.dezimal(np.nanmax(w), vorzeichen=True)} mm"
    alt = (f"{spn.dezimal(env2.u_min[:, 2].min() * 1000, vorzeichen=True)} … "
           f"{spn.dezimal(env2.u_max[:, 2].max() * 1000, vorzeichen=True)} mm")
    check("… gegenläufige Lastfälle: uz-Zusatz = Skala, nicht min(u_min) … max(u_max)",
          z == soll and z != alt, f"{z} (alt {alt})")


def _pendelfachwerk(gelenke):
    """Dreieckfachwerk aus Balken mit Stabendgelenken *gelenke*."""
    m = Model("Pendel")
    m.add_material(Material("S", E=E, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.1))
    a = m.add_node(0, 0, 0)
    b = m.add_node(4, 0, 0)
    c = m.add_node(2, 0, 2)
    for p_, q_ in ((a, b), (b, c), (c, a)):
        m.add_element("beam", [p_, q_], "S", "R", hinges=list(gelenke))
    m.fix(a, [0, 1, 2])
    m.fix(b, [1, 2])
    m.fix(c, [1])
    m.add_load_case("LF1", "G")
    m.load_node(c, Fz=-10e3, Fx=2e3, case="LF1")
    return m


def _wuerfel_starr(art: str):
    """Wuerfel 2x2x2 hex8, Starrkoerper vom Punkt ueber der Oberseite zu den
    neun oberen Knoten, Moment am Master."""
    m = Model("Starr")
    m.add_material(Material("S", E=E, rho=0.0))
    ids = mesher.grid_box(m, "S", 1.0, 1.0, 1.0, 2, 2, 2)
    for i in ids[:, :, 0].ravel():
        m.fix(int(i), [0, 1, 2])
    master = m.add_node(0.5, 0.5, 1.5)
    m.add_starrkoerper(master, [int(i) for i in ids[:, :, 2].ravel()], art)
    m.add_load_case("LF1", "G")
    m.load_node(master, My=5e6, case="LF1")
    return m, master


def _feder(k_dreh: float):
    """Hexaeder, Feder vom oberen Knoten zu einem eingespannten Punkt."""
    m = Model("Feder")
    m.add_material(Material("S", E=E, rho=0.0))
    ids = mesher.grid_box(m, "S", 1.0, 1.0, 1.0, 1, 1, 1)
    for i in ids[:, :, 0].ravel():
        m.fix(int(i), [0, 1, 2])
    oben = int(ids[1, 1, 1])
    p_ = m.add_node(1.0, 1.0, 2.0)
    m.fix(p_, "all")
    m.add_feder_prop("F1", [1e7] * 3 + [k_dreh] * 3)
    m.add_element("feder", [oben, p_], "S", "F1")
    m.add_load_case("LF1", "G")
    m.load_node(oben, Mx=1e3, Fz=-1e3, case="LF1")
    return m, oben


def test_drehknoten_wie_assemblierung():
    """drehknoten entscheidet grau oder Wert - es muss dieselben Knoten nennen,
    die die Assemblierung drehsteif sieht (Befunde 24.09.2026: Pendelstab
    zeigte Nullen, RBE2 versteckte die Master-Drehung, eine nachtraeglich
    gesetzte Drehfeder blieb grau)."""
    from statik3d.gui import viewport as vp
    faelle = [("Kragarm", _kragarm()[0]), ("Würfel", _wuerfel()[0]),
              ("gemischt", _gemischt()[0]),
              ("Pendelstäbe [3,4,5,10,11]", _pendelfachwerk([3, 4, 5, 10, 11])),
              ("Gelenke nur My [4,10]", _pendelfachwerk([4, 10])),
              ("Gelenke Anfang [3,4,5]", _pendelfachwerk([3, 4, 5])),
              ("RBE2", _wuerfel_starr("RBE2")[0]), ("RBE3", _wuerfel_starr("RBE3")[0]),
              ("Feder ohne Drehfeder", _feder(0.0)[0]), ("Feder mit Drehfeder", _feder(1e5)[0])]
    for name, m in faelle:
        vp.drehknoten_vergessen()
        ist, soll = vp.drehknoten(m), _dreh_aus_assemblierung(m)
        check(f"drehknoten = Assemblierung: {name}", np.array_equal(ist, soll),
              f"{np.flatnonzero(ist).tolist()[:12]} / {np.flatnonzero(soll).tolist()[:12]}")
    m = _pendelfachwerk([3, 4, 5, 10, 11])
    r = solver.solve_static(m, case="LF1")
    ps, _c, _n = vp.result_field(m, r, "φy")
    check("Pendelstäbe: φy grau statt Nullen, Zusatz erklärt es",
          not np.isfinite(ps).any() and all(e[3] for e in vp.verformungen_liste(m, r)[4:]),
          str(ps))
    m, master = _wuerfel_starr("RBE2")
    r = solver.solve_static(m, case="LF1")
    ps, _c, _n = vp.result_field(m, r, "φy")
    check("RBE2 am Volumen: φy des Masters = u·1000 (nicht grau)",
          np.isfinite(ps[master]) and abs(ps[master] - np.asarray(r.u)[master, 4] * 1000) < 1e-12
          and abs(ps[master]) > 0, f"{ps[master]}")
    # Feder an Ort und Stelle mit Drehfeder versehen (so uebernimmt der
    # Federdialog): der Zwischenspeicher darf nicht die alte Maske liefern
    m, oben = _feder(0.0)
    vp.drehknoten_vergessen()
    vorher = bool(vp.drehknoten(m)[oben])
    m.federn["F1"].k = [1e7] * 3 + [1e5] * 3
    r = solver.solve_static(m, case="LF1")
    ps, _c, _n = vp.result_field(m, r, "φx")
    check("Feder nachträglich mit Drehfeder: φx am Federknoten mit Wert",
          not vorher and np.isfinite(ps[oben]) and abs(ps[oben]) > 0,
          f"vorher {vorher}, φx {ps[oben]}")


def test_winzige_verdrehung_skala():
    """Skalenformat unter 0,01 (hier mrad): ausgeschrieben, kein 1.43e-03."""
    for lo, hi in ((0.0, 1.43e-3), (-3.91e-3, 0.0), (0.0, 1.3e-6), (0.0, 0.0)):
        fmt = spn.skalenformat(lo, hi)
        check(f"Skalenformat {lo}…{hi}: {fmt} ohne e±",
              not _wissenschaftlich(fmt % hi) and not _wissenschaftlich(fmt % lo)
              and (hi == 0 or float(fmt % hi) != 0.0), f"{fmt % lo} … {fmt % hi}")


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
    # Kennwerte zu phi bei einer Eigenform: keine Zeile (sie waeren Nullen
    # bzw. bei einer Knickfigur die statischen Werte)
    for f in ("φy", "|φ| Verdrehung"):
        z = vp.kennwerte(w.model, rm, feld=f)
        check(f"Eigenform, Färbung {f}: keine phi-Zeile in den Kennwerten",
              not any(x.startswith("phi") for x in z), str(z))


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
    tips = [it.child(i).toolTip(1) for i in range(it.childCount())] if it is not None else []
    check("… wer den gekürzten Zusatz überfährt, liest die ganze Erklärung",
          len(tips) == 8 and all(t == OHNE_VOLUMEN for t in tips[4:]), str(tips[4:5]))
    feld0 = w.cb_field.currentText()
    w._baum_geklickt("ergebnis", "feld:φx"); app.processEvents()
    check("… Klick: Meldung in der Statuszeile, Färbung bleibt",
          w.statusBar().currentMessage() == OHNE_VOLUMEN and w.cb_field.currentText() == feld0,
          f"{w.statusBar().currentMessage()[:70]!r}, {w.cb_field.currentText()}")
    # Doppelklick auf den grauen Eintrag: nichts in den Bericht (es wurde
    # nichts eingestellt - sonst landete ein Bild von |u| im Bericht)
    aufnahmen = []
    w.ansicht_in_bericht = lambda: aufnahmen.append(w.cb_field.currentText())
    n_bericht = len(w.model.bericht)
    try:
        w._baum_bearbeiten("ergebnis", "feld:φx"); app.processEvents()
    finally:
        del w.ansicht_in_bericht
    check("… Doppelklick auf grauen φ-Eintrag: kein Bild, die Statuszeile erklärt",
          aufnahmen == [] and len(w.model.bericht) == n_bericht
          and w.statusBar().currentMessage() == OHNE_VOLUMEN, str(aufnahmen))
    # wer φ trotzdem in der Ergebnismaske waehlt, sieht keine Faerbung aus
    # Nullen; die Statuszeile vorher leeren - sonst stuende dort noch die
    # Meldung des Klicks, und die Pruefung hinge nicht am Zeichnen
    w.cb_field.setCurrentText("uz"); app.processEvents()
    w.statusBar().clearMessage()
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
    zeilen = list(w._kopfzeile_zeilen or [])
    check("Kopfzeile bei „aus“ nennt beide Wege (Glasleiste und Register), keine Zeile breiter als früher",
          _kopf_aus(w), str(zeilen)[-160:])
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
    zeilen = list(w._kopfzeile_zeilen or [])
    check("… Kopfzeile nennt beide Wege", _kopf_aus(w), str(zeilen)[-160:])
    check("… das Ergebnis ist nur versteckt", w.current_result() is not None)
    b.click(); app.processEvents()
    check("Klick: wieder an - Färbung und Skala zurück",
          w.ergebnisse_sichtbar() and len(w.plotter.scalar_bars) >= 1
          and b.isChecked() and all(x.isChecked() for x in rib)
          and not any("Ergebnisse ausgeblendet" in z for z in (w._kopfzeile_zeilen or [])))
    w.act_ergebnisse.setChecked(False); app.processEvents()
    check("Ribbon aus: der Glasknopf folgt", not b.isChecked())
    w.act_ergebnisse.setChecked(True); app.processEvents()


def _spalte1(w, gruppe: str) -> list:
    it = _baumgruppe(w, gruppe)
    return [it.child(i).text(1) for i in range(it.childCount())] if it is not None else []


def test_ergebniswechsel():
    """Der Zusatz gehoert zum gerade gezeigten Ergebnis - auch nach einem
    Wechsel in der Ergebnismaske oder der Glasleiste (Befund 24.09.2026: er
    blieb bei der Umhuellenden stehen)."""
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    w._modell_setzen(_kragarm()[0]); app.processEvents()   # drei Lastfaelle
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    check("Wechsel: nach der Rechnung steht die Umhüllende vorn",
          w.cb_result.currentText().startswith("Umhüllende"), w.cb_result.currentText())
    env_werte = _spalte1(w, "Verformungen")
    faelle = [i for i in range(w.cb_result.count()) if w.cb_result.itemData(i)[0] == "case"]
    if not faelle:
        check("Wechsel: Lastfälle vorhanden", False)
        return
    w.cb_result.setCurrentIndex(faelle[0]); app.processEvents()
    r = w.current_result()
    soll = [e[1] for e in vp.verformungen_liste(w.model, r)]
    check("… Ergebnismaske auf einen Lastfall: Zusätze „Verformungen“ ziehen nach",
          _spalte1(w, "Verformungen") == soll and soll != env_werte,
          f"{w.cb_result.currentText()}: {_spalte1(w, 'Verformungen')[:3]} / {soll[:3]}")
    sg = [e[1] for e in w._ergebnisliste().get("Schnittgrößen", [])]
    check("… und „Schnittgrößen“", sg and _spalte1(w, "Schnittgrößen") == sg,
          str(_spalte1(w, "Schnittgrößen")[:2]))
    # zurueck zur Umhuellenden
    w.cb_result.setCurrentIndex(0); app.processEvents()
    soll = [e[1] for e in vp.verformungen_liste(w.model, w.current_result())]
    check("… zurück zur Umhüllenden: wieder deren Werte", _spalte1(w, "Verformungen") == soll)
    # ueber die Glasleiste auf den Lastfall (derselbe Weg wie ihr Signal)
    cb = w.cb_lastwahl
    ziel = [i for i in range(cb.count()) if cb.itemData(i) and tuple(cb.itemData(i))[0] == "case"]
    if ziel:
        cb.blockSignals(True)
        cb.setCurrentIndex(ziel[0])
        cb.blockSignals(False)
        w._glas_last_gewaehlt(ziel[0]); app.processEvents()
        r = w.current_result()
        soll = [e[1] for e in vp.verformungen_liste(w.model, r)]
        check("… Glasleiste auf den Lastfall: Zusätze ziehen nach",
              w.cb_result.currentData()[0] == "case" and _spalte1(w, "Verformungen") == soll,
              f"{w.cb_result.currentText()}: {_spalte1(w, 'Verformungen')[:3]} / {soll[:3]}")
    else:
        check("… Glasleiste: Lastfall zum Wählen", False, str([cb.itemText(i) for i in range(cb.count())]))


def test_knoten_nach_rechnung():
    """Nach der Rechnung einen Knoten anlegen: das Ergebnis gehoert zum alten
    Netz - der Baum darf daran nicht abbrechen (Befund 24.09.2026: ValueError
    in refresh_all, Baum und Ansicht blieben stehen)."""
    w, app = _fenster()
    w.load_example("frame"); app.processEvents()
    an = solver.solve_all(w.model, design=False)
    w._solve_done("all", an); app.processEvents()
    for sichtbar in (True, False):
        w.act_ergebnisse.setChecked(sichtbar); app.processEvents()
        nn = w.model.nn
        fehler = ""
        try:
            w._maske_knoten_anlegen({"x": 9.0 + nn, "y": 9.0, "z": 9.0}); app.processEvents()
        except Exception as ex:      # noqa: BLE001
            fehler = f"{type(ex).__name__}: {ex}"
        wurzel = w.baum.topLevelItem(0)
        check(f"Knoten nach der Rechnung angelegt (Ergebnisse {'an' if sichtbar else 'aus'}): "
              "keine Ausnahme, der Baum zählt ihn",
              not fehler and w.model.nn == nn + 1 and wurzel is not None
              and wurzel.text(1) == f"{nn + 1} Kn", fehler or (wurzel.text(1) if wurzel else ""))
    check("… die Verformungen des alten Netzes stehen nicht mehr im Baum",
          "Verformungen" not in w._ergebnisliste(), str(list(w._ergebnisliste())))
    w.act_ergebnisse.setChecked(True); app.processEvents()


def test_gelenke_nach_der_rechnung():
    """Gelenke an Ort und Stelle geaendert, neu gerechnet: die Maske gehoert
    zur neuen Rechnung (_solve_done leert den Zwischenspeicher)."""
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    w._modell_setzen(_pendelfachwerk([3, 4, 5, 10, 11])); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    grau = [len(e) > 3 for e in w._ergebnisliste().get("Verformungen", [])][4:]
    check("Pendelstäbe im Fenster: φ-Einträge grau", bool(grau) and all(grau), str(grau))
    for e in w.model.elements:
        e.hinges = []
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    grau = [len(e) > 3 for e in w._ergebnisliste().get("Verformungen", [])][4:]
    check("… Gelenke entfernt, neu gerechnet: φ-Einträge mit Wert",
          bool(grau) and not any(grau)
          and np.array_equal(vp.drehknoten(w.model), _dreh_aus_assemblierung(w.model)), str(grau))


def test_winzige_verdrehung_im_fenster():
    """Kragarm mit 10 N: phi um 0,001 mrad - die Skala schreibt es aus."""
    w, app = _fenster()
    m = Model("Klein")
    m.add_material(Material("S", E=E, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (L, 0, 0), 4)
    m.fix(ids[0], "all")
    m.add_load_case("LF1", "G")
    m.load_node(ids[-1], Fz=-10.0, case="LF1")
    w._modell_setzen(m); app.processEvents()
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    for f in ("φy", "|φ| Verdrehung"):
        w.cb_field.setCurrentText(f); app.processEvents()
        bars = list(w.plotter.scalar_bars.values())
        fmt = bars[0].GetLabelFormat() if bars else ""
        check(f"φ ≈ 0,001 mrad, Färbung {f}: Skala ausgeschrieben", bool(fmt) and "e" not in fmt, fmt)
    w.cb_field.setCurrentText("|u| Verschiebung"); app.processEvents()


# --------------------------------------------------------------------------
# Alte Ergebnisdatei, Ergebnis zu einem frueheren Modellstand (24.09.2026)
# --------------------------------------------------------------------------
#: Ergebnisdatei, geschrieben mit dem Stand e61b184 (vor _umag/_phimag):
#: git archive e61b184 statik3d, darin Kragarm 2 m aus 2 Staeben, LA (Fy, Fz
#: am Ende) und LB (Mx) - |u| am Ende 21,591943 mm, |phi| 16,162441 mrad
ALT_ORDNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten",
                          "ergebnisdatei_e61b184")
PHI_ALT = "nicht in der Ergebnisdatei – neu rechnen"
VERALTET = "Ergebnis passt nicht mehr zum Modell – neu rechnen"


def _alte_dateien() -> str:
    """Die alte Ergebnisdatei samt Modell in einen Wegwerfordner - Oeffnen
    und Speichern duerfen die Vorlage in tests/ nicht veraendern."""
    import shutil
    ziel = tempfile.mkdtemp(prefix="statik3d_alt_")
    for n in ("kragarm_alt.json", "kragarm_alt.ergebnisse"):
        shutil.copy(os.path.join(ALT_ORDNER, n), ziel)
    return os.path.join(ziel, "kragarm_alt.json")


def test_alte_ergebnisdatei():
    """Ergebnisdateien vom Stand e61b184 kennen _umag/_phimag nicht: das
    Oeffnen brach in Envelope.summary ab (Nachkontrolle 24.09.2026)."""
    from statik3d import ergebnisse
    from statik3d.gui import viewport as vp
    p = _alte_dateien()
    m = Model.load(p)
    an = ergebnisse.lesen(ergebnisse.pfad_zu(p), m)
    env = an.envelopes["CASES"]
    with open(ergebnisse.pfad_zu(p), "rb") as fh:
        roh = fh.read()
    check("Alte Ergebnisdatei: wirklich ohne _umag/_phimag geschrieben",
          b"_umag" not in roh and b"_phimag" not in roh and b"u_max" in roh, f"{len(roh)} Bytes")
    try:
        um = np.asarray(env.umag_max)
        fehler = ""
    except Exception as ex:          # noqa: BLE001
        um, fehler = None, f"{type(ex).__name__}: {ex}"
    alt = np.maximum(np.linalg.norm(env.u_max[:, :3], axis=1), np.linalg.norm(env.u_min[:, :3], axis=1))
    check("… umag_max ohne Ausnahme, wie bis dahin aus u_min/u_max",
          um is not None and np.allclose(um, alt) and abs(um.max() * 1000 - 21.591943) < 1e-5,
          fehler or f"{um.max() * 1000:.6f} mm")
    try:
        pm, fehler = env.phimag_max, ""
    except Exception as ex:          # noqa: BLE001
        pm, fehler = "Ausnahme", f"{type(ex).__name__}: {ex}"
    check("… phimag_max: None (nicht gespeichert, nicht falsch klein)", pm is None, fehler or str(pm))
    try:
        s = an.summary()
        fehler = ""
    except Exception as ex:          # noqa: BLE001
        s, fehler = "", f"{type(ex).__name__}: {ex}"
    check("… Analysis.summary ohne Ausnahme", "max. Verschiebung" in s, fehler)
    try:
        w_, _c, name = vp.result_field(m, env, "|u| Verschiebung")
        fehler = ""
    except Exception as ex:          # noqa: BLE001
        w_, name, fehler = None, "", f"{type(ex).__name__}: {ex}"
    check("… Färbung |u| ohne Ausnahme", w_ is not None and name == "|u| max [mm]", fehler or name)
    try:
        liste, fehler = vp.verformungen_liste(m, env), ""
    except Exception as ex:          # noqa: BLE001
        liste, fehler = [], f"{type(ex).__name__}: {ex}"
    phi = [e for e in liste if e[2] == "|φ| Verdrehung"]
    check("… Baumliste: „φ gesamt“ grau mit „nicht in der Ergebnisdatei – neu rechnen“",
          phi and phi[0][1] == PHI_ALT and phi[0][3] is True, fehler or str(phi))
    uu = [e for e in liste if e[2] == "|u| Verschiebung"]
    check("… „u gesamt“ mit Wert", uu and "21.6 mm" in uu[0][1] and not uu[0][3], str(uu))
    achs = [e for e in liste if e[2] in ("φx", "φy", "φz")]
    check("… φx, φy, φz mit Wert (aus u_min/u_max, dort ehrlich)",
          len(achs) == 3 and all(e[1] and not e[3] for e in achs), str(achs))
    # Einfalten einer alten Umhuellenden (Stellungen, Gesamtumhuellende):
    # |phi| bleibt unbekannt statt TypeError
    try:
        ges = solver.Envelope(m, name="Gesamt")
        ges.aufnehmen_umhuellende(env)
        ges2 = solver.Envelope(m, an.cases, name="Neu")
        ges2.aufnehmen_umhuellende(env)
        fehler = ""
    except Exception as ex:          # noqa: BLE001
        ges = ges2 = None
        fehler = f"{type(ex).__name__}: {ex}"
    check("… alte Umhüllende einfalten: |φ| bleibt unbekannt, |u| da",
          ges is not None and ges.phimag_max is None and ges2.phimag_max is None
          and np.allclose(ges.umag_max, alt), fehler)


def test_alte_ergebnisdatei_im_fenster():
    """Dieselbe Datei ueber Datei → Oeffnen: Modell, Ergebnisse, Baum und
    Faerbung |u| ohne Ausnahme."""
    w, app = _fenster()
    p = _alte_dateien()
    fehler = ""
    try:
        ok = w.modell_laden(p); app.processEvents()
    except Exception as ex:          # noqa: BLE001
        ok, fehler = False, f"{type(ex).__name__}: {ex}"
    check("Alte Ergebnisdatei öffnen: ohne Ausnahme, Ergebnisse geladen",
          ok and not fehler and w.analysis is not None and "CASES" in w.analysis.envelopes,
          fehler or str(ok))
    if fehler:
        return
    ver = w._ergebnisliste().get("Verformungen", [])
    phi = [e for e in ver if e[2] == "feld:|φ| Verdrehung"]
    check("… Baum: „φ gesamt“ grau mit Hinweis „neu rechnen“",
          phi and phi[0][1] == PHI_ALT and len(phi[0]) > 3, str(phi))
    n0 = len(w.log.toPlainText().splitlines())
    for feld in ("|u| Verschiebung", "|φ| Verdrehung", "φy"):
        fehler = ""
        try:
            w._baum_geklickt("ergebnis", f"feld:{feld}"); app.processEvents()
            w.redraw(); app.processEvents()
        except Exception as ex:      # noqa: BLE001
            fehler = f"{type(ex).__name__}: {ex}"
        check(f"… Färbung {feld} ohne Ausnahme", not fehler and w.cb_field.currentText() == feld,
              fehler or w.cb_field.currentText())
    w._baum_geklickt("ergebnis", "feld:|u| Verschiebung"); app.processEvents()
    kw = " ".join(getattr(w, "_kennwerte_zeilen", []) or [])
    check("… |u|: Skala und Kennwerte da", len(w.plotter.scalar_bars) >= 1 and "Knoten" in kw, kw[:80])
    fehl = [z for z in w.log.toPlainText().splitlines()[n0:]
            if z.startswith("FEHLER") or "Darstellung:" in z or "Kennwerte:" in z]
    check("… ohne Darstellungsfehler im Protokoll", not fehl, str(fehl[:2]))
    w.load_example("frame"); app.processEvents()


def test_ergebnis_passt_nicht_mehr():
    """Nach der Rechnung bei gezeigten Ergebnissen Knoten, Stab (Stabzug und
    Maske) oder Flaeche anlegen: das Ergebnis kennt die neuen Knoten und
    Elemente nicht. Bis zum 24.09.2026 brach das Zeichnen mit IndexError ab
    (u[kn] in _aufbauen). Die neuen Teile sind grau, die Kopfzeile sagt
    „neu rechnen“ - fuer die Faerbungen |u|, φx, einen Schnittgroessenverlauf
    und eine Spannung."""
    from statik3d.model import ShellProp
    w, app = _fenster()

    def neu():
        w.load_example("frame"); app.processEvents()
        w.model.add_shell_prop(ShellProp("T10", 0.01))
        w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
        return w._ergebnisliste()

    erg = neu()
    spannung = [e[2] for v in erg.values() for e in v if str(e[2]).startswith("spannung:")]
    check("Nicht mehr passend: das Beispiel hat eine Spannungsfärbung", bool(spannung), str(list(erg)))
    faerbungen = ["feld:|u| Verschiebung", "feld:φx", "schnittgroesse:My"] + spannung[:1]
    mat, sec = list(w.model.materials)[0], list(w.model.sections)[0]
    aktionen = {
        "Knoten": lambda: w._maske_knoten_anlegen({"x": 30.0, "y": 9.0, "z": 9.0}),
        "Stabzug": lambda: w._stabzug_erzeugen({"mat": mat, "sec": sec, "x1": 20, "y1": 0, "z1": 0,
                                                "x2": 25, "y2": 0, "z2": 0, "n": 4}),
        "Stab (Maske)": lambda: w._maske_stab_anlegen({"knoten": [0, 5], "mat": mat, "sec": sec}),
        "Fläche": lambda: w._platte_erzeugen({"mat": mat, "dicke": "T10", "lx": 2, "ly": 2, "z": 20.0,
                                             "nx": 2, "ny": 2, "vierecke": True}),
    }
    for akt, tun in aktionen.items():
        for fb in faerbungen:
            neu()
            w._baum_geklickt("ergebnis", fb); app.processEvents()
            nn0, ne0 = w.model.nn, len(w.model.elements)
            n0 = len(w.log.toPlainText().splitlines())
            fehler = ""
            try:
                tun(); app.processEvents()
                w.redraw(); app.processEvents()
            except Exception as ex:  # noqa: BLE001
                fehler = f"{type(ex).__name__}: {ex}"
            gewachsen = w.model.nn > nn0 or len(w.model.elements) > ne0
            kopf = " ".join(getattr(w, "_kopfzeile_zeilen", []) or [])
            fehl = [z for z in w.log.toPlainText().splitlines()[n0:]
                    if z.startswith("FEHLER") or any(k in z for k in (
                        "Darstellung:", "Kennwerte:", "Werte im Bild:", "Verlauf:", "Kopfzeile:"))]
            check(f"{akt} nach der Rechnung, {fb.split(':', 1)[1]}: kein Absturz, "
                  "Kopfzeile „neu rechnen“",
                  not fehler and gewachsen and VERALTET in kopf and not fehl,
                  fehler or (str(fehl[:1]) if fehl else kopf[-60:]))
    # die alten Knoten behalten ihre Werte, die neuen sind grau (NaN)
    neu()
    w._baum_geklickt("ergebnis", "feld:|u| Verschiebung"); app.processEvents()
    fehler = ""
    try:
        aktionen["Stabzug"](); app.processEvents()
    except Exception as ex:          # noqa: BLE001
        fehler = f"{type(ex).__name__}: {ex}"
    # was die Ansicht gezeichnet hat: die Werte am verformten Netz
    import pyvista as pv
    gezeichnet = []
    for nm, akt in w.plotter.actors.items():
        if str(nm).startswith("result_") and akt.GetMapper() is not None:
            ds = pv.wrap(akt.GetMapper().GetInput())
            if "|u| max [mm]" in ds.point_data:
                gezeichnet.append(np.asarray(ds.point_data["|u| max [mm]"], float))
    werte = np.concatenate(gezeichnet) if gezeichnet else np.array([])
    kw = " ".join(getattr(w, "_kennwerte_zeilen", []) or [])
    check("… Stabzug, |u| im Bild: alte Knoten mit Wert, neue ohne (grau), Kennwerte bleiben",
          not fehler and np.isfinite(werte).any() and np.isnan(werte).any() and "Knoten" in kw,
          fehler or f"{int(np.isfinite(werte).sum())} mit Wert, {int(np.isnan(werte).sum())} ohne; {kw[:40]}")
    # neu gerechnet: der Hinweis geht weg
    w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
    kopf = " ".join(getattr(w, "_kopfzeile_zeilen", []) or [])
    check("… neu gerechnet: kein Hinweis mehr", VERALTET not in kopf, kopf[-60:])
    # weniger Elemente als bei der Rechnung: die Nummern koennen verrutscht
    # sein - kein Ergebnis im Bild, aber der Hinweis
    # wie der Knopf „Element löschen“ (element_loeschen): Model.elemente_loeschen
    w.model.elemente_loeschen([len(w.model.elements) - 1])
    fehler = ""
    try:
        w.refresh_all(); app.processEvents()
    except Exception as ex:          # noqa: BLE001
        fehler = f"{type(ex).__name__}: {ex}"
    kopf = " ".join(getattr(w, "_kopfzeile_zeilen", []) or [])
    check("… Element gelöscht: kein Absturz, keine Färbung, Hinweis „neu rechnen“",
          not fehler and VERALTET in kopf and not w.plotter.scalar_bars
          and "ausgeblendet" not in kopf, fehler or kopf[-60:])
    w.load_example("frame"); app.processEvents()


def _gezeichnet_je_knoten(w, spalte: str):
    """Was die Ansicht an Knotenwerten ``spalte`` gezeichnet hat, je
    Knotennummer (NaN: nicht gezeichnet oder ohne Wert). Die Gitterteile
    tragen ihre Knotennummern in _netzteile_zwischen, der Stabkoerper in
    point_data["knoten"]."""
    import pyvista as pv
    werte = np.full(w.model.nn, np.nan)
    teile = {nm: kidx for _t, kidx, nm in (getattr(w, "_netzteile_zwischen", None) or [])}
    for nm, akt in w.plotter.actors.items():
        nm = str(nm)
        if not nm.startswith("result_") or akt.GetMapper() is None:
            continue
        ds = pv.wrap(akt.GetMapper().GetInput())
        if spalte not in ds.point_data:
            continue
        kn = (np.asarray(ds.point_data["knoten"], int) if "knoten" in ds.point_data
              else teile.get(nm[len("result_"):]))
        if kn is None or len(kn) != ds.n_points:
            continue
        werte[kn] = np.asarray(ds.point_data[spalte], float)
    return werte


def test_ergebnis_passt_nach_stand():
    """Die Gegenpruefung von 5090fe2 (24.09.2026): ergebnis_passt verglich
    nur Knoten- und Elementzahl. Ein Element loeschen und eines anlegen
    ergab „passt“ - die Werte lagen dann an falschen Elementen ohne Hinweis;
    loeschen und mehr anlegen ergab „gewachsen“ mit verschobenen Werten; ein
    verschobener Knoten fiel gar nicht auf. Jetzt merkt sich die Oberflaeche
    den Modellstand (Koordinaten, je Element Typ und Knoten): nur ein
    unveraendert gebliebener Anfang mit Angehaengtem ist „gewachsen“ (alte
    Werte an alten Knoten, auch φx - das Auffuellen in _verdrehung), alles
    andere „anders“: kein Ergebnis im Bild, Hinweis „neu rechnen“."""
    from statik3d.gui import viewport as vp
    w, app = _fenster()
    mat = sec = None

    def neu(feld="feld:|u| Verschiebung"):
        nonlocal mat, sec
        w.load_example("frame"); app.processEvents()
        mat, sec = list(w.model.materials)[0], list(w.model.sections)[0]
        w._solve_done("all", solver.solve_all(w.model, design=False)); app.processEvents()
        w._baum_geklickt("ergebnis", feld); app.processEvents()

    def stabzug():
        w._stabzug_erzeugen({"mat": mat, "sec": sec, "x1": 20, "y1": 0, "z1": 0,
                             "x2": 25, "y2": 0, "z2": 0, "n": 4})

    def zustand():
        kopf = " ".join(getattr(w, "_kopfzeile_zeilen", []) or [])
        passt = vp.ergebnis_passt(w.model, w.current_result(), getattr(w, "_ergebnis_stand", None))
        return passt, kopf

    # (a) ein Element loeschen, eines anlegen: gleiche Anzahl, andere Elemente
    neu()
    ne0, nn0 = len(w.model.elements), w.model.nn
    w.model.elemente_loeschen([0])
    w._maske_stab_anlegen({"knoten": [0, 5], "mat": mat, "sec": sec}); app.processEvents()
    w.redraw(); app.processEvents()
    passt, kopf = zustand()
    check("Element gelöscht und eines angelegt (gleiche Anzahl): „anders“, kein Ergebnis "
          "im Bild, Hinweis „neu rechnen“",
          len(w.model.elements) == ne0 and w.model.nn == nn0 and passt == "anders"
          and VERALTET in kopf and not w.plotter.scalar_bars,
          f"{passt}, {len(w.plotter.scalar_bars)} Skalen, {kopf[-50:]}")

    # (b) ein Element loeschen, mehrere anlegen: gewachsen der Zahl nach, die
    # Nummern der alten Elemente sind aber verrutscht
    neu()
    ne0 = len(w.model.elements)
    w.model.elemente_loeschen([0])
    stabzug(); app.processEvents()
    w.redraw(); app.processEvents()
    passt, kopf = zustand()
    check("Element gelöscht, Stabzug angelegt (mehr Elemente): „anders“, kein Ergebnis im Bild",
          len(w.model.elements) > ne0 and passt == "anders" and VERALTET in kopf
          and not w.plotter.scalar_bars, f"{passt}, {len(w.plotter.scalar_bars)} Skalen")

    # Knoten verschoben: gleiche Anzahl, gleiche Elemente, andere Geometrie
    neu()
    w.model.nodes[3] = np.asarray(w.model.nodes[3], float) + [0.0, 0.0, 0.5]
    w.refresh_all(); app.processEvents()
    passt, kopf = zustand()
    check("Knoten verschoben: „anders“, kein Ergebnis im Bild, Hinweis „neu rechnen“",
          passt == "anders" and VERALTET in kopf and not w.plotter.scalar_bars,
          f"{passt}, {len(w.plotter.scalar_bars)} Skalen, {kopf[-50:]}")

    # reines Anhaengen: „gewachsen“, die alten Knoten zeigen genau ihre Werte
    # von vorher, die neuen keinen - fuer φx sichert das das Auffuellen in
    # vp._verdrehung (ohne es gaebe es nach dem Stabzug gar keine φ-Werte)
    for feld in ("|u| Verschiebung", "φx"):
        neu("feld:" + feld)
        r = w.current_result()
        vorher, _c, spalte = vp.result_field(w.model, r, feld)
        vorher = np.asarray(vorher, float).copy()
        nn0 = w.model.nn
        gez0 = _gezeichnet_je_knoten(w, spalte)
        stabzug(); app.processEvents()
        w.redraw(); app.processEvents()
        passt, kopf = zustand()
        gez = _gezeichnet_je_knoten(w, spalte)
        alt = np.isfinite(gez0[:nn0])     # vor dem Stabzug mit Wert gezeichnet
        check(f"Stabzug angehängt, {feld}: „gewachsen“, alte Knoten mit dem Wert von vorher, "
              "neue ohne",
              passt == "gewachsen" and VERALTET in kopf and w.model.nn > nn0
              and alt.sum() > 0 and np.allclose(gez[:nn0][alt], vorher[alt])
              and np.isnan(gez[nn0:]).all(),
              f"{passt}, {int(alt.sum())} alte mit Wert, "
              f"{int(np.isfinite(gez[:nn0]).sum())} nachher, "
              f"{int(np.isfinite(gez[nn0:]).sum())} neue mit Wert")

    # ohne Aenderung neu gezeichnet: „passt“, kein Hinweis
    neu()
    w.redraw(); app.processEvents()
    passt, kopf = zustand()
    check("Unverändert: „passt“, kein Hinweis", passt == "passt" and VERALTET not in kopf,
          f"{passt}, {kopf[-50:]}")
    w.load_example("frame"); app.processEvents()


def main():
    # Haelt etwas an (ein Dialog offscreen), steht der Stapel im Protokoll
    # statt eines stummen Haengers
    import faulthandler
    faulthandler.dump_traceback_later(900, exit=True)
    for t in (test_felder, test_kragarm_verdrehung, test_liste_fuer_den_baum,
              test_reines_volumenmodell, test_gemischtes_modell,
              test_fachwerk_ohne_drehsteifigkeit, test_umhuellende,
              test_drehknoten_wie_assemblierung, test_winzige_verdrehung_skala,
              test_baum_und_klick, test_volumenmodell_im_fenster,
              test_gemischtes_beispiel_im_fenster, test_glasleiste,
              test_ergebniswechsel, test_knoten_nach_rechnung,
              test_gelenke_nach_der_rechnung, test_winzige_verdrehung_im_fenster,
              test_alte_ergebnisdatei, test_alte_ergebnisdatei_im_fenster,
              test_ergebnis_passt_nicht_mehr, test_ergebnis_passt_nach_stand):
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
