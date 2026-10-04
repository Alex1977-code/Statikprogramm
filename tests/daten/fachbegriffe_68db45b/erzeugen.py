"""Referenz fuer tests/test_fachbegriffe.py: Modell, Ergebnisdatei und Bericht
eines Stands **vor** Teilpaket 11b (68db45b, 03.10.2026).

Ein Kragarm mit drei Lastfaellen, je einer Kombination jedes Typs, zwei
Ergebniskombinationen, deren Namen wie Fachbegriffe lauten („GZT“,
„Ermüdung“), und vier Berichtseintraegen (Bild der Umhuellenden ULS, Bild der
Ergebniskombination GZT, Tabelle Auflagerkraefte zur Umhuellenden SLS_CH, die
eine Umhuellende nicht hat, Tabelle Kombinationen).

Erzeugt mit dem Baum von 68db45b:

    python tests/daten/fachbegriffe_68db45b/erzeugen.py <baum 68db45b> <zielordner>

Die Pruefung liest Modell und Ergebnisdatei mit dem neuen Stand, schreibt den
Bericht und vergleicht ihn Zeile fuer Zeile mit bericht.txt (bericht_text).
"""
import os
import re
import sys


def bericht_text(html: str) -> str:
    """Bericht als Text: Bilder (base64) weg, Tags zu Zeilenumbruechen, Datum
    und Programmstand neutral."""
    html = re.sub(r"data:[^\"')]+", "data:", html)
    txt = re.sub(r"<(br|/p|/h\d|/tr|/li|/div|/td|/th)[^>]*>", "\n", html)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", "DATUM", txt)
    txt = re.sub(r"\b\d{1,2}:\d{2}(:\d{2})?\b", "UHRZEIT", txt)
    txt = re.sub(r"Statik3D \d+\.\d+(\.\d+)?\S*", "Statik3D VERSION", txt)
    return "\n".join(" ".join(z.split()) for z in txt.splitlines() if z.strip())


def modell():
    """Das Modell der Referenz (mit dem Baum, aus dem statik3d geladen ist)."""
    from statik3d.model import Model, Material, Section, Combination, Berichtseintrag
    from statik3d import mesher
    m = Model("Fachbegriffe")
    m.add_material(Material("S", E=210e9, rho=0.0))
    m.add_section(Section.rectangle("R", 0.1, 0.2))
    ids = mesher.line_of_beams(m, "S", "R", (0, 0, 0), (2.0, 0, 0), 4)
    m.fix(ids[0], "all")
    m.case().category = "G"
    m.load_node(ids[-1], Fz=-10e3, case=m.active_case)
    lf1 = m.active_case
    m.add_load_case("LF2", "Q")
    m.load_node(ids[-1], Fy=5e3, case="LF2")
    m.add_load_case("LF3", "W")
    m.load_node(ids[-1], Mx=2e3, case="LF3")
    for i, typ in enumerate(("ULS", "EQU", "ACC", "SLS_CH", "SLS_FR", "SLS_QP", "FAT", "USER")):
        m.add_combination(f"K{i + 1}", {lf1: 1.0 + 0.1 * i, "LF2": 0.5}, typ, f"Typ {typ}")
    # Ergebniskombinationen (oder), deren Namen wie Fachbegriffe lauten
    m.combinations["GZT"] = Combination("GZT", {}, "ULS",
                                        alternativen=[{lf1: 1.35}, {lf1: 1.35, "LF2": 1.5}])
    m.combinations["Ermüdung"] = Combination("Ermüdung", {}, "FAT",
                                             alternativen=[{lf1: 1.0}, {"LF3": 1.0}])
    for name, quelle, art, tabelle in (("Bild 1", "env:ULS", "bild", ""),
                                       ("Bild 2", "env:GZT", "bild", ""),
                                       ("Tabelle 1", "env:SLS_CH", "tabelle", "Auflagerkräfte"),
                                       ("Tabelle 2", "", "tabelle", "Kombinationen")):
        e = Berichtseintrag(name=name, quelle=quelle, feld="|u| Verschiebung" if art == "bild" else "",
                            verlauf="kein Verlauf", art=art, tabelle=tabelle)
        if art == "bild":
            e.beschriftung = e.bezug()       # wie „Ansicht in den Bericht“
        m.bericht.append(e)
    return m


def main():
    baum = os.path.abspath(sys.argv[1])
    ziel = os.path.abspath(sys.argv[2])
    sys.path.insert(0, baum)
    import statik3d
    assert os.path.abspath(statik3d.__file__).startswith(baum), statik3d.__file__
    from statik3d import solver, ergebnisse
    from statik3d.report import Report
    os.makedirs(ziel, exist_ok=True)
    m = modell()
    an = solver.solve_all(m, design=False, fatigue=False)
    pfad = os.path.join(ziel, "modell.json")
    m.save(pfad)
    ergebnisse.schreiben(ergebnisse.pfad_zu(pfad), m, an)
    # der Bericht aus den gelesenen Dateien, wie in der Pruefung
    from statik3d.model import Model
    m2 = Model.load(pfad)
    an2 = ergebnisse.lesen(ergebnisse.pfad_zu(pfad), m2)
    with open(os.path.join(ziel, "bericht.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(bericht_text(Report(m2, an2).html()) + "\n")
    print("Umhuellende:", {k: v.name for k, v in an.envelopes.items()})
    print("geschrieben nach", ziel)


if __name__ == "__main__":
    main()
    sys.stdout.flush()
    os._exit(0)
