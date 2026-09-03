'use strict';
/* Statik3D - Bedienung im Browser / auf dem Handy. Keine externen Abhaengigkeiten. */

// ======================================================================
// Hilfen
// ======================================================================
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const enc = encodeURIComponent;

function fmt(v, d = 2) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '–';
  return Number(v).toLocaleString('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d});
}
function g(v, d = 4) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '–';
  const n = Number(v);
  if (n === 0) return '0';
  if (Math.abs(n) >= 1e6 || Math.abs(n) < 1e-4) return n.toExponential(2).replace('.', ',');
  return String(+n.toPrecision(d)).replace('.', ',');
}
let toastTimer = null;
function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = kind;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, kind === 'err' ? 7000 : 2500);
}
function modal(html) {
  $('#modal-body').innerHTML = html + '<div class="btns" style="margin-top:10px"><button class="btn wide" data-action="close-modal">Schließen</button></div>';
  $('#modal').hidden = false;
  bindActions($('#modal-body'));
}
function closeModal() { $('#modal').hidden = true; }

function inp(name, label, val = '', attrs = '') {
  return `<label><span>${esc(label)}</span><input name="${esc(name)}" value="${esc(val)}" ${attrs}></label>`;
}
function num(name, label, val = '', o = {}) {
  const a = [`type="number"`, `step="${o.step ?? 'any'}"`, `inputmode="decimal"`];
  if (o.scale) a.push(`data-scale="${o.scale}"`);
  if (o.int) a.push(`data-type="int"`);
  if (o.min !== undefined) a.push(`min="${o.min}"`);
  if (o.max !== undefined) a.push(`max="${o.max}"`);
  if (o.ph) a.push(`placeholder="${esc(o.ph)}"`);
  return inp(name, label, val, a.join(' '));
}
function sel(name, label, options, val = '', attrs = '') {
  const opts = options.map(o => {
    const [v, t] = Array.isArray(o) ? o : [o, o];
    return `<option value="${esc(v)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(t)}</option>`;
  }).join('');
  return `<label><span>${esc(label)}</span><select name="${esc(name)}" ${attrs}>${opts}</select></label>`;
}
function chk(name, label, on = false, attrs = '') {
  return `<label class="chk"><input type="checkbox" name="${esc(name)}" ${on ? 'checked' : ''} ${attrs}>${esc(label)}</label>`;
}
function selInput(kind, label = null) {
  // Eingabefeld, das die aktuelle Auswahl (Knoten / Elemente) uebernimmt
  const name = kind === 'nodes' ? 'nodes' : 'elems';
  const lab = label || (kind === 'nodes' ? 'Knoten (Auswahl in 3D-Ansicht)' : 'Elemente (Auswahl in 3D-Ansicht)');
  return `<label><span>${esc(lab)}</span><input name="${name}" data-sel="${kind}" data-type="list" value="${selText(kind)}" placeholder="z.B. 1, 2, 5"></label>`;
}
function selText(kind) { return Array.from(kind === 'nodes' ? S.sel.nodes : S.sel.elems).sort((a, b) => a - b).join(', '); }
function utilBadge(u) {
  if (u === null || u === undefined || Number.isNaN(Number(u))) return '<span class="muted">–</span>';
  const v = Number(v0(u));
  const col = v > 1 ? '#c62828' : v > 0.85 ? '#e5701c' : v > 0.6 ? '#d4b000' : '#2e8b3a';
  return `<span class="util" style="background:${col}">${fmt(v, 2)}</span>`;
}
function v0(u) { return u; }
function table(header, rows, o = {}) {
  const th = header.map(hh => `<th>${esc(hh)}</th>`).join('');
  const tr = rows.map((r, i) => {
    const tds = r.map((c, j) => {
      const f = o.format ? o.format(c, j, r) : null;
      if (f !== null && f !== undefined) return `<td class="${o.cls ? o.cls(c, j, r) : ''}">${f}</td>`;
      return `<td>${typeof c === 'number' ? fmt(c, o.dec ?? 2) : esc(c)}</td>`;
    }).join('');
    const attr = o.rowAttr ? o.rowAttr(r, i) : '';
    return `<tr ${attr}>${tds}</tr>`;
  }).join('');
  return `<div class="scroll"><table class="t"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table></div>`;
}

// ======================================================================
// API
// ======================================================================
const API = {
  key: '',
  load() { try { this.key = localStorage.getItem('statik3d.key') || ''; } catch (e) { this.key = ''; }
    const m = location.search.match(/[?&]key=([^&]*)/); if (m) this.save(decodeURIComponent(m[1])); },
  save(k) { this.key = k; try { localStorage.setItem('statik3d.key', k); } catch (e) { /* privat */ } },
  url(path) { return this.key ? path + (path.includes('?') ? '&' : '?') + 'key=' + enc(this.key) : path; },
  async req(method, path, body, opts = {}) {
    const headers = {};
    if (this.key) headers['X-Statik-Key'] = this.key;
    let payload = body;
    if (body !== undefined && !(body instanceof Blob) && !(body instanceof ArrayBuffer)) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    let r;
    try { r = await fetch(path, {method, headers, body: payload}); }
    catch (e) { throw new Error('Keine Verbindung zum Server (läuft python run_web.py noch?)'); }
    if (r.status === 401) { askKey(); throw new Error('Schlüssel fehlt oder falsch'); }
    const text = await r.text();
    let j;
    try { j = JSON.parse(text); } catch (e) { throw new Error('Antwort ungültig: ' + text.slice(0, 120)); }
    if (!r.ok) throw new Error(j.error || r.statusText);
    return j;
  },
  get(p) { return this.req('GET', p); },
  post(p, b) { return this.req('POST', p, b ?? {}); },
};

function askKey() {
  if (!$('#modal').hidden && $('#key-input')) return;
  modal(`<h2>Zugangsschlüssel</h2><p class="muted">Der Server wurde mit <code>--schluessel</code> gestartet. Bitte den Schlüssel eingeben (wird auf diesem Gerät gespeichert).</p>
    <input id="key-input" value="${esc(API.key)}" autocomplete="off" placeholder="Schlüssel">
    <div class="btns" style="margin-top:8px"><button class="btn primary wide" data-action="save-key">Verbinden</button></div>`);
  setTimeout(() => $('#key-input')?.focus(), 50);
}

// ======================================================================
// Zustand
// ======================================================================
const S = {
  state: null, geom: null, tab: 'modell', entries: [], result: null, diagram: null, design: null,
  ro: {which: '', field: 'umag', mode: 0, diagram: '', deform: true, scale: null, factor: 0},
  sel: {nodes: new Set(), elems: new Set()},
  job: null, pollTimer: null, version: -1, member: '', profiles: {}, first: true,
};

// ======================================================================
// 3D-Ansicht (Canvas, orthografisch, Malerverfahren)
// ======================================================================
function cmap(t) {
  const st = [[0, 44, 79, 191], [0.25, 34, 167, 201], [0.5, 89, 193, 90], [0.75, 242, 210, 58], [1, 210, 53, 47]];
  t = Math.max(0, Math.min(1, Number.isFinite(t) ? t : 0));
  for (let i = 1; i < st.length; i++) {
    if (t <= st[i][0]) {
      const a = st[i - 1], b = st[i], f = (t - a[0]) / (b[0] - a[0] || 1);
      return `rgb(${Math.round(a[1] + f * (b[1] - a[1]))},${Math.round(a[2] + f * (b[2] - a[2]))},${Math.round(a[3] + f * (b[3] - a[3]))})`;
    }
  }
  return 'rgb(210,53,47)';
}
function distSeg(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
  let t = l2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / l2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function inTri(px, py, ax, ay, bx, by, cx, cy) {
  const d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by);
  const d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy);
  const d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay);
  const neg = d1 < 0 || d2 < 0 || d3 < 0, pos = d1 > 0 || d2 > 0 || d3 > 0;
  return !(neg && pos);
}

