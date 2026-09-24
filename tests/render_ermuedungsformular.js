// Rendert das Register "Lasten" der Weboberflaeche ohne Browser und gibt die
// Auswahllisten des Formulars "+ Ermüdungslast" (oberer und unterer Zustand)
// als JSON aus: {"case_max": [Werte], "case_min": [Werte]}. Das sind die
// Namen, die der Anwender dort waehlen kann. Die Pruefung steht in
// tests/test_web.py (test_ermuedungslast_zustand_kombination).
// Aufruf:  node tests/render_ermuedungsformular.js <app.js> <zustand.json>
//          zustand.json = /api/state
// Der DOM-Ersatz ist derselbe wie in tests/render_check.js.
'use strict';
const fs = require('fs');
const vm = require('vm');

const [appPfad, zustandPfad] = process.argv.slice(2);
const quelle = fs.readFileSync(appPfad, 'utf8');
const zustand = JSON.parse(fs.readFileSync(zustandPfad, 'utf8'));

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

ctx.__zustand = zustand;
ev("S.state = __zustand; S.tab = 'lasten'; view = {opts: {}, draw(){}, resize(){}, fit(){}, setGeometry(){}};");

const aus = {};
try {
  const html = ev('renderLasten()');
  const formular = (html.match(/<form data-op="add_fatigue_load"[\s\S]*?<\/form>/) || [''])[0];
  if (!formular) aus.fehler = 'Formular add_fatigue_load fehlt';
  for (const name of ['case_max', 'case_min']) {
    const liste = (formular.match(new RegExp(`<select name="${name}"[^>]*>([\\s\\S]*?)</select>`)) || ['', ''])[1];
    aus[name] = [...liste.matchAll(/<option value="([^"]*)"/g)].map(t => t[1]);
  }
} catch (e) {
  aus.fehler = e.message;
}
console.log(JSON.stringify(aus));
