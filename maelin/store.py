"""FalkorDB is the only production source of topology, candidates and memory.

No SQLite, JSON state, or vector-store fallback is used by the service.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

from falkordb import FalkorDB

TENANT = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def _format_nodes(nodes):
    if not isinstance(nodes, (list, tuple)):
        return nodes
    out = []
    for n in nodes:
        if hasattr(n, "properties"):
            p = dict(n.properties)
            nid = p.get("id")
            if nid is None:
                nid = getattr(n, "id", None)
            if nid is not None:
                p.setdefault("id", nid)
            if hasattr(n, "labels") and n.labels:
                p.setdefault("labels", list(n.labels))
            out.append(p)
        elif isinstance(n, dict):
            out.append(n)
        else:
            out.append({"id": str(n)})
    return out


def _format_rels(rels):
    if not isinstance(rels, (list, tuple)):
        return rels
    out = []
    for r in rels:
        if hasattr(r, "properties"):
            p = dict(r.properties)
            eid = p.get("edge_id")
            if eid is None:
                eid = getattr(r, "id", None)
            if eid is not None:
                p.setdefault("edge_id", eid)
            rel_type = getattr(r, "relation", None) or getattr(r, "type", None)
            if rel_type:
                p.setdefault("relation", rel_type)
            src = getattr(r, "src_node", None)
            dest = getattr(r, "dest_node", None)
            if src is not None:
                src_id = src.properties.get("id") if hasattr(src, "properties") else getattr(src, "id", None)
                if src_id is not None:
                    p.setdefault("from", src_id)
            if dest is not None:
                dest_id = dest.properties.get("id") if hasattr(dest, "properties") else getattr(dest, "id", None)
                if dest_id is not None:
                    p.setdefault("to", dest_id)
            out.append(p)
        elif isinstance(r, dict):
            out.append(r)
        else:
            out.append({"edge_id": str(r)})
    return out


class Store:
    def __init__(self, host="localhost", port=6379, password=None):
        self.db = FalkorDB(host=host, port=int(port), password=password,
                           username=os.getenv("FALKOR_USERNAME") or None,
                           ssl=os.getenv("FALKOR_SSL","0").lower() in {"1","true","yes"})

    def graphs(self, tenant):
        if not TENANT.fullmatch(tenant):
            raise ValueError("Invalid tenant. Use 1-32 lowercase alphanumeric characters, '_' or '-'.")
        return (self.db.select_graph(f"maelin_{tenant}_topology"),
                self.db.select_graph(f"maelin_{tenant}_memory"))

    def get_topology_graph(self, tenant: str):
        topology, _ = self.graphs(tenant)
        return topology

    def compute_asset_centrality(self, tenant: str) -> list[dict]:
        graph = self.get_topology_graph(tenant)
        res = graph.query(
            "CALL algo.pageRank('Asset', 'DEPENDS_ON') "
            "YIELD node, score "
            "RETURN node.id AS asset_id, node.role AS role, score "
            "ORDER BY score DESC"
        )
        return [{"asset_id": r[0], "role": r[1], "centrality_score": round(float(r[2]), 4)} for r in res.result_set]

    def team_ownership(self, tenant: str, asset_id: str | None = None) -> list[dict]:
        g, _ = self.graphs(tenant)
        if asset_id:
            rows = g.ro_query("""MATCH (t:Team)-[:OWNS]->(a:Asset {id:$asset_id})
RETURN t.id, t.name, t.lead, t.contact, a.id""", {"asset_id":asset_id}).result_set
        else:
            rows = g.ro_query("""MATCH (t:Team)-[:OWNS]->(a:Asset)
