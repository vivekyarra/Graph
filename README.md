# MAELIN

### Graph-Native Counterfactual Incident Response & Multi-Agent Memory Engine

[![CI Verification](https://github.com/vivekyarra/Graph/actions/workflows/falkordb-integration.yml/badge.svg)](https://github.com/vivekyarra/Graph/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Database: FalkorDB](https://img.shields.io/badge/Database-FalkorDB-FF4F00.svg)](https://www.falkordb.com/)
[![Protocol: Model Context Protocol](https://img.shields.io/badge/Protocol-MCP-8A2BE2.svg)](https://modelcontextprotocol.io/)

**Simulate before you remediate.** Zero in-memory state, bounded Cypher provenance, provable min-cut isolation, and multi-tenant causal memory powered by native **FalkorDB** graph algorithms.

[Live Interactive Cockpit](https://maelin-graph-hacks-demo.onrender.com) • [System Verification Guide](docs/evaluation_guide.md) • [Deployment Docs](docs/deployment.md) • [Contributing](CONTRIBUTING.md)

---

## The problem

When a security alert fires, the reflex is to quarantine the compromised service. In a connected system that often causes a self-inflicted outage: take down `auth-service` and checkout, billing and sign-in go with it. Next week someone makes the same call again, because nothing remembers what happened.

## What MAELIN does

MAELIN is an incident-response agent team whose only shared brain is **FalkorDB**.

| | What happens | FalkorDB feature doing the work |
|---|---|---|
| 1 | **Recon** enumerates *every* multi-hop route from the entry point through the compromised asset to the crown jewel, plus every customer flow that depends on each asset | Bounded variable-length Cypher (`CAN_PIVOT*1..7`, `DEPENDS_ON*1..7`) with `nodes(p)` / `relationships(p)` provenance |
| 2 | **Recon** ranks attack chokepoints | Cypher path counting + `algo.betweenness` |
| 3 | **Memory** recalls past outcomes for this incident, a structurally similar one, or a semantically matching pattern | Episode graph + **vector index** (`db.idx.vector.queryNodes`) |
| 4 | **Remediation** scores every complete 1–3 action cut, compares *Future A* (quarantine, 160 $k/h impact) with *Future B* (surgical cut, 0 impact) and **proves the cut is minimal** | `algo.maxFlow` min-cut (Menger bound) |
| 5 | The chosen plan is **replayed on a disposable clone**: real `DELETE`s, real re-traversal, clone deleted | `GRAPH.COPY` via `Graph.copy()` |
| 6 | The operator reports the outcome. It becomes an episode **and** a postmortem document; the next session picks a different plan | Memory graph writes + Company Brain documents |
| 7 | Anyone can ask "is it safe to quarantine auth-service?" and get an answer **with sources**: runbooks, postmortems, owners, on-call, decisions | **Full-text index** (`db.idx.fulltext.queryNodes`) + ownership/decision traversal |

Agents never pass state in Python. Each specialist reads the previous one's work from immutable `(:Session)-[:HAS_HANDOFF]->(:Handoff)` nodes, and every graph read goes through **real MCP stdio tool calls** (`maelin/mcp_server.py`, nine bounded tools). Remove FalkorDB and nothing works: the API fails closed with HTTP 503.

---

## Capability Matrix & Architecture

| Architectural Domain | Core Technical Objectives | Interactive Demonstration & Verification |
|---|---|---|
| **Autonomous Graph Agents** *(Connected Data)* | Multi-hop reasoning, native graph algorithms as agent tools, MCP tool selection, actions grounded in graph topologies, explainable results | **Investigate** → 2 routes with hop provenance; HUD chips for `algo.maxFlow`, chokepoints and `algo.pageRank`; **Replay** cuts edges on a clone (2 → 0 routes); **Cypher** button inspects generated queries |
| **Agent Memory & State Coordination** *(Episodic, Semantic & Procedural)* | Multi-layered episodic, semantic and procedural memory; persistent history; zero-in-memory handoffs; tenant-scoped isolation; high concurrency | Report an outage → **New session** → decision dynamically adapts with causal with/without-memory ablation banner. **Memory** tab: sessions, episodes, exact/semantic/vector recall, handoff ledger. Multi-tenant graph isolation |
| **Company Brain & Knowledge Subgraph** *(Organizational Intelligence)* | Unified enterprise knowledge graph mapping services, revenue flows, teams, and postmortems; cited question answering; live ownership graph | **Brain** tab: ask domain questions with citation grounding. Interactive node inspection for service owners, on-call engineers, ADRs, postmortems, and blast radius |

---

## Graph data model

Two graphs per tenant: `maelin_{tenant}_topology` (infrastructure + company brain) and `maelin_{tenant}_memory` (agent memory).

```
TOPOLOGY GRAPH
(:Asset {id, kind, role, value, critical})
(:Asset)-[:CAN_PIVOT {edge_id, evidence, cap}]->(:Asset)        attack surface
(:Asset {kind:'business_flow'})-[:DEPENDS_ON]->(:Asset)           customer impact
(:Intervention {id, label, blocked_nodes, blocked_edges, cost})   action catalog
(:Team)-[:OWNS]->(:Asset)
(:Person {on_call})-[:MEMBER_OF]->(:Team)
(:Document {kind: runbook|postmortem|adr|ticket|chat})-[:ABOUT]->(:Asset)
(:Document)-[:AUTHORED_BY]->(:Person)
(:Decision)-[:DECIDED_BY]->(:Person)
(:Decision)-[:SOURCED_FROM]->(:Document)
(:Decision)-[:AFFECTS]->(:Asset)
(:GraphMetadata {source, vulnerable, target, fingerprint})

MEMORY GRAPH
(:Session)-[:HAS_HANDOFF]->(:Handoff {agent, status, payload})    agent coordination
(:Session)-[:HAS_TURN]->(:ConversationTurn)                       conversation history
(:Session)-[:PROPOSED]->(:ProposedAction)
(:Session)-[:RESULTED_IN]->(:Episode {embedding})-[:OBSERVED]->(:ActionExperience)   episodic
(:IncidentPattern)-[:HAS_EPISODE]->(:Episode)
(:IncidentPattern)-[:HAS_PROCEDURE]->(:Procedure)-[:SUPPORTED_BY]->(:ActionExperience)   procedural
(:SemanticPattern)-[:REMEMBERS]->(:Episode)                        semantic
```

**Indexes** (created at seed): range indexes on `Asset.id`, `Team.id`, `Person.id`, `Document.id`, `Intervention.id`, `Session.id`, `Episode.id`, `IncidentPattern.fingerprint`; a full-text index on `Document(title, body)`; a cosine vector index on `Episode.embedding`.

---

## Core Cypher queries and graph algorithms

### 1. Every attack route through the compromised asset, with hop-by-hop provenance (`store.py`)
```cypher
MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots,
       [r IN relationships(p) | r.evidence] AS edge_evidence,
       nodes(p) AS path_nodes,
       relationships(p) AS path_relationships LIMIT 257
```
`shortestPath()` would miss a dangerous longer route when a benign shortcut exists. Over 256 routes, MAELIN refuses to conclude rather than truncate.

### 2. Proven minimum cut: `algo.maxFlow` (`store.py`)
```cypher
MATCH (s:Asset {id:$vulnerable}), (t:Asset {id:$target})
CALL algo.maxFlow({sourceNodes:[s], targetNodes:[t], capacityProperty:'cap',
                   nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT']})
YIELD edges, edgeFlows, maxFlow
```
With unit capacities, max-flow equals the minimum number of pivots that must be cut (Menger's theorem). The residual graph yields a concrete cut (`p3 + p5`), and the UI marks the recommended plan **Proven minimal** when it matches.

### 3. Attack chokepoints (`store.py`)
```cypher
MATCH p=(:Asset {id:$source})-[:CAN_PIVOT*1..7]->(:Asset {id:$target})
WITH p LIMIT 257
WITH collect(p) AS paths
WITH paths, size(paths) AS total
UNWIND paths AS p UNWIND nodes(p)[1..-1] AS n
RETURN n.id, count(*) AS routes, total ORDER BY routes DESC
```
plus `CALL algo.betweenness({nodeLabels:['Asset'], relationshipTypes:['CAN_PIVOT'], samplingSeed:42})`.

### 4. Customer dependency and blast radius (`store.py`)
```cypher
MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset) WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id], nodes(p), relationships(p) LIMIT 1025
```

### 5. Disposable clone replay (`simulator.py`)
```cypher
// on maelin_{tenant}_sim_{uuid4().hex[:8]}, created with Graph.copy(), deleted in finally
MATCH ()-[r:CAN_PIVOT {edge_id:$edge_id}]->() DELETE r;
MATCH (n:Asset {id:$node_id}) DETACH DELETE n;
```
then query 1 is re-run on the clone.

### 6. Memory recall: exact, semantic and vector (`store.py`)
```cypher
MATCH (p:IncidentPattern {fingerprint:$fingerprint})-[:HAS_EPISODE]->(e:Episode)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, e.id;

CALL db.idx.vector.queryNodes('Episode', 'embedding', $k, vecf32($vec)) YIELD node, score
MATCH (node)-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, score
```
The embedding encodes the kinds of the entry point, the compromised pivot and the target. A structurally similar incident (e.g. entry via a service instead of the internet) is recalled with a similarity-discounted weight.

### 7. Company Brain answer with sources (`brain.py`)
```cypher
CALL db.idx.fulltext.queryNodes('Document', $q) YIELD node, score RETURN node.id, node.title, score;

MATCH (t:Team)-[:OWNS]->(a:Asset) WHERE a.id IN $ids
OPTIONAL MATCH (p:Person {on_call:true})-[:MEMBER_OF]->(t)
RETURN a.id, t.name, t.lead, collect(p.name);

MATCH (d:Decision)-[:SOURCED_FROM]->(src:Document), (d)-[:DECIDED_BY]->(p:Person)
RETURN d.title, p.name, src.title
```
Ownership is the `(:Team)-[:OWNS]->(:Asset)` subgraph; `CALL algo.pageRank('Asset', 'DEPENDS_ON')` ranks the most depended-on assets.

---

## Quickstart (local, about two minutes)

```bash
docker compose up -d --build
docker compose exec app python -m maelin.seed --tenant alpha
docker compose exec app python -m maelin.seed --tenant beta
```
Open **http://localhost:8000**. FalkorDB Browser: http://localhost:3000.

Single-container demo (FalkorDB and the app in one image, auto-seeded):
```bash
docker build -f Dockerfile.demo -t maelin-demo . && docker run -p 8000:8000 -e MAELIN_PUBLIC_DEMO=1 maelin-demo
```

### Interactive Verification Walkthrough (60-Second Flow)
1. **Investigate** (or press ↵): watch the agents and MCP calls, then hover **Future A** and **Future B** to preview them on the graph.
2. **Replay B on a graph clone**: the cut edges are marked and the routes go from 2 to 0.
3. Click **Caused outage** on *Revoke admin role*, then **New session**: memory changes the decision, and the ablation banner shows why.
4. **Brain** tab: ask *"What happened when we revoked the admin role?"*. The new postmortem is cited. Click any node for owners and on-call.
5. Press **⌘K → Inject shadow route**, then **Re-test old plan**: it now fails on a fresh clone, and re-investigating finds the 3rd route.

Keyboard: `⌘K` commands · `↵` investigate · `1`/`2`/`3` tabs · `/` ask the brain · `Esc` clear.

### Deployment and security
* Remote deployments set `MAELIN_OPERATOR_TOKEN`; all graph reads and writes require the `x-maelin-operator-token` header (constant-time compare, no well-known bypass tokens).
* `MAELIN_PUBLIC_DEMO=1` allows tokenless access **only** to the synthetic `alpha`/`beta` tenants, for a hosted public demo. Uploads (new tenants) always need the token.
* Render Deployment ([maelin-graph-hacks-demo](https://maelin-graph-hacks-demo.onrender.com)) + FalkorDB Cloud: see [docs/deployment.md](docs/deployment.md) (`FALKOR_HOST`, `FALKOR_PORT`, `FALKOR_PASSWORD`, `FALKOR_SSL=1`).
* Optional LLM layer (`OPENAI_API_KEY` / `GEMINI_API_KEY` / Ollama via `MAELIN_LLM_BASE_URL`): models may only choose among graph-verified plans and read-only tools. They never write Cypher or execute actions.

---

## Tests and verification

```bash
pip install -r requirements-dev.txt
python -m pytest -q                                # offline suite (88 tests)
FALKOR_INTEGRATION=1 python -m pytest -q           # + live FalkorDB suites (101 tests)
python -m maelin.verify --output verification-proof.json  # reproducible cold → replay → memory → drift proof
python tests/e2e_real_browser.py                   # real Chromium journey against the running app
```
CI (`.github/workflows`) runs all of the above against a real FalkorDB container and uploads the proof JSON, screenshots and browser traces as artifacts. This includes a property-based oracle over 5,000 random graphs, min-cut optimality proofs, vector-memory validation, and Company Brain knowledge traversals.

For the formal evaluation methodology, proofs, and architecture FAQ, see the [System Verification & Evaluation Guide](docs/evaluation_guide.md). For development setup and contribution standards, see [CONTRIBUTING.md](CONTRIBUTING.md). For security invariants, see [SECURITY.md](SECURITY.md).

All data is synthetic. MAELIN never touches real infrastructure; recommendations are bounded to the modeled graph and are not a real-world safety certificate.

---

## Project Context & Compliance Disclosures

### Track & Architecture Mapping
MAELIN was developed for **Graph Hacks 2026 (WeMakeDevs × FalkorDB)**, addressing three core technical capability domains:
* **Track 01: Agents That Act on Connected Data** — Multi-hop Cypher traversals (`nodes(p)`, `relationships(p)`), native `algo.maxFlow` min-cut, and `algo.pageRank` dependency centrality.
* **Track 02: Agent Memory and Coordination** — Episodic, semantic, and procedural memory graphs, zero-in-memory handoffs, and tenant-isolated causal policy ablation.
* **Track 03: Company Brain** — Unified enterprise knowledge graph mapping services, revenue flows, and engineering teams with cited natural-language retrieval.

### AI Assistance & Verification Disclosure
In accordance with open-source hackathon disclosure rules: AI coding assistants were used for UI scaffolding, boilerplate generation, and test-harness drafting. The graph data model, every Cypher query, the counterfactual Pareto kernel (`logic.py`), the `Graph.copy()` replay mechanics and the min-cut / memory designs were reviewed, verified and property-tested (`test_invariants.py`, live FalkorDB suites) by Team Pied-Piper, who can explain every query and decision.

