"""FalkorDB is the only production source of topology, candidates and memory.

No SQLite, JSON state, or vector-store fallback is used by the service.
"""
import json
import re
import uuid
from datetime import datetime, timezone

from falkordb import FalkorDB

TENANT = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


def iso_now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, host="localhost", port=6379, password=None):
        self.db = FalkorDB(host=host, port=int(port), password=password)

    def graphs(self, tenant):
        if not TENANT.fullmatch(tenant):
            raise ValueError("Invalid tenant. Use 1-32 lowercase alphanumeric characters, '_' or '-'.")
        return (self.db.select_graph(f"maelin_{tenant}_topology"),
                self.db.select_graph(f"maelin_{tenant}_memory"))

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

    def attack_paths(self, tenant, source, vulnerable, target):
        g, _ = self.graphs(tenant)
        # Bounded enumeration rather than shortestPath, which can omit
        # dangerous longer routes when a shorter benign route exists.
        query = """MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots LIMIT 257"""
        rows = g.ro_query(query, {"source":source,"vulnerable":vulnerable,"target":target}).result_set
        if len(rows) > 256:
            raise OverflowError("More than 256 candidate attack paths. No containment conclusion is safe.")
        return [{"nodes":r[0],"edges":r[1]} for r in rows]

    def business_paths(self, tenant):
        g, _ = self.graphs(tenant)
        q = """MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id] LIMIT 1025"""
        rows = g.ro_query(q).result_set
        if len(rows) > 1024:
            raise OverflowError("Business dependency enumeration exceeded limit; refuse plan scoring.")
        return [{"flow":r[0],"value":r[1],"nodes":r[2]} for r in rows]

    def interventions(self, tenant):
        g, _ = self.graphs(tenant)
        rows = g.ro_query("""MATCH (a:Intervention)
RETURN a.id, a.label, a.blocked_nodes, a.blocked_edges, a.cost, a.note
ORDER BY a.id""").result_set
        return [{"id":r[0],"label":r[1],"blocked_nodes":r[2] or [],
                 "blocked_edges":r[3] or [],"cost":r[4],"note":r[5]} for r in rows]

    def recall(self, tenant, fingerprint):
        _, g = self.graphs(tenant)
        rows = g.ro_query("""MATCH (e:Episode {fingerprint:$fingerprint})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 30""", {"fingerprint":fingerprint}).result_set
        return [{"action_id":r[0],"outcome":r[1],"cost_observed":r[2],
                 "evidence_status":r[3],"created":r[4],"episode_id":r[5]} for r in rows]

    def new_session(self, tenant, fingerprint):
        _, g = self.graphs(tenant)
        sid = str(uuid.uuid4())
        g.query("CREATE (:Session {id:$id, fingerprint:$fingerprint, created:$created})",
                {"id":sid,"fingerprint":fingerprint,"created":iso_now()})
        return sid

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

    def record_outcome(self, tenant, session, fingerprint, action_id, outcome, cost, note):
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
        verified = g.ro_query("""MATCH (s:Session {id:$session, fingerprint:$fingerprint})
-[:RESULTED_IN]->(e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed""",
            {"session":session,"fingerprint":fingerprint,"episode":episode}).result_set
        if verified != [[action_id, outcome, cost]]:
            raise ValueError("Outcome not persisted for the specified session and fingerprint")
        return episode

    def inject_shadow_route(self, tenant):
        """Controlled synthetic fault injection. Never modifies cloud infrastructure."""
        if tenant not in {"alpha", "beta", "ci_alpha", "ci_beta"}:
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
            topology.query("""CREATE (:Asset {id:$id, kind:$kind, x:$x, y:$y, value:$value, critical:$critical})""",
                {"id":a["id"],"kind":a["kind"],"x":a["x"],"y":a["y"],
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