RETURN t.id, t.name, t.lead, t.contact, a.id ORDER BY t.id, a.id""").result_set
        return [{"team_id":r[0], "team_name":r[1], "lead":r[2], "contact":r[3], "asset_id":r[4]} for r in rows]

    def ready(self, tenant):
        topology, _ = self.graphs(tenant)
        # GRAPH.RO_QUERY on a graph that does not exist may raise an error.
        # GRAPH.LIST distinguishes an unseeded tenant from a broken connection.
        if f"maelin_{tenant}_topology" not in self.db.list_graphs():
            return False
        return bool(topology.ro_query("MATCH (n:Asset) RETURN n.id LIMIT 1").result_set)

    def topology(self, tenant):
        g, _ = self.graphs(tenant)
        ns = g.ro_query("MATCH (n:Asset) RETURN n.id, n.kind, n.x, n.y, coalesce(n.value, 0)").result_set
        es = g.ro_query("MATCH (a:Asset)-[r:CAN_PIVOT|DEPENDS_ON]->(b:Asset) RETURN a.id, b.id, type(r), r.edge_id").result_set
        return {
            "nodes": [{"id":n[0],"kind":n[1],"x":n[2],"y":n[3],"value":n[4]} for n in ns],
            "edges": [{"from":e[0],"to":e[1],"kind":e[2],"id":e[3]} for e in es],
        }

    def graph_scene(self, tenant):
        """Read the uploaded incident's defaults from the real topology graph."""
        g, _ = self.graphs(tenant)
        rows = g.ro_query("""MATCH (m:GraphMetadata)
RETURN m.source, m.vulnerable, m.target, m.fingerprint, m.scenario LIMIT 2""").result_set
        if len(rows) > 1:
            raise ValueError("Ambiguous graph metadata")
        if not rows:
            # Existing, already seeded demo graphs predate GraphMetadata.
            from .seed import dataset
            return dataset()
        row = rows[0]
        return {"source":row[0], "vulnerable":row[1], "target":row[2],
                "fingerprint":row[3], "scenario":row[4]}

    def attack_paths(self, tenant, source, vulnerable, target):
        g, _ = self.graphs(tenant)
        # Bounded enumeration rather than shortestPath, which can omit
        # dangerous longer routes when a shorter benign route exists.
        # Explicitly return nodes(p) and relationships(p) in a single query
        # for full hop-by-hop provenance.
        query = """MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots,
       [r IN relationships(p) | r.evidence] AS edge_evidence,
       nodes(p) AS path_nodes,
       relationships(p) AS path_relationships LIMIT 257"""
        rows = g.ro_query(query, {"source":source,"vulnerable":vulnerable,"target":target}).result_set
        if len(rows) > 256:
            raise OverflowError("More than 256 candidate attack paths. No containment conclusion is safe.")
        return [{"nodes": r[0] if isinstance(r[0], list) else [r[0]],
                 "edges": r[1] if isinstance(r[1], list) else [r[1]],
                 "edge_evidence": r[2] if len(r) > 2 and r[2] is not None and isinstance(r[2], list) else [],
                 "path_nodes": _format_nodes(r[3]) if len(r) > 3 and r[3] is not None else (r[0] if isinstance(r[0], list) else [r[0]]),
                 "path_relationships": _format_rels(r[4]) if len(r) > 4 and r[4] is not None else (r[1] if isinstance(r[1], list) else [r[1]])}
                for r in rows]

    def business_paths(self, tenant):
        g, _ = self.graphs(tenant)
        q = """MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id], nodes(p) AS path_nodes, relationships(p) AS path_relationships LIMIT 1025"""
        rows = g.ro_query(q).result_set
        if len(rows) > 1024:
            raise OverflowError("Business dependency enumeration exceeded limit; refuse plan scoring.")
        return [{"flow": r[0], "value": r[1], "nodes": r[2],
                 "path_nodes": _format_nodes(r[3]) if len(r) > 3 and r[3] is not None else r[2],
                 "path_relationships": _format_rels(r[4]) if len(r) > 4 and r[4] is not None else []}
                for r in rows]

    def interventions(self, tenant):
        g, _ = self.graphs(tenant)
        rows = g.ro_query("""MATCH (a:Intervention)
RETURN a.id, a.label, a.blocked_nodes, a.blocked_edges, a.cost, a.note
ORDER BY a.id""").result_set
        return [{"id":r[0],"label":r[1],"blocked_nodes":r[2] or [],
                 "blocked_edges":r[3] or [],"cost":r[4],"note":r[5]} for r in rows]

    def recall(self, tenant, fingerprint, semantic_key=None):
        _, g = self.graphs(tenant)
        rows = g.ro_query("""MATCH (p:IncidentPattern {fingerprint:$fingerprint})-[:HAS_EPISODE]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 30""", {"fingerprint":fingerprint}).result_set
        episodes = [{"action_id":r[0],"outcome":r[1],"cost_observed":r[2],
                     "evidence_status":r[3],"created":r[4],"episode_id":r[5],
                     "match_type":"exact", "memory_weight":1.0} for r in rows]
        if semantic_key:
            # A semantic graph pattern generalizes by role/kind rather than
            # incident ID. Similarity is deliberately discounted, and each
            # supporting action must still exist in the current action catalog.
            related = g.ro_query("""MATCH (k:SemanticPattern {key:$key})-[:REMEMBERS]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 20""", {"key":semantic_key}).result_set
            seen = {ep["episode_id"] for ep in episodes}
            episodes += [{"action_id":r[0],"outcome":r[1],"cost_observed":r[2],
                          "evidence_status":r[3],"created":r[4],"episode_id":r[5],
                          "match_type":"semantic", "memory_weight":0.25}
                         for r in related if r[5] not in seen]
        return episodes

    def new_session(self, tenant, fingerprint):
        _, g = self.graphs(tenant)
        sid = str(uuid.uuid4())
        g.query("CREATE (:Session {id:$id, fingerprint:$fingerprint, created:$created})",
                {"id":sid,"fingerprint":fingerprint,"created":iso_now()})
        return sid

    def set_session_scene(self, tenant, session, scene):
        _, g = self.graphs(tenant)
        g.query("""MATCH (s:Session {id:$session})
SET s.source=$source, s.vulnerable=$vulnerable, s.target=$target, s.scenario=$scenario,
 s.semantic_key=$semantic_key""",
                {"session":session, "source":scene["source"], "vulnerable":scene["vulnerable"],
                 "target":scene["target"], "scenario":scene["scenario"],
                 "semantic_key":scene.get("semantic_key","")})

    def session_scene(self, tenant, session):
        _, g = self.graphs(tenant)
        rows = g.ro_query("""MATCH (s:Session {id:$session})
RETURN s.source, s.vulnerable, s.target, s.fingerprint, s.scenario, s.semantic_key""",
                          {"session":session}).result_set
        if len(rows) != 1 or any(value is None for value in rows[0][:4]):
            raise ValueError("Unknown session or missing graph-bound incident context")
        row = rows[0]
        return {"source":row[0], "vulnerable":row[1], "target":row[2],
                "fingerprint":row[3], "scenario":row[4] or "Graph incident",
                "semantic_key":row[5] if len(row)>5 else None}

    def log_turn(self, tenant, session, role, content):
        """Append graph-backed conversation history; never keep chat as app state."""
        if role not in {"operator", "assistant", "system"}:
            raise ValueError("Invalid conversation role")
        _, graph = self.graphs(tenant)
        graph.query("""MATCH (s:Session {id:$session})
CREATE (s)-[:HAS_TURN]->(:ConversationTurn {id:$id, role:$role, text:$text, created:$created})""",
                    {"session":session,"id":str(uuid.uuid4()),"role":role,
                     "text":str(content)[:1200],"created":iso_now()})

    def conversation(self, tenant, session):
        _, graph = self.graphs(tenant)
        rows = graph.ro_query("""MATCH (s:Session {id:$session})-[:HAS_TURN]->(t:ConversationTurn)
RETURN t.role, t.text, t.created ORDER BY t.created""",
                               {"session":session}).result_set
        return [{"role":r[0], "text":r[1], "created":r[2]} for r in rows]

    def handoff(self, tenant, session, agent, status, payload):
        _, g = self.graphs(tenant)
        g.query("""MATCH (s:Session {id:$session})
CREATE (s)-[:HAS_HANDOFF]->(:Handoff {id:$id, agent:$agent, status:$status, created:$created, payload:$payload})""",
                {"session":session,"id":str(uuid.uuid4()),"agent":agent,
                 "status":status,"created":iso_now(),"payload":json.dumps(payload)})

    def proposed(self, tenant, session, proposals):
        _, g = self.graphs(tenant)
        # Each proposal is attached to a session: recorded outcomes must cite
        # an action that was actually offered in that session.
        for a in proposals:
            g.query("""MATCH (s:Session {id:$session})
MERGE (s)-[:PROPOSED]->(p:ProposedAction {id:$id})""",
                    {"session":session,"id":a})

    def session_actions(self, tenant, session):
        _, g = self.graphs(tenant)
        rows = g.ro_query("""MATCH (s:Session {id:$session})-[:PROPOSED]->(p:ProposedAction)
RETURN p.id""", {"session":session}).result_set
        return [r[0] for r in rows]

    def history(self, tenant, session):
        _, g = self.graphs(tenant)
        rows = g.ro_query("""MATCH (s:Session {id:$session})-[:HAS_HANDOFF]->(h:Handoff)
RETURN h.agent, h.status, h.payload, h.created ORDER BY h.created""", {"session":session}).result_set
        return [{"agent":r[0],"status":r[1],"payload":json.loads(r[2]),"created":r[3]} for r in rows]

    def record_outcome(self, tenant, session, fingerprint, action_id, outcome, cost, note, semantic_key=None):
        _, g = self.graphs(tenant)
        # An outcome has a stable key per session+action; repeated POSTs cannot
        # fabricate dozens of separate failures by retrying the same report.
        episode = f"{session}:{action_id}"
        # Explicitly reject contradictory repeated reports rather than returning
        # success while silently keeping the first value.
        previous = g.ro_query("""MATCH (e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
RETURN a.outcome, a.cost_observed, e.fingerprint""", {"episode":episode}).result_set
        if previous:
            if any(row != [outcome, cost, fingerprint] for row in previous):
                raise ValueError("Conflicting outcome report: this session/action is immutable")
            return episode
        g.query("""MATCH (s:Session {id:$session})
MERGE (e:Episode {id:$episode})
ON CREATE SET e.fingerprint=$fingerprint, e.created=$created, e.note=$note
MERGE (a:ActionExperience {key:$episode})
ON CREATE SET a.action_id=$action_id, a.outcome=$outcome,
 a.cost_observed=$cost, a.evidence_status='operator_report'
MERGE (s)-[:RESULTED_IN]->(e)
MERGE (e)-[:OBSERVED]->(a)""",
                {"session":session,"episode":episode,"fingerprint":fingerprint,
                 "created":iso_now(),"note":note,"action_id":action_id,"outcome":outcome,"cost":cost})
        # Procedural memory is an actual Cypher-queryable incident/action subgraph.
        # Only immutable episode evidence can support a reusable procedure.
        g.query("""MATCH (e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
MERGE (pattern:IncidentPattern {fingerprint:$fingerprint})
MERGE (procedure:Procedure {key:$procedure_key})
ON CREATE SET procedure.action_id=$action_id, procedure.review_policy='review_after_report'
MERGE (pattern)-[:HAS_EPISODE]->(e)
MERGE (pattern)-[:HAS_PROCEDURE]->(procedure)
MERGE (procedure)-[:SUPPORTED_BY]->(a)""",
                {"episode":episode,"fingerprint":fingerprint,
                 "procedure_key":fingerprint+":"+action_id,"action_id":action_id})
        if semantic_key:
            g.query("""MATCH (e:Episode {id:$episode})
MERGE (pattern:SemanticPattern {key:$semantic_key})
MERGE (pattern)-[:REMEMBERS]->(e)""",
                    {"episode":episode, "semantic_key":semantic_key})
        verified = g.ro_query("""MATCH (s:Session {id:$session, fingerprint:$fingerprint})
-[:RESULTED_IN]->(e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed""",
            {"session":session,"fingerprint":fingerprint,"episode":episode}).result_set
        if verified != [[action_id, outcome, cost]]:
            raise ValueError("Outcome not persisted for the specified session and fingerprint")
        return episode

    def inject_shadow_route(self, tenant):
        """Controlled synthetic fault injection. Never modifies cloud infrastructure."""
        if tenant not in {"alpha", "beta", "ci_alpha", "ci_beta"} and not re.fullmatch(r"judge_[0-9a-f]{8}", tenant):
            raise ValueError("Synthetic fault injection is restricted to demo tenants")
        if not self.ready(tenant):
            raise LookupError("Seed the demo before injecting faults")
        g, _ = self.graphs(tenant)
        g.query("""MERGE (n:Asset {id:'shadow-role'})
ON CREATE SET n.kind='identity', n.x=603, n.y=225, n.value=0, n.critical=false""")
        g.query("""MATCH (a:Asset {id:'auth-service'}), (b:Asset {id:'shadow-role'})
MERGE (a)-[r:CAN_PIVOT {edge_id:'p9'}]->(b)
ON CREATE SET r.evidence='synthetic newly-discovered privilege escalation'""")
        g.query("""MATCH (a:Asset {id:'shadow-role'}), (b:Asset {id:'customer-db'})
MERGE (a)-[r:CAN_PIVOT {edge_id:'p10'}]->(b)
ON CREATE SET r.evidence='synthetic newly-discovered database path'""")
        return {"injected_edges":["p9","p10"], "warning":"Synthetic topology modification only; previously complete plans may no longer cut every path."}

    def seed(self, tenant, data, reset=False):
        topology, memory = self.graphs(tenant)
        graph_names = set(self.db.list_graphs())
        if not reset and (f"maelin_{tenant}_topology" in graph_names or
                          f"maelin_{tenant}_memory" in graph_names):
            raise ValueError("Tenant graphs already exist. Supply --reset to deliberately replace demo data.")
        if reset:
            topology.query("MATCH (n) DETACH DELETE n")
            memory.query("MATCH (n) DETACH DELETE n")
        for a in data["assets"]:
            topology.query("""CREATE (:Asset {id:$id, kind:$kind, role:$role, x:$x, y:$y, value:$value, critical:$critical})""",
                {"id":a["id"],"kind":a["kind"],"role":a.get("role", a.get("kind", "asset")),"x":a["x"],"y":a["y"],
                 "value":a.get("value",0),"critical":a.get("critical",False)})
        for typ, field in (("CAN_PIVOT","pivot_edges"),("DEPENDS_ON","depends_edges")):
            # Only code-owned relationship type identifiers, never untrusted strings.
            for e in data[field]:
                topology.query(f"""MATCH (a:Asset {{id:$source}}), (b:Asset {{id:$target}})
CREATE (a)-[:{typ} {{edge_id:$edge_id, evidence:$evidence}}]->(b)""",
                {"source":e["from"],"target":e["to"],"edge_id":e["id"],
                 "evidence":e.get("evidence","synthetic business dependency")})
        for a in data["actions"]:
            topology.query("""CREATE (:Intervention {id:$id, label:$label,
blocked_nodes:$blocked_nodes, blocked_edges:$blocked_edges, cost:$cost, note:$note})""", a)
        for team in data.get("teams", []):
            topology.query("""CREATE (:Team {id:$id, name:$name, lead:$lead, contact:$contact})""",
                {"id":team["id"], "name":team.get("name", team["id"]),
                 "lead":team.get("lead", ""), "contact":team.get("contact", "")})
        for own in data.get("team_ownership", []):
            topology.query("""MATCH (t:Team {id:$team}), (a:Asset {id:$asset})
CREATE (t)-[:OWNS]->(a)""",
                {"team":own["team"], "asset":own["asset"]})
        topology.query("""CREATE (:GraphMetadata {
source:$source, vulnerable:$vulnerable, target:$target,
fingerprint:$fingerprint, scenario:$scenario})""",
            {"source":data["source"],"vulnerable":data["vulnerable"],"target":data["target"],
             "fingerprint":data["fingerprint"],"scenario":data["scenario"]})
