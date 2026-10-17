/* Live FalkorDB topology cockpit: force layout, drag, cut animation and uploads.
   Draws ONLY the graph queried by the API. No hidden in-memory traversal engine. */
(() => {
  let installedGraph = null;
  let dragging = null;
  let wasDrag = false;
  let knownDefaults = null;
  const svg = document.querySelector('#topo');
  function solveLayout(g) {
    if (!g?.nodes?.length) return;
    const nodes=g.nodes, edges=g.edges, byId=new Map(nodes.map(n=>[n.id,n]));
    for(let step=0;step<105;step++){
      const force=new Map(nodes.map(n=>[n.id,{x:(410-n.x)*.006,y:(255-n.y)*.006}]));
      for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
        const a=nodes[i],b=nodes[j],dx=a.x-b.x,dy=a.y-b.y;
        const dist=Math.max(22,Math.hypot(dx,dy)),strength=1400/(dist*dist);
        force.get(a.id).x+=dx/dist*strength;
        force.get(a.id).y+=dy/dist*strength;
        force.get(b.id).x-=dx/dist*strength;
        force.get(b.id).y-=dy/dist*strength;
      }
      for(const edge of edges){
        const a=byId.get(edge.from),b=byId.get(edge.to);
        if(!a||!b)continue;
        const dx=b.x-a.x,dy=b.y-a.y,dist=Math.max(10,Math.hypot(dx,dy));
        const v=(dist-(edge.kind==='DEPENDS_ON'?145:165))*.002;
        force.get(a.id).x+=dx/dist*v;force.get(a.id).y+=dy/dist*v;
        force.get(b.id).x-=dx/dist*v;force.get(b.id).y-=dy/dist*v;
      }
      for(const n of nodes){
        const v=force.get(n.id);
        n.x=Math.min(750,Math.max(70,n.x+v.x*2));
        n.y=Math.min(462,Math.max(45,n.y+v.y*2));
      }
    }
  }
  const originalDraw = drawGraph;
  drawGraph = function() {
    if(graph && graph!==installedGraph){solveLayout(graph);installedGraph=graph;}
    originalDraw();
    if(!graph)return;
    const cut=current?.analysis?.plans?.[selection], edges=graph.edges;
    const cutNodes=new Set(cut?.blocked_nodes||[]);
    const cutEdges=new Set(cut?.blocked_edges||[]);
    const threats=new Set((current?.paths||[]).flatMap(p=>p.edges));
    const paths=svg.querySelectorAll('path[d^="M "]');
    paths.forEach((path,i)=>{
      const e=edges[i];if(!e)return;
      const marked=cutEdges.has(e.id)||cutNodes.has(e.from)||cutNodes.has(e.to);
      path.classList.toggle('edge-cut',marked);
      path.classList.toggle('edge-threat',!marked&&threats.has(e.id));
    });
  };
  function pointOf(event){
    const point=svg.createSVGPoint();
    point.x=event.clientX;point.y=event.clientY;
    const matrix=svg.getScreenCTM();
    return matrix?point.matrixTransform(matrix.inverse()):null;
  }
  svg.addEventListener('pointerdown',event=>{
    const el=event.target.closest('g[data-node]');
    if(!el||!graph)return;
    dragging={id:el.dataset.node,x:event.clientX,y:event.clientY};
    wasDrag=false;svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener('pointermove',event=>{
    if(!dragging||!graph)return;
    if(Math.hypot(event.clientX-dragging.x,event.clientY-dragging.y)>5)wasDrag=true;
    if(!wasDrag)return;
    const at=pointOf(event),node=graph.nodes.find(n=>n.id===dragging.id);
    if(!at||!node)return;
    node.x=Math.max(65,Math.min(755,at.x));
    node.y=Math.max(45,Math.min(465,at.y));
    drawGraph();
  });
  svg.addEventListener('pointerup',()=>{dragging=null;});
  svg.addEventListener('pointercancel',()=>{dragging=null;});
  svg.addEventListener('click',event=>{
    if(!wasDrag)return;
    event.stopImmediatePropagation();
    wasDrag=false;
  },true);

  const originalRefresh=refresh;
  refresh=async function(){
    await originalRefresh();
    if(!graph)return;
    try{
      knownDefaults=await request('/api/scene?tenant='+encodeURIComponent(tenant()));
      for(const key of ['source','vulnerable','target']){
        const control=$(key),candidate=knownDefaults[key];
        if([...control.options].some(o=>o.value===candidate))control.value=candidate;
      }
      drawGraph();
    }catch(e){console.warn('Graph scenario metadata unavailable',e);}
  };

  $('uploadScenario').addEventListener('click',async()=>{
    const button=$('uploadScenario'),status=$('importStatus');
    try{
      const incoming=JSON.parse($('scenarioJson').value);
      const chosen=$('newTenant').value.trim();
      if(!/^[a-z][a-z0-9_-]{0,31}$/.test(chosen))throw Error('Use a valid new tenant name beginning with a lowercase letter');
      button.disabled=true;status.textContent='Validating and writing to FalkorDB…';
      const uploaded=await request('/api/scenarios',{tenant:chosen,dataset:incoming});
      $('tenant').add(new Option('Tenant · '+chosen,chosen));
      $('tenant').value=chosen;
      current=null;selection=0;installedGraph=null;knownDefaults=null;
      await refresh();
      status.textContent='Imported '+uploaded.nodes+' assets. Select a node to investigate.';
      $('scenarioImport').open=false;
    }catch(e){status.textContent='Import failed: '+e.message;}
    finally{button.disabled=false;}
  });

  // Add evidence-bound specialist interpretation without changing the safety kernel.
  const originalHandoff=handoffSummary;
  handoffSummary=function(h){
    const base=originalHandoff(h);
    const r=h.payload?.llm_analysis || h.payload?.remediation_reasoning;
    return r?.conclusion ? base+' Model reasoning: '+r.conclusion : base;
  };
})();
