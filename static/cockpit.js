/* Maelin — Lumen Edge Extreme Savage 3D Graph UI & Topology Cockpit
   True 3D projective geometry, interactive orbit camera, depth layering,
   volumetric laser conduits, animated threat pulses, and engineered glass node pods. */

(() => {
  let installedGraph = null;
  let dragging = null;
  let isOrbiting = false;
  let isPanning = false;
  let panStart = { x: 0, y: 0, panX: 0, panY: 0 };
  let orbitStart = { x: 0, y: 0, yaw: 0, pitch: 0 };
  let wasDrag = false;
  let activeGrabEl = null;
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

  const getSvg = () => document.getElementById('topo') || document.querySelector('#topo');
  let svg = getSvg();

  // Force-directed layout solver for 2D base positions (only for unpositioned nodes)
  function solveLayout(g) {
    if (!g?.nodes?.length) return;
    const nodes = g.nodes, edges = g.edges, byId = new Map(nodes.map(n => [n.id, n]));
    // Check if graph already has valid layout coordinates
    const hasCoords = nodes.every(n => typeof n.x === 'number' && typeof n.y === 'number' && n.x > 0 && n.y > 0);
    if (hasCoords) return;

    for (let step = 0; step < 110; step++) {
      const force = new Map(nodes.map(n => [n.id, { x: (410 - (n.x || 410)) * 0.006, y: (255 - (n.y || 255)) * 0.006 }]));
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j], dx = (a.x || 410) - (b.x || 410), dy = (a.y || 255) - (b.y || 255);
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
        const dx = (b.x || 410) - (a.x || 410), dy = (b.y || 255) - (a.y || 255), dist = Math.max(10, Math.hypot(dx, dy));
        const v = (dist - (edge.kind === 'DEPENDS_ON' ? 145 : 165)) * 0.002;
        force.get(a.id).x += dx / dist * v; force.get(a.id).y += dy / dist * v;
        force.get(b.id).x -= dx / dist * v; force.get(b.id).y -= dy / dist * v;
      }
      for (const n of nodes) {
        const v = force.get(n.id);
        n.x = Math.min(745, Math.max(75, (n.x || 410) + v.x * 2));
        n.y = Math.min(460, Math.max(50, (n.y || 255) + v.y * 2));
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
    if (n.kind === 'business_flow') baseZ = 46;
    else if (n.kind === 'database') baseZ = -55;
    else if (n.id === 'internet') baseZ = 70;
    else if (n.kind === 'identity') baseZ = 24;
    else baseZ = -2;

    // Active/vulnerable node gets dynamic focus lift
    const activeVuln = document.getElementById('vulnerable')?.value || knownDefaults?.vulnerable || 'auth-service';
    if (n.id === activeVuln) {
      baseZ += 32;
    }
    return baseZ;
  }

  // Stop auto-orbit cleanly
  function stopAutoOrbit() {
    if (autoOrbit) {
      autoOrbit = false;
      const btn = document.getElementById('hudAutoOrbit');
      if (btn) btn.classList.remove('active');
      if (orbitAnimId) {
        cancelAnimationFrame(orbitAnimId);
        orbitAnimId = null;
      }
    }
  }

  // Node category glyph helper
  function getNodeGlyph(kind, id) {
    if (id === 'internet') return '⟐';
    if (kind === 'business_flow') return '⚡';
    if (kind === 'database') return '⛁';
    if (kind === 'identity') return '⚿';
    return '⬡';
  }

  // Extreme Savage 3D Graph Renderer
  drawGraph = function() {
    if (!svg) svg = getSvg();
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
    const activeVuln = document.getElementById('vulnerable')?.value || knownDefaults?.vulnerable || 'auth-service';

    // Update HUD telemetry
    const tel = document.getElementById('hudTelemetry');
    if (tel) {
      tel.textContent = `CAM: PITCH ${Math.round(camera.pitch)}° | YAW ${Math.round(camera.yaw)}° | ZOOM ${camera.zoom.toFixed(2)}x | PAN ${Math.round(camera.panX)},${Math.round(camera.panY)}`;
    }

    // Compute 3D node projections
    const nodeProj = new Map();
    for (const n of graph.nodes) {
      const z = getNodeElevation(n);
      const proj = project(n.x - 410, n.y - 255, z);
      nodeProj.set(n.id, { node: n, proj, z });
    }

    let svgContent = `<defs>
      <marker id="arrowR" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto">
        <path d="M0 1 L7 4 L0 7 Z" fill="#f46b7a"/>
      </marker>
      <marker id="arrowB" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto">
        <path d="M0 1 L7 4 L0 7 Z" fill="#7098c2"/>
      </marker>
      <marker id="arrowG" markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto">
        <path d="M0 1 L7 4 L0 7 Z" fill="#5ce1b3"/>
      </marker>
      <radialGradient id="glassSurface" cx="50%" cy="100%" r="85%">
        <stop offset="0%" stop-color="rgba(255,255,255,0.09)"/>
        <stop offset="60%" stop-color="rgba(18,24,34,0.95)"/>
        <stop offset="100%" stop-color="rgba(9,12,17,0.98)"/>
      </radialGradient>
      <radialGradient id="glassSurfaceHot" cx="50%" cy="100%" r="90%">
        <stop offset="0%" stop-color="rgba(244,107,122,0.22)"/>
        <stop offset="60%" stop-color="rgba(28,14,20,0.95)"/>
        <stop offset="100%" stop-color="rgba(12,8,12,0.98)"/>
      </radialGradient>
      <filter id="lumenGlow" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="4" result="blur"/>
        <feComposite in="SourceGraphic" in2="blur" operator="over"/>
      </filter>
      <filter id="laserGlow" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="5" result="blur"/>
        <feComposite in="SourceGraphic" in2="blur" operator="over"/>
      </filter>
    </defs>`;

    // Layer 1: 3D Holographic Perspective Floor Grid (Floor plane at z = -90)
    const zFloor = -90;
    let gridSvg = '<g class="ground-grid" opacity="0.45">';
    for (let gx = -420; gx <= 420; gx += 105) {
      const p1 = project(gx, -270, zFloor);
      const p2 = project(gx, 270, zFloor);
      gridSvg += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="rgba(112,152,194,0.25)" stroke-width="0.8"/>`;
    }
    for (let gy = -270; gy <= 270; gy += 90) {
      const p1 = project(-420, gy, zFloor);
      const p2 = project(420, gy, zFloor);
      gridSvg += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="rgba(112,152,194,0.25)" stroke-width="0.8"/>`;
    }
    // Floor coordinate crosshairs at grid intersections
    for (let gx = -315; gx <= 315; gx += 210) {
      for (let gy = -180; gy <= 180; gy += 180) {
        const cp = project(gx, gy, zFloor);
        gridSvg += `<circle cx="${cp.x}" cy="${cp.y}" r="2" fill="rgba(112,152,194,0.6)"/>`;
      }
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
      const isSelected = n.id === activeVuln;
      const filamentColor = isSelected ? '#f46b7a' : (n.kind === 'business_flow' ? '#7098c2' : '#5ce1b3');
      const filamentWidth = isSelected ? 1.8 : 1.0;
      const filamentOpacity = isSelected ? 0.6 : 0.22;

      // Vertical laser filament
      dropSvg += `<line x1="${gp.x}" y1="${gp.y}" x2="${np.x}" y2="${np.y}" stroke="${filamentColor}" stroke-opacity="${filamentOpacity}" stroke-dasharray="3 3" stroke-width="${filamentWidth}"/>`;
      // Projected floor shadow ellipse with outer glow ring
      dropSvg += `<ellipse cx="${gp.x}" cy="${gp.y}" rx="${38 * gp.scale}" ry="${13 * gp.scale}" fill="rgba(0,0,0,0.6)" stroke="${filamentColor}" stroke-opacity="${isSelected ? 0.45 : 0.2}" stroke-width="1"/>`;
      if (isSelected) {
        dropSvg += `<circle cx="${gp.x}" cy="${gp.y}" r="${4 * gp.scale}" fill="#f46b7a" opacity="0.8"/>`;
      }
    }
    dropSvg += '</g>';
    svgContent += dropSvg;

    // Layer 3: 3D Arched Laser Conduits (Edges)
    const edgeData = [];
    for (let idx = 0; idx < graph.edges.length; idx++) {
      const e = graph.edges[idx];
      const aInfo = nodeProj.get(e.from), bInfo = nodeProj.get(e.to);
      if (!aInfo || !bInfo) continue;

      const pa = aInfo.proj, pb = bInfo.proj;
      const midX = (aInfo.node.x + bInfo.node.x) / 2 - 410;
      const midY = (aInfo.node.y + bInfo.node.y) / 2 - 255;
      const midZ = (aInfo.z + bInfo.z) / 2 + 36; // 3D elevated arch
      const pm = project(midX, midY, midZ);

      const isPivot = e.kind === 'CAN_PIVOT';
      const cut = blockedIds.has(e.id) || blockedNodes.has(e.from) || blockedNodes.has(e.to);
      const isThreat = !cut && threatEdges.has(e.id);
      const avgZ = (pa.z + pb.z) / 2;

      // Calculate tangent vector at endpoint B to trim edge neatly at node card boundary
      const bdx = pb.x - pm.x, bdy = pb.y - pm.y;
      const bdist = Math.hypot(bdx, bdy) || 1;
      const bux = bdx / bdist, buy = bdy / bdist;
      const targetX = pb.x - bux * (44 * pb.scale);
      const targetY = pb.y - buy * (22 * pb.scale);

      // Calculate tangent vector at startpoint A to trim edge neatly at node card boundary
      const adx = pm.x - pa.x, ady = pm.y - pa.y;
      const adist = Math.hypot(adx, ady) || 1;
      const aux = adx / adist, auy = ady / adist;
      const startX = pa.x + aux * (38 * pa.scale);
      const startY = pa.y + auy * (20 * pa.scale);

      edgeData.push({
        edge: e, idx, startX, startY, targetX, targetY, pm, isPivot, cut, isThreat, avgZ
      });
    }

    // Sort edges by depth (painter's algorithm)
    edgeData.sort((a, b) => b.avgZ - a.avgZ);

    let edgesSvg = '<g class="edges-layer">';
    for (const ed of edgeData) {
      const { startX, startY, targetX, targetY, pm, isPivot, cut, isThreat } = ed;
      const stroke = cut ? '#5ce1b3' : (isThreat ? '#f46b7a' : (isPivot ? '#50637a' : '#5c80a6'));
      const width = cut ? 4.2 : (isThreat ? 3.2 : (isPivot ? 2.0 : 1.5));
      const dash = cut ? '8 5' : (isPivot ? '' : '6 5');
      const marker = cut ? 'url(#arrowG)' : (isPivot ? 'url(#arrowR)' : 'url(#arrowB)');
      const cls = cut ? 'edge-cut' : (isThreat ? 'edge-threat' : '');

      const dPath = `M ${startX} ${startY} Q ${pm.x} ${pm.y} ${targetX} ${targetY}`;

      // Outer glow conduit for active threat or cut
      if (isThreat) {
        edgesSvg += `<path d="${dPath}" fill="none" stroke="rgba(244,107,122,0.35)" stroke-width="7" stroke-linecap="round" />`;
      } else if (cut) {
        edgesSvg += `<path d="${dPath}" fill="none" stroke="rgba(92,225,179,0.3)" stroke-width="8" stroke-linecap="round" />`;
      }

      // Base laser conduit
      edgesSvg += `<path d="${dPath}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-dasharray="${dash}" marker-end="${marker}" class="${cls}"/>`;

      // Extreme Savage Live Threat Laser Pulse
      if (isThreat) {
        edgesSvg += `<path d="${dPath}" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-dasharray="16 110" class="edge-threat-pulse"/>`;
      }
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
      const isVuln = n.id === activeVuln;
      const isBlocked = blockedNodes.has(n.id);

      let color = isVuln ? '#f46b7a' :
                  kind === 'business_flow' ? '#7098c2' :
                  kind === 'database' ? '#ffbe5e' :
                  kind === 'identity' ? '#f095ba' :
                  '#5ce1b3';
      if (isBlocked) color = '#5ce1b3';

      const w = 126 * p.scale;
      const h = 42 * p.scale;
      const rx = 8 * p.scale;
      const x = p.x - w / 2;
      const y = p.y - h / 2;
      const label = n.id.replaceAll('-', ' ');
      const glyph = getNodeGlyph(kind, n.id);

      nodesSvg += `<g data-node="${esc(n.id)}" class="node-pod ${isVuln ? 'node-vuln' : ''}" style="cursor:grab">
        <!-- Ambient drop shadow -->
        <rect x="${x}" y="${y + 3 * p.scale}" width="${w}" height="${h}" rx="${rx}" fill="rgba(0,0,0,0.45)" />
        <!-- Engineered glass card body -->
        <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${isVuln ? 'url(#glassSurfaceHot)' : 'url(#glassSurface)'}" stroke="${color}" stroke-width="${isVuln ? 2.2 : 1.3}" stroke-opacity="${isVuln ? 1 : 0.85}"/>
        <!-- Hairline top highlight (1px inset rim) -->
        <line x1="${x + 6 * p.scale}" y1="${y + 1}" x2="${x + w - 6 * p.scale}" y2="${y + 1}" stroke="rgba(255,255,255,0.32)" stroke-width="1" />
        <!-- Luminous Horizon Line along bottom of node -->
        <line x1="${x + 14 * p.scale}" y1="${y + h - 1}" x2="${x + w - 14 * p.scale}" y2="${y + h - 1}" stroke="${color}" stroke-opacity="${isVuln ? 0.9 : 0.4}" stroke-width="1.2" />
        <!-- Category icon glyph badge -->
        <rect x="${x + 7 * p.scale}" y="${p.y - 10 * p.scale}" width="${18 * p.scale}" height="${20 * p.scale}" rx="${4 * p.scale}" fill="rgba(255,255,255,0.06)" stroke="${color}" stroke-width="0.8" stroke-opacity="0.4"/>
        <text x="${x + 16 * p.scale}" y="${p.y + 4 * p.scale}" text-anchor="middle" font-size="${10 * p.scale}px" fill="${color}">${glyph}</text>
        <!-- Node label -->
        <text x="${x + 31 * p.scale}" y="${p.y + 4 * p.scale}" font-size="${10.5 * p.scale}px" font-weight="700" fill="#f0f5fa" font-family="'Space Grotesk', Inter, system-ui, sans-serif">${esc(label)}</text>
        <!-- Impact units / subtitle -->
        ${n.value ? `<text x="${p.x}" y="${y + h + 13 * p.scale}" text-anchor="middle" fill="#8090a3" font-size="${9 * p.scale}px" font-family="ui-monospace, monospace">${n.value} impact units</text>` : ''}
      </g>`;
    }
    nodesSvg += '</g>';
    svgContent += nodesSvg;

    svg.innerHTML = svgContent;
  };

  function setupSvgInteractions() {
    if (!svg) svg = getSvg();
    if (!svg || svg._cockpitInteractionsBound) return;
    svg._cockpitInteractionsBound = true;

    // Prevent context menu on SVG so right-click can pan freely
    svg.addEventListener('contextmenu', e => e.preventDefault());

    // Pointer Interaction: Drag node OR Orbit / Pan 3D Camera
    svg.addEventListener('pointerdown', event => {
      stopAutoOrbit();
      const el = event.target.closest('g[data-node]');

      // Right-click, middle-click, or Shift + left-click initiates PAN
      if (event.button === 2 || event.button === 1 || event.shiftKey) {
        isPanning = true;
        panStart = { x: event.clientX, y: event.clientY, panX: camera.panX, panY: camera.panY };
        svg.classList.add('grabbing');
        svg.setPointerCapture(event.pointerId);
        return;
      }

      if (el && graph) {
        // Node dragging
        dragging = { id: el.dataset.node, clientX: event.clientX, clientY: event.clientY };
        wasDrag = false;
        activeGrabEl = el;
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
      if (isPanning) {
        const dx = event.clientX - panStart.x;
        const dy = event.clientY - panStart.y;
        camera.panX = panStart.panX + dx;
        camera.panY = panStart.panY + dy;
        drawGraph();
        return;
      }

      if (dragging && graph) {
        const dsx = event.clientX - dragging.clientX;
        const dsy = event.clientY - dragging.clientY;
        if (Math.hypot(dsx, dsy) > 4) wasDrag = true;
        if (!wasDrag) return;

        const node = graph.nodes.find(n => n.id === dragging.id);
        if (node) {
          // True 3D Inverse Camera Projection Transformation
          const radY = (camera.yaw * Math.PI) / 180;
          const radP = (camera.pitch * Math.PI) / 180;
          const cosY = Math.cos(radY), sinY = Math.sin(radY);
          const cosP = Math.cos(radP), sinP = Math.sin(radP);
          const safeCosY = Math.abs(cosY) > 0.15 ? cosY : (cosY >= 0 ? 0.15 : -0.15);
          const safeCosP = Math.abs(cosP) > 0.15 ? cosP : 0.15;

          const scale = camera.zoom;
          const dx_world = dsx / (scale * safeCosY);
          const dy_world = (dsy - scale * sinY * sinP * dx_world) / (scale * safeCosP);

          node.x = Math.max(65, Math.min(755, node.x + dx_world));
          node.y = Math.max(45, Math.min(465, node.y + dy_world));

          dragging.clientX = event.clientX;
          dragging.clientY = event.clientY;
          drawGraph();
        }
      } else if (isOrbiting) {
        const dx = event.clientX - orbitStart.x;
        const dy = event.clientY - orbitStart.y;
        if (Math.hypot(dx, dy) > 4) wasDrag = true;

        camera.yaw = (orbitStart.yaw + dx * 0.35) % 360;
        camera.pitch = Math.max(0, Math.min(75, orbitStart.pitch - dy * 0.35));
        drawGraph();
      }
    });

    const cleanupPointers = () => {
      dragging = null;
      isOrbiting = false;
      isPanning = false;
      if (activeGrabEl) {
        activeGrabEl.classList.remove('grabbing');
        activeGrabEl = null;
      }
      svg.classList.remove('grabbing');
    };

    svg.addEventListener('pointerup', cleanupPointers);
    svg.addEventListener('pointercancel', cleanupPointers);

    // Mouse wheel zooms 3D camera
    svg.addEventListener('wheel', event => {
      event.preventDefault();
      stopAutoOrbit();
      camera.zoom = Math.max(0.55, Math.min(2.4, camera.zoom - event.deltaY * 0.0012));
      drawGraph();
    }, { passive: false });

    // Suppress click on node if it was a drag operation
    svg.addEventListener('click', event => {
      if (!wasDrag) return;
      event.stopImmediatePropagation();
      wasDrag = false;
    }, true);
  }

  // Setup 3D Camera HUD controls
  function setupHudControls() {
    const btnIso = document.getElementById('hud3dIso');
    const btnTilt = document.getElementById('hud3dTilt');
    const btnBirdeye = document.getElementById('hud3dBirdeye');
    const btnFlat = document.getElementById('hud2dFlat');
    const btnAuto = document.getElementById('hudAutoOrbit');
    const btnZoomIn = document.getElementById('hudZoomIn');
    const btnZoomOut = document.getElementById('hudZoomOut');
    const btnReset = document.getElementById('hudReset');

    const updateActiveBtn = (active) => {
      [btnIso, btnTilt, btnBirdeye, btnFlat].forEach(b => b?.classList.remove('active'));
      active?.classList.add('active');
    };

    if (btnIso) {
      btnIso.addEventListener('click', () => {
        stopAutoOrbit();
        camera.pitch = 28; camera.yaw = -24; camera.zoom = 1.05;
        camera.panX = 0; camera.panY = 0;
        updateActiveBtn(btnIso);
        drawGraph();
      });
    }

    if (btnTilt) {
      btnTilt.addEventListener('click', () => {
        stopAutoOrbit();
        camera.pitch = 44; camera.yaw = 32; camera.zoom = 1.15;
        camera.panX = 0; camera.panY = 0;
        updateActiveBtn(btnTilt);
        drawGraph();
      });
    }

    if (btnBirdeye) {
      btnBirdeye.addEventListener('click', () => {
        stopAutoOrbit();
        camera.pitch = 56; camera.yaw = -12; camera.zoom = 1.1;
        camera.panX = 0; camera.panY = 0;
        updateActiveBtn(btnBirdeye);
        drawGraph();
      });
    }

    if (btnFlat) {
      btnFlat.addEventListener('click', () => {
        stopAutoOrbit();
        camera.pitch = 0; camera.yaw = 0; camera.zoom = 1.0;
        camera.panX = 0; camera.panY = 0;
        updateActiveBtn(btnFlat);
        drawGraph();
      });
    }

    if (btnZoomIn) {
      btnZoomIn.addEventListener('click', () => {
        camera.zoom = Math.min(2.4, camera.zoom + 0.15);
        drawGraph();
      });
    }

    if (btnZoomOut) {
      btnZoomOut.addEventListener('click', () => {
        camera.zoom = Math.max(0.55, camera.zoom - 0.15);
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
            camera.yaw = (camera.yaw + 0.2) % 360;
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
        stopAutoOrbit();
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

  // Export 3D renderer
  window.renderCockpit3D = drawGraph;
  window.drawGraph = drawGraph;

  // Initialize cockpit stage, HUD controls, and graph rendering
  function initCockpit() {
    setupSvgInteractions();
    setupHudControls();
    if (typeof graph !== 'undefined' && graph) {
      drawGraph();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCockpit);
  } else {
    initCockpit();
  }
})();

