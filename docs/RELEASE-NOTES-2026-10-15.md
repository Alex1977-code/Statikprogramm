# Statik3D – Release-Notes vom 15.10.2026

Diese Notizen richten sich an die Ingenieure, die mit dem Programm rechnen. Sie beschreiben, was sich
gegenüber dem Stand vom 14.10.2026 (Ansicht mit Gizmo, Ausblenden und gespeicherten Ansichten) ändert und
an welchen Stellen Ergebnisse anders ausfallen als bisher. Einzelheiten stehen im Benutzerhandbuch in den
Abschnitten „Reibung mit konsistenter Tangente“, „Vorspannung“, „Spannstahl“ und „Reibung an Lagern aus
RFEM 6“, die Herleitungen im Theoriehandbuch.

## Auf einen Blick

* Reibung rechnet jetzt standardmäßig mit der **konsistenten Tangente**. Der Drehlager-Entwurf war damit in
  26 Minuten fertig und nicht vorläufig; mit dem bisherigen Verfahren kam er in 5,3 Stunden nur bis 68,75 %
  der Last.
* Der **Deckel des Kontaktlaufs zählt alle Runden**. Ein Lauf, der am Deckel endet, ist nicht konvergiert,
  und das Ergebnis heißt „vorläufig“, jetzt auch in der Kopfzeile und in der Statuszeile.
* Die **Ergebnisdatei schreibt das Reibverfahren mit**. Bei einer älteren Ergebnisdatei zu einem Modell mit
  Reibung erscheint ein Hinweis, dass sie mit dem bisherigen Verfahren gerechnet ist.
* Ein **Reibbeiwert an einem Lager aus RFEM 6** gilt nur noch, wenn RFEM dort einen Reibungstyp gewählt hat.
  Das ändert Ergebnisse von Modellen, die bisher mit dem Vorgabewert μ = 0,1 übernommen wurden.
* Die Vorspannung heißt jetzt **Anfangsvorspannung (Pressenkraft P₀)** oder **Endvorspannung (bleibend
  nach dem Verankern)**. Die Anfangsvorspannung kennt den Verankerungsschlupf Δs, und der
  Spannstahlnachweis nennt je Anker freie Ankerlänge, Schlupf und Kraftverlust.
* Beim Öffnen älterer Modelle aus RFEM 6 sagen **Hinweise zu Vorspannung und Lagerreibung**, was zu prüfen
  ist und wo es umgestellt wird. Das Programm stellt nichts von selbst um.
* Bei einem **Rundstahl** stellen Sie ein Gewinde (M12 bis M36) selbst ein; der Import setzt es nicht.

## Reibung mit konsistenter Tangente (neue Vorgabe)

Bis zum 15.10.2026 bestimmte das Programm Haften und Gleiten als Fixpunkt: Es stellte haftende Knoten
schrittweise ins Gleiten, führte die Gleitrichtungen aus der Reibkraft der vorigen Runde nach und hielt
pendelnde Knoten mit eigenen Regeln fest. Am Drehlager-Entwurf endeten so in der plastischen Phase fast alle
Kontaktläufe nach 40 Runden am Deckel.

Jetzt rechnet jeder Reibknoten an einer starren Normalbedingung (Fuge oder Lager mit μ ohne eigene Feder)
in jeder Runde das Coulomb-Gesetz aus seinem Weg in der Fuge und seiner Normalkraft. Er haftet, solange die
Haftkraft unter μ·Fn bleibt, und gleitet sonst mit μ·Fn in Richtung seines Wegs. Die nächste Runde rechnet
mit der passenden Ableitung (Newton-Verfahren). Die Normalbedingung bleibt exakt, und die
Ingenieurkriterien gelten unverändert. Das Haften ist eine sehr steife Feder, deren Steifigkeit das
1 000-fache der Knotensteifigkeit aus den angrenzenden Elementen beträgt; ein haftender Knoten gibt dadurch
um höchstens etwa 1,4·10⁻⁵ der größten Verschiebung nach. Bettungen und Kontaktfedern mit eigener
Steifigkeit rechnen die Reibung wie bisher, und reibungsfreie Fugen rechnen mit beiden Verfahren bitgleich.

**Abnahme am Drehlager-Entwurf** (E0-neu, μ = 0,1): Der Lastfall war nicht vorläufig und brauchte 11
Kontaktläufe mit zusammen 19 Runden; keiner endete am Deckel, gerechnet wurde 26 Minuten. Mit dem
bisherigen Verfahren kam derselbe Lauf in 5,3 Stunden nur bis 68,75 % der Last, und alle Kontaktläufe
endeten am Deckel.

