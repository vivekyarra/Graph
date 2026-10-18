# SentryGraph / MAELIN — Complete Cypher Catalog

Every query SentryGraph (package name: `maelin`) sends to **FalkorDB**, grouped by
the agent that issues it. Each entry states:

1. **Graph** — `db.select_graph("maelin_{tenant}_topology")` or `maelin_{tenant}_memory`.
2. **Protocol** — `GRAPH.RO_QUERY` (read-only, engine-enforced) or `GRAPH.QUERY` (mutation).
3. **Why a graph traversal** — what SQL joins, vector RAG or a Python traversal cannot prove.
4. **The exact Cypher** and the typical server-reported `run_time_ms`.

Latency figures are **server-reported** (`QueryResult.run_time_ms`) on the bundled
10-asset demo topology. They are single-digit milliseconds and are emitted live in
`telemetry_trace` on every `/api/investigate` response — never estimated in prose.

---

## Schema mapping (read this first)

The graph is deliberately compact: assets are one label distinguished by `kind`,
not a label per role. The query semantics are unchanged.

| Brief terminology | This repository |
|---|---|
| `:Ingress` | `(:Asset {kind:'ingress'})` |
| `:Service` | `(:Asset {kind:'service'})` |
| `:IAMRole` | `(:Asset {kind:'identity'})` — e.g. `admin-role` (privileged) |
| `:CVE` / `HAS_VULN` | the incident's vulnerable asset + `fingerprint` + `:Intervention` catalog |
| `:CONNECTS` | `[:CAN_PIVOT {edge_id, evidence, cap}]` |
| `:ASSUMES` | the `CAN_PIVOT` hop from a service to an identity asset |
| `topology_graph` | `maelin_{tenant}_topology` |
| `swarm_memory` | `maelin_{tenant}_memory` |
| `:Playbook` | `(:Playbook {action_id, command, description})` |
| `:RESOLVED_BY` | `(:Episode)-[:RESOLVED_BY {mttr_seconds, verified_by_agent, paths_severed}]->(:Playbook)` |
| `Session` / `Episode` | unchanged (`:Session`, `:Episode`) |

Two graphs per tenant, chosen by `Store.graphs(tenant)`:

```python
topology, memory = store.graphs(tenant)   # maelin_{tenant}_topology, maelin_{tenant}_memory
```

---

## Read/write boundary

| Code path | Method | FalkorDB protocol |
|---|---|---|
| Recon, Memory recall, Remediation, Company Brain, simulator reads | `Store._ro` | **`GRAPH.RO_QUERY`** |
| `seed.py`, `record_outcome`, handoffs, session writes, demo injection | `Store._rw` | `GRAPH.QUERY` |

`GRAPH.RO_QUERY` is rejected by the FalkorDB engine itself if the statement would
write, so reconnaissance cannot mutate live topology even if a query is wrong.

Every call is traced by `maelin/telemetry.py`:

```json
{
  "graph_name": "maelin_alpha_topology",
  "agent_name": "Recon & Graph Mapper",
  "query_type": "ro_query",
  "cypher": "MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target}) ...",
  "run_time_ms": 1.18,
  "evidence_id": "[E1]"
}
```

---

## Agent 1 — Recon & Graph Mapper

### 1.1 Bounded attack-path enumeration (provenance)

**Graph:** topology · **RO** · evidence `[E1]`

```cypher
MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots,
       [r IN relationships(p) | r.evidence] AS edge_evidence,
       nodes(p) AS path_nodes,
       relationships(p) AS path_relationships
LIMIT 257
```

*Why a graph:* the answer is a *set of paths*, with hop order and per-edge evidence.
A relational schema needs a recursive CTE with manual cycle handling and still
cannot return `nodes(p)` / `relationships(p)` as first-class provenance. Vector RAG
retrieves similar text; it cannot enumerate routes.

