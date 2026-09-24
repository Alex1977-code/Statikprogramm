// Rendert die Register "Ergebnisse" und "Nachweise" der Weboberflaeche ohne
// Browser und gibt jede Meldungszeile (<div class="msg ...">) mit ihrer Klasse
// als JSON aus. Die Farbe dieser Zeile ist das Urteil, das der Anwender liest:
// gruen (ok), gelb (warn), rot (err). Die Pruefung steht in tests/test_web.py.
// Aufruf:  node tests/render_nachweiszeile.js <app.js> <daten.json>
//          daten.json = {"state": /api/state, "entries": /api/entries,
//                        "result": /api/results, "design": /api/design,
//                        "member": {Stab: /api/member} (wahlweise)}
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

// Je Stab, was der Anwender ausser der Nachweiszeile sieht:
//  stabzeilen  - die Zeile der Tabelle "Nachweise EC3" (Register Nachweise)
//  stabdetail  - Ueberschrift mit Status und Ausnutzung des Fensters nach
//                Antippen der Zeile (memberDetail schreibt in #modal-body)
//  stabverlauf - die Meldungszeilen unter "Schnittgrößen am Stab" (memberChart)
//                zu daten.member = {Stab: /api/member?which=...&name=Stab}
aus.stabzeilen = {};
aus.stabdetail = {};
aus.stabverlauf = {};
try {
  ev('S.tab = "nachweise"');
  const hn = ev('renderNachweise()');
  const re = /<tr class="tap" data-action="member-detail" data-name="([^"]*)">([\s\S]*?)<\/tr>/g;
  let t;
  while ((t = re.exec(hn)) !== null) aus.stabzeilen[t[1]] = t[2];
  const stabe = ((daten.design || {}).design || {}).members || {};
  for (const name of Object.keys(stabe)) {
    knoten['#modal-body'] = element('#modal-body');
    ev(`memberDetail(${JSON.stringify(name)})`);
    const h = knoten['#modal-body'].innerHTML;
    aus.stabdetail[name] = {
      kopf: (h.match(/<h2>[\s\S]*?<\/h2>/) || [''])[0],
      ausnutzung: (h.match(/<b>Ausnutzung<\/b><span>([\s\S]*?)<\/span><\/div>/) || ['', ''])[1],
    };
  }
  for (const [name, d] of Object.entries(daten.member || {})) {
    ctx.__stab = d;
    aus.stabverlauf[name] = zeilen(ev('memberChart(__stab)'));
  }
} catch (e) { aus.stabfehler = e.message; }
console.log(JSON.stringify(aus));
