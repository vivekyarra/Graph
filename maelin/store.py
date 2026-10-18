"""FalkorDB is the only production source of topology, candidates and memory.

No SQLite, JSON state, or vector-store fallback is used by the service.

Read paths go through ``GRAPH.RO_QUERY`` (``_ro``) and every write through
``GRAPH.QUERY`` (``_rw``); both are instrumented so the API can surface an
exact FalkorDB execution trace with server-side ``run_time_ms``.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

from falkordb import FalkorDB
from .telemetry import traced_query

TENANT = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
EMBED_KINDS = ("ingress", "service", "identity", "database", "business_flow")
VECTOR_DIM = len(EMBED_KINDS) * 3  # 15; kept as a literal in DDL (see ensure_indexes)


def incident_embedding(semantic_key):
    """Structural incident embedding: one-hot asset kind of the entry point,
    the compromised pivot and the target. Similar topologies land close
    together in FalkorDB's vector index even when their IDs differ."""
    parts = (semantic_key or "").split("|")
    if len(parts) != 3:
        return None
    vec = []
    for kind in parts:
        vec += [1.0 if kind == k else 0.0 for k in EMBED_KINDS]
    return vec if any(vec) else None


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

    # ------------------------------------------------------------------
    # Traced query boundary. Reconnaissance is *protocol-level* read-only:
    # GRAPH.RO_QUERY is rejected by FalkorDB if the statement would write.
    # ------------------------------------------------------------------
    def _ro(self, graph, cypher, params=None, agent="Recon & Graph Mapper", evidence=None):
        return traced_query(graph, cypher, params, agent_name=agent,
                            query_type="ro_query", evidence_id=evidence)

    def _rw(self, graph, cypher, params=None, agent="Episodic Memory Coordinator"):
        return traced_query(graph, cypher, params, agent_name=agent,
                            query_type="query")

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
        res = self._ro(graph,
            "CALL algo.pageRank('Asset', 'DEPENDS_ON') "
            "YIELD node, score "
            "RETURN node.id AS asset_id, node.role AS role, score "
            "ORDER BY score DESC")
        return [{"asset_id": r[0], "role": r[1], "centrality_score": round(float(r[2]), 4)} for r in res.result_set]

    def team_ownership(self, tenant: str, asset_id: str | None = None) -> list[dict]:
        g, _ = self.graphs(tenant)
        if asset_id:
            rows = self._ro(g, """MATCH (t:Team)-[:OWNS]->(a:Asset {id:$asset_id})
RETURN t.id, t.name, t.lead, t.contact, a.id""", {"asset_id":asset_id}).result_set
        else:
            rows = self._ro(g, """MATCH (t:Team)-[:OWNS]->(a:Asset)
RETURN t.id, t.name, t.lead, t.contact, a.id ORDER BY t.id, a.id""").result_set
        return [{"team_id":r[0], "team_name":r[1], "lead":r[2], "contact":r[3], "asset_id":r[4]} for r in rows]

    def ready(self, tenant):
        topology, _ = self.graphs(tenant)
        # GRAPH.RO_QUERY on a graph that does not exist may raise an error.
        # GRAPH.LIST distinguishes an unseeded tenant from a broken connection.
        if f"maelin_{tenant}_topology" not in self.db.list_graphs():
            return False
        return bool(self._ro(topology, "MATCH (n:Asset) RETURN n.id LIMIT 1").result_set)

    def topology(self, tenant):
        g, _ = self.graphs(tenant)
        ns = self._ro(g, "MATCH (n:Asset) RETURN n.id, n.kind, n.x, n.y, coalesce(n.value, 0)").result_set
        es = self._ro(g, "MATCH (a:Asset)-[r:CAN_PIVOT|DEPENDS_ON]->(b:Asset) RETURN a.id, b.id, type(r), r.edge_id").result_set
        return {
            "nodes": [{"id":n[0],"kind":n[1],"x":n[2],"y":n[3],"value":n[4]} for n in ns],
            "edges": [{"from":e[0],"to":e[1],"kind":e[2],"id":e[3]} for e in es],
        }

    def graph_scene(self, tenant):
        """Read the uploaded incident's defaults from the real topology graph."""
        g, _ = self.graphs(tenant)
        rows = self._ro(g, """MATCH (m:GraphMetadata)
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
        rows = self._ro(g, query, {"source":source,"vulnerable":vulnerable,"target":target},
                        evidence="[E1]").result_set
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
        rows = self._ro(g, q, evidence="[E2]").result_set
        if len(rows) > 1024:
            raise OverflowError("Business dependency enumeration exceeded limit; refuse plan scoring.")
        return [{"flow": r[0], "value": r[1], "nodes": r[2],
                 "path_nodes": _format_nodes(r[3]) if len(r) > 3 and r[3] is not None else r[2],
                 "path_relationships": _format_rels(r[4]) if len(r) > 4 and r[4] is not None else []}
                for r in rows]

    def interventions(self, tenant):
        g, _ = self.graphs(tenant)
        rows = self._ro(g, """MATCH (a:Intervention)
RETURN a.id, a.label, a.blocked_nodes, a.blocked_edges, a.cost, a.note
ORDER BY a.id""", evidence="[E4]").result_set
        return [{"id":r[0],"label":r[1],"blocked_nodes":r[2] or [],
                 "blocked_edges":r[3] or [],"cost":r[4],"note":r[5]} for r in rows]

    def recall(self, tenant, fingerprint, semantic_key=None):
        _, g = self.graphs(tenant)
        rows = self._ro(g, """MATCH (p:IncidentPattern {fingerprint:$fingerprint})-[:HAS_EPISODE]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 30""", {"fingerprint":fingerprint}, evidence="[E5]").result_set
        episodes = [{"action_id":r[0],"outcome":r[1],"cost_observed":r[2],
                     "evidence_status":r[3],"created":r[4],"episode_id":r[5],
                     "match_type":"exact", "memory_weight":1.0} for r in rows]
        if semantic_key:
            # A semantic graph pattern generalizes by role/kind rather than
            # incident ID. Similarity is deliberately discounted, and each
            # supporting action must still exist in the current action catalog.
            related = self._ro(g, """MATCH (k:SemanticPattern {key:$key})-[:REMEMBERS]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 20""", {"key":semantic_key}).result_set
            seen = {ep["episode_id"] for ep in episodes}
            episodes += [{"action_id":r[0],"outcome":r[1],"cost_observed":r[2],
                          "evidence_status":r[3],"created":r[4],"episode_id":r[5],
                          "match_type":"semantic", "memory_weight":0.25}
                         for r in related if r[5] not in seen]
            episodes += self._vector_recall(g, semantic_key, {ep["episode_id"] for ep in episodes})
        return episodes

    def _vector_recall(self, graph, semantic_key, seen, k=8, min_similarity=0.6):
        """Nearest-neighbour recall over the Episode vector index."""
        vec = incident_embedding(semantic_key)
        if vec is None:
            return []
        try:
            rows = self._ro(graph, """CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($vec))
