"""
Adaptive Vernetzung: rechnen, den Fehler schaetzen, nur dort feiner - und im
Feld groeber.

Die Schleife, die im Programm fehlte (Uebergabe vom 20.09.2026, Abschnitt
1.7): ``netzdichte`` laeuft vor dem Rechnen, und kein Ergebnis fand je in
die Netzsteuerung zurueck. Hier:

1. **Vernetzen** (:func:`mesher.modell_vernetzen`), im ersten Durchgang
   bewusst grob: Linien an Nebenflaechen mit dem groben Bogenwinkel
   (``netz.nebenflaechen_grob``), damit unbelastete Bohrungen und
   Ausrundungen nicht von vornherein die Elementzahl bestimmen.
2. **Rechnen** - die genannten Lastfaelle (:func:`solver.solve_static`).
3. **Schaetzen** (:func:`netzfehler.indikator`): der Spannungssprung je
   Element, der bezogene Gesamtfehler.
4. **Steuern**: neue Kantenlaenge je Element, daraus eine eigene
   Kantenlaenge je Koerper (``netz.koerper_h``) und Feldpunkte
   (``netz.feldpunkte``) - die Quellen des Groessenfelds des naechsten
   Durchgangs. Dann von vorn, bis das Ziel erreicht oder die Rundenzahl
   erschoepft ist.

Warum das zum Drehlager passt: das Modell wird 422-mal gerechnet. Zwei bis
drei Durchgaenge mit je einem oder wenigen Lastfaellen sind gegen 422 Laeufe
auf dem fertigen Netz nichts - und jeder Freiheitsgrad, der dabei wegfaellt,
verkleinert alle 422 Laeufe zugleich (Faktorisierung, Elementschleifen,
Kontaktaufbau).

Alles, was die Schleife setzt, steht danach in den Netzeinstellungen des
Modells und wird mit ihm gespeichert: wer das Netz spaeter neu erzeugt,
bekommt dasselbe Groessenfeld wieder.
"""
from __future__ import annotations

import time

from . import netzfehler


#: Schluessel in Results.info, die die Schleife je Durchgang protokolliert, wenn
#: der Loeser sie fuehrt (Antwort der Loeser-Sitzung vom 20.09.2026: ndof_frei,
#: nnz, nnz_faktor, t_faktorisierung, backend, threads kommen dazu). Sie sagen,
#: was eine Runde an **Loeserzeit** gekostet und gespart hat - die Groesse,
#: um die es geht.
LOESER_ZAHLEN = ("ndof_frei", "nnz", "nnz_faktor", "t_faktorisierung", "contact_factorisations",
                 "contact_iterations", "contact_converged", "backend", "threads", "probelauf", "time")


def _rechnen_standard(workers):
    """Der Loeseraufruf der Schleife: ein **Probelauf**, wenn der Loeser ihn
    kennt (``solve_static(..., probelauf=True)``: ein Kontaktschritt je
    Fliessschritt, Plastizitaet an - am Drehlager 199 s statt 633 s bei
    denselben 100 Spitzenelementen, gemessen von der Loeser-Sitzung am
    20.09.2026), sonst der gewoehnliche Lauf. Ein Probelauf ist ein Netzmass
    und kein Rechenergebnis: seine Kontaktkraefte stimmen nicht, und die
    Schleife gibt ihn nur an den Fehlerschaetzer, nie ans Modell."""
    from . import solver

    def rechnen(m, lf):
        try:
            return solver.solve_static(m, case=lf, workers=workers, probelauf=True)
        except TypeError:
            return solver.solve_static(m, case=lf, workers=workers)
    return rechnen


def _loeserzahlen(ergebnisse) -> str:
    """Die Loeserzahlen des ersten Ergebnisses als Protokolltext (leer, wenn
    der Loeser keine fuehrt)."""
    if not ergebnisse:
        return ""
    info = getattr(ergebnisse[0], "info", None) or {}
    teile = []
    for k in LOESER_ZAHLEN:
        if k in info:
            v = info[k]
            teile.append(f"{k} {v:.3g}" if isinstance(v, float) else f"{k} {v}")
    return ", ".join(teile)