class View3D {
  constructor(canvas) {
    this.c = canvas;
    this.ctx = canvas.getContext('2d');
    this.yaw = -0.62; this.pitch = 0.52; this.zoom = 1; this.pan = {x: 0, y: 0};
    this.center = [0, 0, 0]; this.radius = 1;
    this.geom = null; this.nodes = []; this.result = null; this.diagram = null;
    this.opts = {deform: true, labels: false, scale: 1, edges: true};
    this.pickMode = 'nodes';
    this.pointers = new Map(); this.gesture = null;
    this.onPick = null;
    this._bind();
  }
  resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = this.c.getBoundingClientRect();
    this.w = Math.max(1, r.width); this.h = Math.max(1, r.height);
    this.c.width = Math.round(this.w * dpr); this.c.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.draw();
  }
  setGeometry(gm) {
    this.geom = gm; this.nodes = gm.nodes;
    this.elemLine = {}; this.elemTris = {};
    gm.line_elem.forEach((e, i) => { this.elemLine[e] = i; });
    gm.tri_elem.forEach((e, i) => { (this.elemTris[e] = this.elemTris[e] || []).push(i); });
  }
  fit() {
    if (!this.geom || !this.nodes.length) { this.draw(); return; }
    const [lo, hi] = this.geom.bbox;
    this.center = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
    const d = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]);
    this.radius = d > 0 ? d / 2 : 1;
    this.zoom = 1; this.pan = {x: 0, y: 0};
    this.draw();
  }
  setView(name) {
    const v = {iso: [-0.62, 0.52], xy: [0, Math.PI / 2], xz: [0, 0], yz: [-Math.PI / 2, 0]}[name];
    if (v) { this.yaw = v[0]; this.pitch = v[1]; }
    this.fit();
  }
  _basis() {
    this.B = {cy: Math.cos(this.yaw), sy: Math.sin(this.yaw), cp: Math.cos(this.pitch), sp: Math.sin(this.pitch)};
    this.k = Math.min(this.w, this.h) / (2.3 * this.radius) * this.zoom;
    this.c0 = this._proj(this.center);
  }
  _proj(p) {   // Drehung um z (yaw), Neigung (pitch): [Bild-x, Bild-y, Tiefe zum Betrachter]
    const {cy, sy, cp, sp} = this.B;
    const x1 = cy * p[0] - sy * p[1], y1 = sy * p[0] + cy * p[1], z1 = p[2];
    return [x1, y1 * sp + z1 * cp, z1 * sp - y1 * cp];
  }
  toScreen(p) {
    const q = this._proj(p);
    return [this.w / 2 + (q[0] - this.c0[0]) * this.k + this.pan.x,
            this.h / 2 - (q[1] - this.c0[1]) * this.k + this.pan.y, q[2]];
  }
  displayedNodes() {
    const N = this.nodes, R = this.result;
    if (this.opts.deform && R && R.u && R.u.length === N.length) {
      const s = this.opts.scale;
      return N.map((p, i) => [p[0] + R.u[i][0] * s, p[1] + R.u[i][1] * s, p[2] + R.u[i][2] * s]);
    }
    return N;
  }
  _shade(a, b, c) {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    const n = [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx];
    const l = Math.hypot(n[0], n[1], n[2]) || 1;
    const q = this._proj([n[0] / l, n[1] / l, n[2] / l]);
    const br = 0.55 + 0.45 * Math.abs(q[2]) + 0.1 * Math.abs(q[1]);
    return `rgb(${Math.round(150 * br)},${Math.round(178 * br)},${Math.round(205 * br)})`;
  }
  draw() {
    const ctx = this.ctx;
    if (!this.w) return;
    ctx.clearRect(0, 0, this.w, this.h);
    if (!this.geom || !this.nodes.length) {
      ctx.fillStyle = '#7d8790'; ctx.font = '14px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText('Kein Modell – unter „Mehr“ ein Beispiel laden oder eine Datei öffnen', this.w / 2, this.h / 2);
      return;
    }
    this._basis();
    const P = this.displayedNodes(), n = P.length;
    const sx = new Float64Array(n), sy = new Float64Array(n), sz = new Float64Array(n);
    for (let i = 0; i < n; i++) { const q = this.toScreen(P[i]); sx[i] = q[0]; sy[i] = q[1]; sz[i] = q[2]; }
    this.sx = sx; this.sy = sy; this.sz = sz;
    const gm = this.geom, R = this.result;
    const cn = R && R.scalar_nodes ? R.scalar_nodes : null;
    const ce = R && R.scalar_elems ? R.scalar_elems : null;
    let lo = R ? R.smin : 0, hi = R ? R.smax : 1;
    if (R && (R.field === 'util' || R.field === 'util_fat' || R.field === 'util_el')) { lo = 0; hi = Math.max(1, hi); }
    const rng = (hi - lo) || 1;
    const cv = v => cmap((v - lo) / rng);
    const prims = [];
    const T = gm.tris, TE = gm.tri_elem;
    for (let t = 0; t < T.length; t++) {
      const [a, b, c] = T[t];
      let col;
      if (cn) col = cv((cn[a] + cn[b] + cn[c]) / 3);
      else if (ce) { const v = ce[TE[t]]; col = v == null ? '#c8ced4' : cv(v); }
      else col = this._shade(P[a], P[b], P[c]);
      prims.push({d: (sz[a] + sz[b] + sz[c]) / 3, t: 1, a, b, c, col, sel: S.sel.elems.has(TE[t])});
    }
    const L = gm.lines, LE = gm.line_elem;
    for (let l = 0; l < L.length; l++) {
      const [a, b] = L[l];
      let col = '#2b3742';
      if (cn) col = cv((cn[a] + cn[b]) / 2);
      else if (ce) { const v = ce[LE[l]]; col = v == null ? '#aeb6be' : cv(v); }
      prims.push({d: (sz[a] + sz[b]) / 2 + 1e-9, t: 0, a, b, col, truss: gm.types[LE[l]] === 'truss', sel: S.sel.elems.has(LE[l])});
    }
    prims.sort((p, q) => p.d - q.d);
    const edges = this.opts.edges && T.length < 25000;
    for (const p of prims) {
      if (p.t === 1) {
        ctx.beginPath(); ctx.moveTo(sx[p.a], sy[p.a]); ctx.lineTo(sx[p.b], sy[p.b]); ctx.lineTo(sx[p.c], sy[p.c]); ctx.closePath();
        ctx.fillStyle = p.sel ? '#ff9f43' : p.col; ctx.fill();
        if (edges) { ctx.strokeStyle = 'rgba(30,40,50,.30)'; ctx.lineWidth = 0.6; ctx.stroke(); }
      } else {
        ctx.beginPath(); ctx.moveTo(sx[p.a], sy[p.a]); ctx.lineTo(sx[p.b], sy[p.b]);
        ctx.strokeStyle = p.sel ? '#ff6b00' : p.col; ctx.lineWidth = p.sel ? 5 : (p.truss ? 2 : 3); ctx.lineCap = 'round'; ctx.stroke();
      }
    }
    if (this.diagram) this._drawDiagram(ctx);
    this._drawMarkers(ctx, P);
    this._drawTriad(ctx);
  }
  _drawDiagram(ctx) {
    const D = this.diagram;
    ctx.lineWidth = 1.5;
    let vmaxAbs = 0, labelAt = null;
    for (const poly of D.polys) {
      const B = poly.base.map(p => this.toScreen(p)), Tp = poly.tip.map(p => this.toScreen(p));
      ctx.beginPath();
      ctx.moveTo(B[0][0], B[0][1]);
      for (const q of Tp) ctx.lineTo(q[0], q[1]);
      ctx.lineTo(B[B.length - 1][0], B[B.length - 1][1]);
      ctx.closePath();
      ctx.fillStyle = 'rgba(229,112,28,.22)'; ctx.fill();
      ctx.strokeStyle = '#e5701c'; ctx.stroke();
      poly.vals.forEach((v, i) => { if (Math.abs(v) > vmaxAbs) { vmaxAbs = Math.abs(v); labelAt = [Tp[i], v]; } });
    }
    if (labelAt && D.polys.length) {
      ctx.fillStyle = '#b3510f'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'left';
      ctx.fillText(`${D.quantity} = ${fmt(labelAt[1], 2)} ${D.unit}`, labelAt[0][0] + 6, labelAt[0][1] - 4);
    }
  }
  _drawMarkers(ctx, P) {
    const gm = this.geom, sx = this.sx, sy = this.sy;
    const tri = (x, y, col, s = 8) => { ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - s, y + 1.7 * s); ctx.lineTo(x + s, y + 1.7 * s); ctx.closePath(); ctx.fillStyle = col; ctx.fill(); };
    for (const s of gm.supports) {
      const i = s.node; if (i >= sx.length) continue;
      tri(sx[i], sy[i], s.spring ? '#7cb342' : '#207020');
      if (s.dofs.length === 6) { ctx.strokeStyle = '#207020'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(sx[i] - 9, sy[i] + 16); ctx.lineTo(sx[i] + 9, sy[i] + 16); ctx.stroke(); }
    }
    for (const c of gm.csupports) { const i = c.node; if (i < sx.length) tri(sx[i], sy[i], '#c8a000', 7); }
    ctx.setLineDash([4, 3]); ctx.strokeStyle = '#c8a000'; ctx.lineWidth = 1.5;
    for (const [a, b] of gm.gaps) { ctx.beginPath(); ctx.moveTo(sx[a], sy[a]); ctx.lineTo(sx[b], sy[b]); ctx.stroke(); }
    ctx.setLineDash([]);
    ctx.fillStyle = '#1565c0';
    for (const i of gm.pair_nodes) { if (i < sx.length) { ctx.beginPath(); ctx.arc(sx[i], sy[i], 3, 0, 7); ctx.fill(); } }
    // Gelenke
    for (const [e, end] of gm.hinges) {
      const l = this.elemLine[e]; if (l === undefined) continue;
      const [a, b] = gm.lines[l]; const i = end ? b : a, j = end ? a : b;
      const x = sx[i] + 0.12 * (sx[j] - sx[i]), y = sy[i] + 0.12 * (sy[j] - sy[i]);
      ctx.beginPath(); ctx.arc(x, y, 4, 0, 7); ctx.fillStyle = '#fff'; ctx.fill(); ctx.strokeStyle = '#2b3742'; ctx.lineWidth = 1.5; ctx.stroke();
    }
    // Lasten
    if (this.opts.loads !== false) {
      ctx.strokeStyle = '#c02020'; ctx.fillStyle = '#c02020'; ctx.lineWidth = 2;
      for (const ar of gm.arrows) {
        const p1 = this.toScreen(ar.p), p0 = this.toScreen([ar.p[0] - ar.v[0], ar.p[1] - ar.v[1], ar.p[2] - ar.v[2]]);
        const dx = p1[0] - p0[0], dy = p1[1] - p0[1], l = Math.hypot(dx, dy);
        if (l < 2) continue;
        ctx.beginPath(); ctx.moveTo(p0[0], p0[1]); ctx.lineTo(p1[0], p1[1]); ctx.stroke();
        const ux = dx / l, uy = dy / l, hs = Math.min(9, l * 0.5);
        ctx.beginPath(); ctx.moveTo(p1[0], p1[1]); ctx.lineTo(p1[0] - hs * ux + 0.5 * hs * uy, p1[1] - hs * uy - 0.5 * hs * ux);
        ctx.lineTo(p1[0] - hs * ux - 0.5 * hs * uy, p1[1] - hs * uy + 0.5 * hs * ux); ctx.closePath(); ctx.fill();
      }
      if (gm.gravity) { ctx.fillStyle = '#c02020'; ctx.font = 'bold 12px sans-serif'; ctx.textAlign = 'right'; ctx.fillText('g ↓', this.w - 10, 56); }
    }
    // Kontaktstatus
    const CM = this.result && this.result.contact_markers;
    if (CM) {
      const col = {offen: '#9e9e9e', Kontakt: '#1565c0', Haften: '#2e7d32', Gleiten: '#e65100'};
      for (const m of CM) { if (m.node < sx.length) { ctx.beginPath(); ctx.arc(sx[m.node], sy[m.node], 5, 0, 7); ctx.fillStyle = col[m.status] || '#999'; ctx.fill(); } }
    }
    // Auswahl
    ctx.lineWidth = 2; ctx.strokeStyle = '#1467c6'; ctx.fillStyle = 'rgba(255,255,255,.9)';
    for (const i of S.sel.nodes) { if (i < sx.length) { ctx.beginPath(); ctx.arc(sx[i], sy[i], 6, 0, 7); ctx.fill(); ctx.stroke(); } }
    // Nummern
    if (this.opts.labels) {
      ctx.font = '10px sans-serif'; ctx.textAlign = 'left';
      if (sx.length <= 600) { ctx.fillStyle = '#1467c6'; for (let i = 0; i < sx.length; i++) ctx.fillText(i, sx[i] + 5, sy[i] - 4); }
      if (gm.lines.length <= 600) { ctx.fillStyle = '#7a3e00'; gm.lines.forEach((ln, l) => ctx.fillText('E' + gm.line_elem[l], (sx[ln[0]] + sx[ln[1]]) / 2 + 3, (sy[ln[0]] + sy[ln[1]]) / 2 + 10)); }
    }
  }
  _drawTriad(ctx) {
    const ox = 30, oy = this.h - 34, L = 22;
    const ax = [['x', [1, 0, 0], '#c62828'], ['y', [0, 1, 0], '#2e8b3a'], ['z', [0, 0, 1], '#1467c6']];
    ctx.lineWidth = 2; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'center';
    for (const [n, v, col] of ax) {
      const q = this._proj(v);
      ctx.strokeStyle = col; ctx.fillStyle = col;
      ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox + q[0] * L, oy - q[1] * L); ctx.stroke();
      ctx.fillText(n, ox + q[0] * (L + 9), oy - q[1] * (L + 9) + 4);
    }
  }
  pick(x, y) {
    if (!this.sx) return;
    const gm = this.geom;
    if (this.pickMode === 'nodes') {
      let best = -1, bd = 22 * 22;
      for (let i = 0; i < this.sx.length; i++) { const d = (this.sx[i] - x) ** 2 + (this.sy[i] - y) ** 2; if (d < bd) { bd = d; best = i; } }
      if (best >= 0) { if (S.sel.nodes.has(best)) S.sel.nodes.delete(best); else S.sel.nodes.add(best); this.onPick && this.onPick('node', best); }
    } else {
      let bestE = -1, bl = 14;
      for (let l = 0; l < gm.lines.length; l++) {
        const [a, b] = gm.lines[l];
        const d = distSeg(x, y, this.sx[a], this.sy[a], this.sx[b], this.sy[b]);
        if (d < bl) { bl = d; bestE = gm.line_elem[l]; }
      }
      if (bestE < 0) {
        let bz = -Infinity;
        for (let t = 0; t < gm.tris.length; t++) {
          const [a, b, c] = gm.tris[t];
          if (inTri(x, y, this.sx[a], this.sy[a], this.sx[b], this.sy[b], this.sx[c], this.sy[c])) {
            const z = (this.sz[a] + this.sz[b] + this.sz[c]) / 3;
            if (z > bz) { bz = z; bestE = gm.tri_elem[t]; }
          }
        }
      }
      if (bestE >= 0) { if (S.sel.elems.has(bestE)) S.sel.elems.delete(bestE); else S.sel.elems.add(bestE); this.onPick && this.onPick('elem', bestE); }
    }
    this.draw();
  }
  _bind() {
    const c = this.c;
    c.addEventListener('pointerdown', e => {
      c.setPointerCapture(e.pointerId);
      this.pointers.set(e.pointerId, {x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, t: Date.now(), b: e.button});
      if (this.pointers.size === 2) {
        const [p1, p2] = [...this.pointers.values()];
        this.gesture = {dist: Math.hypot(p1.x - p2.x, p1.y - p2.y), mid: {x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2}};
      }
    });
    c.addEventListener('pointermove', e => {
      const p = this.pointers.get(e.pointerId); if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY;
      if (this.pointers.size === 1) {
        if (p.b === 2 || p.b === 1 || e.shiftKey) { this.pan.x += dx; this.pan.y += dy; }
        else { this.yaw -= dx * 0.008; this.pitch = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, this.pitch + dy * 0.008)); }
        this.draw();
      } else if (this.pointers.size === 2) {
        const [p1, p2] = [...this.pointers.values()];
        const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y), mid = {x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2};
        if (this.gesture) {
          this.zoom = Math.max(0.03, Math.min(300, this.zoom * dist / (this.gesture.dist || dist)));
          this.pan.x += mid.x - this.gesture.mid.x; this.pan.y += mid.y - this.gesture.mid.y;
        }
        this.gesture = {dist, mid};
        this.draw();
      }
    });
    const up = e => {
      const p = this.pointers.get(e.pointerId);
      this.pointers.delete(e.pointerId); this.gesture = null;
      if (p && this.pointers.size === 0 && p.b === 0 && Math.hypot(e.clientX - p.x0, e.clientY - p.y0) < 8 && Date.now() - p.t < 700) {
        const r = this.c.getBoundingClientRect();
        this.pick(e.clientX - r.left, e.clientY - r.top);
      }
    };
    c.addEventListener('pointerup', up);
    c.addEventListener('pointercancel', up);
    c.addEventListener('wheel', e => { e.preventDefault(); this.zoom = Math.max(0.03, Math.min(300, this.zoom * Math.exp(-e.deltaY * 0.0015))); this.draw(); }, {passive: false});
    c.addEventListener('contextmenu', e => e.preventDefault());
    c.addEventListener('dblclick', () => this.fit());
  }
}
let view = null;