YIELD node, score
MATCH (node)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, node.created, node.id, score""",
                {"k":k, "vec":vec}).result_set
        except Exception as exc:
            # Graphs seeded before the vector index existed simply have no vectors.
            if "index" in str(exc).lower():
                return []
            raise
        out = []
        for r in rows:
            similarity = round(1 - float(r[6]), 3)  # cosine distance -> similarity
            if r[5] in seen or similarity < min_similarity:
                continue
            seen.add(r[5])
            out.append({"action_id":r[0], "outcome":r[1], "cost_observed":r[2],
                        "evidence_status":r[3], "created":r[4], "episode_id":r[5],
                        "match_type":"vector", "similarity":similarity,
                        "memory_weight":round(0.25 * similarity, 3)})
        return out

    def new_session(self, tenant, fingerprint):
        _, g = self.graphs(tenant)
        sid = str(uuid.uuid4())
        self._rw(g, "CREATE (:Session {id:$id, fingerprint:$fingerprint, created:$created})",
                 {"id":sid,"fingerprint":fingerprint,"created":iso_now()})
        return sid

    def set_session_scene(self, tenant, session, scene):
        _, g = self.graphs(tenant)
        self._rw(g, """MATCH (s:Session {id:$session})
SET s.source=$source, s.vulnerable=$vulnerable, s.target=$target, s.scenario=$scenario,
 s.semantic_key=$semantic_key""",
                 {"session":session, "source":scene["source"], "vulnerable":scene["vulnerable"],
                  "target":scene["target"], "scenario":scene["scenario"],
                  "semantic_key":scene.get("semantic_key","")})

    def session_scene(self, tenant, session):
        _, g = self.graphs(tenant)
        rows = self._ro(g, """MATCH (s:Session {id:$session})
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
        self._rw(graph, """MATCH (s:Session {id:$session})
CREATE (s)-[:HAS_TURN]->(:ConversationTurn {id:$id, role:$role, text:$text, created:$created})""",
                 {"session":session,"id":str(uuid.uuid4()),"role":role,
                  "text":str(content)[:1200],"created":iso_now()})

    def conversation(self, tenant, session):
        _, graph = self.graphs(tenant)
        rows = self._ro(graph, """MATCH (s:Session {id:$session})-[:HAS_TURN]->(t:ConversationTurn)
RETURN t.role, t.text, t.created ORDER BY t.created""",
                        {"session":session}).result_set
        return [{"role":r[0], "text":r[1], "created":r[2]} for r in rows]

    def handoff(self, tenant, session, agent, status, payload):
        _, g = self.graphs(tenant)
        self._rw(g, """MATCH (s:Session {id:$session})
CREATE (s)-[:HAS_HANDOFF]->(:Handoff {id:$id, agent:$agent, status:$status, created:$created, payload:$payload})""",
                 {"session":session,"id":str(uuid.uuid4()),"agent":agent,
                  "status":status,"created":iso_now(),"payload":json.dumps(payload)})

    def proposed(self, tenant, session, proposals):
        _, g = self.graphs(tenant)
        # Each proposal is attached to a session: recorded outcomes must cite
        # an action that was actually offered in that session.
        for a in proposals:
            self._rw(g, """MATCH (s:Session {id:$session})
MERGE (s)-[:PROPOSED]->(p:ProposedAction {id:$id})""",
                     {"session":session,"id":a})

    def session_actions(self, tenant, session):
        _, g = self.graphs(tenant)
        rows = self._ro(g, """MATCH (s:Session {id:$session})-[:PROPOSED]->(p:ProposedAction)
RETURN p.id""", {"session":session}).result_set
        return [r[0] for r in rows]

    def history(self, tenant, session):
        _, g = self.graphs(tenant)
        rows = self._ro(g, """MATCH (s:Session {id:$session})-[:HAS_HANDOFF]->(h:Handoff)
RETURN h.agent, h.status, h.payload, h.created ORDER BY h.created""", {"session":session}).result_set
        return [{"agent":r[0],"status":r[1],"payload":json.loads(r[2]),"created":r[3]} for r in rows]

    def record_outcome(self, tenant, session, fingerprint, action_id, outcome, cost, note,
                       semantic_key=None, mttr_seconds=None, paths_severed=None):
        """Persist an immutable episode and its reusable, ranked playbook.

        ``:Episode`` carries the quantitative incident context, and
        ``[:RESOLVED_BY {mttr_seconds, verified_by_agent, paths_severed}]``
        links it to a ``:Playbook`` so later sessions can recall proven actions.
        Quantities not supplied by the caller are derived from the graph, never
        invented: severance from the recorded action, MTTR from session age.
        """
        _, g = self.graphs(tenant)
        # An outcome has a stable key per session+action; repeated POSTs cannot
        # fabricate dozens of separate failures by retrying the same report.
        episode = f"{session}:{action_id}"
        # Explicitly reject contradictory repeated reports rather than returning
        # success while silently keeping the first value.
        previous = self._ro(g, """MATCH (e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
RETURN a.outcome, a.cost_observed, e.fingerprint""", {"episode":episode}).result_set
        if previous:
            if any(row != [outcome, cost, fingerprint] for row in previous):
                raise ValueError("Conflicting outcome report: this session/action is immutable")
            return episode
        service_tier = self._service_tier(g, session)
        if paths_severed is None:
            paths_severed = self._paths_severed(g, session, action_id)
        if mttr_seconds is None:
            mttr_seconds = self._session_age_seconds(g, session)
        self._rw(g, """MATCH (s:Session {id:$session})
MERGE (e:Episode {id:$episode})
ON CREATE SET e.fingerprint=$fingerprint, e.created=$created, e.note=$note,
 e.cve_id=$fingerprint, e.service_tier=$service_tier,
 e.paths_severed=$paths_severed, e.timestamp=$created
MERGE (a:ActionExperience {key:$episode})
ON CREATE SET a.action_id=$action_id, a.outcome=$outcome,
 a.cost_observed=$cost, a.evidence_status='operator_report'
MERGE (s)-[:RESULTED_IN]->(e)
MERGE (s)-[:RECORDED]->(e)
MERGE (e)-[:OBSERVED]->(a)""",
                 {"session":session,"episode":episode,"fingerprint":fingerprint,
                  "created":iso_now(),"note":note,"action_id":action_id,"outcome":outcome,"cost":cost,
                  "service_tier":service_tier,"paths_severed":int(paths_severed)})
        # Procedural memory is an actual Cypher-queryable incident/action subgraph.
        # Only immutable episode evidence can support a reusable procedure.
        self._rw(g, """MATCH (e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
MERGE (pattern:IncidentPattern {fingerprint:$fingerprint})
MERGE (procedure:Procedure {key:$procedure_key})
ON CREATE SET procedure.action_id=$action_id, procedure.review_policy='review_after_report'
MERGE (pattern)-[:HAS_EPISODE]->(e)
MERGE (pattern)-[:HAS_PROCEDURE]->(procedure)
MERGE (procedure)-[:SUPPORTED_BY]->(a)""",
                 {"episode":episode,"fingerprint":fingerprint,
                  "procedure_key":fingerprint+":"+action_id,"action_id":action_id})
        # Cross-session recall: a reusable Playbook reached through RESOLVED_BY.
        self._rw(g, """MATCH (e:Episode {id:$episode}), (a:ActionExperience {key:$episode})
MERGE (pb:Playbook {action_id:$action_id})
ON CREATE SET pb.command=$command, pb.description=$description
MERGE (e)-[r:RESOLVED_BY]->(pb)
ON CREATE SET r.mttr_seconds=$mttr_seconds, r.verified_by_agent=$verified_by_agent,
 r.paths_severed=$paths_severed""",
                 {"episode":episode,"action_id":action_id,
                  "command":"maelin:playbook:"+action_id,
                  "description":"Playbook for "+action_id+" (synthetic action catalog)",
                  "mttr_seconds":int(mttr_seconds),"verified_by_agent":"operator_report",
                  "paths_severed":int(paths_severed)})
        if semantic_key:
            self._rw(g, """MATCH (e:Episode {id:$episode})
MERGE (pattern:SemanticPattern {key:$semantic_key})
MERGE (pattern)-[:REMEMBERS]->(e)""",
                     {"episode":episode, "semantic_key":semantic_key})
            vec = incident_embedding(semantic_key)
            if vec is not None:
                self._rw(g, "MATCH (e:Episode {id:$episode}) SET e.embedding = vecf32($vec)",
                         {"episode":episode, "vec":vec})
        verified = self._ro(g, """MATCH (s:Session {id:$session, fingerprint:$fingerprint})
-[:RESULTED_IN]->(e:Episode {id:$episode})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed""",
            {"session":session,"fingerprint":fingerprint,"episode":episode}).result_set
        if verified != [[action_id, outcome, cost]]:
            raise ValueError("Outcome not persisted for the specified session and fingerprint")
        return episode

    def _recon_payload(self, graph, session):
        """Latest Recon handoff payload; tolerant of old graphs and test doubles."""
        try:
            rows = self._ro(graph, """MATCH (s:Session {id:$session})-[:HAS_HANDOFF]->(h:Handoff {agent:'recon'})
RETURN h.payload ORDER BY h.created DESC LIMIT 1""", {"session":session}).result_set
        except Exception:
            return {}
        if not rows or not rows[0] or not rows[0][0]:
            return {}
        try:
            payload = json.loads(rows[0][0])
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _service_tier(self, graph, session):
        """Asset kind (tier) of the compromised service, from Recon's handoff."""
        payload = self._recon_payload(graph, session)
        return (payload.get("service_tier") or payload.get("vulnerable_kind")
                or "service")

    def _paths_severed(self, graph, session, action_id):
        """Exploit paths the recorded action actually cut, from the Recon handoff."""
        payload = self._recon_payload(graph, session)
        action = next((a for a in payload.get("interventions", [])
                       if a.get("id") == action_id), None)
        paths = payload.get("verified_path_payload") or []
        if action is None:
            return 0
        nodes = set(action.get("blocked_nodes") or [])
        edges = set(action.get("blocked_edges") or [])
        return sum(1 for p in paths
                   if nodes.intersection(p.get("nodes") or [])
                   or edges.intersection(p.get("edges") or []))

    def _session_age_seconds(self, graph, session):
        try:
            rows = self._ro(graph, "MATCH (s:Session {id:$session}) RETURN s.created",
                            {"session":session}).result_set
        except Exception:
            return 0
        if not rows or not rows[0] or not rows[0][0]:
            return 0
        try:
            created = datetime.fromisoformat(str(rows[0][0]))
        except ValueError:
            return 0
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - created).total_seconds()))

    def recall_proven_playbook(self, tenant, cve_id, service_tier, limit=3):
        """Rank reusable playbooks by how often they resolved similar episodes.

        ``cve_id`` matches the graph's incident fingerprint (this synthetic
        topology models no CVE nodes); ``service_tier`` matches the asset kind
        of the compromised service captured on the Episode.

        Only episodes whose recorded action was reported ``safe`` count as
        *proven*: an action that caused an outage resolved nothing.
        """
        _, g = self.graphs(tenant)
        rows = self._ro(g, """MATCH (s:Session)-[:RECORDED]->(ep:Episode)-[r:RESOLVED_BY]->(pb:Playbook)
MATCH (ep)-[:OBSERVED]->(ax:ActionExperience {outcome:'safe'})
WHERE ep.cve_id = $cve_id OR ep.service_tier = $service_tier
RETURN pb.action_id AS playbook_id,
       pb.command AS remediation_cmd,
       count(DISTINCT ep) AS times_used,
       avg(r.mttr_seconds) AS avg_mttr_seconds,
       max(ep.timestamp) AS last_used_at
ORDER BY times_used DESC, avg_mttr_seconds ASC
LIMIT $limit""",
            {"cve_id":cve_id, "service_tier":service_tier, "limit":int(limit)},
            agent="Episodic Memory Coordinator", evidence="[E6]").result_set
        return [{"playbook_id":r[0], "remediation_cmd":r[1], "times_used":int(r[2]),
                 "avg_mttr_seconds":round(float(r[3]), 2) if r[3] is not None else None,
                 "last_used_at":r[4]} for r in rows]

    def inject_shadow_route(self, tenant):
        """Controlled synthetic fault injection. Never modifies cloud infrastructure."""
        if tenant not in {"alpha", "beta"} and not re.fullmatch(r"(ci_[a-z0-9_]{1,24}|judge_[0-9a-f]{8})", tenant):
            raise ValueError("Synthetic fault injection is restricted to demo tenants")
        if not self.ready(tenant):
            raise LookupError("Seed the demo before injecting faults")
        g, _ = self.graphs(tenant)
        self._rw(g, """MERGE (n:Asset {id:'shadow-role'})
ON CREATE SET n.kind='identity', n.x=603, n.y=225, n.value=0, n.critical=false""",
                 agent="Demo Sandbox")
        self._rw(g, """MATCH (a:Asset {id:'auth-service'}), (b:Asset {id:'shadow-role'})
MERGE (a)-[r:CAN_PIVOT {edge_id:'p9'}]->(b)
ON CREATE SET r.evidence='synthetic newly-discovered privilege escalation', r.cap=1""",
                 agent="Demo Sandbox")
        self._rw(g, """MATCH (a:Asset {id:'shadow-role'}), (b:Asset {id:'customer-db'})
MERGE (a)-[r:CAN_PIVOT {edge_id:'p10'}]->(b)
ON CREATE SET r.evidence='synthetic newly-discovered database path', r.cap=1""",
                 agent="Demo Sandbox")
        return {"injected_edges":["p9","p10"], "warning":"Synthetic topology modification only; previously complete plans may no longer cut every path."}

    def seed(self, tenant, data, reset=False):
        topology, memory = self.graphs(tenant)
        graph_names = set(self.db.list_graphs())
        if not reset and (f"maelin_{tenant}_topology" in graph_names or
                          f"maelin_{tenant}_memory" in graph_names):
            raise ValueError("Tenant graphs already exist. Supply --reset to deliberately replace demo data.")
        if reset:
            self._rw(topology, "MATCH (n) DETACH DELETE n", agent="Seed")
            self._rw(memory, "MATCH (n) DETACH DELETE n", agent="Seed")
        for a in data["assets"]:
            self._rw(topology, """CREATE (:Asset {id:$id, kind:$kind, role:$role, x:$x, y:$y, value:$value, critical:$critical})""",
                {"id":a["id"],"kind":a["kind"],"role":a.get("role", a.get("kind", "asset")),"x":a["x"],"y":a["y"],
                 "value":a.get("value",0),"critical":a.get("critical",False)}, agent="Seed")
        # Static statement per code-owned relationship type: identifiers are
        # never interpolated into Cypher, so no injection surface and the
        # FalkorDB plan cache is reused.
        pivot_stmt = """MATCH (a:Asset {id:$source}), (b:Asset {id:$target})
CREATE (a)-[:CAN_PIVOT {edge_id:$edge_id, evidence:$evidence, cap:1}]->(b)"""
        depends_stmt = """MATCH (a:Asset {id:$source}), (b:Asset {id:$target})
CREATE (a)-[:DEPENDS_ON {edge_id:$edge_id, evidence:$evidence, cap:1}]->(b)"""
        # cap:1 gives every pivot unit capacity for algo.maxFlow min-cut proofs.
        for typ, field in (("CAN_PIVOT", "pivot_edges"), ("DEPENDS_ON", "depends_edges")):
            statement = pivot_stmt if typ == "CAN_PIVOT" else depends_stmt
            for e in data[field]:
                self._rw(topology, statement,
                    {"source":e["from"],"target":e["to"],"edge_id":e["id"],
                     "evidence":e.get("evidence","synthetic business dependency")}, agent="Seed")
        for a in data["actions"]:
            self._rw(topology, """CREATE (:Intervention {id:$id, label:$label,
blocked_nodes:$blocked_nodes, blocked_edges:$blocked_edges, cost:$cost, note:$note})""", a, agent="Seed")
        for team in data.get("teams", []):
            self._rw(topology, """CREATE (:Team {id:$id, name:$name, lead:$lead, contact:$contact})""",
                {"id":team["id"], "name":team.get("name", team["id"]),
                 "lead":team.get("lead", ""), "contact":team.get("contact", "")}, agent="Seed")
        for own in data.get("team_ownership", []):
            self._rw(topology, """MATCH (t:Team {id:$team}), (a:Asset {id:$asset})
CREATE (t)-[:OWNS]->(a)""",
                {"team":own["team"], "asset":own["asset"]}, agent="Seed")
        for person in data.get("people", []):
            self._rw(topology, """MATCH (t:Team {id:$team})
CREATE (p:Person {id:$id, name:$name, title:$title, on_call:$on_call})-[:MEMBER_OF]->(t)""",
                {"id":person["id"], "name":person["name"], "team":person["team"],
                 "title":person.get("title", ""), "on_call":bool(person.get("on_call"))}, agent="Seed")
        for doc in data.get("documents", []):
            self._create_document(topology, doc)
        for dec in data.get("decisions", []):
            self._rw(topology, """MATCH (by:Person {id:$by}), (src:Document {id:$source})
CREATE (d:Decision {id:$id, title:$title, rationale:$rationale, created:$created})
CREATE (d)-[:DECIDED_BY]->(by), (d)-[:SOURCED_FROM]->(src)
WITH d UNWIND $about AS aid MATCH (a:Asset {id:aid}) CREATE (d)-[:AFFECTS]->(a)""",
                {"id":dec["id"], "title":dec["title"], "rationale":dec.get("rationale", ""),
                 "created":dec.get("created", ""), "by":dec["decided_by"], "source":dec["source"],
                 "about":dec.get("about", [])}, agent="Seed")
        self._rw(topology, """CREATE (:GraphMetadata {
source:$source, vulnerable:$vulnerable, target:$target,
fingerprint:$fingerprint, scenario:$scenario})""",
            {"source":data["source"],"vulnerable":data["vulnerable"],"target":data["target"],
             "fingerprint":data["fingerprint"],"scenario":data["scenario"]}, agent="Seed")
        self.ensure_indexes(tenant)

    # ------------------------------------------------------------------
    # Indexes: range indexes for every lookup key, full-text for the
    # Company Brain, and a vector index for semantic incident memory.
    # ------------------------------------------------------------------
    VECTOR_DIM = len(EMBED_KINDS) * 3

    def ensure_indexes(self, tenant):
        topology, memory = self.graphs(tenant)
        statements = [
            (topology, "CREATE INDEX FOR (a:Asset) ON (a.id)", "topology"),
            (topology, "CREATE INDEX FOR (t:Team) ON (t.id)", "topology"),
            (topology, "CREATE INDEX FOR (p:Person) ON (p.id)", "topology"),
            (topology, "CREATE INDEX FOR (d:Document) ON (d.id)", "topology"),
            (topology, "CREATE INDEX FOR (i:Intervention) ON (i.id)", "topology"),
            (topology, "CALL db.idx.fulltext.createNodeIndex('Document', 'title', 'body')", "topology"),
            (memory, "CREATE INDEX FOR (s:Session) ON (s.id)", "memory"),
            (memory, "CREATE INDEX FOR (e:Episode) ON (e.id)", "memory"),
            (memory, "CREATE INDEX FOR (pb:Playbook) ON (pb.action_id)", "memory"),
            (memory, "CREATE INDEX FOR (p:IncidentPattern) ON (p.fingerprint)", "memory"),
            # Dimension is a fixed literal: VECTOR_DIM is asserted in tests.
            (memory, "CREATE VECTOR INDEX FOR (e:Episode) ON (e.embedding) "
                     "OPTIONS {dimension:15, similarityFunction:'cosine'}", "memory"),
        ]
        for graph, statement, kind in statements:
            try:
                agent = "Seed" if kind == "topology" else "Episodic Memory Coordinator"
                self._rw(graph, statement, agent=agent)
            except Exception as exc:  # Index already exists: idempotent by design.
                if "already" not in str(exc).lower() and "exist" not in str(exc).lower():
                    raise

    @staticmethod
    def _create_document(graph, doc):
        traced_query(graph, """CREATE (d:Document {id:$id, kind:$kind, title:$title, body:$body,
created:$created, origin:$origin, episode_id:$episode_id})
WITH d OPTIONAL MATCH (p:Person {id:$author})
FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (d)-[:AUTHORED_BY]->(p))
WITH d UNWIND $about AS aid MATCH (a:Asset {id:aid}) CREATE (d)-[:ABOUT]->(a)""",
            {"id":doc["id"], "kind":doc["kind"], "title":doc["title"], "body":doc["body"],
             "created":doc.get("created", ""), "origin":doc.get("origin", "seeded"),
             "episode_id":doc.get("episode_id", ""), "author":doc.get("author") or "",
             "about":doc.get("about", [])},
            agent_name="Company Brain", query_type="query")

    # ------------------------------------------------------------------
    # Native FalkorDB graph algorithms used as agent tools.
    # ------------------------------------------------------------------
    def min_cut(self, tenant, vulnerable, target):
        """Menger bound via algo.maxFlow: fewest pivot cuts that separate the
        compromised asset from the target, plus one concrete minimum cut."""
        g, _ = self.graphs(tenant)
        if vulnerable == target:
            return {"max_flow": 0, "cut_edges": [], "algorithm": "algo.maxFlow"}
        rows = self._ro(g, """MATCH (s:Asset {id:$vulnerable}), (t:Asset {id:$target})
CALL algo.maxFlow({sourceNodes:[s], targetNodes:[t], capacityProperty:'cap',
                   nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT']})
YIELD edges, edgeFlows, maxFlow
RETURN [e IN edges | e.edge_id], edgeFlows, maxFlow""",
            {"vulnerable":vulnerable, "target":target},
            agent="Explainable Remediation", evidence="[E4]").result_set
        if not rows:
            return {"max_flow": 0, "cut_edges": [], "algorithm": "algo.maxFlow"}
        edge_ids, flows, max_flow = rows[0]
        flow = dict(zip(edge_ids or [], flows or []))
        pivots = self._ro(g, """MATCH (a:Asset)-[r:CAN_PIVOT]->(b:Asset)
RETURN r.edge_id, a.id, b.id, coalesce(r.cap, 1)""").result_set
        # Residual reachability from the source identifies the source side of
        # a minimum cut; saturated edges leaving it form the cut itself.
        residual = {}
        for eid, a, b, cap in pivots:
            used = flow.get(eid, 0)
            if used < cap:
                residual.setdefault(a, set()).add(b)
            if used > 0:
                residual.setdefault(b, set()).add(a)
        seen, stack = {vulnerable}, [vulnerable]
        while stack:
            for nxt in residual.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        cut = sorted(eid for eid, a, b, _ in pivots if a in seen and b not in seen)
        return {"max_flow": int(max_flow or 0), "cut_edges": cut, "algorithm": "algo.maxFlow"}

    def chokepoints(self, tenant, source=None, target=None, limit=5):
        """Rank assets by the share of entry->target attack routes they sit on
        (deterministic Cypher path counting), with seeded algo.betweenness on
        the CAN_PIVOT subgraph as a secondary structural signal."""
        g, _ = self.graphs(tenant)
        if source is None or target is None:
            scene = self.graph_scene(tenant)
            source, target = source or scene["source"], target or scene["target"]
        rows = self._ro(g, """MATCH p=(:Asset {id:$source})-[:CAN_PIVOT*1..7]->(:Asset {id:$target})
WITH p LIMIT 257
WITH collect(p) AS paths
WITH paths, size(paths) AS total
UNWIND paths AS p
UNWIND nodes(p)[1..-1] AS n
RETURN n.id, n.kind, count(*) AS routes, total
ORDER BY routes DESC, n.id LIMIT $limit""",
            {"source":source, "target":target, "limit":int(limit)}, evidence="[E3]").result_set
        between = {r[0]: round(float(r[1]), 3) for r in self._ro(g,
            """CALL algo.betweenness({nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT'],
samplingSize:4096, samplingSeed:42}) YIELD node, score RETURN node.id, score""").result_set}
        return [{"asset_id":r[0], "kind":r[1], "routes":r[2], "total_routes":r[3],
                 "route_share":round(r[2] / r[3], 3) if r[3] else 0,
                 "betweenness":between.get(r[0], 0.0)} for r in rows]

    # ------------------------------------------------------------------
    # Track 01 upgrade: choke-point cut math on the live topology graph.
    # The shipped topology models assets with a `kind` property rather than
    # distinct :Ingress / :Service / :IAMRole labels, so the queries use
    # kind predicates. Both statements are read-only and bounded.
    # ------------------------------------------------------------------
    BETWEENNESS = """CALL algo.betweenness(['Asset'], ['CAN_PIVOT'])
YIELD node, score
RETURN node.id AS service, coalesce(node.kind, 'service') AS tier, score
ORDER BY score DESC
LIMIT $limit"""

    CHOKEPOINT_CUT = """MATCH p = (ing:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(svc:Asset {kind:'service'})
                -[:CAN_PIVOT]->(iam:Asset {kind:'identity'})
WITH p, ing, svc, iam
WITH collect(p) AS all_paths, count(DISTINCT p) AS total_paths
UNWIND all_paths AS p
UNWIND nodes(p) AS n
WITH n, count(DISTINCT p) AS paths_through_node, total_paths,
     collect(DISTINCT nodes(p)[-1].id) AS target_roles
WHERE 'Asset' IN labels(n) AND n.kind = 'service'
RETURN n.id AS chokepoint_service,
       paths_through_node AS paths_severed,
       total_paths,
       (toFloat(paths_through_node) / toFloat(total_paths)) * 100.0 AS pct_blast_radius_eliminated,
       target_roles
ORDER BY paths_severed DESC
LIMIT $limit"""

    def critical_chokepoints(self, tenant, vulnerable=None, source=None, target=None, limit=5):
        """Betweenness ranking plus an attack-path cut simulation.

        Returns every service that sits on an ingress -> service -> identity
        route, with the number and percentage of distinct multi-hop exploit
        paths that isolating it would sever. A ``vulnerable`` asset is also
        scored against the same paths (direct choke-point cut math) even when
        no attack path traverses it.
        """
        g, _ = self.graphs(tenant)
        scene = None
        if source is None or target is None or vulnerable is None:
            scene = self.graph_scene(tenant)
        if scene is not None:
            source = source or scene["source"]
            target = target or scene["target"]
            vulnerable = vulnerable or scene["vulnerable"]

        betweenness, betweenness_available, betweenness_error = [], True, None
        try:
            betweenness = [
                {"service": r[0], "tier": r[1], "score": round(float(r[2]), 4)}
                for r in self._ro(g, self.BETWEENNESS, {"limit": int(limit)},
                                  evidence="[E3]").result_set
            ]
        except Exception as exc:
            # Betweenness is an optional structural signal. A server build
            # without the procedure, or a graph too small for sampling, must
            # not fail reconnaissance: the deterministic path-cut query below
            # stays authoritative and any real connection error resurfacing
            # there will still fail the request closed.
            betweenness, betweenness_available = [], False
            betweenness_error = f"{type(exc).__name__}: {exc}"[:300]

        try:
            rows = self._ro(g, self.CHOKEPOINT_CUT, {"limit": int(limit)},
                            agent="Explainable Remediation", evidence="[E3]").result_set
        except Exception:
            # Fallback: return path node lists and count in Python. This is a
            # query-shape fallback, not a hidden Python graph traversal of the
            # topology: every path still comes from FalkorDB.
            raw = self._ro(g, """MATCH p = (ing:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(svc:Asset {kind:'service'})
        -[:CAN_PIVOT]->(iam:Asset {kind:'identity'})
RETURN [n IN nodes(p) | n.id], [n IN nodes(p) | n.kind], nodes(p)[-1].id
LIMIT 257""", agent="Explainable Remediation", evidence="[E3]").result_set
            if len(raw) > 256:
                raise OverflowError("Chokepoint path enumeration exceeded 256 routes")
            rows = self._count_cuts(raw, limit)

        cuts = [{"service": r[0], "chokepoint_service": r[0],
                 "paths_severed": int(r[1]), "total_paths": int(r[2]),
                 "pct_blast_radius_eliminated": round(float(r[3]), 2),
                 "target_roles": list(r[4] or [])} for r in rows]
        cuts = self._ensure_vulnerable(cuts, g, vulnerable)
        scores = {b["service"]: b["score"] for b in betweenness}
        for cut in cuts:
            cut["betweenness"] = scores.get(cut["service"], 0.0)
        return {
            "source": source, "target": target, "vulnerable": vulnerable,
            "betweenness": betweenness,
            "betweenness_available": betweenness_available,
            "betweenness_error": betweenness_error,
            "chokepoints": cuts[:int(limit)],
            "algorithm": "algo.betweenness + bounded Cypher exploit-path cut simulation",
            "boundary": "Synthetic topology; severance counts are modeled, not observed.",
        }

    def _count_cuts(self, raw, limit):
        totals = len(raw)
        by_service = {}
        for nodes, kinds, role in raw:
            for node, kind in zip(nodes or [], kinds or []):
                if kind != "service":
                    continue
                entry = by_service.setdefault(node, {"paths": set(), "roles": set()})
                entry["paths"].add(tuple(nodes or []))
                entry["roles"].add(role)
        ranked = sorted(by_service.items(),
                        key=lambda kv: (-len(kv[1]["paths"]), kv[0]))[:int(limit)]
        return [[service, len(data["paths"]), totals,
                 (100.0 * len(data["paths"]) / totals) if totals else 0.0,
                 sorted(r for r in data["roles"] if r)] for service, data in ranked]

    def _ensure_vulnerable(self, cuts, graph, vulnerable):
        if not vulnerable or any(c["service"] == vulnerable for c in cuts):
            return cuts
        rows = self._ro(graph, """MATCH p = (ing:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(:Asset {kind:'identity'})
WITH p, [n IN nodes(p) | n.id] AS ids, nodes(p)[-1].id AS role
WHERE $vulnerable IN ids
RETURN count(DISTINCT p), collect(DISTINCT role)""", {"vulnerable": vulnerable},
            agent="Explainable Remediation", evidence="[E3]").result_set
        severed, roles = (rows[0][0], rows[0][1]) if rows else (0, [])
        total_rows = self._ro(graph, """MATCH p = (:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(:Asset {kind:'identity'})
RETURN count(p)""").result_set
        total = int(total_rows[0][0]) if total_rows else 0
        if not total:
            return cuts
        cuts.append({"service": vulnerable, "chokepoint_service": vulnerable,
                     "paths_severed": int(severed), "total_paths": total,
                     "pct_blast_radius_eliminated": round(100.0 * severed / total, 2),
                     "target_roles": sorted(r for r in (roles or []) if r),
                     "betweenness": 0.0})
        cuts.sort(key=lambda c: (-c["paths_severed"], c["service"]))
        return cuts

    def blast_radius(self, tenant, asset_id):
        """Customer flows that transitively depend on an asset (reverse DEPENDS_ON)."""
        g, _ = self.graphs(tenant)
        rows = self._ro(g, """MATCH (f:Asset {kind:'business_flow'})-[:DEPENDS_ON*1..7]->(a:Asset {id:$id})
RETURN DISTINCT f.id, coalesce(f.value, 0) ORDER BY f.id""", {"id":asset_id}).result_set
        return [{"flow":r[0], "value":r[1]} for r in rows]

    def stats(self, tenant):
        topology, memory = self.graphs(tenant)
        names = set(self.db.list_graphs())
        def count(graph, name, query):
            return self._ro(graph, query).result_set[0][0] if name in names else 0
        t, m = f"maelin_{tenant}_topology", f"maelin_{tenant}_memory"
        return {
            "topology_nodes": count(topology, t, "MATCH (n) RETURN count(n)"),
            "topology_edges": count(topology, t, "MATCH ()-[r]->() RETURN count(r)"),
            "memory_nodes": count(memory, m, "MATCH (n) RETURN count(n)"),
            "memory_edges": count(memory, m, "MATCH ()-[r]->() RETURN count(r)"),
            "sessions": count(memory, m, "MATCH (s:Session) RETURN count(s)"),
            "episodes": count(memory, m, "MATCH (e:Episode) RETURN count(e)"),
            "playbooks": count(memory, m, "MATCH (p:Playbook) RETURN count(p)"),
        }
