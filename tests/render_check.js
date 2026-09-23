// Rendert die Register der Weboberflaeche ohne Browser: app.js wird in einem
// vm-Kontext mit einem winzigen DOM-Ersatz ausgefuehrt, dann werden alle
// render*-Funktionen mit einem echten Zustand (JSON aus dem Server) aufgerufen.
// Aufruf:  node tests/render_check.js <app.js> <zustand.json> [Vorsatz]
// Der Vorsatz steht vor jedem Pruefungsnamen - so bleiben zwei Laeufe mit
// verschiedenen Zustaenden in einer Suite unterscheidbar.
'use strict';
const fs = require('fs');
const vm = require('vm');

const [appPfad, zustandPfad, vorsatz = ''] = process.argv.slice(2);
const quelle = fs.readFileSync(appPfad, 'utf8');
const zustand = JSON.parse(fs.readFileSync(zustandPfad, 'utf8'));

// --- kleinster DOM-Ersatz -------------------------------------------------
function element(id) {
  const el = {
    id, innerHTML: '', textContent: '', value: '', hidden: false, dataset: {}, style: {},
    className: '', tagName: 'DIV', scrollTop: 0, files: [],
    classList: {_s: new Set(), add(x) { this._s.add(x); }, remove(x) { this._s.delete(x); },
                toggle(x, an) { if (an) this._s.add(x); else this._s.delete(x); },
                contains(x) { return this._s.has(x); }, replace(a, b) { this._s.delete(a); this._s.add(b); }},
    addEventListener() {}, removeEventListener() {}, appendChild() {}, remove() {},
    setPointerCapture() {}, getBoundingClientRect() { return {width: 800, height: 600, left: 0, top: 0}; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; }, requestSubmit() {}, focus() {}, click() {},
  };
  return el;
}
const knoten = {};
const doc = {
  body: element('body'),
  addEventListener() {},
  createElement: () => element('neu'),
  querySelector: s => (knoten[s] = knoten[s] || element(s)),
  querySelectorAll: () => [],
};
const ctx = {
  document: doc, console,
  window: {innerWidth: 1440, innerHeight: 900, addEventListener() {}, devicePixelRatio: 1},
  location: {search: '', host: 'test', reload() {}},
  localStorage: {getItem: () => null, setItem() {}},
  fetch: () => Promise.reject(new Error('kein Netz im Test')),
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0,
  ResizeObserver: function () { this.observe = () => {}; },
  requestAnimationFrame: () => 0, encodeURIComponent, Math, JSON, Set, Map, Number, Array, Object, String, Date,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(quelle, ctx, {filename: 'app.js'});

// --- Zustand setzen und rendern -------------------------------------------
// const/let in app.js liegen im lexikalischen Gueltigkeitsbereich des Skripts,
// nicht auf globalThis: Zugriff darum ueber ausgewerteten Quelltext.
const ev = quelltext => vm.runInContext(quelltext, ctx);
const ergebnisse = [];
function pruefe(name, ok, detail) {
  name = vorsatz + name;
  ergebnisse.push([name, !!ok]);
  // zwei Leerzeichen vor dem Detail: test_web trennt dort den Namen ab,
  // auch wenn der Name (mit Vorsatz) laenger als 58 Zeichen ist
  console.log(`${ok ? 'OK ' : 'FAIL'} ${name.padEnd(58)}  ${detail || ''}`);
}
ctx.__zustand = zustand;
ev('S.state = __zustand; view = {opts: {}, draw(){}, resize(){}, fit(){}, setGeometry(){}};');

for (const [tab, fn] of [['modell', 'renderModell'], ['lasten', 'renderLasten'],
                         ['rechnen', 'renderRechnen'], ['nachweise', 'renderNachweise'],
                         ['bruecke', 'renderBruecke'], ['mehr', 'renderMehr']]) {
  ev(`S.tab = ${JSON.stringify(tab)}`);
  let html = '', fehler = '';
  try { html = ev(`${fn}()`); } catch (e) { fehler = e.message; }
  pruefe(`Register ${tab} rendert`, !fehler && html.length > 50, fehler);
}

ev("S.tab = 'bruecke'");
const h = ev('renderBruecke()');
const B = zustand.stellungen;
// Gerechnete Stellungen; "ohne": mit Warnungen des Stabnachweises und ohne
// einen gefuehrten Nachweis - deren eta = 0 ist keine Ausnutzung. Fehlt das
// Feld "nachgewiesen" (Server von vor dem 23.09.2026), gilt eine Stellung mit
// Warnungen als ohne Nachweis.
const gerechnet = B.liste.filter(x => x.ergebnis && !x.ergebnis.fehler);
const offen = gerechnet.filter(x => (x.ergebnis.warnungen || []).length);
const ohne = offen.filter(x => !x.ergebnis.nachgewiesen);
const bestimmt = gerechnet.filter(x => !ohne.includes(x));
const nichtBestimmt = B.eta_bestimmt === false || (ohne.length > 0 && !bestimmt.length);
pruefe('Stellungen als Karten', B.liste.every(x => h.includes(x.name)));
pruefe('Umhuellende genannt', !B.gerechnet || /Umh.llende/.test(h));
pruefe('eta-Kurve gezeichnet', !B.gerechnet || bestimmt.length < 2 || /class="kurve"/.test(h));
pruefe('Kurve hat einen Punkt je Stellung mit bestimmtem eta',
       !B.gerechnet || bestimmt.length < 2
       || (h.match(/class="punkt/g) || []).length === bestimmt.length);
pruefe('DIN 19704 mit offenen Beiwerten',
       !B.regelwerk || (h.includes('DIN 19704') && h.includes('zu bestätigen')));
pruefe('ZTV-ING-Liste', !B.ztv || !B.ztv.length || h.includes('ZTV-ING'));
pruefe('Formular fuer neue Stellung', h.includes('data-op="stellung"'));
pruefe('Rechnen-Knopf mit Nutzlast', h.includes('stellungen_rechnen'));
pruefe('Keine unaufgeloeste Vorlage', !h.includes('undefined') && !h.includes('[object Object]'));

// --- Stellungen ohne (vollstaendigen) Nachweis ----------------------------
// Gegenpruefung 23.09.2026: Karte, Meldung, Tabelle, Kurve und Filmstreifen
// zeigten "η = 0,000" gruen, also als erfuellt, obwohl kein Nachweis
// gefuehrt war - app.js las "warnungen" und "unvollstaendig" nicht.
const karte = x => ev(`stellungKarte(S.state.stellungen.liste[${B.liste.indexOf(x)}], ${B.liste.indexOf(x)})`);
pruefe('Karte ohne Nachweis: kein eta-Wert, sondern "nicht geführt"',
       ohne.every(x => { const k = karte(x); return !/η \d/.test(k) && k.includes('nicht geführt'); }),
       ohne.length ? karte(ohne[0]).replace(/\s+/g, ' ').slice(0, 160) : '');
pruefe('Karte nicht vollständig nachgewiesen: nicht grün',
       offen.every(x => !karte(x).includes('background:var(--ok)')));
pruefe('Tabelle: eta nur für Stellungen mit Nachweis',
       (h.match(/class="util"/g) || []).length === bestimmt.length,
       `${(h.match(/class="util"/g) || []).length} Werte, ${bestimmt.length} bestimmt`);
const zeileTab = x => (h.match(new RegExp(`<tr class="tap" data-action="edit-stellung" data-name="${x.name}">[\\s\\S]*?</tr>`)) || [''])[0];
pruefe('Tabelle: Stellung nicht vollständig nachgewiesen nicht grün',
       offen.every(x => zeileTab(x) && !zeileTab(x).includes('#2e8b3a')));
pruefe('Kurve: kein Punkt für eine Stellung ohne Nachweis',
       ohne.every(x => !h.includes(`<title>${x.name}:`)));
const zeileUmh = (h.match(/<div class="msg [a-z]+">Umhüllende über alle Stellungen[^<]*<\/div>/) || [''])[0];
pruefe('Umhüllende nicht grün, wenn eine Stellung nicht nachgewiesen ist',
       !B.gerechnet || !offen.length || (zeileUmh && !zeileUmh.includes('msg ok')), zeileUmh);
pruefe('Umhüllende ohne jeden Nachweis: "η nicht bestimmt" statt eines Werts',
       !B.gerechnet || !nichtBestimmt
       || (zeileUmh.includes('η nicht bestimmt') && !/η = \d/.test(zeileUmh)), zeileUmh);
if (offen.length) {
  ev(`S.stellung = ${JSON.stringify(offen[0].name)}`);
  const hs = ev('renderBruecke()');
  const meldung = (hs.match(/<div class="msg [a-z]+">η[^<]*<\/div>/) || [''])[0];
  pruefe('Gewählte Stellung ohne vollständigen Nachweis: Meldung nicht grün',
         meldung && !meldung.includes('msg ok')
         && /nicht vollständig nachgewiesen|kein Nachweis geführt/.test(meldung), meldung);
  // an der Karte der Stellung, nicht nur im zugeklappten Bericht der Reihe
  const n = offen[0].ergebnis.warnungen.length;
  pruefe('Gewählte Stellung: die Warnungen sind aufklappbar',
         hs.includes(`<summary>Nicht nachgewiesen <span class="n">${n}</span></summary>`)
         && hs.includes(esc0(offen[0].ergebnis.warnungen[0]).slice(0, 40)));
}
function esc0(s) { return ev(`esc(${JSON.stringify(s)})`); }

const gewaehlt = B.liste.length ? B.liste[0].name : '';
ev(`S.stellung = ${JSON.stringify(gewaehlt)}`);
const h2 = ev('renderBruecke()');
pruefe('Gewaehlte Stellung wird hervorgehoben', !gewaehlt || h2.includes('stellung aktiv'));

ev('renderBaum()');
const baum = knoten['#baum'].innerHTML;
pruefe('Modellbaum gefuellt', baum.includes('Modellbaum') && baum.includes(zustand.name));
pruefe('Modellbaum zeigt Stellungen', !B.liste.length || baum.includes(B.liste[0].name));
pruefe('Modellbaum zeigt Lastfaelle', baum.includes('Lastfälle'));

ev('renderFilm()');
const film = knoten['#film'].innerHTML;
pruefe('Filmstreifen gefuellt', film.includes('Stellungen des Systems'));
pruefe('Filmstreifen zeigt jede Stellung',
       B.liste.every(x => film.includes(x.name)) || !B.liste.length);
pruefe('Filmstreifen ohne jeden Nachweis: kein eta-Wert der Umhüllenden',
       !B.gerechnet || !nichtBestimmt
       || (!/Umhüllende η = \d/.test(film) && film.includes('η nicht bestimmt')),
       (film.match(/Umhüllende[^<]*/) || [''])[0]);
pruefe('Filmstreifen: nicht vollständig nachgewiesen wird genannt',
       !B.gerechnet || !offen.length || /Umhüllende[^<]*nicht/.test(film),
       (film.match(/Umhüllende[^<]*/) || [''])[0]);

ctx.window.innerWidth = 1440;
ev('updateWerkbank()');
pruefe('Werkbank ab 1100 px', doc.body.classList.contains('werkbank'));
ctx.window.innerWidth = 900;
ev('updateWerkbank()');
pruefe('Handy ohne Werkbank', !doc.body.classList.contains('werkbank'));

const exportHtml = (ev("S.tab = 'mehr'"), ev('renderMehr()'));
pruefe('Exportformate im Register Mehr',
       exportHtml.includes('id="export-fmt"') && exportHtml.includes('.sza'));

const schlecht = ergebnisse.filter(r => !r[1]).map(r => r[0]);
console.log(`\n${ergebnisse.length - schlecht.length}/${ergebnisse.length} Pruefungen bestanden`);
if (schlecht.length) { console.log('FEHLGESCHLAGEN: ' + schlecht.join(', ')); process.exit(1); }
