# Maelin — See what breaks before you fix it. Remember what happened last time.

> **Graph Hacks Hackathon Submission** (WeMakeDevs × FalkorDB)  
> **Tracks Entered:** Track 01 (Connected Data), Track 02 (Agent Memory and Coordination), and Track 03 (Company Brain)  
> **Deployment Target:** [Vercel (golden-state-warriors)](https://vercel.com/golden-state-warriors) · [Deployment Guide](docs/deployment.md)  
> **Judge Evidence Packet:** [docs/judge_packet.md](docs/judge_packet.md)  
>
> **AI Assistance & Verification Disclosure:** AI coding assistants were used for UI scaffolding, boilerplate generation, and test harness drafting. All Cypher queries, graph data models, counterfactual Pareto logic (`logic.py`), and FalkorDB `Graph.copy()` simulation mechanics were architected, verified, and property-tested (`test_invariants.py`) by Team Pied-Piper.

---

## The Problem
When a security alert fires, the standard response is emergency containment—quarantine or shut down the compromised service. But in modern distributed architectures, that often causes an immediate self-inflicted outage (for example, taking down an authentication service breaks checkout and billing).

Worse, AI agents often repeat the exact same operational mistake next week because they have no persistent memory of previous containment outcomes.

## What Maelin Does
Maelin is an incident-response decision engine built on **FalkorDB**:
1. **Discovers all multi-hop attack routes:** Uses Cypher graph traversal to find every privilege path connecting an entry point to sensitive data through a compromised component, while separately mapping customer business dependencies with exact hop-by-hop provenance (`nodes(p)`, `relationships(p)`).
2. **Evaluates two counterfactual futures:** Compares **Future A** (emergency quarantine = high business outage) against **Future B** (surgical graph cut = zero customer impact).
3. **Replays actions on disposable graph clones:** Uses FalkorDB's native `Graph.copy()` to clone the topology, execute candidate edge/node cuts in Cypher, re-traverse the modified clone, and verify that 100% of attack paths are severed before recommending an intervention. Clones use dynamic request IDs (`maelin_{tenant}_sim_{uuid4().hex[:8]}`) with strict `try...finally` cleanup to prevent memory leaks.
4. **Remembers past outages across sessions:** When an operator reports that an intervention caused an unexpected outage, Maelin persists the outcome in an isolated FalkorDB memory graph (`Episode -> ActionExperience`). In future sessions, Maelin automatically penalizes that action and recommends a safer alternative.
5. **Maps organizational ownership (Company Brain):** Connects technical infrastructure and business flows to responsible teams (`(:Team)-[:OWNS]->(:Asset)`) so operators immediately know who owns affected components and postmortems.

---

## Why FalkorDB is Indispensable (Rule #3 Litmus Test)
* **Zero in-memory fallbacks:** Production code has no local JSON, NetworkX, or in-memory graph traversal fallbacks.
* **Fails closed:** If FalkorDB is offline or unreachable, the API immediately returns **HTTP 503**. 
* **Native Graph Clone & Replay:** Disposable simulations mutate isolated FalkorDB graph clones directly in Cypher, leaving the live topology untouched.
* **Native Graph Algorithms:** Leverages native FalkorDB GraphBLAS algorithms (`CALL algo.pageRank('Asset', 'DEPENDS_ON')`) inside MCP agent tools.

---

## How It Solves All Three Tracks

| Track | What FalkorDB Powers | How to Verify It |
|---|---|---|
| **Track 01: Connected Data** | Multi-hop Cypher queries (`CAN_PIVOT*1..7` & `DEPENDS_ON*1..7`) with explicit hop-by-hop path provenance (`nodes(p)`, `relationships(p)`), plus native GraphBLAS algorithm procedure (`CALL algo.pageRank('Asset', 'DEPENDS_ON')`). | Click **Investigate**. See two independent attack routes with full path provenance. Run MCP tool `compute_asset_centrality` or query `/api/centrality`. Run **Replay** to see FalkorDB cut edges on a clone and reduce remaining paths from 2 to 0. |
| **Track 02: Agent Memory & Coordination** | Specialists (`Recon`, `Memory`, `Remediation`) coordinate via immutable `Session -> Handoff` nodes in FalkorDB. Episodic and procedural memory penalizes failed actions across sessions. Disposable clones use dynamic UUIDs (`maelin_{tenant}_sim_{uuid4().hex[:8]}`) with strict `try...finally` cleanup. | Click **Report unexpected outage** on an action → start a **New Session** → recommendation switches to a safer alternative. Switch tenant (`alpha` vs `beta`) to verify strict isolation. Use 1-click **↻ Reset Demo State** in the toolbar to return to clean baseline anytime. |
| **Track 03: Company Brain (Knowledge Graph)** | Unified enterprise knowledge graph mapping services, customer revenue flows, accountable teams (`(:Team)-[:OWNS]->(:Asset)`), and incident memories. | Query `/api/teams` or use MCP `get_team_ownership` to trace impacted customer flows directly to accountable owners (e.g. Identity-SecOps, Payments Core, Data Infra) and tie postmortems to team responsibility. |

---

## Architecture & Multi-Agent Flow

![Maelin Architecture](docs/architecture.png)

---

## Quickstart

### Option A: Deploy to Vercel (Production Cloud)
Deploy the Maelin cockpit directly on Vercel:
* **Vercel Scope:** [https://vercel.com/golden-state-warriors](https://vercel.com/golden-state-warriors)
* **GitHub Repository:** [https://github.com/vivekyarra/Graph](https://github.com/vivekyarra/Graph)
* Configure FalkorDB environment variables (`FALKOR_HOST`, `FALKOR_PORT`, `FALKOR_PASSWORD`, `FALKOR_SSL=1`) in the Vercel project settings. See [docs/deployment.md](docs/deployment.md) for full instructions.

### Option B: Run Locally with Docker (2 Minutes)
```bash
docker compose up -d --build
```

### 2. Seed the demo tenant graphs
```bash
docker compose exec app python -m maelin.seed --tenant alpha
docker compose exec app python -m maelin.seed --tenant beta
```

### 3. Open the Dashboard
* **Maelin Dashboard:** [http://localhost:8000](http://localhost:8000)
* **FalkorDB Browser:** [http://localhost:3000](http://localhost:3000) (database port: 6379)

---

## Vercel Serverless Architecture & Persistent FalkorDB Hosting

### Serverless Execution & Graph Persistence
Maelin deploys to Vercel as a high-performance Python serverless application (`api/index.py` configured via `vercel.json`):
- **Vercel Global CDN**: Serves static assets (`/assets/*` -> `static/*`) directly from edge cache.
- **Serverless Compute**: Dispatches API requests (`/api/*` and `/`) to the FastAPI serverless handler (`api/index.py`).

Because **Vercel serverless functions cannot run an internal background Redis daemon**:
- Vercel functions are stateless and ephemeral; they connect via TLS to a dedicated external **FalkorDB** instance (e.g., [FalkorDB Cloud](https://app.falkordb.cloud) or a persistent cloud VM).
- All graph structures, multi-hop Cypher queries, agent handoff traces, and episodic memory (`Episode -> ActionExperience` nodes) persist permanently in FalkorDB across code deployments.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ VERCEL SERVERLESS + PERSISTENT FALKORDB ARCHITECTURE                                  │
│                                                                                        │
│   git push main ──► GitHub Actions CI ──► Vercel Serverless Auto-Deploy                │
│                                              │                                         │
│                                              ▼ (Edge Routing via vercel.json)          │
│                             ┌─────────────────────────────────┐                        │
│                             │     Vercel Global Edge CDN      │                        │
│                             └──────────────┬──────────────────┘                        │
│                                            │                                           │
│                  ┌─────────────────────────┴─────────────────────────┐                 │
│                  ▼                                                   ▼                 │
│     Static Assets (/assets/*)                             API & Cockpit UI (/ & /api/*)│
│     Routed to static/*                                    Routed to api/index.py       │
│     (cockpit.css, cockpit.js)                             (FastAPI Serverless App)     │
│                                                                      │                 │
│                                              TLS Connection (FALKOR_SSL=1)             │
│                                                                      ▼                 │
│                                                   ┌─────────────────────────────────┐  │
│                                                   │  Persistent FalkorDB Instance   │  │
│                                                   │  (Cloud or SSD Volume)          │  │
│                                                   │  Graph Memory Preserved!        │  │
│                                                   └─────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

The automatic deployment pipeline (GitHub Actions CI + Vercel auto-deploy) provides seamless **code delivery**, while **durable graph memory is preserved in hosted FalkorDB**.

### Deploying to Vercel

1. **Provision Persistent FalkorDB**:
   - **Managed**: [FalkorDB Cloud](https://app.falkordb.cloud) with encrypted SSD persistence, automated snapshots, and TLS.
   - **Self-Hosted**: Docker container with persistent named volume:
     ```bash
     docker run -d --name falkordb-prod -p 6379:6379 -v falkordb_data:/data falkordb/falkordb:latest --save 60 1 --appendonly yes --requirepass "secret"
     ```
2. **Import Repository in Vercel**:
   - In [Vercel Dashboard](https://vercel.com/golden-state-warriors), import `https://github.com/vivekyarra/Graph`.
3. **Configure Environment Variables in Vercel**:
   - `FALKOR_HOST`: Remote FalkorDB hostname or cloud IP
   - `FALKOR_PORT`: `6379`
   - `FALKOR_PASSWORD`: Database auth token
   - `FALKOR_SSL`: `1` (required for FalkorDB Cloud TLS connections)
   - `MAELIN_OPERATOR_TOKEN`: Secret token for operator authorization
   - `MAELIN_AGENT_TOOLS`: `mcp`
4. **One-Time Seeding for Remote Persistent Graph**:
   ```bash
   FALKOR_HOST="remote-host" FALKOR_PORT="6379" FALKOR_PASSWORD="secret" FALKOR_SSL="1" python -m maelin.seed --tenant alpha
   FALKOR_HOST="remote-host" FALKOR_PORT="6379" FALKOR_PASSWORD="secret" FALKOR_SSL="1" python -m maelin.seed --tenant beta
   ```

See [docs/deployment.md](docs/deployment.md) for the complete step-by-step Vercel configuration and operational guide.

---

## Core Cypher Queries

### 1. Bounded Multi-Hop Attack Traversal with Hop-by-Hop Provenance (`maelin/store.py`)
```cypher
MATCH p=(s:Asset {id:$source})-[:CAN_PIVOT*1..7]->(t:Asset {id:$target})
WITH p WHERE ANY(n IN nodes(p) WHERE n.id = $vulnerable)
RETURN [n IN nodes(p) | n.id] AS assets,
       [r IN relationships(p) | r.edge_id] AS pivots,
       [r IN relationships(p) | r.evidence] AS edge_evidence,
       nodes(p) AS path_nodes,
       relationships(p) AS path_relationships LIMIT 257
```
*Why this matters:* `shortestPath()` can be deceived by benign shortcuts that bypass the compromised node. This query guarantees finding all danger paths up to 7 hops and returns exact `nodes(p)` and `relationships(p)` for auditable hop-by-hop provenance.

### 2. Customer Business Dependency Traversal (`maelin/store.py`)
```cypher
MATCH p=(f:Asset)-[:DEPENDS_ON*1..7]->(s:Asset)
WHERE f.kind='business_flow'
RETURN f.id, f.value, [n IN nodes(p) | n.id],
       nodes(p) AS path_nodes,
       relationships(p) AS path_relationships LIMIT 1025
```
*Why this matters:* Recursively maps business services and revenue streams (checkout, billing, sign-in) down to dependent infrastructure assets to calculate modeled disruption cost.

### 3. Native FalkorDB Graph Algorithm (`CALL algo.pageRank`) (`maelin/store.py` & `maelin/mcp_server.py`)
```cypher
CALL algo.pageRank('Asset', 'DEPENDS_ON')
YIELD node, score
RETURN node.id AS asset_id, node.role AS role, score
ORDER BY score DESC
```
*Why this matters:* FalkorDB GraphBLAS algorithms directly rank critical structural bottlenecks in the dependency topology. Exposed as MCP tool `compute_asset_centrality` and API `/api/centrality`.

### 4. Organizational Ownership Subgraph for Company Brain (`maelin/store.py` & `maelin/seed.py`)
```cypher
MATCH (t:Team)-[:OWNS]->(a:Asset)
RETURN t.id AS team_id, t.name AS team_name, t.lead AS lead, t.contact AS contact, a.id AS asset_id
ORDER BY t.id, a.id
```
*Why this matters:* Unifies technical topology with human accountability (Track 03 Company Brain). Exposed as MCP tool `get_team_ownership` and API `/api/teams`.

### 5. Disposable Clone Simulation & Replay (`maelin/simulator.py`)
```cypher
// Executed on dynamically cloned graph: maelin_{tenant}_sim_{uuid4().hex[:8]}
MATCH ()-[r:CAN_PIVOT {edge_id:$edge_id}]->() DELETE r;
MATCH (n:Asset {id:$node_id}) DETACH DELETE n;
```
*Why this matters:* Counterfactual what-if simulation mutates only a disposable database clone and verifies containment with actual Cypher re-traversal before cleaning up in `try...finally`.

### 6. Episodic & Procedural Memory Recall (`maelin/store.py`)
```cypher
MATCH (e:Episode {fingerprint:$fingerprint})-[:OBSERVED]->(a:ActionExperience)
RETURN a.action_id, a.outcome, a.cost_observed, a.evidence_status, e.created, e.id
ORDER BY e.created DESC LIMIT 30
```
*Why this matters:* Prevents repeating previous operational failures across sessions while maintaining tenant isolation.

---

## Optional LLM Agent Mode (Gemini & OpenAI)

Maelin runs in deterministic policy mode by default. To enable model-powered analytical insight synthesis and function-calling plan adjudication:

```bash
pip install -r requirements.txt

# Set Gemini or OpenAI API key:
export GEMINI_API_KEY="<your-gemini-key>"
# or: export OPENAI_API_KEY="<your-openai-key>"

export MAELIN_USE_LLM=1
```

*Note: The LLM cannot invent graph edges, generate arbitrary Cypher, or execute cloud commands. It strictly analyzes and selects among graph-verified complete plans.*

---

## FastMCP Server

Maelin includes a built-in stdio FastMCP server exposing typed graph tools (`inspect_attack_paths`, `inspect_business_dependencies`, `compute_asset_centrality`, `get_team_ownership`, `recall_incident_outcomes`, `list_candidate_interventions`, `propose_containment`):

```bash
python -m maelin.mcp_server
```

---

## Test Suite

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```
* **62 offline and invariant tests pass in ~3 seconds.**
* Includes an exhaustive property-based oracle checking 5,000 random graph configurations.
* See [docs/judge_packet.md](docs/judge_packet.md) for live evaluation steps, FalkorDB Cypher verification, and judge Q&A.