**Einstellung:** *Berechnung → Einstellungen*, Gruppe „Kontaktlauf und Spannschritt“, Auswahl „Reibung“ mit
„konsistente Tangente (Vorgabe)“ oder „bisheriges Verfahren (nur zum Vergleich)“, dazu die
„Haftsteifigkeit“ als Vielfaches der Knotensteifigkeit (Vorgabe 1 000). Gespeichert werden beide nur, wenn
sie von der Vorgabe abweichen. Ältere Modelldateien enthalten keine Angabe und rechnen beim nächsten Rechnen
mit der Tangente.

## Deckel über alle Runden und „vorläufig“

Bis zum 15.10.2026 zählte der Deckel der Nachprüfung nur die Runden der zweiten Phase, in denen sich ein
Zustand änderte. Am Drehlager lief ein Kontaktlauf so 121 Runden bis zur Höchstzahl der Iteration, ohne dass
die Zeile des Deckels kam. Jetzt zählt jede Runde eines Kontaktlaufs. Nach 40 Runden endet er mit der Zeile
„Kontakt: Nachprüfung der Reibung nach 40 Runden abgebrochen“, er gilt als nicht konvergiert, und das
Ergebnis ist vorläufig.

Das steht wie bisher in der Zusammenfassung, in der Rechenliste, im Bericht und in der Ergebnisdatei. Neu
steht es auch in der Kopfzeile („berechnet · vorläufig“, farbig hinterlegt) und nach der Rechnung in der
Statuszeile („⚠ Ergebnis vorläufig (Kontakt nicht konvergiert): LF1 …“). Ein vorläufiges Ergebnis ist kein
Nachweis; es zeigt, wohin die Rechnung lief.

## Reibverfahren in der Ergebnisdatei

Die Ergebnisdatei (`<modell>.ergebnisse`) schreibt jetzt mit, mit welchem Reibverfahren gerechnet wurde
(„konsistente Tangente“ oder „bisheriges Verfahren“). Öffnen Sie ein Modell mit Reibung (Kontakt mit μ > 0
oder Lager mit Reibbeiwert) zusammen mit einer älteren Ergebnisdatei ohne diese Angabe, werden die Ergebnisse
geladen und bleiben sichtbar. Ein Hinweis in Statuszeile und Protokoll sagt dazu: „gerechnet mit dem
bisherigen Reibverfahren – für aktuelle Ergebnisse neu rechnen“. Speichern Sie, ohne neu zu rechnen, bleibt
die Angabe weg, und der Hinweis kommt beim nächsten Öffnen wieder. Modelle ohne Reibung bekommen keinen
Hinweis.

Eine Modelldatei, in der ausdrücklich „reibungstangente: true“ steht (gespeichert am 15.10.2026, als das
Verfahren noch nicht Vorgabe war, zum Beispiel die Drehlager-Läufe dieses Tages), galt mit ihrer
Ergebnisdatei als „seit der Rechnung geändert: Rechenart und Einstellungen“. Sie passt jetzt und wird ohne
Hinweis geladen, denn sie ist mit der Tangente gerechnet.

## Lagerreibung nur mit Reibungstyp aus RFEM

Das Feld „Reibbeiwert“ trägt in jeder RFEM-Datei einen Wert (Vorgabe 0,1), auch wenn an dem Lager keine
Reibung gewählt ist. Bis zum 15.10.2026 hat der Import diesen Wert übernommen, sobald das Lager irgendeine
Nichtlinearität hatte. Am Drehlager haftete dadurch das Flächenlager „Starr“ (Ausfall bei Zug, in der Fläche
frei) in der Fläche bis μ·N, was RFEM so nicht rechnet.

Seither gilt der Reibbeiwert nur, wenn RFEM einen **Reibungstyp** nennt: beim Flächenlager „Reibung in der
Ebene xy“, beim Knoten- und Linienlager „Reibung Richtung …“. Ohne Reibungstyp gilt der Freiheitsgrad nach
seiner Federkonstanten (0 = frei), und das Importprotokoll nennt die nicht angesetzten Beiwerte in einem
Satz.