*Deliberate choice:* `shortestPath()` is **not** used. A shorter benign route can
mask a longer exploitable one, so all bounded routes are enumerated. More than 256
candidates raises `OverflowError` rather than silently truncating.

`SELECT graph` invocation: `db.select_graph("maelin_alpha_topology")`.
Typical: **1–3 ms** on the demo topology.

### 1.2 Customer dependency paths

**Graph:** topology · **RO** · evidence `[E2]`

```cypher
MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id],
       nodes(p) AS path_nodes, relationships(p) AS path_relationships
LIMIT 1025
```

*Why a graph:* impact propagates transitively through arbitrary depth; this is the
textbook case where recursive traversal beats a fixed number of SQL joins.

### 1.3 Attack chokepoints (path share + betweenness)

**Graph:** topology · **RO** · evidence `[E3]`

```cypher
MATCH p=(:Asset {id:$source})-[:CAN_PIVOT*1..7]->(:Asset {id:$target})
WITH p LIMIT 257
WITH collect(p) AS paths
WITH paths, size(paths) AS total
UNWIND paths AS p
UNWIND nodes(p)[1..-1] AS n
RETURN n.id, n.kind, count(*) AS routes, total
ORDER BY routes DESC, n.id
LIMIT $limit
```

```cypher
CALL algo.betweenness({nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT'],
                        samplingSize:4096, samplingSeed:42})
YIELD node, score
RETURN node.id, score
```

Seeded sampling (`samplingSeed: 42`) makes the structural ranking **deterministic**,
so the same graph always produces the same ranking — required for reproducible demo
and tests.

### 1.4 Track 01 — critical choke-point cut math

**Graph:** topology · **RO** · evidence `[E3]` · exposed as the MCP tool
`find_critical_chokepoints` and `GET /api/chokepoints`.

**(a) Native betweenness**

```cypher
CALL algo.betweenness(['Asset'], ['CAN_PIVOT'])
YIELD node, score
RETURN node.id AS service, coalesce(node.kind, 'service') AS tier, score
ORDER BY score DESC
LIMIT $limit
```

If the server rejects the procedure (small graph, older build), the tool records
`betweenness_available: false` and continues with deterministic path counting —
reconnaissance never fails because an optional algorithm is unavailable.

**(b) Attack-path cut simulation**

```cypher
MATCH p = (ing:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(svc:Asset {kind:'service'})
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
LIMIT $limit
```

On the demo graph this reports that isolating `auth-service` (or `edge-gateway`)
severs **1 of 1 (100.0%)** modeled exploit paths to `admin-role`. The Remediation
agent renders that as a sentence:

> *Isolating `auth-service` severs 1 of 1 (100.0%) active exploit paths to `admin-role`.*

*Why a graph:* this is a counterfactual over a *path set*, not a property of a row.
Simulating a node removal and recounting distinct multi-hop routes is one traversal
in Cypher. In SQL it requires materialising every path, then one aggregate query per
candidate node; in RAG it is not expressible at all.

**(c) Vulnerable-asset fallback** (the chosen pivot may sit on a route whose last
service hop is itself)

```cypher
MATCH p = (ing:Asset {kind:'ingress'})-[:CAN_PIVOT*1..6]->(:Asset {kind:'identity'})
WITH p, [n IN nodes(p) | n.id] AS ids, nodes(p)[-1].id AS role
WHERE $vulnerable IN ids
RETURN count(DISTINCT p), collect(DISTINCT role)
```

**(d) Python-counted fallback** if the aggregation shape is rejected by a server
build: return path node lists from FalkorDB and count in Python. Only the *counting*
moves; every path still comes from Cypher — no hidden in-memory graph.

### 1.5 Attack-path cut simulation in the simulator

**Graph:** disposable clone · **RO**

```cypher
MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id=$vulnerable)
RETURN [n IN nodes(p) | n.id], [r IN relationships(p) | r.edge_id]
LIMIT 257
```

