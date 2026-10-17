/* Maelin — Lumen Edge Extreme Savage 3D Graph UI & Topology Cockpit
   True 3D projective geometry, interactive orbit camera, depth layering,
   volumetric laser conduits, and engineered glass node pods. */

(() => {
  let installedGraph = null;
  let dragging = null;
  let isOrbiting = false;
  let orbitStart = { x: 0, y: 0, yaw: 0, pitch: 0 };
  let wasDrag = false;
  let knownDefaults = null;
  let autoOrbit = false;
  let orbitAnimId = null;

  // 3D Camera State
  const camera = {
    pitch: 26,     // vertical tilt angle in degrees (0 = top-down 2D, 75 = extreme horizon)
    yaw: -22,      // horizontal rotation in degrees
    fov: 780,      // field of view focal length
    distance: 820, // camera distance from graph center
    zoom: 1.05,    // scale multiplier
    panX: 0,
    panY: 0
  };

  const svg = document.querySelector('#topo');

  // Force-directed layout solver for 2D base positions
  function solveLayout(g) {
    if (!g?.nodes?.length) return;
    const nodes = g.nodes, edges = g.edges, byId = new Map(nodes.map(n => [n.id, n]));
    for (let step = 0; step < 110; step++) {
      const force = new Map(nodes.map(n => [n.id, { x: (410 - n.x) * 0.006, y: (255 - n.y) * 0.006 }]));
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j], dx = a.x - b.x, dy = a.y - b.y;
          const dist = Math.max(22, Math.hypot(dx, dy)), strength = 1450 / (dist * dist);
          force.get(a.id).x += dx / dist * strength;
          force.get(a.id).y += dy / dist * strength;
          force.get(b.id).x -= dx / dist * strength;
          force.get(b.id).y -= dy / dist * strength;
        }
      }
      for (const edge of edges) {
        const a = byId.get(edge.from), b = byId.get(edge.to);
        if (!a || !b) continue;
        const dx = b.x - a.x, dy = b.y - a.y, dist = Math.max(10, Math.hypot(dx, dy));
        const v = (dist - (edge.kind === 'DEPENDS_ON' ? 145 : 165)) * 0.002;
        force.get(a.id).x += dx / dist * v; force.get(a.id).y += dy / dist * v;
        force.get(b.id).x -= dx / dist * v; force.get(b.id).y -= dy / dist * v;
      }
      for (const n of nodes) {
        const v = force.get(n.id);
        n.x = Math.min(745, Math.max(75, n.x + v.x * 2));
        n.y = Math.min(460, Math.max(50, n.y + v.y * 2));
      }
    }
  }

  // 3D Perspective Projection Function
  function project(x, y, z) {
    const radY = (camera.yaw * Math.PI) / 180;
    const radP = (camera.pitch * Math.PI) / 180;
    const cosY = Math.cos(radY), sinY = Math.sin(radY);
    const cosP = Math.cos(radP), sinP = Math.sin(radP);

    // Rotate around Y (yaw)
    const x1 = x * cosY + z * sinY;
    const z1 = -x * sinY + z * cosY;

    // Rotate around X (pitch)
    const y2 = y * cosP - z1 * sinP;
    const z2 = y * sinP + z1 * cosP + camera.distance;

    const depth = Math.max(90, z2);
    const scale = (camera.fov / depth) * camera.zoom;
    const sx = 410 + x1 * scale + camera.panX;
    const sy = 255 + y2 * scale + camera.panY;

    return { x: sx, y: sy, scale, z: depth, rawX: x1, rawY: y2, rawZ: z1 };
  }

  // Determine semantic 3D elevation layer for each node
  function getNodeElevation(n) {
    let baseZ = 0;
    if (n.kind === 'business_flow') baseZ = 42;
    else if (n.kind === 'database') baseZ = -55;
    else if (n.id === 'internet') baseZ = 68;
    else if (n.id === 'auth-service' || n.kind === 'identity') baseZ = 20;
    else baseZ = -5;

    // Active/vulnerable node gets elevation boost
    const vulnVal = document.getElementById('vulnerable')?.value;
    if (vulnVal && n.id === vulnVal) {
      baseZ += 28;
    }
    return baseZ;
  }

  // Extreme Savage 3D Graph Renderer
  drawGraph = function() {
    if (!graph || !svg) return;
    if (graph !== installedGraph) {
      solveLayout(graph);
      installedGraph = graph;
    }

    const threat = current?.paths || [];
    const threatEdges = new Set(threat.flatMap(p => p.edges));
    const chosen = current?.analysis?.plans?.[selection] || null;
    const blockedIds = new Set(chosen?.blocked_edges || []);
    const blockedNodes = new Set(chosen?.blocked_nodes || []);
    const vulnVal = document.getElementById('vulnerable')?.value;

    // Update HUD telemetry
    const tel = document.getElementById('hudTelemetry');
    if (tel) {
      tel.textContent = `CAM: PITCH ${Math.round(camera.pitch)}° | YAW ${Math.round(camera.yaw)}° | ZOOM ${camera.zoom.toFixed(2)}x`;
    }

    // Compute 3D node projections
    const nodeProj = new Map();
    for (const n of graph.nodes) {
      const z = getNodeElevation(n);
      const proj = project(n.x - 410, n.y - 255, z);
      nodeProj.set(n.id, { node: n, proj, z });
    }

    let svgContent = `<defs>
      <marker id="arrowR" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
        <path d="M0 0 L7 4 L0 8" fill="none" stroke="#f46b7a" stroke-width="1.3"/>
      </marker>
      <marker id="arrowB" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
        <path d="M0 0 L7 4 L0 8" fill="none" stroke="#7098c2" stroke-width="1.3"/>
      </marker>
      <radialGradient id="nodeGrad" cx="50%" cy="100%" r="80%">
        <stop offset="0%" stop-color="rgba(255,255,255,0.08)"/>
        <stop offset="100%" stop-color="rgba(16,21,29,0.96)"/>
      </radialGradient>
      <filter id="lumenGlow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="3" result="blur"/>
        <feComposite in="SourceGraphic" in2="blur" operator="over"/>
      </filter>
    </defs>`;

    // Layer 1: 3D Holographic Ground Grid (Floor plane at z = -90)
    const zFloor = -90;
    let gridSvg = '<g class="ground-grid" opacity="0.35">';
    for (let gx = -360; gx <= 360; gx += 120) {
      const p1 = project(gx, -240, zFloor);
      const p2 = project(gx, 240, zFloor);
      gridSvg += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="rgba(112,152,194,0.3)" stroke-width="0.8"/>`;
    }
    for (let gy = -240; gy <= 240; gy += 80) {
      const p1 = project(-360, gy, zFloor);
      const p2 = project(360, gy, zFloor);
      gridSvg += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="rgba(112,152,194,0.3)" stroke-width="0.8"/>`;
    }
    gridSvg += '</g>';
    svgContent += gridSvg;

    // Layer 2: Drop Filaments & Floor Shadows
    let dropSvg = '<g class="drop-filaments">';
    for (const n of graph.nodes) {
      const info = nodeProj.get(n.id);
      if (!info) continue;
      const gp = project(n.x - 410, n.y - 255, zFloor);
      const np = info.proj;
      const isSelected = n.id === vulnVal;
      const shadowColor = isSelected ? '#f46b7a' : (n.kind === 'business_flow' ? '#7098c2' : '#5ce1b3');

      // Vertical laser filament
      dropSvg += `<line x1="${gp.x}" y1="${gp.y}" x2="${np.x}" y2="${np.y}" stroke="rgba(255,255,255,0.18)" stroke-dasharray="3 3" stroke-width="1"/>`;
      // Projected floor shadow ellipse
      dropSvg += `<ellipse cx="${gp.x}" cy="${gp.y}" rx="${34 * gp.scale}" ry="${12 * gp.scale}" fill="rgba(0,0,0,0.55)" stroke="${shadowColor}" stroke-opacity="0.25" stroke-width="1"/>`;
    }
    dropSvg += '</g>';
    svgContent += dropSvg;

    // Layer 3: 3D Edge Conduits (Bezier curves arched in 3D)
    // Edges are sorted by average depth (deepest first)
    const edgeData = [];
    for (let idx = 0; idx < graph.edges.length; idx++) {
      const e = graph.edges[idx];
      const aInfo = nodeProj.get(e.from), bInfo = nodeProj.get(e.to);
      if (!aInfo || !bInfo) continue;

      const pa = aInfo.proj, pb = bInfo.proj;
      const midX = (aInfo.node.x + bInfo.node.x) / 2 - 410;
      const midY = (aInfo.node.y + bInfo.node.y) / 2 - 255;
      const midZ = (aInfo.z + bInfo.z) / 2 + 35; // 3D elevated arch
      const pm = project(midX, midY, midZ);

      const isPivot = e.kind === 'CAN_PIVOT';
      const cut = blockedIds.has(e.id) || blockedNodes.has(e.from) || blockedNodes.has(e.to);
      const isThreat = !cut && threatEdges.has(e.id);
      const avgZ = (pa.z + pb.z) / 2;

      edgeData.push({
        edge: e, idx, pa, pb, pm, isPivot, cut, isThreat, avgZ
      });
    }

    // Sort edges by depth (painter's algorithm)
    edgeData.sort((a, b) => b.avgZ - a.avgZ);

    let edgesSvg = '<g class="edges-layer">';
    for (const ed of edgeData) {
      const { edge: e, pa, pb, pm, isPivot, cut, isThreat } = ed;
      const stroke = cut ? '#5ce1b3' : (isThreat ? '#f46b7a' : (isPivot ? '#50637a' : '#5c80a6'));
      const width = cut ? 4.5 : (isThreat ? 3.2 : (isPivot ? 2.2 : 1.6));
      const dash = cut ? '8 5' : (isPivot ? '' : '6 5');
      const marker = isPivot ? 'url(#arrowR)' : 'url(#arrowB)';
      const cls = cut ? 'edge-cut' : (isThreat ? 'edge-threat' : '');

      edgesSvg += `<path d="M ${pa.x} ${pa.y} Q ${pm.x} ${pm.y} ${pb.x} ${pb.y}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-dasharray="${dash}" marker-end="${marker}" class="${cls}"/>`;
    }
    edgesSvg += '</g>';
    svgContent += edgesSvg;

    // Layer 4: 3D Engineered Glass Pods (Nodes)
    // Sorted by camera depth (deepest first)
    const sortedNodes = [...nodeProj.values()].sort((a, b) => b.proj.z - a.proj.z);

    let nodesSvg = '<g class="nodes-layer">';
    for (const info of sortedNodes) {
      const n = info.node, p = info.proj;
      const kind = n.kind;
      const isVuln = n.id === vulnVal || n.id === 'auth-service';
      const isBlocked = blockedNodes.has(n.id);

      let color = kind === 'business_flow' ? '#7098c2' :
                  kind === 'database' ? '#ffbe5e' :
                  kind === 'identity' ? '#f095ba' :
                  isVuln ? '#f46b7a' : '#5ce1b3';
      if (isBlocked) color = '#5ce1b3';

      const w = 124 * p.scale;
      const h = 42 * p.scale;
      const rx = 9 * p.scale;
      const x = p.x - w / 2;
      const y = p.y - h / 2;
      const label = n.id.replaceAll('-', ' ');

      nodesSvg += `<g data-node="${esc(n.id)}" style="cursor:grab">
        <!-- Ambient drop shadow -->
        <rect x="${x}" y="${y + 3 * p.scale}" width="${w}" height="${h}" rx="${rx}" fill="rgba(0,0,0,0.4)" />
        <!-- Engineered glass card body -->
        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="url(#nodeGrad)" stroke="${color}" stroke-width="${isVuln ? 2.2 : 1.3}" />
        <!-- Hairline top highlight (1px inset) -->
        <line x1="${x + 6 * p.scale}" y1="${y + 1}" x2="${x + w - 6 * p.scale}" y2="${y + 1}" stroke="rgba(255,255,255,0.3)" stroke-width="1" />
        <!-- Core status LED beacon -->
        <circle cx="${x + 15 * p.scale}" cy="${p.y}" r="${3.5 * p.scale}" fill="${color}" />
        <circle cx="${x + 15 * p.scale}" cy="${p.y}" r="${7 * p.scale}" fill="none" stroke="${color}" stroke-width="0.8" stroke-opacity="0.4" />
        <!-- Node label -->
        <text x="${x + 26 * p.scale}" y="${p.y + 4 * p.scale}" font-size="${10.5 * p.scale}px" font-weight="700" fill="#f0f5fa" font-family="Inter, system-ui, sans-serif">${esc(label)}</text>
        <!-- Impact units -->
        ${n.value ? `<text x="${p.x}" y="${y + h + 13 * p.scale}" text-anchor="middle" fill="#8090a3" font-size="${9 * p.scale}px" font-family="ui-monospace, monospace">${n.value} impact units</text>` : ''}
      </g>`;
    }
    nodesSvg += '</g>';
    svgContent += nodesSvg;

    svg.innerHTML = svgContent;
  };

  // Screen point coordinate helper
  function pointOf(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const matrix = svg.getScreenCTM();
    return matrix ? point.matrixTransform(matrix.inverse()) : null;
  }

  // Pointer Interaction: Drag node OR Orbit 3D Camera
  svg.addEventListener('pointerdown', event => {
    const el = event.target.closest('g[data-node]');
    if (el && graph) {
      // Node dragging
      dragging = { id: el.dataset.node, clientX: event.clientX, clientY: event.clientY };
      wasDrag = false;
      el.classList.add('grabbing');
      svg.setPointerCapture(event.pointerId);
    } else {
      // Background 3D Camera Orbit
      isOrbiting = true;
      orbitStart = { x: event.clientX, y: event.clientY, yaw: camera.yaw, pitch: camera.pitch };
      svg.classList.add('grabbing');
      svg.setPointerCapture(event.pointerId);
    }
  });

  svg.addEventListener('pointermove', event => {
    if (dragging && graph) {
      const dx = event.clientX - dragging.clientX;
      const dy = event.clientY - dragging.clientY;
      if (Math.hypot(dx, dy) > 5) wasDrag = true;
      if (!wasDrag) return;

      const node = graph.nodes.find(n => n.id === dragging.id);
      if (node) {
        // Translate screen drag into 2D plane delta scaled by camera zoom
        node.x = Math.max(65, Math.min(755, node.x + dx / camera.zoom));
        node.y = Math.max(45, Math.min(465, node.y + dy / camera.zoom));
        dragging.clientX = event.clientX;
        dragging.clientY = event.clientY;
        drawGraph();
      }
    } else if (isOrbiting) {
      const dx = event.clientX - orbitStart.x;
      const dy = event.clientY - orbitStart.y;
      if (Math.hypot(dx, dy) > 5) wasDrag = true;

      camera.yaw = (orbitStart.yaw + dx * 0.35) % 360;
      camera.pitch = Math.max(0, Math.min(75, orbitStart.pitch - dy * 0.35));
      drawGraph();
    }
  });

  svg.addEventListener('pointerup', () => {
    dragging = null;
    isOrbiting = false;
    svg.classList.remove('grabbing');
  });

  svg.addEventListener('pointercancel', () => {
    dragging = null;
    isOrbiting = false;
    svg.classList.remove('grabbing');
  });

  // Mouse wheel zooms 3D camera
  svg.addEventListener('wheel', event => {
    event.preventDefault();
    camera.zoom = Math.max(0.65, Math.min(2.2, camera.zoom - event.deltaY * 0.0012));
    drawGraph();
  }, { passive: false });

  // Suppress click on node if it was a drag operation
  svg.addEventListener('click', event => {
    if (!wasDrag) return;
    event.stopImmediatePropagation();
    wasDrag = false;
  }, true);

  // Setup 3D Camera HUD controls
  function setupHudControls() {
    const btnIso = document.getElementById('hud3dIso');
    const btnTilt = document.getElementById('hud3dTilt');
    const btnFlat = document.getElementById('hud2dFlat');
    const btnAuto = document.getElementById('hudAutoOrbit');
    const btnReset = document.getElementById('hudReset');

    const updateActiveBtn = (active) => {
      [btnIso, btnTilt, btnFlat].forEach(b => b?.classList.remove('active'));
      active?.classList.add('active');
    };

    if (btnIso) {
      btnIso.addEventListener('click', () => {
        camera.pitch = 28; camera.yaw = -24; camera.zoom = 1.05;
        updateActiveBtn(btnIso);
        drawGraph();
      });
    }

    if (btnTilt) {
      btnTilt.addEventListener('click', () => {
        camera.pitch = 44; camera.yaw = 32; camera.zoom = 1.15;
        updateActiveBtn(btnTilt);
        drawGraph();
      });
    }

    if (btnFlat) {
      btnFlat.addEventListener('click', () => {
        camera.pitch = 0; camera.yaw = 0; camera.zoom = 1.0;
        updateActiveBtn(btnFlat);
        drawGraph();
      });
    }

    if (btnAuto) {
      btnAuto.addEventListener('click', () => {
        autoOrbit = !autoOrbit;
        btnAuto.classList.toggle('active', autoOrbit);
        if (autoOrbit) {
          const step = () => {
            if (!autoOrbit) return;
            camera.yaw = (camera.yaw + 0.15) % 360;
            drawGraph();
            orbitAnimId = requestAnimationFrame(step);
          };
          orbitAnimId = requestAnimationFrame(step);
        } else if (orbitAnimId) {
          cancelAnimationFrame(orbitAnimId);
          orbitAnimId = null;
        }
      });
    }

    if (btnReset) {
      btnReset.addEventListener('click', () => {
        camera.pitch = 26; camera.yaw = -22; camera.zoom = 1.05;
        camera.panX = 0; camera.panY = 0;
        updateActiveBtn(btnIso);
        drawGraph();
      });
    }

    // Ephemeral demo advisory banner toggle
    const advToggle = document.getElementById('advisoryToggle');
    const advDetails = document.getElementById('advisoryDetails');
    if (advToggle && advDetails) {
      advToggle.addEventListener('click', () => {
        advDetails.style.display = advDetails.style.display === 'none' ? 'block' : 'none';
      });
    }
  }

  // Hook refresh to sync scenario scene defaults
  const originalRefresh = refresh;
  refresh = async function() {
    await originalRefresh();
    if (!graph) return;
    try {
      knownDefaults = await request('/api/scene?tenant=' + encodeURIComponent(tenant()));
      for (const key of ['source', 'vulnerable', 'target']) {
        const control = $(key), candidate = knownDefaults[key];
        if ([...control.options].some(o => o.value === candidate)) control.value = candidate;
      }
      drawGraph();
    } catch (e) {
      console.warn('Graph scenario metadata unavailable', e);
    }
  };

  // Scenario upload listener
  $('uploadScenario')?.addEventListener('click', async () => {
    const button = $('uploadScenario'), status = $('importStatus');
    try {
      const incoming = JSON.parse($('scenarioJson').value);
      const chosen = $('newTenant').value.trim();
      if (!/^[a-z][a-z0-9_-]{0,31}$/.test(chosen)) {
        throw Error('Use a valid new tenant name beginning with a lowercase letter');
      }
      button.disabled = true;
      status.textContent = 'Validating and writing to FalkorDB…';
      const uploaded = await request('/api/scenarios', { tenant: chosen, dataset: incoming });
      $('tenant').add(new Option('Tenant · ' + chosen, chosen));
      $('tenant').value = chosen;
      current = null; selection = 0; installedGraph = null; knownDefaults = null;
      await refresh();
      status.textContent = 'Imported ' + uploaded.nodes + ' assets. Select a node to investigate.';
      $('scenarioImport').open = false;
    } catch (e) {
      status.textContent = 'Import failed: ' + e.message;
    } finally {
      button.disabled = false;
    }
  });

  // Evidence-bound specialist interpretation
  const originalHandoff = handoffSummary;
  handoffSummary = function(h) {
    if (h.agent === 'recon' && h.payload?.cypher_query && $('cypherQuery')) {
      $('cypherQuery').textContent = h.payload.cypher_query + '\n' + JSON.stringify(h.payload.query_parameters, null, 2);
    }
    const base = originalHandoff(h);
    const r = h.payload?.llm_analysis || h.payload?.remediation_reasoning;
    return r?.conclusion ? base + ' Model reasoning: ' + r.conclusion : base;
  };

  // Initialize HUD controls
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupHudControls);
  } else {
    setupHudControls();
  }
})();