**Ältere Dateien:** Ob ein Reibbeiwert in einem früher übernommenen Modell aus dem Import stammt, ist dem
gespeicherten Modell nicht sicher anzusehen. Darum zeigt das Programm beim Öffnen nur einen Hinweis. Er nennt
jedes Lager mit Reibbeiwert samt Freiheitsgraden („Starr (ux, uy μ = 0,1)“) und sagt, ob die RFEM-Datei noch
am gemerkten Ort liegt. Umgestellt wird auf Ihre Anweisung: Datei › Austausch › „Aus RFEM nachlesen ▾“ ›
„Lager aus RFEM nachlesen…“ liest die Lager aus der RFEM-Datei nach und nimmt einen Beiwert ohne Reibungstyp
zurück. Ein Lager mit Reibungstyp behält seine Reibung, und ein Beiwert, den Sie selbst geändert haben,
bleibt.

## Anfangs- und Endvorspannung mit Verankerungsschlupf

Im Spannschritt wählen Sie die Lastart. Beide Lastarten werden in einem eigenen Spannschritt vor den übrigen
Lasten aufgebracht, gleichzeitig oder gruppenweise (Gruppe 1, 2, …).

* **Anfangsvorspannung (Pressenkraft P₀):** Sie tragen die Kraft der Presse ein und den Verankerungsschlupf
  Δs in mm (aus der Zulassung). Nach dem Verankern fehlen der Schlupf und die elastischen Verluste; die
  Umgebung federt einen Teil des Verlusts zurück.
* **Endvorspannung (bleibend nach dem Verankern):** Sie tragen die Kraft ein, die im Stab bleiben soll. Das
  ist die bisherige „Vorspannkraft (Soll nach Verankerung)“, nur anders benannt; die Rechnung ist dieselbe
  geblieben.
* **Vorspannung als eingeprägte Dehnung (RFEM):** So kommt die Vorspannung aus RFEM an (als
  Temperaturdifferenz ΔT, die den Stab verkürzt). Das Programm zeigt dabei die Kraft, nicht die Temperatur;
  in der Lasttabelle heißt die Lastart „Vorspannung (eingeprägte Dehnung)“.

Der Spannstahlnachweis führt drei Zustände getrennt: beim Spannen P₀ gegen σ_p,max, nach dem Verankern
N_verankert gegen σ_pm0 und im Lastzustand N_Ed gegen f_pd = f_p0,1k/γ_s. Im Bericht fasst die Tabelle
„Spannstahl je Anker“ die drei Zustände je Anker zusammen.

### Freie Ankerlänge, Schlupf und Kraftverlust im Nachweis

Der Nachweis nennt für jeden Anker mit Anfangsvorspannung und Schlupf die **freie Ankerlänge** L_frei in m
(die Stablänge zwischen den Ankerpunkten, mit der auch die Steifigkeit k_A = E·A/L_frei rechnet), den
**Verankerungsschlupf** Δs in mm und den **Kraftverlust** ΔP in kN.

Der Verlust folgt aus ΔP = k_A·Δs·k_K/(k_A + k_K), mit k_K der Steifigkeit der Umgebung; am beidseitig
festen Anker ist es k_A·Δs. Im Ergebnis steht die verankerte Kraft, und es gilt P₀ − ΔP = N_verankert.
Beim reihenweisen Spannen enthält ΔP auch die elastischen Verluste der übrigen Anker. Ohne Ergebnis des
Spannschritts rechnet der Nachweis mit starrer Umgebung und sagt das.

Sie finden die Angaben in der Ausgabe nach dem Nachweis (Protokoll und Maske Ergebnisse, gleiche Anker in
einer Zeile wie „S1 bis S16“), im Bericht bei den Kennwerten des Stabs und in der Tabelle „Spannstahl je
Anker“ (Spalten L_frei [m], Δs [mm], ΔP [kN]).

Handprobe, wie das Programm sie nachrechnet: Ein Anker mit k_A = 210 kN/mm neben einem Klemmteil mit
k_K = 840 kN/mm, P₀ = 500 kN und Δs = 0,5 mm verliert ΔP = 105 · 840 / 1 050 = 84 kN und trägt danach
416 kN. Ein beidseitig fester Anker Rund 40 mit 3,23 m (E = 170 000 N/mm², A = 1 256,64 mm²) und
Δs = 1 mm verliert 66,14 kN; aus P₀ = 1 010,84 kN werden 944,70 kN. Trägt man wie am Drehlager
P₀ = 944,4 kN ein (0,9 · 835 · 1 256,6 mm²), stehen im Nachweis der Schlupf aus der Zulassung und der daraus
folgende Kraftverlust nebeneinander.

## Hinweise beim Laden älterer Dateien