// ======================================================================
// Daten laden
// ======================================================================
function setPill(text, cls = '') { const p = $('#status-pill'); p.textContent = text; p.className = 'pill ' + cls; }
function updateHeader() {
  const s = S.state; if (!s) return;
  $('#model-name').textContent = `${s.name} · ${s.nn} Kn · ${s.ne} El`;
  if (s.busy) setPill('rechnet…', 'busy');
  else if (s.has_analysis || s.single) setPill('Ergebnisse', 'ok');
  else setPill('bereit');
}
async function refreshState() {
  S.state = await API.get('/api/state');
  S.version = S.state.version;
  updateHeader();
}
async function refreshGeometry() {
  S.geom = await API.get('/api/geometry');
  view.setGeometry(S.geom);
  if (S.first) { view.fit(); S.first = false; } else view.draw();
  updateSelInfo();
}
async function loadResults() {
  const s = S.state;
  if (!s || !(s.has_analysis || s.single)) { S.entries = []; S.result = null; S.diagram = null; view.result = null; view.diagram = null; updateLegend(); view.draw(); return; }
  S.entries = await API.get('/api/entries');
  if (!S.entries.length) { S.result = null; view.result = null; view.draw(); return; }
  if (!S.entries.find(e => e.id === S.ro.which)) S.ro.which = S.entries[0].id;
  S.result = await API.get(`/api/results?which=${enc(S.ro.which)}&field=${enc(S.ro.field)}&mode=${S.ro.mode}`);
  if (S.ro.diagram) {
    try { S.diagram = await API.get(`/api/diagram?which=${enc(S.ro.which)}&quantity=${enc(S.ro.diagram)}`); }
    catch (e) { S.diagram = null; toast(e.message, 'err'); }
  } else S.diagram = null;
  view.result = S.result; view.diagram = S.diagram;
  if (S.ro.scale === null || S.ro.autoWhich !== S.ro.which) {
    const umax = S.result.umax || 0;
    S.ro.scale = umax > 0 ? 0.08 * (S.geom ? S.geom.size : 1) / umax : 1;
    S.ro.autoWhich = S.ro.which; S.ro.factor = 0;
  }
  view.opts.scale = S.ro.scale * Math.pow(10, S.ro.factor);
  view.opts.deform = S.ro.deform;
  updateLegend();
  view.draw();
}
async function refreshAll() {
  await refreshState();
  await refreshGeometry();
  await loadResults();
  render();
  if (S.state.busy) pollJob();
}
function updateLegend() {
  const el = $('#legend'), R = S.result;
  if (!R || (R.scalar_nodes === undefined && R.scalar_elems === undefined) || !R.scalar_label) { el.hidden = true; return; }
  let lo = R.smin, hi = R.smax;
  if (['util', 'util_fat', 'util_el'].includes(R.field)) { lo = 0; hi = Math.max(1, hi); }
  el.hidden = false;
  el.innerHTML = `<div>${esc(R.scalar_label)}</div><div class="bar"></div><div class="lab"><span>${g(lo, 3)}</span><span>${g(hi, 3)}</span></div>`;
}
function updateSelInfo() {
  const n = S.sel.nodes.size, e = S.sel.elems.size;
  const parts = [];
  if (n) parts.push(`${n} Knoten: ${selText('nodes').slice(0, 60)}`);
  if (e) parts.push(`${e} Elemente: ${selText('elems').slice(0, 60)}`);
  $('#sel-info').textContent = parts.join(' · ');
  $$('[data-sel]').forEach(i => { i.value = selText(i.dataset.sel); });
}

// ======================================================================
// Operationen / Auftraege
// ======================================================================
async function runOp(payload, o = {}) {
  try {
    const r = await API.post('/api/op', payload);
    S.state = r.state; S.version = r.state.version; updateHeader();
    if (r.message && !o.quiet) toast(r.message, 'ok');
    if (r.geometry_changed) await refreshGeometry();
    if (!S.state.has_analysis && !S.state.single) { S.result = null; S.diagram = null; view.result = null; view.diagram = null; updateLegend(); view.draw(); }
    else if (payload.op !== 'check') await loadResults();
    if (!o.norender) render();
    return r;
  } catch (e) { toast(e.message, 'err'); return null; }
}
async function startJob(path, body) {
  try {
    const r = await API.post(path, body);
    S.job = r.job; setPill('rechnet…', 'busy');
    pollJob();
    render();
  } catch (e) { toast(e.message, 'err'); }
}
function pollJob() {
  clearTimeout(S.pollTimer);
  const tick = async () => {
    let j;
    try { j = await API.get('/api/job'); } catch (e) { S.pollTimer = setTimeout(tick, 2000); return; }
    S.job = j; updateJobUI();
    if (j.status === 'laeuft') { S.pollTimer = setTimeout(tick, 700); return; }
    await refreshState();
    if (j.status === 'fertig') { toast('Berechnung abgeschlossen', 'ok'); S.ro.scale = null; await loadResults(); if (S.tab === 'rechnen') S.tab = 'ergebnisse'; }
    else if (j.status === 'fehler') toast('Fehler: ' + j.error, 'err');
    render();
  };
  tick();
}
function updateJobUI() {
  const box = $('#job-box'); if (!box || !S.job) return;
  const j = S.job;
  box.innerHTML = jobHTML(j);
  const pre = $('#job-log'); if (pre) pre.scrollTop = pre.scrollHeight;
}
function jobHTML(j) {
  if (!j) return '';
  const st = j.status === 'laeuft' ? '<div class="progress"><div></div></div>' : '';
  const cls = j.status === 'fehler' ? 'err' : j.status === 'fertig' ? 'ok' : '';
  return `<div class="msg ${cls}"><b>${esc(j.label)}</b> – ${esc(j.status)} (${fmt(j.elapsed, 1)} s)</div>${st}<pre id="job-log">${esc((j.messages || []).slice(-40).join('\n'))}${j.error ? '\n' + esc(j.error) : ''}${j.result ? '\n\n' + esc(j.result) : ''}</pre>`;
}

function collect(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled || el.type === 'submit' || el.type === 'button') continue;
    let v;
    if (el.type === 'checkbox') v = el.checked;
    else {
      v = el.value;
      const dt = el.dataset.type;
      if (v === '' && !el.dataset.keep) continue;
      if (dt === 'int') v = parseInt(v, 10);
      else if (dt === 'list' || dt === 'str' || dt === 'vec') { /* Text durchreichen */ }
      else if (el.type === 'number' || dt === 'num') { v = parseFloat(String(v).replace(',', '.')); if (el.dataset.scale) v *= parseFloat(el.dataset.scale); }
    }
    const path = el.name.split('.');
    let o = out;
    for (let i = 0; i < path.length - 1; i++) {
      const k = path[i];
      const nextIsIdx = /^\d+$/.test(path[i + 1]);
      if (o[k] === undefined) o[k] = nextIsIdx ? [] : {};
      o = o[k];
    }
    const last = path[path.length - 1];
    if (Array.isArray(o)) o[parseInt(last, 10)] = v; else o[last] = v;
  }
  return out;
}

// ======================================================================
// Register: Modell
// ======================================================================
function matOpts(s) { return Object.keys(s.materials).map(k => [k, k]); }
function secOpts(s) { return Object.keys(s.sections).map(k => [k, `${k} (${s.sections[k].describe})`]); }
function shellOpts(s) { return Object.keys(s.shells).map(k => [k, `${k} (t = ${g(s.shells[k].t * 1000, 3)} mm)`]); }
function caseOpts(s, extra = []) { return extra.concat(s.load_cases.map(c => [c.name, `${c.name} (${c.category})`])); }
function opBtn(payload, label, cls = 'btn small', confirm = '') {
  return `<button class="${cls}" data-action="op" data-payload="${esc(JSON.stringify(payload))}" ${confirm ? `data-confirm="${esc(confirm)}"` : ''}>${label}</button>`;
}

