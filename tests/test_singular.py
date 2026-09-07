"""
Singularitaeten: **welches** Bauteil kann sich **wie** bewegen - und was
geht dabei ins Nichts.

Geprueft wird gegen geschlossene Werte, nicht gegen „ungefaehr":

* **Der freie Wuerfel.** Ein Hexaeder ohne jedes Lager hat genau sechs
  Starrkoerperbewegungen. Die unausgeglichene Last in jeder davon steht in
  einer Zeile: Kraft = (Summe F)·t, Moment = (Summe r x F)·omega. Fuer eine
  Last, die in sich im Gleichgewicht steht, muss beides **exakt null** sein;
  fuer eine Einzelkraft F am Eckknoten (1,1,1) sind es F in z und F/2 um x
  und um y - nachgerechnet mit dem Hebelarm 0,5 m zum Schwerpunkt.
* **Rechnen statt abbrechen.** Dasselbe Modell mit einer Netto-Last ist
  singulaer. Es wird trotzdem geloest: jede Bewegung bekommt eine
  Hilfsfesselung k·v v^T. Weil K·v = 0 ist, faelscht das nichts - und das
  laesst sich nachrechnen. Die Fesselung verteilt die Restkraft wie eine
  Massenkraft auf die Knoten (v ist die gleichfoermige Verschiebung); durch
  den Mittelschnitt geht darum genau die halbe Last, und die Verlaengerung
  muss (F/2)·L/(E·A) sein. Der trilineare Hexaeder bildet diesen
  gleichfoermigen Dehnungszustand **exakt** ab, die Schranke ist darum 1e-9
  und nicht ein Prozent.
* **Kontakt.** Ein Wuerfel auf einer Unterlage, reibungsfrei: er gleitet in
  x und y und dreht sich um z - drei Bewegungen, nicht sechs und nicht null.
  Haelt man ihn seitlich, bleibt die Frage, ob er **abhebt**; und die
  entscheidet die Last: unter Druck bleibt er liegen (null), unter Zug gehen
  genau die gezogenen 100 kN ins Nichts. Ohne dieses Vorzeichen stuende jedes
  Bauteil unter Eigengewicht als abhebend da.
* **Stufe 2.** Zwei Wuerfel, die sich nur **einen** Knoten teilen, haengen
  topologisch zusammen - die Teiltragwerkssuche sieht nichts. Beweglich ist
  der zweite trotzdem: er dreht sich um den gemeinsamen Knoten. Hier muss die
  Matrixdiagnose das Bauteil beim Namen nennen.

Aufruf:  python -m tests.test_singular
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from statik3d import assemble as asm, singular as sg, solver     # noqa: E402
from statik3d.model import ContactPair, ContactSupport, Material, Model  # noqa: E402

RESULTS = []

E_STAHL = 210e9          # N/m^2 - S235
A_WUERFEL = 1.0          # m^2   - Kantenflaeche des Einheitswuerfels
L_WUERFEL = 1.0          # m
F_LAST = 1.0e6           # N
M_TORSION = 1.0e3        # Nm  - Torsionsmoment am freien Stab
L_STAB = 2.0             # m   - Länge des freien Stabes


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'OK ' if ok else 'FEHLER'} {name:62s} {detail}")
    return bool(ok)


def close(name, got, want, tol, unit=""):
    ok = abs(float(got) - float(want)) <= tol
    abw = abs(got - want) / abs(want) * 100 if want else 0.0
    return check(name, ok, f"{got:.8g}{unit} / {want:.8g}{unit}  Abw. {abw:.6f} %")


# --------------------------------------------------------------------------
# Baukasten
# --------------------------------------------------------------------------
def wuerfel(name: str = "Würfel") -> Model:
    """Ein Einheitswuerfel als ein Hexaeder - ohne jedes Lager."""
    m = Model()
    m.add_material(Material.steel("S235"))
    m.add_nodes(np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                          [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]]))
    m.add_element("hex8", list(range(8)), "S235", group=name)
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    return m


def auf_unterlage(seitlich: bool = False, mu: float = 0.0,
                  last: float = 0.0, quer: float = 0.0) -> Model:
    """Ein Wuerfel auf einem festen, breiteren Block - Kontakt dazwischen.

    Der Block ist absichtlich groesser als der Wuerfel: liegen die
    Slave-Knoten auf einer Kante der Master-Facetten, ist die naechste
    Facette nicht eindeutig und die Normale koennte zur Seite zeigen. So
    liegen sie im Inneren der Oberseite.
    """
    m = Model()
    m.add_material(Material.steel("S235"))
    a, b = -1.0, 2.0
    unten = np.array([[a, a, 0], [b, a, 0], [b, b, 0], [a, b, 0],
                      [a, a, 1], [b, a, 1], [b, b, 1], [a, b, 1.]])
    oben = np.array([[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.],
                     [0, 0, 2], [1, 0, 2], [1, 1, 2], [0, 1, 2.]])
    m.add_nodes(np.vstack([unten, oben]))
    m.add_element("hex8", list(range(8)), "S235", group="Unten")
    m.add_element("hex8", list(range(8, 16)), "S235", group="Oben")
    for k in range(4):
        m.fix(k, [0, 1, 2])
    if seitlich:
        for k in (8, 9, 10, 11):
            m.fix(k, [0, 1])
    m.contact_pairs.append(ContactPair("Fuge", slave_nodes=[8, 9, 10, 11],
                                       master_elements=[0], mu=mu))
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    for k in (12, 13, 14, 15):
        if last or quer:
            m.load_node(k, Fz=last / 4.0, Fx=quer / 4.0)
    return m


def bewegungen(m: Model) -> list:
    """Die freien Bewegungen mit der unausgeglichenen Last des Lastfalls."""
    s = sg.restfreiheiten(m)
    return sg.auswerten(m, s, asm.load_vector(m, m.case("LF1")))


def je_art(sing: list, art: str) -> list:
    return [x for x in sing if x.art == art]


# --------------------------------------------------------------------------
# 1) Der freie Wuerfel: sechs Bewegungen, und was in ihnen ins Nichts geht
# --------------------------------------------------------------------------
def test_freier_wuerfel():
    m = wuerfel()
    m.load_node(6, Fz=F_LAST)
    s = bewegungen(m)
    check("ein Bauteil ohne Lager hat genau sechs Starrkörperbewegungen",
          len(s) == 6 and all(x.art == "gleitet" for x in s), f"{len(s)} Bewegungen")
    check("jede nennt das Bauteil beim Namen",
          all(x.koerper == ["Würfel"] for x in s), str(s[0].koerper))
    check("drei Verschiebungen und drei Drehungen",
          sum(1 for x in s if x.verschiebung()) == 3,
          "; ".join(x.text for x in s[:1]))

    # Einzelkraft F in z am Eckknoten (1, 1, 1); Schwerpunkt (0,5 | 0,5 | 0,5)
    zug = [x for x in s if x.verschiebung() and abs(x.t[2]) > 0.99][0]
    close("Verschiebung in z: unausgeglichen ist genau die Last",
          zug.kraft, F_LAST, 1e-6, " N")
    quer = [x for x in s if x.verschiebung() and abs(x.t[0]) > 0.99][0]
    check("quer dazu geht nichts ins Nichts", quer.kraft == 0.0, f"{quer.kraft:g} N")
    for achse, i in (("x", 0), ("y", 1)):
        dreh = [x for x in s if not x.verschiebung() and abs(x.omega[i]) > 1e-9][0]
        close(f"Drehung um {achse}: Hebelarm 0,5 m mal F",
              dreh.moment, 0.5 * F_LAST, 1e-6, " Nm")
    drehz = [x for x in s if not x.verschiebung() and abs(x.omega[2]) > 1e-9][0]
    check("um die Lastachse selbst kein Moment", drehz.moment == 0.0,
          f"{drehz.moment:g} Nm")

    # dieselbe Last, in sich im Gleichgewicht
    m2 = wuerfel()
    for k in (4, 5, 6, 7):
        m2.load_node(k, Fz=F_LAST / 4)
    for k in (0, 1, 2, 3):
        m2.load_node(k, Fz=-F_LAST / 4)
    s2 = bewegungen(m2)
    check("Last im Gleichgewicht: in keiner Bewegung geht etwas ins Nichts",
          all(x.kraft == 0.0 and x.moment == 0.0 for x in s2),
          f"max {max(x.kraft for x in s2):g} N")
    check("und der Befund sagt genau das",
          all("Gleichgewicht" in x.befund() for x in s2), s2[0].befund()[:60])


# --------------------------------------------------------------------------
# 2) Rechnen statt abbrechen
# --------------------------------------------------------------------------
def test_rechnen_statt_abbrechen():
    # a) Last im Gleichgewicht - die Rechnung ist gueltig
    m = wuerfel()
    for k in (4, 5, 6, 7):
        m.load_node(k, Fz=F_LAST / 4)
    for k in (0, 1, 2, 3):
        m.load_node(k, Fz=-F_LAST / 4)
    r = solver.solve_static(m, case="LF1")
    soll = F_LAST * L_WUERFEL / (E_STAHL * A_WUERFEL)
    close("freier Würfel im Gleichgewicht: Dehnung N·L/(E·A)",
          r.u[4, 2] - r.u[0, 2], soll, 1e-9 * soll, " m")

    # b) Netto-Last - ohne Hilfsfesselung waere hier Schluss
    m2 = wuerfel()
    for k in (4, 5, 6, 7):
        m2.load_node(k, Fz=F_LAST / 4)
    r2 = solver.solve_static(m2, case="LF1")
    check("mit Netto-Last wird gerechnet statt abgebrochen",
          r2.u is not None and np.all(np.isfinite(r2.u)))
    check("und es steht dabei, dass gefesselt wurde",
          all(x.gefesselt for x in r2.singular), f"{len(r2.singular)} Bewegungen")
    # Die Fesselung verteilt die Restkraft gleichmaessig auf alle acht Knoten:
    # oben bleiben F/4 - F/8, unten -F/8, durch den Mittelschnitt geht F/2.
    soll2 = 0.5 * F_LAST * L_WUERFEL / (E_STAHL * A_WUERFEL)
    close("Netto-Last: durch den Mittelschnitt geht genau die halbe Last",
          r2.u[4, 2] - r2.u[0, 2], soll2, 1e-9 * soll2, " m")
    close("Spannung sigma_z = (F/2)/A", r2.solid_res[0][2],
          0.5 * F_LAST / A_WUERFEL, 1e-6 * F_LAST, " N/m²")
    # Vor dem Bereinigen liegt der Starrkoerperanteil bei F/k und damit um
    # Groessenordnungen ueber der Dehnung; uebrig bleiben darf davon nichts,
    # was neben der Dehnung noch sichtbar waere.
    check("der willkürliche Starrkörperanteil ist herausgerechnet",
          abs(float(r2.u[:, 2].mean())) < 1e-6 * soll2,
          f"mittleres u_z = {r2.u[:, 2].mean():.3g} m gegen {soll2:.3g} m Dehnung")
    zug = [x for x in r2.singular if x.verschiebung() and abs(x.t[2]) > 0.99][0]
    close("und die Meldung nennt die Last, die ins Nichts geht",
          zug.kraft, F_LAST, 1e-6, " N")
    check("das Ergebnis trägt die Meldung mit",
          len(r2.info.get("singularitaeten") or []) == 6
          and r2.info["singularitaeten"][0]["kraft"] > 0.0,
          str(sorted((r2.info.get("singularitaeten") or [{}])[0])))

    # c) gelagert: kein Wort davon
    m3 = wuerfel()
    for k in range(4):
        m3.fix(k, [0, 1, 2])
    m3.load_node(6, Fz=-F_LAST)
    r3 = solver.solve_static(m3, case="LF1")
    check("ein gelagertes Bauteil meldet gar nichts",
          not r3.singular and "singularitaeten" not in r3.info,
          str(r3.info.get("singularitaeten")))


# --------------------------------------------------------------------------
# 3) Kontakt: gleiten, abheben, Reibung
# --------------------------------------------------------------------------
def test_stab_dreht_sich_um_die_eigene_achse():
    """Die Hilfsfesselung muss die Verdrehungs-FHG mitnehmen.

    Bei der Drehung eines Stabes um seine **eigene** Achse verschiebt sich
    kein Knoten - die Bewegung steht allein in den Knotenverdrehungen. Eine
    Fesselung nur über die Verschiebungen fände hier gar nichts, und das
    System bliebe singulär. Geprüft wird mit der geschlossenen Lösung der
    Saint-Venantschen Torsion, φ = M·L/(G·I_t):

    * bei einem Torsionsmoment, das in sich im Gleichgewicht steht (+M am
      einen, −M am anderen Ende), geht das volle M durch den Stab;
    * bei einem einseitigen M verteilt die Fesselung die Restwirkung
      gleichmäßig auf beide Knoten - durch den Stab geht dann M/2, und genau
      das M wird als unausgeglichen gemeldet.
    """
    from statik3d.profiles import make_section

    def freierstab(mx: float, gleichgewicht: bool):
        m = Model()
        m.add_material(Material.steel("S235"))
        m.add_section(make_section("IPE 200"))
        a, b = m.add_node(0, 0, 0), m.add_node(L_STAB, 0, 0)
        m.add_element("beam", [a, b], "S235", "IPE 200", group="Stab")
        lc = m.add_load_case("LF1")
        lc.gravity = [0, 0, 0]
        m.load_node(b, Mx=mx)
        if gleichgewicht:
            m.load_node(a, Mx=-mx)
        return m, a, b

    sec = make_section("IPE 200")
    mat = Material.steel("S235")
    G = mat.E / (2 * (1 + mat.nu))

    m, a, b = freierstab(M_TORSION, True)
    r = solver.solve_static(m, case="LF1")
    check("ein ungelagerter Stab wird gerechnet statt abgewiesen",
          np.all(np.isfinite(r.u)) and len(r.singular) == 6,
          f"{len(r.singular)} Bewegungen")
    check("die Drehung um die eigene Stabachse steht in der Liste",
          any(not x.verschiebung() and abs(x.omega[0]) > 1e-9 for x in r.singular),
          "; ".join(x.text for x in r.singular if not x.verschiebung()))
    soll = M_TORSION * L_STAB / (G * sec.It)
    close("Torsion im Gleichgewicht: Verdrillung M·L/(G·I_t)",
          r.u[b, 3] - r.u[a, 3], soll, 1e-9 * soll, " rad")
    check("und nichts geht ins Nichts",
          all(x.kraft == 0.0 and x.moment == 0.0 for x in r.singular),
          f"max {max(x.moment for x in r.singular):g} Nm")

    m2, a2, b2 = freierstab(M_TORSION, False)
    r2 = solver.solve_static(m2, case="LF1")
    # Hier trägt das System nicht mehr von allein: ohne Fesselung wäre Schluss,
    # und zwar an der Drehung um die eigene Achse - die einzige Bewegung, die
    # ausschließlich in den Knotenverdrehungen steht.
    check("bei einseitigem Moment hält erst die Hilfsfesselung das System",
          all(x.gefesselt for x in r2.singular) and len(r2.singular) == 6,
          f"{sum(1 for x in r2.singular if x.gefesselt)} von {len(r2.singular)}")
    close("einseitiges Torsionsmoment: durch den Stab geht die Hälfte",
          r2.u[b2, 3] - r2.u[a2, 3], 0.5 * soll, 1e-9 * soll, " rad")
    dreh = [x for x in r2.singular if not x.verschiebung() and abs(x.omega[0]) > 1e-9][0]
    close("und das ganze Moment wird als unausgeglichen gemeldet",
          dreh.moment, M_TORSION, 1e-6, " Nm")


def test_bericht_nennt_die_grenze():
    """Der Bericht muss sagen, wofür das Ergebnis nicht gilt."""
    from statik3d.report import Report
    m = wuerfel()
    for k in (4, 5, 6, 7):
        m.load_node(k, Fz=F_LAST / 4)
    r = solver.solve_static(m, case="LF1")
    html = Report(m, results=r).html()
    check("der Bericht führt die freien Bewegungen als eigenes Kapitel",
          "Freie Bewegungen" in html and "Hilfsfesselung" in html)
    check("mit der Last, die ins Nichts geht",
          "1000.000" in html or "1000" in html,
          "Kraftspalte in kN")
    check("und als Warnung, damit es niemand übersieht",
          "nicht verwertbar" in html, "")


def test_kontakt_gleitet():
    s = bewegungen(auf_unterlage())
    check("reibungsfrei auf der Unterlage: drei Bewegungen, alle gleitend",
          len(s) == 3 and all(x.art == "gleitet" for x in s),
          "; ".join(x.text for x in s))
    check("nur das obere Bauteil, nicht die Unterlage",
          all(x.koerper == ["Oben"] for x in s), str([x.koerper for x in s]))
    richtungen = sorted(int(np.argmax(np.abs(x.t))) for x in s if x.verschiebung())
    check("es gleitet in x und y, nicht in z", richtungen == [0, 1], str(richtungen))
    dreh = [x for x in s if not x.verschiebung()]
    check("und dreht sich um die Fugennormale z",
          len(dreh) == 1 and abs(dreh[0].omega[2]) > 0.99 * np.linalg.norm(dreh[0].omega),
          str(np.round(dreh[0].omega, 3)))
    check("die Ursache nennt die Fuge",
          all("Fuge" in x.ursache for x in s), s[0].ursache[:70])


def test_kontakt_hebt_ab():
    # seitlich gehalten: in der Fugenebene ist nichts mehr frei
    s = bewegungen(auf_unterlage(seitlich=True))
    check("seitlich gehalten: keine gleitende Bewegung mehr",
          not je_art(s, "gleitet"), str([x.art for x in s]))
    check("aber abheben kann es - der Kegel findet es",
          len(je_art(s, "hebt ab")) == 1, str([x.text for x in s]))

    druck = bewegungen(auf_unterlage(seitlich=True, last=-F_LAST))[0]
    check("unter Druck bleibt es liegen: nichts geht ins Nichts",
          druck.kraft == 0.0 and druck.moment == 0.0,
          f"{druck.kraft:g} N / {druck.moment:g} Nm")
    check("und der Befund sagt, warum", "drückt in die Fuge" in druck.befund(),
          druck.befund()[:60])

    zug = bewegungen(auf_unterlage(seitlich=True, last=F_LAST))[0]
    close("unter Zug geht genau die gezogene Last ins Nichts",
          zug.kraft, F_LAST, 1e-6, " N")
    check("und die Bewegung ist das reine Abheben in z",
          zug.verschiebung() and abs(zug.t[2]) > 0.999,
          str(np.round(zug.t, 4)))

    # Querlast: der Wuerfel kippt um y; Hebelarm 0,5 m ueber der Fuge
    quer = bewegungen(auf_unterlage(seitlich=True, quer=F_LAST))[0]
    close("Querlast: das Kippmoment ist F mal dem Hebelarm 0,5 m",
          quer.moment, 0.5 * F_LAST, 1e-6, " Nm")


def test_reibung_und_einseitige_lager():
    s = bewegungen(auf_unterlage(mu=0.2))
    check("mit Reibbeiwert hält die Fugenebene - kein Gleiten mehr",
          not je_art(s, "gleitet"), str([x.text for x in s]))
    check("abheben bleibt möglich", len(je_art(s, "hebt ab")) == 1,
          str([x.art for x in s]))

    # Einseitige Knotenlager statt Kontaktpaar - dieselbe Aussage
    m = wuerfel("Klotz")
    for k in range(4):
        m.contact_supports.append(ContactSupport(k, [0, 0, 1.0]))
    s2 = sg.restfreiheiten(m)
    gleit = je_art(s2, "gleitet")
    check("einseitige Knotenlager halten senkrecht, nicht in der Ebene",
          len(gleit) == 3, f"{len(gleit)} gleitende von {len(s2)}")
    richtungen = sorted(int(np.argmax(np.abs(x.t))) for x in gleit if x.verschiebung())
    check("es gleitet in x und y", richtungen == [0, 1], str(richtungen))


def test_lagerausfall_kennt_die_richtung():
    """„Ausfall bei Zug" lässt nach oben los, „Ausfall bei Druck" nach unten.

    Ohne dieses Vorzeichen stünde dasselbe Lager einmal als haltend und
    einmal als offen da, je nachdem wie seine Achse zufällig zeigt. Geprüft
    wird mit der Last, die das Lösen antreibt: dann muss die gefundene
    Bewegung das reine Abheben (bzw. Absinken) sein und genau die aufgebrachte
    Kraft ins Nichts gehen.
    """
    for ausfall, vz in (("zug", +1.0), ("druck", -1.0)):
        m = wuerfel("Klotz")
        for k in range(4):
            m.support(k, [0, 1, 2], uz=dict(failure=ausfall))
        for k in (4, 5, 6, 7):
            m.load_node(k, Fz=vz * F_LAST / 4)
        s = [x for x in bewegungen(m) if x.art == "hebt ab"]
        wohin = "oben" if vz > 0 else "unten"
        check(f"Ausfall bei {ausfall}: das Teil löst sich nach {wohin}",
              len(s) == 1 and s[0].verschiebung() and vz * s[0].t[2] > 0.999,
              str(np.round(s[0].t, 4)) if s else "keine Bewegung gefunden")
        close(f"Ausfall bei {ausfall}: die treibende Last geht ins Nichts",
              s[0].kraft if s else 0.0, F_LAST, 1e-6, " N")
        # in der Gegenrichtung hält dasselbe Lager
        m2 = wuerfel("Klotz")
        for k in range(4):
            m2.support(k, [0, 1, 2], uz=dict(failure=ausfall))
        for k in (4, 5, 6, 7):
            m2.load_node(k, Fz=-vz * F_LAST / 4)
        s2 = [x for x in bewegungen(m2) if x.art == "hebt ab"]
        check(f"Ausfall bei {ausfall}: in der Gegenrichtung hält es",
              len(s2) == 1 and s2[0].kraft == 0.0,
              f"{s2[0].kraft:g} N" if s2 else "keine Bewegung gefunden")


# --------------------------------------------------------------------------
# 4) Stufe 2: was die Topologie nicht sieht
# --------------------------------------------------------------------------
def test_stufe2_nennt_das_bauteil():
    """Zwei Würfel an **einem** gemeinsamen Knoten: topologisch ein Teil."""
    m = Model()
    m.add_material(Material.steel("S235"))
    A = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1.]])
    B = np.array([[2, 1, 0], [2, 2, 0], [1, 2, 0],
                  [1, 1, 1], [2, 1, 1], [2, 2, 1], [1, 2, 1.]])
    m.add_nodes(np.vstack([A, B]))
    m.add_element("hex8", [0, 1, 2, 3, 4, 5, 6, 7], "S235", group="A")
    #   Knoten 2 = (1|1|0) ist der einzige gemeinsame Punkt
    m.add_element("hex8", [2, 8, 9, 10, 11, 12, 13, 14], "S235", group="B")
    for k in range(4):
        m.fix(k, [0, 1, 2])
    lc = m.add_load_case("LF1")
    lc.gravity = [0, 0, 0]
    m.load_node(13, Fz=-1000.0)
    from statik3d import diagnose as dg
    d = dg.diagnose(m)
    check("die Topologie sieht ein einziges, gelagertes Teiltragwerk",
          d["teile"] == 1 and not d["ohne_lager"], str(d["teile"]))
    check("Stufe 1 findet folgerichtig keine Starrkörperbewegung",
          not sg.restfreiheiten(m), str(sg.restfreiheiten(m)))
    try:
        solver.solve_static(m, case="LF1")
        check("das singuläre System wird gemeldet", False, "keine Meldung")
    except RuntimeError as ex:
        check("die Matrixdiagnose nennt das bewegliche Bauteil",
              "B" in str(ex) and "ohne Steifigkeit" in str(ex), str(ex)[:150])


def main():
    for f in (test_freier_wuerfel, test_rechnen_statt_abbrechen,
              test_stab_dreht_sich_um_die_eigene_achse,
              test_bericht_nennt_die_grenze, test_kontakt_gleitet, test_kontakt_hebt_ab,
              test_reibung_und_einseitige_lager,
              test_lagerausfall_kennt_die_richtung,
              test_stufe2_nennt_das_bauteil):
        print(f"\n--- {f.__name__} ---")
        try:
            f()
        except Exception as ex:          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{f.__name__} ohne Ausnahme", False, str(ex)[:80])
    n_ok = sum(1 for _n, ok in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"Ergebnis: {n_ok}/{len(RESULTS)} Pruefungen bestanden")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
