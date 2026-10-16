"""Graph-backed what-if executor. Runs interventions only on a disposable FalkorDB clone.

The production topology remains untouched. This module NEVER issues real cloud commands.
The result is based on re-querying the cloned FalkorDB graph after applying cuts,
not simply trusting the optimizer's path enumeration.
"""
from __future__ import annotations
import uuid


def _threat_paths(graph, scene):
    rows = graph.ro_query("""MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id=$vulnerable)
RETURN [n IN nodes(p) | n.id], [r IN relationships(p) | r.edge_id] LIMIT 257""",
        {"source":scene["source"],"target":scene["target"],"vulnerable":scene["vulnerable"]}).result_set
    if len(rows) > 256:
        raise OverflowError("Simulation traversal exceeded 256 candidate paths; outcome is inconclusive")
    return [{"nodes":r[0], "edges":r[1]} for r in rows]


def _business_paths(graph):
    rows = graph.ro_query("""MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id] LIMIT 1025""").result_set
    if len(rows) > 1024:
        raise OverflowError("Simulation dependency traversal exceeded 1024 paths")
    return [{"flow":r[0],"value":r[1],"nodes":r[2]} for r in rows]


def run_simulation(store, tenant, session_id, scene, action_ids):
    """Execute a proposed intervention on an isolated FalkorDB clone; persist results.

    After a topology change the old action may stop being sufficient; this is
    intentionally observable. Only proposals from a real session are eligible.
    """
    if not isinstance(action_ids, list) or not (1 <= len(action_ids) <= 3):
        raise ValueError("Specify 1-3 intervention IDs")
    if len(set(action_ids)) != len(action_ids):
        raise ValueError("Duplicate intervention ID")
    offered = set(store.session_actions(tenant, session_id))
    if not set(action_ids) <= offered:
        raise PermissionError("Action not offered in the specified investigation session")
    actions = {a["id"]:a for a in store.interventions(tenant)}
    if any(i not in actions for i in action_ids):
        raise LookupError("Intervention no longer exists in current topology")
    topo, _ = store.graphs(tenant)
    # Separate namespace per run also avoids the concurrency races of a shared
    # scratch graph. FalkorDB Graph.copy is a database-native graph operation.
    graph_name = f"maelin_{tenant}_sim_{uuid.uuid4().hex}"
    sim = topo.copy(graph_name)
    try:
        original = _threat_paths(sim, scene)
        dependencies = _business_paths(sim)
        if not original:
            result = {"status":"inconclusive_no_known_threat_path", "contained":False,
                      "original_routes":0,"remaining_routes":0,"remaining_paths":[],
                      "affected_flows":[],"modeled_disruption_cost":0}
        else:
            blocked_nodes = {n for i in action_ids for n in actions[i]["blocked_nodes"]}
            blocked_edges = {e for i in action_ids for e in actions[i]["blocked_edges"]}
            # All identifiers come from trusted database intervention records;
            # the queries are parametrized. Never accept arbitrary Cypher.
            for eid in sorted(blocked_edges):
                sim.query("MATCH ()-[r:CAN_PIVOT {edge_id:$edge_id}]->() DELETE r",
                          {"edge_id":eid})
            for nid in sorted(blocked_nodes):
                sim.query("MATCH (n:Asset {id:$node_id}) DETACH DELETE n", {"node_id":nid})
            remaining = _threat_paths(sim, scene)
            after_dependencies = _business_paths(sim)
            before_signatures = {(p["flow"],tuple(p["nodes"])) for p in dependencies}
            after_signatures = {(p["flow"],tuple(p["nodes"])) for p in after_dependencies}
            disappeared = before_signatures - after_signatures
            lost_flows = {flow for flow,_ in disappeared}
            values = {p["flow"]:p["value"] for p in dependencies}
            result = {"status":"contained_on_modeled_snapshot" if not remaining else "incomplete_containment",
                      "contained":not bool(remaining),"original_routes":len(original),
                      "remaining_routes":len(remaining),"remaining_paths":remaining,
                      "affected_flows":sorted(lost_flows),
                      "modeled_disruption_cost":sum(values[f] for f in lost_flows)}
        result.update({"action_ids":action_ids,"simulation":"FalkorDB clone: actual Cypher DELETE + re-traversal",
            "boundary":"Synthetic graph, bounded to 7 hops. No production infrastructure changed; not a real-world safety certificate."})
    finally:
        # Do not leave per-session topology clones holding sensitive data.
        sim.delete()
    store.handoff(tenant,session_id,"sandbox","replayed",result)
    return result