function renderModell() {
  const s = S.state;
  const types = Object.entries(s.types).map(([k, v]) => `${v} ${k}`).join(', ') || '–';
  const mats = Object.values(s.materials), secs = Object.values(s.sections), shells = Object.values(s.shells);
  const selE = Array.from(S.sel.elems);
  return `
<details open><summary>Projekt <span class="n">${esc(s.name)}</span></summary><div class="body">
  <form data-op="meta"><div class="grid2">
    ${inp('name', 'Modellname', s.name)}${inp('fields.projekt', 'Projekt', s.meta.projekt)}
    ${inp('fields.bauteil', 'Bauteil', s.meta.bauteil)}${inp('fields.position', 'Position', s.meta.position)}
    ${inp('fields.bearbeiter', 'Bearbeiter', s.meta.bearbeiter)}${inp('fields.auftraggeber', 'Auftraggeber', s.meta.auftraggeber)}
  </div><button class="btn small">Speichern</button></form>
  <div class="kv" style="margin-top:8px"><b>Knoten</b><span>${s.nn}</span><b>Elemente</b><span>${s.ne} (${esc(types)})</span>
  <b>Lager</b><span>${s.n_supports}</span><b>Lastfälle</b><span>${s.load_cases.length}</span><b>Kombinationen</b><span>${s.combinations.length}</span><b>Stäbe</b><span>${s.members.length}</span></div>
</div></details>

<details><summary>Materialien <span class="n">${mats.length}</span></summary><div class="body">
  <ul class="list">${mats.map(m => `<li><span class="txt">${esc(m.name)}<span class="sub">E = ${g(m.E / 1e9)} GPa · fy = ${m.fy ? g(m.fy / 1e6) : '–'} MPa · ρ = ${g(m.rho)} kg/m³</span></span>${opBtn({op: 'remove_material', name: m.name}, '✕', 'btn small danger')}</li>`).join('') || '<li class="muted">keine</li>'}</ul>
  <form data-op="add_material" data-reset><div class="row">${sel('grade', 'Stahlsorte EN 10025', s.grades, 'S355')}${inp('name', 'Name (optional)', '')}<button class="btn small primary">+ Stahl</button></div></form>
  <details><summary>Eigenes Material</summary><div class="body"><form data-op="add_material" data-reset><div class="grid3">
    ${inp('name', 'Name', '')}${num('E', 'E [GPa]', 210, {scale: 1e9})}${num('nu', 'ν [-]', 0.3)}
    ${num('rho', 'ρ [kg/m³]', 7850)}${num('fy', 'fy [MPa]', '', {scale: 1e6})}${num('fu', 'fu [MPa]', '', {scale: 1e6})}
  </div><button class="btn small">Anlegen</button></form></div></details>
</div></details>

<details><summary>Querschnitte <span class="n">${secs.length}</span></summary><div class="body">
  <ul class="list">${secs.map(x => `<li><span class="txt">${esc(x.name)}<span class="sub">${esc(x.describe)}</span></span>${opBtn({op: 'remove_section', name: x.name}, '✕', 'btn small danger')}</li>`).join('') || '<li class="muted">keine</li>'}</ul>
  <form data-op="add_section" data-reset><input type="hidden" name="kind" value="profile" data-type="str">
    <div class="row">${sel('family', 'Profilreihe', s.families, S.profileFamily || 'IPE', 'data-action="load-profiles"')}
    <label><span>Profil</span><select name="designation" id="profile-list" data-type="str">${(S.profiles[S.profileFamily || 'IPE'] || []).map(p => `<option>${esc(p)}</option>`).join('')}</select></label>
    ${inp('name', 'Name (optional)', '')}<button class="btn small primary">+ Profil</button></div></form>
  <details><summary>Parametrisch</summary><div class="body">
    <form data-op="add_section" data-reset><input type="hidden" name="kind" value="rect" data-type="str"><div class="row">${inp('name', 'Rechteck: Name', 'Rechteck')}${num('b', 'b [mm]', 100, {scale: 1e-3})}${num('h', 'h [mm]', 200, {scale: 1e-3})}<button class="btn small">+</button></div></form>
    <form data-op="add_section" data-reset><input type="hidden" name="kind" value="circle" data-type="str"><div class="row">${inp('name', 'Rund: Name', 'Rund')}${num('d', 'd [mm]', 50, {scale: 1e-3})}<button class="btn small">+</button></div></form>
    <form data-op="add_section" data-reset><input type="hidden" name="kind" value="pipe" data-type="str"><div class="row">${inp('name', 'Rohr: Name', 'Rohr')}${num('d', 'D [mm]', 168.3, {scale: 1e-3})}${num('t', 't [mm]', 5, {scale: 1e-3})}<button class="btn small">+</button></div></form>
    <form data-op="add_section" data-reset><input type="hidden" name="kind" value="i" data-type="str"><div class="row">${inp('name', 'I-Profil: Name', 'I')}${num('h', 'h [mm]', 300, {scale: 1e-3})}${num('b', 'b [mm]', 150, {scale: 1e-3})}${num('tw', 'tw [mm]', 7.1, {scale: 1e-3})}${num('tf', 'tf [mm]', 10.7, {scale: 1e-3})}${num('r', 'r [mm]', 15, {scale: 1e-3})}<button class="btn small">+</button></div></form>
    <form data-op="add_section" data-reset><input type="hidden" name="kind" value="rhs" data-type="str"><div class="row">${inp('name', 'Hohlprofil: Name', 'RHS')}${num('h', 'h [mm]', 100, {scale: 1e-3})}${num('b', 'b [mm]', 100, {scale: 1e-3})}${num('t', 't [mm]', 5, {scale: 1e-3})}<button class="btn small">+</button></div></form>
  </div></details>
</div></details>

<details><summary>Schalendicken <span class="n">${shells.length}</span></summary><div class="body">
  <ul class="list">${shells.map(x => `<li><span class="txt">${esc(x.name)}<span class="sub">t = ${g(x.t * 1000)} mm</span></span>${opBtn({op: 'remove_shell', name: x.name}, '✕', 'btn small danger')}</li>`).join('') || '<li class="muted">keine</li>'}</ul>
  <form data-op="add_shell" data-reset><div class="row">${inp('name', 'Name (optional)', '')}${num('t', 't [mm]', 12, {scale: 1e-3})}<button class="btn small primary">+ Dicke</button></div></form>
</div></details>

<details><summary>Netz erzeugen</summary><div class="body">
  <form data-op="line_of_beams"><h3>Stabzug</h3><div class="grid3">
    ${num('p1.0', 'x1 [m]', 0)}${num('p1.1', 'y1 [m]', 0)}${num('p1.2', 'z1 [m]', 0)}
    ${num('p2.0', 'x2 [m]', 6)}${num('p2.1', 'y2 [m]', 0)}${num('p2.2', 'z2 [m]', 0)}
    ${num('n', 'Elemente', 6, {int: true, step: 1, min: 1})}${sel('mat', 'Material', matOpts(s))}${sel('sec', 'Querschnitt', secOpts(s))}
  </div><button class="btn small primary">Stabzug erzeugen</button></form>
  <form data-op="plate"><h3>Platte (Schalen, xy-Ebene)</h3><div class="grid3">
    ${num('lx', 'Lx [m]', 3)}${num('ly', 'Ly [m]', 2)}${num('origin.2', 'z [m]', 0)}
    ${num('nx', 'nx', 6, {int: true, step: 1, min: 1})}${num('ny', 'ny', 4, {int: true, step: 1, min: 1})}${sel('mat', 'Material', matOpts(s))}
    ${sel('prop', 'Dicke', shellOpts(s))}${num('origin.0', 'x0 [m]', 0)}${num('origin.1', 'y0 [m]', 0)}
  </div>${chk('quad', 'Viereckelemente (shell4)', true)}<button class="btn small primary">Platte erzeugen</button></form>
  <form data-op="box"><h3>Quader (Volumen)</h3><div class="grid3">
    ${num('lx', 'Lx [m]', 1)}${num('ly', 'Ly [m]', 0.3)}${num('lz', 'Lz [m]', 0.4)}
    ${num('nx', 'nx', 8, {int: true, step: 1, min: 1})}${num('ny', 'ny', 3, {int: true, step: 1, min: 1})}${num('nz', 'nz', 4, {int: true, step: 1, min: 1})}
    ${sel('mat', 'Material', matOpts(s))}${sel('typ', 'Elementtyp', [['hex8', 'hex8'], ['tet4', 'tet4']])}${num('origin.0', 'x0 [m]', 0)}
  </div><button class="btn small primary">Quader erzeugen</button></form>
  <div class="btns">${opBtn({op: 'merge_nodes'}, 'Doppelte Knoten zusammenführen')}${opBtn({op: 'clear_mesh'}, 'Netz löschen', 'btn small danger', 'Netz, Lager und Lasten wirklich löschen?')}</div>
</div></details>

<details><summary>Knoten <span class="n">${s.nn}</span></summary><div class="body">
  <form data-op="add_node" data-reset><div class="row">${num('x', 'x [m]', 0)}${num('y', 'y [m]', 0)}${num('z', 'z [m]', 0)}<button class="btn small primary">+ Knoten</button></div></form>
  <form data-op="move_node"><h3>Knoten verschieben</h3><div class="row">${num('node', 'Knoten', Array.from(S.sel.nodes)[0] ?? '', {int: true, step: 1})}${num('x', 'x [m]', '')}${num('y', 'y [m]', '')}${num('z', 'z [m]', '')}<button class="btn small">Verschieben</button></div></form>
  <form data-op="select_box"><h3>Auswahl per Koordinatenfenster</h3><div class="grid3">
    ${num('xmin', 'x min', '')}${num('ymin', 'y min', '')}${num('zmin', 'z min', '')}${num('xmax', 'x max', '')}${num('ymax', 'y max', '')}${num('zmax', 'z max', '')}
  </div><button class="btn small">Knoten wählen</button></form>
  <div class="btns">${opBtn({op: 'delete_nodes', nodes: selText('nodes')}, 'Gewählte Knoten löschen', 'btn small danger', 'Gewählte Knoten löschen?')}<button class="btn small" data-action="clear-sel">Auswahl aufheben</button></div>
  <div class="scroll"><table class="t"><thead><tr><th>Nr.</th><th>x</th><th>y</th><th>z</th></tr></thead><tbody>
  ${(S.geom ? S.geom.nodes.slice(0, 80) : []).map((p, i) => `<tr class="tap ${S.sel.nodes.has(i) ? 'sel' : ''}" data-action="select-node" data-node="${i}"><td>${S.sel.nodes.has(i) ? '● ' : ''}${i}</td><td>${g(p[0])}</td><td>${g(p[1])}</td><td>${g(p[2])}</td></tr>`).join('')}
  </tbody></table></div>${s.nn > 80 ? `<div class="muted">… ${s.nn - 80} weitere (Auswahl in der 3D-Ansicht)</div>` : ''}
</div></details>

<details><summary>Elemente <span class="n">${s.ne}</span></summary><div class="body">
  ${selE.length ? `<div class="msg">Gewählt: ${selE.slice(0, 20).map(e => `E${e} (${esc(S.geom.types[e])})`).join(', ')}${selE.length > 20 ? ' …' : ''}</div>` : ''}
  <form data-op="add_element" data-reset><h3>Stab zwischen zwei Knoten</h3><div class="row">${selInput('nodes', 'Knoten A, B')}${sel('typ', 'Typ', [['beam', 'Balken'], ['truss', 'Fachwerkstab']])}${sel('mat', 'Material', matOpts(s))}${sel('sec', 'Querschnitt', secOpts(s))}<button class="btn small primary">+ Stab</button></div></form>
  <form data-op="add_element" data-reset><h3>Schalenelement (3 oder 4 Knoten)</h3><div class="row">${selInput('nodes', 'Knoten')}<input type="hidden" name="typ" value="shell3" data-type="str" id="shell-typ">${sel('mat', 'Material', matOpts(s))}${sel('prop', 'Dicke', shellOpts(s))}<button class="btn small primary" data-action="add-shell">+ Schale</button></div></form>
  <form data-op="assign"><h3>Zuweisen (gewählte Elemente)</h3><div class="row">${selInput('elems')}${sel('mat', 'Material', [['', '– unverändert –']].concat(matOpts(s)))}${sel('sec', 'Querschnitt', [['', '– unverändert –']].concat(secOpts(s)))}${sel('prop', 'Dicke', [['', '– unverändert –']].concat(shellOpts(s)))}<button class="btn small">Zuweisen</button></div></form>
  <form data-op="hinges"><h3>Momentengelenke (Balken)</h3><div class="row">${selInput('elems')}${sel('mode', 'Gelenk', [[0, 'keine'], [1, 'Anfang (My, Mz)'], [2, 'Ende (My, Mz)'], [3, 'beide Enden'], [4, 'beide Enden + Torsion']], 0, 'data-type="int"')}<button class="btn small">Setzen</button></div></form>
  <div class="btns">${opBtn({op: 'delete_elements', elems: selText('elems'), with_nodes: true}, 'Gewählte Elemente löschen', 'btn small danger', 'Gewählte Elemente (und freie Knoten) löschen?')}</div>
</div></details>

<details><summary>Lager <span class="n">${s.n_supports}</span></summary><div class="body">
  <div class="muted">Knoten in der 3D-Ansicht antippen, dann Lagerart wählen.</div>
  <div class="btns">${opBtn({op: 'support', nodes: '@nodes', dofs: 'all'}, 'Einspannung', 'btn small primary')}${opBtn({op: 'support', nodes: '@nodes', dofs: 'pinned'}, 'Gelenkig (ux uy uz)', 'btn small primary')}${opBtn({op: 'support', nodes: '@nodes', dofs: 'z'}, 'nur uz', 'btn small')}${opBtn({op: 'support', nodes: '@nodes', dofs: 'xz'}, 'ux uz', 'btn small')}${opBtn({op: 'support', nodes: '@nodes', dofs: 'yz'}, 'uy uz', 'btn small')}${opBtn({op: 'remove_support', nodes: '@nodes'}, 'Lager entfernen', 'btn small danger')}</div>
  <form data-op="support"><h3>Beliebig / Feder</h3><div class="row">${selInput('nodes')}</div><div class="grid6">${['ux', 'uy', 'uz', 'rx', 'ry', 'rz'].map((d, i) => chk('d.' + i, d, i < 3)).join('')}</div>
    <div class="row">${num('stiffness', 'Federsteifigkeit [kN/m] (0 = starr)', 0, {scale: 1e3})}<button class="btn small">Lager setzen</button></div></form>
  <ul class="list">${s.supports.slice(0, 60).map(x => `<li class="tap" data-action="select-node" data-node="${x.node}"><span class="txt">Knoten ${x.node}<span class="sub">${x.dofs.map(d => ['ux', 'uy', 'uz', 'rx', 'ry', 'rz'][d]).join(' ')}${x.stiffness ? ' (Feder)' : ''}</span></span>${opBtn({op: 'remove_support', nodes: [x.node]}, '✕', 'btn small danger')}</li>`).join('')}</ul>
  ${s.n_supports > 60 ? `<div class="muted">… ${s.n_supports - 60} weitere</div>` : ''}
</div></details>

<details><summary>Stäbe für Nachweise <span class="n">${s.members.length}</span></summary><div class="body">
  <div class="btns">${opBtn({op: 'auto_members'}, 'Stäbe automatisch erkennen', 'btn small primary')}</div>
  <form data-op="set_member" data-reset><div class="row">${inp('name', 'Neuer Stab: Name', '')}${selInput('elems', 'Elemente (in Reihenfolge)')}<button class="btn small" data-action="member-from-sel">+ Stab</button></div></form>
  <ul class="list">${s.members.map(m => `<li class="tap" data-action="edit-member" data-name="${esc(m.name)}"><span class="txt">${esc(m.name)}<span class="sub">${m.n_elements} El · L = ${g(m.L, 3)} m · βy/βz = ${g(m.beta_y)}/${g(m.beta_z)}${m.detail_category ? ' · Kerbfall ' + g(m.detail_category / 1e6) : ''}${m.design ? '' : ' · ohne Nachweis'}</span></span><span class="muted">›</span></li>`).join('') || '<li class="muted">keine – „automatisch erkennen“ fasst Elemente gleicher Richtung zu Stäben zusammen</li>'}</ul>
</div></details>

<details><summary>Kontakt <span class="n">${s.contact.supports.length + s.contact.gaps.length + s.contact.pairs.length}</span></summary><div class="body">
  <form data-op="contact_support"><h3>Einseitiges Lager (nur Druck)</h3><div class="row">${selInput('nodes')}</div><div class="grid3">
    ${num('direction.0', 'Richtung x', 0)}${num('direction.1', 'y', 0)}${num('direction.2', 'z', 1)}
    ${num('gap', 'Spalt [mm]', 0, {scale: 1e-3})}${num('mu', 'Reibung μ', 0)}${num('stiffness', 'Bettung [kN/m] (0 = starr)', 0, {scale: 1e3})}
  </div><button class="btn small primary">Anlegen</button></form>
  <form data-op="gap_element"><h3>Spaltelement Knoten–Knoten</h3><div class="grid3">${num('node_a', 'Knoten A', '', {int: true, step: 1})}${num('node_b', 'Knoten B', '', {int: true, step: 1})}${num('gap', 'Spalt [mm]', 0, {scale: 1e-3})}${num('mu', 'Reibung μ', 0)}</div><button class="btn small primary">Anlegen</button></form>
  <form data-op="contact_pair"><h3>Kontaktpaar Knoten–Fläche</h3><div class="row">${inp('name', 'Name', '')}${selInput('nodes', 'Slave-Knoten (Auswahl)').replace('name="nodes"', 'name="slave_nodes"')}${inp('master_elements', 'Master-Elemente (Schalen/Volumen)', '', 'data-type="list" placeholder="z.B. 10, 11, 12"')}</div>
    <div class="grid3">${num('mu', 'Reibung μ', 0)}${num('gap', 'Spalt [mm]', 0, {scale: 1e-3})}${chk('flip_normal', 'Normale umkehren')}</div><button class="btn small primary">Anlegen</button></form>
  <ul class="list">
    ${s.contact.supports.map((c, i) => `<li><span class="txt">Einseitig: Knoten ${c.node}<span class="sub">Richtung (${c.direction.map(v => g(v, 2)).join(', ')}) · μ = ${g(c.mu)} · Spalt ${g(c.gap * 1000)} mm</span></span>${opBtn({op: 'remove_contact', kind: 'support', index: i}, '✕', 'btn small danger')}</li>`).join('')}
    ${s.contact.gaps.map((c, i) => `<li><span class="txt">Spalt: ${c.node_a} – ${c.node_b}<span class="sub">μ = ${g(c.mu)} · Spalt ${g(c.gap * 1000)} mm</span></span>${opBtn({op: 'remove_contact', kind: 'gap', index: i}, '✕', 'btn small danger')}</li>`).join('')}
    ${s.contact.pairs.map((c, i) => `<li><span class="txt">Paar ${esc(c.name)}<span class="sub">${c.slave_nodes.length} Slave-Knoten · ${c.master_elements.length} Master-Elemente · μ = ${g(c.mu)}</span></span>${opBtn({op: 'remove_contact', kind: 'pair', index: i}, '✕', 'btn small danger')}</li>`).join('')}
  </ul>
</div></details>

<details><summary>Nachweiseinstellungen</summary><div class="body"><form data-op="design_settings"><div class="grid3">
  ${num('fields.gamma_M0', 'γM0', s.design.gamma_M0)}${num('fields.gamma_M1', 'γM1', s.design.gamma_M1)}${num('fields.gamma_M2', 'γM2', s.design.gamma_M2)}
  ${sel('fields.interaction_method', 'Interaktion', [['B', 'Anhang B (Methode 2)'], ['A', 'Anhang A (Methode 1)']], s.design.interaction_method)}
  ${sel('fields.lt_method', 'Biegedrillknicken', [['general', 'allgemein 6.3.2.2'], ['rolled', 'gewalzt 6.3.2.3']], s.design.lt_method)}
  ${sel('fields.combination_rule', 'Kombinationsregel', [['6.10', 'Gl. 6.10'], ['6.10ab', 'Gl. 6.10a/b']], s.design.combination_rule)}
  ${num('fields.gamma_G_sup', 'γG,sup', s.design.gamma_G_sup)}${num('fields.gamma_G_inf', 'γG,inf', s.design.gamma_G_inf)}${num('fields.gamma_Q', 'γQ', s.design.gamma_Q)}
  ${num('fields.stations', 'Nachweisstellen je Element', s.design.stations, {int: true, step: 1, min: 2})}${num('fields.gamma_Ff', 'γFf (Ermüdung)', s.design.gamma_Ff)}
</div><button class="btn small">Speichern</button></form></div></details>`;
}

