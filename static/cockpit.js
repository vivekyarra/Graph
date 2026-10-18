/* MAELIN cockpit — vanilla JS, no build step. Every number on screen comes from FalkorDB. */
(() => {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const SVGNS = 'http://www.w3.org/2000/svg';

  const state = {
    tenant: store.get('maelin.tenant') || 'alpha',
    graph: { nodes: [], edges: [] },
    scene: null,           // graph defaults (source / vulnerable / target)
    pick: null,            // operator-chosen incident
    goal: 'disruption',
    stage: 0,              // 0 ready · 1 investigated · 2 replayed · 3 reported
    run: null,             // last investigation
    previous: null,        // investigation before the latest one (memory diff)
    sim: null,
    report: null,
    verified: null,        // {session_id, action_ids} of the last contained replay
    drifted: false,
    intel: null,
    critical: null,        // choke-point cut simulation (betweenness + Cypher)
    playbooks: [],         // proven playbooks recalled from cross-session memory
    stats: null,
    preview: null,         // hover what-if overlay
    focus: [],             // brain-highlighted assets
    selected: null,
    tab: 'respond',
    busy: false,
    brain: null,
    asset: null,
  };
  window.maelin = state;
  Object.defineProperty(window, 'current', { get: () => state.run });

  /* ------------------------------------------------------------------ api */
  async function api(path, body) {
    const headers = { 'Content-Type': 'application/json' };
    const token = store.get('maelin.operatorToken');
    if (token) headers['x-maelin-operator-token'] = token;
    const res = await fetch(path, { method: body ? 'POST' : 'GET', headers, body: body ? JSON.stringify(body) : undefined });
    let data = null;
    try { data = await res.json(); } catch { /* empty body */ }
    if (!res.ok) {
      const detail = data && data.detail;
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : res.statusText;
      const err = new Error(msg || `HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return data;
  }
  const q = (path) => `${path}${path.includes('?') ? '&' : '?'}tenant=${encodeURIComponent(state.tenant)}`;

  /* --------------------------------------------------------------- toasts */
  function toast(msg, kind = 'info', ms = 4200) {
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.innerHTML = `<i></i><span>${esc(msg)}</span>`;
    $('#toasts').appendChild(el);
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, ms);
  }
  function fail(err, what) {
    if (err && err.status === 403) {
      toast(`${what}: operator token required. Press ⌘K → Set operator token.`, 'err', 6000);
    } else {
      toast(`${what}: ${err && err.message ? err.message : err}`, 'err', 6000);
    }
  }

  /* ---------------------------------------------------------- count-up */
  function countUp(el, to, ms = 900) {
    const from = Number(el.dataset.v || 0);
    el.dataset.v = to;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches || from === to) { el.textContent = to; return; }
    const t0 = performance.now();
    const tick = (t) => {
      const k = Math.min(1, (t - t0) / ms);
      const e = 1 - Math.pow(1 - k, 4);
      el.textContent = Math.round(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  function animateCounts(root) { $$('[data-count]', root).forEach((el) => countUp(el, Number(el.dataset.count))); }

  /* ------------------------------------------------------- liquid inks */
  function ink(container, inkSel, activeSel) {
    const box = $(container);
    const active = $(activeSel, box);
    const bar = $(inkSel, box);
    if (!active || !bar) return;
    bar.style.width = `${active.offsetWidth}px`;
    bar.style.transform = `translateX(${active.offsetLeft - 3}px)`;
  }
  function inks() {
    ink('#tenantSeg', '.seg-ink', 'button.on');
    ink('#tabs', '.tabs-ink', 'button.on');
    const rail = $('#rail');
    const on = $('button.on', rail);
    const bar = $('.rail-ink', rail);
    if (on && bar) { bar.style.width = `${on.offsetWidth}px`; bar.style.transform = `translateX(${on.offsetLeft - 4}px)`; }
  }
  window.addEventListener('resize', () => { inks(); renderGraph(false); });

  /* ================================================================ GRAPH */
  const GLYPH = {
    ingress: '<circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c2.5 2.6 2.5 13.4 0 16M12 4c-2.5 2.6-2.5 13.4 0 16"/>',
    service: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    identity: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.8-3.8 3.6-6 7-6s6.2 2.2 7 6"/>',
    database: '<ellipse cx="12" cy="6" rx="7" ry="2.8"/><path d="M5 6v12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8V6M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8"/>',
    business_flow: '',
  };
  const R = 21;
  let geo = { pos: {}, scale: 1 };
  let firstPaint = true;

  function el(tag, attrs = {}, parent) {
    const n = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }

  function layout() {
    const nodes = state.graph.nodes;
    const pos = {};
    nodes.forEach((n) => { pos[n.id] = { x: Number(n.x) || 0, y: Number(n.y) || 0 }; });
    const xs = nodes.map((n) => pos[n.id].x), ys = nodes.map((n) => pos[n.id].y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    // Leave room for the HUD (top) and the progress rail (bottom).
    const pad = { l: 80, r: 80, t: 70, b: 110 };
    return { pos, box: [minX - pad.l, minY - pad.t, (maxX - minX) + pad.l + pad.r, (maxY - minY) + pad.t + pad.b] };
  }

  function curve(a, b, bend = 0.1, trim = true) {
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const ux = dx / len, uy = dy / len;
    const s = trim ? R + 3 : 0, e = trim ? R + 6 : 0;
    const p1 = { x: a.x + ux * s, y: a.y + uy * s }, p2 = { x: b.x - ux * e, y: b.y - uy * e };
    const c = { x: (a.x + b.x) / 2 - uy * len * bend, y: (a.y + b.y) / 2 + ux * len * bend };
    return { d: `M${p1.x.toFixed(1)},${p1.y.toFixed(1)} Q${c.x.toFixed(1)},${c.y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`, c, mid: { x: 0.25 * a.x + 0.5 * c.x + 0.25 * b.x, y: 0.25 * a.y + 0.5 * c.y + 0.25 * b.y } };
  }

  function renderGraph(animate = true) {
    const svg = $('#graph');
    svg.innerHTML = '';
    if (!state.graph.nodes.length) return;
    const { pos, box } = layout();
    geo.pos = pos;
    svg.setAttribute('viewBox', box.join(' '));
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    const defs = el('defs', {}, svg);
    defs.innerHTML = `
      <linearGradient id="threatGrad" x1="0" x2="1"><stop offset="0" stop-color="#ff6b5b"/><stop offset="1" stop-color="#ff9a4d"/></linearGradient>
      <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 1L9 5L0 9" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.6"/></marker>`;

    const gDep = el('g', {}, svg), gPivot = el('g', {}, svg), gRoute = el('g', { id: 'routes' }, svg), gCut = el('g', { id: 'cuts' }, svg), gNode = el('g', {}, svg);
    for (const e of state.graph.edges) {
      const a = pos[e.from], b = pos[e.to];
      if (!a || !b) continue;
      const g = curve(a, b, e.kind === 'DEPENDS_ON' ? 0.0 : 0.12);
      const p = el('path', { d: g.d, class: `edge ${e.kind === 'DEPENDS_ON' ? 'dep' : 'pivot'}`, 'data-id': e.id, 'data-from': e.from, 'data-to': e.to }, e.kind === 'DEPENDS_ON' ? gDep : gPivot);
      if (e.kind !== 'DEPENDS_ON') p.setAttribute('marker-end', 'url(#arrow)');
      e._mid = g.mid;
    }
    const choke = state.intel && state.intel.chokepoints && state.intel.chokepoints[0] && state.intel.chokepoints[0].routes > 0 ? state.intel.chokepoints[0].asset_id : null;
    state.graph.nodes.forEach((n, i) => {
      const p = pos[n.id];
      const g = el('g', { class: `node ${n.kind === 'business_flow' ? 'flow' : ''} ${animate && firstPaint ? 'enter' : ''}`, 'data-id': n.id, transform: `translate(${p.x},${p.y})`, tabindex: 0, role: 'button', 'aria-label': n.id }, gNode);
      g.style.setProperty('--i', i);
      const body = el('g', { class: 'body' }, g);
      el('circle', { class: 'ring', r: R }, body);
      if (n.kind === 'business_flow') {
        el('rect', { class: 'disc', x: -26, y: -15, width: 52, height: 30, rx: 15 }, body);
        const t = el('text', { class: 'value', y: 0 }, body);
        t.textContent = `$${n.value || 0}k`;
      } else {
        el('circle', { class: 'disc', r: R }, body);
        const gl = el('g', { class: 'glyph', transform: 'translate(-9,-9) scale(.75)' }, body);
        gl.innerHTML = GLYPH[n.kind] || GLYPH.service;
      }
      const badge = el('g', { class: 'badge', transform: `translate(${R - 2},${-R + 2})` }, body);
      el('rect', { x: -15, y: -7, width: 30, height: 14, rx: 7 }, badge);
      el('text', { x: 0, y: 0 }, badge).textContent = 'CHOKE';
      if (n.id === choke) g.classList.add('choke');
      const label = el('text', { class: 'label', y: n.kind === 'business_flow' ? 31 : R + 16 }, g);
      label.textContent = n.id;
      if (n.kind !== 'business_flow') {
        const sub = el('text', { class: 'sub', y: R + 28 }, g);
        sub.textContent = n.kind;
      }
    });
    firstPaint = false;
    wireNodes();
    paint();
  }

  /* Overlay state → classes. Cheap and fully CSS-transitioned. */
  function paint() {
    const svg = $('#graph');
    if (!svg.firstChild) return;
    const pick = currentPick();
    const run = state.run;
    const routes = run ? run.paths : [];
    const prev = state.preview;
    const sim = state.stage >= 2 && state.sim ? state.sim : null;
    const blockedNodes = new Set(prev ? prev.blocked_nodes : sim ? simBlocks().nodes : []);
    const cutEdges = new Set(prev ? prev.blocked_edges : sim ? simBlocks().edges : []);
    const open = routes.filter((p) => !p.edges.some((e) => cutEdges.has(e)) && !p.nodes.some((n) => blockedNodes.has(n)));
    const onRoute = new Set(open.flatMap((p) => p.nodes));
    const hotEdges = new Set(open.flatMap((p) => p.edges));
    const impacted = new Set(prev ? prev.affected_flows : sim ? sim.affected_flows : []);
    const showFlows = prev || sim;
    const focus = new Set(state.focus);

    $$('.node', svg).forEach((g) => {
      const id = g.dataset.id;
      const isFlow = g.classList.contains('flow');
      g.classList.toggle('entry', !!pick && id === pick.source);
      g.classList.toggle('compromised', !!pick && id === pick.vulnerable);
      g.classList.toggle('target', !!pick && id === pick.target);
      g.classList.toggle('onroute', onRoute.has(id) && !(pick && [pick.source, pick.vulnerable, pick.target].includes(id)));
      g.classList.toggle('blocked', blockedNodes.has(id));
      g.classList.toggle('impacted', isFlow && impacted.has(id));
      g.classList.toggle('safe', isFlow && !!showFlows && !impacted.has(id));
      g.classList.toggle('focus', focus.has(id));
      g.classList.toggle('selected', state.selected === id);
      g.classList.toggle('dim', focus.size > 0 && !focus.has(id));
    });
    $$('.edge', svg).forEach((p) => {
      const id = p.dataset.id;
      const isDep = p.classList.contains('dep');
      p.classList.toggle('hot', !isDep && hotEdges.has(id) && !cutEdges.has(id));
      p.classList.toggle('cut', !isDep && cutEdges.has(id));
      const flowDown = isDep && impacted.has(p.dataset.from) && blockedReach(p.dataset.to, blockedNodes);
      p.classList.toggle('flowing', !!flowDown);
      p.classList.toggle('dim', focus.size > 0 && !(focus.has(p.dataset.from) || focus.has(p.dataset.to)));
    });
    drawRoutes(routes, blockedNodes, cutEdges);
    drawCuts(cutEdges);
  }

  function blockedReach(asset, blocked) {
    if (blocked.has(asset)) return true;
    // A dependency edge is "down" if its target transitively depends on a blocked asset.
    const seen = new Set([asset]);
    const stack = [asset];
    while (stack.length) {
      const a = stack.pop();
      for (const e of state.graph.edges) {
        if (e.kind === 'DEPENDS_ON' && e.from === a && !seen.has(e.to)) {
          if (blocked.has(e.to)) return true;
          seen.add(e.to); stack.push(e.to);
        }
      }
    }
    return false;
  }

  let routeKey = '';
  function drawRoutes(routes, blockedNodes, cutEdges) {
    const g = $('#routes');
    if (!g) return;
    const key = routes.map((r) => r.edges.join('>')).join('|');
    if (key !== routeKey) {
      routeKey = key;
      g.innerHTML = '';
      routes.forEach((r, i) => {
        const pts = r.nodes.map((id) => geo.pos[id]).filter(Boolean);
        if (pts.length < 2) return;
        let d = `M${pts[0].x},${pts[0].y}`;
        for (let k = 1; k < pts.length; k++) {
          const c = curve(pts[k - 1], pts[k], 0.12, false).c;
          d += ` Q${c.x.toFixed(1)},${c.y.toFixed(1)} ${pts[k].x},${pts[k].y}`;
        }
        const grp = el('g', { class: 'route-g', 'data-edges': r.edges.join(','), 'data-nodes': r.nodes.join(',') }, g);
        el('path', { id: `route-${i}`, d, class: 'route draw' }, grp);
        const sparks = el('g', { class: 'sparks' }, grp);
        for (let s = 0; s < 3; s++) {
          const c = el('circle', { r: 2.6, class: 'spark' }, sparks);
          const m = el('animateMotion', { dur: `${2.6 + i * 0.35}s`, repeatCount: 'indefinite', begin: `${-s * 0.9}s`, rotate: 'auto' }, c);
          el('mpath', { href: `#route-${i}` }, m);
        }
      });
    }
    $$('.route-g', g).forEach((grp) => {
      const edges = grp.dataset.edges.split(','), nodes = grp.dataset.nodes.split(',');
      const severed = edges.some((e) => cutEdges.has(e)) || nodes.some((n) => blockedNodes.has(n));
      $('.route', grp).classList.toggle('severed', severed);
      $('.sparks', grp).classList.toggle('severed-sparks', severed);
    });
  }

  function drawCuts(cutEdges) {
    const g = $('#cuts');
    if (!g) return;
    const key = [...cutEdges].sort().join(',');
    if (g.dataset.key === key) return;
    g.dataset.key = key;
    g.innerHTML = '';
    for (const e of state.graph.edges) {
      if (!cutEdges.has(e.id) || !e._mid) continue;
      const at = el('g', { transform: `translate(${e._mid.x},${e._mid.y})` }, g);
      const m = el('g', { class: 'cutmark' }, at);
      el('circle', { r: 8 }, m);
      el('path', { d: 'M-3,-3L3,3M3,-3L-3,3' }, m);
    }
  }

  function simBlocks() {
    if (state.sim && state.sim._blocks) return state.sim._blocks;
    const plan = chosenPlan();
    return plan ? { nodes: plan.blocked_nodes, edges: plan.blocked_edges } : { nodes: [], edges: [] };
  }

  /* -------------------------------------------------------- node hover */
  function wireNodes() {
    const tip = $('#tip');
    $$('#graph .node').forEach((g) => {
      const id = g.dataset.id;
      const n = state.graph.nodes.find((x) => x.id === id);
      g.addEventListener('mouseenter', () => {
        const rect = g.getBoundingClientRect(), host = $('#canvas').getBoundingClientRect();
        const owners = (state.owners || []).filter((o) => o.asset_id === id).map((o) => o.team_name);
        const c = state.intel && state.intel.chokepoints ? state.intel.chokepoints.find((x) => x.asset_id === id) : null;
        tip.innerHTML = `<b>${esc(id)}</b>${esc(n.kind.replace('_', ' '))}${n.kind === 'business_flow' ? ` · $${n.value}k/h at risk` : ''}${owners.length ? `<br>Owner: ${esc(owners.join(', '))}` : ''}${c ? `<br>On ${c.routes}/${c.total_routes} attack routes · betweenness ${c.betweenness}` : ''}<br><span class="faint">Click for company context</span>`;
        const x = rect.left - host.left + rect.width / 2, y = rect.top - host.top;
        tip.style.left = `${Math.max(8, Math.min(host.width - 250, x - 110))}px`;
        tip.style.top = `${Math.max(8, y - 86)}px`;
        tip.classList.add('on');
        $$('#graph .edge').forEach((p) => p.classList.toggle('near', p.dataset.from === id || p.dataset.to === id));
      });
      g.addEventListener('mouseleave', () => { tip.classList.remove('on'); $$('#graph .edge.near').forEach((p) => p.classList.remove('near')); });
      const open = () => { tip.classList.remove('on'); openAsset(id); };
      g.addEventListener('click', open);
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); } });
    });
  }

  /* ================================================================ DATA */
  function currentPick() { return state.pick || state.scene; }
  function chosenPlan() {
    const a = state.run && state.run.analysis;
    if (!a || !a.plans.length) return null;
    const idx = a.agent_choice && Number.isInteger(a.agent_choice.selected_index) ? a.agent_choice.selected_index : 0;
    return a.plans[idx] || a.recommended;
  }

  async function loadTenant(resetFlow = true) {
    state.focus = []; state.selected = null; state.preview = null;
    if (resetFlow) Object.assign(state, { run: null, previous: null, sim: null, report: null, verified: null, drifted: false, stage: 0, pick: null, brain: null, asset: null });
    routeKey = '';
    try {
      const health = await api(q('/api/health'));
      setLive(true, health.seeded ? null : 'not seeded');
      if (!health.seeded) {
        state.graph = { nodes: [], edges: [] };
        renderGraph();
        renderAll();
        toast(`Tenant "${state.tenant}" has no graph yet. Reset demo state to seed it.`, 'warn', 6000);
        return;
      }
    } catch (err) {
      setLive(false);
      fail(err, 'FalkorDB');
      renderAll();
      return;
    }
    try {
      const [graph, scene] = await Promise.all([api(q('/api/graph')), api(q('/api/scene'))]);
      state.graph = graph;
      state.scene = { source: scene.source, vulnerable: scene.vulnerable, target: scene.target, scenario: scene.scenario };
      firstPaint = true;
      renderGraph();
      renderAll();
      refreshSide();
    } catch (err) {
      fail(err, 'Loading graph');
      renderAll();
    }
  }

  async function refreshSide() {
    const tasks = [
      api(q('/api/intel')).then((d) => { state.intel = d; renderIntel(); renderGraph(false); }).catch(() => {}),
      api(q('/api/stats')).then((d) => { state.stats = d; renderLive(); renderMemory(); }).catch(() => {}),
      api(q('/api/teams')).then((d) => { state.owners = d.ownership; }).catch(() => {}),
      api(q('/api/chokepoints')).then((d) => { state.critical = d; renderIntel(); }).catch(() => {}),
      api(q('/api/playbooks')).then((d) => { state.playbooks = d.playbooks || []; renderMemory(); }).catch(() => {}),
    ];
    await Promise.all(tasks);
  }

  function setLive(ok, note) {
    const live = $('#connectivity');
    live.classList.toggle('ok', !!ok);
    live.classList.toggle('err', !ok);
    $('#liveText').textContent = ok ? (note ? `FalkorDB · ${note}` : 'FalkorDB connected') : 'FalkorDB offline';
  }
  function renderLive() {
    const s = state.stats;
    if (!s) return;
    $('#liveText').textContent = `FalkorDB · ${s.topology_nodes + s.memory_nodes} nodes · ${s.topology_edges + s.memory_edges} edges`;
  }

  function renderIntel() {
    const box = $('#intel');
    const i = state.intel;
    if (!i) { box.innerHTML = ''; return; }
    const top = (i.chokepoints || [])[0];
    const pr = (i.centrality || [])[0];
    const cut = state.critical && (state.critical.chokepoints || [])[0];
    box.innerHTML = `
      <div class="chip c-safe" title="Minimum number of pivots that separate ${esc(i.vulnerable)} from ${esc(i.target)}"><span>Min cut <b>${i.min_cut.max_flow}</b> ${i.min_cut.cut_edges.length ? `· ${esc(i.min_cut.cut_edges.join(' + '))}` : ''}</span><span class="algo">algo.maxFlow</span></div>
      ${top ? `<div class="chip c-threat" style="animation-delay:.08s" title="On ${top.routes} of ${top.total_routes} attack routes · betweenness ${top.betweenness}"><span>Chokepoint <b>${esc(top.asset_id)}</b> · ${Math.round(top.route_share * 100)}% of routes</span><span class="algo">Cypher paths</span></div>` : ''}
      ${cut ? `<div class="chip c-threat" style="animation-delay:.12s" title="Isolating ${esc(cut.service)} severs ${cut.paths_severed} of ${cut.total_paths} exploit paths to ${esc((cut.target_roles || []).join(', '))}"><span>Cut <b>${esc(cut.service)}</b> · ${Number(cut.pct_blast_radius_eliminated).toFixed(1)}% blast radius</span><span class="algo">cut sim</span></div>` : ''}
      ${pr ? `<div class="chip c-mem" style="animation-delay:.16s" title="Most depended-upon asset"><span>Most depended on <b>${esc(pr.asset_id)}</b></span><span class="algo">algo.pageRank</span></div>` : ''}`;
  }

  /* ============================================================== RESPOND */
  const ICON = {
    recon: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
    memory: '<path d="M12 3a9 9 0 1 0 9 9M12 7v5l3 2"/>',
    remediation: '<path d="M5 12l4 4 10-10"/>',
    sandbox: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/>',
    check: '<path d="M5 12l4 4 10-10"/>',
  };

  function setStage(n) {
    state.stage = n;
    $$('#rail button').forEach((b) => {
      const s = Number(b.dataset.step);
      b.classList.toggle('on', s === Math.min(n, 3));
      b.classList.toggle('done', s < n);
    });
    inks();
  }

  function swap(view, html) {
    view.innerHTML = `<div class="swap">${html}</div>`;
    animateCounts(view);
  }

  function nodeOptions(selected, role) {
    return state.graph.nodes.filter((n) => n.kind !== 'business_flow')
      .map((n) => `<option value="${esc(n.id)}" ${n.id === selected ? 'selected' : ''} style="color:#0b0c10 !important;background-color:#ffffff !important;-webkit-text-fill-color:#0b0c10 !important;font-weight:500;">${esc(n.id)}</option>`).join('')
      + (role ? '' : '');
  }

  function renderRespond() {
    const view = $('#view-respond');
    const pick = currentPick();
    if (!pick || !state.graph.nodes.length) {
      swap(view, `<div class="empty">No incident graph for <b>${esc(state.tenant)}</b>.<br><br><button class="btn btn-ghost btn-sm" data-act="reset">Seed demo graph</button></div>`);
      return;
    }
    const custom = state.pick && state.scene && (state.pick.source !== state.scene.source || state.pick.vulnerable !== state.scene.vulnerable || state.pick.target !== state.scene.target);
    const hc = state.run && state.run.hallucination_check;
    const hcLabel = !hc ? '' : hc.verified ? 'Verified by FalkorDB Graph Proof'
      : (hc.citations_checked === 0 ? 'No plan citations to verify' : 'Unverified citations detected');
    const proof = hc ? `<div class="proof rise graph-proof ${hc.verified ? 'ok' : hc.citations_checked ? 'bad' : ''}" style="--i:2" title="${esc(hc.method)}">
        <svg viewBox="0 0 24 24"><path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/></svg>
        <span>${hcLabel}</span>
        ${(hc.evidence_ids || []).map((id) => `<span class="ev mono">${esc(id)}</span>`).join('')}
        <span class="mono faint">${hc.citations_checked} citation${hc.citations_checked === 1 ? '' : 's'} checked</span>
      </div>` : '';
    const head = `
      <div class="eyebrow rise" style="--i:0">Incident<span class="line"></span>${state.drifted ? '<span class="pill warn">topology drifted</span>' : ''}</div>
      <h2 class="rise" style="--i:1">${esc(custom ? `${pick.vulnerable} compromised` : (state.scene.scenario || 'Graph incident'))}</h2>
      ${proof}
      <div class="route-pick rise" style="--i:2">
        <div class="pick"><label>Entry</label><select data-pick="source" style="color-scheme: light;">${nodeOptions(pick.source)}</select></div><span class="arrow">→</span>
        <div class="pick v"><label>Compromised</label><select data-pick="vulnerable" id="vulnerable" style="color-scheme: light;">${nodeOptions(pick.vulnerable)}</select></div><span class="arrow">→</span>
        <div class="pick t"><label>Target</label><select data-pick="target" style="color-scheme: light;">${nodeOptions(pick.target)}</select></div>
      </div>`;

    if (state.stage === 0 || !state.run) {
      swap(view, `<div class="stack">${head}
        <div class="goal rise" style="--i:3">
          <button data-goal="disruption" class="${state.goal === 'disruption' ? 'on' : ''}">Protect customers<small>least disruption + cost</small></button>
          <button data-goal="fewest" class="${state.goal === 'fewest' ? 'on' : ''}">Fewest changes<small>simplest safe cut</small></button>
        </div>
        <div class="card rise" style="--i:4">
          <div class="muted" style="font-size:12px">Three agents share state only through FalkorDB. <b style="color:var(--text)">Recon</b> enumerates every multi-hop route, <b style="color:var(--text)">Memory</b> recalls past outcomes, and <b style="color:var(--text)">Remediation</b> scores every complete cut and proves it with <span class="mono">algo.maxFlow</span>.</div>
        </div>
        <button class="btn btn-primary btn-block rise" style="--i:5" id="investigate" data-act="investigate">Investigate <span class="k">↵</span></button>
      </div>`);
      return;
    }

    const run = state.run, a = run.analysis, plan = chosenPlan(), naive = a.naive_emergency_brake;
    const trace = traceHtml(run.handoffs, false);
    if (!plan) {
      swap(view, `<div class="stack">${head}${trace}
        <div class="card"><b>No complete cut within three actions.</b><div class="muted" style="margin-top:4px">${esc(a.reason.replaceAll('_', ' '))}. Partial containment is never presented as safe.</div></div>
        <button class="btn btn-ghost btn-block" data-act="investigate">Re-investigate</button></div>`);
      return;
    }
    const mc = a.min_cut;
    const futures = `
      <div class="eyebrow rise" style="--i:4">Two futures<span class="line"></span><span id="pathsCount" class="mono" style="color:var(--threat)">${run.paths.length}</span><span>routes</span></div>
      <div class="futures rise" style="--i:5">
        <div class="future a" data-preview="naive">
          <div class="lbl">A · emergency brake</div>
          <div class="ttl">${naive ? esc(naive.actions.join(' + ')) : 'Quarantine not modeled'}</div>
          <div class="big" data-count="${naive ? naive.disruption_cost : 0}">0</div><div class="unit">$k/h customer impact</div>
          <div class="flows">${naive ? naive.affected_flows.map((f) => `<span class="pill threat">${esc(f)}</span>`).join('') : ''}</div>
        </div>
        <div class="future b" data-preview="plan">
          <div class="lbl">B · surgical cut</div>
          <div class="ttl">${esc(plan.actions.join(' + '))}</div>
          <div class="big" data-count="${plan.disruption_cost}">0</div><div class="unit">$k/h customer impact</div>
          <div class="flows">${plan.affected_flows.length ? plan.affected_flows.map((f) => `<span class="pill threat">${esc(f)}</span>`).join('') : '<span class="pill safe">all flows up</span>'}</div>
        </div>
      </div>
      ${mc ? `<div class="proof rise" style="--i:6"><svg viewBox="0 0 24 24"><path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/></svg><span>${mc.optimal ? `<b>Proven minimal.</b> ${mc.max_flow} independent pivots, ${mc.plan_edge_cuts} cuts.` : `<b>Min cut ${mc.max_flow}.</b> Plan uses ${mc.plan_edge_cuts} edge + ${mc.plan_node_cuts} node cuts.`}</span><span class="mono">algo.maxFlow</span></div>` : ''}
      ${chokeCutHtml(a)}
      ${traceDrawer(run)}
      ${memoryBanner()}`;

    if (state.stage === 1) {
      swap(view, `<div class="stack">${head}${trace}${futures}
        <div class="actions rise" style="--i:7">
          <button class="btn btn-primary" id="simulate" data-act="simulate">Replay B on a graph clone</button>
          <button class="btn btn-ghost btn-sm" data-act="cypher" title="Show the Cypher the agents ran" style="flex:0 0 auto">Cypher</button>
        </div></div>`);
      return;
    }

    const sim = state.sim;
    const contained = sim && sim.contained;
    const simHtml = sim ? `
      <div class="eyebrow rise" style="--i:4">Replay on <span class="mono" style="text-transform:none;letter-spacing:0">${esc(sim.clone_graph || 'clone')}</span><span class="line"></span><span class="pill ${contained ? 'safe' : 'threat'}">${contained ? 'contained' : 'incomplete'}</span></div>
      <div class="result rise" id="simulation" style="--i:5" data-status="${esc(sim.status)}">
        <div><div class="n ${contained ? 'safe' : 'threat'}"><span data-count="${sim.original_routes}">0</span>→<span data-count="${sim.remaining_routes}">0</span></div><div class="k">attack routes</div></div>
        <div><div class="n ${sim.affected_flows.length ? 'threat' : 'safe'}" data-count="${sim.modeled_disruption_cost}">0</div><div class="k">$k/h impact</div></div>
        <div><div class="n" style="font-size:13px;line-height:22px">deleted</div><div class="k">clone graph</div></div>
      </div>
      <div class="faint rise" style="--i:6;font-size:11px">${contained ? 'MODELED ROUTES CONTAINED' : 'ROUTES REMAIN'}: Cypher DELETE on a FalkorDB <span class="mono">GRAPH.COPY</span>, then re-traversed. Live topology untouched.</div>` : '';

    if (state.stage === 2 && sim && !contained) {
      swap(view, `<div class="stack">${head}${simHtml}
        <div class="card rise" style="--i:7;border-color:rgba(255,107,91,.3)"><b>Do not execute this plan.</b><div class="muted" style="margin-top:4px;font-size:12px">Remaining: ${sim.remaining_paths.map((p) => esc(p.nodes.join(' → '))).join('<br>')}</div></div>
        <button class="btn btn-primary btn-block rise" style="--i:8" id="newSession" data-act="investigate">Re-investigate the changed graph</button></div>`);
      return;
    }

    if (state.stage === 2) {
      const acts = plan.action_ids.map((id, i) => `<div class="li"><span class="kind">${i + 1}</span><div><div class="t">${esc(plan.actions[i])}</div><div class="s mono">${esc(id)}</div></div><button class="btn btn-threat btn-sm" data-outage="${esc(id)}">Caused outage</button></div>`).join('');
      swap(view, `<div class="stack">${head}${decisionRow(plan, naive)}${simHtml}
        <div class="eyebrow rise" style="--i:7">After execution, how did it go?<span class="line"></span></div>
        <div class="card rise" style="--i:8;padding:4px 12px"><div class="list" id="record">${acts}</div></div>
        <button class="btn btn-safe btn-block rise" style="--i:9" data-act="allsafe">Everything worked</button></div>`);
      return;
    }

    // stage 3: reported
    const r = state.report;
    swap(view, `<div class="stack">${head}${decisionRow(plan, naive)}${simHtml}
      <div class="card rise" style="--i:7;border-color:rgba(155,140,255,.3)">
        <div class="row"><span class="pill mem">saved to memory graph</span><span class="faint mono" style="margin-left:auto">${esc((r && r.postmortem_id) || '')}</span></div>
        <div class="muted" style="margin-top:8px;font-size:12px">${r && r.outcome === 'unexpected_outage' ? `<b style="color:var(--text)">${esc(r.action_id)}</b> is now an episode every agent and future session will recall. A postmortem was added to the Company Brain.` : 'The successful outcome is now shared memory for future sessions.'}</div>
      </div>
      <button class="btn btn-primary btn-block rise" style="--i:8" id="newSession" data-act="investigate">New session: re-investigate with memory</button></div>`);
  }

  function decisionRow(plan, naive) {
    return `<div class="decision rise" style="--i:3" data-preview="plan">
      <span class="pill safe">B</span><span class="d-t">${esc(plan.actions.join(' + '))}</span>
      <span class="d-n"><b>${plan.disruption_cost}</b>${naive ? `<s>${naive.disruption_cost}</s>` : ''}<small>$k/h</small></span></div>`;
  }

  function chokeCutHtml(a) {
    const cuts = (a && a.critical_chokepoints) || [];
    if (!cuts.length) return '';
    const sentence = a.chokepoint_summary || '';
    const rows = cuts.slice(0, 3).map((c) => `<div class="li">
      <span class="kind postmortem">CUT</span>
      <div><div class="t">${esc(c.service)}</div><div class="s">${c.paths_severed} of ${c.total_paths} exploit paths to ${esc((c.target_roles || []).join(', ') || 'privileged identities')}</div></div>
      <span class="meter-mini" title="${c.pct_blast_radius_eliminated}% of blast radius eliminated"><i style="width:${Math.max(2, Math.min(100, Number(c.pct_blast_radius_eliminated) || 0))}%"></i></span>
      <b class="mono" style="font-size:11px">${Number(c.pct_blast_radius_eliminated || 0).toFixed(1)}%</b></div>`).join('');
    return `<div class="eyebrow rise" style="--i:6">Choke-point cut<span class="line"></span><span class="algo">algo.betweenness + Cypher</span></div>
      ${sentence ? `<div class="verdict rise" style="--i:6">${esc(sentence)}</div>` : ''}
      <div class="card rise" style="--i:6;padding:4px 12px"><div class="list" id="chokepointCuts">${rows}</div></div>`;
  }

  function traceDrawer(run) {
    const rows = (run && run.telemetry_trace) || [];
    if (!rows.length) return '';
    const total = rows.reduce((s, r) => s + (Number(r.run_time_ms) || 0), 0);
    const body = rows.map((r, i) => `<div class="li trace-row" data-trace-row="${i}" data-graph="${esc(r.graph_name)}">
      <span class="kind ${r.query_type === 'ro_query' ? 'runbook' : 'chat'}">${r.query_type === 'ro_query' ? 'RO' : 'RW'}</span>
      <div><div class="t">${esc(r.agent_name || 'agent')} · <span class="mono">${esc(r.graph_name || '')}</span></div>
        <div class="s mono">${esc(r.evidence_id || '—')} · ${r.run_time_ms == null ? 'n/a' : Number(r.run_time_ms).toFixed(2) + ' ms via FalkorDB GraphBLAS'}</div>
        <details class="cypher-detail"><summary>query</summary><pre class="cypher">${highlightCypher(r.cypher || '')}</pre></details></div>
      <b class="mono" style="font-size:11px">${r.run_time_ms == null ? '—' : Number(r.run_time_ms).toFixed(2) + ' ms'}</b></div>`).join('');
    return `<div class="eyebrow rise" style="--i:6">FalkorDB execution trace<span class="line"></span>
        <span class="mono faint">${rows.length} queries · ${total.toFixed(2)} ms total</span>
        <button class="btn btn-ghost btn-sm" data-act="trace" style="margin-left:8px">Open drawer</button></div>
      <div class="card trace-card rise" id="traceDrawer" style="--i:6;padding:4px 12px"><div class="list">${body}</div></div>`;
  }

  function showTrace() {
    const run = state.run;
    if (!run) return toast('Investigate first.', 'warn');
    const rows = run.telemetry_trace || [];
    const blocks = rows.map((r) => `<div><div class="eyebrow">${esc(r.agent_name || 'agent')} · ${esc(r.graph_name || '')} · ${esc(r.evidence_id || '—')} · <b>${r.run_time_ms == null ? 'n/a' : Number(r.run_time_ms).toFixed(2) + ' ms'}</b> via FalkorDB GraphBLAS (${esc(r.query_type)})</div><pre class="cypher">${highlightCypher(r.cypher || '')}</pre></div>`).join('');
    modal('FalkorDB execution trace', `<div class="stack"><div class="muted" style="font-size:12px">Every row is one GraphBLAS query FalkorDB executed for this investigation. Times are server-reported <span class="mono">run_time_ms</span>, not browser wall-clock.</div>${blocks || '<div class="empty">No traced queries.</div>'}</div>`);
  }

  function memoryBanner() {
    const a = state.run && state.run.analysis;
    const ab = a && a.memory_ablation;
    if (!ab || !ab.reports_considered) return '';
    if (ab.recommendation_changed) {
      return `<div class="banner rise" id="memory" style="--i:7" data-ablation="memory_ablation">
        <div class="side old"><div class="lbl">Without memory</div><div class="v">${esc((ab.without_memory_actions || []).join(' + '))}</div></div>
        <div class="to">→</div>
        <div class="side new"><div class="lbl">With memory</div><div class="v">${esc((ab.with_memory_actions || []).join(' + '))}</div></div>
      </div><div class="faint" style="font-size:10.5px;margin-top:-6px">DECISION CHANGED by ${ab.reports_considered} recalled report${ab.reports_considered > 1 ? 's' : ''}. Operator reports are not independent forensic proof.</div>`;
    }
    return `<div class="faint" id="memory" style="font-size:11px">SAME DECISION after recalling ${ab.reports_considered} report${ab.reports_considered > 1 ? 's' : ''}.</div>`;
  }

  function traceHtml(handoffs, pending) {
    const order = ['recon', 'memory', 'remediation'];
    const label = { recon: 'Recon', memory: 'Memory', remediation: 'Remediation' };
    const rows = order.map((name, i) => {
      const h = (handoffs || []).find((x) => x.agent === name);
      const idx = (handoffs || []).indexOf(h);
      const prevIdx = i === 0 ? -1 : (handoffs || []).findIndex((x) => x.agent === order[i - 1]);
      const tools = (handoffs || []).filter((x, k) => x.agent === 'mcp' && k < idx && k > prevIdx).map((x) => x.payload.tool);
      let desc = '';
      if (h) {
        const p = h.payload;
        if (name === 'recon') desc = `${p.threat_paths} route${p.threat_paths === 1 ? '' : 's'} · ${p.business_dependencies} deps${p.chokepoints && p.chokepoints[0] ? ` · choke ${p.chokepoints[0].asset_id}` : ''}`;
        if (name === 'memory') desc = `${p.precedents} recalled · ${p.reported_failures} failure${p.reported_failures === 1 ? '' : 's'}`;
        if (name === 'remediation') desc = p.recommended ? `${p.candidate_plans} complete cuts scored` : 'no complete cut';
      }
      return `<div class="agent ${h ? 'done' : pending ? 'work' : ''} rise" style="--i:${i + 3}">
        <div class="ic"><svg viewBox="0 0 24 24">${h ? ICON.check : ICON[name]}</svg></div>
        <div class="ag-main"><span class="nm">${label[name]}</span>${h ? `<span class="ds">${esc(desc)}</span>` : '<div class="shimmer" style="width:70%"></div>'}</div>
        <div class="tm">${tools.length ? `<span class="tool" title="${esc(tools.join(', '))}">${tools.length} MCP</span>` : ''}</div></div>`;
    }).join('');
    return `<div class="trace" id="handoffSummary" title="Inspect immutable graph handoff evidence in the Memory tab">${rows}</div>`;
  }

  /* -------------------------------------------------------------- actions */
  async function investigate() {
    if (state.busy) return;
    const pick = currentPick();
    if (!pick) return;
    state.busy = true;
    setTab('respond');
    state.previous = state.run;
    state.preview = null; state.focus = [];
    const view = $('#view-respond');
    const btn = $('[data-act="investigate"]', view);
    if (btn) btn.classList.add('loading');
    // Live agent skeleton while FalkorDB + MCP work.
    swap(view, `<div class="stack"><div class="eyebrow">Agents working<span class="line"></span><span class="mono">${esc(pick.vulnerable)}</span></div>${traceHtml([], true)}</div>`);
    const fill = document.createElement('div'); fill.className = 'fill';
    $('.trace', view).prepend(fill);
    requestAnimationFrame(() => { fill.style.height = '60%'; });
    try {
      const body = { tenant: state.tenant, source: pick.source, vulnerable: pick.vulnerable, target: pick.target,
        goal: state.goal === 'fewest' ? 'Prefer the fewest independent changes while preserving customer service' : 'Minimize customer disruption and remediation cost' };
      const t0 = performance.now();
      const run = await api('/api/investigate', body);
      const elapsed = performance.now() - t0;
      if (elapsed < 900) await sleep(900 - elapsed); // let the agents be seen
      state.run = run; state.sim = null; state.report = null;
      routeKey = '';
      setStage(1);
      renderRespond();
      paint();
      renderMemory();
      refreshSide();
      const ab = run.analysis.memory_ablation;
      if (ab && ab.recommendation_changed) toast('Memory changed the decision: a past outage steered the agents to a safer plan.', 'ok', 5200);
    } catch (err) {
      fail(err, 'Investigation');
      setStage(state.run ? 1 : 0);
      renderRespond();
    } finally {
      state.busy = false;
    }
  }

  async function simulate(actionIds, sessionId, blocks) {
    const plan = chosenPlan();
    const ids = actionIds || (plan && plan.action_ids);
    if (!ids || state.busy) return;
    const cut = blocks || (plan ? { nodes: plan.blocked_nodes, edges: plan.blocked_edges } : { nodes: [], edges: [] });
    state.busy = true;
    const btn = $('#simulate') || $('[data-act="retest"]'); if (btn) btn.classList.add('loading');
    try {
      const sid = sessionId || state.run.session_id;
      const sim = await api('/api/demo/simulate', { tenant: state.tenant, session_id: sid, action_ids: ids });
      sim._blocks = cut;
      state.sim = sim;
      state.preview = null;
      if (sim.contained) state.verified = { session_id: sid, action_ids: ids, blocks: cut };
      setStage(2);
      renderRespond();
      paint();
      toast(sim.contained ? `Clone replay: ${sim.original_routes} → 0 routes. Clone deleted.` : `Clone replay: ${sim.remaining_routes} route${sim.remaining_routes === 1 ? '' : 's'} still open. The old plan no longer holds.`, sim.contained ? 'ok' : 'err', 5200);
      refreshSide();
    } catch (err) {
      fail(err, 'Replay');
      if (btn) btn.classList.remove('loading');
    } finally {
      state.busy = false;
    }
  }

  async function recordOutcome(actionId, outcome) {
    if (state.busy) return;
    state.busy = true;
    try {
      const res = await api('/api/outcome', { tenant: state.tenant, session_id: state.run.session_id, action_id: actionId, outcome, cost_observed: outcome === 'unexpected_outage' ? 100 : 0, note: 'Operator report from the MAELIN cockpit (synthetic)' });
      state.report = { ...res, action_id: actionId, outcome };
      setStage(3);
      renderRespond();
      refreshSide();
      toast(outcome === 'unexpected_outage' ? `Outage for ${actionId} stored as a memory episode + postmortem.` : 'Safe outcome stored in shared memory.', 'ok');
    } catch (err) {
      fail(err, 'Recording outcome');
    } finally {
      state.busy = false;
    }
  }

  async function allSafe() {
    const plan = chosenPlan();
    if (!plan) return;
    for (const id of plan.action_ids) {
      // eslint-disable-next-line no-await-in-loop
      await recordOutcome(id, 'safe');
    }
  }

  async function injectDrift() {
    try {
      const res = await api('/api/demo/inject-shadow-route', { tenant: state.tenant });
      state.drifted = true;
      toast(`New privilege path discovered (${res.injected_edges.join(', ')}). Old plans may no longer hold.`, 'warn', 6000);
      const verified = state.verified;
      await loadTenant(false);
      state.verified = verified;
      setTab('respond');
      if (state.run) {
        renderDrift();
      }
    } catch (err) { fail(err, 'Injecting shadow route'); }
  }

  function renderDrift() {
    const view = $('#view-respond');
    const v = state.verified;
    swap(view, `<div class="stack">
      <div class="eyebrow rise">Topology drift<span class="line"></span><span class="pill warn">shadow-role</span></div>
      <h2 class="rise" style="--i:1">The graph changed under your plan.</h2>
      <div class="muted rise" style="--i:2">Recon would now find a new pivot <span class="mono">auth-service → shadow-role → customer-db</span>. Re-test the plan you verified earlier on a fresh clone, or re-investigate.</div>
      <div class="actions rise" style="--i:3">
        ${v ? `<button class="btn btn-ghost" data-act="retest">Re-test old plan</button>` : ''}
        <button class="btn btn-primary" data-act="investigate">Re-investigate</button>
      </div></div>`);
  }

  async function resetDemoState() {
    const btn = $('#resetDemo');
    btn.classList.add('spin');
    try {
      await api('/api/demo/reset', { tenant: state.tenant });
      toast(`Tenant ${state.tenant} re-seeded in FalkorDB.`, 'ok');
      await loadTenant(true);
    } catch (err) { fail(err, 'Reset'); }
    finally { btn.classList.remove('spin'); }
  }

  /* =============================================================== MEMORY */
  function renderMemory() {
    const view = $('#view-memory');
    const s = state.stats || {};
    const run = state.run;
    const prec = run ? run.precedents : [];
    const ab = run && run.analysis.memory_ablation;
    const ledger = run ? run.handoffs : [];
    view.innerHTML = `<div class="stack">
      <div class="eyebrow rise">Shared memory graph · ${esc(state.tenant)}<span class="line"></span></div>
      <div class="stats rise" style="--i:1">
        <div class="stat"><div class="n" data-count="${s.sessions || 0}">0</div><div class="k">sessions</div></div>
        <div class="stat"><div class="n" data-count="${s.episodes || 0}">0</div><div class="k">episodes</div></div>
        <div class="stat"><div class="n" data-count="${s.memory_nodes || 0}">0</div><div class="k">memory nodes</div></div>
      </div>
      <div class="eyebrow rise" style="--i:2">Proven playbooks<span class="line"></span><span class="mono">cross-session recall</span></div>
      ${(state.playbooks || []).length ? `<div class="card rise" style="--i:3;padding:4px 12px"><div class="list">${state.playbooks.map((p) => `
        <div class="li"><span class="kind runbook">PB</span><div><div class="t">${esc(p.playbook_id)}</div>
          <div class="s">used ${p.times_used}× · avg MTTR ${p.avg_mttr_seconds == null ? 'n/a' : Math.round(p.avg_mttr_seconds) + 's'} · ${esc((p.last_used_at || '').slice(0, 19))}</div></div>
          <span class="pill mem">proven</span></div>`).join('')}</div></div>`
        : `<div class="empty rise" style="--i:3">No playbook has resolved a matching incident yet.<br><span style="font-size:11px">Record an outcome, then open a new session to see recall accelerate.</span></div>`}
      <div class="eyebrow rise" style="--i:2">Recalled for this incident<span class="line"></span></div>
      ${prec.length ? `<div class="card rise" style="--i:3;padding:4px 12px"><div class="list">${prec.slice(0, 5).map((p) => `
        <div class="li"><span class="kind ${p.outcome === 'unexpected_outage' ? 'postmortem' : 'runbook'}">${p.match_type === 'exact' ? 'EX' : p.match_type === 'vector' ? 'VEC' : 'SEM'}</span>
        <div><div class="t">${esc(p.action_id)}</div><div class="s">${esc(p.outcome.replace('_', ' '))} · ${p.match_type}${p.similarity ? ` · sim ${p.similarity}` : ''}</div></div>
        <div class="bar-meter" title="memory weight ${p.memory_weight}"><i style="width:${Math.round(100 * p.memory_weight)}%"></i></div></div>`).join('')}</div></div>`
        : `<div class="empty rise" style="--i:3">${run ? 'No past outcome matches this incident yet.' : 'Investigate to recall memory.'}<br><span style="font-size:11px">Exact fingerprint · semantic pattern · vector index similarity</span></div>`}
      ${ab ? `<div class="eyebrow rise" style="--i:4">Causal ablation<span class="line"></span></div>
      <div class="card rise" style="--i:5;font-size:12px">
        <div class="abl"><span class="faint">Without memory</span><span class="mono">${esc((ab.without_memory_actions || ['none']).join(' + '))}</span><b>${ab.without_memory_score ?? '-'}</b></div>
        <div class="abl"><span class="faint">With memory</span><span class="mono" style="color:#ddd8ff">${esc((ab.with_memory_actions || ['none']).join(' + '))}</span><b>${ab.with_memory_score ?? '-'}</b></div>
        <div class="faint" style="font-size:10.5px;margin-top:8px">Same topology, same candidates, memory removed. Operator reports are not independent forensic proof.</div>
      </div>` : ''}
      <div class="eyebrow rise" style="--i:6">Handoff ledger<span class="line"></span><span class="mono">${ledger.length} nodes</span></div>
      ${ledger.length ? `<div class="card rise" style="--i:7;padding:4px 12px"><div class="list">${groupLedger(ledger).map((g) => `
        <div class="li"><span class="kind chat">${esc(g.agent.slice(0, 3))}</span><div><div class="t">${esc(g.agent)} · ${esc(g.status)}</div>${g.tools.length ? `<div class="tools">${g.tools.map((x, k) => `<span class="tool" style="--i:${k}">${esc(x)}</span>`).join('')}</div>` : ''}</div><span></span></div>`).join('')}</div></div>
        <div class="faint" style="font-size:10.5px">Immutable <span class="mono">(:Session)-[:HAS_HANDOFF]->(:Handoff)</span> nodes. Inspect immutable graph handoff evidence: agents read each other's work only from here.</div>`
        : '<div class="empty rise" style="--i:7">No session yet.</div>'}
    </div>`;
    animateCounts(view);
  }

  function groupLedger(ledger) {
    const out = [];
    let tools = [];
    for (const h of ledger) {
      if (h.agent === 'mcp') { tools.push(h.payload.tool); continue; }
      out.push({ agent: h.agent, status: h.status, created: h.created, tools });
      tools = [];
    }
    if (tools.length) out.push({ agent: 'mcp', status: 'tool_called', created: ledger[ledger.length - 1].created, tools });
    return out;
  }

  /* ================================================================ BRAIN */
  const SUGGEST = ['Is it safe to quarantine auth-service?', 'Who owns customer-db?', 'Why does vault-sync keep a database credential?'];
  function initials(name) { return name.split(/\s+/).map((x) => x[0]).join('').slice(0, 2).toUpperCase(); }
  function hue(s) { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }

  function renderBrain() {
    const view = $('#view-brain');
    const b = state.brain, a = state.asset;
    view.innerHTML = `<div class="stack">
      <div class="eyebrow rise">Company brain<span class="line"></span><span class="mono">full-text + traversal</span></div>
      <form class="ask rise" style="--i:1" id="askForm"><input id="askInput" placeholder="Ask how the company works…" value="${esc(b ? b.question : '')}" maxlength="300" autocomplete="off"><button type="submit" aria-label="Ask"><svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button></form>
      ${b ? '' : `<div class="suggest rise" style="--i:2">${SUGGEST.map((s) => `<button data-ask="${esc(s)}">${esc(s)}</button>`).join('')}</div>`}
      <div id="answerBox">${b ? answerHtml(b) : ''}</div>
      <div id="assetBox">${a ? assetHtml(a) : (b ? '' : '<div class="empty rise" style="--i:3">Click any node in the graph to see who owns it, who is on call, and every document and decision about it.</div>')}</div>
    </div>`;
  }

  function answerHtml(b) {
    return `<div class="card rise" style="--i:2">
      <div class="answer" id="answerText">${esc(b.answer)}</div>
      <div class="list" style="margin-top:10px">${b.sources.slice(0, 6).map((s) => `
        <div class="li"><span class="kind ${esc(s.kind || s.type)}">${esc((s.kind || s.type).slice(0, 3))}</span><div><div class="t">${esc(s.title)}</div><div class="s mono">${esc(s.id)}</div></div>${s.score ? `<span class="faint mono">${s.score}</span>` : '<span></span>'}</div>`).join('')}</div>
    </div>`;
  }

  function assetHtml(a) {
    const people = a.owners.flatMap((o) => o.people.map((p) => ({ ...p, team: o.team })));
    return `<div class="stack" style="margin-top:4px">
      <div class="eyebrow rise">${esc(a.asset_id)}<span class="line"></span><span class="mono">${esc(a.role || a.kind)}</span></div>
      <div class="card rise" style="--i:1">
        <div class="row between"><b>${esc(a.owners.map((o) => o.team).join(', ') || 'Unowned')}</b>${a.blast_radius.length ? `<span class="pill threat">${a.blast_radius.length} flow${a.blast_radius.length > 1 ? 's' : ''} depend</span>` : '<span class="pill safe">no customer flows</span>'}</div>
        <div class="people" style="margin-top:10px">${people.map((p) => `<div class="person"><span class="avatar" style="background:hsl(${hue(p.name)} 70% 72%)">${esc(initials(p.name))}</span><div><div>${esc(p.name)}</div><div class="faint" style="font-size:11px">${esc(p.title)}</div></div>${p.on_call ? '<span class="oncall">on call</span>' : ''}</div>`).join('') || '<span class="faint">No people linked.</span>'}</div>
      </div>
      ${a.documents.length || a.decisions.length ? `<div class="card rise" style="--i:2;padding:4px 12px"><div class="list">
        ${a.decisions.map((d) => `<div class="li"><span class="kind decision">dec</span><div><div class="t">${esc(d.title)}</div><div class="s">${esc(d.decided_by)} · source ${esc(d.source_id)}</div></div><span></span></div>`).join('')}
        ${a.documents.slice(0, 5).map((d) => `<div class="li"><span class="kind ${esc(d.kind)}">${esc(d.kind.slice(0, 3))}</span><div><div class="t">${esc(d.title)}</div><div class="s">${esc(d.author || (d.origin === 'operator_report' ? 'operator report' : ''))} · ${esc(d.created)}</div></div>${d.origin === 'operator_report' ? '<span class="pill mem">new</span>' : '<span></span>'}</div>`).join('')}
      </div></div>` : ''}
      ${a.kind !== 'business_flow' ? `<button class="btn btn-ghost btn-block rise" style="--i:3" data-compromise="${esc(a.asset_id)}">Investigate ${esc(a.asset_id)} as compromised</button>` : ''}
    </div>`;
  }

  async function ask(question) {
    question = (question || '').trim();
    if (question.length < 2) return;
    setTab('brain');
    const box = $('#answerBox');
    if (box) box.innerHTML = '<div class="card"><div class="shimmer" style="width:90%"></div><div class="shimmer" style="width:75%"></div><div class="shimmer" style="width:60%"></div></div>';
    try {
      const b = await api('/api/brain/ask', { tenant: state.tenant, question });
      state.brain = b; state.asset = null;
      state.focus = b.focus_assets || [];
      renderBrain();
      paint();
      typeOut($('#answerText'), b.answer);
    } catch (err) {
      fail(err, 'Company brain');
      renderBrain();
    }
  }

  function typeOut(node, text) {
    if (!node || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const words = text.split(' ');
    let i = 0;
    node.innerHTML = '<span class="cursor"></span>';
    const step = () => {
      i = Math.min(words.length, i + 3);
      node.innerHTML = `${esc(words.slice(0, i).join(' '))}${i < words.length ? '<span class="cursor"></span>' : ''}`;
      if (i < words.length) setTimeout(step, 24);
    };
    step();
  }

  async function openAsset(id) {
    state.selected = id;
    state.focus = [id];
    paint();
    setTab('brain');
    try {
      state.asset = await api(q(`/api/brain/asset/${encodeURIComponent(id)}`));
      state.brain = null;
      renderBrain();
    } catch (err) { fail(err, 'Asset context'); }
  }

  /* ================================================================= TABS */
  const TABS = ['respond', 'memory', 'brain'];
  function setTab(tab) {
    if (state.tab === tab) return;
    const from = TABS.indexOf(state.tab), to = TABS.indexOf(tab);
    state.tab = tab;
    $$('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === tab));
    TABS.forEach((t, i) => {
      const v = $(`#view-${t}`);
      v.classList.toggle('on', t === tab);
      v.classList.toggle('left', i < to);
    });
    if (tab !== 'brain' && state.focus.length && !state.selected) { state.focus = []; paint(); }
    if (tab === 'respond' && state.selected) { state.selected = null; state.focus = []; paint(); }
    void from;
    inks();
  }

  function renderAll() {
    setStage(state.stage);
    renderRespond();
    renderMemory();
    renderBrain();
    renderIntel();
  }

  /* ======================================================= PALETTE/MODAL */
  const COMMANDS = () => [
    { t: 'Investigate current incident', g: '⚡', h: '↵', run: investigate },
    { t: 'Replay recommended plan on a graph clone', g: '⧉', run: () => state.run ? simulate() : toast('Investigate first.', 'warn') },
    { t: 'Inject shadow route (topology drift)', g: '⚠', run: injectDrift },
    { t: 'Reset demo state', g: '↺', run: resetDemoState },
    { t: `Switch to tenant ${state.tenant === 'alpha' ? 'beta' : 'alpha'}`, g: '⇄', run: () => switchTenant(state.tenant === 'alpha' ? 'beta' : 'alpha') },
    { t: 'Show agent Cypher queries', g: '{}', run: showCypher },
    { t: 'Import a graph scenario (JSON)', g: '⇪', run: showImport },
    { t: 'Set operator token', g: '⚿', run: showToken },
    { t: 'Open Memory', g: 'M', run: () => setTab('memory') },
    { t: 'Open Company Brain', g: 'B', run: () => { setTab('brain'); setTimeout(() => $('#askInput') && $('#askInput').focus(), 300); } },
  ];
  let palIndex = 0, palItems = [];
  function openPalette() {
    const pal = $('#palette');
    pal.hidden = false;
    const input = $('#paletteInput');
    input.value = '';
    filterPalette('');
    setTimeout(() => input.focus(), 20);
  }
  function closePalette() { $('#palette').hidden = true; }
  function filterPalette(text) {
    const t = text.trim().toLowerCase();
    palItems = COMMANDS().filter((c) => !t || c.t.toLowerCase().includes(t));
    if (t.length > 2) palItems.push({ t: `Ask the brain: “${text.trim()}”`, g: '?', run: () => ask(text.trim()) });
    palIndex = 0;
    drawPalette();
  }
  function drawPalette() {
    $('#paletteList').innerHTML = palItems.map((c, i) => `<li class="${i === palIndex ? 'on' : ''}" data-i="${i}" role="option"><span class="gl">${esc(c.g)}</span>${esc(c.t)}${c.h ? `<span class="hint">${esc(c.h)}</span>` : ''}</li>`).join('');
  }
  function runPalette(i) { const c = palItems[i]; closePalette(); if (c) c.run(); }

  function modal(title, html) {
    $('#modalTitle').textContent = title;
    $('#modalBody').innerHTML = html;
    $('#modal').hidden = false;
  }
  function closeModal() { $('#modal').hidden = true; }

  function highlightCypher(src) {
    return esc(src)
      .replace(/\b(MATCH|WITH|WHERE|RETURN|LIMIT|ANY|IN|CALL|YIELD|ORDER BY|DESC|MERGE|CREATE|DELETE|DETACH|SET|OPTIONAL|UNWIND|AS|ON CREATE)\b/g, '<span class="kw">$1</span>')
      .replace(/\b(nodes|relationships|algo\.\w+|db\.idx\.\w+\.\w+|vecf32|collect|count)\b/g, '<span class="fn">$1</span>')
      .replace(/(\$\w+)/g, '<span class="pm">$1</span>')
      .replace(/(:[A-Z_]+)/g, '<span class="lb">$1</span>');
  }
  function showCypher() {
    const recon = state.run && state.run.handoffs.find((h) => h.agent === 'recon');
    const q1 = recon ? recon.payload.cypher_query.replace(/ -- vulnerable:.*$/, '') : "MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target}) WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable) RETURN nodes(p), relationships(p) LIMIT 257";
    const blocks = [
      ['Recon · every multi-hop route through the compromised asset', q1.replace(/ (WITH|RETURN|LIMIT) /g, '\n$1 ')],
      ['Remediation · proven minimum cut', "MATCH (s:Asset {id:$vulnerable}), (t:Asset {id:$target})\nCALL algo.maxFlow({sourceNodes:[s], targetNodes:[t],\n  capacityProperty:'cap', relationshipTypes:['CAN_PIVOT']})\nYIELD edges, edgeFlows, maxFlow"],
      ['Recon · attack chokepoints', "CALL algo.betweenness({nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT']})\nYIELD node, score RETURN node.id, score ORDER BY score DESC"],
      ['Remediation · choke-point cut simulation', "MATCH p = (ing:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(svc:Asset {kind:'service'})\n  -[:CAN_PIVOT]->(iam:Asset {kind:'identity'})\nWITH collect(p) AS all_paths, count(DISTINCT p) AS total_paths\nUNWIND all_paths AS p UNWIND nodes(p) AS n\nWITH n, count(DISTINCT p) AS paths_severed, total_paths\nRETURN n.id AS chokepoint_service, paths_severed, total_paths,\n  (toFloat(paths_severed) / toFloat(total_paths)) * 100.0 AS pct_blast_radius_eliminated"],
      ['Memory · proven playbooks across sessions', "MATCH (s:Session)-[:RECORDED]->(ep:Episode)-[r:RESOLVED_BY]->(pb:Playbook)\nWHERE ep.cve_id = $cve_id OR ep.service_tier = $service_tier\nRETURN pb.action_id, count(ep) AS times_used,\n  avg(r.mttr_seconds) AS avg_mttr_seconds\nORDER BY times_used DESC, avg_mttr_seconds ASC LIMIT 3"],
      ['Memory · similar past incidents', "CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($vec))\nYIELD node, score\nMATCH (node)-[:OBSERVED]->(a:ActionExperience)\nRETURN a.action_id, a.outcome, score"],
      ['Replay · on a disposable GRAPH.COPY clone', "MATCH ()-[r:CAN_PIVOT {edge_id:$edge_id}]->() DELETE r\nMATCH (n:Asset {id:$node_id}) DETACH DELETE n"],
    ];
    modal('Cypher the agents ran', `<div class="stack">${blocks.map(([t, c]) => `<div><div class="eyebrow">${esc(t)}</div><pre class="cypher">${highlightCypher(c)}</pre></div>`).join('')}</div>`);
  }
  function showToken() {
    modal('Operator token', `<div class="stack"><div class="muted">Remote deployments protect graph reads and writes with <span class="mono">MAELIN_OPERATOR_TOKEN</span>. It is kept in this browser only.</div>
      <input type="password" id="operatorToken" placeholder="Paste operator token" value="${esc(store.get('maelin.operatorToken') || '')}">
      <div class="actions"><button class="btn btn-ghost" data-token="clear">Clear</button><button class="btn btn-primary" data-token="save">Save</button></div></div>`);
    setTimeout(() => $('#operatorToken').focus(), 30);
  }
  function showImport() {
    modal('Import a graph scenario', `<div class="stack"><div class="muted">Creates a new isolated tenant in FalkorDB from synthetic JSON (assets, pivot_edges, depends_edges, actions, optional teams/people/documents/decisions). Existing tenants are never overwritten.</div>
      <input type="text" id="newTenant" placeholder="new tenant id, e.g. payments_lab" maxlength="32">
      <textarea id="scenarioJson" placeholder='{"scenario": "...", "assets": [...]}'></textarea>
      <div class="row"><button class="btn btn-ghost btn-sm" data-import="sample">Load demo JSON</button><span id="importStatus" class="faint" style="margin-left:auto"></span><button class="btn btn-primary" id="uploadScenario" data-import="go">Import</button></div></div>`);
  }
  async function doImport() {
    const tenant = $('#newTenant').value.trim();
    let dataset;
    try { dataset = JSON.parse($('#scenarioJson').value); } catch { $('#importStatus').textContent = 'Invalid JSON'; return; }
    try {
      const res = await api('/api/scenarios', { tenant, dataset });
      $('#importStatus').textContent = `Imported ${res.nodes} nodes`;
      addTenant(tenant);
      closeModal();
      switchTenant(tenant);
    } catch (err) { $('#importStatus').textContent = err.message; }
  }

  function addTenant(t) {
    const seg = $('#tenantSeg');
    if ($(`button[data-tenant="${CSS.escape(t)}"]`, seg)) return;
    const b = document.createElement('button');
    b.setAttribute('role', 'tab'); b.dataset.tenant = t; b.textContent = t;
    seg.appendChild(b);
  }
  function switchTenant(t) {
    if (!t) return;
    addTenant(t);
    state.tenant = t;
    store.set('maelin.tenant', t);
    $$('#tenantSeg button').forEach((b) => b.classList.toggle('on', b.dataset.tenant === t));
    inks();
    loadTenant(true);
  }

  /* ================================================================ WIRE */
  document.addEventListener('click', (ev) => {
    const t = ev.target.closest('button, li, [data-preview]');
    if (!t) return;
    if (t.closest('#tenantSeg') && t.dataset.tenant) return switchTenant(t.dataset.tenant);
    if (t.closest('#tabs') && t.dataset.tab) return setTab(t.dataset.tab);
    if (t.id === 'openPalette') return openPalette();
    if (t.id === 'resetDemo') return resetDemoState();
    if (t.matches('#paletteList li')) return runPalette(Number(t.dataset.i));
    if (t.matches('[data-close]')) return closeModal();
    const act = t.dataset.act;
    if (act === 'investigate') return investigate();
    if (act === 'simulate') return simulate();
    if (act === 'allsafe') return allSafe();
    if (act === 'cypher') return showCypher();
    if (act === 'trace') return showTrace();
    if (act === 'reset') return resetDemoState();
    if (act === 'retest' && state.verified) return simulate(state.verified.action_ids, state.verified.session_id, state.verified.blocks);
    if (t.dataset.outage) return recordOutcome(t.dataset.outage, 'unexpected_outage');
    if (t.dataset.goal) { state.goal = t.dataset.goal; $$('.goal button').forEach((b) => b.classList.toggle('on', b.dataset.goal === state.goal)); return; }
    if (t.dataset.ask) return ask(t.dataset.ask);
    if (t.dataset.compromise) {
      const base = currentPick();
      state.pick = { ...base, vulnerable: t.dataset.compromise, source: base.source === t.dataset.compromise ? state.scene.source : base.source };
      state.selected = null; state.focus = [];
      setStage(0); setTab('respond'); renderRespond(); paint();
      return;
    }
    if (t.dataset.token === 'save') { store.set('maelin.operatorToken', $('#operatorToken').value.trim() || null); closeModal(); toast('Operator token saved in this browser.', 'ok'); return loadTenant(false); }
    if (t.dataset.token === 'clear') { store.set('maelin.operatorToken', null); closeModal(); toast('Operator token cleared.'); return; }
    if (t.dataset.import === 'sample') { $('#scenarioJson').value = JSON.stringify(SAMPLE(), null, 2); return; }
    if (t.dataset.import === 'go') return doImport();
  });

  // What-if previews: hover a future to see it on the graph.
  document.addEventListener('mouseover', (ev) => {
    const f = ev.target.closest('[data-preview]');
    if (!f || !state.run) return;
    const plan = f.dataset.preview === 'naive' ? state.run.analysis.naive_emergency_brake : chosenPlan();
    if (plan && state.preview !== plan) { state.preview = plan; paint(); }
  });
  document.addEventListener('mouseout', (ev) => {
    const f = ev.target.closest('[data-preview]');
    if (!f || (ev.relatedTarget && f.contains(ev.relatedTarget))) return;
    if (state.preview) { state.preview = null; paint(); }
  });

  document.addEventListener('change', (ev) => {
    const s = ev.target.closest('select[data-pick]');
    if (!s) return;
    const base = currentPick();
    state.pick = { ...base, [s.dataset.pick]: s.value };
    state.run = null; state.sim = null; state.report = null; routeKey = '';
    setStage(0); renderRespond(); paint();
  });

  document.addEventListener('submit', (ev) => {
    if (ev.target.id === 'askForm') { ev.preventDefault(); ask($('#askInput').value); }
  });

  $('#paletteInput').addEventListener('input', (ev) => filterPalette(ev.target.value));
  $('#paletteInput').addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown') { palIndex = Math.min(palItems.length - 1, palIndex + 1); drawPalette(); ev.preventDefault(); }
    if (ev.key === 'ArrowUp') { palIndex = Math.max(0, palIndex - 1); drawPalette(); ev.preventDefault(); }
    if (ev.key === 'Enter') { runPalette(palIndex); ev.preventDefault(); }
  });
  $('#palette').addEventListener('mousedown', (ev) => { if (ev.target.id === 'palette') closePalette(); });
  $('#modal').addEventListener('mousedown', (ev) => { if (ev.target.id === 'modal') closeModal(); });

  document.addEventListener('keydown', (ev) => {
    const typing = ev.target.matches('input, textarea, select');
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'k') { ev.preventDefault(); $('#palette').hidden ? openPalette() : closePalette(); return; }
    if (ev.key === 'Escape') { closePalette(); closeModal(); if (state.focus.length) { state.focus = []; state.selected = null; paint(); } return; }
    if (typing || !$('#palette').hidden || !$('#modal').hidden) return;
    if (ev.key === 'Enter' && state.tab === 'respond' && state.stage === 0) { ev.preventDefault(); investigate(); }
    if (ev.key === '/') { ev.preventDefault(); setTab('brain'); setTimeout(() => $('#askInput') && $('#askInput').focus(), 250); }
    if (['1', '2', '3'].includes(ev.key)) setTab(TABS[Number(ev.key) - 1]);
  });

  // Minimal valid scenario template for the importer (mirrors data/demo.json shape).
  function SAMPLE() {
    return {
      scenario: 'Imported payments lab incident', fingerprint: 'payments-lab-case',
      source: 'internet', vulnerable: 'api', target: 'ledger-db',
      assets: [
        { id: 'internet', kind: 'ingress', x: 80, y: 220 }, { id: 'api', kind: 'service', x: 260, y: 220 },
        { id: 'ops-role', kind: 'identity', x: 440, y: 120 }, { id: 'ledger-db', kind: 'database', x: 620, y: 220 },
        { id: 'payouts', kind: 'business_flow', value: 60, x: 260, y: 400 },
      ],
      pivot_edges: [{ id: 'e1', from: 'internet', to: 'api' }, { id: 'e2', from: 'api', to: 'ops-role' }, { id: 'e3', from: 'ops-role', to: 'ledger-db' }, { id: 'e4', from: 'api', to: 'ledger-db' }],
      depends_edges: [{ id: 'd1', from: 'payouts', to: 'api' }],
      actions: [
        { id: 'isolate-api', label: 'Isolate api', blocked_nodes: ['api'], blocked_edges: [], cost: 1 },
        { id: 'revoke-ops', label: 'Revoke ops-role', blocked_nodes: [], blocked_edges: ['e2'], cost: 2 },
        { id: 'firewall-db', label: 'Firewall api → ledger-db', blocked_nodes: [], blocked_edges: ['e4'], cost: 2 },
      ],
    };
  }

  /* boot */
  const known = store.get('maelin.tenant');
  if (known && !['alpha', 'beta'].includes(known)) addTenant(known);
  $$('#tenantSeg button').forEach((b) => b.classList.toggle('on', b.dataset.tenant === state.tenant));
  window.hudWired = true;
  renderAll();
  requestAnimationFrame(inks);
  document.fonts && document.fonts.ready.then(inks);
  loadTenant(true);
})();
