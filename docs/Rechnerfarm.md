# Statik3D – Mehrkernrechnung und Rechnerfarm

## Mehrere Kerne auf einem Rechner

Standardmäßig nutzt Statik3D alle Prozessorkerne des Rechners bis auf einen
(der bleibt der Oberfläche; Einstellung „Prozesse“):

* Elementschleifen (Assemblierung der Steifigkeitsmatrix, Nachlaufrechnung)
  werden ab 1500 Elementen auf einen Prozess-Pool verteilt.
* Kombinationen mit Kontakt (nichtlinear) und Nachweise vieler Stäbe laufen
  als unabhängige Aufträge parallel.
* Der Gleichungslöser SuperLU ist einprozessig. Für große Modelle lohnt
  `pip install pypardiso mkl` (Intel MKL Pardiso, mehrere Threads) – Statik3D
  findet die MKL-Bibliothek selbst und benutzt Pardiso automatisch. Messung
  (Platte, 25 600 Schalen, 155 000 FHG, 4 Kerne): Assemblierung 47 s → 16 s
  parallel; Faktorisierung SuperLU 113 s → Pardiso 3 s; jeder weitere
  Lastfall 8 s (Lösen + Nachlauf).

Einstellung: GUI → Berechnung → Prozesse, oder in Python

```python
from statik3d import parallel
parallel.configure(workers=8)
```

CLI: `python -m statik3d.cli modell.json --kerne 8`

## Rechnerfarm (mehrere Rechner)

Die Farm besteht aus einem Server (Auftragswarteschlange), beliebig vielen
Workern auf den Rechnern der Farm und dem Client (GUI oder CLI). Alle Rechner
müssen denselben Programmstand haben und sich im selben Netz erreichen
(TCP-Port, Standard 5555).

### Ohne Kommandozeile: Arbeitsplatz und Rechenhilfe (seit 13.09.2026)

1. **Arbeitsplatz** (der Rechner, an dem gerechnet wird): *Berechnung →
   Einstellungen → Rechnerfarm einschalten*. Das startet den Server, eigene
   Worker (Zahl = „Prozesse“) und eine **Ankündigung im Netz** (UDP-Rundruf
   auf Port 5556, alle zwei Sekunden); das Backend springt auf
   „Rechnerfarm“. Das Protokoll nennt die eigene Adresse und den Port. In der
   Windows-Firewall muss TCP-Port 5555 eingehend frei sein.
2. **Rechenhilfe** (jeder weitere Rechner): dieselbe `Statik3D.exe` starten
   und *Extras → Als Rechenhilfe arbeiten…* wählen — oder gleich
   `Statik3D.exe --rechenhilfe`. Im Fenster **Arbeitsplatz suchen** drücken:
   die Ankündigung wird empfangen, Name, Adresse, Port und Programmstand des
   Arbeitsplatzes erscheinen (Adresse und Port lassen sich auch von Hand
   eintragen). Denselben **Schlüssel** wie am Arbeitsplatz eintragen, die
   Zahl der Rechenprozesse wählen (Vorgabe alle Kerne bis auf einen),
   **Verbinden**. Das Fenster prüft die Verbindung samt Schlüssel, lädt MUMPS
   nach, wenn es dort fehlt (der Arbeitsplatz könnte es als Löser verlangen),
   und startet die Worker als eigene Prozesse; danach zeigt es alle zwei
   Sekunden, wie viele Prozesse aktiv sind und wie viele Aufträge sie
   erledigt haben. **Trennen** beendet sie; das Schließen des Fensters ebenso.
   `Statik3D.exe --rechenhilfe --host 192.168.1.10 --key geheim --kerne 8`
   verbindet ohne Klick (für Verknüpfungen und Autostart).
3. **Farm-Status** am Arbeitsplatz zeigt jede Rechenhilfe mit Rechner,
   Version und Stand (Commit); ein anderer Stand als am Arbeitsplatz wird
   markiert — dann dort dasselbe Programm einspielen (Update).

Jeder Worker meldet Version und Stand; ein fremder Stand steht auch in der
Statuszeile der Farm. Geprüft in `tests/test_farm.py` (Ankündigung und Suche
auf dem eigenen Rechner, Worker-Prozess, Stand im Status) und
`tests/test_gui_smoke.py` (Einschalten, Fenster, Suche, Verbinden, falscher
Schlüssel, Trennen).

### Mit Kommandozeile (Python-Umgebung)

1. Server starten (auf einem beliebigen Rechner, z. B. dem Arbeitsplatz):

       python -m statik3d.farm server --port 5555 --key geheim

2. Worker auf jedem Rechner der Farm starten (nutzt alle Kerne, oder `--cores n`):

       python -m statik3d.farm worker --host 192.168.1.10 --port 5555 --key geheim

3. Status prüfen:

       python -m statik3d.farm status --host 192.168.1.10 --port 5555 --key geheim

4. Rechnen:

   * GUI → Berechnung → Backend „Rechnerfarm“, Server/Port/Schlüssel eintragen.
     Der Knopf „Lokalen Server + Worker starten“ startet Server und Worker
     direkt in der Oberfläche; weitere Rechner verbinden sich mit `--host`
     auf die IP des Arbeitsplatzes.
   * CLI: `python -m statik3d.cli modell.json --farm 192.168.1.10:5555 --schluessel geheim`
   * Python: `parallel.configure(backend="farm", farm_host=..., farm_port=..., farm_key=...)`

Auf die Farm verteilt werden: Kombinationen bei Kontaktmodellen, Nachweise
nach EC3 (Stabgruppen) sowie eigene Aufträge über `statik3d.parallel.run_jobs`.
Die lineare Lösung eines einzelnen Modells läuft immer lokal (Faktorisierung
einmal, alle Lastfälle mit derselben Faktorisierung); die Farm lohnt sich bei
vielen nichtlinearen Kombinationen, Parameterstudien oder Nachweisen sehr
vieler Stäbe.

### Eigene Aufträge

```python
from statik3d.parallel import Job, run_jobs, register_job

@register_job("meine_studie")
def _job(model: dict, parameter: float):
    from statik3d.model import Model
    from statik3d import solver
    m = Model.from_dict(model)
    ...
    return ergebnis

jobs = [Job("meine_studie", {"model": m.to_dict(), "parameter": p}) for p in werte]
for r in run_jobs(jobs):
    print(r.ok, r.result, r.worker, r.seconds)
```

Die Registrierung muss in einem Modul erfolgen, das auf allen Workern importiert
wird (z. B. `statik3d/jobs.py` oder ein eigenes Paket in `PYTHONPATH`).

### Sicherheit

Die Verbindung ist mit dem Schlüssel (HMAC-Authentifizierung) gesichert, aber
nicht verschlüsselt. Die Farm gehört in ein vertrauenswürdiges Netz (Büro-LAN,
VPN). Aufträge werden als Python-Objekte (pickle) übertragen; nur Rechner mit
demselben Schlüssel können Aufträge einstellen oder abholen.

### Fehlerbehandlung

* Fällt ein Worker aus, bleiben seine laufenden Aufträge unbeantwortet; der
  Client meldet nach Ablauf von `farm_timeout` (Standard 3600 s) einen
  Timeout. Aufträge, die ein Worker noch nicht abgeholt hat, werden von den
  übrigen Workern bearbeitet.
* Ohne aktiven Worker bricht der Client sofort mit einer Meldung ab.
* Fehler innerhalb eines Auftrags (z. B. singuläres System) werden mit
  Traceback an den Client zurückgegeben.