function memberForm(m) {
  const f = (k, label, o = {}) => num('fields.' + k, label, m[k] ?? '', o);
  return `<h2>Stab ${esc(m.name)}</h2><div class="muted">${m.n_elements} Elemente: ${m.elements.slice(0, 30).join(', ')}${m.elements.length > 30 ? ' …' : ''} · L = ${g(m.L, 3)} m</div>
  <form data-op="set_member" data-close><input type="hidden" name="name" value="${esc(m.name)}" data-type="str">
    <div class="grid3">${f('beta_y', 'βy (Knicklänge y)')}${f('beta_z', 'βz (Knicklänge z)')}${f('L_LT', 'L_LT [m] (leer = L)')}
    ${f('Lcr_y', 'Lcr,y [m] (optional)')}${f('Lcr_z', 'Lcr,z [m] (optional)')}${f('C1', 'C1 (leer = auto)')}
    ${f('k_z', 'kz')}${f('k_w', 'kw')}${sel('fields.load_position', 'Lastangriff', [['shear_centre', 'Schubmittelpunkt'], ['top', 'Obergurt'], ['bottom', 'Untergurt']], m.load_position)}
    ${num('fields.detail_category', 'Kerbfall Δσc [MPa]', m.detail_category ? m.detail_category / 1e6 : '', {scale: 1e6})}
    ${num('fields.detail_category_shear', 'Kerbfall Δτc [MPa]', m.detail_category_shear ? m.detail_category_shear / 1e6 : '', {scale: 1e6})}
    ${sel('fields.consequence', 'Schadensfolge', [['low', 'gering'], ['high', 'hoch']], m.consequence)}
    ${sel('fields.assessment', 'Konzept', [['damage_tolerant', 'schadenstolerant'], ['safe_life', 'Betriebsfestigkeit (safe life)']], m.assessment)}
    ${sel('fields.fatigue_points', 'Spannungspunkte', [['flanges', 'Flansche'], ['all', 'alle Punkte']], m.fatigue_points)}</div>
    <div class="grid2">${chk('fields.design', 'Nachweis führen', m.design)}${chk('fields.lt_check', 'Biegedrillknicken', m.lt_check)}${chk('fields.sway_y', 'verschieblich y', m.sway_y)}${chk('fields.sway_z', 'verschieblich z', m.sway_z)}</div>
    <div class="btns"><button class="btn primary">Speichern</button>${opBtn({op: 'remove_member', name: m.name}, 'Stab löschen', 'btn danger', 'Stab löschen?')}</div></form>`;
}

// ======================================================================
// Register: Lasten
// ======================================================================
function renderLasten() {
  const s = S.state;
  const lc = s.load_cases.find(c => c.name === s.active_case) || s.load_cases[0];
  const cat = s.categories;
  const catOpts = Object.keys(cat).map(k => [k, `${k} – ${cat[k].text} (ψ ${cat[k].psi.join('/')})`]);
  const L = lc ? lc.loads : {nodal: [], beam: [], face: [], temp: [], counts: {}};
  const kN = v => fmt(v / 1e3, 2);
  return `
<details open><summary>Lastfälle <span class="n">${s.load_cases.length}</span></summary><div class="body">
  <ul class="list">${s.load_cases.map(c => `<li class="tap ${c.name === s.active_case ? 'active' : ''}" data-action="op" data-payload="${esc(JSON.stringify({op: 'set_active_case', name: c.name}))}"><span class="txt">${c.name === s.active_case ? '● ' : ''}${esc(c.name)} <span class="chip">${esc(c.category)}</span><span class="sub">${esc(c.description || cat[c.category]?.text || '')} · ${c.n_loads} Lasten${c.exclusive_group ? ' · Gruppe ' + esc(c.exclusive_group) : ''}</span></span><button class="btn small" data-action="edit-case" data-name="${esc(c.name)}">✎</button></li>`).join('')}</ul>
  <form data-op="add_case" data-reset><div class="row">${inp('name', 'Neuer Lastfall', '', `placeholder="LF${s.load_cases.length + 1}"`)}${sel('category', 'Einwirkung', catOpts, 'Q')}${inp('description', 'Beschreibung', '')}<button class="btn small primary">+ Lastfall</button></div></form>
</div></details>

<details open><summary>Lasten im Lastfall ${esc(lc ? lc.name : '')} <span class="n">${lc ? lc.n_loads : 0}</span></summary><div class="body">
  <div class="btns">${opBtn({op: 'gravity', gz: lc && lc.gravity[2] ? 0 : -9.81}, lc && lc.gravity[2] ? 'Eigengewicht: EIN (ausschalten)' : 'Eigengewicht einschalten', lc && lc.gravity[2] ? 'btn small accent' : 'btn small')}${opBtn({op: 'clear_loads'}, 'Alle Lasten entfernen', 'btn small danger', 'Alle Lasten dieses Lastfalls entfernen?')}</div>
  <form data-op="nodal_load" data-reset><h3>Knotenlast [kN, kNm]</h3><div class="row">${selInput('nodes')}</div><div class="grid6">${['Fx', 'Fy', 'Fz', 'Mx', 'My', 'Mz'].map((k, i) => num('F.' + i, k, 0, {scale: 1e3})).join('')}</div><button class="btn small primary">Knotenlast setzen</button></form>
  <form data-op="beam_load" data-reset><h3>Streckenlast [kN/m]</h3><div class="row">${selInput('elems')}</div><div class="grid3">${num('q.0', 'qx', 0, {scale: 1e3})}${num('q.1', 'qy', 0, {scale: 1e3})}${num('q.2', 'qz', -10, {scale: 1e3})}</div>
    <details><summary>Trapezlast: Endwerte</summary><div class="body"><div class="grid3">${num('q2.0', 'qx Ende', '', {scale: 1e3})}${num('q2.1', 'qy Ende', '', {scale: 1e3})}${num('q2.2', 'qz Ende', '', {scale: 1e3})}</div></div></details>
    <div class="row">${sel('system', 'Bezug', [['global', 'global'], ['local', 'lokal (Stabachsen)']])}<button class="btn small primary">Streckenlast setzen</button></div></form>
  <form data-op="face_load" data-reset><h3>Flächenlast [kN/m²]</h3><div class="row">${selInput('elems', 'Schalen-/Volumenelemente')}${num('p', 'p (+ = in Normalenrichtung / Druck)', 5, {scale: 1e3})}${num('face', 'Fläche (Volumen 0..5)', 0, {int: true, step: 1})}<button class="btn small primary">Setzen</button></div></form>
  <form data-op="temp_load" data-reset><h3>Temperatur [K]</h3><div class="row">${selInput('elems')}${num('dT', 'ΔT gleichmäßig', 20)}${num('dT_z', 'ΔT oben–unten', 0)}<button class="btn small primary">Setzen</button></div></form>
  <h3>Vorhandene Lasten</h3>
  <ul class="list">
    ${lc && lc.gravity.some(v => v) ? `<li><span class="txt">Eigengewicht g = (${lc.gravity.map(v => g(v)).join(', ')}) m/s²</span></li>` : ''}
    ${L.nodal.map((l, i) => `<li class="tap" data-action="select-node" data-node="${l.node}"><span class="txt">Knoten ${l.node}<span class="sub">F = (${l.F.slice(0, 3).map(kN).join(', ')}) kN · M = (${l.F.slice(3).map(kN).join(', ')}) kNm</span></span>${opBtn({op: 'remove_load', kind: 'nodal', index: i}, '✕', 'btn small danger')}</li>`).join('')}
    ${L.beam.map((l, i) => `<li class="tap" data-action="select-elem" data-elem="${l.elem}"><span class="txt">Element ${l.elem}<span class="sub">q = (${l.q.map(kN).join(', ')})${l.q2 ? ' → (' + l.q2.map(kN).join(', ') + ')' : ''} kN/m ${l.system}</span></span>${opBtn({op: 'remove_load', kind: 'beam', index: i}, '✕', 'btn small danger')}</li>`).join('')}
    ${L.face.map((l, i) => `<li class="tap" data-action="select-elem" data-elem="${l.elem}"><span class="txt">Element ${l.elem}<span class="sub">p = ${kN(l.p)} kN/m² (Fläche ${l.face})</span></span>${opBtn({op: 'remove_load', kind: 'face', index: i}, '✕', 'btn small danger')}</li>`).join('')}
    ${L.temp.map((l, i) => `<li class="tap" data-action="select-elem" data-elem="${l.elem}"><span class="txt">Element ${l.elem}<span class="sub">ΔT = ${g(l.dT)} K, ΔTz = ${g(l.dT_z)} K</span></span>${opBtn({op: 'remove_load', kind: 'temp', index: i}, '✕', 'btn small danger')}</li>`).join('')}
  </ul>
  ${['nodal', 'beam', 'face', 'temp'].some(k => (L.counts[k] || 0) > L[k].length) ? '<div class="muted">Liste gekürzt (nur die ersten 300 je Art).</div>' : ''}
</div></details>

<details ${s.combinations.length ? 'open' : ''}><summary>Kombinationen <span class="n">${s.combinations.length}</span></summary><div class="body">
  <form data-op="auto_combinations"><div class="row">${sel('rule', 'Regel DIN EN 1990', [['6.10', 'Gl. 6.10'], ['6.10ab', 'Gl. 6.10a/b']], s.design.combination_rule)}<label class="w">${chk('uls', 'GZT', true)}</label><label class="w">${chk('sls', 'GZG', true)}</label><label class="w">${chk('accidental', 'außergew.', true)}</label><button class="btn small primary">Automatisch erzeugen</button></div></form>
  <form data-op="add_combination" data-reset><div class="row">${inp('name', 'Manuell: Name', '')}${sel('typ', 'Art', [['ULS', 'GZT (ULS)'], ['EQU', 'EQU'], ['ACC', 'außergewöhnlich'], ['SLS_CH', 'GZG charakteristisch'], ['SLS_FR', 'GZG häufig'], ['SLS_QP', 'GZG quasi-ständig'], ['USER', 'frei']])}${inp('factors', 'Faktoren', '', 'placeholder="LF1=1.35, LF2=1.5" data-type="str"')}<button class="btn small">+ Kombination</button></div></form>
  <div class="btns">${s.combinations.length ? opBtn({op: 'clear_combinations'}, 'Alle entfernen', 'btn small danger', 'Alle Kombinationen entfernen?') : ''}</div>
  <ul class="list">${s.combinations.slice(0, 120).map(c => `<li><span class="txt">${esc(c.name)} <span class="chip">${esc(c.typ)}</span><span class="sub">${esc(c.formula)}${c.leading ? ' · Leiteinwirkung ' + esc(c.leading) : ''}</span></span>${opBtn({op: 'remove_combination', name: c.name}, '✕', 'btn small danger')}</li>`).join('') || '<li class="muted">keine – „Automatisch erzeugen“ bildet GZT/GZG-Kombinationen aus den Lastfällen</li>'}</ul>
  ${s.combinations.length > 120 ? `<div class="muted">… ${s.combinations.length - 120} weitere</div>` : ''}
</div></details>

<details><summary>Ermüdungslasten <span class="n">${s.fatigue_loads.length}</span></summary><div class="body">
  <ul class="list">${s.fatigue_loads.map(f => `<li><span class="txt">${esc(f.name)}<span class="sub">${esc(f.case_max)} ↔ ${esc(f.case_min || 'Null')} · ${g(f.cycles)} Lastspiele · Faktor ${g(f.factor)}</span></span>${opBtn({op: 'remove_fatigue_load', name: f.name}, '✕', 'btn small danger')}</li>`).join('') || '<li class="muted">keine</li>'}</ul>
  <form data-op="add_fatigue_load" data-reset><div class="row">${inp('name', 'Name', '')}${sel('case_max', 'Lastfall max', caseOpts(s))}${sel('case_min', 'Lastfall min', caseOpts(s, [['', 'Nullzustand']]))}${num('cycles', 'Lastspiele', 2e6)}${num('factor', 'Faktor', 1)}<button class="btn small primary">+ Ermüdungslast</button></div></form>
  <div class="muted">Kerbfälle je Stab unter Modell → Stäbe.</div>
</div></details>`;
}

