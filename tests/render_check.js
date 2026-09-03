// Rendert die Register der Weboberflaeche ohne Browser: app.js wird in einem
// vm-Kontext mit einem winzigen DOM-Ersatz ausgefuehrt, dann werden alle
// render*-Funktionen mit einem echten Zustand (JSON aus dem Server) aufgerufen.
// Aufruf:  node tests/render_check.js <app.js> <zustand.json>
'use strict';
const fs = require('fs');
const vm = require('vm');

const [appPfad, zustandPfad] = process.argv.slice(2);
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
  ergebnisse.push([name, !!ok]);
  console.log(`${ok ? 'OK ' : 'FAIL'} ${name.padEnd(58)} ${detail || ''}`);
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
pruefe('Stellungen als Karten', B.liste.every(x => h.includes(x.name)));
pruefe('Umhuellende genannt', !B.gerechnet || /Umh.llende/.test(h));
pruefe('eta-Kurve gezeichnet', !B.gerechnet || /class="kurve"/.test(h));
pruefe('Kurve hat einen Punkt je Stellung',
       !B.gerechnet || (h.match(/class="punkt/g) || []).length === B.kurve.length);
pruefe('DIN 19704 mit offenen Beiwerten',
       !B.regelwerk || (h.includes('DIN 19704') && h.includes('zu bestätigen')));
pruefe('ZTV-ING-Liste', !B.ztv || !B.ztv.length || h.includes('ZTV-ING'));
pruefe('Formular fuer neue Stellung', h.includes('data-op="stellung"'));
pruefe('Rechnen-Knopf mit Nutzlast', h.includes('stellungen_rechnen'));
pruefe('Keine unaufgeloeste Vorlage', !h.includes('undefined') && !h.includes('[object Object]'));

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