Applied after real `DELETE`s on a `Graph.copy()` clone — the plan is verified by
re-traversal, not by trusting the optimizer.

---

## Agent 2 — Episodic Memory Coordinator

### 2.1 Exact-fingerprint recall

**Graph:** memory · **RO** · evidence `[E5]`

```cypher
MATCH (p:IncidentPattern {fingerprint:$fingerprint})-[:HAS_EPISODE]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC
LIMIT 30
```

### 2.2 Semantic pattern recall

**Graph:** memory · **RO**

```cypher
MATCH (k:SemanticPattern {key:$key})-[:REMEMBERS]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC
LIMIT 20
```

Similarity is discounted (`memory_weight = 0.25`) because a role/kind match is
weaker evidence than an exact incident match.

### 2.3 Vector recall over `Episode.embedding`

**Graph:** memory · **RO**

```cypher
CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($vec))
YIELD node, score
MATCH (node)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, node.created, node.id, score
```

The embedding is a structural one-hot of the entry/pivot/target asset kinds
(15 dimensions). Two incidents with different IDs but the same *shape* land close
together. This is the one place a vector index is correct — and it is still joined
into the graph for the action it supports.

### 2.4 Track 02 — proven playbooks across sessions

**Graph:** memory · **RO** · evidence `[E6]` · MCP tool `recall_proven_playbook`,
`GET /api/playbooks`

```cypher
MATCH (s:Session)-[:RECORDED]->(ep:Episode)-[r:RESOLVED_BY]->(pb:Playbook)
MATCH (ep)-[:OBSERVED]->(ax:ActionExperience {outcome:'safe'})
WHERE ep.cve_id = $cve_id OR ep.service_tier = $service_tier
RETURN pb.action_id AS playbook_id,
       pb.command AS remediation_cmd,
       count(DISTINCT ep) AS times_used,
       avg(r.mttr_seconds) AS avg_mttr_seconds,
       max(ep.timestamp) AS last_used_at
ORDER BY times_used DESC, avg_mttr_seconds ASC
LIMIT $limit
```

Ranking is *usage first, then mean time to resolve*, so a playbook that worked once
does not outrank one that has worked five times. The `outcome:'safe'` filter is a
deliberate tightening of the brief's query: an action reported as causing an
outage is a memory of a failure, not a **proven** playbook. `:RECORDED` is written
alongside `:RESULTED_IN` on every episode so the recall path exists explicitly.

### 2.5 Outcome write (episode + playbook link)

**Graph:** memory · **RW** (`GRAPH.QUERY`)

```cypher
MATCH (s:Session {id:$session})
MERGE (e:Episode {id:$episode})
ON CREATE SET e.fingerprint=$fingerprint, e.created=$created, e.note=$note,
 e.cve_id=$fingerprint, e.service_tier=$service_tier,
 e.paths_severed=$paths_severed, e.timestamp=$created
MERGE (a:ActionExperience {key:$episode})
ON CREATE SET a.action_id=$action_id, a.outcome=$outcome,
 a.cost_observed=$cost, a.evidence_status='operator_report'
MERGE (s)-[:RESULTED_IN]->(e)
MERGE (e)-[:OBSERVED]->(a)
```

```cypher
MATCH (e:Episode {id:$episode}), (a:ActionExperience {key:$episode})
MERGE (pb:Playbook {action_id:$action_id})
ON CREATE SET pb.command=$command, pb.description=$description
MERGE (e)-[r:RESOLVED_BY]->(pb)
ON CREATE SET r.mttr_seconds=$mttr_seconds, r.verified_by_agent=$verified_by_agent,
 r.paths_severed=$paths_severed
```