Beim Import aus RFEM 6 und beim Öffnen eines früher übernommenen Modells steht je Vorspannungswert ein
Hinweis, zum Beispiel „Vorspannung 952 kN an S1–S16 in 129 Lastfällen aus RFEM übernommen (…) – in Statik3D
prüfen und ggf. als Anfangsvorspannung (Pressenkraft) oder Endvorspannung anpassen“. In den betroffenen
Lastfällen steht der Vermerk „aus RFEM übernommen – prüfen“ (Lastfallmaske und Lasttabelle).

Bei Dateien, die vor dem 13.10.2026 übernommen wurden, leitet das Programm die Vorspannung aus der ΔT-Last
ab, kennzeichnet sie mit „aus ΔT abgeleitet“ und sagt in einer Protokollzeile sowie in der Statuszeile, was
zu tun ist: Register **Lasten › Vorspannung**, Lastart „Eingeprägte Dehnung (RFEM, ΔT) in Endvorspannung
umwandeln“ stellt die Vorspannung auf die Endvorspannung um; mit „Anfangsvorspannung (Pressenkraft P₀)“ und
Δs setzen Sie stattdessen die Pressenkraft. **Das Programm stellt nichts von selbst um.** Eine alte Datei hat
die Herkunft der ΔT nicht gespeichert, und eine echte Abkühlung eines Zugstabs sieht genauso aus; ist es eine
echte Temperaturlast, lassen Sie sie, wie sie ist. Eine Datei, die ab dem 14.10.2026 übernommen wurde,
bekommt diese abgeleitete Vorspannung nicht mehr.

Der Hinweis zur Lagerreibung nennt jedes Lager mit Reibbeiwert und den Stand der RFEM-Datei (siehe oben).
Stehen mehrere Hinweise an (Zugstäbe, Lagerreibung, Vorspannung, Reibverfahren der Ergebnisdatei), zeigt die
Statuszeile sie zusammen; bis dahin überschrieb der letzte die übrigen.

## Gewinde am Rundstahl selbst einstellen

Ein Rundstahl aus RFEM kommt als Rundstahl **ohne** Gewinde an („Rund 16“ bleibt „Rund 16“). Wer den Stab
als Schraube nachweisen will, wählt in der Maske des Querschnitts unter „Gewinde“ eine Größe (M12 … M36).
Das Feld „A_s Gewinde“ zeigt dann den Spannungsquerschnitt nach EN ISO 898-1 (M16 157 mm², M20 245 mm²), und
der Stab wird auf Zug nach EN 1993-1-8 nachgewiesen; die Güte kommt aus dem Werkstoff. Passt der
Gewindedurchmesser nicht zum Stabdurchmesser (M20 an Rund 16), erscheint ein Hinweis, gesperrt ist nichts.
Die Auswahl gibt es nur beim Rundstahl. Ohne Gewinde bleibt alles wie vorher.

## Wo Ergebnisse anders ausfallen

* **Prüfmatrix K4** (Fuge mit μ = 0,3, Klotz A haftet, Klotz B gleitet gegen Federn): Der Schlupf von Klotz
  A ist nicht mehr exakt 0, sondern 0,003 bis 0,009 % je nach Element, weil das Haften jetzt eine sehr
  steife Feder ist statt einer starren Zeile. Das sind 0,29 bis 0,93 % der Grenze von 1 %; alle Zellen
  bleiben grün.
* **Prüfmatrix K4 und K5:** Die Reibkraft quer zur Gleitrichtung von Klotz B geht an hex8 und hex20 auf 0
  (bisher bis 0,002 %). Die Federkraft von Klotz B ändert sich in Vorzeichen und Betrag nur im Bereich von
  10⁻³ %. Die Prüfmatrix steht wie vorher bei 86 grünen, 32 gelben, 0 roten und 2 gesperrten Zellen.
* **Klotz und Blechpaket gleiten richtig:** Ein steifer Klotz auf einem Lager mit Reibung, den eine
  Zugfeder hält, galt bei F = 1,5·μ·N bisher als konvergiert, obwohl er nur 1,1 statt 100 µm geglitten war
  und 4,8 % der Last im Gleichgewicht fehlten; die kleine Reststeifigkeit gleitender Knoten trug die Kraft.
  Die Gleichgewichtskontrolle meldet dieses alte Ergebnis als „NICHT gültig“. Jetzt gleitet er auf 10⁻⁴
  genau um (F − μ·N) durch die Federsteifigkeit. Ein vorgespanntes Blechpaket unter Querkraft glitt bei
  1,05·μ·F_v bisher 3,7 statt 30 µm (44 Runden), jetzt 30,003 µm in 8 Runden.