function caseForm(c) {
  const cat = S.state.categories;
  const catOpts = Object.keys(cat).map(k => [k, `${k} – ${cat[k].text}`]);
  return `<h2>Lastfall ${esc(c.name)}</h2><form data-op="edit_case" data-close><input type="hidden" name="name" value="${esc(c.name)}" data-type="str">
    <div class="grid2">${inp('fields.new_name', 'Name', c.name)}${sel('fields.category', 'Einwirkung', catOpts, c.category)}${inp('fields.description', 'Beschreibung', c.description)}${inp('fields.exclusive_group', 'Ausschlussgruppe', c.exclusive_group)}
    ${inp('fields.psi', 'ψ0, ψ1, ψ2 (leer = Kategorie)', c.psi ? c.psi.join(', ') : '', 'data-type="str" data-keep="1"')}${num('fields.gamma_sup', 'γ sup (leer = Kategorie)', c.gamma_sup ?? '', {})}</div>
    <div class="btns"><button class="btn primary">Speichern</button>${opBtn({op: 'copy_case', name: c.name}, 'Kopieren')}${opBtn({op: 'remove_case', name: c.name}, 'Löschen', 'btn danger', 'Lastfall löschen?')}</div></form>`;
}

// ======================================================================
// Register: Rechnen
// ======================================================================
function renderRechnen() {
  const s = S.state, st = s.settings;
  const busy = s.busy || (S.job && S.job.status === 'laeuft');
  return `
<div class="card"><form id="solve-form">
  <div class="grid2">${sel('kind', 'Analyse', [['all', 'Alle Lastfälle + Kombinationen'], ['case', 'Nur ein Lastfall'], ['modal', 'Eigenschwingungen'], ['buckling', 'Knicken (Grundzustand = Lastfall)']], S.solveKind || 'all')}
  ${sel('case', 'Lastfall (für Lastfall / Knicken)', caseOpts(s), s.active_case)}
  ${num('nmodes', 'Anzahl Eigenformen', 6, {int: true, step: 1, min: 1})}${num('workers', `Prozesse (max. ${s.cpu})`, st.workers, {int: true, step: 1, min: 1, max: 64})}</div>
  <div class="grid2">${chk('design', `Nachweise EC3 (${s.members.length} Stäbe)`, true)}${chk('fatigue', `Ermüdung (${s.fatigue_loads.length} Lasten)`, true)}</div>
  <details><summary>Rechnerfarm</summary><div class="body"><div class="grid2">${sel('backend', 'Ausführung', [['local', 'lokal (Prozess-Pool)'], ['farm', 'Rechnerfarm']], st.backend)}${inp('farm_host', 'Server', st.farm_host)}${num('farm_port', 'Port', st.farm_port, {int: true, step: 1})}${inp('farm_key', 'Schlüssel', st.farm_key)}</div>
    <div class="btns"><button type="button" class="btn small" data-action="farm-status">Farm-Status prüfen</button></div>
    <div class="muted">Server: <code>python -m statik3d.farm server --port ${st.farm_port} --key …</code>, Worker auf weiteren Rechnern: <code>python -m statik3d.farm worker --host &lt;Server&gt; --key …</code></div></div></details>
  <div class="btns" style="margin-top:8px"><button type="button" class="btn primary wide" data-action="solve" ${busy ? 'disabled' : ''}>${busy ? 'Berechnung läuft …' : '▶ Berechnen'}</button></div>
</form></div>
<div id="job-box">${jobHTML(S.job || s.job)}</div>
${s.analysis ? `<div class="card"><h3>Letzte Analyse</h3><pre>${esc(s.analysis.summary)}</pre><div class="muted">Löser ${esc(s.analysis.info.solver || '')} · ${esc(s.analysis.info.parallel || '')} · ${s.analysis.info.ndof} FHG</div></div>` : ''}
${s.single ? `<div class="card"><h3>${esc(s.single.name)}</h3><pre>${esc(s.single.summary)}</pre></div>` : ''}
<div class="muted">Parallelisierung aktuell: ${esc(s.parallel)}</div>`;
}

// ======================================================================
// Register: Ergebnisse
// ======================================================================
function renderErgebnisse() {
  const s = S.state, R = S.result;
  if (!R) return `<div class="card"><p class="muted">Noch keine Ergebnisse. Unter „Rechnen“ die Berechnung starten.</p><div class="btns"><button class="btn primary" data-action="tab" data-tab="rechnen">Zu Rechnen</button></div></div>`;
  const fields = [['umag', '|u| Verschiebung'], ['uz', 'uz'], ['ux', 'ux'], ['uy', 'uy'], ['vm', 'Vergleichsspannung σv'], ['util', 'Ausnutzung EC3'], ['util_fat', 'Ausnutzung Ermüdung'], ['util_el', 'Ausnutzung elastisch'], ['member', 'Stäbe farbig'], ['none', 'keine Färbung']];
  const diag = [['', 'kein Verlauf'], ['N', 'N'], ['Vy', 'Vy'], ['Vz', 'Vz'], ['Mt', 'Mt'], ['My', 'My'], ['Mz', 'Mz']];
  const memberOpts = [['', '– Stab wählen –']].concat(s.members.map(m => [m.name, m.name]));
  let html = `
<div class="card">
  <div class="grid2">${sel('which', 'Ergebnis', S.entries.map(e => [e.id, e.label]), S.ro.which, 'data-ro="which"')}${sel('field', 'Färbung', fields, S.ro.field, 'data-ro="field"')}
  ${R.modes ? sel('mode', 'Eigenform', R.modes.map((m, i) => [i, m]), S.ro.mode, 'data-ro="mode"') : sel('diagram', 'Schnittgrößenverlauf', diag, S.ro.diagram, 'data-ro="diagram"')}
  <label><span>Überhöhung ×${g(S.ro.scale * Math.pow(10, S.ro.factor), 3)}</span><input type="range" min="-2" max="2" step="0.1" value="${S.ro.factor}" data-ro="factor"></label></div>
  ${chk('deform', 'Verformt darstellen', S.ro.deform, 'data-ro="deform"')}
  <pre>${esc(R.summary)}</pre>
  ${R.design_summary ? `<div class="msg ${/NICHT/.test(R.design_summary) ? 'err' : 'ok'}">${esc(R.design_summary)}</div>` : ''}
  ${R.fatigue_summary ? `<div class="msg">${esc(R.fatigue_summary)}</div>` : ''}
</div>`;
  if (s.members.length) {
    html += `<details open><summary>Schnittgrößen am Stab</summary><div class="body">${sel('member', 'Stab', memberOpts, S.member, 'data-action="member-chart"')}<div id="member-chart">${S.memberData && S.member ? memberChart(S.memberData) : ''}</div></div></details>`;
  }
  if (R.beam_rows) {
    html += `<details><summary>Stabkräfte <span class="n">${R.beam_total}</span></summary><div class="body">${table(R.beam_header, R.beam_rows, {rowAttr: r => `class="tap" data-action="select-elem" data-elem="${r[0]}"`, format: (c, j) => j === 0 ? esc(c) : j === 9 ? utilBadge(c) : null})}${R.beam_total > R.beam_rows.length ? '<div class="muted">gekürzt – vollständig im Bericht</div>' : ''}</div></details>`;
  }
  if (R.env_rows) {
    html += `<details><summary>Umhüllende Extremwerte <span class="n">${R.env_total}</span></summary><div class="body">${table(R.env_header, R.env_rows, {rowAttr: r => `class="tap" data-action="select-elem" data-elem="${r[0]}"`, format: (c, j) => (j === 0 || j === 1 || j === 3 || j === 5) ? esc(c) : null})}</div></details>`;
  }
  if (R.react_rows) {
    html += `<details><summary>Auflagerkräfte <span class="n">${R.react_rows.length}</span></summary><div class="body">${table(R.react_header, R.react_rows.concat([['Σ'].concat(R.react_sum)]), {rowAttr: r => r[0] === 'Σ' ? 'style="font-weight:600"' : `class="tap" data-action="select-node" data-node="${r[0]}"`, format: (c, j) => j === 0 ? esc(c) : null})}</div></details>`;
  }
  if (R.contact_rows) {
    html += `<details><summary>Kontakt <span class="n">${R.contact_rows.length}</span></summary><div class="body">${table(R.contact_header, R.contact_rows, {format: (c, j) => j <= 2 ? esc(c) : null})}</div></details>`;
  }
  return html;
}
function memberChart(d) {
  if (!d.x || !d.x.length) return '<div class="muted">keine Stabelemente</div>';
  const W = 640, H = 200, ml = 46, mr = 12, mt = 14, mb = 26;
  const series = [['N', '#1467c6', 'N [kN]'], ['Vz', '#2e8b3a', 'Vz [kN]'], ['My', '#c62828', 'My [kNm]']];
  const parts = [];
  const xmax = d.x[d.x.length - 1] || 1;
  for (const [k, col, label] of series) {
    const raw = d[k];
    const lines = d.envelope ? [raw.min, raw.max] : [raw];
    let lo = 0, hi = 0;
    for (const arr of lines) for (const v of arr) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    const X = x => ml + (x / xmax) * (W - ml - mr), Y = v => mt + (hi - v) / (hi - lo) * (H - mt - mb);
    let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}"><text x="${ml}" y="11" font-size="11" fill="#66717c">${label}</text>`;
    svg += `<line x1="${ml}" y1="${Y(0)}" x2="${W - mr}" y2="${Y(0)}" stroke="#aab" stroke-width="1"/>`;
    for (const arr of lines) {
      const pts = arr.map((v, i) => `${X(d.x[i]).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
      svg += `<polygon points="${X(d.x[0])},${Y(0)} ${pts} ${X(d.x[d.x.length - 1])},${Y(0)}" fill="${col}" fill-opacity=".15"/><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2"/>`;
    }
    svg += `<text x="${ml - 4}" y="${Y(hi) + 4}" font-size="10" text-anchor="end" fill="#333">${fmt(hi, 1)}</text><text x="${ml - 4}" y="${Y(lo) + 4}" font-size="10" text-anchor="end" fill="#333">${fmt(lo, 1)}</text>`;
    svg += `<text x="${ml}" y="${H - 8}" font-size="10" fill="#666">x = 0</text><text x="${W - mr}" y="${H - 8}" font-size="10" text-anchor="end" fill="#666">x = ${g(xmax, 3)} m</text></svg>`;
    parts.push(svg);
  }
  let extra = '';
  if (d.design) {
    const gv = d.design.governing || {};
    extra += `<div class="msg ${d.design.util > 1 ? 'err' : 'ok'}">Nachweis: Ausnutzung ${fmt(d.design.util, 3)} – ${esc(gv.name || '')} (${esc(gv.combo || '')}, x = ${g(gv.x, 3)} m) · Klasse ${d.design.cls}</div>`;
  }
  if (d.fatigue) extra += `<div class="msg">Ermüdung: D = ${fmt(d.fatigue.util, 3)} · Δσ max = ${fmt(d.fatigue.dsig_max / 1e6, 1)} MPa</div>`;
  return parts.join('') + extra;
}
async function loadMemberChart() {
  if (!S.member || !S.ro.which) { S.memberData = null; return; }
  try { S.memberData = await API.get(`/api/member?which=${enc(S.ro.which)}&name=${enc(S.member)}`); }
  catch (e) { S.memberData = null; toast(e.message, 'err'); }
  const box = $('#member-chart'); if (box) { box.innerHTML = S.memberData ? memberChart(S.memberData) : ''; }
}