def adaptiv_vernetzen(model, lastfaelle=None, runden: int = 2, ziel: float = netzfehler.ZIEL,
                      log: list = None, workers: int = None, fortschritt=None,
                      grob_beginnen: bool = True, rechnen=None,
                      wachstum_max: float = netzfehler.WACHSTUM_MAX) -> dict:
    """Die adaptive Schleife: ``runden`` Verfeinerungsschritte, also
    ``runden + 1`` Vernetzungen und Rechnungen; Abbruch, sobald der bezogene
    Fehler unter ``ziel`` liegt.

    ``lastfaelle``: Namen der Lastfaelle, an denen sich das Netz ausrichtet
    (Vorgabe: der aktive, sonst der erste). ``rechnen(model, lastfall)`` kann
    den Loeseraufruf ersetzen (Pruefungen); Vorgabe
    :func:`solver.solve_static`. ``grob_beginnen`` schaltet fuer die Dauer
    der Schleife ``netz.nebenflaechen_grob`` ein und stellt danach den alten
    Wert wieder her - das Netz bleibt, wie die Schleife es gemacht hat.

    ``wachstum_max``: um hoechstens diesen Faktor darf die Elementzahl je
    Runde wachsen. Die Schaetzung in :func:`netzfehler.neue_kantenlaengen`
    haelt ihn nur ungefaehr - der Vernetzer legt an Huelle und Uebergaengen
    mehr Elemente, als Summe (h/h_neu)^3 sagt (kleine Platte: 3 973 ->
    45 801 statt 11 919, 20.09.2026). Darum wird nachgemessen: liegt das
    neue Netz ueber dem Budget, werden Koerperkantenlaengen und Feldpunkte
    um die Kubikwurzel des Ueberschusses vergroebert und **einmal** neu
    vernetzt. Erzwungen, nicht gehofft.

    Rueckgabe {"verlauf": [je Durchgang ein Woerterbuch], "ergebnisse":
    die Ergebnisse des letzten Durchgangs, "indikator": sein Indikator}.
    Die Ergebnisse sind die eines **Probelaufs**, wenn der Loeser ihn kennt
    (:func:`_rechnen_standard`) - ein Netzmass, kein Rechenergebnis: nicht
    in Auflagerkraefte, Nachweise oder einen Bericht uebernehmen.
    """
    from . import mesher
    from .importers import _common as C
    log = [] if log is None else log
    netz = model.netz
    if not lastfaelle:
        aktiv = getattr(model, "active_case", "") or ""
        lastfaelle = [aktiv] if aktiv in model.load_cases else list(model.load_cases)[:1]
    lastfaelle = list(lastfaelle)
    if rechnen is None:
        rechnen = _rechnen_standard(workers)
    alt_grob = bool(getattr(netz, "nebenflaechen_grob", False))
    if grob_beginnen:
        netz.nebenflaechen_grob = True
    verlauf: list = []
    ergebnisse: list = []
    ind = netzfehler.indikator(model, [])
    try:
        for runde in range(int(runden) + 1):
            if fortschritt is not None and fortschritt(runde / (runden + 1),
                                                       f"Adaptiv: Durchgang {runde + 1} von {runden + 1}") is False:
                C.say(log, "Adaptive Vernetzung abgebrochen.")
                break
            t0 = time.time()
            erg = mesher.modell_vernetzen(model, log, workers=workers)
            if erg.get("abgebrochen"):
                break
            if verlauf and wachstum_max and wachstum_max > 0:
                budget = wachstum_max * verlauf[-1]["elemente"]
                if len(model.elements) > 1.15 * budget:
                    s = (len(model.elements) / budget) ** (1.0 / 3.0)
                    C.say(log, f"  {len(model.elements)} Elemente überschreiten das Budget "
                               f"({budget:.0f}, das {wachstum_max:g}-Fache) - Kantenlängen um "
                               f"{s:.2f} vergröbert und neu vernetzt")
                    netz.koerper_h = {k: v * s for k, v in (netz.koerper_h or {}).items()}
                    netz.feldpunkte = [[p[0], p[1], p[2], p[3] * s] + list(p[4:]) for p in netz.feldpunkte]
                    erg = mesher.modell_vernetzen(model, log, workers=workers)
                    if erg.get("abgebrochen"):
                        break
            t_netz = time.time() - t0
            t0 = time.time()
            ergebnisse = [rechnen(model, lf) for lf in lastfaelle]
            t_rechnen = time.time() - t0
            ind = netzfehler.indikator(model, ergebnisse)
            sv_max = float(ind["sv"].max()) if len(ind["sv"]) else 0.0
            schritt = {"runde": runde, "elemente": len(model.elements), "knoten": int(model.nn),
                       "tetraeder": int(ind["N"]), "eta_rel": float(ind["eta_rel"]),
                       "sv_max": sv_max, "t_netz": t_netz, "t_rechnen": t_rechnen}
            verlauf.append(schritt)
            C.say(log, f"Adaptiv Durchgang {runde + 1}: {schritt['elemente']} Elemente, "
                       f"{schritt['knoten']} Knoten, geschätzter Fehler {ind['eta_rel'] * 100:.1f} % "
                       f"(Ziel {ziel * 100:.0f} %), σ_v max {sv_max / 1e6:.1f} N/mm², "
                       f"Netz {t_netz:.1f} s, Rechnung {t_rechnen:.1f} s")
            for z in netzfehler.bericht(ind)[1:]:
                C.say(log, z)
            zahlen = _loeserzahlen(ergebnisse)
            if zahlen:
                C.say(log, f"  Löser: {zahlen}")
            if runde >= runden or not ind["N"] or ind["eta_rel"] <= ziel:
                break
            h_neu = netzfehler.neue_kantenlaengen(ind, ziel, h_min=float(netz.h_min or 0.0),
                                                  h_max=float(netz.h_max or 0.0),
                                                  wachstum_max=wachstum_max)
            koerper_h = netzfehler.koerper_kantenlaengen(model, ind, h_neu,
                                                         h_min=float(netz.h_min or 0.0),
                                                         h_max=float(netz.h_max or 0.0))
            netz.koerper_h = dict(getattr(netz, "koerper_h", None) or {})
            netz.koerper_h.update(koerper_h)
            netz.feldpunkte = netzfehler.feldpunkte(model, ind, h_neu, netz.koerper_h)
            if koerper_h:
                grob = max(koerper_h.values())
                fein = min(koerper_h.values())
                C.say(log, f"  nächster Durchgang: Kantenlänge je Körper {fein * 1e3:.1f} … "
                           f"{grob * 1e3:.1f} mm, {len(netz.feldpunkte)} Feldpunkte "
                           f"(feinste {min((p[3] for p in netz.feldpunkte), default=grob) * 1e3:.1f} mm)")
    finally:
        netz.nebenflaechen_grob = alt_grob
    return {"verlauf": verlauf, "ergebnisse": ergebnisse, "indikator": ind}