`mttr_seconds` (session age), `paths_severed` (derived from the recorded action
against the Recon handoff's path set) and `service_tier` (asset kind) are derived
from graph data, never invented. A repeated POST for the same session+action is
idempotent; a *contradictory* repeat raises `ValueError` instead of silently
keeping the first value.

---

## Agent 3 — Explainable Remediation

### 3.1 Proven minimum cut (Menger bound)

**Graph:** topology · **RO** · evidence `[E4]`

```cypher
MATCH (s:Asset {id:$vulnerable}), (t:Asset {id:$target})
CALL algo.maxFlow({sourceNodes:[s], targetNodes:[t], capacityProperty:'cap',
                   nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT']})
YIELD edges, edgeFlows, maxFlow
RETURN [e IN edges | e.edge_id], edgeFlows, maxFlow
```

With unit edge capacities, max-flow equals the minimum number of pivots that must
be cut. Residual reachability from the source then yields one concrete cut.

### 3.2 Intervention catalog

**Graph:** topology · **RO** · evidence `[E4]`

```cypher
MATCH (a:Intervention)
RETURN a.id, a.label, a.blocked_nodes, a.blocked_edges, a.cost, a.note
ORDER BY a.id
```

The deterministic kernel (`maelin/logic.py`) scores every complete 1–3 action cut.
The LLM, when configured, may only select **within** the verified envelope.

### 3.3 Evidence verification

After the plan is chosen, `maelin/evidence.py` checks that every cited node
(blocked services, pivot endpoints, target roles) is a member of the node ID set
returned by the attack-path query. The API returns:

```json
"hallucination_check": {
  "verified": true,
  "evidence_ids": ["[E1]", "[E2]", "[E3]", "[E4]", "[E5]"],
  "verified_nodes": ["admin-role", "auth-service"],
  "unverified_nodes": [],
  "citations_checked": 2,
  "method": "deterministic set membership over FalkorDB-returned node IDs"
}
```

The UI renders **Verified by FalkorDB Graph Proof** or **Unverified citations
detected** accordingly.

---

## Company Brain (supporting subgraph)

**Graph:** topology · **RO**

```cypher
CALL db.idx.fulltext.queryNodes('Document', $q) YIELD node, score
RETURN node.id, node.kind, node.title, node.body, node.created, score
ORDER BY score DESC LIMIT $limit
```

```cypher
MATCH (t:Team)-[:OWNS]->(a:Asset) WHERE a.id IN $ids
OPTIONAL MATCH (p:Person {on_call:true})-[:MEMBER_OF]->(t)
RETURN a.id, t.name, t.lead, collect(p.name)
```

```cypher
MATCH (d:Decision)-[:SOURCED_FROM]->(src:Document)
OPTIONAL MATCH (d)-[:AFFECTS]->(a:Asset)
WITH d, src, collect(a.id) AS assets
WHERE src.id IN $docs OR any(x IN assets WHERE x IN $focus)
MATCH (d)-[:DECIDED_BY]->(p:Person)
RETURN d.id, d.title, p.name, src.id, src.title
ORDER BY d.created DESC LIMIT 3
```

```cypher
CALL algo.pageRank('Asset', 'DEPENDS_ON')
YIELD node, score
RETURN node.id AS asset_id, node.role AS role, score
ORDER BY score DESC
```

---

## Injection & plan-cache invariants

* **No f-string Cypher.** Every identifier the user can influence (tenant, asset,
  fingerprint, source/target) is passed via the named `params` dict. The only
  interpolated identifiers are a closed literal set (relationship type constants in
  `seed.py` and the fixed vector dimension in DDL).
* **Bounded everything.** Paths `LIMIT 257` with an explicit overflow error; business
  paths `LIMIT 1025`; candidate actions capped at 48 (≤18,472 combinations).
* **No arbitrary query tool.** The MCP server exposes 13 typed tools with scalar
  arguments — there is no `execute_cypher` / `query_write`.
* **Read-only by protocol.** Recon tools cannot write even if a query is malformed,
  because `GRAPH.RO_QUERY` rejects writes server-side.

Regression tests for these invariants live in `tests/test_agent_proofs.py`,
`tests/test_challenger_security.py` and `tests/test_invariants.py`.