// ======================================================================
// Register: Nachweise
// ======================================================================
function renderNachweise() {
  const s = S.state, D = S.design;
  const busy = s.busy;
  let html = `<div class="card"><div class="btns"><button class="btn primary" data-action="design" ${busy || !s.has_analysis ? 'disabled' : ''}>Nachweise EC3 führen</button><button class="btn" data-action="fatigue" ${busy || !s.has_analysis ? 'disabled' : ''}>Ermüdungsnachweis</button></div>
  <div class="muted">${s.has_analysis ? `${s.members.length} Stäbe, ${s.fatigue_loads.length} Ermüdungslasten` : 'Zuerst unter „Rechnen“ berechnen (Nachweise laufen dort auf Wunsch automatisch mit).'}</div></div>`;
  if (D && D.design) {
    const d = D.design, rows = d.table.slice(1);
    html += `<div class="card"><div class="msg ${d.util_max > 1 ? 'err' : 'ok'}">${esc(d.summary)}</div>
    ${table(['Stab', 'Querschnitt', 'Kl.', 'Ausn.', 'maßgebend', 'Kombination', 'x [m]'], rows.map(r => [r[0], r[1], r[4], parseFloat(r[5]), r[6], r[7], r[8]]), {rowAttr: r => `class="tap" data-action="member-detail" data-name="${esc(r[0])}"`, format: (c, j) => j === 3 ? utilBadge(c) : j === 6 ? esc(c) : esc(c)})}
    <div class="muted">Zeile antippen: alle Zwischenwerte des Stabes.</div></div>`;
  }
  if (D && D.fatigue) {
    const f = D.fatigue, rows = f.table.slice(1);
    html += `<div class="card"><div class="msg ${rows.some(r => parseFloat(r[7]) > 1) ? 'err' : 'ok'}">${esc(f.summary)}</div>
    ${table(['Stab', 'Kerbfall', 'γMf', 'Δσ max', 'Δσ E,2', 'D', 'D Schub', 'Ausn.', 'maßgebend'], rows.map(r => [r[0], r[1], r[2], r[3], r[4], r[5], r[6], parseFloat(r[7]), r[8]]), {rowAttr: r => `class="tap" data-action="fatigue-detail" data-name="${esc(r[0])}"`, format: (c, j) => j === 7 ? utilBadge(c) : esc(c)})}</div>`;
  }
  return html;
}
function valHTML(v, depth = 0) {
  if (v === null || v === undefined) return '–';
  if (typeof v === 'number') return g(v, 4);
  if (typeof v === 'boolean') return v ? 'ja' : 'nein';
  if (typeof v !== 'object') return esc(v);
  if (Array.isArray(v)) {
    if (v.every(x => typeof x !== 'object' || x === null)) return v.map(x => valHTML(x)).join(', ');
    return v.map(x => valHTML(x, depth + 1)).join('<br>');
  }
  if (depth > 3) return esc(JSON.stringify(v));
  return `<div class="kv">${Object.entries(v).map(([k, x]) => `<b>${esc(k)}</b><span>${valHTML(x, depth + 1)}</span>`).join('')}</div>`;
}
function kvTable(obj, skip = []) {
  return `<div class="kv">${Object.entries(obj || {}).filter(([k, v]) => !skip.includes(k) && v !== null && v !== undefined).map(([k, v]) => `<b>${esc(k)}</b><span>${valHTML(v)}</span>`).join('')}</div>`;
}
function checksTable(ch) {
  if (!ch || typeof ch !== 'object' || Array.isArray(ch)) return '';
  const rows = Object.entries(ch).map(([k, v]) => Array.isArray(v) ? [k, v[0], v[1] ?? ''] : [k, v, '']);
  if (!rows.length) return '';
  return table(['Nachweis', 'Ausn.', 'Gleichung'], rows, {format: (c, j) => j === 0 ? esc(c) : j === 1 ? utilBadge(c) : `<span style="white-space:normal;font-size:12px;display:inline-block;max-width:60vw">${esc(c)}</span>`});
}
function memberDetail(name) {
  const m = S.design && S.design.design && S.design.design.members[name];
  if (!m) return;
  let html = `<h2>Stab ${esc(name)} <span class="${m.util > 1 ? 'status-bad' : 'status-ok'}">${esc(m.status)}</span></h2>
  <div class="kv"><b>Querschnitt</b><span>${esc(m.section)} (Klasse ${m.cls})</span><b>Material</b><span>${esc(m.material)}</span><b>Länge</b><span>${g(m.L, 4)} m</span><b>Ausnutzung</b><span>${utilBadge(m.util)}</span></div>
  <h3>Maßgebend</h3>${kvTable(m.governing, ['checks'])}${checksTable(m.governing && m.governing.checks)}`;
  if (m.warnings && m.warnings.length) html += `<div class="msg warn">${m.warnings.map(esc).join('<br>')}</div>`;
  if (m.section_checks && m.section_checks.length) {
    html += `<h3>Querschnittsnachweise (je Kombination)</h3>`;
    for (const c of m.section_checks.slice(0, 12)) html += `<details><summary>${esc(c.combo || c.name || '')} <span class="n">${fmt(c.util, 3)}</span></summary><div class="body">${kvTable(c, ['checks'])}${checksTable(c.checks)}</div></details>`;
  }
  if (m.stability && m.stability.length) {
    html += `<h3>Stabilität (je Kombination)</h3>`;
    for (const c of m.stability.slice(0, 12)) html += `<details><summary>${esc(c.combo || c.name || '')} <span class="n">${fmt(c.util, 3)}</span></summary><div class="body">${kvTable(c, ['checks'])}${checksTable(c.checks)}</div></details>`;
  }
  if (m.extremes && Object.keys(m.extremes).length) html += `<h3>Extremwerte</h3>${kvTable(m.extremes)}`;
  modal(html);
}
function fatigueDetail(name) {
  const m = S.design && S.design.fatigue && S.design.fatigue.members[name];
  if (!m) return;
  let html = `<h2>Ermüdung ${esc(name)}</h2>${kvTable(m, ['ranges', 'ranges_shear', 'warnings'])}`;
  if (m.ranges && m.ranges.length) html += `<h3>Schwingbreiten</h3>${table(['Δσ [MPa]', 'n', 'Last', 'x [m]'], m.ranges.slice(0, 40).map(r => [r[0] / 1e6, r[1], r[2], r[3]]), {format: (c, j) => j === 2 ? esc(c) : j === 1 ? g(c) : null})}`;
  if (m.warnings && m.warnings.length) html += `<div class="msg warn">${m.warnings.map(esc).join('<br>')}</div>`;
  modal(html);
}
async function loadDesign() {
  try { S.design = await API.get('/api/design'); } catch (e) { S.design = null; }
}

// ======================================================================
// Register: Mehr
// ======================================================================
function renderMehr() {
  const s = S.state;
  const hasRes = s.has_analysis || s.single;
  return `
<details open><summary>Datei</summary><div class="body">
  <div class="btns"><label class="btn primary">Öffnen / Importieren<input type="file" id="file-input" hidden accept=".json,.dxf,.ifc,.xlsx,.csv,.inp,.bdf,.nas,.dat,.step,.stp,.iges,.igs,.brep,.stl"></label>
  ${sel('unit', 'Längeneinheit der Datei', [['', 'automatisch / m'], ['0.001', 'mm'], ['0.01', 'cm']], '', 'id="import-unit" style="max-width:160px"')}</div>
  <div class="muted">Statik3D-JSON, DXF, IFC (InfoCAD/RFEM-Statikmodell), SAF/RFEM-xlsx, Abaqus INP, Nastran BDF, STEP/IGES/STL (gmsh).</div>
  <div class="btns"><a class="btn" href="${API.url('/api/download')}" download>Modell speichern (JSON)</a><button class="btn" data-action="check">Modell prüfen</button><button class="btn danger" data-action="new">Neues Modell</button></div>
</div></details>
<details open><summary>Bericht</summary><div class="body">
  ${hasRes ? '' : '<div class="muted">Erst berechnen, dann steht der Bericht zur Verfügung.</div>'}
  <div class="btns"><a class="btn primary" href="${API.url('/api/report?fmt=html')}" target="_blank" rel="noopener">Bericht anzeigen (HTML)</a><a class="btn" href="${API.url('/api/report?fmt=pdf&download=1')}">PDF</a><a class="btn" href="${API.url('/api/report?fmt=md&download=1')}">Markdown</a></div>
  <div class="muted">HTML: im Browser Teilen → Drucken → als PDF sichern. PDF direkt benötigt reportlab auf dem Server.</div>
</div></details>
<details open><summary>Beispiele</summary><div class="body"><div class="btns">${Object.entries(s.examples).map(([k, v]) => `<button class="btn small" data-action="example" data-name="${esc(k)}">${esc(v)}</button>`).join('')}</div></div></details>
<details><summary>Ansicht</summary><div class="body">
  ${chk('edges', 'Elementkanten zeichnen', view.opts.edges, 'data-view-opt="edges"')}${chk('loads', 'Lasten anzeigen', view.opts.loads !== false, 'data-view-opt="loads"')}${chk('labels', 'Knoten-/Elementnummern', view.opts.labels, 'data-view-opt="labels"')}
  <div class="muted">Ziehen dreht, zwei Finger zoomen und verschieben, Doppeltipp zeigt alles. Antippen wählt Knoten oder Elemente (Umschalter „Kn/El“ oben).</div>
</div></details>
<details><summary>Protokoll</summary><div class="body"><pre>${esc(s.log.join('\n'))}</pre></div></details>
<details><summary>Verbindung / Info</summary><div class="body">
  <div class="kv"><b>Server</b><span>Statik3D Web ${esc(s.server_version)}</span><b>Adresse</b><span>${esc(location.host)}</span><b>Parallel</b><span>${esc(s.parallel)}</span><b>Kerne</b><span>${s.cpu}</span></div>
  <div class="btns"><button class="btn small primary" data-action="update-check">Update suchen</button><button class="btn small" data-action="key">Zugangsschlüssel ändern</button><button class="btn small" data-action="reload">Neu laden</button></div>
  <div id="update-box"></div>
  <div class="muted">Zum Startbildschirm hinzufügen: Browser-Menü → „Zum Startbildschirm“ – dann startet Statik3D wie eine App.</div>
</div></details>`;
}

