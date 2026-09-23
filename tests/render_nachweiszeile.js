// Rendert die Register "Ergebnisse" und "Nachweise" der Weboberflaeche ohne
// Browser und gibt jede Meldungszeile (<div class="msg ...">) mit ihrer Klasse
// als JSON aus. Die Farbe dieser Zeile ist das Urteil, das der Anwender liest:
// gruen (ok), gelb (warn), rot (err). Die Pruefung steht in tests/test_web.py.
// Aufruf:  node tests/render_nachweiszeile.js <app.js> <daten.json>
//          daten.json = {"state": /api/state, "entries": /api/entries,
//                        "result": /api/results, "design": /api/design}
// Der DOM-Ersatz ist derselbe wie in tests/render_check.js.
'use strict';
const fs = require('fs');
const vm = require('vm');

const [appPfad, datenPfad] = process.argv.slice(2);
const quelle = fs.readFileSync(appPfad, 'utf8');
const daten = JSON.parse(fs.readFileSync(datenPfad, 'utf8'));

function element(id) {
  return {
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
const ev = quelltext => vm.runInContext(quelltext, ctx);

ctx.__daten = daten;
ev('S.state = __daten.state; S.entries = __daten.entries; S.result = __daten.result; '
   + 'S.design = __daten.design; view = {opts: {}, draw(){}, resize(){}, fit(){}, setGeometry(){}};');

function zeilen(html) {
  const aus = [];
  const re = /<div class="msg([^"]*)">([^<]*)<\/div>/g;
  let t;
  while ((t = re.exec(html)) !== null) aus.push({klasse: t[1].trim(), text: t[2]});
  return aus;
}
const aus = {};
for (const [tab, fn] of [['ergebnisse', 'renderErgebnisse'], ['nachweise', 'renderNachweise']]) {
  ev(`S.tab = ${JSON.stringify(tab)}`);
  try { aus[tab] = zeilen(ev(`${fn}()`)); } catch (e) { aus[tab] = {fehler: e.message}; }
}
console.log(JSON.stringify(aus));
