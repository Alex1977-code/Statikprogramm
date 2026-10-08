"""Alle Testsuiten nacheinander ausfuehren:  python -m tests.run_all  [--gui]"""
import os
import subprocess
import sys

SUITES = ["tests.test_verification", "tests.test_elemente_volumen", "tests.test_elemente_schalen",
          "tests.test_elemente_ebene", "tests.test_elemente_stab", "tests.test_elemente",
          "tests.test_fortschritt", "tests.test_netzguete", "tests.test_vernetzer_extern", "tests.test_werkzeuge", "tests.test_farm",
          "tests.test_solver_ext", "tests.test_ec3",
          "tests.test_fehler_p8",
          "tests.test_fehler_p10",
          "tests.test_fehler_p13",
          "tests.test_nachtrag_q8",
          "tests.test_importers", "tests.test_report", "tests.test_web", "tests.test_update", "tests.test_supports", "tests.test_sections", "tests.test_rfem", "tests.test_rfem6", "tests.test_hicad", "tests.test_infocad", "tests.test_joints", "tests.test_exporters", "tests.test_bridges", "tests.test_geometrie", "tests.test_tabellen", "tests.test_gzg", "tests.test_beulen", "tests.test_klasse4", "tests.test_theorie2", "tests.test_volumen", "tests.test_geometrie_kette", "tests.test_mesher3d", "tests.test_fugen", "tests.test_kontakte", "tests.test_layer", "tests.test_skizze", "tests.test_unterlagen", "tests.test_abbruch", "tests.test_stabende", "tests.test_kontur", "tests.test_nachiteration", "tests.test_kontakthalt", "tests.test_passung", "tests.test_spiel", "tests.test_plastizitaet", "tests.test_dilatation", "tests.test_transformieren", "tests.test_konstruktion", "tests.test_verschneiden", "tests.test_woelb", "tests.test_lasten", "tests.test_situationen", "tests.test_knicklaengen", "tests.test_theorie3", "tests.test_wasserdruck", "tests.test_wind", "tests.test_schwingung", "tests.test_schweissnaehte", "tests.test_diagnose", "tests.test_singular", "tests.test_freie_teile", "tests.test_uebermass",
    "tests.test_loeser", "tests.test_startbild", "tests.test_netzverfeinerung", "tests.test_bemassung", "tests.test_netzdichte", "tests.test_einheiten", "tests.test_stroemung",
          "tests.test_lastenheft", "tests.test_ausgabe", "tests.test_umhuellende", "tests.test_kopie",
          "tests.test_ermuedung_verlauf", "tests.test_ermuedungsmaske", "tests.test_kontaktzustand", "tests.test_worker", "tests.test_rechenliste",
          "tests.test_spannungen", "tests.test_ergebnisse", "tests.test_ergebnisbaum", "tests.test_maskenrahmen", "tests.test_nachweisampel", "tests.test_ergebnisbild", "tests.test_ungespeichert", "tests.test_paket_f", "tests.test_stellungen_zuweisung", "tests.test_register_berechnung", "tests.test_kontextregister", "tests.test_kleinigkeiten", "tests.test_qt_deutsch", "tests.test_protokoll_lesbar", "tests.test_baum_ruhig", "tests.test_baum_gruppen", "tests.test_tabelleninhalte", "tests.test_zahlenfeld", "tests.test_fachbegriffe", "tests.test_huellen_schluessel", "tests.test_namen_lf_lk", "tests.test_fehler_p4", "tests.test_fehler_p5",
          "tests.test_netzfeld", "tests.test_netzfehler", "tests.test_sweep", "tests.test_sweep_feld", "tests.test_fensteraufteilung", "tests.test_ergebnisdarstellung", "tests.test_glasleiste_ribbon", "tests.test_ribbon_ordnung", "tests.test_symbole_ribbon", "tests.test_tasten_fokus", "tests.test_loeschen", "tests.test_aenderungsmerker", "tests.test_baum_klickregel", "tests.test_baum_filter", "tests.test_umlaute_einzahl",
           "tests.test_neuvernetzen", "tests.test_elementwahl", "tests.test_randspannung",
           "tests.test_klickauswahl", "tests.test_rechtsklick", "tests.test_hinweise",
           "tests.test_tetp", "tests.test_tetp_rechnung", "tests.test_entartung",
           "tests.test_vertraeglich", "tests.test_nachlauf_parallel", "tests.test_pool_speicher", "tests.test_zerlegung_speicher", "tests.test_sweep_aus",
           "tests.test_register_start",
           "tests.test_fehler_p14",
           "tests.test_unten_kopfzeile", "tests.test_befehl_stab",
           "tests.test_stab_nachweis", "tests.test_stab_teilen", "tests.test_ergebniszeile",
           "tests.test_elementuebersicht", "tests.test_elementstufe", "tests.test_netz_grenze", "tests.test_fein_smart",
           "tests.test_beenden_ohne_absturz",
           "tests.test_fehler_p12", "tests.test_fehler_p6", "tests.test_nachtrag_q7",
           "tests.contracts.test_vertrag", "tests.test_kontakt_exakt", "tests.test_kontakt_pendeln", "tests.test_pruefmatrix_q3", "tests.test_kontaktseiten", "tests.test_sehne_gueltig",
           "tests.test_fehler_p7",
           "tests.test_fehler_p16", "tests.test_fehler_p15",
           "tests.test_nachtrag_q2", "tests.test_nachtrag_q3", "tests.test_nachtrag_q10", "tests.test_nachtrag_q9", "tests.test_nachtrag_q4", "tests.test_nachtrag_q5", "tests.test_nachtrag_q6", "tests.test_nachtrag_q1",
           "tests.test_nachtrag_m26",
           "volumen3d.tests.test_kern"]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    failed = []
    suites = list(SUITES)
    if "--gui" in argv:
        suites.append("tests.test_gui_smoke")
    for s in suites:
        cmd = [sys.executable, "-m", s]
        if s.endswith("gui_smoke") and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            cmd = ["xvfb-run", "-a"] + cmd
        print(f"\n===== {s} =====")
        r = subprocess.run(cmd, cwd=here)
        if r.returncode != 0:
            failed.append(s)
    print("\n" + "=" * 60)
    print("ALLE TESTS BESTANDEN" if not failed else f"FEHLGESCHLAGEN: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
