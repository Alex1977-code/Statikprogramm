"""
Test der Stellungen des Systems (bewegliche Bruecken): Kinematik, abgeleitetes
Modell je Stellung, Umhuellende der Nachweise, Speichern/Laden.
Aufruf:  python -m tests.test_stellungen      (auch mit pytest lauffaehig)
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d.model import Model, Material, Section, Support, Stellung  # noqa: E402
from statik3d import stellungen as ST  # noqa: E402
from statik3d.elements import beam3d as bm  # noqa: E402
from statik3d.examples_lib import build_example  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"{'OK ' if ok else 'FAIL'} {name:58s} {detail}")
    return ok


def _assert_since(n0):
    failed = [r[0] for r in RESULTS[n0:] if not r[1]]
    assert not failed, "fehlgeschlagen: " + ", ".join(failed)


def kragarm(angle=0.0, n=8, L=8.0) -> Model:
    """Kragarm laengs x, Drehachse im Ursprung laengs y, alles beweglich."""
    m = Model("Kragarm")
    m.add_material(Material.steel("S355"))
    m.add_section(Section.from_profile("HEB 300"))
    ids = [m.add_node(i * L / n, 0.0, 0.0) for i in range(n + 1)]
    for i in range(n):
        m.add_element("beam", [ids[i], ids[i + 1]], "S355", "HEB 300", group="klappe")
    m.add_member("HT", list(range(n)), beta_y=1.0, beta_z=1.0)
    m.fix(ids[0], "all")
    for e in range(n):
        m.load_beam(e, qz=-5000.0)
    m.add_combination("GZT", {"LF1": 1.35}, "ULS")
    m.add_stellung("S1", "zu", "rotate", angle=0.0, axis_point=[0, 0, 0],
                   axis_dir=[0, -1, 0], moving_groups=["klappe"])
    m.add_stellung("S2", "auf", "rotate", angle=angle or 60.0, axis_point=[0, 0, 0],
                   axis_dir=[0, -1, 0], moving_groups=["klappe"])
    return m


# --------------------------------------------------------------------------
def test_drehmatrix():
    n0 = len(RESULTS)
    R = ST.rotation_matrix([0, 0, 1], 90.0)
    check("Drehung 90 Grad um z bildet x auf y ab",
          np.allclose(R @ [1, 0, 0], [0, 1, 0], atol=1e-12))
    check("Drehmatrix ist orthogonal", np.allclose(R.T @ R, np.eye(3), atol=1e-12))
    check("Drehmatrix hat Determinante 1", abs(np.linalg.det(R) - 1.0) < 1e-12)
    R2 = ST.rotation_matrix([1, 2, 3], 37.0)
    check("beliebige Achse: orthogonal", np.allclose(R2.T @ R2, np.eye(3), atol=1e-12))
    check("Achsrichtung bleibt fest",
          np.allclose(R2 @ np.array([1, 2, 3.0]), [1, 2, 3.0], atol=1e-12))
    try:
        ST.rotation_matrix([0, 0, 0], 10.0)
        ok = False
    except ValueError:
        ok = True
    check("Nullvektor als Achse wird abgewiesen", ok)
    _assert_since(n0)


def test_kinematik():
    n0 = len(RESULTS)
    m = kragarm(angle=90.0)
    st = m.stellungen["S2"]
    nodes, mask = ST.transform_nodes(m, st)
    check("alle Knoten der bewegten Gruppe bewegen sich", mask.all())
    check("Drehung 90 Grad stellt den Kragarm auf",
          np.allclose(nodes[-1], [0.0, 0.0, 8.0], atol=1e-9),
          f"Spitze {np.round(nodes[-1], 6)}")
    check("Drehpunkt bleibt liegen", np.allclose(nodes[0], [0, 0, 0], atol=1e-12))
    L0 = np.linalg.norm(m.nodes[1] - m.nodes[0])
    L1 = np.linalg.norm(nodes[1] - nodes[0])
    check("Starrkoerperbewegung erhaelt die Laengen", abs(L0 - L1) < 1e-12)

    # Stellung ohne Bewegung
    nodes0, _ = ST.transform_nodes(m, m.stellungen["S1"])
    check("Stellung mit 0 Grad laesst die Geometrie unveraendert",
          np.allclose(nodes0, m.nodes, atol=1e-15))

    # Verschiebung (Hubbruecke)
    m.add_stellung("H", "gehoben", "translate", moving_groups=["klappe"],
                   axis_dir=[0, 0, 1])
    m.stellungen["H"].shift = 2.5
    nodes_h, _ = ST.transform_nodes(m, m.stellungen["H"])
    check("Hubstellung verschiebt um den vollen Betrag",
          np.allclose(nodes_h - m.nodes, [0, 0, 2.5], atol=1e-12))

    # Nur ein Teil bewegt sich
    m2 = kragarm(angle=45.0)
    m2.stellungen["S2"].moving_groups = []
    m2.stellungen["S2"].moving_nodes = [5, 6, 7, 8]
    _, mask2 = ST.transform_nodes(m2, m2.stellungen["S2"])
    check("nur die genannten Knoten bewegen sich",
          mask2.sum() == 4 and mask2[5] and not mask2[4])
    _assert_since(n0)


def test_querschnittslage():
    """Der roll-Winkel muss die Starrkoerperdrehung mitmachen - sonst dreht
    sich der Steg des Profils gegenueber dem Bauteil."""
    n0 = len(RESULTS)
    for angle in (30.0, 90.0, 82.0):
        m = kragarm(angle=angle)
        st = m.stellungen["S2"]
        d = ST.derive_model(m, st)
        R = ST.rotation_matrix(st.axis_dir, st.angle)
        ok = True
        for i, e in enumerate(m.elements):
            T0, _ = bm.local_axes(m.nodes[e.nodes[0]], m.nodes[e.nodes[1]], e.roll)
            Tn, _ = bm.local_axes(d.nodes[e.nodes[0]], d.nodes[e.nodes[1]],
                                  d.elements[i].roll)
            ok = ok and np.allclose(R @ T0[1], Tn[1], atol=1e-9) \
                and np.allclose(R @ T0[2], Tn[2], atol=1e-9)
        check(f"Querschnittslage folgt der Drehung ({angle:g} Grad)", ok)
    # ohne Bewegung darf sich der roll nicht aendern
    m = kragarm(angle=0.0)
    d = ST.derive_model(m, m.stellungen["S1"])
    check("unbewegte Stellung laesst roll unveraendert",
          all(a.roll == b.roll for a, b in zip(m.elements, d.elements)))
    _assert_since(n0)


def test_abgeleitetes_modell():
    n0 = len(RESULTS)
    m = kragarm(angle=60.0)
    st = m.stellungen["S2"]
    st.supports = [Support(4, [2])]
    d = ST.derive_model(m, st)
    check("Lager der Stellung treten hinzu", len(d.supports) == len(m.supports) + 1)
    st.use_model_supports = False
    d2 = ST.derive_model(m, st)
    check("Modelllager koennen ersetzt werden",
          len(d2.supports) == 1 and d2.supports[0].node == 4)
    check("abgeleitetes Modell traegt keine Stellungen mehr", not d2.stellungen)
    check("Ausgangsmodell bleibt unveraendert",
          len(m.supports) == 1 and np.allclose(m.nodes[-1], [8, 0, 0]))

    # Lastfallauswahl
    m.add_load_case("Verkehr", "Q_G", "nur zu")
    m.load_beam(0, qz=-3000.0)
    m.add_combination("GZT_V", {"LF1": 1.35, "Verkehr": 1.5}, "ULS")
    st.use_model_supports = True
    st.cases = ["LF1"]
    log = []
    d3 = ST.derive_model(m, st, log=log)
    check("nicht wirkende Lastfaelle entfallen", list(d3.load_cases) == ["LF1"])
    check("Kombination mit fehlendem Lastfall entfaellt", "GZT_V" not in d3.combinations)
    check("uebrige Kombination bleibt", "GZT" in d3.combinations)
    check("Protokoll nennt die Streichungen", len(log) == 2, str(log))
    check("aktiver Lastfall bleibt gueltig", d3.active_case in d3.load_cases)
    _assert_since(n0)


def test_umhuellende():
    n0 = len(RESULTS)
    m = kragarm(angle=75.0)
    sa = ST.solve_stellungen(m, design=True, fatigue=False)
    check("beide Stellungen gerechnet", sa.stellungen == ["S1", "S2"])
    check("je Stellung eine Analyse", len(sa.analyses) == 2)
    me = sa.members.get("HT")
    check("Stab in der Umhuellenden enthalten", me is not None)
    check("Ausnutzung je Stellung erfasst", set(me.per_stellung) == {"S1", "S2"})
    check("Umhuellende nimmt das Maximum",
          abs(me.util - max(me.per_stellung.values())) < 1e-12,
          f"{me.util:.4f} = max{tuple(round(v, 4) for v in me.per_stellung.values())}")
    check("massgebende Stellung ist die mit dem Maximum",
          me.per_stellung[me.stellung] == max(me.per_stellung.values()))
    check("Kragarm ist geschlossen staerker ausgenutzt als aufgestellt",
          me.per_stellung["S1"] > me.per_stellung["S2"],
          f"S1={me.per_stellung['S1']:.3f} > S2={me.per_stellung['S2']:.3f}")
    kurve = sa.curve("HT")
    check("Kurve liefert Winkel und Ausnutzung je Stellung",
          len(kurve) == 2 and kurve[1][1] == 75.0)
    check("Tabelle hat Kopfzeile und je Stab eine Zeile", len(sa.table()) == 2)
    check("Zusammenfassung nennt die massgebende Stellung",
          me.stellung in sa.summary())
    check("Ausnutzung ueber die Stellungen", set(sa.util_by_stellung()) == {"S1", "S2"})

    # nur eine Auswahl rechnen
    sa2 = ST.solve_stellungen(m, design=True, only=["S2"])
    check("Auswahl einzelner Stellungen moeglich", sa2.stellungen == ["S2"])
    # inaktive Stellungen bleiben aussen vor
    m.stellungen["S2"].active = False
    sa3 = ST.solve_stellungen(m, design=True)
    check("inaktive Stellung wird uebergangen", sa3.stellungen == ["S1"])
    m.stellungen["S1"].active = False
    try:
        ST.solve_stellungen(m, design=True)
        ok = False
    except ValueError:
        ok = True
    check("ohne aktive Stellung meldet der Aufruf einen Fehler", ok)
    _assert_since(n0)


def test_speichern_laden(tmp=None):
    n0 = len(RESULTS)
    m = kragarm(angle=60.0)
    m.stellungen["S2"].supports = [Support(3, [2], None, None)]
    m.stellungen["S2"].cases = ["LF1"]
    m.stellungen["S2"].description = "Antrieb haelt"
    d = json.loads(json.dumps(m.to_dict()))
    m2 = Model.from_dict(d)
    check("Stellungen ueberstehen Speichern/Laden", list(m2.stellungen) == ["S1", "S2"])
    s2 = m2.stellungen["S2"]
    check("Winkel erhalten", s2.angle == 60.0)
    check("Drehachse erhalten", s2.axis_dir == [0, -1, 0])
    check("bewegtes Bauteil erhalten", s2.moving_groups == ["klappe"])
    check("Lager der Stellung erhalten",
          len(s2.supports) == 1 and s2.supports[0].node == 3
          and isinstance(s2.supports[0], Support))
    check("Lastfallauswahl erhalten", s2.cases == ["LF1"])
    check("Beschreibung erhalten", s2.description == "Antrieb haelt")
    check("aktive Stellung erhalten", m2.active_stellung == m.active_stellung)
    check("Modell ohne Stellungen laedt weiterhin",
          not Model.from_dict({k: v for k, v in d.items()
                               if k not in ("stellungen", "active_stellung")}).stellungen)
    check("copy() uebernimmt die Stellungen", list(m.copy().stellungen) == ["S1", "S2"])
    _assert_since(n0)


def test_pruefung():
    n0 = len(RESULTS)
    m = kragarm(angle=30.0)
    check("gueltiges Modell ohne Beanstandung zu den Stellungen",
          not [x for x in m.check() if "Stellung" in x], str(m.check()))
    m.stellungen["S2"].moving_nodes = [999]
    check("unbekannter Knoten wird gemeldet",
          any("999" in x and "FEHLER" in x for x in m.check()))
    m.stellungen["S2"].moving_nodes = []
    m.stellungen["S2"].cases = ["gibtsnicht"]
    check("unbekannter Lastfall wird gemeldet",
          any("gibtsnicht" in x and "FEHLER" in x for x in m.check()))
    m.stellungen["S2"].cases = []
    m.stellungen["S2"].moving_groups = ["fehlt"]
    check("unbekannte Elementgruppe wird als Warnung gemeldet",
          any("fehlt" in x and "WARNUNG" in x for x in m.check()))
    m.stellungen["S2"].moving_groups = ["klappe"]
    m.stellungen["S2"].use_model_supports = False
    check("Stellung ohne jede Lagerung wird gemeldet",
          any("keine Lagerung" in x for x in m.check()))
    m.stellungen["S2"].use_model_supports = True
    for s in m.stellungen.values():
        s.active = False
    check("keine aktive Stellung wird gemeldet",
          any("keine Stellung aktiv" in x for x in m.check()))
    _assert_since(n0)


def test_serie():
    n0 = len(RESULTS)
    m = kragarm(angle=60.0)
    vorlage = m.stellungen["S2"]
    neu = ST.series(m, "A", 0.0, 82.0, 6, template=vorlage)
    check("Serie legt die gewuenschte Anzahl an", len(neu) == 6)
    check("Serie laeuft von Anfangs- bis Endwinkel",
          neu[0].angle == 0.0 and neu[-1].angle == 82.0)
    check("Zwischenwerte gleichmaessig verteilt",
          abs(neu[1].angle - 82.0 / 5) < 1e-9)
    check("Serie uebernimmt die Drehachse", neu[3].axis_dir == vorlage.axis_dir)
    check("Serie uebernimmt das bewegte Bauteil",
          neu[3].moving_groups == vorlage.moving_groups)
    check("Serie liegt im Modell", all(s.name in m.stellungen for s in neu))
    try:
        ST.series(m, "B", 0.0, 10.0, 1)
        ok = False
    except ValueError:
        ok = True
    check("Serie mit einem Schritt wird abgewiesen", ok)
    _assert_since(n0)


def test_beispiel_klappbruecke():
    n0 = len(RESULTS)
    m = build_example("bascule")
    check("Beispiel bringt fuenf Stellungen mit", len(m.stellungen) == 5)
    check("Beispiel ist ohne Beanstandung", not m.check(), str(m.check()))
    check("bewegtes Bauteil erkannt",
          ST.moved_elements(m, m.stellungen["S3"]) == len(m.elements))
    sa = ST.solve_stellungen(m, design=True, fatigue=True)
    check("alle fuenf Stellungen gerechnet", len(sa.analyses) == 5)
    u = sa.util_by_stellung()
    check("jede Stellung liefert eine Ausnutzung",
          all(0.0 < u[n] < 1.0 for n in sa.stellungen),
          " ".join(f"{n}={u[n]:.3f}" for n in sa.stellungen))
    check("alle Nachweise erfuellt", sa.util_max <= 1.0, f"max {sa.util_max:.3f}")
    check("massgebend ist nicht die Endlage",
          sa.worst().stellung != "S5",
          f"massgebend {sa.worst().stellung} ({sa.worst().member})")
    check("Verkehr wirkt nur in der Verkehrsstellung",
          "Verkehr" in sa.models["S1"].load_cases
          and "Verkehr" not in sa.models["S3"].load_cases)
    check("geoeffnete Stellung hat weniger Kombinationen",
          len(sa.models["S3"].combinations) < len(sa.models["S1"].combinations))
    check("Endauflager nur in der Verkehrsstellung",
          len(sa.models["S1"].supports) > len(sa.models["S3"].supports))
    _assert_since(n0)


def main():
    for fn in (test_drehmatrix, test_kinematik, test_querschnittslage,
               test_abgeleitetes_modell, test_umhuellende, test_speichern_laden,
               test_pruefung, test_serie, test_beispiel_klappbruecke):
        print(f"\n--- {fn.__name__} ---")
        fn()
    bad = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} in Ordnung")
    if bad:
        print("fehlgeschlagen: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