// ======================================================================
// Rendern und Ereignisse
// ======================================================================
function render() {
  const p = $('#panel');
  if (!S.state) { p.innerHTML = '<div class="muted" style="padding:20px">Verbinde …</div>'; return; }
  const open = new Set($$('details[open]', p).map(d => d.querySelector('summary')?.textContent.trim().split(' ')[0]));
  const scroll = p.scrollTop;
  const fn = {modell: renderModell, lasten: renderLasten, rechnen: renderRechnen, ergebnisse: renderErgebnisse, nachweise: renderNachweise, mehr: renderMehr}[S.tab] || renderModell;
  try { p.innerHTML = fn(); } catch (e) { p.innerHTML = `<div class="msg err">Darstellungsfehler: ${esc(e.message)}</div>`; console.error(e); }
  if (open.size) $$('details', p).forEach(d => { const k = d.querySelector('summary')?.textContent.trim().split(' ')[0]; if (open.has(k)) d.open = true; });
  $$('#tabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === S.tab));
  bindActions(p);
  p.scrollTop = scroll;
  updateSelInfo();
}

function bindActions(root) {
  $$('form[data-op]', root).forEach(f => {
    f.addEventListener('submit', async e => {
      e.preventDefault();
      const payload = Object.assign({op: f.dataset.op}, collect(f));
      if (payload.d) { payload.dofs = Object.entries(payload.d).filter(([, v]) => v).map(([k]) => parseInt(k, 10)); delete payload.d; }
      if (f.dataset.op === 'select_box') {
        try { const r = await API.post('/api/op', payload); S.sel.nodes = new Set(r.nodes); view.draw(); updateSelInfo(); toast(r.message); } catch (err) { toast(err.message, 'err'); }
        return;
      }
      const r = await runOp(payload);
      if (r && f.dataset.reset) f.reset();
      if (r && f.dataset.close) closeModal();
    });
  });
  $$('[data-action]', root).forEach(el => {
    const ev = el.tagName === 'SELECT' || el.type === 'file' ? 'change' : 'click';
    el.addEventListener(ev, e => { if (el.tagName === 'BUTTON' && el.closest('form') && el.type !== 'button' && el.dataset.action !== 'op' && !['member-from-sel', 'add-shell'].includes(el.dataset.action)) return; e.preventDefault(); e.stopPropagation(); ACTIONS[el.dataset.action]?.(el, e); });
  });
  $$('[data-ro]', root).forEach(el => {
    el.addEventListener(el.type === 'range' ? 'input' : 'change', async () => {
      const k = el.dataset.ro;
      if (k === 'deform') { S.ro.deform = el.checked; view.opts.deform = el.checked; view.draw(); return; }
      if (k === 'factor') { S.ro.factor = parseFloat(el.value); view.opts.scale = S.ro.scale * Math.pow(10, S.ro.factor); el.previousElementSibling.textContent = `Überhöhung ×${g(view.opts.scale, 3)}`; view.draw(); return; }
      if (k === 'mode') S.ro.mode = parseInt(el.value, 10); else S.ro[k] = el.value;
      if (k === 'which') { S.ro.mode = 0; }
      await loadResults();
      if (k === 'which') await loadMemberChart();
      render();
    });
  });
  $$('[data-view-opt]', root).forEach(el => el.addEventListener('change', () => { view.opts[el.dataset.viewOpt] = el.checked; view.draw(); }));
  $$('input[type=file]', root).forEach(el => el.addEventListener('change', () => importFile(el)));
}

async function importFile(el) {
  const f = el.files && el.files[0]; if (!f) return;
  const unit = $('#import-unit')?.value || '';
  toast(`Lade ${f.name} …`);
  try {
    const r = await API.req('POST', `/api/import?name=${enc(f.name)}${unit ? '&unit=' + unit : ''}`, f);
    S.state = r.state; S.version = r.state.version; updateHeader(); S.first = true; S.sel.nodes.clear(); S.sel.elems.clear();
    await refreshGeometry(); await loadResults(); render();
    toast(r.message + (r.messages && r.messages.length ? '\n' + r.messages.slice(0, 4).join('\n') : ''), 'ok');
    if (r.messages && r.messages.length > 4) modal(`<h2>Import-Protokoll</h2><pre>${esc(r.messages.join('\n'))}</pre>`);
  } catch (e) { toast(e.message, 'err'); }
  el.value = '';
}

const ACTIONS = {
  'close-modal': closeModal,
  'save-key': () => { API.save($('#key-input').value.trim()); closeModal(); refreshAll().catch(e => toast(e.message, 'err')); },
  'key': askKey,
  'reload': () => location.reload(),
  'tab': el => showTab(el.dataset.tab),
  'op': async el => {
    let payload = JSON.parse(el.dataset.payload);
    if (payload.nodes === '@nodes') { payload.nodes = selText('nodes'); if (!payload.nodes) return toast('Zuerst Knoten in der 3D-Ansicht antippen', 'err'); }
    if (payload.elems === '@elems') { payload.elems = selText('elems'); if (!payload.elems) return toast('Zuerst Elemente in der 3D-Ansicht antippen', 'err'); }
    if (el.dataset.confirm && !confirm(el.dataset.confirm)) return;
    const r = await runOp(payload);
    if (r && el.closest('#modal-body')) closeModal();
  },
  'select-node': el => { const i = parseInt(el.dataset.node, 10); if (S.sel.nodes.has(i)) S.sel.nodes.delete(i); else S.sel.nodes.add(i); view.draw(); updateSelInfo(); },
  'select-elem': el => { const i = parseInt(el.dataset.elem, 10); if (S.sel.elems.has(i)) S.sel.elems.delete(i); else S.sel.elems.add(i); view.draw(); updateSelInfo(); },
  'clear-sel': () => { S.sel.nodes.clear(); S.sel.elems.clear(); view.draw(); updateSelInfo(); },
  'example': async el => {
    try { const r = await API.post('/api/example', {name: el.dataset.name}); S.state = r.state; S.version = r.state.version; updateHeader(); S.first = true; S.sel.nodes.clear(); S.sel.elems.clear(); S.ro.which = ''; await refreshGeometry(); await loadResults(); toast(r.message, 'ok'); showTab('modell'); }
    catch (e) { toast(e.message, 'err'); }
  },
  'load-profiles': async el => {
    const fam = el.value; S.profileFamily = fam;
    if (!S.profiles[fam]) { try { S.profiles[fam] = (await API.get('/api/profiles?family=' + enc(fam))).profiles; } catch (e) { toast(e.message, 'err'); return; } }
    const list = $('#profile-list'); if (list) list.innerHTML = S.profiles[fam].map(p => `<option>${esc(p)}</option>`).join('');
  },
  'add-shell': el => { const f = el.closest('form'); const n = (f.elements.nodes.value.match(/\d+/g) || []).length; f.elements.typ.value = n === 4 ? 'shell4' : 'shell3'; f.requestSubmit(); },
  'member-from-sel': el => { const f = el.closest('form'); f.querySelector('[name=elems]').name = 'elements'; f.requestSubmit(); },
  'edit-member': el => { const m = S.state.members.find(x => x.name === el.dataset.name); if (m) modal(memberForm(m)); },
  'edit-case': el => { const c = S.state.load_cases.find(x => x.name === el.dataset.name); if (c) modal(caseForm(c)); },
  'solve': () => { const f = $('#solve-form'); const v = collect(f); S.solveKind = v.kind; startJob('/api/solve', v); },
  'design': () => startJob('/api/design', {}),
  'fatigue': () => startJob('/api/fatigue', {}),
  'farm-status': async () => {
    const f = $('#solve-form'); const v = collect(f);
    try { await API.post('/api/settings', v); const r = await API.get('/api/farm'); modal(`<h2>Rechnerfarm</h2><pre>${esc(r.describe)}\n${esc(JSON.stringify(r.status, null, 1))}</pre>`); }
    catch (e) { toast(e.message, 'err'); }
  },
  'member-chart': async el => { S.member = el.value; await loadMemberChart(); },
  'member-detail': el => memberDetail(el.dataset.name),
  'fatigue-detail': el => fatigueDetail(el.dataset.name),
  'update-check': async () => {
    const box = $('#update-box'); if (box) box.innerHTML = '<div class="muted">Frage GitHub …</div>';
    try {
      const r = await API.get('/api/update');
      const html = `<div class="msg ${r.available ? 'warn' : 'ok'}">${esc(r.message)}</div><div class="muted">${esc(r.current)}</div>` +
        (r.available ? (r.kind === 'exe'
          ? `<div class="btns"><a class="btn primary" href="${esc(r.download)}">Statik3D.exe herunterladen</a><a class="btn" href="${esc(r.releases)}" target="_blank" rel="noopener">Release ansehen</a></div><div class="muted">Oder im Programmfenster auf dem PC: Knopf „Update“ unten rechts.</div>`
          : `<div class="btns"><button class="btn primary" data-action="update-apply">Jetzt aktualisieren</button></div>`) : '');
      if (box) { box.innerHTML = html; bindActions(box); }
    } catch (e) { if (box) box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
  },
  'update-apply': async () => {
    const box = $('#update-box'); if (box) box.innerHTML = '<div class="muted">Aktualisiere …</div><div class="progress"><div></div></div>';
    try { const r = await API.post('/api/update', {}); if (box) box.innerHTML = `<div class="msg ok">${esc(r.message)}</div>`; toast(r.message, 'ok'); }
    catch (e) { if (box) box.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
  },
  'check': async () => { try { const r = await API.get('/api/check'); modal(`<h2>Modellprüfung</h2>${r.messages.length ? r.messages.map(m => `<div class="msg ${/FEHLER/.test(m) ? 'err' : 'warn'}">${esc(m)}</div>`).join('') : '<div class="msg ok">Keine Beanstandungen</div>'}`); } catch (e) { toast(e.message, 'err'); } },
  'new': async () => { if (!confirm('Neues, leeres Modell anlegen? Ungespeicherte Änderungen gehen verloren.')) return; S.sel.nodes.clear(); S.sel.elems.clear(); S.first = true; await runOp({op: 'new', name: 'Modell'}); },
};

function showTab(tab) {
  S.tab = tab;
  const sheet = $('#sheet');
  if (sheet.classList.contains('collapsed')) sheet.classList.remove('collapsed');
  if (tab === 'nachweise') loadDesign().then(render); else render();
  if (tab === 'ergebnisse' && S.member) loadMemberChart();
}

function bindShell() {
  $$('#tabs button').forEach(b => b.addEventListener('click', () => showTab(b.dataset.tab)));
  $$('#view-tools [data-view]').forEach(b => b.addEventListener('click', () => { if (b.dataset.view === 'fit') view.fit(); else view.setView(b.dataset.view); }));
  $('#btn-pick').addEventListener('click', () => { view.pickMode = view.pickMode === 'nodes' ? 'elems' : 'nodes'; $('#btn-pick').textContent = view.pickMode === 'nodes' ? 'Kn' : 'El'; $('#btn-pick').classList.toggle('on', view.pickMode === 'elems'); $('#view-hint').textContent = view.pickMode === 'nodes' ? 'Tippen: Knoten wählen · Ziehen: drehen · 2 Finger: zoom/schieben' : 'Tippen: Element wählen · Ziehen: drehen · 2 Finger: zoom/schieben'; });
  $('#btn-clear-sel').addEventListener('click', () => ACTIONS['clear-sel']());
  $('#btn-deform').addEventListener('click', () => { S.ro.deform = !S.ro.deform; view.opts.deform = S.ro.deform; $('#btn-deform').classList.toggle('on', S.ro.deform); view.draw(); });
  $('#btn-labels').addEventListener('click', () => { view.opts.labels = !view.opts.labels; $('#btn-labels').classList.toggle('on', view.opts.labels); view.draw(); });
  $('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
  // Bottom-Sheet: tippen wechselt die Groesse, ziehen stellt sie ein
  const sheet = $('#sheet'), handle = $('#sheet-handle');
  let drag = null;
  handle.addEventListener('pointerdown', e => { drag = {y: e.clientY, h: sheet.getBoundingClientRect().height, moved: false}; handle.setPointerCapture(e.pointerId); });
  handle.addEventListener('pointermove', e => { if (!drag) return; const dy = drag.y - e.clientY; if (Math.abs(dy) > 6) drag.moved = true; if (drag.moved) { sheet.classList.remove('collapsed', 'full'); sheet.style.height = Math.max(36, Math.min(window.innerHeight - 150, drag.h + dy)) + 'px'; view.resize(); } });
  handle.addEventListener('pointerup', () => { if (drag && !drag.moved) { sheet.style.height = ''; if (sheet.classList.contains('collapsed')) sheet.classList.remove('collapsed'); else if (sheet.classList.contains('full')) sheet.classList.replace('full', 'collapsed'); else sheet.classList.add('full'); setTimeout(() => view.resize(), 220); } drag = null; });
  view.onPick = () => updateSelInfo();
  new ResizeObserver(() => view.resize()).observe($('#view-wrap'));
  window.addEventListener('orientationchange', () => setTimeout(() => view.resize(), 300));
}

async function watchVersion() {
  // Aenderungen von anderer Seite (Desktop-GUI, zweites Geraet) erkennen
  try {
    const s = await API.get('/api/state');
    if (s.version !== S.version) {
      const wasBusy = S.state && S.state.busy;
      S.state = s; S.version = s.version; updateHeader();
      await refreshGeometry(); await loadResults(); render();
      if (s.busy && !wasBusy) pollJob();
    } else if (s.busy && !(S.job && S.job.status === 'laeuft')) { S.state = s; pollJob(); }
  } catch (e) { /* offline: naechster Versuch */ }
  setTimeout(watchVersion, 4000);
}

async function init() {
  API.load();
  view = new View3D($('#view'));
  bindShell();
  view.resize();
  render();
  try { await refreshAll(); }
  catch (e) { setPill('offline', 'err'); if (!/Schlüssel/.test(e.message)) toast(e.message, 'err'); }
  try { S.profiles.IPE = (await API.get('/api/profiles?family=IPE')).profiles; if (S.tab === 'modell') render(); } catch (e) { /* ohne Profilliste */ }
  setTimeout(watchVersion, 4000);
}
document.addEventListener('DOMContentLoaded', init);