* **Mechanismus ohne Halt** (Block mit H = 1,5·μ·N und nichts, was ihn hält): Das Ergebnis heißt jetzt
  „vorläufig“ statt „konvergiert“.
* **Bisheriges Verfahren nicht mehr bitgleich:** Weil der Deckel jetzt alle Runden zählt, endet das
  bisherige Verfahren öfter am Deckel als vor dem 15.10.2026. Wer es zum Vergleich einschaltet, bekommt
  darum nicht mehr bitgleich die alten Zahlen.
* **Rundenzahlen** an den Prüfmodellen der Kontaktprüfungen, konsistente Tangente gegen bisheriges
  Verfahren: Block mit Reibung 6 statt 29, Stempel auf Sockel 7 statt 14 (plastisch 30 statt 61), Platte mit
  vier vorgespannten Ankern auf einem Lager wie „Starr“ 21 statt 66 Runden und 16 statt 25 Zerlegungen,
  Block nahe der Grenzlast 34 statt 136, kippender Stempel 34 statt 76, Block mit Anschlag 6 statt 13. Die
  Verschiebungen weichen dabei um höchstens 1,4·10⁻⁵ ab. Das Pendelmodell der Kontaktprüfungen mit Fließen
  im Block braucht dagegen mehr Runden als bisher (184 statt 112).
* **Gequetschter Block** (60 MN über der Quetschlast, 13 % plastische Dehnung): Die größte Verschiebung hängt
  an der Zahl der Laststufen, mit der Tangente bei wenigen Stufen deutlicher als bisher (1 Stufe 42,130 mm,
  8 Stufen 42,666 mm). Ab 20 Stufen liegen beide Verfahren auf 0,0001 mm beieinander, und die Reihe
  konvergiert gegen etwa 42,83 mm. Wer ein Bauteil weit über seiner Grenzlast rechnet, teilt die Last fein.
* **Lagerreibung aus RFEM:** Modelle, die mit dem Vorgabewert μ = 0,1 aus RFEM übernommen wurden, ohne dass
  RFEM dort einen Reibungstyp gewählt hatte, rechnen nach dem Nachlesen der Lager (oder bei neuem Import)
  ohne diese Reibung. Am Drehlager steigt dadurch die Kraft an den Knaggen in X auf 3 968,6 kN statt
  3 465,1 kN.

## Hinweise zum Umstieg

* Dateien von vorher lassen sich weiter öffnen. Die neuen Felder (Lastart und Schlupf der Vorspannung,
  Gewinde, Reibverfahren, Merkmale des Imports) stehen nur in der Modelldatei, wenn sie von der Vorgabe
  abweichen. Eine Datei ohne diese Angaben bleibt beim Öffnen und Speichern, wie sie war, abgesehen von den
  Hinweisen zu Zugstäben und Lagerreibung, die als offene Importhinweise mitgespeichert werden.
* Ergebnisdateien von vorher passen weiter. Hat das Modell Reibung, sagt ein Hinweis, dass sie mit dem
  bisherigen Reibverfahren gerechnet sind; für aktuelle Ergebnisse rechnen Sie neu.
* Ein früher übernommenes Drehlager zeigt je einen Hinweis zu Zugstäben, Lagerreibung und Vorspannung;
  keiner davon ändert etwas von selbst.

## Nicht enthalten

Folgende Punkte sind bekannt und bewusst nicht in diesem Stand:

* Die Hebel H1 bis H3 zur Rechenzeit am Drehlager (Zweig `loeser/drehlager-zeit`).
* Eine automatische Umwandlung von ΔT in Vorspannung; es gibt nur den Hinweis und die Umwandlung auf Ihre
  Anweisung.
* Der Bolzennachweis nach EN 1993-1-8, 3.13 für Passstifte (vorgemerkt).
* Maskenfelder für die Kontaktschalter.
* Der Sammelbefehl „Einwirkung für mehrere Lastfälle“.
* Linienlasten in lokalen Achsen.
* Der Hebelarm-Anteil der Feder.
* Die ΣM-Kontrolle in Theorie II. Ordnung.
* Die Kopie des Werkstoffs bei Verbindungen und Vorlagen.
* Die Ermüdung des Spannstahls.
* Nachtrag 2 der Fehlerliste (M01 bis M47).
* Schalen mit Kontakt.
* Ein symmetrischer Löser (Hebel etwa 48 % je Zerlegung; die Matrix ist heute mit gleitenden Reibknoten
  unsymmetrisch).
* Die ama-LU (Zweig `loeser/ama-uebernahme`).
* Die Linux-Fassung.
